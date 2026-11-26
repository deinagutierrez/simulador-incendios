#!/usr/bin/env bash
# Instala el entorno (carpeta .venv) y comprueba que el clon funciona. Linux.
#
# El entorno usa siempre Python 3.14, la versión con la que se verificaron los motores y las bibliotecas de
# requirements.txt. Sirve cualquier Python 3 del sistema, también uno más nuevo (3.15, 3.16...):
#   1. si hay un python3.14 (o se indica otro con PYTHON=...), se usa ese;
#   2. si no, se baja Python 3.14 con uv (https://docs.astral.sh/uv/), sin sudo y sin tocar el Python del sistema.
#      uv se instala en .instalador/ con el Python que haya; el Python 3.14 queda en la carpeta de uv del usuario.
set -euo pipefail
cd "$(dirname "$0")"

VERSION="3.14"
UV_VERSION="0.13.7"

version_de() { "$1" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true; }

# Un .venv de otra versión (por ejemplo, de un intento anterior con el Python del sistema) se rehace.
if [ -x .venv/bin/python ] && [ "$(version_de .venv/bin/python)" != "$VERSION" ]; then
  echo "El entorno .venv es de Python $(version_de .venv/bin/python); se rehace con Python $VERSION."
  rm -rf .venv
fi

if [ ! -x .venv/bin/python ]; then
  PY="${PYTHON:-}"
  if [ -z "$PY" ] && command -v "python$VERSION" >/dev/null 2>&1; then
    PY="python$VERSION"
  fi
  if [ -n "$PY" ]; then
    if [ "$(version_de "$PY")" != "$VERSION" ]; then
      echo "Aviso: $PY es Python $(version_de "$PY"); lo verificado es $VERSION."
    fi
    "$PY" -m venv .venv
  else
    # Sin Python 3.14 en el sistema: se usa uv para bajarlo.
    UV="$(command -v uv || true)"
    if [ -z "$UV" ]; then
      BASE="$(command -v python3 || command -v python || true)"
      if [ -z "$BASE" ]; then
        echo "No se encontró Python. Instalar cualquier Python 3 y volver a ejecutar ./instalar.sh"
        exit 1
      fi
      echo "No hay Python $VERSION en el sistema: se instala uv $UV_VERSION en .instalador/ para bajarlo."
      [ -x .instalador/bin/uv ] || { "$BASE" -m venv .instalador && .instalador/bin/python -m pip install -q "uv==$UV_VERSION"; }
      UV=".instalador/bin/uv"
    fi
    "$UV" python install "$VERSION"
    "$UV" venv --seed --python "$VERSION" .venv
  fi
fi

# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python herramientas/probar.py
