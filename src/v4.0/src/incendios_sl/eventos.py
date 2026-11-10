"""De una ficha de evento de v3.0 (escenarios/v4.0/eventos/<id>.yaml) a los insumos de SIM.

Los insumos se derivan de los productos de v3.0 en `datos/inputSimulacion` y quedan en caché, regenerables, en
`datos/procesados/v4.0/<evento>/`, cada uno con un `<archivo>.json` hermano de procedencia (fuentes con tamaño y fecha,
parámetros); si cambia una fuente o un parámetro el producto se vuelve a generar:

| Insumo de SIM | Origen |
| --- | --- |
| `meteo_horaria.csv` | último `meteo/<ev>_*_dominio.csv` (promedio del dominio, Open-Meteo) en el formato exacto de SIM: `timestamp` ISO con huso −03:00, `temp_c`, `hr_pct`, `viento_kmh` = m/s·3,6 (velocidad vectorial, como v3.0), `viento_dir_deg` (desde donde sopla), `precip_mm` (hora que termina en `timestamp`), `fuente` |
| `combustible_pre_evento.tif` | regla 3.3 de SIM (`scripts/preparar_datos.py`, `app/motores/sim_adaptador.py` de V.4) con `simulador.fuel.generar_sb40.generar`: cobertura MapBiomas del año anterior al evento (o `cobertura_anio` de la ficha si es anterior) + MDT + **mediana NDVI/NDMI de enero–marzo** (verano) con los compuestos mensuales de SIM + terciles `umbrales_ndvi.csv` (calibrados en verano) |
| `indices_mes_evento.tif` | el compuesto S2 pre-evento de v3.0 (`combustibles/<ev>/ndvi_30m`, `ndmi_30m`) en 2 bandas int16 ×10000, nodata −32768 |
| `ndvi_verano_previo.tif` | la misma mediana NDVI de enero–marzo (curado del herbáceo); sin ningún mes de verano no se genera y SIM usa el curado de Scott y Burgan |

Verano (`indices_verano`): enero–marzo del año del evento; si el evento es de enero–marzo, el del año anterior (el
compuesto del año del evento incluiría escenas posteriores a la ignición). Compuestos `NDVI_NDMI_AAAA_MM.tif` (2 bandas
×10000) de `sim_v4/dinamicos/indices/` o, si no están, de `banco_v4/entradas/indices_extra/` (mismo método, E020 de V.4).
Respaldo documentado (con aviso en el log y `regla_indices` en la procedencia): si falta algún mes se usa la mediana de los
meses que haya (`verano_parcial`); si no hay ninguno, el compuesto pre-evento de v3.0 (`respaldo_compuesto_evento`, el
comportamiento de la primera integración: con un compuesto de invierno los terciles de verano clasifican de más en el tercil bajo).
| `perimetro_observado.geojson` | `eventos/<ev>/cicatriz_referencia_<ev>.tif` poligonizada, con `fecha` y `fuente` |
| `focos_viirs.geojson` | `catalogo/hotspots/viirs_<ev>.csv` (si existe y no está vacío): `hora_deteccion` UTC = fecha + `acq_time_s`, `frp` |

Igniciones: los puntos `ignicion` (snmf) o `ignicion_alternativas[N]` (altN) con la hora `inicio.hora_utc_hipotesis[h]`.
Como en v3.0, un punto que cae fuera de la grilla o en una celda no combustible se desplaza (HIPÓTESIS) a la celda
combustible más cercana, dentro de la cicatriz de referencia si existe. La corrida va de t0 a `fin.fin_simulacion_utc`
(o `horas`, si es menor) y se verifica que la serie meteorológica la cubra.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from . import config as cfgmod

log = logging.getLogger(__name__)

HUSO_SIM = dt.timezone(dt.timedelta(hours=-3))      # San Luis: UTC−3 sin horario de verano
COLUMNAS_METEO_SIM = ["timestamp", "temp_c", "hr_pct", "viento_kmh", "viento_dir_deg", "precip_mm", "fuente"]
NODATA_INDICES = -32768
VERSION_INSUMOS = "1.0"
# versión de la regla del combustible pre-evento y del NDVI de verano (va en los parámetros de la procedencia: si cambia,
# la caché vieja deja de estar vigente). "3.3-verano" = regla 3.3 de V.4; la caché sin esta clave (índices del
# compuesto del evento, invierno) se regenera sola.
VERSION_COMBUSTIBLE = "3.3-verano"
MESES_VERANO = (1, 2, 3)


# ---------------------------------------------------------------------------------------------------------- rutas
def dir_evento(id_evento: str) -> Path:
    d = cfgmod.dir_procesados() / cfgmod.VERSION_RESULTADOS / id_evento
    d.mkdir(parents=True, exist_ok=True)
    return d


def _raiz_sim() -> Path:
    from simulador.rutas import raiz_datos
    return raiz_datos()


def _manifiesto():
    from simulador.io.manifiesto import Manifiesto
    return Manifiesto.cargar(_raiz_sim() / "manifiesto_datos.yaml")


def ruta_meteo_v3(id_evento: str) -> Path:
    """Último `meteo/<ev>_*_dominio.csv` en orden alfabético (como v3.0 `entradas.ruta_producto`)."""
    patron = str(cfgmod.dir_entradas() / "meteo" / f"{id_evento}_*_dominio.csv")
    c = sorted(glob.glob(patron))
    if not c:
        partes = sorted(glob.glob(patron + ".part*"))
        if partes:
            return cfgmod.unir_partes(Path(partes[0]).with_suffix(""))
        raise FileNotFoundError(f"no existe la meteorología {patron} (src/v3.0/scripts/preparar_evento.py)")
    return Path(c[-1])


# ------------------------------------------------------------------------------------------------- procedencia
def _firma(p: Path) -> dict[str, Any]:
    p = Path(p); s = p.stat()
    return {"archivo": _rel(p), "bytes": int(s.st_size), "mtime": round(s.st_mtime, 3)}


def _rel(p: Path) -> str:
    p = Path(p).resolve()
    try:
        return p.relative_to(cfgmod.raiz_repositorio()).as_posix()
    except ValueError:
        return p.as_posix()


def _vigente(producto: Path, fuentes: list[Path], parametros: dict[str, Any]) -> bool:
    j = Path(str(producto) + ".json")
    if not (producto.exists() and j.exists()):
        return False
    try:
        d = json.loads(j.read_text(encoding="utf-8"))
    except Exception:
        return False
    return d.get("entradas") == [_firma(f) for f in fuentes] and d.get("parametros") == parametros and d.get("version") == VERSION_INSUMOS


def _procedencia(producto: Path, fuentes: list[Path], parametros: dict[str, Any], descripcion: str, extra: dict | None = None) -> None:
    d = {"producto": producto.name, "descripcion": descripcion, "version": VERSION_INSUMOS,
         "generado": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "codigo": "incendios_sl.eventos (v4.0)",
         "parametros": parametros, "entradas": [_firma(f) for f in fuentes]} | (extra or {})
    Path(str(producto) + ".json").write_text(json.dumps(d, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


# ------------------------------------------------------------------------------------------------- meteorología
def convertir_meteo(df: pd.DataFrame, fuente: str = "openmeteo_dominio") -> pd.DataFrame:
    """Serie del dominio de v3.0 (time_utc, temperature_2m, relative_humidity_2m, wind_speed_10m[_vectorial] en m/s,
    wind_direction_10m, precipitation) → CSV estándar de SIM. Se rellenan por interpolación huecos de hasta 3 h."""
    t = pd.to_datetime(df["time_utc"], utc=True)
    vel = df["wind_speed_10m_vectorial"] if "wind_speed_10m_vectorial" in df else df["wind_speed_10m"]
    rad = np.deg2rad(df["wind_direction_10m"].to_numpy(float))
    x = pd.DataFrame({"temp_c": df["temperature_2m"].to_numpy(float), "hr_pct": df["relative_humidity_2m"].to_numpy(float),
                      "u": -vel.to_numpy(float) * np.sin(rad), "v": -vel.to_numpy(float) * np.cos(rad),
                      "precip_mm": df["precipitation"].to_numpy(float)}, index=t).sort_index()
    x = x[~x.index.duplicated()]
    x = x.reindex(pd.date_range(x.index[0], x.index[-1], freq="1h")).interpolate(limit=3, limit_area="inside")
    if x.isna().any().any():
        raise ValueError(f"la serie meteorológica tiene huecos de más de 3 h: {x.index[x.isna().any(axis=1)][:3].tolist()}")
    vkmh = np.hypot(x["u"], x["v"]) * 3.6
    desde = (np.degrees(np.arctan2(-x["u"], -x["v"])) + 360.0) % 360.0      # dirección desde donde sopla
    return pd.DataFrame({
        "timestamp": [ts.tz_convert(HUSO_SIM).isoformat() for ts in x.index],
        "temp_c": x["temp_c"].round(2).to_numpy(), "hr_pct": x["hr_pct"].clip(0, 100).round(2).to_numpy(),
        "viento_kmh": vkmh.round(3).to_numpy(), "viento_dir_deg": desde.round(2).to_numpy(),
        "precip_mm": x["precip_mm"].clip(lower=0).round(3).to_numpy(), "fuente": fuente})


def preparar_meteo(id_evento: str, ficha: dict, forzar: bool = False) -> Path:
    src = ruta_meteo_v3(id_evento)
    out = dir_evento(id_evento) / "meteo_horaria.csv"
    modelo = str((ficha.get("meteorologia") or {}).get("modelo", "openmeteo"))
    par = {"fuente": src.name, "modelo": modelo, "viento": "vectorial m/s × 3,6"}
    if forzar or not _vigente(out, [src], par):
        df = convertir_meteo(pd.read_csv(src), fuente=f"{modelo}_openmeteo_dominio")
        df[COLUMNAS_METEO_SIM].to_csv(out, index=False, encoding="utf-8", lineterminator="\n")
        from simulador.io.manifiesto import validar_meteo_csv
        validar_meteo_csv(out)
        _procedencia(out, [src], par, "serie horaria de SIM (promedio del dominio de v3.0)",
                     {"inicio": df["timestamp"].iloc[0], "fin": df["timestamp"].iloc[-1], "horas": int(len(df))})
    return out


# ------------------------------------------------------------------------------------------------- rásteres
def _leer(p: Path, nodata_a_nan: bool = True) -> tuple[np.ndarray, dict]:
    import rasterio
    with rasterio.open(p) as s:
        a = s.read(1); perfil = s.profile.copy(); nd = s.nodata
    if nodata_a_nan and a.dtype.kind == "f":
        a = np.where(a == nd, np.nan, a) if nd is not None else a
    return a, perfil


def _grilla_sim():
    return _manifiesto().grilla


def _verificar_grilla(p: Path) -> None:
    import rasterio
    with rasterio.open(p) as s:
        _grilla_sim().verificar_raster(s, p.name)


def _escribir(p: Path, bandas: list[np.ndarray], dtype: str, nodata, descripciones: list[str]) -> None:
    import rasterio
    from rasterio.crs import CRS
    g = _grilla_sim()
    perfil = dict(driver="GTiff", height=g.alto, width=g.ancho, count=len(bandas), dtype=dtype, crs=CRS.from_user_input(g.crs),
                  transform=g.transform, nodata=nodata, compress="deflate", tiled=True)
    # escritura atómica: dos corridas del mismo evento en paralelo no dejan un GeoTIFF a medio escribir en la caché
    import os
    tmp = p.with_name(f"{p.stem}.{os.getpid()}.tmp{p.suffix}")
    with rasterio.open(tmp, "w", **perfil) as dst:
        for i, (b, d) in enumerate(zip(bandas, descripciones), start=1):
            dst.write(b.astype(dtype), i); dst.set_band_description(i, d)
    os.replace(tmp, p)


def _fuentes_indices(id_evento: str) -> tuple[Path, Path]:
    C = cfgmod.dir_entradas() / "combustibles" / id_evento
    p_ndvi, p_ndmi = C / f"ndvi_30m_{id_evento}.tif", C / f"ndmi_30m_{id_evento}.tif"
    for p in (p_ndvi, p_ndmi):
        if not cfgmod.unir_partes(p).exists():
            raise FileNotFoundError(f"falta {p} (src/v3.0/scripts/obtener_indices.py)")
    return p_ndvi, p_ndmi


def fecha_evento(ficha: dict) -> pd.Timestamp:
    """Fecha local del evento: `inicio.fecha_local` o el día de la primera hipótesis de hora."""
    ini = ficha.get("inicio") or {}
    return pd.Timestamp(str(ini.get("fecha_local") or ini["hora_utc_hipotesis"][0])[:10])


def anio_cobertura(ficha: dict) -> int:
    """Regla 3.3: cobertura del año anterior al evento, o `cobertura_anio` de la ficha si es anterior."""
    a = fecha_evento(ficha).year - 1
    return min(a, int(ficha["cobertura_anio"])) if ficha.get("cobertura_anio") is not None else a


def dirs_compuestos() -> list[Path]:
    """Carpetas de compuestos mensuales NDVI/NDMI (2 bandas ×10000), en orden de preferencia."""
    return [_raiz_sim() / "dinamicos" / "indices", cfgmod.dir_entradas() / "banco_v4" / "entradas" / "indices_extra"]


def ruta_compuesto(anio: int, mes: int) -> Path | None:
    """`NDVI_NDMI_AAAA_MM.tif` de la entrega de SIM o, si no está, el generado con el mismo método (indices_extra)."""
    for d in dirs_compuestos():
        p = cfgmod.unir_partes(d / f"NDVI_NDMI_{anio}_{mes:02d}.tif")
        if p.exists():
            return p
    return None


def indices_verano(ficha: dict) -> dict[str, Any]:
    """Verano de la regla 3.3: {anio, meses, fuentes, faltan, regla}. `regla` = `verano` (los 3 meses), `verano_parcial`
    (mediana de los que haya) o `respaldo_compuesto_evento` (ninguno: compuesto pre-evento de v3.0)."""
    f = fecha_evento(ficha)
    anio = f.year if f.month > max(MESES_VERANO) else f.year - 1      # evento en verano: el verano anterior (sin fuga)
    rutas = {m: ruta_compuesto(anio, m) for m in MESES_VERANO}
    meses = [m for m, p in rutas.items() if p is not None]
    faltan = [f"{anio}-{m:02d}" for m, p in rutas.items() if p is None]
    regla = "verano" if not faltan else ("verano_parcial" if meses else "respaldo_compuesto_evento")
    return {"anio": anio, "meses": meses, "fuentes": [rutas[m] for m in meses], "faltan": faltan, "regla": regla}


def mediana_verano(fuentes: list[Path]) -> tuple[np.ndarray, np.ndarray]:
    """(NDVI, NDMI) mediana por celda de los compuestos mensuales (float, NaN sin dato), como `sim_adaptador.preparar`."""
    import rasterio
    import warnings
    nd, nm = [], []
    for p in fuentes:
        with rasterio.open(p) as s:
            _grilla_sim().verificar_raster(s, Path(p).name)
            a = s.read().astype("float32"); a[a == s.nodata] = np.nan
        nd.append(a[0] / 10000); nm.append(a[1] / 10000)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)          # celdas sin dato en todos los meses
        return np.nanmedian(nd, 0), np.nanmedian(nm, 0)


def _avisar_verano(id_evento: str, v: dict) -> None:
    if v["regla"] == "verano_parcial":
        log.warning("%s: faltan compuestos de verano %s; combustible pre-evento con la mediana de %s (respaldo)",
                    id_evento, ", ".join(v["faltan"]), ", ".join(f"{v['anio']}-{m:02d}" for m in v["meses"]))
    elif v["regla"] == "respaldo_compuesto_evento":
        log.warning("%s: no hay compuestos de verano %s (%s); RESPALDO: combustible con el compuesto pre-evento de v3.0 "
                    "(fuera de verano los terciles de umbrales_ndvi.csv sesgan al tercil bajo) y sin ndvi_verano",
                    id_evento, v["anio"], ", ".join(v["faltan"]))


REGLAS_COMBUSTIBLE = ("3.3", "3.3b", "3.3c")
# caché por regla; 3.3c = 3.3b + pasturas (MapBiomas 15) → GR1 (docs/v4.0/24, en prueba)
ARCHIVO_COMBUSTIBLE = {"3.3": "combustible_pre_evento.tif", "3.3b": "combustible_pre_evento_33b.tif", "3.3c": "combustible_pre_evento_33c.tif"}


def preparar_combustible(id_evento: str, ficha: dict, forzar: bool = False, regla: str = "3.3") -> Path:
    """Combustible pre-evento. `regla` 3.3 (V.4), 3.3b (NDVI estructural de las leñosas sin la anomalía interanual del
    verano, docs/v4.0/17) o 3.3c (3.3b + pasturas → GR1, docs/v4.0/24): un archivo de caché por regla (`ARCHIVO_COMBUSTIBLE`)."""
    from simulador.fuel.generar_sb40 import generar, ndvi_estructural_anomalia, NODATA
    if regla not in REGLAS_COMBUSTIBLE:
        raise ValueError(f"regla_combustible {regla!r} desconocida: {' | '.join(REGLAS_COMBUSTIBLE)}")
    dom = ficha["dominio"]; anio = anio_cobertura(ficha)
    p_lc = cfgmod.dir_entradas() / "cobertura" / f"cobertura_mapbiomas_col3_{anio}_{dom}.tif"
    if not p_lc.exists():
        raise FileNotFoundError(f"falta la cobertura {p_lc}")
    man = _manifiesto()
    p_mdt = man.ruta("mdt")
    p_umb = man.ruta("umbrales_ndvi") if "umbrales_ndvi" in man.entradas else _raiz_sim() / "estaticos" / "combustible" / "umbrales_ndvi.csv"
    v = indices_verano(ficha)
    _avisar_verano(id_evento, v)
    p_ind = v["fuentes"] if v["fuentes"] else list(_fuentes_indices(id_evento))
    out = dir_evento(id_evento) / ARCHIVO_COMBUSTIBLE[regla]
    par = {"version_regla": VERSION_COMBUSTIBLE, "regla_combustible": regla, "cobertura_anio": anio, "verano_anio": v["anio"], "meses_verano": v["meses"],
           "regla_indices": v["regla"], "regla": "generar_sb40 (MapBiomas año anterior + MDT + mediana NDVI/NDMI ene–mar, regla 3.3)"}
    fuentes = [p_lc, p_mdt, *p_ind, p_umb]
    if forzar or not _vigente(out, fuentes, par):
        _verificar_grilla(p_lc)
        lc, _ = _leer(p_lc, False); dem, _ = _leer(p_mdt, False)
        if v["fuentes"]:
            ndvi, ndmi = mediana_verano(v["fuentes"])
        else:
            for p in p_ind:
                _verificar_grilla(p)
            ndvi, ndmi = (_leer(p)[0].astype("float32") for p in p_ind)
        umb = pd.read_csv(p_umb, encoding="utf-8")
        corr = {}
        if regla in ("3.3b", "3.3c"):
            est, corr = ndvi_estructural_anomalia(lc, ndvi, umb)
            comb = generar(lc, dem, ndvi, ndmi, umb, ndvi_estructural=est, pasturas_gr1=(regla == "3.3c"))
        else:
            comb = generar(lc, dem, ndvi, ndmi, umb)
        _escribir(out, [comb], "int16", NODATA, ["modelo Scott & Burgan (FBFM40) pre-evento"])
        cod, n = np.unique(comb, return_counts=True)
        _procedencia(out, fuentes, par, f"combustible pre-evento (regla {regla} de SIM: cobertura {anio} + verano {v['anio']}, {v['regla']})",
                     {"conteo_codigos": {int(c): int(k) for c, k in zip(cod, n)}, "faltan_meses": v["faltan"],
                      "corrimiento_ndvi_lenosas": {str(k): x for k, x in corr.items()}})
    return out


def preparar_indices(id_evento: str, forzar: bool = False) -> Path:
    p_ndvi, p_ndmi = _fuentes_indices(id_evento)
    out = dir_evento(id_evento) / "indices_mes_evento.tif"
    par = {"escala": 10000, "nodata": NODATA_INDICES, "bandas": ["NDVI", "NDMI"]}
    if forzar or not _vigente(out, [p_ndvi, p_ndmi], par):
        bandas = []
        for p in (p_ndvi, p_ndmi):
            _verificar_grilla(p)
            a, _ = _leer(p)
            bandas.append(np.where(np.isfinite(a), np.clip(np.round(a * 10000.0), -10000, 10000), NODATA_INDICES))
        _escribir(out, bandas, "int16", NODATA_INDICES, ["NDVI x10000", "NDMI x10000"])
        _procedencia(out, [p_ndvi, p_ndmi], par, "NDVI/NDMI del compuesto Sentinel-2 pre-evento de v3.0 (2 bandas ×10000)")
    return out


def preparar_ndvi_verano(id_evento: str, ficha: dict, forzar: bool = False) -> Path | None:
    """Mediana del NDVI de enero–marzo (`indices_verano`, la misma del combustible); None si no hay ningún mes."""
    v = indices_verano(ficha)
    if not v["fuentes"]:
        return None
    out = dir_evento(id_evento) / "ndvi_verano_previo.tif"
    par = {"version_regla": VERSION_COMBUSTIBLE, "anio": v["anio"], "meses": v["meses"], "regla_indices": v["regla"],
           "estadistico": "mediana", "escala": 10000}
    if forzar or not _vigente(out, v["fuentes"], par):
        ndvi, _ = mediana_verano(v["fuentes"])
        _escribir(out, [np.where(np.isnan(ndvi), NODATA_INDICES, np.round(ndvi * 10000))], "int16", NODATA_INDICES,
                  [f"NDVI x10000 mediana ene-mar {v['anio']}"])
        _procedencia(out, v["fuentes"], par, "NDVI de verano previo (curado del herbáceo en SIM)", {"faltan_meses": v["faltan"]})
    return out


def ruta_cicatriz(id_evento: str) -> Path:
    return cfgmod.dir_entradas() / "eventos" / id_evento / f"cicatriz_referencia_{id_evento}.tif"


def superficie_cicatriz_ha(id_evento: str, ruta_combustible: str | Path) -> float | None:
    """Superficie de la cicatriz de referencia sobre celdas combustibles (FBFM40 ≥ 101) de la grilla del combustible: la
    `ha_ref` de `resumen.metricas_evento`, lo que el autómata puede llegar a quemar (tope de `parar_en_cicatriz`).
    None si falta la cicatriz o el combustible."""
    import rasterio
    from .resumen import _leer_en
    if not ruta_combustible or not ruta_cicatriz(id_evento).exists() or not Path(ruta_combustible).is_file():
        return None
    with rasterio.open(ruta_combustible) as s:
        comb = s.read(1); tr = s.transform
    ref = _leer_en(ruta_cicatriz(id_evento), tr, comb.shape) == 1
    return round(float((ref & (comb >= 101)).sum()) * abs(tr.a * tr.e) / 1e4, 2)


def preparar_perimetro(id_evento: str, ficha: dict, forzar: bool = False) -> Path | None:
    src = ruta_cicatriz(id_evento)
    if not src.exists():
        return None
    out = dir_evento(id_evento) / "perimetro_observado.geojson"
    fin = ficha.get("fin") or {}
    fecha = fin.get("fecha_extincion_snmf") or (str(fin.get("evaluacion_utc", [""])[-1])[:10] or None)
    fuente = (ficha.get("referencia_espacial") or {}).get("fuente", "cicatriz de referencia de v3.0")
    par = {"fecha": fecha, "fuente": fuente}
    if forzar or not _vigente(out, [src], par):
        import geopandas as gpd
        import rasterio
        from rasterio import features
        from shapely.geometry import shape
        from shapely.ops import unary_union
        with rasterio.open(src) as s:
            a = s.read(1); tr = s.transform; crs = s.crs
        geoms = [shape(g) for g, v in features.shapes(a.astype("uint8"), mask=a == 1, transform=tr) if v == 1]
        pol = unary_union(geoms) if geoms else None
        ha = float((a == 1).sum()) * abs(tr.a * tr.e) / 1e4
        gdf = gpd.GeoDataFrame([{"fecha": fecha, "fuente": fuente, "evento": id_evento, "ha": round(ha, 2)}],
                               geometry=[pol], crs=crs).to_crs("EPSG:4326")
        gdf.to_file(out, driver="GeoJSON")
        _procedencia(out, [src], par, "perímetro observado = cicatriz de referencia de v3.0 poligonizada", {"ha": round(ha, 2)})
    return out


def leer_focos_csv(p: Path) -> pd.DataFrame:
    """Focos VIIRS de v3.0 (date, sat, acq_time_s, lon, lat, frp, …) con `hora_deteccion` UTC; vacío si no hay."""
    if not Path(p).exists() or Path(p).stat().st_size < 10:
        return pd.DataFrame()
    f = pd.read_csv(p)
    if not len(f):
        return f
    seg = f["acq_time_s"].fillna(13.5 * 3600) if "acq_time_s" in f else 13.5 * 3600   # sin hora: paso de mediodía
    f["hora_deteccion"] = pd.to_datetime(f["date"]).dt.tz_localize("UTC") + pd.to_timedelta(seg, unit="s")
    return f


def preparar_focos(id_evento: str, forzar: bool = False) -> Path | None:
    src = cfgmod.dir_catalogo() / "hotspots" / f"viirs_{id_evento}.csv"
    f = leer_focos_csv(src)
    if not len(f):
        return None
    out = dir_evento(id_evento) / "focos_viirs.geojson"
    par = {"hora": "date + acq_time_s (UTC)"}
    if forzar or not _vigente(out, [src], par):
        import geopandas as gpd
        gdf = gpd.GeoDataFrame({"id": [f"VIIRS-{i:05d}" for i in range(len(f))],
                                "hora_deteccion": [t.isoformat() for t in f["hora_deteccion"]],
                                "frp": f["frp"].astype(float) if "frp" in f else np.nan,
                                "satelite": f["sat"].astype(str) if "sat" in f else ""},
                               geometry=gpd.points_from_xy(f["lon"], f["lat"]), crs="EPSG:4326")
        gdf.to_file(out, driver="GeoJSON")
        _procedencia(out, [src], par, "focos VIIRS del catálogo de v3.0", {"n": int(len(gdf))})
    return out


def preparar_evento(id_evento: str, forzar: bool = False, regla_combustible: str = "3.3") -> dict[str, Path | None]:
    """Genera (o reutiliza de la caché) todos los insumos de SIM del evento. Devuelve sus rutas."""
    ficha = cfgmod.cargar_evento(id_evento)
    return {"meteo": preparar_meteo(id_evento, ficha, forzar),
            "combustible": preparar_combustible(id_evento, ficha, forzar, regla_combustible),
            "indices_mes_evento": preparar_indices(id_evento, forzar),
            "ndvi_verano": preparar_ndvi_verano(id_evento, ficha, forzar),
            "perimetro_observado": preparar_perimetro(id_evento, ficha, forzar),
            "focos": preparar_focos(id_evento, forzar)}


# ------------------------------------------------------------------------------------------------- ignición y tiempos
def puntos_ignicion(ficha: dict, ignicion: str = "snmf") -> tuple[list[dict[str, Any]], str]:
    """Puntos {nombre, lon, lat} y fuente: `snmf` = ficha.ignicion; `altN` = ficha.ignicion_alternativas[N]."""
    ign = str(ignicion or "snmf")
    if ign == "snmf":
        b = ficha["ignicion"]
    elif ign.startswith("alt") and ign[3:].isdigit():
        alts = ficha.get("ignicion_alternativas") or []
        k = int(ign[3:])
        if k >= len(alts):
            raise ValueError(f"{ficha.get('id')}: no existe la ignición {ign} (hay {len(alts)} alternativas: "
                             f"{', '.join(f'alt{i}' for i in range(len(alts))) or 'ninguna'})")
        b = alts[k]
    else:
        raise ValueError(f"ignicion {ign!r} inválida: snmf | alt0 | alt1 …")
    return [dict(p) for p in b["puntos"]], str(b.get("fuente", ""))


def tiempos(ficha: dict, hipotesis: int = 0, horas: float | None = None) -> tuple[pd.Timestamp, pd.Timestamp]:
    """(t0, t_fin) en UTC: t0 = inicio.hora_utc_hipotesis[h]; t_fin = fin.fin_simulacion_utc o t0 + horas (lo menor)."""
    hs = (ficha.get("inicio") or {}).get("hora_utc_hipotesis") or []
    h = int(hipotesis or 0)
    if not 0 <= h < len(hs):
        raise ValueError(f"{ficha.get('id')}: hipótesis {h} fuera de rango (hay {len(hs)} horas: {hs})")
    t0 = pd.Timestamp(hs[h]).tz_convert("UTC")
    t_fin = pd.Timestamp(ficha["fin"]["fin_simulacion_utc"]).tz_convert("UTC")
    if horas:
        t_fin = min(t_fin, t0 + pd.Timedelta(hours=float(horas)))
    if t_fin <= t0:
        raise ValueError(f"{ficha.get('id')}: fin de la simulación ({t_fin}) no posterior a t0 ({t0})")
    return t0, t_fin


def igniciones(ficha: dict, hipotesis: int = 0, ignicion: str = "snmf", combustible: Path | None = None,
               cicatriz: Path | None = None) -> list[dict[str, Any]]:
    """Lista de igniciones de SIM [{lon, lat, hora_ignicion, id}]. Con `combustible`, los puntos fuera de la grilla o
    en celdas no combustibles (NB o sin dato) se desplazan a la celda combustible más cercana (dentro de la cicatriz
    si existe), como en v3.0; el desplazamiento queda en `desplazada_m`."""
    puntos, _ = puntos_ignicion(ficha, ignicion)
    t0, _ = tiempos(ficha, hipotesis)
    hora = t0.tz_convert(HUSO_SIM).isoformat()
    out = [{"lon": float(p["lon"]), "lat": float(p["lat"]), "hora_ignicion": hora, "id": str(p.get("nombre", f"p{i}"))}
           for i, p in enumerate(puntos)]
    if combustible is None:
        return out
    from pyproj import Transformer
    g = _grilla_sim()
    comb, _ = _leer(Path(combustible), False)
    quemable = comb >= 101
    cand = quemable
    if cicatriz is not None and Path(cicatriz).exists():
        ref, _ = _leer(Path(cicatriz), False)
        if (quemable & (ref == 1)).any():
            cand = quemable & (ref == 1)
    a5345 = Transformer.from_crs("EPSG:4326", g.crs, always_xy=True)
    a4326 = Transformer.from_crs(g.crs, "EPSG:4326", always_xy=True)
    rr = cc = None
    for p in out:
        x, y = a5345.transform(p["lon"], p["lat"])
        f, c = (int(v) for v in g.indices(x, y))
        if 0 <= f < g.alto and 0 <= c < g.ancho and quemable[f, c]:
            continue
        if rr is None:
            rr, cc = np.nonzero(cand)
        k = int(np.argmin((rr - f) ** 2 + (cc - c) ** 2))
        d = float(np.hypot(rr[k] - f, cc[k] - c) * g.res)
        xn, yn = g.centros(int(rr[k]), int(cc[k]))
        p["lon"], p["lat"] = (round(v, 7) for v in a4326.transform(xn, yn))
        p["desplazada_m"] = round(d, 0)
        log.warning("ignición %s en celda no combustible o fuera de la grilla; desplazada %.0f m (HIPÓTESIS)", p["id"], d)
    return out


def verificar_meteo(ruta: Path, t0: pd.Timestamp, t_fin: pd.Timestamp) -> None:
    """La serie de SIM debe cubrir [t0, t_fin]."""
    m = pd.read_csv(ruta, usecols=["timestamp"])
    ini, fin = pd.Timestamp(m["timestamp"].iloc[0]), pd.Timestamp(m["timestamp"].iloc[-1])
    if ini > t0 or fin < t_fin:
        raise ValueError(f"la meteorología ({ini} → {fin}) no cubre la corrida ({t0} → {t_fin}); reducir `horas` o regenerar la serie")


def insumos_evento(id_evento: str, hipotesis: int = 0, ignicion: str = "snmf", horas: float | None = None,
                   preparar: bool = True, regla_combustible: str = "3.3") -> tuple[dict[str, Any], dict[str, Any]]:
    """(parte del cfg de SIM, metadatos de entrada) de un evento. Con `preparar=False` no se generan ni leen rásteres
    (rutas esperadas en la caché, igniciones sin desplazar, sin verificar la meteorología): sirve para las pruebas."""
    ficha = cfgmod.cargar_evento(id_evento)
    t0, t_fin = tiempos(ficha, hipotesis, horas)
    d = dir_evento(id_evento)
    if preparar:
        rutas = preparar_evento(id_evento, regla_combustible=regla_combustible)
        verificar_meteo(rutas["meteo"], t0, t_fin)
        ign = igniciones(ficha, hipotesis, ignicion, rutas["combustible"], ruta_cicatriz(id_evento))
    else:
        rutas = {"meteo": d / "meteo_horaria.csv",
                 "combustible": d / ARCHIVO_COMBUSTIBLE[regla_combustible],
                 "indices_mes_evento": d / "indices_mes_evento.tif", "ndvi_verano": None,
                 "perimetro_observado": d / "perimetro_observado.geojson", "focos": None}
        ign = igniciones(ficha, hipotesis, ignicion)
    puntos, fuente = puntos_ignicion(ficha, ignicion)
    cfg = {"t_inicio": t0.tz_convert(HUSO_SIM).isoformat(), "duracion_h": round((t_fin - t0).total_seconds() / 3600.0, 6),
           "ignicion": ign} | {k: (str(v) if v else None) for k, v in rutas.items()}
    meta = {"evento": ficha["id"], "nombre_evento": ficha.get("nombre"), "dominio": ficha["dominio"], "hipotesis_ignicion": int(hipotesis or 0),
            "ignicion": str(ignicion or "snmf"), "fuente_ignicion": fuente, "puntos_ignicion": puntos, "igniciones": ign,
            "t_inicio_utc": t0.isoformat(), "t_fin_utc": t_fin.isoformat(), "evaluacion_utc": (ficha.get("fin") or {}).get("evaluacion_utc", []),
            "referencia": ficha.get("referencia_espacial"), "combate": ficha.get("combate"),
            "insumos": {k: (_rel(Path(v)) if v else None) for k, v in rutas.items()}}
    return cfg, meta
