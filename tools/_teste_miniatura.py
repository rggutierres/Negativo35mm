"""
A miniatura é fiel ao arquivo do positivo?

O usuário relatou "preview mais claro que o arquivo". Este teste compara a
mediana de luminância da miniatura com a do arquivo, e FALHA se houver diferença
perceptível. Foi o que teria pegado o positivo salvo com a curva errada.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from PIL import Image  # noqa: E402

from neg35 import config, post, servidor  # noqa: E402

cfg = config.carregar()
pasta = Path(cfg.pasta_positivo)

FALHAS: list[str] = []


def checar(cond: bool, msg: str) -> None:
    print(f"  {'ok  ' if cond else 'FALHOU'} {msg}")
    if not cond:
        FALHAS.append(msg)


print("=== miniatura vs arquivo ===")
print()
cab = f"{'foto':<22} {'arquivo':>9} {'miniatura':>10} {'diferença':>10}"
print(cab)
print("-" * len(cab))

diffs = []
for f in sorted(pasta.glob("*_positivo.png")):
    nome = f.name.replace("_positivo.png", "")
    with Image.open(f) as im:
        a = np.asarray(im.convert("RGB")).astype(np.float64) / 255.0
    med_a = float(np.median(post.luminancia(a)))

    d = servidor.thumb(f, 340)
    with Image.open(io.BytesIO(d)) as im:
        t = np.asarray(im.convert("RGB")).astype(np.float64) / 255.0
    med_t = float(np.median(post.luminancia(t)))

    dif = abs(med_t - med_a)
    diffs.append((nome, med_a, med_t, dif))
    marca = "" if dif < 0.03 else "  <-- DIFERENTE"
    print(f"{nome:<22} {med_a:>9.4f} {med_t:>10.4f} {dif:>10.4f}{marca}")

print()
if diffs:
    pior = max(diffs, key=lambda x: x[3])
    maior = pior[3]
    print(f"  maior diferença: {maior:.4f} ({pior[0]})")
    checar(maior < 0.03,
           f"nenhuma miniatura difere mais de 0,03 do arquivo (maior {maior:.4f})")

    # Uma mediana alta numa foto pode ser cena clara (duas destas são: 0,84).
    # O erro de curva, ao contrário, é GLOBAL: sem a curva de exibição TODAS as
    # fotos ficam lavadas, com mediana ~0,85. Então olhamos a mediana do
    # conjunto, não foto a foto.
    med_conjunto = float(np.median([m for _, m, _, _ in diffs]))
    print(f"  mediana do conjunto: {med_conjunto:.4f}")
    checar(0.35 < med_conjunto < 0.72,
           f"o conjunto não está lavado nem escuro ({med_conjunto:.3f})")
    if not (0.35 < med_conjunto < 0.72):
        print("  Sem a curva de exibição, todas ficariam em ~0,85.")
        print("  Confira `servidor._curva_fn(cfg)` ao salvar o positivo.")

print()
if FALHAS:
    print(f"{len(FALHAS)} verificação(ões) falharam.")
    print("Se as miniaturas diferem do arquivo, veja se o positivo foi salvo com")
    print("curva=None em vez de servidor._curva_fn(cfg) -- foi o que aconteceu.")
    raise SystemExit(1)
print("Todas as verificações passaram.")
