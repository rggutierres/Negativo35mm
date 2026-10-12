"""
Baixa wheels do PyPI sem depender do pip resolver/rede lenta.

O pip neste ambiente trava (proxy corporativo). Aqui consultamos a API JSON
do PyPI, escolhemos a wheel exata para a versão do Python e baixamos por
HTTPS direto, que funciona.

    python tools/baixar_wheels.py
"""

from __future__ import annotations

import json
import ssl
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DEST = RAIZ / "wheels"

# (pacote, versão, precisa ser binária?)
ALVOS = [
    ("rawpy", "0.27.1", True),
]

CA = RAIZ / "ca-empresa.pem"


def contexto_ssl() -> ssl.SSLContext:
    """Usa o bundle com as CAs corporativas quando ele existir."""
    if CA.exists():
        try:
            return ssl.create_default_context(cafile=str(CA))
        except Exception:  # noqa: BLE001
            pass
    return ssl.create_default_context()


def buscar_url(pacote: str, versao: str, tag: str) -> str | None:
    ctx = contexto_ssl()
    url = f"https://pypi.org/pypi/{pacote}/{versao}/json"
    print(f"consultando {url}")
    with urllib.request.urlopen(url, timeout=60, context=ctx) as r:
        dados = json.load(r)

    arquivos = dados.get("urls", [])
    print(f"  {len(arquivos)} arquivos na versão {versao}")

    # Preferência: wheel que casa com a tag do interpretador (ex.: cp313).
    for f in arquivos:
        nome = f["filename"]
        if tag in nome and nome.endswith(".whl") and "win_amd64" in nome:
            return f["url"]

    # Fallback: qualquer wheel win_amd64.
    for f in arquivos:
        nome = f["filename"]
        if nome.endswith(".whl") and "win_amd64" in nome:
            return f["url"]

    print("  nenhuma wheel win_amd64 encontrada. Disponíveis:")
    for f in arquivos[:12]:
        print(f"    {f['filename']}")
    return None


def baixar(url: str) -> Path:
    nome = url.rsplit("/", 1)[-1]
    destino = DEST / nome
    if destino.exists():
        print(f"  já existe: {nome} ({destino.stat().st_size:,} bytes)")
        return destino

    print(f"  baixando {nome}")
    ctx = contexto_ssl()
    with urllib.request.urlopen(url, timeout=300, context=ctx) as r, destino.open("wb") as f:
        while True:
            bloco = r.read(1 << 20)
            if not bloco:
                break
            f.write(bloco)
    print(f"  salvo: {destino.stat().st_size:,} bytes")
    return destino


def main() -> int:
    versao = sys.argv[1] if len(sys.argv) > 1 else None
    DEST.mkdir(parents=True, exist_ok=True)

    # Descobre a tag do interpretador que vai USAR o pacote (3.13).
    py313 = Path(r"C:\Program Files\Python313\python.exe")
    if py313.exists():
        import subprocess

        tag = subprocess.run(
            [str(py313), "-c",
             "import sysconfig;print(sysconfig.get_config_var('EXT_SUFFIX'))"],
            capture_output=True, text=True,
        ).stdout.strip()
        print(f"tag do Python 3.13: {tag}")
        tag_curta = tag.split(".")[0] if tag else "cp313"
    else:
        tag_curta = "cp313"

    for pacote, ver, _ in ALVOS:
        print(f"\n=== {pacote} {ver if not versao else versao} ===")
        url = buscar_url(pacote, versao or ver, tag_curta)
        if not url:
            print("  FALHOU: sem wheel compatível")
            return 1
        baixar(url)

    print()
    print("Agora instale sem rede (não baixa nada):")
    print(f'  "{py313}" -m pip install --no-index --find-links "{DEST}" rawpy')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
