"""
Mede a máscara do negativo no arquivo ORIGINAL (não no positivo).

Este é o valor que a proteção "máscara fraca" deve usar. Medir no positivo já
invertido devolvia lixo (R=1.00 exato), e por isso TODA restauração era pulada.

    .venv\\Scripts\\python.exe tools/_medir_mascaras.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from neg35 import config, pipeline, servidor  # noqa: E402

LIMITE = 2.5

cfg = config.carregar()
origem = Path(cfg.pasta_origem)
positivo = Path(cfg.pasta_positivo)

nomes = sorted(a.name.replace("_positivo.png", "")
               for a in positivo.glob("*_positivo.png"))
print(f"origem   : {origem}")
print(f"positivos: {positivo}  ({len(nomes)} arquivo(s))")
print(f"limite   : R/B >= {LIMITE} para enviar à IA")
print()
print(f"{'arquivo':<28} {'R/B':>6}  {'situação'}")
print("-" * 60)

medidos = []
for nome in nomes:
    rb, motivo = servidor._mascara_do_negativo(cfg, nome)
    if rb is None:
        situacao = f"não medido {motivo}"
    elif rb >= LIMITE:
        situacao = "ENVIA para a IA"
        medidos.append(rb)
    else:
        situacao = "pula (máscara fraca)"
        medidos.append(rb)
    valor = f"{rb:6.2f}" if rb is not None else "     -"
    print(f"{nome:<28} {valor}  {situacao}")

print()
if medidos:
    enviam = sum(1 for x in medidos if x >= LIMITE)
    print(f"  medidos  : {len(medidos)}")
    print(f"  ENVIAM   : {enviam}")
    print(f"  PULADOS  : {len(medidos) - enviam}")
    print(f"  R/B min/máx/mediana: {min(medidos):.2f} / {max(medidos):.2f} / "
          f"{np.median(medidos):.2f}")
    print()
    print("  (um negativo bem exposto fica por volta de 3 a 4,5;")
    print("   perto de 1 significa que a correção de cor laranja se perdeu)")
else:
    print("  nenhuma máscara pôde ser medida -- a pasta de origem está acessível?")
