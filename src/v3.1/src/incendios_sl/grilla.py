"""Grilla maestra de simulación (EPSG:5345, 30 m) y utilidades de alineación de rasters y vectores.

Convenciones:
- Filas crecen hacia el sur (transformación afín con paso negativo en y), columnas hacia el este.
- Todas las superficies y distancias se calculan en metros sobre el CRS proyectado.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import rasterio
from rasterio import features
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.warp import reproject
from pyproj import Transformer
from shapely.geometry import shape, mapping
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shp_transform


@dataclass(frozen=True)
class Grilla:
    crs: str
    res: float
    xmin: float
    ymin: float
    xmax: float
    ymax: float

    # ---- geometría ----
    @property
    def ncol(self) -> int:
        return int(round((self.xmax - self.xmin) / self.res))

    @property
    def nfil(self) -> int:
        return int(round((self.ymax - self.ymin) / self.res))

    @property
    def shape(self) -> tuple[int, int]:
        return (self.nfil, self.ncol)

    @property
    def transform(self) -> Affine:
        return Affine(self.res, 0.0, self.xmin, 0.0, -self.res, self.ymax)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return (self.xmin, self.ymin, self.xmax, self.ymax)

    @property
    def n_celdas(self) -> int:
        return self.nfil * self.ncol

    @property
    def area_celda_m2(self) -> float:
        return self.res * self.res

    def ampliar(self, margen_m: float) -> "Grilla":
        """Grilla ampliada con un margen redondeado hacia arriba a un múltiplo de la resolución."""
        k = math.ceil(margen_m / self.res - 1e-9)
        m = k * self.res
        return Grilla(self.crs, self.res, self.xmin - m, self.ymin - m, self.xmax + m, self.ymax + m)

    def ventana_en(self, otra: "Grilla") -> tuple[int, int]:
        """Desplazamiento (fila, columna) del origen de esta grilla dentro de `otra` (misma res y alineación)."""
        if abs(otra.res - self.res) > 1e-9:
            raise ValueError("resoluciones distintas")
        dc = (self.xmin - otra.xmin) / self.res
        dr = (otra.ymax - self.ymax) / self.res
        if abs(dc - round(dc)) > 1e-6 or abs(dr - round(dr)) > 1e-6:
            raise ValueError("las grillas no están alineadas")
        return int(round(dr)), int(round(dc))

    def xy_a_rc(self, x: np.ndarray | float, y: np.ndarray | float) -> tuple[np.ndarray, np.ndarray]:
        col = np.floor((np.asarray(x) - self.xmin) / self.res).astype(np.int64)
        fil = np.floor((self.ymax - np.asarray(y)) / self.res).astype(np.int64)
        return fil, col

    def rc_a_xy(self, fil: np.ndarray | int, col: np.ndarray | int) -> tuple[np.ndarray, np.ndarray]:
        """Centro de la celda."""
        x = self.xmin + (np.asarray(col) + 0.5) * self.res
        y = self.ymax - (np.asarray(fil) + 0.5) * self.res
        return x, y

    def lonlat_a_rc(self, lon, lat) -> tuple[np.ndarray, np.ndarray]:
        t = Transformer.from_crs("EPSG:4326", self.crs, always_xy=True)
        x, y = t.transform(lon, lat)
        return self.xy_a_rc(x, y)

    def dentro(self, fil, col) -> np.ndarray:
        fil = np.asarray(fil); col = np.asarray(col)
        return (fil >= 0) & (fil < self.nfil) & (col >= 0) & (col < self.ncol)

    # ---- raster ----
    def perfil(self, dtype: str, nodata: Any = None, count: int = 1) -> dict[str, Any]:
        return {
            "driver": "GTiff", "dtype": dtype, "count": count, "width": self.ncol, "height": self.nfil,
            "crs": self.crs, "transform": self.transform, "nodata": nodata,
            "tiled": True, "blockxsize": 512, "blockysize": 512, "compress": "lzw",
        }

    def rasterizar(self, geometrias: Iterable[tuple[BaseGeometry, Any]], dtype="uint8", fill=0, all_touched=False) -> np.ndarray:
        """Rasteriza pares (geometría en el CRS de la grilla, valor)."""
        pares = [(mapping(g), v) for g, v in geometrias]
        if not pares:
            return np.full(self.shape, fill, dtype=dtype)
        return features.rasterize(pares, out_shape=self.shape, transform=self.transform, fill=fill,
                                  all_touched=all_touched, dtype=dtype)

    def como_dict(self) -> dict[str, Any]:
        return {"crs": self.crs, "res": self.res, "xmin": self.xmin, "ymin": self.ymin, "xmax": self.xmax,
                "ymax": self.ymax, "ncol": self.ncol, "nfil": self.nfil}

    @classmethod
    def desde_config(cls, cfg: dict[str, Any]) -> "Grilla":
        g = cfg["grilla"]
        return cls(cfg["crs"], float(cfg["resolucion_m"]), float(g["xmin"]), float(g["ymin"]), float(g["xmax"]), float(g["ymax"]))

    @classmethod
    def desde_raster(cls, path: str | Path) -> "Grilla":
        with rasterio.open(path) as ds:
            t = ds.transform
            if abs(t.a) != abs(t.e) or t.b != 0 or t.d != 0:
                raise ValueError("raster rotado o con píxel no cuadrado")
            return cls(ds.crs.to_string(), abs(t.a), ds.bounds.left, ds.bounds.bottom, ds.bounds.right, ds.bounds.top)


# ---------------------------------------------------------------------------
def alinear_raster(src: str | Path, grilla: Grilla, remuestreo: Resampling, dtype: str | None = None,
                   nodata_dst: Any = None, banda: int = 1) -> np.ndarray:
    """Reproyecta/remuestrea la banda de un raster a la grilla. Devuelve el array (nfil, ncol)."""
    with rasterio.open(src) as ds:
        dtype = dtype or ds.dtypes[banda - 1]
        nodata_src = ds.nodata
        if nodata_dst is None:
            nodata_dst = nodata_src
        out = np.full(grilla.shape, nodata_dst if nodata_dst is not None else 0, dtype=dtype)
        reproject(rasterio.band(ds, banda), out, dst_transform=grilla.transform, dst_crs=grilla.crs,
                  src_nodata=nodata_src, dst_nodata=nodata_dst, resampling=remuestreo, num_threads=4)
    return out


def guardar_raster(path: str | Path, arr: np.ndarray, grilla: Grilla, nodata: Any = None,
                   descripciones: list[str] | None = None, tags: dict[str, str] | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.asarray(arr)
    if arr.ndim == 2:
        arr = arr[None, ...]
    perfil = grilla.perfil(str(arr.dtype), nodata, count=arr.shape[0])
    with rasterio.open(path, "w", **perfil) as dst:
        dst.write(arr)
        if descripciones:
            for i, d in enumerate(descripciones, 1):
                dst.set_band_description(i, d)
        if tags:
            dst.update_tags(**tags)
    return path


def leer_raster(path: str | Path, banda: int | None = 1) -> tuple[np.ndarray, Grilla, Any]:
    with rasterio.open(path) as ds:
        arr = ds.read(banda) if banda else ds.read()
        return arr, Grilla.desde_raster(path), ds.nodata


# ---------------------------------------------------------------------------
def pendiente_orientacion(dem: np.ndarray, res: float, nodata=None) -> tuple[np.ndarray, np.ndarray]:
    """Pendiente (grados) y orientación (grados, azimut al que mira la ladera: 0 N, 90 E, 180 S, 270 O)
    con el operador de Horn (1981) sobre 3 × 3, como gdaldem. Bordes: se repite el valor vecino.
    Celdas planas: orientación = -1."""
    z = dem.astype(np.float64)
    if nodata is not None:
        z = np.where(z == nodata, np.nan, z)
    zp = np.pad(z, 1, mode="edge")
    a, b, c = zp[:-2, :-2], zp[:-2, 1:-1], zp[:-2, 2:]
    d, _, f = zp[1:-1, :-2], zp[1:-1, 1:-1], zp[1:-1, 2:]
    g, h, i = zp[2:, :-2], zp[2:, 1:-1], zp[2:, 2:]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * res)          # positivo hacia el este
    dzdy_norte = ((a + 2 * b + c) - (g + 2 * h + i)) / (8 * res)    # positivo hacia el norte
    pend = np.degrees(np.arctan(np.hypot(dzdx, dzdy_norte)))
    # la ladera "mira" cuesta abajo: vector (-dzdx, -dzdy); azimut = atan2(este, norte)
    asp = (np.degrees(np.arctan2(-dzdx, -dzdy_norte))) % 360.0
    plano = (dzdx == 0) & (dzdy_norte == 0)
    asp = np.where(plano, -1.0, asp)
    return pend.astype(np.float32), asp.astype(np.float32)


def geometria_a_crs(geom: BaseGeometry, crs_origen: str, crs_destino: str) -> BaseGeometry:
    t = Transformer.from_crs(crs_origen, crs_destino, always_xy=True)
    return shp_transform(lambda x, y, z=None: t.transform(x, y), geom)


def bbox_a_lonlat(grilla: Grilla) -> tuple[float, float, float, float]:
    """Bounding box en lon/lat (WGS84) que envuelve a la grilla (muestreando el borde)."""
    t = Transformer.from_crs(grilla.crs, "EPSG:4326", always_xy=True)
    xs = np.linspace(grilla.xmin, grilla.xmax, 50)
    ys = np.linspace(grilla.ymin, grilla.ymax, 50)
    bx = np.concatenate([xs, xs, np.full(50, grilla.xmin), np.full(50, grilla.xmax)])
    by = np.concatenate([np.full(50, grilla.ymin), np.full(50, grilla.ymax), ys, ys])
    lon, lat = t.transform(bx, by)
    return float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max())
