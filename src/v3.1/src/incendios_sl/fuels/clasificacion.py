"""Mapa de clases de combustible v1 a partir de cobertura MapBiomas + NDVI/NDMI pre-incendio.

Reglas explícitas (diseño §7.2); los umbrales son HIPÓTESIS iniciales, configurables en escenarios/v3.1/modelos/modelo_v1.yaml.
Se conserva una máscara de validez de los índices: donde no hay NDVI/NDMI válido la clase se asigna solo por
cobertura y se marca en la banda `calidad` (0 = sin índices, 1 = con índices).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
from rasterio.enums import Resampling

from .. import config as cfgmod
from ..grilla import Grilla, alinear_raster, guardar_raster, leer_raster
from ..procedencia import escribir_procedencia, producto_vigente
from .tabla import CLASES_V1, cargar_tabla

log = logging.getLogger(__name__)

UMBRALES_DEFECTO = {
    "ndvi_cultivo_suelo_desnudo": 0.15,   # cultivo/pastura con NDVI < umbral -> no combustible (suelo/rastrojo escaso)
    "ndvi_pastizal_curado": 0.35,         # pastizal con NDVI < umbral -> curado alto (fracción herbácea seca)
    "curado_alto": 0.80, "curado_bajo": 0.50,
}


def indices_a_grilla(path_idx: Path, g: Grilla) -> tuple[np.ndarray, np.ndarray]:
    """Índice int16×10000 (20 m) -> float32 a la grilla por promedio; máscara de validez."""
    arr = alinear_raster(path_idx, g, Resampling.average, dtype="float32", nodata_dst=np.nan)
    with_nd = np.isfinite(arr)
    return (arr / 10000.0).astype(np.float32), with_nd


def clasificar(cobertura: np.ndarray, ndvi: np.ndarray | None, valido: np.ndarray | None, umbrales: dict[str, float] | None = None
               ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Devuelve (clase uint8, curado float32 [0-1], calidad uint8)."""
    u = UMBRALES_DEFECTO | (umbrales or {})
    clase = np.zeros(cobertura.shape, np.uint8)
    for c in CLASES_V1:
        for cod in c["coberturas"]:
            clase[cobertura == cod] = c["clase"]
    curado = np.full(cobertura.shape, 0.5, np.float32)     # fracción de herbáceo curado (muerto), HIPÓTESIS base 50 %
    calidad = np.zeros(cobertura.shape, np.uint8)
    if ndvi is not None and valido is not None:
        ok = valido & np.isfinite(ndvi)
        calidad[ok] = 1
        # cultivos/pasturas con NDVI muy bajo: suelo desnudo o rastrojo escaso -> no combustible
        clase[(clase == 2) & ok & (ndvi < u["ndvi_cultivo_suelo_desnudo"])] = 0
        herb = np.isin(clase, [1, 2, 3, 5])
        curado[herb & ok & (ndvi < u["ndvi_pastizal_curado"])] = u["curado_alto"]
        curado[herb & ok & (ndvi >= u["ndvi_pastizal_curado"])] = u["curado_bajo"]
    return clase, curado, calidad


def generar_mapa_combustibles(dom: dict[str, Any], ev: dict[str, Any], g: Grilla, path_cobertura: Path,
                              path_ndvi: Path | None, path_ndmi: Path | None, umbrales: dict[str, float] | None = None) -> dict[str, Path]:
    edir = cfgmod.dir_derivados("combustibles", ev["id"])
    out = {"clase": edir / f"combustible_clase_{ev['id']}.tif", "curado": edir / f"combustible_curado_{ev['id']}.tif",
           "calidad": edir / f"combustible_calidad_{ev['id']}.tif", "ndvi30": edir / f"ndvi_30m_{ev['id']}.tif",
           "ndmi30": edir / f"ndmi_30m_{ev['id']}.tif", "resumen": edir / f"resumen_combustibles_{ev['id']}.json"}
    params = {"grilla": g.como_dict(), "cobertura": str(path_cobertura), "ndvi": str(path_ndvi), "ndmi": str(path_ndmi),
              "umbrales": UMBRALES_DEFECTO | (umbrales or {}), "version_clases": "v1"}
    if producto_vigente(out["clase"], params):
        return out
    cob, _, _ = leer_raster(path_cobertura)
    ndvi = ndmi = val = None
    if path_ndvi:
        ndvi, val = indices_a_grilla(path_ndvi, g)
        guardar_raster(out["ndvi30"], np.where(val, ndvi, -9999).astype(np.float32), g, nodata=-9999.0)
    if path_ndmi:
        ndmi, val2 = indices_a_grilla(path_ndmi, g)
        guardar_raster(out["ndmi30"], np.where(val2, ndmi, -9999).astype(np.float32), g, nodata=-9999.0)
    clase, curado, calidad = clasificar(cob, ndvi, val, umbrales)
    guardar_raster(out["clase"], clase, g, nodata=None)
    guardar_raster(out["curado"], curado, g, nodata=None)
    guardar_raster(out["calidad"], calidad, g, nodata=None)
    tabla = cargar_tabla().set_index("clase")
    u, c = np.unique(clase, return_counts=True)
    resumen = {"evento": ev["id"], "clases": [{"clase": int(k), "nombre": tabla.loc[int(k), "nombre"], "celdas": int(v),
                                               "ha": float(v * g.area_celda_m2 / 1e4), "pct": float(100 * v / clase.size)} for k, v in zip(u, c)],
               "celdas_con_indices_validos": int(calidad.sum()), "pct_con_indices": float(100 * calidad.mean()),
               "umbrales": params["umbrales"],
               "nota": "clasificación provisional por reglas; no validada en campo; curado = HIPÓTESIS"}
    with open(out["resumen"], "w", encoding="utf-8") as f:
        json.dump(resumen, f, indent=2, ensure_ascii=False)
    for k in ("clase", "curado", "calidad"):
        escribir_procedencia(out[k], "clasificación v1 cobertura + NDVI", params, [path_cobertura] + ([path_ndvi] if path_ndvi else []))
    log.info("mapa de combustibles %s: %s", ev["id"], {r['nombre']: round(r['pct'], 1) for r in resumen["clases"]})
    return out
