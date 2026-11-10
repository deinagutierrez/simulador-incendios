"""Viento horario local de v3.1 (docs/v3.1/04): pesos IDW, mezcla de campos y nubosidad estimada."""
import numpy as np
import pandas as pd

from incendios_sl.grilla import Grilla
from incendios_sl.wind.horario import PesosIDW, nubosidad_pct, viento_idw


class _LibFalsa:
    """Biblioteca mínima: campo unitario uniforme con la dirección pedida (U este, V norte por m/s)."""
    def __init__(self):
        self.grilla = Grilla("EPSG:5345", 100.0, 4_000_000.0, 6_390_000.0, 4_010_000.0, 6_400_000.0)

    def campo(self, vel, d):
        a = np.radians((d + 180.0) % 360.0)        # dirección hacia la que sopla
        u = np.full(self.grilla.shape, vel * np.sin(a), np.float32); v = np.full(self.grilla.shape, vel * np.cos(a), np.float32)
        return u, v


def test_pesos_idw_suman_uno_y_viento_uniforme_se_conserva():
    lib = _LibFalsa()
    from pyproj import Transformer
    tr = Transformer.from_crs("EPSG:5345", "EPSG:4326", always_xy=True)
    pts = {f"p{i}": tr.transform(4_000_000.0 + 2000 * i, 6_395_000.0) for i in range(4)}
    p = PesosIDW(lib, pts)
    assert np.allclose(p.w.sum(axis=0), 1.0, atol=1e-5)
    U, V = viento_idw(lib, p, np.full(4, 5.0), np.full(4, 270.0))   # viento del O a 5 m/s en todos los puntos
    assert np.allclose(U, 5.0, atol=1e-4) and np.allclose(V, 0.0, atol=1e-4)


def test_nubosidad_en_rango_y_noche_arrastra_valor():
    t = pd.Series(pd.date_range("2024-09-02T00:00Z", periods=48, freq="h"))
    sw = pd.Series(np.where((t.dt.hour >= 12) & (t.dt.hour <= 21), 600.0, 0.0))
    n = nubosidad_pct(t, sw)
    assert np.all((n >= 0) & (n <= 100)) and not np.isnan(n).any()
