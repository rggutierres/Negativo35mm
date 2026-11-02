"""
Desfazer: o teste de segurança com um arquivo que EXISTE de outra foto.

Um arquivo inexistente já falha por não existir -- isso não prova a checagem.
Aqui criamos uma cópia de OUTRA foto e tentamos usar como se fosse desta.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from PIL import Image  # noqa: E402

from neg35 import config, servidor  # noqa: E402

cfg = config.carregar()
cands = sorted(Path(cfg.pasta_restaurada).glob("*_restaurado.png"))
if len(cands) < 2:
    print("preciso de duas restauradas para este teste")
    raise SystemExit(0)

a = cands[0]
b = cands[1]
nome_a = a.name.replace("_restaurado.png", "")
nome_b = b.name.replace("_restaurado.png", "")

tmp = Path(tempfile.mkdtemp(prefix="neg35_undo_seg_"))
cfg.pasta_restaurada = str(tmp)
alvo_a = tmp / a.name
shutil.copy2(a, alvo_a)

bkp = tmp / "_antes_da_rotacao"
bkp.mkdir()
# cópia legítima da foto A
legitima = bkp / f"{a.stem}_giro_20260101_000000.png"
shutil.copy2(a, legitima)
# cópia de OUTRA foto, com nome que não começa pelo stem de A
alheia = bkp / f"{b.stem}_giro_20260101_000000.png"
shutil.copy2(b, alheia)

print(f"foto A: {a.name}")
print(f"foto B: {b.name}")
print()

print("=== usada a cópia legítima de A ===")
try:
    r = servidor.desfazer_restaurado(cfg, nome_a, legitima.name)
    print(f"  ok, usou {r['backup_usado']}")
except Exception as e:  # noqa: BLE001
    print(f"  FALHOU: {type(e).__name__}: {e}")

print()
print("=== tentando usar a cópia de B para desfazer A ===")
try:
    r = servidor.desfazer_restaurado(cfg, nome_a, alheia.name)
    print(f"  ACEITOU (ERRADO): {r['backup_usado']}")
except ValueError as e:
    print(f"  recusado como esperado: {e}")
except Exception as e:  # noqa: BLE001
    print(f"  recusado, mas por outro motivo: {type(e).__name__}: {e}")

print()
print("=== caminho com '..' apontando para fora ===")
forjado = f"../../{b.stem}_giro_20260101_000000.png"
try:
    r = servidor.desfazer_restaurado(cfg, nome_a, forjado)
    print(f"  ACEITOU (ERRADO): {r['backup_usado']}")
except ValueError as e:
    print(f"  recusado como esperado: {e}")
except Exception as e:  # noqa: BLE001
    print(f"  recusado, mas por outro motivo: {type(e).__name__}: {e}")

with Image.open(alvo_a) as im:
    print(f"\n  A terminou em {im.size[0]}x{im.size[1]} "
          f"(o tamanho dela: {a.exists()})")
with Image.open(a) as im, Image.open(b) as imb:
    print(f"  arquivos reais intactos: {im.size[0]}x{im.size[1]} "
          f"e {imb.size[0]}x{imb.size[1]}")

shutil.rmtree(tmp, ignore_errors=True)
