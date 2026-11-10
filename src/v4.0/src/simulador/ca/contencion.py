"""Contención por combate y despacho (v3.0 docs/10 y 13) sobre el autómata de SIM.

Qué modela
----------
Desde el inicio del combate (`inicio_min`, o `retardo_h`·60 si es null) las dotaciones producen `tasa` metros de línea por
hora: fija (`despacho: fijo`, `tasa_linea_m_h`) o escalonada con la superficie afectada simulada A (ha) según el ajuste
del SNMF (`despacho: snmf`): tasa = min(κ(A)·a·max(A, 1)^b, tasa_max), con κ(A) = κ hasta `kappa_quiebre_ha` y
κ·(A/A0)^−γ por encima, con piso min(κ_min, κ) (docs/13 §8). El presupuesto se acumula paso a paso hasta
`acumular_max_h` horas de producción (línea indirecta; 1 = sin acumulación más allá de la hora) y se gasta conteniendo
celdas a `costo_celda_m` metros cada una (null = resolución).

Candidatas: celdas del perímetro EXTERIOR (con alguna vecina de 8 combustible, no cortada, que pertenece al combustible
conectado con el exterior del incendio; las islas interiores no justifican línea), tanto activas como encendidas en el
paso que esperan en la cola del autómata (estado IGNICION: si no, la línea quedaba un paso atrás), cuya intensidad I es
menor que el umbral de sostén: `intensidad_sostener_kw_m` (terrestre) o `intensidad_sostener_aereo_kw_m` mientras hay
medio aéreo activo (intervalos ISO de la ficha o sorteo automático por clase de superficie).
`intensidad` elige la métrica de I:
- `v3` (por defecto, v3.0 `intensidad_maxima_activas`): máximo sobre los enlaces (las K vecinas) hacia vecinas
  combustibles no cortadas de I_B·R(θ_k)/R_max con la elipse de la celda (`Automata.intensidad_enlaces`), ponderado por
  la probabilidad de cruce cuando el enlace atraviesa un camino con barreras activas (I·P, la línea se ancla en caminos).
  No depende del origen heredado: vale igual en el modo estocástico de los ensembles (cada celda es su propio origen).
- `avance` (v4.0 anterior): intensidad en la dirección origen heredado → celda, la llama local de L03 invertida con
  L = 0,0775·I^0,46. En las celdas que son su propio origen (re-anclaje, estocástico) da la intensidad de cabeza.

Selección: `contigua` (táctica de ancla y flancos de v3.0: la línea crece por contigüidad de 8 vecinos desde la ya
construida; `prioridad: flancos` elige la contigua de menor I, `cabeza` la de mayor I sostenible; sin contiguas se abre
un anclaje nuevo en la de menor I) o `menor_llama` (como L03: de menor a mayor I).

Contener = marcar la celda en `contenida` y registrar `t_contencion` (min); en las activas se anulan las vecinas
pendientes (`act_pend` = False). La línea actúa dentro del paso a través del gancho `Automata.filtro_enlaces`
(`filtro`): en cada activación y en cada sub-paso se anulan los enlaces de las celdas contenidas (las de la cola quedan
contenidas al activarse) y los que atraviesan la línea (diagonales por la esquina de dos celdas contenidas, saltos de
caballo con una intermedia contenida; `cortado`, como `_cortado_por_contencion` de v3.0). La celda termina de quemarse por
la regla normal del autómata.

Escapes: en cada cambio de hora, cada celda contenida cuya intensidad potencial con la meteorología de esa hora
(`Automata.fisica_celdas`; intensidad direccional, con el mismo factor de barrera, hacia cada una de sus K vecinas
combustibles no cortadas) supera `intensidad_escape_kw_m` escapa con probabilidad `p_escape_hora` (sorteo hash
u01(semilla, fila, col, 99, hora) del autómata, reproducible e independiente del orden, igual a v3.0): sale de la línea y
enciende las vecinas hacia las que supera el umbral, con llegada t + d_k/R(θ_k) (tope 1 h).

Parada (`corrida._simular`): `escape_posible` dice si la parada anticipada debe suspenderse por posibles escapes.

Todo el estado vive en el objeto (`Contencion`), uno por corrida y por miembro de ensemble. Usa los arrays públicos y los
ganchos del autómata (act, act_pend, estado, cola_ign, origen, df, dc, dist, rumbo, K, H, W, res, filtro_enlaces,
fisica_celdas, intensidad_enlaces, _ignitar) y, para el factor de barrera, su configuración de barreras.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import estados as E
from .automata import u01, p_cruce
from ..physics.elipse import ros_direccional

__all__ = ["Contencion", "MOTIVOS", "SUSPENSION", "INTENSIDADES", "u01", "kappa", "tasa_snmf", "elegir_linea", "cortado",
           "cortar_enlaces", "exterior", "vecino_exterior", "intensidad_local", "intensidad_v3", "fisica_celdas"]

LLAMA_A, LLAMA_B = 0.0775, 0.46          # Byram (1959) en SI: L (m) = 0,0775·I (kW/m)^0,46
INTENSIDADES = ("v3", "avance")

MOTIVOS = {
    "horizonte": "Se alcanzó el fin del horizonte de simulación (duracion_h).",
    "extinguido": "El incendio se extinguió antes del fin del horizonte (sin celdas activas ni igniciones pendientes).",
    "sin_avance": "Parada por falta de avance: {n} horas sin nuevas celdas afectadas (parametros.parada.horas_sin_avance).",
    "contenido": "Frente contenido: ninguna celda activa con vecinas por encender, sin igniciones pendientes y con línea de "
                 "contención (parametros.parada.contenido).",
    "superficie_observada": "Se alcanzó la superficie del perímetro observado: la corrida termina al igualarla "
                            "(parametros.parada.superficie_observada).",
}
# motivos por los que la parada anticipada (contenido / sin_avance) se suspende; se agregan al texto del motivo de fin
SUSPENSION = {
    "escapes": "celdas contenidas con vecinas combustibles y p_escape_hora > 0 (posibles escapes; v3.0 seguía hasta el fin)",
    "latentes": "celdas latentes por humedad (extinción reversible) dentro de las primeras {h} h sin avance",
    "pavesas": "pavesas activas con celdas en combustión",
}

_VEC8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


# ------------------------------------------------------------------------------------------- utilidades
def kappa(A: float, s: dict) -> float:
    """κ(A): constante hasta el quiebre y decreciente por encima, con piso min(κ_min, κ) (v3.0 motor._kappa)."""
    k = float(s.get("kappa", 1.0)); A0 = s.get("kappa_quiebre_ha"); g = float(s.get("kappa_gamma") or 0.0)
    if A0 is None or A <= float(A0) or g == 0.0:
        return k
    return max(k * (A / float(A0)) ** (-g), min(float(s.get("kappa_min", 1.0)), k))


def tasa_snmf(A: float, s: dict) -> float:
    """Producción de línea del despacho SNMF (m/h): min(κ(A)·a·max(A, 1)^b, tasa_max)."""
    A = max(float(A), 1.0)
    return float(min(kappa(A, s) * float(s.get("a", 17.3)) * A ** float(s.get("b", 0.36)), float(s.get("tasa_max_m_h", np.inf))))


def intensidad_local(au) -> np.ndarray:
    """`avance`: intensidad de Byram (kW/m) de cada celda activa en su dirección de avance (origen heredado → celda): la
    llama de cabeza escalada con (R(θ)/R_max)^0,46 (`Supresion.llama_local`) e invertida con L = 0,0775·I^0,46."""
    from .supresion import Supresion
    L = np.maximum(np.nan_to_num(Supresion.llama_local(au).astype("float64"), nan=0.0), 0.0)
    return (L / LLAMA_A) ** (1.0 / LLAMA_B)


def _libres(au, f: np.ndarray, c: np.ndarray, contenida: np.ndarray | None):
    """(n, K) enlaces de (f, c) hacia vecinas dentro de la grilla, COMBUSTIBLE y no cortadas por la línea; los saltos de
    caballo exigen además las dos intermedias de `_activar_cola` no NO_COMBUSTIBLE. Devuelve (libres, fv, cv) recortados."""
    fv = f[:, None] + au.df[None, :]; cv = c[:, None] + au.dc[None, :]
    dentro = (fv >= 0) & (fv < au.H) & (cv >= 0) & (cv < au.W)
    fv = np.clip(fv, 0, au.H - 1); cv = np.clip(cv, 0, au.W - 1)
    libres = dentro & (au.estado[fv, cv] == E.COMBUSTIBLE)
    for k in range(au.K):
        a, b = int(au.df[k]), int(au.dc[k])
        if contenida is not None:
            libres[:, k] &= ~cortado(contenida, f, c, a, b)
        if k >= 8:
            sa, sb = int(np.sign(a)), int(np.sign(b))
            inter = [(a - sa, b), (a, b - sb)] if abs(a) == 2 else [(a, b - sb), (a - sa, b)]
            for di, dj in inter:
                libres[:, k] &= au.estado[np.clip(f + di, 0, au.H - 1), np.clip(c + dj, 0, au.W - 1)] != E.NO_COMBUSTIBLE
    return libres, fv, cv


def _p_barrera(au, f: np.ndarray, c: np.ndarray, fv: np.ndarray, cv: np.ndarray, Idir: np.ndarray, IB: np.ndarray):
    """(n, K) probabilidad de cruce de cada enlace con la regla de barreras del autómata (None si no hay barreras): llama
    L = 0,0775·I^0,46 direccional (o de cabeza con `llama: cabeza`); `umbral_tipo` mira la receptora, `umbral` y
    `probabilistico` el ancho máximo del enlace (`_max_enlace`). Es el I·P(cruce) de v3.0 `_intensidad_efectiva`."""
    if not getattr(au, "bar_activo", False) or not bool(au.es_camino.any()):
        return None
    if au.bar_llama == "cabeza":
        L = np.broadcast_to((LLAMA_A * np.maximum(IB, 0.0) ** LLAMA_B)[:, None], Idir.shape)
    else:
        L = LLAMA_A * np.maximum(Idir, 0.0) ** LLAMA_B
    if au.bar_modo == "umbral_tipo":
        U = au.umbral_camino[fv, cv]
        return np.where((U > 0) & (L < U), 0.0, 1.0)
    P = np.ones(Idir.shape)
    for k in range(au.K):
        W = au._max_enlace(au.capas.camino_ancho, f, c, np.full(len(f), k)) if au.bar_enlace else au.capas.camino_ancho[fv[:, k], cv[:, k]]
        P[:, k] = p_cruce(L[:, k], W, au.bar_modo, au.bar_lambda, au.bar_beta, au.bar_normalizar)
    return P


def _intensidad_dir(au, f, c, fv, cv, libres, IB, rel) -> np.ndarray:
    """(n, K) intensidad efectiva hacia cada vecina: I_B·R(θ_k)/R_max (·P de cruce), 0 en los enlaces no libres."""
    I = np.where(libres, IB[:, None] * np.clip(np.nan_to_num(rel, nan=0.0), 0.0, 1.0), 0.0)
    P = _p_barrera(au, f, c, fv, cv, I, IB)
    return I if P is None else I * P


def intensidad_v3(au, contenida: np.ndarray | None = None) -> np.ndarray:
    """`v3`: por celda activa, máximo de la intensidad de Byram (kW/m) hacia sus vecinas pendientes, combustibles y no
    cortadas (`Automata.intensidad_enlaces`, elipse de la celda), con el factor de cruce de barreras; 0 si no tiene."""
    n = len(au.act)
    if n == 0:
        return np.zeros(0)
    f, c = np.divmod(au.act, au.W)
    libres, fv, cv = _libres(au, f, c, contenida)
    libres &= au.act_pend
    I = np.where(libres, au.intensidad_enlaces(slice(None)), 0.0)
    P = _p_barrera(au, f, c, fv, cv, I, au.act_IB.astype("float64"))
    return (I if P is None else I * P).max(1)


def exterior(au) -> tuple[np.ndarray, int, int]:
    """Combustible conectado con el exterior del incendio en la ventana que lo envuelve (+3 celdas): componentes
    8-conexas de celdas COMBUSTIBLE que tocan el borde de la ventana (v3.0 motor._exterior). Devuelve (máscara, r0, c0)."""
    from scipy import ndimage
    af = au.estado >= E.IGNICION
    filas = np.flatnonzero(af.any(axis=1)); cols = np.flatnonzero(af.any(axis=0))
    if len(filas) == 0:
        return np.zeros((1, 1), bool), 0, 0
    r0 = max(0, filas[0] - 3); r1 = min(au.H, filas[-1] + 4); c0 = max(0, cols[0] - 3); c1 = min(au.W, cols[-1] + 4)
    sub = au.estado[r0:r1, c0:c1] == E.COMBUSTIBLE
    lab, n = ndimage.label(sub, structure=np.ones((3, 3), int))
    if n == 0:
        return np.zeros(sub.shape, bool), r0, c0
    borde = np.unique(np.concatenate([lab[0, :], lab[-1, :], lab[:, 0], lab[:, -1]]))
    return np.isin(lab, borde[borde > 0]), r0, c0


def _en_exterior(ext: np.ndarray, r0: int, c0: int, fv: np.ndarray, cv: np.ndarray) -> np.ndarray:
    ri = fv - r0; cj = cv - c0
    ok = (ri >= 0) & (ri < ext.shape[0]) & (cj >= 0) & (cj < ext.shape[1])
    out = np.zeros(fv.shape, bool)
    out[ok] = ext[ri[ok], cj[ok]]
    return out


def vecino_exterior(au, ext: np.ndarray, r0: int, c0: int) -> np.ndarray:
    """True por celda activa si alguna de sus 8 vecinas inmediatas sigue pendiente y pertenece al exterior (`ext`).
    Excluye la segunda fila (solo alcanza el exterior por saltos de caballo) y las que lindan solo con islas interiores."""
    n = len(au.act)
    out = np.zeros(n, bool)
    if n == 0:
        return out
    f, c = np.divmod(au.act, au.W)
    for k in range(min(au.K, 8)):
        out |= au.act_pend[:, k] & _en_exterior(ext, r0, c0, f + int(au.df[k]), c + int(au.dc[k]))
    return out


def cortado(contenida: np.ndarray, f: np.ndarray, c: np.ndarray, dfk: int, dck: int) -> np.ndarray:
    """True si el enlace (dfk, dck) desde (f, c) atraviesa la línea (v3.0 `_cortado_por_contencion`): diagonales si alguna
    de las dos celdas ortogonales está contenida; saltos de caballo si alguna de las dos intermedias lo está."""
    H, W = contenida.shape
    if dfk == 0 or dck == 0:
        return np.zeros(f.shape, bool)
    if abs(dfk) == 2:
        h = dfk // 2; pares = [(h, 0), (h, dck)]
    elif abs(dck) == 2:
        h = dck // 2; pares = [(0, h), (dfk, h)]
    else:
        pares = [(dfk, 0), (0, dck)]
    out = np.zeros(f.shape, bool)
    for di, dj in pares:
        out |= contenida[np.clip(f + di, 0, H - 1), np.clip(c + dj, 0, W - 1)]
    return out


def cortar_enlaces(au, contenida: np.ndarray) -> int:
    """Anula en las celdas activas los enlaces pendientes que atraviesan la línea de contención. Devuelve cuántos."""
    if len(au.act) == 0 or not contenida.any():
        return 0
    f, c = np.divmod(au.act, au.W)
    n = 0
    for k in range(au.K):
        pend = au.act_pend[:, k]
        if not pend.any():
            continue
        cut = pend & cortado(contenida, f, c, int(au.df[k]), int(au.dc[k]))
        if cut.any():
            au.act_pend[cut, k] = False
            n += int(cut.sum())
    return n


def fisica_celdas(au, idx: np.ndarray, t_min: float):
    """(R_max m/min, rumbo de la cabeza, e, I_B de cabeza kW/m) de celdas arbitrarias en t_min (minutos desde t0):
    envoltura de `Automata.fisica_celdas` (no toca la banda activa ni `ultimo_*`)."""
    s = au.fisica_celdas(idx, au.t0 + pd.Timedelta(minutes=float(t_min)))
    return tuple(np.asarray(s[k], "float64") for k in ("R_max", "rumbo", "e", "IB"))


def elegir_linea(f: np.ndarray, c: np.ndarray, I: np.ndarray, n_max: int, linea: np.ndarray, prioridad: str = "flancos") -> np.ndarray:
    """Táctica de ancla y flancos (v3.0 motor._elegir_linea, FARSITE): la línea crece por candidatas contiguas (8 vecinos)
    a la ya construida (`linea`), eligiendo la de menor I (`flancos`) o la de mayor I (`cabeza`); sin contiguas abre un
    anclaje nuevo en la de menor I. Devuelve los índices (en el orden de elección) dentro de las candidatas."""
    n = len(f)
    if n_max <= 0 or n == 0:
        return np.zeros(0, np.int64)
    H, W = linea.shape
    adj = np.zeros(n, bool)
    for di, dj in _VEC8:
        ii = f + di; jj = c + dj
        ok = (ii >= 0) & (ii < H) & (jj >= 0) & (jj < W)
        adj[ok] |= linea[ii[ok], jj[ok]]
    libre = np.ones(n, bool)
    signo = -1.0 if prioridad == "cabeza" else 1.0
    elegidos = []
    for _ in range(min(int(n_max), n)):
        pool = libre & adj
        if pool.any():
            idx = np.flatnonzero(pool); q = idx[np.argmin(signo * I[idx])]
        else:
            idx = np.flatnonzero(libre); q = idx[np.argmin(I[idx])]      # nuevo anclaje
        libre[q] = False
        elegidos.append(q)
        adj |= (np.abs(f - f[q]) <= 1) & (np.abs(c - c[q]) <= 1)
    return np.asarray(elegidos, np.int64)


def _a_minutos(v, t0: pd.Timestamp) -> float:
    t = pd.Timestamp(v)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")                  # ISO sin huso: UTC (como la ficha de v3.0)
    return (t - t0).total_seconds() / 60.0


# ------------------------------------------------------------------------------------------- estado
class Contencion:
    def __init__(self, c: dict, res_m: float, t0: pd.Timestamp, miembro: int = 0):
        self.c = c
        self.res = float(res_m)
        self.t0 = pd.Timestamp(t0)
        ini = c.get("inicio_min")
        self.inicio = float(ini) if ini is not None else float(c.get("retardo_h") or 0.0) * 60.0
        self.despacho = str(c.get("despacho", "fijo"))
        if self.despacho not in ("fijo", "snmf"):
            raise ValueError(f"contencion.despacho debe ser fijo o snmf (vino {self.despacho!r})")
        self.seleccion = str(c.get("seleccion", "contigua"))
        if self.seleccion not in ("contigua", "menor_llama"):
            raise ValueError(f"contencion.seleccion debe ser contigua o menor_llama (vino {self.seleccion!r})")
        self.prioridad = str(c.get("prioridad", "flancos"))
        if self.prioridad not in ("flancos", "cabeza"):
            raise ValueError(f"contencion.prioridad debe ser flancos o cabeza (vino {self.prioridad!r})")
        self.intensidad = str(c.get("intensidad", "v3"))
        if self.intensidad not in INTENSIDADES:
            raise ValueError(f"contencion.intensidad debe ser v3 o avance (vino {self.intensidad!r})")
        self.costo = float(c.get("costo_celda_m") or self.res)
        self.acumular = float(c.get("acumular_max_h") or 1.0)
        self.I_sost = float(c.get("intensidad_sostener_kw_m", 1700.0))
        self.I_sost_aereo = float(c.get("intensidad_sostener_aereo_kw_m", 3500.0))
        self.I_escape = float(c.get("intensidad_escape_kw_m", 3500.0))
        self.p_escape = float(c.get("p_escape_hora", 0.0) or 0.0)
        self.semilla = int(c.get("semilla", 20261015)) + int(miembro)     # miembro 0 = corrida simple
        self.intervalos = [(_a_minutos(a, self.t0), _a_minutos(b, self.t0)) for a, b in (c.get("aereo_intervalos") or [])]
        self.auto = dict(c.get("aereo_auto") or {})
        self.contenida = None
        self.t_contencion = None
        self.banco = 0.0
        self.metros = 0.0
        self.celdas = 0                 # contenciones acumuladas (una celda que escapa y se vuelve a contener cuenta dos)
        self.celdas_cola = 0            # de ellas, contenidas mientras esperaban en la cola (IGNICION)
        self.escapes = 0
        self.tasa = None
        self.iniciado = False
        self.aereo_desde = None         # minuto desde t0 del medio aéreo sorteado
        self.aereo_clase = -1
        self.aereo_clase_sorteo = None
        self._hora = {"m": 0.0, "escapes": 0, "aereo": False}

    @classmethod
    def desde_cfg(cls, cfg: dict, res_m: float, t0, miembro: int = 0):
        c = cfg.get("parametros", {}).get("contencion") or {}
        if not c.get("activo"):
            return None
        return cls(c, res_m, t0, miembro)

    # ----------------------------------------------------------------------------- gancho del autómata
    def enganchar(self, au):
        """Crea el estado de la línea y registra `filtro` como `au.filtro_enlaces` (la línea actúa dentro del paso)."""
        if self.contenida is None:
            self.contenida = np.zeros((au.H, au.W), bool)
            self.t_contencion = np.full((au.H, au.W), np.nan, "float32")
        df = [int(x) for x in au.df]; dc = [int(x) for x in au.dc]

        def filtro(idx: np.ndarray) -> np.ndarray:
            idx = np.asarray(idx, np.int64)
            out = np.ones((len(idx), len(df)), bool)
            if not len(idx) or not self.contenida.any():
                return out
            f, c = np.divmod(idx, au.W)
            out[self.contenida[f, c], :] = False                 # celdas contenidas: ningún enlace
            for k in range(len(df)):
                out[:, k] &= ~cortado(self.contenida, f, c, df[k], dc[k])
            return out

        au.filtro_enlaces = filtro

    # ----------------------------------------------------------------------------- despacho y medios aéreos
    def tasa_hora(self, A: float) -> float:
        if self.despacho == "snmf":
            return tasa_snmf(A, self.c.get("snmf") or {})
        return float(self.c.get("tasa_linea_m_h", 0.0) or 0.0)

    def sortear_aereo(self, A: float, t_min: float):
        """Al entrar el incendio simulado en cada clase de superficie se sortea la llegada del medio aéreo con la
        probabilidad condicional (P_k − P_k−1)/(1 − P_k−1); rng [semilla, 7, clase]; llega no antes de `demora_h`."""
        a = self.auto
        if not a.get("activo") or self.aereo_desde is not None:
            return
        umbrales = np.asarray(a.get("umbrales_ha", []), float); P = list(a.get("prob_clase", []))
        k = min(int(np.searchsorted(umbrales, A, side="right")), len(P) - 1)
        while self.aereo_clase < k:
            self.aereo_clase += 1
            Pk = float(P[self.aereo_clase]); Pa = float(P[self.aereo_clase - 1]) if self.aereo_clase > 0 else 0.0
            p = float(np.clip((Pk - Pa) / max(1.0 - Pa, 1e-9), 0.0, 1.0))
            if np.random.default_rng([self.semilla, 7, self.aereo_clase]).random() < p:
                self.aereo_desde = max(float(t_min), float(a.get("demora_h", 0.0) or 0.0) * 60.0)
                self.aereo_clase_sorteo = self.aereo_clase
                return

    def aereo_activo(self, t_min: float) -> bool:
        if any(a <= t_min + 1e-9 and t_min <= b + 1e-9 for a, b in self.intervalos):
            return True
        if self.aereo_desde is None or t_min < self.aereo_desde - 1e-9:
            return False
        h0, h1 = (self.auto.get("horas_vuelo_utc") or [0, 24])[:2]
        h = (self.t0 + pd.Timedelta(minutes=float(t_min))).tz_convert("UTC").hour
        return int(h0) <= h < int(h1)             # solo de día

    def umbral_sostener(self, t_min: float) -> float:
        return self.I_sost_aereo if self.aereo_activo(t_min) else self.I_sost

    # ----------------------------------------------------------------------------- paso
    def aplicar(self, au, t_ini: float, t_fin: float) -> int:
        """Después de cada paso del autómata (t_ini → t_fin, minutos desde t0): sorteo aéreo, escapes al cambio de hora,
        producción de línea y contención. Devuelve las celdas contenidas en el paso."""
        if self.contenida is None or au.filtro_enlaces is None:
            self.enganchar(au)
        A = au.area_quemada_ha()
        self.sortear_aereo(A, t_fin)
        aereo = self.aereo_activo(t_fin)
        self._hora["aereo"] |= aereo
        if t_fin < self.inicio - 1e-6:
            return 0
        self.iniciado = True
        # 1) escapes: una vez por hora, con la meteorología de la hora nueva
        h_ini, h_fin = int(np.floor((t_ini + 1e-6) / 60.0)), int(np.floor((t_fin + 1e-6) / 60.0))
        if h_fin > h_ini and self.p_escape > 0 and self.contenida.any():
            n = self._escapes(au, t_fin, h_fin)
            self.escapes += n; self._hora["escapes"] += n
        # 2) presupuesto: producción desde el inicio del combate, acumulable hasta `acumular_max_h` horas
        horas = (t_fin - max(t_ini, self.inicio)) / 60.0
        self.tasa = self.tasa_hora(A)
        if horas > 0:
            self.banco = min(self.banco + self.tasa * horas, self.tasa * max(self.acumular, horas))
        n_max = int((self.banco + 1e-9) // self.costo) if self.costo > 0 else 0
        n_sel = 0
        if n_max > 0 and (len(au.act) or au.cola_ign):
            f, c, fila, I = self._candidatas(au, self.I_sost_aereo if aereo else self.I_sost, t_fin)
            sel = self._elegir(f, c, I, n_max)
            if len(sel):
                fs, cs, filas = f[sel], c[sel], fila[sel]
                au.act_pend[filas[filas >= 0], :] = False
                self.contenida[fs, cs] = True
                self.t_contencion[fs, cs] = t_fin
                n_sel = int(len(sel))
                m = n_sel * self.costo
                self.banco = max(self.banco - m, 0.0)
                self.metros += m; self._hora["m"] += m
                self.celdas += n_sel; self.celdas_cola += int((filas < 0).sum())
        cortar_enlaces(au, self.contenida)
        return n_sel

    def _cola(self, au) -> np.ndarray:
        """Índices planos de las celdas encendidas que esperan en la cola del autómata (estado IGNICION)."""
        if not au.cola_ign:
            return np.zeros(0, np.int64)
        idx = np.unique(np.fromiter((i for i, _ in au.cola_ign), np.int64, len(au.cola_ign)))
        return idx[au.estado.ravel()[idx] == E.IGNICION]

    def _candidatas(self, au, umbral: float, t_min: float):
        """Candidatas a contener: activas y en cola del perímetro exterior, no contenidas, con I < umbral. Devuelve
        (f, c, fila en la banda activa o −1 si está en la cola, I)."""
        ext, r0, c0 = exterior(au)
        fa, ca = np.divmod(au.act, au.W)
        Ia = intensidad_v3(au, self.contenida) if self.intensidad == "v3" else intensidad_local(au)
        ma = vecino_exterior(au, ext, r0, c0) & ~self.contenida[fa, ca] & (Ia < umbral)
        q = self._cola(au)
        fq, cq = np.divmod(q, au.W)
        mq = ~self.contenida[fq, cq]
        if mq.any():
            libres, fv, cv = _libres(au, fq[mq], cq[mq], self.contenida)
            ext_q = (libres[:, :min(au.K, 8)] & _en_exterior(ext, r0, c0, fv[:, :min(au.K, 8)], cv[:, :min(au.K, 8)])).any(1)
            mq[mq] = ext_q
        Iq = np.zeros(len(q))
        if mq.any():
            Iq[mq] = self._intensidad_celdas(au, q[mq], t_min)
            mq &= Iq < umbral
        filas = np.concatenate([np.flatnonzero(ma), np.full(int(mq.sum()), -1, np.int64)])
        return (np.concatenate([fa[ma], fq[mq]]), np.concatenate([ca[ma], cq[mq]]), filas,
                np.concatenate([Ia[ma], Iq[mq]]))

    def _intensidad_celdas(self, au, idx: np.ndarray, t_min: float) -> np.ndarray:
        """Intensidad de decisión (kW/m) de celdas fuera de la banda activa (cola) con la física del autómata en t_min."""
        f, c = np.divmod(idx, au.W)
        s = au.fisica_celdas(idx, au.t0 + pd.Timedelta(minutes=float(t_min)))
        R, ru, e, IB = (np.asarray(s[k], "float64") for k in ("R_max", "rumbo", "e", "IB"))
        IB = np.where(R > 0, IB, 0.0)
        if self.intensidad == "v3":
            libres, fv, cv = _libres(au, f, c, self.contenida)
            rel = ros_direccional(1.0, e[:, None], au.rumbo[None, :] - ru[:, None])
            return _intensidad_dir(au, f, c, fv, cv, libres, IB, rel).max(1)
        # avance: dirección origen heredado → celda (como `intensidad_local`)
        fo, co = np.divmod(au.origen[f, c], au.W)
        dx = (c - co) * au.res; dy = -(f - fo) * au.res
        th = (np.degrees(np.arctan2(dx, dy)) + 360.0) % 360.0
        rel = np.where(np.hypot(dx, dy) > 0, np.nan_to_num(ros_direccional(1.0, e, th - ru), nan=1.0), 1.0)
        L = np.maximum(np.nan_to_num(np.asarray(s["llama"], "float64"), nan=0.0), 0.0) * np.clip(rel, 0.0, 1.0) ** 0.46
        return (L / LLAMA_A) ** (1.0 / LLAMA_B)

    def _elegir(self, f: np.ndarray, c: np.ndarray, I: np.ndarray, n_max: int) -> np.ndarray:
        if len(f) == 0:
            return np.zeros(0, np.int64)
        if self.seleccion == "menor_llama":
            return np.argsort(I, kind="stable")[:n_max]
        return elegir_linea(f, c, I, n_max, self.contenida, self.prioridad)

    def _intensidad_escape(self, au, idx: np.ndarray, t_min: float):
        """Intensidad potencial (n, K) de las celdas contenidas `idx` hacia sus vecinas libres en t_min, con R y R(θ)/R_max."""
        f, c = np.divmod(idx, au.W)
        s = au.fisica_celdas(idx, au.t0 + pd.Timedelta(minutes=float(t_min)))
        R, ru, e, IB = (np.asarray(s[k], "float64") for k in ("R_max", "rumbo", "e", "IB"))
        libres, fv, cv = _libres(au, f, c, self.contenida)
        libres &= (R > 0)[:, None]
        rel = np.clip(np.nan_to_num(ros_direccional(1.0, e[:, None], au.rumbo[None, :] - ru[:, None]), nan=0.0), 0.0, 1.0)
        return _intensidad_dir(au, f, c, fv, cv, libres, IB, rel), R, rel, fv, cv

    def _escapes(self, au, t_min: float, hora: int) -> int:
        idx = np.flatnonzero(self.contenida.ravel())
        f, c = np.divmod(idx, au.W)
        Idir, R, rel, fv, cv = self._intensidad_escape(au, idx, t_min)
        caliente = Idir > self.I_escape
        esc = caliente.any(1)
        if not esc.any():
            return 0
        esc &= u01(self.semilla, f, c, 99, hora) < self.p_escape
        if not esc.any():
            return 0
        ii, kk = np.nonzero(caliente & esc[:, None])
        vecinas = fv[ii, kk] * au.W + cv[ii, kk]
        # el fuego sale de la celda contenida (origen heredado) y llega a la vecina tras recorrer d_k a R(θ_k), tope 1 h
        d_k = np.asarray(au.dist, "float64")[kk]
        R_k = R[ii] * rel[ii, kk]
        t_ign = t_min + np.minimum(d_k / np.maximum(R_k, 1e-6), 60.0)
        orden = np.argsort(t_ign, kind="stable")              # _ignitar conserva la primera aparición de cada celda
        au._ignitar(vecinas[orden], t_ign[orden], idx[ii][orden])
        self.contenida[f[esc], c[esc]] = False
        self.t_contencion[f[esc], c[esc]] = np.nan
        return int(esc.sum())

    # ----------------------------------------------------------------------------- consultas y resúmenes
    def frente_contenido(self, au) -> bool:
        """Hay línea y ninguna celda activa conserva vecinas por encender (ni hay igniciones en cola)."""
        return self.contenida is not None and bool(self.contenida.any()) and not bool(au.act_pend.any()) and not au.cola_ign

    def escape_posible(self, au, t_min: float, t_fin_min: float, modo: str = "v3") -> bool:
        """¿Puede haber escapes después de t_min? (suspende la parada anticipada, `parametros.parada.escapes`):
        `v3` (por defecto): hay celdas contenidas con alguna vecina combustible no cortada y p_escape_hora > 0 (v3.0
        seguía hasta el fin); `potencial`: además alguna supera `intensidad_escape_kw_m` con la meteorología de alguna de
        las horas que faltan hasta t_fin_min; `ignorar`: nunca (v4.0 anterior)."""
        if modo == "ignorar" or self.p_escape <= 0 or self.contenida is None or not self.contenida.any():
            return False
        idx = np.flatnonzero(self.contenida.ravel())
        f, c = np.divmod(idx, au.W)
        con = _libres(au, f, c, self.contenida)[0].any(1)
        if not con.any():
            return False
        if modo == "v3":
            return True
        for h in range(int(np.floor((t_min + 1e-6) / 60.0)) + 1, int(np.floor((t_fin_min + 1e-6) / 60.0)) + 1):
            if (self._intensidad_escape(au, idx[con], h * 60.0)[0] > self.I_escape).any():
                return True
        return False

    def resumen_hora(self, t_min: float) -> dict:
        """Bloque `contencion` del JSON horario (acumula desde el bloque anterior y reinicia los contadores)."""
        d = {"celdas_contenidas": int(self.contenida.sum()) if self.contenida is not None else 0,
             "metros_linea_hora": round(self._hora["m"], 1), "linea_km": round(self.metros / 1000.0, 3),
             "escapes_hora": int(self._hora["escapes"]),
             "tasa_linea_m_h": None if self.tasa is None else round(float(self.tasa), 1),
             "aereo_activo": bool(self._hora["aereo"] or self.aereo_activo(t_min)),
             "umbral_sostener_kw_m": self.umbral_sostener(t_min), "combate_iniciado": bool(self.iniciado),
             "inicio_min": round(self.inicio, 2), "banco_m": round(self.banco, 1)}
        self._hora = {"m": 0.0, "escapes": 0, "aereo": False}
        return d

    def resumen(self, t_min: float) -> dict:
        def utc(m):
            return None if m is None else (self.t0 + pd.Timedelta(minutes=float(m))).tz_convert("UTC").isoformat()
        return {"activo": True, "despacho": self.despacho, "seleccion": self.seleccion, "prioridad": self.prioridad,
                "intensidad": self.intensidad,
                "inicio_min": round(self.inicio, 2), "inicio_utc": utc(self.inicio), "costo_celda_m": self.costo,
                "acumular_max_h": self.acumular, "celdas_contenidas_final": int(self.contenida.sum()) if self.contenida is not None else 0,
                "contenciones_total": int(self.celdas), "contenciones_en_cola": int(self.celdas_cola),
                "metros_linea": round(self.metros, 1), "linea_km": round(self.metros / 1000.0, 3),
                "escapes": int(self.escapes), "tasa_linea_m_h_final": None if self.tasa is None else round(float(self.tasa), 1),
                "aereo_intervalos": len(self.intervalos), "aereo_auto_activo": bool(self.auto.get("activo")),
                "aereo_auto_desde_min": self.aereo_desde, "aereo_auto_desde_utc": utc(self.aereo_desde),
                "aereo_auto_clase": self.aereo_clase_sorteo, "semilla": self.semilla, "t_min": round(float(t_min), 2)}
