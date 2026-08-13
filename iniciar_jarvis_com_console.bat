@echo off
REM iniciar_jarvis_com_console.bat
REM =================================
REM Mesma coisa que "Iniciar Jarvis.vbs", mas com o console visível --
REM use este pra diagnosticar um problema (Python não encontrado,
REM dependência faltando, erro na inicialização), já que o .vbs não
REM mostra nada na tela se der errado.
cd /d "%~dp0"
set "PYTHON_REAL=%LocalAppData%\Programs\Python\Python312\python.exe"
if exist "%PYTHON_REAL%" (
    "%PYTHON_REAL%" main.py
) else (
    python main.py
)
pause
