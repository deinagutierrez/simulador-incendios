"""NDVI y NDMI pre-incendio desde Google Earth Engine (Sentinel-2 SR Harmonized + Cloud Score+; Landsat 8/9 opcional).

Salidas (por evento, en datos/inputSimulacion/indices/<evento>/):
- ndvi_<evento>.tif, ndmi_<evento>.tif   int16 × 10000, NoData -32768, a `escala` m sobre la grilla de índices
- n_obs_<evento>.tif                      uint8: número de observaciones válidas por píxel usadas en la mediana
- metadatos_<evento>.json                 escenas usadas (fecha, tesela, nubosidad, fracción despejada), parámetros

NDVI = (NIR − Rojo)/(NIR + Rojo); NDMI = (NIR − SWIR1)/(NIR + SWIR1).
Sentinel-2: NIR = B8 (10 m), Rojo = B4 (10 m), SWIR1 = B11 (20 m); reflectancia = DN/10000 (colección armonizada).
Landsat C2 L2: NIR = SR_B5, Rojo = SR_B4, SWIR1 = SR_B6; reflectancia = DN·2.75e-5 − 0.2; máscara QA_PIXEL.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .. import config as cfgmod
from ..grilla import Grilla
from ..procedencia import escribir_procedencia, producto_vigente, ahora_utc
from .gee_comun import ee_init, region_ee, descargar_imagen_a_grilla

log = logging.getLogger(__name__)
NODATA = -32768
ESCALA_IDX = 10000


def _s2_coleccion(ee, reg, inicio: str, fin: str, umbral_cs: float):
    cs = ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED")
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(reg).filterDate(inicio, fin)
           .linkCollection(cs, ["cs_cdf"]))

    def prep(img):
        valido = img.select("cs_cdf").gte(umbral_cs)
        refl = img.select(["B4", "B8", "B11"]).divide(10000)
        ndvi = refl.normalizedDifference(["B8", "B4"]).rename("ndvi")
        ndmi = refl.normalizedDifference(["B8", "B11"]).rename("ndmi")
        return (ee.Image.cat([ndvi, ndmi]).updateMask(valido)
                .copyProperties(img, ["system:time_start", "MGRS_TILE", "CLOUDY_PIXEL_PERCENTAGE"]))
    return col.map(prep), col


def _landsat_coleccion(ee, reg, inicio: str, fin: str):
    def prep(img):
        qa = img.select("QA_PIXEL")
        # bits 1 dilated cloud, 3 cloud, 4 cloud shadow, 5 snow -> inválidos
        mascara = qa.bitwiseAnd(0b11010).eq(0)
        refl = img.select(["SR_B4", "SR_B5", "SR_B6"]).multiply(2.75e-5).add(-0.2)
        ndvi = refl.normalizedDifference(["SR_B5", "SR_B4"]).rename("ndvi")
        ndmi = refl.normalizedDifference(["SR_B5", "SR_B6"]).rename("ndmi")
        return (ee.Image.cat([ndvi, ndmi]).updateMask(mascara)
                .copyProperties(img, ["system:time_start", "CLOUD_COVER", "WRS_PATH", "WRS_ROW"]))
    l8 = ee.ImageCollection("LANDSAT/LC08/C02/T1_L2").filterBounds(reg).filterDate(inicio, fin)
    l9 = ee.ImageCollection("LANDSAT/LC09/C02/T1_L2").filterBounds(reg).filterDate(inicio, fin)
    col = l8.merge(l9)
    return col.map(prep), col


def _escenas_info(ee, col_idx, reg, es_s2: bool) -> list[dict[str, Any]]:
    def f(img):
        fr = img.select("ndvi").mask().reduceRegion(ee.Reducer.mean(), reg, 300, maxPixels=1e9).get("ndvi")
        props = {"fecha": img.date().format("YYYY-MM-dd"), "fraccion_valida": fr}
        if es_s2:
            props.update({"tesela": img.get("MGRS_TILE"), "nubosidad_escena_pct": img.get("CLOUDY_PIXEL_PERCENTAGE")})
        else:
            props.update({"path": img.get("WRS_PATH"), "row": img.get("WRS_ROW"), "nubosidad_escena_pct": img.get("CLOUD_COVER")})
        return ee.Feature(None, props)
    fc = col_idx.map(f)
    info = fc.getInfo()["features"]
    return [x["properties"] for x in info]


def obtener_indices(evento: dict[str, Any], grilla_idx: Grilla, escala: float = 20.0, coleccion: str | None = None,
                    umbral_cs: float | None = None, compuesto: str = "mediana") -> dict[str, Path]:
    """Calcula en GEE el compuesto NDVI/NDMI pre-incendio y descarga solo el recorte a la grilla de índices."""
    ee = ee_init()
    cfg = evento["indices"]
    coleccion = coleccion or cfg["coleccion"]
    umbral_cs = umbral_cs if umbral_cs is not None else float(cfg.get("umbral_cs_cdf", 0.6))
    inicio, fin = cfg["ventana"]
    reg = region_ee(grilla_idx)
    odir = cfgmod.dir_procesados() / "indices" / evento["id"]; odir.mkdir(parents=True, exist_ok=True)
    out = {k: odir / f"{k}_{evento['id']}.tif" for k in ("ndvi", "ndmi", "n_obs")}
    meta_path = odir / f"metadatos_{evento['id']}.json"
    params = {"coleccion": coleccion, "ventana": [inicio, fin], "umbral_cs_cdf": umbral_cs, "compuesto": compuesto,
              "escala_m": escala, "grilla": grilla_idx.como_dict()}
    if all(producto_vigente(p, params) for p in out.values()):
        return out | {"metadatos": meta_path}

    es_s2 = "S2" in coleccion
    col_idx, col_raw = _s2_coleccion(ee, reg, inicio, fin, umbral_cs) if es_s2 else _landsat_coleccion(ee, reg, inicio, fin)
    n = col_idx.size().getInfo()
    if n == 0:
        raise RuntimeError(f"Sin escenas en {coleccion} para {inicio}..{fin}; no se puede caracterizar el combustible pre-incendio")
    escenas = _escenas_info(ee, col_idx, reg, es_s2)
    if compuesto == "mediana":
        comp = col_idx.median()
    elif compuesto == "promedio":
        comp = col_idx.mean()
    else:
        raise ValueError(compuesto)
    n_obs = col_idx.select("ndvi").count().rename("n_obs").toUint8()
    comp_i16 = comp.multiply(ESCALA_IDX).round().toInt16().unmask(NODATA)
    # remuestreo a la escala de salida por promedio (reduceResolution) cuando escala > resolución nativa
    if es_s2 and escala > 10:
        comp_i16 = comp.setDefaultProjection("EPSG:5345", None, 10).reduceResolution(ee.Reducer.mean(), maxPixels=64) \
            .multiply(ESCALA_IDX).round().toInt16().unmask(NODATA)
    # Reanudación: un raster ya escrito (guardar_raster escribe el producto completo al final de todas las teselas) sin
    # procedencia proviene de una corrida interrumpida con los mismos parámetros; se conserva y se descarga sólo lo que falta.
    pendientes = {"ndvi": (comp_i16.select("ndvi"), "int16", NODATA), "ndmi": (comp_i16.select("ndmi"), "int16", NODATA),
                  "n_obs": (n_obs.unmask(0), "uint8", 0)}
    for k, (img, dtype, nd) in pendientes.items():
        if out[k].exists() and not producto_vigente(out[k], params):
            log.warning("índices %s: se reutiliza %s de una corrida interrumpida (sin procedencia previa)", evento["id"], out[k].name)
            continue
        descargar_imagen_a_grilla(img, grilla_idx, out[k], dtype, nd, escala)
    meta = {"evento": evento["id"], "coleccion": coleccion, "ventana": [inicio, fin], "umbral_cs_cdf": umbral_cs,
            "compuesto": compuesto, "escala_m": escala, "n_escenas": n, "escenas": escenas,
            "formula": {"ndvi": "(NIR-Rojo)/(NIR+Rojo)", "ndmi": "(NIR-SWIR1)/(NIR+SWIR1)"},
            "codificacion": f"int16 x {ESCALA_IDX}, NoData {NODATA}", "generado_utc": ahora_utc(),
            "advertencia": "valores sin dato se conservan como NoData; n_obs indica el número de observaciones válidas"}
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    for k, p in out.items():
        escribir_procedencia(p, f"{coleccion} compuesto {compuesto} vía GEE", params, [], extra={"n_escenas": n})
    log.info("índices %s: %d escenas, salida %s", evento["id"], n, odir)
    return out | {"metadatos": meta_path}
