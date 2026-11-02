@echo off
REM ---------------------------------------------------------------------------
REM neg35 - reiniciar  (use este depois de uma atualizacao)
REM
REM Fecha qualquer janela do neg35 que esteja aberta e abre uma nova.
REM
REM Por que isto existe: o Python carrega o codigo UMA vez, ao iniciar, e nao
REM recarrega. Uma janela aberta antes de uma correcao continua rodando o
REM codigo antigo -- e ai o erro antigo reaparece, como se nada tivesse sido
REM corrigido. Ja aconteceu varias vezes.
REM
REM Se preferir o comportamento normal, use o run.cmd.
REM ---------------------------------------------------------------------------

cd /d "%~dp0"

echo.
echo Encerrando janelas antigas do neg35...
powershell -NoProfile -Command ^
  "$alvos = Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*app.py*' -and $_.CommandLine -like '*neg35*' };" ^
  "if ($alvos) { $alvos | ForEach-Object { Write-Host ('  encerrando PID ' + $_.ProcessId); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } } else { Write-Host '  nenhuma janela antiga encontrada' }"

REM dá um tempo para a porta ser liberada
timeout /t 2 /nobreak >nul

if exist "ca-empresa.pem" (
    set "REQUESTS_CA_BUNDLE=%~dp0ca-empresa.pem"
    set "SSL_CERT_FILE=%~dp0ca-empresa.pem"
)

if not exist ".venv\Scripts\python.exe" (
    echo ERRO: ambiente nao preparado. Rode tools\preparar_ambiente.py
    pause
    exit /b 1
)

REM O ambiente precisa ficar FORA de C:\Temp (ver o comentario do run.cmd).
REM Dentro de C:\Temp ele nao consegue gravar em outros discos e a conversao
REM falha com "Permission denied" ao usar pastas em E:.
set "NEG35_PY="
if exist "C:\neg35\venv\Scripts\python.exe" (
    set "NEG35_PY=C:\neg35\venv\Scripts\python.exe"
) else (
    set "NEG35_PY=.venv\Scripts\python.exe"
    echo AVISO: usando o ambiente dentro de C:\Temp; ele nao grava em outros discos.
)

echo.
echo Iniciando o neg35 (versao nova)...
echo Para encerrar, feche esta janela ou pressione Ctrl+C.
echo.

"%NEG35_PY%" tools\app.py --abrir %*

if errorlevel 1 pause
