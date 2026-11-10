import numpy as np

from incendios_sl.fuels.clasificacion import clasificar
from incendios_sl.fuels.tabla import waf_sin_abrigo_baughman, generar_tabla, CLASES_V1


def test_clasificacion_por_cobertura_y_ndvi():
    cob = np.array([[33, 24, 12, 12], [19, 19, 77, 3], [4, 66, 9, 27]], np.uint8)
    ndvi = np.array([[0.1, 0.1, 0.2, 0.5], [0.1, 0.3, 0.3, 0.6], [np.nan, 0.4, 0.5, 0.1]], np.float32)
    val = np.isfinite(ndvi)
    clase, curado, calidad = clasificar(cob, ndvi, val)
    assert clase.tolist() == [[0, 0, 1, 1], [0, 2, 3, 6], [5, 4, 7, 0]]   # cultivo con NDVI<0.15 -> no combustible
    assert curado[0, 2] == np.float32(0.8) and curado[0, 3] == np.float32(0.5)
    assert calidad[2, 0] == 0 and calidad[0, 0] == 1
    # sin índices: solo cobertura
    clase2, _, cal2 = clasificar(cob, None, None)
    assert clase2[1, 0] == 2 and cal2.sum() == 0


def test_todas_las_coberturas_asignadas():
    cods = {c for cl in CLASES_V1 for c in cl["coberturas"]}
    leyenda = {3, 4, 6, 66, 77, 63, 12, 11, 73, 18, 19, 36, 15, 9, 21, 24, 25, 34, 33, 27}
    faltan = leyenda - cods
    assert faltan == {73}, faltan   # turberas no existen en San Luis; única clase sin regla


def test_waf_baughman_reproduce_valores_publicados():
    # Baughman & Albini 1980 / Andrews 2012: para viento a 20 ft sobre la vegetación, WAF = 1.83 / ln((20+0.36H)/(0.13H))
    for H_ft in [0.5, 1.0, 2.0, 6.0]:
        H = H_ft * 0.3048
        esperado = 1.83 / np.log((20 + 0.36 * H_ft) / (0.13 * H_ft))
        assert abs(waf_sin_abrigo_baughman(H, 20 * 0.3048) - esperado) < 0.005
    # a 10 m el factor es menor que a 20 ft (6.1 m)
    assert waf_sin_abrigo_baughman(0.3, 10.0) < waf_sin_abrigo_baughman(0.3, 6.096)


def test_tabla_combustibles(tmp_path):
    df = generar_tabla(tmp_path / "t.csv")
    assert len(df) == 8 and (df.k_clase == 1.0).all()
    gr2 = df[df.analogo_sb == "GR2"].iloc[0]
    assert abs(gr2.w0_herb_kg_m2 - 0.2242) < 1e-3 and abs(gr2.profundidad_m - 0.3048) < 1e-6 and gr2.mx_muerto_pct == 15
    assert df[df.clase == 0].w0_1h_kg_m2.iloc[0] == 0
