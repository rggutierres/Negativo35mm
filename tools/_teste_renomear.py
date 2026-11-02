"""
Renomear funciona e é seguro?

Testa numa pasta isolada, nunca nos arquivos reais do usuário:

- renomeia origem + positivo + restaurada da mesma foto;
- limpa o prefixo (espaço vira hífen, caractere proibido sai);
- NÃO sobrescreve: colisão de nome é recusada;
- foto já renomeada sai da lista;
- prefixo vazio é recusado.
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

FALHAS: list[str] = []


def checar(cond: bool, msg: str) -> None:
    print(f"  {'ok  ' if cond else 'FALHOU'} {msg}")
    if not cond:
        FALHAS.append(msg)


tmp = Path(tempfile.mkdtemp(prefix="neg35_ren_"))
origem = tmp / "origem"
positivo = tmp / "positivo"
restaurada = tmp / "restaurada"
for d in (origem, positivo, restaurada):
    d.mkdir()

NOME = "20261012_133746"
# origem: DNG + JPG (dois arquivos da mesma foto)
(origem / f"{NOME}.dng").write_bytes(b"dng-falso")
(origem / f"{NOME}.jpg").write_bytes(b"jpg-falso")
# positivo e restaurada
Image.new("RGB", (40, 20), (10, 20, 30)).save(
    positivo / f"{NOME}_positivo.png")
Image.new("RGB", (40, 20), (200, 100, 50)).save(
    restaurada / f"{NOME}_restaurado.png")
# outra foto só com origem
(origem / "20261012_999999.dng").write_bytes(b"outro")

cfg = config.carregar()
cfg.pasta_origem = str(origem)
cfg.pasta_positivo = str(positivo)
cfg.pasta_restaurada = str(restaurada)

print("=== 1) lista inicial ===")
d = servidor.listar_para_renomear(cfg)
checar(d["total"] == 2, f"duas fotos sem prefixo (achei {d['total']})")
item = next(i for i in d["itens"] if i["nome"] == NOME)
checar(sorted(item["arquivos"]) == sorted([f"{NOME}.dng", f"{NOME}.jpg"]),
       f"a origem tem os dois arquivos ({item['arquivos']})")
checar(item["tem_positivo"] and item["tem_restaurado"],
       "a lista avisa que positivo e restaurada acompanham")

print()
print("=== 2) limpeza do prefixo ===")
for entrada, esperado in (
    ("filme1-tira1", "filme1-tira1"),
    ("  Filme 1 - Tira 2  ", "Filme-1---Tira-2"),
    ("a/b:c*d", "abcd"),
    ("___x___", "x"),
):
    saida = servidor.limpar_prefixo(entrada)
    marca = "ok  " if saida == esperado else "DIFF"
    print(f"  {marca} {entrada!r} -> {saida!r} (esperado {esperado!r})")

print()
print("=== 3) renomear uma foto (origem + positivo + restaurada) ===")
r = servidor.renomear_fotos(cfg, [NOME], "filme1-tira1")
checar(r["ok"] == 1 and r["falhas"] == 0, f"1 renomeada, 0 falhas ({r})")

novo = f"filme1-tira1_{NOME}"
checar((origem / f"{novo}.dng").is_file(), "DNG renomeado")
checar((origem / f"{novo}.jpg").is_file(), "JPG renomeado")
checar((positivo / f"{novo}_positivo.png").is_file(), "positivo renomeado")
checar((restaurada / f"{novo}_restaurado.png").is_file(),
       "restaurada renomeada")
checar(not (origem / f"{NOME}.dng").exists(), "o nome antigo não ficou")
checar(not (positivo / f"{NOME}_positivo.png").exists(),
       "o positivo antigo não ficou")

print()
print("=== 4) a foto renomeada sai da lista ===")
d2 = servidor.listar_para_renomear(cfg)
checar(d2["total"] == 1, f"sobrou 1 sem prefixo (achei {d2['total']})")
checar(all(i["nome"] != NOME for i in d2["itens"]),
       "a foto renomeada não aparece mais")

print()
print("=== 5) colisão de nome é recusada, sem estragar nada ===")
# cria uma foto cujo destino já existe
(origem / "20261012_888888.dng").write_bytes(b"x")
(origem / "filme2_20261012_888888.dng").write_bytes(b"ja-existe")
r2 = servidor.renomear_fotos(cfg, ["20261012_888888"], "filme2")
checar(r2["falhas"] == 1, "colisão recusada")
checar((origem / "20261012_888888.dng").is_file(),
       "o arquivo original ficou no lugar")
checar((origem / "filme2_20261012_888888.dng").read_bytes() == b"ja-existe",
       "o arquivo que já existia não foi sobrescrito")

print()
print("=== 6) prefixo vazio e lista vazia ===")
for rotulo, args in (("prefixo vazio", (["x"], "")),
                     ("prefixo só com proibidos", (["x"], '///'))):
    try:
        servidor.renomear_fotos(cfg, *args)
        checar(False, f"{rotulo} recusado")
    except ValueError:
        checar(True, f"{rotulo} recusado")
try:
    servidor.renomear_fotos(cfg, [], "abc")
    checar(False, "lista vazia recusada")
except ValueError:
    checar(True, "lista vazia recusada")

shutil.rmtree(tmp, ignore_errors=True)
print()
if FALHAS:
    print(f"{len(FALHAS)} verificação(ões) falharam.")
    raise SystemExit(1)
print("Todas as verificações passaram.")
