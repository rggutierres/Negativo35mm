"""
neg35 -- fluxo completo em lote: negativo -> positivo local -> restauração por IA.

    .venv\\Scripts\\python.exe tools/lote.py

O que ele faz, na ordem:

1. Lê (ou cria) o `.env`, que guarda pastas, chave de API, modelo e prompt
2. Mostra as pastas e deixa você confirmar ou alterar
3. Lista os originais que AINDA NÃO foram restaurados
4. Você escolhe (múltipla escolha ou todos)
5. Mostra o custo estimado
6. Ao confirmar: gera o positivo local (grátis) e chama a IA (paga)

Etapa 1 é de graça e roda sempre. Etapa 2 é o que custa dinheiro, então o
custo é mostrado ANTES de qualquer chamada.

    # opções
    --tudo            não pergunta nada, processa tudo que falta
    --selecao 1,3-5   escolhe sem interação
    --so-local        gera só os positivos, sem chamar IA (grátis)
    --env CAMINHO     usa outro arquivo de configuração
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from neg35 import api, config, core, pipeline, render  # noqa: E402

EXT_IMAGEM = {".dng", ".cr2", ".cr3", ".nef", ".arw", ".raf", ".orf", ".rw2",
              ".pef", ".jpg", ".jpeg", ".tif", ".tiff", ".png"}

# Preço por imagem em USD, usado quando a consulta ao OpenRouter falha.
CUSTO_FALLBACK = {
    "google/gemini-2.5-flash-image": 0.039,
    "google/gemini-nano-banana-2.1": 0.039,
    "google/gemini-3.1-flash-image": 0.077,
    "google/gemini-3-pro-image": 0.155,
    "openai/gpt-5-image-mini": 0.010,
}


# ---------------------------------------------------------------------------
# apresentação
# ---------------------------------------------------------------------------
def titulo(t: str) -> None:
    print()
    print("=" * 74)
    print(t)
    print("=" * 74)


def perguntar(caminho_atual: str, descricao: str) -> str:
    """Mostra o valor atual e aceita Enter para manter, ou um novo valor."""
    print(f"  {descricao}:")
    print(f"    atual: {caminho_atual}")
    try:
        novo = input("    novo (Enter mantém): ").strip().strip('"')
    except (EOFError, KeyboardInterrupt):
        print()
        return caminho_atual
    if not novo:
        return caminho_atual
    return novo


def validar_pastas(cfg: config.Config) -> bool:
    """Confere se as três pastas existem e se a origem tem imagem."""
    ok = True
    origem = Path(cfg.pasta_origem)

    if not origem.is_dir():
        print(f"  !! origem não existe ou não é pasta: {origem}")
        ok = False
    else:
        n = sum(1 for p in origem.iterdir()
                if p.is_file() and p.suffix.lower() in EXT_IMAGEM)
        if n == 0:
            print(f"  !! origem não tem nenhuma imagem: {origem}")
            ok = False
        else:
            print(f"  origem      : {origem}  ({n} imagens)")

    for rotulo, caminho in (("positivo", cfg.pasta_positivo),
                            ("restaurada", cfg.pasta_restaurada)):
        p = Path(caminho)
        if p.is_dir():
            print(f"  {rotulo:<11}: {p}  (existe)")
        else:
            print(f"  {rotulo:<11}: {p}  (será criada)")
    return ok


# ---------------------------------------------------------------------------
# varredura
# ---------------------------------------------------------------------------
def listar_originais(origem: Path) -> list[dict]:
    """
    Agrupa por nome-base, juntando DNG e JPG da mesma foto.

    Preferência de fonte: DNG > JPG, porque o JPG do celular tem a máscara
    laranja neutralizada pelo balanço de branco automático e o positivo sai
    pior. Só usa JPG quando não existe DNG daquele nome.
    """
    por_base: dict[str, dict] = {}
    for p in sorted(origem.iterdir()):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext not in EXT_IMAGEM:
            continue
        item = por_base.setdefault(p.stem, {"nome": p.stem})
        if ext in {".dng", ".cr2", ".cr3", ".nef", ".arw", ".raf", ".orf", ".rw2", ".pef"}:
            item["raw"] = p
        elif ext in {".jpg", ".jpeg"}:
            item["jpg"] = p
        else:
            item.setdefault("outro", p)

    for item in por_base.values():
        item["fonte"] = item.get("raw") or item.get("jpg") or item.get("outro")
    return [por_base[k] for k in sorted(por_base)]


def nome_positivo(stem: str) -> str:
    return f"{stem}_positivo.png"


def nome_restaurado(stem: str) -> str:
    return f"{stem}_restaurado.png"


def filtrar_pendentes(
    itens: list[dict],
    cfg: config.Config,
    pasta_saida: Path,
    com_ia: bool,
) -> tuple[list[dict], int]:
    """
    Remove o que já está convertido na pasta de saída relevante.

    Qual pasta conta depende do modo:
      - com IA     -> pasta Restaurada, arquivo {nome}_restaurado.png
      - --so-local -> pasta Positivo,   arquivo {nome}_positivo.png

    Usar o critério do modo evita dois erros: pular uma foto que só tem o
    positivo quando o usuário quer a restauração, e reportar como pendente
    uma foto cujo positivo já existe quando é só isso que se quer.

    Devolve (pendentes, quantos_foram_pulados).
    """
    if not cfg.pular_restauradas:
        return itens, 0

    if not pasta_saida.is_dir():
        return itens, 0

    existentes = {p.name.lower() for p in pasta_saida.iterdir() if p.is_file()}
    nome_esperado = nome_restaurado if com_ia else nome_positivo

    pendentes, pulados = [], 0
    for it in itens:
        if nome_esperado(it["nome"]).lower() in existentes:
            pulados += 1
        else:
            pendentes.append(it)
    return pendentes, pulados


def escolher(itens: list[dict], selecao: str | None) -> list[dict]:
    """Interpreta a escolha: '1,3-5', 'todos', 'a'. Sem argumento, pergunta."""
    if selecao is None:
        print()
        print("Quais processar?")
        print("  exemplos:  1        apenas o primeiro")
        print("             1,3,5    três específicos")
        print("             2-6      faixa")
        print("             todos    todos os listados")
        print("             a        abortar")
        try:
            selecao = input("  escolha: ")
        except (EOFError, KeyboardInterrupt):
            print()
            return []

    s = selecao.strip().lower()
    if s in ("a", "abortar", "sair", "q", ""):
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
                print(f"  ignorando '{parte}': não é número")
                continue
            if 1 <= i <= len(itens):
                escolhidos.append(itens[i - 1])
            else:
                print(f"  ignorando {i}: fora da faixa 1..{len(itens)}")

    vistos, unicos = set(), []
    for it in escolhidos:
        if it["nome"] not in vistos:
            vistos.add(it["nome"])
            unicos.append(it)
    return unicos


# ---------------------------------------------------------------------------
# custo
# ---------------------------------------------------------------------------
def custo_por_imagem(cfg: config.Config) -> tuple[float, str]:
    """
    Consulta o preço do modelo no OpenRouter. Devolve (usd, origem_do_dado).

    Se a consulta falhar (rede, proxy), cai numa tabela local em vez de
    mentir que é zero.
    """
    if cfg.provedor != "openrouter":
        return CUSTO_FALLBACK.get(cfg.modelo, 0.0), "tabela local"

    try:
        for mid, preco, _ in api.listar_modelos_de_imagem():
            if mid == cfg.modelo:
                return float(preco) * api.TOKENS_POR_IMAGEM, "consulta ao OpenRouter"
    except Exception:  # noqa: BLE001
        pass

    if cfg.modelo in CUSTO_FALLBACK:
        return CUSTO_FALLBACK[cfg.modelo], "tabela local (consulta falhou)"
    return 0.0, "desconhecido"


# ---------------------------------------------------------------------------
# processamento
# ---------------------------------------------------------------------------
def verificar_escrita(pastas: list[Path]) -> list[tuple[Path, str]]:
    """
    Confere se dá para escrever em cada pasta ANTES de processar.

    Sem isso, o programa trabalha (e gasta API) para só então descobrir que
    não consegue gravar -- e o usuário perde tempo e dinheiro. Testar na
    entrada custa milissegundos.

    Devolve a lista de (pasta, motivo) que falharam.
    """
    falhas: list[tuple[Path, str]] = []
    for p in pastas:
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            falhas.append((p, f"não consegui criar: {e}"))
            continue
        teste = p / "_neg35_teste_escrita.tmp"
        try:
            teste.write_bytes(b"x")
            teste.unlink()
        except OSError as e:
            falhas.append((p, f"sem permissão de escrita: {e}"))
    return falhas


def processar(
    item: dict,
    cfg: config.Config,
    positivo_dir: Path,
    restaurado_dir: Path,
    com_ia: bool,
) -> tuple[bool, str]:
    """Gera o positivo e, se pedido, restaura. Devolve (ok, mensagem)."""
    origem: Path = item["fonte"]

    # --- Etapa 1: inversão local (grátis)
    res = pipeline.desenvolver(
        origem,
        pipeline.Parametros(
            filme=cfg.filme,
            saturacao=cfg.saturacao,
            nitidez=cfg.nitidez,
            balanco_forca=cfg.balanco,
        ),
    )
    arq_positivo = positivo_dir / nome_positivo(item["nome"])
    pipeline.salvar(res.positivo, arq_positivo, linear=True)

    partes = [f"positivo ok ({arq_positivo.name})"]
    if res.meta.get("aviso"):
        partes.append(f"AVISO: {res.meta['aviso']}")

    # --- Checagem da máscara ANTES de gastar API
    #
    # Se o decodificador aplicou balanço de branco (o que acontece no fallback
    # do ImageMagick), a máscara laranja chega neutralizada e o positivo sai
    # lavado. Medimos isso em R/B ~1,5 no fallback contra ~4,3 no caminho
    # LibRaw. Testado: mandar esse positivo para a IA devolve uma imagem
    # borrada e esverdeada -- ou seja, dinheiro jogado fora.
    base = res.base_filme
    rb = float(base[0] / max(base[2], 1e-9)) if base is not None else 0.0
    mascara_fraca = rb < 2.5

    if mascara_fraca:
        partes.append(f"!! máscara fraca (R/B={rb:.2f})")

    if not com_ia:
        return True, " | ".join(partes)

    if mascara_fraca and cfg.pular_mascara_fraca:
        return True, (" | ".join(partes)
                      + " -- restauração PULADA (máscara fraca; a IA não recupera)")

    # --- Etapa 2: restauração por IA (paga)
    # Reduz antes de enviar: o modelo normaliza a resolução internamente,
    # então mandar 4000px não melhora e gasta upload.
    lin = res.positivo
    if cfg.max_lado_envio and max(lin.shape[:2]) > cfg.max_lado_envio:
        escala = cfg.max_lado_envio / max(lin.shape[:2])
        novo_w = max(int(lin.shape[1] * escala), 1)
        u8 = render.ampliar(lin, largura=novo_w, ja_srgb=False)
        envio = core.normalizar(u8, linear=False)
    else:
        envio = lin

    rest = api.Restauracao(
        provedor=cfg.provedor, modelo=cfg.modelo, prompt=cfg.prompt
    )
    resposta = rest.restaurar(core.linear_para_srgb(envio))
    restaurado = core.normalizar(resposta, linear=False)

    arq_restaurado = restaurado_dir / nome_restaurado(item["nome"])
    pipeline.salvar(restaurado, arq_restaurado, linear=True)
    partes.append(f"restaurado ok ({restaurado.shape[1]}x{restaurado.shape[0]})")
    return True, " | ".join(partes)


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fluxo em lote: negativo -> positivo local -> restauração por IA"
    )
    ap.add_argument("--env", default=None, help="caminho do .env")
    ap.add_argument("--tudo", action="store_true", help="processa tudo que falta")
    ap.add_argument("--selecao", default=None, help="ex: 1,3-5 (sem interação)")
    ap.add_argument("--so-local", action="store_true",
                    help="só gera os positivos, sem chamar IA (grátis)")
    ap.add_argument("--sem-perguntar-pastas", action="store_true",
                    help="não confirma as pastas, usa direto o .env")
    args = ap.parse_args()

    env_path = Path(args.env) if args.env else config.ENV_PADRAO

    # -- 1) configuração
    cfg, env_path, criado = config.garantir_env(env_path)
    titulo("neg35 -- negativo 35mm -> positivo -> restauração")
    if criado:
        print(f"  criei o arquivo de configuração: {env_path}")
    else:
        print(f"  configuração: {env_path}")

    # -- 2) confirmação das pastas
    if not args.sem_perguntar_pastas:
        print()
        print("Pastas de trabalho (Enter mantém, ou digite um caminho novo):")
        novo_origem = perguntar(cfg.pasta_origem, "1/3 origem (os .dng/.jpg)")
        novo_positivo = perguntar(cfg.pasta_positivo, "2/3 positivos locais (.png)")
        novo_restaurada = perguntar(cfg.pasta_restaurada, "3/3 restauradas pela IA (.png)")

        mudou = (novo_origem != cfg.pasta_origem
                 or novo_positivo != cfg.pasta_positivo
                 or novo_restaurada != cfg.pasta_restaurada)
        cfg.pasta_origem = novo_origem
        cfg.pasta_positivo = novo_positivo
        cfg.pasta_restaurada = novo_restaurada
        if mudou:
            config.salvar(cfg, env_path)
            print(f"  pastas atualizadas e salvas em {env_path.name}")

    print()
    ok = validar_pastas(cfg)
    if not ok:
        print()
        print("Corrija as pastas e rode de novo. Para editar à mão:", env_path)
        return 2

    positivo_dir = Path(cfg.pasta_positivo)
    restaurado_dir = Path(cfg.pasta_restaurada)

    # Verificação de escrita logo na entrada: melhor descobrir agora do que
    # depois de escolher as fotos (ou de gastar API).
    problemas = verificar_escrita([positivo_dir, restaurado_dir])
    if problemas:
        print()
        print("  !! NÃO CONSIGO ESCREVER nas pastas de saída:")
        for p, motivo in problemas:
            print(f"     {p}")
            print(f"       {motivo}")
        print()
        print("  Causas comuns:")
        print("   - o sincronizador do Google Drive/OneDrive está segurando a pasta")
        print("     (pause a sincronização, ou use uma pasta fora do Drive)")
        print("   - a pasta está aberta em outro programa com trava exclusiva")
        print("   - falta permissão no caminho, ou a pasta é somente leitura")
        print()
        print("  Dica: processe numa pasta LOCAL e deixe o Drive sincronizar")
        print("  o resultado depois. O Drive travando a pasta de saída é a")
        print("  causa mais comum deste erro.")
        return 2

    # Define o modo ANTES do filtro: ele decide qual pasta conta como
    # "já convertido".
    com_ia = not args.so_local
    if com_ia and cfg.provedor == "openrouter" and not cfg.openrouter_api_key:
        print()
        print("  !! falta openrouter_api_key no .env -- não dá para restaurar.")
        print("     Rode com --so-local para gerar só os positivos (grátis).")
        com_ia = False
    elif com_ia and cfg.provedor == "gemini" and not cfg.gemini_api_key:
        print()
        print("  !! falta gemini_api_key no .env.")
        print("     Rode com --so-local para gerar só os positivos (grátis).")
        com_ia = False

    pasta_saida = restaurado_dir if com_ia else positivo_dir

    # -- 3) o que ainda falta
    titulo("Originais encontrados")
    todos = listar_originais(Path(cfg.pasta_origem))
    pendentes, pulados = filtrar_pendentes(todos, cfg, pasta_saida, com_ia)

    rotulo_modo = "restauradas" if com_ia else "positivos"
    print(f"  {len(todos)} foto(s) na origem")
    if pulados:
        print(f"  {pulados} já com {rotulo_modo} -- ignoradas")
    print(f"  {len(pendentes)} a processar")
    print()
    print(f"{'#':>3}  {'arquivo':<24} {'fonte':<6} {'MB':>7}  observação")
    print("-" * 74)
    for i, it in enumerate(pendentes, 1):
        f = it["fonte"]
        tipo = "DNG" if "raw" in it and f is it["raw"] else "JPG"
        mb = f.stat().st_size / 1048576
        obs = ""
        if "raw" not in it:
            obs = "sem DNG -- máscara laranja provavelmente perdida"
        print(f"{i:>3}  {it['nome']:<24} {tipo:<6} {mb:>7.1f}  {obs}")

    if not pendentes:
        print()
        print("Nada a fazer. Tudo já foi restaurado.")
        return 0

    if not cfg.pasta_origem:
        print("origem vazia")
        return 2

    # -- 4) escolha
    selecao = "todos" if args.tudo else args.selecao
    escolhidos = escolher(pendentes, selecao)
    if not escolhidos:
        print("  nada selecionado, saindo")
        return 0

    # -- 5) custo estimado
    titulo("Estimativa")
    print(f"  fotos selecionadas : {len(escolhidos)}")
    print(f"  modelo             : {cfg.modelo}")
    print(f"  provedor           : {cfg.provedor}")

    if com_ia:
        unitario, fonte_dado = custo_por_imagem(cfg)
        total = unitario * len(escolhidos)
        print(f"  custo por imagem   : US$ {unitario:.4f}  ({fonte_dado})")
        print(f"  CUSTO ESTIMADO     : US$ {total:.3f}"
              f"   (~R$ {total * 5.5:.2f} ao câmbio de 5,5)")
    else:
        print("  sem chamada de IA nesta execução -- custo ZERO")

    print()
    print("  Etapa 1 (positivo local) é sempre grátis e roda para todos.")

    if not args.tudo and args.selecao is None:
        try:
            resp = input("\n  Confirma? (s/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if resp not in ("s", "sim", "y", "yes"):
            print("  cancelado")
            return 0

    # -- 6) processar
    titulo("Processando")
    ok_n = falhas = 0
    t_inicio = time.time()
    for i, it in enumerate(escolhidos, 1):
        print(f"[{i}/{len(escolhidos)}] {it['nome']}")
        try:
            sucesso, msg = processar(it, cfg, positivo_dir, restaurado_dir, com_ia)
            print(f"    {msg}")
            ok_n += 1 if sucesso else 0
        except api.RestaurarErro as e:
            print(f"    FALHOU na IA: {str(e)[:200]}")
            print("    (o positivo local foi salvo de qualquer forma)")
            falhas += 1
        except Exception as e:  # noqa: BLE001
            print(f"    FALHOU: {type(e).__name__}: {str(e)[:200]}")
            falhas += 1

    dt = time.time() - t_inicio
    titulo("Resumo")
    print(f"  processadas : {ok_n}")
    print(f"  falhas      : {falhas}")
    print(f"  tempo       : {dt:.1f}s ({dt / max(len(escolhidos), 1):.1f}s por foto)")
    print(f"  positivos   : {positivo_dir}")
    if com_ia:
        print(f"  restauradas : {restaurado_dir}")
    return 0 if falhas == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
