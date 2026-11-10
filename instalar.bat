@echo off
rem Instala el entorno (carpeta .venv) y comprueba que el clon funciona. Windows.
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo No se encontro Python. Instalar Python 3.12 o superior desde python.org y volver a ejecutar instalar.bat
  exit /b 1
)
if not exist .venv (
  python -m venv .venv
  if errorlevel 1 exit /b 1
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
python herramientas\probar.py
exit /b %errorlevel%
