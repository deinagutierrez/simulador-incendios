"""Serie meteorológica horaria estándar e interpolación al paso del autómata.

Formato (sección 2.3 del estándar):
    timestamp,temp_c,hr_pct,viento_kmh,viento_dir_deg,precip_mm,fuente
- `timestamp` ISO 8601 con huso horario; `viento_dir_deg` es la dirección DESDE donde sopla
  (convención meteorológica, 0 = N, horario); viento a 10 m.
- La interpolación es lineal en T, HR y precipitación; el viento se interpola por componentes
  (u, v) para no promediar ángulos.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .manifiesto import validar_meteo_csv

HUSO = "America/Argentina/San_Luis"


@dataclass
class EstadoMeteo:
    t: pd.Timestamp
    temp_c: float
    hr_pct: float
    viento_kmh: float          # a 10 m
    viento_dir_deg: float      # desde donde sopla
    precip_mm_h: float         # intensidad en la hora en curso


class SerieMeteo:
    def __init__(self, df: pd.DataFrame, fuente_archivo: str = ""):
        df = df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.sort_values("timestamp").reset_index(drop=True)
        self.df = df
        self.fuente_archivo = fuente_archivo
        self.t = df["timestamp"].values.astype("datetime64[s]").astype("int64")  # segundos UTC
        rad = np.deg2rad(df["viento_dir_deg"].values)
        # componentes "hacia donde va": u (este), v (norte)
        self.u = -df["viento_kmh"].values * np.sin(rad)
        self.v = -df["viento_kmh"].values * np.cos(rad)

    @classmethod
    def cargar(cls, ruta: Path) -> "SerieMeteo":
        df = validar_meteo_csv(Path(ruta))
        return cls(df, str(ruta))

    @property
    def inicio(self) -> pd.Timestamp:
        return self.df["timestamp"].iloc[0]

    @property
    def fin(self) -> pd.Timestamp:
        return self.df["timestamp"].iloc[-1]

    def cubre(self, t0: pd.Timestamp, t1: pd.Timestamp) -> bool:
        return self.inicio <= t0 and self.fin >= t1

    def _s(self, t: pd.Timestamp) -> float:
        return pd.Timestamp(t).tz_convert("UTC").value // 10**9

    def en(self, t: pd.Timestamp) -> EstadoMeteo:
        s = self._s(t)
        if s < self.t[0] or s > self.t[-1]:
            raise ValueError(f"{t} fuera de la serie meteorológica ({self.inicio} → {self.fin})")
        d = self.df
        temp = float(np.interp(s, self.t, d["temp_c"].values))
        hr = float(np.interp(s, self.t, d["hr_pct"].values))
        u = float(np.interp(s, self.t, self.u))
        v = float(np.interp(s, self.t, self.v))
        vel = float(np.hypot(u, v))
        # dirección desde donde sopla: opuesta al vector (u, v)
        dir_desde = (np.degrees(np.arctan2(-u, -v)) + 360) % 360 if vel > 1e-6 else float(d["viento_dir_deg"].values[np.searchsorted(self.t, s, side="right") - 1])
        # precipitación: la fila con timestamp T registra la lluvia de la hora que termina en T
        i = int(np.searchsorted(self.t, s, side="right"))
        i = min(max(i, 1), len(self.t) - 1)
        precip = float(d["precip_mm"].values[i])
        return EstadoMeteo(pd.Timestamp(t), temp, hr, vel, float(dir_desde), precip)

    def horas(self, t0: pd.Timestamp, t1: pd.Timestamp) -> pd.DataFrame:
        d = self.df
        m = (d["timestamp"] >= pd.Timestamp(t0).tz_convert("UTC")) & (d["timestamp"] <= pd.Timestamp(t1).tz_convert("UTC"))
        return d[m].reset_index(drop=True)


def local(t: pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(t).tz_convert(HUSO)
