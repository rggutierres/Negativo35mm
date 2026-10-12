"""
Orquestração: arquivo -> negativo -> positivo -> (IA) -> arquivo.

A ordem das etapas não é negociável:

    1. carregar          (RAW/DNG de preferência, JPEG em último caso)
    2. normalizar UMA vez para luz linear
    3. achar a base do filme  <-- parâmetro mais sensível do pipeline
    4. inverter
    5. balanço de branco  (antes do contraste!)
    6. contraste
    7. saturação
    8. nitidez            (depois de tudo)
    9. [opcional] IA para denoise/upscale
   10. codificar para sRGB e salvar / comparar

REGRA CRÍTICA SOBRE GAMA
------------------------
Tudo entre os passos 2 e 9 é LUZ LINEAR. A codificação sRGB acontece uma
única vez, no passo 10. Aplicar a decodificação de gama duas vezes encolhe
a máscara laranja ~3,3x e a imagem sai lavada, com o branco estourado.
Foi o bug que apareceu ao ler DNG com rawpy: a saída do LibRaw com
gamma=(1,1) JÁ é linear, então ela não pode passar por srgb_para_linear.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import api, core, post

__all__ = ["Parametros", "Resultado", "desenvolver", "salvar", "carregar"]

EXTENSOES_RAW = {".dng", ".cr2", ".cr3", ".nef", ".arw", ".raf", ".orf", ".rw2", ".pef"}


@dataclass
class Parametros:
    """Todos os botões do pipeline, com padrões conservadores."""

    filme: str = "generico"
    # None = detecta a máscara sozinho. Passe uma tupla para forçar.
    base_filme: tuple[float, float, float] | None = None
    ganhos: tuple[float, float, float] | None = None
    recorte_branco: float = 0.0

    balanco_forca: float = 0.85
    ponto_neutro: tuple[float, float, float] | None = None
    contraste_preto: float = 0.005
    contraste_branco: float = 0.995
    contraste_por_canal: bool = False
    gamma: float = 1.0

    saturacao: float = 1.12
    nitidez: float = 0.35
    nitidez_raio: float = 1.2
    nitidez_limiar: float = 0.02

    preto_e_branco: float = 0.0
    auto: bool = True

    # Etapa 2 (deixe None para não gastar API)
    restaurar: str | None = None          # "openrouter" | "gemini" | "openai"
    modelo_ia: str | None = None
    prompt_ia: str = api.PROMPT_ESTRITO


@dataclass
class Resultado:
    positivo: np.ndarray                  # luz LINEAR
    restaurado: np.ndarray | None = None  # luz LINEAR
    base_filme: np.ndarray | None = None
    ponto_neutro: np.ndarray | None = None
    etapas: dict[str, np.ndarray] = field(default_factory=dict)
    meta: dict = field(default_factory=dict)

    @property
    def final(self) -> np.ndarray:
        return self.restaurado if self.restaurado is not None else self.positivo


# ----------------------------------------------------------------------
def _aplicar_exif(img: np.ndarray, orientacao: int) -> np.ndarray:
    """Aplica a rotação do EXIF, que o Pillow NÃO faz automaticamente."""
    if orientacao in (None, 0, 1):
        return img
    if orientacao == 2:
        return img[:, ::-1]
    if orientacao == 3:
        return img[::-1, ::-1]
    if orientacao == 4:
        return img[::-1, :]
    if orientacao == 5:
        return np.swapaxes(img, 0, 1)
    if orientacao == 6:
        return np.rot90(img, k=3)
    if orientacao == 7:
        return np.rot90(np.swapaxes(img, 0, 1), k=2)
    if orientacao == 8:
        return np.rot90(img, k=1)
    return img


def carregar(caminho: str | Path, para_linear: bool = True) -> np.ndarray:
    """
    Lê a imagem como float [0,1].

    para_linear=True (padrão): devolve LUZ LINEAR, que é o que o pipeline
    espera. De DNG vem direto do decodificador; de JPEG/PNG aplica a
    decodificação de gama sRGB.

    para_linear=False: devolve sRGB, para inspeção ou exibição.
    """
    caminho = Path(caminho)
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho}")

    if caminho.suffix.lower() in EXTENSOES_RAW:
        return _carregar_raw(caminho, para_linear=para_linear)

    try:
        from PIL import Image

        with Image.open(caminho) as im:
            orientacao = 1
            try:
                orientacao = im.getexif().get(0x0112, 1)
            except Exception:  # noqa: BLE001
                pass
            if im.mode != "RGB":
                im = im.convert("RGB")
            bruto = np.asarray(im)
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("Instale 'Pillow': pip install Pillow") from e

    bruto = _aplicar_exif(bruto, orientacao)
    if para_linear:
        return core.normalizar(bruto, linear=False)
    return core.recortar(bruto)


def _carregar_raw(caminho: Path, para_linear: bool) -> np.ndarray:
    """
    DNG/RAW -> float.

    rawpy (LibRaw) é preferido. Alguns DNG do Expert RAW (compressão
    proprietária, DNG v1.7) não são suportados e levantam erro; nesse caso
    caímos para o ImageMagick.

    ORIENTAÇÃO: ao contrário do JPEG, o DNG normalmente NÃO carrega tag de
    orientação -- os pixels vêm na orientação do sensor. Se você fotografou
    com o celular girado, o negativo "deitado" chega aqui em pé. Isso não é
    erro: é o comportamento correto. Gire na exibição, ou use
    render.ampliar/girar, não mexa nos pixels originais.
    """
    try:
        import rawpy

        with rawpy.imread(str(caminho)) as raw:
            # gamma=(1,1) => luz linear, sem curva aplicada pela câmera.
            rgb = raw.postprocess(
                gamma=(1, 1),
                no_auto_bright=True,
                output_bps=16,
                use_camera_wb=False,
                output_color=rawpy.ColorSpace.sRGB,
            )
        lin = core.para_float(rgb)
        return lin if para_linear else core.linear_para_srgb(lin)
    except ImportError:
        pass
    except Exception as e:  # noqa: BLE001
        # Não aborta: tenta o ImageMagick antes de desistir.
        #
        # Causa conhecida: vários DNG do Expert RAW do S22 Ultra (compressão 7,
        # LinearRaw, 12 bits) fazem o LibRaw 0.22.1 levantar LibRawDataError no
        # postprocess, mesmo com os metadados idênticos aos de arquivos que
        # funcionam. Testamos half_size, output_bps, output_color, demosaic e
        # mais -- NENHUM parâmetro contorna. É limitação do decodificador.
        #
        # O ImageMagick usa a mesma LibRaw mas tolera o bloco corrompido, então
        # é a via prática. A diferença de fidelidade é pequena para negativo
        # (medimos R/B da máscara em 4,1 contra 4,3 do caminho LibRaw).
        print(f"    (rawpy não decodificou: {type(e).__name__} -- "
              f"usando ImageMagick, leve perda de fidelidade)")

    return _carregar_via_imagemagick(caminho, para_linear=para_linear)


def _carregar_via_imagemagick(caminho: Path, para_linear: bool) -> np.ndarray:
    """
    Fallback: pede ao ImageMagick o PNG de 16 bits pelo STDOUT.

    Note o `PNG:-`: a saída vai para o pipe, não para um arquivo temporário.
    Isso evita depender de %TEMP%, que pode estar bloqueado por política, e
    evita escrever em disco à toa.

    O ImageMagick aplica o perfil da câmera e entrega sRGB pronto. É MENOS
    fiel que o LibRaw (perdemos a linearidade crua), mas é muito melhor que
    não ler nada -- e para DNG de compressão proprietária pode ser a única
    opção.
    """
    import io
    import subprocess

    proc = subprocess.run(
        ["magick", str(caminho), "-depth", "16", "PNG:-"],
        capture_output=True,
    )
    if proc.returncode != 0 or not proc.stdout:
        erro = proc.stderr.decode("utf-8", "replace").strip()[:200]
        raise RuntimeError(
            f"Não consegui decodificar {caminho.name}. ImageMagick: {erro}"
        )

    from PIL import Image

    with Image.open(io.BytesIO(proc.stdout)) as im:
        bruto = np.asarray(im.convert("RGB"))

    # O ImageMagick entrega sRGB, então aqui a decodificação de gama É devida.
    if para_linear:
        return core.normalizar(bruto, linear=False)
    return core.recortar(bruto)


# ----------------------------------------------------------------------
def desenvolver(
    origem: str | Path | np.ndarray,
    params: Parametros | None = None,
    salvar_em: str | Path | None = None,
    manter_etapas: bool = True,
    entrada_linear: bool | None = None,
) -> Resultado:
    """
    Pipeline completo sobre um arquivo (ou array já carregado).

    Se passar um ARRAY, ele é tratado como sRGB por padrão. Para passar luz
    linear (saída de rawpy, por exemplo) use entrada_linear=True.

    Devolve um Resultado; `res.final` é a melhor imagem em LUZ LINEAR.
    Use salvar() para codificar para sRGB.
    """
    p = params or Parametros()

    etapas: dict[str, np.ndarray] = {}
    meta: dict = {}

    def registrar(nome: str, img: np.ndarray) -> None:
        if manter_etapas:
            etapas[nome] = img

    # -- 1/2) obter luz linear
    if isinstance(origem, np.ndarray):
        linear = bool(entrada_linear) if entrada_linear is not None else False
        lin = core.normalizar(origem, linear=linear)
        meta["origem"] = "array"
        meta["entrada_linear"] = linear
    else:
        # carregar() já devolve linear.
        lin = carregar(origem, para_linear=True)
        meta["origem"] = str(Path(origem).name)
        meta["entrada_linear"] = True

    srgb_ref = core.linear_para_srgb(lin)
    registrar("00_negativo", srgb_ref)

    # -- 3) base do filme
    if p.base_filme is None:
        base = core.detectar_base_do_filme(lin)
        meta["base_detectada"] = True
    else:
        base = np.asarray(p.base_filme, dtype=np.float64).reshape(3)
        meta["base_detectada"] = False
    meta["base_filme"] = base.tolist()

    # Correção de exposição: se a base detectada está muito escura, o
    # negativo está subexposto e nenhuma curva salva. Avisa em vez de fingir.
    if float(np.max(base)) < 0.22:
        meta["aviso"] = (
            "Base do filme muito escura (negativo subexposto?). "
            "Refaça a captura com mais luz ou exposição maior."
        )
    elif float(np.max(base)) > 0.985:
        meta["aviso"] = (
            "Base do filme estourada (clipping). Reduza a exposição na captura."
        )

    # -- ganhos por filme (ou explícitos)
    if p.ganhos is not None:
        ganhos = p.ganhos
    else:
        ganhos = core.GANHOS_POR_FILME.get(p.filme.lower(), (0.0, 0.0, 0.0))
    meta["ganhos"] = list(ganhos)

    # -- 4) inverter
    positivo = core.inverter_negativo(
        lin,
        base_filme=base,
        ganhos=ganhos,
        forcar_neutro=True,
        recorte_branco=p.recorte_branco,
    )
    registrar("01_invertido", core.linear_para_srgb(positivo))

    # -- 5..8) ajustes, tudo em linear
    ref = post.medir_neutro(positivo)
    meta["ponto_neutro"] = ref.tolist()

    if p.auto:
        positivo = post.auto_balanco(
            positivo, forca=p.balanco_forca, ponto_neutro=p.ponto_neutro
        )
        registrar("02_balanco", core.linear_para_srgb(positivo))

        positivo = post.esticar_contraste(
            positivo,
            preto=p.contraste_preto,
            branco=p.contraste_branco,
            por_canal=p.contraste_por_canal,
            gamma=p.gamma,
        )
        registrar("03_contraste", core.linear_para_srgb(positivo))

        if abs(p.saturacao - 1.0) > 1e-6:
            positivo = post.saturacao(positivo, p.saturacao)
        registrar("04_saturacao", core.linear_para_srgb(positivo))

        if p.nitidez > 0.0:
            positivo = post.nitidez(
                positivo, quantia=p.nitidez, raio=p.nitidez_raio, limiar=p.nitidez_limiar
            )
        registrar("05_nitidez", core.linear_para_srgb(positivo))

    # -- P&B quando o filme é monocromático
    pb = p.preto_e_branco
    if pb <= 0.0 and p.filme.lower() in {"hp5", "tri-x400", "pretoebranco"}:
        pb = 1.0
    if pb > 0.0:
        positivo = post.preto_e_branco(positivo, pb)
        registrar("06_pretoebranco", core.linear_para_srgb(positivo))

    resultado = Resultado(
        positivo=positivo,
        base_filme=base,
        ponto_neutro=ref,
        etapas=etapas,
        meta=meta,
    )

    # -- 9) restauração por IA (opcional)
    if p.restaurar:
        rest = api.Restauracao(
            provedor=p.restaurar, modelo=p.modelo_ia, prompt=p.prompt_ia
        )
        # A API trabalha em sRGB (é o que ela espera); voltamos a linear.
        resposta = rest.restaurar(core.linear_para_srgb(positivo))
        resultado.restaurado = core.normalizar(resposta, linear=False)
        resultado.meta["restaurado_por"] = f"{p.restaurar}:{rest.modelo}"
        registrar("07_restaurado", core.linear_para_srgb(resultado.restaurado))

    # -- 10) salvar (codifica para sRGB aqui, uma única vez)
    if salvar_em is not None:
        salvar(resultado.final, salvar_em)

    return resultado


# ----------------------------------------------------------------------
def salvar(img: np.ndarray, caminho: str | Path, linear: bool = True) -> Path:
    """
    Salva float [0,1] como PNG.

    linear=True (padrão): a entrada é LUZ LINEAR e será codificada para sRGB.
        É o padrão porque o pipeline inteiro trabalha em linear.
    linear=False: a entrada JÁ está em sRGB; salva como está.

    O parâmetro é obrigatório de propósito. Um "detector automático" de gama
    é frágil: uma foto em sRGB com mediana baixa (cena escura) seria
    codificada duas vezes e sairia lavada. Melhor ser explícito.

    Exceção: se a entrada já for uint8, ela é tratada como sRGB pronta e não
    é recodificada -- isso deixa os compositores de render.py
    (que devolvem uint8) funcionarem sem o chamador pensar no assunto.

    Nunca use JPEG no meio do pipeline; PNG preserva o que foi calculado.
    """
    from PIL import Image

    a = np.asarray(img)
    if a.dtype == np.uint8:
        linear = False
        a = a.astype(np.float64) / 255.0
    else:
        a = a.astype(np.float64)
        if a.size and float(a.max()) > 1.5:
            a = a / 255.0

    if a.ndim == 2:
        a = np.stack([a, a, a], axis=-1)
    if a.shape[-1] == 4:
        a = a[..., :3]
    a = np.clip(a, 0.0, 1.0)

    if linear:
        a = core.linear_para_srgb(a)

    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    u8 = (a * 255.0 + 0.5).astype(np.uint8)
    im = Image.fromarray(u8, mode="RGB")

    # Grava num arquivo temporário e só então renomeia. Se algo falhar no meio
    # (disco cheio, permissão, arquivo travado pelo sincronizador do Drive),
    # não fica um arquivo truncado no destino passando por bom.
    #
    # O formato é resolvido pelo SUFIXO ORIGINAL e passado explicitamente: o
    # nome temporário termina em ".tmp" e o Pillow não infere formato por ele
    # (era o que quebrava com "unknown file extension: .tmp").
    sufixo = caminho.suffix.lower()
    if sufixo in {".jpg", ".jpeg"}:
        formato, opcoes = "JPEG", {"quality": 95}
    elif sufixo in {".tif", ".tiff"}:
        formato, opcoes = "TIFF", {}
    else:
        formato, opcoes = "PNG", {}

    temp = caminho.with_name(caminho.name + ".tmp")
    try:
        im.save(temp, format=formato, **opcoes)
        temp.replace(caminho)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    return caminho
