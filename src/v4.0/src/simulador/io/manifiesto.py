"""Manifiesto de datos: catálogo de todas las entradas del simulador y su validación.

El simulador **solo** lee lo que figura en `manifiesto_datos.yaml`. Al cargar:
1. cada archivo debe existir y su sha256 coincidir;
2. los rasters deben estar en la grilla de trabajo con el dtype y nodata declarados y
   valores dentro del rango válido; los combustibles, con códigos FBFM40 conocidos;
3. los vectores deben tener las capas y atributos mínimos;
4. las series meteorológicas, las columnas estándar.
Cualquier diferencia detiene la carga con `ErrorManifiesto`. No hay correcciones silenciosas.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml

from .grilla import Grilla, ErrorGrilla

VERSION_MANIFIESTO = "1.0"

ATRIBUTOS_VECTOR = {
    "caminos": ["id", "tipo", "ancho_m"],
    "viviendas": ["id"],
    "red_electrica": ["id", "tension"],
}
TIPOS_CAMINO = {"pavimentado", "ripio", "tierra", "huella"}
TENSIONES = {"AT", "MT", "BT"}
COLUMNAS_METEO = ["timestamp", "temp_c", "hr_pct", "viento_kmh", "viento_dir_deg", "precip_mm", "fuente"]


class ErrorManifiesto(RuntimeError):
    pass


def sha256_archivo(ruta: Path, bloque: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        while True:
            b = f.read(bloque)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


@dataclass
class Entrada:
    nombre: str
    ruta: str
    tipo: str                       # raster | vector | csv | geojson | json | tabla
    sha256: str
    crs: str | None = None
    dtype: str | None = None
    nodata: float | None = None
    unidades: str | None = None
    rango: list | None = None       # [min, max] válidos (sin contar nodata)
    bandas: int | None = None
    capas: list | None = None       # vectores: capas requeridas
    origen: dict = field(default_factory=dict)
    fecha_preparacion: str | None = None
    descripcion: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class Manifiesto:
    raiz: Path
    version: str
    grilla: Grilla
    entradas: dict[str, Entrada]
    codigos_combustible: list[int]
    fecha: str | None = None
    notas: list[str] = field(default_factory=list)

    def ruta(self, nombre: str) -> Path:
        if nombre not in self.entradas:
            raise ErrorManifiesto(f"La entrada '{nombre}' no figura en el manifiesto")
        return self.raiz / self.entradas[nombre].ruta

    def sha(self, nombre: str) -> str:
        return self.entradas[nombre].sha256

    # ------------------------------------------------------------------ E/S
    @classmethod
    def cargar(cls, ruta_yaml: Path) -> "Manifiesto":
        ruta_yaml = Path(ruta_yaml)
        d = yaml.safe_load(ruta_yaml.read_text(encoding="utf-8"))
        raiz = ruta_yaml.parent
        g = d["grilla"]
        grilla = Grilla(crs=g["crs"], xmin=g["xmin"], ymax=g["ymax"], res=g["res"], ancho=g["ancho"], alto=g["alto"])
        entradas = {}
        for e in d["entradas"]:
            campos = {k: e.pop(k) for k in list(e) if k in Entrada.__dataclass_fields__}
            entradas[campos["nombre"]] = Entrada(**campos, extra=e)
        return cls(raiz=raiz, version=str(d.get("version", "?")), grilla=grilla, entradas=entradas,
                   codigos_combustible=list(d.get("codigos_combustible", [])), fecha=d.get("fecha"),
                   notas=d.get("notas", []))

    def guardar(self, ruta_yaml: Path) -> None:
        d = {
            "version": self.version,
            "fecha": self.fecha,
            "grilla": {"crs": self.grilla.crs, "xmin": self.grilla.xmin, "ymax": self.grilla.ymax,
                       "res": self.grilla.res, "ancho": self.grilla.ancho, "alto": self.grilla.alto,
                       "xmin_xmax_ymin_ymax": list(self.grilla.bounds)},
            "codigos_combustible": self.codigos_combustible,
            "notas": self.notas,
            "entradas": [],
        }
        for e in self.entradas.values():
            item = {k: v for k, v in e.__dict__.items() if k != "extra" and v not in (None, {}, [])}
            item.update(e.extra)
            d["entradas"].append(item)
        Path(ruta_yaml).write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False, width=120), encoding="utf-8")

    # ------------------------------------------------------------------ validación
    def validar(self, verificar_sha: bool = True, verbose: bool = True) -> list[str]:
        """Valida todas las entradas. Devuelve la lista de mensajes OK; lanza ErrorManifiesto al primer problema."""
        mensajes = []
        for e in self.entradas.values():
            ruta = self.raiz / e.ruta
            if not ruta.exists():
                raise ErrorManifiesto(f"[{e.nombre}] no existe: {ruta}")
            if verificar_sha:
                sha = sha256_archivo(ruta)
                if sha != e.sha256:
                    raise ErrorManifiesto(f"[{e.nombre}] sha256 distinto al del manifiesto:\n  manifiesto {e.sha256}\n  archivo    {sha}")
            if e.tipo == "raster":
                self._validar_raster(e, ruta)
            elif e.tipo == "vector":
                self._validar_vector(e, ruta)
            elif e.tipo == "meteo":
                validar_meteo_csv(ruta)
            msg = f"OK  {e.nombre:28s} {e.ruta}"
            mensajes.append(msg)
            if verbose:
                print(msg)
        return mensajes

    def _validar_raster(self, e: Entrada, ruta: Path) -> None:
        import rasterio
        with rasterio.open(ruta) as src:
            try:
                self.grilla.verificar_raster(src, e.nombre)
            except ErrorGrilla as ex:
                raise ErrorManifiesto(str(ex)) from ex
            if e.dtype and src.dtypes[0] != e.dtype:
                raise ErrorManifiesto(f"[{e.nombre}] dtype {src.dtypes[0]} ≠ {e.dtype}")
            if e.nodata is not None and (src.nodata is None or float(src.nodata) != float(e.nodata)):
                raise ErrorManifiesto(f"[{e.nombre}] nodata {src.nodata} ≠ {e.nodata}")
            if e.bandas and src.count != e.bandas:
                raise ErrorManifiesto(f"[{e.nombre}] {src.count} bandas ≠ {e.bandas}")
            if e.rango or e.extra.get("codigos") == "combustible":
                a = src.read(1)
                validos = a != src.nodata if src.nodata is not None else np.ones(a.shape, bool)
                if e.rango:
                    v = a[validos]
                    if v.size and (v.min() < e.rango[0] or v.max() > e.rango[1]):
                        raise ErrorManifiesto(f"[{e.nombre}] valores fuera de rango {e.rango}: min {v.min()} max {v.max()}")
                if e.extra.get("codigos") == "combustible":
                    cods = set(np.unique(a[validos]).tolist())
                    desconocidos = cods - set(self.codigos_combustible)
                    if desconocidos:
                        raise ErrorManifiesto(f"[{e.nombre}] códigos de combustible desconocidos: {sorted(desconocidos)}")

    def _validar_vector(self, e: Entrada, ruta: Path) -> None:
        import pyogrio
        capas = {c[0] for c in pyogrio.list_layers(ruta)}
        for capa in e.capas or []:
            if capa not in capas:
                raise ErrorManifiesto(f"[{e.nombre}] falta la capa '{capa}' en {ruta.name} (hay {sorted(capas)})")
            info = pyogrio.read_info(ruta, layer=capa)
            if e.crs and not _mismo_crs(info["crs"], e.crs):
                raise ErrorManifiesto(f"[{e.nombre}:{capa}] CRS {info['crs']} ≠ {e.crs}")
            faltan = [a for a in ATRIBUTOS_VECTOR.get(capa, []) if a not in info["fields"]]
            if faltan:
                raise ErrorManifiesto(f"[{e.nombre}:{capa}] faltan atributos {faltan}")
            if capa == "caminos":
                df = pyogrio.read_dataframe(ruta, layer=capa, read_geometry=False, columns=["tipo", "ancho_m"])
                malos = set(df["tipo"].unique()) - TIPOS_CAMINO
                if malos:
                    raise ErrorManifiesto(f"[{e.nombre}:caminos] tipos no estándar: {malos}")
                if df["ancho_m"].isna().any() or (df["ancho_m"] <= 0).any():
                    raise ErrorManifiesto(f"[{e.nombre}:caminos] ancho_m vacío o ≤ 0")
            if capa == "red_electrica":
                df = pyogrio.read_dataframe(ruta, layer=capa, read_geometry=False, columns=["tension"])
                malos = set(df["tension"].unique()) - TENSIONES
                if malos:
                    raise ErrorManifiesto(f"[{e.nombre}:red_electrica] tensiones no estándar: {malos}")


def validar_meteo_csv(ruta: Path) -> "pd.DataFrame":
    import pandas as pd
    df = pd.read_csv(ruta)
    faltan = [c for c in COLUMNAS_METEO if c not in df.columns]
    if faltan:
        raise ErrorManifiesto(f"[{ruta.name}] faltan columnas {faltan}; se esperan exactamente {COLUMNAS_METEO}")
    con_huso = df["timestamp"].astype(str).str.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:?\d{2})$")
    if not con_huso.all():
        raise ErrorManifiesto(f"[{ruta.name}] timestamps sin huso horario (se exige ISO 8601 con offset, p. ej. 2025-09-29T12:00:00-03:00): "
                              f"{df.loc[~con_huso, 'timestamp'].head(3).tolist()}")
    ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    if ts.isna().any():
        raise ErrorManifiesto(f"[{ruta.name}] timestamps inválidos")
    if len(df) < 2:
        raise ErrorManifiesto(f"[{ruta.name}] la serie necesita al menos 2 horas")
    dif = ts.diff().dropna().dt.total_seconds().unique()
    if not np.allclose(dif, 3600):
        raise ErrorManifiesto(f"[{ruta.name}] la serie no es horaria sin huecos (saltos: {sorted(set(dif))} s)")
    num = ["temp_c", "hr_pct", "viento_kmh", "viento_dir_deg", "precip_mm"]
    if df[num].isna().any().any():
        raise ErrorManifiesto(f"[{ruta.name}] hay celdas vacías en {num}")
    if ((df.hr_pct < 0) | (df.hr_pct > 100)).any() or (df.viento_kmh < 0).any() or ((df.viento_dir_deg < 0) | (df.viento_dir_deg > 360)).any() or (df.precip_mm < 0).any():
        raise ErrorManifiesto(f"[{ruta.name}] valores fuera de rango físico")
    return df


def _mismo_crs(a, b) -> bool:
    from pyproj import CRS
    try:
        return CRS.from_user_input(a) == CRS.from_user_input(b)
    except Exception:
        return str(a) == str(b)
