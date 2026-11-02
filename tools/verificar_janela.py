"""
Confere se a janela do neg35 que está aberta está ATUALIZADA.

O Python carrega os módulos uma vez, ao iniciar, e não recarrega. Uma janela
aberta antes de uma correção continua rodando o código antigo -- e o erro
antigo reaparece como se nada tivesse sido corrigido.

Este script pergunta à janela em execução quais recursos ela tem e compara com
o que o código em disco implementa.

    verificar.cmd
    (ou) .venv\\Scripts\\python.exe tools\\verificar_janela.py
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from neg35 import servidor  # noqa: E402

PORTA = 8765
URL = f"http://127.0.0.1:{PORTA}/api/estado"

# Recursos que a TELA exige. Se faltar algum, a tela mostra o aviso laranja.
ESPERADOS_PELA_TELA = [
    "mascara_medida_no_negativo",
    "cache_adobe_configuravel",
    "pastas_de_saida_testadas",
    "chave_do_env",
    "cor_no_envio",
    "abrir_pasta_no_explorer",
]

print()
print("=" * 66)
print("  neg35 -- a janela aberta esta atualizada?")
print("=" * 66)

try:
    with urllib.request.urlopen(URL, timeout=15) as r:
        d = json.loads(r.read())
except urllib.error.URLError as e:
    print()
    print("  NÃO CONSEGUI FALAR COM O PROGRAMA")
    print(f"    {URL}")
    print(f"    motivo: {getattr(e, 'reason', e)}")
    print()
    print("  Provavelmente não há janela aberta.")
    print("  Abra com:  reiniciar.cmd")
    sys.exit(2)
except Exception as e:  # noqa: BLE001
    print(f"\n  Falha inesperada: {type(e).__name__}: {e}")
    sys.exit(2)

no_ar = set(d.get("recursos") or [])
no_disco = set(servidor.RECURSOS)

print()
print(f"  recursos no código em disco : {len(no_disco)}")
print(f"  recursos na janela aberta   : {len(no_ar)}")

faltando_tela = [r for r in ESPERADOS_PELA_TELA if r not in no_ar]
faltando_disco = sorted(no_disco - no_ar)

if not no_ar:
    print()
    print("  A janela não informa recursos nenhum: é uma versão bem antiga.")
    print("  Feche-a e abra com reiniciar.cmd")
    sys.exit(1)

print()
if not faltando_disco:
    print("  RESULTADO: a janela está ATUALIZADA.")
    print("             Ela tem todos os recursos do código em disco.")
    sys.exit(0)

print("  RESULTADO: a janela está DESATUALIZADA.")
print()
print("  Faltam (por recurso):")
for r in faltando_disco:
    exigido = " [a tela precisa deste]" if r in faltando_tela else ""
    print(f"    - {r}{exigido}")

print()
print("  O que fazer:")
print("    1. Feche a janela do neg35 (Ctrl+C ou feche a janela)")
print("    2. Rode:  reiniciar.cmd")
print()
if "cor_no_envio" in faltando_tela:
    print("  ATENÇÃO: falta 'cor_no_envio'. Enquanto isso, a imagem enviada à")
    print("  IA vai ~3x mais escura que o positivo, e o resultado sai escuro.")
sys.exit(1)
