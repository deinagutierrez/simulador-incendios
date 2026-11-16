"""NDVI y NDMI desde Sentinel-2 L2A en AWS, sin clave ni cuenta (decisión D-E3-08; plan §4.3).

Catálogo Earth Search (`earth-search.aws.element84.com/v1`, colección `sentinel-2-l2a`); las bandas son COG públicos en S3
que `rasterio` lee por HTTP, solo la parte que cae en el dominio.

Dos productos, cada uno con el método del motor que lo usa:

| Producto | Ventana | NDMI | Lectura | Salida |
|---|---|---|---|---|
| `ventana` (v3.1, y v4.0 como `indices_mes_evento`) | la que se pida; en tiempo real, 45 días que terminan el día anterior | (B8 − B11)/(B8 + B11) | 20 m (B4 y B8 desde su nivel de 20 m), promedio | `ndvi_*.tif`, `ndmi_*.tif`, `n_obs_*.tif` a 20 m en la grilla de índices de v3.1, como `gee_indices.py` |
| `mensual` (v4.0, regla 3.3b) | un mes calendario | (B8A − B11)/(B8A + B11) | directo a 30 m, vecino más cercano | `NDVI_NDMI_AAAA_MM.tif`, 2 bandas, en la grilla del dominio, como `descargar_ndvi_ndmi_gee.py` |

NDVI = (B8 − B4)/(B8 + B4) en los dos. En los dos: índice por fecha y mediana de las fechas, como hacen los scripts de GEE.

Máscara de nubes: capa SCL (se descartan sin dato, saturado, sombra de nube, nube media y alta, cirros y nieve) en lugar de
Cloud Score+ ≥ 0,6, y se descartan las teselas con más de 80 % de nubes. Reflectancia = DN / 10000 + `desplazamiento`: los
metadatos dicen a la vez que la corrección ya está aplicada (`earthsearch:boa_offset_applied`) y que hay que sumar −0,1
(`raster:bands.offset`); cuál vale se decide con números (prerregistro E-E3-2) y se guarda en la procedencia.

Diferencias con lo calibrado, que mide E-E3-2: máscara SCL en lugar de Cloud Score+; escala de reflectancia; mosaico de dos
zonas UTM (19 y 20) reproyectadas a EPSG:5345.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import time
import warnings
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from . import comun
from .comun import Grilla

log = logging.getLogger(__name__)

CATALOGO = "https://earth-search.aws.element84.com/v1"
COLECCION = "sentinel-2-l2a"
ACTIVOS = {"B04": "red", "B08": "nir", "B8A": "nir08", "B11": "swir16", "SCL": "scl"}
BANDAS_10M = {"B04", "B08"}
SCL_INVALIDOS = (0, 1, 3, 8, 9, 10, 11)     # sin dato, saturado, sombra de nube, nube media, nube alta, cirros, nieve
MAX_NUBES_TESELA = 80.0
VERSION = "1.0"
# Lectura de COG por HTTP: no listar el directorio, pedir rangos juntos y reintentar.
ENTORNO_GDAL = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "AWS_NO_SIGN_REQUEST": "YES", "GDAL_HTTP_MULTIRANGE": "YES",
                "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES", "GDAL_HTTP_MAX_RETRY": "4", "GDAL_HTTP_RETRY_DELAY": "2",
                "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif", "VSI_CACHE": "TRUE"}

Progreso = Callable[[int, int, str], None]


def _sin_progreso(hechos: int, total: int, texto: str) -> None:
    pass


@dataclass(frozen=True)
class Metodo:
    """Cómo se arma un producto. Va completo a la procedencia y a la clave de la caché."""
    nombre: str                       # "ventana" o "mensual"
    nir_ndmi: str                     # "B08" o "B8A"
    remuestreo: str                   # "average" o "nearest"
    desplazamiento: float = 0.0       # se suma a DN/10000 (0 o −0,1)
    max_nubes: float = MAX_NUBES_TESELA
    scl_invalidos: tuple = SCL_INVALIDOS

    def bandas(self) -> list[str]:
        return sorted({"B04", "B08", self.nir_ndmi, "B11"})

    def como_dict(self) -> dict:
        return {"nombre": self.nombre, "ndvi": "(B08-B04)/(B08+B04)", "ndmi": f"({self.nir_ndmi}-B11)/({self.nir_ndmi}+B11)",
                "remuestreo": self.remuestreo, "lectura_bandas_10m": "nivel de 20 m del COG",
                "reflectancia": f"DN/10000 + ({self.desplazamiento})", "max_nubes_tesela_pct": self.max_nubes,
                "mascara": f"SCL, se descartan las clases {list(self.scl_invalidos)}", "compuesto": "mediana de los índices por fecha",
                "version": VERSION}


def metodo_ventana(desplazamiento: float = 0.0) -> Metodo:
    return Metodo("ventana", "B08", "average", desplazamiento)


def metodo_mensual(desplazamiento: float = 0.0) -> Metodo:
    return Metodo("mensual", "B8A", "nearest", desplazamiento)


# ------------------------------------------------------------------ catálogo
def buscar(limites: tuple[float, float, float, float], desde: dt.date, hasta: dt.date, max_nubes: float = MAX_NUBES_TESELA,
           sesion=None, tiempo_s: float = 60.0) -> list[dict]:
    """Escenas de `desde` a `hasta` inclusive que tocan el recuadro (oeste, sur, este, norte en grados), con a lo sumo
    `max_nubes` % de nubes en la tesela. Devuelve los ítems STAC, ordenados por fecha y tesela."""
    import requests
    s = sesion or requests.Session()
    cuerpo = {"collections": [COLECCION], "bbox": list(limites), "limit": 100,
              "datetime": f"{desde:%Y-%m-%d}T00:00:00Z/{hasta:%Y-%m-%d}T23:59:59Z"}
    items, url, metodo = [], f"{CATALOGO}/search", "POST"
    for _ in range(50):
        r = s.post(url, json=cuerpo, timeout=tiempo_s) if metodo == "POST" else s.get(url, timeout=tiempo_s)
        r.raise_for_status()
        d = r.json()
        items += d.get("features", [])
        sig = next((l for l in d.get("links", []) if l.get("rel") == "next"), None)
        if not sig:
            break
        url, metodo = sig["href"], sig.get("method", "GET").upper()
        if metodo == "POST":
            cuerpo = sig.get("body") or cuerpo
    vistos, out = set(), []
    for it in items:
        if it["id"] in vistos:
            continue
        vistos.add(it["id"])
        nubes = it["properties"].get("eo:cloud_cover")
        if nubes is not None and float(nubes) > max_nubes:
            continue
        out.append(it)
    return sorted(out, key=lambda it: (it["properties"]["datetime"], it["id"]))


def resumen_escena(it: dict) -> dict:
    p = it["properties"]
    return {"id": it["id"], "fecha": p["datetime"][:10], "tesela": p.get("grid:code", "").replace("MGRS-", ""),
            "nubes_pct": p.get("eo:cloud_cover"), "linea_base": p.get("s2:processing_baseline"),
            "boa_offset_applied": p.get("earthsearch:boa_offset_applied")}


# ------------------------------------------------------------------ lectura
def leer_banda(href: str, grilla: Grilla, remuestreo: str, nivel_20m: bool) -> np.ndarray:
    """Banda remota reproyectada a la grilla (uint16, 0 = sin dato). Con `nivel_20m` lee el primer nivel reducido del COG
    (las bandas de 10 m tienen su nivel de 20 m)."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.vrt import WarpedVRT
    with rasterio.Env(**ENTORNO_GDAL):
        abrir = {"overview_level": 0} if nivel_20m else {}
        with rasterio.open(href, **abrir) as src, \
                WarpedVRT(src, crs=grilla.crs, transform=grilla.transform, width=grilla.ncol, height=grilla.nfil,
                          resampling=getattr(Resampling, remuestreo), src_nodata=0, nodata=0) as vrt:
            return vrt.read(1)


def _leer_con_reintentos(href: str, grilla: Grilla, remuestreo: str, nivel_20m: bool, intentos: int = 3) -> np.ndarray:
    ultimo = None
    for i in range(intentos):
        try:
            return leer_banda(href, grilla, remuestreo, nivel_20m)
        except Exception as e:            # pragma: no cover - red
            ultimo = e
            log.warning("lectura de %s falló (intento %d): %s", href.rsplit("/", 2)[-2:], i + 1, str(e)[:160])
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"no se pudo leer {href}: {ultimo}")


def indices_escena(it: dict, grilla: Grilla, metodo: Metodo, lector=None) -> tuple[np.ndarray, np.ndarray]:
    """(NDVI, NDMI) de una escena en la grilla, int16 × 10000 con −32768 donde no hay dato o la SCL lo descarta.
    `lector(href, grilla, remuestreo, nivel_20m)` permite reemplazar la lectura en las pruebas."""
    leer = lector or _leer_con_reintentos
    activos = it["assets"]
    scl = leer(activos[ACTIVOS["SCL"]]["href"], grilla, "nearest", False)
    valido = (scl != 0) & ~np.isin(scl, metodo.scl_invalidos)
    if not valido.any():
        vacio = np.full(grilla.forma, comun.NODATA_INDICES, "int16")
        return vacio, vacio.copy()
    refl = {}
    for b in metodo.bandas():
        dn = leer(activos[ACTIVOS[b]]["href"], grilla, metodo.remuestreo, b in BANDAS_10M)
        valido &= dn > 0
        refl[b] = dn.astype("float32") / 10000.0 + np.float32(metodo.desplazamiento)
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = (refl["B08"] - refl["B04"]) / (refl["B08"] + refl["B04"])
        ndmi = (refl[metodo.nir_ndmi] - refl["B11"]) / (refl[metodo.nir_ndmi] + refl["B11"])
    ndvi[~valido] = np.nan
    ndmi[~valido] = np.nan
    return comun.a_int16(ndvi), comun.a_int16(ndmi)


# ------------------------------------------------------------------ caché por escena
def _clave(grilla: Grilla, metodo: Metodo) -> str:
    texto = json.dumps({"grilla": grilla.como_dict(), "metodo": metodo.como_dict()}, sort_keys=True)
    return hashlib.sha256(texto.encode()).hexdigest()[:16]


def dir_escenas(grilla: Grilla, metodo: Metodo) -> Path:
    return comun.dir_cache("sentinel2", "escenas", f"{metodo.nombre}_{_clave(grilla, metodo)}")


def indices_escena_en_cache(it: dict, grilla: Grilla, metodo: Metodo, lector=None) -> tuple[np.ndarray, np.ndarray, bool]:
    """Como `indices_escena`, guardando el resultado: una escena ya leída no se vuelve a pedir."""
    ruta = dir_escenas(grilla, metodo) / f"{it['id']}.npz"
    if ruta.exists():
        try:
            with np.load(ruta) as z:
                return z["ndvi"], z["ndmi"], True
        except (OSError, ValueError, KeyError):
            ruta.unlink(missing_ok=True)
    ndvi, ndmi = indices_escena(it, grilla, metodo, lector)
    tmp = ruta.with_name(ruta.stem + ".tmp.npz")
    np.savez_compressed(tmp, ndvi=ndvi, ndmi=ndmi)
    tmp.replace(ruta)
    return ndvi, ndmi, False


# ------------------------------------------------------------------ compuesto
@dataclass
class Compuesto:
    ndvi: np.ndarray                  # float32, NaN sin dato
    ndmi: np.ndarray
    n_obs: np.ndarray                 # uint8: fechas válidas por celda
    escenas: list[dict] = field(default_factory=list)
    fechas: list[str] = field(default_factory=list)
    segundos: float = 0.0
    de_cache: int = 0


def _mosaico(capas: list[np.ndarray]) -> np.ndarray:
    """Teselas de una misma fecha: en cada celda, el primer valor con dato."""
    out = capas[0].copy()
    for c in capas[1:]:
        hueco = out == comun.NODATA_INDICES
        out[hueco] = c[hueco]
    return out


def _mediana(pila: list[np.ndarray], filas_por_bloque: int = 256) -> np.ndarray:
    nf, nc = pila[0].shape
    out = np.full((nf, nc), np.nan, "float32")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)          # celdas sin dato en todas las fechas
        for f0 in range(0, nf, filas_por_bloque):
            bloque = np.stack([p[f0:f0 + filas_por_bloque] for p in pila]).astype("float32")
            bloque[bloque == comun.NODATA_INDICES] = np.nan
            out[f0:f0 + filas_por_bloque] = np.nanmedian(bloque, axis=0) / comun.ESCALA_INDICES
    return out


def componer(items: list[dict], grilla: Grilla, metodo: Metodo, progreso: Progreso = _sin_progreso, hilos: int = 6,
             lector=None) -> Compuesto:
    """Índices por escena (en paralelo, con caché), mosaico por fecha y mediana de las fechas."""
    t0 = time.time()
    if not items:
        raise ValueError("no hay escenas para componer")
    por_escena: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    de_cache = 0
    total = len(items)
    progreso(0, total, f"{total} escenas para leer")
    with ThreadPoolExecutor(max_workers=max(1, hilos)) as ex:
        futuros = {ex.submit(indices_escena_en_cache, it, grilla, metodo, lector): it for it in items}
        for k, fut in enumerate(as_completed(futuros), 1):
            it = futuros[fut]
            ndvi, ndmi, cache = fut.result()
            de_cache += cache
            por_escena[it["id"]] = (ndvi, ndmi)
            progreso(k, total, f"escena {resumen_escena(it)['fecha']} {resumen_escena(it)['tesela']}" + (" (caché)" if cache else ""))
    por_fecha: dict[str, list[str]] = defaultdict(list)
    for it in items:
        por_fecha[it["properties"]["datetime"][:10]].append(it["id"])
    ndvi_f, ndmi_f, fechas = [], [], []
    for fecha in sorted(por_fecha):
        ids = por_fecha[fecha]
        v = _mosaico([por_escena[i][0] for i in ids])
        m = _mosaico([por_escena[i][1] for i in ids])
        if (v != comun.NODATA_INDICES).any():
            ndvi_f.append(v); ndmi_f.append(m); fechas.append(fecha)
    if not fechas:
        raise ValueError("ninguna escena tiene celdas despejadas en el dominio")
    n_obs = np.sum([v != comun.NODATA_INDICES for v in ndvi_f], axis=0).astype("uint8")
    return Compuesto(_mediana(ndvi_f), _mediana(ndmi_f), n_obs, [resumen_escena(it) for it in items], fechas,
                     round(time.time() - t0, 1), de_cache)


# ------------------------------------------------------------------ productos
def compuesto_ventana(desde: dt.date, hasta: dt.date, salida: Path, etiqueta: str, desplazamiento: float = 0.0,
                      progreso: Progreso = _sin_progreso, items: list[dict] | None = None, lector=None) -> dict:
    """Compuesto de ventana (método v3.1) de `desde` a `hasta` inclusive, a 20 m en la grilla de índices de v3.1.
    Escribe `ndvi_<etiqueta>.tif`, `ndmi_<etiqueta>.tif`, `n_obs_<etiqueta>.tif` y `metadatos_<etiqueta>.json` en `salida`."""
    grilla = comun.grilla_indices_20m()
    metodo = metodo_ventana(desplazamiento)
    if items is None:
        progreso(0, 1, "buscando escenas en el catálogo")
        items = buscar(grilla.limites_grados(), desde, hasta, metodo.max_nubes)
    c = componer(items, grilla, metodo, progreso, lector=lector)
    salida.mkdir(parents=True, exist_ok=True)
    rutas = {"ndvi": salida / f"ndvi_{etiqueta}.tif", "ndmi": salida / f"ndmi_{etiqueta}.tif", "n_obs": salida / f"n_obs_{etiqueta}.tif"}
    comun.escribir_tif(rutas["ndvi"], [comun.a_int16(c.ndvi)], grilla, "int16", comun.NODATA_INDICES, ["NDVI x10000"])
    comun.escribir_tif(rutas["ndmi"], [comun.a_int16(c.ndmi)], grilla, "int16", comun.NODATA_INDICES, ["NDMI x10000 (B08)"])
    comun.escribir_tif(rutas["n_obs"], [c.n_obs], grilla, "uint8", 0, ["fechas válidas"])
    parametros = {"producto": "ventana", "ventana": [f"{desde}", f"{hasta}"], "grilla": grilla.como_dict(), "metodo": metodo.como_dict()}
    meta = _metadatos(c, parametros, grilla)
    for r in rutas.values():
        comun.escribir_procedencia(r, f"Sentinel-2 L2A, AWS (Earth Search), compuesto de ventana", parametros,
                                   {"n_escenas": len(c.escenas), "n_fechas": len(c.fechas)})
    comun.escribir_json(salida / f"metadatos_{etiqueta}.json", meta)
    return {k: str(v) for k, v in rutas.items()} | {"metadatos": str(salida / f"metadatos_{etiqueta}.json"),
                                                     "n_escenas": len(c.escenas), "fechas": c.fechas, "segundos": c.segundos}


def compuesto_mensual(anio: int, mes: int, salida: Path, desplazamiento: float = 0.0, progreso: Progreso = _sin_progreso,
                      items: list[dict] | None = None, lector=None, nombre: str | None = None) -> dict:
    """Compuesto mensual (método de SIM) en la grilla del dominio: `NDVI_NDMI_AAAA_MM.tif`, 2 bandas int16 × 10000."""
    grilla = comun.grilla_dominio()
    metodo = metodo_mensual(desplazamiento)
    desde = dt.date(anio, mes, 1)
    hasta = (dt.date(anio + (mes == 12), mes % 12 + 1, 1) - dt.timedelta(days=1))
    if items is None:
        progreso(0, 1, f"buscando escenas de {anio}-{mes:02d}")
        items = buscar(grilla.limites_grados(), desde, hasta, metodo.max_nubes)
    c = componer(items, grilla, metodo, progreso, lector=lector)
    ruta = salida / (nombre or f"NDVI_NDMI_{anio}_{mes:02d}.tif")
    comun.escribir_tif(ruta, [comun.a_int16(c.ndvi), comun.a_int16(c.ndmi)], grilla, "int16", comun.NODATA_INDICES,
                       ["NDVI x10000", "NDMI x10000 (B8A)"])
    parametros = {"producto": "mensual", "mes": f"{anio}-{mes:02d}", "grilla": grilla.como_dict(), "metodo": metodo.como_dict()}
    comun.escribir_procedencia(ruta, "Sentinel-2 L2A, AWS (Earth Search), compuesto mensual", parametros,
                               {"n_escenas": len(c.escenas), "fechas": c.fechas, "escenas": c.escenas,
                                "celdas_sin_dato_pct": round(100 * float(np.mean(~np.isfinite(c.ndvi))), 3)})
    return {"ruta": str(ruta), "n_escenas": len(c.escenas), "fechas": c.fechas, "segundos": c.segundos}


def _metadatos(c: Compuesto, parametros: dict, grilla: Grilla) -> dict:
    return {"fuente": "Sentinel-2 L2A (Copernicus), catálogo Earth Search de Element 84 en AWS, sin clave",
            "licencia": "datos Copernicus Sentinel, uso libre con atribución", "generado_utc": comun.ahora_utc(),
            "parametros": parametros, "n_escenas": len(c.escenas), "fechas": c.fechas, "escenas": c.escenas,
            "escenas_de_cache": c.de_cache, "segundos": c.segundos,
            "celdas_sin_dato_pct": round(100 * float(np.mean(~np.isfinite(c.ndvi))), 3),
            "codificacion": "int16 x 10000, nodata -32768"}
