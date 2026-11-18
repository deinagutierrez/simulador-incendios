"""Campo de viento para el mapa (casilla «Viento» de la pantalla).

Cada proceso motor deja en `<corrida>/viento/` el viento que usó, muestreado cada ~1 km, y el servidor lo entrega como
flechas en `GET /api/corridas/<id>/viento?hora=N`. Estas pruebas usan el motor simulado (viento de prueba que gira 15° por
hora y no mueve el fuego) y no usan internet. Que guardar el viento no cambia el resultado de los motores reales lo cubre
`test_servidor.py::test_modo_ambos_por_el_servidor_da_lo_mismo_que_la_corrida_offline` (0 celdas distintas).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))
sys.path.insert(0, str(REPO / "app" / "motores"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from control import malla_viento                      # noqa: E402
from servidor import viento                           # noqa: E402
from test_servidor import Servidor                    # noqa: E402

GRILLA = {"crs": "EPSG:5345", "xmin": 4_000_000.0, "ymax": 6_400_000.0, "res": 30.0, "filas": 200, "cols": 150}


@pytest.fixture(scope="module")
def servidor(tmp_path_factory):
    s = Servidor(tmp_path_factory.mktemp("corridas_viento"))
    yield s
    s.cerrar()


def test_malla_cada_un_kilometro_y_corrida_medio_paso():
    m = malla_viento(GRILLA)
    assert m["paso_m"] == 990.0 and (m["ny"], m["nx"]) == (len(m["filas"]), len(m["cols"])) == (6, 5)
    assert m["filas"][0] == 16 and m["x0"] == GRILLA["xmin"] + 16.5 * 30.0 and m["y0"] == GRILLA["ymax"] - 16.5 * 30.0
    corrida = malla_viento(GRILLA, medio_paso=True)       # la de v3.1: intercalada con la de v4.0
    assert corrida["filas"][0] == 32 and corrida["x0"] - m["x0"] == 16 * 30.0


def test_sin_viento_guardado_no_hay_flechas(tmp_path):
    assert viento.horas(tmp_path) == [] and viento.flechas(tmp_path, 3) is None


def test_flechas_por_hora_en_vivo_y_al_recorrer(servidor):
    id_ = servidor.simulada(horas=6)
    servidor.esperar(id_, "terminada")
    codigo, w = servidor.pedir(f"/api/corridas/{id_}/viento?hora=3")
    assert codigo == 200 and w["hora"] == 3 and w["horas"] == list(range(7)) and w["momento"] == "instante"
    assert len(w["flechas"]) == w["filas"] * w["columnas"] > 0
    lat, lon, vel, desde, f, c = w["flechas"][0]
    assert -33.5 < lat < -32 and -66.5 < lon < -65 and 0 < vel < 60 and 0 <= desde < 360 and (f, c) == (0, 0)
    # el viento de prueba viene del 300° + 15° por hora (±10° en el espacio): en la hora 3, de unos 345°
    assert abs(((w["dir_media"] - 345) + 180) % 360 - 180) < 12
    codigo, w0 = servidor.pedir(f"/api/corridas/{id_}/viento?hora=0")
    assert codigo == 200 and w0["hora"] == 0 and w0["dir_media"] != w["dir_media"]
    codigo, ultima = servidor.pedir(f"/api/corridas/{id_}/viento?hora=99")     # más allá del final: la última guardada
    assert codigo == 200 and ultima["hora"] == 6
    assert servidor.pedir(f"/api/corridas/{id_}/viento")[1]["hora"] == 6


def test_el_viento_manual_se_ve_en_las_flechas(servidor):
    id_ = servidor.simulada(horas=40, s_por_hora=0.05)
    servidor.esperar(id_, "corriendo")
    servidor.pedir(f"/api/corridas/{id_}/pausar", {})
    h = servidor.esperar(id_, "pausada")["ultima_hora"]["h"]
    codigo, r = servidor.pedir(f"/api/corridas/{id_}/intervenciones", {"tipo": "viento_manual",
                                                                       "datos": {"vel_kmh": 50, "dir_desde": 90}})
    assert codigo == 200 and r["estado"] == "aceptada"
    servidor.pedir(f"/api/corridas/{id_}/reanudar", {})
    servidor.esperar(id_, "terminada")
    w = servidor.pedir(f"/api/corridas/{id_}/viento?hora={h + 1}")[1]
    assert w["hora"] == h + 1 and abs(w["dir_media"] - 90) < 12 and 45 < w["vel_media_kmh"] < 55
    antes = servidor.pedir(f"/api/corridas/{id_}/viento?hora={h}")[1]
    assert abs(antes["vel_media_kmh"] - 50) > 5                                # la hora de la pausa conserva el anterior


def test_el_zip_exportado_trae_el_viento(servidor, tmp_path):
    import io
    import zipfile
    id_ = servidor.simulada(horas=2)
    servidor.esperar(id_, "terminada")
    codigo, crudo = servidor.pedir(f"/api/corridas/{id_}/exportar")
    assert codigo == 200
    nombres = zipfile.ZipFile(io.BytesIO(crudo)).namelist()
    assert f"{id_}/viento/malla.json" in nombres and f"{id_}/viento/h0002.npy" in nombres
