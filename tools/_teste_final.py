"""
Teste de ponta a ponta: lote com Adobe + curva de tom nos arquivos reais.

Usa pastas locais (o sandbox nega escrita em E:), mas os arquivos de origem são
os DNG problemáticos de verdade.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from neg35 import config  # noqa: E402

BASE = RAIZ / "tools" / "_teste_final"
ORIGEM = BASE / "origem"
POSITIVO = BASE / "positivo"
RESTAURADA = BASE / "restaurada"
ENV = BASE / ".env"
PY = RAIZ / ".venv" / "Scripts" / "python.exe"

REAIS = [
    Path(r"C:\Temp\teste\20261012_143104.dng"),
    Path(r"E:\Bkp\GoogleDrive\Negativo35mm\RAW\Pro_20261012_141119.dng"),
    Path(r"E:\Bkp\GoogleDrive\Negativo35mm\RAW\Expert_20261012_141057.dng"),
]


def main() -> int:
    shutil.rmtree(BASE, ignore_errors=True)
    for d in (ORIGEM, POSITIVO, RESTAURADA):
        d.mkdir(parents=True)

    copiados = []
    for f in REAIS:
        if f.exists():
            shutil.copy2(f, ORIGEM / f.name)
            copiados.append(f.name)
    if not copiados:
        print("nenhum arquivo de origem disponível")
        return 0
    print(f"origem: {len(copiados)} arquivo(s): {', '.join(copiados)}")

    cfg = config.carregar()
    cfg.pasta_origem = str(ORIGEM)
    cfg.pasta_positivo = str(POSITIVO)
    cfg.pasta_restaurada = str(RESTAURADA)
    cfg.usar_adobe = True
    cfg.usar_curva = True
    config.salvar(cfg, ENV)

    print()
    print("=== rodando o lote (só local, sem gastar API) ===")
    proc = subprocess.run(
        [str(PY), str(RAIZ / "tools" / "lote.py"), "--env", str(ENV),
         "--sem-perguntar-pastas", "--so-local", "--tudo"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(RAIZ),
        env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
    )
    saida = proc.stdout + proc.stderr
    for linha in saida.splitlines():
        if any(k in linha for k in ("Adobe", "positivo ok", "FALHOU", "processadas",
                                    "falhas", "via Adobe", "máscara", "AVISO")):
            print("  " + linha.strip())

    print()
    print("=== positivos gerados ===")
    from PIL import Image

    import numpy as np

    positivos = sorted(POSITIVO.glob("*.png"))
    for p in positivos:
        arr = np.asarray(Image.open(p).convert("RGB")).astype(np.float64) / 255.0
        lum = 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]
        sat = float((arr.max(axis=-1) - arr.min(axis=-1)).mean())
        print(f"  {p.name:<40} p05={np.percentile(lum,5):.3f} "
              f"p50={np.percentile(lum,50):.3f} p95={np.percentile(lum,95):.3f} "
              f"sat={sat:.3f}  ({p.stat().st_size/1048576:.1f} MB)")

    if not positivos:
        print("  NENHUM positivo gerado")
        return 1

    print()
    print("Alvo da curva: p50 em ~0,50. Antes da curva ficava em 0,70-0,87.")
    _ = RESTAURADA
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
