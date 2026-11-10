"""Tests de simetría y sensibilidad del autómata (sección 4.5 y 7.4 del enunciado)."""

import numpy as np
import pytest

from simulador.sintetico import capas_sinteticas, meteo_constante, config_sintetica, correr_sintetico
from simulador.physics.elipse import relacion_largo_ancho


def _radios(au, n):
    q = au.afectada; f, c = np.nonzero(q); r = np.hypot(f - n // 2, c - n // 2) * 30
    ang = np.degrees(np.arctan2(c - n // 2, -(f - n // 2))) % 360
    out = []
    for a0 in range(0, 360, 15):
        m = np.abs(((ang - a0) + 180) % 360 - 180) < 4
        out.append(r[m].max())
    return np.array(out), (q.sum() * 900 / np.pi) ** 0.5


@pytest.mark.parametrize("vecindad", [8, 16])
def test_circulo_sin_viento(vecindad):
    cap = capas_sinteticas(201, 104); met = meteo_constante(viento_kmh=0, hr_pct=15)
    au = correr_sintetico(cap, met, config_sintetica(vecindad=vecindad), horas=8)
    r, req = _radios(au, 201)
    assert not au.toco_borde
    assert (r.max() - r.min()) / req < 0.10, f"error de radio {(r.max()-r.min())/req:.3f}"


@pytest.mark.parametrize("vecindad", [8, 16])
def test_elipse_con_viento(vecindad):
    cap = capas_sinteticas(401, 104); met = meteo_constante(viento_kmh=20, viento_dir_deg=0, hr_pct=15)
    au = correr_sintetico(cap, met, config_sintetica(vecindad=vecindad), horas=2)
    q = au.afectada; f, c = np.nonzero(q)
    largo = f.max() - f.min() + 1; ancho = c.max() - c.min() + 1
    lb_sim = largo / ancho
    # LB teórica con el viento efectivo real de la corrida (rumbo medio de la cabeza = S)
    from simulador.physics import rothermel as RT
    assert f.max() - 200 > 200 - f.min()             # cabeza hacia el S (viento del N)
    # tolerancia 20 % respecto de Anderson con el viento a media llama de GR4
    # factor 10 m → 20 ft del modelo (0,87 corregido; V.4 usaba 1/0,87 y este test lo incorporaba: docs/v4.0/15, P1)
    from simulador.physics.viento import waf_sin_dosel, KMH_A_MI_H, ParametrosViento
    lb_teo = relacion_largo_ancho(20 * KMH_A_MI_H * ParametrosViento().factor_10m_20ft * waf_sin_dosel(np.array([2.0]))[0])
    assert abs(lb_sim - lb_teo) / lb_teo < 0.20, f"LB sim {lb_sim:.2f} vs teórica {lb_teo:.2f}"


def test_pendiente_elonga_ladera_arriba():
    cap = capas_sinteticas(301, 104, pendiente_deg=20, orientacion_deg=180)   # baja hacia el S → sube hacia el N
    met = meteo_constante(viento_kmh=0, hr_pct=15)
    au = correr_sintetico(cap, met, config_sintetica(), horas=4)
    f, c = np.nonzero(au.afectada)
    arriba = 150 - f.min(); abajo = f.max() - 150
    assert arriba > 2 * abajo


@pytest.mark.parametrize("vecindad", [8, 16])
def test_area_invariante_al_rumbo_del_viento(vecindad):
    areas = []
    for d in (0, 45, 90):
        cap = capas_sinteticas(401, 104); met = meteo_constante(viento_kmh=20, viento_dir_deg=d, hr_pct=15)
        au = correr_sintetico(cap, met, config_sintetica(vecindad=vecindad), horas=2)
        areas.append(au.area_quemada_ha())
    assert (max(areas) - min(areas)) / np.mean(areas) < 0.05, f"áreas {areas}"


def test_sensibilidad_dt():
    """La superficie no puede variar más de un 5 % entre Δt = 1 y Δt = 5 min."""
    areas = {}
    for dt in (1.0, 5.0):
        cap = capas_sinteticas(301, 122); met = meteo_constante(viento_kmh=15, viento_dir_deg=315, hr_pct=20)
        au = correr_sintetico(cap, met, config_sintetica(dt_min=dt), horas=3)
        areas[dt] = au.area_quemada_ha()
    assert abs(areas[1.0] - areas[5.0]) / areas[1.0] < 0.05, f"áreas {areas}"


def test_sensibilidad_un_factor_a_la_vez():
    """Más viento, menos HR, más pendiente y menos humedad viva → más superficie."""
    base = dict(viento_kmh=10, viento_dir_deg=0, hr_pct=30)
    def area(**kw):
        p = dict(base); p.update({k: v for k, v in kw.items() if k in base})
        # orientación 0 = la ladera baja hacia el N, sube hacia el S: alineada con el viento del N
        cap = capas_sinteticas(301, 122, pendiente_deg=kw.get("pendiente", 0), orientacion_deg=0)
        cap.ndmi_mes = np.zeros(cap.shape, "float32")                 # NDMI 0 → humedad viva = viva_a
        cap.ndvi_mes = np.full(cap.shape, 0.25, "float32"); cap.ndvi_verano = np.full(cap.shape, 0.45, "float32")
        met = meteo_constante(**p)
        cfg = config_sintetica(**({"parametros": {"humedad": {"viva_a": kw["viva_a"]}}} if "viva_a" in kw else {}))
        return correr_sintetico(cap, met, cfg, horas=2).area_quemada_ha()
    a0 = area()
    assert area(viento_kmh=20) > a0
    assert area(hr_pct=15) > a0
    assert area(pendiente=20) > a0
    assert area(viva_a=60) > a0


def test_estocastico_reproducible():
    cap = capas_sinteticas(201, 104); met = meteo_constante(viento_kmh=10, hr_pct=20)
    a1 = correr_sintetico(cap, met, config_sintetica(modo="estocastico", semilla=7), horas=2).area_quemada_ha()
    a2 = correr_sintetico(cap, met, config_sintetica(modo="estocastico", semilla=7), horas=2).area_quemada_ha()
    assert a1 == a2 and a1 > 0


def test_no_combustible_y_borde():
    cap = capas_sinteticas(61, 104); met = meteo_constante(viento_kmh=25, viento_dir_deg=0, hr_pct=15)
    cap.combustible[:, :5] = 98   # agua al oeste
    au = correr_sintetico(cap, met, config_sintetica(), horas=3)
    assert au.toco_borde and not au.afectada[:, :5].any()
