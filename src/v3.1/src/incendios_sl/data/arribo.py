"""Tiempo de arribo del primer recurso terrestre desde los cuarteles de bomberos por la red vial (docs/13 §6).

Superficie de fricción a 100 m sobre el dominio ampliado (por defecto 120 km, cubre los cuarteles que despachan a sus
incendios): cada celda toma la velocidad de la vía más rápida que la toca (`all_touched`) y, sin vía, la velocidad a campo
traviesa. El tiempo de viaje desde cada cuartel es el costo acumulado mínimo (MCP geométrico, 8 vecinos) con costo de
celda = res / velocidad. Velocidades por clase de vía: HIPÓTESIS (autobomba forestal / 4×4), en `modelo_v2.yaml`.

Producto: `datos/inputSimulacion/infraestructura/arribo_<dominio>.npz` con `tiempo_h` (n_cuarteles, nfil, ncol) float32 recortado
al dominio a 100 m (inf = más de `max_h`), `ids`, `nombres` y la grilla; y `tiempo_arribo_<dominio>.tif` (banda 1: tiempo
mínimo en h; banda 2: id del cuartel más cercano) para el mapa. Procedencia en el JSON adjunto.
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
from pyproj import Transformer

from .. import config as cfgmod
from ..grilla import Grilla, guardar_raster
from ..procedencia import escribir_procedencia, producto_vigente

log = logging.getLogger(__name__)

VELOCIDAD_KMH = {"autopista": 80.0, "ruta_pavimentado": 70.0, "ruta": 45.0, "camino": 35.0, "calle": 30.0, "servicio": 20.0,
                 "huella": 15.0, "vado": 15.0, "otro": 15.0, "senda": 4.0}


def _clave(clase: str, superficie: str) -> str:
    return "ruta_pavimentado" if clase == "ruta" and superficie == "pavimentado" else clase


def friccion_h(velocidad_kmh: np.ndarray, res_m: float) -> np.ndarray:
    """Horas para atravesar una celda en dirección ortogonal."""
    return (res_m / 1000.0 / np.maximum(velocidad_kmh, 1e-6)).astype(np.float64)


def tiempos_desde(costo: np.ndarray, origen: tuple[int, int], max_h: float) -> np.ndarray:
    """Costo acumulado mínimo (h) desde una celda, 8 vecinos con distancia geométrica; inf más allá de `max_h`."""
    from skimage.graph import MCP_Geometric
    mcp = MCP_Geometric(costo, fully_connected=True)
    acum, _ = mcp.find_costs([origen])     # sin corte por costo (`max_cumulative_cost` está obsoleto en skimage 0.26)
    acum = np.asarray(acum, np.float64)
    acum[~np.isfinite(acum) | (acum > max_h)] = np.inf
    return acum


def preparar_arribo(dom: dict[str, Any], velocidades: dict[str, float] | None = None, campo_traviesa_kmh: float = 3.0,
                    res_m: float = 100.0, margen_m: float = 120_000.0, max_h: float = 8.0) -> Path:
    vel = dict(VELOCIDAD_KMH | (velocidades or {}))
    comb = dom.get("combate") or {}
    p_cuart = cfgmod.ruta(comb.get("cuarteles", "bomberos_san_luis.geojson"))
    p_cam = cfgmod.ruta(dom["infraestructura"]["caminos"])
    gd = Grilla.desde_config(dom)
    # grilla de 100 m alineada al origen del dominio, que lo cubre, y su ampliación
    nd = (math.ceil((gd.xmax - gd.xmin) / res_m), math.ceil((gd.ymax - gd.ymin) / res_m))
    g100 = Grilla(gd.crs, res_m, gd.xmin, gd.ymax - nd[1] * res_m, gd.xmin + nd[0] * res_m, gd.ymax)
    ga = g100.ampliar(margen_m)
    out = cfgmod.dir_derivados("infraestructura") / f"arribo_{dom['id']}.npz"
    params = {"grilla": g100.como_dict(), "margen_m": margen_m, "velocidades_kmh": dict(sorted(vel.items())),
              "campo_traviesa_kmh": campo_traviesa_kmh, "max_h": max_h, "version": "1.0"}
    if producto_vigente(out, params):
        return out
    caja4326 = tuple(gpd.GeoSeries.from_xy([ga.xmin, ga.xmax], [ga.ymin, ga.ymax], crs=ga.crs).to_crs(4326).total_bounds)
    cam = gpd.read_file(p_cam, bbox=caja4326)
    cam = cam[~cam["dup_probable"].astype(bool) & (cam["clase"] != "ferrocarril")].to_crs(ga.crs)
    cam["v"] = [vel.get(_clave(str(c), str(s)), vel["otro"]) for c, s in zip(cam["clase"], cam["superficie"])]
    cam = cam.sort_values("v")                     # la vía más rápida se pinta última
    v = ga.rasterizar(zip(cam.geometry, cam["v"]), dtype="float32", fill=campo_traviesa_kmh, all_touched=True)
    costo = friccion_h(v, res_m)
    cu = gpd.read_file(p_cuart).to_crs(ga.crs)
    fil, col = ga.xy_a_rc(cu.geometry.x.to_numpy(), cu.geometry.y.to_numpy())
    dentro = ga.dentro(fil, col)
    r0, c0 = g100.ventana_en(ga)
    tiempos, ids, nombres = [], [], []
    for k in np.flatnonzero(dentro):
        acum = tiempos_desde(costo, (int(fil[k]), int(col[k])), max_h)
        tiempos.append(acum[r0:r0 + g100.nfil, c0:c0 + g100.ncol].astype(np.float32))
        ids.append(int(cu["id"].iloc[k])); nombres.append(str(cu["nombre"].iloc[k]))
    T = np.stack(tiempos)
    np.savez_compressed(out, tiempo_h=T, ids=np.array(ids, np.int32), nombres=json.dumps(nombres, ensure_ascii=False),
                        grilla=json.dumps(g100.como_dict()))
    tmin = T.min(axis=0)
    idmin = np.where(np.isfinite(tmin), np.array(ids)[T.argmin(axis=0)], 0).astype(np.float32)
    guardar_raster(out.with_name(f"tiempo_arribo_{dom['id']}.tif"), np.stack([np.where(np.isfinite(tmin), tmin, -1.0).astype(np.float32), idmin]),
                   g100, nodata=-1.0, descripciones=["tiempo de viaje mínimo (h)", "id del cuartel más cercano (bomberos_san_luis.geojson)"])
    escribir_procedencia(out, "cuarteles de bomberos (Ministerio de Seguridad SL + BOMBEROS.shp) y red vial integrada; MCP 8 vecinos",
                         params, [p_cuart, p_cam],
                         extra={"cuarteles": len(ids), "fuera_de_la_grilla_ampliada": int((~dentro).sum()),
                                "tiempo_mediano_dominio_h": float(np.nanmedian(np.where(np.isfinite(tmin), tmin, np.nan))),
                                "nota": "velocidades por clase de vía = HIPÓTESIS (docs/13 §6)"})
    log.info("arribo: %d cuarteles; tiempo mínimo mediano en el dominio %.2f h", len(ids), float(np.nanmedian(np.where(np.isfinite(tmin), tmin, np.nan))))
    return out


def cargar_arribo(path: Path) -> tuple[np.ndarray, np.ndarray, list[str], Grilla]:
    z = np.load(path, allow_pickle=False)
    gd = json.loads(str(z["grilla"]))
    g = Grilla(gd["crs"], gd["res"], gd["xmin"], gd["ymin"], gd["xmax"], gd["ymax"])
    return z["tiempo_h"], z["ids"], json.loads(str(z["nombres"])), g


def tiempo_arribo(path: Path, puntos_lonlat: list[tuple[float, float]], ids_permitidos: list[int] | None = None) -> dict[str, Any]:
    """Primer arribo a cualquiera de los puntos: mínimo sobre puntos y cuarteles (los `ids_permitidos`, si alguno está
    en el producto; si no, todos). Devuelve tiempo de viaje (h), id y nombre del cuartel."""
    T, ids, nombres, g = cargar_arribo(path)
    sel = np.isin(ids, ids_permitidos) if ids_permitidos else np.ones(len(ids), bool)
    if not sel.any():
        log.warning("arribo: ninguno de los cuarteles %s está en el producto; se usan todos", ids_permitidos)
        sel[:] = True
    tr = Transformer.from_crs("EPSG:4326", g.crs, always_xy=True)
    mejor = (np.inf, -1)
    for lon, lat in puntos_lonlat:
        x, y = tr.transform(lon, lat)
        f, c = g.xy_a_rc(x, y)
        f = int(np.clip(f, 0, g.nfil - 1)); c = int(np.clip(c, 0, g.ncol - 1))
        t = np.where(sel, T[:, f, c], np.inf)
        k = int(np.argmin(t))
        if t[k] < mejor[0]:
            mejor = (float(t[k]), k)
    t, k = mejor
    return {"t_viaje_h": t, "cuartel_id": int(ids[k]) if k >= 0 else None, "cuartel": nombres[k] if k >= 0 else None,
            "restringido_a_ficha": bool(ids_permitidos) and bool(np.isin(ids, ids_permitidos).any())}
