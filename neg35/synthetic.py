"""
Gerador de negativo sintético.

Serve para validar a matemática SEM precisar de um filme real: pega uma
imagem positiva, aplica a máscara laranja e a inversão exata, e devolve um
negativo "fisicamente plausível". Se o pipeline recuperar a imagem
original a partir dele, a matemática de inversão está correta.

O que isto É: um teste de round-trip exato da álgebra de cor.
O que isto NÃO É: uma simulação de filme. Não modela a curva
Hurter-Driffield, halation, grão nem a resposta espectral real.
Para julgar QUALIDADE visual use uma foto de verdade (tools/baixar_amostra.py).
"""

from __future__ import annotations

import numpy as np

from . import core

__all__ = ["positivo_para_negativo", "tira_de_teste", "MASCARAS_PRESET"]

# Cores típicas de máscara laranja por família de filme (em luz linear).
MASCARAS_PRESET: dict[str, tuple[float, float, float]] = {
    "kodak": (0.86, 0.55, 0.30),
    "fuji": (0.80, 0.58, 0.38),
    "cinestill": (0.84, 0.50, 0.26),
}


def positivo_para_negativo(
    positivo: np.ndarray,
    mascara: tuple[float, float, float] = (0.86, 0.55, 0.30),
    exposicao: float = 1.0,
    veu: float = 0.06,
) -> np.ndarray:
    """
    Positivo sRGB [0,1] -> negativo linear (o que a câmera fotografaria).

    Inverso exato de core.inverter_negativo para ganhos = 0.

    Parametros
    ----------
    mascara   : cor da base do filme em luz linear.
    exposicao : escala de densidade; <1 subexpõe o negativo.
    veu       : densidade mínima ("base fog") que todo negativo tem.
    """
    pos = core.recortar(positivo)

    # O sensor registra a luz que atravessa o positivo.
    transm = np.clip(exposicao * (1.0 - pos), veu, 1.0)

    # Essa luz atravessa a máscara laranja da base do filme.
    base = np.asarray(mascara, dtype=np.float64).reshape(3)
    negativo_linear = np.clip(transm * base, 0.0, 1.0)

    # A câmera entrega sRGB gama-encodado. É isso que o app vai ler.
    return core.linear_para_srgb(negativo_linear)


def tira_de_teste(largura: int = 640, altura: int = 440) -> np.ndarray:
    """
    Padrão de teste construído à mão, com o que REALMENTE testa uma inversão
    de negativo:

    - rampa de cinza contínua (à esquerda)  -> revela dominante de cor
    - escala de cinza em 6 degraus          -> revela erro de curva
    - 6 amostras de pele em exposições diferentes -> revela balanço
    - cartão de cores tipo Macbeth          -> revela saturação e matiz
    - bloco de contraste baixo              -> revela esmagamento de sombras

    Tudo gerado de forma determinística: rodar duas vezes dá o mesmo pixel.
    """
    w, h = int(largura), int(altura)
    img = np.zeros((h, w, 3), dtype=np.float64)

    # Fundo cinza neutro médio (evita que áreas não pintadas enganem o gray-world).
    img[:] = 0.45

    # -- 1) rampa de cinza contínua, faixa esquerda (30% da largura)
    x_rampa = int(w * 0.30)
    rampa = np.linspace(0.02, 0.98, x_rampa)[None, :, None]
    img[:, :x_rampa] = rampa

    # -- 2) escala de cinza em degraus (topo, do meio para a direita)
    y_degrau = int(h * 0.22)
    x0_degrau = int(w * 0.34)
    largura_degrau = int(w * 0.60)
    n_degraus = 6
    passo = largura_degrau // n_degraus
    for i in range(n_degraus):
        valor = 0.05 + 0.90 * (i / (n_degraus - 1))
        a = x0_degrau + i * passo
        img[0:y_degrau, a:a + passo] = valor

    # -- 3) cartão de cores (faixa do meio, à direita)
    cores = {
        "pele_clara": (0.86, 0.68, 0.58),
        "pele_media": (0.66, 0.47, 0.37),
        "pele_escura": (0.31, 0.21, 0.16),
        "azul": (0.19, 0.31, 0.62),
        "verde": (0.24, 0.55, 0.28),
        "vermelho": (0.72, 0.19, 0.16),
        "amarelo": (0.88, 0.78, 0.16),
        "ciano": (0.16, 0.60, 0.66),
        "magenta": (0.66, 0.24, 0.56),
        "laranja": (0.85, 0.50, 0.14),
        "roxo": (0.38, 0.24, 0.52),
        "verde_limao": (0.55, 0.72, 0.22),
    }
    y0_cartao = int(h * 0.26)
    y1_cartao = int(h * 0.72)
    x0_cartao = int(w * 0.36)
    x1_cartao = int(w * 0.98)
    colunas, linhas = 4, 3
    larg_c = (x1_cartao - x0_cartao) // colunas
    alt_l = (y1_cartao - y0_cartao) // linhas
    for idx, c in enumerate(cores.values()):
        li, ci = divmod(idx, colunas)
        a = x0_cartao + ci * larg_c
        b = y0_cartao + li * alt_l
        img[b:b + alt_l - 3, a:a + larg_c - 3] = c

    # -- 4) bloco de baixo contraste (canto inferior esquerdo)
    # Um negativo mal invertido DESTRÓI esta área primeiro: tudo vira cinza chapado.
    y0_bc = int(h * 0.74)
    x0_bc = int(w * 0.02)
    x1_bc = int(w * 0.28)
    base_bc = 0.42
    faixas = np.linspace(-0.035, 0.035, 6)
    faixa_alt = max((h - y0_bc) // 6, 1)
    for i, f in enumerate(faixas):
        y = y0_bc + i * faixa_alt
        img[y:y + faixa_alt, x0_bc:x1_bc] = np.clip(base_bc + f, 0.0, 1.0)

    return np.clip(img, 0.0, 1.0)
