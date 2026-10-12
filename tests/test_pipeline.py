"""
Testes do núcleo. Só precisa de numpy + Pillow.

    python tests/test_pipeline.py
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from neg35 import core, pipeline, post, synthetic  # noqa: E402

D65 = np.array([0.95047, 1.0, 1.08883])


class Falha(AssertionError):
    pass


def verificar(cond: bool, msg: str) -> None:
    if not cond:
        raise Falha(msg)


# ----------------------------------------------------------------------
def teste_srgb_round_trip() -> None:
    x = np.linspace(0.0, 1.0, 1001)
    ida = core.srgb_para_linear(core.linear_para_srgb(x))
    erro = float(np.abs(ida - x).max())
    verificar(erro < 1e-9, f"sRGB round-trip errou {erro:.2e}")
    print(f"  ok  sRGB round-trip (erro máx {erro:.1e})")


def teste_primeiro_linear() -> None:
    verificar(abs(core.srgb_para_linear(0.0)) < 1e-12, "linear(0) != 0")
    verificar(abs(core.srgb_para_linear(1.0) - 1.0) < 1e-12, "linear(1) != 1")
    meio = float(core.srgb_para_linear(0.5))
    verificar(abs(meio - 0.2140) < 1e-3, f"linear(0.5) = {meio:.4f}, esperado ~0.2140")
    print(f"  ok  sRGB 0.5 -> linear {meio:.4f}")


def teste_round_trip_negativo() -> None:
    """
    A foto original deve voltar quando o negativo sintético é invertido.

    Comparamos em LUZ LINEAR, que é o espaço em que o pipeline agora
    trabalha internamente. Comparar linear contra sRGB daria um erro enorme
    e falso (medimos 57 níveis quando fizemos isso por engano).
    """
    original = synthetic.tira_de_teste()
    alvo = core.normalizar(original, linear=False)
    piores: list[tuple[str, float]] = []

    for nome, mascara in synthetic.MASCARAS_PRESET.items():
        for expo in (0.7, 1.0):
            negativo = synthetic.positivo_para_negativo(original, mascara=mascara, exposicao=expo)
            res = pipeline.desenvolver(
                negativo,
                pipeline.Parametros(
                    filme="generico",
                    saturacao=1.0,
                    nitidez=0.0,
                    balanco_forca=1.0,
                ),
            )
            erro = float(np.abs(res.positivo - alvo).mean() * 255.0)
            piores.append((f"{nome}/expo{expo}", erro))
            verificar(
                erro < 12.0,
                f"round-trip {nome} expo={expo}: erro médio {erro:.1f} níveis (esperado <12)",
            )

    pior = max(piores, key=lambda t: t[1])
    print(f"  ok  round-trip negativo em linear (pior caso: {pior[0]} = {pior[1]:.1f} níveis)")


def teste_base_detectada() -> None:
    """A máscara estimada deve bater com a real, dentro de ~15%."""
    for nome, mascara in synthetic.MASCARAS_PRESET.items():
        negativo = synthetic.positivo_para_negativo(synthetic.tira_de_teste(), mascara=mascara)
        lin = core.srgb_para_linear(negativo)
        base = core.detectar_base_do_filme(lin)
        real = np.asarray(mascara)
        # Compara a FORMA da máscara, não a escala absoluta (a exposição muda a escala).
        forma_est = base / base[1]
        forma_real = real / real[1]
        erro = float(np.abs(forma_est - forma_real).max())
        verificar(
            erro < 0.15,
            f"base {nome}: forma estimada {forma_est.round(3)} vs real {forma_real.round(3)} "
            f"(erro {erro:.3f})",
        )
    print("  ok  detecção da base do filme (<15% de forma)")


def teste_base_precisa_da_borda() -> None:
    """Sem filme virgem visível, a detecção ainda não pode explodir."""
    negativo = synthetic.positivo_para_negativo(synthetic.tira_de_teste())
    corte = negativo[40:-40, 40:-40]          # remove a borda
    lin = core.srgb_para_linear(corte)
    base = core.detectar_base_do_filme(lin)
    verificar(np.all(np.isfinite(base)), "base contém NaN/inf")
    verificar(np.all(base > 0), f"base não positiva: {base}")
    verificar(base[0] >= base[2], f"base sem máscara laranja: {base}")
    print(f"  ok  base sem borda = {base.round(3)}")


def teste_preto_e_branco() -> None:
    img = np.zeros((32, 32, 3))
    img[:16] = 0.15
    img[16:] = 0.85
    out = post.preto_e_branco(img, 1.0)
    espalhamento = float(np.abs(out[..., 0] - out[..., 1]).max())
    verificar(espalhamento < 1e-9, f"P&B deixou diferença entre canais: {espalhamento:.2e}")
    print("  ok  conversão P&B")


def teste_saturacao_preserva_luminancia() -> None:
    """
    O luma deve ser preservado EXATAMENTE enquanto nada clipa.
    A tira de teste tem brancos puros, que clipam por física -- então aqui
    usamos uma cena contida, e o clipping é testado à parte.
    """
    img = np.full((64, 64, 3), 0.5)
    img[32:48] = (0.60, 0.45, 0.40)   # pele contida
    img[48:56] = (0.30, 0.35, 0.55)   # azul contido

    def lum(x):
        return 0.2126 * x[..., 0] + 0.7152 * x[..., 1] + 0.0722 * x[..., 2]

    for fator in (0.6, 1.0, 1.25):
        depois = post.saturacao(img, fator)
        erro = float(np.abs(lum(img) - lum(depois)).max())
        verificar(erro < 1e-9, f"saturação {fator} mudou o luma em {erro:.2e}")

    print("  ok  saturação preserva luma (sem clipping)")


def teste_saturacao_com_clipping_e_finita() -> None:
    """Saturação alta não pode gerar NaN/inf mesmo estourando os canais."""
    img = synthetic.tira_de_teste()
    for fator in (1.5, 2.5, 4.0):
        out = post.saturacao(img, fator)
        verificar(np.all(np.isfinite(out)), f"saturação {fator} gerou NaN/inf")
        verificar(out.min() >= 0.0 and out.max() <= 1.0, f"saturação {fator} saiu de [0,1]")
    print("  ok  saturação alta permanece finita e em [0,1]")


def teste_balanco_neutraliza_dominante() -> None:
    """Empurra a imagem para azul e verifica que o balanço traz de volta."""
    img = synthetic.tira_de_teste()
    azulado = np.clip(img * np.array([0.82, 0.94, 1.18]), 0.0, 1.0)

    antes = post.medir_neutro(azulado)
    depois = post.medir_neutro(post.auto_balanco(azulado, forca=1.0))

    def espalhamento(v):
        return float(v.max() / max(v.min(), 1e-9))

    e_antes, e_depois = espalhamento(antes), espalhamento(depois)
    verificar(e_depois < e_antes, f"balanço não melhorou: {e_antes:.3f} -> {e_depois:.3f}")
    verificar(e_depois < 1.10, f"balanço insuficiente: desvio residual {e_depois:.3f}")
    print(f"  ok  balanço de branco (desvio {e_antes:.3f} -> {e_depois:.3f})")


def teste_contraste_usa_escala() -> None:
    img = np.full((64, 64, 3), 0.45)
    img[:32] = 0.35
    img[32:] = 0.55
    out = post.esticar_contraste(img, preto=0.005, branco=0.995)
    verificar(out.min() < 0.02, f"preto não chegou ao fundo: {out.min():.4f}")
    verificar(out.max() > 0.98, f"branco não chegou ao topo: {out.max():.4f}")
    print(f"  ok  contraste usa a escala ({out.min():.3f} .. {out.max():.3f})")


def teste_nitidez_nao_muda_plano() -> None:
    """Numa área uniforme a nitidez não pode criar textura."""
    img = np.full((64, 64, 3), 0.5)
    out = post.nitidez(img, quantia=1.0, raio=2.0, limiar=0.02)
    erro = float(np.abs(out - img).max())
    verificar(erro < 1e-9, f"nitidez alterou área plana em {erro:.2e}")
    print("  ok  nitidez preserva área plana (limiar funciona)")


def teste_recortar_normaliza_uma_vez() -> None:
    """
    REGRESSÃO: normalização dupla de uint8 produzia imagens brancas.

    recortar() assume sRGB e aplica a decodificação de gama (uma vez).
    normalizar(linear=True) NÃO aplica gama -- é para dados já lineares.
    """
    for valor in (0, 1, 37, 128, 141, 200, 255):
        a = np.full((4, 5, 3), valor, dtype=np.uint8)

        # Caminho sRGB: decodifica o gama exatamente uma vez.
        r = core.recortar(a)
        esperado = float(core.srgb_para_linear(np.array([valor / 255.0]))[0])
        verificar(
            abs(float(r.mean()) - esperado) < 1e-9,
            f"recortar(uint8 {valor}) = {r.mean():.5f}, esperado {esperado:.5f}",
        )

        # Caminho linear: escala linear, SEM gama. É isto que o DNG usa.
        n = core.normalizar(a, linear=True)
        verificar(
            abs(float(n.mean()) - valor / 255.0) < 1e-9,
            f"normalizar(uint8 {valor}, linear) = {n.mean():.5f}, "
            f"esperado {valor/255:.5f}",
        )

    # uint16 nos dois caminhos.
    b = np.full((4, 4, 3), 32768, dtype=np.uint16)
    verificar(
        abs(float(core.normalizar(b, linear=True).mean()) - 32768 / 65535) < 1e-6,
        "normalizar(uint16, linear) errado",
    )
    # float em escala 0..255 e em escala 0..1
    c = np.full((4, 4, 3), 141.0)
    verificar(
        abs(float(core.normalizar(c, linear=True).mean()) - 141 / 255) < 1e-9,
        "normalizar(float 0..255, linear) errado",
    )
    d = np.full((4, 4, 3), 0.553)
    verificar(
        abs(float(core.normalizar(d, linear=True).mean()) - 0.553) < 1e-9,
        "normalizar(float 0..1, linear) errado",
    )

    print("  ok  normalização única nos dois caminhos (sRGB e linear)")


def teste_linear_nao_recebe_gama() -> None:
    """
    REGRESSÃO CARA: aplicar srgb_para_linear sobre dados que JÁ são lineares
    estraga a DETECÇÃO DA BASE e lava a imagem. Foi este o bug que fez o
    positivo do DNG sair péssimo enquanto o do JPG saía razoável.

    Detalhe que confunde: o gama NÃO achata a razão R/B de uma cor isolada
    (aplicar x^(1/2.4) nos dois canais preserva a razão). O que ele estraga
    é a ESTATÍSTICA: o percentil alto é calculado sobre valores esticados
    de forma não uniforme, então a base estimada sai errada.
    """
    # Cena sintética em luz linear, com máscara laranja e conteúdo variado.
    rng = np.random.default_rng(3)
    lin = np.zeros((64, 64, 3))
    lin[..., 0] = 0.20 + 0.45 * rng.random((64, 64))
    lin[..., 1] = 0.10 + 0.25 * rng.random((64, 64))
    lin[..., 2] = 0.04 + 0.12 * rng.random((64, 64))

    # Caminho certo: sem gama.
    certo = core.normalizar(lin, linear=True)
    verificar(
        float(np.abs(certo - lin).max()) < 1e-12,
        "normalizar(linear=True) alterou os valores",
    )

    # Caminho errado: gama aplicado sobre dados já lineares.
    errado = core.normalizar(lin, linear=False)
    encolheu = float(lin.mean() / max(errado.mean(), 1e-9))
    verificar(
        encolheu > 2.0,
        f"o caminho errado deveria encolher os valores; encolheu {encolheu:.2f}x",
    )

    # O que importa: a base detectada por cada caminho.
    b_certo = core.detectar_base_do_filme(certo)
    b_errado = core.detectar_base_do_filme(errado)
    desvio = float(np.abs(b_certo / b_certo[2] - b_errado / b_errado[2]).max())
    verificar(
        desvio > 0.5,
        f"esperava base bem diferente entre os caminhos; forma difere só {desvio:.2f}",
    )

    print(f"  ok  gama não é aplicado em linear "
          f"(base certa {b_certo.round(3)} vs errada {b_errado.round(3)})")


def teste_render_nao_branqueia() -> None:
    """REGRESSÃO: compositores devolviam imagem ~toda branca."""
    from neg35 import render

    padrao = synthetic.tira_de_teste(largura=200, altura=140)

    # O padrão sintético é sRGB -> passa ja_srgb=True.
    u8 = render.para_u8_srgb(padrao, ja_srgb=True)
    verificar(u8.dtype == np.uint8, "para_u8_srgb não devolve uint8")
    erro = float(np.abs(u8.astype(np.float64) / 255.0 - padrao).max())
    verificar(erro <= 1.5 / 255.0, f"para_u8_srgb deformou em {erro * 255:.2f} níveis")

    branqueado = float((u8.min(axis=-1) > 250).mean())
    verificar(branqueado < 0.05, f"para_u8_srgb branqueou {branqueado:.1%} da imagem")

    comp = render.lado_a_lado(padrao, 1.0 - padrao, ja_srgb=True)
    frac_branca = float((comp.min(axis=-1) > 250).mean())
    verificar(
        frac_branca < 0.10,
        f"lado_a_lado ficou {frac_branca:.1%} branco (esperado <10%)",
    )

    tira = render.tira_de_etapas(
        {"a": padrao, "b": 1.0 - padrao, "c": padrao}, ja_srgb=True
    )
    frac_branca_tira = float((tira.min(axis=-1) > 250).mean())
    verificar(
        frac_branca_tira < 0.10,
        f"tira_de_etapas ficou {frac_branca_tira:.1%} branca",
    )

    print("  ok  render não branqueia (lado_a_lado e tira_de_etapas)")


def teste_render_codifica_linear_uma_vez() -> None:
    """
    REGRESSÃO: aplicar a codificação sRGB duas vezes lava a imagem.

    Um cinza linear de 0.2 deve virar ~0.48 em sRGB. Se alguém codificar de
    novo, vira ~0.73 e a imagem clareia.
    """
    from neg35 import render

    lin = np.full((16, 16, 3), 0.2)          # luz linear
    s = render.para_u8_srgb(lin, ja_srgb=False)
    esperado = core.linear_para_srgb(np.array([0.2]))[0]
    obtido = float(s.mean()) / 255.0
    verificar(
        abs(obtido - esperado) < 2 / 255.0,
        f"codificação sRGB errada: {obtido:.3f} vs esperado {esperado:.3f}",
    )
    # Codificar duas vezes teria dado ~0.73; garante que não aconteceu.
    verificar(obtido < 0.60, f"parece codificação dupla: {obtido:.3f}")

    # Entrada uint8 sRGB passa direto, sem recodificar.
    u8 = (lin * 255).astype(np.uint8)
    ida = render.para_u8_srgb(u8, ja_srgb=True)
    verificar(np.array_equal(ida, u8), "uint8 sRGB foi alterado")

    print(f"  ok  render codifica sRGB uma vez (0.2 linear -> {obtido:.3f})")


def teste_salvar_preserva_linear() -> None:
    """
    Salvar e reler deve preservar os valores de LUZ LINEAR.

    Idas e voltas de gama acumulam erro: é justamente esse acúmulo que
    deixa a imagem lavada em pipelines longos. Aqui garantimos que a
    codificação/decodificação sRGB é exata (dentro do arredondamento 8 bits).
    """
    import shutil
    from pathlib import Path

    padrao = synthetic.tira_de_teste(largura=120, altura=90)
    # O padrão é sRGB; passamos para linear, que é o que o pipeline usa.
    lin = core.normalizar(padrao, linear=False)

    tmp = Path(__file__).resolve().parent / "_tmp_saida"
    try:
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True, exist_ok=True)
        destino = tmp / "t.png"
        pipeline.salvar(lin, destino, linear=True)
        lido = pipeline.carregar(destino, para_linear=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    erro = float(np.abs(lido - lin).max() * 255.0)
    verificar(erro <= 3.0, f"ida-e-volta linear deformou {erro:.2f} níveis")
    print(f"  ok  salvar/carregar preserva o linear (erro máx {erro:.2f} níveis)")


def teste_ganhos_por_filme_sao_validos() -> None:
    for nome, ganhos in core.GANHOS_POR_FILME.items():
        verificar(len(ganhos) == 3, f"{nome}: ganhos não tem 3 canais")
        verificar(
            all(-2.0 < g < 2.0 for g in ganhos),
            f"{nome}: ganho fora de faixa plausível {ganhos}",
        )
    print(f"  ok  {len(core.GANHOS_POR_FILME)} presets de filme válidos")


def teste_imagem_pequena_nao_quebra() -> None:
    """Robustez: imagens minúsculas, uniformes e extremas não podem gerar NaN."""
    casos = []
    for n in (1, 2, 3, 8):
        for valor in (0.0, 0.5, 1.0):
            casos.append((f"{n}x{n} valor {valor}", np.full((n, n, 3), valor)))

    # Também uma imagem degenerada com aleatoriedade extrema.
    rng = np.random.default_rng(7)
    casos.append(("4x4 aleatório", rng.random((4, 4, 3))))

    for nome, img in casos:
        res = pipeline.desenvolver(
            img, pipeline.Parametros(saturacao=1.0, nitidez=0.0), manter_etapas=False
        )
        verificar(np.all(np.isfinite(res.positivo)), f"{nome} gerou NaN/inf")
        verificar(
            res.positivo.min() >= 0.0 and res.positivo.max() <= 1.0,
            f"{nome} saiu de [0,1]",
        )
    print(f"  ok  {len(casos)} casos degenerados não quebram")


def teste_aviso_subexposicao() -> None:
    """Negativo escuro demais deve AVISAR, não fingir que deu certo."""
    escuro = np.full((64, 64, 3), 0.05)
    res = pipeline.desenvolver(
        escuro, pipeline.Parametros(saturacao=1.0, nitidez=0.0), manter_etapas=False
    )
    verificar("aviso" in res.meta, "negativo subexposto não gerou aviso")
    print(f"  ok  aviso de subexposição: {res.meta['aviso'][:52]}...")


# ----------------------------------------------------------------------
def main() -> int:
    testes = [
        teste_srgb_round_trip,
        teste_primeiro_linear,
        teste_round_trip_negativo,
        teste_base_detectada,
        teste_base_precisa_da_borda,
        teste_preto_e_branco,
        teste_saturacao_preserva_luminancia,
        teste_saturacao_com_clipping_e_finita,
        teste_balanco_neutraliza_dominante,
        teste_contraste_usa_escala,
        teste_nitidez_nao_muda_plano,
        teste_recortar_normaliza_uma_vez,
        teste_linear_nao_recebe_gama,
        teste_render_nao_branqueia,
        teste_render_codifica_linear_uma_vez,
        teste_salvar_preserva_linear,
        teste_ganhos_por_filme_sao_validos,
        teste_imagem_pequena_nao_quebra,
        teste_aviso_subexposicao,
    ]

    falhas = 0
    for t in testes:
        print(f"{t.__name__}")
        try:
            t()
        except Exception as e:  # noqa: BLE001
            falhas += 1
            print(f"  FALHOU: {e}")
            traceback.print_exc()

    print()
    if falhas:
        print(f"{falhas} de {len(testes)} testes FALHARAM")
        return 1
    print(f"Todos os {len(testes)} testes passaram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
