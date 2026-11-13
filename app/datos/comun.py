"""Piezas comunes de los datos dinámicos: rutas, grillas del dominio, escritura de rásteres y procedencia.

No importa ningún motor: las grillas se leen del YAML del dominio con la misma aritmética que `incendios_sl.grilla.Grilla`
de v3.1 (`ampliar` redondea el margen hacia arriba a un múltiplo de la resolución).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[2]
ENTRADAS = REPO / "datos" / "inputSimulacion"
CACHE = REPO / "datos" / "procesados" / "app"
NODATA_INDICES = -32768
ESCALA_INDICES = 10000


def dir_cache(*partes: str) -> Path:
    d = CACHE.joinpath(*partes)
    d.mkdir(parents=True, exist_ok=True)
    return d


def ahora_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class Grilla:
    crs: str
    res: float
    xmin: float
    ymin: float
    xmax: float
    ymax: float

    @property
    def ncol(self) -> int:
        return int(round((self.xmax - self.xmin) / self.res))

    @property
    def nfil(self) -> int:
        return int(round((self.ymax - self.ymin) / self.res))

    @property
    def forma(self) -> tuple[int, int]:
        return self.nfil, self.ncol

    @property
    def transform(self):
        from affine import Affine
        return Affine(self.res, 0.0, self.xmin, 0.0, -self.res, self.ymax)

    def ampliar(self, margen_m: float) -> "Grilla":
        m = math.ceil(margen_m / self.res - 1e-9) * self.res
        return Grilla(self.crs, self.res, self.xmin - m, self.ymin - m, self.xmax + m, self.ymax + m)

    def con_res(self, res: float) -> "Grilla":
        """La misma extensión con otra resolución (como pide GEE con `crs_transform` en `gee_comun.py` de v3.1)."""
        return Grilla(self.crs, float(res), self.xmin, self.ymin, self.xmin + round((self.xmax - self.xmin) / res) * res,
                      self.ymax)

    def como_dict(self) -> dict:
        return {"crs": self.crs, "res": self.res, "xmin": self.xmin, "ymin": self.ymin, "xmax": self.xmax, "ymax": self.ymax,
                "ncol": self.ncol, "nfil": self.nfil}

    def limites_grados(self) -> tuple[float, float, float, float]:
        """(oeste, sur, este, norte) en grados, para buscar escenas."""
        from pyproj import Transformer
        t = Transformer.from_crs(self.crs, "EPSG:4326", always_xy=True)
        xs = np.linspace(self.xmin, self.xmax, 21)
        ys = np.linspace(self.ymin, self.ymax, 21)
        X, Y = np.meshgrid(xs, ys)
        lon, lat = t.transform(X.ravel(), Y.ravel())
        return float(np.min(lon)), float(np.min(lat)), float(np.max(lon)), float(np.max(lat))


@lru_cache(maxsize=1)
def dominio_yaml() -> dict:
    ruta = next((REPO / "escenarios" / "v4.0" / "dominios").glob("dominio_*.yaml"))
    return yaml.safe_load(ruta.read_text(encoding="utf-8"))


def grilla_dominio() -> Grilla:
    d = dominio_yaml()
    g = d["grilla"]
    return Grilla(d["crs"], float(d["resolucion_m"]), float(g["xmin"]), float(g["ymin"]), float(g["xmax"]), float(g["ymax"]))


def grilla_indices_20m() -> Grilla:
    """Grilla del compuesto de ventana: la de índices de v3.1 (dominio + `margen_indices_m`) a 20 m, como la descarga de
    `gee_indices.obtener_indices(..., escala=20)`."""
    return grilla_dominio().ampliar(float(dominio_yaml()["margen_indices_m"])).con_res(20.0)


# ------------------------------------------------------------------ archivos
def sha256(ruta: Path, bloque: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        while True:
            b = f.read(bloque)
            if not b:
                return h.hexdigest()
            h.update(b)


def escribir_json(ruta: Path, datos) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_name(ruta.name + ".tmp")
    tmp.write_text(json.dumps(datos, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    os.replace(tmp, ruta)


def leer_json(ruta: Path, defecto=None):
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defecto


def escribir_procedencia(producto: Path, fuente: str, parametros: dict, extra: dict | None = None) -> dict:
    """`<producto>.json` con fuente, parámetros, fecha y sha256 del producto (plan §4.5)."""
    d = {"producto": producto.name, "fuente": fuente, "generado_utc": ahora_utc(), "codigo": "app/datos (simulador)",
         "parametros": parametros, "sha256": sha256(producto)} | (extra or {})
    escribir_json(Path(str(producto) + ".json"), d)
    return d


def escribir_tif(ruta: Path, bandas: list[np.ndarray], grilla: Grilla, dtype: str, nodata, descripciones: list[str] | None = None) -> Path:
    import rasterio
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_name(ruta.name + ".tmp.tif")
    perfil = {"driver": "GTiff", "height": grilla.nfil, "width": grilla.ncol, "count": len(bandas), "dtype": dtype,
              "crs": grilla.crs, "transform": grilla.transform, "nodata": nodata, "compress": "deflate", "tiled": True,
              "blockxsize": 256, "blockysize": 256, "predictor": 2}
    with rasterio.open(tmp, "w", **perfil) as s:
        for i, b in enumerate(bandas, 1):
            s.write(b.astype(dtype), i)
            if descripciones:
                s.set_band_description(i, descripciones[i - 1])
    os.replace(tmp, ruta)
    return ruta


def a_int16(indice: np.ndarray) -> np.ndarray:
    """Índice en [-1, 1] (NaN sin dato) → int16 × 10000 con nodata −32768, como los productos del proyecto."""
    return np.where(np.isfinite(indice), np.clip(np.round(indice * ESCALA_INDICES), -ESCALA_INDICES, ESCALA_INDICES),
                    NODATA_INDICES).astype("int16")
