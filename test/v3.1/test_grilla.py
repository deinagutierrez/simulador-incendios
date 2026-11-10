import numpy as np
import pytest
from shapely.geometry import box

from incendios_sl import config as cfgmod
from incendios_sl.grilla import Grilla, pendiente_orientacion, geometria_a_crs


@pytest.fixture
def g():
    return Grilla("EPSG:5345", 30.0, 3513060, 6367770, 3563220, 6417900)


def test_dimensiones_grilla_maestra(g):
    assert g.ncol == 1672 and g.nfil == 1671
    assert g.n_celdas == 2_793_912
    assert g.area_celda_m2 == 900.0


def test_ampliar_redondea_a_multiplo(g):
    ga = g.ampliar(10000)
    assert (ga.xmin - g.xmin) % 30 == 0 and ga.xmin == g.xmin - 10020
    r, c = g.ventana_en(ga)
    assert (r, c) == (334, 334)
    with pytest.raises(ValueError):
        Grilla("EPSG:5345", 30.0, g.xmin + 10, g.ymin, g.xmax + 10, g.ymax).ventana_en(g)


def test_rc_xy_ida_y_vuelta(g):
    x, y = g.rc_a_xy(np.array([0, 100, 1670]), np.array([0, 50, 1671]))
    r, c = g.xy_a_rc(x, y)
    assert r.tolist() == [0, 100, 1670] and c.tolist() == [0, 50, 1671]


def test_centroide_dominio_cae_dentro(g):
    r, c = g.lonlat_a_rc(-65.5936, -32.6062)
    assert g.dentro(r, c)
    assert 700 < r < 1000 and 700 < c < 1000


def test_area_proyectada_del_dominio_exacto():
    import geopandas as gpd
    p = cfgmod.ruta("primero_cuadrado.geojson")
    if not p.exists():
        pytest.skip("requiere el insumo primero_cuadrado.geojson (ver datos/README.md)")
    gdf = gpd.read_file(p)
    dom = gdf[gdf["tipo"] == "dominio_exacto_25_celdas"].to_crs(5345)
    assert abs(dom.area.iloc[0] / 1e6 - 2500.0) < 1.0


def test_rasterizar_cuadrado(g):
    geom = box(g.xmin + 300, g.ymax - 600, g.xmin + 600, g.ymax - 300)  # 10 x 10 celdas
    m = g.rasterizar([(geom, 1)])
    assert m.sum() == 100 and m[10:20, 10:20].all()


def test_pendiente_orientacion_planos():
    n = 21
    yy, xx = np.mgrid[0:n, 0:n]
    res = 30.0
    # plano que sube hacia el norte (fila 0 es el norte): z crece al disminuir la fila
    z = (n - 1 - yy) * res * np.tan(np.radians(10))
    pend, asp = pendiente_orientacion(z, res)
    assert abs(pend[10, 10] - 10) < 0.01 and abs(asp[10, 10] - 180) < 0.01   # la ladera mira al sur
    # plano que sube hacia el este -> mira al oeste
    z = xx * res * np.tan(np.radians(20))
    pend, asp = pendiente_orientacion(z, res)
    assert abs(pend[10, 10] - 20) < 0.01 and abs(asp[10, 10] - 270) < 0.01
    # plano horizontal
    pend, asp = pendiente_orientacion(np.full((n, n), 500.0), res)
    assert pend.max() == 0 and (asp == -1).all()


def test_reproyeccion_geometria():
    from shapely.geometry import Point
    p = geometria_a_crs(Point(-66.0, -32.0), "EPSG:4326", "EPSG:5345")
    assert abs(p.x - 3_500_000) < 1.0   # meridiano central de faja 3 -> falso este 3.500.000
