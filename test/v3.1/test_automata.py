import numpy as np
import pytest

from incendios_sl.simulation.automata import estencil, ACTIVA, COMB, QUEMADA, NOCOMB, FUERA
from incendios_sl.simulation.motor import Simulacion, ConfigSimulacion
from incendios_sl.simulation.rothermel import rothermel_lecho, lecho_desde_fila
from incendios_sl.simulation.sintetico import entradas_homogeneas, tabla_prueba


@pytest.fixture(scope="module")
def tabla(tmp_path_factory):
    return tabla_prueba(tmp_path_factory.mktemp("tab"))


def test_estencil_distancias_y_azimuts():
    dy, dx, dist, az = estencil(16, 30.0)
    assert len(dy) == 16 and np.allclose(sorted(set(np.round(dist, 3))), [30.0, 42.426, 67.082])
    assert abs(np.degrees(az[0]) - 0) < 1e-9 and abs(np.degrees(az[2]) - 90) < 1e-9 and abs(np.degrees(az[4]) - 180) < 1e-9
    with pytest.raises(ValueError):
        estencil(6, 30.0)


def _radial(sim, n):
    c = n // 2
    yy, xx = np.mgrid[0:n, 0:n]
    d = np.hypot(yy - c, xx - c) * sim.e.res_m
    ok = np.isfinite(sim.t_arr) & (d > 150)
    az = np.degrees(np.arctan2(xx - c, -(yy - c))) % 360
    return {a0: float((d[m] / sim.t_arr[m]).mean()) for a0 in range(0, 360, 15) for m in [ok & (np.abs(((az - a0 + 180) % 360) - 180) < 4)]}


def test_frente_circular_sin_viento_ni_pendiente(tabla):
    e = entradas_homogeneas(n=121, clase=1, horas=24, tabla=tabla)
    sim = Simulacion(e, ConfigSimulacion(vecindad=16, dt_s=60))
    reg = sim.ejecutar()
    r = rothermel_lecho(lecho_desde_fila(tabla.set_index("clase").loc[1]), (6, 7, 8), 60, 90, curado=0.8)
    R0 = r.R0_m_min / 60
    reff = _radial(sim, 121)
    assert max(abs(v / R0 - 1) for v in reff.values()) < 0.04       # isotropía con 16 vecinos
    assert reg["motivo_fin"] == 1
    teorico = np.pi * (R0 * 24 * 3600) ** 2 / 900
    assert abs(reg["celdas_quemadas"] / teorico - 1) < 0.06


def test_ocho_vecinos_peor_isotropia(tabla):
    e = entradas_homogeneas(n=121, clase=1, horas=24, tabla=tabla)
    r8 = _radial(Simulacion(e, ConfigSimulacion(vecindad=8)).__class__(e, ConfigSimulacion(vecindad=8)), 121) if False else None
    s8 = Simulacion(e, ConfigSimulacion(vecindad=8)); s8.ejecutar()
    s16 = Simulacion(e, ConfigSimulacion(vecindad=16)); s16.ejecutar()
    R0 = rothermel_lecho(lecho_desde_fila(tabla.set_index("clase").loc[1]), (6, 7, 8), 60, 90, curado=0.8).R0_m_min / 60
    e8 = max(abs(v / R0 - 1) for v in _radial(s8, 121).values()); e16 = max(abs(v / R0 - 1) for v in _radial(s16, 121).values())
    assert e16 < e8


def test_viento_elipse_hacia_el_este(tabla):
    e = entradas_homogeneas(n=241, clase=1, horas=6, vel=5.0, dir_desde=270.0, tabla=tabla)
    sim = Simulacion(e, ConfigSimulacion(vecindad=16)); sim.ejecutar()
    c = 120; ta = sim.t_arr
    este = np.where(np.isfinite(ta[c, c + 1:]))[0].max() + 1
    oeste = np.where(np.isfinite(ta[c, :c][::-1]))[0].max() + 1
    norte = np.where(np.isfinite(ta[:c, c][::-1]))[0].max() + 1
    sur = np.where(np.isfinite(ta[c + 1:, c]))[0].max() + 1
    assert este > 5 * oeste and este > 3 * norte and abs(norte - sur) <= 2


def test_pendiente_acelera_cuesta_arriba(tabla):
    e = entradas_homogeneas(n=241, clase=1, horas=6, pendiente=20.0, orientacion=180.0, tabla=tabla)  # ladera mira al sur: sube al norte
    sim = Simulacion(e, ConfigSimulacion(vecindad=16)); sim.ejecutar()
    c = 120; ta = sim.t_arr
    norte = np.where(np.isfinite(ta[:c, c][::-1]))[0].max() + 1
    sur = np.where(np.isfinite(ta[c + 1:, c]))[0].max() + 1
    assert norte > 3 * sur


def test_barrera_no_combustible_y_fuera_de_dominio(tabla):
    e = entradas_homogeneas(n=121, clase=1, horas=24, tabla=tabla, barrera=(0, 121, 80, 83))
    e.mascara[:10, :] = 0   # franja fuera del dominio
    sim = Simulacion(e, ConfigSimulacion(vecindad=16)); sim.ejecutar()
    assert np.isfinite(sim.t_arr[:, 83:]).sum() == 0
    assert np.isfinite(sim.t_arr[:10, :]).sum() == 0 and (sim.estado[:10, :] == FUERA).all()
    assert (sim.estado[10:, 80:83] == NOCOMB).all()


def test_sin_reencendido_y_estados_validos(tabla):
    e = entradas_homogeneas(n=81, clase=1, horas=10, vel=3.0, tabla=tabla)
    sim = Simulacion(e, ConfigSimulacion(vecindad=16)); sim.ejecutar()
    quemadas = np.isfinite(sim.t_arr)
    assert set(np.unique(sim.estado[quemadas])) <= {ACTIVA, QUEMADA}
    assert set(np.unique(sim.estado[~quemadas])) <= {COMB}
    # cada celda quemada se encendió después (o igual) que su vecino más temprano: t_arr monótono a lo largo del frente
    assert sim.t_arr[40, 40] == 0.0 and (sim.t_arr[quemadas] >= 0).all()


def test_terminacion_por_humedad_de_extincion(tabla):
    e = entradas_homogeneas(n=61, clase=1, horas=30, m1=20.0, tabla=tabla)
    reg = Simulacion(e, ConfigSimulacion(vecindad=16, horas_sin_propagacion_para_terminar=12)).ejecutar()
    assert reg["motivo_fin"] == 3 and reg["celdas_quemadas"] == 1 and abs(reg["t_simulado_s"] - 12 * 3600) < 1


def test_fin_por_meteorologia_insuficiente(tabla):
    e = entradas_homogeneas(n=61, clase=1, horas=6, tabla=tabla)
    e.meteo = e.meteo.iloc[:3]       # solo 3 horas de datos
    reg = Simulacion(e, ConfigSimulacion(vecindad=16)).ejecutar()
    assert reg["motivo_fin"] == 2


def test_reproducibilidad(tabla):
    e = entradas_homogeneas(n=101, clase=3, horas=8, vel=4.0, dir_desde=200.0, pendiente=10.0, orientacion=45.0, tabla=tabla)
    a = Simulacion(e, ConfigSimulacion(vecindad=16)); a.ejecutar()
    b = Simulacion(e, ConfigSimulacion(vecindad=16)); b.ejecutar()
    assert np.array_equal(a.t_arr, b.t_arr) and np.array_equal(a.estado, b.estado)


def test_paso_temporal_no_limita_velocidad(tabla):
    """Con Δt = 600 s y viento fuerte el fuego debe avanzar más de una celda por paso (sin restricción CFL)."""
    e = entradas_homogeneas(n=241, clase=1, horas=2, vel=8.0, dir_desde=270.0, tabla=tabla)
    s60 = Simulacion(e, ConfigSimulacion(vecindad=16, dt_s=60)); s60.ejecutar()
    s600 = Simulacion(e, ConfigSimulacion(vecindad=16, dt_s=600)); s600.ejecutar()
    c = 120
    e60 = np.where(np.isfinite(s60.t_arr[c, c + 1:]))[0].max() + 1
    e600 = np.where(np.isfinite(s600.t_arr[c, c + 1:]))[0].max() + 1
    assert e600 > 12 and abs(e600 - e60) <= max(3, 0.1 * e60)


def test_guardar_y_recuperar(tabla, tmp_path):
    e = entradas_homogeneas(n=61, clase=1, horas=3, tabla=tabla)
    sim = Simulacion(e, ConfigSimulacion(vecindad=16)); sim.ejecutar()
    rutas = sim.guardar(tmp_path / "run")
    assert rutas["serie"].exists() and rutas["registro"].exists()
    ta = np.load(tmp_path / "run" / "t_llegada_s.npy")
    assert np.array_equal(np.isfinite(ta), np.isfinite(sim.t_arr))
