"""
Etapa 2 -- restauração via modelo de imagem (opcional, remota).

AVISO IMPORTANTE
----------------
Um LLM de TEXTO não faz isto. Só modelos com saída de imagem funcionam:
Gemini (linha "Nano Banana") ou OpenAI (gpt-image / gpt-5-image).
DeepSeek, Claude e GPT de texto aceitam imagem na ENTRADA mas devolvem
apenas TEXTO -- não existe endpoint de edição de imagem neles.

REGRA CRÍTICA: mande a imagem JÁ POSITIVA. Se você enviar o negativo cru,
o modelo não vai "inverter" -- vai INVENTAR uma cena nova que parece
plausível. A inversão é matemática (neg35.core); a restauração é IA.

Os nomes de modelo mudam rápido. Se der 404, liste os modelos atuais:
    GET https://openrouter.ai/api/v1/models
e filtre por `architecture.output_modalities` contendo "image".
"""

from __future__ import annotations

import base64
import io
import os
from dataclasses import dataclass, field

import numpy as np

from . import core

__all__ = [
    "Restauracao",
    "RestaurarErro",
    "PROMPT_PADRAO",
    "PROMPT_ESTRITO",
    "MODELOS",
    "TOKENS_POR_IMAGEM",
    "listar_modelos_de_imagem",
]

# O OpenRouter publica o preço por TOKEN de imagem. Uma imagem de ~1024px
# consome cerca de 1290 tokens, segundo o anúncio do próprio Google para o
# Gemini 2.5 Flash Image. Usamos isso só para converter em US$/imagem.
TOKENS_POR_IMAGEM = 1290

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
OPENAI_URL = "https://api.openai.com/v1/images/edits"

# Atualize estes nomes se o provedor aposentar o modelo.
MODELOS: dict[str, str] = {
    "openrouter": "google/gemini-nano-banana-2.1",
    "gemini": "gemini-2.5-flash-image",
    "openai": "gpt-image-1-mini",
}


PROMPT_PADRAO = (
    "Professional digital restoration of a 35mm film photograph. "
    "Remove scanning noise and film grain while preserving natural textures. "
    "Correct color balance for realistic skin tones, with vibrant but natural "
    "color saturation. Enhance facial features with high-definition sharpening. "
    "Upscale to contemporary 4K resolution with professional studio clarity, "
    "keeping the authentic feel of the original shot but with modern optical precision."
)

# Prompt restritivo: use este. O prompt "vibrant/4K/studio" acima tende a
# fazer o modelo ALUCINAR -- trocar rostos, suavizar pele demais e inventar
# textura que não existia no negativo.
PROMPT_ESTRITO = (
    "Restore this photograph, which is already a correct positive scan of a "
    "35mm color negative. Your job is restoration, NOT reinterpretation.\n"
    "\n"
    "DO:\n"
    "- remove scanner noise, dust residue and film grain\n"
    "- keep natural skin pores, hair strands and film micro-texture intact\n"
    "- produce neutral, realistic color balance with natural skin tones\n"
    "- apply modest, even sharpening and a clean 2x upscale\n"
    "- preserve the original framing and perspective exactly\n"
    "\n"
    "DO NOT:\n"
    "- change, beautify, slim, age or reshape any face\n"
    "- change identity, expression, pose, clothing or background\n"
    "- add objects, people, text or texture that are not in the source\n"
    "- add a vignette, a filter, or a cinematic color grade\n"
    "- over-saturate; this is a restoration, not an advertisement\n"
    "\n"
    "If a detail is unrecoverable, leave it soft rather than inventing it. "
    "The result must be recognisably the same photograph, only cleaner."
)


class RestaurarErro(RuntimeError):
    """Falha ao chamar a API de restauração."""


@dataclass
class Restauracao:
    """Chama um modelo de imagem para restaurar um positivo já pronto."""

    provedor: str = "openrouter"
    modelo: str | None = None
    api_key: str | None = None
    prompt: str = PROMPT_ESTRITO
    timeout: float = 240.0
    extras: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.modelo is None:
            self.modelo = MODELOS.get(self.provedor)
        if self.modelo is None:
            raise RestaurarErro(
                f"Provedor desconhecido: {self.provedor!r}. Use um de {sorted(MODELOS)}."
            )
        if self.api_key is None:
            self.api_key = _chave_do_ambiente(self.provedor)

    # ------------------------------------------------------------------
    def restaurar(self, positivo: np.ndarray) -> np.ndarray:
        """Positivo [0,1] float -> positivo restaurado [0,1] float."""
        png = _para_png_b64(positivo)
        if self.provedor == "openrouter":
            dados = self._openrouter(png)
        elif self.provedor == "gemini":
            dados = self._gemini(png)
        elif self.provedor == "openai":
            dados = self._openai(png)
        else:
            raise RestaurarErro(f"Provedor não implementado: {self.provedor}")
        return _de_png(dados)

    # ------------------------------------------------------------------
    def _openrouter(self, png_b64: str) -> bytes:
        """OpenRouter: um único formato OpenAI-compatible para todos os modelos."""
        corpo = {
            "model": self.modelo,
            "modalities": ["image", "text"],
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self.prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{png_b64}"},
                        },
                    ],
                }
            ],
        }
        r = _post(
            OPENROUTER_URL,
            corpo,
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                # Cabeçalhos de atribuição que o OpenRouter usa para ranking.
                "HTTP-Referer": "https://github.com/neg35",
                "X-Title": "neg35",
            },
            self.timeout,
        )
        if r.status_code != 200:
            raise RestaurarErro(f"OpenRouter HTTP {r.status_code}: {r.text[:600]}")

        j = r.json()
        msg = (j.get("choices") or [{}])[0].get("message", {})
        return _extrair_imagem_openai(msg, j)

    # ------------------------------------------------------------------
    def _gemini(self, png_b64: str) -> bytes:
        url = GEMINI_URL.format(modelo=self.modelo)
        corpo = {
            "contents": [
                {
                    "parts": [
                        {"text": self.prompt},
                        {"inline_data": {"mime_type": "image/png", "data": png_b64}},
                    ]
                }
            ]
        }
        r = _post(
            url,
            corpo,
            {"Content-Type": "application/json", "x-goog-api-key": self.api_key},
            self.timeout,
        )
        if r.status_code != 200:
            raise RestaurarErro(f"Gemini HTTP {r.status_code}: {r.text[:600]}")

        j = r.json()
        for cand in j.get("candidates", []):
            for parte in cand.get("content", {}).get("parts", []):
                dado = parte.get("inlineData") or parte.get("inline_data")
                if dado and dado.get("data"):
                    return base64.b64decode(dado["data"])
        raise RestaurarErro(f"Gemini não devolveu imagem. Resposta: {str(j)[:600]}")

    # ------------------------------------------------------------------
    def _openai(self, png_b64: str) -> bytes:
        """Endpoint /images/edits exige multipart/form-data."""
        import requests

        arquivos = {"image": ("negativo.png", base64.b64decode(png_b64), "image/png")}
        dados = {"model": self.modelo, "prompt": self.prompt, "n": "1"}
        dados.update({k: str(v) for k, v in self.extras.items()})

        r = requests.post(
            OPENAI_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            files=arquivos,
            data=dados,
            timeout=self.timeout,
        )
        if r.status_code != 200:
            raise RestaurarErro(f"OpenAI HTTP {r.status_code}: {r.text[:600]}")

        j = r.json()
        itens = j.get("data") or []
        if not itens:
            raise RestaurarErro(f"OpenAI não devolveu imagem. Resposta: {str(j)[:600]}")

        item = itens[0]
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"])

        url = item.get("url")
        if url:
            img = requests.get(url, timeout=self.timeout)
            img.raise_for_status()
            return img.content

        raise RestaurarErro("OpenAI devolveu item sem b64_json nem url.")


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _chave_do_ambiente(provedor: str) -> str:
    nomes = {
        "openrouter": ("OPENROUTER_API_KEY",),
        "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        "openai": ("OPENAI_API_KEY",),
    }[provedor]
    for n in nomes:
        v = os.environ.get(n)
        if v:
            return v
    raise RestaurarErro(
        f"Falta a chave de API. Defina {nomes[0]} (ou passe api_key=...)."
    )


def _post(url: str, corpo: dict, headers: dict, timeout: float):
    try:
        import requests
    except ImportError as e:  # pragma: no cover
        raise RestaurarErro("Instale 'requests': pip install requests") from e

    try:
        return requests.post(url, json=corpo, headers=headers, timeout=timeout)
    except requests.exceptions.SSLError as e:
        raise RestaurarErro(_dica_tls(e)) from e
    except requests.exceptions.ConnectionError as e:
        raise RestaurarErro(
            "Não consegui conectar em "
            f"{url.split('/')[2]}. Verifique a internet, o proxy corporativo e "
            f"o firewall.\nDetalhe: {e}\n{_dica_tls(e)}"
        ) from e


def _dica_tls(erro: Exception) -> str:
    """
    Explica as causas prováveis de falha de TLS.

    Ambientes corporativos costumam inspecionar HTTPS com um proxy que
    reassina os certificados. O Python (certifi) não conhece essa CA raiz e
    recusa a conexão, enquanto o navegador e o Node aceitam porque usam o
    repositório de certificados do Windows.
    """
    txt = str(erro)
    if "self-signed" in txt or "self signed" in txt or "certificate" in txt.lower():
        return (
            "\nCAUSA PROVÁVEL: proxy corporativo que reassina certificados TLS.\n"
            "O Python usa o pacote 'certifi' e não conhece a CA raiz da sua rede.\n"
            "\n"
            "SOLUÇÕES (da melhor para a pior):\n"
            "  1. Aponte o Python para a CA da empresa:\n"
            "       set REQUESTS_CA_BUNDLE=C:\\caminho\\para\\ca-corporativa.pem\n"
            "  2. Exporte os certificados raiz do Windows para um .pem e use acima.\n"
            "  3. Só como último recurso, desative a verificação (INSEGURO --\n"
            "     expõe sua chave de API a interceptação):\n"
            "       set PYTHONHTTPSVERIFY=0\n"
        )
    return ""


def _para_png_b64(positivo: np.ndarray) -> str:
    """float [0,1] -> PNG sem perdas em base64 (não use JPEG no meio)."""
    from PIL import Image

    pos = core.recortar(positivo)
    u8 = (pos * 255.0 + 0.5).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(u8, mode="RGB").save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _de_png(dados: bytes) -> np.ndarray:
    from PIL import Image

    im = Image.open(io.BytesIO(dados))
    if im.mode != "RGB":
        im = im.convert("RGB")
    return core.para_float(np.asarray(im))


def _extrair_imagem_openai(msg: dict, bruto: dict) -> bytes:
    """
    Extrai a imagem de uma resposta OpenAI-compatible.

    O OpenRouter devolve as imagens em `message.images`, no formato
    {"type":"image_url","image_url":{"url":"data:image/png;base64,..."}}.
    """
    for img in msg.get("images") or []:
        if isinstance(img, str) and img.startswith("data:"):
            return base64.b64decode(img.split(",", 1)[1])
        if isinstance(img, dict):
            url = (img.get("image_url") or {}).get("url") or img.get("url")
            if isinstance(url, str) and url.startswith("data:"):
                return base64.b64decode(url.split(",", 1)[1])
            if isinstance(url, str) and url.startswith("http"):
                import requests

                r = requests.get(url, timeout=120)
                r.raise_for_status()
                return r.content

    # Alguns modelos devolvem a imagem dentro de content como lista.
    conteudo = msg.get("content")
    if isinstance(conteudo, list):
        for parte in conteudo:
            if isinstance(parte, dict) and parte.get("type") in ("image_url", "output_image"):
                url = (parte.get("image_url") or {}).get("url") or parte.get("data")
                if isinstance(url, str) and url.startswith("data:"):
                    return base64.b64decode(url.split(",", 1)[1])

    raise RestaurarErro(
        "Não encontrei imagem na resposta. "
        f"Texto devolvido: {str(msg.get('content'))[:400]} | bruto: {str(bruto)[:200]}"
    )


def listar_modelos_de_imagem() -> list[tuple[str, str, str]]:
    """
    Consulta o OpenRouter e lista (id, preco_saida_imagem, contexto) dos
    modelos que devolvem imagem. Use isto quando um modelo for aposentado.
    """
    import requests

    try:
        r = requests.get("https://openrouter.ai/api/v1/models", timeout=60)
        r.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise RestaurarErro(
            f"Falha ao consultar o OpenRouter: {e}\n{_dica_tls(e)}"
        ) from e

    saida = []
    for m in r.json().get("data", []):
        arq = m.get("architecture") or {}
        if "image" in (arq.get("output_modalities") or []):
            saida.append(
                (
                    m.get("id", "?"),
                    (m.get("pricing") or {}).get("image_output", "?"),
                    str(m.get("context_length", "?")),
                )
            )
    return sorted(saida)
