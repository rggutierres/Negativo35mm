@echo off
REM ---------------------------------------------------------------------------
REM neg35 - atalho para o fluxo em lote
REM
REM Duplo clique neste arquivo para rodar.
REM
REM As duas linhas de ambiente abaixo resolvem o erro de certificado do
REM Kaspersky: a varredura de conexoes criptografadas reassina o certificado
REM do HTTPS, e o Python (que usa o pacote 'certifi') nao conhece a CA raiz
REM do antivirus. O arquivo ca-empresa.pem, gerado por tools\consertar_tls.py,
REM une as CAs publicas com as confiaveis do Windows.
REM
REM Se o ca-empresa.pem nao existir, rode uma vez:
REM     python tools\consertar_tls.py
REM ---------------------------------------------------------------------------

cd /d "%~dp0"

if exist "ca-empresa.pem" (
    set "REQUESTS_CA_BUNDLE=%~dp0ca-empresa.pem"
    set "SSL_CERT_FILE=%~dp0ca-empresa.pem"
) else (
    echo.
    echo AVISO: ca-empresa.pem nao encontrado.
    echo Se a chamada de API falhar com erro de certificado, rode uma vez:
    echo     python tools\consertar_tls.py
    echo.
)

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo ERRO: ambiente nao preparado. Rode uma vez:
    echo     python tools\preparar_ambiente.py
    echo     python tools\instalar_wheels.py
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" tools\lote.py %*

REM paus só quando foi duplo clique (sem argumentos), para a janela nao fechar
if "%~1"=="" pause
