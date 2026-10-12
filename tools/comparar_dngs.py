"""
Compara os DNGs que decodificam com os que não decodificam.

Objetivo: achar o que diferencia os dois grupos. Suspeita: os que falham
foram gravados em modo de alta resolução (50MP/108MP), que o Expert RAW
grava de um jeito que os decodificadores comuns não leem.

    python tools/comparar_dngs.py <pasta>
"""

from __future__ import annotations

import glob
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# Reaproveita o parser de TIFF do inspetor.
spec = importlib.util.spec_from_file_location("insp", str(RAIZ / "tools" / "inspecionar_dng.py"))
insp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(insp)

INTERESSA = {
    0x0100: "Largura",
    0x0101: "Altura",
    0x0106: "Photometric",
    0x0103: "Compressao",
    0x0102: "BitsPorAmostra",
    0x0115: "AmostrasPorPixel",
    0xC612: "DNGVersion",
    0xC614: "Camera",
    0xC61D: "WhiteLevel",
    0xC61A: "BlackLevel",
    0x828D: "CFARepeatDim",
    0x828E: "CFAPattern",
}


def tags_de(caminho: Path) -> dict:
    try:
        return insp.ler_tiff(caminho.read_bytes())
    except Exception as e:  # noqa: BLE001
        return {"_erro": str(e)}


def testa_magick(caminho: Path) -> str:
    p = subprocess.run(["magick", "identify", str(caminho)],
                       capture_output=True, text=True)
    if p.returncode == 0:
        return p.stdout.strip().split()[1] if len(p.stdout.split()) > 1 else "OK"
    err = p.stderr.strip()
    if "Unsupported file format" in err:
        return "UNSUPPORTED"
    if "Data corrupted" in err or "data corrupted" in err:
        return "CORROMPIDO"
    return err[:40]


def testa_rawpy(caminho: Path) -> str:
    py = RAIZ / ".venv" / "Scripts" / "python.exe"
    if not py.exists():
        return "(sem venv)"
    codigo = (
        "import rawpy,sys\n"
        f"r=rawpy.imread(r'{caminho}')\n"
        "print(f'{r.sizes.width}x{r.sizes.height}')\n"
    )
    p = subprocess.run([str(py), "-c", codigo], capture_output=True, text=True)
    if p.returncode == 0:
        return p.stdout.strip()
    err = (p.stderr or "").strip().splitlines()
    msg = err[-1] if err else "?"
    if "Unsupported" in msg:
        return "UNSUPPORTED"
    if "Data error" in msg:
        return "DATA ERROR"
    return msg[:40]


def main() -> int:
    pasta = sys.argv[1] if len(sys.argv) > 1 else "E:/Bkp/GoogleDrive/RAW"
    arquivos = sorted(glob.glob(os.path.join(pasta, "*.dng")))
    if not arquivos:
        print(f"nenhum DNG em {pasta}")
        return 1

    print(f"{'arquivo':<24} {'ImageMagick':<13} {'rawpy':<13} "
          f"{'LxA':<12} {'phot':>5} {'comp':>5} {'bits':>12} {'DNG':>10}")
    print("-" * 106)

    for p in arquivos:
        path = Path(p)
        tags = tags_de(path)
        lar = tags.get(0x0100, "?")
        alt = tags.get(0x0101, "?")
        phot = tags.get(0x0106, "?")
        comp = tags.get(0x0103, "?")
        bits = tags.get(0x0102, "?")
        dngv = tags.get(0xC612, "?")
        dim = f"{lar}x{alt}"

        print(f"{path.name:<24} {testa_magick(path):<13} {testa_rawpy(path):<13} "
              f"{dim:<12} {str(phot):>5} {str(comp):>5} {str(bits):>12} {str(dngv):>10}")

    print()
    print("Chave de 'comp': 1=nenhuma, 7=JPEG, 8=Deflate")
    print("Chave de 'phot': 1=BlackIsZero, 2=RGB, 34892=LinearRaw, 32803=CFA")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
