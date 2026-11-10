"""Utilidades comunes para Google Earth Engine: autenticación, región y descarga recortada por teselas.

La autenticación usa las credenciales ya configuradas en ~/.config/earthengine (refresh token);
no se leen ni escriben secretos en el código ni en los registros.
"""
from __future__ import annotations

import io
import logging
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import requests

from ..grilla import Grilla, guardar_raster

log = logging.getLogger(__name__)
_ee = None


def ee_init():
    """Inicializa Earth Engine una sola vez. Lanza una excepción clara si no hay credenciales.

    El proyecto de Google Cloud se toma, en este orden, de la variable EARTHENGINE_PROJECT, de `gee_project` en
    config/herramientas.yaml o del guardado con `earthengine set_project` (credenciales en ~/.config/earthengine)."""
    global _ee
    if _ee is None:
        import os
        import ee
        from .. import config as cfgmod
        proyecto = os.environ.get("EARTHENGINE_PROJECT") or cfgmod.cargar_rutas_herramientas().get("gee_project")
        try:
            ee.Initialize(project=proyecto) if proyecto else ee.Initialize()
        except Exception as e:  # pragma: no cover - depende del entorno
            raise RuntimeError("No se pudo inicializar Earth Engine; ejecute `earthengine authenticate` y "
                               "`earthengine set_project <proyecto>` (o indique gee_project en config/herramientas.yaml).") from e
        _ee = ee
    return _ee


def region_ee(grilla: Grilla):
    ee = ee_init()
    return ee.Geometry.Rectangle(list(grilla.bounds), proj=grilla.crs, geodesic=False)


def descargar_imagen_a_grilla(img, grilla: Grilla, out: Path, dtype: str, nodata, escala: float | None = None,
                              max_px_por_tesela: int = 4_000_000, reintentos: int = 3, bandas: list[str] | None = None) -> Path:
    """Descarga `img` (ee.Image) recortada a la grilla, por teselas si supera el límite de getDownloadURL.

    La imagen debe estar lista en las unidades/dtype deseados (p. ej. int16 escalado). Se solicita en el
    CRS de la grilla con crs_transform alineado, por lo que el remuestreo lo hace GEE (vecino más cercano
    para la reproyección implícita; usar img.reproject/reduceResolution antes si se requiere otro método)."""
    ee = ee_init()
    escala = escala or grilla.res
    nb = len(bandas) if bandas else 1
    ncol = int(round((grilla.xmax - grilla.xmin) / escala))
    nfil = int(round((grilla.ymax - grilla.ymin) / escala))
    out_arr = np.full((nb, nfil, ncol), nodata, dtype=dtype)
    # teselado
    n_tes = max(1, math.ceil(nfil * ncol * nb / max_px_por_tesela))
    k = math.ceil(math.sqrt(n_tes))
    paso_f = math.ceil(nfil / k); paso_c = math.ceil(ncol / k)
    for fi in range(0, nfil, paso_f):
        for ci in range(0, ncol, paso_c):
            nf = min(paso_f, nfil - fi); nc = min(paso_c, ncol - ci)
            x0 = grilla.xmin + ci * escala; y1 = grilla.ymax - fi * escala
            reg = ee.Geometry.Rectangle([x0, y1 - nf * escala, x0 + nc * escala, y1], proj=grilla.crs, geodesic=False)
            params = {"region": reg, "crs": grilla.crs, "crs_transform": [escala, 0, x0, 0, -escala, y1], "format": "GEO_TIFF"}
            if bandas:
                params["bands"] = bandas
            for intento in range(reintentos):
                try:
                    url = img.getDownloadURL(params)
                    r = requests.get(url, timeout=900)
                    r.raise_for_status()
                    with rasterio.open(io.BytesIO(r.content)) as ds:
                        a = ds.read()
                        nd_src = ds.nodata
                    if nd_src is not None:
                        a = np.where(a == nd_src, nodata, a)
                    if np.issubdtype(a.dtype, np.floating):
                        a = np.where(np.isnan(a), nodata, a)
                    out_arr[:, fi:fi + a.shape[1], ci:ci + a.shape[2]] = a.astype(dtype)
                    log.info("tesela (%d,%d) %dx%d descargada (%.1f MB)", fi, ci, nf, nc, len(r.content) / 1e6)
                    break
                except Exception as e:  # pragma: no cover
                    log.warning("intento %d fallido en tesela (%d,%d): %s", intento + 1, fi, ci, str(e)[:200])
                    time.sleep(5 * (intento + 1))
            else:
                raise RuntimeError(f"descarga GEE fallida tras {reintentos} intentos")
    g_out = Grilla(grilla.crs, escala, grilla.xmin, grilla.ymax - nfil * escala, grilla.xmin + ncol * escala, grilla.ymax)
    guardar_raster(out, out_arr if nb > 1 else out_arr[0], g_out, nodata=nodata, descripciones=bandas)
    return out
