"""Pruebas del despacho local del SNMF (docs/13): tasa escalonada con la superficie, medios aéreos automáticos, tiempo
de arribo por la red vial y lectura de la configuración."""
import numpy as np
import pandas as pd
import pytest

from incendios_sl.data.arribo import friccion_h, tiempos_desde
from incendios_sl.simulation.entradas import config_v2, fusionar, region_despacho
from incendios_sl.simulation.motor import Simulacion, ConfigSimulacion
from incendios_sl.simulation.sintetico import entradas_homogeneas, tabla_prueba


@pytest.fixture(scope="module")
def tabla(tmp_path_factory):
    return tabla_prueba(tmp_path_factory.mktemp("tab"))


def test_tasa_escalonada_con_la_superficie(tabla):
    e = entradas_homogeneas(n=41, horas=1, tabla=tabla)
    s = Simulacion(e, ConfigSimulacion(despacho_modo="snmf", despacho_a=20.0, despacho_b=0.5, despacho_kappa=2.0, despacho_tasa_max_m_h=1000.0))
    assert s._tasa_hora() == pytest.approx(40.0)                      # sin superficie quemada se usa A = 1 ha
    s.t_arr[:10, :10] = 0.0                                          # 100 celdas de 30 m = 9 ha
    assert s._tasa_hora() == pytest.approx(2.0 * 20.0 * 9.0 ** 0.5)
    s.t_arr[...] = 0.0                                               # 41² celdas = 151 ha -> 492 m/h; con tope 1.000 no satura
    assert s._tasa_hora() == pytest.approx(2.0 * 20.0 * (41 * 41 * 0.09) ** 0.5)
    s.c.despacho_tasa_max_m_h = 100.0
    assert s._tasa_hora() == 100.0
    f = Simulacion(e, ConfigSimulacion(tasa_linea_m_h=777.0))
    assert f._tasa_hora() == 777.0                                   # modo fijo


def test_kappa_decrece_con_la_superficie(tabla):
    e = entradas_homogeneas(n=41, horas=1, tabla=tabla)
    s = Simulacion(e, ConfigSimulacion(despacho_modo="snmf", despacho_kappa=10.0, despacho_kappa_quiebre_ha=1000.0, despacho_kappa_gamma=0.5, despacho_kappa_min=1.0))
    assert s._kappa(10.0) == 10.0 and s._kappa(1000.0) == 10.0
    assert s._kappa(4000.0) == pytest.approx(5.0)                    # 10 · 4^-0,5
    assert s._kappa(1e7) == 1.0                                      # piso
    assert Simulacion(e, ConfigSimulacion(despacho_kappa=10.0))._kappa(1e7) == 10.0   # sin quiebre: constante
    assert Simulacion(e, ConfigSimulacion(despacho_kappa=0.5, despacho_kappa_quiebre_ha=1.0, despacho_kappa_gamma=1.0))._kappa(100.0) == 0.5  # el piso no sube κ


def test_despacho_snmf_contiene_y_registra_la_tasa(tabla):
    e = entradas_homogeneas(n=161, clase=1, horas=12, tabla=tabla)
    cfg = ConfigSimulacion(contencion_activo=True, contencion_retardo_h=1.0, despacho_modo="snmf", despacho_a=300.0, despacho_b=0.4,
                           intensidad_sostener_kw_m=1e9, intensidad_escape_kw_m=1e12)
    s = Simulacion(e, cfg); reg = s.ejecutar()
    serie = pd.DataFrame(s.serie)
    tasas = serie.tasa_linea_m_h.dropna()
    assert len(tasas) > 0 and reg["v2"]["despacho_modo"] == "snmf" and (s.estado == 4).sum() > 0
    # la tasa sigue a la superficie quemada al momento de construir la línea
    assert tasas.iloc[0] == pytest.approx(300.0 * max(serie.ha_quemadas.iloc[0], 1.0) ** 0.4, rel=0.15)


def test_inicio_exacto_del_combate(tabla):
    """Con `contencion_inicio_exacto` la primera línea se construye en el minuto de llegada con la producción prorrateada;
    sin él, en la hora en punto siguiente."""
    def correr(exacto):
        e = entradas_homogeneas(n=121, clase=1, horas=6, tabla=tabla)
        cfg = ConfigSimulacion(contencion_activo=True, contencion_inicio_s=3.25 * 3600, tasa_linea_m_h=300.0, contencion_inicio_exacto=exacto,
                               intensidad_sostener_kw_m=1e9, intensidad_escape_kw_m=1e12)
        s = Simulacion(e, cfg); s.ejecutar()
        return s
    a, b = correr(True), correr(False)
    ta = a.t_cont[np.isfinite(a.t_cont)]; tb = b.t_cont[np.isfinite(b.t_cont)]
    assert ta.min() == pytest.approx(3.25 * 3600) and tb.min() == pytest.approx(4 * 3600)
    assert (ta == ta.min()).sum() == int(0.75 * 300 // 30)           # 45 min de producción: 225 m = 7 celdas
    assert (tb == tb.min()).sum() == int(300 // 30)                  # hora completa: 10 celdas
    # con la llegada en una hora en punto los dos modos coinciden
    def en_punto(exacto):
        e = entradas_homogeneas(n=121, clase=1, horas=4, tabla=tabla)
        s = Simulacion(e, ConfigSimulacion(contencion_activo=True, contencion_retardo_h=2.0, tasa_linea_m_h=1200.0, contencion_inicio_exacto=exacto)); s.ejecutar()
        return s
    x, y = en_punto(True), en_punto(False)
    assert np.array_equal(x.t_arr, y.t_arr) and np.array_equal(x.t_cont, y.t_cont)
    # llegada fraccionaria (como la del retardo vial): se redondea al minuto siguiente y la simulación llega al final
    e = entradas_homogeneas(n=121, clase=1, horas=4, tabla=tabla)
    s = Simulacion(e, ConfigSimulacion(contencion_activo=True, contencion_inicio_s=8741.5457, tasa_linea_m_h=300.0, contencion_inicio_exacto=True))
    reg = s.ejecutar()
    assert reg["motivo_fin"] != 4 and reg["pasos"] < 1000 and reg["t_simulado_s"] == pytest.approx(4 * 3600)
    assert s.t_cont[np.isfinite(s.t_cont)].min() == pytest.approx(8760.0)


def test_aereo_automatico_sorteo_demora_y_horario(tabla):
    e = entradas_homogeneas(n=41, horas=1, tabla=tabla)               # inicio 2024-01-01 00 UTC
    nunca = Simulacion(e, ConfigSimulacion(aereo_auto=True, aereo_prob_clase=(0, 0, 0, 0, 0)))
    nunca.t_arr[...] = 0.0; nunca._sortear_aereo()
    assert nunca._aereo_desde_s is None and nunca._umbral_sostener() == nunca.c.intensidad_sostener_kw_m
    seguro = Simulacion(e, ConfigSimulacion(aereo_auto=True, aereo_prob_clase=(1, 1, 1, 1, 1), aereo_demora_h=24.0, aereo_horas_vuelo_utc=(11, 22)))
    seguro._sortear_aereo()
    assert seguro._aereo_desde_s == 24 * 3600.0 and seguro._aereo_clase_sorteo == 0
    for h, activo in ((5, False), (30, False), (36, True), (47, False)):   # antes de la demora; noche; día; noche
        seguro.t = h * 3600.0
        assert seguro._aereo_activo() is activo
        assert seguro._umbral_sostener() == (seguro.c.intensidad_sostener_aereo_kw_m if activo else seguro.c.intensidad_sostener_kw_m)
    # condicional: sólo la clase final >10.000 ha tiene P = 1 -> se dispara al entrar en ella, no antes
    c = Simulacion(e, ConfigSimulacion(aereo_auto=True, aereo_prob_clase=(0, 0, 0, 0, 1), aereo_umbrales_ha=(0.01, 0.02, 0.03, 100.0)))
    c.t_arr[:5, :5] = 0.0; c._sortear_aereo()
    assert c._aereo_desde_s is None and c._aereo_clase == 3
    c.t_arr[...] = 0.0; c._sortear_aereo()
    assert c._aereo_clase_sorteo == 4


def test_aereo_automatico_reproduce_probabilidades():
    """Con probabilidades condicionales por clase, P(aéreo antes de terminar en la clase k) = prob_clase[k]."""
    prob = (0.014, 0.103, 0.148, 0.259, 0.40)
    hits = np.zeros(5)
    n = 4000
    for semilla in range(n):
        disparo = None
        for k in range(5):
            Pa = prob[k - 1] if k else 0.0
            if np.random.default_rng([semilla, 7, k]).random() < (prob[k] - Pa) / (1 - Pa):
                disparo = k; break
        for kf in range(5):
            hits[kf] += disparo is not None and disparo <= kf
    assert np.allclose(hits / n, prob, atol=0.025)


def test_tiempo_de_viaje_por_friccion():
    v = np.full((50, 200), 3.0); v[25, :] = 60.0                    # una ruta recta a 60 km/h, el resto a pie
    T = tiempos_desde(friccion_h(v, 100.0), (25, 0), max_h=8.0)
    assert T[25, 100] == pytest.approx(100 * 0.1 / 60.0, rel=1e-6)  # 10 km por la ruta
    # + 1 km a campo traviesa; el MCP promedia el costo de las dos celdas de cada paso (medio paso aún a velocidad de ruta)
    assert T[35, 100] == pytest.approx(T[25, 100] + 9.5 * 0.1 / 3.0 + 0.5 * 0.1 / 60.0, rel=1e-6)
    assert not np.isfinite(tiempos_desde(friccion_h(v, 100.0), (0, 0), max_h=0.5)[49, 199])


def test_configuracion_despacho_y_ficha():
    mod = {"contencion": {"activo": True, "despacho": {"modo": "snmf", "kappa": 3.0, "regiones": {"llanura_sur": {"a": 29.6, "b": 0.38, "departamentos": ["GOBERNADOR DUPUY"]},
                                                                                              "serrano": {"a": 17.3, "b": 0.36}}, "region_defecto": "serrano"},
                           "aereo_auto": {"activo": True}}}
    t0 = pd.Timestamp("2024-09-02T16:00Z")
    assert region_despacho(mod["contencion"]["despacho"], "Gobernador Dupuy") == "llanura_sur"
    assert region_despacho(mod["contencion"]["despacho"], "CHACABUCO") == "serrano" and region_despacho(mod["contencion"]["despacho"], None) == "serrano"
    v = config_v2(mod, {}, t0, region="llanura_sur")
    assert v["despacho_modo"] == "snmf" and v["despacho_kappa"] == 3.0 and v["despacho_a"] == 29.6 and v["aereo_auto"] is True
    # la ficha con medios aéreos observados (aunque sea una lista vacía) desactiva el sorteo, salvo en modo pronóstico
    ev = {"combate": {"aereo": [["2024-09-03T11:00Z", "2024-09-03T22:00Z"]]}}
    v = config_v2(mod, ev, t0, region="serrano")
    assert v["aereo_auto"] is False and v["aereo_intervalos_s"] == [(19 * 3600.0, 30 * 3600.0)]
    assert config_v2(mod, {"combate": {"aereo": []}}, t0)["aereo_auto"] is False
    v = config_v2(fusionar(mod, {"contencion": {"usar_ficha": False}}), ev, t0)
    assert v["aereo_auto"] is True and v["aereo_intervalos_s"] == []
    assert fusionar({"a": {"b": 1, "c": 2}}, {"a": {"c": 3}}) == {"a": {"b": 1, "c": 3}}
