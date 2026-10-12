"""
Montagem de imagens de diagnóstico: antes/depois e etapas do pipeline.

CONVENÇÃO DE GAMA
-----------------
Todas as funções daqui recebem e devolvem imagens em LUZ LINEAR e devolvem
uint8 sRGB prontos para salvar com pipeline.salvar(..., linear=False).

Motivo: o pipeline inteiro trabalha em linear, então os valores que chegam
das etapas (res.etapas, res.final) já estão em linear. Codificar aqui e
salvar sem recodificar evita aplicar gama duas vezes -- que foi a causa de
imagens lavadas.

Se você tiver dados que JÁ estão em sRGB (uma foto lida com carregar(
para_linear=False), por exemplo), passe ja_srgb=True.
"""

from __future__ import annotations

import numpy as np

from . import core

__all__ = ["lado_a_lado", "tira_de_etapas", "ampliar", "rotular_faixa", "para_u8_srgb"]


def para_u8_srgb(img: np.ndarray, ja_srgb: bool = False) -> np.ndarray:
    """
    Converte qualquer imagem para uint8 sRGB, codificando UMA única vez.

    ja_srgb=False (padrão): a entrada é luz linear; aplica a codificação sRGB.
    ja_srgb=True: a entrada já é sRGB; apenas quantiza para uint8.

    É idempotente na prática: passar uint8 sRGB com ja_srgb=True devolve o
    mesmo uint8. Foi a falta dessa idempotência que já gerou imagens brancas.
    """
    a = np.asarray(img)
    if a.ndim == 2:
        a = np.stack([a, a, a], axis=-1)
    if a.shape[-1] == 4:
        a = a[..., :3]

    if a.dtype == np.uint8:
        return np.ascontiguousarray(a)

    if a.dtype == np.uint16:
        f = a.astype(np.float64) / 65535.0
    else:
        f = a.astype(np.float64)
        if f.size and float(f.max()) > 1.5:
            f = f / 255.0

    f = np.clip(f, 0.0, 1.0)
    if not ja_srgb:
        f = core.linear_para_srgb(f)
    return (f * 255.0 + 0.5).astype(np.uint8)


# Compatibilidade com chamadores antigos.
def _u8(img: np.ndarray) -> np.ndarray:
    return para_u8_srgb(img, ja_srgb=False)


def _separador(altura: int, largura: int = 4) -> np.ndarray:
    return np.full((altura, largura, 3), 255, dtype=np.uint8)


def lado_a_lado(
    esquerda: np.ndarray,
    direita: np.ndarray,
    ja_srgb: bool = False,
) -> np.ndarray:
    """
    Negativo | Positivo, na mesma altura. Redimensiona se preciso.

    Devolve uint8 sRGB -- salve com pipeline.salvar(x, linear=False).
    """
    a = para_u8_srgb(esquerda, ja_srgb=ja_srgb)
    b = para_u8_srgb(direita, ja_srgb=ja_srgb)
    if a.shape[0] != b.shape[0]:
        alvo = min(a.shape[0], b.shape[0])
        a = ampliar(a, alvo=alvo, ja_srgb=True)
        b = ampliar(b, alvo=alvo, ja_srgb=True)
    return np.concatenate([a, _separador(a.shape[0]), b], axis=1)


def tira_de_etapas(
    etapas: dict[str, np.ndarray],
    ordem: list[str] | None = None,
    largura_max: int = 320,
    ja_srgb: bool = False,
) -> np.ndarray:
    """
    Uma faixa horizontal com cada etapa, reduzida para caber.

    Devolve uint8 sRGB -- salve com pipeline.salvar(x, linear=False).
    """
    if not etapas:
        raise ValueError("Nenhuma etapa para montar.")

    nomes = ordem or sorted(etapas.keys())
    quadros = []
    for n in nomes:
        if n not in etapas:
            continue
        u = para_u8_srgb(etapas[n], ja_srgb=ja_srgb)
        quadros.append(ampliar(u, largura=largura_max, ja_srgb=True))

    if not quadros:
        raise ValueError("Nenhuma etapa da lista existe no dicionário.")

    alturas = {q.shape[0] for q in quadros}
    if len(alturas) > 1:
        alvo = min(alturas)
        quadros = [q[:alvo] for q in quadros]

    partes: list[np.ndarray] = []
    for i, q in enumerate(quadros):
        if i:
            partes.append(_separador(q.shape[0], 3))
        partes.append(q)
    return np.concatenate(partes, axis=1)


def ampliar(
    img: np.ndarray,
    largura: int | None = None,
    alvo: int | None = None,
    ja_srgb: bool = False,
) -> np.ndarray:
    """
    Redimensiona e devolve uint8 sRGB.

    largura : largura final desejada.
    alvo    : altura final desejada (para igualar alturas).
    ja_srgb : marque True se a entrada já está em sRGB.
    """
    from PIL import Image

    a = para_u8_srgb(img, ja_srgb=ja_srgb)
    h, w = a.shape[:2]
    if alvo is not None and alvo != h:
        escala = alvo / h
        nw, nh = max(int(round(w * escala)), 1), alvo
    elif largura is not None and largura != w:
        escala = largura / w
        nw, nh = largura, max(int(round(h * escala)), 1)
    else:
        return a

    im = Image.fromarray(a, mode="RGB")
    metodo = Image.LANCZOS if (nw * nh) < (w * h) else Image.BICUBIC
    return np.asarray(im.resize((nw, nh), metodo))


def rotular_faixa(
    img: np.ndarray,
    texto: str,
    altura: int = 22,
    ja_srgb: bool = False,
) -> np.ndarray:
    """Adiciona uma faixa preta com texto no topo (fonte padrão do PIL)."""
    from PIL import Image, ImageDraw

    a = para_u8_srgb(img, ja_srgb=ja_srgb)

    faixa = np.zeros((altura, a.shape[1], 3), dtype=np.uint8)
    im = Image.fromarray(faixa, mode="RGB")
    desenho = ImageDraw.Draw(im)
    desenho.text((6, 5), texto, fill=(255, 255, 255))
    return np.concatenate([np.asarray(im), a], axis=0)
