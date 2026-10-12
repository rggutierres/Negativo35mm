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
    "esticar_contraste",
    "saturacao",
    "nitidez",
    "preto_e_branco",
    "medir_neutro",
]


def _linear(img: np.ndarray) -> np.ndarray:
    """Valida entrada: float [0,1], 3 canais, já em luz linear."""
    a = np.asarray(img, dtype=np.float64)
    if a.ndim == 2:
        a = np.stack([a, a, a], axis=-1)
    if a.shape[-1] == 4:
        a = a[..., :3]
    return np.clip(a, 0.0, 1.0)


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
