"""Supresión desde cuarteles (L03, protocolo v1.3 §2.4).

Cada dotación llega en su minuto (desde t0) y desde entonces construye `produccion_linea_m_h` metros de línea por hora.
En cada paso, el presupuesto de línea se gasta conteniendo celdas del frente activo (en combustión y con vecinas aún
no alcanzadas) cuya longitud de llama LOCAL (en su dirección de avance, `llama_local`) es menor que `llama_max_m` (ataque directo), de menor a mayor llama: primero
flancos y cola, después la cabeza si la llama lo permite. Una celda contenida consume `res` metros de línea y deja de
propagar (sus vecinas pendientes se anulan); termina de quemarse por la regla normal del autómata.

El presupuesto que no se puede gastar (no hay frente atacable) no se acumula.

`intensidad` (v4.0, `parametros.supresion.intensidad`) elige la llama de decisión:
- `avance` (por defecto, V.4): dirección de avance origen heredado → celda (`llama_local`). En las celdas que son su
  propio origen (re-anclaje de Huygens, modo estocástico de los ensembles) es la llama de CABEZA: con ensemble L03 casi no
  contiene. Se conserva por defecto porque reproduce V.4 bit a bit.
- `v3`: la llama hacia la vecina pendiente (combustible) más expuesta, con la elipse de la celda (`llama_enlaces`, el
  criterio de intensidad de v3.0 / `contencion.intensidad: v3`); no depende del origen heredado.
"""

from __future__ import annotations

import numpy as np

INTENSIDADES = ("avance", "v3")


class Supresion:
    def __init__(self, llegadas_min: list[float], produccion_linea_m_h: float, llama_max_m: float, res_m: float,
                 intensidad: str = "avance"):
        self.llegadas = sorted(float(x) for x in llegadas_min)
        self.p = float(produccion_linea_m_h)
        self.llama_max = float(llama_max_m)
        self.res = float(res_m)
        self.intensidad = str(intensidad)
        if self.intensidad not in INTENSIDADES:
            raise ValueError(f"supresion.intensidad debe ser avance o v3 (vino {self.intensidad!r})")
        self.resto_m = 0.0
        self.linea_m = 0.0
        self.celdas = 0
        self.contenida = None

    @classmethod
    def desde_cfg(cls, cfg: dict, res_m: float):
        s = cfg.get("parametros", {}).get("supresion") or {}
        if not s.get("activo"):
            return None
        return cls(s.get("llegadas_min", []), s.get("produccion_linea_m_h", 500.0), s.get("llama_max_m", 2.4), res_m,
                   s.get("intensidad", "avance"))

    def dotaciones(self, t_min: float) -> int:
        return sum(1 for t in self.llegadas if t <= t_min + 1e-9)

    def aplicar(self, au, t_ini: float, t_fin: float) -> int:
        """Gasta la línea construida entre t_ini y t_fin (minutos desde t0). Devuelve las celdas contenidas en el paso."""
        if self.contenida is None:
            self.contenida = np.zeros((au.H, au.W), bool)
        horas = sum(max(0.0, t_fin - max(t_ini, t)) for t in self.llegadas) / 60.0
        if horas <= 0 or len(au.act) == 0:
            return 0
        presupuesto = self.resto_m + self.p * horas
        llama = self.llama_enlaces(au) if self.intensidad == "v3" else self.llama_local(au)
        frente = au.act_pend.any(1) & (llama < self.llama_max)
        cand = np.flatnonzero(frente)
        if cand.size == 0:
            self.resto_m = 0.0
            return 0
        n = int(presupuesto // self.res)
        if n == 0:
            self.resto_m = presupuesto
            return 0
        sel = cand[np.argsort(llama[cand], kind="stable")[:n]]
        au.act_pend[sel, :] = False
        f, c = np.divmod(au.act[sel], au.W)
        self.contenida[f, c] = True
        usado = len(sel) * self.res
        self.resto_m = presupuesto - usado if len(sel) == n else 0.0
        self.linea_m += usado
        self.celdas += len(sel)
        return len(sel)

    @staticmethod
    def llama_local(au) -> np.ndarray:
        """Longitud de llama en la dirección de avance de cada celda activa (origen heredado → celda).

        El autómata guarda la llama de la cabeza (`act_llama`); en flancos y cola la intensidad de Byram escala con
        R(θ)/R_max de la misma elipse, y la llama con I^0,46 (Byram 1959)."""
        from ..physics.elipse import ros_direccional
        f, c = np.divmod(au.act, au.W)
        rel = ros_direccional(1.0, au.excentricidad[f, c].astype("float64"), au.act_theta_self - au.rumbo_cab[f, c])
        rel = np.where(au.act_dist_self > 0, np.nan_to_num(rel, nan=1.0), 1.0)
        return au.act_llama * np.clip(rel, 0.0, 1.0) ** 0.46

    @staticmethod
    def llama_enlaces(au) -> np.ndarray:
        """Longitud de llama hacia la vecina pendiente (combustible) más expuesta de cada celda activa: la llama de cabeza
        escalada con (max_k R(θ_k)/R_max)^0,46, θ_k = rumbo del enlace desde la celda (`Automata.intensidad_enlaces`);
        0 si no le quedan vecinas por encender."""
        from . import estados as E
        n = len(au.act)
        if n == 0:
            return np.zeros(0, "float32")
        f, c = np.divmod(au.act, au.W)
        fv = np.clip(f[:, None] + au.df[None, :], 0, au.H - 1); cv = np.clip(c[:, None] + au.dc[None, :], 0, au.W - 1)
        I = np.where(au.estado[fv, cv] == E.COMBUSTIBLE, au.intensidad_enlaces(slice(None)), 0.0).max(1)
        IB = au.act_IB.astype("float64")
        rel = np.where(IB > 0, I / np.maximum(IB, 1e-12), 0.0)
        return au.act_llama * np.clip(rel, 0.0, 1.0) ** 0.46

    def resumen(self, t_min: float) -> dict:
        return {"dotaciones": self.dotaciones(t_min), "linea_km": round(self.linea_m / 1000, 3), "celdas_contenidas": int(self.celdas),
                "proxima_llegada_min": next((t for t in self.llegadas if t > t_min), None)}
