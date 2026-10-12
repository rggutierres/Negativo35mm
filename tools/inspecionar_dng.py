"""
Inspeciona um DNG e diz se ele serve para o pipeline.

    python tools/inspecionar_dng.py "C:\\caminho\\foto.dng"

Responde às perguntas que importam:

1. É realmente um DNG, ou só um JPG com nome trocado?
2. Os pixels são Bayer cru (RAW de verdade) ou já vieram demosaicos?
3. Está clipado / subexposto?
4. O que a câmera aplicou por cima (WB, curva, correções de lente)?

A resposta da pergunta 2 é a mais importante e quase ninguém verifica.
Um DNG pode ser um "TIFF fantasia": extensão .dng, mas com pixels RGB já
processados pela câmera. Isso não é inútil, mas você perde o controle que
o RAW deveria te dar.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# Tags TIFF que interessam para DNG.
TAGS = {
    0x0100: "ImageWidth",
    0x0101: "ImageLength",
    0x0102: "BitsPerSample",
    0x0103: "Compression",
    0x0106: "PhotometricInterpretation",
    0x010F: "Make",
    0x0110: "Model",
    0x0111: "StripOffsets",
    0x0115: "SamplesPerPixel",
    0x0117: "StripByteCounts",
    0x0131: "Software",
    0x014A: "SubIFDs",
    0x828D: "CFARepeatPatternDim",
    0x828E: "CFAPattern",
    0xC612: "DNGVersion",
    0xC614: "UniqueCameraModel",
    0xC61A: "BlackLevel",
    0xC61D: "WhiteLevel",
    0xC621: "ColorMatrix1",
    0xC628: "AsShotNeutral",
    0xC62A: "BaselineExposure",
    0xC65A: "CalibrationIlluminant1",
}

# PhotometricInterpretation
PHOTOMETRIC = {
    0: "WhiteIsZero (Bayer invertido)",
    1: "BlackIsZero (Bayer normal)",
    2: "RGB (JÁ DEMOSAICADO!)",
    3: "Palette",
    6: "YCbCr",
    32803: "CFA (Bayer cru)",
    34892: "LinearRaw",
}

COMPRESSION = {1: "nenhuma", 5: "LZW", 6: "JPEG antigo", 7: "JPEG", 8: "Deflate", 32773: "PackBits"}


def ler_tiff(dados: bytes) -> dict[int, object]:
    """
    Lê as tags do primeiro IFD. Suficiente para diagnóstico.

    Devolve tag -> valor: escalar para contagem 1, lista para contagem > 1,
    string para ASCII. NÃO aninha em listas -- isso já causou bug silencioso
    (um valor virava [[2]] e a comparação `phot == 2` falhava sempre).
    """
    if dados[:4] == b"II*\x00":
        ordem = "<"
    elif dados[:4] == b"MM\x00*":
        ordem = ">"
    else:
        raise ValueError(f"não é TIFF/DNG (assinatura {dados[:4]!r})")

    offset = struct.unpack_from(ordem + "I", dados, 4)[0]
    vistos: set[int] = set()
    tags: dict[int, object] = {}

    # Segue a cadeia de IFDs, coletando o que aparecer primeiro.
    while offset and offset not in vistos and len(vistos) < 12:
        vistos.add(offset)
        if offset + 2 > len(dados):
            break
        n = struct.unpack_from(ordem + "H", dados, offset)[0]
        for i in range(n):
            pos = offset + 2 + i * 12
            if pos + 12 > len(dados):
                break
            tag, tipo, cont = struct.unpack_from(ordem + "HHI", dados, pos)

            tamanhos = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}
            tam = tamanhos.get(tipo, 1) * cont
            desloc = pos + 8
            if tam > 4:
                # O valor não cabe nos 4 bytes do campo: é um ponteiro.
                desloc = struct.unpack_from(ordem + "I", dados, pos + 8)[0]

            try:
                valor = _ler_valor(ordem, tipo, cont, dados, desloc)
            except (struct.error, IndexError):
                valor = "?"

            if tag in tags:
                # Tag repetida em outro IFD: concatena em vez de sobrescrever.
                antigo = tags[tag]
                if isinstance(antigo, list):
                    antigo.extend(valor if isinstance(valor, list) else [valor])
                else:
                    tags[tag] = [antigo, valor]
            else:
                tags[tag] = valor

        prox = struct.unpack_from(ordem + "I", dados, offset + 2 + n * 12)[0]
        offset = prox

    return tags


def _ler_valor(ordem: str, tipo: int, cont: int, dados: bytes, desloc: int):
    """Extrai um valor TIFF já desaninhado: string, escalar ou lista."""
    if tipo == 2:  # ASCII
        return dados[desloc:desloc + cont].split(b"\x00")[0].decode("utf-8", "replace")
    if tipo == 3:  # SHORT
        vals = list(struct.unpack_from(ordem + f"{cont}H", dados, desloc))
    elif tipo in (4, 9):  # LONG / SLONG
        vals = list(struct.unpack_from(ordem + f"{cont}I", dados, desloc))
    elif tipo == 5:  # RATIONAL
        vals = [
            struct.unpack_from(ordem + "II", dados, desloc + 8 * k)
            for k in range(cont)
        ]
    elif tipo == 8:  # SSHORT
        vals = list(struct.unpack_from(ordem + f"{cont}h", dados, desloc))
    else:  # BYTE e afins
        vals = list(dados[desloc:desloc + cont])

    return vals[0] if cont == 1 else vals


def main() -> int:
    if len(sys.argv) < 2:
        print("uso: python tools/inspecionar_dng.py <arquivo.dng>", file=sys.stderr)
        return 2

    caminho = Path(sys.argv[1]).expanduser()
    if not caminho.exists():
        print(f"ERRO: não encontrei {caminho}", file=sys.stderr)
        return 2

    dados = caminho.read_bytes()
    tamanho_mb = len(dados) / 1024 / 1024

    print(f"arquivo      : {caminho.name}")
    print(f"tamanho      : {tamanho_mb:.1f} MB")
    print(f"assinatura   : {dados[:4]!r}")

    # Alguns apps salvam JPG com extensão .dng. Verifica antes de tudo.
    if dados[:2] == b"\xff\xd8":
        print()
        print("*** ISTO É UM JPEG, NÃO UM DNG ***")
        print("O arquivo tem extensão .dng mas o conteúdo é JPEG (começa com FFD8).")
        print("Provavelmente o app salvou JPG e o nome foi trocado, ou a opção")
        print("de RAW não está ativa de fato.")
        return 1

    try:
        tags = ler_tiff(dados)
    except ValueError as e:
        print(f"ERRO: {e}")
        return 1

    print()
    print("=== metadados ===")
    for tag in (0x010F, 0x0110, 0x0131, 0xC614, 0xC612, 0x0100, 0x0101, 0x0102):
        if tag in tags:
            nome = TAGS.get(tag, f"0x{tag:04X}")
            print(f"  {nome:<20}: {tags[tag]}")

    print()
    print("=== a pergunta que importa: os pixels são Bayer cru? ===")
    phot = tags.get(0x0106)
    cfa = 0x828E in tags or 0x828D in tags
    spp = tags.get(0x0115)

    if phot is not None:
        print(f"  PhotometricInterpretation = {phot} -> {PHOTOMETRIC.get(phot, 'desconhecido')}")

    if phot == 2:
        print()
        print("  >>> JÁ DEMOSAICADO (RGB), NÃO É BAYER CRU <<<")
        print("  Este DNG guarda pixels RGB que a câmera já processou. Você")
        print("  ainda tem 16 bits e mais margem que um JPEG, mas as decisões")
        print("  de cor e redução de ruído já foram tomadas pelo celular.")
        print("  Para digitalizar filme, prefira o modo PRO da câmera, que")
        print("  grava Bayer cru de quadro único.")
    elif phot == 32803 or cfa:
        print()
        print("  >>> BAYER CRU: é RAW de verdade <<<")
        print(f"  CFAPattern presente: {cfa}   SamplesPerPixel: {spp}")
        print("  Ideal para o pipeline: aqui o negativo não sofreu nenhuma")
        print("  curva ou balanço de branco antes de chegar em você.")
    else:
        print(f"  (inconclusivo: photometric={phot}, cfa={cfa}, spp={spp})")

    comp = tags.get(0x0103)
    if comp is not None:
        print(f"  Compression = {comp} -> {COMPRESSION.get(comp, '?')}")

    print()
    print("=== o que a câmera aplicou ===")
    if 0xC628 in tags:
        print(f"  AsShotNeutral  : {tags[0xC628]}")
        print("                   (o balanço que a câmera escolheu -- ignoramos)")
    if 0xC61A in tags:
        print(f"  BlackLevel     : {tags[0xC61A]}")
    if 0xC61D in tags:
        print(f"  WhiteLevel     : {tags[0xC61D]}")
    if 0xC62A in tags:
        print(f"  BaselineExposure: {tags[0xC62A]}")

    print()
    print("=== leitura completa com rawpy ===")
    try:
        import numpy as np  # noqa: F401
        import rawpy
    except ImportError as e:
        print(f"  (pulado: falta {e.name} -- pip install rawpy numpy)")
        return 0

    try:
        with rawpy.imread(str(caminho)) as raw:
            print(f"  sensor        : {raw.sizes.width}x{raw.sizes.height}")
            print(f"  bits          : {raw.sizes.bits}")
            print(f"  colours       : {raw.sizes.colors}")
            print(f"  black levels  : {raw.black_level_per_channel}")
            print(f"  white level   : {raw.white_level}")
            rgb = raw.postprocess(
                gamma=(1, 1), no_auto_bright=True, output_bps=16,
                use_camera_wb=False, output_color=rawpy.ColorSpace.sRGB,
            )
            print(f"  pós-processado: {rgb.shape} {rgb.dtype}")
            print(f"  faixa         : {rgb.min()} .. {rgb.max()}")
    except Exception as e:  # noqa: BLE001
        print(f"  ERRO ao ler: {type(e).__name__}: {e}")
        return 1

    print()
    print("=== aplicar o pipeline neg35 ===")
    from neg35 import core, pipeline

    res = pipeline.desenvolver(
        core.para_float(rgb),
        pipeline.Parametros(saturacao=1.0, nitidez=0.0),
        manter_etapas=False,
    )
    base = res.base_filme
    print(f"  base detectada: {base.round(4)}")
    print(f"  razão R/B     : {base[0] / max(base[2], 1e-6):.2f}")
    if res.meta.get("aviso"):
        print(f"  AVISO         : {res.meta['aviso']}")
    else:
        print("  exposição     : ok, sem aviso")

    saida = RAIZ / "tools" / "amostras" / "dng_inspecionado.png"
    pipeline.salvar(res.final, saida)
    print(f"  positivo salvo: {saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
