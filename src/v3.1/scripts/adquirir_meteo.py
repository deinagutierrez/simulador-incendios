"""Script independiente de adquisición meteorológica horaria (Open-Meteo).

Ejemplos:
  python scripts/adquirir_meteo.py --geometria primero_cuadrado.geojson --inicio 2024-09-17T00:00Z --fin 2024-10-10T03:00Z
  python scripts/adquirir_meteo.py --dominio las_lagunas_potrerillos --inicio 2022-08-25T00:00Z --fin 2022-09-15T00:00Z --modelo era5
  python scripts/adquirir_meteo.py --lon -65.59 --lat -32.61 --inicio ... --fin ... --tipo pronostico

Parámetros: geometría (GeoJSON) o dominio configurado o punto; fechas UTC; variables; modelo/fuente; directorio de salida.
Salidas: CSV largo (punto × hora), Parquet, CSV de la serie del dominio y JSON de metadatos (fuente, fecha de
adquisición, periodo, unidades, control de calidad, limitaciones).
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from incendios_sl import config as cfgmod  # noqa: E402
from incendios_sl.grilla import Grilla, geometria_a_crs  # noqa: E402
from incendios_sl.meteorology.openmeteo import adquirir, ConfigMeteo, VARIABLES_OBLIGATORIAS  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--geometria", help="GeoJSON del área (se usa su envolvente en EPSG:5345)")
    g.add_argument("--dominio", help="id de dominio configurado (escenarios/v3.1/dominios/dominio_<id>.yaml)")
    g.add_argument("--lon", type=float, help="longitud de un punto único (requiere --lat)")
    ap.add_argument("--lat", type=float)
    ap.add_argument("--inicio", required=True, help="fecha-hora inicial UTC, p. ej. 2024-09-17T00:00Z")
    ap.add_argument("--fin", required=True, help="fecha-hora final UTC")
    ap.add_argument("--variables", default=",".join(VARIABLES_OBLIGATORIAS + ["shortwave_radiation", "wind_gusts_10m", "vapour_pressure_deficit"]))
    ap.add_argument("--modelo", default="ecmwf_ifs", help="best_match | ecmwf_ifs | era5 | era5_land (histórico)")
    ap.add_argument("--tipo", default="historico", choices=["historico", "pronostico"])
    ap.add_argument("--puntos-lado", type=int, default=4, help="n: malla de n×n puntos (1 = un solo punto central)")
    ap.add_argument("--margen", type=float, default=10020.0, help="margen (m) alrededor del área para la malla de puntos")
    ap.add_argument("--salida", default=None, help="directorio de salida (defecto datos/inputSimulacion/meteo)")
    ap.add_argument("--etiqueta", default="meteo")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    if a.dominio:
        dom = cfgmod.cargar_dominio(a.dominio)
        grilla = Grilla.desde_config(dom).ampliar(a.margen)
    elif a.geometria:
        import geopandas as gpd
        gdf = gpd.read_file(a.geometria).to_crs("EPSG:5345")
        xmin, ymin, xmax, ymax = gdf.total_bounds
        grilla = Grilla("EPSG:5345", 30.0, xmin, ymin, xmax, ymax).ampliar(a.margen)
    else:
        if a.lat is None:
            ap.error("--lon requiere --lat")
        from shapely.geometry import Point
        p = geometria_a_crs(Point(a.lon, a.lat), "EPSG:4326", "EPSG:5345")
        grilla = Grilla("EPSG:5345", 30.0, p.x - 15, p.y - 15, p.x + 15, p.y + 15)
        a.puntos_lado = 1
    cfg = ConfigMeteo(modelo=a.modelo, variables=[v.strip() for v in a.variables.split(",") if v.strip()],
                      n_puntos_lado=a.puntos_lado, tipo=a.tipo)
    r = adquirir(grilla, a.inicio, a.fin, cfg, out_dir=Path(a.salida) if a.salida else None, etiqueta=a.etiqueta)
    print("Archivos:", {k: str(v) for k, v in r.items() if k in ("csv", "parquet", "json", "dominio_csv")})
    print("Desde caché:", r["desde_cache"], "| filas:", len(r["df"]), "| horas en la serie del dominio:", len(r["dominio"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
