"""
Compara DNG do modo PRO com DNG do EXPERT RAW do mesmo celular.

Uso:
    .venv\\Scripts\\python.exe tools/comparar_modos.py "pasta_com_as_fotos_novas"

Ou, sem argumento, analisa as duas pastas conhecidas.

Para cada arquivo responde:
  1. O LibRaw decodifica? (é o que decide se o pipeline rende bem)
  2. Qual a resolução, bits e compressão?
  3. Qual a máscara laranja resultante (R/B)?
  4. O positivo fica bom ou lavado?

A hipótese em teste: DNG do modo PRO decodifica, DNG do Expert RAW não.
Se confirmar, a recomendação é fotografar em modo Pro.
"""

from __future__ import annotations

import importlib.util
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

PY = RAIZ / ".venv" / "Scripts" / "python.exe"


def ler_tags(caminho: Path) -> dict:
    try:
        return insp.ler_tiff(caminho.read_bytes())
    except Exception:  # noqa: BLE001
        return {}


def testa_libraw(caminho: Path) -> tuple[bool, str]:
    """Tenta decodificar de verdade (não só abrir)."""
    codigo = (
        "import rawpy\n"
        f"r = rawpy.imread(r'{caminho}')\n"
        "rgb = r.postprocess(gamma=(1,1), no_auto_bright=True, output_bps=16, use_camera_wb=False)\n"
        "print('OK', rgb.shape[1], rgb.shape[0])\n"
    )
    p = subprocess.run([str(PY), "-c", codigo], capture_output=True, text=True)
    if p.returncode == 0:
        return True, p.stdout.strip()
    msg = (p.stderr or "").strip().splitlines()
    return False, (msg[-1][:38] if msg else "?")


def analisar(caminho: Path) -> dict:
    t = ler_tags(caminho)
    ok, detalhe = testa_libraw(caminho)
    d = {
        "nome": caminho.name,
        "ok": ok,
        "detalhe": detalhe,
        "comp": t.get(0x0103),
        "bits": t.get(0x0102),
        "w": t.get(0x0100),
        "h": t.get(0x0101),
        "dngv": t.get(0xC612),
        "mb": caminho.stat().st_size / 1048576,
        "rb": None,
    }
    if ok:
        # Mede a máscara laranja, que é o que define a qualidade da inversão.
        codigo = (
            "import sys; sys.path.insert(0, r'%s')\n"
            "from neg35 import core, pipeline\n"
            "lin = pipeline.carregar(r'%s', para_linear=True)\n"
            "b = core.detectar_base_do_filme(lin)\n"
            "print(b[0], b[1], b[2])\n" % (RAIZ, caminho)
        )
        p = subprocess.run([str(PY), "-c", codigo], capture_output=True, text=True)
        if p.returncode == 0:
            try:
                r, g, b = (float(x) for x in p.stdout.split())
                d["rb"] = r / max(b, 1e-9)
            except ValueError:
                pass
    return d


def main() -> int:
    if len(sys.argv) > 1:
        pastas = [Path(sys.argv[1])]
    else:
        pastas = [
            Path(r"E:\Bkp\GoogleDrive\Negativo35mm\RAW"),
            Path(r"E:\Bkp\GoogleDrive\RAW"),
        ]

    arquivos: list[Path] = []
    for p in pastas:
        if p.is_dir():
            arquivos.extend(sorted(p.glob("*.dng")))
    if not arquivos:
        print("nenhum DNG encontrado. Passe a pasta como argumento.")
        return 1

    print(f"analisando {len(arquivos)} DNG(s) de {len(pastas)} pasta(s)")
    print()
    cab = (f"{'arquivo':<24} {'LibRaw':<10} {'comp':>7} {'bits':>13} "
           f"{'dimensao':>11} {'MB':>6} {'R/B':>6}")
    print(cab)
    print("-" * len(cab))

    resultados = []
    for a in arquivos:
        d = analisar(a)
        resultados.append(d)
        bits = str(d["bits"])[:13] if d["bits"] is not None else "-"
        dim = f"{d['w']}x{d['h']}" if d["w"] else "-"
        rb = f"{d['rb']:.2f}" if d["rb"] else "-"
        status = "OK" if d["ok"] else "FALHA"
        print(f"{d['nome']:<24} {status:<10} {str(d['comp']):>7} {bits:>13} "
              f"{dim:>11} {d['mb']:>6.1f} {rb:>6}")

    ok = [d for d in resultados if d["ok"]]
    ruins = [d for d in resultados if not d["ok"]]

    print()
    print(f"decodificam: {len(ok)}   falham: {len(ruins)}")

    if ok:
        print()
        print("=== os que decodificam ===")
        for d in ok:
            rb = f"{d['rb']:.2f}" if d["rb"] else "?"
            qualidade = ("máscara boa" if d["rb"] and d["rb"] > 2.5
                         else "máscara FRACA (positivo sai lavado)")
            print(f"  {d['nome']:<24} R/B={rb:<6} {qualidade}")

    if ok and ruins:
        print()
        print("=== comparando os grupos ===")
        for chave, rotulo in [("comp", "Compression"), ("bits", "BitsPerSample"),
                              ("dngv", "DNGVersion"), ("w", "Largura"),
                              ("h", "Altura")]:
            v_ok = {str(d[chave]) for d in ok}
            v_ruim = {str(d[chave]) for d in ruins}
            if v_ok != v_ruim:
                print(f"  {rotulo:<16} decodifica={sorted(v_ok)}")
                print(f"  {'':<16} falha     ={sorted(v_ruim)}")
            else:
                print(f"  {rotulo:<16} igual nos dois ({sorted(v_ok)})")

        print()
        print("Se Compression/DNGVersion/Bits forem IGUAIS e só o modo de captura")
        print("explicar a diferença, a conclusão é que o problema está no modo do")
        print("celular (Expert RAW), não no formato do arquivo.")

    print()
    print("Próximo passo sugerido: fotografar a MESMA cena em modo Pro e em")
    print("Expert RAW e rodar de novo. Comparação direta, sem ambiguidade.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
