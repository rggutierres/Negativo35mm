"""
Reconverte os positivos que estão ROTACIONADOS.

O QUE ACONTECEU, medido:

    DNG                     4000 x 1868  (largura x altura, flip=6)
    desenvolver() hoje      4000 x 1868  correto
    positivo no disco       1868 x 4000  TRANSPOSTO  <- gerado por versão antiga

O código atual está correto; os arquivos existentes foram gravados por uma
versão que transpunha o array ao salvar. Como o positivo é a base de tudo
(comparação, restauração, recorte), o erro contaminou o resto -- inclusive
explica a dificuldade com o recorte: a proporção do quadro ficava invertida.

Este script:
  --conferir   só lista quais estão com a orientação trocada (não grava nada)
  (padrão)     reconverte os trocados, gravando por cima

Não apaga nada antes de gravar: `pipeline.salvar` grava em `.tmp` e renomeia.
E os positivos são regeneráveis a partir dos negativos, então não há perda.

CUIDADO QUE ME CUSTOU UMA RODADA: `pipeline.salvar` tem de receber a MESMA
`curva` que `servidor.converter` usa (`servidor._curva_fn(cfg)`), não `curva=None`.

Com `curva=None` a luz linear é codificada em sRGB puro, e o positivo sai
LAVADO: medido, mediana de luminância 0,89 em vez de 0,52. Foi exatamente o que
o usuário viu como "preview mais claro que o arquivo" -- e fui eu que causei,
reconvertendo sem a curva.

A curva de exibição existe porque negativo de filme tem densidade baixa: sem ela
a imagem fica clara demais. Ver `neg35/curva.py`.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from PIL import Image  # noqa: E402

from neg35 import config, pipeline, servidor  # noqa: E402

cfg = config.carregar()
origem_dir = Path(cfg.pasta_origem)
positivo_dir = Path(cfg.pasta_positivo)

CONFERIR = "--conferir" in sys.argv
# Força reconverter TODOS, mesmo os que já estão na orientação certa. Serve para
# refazer com outra curva de exibição, ou depois de corrigir o pipeline.
TODOS = "--todos" in sys.argv


def arquivo_de_origem(nome: str) -> Path | None:
    cands = sorted(origem_dir.glob(f"{nome}.*"))
    raws = [c for c in cands if c.suffix.lower() in servidor.EXT_RAW]
    if raws:
        return raws[0]
    return cands[0] if cands else None


def orientacao_esperada(origem: Path) -> tuple[int, int] | None:
    """
    Largura x altura que o positivo DEVE ter.

    `raw.sizes.width/height` já são as dimensões DEPOIS de aplicar o `flip` do
    arquivo -- é o mesmo que `postprocess()` devolve. Conferido: para esta foto
    dá 4000x1868, igual ao array que `desenvolver` retorna (1868, 4000, 3).

    Eu havia assumido que `flip` em (5, 6) exigia trocar os eixos aqui. Não
    exige: `sizes` já vem no espaço de saída. Com a troca, o "esperado" ficava
    igual ao arquivo trocado e nada era detectado.
    """
    try:
        import rawpy

        with rawpy.imread(str(origem)) as raw:
            s = raw.sizes
            return s.width, s.height
    except Exception:  # noqa: BLE001
        return None


print(f"origem   : {origem_dir}")
print(f"positivos: {positivo_dir}")
print(f"modo     : {'CONFERIR (não grava)' if CONFERIR else 'RECONVERTER'}")
print()

positivos = sorted(positivo_dir.glob("*_positivo.png"))
print(f"{len(positivos)} positivo(s) encontrados")
print()

cab = f"{'foto':<22} {'no disco':>12} {'esperado':>12}  situação"
print(cab)
print("-" * len(cab))

trocados: list[tuple[str, Path]] = []
for f in positivos:
    nome = f.name.replace("_positivo.png", "")
    with Image.open(f) as im:
        lw, lh = im.size

    origem = arquivo_de_origem(nome)
    esperado = orientacao_esperada(origem) if origem else None

    if esperado is None:
        # Sem como perguntar ao DNG: o negativo é sempre mais largo que alto
        # (4000x1868), então um positivo retrato está trocado.
        situacao = ("TROCADO" if lh > lw else "ok (por heurística)")
        if lh > lw:
            trocados.append((nome, f))
        print(f"{nome:<22} {lw:>5}x{lh:<6} {'—':>12}  {situacao}")
        continue

    ew, eh = esperado
    if (lw, lh) == (ew, eh):
        situacao = "ok"
        if TODOS:
            situacao = "ok (refazendo por --todos)"
            trocados.append((nome, f))
    elif (lw, lh) == (eh, ew):
        situacao = "TROCADO"
        trocados.append((nome, f))
    else:
        situacao = f"diferente (esperado {ew}x{eh})"
        trocados.append((nome, f))
    print(f"{nome:<22} {lw:>5}x{lh:<6} {ew:>5}x{eh:<6}  {situacao}")

print()
print(f"para corrigir: {len(trocados)} de {len(positivos)}")

if CONFERIR or not trocados:
    if not CONFERIR and not trocados:
        print("nada a fazer.")
    raise SystemExit(0)

print()
print("=== reconvertendo ===")
t0 = time.time()
ok = falhas = 0
for i, (nome, f) in enumerate(trocados, 1):
    origem = arquivo_de_origem(nome)
    print(f"  [{i}/{len(trocados)}] {nome} ... ", end="", flush=True)
    if origem is None:
        print("origem não encontrada")
        falhas += 1
        continue
    try:
        res = pipeline.desenvolver(
            origem,
            pipeline.Parametros(
                filme=cfg.filme, saturacao=cfg.saturacao,
                nitidez=cfg.nitidez, balanco_forca=cfg.balanco,
            ),
            manter_etapas=False,
        )
        pipeline.salvar(res.positivo, f, linear=True,
                        curva=servidor._curva_fn(cfg))
        with Image.open(f) as im:
            print(f"ok -> {im.size[0]}x{im.size[1]}")
        ok += 1
    except Exception as e:  # noqa: BLE001
        print(f"FALHOU: {type(e).__name__}: {str(e)[:120]}")
        falhas += 1

print()
print(f"reconvertidos: {ok}   falhas: {falhas}   "
      f"({time.time() - t0:.0f} s)")
