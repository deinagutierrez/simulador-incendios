"""Meteorología de una corrida en tiempo real: pronóstico de Open-Meteo, CSV cargado a mano y modo escenario.

Todo termina en la "serie del dominio" con el formato de v3.x (`<etiqueta>_dominio.csv`: `time_utc`, `temperature_2m`,
`relative_humidity_2m`, `wind_speed_10m` en m/s, `wind_direction_10m` desde donde sopla, `precipitation` en mm/h,
`wind_speed_10m_vectorial`, `u10`, `v10`, `n_puntos`), que es lo que leen los dos motores: v3.1 directo y v4.0 a través de
`eventos.convertir_meteo`.

El pronóstico usa el cliente congelado de v3.1 (`openmeteo.adquirir`, `tipo: pronostico`), así que estas funciones corren
en el proceso de datos, con el camino de v3.1 (D-E3-24, punto 14). Una "toma" es una carpeta de la caché
`datos/procesados/app/meteo/<id>/` con la serie, sus metadatos y un `info.json` que lee el servidor.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import shutil
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import comun

MODELO = "ecmwf_ifs025"             # D-E3-07
RESPALDO = "best_match"
DIAS_ATRAS = 5
DIAS_ADELANTE = 7
MAX_HUECO_H = 2                     # control de calidad de v3.1: más de 2 h seguidas sin dato → rechazo
COLUMNAS_V3 = ["time_utc", "temperature_2m", "relative_humidity_2m", "wind_speed_10m", "wind_direction_10m", "precipitation"]
COLUMNAS_V4 = ["timestamp", "temp_c", "hr_pct", "viento_kmh", "viento_dir_deg", "precip_mm"]
RANGOS = {"temperature_2m": (-40, 50), "relative_humidity_2m": (0, 100), "wind_speed_10m": (0, 60),
          "wind_direction_10m": (0, 360), "precipitation": (0, 200)}


def dir_tomas() -> Path:
    return comun.dir_cache("meteo")


def _hora(t: pd.Timestamp) -> pd.Timestamp:
    return t.tz_convert("UTC").floor("h") if t.tzinfo else t.tz_localize("UTC").floor("h")


def _guardar_toma(id_: str, dominio: pd.DataFrame, fuente: str, rotulo: str, extra: dict) -> dict:
    d = dir_tomas() / id_
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    ruta = d / f"{id_}_dominio.csv"
    dominio.to_csv(ruta, index=False)
    t = pd.to_datetime(dominio["time_utc"], utc=True)
    info = {"id": id_, "tipo": "meteo", "fuente": fuente, "rotulo": rotulo, "creada_utc": comun.ahora_utc(),
            "desde_utc": f"{t.min():%Y-%m-%dT%H:%M:%SZ}", "hasta_utc": f"{t.max():%Y-%m-%dT%H:%M:%SZ}", "horas": int(len(t)),
            "archivo": ruta.name, "sha256": comun.sha256(ruta)} | extra
    comun.escribir_json(d / "info.json", info)
    return info


def _hora_a_hora(dominio: pd.DataFrame) -> None:
    """Rechaza una serie con horas repetidas, desordenadas o huecos de más de `MAX_HUECO_H` horas."""
    t = pd.to_datetime(dominio["time_utc"], utc=True)
    if t.duplicated().any():
        raise ValueError(f"hay horas repetidas, por ejemplo {t[t.duplicated()].iloc[0]:%Y-%m-%d %H:%M} UTC")
    if not t.is_monotonic_increasing:
        raise ValueError("las horas no están en orden")
    paso = t.diff().dropna()
    if (paso <= pd.Timedelta(0)).any() or (paso % pd.Timedelta(hours=1) != pd.Timedelta(0)).any():
        raise ValueError("las horas tienen que ser en punto y con paso de una hora")
    if (paso > pd.Timedelta(hours=MAX_HUECO_H + 1)).any():
        i = int(np.argmax(paso.to_numpy() > np.timedelta64(MAX_HUECO_H + 1, "h")))
        raise ValueError(f"falta más de {MAX_HUECO_H} h seguidas después de {t.iloc[i]:%Y-%m-%d %H:%M} UTC")
    for c in COLUMNAS_V3[1:]:
        v = dominio[c]
        if v.isna().any():
            raise ValueError(f"la columna {c} tiene valores vacíos")
        lo, hi = RANGOS[c]
        fuera = (v < lo) | (v > hi)
        if fuera.any():
            raise ValueError(f"{c} fuera de rango físico ({lo} a {hi}): {float(v[fuera].iloc[0])} el "
                             f"{pd.Timestamp(dominio['time_utc'][fuera].iloc[0]):%Y-%m-%d %H:%M}")


def _completar(df: pd.DataFrame) -> pd.DataFrame:
    """Serie de un solo punto → columnas que agrega `serie_dominio` de v3.1, rellenando huecos cortos como v4.0."""
    t = pd.to_datetime(df["time_utc"], utc=True)
    x = df.set_index(t)[COLUMNAS_V3[1:]].astype(float)
    rad = np.deg2rad(x["wind_direction_10m"])
    u, v = -x["wind_speed_10m"] * np.sin(rad), -x["wind_speed_10m"] * np.cos(rad)
    x = x.assign(u10=u, v10=v)
    x = x.reindex(pd.date_range(x.index[0], x.index[-1], freq="1h")).interpolate(limit=MAX_HUECO_H, limit_area="inside")
    vel = np.hypot(x["u10"], x["v10"])
    x["wind_direction_10m"] = (np.degrees(np.arctan2(-x["u10"], -x["v10"])) + 360.0) % 360.0
    out = pd.DataFrame({"time_utc": [f"{h:%Y-%m-%d %H:%M:%S+00:00}" for h in x.index],
                        "temperature_2m": x["temperature_2m"].to_numpy(), "relative_humidity_2m": x["relative_humidity_2m"].to_numpy(),
                        "wind_speed_10m": x["wind_speed_10m"].to_numpy(), "wind_direction_10m": x["wind_direction_10m"].round(3).to_numpy(),
                        "precipitation": x["precipitation"].to_numpy(), "wind_speed_10m_vectorial": vel.to_numpy(),
                        "u10": x["u10"].to_numpy(), "v10": x["v10"].to_numpy(), "n_puntos": 1})
    return out


# ------------------------------------------------------------------ pronóstico
def pronostico(ahora: pd.Timestamp | None = None, modelo: str = MODELO, respaldo: str | None = RESPALDO,
               dias_atras: int = DIAS_ATRAS, dias_adelante: int = DIAS_ADELANTE, aviso=print) -> dict:
    """Baja el pronóstico de los 16 puntos con el cliente de v3.1 y deja una toma en la caché. Ventana: desde
    `dias_atras` días antes de la hora en curso (para la humedad del combustible muerto) hasta el final del día
    `dias_adelante`. Con `respaldo`, si el modelo principal falla o no pasa el control de calidad, prueba con ese."""
    from incendios_sl import config as cfgmod                     # v3.1 (proceso de datos)
    from incendios_sl.data import preparar_dominio as pdm
    from incendios_sl.meteorology.openmeteo import ConfigMeteo

    ahora = _hora(ahora if ahora is not None else pd.Timestamp.now(tz="UTC"))
    inicio = ahora - pd.Timedelta(days=dias_atras)
    fin = (ahora + pd.Timedelta(days=dias_adelante)).normalize() + pd.Timedelta(hours=23)
    dom = cfgmod.cargar_dominio(comun.dominio_yaml()["id"])
    g = pdm.grilla_viento(dom)
    cache = comun.dir_cache("meteo_crudo")
    errores = []
    for m in [modelo] + ([respaldo] if respaldo and respaldo != modelo else []):
        t0 = time.time()
        try:
            aviso(f"pidiendo el pronóstico {m} de 16 puntos a Open-Meteo")
            r = adquirir_en_paralelo(g, inicio, fin, ConfigMeteo(modelo=m, tipo="pronostico"), cache, "pronostico")
        except Exception as e:                   # sin red, servicio caído o control de calidad rechazado
            errores.append(f"{m}: {e}")
            continue
        segundos = round(time.time() - t0, 1)
        dominio = pd.read_csv(r["dominio_csv"])
        meta = json.loads(Path(r["json"]).read_text(encoding="utf-8"))
        id_ = f"M-{ahora:%Y%m%dT%H%M}-pronostico"
        info = _guardar_toma(id_, dominio, f"Open-Meteo Forecast API, modelo {m}",
                             "pronóstico" + ("" if m == modelo else f" (respaldo {m})"),
                             {"modelo": m, "modelo_pedido": modelo, "descargado_utc": meta.get("descargado_utc"),
                              "hora_de_la_toma_utc": f"{ahora:%Y-%m-%dT%H:%M:%SZ}", "segundos": segundos,
                              "desde_cache": bool(r.get("desde_cache")), "puntos": 16, "licencia": meta.get("licencia"),
                              "control_calidad": meta.get("control_calidad"), "errores_previos": errores,
                              "aviso": "Open-Meteo entrega análisis y pronóstico de un modelo, no observaciones"})
        shutil.copy(r["json"], dir_tomas() / id_ / "openmeteo.json")
        return info
    raise RuntimeError("no se pudo bajar el pronóstico. " + " | ".join(errores))


def adquirir_en_paralelo(grilla, inicio: pd.Timestamp, fin: pd.Timestamp, cfg, out_dir: Path, etiqueta: str,
                         hilos: int = 8) -> dict:
    """Lo mismo que `openmeteo.adquirir` de v3.1 (mismos 16 puntos, mismo pedido por punto, mismo control de calidad, misma
    serie del dominio y mismos archivos), pero con los pedidos en paralelo: el original los hace de a uno con una pausa
    de 0,2 s y tarda unos 12 s, por encima del criterio de 10 s del plan. Usa las funciones congeladas de v3.1."""
    from concurrent.futures import ThreadPoolExecutor
    from incendios_sl.meteorology.openmeteo import (URL_PRONOSTICO, VARIABLES_OBLIGATORIAS, _consultar, control_calidad,
                                                    puntos_malla, serie_dominio)
    pts = puntos_malla(grilla, cfg.n_puntos_lado)
    with ThreadPoolExecutor(max_workers=hilos) as ex:
        respuestas = list(ex.map(lambda p: _consultar(float(p.lat), float(p.lon), inicio, fin, cfg), [p for _, p in pts.iterrows()]))
    filas, meta_puntos = [], []
    for (_, p), d in zip(pts.iterrows(), respuestas):
        sub = pd.DataFrame(d["hourly"])
        sub["time_utc"] = pd.to_datetime(sub.pop("time"), utc=True)
        sub.insert(0, "punto_id", p.punto_id)
        filas.append(sub)
        meta_puntos.append({"punto_id": p.punto_id, "lon_pedido": p.lon, "lat_pedido": p.lat, "lon_modelo": d.get("longitude"),
                            "lat_modelo": d.get("latitude"), "elevacion_modelo_m": d.get("elevation"), "unidades": d.get("hourly_units")})
    df = pd.concat(filas, ignore_index=True)
    df = df[(df.time_utc >= inicio) & (df.time_utc <= fin)].copy()
    qc = control_calidad(df, cfg.variables)
    if qc["max_horas_consecutivas_faltantes_obligatorias"] > MAX_HUECO_H:
        raise RuntimeError(f"meteorología incompleta: {qc['max_horas_consecutivas_faltantes_obligatorias']} h consecutivas sin "
                           f"dato en variables obligatorias (modelo {cfg.modelo}); no se rellena")
    falta = [v for v in VARIABLES_OBLIGATORIAS if df[v].isna().all()]
    if falta:
        raise RuntimeError(f"el modelo {cfg.modelo} no entregó {', '.join(falta)}")
    base = out_dir / f"{etiqueta}_{cfg.modelo}_{inicio:%Y%m%dT%H}_{fin:%Y%m%dT%H}"
    rutas = {"csv": base.with_suffix(".csv"), "parquet": base.with_suffix(".parquet"), "json": base.with_suffix(".json"),
             "dominio_csv": base.with_name(base.name + "_dominio.csv")}
    df.to_csv(rutas["csv"], index=False)
    df.to_parquet(rutas["parquet"], index=False)
    serie_dominio(df).to_csv(rutas["dominio_csv"], index=False)
    meta = {"fuente": "Open-Meteo Forecast API", "url": URL_PRONOSTICO, "modelo": cfg.modelo, "licencia": "CC-BY 4.0",
            "descargado_utc": comun.ahora_utc(), "periodo_utc": [str(inicio), str(fin)], "variables": cfg.variables,
            "convencion_direccion_viento": "meteorológica: grados desde los que sopla (0 = N, 90 = E)",
            "unidades": {"temperature_2m": "°C", "relative_humidity_2m": "%", "wind_speed_10m": "m/s", "precipitation": "mm/h"},
            "puntos": meta_puntos, "control_calidad": qc,
            "codigo": "app/datos/meteo.adquirir_en_paralelo con las funciones de openmeteo.py de v3.1"}
    comun.escribir_json(rutas["json"], meta)
    return rutas | {"desde_cache": False}


# ------------------------------------------------------------------ CSV cargado a mano
def leer_csv_manual(contenido: bytes) -> tuple[pd.DataFrame, str]:
    """CSV en el formato de v3.x (`time_utc`, `temperature_2m`, … en m/s) o en el de v4.0 (`timestamp` con huso,
    `temp_c`, `hr_pct`, `viento_kmh`, `viento_dir_deg`, `precip_mm`). Devuelve la serie del dominio y el formato."""
    try:
        df = pd.read_csv(io.BytesIO(contenido))
    except Exception as e:
        raise ValueError(f"no se pudo leer el CSV: {e}")
    cols = set(df.columns)
    if set(COLUMNAS_V3) <= cols:
        formato = "v3.x"
        t = pd.to_datetime(df["time_utc"], utc=True, errors="coerce")
        base = pd.DataFrame({"time_utc": t} | {c: pd.to_numeric(df[c], errors="coerce") for c in COLUMNAS_V3[1:]})
    elif set(COLUMNAS_V4) <= cols:
        formato = "v4.0"
        t = pd.to_datetime(df["timestamp"], errors="coerce", utc=False)
        if t.isna().any() or any(getattr(x, "tzinfo", None) is None for x in t):
            raise ValueError("en el formato de v4.0 la columna timestamp tiene que llevar huso horario, por ejemplo 2026-11-13T09:00:00-03:00")
        t = pd.to_datetime(df["timestamp"], utc=True)
        base = pd.DataFrame({"time_utc": t, "temperature_2m": pd.to_numeric(df["temp_c"], errors="coerce"),
                             "relative_humidity_2m": pd.to_numeric(df["hr_pct"], errors="coerce"),
                             "wind_speed_10m": pd.to_numeric(df["viento_kmh"], errors="coerce") / 3.6,
                             "wind_direction_10m": pd.to_numeric(df["viento_dir_deg"], errors="coerce") % 360.0,
                             "precipitation": pd.to_numeric(df["precip_mm"], errors="coerce")})
    else:
        raise ValueError("columnas no reconocidas. Formato v3.x: " + ", ".join(COLUMNAS_V3) + ". Formato v4.0: " + ", ".join(COLUMNAS_V4))
    if base["time_utc"].isna().any():
        raise ValueError("hay horas que no se pueden leer")
    if len(base) < 24:
        raise ValueError("la serie tiene menos de 24 horas")
    base = base.sort_values("time_utc").reset_index(drop=True)
    _hora_a_hora(base)
    return _completar(base), formato


def toma_manual(contenido: bytes, nombre: str) -> dict:
    dominio, formato = leer_csv_manual(contenido)
    sha = __import__("hashlib").sha256(contenido).hexdigest()
    id_ = f"M-{pd.Timestamp.now(tz='UTC'):%Y%m%dT%H%M}-manual-{sha[:6]}"
    info = _guardar_toma(id_, dominio, f"CSV cargado a mano ({nombre})", "meteorología cargada a mano",
                         {"formato": formato, "archivo_original": nombre, "sha256_original": sha,
                          "aviso": "serie de un solo punto, sin control de procedencia"})
    (dir_tomas() / id_ / f"original_{Path(nombre).name}").write_bytes(contenido)
    return info


# ------------------------------------------------------------------ modo escenario
def toma_escenario(desde_utc: str, horas: int, temp_c: float, hr_pct: float, viento_kmh: float, viento_dir_deg: float,
                   precip_mm: float = 0.0, dias_previos: int = DIAS_ATRAS) -> dict:
    """Serie con valores constantes (§4.2, "si falla" (4)). Empieza `dias_previos` días antes de `desde_utc`, con los
    mismos valores, para que la humedad del combustible muerto llegue al equilibrio con ellos."""
    t0 = _hora(pd.Timestamp(desde_utc))
    if not (1 <= int(horas) <= 240):
        raise ValueError("las horas del escenario van de 1 a 240")
    valores = {"temperature_2m": float(temp_c), "relative_humidity_2m": float(hr_pct), "wind_speed_10m": float(viento_kmh) / 3.6,
               "wind_direction_10m": float(viento_dir_deg) % 360.0, "precipitation": float(precip_mm)}
    t = pd.date_range(t0 - pd.Timedelta(days=dias_previos), t0 + pd.Timedelta(hours=int(horas) + 1), freq="1h")
    base = pd.DataFrame({"time_utc": t} | {k: v for k, v in valores.items()})
    _hora_a_hora(base)
    id_ = f"M-{pd.Timestamp.now(tz='UTC'):%Y%m%dT%H%M%S}-escenario-{__import__('secrets').token_hex(2)}"
    return _guardar_toma(id_, _completar(base), "escenario con valores fijos puestos a mano", "escenario manual",
                         {"valores": {"temp_c": float(temp_c), "hr_pct": float(hr_pct), "viento_kmh": float(viento_kmh),
                                      "viento_dir_deg": float(viento_dir_deg) % 360.0, "precip_mm": float(precip_mm)},
                          "inicio_escenario_utc": f"{t0:%Y-%m-%dT%H:%M:%SZ}", "dias_previos": dias_previos,
                          "aviso": "valores constantes: no es un pronóstico"})


def tomas() -> list[dict]:
    """Tomas de la caché, de la más nueva a la más vieja."""
    out = [comun.leer_json(p) for p in dir_tomas().glob("*/info.json")]
    return sorted([o for o in out if o], key=lambda o: o.get("creada_utc", ""), reverse=True)
