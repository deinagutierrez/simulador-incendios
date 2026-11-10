"""Modelo de propagación de Rothermel (1972) con la formulación de Andrews (2018, RMRS-GTR-371).

Vectorizado: todas las entradas son arrays de forma (N,) (una fila por celda activa) o (N, 5)
para las clases de combustible en el orden [1 h, 10 h, 100 h, herbáceo, leñoso].
El herbáceo se divide internamente en herbáceo muerto (curado) y herbáceo vivo.

Unidades internas: imperiales (lb, ft, min, BTU), como la publicación. Las funciones de
salida convierten a m/min, kW/m y m.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

T_AC_A_LB_FT2 = 0.0459137     # 1 t/ac = 0.0459137 lb/ft²
FT_MIN_A_M_MIN = 0.3048
BTU_FT_S_A_KW_M = 3.4613
MI_H_A_FT_MIN = 88.0
RHO_P = 32.0                  # densidad de partícula lb/ft³
S_T = 0.0555                  # contenido mineral total
S_E = 0.010                   # contenido mineral efectivo
ETA_S = 0.174 * S_E ** (-0.19)


@dataclass
class SalidaRothermel:
    R0: np.ndarray          # ft/min, sin viento ni pendiente
    IR: np.ndarray          # BTU/ft²/min, intensidad de reacción
    sigma: np.ndarray       # 1/ft, SAV característico
    beta: np.ndarray
    beta_op: np.ndarray
    phi_w: np.ndarray       # factor de viento (con el viento dado)
    phi_s: np.ndarray       # factor de pendiente
    B: np.ndarray
    C: np.ndarray
    E: np.ndarray
    mx_muerto: np.ndarray
    mf_muerto: np.ndarray   # humedad ponderada del combustible muerto
    tau_min: np.ndarray     # tiempo de residencia (Anderson 1969): 384/σ min
    extinguido: np.ndarray  # True si la humedad muerta supera Mx (no propaga)
    U_lim: np.ndarray | None = None   # tope del viento EFECTIVO (ft/min; Andrews et al. 2013), None = sin tope posterior

LIMITES_VIENTO = ("rothermel_1972", "andrews_2013", "ninguno")


def _grupo_tamano(sigma: np.ndarray) -> np.ndarray:
    """Grupos de clase de tamaño para los factores g_ij (Andrews 2018, tabla 5)."""
    g = np.full(sigma.shape, -1, dtype=np.int8)
    g[sigma >= 1200] = 0
    g[(sigma >= 192) & (sigma < 1200)] = 1
    g[(sigma >= 96) & (sigma < 192)] = 2
    g[(sigma >= 48) & (sigma < 96)] = 3
    g[(sigma >= 16) & (sigma < 48)] = 4
    g[(sigma > 0) & (sigma < 16)] = 5      # v4.0 (P9): antes quedaba en −1 (g = 0, carga excluida); ningún SB40 la usa
    return g


def rothermel(w_tac: np.ndarray, sav: np.ndarray, profundidad_ft: np.ndarray, mx_muerto: np.ndarray,
              calor_muerto: np.ndarray, calor_vivo: np.ndarray, curado: np.ndarray,
              m1: np.ndarray, m10: np.ndarray, m100: np.ndarray, m_herb: np.ndarray, m_woody: np.ndarray,
              U_ftmin: np.ndarray, tan_pendiente: np.ndarray, limitar_viento: bool = True,
              limite_viento: str = "rothermel_1972") -> SalidaRothermel:
    """Rothermel 1972 para N celdas.

    w_tac (N,5) cargas t/ac; sav (N,5) 1/ft; curado (N,) fracción de herbáceo muerto [0,1];
    humedades en fracción (0.08 = 8 %); U_ftmin viento a media llama; tan_pendiente = tan(θ).
    Límite de viento (`limite_viento`, ignorado si `limitar_viento` es False):
    - `rothermel_1972`: U ≤ 0,9·I_R sobre el viento a media llama, antes de combinar con la pendiente (V.4 original);
    - `andrews_2013`: U_eff ≤ 96,8·I_R^(1/3) (ft/min, I_R en BTU/ft²/min) sobre el viento EFECTIVO; se guarda en
      `U_lim` y lo aplica `combinar_viento_pendiente` (Andrews, Cruz & Rothermel 2013);
    - `ninguno`: sin tope.
    """
    if limite_viento not in LIMITES_VIENTO:
        raise ValueError(f"limite_viento '{limite_viento}' desconocido (opciones: {', '.join(LIMITES_VIENTO)})")
    N = w_tac.shape[0]
    # --- clases: 0 1h, 1 10h, 2 100h, 3 herb muerto, 4 herb vivo, 5 leñoso vivo --------------
    w = np.zeros((N, 6)); s = np.zeros((N, 6)); M = np.zeros((N, 6))
    w[:, 0:3] = w_tac[:, 0:3] * T_AC_A_LB_FT2
    herb = w_tac[:, 3] * T_AC_A_LB_FT2
    w[:, 3] = herb * curado
    w[:, 4] = herb * (1.0 - curado)
    w[:, 5] = w_tac[:, 4] * T_AC_A_LB_FT2
    s[:, 0:3] = sav[:, 0:3]
    s[:, 3] = sav[:, 3]; s[:, 4] = sav[:, 3]; s[:, 5] = sav[:, 4]
    M[:, 0] = m1; M[:, 1] = m10; M[:, 2] = m100; M[:, 3] = m1; M[:, 4] = m_herb; M[:, 5] = m_woody
    muerto = np.array([1, 1, 1, 1, 0, 0], bool)
    vivo = ~muerto
    presente = w > 0

    # --- factores de ponderación ----------------------------------------------------------------
    A = np.where(presente, s * w / RHO_P, 0.0)
    A_d = A[:, muerto].sum(1); A_l = A[:, vivo].sum(1); A_t = A_d + A_l
    with np.errstate(divide="ignore", invalid="ignore"):
        f = np.zeros((N, 6))
        f[:, muerto] = np.where(A_d[:, None] > 0, A[:, muerto] / A_d[:, None], 0.0)
        f[:, vivo] = np.where(A_l[:, None] > 0, A[:, vivo] / A_l[:, None], 0.0)
        f_d = np.where(A_t > 0, A_d / A_t, 0.0); f_l = np.where(A_t > 0, A_l / A_t, 0.0)
    sigma_d = (f[:, muerto] * s[:, muerto]).sum(1); sigma_l = (f[:, vivo] * s[:, vivo]).sum(1)
    sigma = f_d * sigma_d + f_l * sigma_l
    sigma = np.maximum(sigma, 1.0)
    w_tot = w.sum(1)
    delta = np.maximum(profundidad_ft, 1e-6)
    rho_b = w_tot / delta
    beta = rho_b / RHO_P
    beta_op = 3.348 * sigma ** (-0.8189)
    ratio = np.where(beta_op > 0, beta / beta_op, 0.0)
    Aexp = 133.0 * sigma ** (-0.7913)
    G_max = sigma ** 1.5 / (495.0 + 0.0594 * sigma ** 1.5)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        G = np.where(ratio > 0, G_max * ratio ** Aexp * np.exp(Aexp * (1.0 - ratio)), 0.0)
    xi = np.exp((0.792 + 0.681 * np.sqrt(sigma)) * (beta + 0.1)) / (192.0 + 0.2595 * sigma)

    # --- cargas netas con g_ij (mismo grupo de tamaño y categoría) ------------------------------
    grp = _grupo_tamano(s)
    g = np.zeros((N, 6))
    for cat in (muerto, vivo):
        idx = np.where(cat)[0]
        for i in idx:
            mismo = np.zeros((N, 6), bool)
            for j in idx:
                mismo[:, j] = (grp[:, j] == grp[:, i]) & (grp[:, i] >= 0) & presente[:, j]
            g[:, i] = (f * mismo).sum(1)
    wn = w * (1.0 - S_T)
    wn_d = (g[:, muerto] * wn[:, muerto]).sum(1); wn_l = (g[:, vivo] * wn[:, vivo]).sum(1)

    # --- humedades ponderadas y de extinción ----------------------------------------------------
    Mf_d = (f[:, muerto] * M[:, muerto]).sum(1)
    Mf_l = (f[:, vivo] * M[:, vivo]).sum(1)
    with np.errstate(divide="ignore", invalid="ignore"):
        e_d = np.where(presente[:, muerto], np.exp(-138.0 / s[:, muerto]), 0.0)
        e_l = np.where(presente[:, vivo], np.exp(-500.0 / s[:, vivo]), 0.0)
        num_W = (w[:, muerto] * e_d).sum(1); den_W = (w[:, vivo] * e_l).sum(1)
        W = np.where(den_W > 0, num_W / den_W, 0.0)
        Mfd_p = np.where(num_W > 0, (w[:, muerto] * M[:, muerto] * e_d).sum(1) / num_W, 0.0)
        mx_l = np.maximum(2.9 * W * (1.0 - Mfd_p / np.maximum(mx_muerto, 1e-6)) - 0.226, mx_muerto)
    r_d = np.clip(np.where(mx_muerto > 0, Mf_d / mx_muerto, 1.0), 0, 1)
    r_l = np.clip(np.where(mx_l > 0, Mf_l / mx_l, 1.0), 0, 1)
    eta_d = 1.0 - 2.59 * r_d + 5.11 * r_d ** 2 - 3.52 * r_d ** 3
    eta_l = 1.0 - 2.59 * r_l + 5.11 * r_l ** 2 - 3.52 * r_l ** 3
    eta_d = np.where(A_l == 0, eta_d, eta_d)  # (explícito: sin vivos, eta_l multiplica carga nula)

    IR = G * (wn_d * calor_muerto * eta_d + wn_l * calor_vivo * eta_l) * ETA_S
    IR = np.maximum(IR, 0.0)

    # --- sumidero de calor ---------------------------------------------------------------------
    eps = np.where(presente, np.exp(-138.0 / np.maximum(s, 1.0)), 0.0)
    Qig = 250.0 + 1116.0 * M
    sink_d = (f[:, muerto] * eps[:, muerto] * Qig[:, muerto]).sum(1)
    sink_l = (f[:, vivo] * eps[:, vivo] * Qig[:, vivo]).sum(1)
    heat_sink = rho_b * (f_d * sink_d + f_l * sink_l)
    with np.errstate(divide="ignore", invalid="ignore"):
        R0 = np.where(heat_sink > 0, IR * xi / heat_sink, 0.0)

    # --- viento y pendiente --------------------------------------------------------------------
    C = 7.47 * np.exp(-0.133 * sigma ** 0.55)
    B = 0.02526 * sigma ** 0.54
    E = 0.715 * np.exp(-3.59e-4 * sigma)
    U = np.maximum(U_ftmin, 0.0)
    U_lim = None
    if limitar_viento and limite_viento == "rothermel_1972":
        U = np.minimum(U, 0.9 * IR)   # límite de viento efectivo de Rothermel (1972)
    elif limitar_viento and limite_viento == "andrews_2013":
        U_lim = 96.8 * np.cbrt(IR)
    with np.errstate(divide="ignore", invalid="ignore"):
        phi_w = np.where(ratio > 0, C * U ** B * ratio ** (-E), 0.0)
    phi_s = 5.275 * np.maximum(beta, 1e-6) ** (-0.3) * tan_pendiente ** 2
    tau = 384.0 / sigma
    extinguido = Mf_d >= mx_muerto
    R0 = np.where(extinguido | (w_tot <= 0), 0.0, R0)
    return SalidaRothermel(R0, IR, sigma, beta, beta_op, phi_w, phi_s, B, C, E, mx_muerto, Mf_d, tau, extinguido, U_lim)


def combinar_viento_pendiente(sal: SalidaRothermel, dir_viento_hacia_deg: np.ndarray,
                              orientacion_deg: np.ndarray, plano: np.ndarray):
    """Suma vectorial de los efectos de viento y pendiente (BehavePlus / FARSITE).

    - El viento empuja hacia `dir_viento_hacia_deg` (0 = N, horario).
    - La pendiente empuja ladera arriba: opuesto a la orientación (que es la dirección de bajada).
    Devuelve (R_max ft/min, rumbo de la cabeza en grados, viento efectivo ft/min, phi_eff).
    """
    phi_s = np.where(plano, 0.0, sal.phi_s)
    dir_arriba = (orientacion_deg + 180.0) % 360.0
    # componentes (este, norte) de cada vector
    wx = sal.phi_w * np.sin(np.deg2rad(dir_viento_hacia_deg)); wy = sal.phi_w * np.cos(np.deg2rad(dir_viento_hacia_deg))
    sx = phi_s * np.sin(np.deg2rad(dir_arriba)); sy = phi_s * np.cos(np.deg2rad(dir_arriba))
    x = wx + sx; y = wy + sy
    phi_eff = np.hypot(x, y)
    rumbo = np.where(phi_eff > 1e-9, (np.degrees(np.arctan2(x, y)) + 360.0) % 360.0, dir_viento_hacia_deg)
    R_max = sal.R0 * (1.0 + phi_eff)
    # viento efectivo equivalente (invierte phi_w = C U^B ratio^-E)
    ratio = np.where(sal.beta_op > 0, sal.beta / sal.beta_op, 1.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        U_eff = np.where((sal.C > 0) & (phi_eff > 0),
                         (phi_eff / (sal.C * ratio ** (-sal.E))) ** (1.0 / sal.B), 0.0)
    U_eff = np.where(np.isfinite(U_eff), U_eff, 0.0)
    if sal.U_lim is not None:
        # Andrews, Cruz & Rothermel (2013): tope sobre el viento efectivo, después de combinar
        m = U_eff > sal.U_lim
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            phi_lim = sal.C * sal.U_lim ** sal.B * ratio ** (-sal.E)
        phi_eff = np.where(m, phi_lim, phi_eff)
        U_eff = np.minimum(U_eff, sal.U_lim)
        R_max = sal.R0 * (1.0 + phi_eff)
    return R_max, rumbo, U_eff, phi_eff


def intensidad_byram(IR: np.ndarray, R_ftmin: np.ndarray, tau_min: np.ndarray):
    """Intensidad lineal de Byram (kW/m) y longitud de llama (m) a partir de I_R, ROS y residencia."""
    H_A = IR * tau_min                      # BTU/ft²
    I_B = H_A * R_ftmin / 60.0              # BTU/ft/s
    L_ft = 0.45 * np.maximum(I_B, 0.0) ** 0.46
    return I_B * BTU_FT_S_A_KW_M, L_ft * FT_MIN_A_M_MIN
