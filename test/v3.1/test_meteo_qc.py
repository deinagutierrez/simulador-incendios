import numpy as np
import pandas as pd

from incendios_sl.grilla import Grilla
from incendios_sl.meteorology.openmeteo import control_calidad, puntos_malla, VARIABLES_OBLIGATORIAS


def test_puntos_malla_dentro_de_la_grilla():
    g = Grilla("EPSG:5345", 30.0, 3513060, 6367770, 3563220, 6417900).ampliar(10020)
    p = puntos_malla(g, 4)
    assert len(p) == 16 and p.x.between(g.xmin, g.xmax).all() and p.y.between(g.ymin, g.ymax).all()
    assert p.lon.between(-66.1, -65.1).all() and p.lat.between(-33.0, -32.2).all()


def test_control_calidad_detecta_fuera_de_rango_duplicados_y_huecos():
    t = pd.date_range("2024-09-18", periods=6, freq="h", tz="UTC")
    df = pd.DataFrame({"punto_id": "p00", "time_utc": t, "temperature_2m": [20, 21, 99, 22, 23, 24],
                       "relative_humidity_2m": [50, 60, 70, 150, 40, 30], "wind_speed_10m": [1, 2, np.nan, np.nan, np.nan, 3],
                       "wind_direction_10m": [0, 90, 180, 270, 360, 10], "precipitation": [0, 0, 0, 0, 0, 0]})
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    inf = control_calidad(df, VARIABLES_OBLIGATORIAS)
    assert inf["duplicados"] == 1
    assert inf["variables"]["temperature_2m"]["fuera_de_rango"] == 1 and np.isnan(df.temperature_2m.iloc[2])
    assert inf["variables"]["relative_humidity_2m"]["fuera_de_rango"] == 1
    assert inf["max_horas_consecutivas_faltantes_obligatorias"] == 3
