"""Adaptador del motor v3.1 para el combate común (`combate.py`; decisión D-E3-36).

No cambia ningún archivo de src/v3.1 ni usa su contención (`Simulacion._contener_hora`): el método es el de `combate.py`,
igual que en v4.0. De v3.1 se usan sus primitivas de numba (`_ros_celda`, `_intensidad_celda`, `_intensidad_efectiva`,
`contener_slots`, `_activar`) y el estado CONTENIDA de su autómata, que es el que corta los enlaces a través de la línea
(`_cortado_por_contencion`, dentro de `paso`).

Este módulo importa el motor al cargarse: `motor_v31.py` lo importa recién después de poner src/v3.1 en `sys.path`.

`habilitar()` (la primera vez que hay combate) deja la simulación como si tuviera la contención encendida pero sin empezar
nunca: `contencion_activo` = True con el inicio a 1e9 s, y `t_cont` con la forma de la grilla (apagada es de 1 × 1). Así el
autómata respeta las celdas CONTENIDA y el motor llama en cada cambio de hora a `_contener_hora`, que el conductor redefine
para correr ahí el paso del combate común (después de las tablas, el viento y las velocidades de la hora nueva). Hasta
`habilitar()` nada de eso se toca: una corrida sin combate es idéntica a las de siempre.

Frenar: `contener_slots` (la celda pasa a CONTENIDA y sale del frente activo). Reavivar: `_activar` con su tiempo de llegada
original (vuelve al frente con el avance en cero y propaga hacia sus vecinas combustibles).

Bloquear (una descarga sobre combustible sin quemar): la celda pasa de COMB a CONTENIDA sin haber ardido (su tiempo de llegada
sigue infinito); el autómata no la enciende y corta los enlaces que la atraviesan. Desbloquear: vuelve a COMB. Las celdas
activas que tenían un enlace hacia ella lo retoman solas (el motor mira el estado de la vecina en cada paso).

`sincronizar` mantiene `Simulacion.n_cont`, que el motor usa para no dar el incendio por agotado mientras haya línea que
puede escapar y para el motivo de fin 7 (contenido).
"""
from __future__ import annotations

import numpy as np
from numba import njit

from incendios_sl.simulation.automata import (ACTIVA, COMB, CONTENIDA, QUEMADA, _activar, _intensidad_celda,
                                              _intensidad_efectiva, _ros_celda, contener_slots)
from incendios_sl.simulation.propagacion import ros_direccional

INICIO_NUNCA_S = 1.0e9          # finito: el motor lo suma a la hora de inicio para su registro (un infinito lo rompe)


@njit(cache=True)
def _intensidades(celdas, az, clase, cur_idx, lfmc_bin, u10, v10, tan_pend, az_arriba, R0_tab, coef_tab, waf, kcl,
                  IR_tab, tr_tab, usar_barreras, barrera, ancho_tab, modo_cruce, lam, beta, ll_a, ll_b):
    """(n, K) kW/m: intensidad de Byram de cada celda hacia cada vecina con las tablas de la hora, por la probabilidad de
    cruce si el enlace tiene barrera. Las mismas cuentas que `intensidad_maxima_activas` y `escapes` de v3.1, sin mirar el
    estado de la vecina."""
    n = celdas.shape[0]
    K = az.shape[0]
    out = np.zeros((n, K))
    for q in range(n):
        i = celdas[q, 0]; j = celdas[q, 1]
        r, th, e = _ros_celda(i, j, clase, cur_idx, lfmc_bin, u10, v10, tan_pend, az_arriba, R0_tab, coef_tab, waf, kcl)
        if r <= 0.0:
            continue
        fac = _intensidad_celda(i, j, clase, cur_idx, lfmc_bin, IR_tab, tr_tab)
        for k in range(K):
            I = fac * ros_direccional(r, e, th, az[k])
            out[q, k] = _intensidad_efectiva(I, i, j, k, usar_barreras, barrera, ancho_tab, modo_cruce, lam, beta, ll_a, ll_b)
    return out


class AdaptadorV31:
    def __init__(self, sim, grilla=None):
        """`grilla`: la del dominio (con `xmin`, `ymax` y `res`, en EPSG:5345), para ubicar las descargas. Sin ella (pruebas
        con entradas sintéticas) se toma el origen en (0, filas · res)."""
        self.sim = sim
        self.forma = tuple(int(v) for v in sim.estado.shape)
        self.res = float(sim.e.res_m)
        self.xmin = float(grilla.xmin) if grilla is not None else 0.0
        self.ymax = float(grilla.ymax) if grilla is not None else self.forma[0] * self.res
        self.df = np.asarray(sim.dy, np.int64)
        self.dc = np.asarray(sim.dx, np.int64)
        self.K = len(self.df)
        self.combate = None

    # ------------------------------------------------------------------------------------------ preparación
    def habilitar(self) -> None:
        s = self.sim
        if s.c.contencion_activo:
            raise ValueError("la corrida ya usa la contención propia del motor v3.1: el combate de la app no se le suma")
        s.t_cont = np.full(self.forma, np.inf, np.float32)
        s.c.contencion_inicio_s = INICIO_NUNCA_S
        s.c.contencion_inicio_exacto = False
        s.c.aereo_auto = False
        s.c.contencion_activo = True                 # al final: nunca con `t_cont` de 1 × 1

    def sincronizar(self, n_linea: int) -> None:
        self.sim.n_cont = int(n_linea)

    def hora_utc(self, t_min: float) -> int:
        import pandas as pd
        t = pd.Timestamp(self.sim.e.t_inicio_utc) + pd.Timedelta(minutes=float(t_min))
        return int((t.tz_convert("UTC") if t.tzinfo is not None else t).hour)

    def rc(self, xy) -> tuple[np.ndarray, np.ndarray]:
        xy = np.asarray(xy, "float64")
        return (self.ymax - xy[:, 1]) / self.res, (xy[:, 0] - self.xmin) / self.res

    # ------------------------------------------------------------------------------------------ lectura
    def afectada(self) -> np.ndarray:
        return np.isfinite(self.sim.t_arr)

    def combustible(self) -> np.ndarray:
        return self.sim.estado == COMB

    def activas(self) -> np.ndarray:
        s = self.sim
        cd = s.celda_de[:int(s.n_act[0])].astype(np.int64)
        return cd[:, 0] * self.forma[1] + cd[:, 1]

    def intensidad(self, idx: np.ndarray) -> np.ndarray:
        s, c = self.sim, self.sim.c
        idx = np.asarray(idx, np.int64)
        if not len(idx):
            return np.zeros((0, self.K))
        f, col = np.divmod(idx, self.forma[1])
        celdas = np.ascontiguousarray(np.stack([f, col], axis=1).astype(np.int64))
        return _intensidades(celdas, s.az, s.e.clase, s.cur_idx, s.lfmc_bin, s.u10, s.v10, s.tan_pend, s.az_arriba, s.R0_tab,
                             s.coef_tab, s.waf, s.kcl, s.IR_tab, s.tr_tab, bool(s.usar_barreras), s.barrera, s.ancho_tab,
                             int(s.modo_cruce), float(c.cruce_lambda), float(c.cruce_beta), float(c.longitud_llama_a),
                             float(c.longitud_llama_b))

    # ------------------------------------------------------------------------------------------ frenar y reavivar
    def frenar(self, idx: np.ndarray, t_min: float) -> None:
        s = self.sim
        f, col = np.divmod(np.asarray(idx, np.int64), self.forma[1])
        slots = s.slot_de[f, col].astype(np.int64)
        slots = np.unique(slots[slots >= 0])[::-1]                   # de mayor a menor: `contener_slots` saca del final
        if len(slots):
            contener_slots(np.ascontiguousarray(slots), s.estado, s.slot_de, s.celda_de, s.n_act, s.prog, s.ros_c,
                           int(s.c.vecindad), s.t_cont, float(s.t))

    def bloquear(self, idx: np.ndarray, t_min: float) -> None:
        s = self.sim
        f, col = np.divmod(np.asarray(idx, np.int64), self.forma[1])
        sin_quemar = s.estado[f, col] == COMB
        s.estado[f[sin_quemar], col[sin_quemar]] = CONTENIDA

    def desbloquear(self, idx: np.ndarray, t_min: float) -> None:
        s = self.sim
        f, col = np.divmod(np.asarray(idx, np.int64), self.forma[1])
        bloqueada = (s.estado[f, col] == CONTENIDA) & ~np.isfinite(s.t_arr[f, col])      # CONTENIDA sin haber ardido
        s.estado[f[bloqueada], col[bloqueada]] = COMB

    def reavivar(self, idx: np.ndarray, t_min: float) -> None:
        s = self.sim
        f, col = np.divmod(np.unique(np.asarray(idx, np.int64)), self.forma[1])
        for i, j in zip(f.tolist(), col.tolist()):
            if s.estado[i, j] not in (CONTENIDA, QUEMADA) or not np.isfinite(s.t_arr[i, j]):
                continue                                             # ACTIVA ya propaga; lo demás no ardió
            antes = s.estado[i, j]
            slot = _activar(i, j, float(s.t_arr[i, j]), s.estado, s.t_arr, s.slot_de, s.celda_de, s.n_act, s.prog, s.ros_c,
                            int(s.c.vecindad), s.e.clase, s.cur_idx, s.lfmc_bin, s.u10, s.v10, s.tan_pend, s.az_arriba,
                            s.R0_tab, s.coef_tab, s.waf, s.kcl)
            if slot < 0:
                s.estado[i, j] = antes
                raise RuntimeError("el frente activo del motor está lleno (capacidad_frente): no se pudo reavivar la celda")
            s.t_cont[i, j] = np.inf


__all__ = ["AdaptadorV31", "ACTIVA", "COMB", "CONTENIDA", "QUEMADA", "INICIO_NUNCA_S"]
