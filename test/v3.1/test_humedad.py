import numpy as np
import pandas as pd

from incendios_sl.fuels.humedad import ffmc_a_humedad, humedad_a_ffmc, ffmc_horario, ffmc_horario_paso, serie_humedad, lfmc_desde_ndmi


def test_conversion_ffmc_humedad_inversa():
    for f in [0, 50, 85, 95, 101]:
        assert abs(humedad_a_ffmc(ffmc_a_humedad(f)) - f) < 1e-9


def test_equilibrio_secado_y_humectacion():
    # condiciones constantes secas: la humedad converge al equilibrio de secado Ed
    temp, rh, ws = 30.0, 20.0, 15.0
    Ed = 0.942 * rh ** 0.679 + 11 * np.exp((rh - 100) / 10) + 0.18 * (21.1 - temp) * (1 - np.exp(-0.115 * rh))
    f = ffmc_horario([temp] * 200, [rh] * 200, [ws] * 200, [0.0] * 200, ffmc_inicial=60)
    assert abs(ffmc_a_humedad(f[-1]) - Ed) < 0.05
    # condiciones húmedas: converge al equilibrio de humectación Ew (partiendo seco)
    temp, rh = 10.0, 95.0
    Ew = 0.618 * rh ** 0.753 + 10 * np.exp((rh - 100) / 10) + 0.18 * (21.1 - temp) * (1 - np.exp(-0.115 * rh))
    f = ffmc_horario([temp] * 300, [rh] * 300, [ws] * 300, [0.0] * 300, ffmc_inicial=95)
    assert abs(ffmc_a_humedad(f[-1]) - Ew) < 0.05


def test_lluvia_aumenta_humedad():
    f0 = ffmc_horario_paso(20, 50, 10, 0.0, 90)
    f1 = ffmc_horario_paso(20, 50, 10, 5.0, 90)
    assert ffmc_a_humedad(f1) > ffmc_a_humedad(f0) + 5


def test_faltantes_no_se_rellenan():
    f = ffmc_horario([20, np.nan, 20], [50, 50, 50], [10, 10, 10], [0, 0, 0])
    assert np.isnan(f[1]) and np.isfinite(f[0]) and np.isfinite(f[2])


def test_serie_humedad_columnas():
    t = pd.date_range("2024-09-18", periods=48, freq="h", tz="UTC")
    dom = pd.DataFrame({"time_utc": t, "temperature_2m": 25.0, "relative_humidity_2m": 25.0, "wind_speed_10m": 5.0, "precipitation": 0.0})
    h = serie_humedad(dom, {"muerto_10h_offset": 1.0, "muerto_100h_offset": 2.0})
    assert list(h.columns)[:6] == ["time_utc", "ffmc", "m_1h_pct", "m_10h_pct", "m_100h_pct", "lluvia_24h_mm"]
    assert {"m_1h_pct_rt", "m_10h_pct_rt", "m_100h_pct_rt", "emc_pct"} <= set(h.columns)
    assert (h.m_10h_pct - h.m_1h_pct).round(6).eq(1.0).all()
    assert 2 < h.m_1h_pct.iloc[-1] < 12


def test_emc_simard_valores_y_continuidad():
    from incendios_sl.fuels.humedad import emc_simard
    # 25 °C y 25 % HR: equilibrio ≈ 5 %; 25 °C y 90 %: ≈ 20 %; monótono creciente con la HR
    assert 4.0 < float(emc_simard(25.0, 25.0)) < 6.5 and 17.0 < float(emc_simard(25.0, 90.0)) < 24.0
    e = emc_simard(np.full(100, 25.0), np.linspace(1, 99, 100))
    assert np.all(np.diff(e) > -0.3)


def test_retardo_seca_en_horas_y_ffmc_en_dias():
    """Tras lluvia, el combustible de 1 h del modelo de retardo vuelve cerca del equilibrio en ~3 h; el FFMC tarda mucho más
    (es la limitación observada en Las Chacras 2023, docs/11)."""
    from incendios_sl.fuels.humedad import humedad_retardo, emc_simard
    n = 30; temp = [28.0] * n; rh = [21.0] * n; pr = [0.0] * n; pr[2] = 3.6
    m1 = humedad_retardo(temp, rh, pr, tau_h=1.0)
    emc = float(emc_simard(28.0, 21.0))
    # la hora de lluvia satura (35 %) y en esa misma hora relaja una constante de tiempo: queda ~16 %; a las 3 h está en el equilibrio
    assert m1[2] > 12.0 and abs(m1[5] - emc) < 1.5 and abs(m1[10] - emc) < 0.1
    m10 = humedad_retardo(temp, rh, pr, tau_h=10.0, factor_lluvia=0.5, m_max=40.0)
    assert m10[5] > m1[5] + 3 and m10[25] < m10[5]
    f = ffmc_horario(temp, rh, [15.0] * n, pr, ffmc_inicial=humedad_a_ffmc(emc))
    assert ffmc_a_humedad(f[5]) > m1[5] + 5          # el FFMC sigue húmedo 3 h después de la lluvia


def test_retardo_faltantes_y_tope():
    from incendios_sl.fuels.humedad import humedad_retardo
    m = humedad_retardo([20, np.nan, 20], [50, 50, 50], [0, 0, 0], tau_h=1.0)
    assert np.isnan(m[1]) and np.isfinite(m[0]) and np.isfinite(m[2])
    m = humedad_retardo([15.0] * 5, [95.0] * 5, [0, 30.0, 30.0, 0, 0], tau_h=100.0, m_max=45.0)
    assert m.max() <= 45.0 + 1e-9


def test_lfmc_desde_ndmi():
    cfg = {"ndmi_min": -0.1, "ndmi_max": 0.4, "lfmc_min": 30, "lfmc_max": 120}
    out = lfmc_desde_ndmi(np.array([-0.5, -0.1, 0.15, 0.4, 0.9, np.nan]), cfg)
    assert np.allclose(out[:5], [30, 30, 75, 120, 120]) and np.isnan(out[5])
