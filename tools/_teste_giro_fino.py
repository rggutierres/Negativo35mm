"""
Testa a rotação por ângulo qualquer (giro fino), numa CÓPIA.

O giro fino serve para endireitar negativo fotografado torto: 1 ou 2 graus
resolvem o que o giro de 90 não resolve.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from PIL import Image  # noqa: E402

from neg35 import config, servidor  # noqa: E402

cfg = config.carregar()
cands = sorted(Path(cfg.pasta_restaurada).glob("*_restaurado.png"))
if not cands:
    print("sem restaurada para testar")
    raise SystemExit(0)

origem = cands[0]
nome = origem.name.replace("_restaurado.png", "")

FALHAS: list[str] = []


def checar(cond: bool, msg: str) -> None:
    print(f"  {'ok  ' if cond else 'FALHOU'} {msg}")
    if not cond:
        FALHAS.append(msg)


tmp = Path(tempfile.mkdtemp(prefix="neg35_giro_"))
cfg.pasta_restaurada = str(tmp)
alvo = tmp / origem.name
shutil.copy2(origem, alvo)

with Image.open(alvo) as im:
    w0, h0 = im.size
print(f"cópia: {w0}x{h0}")
print()

print("=== giro de 90 mantém as dimensões trocadas ===")
r = servidor.girar_restaurado(cfg, nome, 90)
checar(tuple(r["tamanho"]) == (h0, w0),
       f"90° -> {r['tamanho'][0]}x{r['tamanho'][1]} (esperado {h0}x{w0})")

print()
print("=== giro fino de 1 grau ===")
with Image.open(alvo) as im:
    antes = im.size
r = servidor.girar_restaurado(cfg, nome, 1.5)
with Image.open(alvo) as im:
    depois = im.size
checar(depois[0] > antes[0] and depois[1] > antes[1],
       f"a imagem cresce para caber a rotação "
       f"({antes[0]}x{antes[1]} -> {depois[0]}x{depois[1]})")
checar(r["angulo"] == 1.5, f"ângulo reportado ({r['angulo']})")

print()
print("=== casos inválidos ===")
for ang, rotulo in ((0, "zero"), (400, "acima de 360")):
    try:
        servidor.girar_restaurado(cfg, nome, ang)
        checar(False, f"{rotulo} recusado")
    except ValueError:
        checar(True, f"{rotulo} recusado")

try:
    servidor.girar_restaurado(cfg, "nao_existe", 1)
    checar(False, "foto inexistente recusada")
except FileNotFoundError:
    checar(True, "foto inexistente recusada")

print()
print("=== o atalho de 90 graus continua funcionando ===")
r = servidor.rotacionar_restaurado(cfg, nome, 1)
checar(r.get("giros") == 1, f"rotacionar_restaurado reporta giros ({r.get('giros')})")
checar("angulo" in r, "e também informa o ângulo")

with Image.open(origem) as im:
    checar(im.size == (w0, h0), f"o arquivo real não foi tocado "
                                f"({im.size[0]}x{im.size[1]})")

shutil.rmtree(tmp, ignore_errors=True)
print()
if FALHAS:
    print(f"{len(FALHAS)} verificação(ões) falharam.")
    raise SystemExit(1)
print("Todas as verificações passaram.")
