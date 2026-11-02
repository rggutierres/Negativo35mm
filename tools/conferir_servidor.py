"""
O servidor está no ar e ATUALIZADO?

Confere, numa única chamada: os controles novos no HTML servido, os campos no
/api/config, e os recursos que o servidor declara.

Serve para responder "eu fechei e abri de novo, mas não vejo a mudança" com
dados, em vez de suposição.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"

falhas = []


def checar(cond: bool, msg: str) -> None:
    print(f"  {'ok  ' if cond else 'FALHOU'} {msg}")
    if not cond:
        falhas.append(msg)


print(f"=== {BASE} ===")
try:
    with urllib.request.urlopen(f"{BASE}/api/estado", timeout=25) as r:
        estado = json.loads(r.read())
except (urllib.error.URLError, OSError) as e:
    print(f"  o servidor NÃO respondeu: {e}")
    print()
    print("  Nada rodando nesse endereço. Suba com run.cmd (ou reiniciar.cmd).")
    raise SystemExit(1)

print(f"  recursos declarados: {len(estado.get('recursos', []))}")
for r in estado.get("recursos", []):
    print(f"    - {r}")

print()
print("=== controles na tela de configuração ===")
with urllib.request.urlopen(f"{BASE}/", timeout=25) as r:
    html = r.read().decode("utf-8")

ESPERADOS = [
    ("cfg-recortar-bordas", "Recortar a borda do filme (furinhos)"),
    ("cfg-recorte-margem", "Folga de borda a manter"),
    ("cfg-dica", "Medir a foto e enviar os números no prompt"),
    ("cfg-casar-exposicao", "Clarear o resultado da IA"),
    ("cfg-exposicao-forca", "Clarear: força"),
    ("cfg-auto", "converter automaticamente"),
    ("cfg-cache-adobe", "cache do Adobe"),
]
for cid, rotulo in ESPERADOS:
    checar(f'id="{cid}"' in html, f"{rotulo}  [{cid}]")

print()
print("=== campos entregues pelo /api/config ===")
with urllib.request.urlopen(f"{BASE}/api/config", timeout=25) as r:
    cfg = json.loads(r.read())
for k in ("recortar_bordas", "recorte_margem", "dica_por_foto",
          "casar_exposicao", "exposicao_forca", "pastas", "tem_chave"):
    checar(k in cfg, f"{k} = {cfg.get(k)!r}")

print()
print("=== o JavaScript servido tem o aviso de regeneração? ===")
# O JS é servido por /web/, não numa rota própria.
with urllib.request.urlopen(f"{BASE}/web/app.js", timeout=25) as r:
    js = r.read().decode("utf-8")
checar("Gerando novamente com IA" in js, "aviso 'Gerando novamente com IA'")
checar("compVersao" in js, "contador de versão (fura o cache)")
checar("urlImagemGrande('restaurado'" in js
       or 'urlImagemGrande("restaurado"' in js,
       "abre só a restaurada ao clicar")

print()
if falhas:
    print(f"{len(falhas)} verificação(ões) falharam.")
    print("Se o HTML não tem os controles, o servidor em execução é ANTIGO:")
    print("encerre todos e suba de novo (tools/reiniciar.cmd).")
    raise SystemExit(1)
print("O servidor está no ar e ATUALIZADO.")
