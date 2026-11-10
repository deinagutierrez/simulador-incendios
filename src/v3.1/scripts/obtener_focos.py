"""Extrae focos de calor (VIIRS 375 m SNPP/NOAA-20 vía LANCE y MODIS 1 km vía FIRMS) desde Google Earth Engine para un evento.

Uso:
    python scripts/obtener_focos.py --evento SL-2024-MESILLA [--margen-dias 2] [--margen-m 5000]

Salidas (mismo formato que los catálogos existentes en datos/inputSimulacion/catalogo/hotspots/):
    viirs_<evento>.csv  columnas: date, sat, acq_time_s, lon, lat, frp, conf, daynight
    modis_<evento>.csv  columnas: date, sat, lon, lat, t21, conf
Las coordenadas son los centros de píxel de las colecciones rasterizadas de GEE (375 m VIIRS, 1 km MODIS), no las
detecciones puntuales originales de FIRMS. `acq_time_s` es el valor de la banda `acq_time` (segundos desde 00 UTC del día,
interpretación verificada en la Etapa 1 contra el horario de paso de NOAA-20). `conf`/`daynight` son los códigos numéricos de GEE.
Ventana temporal: [inicio meteorología − margen, fin meteorología + margen]. Región: grilla del dominio + margen_m.
Los archivos del evento (viirs_/modis_<evento>.csv) se restringen a los focos a ≤ radio_cicatriz_m del polígono MapBiomas del
evento, para que las métricas temporales no incluyan otros incendios simultáneos del dominio; la extracción completa se guarda
en *_<evento>_dominio.csv.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from incendios_sl import config as cfgmod  # noqa: E402
from incendios_sl.data.preparar_dominio import grilla_dominio  # noqa: E402
from incendios_sl.remote_sensing.gee_comun import ee_init, region_ee  # noqa: E402

log = logging.getLogger("obtener_focos")

COLECCIONES_VIIRS = {"SNPP_VIIRS": "NASA/LANCE/SNPP_VIIRS/C2", "NOAA20_VIIRS": "NASA/LANCE/NOAA20_VIIRS/C2"}
COLECCION_MODIS = "FIRMS"


def _muestrear(ee, col, reg, banda_valida: str, bandas: list[str], escala: float, etiqueta: str) -> pd.DataFrame:
    """Para cada imagen diaria, muestrea los píxeles con detección (banda_valida enmascarada) y devuelve una tabla."""
    def por_imagen(img):
        img = ee.Image(img)
        fecha = img.date().format("YYYY-MM-dd")
        m = img.select(banda_valida).mask()
        pts = img.select(bandas).updateMask(m).sample(region=reg, scale=escala, geometries=True, tileScale=4)
        return pts.map(lambda f: f.set({"date": fecha, "sat": etiqueta}))
    fc = ee.FeatureCollection(col.map(por_imagen)).flatten()
    info = fc.getInfo()
    filas = []
    for f in info["features"]:
        lon, lat = f["geometry"]["coordinates"]
        filas.append({"date": f["properties"]["date"], "sat": etiqueta, "lon": lon, "lat": lat,
                      **{b: f["properties"].get(b) for b in bandas}})
    return pd.DataFrame(filas, columns=["date", "sat", "lon", "lat"] + bandas)


def _filtro_cicatriz(dom: dict, ev: dict, radio_m: float):
    """Devuelve una función que marca los focos a ≤ radio_m del polígono MapBiomas del evento (None si no hay oid)."""
    oid = str(ev.get("referencia_espacial", {}).get("oid", "")) if ev.get("referencia_espacial") else ""
    if not oid or radio_m <= 0:
        return None
    import geopandas as gpd
    gdf = gpd.read_file(cfgmod.ruta(dom["cicatrices"]["poligonos"]), where=f"oid = '{oid}'").to_crs("EPSG:5345")
    zona = gdf.geometry.iloc[0].buffer(radio_m)

    def dentro(df: pd.DataFrame) -> pd.Series:
        if not len(df):
            return pd.Series([], dtype=bool)
        pts = gpd.GeoSeries(gpd.points_from_xy(df.lon, df.lat), crs="EPSG:4326").to_crs("EPSG:5345")
        return pts.within(zona).to_numpy()
    return dentro


def obtener_focos(id_evento: str, margen_dias: int = 2, margen_m: float = 5000.0, radio_cicatriz_m: float = 3000.0) -> dict[str, Path]:
    ee = ee_init()
    ev = cfgmod.cargar_evento(id_evento); dom = cfgmod.cargar_dominio(ev["dominio"])
    g = grilla_dominio(dom).ampliar(margen_m)
    reg = region_ee(g)
    t0 = (pd.Timestamp(ev["meteorologia"]["inicio_utc"]) - pd.Timedelta(days=margen_dias)).strftime("%Y-%m-%d")
    t1 = (pd.Timestamp(ev["meteorologia"]["fin_utc"]) + pd.Timedelta(days=margen_dias + 1)).strftime("%Y-%m-%d")
    odir = cfgmod.dir_catalogo() / "hotspots"; odir.mkdir(parents=True, exist_ok=True)
    out = {"viirs": odir / f"viirs_{id_evento}.csv", "modis": odir / f"modis_{id_evento}.csv",
           "viirs_dominio": odir / f"viirs_{id_evento}_dominio.csv", "modis_dominio": odir / f"modis_{id_evento}_dominio.csv"}
    filtro = _filtro_cicatriz(dom, ev, radio_cicatriz_m)

    partes = []
    for etiqueta, cid in COLECCIONES_VIIRS.items():
        col = ee.ImageCollection(cid).filterBounds(reg).filterDate(t0, t1)
        n = col.size().getInfo()
        log.info("%s: %d imágenes diarias en %s..%s", cid, n, t0, t1)
        if n:
            df = _muestrear(ee, col, reg, "Bright_ti4", ["acq_time", "frp", "confidence", "DayNight"], 375.0, etiqueta)
            log.info("%s: %d detecciones", etiqueta, len(df))
            partes.append(df)
    viirs = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=["date", "sat", "acq_time", "lon", "lat", "frp", "confidence", "DayNight"])
    viirs = viirs.rename(columns={"acq_time": "acq_time_s", "confidence": "conf", "DayNight": "daynight"})
    viirs = viirs[["date", "sat", "acq_time_s", "lon", "lat", "frp", "conf", "daynight"]].sort_values(["date", "sat", "acq_time_s"])
    viirs.to_csv(out["viirs_dominio"], index=False)
    n_dom_v = len(viirs)
    if filtro is not None:
        viirs = viirs[filtro(viirs)]
    viirs.to_csv(out["viirs"], index=False)
    log.info("VIIRS: %d detecciones en el dominio, %d a ≤ %.0f m de la cicatriz del evento", n_dom_v, len(viirs), radio_cicatriz_m)

    col = ee.ImageCollection(COLECCION_MODIS).filterBounds(reg).filterDate(t0, t1)
    n = col.size().getInfo()
    log.info("FIRMS (MODIS): %d imágenes diarias", n)
    modis = _muestrear(ee, col, reg, "T21", ["T21", "confidence"], 1000.0, "MODIS") if n else pd.DataFrame(columns=["date", "sat", "lon", "lat", "T21", "confidence"])
    modis = modis.rename(columns={"T21": "t21", "confidence": "conf"})[["date", "sat", "lon", "lat", "t21", "conf"]].sort_values(["date"])
    modis.to_csv(out["modis_dominio"], index=False)
    n_dom_m = len(modis)
    if filtro is not None:
        modis = modis[filtro(modis)]
    modis.to_csv(out["modis"], index=False)
    log.info("MODIS: %d detecciones en el dominio, %d a ≤ %.0f m de la cicatriz del evento", n_dom_m, len(modis), radio_cicatriz_m)

    resumen = {"evento": id_evento, "ventana": [t0, t1], "margen_m": margen_m, "radio_cicatriz_m": radio_cicatriz_m,
               "viirs_dominio": int(n_dom_v), "modis_dominio": int(n_dom_m), "viirs": int(len(viirs)), "modis": int(len(modis)),
               "viirs_por_dia": viirs.groupby("date").size().to_dict() if len(viirs) else {},
               "modis_por_dia": modis.groupby("date").size().to_dict() if len(modis) else {}}
    import json
    with open(odir / f"resumen_focos_{id_evento}.json", "w", encoding="utf-8") as f:
        json.dump(resumen, f, indent=2, ensure_ascii=False)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--evento", required=True)
    ap.add_argument("--margen-dias", type=int, default=2)
    ap.add_argument("--margen-m", type=float, default=5000.0)
    ap.add_argument("--radio-cicatriz-m", type=float, default=3000.0, help="0 = sin filtrar (todo el dominio)")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    r = obtener_focos(a.evento, a.margen_dias, a.margen_m, a.radio_cicatriz_m)
    print({k: str(v) for k, v in r.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
