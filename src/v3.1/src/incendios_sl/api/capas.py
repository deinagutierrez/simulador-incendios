"""Capas para la interfaz web: rasters reproyectados a Web Mercator (EPSG:3857) como PNG con transparencia,
vectores simplificados en GeoJSON (WGS84) y flechas de viento. Los resultados originales de 30 m no se modifican;
las superposiciones son representaciones derivadas con caché en memoria y en datos/inputSimulacion/web/.
"""
from __future__ import annotations

import io
import json
import logging
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.warp import calculate_default_transform, reproject, transform_bounds

from .. import config as cfgmod
from ..grilla import Grilla, leer_raster

log = logging.getLogger(__name__)
_lock = threading.Lock()
_cache: dict[str, Any] = {}

COLORES_CLASE = {0: (31, 119, 180), 1: (214, 188, 116), 2: (237, 222, 142), 3: (134, 176, 116), 4: (168, 147, 88), 5: (125, 201, 117), 6: (31, 141, 73), 7: (122, 108, 0)}
NOMBRES_CLASE = {0: "No combustible", 1: "Pastizal natural", 2: "Pastura / cultivo", 3: "Arbustal abierto", 4: "Arbustal cerrado", 5: "Bosque abierto", 6: "Bosque cerrado", 7: "Plantación"}


def a_mercator(arr: np.ndarray, g: Grilla, nodata, dtype: str, remuestreo: Resampling, res_m: float | None = None) -> tuple[np.ndarray, list[float]]:
    """Reproyecta un array de la grilla a EPSG:3857. Devuelve (array, bounds lon/lat [S, O, N, E] para Leaflet)."""
    tr, w, h = calculate_default_transform(g.crs, "EPSG:3857", g.ncol, g.nfil, *g.bounds, resolution=res_m)
    dst = np.full((h, w), nodata, dtype=dtype)
    reproject(arr.astype(dtype), dst, src_transform=g.transform, src_crs=g.crs, dst_transform=tr, dst_crs="EPSG:3857",
              src_nodata=nodata, dst_nodata=nodata, resampling=remuestreo)
    xmin, ymin = tr.c, tr.f + tr.e * h; xmax, ymax = tr.c + tr.a * w, tr.f
    lonmin, latmin, lonmax, latmax = transform_bounds("EPSG:3857", "EPSG:4326", xmin, ymin, xmax, ymax)
    return dst, [latmin, lonmin, latmax, lonmax]


def png_rgba(rgba: np.ndarray) -> bytes:
    buf = io.BytesIO(); Image.fromarray(rgba, "RGBA").save(buf, format="PNG", optimize=True); return buf.getvalue()


def _dominio(id_dominio: str):
    dom = cfgmod.cargar_dominio(id_dominio)
    return dom, Grilla.desde_config(dom)


# --------------------------------------------------------------------- capas estáticas
def capa_estatica(id_dominio: str, nombre: str, evento: str | None = None) -> tuple[bytes, list[float], dict[str, Any]]:
    """nombre: sombras | pendiente | combustible | ndvi | ndmi | mascara | cicatriz (requiere evento)."""
    clave = f"{id_dominio}:{nombre}:{evento}"
    with _lock:
        if clave in _cache:
            return _cache[clave]
    dom, g = _dominio(id_dominio)
    D = cfgmod.dir_entradas()
    leyenda: dict[str, Any] = {}
    if nombre == "sombras":
        dem, _, _ = leer_raster(D / "dem" / f"dem_{dom['dem']['fuente']}_{dom['id']}.tif")
        dy, dx = np.gradient(dem.astype(float), g.res); sl = np.arctan(np.hypot(dx, dy)); asp = np.arctan2(-dx, dy)
        hs = np.sin(np.radians(45)) * np.cos(sl) + np.cos(np.radians(45)) * np.sin(sl) * np.cos(np.radians(315) - asp)
        m, b = a_mercator(((hs + 1) / 2 * 255).astype(np.float32), g, -1.0, "float32", Resampling.bilinear)
        v = np.clip(m, 0, 255).astype(np.uint8); a = np.where(m < 0, 0, 160).astype(np.uint8)
        rgba = np.dstack([v, v, v, a]); leyenda = {"tipo": "sombreado", "fuente": "DEM Copernicus GLO-30"}
    elif nombre == "pendiente":
        p, _, _ = leer_raster(D / "dem" / f"pendiente_{dom['dem']['fuente']}_{dom['id']}.tif")
        m, b = a_mercator(p, g, -1.0, "float32", Resampling.bilinear)
        import matplotlib; cm = matplotlib.colormaps["magma"]
        rgba = (cm(np.clip(m / 30, 0, 1)) * 255).astype(np.uint8); rgba[..., 3] = np.where(m < 0, 0, 180)
        leyenda = {"tipo": "continua", "min": 0, "max": 30, "unidad": "°", "cmap": "magma"}
    elif nombre in ("ndvi", "ndmi"):
        if not evento:
            raise FileNotFoundError("ndvi/ndmi requieren evento")
        p, _, nd = leer_raster(D / "combustibles" / evento / f"{nombre}_30m_{evento}.tif")
        m, b = a_mercator(np.where(p == nd, -9999, p).astype(np.float32), g, -9999.0, "float32", Resampling.bilinear)
        import matplotlib; cm = matplotlib.colormaps["YlGn" if nombre == "ndvi" else "BrBG"]
        lo, hi = (0.0, 0.6) if nombre == "ndvi" else (-0.4, 0.2)
        rgba = (cm(np.clip((m - lo) / (hi - lo), 0, 1)) * 255).astype(np.uint8); rgba[..., 3] = np.where(m < -1, 0, 190)
        leyenda = {"tipo": "continua", "min": lo, "max": hi, "cmap": "YlGn" if nombre == "ndvi" else "BrBG"}
    elif nombre == "combustible":
        if not evento:
            raise FileNotFoundError("combustible requiere evento")
        c, _, _ = leer_raster(D / "combustibles" / evento / f"combustible_clase_{evento}.tif")
        m, b = a_mercator(c, g, 255, "uint8", Resampling.nearest)
        rgba = np.zeros(m.shape + (4,), np.uint8)
        for k, col in COLORES_CLASE.items():
            rgba[m == k] = (*col, 200)
        leyenda = {"tipo": "clases", "clases": [{"codigo": k, "nombre": NOMBRES_CLASE[k], "color": "#%02x%02x%02x" % c} for k, c in COLORES_CLASE.items()]}
    elif nombre == "mascara":
        mk, _, _ = leer_raster(D / "grilla" / f"mascara_dominio_{dom['id']}.tif")
        m, b = a_mercator(mk, g, 255, "uint8", Resampling.nearest)
        rgba = np.zeros(m.shape + (4,), np.uint8); rgba[m == 0] = (0, 0, 0, 90)
        leyenda = {"tipo": "mascara"}
    elif nombre == "cicatriz":
        if not evento:
            raise FileNotFoundError("cicatriz requiere evento")
        r, _, _ = leer_raster(D / "eventos" / evento / f"cicatriz_referencia_{evento}.tif")
        m, b = a_mercator(r, g, 255, "uint8", Resampling.nearest)
        rgba = np.zeros(m.shape + (4,), np.uint8); rgba[m == 1] = (0, 200, 255, 150)
        leyenda = {"tipo": "cicatriz", "color": "#00c8ff"}
    else:
        raise FileNotFoundError(f"capa desconocida {nombre}")
    out = (png_rgba(rgba), b, leyenda)
    with _lock:
        _cache[clave] = out
    return out


# --------------------------------------------------------------------- resultados de simulación
class ResultadoWeb:
    """Tiempo de llegada de una corrida reproyectado a 3857 (una vez) para producir estados por hora."""

    def __init__(self, run_dir: Path):
        self.dir = Path(run_dir)
        ta, g, nd = leer_raster(self.dir / "t_llegada_s.tif")
        ta = np.where(ta == nd, np.inf, ta).astype(np.float32)
        self.g = g
        self.ta, self.bounds = a_mercator(np.where(np.isfinite(ta), ta, -1.0).astype(np.float32), g, -2.0, "float32", Resampling.nearest)
        self.reg = json.load(open(self.dir / "registro.json", encoding="utf-8"))
        self.t_fin = float(self.reg.get("t_simulado_s", 0))
        self.bounds_incendio = self._bounds_incendio(np.isfinite(ta) & (ta >= 0), g)
        # v2: hora de contención por celda (perímetro asegurado por el combate)
        self.tc = None
        p_tc = self.dir / "t_contencion_s.tif"
        if p_tc.exists():
            tc, _, ndc = leer_raster(p_tc)
            tc = np.where(tc == ndc, -1.0, tc).astype(np.float32)
            self.tc, _ = a_mercator(tc, g, -2.0, "float32", Resampling.nearest)

    def _bounds_incendio(self, quemado: np.ndarray, g: Grilla, margen_m: float = 1000.0) -> list[list[float]] | None:
        """Extensión (lon/lat, formato Leaflet [[S, O], [N, E]]) de lo simulado más la cicatriz de referencia, con margen,
        para acercar el mapa al incendio en lugar de mostrar todo el dominio."""
        u = quemado.copy()
        ev = (self.reg.get("entradas") or {}).get("evento")
        p = cfgmod.dir_entradas() / "eventos" / str(ev) / f"cicatriz_referencia_{ev}.tif"
        if ev and p.exists():
            ref, gr, _ = leer_raster(p)
            if ref.shape == u.shape:
                u |= ref == 1
        if not u.any():
            return None
        filas = np.flatnonzero(u.any(axis=1)); cols = np.flatnonzero(u.any(axis=0))
        xmin = g.xmin + cols[0] * g.res - margen_m; xmax = g.xmin + (cols[-1] + 1) * g.res + margen_m
        ymax = g.ymax - filas[0] * g.res + margen_m; ymin = g.ymax - (filas[-1] + 1) * g.res - margen_m
        lonmin, latmin, lonmax, latmax = transform_bounds(g.crs, "EPSG:4326", xmin, ymin, xmax, ymax)
        return [[latmin, lonmin], [latmax, lonmax]]

    def png(self, t_s: float, ventana_s: float = 3600.0) -> bytes:
        q = (self.ta >= 0) & (self.ta <= t_s)
        reciente = q & (self.ta > t_s - ventana_s)
        rgba = np.zeros(self.ta.shape + (4,), np.uint8)
        rgba[q] = (217, 84, 30, 190); rgba[reciente] = (255, 213, 0, 230)
        if self.tc is not None:
            cont = (self.tc >= 0) & (self.tc <= t_s)
            rgba[cont] = (26, 61, 143, 230)
        return png_rgba(rgba)

    def perimetro_geojson(self, t_s: float, simplificar_m: float = 60.0) -> dict[str, Any]:
        from rasterio import features
        from shapely.geometry import shape, mapping
        from shapely.ops import unary_union, transform as shp_transform
        ta, g, nd = leer_raster(self.dir / "t_llegada_s.tif")
        q = ((ta != nd) & (ta >= 0) & (ta <= t_s)).astype(np.uint8)
        geoms = [shape(s) for s, v in features.shapes(q, mask=q == 1, transform=g.transform) if v == 1]
        if not geoms:
            return {"type": "FeatureCollection", "features": []}
        u = unary_union(geoms).simplify(simplificar_m)
        t = Transformer.from_crs(g.crs, "EPSG:4326", always_xy=True)
        u = shp_transform(lambda x, y, z=None: t.transform(x, y), u)
        return {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"t_s": t_s, "ha": float(q.sum() * g.area_celda_m2 / 1e4)}, "geometry": mapping(u)}]}


_resultados: dict[str, ResultadoWeb] = {}


def resultado(run_id: str) -> ResultadoWeb:
    with _lock:
        if run_id not in _resultados:
            _resultados[run_id] = ResultadoWeb(cfgmod.dir_resultados() / run_id)
        return _resultados[run_id]


# --------------------------------------------------------------------- vectores
@lru_cache(maxsize=32)
def vector_geojson(id_dominio: str, nombre: str, tolerancia_m: float = 30.0) -> dict[str, Any]:
    """caminos | viviendas | electricidad_mt | puntos_ignicion (por evento se sirven aparte)."""
    import geopandas as gpd
    dom, g = _dominio(id_dominio)
    p = cfgmod.dir_entradas() / "infraestructura" / f"{nombre}_{dom['id']}.gpkg"
    if not p.exists():
        raise FileNotFoundError(p)
    import pyogrio
    partes = []
    for layer in pyogrio.list_layers(p)[:, 0]:
        gdf = gpd.read_file(p, layer=layer)
        gdf["geometry"] = gdf.geometry.simplify(tolerancia_m)
        cols = [c for c in ("clase", "jerarquia", "superficie", "nombre", "tipo", "uso_residencial", "tension_kv") if c in gdf.columns]
        partes.append(gdf[cols + ["geometry"]].to_crs(4326))
    import pandas as pd
    todo = gpd.GeoDataFrame(pd.concat(partes, ignore_index=True), crs=4326)
    return json.loads(todo.to_json())


def flechas_viento(run_id: str, t_s: float, paso_m: float = 2000.0) -> dict[str, Any]:
    """Flechas de viento a 10 m para la hora de la corrida: muestreo del campo de WindNinja escalado (GeoJSON de puntos)."""
    import pandas as pd
    from ..simulation.entradas import cargar_entradas_evento
    r = resultado(run_id)
    ev_id = r.reg["entradas"]["evento"]; hip = int(r.reg["entradas"].get("hipotesis_ignicion", 0))
    clave = f"viento:{ev_id}"
    with _lock:
        ent = _cache.get(clave)
    if ent is None:
        ent, _, _, _ = cargar_entradas_evento(ev_id, hip)
        with _lock:
            _cache[clave] = ent
    t0 = pd.Timestamp(r.reg["entradas"]["t_inicio_utc"]); h = (t0 + pd.Timedelta(seconds=float(t_s))).floor("h")
    met = ent.meteo.copy(); met["time_utc"] = pd.to_datetime(met["time_utc"], utc=True)
    fila = met[met.time_utc == h]
    if len(fila) == 0 or ent.viento is None:
        return {"type": "FeatureCollection", "features": []}
    f = fila.iloc[0]
    U, V = ent.viento(float(f.wind_speed_10m_vectorial), float(f.wind_direction_10m))
    g = r.g; k = int(paso_m / g.res)
    rr, cc = np.mgrid[k // 2:g.nfil:k, k // 2:g.ncol:k]
    x, y = g.rc_a_xy(rr.ravel(), cc.ravel())
    t = Transformer.from_crs(g.crs, "EPSG:4326", always_xy=True); lon, lat = t.transform(x, y)
    u = U[rr.ravel(), cc.ravel()]; v = V[rr.ravel(), cc.ravel()]
    feats = []
    for i in range(len(lon)):
        if not np.isfinite(u[i]):
            continue
        vel = float(np.hypot(u[i], v[i])); hacia = float(np.degrees(np.arctan2(u[i], v[i])) % 360)
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [float(lon[i]), float(lat[i])]},
                      "properties": {"vel_ms": round(vel, 2), "hacia_deg": round(hacia, 1)}})
    return {"type": "FeatureCollection", "features": feats, "properties": {"hora_utc": str(h), "entrada_vel_ms": float(f.wind_speed_10m_vectorial),
                                                                            "entrada_dir_desde": float(f.wind_direction_10m), "nota": "WindNinja 100 m remuestreado a 30 m; flechas en la dirección hacia la que sopla"}}
