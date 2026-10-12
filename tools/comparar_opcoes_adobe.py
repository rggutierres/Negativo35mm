"""
Compara as opções de saída do Adobe DNG Converter contra a referência boa.

O Adobe conserta a decodificação (comprovado) mas aplica curva que clareia as
sombras. Aqui testamos cada modo de conversão para achar o que preserva melhor
o dado do negativo.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from neg35 import core, pipeline, render  # noqa: E402

BASE = RAIZ / ".tmp"
REF = Path(r"E:\Bkp\GoogleDrive\RAW\20261012_110646.dng")
SAIDA = RAIZ / "tools" / "amostras" / "adobe"

PARAMS = dict(saturacao=1.15, nitidez=0.40, balanco_forca=0.90)
CAB = (f"{'fonte':<24} {'R/B':>6} {'base':>26} {'p05':>6} {'p50':>6} "
       f"{'p95':>6} {'sat':>6}  veredito")


def avaliar(lin: np.ndarray) -> dict:
    b = core.detectar_base_do_filme(lin)
    res = pipeline.desenvolver(lin, pipeline.Parametros(**PARAMS),
                              entrada_linear=True, manter_etapas=False)
    s = core.linear_para_srgb(res.positivo)
    lum = 0.2126 * s[..., 0] + 0.7152 * s[..., 1] + 0.0722 * s[..., 2]
    p05, p50, p95 = (float(np.percentile(lum, q)) for q in (5, 50, 95))
    if p05 > 0.75:
        v = "LAVADO"
    elif p05 > 0.62:
        v = "claro demais"
    elif p05 < 0.30:
        v = "escuro demais"
    else:
        v = "bom"
    return {
        "rb": float(b[0] / max(b[2], 1e-9)),
        "base": b,
        "p05": p05, "p50": p50, "p95": p95,
        "sat": float((s.max(axis=-1) - s.min(axis=-1)).mean()),
        "veredito": v,
        "positivo": res.positivo,
    }


def linha(rotulo: str, m: dict) -> str:
    return (f"{rotulo:<24} {m['rb']:>6.2f} {str(m['base'].round(3)):>26} "
            f"{m['p05']:>6.3f} {m['p50']:>6.3f} {m['p95']:>6.3f} "
            f"{m['sat']:>6.3f}  {m['veredito']}")


def main() -> int:
    SAIDA.mkdir(parents=True, exist_ok=True)
    print(CAB)
    print("-" * len(CAB))

    if REF.exists():
        lin = pipeline.carregar(REF, para_linear=True)
        m = avaliar(lin)
        print(linha("REFERENCIA 110646", m))

    for d in sorted(BASE.glob("opt_*")):
        arquivos = list(d.glob("*.dng"))
        if not arquivos:
            continue
        f = arquivos[0]
        try:
            lin = pipeline.carregar(f, para_linear=True)
        except Exception as e:  # noqa: BLE001
            print(f"{d.name:<24} FALHOU: {type(e).__name__}")
            continue
        m = avaliar(lin)
        print(linha(d.name, m))
        pipeline.salvar(
            render.ampliar(core.linear_para_srgb(m["positivo"]), largura=900),
            SAIDA / f"{d.name}_preview.png", linear=False,
        )

    print()
    print("Referência boa: p05 ~0,63. Valores acima de 0,75 indicam positivo lavado.")
    print(f"previews em {SAIDA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
