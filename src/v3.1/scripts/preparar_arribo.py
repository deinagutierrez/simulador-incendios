"""Tiempo de arribo desde los cuarteles de bomberos por la red vial sobre el dominio (docs/13 §6).

Uso: python scripts/preparar_arribo.py [--dominio las_lagunas_potrerillos] [--modelo modelo_v2]
Salida: datos/inputSimulacion/infraestructura/arribo_<dominio>.npz y tiempo_arribo_<dominio>.tif (se reutilizan si están vigentes).
Las velocidades por clase de vía y a campo traviesa se leen de `contencion.arribo` del YAML del modelo.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from incendios_sl import config as cfgmod  # noqa: E402
from incendios_sl.data.arribo import preparar_arribo  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--dominio", default="las_lagunas_potrerillos"); ap.add_argument("--modelo", default="modelo_v2")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    arr = (cfgmod.cargar_modelo(a.modelo).get("contencion", {}) or {}).get("arribo", {}) or {}
    t = time.time()
    p = preparar_arribo(cfgmod.cargar_dominio(a.dominio), velocidades=arr.get("velocidad_kmh"), campo_traviesa_kmh=float(arr.get("campo_traviesa_kmh", 3.0)),
                        res_m=float(arr.get("res_m", 100.0)), margen_m=float(arr.get("margen_m", 120000.0)), max_h=float(arr.get("max_h", 8.0)))
    print(f"{p} ({time.time() - t:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
