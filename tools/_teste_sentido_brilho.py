"""
A curva de brilho está no sentido certo?

Acima de 1 tem de CLAREAR; abaixo, ESCURECER. A primeira versão estava
invertida -- arrastar para a esquerda clareava.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from neg35 import post  # noqa: E402

print("=== curva pura, em tons variados ===")
x = np.linspace(0.15, 0.90, 6)
img = np.stack([x] * 3, axis=-1)[None, :, :]
antes = float(np.median(post.luminancia(img)))

cab = f"{'força':>7} {'p50 antes':>10} {'p50 depois':>11} {'efeito':>10}"
print(cab)
print("-" * len(cab))
erros = []
for f in (0.4, 0.6, 0.8, 1.0, 1.2, 1.5, 1.8, 2.0):
    out = post.clarear_com_curva(img, f)
    depois = float(np.median(post.luminancia(out)))
    if abs(f - 1.0) < 0.01:
        efeito = "neutro"
        if abs(depois - antes) > 1e-6:
            erros.append(f"força 1,0 mexeu na imagem ({antes:.4f} -> {depois:.4f})")
    elif f > 1.0:
        efeito = "CLAREIA"
        if depois <= antes + 1e-6:
            erros.append(f"força {f} deveria clarear, mas deu {depois:.4f} <= {antes:.4f}")
    else:
        efeito = "ESCURECE"
        if depois >= antes - 1e-6:
            erros.append(f"força {f} deveria escurecer, mas deu {depois:.4f} >= {antes:.4f}")
    print(f"{f:>7.2f} {antes:>10.4f} {depois:>11.4f} {efeito:>10}")

print()
print("=== monotonicidade: mais força = mais claro? ===")
valores = [(f, float(np.median(post.luminancia(post.clarear_com_curva(img, f)))))
           for f in (0.4, 0.6, 0.8, 1.0, 1.2, 1.5, 1.8, 2.0)]
crescente = all(valores[i][1] <= valores[i + 1][1] + 1e-9
                for i in range(len(valores) - 1))
print(f"  {'cresce com a força' if crescente else 'NÃO CRESCE (bug)'}")
if not crescente:
    erros.append("a curva não é monotônica")

print()
print("=== e numa foto de verdade? ===")
from PIL import Image  # noqa: E402
from neg35 import config  # noqa: E402

cfg = config.carregar()
p = Path(cfg.pasta_positivo) / "20261012_133756_positivo.png"
if p.is_file():
    with Image.open(p) as im:
        real = np.asarray(im.convert("RGB")).astype(np.float64) / 255.0
    a = float(np.median(post.luminancia(real)))
    print(f"  original: p50 = {a:.4f}")
    for f in (0.6, 1.0, 1.4):
        out = post.clarear_com_curva(real, f)
        lum = post.luminancia(out)
        print(f"    força {f:<5} -> p50 = {np.median(lum):.4f}   "
              f"branco = {(lum >= 0.99).mean():.1%}")

print()
if erros:
    print("PROBLEMAS:")
    for e in erros:
        print(f"  - {e}")
    raise SystemExit(1)
print("Todas as verificações passaram.")
