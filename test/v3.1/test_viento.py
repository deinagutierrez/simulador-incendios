import numpy as np
import xarray as xr

from incendios_sl.grilla import Grilla
from incendios_sl.meteorology.openmeteo import uv_desde_vel_dir, vel_dir_desde_uv, serie_dominio
from incendios_sl.wind.windninja import BibliotecaViento, leer_asc
import pandas as pd


def test_convencion_meteorologica_uv():
    # viento DESDE el norte (0°): sopla hacia el sur -> V negativo, U ~ 0
    u, v = uv_desde_vel_dir(np.array([10.0]), np.array([0.0]))
    assert abs(u[0]) < 1e-9 and v[0] == -10
    # desde el oeste (270°): sopla hacia el este -> U positivo
    u, v = uv_desde_vel_dir(np.array([5.0]), np.array([270.0]))
    assert abs(u[0] - 5) < 1e-9 and abs(v[0]) < 1e-9
    # ida y vuelta
    vel, d = vel_dir_desde_uv(*uv_desde_vel_dir(np.array([7.0, 3.0]), np.array([45.0, 200.0])))
    assert np.allclose(vel, [7, 3]) and np.allclose(d, [45, 200])


def test_promedio_vectorial_dominio():
    t = pd.Timestamp("2024-09-18T12:00Z")
    df = pd.DataFrame({"time_utc": [t, t], "punto_id": ["a", "b"], "temperature_2m": [20.0, 30.0],
                       "relative_humidity_2m": [40.0, 60.0], "precipitation": [0.0, 1.0],
                       "wind_speed_10m": [10.0, 10.0], "wind_direction_10m": [350.0, 10.0]})
    s = serie_dominio(df)
    assert s.temperature_2m.iloc[0] == 25 and s.n_puntos.iloc[0] == 2
    assert abs(s.wind_direction_10m.iloc[0] - 0) < 1e-6 or abs(s.wind_direction_10m.iloc[0] - 360) < 1e-6
    assert abs(s.wind_speed_10m_vectorial.iloc[0] - 10 * np.cos(np.radians(10))) < 1e-6


def test_leer_asc(tmp_path):
    p = tmp_path / "x_u.asc"
    p.write_text("ncols 3\nnrows 2\nxllcorner 100\nyllcorner 200\ncellsize 10\nNODATA_value -9999\n1 2 3\n4 -9999 6\n")
    a, h = leer_asc(p)
    assert a.shape == (2, 3) and np.isnan(a[1, 1]) and a[0, 2] == 3 and h["cellsize"] == 10


def test_biblioteca_viento_escalado_e_interpolacion(tmp_path):
    dirs = np.arange(0, 360, 90.0)
    ny, nx = 4, 5
    U = np.zeros((4, ny, nx), np.float32); V = np.zeros_like(U)
    # campos unitarios sintéticos: viento desde N -> V=-1; desde E -> U=-1; desde S -> V=+1; desde O -> U=+1
    V[0] = -1; U[1] = -1; V[2] = 1; U[3] = 1
    xs = 1000 + (np.arange(nx) + 0.5) * 100; ys = 2000 + (ny - np.arange(ny) - 0.5) * 100
    ds = xr.Dataset({"U": (("direccion", "y", "x"), U), "V": (("direccion", "y", "x"), V)},
                    coords={"direccion": dirs, "y": ys, "x": xs}, attrs={"crs": "EPSG:5345"})
    p = tmp_path / "lib.nc"; ds.to_netcdf(p)
    lib = BibliotecaViento(p)
    assert lib.grilla.bounds == (1000, 2000, 1500, 2400)
    u, v = lib.campo(8.0, 0.0)
    assert np.allclose(v, -8) and np.allclose(u, 0)
    u, v = lib.campo(4.0, 45.0)          # interpolación lineal entre N y E
    assert np.allclose(u, -2) and np.allclose(v, -2)
    u, v = lib.campo(4.0, 315.0)         # entre O (270) y N (360): ciclo
    assert np.allclose(u, 2) and np.allclose(v, -2)
    # remuestreo a una grilla de 50 m dentro de la malla
    dst = Grilla("EPSG:5345", 50.0, 1100, 2100, 1400, 2300)
    U2, V2 = lib.a_grilla(*lib.campo(8.0, 0.0), dst)
    assert U2.shape == (4, 6) and np.allclose(V2, -8)
    lib.cerrar()
