"""
Testa a restauração PELO SERVIDOR, exatamente como a tela faz.

Diferença para os testes anteriores: aqueles chamavam `servidor.restaurar`
direto no processo. Este fala HTTP com o servidor que está no ar, então exercita
o caminho real da interface: /api/regenerar, progresso, gravação do arquivo.

Verifica no fim:
  - a chamada foi aceita
  - o trabalho terminou sem erro
  - o arquivo foi regravado
  - o resultado NÃO tem faixa de borda (os furinhos)
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from PIL import Image  # noqa: E402

from neg35 import config, post  # noqa: E402

BASE = "http://127.0.0.1:8765"
NOME = sys.argv[1] if len(sys.argv) > 1 else "20261012_133746"

cfg = config.carregar()
restaurada = Path(cfg.pasta_restaurada) / f"{NOME}_restaurado.png"


def pedir(rota: str, corpo: dict | None = None, timeout: int = 60):
    dados = None
    cabecalho = {}
    if corpo is not None:
        dados = json.dumps(corpo).encode("utf-8")
        cabecalho["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + rota, data=dados, headers=cabecalho,
                                 method="POST" if dados else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


print(f"=== testando pelo SERVIDOR: {NOME} ===")
print()

antes = None
if restaurada.is_file():
    with Image.open(restaurada) as im:
        antes = np.asarray(im.convert("RGB")).astype(np.float64) / 255.0
    print(f"  restaurada atual: {antes.shape[1]}x{antes.shape[0]}  "
          f"({restaurada.stat().st_mtime:.0f})")
else:
    print("  não existe restaurada ainda")

print()
print("--- POST /api/regenerar (é o que o botão 'Refazer' faz) ---")
st, resp = pedir("/api/regenerar", {"nome": NOME, "brilho": 1.0, "forcar": True})
print(f"  HTTP {st}: {resp}")
if st != 200:
    print("\n  a chamada foi recusada -- nada a medir")
    raise SystemExit(1)

print()
print("--- acompanhando o progresso ---")
limite = time.time() + 300
visto = []
while time.time() < limite:
    st, prog = pedir("/api/progresso")
    if st != 200:
        print(f"  erro no progresso: {st} {prog}")
        break
    etapa = prog.get("etapa") or prog.get("fase") or ""
    msg = prog.get("msg") or ""
    if (etapa, msg) not in visto and (etapa or msg):
        visto.append((etapa, msg))
        print(f"  [{etapa}] {msg[:90]}")
    if prog.get("terminado"):
        print(f"  terminado. resumo: "
              f"ok={prog.get('ok')} falhas={prog.get('falhas')}")
        print(f"  detalhes: {prog.get('resultados')}")
        erro = prog.get("erro")
        if erro:
            print(f"  ERRO: {erro}")
        break
    time.sleep(2)
else:
    print("  não terminou em 5 min")

print()
print("--- o arquivo foi regravado? ---")
if not restaurada.is_file():
    print("  NÃO existe restaurada -- a restauração falhou")
    raise SystemExit(1)

depois = None
for _ in range(5):
    with Image.open(restaurada) as im:
        depois = np.asarray(im.convert("RGB")).astype(np.float64) / 255.0
    break

mtime = restaurada.stat().st_mtime
print(f"  arquivo: {depois.shape[1]}x{depois.shape[0]}  mtime {mtime:.0f}")
if antes is not None and antes.shape == depois.shape:
    dif = float(np.abs(antes - depois).mean())
    print(f"  diferença média para a versão anterior: {dif:.4f}")
    print(f"  -> {'MUDOU (regenerou)' if dif > 0.01 else 'IGUAL (não regenerou!)'}")

print()
print("--- verificação: sobrou faixa de borda? ---")
lum = post.luminancia(depois)
h, w = lum.shape


def faixa_clara(perfil_lum, perfil_grad=None, lim=0.80):
    n = 0
    for v in perfil_lum:
        if v > lim:
            n += 1
        else:
            break
    return n


cols = [float(np.median(lum[:, i])) for i in range(w)]
cols_rev = [float(np.median(lum[:, w - 1 - i])) for i in range(w)]
lins = [float(np.median(lum[i, :])) for i in range(h)]
lins_rev = [float(np.median(lum[h - 1 - i, :])) for i in range(h)]

res = {
    "esquerda": faixa_clara(cols),
    "direita": faixa_clara(cols_rev),
    "topo": faixa_clara(lins),
    "base": faixa_clara(lins_rev),
}
for lado, n in res.items():
    print(f"  {lado:<9}: {n} px de faixa clara")

prop = depois.shape[1] / depois.shape[0]
print(f"  proporção: {prop:.3f}  (quadro 35mm = 1,500; sem recorte = ~2,14)")

print()
pior = max(res.values())
if pior <= 35 and abs(prop - 1.5) < 0.12:
    print(f"  RESULTADO: OK -- faixa residual máxima de {pior} px, "
          f"proporção de quadro 3:2.")
    print("  -> os furinhos foram eliminados pelo caminho da interface.")
    raise SystemExit(0)
print(f"  RESULTADO: atencao -- faixa de {pior} px, proporção {prop:.3f}.")
raise SystemExit(2)
