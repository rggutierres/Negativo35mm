"""
Testa o ESPAÇO DE COR da imagem enviada à IA.

O bug que este teste previne: a imagem ia para a IA ~3x mais escura que o
positivo, e o resultado voltava escuro. Parecia que o modelo escurecia, quando
ele apenas RECEBIA escuro.

A causa era sutil e vale registrar: `pipeline.carregar(para_linear=False)`
prometia sRGB e devolvia luz linear -- `core.normalizar` sempre devolve linear,
e o parâmetro `linear` dela descreve a ENTRADA, não a saída.

Medido no positivo desta sessão:

    bruto do arquivo (sRGB)       0,6096
    carregar(para_linear=True)    0,3386
    carregar(para_linear=False)   0,3386   <- deveria ser 0,6096

    .venv\\Scripts\\python.exe tools/_teste_cor_envio.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))

from PIL import Image  # noqa: E402

from neg35 import config, pipeline, servidor, synthetic  # noqa: E402

BASE = RAIZ / "tools" / "_teste_cor"
POSITIVO = BASE / "positivo"
ENV = BASE / ".env"
FALHAS: list[str] = []


def checar(cond: bool, msg: str) -> None:
    if cond:
        print(f"  ok  {msg}")
    else:
        print(f"  FALHOU: {msg}")
        FALHAS.append(msg)


def luminancia(a: np.ndarray) -> np.ndarray:
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def mediana_lum(a: np.ndarray) -> float:
    return float(np.median(luminancia(a)))


def montar() -> tuple[Path, np.ndarray]:
    """
    Cria um positivo com tons CONHECIDOS.

    Usa um gradiente em vez de áreas chapadas: assim a mediana tem significado
    e o redimensionamento não muda a distribuição.
    """
    shutil.rmtree(BASE, ignore_errors=True)
    POSITIVO.mkdir(parents=True)

    # Gradiente horizontal + faixa vertical, em sRGB, tons médios variados
    altura, largura = 400, 700
    x = np.linspace(0.15, 0.85, largura)
    img = np.repeat(x[None, :, None], altura, axis=0)
    img = np.repeat(img, 3, axis=2)
    # uma faixa escura e uma clara, para ter amplitude
    img[: altura // 5] *= 0.35
    img[-altura // 5:] = np.clip(img[-altura // 5:] * 1.4, 0, 1)

    arq = POSITIVO / "grad_positivo.png"
    Image.fromarray((img * 255).astype(np.uint8)).save(arq)

    cfg = config.carregar()
    cfg.pasta_origem = str(BASE / "origem")
    cfg.pasta_positivo = str(POSITIVO)
    cfg.pasta_restaurada = str(BASE / "restaurada")
    cfg.max_lado_envio = 1536
    config.salvar(cfg, ENV)
    return arq, img


def main() -> int:
    arq, esperado = montar()
    cfg = config.carregar(ENV, usar_ambiente=False)

    original = mediana_lum(esperado)
    print(f"positivo de teste: {esperado.shape[1]}x{esperado.shape[0]}, "
          f"mediana de luminância = {original:.4f}")
    print()

    # ---------------------------------------------------------------- 1
    print("=== 1) carregar_srgb devolve o que está no arquivo ===")
    srgb = pipeline.carregar_srgb(arq)
    obtido = mediana_lum(srgb)
    print(f"  carregar_srgb: {obtido:.4f}")
    checar(abs(obtido - original) < 0.01,
           f"bate com o arquivo ({original:.4f} vs {obtido:.4f})")

    # ---------------------------------------------------------------- 2
    print()
    print("=== 2) o bug: carregar(para_linear=False) NÃO devolve sRGB ===")
    # Documenta o comportamento (ainda) enganoso, para o teste registrar por
    # que existe uma função separada.
    enganoso = pipeline.carregar(arq, para_linear=False)
    escuro = mediana_lum(enganoso)
    print(f"  carregar(para_linear=False): {escuro:.4f}  "
          f"({escuro / max(original, 1e-9):.0%} do original)")
    checar(escuro < original * 0.9,
           "carregar(para_linear=False) devolve MAIS ESCURO que o arquivo "
           "(é luz linear, apesar do nome)")

    # ---------------------------------------------------------------- 3
    print()
    print("=== 3) preparar_envio preserva o positivo ===")
    env = servidor.preparar_envio(srgb, cfg)
    env_med = mediana_lum(env)
    print(f"  enviado: {env_med:.4f}   {env.shape[1]}x{env.shape[0]}")
    checar(abs(env_med - original) < 0.01,
           f"o que vai para a IA tem a mesma exposição do positivo "
           f"({original:.4f} vs {env_med:.4f})")
    checar(env.shape[1] <= 1536, f"respeitou max_lado_envio ({env.shape[1]})")

    # ---------------------------------------------------------------- 4
    print()
    print("=== 4) e com uma imagem grande de verdade? ===")
    # redução forte: 4000 de largura -> 1536
    grande = np.repeat(np.repeat(esperado, 6, axis=0), 6, axis=1)
    arq_grande = POSITIVO / "grande_positivo.png"
    Image.fromarray((np.clip(grande, 0, 1) * 255).astype(np.uint8)).save(arq_grande)
    s2 = pipeline.carregar_srgb(arq_grande)
    env2 = servidor.preparar_envio(s2, cfg)
    print(f"  original {s2.shape[1]}x{s2.shape[0]} -> enviado "
          f"{env2.shape[1]}x{env2.shape[0]}")
    print(f"  mediana: {mediana_lum(s2):.4f} -> {mediana_lum(env2):.4f}")
    checar(abs(mediana_lum(env2) - mediana_lum(s2)) < 0.01,
           "redução forte NÃO altera a exposição")

    # ---------------------------------------------------------------- 5
    print()
    print("=== 5) sem redução (imagem pequena) ===")
    cfg2 = config.carregar(ENV, usar_ambiente=False)
    cfg2.max_lado_envio = 100000
    env3 = servidor.preparar_envio(srgb, cfg2)
    checar(env3.shape == srgb.shape, "não redimensionou quando não precisava")
    checar(abs(mediana_lum(env3) - original) < 0.01, "exposição preservada")

    shutil.rmtree(BASE, ignore_errors=True)
    print()
    if FALHAS:
        print(f"{len(FALHAS)} verificação(ões) falharam.")
        return 1
    print("Todas as verificações passaram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
