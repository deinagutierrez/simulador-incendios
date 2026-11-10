"""Tests de la física: Rothermel, humedades, elipse y viento."""

import numpy as np
import pandas as pd
import pytest

from simulador.fuel.sb40 import TablaCombustible, tabla, codigos_conocidos
from simulador.physics.rothermel import rothermel, combinar_viento_pendiente, intensidad_byram, FT_MIN_A_M_MIN
from simulador.physics.humedad import emc_simard, humedad_viva, curado_pasto, ParametrosHumedad, serie_humedad_muerta
from simulador.physics.elipse import relacion_largo_ancho, excentricidad, ros_direccional
from simulador.physics.viento import waf_sin_dosel

T = TablaCombustible()


def _ros(claves, m1=.03, m10=.04, m100=.05, mh=.30, mw=.60, U_mih=5.0, tan_p=0.0, curado=1.0):
    idx = np.array([list(T.clave).index(k) for k in claves]); n = len(idx)
    sal = rothermel(T.w[idx], T.sav[idx], T.profundidad_ft[idx], T.mx_muerto[idx], T.calor_muerto[idx], T.calor_vivo[idx],
                    np.full(n, curado), np.full(n, m1), np.full(n, m10), np.full(n, m100), np.full(n, mh), np.full(n, mw),
                    np.full(n, U_mih * 88.0), np.full(n, tan_p))
    return sal, sal.R0 * (1 + sal.phi_w + sal.phi_s)


def test_tabla_sb40_completa():
    df = tabla()
    assert len(df) == 45 and len(codigos_conocidos()) == 45
    assert set(df.clave[df.codigo >= 100].str[:2]) == {"GR", "GS", "SH", "TU", "TL", "SB"}
    assert (df.loc[df.codigo >= 100, "profundidad_ft"] > 0).all()


def test_rothermel_orden_de_magnitud_scott_burgan():
    """ROS a 5 mi/h de viento a media llama y humedad baja (escenario D1L1 de S&B), en ch/h.
    Valores de referencia: fichas de Scott & Burgan (2005), lectura gráfica (±25 %)."""
    ref = {"GR1": 27, "GR2": 65, "GR4": 130, "SH2": 11, "SH5": 90, "TU1": 5}
    sal, R = _ros(list(ref))
    chh = R * 60 / 66.0
    for k, v in zip(ref, chh):
        assert abs(v - ref[k]) / ref[k] < 0.25, f"{k}: {v:.1f} ch/h vs ref {ref[k]}"


def test_rothermel_monotonias():
    _, r_seco = _ros(["GR2", "SH2"], m1=.03)
    _, r_humedo = _ros(["GR2", "SH2"], m1=.10)
    assert (r_seco > r_humedo).all()
    _, r_calmo = _ros(["GR2", "SH2"], U_mih=0)
    _, r_viento = _ros(["GR2", "SH2"], U_mih=5)
    assert (r_viento > r_calmo).all()
    _, r_plano = _ros(["GR2"], U_mih=0)
    _, r_pend = _ros(["GR2"], U_mih=0, tan_p=np.tan(np.deg2rad(30)))
    assert r_pend[0] > r_plano[0]


def test_extincion_por_humedad():
    sal, R = _ros(["GR2"], m1=.20)   # Mx GR2 = 15 %
    assert sal.extinguido[0] and R[0] == 0


def test_combinacion_vectorial_viento_pendiente():
    sal, _ = _ros(["GR2"], U_mih=5, tan_p=np.tan(np.deg2rad(20)))
    # viento hacia el S (180), pendiente que sube hacia el N (orientación 180 = baja al S) → se oponen
    R, rumbo, U_eff, phi = combinar_viento_pendiente(sal, np.array([180.0]), np.array([180.0]), np.array([False]))
    assert phi[0] < sal.phi_w[0] + sal.phi_s[0]
    # alineados
    R2, rumbo2, _, phi2 = combinar_viento_pendiente(sal, np.array([0.0]), np.array([180.0]), np.array([False]))
    assert abs(phi2[0] - (sal.phi_w[0] + sal.phi_s[0])) < 1e-6 and abs(rumbo2[0]) < 1e-6


def test_byram():
    sal, R = _ros(["GR4"])
    IB, L = intensidad_byram(sal.IR, R, sal.tau_min)
    assert 500 < IB[0] < 20000 and 0.5 < L[0] < 6


def test_emc_simard():
    e = emc_simard(np.array([30.0, 20.0, 10.0]), np.array([15.0, 50.0, 90.0]))
    assert e[0] < e[1] < e[2] and 0.015 <= e[0] < 0.06 and 0.15 < e[2] < 0.30
    # NFDRS (°F) por defecto: 30 °C / 20 % = 4,158 % (V.4 daba 2,67 %; docs/v4.0/15, P2)
    assert abs(emc_simard(30.0, 20.0) - 0.04158) < 2e-5
    assert abs(emc_simard(30.0, 20.0, "v4_original", 2.0) - 0.02674) < 2e-5


def test_serie_humedad_metodos():
    ts = pd.date_range("2024-01-01T00:00:00-03:00", periods=48, freq="h")
    df = pd.DataFrame({"timestamp": ts, "temp_c": 28.0, "hr_pct": 25.0, "viento_kmh": 10.0, "precip_mm": 0.0})
    df.loc[20, "precip_mm"] = 6.0
    ff = serie_humedad_muerta(df, ParametrosHumedad(metodo_muerto="ffmc_vanwagner"))
    assert np.allclose(ff.m10 - ff.m1, 0.01) and np.allclose(ff.m100 - ff.m1, 0.02)
    assert ff.m1[21] > ff.m1[19] and 0.02 < ff.m1.iloc[-1] < 0.15
    fi = serie_humedad_muerta(df, ParametrosHumedad(metodo_muerto="fija", fija_m1=0.05, fija_m10=6, fija_m100=0.07))
    assert (fi.m1 == 0.05).all() and (fi.m10 == 0.06).all() and (fi.m100 == 0.07).all()
    rt = serie_humedad_muerta(df, ParametrosHumedad(fija_m100=0.12))       # pisa solo el 100 h
    assert (rt.m100 == 0.12).all() and rt.m1.std() > 0
    assert rt.lluvia_24h_mm[20] == 6.0 and rt.lluvia_24h_mm[43] == 6.0 and rt.lluvia_24h_mm[44] == 0.0
    with pytest.raises(ValueError):
        ParametrosHumedad(metodo_muerto="fija", fija_m1=0.05)
    with pytest.raises(ValueError):
        ParametrosHumedad(emc="celsius")


def test_subclase_sigma_menor_16_y_codigos_desconocidos():
    from simulador.physics.rothermel import _grupo_tamano
    assert list(_grupo_tamano(np.array([2000.0, 109.0, 30.0, 10.0, 0.0]))) == [0, 2, 4, 5, -1]
    with pytest.warns(UserWarning, match="desconocidos"):
        idx = T.mapa_indices(np.array([[102, 777], [-9999, 102]], "int16"), -9999)
    assert idx[0, 1] == -1 and idx[1, 0] == -1 and idx[0, 0] >= 0


def test_serie_humedad_muerta_lluvia():
    ts = pd.date_range("2024-01-01T00:00:00-03:00", periods=30, freq="h")
    df = pd.DataFrame({"timestamp": ts, "temp_c": 25.0, "hr_pct": 30.0, "precip_mm": 0.0})
    df.loc[10, "precip_mm"] = 5.0
    h = serie_humedad_muerta(df, ParametrosHumedad())
    assert h.m1[10] > h.m1[9] and h.m1[20] < h.m1[10]          # sube con la lluvia y vuelve a secarse
    assert h.m100.iloc[-1] > h.m1.iloc[-1]                      # el 100 h retiene más


def test_humedad_viva_y_curado():
    p = ParametrosHumedad()
    assert humedad_viva(np.array([-0.5]), p)[0] == p.viva_min / 100
    assert humedad_viva(np.array([0.9]), p)[0] == p.viva_max / 100
    c = curado_pasto(np.array([0.2, 0.4]), np.array([0.4, 0.4]), p)
    assert c[0] > c[1] and c[1] == p.curado_min


def test_elipse():
    lb = relacion_largo_ancho(np.array([0.0, 5.0, 40.0]))
    assert abs(lb[0] - 1.0) < 1e-6 and 2.5 < lb[1] < 4.5 and lb[2] == 8.0
    e = excentricidad(lb)
    R = ros_direccional(np.array([10.0]), e[1:2], np.array([0.0, 90.0, 180.0]))
    assert R[0] == 10.0 and R[0] > R[1] > R[2] > 0


def test_waf():
    w = waf_sin_dosel(np.array([0.4, 1.0, 6.0]))
    assert (np.diff(w) > 0).all() and 0.2 < w[0] < 0.6
