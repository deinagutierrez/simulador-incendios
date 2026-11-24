"""Combate del fuego: el método común a los dos motores (decisión D-E3-36; diseño en docs/etapa3/F8_combate.md).

Los dos motores traen una contención propia (v3.1 `motor._contener_hora`, v4.0 `ca/contencion.py`), parecidas pero no
iguales: una trabaja al cambio de hora y la otra en cada paso, y lo aéreo solo sube un umbral. La app no usa ninguna de las
dos: el combate se decide ACÁ, con las mismas reglas, los mismos parámetros y el mismo orden para los dos motores. Cada motor
aporta solo lo que es suyo, por medio de un adaptador (`combate_v40.py`, `combate_v31.py`): qué celdas arden, con qué
intensidad, y cómo se frena o se reaviva una celda en su autómata. Por eso es normal que no combatan en el mismo lugar: el
fuego de cada motor es distinto, el método no.

Este módulo no importa ningún motor: solo la biblioteca estándar, numpy y (para el perímetro exterior) scipy.

Qué modela
----------
- **Dotaciones** (bomberos en tierra, intervención `dotacion`): cada despacho suma `bomberos` personas que desde su llegada
  construyen `M_H_POR_BOMBERO` metros de línea por hora y por persona. Lo construido en una hora se coloca al cumplirse esa
  hora, sobre el perímetro que tiene el fuego en ese momento.
- **Línea**: una celda del frente con línea deja de propagar (queda frenada) y el fuego no pasa a través de la línea (ni por
  las esquinas de dos celdas en diagonal, ni con los saltos de caballo de la vecindad de 16). Cada celda cuesta `res` metros.
- **Dónde se construye**: en las celdas del frente (las que arden y todavía tienen vecinas por encender) del perímetro
  EXTERIOR (las islas sin quemar de adentro no justifican línea) cuya intensidad hacia sus vecinas libres es menor que
  `I_SOSTENER_KW_M` (ataque directo). Con el frente más intenso que eso no se puede trabajar: lo producido se guarda hasta
  `ACUMULAR_MAX_H` horas de producción y el resto se pierde.
- **Táctica**: ancla y flancos. La línea crece por celdas contiguas (8 vecinas) a la que ya existe; entre las contiguas elige
  la de menor intensidad (`prioridad: flancos`) o la de mayor intensidad sostenible (`cabeza`). Sin contiguas abre un ancla
  nueva en la celda de menor intensidad.
- **Escapes**: en cada hora, una celda frenada cuya intensidad potencial hacia alguna vecina libre supera `I_ESCAPE_KW_M`
  escapa con probabilidad `P_ESCAPE_HORA` (sorteo por hash de la celda y la hora: reproducible, no depende del orden): sale de
  la línea y vuelve a propagar.
- **Descargas aéreas** (intervención `descarga`): una franja recta que empieza en el punto marcado, en la dirección marcada,
  con el largo y el ancho del medio (`MEDIOS`: avión hidrante o helicóptero). Sus celdas pasan a ser línea en el acto: las
  que arden quedan frenadas si su intensidad es menor que `I_AEREO_KW_M` (con más, la descarga no las frena) y las que
  todavía no ardieron quedan bloqueadas (el fuego no entra). Con **agua** la línea es temporal: dura `PRODUCTOS["agua"]`
  horas y vence; con **retardante** queda hasta el final. Solo de día (`HORAS_VUELO_UTC`) y hasta `max_por_hora` descargas
  por medio y por hora (el ciclo de carga de cada aeronave).
- **Al vencer el agua** las celdas dejan de ser línea. Las bloqueadas vuelven a ser combustible; las frenadas, y las celdas
  ya quemadas pegadas a una celda que se seca, vuelven a propagar si en ese momento el fuego puede avanzar (intensidad mayor
  que cero hacia una vecina libre). Si no puede (de noche, con humedad), ahí el fuego quedó apagado. El agua no apaga: da
  tiempo.
- **Brechas**: una celda bloqueada (agua o retardante sobre combustible sin quemar) a la que el fuego llega con más de
  `I_ESCAPE_KW_M` cede con probabilidad `P_ESCAPE_HORA` por hora, con el mismo sorteo de los escapes.
- **Consolidación**: las dotaciones, antes de construir línea nueva, aseguran las celdas de agua que están en contacto con el
  fuego (primero las que vencen antes): pasan a ser línea de bomberos, que ya no vence. Es la forma de aprovechar el tiempo
  que da una descarga.

Cadencia: una vez por hora simulada, en la hora en punto, después de las intervenciones de esa hora y con la meteorología de
la hora que empieza. Es la única cadencia que los dos motores permiten por igual sin modificarlos; por eso las duraciones se
cuentan en horas enteras. Orden dentro del paso: 1) escapes y brechas, 2) producción de las dotaciones presentes en la hora
que terminó, 3) consolidación del agua en contacto con el fuego (antes de que venza: es el trabajo de esa hora),
4) vencimientos, 5) línea nueva.

Parámetros: son los de docs/v4.0/10 y 13 (hauling chart de Andrews y Rothermel, reportes del SNMF), todos [HIPÓTESIS] sin
calibrar para esta app; se informan en `resultados.combate.parametros`.

El adaptador de un motor
------------------------
Un objeto con:
- `forma` (filas, columnas), `res` (m), `df`, `dc` (desplazamientos de fila y columna de sus K vecinas);
- `habilitar()`: prepara el motor para recibir línea; se llama una sola vez, antes del primer uso. Hasta entonces el motor
  no cambia en nada (una corrida sin combate es idéntica a las de siempre);
- `afectada()` → bool (filas, columnas): celdas que el fuego ya alcanzó;
- `combustible()` → bool: celdas que todavía pueden encenderse;
- `activas()` → índices planos de las celdas que arden y pueden propagar;
- `intensidad(idx)` → (n, K) kW/m: intensidad de Byram de cada celda hacia cada una de sus K vecinas con la meteorología del
  momento (ya ponderada por el cruce de barreras del motor), sin mirar el estado de la vecina; 0 si la celda no propaga;
- `frenar(idx, t_min)`: esas celdas (que arden) dejan de propagar;
- `reavivar(idx, t_min)`: esas celdas (ya alcanzadas por el fuego) vuelven a propagar desde `t_min` hacia sus vecinas libres;
- `bloquear(idx, t_min)` / `desbloquear(idx, t_min)`: esas celdas (sin quemar) no pueden encenderse / vuelven a ser
  combustible para sus vecinas;
- `rc(xy)` → (filas, columnas) fraccionarias de puntos `[[x, y], …]` en EPSG:5345 (la celda (i, j) va de i a i + 1);
- `hora_utc(t_min)` → hora del día (0 a 23, UTC) del minuto simulado `t_min`;
- `sincronizar(n_linea)`: el motor se entera de cuántas celdas de línea hay (para sus reglas de fin de corrida).
El adaptador lee en cada momento las máscaras `linea` y `frenada` de este objeto (se actualizan en el lugar).
"""
from __future__ import annotations

import hashlib

import numpy as np

# ------------------------------------------------------------------------------------------------ parámetros [HIPÓTESIS]
M_H_POR_BOMBERO = 20.0          # m de línea por hora y por persona (docs/v4.0/13 §4: `m_h_por_bombero`)
I_SOSTENER_KW_M = 1700.0        # ataque directo en tierra: hasta 2,4 m de llama (hauling chart; docs/v4.0/10)
I_ESCAPE_KW_M = 3500.0          # por encima, una celda frenada puede escapar
P_ESCAPE_HORA = 0.5             # probabilidad de escape por hora de una celda frenada que supera `I_ESCAPE_KW_M`
ACUMULAR_MAX_H = 1.0            # horas de producción que una dotación puede guardar si no tiene dónde trabajar
SEMILLA = 20261015              # la de las barreras de los dos motores
MAX_DOTACIONES = 50             # despachos sin retirar a la vez
PRIORIDADES = ("flancos", "cabeza")
# medios aéreos [HIPÓTESIS]: franja que moja una descarga y cuántas se pueden hacer por hora (ciclo de carga por la cantidad
# de aeronaves que se vieron juntas en San Luis: hasta 4 AT-802 y 2 helicópteros, docs/v4.0/13 §2.2)
I_AEREO_KW_M = 3500.0           # ataque directo desde el aire: por encima, la descarga no frena la llama (docs/v4.0/10)
MEDIOS = {
    "avion": {"nombre": "avión hidrante", "largo_m": 150.0, "ancho_m": 20.0, "max_por_hora": 12,
              "detalle": "AT-802, unos 3.000 L; ciclo de 20 minutos, hasta 4 aviones"},
    "helicoptero": {"nombre": "helicóptero con helibalde", "largo_m": 45.0, "ancho_m": 15.0, "max_por_hora": 16,
                    "detalle": "unos 1.000 L; ciclo de 7 a 8 minutos, hasta 2 helicópteros"},
}
PRODUCTOS = {"agua": {"nombre": "agua", "dura_h": 1}, "retardante": {"nombre": "retardante", "dura_h": None}}
HORAS_VUELO_UTC = (11, 22)      # de 8 a 19 h de Argentina (docs/v4.0/13 §6: `aereo_horas_vuelo_utc`)

# clase de cada celda de línea (capa 2 de `capas()`)
SIN_LINEA, LINEA_MANUAL, AGUA, RETARDANTE = 0, 1, 2, 3
CLASES = {LINEA_MANUAL: "linea", AGUA: "agua", RETARDANTE: "retardante"}
CLASE_DE_PRODUCTO = {"agua": AGUA, "retardante": RETARDANTE}
ARCHIVO = "combate_parcial.npy"   # (3, filas, cols) float32: desde (min), hasta (min; NaN = sigue en pie), clase

_U64 = [np.uint64(x) for x in (0x9E3779B97F4A7C15, 0xBF58476D1CE4E5B9, 0x94D049BB133111EB,
                               0xD6E8FEB86659FD93, 0xA0761D6478BD642F)]
_VEC8 = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


def parametros() -> dict:
    return {"m_h_por_bombero": M_H_POR_BOMBERO, "intensidad_sostener_kw_m": I_SOSTENER_KW_M,
            "intensidad_escape_kw_m": I_ESCAPE_KW_M, "p_escape_hora": P_ESCAPE_HORA, "acumular_max_h": ACUMULAR_MAX_H,
            "semilla": SEMILLA, "cadencia_min": 60, "tactica": "ancla y flancos",
            "intensidad_aereo_kw_m": I_AEREO_KW_M, "horas_vuelo_utc": list(HORAS_VUELO_UTC),
            "medios": {k: dict(v) for k, v in MEDIOS.items()}, "productos": {k: dict(v) for k, v in PRODUCTOS.items()}}


# ------------------------------------------------------------------------------------------------ utilidades
def u01(semilla, i, j, k, h) -> np.ndarray:
    """Uniforme [0, 1) determinista por (semilla, fila, columna, enlace, hora): la mezcla splitmix64 que usan los dos
    motores para sus barreras. No depende del orden en que se procesan las celdas."""
    forma = np.broadcast(np.asarray(i), np.asarray(j), np.asarray(k), np.asarray(h)).shape
    with np.errstate(over="ignore"):
        x = np.full(forma, np.uint64(int(semilla) & 0xFFFFFFFFFFFFFFFF), np.uint64) * _U64[0]
        for v, m in zip((i, j, k, h), _U64[1:]):
            x ^= (np.asarray(v, np.int64) + 1).astype(np.uint64) * m
        x ^= x >> np.uint64(30); x *= _U64[1]
        x ^= x >> np.uint64(27); x *= _U64[2]
        x ^= x >> np.uint64(31)
    return (x >> np.uint64(11)).astype(np.float64) * (1.0 / 9007199254740992.0)


def sha256_indices(indices) -> str:
    """La misma huella de un conjunto de celdas que `intervenciones.sha256_indices` (índices ordenados, int64 little-endian)."""
    a = np.unique(np.asarray(indices, dtype="int64").ravel())
    return hashlib.sha256(a.astype("<i8").tobytes()).hexdigest()


def cortado(linea: np.ndarray, f: np.ndarray, c: np.ndarray, dfk: int, dck: int) -> np.ndarray:
    """True si el enlace (dfk, dck) desde (f, c) atraviesa la línea: en diagonal, si alguna de las dos celdas ortogonales es
    de línea; en un salto de caballo, si lo es alguna de las dos intermedias. Los enlaces ortogonales nunca (la que cuenta
    ahí es la propia celda de destino). Es la regla de los dos motores (`_cortado_por_contencion`, `contencion.cortado`)."""
    H, W = linea.shape
    if dfk == 0 or dck == 0:
        return np.zeros(np.shape(f), bool)
    if abs(dfk) == 2:
        h = dfk // 2; pares = [(h, 0), (h, dck)]
    elif abs(dck) == 2:
        h = dck // 2; pares = [(0, h), (dfk, h)]
    else:
        pares = [(dfk, 0), (0, dck)]
    out = np.zeros(np.shape(f), bool)
    for di, dj in pares:
        out |= linea[np.clip(f + di, 0, H - 1), np.clip(c + dj, 0, W - 1)]
    return out


def exterior(afectada: np.ndarray, libre: np.ndarray) -> tuple[np.ndarray, int, int]:
    """Combustible libre conectado con el exterior del incendio, en la ventana que envuelve lo afectado (+3 celdas):
    componentes de 8 vecinas de celdas `libre` que tocan el borde de la ventana. Lo demás son islas interiores.
    Devuelve (máscara de la ventana, fila 0, columna 0)."""
    from scipy import ndimage
    filas = np.flatnonzero(afectada.any(axis=1)); cols = np.flatnonzero(afectada.any(axis=0))
    if len(filas) == 0:
        return np.zeros((1, 1), bool), 0, 0
    H, W = afectada.shape
    r0 = max(0, int(filas[0]) - 3); r1 = min(H, int(filas[-1]) + 4)
    c0 = max(0, int(cols[0]) - 3); c1 = min(W, int(cols[-1]) + 4)
    sub = libre[r0:r1, c0:c1]
    etiquetas, n = ndimage.label(sub, structure=np.ones((3, 3), int))
    if n == 0:
        return np.zeros(sub.shape, bool), r0, c0
    borde = np.unique(np.concatenate([etiquetas[0, :], etiquetas[-1, :], etiquetas[:, 0], etiquetas[:, -1]]))
    return np.isin(etiquetas, borde[borde > 0]), r0, c0


def _en_ventana(mascara: np.ndarray, r0: int, c0: int, f: np.ndarray, c: np.ndarray) -> np.ndarray:
    ri = f - r0; cj = c - c0
    ok = (ri >= 0) & (ri < mascara.shape[0]) & (cj >= 0) & (cj < mascara.shape[1])
    out = np.zeros(np.shape(f), bool)
    out[ok] = mascara[ri[ok], cj[ok]]
    return out


def elegir_linea(f: np.ndarray, c: np.ndarray, I: np.ndarray, n_max: int, linea: np.ndarray, prioridad: str = "flancos") -> np.ndarray:
    """Táctica de ancla y flancos: de las candidatas (f, c, I) elige hasta `n_max`, de a una. En cada elección toma, entre las
    contiguas (8 vecinas) a la línea ya construida (`linea`, más las elegidas antes), la de menor intensidad (`flancos`) o la
    de mayor (`cabeza`); si no hay contiguas abre un ancla nueva en la de menor intensidad. Los empates se resuelven por el
    orden de las candidatas (que llegan ordenadas por celda). Devuelve los índices dentro de las candidatas, en orden."""
    n = len(f)
    if n_max <= 0 or n == 0:
        return np.zeros(0, np.int64)
    H, W = linea.shape
    contigua = np.zeros(n, bool)
    for di, dj in _VEC8:
        ii = f + di; jj = c + dj
        ok = (ii >= 0) & (ii < H) & (jj >= 0) & (jj < W)
        contigua[ok] |= linea[ii[ok], jj[ok]]
    libre = np.ones(n, bool)
    signo = -1.0 if prioridad == "cabeza" else 1.0
    elegidas = []
    for _ in range(min(int(n_max), n)):
        grupo = libre & contigua
        if grupo.any():
            idx = np.flatnonzero(grupo); q = idx[np.argmin(signo * I[idx])]
        else:
            idx = np.flatnonzero(libre); q = idx[np.argmin(I[idx])]          # ancla nueva
        libre[q] = False
        elegidas.append(q)
        contigua |= (np.abs(f - f[q]) <= 1) & (np.abs(c - c[q]) <= 1)
    return np.asarray(elegidas, np.int64)


def celdas_de_tramo(f0: float, c0: float, f1: float, c1: float, ancho_celdas: float, forma: tuple[int, int]) -> np.ndarray:
    """Índices planos de las celdas de una franja recta, en el orden en que las recorre: las que toca el segmento
    (f0, c0) → (f1, c1) (coordenadas de grilla fraccionarias: la celda (i, j) va de i a i + 1 y de j a j + 1; se muestrea
    cada 1/8 de celda) y, si la franja es más ancha que una celda, las que tienen el centro a menos de medio ancho. Las que
    caen fuera de la grilla se descartan."""
    H, W = int(forma[0]), int(forma[1])
    largo = float(np.hypot(f1 - f0, c1 - c0))
    n = max(1, int(np.ceil(largo * 8.0)))
    s = (np.arange(n) + 0.5) / n
    ff = np.floor(f0 + s * (f1 - f0)).astype(np.int64); cc = np.floor(c0 + s * (c1 - c0)).astype(np.int64)
    if ancho_celdas > 1.0 and largo > 0:
        r = ancho_celdas / 2.0
        i0, i1 = int(np.floor(min(f0, f1) - r)), int(np.ceil(max(f0, f1) + r))
        j0, j1 = int(np.floor(min(c0, c1) - r)), int(np.ceil(max(c0, c1) + r))
        gi, gj = (a.ravel() for a in np.mgrid[i0:i1 + 1, j0:j1 + 1])
        u = np.clip(((gi + 0.5 - f0) * (f1 - f0) + (gj + 0.5 - c0) * (c1 - c0)) / largo ** 2, 0.0, 1.0)
        cerca = np.hypot(gi + 0.5 - (f0 + u * (f1 - f0)), gj + 0.5 - (c0 + u * (c1 - c0))) <= r
        orden = np.argsort(u[cerca], kind="stable")
        ff = np.concatenate([ff, gi[cerca][orden]]); cc = np.concatenate([cc, gj[cerca][orden]])
        s = np.concatenate([s, u[cerca][orden]])
        orden = np.argsort(s, kind="stable")
        ff, cc = ff[orden], cc[orden]
    dentro = (ff >= 0) & (ff < H) & (cc >= 0) & (cc < W)
    idx = ff[dentro] * W + cc[dentro]
    _, primera = np.unique(idx, return_index=True)
    return idx[np.sort(primera)]


def _rechazada(t: float, motivo: str) -> dict:
    return {"estado": "rechazada", "t_vigor_min": float(t), "motivo": motivo, "datos": {}}


def hora_texto(t_min: float) -> str:
    h = float(t_min) / 60.0
    return f"{h:.0f}" if abs(h - round(h)) < 1e-9 else f"{h:.2f}".rstrip("0").rstrip(".").replace(".", ",")


# ------------------------------------------------------------------------------------------------ el combate de una corrida
class Combate:
    """El combate de una corrida. El conductor del motor crea uno con su adaptador, le pasa las intervenciones de combate
    (`intervenir`) y llama a `paso_hora(t)` en cada hora simulada en punto, después de atender las órdenes de esa hora."""

    TIPOS = ("dotacion", "descarga")

    def __init__(self, adaptador, semilla: int = SEMILLA):
        self.ad = adaptador
        self.H, self.W = (int(v) for v in adaptador.forma)
        self.res = float(adaptador.res)
        self.df = np.asarray(adaptador.df, np.int64); self.dc = np.asarray(adaptador.dc, np.int64)
        self.K = len(self.df)
        self.inmediata = np.maximum(np.abs(self.df), np.abs(self.dc)) == 1
        self.semilla = int(semilla)
        self.costo = self.res                              # m de línea por celda
        forma = (self.H, self.W)
        # las dos máscaras que lee el adaptador (se actualizan en el lugar: nunca se reemplazan)
        self.linea = np.zeros(forma, bool)                 # celdas de línea, de cualquier clase
        self.frenada = np.zeros(forma, bool)               # de ellas, las que ardían cuando se las frenó
        self.clase = np.zeros(forma, np.uint8)
        self.desde = np.full(forma, np.nan, "float32")     # minuto en que la celda pasó a ser línea (la última vez)
        self.hasta = np.full(forma, np.nan, "float32")     # minuto en que dejó de serlo; NaN = sigue en pie
        self.vence = np.full(forma, np.inf, "float32")     # minuto en que una celda de agua deja de ser línea (inf = no vence)
        self._k_de = {(int(a), int(b)): k for k, (a, b) in enumerate(zip(self.df.tolist(), self.dc.tolist()))}
        self.dotaciones: list[dict] = []
        self.descargas: list[dict] = []
        self.vencidas = 0
        self.brechas = 0
        self.consolidadas = 0
        self.habilitado = False
        self.t_previo: float | None = None
        self.linea_m = 0.0                                 # metros construidos en total (los escapes no descuentan)
        self.escapes = 0
        self.horas: list[dict] = []                        # un resumen por paso horario

    # ------------------------------------------------------------------------------------------ estado
    def _habilitar(self) -> None:
        if not self.habilitado:
            self.ad.habilitar()
            self.habilitado = True

    def _poner(self, idx: np.ndarray, t: float, clase: int, frenada: bool, vence: float = np.inf) -> None:
        f, c = np.divmod(np.asarray(idx, np.int64), self.W)
        self.linea[f, c] = True
        self.frenada[f, c] = frenada
        self.clase[f, c] = clase
        self.desde[f, c] = t
        self.hasta[f, c] = np.nan
        self.vence[f, c] = vence

    def _quitar(self, idx: np.ndarray, t: float) -> None:
        f, c = np.divmod(np.asarray(idx, np.int64), self.W)
        self.linea[f, c] = False
        self.frenada[f, c] = False
        self.vence[f, c] = np.inf
        self.hasta[f, c] = t                               # `clase` y `desde` quedan: es lo que se dibuja hasta `hasta`

    def _liberar(self, idx: np.ndarray, t: float) -> None:
        """Celdas que dejan de ser línea por vencimiento o por brecha. Las bloqueadas vuelven a ser combustible. Vuelven a
        propagar, si en este momento pueden (intensidad mayor que cero hacia una vecina libre): las frenadas, y las celdas ya
        quemadas (que no arden) pegadas a una bloqueada que se libera. Las que todavía arden siguen solas."""
        idx = np.asarray(idx, np.int64)
        if not len(idx):
            return
        era_frenada = self.frenada.ravel()[idx]
        frenadas, bloqueadas = idx[era_frenada], idx[~era_frenada]
        self._quitar(idx, t)                               # primero las máscaras: el motor ya no las ve como línea
        candidatas = frenadas
        if len(bloqueadas):
            self.ad.desbloquear(bloqueadas, t)
            afectada = self.ad.afectada() & ~self.linea
            f, c = np.divmod(bloqueadas, self.W)
            vecinas = []
            for di, dj in _VEC8:
                ii, jj = f + di, c + dj
                ok = (ii >= 0) & (ii < self.H) & (jj >= 0) & (jj < self.W)
                ok[ok] &= afectada[ii[ok], jj[ok]]
                vecinas.append(ii[ok] * self.W + jj[ok])
            vecinas = np.unique(np.concatenate(vecinas))
            vecinas = vecinas[~np.isin(vecinas, np.asarray(self.ad.activas(), np.int64))]
            candidatas = np.unique(np.concatenate([frenadas, vecinas]))
        if not len(candidatas):
            return
        ok, _, _ = self._enlaces_libres(candidatas, self.ad.combustible() & ~self.linea)
        I = np.where(ok, np.asarray(self.ad.intensidad(candidatas), "float64"), 0.0).max(1)
        if (I > 0).any():
            self.ad.reavivar(candidatas[I > 0], t)

    def capas(self) -> np.ndarray:
        """(3, filas, cols) float32 para el mapa: desde, hasta (NaN = en pie) y clase (0 = nunca fue línea)."""
        return np.stack([self.desde, self.hasta, self.clase.astype("float32")]).astype("float32")

    def _enlaces_libres(self, idx: np.ndarray, libre: np.ndarray):
        """(n, K) enlaces de las celdas `idx` hacia vecinas dentro de la grilla, libres (`libre`) y no cortadas por la línea.
        Devuelve (máscara, fila y columna de las vecinas recortadas a la grilla)."""
        f, c = np.divmod(idx, self.W)
        fv = f[:, None] + self.df[None, :]; cv = c[:, None] + self.dc[None, :]
        dentro = (fv >= 0) & (fv < self.H) & (cv >= 0) & (cv < self.W)
        fv = np.clip(fv, 0, self.H - 1); cv = np.clip(cv, 0, self.W - 1)
        ok = dentro & libre[fv, cv]
        if self.linea.any():
            for k in range(self.K):
                if ok[:, k].any():
                    ok[:, k] &= ~cortado(self.linea, f, c, int(self.df[k]), int(self.dc[k]))
        return ok, fv, cv

    # ------------------------------------------------------------------------------------------ intervenciones
    def intervenir(self, entrada: dict, t: float) -> dict:
        """Aplica una intervención de combate ya validada (`intervenciones.validar_entrada`) en la hora `t` (minutos).
        Devuelve lo que espera `Control.aplicar`."""
        t = float(t)
        if entrada["tipo"] == "dotacion":
            return self._dotacion(entrada["datos"], t)
        if entrada["tipo"] == "descarga":
            return self._descarga(entrada["datos"], t)
        return _rechazada(t, f"tipo {entrada['tipo']!r} no es de combate")

    def _descarga(self, d: dict, t: float) -> dict:
        medio, producto = MEDIOS[d["medio"]], PRODUCTOS[d["producto"]]
        hora = int(self.ad.hora_utc(t))
        if not HORAS_VUELO_UTC[0] <= hora < HORAS_VUELO_UTC[1]:
            return _rechazada(t, "los medios aéreos operan de día (de 8 a 19 h de Argentina): a esta hora no se puede descargar")
        hechas = sum(1 for x in self.descargas if x["medio"] == d["medio"] and abs(x["t_min"] - t) < 1e-6)
        if hechas >= medio["max_por_hora"]:
            return _rechazada(t, f"ya se hicieron {hechas} descargas de {medio['nombre']} en esta hora: es el máximo "
                                 f"({medio['detalle']})")
        (x0, y0), (x1, y1) = ((float(p[0]), float(p[1])) for p in d["xy_5345"])
        distancia = float(np.hypot(x1 - x0, y1 - y0))
        if distancia <= 0:
            return _rechazada(t, "la descarga necesita dos puntos distintos: dónde empieza y hacia dónde va")
        xf = round(x0 + (x1 - x0) / distancia * medio["largo_m"], 2); yf = round(y0 + (y1 - y0) / distancia * medio["largo_m"], 2)
        ff, cc = self.ad.rc(np.array([[x0, y0], [xf, yf]], "float64"))
        franja = celdas_de_tramo(float(ff[0]), float(cc[0]), float(ff[1]), float(cc[1]), medio["ancho_m"] / self.res, (self.H, self.W))
        if not len(franja):
            return _rechazada(t, "la descarga cae fuera de la zona que se simula")
        vence = np.inf if producto["dura_h"] is None else t + 60.0 * producto["dura_h"]
        clase = CLASE_DE_PRODUCTO[d["producto"]]
        es_linea = self.linea.ravel()[franja]
        renovar = franja[es_linea & (self.clase.ravel()[franja] == AGUA)]     # agua todavía en pie: se moja otra vez
        nuevas = franja[~es_linea]
        libre = self.ad.combustible() & ~self.linea
        sin_quemar = nuevas[libre.ravel()[nuevas]]
        ardiendo = nuevas[np.isin(nuevas, np.asarray(self.ad.activas(), np.int64))]
        frenar, intensas = ardiendo, 0
        if len(ardiendo):
            ok, _, _ = self._enlaces_libres(ardiendo, libre)
            I = np.where(ok, np.asarray(self.ad.intensidad(ardiendo), "float64"), 0.0).max(1)
            frenar, intensas = ardiendo[I < I_AEREO_KW_M], int((I >= I_AEREO_KW_M).sum())
        if not (len(sin_quemar) or len(frenar) or len(renovar)):
            return _rechazada(t, f"el fuego bajo la descarga es demasiado intenso (más de {I_AEREO_KW_M:g} kW/m): no lo frena"
                              if intensas else "la descarga no toca fuego ni combustible sin quemar")
        self._habilitar()
        if len(sin_quemar):
            self._poner(sin_quemar, t, clase, False, vence)
            self.ad.bloquear(sin_quemar, t)
        if len(frenar):
            self._poner(frenar, t, clase, True, vence)
            self.ad.frenar(frenar, t)
        if len(renovar):
            f, c = np.divmod(renovar, self.W)
            self.vence[f, c] = np.maximum(self.vence[f, c], vence)
            if clase == RETARDANTE:
                self.clase[f, c] = RETARDANTE
        self.ad.sincronizar(int(self.linea.sum()))
        x = {"id": len(self.descargas) + 1, "medio": d["medio"], "producto": d["producto"], "t_min": t,
             "vence_min": None if not np.isfinite(vence) else float(vence), "celdas_mojadas": int(len(sin_quemar)),
             "celdas_frenadas": int(len(frenar)), "celdas_renovadas": int(len(renovar)), "celdas_intensas": intensas}
        self.descargas.append(x)
        celdas = lambda n: f"{n} celda" if n == 1 else f"{n} celdas"  # noqa: E731
        motivo = f"{medio['nombre']} con {producto['nombre']}: moja {celdas(len(sin_quemar))} sin quemar y frena {len(frenar)} con fuego"
        if len(renovar):
            motivo += f"; vuelve a mojar {celdas(len(renovar))} que seguían mojadas"
        motivo += f"; dura hasta la hora {hora_texto(vence)}" if np.isfinite(vence) else "; no vence"
        if intensas:
            motivo += f"; {celdas(intensas)} del frente con demasiada intensidad (más de {I_AEREO_KW_M:g} kW/m): no las frena"
        tocadas = np.concatenate([sin_quemar, frenar, renovar])
        return {"estado": "recortada" if intensas else "aceptada", "t_vigor_min": t, "motivo": motivo,
                "datos": {"descarga": x["id"], "largo_m": medio["largo_m"], "ancho_m": medio["ancho_m"], "xy_fin_5345": [xf, yf],
                          "celdas_mojadas": x["celdas_mojadas"], "celdas_frenadas": x["celdas_frenadas"],
                          "celdas_renovadas": x["celdas_renovadas"], "celdas_intensas": intensas, "vence_min": x["vence_min"],
                          "celdas_sha256": sha256_indices(tocadas)}}

    def _dotacion(self, d: dict, t: float) -> dict:
        en_curso = [x for x in self.dotaciones if x["hasta_min"] is None]
        if d.get("retirar"):
            if not en_curso:
                return _rechazada(t, "no hay dotaciones trabajando ni en camino")
            for x in en_curso:
                x["hasta_min"] = t
            n = sum(x["bomberos"] for x in en_curso)
            cuantas = "se retira 1 dotación" if len(en_curso) == 1 else f"se retiran {len(en_curso)} dotaciones"
            return {"estado": "aceptada", "t_vigor_min": t, "motivo": f"{cuantas} ({n} bomberos)",
                    "datos": {"dotaciones_retiradas": len(en_curso), "bomberos_retirados": int(n)}}
        if len(en_curso) >= MAX_DOTACIONES:
            return _rechazada(t, f"ya hay {MAX_DOTACIONES} dotaciones despachadas: retiralas antes de sumar otra")
        self._habilitar()
        bomberos = int(d["bomberos"])
        desde = t + float(d.get("llegada_min") or 0.0)
        tasa = round(bomberos * M_H_POR_BOMBERO, 3)
        x = {"id": len(self.dotaciones) + 1, "bomberos": bomberos, "tasa_m_h": tasa, "despacho_min": t, "desde_min": desde,
             "hasta_min": None, "prioridad": str(d.get("prioridad") or "flancos"), "banco_m": 0.0, "linea_m": 0.0}
        self.dotaciones.append(x)
        return {"estado": "aceptada", "t_vigor_min": desde,
                "motivo": f"{bomberos} bomberos, {tasa:g} m de línea por hora desde la hora {hora_texto(desde)}",
                "datos": {"dotacion": x["id"], "tasa_m_h": tasa, "desde_min": round(desde, 3)}}

    # ------------------------------------------------------------------------------------------ paso horario
    def paso_hora(self, t: float) -> dict | None:
        """El paso de combate de la hora en punto `t` (minutos). None si todavía no hubo ninguna intervención de combate."""
        if not self.habilitado:
            return None
        t = float(t)
        previo = t if self.t_previo is None else self.t_previo
        self.t_previo = t
        h = int(round(t / 60.0))
        r = {"h": h, "t_sim_min": round(t, 3), "linea_m_hora": 0.0, "celdas_nuevas": 0, "escapes_hora": 0,
             "bomberos": 0, "tasa_m_h": 0.0, "frente_celdas": None, "frente_sostenible": None,
             "vencidas_hora": 0, "brechas_hora": 0, "consolidadas_hora": 0}
        if self.frenada.any():
            r["escapes_hora"] = self._escapes(t, h, self.ad.combustible() & ~self.linea)
        if self.linea.any():
            r["brechas_hora"] = self._brechas(t, h)
        trabajan = self._acumular(t, previo, r)
        if trabajan:
            self._consolidar(trabajan, r)                  # antes de que venza: el agua se asegura mientras está mojada
        if self.linea.any():
            r["vencidas_hora"] = self._vencimientos(t)
        self._linea_nueva([x for x in trabajan if x["banco_m"] >= self.costo - 1e-9], t, r)
        self.escapes += r["escapes_hora"]; self.vencidas += r["vencidas_hora"]; self.brechas += r["brechas_hora"]
        self.consolidadas += r["consolidadas_hora"]
        self.linea_m += r["linea_m_hora"]
        temporal = self.linea & np.isfinite(self.vence)
        r |= {"linea_m": round(self.linea_m, 1), "celdas_linea": int(self.linea.sum()),
              "celdas_agua": int(temporal.sum()), "descargas": len(self.descargas),
              "linea_en_pie_m": round(int(self.linea.sum()) * self.costo, 1), "escapes": int(self.escapes),
              "banco_m": round(sum(x["banco_m"] for x in self.dotaciones if x["hasta_min"] is None), 1)}
        self.ad.sincronizar(r["celdas_linea"])
        self.horas.append(r)
        return r

    def _vencimientos(self, t: float) -> int:
        """El agua que vence en `t` deja de ser línea (ver `_liberar`)."""
        idx = np.flatnonzero((self.linea & (self.vence <= t + 1e-6)).ravel())
        self._liberar(idx, t)
        return int(len(idx))

    def _brechas(self, t: float, h: int) -> int:
        """Celdas bloqueadas (sin quemar) a las que el fuego llega con más de `I_ESCAPE_KW_M`: ceden con probabilidad
        `P_ESCAPE_HORA` (sorteo por hash de la celda y la hora, con otro número de enlace que los escapes)."""
        idx = np.flatnonzero((self.linea & ~self.frenada).ravel())
        if not len(idx):
            return 0
        afectada = self.ad.afectada() & ~self.linea
        f, c = np.divmod(idx, self.W)
        I = np.zeros(len(idx))
        for di, dj in _VEC8:                               # la vecina (di, dj) arde hacia la celda por el enlace (−di, −dj)
            k = self._k_de.get((-di, -dj))
            ii, jj = f + di, c + dj
            ok = (ii >= 0) & (ii < self.H) & (jj >= 0) & (jj < self.W)
            ok[ok] &= afectada[ii[ok], jj[ok]]
            if k is None or not ok.any():
                continue
            hacia = np.asarray(self.ad.intensidad(ii[ok] * self.W + jj[ok]), "float64")[:, k]
            I[ok] = np.maximum(I[ok], hacia)
        cede = (I > I_ESCAPE_KW_M) & (u01(self.semilla, f, c, 98, h) < P_ESCAPE_HORA)
        self._liberar(idx[cede], t)
        return int(cede.sum())

    def _escapes(self, t: float, h: int, libre: np.ndarray) -> int:
        idx = np.flatnonzero(self.frenada.ravel())
        if not len(idx):
            return 0
        ok, _, _ = self._enlaces_libres(idx, libre)
        con = ok.any(1)
        if not con.any():
            return 0
        idx, ok = idx[con], ok[con]
        I = np.where(ok, np.asarray(self.ad.intensidad(idx), "float64"), 0.0).max(1)
        f, c = np.divmod(idx, self.W)
        escapa = (I > I_ESCAPE_KW_M) & (u01(self.semilla, f, c, 99, h) < P_ESCAPE_HORA)
        if not escapa.any():
            return 0
        idx = idx[escapa]
        self._quitar(idx, t)                               # primero las máscaras: el motor ya no las ve como línea
        self.ad.reavivar(idx, t)
        return int(len(idx))

    def _acumular(self, t: float, previo: float, r: dict) -> list[dict]:
        """Producción de la hora que terminó (previo → t). Devuelve las dotaciones que tienen con qué construir."""
        trabajan = []
        for x in self.dotaciones:
            fin = t if x["hasta_min"] is None else min(t, x["hasta_min"])
            horas = max(0.0, fin - max(previo, x["desde_min"])) / 60.0
            if x["hasta_min"] is not None and x["hasta_min"] <= previo + 1e-9:
                x["banco_m"] = 0.0                         # retirada: lo que no colocó se pierde
                continue
            if horas > 0:
                x["banco_m"] = min(x["banco_m"] + x["tasa_m_h"] * horas, x["tasa_m_h"] * max(ACUMULAR_MAX_H, horas))
                r["bomberos"] += x["bomberos"]; r["tasa_m_h"] += x["tasa_m_h"]
            if x["banco_m"] >= self.costo - 1e-9:
                trabajan.append(x)
        return trabajan

    def _linea_nueva(self, trabajan: list[dict], t: float, r: dict) -> None:
        """Línea nueva sobre el frente de ahora, con lo que le queda a cada dotación."""
        if not trabajan:
            return
        f, c, I, intensas = self._frente(self.ad.combustible() & ~self.linea)
        r["frente_celdas"] = int(len(f) + intensas); r["frente_sostenible"] = int(len(f))
        for x in trabajan:
            if not len(f):
                break
            n_max = int((x["banco_m"] + 1e-9) // self.costo)
            sel = elegir_linea(f, c, I, n_max, self.linea, x["prioridad"])
            if not len(sel):
                continue
            idx = f[sel] * self.W + c[sel]
            self._poner(idx, t, LINEA_MANUAL, True)
            self.ad.frenar(idx, t)
            m = len(sel) * self.costo
            x["banco_m"] = max(x["banco_m"] - m, 0.0); x["linea_m"] += m
            r["linea_m_hora"] += m; r["celdas_nuevas"] += int(len(sel))
            queda = np.ones(len(f), bool); queda[sel] = False
            f, c, I = f[queda], c[queda], I[queda]

    def _consolidar(self, trabajan: list[dict], r: dict) -> None:
        """Antes de la línea nueva, las dotaciones aseguran el agua en contacto con el fuego (las celdas frenadas y las
        bloqueadas pegadas a una celda afectada), primero la que vence antes: pasa a ser línea de bomberos, que no vence."""
        temporal = self.linea & np.isfinite(self.vence)
        if not temporal.any():
            return
        idx = np.flatnonzero(temporal.ravel())
        f, c = np.divmod(idx, self.W)
        contacto = self.frenada[f, c].copy()
        afectada = self.ad.afectada()
        for di, dj in _VEC8:
            ii, jj = np.clip(f + di, 0, self.H - 1), np.clip(c + dj, 0, self.W - 1)
            contacto |= afectada[ii, jj]
        idx = idx[contacto]
        idx = idx[np.lexsort((idx, self.vence.ravel()[idx]))]                 # primero lo que vence antes; después, por celda
        for x in trabajan:
            n = min(int((x["banco_m"] + 1e-9) // self.costo), len(idx))
            if n <= 0:
                continue
            f, c = np.divmod(idx[:n], self.W)
            self.vence[f, c] = np.inf
            self.clase[f, c] = LINEA_MANUAL
            m = n * self.costo
            x["banco_m"] = max(x["banco_m"] - m, 0.0); x["linea_m"] += m
            r["linea_m_hora"] += m; r["consolidadas_hora"] += n
            idx = idx[n:]

    def _frente(self, libre: np.ndarray):
        """Candidatas a recibir línea: celdas que arden, sin línea, del perímetro exterior, con intensidad hacia sus vecinas
        libres menor que `I_SOSTENER_KW_M`. Devuelve (f, c, I, cuántas del perímetro exterior son demasiado intensas)."""
        idx = np.unique(np.asarray(self.ad.activas(), np.int64))
        idx = idx[~self.linea.ravel()[idx]]
        vacio = np.zeros(0, np.int64)
        if not len(idx):
            return vacio, vacio, np.zeros(0), 0
        ok, fv, cv = self._enlaces_libres(idx, libre)
        con = ok.any(1)
        idx, ok, fv, cv = idx[con], ok[con], fv[con], cv[con]
        if not len(idx):
            return vacio, vacio, np.zeros(0), 0
        ext, r0, c0 = exterior(self.ad.afectada(), libre)
        k8 = np.flatnonzero(self.inmediata)
        borde = (ok[:, k8] & _en_ventana(ext, r0, c0, fv[:, k8], cv[:, k8])).any(1)
        idx, ok = idx[borde], ok[borde]
        if not len(idx):
            return vacio, vacio, np.zeros(0), 0
        I = np.where(ok, np.asarray(self.ad.intensidad(idx), "float64"), 0.0).max(1)
        sostenible = I < I_SOSTENER_KW_M
        f, c = np.divmod(idx[sostenible], self.W)
        return f, c, I[sostenible], int((~sostenible).sum())

    # ------------------------------------------------------------------------------------------ informe
    def informe(self) -> dict | None:
        """Lo que se suma a `resultados.combate`; None si la corrida no tuvo combate."""
        if not self.habilitado:
            return None
        return {"parametros": parametros(),
                "dotaciones": [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in x.items()} for x in self.dotaciones],
                "descargas": [dict(x) for x in self.descargas], "vencidas": int(self.vencidas), "brechas": int(self.brechas),
                "consolidadas": int(self.consolidadas),
                "linea_m": round(self.linea_m, 1), "celdas_linea_final": int(self.linea.sum()), "escapes": int(self.escapes),
                "celdas_linea_sha256": sha256_indices(np.flatnonzero(self.linea.ravel())), "horas": list(self.horas),
                "archivo": ARCHIVO}
