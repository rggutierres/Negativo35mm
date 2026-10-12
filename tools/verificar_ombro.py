"""
Verifica se o "ombro" de branco (compresão de destaque por canal) corrigiu o
positivo lavado dos DNG reconvertidos pelo Adobe, sem estragar o que já
funcionava.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from neg35 import core, pipeline, render  # noqa: E402

SAIDA = RAIZ / "tools" / "amostras" / "adobe"

CASOS = [
    ("REFERENCIA boa 110646", Path(r"E:\Bkp\GoogleDrive\RAW\20261012_110646.dng")),
    ("Adobe 143104", RAIZ / ".tmp" / "opt_A_padrao" / "20261012_143104.dng"),
    ("Adobe Pro_141119", RAIZ / ".tmp" / "convertido" / "Pro_20261012_141119.dng"),
    ("ImageMagick 143104 (antes)", Path(r"C:\Temp\teste\20261012_143104.dng")),
]

PARAMS = dict(saturacao=1.15, nitidez=0.40, balanco_forca=0.90)
CAB = (f"{'fonte':<28} {'R/B':>6} {'p05':>6} {'p50':>6} {'p95':>6} "
       f"{'sat':>6}  veredito")


def main() -> int:
    SAIDA.mkdir(parents=True, exist_ok=True)
    print(CAB)
    print("-" * len(CAB))

    for nome, caminho in CASOS:
        if not caminho.exists():
            print(f"{nome:<28} (não existe)")
            continue

        lin = pipeline.carregar(caminho, para_linear=True)
        b = core.detectar_base_do_filme(lin)
        res = pipeline.desenvolver(
            lin, pipeline.Parametros(**PARAMS),
            entrada_linear=True, manter_etapas=False,
        )
        s = core.linear_para_srgb(res.positivo)
        lum = 0.2126 * s[..., 0] + 0.7152 * s[..., 1] + 0.0722 * s[..., 2]
        p05, p50, p95 = (float(np.percentile(lum, q)) for q in (5, 50, 95))
        sat = float((s.max(axis=-1) - s.min(axis=-1)).mean())
        if p05 > 0.75:
            v = "LAVADO"
        elif p05 > 0.62:
            v = "claro demais"
        elif p05 < 0.30:
            v = "escuro demais"
        else:
            v = "BOM"

        print(f"{nome:<28} {b[0] / max(b[2], 1e-9):>6.2f} {p05:>6.3f} {p50:>6.3f} "
              f"{p95:>6.3f} {sat:>6.3f}  {v}")

        apelido = nome.split()[0].replace("/", "_")
        pipeline.salvar(
            render.ampliar(core.linear_para_srgb(res.positivo), largura=800),
            SAIDA / f"CORRIGIDO_{apelido}.png", linear=False,
        )

    print()
    print("Antes da correção, os arquivos do Adobe davam p05 = 0,807 (LAVADO).")
    print(f"previews em {SAIDA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
