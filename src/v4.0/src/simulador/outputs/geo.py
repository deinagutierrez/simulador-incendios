"""Productos geoespaciales: GeoTIFF, GeoJSON (WGS84, RFC 7946) y CSV."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.crs import CRS

from .indicadores import mascaras_en, poligonos


def escribir_geotiff(ruta: Path, arr: np.ndarray, grilla, nodata, dtype: str = "float32", descripcion: str = ""):
    perfil = dict(driver="GTiff", height=grilla.alto, width=grilla.ancho, count=1, dtype=dtype,
                  crs=CRS.from_user_input(grilla.crs), transform=grilla.transform, nodata=nodata, compress="deflate")
    with rasterio.open(ruta, "w", **perfil) as dst:
        dst.write(arr.astype(dtype), 1)
        if descripcion:
            dst.set_band_description(1, descripcion)
    return ruta


def exportar_rasters(au, carpeta: Path, nombre_toa: str | None = None):
    g = au.capas.grilla
    out = {}
    toa = np.where(np.isnan(au.t_llegada), np.nan, au.t_llegada).astype("float32")
    out["hora_llegada"] = escribir_geotiff(carpeta / "hora_llegada_min.tif", toa, g, np.nan, "float32", "minutos desde t0 (NaN = no arde)")
    out["intensidad"] = escribir_geotiff(carpeta / "intensidad_max_kw_m.tif", np.where(au.afectada, au.intensidad_max, np.nan), g, np.nan, "float32", "kW/m")
    out["ros"] = escribir_geotiff(carpeta / "ros_max_m_min.tif", np.where(au.afectada, au.ros_max, np.nan), g, np.nan, "float32", "m/min")
    out["llama"] = escribir_geotiff(carpeta / "longitud_llama_max_m.tif", np.where(au.afectada, au.llama_max, np.nan), g, np.nan, "float32", "m")
    out["estado"] = escribir_geotiff(carpeta / "estado_final.tif", au.estado, g, 255, "uint8", "0 NB, 1 combustible, 2 ignición, 3 combustión, 4 quemado")
    if nombre_toa:
        out["toa_evaluador"] = escribir_geotiff(carpeta / nombre_toa, toa, g, np.nan, "float32", "minutos desde t0 (NaN = no arde)")
    return out


def exportar_perimetros(au, horas: list[tuple[int, float]], carpeta: Path) -> Path:
    """GeoJSON (WGS84) con un polígono por hora (área afectada acumulada)."""
    import geopandas as gpd
    g = au.capas.grilla
    filas = []
    for h, t_min in horas:
        af, comb, _, _ = mascaras_en(au, t_min)
        pol = poligonos(af, g)
        if pol is None:
            continue
        ts = (au.t0 + pd.Timedelta(minutes=t_min)).tz_convert("America/Argentina/San_Luis").isoformat()
        filas.append({"hora": h, "timestamp": ts, "minutos_desde_t0": float(t_min), "ha": round(pol.area / 1e4, 2), "geometry": pol})
    gdf = gpd.GeoDataFrame(filas, geometry="geometry", crs=g.crs) if filas else gpd.GeoDataFrame(geometry=[], crs=g.crs)
    ruta = carpeta / "perimetros_horarios.geojson"
    gdf.to_crs("EPSG:4326").to_file(ruta, driver="GeoJSON")
    return ruta


def exportar_csv(indicadores: list[dict], carpeta: Path) -> Path:
    filas = []
    for d in indicadores:
        fila = {"hora": d["hora_indice"], "timestamp": d["timestamp"], "minutos_desde_t0": d["minutos_desde_t0"]}
        for grupo in ("superficie", "perimetro", "frente", "meteo"):
            for k, v in d[grupo].items():
                fila[f"{grupo}_{k}"] = v
        for k, v in d["exposicion"].items():
            if not isinstance(v, list):
                fila[f"exposicion_{k}"] = v
        for k, v in d["estado_celdas"].items():
            fila[f"celdas_{k}"] = v
        for grupo in ("supresion", "contencion"):          # solo si están activas (sin ellas la tabla no cambia)
            for k, v in (d.get(grupo) or {}).items():
                if not isinstance(v, (list, dict)):
                    fila[f"{grupo}_{k}"] = v
        fila["alertas"] = " | ".join(d["alertas"])
        filas.append(fila)
    ruta = carpeta / "serie_indicadores.csv"
    pd.DataFrame(filas).to_csv(ruta, index=False, encoding="utf-8", lineterminator="\n")
    return ruta


def escribir_json(d: dict, ruta: Path):
    Path(ruta).write_text(json.dumps(d, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (pd.Timestamp,)):
        return o.isoformat()
    return str(o)
