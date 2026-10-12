"""
Comparação final, com métrica ÚNICA para todos.

Correção de método: antes eu media o positivo local com `linear_para_srgb`
(codifica gama) e o positivo da IA medindo o dado cru. Isso comparava coisas
diferentes e me levou a conclusões erradas em sequência.

Aqui tudo é medido do ARQUIVO salvo, que é o que o olho vê.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from neg35 import core, pipeline, render  # noqa: E402

from PIL import Image  # noqa: E402

SAIDA = RAIZ / "tools" / "amostras" / "final"
PARAMS = dict(saturacao=1.15, nitidez=0.40, balanco_forca=0.90)


def medir_srgb(arr_u8: np.ndarray) -> dict:
    s = arr_u8.astype(np.float64) / 255.0
    lum = 0.2126 * s[..., 0] + 0.7152 * s[..., 1] + 0.0722 * s[..., 2]
    sat = float((s.max(axis=-1) - s.min(axis=-1)).mean())
    return {
        "mean": float(lum.mean()),
        "p05": float(np.percentile(lum, 5)),
        "p50": float(np.percentile(lum, 50)),
        "p95": float(np.percentile(lum, 95)),
        "sat": sat,
    }


def main() -> int:
    SAIDA.mkdir(parents=True, exist_ok=True)

    fontes = {
        "Adobe 143104": RAIZ / ".tmp" / "opt_A_padrao" / "20261012_143104.dng",
        "REFERENCIA 110646": Path(r"E:\Bkp\GoogleDrive\RAW\20261012_110646.dng"),
    }

    linhas = []
    for nome, caminho in fontes.items():
        if not caminho.exists():
            continue
        # Positivo local, pelo pipeline, salvo em resolução cheia.
        res = pipeline.desenvolver(
            caminho, pipeline.Parametros(**PARAMS), manter_etapas=False
        )
        destino = SAIDA / f"{nome.split()[0]}_local.png"
        pipeline.salvar(res.positivo, destino, linear=True)
        arr = np.asarray(Image.open(destino).convert("RGB"))
        linhas.append((f"{nome} (local)", medir_srgb(arr)))

    # Positivos restaurados pela IA (já salvos em execuções anteriores).
    ia = {
        "Adobe+IA (ia_final)": RAIZ / "tools" / "amostras" / "adobe" / "ia_final" / "02_restaurado_ia.png",
        "JPG+IA (do_jpg)": RAIZ / "tools" / "amostras" / "jpg_vs_raw" / "do_jpg" / "02_restaurado_ia.png",
        "DNG+IA (do_dng)": RAIZ / "tools" / "amostras" / "jpg_vs_raw" / "do_dng" / "02_restaurado_ia.png",
    }
    for nome, caminho in ia.items():
        if caminho.exists():
            arr = np.asarray(Image.open(caminho).convert("RGB"))
            linhas.append((nome, medir_srgb(arr)))

    cab = (f"{'versão':<30} {'mean':>6} {'p05':>6} {'p50':>6} {'p95':>6} "
           f"{'sat':>6}  leitura")
    print(cab)
    print("-" * len(cab))
    for nome, m in linhas:
        if m["sat"] < 0.06:
            leitura = "dessaturado"
        elif m["p05"] > 0.60:
            leitura = "sem preto (lavado)"
        elif m["p50"] < 0.25:
            leitura = "escuro demais"
        else:
            leitura = "faixa razoável"
        print(f"{nome:<30} {m['mean']:>6.3f} {m['p05']:>6.3f} {m['p50']:>6.3f} "
              f"{m['p95']:>6.3f} {m['sat']:>6.3f}  {leitura}")

    print()
    print("Tudo medido do ARQUIVO, mesma métrica para todos.")
    print(f"arquivos em {SAIDA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
