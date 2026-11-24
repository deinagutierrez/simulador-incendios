"""Combate común sobre el motor v3.1 (app/motores/combate_v31.py; decisión D-E3-36).

Lo que necesita el motor cargado en el mismo proceso lo hace test/app/ayudante_combate_v31.py, en un proceso aparte (cada
proceso carga un solo `incendios_sl`), una sola vez para todas las pruebas de este archivo: sobre las entradas sintéticas del
propio motor comprueba lo mismo que test_combate_v40.py en v4.0. Unos segundos (más la compilación de numba la primera
vez). Las corridas con el proceso motor real están en test_combate_motores.py.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
AYUDANTE = Path(__file__).resolve().parent / "ayudante_combate_v31.py"
TOPE_S = 600


@pytest.fixture(scope="module")
def r() -> dict:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    env.pop("PYTHONPATH", None)
    env.pop("INCENDIOS_SL_INPUT", None)
    p = subprocess.run([sys.executable, str(AYUDANTE)], cwd=REPO, env=env, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=TOPE_S)
    assert p.returncode == 0, p.stdout[-2000:] + p.stderr[-3000:]
    return json.loads(p.stdout.rsplit("RESULTADO ", 1)[1])


def test_las_piezas_comunes_son_las_del_motor(r):
    assert r["hash_igual"] is True                       # el sorteo de escapes: el mismo splitmix64 de v3.1
    assert r["corte_distinto"] == 0                      # la línea corta los mismos enlaces que `_cortado_por_contencion`


def test_sin_despachos_la_simulacion_no_se_toca(r):
    s = r["sin_despachos"]
    assert s["celdas"] > 1000 and s["llegada"] == 0 and s["estado"] == 0
    assert s["contencion_activo"] is False and s["habilitado"] is False and s["t_cont"] == [1, 1]


def test_habilitar_sin_linea_no_cambia_la_propagacion(r):
    # con la contención del motor encendida (pero sin empezar nunca) y ninguna celda con línea, da lo mismo que apagada
    s = r["habilitado_sin_linea"]
    assert s["respuesta"] == "aceptada" and s["contencion_activo"] is True and s["t_cont"] == [121, 121] and s["linea"] == 0
    assert s["llegada"] == 0 and s["estado"] == 0 and s["motivo"] == r["sin_despachos"]["motivo"]


@pytest.mark.parametrize("vecindad", [8, 16])
def test_la_linea_frena_el_fuego(r, vecindad):
    s = r[f"frena_{vecindad}"]
    assert s["respuesta"] == "aceptada"
    assert s["nuevas_h2"] == s["frente_h2"] > 0 and s["nuevas_despues"] == [0, 0, 0]
    assert s["ultima_llegada_s"] <= 7200.0 + 1e-3        # nada se enciende después de la hora 2
    assert s["celdas"] < 0.5 * s["celdas_libre"]
    # la línea del método común es exactamente el estado CONTENIDA del motor, y el motor lo sabe (`n_cont`, motivo 7)
    assert s["linea"] == s["contenidas_motor"] == s["n_cont"] == s["nuevas_h2"] and s["linea_igual_a_contenidas"] is True
    assert s["motivo"] == 7


def test_pocas_dotaciones_producen_lo_mismo_que_en_v40(r):
    s = r["pocas"]
    # 30 bomberos = 600 m/h = 20 celdas por hora, desde la hora 2: la misma cuenta de test_combate_v40.py
    assert s["linea_m_hora"] == [0.0, 600.0, 600.0, 600.0, 600.0]
    assert s["linea"] == 120 and s["componentes"] == 1 and s["activas_con_linea"] == 0
    assert s["celdas"] < r["sin_despachos"]["celdas"]


def test_reavivar_vuelve_a_propagar_desde_ese_momento(r):
    s = r["reavivar"]
    assert s["celdas"] > s["celdas_antes"]
    assert s["primera_llegada_nueva_s"] >= 4 * 3600.0    # nada se enciende "en el pasado"
    assert s["llegada_original_igual"] is True and s["lejos_max_celdas"] < 80


def test_determinista(r):
    assert r["determinista"] is True


def test_con_la_contencion_propia_del_motor_el_despacho_se_rechaza(r):
    s = r["contencion_propia"]
    assert s["respuesta"] == "error" and "contención propia del motor v3.1" in s["motivo"]
    assert s["habilitado"] is False and s["contenidas_motor"] > 0          # corrió la contención del motor, no la común


# ================================================================================================ descargas aéreas (etapa 2)
def test_el_adaptador_ubica_las_descargas(r):
    u = r["ubicacion"]
    assert u["filas"] == [10.5, 0.0] and u["cols"] == [20.25, 0.0] and u["hora_0"] == 15 and u["hora_125"] == 17


def test_agua_delante_del_fuego_lo_demora_y_al_secarse_sigue(r):
    s = r["agua"]
    assert s["estados"] == ["aceptada"] * 6 and s["mojadas"] == 30 and s["vence"] == [180.0]
    assert s["agua_h2"] == 30 and s["vencidas_h3"] == 30 and s["linea_final"] == 0 and s["contenidas_final"] == 0 and s["n_cont"] == 0
    assert s["detras_libre_min"] < 170.0                 # sin la franja el fuego pasa antes de que el agua se seque
    assert 180.0 - 1e-3 <= s["detras_min"] < 240.0       # con la franja pasa recién cuando se seca, y pasa


@pytest.mark.parametrize("vecindad", [8, 16])
def test_el_retardante_aguanta_y_el_fuego_lo_rodea(r, vecindad):
    s = r[f"retardante_{vecindad}"]
    assert s["estados"] == ["aceptada"] * 6 and s["vence"] == [None] * 6
    assert s["linea"] == 30 and s["vencidas"] == 0 and s["clase_ok"] is True and s["franja_ardio"] == 0
    assert s["medio_min"] is None or s["medio_min"] > s["medio_libre_min"] + 60.0
    assert s["celdas"] < s["celdas_libre"] and s["linea_igual_a_contenidas"] is True


def test_descarga_sobre_el_frente_y_agua_asegurada_por_los_bomberos(r):
    s = r["sobre_el_frente"]
    assert s["frenadas"] > 0 and s["frenadas"] + s["mojadas"] == s["linea_h2"]
    c = r["consolida"]
    assert c["consolidadas_h3"] > 0 and c["consolidadas_h3"] + c["vencidas_h3"] == 30
    assert c["aseguradas"] == c["consolidadas_h3"] and c["clase_ok"] is True and c["no_vencen"] is True


def test_descargas_de_noche_tope_y_determinismo(r):
    assert r["de_noche"]["estado"] == "rechazada" and "de día" in r["de_noche"]["motivo"] and r["de_noche"]["habilitado"] is False
    assert r["tope"] == {"aceptadas": 12, "ultima": "rechazada"}
    assert r["determinista_descargas"] is True
