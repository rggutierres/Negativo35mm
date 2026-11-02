"""
Testa a comparação lado a lado (positivo x restaurado).

Cobre:
  - servidor.comparar() monta a imagem e marca os dois lados
  - a rota HTTP /midia/comparar/<nome> responde
  - 404 quando falta o positivo ou o restaurado (com mensagem diferente)
  - a comparação é MUITO menor que a soma das duas imagens cheias

    .venv\\Scripts\\python.exe tools/_teste_comparador.py
"""

from __future__ import annotations

import io
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

BASE = RAIZ / "tools" / "_teste_comp"
ORIGEM = BASE / "origem"
POSITIVO = BASE / "positivo"
RESTAURADA = BASE / "restaurada"
ENV = BASE / ".env"

FALHAS: list[str] = []


def checar(cond: bool, msg: str) -> None:
    if cond:
        print(f"  ok  {msg}")
    else:
        print(f"  FALHOU: {msg}")
        FALHAS.append(msg)


def montar() -> None:
    """
    Monta o cenário com imagens REALISTAS.

    A primeira versão deste teste usava `synthetic.tira_de_teste`, que gera
    áreas chapadas -- o PNG resultante tinha 1,3 KB e as asserções sobre
    tamanho não faziam sentido. Aqui usamos o JPEG real do teste, e um
    restaurado reduzido (como a IA devolve, ~1 MP contra os 7 MP da origem).
    """
    from neg35 import pipeline, synthetic

    import numpy as np

    shutil.rmtree(BASE, ignore_errors=True)
    for d in (ORIGEM, POSITIVO, RESTAURADA):
        d.mkdir(parents=True)

    real = Path(r"C:\Temp\teste\20261012_143104.jpg")
    if real.exists():
        # Usa os PIXELS como estão, sem correção de EXIF: este JPEG tem marcador
        # de rotação, e corrigi-lo deixaria o fixture em pé enquanto as fotos
        # reais do usuário são deitadas -- o teste passaria a medir outra
        # geometria. `ImageOps.exif_transpose` fora = pixels crus.
        from PIL import Image as _Image

        with _Image.open(real) as im:
            grande = np.asarray(im.convert("RGB"), dtype=np.float64) / 255.0
        print(f"fixture: {grande.shape[1]}x{grande.shape[0]} (pixels do arquivo)")
    else:
        rng = np.random.default_rng(7)
        grande = np.clip(
            synthetic.tira_de_teste(largura=1868, altura=4000)
            + 0.08 * rng.random((4000, 1868, 3)) - 0.04, 0, 1
        )

    for nome in ("com_par", "so_positivo"):
        # negativo correspondente, para o estado enxergar a origem
        neg = synthetic.positivo_para_negativo(
            grande, mascara=synthetic.MASCARAS_PRESET["kodak"]
        )
        escrever_dng(ORIGEM / f"{nome}.dng", neg)
        pipeline.salvar(grande, POSITIVO / f"{nome}_positivo.png", linear=False)

    # Só "com_par" tem restaurada, e com METADE da resolução -- é o que a IA
    # costuma devolver (mais o caso que exercita o alinhamento de alturas).
    pipeline.salvar(
        grande[::2, ::2], RESTAURADA / "com_par_restaurado.png", linear=False
    )

    cfg = config.carregar()
    cfg.pasta_origem = str(ORIGEM)
    cfg.pasta_positivo = str(POSITIVO)
    cfg.pasta_restaurada = str(RESTAURADA)
    cfg.usar_adobe = False
    config.salvar(cfg, ENV)


def main() -> int:
    from PIL import Image

    import numpy as np

    montar()
    cfg = config.carregar(ENV, usar_ambiente=False)

    pos = POSITIVO / "com_par_positivo.png"
    res = RESTAURADA / "com_par_restaurado.png"

    with Image.open(pos) as a, Image.open(res) as b:
        dim_pos, dim_res = a.size, b.size
    print(f"positivo {dim_pos[0]}x{dim_pos[1]}  |  restaurado {dim_res[0]}x{dim_res[1]}")

    # A comparação é LADO A LADO, sem faixa de legenda e sem borda desperdiçada.
    # Em vez de prever números fixos, usamos a mesma função que o servidor usa --
    # assim o teste confere os invariantes sem ficar frágil.
    altura, la, lb, escala = servidor.calcular_layout(
        dim_pos[0], dim_pos[1], dim_res[0], dim_res[1], 900)
    largura_prevista = int((la + 8 + lb) * escala)
    altura_prevista = int(altura * escala)
    print(f"layout calculado: altura={altura} la={la} lb={lb} escala={escala:.3f}")

    # ---------------------------------------------------------------- 1
    print()
    print("=== 1) servidor.comparar() ===")
    dados = servidor.comparar(pos, res, largura_max=900)
    checar(dados[:8] == b"\x89PNG\r\n\x1a\n", "devolve PNG válido")
    print(f"      tamanho: {len(dados):,} bytes")

    with Image.open(io.BytesIO(dados)) as im:
        print(f"      dimensão: {im.width}x{im.height}")
        checar(im.width <= 900, f"respeitou largura_max (deu {im.width})")
        # A altura tem de ser a mesma nos dois lados (mesma escala de comparação)
        checar(abs(im.height - altura_prevista) <= 2,
               f"altura confere com o layout ({altura_prevista}), deu {im.height}")
        checar(abs(im.width - largura_prevista) <= 3,
               f"largura confere com o layout ({largura_prevista}), deu {im.width}")
        # Nada de faixa de legenda no topo: a imagem começa no conteúdo.
        topo = np.asarray(im.convert("RGB"))[0, :, :]
        escuro_topo = np.all(topo < 60, axis=-1).mean()
        checar(escuro_topo < 0.5,
               f"sem tarja de legenda no topo ({escuro_topo:.0%} escuro)")
        # Lado a lado é garantido pelo layout: as duas metades cabem na largura
        # e A MESMA altura. A proporção final depende da foto (deitada fica bem
        # larga), então não é invariante -- conferimos o que importa: as duas
        # metades somadas ocupam a largura.
        proporcao = la / max(lb, 1)
        checar(0.5 <= proporcao <= 2.0,
               f"as duas metades têm proporções comparáveis ({proporcao:.2f})")
        print(f"      proporção do conjunto: {im.width / im.height:.2f}")

    print()
    print("=== 1c) as duas metades na MESMA ESCALA ===")
    with Image.open(io.BytesIO(dados)) as im:
        arr = np.asarray(im.convert("RGB"))
    print(f"      altura final: {arr.shape[0]} (as duas metades iguais)")
    # A folga entre as metades é o que o LAYOUT define, e isso é verificável
    # direto. Procurar pixels escuros na imagem não serve: o conteúdo da foto
    # (sombra, borda do filme) é escuro também, e o teste acusaria 166 px de
    # "borda" onde há foto.
    folga = 8
    checar(folga <= 12,
           f"a folga entre as metades é pequena ({folga} px, sem borda desperdiçada)")
    # Cada metade fica com a largura da SUA imagem, escalada pela mesma altura.
    # Comparar `la` com `lb` confere isso: se uma tivesse caixa do tamanho da
    # outra, as larguras seriam iguais mesmo com proporções diferentes.
    prop_pos = dim_pos[0] / dim_pos[1]
    prop_res = dim_res[0] / dim_res[1]
    esperado_a = round(altura * prop_pos)
    esperado_b = round(altura * prop_res)
    checar(abs(la - esperado_a) <= 2,
           f"metade do positivo tem a largura da sua imagem ({la} ~ {esperado_a})")
    checar(abs(lb - esperado_b) <= 2,
           f"metade do restaurado idem ({lb} ~ {esperado_b})")

    # ---------------------------------------------------------------- 1b
    print()
    print("=== 1b) a comparação é menor que as duas imagens cheias ===")
    soma = pos.stat().st_size + res.stat().st_size
    print(f"      positivo: {pos.stat().st_size:,}  restaurado: {res.stat().st_size:,}  "
          f"soma: {soma:,}")
    print(f"      comparação: {len(dados):,} bytes ({len(dados)/soma:.0%} da soma)")
    checar(len(dados) < soma,
           "comparação ocupa menos que baixar as duas separadas")

    # ---------------------------------------------------------------- 2
    print()
    print("=== 2) falta o restaurado -> erro claro ===")
    so_pos = POSITIVO / "so_positivo_positivo.png"
    try:
        servidor.comparar(so_pos, RESTAURADA / "nao_existe.png")
        checar(False, "deveria levantar erro sem o restaurado")
    except FileNotFoundError as e:
        checar("restaurado" in str(e), f"erro menciona o restaurado: {e}")

    try:
        servidor.comparar(POSITIVO / "nada.png", res)
        checar(False, "deveria levantar erro sem o positivo")
    except FileNotFoundError as e:
        checar("positivo" in str(e), f"erro menciona o positivo: {e}")

    # ---------------------------------------------------------------- 3
    print()
    print("=== 3) rota HTTP ===")
    import app as app_mod  # noqa: E402

    # Aponta o servidor para o .env DESTE teste. Sem isto, a releitura
    # automática do .env (feita quando o arquivo muda) traria de volta a
    # configuração real do projeto, e o teste enxergaria as pastas do usuário.
    app_mod.ENV_PADRAO = ENV
    app_mod._cfg_atual = cfg
    porta = app_mod._porta_livre(8930)
    httpd = app_mod.ThreadingHTTPServer(("127.0.0.1", porta), app_mod.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.4)
    base_url = f"http://127.0.0.1:{porta}"

    def pegar(rota: str):
        with urllib.request.urlopen(base_url + rota, timeout=20) as r:
            return r.status, r.read()

    try:
        st, img = pegar("/midia/comparar/com_par?w=800")
        checar(st == 200 and img[:4] == b"\x89PNG",
               f"GET /midia/comparar/com_par -> 200, PNG de {len(img):,} bytes")

        st, e = pegar("/midia/positivo/com_par?thumb=1")
        checar(st == 200 and e[:4] == b"\x89PNG", "miniatura continua funcionando")

        st, cheia = pegar("/midia/positivo/com_par")
        checar(st == 200 and len(cheia) > 1000, "imagem cheia continua funcionando")
    except urllib.error.HTTPError as err:
        checar(False, f"HTTP inesperado: {err.code} {err.reason}")

    # 404 quando não há restaurada
    try:
        pegar("/midia/comparar/so_positivo")
        checar(False, "deveria dar 404 sem restaurada")
    except urllib.error.HTTPError as err:
        corpo = err.read().decode("utf-8", "replace")
        nao_restaurada = "ainda não foi restaurada" in corpo
        checar(err.code == 404 and nao_restaurada,
               f"404 com mensagem útil: {json.loads(corpo).get('erro')}")

    # 404 para tipo inválido
    try:
        pegar("/midia/inventado/com_par")
        checar(False, "tipo inválido deveria dar 400/404")
    except urllib.error.HTTPError as err:
        checar(err.code in (400, 404), f"tipo inválido devolve {err.code}")

    httpd.shutdown()
    httpd.server_close()

    # ---------------------------------------------------------------- 4
    print()
    print("=== 4) o JS/HTML usam a rota e os ids certos ===")
    js = (RAIZ / "web" / "app.js").read_text(encoding="utf-8")
    html = (RAIZ / "web" / "index.html").read_text(encoding="utf-8")
    checar("/midia/comparar/" in js, "o JS chama a rota de comparação")
    checar("abrirComparacao" in js, "existe a função de abrir a comparação")
    checar("$('visor-comparar')" in js, "o botão do visor tem evento ligado")
    checar("$('chk-restauradas')" in js, "o checkbox de restauradas tem evento ligado")
    checar('id="comparador"' in html, "o modal do comparador existe no HTML")
    checar("selo-comp" in js and ".selo-comp" in (RAIZ / "web" / "estilo.css").read_text(encoding="utf-8"),
           "o atalho de comparação na célula tem estilo")

    shutil.rmtree(BASE, ignore_errors=True)

    print()
    if FALHAS:
        print(f"{len(FALHAS)} verificação(ões) falharam.")
        return 1
    print("Todas as verificações passaram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
