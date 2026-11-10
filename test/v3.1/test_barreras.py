"""Pruebas sintéticas del modelo v2: barreras lineales sobre enlaces y contención por combate (docs/10 §7.1)."""
import numpy as np
import pytest

from incendios_sl.simulation.automata import u01, p_cruce, longitud_llama, estencil, CONTENIDA, QUEMADA, ACTIVA
from incendios_sl.simulation.motor import Simulacion, ConfigSimulacion
from incendios_sl.simulation.sintetico import entradas_homogeneas, tabla_prueba


@pytest.fixture(scope="module")
def tabla(tmp_path_factory):
    return tabla_prueba(tmp_path_factory.mktemp("tab"))


def barrera_vertical(n: int, col: int, codigo: int = 1, nvec: int = 16) -> np.ndarray:
    """Producto sintético de barreras: línea vertical entre las columnas `col` y `col + 1`."""
    dy, dx, _, _ = estencil(nvec, 30.0)
    cod = np.zeros((n, n, nvec), np.uint8)
    cc = np.arange(n)[None, :].repeat(n, 0)
    for k in range(nvec):
        cruza = (cc <= col) != (cc + dx[k] <= col)
        cod[:, :, k] = np.where(cruza, codigo, 0)
    return cod


def test_u01_uniforme_y_determinista():
    v = np.array([u01(7, i, j, k, h) for i in range(20) for j in range(20) for k in range(5) for h in range(5)])
    assert 0.0 <= v.min() and v.max() < 1.0 and abs(v.mean() - 0.5) < 0.01 and abs(v.std() - 0.2887) < 0.01
    assert u01(7, 3, 4, 5, 6) == u01(7, 3, 4, 5, 6) and u01(7, 3, 4, 5, 6) != u01(7, 3, 4, 5, 7) and u01(7, 3, 4, 5, 6) != u01(8, 3, 4, 5, 6)


def test_longitud_llama_y_probabilidad_de_cruce():
    L = longitud_llama(1000.0, 0.0775, 0.46)
    assert abs(L - 1.84) < 0.02                       # Byram: 1.000 kW/m ≈ 1,8 m de llama
    assert longitud_llama(0.0, 0.0775, 0.46) == 0.0
    assert abs(p_cruce(2.0, 2.0, 1, 1.0, 4.0) - 0.5) < 1e-9        # L/W = λ → 0,5
    assert abs(p_cruce(4.0, 2.0, 1, 1.0, 4.0) - 1 / (1 + np.exp(-4.0))) < 1e-9 and p_cruce(0.5, 2.0, 1, 1.0, 4.0) < 0.05
    assert p_cruce(2.1, 2.0, 2, 1.0, 4.0) == 1.0 and p_cruce(1.9, 2.0, 2, 1.0, 4.0) == 0.0   # modo umbral
    assert p_cruce(5.0, 0.0, 1, 1.0, 4.0) == 1.0     # sin ancho: no hay barrera


def test_v2_apagado_identico_a_v1(tabla):
    e1 = entradas_homogeneas(n=121, clase=1, horas=6, vel=4.0, dir_desde=270.0, tabla=tabla)
    a = Simulacion(e1, ConfigSimulacion()); a.ejecutar()
    e2 = entradas_homogeneas(n=121, clase=1, horas=6, vel=4.0, dir_desde=270.0, tabla=tabla)
    e2.barreras = barrera_vertical(121, 80); e2.ancho_barrera_m = np.array([0.0, 10.0])
    b = Simulacion(e2, ConfigSimulacion(barreras_activo=False, contencion_activo=False)); b.ejecutar()
    assert np.array_equal(a.t_arr, b.t_arr) and np.array_equal(a.estado, b.estado)
    assert b.registro["v2"]["barreras_activo"] is False and b.registro["v2"]["cruces_barrera"] == 0


def test_barrera_umbral_bloquea_o_deja_pasar(tabla):
    def correr(ancho):
        e = entradas_homogeneas(n=161, clase=1, horas=6, vel=5.0, dir_desde=270.0, tabla=tabla, ignicion=[(80, 40, 0.0)])
        e.barreras = barrera_vertical(161, 100); e.ancho_barrera_m = np.array([0.0, ancho])
        s = Simulacion(e, ConfigSimulacion(barreras_activo=True, cruce_modo="umbral", cruce_lambda=1.0)); s.ejecutar()
        return s
    libre = entradas_homogeneas(n=161, clase=1, horas=6, vel=5.0, dir_desde=270.0, tabla=tabla, ignicion=[(80, 40, 0.0)])
    sl = Simulacion(libre, ConfigSimulacion()); sl.ejecutar()
    assert np.isfinite(sl.t_arr[:, 101:]).sum() > 0
    ancha = correr(1000.0)
    assert np.isfinite(ancha.t_arr[:, 101:]).sum() == 0 and ancha.registro["v2"]["bloqueos_barrera"] > 0 and ancha.registro["v2"]["cruces_barrera"] == 0
    fina = correr(0.001)
    assert np.isfinite(fina.t_arr[:, 101:]).sum() > 0 and fina.registro["v2"]["bloqueos_barrera"] == 0
    assert np.array_equal(np.isfinite(fina.t_arr), np.isfinite(sl.t_arr))


def test_fraccion_de_cruces_sigue_la_probabilidad(tabla):
    """Con β = 0 la logística vale 0,5 para cualquier L/W: la mitad de los intentos de cruce debe tener éxito."""
    e = entradas_homogeneas(n=201, clase=1, horas=10, vel=5.0, dir_desde=270.0, tabla=tabla, ignicion=[(100, 60, 0.0)])
    e.barreras = barrera_vertical(201, 80); e.ancho_barrera_m = np.array([0.0, 10.0])
    s = Simulacion(e, ConfigSimulacion(barreras_activo=True, cruce_modo="probabilistico", cruce_lambda=1.0, cruce_beta=0.0, semilla=3)); s.ejecutar()
    cr = int(s.cruces.sum()); bl = int(s.bloqueos.sum())
    assert cr + bl >= 150
    assert abs(cr / (cr + bl) - 0.5) < 0.08
    assert np.isfinite(s.t_arr[:, 101:]).sum() > 0


def test_contencion_reduce_area_y_marca_celdas(tabla):
    libre = entradas_homogeneas(n=161, clase=1, horas=12, tabla=tabla)
    sl = Simulacion(libre, ConfigSimulacion()); sl.ejecutar()
    e = entradas_homogeneas(n=161, clase=1, horas=12, tabla=tabla)
    cfg = ConfigSimulacion(contencion_activo=True, contencion_retardo_h=1.0, tasa_linea_m_h=6000.0, intensidad_sostener_kw_m=1e9, intensidad_escape_kw_m=1e12)
    s = Simulacion(e, cfg); reg = s.ejecutar()
    assert reg["celdas_quemadas"] < 0.5 * sl.registro["celdas_quemadas"]
    assert (s.estado == CONTENIDA).sum() > 0 and reg["v2"]["metros_linea"] > 0 and reg["motivo_fin"] == 7
    assert np.isfinite(s.t_cont[s.estado == CONTENIDA]).all() and not np.isfinite(s.t_cont[s.estado != CONTENIDA]).any()
    # sin presupuesto de línea no hay contención y el resultado coincide con el libre
    e0 = entradas_homogeneas(n=161, clase=1, horas=12, tabla=tabla)
    s0 = Simulacion(e0, ConfigSimulacion(contencion_activo=True, tasa_linea_m_h=0.0)); s0.ejecutar()
    assert np.array_equal(np.isfinite(s0.t_arr), np.isfinite(sl.t_arr))


def test_contencion_no_sostiene_frente_intenso(tabla):
    """Con umbral de sostén nulo ninguna celda puede asegurarse: el fuego queda libre."""
    libre = entradas_homogeneas(n=121, clase=1, horas=8, vel=4.0, tabla=tabla)
    sl = Simulacion(libre, ConfigSimulacion()); sl.ejecutar()
    e = entradas_homogeneas(n=121, clase=1, horas=8, vel=4.0, tabla=tabla)
    s = Simulacion(e, ConfigSimulacion(contencion_activo=True, contencion_retardo_h=0.0, tasa_linea_m_h=1e6, intensidad_sostener_kw_m=0.0)); s.ejecutar()
    assert (s.estado == CONTENIDA).sum() == 0 and np.array_equal(np.isfinite(s.t_arr), np.isfinite(sl.t_arr))


def test_reproducibilidad_v2(tabla):
    def correr():
        e = entradas_homogeneas(n=121, clase=3, horas=8, vel=4.0, dir_desde=200.0, tabla=tabla)
        e.barreras = barrera_vertical(121, 70); e.ancho_barrera_m = np.array([0.0, 3.0])
        s = Simulacion(e, ConfigSimulacion(barreras_activo=True, contencion_activo=True, contencion_retardo_h=1.0, tasa_linea_m_h=300.0)); s.ejecutar()
        return s
    a, b = correr(), correr()
    assert np.array_equal(a.t_arr, b.t_arr) and np.array_equal(a.estado, b.estado) and np.array_equal(a.t_cont, b.t_cont)
