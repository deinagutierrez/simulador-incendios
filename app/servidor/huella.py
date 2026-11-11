"""Huella del fuego como imagen para el mapa.

El proceso motor deja `t_llegada_parcial.npy` (minutos desde el inicio, NaN donde el fuego no llegó) en la grilla del
dominio, EPSG:5345. Un mapa web estira las imágenes en la proyección Web Mercator (EPSG:3857), así que acá se pasa la
matriz a esa proyección y se pinta: del amarillo (lo primero que ardió) al rojo oscuro (lo último), transparente lo demás.
"""
from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

import numpy as np

HUELLA = "t_llegada_parcial.npy"
# rampa: fracción del tiempo transcurrido → color
RAMPA = np.array([[0.0, 255, 237, 160], [0.35, 254, 178, 76], [0.65, 240, 59, 32], [1.0, 128, 0, 38]], dtype="float64")


@lru_cache(maxsize=16)
def _destino(crs: str, xmin: float, ymax: float, res: float, filas: int, cols: int):
    """Transformación de la grilla del motor a Web Mercator y recuadro de la imagen en grados."""
    from rasterio.transform import array_bounds, from_origin
    from rasterio.warp import calculate_default_transform, transform_bounds
    origen = from_origin(xmin, ymax, res, res)
    izq, abajo, der, arriba = array_bounds(filas, cols, origen)
    destino, ancho, alto = calculate_default_transform(crs, "EPSG:3857", cols, filas, izq, abajo, der, arriba)
    oeste, sur, este, norte = transform_bounds("EPSG:3857", "EPSG:4326", *array_bounds(alto, ancho, destino))
    return origen, destino, int(ancho), int(alto), [[sur, oeste], [norte, este]]


def limites(grilla: dict) -> list[list[float]]:
    """[[sur, oeste], [norte, este]] de la imagen de la huella, en grados."""
    return _destino(str(grilla["crs"]), float(grilla["xmin"]), float(grilla["ymax"]), float(grilla["res"]),
                    int(grilla["filas"]), int(grilla["cols"]))[4]


def png(carpeta: Path, grilla: dict, hora: float | None = None) -> bytes | None:
    """PNG de la huella hasta la hora simulada `hora` (o completa). None si todavía no hay huella."""
    ruta = Path(carpeta) / HUELLA
    if not ruta.exists():
        return None
    from PIL import Image
    from rasterio.warp import Resampling, reproject
    t = np.load(ruta).astype("float32")
    if t.shape != (int(grilla["filas"]), int(grilla["cols"])):
        return None
    if hora is not None:
        t = np.where(t <= float(hora) * 60.0, t, np.nan)
    origen, destino, ancho, alto, _ = _destino(str(grilla["crs"]), float(grilla["xmin"]), float(grilla["ymax"]),
                                              float(grilla["res"]), int(grilla["filas"]), int(grilla["cols"]))
    salida = np.full((alto, ancho), np.nan, dtype="float32")
    reproject(t, salida, src_transform=origen, src_crs=str(grilla["crs"]), src_nodata=np.nan,
              dst_transform=destino, dst_crs="EPSG:3857", dst_nodata=np.nan, resampling=Resampling.nearest)
    quemado = np.isfinite(salida)
    rgba = np.zeros((alto, ancho, 4), dtype="uint8")
    if quemado.any():
        tope = max(float(np.nanmax(salida)), 1.0)
        fraccion = np.clip(salida[quemado] / tope, 0.0, 1.0)
        for canal in range(3):
            rgba[..., canal][quemado] = np.interp(fraccion, RAMPA[:, 0], RAMPA[:, canal + 1]).astype("uint8")
        rgba[..., 3][quemado] = 200
    memoria = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(memoria, format="PNG", optimize=False)
    return memoria.getvalue()
