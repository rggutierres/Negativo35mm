r"""
Conserta o TLS do Python quando um antivírus intercepta HTTPS.

SINTOMA
-------
    SSLError: certificate verify failed: self-signed certificate in
    certificate chain

CAUSA (confirmada no seu caso)
-----------------------------
Não é proxy corporativo: é o **Kaspersky**, pela varredura de conexões
criptografadas. Ele se coloca no meio da conexão e reassina o certificado com
a CA raiz dele. O navegador aceita porque o Kaspersky instala essa CA no
repositório do Windows. O Node também. O Python NÃO, porque usa o pacote
`certifi`, que tem só as CAs públicas.

TRÊS CAMINHOS, e a escolha é sua
--------------------------------
1. **Exclusões no Kaspersky** (você mencionou que pode adicionar). Nas
   configurações de varredura de conexões criptografadas existe uma lista de
   exclusões por domínio/endereço. Adicione:
       api.openrouter.ai
       openrouter.ai
       generativelanguage.googleapis.com
       api.openai.com
   Vantagem: resolve de vez, sem tocar no Python.
   Custo: essas URLs deixam de ser inspecionadas pelo antivírus.
   (Os nomes exatos do menu mudam entre versões -- não consegui confirmar a
   sua no site da Kaspersky.)

2. **Este script** (recomendado por padrão). Gera um bundle unindo as CAs
   públicas do `certifi` com as CAs confiáveis do Windows -- incluindo a que
   o Kaspersky instalou. Você mantém a proteção E o Python conecta.
   Custo: um arquivo extra e uma variável de ambiente.

3. Desativar a varredura de conexões criptografadas no antivírus.
   Funciona, mas reduz a proteção em TODA a navegação. Não recomendo só por
   causa deste programa.

O QUE ESTE SCRIPT FAZ
---------------------
Exporta as autoridades certificadoras do repositório do Windows via .NET e as
anexa ao bundle do certifi, gerando `ca-empresa.pem` nesta pasta.

Por que .NET e não `Get-ChildItem Cert:\...`: neste ambiente o provider `Cert:`
do PowerShell não existe quando ele roda por subprocess, e `Import-Module
Microsoft.PowerShell.Security` falha ao carregar TypeData. Acessar
`X509Store` direto pelo .NET não depende de nada disso.

Anexar raízes do repositório do Windows é seguro: uma CA raiz é
autocertificada e só entra ali depois que alguém com privilégio de
administrador a instalou explicitamente -- no caso, o próprio antivírus. É o
mesmo conjunto de confiança que o seu navegador já usa.

USO
---
    python tools/consertar_tls.py

Depois, a cada sessão do terminal (ou nas variáveis de ambiente do sistema):

    set REQUESTS_CA_BUNDLE=<pasta do projeto>\\ca-empresa.pem
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "ca-empresa.pem"

# Acessa o repositório de certificados pelo .NET. Não usa o provider Cert:
# nem Import-Module, que falham no subprocess deste ambiente.
CODIGO_CS = r"""
using System;
using System.Security.Cryptography.X509Certificates;
using System.Text;

public class CaExport {
    public static string Extrair() {
        var sb = new StringBuilder();
        string[] lojas = { "Root", "CA", "AuthRoot" };
        foreach (StoreLocation loc in new[]{ StoreLocation.LocalMachine, StoreLocation.CurrentUser }) {
            foreach (string nome in lojas) {
                try {
                    using (var s = new X509Store(nome, loc)) {
                        s.Open(OpenFlags.ReadOnly | OpenFlags.OpenExistingOnly);
                        foreach (var c in s.Certificates) {
                            sb.AppendLine("-----BEGIN CERTIFICATE-----");
                            sb.AppendLine(Convert.ToBase64String(c.RawData, Base64FormattingOptions.InsertLineBreaks));
                            sb.AppendLine("-----END CERTIFICATE-----");
                        }
                    }
                } catch (Exception e) {
                    sb.AppendLine("# ERRO " + loc + "/" + nome + ": " + e.Message);
                }
            }
        }
        return sb.ToString();
    }
}
"""


def exportar_do_windows() -> tuple[list[str], list[str]]:
    """
    Extrai os certificados das lojas do Windows.

    Devolve (blocos_pem, avisos).
    """
    script = "$cs = @'\n" + CODIGO_CS + "\n'@\nAdd-Type -TypeDefinition $cs -Language CSharp\n[CaExport]::Extrair()\n"

    proc = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=240,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"PowerShell falhou (rc={proc.returncode}): {proc.stderr.strip()[:400]}"
        )

    # Reconstrói os blocos PEM. O .NET insere quebras de linha CRLF dentro do
    # base64, então normalizamos linha a linha em vez de confiar no formato.
    blocos: list[str] = []
    avisos: list[str] = []
    atual: list[str] = []
    dentro = False
    for bruta in proc.stdout.splitlines():
        linha = bruta.strip()
        if linha.startswith("# ERRO"):
            avisos.append(linha)
            continue
        if linha == "-----BEGIN CERTIFICATE-----":
            dentro, atual = True, []
        elif linha == "-----END CERTIFICATE-----" and dentro:
            if atual:
                blocos.append(
                    "-----BEGIN CERTIFICATE-----\n"
                    + "\n".join(atual)
                    + "\n-----END CERTIFICATE-----\n"
                )
            dentro = False
        elif dentro and linha:
            atual.append(linha)

    return blocos, avisos


def _filtrar_x509(blocos: list[str]) -> list[str]:
    """Descarta o que não for um X.509 legível (se 'cryptography' existir)."""
    try:
        from cryptography import x509
    except ImportError:
        return blocos

    validos = []
    for pem in blocos:
        try:
            x509.load_pem_x509_certificate(pem.encode())
            validos.append(pem)
        except Exception:  # noqa: BLE001 -- certificado estranho: ignora
            continue
    return validos


def main() -> int:
    try:
        import certifi
    except ImportError:
        print("ERRO: instale 'certifi': pip install certifi", file=sys.stderr)
        return 1

    try:
        publicas = Path(certifi.where()).read_bytes()
    except OSError as e:
        print(f"ERRO: não consegui ler o bundle do certifi: {e}", file=sys.stderr)
        return 1
    print(f"certifi                    : {len(publicas):,} bytes")

    try:
        blocos, avisos = exportar_do_windows()
    except Exception as e:  # noqa: BLE001
        print(f"ERRO ao ler o repositório do Windows: {e}", file=sys.stderr)
        return 1

    for a in avisos:
        print(f"  aviso: {a[:100]}")
    if not blocos:
        print("ERRO: nenhum certificado encontrado no repositório do Windows.", file=sys.stderr)
        return 1

    blocos = _filtrar_x509(blocos)
    print(f"CA do Windows              : {len(blocos)} certificados")

    # Anexa só o que ainda não está no certifi, sem repetir.
    vistos = {publicas}
    novas: list[str] = []
    for pem in blocos:
        b = pem.encode()
        if b not in vistos:
            vistos.add(b)
            novas.append(pem)

    with SAIDA.open("wb") as f:
        f.write(publicas)
        if not publicas.endswith(b"\n"):
            f.write(b"\n")
        for pem in novas:
            f.write(pem.encode())

    print(f"Novas (não estavam no certifi): {len(novas)}")
    print(f"Arquivo gerado             : {SAIDA}")
    print()
    print("Agora defina a variável e teste:")
    print(f'  set REQUESTS_CA_BUNDLE={SAIDA}')
    print("  python -m neg35.cli modelos")
    print()
    print("Para valer sempre:")
    print(f'  setx REQUESTS_CA_BUNDLE "{SAIDA}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
