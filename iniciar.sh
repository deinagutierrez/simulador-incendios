#!/usr/bin/env bash
# Arranca el simulador: levanta el servidor local y abre el navegador en http://127.0.0.1:8000. Linux.
# Opciones (se pasan a app/servir.py): --puerto 8010, --sin-navegador, --con-simulado. Se cierra con Ctrl+C.
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -f .venv/bin/activate ]; then
  echo "Falta el entorno. Ejecutar primero ./instalar.sh"
  exit 1
fi
# shellcheck disable=SC1091
. .venv/bin/activate
exec python app/servir.py "$@"
