"""Autómata celular de propagación (núcleo numba).

Esquema: tiempos de llegada por avance acumulado en enlaces (versión discreta del principio de tiempo mínimo de
viaje). Cada celda del frente activo mantiene, para cada uno de sus 16 (u 8) vecinos no quemados, la fracción del
enlace recorrida por el fuego: f += Δt·R(θ)/d. Cuando f ≥ 1 el vecino se enciende en el instante exacto del cruce y
continúa propagando en el resto del paso (sin límite de "una celda por paso"). La ROS cambia cada hora con la
meteorología y el viento; el avance ya acumulado se conserva (función escalonada, exacta para ROS constante por hora).

Estados: 255 fuera de dominio, 0 no combustible, 1 combustible, 2 frente activo (puede encender vecinos),
3 quemada (sin vecinos combustibles por encender), 4 contenida (quemada y asegurada por el combate; puede escapar).
Una celda no vuelve nunca a 1.

Modelo v2 (docs/10): barreras lineales sobre enlaces con cruce probabilístico según longitud de llama / ancho, y
contención por combate. Con `modo_cruce = 0` y sin contención el comportamiento es idéntico al v1.
"""
from __future__ import annotations

import math

import numpy as np
from numba import njit

from .propagacion import combinar_viento_pendiente, excentricidad, ros_direccional

FUERA, NOCOMB, COMB, ACTIVA, QUEMADA, CONTENIDA = 255, 0, 1, 2, 3, 4
FT_MIN_A_M_S = 0.00508
BTU_FT2_MIN_A_KW_M2 = 0.189275     # 1 BTU/ft²/min = 1,05506 kJ / (0,092903 m² · 60 s)


def estencil(n: int, res: float):
    """Desplazamientos (dfila, dcol), distancia (m) y azimut (rad) de cada vecino."""
    if n == 8:
        offs = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]
    elif n == 16:
        offs = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1),
                (-2, 1), (-1, 2), (1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1)]
    else:
        raise ValueError("vecindad debe ser 8 o 16")
    dy = np.array([o[0] for o in offs], np.int64); dx = np.array([o[1] for o in offs], np.int64)
    dist = np.hypot(dy, dx) * res
    az = np.arctan2(dx.astype(float), -dy.astype(float))   # azimut: norte = fila decreciente
    return dy, dx, dist.astype(np.float64), az.astype(np.float64)


# ---------------------------------------------------------------- utilidades deterministas
@njit(cache=True)
def u01(semilla, i, j, k, h):
    """Uniforme [0,1) determinista por (semilla, celda, enlace, hora): mezcla tipo splitmix64.
    Independiente del orden de procesamiento → reproducible bit a bit."""
    x = np.uint64(semilla) * np.uint64(0x9E3779B97F4A7C15)
    x ^= np.uint64(i + 1) * np.uint64(0xBF58476D1CE4E5B9)
    x ^= np.uint64(j + 1) * np.uint64(0x94D049BB133111EB)
    x ^= np.uint64(k + 1) * np.uint64(0xD6E8FEB86659FD93)
    x ^= np.uint64(h + 1) * np.uint64(0xA0761D6478BD642F)
    x ^= x >> np.uint64(30); x *= np.uint64(0xBF58476D1CE4E5B9)
    x ^= x >> np.uint64(27); x *= np.uint64(0x94D049BB133111EB)
    x ^= x >> np.uint64(31)
    return float(x >> np.uint64(11)) * (1.0 / 9007199254740992.0)


@njit(cache=True)
def longitud_llama(I_kw_m, a, b):
    """Byram (1959): L = a·I^b, con I en kW/m (a = 0,0775, b = 0,46 → m)."""
    if I_kw_m <= 0.0:
        return 0.0
    return a * I_kw_m ** b


@njit(cache=True)
def p_cruce(L, W, modo, lam, beta):
    """Probabilidad de que el fuego cruce una barrera de ancho W con longitud de llama L (docs/10 §3.2).
    modo 1: logística en L/W; modo 2: umbral determinista (1 si L/W > λ)."""
    if W <= 0.0:
        return 1.0
    x = L / W
    if modo == 2:
        return 1.0 if x > lam else 0.0
    z = -beta * (x - lam)
    if z > 50.0:
        return 0.0
    if z < -50.0:
        return 1.0
    return 1.0 / (1.0 + math.exp(z))


# ---------------------------------------------------------------- ROS por celda
@njit(cache=True)
def _ros_celda(i, j, clase, cur_idx, lfmc_bin, u10, v10, tan_pend, az_arriba, R0_tab, coef_tab, waf, kcl):
    """(R_cabeza m/s, theta_max, e) para la celda (i, j) con las tablas de la hora."""
    c = clase[i, j]
    if c == 0:
        return 0.0, 0.0, 0.0
    k = cur_idx[i, j]
    R0 = R0_tab[c, lfmc_bin[i, j], k]
    if R0 <= 0.0:
        return 0.0, 0.0, 0.0
    C = coef_tab[c, k, 0]; B = coef_tab[c, k, 1]; ratioE = coef_tab[c, k, 2]; phis_coef = coef_tab[c, k, 3]
    ueff, theta, phic = combinar_viento_pendiente(u10[i, j], v10[i, j], waf[c], tan_pend[i, j], az_arriba[i, j], C, B, ratioE, phis_coef)
    r = kcl[c] * R0 * (1.0 + phic) * FT_MIN_A_M_S
    return r, theta, excentricidad(ueff)


@njit(cache=True)
def _intensidad_celda(i, j, clase, cur_idx, lfmc_bin, IR_tab, tr_tab):
    """Factor I_R·t_r (kJ/m²) de la celda: I_B(θ) = factor · R(θ) [kW/m con R en m/s]."""
    c = clase[i, j]
    if c == 0:
        return 0.0
    return IR_tab[c, lfmc_bin[i, j], cur_idx[i, j]] * tr_tab[c, cur_idx[i, j]]


@njit(cache=True)
def _cortado_por_contencion(estado, i, j, k, dy, dx):
    """True si el enlace k desde (i, j) atraviesa una línea de contención: en los saltos de caballo (2 celdas) si
    alguna de las dos celdas intermedias está contenida; en las diagonales si alguna de las dos celdas ortogonales
    lo está (la línea no se filtra por sus esquinas). Evita que una línea de una celda de ancho sea sorteada por el
    estencil de 16 vecinos."""
    a = dy[k]; b = dx[k]
    if a == 0 or b == 0:
        return False
    if abs(a) == 2:
        h = a // 2
        return estado[i + h, j] == CONTENIDA or estado[i + h, j + b] == CONTENIDA
    if abs(b) == 2:
        h = b // 2
        return estado[i, j + h] == CONTENIDA or estado[i + a, j + h] == CONTENIDA
    return estado[i + a, j] == CONTENIDA or estado[i, j + b] == CONTENIDA


@njit(cache=True)
def _activar(i, j, t_ign, estado, t_arr, slot_de, celda_de, n_act, prog, ros_c, nvec, clase, cur_idx, lfmc_bin,
             u10, v10, tan_pend, az_arriba, R0_tab, coef_tab, waf, kcl):
    estado[i, j] = ACTIVA
    t_arr[i, j] = t_ign
    s = n_act[0]
    if s >= celda_de.shape[0]:
        return -1
    celda_de[s, 0] = i; celda_de[s, 1] = j
    slot_de[i, j] = s
    for k in range(nvec):
        prog[s, k] = 0.0
    r, th, e = _ros_celda(i, j, clase, cur_idx, lfmc_bin, u10, v10, tan_pend, az_arriba, R0_tab, coef_tab, waf, kcl)
    ros_c[s, 0] = r; ros_c[s, 1] = th; ros_c[s, 2] = e
    n_act[0] = s + 1
    return s


@njit(cache=True)
def _liberar(s, estado, slot_de, celda_de, n_act, prog, ros_c, nvec, estado_final):
    i = celda_de[s, 0]; j = celda_de[s, 1]
    estado[i, j] = estado_final
    slot_de[i, j] = -1
    last = n_act[0] - 1
    if s != last:
        celda_de[s, 0] = celda_de[last, 0]; celda_de[s, 1] = celda_de[last, 1]
        slot_de[celda_de[s, 0], celda_de[s, 1]] = s
        for k in range(nvec):
            prog[s, k] = prog[last, k]
        ros_c[s, 0] = ros_c[last, 0]; ros_c[s, 1] = ros_c[last, 1]; ros_c[s, 2] = ros_c[last, 2]
    n_act[0] = last


@njit(cache=True)
def recalcular_ros_activas(estado, celda_de, n_act, ros_c, clase, cur_idx, lfmc_bin, u10, v10, tan_pend, az_arriba, R0_tab, coef_tab, waf, kcl):
    for s in range(n_act[0]):
        i = celda_de[s, 0]; j = celda_de[s, 1]
        r, th, e = _ros_celda(i, j, clase, cur_idx, lfmc_bin, u10, v10, tan_pend, az_arriba, R0_tab, coef_tab, waf, kcl)
        ros_c[s, 0] = r; ros_c[s, 1] = th; ros_c[s, 2] = e


@njit(cache=True)
def paso(t, dt, estado, t_arr, slot_de, celda_de, n_act, prog, ros_c, dy, dx, dist, az, clase, cur_idx, lfmc_bin,
         u10, v10, tan_pend, az_arriba, R0_tab, coef_tab, waf, kcl, ros_min,
         usar_barreras, barrera, ancho_tab, bloq, IR_tab, tr_tab, modo_cruce, lam, beta, ll_a, ll_b, semilla, hora_idx,
         cruces, bloqueos, hay_contencion):
    """Avanza un paso Δt. Devuelve (n_encendidas, suma de tasas de avance > 0, desbordamiento, n_bloqueos_nuevos).

    Barreras (v2): un enlace con barrera que alcanza f ≥ 1 sortea el cruce con P(L/W); si falla queda bloqueado
    (bit k de `bloq[i,j]`) hasta el próximo cambio horario, cuando se vuelve a sortear. Un enlace bloqueado mantiene la
    celda activa pero no suma avance."""
    nfil, ncol = estado.shape
    nvec = dy.shape[0]
    n_ign = 0
    n_bloq = 0
    avance_total = 0.0
    desborde = 0
    # cola de celdas a procesar en este paso: (slot, tiempo desde el que avanzan)
    cola_s = np.empty(1024, np.int64); cola_t = np.empty(1024, np.float64)
    nq = 0
    for s in range(n_act[0]):
        cola_s[nq] = s; cola_t[nq] = t; nq += 1
        if nq >= cola_s.shape[0]:
            cola_s = np.concatenate((cola_s, np.empty(cola_s.shape[0], np.int64)))
            cola_t = np.concatenate((cola_t, np.empty(cola_t.shape[0], np.float64)))
    q = 0
    t_fin = t + dt
    while q < nq:
        s = cola_s[q]; t0 = cola_t[q]; q += 1
        if s >= n_act[0]:
            continue
        i = celda_de[s, 0]; j = celda_de[s, 1]
        r = ros_c[s, 0]; th = ros_c[s, 1]; e = ros_c[s, 2]
        quedan = 0
        for k in range(nvec):
            ii = i + dy[k]; jj = j + dx[k]
            if ii < 0 or ii >= nfil or jj < 0 or jj >= ncol:
                continue
            if estado[ii, jj] != COMB:
                continue
            if hay_contencion and _cortado_por_contencion(estado, i, j, k, dy, dx):
                continue                     # el enlace atraviesa una línea de contención
            quedan += 1
            if r <= ros_min:
                continue
            if usar_barreras and (bloq[i, j] >> np.uint16(k)) & np.uint16(1):
                continue                     # bloqueado en esta hora
            rk = ros_direccional(r, e, th, az[k])
            if rk <= 0.0:
                continue
            tasa = rk / dist[k]              # fracción del enlace por segundo
            avance_total += tasa
            f = prog[s, k] + tasa * (t_fin - t0)
            if f >= 1.0:
                if usar_barreras and barrera[i, j, k] > 0:
                    W = ancho_tab[barrera[i, j, k]]
                    I_B = _intensidad_celda(i, j, clase, cur_idx, lfmc_bin, IR_tab, tr_tab) * rk
                    P = p_cruce(longitud_llama(I_B, ll_a, ll_b), W, modo_cruce, lam, beta)
                    if u01(semilla, i, j, k, hora_idx) >= P:
                        bloq[i, j] |= np.uint16(1) << np.uint16(k)
                        prog[s, k] = 1.0
                        n_bloq += 1
                        if bloqueos[i, j] < 65535:
                            bloqueos[i, j] += 1
                        continue
                    if cruces[i, j] < 65535:
                        cruces[i, j] += 1
                t_ign = t_fin - (f - 1.0) / tasa
                if t_ign < t0:
                    t_ign = t0
                s2 = _activar(ii, jj, t_ign, estado, t_arr, slot_de, celda_de, n_act, prog, ros_c, nvec, clase, cur_idx,
                              lfmc_bin, u10, v10, tan_pend, az_arriba, R0_tab, coef_tab, waf, kcl)
                if s2 < 0:
                    desborde = 1
                    estado[ii, jj] = COMB
                    continue
                n_ign += 1
                quedan -= 1
                if nq >= cola_s.shape[0]:
                    cola_s = np.concatenate((cola_s, np.empty(cola_s.shape[0], np.int64)))
                    cola_t = np.concatenate((cola_t, np.empty(cola_t.shape[0], np.float64)))
                cola_s[nq] = s2; cola_t[nq] = t_ign; nq += 1
                prog[s, k] = 1.0
            else:
                prog[s, k] = f
        if quedan == 0:
            # la celda no tiene nada más que encender: pasa a quemada (sin reencendido posible)
            # nota: el slot se libera al final del paso para no invalidar la cola
            prog[s, 0] = -1.0
    # liberar slots marcados (de atrás hacia adelante para que el swap-remove no afecte índices no procesados)
    s = n_act[0] - 1
    while s >= 0:
        if prog[s, 0] < 0.0:
            _liberar(s, estado, slot_de, celda_de, n_act, prog, ros_c, nvec, QUEMADA)
        s -= 1
    return n_ign, avance_total, desborde, n_bloq


# ---------------------------------------------------------------- contención (v2)
@njit(cache=True)
def _intensidad_efectiva(I, i, j, k, usar_barreras, barrera, ancho_tab, modo_cruce, lam, beta, ll_a, ll_b):
    """Intensidad esperada a través del enlace: I·P(cruce) si hay barrera (anclaje de la línea en caminos)."""
    if usar_barreras and barrera[i, j, k] > 0:
        return I * p_cruce(longitud_llama(I, ll_a, ll_b), ancho_tab[barrera[i, j, k]], modo_cruce, lam, beta)
    return I


@njit(cache=True)
def intensidad_maxima_activas(estado, celda_de, n_act, ros_c, dy, dx, az, clase, cur_idx, lfmc_bin, IR_tab, tr_tab,
                              usar_barreras, barrera, ancho_tab, modo_cruce, lam, beta, ll_a, ll_b):
    """Para cada celda activa, la intensidad de Byram máxima (kW/m) hacia sus vecinos combustibles no quemados,
    ponderada por la probabilidad de cruce cuando el enlace tiene barrera; −1 si no tiene vecinos por encender."""
    nfil, ncol = estado.shape
    nvec = dy.shape[0]
    out = np.full(n_act[0], -1.0)
    for s in range(n_act[0]):
        i = celda_de[s, 0]; j = celda_de[s, 1]
        r = ros_c[s, 0]; th = ros_c[s, 1]; e = ros_c[s, 2]
        fac = _intensidad_celda(i, j, clase, cur_idx, lfmc_bin, IR_tab, tr_tab)
        mx = -1.0
        for k in range(nvec):
            ii = i + dy[k]; jj = j + dx[k]
            if ii < 0 or ii >= nfil or jj < 0 or jj >= ncol or estado[ii, jj] != COMB:
                continue
            if _cortado_por_contencion(estado, i, j, k, dy, dx):
                continue
            I = fac * ros_direccional(r, e, th, az[k]) if r > 0.0 else 0.0
            I = _intensidad_efectiva(I, i, j, k, usar_barreras, barrera, ancho_tab, modo_cruce, lam, beta, ll_a, ll_b)
            if I > mx:
                mx = I
        out[s] = mx
    return out


@njit(cache=True)
def vecino_exterior(estado, celda_de, n_act, dy, dx, ext, r0, c0):
    """True por slot si la celda activa es borde exterior: tiene, entre sus 8 vecinos inmediatos, alguno combustible
    (no cortado por contención) que pertenece al exterior del incendio (`ext`: máscara de combustible conectado con el
    borde de la ventana, con origen (r0, c0)). Excluye las celdas de segunda fila (solo alcanzan el exterior por saltos
    de caballo) y las que solo lindan con islas interiores: ninguna justifica línea."""
    nfil, ncol = estado.shape
    nvec = min(dy.shape[0], 8)
    out = np.zeros(n_act[0], np.bool_)
    for s in range(n_act[0]):
        i = celda_de[s, 0]; j = celda_de[s, 1]
        for k in range(nvec):
            ii = i + dy[k]; jj = j + dx[k]
            if ii < 0 or ii >= nfil or jj < 0 or jj >= ncol or estado[ii, jj] != COMB:
                continue
            if _cortado_por_contencion(estado, i, j, k, dy, dx):
                continue
            ri = ii - r0; cj = jj - c0
            if ri >= 0 and ri < ext.shape[0] and cj >= 0 and cj < ext.shape[1] and ext[ri, cj]:
                out[s] = True
                break
    return out


@njit(cache=True)
def contener_slots(slots_desc, estado, slot_de, celda_de, n_act, prog, ros_c, nvec, t_cont, t_ahora):
    """Asegura (estado CONTENIDA) las celdas activas de los slots dados, ordenados de mayor a menor."""
    for q in range(slots_desc.shape[0]):
        s = slots_desc[q]
        i = celda_de[s, 0]; j = celda_de[s, 1]
        t_cont[i, j] = t_ahora
        _liberar(s, estado, slot_de, celda_de, n_act, prog, ros_c, nvec, CONTENIDA)


@njit(cache=True)
def escapes(celdas, estado, t_arr, slot_de, celda_de, n_act, prog, ros_c, nvec, dy, dx, az, clase, cur_idx, lfmc_bin,
            u10, v10, tan_pend, az_arriba, R0_tab, coef_tab, waf, kcl, IR_tab, tr_tab, I_escape, p_escape, semilla, hora_idx,
            usar_barreras, barrera, ancho_tab, modo_cruce, lam, beta, ll_a, ll_b):
    """Celdas contenidas cuya intensidad (efectiva a través de barreras) hacia algún vecino combustible supera I_escape
    se reactivan con probabilidad p_escape (sorteo determinista por celda y hora). Devuelve el número de escapes."""
    nfil, ncol = estado.shape
    n = 0
    for q in range(celdas.shape[0]):
        i = celdas[q, 0]; j = celdas[q, 1]
        if estado[i, j] != CONTENIDA:
            continue
        r, th, e = _ros_celda(i, j, clase, cur_idx, lfmc_bin, u10, v10, tan_pend, az_arriba, R0_tab, coef_tab, waf, kcl)
        if r <= 0.0:
            continue
        fac = _intensidad_celda(i, j, clase, cur_idx, lfmc_bin, IR_tab, tr_tab)
        mx = -1.0
        for k in range(nvec):
            ii = i + dy[k]; jj = j + dx[k]
            if ii < 0 or ii >= nfil or jj < 0 or jj >= ncol or estado[ii, jj] != COMB:
                continue
            if _cortado_por_contencion(estado, i, j, k, dy, dx):
                continue
            I = _intensidad_efectiva(fac * ros_direccional(r, e, th, az[k]), i, j, k, usar_barreras, barrera, ancho_tab, modo_cruce, lam, beta, ll_a, ll_b)
            if I > mx:
                mx = I
        if mx > I_escape and u01(semilla, i, j, 99, hora_idx) < p_escape:
            s = _activar(i, j, t_arr[i, j], estado, t_arr, slot_de, celda_de, n_act, prog, ros_c, nvec, clase, cur_idx, lfmc_bin,
                         u10, v10, tan_pend, az_arriba, R0_tab, coef_tab, waf, kcl)
            if s < 0:
                estado[i, j] = CONTENIDA
                break
            n += 1
    return n


def preparar_estado(mascara: np.ndarray, clase: np.ndarray) -> np.ndarray:
    estado = np.full(mascara.shape, FUERA, np.uint8)
    dentro = mascara == 1
    estado[dentro] = np.where(clase[dentro] == 0, NOCOMB, COMB).astype(np.uint8)
    return estado
