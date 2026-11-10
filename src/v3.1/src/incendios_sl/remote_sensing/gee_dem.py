"""Exportación del DEM Copernicus GLO-30 (GEE) recortado a una grilla en EPSG:5345."""
from __future__ import annotations

import logging
from pathlib import Path

from ..grilla import Grilla
from ..procedencia import escribir_procedencia, producto_vigente
from .gee_comun import ee_init, region_ee, descargar_imagen_a_grilla

log = logging.getLogger(__name__)
COLECCION = "COPERNICUS/DEM/GLO30_2024_1"


def exportar_copernicus_glo30(grilla: Grilla, out: Path) -> Path:
    params = {"coleccion": COLECCION, "grilla": grilla.como_dict(), "remuestreo": "bilinear (GEE) a 30 m"}
    if producto_vigente(out, params):
        return out
    ee = ee_init()
    col = ee.ImageCollection(COLECCION).filterBounds(region_ee(grilla)).select("DEM")
    # el mosaico pierde la proyección por defecto; sin fijarla, resample() degenera en un valor constante (verificado)
    dem = col.mosaic().setDefaultProjection(col.first().projection()).resample("bilinear")
    descargar_imagen_a_grilla(dem, grilla, out, dtype="float32", nodata=-9999.0)
    escribir_procedencia(out, f"{COLECCION} vía GEE getDownloadURL", params, [],
                         extra={"nota": "mosaico de teselas GLO-30 2024_1; alturas sobre el elipsoide EGM2008 (ortométricas)"})
    log.info("DEM Copernicus exportado: %s", out)
    return out
