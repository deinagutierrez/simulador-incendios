"""L03 (protocolo v1.3 §2.4): supresión desde cuarteles sobre escenarios sintéticos."""

import numpy as np
import pandas as pd

from simulador.ca.automata import Automata
from simulador.ca.supresion import Supresion
from simulador.sintetico import capas_sinteticas, meteo_constante, config_sintetica

T0 = "2024-01-01T12:00:00-03:00"


def _correr(horas=6.0, sup=None, viento=10.0, modo="determinista"):
    capas = capas_sinteticas(121, codigo=102)
    met = meteo_constante(T0, horas=int(horas) + 2, viento_kmh=viento, viento_dir_deg=270.0)
    cfg = config_sintetica(modo=modo, semilla=42)
    au = Automata(capas, met, cfg)
    t0 = pd.Timestamp(T0)
    au.preparar(t0, t0 + pd.Timedelta(hours=horas))
    au.encender(60, 30, t0, "c")
    for _ in range(int(round(horas * 60 / cfg["dt_min"]))):
        antes = au.minutos(au.t)
        au.paso_tiempo()
        if sup is not None:
            sup.aplicar(au, antes, au.minutos(au.t))
        if not au.activo():
            break
    return au


def test_sin_dotaciones_es_identico_a_la_base():
    base = _correr()
    nada = _correr(sup=Supresion([], 500.0, 2.4, 30.0))
    np.testing.assert_array_equal(np.isnan(base.t_llegada), np.isnan(nada.t_llegada))
    np.testing.assert_allclose(base.t_llegada[np.isfinite(base.t_llegada)], nada.t_llegada[np.isfinite(nada.t_llegada)])


def test_llama_limite_cero_no_contiene():
    base = _correr()
    s = Supresion([0.0], 5000.0, 0.0, 30.0)
    con = _correr(sup=s)
    assert s.celdas == 0
    assert con.area_quemada_ha() == base.area_quemada_ha()


def test_supresion_reduce_la_superficie_y_respeta_el_presupuesto():
    base = _correr()
    s = Supresion([30.0, 90.0], 600.0, 2.4, 30.0)
    con = _correr(sup=s)
    assert con.area_quemada_ha() < base.area_quemada_ha()
    horas_dotacion = (6 * 60 - 30) / 60 + (6 * 60 - 90) / 60
    assert s.linea_m <= 600.0 * horas_dotacion + 1e-6
    assert s.celdas > 0 and s.contenida.sum() == s.celdas


def test_mucha_linea_apaga_el_incendio():
    s = Supresion([0.0], 1e6, 100.0, 30.0)
    au = _correr(sup=s)
    assert not au.activo()
    assert au.area_quemada_ha() < 5.0


def test_contiene_primero_la_menor_llama():
    # sin viento la llama es pareja; con viento de 10 km/h la cola y los flancos tienen menos llama que la cabeza:
    # con poca línea, lo contenido debe quedar del lado de barlovento (oeste) del punto de ignición
    s = Supresion([20.0], 300.0, 100.0, 30.0)
    _correr(sup=s, horas=3.0)
    f, c = np.nonzero(s.contenida)
    assert c.size > 0 and np.median(c) < 60


def test_intensidad_v3_opcional():
    """`supresion.intensidad`: `avance` (por defecto, V.4) usa la dirección origen → celda; en el modo estocástico
    (ensembles) cada celda es su propio origen y la llama es la de cabeza en todo el frente, así que con llama_max por
    debajo de la de cabeza L03 no contiene nada. `v3` usa la llama hacia la vecina pendiente más expuesta."""
    from simulador.config import DEFAULTS
    cfg = {"parametros": {"supresion": dict(DEFAULTS["parametros"]["supresion"], activo=True)}}
    assert Supresion.desde_cfg(cfg, 30.0).intensidad == "avance"
    cfg["parametros"]["supresion"]["intensidad"] = "v3"
    assert Supresion.desde_cfg(cfg, 30.0).intensidad == "v3"
    # determinista: el criterio por defecto no cambia (mismo resultado que sin indicar la opción)
    a = _correr(sup=Supresion([30.0], 600.0, 2.4, 30.0), horas=3.0)
    b = _correr(sup=Supresion([30.0], 600.0, 2.4, 30.0, intensidad="avance"), horas=3.0)
    np.testing.assert_array_equal(np.nan_to_num(a.t_llegada, nan=-1), np.nan_to_num(b.t_llegada, nan=-1))
    # estocástico: la llama de cabeza GR2 a 10 km/h es 0,81 m; límite 0,7 m
    s_av = Supresion([20.0], 600.0, 0.7, 30.0)
    _correr(sup=s_av, horas=2.0, modo="estocastico")
    s_v3 = Supresion([20.0], 600.0, 0.7, 30.0, intensidad="v3")
    au = _correr(sup=s_v3, horas=2.0, modo="estocastico")
    assert s_av.celdas == 0 and s_v3.celdas > 0
    L = Supresion.llama_enlaces(au)
    assert (L <= au.act_llama + 1e-6).all() and (L[~au.act_pend.any(1)] == 0).all()
    import pytest
    with pytest.raises(ValueError):
        Supresion([0.0], 1.0, 1.0, 30.0, intensidad="otra")
