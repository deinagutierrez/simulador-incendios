"""Grilla de trabajo: CRS, transformación afín, tamaño y recorte por ventana alineada."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

from affine import Affine
from rasterio.windows import Window


class ErrorGrilla(ValueError):
    """La grilla de una capa no coincide con la grilla de trabajo."""


@dataclass(frozen=True)
class Grilla:
    crs: str
    xmin: float
    ymax: float
    res: float
    ancho: int   # columnas
    alto: int    # filas

    # ------------------------------------------------------------------ derivadas
    @property
    def transform(self) -> Affine:
        return Affine(self.res, 0.0, self.xmin, 0.0, -self.res, self.ymax)

    @property
    def xmax(self) -> float:
        return self.xmin + self.ancho * self.res

    @property
    def ymin(self) -> float:
        return self.ymax - self.alto * self.res

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return (self.xmin, self.ymin, self.xmax, self.ymax)

    @property
    def shape(self) -> tuple[int, int]:
        return (self.alto, self.ancho)

    @property
    def area_celda_ha(self) -> float:
        return self.res * self.res / 1e4

    # ------------------------------------------------------------------ E/S
    def to_dict(self) -> dict:
        d = asdict(self)
        d["transform"] = list(self.transform)[:6]
        d["bounds"] = list(self.bounds)
        return d

    def guardar(self, ruta: Path) -> None:
        Path(ruta).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def cargar(cls, ruta: Path) -> "Grilla":
        d = json.loads(Path(ruta).read_text(encoding="utf-8"))
        return cls(crs=d["crs"], xmin=d["xmin"], ymax=d["ymax"], res=d["res"], ancho=d["ancho"], alto=d["alto"])

    @classmethod
    def desde_raster(cls, src) -> "Grilla":
        t = src.transform
        if abs(t.b) > 1e-9 or abs(t.d) > 1e-9 or abs(abs(t.a) - abs(t.e)) > 1e-6:
            raise ErrorGrilla(f"raster con rotación o celdas no cuadradas: {src.name}")
        return cls(crs=src.crs.to_string(), xmin=t.c, ymax=t.f, res=abs(t.a), ancho=src.width, alto=src.height)

    # ------------------------------------------------------------------ comprobaciones
    def coincide(self, otra: "Grilla", tol: float = 1e-3) -> bool:
        return (
            _mismo_crs(self.crs, otra.crs)
            and abs(self.xmin - otra.xmin) < tol
            and abs(self.ymax - otra.ymax) < tol
            and abs(self.res - otra.res) < tol
            and self.ancho == otra.ancho
            and self.alto == otra.alto
        )

    def verificar_raster(self, src, nombre: str = "") -> None:
        g = Grilla.desde_raster(src)
        if not self.coincide(g):
            raise ErrorGrilla(
                f"La capa {nombre or src.name} no está en la grilla de trabajo.\n"
                f"  esperado: {self}\n  encontrado: {g}"
            )

    def alineado(self, x: float, y: float, tol: float = 1e-3) -> bool:
        """¿El punto (x, y) cae sobre un vértice de la grilla?"""
        kx = (x - self.xmin) / self.res
        ky = (self.ymax - y) / self.res
        return abs(kx - round(kx)) < tol and abs(ky - round(ky)) < tol

    # ------------------------------------------------------------------ ventanas
    def ventana(self, xmin: float, ymin: float, xmax: float, ymax: float) -> tuple["Grilla", Window]:
        """Sub-grilla alineada a esta grilla. Falla si los bordes no caen sobre vértices
        o si la caja se sale del dominio."""
        for x, y in ((xmin, ymax), (xmax, ymin)):
            if not self.alineado(x, y):
                raise ErrorGrilla(f"La caja ({xmin}, {ymin}, {xmax}, {ymax}) no está alineada a la grilla de {self.res} m")
        if xmin < self.xmin - 1e-3 or xmax > self.xmax + 1e-3 or ymin < self.ymin - 1e-3 or ymax > self.ymax + 1e-3:
            raise ErrorGrilla(f"La caja ({xmin}, {ymin}, {xmax}, {ymax}) se sale del dominio {self.bounds}")
        col0 = int(round((xmin - self.xmin) / self.res))
        fil0 = int(round((self.ymax - ymax) / self.res))
        ancho = int(round((xmax - xmin) / self.res))
        alto = int(round((ymax - ymin) / self.res))
        sub = Grilla(self.crs, xmin, ymax, self.res, ancho, alto)
        return sub, Window(col0, fil0, ancho, alto)

    def indices(self, x, y):
        """Coordenadas → (fila, columna). Acepta escalares o arrays."""
        import numpy as np
        col = np.floor((np.asarray(x) - self.xmin) / self.res).astype(int)
        fil = np.floor((self.ymax - np.asarray(y)) / self.res).astype(int)
        return fil, col

    def centros(self, fil, col):
        """(fila, columna) → coordenadas del centro de celda."""
        x = self.xmin + (col + 0.5) * self.res
        y = self.ymax - (fil + 0.5) * self.res
        return x, y


def _mismo_crs(a: str, b: str) -> bool:
    from pyproj import CRS
    try:
        return CRS.from_user_input(a) == CRS.from_user_input(b)
    except Exception:
        return a == b
