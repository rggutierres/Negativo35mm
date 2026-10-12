"""
Gera arquivos de teste reais em disco (negativo sintético + original).

    python tools/gerar_teste.py

Escreve em tools/amostras/:
    original.png          -- a "foto" que queremos recuperar
    negativo_kodak.png    -- negativo simulado, mascara Kodak
    negativo_fuji.png     -- negativo simulado, mascara Fuji
    negativo_subexpo.png  -- negativo 1.5 stops subexposto (teste do aviso)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from neg35 import core, pipeline, synthetic  # noqa: E402

SAIDA = Path(__file__).resolve().parent / "amostras"


def main() -> int:
    SAIDA.mkdir(parents=True, exist_ok=True)

    original = synthetic.tira_de_teste(largura=640, altura=420)
    pipeline.salvar(original, SAIDA / "original.png")
    print(f"original.png           {original.shape}")

    for nome, chave in (("negativo_kodak.png", "kodak"), ("negativo_fuji.png", "fuji")):
        neg = synthetic.positivo_para_negativo(original, mascara=synthetic.MASCARAS_PRESET[chave])
        pipeline.salvar(neg, SAIDA / nome)
        lin = core.srgb_para_linear(neg)
        base = core.detectar_base_do_filme(lin)
        real = np.asarray(synthetic.MASCARAS_PRESET[chave])
        print(f"{nome:<22} base real {real.round(3)}  detectada {base.round(3)}")

    # Negativo subexposto: 1.5 stops a menos de densidade -> base escura.
    fraco = synthetic.positivo_para_negativo(
        original, mascara=synthetic.MASCARAS_PRESET["kodak"], exposicao=0.35
    )
    pipeline.salvar(fraco, SAIDA / "negativo_subexpo.png")
    print("negativo_subexpo.png   (deve disparar o aviso de subexposição)")

    print(f"\nArquivos em: {SAIDA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
