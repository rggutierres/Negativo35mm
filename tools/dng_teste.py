"""
Cria um DNG de teste que LibRaw E ImageMagick aceitam.

Por que isso é necessário: ambos decidem o formato pelo CONTEÚDO, não pela
extensão (salvar um PNG com nome `.dng` não engana nenhum dos dois), e a
maioria dos arranjos de tags é recusada.

Testado (ver tools/_testar_dng_minimo.py) -- dos cinco arranjos tentados, só
UM foi aceito pelos dois decodificadores:

    PhotometricInterpretation = 34892 (LinearRaw), 3 amostras, 16 bits

O arranjo mais "óbvio" (PhotometricInterpretation = 2, RGB) é RECUSADO.
Também recusados: DNGVersion 1.1/1.6, e CFA de 1 amostra.

Isto não é um DNG de sensor Bayer -- é um TIFF RGB linear, que é o mesmo tipo
de estrutura de um DNG "já demosaico". Serve para exercitar o caminho de
leitura por arquivo.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

# Tags TIFF usadas.
T_LARGURA = 0x0100
T_ALTURA = 0x0101
T_BITS = 0x0102
T_COMPRESSAO = 0x0103
T_PHOTOMETRIC = 0x0106
T_STRIP_OFFSETS = 0x0111
T_AMOSTRAS = 0x0115
T_STRIP_BYTES = 0x0117
T_PLANAR = 0x011C
T_DNG_VERSION = 0xC612

# 34892 = LinearRaw. É o ÚNICO arranjo que LibRaw e ImageMagick aceitaram
# nos testes. Ver o docstring do módulo.
PHOTOMETRIC_LINEAR_RAW = 34892


def escrever_dng(caminho: Path, rgb: np.ndarray) -> Path:
    """
    Grava um TIFF LinearRaw de 16 bits sem compressão com DNGVersion.

    rgb: array (altura, largura, 3) em [0,1].
    """
    a = np.clip(np.asarray(rgb, dtype=np.float64), 0.0, 1.0)
    altura, largura = a.shape[:2]
    dados = (a * 65535.0 + 0.5).astype("<u2")          # little-endian (II)

    # Layout: [header 8][dados][IFD][BitsPerSample]
    # Os dados vêm antes do IFD para o StripOffsets ser calculável sem
    # depender do tamanho final do IFD.
    offset_dados = 8
    offset_ifd = offset_dados + dados.nbytes

    entradas: list[tuple[int, int, int, int]] = [
        (T_LARGURA, 4, 1, largura),                    # LONG
        (T_ALTURA, 4, 1, altura),
        (T_COMPRESSAO, 3, 1, 1),                       # SHORT, sem compressão
        (T_PHOTOMETRIC, 3, 1, PHOTOMETRIC_LINEAR_RAW),  # SHORT
        (T_STRIP_OFFSETS, 4, 1, offset_dados),         # LONG
        (T_AMOSTRAS, 3, 1, 3),                         # SHORT
        (T_STRIP_BYTES, 4, 1, dados.nbytes),           # LONG
        (T_PLANAR, 3, 1, 1),                           # SHORT, chunky
    ]

    # BitsPerSample: 3 SHORTs = 6 bytes, não cabe inline -> vai para o fim.
    # Bits e DNGVersion entram na lista antes de calcular o offset final.
    versao = 1 | (4 << 8) | (0 << 16) | (0 << 24)
    entradas.append((T_BITS, 3, 3, -1))                # -1 = resolver depois
    entradas.append((T_DNG_VERSION, 1, 4, versao))
    entradas.sort(key=lambda e: e[0])

    offset_bits = offset_ifd + 2 + len(entradas) * 12 + 4
    entradas = [
        (t, ty, c, offset_bits if v == -1 else v) for (t, ty, c, v) in entradas
    ]

    buf = bytearray()
    buf += b"II" + struct.pack("<H", 42) + struct.pack("<I", offset_ifd)
    buf += dados.tobytes()
    assert len(buf) == offset_ifd, f"IFD deveria começar em {offset_ifd}"

    buf += struct.pack("<H", len(entradas))
    for tag, tipo, cont, valor in entradas:
        buf += struct.pack("<HHI", tag, tipo, cont)
        if tipo == 3 and cont == 1:
            buf += struct.pack("<HH", valor, 0)         # SHORT inline + padding
        elif tipo == 1:
            buf += struct.pack("<I", valor)             # BYTE x4 inline
        else:
            buf += struct.pack("<I", valor)             # ponteiro ou LONG
    buf += struct.pack("<I", 0)                         # sem próximo IFD
    buf += struct.pack("<HHH", 16, 16, 16)              # BitsPerSample

    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(bytes(buf))
    return caminho


if __name__ == "__main__":
    import sys

    destino = Path(sys.argv[1] if len(sys.argv) > 1 else "tools/_dng_teste.dng")
    arr = np.zeros((32, 48, 3))
    arr[..., 0] = np.linspace(0, 1, 48)[None, :]
    escrever_dng(destino, arr)
    print(f"escrito: {destino} ({destino.stat().st_size:,} bytes)")
