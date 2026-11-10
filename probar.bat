@echo off
rem Vuelve a comprobar que todo funciona (usa el entorno .venv si existe). Agregar --rapido para omitir las corridas cortas.
setlocal
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
python herramientas\probar.py %*
exit /b %errorlevel%
