"""
Testa se o DNG reconvertido pelo Adobe DNG Converter resolve.

Compara:
  - o original (bloco corrompido, LibRaw aborta)
  - o reconvertido pelo Adobe (deve decodificar sem erro)

E mede a máscara laranja dos dois, que é o que decide a qualidade do positivo.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from neg35 import core, pipeline, render  # noqa: E402

PY = RAIZ / ".venv" / "Scripts" / "python.exe"
spec = importlib.util.spec_from_file_location(
    "insp", str(RAIZ / "tools" / "inspecionar_dng.py")
)
insp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(insp)

ORIGINAIS = [
    Path(r"C:\Temp\teste\20261012_143104.dng"),
    Path(r"E:\Bkp\GoogleDrive\Negativo35mm\RAW\Pro_20261012_141119.dng"),
    Path(r"E:\Bkp\GoogleDrive\Negativo35mm\RAW\Expert_20261012_141057.dng"),
]
CONVERTIDOS = RAIZ / ".tmp" / "convertido"
SAIDA = RAIZ / "tools" / "amostras" / "adobe"


def testa(caminho: Path) -> tuple[str, list[int], dict]:
    codigo = (
        "import rawpy\n"
        f"r = rawpy.imread(r'{caminho}')\n"
        "try:\n"
        "    rgb = r.postprocess(gamma=(1,1), no_auto_bright=True, output_bps=16, use_camera_wb=False)\n"
        "    print('OK', rgb.shape[1], rgb.shape[0], rgb.mean())\n"
        "except Exception as e:\n"
        "    print('FALHOU', type(e).__name__)\n"
    )
    p = subprocess.run([str(PY), "-c", codigo], capture_output=True, text=True)
    offsets = []
    for linha in (p.stderr or "").splitlines():
        if "corrupted at" in linha:
            try:
                offsets.append(int(linha.rsplit(" ", 1)[-1]))
            except ValueError:
                pass
    try:
        tags = insp.ler_tiff(caminho.read_bytes())
    except Exception:  # noqa: BLE001
        tags = {}
    return p.stdout.strip() or "?", offsets, tags


def medir_mascara(caminho: Path) -> tuple[float, np.ndarray] | None:
    try:
        lin = pipeline.carregar(caminho, para_linear=True)
    except Exception:  # noqa: BLE001
        return None
    b = core.detectar_base_do_filme(lin)
    return float(b[0] / max(b[2], 1e-9)), b


def main() -> int:
    SAIDA.mkdir(parents=True, exist_ok=True)
    print("=== original vs reconvertido pelo Adobe ===")
    print(f"{'arquivo':<42} {'LibRaw':<20} {'comp':>7} {'R/B':>6}")
    print("-" * 80)

    for orig in ORIGINAIS:
        if not orig.exists():
            print(f"{orig.name:<42} (não existe)")
            continue
        res_o, offs_o, tags_o = testa(orig)
        m_o = medir_mascara(orig)
        rb_o = f"{m_o[0]:.2f}" if m_o else "-"
        st_o = "OK" if res_o.startswith("OK") else res_o.split()[0] + (
            f" ({offs_o[0]})" if offs_o else "")
        print(f"{orig.name:<42} {st_o:<20} {str(tags_o.get(0x0103)):>7} {rb_o:>6}")

        conv = CONVERTIDOS / orig.name
        if not conv.exists():
            print(f"{'  -> convertido: NÃO ENCONTRADO':<42}")
            print()
            continue

        res_c, offs_c, tags_c = testa(conv)
        m_c = medir_mascara(conv)
        rb_c = f"{m_c[0]:.2f}" if m_c else "-"
        st_c = "OK" if res_c.startswith("OK") else res_c.split()[0] + (
            f" ({offs_c[0]})" if offs_c else "")
        print(f"{'  -> ' + conv.name:<42} {st_c:<20} {str(tags_c.get(0x0103)):>7} {rb_c:>6}")

        if res_c.startswith("OK"):
            res = pipeline.desenvolver(
                conv, pipeline.Parametros(saturacao=1.15, nitidez=0.40, balanco_forca=0.90)
            )
            s = core.linear_para_srgb(res.positivo)
            lum = 0.2126 * s[..., 0] + 0.7152 * s[..., 1] + 0.0722 * s[..., 2]
            sat = float((s.max(axis=-1) - s.min(axis=-1)).mean())
            print(f"{'     positivo':<42} p05={np.percentile(lum,5):.3f} "
                  f"p50={np.percentile(lum,50):.3f} sat={sat:.3f}")
            pipeline.salvar(
                render.ampliar(core.linear_para_srgb(res.positivo), largura=900),
                SAIDA / f"{orig.stem}_adobe_preview.png", linear=False,
            )
        print()

    print(f"previews em {SAIDA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
