"""
Compara os dois métodos de balanço de branco.

gray-world: assume que a média da cena é cinza. Erra em cena dominada por uma
            cor -- folhagem deixa a imagem esverdeada.
base:       usa o filme virgem como preto neutro. Âncora absoluta.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from neg35 import core, curva, pipeline  # noqa: E402

FONTES = {
    "Adobe 143104": RAIZ / ".tmp" / "convertido" / "20261012_143104.dng",
    "REF 110646": Path(r"E:\Bkp\GoogleDrive\RAW\20261012_110646.dng"),
}
PARAMS = dict(saturacao=1.15, nitidez=0.40, balanco_forca=0.90)

CAB = (f"{'arquivo / metodo':<32} {'p05':>6} {'p50':>6} {'G/R':>6} {'G/B':>6}  cast")


def main() -> int:
    print(CAB)
    print("-" * len(CAB))
    for nome, arq in FONTES.items():
        if not arq.exists():
            print(f"{nome:<32} (não existe)")
            continue
        lin = pipeline.carregar(arq, para_linear=True)
        for metodo in ("gray-world", "base"):
            res = pipeline.desenvolver(
                lin,
                pipeline.Parametros(**PARAMS, balanco_metodo=metodo),
                entrada_linear=True, manter_etapas=False,
            )
            s = curva.aplicar(res.positivo, alvo=0.50)
            lum = 0.2126 * s[..., 0] + 0.7152 * s[..., 1] + 0.0722 * s[..., 2]
            mm = (lum > np.percentile(lum, 30)) & (lum < np.percentile(lum, 70))
            med = np.median(s[mm], axis=0)
            gr = float(med[1] / max(med[0], 1e-9))
            gb = float(med[1] / max(med[2], 1e-9))
            if abs(gr - 1) < 0.03 and abs(gb - 1) < 0.03:
                cast = "neutro"
            elif gr > 1.03 and gb > 1.03:
                cast = "VERDE"
            elif gr < 0.97 and gb < 0.97:
                cast = "magenta"
            else:
                cast = "outro"
            rotulo = f"{nome} / {metodo}"
            print(f"{rotulo:<32} {np.percentile(lum,5):>6.3f} "
                  f"{np.percentile(lum,50):>6.3f} {gr:>6.2f} {gb:>6.2f}  {cast}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
