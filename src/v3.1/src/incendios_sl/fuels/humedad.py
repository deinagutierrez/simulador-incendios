"""Estado dinámico de humedad del combustible.

Muerto fino (1 h): Fine Fuel Moisture Code horario del sistema canadiense (Van Wagner 1977; Van Wagner & Pickett
1985), portado de la implementación de referencia `cffdrs` (R, función hourly_fine_fuel_moisture_code).
Entradas: temperatura (°C), humedad relativa (%), viento a 10 m (km/h), lluvia horaria (mm).
Humedad (%) = 147.2 · (101 − FFMC) / (59.5 + FFMC)   (FFMC_COEFFICIENT = 250·59.5/101 ≈ 147.27).

10 h y 100 h: 1 h + desplazamientos (HIPÓTESIS, config). Vivo herbáceo/leñoso: escalado lineal de NDMI
(HIPÓTESIS/CALIBRAR, config). Nada de esto está validado localmente.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FFMC_COEF = 250.0 * 59.5 / 101.0


def ffmc_a_humedad(ffmc: np.ndarray | float) -> np.ndarray | float:
    return FFMC_COEF * (101.0 - ffmc) / (59.5 + ffmc)


def humedad_a_ffmc(m: np.ndarray | float) -> np.ndarray | float:
    return 59.5 * (250.0 - m) / (FFMC_COEF + m)


def ffmc_horario_paso(temp: float, rh: float, ws_kmh: float, prec_mm: float, ffmc_prev: float, dt_h: float = 1.0) -> float:
    """Un paso del FFMC horario (cffdrs::hourly_fine_fuel_moisture_code)."""
    mo = FFMC_COEF * (101.0 - ffmc_prev) / (59.5 + ffmc_prev)
    if prec_mm > 0.0:
        rf = prec_mm
        mr = mo + 42.5 * rf * np.exp(-100.0 / (251.0 - mo)) * (1.0 - np.exp(-6.93 / rf))
        if mo > 150.0:
            mr += 0.0015 * (mo - 150.0) ** 2 * np.sqrt(rf)
        mo = min(mr, 250.0)
    rh = min(max(rh, 0.0), 100.0)
    Ed = 0.942 * rh ** 0.679 + 11.0 * np.exp((rh - 100.0) / 10.0) + 0.18 * (21.1 - temp) * (1.0 - np.exp(-0.115 * rh))
    ko = 0.424 * (1.0 - (rh / 100.0) ** 1.7) + 0.0694 * np.sqrt(max(ws_kmh, 0.0)) * (1.0 - (rh / 100.0) ** 8)
    kd = ko * 0.0579 * np.exp(0.0365 * temp)
    md = Ed + (mo - Ed) * 10.0 ** (-kd * dt_h)
    Ew = 0.618 * rh ** 0.753 + 10.0 * np.exp((rh - 100.0) / 10.0) + 0.18 * (21.1 - temp) * (1.0 - np.exp(-0.115 * rh))
    k1 = 0.424 * (1.0 - ((100.0 - rh) / 100.0) ** 1.7) + 0.0694 * np.sqrt(max(ws_kmh, 0.0)) * (1.0 - ((100.0 - rh) / 100.0) ** 8)
    kw = k1 * 0.0579 * np.exp(0.0365 * temp)
    mw = Ew - (Ew - mo) * 10.0 ** (-kw * dt_h)
    if mo > Ed:
        m = md
    elif mo < Ew:
        m = mw
    else:
        m = mo
    f = 59.5 * (250.0 - m) / (FFMC_COEF + m)
    return float(max(f, 0.0))


def ffmc_horario(temp, rh, ws_kmh, prec_mm, ffmc_inicial: float = 85.0, dt_h: float = 1.0) -> np.ndarray:
    """Serie de FFMC horario. Valores faltantes se propagan como NaN (no se inventan)."""
    temp = np.asarray(temp, float); rh = np.asarray(rh, float); ws = np.asarray(ws_kmh, float); pr = np.asarray(prec_mm, float)
    out = np.full(len(temp), np.nan)
    f = ffmc_inicial
    for i in range(len(temp)):
        if np.isnan(temp[i]) or np.isnan(rh[i]) or np.isnan(ws[i]) or np.isnan(pr[i]):
            out[i] = np.nan
            continue
        f = ffmc_horario_paso(temp[i], rh[i], ws[i], pr[i], f, dt_h)
        out[i] = f
    return out


# ---------------------------------------------------------------------------------------------------------------
# Variante "retardo_simard" (docs/11): humedad de equilibrio de Simard (1968) y relajación exponencial con tiempos de
# retardo de 1, 10 y 100 h (BIBLIO: Fosberg 1970; Bradshaw et al. 1978, NFDRS). El FFMC describe la hojarasca de
# coníferas (tiempo de respuesta efectivo 6-10 h) y seca demasiado lento para pastizales y arbustales finos.
def emc_simard(temp_c, rh) -> np.ndarray:
    """Humedad de equilibrio (%) de Simard (1968), T en °F, HR en %. BIBLIO."""
    t = np.asarray(temp_c, float) * 9.0 / 5.0 + 32.0
    h = np.clip(np.asarray(rh, float), 0.0, 100.0)
    e1 = 0.03229 + 0.281073 * h - 0.000578 * h * t
    e2 = 2.22749 + 0.160107 * h - 0.014784 * t
    e3 = 21.0606 + 0.005565 * h ** 2 - 0.00035 * h * t - 0.483199 * h
    return np.where(h < 10.0, e1, np.where(h < 50.0, e2, e3))


def lluvia_vanwagner(m: float, prec_mm: float) -> float:
    """Incremento de humedad por lluvia de la ecuación del FFMC (Van Wagner 1987), en la escala de humedad (%)."""
    if prec_mm <= 0.0:
        return m
    mr = m + 42.5 * prec_mm * np.exp(-100.0 / (251.0 - m)) * (1.0 - np.exp(-6.93 / prec_mm))
    if m > 150.0:
        mr += 0.0015 * (m - 150.0) ** 2 * np.sqrt(prec_mm)
    return float(min(mr, 250.0))


def humedad_retardo(temp, rh, prec_mm, tau_h: float, factor_lluvia: float = 1.0, m_max: float = 35.0, dt_h: float = 1.0,
                    m_inicial: float | None = None) -> np.ndarray:
    """Serie de humedad (%) de una clase de retardo tau_h: m(t+dt) = EMC + (m − EMC)·exp(−dt/τ); la lluvia suma el
    incremento de Van Wagner multiplicado por `factor_lluvia` (1 para 1 h; HIPÓTESIS para 10 h y 100 h), con tope `m_max`
    (saturación de fibra ampliada, HIPÓTESIS). Valores faltantes se propagan como NaN."""
    temp = np.asarray(temp, float); rh = np.asarray(rh, float); pr = np.asarray(prec_mm, float)
    emc = emc_simard(temp, rh)
    out = np.full(len(temp), np.nan)
    m = float(emc[0]) if m_inicial is None and np.isfinite(emc[0]) else (m_inicial if m_inicial is not None else 15.0)
    decaim = float(np.exp(-dt_h / tau_h))
    for i in range(len(temp)):
        if np.isnan(temp[i]) or np.isnan(rh[i]) or np.isnan(pr[i]):
            out[i] = np.nan
            continue
        if pr[i] > 0.0:
            m = min(m + factor_lluvia * (lluvia_vanwagner(m, pr[i]) - m), m_max)
        m = float(emc[i] + (m - emc[i]) * decaim)
        out[i] = m
    return out


def serie_humedad(dominio: pd.DataFrame, cfg_hum: dict, ffmc_inicial: float = 85.0) -> pd.DataFrame:
    """A partir de la serie horaria del dominio (Open-Meteo) calcula las dos variantes de humedad muerta:
    - FFMC horario (columnas m_1h_pct, m_10h_pct, m_100h_pct; modelo v1, sin cambios);
    - retardo de Simard (columnas m_1h_pct_rt, m_10h_pct_rt, m_100h_pct_rt; modelo v2, `humedad.muerto_1h: retardo_simard`).
    La corrida elige la variante según el YAML del modelo (`simulation/entradas.py`)."""
    f = ffmc_horario(dominio["temperature_2m"], dominio["relative_humidity_2m"], dominio["wind_speed_10m"] * 3.6,
                     dominio["precipitation"], ffmc_inicial)
    m1 = ffmc_a_humedad(f)
    out = dominio[["time_utc"]].copy()
    out["ffmc"] = f
    out["m_1h_pct"] = m1
    out["m_10h_pct"] = m1 + float(cfg_hum.get("muerto_10h_offset", 1.0))
    out["m_100h_pct"] = m1 + float(cfg_hum.get("muerto_100h_offset", 2.0))
    # lluvia acumulada 24 h (para la regla de extinción temporal, HIPÓTESIS)
    out["lluvia_24h_mm"] = dominio["precipitation"].rolling(24, min_periods=1).sum().to_numpy()
    rt = cfg_hum.get("retardo", {}) or {}
    for nombre, tau, fl, mmax in (("1h", 1.0, 1.0, 35.0), ("10h", 10.0, float(rt.get("factor_lluvia_10h", 0.5)), 40.0),
                                  ("100h", 100.0, float(rt.get("factor_lluvia_100h", 0.25)), 45.0)):
        out[f"m_{nombre}_pct_rt"] = humedad_retardo(dominio["temperature_2m"], dominio["relative_humidity_2m"], dominio["precipitation"],
                                                   tau_h=float(rt.get(f"tau_{nombre}", tau)), factor_lluvia=fl, m_max=mmax)
    out["emc_pct"] = emc_simard(dominio["temperature_2m"], dominio["relative_humidity_2m"])
    return out


def lfmc_desde_ndmi(ndmi: np.ndarray, cfg: dict) -> np.ndarray:
    """Humedad de combustible vivo (%) por escalado lineal de NDMI entre [ndmi_min, ndmi_max] -> [lfmc_min, lfmc_max].
    HIPÓTESIS de prueba (CALIBRAR); NaN donde NDMI no es válido."""
    a, b = float(cfg["ndmi_min"]), float(cfg["ndmi_max"])
    lo, hi = float(cfg["lfmc_min"]), float(cfg["lfmc_max"])
    t = np.clip((ndmi - a) / (b - a), 0.0, 1.0)
    return np.where(np.isfinite(ndmi), lo + t * (hi - lo), np.nan).astype(np.float32)
