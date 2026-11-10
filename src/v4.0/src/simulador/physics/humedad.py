"""Humedad del combustible muerto (1 h, 10 h, 100 h), vivo y curado del pasto.

Combustible muerto (`ParametrosHumedad.metodo_muerto`)
------------------------------------------------------
- `retardo` (V.4): humedad de equilibrio (EMC) de Simard (1968) en función de T (°F) y HR (%), base del
  método de Fosberg/Nelson de NFDRS y BehavePlus. 1 h, 10 h y 100 h siguen a la EMC con relajación
  exponencial (τ = 1, 10 y 100 h). Lluvia: cada mm suma `lluvia_1h|10h|100h` puntos (con tope) → **a calibrar**.
  EMC (`emc`): `nfdrs` = coeficientes NFDRS en °F (como v3.0 fuels/humedad.py:73-80; corregido) |
  `v4_original` = la fórmula de V.4 (coeficientes de la versión en °C aplicados a T en °F: 30 °C / 20 % da
  2,67 % en lugar de 4,16 %; docs/v4.0/15, P2). Recorte a [emc_min_pct, emc_max_pct] (V.4: piso de 2 %).
- `ffmc_vanwagner` (v3.0 modelo_v1): FFMC horario de Van Wagner (1977; Van Wagner & Pickett 1985), portado de
  v3.0 fuels/humedad.py (cffdrs::hourly_fine_fuel_moisture_code), con 10 h = 1 h + `ffmc_offset_10h` y
  100 h = 1 h + `ffmc_offset_100h` (fracciones; HIPÓTESIS de v3.0).
- `fija`: 1 h, 10 h y 100 h constantes (`fija_m1`, `fija_m10`, `fija_m100`, obligatorias). Con otro método, una
  `fija_mX` no nula pisa esa clase.
- `lluvia_24h_mm_extincion` (v3.0, 15 mm): si la lluvia acumulada en 24 h alcanza el umbral, R0 = 0 en esa hora.
- `mx_grupo` / `mx_codigo`: humedad de extinción del muerto por familia S&B (GR, GS, SH, TU, TL, SB) o por código
  (v3.0 `mx_muerto_pct_clase`); fracción (valores > 1 se leen como %). Pisan la Mx de la tabla.

Combustible vivo (`viva_metodo`) y curado
-----------------------------------------
- `lineal` (V.4): M_vivo (%) = clip(a + b · NDMI, min, max) (a = 120, b = 250, [50, 250]), igual para herbáceo y
  leñoso → **a calibrar**.
- `minmax` (v3.0 lfmc_desde_ndmi): escalado lineal de NDMI entre [ndmi_min, ndmi_max] → [lfmc_min, lfmc_max], con
  parámetros separados para herbáceo (`viva_herb_minmax`) y leñoso (`viva_lenoso_minmax`).
- `fija`: `viva_fija` (fracción, o {herb, lenoso}).
- Sin índices (o NDMI inválido en `minmax`): `viva_defecto` (60 %, declarado).
- Curado del pasto: comparación del NDVI del mes con el NDVI del verano anterior:
      curado = clip(k · (1 − NDVI_mes / NDVI_verano), min, 1)   (k = 1.5, min = 0.3) → **a calibrar**
  Si no hay índices, regla de Scott & Burgan: curado = clip((1.2 − M_herb) / 0.9, 0, 1). `curado_fijo` lo fija.
  `curado_solo_dinamicos` (P9): la transferencia herbáceo vivo → muerto solo se aplica a los modelos dinámicos
  de S&B (V.4 la aplicaba a todos; sin efecto con la tabla SB40, sí con un CSV propio).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

METODOS_MUERTO = ("retardo", "ffmc_vanwagner", "fija")
METODOS_VIVA = ("lineal", "minmax", "fija")
METODOS_EMC = ("nfdrs", "v4_original")
FFMC_COEF = 250.0 * 59.5 / 101.0


def emc_simard(temp_c: np.ndarray, hr_pct: np.ndarray, metodo: str = "nfdrs", minimo_pct: float = 1.0,
               maximo_pct: float = 35.0) -> np.ndarray:
    """Humedad de equilibrio (fracción) según Simard (1968). temp en °C (se pasa a °F), HR en %.

    `nfdrs`: coeficientes NFDRS en °F (Bradshaw et al. 1983; v3.0). `v4_original`: la fórmula de V.4 (con
    `minimo_pct = 2` reproduce V.4 exactamente)."""
    T = np.asarray(temp_c, float) * 9.0 / 5.0 + 32.0
    H = np.clip(np.asarray(hr_pct, float), 0, 100)
    if metodo == "v4_original":
        emc = np.where(
            H < 10, 0.03 + 0.2626 * H - 0.00104 * H * T,
            np.where(H < 50, 1.76 + 0.1601 * H - 0.0266 * T,
                     21.06 - 0.4944 * H + 0.005565 * H ** 2 - 0.00063 * H * T))
    elif metodo == "nfdrs":
        emc = np.where(
            H < 10, 0.03229 + 0.281073 * H - 0.000578 * H * T,
            np.where(H < 50, 2.22749 + 0.160107 * H - 0.014784 * T,
                     21.0606 + 0.005565 * H ** 2 - 0.00035 * H * T - 0.483199 * H))
    else:
        raise ValueError(f"emc '{metodo}' desconocido (opciones: {', '.join(METODOS_EMC)})")
    return np.clip(emc, minimo_pct, maximo_pct) / 100.0


def _fraccion(v):
    """Fracción a partir de un valor en fracción o en % (> 1)."""
    v = float(v)
    return v / 100.0 if v > 1.0 else v


@dataclass
class ParametrosHumedad:
    lluvia_1h: float = 3.0       # puntos de humedad por mm
    lluvia_10h: float = 1.5
    lluvia_100h: float = 0.5
    tope_lluvia: float = 0.35    # fracción máxima tras lluvia
    tau_1h: float = 1.0          # horas
    tau_10h: float = 10.0
    tau_100h: float = 100.0
    # exposición (puntos porcentuales sumados al 1 h)
    sombra_dosel: float = 0.02   # TU / TL
    ladera_sombria: float = 0.01 # orientación hacia el polo (S en el hemisferio sur), pendiente > 5°
    # humedad viva: M (%) = a + b·NDMI, acotada. Con a = 120, b = 250: NDMI −0,2 → 70 %, 0 → 120 %, +0,2 → 170 %
    # (arbustal dormido de fin de invierno ≈ 60–90 %; pasto verde ≥ 120 %). A CALIBRAR.
    viva_a: float = 120.0
    viva_b: float = 250.0
    viva_min: float = 50.0
    viva_max: float = 250.0
    # curado
    curado_k: float = 1.5
    curado_min: float = 0.3
    # --- v4.0: opciones de la verificación y de v3.0 (docs/v4.0/14-15) ---------------------------------------
    metodo_muerto: str = "retardo"          # retardo | ffmc_vanwagner | fija
    emc: str = "nfdrs"                      # nfdrs (corregido) | v4_original
    emc_min_pct: float = 1.0                # V.4: 2.0
    emc_max_pct: float = 35.0
    fija_m1: float | None = None            # fracciones; obligatorias con metodo_muerto = fija
    fija_m10: float | None = None
    fija_m100: float | None = None
    ffmc_offset_10h: float = 0.01           # 10 h = 1 h + offset (fracción; v3.0 muerto_10h_offset = 1 %)
    ffmc_offset_100h: float = 0.02
    ffmc_inicial: float = 85.0              # FFMC al comienzo de la serie (v3.0)
    lluvia_24h_mm_extincion: float | None = None   # v3.0 = 15 mm; null = sin regla
    mx_grupo: dict = field(default_factory=dict)   # {GR: 0.15, …} pisa la Mx muerta de la tabla
    mx_codigo: dict = field(default_factory=dict)  # {102: 0.20, …} (prevalece sobre mx_grupo)
    viva_metodo: str = "lineal"             # lineal (V.4) | minmax (v3.0) | fija
    viva_fija: float | dict | None = None   # fracción o {herb, lenoso}
    viva_herb_minmax: dict = field(default_factory=lambda: {"ndmi_min": -0.1, "ndmi_max": 0.4, "lfmc_min": 30.0, "lfmc_max": 120.0})
    viva_lenoso_minmax: dict = field(default_factory=lambda: {"ndmi_min": -0.1, "ndmi_max": 0.4, "lfmc_min": 60.0, "lfmc_max": 150.0})
    viva_defecto: float = 0.60              # sin índices (o NDMI inválido en minmax)
    curado_fijo: float | None = None        # fracción de herbáceo curado constante
    curado_solo_dinamicos: bool = True      # V.4: False (curado a todos los modelos)

    def __post_init__(self):
        if self.metodo_muerto not in METODOS_MUERTO:
            raise ValueError(f"humedad.metodo_muerto '{self.metodo_muerto}' desconocido (opciones: {', '.join(METODOS_MUERTO)})")
        if self.emc not in METODOS_EMC:
            raise ValueError(f"humedad.emc '{self.emc}' desconocido (opciones: {', '.join(METODOS_EMC)})")
        if self.viva_metodo not in METODOS_VIVA:
            raise ValueError(f"humedad.viva_metodo '{self.viva_metodo}' desconocido (opciones: {', '.join(METODOS_VIVA)})")
        if self.metodo_muerto == "fija" and None in (self.fija_m1, self.fija_m10, self.fija_m100):
            raise ValueError("humedad.metodo_muerto = fija exige fija_m1, fija_m10 y fija_m100")
        if self.viva_metodo == "fija" and self.viva_fija is None:
            raise ValueError("humedad.viva_metodo = fija exige viva_fija")
        self.mx_grupo = dict(self.mx_grupo or {}); self.mx_codigo = dict(self.mx_codigo or {})


# ------------------------------------------------------------------------------------------- FFMC (v3.0)
def ffmc_a_humedad(ffmc):
    """FFMC → humedad del fino (%)."""
    return FFMC_COEF * (101.0 - ffmc) / (59.5 + ffmc)


def ffmc_horario_paso(temp: float, rh: float, ws_kmh: float, prec_mm: float, ffmc_prev: float, dt_h: float = 1.0) -> float:
    """Un paso del FFMC horario (cffdrs::hourly_fine_fuel_moisture_code; copia de v3.0 fuels/humedad.py)."""
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
            continue
        f = ffmc_horario_paso(temp[i], rh[i], ws[i], pr[i], f, dt_h)
        out[i] = f
    return out


# ------------------------------------------------------------------------------------------- serie horaria
def serie_humedad_muerta(df_meteo: pd.DataFrame, p: ParametrosHumedad) -> pd.DataFrame:
    """Serie horaria de m1, m10, m100 (fracción) según `p.metodo_muerto`, más `emc` y `lluvia_24h_mm`.

    `retardo` parte del equilibrio en la primera hora de la serie (V.4)."""
    emc = emc_simard(df_meteo["temp_c"].values, df_meteo["hr_pct"].values, p.emc, p.emc_min_pct, p.emc_max_pct)
    n = len(emc)
    pr = df_meteo["precip_mm"].values
    if p.metodo_muerto == "retardo":
        m1 = np.empty(n); m10 = np.empty(n); m100 = np.empty(n)
        m1[0] = m10[0] = m100[0] = emc[0]
        k1, k10, k100 = (1 - np.exp(-1.0 / p.tau_1h)), (1 - np.exp(-1.0 / p.tau_10h)), (1 - np.exp(-1.0 / p.tau_100h))
        for i in range(1, n):
            m1[i] = m1[i - 1] + (emc[i] - m1[i - 1]) * k1
            m10[i] = m10[i - 1] + (emc[i] - m10[i - 1]) * k10
            m100[i] = m100[i - 1] + (emc[i] - m100[i - 1]) * k100
            if pr[i] > 0:
                m1[i] = min(m1[i] + p.lluvia_1h * pr[i] / 100, p.tope_lluvia)
                m10[i] = min(m10[i] + p.lluvia_10h * pr[i] / 100, p.tope_lluvia)
                m100[i] = min(m100[i] + p.lluvia_100h * pr[i] / 100, p.tope_lluvia)
    elif p.metodo_muerto == "ffmc_vanwagner":
        viento = df_meteo["viento_kmh"].values if "viento_kmh" in df_meteo else np.zeros(n)
        f = ffmc_horario(df_meteo["temp_c"].values, df_meteo["hr_pct"].values, viento, pr, p.ffmc_inicial)
        m1 = ffmc_a_humedad(f) / 100.0
        m10 = m1 + p.ffmc_offset_10h
        m100 = m1 + p.ffmc_offset_100h
    else:
        m1 = np.full(n, np.nan); m10 = np.full(n, np.nan); m100 = np.full(n, np.nan)
    for arr, v in ((m1, p.fija_m1), (m10, p.fija_m10), (m100, p.fija_m100)):
        if v is not None:
            arr[:] = _fraccion(v)
    out = df_meteo[["timestamp"]].copy()
    out["emc"] = emc; out["m1"] = m1; out["m10"] = m10; out["m100"] = m100
    out["lluvia_24h_mm"] = pd.Series(pr, dtype=float).rolling(24, min_periods=1).sum().to_numpy()
    return out


# ------------------------------------------------------------------------------------------- vivo y curado
def humedad_viva(ndmi: np.ndarray, p: ParametrosHumedad) -> np.ndarray:
    """NDMI (−1..1) → humedad del combustible vivo (fracción), relación lineal de V.4."""
    return np.clip(p.viva_a + p.viva_b * np.asarray(ndmi, float), p.viva_min, p.viva_max) / 100.0


def lfmc_desde_ndmi(ndmi: np.ndarray, cfg: dict) -> np.ndarray:
    """Humedad viva (%) por escalado lineal de NDMI entre [ndmi_min, ndmi_max] → [lfmc_min, lfmc_max] (v3.0).
    NaN donde NDMI no es válido. HIPÓTESIS de prueba (CALIBRAR)."""
    a, b = float(cfg["ndmi_min"]), float(cfg["ndmi_max"])
    lo, hi = float(cfg["lfmc_min"]), float(cfg["lfmc_max"])
    ndmi = np.asarray(ndmi, float)
    t = np.clip((ndmi - a) / (b - a), 0.0, 1.0)
    return np.where(np.isfinite(ndmi), lo + t * (hi - lo), np.nan)


def humedades_vivas(ndmi: np.ndarray | None, shape: tuple, p: ParametrosHumedad) -> tuple[np.ndarray, np.ndarray]:
    """(M herbáceo vivo, M leñoso vivo) por celda (fracción, float32) según `p.viva_metodo`.

    `lineal` reproduce V.4: NDMI inválido → −0,1; sin NDMI → `viva_defecto` (V.4: 60 %)."""
    if p.viva_metodo == "fija":
        v = p.viva_fija
        h, l = (v.get("herb"), v.get("lenoso")) if isinstance(v, dict) else (v, v)
        return np.full(shape, _fraccion(h), "float32"), np.full(shape, _fraccion(l), "float32")
    if ndmi is None:
        d = np.full(shape, p.viva_defecto, "float32")
        return d, d.copy()
    if p.viva_metodo == "lineal":
        m = humedad_viva(np.nan_to_num(ndmi, nan=-0.1), p).astype("float32")
        return m, m
    h = lfmc_desde_ndmi(ndmi, p.viva_herb_minmax) / 100.0
    l = lfmc_desde_ndmi(ndmi, p.viva_lenoso_minmax) / 100.0
    return (np.where(np.isfinite(h), h, p.viva_defecto).astype("float32"),
            np.where(np.isfinite(l), l, p.viva_defecto).astype("float32"))


def curado_pasto(ndvi_mes: np.ndarray, ndvi_verano: np.ndarray, p: ParametrosHumedad) -> np.ndarray:
    """Fracción de la carga herbácea que está muerta (curada)."""
    with np.errstate(divide="ignore", invalid="ignore"):
        c = p.curado_k * (1.0 - np.asarray(ndvi_mes, float) / np.maximum(np.asarray(ndvi_verano, float), 0.05))
    c = np.where(np.isfinite(c), c, 1.0)
    return np.clip(c, p.curado_min, 1.0)


def curado_scott_burgan(m_herb: np.ndarray) -> np.ndarray:
    """Regla original de S&B: transferencia según humedad herbácea viva (30 % → 100 % curado, 120 % → 0)."""
    return np.clip((1.2 - np.asarray(m_herb, float)) / 0.9, 0.0, 1.0)
