"""Estado da conversão: quantos prontos, quantos faltam, e por quê."""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from neg35 import config, servidor  # noqa: E402

cfg = config.carregar()

print("=== pastas ===")
print(f"  origem      {cfg.pasta_origem}")
print(f"  positivo    {cfg.pasta_positivo}")
print(f"  restaurada  {cfg.pasta_restaurada}")
print(f"  auto        converter_auto = {cfg.converter_auto}")

print()
print("=== conversão ===")
d = servidor.verificar_pastas(cfg)
print(f"  positivo gravável: {d['positivo']['gravavel']}  {d['positivo']['erro']}")

est = servidor.estado(cfg)
c = est["contagens"]
print(f"  total            : {c['total']}")
print(f"  com positivo     : {c['com_positivo']}")
print(f"  faltam converter : {c['faltam_positivo']}")
print(f"  faltam restaurar : {c['faltam_restaurar']}")

if est["pendentes_positivo"]:
    print()
    print("  ainda sem positivo:")
    for n in est["pendentes_positivo"]:
        print(f"    {n}")

# Onde os arquivos realmente estão
print()
print("=== arquivos em disco ===")
for rotulo, pasta in (("configurado", Path(cfg.pasta_positivo)),
                      ("queda do projeto", RAIZ / "saida" / "positivo")):
    n = len(list(pasta.glob("*_positivo.png"))) if pasta.is_dir() else 0
    print(f"  {rotulo:<18} {n:>3} arquivo(s)  {pasta}")
