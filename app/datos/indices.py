"""Tomas de índices para una corrida en tiempo real: compuesto de ventana por AWS, por Google Earth Engine o cargado a mano.

Una toma es una carpeta de la caché `datos/procesados/app/indices/<id>/` con `ndvi_<id>.tif`, `ndmi_<id>.tif` y un
`info.json` que lee el servidor. Los TIF quedan en el formato de `gee_indices.py` de v3.1 (int16 × 10000, nodata −32768), a
20 m en la grilla de índices (AWS y GEE) o a 30 m en la grilla del dominio (carga manual). Al armar el evento, la función de
v3.1 `generar_mapa_combustibles` los lleva a 30 m por promedio, igual con cualquiera de los tres.

Ventana en tiempo real (plan §4.3): los 45 días que terminan el día anterior a la corrida.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import shutil
from pathlib import Path

import numpy as np

from . import comun

DIAS_VENTANA = 45
# La vía AWS queda "en prueba" hasta que E-E3-2 se cumpla (D-E3-24, punto 21). Se cambia a False al aprobarse.
AWS_EN_PRUEBA = True


def dir_tomas() -> Path:
    return comun.dir_cache("indices")


def ventana_para(fecha_corrida: dt.date, dias: int = DIAS_VENTANA) -> tuple[dt.date, dt.date]:
    """(primer día, último día) inclusive: `dias` días que terminan el día anterior a `fecha_corrida`."""
    hasta = fecha_corrida - dt.timedelta(days=1)
    return hasta - dt.timedelta(days=dias - 1), hasta


def _info(id_: str, carpeta: Path, fuente: str, rotulo: str, extra: dict) -> dict:
    info = {"id": id_, "tipo": "indices", "fuente": fuente, "rotulo": rotulo, "creada_utc": comun.ahora_utc(),
            "ndvi": f"ndvi_{id_}.tif", "ndmi": f"ndmi_{id_}.tif",
            "sha256": {k: comun.sha256(carpeta / f"{k}_{id_}.tif") for k in ("ndvi", "ndmi")}} | extra
    comun.escribir_json(carpeta / "info.json", info)
    return info


# ------------------------------------------------------------------ AWS
def toma_aws(fecha_corrida: dt.date, progreso=None, dias: int = DIAS_VENTANA) -> dict:
    from . import sentinel2 as s2
    desde, hasta = ventana_para(fecha_corrida, dias)
    id_ = f"I-{hasta:%Y%m%d}-aws"
    carpeta = dir_tomas() / id_
    tmp = carpeta.with_name(carpeta.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    r = s2.compuesto_ventana(desde, hasta, tmp, id_, progreso=progreso or s2._sin_progreso)
    shutil.rmtree(carpeta, ignore_errors=True)
    tmp.rename(carpeta)
    meta = comun.leer_json(carpeta / f"metadatos_{id_}.json", {})
    rotulo = "Sentinel-2 por AWS" + (" (en prueba hasta E-E3-2)" if AWS_EN_PRUEBA else "")
    return _info(id_, carpeta, "Sentinel-2 L2A, AWS (Earth Search), compuesto de ventana, máscara SCL", rotulo,
                 {"via": "aws", "en_prueba": AWS_EN_PRUEBA, "ventana": [f"{desde}", f"{hasta}"], "dias": dias,
                  "ndmi_nir": "B08", "resolucion_m": 20, "n_escenas": r["n_escenas"], "fechas": r["fechas"],
                  "ultima_fecha": r["fechas"][-1] if r["fechas"] else None, "segundos": r["segundos"],
                  "escenas": meta.get("escenas"), "celdas_sin_dato_pct": meta.get("celdas_sin_dato_pct"),
                  "metodo": (meta.get("parametros") or {}).get("metodo")})


# ------------------------------------------------------------------ Google Earth Engine (opcional)
def gee_disponible() -> tuple[bool, str]:
    """(disponible, motivo). Hace falta la biblioteca `earthengine-api` y credenciales (`earthengine authenticate`)."""
    try:
        import ee  # noqa: F401
    except ImportError:
        return False, "falta la biblioteca earthengine-api (opcional: pip install earthengine-api==1.7.43)"
    cred = Path.home() / ".config" / "earthengine" / "credentials"
    if not cred.exists():
        return False, "faltan las credenciales de Earth Engine (ejecutar: earthengine authenticate)"
    return True, "credenciales de Earth Engine presentes"


def toma_gee(fecha_corrida: dt.date, dias: int = DIAS_VENTANA) -> dict:
    """Compuesto de ventana con el código congelado de v3.1 (`gee_indices.obtener_indices`): Sentinel-2 SR armonizado,
    Cloud Score+ ≥ 0,6, mediana, 20 m. Corre en el proceso de datos (camino de v3.1)."""
    ok, motivo = gee_disponible()
    if not ok:
        raise RuntimeError(motivo)
    from incendios_sl import config as cfgmod                     # v3.1
    from incendios_sl.data import preparar_dominio as pdm
    from incendios_sl.remote_sensing.gee_indices import obtener_indices
    desde, hasta = ventana_para(fecha_corrida, dias)
    id_ = f"I-{hasta:%Y%m%d}-gee"
    dom = cfgmod.cargar_dominio(comun.dominio_yaml()["id"])
    ev = {"id": id_, "indices": {"coleccion": "COPERNICUS/S2_SR_HARMONIZED", "umbral_cs_cdf": 0.6,
                                 "ventana": [f"{desde}", f"{hasta + dt.timedelta(days=1)}"]}}   # GEE: fin excluido
    r = obtener_indices(ev, pdm.grilla_indices(dom), escala=20.0)
    carpeta = dir_tomas() / id_
    shutil.rmtree(carpeta, ignore_errors=True)
    carpeta.mkdir(parents=True)
    for k in ("ndvi", "ndmi", "n_obs"):
        shutil.copy(r[k], carpeta / f"{k}_{id_}.tif")
    meta = comun.leer_json(r["metadatos"], {})
    shutil.copy(r["metadatos"], carpeta / f"metadatos_{id_}.json")
    return _info(id_, carpeta, "Sentinel-2 SR armonizado por Google Earth Engine, Cloud Score+ >= 0,6 (gee_indices.py de v3.1)",
                 "Sentinel-2 por Google Earth Engine",
                 {"via": "gee", "en_prueba": False, "ventana": [f"{desde}", f"{hasta}"], "dias": dias, "ndmi_nir": "B08",
                  "resolucion_m": 20, "n_escenas": meta.get("n_escenas"), "escenas": meta.get("escenas")})


# ------------------------------------------------------------------ TIF cargado a mano
def leer_tif_manual(ruta: Path, nombre: str) -> np.ndarray:
    """Un índice cargado a mano: grilla exacta del dominio (forma, transformación y CRS), int16 × 10000 con nodata
    −32768 y valores entre −1 y 1. Devuelve la banda int16."""
    import rasterio
    g = comun.grilla_dominio()
    try:
        s = rasterio.open(ruta)
    except Exception as e:
        raise ValueError(f"{nombre}: no es un GeoTIFF legible ({e})")
    with s:
        if s.count != 1:
            raise ValueError(f"{nombre}: tiene {s.count} bandas; se espera una")
        if s.crs is None or s.crs.to_epsg() != int(g.crs.split(":")[1]):
            raise ValueError(f"{nombre}: el sistema de coordenadas es {s.crs}; se espera {g.crs}")
        if (s.height, s.width) != g.forma:
            raise ValueError(f"{nombre}: mide {s.height} × {s.width} celdas; la grilla del dominio es {g.forma[0]} × {g.forma[1]}")
        if not s.transform.almost_equals(g.transform, precision=1e-6):
            raise ValueError(f"{nombre}: la transformación {tuple(s.transform)[:6]} no coincide con la del dominio "
                             f"{tuple(g.transform)[:6]}")
        if s.dtypes[0] != "int16":
            raise ValueError(f"{nombre}: el tipo es {s.dtypes[0]}; se espera int16 (índice × 10000)")
        if s.nodata is None or int(s.nodata) != comun.NODATA_INDICES:
            raise ValueError(f"{nombre}: el valor sin dato es {s.nodata}; se espera {comun.NODATA_INDICES}")
        a = s.read(1)
    validos = a[a != comun.NODATA_INDICES]
    if validos.size == 0:
        raise ValueError(f"{nombre}: no tiene ninguna celda con dato")
    if validos.min() < -comun.ESCALA_INDICES or validos.max() > comun.ESCALA_INDICES:
        raise ValueError(f"{nombre}: valores fuera de −10000 a 10000 (índice × 10000): {int(validos.min())} a {int(validos.max())}")
    return a


def toma_manual(ruta_ndvi: Path, ruta_ndmi: Path, ventana: list[str], ndmi_nir: str, nombre_ndvi: str, nombre_ndmi: str,
                descripcion: str = "") -> dict:
    """Índices cargados a mano. La ventana de fechas y la banda del NDMI las declara quien carga: el programa no las puede
    comprobar, así que se guardan tal cual y la corrida queda rotulada."""
    if ndmi_nir not in ("B08", "B8A"):
        raise ValueError("ndmi_nir: B08 o B8A")
    try:
        desde, hasta = (dt.date.fromisoformat(str(x)) for x in ventana)
    except (ValueError, TypeError):
        raise ValueError("ventana: dos fechas AAAA-MM-DD (primer y último día)")
    if hasta < desde:
        raise ValueError("ventana: el último día es anterior al primero")
    ndvi = leer_tif_manual(ruta_ndvi, nombre_ndvi)
    ndmi = leer_tif_manual(ruta_ndmi, nombre_ndmi)
    sha = hashlib.sha256(ndvi.tobytes() + ndmi.tobytes()).hexdigest()
    id_ = f"I-{hasta:%Y%m%d}-manual-{sha[:6]}"
    carpeta = dir_tomas() / id_
    shutil.rmtree(carpeta, ignore_errors=True)
    carpeta.mkdir(parents=True)
    g = comun.grilla_dominio()
    comun.escribir_tif(carpeta / f"ndvi_{id_}.tif", [ndvi], g, "int16", comun.NODATA_INDICES, ["NDVI x10000"])
    comun.escribir_tif(carpeta / f"ndmi_{id_}.tif", [ndmi], g, "int16", comun.NODATA_INDICES, [f"NDMI x10000 ({ndmi_nir})"])
    return _info(id_, carpeta, f"TIF cargados a mano ({nombre_ndvi}, {nombre_ndmi})", "índices cargados a mano",
                 {"via": "manual", "en_prueba": False, "ventana": [f"{desde}", f"{hasta}"], "ndmi_nir": ndmi_nir,
                  "declarado_por_quien_carga": ["ventana", "ndmi_nir"], "descripcion": descripcion, "resolucion_m": 30,
                  "celdas_sin_dato_pct": round(100 * float(np.mean(ndvi == comun.NODATA_INDICES)), 3),
                  "aviso": "ventana y fórmula del NDMI declaradas por quien cargó los archivos; el programa no las comprueba"})


def tomas() -> list[dict]:
    out = [comun.leer_json(p) for p in dir_tomas().glob("I-*/info.json")]
    return sorted([o for o in out if o], key=lambda o: o.get("creada_utc", ""), reverse=True)
