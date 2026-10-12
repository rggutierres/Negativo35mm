"""
Verifica se os DNGs estão íntegros comparando CRC32 com o que está no ZIP.

Motivo: o LibRaw acusa "data corrupted" em offsets específicos. Precisamos
saber se o arquivo em disco está íntegro (e o problema é o decodificador)
ou se a cópia corrompeu (e o problema é a transferência).

    python tools/verificar_integridade.py <pasta_dng> <arquivo.zip>
"""

from __future__ import annotations

import sys
import zipfile
import zlib
from pathlib import Path


def crc_arquivo(caminho: Path, bloco: int = 1 << 20) -> tuple[int, int]:
    c = 0
    total = 0
    with caminho.open("rb") as f:
        while True:
            d = f.read(bloco)
            if not d:
                break
            total += len(d)
            c = zlib.crc32(d, c)
    return c & 0xFFFFFFFF, total


def main() -> int:
    if len(sys.argv) < 3:
        print("uso: python tools/verificar_integridade.py <pasta_dng> <arquivo.zip>",
              file=sys.stderr)
        return 2

    pasta = Path(sys.argv[1])
    zips = [Path(p) for p in sys.argv[2:]]

    print("=== CRC dos arquivos em disco ===")
    em_disco: dict[str, tuple[int, int]] = {}
    for p in sorted(pasta.glob("*.dng")):
        c, n = crc_arquivo(p)
        em_disco[p.name] = (c, n)
        print(f"  {p.name:<26} {n:>10,} bytes  CRC32 {c:08X}")

    print()
    print("=== CRC dentro do ZIP ===")
    no_zip: dict[str, tuple[int, int]] = {}
    for z in zips:
        if not z.exists():
            print(f"  {z} não existe")
            continue
        print(f"  {z.name}:")
        with zipfile.ZipFile(z) as zf:
            for info in zf.infolist():
                if not info.filename.lower().endswith(".dng"):
                    continue
                nome = Path(info.filename).name
                no_zip[nome] = (info.CRC, info.file_size)
                print(f"    {nome:<26} {info.file_size:>10,} bytes  CRC32 {info.CRC:08X}")

    print()
    print("=== comparação ===")
    iguais = diferentes = ausentes = 0
    for nome, (c_disco, n_disco) in em_disco.items():
        if nome not in no_zip:
            print(f"  {nome:<26} não está no ZIP")
            ausentes += 1
            continue
        c_zip, n_zip = no_zip[nome]
        if c_disco == c_zip:
            print(f"  {nome:<26} ÍNTEGRO (CRC bate)")
            iguais += 1
        else:
            print(f"  {nome:<26} DIFERENTE! disco {c_disco:08X} vs zip {c_zip:08X}")
            diferentes += 1

    print()
    print(f"íntegros: {iguais}   diferentes: {diferentes}   ausentes: {ausentes}")
    print()
    if diferentes == 0 and iguais > 0:
        print("CONCLUSÃO: os arquivos em disco estão íntegros. Se o LibRaw ainda")
        print("reclama, o problema é de COMPATIBILIDADE do decodificador com")
        print("este tipo de DNG, não de corrupção na transferência.")
    elif diferentes:
        print("CONCLUSÃO: a cópia corrompeu. Reextraia do ZIP e use esses")
        print("arquivos -- e prefira sempre transferir DNG dentro de ZIP.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
