"""Adaptador del motor v4.0 para el combate común (`combate.py`; decisión D-E3-36).

No cambia ningún archivo de src/v4.0 ni usa su contención (`ca/contencion.py` sigue apagada): el método es el de
`combate.py`, igual que en v3.1. De v4.0 se usan solo sus piezas públicas:

- la física de celdas arbitrarias (`Automata.fisica_celdas`) y la probabilidad de cruce de barreras (`contencion._p_barrera`),
  para la intensidad hacia cada vecina;
- el gancho `Automata.filtro_enlaces`, que el autómata consulta al activar cada celda y en cada sub-paso: ahí la línea anula
  los enlaces de las celdas frenadas, los que llegan a una celda de línea y los que la atraviesan;
- la cola de igniciones y `_activar_cola`, para reavivar una celda con el mismo código con que el motor enciende cualquiera.

`habilitar()` instala el filtro la primera vez que hay combate. Hasta entonces el autómata no se toca: una corrida sin
combate es idéntica a las de siempre.

Frenar: una celda de la banda activa pierde sus enlaces pendientes; una que todavía espera en la cola (encendida en el último
paso) queda sin enlaces cuando el motor la activa, por el filtro. En los dos casos termina de quemarse por la regla normal.

Bloquear (una descarga sobre combustible sin quemar): no hace falta tocar el autómata, porque el filtro ya anula los enlaces
que llegan a una celda de línea. Desbloquear y reavivar: el filtro anuló esos enlaces en el lugar (`act_pend &= …`), así que
al quitar celdas de línea se vuelven a marcar como pendientes los enlaces de la banda activa hacia vecinas combustibles
(`_restaurar_pendientes`); los que la línea siga cortando los vuelve a anular el filtro en el sub-paso siguiente. Una celda
activa que esperaba junto a una franja de agua la cruza apenas se seca.

Reavivar: la celda vuelve a la banda activa como su propio origen (sale de la banda si estaba, pasa por la cola y
`_activar_cola` le arma las filas), con el avance en cero, sin crédito de tiempo y con la residencia contada desde ahora;
`t_llegada` no cambia. Es el equivalente de `_activar` en v3.1: la celda propaga otra vez hacia sus vecinas libres, cada una a
su velocidad.
"""
from __future__ import annotations

import numpy as np


class AdaptadorV40:
    def __init__(self, au):
        self.au = au
        self.forma = (int(au.H), int(au.W))
        self.res = float(au.res)
        self.df = np.asarray(au.df, np.int64)
        self.dc = np.asarray(au.dc, np.int64)
        self.K = int(au.K)
        self.combate = None                         # lo pone el conductor: de ahí se leen `linea` y `frenada`

    # ------------------------------------------------------------------------------------------ preparación
    def habilitar(self) -> None:
        au = self.au
        p = au.cfg.get("parametros") or {}
        propia = any((p.get(k) or {}).get("activo") for k in ("contencion", "supresion"))
        if propia or au.filtro_enlaces is not None or getattr(au, "contencion", None) is not None or getattr(au, "supresion", None) is not None:
            raise ValueError("la corrida ya usa la contención propia del motor v4.0: el combate de la app no se le suma")
        if self.combate is None:
            raise RuntimeError("el adaptador no tiene su combate")
        au.filtro_enlaces = self._filtro

    def _filtro(self, idx: np.ndarray) -> np.ndarray:
        """(n, K) enlaces permitidos de las celdas `idx`: ninguno si la celda está frenada; no hacia una celda de línea; no a
        través de la línea."""
        from combate import cortado
        co = self.combate
        idx = np.asarray(idx, np.int64)
        out = np.ones((len(idx), self.K), bool)
        if not len(idx) or not co.linea.any():
            return out
        H, W = self.forma
        f, c = np.divmod(idx, W)
        out[co.frenada[f, c], :] = False
        for k in range(self.K):
            a, b = int(self.df[k]), int(self.dc[k])
            out[:, k] &= ~co.linea[np.clip(f + a, 0, H - 1), np.clip(c + b, 0, W - 1)]
            out[:, k] &= ~cortado(co.linea, f, c, a, b)
        return out

    def sincronizar(self, n_linea: int) -> None:
        pass                                        # v4.0 no lleva la cuenta: su bucle sigue hasta el horizonte o sin avance

    def hora_utc(self, t_min: float) -> int:
        import pandas as pd
        return int((self.au.t0 + pd.Timedelta(minutes=float(t_min))).tz_convert("UTC").hour)

    def rc(self, xy) -> tuple[np.ndarray, np.ndarray]:
        """(filas, columnas) fraccionarias en la grilla de la simulación de puntos en EPSG:5345."""
        from pyproj import CRS, Transformer
        g = self.au.capas.grilla
        xy = np.asarray(xy, "float64")
        x, y = xy[:, 0], xy[:, 1]
        if CRS.from_user_input("EPSG:5345") != CRS.from_user_input(g.crs):
            x, y = Transformer.from_crs("EPSG:5345", g.crs, always_xy=True).transform(x, y)
        return (g.ymax - np.asarray(y, "float64")) / g.res, (np.asarray(x, "float64") - g.xmin) / g.res

    # ------------------------------------------------------------------------------------------ lectura
    def afectada(self) -> np.ndarray:
        from simulador.ca import estados as E
        return self.au.estado >= E.IGNICION

    def combustible(self) -> np.ndarray:
        from simulador.ca import estados as E
        return self.au.estado == E.COMBUSTIBLE

    def _en_cola(self) -> np.ndarray:
        from simulador.ca import estados as E
        au = self.au
        if not au.cola_ign:
            return np.zeros(0, np.int64)
        idx = np.unique(np.fromiter((i for i, _ in au.cola_ign), np.int64, len(au.cola_ign)))
        return idx[au.estado.ravel()[idx] == E.IGNICION]

    def activas(self) -> np.ndarray:
        """La banda activa más las celdas encendidas en el último paso, que esperan en la cola: son el borde de afuera del
        fuego y, si no se las cuenta, la línea queda una celda atrás."""
        return np.unique(np.concatenate([np.asarray(self.au.act, np.int64), self._en_cola()]))

    def intensidad(self, idx: np.ndarray) -> np.ndarray:
        """(n, K) kW/m: intensidad de Byram de cabeza por R(θ_k)/R_max con la elipse de la celda en este instante
        (θ_k = rumbo del enlace − rumbo de la cabeza) y por la probabilidad de cruce si el enlace tiene barrera."""
        from simulador.ca import contencion as cont
        from simulador.physics.elipse import ros_direccional
        au = self.au
        idx = np.asarray(idx, np.int64)
        if not len(idx):
            return np.zeros((0, self.K))
        s = au.fisica_celdas(idx, au.t)
        R, rumbo, e, IB = (np.asarray(s[k], "float64") for k in ("R_max", "rumbo", "e", "IB"))
        IB = np.where((R > 0) & ~np.asarray(s["ext"], bool), np.nan_to_num(IB, nan=0.0), 0.0)
        rel = np.clip(np.nan_to_num(ros_direccional(1.0, e[:, None], np.asarray(au.rumbo, float)[None, :] - rumbo[:, None]), nan=0.0), 0.0, 1.0)
        I = IB[:, None] * rel
        f, c = np.divmod(idx, au.W)
        fv = np.clip(f[:, None] + self.df[None, :], 0, au.H - 1); cv = np.clip(c[:, None] + self.dc[None, :], 0, au.W - 1)
        P = cont._p_barrera(au, f, c, fv, cv, I, IB)
        return I if P is None else I * P

    # ------------------------------------------------------------------------------------------ frenar y reavivar
    def _filas(self, idx: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Filas de la banda activa de las celdas `idx` que están en ella: (filas, máscara de `idx` que tiene fila)."""
        act = np.asarray(self.au.act, np.int64)
        if not len(act) or not len(idx):
            return np.zeros(0, np.int64), np.zeros(len(idx), bool)
        orden = np.argsort(act, kind="stable")
        pos = np.clip(np.searchsorted(act[orden], idx), 0, len(act) - 1)
        esta = act[orden][pos] == idx
        return orden[pos[esta]], esta

    def frenar(self, idx: np.ndarray, t_min: float) -> None:
        filas, _ = self._filas(np.asarray(idx, np.int64))
        if len(filas):
            self.au.act_pend[filas, :] = False       # las de la cola quedan sin enlaces al activarse (filtro)

    def bloquear(self, idx: np.ndarray, t_min: float) -> None:
        pass                                        # el filtro ya anula los enlaces que llegan a una celda de línea

    def desbloquear(self, idx: np.ndarray, t_min: float) -> None:
        self._restaurar_pendientes()

    def _restaurar_pendientes(self) -> None:
        """Vuelve a marcar como pendientes los enlaces de la banda activa hacia vecinas combustibles (con la misma regla de
        `Automata._activar_cola`: dentro de la grilla, vecina COMBUSTIBLE y, en los saltos de caballo, intermedias que no
        sean NO_COMBUSTIBLE), salvo los que la línea sigue cortando. Un enlace solo deja de estar pendiente cuando su vecina
        deja de ser COMBUSTIBLE o cuando lo anula el filtro, así que esto solo recupera lo que anuló la línea que ya no está."""
        from simulador.ca import estados as E
        au = self.au
        if not len(au.act):
            return
        act = np.asarray(au.act, np.int64)
        f, c = np.divmod(act, au.W)
        fv = f[:, None] + self.df[None, :]; cv = c[:, None] + self.dc[None, :]
        dentro = (fv >= 0) & (fv < au.H) & (cv >= 0) & (cv < au.W)
        fv = np.clip(fv, 0, au.H - 1); cv = np.clip(cv, 0, au.W - 1)
        pend = dentro & (au.estado[fv, cv] == E.COMBUSTIBLE)
        for k in range(8, self.K):
            a, b = int(self.df[k]), int(self.dc[k])
            intermedias = [(a - np.sign(a), b), (a, b - np.sign(b))] if abs(a) == 2 else [(a, b - np.sign(b)), (a - np.sign(a), b)]
            for di, dj in intermedias:
                pend[:, k] &= au.estado[np.clip(f + int(di), 0, au.H - 1), np.clip(c + int(dj), 0, au.W - 1)] != E.NO_COMBUSTIBLE
        au.act_pend |= pend & self._filtro(act)

    def reavivar(self, idx: np.ndarray, t_min: float) -> None:
        from simulador.ca import estados as E
        au = self.au
        idx = np.unique(np.asarray(idx, np.int64))
        f, c = np.divmod(idx, au.W)
        estado = au.estado[f, c]
        ya = (estado == E.COMBUSTION) | (estado == E.QUEMADO)   # las que esperan en la cola se activan solas, ya sin línea
        idx, f, c = idx[ya], f[ya], c[ya]
        if not len(idx):
            return
        t = float(au.minutos(au.t))
        filas, _ = self._filas(idx)
        if len(filas):
            queda = np.ones(len(au.act), bool); queda[filas] = False
            au._compactar(queda)
        au.estado[f, c] = E.IGNICION
        au.origen[f, c] = idx
        au.retardo_ign[f, c] = 0.0
        au.o_rumbo[f, c] = np.nan
        au.cola_ign.extend((int(i), t) for i in idx)
        au._activar_cola(t)                          # activa también lo que ya estaba listo en la cola, como haría el paso
        filas, esta = self._filas(idx)
        if not esta.all():
            raise RuntimeError("el motor no activó las celdas reavivadas")
        au.act_credito[filas] = 0.0                  # sin crédito: el avance empieza ahora, no en la llegada original
        au.act_t0[filas] = t                         # la residencia y las llegadas a las vecinas se cuentan desde ahora
        au.act_nuevo[filas] = False
        self._restaurar_pendientes()                 # las demás celdas activas recuperan lo que cortaba la línea que se fue
