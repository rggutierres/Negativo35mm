"""
Compara DNGs que decodificam com os que falham no LibRaw.

Os arquivos novos têm cabeçalho válido (o LibRaw lê tamanho e dimensões) mas
o `postprocess` falha com "data corrupted". Isso significa: metadados
suportados, dados de pixel NÃO suportados.

    .venv\\Scripts\\python.exe tools/diag_dng_falha.py "E:\\...\\RAW" [funciona.dng]
"""

from __future__ import annotations

import glob
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

spec = importlib.util.spec_from_file_location(
    "insp", str(RAIZ / "tools" / "inspecionar_dng.py")
)
insp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(insp)

INTERESSA = [
    (0x0100, "Largura"),
    (0x0101, "Altura"),
    (0x0102, "BitsPorAmostra"),
    (0x0103, "Compressao"),
    (0x0106, "Photometric"),
    (0x0115, "AmostrasPorPixel"),
    (0x011C, "Planar"),
    (0x828D, "CFARepeatDim"),
    (0x828E, "CFAPattern"),
    (0xC612, "DNGVersion"),
    (0xC614, "Camera"),
    (0xC61D, "WhiteLevel"),
    (0xC61A, "BlackLevel"),
    (0xC628, "AsShotNeutral"),
    (0xC62F, "ActiveArea"),
]


def tags(caminho: Path) -> dict:
    try:
        return insp.ler_tiff(caminho.read_bytes())
    except Exception as e:  # noqa: BLE001
        return {"_erro": str(e)}


def testa_rawpy(caminho: Path) -> str:
    py = RAIZ / ".venv" / "Scripts" / "python.exe"
    codigo = (
        "import rawpy,sys\n"
        f"r = rawpy.imread(r'{caminho}')\n"
        "rgb = r.postprocess(gamma=(1,1), no_auto_bright=True, output_bps=16, use_camera_wb=False)\n"
        "print('OK', rgb.shape)\n"
    )
    p = subprocess.run([str(py), "-c", codigo], capture_output=True, text=True)
    if p.returncode == 0:
        return p.stdout.strip()
    linhas = (p.stderr or "").strip().splitlines()
    msg = linhas[-1] if linhas else "?"
    if "Unsupported" in msg:
        return "UNSUPPORTED"
    if "Data error" in msg:
        return "DATA ERROR"
    return msg[:34]


def main() -> int:
    pasta = sys.argv[1] if len(sys.argv) > 1 else r"E:\Bkp\GoogleDrive\Negativo35mm\RAW"
    referencia = sys.argv[2] if len(sys.argv) > 2 else None

    arquivos = sorted(glob.glob(os.path.join(pasta, "*.dng")))
    if not arquivos:
        print(f"nenhum DNG em {pasta}")
        return 1

    print(f"analisando {len(arquivos)} DNG(s)")
    print()

    linhas = []
    for p in arquivos:
        path = Path(p)
        t = tags(path)
        res = testa_rawpy(path)
        linhas.append({
            "nome": path.name,
            "res": res,
            "comp": t.get(0x0103),
            "phot": t.get(0x0106),
            "bits": t.get(0x0102),
            "spp": t.get(0x0115),
            "planar": t.get(0x011C),
            "dngv": t.get(0xC612),
            "cfa": (0x828E in t),
            "w": t.get(0x0100),
            "h": t.get(0x0101),
        })

    cab = (f"{'arquivo':<24} {'rawpy':<12} {'comp':>7} {'phot':>6} {'bits':>13} "
           f"{'spp':>4} {'plan':>5} {'CFA':>4} {'DNG':>12}")
    print(cab)
    print("-" * len(cab))
    for L in linhas:
        bits = L["bits"]
        bits_s = str(bits)[:13] if bits is not None else "-"
        print(f"{L['nome']:<24} {L['res']:<12} {str(L['comp']):>7} {str(L['phot']):>6} "
              f"{bits_s:>13} {str(L['spp']):>4} {str(L['planar']):>5} "
              f"{('sim' if L['cfa'] else 'nao'):>4} {str(L['dngv'])[:12]:>12}")

    # Separa os grupos.
    ok = [L for L in linhas if L["res"].startswith("OK")]
    ruins = [L for L in linhas if not L["res"].startswith("OK")]

    print()
    print(f"decodificam: {len(ok)}   falham: {len(ruins)}")

    if ok and ruins:
        print()
        print("=== diferenças entre os grupos ===")
        for chave, rotulo in [("comp", "Compression"), ("phot", "Photometric"),
                              ("bits", "BitsPerSample"), ("spp", "SamplesPerPixel"),
                              ("planar", "PlanarConfig"), ("cfa", "CFA presente"),
                              ("dngv", "DNGVersion")]:
            v_ok = {str(L[chave]) for L in ok}
            v_ruim = {str(L[chave]) for L in ruins}
            if v_ok != v_ruim:
                print(f"  {rotulo:<16} funciona={sorted(v_ok)}  falha={sorted(v_ruim)}")
            else:
                print(f"  {rotulo:<16} igual nos dois ({sorted(v_ok)})")
    elif ruins and not ok:
        print()
        print("TODOS falham: o problema não é um arquivo específico, é o formato")
        print("de captura (ou o conjunto de tags) que o LibRaw não suporta.")

    print()
    print("Chaves: comp 7=JPEG lossy, 1=nenhuma, 52546=proprietária")
    print("        phot 34892=LinearRaw, 2=RGB demosaico, 32803=CFA")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
