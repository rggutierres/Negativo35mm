"""Testa o registro de falhas de restauração com o caso real de máscara fraca."""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from neg35 import config, servidor  # noqa: E402

cfg = config.carregar()

# Os três negativos que o usuário relatou, com os R/B medidos por ele.
CASOS = [("20261012_214914", 2.10),
         ("20261012_214922", 1.85),
         ("20261012_214938", 2.31)]

print("=== registrando as 3 falhas de máscara fraca ===")
for nome, rb in CASOS:
    servidor.registrar_falha_restauro(
        cfg, nome, f"máscara fraca (R/B={rb:.2f})",
        "A IA não recupera esses casos; ela inventa detalhes.",
        mascara_fraca=True, r_b=rb)
    print(f"  {nome}  R/B={rb:.2f}")

d = servidor.falhas_restauro(cfg)
print()
print(f"total na aba: {d['total']}   limite de máscara: {d['limite_mascara']}")
print()
for f in d["falhas"]:
    print(f"  {f['nome']}")
    print(f"    motivo        : {f['motivo']}")
    print(f"    detalhe       : {f['detalhe']}")
    print(f"    máscara fraca : {f['mascara_fraca']}")
    print(f"    R/B           : {f['r_b']}")
    print(f"    tem positivo  : {f['tem_positivo']}")
    print(f"    quando        : {f['quando']}")

print()
print("=== uma foto que já tem restaurada não deve aparecer ===")
prontas = [f.name.replace("_restaurado.png", "")
           for f in Path(cfg.pasta_restaurada).glob("*_restaurado.png")]
print(f"  restauradas existentes: {prontas}")
nomes = [f["nome"] for f in d["falhas"]]
for p in prontas:
    print(f"  {p} está na lista? "
          f"{'SIM (errado)' if p in nomes else 'não (correto)'}")

print()
print("=== e ao restaurar com sucesso, sai da lista ===")
alvo = CASOS[0][0]
servidor.limpar_falha_restauro(cfg, alvo)
d2 = servidor.falhas_restauro(cfg)
print(f"  removi {alvo} -> total agora {d2['total']}")
print(f"  ainda tem {alvo}? "
      f"{'SIM (errado)' if alvo in [x['nome'] for x in d2['falhas']] else 'não (correto)'}")

# Restaura o registro completo, para a tela mostrar os três
for nome, rb in CASOS:
    servidor.registrar_falha_restauro(
        cfg, nome, f"máscara fraca (R/B={rb:.2f})",
        "A IA não recupera esses casos; ela inventa detalhes.",
        mascara_fraca=True, r_b=rb)
print()
print(f"registro final: {servidor.falhas_restauro(cfg)['total']} falha(s)")
