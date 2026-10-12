"""
Busca os dois parâmetros da curva de exibição, de forma rápida.

    linear_norm = (positivo - preto) / (1 - preto)
    saida_srgb  = linear_para_srgb(linear_norm ** gamma)

  preto  -> onde começa a parte mais escura (levanta o preto)
  gamma  -> comprime os tons médios (gama > 1 escurece)

Alvo: p05 ~0,10-0,25 e p50 ~0,45-0,58, saturação a mais alta possível.

Otimização: trabalha numa AMOSTRA de pixels, não na imagem inteira. Medir
percentis numa amostra representativa dá o mesmo resultado e é ~100x mais
rápido -- sem isso a busca em 100 combinações levava mais de 10 minutos.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from neg35 import core, pipeline  # noqa: E402

PARAMS = dict(saturacao=1.15, nitidez=0.40, balanco_forca=0.90)
PASSO = 16          # amostra 1 pixel a cada 16 em cada eixo -> ~1/256 dos dados

FONTES = {
    "110646 (ref)": Path(r"E:\Bkp\GoogleDrive\RAW\20261012_110646.dng"),
    "Adobe 143104": RAIZ / ".tmp" / "opt_A_padrao" / "20261012_143104.dng",
}


def amostrar(lin: np.ndarray) -> np.ndarray:
    return lin[::PASSO, ::PASSO].reshape(-1, 3)


def aplicar(amostra: np.ndarray, preto: float, gamma: float) -> np.ndarray:
    x = np.clip(amostra, 0.0, 1.0)
    x = np.clip((x - preto) / max(1.0 - preto, 1e-6), 0.0, 1.0)
    return core.linear_para_srgb(x ** gamma)


def medir(amostra: np.ndarray) -> tuple[float, float, float]:
    """Devolve (p05, p50, saturação) da amostra já em sRGB."""
    lum = 0.2126 * amostra[:, 0] + 0.7152 * amostra[:, 1] + 0.0722 * amostra[:, 2]
    sat = float((amostra.max(axis=-1) - amostra.min(axis=-1)).mean())
    return (float(np.percentile(lum, 5)), float(np.percentile(lum, 50)), sat)


def main() -> int:
    amostras = {}
    for nome, caminho in FONTES.items():
        if not caminho.exists():
            print(f"(não existe) {nome}")
            continue
        lin = pipeline.desenvolver(
            caminho, pipeline.Parametros(**PARAMS), manter_etapas=False
        ).positivo
        amostras[nome] = amostrar(lin)
        print(f"amostra de {nome}: {amostras[nome].shape[0]:,} pixels")

    print()
    print("Alvo: 0.08 <= p05 <= 0.28  e  0.42 <= p50 <= 0.60")
    print()

    grade_preto = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45]
    grade_gamma = [1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.5, 2.8, 3.0, 3.2, 3.5, 4.0, 4.5, 5.0]

    resultados = []
    for preto in grade_preto:
        for gamma in grade_gamma:
            notas = []
            dentro = True
            for nome, am in amostras.items():
                p05, p50, sat = medir(aplicar(am, preto, gamma))
                if not (0.08 <= p05 <= 0.28 and 0.42 <= p50 <= 0.60):
                    dentro = False
                notas.append((nome, p05, p50, sat))
            sat_media = sum(n[3] for n in notas) / max(len(notas), 1)
            erro = sum(abs(n[1] - 0.17) + abs(n[2] - 0.51) for n in notas)
            resultados.append((dentro, erro, sat_media, preto, gamma, notas))

    dentro = [r for r in resultados if r[0]]
    if dentro:
        # Entre as que atendem, a de maior saturação média.
        dentro.sort(key=lambda r: -r[2])
        _, _, sat_media, preto, gamma, notas = dentro[0]
        print("=== configuração que serve para TODAS as fontes ===")
        print(f"  preto = {preto:.2f}   gamma = {gamma:.2f}   "
              f"saturação média = {sat_media:.3f}")
        print()
        for nome, p05, p50, sat in notas:
            print(f"    {nome:<16} p05={p05:.3f}  p50={p50:.3f}  sat={sat:.3f}")
    else:
        print("Nenhuma configuração deixou todas as fontes na faixa alvo.")
        resultados.sort(key=lambda r: r[1])
        print("As 6 mais próximas:")
        for _, erro, sat, preto, gamma, notas in resultados[:6]:
            print(f"  preto={preto:.2f} gamma={gamma:.2f}  erro={erro:.3f}  "
                  f"sat={sat:.3f}")
            for nome, p05, p50, s in notas:
                print(f"      {nome:<16} p05={p05:.3f} p50={p50:.3f} sat={s:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
