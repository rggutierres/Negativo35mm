"""
Exercita a restauração inteira SEM chamar a API, medindo o que é enviado.

Substitui a camada HTTP por uma função que captura a imagem recebida e devolve
uma imagem sintética. Assim verificamos o caminho completo -- leitura, redução,
envio e gravação -- sem gastar nada.

O ponto que este teste protege: a imagem enviada tem de ter a MESMA exposição
do positivo. O bug antigo mandava com 1/15 do brilho.
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

from neg35 import config, pipeline, servidor  # noqa: E402

BASE = RAIZ / "tools" / "_teste_fluxo"
POSITIVO = BASE / "positivo"
RESTAURADA = BASE / "restaurada"
ENV = BASE / ".env"
FALHAS: list[str] = []


def checar(cond: bool, msg: str) -> None:
    if cond:
        print(f"  ok  {msg}")
    else:
        print(f"  FALHOU: {msg}")
        FALHAS.append(msg)


def lum(a):
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def montar() -> Path:
    """Positivo realista: gradiente com tons médios e uma borda clara."""
    shutil.rmtree(BASE, ignore_errors=True)
    POSITIVO.mkdir(parents=True)
    RESTAURADA.mkdir(parents=True)

    h, w = 900, 1600
    x = np.linspace(0.25, 0.80, w)
    img = np.repeat(x[None, :, None], h, axis=0)
    img = np.repeat(img, 3, axis=2)
    img[: h // 5] = 0.98                  # borda clara do filme
    img[-h // 5:] *= 0.45                 # sombra

    arq = POSITIVO / "foto_positivo.png"
    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(arq)

    cfg = config.carregar()
    cfg.pasta_origem = str(BASE / "origem")
    cfg.pasta_positivo = str(POSITIVO)
    cfg.pasta_restaurada = str(RESTAURADA)
    cfg.max_lado_envio = 1024
    cfg.usar_adobe = False
    cfg.openrouter_api_key = "sk-or-v1-TESTE"
    config.salvar(cfg, ENV)
    return arq


def main() -> int:
    arq = montar()
    cfg = config.carregar(ENV, usar_ambiente=False)

    with Image.open(arq) as im:
        original = np.asarray(im.convert("RGB")).astype(np.float64) / 255.0
    p50_original = float(np.median(lum(original)))

    print(f"positivo: {original.shape[1]}x{original.shape[0]}  "
          f"p50={p50_original:.4f}")
    print()

    # ---------------------------------------------------------------- 1
    print("=== 1) o que preparar_envio entrega ===")
    srgb = pipeline.carregar_srgb(arq)
    env = servidor.preparar_envio(srgb, cfg)
    p50_env = float(np.median(lum(env)))
    print(f"  enviado: {env.shape[1]}x{env.shape[0]}  p50={p50_env:.4f}")
    print(f"  diferença vs positivo: {p50_env - p50_original:+.4f}")
    checar(abs(p50_env - p50_original) < 0.02,
           f"a imagem enviada tem a exposição do positivo "
           f"({p50_original:.4f} vs {p50_env:.4f})")
    checar(max(env.shape[:2]) <= 1024, f"respeitou max_lado_envio ({env.shape[1]})")

    # ---------------------------------------------------------------- 2
    print()
    print("=== 2) o fluxo completo, com a API interceptada ===")
    import neg35.api as api_mod

    recebido = {}

    class FalsaRestauracao:
        def __init__(self, **kw):
            self.kw = kw

        def restaurar(self, img):
            recebido["img"] = np.asarray(img, dtype=np.float64).copy()
            recebido["kw"] = self.kw
            # devolve uma "restauração" plausível: mesma cena, um pouco mais
            # contrastada, preservando a exposição
            a = np.asarray(img, dtype=np.float64)
            return np.clip(a * 1.05, 0, 1)

    original_cls = api_mod.Restauracao
    api_mod.Restauracao = FalsaRestauracao
    try:
        res = servidor.restaurar(cfg, ["foto"], forcar=True)
    finally:
        api_mod.Restauracao = original_cls

    print(f"  resultado: ok={res['ok']} falhas={res['falhas']}")
    checar(res["ok"] == 1, f"restaurou a foto (ok={res['ok']})")

    if "img" in recebido:
        r = recebido["img"]
        p50_r = float(np.median(lum(r)))
        print(f"  a IA recebeu: {r.shape[1]}x{r.shape[0]}  p50={p50_r:.4f}")
        checar(abs(p50_r - p50_original) < 0.02,
               f"a IA RECEBEU com a exposição do positivo "
               f"({p50_original:.4f} vs {p50_r:.4f})")
        checar(p50_r > 0.35,
               f"a IA não recebeu imagem escura (p50={p50_r:.4f}; o bug dava 0.04)")
        # a chave tem de chegar
        chave = (recebido.get("kw") or {}).get("api_key", "")
        checar("TESTE" in chave, "a chave do .env foi passada")

    # ---------------------------------------------------------------- 3
    print()
    print("=== 3) o arquivo gravado saiu escuro? ===")
    saida = RESTAURADA / "foto_restaurado.png"
    checar(saida.is_file(), "gravou o restaurado")
    if saida.is_file():
        with Image.open(saida) as im:
            g = np.asarray(im.convert("RGB")).astype(np.float64) / 255.0
        p50_g = float(np.median(lum(g)))
        print(f"  gravado: {g.shape[1]}x{g.shape[0]}  p50={p50_g:.4f}")
        checar(p50_g > 0.35,
               f"o restaurado gravado NÃO está escuro (p50={p50_g:.4f})")

    shutil.rmtree(BASE, ignore_errors=True)
    print()
    if FALHAS:
        print(f"{len(FALHAS)} verificação(ões) falharam.")
        return 1
    print("Todas as verificações passaram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
