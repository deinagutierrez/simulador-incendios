#!/usr/bin/env bash
# Vuelve a comprobar que todo funciona (usa el entorno .venv si existe). Agregar --rapido para omitir las corridas cortas.
set -euo pipefail
cd "$(dirname "$0")"
# shellcheck disable=SC1091
[ -f .venv/bin/activate ] && . .venv/bin/activate
python herramientas/probar.py "$@"
