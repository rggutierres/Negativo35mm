@echo off
REM ---------------------------------------------------------------------------
REM neg35 - verificar  (confere se a janela aberta esta atualizada)
REM
REM Rode este arquivo quando algo parecer "nao funcionar mesmo depois da
REM correcao". Ele pergunta ao programa que esta rodando quais recursos ele
REM tem, e diz o que esta faltando.
REM
REM Tambem mostra QUAL interpretador esta em uso e se ele consegue gravar nas
REM pastas de saida -- foi o que explicou um "Permission denied" que nao era
REM permissao de pasta (ver o comentario do run.cmd).
REM ---------------------------------------------------------------------------

cd /d "%~dp0"

set "NEG35_PY="
if exist "C:\neg35\venv\Scripts\python.exe" (
    set "NEG35_PY=C:\neg35\venv\Scripts\python.exe"
) else if exist ".venv\Scripts\python.exe" (
    set "NEG35_PY=.venv\Scripts\python.exe"
)

if not defined NEG35_PY (
    echo ERRO: ambiente nao preparado.
    pause
    exit /b 1
)

echo Interpretador: %NEG35_PY%
echo.

"%NEG35_PY%" tools\verificar_janela.py
pause
