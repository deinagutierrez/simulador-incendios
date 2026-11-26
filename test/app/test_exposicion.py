"""La exposición que el adaptador de v3.1 calcula (app/motores/exposicion.py) da lo mismo que la de v4.0
(src/v4.0/src/simulador/outputs/indicadores.py), con la misma infraestructura y la misma máscara.

Sin motores corriendo: se arma un fuego a mano sobre la grilla del dominio, alrededor de una vivienda.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app" / "motores"))

import exposicion                                    # noqa: E402

GRILLA = {"crs": "EPSG:5345", "xmin": 3513060.0, "ymax": 6417900.0, "res": 30.0, "filas": 1671, "cols": 1672}


@pytest.fixture(scope="module")
def expo():
    if not exposicion.INFRAESTRUCTURA.exists():
        pytest.skip("falta infraestructura.gpkg")
    return exposicion.Exposicion(GRILLA)


def _fuego(expo, radio_celdas: int, anillo: int):
    """Disco afectado centrado en una vivienda que tiene un camino cerca; el borde del disco está en combustión."""
    viv = expo.capas["viviendas"].geometry.centroid
    cam = expo.capas["caminos"]
    i = int(np.argmin([cam.distance(p).min() for p in viv]))
    x, y = viv.iloc[i].x, viv.iloc[i].y
    f0, c0 = int((GRILLA["ymax"] - y) // 30), int((x - GRILLA["xmin"]) // 30)
    ff, cc = np.ogrid[:GRILLA["filas"], :GRILLA["cols"]]
    d = np.hypot(ff - f0, cc - c0)
    afectada = d <= radio_celdas
    return afectada, afectada & (d > radio_celdas - anillo)


def _v40(expo, afectada, combustion):
    sys.path.insert(0, str(REPO / "src" / "v4.0" / "src"))
    try:
        from simulador.outputs.indicadores import exposicion as exposicion_v40
    finally:
        sys.path.remove(str(REPO / "src" / "v4.0" / "src"))
    capas = SimpleNamespace(grilla=SimpleNamespace(transform=expo.transform), viviendas_gdf=expo.capas["viviendas"],
                            red_gdf=expo.capas["red_electrica"], caminos_gdf=expo.capas["caminos"])
    return exposicion_v40(SimpleNamespace(capas=capas), afectada, combustion, exposicion.BUFFER_VIVIENDAS_M)


def test_igual_que_v40_con_viviendas_y_caminos_alcanzados(expo):
    afectada, combustion = _fuego(expo, 40, 3)
    mia, ref = expo.en(afectada, combustion), _v40(expo, afectada, combustion)
    assert mia["viviendas_afectadas"] >= 1 and mia["caminos_km_afectados"] > 0
    for k in ("viviendas_afectadas", "viviendas_amenazadas", "viviendas_a_salvo", "viviendas_total"):
        assert mia[k] == getattr(ref, k), k
    for k in ("tendido_km_quemado", "caminos_km_afectados"):
        assert mia[k] == pytest.approx(getattr(ref, k), abs=0.01), k


def test_sin_fuego_todo_en_cero(expo):
    nada = np.zeros((GRILLA["filas"], GRILLA["cols"]), bool)
    r = expo.en(nada, nada)
    assert (r["viviendas_afectadas"], r["viviendas_amenazadas"], r["tendido_km_quemado"], r["caminos_km_afectados"]) == (0, 0, 0.0, 0.0)
    assert r["viviendas_a_salvo"] == r["viviendas_total"]


def test_meteo_de_v31_en_km_h_y_rumbo():
    fila = SimpleNamespace(temperature_2m=25.44, relative_humidity_2m=31.6, wind_speed_10m_vectorial=5.0,
                           wind_direction_10m=350.0, precipitation=0.0)
    assert exposicion.meteo_v31(fila) == {"temp_c": 25.4, "hr_pct": 32.0, "viento_kmh": 18.0, "viento_dir_deg": 350.0,
                                          "viento_dir_texto": "N", "precip_mm_h": 0.0}
