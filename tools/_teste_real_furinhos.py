"""
TESTE REAL: restaura uma foto e verifica se a borda do filme (furinhos) saiu.

Este teste chama a IA de verdade, com a chave do .env. Custa ~US$ 0,04 por foto.

COMO VERIFICA, sem depender de olhar:

  1. PROPORÇÃO do resultado. O quadro do 35mm é 3:2. Se a IA recebeu a imagem já
     recortada e manteve o enquadramento, o resultado tem de ficar perto de 1,5.
     Um resultado largo (2,1) significa que a borda estava na imagem -- e é
     exatamente o que acontecia antes.

  2. BORDA CLARA. A borda do filme invertida é lisa e clara (lum ~0,91-1,00,
     gradiente ~0). O quadro tem textura (gradiente ~0,005). Então medimos: se
     as faixas das extremidades do resultado forem lisas e claras, sobrou borda.

  3. FURINHOS. Se houver padrão repetido de manchas claras/escuras nas
     extremidades, os furinhos sobreviveram.

Uso:
    python tools/_teste_real_furinhos.py [nome_da_foto]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from PIL import Image  # noqa: E402

from neg35 import config, pipeline, post, servidor  # noqa: E402

cfg = config.carregar()
pp = Path(cfg.pasta_positivo)
pr = Path(cfg.pasta_restaurada)


def carregar(p: Path) -> np.ndarray:
    with Image.open(p) as im:
        return np.asarray(im.convert("RGB")).astype(np.float64) / 255.0


def analisar_borda(a: np.ndarray, faixa_frac: float = 0.04) -> dict:
    """
    Mede as faixas das extremidades: são borda do filme ou foto?

    Devolve, para cada lado, o gradiente mediano (lisura) e a luminância mediana
    (clareza), além da variação (que denuncia furinhos).
    """
    h, w = a.shape[:2]
    lum = post.luminancia(a)
    gy, gx = np.gradient(lum)
    det = np.hypot(gx, gy)

    fx = max(int(w * faixa_frac), 6)
    fy = max(int(h * faixa_frac), 6)

    lados = {
        "esquerda": (slice(None), slice(0, fx)),
        "direita": (slice(None), slice(w - fx, w)),
        "topo": (slice(0, fy), slice(None)),
        "base": (slice(h - fy, h), slice(None)),
    }
    saida = {}
    for nome, corte in lados.items():
        l = lum[corte].ravel()
        d = det[corte].ravel()
        p10, p50, p90 = (float(np.percentile(l, q)) for q in (10, 50, 90))
        saida[nome] = {
            "grad": float(np.median(d)),
            "lum": p50,
            "var": p90 - p10,
            "liso": float(np.median(d)) < 0.002,
            "claro": p50 > 0.80,
        }
    return saida


def veredito(nome: str, m: dict) -> str:
    """Classifica uma faixa: BORDA (sobrou filme), FOTO, ou DUVIDOSO."""
    if m["liso"] and m["claro"]:
        return "BORDA"
    if m["grad"] > 0.003:
        return "foto"
    if m["claro"] and m["var"] > 0.15:
        return "BORDA+padrão"
    return "duvidoso"


def main() -> int:
    nome = sys.argv[1] if len(sys.argv) > 1 else "20261012_133746"
    pos = pp / f"{nome}_positivo.png"
    res = pr / f"{nome}_restaurado.png"

    if not pos.is_file():
        print(f"não existe positivo para {nome}")
        return 1

    print("=" * 74)
    print(f"TESTE REAL — {nome}")
    print("=" * 74)
    print(f"casar_exposicao  = {cfg.casar_exposicao}")
    print(f"recortar_bordas  = {cfg.recortar_bordas}")
    print(f"recorte_margem   = {cfg.recorte_margem}")
    print(f"dica_por_foto    = {cfg.dica_por_foto}")
    print(f"max_lado_envio   = {cfg.max_lado_envio}")
    print(f"modelo           = {cfg.modelo}")
    print(f"chave            = {'presente' if cfg.openrouter_api_key else 'AUSENTE'}")

    # ---- o que é enviado
    print()
    print("--- o que a IA vai receber ---")
    lin = pipeline.carregar_srgb(pos)
    env = servidor.preparar_envio(lin, cfg)
    ret = getattr(servidor.preparar_envio, "ultimo_recorte", None)
    print(f"  positivo     : {lin.shape[1]}x{lin.shape[0]}  "
          f"proporção {lin.shape[1]/lin.shape[0]:.3f}")
    print(f"  enviado      : {env.shape[1]}x{env.shape[0]}  "
          f"proporção {env.shape[1]/env.shape[0]:.3f}")
    print(f"  recorte      : {ret if ret else 'NÃO cortou (sem detecção)'}")
    if ret is None:
        print()
        print("  >>> ATENÇÃO: não recortou. Se a foto tem borda, o resultado")
        print("  >>> vai sair com ela. Verifique a detecção antes de gastar IA.")
    m = servidor.analisar_foto(env)
    print(f"  mediana envio: {m['p50']:.3f}  (dica: "
          f"{len(servidor.dica_para_a_ia(m))} caracteres)")

    # ---- chamar a IA
    if not cfg.openrouter_api_key:
        print("\nfalta a chave; não dá para testar de verdade")
        return 1

    print()
    print("--- chamando a IA (pode levar 30-90 s) ---")
    if res.is_file():
        antes = carregar(res)
        print(f"  restaurada anterior existe: {antes.shape[1]}x{antes.shape[0]}")
    else:
        antes = None

    t0 = time.time()
    try:
        resumo = servidor.restaurar(cfg, [nome], forcar=True)
    except Exception as e:  # noqa: BLE001
        print(f"  ERRO: {type(e).__name__}: {e}")
        return 1
    dur = time.time() - t0
    print(f"  resultado: ok={resumo.get('ok')} falhas={resumo.get('falhas')} "
          f"({dur:.0f} s)")
    for r in resumo.get("resultados", []):
        print(f"    {r}")

    if not res.is_file():
        print("\na restaurada não foi gravada -- não há o que medir")
        return 1

    depois = carregar(res)
    print()
    print("--- ANTES / DEPOIS ---")
    if antes is not None and antes.shape[:2] != depois.shape[:2]:
        print(f"  antes : {antes.shape[1]}x{antes.shape[0]}  "
              f"proporção {antes.shape[1]/antes.shape[0]:.3f}")
    print(f"  depois: {depois.shape[1]}x{depois.shape[0]}  "
          f"proporção {depois.shape[1]/depois.shape[0]:.3f}")

    # ---- verificação
    print()
    print("--- verificação das extremidades (o resultado tem borda?) ---")
    cab = f"  {'lado':<10} {'gradiente':>10} {'lum':>7} {'variação':>9}  veredito"
    print(cab)
    print("  " + "-" * (len(cab) - 2))
    medidas = analisar_borda(depois)
    achados = []
    for lado, mm in medidas.items():
        v = veredito(lado, mm)
        print(f"  {lado:<10} {mm['grad']:>10.5f} {mm['lum']:>7.3f} "
              f"{mm['var']:>9.3f}  {v}")
        if v.startswith("BORDA"):
            achados.append(lado)

    prop = depois.shape[1] / depois.shape[0]
    print()
    print(f"  proporção do resultado: {prop:.3f}")
    print(f"  (o quadro do 35mm é 3:2 = 1,500; a imagem inteira sem recorte "
          f"daria ~2,14)")

    print()
    if achados:
        print(f"  RESULTADO: SOBROU BORDA nos lados: {', '.join(achados)}")
        print("  -> o recorte não resolveu. Investigar e repetir.")
        return 2
    if abs(prop - 1.5) > 0.15:
        print(f"  RESULTADO: a proporção {prop:.3f} não é ~1,5.")
        print("  -> o enquadramento não corresponde ao quadro recortado.")
        return 3
    print("  RESULTADO: sem borda do filme e proporção de quadro 3:2.")
    print("  -> os furinhos foram eliminados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
