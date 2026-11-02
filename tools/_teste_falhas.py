"""A aba de falhas acha as falhas reais?"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from neg35 import config, servidor  # noqa: E402

cfg = config.carregar()
print(f"registro de falhas : {servidor.caminho_falhas(cfg)}")
print(f"existe             : {servidor.caminho_falhas(cfg).is_file()}")
print()

d = servidor.falhas_e_pendentes(cfg)
print(f"total com problema: {d['total']}")
print()

for f in d["falhas"]:
    print(f"  {f['nome']}")
    print(f"    arquivo: {f['arquivo']}  ({f['tamanho']/1024/1024:.1f} MB)")
    if f.get("sem_motivo"):
        print("    motivo : (sem registro -- veio da varredura)")
    else:
        print(f"    motivo : {f['motivo']}")
        print(f"    quando : {f['quando']}")
    print()

print("=== e um negativo que CONVERTEU não pode aparecer ===")
ok = "20261012_133746"
nomes = [f["nome"] for f in d["falhas"]]
print(f"  {ok} está na lista? {'SIM (errado)' if ok in nomes else 'não (correto)'}")
