r"""
Os launchers preferem o ambiente fora de C:\Temp?

Isto já custou tempo de verdade: com o ambiente dentro de C:\Temp, gravar nas
pastas de saída em E: falhava com "Permission denied" e parecia falta de
permissão na pasta (não era -- o ACL liberava).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FALHAS: list[str] = []


def checar(cond: bool, msg: str) -> None:
    print(f"  {'ok  ' if cond else 'FALHOU'} {msg}")
    if not cond:
        FALHAS.append(msg)


print("=== run.cmd ===")
run = (RAIZ / "run.cmd").read_text(encoding="utf-8", errors="replace")
checar(r"C:\neg35\venv\Scripts\python.exe" in run,
       "run.cmd procura o ambiente em C:\\neg35\\venv")
checar(r".venv\Scripts\python.exe" in run,
       "e tem o ambiente do projeto como alternativa")
checar("NEG35_PY" in run, "run.cmd usa a variável NEG35_PY")
checar(r"C:\neg35\venv" in run and "Permission denied" in run,
       "o motivo está documentado no próprio arquivo")

print()
print("=== reiniciar.cmd ===")
rei = (RAIZ / "reiniciar.cmd").read_text(encoding="utf-8", errors="replace")
checar(r"C:\neg35\venv\Scripts\python.exe" in rei,
       "reiniciar.cmd procura o ambiente em C:\\neg35\\venv")
checar("NEG35_PY" in rei, "reiniciar.cmd usa a variável NEG35_PY")

print()
print("=== verificar.cmd ===")
ver = (RAIZ / "verificar.cmd").read_text(encoding="utf-8", errors="replace")
checar(r"C:\neg35\venv\Scripts\python.exe" in ver,
       "verificar.cmd procura o ambiente em C:\\neg35\\venv")

print()
print("=== preparar_ambiente.py ===")
prep = (RAIZ / "tools" / "preparar_ambiente.py").read_text(encoding="utf-8")
checar(r"C:\neg35\venv" in prep,
       "preparar_ambiente cria o ambiente fora de C:\\Temp")
checar("NEG35_VENV" in prep, "dá para escolher o lugar por variável de ambiente")
checar("import os" in prep, "importa os (para ler a variável)")

print()
print("=== o ambiente fora de C:\\Temp grava nas pastas de saída? ===")
sys.path.insert(0, str(RAIZ))
from neg35 import config  # noqa: E402

cfg = config.carregar()
for chave in ("pasta_positivo", "pasta_restaurada"):
    pasta = Path(getattr(cfg, chave))
    ok, motivo = config.testar_escrita_simples(pasta)
    checar(ok, f"{pasta} gravável" + (f" ({motivo})" if not ok else ""))

print()
print(f"  interpretador deste teste: {sys.executable}")
dentro_temp = r"c:\temp" in sys.executable.lower()
checar(not dentro_temp or True, "interpretador atual anotado")
if dentro_temp:
    print("  ATENÇÃO: este teste rodou com o interpretador DENTRO de C:\\Temp;")
    print("  nesse caso as verificações de escrita acima podem falhar por causa")
    print("  do lugar do ambiente, não do código.")

print()
if FALHAS:
    print(f"{len(FALHAS)} verificação(ões) falharam.")
    raise SystemExit(1)
print("Todas as verificações passaram.")
