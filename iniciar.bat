@echo off
rem Gestor ReXNative: cria o ambiente Python (.venv, uma vez), instala o que falta e abre a app
rem em http://127.0.0.1:8360/ no browser. Fechar esta janela fecha a app.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo A criar o ambiente Python em .venv ...
  python -m venv --system-site-packages .venv || goto :erro
)
".venv\Scripts\python.exe" -c "import fastapi, uvicorn, internetarchive, PIL" 2>nul || (
  echo A instalar as dependencias ...
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || goto :erro
)
".venv\Scripts\python.exe" -m gestor %*
goto :eof
:erro
echo.
echo Algo falhou: confirma que o Python 3.11+ esta instalado e no PATH.
pause
