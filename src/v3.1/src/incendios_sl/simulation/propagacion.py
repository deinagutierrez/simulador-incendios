"""Propagación direccional: combinación vectorial de viento y pendiente y elipse de Anderson (1983).

- Viento a media llama: U_mf = WAF · U10 (dirección HACIA la que sopla).
- Pendiente: el factor φ_s se convierte en un "viento virtual" cuesta arriba U_s tal que φ_w(U_s) = φ_s
  (inversa de la ecuación de viento de Rothermel), y se suma vectorialmente a U_mf (método de Rothermel 1983 /
  Finney 1998 descrito en Andrews 2018, "cross-slope wind"). El vector resultante da la dirección de máxima
  propagación θ_max y el viento efectivo U_eff; R_cabeza = R0·(1 + φ_w(U_eff)).
- Elipse: LB = 0.936·e^(0.2566·U) + 0.461·e^(−0.1548·U) − 0.397 (U_eff en mph, tope 8), e = sqrt(LB² − 1)/LB,
  R(θ) = R_cabeza·(1 − e)/(1 − e·cos(θ − θ_max)) (Anderson 1983 según Finney 1998 / Andrews 2018).
Limitación documentada: la suma vectorial sobrestima en viento cruzado fuerte (Sharples 2008).
"""
from __future__ import annotations

import math

import numpy as np
from numba import njit

FT_MIN_A_MPH = 0.011363636
M_S_A_FT_MIN = 196.850394


@njit(cache=True, fastmath=False)
def combinar_viento_pendiente(u10_este, v10_norte, waf, tan_pend, az_cuesta_arriba_rad, C, B, ratioE, phis_coef):
    """Devuelve (U_eff ft/min, theta_max rad azimut, phi_c)."""
    umf = waf * math.hypot(u10_este, v10_norte) * M_S_A_FT_MIN
    if umf > 0.0:
        az_w = math.atan2(u10_este, v10_norte)   # azimut hacia donde sopla
        ux = umf * math.sin(az_w); uy = umf * math.cos(az_w)
    else:
        ux = 0.0; uy = 0.0
    phis = phis_coef * tan_pend * tan_pend
    if phis > 0.0 and B > 0.0:
        us = (phis * ratioE / C) ** (1.0 / B)
        ux += us * math.sin(az_cuesta_arriba_rad); uy += us * math.cos(az_cuesta_arriba_rad)
    ueff = math.hypot(ux, uy)
    theta = math.atan2(ux, uy) if ueff > 0.0 else 0.0
    phic = C * ueff ** B / ratioE if ueff > 0.0 else 0.0
    return ueff, theta, phic


@njit(cache=True)
def excentricidad(ueff_ft_min):
    u = ueff_ft_min * FT_MIN_A_MPH
    lb = 0.936 * math.exp(0.2566 * u) + 0.461 * math.exp(-0.1548 * u) - 0.397
    if lb < 1.0:
        lb = 1.0
    if lb > 8.0:
        lb = 8.0
    return math.sqrt(lb * lb - 1.0) / lb


@njit(cache=True)
def ros_direccional(r_cabeza, e, theta_max, theta):
    """R(θ) de la elipse (misma unidad que r_cabeza)."""
    return r_cabeza * (1.0 - e) / (1.0 - e * math.cos(theta - theta_max))


def lb_desde_ueff(ueff_ft_min: float) -> float:
    u = ueff_ft_min * FT_MIN_A_MPH
    return float(np.clip(0.936 * np.exp(0.2566 * u) + 0.461 * np.exp(-0.1548 * u) - 0.397, 1.0, 8.0))
