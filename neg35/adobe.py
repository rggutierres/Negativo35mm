"""
Conversão em lote com o Adobe DNG Converter.

Motivo: uma parte dos DNG do S22 Ultra sai com um bloco JPEG defeituoso, e o
LibRaw não tolera -- ele aborta o arquivo inteiro. O Adobe DNG Converter
resolve: ele lê o arquivo com tolerância e regrava sem compressão.

Medido nos seus arquivos:

    arquivo              antes                     depois do Adobe
    20261012_143104      Data error (bloco 953516)  decodifica, máscara 3,35
    Pro_20261012_141119  Data error (bloco 1631779) decodifica, máscara 3,30
    Expert_..._141057    Unsupported (comp 52546)   ainda falha (perdido)

O que ele NÃO resolve: arquivos com compressão proprietária 52546, porque a
origem nem é RAW de sensor.

Uso:
    from neg35 import adobe
    adobe.disponivel()
    adobe.converter([f1, f2], pasta_saida)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

__all__ = ["encontrar", "disponivel", "converter", "converter_pasta", "AdobeIndisponivel"]

# Caminhos onde o instalador do Adobe costuma colocar o executável.
CAMINHOS_PADRAO = [
    r"C:\Program Files\Adobe\Adobe DNG Converter\Adobe DNG Converter.exe",
    r"C:\Program Files (x86)\Adobe\Adobe DNG Converter\Adobe DNG Converter.exe",
    r"C:\Program Files\Adobe\Adobe DNG Converter.exe",
]

# Mensagens do Adobe que não são erro de verdade -- ele é verboso sobre
# componentes opcionais (GPU, modelos de IA) que não usamos.
RUIDO = (
    "InitializeFileLogging failed",
    "GPU Warning",
    "cr_sensei_model_manager",
    "GetRuntimeModelZooPaths",
    "ComputeRawDepthModelKey",
    "ComputeBaseLayeredDepthModelKey",
    "ComputeBaseFocalMatteModelKey",
    "not present",
    "Are DLLs missing",
)


class AdobeIndisponivel(RuntimeError):
    """O Adobe DNG Converter não foi encontrado."""


def encontrar(explicito: str | Path | None = None) -> Path:
    """Localiza o executável. Levanta AdobeIndisponivel se não achar."""
    candidatos = []
    if explicito:
        candidatos.append(Path(explicito))
    candidatos.extend(Path(p) for p in CAMINHOS_PADRAO)

    for c in candidatos:
        if c.is_file():
            return c

    # Última tentativa: procurar em Program Files.
    for base in (Path(r"C:\Program Files"), Path(r"C:\Program Files (x86)")):
        if not base.is_dir():
            continue
        try:
            achados = list(base.glob("Adobe*/**/Adobe DNG Converter.exe"))
        except OSError:
            continue
        if achados:
            return achados[0]

    raise AdobeIndisponivel(
        "Adobe DNG Converter não encontrado. Instale em adobe.com/products/dng "
        "(gratuito) ou passe o caminho do executável."
    )


def disponivel(explicito: str | Path | None = None) -> bool:
    try:
        encontrar(explicito)
        return True
    except AdobeIndisponivel:
        return False


def converter(
    arquivos: list[Path],
    destino: Path,
    exe: str | Path | None = None,
    sobrescrever: bool = False,
    verbose: bool = False,
) -> tuple[list[Path], list[str]]:
    """
    Converte os arquivos para DNG sem compressão na pasta destino.

    Devolve (arquivos_gerados, problemas).

    Opções usadas:
      -p0           não embutir o RAW original (arquivo menor)
      -u            sem compressão (elimina o bloco defeituoso)
      -d <pasta>    pasta de destino
    """
    exe = encontrar(exe)
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)

    gerados: list[Path] = []
    problemas: list[str] = []

    for origem in arquivos:
        origem = Path(origem)
        if not origem.is_file():
            problemas.append(f"{origem.name}: não existe")
            continue

        alvo = destino / origem.name
        if alvo.exists() and not sobrescrever:
            # O Adobe sobrescreve silenciosamente, então checamos antes.
            gerados.append(alvo)
            continue

        cmd = [str(exe), "-d", str(destino), "-p0", "-u", str(origem)]
        proc = subprocess.run(cmd, capture_output=True, text=True)

        if alvo.exists():
            gerados.append(alvo)
            if verbose:
                print(f"    convertido: {origem.name}")
        else:
            # Coleta só as mensagens úteis do stderr.
            linhas = [
                l.strip() for l in (proc.stderr or "").splitlines()
                if l.strip() and not any(r in l for r in RUIDO)
            ]
            detalhe = " | ".join(linhas[:2]) or "sem mensagem"
            problemas.append(f"{origem.name}: {detalhe}")
            if verbose:
                print(f"    FALHOU: {origem.name} -- {detalhe}")

    return gerados, problemas


def converter_pasta(
    pasta: Path,
    destino: Path,
    exe: str | Path | None = None,
    verbose: bool = True,
) -> tuple[list[Path], list[str]]:
    """Converte todos os DNG de uma pasta."""
    pasta = Path(pasta)
    arquivos = sorted(pasta.glob("*.dng"))
    if not arquivos:
        return [], [f"nenhum DNG em {pasta}"]

    if verbose:
        print(f"  convertendo {len(arquivos)} DNG(s) com o Adobe...")
    return converter(arquivos, destino, exe=exe, verbose=verbose)


if __name__ == "__main__":
    # Uso direto:  python -m neg35.adobe <pasta_origem> <pasta_destino>
    if len(sys.argv) < 3:
        print("uso: python -m neg35.adobe <pasta_origem> <pasta_destino>")
        raise SystemExit(2)
    try:
        gerados, problemas = converter_pasta(Path(sys.argv[1]), Path(sys.argv[2]))
    except AdobeIndisponivel as e:
        print(f"ERRO: {e}")
        raise SystemExit(1)
    print(f"  convertidos: {len(gerados)}")
    for p in problemas:
        print(f"  problema: {p}")
