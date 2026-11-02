"""
O filtro de olhos vermelhos funciona? E ele NÃO estraga vermelho de objeto?

Dois testes:

1. SINTÉTICO, com resposta conhecida: uma "pupila vermelha" num rosto bege, ao
   lado de uma blusa vermelha grande. O filtro tem de acertar a pupila e
   PRESERVAR a blusa. Isso testa o filtro de forma, que é a parte arriscada.

2. NAS FOTOS REAIS: quantas regiões ele acha. Não sei quais têm flash no olho,
   então o teste apenas relata -- não afirma.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from PIL import Image, ImageDraw  # noqa: E402

from neg35 import config, olhos  # noqa: E402

FALHAS: list[str] = []


def checar(cond: bool, msg: str) -> None:
    print(f"  {'ok  ' if cond else 'FALHOU'} {msg}")
    if not cond:
        FALHAS.append(msg)


print("=== 1) teste sintético: pupila vermelha + blusa vermelha ===")
H, W = 300, 400
img = np.zeros((H, W, 3))
img[:] = (0.86, 0.72, 0.60)                      # pele

# duas pupilas vermelhas (pequenas, redondas)
for cx in (150, 250):
    yy, xx = np.mgrid[0:H, 0:W]
    dentro = (yy - 120) ** 2 + (xx - cx) ** 2 <= 9 ** 2
    img[dentro] = (0.75, 0.12, 0.10)

# blusa vermelha GRANDE (não é olho)
img[200:290, 60:340] = (0.72, 0.14, 0.12)

mascara, info = olhos.detectar(img, dilatar=1)
print(f"  regiões encontradas: {info['regioes_encontradas']}")
print(f"  regiões aceitas    : {info['regioes_aceitas']}")
print(f"  pixels na máscara  : {info.get('pixels', 0)}")

# a pupila está marcada?
pupila_marcada = bool(mascara[120, 150]) and bool(mascara[120, 250])
checar(pupila_marcada, "as duas pupilas foram marcadas")
# a blusa NÃO foi marcada (fora dos círculos)
blusa_limpa = not bool(mascara[210:280, 100:300].any())
checar(blusa_limpa, "a blusa vermelha grande foi preservada")
checar(info["regioes_aceitas"] == 2,
       f"exatamente 2 regiões aceitas (achei {info['regioes_aceitas']})")

print()
print("=== 1b) depois de corrigir ===")
saida, info2 = olhos.corrigir(img, forca=1.0)
r_pupila = saida[120, 150]
r_blusa = saida[240, 200]
print(f"  pupila: {r_pupila.round(3)}")
print(f"  blusa : {r_blusa.round(3)}")
checar(r_pupila[0] < 0.45, f"o vermelho da pupila caiu ({r_pupila[0]:.2f})")
checar(abs(r_pupila[0] - r_pupila[1]) < 0.25,
       "a pupila ficou neutra (R perto de G)")
checar(abs(r_blusa[0] - 0.72) < 0.02,
       f"a blusa ficou intacta (R={r_blusa[0]:.2f})")

print()
print("=== 2) nas fotos reais ===")
cfg = config.carregar()
pasta = Path(cfg.pasta_restaurada)
achadas = 0
for f in sorted(pasta.glob("*_restaurado.png")):
    with Image.open(f) as im:
        a = np.asarray(im.convert("RGB")).astype(np.float64) / 255.0
    _, info = olhos.detectar(a, dilatar=1)
    n = info["regioes_aceitas"]
    if n:
        achadas += 1
    print(f"  {f.name:<44} regiões={n:<3} pixels={info.get('pixels', 0)}")
print()
print(f"  fotos com alguma região detectada: {achadas}")

print()
if FALHAS:
    print(f"{len(FALHAS)} verificação(ões) falharam.")
    raise SystemExit(1)
print("Todas as verificações passaram.")
