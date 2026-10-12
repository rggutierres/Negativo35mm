"""
Configuração do neg35, guardada num arquivo `.env`.

Por que um .env e não constantes no código: pasta de origem, pasta de saída,
modelo de IA e prompt mudam com o tempo, e quem usa não deve precisar editar
Python para trocar um caminho.

ORDEM DE PRECEDÊNCIA (do mais forte para o mais fraco):
    variável de ambiente do sistema  >  arquivo .env  >  padrão do código

Isso permite testar com `set OPENROUTER_API_KEY=...` sem tocar no .env, e
manter o .env como configuração "de produção".

ATENÇÃO À SEGURANÇA: o .env guarda a chave de API em texto puro. Ele está no
.gitignore. Não versione, não mande por chat, e revogue a chave se vazar.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ENV_PADRAO = RAIZ / ".env"

# ---------------------------------------------------------------------------
# Prompt de restauração.
#
# O prompt "vibrant / 4K / modern camera technology" é uma armadilha: ele
# autoriza o modelo a REINVENTAR a foto. Testado com gpt-5-image-mini, o
# resultado foi uma imagem nova -- inventou uma segunda criança no colo do
# homem, mudou o ângulo da cabeça e trocou o fundo. Bonito e inútil.
#
# Este prompt é deliberadamente restritivo: diz o que fazer, o que NÃO fazer,
# e o que fazer na dúvida ("deixe suave em vez de inventar"). Também trata
# cor cruzada, que é o problema real de negativo antigo.
# ---------------------------------------------------------------------------
PROMPT_PADRAO = (
    "Restore this photograph. It is already a correct positive scan of a "
    "35mm color negative, so the colors are in the right orientation -- they "
    "just need correcting.\n"
    "\n"
    "This is RESTORATION, not reinterpretation. Your job is to recover what "
    "is there, not to create something new.\n"
    "\n"
    "DO:\n"
    "- correct the color cast and restore neutral, realistic skin tones\n"
    "- fix the faded, low-contrast look of an aged color negative by "
    "restoring proper black point, white point and midtone density\n"
    "- remove scanner noise, dust specks, scratches and film grain\n"
    "- keep natural skin pores, hair strands and fabric weave intact\n"
    "- apply modest, even sharpening\n"
    "- preserve the original framing, aspect ratio and perspective exactly\n"
    "\n"
    "DO NOT:\n"
    "- change, beautify, reshape, slim or age any face\n"
    "- change the identity, expression, pose, gaze or clothing of any person\n"
    "- add or remove people, objects, text or background elements\n"
    "- replace the background or change its content\n"
    "- add a vignette, a color grade, a filter, or a cinematic look\n"
    "- over-saturate; this is a family photograph, not an advertisement\n"
    "- crop, reframe, zoom or change the image dimensions\n"
    "\n"
    "If a detail is unrecoverable, leave it soft rather than inventing it. "
    "The result must be recognisably the same photograph and the same people, "
    "only cleaner and correctly colored."
)


@dataclass
class Config:
    """Todas as configurações do neg35."""

    # -- pastas de trabalho
    pasta_origem: str = r"E:\Bkp\GoogleDrive\Negativo35mm\RAW"
    pasta_positivo: str = r"E:\Bkp\GoogleDrive\Negativo35mm\Positivo"
    pasta_restaurada: str = r"E:\Bkp\GoogleDrive\Negativo35mm\Restaurada"

    # -- Etapa 2 (IA)
    provedor: str = "openrouter"
    modelo: str = "google/gemini-2.5-flash-image"
    openrouter_api_key: str = ""
    gemini_api_key: str = ""
    prompt: str = PROMPT_PADRAO

    # -- ajustes do pipeline local (etapa 1)
    filme: str = "generico"
    saturacao: float = 1.15
    nitidez: float = 0.40
    balanco: float = 0.90

    # -- operação
    max_lado_envio: int = 1536
    pular_restauradas: bool = True
    # Pula a restauração por IA quando a máscara laranja chega fraca.
    #
    # Quando o decodificador aplica balanço de branco (é o que o fallback do
    # ImageMagick faz), o positivo sai lavado e a IA NÃO recupera: testado,
    # devolveu imagem borrada e esverdeada. Melhor não gastar.
    # Coloque false para restaurar mesmo assim.
    pular_mascara_fraca: bool = True


# Chaves do .env -> nomes de campo, e o padrão.
CAMPOS = {f.name: f for f in fields(Config)}


# Campos que aceitam quebra de linha codificada como "\n" no .env.
# Só estes desescapam. NÃO faça isso em caminhos do Windows: um caminho como
# E:\Bkp\GoogleDrive\Negativo35mm\RAW contém a sequência "\N", e desescapar
# \"\\n\" de forma genérica transformaria o caminho em lixo
# ("E:\Bkp\GoogleDrive" + quebra de linha + "egativo35mm\RAW").
CAMPOS_MULTILINHA = {"prompt"}


def _converter(nome: str, valor: str, atual):
    """Converte o texto do .env para o tipo do campo."""
    if isinstance(atual, bool):
        return valor.strip().lower() in ("1", "true", "sim", "yes", "on")
    if isinstance(atual, int):
        return int(float(valor))
    if isinstance(atual, float):
        return float(valor)
    if nome in CAMPOS_MULTILINHA:
        return valor.replace("\\n", "\n")
    return valor


def ler_env(caminho: Path) -> dict[str, str]:
    """Lê o .env como dicionário simples. Sem dependência externa."""
    dados: dict[str, str] = {}
    if not caminho.exists():
        return dados
    for bruta in caminho.read_text(encoding="utf-8").splitlines():
        linha = bruta.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        dados[chave.strip()] = valor.strip()
    return dados


def carregar(
    caminho: Path | None = None,
    usar_ambiente: bool = True,
) -> Config:
    """
    Monta a Config: padrão -> .env -> variável de ambiente.

    usar_ambiente=True deixa uma variável de sistema sobrepor o .env, o que
    é útil para testar sem mexer na configuração salva.
    """
    # ATENÇÃO: resolva o caminho AQUI. Passar `caminho` adiante sem resolver
    # fazia ler_env(None) cair no .env padrão, ignorando um --env explícito.
    caminho = Path(caminho) if caminho is not None else ENV_PADRAO
    dados = ler_env(caminho)
    cfg = Config()

    for nome, campo in CAMPOS.items():
        if nome in dados:
            try:
                setattr(cfg, nome, _converter(nome, dados[nome], getattr(cfg, nome)))
            except (ValueError, TypeError):
                pass  # valor inválido no .env: mantém o padrão

    if usar_ambiente:
        # Variáveis de ambiente ganham do .env.
        mapa = {
            "OPENROUTER_API_KEY": "openrouter_api_key",
            "GEMINI_API_KEY": "gemini_api_key",
            "GOOGLE_API_KEY": "gemini_api_key",
            "NEG35_PASTA_ORIGEM": "pasta_origem",
            "NEG35_PASTA_POSITIVO": "pasta_positivo",
            "NEG35_PASTA_RESTAURADA": "pasta_restaurada",
            "NEG35_MODELO": "modelo",
            "NEG35_PROVEDOR": "provedor",
        }
        for var, campo in mapa.items():
            v = os.environ.get(var)
            if v:
                setattr(cfg, campo, v)

    return cfg


def salvar(cfg: Config, caminho: Path | None = None) -> Path:
    """Grava a Config no .env, preservando comentários de cabeçalho."""
    caminho = Path(caminho) if caminho is not None else ENV_PADRAO
    caminho.parent.mkdir(parents=True, exist_ok=True)

    d = asdict(cfg)
    linhas = [
        "# neg35 -- configuração",
        "#",
        "# A chave de API fica aqui em texto puro. Este arquivo está no .gitignore.",
        "# Se a chave vazar, revogue no provedor e gere outra.",
        "#",
        "# Precedência: variável de ambiente > este arquivo > padrão do código.",
        "",
        "# ---------- pastas de trabalho ----------",
        f"pasta_origem={d['pasta_origem']}",
        f"pasta_positivo={d['pasta_positivo']}",
        f"pasta_restaurada={d['pasta_restaurada']}",
        "",
        "# ---------- Etapa 2: restauração por IA ----------",
        "# Modelos com saída de imagem. Lista atual: ... -m neg35.cli modelos",
        "#   google/gemini-2.5-flash-image   ~$0,039/imagem  (recomendado)",
        "#   google/gemini-nano-banana-2.1   ~$0,039/imagem",
        "#   openai/gpt-5-image-mini         ~$0,010/imagem  ATENÇÃO: alucina,",
        "#       testado e ele inventou uma pessoa que não existe na foto",
        f"provedor={d['provedor']}",
        f"modelo={d['modelo']}",
        f"openrouter_api_key={d['openrouter_api_key']}",
        f"gemini_api_key={d['gemini_api_key']}",
        "",
        "# ---------- ajustes do pipeline local (etapa 1) ----------",
        f"filme={d['filme']}",
        f"saturacao={d['saturacao']}",
        f"nitidez={d['nitidez']}",
        f"balanco={d['balanco']}",
        "",
        "# ---------- operação ----------",
        "# Reduz o lado maior antes de enviar. O modelo normaliza a resolução",
        "# internamente, então mandar 7 MP não melhora nada e gasta upload.",
        f"max_lado_envio={d['max_lado_envio']}",
        "# Pula fotos que já têm resultado na pasta Restaurada.",
        f"pular_restauradas={'true' if d['pular_restauradas'] else 'false'}",
        "# Pula a restauração por IA quando a máscara laranja chega fraca ao",
        "# ponto da IA não conseguir recuperar (testado: ela devolve borrado e",
        "# esverdeado). Isso acontece quando o decodificador aplicou balanço de",
        "# branco -- típico do fallback do ImageMagick em DNG não suportado.",
        "# Coloque false para gastar mesmo assim.",
        f"pular_mascara_fraca={'true' if d['pular_mascara_fraca'] else 'false'}",
        "",
        "# ---------- prompt de restauração ----------",
        "# Use \\n para quebrar linha. Mantenha as proibições: são elas que",
        "# impedem o modelo de inventar rostos e fundos.",
        "prompt=" + str(d["prompt"]).replace("\n", "\\n"),
        "",
    ]
    caminho.write_text("\n".join(linhas), encoding="utf-8")
    return caminho


def garantir_env(caminho: Path | None = None) -> tuple[Config, Path, bool]:
    """
    Carrega o .env; se não existir, cria com os padrões.

    Devolve (config, caminho, foi_criado).
    """
    caminho = Path(caminho) if caminho is not None else ENV_PADRAO
    criado = not caminho.exists()
    cfg = carregar(caminho)
    if criado:
        salvar(cfg, caminho)
    return cfg, caminho, criado
