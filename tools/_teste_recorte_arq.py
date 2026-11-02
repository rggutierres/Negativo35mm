"""
Testa o recorte do arquivo restaurado — numa CÓPIA, nunca no original.

POR QUE FOI REESCRITO: a versão anterior recortava e sobrescrevia o arquivo REAL
do usuário, e depois tentava "restaurar do backup mais recente". Esse palpite é
frágil: se houver mais de um backup (de rotação e de recorte), o "mais recente"
pode ser justamente o errado — e o teste deixaria a foto do usuário num estado
que ele não escolheu.

Agora copia para uma pasta temporária e trabalha só nela.
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
NOME = origem.name.replace("_restaurado.png", "")

FALHAS: list[str] = []


def checar(cond: bool, msg: str) -> None:
    print(f"  {'ok  ' if cond else 'FALHOU'} {msg}")
    if not cond:
        FALHAS.append(msg)


tmp = Path(tempfile.mkdtemp(prefix="neg35_crop_"))
cfg.pasta_restaurada = str(tmp)
alvo = tmp / origem.name
shutil.copy2(origem, alvo)

with Image.open(alvo) as im:
    antes = im.size
print(f"original copiado: {origem.name}  {antes[0]}x{antes[1]}")
print()

r = servidor.recortar_restaurado(cfg, NOME, 0.1, 0.2, 0.9, 0.8)
esperado = (int(round(antes[0] * 0.8)), int(round(antes[1] * 0.6)))
checar(abs(r["tamanho"][0] - esperado[0]) <= 2
       and abs(r["tamanho"][1] - esperado[1]) <= 2,
       f"tamanho ~80%x60% ({r['tamanho'][0]}x{r['tamanho'][1]}, "
       f"esperado {esperado[0]}x{esperado[1]})")
checar(Path(r["backup"]).is_file(), "cópia de segurança criada")

with Image.open(alvo) as im:
    no_disco = im.size
checar(tuple(no_disco) == tuple(r["tamanho"]),
       f"arquivo recortado no disco ({no_disco[0]}x{no_disco[1]})")

print()
print("=== a listagem da tela ignora a pasta de backup? ===")
vistos = sorted(p.name for p in tmp.glob("*_restaurado.png"))
checar(not any("_antes_da_rotacao" in v for v in vistos),
       f"backups fora da listagem ({len(vistos)} arquivo(s) visto(s))")

print()
print("=== recortes inválidos são recusados? ===")
CASOS = [
    ("fora de 0..1", (1.2, 0.1, 0.8, 0.9), ValueError),
    ("invertido", (0.8, 0.1, 0.2, 0.9), ValueError),
    ("menor que 5%", (0.50, 0.1, 0.52, 0.9), ValueError),
    ("imagem inteira", (0.0, 0.0, 1.0, 1.0), ValueError),
    ("foto inexistente", None, FileNotFoundError),
]
for rotulo, args, erro in CASOS:
    nome_teste = NOME if args is not None else "nao_existe"
    try:
        servidor.recortar_restaurado(cfg, nome_teste, *(args or (0.1, 0.1, 0.9, 0.9)))
        checar(False, f"{rotulo} recusado")
    except erro:
        checar(True, f"{rotulo} recusado")

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
