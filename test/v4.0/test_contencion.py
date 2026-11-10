"""Contención por combate y despacho (v3.0 docs/10 y 13) sobre escenarios sintéticos de SIM."""

import numpy as np
import pandas as pd
import pytest

from simulador.ca.contencion import Contencion, u01, kappa, tasa_snmf, elegir_linea, MOTIVOS
from simulador.ca.automata import Automata
from simulador.outputs import geo
from simulador.sintetico import capas_sinteticas, meteo_constante, config_sintetica, simular_sintetico

T0 = "2024-01-01T12:00:00-03:00"
SIN_PARADA = {"horas_sin_avance": None, "contenido": False}


@pytest.fixture(scope="module")
def escenario():
    return capas_sinteticas(121, codigo=102), meteo_constante(T0, horas=10, viento_kmh=10.0, viento_dir_deg=270.0)


def _correr(escenario, cont=None, parada=None, horas=6.0, **param):
    capas, met = escenario
    p = {"contencion": dict({"activo": cont is not None}, **(cont or {})), "parada": parada or SIN_PARADA}
    p.update(param)
    cfg = config_sintetica(parametros=p)
    return simular_sintetico(capas, met, cfg, horas, T0, fila=60, col=30)


def _base_cruda(escenario, horas=6.0):
    """Bucle del autómata sin la capa de corridas (referencia anterior a la contención)."""
    capas, met = escenario
    cfg = config_sintetica()
    au = Automata(capas, met, cfg)
    t0 = pd.Timestamp(T0)
    au.preparar(t0, t0 + pd.Timedelta(hours=horas))
    au.encender(60, 30, t0, "c")
    for _ in range(int(round(horas * 60 / cfg["dt_min"]))):
        au.paso_tiempo()
    return au


def _iguales(a, b, estado=True):
    np.testing.assert_array_equal(np.isnan(a.t_llegada), np.isnan(b.t_llegada))
    np.testing.assert_array_equal(a.t_llegada[np.isfinite(a.t_llegada)], b.t_llegada[np.isfinite(b.t_llegada)])
    if estado:
        np.testing.assert_array_equal(a.estado, b.estado)


@pytest.fixture(scope="module")
def base(escenario):
    return _correr(escenario)


# ------------------------------------------------------------------------------------------- equivalencias
def test_apagada_es_identica_a_la_base(escenario, base):
    au, ind = base
    _iguales(au, _base_cruda(escenario))
    assert au.contencion is None and all("contencion" not in d for d in ind)
    assert au.motivo_fin == "horizonte" and len(ind) == 7


def test_tasa_cero_es_libre(escenario, base):
    au, _ = _correr(escenario, {"inicio_min": 0, "tasa_linea_m_h": 0.0})
    _iguales(au, base[0])
    assert au.contencion.contenida.sum() == 0 and au.contencion.metros == 0


def test_umbral_cero_es_libre(escenario, base):
    au, _ = _correr(escenario, {"inicio_min": 0, "tasa_linea_m_h": 5000.0, "intensidad_sostener_kw_m": 0.0,
                                "intensidad_sostener_aereo_kw_m": 0.0})
    _iguales(au, base[0])
    assert au.contencion.contenida.sum() == 0


# ------------------------------------------------------------------------------------------- contención
def test_reduce_area_y_marca_celdas(escenario, base):
    # con la intensidad v3 (por defecto) la línea persigue los flancos (I lateral) antes que la cabeza: a 1000 m/h la
    # cabeza se escapa (0,59 de la base); a 1500 m/h se contiene. Con `avance` (v4.0 anterior) bastaban 1000 m/h.
    au, ind = _correr(escenario, {"inicio_min": 30, "tasa_linea_m_h": 1500.0})
    c = au.contencion
    assert au.area_quemada_ha() < 0.5 * base[0].area_quemada_ha()
    av, _ = _correr(escenario, {"inicio_min": 30, "tasa_linea_m_h": 1000.0, "intensidad": "avance"})
    assert av.area_quemada_ha() < 0.5 * base[0].area_quemada_ha() and av.contencion.intensidad == "avance"
    n = int(c.contenida.sum())
    assert n > 0 and np.isfinite(c.t_contencion).sum() == n
    assert np.nanmin(c.t_contencion) >= 30.0
    assert c.metros == pytest.approx(c.celdas * 30.0)
    assert c.metros <= 1500.0 * (6 * 60 - 30) / 60 + 1e-6            # presupuesto: tasa × horas de combate
    assert (au.estado[c.contenida] >= 2).all()                         # solo se contienen celdas del incendio
    bloque = ind[-1]["contencion"]
    assert set(bloque) >= {"celdas_contenidas", "metros_linea_hora", "linea_km", "escapes_hora", "tasa_linea_m_h", "aereo_activo", "inicio_min"}
    assert bloque["linea_km"] == pytest.approx(c.metros / 1000, abs=1e-3)
    assert sum(d["contencion"]["metros_linea_hora"] for d in ind) == pytest.approx(c.metros)
    assert ind[0]["contencion"]["combate_iniciado"] is False


def test_inicio_por_retardo(escenario):
    au, ind = _correr(escenario, {"inicio_min": None, "retardo_h": 2.0, "tasa_linea_m_h": 1000.0}, horas=3.0)
    c = au.contencion
    assert c.inicio == 120.0 and np.nanmin(c.t_contencion) >= 120.0
    assert [d["contencion"]["metros_linea_hora"] for d in ind[:3]] == [0.0, 0.0, 0.0]


def test_linea_contigua_y_menor_llama(escenario, base):
    from scipy import ndimage
    au, _ = _correr(escenario, {"inicio_min": 30, "tasa_linea_m_h": 600.0, "seleccion": "contigua"})
    _, n_comp = ndimage.label(au.contencion.contenida, structure=np.ones((3, 3), int))
    assert n_comp <= 3                                  # la línea crece desde pocos anclajes
    # menor_llama a 600 m/h solo contiene cola y flancos (I ≤ 89 kW/m con v3) y la cabeza rellena el mismo conjunto
    au2, _ = _correr(escenario, {"inicio_min": 30, "tasa_linea_m_h": 1000.0, "seleccion": "menor_llama"})
    assert au2.contencion.contenida.sum() > 0 and au2.area_quemada_ha() < base[0].area_quemada_ha()


def test_elegir_linea_flancos_y_cabeza():
    # cinco candidatas en fila; la línea existente toca la del extremo izquierdo
    f = np.zeros(5, int) + 5; c = np.arange(5) + 5; I = np.array([5.0, 1.0, 9.0, 0.5, 3.0])
    linea = np.zeros((20, 20), bool); linea[5, 4] = True
    assert elegir_linea(f, c, I, 3, linea, "flancos").tolist() == [0, 1, 2]       # crece por contigüidad
    sin = np.zeros((20, 20), bool)
    # anclaje en la menor I (3); sus contiguas son 2 (I = 9) y 4 (I = 3): flancos toma la menor, cabeza la mayor
    assert elegir_linea(f, c, I, 2, sin, "flancos").tolist() == [3, 4]
    assert elegir_linea(f, c, I, 2, sin, "cabeza").tolist() == [3, 2]
    assert elegir_linea(f, c, I, 0, sin).size == 0 and elegir_linea(f, c, I, 99, sin).size == 5


def test_combinable_con_l03(escenario):
    au, _ = _correr(escenario, {"inicio_min": 30, "tasa_linea_m_h": 400.0},
                    supresion={"activo": True, "llegadas_min": [60.0], "produccion_linea_m_h": 300.0, "llama_max_m": 2.4})
    assert au.supresion.celdas > 0 and au.contencion.contenida.sum() > 0
    assert not (au.supresion.contenida & au.contencion.contenida).any()


def test_reproducible_con_semilla(escenario):
    cont = {"inicio_min": 30, "tasa_linea_m_h": 800.0, "intensidad_escape_kw_m": 50.0, "p_escape_hora": 0.5,
            "aereo_auto": {"activo": True, "umbrales_ha": [1, 5], "prob_clase": [0.5, 0.5, 0.5], "demora_h": 1, "horas_vuelo_utc": [0, 24]}}
    a, _ = _correr(escenario, cont)
    b, _ = _correr(escenario, cont)
    _iguales(a, b)
    np.testing.assert_array_equal(a.contencion.contenida, b.contencion.contenida)
    np.testing.assert_array_equal(np.nan_to_num(a.contencion.t_contencion, nan=-1), np.nan_to_num(b.contencion.t_contencion, nan=-1))
    assert a.contencion.escapes == b.contencion.escapes
    # otro miembro de ensemble: semilla de contención distinta, estado propio
    capas, met = escenario
    cfg = config_sintetica(parametros={"contencion": dict(cont, activo=True), "parada": SIN_PARADA})
    m1, _ = simular_sintetico(capas, met, cfg, 6.0, T0, fila=60, col=30, miembro=1)
    assert m1.contencion.semilla == a.contencion.semilla + 1 and m1.contencion is not a.contencion


# ------------------------------------------------------------------------------------------- despacho
def test_tasa_snmf_y_kappa():
    s = {"a": 17.3, "b": 0.36, "kappa": 10.0, "tasa_max_m_h": 20000.0, "kappa_quiebre_ha": 3000.0, "kappa_gamma": 0.62, "kappa_min": 1.0}
    assert tasa_snmf(0.2, s) == pytest.approx(10.0 * 17.3)                     # A mínima de 1 ha
    assert tasa_snmf(100.0, s) == pytest.approx(10.0 * 17.3 * 100.0 ** 0.36)
    assert tasa_snmf(1e7, dict(s, kappa_gamma=0.0)) == 20000.0                  # tope
    assert kappa(3000.0, s) == 10.0 and kappa(6000.0, s) == pytest.approx(10.0 * 2.0 ** -0.62)
    assert kappa(1e9, s) == 1.0                                                  # piso min(κ_min, κ)
    assert kappa(1e9, dict(s, kappa=0.5)) == 0.5
    ks = [kappa(A, s) for A in (1e3, 5e3, 1e4, 5e4)]
    assert all(x >= y for x, y in zip(ks, ks[1:]))


def test_despacho_snmf_en_corrida(escenario):
    s = {"a": 17.3, "b": 0.36, "kappa": 1.0, "tasa_max_m_h": 20000.0, "kappa_quiebre_ha": 3000.0, "kappa_gamma": 0.62, "kappa_min": 1.0}
    au, ind = _correr(escenario, {"inicio_min": 30, "despacho": "snmf", "snmf": s})
    for d in ind[1:]:
        A = d["estado_celdas"]["afectada"] * 0.09
        assert d["contencion"]["tasa_linea_m_h"] == pytest.approx(tasa_snmf(A, s), abs=0.1)
    assert au.contencion.contenida.sum() > 0


def test_sorteo_aereo():
    t0 = pd.Timestamp(T0)
    base = {"activo": True, "aereo_auto": {"activo": True, "umbrales_ha": [10, 100, 1000, 10000],
                                          "prob_clase": [0.014, 0.103, 0.148, 0.259, 0.40], "demora_h": 24, "horas_vuelo_utc": [11, 22]}}
    # condicionalidad: P(aéreo | superficie en la clase k) = P_k
    for A, P in ((500.0, 0.148), (5e4, 0.40)):
        n = 0
        for s in range(3000):
            c = Contencion(dict(base, semilla=s), 30.0, t0)
            c.sortear_aereo(A, 60.0)
            n += c.aereo_desde is not None
        assert abs(n / 3000 - P) < 0.025
    # demora y horario de vuelo (t0 = 15 UTC)
    c = Contencion(dict(base, aereo_auto=dict(base["aereo_auto"], prob_clase=[1, 1, 1, 1, 1])), 30.0, t0)
    c.sortear_aereo(1.0, 60.0)
    assert c.aereo_desde == 24 * 60 and c.aereo_clase_sorteo == 0
    assert not c.aereo_activo(23 * 60) and c.aereo_activo(24 * 60)            # 15 UTC: de día
    assert not c.aereo_activo(24 * 60 + 8 * 60)                                # 23 UTC: de noche
    assert c.umbral_sostener(24 * 60) == c.I_sost_aereo and c.umbral_sostener(60) == c.I_sost
    # intervalos de la ficha (ISO con huso)
    c = Contencion({"activo": True, "aereo_intervalos": [["2024-01-01T13:00:00-03:00", "2024-01-01T14:00:00-03:00"]]}, 30.0, t0)
    assert c.aereo_activo(90.0) and not c.aereo_activo(30.0) and not c.aereo_activo(150.0)


# ------------------------------------------------------------------------------------------- escapes
def test_u01_igual_a_v3_y_uniforme():
    M = 2 ** 64
    def ref(s, i, j, k, h):
        x = (s * 0x9E3779B97F4A7C15) % M
        x ^= ((i + 1) * 0xBF58476D1CE4E5B9) % M; x ^= ((j + 1) * 0x94D049BB133111EB) % M
        x ^= ((k + 1) * 0xD6E8FEB86659FD93) % M; x ^= ((h + 1) * 0xA0761D6478BD642F) % M
        x ^= x >> 30; x = (x * 0xBF58476D1CE4E5B9) % M
        x ^= x >> 27; x = (x * 0x94D049BB133111EB) % M
        x ^= x >> 31
        return (x >> 11) / 9007199254740992.0
    i = np.arange(50); u = u01(20261015, i, 7, 99, 3)
    assert np.allclose(u, [ref(20261015, int(a), 7, 99, 3) for a in i], rtol=0, atol=0)
    v = u01(1, np.arange(20000), 3, 99, 0)
    assert abs(v.mean() - 0.5) < 0.01 and v.min() >= 0 and v.max() < 1


def test_escapes(escenario):
    cont = {"inicio_min": 30, "tasa_linea_m_h": 1000.0}
    sin, _ = _correr(escenario, dict(cont, intensidad_escape_kw_m=0.0, p_escape_hora=0.0))
    con, ind = _correr(escenario, dict(cont, intensidad_escape_kw_m=0.0, p_escape_hora=1.0))
    alto, _ = _correr(escenario, dict(cont, intensidad_escape_kw_m=1e6, p_escape_hora=1.0))
    assert sin.contencion.escapes == 0 and alto.contencion.escapes == 0
    _iguales(sin, alto)
    assert con.contencion.escapes > 0 and con.area_quemada_ha() > sin.area_quemada_ha()
    assert sum(d["contencion"]["escapes_hora"] for d in ind) == con.contencion.escapes
    # las celdas que escaparon dejan de figurar como contenidas
    assert np.isfinite(con.contencion.t_contencion).sum() == con.contencion.contenida.sum()


# ------------------------------------------------------------------------------------------- parada
def test_parada_por_contenido(escenario):
    # sin escapes posibles (p_escape_hora = 0) la parada por contenido corta la corrida
    cont = {"inicio_min": 30, "tasa_linea_m_h": 1e5, "p_escape_hora": 0.0}
    au, ind = _correr(escenario, cont, parada={"horas_sin_avance": 12, "contenido": True})
    assert au.motivo_fin == "contenido" and au.motivo_fin_texto == MOTIVOS["contenido"]
    assert len(ind) < 7 and au.contencion.contenida.sum() > 0 and not au.act_pend.any() and au.parada_suspendida == {}
    # sin la parada por contenido, la corrida llega al horizonte pero el motivo final sigue siendo "contenido"
    au2, ind2 = _correr(escenario, cont)
    assert len(ind2) == 7 and au2.motivo_fin == "contenido"
    _iguales(au, au2, estado=False)          # mismo incendio; solo cambia cuándo se deja de simular


def test_parada_suspendida_por_escapes(escenario):
    """Hallazgo 2 (str3): con celdas contenidas que lindan con combustible y p_escape_hora > 0 la parada se suspende
    (v3.0 seguía hasta t_fin); `parada.escapes: ignorar` vuelve al criterio anterior; `potencial` para si ninguna celda
    contenida puede superar el umbral de escape con la meteorología que falta."""
    cont = {"inicio_min": 30, "tasa_linea_m_h": 1e5, "p_escape_hora": 0.5}
    par = {"horas_sin_avance": 2, "contenido": True}
    au, ind = _correr(escenario, cont, parada=par)
    assert len(ind) == 7 and au.motivo_fin == "contenido" and au.parada_suspendida.get("escapes", 0) >= 5
    assert "Parada anticipada suspendida por" in au.motivo_fin_texto and "escapes" in au.motivo_fin_texto
    au2, ind2 = _correr(escenario, cont, parada=dict(par, escapes="ignorar"))
    assert len(ind2) < 7 and au2.motivo_fin == "contenido" and au2.parada_suspendida == {}
    # el viento constante de 10 km/h no alcanza 3500 kW/m: con `potencial` no hay escape posible y la parada vale
    au3, ind3 = _correr(escenario, cont, parada=dict(par, escapes="potencial"))
    assert len(ind3) == len(ind2) and au3.motivo_fin == "contenido"
    # umbral de escape bajo y sorteo casi imposible: el escape es posible (suspende) aunque no ocurra
    au4, ind4 = _correr(escenario, dict(cont, intensidad_escape_kw_m=10.0, p_escape_hora=1e-9), parada=dict(par, escapes="potencial"))
    assert len(ind4) == 7 and au4.contencion.escapes == 0 and au4.parada_suspendida.get("escapes", 0) > 0


def _meteo_tramos(t0, tramos, horas=30, dir_deg=270.0):
    """Viento escalonado [(hora desde t0, km/h), …] (calma y después viento fuerte)."""
    from simulador.io.meteo import SerieMeteo
    ts = pd.date_range(pd.Timestamp(t0) - pd.Timedelta(hours=24), periods=horas + 24, freq="h")
    h = np.arange(len(ts)) - 24
    v = np.zeros(len(ts))
    for h0, vk in tramos:
        v[h >= h0] = vk
    return SerieMeteo(pd.DataFrame({"timestamp": [t.isoformat() for t in ts], "temp_c": 25.0, "hr_pct": 25.0, "viento_kmh": v,
                                    "viento_dir_deg": dir_deg, "precip_mm": 0.0, "fuente": "s"}))


def test_escape_tras_parada_suspendida():
    """adv_s1 (str3): calma 6 h y después 45 km/h. Antes la parada por contenido cortaba a la hora 1 con 0,09 ha; ahora la
    corrida sigue, a las 7 h las celdas contenidas superan el umbral y escapan (como v3.0 sin parada)."""
    capas = capas_sinteticas(121, codigo=102)
    met = _meteo_tramos(T0, [(0, 0.0), (6, 45.0)])
    p = {"contencion": {"activo": True, "inicio_min": 30, "tasa_linea_m_h": 1e5, "intensidad_escape_kw_m": 400.0, "p_escape_hora": 1.0},
         "parada": {"horas_sin_avance": 4, "contenido": True}}
    au, ind = simular_sintetico(capas, met, config_sintetica(parametros=p), 14.0, T0, fila=60, col=30)
    assert len(ind) == 15 and au.contencion.escapes > 0 and au.parada_suspendida.get("escapes", 0) >= 5
    p["parada"]["escapes"] = "ignorar"
    au0, ind0 = simular_sintetico(capas, met, config_sintetica(parametros=p), 14.0, T0, fila=60, col=30)
    assert au0.motivo_fin == "contenido" and len(ind0) < 4 and au0.contencion.escapes == 0
    assert au.area_quemada_ha() > 3 * au0.area_quemada_ha()


def test_parada_latentes_noche_humeda():
    """H2 (str4): noche húmeda de 13 h con extinción reversible. Antes `horas_sin_avance: 12` cortaba a las 15 h con
    25,6 ha; con celdas latentes el límite sube a 24 h y el fuego retoma de día (726 ha, igual que sin parada)."""
    from simulador.io.meteo import SerieMeteo
    t0 = pd.Timestamp(T0)
    ts = pd.date_range(t0 - pd.Timedelta(hours=24), periods=56, freq="h")
    h = np.arange(len(ts)) - 24
    hum = (h >= 3) & (h < 16)
    met = SerieMeteo(pd.DataFrame({"timestamp": [t.isoformat() for t in ts], "temp_c": np.where(hum, 8.0, 30.0),
                                   "hr_pct": np.where(hum, 95.0, 15.0), "viento_kmh": 10.0, "viento_dir_deg": 0.0,
                                   "precip_mm": 0.0, "fuente": "t"}))
    capas = capas_sinteticas(161, 102)
    res = {}
    for nombre, par in (("defecto", {"horas_sin_avance": 12, "contenido": True}), ("sin", SIN_PARADA),
                        ("solo12", {"horas_sin_avance": 12, "contenido": True, "latentes_max_h": 0})):
        cfg = config_sintetica(parametros={"barreras": {"activo": False}, "parada": par})
        res[nombre] = simular_sintetico(capas, met, cfg, 30.0, T0, fila=80, col=80)
    au, ind = res["defecto"]
    assert au.motivo_fin == "horizonte" and len(ind) == 31 and au.parada_suspendida.get("latentes", 0) >= 1
    assert au.area_quemada_ha() == res["sin"][0].area_quemada_ha() > 500.0
    assert "latentes" in au.motivo_fin_texto
    assert res["solo12"][0].motivo_fin == "sin_avance" and res["solo12"][0].area_quemada_ha() < 50.0    # comportamiento anterior


def test_razon_suspension():
    """Reglas de suspensión de la parada (escapes > pavesas > latentes) sobre un autómata mínimo."""
    from types import SimpleNamespace
    from simulador.corrida import razon_suspension
    au = SimpleNamespace(act_IB=np.array([0.0, 5.0]), n_latentes=3)
    assert razon_suspension(au, None, "contenido", 60, 600, 1, 12, pavesas=True) == "pavesas"
    assert razon_suspension(au, None, "contenido", 60, 600, 1, 12, pavesas=False) is None
    assert razon_suspension(au, None, "sin_avance", 60, 600, 12, 12) == "latentes"
    assert razon_suspension(au, None, "sin_avance", 60, 600, 24, 12) is None              # 24 h sin avance: para
    assert razon_suspension(au, None, "sin_avance", 60, 600, 12, 12, h_latentes=0) is None
    au.act_IB = np.zeros(2); au.n_latentes = 0
    assert razon_suspension(au, None, "sin_avance", 60, 600, 12, 12, pavesas=True) is None


def test_u01_del_automata():
    from simulador.ca import automata, contencion
    assert contencion.u01 is automata.u01


def test_intensidad_v3_ensemble():
    """Hallazgos 1 y 4 (str3): en el modo estocástico (ensembles) cada celda es su propio origen y la intensidad de avance
    es la de cabeza en todo el frente: no había celdas sostenibles y la contención no actuaba. Con `intensidad: v3` (por
    defecto) I sale de los enlaces hacia las vecinas pendientes y no depende del origen."""
    from simulador.ca.contencion import intensidad_local, intensidad_v3, exterior, vecino_exterior
    capas = capas_sinteticas(121, codigo=104)
    met = meteo_constante(T0, horas=8, viento_kmh=20.0, viento_dir_deg=270.0)
    cfg0 = config_sintetica(modo="estocastico", semilla=42, parametros={"parada": SIN_PARADA})
    au, _ = simular_sintetico(capas, met, cfg0, 1.0, T0, fila=60, col=30)
    ext, r0, c0 = exterior(au); b = vecino_exterior(au, ext, r0, c0)
    Ia, Iv = intensidad_local(au), intensidad_v3(au)
    assert (au.act_dist_self == 0).all() and np.ptp(Ia[b]) < 1e-6 * Ia[b].max()          # avance: cabeza en todo el frente
    assert (Iv[b] < 600).sum() > 0.5 * b.sum() and Iv[b].max() == pytest.approx(Ia[b].max(), rel=0.01)
    # I_v3 = máximo de intensidad_enlaces sobre las vecinas pendientes que siguen siendo combustible (sin barreras ni línea)
    Ie = au.intensidad_enlaces(slice(None))
    fv = np.clip(au.act[:, None] // au.W + au.df[None, :], 0, au.H - 1); cv = np.clip(au.act[:, None] % au.W + au.dc[None, :], 0, au.W - 1)
    assert np.allclose(Iv, np.where(au.estado[fv, cv] == 1, Ie, 0.0).max(1))
    libre, _ = simular_sintetico(capas, met, cfg0, 2.5, T0, fila=60, col=30)
    cont = {"activo": True, "inicio_min": 30, "tasa_linea_m_h": 6000.0, "intensidad_sostener_kw_m": 600.0, "p_escape_hora": 0.0}
    for inten in ("v3", "avance"):
        cfg = config_sintetica(modo="estocastico", semilla=42, parametros={"parada": SIN_PARADA, "contencion": dict(cont, intensidad=inten)})
        a, _ = simular_sintetico(capas, met, cfg, 2.5, T0, fila=60, col=30)
        if inten == "v3":
            assert a.contencion.contenida.sum() > 50 and a.area_quemada_ha() < 0.9 * libre.area_quemada_ha()
        else:
            assert a.contencion.contenida.sum() == 0 and a.area_quemada_ha() == libre.area_quemada_ha()
    with pytest.raises(ValueError):
        Contencion({"intensidad": "otra"}, 30.0, pd.Timestamp(T0))


def test_linea_dentro_del_paso_y_dt():
    """Hallazgo 3 (str3): la línea actúa dentro del paso (`Automata.filtro_enlaces`) y admite las celdas de la cola.
    Presupuesto y umbral ilimitados, sin escapes: después de la primera contención no se enciende ninguna celda y el área
    depende poco de dt (antes, en SH5 a 30 km/h: 25,3 / 32,9 / 73,0 ha con dt 0,5 / 2 / 5 min y 481 celdas tardías)."""
    capas = capas_sinteticas(121, codigo=145)
    met = meteo_constante(T0, horas=6, viento_kmh=30.0, viento_dir_deg=270.0)
    cont = {"inicio_min": 30, "tasa_linea_m_h": 1e7, "intensidad_sostener_kw_m": 1e9, "intensidad_sostener_aereo_kw_m": 1e9,
            "p_escape_hora": 0.0, "acumular_max_h": 1.0, "activo": True}
    area = {}
    for dtm in (1.0, 5.0):
        cfg = config_sintetica(parametros={"contencion": cont, "parada": SIN_PARADA}, dt_min=dtm)
        au, _ = simular_sintetico(capas, met, cfg, 1.5, T0, fila=60, col=30)
        c = au.contencion
        t1 = np.nanmin(c.t_contencion)
        assert t1 == pytest.approx(30.0 + dtm)                          # primer gasto al cerrar el primer paso de combate
        assert (au.t_llegada > t1 + 1e-3).sum() == 0                    # nada se enciende después del primer corte
        assert au.filtro_enlaces is not None
        area[dtm] = au.area_quemada_ha()
        if dtm == 5.0:
            assert c.celdas_cola > 0 and c.resumen(90.0)["contenciones_en_cola"] == c.celdas_cola
    assert max(area.values()) / min(area.values()) < 1.35


def test_escapes_vecindad16_y_barrera():
    """Hallazgo de lectura (str3): con vecindad 16 los escapes miran las 16 vecinas (saltos de caballo incluidos, con la
    regla de intermedias de `_activar_cola`), con la física de `Automata.fisica_celdas`; con barreras activas la intensidad
    hacia una vecina con camino se pondera por la probabilidad de cruce (v3.0 `_intensidad_efectiva`)."""
    from simulador.ca import estados as E
    t0 = pd.Timestamp(T0)
    met = meteo_constante(T0, horas=6, viento_kmh=10.0, viento_dir_deg=270.0)
    cont = {"activo": True, "inicio_min": 0, "intensidad_escape_kw_m": 0.0, "p_escape_hora": 1.0}
    # 16 vecinas: las 8 inmediatas ya quemadas; solo quedan los 8 saltos de caballo
    capas = capas_sinteticas(41, codigo=102)
    au = Automata(capas, met, config_sintetica(vecindad=16, parametros={"barreras": {"activo": False}}))
    au.preparar(t0, t0 + pd.Timedelta(hours=2))
    c = Contencion(cont, 30.0, t0); c.enganchar(au)
    c.contenida[20, 20] = True; au.estado[20, 20] = E.QUEMADO
    au.estado[19:22, 19:22] = E.QUEMADO
    assert c._escapes(au, 60.0, 1) == 1 and not c.contenida[20, 20]
    caballo = [(20 + int(a), 20 + int(b)) for a, b in zip(au.df[8:], au.dc[8:])]
    assert all(au.estado[f, cc] == E.IGNICION for f, cc in caballo)
    assert (au.estado == E.IGNICION).sum() == 8
    # vecindad 8 con un camino-muro (8 m, umbral λ = 50) en la vecina este: no se encienden ni ella ni las diagonales que
    # la tienen como intermedia (barrera por enlace, H1/H3); las otras 5 sí
    capas = capas_sinteticas(41, codigo=102)
    capas.camino_ancho[20, 21] = 8.0; capas.camino_tipo[20, 21] = 0
    au = Automata(capas, met, config_sintetica(parametros={"barreras": {"activo": True, "modo": "umbral", "lambda": 50.0}}))
    au.preparar(t0, t0 + pd.Timedelta(hours=2))
    c = Contencion(cont, 30.0, t0); c.enganchar(au)
    c.contenida[20, 20] = True; au.estado[20, 20] = E.QUEMADO
    assert c._escapes(au, 60.0, 1) == 1
    assert (au.estado[19:22, 21] == E.COMBUSTIBLE).all() and (au.estado == E.IGNICION).sum() == 5


def test_parada_sin_avance(escenario):
    au, ind = _correr(escenario, {"inicio_min": 30, "tasa_linea_m_h": 1e5, "p_escape_hora": 0.0},
                      parada={"horas_sin_avance": 2, "contenido": False})
    assert au.motivo_fin == "sin_avance" and "2 horas" in au.motivo_fin_texto
    assert ind[-1]["hora_indice"] < 6


def test_salidas_csv(escenario, tmp_path):
    au, ind = _correr(escenario, {"inicio_min": 30, "tasa_linea_m_h": 1000.0}, horas=2.0)
    df = pd.read_csv(geo.exportar_csv(ind, tmp_path))
    for col in ("contencion_celdas_contenidas", "contencion_metros_linea_hora", "contencion_linea_km", "contencion_escapes_hora",
                "contencion_tasa_linea_m_h", "contencion_aereo_activo", "contencion_inicio_min"):
        assert col in df.columns
    assert df["contencion_celdas_contenidas"].iloc[-1] == au.contencion.contenida.sum()
    au0, ind0 = _correr(escenario, horas=2.0)
    assert not any(c.startswith("contencion_") for c in pd.read_csv(geo.exportar_csv(ind0, tmp_path)).columns)
