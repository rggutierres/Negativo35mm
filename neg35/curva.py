"""
Curva de tom de exibição.

POR QUE ISSO EXISTE
-------------------
O positivo do pipeline é LUZ LINEAR da cena. Codificá-lo direto para sRGB é
tecnicamente correto, mas deixa a imagem mais clara que o natural: negativo de
filme tem densidade baixa, então a mediana fica em ~0,7-0,9 em sRGB, quando o
olho espera ~0,5. O resultado parece lavado.

UMA CURVA FIXA NÃO RESOLVE
--------------------------
Medimos duas fontes diferentes com o mesmo pipeline:

    fonte                mediana sRGB (sem curva)   gamma que a corrige
    110646 (LibRaw)                      0,701                  ~2,0
    Adobe 143104                         0,867                  ~3,2

A diferença é grande demais para um valor fixo -- ele escureceria demais uma e
de menos a outra. A causa é que o Adobe aplica a própria curva ao converter.

A SOLUÇÃO: ANCORAR A MEDIANA
----------------------------
Em vez de gama fixo, cada imagem recebe o gama que leva a mediana de luminância
para um alvo (0,50 em sRGB por padrão). Assim:

  - a MEDIANA fica igual em todas as fotos (exposição consistente);
  - a CURVA (gama) muda por foto, que é exatamente o que compensa a diferença
    de densidade entre um negativo e outro;
  - a cor não é tocada: o mesmo gama vai nos três canais.

O gama é limitado a uma faixa para não exagerar numa foto fora do comum.
"""

from __future__ import annotations

import numpy as np

from . import core

__all__ = ["luminancia", "gama_para_alvo", "aplicar", "parametros_sugeridos"]

# Faixa do gama adaptativo. Fora disso a correção costuma indicar um problema
# na captura (negativo muito sub ou superexposto), e forçar piora.
GAMMA_MIN = 1.2
GAMMA_MAX = 4.5
GAMMA_PADRAO = 2.0
ALVO_PADRAO = 0.50


def luminancia(lin: np.ndarray, amostra: int = 8) -> np.ndarray:
    """Luminância Rec.709 de uma amostra da imagem (para velocidade)."""
    a = np.asarray(lin, dtype=np.float64)
    if amostra > 1:
        a = a[::amostra, ::amostra]
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def _mediana_srgb(lin: np.ndarray, gamma: float, amostra: int = 8) -> float:
    """Mediana da luminância em sRGB, depois de aplicar o gama."""
    lum = luminancia(lin, amostra=amostra)
    lum = np.clip(lum, 0.0, 1.0) ** gamma
    return float(np.median(core.linear_para_srgb(lum)))


def gama_para_alvo(
    lin: np.ndarray,
    alvo: float = ALVO_PADRAO,
    amostra: int = 8,
    tolerancia: float = 0.002,
    max_iter: int = 24,
) -> float:
    """
    Acha o gama que leva a mediana da luminância para `alvo` (em sRGB).

    A mediana em sRGB cresce com o gama (gama maior = mais escuro = mediana
    menor), então a função é monótona e a bisseção converge rápido.
    """
    lo, hi = GAMMA_MIN, GAMMA_MAX

    # Se nem no extremo mais escuro chega ao alvo, usa o extremo.
    if _mediana_srgb(lin, hi, amostra) > alvo:
        return hi
    # Se nem no mais claro chega, usa o extremo.
    if _mediana_srgb(lin, lo, amostra) < alvo:
        return lo

    for _ in range(max_iter):
        meio = (lo + hi) / 2.0
        m = _mediana_srgb(lin, meio, amostra)
        if abs(m - alvo) <= tolerancia:
            return meio
        # mediana maior que o alvo => precisa escurecer => gama maior
        if m > alvo:
            lo = meio
        else:
            hi = meio
    return (lo + hi) / 2.0


def aplicar(
    lin: np.ndarray,
    gamma: float | None = None,
    alvo: float = ALVO_PADRAO,
    preto: float = 0.0,
) -> np.ndarray:
    """
    Aplica a curva de exibição e devolve sRGB [0,1].

    gamma=None (padrão): calcula o gama adaptativo por imagem.
    gamma=<valor>: usa esse gama fixo.

    preto > 0 levanta o ponto preto (útil quando o negativo tem véu de base).
    O MESMO gama vai nos três canais, então a cor não é alterada.
    """
    a = np.asarray(lin, dtype=np.float64)
    if a.ndim == 2:
        a = np.stack([a, a, a], axis=-1)
    if a.shape[-1] == 4:
        a = a[..., :3]
    a = np.clip(a, 0.0, 1.0)

    if preto > 0.0:
        a = np.clip((a - preto) / max(1.0 - preto, 1e-6), 0.0, 1.0)

    g = gamma if gamma is not None else gama_para_alvo(a, alvo=alvo)
    return core.linear_para_srgb(a ** g)


def parametros_sugeridos(lin: np.ndarray, alvo: float = ALVO_PADRAO) -> dict:
    """Diagnóstico: qual gama seria usado e onde a mediana fica."""
    g = gama_para_alvo(lin, alvo=alvo)
    return {
        "gamma": g,
        "mediana_sem_curva": float(np.median(core.linear_para_srgb(luminancia(lin)))),
        "mediana_com_curva": _mediana_srgb(lin, g),
        "alvo": alvo,
    }
