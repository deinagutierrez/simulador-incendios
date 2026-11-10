"""Arribo del combate terrestre desde los cuarteles por la red vial y régimen territorial del despacho (v3.0 docs/13 §6).

Lee el producto de v3.0 `datos/inputSimulacion/infraestructura/arribo_<dominio>.npz` (generado por
src/v3.0/scripts/preparar_arribo.py: costo acumulado mínimo MCP, 8 vecinos, sobre una superficie de fricción de 100 m;
`tiempo_h` (n_cuarteles, nfil, ncol) en horas, inf = más de `max_h`; `ids`, `nombres`, `grilla`). Aquí solo se consulta:

- `tiempo_arribo`: primer arribo a cualquiera de los puntos = mínimo sobre puntos y cuarteles permitidos (port de
  v3.0 `data/arribo.tiempo_arribo`).
- `inicio_combate_vial`: retardo del ataque inicial = t_aviso + t_despacho + viaje (port de v3.0
  `entradas.inicio_combate_vial`). Igual que en v3.0, `cuarteles_id: []` de la ficha equivale a "todos".
- `llegadas_l03`: las N llegadas más rápidas (cuarteles distintos) + demora fija, para la supresión L03 de V.4
  (protocolo v1.3 §2.4.1: 3 cuarteles, 30 min de demora de despacho).
- `departamento_de` y `region_despacho`: régimen territorial de la tasa SNMF según el departamento de la ignición
  (v3.0 `entradas.region_despacho`, coeficientes del ajuste log-log de 186 eventos, docs/13 §2.1).
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from . import config as cfgmod

log = logging.getLogger(__name__)

# régimen territorial (docs/13 §2.1; v3.0 modelo_v2.yaml contencion.despacho.regiones): tasa = κ·a·A^b
REGIONES_SNMF: dict[str, dict[str, Any]] = {
    "periurbano": {"a": 25.5, "b": 0.41, "departamentos": ["JUAN MARTIN DE PUEYRREDON", "GENERAL PEDERNERA"]},
    "llanura_sur": {"a": 29.6, "b": 0.38, "departamentos": ["GOBERNADOR DUPUY"]},
    "serrano": {"a": 17.3, "b": 0.36},
}
REGION_DEFECTO = "serrano"


def ruta_arribo(id_dominio: str) -> Path:
    return cfgmod.dir_entradas() / "infraestructura" / f"arribo_{id_dominio}.npz"


@lru_cache(maxsize=2)
def _cargar(path: str) -> tuple[np.ndarray, np.ndarray, list[str], dict[str, Any]]:
    z = np.load(path, allow_pickle=False)
    return z["tiempo_h"], z["ids"], json.loads(str(z["nombres"])), json.loads(str(z["grilla"]))


def cargar_arribo(path: Path) -> tuple[np.ndarray, np.ndarray, list[str], dict[str, Any]]:
    """(tiempo_h [n, nfil, ncol] en h, ids de bomberos_san_luis.geojson, nombres, grilla {crs, res, xmin, ymax, ncol, nfil})."""
    return _cargar(str(Path(path).resolve()))


def _celdas(g: dict[str, Any], puntos_lonlat: list[tuple[float, float]]) -> list[tuple[int, int]]:
    from pyproj import Transformer
    tr = Transformer.from_crs("EPSG:4326", g["crs"], always_xy=True)
    out = []
    for lon, lat in puntos_lonlat:
        x, y = tr.transform(float(lon), float(lat))
        f = int(np.floor((g["ymax"] - y) / g["res"])); c = int(np.floor((x - g["xmin"]) / g["res"]))
        out.append((int(np.clip(f, 0, g["nfil"] - 1)), int(np.clip(c, 0, g["ncol"] - 1))))
    return out


def tiempos_por_cuartel(path: Path, puntos_lonlat: list[tuple[float, float]]) -> np.ndarray:
    """Tiempo de viaje (h) de cada cuartel al más cercano de los puntos: mínimo sobre los puntos (inf = fuera de alcance)."""
    T, _, _, g = cargar_arribo(path)
    return np.min(np.stack([T[:, f, c] for f, c in _celdas(g, puntos_lonlat)]), axis=0).astype(np.float64)


def tiempo_arribo(path: Path, puntos_lonlat: list[tuple[float, float]], ids_permitidos: list[int] | None = None) -> dict[str, Any]:
    """Primer arribo: mínimo sobre puntos y cuarteles (los `ids_permitidos`, si alguno está en el producto; si no, todos)."""
    _, ids, nombres, _ = cargar_arribo(path)
    t = tiempos_por_cuartel(path, puntos_lonlat)
    sel = np.isin(ids, ids_permitidos) if ids_permitidos else np.ones(len(ids), bool)
    if not sel.any():
        log.warning("arribo: ninguno de los cuarteles %s está en el producto; se usan todos", ids_permitidos)
        sel[:] = True
    t = np.where(sel, t, np.inf)
    k = int(np.argmin(t))
    ok = bool(np.isfinite(t[k]))
    return {"t_viaje_h": float(t[k]), "cuartel_id": int(ids[k]) if ok else None, "cuartel": nombres[k] if ok else None,
            "restringido_a_ficha": bool(ids_permitidos) and bool(np.isin(ids, ids_permitidos).any())}


def inicio_combate_vial(id_dominio: str, puntos_lonlat: list[tuple[float, float]], cuarteles_id: list[int] | None = None,
                        t_aviso_h: float = 0.5, t_despacho_h: float = 0.25) -> dict[str, Any] | None:
    """Retardo del ataque inicial = aviso + despacho + viaje desde el cuartel más cercano a la ignición (entre los de la
    ficha, si hay). None si falta el producto de arribo o la ignición queda fuera del alcance (se usa `retardo_h`)."""
    p = ruta_arribo(id_dominio)
    if not p.exists():
        log.warning("retardo vial: falta %s (src/v3.0/scripts/preparar_arribo.py); se usa retardo_h", p)
        return None
    r = tiempo_arribo(p, puntos_lonlat, list(cuarteles_id) if cuarteles_id else None)
    if not np.isfinite(r["t_viaje_h"]):
        log.warning("retardo vial: ignición fuera del alcance de los cuarteles; se usa retardo_h")
        return None
    r["retardo_h"] = float(t_aviso_h) + float(t_despacho_h) + r["t_viaje_h"]
    log.info("retardo vial: %.2f h (viaje %.2f h desde %s)", r["retardo_h"], r["t_viaje_h"], r["cuartel"])
    return r


def llegadas_l03(id_dominio: str, puntos_lonlat: list[tuple[float, float]], n: int = 3, demora_min: float = 30.0) -> list[dict[str, Any]]:
    """Las `n` llegadas más rápidas (una por cuartel) en minutos desde la ignición: demora de despacho + viaje vial.
    Lista vacía si falta el producto o ningún cuartel llega en `max_h`."""
    p = ruta_arribo(id_dominio)
    if not p.exists():
        log.warning("L03: falta %s; sin dotaciones", p)
        return []
    _, ids, nombres, _ = cargar_arribo(p)
    t = tiempos_por_cuartel(p, puntos_lonlat)
    orden = [int(k) for k in np.argsort(t, kind="stable") if np.isfinite(t[k])][: int(n)]
    return [{"cuartel_id": int(ids[k]), "cuartel": nombres[k], "viaje_min": round(float(t[k]) * 60.0, 1),
             "llegada_min": round(float(demora_min) + float(t[k]) * 60.0, 1)} for k in orden]


@lru_cache(maxsize=4)
def _departamentos(path: str):
    import geopandas as gpd
    return gpd.read_file(path).to_crs(4326)


def departamento_de(lon: float, lat: float, ruta_departamentos: Path | None = None) -> str | None:
    """Departamento (columna `departamento`, mayúsculas) que contiene el punto; None si no hay capa o cae afuera."""
    from shapely.geometry import Point
    p = Path(ruta_departamentos) if ruta_departamentos else cfgmod.dir_crudos() / "departamentos_san_luis_ign_conae.geojson"
    if not p.exists():
        log.warning("despacho: falta %s; se usa la región por defecto", p)
        return None
    dep = _departamentos(str(p.resolve()))
    hit = dep[dep.contains(Point(float(lon), float(lat)))]
    return str(hit["departamento"].iloc[0]) if len(hit) else None


def region_despacho(departamento: str | None, regiones: dict[str, Any] | None = None, region_defecto: str = REGION_DEFECTO) -> str:
    """Régimen territorial de la respuesta según el departamento de la ignición (v3.0 entradas.region_despacho)."""
    d = (departamento or "").upper()
    for nombre, r in (regiones if regiones is not None else REGIONES_SNMF).items():
        if d and d in [x.upper() for x in (r or {}).get("departamentos", [])]:
            return nombre
    return str(region_defecto)
