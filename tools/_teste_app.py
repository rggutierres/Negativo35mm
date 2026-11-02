"""
Testa a interface: lógica do servidor, rotas HTTP e a página.

Não abre porta fixa nem depende de navegador. O servidor HTTP é iniciado numa
porta livre temporária só durante o teste.

    .venv\\Scripts\\python.exe tools/_teste_app.py
"""

from __future__ import annotations

import json
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))

from neg35 import config, servidor  # noqa: E402
from dng_teste import escrever_dng  # noqa: E402

BASE = RAIZ / "tools" / "_teste_app"
ORIGEM = BASE / "origem"
POSITIVO = BASE / "positivo"
RESTAURADA = BASE / "restaurada"
ENV = BASE / ".env"


def montar() -> None:
    from neg35 import pipeline, synthetic

    shutil.rmtree(BASE, ignore_errors=True)
    for d in (ORIGEM, POSITIVO, RESTAURADA):
        d.mkdir(parents=True)

    original = synthetic.tira_de_teste(largura=300, altura=200)
    for i, nome in enumerate(["foto_a", "foto_b", "foto_c"], 1):
        neg = synthetic.positivo_para_negativo(
            original, mascara=synthetic.MASCARAS_PRESET["kodak"]
        )
        escrever_dng(ORIGEM / f"{nome}.dng", neg)
        if i == 2:
            pipeline.salvar(neg, ORIGEM / f"{nome}.jpg", linear=False)

    # foto_a já tem positivo E restaurado -> não deve aparecer em nenhuma fila
    cfg = config.carregar()
    cfg.pasta_origem = str(ORIGEM)
    cfg.pasta_positivo = str(POSITIVO)
    cfg.pasta_restaurada = str(RESTAURADA)
    cfg.usar_adobe = False
    cfg.usar_curva = True
    config.salvar(cfg, ENV)


def cfg_teste() -> config.Config:
    return config.carregar(ENV, usar_ambiente=False)


def main() -> int:
    falhas = 0

    def checar(cond: bool, msg: str) -> None:
        nonlocal falhas
        if cond:
            print(f"  ok  {msg}")
        else:
            print(f"  FALHOU: {msg}")
            falhas += 1

    montar()
    cfg = cfg_teste()

    # ---------------------------------------------------------------- 1
    print("=== 1) varredura inicial ===")
    est = servidor.estado(cfg)
    print(f"  total={est['contagens']['total']} "
          f"faltam_positivo={est['contagens']['faltam_positivo']} "
          f"faltam_restaurar={est['contagens']['faltam_restaurar']}")
    checar(est["contagens"]["total"] == 3, "encontrou 3 fotos")
    checar(est["contagens"]["faltam_positivo"] == 3, "3 sem positivo")
    checar(est["contagens"]["faltam_restaurar"] == 0, "0 na fila de restaurar")
    checar(len(est["itens"]) == 3, "3 itens no estado")
    nomes_dng = [i for i in est["itens"] if i["tipo"] == "DNG"]
    checar(len(nomes_dng) == 3, "preferiu DNG nos três (foto_b tem JPG junto)")

    # ---------------------------------------------------------------- 2
    print()
    print("=== 2) conversão com progresso ===")
    eventos = []
    resumo = servidor.converter(cfg, progresso=lambda e: eventos.append(dict(e)))
    print(f"  resumo: total={resumo['total']} ok={resumo['ok']} "
          f"falhas={resumo['falhas']} em {resumo['segundos']}s")
    checar(resumo["total"] == 3, "converteu 3")
    checar(resumo["ok"] == 3, "3 positivos gerados")
    checar(resumo["falhas"] == 0, "sem falhas")
    checar(len(eventos) > 3, f"emitiu eventos de progresso ({len(eventos)})")
    etapas = {e["etapa"] for e in eventos}
    checar("invertendo" in etapas, f"tem etapa 'invertendo' (etapas: {sorted(etapas)})")
    checar("pronto" in etapas, "tem etapa 'pronto'")

    positivos = sorted(p.name for p in POSITIVO.glob("*.png"))
    checar(len(positivos) == 3, f"3 arquivos de positivo em disco: {positivos}")

    # ---------------------------------------------------------------- 3
    print()
    print("=== 3) estado depois de converter ===")
    est2 = servidor.estado(cfg)
    print(f"  com_positivo={est2['contagens']['com_positivo']} "
          f"faltam_restaurar={est2['contagens']['faltam_restaurar']} "
          f"faltam_positivo={est2['contagens']['faltam_positivo']}")
    checar(est2["contagens"]["faltam_positivo"] == 0, "nada mais a converter")
    checar(est2["contagens"]["faltam_restaurar"] == 3, "3 na fila de restaurar")
    checar(len(est2["pendentes_restaurar"]) == 3, "pendentes_restaurar tem 3")

    # ---------------------------------------------------------------- 4
    print()
    print("=== 4) miniatura ===")
    algum = next(POSITIVO.glob("*.png"))
    dados = servidor.thumb(algum, 200)
    checar(dados[:8] == b"\x89PNG\r\n\x1a\n", "miniatura é PNG válido")
    from PIL import Image
    import io
    with Image.open(io.BytesIO(dados)) as im:
        print(f"  miniatura: {im.size[0]}x{im.size[1]}")
        checar(max(im.size) <= 200, "miniatura reduzida corretamente")

    # ---------------------------------------------------------------- 5
    print()
    print("=== 5) restaurar sem chave deve recusar tudo ===")
    resumo_r = servidor.restaurar(cfg, est2["pendentes_restaurar"][:1])
    ok_r = resumo_r["ok"]
    print(f"  resultados: {resumo_r['resultados']}")
    checar(ok_r == 0, "não restaurou nada (sem chave de API)")

    # ---------------------------------------------------------------- 6
    print()
    print("=== 6) servidor HTTP ===")
    import app as app_mod  # noqa: E402

    # Aponta o servidor para o .env DESTE teste, e não para o do projeto.
    # Hoje o servidor relê o .env quando o arquivo muda (mtime), então apontar
    # só `_cfg_atual` não basta: a releitura o traria de volta para o .env real
    # e o teste passaria a enxergar as 27 fotos do usuário.
    app_mod.ENV_PADRAO = ENV
    app_mod._cfg_atual = config.carregar(ENV, usar_ambiente=False)
    porta = app_mod._porta_livre(8910)
    httpd = app_mod.ThreadingHTTPServer(("127.0.0.1", porta), app_mod.Handler)
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    time.sleep(0.4)
    base_url = f"http://127.0.0.1:{porta}"

    def pegar(rota: str, cru: bool = False):
        req = urllib.request.Request(base_url + rota)
        with urllib.request.urlopen(req, timeout=20) as r:
            dados = r.read()
            return (r.status, dados) if cru else (r.status, json.loads(dados))

    def postar(rota: str, corpo: dict):
        req = urllib.request.Request(
            base_url + rota, method="POST",
            data=json.dumps(corpo).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read())

    try:
        st, html = pegar("/", cru=True)
        checar(st == 200 and b"neg35" in html, "GET / devolve a página")
        checar(b"progresso" in html and b"grade" in html,
               "a página tem barra de progresso e grade")

        st, css = pegar("/web/estilo.css", cru=True)
        checar(st == 200 and len(css) > 500, f"CSS servido ({len(css)} bytes)")
        st, js = pegar("/web/app.js", cru=True)
        checar(st == 200 and b"carregarEstado" in js, f"JS servido ({len(js)} bytes)")

        st, e = pegar("/api/estado")
        checar(st == 200 and e["contagens"]["total"] == 3, "GET /api/estado ok")

        st, p = pegar("/api/progresso")
        checar(st == 200 and "terminado" in p, "GET /api/progresso ok")

        st, c = pegar("/api/custo?nomes=a,b")
        checar(st == 200 and "usd" in c, f"GET /api/custo ok (US$ {c.get('usd')})")

        nome = est2["pendentes_restaurar"][0]
        st, img = pegar(f"/midia/positivo/{nome}?thumb=1", cru=True)
        checar(st == 200 and img[:4] == b"\x89PNG", "miniatura servida pela rota")
        st, img2 = pegar(f"/midia/positivo/{nome}", cru=True)
        checar(st == 200 and len(img2) > len(img), "imagem cheia é maior que a miniatura")

        # abre a pasta no Explorer: só as três configuradas, nada arbitrário
        st, j = pegar("/api/abrir-pasta?qual=positivo")
        checar(st == 200 and j.get("ok") is True, "abre a pasta de positivos")
        try:
            pegar("/api/abrir-pasta?qual=qualquer")
            checar(False, "deveria recusar 'qual' inválido")
        except urllib.error.HTTPError as err:
            checar(err.code == 400,
                   f"recusa 'qual' inválido com 400 (deu {err.code})")

        st, r = postar("/api/restaurar", {"nomes": []})
        checar(False, "não deveria aceitar lista vazia")
    except urllib.error.HTTPError as e:
        if e.code == 400:
            checar(True, "recusou restaurar sem seleção (HTTP 400)")
    except Exception as e:  # noqa: BLE001
        checar(False, f"erro inesperado no HTTP: {type(e).__name__}: {e}")

    # 404 numa rota inexistente
    try:
        pegar("/api/nao-existe")
        checar(False, "rota inexistente deveria dar 404")
    except urllib.error.HTTPError as e:
        checar(e.code == 404, f"rota inexistente devolve 404 (deu {e.code})")

    httpd.shutdown()
    httpd.server_close()

    shutil.rmtree(BASE, ignore_errors=True)

    print()
    print("Todos os testes passaram." if not falhas else f"{falhas} teste(s) falharam.")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
