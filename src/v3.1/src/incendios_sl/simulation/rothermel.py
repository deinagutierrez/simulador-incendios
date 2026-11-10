"""Modelo de velocidad de propagación superficial de Rothermel (1972) con las correcciones de Albini (1976),
multiclase (muerto 1 h / 10 h / 100 h, vivo herbáceo, vivo leñoso), según la explicación integral de
Andrews (2018, RMRS-GTR-371). Unidades internas imperiales (lb, ft, min, BTU) como en la formulación original;
la interfaz pública acepta SI (kg/m², m, 1/m, kJ/kg) y devuelve ft/min y m/min.

Opciones documentadas:
- `albini=True` (defecto): A = 133·σ^−0.7913 y carga neta w_n = w0·(1 − S_T) con agrupación g_i por clases de σ
  (Albini 1976, BehavePlus/FARSITE). `albini=False`: A = 1/(4.774·σ^0.1 − 7.27) y w_n = w0/(1 + S_T) (Rothermel 1972
  original, variante usada por WRF-SFIRE); se mantiene solo para contrastar con implementaciones de referencia.
- Combustible dinámico (Scott & Burgan 2005): una fracción `curado` de la carga herbácea viva se transfiere a una
  clase muerta con la σ del herbáceo y la humedad del 1 h.
- Sin límite de viento (Andrews, Cruz & Rothermel 2013 recomiendan no imponer el límite original); configurable.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

S_T = 0.0555        # contenido mineral total (fracción) — Rothermel 1972
S_E = 0.010         # contenido mineral efectivo (fracción)
RHO_P = 32.0        # densidad de partícula (lb/ft³)
KG_M2_A_LB_FT2 = 0.204816    # 1 kg/m² = 0.204816 lb/ft²
M_A_FT = 3.280840
KJ_KG_A_BTU_LB = 1.0 / 2.326
FT_MIN_A_M_MIN = 0.3048
FT_MIN_A_M_S = 0.00508


@dataclass
class LechoCombustible:
    """Parámetros de un modelo de combustible en SI."""
    w0_kg_m2: list[float]          # cargas [1h, 10h, 100h, herb, leñoso]
    sav_1_m: list[float]           # σ de cada clase (1/m); 0 si la clase no existe
    profundidad_m: float
    mx_muerto_pct: float
    calor_kJ_kg: float = 18608.0   # 8000 BTU/lb
    dinamico: bool = False
    nombre: str = ""

    def imperial(self) -> dict:
        return {"w0": [w * KG_M2_A_LB_FT2 for w in self.w0_kg_m2], "sig": [s / M_A_FT for s in self.sav_1_m],
                "delta": self.profundidad_m * M_A_FT, "mx": self.mx_muerto_pct / 100.0, "h": self.calor_kJ_kg * KJ_KG_A_BTU_LB}


@dataclass
class ResultadoRothermel:
    R0_ft_min: float            # velocidad sin viento ni pendiente
    I_R: float                  # intensidad de reacción (BTU/ft²/min)
    xi: float
    beta: float
    beta_op: float
    sigma: float                # σ característica (1/ft)
    C: float; B: float; E: float
    phis_coef: float            # 5.275·β^−0.3
    rho_b_eps_qig: float
    eta_M_muerto: float
    eta_M_vivo: float
    mx_vivo: float
    w_total: float

    @property
    def R0_m_min(self) -> float:
        return self.R0_ft_min * FT_MIN_A_M_MIN

    @property
    def ratio_E(self) -> float:
        """(β/β_op)^E, para φ_w = C·U^B / ratio_E."""
        return (self.beta / self.beta_op) ** self.E

    def phi_w(self, U_ft_min: float) -> float:
        return self.C * max(U_ft_min, 0.0) ** self.B / self.ratio_E

    def phi_s(self, tan_pend: float) -> float:
        return self.phis_coef * max(tan_pend, 0.0) ** 2

    def R_ft_min(self, U_ft_min: float = 0.0, tan_pend: float = 0.0) -> float:
        return self.R0_ft_min * (1.0 + self.phi_w(U_ft_min) + self.phi_s(tan_pend))


def _g_factores(sig_d: np.ndarray) -> np.ndarray:
    """Factores g_i de Albini (1976): las clases muertas se agrupan por intervalos de σ y comparten f."""
    limites = [1200, 192, 96, 48, 16, 0]
    g = np.zeros_like(sig_d)
    return g, limites


def rothermel_lecho(lecho: LechoCombustible, m_muerto_pct: tuple[float, float, float], m_herb_pct: float, m_lenoso_pct: float,
                    curado: float | None = None, albini: bool = True) -> ResultadoRothermel:
    """Calcula R0 y los coeficientes del lecho para humedades dadas (porcentajes).

    `curado`: fracción (0–1) de la carga herbácea viva transferida a muerta (modelos dinámicos). Si es None y el
    modelo es dinámico, se usa la regla estándar por humedad herbácea: 1 si LFMC_herb ≤ 30 %, 0 si ≥ 120 %, lineal."""
    p = lecho.imperial()
    w0 = np.array(p["w0"], float); sig = np.array(p["sig"], float); h = p["h"]; delta = p["delta"]; mx_d = p["mx"]
    m = np.array([m_muerto_pct[0], m_muerto_pct[1], m_muerto_pct[2], m_herb_pct, m_lenoso_pct], float) / 100.0
    # transferencia de curado (dinámico): clase muerta adicional con σ del herbáceo y humedad del 1 h
    if lecho.dinamico and w0[3] > 0:
        if curado is None:
            curado = float(np.clip((1.20 - m[3]) / 0.90, 0.0, 1.0))
        T = float(np.clip(curado, 0.0, 1.0))
        w_tr = w0[3] * T
        w0 = np.append(w0, w_tr); sig = np.append(sig, sig[3]); m = np.append(m, m[0]); w0[3] -= w_tr
        muerto = np.array([1, 1, 1, 0, 0, 1], bool)
    else:
        muerto = np.array([1, 1, 1, 0, 0], bool)
    vivo = ~muerto
    valido = (w0 > 0) & (sig > 0)
    w_total = float(w0[valido].sum())
    if w_total <= 0 or delta <= 0:
        return ResultadoRothermel(0, 0, 0, 0, 1, 1, 0, 1, 1, 0, 1, 0, 0, 0, 0)

    def pesos(mask):
        A = np.where(valido & mask, sig * w0 / RHO_P, 0.0)
        At = A.sum()
        f = A / At if At > 0 else np.zeros_like(A)
        return f, At
    f_d, A_d = pesos(muerto); f_l, A_l = pesos(vivo)
    A_T = A_d + A_l
    f_dead = A_d / A_T; f_live = A_l / A_T
    sig_d = float((f_d * sig).sum()); sig_l = float((f_l * sig).sum())
    sigma = f_dead * sig_d + f_live * sig_l
    # cargas netas
    if albini:
        w_n = w0 * (1.0 - S_T)
        # g_i: clases muertas agrupadas por intervalo de σ (Albini 1976)
        g = np.zeros_like(w0)
        for mask, f in ((muerto, f_d), (vivo, f_l)):
            idx = np.where(valido & mask)[0]
            limites = [(1200, np.inf), (192, 1200), (96, 192), (48, 96), (16, 48), (0, 16)]
            for lo, hi in limites:
                grupo = [i for i in idx if lo <= sig[i] < hi]
                if grupo:
                    s = sum(f[i] for i in grupo)
                    for i in grupo:
                        g[i] = s
        wn_dead = float((g * w_n * (valido & muerto)).sum()); wn_live = float((g * w_n * (valido & vivo)).sum())
    else:
        w_n = w0 / (1.0 + S_T)
        wn_dead = float((f_d * w_n).sum()); wn_live = float((f_l * w_n).sum())
    # humedades características
    m_dead = float((f_d * m).sum()); m_live = float((f_l * m).sum())
    # humedad de extinción del vivo
    mx_live = mx_d
    if A_l > 0:
        num = float((w0 * np.exp(-138.0 / np.where(sig > 0, sig, 1)) * (valido & muerto)).sum())
        den = float((w0 * np.exp(-500.0 / np.where(sig > 0, sig, 1)) * (valido & vivo)).sum())
        if den > 0 and num > 0:
            W = num / den
            m_fine = float((w0 * m * np.exp(-138.0 / np.where(sig > 0, sig, 1)) * (valido & muerto)).sum()) / num
            mx_live = max(2.9 * W * (1.0 - m_fine / mx_d) - 0.226, mx_d)
    def eta_M(mf, mx):
        r = min(mf / mx, 1.0) if mx > 0 else 1.0
        return max(0.0, 1.0 - 2.59 * r + 5.11 * r ** 2 - 3.52 * r ** 3)
    etaM_d = eta_M(m_dead, mx_d); etaM_l = eta_M(m_live, mx_live) if A_l > 0 else 0.0
    # Regla explícita (BehavePlus/FARSITE): si la humedad del muerto alcanza su humedad de extinción no hay propagación,
    # aunque la fracción viva conserve un factor de amortiguación positivo.
    if m_dead >= mx_d - 1e-9:
        return ResultadoRothermel(0.0, 0.0, 0.0, 0.0, 1.0, max(sigma, 1.0), 1.0, 1.0, 1.0, 0.0, 1.0, 0.0, 0.0, float(mx_live), w_total)
    eta_s = 0.174 * S_E ** (-0.19)
    rho_b = w_total / delta
    beta = rho_b / RHO_P
    beta_op = 3.348 * sigma ** (-0.8189)
    rel = beta / beta_op
    gmax = sigma ** 1.5 / (495.0 + 0.0594 * sigma ** 1.5)
    A = 133.0 * sigma ** (-0.7913) if albini else 1.0 / (4.774 * sigma ** 0.1 - 7.27)
    gamma = gmax * rel ** A * np.exp(A * (1.0 - rel))
    I_R = gamma * (wn_dead * h * etaM_d + wn_live * h * etaM_l) * eta_s
    xi = np.exp((0.792 + 0.681 * sigma ** 0.5) * (beta + 0.1)) / (192.0 + 0.2595 * sigma)
    # sumidero de calor
    eps = np.exp(-138.0 / np.where(sig > 0, sig, 1))
    qig = 250.0 + 1116.0 * m
    sink = rho_b * (f_dead * float((f_d * eps * qig).sum()) + f_live * float((f_l * eps * qig).sum()))
    R0 = I_R * xi / sink if sink > 0 else 0.0
    C = 7.47 * np.exp(-0.133 * sigma ** 0.55); B = 0.02526 * sigma ** 0.54; E = 0.715 * np.exp(-3.59e-4 * sigma)
    return ResultadoRothermel(float(R0), float(I_R), float(xi), float(beta), float(beta_op), float(sigma), float(C), float(B),
                              float(E), float(5.275 * beta ** (-0.3)), float(sink), etaM_d, etaM_l, float(mx_live), w_total)


def lecho_desde_fila(fila) -> LechoCombustible:
    """Construye un LechoCombustible desde una fila de tabla_combustibles_v1.csv."""
    return LechoCombustible(
        w0_kg_m2=[fila.w0_1h_kg_m2, fila.w0_10h_kg_m2, fila.w0_100h_kg_m2, fila.w0_herb_kg_m2, fila.w0_lenoso_kg_m2],
        sav_1_m=[fila.sav_1h_1_m, 357.6 / 0.3048 if False else 109.0 * M_A_FT, 30.0 * M_A_FT, fila.sav_herb_1_m, fila.sav_lenoso_1_m],
        profundidad_m=float(fila.profundidad_m), mx_muerto_pct=float(fila.mx_muerto_pct), calor_kJ_kg=float(fila.calor_kJ_kg),
        dinamico=bool(fila.dinamico), nombre=str(fila.nombre))
