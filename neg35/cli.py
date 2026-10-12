"""
neg35 -- linha de comando.

    # Um arquivo
    python -m neg35.cli desenvolver negativo.jpg --filme gold200

    # Uma PASTA inteira: lista, você escolhe, ele converte
    python -m neg35.cli pasta "E:\\Bkp\\GoogleDrive\\RAW"

    # Diagnóstico e utilidades
    python -m neg35.cli amostrar negativo.jpg
    python -m neg35.cli comparar --gerar
    python -m neg35.cli modelos
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from neg35 import api, core, pipeline, post, render, synthetic  # noqa: E402

EXT_JPG = {".jpg", ".jpeg"}
EXT_RAW = {".dng", ".cr2", ".cr3", ".nef", ".arw", ".raf", ".orf", ".rw2", ".pef"}


# ----------------------------------------------------------------------
def _dir_saida(entrada: Path, extra: str | None) -> Path:
    base = extra or str(entrada.with_suffix("")) + "_neg35"
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _tupla(v: str | None) -> tuple[float, float, float] | None:
    if v is None:
        return None
    partes = [float(x) for x in v.replace(";", ",").split(",")]
    if len(partes) != 3:
        raise argparse.ArgumentTypeError("Esperado três valores: R,G,B")
    return (partes[0], partes[1], partes[2])


def _params(args, **over) -> pipeline.Parametros:
    p = pipeline.Parametros(
        filme=getattr(args, "filme", "generico"),
        base_filme=_tupla(getattr(args, "base", None)),
        ganhos=_tupla(getattr(args, "ganhos", None)) if getattr(args, "ganhos", None) else None,
        recorte_branco=getattr(args, "recorte_branco", 0.0),
        balanco_forca=getattr(args, "balanco", 0.85),
        ponto_neutro=_tupla(getattr(args, "neutro", None)),
        contraste_preto=getattr(args, "preto", 0.005),
        contraste_branco=getattr(args, "branco", 0.995),
        contraste_por_canal=getattr(args, "por_canal", False),
        gamma=getattr(args, "gamma", 1.0),
        saturacao=getattr(args, "saturacao", 1.12),
        nitidez=getattr(args, "sharp", 0.35),
        nitidez_raio=getattr(args, "sharp_raio", 1.2),
        nitidez_limiar=getattr(args, "sharp_limiar", 0.02),
        preto_e_branco=getattr(args, "pb", 0.0),
        auto=not getattr(args, "sem_auto", False),
        restaurar=getattr(args, "restaurar", None),
        modelo_ia=getattr(args, "modelo_ia", None),
    )
    for k, v in over.items():
        setattr(p, k, v)
    return p


# ----------------------------------------------------------------------
def _processar_um(
    origem: Path,
    saida: Path,
    params: pipeline.Parametros,
    salvar_etapas: bool = False,
) -> pipeline.Resultado:
    """Processa um arquivo e grava positivo + comparação."""
    res = pipeline.desenvolver(origem, params, manter_etapas=salvar_etapas)

    pipeline.salvar(res.final, saida / "positivo_final.png", linear=True)

    # O negativo é lido em sRGB só para a tira de conferência.
    neg = pipeline.carregar(origem, para_linear=False)
    tira = render.lado_a_lado(
        core.normalizar(neg, linear=False), res.final, ja_srgb=False
    )
    pipeline.salvar(tira, saida / "comparacao_antes_depois.png", linear=False)

    if salvar_etapas and res.etapas:
        pipeline.salvar(
            render.tira_de_etapas(res.etapas), saida / "etapas.png", linear=False
        )
    return res


def cmd_desenvolver(args) -> int:
    """Converte UM arquivo."""
    entrada = Path(args.entrada)
    if not entrada.exists():
        print(f"ERRO: não encontrei {entrada}", file=sys.stderr)
        return 2

    saida = _dir_saida(entrada, args.saida)
    print(f"Entrada : {entrada}")
    print(f"Saída   : {saida}")

    try:
        res = _processar_um(entrada, saida, _params(args), salvar_etapas=True)
    except Exception as e:  # noqa: BLE001
        print(f"ERRO: {e}", file=sys.stderr)
        return 1

    if res.meta.get("aviso"):
        print(f"AVISO   : {res.meta['aviso']}")
    base = res.base_filme
    if base is not None:
        print(f"Base    : R={base[0]:.4f}  G={base[1]:.4f}  B={base[2]:.4f}"
              f"  (R/B={base[0]/max(base[2],1e-9):.2f})")
    print(f"OK      -> {saida / 'positivo_final.png'}")
    return 0


# ----------------------------------------------------------------------
def _listar_pasta(pasta: Path) -> list[dict]:
    """Agrupa os arquivos da pasta por nome-base, juntando JPG e RAW."""
    por_base: dict[str, dict] = {}
    for p in sorted(pasta.iterdir()):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext in EXT_JPG:
            por_base.setdefault(p.stem, {"nome": p.stem})["jpg"] = p
        elif ext in EXT_RAW:
            por_base.setdefault(p.stem, {"nome": p.stem})["raw"] = p
    return [por_base[k] for k in sorted(por_base)]


def _escolher(itens: list[dict], selecao: str) -> list[dict]:
    """
    Interpreta a seleção do usuário.

    Aceita: "1,3,5"   "1-4"   "todos"   "a" (abortar)
    """
    s = selecao.strip().lower()
    if s in ("a", "abortar", "sair", "q"):
        return []
    if s in ("todos", "t", "*", "all"):
        return itens

    escolhidos: list[dict] = []
    for parte in s.replace(" ", "").split(","):
        if not parte:
            continue
        if "-" in parte:
            a, _, b = parte.partition("-")
            try:
                i0, i1 = int(a), int(b)
            except ValueError:
                print(f"  ignorando '{parte}': formato inválido")
                continue
            for i in range(i0, i1 + 1):
                if 1 <= i <= len(itens):
                    escolhidos.append(itens[i - 1])
        else:
            try:
                i = int(parte)
            except ValueError:
                print(f"  ignorando '{parte}': não é um número")
                continue
            if 1 <= i <= len(itens):
                escolhidos.append(itens[i - 1])
            else:
                print(f"  ignorando {i}: fora da faixa 1..{len(itens)}")

    # Remove duplicatas mantendo a ordem.
    vistos: set[str] = set()
    unicos = []
    for it in escolhidos:
        if it["nome"] not in vistos:
            vistos.add(it["nome"])
            unicos.append(it)
    return unicos


def cmd_pasta(args) -> int:
    """Lista uma pasta, deixa você escolher, e converte o que escolher."""
    pasta = Path(args.pasta)
    if not pasta.is_dir():
        print(f"ERRO: {pasta} não é uma pasta", file=sys.stderr)
        return 2

    itens = _listar_pasta(pasta)
    if not itens:
        print(f"nenhum JPG ou RAW em {pasta}")
        return 1

    com_par = sum(1 for i in itens if "jpg" in i and "raw" in i)
    print(f"\nPasta: {pasta}")
    print(f"{len(itens)} foto(s): {com_par} com JPG+DNG, "
          f"{sum(1 for i in itens if 'raw' in i and 'jpg' not in i)} só DNG, "
          f"{sum(1 for i in itens if 'jpg' in i and 'raw' not in i)} só JPG")
    print()
    print(f"{'#':>3}  {'arquivo':<24} {'JPG':>8} {'DNG':>8}  observação")
    print("-" * 72)
    for i, it in enumerate(itens, 1):
        jpg = f"{it['jpg'].stat().st_size/1024:,.0f}K" if "jpg" in it else "-"
        raw = f"{it['raw'].stat().st_size/1048576:.1f}M" if "raw" in it else "-"
        obs = ""
        if "raw" in it and "jpg" not in it:
            obs = "sem JPG"
        if "jpg" in it and "raw" not in it:
            obs = "sem DNG -- qualidade menor"
        print(f"{i:>3}  {it['nome']:<24} {jpg:>8} {raw:>8}  {obs}")

    print()
    print("Máscara laranja: o DNG preserva, o JPG costuma perder (o balanço de")
    print("branco automático do celular neutraliza). Prefira o DNG sempre que")
    print("tiver. Ambos têm a MESMA resolução, então o custo em tokens é igual.")
    print()

    selecao = args.selecao
    if selecao is None:
        try:
            selecao = input("Quais converter? (ex: 1,3-5 / todos / a=abortar): ")
        except (EOFError, KeyboardInterrupt):
            print("\nabortado")
            return 0

    escolhidos = _escolher(itens, selecao)
    if not escolhidos:
        print("nada a fazer")
        return 0

    print()
    print(f"Vai converter {len(escolhidos)} foto(s): "
          f"{', '.join(i['nome'] for i in escolhidos)}")
    print()

    raiz_saida = Path(args.saida) if args.saida else pasta / "neg35_saida"
    raiz_saida.mkdir(parents=True, exist_ok=True)

    ok = falhas = 0
    for it in escolhidos:
        # Preferência pela fonte escolhida pelo usuário.
        if args.fonte == "jpg":
            fonte = it.get("jpg") or it.get("raw")
        elif args.fonte == "dng":
            fonte = it.get("raw") or it.get("jpg")
        else:  # auto
            fonte = it.get("raw") or it.get("jpg")

        tipo = "DNG" if fonte.suffix.lower() in EXT_RAW else "JPG"
        destino = raiz_saida / f"{it['nome']}_{tipo.lower()}"
        print(f"[{it['nome']}] usando {tipo} -> {destino.name}")
        try:
            res = _processar_um(fonte, destino, _params(args))
            b = res.base_filme
            marca = f"base R/B={b[0]/max(b[2],1e-9):.2f}" if b is not None else ""
            aviso = f"  AVISO: {res.meta['aviso']}" if res.meta.get("aviso") else ""
            print(f"    ok  {marca}{aviso}")
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"    FALHOU: {type(e).__name__}: {str(e)[:140]}")
            falhas += 1

    print()
    print(f"convertidas: {ok}   falhas: {falhas}")
    print(f"saída: {raiz_saida}")
    return 0 if falhas == 0 else 1


# ----------------------------------------------------------------------
def cmd_amostrar(args) -> int:
    """Só diagnostica: base do filme e ponto neutro. Não escreve nada."""
    try:
        lin = pipeline.carregar(Path(args.entrada), para_linear=True)
    except Exception as e:  # noqa: BLE001
        print(f"ERRO: {e}", file=sys.stderr)
        return 1

    base = core.detectar_base_do_filme(lin)
    previa = core.inverter_negativo(lin, base_filme=base)
    neutro = post.medir_neutro(previa)

    print(f"Formato    : {lin.shape[2]} canais, {lin.shape[1]}x{lin.shape[0]}")
    print(f"Linear     : min={lin.min():.4f} max={lin.max():.4f} mean={lin.mean():.4f}")
    print(f"Base filme : R={base[0]:.4f}  G={base[1]:.4f}  B={base[2]:.4f}")
    print(f"Razão R/B  : {base[0] / max(base[2], 1e-6):.2f}")
    print("             (>2,5 indica máscara laranja preservada;")
    print("              ~1,2 indica que a máscara foi neutralizada --")
    print("              típico de JPG do celular, e a inversão fica pior)")
    print(f"Neutro     : R={neutro[0]:.4f}  G={neutro[1]:.4f}  B={neutro[2]:.4f}")
    print()
    print("Cole no comando com --base para travar a detecção:")
    print(f"  --base {base[0]:.4f},{base[1]:.4f},{base[2]:.4f}")
    return 0


def cmd_comparar(args) -> int:
    """Valida a matemática numa tira sintética (não precisa de foto real)."""
    filtro = synthetic.MASCARAS_PRESET.get(args.mascara, synthetic.MASCARAS_PRESET["kodak"])
    if args.gerar:
        positivo = synthetic.tira_de_teste()
        negativo = synthetic.positivo_para_negativo(positivo, mascara=filtro)
    else:
        positivo = pipeline.carregar(Path(args.positivo), para_linear=False)
        negativo = pipeline.carregar(Path(args.negativo), para_linear=False)

    res = pipeline.desenvolver(
        negativo,
        pipeline.Parametros(
            filme="generico",
            saturacao=1.0,
            nitidez=0.0,
            balanco_forca=1.0,
            auto=not args.sem_auto,
        ),
    )

    if args.gerar:
        alvo = core.normalizar(positivo, linear=False)
        erro = float(np_abs_mean(res.positivo, alvo))
        print(f"Erro médio abs. vs original: {erro * 255:.2f} níveis de 255")
        print("(referência: abaixo de ~12 é bom; acima de ~25 algo está errado)")

    saida = Path(args.saida or "comparacao_neg35")
    saida.mkdir(parents=True, exist_ok=True)
    pipeline.salvar(
        render.lado_a_lado(negativo, res.final), saida / "antes_depois.png", linear=False
    )
    if args.gerar:
        pipeline.salvar(positivo, saida / "original_sintetico.png", linear=False)
    if res.etapas:
        pipeline.salvar(
            render.tira_de_etapas(res.etapas), saida / "etapas.png", linear=False
        )
    print(f"OK -> {saida.resolve()}")
    return 0


def np_abs_mean(a, b):
    import numpy as np

    return np.abs(core.recortar(a) - core.recortar(b)).mean()


def cmd_modelos(args) -> int:
    try:
        linhas = api.listar_modelos_de_imagem()
    except Exception as e:  # noqa: BLE001
        print(f"ERRO: {e}", file=sys.stderr)
        return 1

    print(f"{'modelo':<48} {'US$/imagem':>12}  contexto")
    print("-" * 78)
    for mid, preco, ctx in linhas:
        # O OpenRouter publica o preço por TOKEN de imagem, não por foto.
        # Um modelo de imagem gasta ~1290 tokens por imagem; converter deixa
        # a comparação honesta com o preço por imagem do Google.
        try:
            usd = f"${float(preco) * api.TOKENS_POR_IMAGEM:.4f}"
        except (TypeError, ValueError):
            usd = str(preco)
        print(f"{mid:<48} {usd:>12}  {ctx}")
    print()
    print(f"US$/imagem = preço/token x {api.TOKENS_POR_IMAGEM} tokens, que é o consumo")
    print("típico de uma imagem. O custo real varia com a resolução pedida.")
    return 0


# ----------------------------------------------------------------------
def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="neg35",
        description="Inverte negativos 35mm e (opcionalmente) restaura com IA.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # -- opções compartilhadas de ajuste
    def comuns(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--filme", default="generico",
                            choices=sorted(core.GANHOS_POR_FILME))
        parser.add_argument("--base", default=None,
                            help="força a máscara: R,G,B em luz linear")
        parser.add_argument("--ganhos", default=None, help="ganhos por canal em stops")
        parser.add_argument("--recorte-branco", type=float, default=0.0, dest="recorte_branco")
        parser.add_argument("--balanco", type=float, default=0.85, help="força do balanço 0..1")
        parser.add_argument("--neutro", default=None, help="cinza conhecido: R,G,B em sRGB 0..1")
        parser.add_argument("--preto", type=float, default=0.005)
        parser.add_argument("--branco", type=float, default=0.995)
        parser.add_argument("--por-canal", action="store_true", dest="por_canal")
        parser.add_argument("--gamma", type=float, default=1.0)
        parser.add_argument("--saturacao", type=float, default=1.12)
        parser.add_argument("--sharp", type=float, default=0.35)
        parser.add_argument("--sharp-raio", type=float, default=1.2, dest="sharp_raio")
        parser.add_argument("--sharp-limiar", type=float, default=0.02, dest="sharp_limiar")
        parser.add_argument("--pb", type=float, default=0.0, help="dessaturar 0..1 (filme P&B)")
        parser.add_argument("--sem-auto", action="store_true", dest="sem_auto")
        parser.add_argument("--restaurar", default=None,
                            choices=["openrouter", "gemini", "openai"])
        parser.add_argument("--modelo-ia", default=None, dest="modelo_ia")

    d = sub.add_parser("desenvolver", help="inverte um negativo e salva o positivo")
    d.add_argument("entrada", help="foto do negativo (.dng, .tif, .jpg...)")
    d.add_argument("--saida", default=None, help="pasta de saída")
    comuns(d)
    d.set_defaults(func=cmd_desenvolver)

    pa = sub.add_parser("pasta", help="lista uma pasta, você escolhe, ele converte")
    pa.add_argument("pasta", help="pasta com os arquivos (JPG e/ou DNG)")
    pa.add_argument("--selecao", default=None,
                    help='quais converter: "1,3-5" ou "todos" (sem isso, pergunta)')
    pa.add_argument("--fonte", default="auto", choices=["auto", "dng", "jpg"],
                    help="auto (padrão) prefere DNG, que preserva a máscara")
    pa.add_argument("--saida", default=None, help="pasta de saída")
    comuns(pa)
    pa.set_defaults(func=cmd_pasta)

    a = sub.add_parser("amostrar", help="diagnostica a máscara sem salvar imagem")
    a.add_argument("entrada")
    a.set_defaults(func=cmd_amostrar)

    c = sub.add_parser("comparar", help="valida a matemática numa tira sintética")
    c.add_argument("--gerar", action="store_true", help="usa a tira de teste sintética")
    c.add_argument("--negativo", default=None)
    c.add_argument("--positivo", default=None)
    c.add_argument("--mascara", default="kodak", choices=sorted(synthetic.MASCARAS_PRESET))
    c.add_argument("--saida", default=None)
    c.add_argument("--sem-auto", action="store_true", dest="sem_auto")
    c.set_defaults(func=cmd_comparar)

    m = sub.add_parser("modelos", help="lista modelos de imagem e preços (OpenRouter)")
    m.set_defaults(func=cmd_modelos)

    return p


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    if args.cmd == "comparar" and not args.gerar and not (args.negativo and args.positivo):
        print("ERRO: use --gerar, ou passe --negativo e --positivo.", file=sys.stderr)
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
