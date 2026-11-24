"""Huella del fuego como imagen para el mapa.

El proceso motor deja `t_llegada_parcial.npy` (minutos desde el inicio, NaN donde el fuego no llegó) en la grilla del
dominio, EPSG:5345. Un mapa web estira las imágenes en la proyección Web Mercator (EPSG:3857), así que acá se pasa la
matriz a esa proyección y se pinta: del amarillo (lo primero que ardió) al rojo oscuro (lo último), transparente lo demás.

El proceso motor reemplaza la huella cada hora simulada mientras el servidor la puede estar leyendo. Una lectura que falla
(en Windows el archivo puede estar bloqueado un instante, o leerse a medias) se reintenta unas veces y, si sigue fallando,
se usa la última huella que se leyó bien de esa corrida; si no hay ninguna, se responde como si todavía no hubiera huella.
"""
from __future__ import annotations

import io
import threading
import time
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path

import numpy as np

HUELLA = "t_llegada_parcial.npy"
COMBATE = "combate_parcial.npy"    # (3, filas, cols): desde, hasta (NaN = en pie) y clase de cada celda de línea
# clase de la línea de combate → color (app/motores/combate.py): 1 línea de bomberos, 2 agua, 3 retardante
COLORES_LINEA = {1: (17, 17, 17), 2: (21, 101, 192), 3: (216, 27, 96)}
# rampa: fracción del tiempo transcurrido → color
RAMPA = np.array([[0.0, 255, 237, 160], [0.35, 254, 178, 76], [0.65, 240, 59, 32], [1.0, 128, 0, 38]], dtype="float64")
INTENTOS_LECTURA = 5
ESPERA_LECTURA_S = 0.03
MAX_GUARDADAS = 6                  # últimas huellas leídas bien (una por corrida), para cuando una lectura falla

_guardadas: OrderedDict[str, np.ndarray] = OrderedDict()
_cerrojo = threading.Lock()


def leer(ruta: Path, forma: tuple[int, int] | None = None) -> np.ndarray | None:
    """Tiempo de llegada (float32) de `ruta`, o None si no existe. Si la lectura falla (archivo bloqueado o a medio
    escribir, o con otra forma que `forma`), reintenta `INTENTOS_LECTURA` veces y después devuelve la última que se leyó bien
    de esa ruta (o None si no hubo ninguna). Nunca lanza por el archivo."""
    ruta = Path(ruta)
    clave = str(ruta.resolve())
    for i in range(INTENTOS_LECTURA):
        if not ruta.exists():
            return None
        try:
            t = np.load(ruta, allow_pickle=False).astype("float32")
            if t.ndim == 2 and (forma is None or t.shape == tuple(forma)):
                with _cerrojo:
                    _guardadas[clave] = t
                    _guardadas.move_to_end(clave)
                    while len(_guardadas) > MAX_GUARDADAS:
                        _guardadas.popitem(last=False)
                return t
        except (OSError, ValueError, EOFError):
            pass
        if i < INTENTOS_LECTURA - 1:
            time.sleep(ESPERA_LECTURA_S)
    with _cerrojo:
        return _guardadas.get(clave)


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


def png(carpeta: Path, grilla: dict, hora: float | None = None, color: tuple[int, int, int] | None = None) -> bytes | None:
    """PNG de la huella hasta la hora simulada `hora` (o completa). None si todavía no hay huella.
    Sin `color` se pinta con la rampa del tiempo de llegada; con `color`, de un solo color (para comparar dos motores)."""
    t = leer(Path(carpeta) / HUELLA, (int(grilla["filas"]), int(grilla["cols"])))
    if t is None:
        return None
    from PIL import Image
    from rasterio.warp import Resampling, reproject
    if hora is not None:
        t = np.where(t <= float(hora) * 60.0, t, np.nan)
    origen, destino, ancho, alto, _ = _destino(str(grilla["crs"]), float(grilla["xmin"]), float(grilla["ymax"]),
                                              float(grilla["res"]), int(grilla["filas"]), int(grilla["cols"]))
    salida = np.full((alto, ancho), np.nan, dtype="float32")
    reproject(t, salida, src_transform=origen, src_crs=str(grilla["crs"]), src_nodata=np.nan,
              dst_transform=destino, dst_crs="EPSG:3857", dst_nodata=np.nan, resampling=Resampling.nearest)
    quemado = np.isfinite(salida)
    rgba = np.zeros((alto, ancho, 4), dtype="uint8")
    if quemado.any() and color is not None:
        rgba[quemado, :3] = color
        rgba[..., 3][quemado] = 120
    elif quemado.any():
        tope = max(float(np.nanmax(salida)), 1.0)
        fraccion = np.clip(salida[quemado] / tope, 0.0, 1.0)
        for canal in range(3):
            rgba[..., canal][quemado] = np.interp(fraccion, RAMPA[:, 0], RAMPA[:, canal + 1]).astype("uint8")
        rgba[..., 3][quemado] = 200
    memoria = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(memoria, format="PNG", optimize=False)
    return memoria.getvalue()


def leer_combate(ruta: Path, forma: tuple[int, int]) -> np.ndarray | None:
    """Las capas de la línea de combate (3, filas, cols), o None si no hay. Como `leer`: reintenta si el proceso motor la
    está reemplazando y, si sigue fallando, devuelve la última que se leyó bien."""
    ruta = Path(ruta)
    clave = str(ruta.resolve())
    for i in range(INTENTOS_LECTURA):
        if not ruta.exists():
            return None
        try:
            a = np.load(ruta, allow_pickle=False).astype("float32")
            if a.ndim == 3 and a.shape == (3,) + tuple(forma):
                with _cerrojo:
                    _guardadas[clave] = a
                    _guardadas.move_to_end(clave)
                    while len(_guardadas) > MAX_GUARDADAS:
                        _guardadas.popitem(last=False)
                return a
        except (OSError, ValueError, EOFError):
            pass
        if i < INTENTOS_LECTURA - 1:
            time.sleep(ESPERA_LECTURA_S)
    with _cerrojo:
        return _guardadas.get(clave)


def linea_en_pie(capas: np.ndarray, hora: float | None) -> np.ndarray:
    """Clase (uint8, 0 = nada) de las celdas que son línea en la hora `hora` (o las que siguen en pie, sin hora)."""
    desde, hasta, clase = capas
    if hora is None:
        en_pie = np.isfinite(desde) & np.isnan(hasta)
    else:
        t = float(hora) * 60.0
        en_pie = np.isfinite(desde) & (desde <= t + 1e-6) & (np.isnan(hasta) | (hasta > t + 1e-6))
    return np.where(en_pie, clase, 0).astype("uint8")


def linea_png(carpeta: Path, grilla: dict, hora: float | None = None) -> bytes | None:
    """PNG de la línea de combate en la hora `hora`: una celda de color por celda de línea (negro la de los bomberos).
    None si la corrida no tiene combate."""
    capas = leer_combate(Path(carpeta) / COMBATE, (int(grilla["filas"]), int(grilla["cols"])))
    if capas is None:
        return None
    from PIL import Image
    from rasterio.warp import Resampling, reproject
    clase = linea_en_pie(capas, hora)
    origen, destino, ancho, alto, _ = _destino(str(grilla["crs"]), float(grilla["xmin"]), float(grilla["ymax"]),
                                              float(grilla["res"]), int(grilla["filas"]), int(grilla["cols"]))
    salida = np.zeros((alto, ancho), dtype="uint8")
    reproject(clase, salida, src_transform=origen, src_crs=str(grilla["crs"]), src_nodata=0,
              dst_transform=destino, dst_crs="EPSG:3857", dst_nodata=0, resampling=Resampling.nearest)
    rgba = np.zeros((alto, ancho, 4), dtype="uint8")
    for valor, color in COLORES_LINEA.items():
        m = salida == valor
        if m.any():
            rgba[m, :3] = color
            rgba[..., 3][m] = 255
    memoria = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(memoria, format="PNG", optimize=False)
    return memoria.getvalue()


def _cargar(carpeta: Path, grilla: dict, hora: float | None) -> np.ndarray | None:
    t = leer(Path(carpeta) / HUELLA, (int(grilla["filas"]), int(grilla["cols"])))
    if t is None:
        return None
    return np.isfinite(t) & ((t <= float(hora) * 60.0) if hora is not None else True)


def perimetro(carpeta: Path, grilla: dict, hora: float | None = None) -> dict | None:
    """Contorno del área quemada hasta la hora `hora`, como GeoJSON en grados. None si todavía no hay huella."""
    quemado = _cargar(carpeta, grilla, hora)
    if quemado is None:
        return None
    from rasterio.features import shapes
    from rasterio.transform import from_origin
    from rasterio.warp import transform_geom
    origen = from_origin(float(grilla["xmin"]), float(grilla["ymax"]), float(grilla["res"]), float(grilla["res"]))
    celdas = int(quemado.sum())
    figuras = []
    if celdas:
        for geometria, valor in shapes(quemado.astype("uint8"), mask=quemado, transform=origen):
            if valor == 1:
                figuras.append(transform_geom(str(grilla["crs"]), "EPSG:4326", geometria, precision=6))
    ha = celdas * float(grilla["res"]) ** 2 / 1e4
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"hora": hora, "ha": round(ha, 2), "celdas": celdas},
         "geometry": {"type": "MultiPolygon", "coordinates": [f["coordinates"] for f in figuras]}}]}


def comparar(carpeta_a: Path, carpeta_b: Path, grilla_a: dict, grilla_b: dict, hora: float | None = None) -> dict | None:
    """Coincidencia entre dos huellas hasta la hora `hora`: superficie de cada una, de la parte común y de la envolvente,
    y el cociente entre esas dos (IoU). None si falta alguna huella o las grillas no coinciden."""
    misma_grilla = str(grilla_a["crs"]) == str(grilla_b["crs"]) and all(
        float(grilla_a[k]) == float(grilla_b[k]) for k in ("xmin", "ymax", "res", "filas", "cols"))
    if not misma_grilla:
        return None
    a, b = _cargar(carpeta_a, grilla_a, hora), _cargar(carpeta_b, grilla_b, hora)
    if a is None or b is None:
        return None
    ha = float(grilla_a["res"]) ** 2 / 1e4
    comun, union = int((a & b).sum()), int((a | b).sum())
    return {"hora": hora, "ha_a": round(int(a.sum()) * ha, 2), "ha_b": round(int(b.sum()) * ha, 2),
            "ha_comun": round(comun * ha, 2), "ha_envolvente": round(union * ha, 2),
            "iou": round(comun / union, 4) if union else None}
