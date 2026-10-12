"""
Compara os DNGs de teste: download solto do Drive vs extraído de ZIP.

A pergunta: o arquivo que vem dentro de um ZIP é diferente do que vem solto?
E qual dos dois o LibRaw consegue decodificar?

Se o do ZIP decodificar e o solto não, a conclusão é que o download solto pelo
navegador corrompe o arquivo -- e a solução é sempre transferir por ZIP.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PY = RAIZ / ".venv" / "Scripts" / "python.exe"

PASTA = Path(r"C:\Temp\teste")
ZIP = PASTA / "drive-download-20261012T173313Z-1-001.zip"


def md5(caminho: Path) -> str:
    h = hashlib.md5()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def decodifica(caminho: Path) -> tuple[str, list[int]]:
    codigo = (
        "import rawpy\n"
        f"r = rawpy.imread(r'{caminho}')\n"
        "try:\n"
        "    rgb = r.postprocess(gamma=(1,1), no_auto_bright=True, output_bps=16, use_camera_wb=False)\n"
        "    print('OK', rgb.shape[1], rgb.shape[0])\n"
        "except Exception as e:\n"
        "    print('FALHOU', type(e).__name__)\n"
    )
    p = subprocess.run([str(PY), "-c", codigo], capture_output=True, text=True)
    offsets = []
    for linha in (p.stderr or "").splitlines():
        if "corrupted at" in linha:
            try:
                offsets.append(int(linha.rsplit(" ", 1)[-1]))
            except ValueError:
                pass
    return (p.stdout.strip() or "?"), offsets


def main() -> int:
    if not PASTA.is_dir():
        print(f"não existe: {PASTA}")
        return 1

    dngs = sorted(PASTA.glob("*.dng"))
    if not dngs:
        print("nenhum DNG na pasta")
        return 1

    print("=== arquivos ===")
    info = []
    for d in dngs:
        h = md5(d)
        res, offs = decodifica(d)
        info.append((d, h, res, offs))
        print(f"  {d.name}")
        print(f"     tamanho : {d.stat().st_size:,} bytes")
        print(f"     md5     : {h}")

    print()
    print("=== decodificação (LibRaw) ===")
    for d, h, res, offs in info:
        status = "OK" if res.startswith("OK") else res
        blocos = f"blocos corrompidos: {offs}" if offs else "nenhum bloco corrompido"
        print(f"  {d.name:<46} {status:<22} {blocos}")

    # Compara os pares que deveriam ser o mesmo arquivo.
    print()
    print("=== os arquivos são idênticos entre si? ===")
    for i in range(len(info)):
        for j in range(i + 1, len(info)):
            a, ha = info[i][0], info[i][1]
            b, hb = info[j][0], info[j][1]
            igual = "IDÊNTICO" if ha == hb else "DIFERENTE"
            print(f"  {a.name[:28]:<30} vs {b.name[:28]:<30} {igual}")

    # Confere o conteúdo do ZIP.
    if ZIP.exists():
        import zipfile

        print()
        print(f"=== conteúdo do ZIP ({ZIP.name}) ===")
        with zipfile.ZipFile(ZIP) as z:
            for e in z.infolist():
                print(f"  {e.filename:<46} {e.file_size:>12,} bytes  CRC32 {e.CRC:08X}")
                # Compara o CRC do ZIP com o arquivo em disco de mesmo nome.
                for d, h, res, offs in info:
                    if d.name == Path(e.filename).name:
                        import zlib

                        c = 0
                        with d.open("rb") as f:
                            for bloco in iter(lambda: f.read(1 << 20), b""):
                                c = zlib.crc32(bloco, c)
                        c &= 0xFFFFFFFF
                        estado = "ÍNTEGRO" if c == e.CRC else "DIFERENTE DO ZIP"
                        print(f"       em disco: CRC32 {c:08X}  -> {estado}")

    print()
    print("=== conclusão ===")
    ok = [d for d, _, res, _ in info if res.startswith("OK")]
    ruins = [(d, offs) for d, _, res, offs in info if not res.startswith("OK")]
    if ok and ruins:
        print(f"  {len(ok)} decodifica(m) e {len(ruins)} não -> os arquivos SÃO diferentes")
        print("  A fonte que decodifica é a que você deve usar para transferir.")
    elif ok:
        print("  Todos decodificam. O problema anterior era de transferência.")
    else:
        print("  Nenhum decodifica. Todos têm o mesmo defeito:")
        for d, offs in ruins:
            print(f"    {d.name}: {offs or 'sem aviso de bloco, formato não suportado'}")
        if all(not offs for _, offs in ruins):
            print("  Sem aviso de bloco -> é formato (compressão) não suportado,")
            print("  provavelmente a compressão proprietária 52546.")
        else:
            print("  Com aviso de bloco -> corrupção de dado, e o LibRaw aborta")
            print("  por causa de um único bloco ruim.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
