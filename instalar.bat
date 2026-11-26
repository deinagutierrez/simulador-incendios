@echo off
rem Instala el entorno (carpeta .venv) y comprueba que el clon funciona. Windows.
rem
rem El entorno usa siempre Python 3.14, la version con la que se verificaron los motores y las bibliotecas de
rem requirements.txt. Sirve cualquier Python 3 instalado, tambien uno mas nuevo (3.15, 3.16...):
rem   1. si el lanzador "py" tiene Python 3.14, se usa ese;
rem   2. si no, se baja Python 3.14 con uv (https://docs.astral.sh/uv/), sin permisos de administrador.
rem      uv se instala en .instalador\ con el Python que haya; el Python 3.14 queda en la carpeta de uv del usuario.
setlocal
cd /d "%~dp0"
set VERSION=3.14
set UV_VERSION=0.13.7

rem Un .venv de otra version (por ejemplo, de un intento anterior) se rehace.
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe -c "import sys; sys.exit(0 if '%%d.%%d' %% sys.version_info[:2] == '%VERSION%' else 1)"
  if errorlevel 1 (
    echo El entorno .venv no es de Python %VERSION%; se rehace.
    rmdir /s /q .venv
  )
)

if exist .venv\Scripts\python.exe goto instalar

py -%VERSION% -c "pass" >nul 2>nul
if not errorlevel 1 (
  py -%VERSION% -m venv .venv
  if errorlevel 1 exit /b 1
  goto instalar
)

rem Sin Python 3.14: se usa uv para bajarlo.
set UV=uv
where uv >nul 2>nul
if not errorlevel 1 goto con_uv
set BASE=python
where python >nul 2>nul
if errorlevel 1 (
  py -3 -c "pass" >nul 2>nul
  if errorlevel 1 (
    echo No se encontro Python. Instalar cualquier Python 3 desde python.org y volver a ejecutar instalar.bat
    exit /b 1
  )
  set BASE=py -3
)
echo No hay Python %VERSION% instalado: se instala uv %UV_VERSION% en .instalador\ para bajarlo.
if not exist .instalador\Scripts\uv.exe (
  %BASE% -m venv .instalador
  if errorlevel 1 exit /b 1
  .instalador\Scripts\python.exe -m pip install -q uv==%UV_VERSION%
  if errorlevel 1 exit /b 1
)
set UV=.instalador\Scripts\uv.exe
:con_uv
%UV% python install %VERSION%
if errorlevel 1 exit /b 1
%UV% venv --seed --python %VERSION% .venv
if errorlevel 1 exit /b 1

:instalar
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
python herramientas\probar.py
exit /b %errorlevel%
