"""
Correção de olhos vermelhos.

O PROBLEMA: o flash atravessa a pupila e volta refletido da retina. A retina é
avermelhada, então a pupila sai vermelho-alaranjada em vez de preta.

COMO CORRIGIR: achar os pixels em que o VERMELHO domina de forma anômala e
substituir esse vermelho pela média dos outros canais. A pupila fica cinza-escura
-- que é o que ela deveria ser -- em vez de vermelha.

POR QUE NÃO BASTA UM LIMIAR DE COR: uma roupa vermelha, um lábio, um tomate
também têm vermelho dominante. Aplicar o filtro no vermelho do mundo inteiro
estragaria a foto. Então o filtro trabalha em DUAS ETAPAS:

1. marca os pixels com vermelho anômalo;
2. agrupa os marcados em REGIÕES e descarta as que não parecem pupila:

   - área: pupila de olho num scan de 1500 px tem de 12 a ~8000 px. Região
     gigante (roupa) cai fora;
   - forma: precisa ter largura E altura de pelo menos 3 px -- um traço fino
     (borda de objeto vermelho) não é pupila;
   - preenchimento: a área da região comparada com a área do retângulo que a
     contém tem de ser razoável. Pupila é redonda (~0,78 de um círculo).
     Um "L" de tecido vermelho preenche pouco.

Só depois disso o vermelho é neutralizado, e apenas dentro das regiões aceitas.

Trabalha em sRGB [0,1], que é o que os arquivos restaurados contêm.
"""

from __future__ import annotations

import numpy as np

# Limiares de cor. Calibrados para "vermelho de pupila com flash", não para
# vermelho de objeto: exige dominância forte E saturação alta.
LUM_MIN = 0.28          # abaixo disto é sombra, não reflexo de flash
DOMINANCIA = 1.45       # R tem de ser 1,45x o maior entre G e B
SATURACAO_MIN = 0.42    # (R - menor)/R

# Limites de forma das regiões aceitas.
AREA_MIN = 12
AREA_MAX = 8000
LADO_MIN = 3
PREENCHIMENTO_MIN = 0.35

# Escala de trabalho para rotular regiões: acima disto, reduz.
LADO_MAX_ROTULO = 900


def _mascara_de_cor(a: np.ndarray) -> np.ndarray:
    """Pixels com vermelho anômalo, sem julgamento de forma."""
    r = a[..., 0]
    g = a[..., 1]
    b = a[..., 2]
    maior_outro = np.maximum(g, b)
    menor = np.minimum(np.minimum(r, g), b)

    dominante = r > maior_outro * DOMINANCIA
    saturado = (r - menor) / np.maximum(r, 1e-6) > SATURACAO_MIN
    claro_o_bastante = r > LUM_MIN

    return dominante & saturado & claro_o_bastante


def _rotular(mascara: np.ndarray) -> tuple[np.ndarray, int]:
    """
    Rotula regiões conectadas (4 vizinhos) com busca em largura.

    Devolve (rotulos, quantidade). Fundo é 0.

    Implementado à mão porque o projeto não tem scipy nem OpenCV, e trazer uma
    dessas bibliotecas por causa disto não se paga.
    """
    h, w = mascara.shape
    rotulos = np.zeros((h, w), dtype=np.int32)
    atual = 0
    # Pilha de coordenadas; tuplas simples bastam, o número de pixels é pequeno.
    for y0, x0 in zip(*np.nonzero(mascara)):
        if rotulos[y0, x0]:
            continue
        atual += 1
        pilha = [(int(y0), int(x0))]
        rotulos[y0, x0] = atual
        while pilha:
            y, x = pilha.pop()
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and mascara[ny, nx] \
                        and not rotulos[ny, nx]:
                    rotulos[ny, nx] = atual
                    pilha.append((ny, nx))
    return rotulos, atual


def _regioes_aceitas(rotulos: np.ndarray, total: int) -> list[int]:
    """Quais rótulos têm cara de pupila."""
    aceitos = []
    for r in range(1, total + 1):
        ys, xs = np.where(rotulos == r)
        area = len(ys)
        if area < AREA_MIN or area > AREA_MAX:
            continue
        altura = int(ys.max() - ys.min()) + 1
        largura = int(xs.max() - xs.min()) + 1
        if altura < LADO_MIN or largura < LADO_MIN:
            continue
        preenchimento = area / float(altura * largura)
        if preenchimento < PREENCHIMENTO_MIN:
            continue
        aceitos.append(r)
    return aceitos


def _dilatar(mascara: np.ndarray, raio: int = 1) -> np.ndarray:
    """Engorda a máscara, para pegar a borda da pupila."""
    saida = mascara.copy()
    for _ in range(max(raio, 0)):
        atual = saida.copy()
        atual[1:, :] |= saida[:-1, :]
        atual[:-1, :] |= saida[1:, :]
        atual[:, 1:] |= saida[:, :-1]
        atual[:, :-1] |= saida[:, 1:]
        saida = atual
    return saida


def detectar(a: np.ndarray, dilatar: int = 1) -> tuple[np.ndarray, dict]:
    """
    Acha as regiões de olho vermelho. Devolve (mascara, info).

    Reduz a imagem para rotular se for grande: rotular em Python puro em 1500 px
    de largura seria lento, e a olho nu a diferença na máscara é nenhuma.
    """
    a = np.asarray(a, dtype=np.float64)
    h, w = a.shape[:2]

    escala = 1.0
    if max(h, w) > LADO_MAX_ROTULO:
        escala = LADO_MAX_ROTULO / max(h, w)
        nh, nw = max(int(h * escala), 1), max(int(w * escala), 1)
        from PIL import Image

        pequena = np.asarray(
            Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))
            .resize((nw, nh), Image.BILINEAR)
        ).astype(np.float64) / 255.0
    else:
        pequena = a

    candidata = _mascara_de_cor(pequena)
    rotulos, total = _rotular(candidata)
    aceitos = _regioes_aceitas(rotulos, total)

    info = {
        "escala": escala,
        "regioes_encontradas": total,
        "regioes_aceitas": len(aceitos),
        "pixels_pequena": int(sum((rotulos == r).sum() for r in aceitos)),
    }

    if not aceitos:
        return np.zeros((h, w), dtype=bool), info

    pequena_aceita = np.isin(rotulos, aceitos)
    if escala != 1.0:
        from PIL import Image

        grande = np.asarray(
            Image.fromarray(pequena_aceita.astype(np.uint8) * 255)
            .resize((w, h), Image.NEAREST)
        ) > 127
    else:
        grande = pequena_aceita

    # Reencontra com a máscara de cor em resolução cheia: o upscale pode ter
    # espalhado a região para pixels que não são vermelhos.
    grande &= _mascara_de_cor(a)
    grande = _dilatar(grande, dilatar)

    info["pixels"] = int(grande.sum())
    info["fracao"] = float(grande.mean())
    return grande, info


def corrigir(a: np.ndarray, forca: float = 0.85,
             dilatar: int = 1) -> tuple[np.ndarray, dict]:
    """
    Neutraliza o vermelho das pupilas.

    `forca` 0..1 mistura com o original: 1,0 substitui o vermelho por completo,
    0,85 deixa um resto de cor (às vezes fica mais natural).

    A substituição é `R := (G + B) / 2`, aplicada só nos pixels da máscara. O
    G e o B não são tocados, então o resto da foto fica idêntico -- inclusive o
    vermelho de objetos, que nem entra na máscara.

    Devolve (imagem, info).
    """
    a = np.asarray(a, dtype=np.float64)
    mascara, info = detectar(a, dilatar=dilatar)
    info["forca"] = float(forca)
    if not info.get("pixels"):
        return a, info

    f = min(1.0, max(0.0, float(forca)))
    saida = a.copy()
    r = saida[..., 0]
    media = (saida[..., 1] + saida[..., 2]) / 2.0
    r[mascara] = (1.0 - f) * r[mascara] + f * media[mascara]
    info["pixels_alterados"] = int(mascara.sum())
    return np.clip(saida, 0.0, 1.0), info
