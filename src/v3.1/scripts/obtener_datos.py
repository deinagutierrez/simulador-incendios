"""Descarga insumos pesados que no están en el repositorio (hoy: Topografia/ con el DEM ASTER, y opcionalmente
indices/) desde el release de GitHub. Los datos de simulación ya están en datos/inputSimulacion/.

Uso:
  python scripts/obtener_datos.py --destino /ruta/a/datos_incendios [--url ...] [--solo-derivados]
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
import zipfile
from pathlib import Path

URL = "https://github.com/gvcosta/Gemelos_Digitales_Incendios_UNSL/releases/download/v1.0-artefacto/simulador_v1.zip"
PREFIJO = "simulador/"
CARPETAS_DATOS = ("Topografia/", "datos/inputSimulacion/indices/")
ARCHIVOS_DATOS = ()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--destino", required=True)
    ap.add_argument("--url", default=URL)
    ap.add_argument("--zip", help="zip ya descargado (evita la descarga)")
    ap.add_argument("--solo-derivados", action="store_true", help="extraer solo datos/inputSimulacion/indices")
    a = ap.parse_args()
    destino = Path(a.destino); destino.mkdir(parents=True, exist_ok=True)
    zpath = Path(a.zip) if a.zip else destino / "simulador_v1.zip"
    if not zpath.exists():
        print(f"descargando {a.url} (1,4 GB)…")
        def prog(n, bs, total):
            if total > 0 and n % 200 == 0:
                print(f"\r  {n * bs / 1e9:.2f} / {total / 1e9:.2f} GB", end="", flush=True)
        urllib.request.urlretrieve(a.url, zpath, prog); print()
    carpetas = ("datos/inputSimulacion/indices/",) if a.solo_derivados else CARPETAS_DATOS
    archivos = () if a.solo_derivados else ARCHIVOS_DATOS
    n = 0
    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            rel = info.filename[len(PREFIJO):] if info.filename.startswith(PREFIJO) else info.filename
            if info.is_dir() or not (rel.startswith(carpetas) or rel in archivos):
                continue
            out = destino / rel; out.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(out, "wb") as dst:
                dst.write(src.read())
            n += 1
    print(f"{n} archivos en {destino}. Para que el código los vea, definí INCENDIOS_SL_DATOS={destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
