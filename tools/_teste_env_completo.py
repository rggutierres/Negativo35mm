"""
Confere se TODO campo do Config é escrito no .env.

Este bug já aconteceu: acrescentei campos à classe Config e esqueci de
acrescentá-los ao modelo de linhas do `salvar()`. O campo passa a existir no
código, aparece na tela, e simplesmente não está no arquivo -- o usuário não
acha, e a alteração dele se perde na próxima gravação.

    .venv\\Scripts\\python.exe tools/_teste_env_completo.py
"""

from __future__ import annotations

import re
import shutil
import sys
from dataclasses import fields
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from neg35 import config  # noqa: E402

BASE = RAIZ / "tools" / "_teste_env"
ENV = BASE / ".env"
FALHAS: list[str] = []


def checar(cond: bool, msg: str) -> None:
    if cond:
        print(f"  ok  {msg}")
    else:
        print(f"  FALHOU: {msg}")
        FALHAS.append(msg)


def main() -> int:
    shutil.rmtree(BASE, ignore_errors=True)
    BASE.mkdir(parents=True)

    print("=== 1) todo campo do Config aparece no .env gravado? ===")
    cfg = config.Config()
    config.salvar(cfg, ENV)
    texto = ENV.read_text(encoding="utf-8")

    # Nomes das chaves efetivamente presentes (ignorando comentários)
    chaves = set()
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        if "=" in linha:
            chaves.add(linha.split("=", 1)[0].strip())

    todos = {f.name for f in fields(config.Config)}
    faltando = sorted(todos - chaves)
    extras = sorted(chaves - todos)

    print(f"  campos em Config : {len(todos)}")
    print(f"  chaves no .env   : {len(chaves)}")
    if faltando:
        print(f"  NÃO escritos: {faltando}")
    if extras:
        print(f"  (chaves sem campo correspondente: {extras})")
    checar(not faltando,
           "todo campo do Config é gravado no .env (nenhum fica só na memória)")

    # ---------------------------------------------------------------- 2
    print()
    print("=== 2) ida e volta: o que grava é o que lê? ===")
    alterado = config.Config()
    alterado.filme = "portra400"
    alterado.saturacao = 1.33
    alterado.pasta_cache_adobe = r"C:\Temp\cache_neg35"
    alterado.converter_auto = True
    alterado.usar_adobe = False
    alterado.max_lado_envio = 2048
    alterado.casar_exposicao = False
    alterado.exposicao_forca = 0.7
    alterado.brilho_envio = 1.35
    alterado.dica_por_foto = False
    alterado.recortar_bordas = False
    alterado.recorte_margem = 0.05
    config.salvar(alterado, ENV)
    lido = config.carregar(ENV, usar_ambiente=False)

    for campo, esperado in (("filme", "portra400"), ("saturacao", 1.33),
                            ("pasta_cache_adobe", r"C:\Temp\cache_neg35"),
                            ("converter_auto", True), ("usar_adobe", False),
                            ("max_lado_envio", 2048),
                            ("casar_exposicao", False),
                            ("exposicao_forca", 0.7),
                            ("brilho_envio", 1.35),
                            ("dica_por_foto", False),
                            ("recortar_bordas", False),
                            ("recorte_margem", 0.05)):
        obtido = getattr(lido, campo)
        checar(obtido == esperado,
               f"{campo}: gravou {esperado!r} e leu {obtido!r}")

    # ---------------------------------------------------------------- 3
    print()
    print("=== 3) os campos documentados têm comentário? ===")
    linhas = texto.splitlines()
    sem_contexto = []
    for i, linha in enumerate(linhas):
        limpa = linha.strip()
        if not limpa or limpa.startswith("#") or "=" not in limpa:
            continue
        chave = limpa.split("=", 1)[0].strip()
        # Procura um comentário nas 8 linhas anteriores
        contexto = any(linhas[j].strip().startswith("#")
                       for j in range(max(0, i - 8), i))
        if not contexto:
            sem_contexto.append(chave)
    if sem_contexto:
        print(f"  sem comentário explicativo: {sem_contexto}")
    checar(not sem_contexto,
           "todo campo do .env tem comentário explicando para que serve")

    # ---------------------------------------------------------------- 4
    print()
    print("=== 4) o .env real do projeto está completo? ===")
    real = RAIZ / ".env"
    if real.is_file():
        chaves_real = set()
        for linha in real.read_text(encoding="utf-8",
                                    errors="replace").splitlines():
            limpa = linha.strip()
            if limpa and not limpa.startswith("#") and "=" in limpa:
                chaves_real.add(limpa.split("=", 1)[0].strip())
        falta_real = sorted(todos - chaves_real)
        if falta_real:
            print(f"  faltam no seu .env: {falta_real}")
            print("  (ele é regravado quando você salva pela engrenagem)")
        checar(not falta_real,
               "o .env do projeto já tem todas as chaves")
    else:
        print("  (não há .env na raiz)")

    shutil.rmtree(BASE, ignore_errors=True)
    print()
    if FALHAS:
        print(f"{len(FALHAS)} verificação(ões) falharam.")
        return 1
    print("Todas as verificações passaram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
