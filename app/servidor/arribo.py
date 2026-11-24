"""Tiempo de llegada de los bomberos a un punto, por la red vial, desde cada cuartel (para el despacho de dotaciones).

Lee el producto que ya existe (`datos/inputSimulacion/infraestructura/arribo_<dominio>.npz`, de v3.x `data/arribo.py`,
docs/v4.0/13 §6): el tiempo de viaje en horas desde 39 cuarteles a cada celda de 100 m del dominio. No carga ningún motor.

El retardo del primer ataque de docs/v4.0/13 es aviso (0,5 h) + alistamiento (0,25 h) + viaje. Acá se devuelven las tres
partes por separado: antes de iniciar cuentan las tres (el fuego empieza en la hora 0 y hay que enterarse); en una pausa el
despacho se decide en ese momento, así que cuentan el alistamiento y el viaje.
"""
from __future__ import annotations

import json
from functools import lru_cache

import numpy as np

from . import datos

AVISO_MIN = 30
ALISTAMIENTO_MIN = 15
MAX_CUARTELES = 8


@lru_cache(maxsize=1)
def _producto():
    ruta = next(iter(sorted((datos.ENTRADAS / "infraestructura").glob("arribo_*.npz"))), None)
    if ruta is None:
        return None
    with np.load(ruta, allow_pickle=False) as d:
        return {"tiempo_h": d["tiempo_h"].astype("float32"), "grilla": json.loads(str(d["grilla"])),
                "nombres": [str(n) for n in json.loads(str(d["nombres"]))]}


def estimar(lon: float, lat: float, cuantos: int = 5) -> dict | None:
    """Los `cuantos` cuarteles que llegan antes al punto (grados): `{aviso_min, alistamiento_min, cuarteles: [{nombre,
    viaje_min}]}`, del más rápido al más lento. None si no está el producto o el punto cae fuera de su grilla."""
    p = _producto()
    if p is None:
        return None
    from pyproj import Transformer
    g = p["grilla"]
    x, y = Transformer.from_crs("EPSG:4326", g["crs"], always_xy=True).transform(float(lon), float(lat))
    col = int(np.floor((x - g["xmin"]) / g["res"]))
    fila = int(np.floor((g["ymax"] - y) / g["res"]))
    if not (0 <= fila < g["nfil"] and 0 <= col < g["ncol"]):
        return None
    t = p["tiempo_h"][:, fila, col]
    orden = [int(i) for i in np.argsort(t, kind="stable") if np.isfinite(t[i])][:max(1, min(int(cuantos), MAX_CUARTELES))]
    return {"aviso_min": AVISO_MIN, "alistamiento_min": ALISTAMIENTO_MIN,
            "cuarteles": [{"nombre": p["nombres"][i], "viaje_min": int(round(float(t[i]) * 60.0))} for i in orden]}
