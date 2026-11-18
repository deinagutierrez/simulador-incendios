"""Campo de viento de una corrida, para dibujarlo con flechas en el mapa.

Cada proceso motor deja en `<corrida>/viento/` el viento que usó, muestreado cada ~1 km (`app/motores/control.py`,
`guardar_viento`): `malla.json` (CRS, primer punto, separación, forma y qué campo es) y `hNNNN.npy` por hora, con las
componentes u (este) y v (norte) hacia donde va el viento, en km/h. Cada motor guarda el suyo:

- v3.1: el campo de WindNinja escalado con la velocidad y la dirección de la hora (varían en el espacio con el relieve); se
  guarda al terminar cada hora el viento fijo que rigió en ella (`momento: intervalo`), en una malla corrida medio paso
  respecto de la de v4.0 para que las flechas de los dos motores no se encimen;
- v4.0: el viento uniforme de la hora con la velocidad ajustada por el factor topográfico (la dirección es una sola), en la
  hora en punto (`momento: instante`; entre horas el motor lo interpola);
- el motor simulado: un viento de prueba que no mueve el fuego.

El servidor no carga ningún motor: solo lee esos archivos y los pasa a grados.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import numpy as np

CARPETA = "viento"
_HORA = re.compile(r"^h(\d{4})\.npy$")


@lru_cache(maxsize=4)
def _a_grados(crs: str):
    from pyproj import Transformer
    return Transformer.from_crs(crs, "EPSG:4326", always_xy=True)


def horas(carpeta: Path) -> list[int]:
    """Horas con viento guardado, en orden."""
    d = Path(carpeta) / CARPETA
    if not d.is_dir():
        return []
    return sorted(int(m.group(1)) for p in d.iterdir() if (m := _HORA.match(p.name)))


def flechas(carpeta: Path, hora: float | None = None) -> dict | None:
    """Flechas del viento para la hora `hora` (la última guardada que no la pase; sin `hora`, la última). None si la
    corrida no tiene viento guardado (motor sin viento o corrida anterior a esta función)."""
    disponibles = horas(carpeta)
    if not disponibles:
        return None
    d = Path(carpeta) / CARPETA
    try:
        malla = json.loads((d / "malla.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if hora is None:
        k = disponibles[-1]
    else:
        previas = [h for h in disponibles if h <= hora + 1e-9]
        k = previas[-1] if previas else disponibles[0]
    try:
        uv = np.load(d / f"h{k:04d}.npy").astype("float64")
    except (OSError, ValueError):
        return None
    u, v = uv[0], uv[1]
    ny, nx = u.shape
    paso = float(malla["paso_m"])
    xs = float(malla["x0"]) + np.arange(nx) * paso
    ys = float(malla["y0"]) - np.arange(ny) * paso
    X, Y = np.meshgrid(xs, ys)
    lon, lat = _a_grados(str(malla["crs"])).transform(X, Y)
    vel = np.hypot(u, v)
    desde = (np.degrees(np.arctan2(-u, -v)) + 360.0) % 360.0
    ok = np.isfinite(vel)
    F, C = np.indices(u.shape)
    # cada flecha: [lat, lon, velocidad km/h, de dónde viene (grados), fila, columna de la malla] (la fila y la columna
    # sirven para ralear las flechas al alejar el mapa)
    filas = [[round(float(a), 5), round(float(o), 5), round(float(s), 1), int(round(float(g))) % 360, int(i), int(j)]
             for a, o, s, g, i, j, b in zip(lat.ravel(), lon.ravel(), vel.ravel(), desde.ravel(), F.ravel(), C.ravel(), ok.ravel())
             if b]
    # resumen: velocidad media escalar y dirección media vectorial (como el promedio del dominio de v3.1)
    um, vm = float(np.nanmean(u)), float(np.nanmean(v))
    return {"hora": k, "horas": disponibles, "campo": malla.get("campo", ""), "momento": malla.get("momento", "instante"),
            "paso_m": paso, "filas": ny, "columnas": nx,
            "vel_media_kmh": round(float(np.nanmean(vel)), 1), "vel_max_kmh": round(float(np.nanmax(vel)), 1),
            "dir_media": int(round((np.degrees(np.arctan2(-um, -vm)) + 360.0) % 360.0)) % 360,
            "flechas": filas}
