"""
Regrava o .env do projeto acrescentando as chaves que faltavam.

Preserva TODOS os valores atuais (pastas, chave de API, prompt, ajustes). Só
acrescenta as chaves novas.

Este script existiu antes e foi apagado; o problema voltou quando acrescentei
`casar_exposicao` e `exposicao_forca` ao Config sem regravar o arquivo. Agora
fica no projeto: o teste `_teste_env_completo` acusa a falta, e este script
resolve.
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import fields
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from neg35 import config  # noqa: E402

ENV = RAIZ / ".env"
BACKUP = RAIZ / ".env.bak"


def chaves_de(caminho: Path) -> set[str]:
    if not caminho.is_file():
        return set()
    s = set()
    for linha in caminho.read_text(encoding="utf-8", errors="replace").splitlines():
        limpa = linha.strip()
        if limpa and not limpa.startswith("#") and "=" in limpa:
            s.add(limpa.split("=", 1)[0].strip())
    return s


antes = chaves_de(ENV)
cfg = config.carregar(ENV, usar_ambiente=False)

print("=== antes ===")
print(f"  chaves no .env: {len(antes)}")
print(f"  pasta_origem  : {cfg.pasta_origem}")
print(f"  pasta_positivo: {cfg.pasta_positivo}")
print(f"  provedor      : {cfg.provedor}")
print(f"  chave         : {'preenchida' if cfg.openrouter_api_key else 'VAZIA'}"
      f" ({len(cfg.openrouter_api_key)} chars)")
print(f"  prompt        : {len(cfg.prompt)} caracteres")

if ENV.is_file():
    shutil.copy2(ENV, BACKUP)
    print(f"\n  backup em: {BACKUP.name}")

config.salvar(cfg, ENV)
depois = chaves_de(ENV)
todas = {f.name for f in fields(config.Config)}

print()
print("=== depois ===")
print(f"  chaves no .env: {len(depois)}")
novas = sorted(depois - antes)
if novas:
    print(f"  acrescentadas : {novas}")
removidas = sorted(antes - depois)
if removidas:
    print(f"  ATENÇÃO, removidas: {removidas}")
print(f"  faltando do Config: {sorted(todas - depois) or 'nenhuma'}")

lido = config.carregar(ENV, usar_ambiente=False)
print()
print("=== valores preservados? ===")
iguais = True
for campo in ("pasta_origem", "pasta_positivo", "pasta_restaurada", "provedor",
              "modelo", "filme", "saturacao", "nitidez", "balanco",
              "curva_alvo", "usar_curva", "usar_adobe", "max_lado_envio",
              "pasta_cache_adobe", "converter_auto", "prompt",
              "openrouter_api_key"):
    a, b = getattr(cfg, campo), getattr(lido, campo)
    if a != b:
        iguais = False
        print(f"  MUDOU {campo}: {a!r} -> {b!r}")
print("  todos preservados" if iguais else "  HOUVE MUDANÇA")
