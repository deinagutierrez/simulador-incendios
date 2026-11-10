"""Entradas sintéticas para pruebas del autómata (sin datos externos)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..fuels.tabla import generar_tabla
from .motor import EntradasSimulacion


def tabla_prueba(tmp_path=None) -> pd.DataFrame:
    import tempfile
    from pathlib import Path
    p = Path(tmp_path or tempfile.mkdtemp()) / "tabla.csv"
    return generar_tabla(p)


def meteo_constante(horas: int, temp=25.0, hr=30.0, vel=0.0, dir_desde=270.0, prec=0.0, m1=6.0, inicio="2024-01-01T00:00Z"):
    t = pd.date_range(inicio, periods=horas + 1, freq="h")
    met = pd.DataFrame({"time_utc": t, "temperature_2m": temp, "relative_humidity_2m": hr, "wind_speed_10m_vectorial": vel,
                        "wind_direction_10m": dir_desde, "precipitation": prec})
    hum = pd.DataFrame({"time_utc": t, "ffmc": 90.0, "m_1h_pct": m1, "m_10h_pct": m1 + 1, "m_100h_pct": m1 + 2, "lluvia_24h_mm": 0.0})
    return met, hum


def entradas_homogeneas(n=201, res=30.0, clase=1, pendiente=0.0, orientacion=-1.0, curado=0.8, lfmc=60.0, vel=0.0, dir_desde=270.0,
                        horas=6, m1=6.0, ignicion=None, tabla=None, barrera=None) -> EntradasSimulacion:
    """Grilla homogénea n×n de una clase; viento uniforme opcional; barrera = (fila0, fila1, col0, col1) no combustible."""
    shape = (n, n)
    mascara = np.ones(shape, np.uint8)
    cl = np.full(shape, clase, np.uint8)
    if barrera:
        f0, f1, c0, c1 = barrera; cl[f0:f1, c0:c1] = 0
    met, hum = meteo_constante(horas, vel=vel, dir_desde=dir_desde, m1=m1)
    rad = np.deg2rad(dir_desde)
    U = np.full(shape, -vel * np.sin(rad), np.float32); V = np.full(shape, -vel * np.cos(rad), np.float32)

    def viento(v, d):
        r = np.deg2rad(d)
        return np.full(shape, -v * np.sin(r), np.float32), np.full(shape, -v * np.cos(r), np.float32)
    ign = ignicion or [(n // 2, n // 2, 0.0)]
    return EntradasSimulacion(res_m=res, mascara=mascara, clase=cl, pendiente_deg=np.full(shape, pendiente, np.float32),
                              orientacion_deg=np.full(shape, orientacion, np.float32), curado=np.full(shape, curado, np.float32),
                              lfmc_herb=np.full(shape, lfmc, np.float32), lfmc_lenoso=np.full(shape, lfmc + 30, np.float32),
                              tabla=tabla if tabla is not None else tabla_prueba(), meteo=met, humedad=hum, viento=viento, igniciones=ign,
                              t_inicio_utc=pd.Timestamp(met.time_utc.iloc[0]), t_fin_utc=pd.Timestamp(met.time_utc.iloc[-1]))
