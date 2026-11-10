import numpy as np
import pytest

from incendios_sl.simulation.rothermel import LechoCombustible, rothermel_lecho, M_A_FT
from incendios_sl.simulation.propagacion import combinar_viento_pendiente, excentricidad, ros_direccional, lb_desde_ueff

GR2 = LechoCombustible([0.1 * 0.2242, 0, 0, 1.0 * 0.2242, 0], [2000 * M_A_FT, 0, 0, 1800 * M_A_FT, 0], 0.3048, 15, 18608, dinamico=True, nombre="GR2")


def test_contraste_con_referencia_sfire_una_clase():
    """Una sola clase muerta: la variante Rothermel 1972 (albini=False) debe reproducir la implementación de
    referencia de firebench (WRF-SFIRE) con error < 0.5 % (misma formulación; calor 17.433 MJ/kg; Mx como fracción)."""
    fb = pytest.importorskip("firebench.ros_models.surface_for_vegetation")
    for (w, d, sav, mx, m, U, s) in [(0.5, 0.3, 2000, 15, 6, 0, 0), (0.5, 0.3, 2000, 15, 6, 3.0, 0), (0.8, 0.6, 1800, 25, 10, 2.0, 15), (1.5, 1.0, 750, 30, 8, 4.0, 25)]:
        ref = fb.Rothermel_SFIRE.rothermel(fgi=w, fueldepthm=d, fueldens=32.0, savr=sav, fuelmce=mx / 100, st=0.0555, se=0.01, ichap=0, wind=U, slope=s, fmc=m)
        r = rothermel_lecho(LechoCombustible([w, 0, 0, 0, 0], [sav * M_A_FT, 0, 0, 0, 0], d, mx, 17433.0), (m, m + 1, m + 2), 90, 120, albini=False)
        R = r.R_ft_min(U * 196.85, np.tan(np.radians(s))) * 0.00508
        assert abs(R / ref - 1) < 0.005, (w, sav, m, U, s, R, ref)


def test_extincion_por_humedad():
    assert rothermel_lecho(GR2, (14.9, 15.9, 16.9), 60, 90, curado=0.8).R0_ft_min > 0
    assert rothermel_lecho(GR2, (15.0, 16, 17), 60, 90, curado=0.8).R0_ft_min == 0
    assert rothermel_lecho(GR2, (25.0, 26, 27), 60, 90, curado=0.8).R0_ft_min == 0


def test_monotonia_humedad_viento_pendiente_curado():
    r6 = rothermel_lecho(GR2, (6, 7, 8), 60, 90, curado=0.8); r10 = rothermel_lecho(GR2, (10, 11, 12), 60, 90, curado=0.8)
    assert r6.R0_ft_min > r10.R0_ft_min > 0
    assert r6.R_ft_min(500, 0) > r6.R_ft_min(100, 0) > r6.R0_ft_min
    assert r6.R_ft_min(0, np.tan(np.radians(30))) > r6.R_ft_min(0, np.tan(np.radians(10))) > r6.R0_ft_min
    assert rothermel_lecho(GR2, (6, 7, 8), 60, 90, curado=0.8).R0_ft_min > rothermel_lecho(GR2, (6, 7, 8), 60, 90, curado=0.3).R0_ft_min
    # curado por defecto (regla estándar por LFMC): 30 % -> totalmente curado == curado=1
    a = rothermel_lecho(GR2, (6, 7, 8), 30, 90).R0_ft_min; b = rothermel_lecho(GR2, (6, 7, 8), 30, 90, curado=1.0).R0_ft_min
    assert abs(a - b) < 1e-9


def test_no_combustible():
    nb = LechoCombustible([0, 0, 0, 0, 0], [0, 0, 0, 0, 0], 0, 0, 0)
    assert rothermel_lecho(nb, (6, 7, 8), 60, 90).R0_ft_min == 0


def test_combinacion_vectorial_y_elipse():
    r = rothermel_lecho(GR2, (6, 7, 8), 60, 90, curado=0.8)
    # solo viento desde el oeste (sopla hacia el este, U>0): theta_max = 90°
    ueff, th, phic = combinar_viento_pendiente(5.0, 0.0, 0.4, 0.0, 0.0, r.C, r.B, r.ratio_E, r.phis_coef)
    assert abs(np.degrees(th) - 90) < 1e-6 and abs(phic / r.phi_w(0.4 * 5 * 196.85) - 1) < 1e-4
    # solo pendiente, cuesta arriba hacia el norte: theta_max = 0 y phi_c == phi_s
    tanp = np.tan(np.radians(20))
    ueff, th, phic = combinar_viento_pendiente(0.0, 0.0, 0.4, tanp, 0.0, r.C, r.B, r.ratio_E, r.phis_coef)
    assert abs(th) < 1e-6 and abs(phic / r.phi_s(tanp) - 1) < 1e-4
    # elipse: cabeza = R, cola = R(1-e)/(1+e), flanco menor que cabeza
    e = excentricidad(ueff)
    assert 0 < e < 1
    R = 1.0
    assert abs(ros_direccional(R, e, 0.0, 0.0) - R) < 1e-12
    assert abs(ros_direccional(R, e, 0.0, np.pi) - R * (1 - e) / (1 + e)) < 1e-12
    assert ros_direccional(R, e, 0.0, np.pi / 2) < R
    # sin viento ni pendiente: e = 0 -> isotrópico
    assert excentricidad(0.0) == 0.0 and lb_desde_ueff(0.0) == 1.0
    assert lb_desde_ueff(1e9) == 8.0
