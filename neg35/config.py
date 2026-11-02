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
from dataclasses import asdict, dataclass, field, fields
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


def pasta_local_padrao() -> Path:
    """
    Pasta local sugerida para a SAÍDA (positivos e restauradas).

    Por que a saída é local e não na nuvem: a unidade que o Google Drive cria
    no Windows (letra E:, no seu caso) é um sistema de arquivos virtual.
    Escrever nela por programa falha com "Acesso negado" em muitas
    configurações -- foi exatamente o erro que apareceu. O Drive aceita bem a
    LEITURA dos originais, que é o que interessa.

    Desenho: origem na nuvem, resultado local. Para levar os resultados à
    nuvem depois, é só arrastar a pasta.
    """
    return Path.home() / "neg35"


def pastas_locais() -> tuple[str, str]:
    """(pasta de positivos, pasta de restauradas), sugeridas, em local."""
    base = pasta_local_padrao()
    return str(base / "positivo"), str(base / "restaurada")


def _gravavel(pasta: Path) -> bool:
    """Testa escrita de verdade (cria e apaga um arquivo)."""
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        t = pasta / "_neg35_teste.tmp"
        t.write_bytes(b"x")
        t.unlink()
        return True
    except OSError:
        return False


def pasta_de_queda() -> Path:
    """
    Pasta usada quando a pasta de saída configurada não aceita escrita.

    É a ÚLTIMA da lista de candidatas, e é justamente a que quase sempre
    funciona: fica ao lado do programa.

    A variável de ambiente `NEG35_PASTA_QUEDA` permite apontar para outro
    lugar -- os testes usam isso para não escrever (nem apagar) nada na pasta
    real do projeto, que pode conter o trabalho do usuário.
    """
    import os

    escolhida = os.environ.get("NEG35_PASTA_QUEDA")
    if escolhida:
        return Path(escolhida)
    return Path(__file__).resolve().parent.parent / "saida"


def pasta_local_gravavel(preferida: str | Path | None = None) -> Path:
    """
    Devolve a primeira pasta local em que dá para GRAVAR de verdade.

    Testar antes de escolher evita o pior cenário: o programa ser configurado
    para um caminho bonito que não aceita escrita, e o usuário só descobrir
    depois de converter tudo (ou de pagar a IA).

    Se `preferida` for dada e gravar, ela ganha -- assim respeitamos a escolha
    do usuário. Senão, tentamos ~/neg35 -> ~/Pictures/neg35 -> ~/Documents/neg35
    -> pasta de queda. A última quase sempre funciona.
    """
    if preferida:
        p = Path(preferida)
        if _gravavel(p):
            return p
    casa = Path.home()
    candidatas = [
        casa / "neg35",
        casa / "Pictures" / "neg35",
        casa / "Documents" / "neg35",
        pasta_de_queda(),
    ]
    for c in candidatas:
        if _gravavel(c):
            return c
    return candidatas[0]


def pastas_locais_gravaveis(preferida: str | Path | None = None) -> tuple[str, str]:
    """Como pastas_locais(), mas escolhendo o que comprovadamente grava."""
    base = pasta_local_gravavel(preferida)
    return str(base / "positivo"), str(base / "restaurada")


def testar_escrita_simples(pasta: Path) -> tuple[bool, str]:
    r"""
    Testa escrita de verdade. Sem dependência circular com o servidor.

    A mensagem inclui o CAMINHO e, quando a falha é de permissão, explica a causa
    mais comum nesta máquina: o ambiente virtual guardado dentro de C:\Temp.

    Isso foi medido, não é suposição: com o mesmo usuário e no mesmo instante,
    `.venv\Scripts\python.exe` (dentro de C:\Temp) falha com errno 13 ao gravar
    em E:, enquanto C:\neg35\venv e o Python do sistema gravam normal. O ACL da
    pasta estava liberado para "Usuários autenticados: Modify" nos dois casos.
    Ou seja: a restrição é do ambiente, não da pasta -- e o usuário não precisa
    "dar permissão" em cada pasta nova.
    """
    try:
        pasta.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return False, f"não foi possível criar {pasta} ({e.strerror or e})"
    t = pasta / "_neg35_teste.tmp"
    try:
        t.write_bytes(b"x")
        t.unlink()
        return True, ""
    except OSError as e:
        motivo = f"sem permissão de escrita em {pasta} ({e.strerror or e})"
        if getattr(e, "winerror", None) in (5, None) and e.errno in (13, None):
            motivo += (
                " -- se o ambiente Python estiver em C:\\Temp, ele só grava "
                "dentro de C:\\Temp nesta máquina; use o ambiente em "
                "C:\\neg35\\venv (é o que o run.cmd faz)"
            )
        return False, motivo


def _contar(pasta: Path, sufixo: str) -> int:
    if not pasta.is_dir():
        return 0
    try:
        return sum(1 for p in pasta.iterdir()
                   if p.is_file() and p.name.endswith(sufixo))
    except OSError:
        return 0


def candidatos_de_saida() -> list[dict]:
    """
    Locais possíveis para a saída, cada um TESTADO quanto a escrita.

    Existe porque a pasta certa depende da máquina do usuário. Numa delas,
    escrever no perfil do usuário pode ser negado -- então sugerir
    "C:\\Users\\<nome>\\neg35" seria um chute ruim. Aqui a tela só oferece o
    que funciona, e explica o que não funciona.

    Devolve uma lista com os graváveis primeiro, na ordem de preferência.
    """
    casa = Path.home()
    projeto = Path(__file__).resolve().parent.parent
    propostas = [
        ("Pictures", casa / "Pictures" / "neg35",
         "sua pasta de Imagens"),
        ("Documents", casa / "Documents" / "neg35",
         "sua pasta de Documentos"),
        ("home", casa / "neg35", "sua pasta de usuário"),
        ("projeto", pasta_de_queda(), "pasta ao lado do programa"),
    ]

    saida = []
    for chave, caminho, rotulo in propostas:
        ok, erro = testar_escrita_simples(caminho)
        saida.append({
            "chave": chave,
            "caminho": str(caminho),
            "rotulo": rotulo,
            "gravavel": ok,
            "erro": erro,
            "ja_tem": _contar(caminho / "positivo", "_positivo.png")
                      + _contar(caminho / "restaurada", "_restaurado.png"),
        })
    saida.sort(key=lambda c: not c["gravavel"])
    return saida


def pasta_cache_adobe(cfg: "Config") -> Path | None:
    """
    Onde guardar os DNG reconvertidos pelo Adobe. None = não usar cache.

    Ordem de decisão:

    1. `pasta_cache_adobe` do .env, se preenchida.
    2. A pasta IRMÃ dos positivos, **se já houver cache lá com arquivos**.
       Motivo: era o comportamento antigo, e essas conversões custam minutos.
       Jogar fora 26 arquivos de 43 MB para recomeçar seria desperdício.
    3. A pasta temporária do sistema -- lugar próprio para dado descartável.

    O cache existe porque o Adobe leva alguns segundos por arquivo. Ele NÃO é
    necessário para a correção em si: o positivo gerado já tem tudo. Apagar o
    cache é seguro, só custa tempo na próxima conversão.
    """
    escolhida = (cfg.pasta_cache_adobe or "").strip()
    if escolhida:
        p = Path(escolhida).expanduser()
    else:
        irma = Path(cfg.pasta_positivo).parent / "_adobe_convertido"
        if irma.is_dir() and any(irma.iterdir()):
            return irma
        import tempfile

        p = Path(tempfile.gettempdir()) / "neg35_adobe"

    if _gravavel(p):
        return p
    # Sem permissão no destino preferido: tenta a pasta temporária.
    import tempfile

    alternativa = Path(tempfile.gettempdir()) / "neg35_adobe"
    if str(alternativa) != str(p) and _gravavel(alternativa):
        return alternativa
    return None


@dataclass
class Config:
    """Todas as configurações do neg35."""

    # -- pastas de trabalho
    # A origem pode ficar na nuvem; positivos e restauradas ficam LOCAIS,
    # porque a unidade do Drive recusa escrita por programa.
    pasta_origem: str = r"E:\Bkp\GoogleDrive\Negativo35mm\RAW"
    pasta_positivo: str = field(default_factory=lambda: pastas_locais()[0])
    pasta_restaurada: str = field(default_factory=lambda: pastas_locais()[1])

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

    # -- curva de tom de exibição
    # O positivo é luz linear. Codificar direto para sRGB deixa a imagem mais
    # clara que o natural (parece lavada), porque negativo de filme tem
    # densidade baixa. A curva abaixo ancora a mediana de luminância num alvo.
    usar_curva: bool = True
    curva_alvo: float = 0.50     # mediana de luminância desejada, em sRGB
    curva_gamma: float = 0.0     # 0 = gama adaptativo por imagem; >0 = fixo
    curva_preto: float = 0.0     # levanta o ponto preto (véu de base)

    # -- conversão com o Adobe DNG Converter
    # Conserta DNG com bloco JPEG defeituoso, que o LibRaw não tolera.
    usar_adobe: bool = True
    adobe_exe: str = ""          # vazio = procura nos caminhos padrão
    # Onde guardar os DNG reconvertidos pelo Adobe.
    #
    # O Adobe regrava SEM compressão, então cada arquivo fica com ~43 MB (o
    # original tem ~14 MB). Vazio = pasta temporária do sistema, que é o lugar
    # certo para dado descartável.
    #
    # Se já existir cache na pasta irmã dos positivos (o comportamento antigo),
    # ele é REUSADO em vez de refeito -- recriar 26 arquivos custa minutos.
    pasta_cache_adobe: str = ""

    # -- operação
    max_lado_envio: int = 1536
    pular_restauradas: bool = True
    # Converte sozinho ao abrir a tela?
    #
    # Padrão: NÃO. Motivo prático: a conversão disparava a cada abertura da
    # página, então parecia "recomeçar do zero" toda vez -- mesmo já havendo
    # positivos prontos (que o programa pula corretamente, mas a tela não
    # deixava isso claro). Melhor o usuário mandar converter quando quiser,
    # com o botão que já existe.
    # Coloque true para o comportamento automático.
    converter_auto: bool = False

    # -- compensação de exposição da IA
    # A IA devolve o resultado mais escuro que o positivo. Medido em três
    # fotos: 0,234 a menos na mediana, precisando de ~1,6x de ganho.
    # Marcado, o programa iguala a mediana do resultado à do positivo.
    casar_exposicao: bool = True
    # Quanto da correção aplicar (1,0 = iguala tudo). Abaixo de 1 preserva um
    # pouco do contraste que o modelo deu de propósito.
    exposicao_forca: float = 0.85
    # Clareia a imagem ANTES de enviar à IA (multiplicador; 1,0 = não mexe).
    #
    # Por que isto existe: o modelo devolve mais escuro do que recebe, e ajustar
    # só a SAÍDA esbarra no limite de segurança do realce -- nas fotos medidas o
    # ganho ficou em 1,2 a 1,6x quando o alvo pedia mais. Clarear a ENTRADA
    # ataca a causa e não tem esse limite: o positivo já está em 0,61, então há
    # espaço antes de estourar.
    brilho_envio: float = 1.0
    # Recorta a borda do filme (furinhos, e o pedaço do quadro vizinho) antes de
    # enviar à IA.
    #
    # A detecção usa gradiente E luminância para achar o quadro, e a PROPORÇÃO
    # 3:2 do filme 35mm como trava: se o retângulo não tiver essa proporção, não
    # corta. Medido em fotos reais: corta 29-37% da imagem, e o que é descartado
    # tem gradiente 0,00000 e luminância ~1,00 (borda lisa e clara).
    recortar_bordas: bool = True
    # Deixa uma folga de borda, em fração do quadro. 0 = encosta no quadro.
    recorte_margem: float = 0.0
    # Pede à IA, no prompt, para remover a borda do filme e os furinhos.
    #
    # Isto é necessário porque o prompt original manda "preserve the original
    # framing exactly" e "do not crop": a IA obedecia e mantinha os furinhos. A
    # instrução nova resolve a contradição e diz que a borda do filme pode sair.
    #
    # Pode ser usado junto com `recortar_bordas` (corta aqui E avisa a IA) ou
    # sozinho (deixa a IA cortar).
    limpar_borda_no_prompt: bool = True
    # Acrescenta ao prompt os números MEDIDOS desta foto (exposição, sombras,
    # cast de cor), para o modelo receber informação que ele não tem como saber.
    # Medido: os ajustes necessários são sistemáticos, então isto é mais
    # confiável que pedir para um modelo de visão "adivinhar" os parâmetros.
    dica_por_foto: bool = True
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
        "# ---------- curva de tom de exibição ----------",
        "# O positivo é luz linear. Codificar direto para sRGB deixa a imagem",
        "# mais clara que o natural (parece lavada), porque negativo de filme",
        "# tem densidade baixa. A curva ancora a mediana de luminância no alvo.",
        "#",
        "# Medido: sem curva, a mediana fica em 0,70 (LibRaw) e 0,87 (Adobe).",
        "# Com a curva no alvo 0,50, as duas ficam consistentes.",
        f"usar_curva={'true' if d['usar_curva'] else 'false'}",
        "# Mediana de luminância desejada, em sRGB (0,50 = natural).",
        f"curva_alvo={d['curva_alvo']}",
        "# 0 = gama adaptativo por imagem (recomendado). >0 = gama fixo.",
        f"curva_gamma={d['curva_gamma']}",
        "# Levanta o ponto preto, em luz linear. Use se o negativo tiver véu.",
        f"curva_preto={d['curva_preto']}",
        "",
        "# ---------- Adobe DNG Converter ----------",
        "# Conserta DNG com bloco JPEG defeituoso -- o LibRaw aborta nesses,",
        "# o Adobe lê com tolerância e regrava sem compressão.",
        f"usar_adobe={'true' if d['usar_adobe'] else 'false'}",
        "# Vazio = procura nos caminhos padrão de instalação.",
        f"adobe_exe={d['adobe_exe']}",
        "# Onde guardar os DNG reconvertidos pelo Adobe. Vazio = pasta",
        "# temporária do sistema, que é o lugar próprio para dado descartável.",
        "#",
        "# O Adobe regrava SEM compressão: cada arquivo fica com ~43 MB (o",
        "# original tem ~14 MB). Apagar esta pasta é seguro -- só custa tempo",
        "# na próxima conversão, porque o cache é reusado entre execuções.",
        f"pasta_cache_adobe={d['pasta_cache_adobe']}",
        "",
        "# ---------- operação ----------",
        "# Reduz o lado maior antes de enviar. O modelo normaliza a resolução",
        "# internamente, então mandar 7 MP não melhora nada e gasta upload.",
        f"max_lado_envio={d['max_lado_envio']}",
        "# Converte sozinho ao abrir a tela? false = você manda pelo botão.",
        "# true faz a conversão começar assim que a página abre, o que pode",
        "# parecer que está refazendo tudo (ele pula o que já tem positivo).",
        f"converter_auto={'true' if d['converter_auto'] else 'false'}",
        "",
        "# ---------- compensação de exposição da IA ----------",
        "# A IA devolve o resultado mais escuro que o positivo. Medido em três",
        "# fotos: 0,234 a menos na mediana -- cerca de 1,6x de ganho para igualar.",
        "# Marcado, o programa iguala a mediana do resultado à do positivo.",
        f"casar_exposicao={'true' if d['casar_exposicao'] else 'false'}",
        "# Quanto da correção aplicar (1,0 = iguala tudo). Abaixo de 1 preserva",
        "# um pouco do contraste que o modelo deu de propósito.",
        f"exposicao_forca={d['exposicao_forca']}",
        "# Clareia a imagem ANTES de enviar à IA (1,0 = não mexe).",
        "# O modelo devolve mais escuro do que recebe; clarear a entrada ataca a",
        "# causa, e não esbarra no limite de segurança do realce.",
        f"brilho_envio={d['brilho_envio']}",
        "# Recorta a borda do filme (furinhos e pedaço do quadro vizinho) antes de",
        "# enviar à IA. Usa a proporção 3:2 do filme 35mm como trava: se o retângulo",
        "# detectado não tiver essa proporção, NÃO corta (evita cortar a foto).",
        f"recortar_bordas={'true' if d['recortar_bordas'] else 'false'}",
        "# Folga de borda a manter, em fração do quadro (0 = encosta no quadro).",
        f"recorte_margem={d['recorte_margem']}",
        "# Pede à IA, no prompt, para remover a borda do filme e os furinhos.",
        "# O prompt original manda preservar o enquadramento exato, então a IA",
        "# mantinha os furinhos; esta instrução resolve a contradição.",
        f"limpar_borda_no_prompt={'true' if d['limpar_borda_no_prompt'] else 'false'}",
        "# Acrescenta ao prompt os números medidos DESTA foto (exposição, sombras,",
        "# cast de cor). O modelo não tem como saber a exposição correta sozinho.",
        f"dica_por_foto={'true' if d['dica_por_foto'] else 'false'}",
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
