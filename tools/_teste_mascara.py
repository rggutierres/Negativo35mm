"""
Testa a medida da máscara usada pela proteção "máscara fraca".

Havia um bug grave e silencioso aqui: a máscara era medida no POSITIVO já
invertido, com `core.detectar_base_do_filme`. Essa função procura a máscara
laranja do NEGATIVO -- no positivo ela virou preto, e a função devolvia
R = 1.0000 exato em todas as fotos. Como o limite é R/B >= 2,5, TODA
restauração era pulada, sempre, com a mensagem "máscara fraca".

O bug era invisível porque a mensagem parecia plausível.

    .venv\\Scripts\\python.exe tools/_teste_mascara.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))

from neg35 import config, core, pipeline, servidor, synthetic  # noqa: E402
from dng_teste import escrever_dng  # noqa: E402

BASE = RAIZ / "tools" / "_teste_mascara"
ORIGEM = BASE / "origem"
POSITIVO = BASE / "positivo"
RESTAURADA = BASE / "restaurada"
ENV = BASE / ".env"
# Limite de produção: R/B abaixo disso, a restauração pula.
LIMITE = 2.5
# A máscara Kodak SINTÉTICA mede ~1,6, não os ~3-4,5 de um negativo real.
# Então, para este teste, usamos um limite proporcional -- o que se verifica
# aqui é a LÓGICA (medir no negativo, comparar com o limite), não o valor
# absoluto do filme sintético.
LIMITE_SINTETICO = 1.3

FALHAS: list[str] = []


def checar(cond: bool, msg: str) -> None:
    if cond:
        print(f"  ok  {msg}")
    else:
        print(f"  FALHOU: {msg}")
        FALHAS.append(msg)


def montar() -> None:
    shutil.rmtree(BASE, ignore_errors=True)
    for d in (ORIGEM, POSITIVO, RESTAURADA):
        d.mkdir(parents=True)

    # Negativo sintético com máscara Kodak (bem alaranjada) e um com máscara
    # neutralizada (o caso que a proteção deve pegar).
    original = synthetic.tira_de_teste(largura=400, altura=300)

    neg_boa = synthetic.positivo_para_negativo(
        original, mascara=synthetic.MASCARAS_PRESET["kodak"]
    )
    escrever_dng(ORIGEM / "boa.dng", neg_boa)

    # máscara fraca: base quase neutra
    neutra = synthetic.positivo_para_negativo(original, mascara=(0.55, 0.55, 0.55))
    escrever_dng(ORIGEM / "fraca.dng", neutra)

    for nome, neg in (("boa", neg_boa), ("fraca", neutra)):
        res = pipeline.desenvolver(neg, pipeline.Parametros(), entrada_linear=True,
                                   manter_etapas=False)
        pipeline.salvar(res.positivo, POSITIVO / f"{nome}_positivo.png", linear=True)

    cfg = config.carregar()
    cfg.pasta_origem = str(ORIGEM)
    cfg.pasta_positivo = str(POSITIVO)
    cfg.pasta_restaurada = str(RESTAURADA)
    cfg.usar_adobe = False
    config.salvar(cfg, ENV)


def main() -> int:
    montar()
    cfg = config.carregar(ENV, usar_ambiente=False)

    # ---------------------------------------------------------------- 1
    print("=== 1) medir no POSITIVO é sem sentido (o bug original) ===")
    # Demonstra por que o bug era invisível: a função "funciona" e devolve um
    # número -- só que sem significado nenhum.
    valores_positivo = []
    for arq in sorted(POSITIVO.glob("*_positivo.png")):
        lin = pipeline.carregar(arq, para_linear=True)
        base = core.detectar_base_do_filme(lin)
        rb = float(base[0] / max(base[2], 1e-9))
        valores_positivo.append(rb)
        print(f"  {arq.name:<24} R/B medido no positivo = {rb:.2f}")
    checar(all(v < LIMITE for v in valores_positivo),
           "medir no positivo dá valor abaixo do limite (é o que causava o bug)")
    checar(any(abs(v - 1.0) < 0.35 for v in valores_positivo),
           "os valores ficam perto de 1,0 -- sinal de que a máscara não existe ali")

    # ---------------------------------------------------------------- 2
    print()
    print("=== 2) a função correta mede no NEGATIVO ===")
    rb_boa, motivo = servidor._mascara_do_negativo(cfg, "boa")
    print(f"  boa   -> R/B = {rb_boa!r}  {motivo}")
    checar(rb_boa is not None, "conseguiu medir a foto boa")
    if rb_boa is not None:
        checar(rb_boa > 1.2,
               f"a máscara da foto boa é bem alaranjada (R/B={rb_boa:.2f})")
        checar(rb_boa > max(valores_positivo),
               "o valor no negativo é MAIOR que no positivo (como deve ser)")

    rb_fraca, _ = servidor._mascara_do_negativo(cfg, "fraca")
    print(f"  fraca -> R/B = {rb_fraca!r}")
    checar(rb_fraca is not None, "conseguiu medir a foto fraca")
    if rb_fraca is not None and rb_boa is not None:
        checar(rb_fraca < rb_boa,
               f"a máscara neutra mede menos que a Kodak "
               f"({rb_fraca:.2f} < {rb_boa:.2f})")

    # ---------------------------------------------------------------- 3
    print()
    print("=== 3) a restauração NÃO pula a foto com máscara boa ===")
    # Este é o teste que o bug quebrava: com a medida errada, a foto boa era
    # pulada. Aqui interceptamos a camada HTTP para não chamar a rede.
    #
    # Baixamos `servidor.LIMITE_MASCARA` para LIMITE_SINTETICO: a máscara Kodak
    # sintética mede ~1,6, e com o limite de produção (2,5) ela seria pulada --
    # correto para filme real, mas não permitiria exercitar a lógica.
    import neg35.api as api_mod

    capturado = {"chamou": False}

    def _post_falso(url, corpo, headers, timeout):
        capturado["chamou"] = True
        raise api_mod.RestaurarErro("interceptado no teste")

    print(f"  (limite de produção {LIMITE}; usando {LIMITE_SINTETICO} neste teste)")
    original_post = api_mod._post
    original_limite = servidor.LIMITE_MASCARA
    api_mod._post = _post_falso
    servidor.LIMITE_MASCARA = LIMITE_SINTETICO
    try:
        cfg2 = config.carregar(ENV, usar_ambiente=False)
        cfg2.openrouter_api_key = "sk-or-v1-TESTE"
        res = servidor.restaurar(cfg2, ["boa"], forcar=False)
        pulados = [r for r in res["resultados"] if r.get("pulado")]
        print(f"  resultado: {res['resultados']}")
        checar(not pulados, "a foto com máscara boa NÃO foi pulada")
        checar(capturado["chamou"], "ela chegou até a chamada da IA")
    finally:
        api_mod._post = original_post
        servidor.LIMITE_MASCARA = original_limite

    # ---------------------------------------------------------------- 4
    print()
    print("=== 4) sem o DNG, não mede e NÃO pula (decisão do usuário) ===")
    fantasma = POSITIVO / "sem_origem_positivo.png"
    shutil.copy2(next(POSITIVO.glob("*_positivo.png")), fantasma)
    rb, motivo = servidor._mascara_do_negativo(cfg, "sem_origem")
    print(f"  R/B = {rb!r}  motivo: {motivo}")
    checar(rb is None, "devolveu None quando não há DNG para medir")
    checar("DNG" in motivo, f"o motivo explica a ausência: {motivo}")

    api_mod._post = _post_falso
    try:
        cfg3 = config.carregar(ENV, usar_ambiente=False)
        cfg3.openrouter_api_key = "sk-or-v1-TESTE"
        res = servidor.restaurar(cfg3, ["sem_origem"], forcar=False)
        pulados = [r for r in res["resultados"] if r.get("pulado")]
        checar(not pulados,
               "não pulou: 'não medido' é diferente de 'medido ruim'")
    finally:
        api_mod._post = original_post

    shutil.rmtree(BASE, ignore_errors=True)

    print()
    if FALHAS:
        print(f"{len(FALHAS)} verificação(ões) falharam.")
        return 1
    print("Todas as verificações passaram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
