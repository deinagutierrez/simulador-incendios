"""Motor del autómata celular (tiempo de llegada, banda activa, Huygens discreto).

Idea central
------------
Cada celda en COMBUSTION propaga hacia sus K vecinas acumulando `avance_k += R(θ_k)·Δt`; la vecina
se enciende cuando el avance alcanza la distancia d_k. Solo se procesan las celdas activas (la banda
del frente), nunca la grilla entera.

Corrección de flancos (origen heredado)
---------------------------------------
Un autómata puro vecino a vecino subestima los flancos de la elipse porque solo dispone de K
direcciones de propagación. Para corregirlo, cada celda hereda el **origen** (celda y hora de
ignición) de la elipse que la encendió y evalúa sus avances a lo largo de los rayos que salen de
ese origen (θ_k y d_k se miden desde el origen, no desde la celda). Esto reproduce exactamente la
construcción de Huygens en condiciones homogéneas. El origen se re-ancla (la celda pasa a ser su
propio origen) cuando la distancia al origen supera `radio_huygens_m`, cuando cambia el modelo de
combustible, el factor de carga o se cruza un camino: así el esquema sigue respondiendo a la
heterogeneidad del terreno y del combustible.

v4.0 (P3, `parametros.huygens`): V.4 inicializaba el avance de una celda nueva con el rumbo y la
excentricidad ACTUALES, como si la elipse siempre hubiera tenido la forma de ese instante: con rotación
del viento o cambios de rumbo por la pendiente se encendían de golpe celdas de la elipse nueva (hacia
atrás en el tiempo, y como trinquete). Ahora el origen guarda su rumbo y su e al anclar, el avance
inicial usa esa forma histórica y el origen se re-ancla cuando el rumbo del padre difiere en más de
`tol_rumbo_deg` o su e en más de `tol_e`. `huygens: null` = V.4 bit a bit.

Barreras lineales (`parametros.barreras`, v3.0 docs/10)
-------------------------------------------------------
Al alcanzar una vecina con camino (ancho W > 0, celda receptora) el cruce depende de la longitud de
llama L: `umbral_tipo` (V.4: L ≥ umbral del tipo), `umbral` (L/W > λ) o `probabilistico`
(P = 1/(1+exp(−β(L/W − λ))), sorteo con el hash u01(semilla, fila, col, k, hora) de v3.0, con la celda
emisora). En los dos últimos un enlace que falla queda bloqueado hasta la hora siguiente. `llama: direccional`
usa L(θ) = L_cabeza·(R(θ)/R_max)^0,46 con θ = rumbo del enlace − rumbo de la cabeza de la emisora (P4);
`cabeza` = V.4. `activo: false` = sin restricción de cruce (los caminos solo reducen la carga).
En `umbral` y `probabilistico` la barrera se evalúa por ENLACE (H1/H3): W = máximo de `camino_ancho` sobre la
receptora y las celdas intermedias del enlace (diagonal: sus dos ortogonales; caballo: las dos de `_activar_cola`
más las dos que cruza el segmento), así un salto de caballo no saltea un camino y una barrera rasterizada en
diagonal (cadena de 8 conexión) no deja pasar el fuego por las esquinas; un camino intermedio también re-ancla el
origen. `umbral_tipo` mira solo la receptora (V.4). `normalizar` (por defecto true, H6): P = (σ(x) − σ(0))/(1 − σ(0)),
P(L=0) = 0; false = logística de v3.0 (piso P(0) = σ(0)).

Otras opciones v4.0: `extincion` reversible|definitiva (P5), crédito de la activación tras el retardo de
ignición (P7; `credito_desde_activacion: false` = V.4, crédito desde la llegada), pavesas por unidad de tiempo (P8),
`limite_viento`, `propagacion.k_*` y `factor_waf`. `n_latentes` = celdas activas con R = 0 por humedad que todavía
tienen vecinas pendientes (se actualiza en cada sub-paso; la parada por `horas_sin_avance` lo consulta, H2).

Ganchos para la contención por combate (`ca/contencion.py`)
-----------------------------------------------------------
- `filtro_enlaces` (None por defecto): callable `f(idx: np.ndarray[int64]) -> np.ndarray[bool] (n, K)` con los
  enlaces permitidos de las celdas de índice plano `idx`; se aplica `pend &= f(idx)` en `_activar_cola` (filas nuevas)
  y `act_pend &= f(act)` en `_refrescar_pendientes` (cada sub-paso, antes de propagar). None = sin efecto.
- `fisica_celdas(idx_planos, t: pd.Timestamp) -> dict` con `R_max` (m/min), `rumbo` (grados, hacia donde va la
  cabeza), `e`, `IB` (kW/m de cabeza), `llama` (m), `tau` (min), `ext` (bool, R = 0 por humedad o lluvia) para celdas
  arbitrarias, sin tocar la banda activa ni `ultimo_*` (lo usa `_ros_activas`).
- `intensidad_enlaces(sel_filas_act) -> np.ndarray (n, K)`: intensidad de Byram (kW/m) hacia cada vecina,
  I_cab·R(θ_k)/R_max con la elipse actual de la celda (θ_k = rumbo del enlace desde la celda − rumbo de la cabeza);
  0 donde el enlace no está pendiente. `sel_filas_act` indexa las filas de la banda activa (máscara o índices).
- `u01(semilla, i, j, k, h)` (nivel de módulo): hash uniforme reproducible de v3.0; la contención lo importa de acá.

Sub-pasos adaptativos
---------------------
Dentro de cada Δt nominal, el frente no puede avanzar más de `cfl`·d_min por sub-paso; de lo
contrario la velocidad quedaría limitada por la discretización (una celda por paso).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import estados as E
from ..fuel.sb40 import TablaCombustible
from ..io.capas import TIPOS_CAMINO
from ..physics import rothermel as RT
from ..physics.humedad import (ParametrosHumedad, serie_humedad_muerta, humedades_vivas, curado_pasto,
                               curado_scott_burgan)
from ..physics.viento import ParametrosViento, CampoViento, KMH_A_FT_MIN
from ..physics.elipse import relacion_largo_ancho, excentricidad, ros_direccional

__all__ = ["Automata", "Ignicion", "ResumenPaso", "u01", "p_cruce", "MODOS_BARRERA"]

MODOS_BARRERA = ("umbral_tipo", "umbral", "probabilistico")
_U64 = [np.uint64(x) for x in (0x9E3779B97F4A7C15, 0xBF58476D1CE4E5B9, 0x94D049BB133111EB,
                               0xD6E8FEB86659FD93, 0xA0761D6478BD642F)]


def u01(semilla, i, j, k, h) -> np.ndarray:
    """Uniforme [0,1) determinista por (semilla, fila, col, enlace, hora): mezcla tipo splitmix64, idéntica a
    v3.0 simulation/automata.u01 pero vectorizada. Independiente del orden de procesamiento (reproducible)."""
    forma = np.broadcast(np.asarray(i), np.asarray(j), np.asarray(k), np.asarray(h)).shape
    with np.errstate(over="ignore"):
        x = np.full(forma, np.uint64(int(semilla) & 0xFFFFFFFFFFFFFFFF), np.uint64) * _U64[0]
        for v, m in zip((i, j, k, h), _U64[1:]):
            x ^= (np.asarray(v, np.int64) + 1).astype(np.uint64) * m
        x ^= x >> np.uint64(30); x *= _U64[1]
        x ^= x >> np.uint64(27); x *= _U64[2]
        x ^= x >> np.uint64(31)
    return (x >> np.uint64(11)).astype(np.float64) * (1.0 / 9007199254740992.0)


def _logistica(x, lam: float, beta: float) -> np.ndarray:
    z = np.clip(-beta * (np.asarray(x, float) - lam), -50.0, 50.0)
    return np.where(z >= 50.0, 0.0, np.where(z <= -50.0, 1.0, 1.0 / (1.0 + np.exp(z))))


def p_cruce(L, W, modo: str, lam: float, beta: float, normalizar: bool = False) -> np.ndarray:
    """Probabilidad de cruzar una barrera de ancho W con longitud de llama L (v3.0 docs/10 §3.2).
    `umbral`: 1 si L/W > λ; `probabilistico`: logística σ(x) = 1/(1+exp(−β(x−λ))) en x = L/W. W ≤ 0 → 1.
    `normalizar` (H6): P = (σ(x) − σ(0))/(1 − σ(0)), con P(L=0) = 0 (la logística de v3.0 tiene un piso σ(0), 1,8 %
    con λ=1, β=4, por enlace y por hora: un camino ancho se cruzaba sin llama)."""
    L = np.asarray(L, float); W = np.asarray(W, float)
    x = L / np.maximum(W, 1e-9)
    if modo == "umbral":
        P = (x > lam).astype(float)
    else:
        P = _logistica(x, lam, beta)
        if normalizar:
            s0 = float(_logistica(0.0, lam, beta))
            P = np.clip((P - s0) / max(1.0 - s0, 1e-12), 0.0, 1.0)
    return np.where(W <= 0, 1.0, P)


@dataclass
class Ignicion:
    fila: int
    col: int
    t: pd.Timestamp
    id: str = ""


@dataclass
class ResumenPaso:
    t: pd.Timestamp
    n_activas: int
    n_quemadas: int
    toco_borde: bool


class Automata:
    def __init__(self, capas, meteo, cfg: dict, tabla: TablaCombustible | None = None):
        self.capas = capas
        self.meteo = meteo
        self.cfg = cfg
        p = cfg["parametros"]
        self.tabla = tabla or TablaCombustible()
        self.p_hum = ParametrosHumedad(**(p.get("humedad") or {}))
        self.p_viento = ParametrosViento(**(p.get("viento") or {}))
        self.dt = float(cfg["dt_min"])
        self.res = capas.grilla.res
        self.modo = cfg["modo"]
        self.rng = np.random.default_rng(int(cfg.get("semilla", 42)))
        self.limitar_viento = bool(p.get("limitar_viento", True))
        self.limite_viento = str(p.get("limite_viento", "rothermel_1972")) if self.limitar_viento else "ninguno"
        if self.limite_viento not in RT.LIMITES_VIENTO:
            raise ValueError(f"limite_viento '{self.limite_viento}' desconocido (opciones: {', '.join(RT.LIMITES_VIENTO)})")
        self.limitar_viento = self.limite_viento != "ninguno"
        self.delay_ign = float(p.get("ignicion_delay_min", 0.0))
        self.cfl = float(p.get("cfl", 0.9))
        self.dt_sub_min = float(p.get("dt_sub_min", 0.1))
        self.radio_huygens = float(p.get("radio_huygens_m", 300.0))
        hy = p.get("huygens", {"tol_rumbo_deg": 15.0, "tol_e": 0.05})
        self.huygens = None if hy is None else {"tol_rumbo_deg": float(hy.get("tol_rumbo_deg", 15.0)), "tol_e": float(hy.get("tol_e", 0.05))}
        self.extincion = str(p.get("extincion", "reversible"))
        if self.extincion not in ("reversible", "definitiva"):
            raise ValueError(f"extincion '{self.extincion}' desconocida (reversible | definitiva)")
        pb = p.get("barreras") or {}
        self.bar_activo = bool(pb.get("activo", True))
        self.bar_modo = str(pb.get("modo", "probabilistico"))
        self.bar_llama = str(pb.get("llama", "direccional"))
        if self.bar_modo not in MODOS_BARRERA or self.bar_llama not in ("direccional", "cabeza"):
            raise ValueError(f"barreras: modo '{self.bar_modo}' / llama '{self.bar_llama}' desconocidos")
        self.bar_lambda = float(pb.get("lambda", 1.0)); self.bar_beta = float(pb.get("beta", 4.0))
        self.bar_semilla = int(pb.get("semilla", 20261015))
        self.bar_normalizar = bool(pb.get("normalizar", True))          # H6; False = logística de v3.0 (piso σ(0))
        self.bar_enlace = self.bar_modo in ("umbral", "probabilistico")  # H1/H3: barrera por enlace (umbral_tipo = V.4)
        ps = p.get("spotting") or {}
        self.spot_por_tiempo = bool(ps.get("por_unidad_tiempo", True))   # P8; False = V.4 (p por sub-paso)
        self.credito_activacion = bool(p.get("credito_desde_activacion", True))   # P7/H5; False = V.4

        g = capas.grilla
        self.H, self.W = g.shape
        self.df, self.dc, self.dist, self.rumbo = E.vecindad(int(cfg["vecindad"]), self.res)
        self.K = len(self.df)
        self.inter = [self._intermedias(int(a), int(b)) for a, b in zip(self.df, self.dc)]
        # gancho de la contención: f(idx planos) -> (n, K) bool con los enlaces permitidos (None = sin filtro)
        self.filtro_enlaces = None

        # --- combustible por celda ---------------------------------------------------------
        self.idx_modelo = self.tabla.mapa_indices(capas.combustible, capas.nodata_combustible)
        combustible = (self.idx_modelo >= 0) & self.tabla.combustible[np.clip(self.idx_modelo, 0, None)]
        self.estado = np.where(combustible, E.COMBUSTIBLE, E.NO_COMBUSTIBLE).astype(np.uint8)
        self.factor_carga = np.ones((self.H, self.W), "float32")
        pc = p["caminos"]
        if pc.get("factor_carga_por_ancho", True):
            self.factor_carga *= np.clip(1.0 - capas.camino_ancho / self.res, 0.0, 1.0)
        self.estado[(capas.camino_ancho >= self.res) & combustible] = E.NO_COMBUSTIBLE
        if capas.modificador is not None:
            self.factor_carga *= capas.modificador
        self.estado[(self.factor_carga <= 0) & combustible] = E.NO_COMBUSTIBLE
        self.es_camino = capas.camino_ancho > 0
        self.umbral_camino = np.zeros((self.H, self.W), "float32")
        for i, t in enumerate(TIPOS_CAMINO):
            self.umbral_camino[capas.camino_tipo == i] = pc["umbral_llama_m"].get(t, 1.0)
        # propagación: multiplicadores de R0 por modelo (v3.0 k_clase) y del WAF
        pp = p.get("propagacion") or {}
        self.k_modelo = self.tabla.factores_ros(pp.get("k_global", 1.0), pp.get("k_grupo"), pp.get("k_codigo"))
        self.k_activo = bool(np.any(self.k_modelo != 1.0))
        fw = float(pp.get("factor_waf", 1.0))
        self.waf = self.tabla.waf() if fw == 1.0 else self.tabla.waf() * fw
        self.f_20ft = float(self.p_viento.factor_10m_20ft)
        self.mx_modelo = self.tabla.mx_ajustada(self.p_hum.mx_grupo, self.p_hum.mx_codigo)

        # --- humedades ----------------------------------------------------------------------
        self.hum = None
        self.m_herb, self.m_lenoso = humedades_vivas(capas.ndmi_mes, (self.H, self.W), self.p_hum)
        self.m_vivo = self.m_herb                                        # (compatibilidad: herbáceo vivo)
        if self.p_hum.curado_fijo is not None:
            self.curado = np.full((self.H, self.W), float(self.p_hum.curado_fijo), "float32")
        elif capas.ndvi_mes is not None and capas.ndvi_verano is not None:
            self.curado = curado_pasto(np.nan_to_num(capas.ndvi_mes, nan=0.2), np.nan_to_num(capas.ndvi_verano, nan=0.4), self.p_hum).astype("float32")
        else:
            self.curado = curado_scott_burgan(self.m_herb).astype("float32")
        grupo = np.full((self.H, self.W), "", dtype="<U2")
        ok = self.idx_modelo >= 0
        grupo[ok] = self.tabla.grupo[self.idx_modelo[ok]]
        self.extra_m1 = np.zeros((self.H, self.W), "float32")
        self.extra_m1[np.isin(grupo, ["TU", "TL"])] += self.p_hum.sombra_dosel
        sombria = (~capas.plano) & (capas.pendiente > 5) & (np.abs(((capas.orientacion - 180) + 180) % 360 - 180) < 60)
        self.extra_m1[sombria] += self.p_hum.ladera_sombria

        self.viento = CampoViento(capas, self.p_viento, cfg.get("viento_externo"), g, capas.ventana)

        # --- estado de la simulación ----------------------------------------------------------
        self.t_llegada = np.full((self.H, self.W), np.nan, "float32")   # minutos desde t0
        self.ros_max = np.zeros((self.H, self.W), "float32")            # m/min
        self.intensidad_max = np.zeros((self.H, self.W), "float32")     # kW/m
        self.llama_max = np.zeros((self.H, self.W), "float32")          # m
        self.rumbo_cab = np.full((self.H, self.W), np.nan, "float32")
        self.excentricidad = np.zeros((self.H, self.W), "float32")    # e de la elipse en el último paso (L03)
        self.t_fin = np.full((self.H, self.W), np.nan, "float32")       # minuto en que la celda pasa a QUEMADO
        self.origen = np.full((self.H, self.W), -1, np.int64)           # índice plano del origen heredado
        self.retardo_ign = np.zeros((self.H, self.W), "float32")        # retardo de ignición aplicado (P7)
        self.o_rumbo = np.full((self.H, self.W), np.nan, "float32")     # forma de la elipse al anclar el origen (P3)
        self.o_e = np.zeros((self.H, self.W), "float32")
        self.cruces_barrera = np.zeros((self.H, self.W), np.int32)      # por celda emisora
        self.bloqueos_barrera = np.zeros((self.H, self.W), np.int32)
        # banda activa (arrays compactos, una fila por celda activa)
        self.act = np.zeros(0, np.int64)
        self.act_avance = np.zeros((0, self.K), "float32")
        self.act_pend = np.zeros((0, self.K), bool)
        self.act_theta = np.zeros((0, self.K), "float32")   # rumbo origen → vecina k
        self.act_dist = np.zeros((0, self.K), "float32")    # distancia origen → vecina k
        self.act_theta_self = np.zeros(0, "float32")        # rumbo origen → celda
        self.act_dist_self = np.zeros(0, "float32")
        self.act_nuevo = np.zeros(0, bool)
        self.act_t0 = np.zeros(0, "float32")
        self.act_tau = np.zeros(0, "float32")
        self.act_llama = np.zeros(0, "float32")
        self.act_R = np.zeros(0, "float32")
        self.act_IB = np.zeros(0, "float32")                # intensidad de Byram de cabeza del último sub-paso (kW/m)
        self.act_credito = np.zeros(0, "float32")
        self.act_bloq_h = np.zeros((0, self.K), np.int32)   # hora (desde t0) en que el enlace quedó bloqueado; −1 libre
        self.cola_ign: list[tuple[int, float]] = []
        self.n_latentes = 0                                 # activas con R = 0 por humedad y vecinas pendientes (H2)
        self.toco_borde = False
        self.paso = 0
        self.n_subpasos = 0
        self.t0 = None
        self.t = None
        self.t_min_actual = 0.0
        self.igniciones: list[Ignicion] = []
        self.ultimo_meteo = None
        self.ultimo_hum = (0.08, 0.1, 0.12)
        self.ultimo_lluvia_ext = False
        self.spots = 0

    # ------------------------------------------------------------------------------- preparación
    def preparar(self, t0: pd.Timestamp, t_fin: pd.Timestamp):
        self.t0 = pd.Timestamp(t0); self.t = self.t0
        if not self.meteo.cubre(self.t0, t_fin):
            raise ValueError(f"La serie meteorológica ({self.meteo.inicio} → {self.meteo.fin}) no cubre la corrida ({self.t0} → {t_fin})")
        df = self.meteo.horas(self.meteo.inicio, t_fin)
        self.hum = serie_humedad_muerta(df, self.p_hum)
        self.hum_t = self.hum["timestamp"].values.astype("datetime64[s]").astype("int64")

    def _humedad_muerta(self, t: pd.Timestamp):
        s = pd.Timestamp(t).tz_convert("UTC").value // 10**9
        h = self.hum
        return (float(np.interp(s, self.hum_t, h["m1"].values)), float(np.interp(s, self.hum_t, h["m10"].values)),
                float(np.interp(s, self.hum_t, h["m100"].values)))

    def _extincion_lluvia(self, t: pd.Timestamp) -> bool:
        """True si la lluvia acumulada en 24 h (hora en curso) alcanza `lluvia_24h_mm_extincion` (v3.0)."""
        umbral = self.p_hum.lluvia_24h_mm_extincion
        if umbral is None:
            return False
        s = pd.Timestamp(t).tz_convert("UTC").value // 10**9
        i = int(np.clip(np.searchsorted(self.hum_t, s, side="right") - 1, 0, len(self.hum_t) - 1))
        return bool(self.hum["lluvia_24h_mm"].values[i] >= float(umbral))

    def minutos(self, t: pd.Timestamp) -> float:
        return (pd.Timestamp(t) - self.t0).total_seconds() / 60.0

    # ------------------------------------------------------------------------------- igniciones
    def encender(self, fila: int, col: int, t: pd.Timestamp, id: str = "") -> bool:
        if not (0 <= fila < self.H and 0 <= col < self.W):
            raise ValueError(f"Ignición ({fila}, {col}) fuera de la ventana de simulación")
        if self.estado[fila, col] != E.COMBUSTIBLE:
            for r in range(1, 4):   # celda combustible más cercana (el punto puede caer en un camino o NB)
                f0, f1 = max(0, fila - r), min(self.H, fila + r + 1); c0, c1 = max(0, col - r), min(self.W, col + r + 1)
                cand = np.argwhere(self.estado[f0:f1, c0:c1] == E.COMBUSTIBLE)
                if len(cand):
                    fila, col = int(cand[0][0] + f0), int(cand[0][1] + c0)
                    break
            else:
                return False
        idx = np.array([fila * self.W + col])
        self._ignitar(idx, self.minutos(t), origen=idx, inmediato=True)
        self.igniciones.append(Ignicion(fila, col, pd.Timestamp(t), id))
        return True

    def _ignitar(self, idx: np.ndarray, t_min, origen: np.ndarray, inmediato=False):
        idx = np.asarray(idx, np.int64)
        t_arr = np.broadcast_to(np.asarray(t_min, "float32"), idx.shape)
        origen = np.broadcast_to(np.asarray(origen, np.int64), idx.shape)
        idx, primera = np.unique(idx, return_index=True)
        t_arr = t_arr[primera]; origen = origen[primera]
        f, c = np.divmod(idx, self.W)
        libres = self.estado[f, c] == E.COMBUSTIBLE
        idx, f, c, t_arr, origen = idx[libres], f[libres], c[libres], t_arr[libres], origen[libres]
        if not len(idx):
            return
        self.estado[f, c] = E.IGNICION
        self.t_llegada[f, c] = t_arr
        self.origen[f, c] = origen
        delay = 0.0 if inmediato else self.delay_ign
        self.retardo_ign[f, c] = delay
        self.cola_ign.extend((int(i), float(ta) + delay) for i, ta in zip(idx, t_arr))

    def _activar_cola(self, t_min: float):
        if not self.cola_ign:
            return
        listos = [i for i, ta in self.cola_ign if ta <= t_min + 1e-6]
        if not listos:
            return
        self.cola_ign = [(i, ta) for i, ta in self.cola_ign if ta > t_min + 1e-6]
        idx = np.array(listos, np.int64)
        f, c = np.divmod(idx, self.W)
        self.estado[f, c] = E.COMBUSTION
        n = len(idx)
        fv = f[:, None] + self.df[None, :]; cv = c[:, None] + self.dc[None, :]
        dentro = (fv >= 0) & (fv < self.H) & (cv >= 0) & (cv < self.W)
        pend = np.zeros((n, self.K), bool)
        fvc = np.clip(fv, 0, self.H - 1); cvc = np.clip(cv, 0, self.W - 1)
        pend[dentro] = (self.estado[fvc, cvc] == E.COMBUSTIBLE)[dentro]
        if self.K > 8:
            # saltos de caballo: no pueden atravesar barreras; las dos celdas intermedias deben ser combustibles
            # (o estar ya afectadas), si no el fuego "saltaría" un camino o un cuerpo de agua de una celda de ancho
            for k in range(8, self.K):
                dfk, dck = int(self.df[k]), int(self.dc[k])
                inter = [(dfk - np.sign(dfk), dck), (dfk, dck - np.sign(dck))] if abs(dfk) == 2 else [(dfk, dck - np.sign(dck)), (dfk - np.sign(dfk), dck)]
                ok = np.ones(n, bool)
                for di, dj in inter:
                    fi = np.clip(f + di, 0, self.H - 1); ci = np.clip(c + dj, 0, self.W - 1)
                    ok &= self.estado[fi, ci] != E.NO_COMBUSTIBLE
                pend[:, k] &= ok
        if self.filtro_enlaces is not None:
            pend &= np.asarray(self.filtro_enlaces(idx), bool)
        if (~dentro).any():
            self.toco_borde = True     # vecinas fuera de la ventana = NO_COMBUSTIBLE
        # geometría respecto del origen heredado
        o = self.origen[f, c]
        fo, co = np.divmod(o, self.W)
        dxs = (c - co) * self.res; dys = -(f - fo) * self.res           # celda − origen (este, norte)
        dxk = (cv - co[:, None]) * self.res; dyk = -(fv - fo[:, None]) * self.res
        theta = (np.degrees(np.arctan2(dxk, dyk)) + 360.0) % 360.0
        distk = np.hypot(dxk, dyk)
        theta_self = (np.degrees(np.arctan2(dxs, dys)) + 360.0) % 360.0
        dist_self = np.hypot(dxs, dys)
        self.act = np.concatenate([self.act, idx])
        self.act_avance = np.vstack([self.act_avance, np.zeros((n, self.K), "float32")])
        self.act_pend = np.vstack([self.act_pend, pend])
        self.act_theta = np.vstack([self.act_theta, theta.astype("float32")])
        self.act_dist = np.vstack([self.act_dist, distk.astype("float32")])
        self.act_theta_self = np.concatenate([self.act_theta_self, theta_self.astype("float32")])
        self.act_dist_self = np.concatenate([self.act_dist_self, dist_self.astype("float32")])
        self.act_nuevo = np.concatenate([self.act_nuevo, np.ones(n, bool)])
        self.act_t0 = np.concatenate([self.act_t0, self.t_llegada[f, c]])
        self.act_tau = np.concatenate([self.act_tau, np.zeros(n, "float32")])
        self.act_llama = np.concatenate([self.act_llama, np.zeros(n, "float32")])
        self.act_R = np.concatenate([self.act_R, np.zeros(n, "float32")])
        self.act_IB = np.concatenate([self.act_IB, np.zeros(n, "float32")])
        # crédito desde la ACTIVACIÓN (llegada + retardo de ignición; P7: V.4 lo contaba desde la llegada y
        # anulaba el retardo). Con retardo 0 es idéntico a V.4; `credito_desde_activacion: false` = V.4 (H5).
        t_act = self.t_llegada[f, c] + self.retardo_ign[f, c] if self.credito_activacion else self.t_llegada[f, c]
        credito = np.maximum(t_min - t_act, 0.0).astype("float32")
        self.act_credito = np.concatenate([self.act_credito, credito])
        self.act_bloq_h = np.vstack([self.act_bloq_h, np.full((n, self.K), -1, np.int32)])

    # ------------------------------------------------------------------------------- física por paso
    def _ros_activas(self, t: pd.Timestamp):
        """Física de la banda activa en t (actualiza `ultimo_meteo`, `ultimo_hum` y `ultimo_lluvia_ext`)."""
        s, met, hum, lluvia = self._fisica(self.act, t)
        self.ultimo_meteo = met; self.ultimo_hum = hum; self.ultimo_lluvia_ext = lluvia
        return s["R_max"], s["rumbo"], s["e"], s["IB"], s["llama"], s["tau"], s["ext"]

    def fisica_celdas(self, idx_planos, t: pd.Timestamp) -> dict:
        """Física del autómata en t para celdas arbitrarias (índices planos), sin tocar la banda activa ni `ultimo_*`.
        Devuelve {R_max (m/min), rumbo (° hacia donde va la cabeza), e, IB (kW/m de cabeza), llama (m), tau (min),
        ext (bool: R = 0 por humedad o lluvia)}, un array (n,) por clave."""
        return self._fisica(np.asarray(idx_planos, np.int64).ravel(), pd.Timestamp(t))[0]

    def _fisica(self, idx: np.ndarray, t: pd.Timestamp):
        n = len(idx)
        f, c = np.divmod(idx, self.W)
        met = self.meteo.en(t)
        m1, m10, m100 = self._humedad_muerta(t)
        lluvia = self._extincion_lluvia(t)
        if n == 0:
            v = np.zeros(0)
            return {"R_max": v, "rumbo": v, "e": v, "IB": v, "llama": v, "tau": v, "ext": np.zeros(0, bool)}, met, (m1, m10, m100), lluvia
        im = self.idx_modelo[f, c]
        T = self.tabla
        w = T.w[im] * self.factor_carga[f, c][:, None]
        vel_kmh, dir_desde = self.viento.velocidad_dir(f, c, met.viento_kmh, met.viento_dir_deg, int(self.minutos(t) // 60))
        U_mf = vel_kmh * KMH_A_FT_MIN * self.f_20ft * self.waf[im]
        tan_p = np.tan(np.deg2rad(self.capas.pendiente[f, c]))
        curado = self.curado[f, c]
        if self.p_hum.curado_solo_dinamicos:
            curado = np.where(T.dinamico[im], curado, 0.0)      # P9: transferencia solo en modelos dinámicos
        sal = RT.rothermel(w, T.sav[im], T.profundidad_ft[im], self.mx_modelo[im], T.calor_muerto[im], T.calor_vivo[im],
                           curado, np.minimum(m1 + self.extra_m1[f, c], 0.35), np.full(n, m10), np.full(n, m100),
                           self.m_herb[f, c], self.m_lenoso[f, c], U_mf, tan_p, self.limitar_viento, self.limite_viento)
        if self.k_activo:
            sal.R0 = sal.R0 * self.k_modelo[im]                  # k escala R0 y, con él, la intensidad
        if lluvia:
            sal.R0 = np.zeros_like(sal.R0); sal.extinguido = np.ones(n, bool)
        dir_hacia = (dir_desde + 180.0) % 360.0
        R_max_ft, rumbo, U_eff_ft, _ = RT.combinar_viento_pendiente(sal, dir_hacia, self.capas.orientacion[f, c], self.capas.plano[f, c])
        lb = relacion_largo_ancho(U_eff_ft / 88.0)
        e = excentricidad(lb)
        IB, llama = RT.intensidad_byram(sal.IR, R_max_ft, sal.tau_min)     # I_B ∝ R_max (incluye k)
        s = {"R_max": R_max_ft * RT.FT_MIN_A_M_MIN, "rumbo": rumbo, "e": e, "IB": IB, "llama": llama,
             "tau": sal.tau_min, "ext": sal.extinguido}
        return s, met, (m1, m10, m100), lluvia

    # ------------------------------------------------------------------------------- paso
    def paso_tiempo(self) -> ResumenPaso:
        t_ini = self.minutos(self.t)
        t_fin = t_ini + self.dt
        t_min = t_ini
        d_min = float(self.dist.min())
        while t_fin - t_min > 1e-6:
            self._activar_cola(t_min)
            n = len(self.act)
            if n == 0:
                self.n_latentes = 0
                break
            t_abs = self.t0 + pd.Timedelta(minutes=t_min)
            R_max, rumbo, e, IB, llama, tau, ext = self._ros_activas(t_abs)
            f, c = np.divmod(self.act, self.W)
            np.maximum.at(self.ros_max, (f, c), R_max.astype("float32"))
            np.maximum.at(self.intensidad_max, (f, c), IB.astype("float32"))
            np.maximum.at(self.llama_max, (f, c), llama.astype("float32"))
            self.rumbo_cab[f, c] = rumbo
            self.excentricidad[f, c] = e
            self.act_tau = np.maximum(self.act_tau, tau).astype("float32")
            self.act_llama = llama.astype("float32"); self.act_R = R_max.astype("float32"); self.act_IB = IB.astype("float32")
            # ROS a lo largo de los rayos origen → vecina
            theta = self.act_theta - rumbo[:, None]
            R_dir = ros_direccional(R_max[:, None], e[:, None], theta)
            R_dir = np.where(ext[:, None], 0.0, R_dir)
            # celdas recién activadas: avance inicial equivalente al radio ya recorrido desde el origen
            if self.act_nuevo.any():
                if self.huygens is None:
                    # V.4: con la forma ACTUAL de la elipse (redibuja la elipse hacia atrás en el tiempo, P3)
                    nv = self.act_nuevo
                    R_self = ros_direccional(R_max[nv], e[nv], self.act_theta_self[nv] - rumbo[nv])
                    esc = self.act_dist_self[nv] / np.maximum(R_self, 1e-6)
                    self.act_avance[nv] = (R_dir[nv] * esc[:, None]).astype("float32")
                else:
                    self._avance_inicial_origen(np.flatnonzero(self.act_nuevo), rumbo, e)
                self.act_nuevo[:] = False
            rmax = float(R_dir.max()) if R_dir.size else 0.0
            restante = t_fin - t_min
            dt_sub = restante if rmax * restante <= self.cfl * d_min else max(self.cfl * d_min / rmax, self.dt_sub_min)
            dt_sub = min(dt_sub, restante)
            if self.modo == "estocastico":
                self._propagar_estocastico(R_dir, f, c, t_min, dt_sub)
            else:
                self._propagar_determinista(R_dir, f, c, t_min, dt_sub)
            if self.cfg["parametros"]["spotting"]["activo"]:
                self._spotting(IB, R_max, f, c, t_min, dt_sub)
            t_min += dt_sub
            self._quemadas_completas(t_min, ext)
            self.n_subpasos += 1
        self.paso += 1
        self.t = self.t0 + pd.Timedelta(minutes=t_fin)
        self.t_min_actual = t_fin
        return ResumenPaso(self.t, len(self.act), int((self.estado == E.QUEMADO).sum()), self.toco_borde)

    def _avance_inicial_origen(self, nv: np.ndarray, rumbo: np.ndarray, e: np.ndarray):
        """P3 (A): el origen guarda rumbo y e al anclar (la primera vez que se evalúa una celda con ese origen,
        que es el propio origen) y el avance inicial de las celdas nuevas usa esa forma histórica:
        avance_k = d_self · R_o(θ_k) / R_o(θ_self)."""
        o = self.origen.ravel()[self.act[nv]]
        o_r = self.o_rumbo.ravel(); o_e = self.o_e.ravel()
        sin = np.isnan(o_r[o])
        if sin.any():
            o_r[o[sin]] = rumbo[nv][sin]; o_e[o[sin]] = e[nv][sin]
        ro = o_r[o].astype(float); eo = o_e[o].astype(float)
        Rs = ros_direccional(1.0, eo, self.act_theta_self[nv] - ro)
        Rk = ros_direccional(1.0, eo[:, None], self.act_theta[nv] - ro[:, None])
        self.act_avance[nv] = (self.act_dist_self[nv][:, None] * Rk / np.maximum(Rs, 1e-6)[:, None]).astype("float32")

    def _vecinas(self, f, c):
        fv = f[:, None] + self.df[None, :]; cv = c[:, None] + self.dc[None, :]
        dentro = (fv >= 0) & (fv < self.H) & (cv >= 0) & (cv < self.W)
        return np.clip(fv, 0, self.H - 1), np.clip(cv, 0, self.W - 1), dentro

    def _refrescar_pendientes(self, f, c):
        fv, cv, dentro = self._vecinas(f, c)
        self.act_pend &= dentro & (self.estado[fv, cv] == E.COMBUSTIBLE)
        if self.filtro_enlaces is not None and len(self.act):
            self.act_pend &= np.asarray(self.filtro_enlaces(self.act), bool)
        return fv, cv

    @staticmethod
    def _intermedias(a: int, b: int) -> list:
        """Celdas intermedias (desplazamientos desde la emisora) del enlace (a, b): ortogonal ninguna; diagonal sus dos
        ortogonales; caballo las dos que exige `_activar_cola` (V.4) más las dos que cruza el segmento entre centros."""
        if abs(a) + abs(b) <= 1:
            return []
        if abs(a) == 1 and abs(b) == 1:
            return [(a, 0), (0, b)]
        sa, sb = int(np.sign(a)), int(np.sign(b))
        v4 = [(a - sa, b), (a, b - sb)] if abs(a) == 2 else [(a, b - sb), (a - sa, b)]
        seg = [(a - sa, 0), (a - sa, b)] if abs(a) == 2 else [(0, b - sb), (a, b - sb)]
        return list(dict.fromkeys(v4 + seg))

    def _max_enlace(self, campo: np.ndarray, f: np.ndarray, c: np.ndarray, kk: np.ndarray) -> np.ndarray:
        """Máximo de `campo` sobre la receptora y las celdas intermedias de los enlaces (f, c, kk) (1-D, emisoras)."""
        fr = np.clip(f + self.df[kk], 0, self.H - 1); cr = np.clip(c + self.dc[kk], 0, self.W - 1)
        out = campo[fr, cr].copy()
        for k in np.unique(kk):
            m = kk == k
            for a, b in self.inter[int(k)]:
                fi = np.clip(f[m] + a, 0, self.H - 1); ci = np.clip(c[m] + b, 0, self.W - 1)
                out[m] = np.maximum(out[m], campo[fi, ci])
        return out

    def _origen_para(self, ii, kk, fv, cv):
        """Origen que hereda la vecina (ii, kk): el del padre, salvo re-anclaje."""
        padre = self.act[ii]
        o = self.origen.ravel()[padre]
        fp, cp = np.divmod(padre, self.W)
        fn, cn = fv[ii, kk], cv[ii, kk]
        reancla = (self.act_dist[ii, kk] > self.radio_huygens) \
            | (self.idx_modelo[fn, cn] != self.idx_modelo[fp, cp]) \
            | (self.factor_carga[fn, cn] != self.factor_carga[fp, cp]) \
            | self.es_camino[fn, cn] | self.es_camino[fp, cp]
        if self.bar_enlace:
            reancla |= self._max_enlace(self.es_camino, fp, cp, kk)       # camino en una celda intermedia (H1/H3)
        if self.huygens is not None:
            # P3: re-anclar si la forma actual del padre difiere de la guardada en el origen
            o_r = self.o_rumbo.ravel()[o]; o_e = self.o_e.ravel()[o]
            d_r = np.abs((self.rumbo_cab.ravel()[padre] - o_r + 180.0) % 360.0 - 180.0)
            d_e = np.abs(self.excentricidad.ravel()[padre] - o_e)
            reancla |= np.isfinite(o_r) & ((d_r > self.huygens["tol_rumbo_deg"]) | (d_e > self.huygens["tol_e"]))
        return np.where(reancla, fn * self.W + cn, o)

    # ------------------------------------------------------------------------------- barreras
    def _bloqueo(self, llega, R_dir, f, c, fv, cv, t_min) -> np.ndarray:
        """Enlaces de `llega` que NO cruzan la barrera (ver docstring del módulo): `umbral_tipo` mira la receptora (V.4);
        `umbral` y `probabilistico` el ancho máximo del enlace (receptora e intermedias, `_max_enlace`)."""
        if not self.bar_activo or not llega.any():
            return np.zeros_like(llega)
        if self.bar_llama == "cabeza":
            L = self.act_llama[:, None]
        else:
            # llama en la dirección del ENLACE (celda emisora → receptora), con la elipse actual de la emisora, como
            # v3.0. El rayo desde el origen heredado no sirve: en los flancos lejanos es casi paralelo a la cabeza.
            rel = ros_direccional(1.0, self.excentricidad[f, c].astype(float)[:, None],
                                  self.rumbo[None, :] - self.rumbo_cab[f, c].astype(float)[:, None])
            L = self.act_llama[:, None] * np.clip(rel, 0.0, 1.0) ** 0.46
        if self.bar_modo == "umbral_tipo":
            umbral = self.umbral_camino[fv, cv]
            return llega & (umbral > 0) & (L < umbral)
        hora = int(t_min // 60)
        ya = llega & (self.act_bloq_h == hora)                  # bloqueado en esta hora: no se vuelve a sortear
        bloqueado = ya.copy()
        ii, kk = np.nonzero(llega & ~ya)
        W = self._max_enlace(self.capas.camino_ancho, f[ii], c[ii], kk) if len(ii) else np.zeros(0, "float32")
        con = W > 0
        ii, kk, W = ii[con], kk[con], W[con]
        if len(ii):
            Lc = np.broadcast_to(L, llega.shape)[ii, kk]
            P = p_cruce(Lc, W, self.bar_modo, self.bar_lambda, self.bar_beta, self.bar_normalizar)
            if self.bar_modo == "umbral":
                falla = P < 0.5
            else:
                falla = u01(self.bar_semilla, f[ii], c[ii], kk, hora) >= P
            bloqueado[ii[falla], kk[falla]] = True
            self.act_bloq_h[ii[falla], kk[falla]] = hora
            np.add.at(self.bloqueos_barrera, (f[ii[falla]], c[ii[falla]]), 1)
            np.add.at(self.cruces_barrera, (f[ii[~falla]], c[ii[~falla]]), 1)
        return bloqueado

    def _propagar_determinista(self, R_dir, f, c, t_min, dt_sub):
        fv, cv = self._refrescar_pendientes(f, c)
        prev = self.act_avance.copy()
        dt_eff = dt_sub + self.act_credito
        self.act_avance += (R_dir * dt_eff[:, None]).astype("float32")
        llega = self.act_pend & (self.act_avance >= self.act_dist)
        if self.huygens is not None:
            llega &= R_dir > 0          # el avance inicial geométrico no enciende si la celda no propaga
        bloqueado = self._bloqueo(llega, R_dir, f, c, fv, cv, t_min)
        if bloqueado.any():
            self.act_avance[bloqueado] = self.act_dist[bloqueado]
        llega &= ~bloqueado
        if llega.any():
            ii, kk = np.nonzero(llega)
            frac = np.clip((self.act_dist[ii, kk] - prev[ii, kk]) / np.maximum(R_dir[ii, kk] * dt_eff[ii], 1e-6), 0, 1)
            t_lleg = (t_min - self.act_credito[ii]) + frac * dt_eff[ii]
            t_lleg = np.maximum(t_lleg, self.act_t0[ii])
            idx = fv[ii, kk] * self.W + cv[ii, kk]
            orig = self._origen_para(ii, kk, fv, cv)
            orden = np.argsort(t_lleg)
            idx_o, primera = np.unique(idx[orden], return_index=True)
            self._ignitar(idx_o, t_lleg[orden][primera], orig[orden][primera])
            self.act_pend[llega] = False
        self.act_credito[:] = 0.0

    def _propagar_estocastico(self, R_dir, f, c, t_min, dt_sub):
        """Versión probabilística (Alexandridis et al. 2008 adaptado): p_k = 1 − exp(−R_k·Δt/d_k), con
        d_k la distancia a la vecina (la ponderación 1/√2 de las diagonales queda implícita en d_k).
        Sin herencia de origen: cada celda emite su propia elipse."""
        fv, cv = self._refrescar_pendientes(f, c)
        fp = float(self.cfg["parametros"]["estocastico"].get("factor_p", 1.0))
        dt_eff = dt_sub + self.act_credito
        p = 1.0 - np.exp(-fp * R_dir * dt_eff[:, None] / self.dist[None, :])
        u = self.rng.random(p.shape)
        llega = self.act_pend & (u < p)
        llega &= ~self._bloqueo(llega, R_dir, f, c, fv, cv, t_min)
        if llega.any():
            ii, kk = np.nonzero(llega)
            idx = fv[ii, kk] * self.W + cv[ii, kk]
            self._ignitar(idx, t_min + dt_sub * self.rng.random(), idx)
            self.act_pend[llega] = False
        self.act_credito[:] = 0.0

    def _spotting(self, IB, R_max, f, c, t_min, dt_sub=None):
        """Pavesas. P8: con `spotting.por_unidad_tiempo` (por defecto) `p_max` es la probabilidad por paso nominal Δt
        y se ajusta al sub-paso, p_sub = 1 − (1 − p)^(dt_sub/Δt), con ignición en t + dt_sub; con False, V.4 (p por
        sub-paso, ignición en t + Δt: el número de pavesas dependía del CFL)."""
        ps = self.cfg["parametros"]["spotting"]
        met = self.ultimo_meteo
        p = ps["p_max"] * (1.0 - np.exp(-IB / ps["intensidad_ref_kw_m"])) * min(met.viento_kmh / 30.0, 1.0)
        t_ign = t_min + self.dt
        if self.spot_por_tiempo and dt_sub is not None:
            p = 1.0 - (1.0 - p) ** (dt_sub / self.dt)
            t_ign = t_min + dt_sub
        cand = np.nonzero(self.rng.random(len(IB)) < p)[0][: ps["max_por_paso"]]
        if not len(cand):
            return
        d = self.rng.lognormal(np.log(ps["dist_mediana_m"]) + np.log1p(met.viento_kmh / 20.0), ps["sigma_log"], len(cand))
        ang = np.deg2rad((met.viento_dir_deg + 180.0) % 360.0 + self.rng.normal(0, 15, len(cand)))
        ff = np.round(f[cand] - d * np.cos(ang) / self.res).astype(int)
        cc = np.round(c[cand] + d * np.sin(ang) / self.res).astype(int)
        ok = (ff >= 0) & (ff < self.H) & (cc >= 0) & (cc < self.W)
        if ok.any():
            idx = ff[ok] * self.W + cc[ok]
            antes = int((self.estado.ravel()[idx] == E.COMBUSTIBLE).sum())
            self._ignitar(idx, t_ign, idx)
            self.spots += antes

    def _quemadas_completas(self, t_min, ext):
        """Pasan a QUEMADO las celdas con la residencia cumplida y sin vecinas por alcanzar. Con `extincion:
        definitiva` (V.4) también las que tienen R = 0 por humedad; con `reversible` quedan latentes y retoman."""
        residencia_ok = t_min >= self.act_t0 + self.act_tau
        sin_pend = ~self.act_pend.any(1)
        listo = residencia_ok & (sin_pend | ext) if self.extincion == "definitiva" else residencia_ok & sin_pend
        self.n_latentes = int((ext & ~sin_pend & ~listo).sum())          # H2: latentes que siguen en la banda
        if listo.any():
            f, c = np.divmod(self.act[listo], self.W)
            self.estado[f, c] = E.QUEMADO
            self.t_fin[f, c] = t_min
            self._compactar(~listo)

    def _compactar(self, k: np.ndarray):
        """Conserva las filas `k` de todos los arrays de la banda activa."""
        self.act = self.act[k]; self.act_avance = self.act_avance[k]; self.act_pend = self.act_pend[k]
        self.act_theta = self.act_theta[k]; self.act_dist = self.act_dist[k]
        self.act_theta_self = self.act_theta_self[k]; self.act_dist_self = self.act_dist_self[k]
        self.act_nuevo = self.act_nuevo[k]
        self.act_t0 = self.act_t0[k]; self.act_tau = self.act_tau[k]; self.act_llama = self.act_llama[k]
        self.act_R = self.act_R[k]; self.act_credito = self.act_credito[k]; self.act_bloq_h = self.act_bloq_h[k]
        self.act_IB = self.act_IB[k]

    # ------------------------------------------------------------------------------- consultas
    def intensidad_enlaces(self, sel_filas_act) -> np.ndarray:
        """(n, K) intensidad de Byram (kW/m) hacia cada vecina de las filas `sel_filas_act` de la banda activa:
        I_cab·R(θ_k)/R_max con la elipse del último sub-paso de la celda (θ_k = rumbo del enlace desde la celda − rumbo
        de la cabeza; criterio de v3.0 `intensidad_maxima_activas`); 0 donde el enlace no está pendiente."""
        sel = np.arange(len(self.act))[sel_filas_act]
        f, c = np.divmod(self.act[sel], self.W)
        ru = self.rumbo_cab[f, c].astype(float)
        rel = ros_direccional(1.0, self.excentricidad[f, c].astype(float)[:, None],
                              self.rumbo[None, :] - np.where(np.isfinite(ru), ru, 0.0)[:, None])
        I = self.act_IB[sel].astype(float)[:, None] * np.clip(rel, 0.0, 1.0)
        return np.where(self.act_pend[sel], I, 0.0)
    @property
    def quemando(self) -> np.ndarray:
        return (self.estado == E.COMBUSTION) | (self.estado == E.IGNICION)

    @property
    def afectada(self) -> np.ndarray:
        return self.estado >= E.IGNICION

    def area_quemada_ha(self) -> float:
        return float(self.afectada.sum()) * self.capas.grilla.area_celda_ha

    def activo(self) -> bool:
        return len(self.act) > 0 or len(self.cola_ign) > 0
