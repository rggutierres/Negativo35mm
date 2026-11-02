"""
Testa a rotação do arquivo restaurado — numa CÓPIA, nunca no original.

POR QUE FOI REESCRITO: a versão anterior usava `cfg.pasta_restaurada` direto, ou
seja, girava e sobrescrevia o arquivo REAL do usuário. Um teste nunca deve
alterar o dado que o usuário produziu — a restauração custou dinheiro, e se o
teste falhasse no meio a foto ficaria girada.

Agora copia para uma pasta temporária e trabalha só nela. No fim, confere que o
arquivo real continua intacto.
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
origem_dir = Path(cfg.pasta_restaurada)
candidatos = sorted(origem_dir.glob("*_restaurado.png"))
if not candidatos:
    print("sem restaurada para testar")
    raise SystemExit(0)

origem = candidatos[0]
nome = origem.name.replace("_restaurado.png", "")

FALHAS: list[str] = []


def checar(cond: bool, msg: str) -> None:
    print(f"  {'ok  ' if cond else 'FALHOU'} {msg}")
    if not cond:
        FALHAS.append(msg)


tmp = Path(tempfile.mkdtemp(prefix="neg35_rot_"))
cfg.pasta_restaurada = str(tmp)
alvo = tmp / origem.name
shutil.copy2(origem, alvo)

with Image.open(alvo) as im:
    antes = im.size
print(f"original copiado: {origem.name}  {antes[0]}x{antes[1]}")
print()

r = servidor.rotacionar_restaurado(cfg, nome, 1)
checar(r["giros"] == 1, f"giros reportados ({r['giros']})")
checar(tuple(r["tamanho"]) == (antes[1], antes[0]),
       f"tamanho trocou os eixos ({r['tamanho'][0]}x{r['tamanho'][1]})")
checar(Path(r["backup"]).is_file(), "cópia de segurança criada")

with Image.open(alvo) as im:
    depois = im.size
checar(depois == (antes[1], antes[0]),
       f"arquivo girado no disco ({depois[0]}x{depois[1]})")

servidor.rotacionar_restaurado(cfg, nome, 3)      # +3 = 360 no total
with Image.open(alvo) as im:
    voltou = im.size
checar(voltou == antes,
       f"3 giros depois voltam ao original ({voltou[0]}x{voltou[1]})")

print()
print("=== a listagem da tela ignora a pasta de backup? ===")
vistos = sorted(p.name for p in tmp.glob("*_restaurado.png"))
checar(not any("_antes_da_rotacao" in v for v in vistos),
       f"backups fora da listagem ({len(vistos)} arquivo(s) visto(s))")

print()
print("=== casos inválidos são recusados? ===")
try:
    servidor.rotacionar_restaurado(cfg, nome, 0)
    checar(False, "giros=0 recusado")
except ValueError:
    checar(True, "giros=0 recusado")

try:
    servidor.rotacionar_restaurado(cfg, "nao_existe", 1)
    checar(False, "foto inexistente recusada")
except FileNotFoundError:
    checar(True, "foto inexistente recusada")

with Image.open(origem) as im:
    intocado = im.size
checar(intocado == antes,
       f"o arquivo real do usuário não foi tocado ({intocado[0]}x{intocado[1]})")

shutil.rmtree(tmp, ignore_errors=True)
print()
if FALHAS:
    print(f"{len(FALHAS)} verificação(ões) falharam.")
    raise SystemExit(1)
print("Todas as verificações passaram.")
