#!/usr/bin/env bash
# Instala el entorno (carpeta .venv) y comprueba que el clon funciona. Linux.
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "No se encontró $PY. Instalar Python 3.12 o superior y volver a ejecutar ./instalar.sh"
  exit 1
fi
[ -d .venv ] || "$PY" -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python herramientas/probar.py
