"""Testa a API e o HTML da aba 'Falha na Restauração'."""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))

from neg35 import config  # noqa: E402

import app as m  # noqa: E402

m._cfg_atual = config.carregar()
porta = m._porta_livre(8895)
srv = m.ThreadingHTTPServer(("127.0.0.1", porta), m.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.6)
base = f"http://127.0.0.1:{porta}"

print("=== GET /api/falhas-restauro ===")
with urllib.request.urlopen(base + "/api/falhas-restauro", timeout=60) as r:
    d = json.loads(r.read())
print(f"  total: {d['total']}   limite de máscara: {d['limite_mascara']}")
for f in d["falhas"]:
    print(f"    {f['nome']}  R/B={f['r_b']}  fraca={f['mascara_fraca']}  "
          f"positivo={f['tem_positivo']}")

print()
print("=== GET /api/falhas (conversão) ainda funciona? ===")
with urllib.request.urlopen(base + "/api/falhas", timeout=60) as r:
    dc = json.loads(r.read())
print(f"  total: {dc['total']}")

print()
print("=== o HTML tem as duas abas? ===")
with urllib.request.urlopen(base + "/", timeout=60) as r:
    h = r.read().decode("utf-8")
for marca in ("Falha na Conversão para Positivo", "Falha na Restauração",
              "painel-falhas-restauro", "restauro-forcar-todas",
              "restauro-lista", "aba-conta-restauro"):
    print(f"  {'OK ' if marca in h else 'NAO'}  {marca}")

print()
print("=== o nome ANTIGO não deve mais existir ===")
print(f"  'Falhas na conversão': "
      f"{'AINDA EXISTE (errado)' if 'Falhas na conversão' in h else 'removido (correto)'}")

srv.shutdown()
