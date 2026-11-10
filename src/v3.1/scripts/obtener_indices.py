"""Script independiente de obtención de NDVI y NDMI mediante Google Earth Engine.

Ejemplos:
  python scripts/obtener_indices.py --evento SL-2024-LASLAGUNAS
  python scripts/obtener_indices.py --geometria primero_cuadrado.geojson --inicio 2022-07-15 --fin 2022-09-01 \
      --coleccion COPERNICUS/S2_SR_HARMONIZED --resolucion 20 --umbral-nubes 0.6 --salida datos/inputSimulacion/indices/prueba --id prueba

Parámetros: geometría o evento configurado, fechas, colección (COPERNICUS/S2_SR_HARMONIZED o LANDSAT/LC08/C02/T1_L2),
resolución de salida (m), umbral de nubosidad (cs_cdf mínimo para S2), directorio de salida.
Salidas: ndvi, ndmi (int16 × 10000, NoData −32768), n_obs (observaciones válidas), metadatos JSON (escenas, nubosidad).
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from incendios_sl import config as cfgmod  # noqa: E402
from incendios_sl.grilla import Grilla  # noqa: E402
from incendios_sl.remote_sensing.gee_indices import obtener_indices  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--evento", help="id de evento configurado (usa su ventana, colección y umbral)")
    g.add_argument("--geometria", help="GeoJSON del área")
    ap.add_argument("--inicio"); ap.add_argument("--fin")
    ap.add_argument("--coleccion", default="COPERNICUS/S2_SR_HARMONIZED")
    ap.add_argument("--resolucion", type=float, default=20.0)
    ap.add_argument("--umbral-nubes", type=float, default=0.6, help="cs_cdf mínimo (Cloud Score+) para píxel válido")
    ap.add_argument("--compuesto", default="mediana", choices=["mediana", "promedio"])
    ap.add_argument("--margen", type=float, default=1020.0)
    ap.add_argument("--salida", default=None)
    ap.add_argument("--id", default="area")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    if a.evento:
        ev = cfgmod.cargar_evento(a.evento)
        dom = cfgmod.cargar_dominio(ev["dominio"])
        grilla = Grilla.desde_config(dom).ampliar(float(dom["margen_indices_m"]))
    else:
        if not (a.inicio and a.fin):
            ap.error("--geometria requiere --inicio y --fin")
        import geopandas as gpd
        gdf = gpd.read_file(a.geometria).to_crs("EPSG:5345")
        xmin, ymin, xmax, ymax = gdf.total_bounds
        grilla = Grilla("EPSG:5345", 30.0, xmin, ymin, xmax, ymax).ampliar(a.margen)
        ev = {"id": a.id, "indices": {"coleccion": a.coleccion, "ventana": [a.inicio, a.fin], "umbral_cs_cdf": a.umbral_nubes}}
    if a.salida:
        import incendios_sl.config as c
        c.dir_derivados = lambda *p, _base=Path(a.salida): (_base.mkdir(parents=True, exist_ok=True) or _base)  # type: ignore
    r = obtener_indices(ev, grilla, escala=a.resolucion, coleccion=a.coleccion if a.geometria else None,
                        umbral_cs=a.umbral_nubes if a.geometria else None, compuesto=a.compuesto)
    print({k: str(v) for k, v in r.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
