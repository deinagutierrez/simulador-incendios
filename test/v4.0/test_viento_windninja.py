"""Viento WindNinja en SIM (docs/v4.0/17): lectura de la biblioteca de v3.0, orientación, composición y atajo de corrida."""
import numpy as np
import pytest

from simulador.physics.viento import BibliotecaWindNinja, CampoViento, ParametrosViento, buscar_biblioteca


def _biblioteca():
    try:
        return BibliotecaWindNinja(buscar_biblioteca())
    except FileNotFoundError:
        pytest.skip("falta la biblioteca WindNinja de v3.0 (datos/inputSimulacion/viento)")


def test_direccion_y_escala_lineal():
    b = _biblioteca()
    x = b.x0 + b.res * np.array([100.0, 350.0, 600.0]); y = b.y0 - b.res * np.array([100.0, 350.0, 600.0])
    for d in (0.0, 90.0, 180.0, 270.0):
        U, V = b.muestrear(x, y, d)
        hacia = np.radians(d + 180.0)
        # el flujo va (en media) hacia donde indica la dirección meteorológica + 180°
        assert np.mean(U * np.sin(hacia) + V * np.cos(hacia)) > 0.8
    U5, V5 = b.campo_unitario(1)
    Ui, Vi = b.muestrear(np.array([b.x0 + 200 * b.res]), np.array([b.y0 - 300 * b.res]), 5.0)
    assert Ui[0] == pytest.approx(U5[300, 200], abs=1e-6) and Vi[0] == pytest.approx(V5[300, 200], abs=1e-6)
    Um, _ = b.muestrear(np.array([b.x0 + 200 * b.res]), np.array([b.y0 - 300 * b.res]), 2.5)   # mitad entre 0° y 5°
    U0, _ = b.campo_unitario(0)
    assert Um[0] == pytest.approx(0.5 * (U0[300, 200] + U5[300, 200]), abs=1e-6)


def test_orientacion_contra_el_relieve():
    """Las filas de la biblioteca tienen que coincidir con el terreno: el viento se acelera en las crestas."""
    import rasterio
    from scipy.ndimage import uniform_filter
    from simulador.rutas import raiz_datos
    b = _biblioteca()
    p = raiz_datos() / "estaticos" / "topografia" / "mdt.tif"
    if not p.exists():
        pytest.skip("falta el MDT de sim_v4")
    with rasterio.open(p) as s:
        mdt = s.read(1).astype("float32"); T = s.transform
    z = np.where(mdt == -32768, np.nan, mdt); z = np.where(np.isfinite(z), z, np.nanmean(z))
    rel = z - uniform_filter(z, 33)
    rr, cc = np.mgrid[0:mdt.shape[0]:8, 0:mdt.shape[1]:8]
    U, V = b.muestrear(T.c + (cc + 0.5) * T.a, T.f + (rr + 0.5) * T.e, 90.0)
    assert np.corrcoef(np.hypot(U, V).ravel(), rel[rr, cc].ravel())[0, 1] > 0.5


def test_campo_viento_windninja_en_la_grilla_del_dominio():
    from simulador.io.grilla import Grilla
    b = _biblioteca()

    class Capas:                                          # lo mínimo que usa CampoViento
        mdt = np.zeros((20, 20), "float32"); nodata_mdt = -32768
        grilla = Grilla("EPSG:5345", 3513060.0, 6417900.0, 30.0, 20, 20)
    cv = CampoViento(Capas(), ParametrosViento(fuente="windninja", biblioteca=str(b.ruta)), None, Capas.grilla, None)
    assert cv.cubre
    f, c = np.nonzero(np.ones((20, 20), bool))
    vel, d = cv.velocidad_dir(f, c, 20.0, 315.0, 0)
    assert np.all(np.isfinite(vel)) and 10.0 < np.median(vel) < 30.0
    assert np.all(np.abs((d - 315.0 + 180.0) % 360.0 - 180.0) < 45.0)
    with pytest.raises(ValueError, match="fuente"):
        CampoViento(Capas(), ParametrosViento(fuente="otra"), None, Capas.grilla, None)


def test_atajo_viento_en_la_corrida():
    from incendios_sl import escenario
    t = escenario.traducir({"evento": "SL-2024-LASLAGUNAS", "hipotesis": 1, "variante": "libre", "viento": "serie"}, preparar=False)
    assert t["cfg"]["parametros"]["viento"]["fuente"] == "serie"
    t = escenario.traducir({"evento": "SL-2024-LASLAGUNAS", "hipotesis": 1, "variante": "libre"}, preparar=False)
    assert t["cfg"]["parametros"]["viento"]["fuente"] == "windninja"          # modelo_v3
    t = escenario.traducir({"evento": "SL-2024-LASLAGUNAS", "hipotesis": 1, "variante": "v4_original"}, preparar=False)
    assert t["cfg"]["parametros"]["viento"].get("fuente", "serie") == "serie"  # V.4 tal como se entregó
