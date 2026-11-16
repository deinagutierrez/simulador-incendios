@echo off
rem Arranca el simulador: levanta el servidor local y abre el navegador en http://127.0.0.1:8000. Windows.
rem Opciones (se pasan a app\servir.py): --puerto 8010, --sin-navegador, --con-simulado. Se cierra con Ctrl+C.
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\activate.bat (
  echo Falta el entorno. Ejecutar primero instalar.bat
  exit /b 1
)
call .venv\Scripts\activate.bat
python app\servir.py %*
exit /b %errorlevel%
