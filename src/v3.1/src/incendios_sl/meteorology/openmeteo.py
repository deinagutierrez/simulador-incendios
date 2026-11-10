"""Adquisición de meteorología horaria desde Open-Meteo (Historical Weather API / Forecast API).

Características: malla de puntos sobre el dominio, normalización (UTC, m/s, °C, mm), control de calidad,
caché por hash de parámetros, CSV + Parquet + JSON de procedencia, reintentos ante errores de red.
La dirección del viento es la meteorológica (grados DESDE los que sopla), verificada empíricamente (Etapa 1).
Los datos de la API histórica son reanálisis/análisis de modelo (ERA5, ERA5-Land, ECMWF IFS), no observaciones.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests
from pyproj import Transformer

from .. import config as cfgmod
from ..grilla import Grilla
from ..procedencia import hash_dict, ahora_utc, escribir_procedencia

log = logging.getLogger(__name__)

URL_ARCHIVO = "https://archive-api.open-meteo.com/v1/archive"
URL_PRONOSTICO = "https://api.open-meteo.com/v1/forecast"

VARIABLES_OBLIGATORIAS = ["temperature_2m", "relative_humidity_2m", "wind_speed_10m", "wind_direction_10m", "precipitation"]
VARIABLES_OPCIONALES = ["shortwave_radiation", "wind_gusts_10m", "vapour_pressure_deficit", "soil_moisture_0_to_7cm", "dew_point_2m", "surface_pressure"]

RANGOS = {  # plausibilidad física (unidades normalizadas)
    "temperature_2m": (-30, 50), "relative_humidity_2m": (0, 100), "wind_speed_10m": (0, 60),
    "wind_direction_10m": (0, 360), "precipitation": (0, 200), "shortwave_radiation": (0, 1400),
    "wind_gusts_10m": (0, 90), "vapour_pressure_deficit": (0, 12), "soil_moisture_0_to_7cm": (0, 1),
    "dew_point_2m": (-40, 40), "surface_pressure": (500, 1100),
}


@dataclass
class ConfigMeteo:
    modelo: str = "ecmwf_ifs"                 # best_match | ecmwf_ifs | era5 | era5_land
    variables: list[str] = field(default_factory=lambda: VARIABLES_OBLIGATORIAS + ["shortwave_radiation", "wind_gusts_10m", "vapour_pressure_deficit"])
    n_puntos_lado: int = 4
    tipo: str = "historico"                   # historico (archive) | pronostico (forecast)
    reintentos: int = 4
    pausa_s: float = 1.0


def puntos_malla(grilla: Grilla, n: int) -> pd.DataFrame:
    """n × n puntos regularmente espaciados dentro de la grilla (centros de subceldas), en lon/lat."""
    xs = grilla.xmin + (np.arange(n) + 0.5) * (grilla.xmax - grilla.xmin) / n
    ys = grilla.ymin + (np.arange(n) + 0.5) * (grilla.ymax - grilla.ymin) / n
    X, Y = np.meshgrid(xs, ys)
    t = Transformer.from_crs(grilla.crs, "EPSG:4326", always_xy=True)
    lon, lat = t.transform(X.ravel(), Y.ravel())
    return pd.DataFrame({"punto_id": [f"p{i:02d}" for i in range(n * n)], "x": X.ravel(), "y": Y.ravel(),
                         "lon": np.round(lon, 5), "lat": np.round(lat, 5)})


def _consultar(lat: float, lon: float, inicio: pd.Timestamp, fin: pd.Timestamp, cfg: ConfigMeteo) -> dict[str, Any]:
    params = {"latitude": lat, "longitude": lon, "hourly": ",".join(cfg.variables), "timezone": "UTC",
              "wind_speed_unit": "ms", "temperature_unit": "celsius", "precipitation_unit": "mm"}
    if cfg.tipo == "historico":
        url = URL_ARCHIVO
        params |= {"start_date": inicio.strftime("%Y-%m-%d"), "end_date": fin.strftime("%Y-%m-%d"), "models": cfg.modelo}
    else:
        url = URL_PRONOSTICO
        params |= {"start_date": inicio.strftime("%Y-%m-%d"), "end_date": fin.strftime("%Y-%m-%d")}
        if cfg.modelo not in ("best_match", ""):
            params["models"] = cfg.modelo
    ultimo = None
    for i in range(cfg.reintentos):
        try:
            r = requests.get(url, params=params, timeout=120)
            if r.status_code == 429:
                raise requests.HTTPError("429 límite de solicitudes")
            r.raise_for_status()
            return r.json()
        except Exception as e:  # pragma: no cover - red
            ultimo = e
            espera = cfg.pausa_s * (2 ** i)
            log.warning("Open-Meteo intento %d fallido (%s); reintento en %.0f s", i + 1, str(e)[:120], espera)
            time.sleep(espera)
    raise RuntimeError(f"Open-Meteo: fallo tras {cfg.reintentos} intentos: {ultimo}")


def control_calidad(df: pd.DataFrame, variables: list[str]) -> dict[str, Any]:
    """Duplicados, faltantes y valores fuera de rango. Devuelve un informe; marca fuera de rango como NaN."""
    inf: dict[str, Any] = {"duplicados": int(df.duplicated(["punto_id", "time_utc"]).sum()), "variables": {}}
    df.drop_duplicates(["punto_id", "time_utc"], inplace=True)
    for v in variables:
        if v not in df:
            inf["variables"][v] = {"faltante": "columna ausente"}
            continue
        lo, hi = RANGOS.get(v, (-np.inf, np.inf))
        fuera = ((df[v] < lo) | (df[v] > hi)) & df[v].notna()
        inf["variables"][v] = {"nulos": int(df[v].isna().sum()), "fuera_de_rango": int(fuera.sum()),
                               "min": None if df[v].isna().all() else float(df[v].min()),
                               "max": None if df[v].isna().all() else float(df[v].max())}
        df.loc[fuera, v] = np.nan
    # huecos consecutivos por punto en las obligatorias
    huecos_max = 0
    for v in [x for x in VARIABLES_OBLIGATORIAS if x in df]:
        for _, s in df.groupby("punto_id")[v]:
            run = (s.isna().astype(int).groupby((~s.isna()).cumsum()).sum()).max()
            huecos_max = max(huecos_max, int(run))
    inf["max_horas_consecutivas_faltantes_obligatorias"] = huecos_max
    return inf


def uv_desde_vel_dir(vel: np.ndarray, dir_desde_deg: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Componentes U (este) y V (norte) a partir de velocidad y dirección meteorológica (desde)."""
    rad = np.deg2rad(dir_desde_deg)
    return -vel * np.sin(rad), -vel * np.cos(rad)


def vel_dir_desde_uv(u: np.ndarray, v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    vel = np.hypot(u, v)
    dir_desde = (270.0 - np.degrees(np.arctan2(v, u))) % 360.0
    return vel, dir_desde


def serie_dominio(df: pd.DataFrame) -> pd.DataFrame:
    """Serie horaria representativa del dominio: promedio de escalares y promedio vectorial del viento."""
    g = df.groupby("time_utc")
    out = g[[c for c in df.columns if c in RANGOS and c not in ("wind_direction_10m",)]].mean()
    u, v = uv_desde_vel_dir(df["wind_speed_10m"].to_numpy(), df["wind_direction_10m"].to_numpy())
    tmp = pd.DataFrame({"time_utc": df["time_utc"], "u": u, "v": v}).groupby("time_utc").mean()
    vel_vec, dir_vec = vel_dir_desde_uv(tmp["u"].to_numpy(), tmp["v"].to_numpy())
    out["wind_speed_10m_vectorial"] = vel_vec
    out["wind_direction_10m"] = dir_vec
    out["u10"] = tmp["u"]; out["v10"] = tmp["v"]
    out["n_puntos"] = g.size()
    return out.reset_index()


def adquirir(grilla: Grilla, inicio_utc: str, fin_utc: str, cfg: ConfigMeteo | None = None,
             out_dir: Path | None = None, etiqueta: str = "meteo") -> dict[str, Any]:
    """Descarga (o reutiliza de caché) la meteorología horaria para la malla de puntos del dominio.

    Devuelve dict con rutas (csv, parquet, json), el DataFrame largo y la serie del dominio."""
    cfg = cfg or ConfigMeteo()
    faltan = [v for v in VARIABLES_OBLIGATORIAS if v not in cfg.variables]
    if faltan:
        raise ValueError(f"faltan variables obligatorias: {faltan}")
    inicio = pd.Timestamp(inicio_utc).tz_convert("UTC") if pd.Timestamp(inicio_utc).tzinfo else pd.Timestamp(inicio_utc, tz="UTC")
    fin = pd.Timestamp(fin_utc).tz_convert("UTC") if pd.Timestamp(fin_utc).tzinfo else pd.Timestamp(fin_utc, tz="UTC")
    pts = puntos_malla(grilla, cfg.n_puntos_lado)
    params = {"modelo": cfg.modelo, "tipo": cfg.tipo, "variables": sorted(cfg.variables), "inicio": str(inicio), "fin": str(fin),
              "puntos": pts[["lon", "lat"]].round(4).values.tolist()}
    clave = hash_dict(params)[:16]
    out_dir = out_dir or cfgmod.dir_derivados("meteo")
    base = out_dir / f"{etiqueta}_{cfg.modelo}_{inicio.strftime('%Y%m%dT%H')}_{fin.strftime('%Y%m%dT%H')}_{clave}"
    rutas = {"csv": base.with_suffix(".csv"), "parquet": base.with_suffix(".parquet"), "json": base.with_suffix(".json"),
             "dominio_csv": base.with_name(base.name + "_dominio.csv")}
    if rutas["parquet"].exists() and rutas["json"].exists():
        df = pd.read_parquet(rutas["parquet"])
        log.info("meteorología reutilizada de caché: %s", rutas["parquet"].name)
        return rutas | {"df": df, "dominio": serie_dominio(df), "desde_cache": True}

    filas = []
    meta_puntos = []
    for _, p in pts.iterrows():
        d = _consultar(float(p.lat), float(p.lon), inicio, fin, cfg)
        h = d["hourly"]
        sub = pd.DataFrame(h)
        sub["time_utc"] = pd.to_datetime(sub.pop("time"), utc=True)
        sub.insert(0, "punto_id", p.punto_id)
        filas.append(sub)
        meta_puntos.append({"punto_id": p.punto_id, "lon_pedido": p.lon, "lat_pedido": p.lat,
                            "lon_modelo": d.get("longitude"), "lat_modelo": d.get("latitude"),
                            "elevacion_modelo_m": d.get("elevation"), "unidades": d.get("hourly_units")})
        time.sleep(0.2)
    df = pd.concat(filas, ignore_index=True)
    df = df[(df.time_utc >= inicio) & (df.time_utc <= fin)].copy()
    qc = control_calidad(df, cfg.variables)
    if qc["max_horas_consecutivas_faltantes_obligatorias"] > 2:
        raise RuntimeError(f"Meteorología incompleta: {qc['max_horas_consecutivas_faltantes_obligatorias']} h consecutivas "
                           f"sin dato en variables obligatorias (modelo {cfg.modelo}). No se rellena.")
    df.to_csv(rutas["csv"], index=False)
    df.to_parquet(rutas["parquet"], index=False)
    dom = serie_dominio(df)
    dom.to_csv(rutas["dominio_csv"], index=False)
    meta = {"fuente": "Open-Meteo " + ("Historical Weather API (reanálisis/análisis de modelo, NO observaciones)" if cfg.tipo == "historico" else "Forecast API"),
            "url": URL_ARCHIVO if cfg.tipo == "historico" else URL_PRONOSTICO, "modelo": cfg.modelo, "licencia": "CC-BY 4.0",
            "descargado_utc": ahora_utc(), "periodo_utc": [str(inicio), str(fin)], "variables": cfg.variables,
            "convencion_direccion_viento": "meteorológica: grados desde los que sopla (0 = N, 90 = E)",
            "unidades": {"temperature_2m": "°C", "relative_humidity_2m": "%", "wind_speed_10m": "m/s", "precipitation": "mm/h",
                         "shortwave_radiation": "W/m²"}, "puntos": meta_puntos, "control_calidad": qc,
            "limitaciones": "resolución espacial del modelo (IFS 9 km / ERA5 25 km / ERA5-Land 11 km) y horaria; "
                            "la variación sub-malla (valles, laderas) no está representada", "hash_parametros": clave}
    with open(rutas["json"], "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False, default=str)
    escribir_procedencia(rutas["parquet"], meta["fuente"], params, [], extra={"control_calidad": qc})
    log.info("meteorología descargada: %d filas, %d puntos, QC=%s", len(df), len(pts), qc["max_horas_consecutivas_faltantes_obligatorias"])
    return rutas | {"df": df, "dominio": dom, "desde_cache": False}
