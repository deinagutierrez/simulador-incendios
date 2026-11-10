"""Motor de simulación: prepara tablas por hora, ejecuta el autómata y persiste resultados.

Uso programático:
    sim = Simulacion(entradas, cfg)      # entradas: arrays y series (ver EntradasSimulacion)
    sim.ejecutar(callback=None)          # devuelve el registro final
    sim.guardar(dir_resultados)

Las entradas pueden venir de los productos de la Etapa 3 (`cargar_entradas_evento`) o ser sintéticas (pruebas).
Modelo v2 (docs/10): barreras lineales (`EntradasSimulacion.barreras`, `ConfigSimulacion.barreras_activo`) y
contención por combate (`ConfigSimulacion.contencion_activo`). Ambos apagados → resultado idéntico al v1.
Despacho local (docs/13): `despacho_modo = "snmf"` escala la tasa de línea con la superficie simulada según los reportes del
SNMF y `aereo_auto` sortea la llegada de medios aéreos por clase de tamaño; con los valores por defecto no cambia nada.
"""
from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
import psutil

from .. import __version__
from ..fuels.tabla import cargar_tabla
from .automata import (ACTIVA, COMB, CONTENIDA, FUERA, NOCOMB, QUEMADA, BTU_FT2_MIN_A_KW_M2, estencil, paso, preparar_estado,
                       recalcular_ros_activas, _activar, intensidad_maxima_activas, contener_slots, escapes, vecino_exterior)
from .rothermel import LechoCombustible, lecho_desde_fila, rothermel_lecho

log = logging.getLogger(__name__)

MOTIVOS = {1: "fin documentado del incendio alcanzado", 2: "fin de los datos meteorológicos",
           3: "sin propagación físicamente posible según el modelo (horas consecutivas sin avance)",
           4: "límite de seguridad computacional (pasos/tiempo)", 5: "frente agotado: no quedan celdas activas",
           6: "desbordamiento de la capacidad del frente activo (aumentar capacidad_frente)",
           7: "incendio contenido: sin celdas activas, perímetro asegurado hasta el fin documentado"}


@dataclass
class EntradasSimulacion:
    res_m: float
    mascara: np.ndarray                 # uint8 1 dentro
    clase: np.ndarray                   # uint8 clases de combustible
    pendiente_deg: np.ndarray           # float32
    orientacion_deg: np.ndarray         # float32 azimut cuesta abajo (−1 plano)
    curado: np.ndarray                  # float32 fracción herbácea curada
    lfmc_herb: np.ndarray               # float32 % (NaN -> valor por defecto)
    lfmc_lenoso: np.ndarray             # float32 %
    tabla: pd.DataFrame                 # tabla_combustibles_v1
    meteo: pd.DataFrame                 # serie del dominio: time_utc, temperature_2m, relative_humidity_2m, wind_speed_10m_vectorial, wind_direction_10m, precipitation
    humedad: pd.DataFrame               # time_utc, m_1h_pct, m_10h_pct, m_100h_pct, lluvia_24h_mm
    viento: Callable[[float, float], tuple[np.ndarray, np.ndarray]] | None   # (vel, dir_desde) -> (U10, V10) a 30 m
    igniciones: list[tuple[int, int, float]]   # (fila, col, t_s desde inicio)
    t_inicio_utc: pd.Timestamp
    t_fin_utc: pd.Timestamp
    barreras: np.ndarray | None = None          # uint8 (nfil, ncol, nvec): código de barrera por enlace (v2)
    ancho_barrera_m: np.ndarray | None = None   # float64 por código (índice 0 = sin barrera)


@dataclass
class ConfigSimulacion:
    vecindad: int = 16
    dt_s: float = 60.0
    ros_min_m_min: float = 0.05
    horas_sin_propagacion_para_terminar: int = 12
    max_pasos: int = 10_000_000
    max_segundos_cpu: float = 6 * 3600
    capacidad_frente: int = 400_000
    k_clase: dict[int, float] = field(default_factory=dict)
    factor_waf: float = 1.0
    n_bins_lfmc: int = 10
    lfmc_defecto_pct: float = 90.0
    lluvia_24h_mm_extincion: float = 5.0
    niveles_curado: tuple[float, ...] = (0.5, 0.8)
    albini: bool = True
    guardar_estado_cada_s: float = 3600.0
    # --- v2: intensidad y barreras
    longitud_llama_a: float = 0.0775
    longitud_llama_b: float = 0.46
    barreras_activo: bool = False
    cruce_modo: str = "probabilistico"        # probabilistico | umbral
    cruce_lambda: float = 1.0
    cruce_beta: float = 4.0
    semilla: int = 20261015
    # --- v2: contención
    contencion_activo: bool = False
    contencion_inicio_s: float | None = None  # segundos desde la ignición; None → retardo_h
    contencion_retardo_h: float = 2.0
    contencion_inicio_exacto: bool = False    # la primera línea se construye en el minuto de llegada (producción prorrateada) y no en la hora en punto siguiente
    tasa_linea_m_h: float = 300.0
    costo_celda_m: float = 30.0
    prioridad: str = "flancos"                # flancos (ancla en la cola y avanza por los flancos) | cabeza (sector más activo sostenible primero)
    acumular_max_h: float = 1.0               # horas de producción que pueden acumularse como línea indirecta (1 = sin acumulación)
    intensidad_sostener_kw_m: float = 1700.0
    intensidad_sostener_aereo_kw_m: float = 3500.0
    intensidad_escape_kw_m: float = 3500.0
    p_escape_hora: float = 0.5
    aereo_intervalos_s: list[tuple[float, float]] = field(default_factory=list)
    # --- despacho local (docs/13): tasa = κ · a · max(A, 1 ha)^b con A la superficie simulada; medios aéreos automáticos
    despacho_modo: str = "fijo"               # fijo (tasa_linea_m_h) | snmf
    despacho_a: float = 17.3
    despacho_b: float = 0.36
    despacho_kappa: float = 1.0
    despacho_tasa_max_m_h: float = 20000.0
    despacho_kappa_quiebre_ha: float = float("inf")   # κ(A) = κ hasta el quiebre y κ·(A/A0)^-γ después, con piso κ_min (docs/13 §8)
    despacho_kappa_gamma: float = 0.0
    despacho_kappa_min: float = 1.0
    aereo_auto: bool = False
    aereo_umbrales_ha: tuple[float, ...] = (10.0, 100.0, 1000.0, 10000.0)
    aereo_prob_clase: tuple[float, ...] = (0.014, 0.103, 0.148, 0.259, 0.40)
    aereo_demora_h: float = 24.0
    aereo_horas_vuelo_utc: tuple[float, float] = (11.0, 22.0)
    # --- v2: humedad de extinción del muerto por clase (%, docs/11); vacío = la del análogo en la tabla
    mx_clase: dict[int, float] = field(default_factory=dict)


class Simulacion:
    def __init__(self, ent: EntradasSimulacion, cfg: ConfigSimulacion):
        self.e = ent; self.c = cfg
        self.dy, self.dx, self.dist, self.az = estencil(cfg.vecindad, ent.res_m)
        self.estado = preparar_estado(ent.mascara, ent.clase)
        self.t_arr = np.full(ent.mascara.shape, np.inf, np.float32)
        self.slot_de = np.full(ent.mascara.shape, -1, np.int32)
        self.celda_de = np.zeros((cfg.capacidad_frente, 2), np.int32)
        self.n_act = np.zeros(1, np.int64)
        self.prog = np.zeros((cfg.capacidad_frente, cfg.vecindad), np.float32)
        self.ros_c = np.zeros((cfg.capacidad_frente, 3), np.float64)
        self.tan_pend = np.tan(np.radians(ent.pendiente_deg)).astype(np.float64)
        az_up = np.where(ent.orientacion_deg < 0, 0.0, (ent.orientacion_deg + 180.0) % 360.0)
        self.az_arriba = np.radians(az_up).astype(np.float64)
        self.tan_pend[ent.orientacion_deg < 0] = 0.0
        # tablas de combustible
        self.tabla = ent.tabla.set_index("clase").sort_index()
        n_cl = int(self.tabla.index.max()) + 1
        self.lechos: dict[int, LechoCombustible | None] = {int(c): (lecho_desde_fila(r) if r.analogo_sb != "NB" else None) for c, r in self.tabla.iterrows()}
        for c, mx in (cfg.mx_clase or {}).items():
            if self.lechos.get(int(c)) is not None:
                self.lechos[int(c)].mx_muerto_pct = float(mx)
        self.waf = np.zeros(n_cl); self.kcl = np.ones(n_cl)
        for c, r in self.tabla.iterrows():
            self.waf[int(c)] = r.waf_efectivo_10m * cfg.factor_waf; self.kcl[int(c)] = cfg.k_clase.get(int(c), 1.0)
        # bins de humedad viva y niveles de curado
        lo = float(self.e.lfmc_herb[np.isfinite(self.e.lfmc_herb)].min()) if np.isfinite(self.e.lfmc_herb).any() else cfg.lfmc_defecto_pct
        hi = float(self.e.lfmc_herb[np.isfinite(self.e.lfmc_herb)].max()) if np.isfinite(self.e.lfmc_herb).any() else cfg.lfmc_defecto_pct
        self.lfmc_edges = np.linspace(lo, hi + 1e-6, cfg.n_bins_lfmc + 1)
        self.lfmc_centros_h = 0.5 * (self.lfmc_edges[:-1] + self.lfmc_edges[1:])
        herb = np.where(np.isfinite(ent.lfmc_herb), ent.lfmc_herb, cfg.lfmc_defecto_pct)
        self.lfmc_bin = np.clip(np.digitize(herb, self.lfmc_edges[1:-1]), 0, cfg.n_bins_lfmc - 1).astype(np.uint8)
        len_ = np.where(np.isfinite(ent.lfmc_lenoso), ent.lfmc_lenoso, cfg.lfmc_defecto_pct)
        # centro leñoso por bin: media del leñoso en las celdas del bin (misma fuente NDMI)
        self.lfmc_centros_l = np.array([len_[self.lfmc_bin == b].mean() if (self.lfmc_bin == b).any() else cfg.lfmc_defecto_pct for b in range(cfg.n_bins_lfmc)])
        niveles = np.array(cfg.niveles_curado)
        self.cur_idx = np.abs(ent.curado[..., None] - niveles[None, None, :]).argmin(axis=2).astype(np.uint8)
        self.R0_tab = np.zeros((n_cl, cfg.n_bins_lfmc, len(niveles)))
        self.coef_tab = np.zeros((n_cl, len(niveles), 4))
        self.IR_tab = np.zeros((n_cl, cfg.n_bins_lfmc, len(niveles)))   # kW/m²
        self.tr_tab = np.zeros((n_cl, len(niveles)))                     # s
        self.serie: list[dict[str, Any]] = []
        self.registro: dict[str, Any] = {"version_codigo": __version__, "config": cfg.__dict__ | {"k_clase": {int(k): v for k, v in cfg.k_clase.items()}}}
        self.u10 = np.zeros(ent.mascara.shape, np.float32); self.v10 = np.zeros(ent.mascara.shape, np.float32)
        self.t = 0.0
        self.motivo = 0
        # --- v2
        self.usar_barreras = bool(cfg.barreras_activo and ent.barreras is not None)
        if self.usar_barreras:
            if ent.barreras.shape[2] < cfg.vecindad:
                raise ValueError("el producto de barreras tiene menos enlaces que la vecindad configurada")
            self.barrera = np.ascontiguousarray(ent.barreras[:, :, :cfg.vecindad])
            self.ancho_tab = np.asarray(ent.ancho_barrera_m, np.float64)
        else:
            self.barrera = np.zeros((1, 1, cfg.vecindad), np.uint8); self.ancho_tab = np.zeros(1, np.float64)
        self.bloq = np.zeros(ent.mascara.shape if self.usar_barreras else (1, 1), np.uint16)
        self.cruces = np.zeros(ent.mascara.shape if self.usar_barreras else (1, 1), np.uint16)
        self.bloqueos = np.zeros(ent.mascara.shape if self.usar_barreras else (1, 1), np.uint16)
        self.modo_cruce = 0 if not self.usar_barreras else (2 if cfg.cruce_modo == "umbral" else 1)
        self.t_cont = np.full(ent.mascara.shape, np.inf, np.float32) if cfg.contencion_activo else np.full((1, 1), np.inf, np.float32)
        self.n_cont = 0; self.n_escapes = 0; self.m_linea_total = 0.0; self._banco = 0.0
        self._aereo_desde_s: float | None = None; self._aereo_clase = -1; self._aereo_clase_sorteo: int | None = None
        self._combate_iniciado = False
        self._hora_stats = {"m_linea": 0.0, "escapes": 0, "contenidas": 0, "bloqueos": 0, "I_max": float("nan"), "tasa": float("nan"), "aereo": False}

    # ------------------------------------------------------------------
    def _tablas_hora(self, m1: float, m10: float, m100: float, lluvia24: float) -> None:
        extinguido = lluvia24 >= self.c.lluvia_24h_mm_extincion
        for c, lecho in self.lechos.items():
            if lecho is None:
                continue
            for ci, cur in enumerate(self.c.niveles_curado):
                for b in range(self.c.n_bins_lfmc):
                    if extinguido:
                        self.R0_tab[c, b, ci] = 0.0; self.IR_tab[c, b, ci] = 0.0
                        continue
                    r = rothermel_lecho(lecho, (m1, m10, m100), float(self.lfmc_centros_h[b]), float(self.lfmc_centros_l[b]),
                                        curado=float(cur), albini=self.c.albini)
                    self.R0_tab[c, b, ci] = r.R0_ft_min
                    self.IR_tab[c, b, ci] = r.I_R * BTU_FT2_MIN_A_KW_M2
                    if b == 0:
                        self.coef_tab[c, ci] = (r.C, r.B, r.ratio_E if r.beta > 0 else 1.0, r.phis_coef)
                        self.tr_tab[c, ci] = 384.0 / r.sigma * 60.0 if r.sigma > 0 else 0.0   # Anderson 1969: t_r = 384/σ min (σ en 1/ft)

    def _hora_indices(self):
        met = self.e.meteo.copy(); hum = self.e.humedad.copy()
        met["time_utc"] = pd.to_datetime(met["time_utc"], utc=True); hum["time_utc"] = pd.to_datetime(hum["time_utc"], utc=True)
        df = met.merge(hum, on="time_utc", how="inner").sort_values("time_utc").reset_index(drop=True)
        df = df[(df.time_utc >= self.e.t_inicio_utc.floor("h")) & (df.time_utc <= self.e.t_fin_utc)]
        return df.reset_index(drop=True)

    # ------------------------------------------------------------------ v2: contención
    def _aereo_activo(self) -> bool:
        if any(a <= self.t <= b for a, b in self.c.aereo_intervalos_s):
            return True
        if self._aereo_desde_s is None or self.t < self._aereo_desde_s:
            return False
        h = (self.e.t_inicio_utc + pd.Timedelta(seconds=self.t)).hour
        h0, h1 = self.c.aereo_horas_vuelo_utc
        return h0 <= h < h1                      # sólo de día

    def _umbral_sostener(self) -> float:
        return self.c.intensidad_sostener_aereo_kw_m if self._aereo_activo() else self.c.intensidad_sostener_kw_m

    def _ha_quemadas(self) -> float:
        return float(np.count_nonzero(np.isfinite(self.t_arr)) * self.e.res_m ** 2 / 1e4)

    def _tasa_hora(self) -> float:
        """Producción de línea de la hora (m/h): fija o escalonada con la superficie simulada (despacho del SNMF, docs/13)."""
        c = self.c
        if c.despacho_modo != "snmf":
            return c.tasa_linea_m_h
        A = max(self._ha_quemadas(), 1.0)
        return float(min(self._kappa(A) * c.despacho_a * A ** c.despacho_b, c.despacho_tasa_max_m_h))

    def _kappa(self, A: float) -> float:
        """Factor del modelo sobre la tasa efectiva del SNMF: constante en los incendios chicos (donde el modelo sobreestima la
        propagación) y decreciente por encima del quiebre, hasta el piso κ_min (sin sesgo a la escala de Las Lagunas, docs/13 §8)."""
        c = self.c
        if A <= c.despacho_kappa_quiebre_ha or c.despacho_kappa_gamma == 0.0:
            return c.despacho_kappa
        return max(c.despacho_kappa * (A / c.despacho_kappa_quiebre_ha) ** (-c.despacho_kappa_gamma), min(c.despacho_kappa_min, c.despacho_kappa))

    def _sortear_aereo(self) -> None:
        """Medios aéreos automáticos: al entrar el incendio simulado en cada clase de superficie se sortea su llegada con la
        probabilidad condicional que reproduce P(aéreo | clase final) del SNMF; llegan no antes de `aereo_demora_h`."""
        c = self.c
        if not c.aereo_auto or self._aereo_desde_s is not None:
            return
        k = int(np.searchsorted(np.asarray(c.aereo_umbrales_ha), self._ha_quemadas(), side="right"))
        while self._aereo_clase < k:
            self._aereo_clase += 1
            P = c.aereo_prob_clase[self._aereo_clase]; Pa = c.aereo_prob_clase[self._aereo_clase - 1] if self._aereo_clase > 0 else 0.0
            p = float(np.clip((P - Pa) / max(1.0 - Pa, 1e-9), 0.0, 1.0))
            u = np.random.default_rng([c.semilla, 7, self._aereo_clase]).random()
            if u < p:
                self._aereo_desde_s = max(self.t, c.aereo_demora_h * 3600.0); self._aereo_clase_sorteo = self._aereo_clase
                return

    _VEC8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

    def _exterior(self) -> tuple[np.ndarray, int, int]:
        """Máscara del combustible conectado con el exterior del incendio dentro de la ventana que lo envuelve (+3 celdas):
        componentes 8-conexas de celdas COMB que tocan el borde de la ventana. Las demás son islas interiores."""
        from scipy import ndimage
        quem = np.isfinite(self.t_arr)
        filas = np.flatnonzero(quem.any(axis=1)); cols = np.flatnonzero(quem.any(axis=0))
        if len(filas) == 0:
            return np.zeros((1, 1), bool), 0, 0
        nfil, ncol = self.estado.shape
        r0 = max(0, filas[0] - 3); r1 = min(nfil, filas[-1] + 4); c0 = max(0, cols[0] - 3); c1 = min(ncol, cols[-1] + 4)
        sub = self.estado[r0:r1, c0:c1] == COMB
        lab, n = ndimage.label(sub, structure=np.ones((3, 3), int))
        if n == 0:
            return np.zeros(sub.shape, bool), r0, c0
        borde = np.unique(np.concatenate([lab[0, :], lab[-1, :], lab[:, 0], lab[:, -1]]))
        borde = borde[borde > 0]
        return np.isin(lab, borde), r0, c0

    def _elegir_linea(self, cand: np.ndarray, I: np.ndarray, n_max: int) -> list[int]:
        """Táctica de ancla y flancos (FARSITE, Finney 1998): la línea crece por celdas contiguas (8 vecinos) a la línea ya
        construida, eligiendo en cada paso la candidata contigua de menor intensidad (`prioridad: flancos`) o de mayor
        intensidad sostenible (`prioridad: cabeza`). Sin candidatas contiguas se abre un nuevo anclaje en la celda de menor
        intensidad (la cola). Así la línea es continua y el fuego solo puede rodearla por sus extremos."""
        if n_max <= 0 or len(cand) == 0:
            return []
        c = self.c
        fi = self.celda_de[cand, 0].astype(np.int64); co = self.celda_de[cand, 1].astype(np.int64)
        nfil, ncol = self.estado.shape
        linea = self.estado == CONTENIDA
        libre = np.ones(len(cand), bool)
        Ic = I[cand]
        signo = 1.0 if c.prioridad != "cabeza" else -1.0
        elegidos: list[int] = []
        for _ in range(min(n_max, len(cand))):
            adj = np.zeros(len(cand), bool)
            for di, dj in self._VEC8:
                ii = np.clip(fi + di, 0, nfil - 1); jj = np.clip(co + dj, 0, ncol - 1)
                adj |= linea[ii, jj]
            pool = libre & adj
            if not pool.any():
                pool = libre                      # nuevo anclaje: la celda de menor intensidad disponible
                orden_val = Ic
            else:
                orden_val = signo * Ic
            idx = np.flatnonzero(pool)
            q = idx[np.argmin(orden_val[idx])]
            libre[q] = False; linea[fi[q], co[q]] = True
            elegidos.append(int(cand[q]))
        return elegidos

    def _t_inicio_combate(self) -> float:
        c = self.c
        t = c.contencion_inicio_s if c.contencion_inicio_s is not None else c.contencion_retardo_h * 3600.0
        if c.contencion_inicio_exacto:
            # minuto entero de llegada: el reloj de la simulación debe seguir alineado con las horas en punto (una llegada
            # fraccionaria, p. ej. 8.741,55 s, dejaba pasos de microsegundos al llegar a la hora siguiente)
            t = math.ceil(t / 60.0 - 1e-9) * 60.0
        return t

    def _contener_hora(self, hora_idx: int, fraccion: float = 1.0) -> None:
        """Al cambio de hora: escapes de celdas contenidas y construcción de línea sobre el perímetro activo. Con
        `fraccion` < 1 (llegada en mitad de la hora, `contencion_inicio_exacto`) la producción se prorratea."""
        c = self.c
        self._sortear_aereo()
        self._hora_stats["aereo"] = self._aereo_activo()
        if self.t < self._t_inicio_combate() - 1e-6:
            return
        self._combate_iniciado = True
        # 1) escapes (con las ROS de la nueva hora)
        if self.n_cont > 0:
            celdas = np.argwhere(self.estado == CONTENIDA).astype(np.int32)
            n = escapes(celdas, self.estado, self.t_arr, self.slot_de, self.celda_de, self.n_act, self.prog, self.ros_c, c.vecindad,
                        self.dy, self.dx, self.az, self.e.clase, self.cur_idx, self.lfmc_bin, self.u10, self.v10, self.tan_pend, self.az_arriba,
                        self.R0_tab, self.coef_tab, self.waf, self.kcl, self.IR_tab, self.tr_tab, c.intensidad_escape_kw_m, c.p_escape_hora, c.semilla, hora_idx,
                        self.usar_barreras, self.barrera, self.ancho_tab, self.modo_cruce, c.cruce_lambda, c.cruce_beta, c.longitud_llama_a, c.longitud_llama_b)
            self.n_escapes += int(n); self._hora_stats["escapes"] = int(n); self.n_cont -= int(n)
        # 2) línea de contención: celdas activas de menor intensidad primero, hasta agotar el presupuesto horario
        if self.n_act[0] == 0:
            return
        I = intensidad_maxima_activas(self.estado, self.celda_de, self.n_act, self.ros_c, self.dy, self.dx, self.az, self.e.clase, self.cur_idx,
                                      self.lfmc_bin, self.IR_tab, self.tr_tab, self.usar_barreras, self.barrera, self.ancho_tab, self.modo_cruce,
                                      c.cruce_lambda, c.cruce_beta, c.longitud_llama_a, c.longitud_llama_b)
        self._hora_stats["I_max"] = float(I.max()) if len(I) else float("nan")
        umbral = self._umbral_sostener()
        # presupuesto horario; lo no gastado (frente demasiado intenso) se acumula como línea indirecta hasta un tope
        tasa = self._tasa_hora(); self._hora_stats["tasa"] = tasa
        self._banco = min(self._banco + tasa * fraccion, tasa * max(1.0, c.acumular_max_h))
        n_max = int(self._banco // c.costo_celda_m)
        # candidatas: celdas del perímetro EXTERIOR (con vecinos combustibles conectados con el exterior; las islas
        # interiores no justifican línea) cuya intensidad puede sostenerse (I < umbral). De noche I ≈ 0 en todo el
        # borde y la línea se construye sobre el perímetro detenido (trabajo nocturno).
        elegidos: list[int] = []
        if n_max > 0:
            ext, r0, c0 = self._exterior()
            ok_ext = vecino_exterior(self.estado, self.celda_de, self.n_act, self.dy, self.dx, ext, r0, c0)
            cand = np.nonzero((I >= 0.0) & (I < umbral) & ok_ext)[0]
            elegidos = self._elegir_linea(cand, I, n_max)
        self._banco -= len(elegidos) * c.costo_celda_m
        if elegidos:
            slots = np.array(sorted(elegidos, reverse=True), np.int64)
            contener_slots(slots, self.estado, self.slot_de, self.celda_de, self.n_act, self.prog, self.ros_c, c.vecindad, self.t_cont, self.t)
            self.n_cont += len(elegidos)
            m = len(elegidos) * c.costo_celda_m
            self.m_linea_total += m; self._hora_stats["m_linea"] = m
        self._hora_stats["contenidas"] = int(self.n_cont)

    # ------------------------------------------------------------------
    def ejecutar(self, callback: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
        t0 = time.time(); proc = psutil.Process()
        df = self._hora_indices()
        if len(df) == 0:
            raise ValueError("sin horas meteorológicas en el periodo de simulación")
        t_ini = self.e.t_inicio_utc
        dur_total = (self.e.t_fin_utc - t_ini).total_seconds()
        ros_min = self.c.ros_min_m_min / 60.0
        # igniciones iniciales (en el instante indicado)
        pendientes = sorted(self.e.igniciones, key=lambda x: x[2])
        pasos = 0; horas_sin_avance = 0; hora_actual = None; hora_idx = 0
        self.t = 0.0
        c = self.c
        while self.t < dur_total:
            ahora = t_ini + pd.Timedelta(seconds=self.t)
            h = ahora.floor("h")
            if h != hora_actual:
                fila = df[df.time_utc == h]
                if len(fila) == 0:
                    self.motivo = 2; break
                f = fila.iloc[0]
                self._tablas_hora(float(f.m_1h_pct), float(f.m_10h_pct), float(f.m_100h_pct), float(f.lluvia_24h_mm))
                if self.e.viento is not None:
                    if getattr(self.e.viento, "por_hora", False):   # viento horario local (v3.1, docs/v3.1/04)
                        U, V = self.e.viento(float(f.wind_speed_10m_vectorial), float(f.wind_direction_10m), hora=h)
                    else:
                        U, V = self.e.viento(float(f.wind_speed_10m_vectorial), float(f.wind_direction_10m))
                    self.u10[...] = np.nan_to_num(U); self.v10[...] = np.nan_to_num(V)
                recalcular_ros_activas(self.estado, self.celda_de, self.n_act, self.ros_c, self.e.clase, self.cur_idx, self.lfmc_bin,
                                       self.u10, self.v10, self.tan_pend, self.az_arriba, self.R0_tab, self.coef_tab, self.waf, self.kcl)
                if hora_actual is not None:
                    self._registrar_hora(hora_actual, f, proc, t0)
                    if callback:
                        callback(self.serie[-1])
                hora_actual = h
                fila_h = f
                hora_idx = int(round((h - t_ini.floor("h")).total_seconds() / 3600.0))
                self._hora_stats = {"m_linea": 0.0, "escapes": 0, "contenidas": int(self.n_cont), "bloqueos": 0, "I_max": float("nan"), "tasa": float("nan"), "aereo": False}
                if self.usar_barreras:
                    self.bloq[...] = 0            # los enlaces bloqueados vuelven a sortear el cruce en la nueva hora
                if c.contencion_activo:
                    self._contener_hora(hora_idx)
            elif c.contencion_activo and c.contencion_inicio_exacto and not self._combate_iniciado and self.t >= self._t_inicio_combate() - 1e-6:
                # llegada del primer recurso en mitad de la hora: línea con la producción de los minutos que faltan hasta la hora en punto
                self._contener_hora(hora_idx, fraccion=(h + pd.Timedelta(hours=1) - ahora).total_seconds() / 3600.0)
            # igniciones programadas
            while pendientes and pendientes[0][2] <= self.t + c.dt_s:
                i, j, ti = pendientes.pop(0)
                if self.estado[i, j] == COMB:
                    _activar(i, j, max(ti, self.t), self.estado, self.t_arr, self.slot_de, self.celda_de, self.n_act, self.prog, self.ros_c,
                             c.vecindad, self.e.clase, self.cur_idx, self.lfmc_bin, self.u10, self.v10, self.tan_pend, self.az_arriba,
                             self.R0_tab, self.coef_tab, self.waf, self.kcl)
                else:
                    log.warning("ignición en celda no combustible (%d,%d): ignorada", i, j)
            dt = min(c.dt_s, dur_total - self.t, (h + pd.Timedelta(hours=1) - ahora).total_seconds())
            if c.contencion_activo and c.contencion_inicio_exacto and not self._combate_iniciado and self._t_inicio_combate() > self.t + 1e-6:
                dt = min(dt, self._t_inicio_combate() - self.t)     # el paso termina justo en la llegada
            n_ign, avance, desb, n_bloq = paso(self.t, dt, self.estado, self.t_arr, self.slot_de, self.celda_de, self.n_act, self.prog, self.ros_c,
                                               self.dy, self.dx, self.dist, self.az, self.e.clase, self.cur_idx, self.lfmc_bin, self.u10, self.v10,
                                               self.tan_pend, self.az_arriba, self.R0_tab, self.coef_tab, self.waf, self.kcl, ros_min,
                                               self.usar_barreras, self.barrera, self.ancho_tab, self.bloq, self.IR_tab, self.tr_tab, self.modo_cruce,
                                               c.cruce_lambda, c.cruce_beta, c.longitud_llama_a, c.longitud_llama_b, c.semilla, hora_idx,
                                               self.cruces, self.bloqueos, bool(c.contencion_activo))
            self._hora_stats["bloqueos"] += int(n_bloq)
            self.t += dt; pasos += 1
            if desb:
                self.motivo = 6; break
            if self.n_act[0] == 0 and not pendientes and not (c.contencion_activo and self.n_cont > 0):
                self.motivo = 5; break
            # control de "sin propagación": por hora
            if abs((self.t % 3600.0)) < 1e-6 or dt < c.dt_s:
                if avance <= 0.0:
                    horas_sin_avance += 1
                else:
                    horas_sin_avance = 0
                if c.contencion_activo and self.n_cont > 0:
                    horas_sin_avance = 0          # fuego contenido: se sigue hasta el fin documentado por posibles escapes
                if horas_sin_avance >= c.horas_sin_propagacion_para_terminar:
                    self.motivo = 3; break
            if pasos >= c.max_pasos or (time.time() - t0) > c.max_segundos_cpu:
                self.motivo = 4; break
        else:
            self.motivo = 7 if (c.contencion_activo and self.n_cont > 0 and self.n_act[0] == 0) else 1
        if hora_actual is not None:
            self._registrar_hora(hora_actual, fila_h, proc, t0)
        self.registro.update({"motivo_fin": self.motivo, "motivo_fin_texto": MOTIVOS.get(self.motivo, "?"),
                              "t_simulado_s": self.t, "t_simulado_utc": str(t_ini + pd.Timedelta(seconds=self.t)),
                              "pasos": pasos, "segundos_cpu": round(time.time() - t0, 1), "memoria_pico_gb": round(proc.memory_info().peak_wset / 1e9, 3) if hasattr(proc.memory_info(), "peak_wset") else None,
                              "celdas_quemadas": int(np.isfinite(self.t_arr).sum()), "ha_quemadas": float(np.isfinite(self.t_arr).sum() * self.e.res_m ** 2 / 1e4),
                              "v2": {"barreras_activo": self.usar_barreras, "contencion_activo": bool(c.contencion_activo),
                                     "cruces_barrera": int(self.cruces.sum()) if self.usar_barreras else 0, "bloqueos_barrera": int(self.bloqueos.sum()) if self.usar_barreras else 0,
                                     "celdas_contenidas_final": int((self.estado == CONTENIDA).sum()), "escapes": int(self.n_escapes), "metros_linea": float(self.m_linea_total),
                                     "despacho_modo": c.despacho_modo,
                                     "contencion_inicio_utc": str(t_ini + pd.Timedelta(seconds=c.contencion_inicio_s if c.contencion_inicio_s is not None else c.contencion_retardo_h * 3600.0)) if c.contencion_activo else None,
                                     "aereo_auto_desde_utc": str(t_ini + pd.Timedelta(seconds=self._aereo_desde_s)) if self._aereo_desde_s is not None else None,
                                     "aereo_auto_clase": self._aereo_clase_sorteo}})
        return self.registro

    def _registrar_hora(self, hora, f, proc, t0):
        q = int(np.isfinite(self.t_arr).sum())
        st = self._hora_stats
        self.serie.append({"time_utc": str(hora), "t_s": self.t, "celdas_quemadas": q, "ha_quemadas": q * self.e.res_m ** 2 / 1e4,
                           "celdas_activas": int(self.n_act[0]), "temperature_2m": float(f.temperature_2m), "relative_humidity_2m": float(f.relative_humidity_2m),
                           "wind_speed_10m": float(f.wind_speed_10m_vectorial), "wind_direction_10m": float(f.wind_direction_10m),
                           "m_1h_pct": float(f.m_1h_pct), "segundos_cpu": round(time.time() - t0, 1),
                           "celdas_contenidas": int((self.estado == CONTENIDA).sum()) if self.c.contencion_activo else 0,
                           "metros_linea_hora": float(st["m_linea"]), "escapes_hora": int(st["escapes"]), "bloqueos_barrera_hora": int(st["bloqueos"]),
                           "intensidad_max_kw_m": float(st["I_max"]) if st["I_max"] == st["I_max"] else None,
                           "tasa_linea_m_h": float(st["tasa"]) if st["tasa"] == st["tasa"] else None, "aereo_activo": bool(st["aereo"])})

    # ------------------------------------------------------------------
    def guardar(self, out_dir: Path, grilla=None, extra: dict[str, Any] | None = None) -> dict[str, Path]:
        out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
        rutas = {"serie": out_dir / "serie_horaria.csv", "registro": out_dir / "registro.json"}
        pd.DataFrame(self.serie).to_csv(rutas["serie"], index=False)
        from datetime import datetime
        reg = self.registro | {"fecha_corrida": datetime.now().astimezone().isoformat(timespec="seconds")} | (extra or {})
        with open(rutas["registro"], "w", encoding="utf-8") as f:
            json.dump(reg, f, indent=2, ensure_ascii=False, default=str)
        if grilla is not None:
            from ..grilla import guardar_raster
            ta = np.where(np.isfinite(self.t_arr), self.t_arr, -1.0).astype(np.float32)
            rutas["t_llegada"] = guardar_raster(out_dir / "t_llegada_s.tif", ta, grilla, nodata=-1.0,
                                                tags={"unidades": "segundos desde t_inicio", "t_inicio_utc": str(self.e.t_inicio_utc)})
            rutas["estado"] = guardar_raster(out_dir / "estado_final.tif", self.estado, grilla, nodata=255)
            if self.c.contencion_activo:
                tc = np.where(np.isfinite(self.t_cont), self.t_cont, -1.0).astype(np.float32)
                rutas["t_contencion"] = guardar_raster(out_dir / "t_contencion_s.tif", tc, grilla, nodata=-1.0, tags={"unidades": "segundos desde t_inicio"})
            if self.usar_barreras:
                rutas["cruces"] = guardar_raster(out_dir / "cruces_barrera.tif", self.cruces, grilla, nodata=None)
                rutas["bloqueos"] = guardar_raster(out_dir / "bloqueos_barrera.tif", self.bloqueos, grilla, nodata=None)
        else:
            np.save(out_dir / "t_llegada_s.npy", self.t_arr); np.save(out_dir / "estado_final.npy", self.estado)
            if self.c.contencion_activo:
                np.save(out_dir / "t_contencion_s.npy", self.t_cont)
        from ..validation.resumen import escribir_resumen
        rutas["resumen"], rutas["resumen_md"] = escribir_resumen(out_dir)
        return rutas
