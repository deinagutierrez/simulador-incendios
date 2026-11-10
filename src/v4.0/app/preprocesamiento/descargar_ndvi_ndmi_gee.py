"""
NDVI y NDMI de Sentinel-2 para el dominio Las Lagunas-Potrerillos, 2023-hoy.

Mismas definiciones que GemeloIncendiosSanLuis/07_pipeline/gee_sanluis.py:
    NDVI = (B8  - B4 ) / (B8  + B4 )
    NDMI = (B8A - B11) / (B8A + B11)
Máscara de nubes: Cloud Score+ cs_cdf >= 0.60.

Salidas (en esta carpeta):
    serie_escenas_dominio.csv   una fila por fecha de paso (mosaico del día):
                                estadísticas sobre el dominio exacto de 25 celdas
    serie_escenas_celdas.csv    media por celda de 10 km y fecha
    mensual/NDVI_NDMI_AAAA_MM.tif  compuesto mediano mensual, 2 bandas
                                (NDVI, NDMI) int16 x10000, nodata -32768,
                                en la grilla exacta del dominio (EPSG:5345, 30 m,
                                1672 x 1671)

Uso:  python descargar_ndvi_ndmi_gee.py [--fin AAAA-MM-DD] [--sin-raster]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from pathlib import Path

import ee
import pandas as pd
import requests

AQUI = Path(__file__).resolve().parent
GEOJSON = AQUI.parent / "dominio_lagunas_potrerillos.geojson"
PROJECT = "miprojecto-508714"

FECHA_INI = "2023-01-01"
UMBRAL_NUBES = 0.60
ESCALA = 30
LOTE = 4          # fechas por consulta; más grande agota la memoria de GEE

# Grilla del dominio (ver ../README.md)
CRS = "EPSG:5345"
XMIN, YMAX = 3513060, 6417900
NCOL, NFIL = 1672, 1671
CRS_TRANSFORM = [30, 0, XMIN, 0, -30, YMAX]
NODATA = -32768


def traer(obj, intentos=4, espera=20):
    for n in range(intentos):
        try:
            return obj.getInfo()
        except Exception as e:
            if n == intentos - 1:
                raise
            print(f"   reintento {n + 1} tras error: {e}")
            time.sleep(espera)


def cargar_geometrias():
    d = json.loads(GEOJSON.read_text(encoding="utf-8"))
    dominio = celdas = None
    lista_celdas = []
    for f in d["features"]:
        tipo = f["properties"].get("tipo")
        if tipo == "dominio_exacto_25_celdas":
            dominio = ee.Geometry(f["geometry"], None, False)
        elif tipo == "celda_grilla_10km":
            lista_celdas.append(
                ee.Feature(ee.Geometry(f["geometry"], None, False), {"cid": f["properties"]["cid"]})
            )
    celdas = ee.FeatureCollection(lista_celdas)
    return dominio, celdas


def coleccion(aoi, ini, fin):
    cs = ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED")

    def preparar(img):
        despejado = img.select("cs_cdf").gte(UMBRAL_NUBES)
        r = img.select(["B4", "B8", "B8A", "B11"]).multiply(0.0001)
        ndvi = r.normalizedDifference(["B8", "B4"]).rename("NDVI")
        ndmi = r.normalizedDifference(["B8A", "B11"]).rename("NDMI")
        return (
            ndvi.addBands(ndmi)
            .updateMask(despejado)
            .set("fecha", img.date().format("YYYY-MM-dd"))
            .copyProperties(img, ["system:time_start"])
        )

    return (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(aoi)
        .filterDate(ini, fin)
        .linkCollection(cs, ["cs_cdf"])
        .map(preparar)
    )


def mosaico_diario(col, fechas):
    """Une los tiles del mismo día en una sola imagen. Cada fecha filtra por
    rango de fechas (no por propiedad) para que GEE no recorra la colección
    entera: filtrar por propiedad agota la memoria."""
    imgs = []
    for f in fechas:
        sig = (dt.date.fromisoformat(f) + dt.timedelta(days=1)).isoformat()
        sub = col.filterDate(f, sig)
        imgs.append(
            sub.mosaic().set(
                {"fecha": f, "system:time_start": ee.Date(f).millis(), "tiles": sub.size()}
            )
        )
    return ee.ImageCollection(imgs)


def stats_dominio(img, aoi):
    reductor = (
        ee.Reducer.mean()
        .combine(ee.Reducer.median(), sharedInputs=True)
        .combine(ee.Reducer.percentile([10, 90]), sharedInputs=True)
        .combine(ee.Reducer.stdDev(), sharedInputs=True)
        .combine(ee.Reducer.count(), sharedInputs=True)
    )
    s = img.reduceRegion(reductor, aoi, ESCALA, CRS, maxPixels=int(1e9), tileScale=8)
    total = (
        ee.Image.constant(1)
        .reduceRegion(ee.Reducer.count(), aoi, ESCALA, CRS, maxPixels=int(1e9))
        .get("constant")
    )
    return s, total


def serie_dominio(col, aoi, fechas):
    filas = []
    for i in range(0, len(fechas), LOTE):  # en lotes para no pasar el límite de getInfo
        lote = fechas[i:i + LOTE]
        sub = mosaico_diario(col, lote)

        def f(img):
            s, total = stats_dominio(img, aoi)
            return ee.Feature(None, s).set(
                {"fecha": img.get("fecha"), "tiles": img.get("tiles"), "px_total": total}
            )

        info = traer(ee.FeatureCollection(sub.map(f)))
        filas += [x["properties"] for x in info["features"]]
        print(f"   dominio: {min(i + LOTE, len(fechas))}/{len(fechas)} fechas")
    df = pd.DataFrame(filas)
    # el conteo ponderado en los bordes puede pasar apenas de 100
    df["pct_despejado"] = (100 * df["NDVI_count"] / df["px_total"]).clip(upper=100).round(2)
    orden = ["fecha", "tiles", "pct_despejado"]
    for b in ("NDVI", "NDMI"):
        orden += [f"{b}_mean", f"{b}_median", f"{b}_p10", f"{b}_p90", f"{b}_stdDev"]
    df = df[orden].sort_values("fecha").reset_index(drop=True)
    return df


def serie_celdas(col, celdas, fechas):
    filas = []
    for i in range(0, len(fechas), LOTE):
        lote = fechas[i:i + LOTE]
        sub = mosaico_diario(col, lote)

        def f(img):
            fecha = img.get("fecha")
            r = img.reduceRegions(
                celdas,
                ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True),
                ESCALA,
                CRS,
                tileScale=8,
            )
            return r.map(lambda x: x.set("fecha", fecha).setGeometry(None))

        info = traer(ee.FeatureCollection(sub.map(f)).flatten())
        filas += [x["properties"] for x in info["features"]]
        print(f"   celdas: {min(i + LOTE, len(fechas))}/{len(fechas)} fechas")
    df = pd.DataFrame(filas)
    df = df.rename(columns={"NDVI_mean": "NDVI", "NDMI_mean": "NDMI", "NDVI_count": "px_validos"})
    df = df[["fecha", "cid", "px_validos", "NDVI", "NDMI"]]
    return df.sort_values(["fecha", "cid"]).reset_index(drop=True)


def descargar_mensuales(col, aoi, ini, fin, carpeta):
    carpeta.mkdir(exist_ok=True)
    d = dt.date.fromisoformat(ini)
    fin_d = dt.date.fromisoformat(fin)
    resumen = []
    while d < fin_d:
        sig = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        nombre = f"NDVI_NDMI_{d:%Y_%m}"
        destino = carpeta / f"{nombre}.tif"
        sub = col.filterDate(str(d), str(min(sig, fin_d)))
        n = traer(sub.size())
        resumen.append({"mes": f"{d:%Y-%m}", "escenas": n})
        if n == 0:
            print(f"   {nombre}: sin escenas")
        elif destino.exists():
            print(f"   {nombre}: ya existe")
        else:
            img = (
                sub.median()
                .multiply(10000)
                .round()
                .toInt16()
                .unmask(NODATA)
                .clip(aoi)
                .unmask(NODATA)
            )
            url = img.getDownloadURL(
                {
                    "bands": ["NDVI", "NDMI"],
                    "crs": CRS,
                    "crs_transform": CRS_TRANSFORM,
                    "dimensions": f"{NCOL}x{NFIL}",
                    "format": "GEO_TIFF",
                }
            )
            for k in range(4):
                r = requests.get(url, timeout=600)
                if r.status_code == 200:
                    destino.write_bytes(r.content)
                    import rasterio
                    with rasterio.open(destino, "r+") as t:
                        t.set_band_description(1, "NDVI_x10000")
                        t.set_band_description(2, "NDMI_x10000")
                        t.nodata = NODATA
                    break
                print(f"   {nombre}: HTTP {r.status_code}, reintento")
                time.sleep(15)
            print(f"   {nombre}: {n} escenas -> {destino.name}")
        d = sig
    return pd.DataFrame(resumen)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fin", default=(dt.date.today() + dt.timedelta(days=1)).isoformat())
    ap.add_argument("--sin-raster", action="store_true")
    a = ap.parse_args()

    ee.Initialize(project=PROJECT)
    aoi, celdas = cargar_geometrias()
    col = coleccion(aoi, FECHA_INI, a.fin)

    fechas = sorted(set(traer(col.aggregate_array("fecha"))))
    print(f"{len(fechas)} fechas de paso de Sentinel-2 entre {fechas[0]} y {fechas[-1]}")

    print("Serie por escena (dominio)...")
    serie_dominio(col, aoi, fechas).to_csv(AQUI / "serie_escenas_dominio.csv", index=False)

    print("Serie por escena (celdas 10 km)...")
    serie_celdas(col, celdas, fechas).to_csv(AQUI / "serie_escenas_celdas.csv", index=False)

    if not a.sin_raster:
        print("Compuestos mensuales 30 m...")
        res = descargar_mensuales(col, aoi, FECHA_INI, a.fin, AQUI / "mensual")
        res.to_csv(AQUI / "mensual" / "escenas_por_mes.csv", index=False)

    print("Listo.")


if __name__ == "__main__":
    main()
