"""
Prepara um ambiente Python no projeto, contornando dois problemas do Windows
neste ambiente:

1. %TEMP% é bloqueado pelo sandbox -> o pip não consegue desempacotar.
   Solução: apontar TMP/TEMP para .tmp dentro do projeto.
2. pip resolver/rede trava no proxy -> baixamos as wheels direto do PyPI
   por HTTPS e instalamos offline com --no-index.

Resultado: .venv/Scripts/python.exe com numpy, Pillow, rawpy e requests.

    python tools/preparar_ambiente.py
"""

from __future__ import annotations

import json
import ssl
import subprocess
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
WHEELS = RAIZ / "wheels"
TMP = RAIZ / ".tmp"
VENV = RAIZ / ".venv"
CA = RAIZ / "ca-empresa.pem"
PY313 = Path(r"C:\Program Files\Python313\python.exe")

# Pacote -> versão fixa (evita o resolutor e garante wheel disponível).
# 'requests' vem com as dependências puras dele, senão a instalação offline
# falha por falta de charset_normalizer/urllib3/idna/certifi.
PACOTES = {
    "numpy": "2.3.4",
    "pillow": "11.3.0",
    "rawpy": "0.27.1",
}

# Só wheels puras (py3-none-any): nenhuma compilação, nenhuma dependência
# transitiva pendente.
EXTRA_PURO = {
    "requests": "2.32.5",
    "urllib3": "2.5.0",
    "idna": "3.11",
    "certifi": "2025.10.5",
    "charset-normalizer": "3.4.4",
}


def ctx() -> ssl.SSLContext:
    if CA.exists():
        try:
            return ssl.create_default_context(cafile=str(CA))
        except Exception:  # noqa: BLE001
            pass
    return ssl.create_default_context()


def escolher_wheel(pacote: str, versao: str, tag: str) -> tuple[str, str] | None:
    """Devolve (nome, url) da wheel exata para a tag (ex.: cp313)."""
    url = f"https://pypi.org/pypi/{pacote}/{versao}/json"
    with urllib.request.urlopen(url, timeout=60, context=ctx()) as r:
        dados = json.load(r)

    arquivos = dados.get("urls", [])
    candidatos = [f for f in arquivos if f["filename"].endswith(".whl")]

    # 1) wheel específica do interpretador (cp313) para win_amd64
    for f in candidatos:
        n = f["filename"]
        if tag in n and "win_amd64" in n:
            return n, f["url"]
    # 2) wheel pura (py3-none-any)
    for f in candidatos:
        n = f["filename"]
        if "py3-none-any" in n or "py2.py3-none-any" in n:
            return n, f["url"]
    # 3) qualquer win_amd64
    for f in candidatos:
        n = f["filename"]
        if "win_amd64" in n:
            return n, f["url"]

    print(f"  !! sem wheel compatível. Disponíveis: "
          f"{[f['filename'] for f in candidatos][:8]}")
    return None


def baixar(nome: str, url: str) -> Path:
    destino = WHEELS / nome
    if destino.exists() and destino.stat().st_size > 1000:
        print(f"  já tem {nome}")
        return destino
    print(f"  baixando {nome}")
    with urllib.request.urlopen(url, timeout=600, context=ctx()) as r, destino.open("wb") as f:
        while True:
            bloco = r.read(1 << 20)
            if not bloco:
                break
            f.write(bloco)
    print(f"    {destino.stat().st_size:,} bytes")
    return destino


def main() -> int:
    if not PY313.exists():
        print(f"ERRO: não encontrei {PY313}", file=sys.stderr)
        print("Este script usa o Python 3.13 porque o rawpy não tem wheel")
        print("pronta para o 3.14 e compilar do zero trava.")
        return 1

    WHEELS.mkdir(exist_ok=True)
    TMP.mkdir(exist_ok=True)

    # Tag do interpretador alvo.
    tag = subprocess.run(
        [str(PY313), "-c", "import sysconfig;print(sysconfig.get_config_var('EXT_SUFFIX'))"],
        capture_output=True, text=True,
    ).stdout.strip()
    tag_curta = tag.split(".")[1] if tag.startswith(".") else "cp313"
    print(f"interpretador alvo: {PY313}")
    print(f"tag: {tag_curta}")
    print()

    print("=== baixando wheels ===")
    for pacote, versao in {**PACOTES, **EXTRA_PURO}.items():
        esc = escolher_wheel(pacote, versao, tag_curta)
        if not esc:
            print(f"  FALHOU: {pacote} {versao}")
            return 1
        baixar(*esc)

    print()
    print("=== criando .venv (se não existir) ===")
    if not (VENV / "Scripts" / "python.exe").exists():
        subprocess.run([str(PY313), "-m", "venv", str(VENV)], check=False)
    py = VENV / "Scripts" / "python.exe"
    if not py.exists():
        print("ERRO: não consegui criar o venv", file=sys.stderr)
        return 1

    purelib = subprocess.run(
        [str(py), "-c", "import sysconfig;print(sysconfig.get_paths()['purelib'])"],
        capture_output=True, text=True,
    ).stdout.strip()
    print(f"site-packages: {purelib}")

    print()
    print("=== instalando offline (sem tocar na rede) ===")
    env = {
        **_import_os_environ(),
        "TMP": str(TMP),
        "TEMP": str(TMP),
        "PYTHONPATH": str(WHEELS),
    }
    proc = subprocess.run(
        [str(PY313), "-m", "pip", "install", "--no-index", "--find-links",
         str(WHEELS), "--target", purelib, *PACOTES.keys()],
        capture_output=True, text=True, env=env,
    )
    saida = (proc.stdout + proc.stderr).splitlines()
    for linha in saida[-15:]:
        if "Failed to remove contents" in linha:
            continue
        print(f"  {linha}")

    print()
    print("=== verificação ===")
    teste = subprocess.run(
        [str(py), "-c",
         "import numpy, PIL, rawpy, requests;"
         "print('numpy', numpy.__version__);"
         "print('Pillow', PIL.__version__);"
         "print('rawpy', rawpy.__version__);"
         "print('libraw', rawpy.libraw_version);"
         "print('requests', requests.__version__)"],
        capture_output=True, text=True,
    )
    print(teste.stdout.strip() or teste.stderr.strip()[:600])
    if teste.returncode != 0:
        return 1

    print()
    print("Ambiente pronto. Use este interpretador:")
    print(f"  {py}")
    print()
    print("Exemplo:")
    print(f'  "{py}" tools/comparar_jpg_dng.py "E:\\Bkp\\GoogleDrive\\RAW"')
    return 0


def _import_os_environ() -> dict:
    import os

    return dict(os.environ)


if __name__ == "__main__":
    raise SystemExit(main())
