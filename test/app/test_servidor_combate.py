"""Pruebas del servidor para el combate (contrato 1.6), con el motor simulado.

Dotaciones al crear la corrida, despacho y retiro en pausa, descargas aéreas en pausa (con sus franjas para el mapa), avisos
`combate`, la línea como imagen, la llegada estimada desde los cuarteles, la reproducción desde la bitácora y la exportación. El combate del motor simulado es el método común de
verdad (`app/motores/combate.py`) sobre un fuego de juguete. Levantan el servidor en un puerto libre; no usan internet y
tardan segundos.
"""
from __future__ import annotations

import io
import json
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_servidor import FINALES, Servidor   # noqa: E402

PUNTO = {"lon": -65.55, "lat": -32.64}
LADO = 80


@pytest.fixture(scope="module")
def servidor(tmp_path_factory):
    s = Servidor(tmp_path_factory.mktemp("corridas_combate"))
    yield s
    s.cerrar()


def _crear(servidor, horas=12, s_por_hora=0.03, **extra) -> str:
    codigo, r = servidor.pedir("/api/corridas", {"motor": "simulado", "horas": horas, "iniciar": True, "ignicion": [PUNTO],
                                                 "simulado": {"s_por_hora": s_por_hora, "lado": LADO}, **extra})
    assert codigo == 201, r
    return r["corridas"][0]["id"]


def _esperar(servidor, id_: str, estados, limite_s: float = 60.0) -> dict:
    limite = time.monotonic() + limite_s
    while True:
        d = servidor.pedir(f"/api/corridas/{id_}")[1]
        if d["estado"] in estados:
            return d
        assert time.monotonic() < limite, d["estado"]
        time.sleep(0.03)


def _pausar_en(servidor, id_: str, hora: int) -> None:
    assert servidor.pedir(f"/api/corridas/{id_}/pausar", {"en_t_sim_min": hora * 60})[0] == 200
    _esperar(servidor, id_, {"pausada"})


def _pixeles(servidor, id_: str, hora: int) -> int:
    from PIL import Image
    codigo, png = servidor.pedir(f"/api/corridas/{id_}/combate.png?hora={hora}")
    assert codigo == 200, png
    return int((np.asarray(Image.open(io.BytesIO(png)))[..., 3] > 0).sum())


def test_estado_informa_el_combate(servidor):
    codigo, e = servidor.pedir("/api/estado")
    assert codigo == 200
    c = e["combate"]
    assert c["max_bomberos"] == 500 and c["max_llegada_min"] == 1440 and c["prioridades"] == ["flancos", "cabeza"]
    assert c["parametros"]["m_h_por_bombero"] == 20.0 and c["parametros"]["intensidad_sostener_kw_m"] == 1700.0
    assert c["parametros"]["cadencia_min"] == 60


def test_arribo_desde_los_cuarteles(servidor):
    codigo, r = servidor.pedir(f"/api/arribo?lat={PUNTO['lat']}&lon={PUNTO['lon']}")
    assert codigo == 200, r
    assert r["aviso_min"] == 30 and r["alistamiento_min"] == 15 and 1 <= len(r["cuarteles"]) <= 5
    viajes = [q["viaje_min"] for q in r["cuarteles"]]
    assert viajes == sorted(viajes) and all(isinstance(v, int) and 0 <= v < 600 for v in viajes)
    assert all(q["nombre"] for q in r["cuarteles"])
    assert servidor.pedir("/api/arribo?lat=0&lon=0")[0] == 404              # fuera del dominio
    assert servidor.pedir("/api/arribo?lat=abc&lon=1")[0] == 422


@pytest.mark.parametrize("dotaciones, texto", [
    ([{"bomberos": 0}], "greater than or equal to 1"),
    ([{"bomberos": 501}], "less than or equal to 500"),
    ([{"bomberos": 5, "llegada_min": -1}], "greater than or equal to 0"),
    ([{"bomberos": 5, "prioridad": "cola"}], "flancos"),
    ([{"retirar": True}], "antes de iniciar no hay nada que retirar"),
    ([{"llegada_min": 5}], "falta `bomberos`"),
    ([{"bomberos": 5, "otra": 1}], "otra"),
    ([{"bomberos": 1}] * 21, "at most 20"),
])
def test_dotaciones_mal_pedidas_al_crear(servidor, dotaciones, texto):
    codigo, r = servidor.pedir("/api/corridas", {"motor": "simulado", "horas": 3, "ignicion": [PUNTO], "dotaciones": dotaciones,
                                                 "simulado": {"lado": LADO}})
    assert codigo == 422, r
    assert texto in json.dumps(r, ensure_ascii=False)


def test_dotaciones_desde_el_inicio_y_en_pausa(servidor):
    id_ = _crear(servidor, dotaciones=[{"bomberos": 20, "llegada_min": 60}])
    _pausar_en(servidor, id_, 4)
    # la línea de las horas 2 y 3 ya está (400 m/h = 13 celdas por hora); la de la hora 4 se coloca al reanudar
    assert _pixeles(servidor, id_, 4) == 26 and _pixeles(servidor, id_, 2) == 13 and _pixeles(servidor, id_, 1) == 0
    d = servidor.pedir(f"/api/corridas/{id_}")[1]
    assert d["dotaciones_iniciales"] == [{"bomberos": 20, "llegada_min": 60, "prioridad": "flancos"}]
    assert [x["h"] for x in d["combate"]] == [0, 1, 2, 3] and [x["celdas_nuevas"] for x in d["combate"]] == [0, 0, 13, 13]

    # mal pedidas en pausa: 422 con el motivo, y no entran a la bitácora
    for datos, texto in (({"bomberos": 0}, "greater than or equal to 1"), ({"retirar": True, "bomberos": 3}, "con `retirar` no van"),
                         ({"bomberos": 3, "llegada_min": 2000}, "less than or equal to 1440")):
        codigo, r = servidor.pedir(f"/api/corridas/{id_}/intervenciones", {"tipo": "dotacion", "datos": datos})
        assert codigo == 422 and "despacho de bomberos" in r["detail"] and texto in r["detail"], r

    codigo, a = servidor.pedir(f"/api/corridas/{id_}/intervenciones", {"tipo": "dotacion", "datos": {"bomberos": 300, "prioridad": "cabeza"}})
    assert codigo == 200 and a["estado"] == "aceptada" and a["t_vigor_min"] == 240.0, a
    assert a["entrada"]["tipo"] == "dotacion" and a["entrada"]["datos"] == {
        "bomberos": 300, "llegada_min": 0, "prioridad": "cabeza", "dotacion": 2, "tasa_m_h": 6000.0, "desde_min": 240.0}
    codigo, b = servidor.pedir(f"/api/corridas/{id_}/intervenciones", {"tipo": "dotacion", "datos": {"bomberos": 5, "llegada_min": 90}})
    assert codigo == 200 and b["t_vigor_min"] == 330.0 and b["entrada"]["datos"]["desde_min"] == 330.0

    assert servidor.pedir(f"/api/corridas/{id_}/reanudar", {})[0] == 200
    _pausar_en(servidor, id_, 8)
    codigo, r = servidor.pedir(f"/api/corridas/{id_}/intervenciones", {"tipo": "dotacion", "datos": {"retirar": True}})
    assert codigo == 200 and r["entrada"]["datos"] == {"retirar": True, "dotaciones_retiradas": 3, "bomberos_retirados": 325}
    codigo, r = servidor.pedir(f"/api/corridas/{id_}/intervenciones", {"tipo": "dotacion", "datos": {"retirar": True}})
    assert codigo == 200 and r["estado"] == "rechazada" and "no hay dotaciones" in r["motivo"] and r["entrada"] is None
    servidor.pedir(f"/api/corridas/{id_}/reanudar", {})
    d = _esperar(servidor, id_, FINALES)

    assert d["estado"] == "terminada" and d["bitacora_integra"] is True
    assert [e["tipo"] for e in d["bitacora"]] == ["pausa", "dotacion", "dotacion", "reanudacion", "pausa", "dotacion", "reanudacion"]
    h = {x["h"]: x for x in d["combate"]}
    assert sorted(h) == list(range(12))                                     # un paso de combate por hora, salvo la última
    # hora 5: las 300 llegaron en la 4 y trabajaron una hora; con lo de la primera dotación alcanza para todo el borde
    assert h[5]["bomberos"] == 320 and h[5]["celdas_nuevas"] == h[5]["frente_celdas"] > 0
    assert h[6]["frente_celdas"] == 0 and h[6]["bomberos"] == 325 and h[9]["bomberos"] == 0
    assert h[11]["celdas_linea"] == h[5]["celdas_linea"] and h[11]["escapes"] == 0
    res = d["resultados"]["combate"]
    assert res["celdas_linea_final"] == h[11]["celdas_linea"] and res["linea_m"] == h[11]["linea_m"] and res["archivo"] == "combate_parcial.npy"
    assert [x["hasta_min"] for x in res["dotaciones"]] == [480.0, 480.0, 480.0] and res["parametros"]["p_escape_hora"] == 0.5
    # el fuego quedó contenido: la superficie no creció después de la hora 5
    carpeta = servidor.app.state.gestor.obtener(id_).carpeta
    huella = np.load(carpeta / "t_llegada_parcial.npy")
    assert float(np.nanmax(huella)) <= 5 * 60.0
    # la línea en disco y como imagen, por hora
    capas = np.load(carpeta / "combate_parcial.npy")
    assert capas.shape == (3,) + huella.shape and int((capas[2] == 1).sum()) == res["celdas_linea_final"]
    assert _pixeles(servidor, id_, 12) == res["celdas_linea_final"] and _pixeles(servidor, id_, 3) == 26

    # reproducción desde la bitácora: la misma cadena, la misma huella y la misma línea
    codigo, r = servidor.pedir(f"/api/corridas/{id_}/reproducir", {"iniciar": True})
    assert codigo == 201, r
    d2 = _esperar(servidor, r["corridas"][0]["id"], FINALES)
    assert d2["estado"] == "terminada" and d2["resultados"]["reproduccion"]["cadena_igual"] is True
    assert d2["resultados"]["combate"]["celdas_linea_sha256"] == res["celdas_linea_sha256"]
    carpeta2 = servidor.app.state.gestor.obtener(d2["id"]).carpeta
    assert np.array_equal(np.load(carpeta2 / "t_llegada_parcial.npy"), huella, equal_nan=True)
    assert np.array_equal(np.load(carpeta2 / "combate_parcial.npy"), capas, equal_nan=True)

    # exportación: la línea va en el zip
    codigo, crudo = servidor.pedir(f"/api/corridas/{id_}/exportar")
    assert codigo == 200
    nombres = {n.split("/", 1)[1] for n in zipfile.ZipFile(io.BytesIO(crudo)).namelist()}
    assert {"corrida.json", "bitacora.jsonl", "combate_parcial.npy"} <= nombres


def test_sin_combate_no_hay_linea_ni_avisos(servidor):
    id_ = _crear(servidor, horas=4)
    d = _esperar(servidor, id_, FINALES)
    assert d["combate"] == [] and d["dotaciones_iniciales"] == [] and "combate" not in d["resultados"]
    assert not (servidor.app.state.gestor.obtener(id_).carpeta / "combate_parcial.npy").exists()
    assert servidor.pedir(f"/api/corridas/{id_}/combate.png?hora=2")[0] == 404
    assert not any(e.get("aviso") == "combate" for e in servidor.app.state.gestor.obtener(id_).eventos)


def test_despacho_fuera_de_pausa_se_rechaza(servidor):
    id_ = _crear(servidor, horas=40, s_por_hora=0.05)
    codigo, r = servidor.pedir(f"/api/corridas/{id_}/intervenciones", {"tipo": "dotacion", "datos": {"bomberos": 5}})
    assert codigo == 409, r
    servidor.pedir(f"/api/corridas/{id_}/detener", {})
    _esperar(servidor, id_, FINALES)


# ================================================================================================ descargas aéreas (etapa 2)
RES = 30.0


def _grilla() -> tuple[float, float]:
    """xmin e ymax de la grilla del motor simulado con ignición en PUNTO (la misma cuenta que proceso_simulado.py)."""
    from pyproj import Transformer
    x, y = Transformer.from_crs("EPSG:4326", "EPSG:5345", always_xy=True).transform(PUNTO["lon"], PUNTO["lat"])
    return round((x - LADO * RES / 2) / RES) * RES, round((y + LADO * RES / 2) / RES) * RES


def _xy(fila: float, col: float) -> list[float]:
    xmin, ymax = _grilla()
    return [xmin + col * RES, ymax - fila * RES]


def _lonlat(puntos) -> list[list[float]]:
    from pyproj import Transformer
    t = Transformer.from_crs("EPSG:5345", "EPSG:4326", always_xy=True)
    return [list(t.transform(x, y)) for x, y in puntos]


def _descargar(servidor, id_: str, fila: float, col: float, **datos):
    """Una descarga hacia el este que empieza en (fila, col) de la grilla del motor simulado."""
    cuerpo = {"medio": "avion", "xy_5345": [_xy(fila, col), _xy(fila, col + 1)]} | datos
    return servidor.pedir(f"/api/corridas/{id_}/intervenciones", {"tipo": "descarga", "datos": cuerpo})


def test_estado_informa_los_medios_aereos(servidor):
    c = servidor.pedir("/api/estado")[1]["combate"]
    assert c["medios"] == ["avion", "helicoptero"] and c["productos"] == ["agua", "retardante"]
    p = c["parametros"]
    assert p["medios"]["avion"]["largo_m"] == 150.0 and p["medios"]["helicoptero"]["max_por_hora"] == 16
    assert p["productos"]["agua"]["dura_h"] == 1 and p["productos"]["retardante"]["dura_h"] is None
    assert p["horas_vuelo_utc"] == [11, 22] and p["intensidad_aereo_kw_m"] == 3500.0


def test_descargas_en_pausa(servidor):
    C = LADO / 2                                          # el foco; el fuego de juguete avanza 3 celdas por hora
    id_ = _crear(servidor, horas=10, t_inicio_utc="2026-01-01T12:00:00Z")
    _pausar_en(servidor, id_, 4)                          # radio 12: el borde sur está en la fila C + 12

    # mal pedidas: 422 con el motivo
    for datos, texto in (({"medio": "dron", "xy_5345": [_xy(60, 40), _xy(60, 41)]}, "avion"),
                         ({"medio": "avion", "producto": "espuma", "xy_5345": [_xy(60, 40), _xy(60, 41)]}, "agua"),
                         ({"medio": "avion", "xy_5345": [_xy(60, 40)]}, "at least 2"),
                         ({"medio": "avion", "xy_5345": [_xy(60, 40), _xy(60, 40)]}, "mismo lugar"),
                         ({"medio": "avion", "xy_5345": [_xy(60, 40), _xy(60, 41)], "lonlat": [[0, 0], [1, 1]]}, "uno de los dos"),
                         ({"medio": "avion", "lonlat": [[-60.0, -30.0], [-60.0, -30.1]]}, "fuera del dominio")):
        codigo, r = servidor.pedir(f"/api/corridas/{id_}/intervenciones", {"tipo": "descarga", "datos": datos})
        assert codigo == 422 and "descarga aérea" in r["detail"] and texto in r["detail"], r

    # delante del fuego (4 filas al sur del borde), con agua: en grados, como las manda la pantalla
    fila = C + 16.5
    codigo, a = servidor.pedir(f"/api/corridas/{id_}/intervenciones",
                               {"tipo": "descarga", "datos": {"medio": "avion", "lonlat": _lonlat([_xy(fila, C - 3), _xy(fila, C - 2)])}})
    assert codigo == 200 and a["estado"] == "aceptada" and a["t_vigor_min"] == 240.0, a
    d = a["entrada"]["datos"]
    assert a["entrada"]["tipo"] == "descarga" and d["medio"] == "avion" and d["producto"] == "agua"
    assert d["celdas_mojadas"] == 5 and d["celdas_frenadas"] == 0 and d["vence_min"] == 300.0 and d["largo_m"] == 150.0
    assert abs(d["xy_fin_5345"][0] - (d["xy_5345"][0][0] + 150.0)) < 0.5 and abs(d["xy_fin_5345"][1] - d["xy_5345"][0][1]) < 0.5
    # sobre el borde sur del fuego, con retardante: frena lo que arde
    codigo, b = _descargar(servidor, id_, C + 12.5, C - 2, producto="retardante")
    assert codigo == 200 and b["estado"] == "aceptada" and b["entrada"]["datos"]["celdas_frenadas"] > 0, b
    assert b["entrada"]["datos"]["vence_min"] is None
    # lejos de todo (ya quemado: el foco): rechazada, y no entra en la bitácora
    codigo, c = _descargar(servidor, id_, C + 0.5, C - 2, medio="helicoptero")
    assert codigo == 200 and c["estado"] == "rechazada" and c["entrada"] is None and "no toca fuego" in c["motivo"], c

    # las franjas para el mapa
    codigo, fc = servidor.pedir(f"/api/corridas/{id_}/descargas.geojson")
    assert codigo == 200 and [f["properties"]["producto"] for f in fc["features"]] == ["agua", "retardante"]
    f0 = fc["features"][0]
    assert f0["geometry"]["type"] == "Polygon" and len(f0["geometry"]["coordinates"][0]) == 5
    assert f0["properties"]["estado"] == "aceptada" and f0["properties"]["n"] == a["n"] and f0["properties"]["celdas_mojadas"] == 5
    assert "xy_5345" not in f0["properties"]
    lons = [p[0] for p in f0["geometry"]["coordinates"][0]]; lats = [p[1] for p in f0["geometry"]["coordinates"][0]]
    assert 0.0012 < max(lons) - min(lons) < 0.002 and 0.0001 < max(lats) - min(lats) < 0.0004      # unos 150 × 20 m

    # la línea como imagen: 5 celdas de agua y las de retardante
    assert _pixeles(servidor, id_, 4) == 5 + b["entrada"]["datos"]["celdas_frenadas"] + b["entrada"]["datos"]["celdas_mojadas"]

    servidor.pedir(f"/api/corridas/{id_}/reanudar", {})
    d = _esperar(servidor, id_, FINALES)
    assert d["estado"] == "terminada" and d["bitacora_integra"] is True
    assert [e["tipo"] for e in d["bitacora"]] == ["pausa", "descarga", "descarga", "reanudacion"]
    h = {x["h"]: x for x in d["combate"]}
    assert h[4]["celdas_agua"] == 5 and h[4]["descargas"] == 2 and h[5]["vencidas_hora"] == 5 and h[5]["celdas_agua"] == 0
    res = d["resultados"]["combate"]
    assert len(res["descargas"]) == 2 and res["vencidas"] == 5 and res["celdas_linea_final"] == h[9]["celdas_linea"] > 0
    assert _pixeles(servidor, id_, 4) > _pixeles(servidor, id_, 6) == res["celdas_linea_final"]    # el agua ya se secó

    # reproducción y exportación
    codigo, r = servidor.pedir(f"/api/corridas/{id_}/reproducir", {"iniciar": True})
    assert codigo == 201, r
    d2 = _esperar(servidor, r["corridas"][0]["id"], FINALES)
    assert d2["resultados"]["reproduccion"]["cadena_igual"] is True
    g = servidor.app.state.gestor
    for nombre in ("t_llegada_parcial.npy", "combate_parcial.npy"):
        assert np.array_equal(np.load(g.obtener(id_).carpeta / nombre), np.load(g.obtener(d2["id"]).carpeta / nombre), equal_nan=True)
    codigo, crudo = servidor.pedir(f"/api/corridas/{id_}/exportar")
    z = zipfile.ZipFile(io.BytesIO(crudo))
    nombres = {n.split("/", 1)[1] for n in z.namelist()}
    assert {"descargas.geojson", "combate_parcial.npy", "cortafuegos.geojson"} <= nombres
    assert len(json.loads(z.read(f"{id_}/descargas.geojson"))["features"]) == 2


def test_descargas_de_noche_se_rechazan(servidor):
    id_ = _crear(servidor, horas=6, t_inicio_utc="2026-01-01T22:00:00Z")          # las 19 h de Argentina: ya no vuelan
    _pausar_en(servidor, id_, 2)
    codigo, r = _descargar(servidor, id_, LADO / 2 + 10.5, LADO / 2 - 2)
    assert codigo == 200 and r["estado"] == "rechazada" and "de día" in r["motivo"] and r["entrada"] is None, r
    assert servidor.pedir(f"/api/corridas/{id_}/descargas.geojson")[1]["features"] == []
    servidor.pedir(f"/api/corridas/{id_}/detener", {})
    d = _esperar(servidor, id_, FINALES)
    assert "combate" not in d["resultados"] and d["combate"] == []                 # una descarga rechazada no enciende el combate
