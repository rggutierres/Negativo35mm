"""
Núcleo colorimétrico: espaço linear, detecção da máscara laranja, inversão.

Regra de ouro deste módulo
--------------------------
NUNCA inverta um negativo em sRGB. O negativo responde de forma LINEAR e
carrega uma máscara laranja. Inverter gama-encodado produz contraste
esmagado e dominante ciano. Toda a matemática acontece em luz linear;
a codificação sRGB só entra no último passo.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "srgb_para_linear",
    "linear_para_srgb",
    "para_float",
    "normalizar",
    "recortar",
    "detectar_base_do_filme",
    "inverter_negativo",
    "GANHOS_POR_FILME",
]

# Ganhos iniciais por tipo de filme, em "stops" (2**ganho aplicado por canal).
# São só um PONTO DE PARTIDA: o ajuste fino automático (post.auto_balanco)
# parte daqui e corrige. Valores herdados da prática de escaneamento.
GANHOS_POR_FILME: dict[str, tuple[float, float, float]] = {
    "generico": (0.00, 0.00, 0.00),
    "gold200": (-0.10, 0.00, 0.18),   # Kodak Gold: tons quentes
    "portra400": (-0.06, 0.00, 0.12),  # Portra: pele contida, leve quente
    "ektar100": (-0.16, 0.00, 0.28),   # Ektar: muito saturado, azul profundo
    "ultramax400": (-0.12, 0.00, 0.20),
    "superia400": (-0.08, -0.02, 0.22),  # Fuji: verde/ciano característico
    "cinestill800t": (-0.05, 0.00, 0.25),
    "hp5": (0.00, 0.00, 0.00),         # P&B: sem máscara, ganhos neutros
    "tri-x400": (0.00, 0.00, 0.00),
    "pretoebranco": (0.00, 0.00, 0.00),
}


# --------------------------------------------------------------------------
# Espaços de cor
# --------------------------------------------------------------------------
def srgb_para_linear(x: np.ndarray) -> np.ndarray:
    """Converte sRGB [0,1] -> luz linear [0,1] (função EOTF do sRGB)."""
    x = np.asarray(x, dtype=np.float64)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def linear_para_srgb(x: np.ndarray) -> np.ndarray:
    """Converte luz linear [0,1] -> sRGB [0,1] (função OETF do sRGB)."""
    x = np.clip(np.asarray(x, dtype=np.float64), 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * x ** (1.0 / 2.4) - 0.055)


# --------------------------------------------------------------------------
# Utilidades de array
# --------------------------------------------------------------------------
def para_float(img: np.ndarray) -> np.ndarray:
    """uint8/uint16/float -> float64 no intervalo [0,1]."""
    a = np.asarray(img)
    if a.dtype == np.uint8:
        return a.astype(np.float64) / 255.0
    if a.dtype == np.uint16:
        return a.astype(np.float64) / 65535.0
    if np.issubdtype(a.dtype, np.floating):
        f = a.astype(np.float64)
        # Se veio em escala 0..255, normaliza; se já está em 0..1, mantém.
        return f / 255.0 if f.max() > 1.5 else f
    return a.astype(np.float64) / np.iinfo(a.dtype).max


def normalizar(
    img: np.ndarray,
    linear: bool = False,
) -> np.ndarray:
    """
    Traz QUALQUER entrada para luz linear float [0,1] -- UMA única vez.

    Este é o ponto mais delicado do pipeline, e a origem do bug mais caro
    que já apareceu aqui.

    linear=False (padrão): a entrada é sRGB (JPEG/PNG de câmera). Aplica a
        decodificação de gama.
    linear=True: a entrada JÁ é luz linear (saída do rawpy/LibRaw, TIFF
        linear). NÃO aplica gama.

    Por que isso importa: aplicar srgb_para_linear sobre dados que já estão
    lineares ENCOLHE tudo ~3,3x na média. A máscara laranja, que era
    R/B=4,2, vira R/B=1,1 -- indistinguível de cinza -- e a inversão sai
    lavada, com o branco estourado. Foi exatamente o sintoma que apareceu
    ao ler DNG com rawpy.
    """
    a = np.asarray(img)

    if np.issubdtype(a.dtype, np.integer):
        if a.dtype == np.bool_:
            a = a.astype(np.float64)
        else:
            a = a.astype(np.float64) / float(np.iinfo(a.dtype).max)
    else:
        a = a.astype(np.float64)
        if a.size and float(a.max()) > 1.5:
            a = a / 255.0

    # Garante [0,1] antes da decodificação de gama.
    a = np.clip(a, 0.0, 1.0)

    if not linear:
        a = srgb_para_linear(a)

    return a


def recortar(img: np.ndarray) -> np.ndarray:
    """
    Garante R,G,B float64 em [0,1]; remove canal alfa se existir.

    Aceita QUALQUER entrada e normaliza uma única vez, assumindo entrada
    sRGB. Para dados já lineares use normalizar(img, linear=True).
    """
    a = normalizar(img, linear=False)

    if a.ndim == 2:
        a = np.stack([a, a, a], axis=-1)
    if a.shape[-1] == 4:
        a = a[..., :3]

    return np.clip(a, 0.0, 1.0)


def _media_robusta(regiao: np.ndarray) -> np.ndarray:
    """Média por canal descartando 10% de cada extremo (evita grão e defeitos)."""
    plano = regiao.reshape(-1, regiao.shape[-1])
    lo = np.percentile(plano, 10, axis=0)
    hi = np.percentile(plano, 90, axis=0)
    dentro = np.all((plano >= lo) & (plano <= hi), axis=-1)
    if not np.any(dentro):
        return plano.mean(axis=0)
    return plano[dentro].mean(axis=0)


# --------------------------------------------------------------------------
# Detecção da base do filme (a área laranja sem exposição)
# --------------------------------------------------------------------------
def detectar_base_do_filme(
    linear: np.ndarray,
    fracao: float = 0.08,
) -> np.ndarray:
    """
    Estima a cor da máscara laranja: o filme virgem, que é a região mais
    CLARA do negativo.

    Estratégia: para cada canal, pega o percentil alto; a partir daí isola
    os pixels claros e tira uma média robusta. Assim uma partícula de poeira
    branca ou um trecho de moldura não sequestra a estimativa.

    Retorna um vetor de 3 valores em luz linear. Este é o parâmetro mais
    sensível de todo o pipeline -- se a base estiver errada, o balanço de
    branco inteiro sai errado.
    """
    # Entrada é luz LINEAR: não pode passar por recortar(), que aplicaria
    # a decodificação de gama e encolheria a máscara laranja.
    a = np.asarray(linear, dtype=np.float64)
    if a.ndim == 2:
        a = np.stack([a, a, a], axis=-1)
    if a.shape[-1] == 4:
        a = a[..., :3]
    lin = np.clip(a, 0.0, 1.0)
    plano = lin.reshape(-1, 3)

    # Percentil alto por canal = candidatos a filme virgem.
    corte = np.percentile(plano, (1.0 - fracao) * 100.0, axis=0)
    candidatos = plano[np.all(plano >= corte * 0.92, axis=-1)]

    if candidatos.shape[0] < 32:
        # Imagem pequena ou pouquíssima área clara: cai para o percentil puro.
        return np.percentile(plano, 99.0, axis=0)

    base = _media_robusta(candidatos.reshape(1, -1, 3)).reshape(3)

    # Trava de segurança: a máscara laranja sempre tem R > G > B.
    # Se a estimativa violar isso, a cena não tinha filme virgem visível.
    if not (base[0] >= base[1] >= base[2] and base[2] > 1e-4):
        base = np.percentile(plano, 99.0, axis=0)

    # Evita divisão por ~zero em canal estourado.
    return np.maximum(base, 1e-4)


# --------------------------------------------------------------------------
# Inversão
# --------------------------------------------------------------------------
def inverter_negativo(
    linear: np.ndarray,
    base_filme: np.ndarray | None = None,
    ganhos: tuple[float, float, float] | np.ndarray = (0.0, 0.0, 0.0),
    forcar_neutro: bool = True,
    recorte_branco: float = 0.0,
) -> np.ndarray:
    """
    Negativo LINEAR -> positivo LINEAR. A máscara laranja é removida por
    DIVISÃO (normalização pela base), não por subtração.

    A entrada precisa ser luz linear. Se você tem um JPEG, decodifique antes
    com core.normalizar(img, linear=False).

    Passos
    ------
    1. Normaliza cada canal pela base do filme.
    2. Escala para cinza ~1.0 no canal mais escuro (evita clipar tudo).
    3. Aplica ganhos por canal (correção fina de temperatura).
    4. Inverte:  positivo = 1 - transmitância.
    5. Re-escala por recorte_branco, que controla o quão rápido o branco
       satura (0.0 = sem re-escala).

    Devolve luz linear [0,1] já em positivo.
    """
    # Aqui a entrada JÁ é linear: não passa por recortar, que aplicaria gama.
    lin = np.asarray(linear, dtype=np.float64)
    if lin.ndim == 2:
        lin = np.stack([lin, lin, lin], axis=-1)
    if lin.shape[-1] == 4:
        lin = lin[..., :3]
    lin = np.clip(lin, 0.0, 1.0)

    if base_filme is None:
        base_filme = detectar_base_do_filme(lin)

    base = np.maximum(np.asarray(base_filme, dtype=np.float64).reshape(3), 1e-4)

    # 1) tira o laranja
    t = lin / base

    # 2) Compressão de branco, POR CANAL.
    #
    # O filme virgem é a parte mais clara do negativo, mas cenas com fonte de
    # luz direta podem ser MAIS claras que ele. Se normalizarmos pelo máximo
    # global, qualquer pixel desses satura e o "branco" estoura -- a imagem
    # inteira lava.
    #
    # Em vez disso, tomamos o filme virgem como um branco conhecido: 0.90.
    # Assim:
    #   - o que for igual à base vira 0.90 (o valor onde a curva começa a
    #     comprimir, deixando ~10% de folga para a luz direta);
    #   - o que estiver acima é espremido em 0.90..1.0 com uma função
    #     logarítmica (ombro de destaque), preservando separação;
    #   - abaixo disso é escala linear, sem perda nenhuma de sombra.
    #
    # Isto é um "shoulder" (ombro) de curva de filme de verdade. Foi o que
    # corrigiu o positivo lavado dos DNG reconvertidos pelo Adobe, onde o
    # normalização pelo máximo global queimava tudo.
    if forcar_neutro:
        t = np.clip(t, 0.0, None)
        ombro_inicio = 0.90
        excesso = np.maximum(t - ombro_inicio, 0.0)
        comprimido = ombro_inicio + (1.0 - ombro_inicio) * (
            1.0 - np.exp(-excesso / max(1.0 - ombro_inicio, 1e-6))
        )
        t = np.where(t > ombro_inicio, comprimido, t)

    # 3) temperatura fina por canal
    g = np.asarray(ganhos, dtype=np.float64).reshape(3)
    t = t * (2.0 ** g)

    # 4) densidade -> luz
    pos = 1.0 - t

    # 5) controle de saturação do branco
    if recorte_branco > 0.0:
        pos = pos / (1.0 - recorte_branco)

    return np.clip(pos, 0.0, 1.0)
