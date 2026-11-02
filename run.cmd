@echo off
REM ---------------------------------------------------------------------------
REM neg35 - atalho para a interface
REM
REM Duplo clique neste arquivo para abrir a tela no navegador.
REM
REM IMPORTANTE: sempre feche esta janela e abra de novo depois de uma
REM atualizacao, ou depois de mudar as pastas por fora. O programa le o
REM arquivo .env UMA vez, ao iniciar, e nao recarrega sozinho -- uma janela
REM antiga continua usando os valores velhos, e ai a tela discorda do .env.
REM
REM As duas linhas de ambiente abaixo resolvem o erro de certificado do
REM Kaspersky: a varredura de conexoes criptografadas reassina o certificado
REM do HTTPS, e o Python (que usa o pacote 'certifi') nao conhece a CA raiz
REM do antivirus. O arquivo ca-empresa.pem, gerado por tools\consertar_tls.py,
REM une as CAs publicas com as confiaveis do Windows.
REM
REM Se a chamada de API falhar com erro de certificado, rode uma vez:
REM     python tools\consertar_tls.py
REM ---------------------------------------------------------------------------

REM ---------------------------------------------------------------------------
REM ONDE ESTA O PYTHON -- isto ja deu "Permission denied" ao trocar as pastas
REM
REM MEDIDO nesta maquina: um ambiente virtual guardado dentro de C:\Temp
REM consegue gravar SOMENTE dentro de C:\Temp. Pastas de saida em outros
REM discos (E:, D:) falham com "sem permissao de escrita (Permission denied)"
REM mesmo com o ACL da pasta liberado para o usuario.
REM
REM   .venv\Scripts\python.exe              -> gravar em E: = FALHOU (errno 13)
REM   C:\neg35\venv\Scripts\python.exe      -> gravar em E: = OK
REM   C:\Program Files\Python313\python.exe -> gravar em E: = OK
REM
REM Mesmo usuario, mesma pasta, mesmo instante: o problema e o LUGAR do
REM ambiente, nao a permissao da pasta. Por isso o ambiente fica fora de C:\Temp.
REM Se um dia mover o projeto, mantenha o ambiente fora de C:\Temp.
REM ---------------------------------------------------------------------------

cd /d "%~dp0"

set "NEG35_PY="
if exist "C:\neg35\venv\Scripts\python.exe" (
    set "NEG35_PY=C:\neg35\venv\Scripts\python.exe"
) else if exist ".venv\Scripts\python.exe" (
    set "NEG35_PY=.venv\Scripts\python.exe"
)

if exist "ca-empresa.pem" (
    set "REQUESTS_CA_BUNDLE=%~dp0ca-empresa.pem"
    set "SSL_CERT_FILE=%~dp0ca-empresa.pem"
) else (
    echo.
    echo AVISO: ca-empresa.pem nao encontrado.
    echo Se a restauracao falhar com erro de certificado, rode uma vez:
    echo     python tools\consertar_tls.py
    echo.
)

if not defined NEG35_PY (
    echo.
    echo ERRO: ambiente nao preparado. Rode uma vez:
    echo     python tools\preparar_ambiente.py
    echo     python tools\instalar_wheels.py
    echo.
    pause
    exit /b 1
)

REM Avisa se o ambiente estiver dentro de C:\Temp: nesse caso nao grava fora.
echo %NEG35_PY% | find /i "C:\Temp" >nul
if not errorlevel 1 (
    echo.
    echo AVISO: usando o ambiente dentro de C:\Temp.
    echo Nesta maquina esse ambiente NAO consegue gravar em outros discos.
    echo Se as pastas de saida estiverem em E:, a conversao falha com
    echo "Permission denied". O ambiente correto fica em C:\neg35\venv.
    echo.
)

echo.
echo Iniciando a interface do neg35...
echo Para encerrar, feche esta janela ou pressione Ctrl+C.
echo.

"%NEG35_PY%" tools\app.py --abrir %*

if errorlevel 1 pause
