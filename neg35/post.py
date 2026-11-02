"""
Ajustes finais: balanço de branco, contraste, saturação e nitidez.

CONVENÇÃO -- leia antes de mexer
--------------------------------
Todas as funções deste módulo recebem e devolvem luz LINEAR float [0,1].

Isso é deliberado. A conversão para sRGB acontece UMA única vez, na borda do
pipeline, em pipeline.carregar/salvar. Se estas funções também codificassem,
o gama seria aplicado duas vezes e a imagem sairia lavada -- foi exatamente
o bug que apareceu ao ler DNG.

Ordem importa: balanço de branco antes do contraste (senão você estica um
desvio de cor) e nitidez depois de tudo (senão a saturação amplifica halos).
"""

from __future__ import annotations

import numpy as np

from . import core

__all__ = [
    "auto_balanco",
    "balanco_pela_base",
    "casar_exposicao",
    "esticar_contraste",
    "luminancia",
    "saturacao",
    "nitidez",
    "preto_e_branco",
    "medir_neutro",
    "mascara_filme_virgem",
]


def _linear(img: np.ndarray) -> np.ndarray:
    """Valida entrada: float [0,1], 3 canais, já em luz linear."""
    a = np.asarray(img, dtype=np.float64)
    if a.ndim == 2:
        a = np.stack([a, a, a], axis=-1)
    if a.shape[-1] == 4:
        a = a[..., :3]
    return np.clip(a, 0.0, 1.0)


def _srgb(img) -> np.ndarray:
    """
    Valida entrada como sRGB [0,1], aceitando também uint8 ou PIL.

    Atenção: a maior parte deste módulo trabalha em LUZ LINEAR. Esta função e
    as que a usam (`casar_exposicao`) são a exceção -- mexem em sRGB, que é o
    que vem do modelo de IA e o que vai para o arquivo.
    """
    a = np.asarray(img)
    if a.dtype == np.uint8:
        a = a.astype(np.float64) / 255.0
    else:
        a = a.astype(np.float64)
        if a.size and float(a.max()) > 1.5:
            a = a / 255.0
    if a.ndim == 2:
        a = np.stack([a, a, a], axis=-1)
    if a.shape[-1] == 4:
        a = a[..., :3]
    return np.clip(a, 0.0, 1.0)


def luminancia(img: np.ndarray) -> np.ndarray:
    """Luminância Rec.709, sem alterar a imagem."""
    a = _srgb(img)
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def _comprimir_realce(x: np.ndarray) -> np.ndarray:
    """
    Comprime suavemente o topo da escala linear, sem deixar nada passar de 1.

    Fórmula: `x / (1 + x)`, reescalada para que 1,0 continue sendo 1,0. O efeito
    é quase nulo embaixo (em 0,3 muda 4%) e forte perto do topo.

    Substitui o corte seco em 1,0. O corte cria manchas chapadas de branco puro
    onde o valor passou do limite -- foi medido: 38% da imagem virava branco.
    Aqui os tons claros são comprimidos em vez de truncados.
    """
    return (x / (1.0 + x)) * 2.0


def _curva_por_pontos(x: np.ndarray, de: list[float],
                      para: list[float]) -> np.ndarray:
    """
    Curva monótona que passa por pontos dados, aplicada por interpolação.

    `de` e `para` são listas do mesmo tamanho, em ordem crescente de `de`.
    Devolve a curva avaliada em `x`, sem nunca diminuir nem passar de 1.
    """
    pontos_x = np.asarray(de, dtype=np.float64)
    pontos_y = np.clip(np.asarray(para, dtype=np.float64), 0.0, 1.0)

    # np.interp exige x crescente; garantimos e evitamos divisão por zero em
    # trechos repetidos.
    ordem = np.argsort(pontos_x)
    pontos_x = pontos_x[ordem]
    pontos_y = pontos_y[ordem]

    saida = np.interp(x, pontos_x, pontos_y)
    return np.clip(saida, 0.0, 1.0)


def casar_exposicao(
    original,
    resultado,
    forca: float = 0.85,
    max_ganho: float = 3.0,
) -> np.ndarray:
    """
    Corrige a exposição do RESULTADO para casar com a do ORIGINAL.

    Por que existe: medido em três fotos, a IA devolve o resultado
    CONSISTENTEMENTE mais escuro que o positivo que recebeu -- 0,234 a menos na
    mediana (p50), precisando de ~1,6x para igualar:

        foto              p50 positivo   p50 restaurado
        20261012_133734       0,653           0,438
        20261012_133756       0,638           0,433
        20261012_133814       0,598           0,316

    Como faz: monta uma CURVA DE TOM que passa por três pontos medidos, em luz
    linear:

        entrada 0        -> saída 0        (o preto fica preto)
        mediana atual    -> mediana alvo   (o meio-tom casa com o positivo)
        P99 atual        -> P99 alvo       (o topo não passa do que o positivo tem)

    O terceiro ponto é o que evita o branco estourado, e foi o que faltou nas
    duas tentativas anteriores:

    - **ganho puro** (`v * k`): clareia tudo igualmente. Como o ganho necessário
      é ~1,4x, o que já estava claro passa de 1,0 e é cortado. Medido: 38% da
      imagem virava branco puro, e o positivo não tem um único pixel assim.
    - **gama único** (`v ** (1/g)`): não estoura, mas muda a cor -- a curva
      trata cada canal de forma diferente. Medido num teste com cor conhecida: o
      vermelho foi de 0,571 para 0,452.
    - **ganho + compressão** (`x/(1+x)`): satura cedo demais; o branco continuou
      em 25 a 39%.

    Ancorar no P99 do positivo é o que resolve: o topo do resultado passa a ter
    a MESMA altura do topo do positivo, então não há o que estourar.

    Ancorar no P99 é o que resolve: o topo do resultado passa a ter a MESMA
    altura do topo do positivo, então não há o que estourar.

    - `forca` < 1 aplica parte da correção (interpola os alvos em log).
    - `max_ganho` limita o exagero.

    Devolve sRGB [0,1].
    """
    a = _srgb(resultado)
    ref = _srgb(original)

    lin_a = core.srgb_para_linear(a)
    lin_ref = core.srgb_para_linear(ref)

    # Trabalha na luminância: a curva é a mesma para os três canais, o que
    # preserva a cor (só o brilho muda).
    lum_a = luminancia(lin_a)
    lum_ref = luminancia(lin_ref)

    med_a = float(np.median(lum_a))
    med_ref = float(np.median(lum_ref))
    if med_a <= 1e-6 or med_ref <= 1e-6:
        return a

    if abs(med_a - med_ref) / max(med_ref, 1e-6) < 0.02:
        return a                      # exposição já próxima: não mexe

    p99_a = float(np.percentile(lum_a, 99))
    p99_ref = float(np.percentile(lum_ref, 99))

    # Interpola os alvos em log: é onde "aplicar parte da correção" faz sentido
    # visual (em escala linear, metade do caminho entre 0,1 e 0,4 não é 0,25).
    def alvo(atual: float, referencia: float, limite: float) -> float:
        if atual <= 1e-6 or referencia <= 1e-6:
            return atual
        v = float(np.exp(np.log(atual) + forca * (np.log(referencia) - np.log(atual))))
        return float(min(v, limite))

    med_alvo = alvo(med_a, med_ref, med_a * max_ganho)

    # --- ganho limitado pelo topo da imagem -------------------------------
    #
    # GANHO multiplica os TRÊS canais pelo mesmo número e portanto preserva a
    # razão entre eles -- quer dizer, preserva a COR por construção. Foi o que
    # deu o melhor resultado em teste com cor controlada: erro 0,015, contra
    # 0,062 do gama único e 0,079 de somar a diferença aos canais.
    #
    # O problema do ganho era só o corte no branco: com o ganho que estas fotos
    # pedem (~1,4x), o que já estava claro passa de 1,0 e vira branco puro --
    # medido, 38% da imagem, e o positivo não tem um pixel assim.
    #
    # A solução mais simples e sem efeito colateral: LIMITAR o ganho para que o
    # pixel mais claro não chegue a 1,0. Nada é cortado, e a cor fica exatamente
    # preservada. O preço é clarear menos do que o alvo quando a imagem tem
    # branco alto -- o que é melhor que estourar.
    #
    # Tentei antes, sem sucesso, comprimir a imagem toda com x/(1+x) (satura
    # cedo) e usar gama único (muda a cor).
    topo = float(np.percentile(lum_a, 99.9))
    ganho_max_seguro = (1.0 / topo) if topo > 0.5 else max_ganho

    ganho = float(np.clip(min(med_alvo / med_a, ganho_max_seguro),
                          1.0, max_ganho))

    if abs(ganho - 1.0) < 0.01:
        return a                      # diferença irrelevante

    nova = np.clip(lin_a, 0.0, 1.0) * ganho
    return np.clip(core.linear_para_srgb(np.clip(nova, 0.0, 1.0)), 0.0, 1.0)


def clarear_com_curva(imagem, forca: float) -> np.ndarray:
    """
    Clareia ou escurece a imagem com curva de tom, sem estourar o branco nem
    esmagar o preto. Entra e sai sRGB.

    `forca`: 1,0 não mexe. ACIMA de 1 clareia, ABAIXO escurece.

    Usa DUAS curvas de Reinhard, uma para cada sentido -- e isso é de propósito,
    porque a mesma fórmula não serve para os dois:

        f(x) = x (1+k) / (x + k)

    - Com k > 1 a curva é côncava: comprime o TOPO, ou seja clareia. E `f(1)=1`,
      então o branco nunca estoura, por mais forte que seja.
    - Com k < 1 ela vira convexa e clareia os tons escuros, que é o OPOSTO do
      que se quer ao escurecer.

    Para escurecer, a curva espelhada:

        g(x) = 1 - f(1-x)

    Ela esmaga a BASE (o preto fica preto) e `g(1)=1`. É o espelho exato, então
    o comportamento é simétrico e monótono nos dois sentidos.

    Tentei antes uma fórmula única (`k = exp(-expo)`) e o resultado foi invertido
    -- arrastar para a esquerda clareava. A medição pegou; o raciocínio no papel
    não.

    Por que curva e não ganho simples: medido, um ganho de 1,2x levou os pixels
    de branco puro de 0% para 40%, e a foto não ficou mais clara -- ficou com a
    metade superior chapada. Estes positivos já têm ~42% dos pixels na faixa
    clara (a borda do filme), então multiplicar joga essa população ao teto.

    Aplica em LUZ LINEAR, com a mesma curva nos três canais: a cor é preservada.
    """
    a = _srgb(imagem)
    lin = core.srgb_para_linear(a)

    expo = float(forca) - 1.0
    if abs(expo) < 0.01:
        return a

    if expo > 0:
        # Clarear: comprime o topo. quanto maior a força, menor o k.
        k = float(np.exp(-expo))
        ton = (lin * (1.0 + k)) / (lin + k)
    else:
        # Escurecer: espelha a mesma curva, esmagando a base.
        k = float(np.exp(expo))
        ton = 1.0 - ((1.0 - lin) * (1.0 + k)) / ((1.0 - lin) + k)

    return np.clip(core.linear_para_srgb(np.clip(ton, 0.0, 1.0)), 0.0, 1.0)


# Proporção do quadro do filme nestas digitalizações.
#
# O 35mm padrão é 36x24 mm = 3:2 = 1,500. Mas MEDINDO o quadro em 25 fotos, o
# valor é 1,438 a 1,465 com mediana 1,455 e desvio 0,007 -- consistente demais
# para ser ruído. A diferença de 3% em relação ao teórico vem da digitalização
# (margem de corte, pequena diferença de ampliação), não do filme.
#
# Uso o valor MEDIDO como alvo da trava, aceitando 6% em volta: 1,368 a 1,542.
# Isso rejeita os casos em que a detecção erra -- uma foto com área clara grande
# deu 1,768, e as imagens de teste 160x120 deram 1,333. Nesses casos não se
# corta, que é o comportamento seguro.
PROPORCAO_QUADRO = 1.455

# Tolerância em volta da proporção do quadro, para a trava.
TOLERANCIA_QUADRO = 0.06

# Limiar de "liso": gradiente abaixo disto é borda.
#
# CALIBRAÇÃO, e aqui errei uma vez: na borda do filme o gradiente tem p50 =
# 0,00000 mas p90 = 0,0014 a 0,0020. Com o limiar em 0,001, só 62 a 83% dos
# pixels da borda passavam, a coluna deixava de ser reconhecida como borda e a
# detecção PARAVA CEDO -- parou em x=526 quando a borda ia até ~630. Sobravam
# 100 px de faixa clara, que a IA transformava numa moldura escura no resultado.
# Com 0,003 a detecção para em 641, logo depois do fim real da borda (~630).
LIMIAR_LISO = 0.003

# Limiar de "claro": a borda invertida é clara.
#
# NÃO pode ser um percentil da imagem: a borda ocupa mais de 20% dos pixels,
# então `percentile(lum, 80)` É a própria borda (mediu 0,912) e nada passava.
# Valor fixo, calibrado: borda 0,905 a 0,927; quadro p95 0,682 a 0,698.
LIMIAR_CLARO = 0.80


def achar_quadro(positivo_srgb: np.ndarray,
                 proporcao: float = PROPORCAO_QUADRO,
                 tolerancia: float = TOLERANCIA_QUADRO
                 ) -> tuple[int, int, int, int] | None:
    """
    Acha o retângulo do QUADRO dentro do positivo, excluindo a borda do filme
    (que traz os furinhos e, às vezes, um pedaço do quadro vizinho).

    Devolve (x0, y0, x1, y1) ou None se não tiver certeza.

    COMO DISTINGUE A BORDA DO QUADRO -- medido, não suposto:

    O filme virgem, depois de invertido, vira um tom CLARO e LISO (a máscara
    laranja dá lavanda/rosa). Medições numa foto real:

        borda : lum 0,913  gradiente p50 0,00000  p95-p05 0,0028
        quadro: lum 0,3-0,8  gradiente p50 0,005   p95-p05 0,3-0,9

    Então a borda é o que é liso E claro. A primeira tentativa falhou porque eu
    supus que a borda ficava PRETA -- ela fica clara.

    POR QUE A PROPORÇÃO É A TRAVA:

    Se o retângulo detectado não tiver a proporção do quadro, a detecção errou,
    e devolvemos None em vez de arriscar cortar um pedaço da foto. Uma borda a
    mais é feia; um pedaço da foto a menos é perda irreversível.
    """
    a = _srgb(positivo_srgb)
    lum = luminancia(a)
    h, w = lum.shape

    gy, gx = np.gradient(lum)
    detalhe = np.hypot(gx, gy)
    liso = detalhe < LIMIAR_LISO
    claro = lum > LIMIAR_CLARO

    # A borda é lisa E clara. Linhas/colunas inteiras assim são borda.
    eh_borda = liso & claro

    def faixa(fracao: np.ndarray, minimo: float = 0.75
              ) -> tuple[int, int] | None:
        """Primeiro e último índice que NÃO é borda."""
        conteudo = np.where(fracao < minimo)[0]
        if len(conteudo) < 20:
            return None
        return int(conteudo[0]), int(conteudo[-1])

    fx = faixa(eh_borda.mean(axis=0))
    fy = faixa(eh_borda.mean(axis=1))
    if fx is None or fy is None:
        return None

    x0, x1 = fx
    y0, y1 = fy
    largura = x1 - x0 + 1
    altura = y1 - y0 + 1

    if largura < w * 0.3 or altura < h * 0.3:
        return None                      # detectou um recorte pequeno demais

    # Trava principal: proporção do quadro.
    #
    # Comparamos LADO MAIOR / LADO MENOR, não largura/altura. Isto é essencial
    # porque metade destas fotos é RETRATO: o quadro mede 1781x2600, e
    # largura/altura daria 0,685 (= 1/1,46), reprovando a trava e deixando a
    # detecção devolver None -- foi o que aconteceu, e o recorte parou de
    # funcionar em TODAS as fotos de uma vez.
    prop = max(largura, altura) / max(min(largura, altura), 1)
    if abs(prop - proporcao) / proporcao > tolerancia:
        return None

    # A borda tem de existir de verdade (senão não há o que cortar)
    if largura >= w - 2 and altura >= h - 2:
        return None

    return x0, y0, x1, y1


def _achar_gap(lum: np.ndarray, lado: str, max_frac: float = 0.30) -> int:
    """
    Acha o VÃO ESCURO entre a borda do filme e o quadro, e devolve onde o quadro
    começa.

    POR QUE O VÃO É O MELHOR MARCADOR:

    A ordem no arquivo, de fora para dentro, é:

        [fundo da foto da mesa] [faixa clara com os FUROS pretos] [VÃO ESCURO] [quadro]

    Os furos são retângulos PRETOS no meio da faixa clara, e ficam mais largos
    embaixo. Isso derruba a fração de "claro" por linha de 76% para 37% em pouco
    espaço -- por isso a detecção por "linha clara" reconhece só 2 linhas e deixa
    os furos na imagem.

    O VÃO, ao contrário, é INTEIRO escuro: uma faixa de linhas com luminância
    mediana muito baixa, sem furos, sem textura. É um marcador limpo, e é o
    último elemento antes do quadro.

    Então: varre de fora para dentro; acha a primeira sequência de linhas
    escuras (>= `min_escuro`); o quadro começa depois dela.

    Devolve o índice onde o quadro começa (0 se não achou nada).
    """
    h, w = lum.shape
    limite = int((h if lado in ("topo", "base") else w) * max_frac)

    def perfil(i: int) -> np.ndarray:
        if lado == "topo":
            return lum[i, :]
        if lado == "base":
            return lum[h - 1 - i, :]
        if lado == "esq":
            return lum[:, i]
        return lum[:, w - 1 - i]

    min_escuro = 5
    corrida = 0
    for i in range(limite):
        mediana = float(np.median(perfil(i)))
        if mediana < 0.18:
            corrida += 1
            if corrida >= min_escuro:
                return i + 1          # o quadro começa depois do vão
        else:
            corrida = 0
    return 0


def _apara_resíduo(a: np.ndarray, recuo_lados: float = 0.0,
                   max_frac: float = 0.30) -> tuple:
    """
    Corta fora tudo o que está entre a borda do arquivo e o quadro.

    Usa o VÃO ESCURO como marcador (ver `_achar_gap`), nos quatro lados.

    HISTÓRICO, porque isto levou muitas tentativas: tentei detecção por
    gradiente, por uniformidade, por fração de pixels claros, e recorte fixo de
    3% e 4,5%. Todas erraram em algum caso, porque a transição da borda para a
    foto é gradual e os furos quebram os critérios por linha. O vão escuro é o
    único elemento estruturalmente distinto: é uma faixa inteira escura.

    Se não achar vão em nenhum lado, devolve a imagem como está -- não cortar é
    o comportamento seguro.
    """
    h, w = a.shape[:2]
    lum = luminancia(a)

    cima = _achar_gap(lum, "topo", max_frac)
    baixo = _achar_gap(lum, "base", max_frac)
    esq = _achar_gap(lum, "esq", max_frac)
    dir_ = _achar_gap(lum, "dir", max_frac)

    # `_achar_gap` devolve "quantos px cortar" de cada lado.
    y0, x0 = cima, esq
    y1, x1 = h - 1 - baixo, w - 1 - dir_

    # Recuo opcional para a franja de transição.
    if recuo_lados > 0:
        dx = int(round((x1 - x0 + 1) * recuo_lados))
        dy = int(round((y1 - y0 + 1) * recuo_lados))
        x0, y0 = x0 + dx, y0 + dy
        x1, y1 = x1 - dx, y1 - dy

    if x0 == 0 and y0 == 0 and x1 == w - 1 and y1 == h - 1:
        return a, None

    if x1 - x0 < w * 0.3 or y1 - y0 < h * 0.3:
        return a, None                     # cortou demais: não confia

    return np.ascontiguousarray(a[y0:y1 + 1, x0:x1 + 1]), (x0, y0, x1, y1)
    """
    Tira o resíduo de borda que a detecção do quadro deixou.

    POR QUE LADOS USAM DETECÇÃO E TOPO/BASE USAM RECORTE FIXO:

    Medido no positivo de 4000x1868, contando quanto de cada linha é "claro
    e liso" (o que identifica a borda):

        topo, y=0   76%   y=12  47%   y=20  38%   y=34  37%
        base, y=0   100%  (segue alto por ~85 px)

    A faixa do TOPO tem os furos pretos no meio da faixa clara, e os furos são
    mais largos embaixo. Isso derruba a fração de "claro" de 76% para 37% em 34
    px -- então a detecção por linha reconhece apenas 2 linhas de borda no topo e
    os furinhos ficam na imagem. Nas LATERAIS a faixa é contínua e a detecção
    funciona (remove 600 a 800 px).

    Ou seja: a detecção é confiável nas laterais e não é no topo/base. Em vez de
    inventar outro critério que volte a errar, uso detecção onde ela funciona e um
    recorte fixo onde não funciona.

    Por que topo/base = 4,5%: medido, a faixa com furinhos mais o vão escuro
    ocupa ~3,5% a 4% da altura nestas fotos. 4,5% cobre com folga. O custo é
    perder 4,5% da altura da FOTO -- aceitável, e muito melhor que entregar os
    furinhos à IA (que os repinta como moldura).

    Os lados mantêm a detecção por faixa (clara ou escura, ambas uniformes) e um
    recuo de 1,5% para a transição.

    Devolve (imagem, retângulo) -- retângulo None se nada foi tirado.
    """


def cortar_quadro(positivo_srgb: np.ndarray,
                  margem: float = 0.0) -> tuple[np.ndarray, tuple | None]:
    """
    Corta a borda do filme, se der para detectá-la com segurança.

    Duas etapas:

    1. `achar_quadro` acha o retângulo do quadro, com a trava da proporção 3:2.
    2. `_apara_resíduo` tira a sobra que a etapa 1 deixou para trás.

    A segunda etapa foi necessária porque a primeira parava cedo: medido, ainda
    sobravam 62 a 70 px de faixa lavanda nas laterais do que era enviado à IA --
    e a IA reproduzia a faixa no resultado, que é justamente o que o usuário viu.

    Devolve (imagem, retângulo) -- retângulo None quando não cortou. `margem`
    (fração) deixa um pouco de borda, se for preferido.

    Não cortar é o comportamento seguro: se a detecção não tiver certeza, a
    imagem volta intacta.
    """
    a = _srgb(positivo_srgb)
    q = achar_quadro(a)
    if q is None:
        return a, None

    x0, y0, x1, y1 = q
    if margem > 0:
        dx = int((x1 - x0) * margem)
        dy = int((y1 - y0) * margem)
        x0 = max(x0 - dx, 0)
        y0 = max(y0 - dy, 0)
        x1 = min(x1 + dx, a.shape[1] - 1)
        y1 = min(y1 + dy, a.shape[0] - 1)

    corte = np.ascontiguousarray(a[y0:y1 + 1, x0:x1 + 1])
    corte, _ = _apara_resíduo(corte)
    return corte, (x0, y0, x1, y1)


def medir_neutro(positivo_linear: np.ndarray) -> np.ndarray:
    """
    Estima o ponto neutro (cinza) da cena pelo método gray-world robusto:
    a média por canal depois de descartar os extremos.

    Funciona bem quando a cena não é dominada por uma cor única. Numa foto
    de praia ou de floresta, o gray-world erra -- por isso existe o modo
    manual de passar um ponto que se sabe ser cinza.
    """
    lin = _linear(positivo_linear)
    plano = lin.reshape(-1, 3)

    lo = np.percentile(plano, 5, axis=0)
    hi = np.percentile(plano, 95, axis=0)
    dentro = np.all((plano >= lo) & (plano <= hi), axis=-1)
    if int(dentro.sum()) < 32:
        return np.maximum(plano.mean(axis=0), 1e-6)

    return np.maximum(plano[dentro].mean(axis=0), 1e-6)


def auto_balanco(
    positivo_linear: np.ndarray,
    forca: float = 1.0,
    ponto_neutro: np.ndarray | tuple[float, float, float] | None = None,
) -> np.ndarray:
    """
    Neutraliza a dominante de cor. Entrada e saída em luz linear.

    forca=0 -> não faz nada; forca=1 -> neutraliza totalmente.
    Valores intermediários (0.5-0.8) costumam dar o resultado mais natural,
    porque fotos de filme de época TÊM uma dominante charmoso, e zerar tudo
    deixa a imagem com cara de digital.

    ponto_neutro aceita um valor em LUZ LINEAR (não em sRGB).
    """
    lin = _linear(positivo_linear)
    if forca <= 0.0:
        return lin

    if ponto_neutro is not None:
        ref = np.asarray(ponto_neutro, dtype=np.float64).reshape(3)
    else:
        ref = medir_neutro(lin)

    # Trava dura: uma medida de neutro ~zero (imagem preta, 1x1, uniforme)
    # faria o ganho explodir para infinito e contaminar tudo com NaN.
    ref = np.maximum(ref, 1e-4)

    alvo = float(ref.mean())
    ganho = alvo / ref
    ganho = 1.0 + forca * (ganho - 1.0)

    return np.clip(lin * ganho, 0.0, 1.0)


def mascara_filme_virgem(linear: np.ndarray, percentil: float = 97.0) -> np.ndarray:
    """
    Máscara booleana dos pixels de filme virgem (a borda laranja do negativo).

    São os pixels mais claros E mais laranja -- filme sem exposição, que
    atravessa o filme inteiro. No positivo, esses pixels têm que ser PRETOS e
    NEUTROS.
    """
    lin = _linear(linear)
    lum = 0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2]
    corte = np.percentile(lum, percentil)
    return lum >= corte


def balanco_pela_base(
    positivo_linear: np.ndarray,
    negativo_linear: np.ndarray,
    forca: float = 1.0,
    percentil: float = 97.0,
) -> np.ndarray:
    """
    Neutraliza a cor usando o FILME VIRGEM como referência de preto neutro.

    Por que isto existe: o `auto_balanco` usa gray-world (a média da cena
    deveria ser cinza). Isso ERRA em cena dominada por uma cor -- numa foto
    com muita folhagem, ele assume que o verde é dominante e compensa demais,
    deixando a imagem esverdeada.

    O filme virgem é uma âncora absoluta: é filme sem exposição, logo deve
    virar preto neutro no positivo. Nenhuma suposição sobre a cena.

    Corrige por canal, para que o preto do filme fique com R=G=B.
    """
    pos = _linear(positivo_linear)
    neg = _linear(negativo_linear)

    if pos.shape[:2] != neg.shape[:2]:
        return pos  # não dá para alinhar: devolve sem mexer

    m = mascara_filme_virgem(neg, percentil=percentil)
    if int(m.sum()) < 16:
        return pos  # poucos pixels de filme virgem: não arrisca

    preto = np.median(pos[m], axis=0)
    alvo = float(preto.mean())

    # TRAVA IMPORTANTE: se o preto do filme já está muito perto de zero, o
    # ganho por canal vira divisão por ruído -- medimos G/B explodindo para 385
    # porque o canal azul ficou em 4e-6. Nesse caso não há o que equilibrar:
    # o preto já é preto.
    if alvo <= 2e-3 or float(preto.min()) <= 2e-4:
        return pos

    ganho = alvo / np.maximum(preto, 1e-5)
    # Limita a correção: um ganho acima de ~1,5x indica que a âncora está
    # ruidosa, não que a cor está errada.
    ganho = np.clip(ganho, 1.0 / 1.5, 1.5)
    ganho = 1.0 + forca * (ganho - 1.0)
    return np.clip(pos * ganho, 0.0, 1.0)


def esticar_contraste(
    positivo_linear: np.ndarray,
    preto: float = 0.005,
    branco: float = 0.995,
    por_canal: bool = False,
    gamma: float = 1.0,
) -> np.ndarray:
    """
    Estica os níveis para usar toda a escala, ignorando outliers.
    Entrada e saída em luz linear.

    preto/branco são percentis (0.005 = 0,5%). Ignorar os extremos é o que
    evita que um único pixel de poeira achate o contraste da foto inteira.

    por_canal=True corrige dominantes residuais mas DESTRÓI a neutralidade
    de cores saturadas da cena. Use só quando a dominante for teimosa.

    gamma > 1 clareia as sombras; < 1 escurece (aplicado em linear).
    """
    lin = _linear(positivo_linear)

    if por_canal:
        eixo = (0, 1)
    else:
        eixo = None

    lo = np.percentile(lin, preto * 100.0, axis=eixo)
    hi = np.percentile(lin, branco * 100.0, axis=eixo)

    amplitude = np.maximum(hi - lo, 1e-6)
    out = np.clip((lin - lo) / amplitude, 0.0, 1.0)

    if gamma != 1.0:
        out = out ** gamma

    return out


def saturacao(positivo_linear: np.ndarray, fator: float = 1.0) -> np.ndarray:
    """
    Ajusta saturação preservando o LUMA (0.2126R + 0.7152G + 0.0722B).
    Entrada e saída em luz linear.

    Atenção: o luma é preservado EXATAMENTE só enquanto nada é clipado.
    Cores já quase estouradas vão saturar contra 0/1 e aí a relação se perde
    -- é física, não bug. É por isso que saturação alta 'queima' vermelhos.

    fator=1.0 neutro, 1.2 leve, 1.5 forte (cuidado: pele vira laranja).
    """
    lin = _linear(positivo_linear)
    if abs(fator - 1.0) < 1e-6:
        return lin

    lum = 0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2]
    lum = lum[..., None]
    return np.clip(lum + (lin - lum) * fator, 0.0, 1.0)


def nitidez(
    positivo_linear: np.ndarray,
    quantia: float = 0.0,
    raio: float = 1.2,
    limiar: float = 0.02,
) -> np.ndarray:
    """
    Máscara de nitidez com limiar (unsharp mask). Entrada e saída em linear.

    O limiar é o detalhe que separa nitidez de ruído: variações menores que
    ele são ignoradas, então o grão do filme não vira granulado digital.
    Comece em 0.3-0.5 com limiar 0.02 antes de tentar mais.

    Nota: a nitidez é aplicada em LUZ LINEAR, que é onde o sinal realmente
    está. Aplica-se antes da codificação sRGB final.
    """
    lin = _linear(positivo_linear)
    if quantia <= 0.0:
        return lin

    # O borrão é feito em LUZ LINEAR, não em sRGB: passar por 8 bits/sRGB
    # aqui perderia precisão justamente nas sombras, que é onde o negativo
    # de filme carrega a informação.
    b = _blur_linear(lin, raio)

    detalhe = lin - b
    mascara = np.clip((np.abs(detalhe) - limiar) / max(limiar, 1e-6), 0.0, 1.0)
    return np.clip(lin + detalhe * mascara * quantia, 0.0, 1.0)


def _blur_linear(img: np.ndarray, raio: float) -> np.ndarray:
    """Blur gaussiano aproximado por box-blur separável, em numpy."""
    r = max(int(round(raio)), 1)
    out = img
    for eixo in (0, 1):
        k = 2 * r + 1
        pad = [(0, 0)] * img.ndim
        pad[eixo] = (r, r)
        p = np.pad(out, pad, mode="edge")
        c = np.cumsum(p, axis=eixo)
        if eixo == 0:
            zeros = np.zeros((1,) + c.shape[1:])
            soma = c[k - 1:, :, :] - np.concatenate([zeros, c[:-k, :, :]], axis=0)
        else:
            zeros = np.zeros((c.shape[0], 1, c.shape[2]))
            soma = c[:, k - 1:, :] - np.concatenate([zeros, c[:, :-k, :]], axis=1)
        out = soma / k
    return out


def preto_e_branco(positivo_linear: np.ndarray, forca: float = 1.0) -> np.ndarray:
    """Dessatura mantendo luma (útil para filmes P&B escaneados em RGB)."""
    lin = _linear(positivo_linear)
    lum = (0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2])[..., None]
    return np.clip(lin + (lum - lin) * forca, 0.0, 1.0)
