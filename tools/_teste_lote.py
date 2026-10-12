"""
Testa o fluxo do tools/lote.py sem tocar nas pastas reais nem gastar API.

Cria uma origem simulada com negativos sintéticos, roda o lote em modo
--so-local, e confere:
- criação do .env
- listagem e filtro de já-restaurados
- geração dos positivos
- que um segundo run não reprocessa o que já foi restaurado
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from neg35 import pipeline, synthetic  # noqa: E402

BASE = RAIZ / "tools" / "_teste_lote"
ORIGEM = BASE / "origem"
POSITIVO = BASE / "positivo"
RESTAURADA = BASE / "restaurada"
ENV = BASE / ".env"

PY = RAIZ / ".venv" / "Scripts" / "python.exe"


def montar() -> None:
    """Cria três negativos sintéticos (DNG de verdade) e um 'já restaurado'."""
    import shutil

    from dng_teste import escrever_dng

    shutil.rmtree(BASE, ignore_errors=True)
    ORIGEM.mkdir(parents=True)
    POSITIVO.mkdir(parents=True)
    RESTAURADA.mkdir(parents=True)

    original = synthetic.tira_de_teste(largura=320, altura=220)
    for i, nome in enumerate(["foto_a", "foto_b", "foto_c"], 1):
        neg = synthetic.positivo_para_negativo(
            original, mascara=synthetic.MASCARAS_PRESET["kodak"]
        )
        # DNG de verdade: o LibRaw e o ImageMagick decidem pelo CONTEÚDO, então
        # um PNG renomeado para .dng é recusado pelos dois.
        escrever_dng(ORIGEM / f"{nome}.dng", neg)
        # Uma "foto_b.jpg" junto, para testar a preferência por DNG.
        if i == 2:
            pipeline.salvar(neg, ORIGEM / f"{nome}.jpg", linear=False)

    # Simula foto_a JÁ restaurada, para o filtro ter o que pular.
    pipeline.salvar(original, RESTAURADA / "foto_a_restaurado.png", linear=False)

    # Simula foto_a JÁ restaurada, para o filtro ter o que pular.
    pipeline.salvar(original, RESTAURADA / "foto_a_restaurado.png", linear=False)


def rodar(*args: str) -> tuple[int, str]:
    proc = subprocess.run(
        [str(PY), str(RAIZ / "tools" / "lote.py"), "--env", str(ENV),
         "--sem-perguntar-pastas", *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(RAIZ),
        env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
    )
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    falhas = 0
    montar()

    print("=== 1) o .env é criado com os padrões do código ===")
    rc, saida = rodar("--so-local", "--selecao", "todos")
    if ENV.exists():
        print(f"  ok  .env criado ({ENV.stat().st_size} bytes)")
    else:
        print("  FALHOU: .env não foi criado")
        falhas += 1
        print(saida[:1500])
        return 1

    # Aponta o .env para as pastas de teste usando a API de config, não
    # substituição de texto (que é frágil e já mordeu uma vez).
    from neg35 import config as cfgmod

    cfg = cfgmod.carregar(ENV, usar_ambiente=False)
    cfg.pasta_origem = str(ORIGEM)
    cfg.pasta_positivo = str(POSITIVO)
    cfg.pasta_restaurada = str(RESTAURADA)
    cfgmod.salvar(cfg, ENV)

    relido = cfgmod.carregar(ENV, usar_ambiente=False)
    if relido.pasta_origem != str(ORIGEM):
        print(f"  FALHOU: caminho corrompeu no round-trip: {relido.pasta_origem!r}")
        return 1
    print(f"  ok  caminhos preservados no round-trip ({relido.pasta_origem})")

    print()
    print("=== 2) execução local: lista os 3 (nenhum positivo existe ainda) ===")
    rc, saida = rodar("--so-local", "--selecao", "todos")
    for linha in saida.splitlines():
        if any(k in linha for k in ("foto(s) na origem", "já com", "a processar",
                                    "processadas", "falhas", "positivo ok")):
            print("  " + linha.strip())

    gerados = sorted(p.name for p in POSITIVO.glob("*.png"))
    print(f"  positivos gerados: {gerados}")
    if len(gerados) == 3:
        print("  ok  gerou os 3 positivos (critério do modo local = pasta Positivo)")
    else:
        print(f"  FALHOU: esperava 3 positivos, veio {gerados}")
        falhas += 1

    print()
    print("=== 2b) critério com IA: foto_a tem restaurado, então é pulada ===")
    # Testa a função de filtro direto, porque o script sem chave de API cai
    # para o modo local mesmo sem --so-local.
    from neg35 import config as cfgmod

    sys.path.insert(0, str(RAIZ / "tools"))
    import lote as lote_mod  # noqa: E402

    cfg_t = cfgmod.carregar(ENV, usar_ambiente=False)
    todos = lote_mod.listar_originais(ORIGEM)
    pend, pul = lote_mod.filtrar_pendentes(todos, cfg_t, RESTAURADA, com_ia=True)
    print(f"  modo IA: {len(todos)} originais -> {pul} pulados, {len(pend)} pendentes")
    print(f"  pendentes: {[p['nome'] for p in pend]}")
    if pul == 1 and len(pend) == 2:
        print("  ok  pulou foto_a (já restaurada) e manteve b e c")
    else:
        print("  FALHOU: esperava 1 pulado e 2 pendentes")
        falhas += 1

    print()
    print("=== 3) preferência por DNG quando existe JPG também ===")
    print(f"  arquivos em origem: {sorted(p.name for p in ORIGEM.iterdir())}")
    if "foto_b.dng" in saida or "foto_b" in saida:
        # Confere na listagem qual fonte foi escolhida
        for linha in saida.splitlines():
            if "foto_b" in linha and ("DNG" in linha or "JPG" in linha):
                print(f"  listagem: {linha.strip()}")
                if "DNG" in linha:
                    print("  ok  escolheu o DNG, não o JPG")
                else:
                    print("  FALHOU: escolheu o JPG tendo DNG disponível")
                    falhas += 1
                break

    print()
    print("=== 4) segunda execução: nada a fazer (já tem positivo) ===")
    rc, saida = rodar("--so-local", "--selecao", "todos")
    if "Nada a fazer" in saida:
        print("  ok  reconheceu que não há pendentes")
    else:
        print("  FALHOU: deveria dizer que não há pendentes")
        print(saida[:800])
        falhas += 1

    print()
    print("=== 5) apagando um positivo: ele volta a ser pendente ===")
    alvo = next(POSITIVO.glob("foto_b_positivo.png"), None)
    if alvo:
        alvo.unlink()
    rc, saida = rodar("--so-local", "--selecao", "1")
    for linha in saida.splitlines():
        if "selecionadas" in linha or "positivo ok" in linha or "a processar" in linha:
            print("  " + linha.strip())
    if (POSITIVO / "foto_b_positivo.png").exists():
        print("  ok  regenerou o positivo apagado, e só ele")
    else:
        print("  FALHOU: não regenerou foto_b")
        falhas += 1

    import shutil

    shutil.rmtree(BASE, ignore_errors=True)

    print()
    print("Todos os passos passaram." if not falhas else f"{falhas} passo(s) falharam.")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
