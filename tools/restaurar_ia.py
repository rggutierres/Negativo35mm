"""
Etapa 2 -- restauração por IA, com comparação.

    .venv\\Scripts\\python.exe tools/restaurar_ia.py <positivo.png> [opções]

Envia um positivo JÁ PRONTO para um modelo de imagem e monta a comparação.

IMPORTANTE: envie o positivo, nunca o negativo cru. Modelos de imagem não
sabem que a máscara laranja é filme virgem -- tratam como dominante de cor e
"consertam" inventando uma cena. A inversão é matemática; a restauração é IA.

Exemplos:
    set OPENROUTER_API_KEY=sk-or-v1-...
    .venv\\Scripts\\python.exe tools/restaurar_ia.py positivo.png --provedor openrouter

    set GEMINI_API_KEY=AIza...
    .venv\\Scripts\\python.exe tools/restaurar_ia.py positivo.png --provedor gemini

    # lista os modelos de imagem disponíveis com preço por foto
    .venv\\Scripts\\python.exe tools/restaurar_ia.py --modelos
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from neg35 import api, core, pipeline, render  # noqa: E402

SAIDA_PADRAO = RAIZ / "tools" / "amostras" / "restauracao"


def listar() -> int:
    try:
        linhas = api.listar_modelos_de_imagem()
    except Exception as e:  # noqa: BLE001
        print(f"ERRO: {e}", file=sys.stderr)
        return 1
    print(f"{'modelo':<48} {'US$/imagem':>12}  contexto")
    print("-" * 78)
    for mid, preco, ctx in linhas:
        try:
            usd = f"${float(preco) * api.TOKENS_POR_IMAGEM:.4f}"
        except (TypeError, ValueError):
            usd = str(preco)
        print(f"{mid:<48} {usd:>12}  {ctx}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("positivo", nargs="?", help="PNG do positivo já invertido")
    ap.add_argument("--provedor", default="openrouter",
                    choices=["openrouter", "gemini", "openai"])
    ap.add_argument("--modelo", default=None, help="sobrepõe o modelo padrão")
    ap.add_argument("--saida", default=None)
    ap.add_argument("--prompt", default="estrito", choices=["estrito", "padrao"],
                    help="estrito (recomendado) proíbe reinterpretar")
    ap.add_argument("--max-lado", type=int, default=1536,
                    help="reduz o lado maior antes de enviar (poupa upload)")
    ap.add_argument("--forcar", action="store_true",
                    help="envia mesmo com máscara fraca (provável desperdício)")
    ap.add_argument("--modelos", action="store_true", help="só lista e sai")
    args = ap.parse_args()

    if args.modelos:
        return listar()

    if not args.positivo:
        print("ERRO: informe o PNG do positivo (ou use --modelos).", file=sys.stderr)
        return 2

    origem = Path(args.positivo)
    if not origem.exists():
        print(f"ERRO: não encontrei {origem}", file=sys.stderr)
        return 2

    saida = Path(args.saida) if args.saida else SAIDA_PADRAO
    saida.mkdir(parents=True, exist_ok=True)

    # Carrega o positivo em LUZ LINEAR (o pipeline trabalha assim).
    pos_lin = pipeline.carregar(origem, para_linear=True)
    print(f"positivo : {origem.name}  {pos_lin.shape[1]}x{pos_lin.shape[0]}")

    # Mede a máscara ANTES de gastar. Sem isto, este script manda para a IA um
    # arquivo que o tools/lote.py teria pulado -- e pagar por uma entrada
    # estragada devolve imagem borrada e com cast, como medimos.
    base = core.detectar_base_do_filme(pos_lin)
    rb = float(base[0] / max(base[2], 1e-9))
    print(f"máscara  : R/B={rb:.2f}  base={base.round(3)}")

    if rb < 2.5:
        print()
        print("  !! MÁSCARA FRACA (R/B < 2,5)")
        print("     O decodificador provavelmente aplicou balanço de branco, o que")
        print("     neutraliza a máscara laranja do filme. Medimos: a IA recebe uma")
        print("     entrada lavada e devolve imagem borrada e com dominante de cor.")
        print("     O positivo local (grátis) já está salvo. Gastar API aqui é")
        print("     provável desperdício.")
        if not args.forcar:
            print()
            print("     Use --forcar para enviar mesmo assim.")
            pipeline.salvar(pos_lin, saida / "01_positivo_local.png", linear=True)
            print(f"     positivo local salvo em {saida}")
            return 0
        print("     (--forcar: enviando mesmo assim)")
        print()

    # Reduz o lado maior: o modelo redimensiona internamente de qualquer
    # forma, então enviar 4000px só gasta upload e tempo.
    if args.max_lado and max(pos_lin.shape[:2]) > args.max_lado:
        escala = args.max_lado / max(pos_lin.shape[:2])
        novo = (max(int(pos_lin.shape[1] * escala), 1),
                max(int(pos_lin.shape[0] * escala), 1))
        pos_envio = render.ampliar(pos_lin, largura=novo[0], ja_srgb=False)
        # ampliar devolve uint8 sRGB; volta para linear explicitamente.
        pos_envio_lin = core.normalizar(pos_envio, linear=False)
        print(f"reduzido : {novo[0]}x{novo[1]} ({escala:.0%}) para o envio")
    else:
        pos_envio_lin = pos_lin

    prompt = api.PROMPT_ESTRITO if args.prompt == "estrito" else api.PROMPT_PADRAO
    modelo = args.modelo or api.MODELOS.get(args.provedor)

    print(f"provedor : {args.provedor}")
    print(f"modelo   : {modelo}")
    print(f"prompt   : {args.prompt} ({len(prompt)} caracteres)")
    print()
    print("enviando...")

    t0 = time.time()
    try:
        rest = api.Restauracao(
            provedor=args.provedor, modelo=args.modelo, prompt=prompt
        )
        resposta_srgb = rest.restaurar(core.linear_para_srgb(pos_envio_lin))
    except api.RestaurarErro as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 1

    dt = time.time() - t0
    restaurado = core.normalizar(resposta_srgb, linear=False)
    print(f"recebido : {restaurado.shape[1]}x{restaurado.shape[0]} em {dt:.1f}s")

    # --- métricas de antes/depois
    def estat(img: np.ndarray, rotulo: str) -> None:
        s = core.linear_para_srgb(img)
        lum = 0.2126 * s[..., 0] + 0.7152 * s[..., 1] + 0.0722 * s[..., 2]
        sat = s.max(axis=-1) - s.min(axis=-1)
        # Gradiente médio: mede nitidez/detalhe global.
        gy, gx = np.gradient(lum)
        grad = float(np.sqrt(gx ** 2 + gy ** 2).mean())
        print(f"  {rotulo:<20} lum p05={np.percentile(lum,5):.3f} "
              f"p50={np.percentile(lum,50):.3f} p95={np.percentile(lum,95):.3f} | "
              f"sat={sat.mean():.3f} | detalhe={grad*1000:.3f}")

    print()
    print("=== antes / depois ===")
    estat(pos_envio_lin, "positivo local")
    estat(restaurado, "restaurado pela IA")

    # --- salva
    pipeline.salvar(restaurado, saida / "02_restaurado_ia.png", linear=True)
    pipeline.salvar(pos_envio_lin, saida / "01_positivo_local.png", linear=True)

    # Tira: local | restaurado
    tira = render.tira_de_etapas(
        {"local": pos_envio_lin, "IA": restaurado},
        ordem=["local", "IA"], largura_max=760,
    )
    pipeline.salvar(tira, saida / "03_comparacao_local_vs_ia.png", linear=False)

    # Recorte 1:1 das áreas de pele, que é onde a IA costuma errar.
    h, w = pos_envio_lin.shape[:2]
    y0, x0 = int(h * 0.28), int(w * 0.34)
    y1, x1 = min(y0 + int(h * 0.22), h), min(x0 + int(w * 0.26), w)
    if y1 > y0 and x1 > x0:
        rec_local = pos_envio_lin[y0:y1, x0:x1]
        escala = min(rec_local.shape[0], restaurado.shape[0]) / max(rec_local.shape[0], 1)
        ry1 = int(y1 * restaurado.shape[0] / h)
        rx1 = int(x1 * restaurado.shape[1] / w)
        ry0 = int(y0 * restaurado.shape[0] / h)
        rx0 = int(x0 * restaurado.shape[1] / w)
        rec_ia = restaurado[ry0:ry1, rx0:rx1]
        recorte = render.tira_de_etapas(
            {"local_1x1": rec_local, "IA_1x1": rec_ia},
            ordem=["local_1x1", "IA_1x1"], largura_max=700,
        )
        pipeline.salvar(recorte, saida / "04_recorte_pele_1x1.png", linear=False)
        print()
        print("recorte 1:1 da região de pele salvo em 04_recorte_pele_1x1.png")
        print("(é onde modelos costumam suavizar demais ou trocar traços)")

    print()
    print(f"arquivos em {saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
