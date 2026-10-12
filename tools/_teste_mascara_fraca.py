"""
Valida o fluxo com um DNG que o LibRaw não decodifica.

Confirma que o programa:
1. cai no ImageMagick e avisa
2. MEDE a máscara fraca
3. NÃO gasta API nesse arquivo (pular_mascara_fraca=true)
4. ainda assim entrega o positivo local
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

ORIGEM_REAL = Path(r"E:\Bkp\GoogleDrive\Negativo35mm\RAW")
BASE = RAIZ / "tools" / "_teste_falha"
ORIGEM = BASE / "origem"
POSITIVO = BASE / "positivo"
RESTAURADA = BASE / "restaurada"
ENV = BASE / ".env"
PY = RAIZ / ".venv" / "Scripts" / "python.exe"


def main() -> int:
    if not ORIGEM_REAL.exists():
        print(f"pasta de origem real não existe: {ORIGEM_REAL}")
        return 0

    arquivos = sorted(ORIGEM_REAL.glob("*.dng"))[:1]
    if not arquivos:
        print("nenhum DNG para testar")
        return 0

    shutil.rmtree(BASE, ignore_errors=True)
    for d in (ORIGEM, POSITIVO, RESTAURADA):
        d.mkdir(parents=True)
    # Copia um arquivo que falha no LibRaw.
    alvo = ORIGEM / arquivos[0].name
    shutil.copy2(arquivos[0], alvo)
    print(f"arquivo: {alvo.name} ({alvo.stat().st_size/1048576:.1f} MB)")

    from neg35 import config

    cfg = config.carregar()
    cfg.pasta_origem = str(ORIGEM)
    cfg.pasta_positivo = str(POSITIVO)
    cfg.pasta_restaurada = str(RESTAURADA)
    cfg.pular_mascara_fraca = True
    config.salvar(cfg, ENV)

    print()
    print("=== rodando com --tudo (deve PULAR a IA por máscara fraca) ===")
    proc = subprocess.run(
        [str(PY), str(RAIZ / "tools" / "lote.py"), "--env", str(ENV),
         "--sem-perguntar-pastas", "--tudo"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(RAIZ),
        env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
    )
    saida = proc.stdout + proc.stderr
    for linha in saida.splitlines():
        if any(k in linha for k in ("rawpy", "máscara", "MÁSCARA", "restauração PULADA",
                                    "positivo ok", "CUSTO", "processadas", "falhas",
                                    "p05")):
            print("  " + linha.strip())

    positivos = list(POSITIVO.glob("*.png"))
    restaurados = list(RESTAURADA.glob("*.png"))

    print()
    falhas = 0
    if positivos:
        print(f"  ok  positivo gerado: {positivos[0].name} "
              f"({positivos[0].stat().st_size/1048576:.1f} MB)")
    else:
        print("  FALHOU: nenhum positivo gerado")
        falhas += 1

    if not restaurados:
        print("  ok  NÃO chamou a IA (máscara fraca) -- nada foi gasto")
    else:
        print(f"  ATENÇÃO: gerou restaurado ({restaurados[0].name}) -- gastou API")
        falhas += 1

    if "máscara fraca" in saida.lower() or "máscara fraca" in saida:
        print("  ok  avisou sobre a máscara fraca")
    else:
        print("  FALHOU: não avisou sobre a máscara fraca")
        falhas += 1

    shutil.rmtree(BASE, ignore_errors=True)
    print()
    print("Tudo certo." if not falhas else f"{falhas} problema(s).")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
