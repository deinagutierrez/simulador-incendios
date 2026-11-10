"""Métricas de v3.1: IoU a igual superficie y primeras detecciones (docs/v3.1/01)."""
import numpy as np
import pandas as pd

from incendios_sl.grilla import Grilla
from incendios_sl.validation.metricas import iou_igual_superficie, metricas_primera_deteccion


def _grilla(n=60):
    return Grilla("EPSG:5345", 30.0, 4_000_000.0, 6_400_000.0, 4_000_000.0 + n * 30, 6_400_000.0 + n * 30)


def test_iou_igual_superficie_independiente_de_la_velocidad():
    n = 60; yy, xx = np.mgrid[:n, :n]
    d = np.hypot(yy - 30, xx - 30)
    ref = d <= 10; valido = np.ones((n, n), bool)
    for v in (1.0, 5.0):          # mismo fuego circular a dos velocidades: misma forma, IoU 1
        r = iou_igual_superficie(d * 30 / v, ref, valido, 30.0)
        assert r["alcanza"] and r["iou"] > 0.95
    assert iou_igual_superficie(d * 30, ref, valido, 30.0)["horas"] > iou_igual_superficie(d * 6, ref, valido, 30.0)["horas"]


def test_primera_deteccion_clasifica_adelantado_atrasado():
    g = _grilla(); n = 60
    t0 = pd.Timestamp("2024-09-02T12:00:00Z")
    x, y = g.rc_a_xy(30, 30)
    from pyproj import Transformer
    lon, lat = Transformer.from_crs(g.crs, "EPSG:4326", always_xy=True).transform(x, y)
    # detección a las 18 UTC (6 h después de t0); el mismo lugar vuelve a detectarse a las 06 UTC (no es primera)
    hs = pd.DataFrame({"date": ["2024-09-02", "2024-09-03"], "acq_time_s": [18 * 3600, 6 * 3600], "lon": [lon] * 2, "lat": [lat] * 2})
    for t_lleg_h, clase in ((4.0, "a_tiempo"), (30.0, "atrasado")):
        ta = np.full((n, n), np.inf); ta[30, 30] = t_lleg_h * 3600
        r = metricas_primera_deteccion(ta, g, hs, t0, ventana_h=13)
        assert r["n_primeras"] == 1 and r[f"frac_{clase}"] == 1.0
    ta = np.full((n, n), np.inf)
    assert metricas_primera_deteccion(ta, g, hs, t0)["frac_no_alcanzado"] == 1.0
    # adelantado: con la detección 20 h después de la llegada
    hs2 = hs.assign(date=["2024-09-03", "2024-09-04"])
    ta[30, 30] = 4 * 3600
    r = metricas_primera_deteccion(ta, g, hs2, t0, ventana_h=13)
    assert r["frac_adelantado"] == 1.0 and r["error_mediano_h"] < 0
