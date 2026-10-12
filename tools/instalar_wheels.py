"""
Instala as wheels extraindo direto com zipfile, sem usar pip.

Por que: o pip desempacota em %TEMP% (bloqueado pelo sandbox) e, mesmo com
TMP apontado para o projeto, cria subdiretórios temporários que a política
de escrita nega. Uma wheel é só um arquivo ZIP: extrair na mão elimina o
problema inteiro.

    python tools/instalar_wheels.py
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
WHEELS = RAIZ / "wheels"
SITE = RAIZ / ".venv" / "Lib" / "site-packages"


def main() -> int:
    if not SITE.parent.exists():
        print(f"ERRO: {SITE.parent} não existe. Rode tools/preparar_ambiente.py antes.")
        return 1

    arquivos = sorted(WHEELS.glob("*.whl"))
    if not arquivos:
        print(f"ERRO: nenhuma wheel em {WHEELS}")
        return 1

    print(f"destino: {SITE}")
    print(f"wheels : {len(arquivos)}")
    print()

    SITE.mkdir(parents=True, exist_ok=True)
    total = 0

    for whl in arquivos:
        print(f"{whl.name}")
        try:
            with zipfile.ZipFile(whl) as z:
                membros = z.namelist()
                escritos = 0
                for m in membros:
                    # .data/ guarda scripts e dados; o resto é o pacote.
                    if m.endswith("/") or m.startswith("__pycache__/"):
                        continue
                    destino = SITE / m
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(m) as origem, destino.open("wb") as saida:
                        saida.write(origem.read())
                    escritos += 1
                print(f"  {escritos} arquivos extraídos")
                total += escritos
        except zipfile.BadZipFile:
            print(f"  ERRO: arquivo corrompido, baixe de novo")
            return 1
        except PermissionError as e:
            print(f"  ERRO de permissão: {e}")
            return 1

    print()
    print(f"total: {total} arquivos")
    print()
    print("=== verificação ===")

    import subprocess

    py = RAIZ / ".venv" / "Scripts" / "python.exe"
    if not py.exists():
        print(f"ERRO: {py} não existe")
        return 1

    teste = subprocess.run(
        [str(py), "-c",
         "import numpy, PIL, rawpy\n"
         "print('numpy ', numpy.__version__)\n"
         "print('Pillow', PIL.__version__)\n"
         "print('rawpy ', rawpy.__version__)\n"
         "print('libraw', rawpy.libraw_version)\n"
         "print('flags ', sorted(k for k, v in rawpy.flags.items() if v))"],
        capture_output=True, text=True,
    )
    print(teste.stdout.strip() or teste.stderr.strip()[:800])
    return 0 if teste.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
