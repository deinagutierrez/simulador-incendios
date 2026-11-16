"""Pruebas del servidor para las intervenciones (fase F5, contrato 1.5 §4.2), con el motor simulado.

Cortafuegos al crear la corrida (en grados), intervenciones en pausa con su `ref`, bitácora en vivo, pausa con hora objetivo,
grupo "ambos" pausado en la misma hora, reproducción desde la bitácora, `cortafuegos.geojson` y exportación. Levantan el
servidor de verdad en un puerto libre; no usan internet y tardan segundos.
"""
from __future__ import annotations

import io
import json
import sys
import threading
import time
import zipfile
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from servidor.corridas import Gestor          # noqa: E402
from servidor.trazos import iv                # noqa: E402
from test_servidor import FINALES, Servidor   # noqa: E402

PUNTO = {"lon": -65.55, "lat": -32.64}
RES = 30.0
LADO = 60


def _grilla() -> tuple[float, float]:
    """xmin e ymax de la grilla del motor simulado con ignición en PUNTO (la misma cuenta que proceso_simulado.py)."""
    from pyproj import Transformer
    x, y = Transformer.from_crs("EPSG:4326", "EPSG:5345", always_xy=True).transform(PUNTO["lon"], PUNTO["lat"])
    return round((x - LADO * RES / 2) / RES) * RES, round((y + LADO * RES / 2) / RES) * RES


XMIN, YMAX = _grilla()


def xy(fila: float, col: float) -> list[float]:
    """Centro de una celda (fila, columna) de la grilla del motor simulado, en EPSG:5345."""
    return [XMIN + (col + 0.5) * RES, YMAX - (fila + 0.5) * RES]


def lonlat(puntos) -> list[list[float]]:
    from pyproj import Transformer
    t = Transformer.from_crs("EPSG:5345", "EPSG:4326", always_xy=True)
    return [list(t.transform(x, y)) for x, y in puntos]


C = LADO / 2                                    # el foco
SUR = [xy(C + 25, 0), xy(C + 25, LADO - 1)]     # de borde a borde, 25 celdas al sur: el fuego llega pasadas las 8 h
NORTE = [xy(C - 5, C + 0.3), xy(C - 28, C + 0.3)]   # sale de lo quemado a las 6 h (radio 18 celdas) hacia el norte
QUEMADO = [xy(C - 2, C - 2), xy(C + 2, C + 2)]      # entero adentro de lo quemado a las 6 h


@pytest.fixture(scope="module")
def servidor(tmp_path_factory):
    s = Servidor(tmp_path_factory.mktemp("corridas_f5"))
    yield s
    s.cerrar()


def _simulada(servidor, horas=30, s_por_hora=0.03, iniciar=True, **extra) -> str:
    codigo, r = servidor.pedir("/api/corridas", {"motor": "simulado", "horas": horas, "iniciar": iniciar, "ignicion": [PUNTO],
                                                 "simulado": {"s_por_hora": s_por_hora, "lado": LADO}, **extra})
    assert codigo == 201, r
    return r["corridas"][0]["id"]


def _huella(servidor, id_: str) -> np.ndarray:
    return np.load(servidor.app.state.gestor.obtener(id_).carpeta / "t_llegada_parcial.npy")


def _corrida_json(servidor, id_: str) -> dict:
    return json.loads((servidor.app.state.gestor.obtener(id_).carpeta / "corrida.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------- pedidos inválidos
def test_estado_trae_las_reglas_de_las_intervenciones(servidor):
    codigo, e = servidor.pedir("/api/estado")
    assert codigo == 200 and e["intervenciones"]["anchos_m"] == [3, 6, 10, 15, 25]
    assert e["intervenciones"]["vel_max_kmh"] == 216 and e["intervenciones"]["espera_s"] == 30


@pytest.mark.parametrize("cortafuego, texto", [
    ({"ancho_m": 7, "lonlat": lonlat(SUR)}, "ancho_m"),
    ({"ancho_m": 10, "lonlat": lonlat(SUR)[:1]}, "lonlat"),
    ({"ancho_m": 10, "lonlat": lonlat(SUR), "xy_5345": SUR}, "uno de los dos"),
    ({"ancho_m": 10}, "uno de los dos"),
    ({"ancho_m": 10, "lonlat": [[-60.0, -32.6], [-60.1, -32.6]]}, "fuera del dominio"),
    ({"ancho_m": 10, "xy_5345": [SUR[0], SUR[0]]}, "un solo punto"),
    ({"ancho_m": 10, "lonlat": lonlat(SUR), "color": "rojo"}, "color"),
])
def test_cortafuegos_invalidos_al_crear(servidor, cortafuego, texto):
    codigo, r = servidor.pedir("/api/corridas", {"motor": "simulado", "horas": 3, "ignicion": [PUNTO], "cortafuegos": [cortafuego]})
    assert codigo == 422 and texto in json.dumps(r, ensure_ascii=False), r


def test_hora_de_inicio_con_minutos_se_rechaza(servidor):
    codigo, r = servidor.pedir("/api/corridas", {"motor": "simulado", "horas": 3, "t_inicio_utc": "2026-01-01T12:30:00Z"})
    assert codigo == 422 and "hora en punto" in r["detail"] and "t_inicio_utc" in r["detail"]
    codigo, r = servidor.pedir("/api/corridas", {"motor": "v4.0", "evento": "SL-2024-LASLAGUNAS", "horas": 3,
                                                 "t_inicio_utc": "2024-09-19T16:00:05Z"})
    assert codigo == 422 and "hora en punto" in r["detail"]
    assert servidor.pedir("/api/corridas", {"motor": "simulado", "horas": 3, "t_inicio_utc": "2026-01-01T12:00:00Z"})[0] == 201


@pytest.mark.parametrize("cuerpo", [
    {"tipo": "cortafuego"},
    {"tipo": "riego", "datos": {}},
    {"tipo": "cortafuego", "datos": {"ancho_m": 12, "xy_5345": SUR}},
    {"tipo": "cortafuego", "datos": {"ancho_m": 10.5, "xy_5345": SUR}},
    {"tipo": "viento_manual", "datos": {"vel_kmh": 300, "dir_desde": 90}},
    {"tipo": "viento_manual", "datos": {"vel_kmh": 30, "dir_desde": 361}},
    {"tipo": "viento_manual", "datos": {"vel_kmh": 30}},
    {"tipo": "viento_manual", "datos": {"modo": "pronostico", "vel_kmh": 30}},
    {"tipo": "viento_manual", "datos": {"modo": "otro"}},
    {"tipo": "viento_manual", "datos": {"vel_kmh": 30, "dir_desde": 90}, "extra": 1},
])
def test_intervenciones_invalidas_dan_422(servidor, cuerpo):
    id_ = _simulada(servidor, horas=200, s_por_hora=0.05)
    assert servidor.pedir(f"/api/corridas/{id_}/pausar", {})[0] == 200
    servidor.esperar(id_, "pausada")
    codigo, r = servidor.pedir(f"/api/corridas/{id_}/intervenciones", cuerpo)
    assert codigo == 422, r
    servidor.pedir(f"/api/corridas/{id_}/detener", {})
    fin = servidor.esperar(id_, "detenida")
    assert [b["tipo"] for b in fin["bitacora"]] == ["pausa", "detencion"]             # no entró nada


def test_intervenir_fuera_de_pausa_da_409(servidor):
    viento = {"tipo": "viento_manual", "datos": {"vel_kmh": 20, "dir_desde": 90}}
    creada = _simulada(servidor, horas=3, iniciar=False)
    assert servidor.pedir(f"/api/corridas/{creada}/intervenciones", viento)[0] == 409
    id_ = _simulada(servidor, horas=200, s_por_hora=0.05)
    servidor.esperar(id_, "corriendo")
    codigo, r = servidor.pedir(f"/api/corridas/{id_}/intervenciones", viento)
    assert codigo == 409 and "pausa" in r["detail"]
    assert servidor.pedir("/api/corridas/no-existe/intervenciones", viento)[0] == 404
    assert servidor.pedir(f"/api/corridas/{id_}/pausar", {"en_t_sim_min": -5})[0] == 422
    servidor.pedir(f"/api/corridas/{id_}/detener", {})
    servidor.esperar(id_, "detenida")


# ---------------------------------------------------------------------- cortafuegos antes de iniciar
def test_cortafuegos_al_crear_en_grados(servidor):
    con = _simulada(servidor, horas=12, cortafuegos=[{"ancho_m": 10, "suelo_mineral": True, "lonlat": lonlat(SUR)}])
    sin = _simulada(servidor, horas=12)
    fin, fin_sin = servidor.esperar(con, "terminada"), servidor.esperar(sin, "terminada")

    c = _corrida_json(servidor, con)
    trazo = c["configuracion"]["cortafuegos"][0]
    assert trazo["ancho_m"] == 10 and trazo["suelo_mineral"] is True
    assert np.allclose(trazo["xy_5345"], SUR, atol=0.01)                   # de grados a EPSG:5345, a 0,01 m
    assert trazo["longitud_dibujada_m"] == pytest.approx((LADO - 1) * RES, abs=0.05)
    assert c["bitacora_raiz"] == iv.raiz(c) and fin["bitacora_raiz"] == c["bitacora_raiz"]
    assert fin["cortafuegos_iniciales"] == c["configuracion"]["cortafuegos"]
    assert c["resultados"]["cortafuegos_iniciales"][0]["estado"] == "aceptada"

    # el fuego no pasa al sur de la línea: menos superficie que sin cortafuego, y nada debajo de la fila de la línea
    assert fin["resultados"]["ha_final"] < fin_sin["resultados"]["ha_final"]
    assert not np.isfinite(_huella(servidor, con)[int(C) + 26:, :]).any()
    assert np.isfinite(_huella(servidor, sin)[int(C) + 26:, :]).any()

    codigo, g = servidor.pedir(f"/api/corridas/{con}/cortafuegos.geojson")
    assert codigo == 200 and len(g["features"]) == 1
    f = g["features"][0]
    assert f["properties"]["origen"] == "inicial" and f["properties"]["estado"] == "aceptada"
    assert f["properties"]["longitud_dibujada_m"] == trazo["longitud_dibujada_m"] and "xy_5345" not in f["properties"]
    assert np.allclose(f["geometry"]["coordinates"], lonlat(SUR), atol=1e-6)           # en grados


# ---------------------------------------------------------------------- en pausa: ref, bitácora en vivo, reproducción
@pytest.fixture(scope="module")
def con_intervenciones(servidor):
    """Una corrida pausada a las 6 h con hora objetivo, con tres intervenciones aceptadas o recortadas y una rechazada."""
    id_ = _simulada(servidor, horas=24, s_por_hora=0.03, iniciar=False)
    assert servidor.pedir(f"/api/corridas/{id_}/iniciar", {})[0] == 200
    codigo, r = servidor.pedir(f"/api/corridas/{id_}/pausar", {"en_t_sim_min": 330})      # se redondea a la hora: 360
    assert codigo == 200 and r["pausa_en_t_sim_min"] == 360
    pausa = servidor.esperar(id_, "pausada")
    vivo = {"pausa": pausa}

    vivo["sur"] = servidor.pedir(f"/api/corridas/{id_}/intervenciones",
                                 {"tipo": "cortafuego", "datos": {"ancho_m": 6, "lonlat": lonlat(SUR)}})
    vivo["norte"] = servidor.pedir(f"/api/corridas/{id_}/intervenciones",
                                   {"tipo": "cortafuego", "datos": {"ancho_m": 25, "suelo_mineral": True, "xy_5345": NORTE}})
    vivo["quemado"] = servidor.pedir(f"/api/corridas/{id_}/intervenciones",
                                     {"tipo": "cortafuego", "datos": {"ancho_m": 3, "xy_5345": QUEMADO}})
    # dos a la vez: cada respuesta vuelve con su propio `ref`
    respuestas = {}

    def mandar(nombre, datos):
        respuestas[nombre] = servidor.pedir(f"/api/corridas/{id_}/intervenciones", {"tipo": "viento_manual", "datos": datos})

    hilos = [threading.Thread(target=mandar, args=("viento", {"vel_kmh": 40, "dir_desde": 360})),
             threading.Thread(target=mandar, args=("pronostico", {"modo": "pronostico"}))]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(60)
    vivo |= respuestas
    vivo["detalle_en_pausa"] = servidor.detalle(id_)
    vivo["geojson_en_pausa"] = servidor.pedir(f"/api/corridas/{id_}/cortafuegos.geojson")[1]
    assert servidor.pedir(f"/api/corridas/{id_}/reanudar", {})[0] == 200
    vivo["fin"] = servidor.esperar(id_, "terminada")
    return id_, vivo


def test_intervenciones_en_pausa(servidor, con_intervenciones):
    id_, v = con_intervenciones
    assert v["pausa"]["pausa_t_sim_min"] == 360 and v["pausa"]["ultima_hora"]["h"] == 6

    codigo, sur = v["sur"]
    assert codigo == 200 and sur["aviso"] == "intervencion" and sur["estado"] == "aceptada" and sur["n"] == 2
    assert sur["ref"] and sur["t_vigor_min"] == 360
    e = sur["entrada"]
    assert e["tipo"] == "cortafuego" and e["n"] == 2 and e["datos"]["ancho_m"] == 6 and len(e["hash"]) == 64
    assert np.allclose(e["datos"]["xy_5345"], SUR, atol=0.01) and e["datos"]["celdas"] == LADO

    codigo, norte = v["norte"]
    assert codigo == 200 and norte["estado"] == "recortada" and norte["entrada"]["datos"]["celdas_recortadas"] > 0
    d = norte["entrada"]["datos"]
    assert d["longitud_aplicada_m"] < d["longitud_dibujada_m"] and d["suelo_mineral"] is True

    codigo, quemado = v["quemado"]
    assert codigo == 200 and quemado["estado"] == "rechazada" and quemado["n"] is None and quemado["entrada"] is None
    assert "quemadas" in quemado["motivo"]

    (c1, viento), (c2, pron) = v["viento"], v["pronostico"]
    assert c1 == c2 == 200 and viento["ref"] != pron["ref"]
    assert viento["entrada"]["datos"] == {"vel_kmh": 40, "dir_desde": 0, "efecto": "ninguno"}       # 360 → 0
    assert pron["entrada"]["datos"]["modo"] == "pronostico"
    assert {viento["n"], pron["n"]} == {4, 5}


def test_bitacora_en_vivo_y_al_terminar(servidor, con_intervenciones):
    id_, v = con_intervenciones
    en_pausa, fin = v["detalle_en_pausa"], v["fin"]
    assert en_pausa["estado"] == "pausada"
    assert [b["tipo"] for b in en_pausa["bitacora"]] == ["pausa", "cortafuego", "cortafuego", "viento_manual", "viento_manual"]
    assert en_pausa["bitacora_integra"] is True and en_pausa["bitacora_raiz"] == fin["bitacora_raiz"]
    assert fin["bitacora"][:5] == en_pausa["bitacora"]                            # lo de en vivo es lo que queda
    assert [b["tipo"] for b in fin["bitacora"]][5:] == ["reanudacion"]
    assert iv.verificar_cadena(fin["bitacora_raiz"], fin["bitacora"]) == (True, None) and fin["bitacora_integra"] is True
    disco = [json.loads(x) for x in (servidor.app.state.gestor.obtener(id_).carpeta / "bitacora.jsonl")
             .read_text(encoding="utf-8").splitlines()]
    assert disco == fin["bitacora"]

    g = v["geojson_en_pausa"]
    assert [(f["properties"]["origen"], f["properties"]["n"], f["properties"]["estado"]) for f in g["features"]] == \
        [("intervencion", 2, "aceptada"), ("intervencion", 3, "recortada")]
    assert g["features"][1]["properties"]["longitud_aplicada_m"] < g["features"][1]["properties"]["longitud_dibujada_m"]
    assert np.allclose(g["features"][0]["geometry"]["coordinates"], lonlat(SUR), atol=1e-6)

    codigo, paquete = servidor.pedir(f"/api/corridas/{id_}/exportar")
    assert codigo == 200
    z = zipfile.ZipFile(io.BytesIO(paquete))
    assert f"{id_}/bitacora.jsonl" in z.namelist() and f"{id_}/cortafuegos.geojson" in z.namelist()
    assert len(json.loads(z.read(f"{id_}/cortafuegos.geojson"))["features"]) == 2
    assert json.loads(z.read(f"{id_}/corrida.json"))["bitacora"] == fin["bitacora"]


def test_reproducir_desde_la_bitacora(servidor, con_intervenciones):
    id_, v = con_intervenciones
    codigo, r = servidor.pedir(f"/api/corridas/{id_}/reproducir", {"iniciar": True})
    assert codigo == 201, r
    otra = r["corridas"][0]
    assert otra["reproduccion_de"] == id_ and otra["id"] != id_ and otra["grupo"] is None
    fin = servidor.esperar(otra["id"], "terminada")

    original, copia = _corrida_json(servidor, id_), _corrida_json(servidor, otra["id"])
    for k in ("formato", "motor", "configuracion", "programa", "simulado"):
        assert copia[k] == original[k], k
    assert copia["reproduccion"]["de"] == id_ and copia["reproduccion"]["raiz"] == original["bitacora_raiz"]
    rep = fin["resultados"]["reproduccion"]
    assert rep["cadena_igual"] is True and rep["raiz_igual"] is True and rep["sin_aplicar"] == []
    assert [b["hash"] for b in fin["bitacora"]] == [b["hash"] for b in v["fin"]["bitacora"]]
    assert np.array_equal(_huella(servidor, id_), _huella(servidor, otra["id"]), equal_nan=True)     # 0 celdas distintas

    assert servidor.pedir("/api/corridas/no-existe/reproducir", {})[0] == 404
    larga = _simulada(servidor, horas=200, s_por_hora=0.05)
    servidor.esperar(larga, "corriendo")
    assert servidor.pedir(f"/api/corridas/{larga}/reproducir", {})[0] == 409            # en marcha
    servidor.pedir(f"/api/corridas/{larga}/detener", {})
    servidor.esperar(larga, "detenida")


def test_una_reproduccion_no_acepta_intervenciones(servidor, con_intervenciones):
    id_, _ = con_intervenciones
    codigo, r = servidor.pedir(f"/api/corridas/{id_}/reproducir", {})
    assert codigo == 201
    otra = r["corridas"][0]["id"]
    assert servidor.detalle(otra)["estado"] == "creada"                                 # sin `iniciar` no arranca
    assert servidor.pedir(f"/api/corridas/{otra}/iniciar", {})[0] == 200
    assert servidor.pedir(f"/api/corridas/{otra}/pausar", {"en_t_sim_min": 720})[0] == 200
    servidor.esperar(otra, "pausada")
    codigo, r = servidor.pedir(f"/api/corridas/{otra}/intervenciones", {"tipo": "viento_manual", "datos": {"modo": "pronostico"}})
    assert codigo == 409 and "reproducción" in r["detail"]
    servidor.pedir(f"/api/corridas/{otra}/reanudar", {})
    fin = servidor.esperar(otra, "terminada")
    assert fin["resultados"]["reproduccion"]["cadena_igual"] is True        # la pausa a mano no entra en la cadena


# ---------------------------------------------------------------------- grupo "ambos" (con dos corridas simuladas)
def _grupo(servidor, s_por_hora=(0.1, 0.3), horas=200) -> tuple[str, list[str]]:
    g = servidor.app.state.gestor
    grupo = f"G-prueba{len(g.corridas)}"
    pedido = {"motor": "simulado", "horas": horas, "ignicion": [PUNTO]}
    ids = []
    for s in s_por_hora:
        c = g._crear_una("simulado", pedido | {"simulado": {"s_por_hora": s, "lado": LADO}}, grupo)
        ids.append(c.id)
    for i in ids:
        assert servidor.pedir(f"/api/corridas/{i}/iniciar", {})[0] == 200
    return grupo, ids


def test_grupo_se_pausa_en_la_misma_hora_y_recibe_la_misma_intervencion(servidor):
    grupo, ids = _grupo(servidor)
    for i in ids:
        servidor.esperar(i, "corriendo")
    time.sleep(0.3)               # que se separen (una va 3 veces más rápido), sin que el fuego llegue a la línea SUR (8 h)
    codigo, r = servidor.pedir(f"/api/grupos/{grupo}/pausar", {})
    assert codigo == 200 and r["grupo"] == grupo and r["en_t_sim_min"] % 60 == 0
    a, b = (servidor.esperar(i, "pausada") for i in ids)
    limite = time.monotonic() + 30
    while not (a["estado"] == b["estado"] == "pausada" and a["pausa_t_sim_min"] == b["pausa_t_sim_min"]):
        assert time.monotonic() < limite, (a["pausa_t_sim_min"], b["pausa_t_sim_min"])
        time.sleep(0.05)
        a, b = (servidor.detalle(i) for i in ids)
    t = a["pausa_t_sim_min"]
    assert t >= r["en_t_sim_min"] and a["ultima_hora"]["h"] == b["ultima_hora"]["h"] == t // 60

    codigo, r = servidor.pedir(f"/api/grupos/{grupo}/intervenciones",
                               {"tipo": "cortafuego", "datos": {"ancho_m": 15, "lonlat": lonlat(SUR)}})
    assert codigo == 200 and r["t_sim_min"] == t and sorted(x["id"] for x in r["respuestas"]) == sorted(ids)
    assert all(x["aviso"]["estado"] in ("aceptada", "recortada") for x in r["respuestas"]), (t, r)
    assert r["respuestas"][0]["aviso"]["entrada"]["datos"]["xy_5345"] == r["respuestas"][1]["aviso"]["entrada"]["datos"]["xy_5345"]

    # con una sola en pausa, el grupo no interviene
    assert servidor.pedir(f"/api/corridas/{ids[0]}/reanudar", {})[0] == 200
    codigo, r = servidor.pedir(f"/api/grupos/{grupo}/intervenciones", {"tipo": "viento_manual", "datos": {"modo": "pronostico"}})
    assert codigo == 409 and "no está en pausa" in r["detail"]

    # con hora pedida: las dos pausan ahí (la que estaba en pausa se reanuda hasta esa hora)
    objetivo = t + 600
    codigo, r = servidor.pedir(f"/api/grupos/{grupo}/pausar", {"en_t_sim_min": objetivo})
    assert codigo == 200 and r["en_t_sim_min"] >= objetivo
    for i in ids:
        assert servidor.esperar(i, "pausada")["pausa_t_sim_min"] == r["en_t_sim_min"]
    for i in ids:
        servidor.pedir(f"/api/corridas/{i}/detener", {})
    for i in ids:
        fin = servidor.esperar(i, "detenida")
        tipos = [b["tipo"] for b in fin["bitacora"]]
        assert tipos[:2] == ["pausa", "cortafuego"] and tipos[-1] == "detencion"
    assert servidor.pedir("/api/grupos/no-existe/pausar", {})[0] == 404
    assert servidor.pedir(f"/api/grupos/{grupo}/pausar", {})[0] == 409            # ya no están en marcha


# ---------------------------------------------------------------------- el gestor, sin HTTP
def test_la_bitacora_queda_si_el_proceso_se_cae(tmp_path):
    g = Gestor(tmp_path, permitir_simulado=True)
    c = g.crear({"motor": "simulado", "horas": 20, "simulado": {"s_por_hora": 0.05, "fallar_en_h": 4}})[0]
    g.iniciar(c.id)
    g.pausar(c.id, 120)
    limite = time.monotonic() + 30
    while c.estado != "pausada":
        assert time.monotonic() < limite and c.estado not in FINALES
        time.sleep(0.05)
    r = g.intervenir(c.id, {"tipo": "viento_manual", "datos": {"vel_kmh": 10, "dir_desde": 45}})
    assert r["estado"] == "aceptada"
    g.reanudar(c.id)
    while c.estado not in FINALES:
        assert time.monotonic() < limite
        time.sleep(0.05)
    assert c.estado == "error"
    d = c.detalle()
    assert [b["tipo"] for b in d["bitacora"]] == ["pausa", "viento_manual", "reanudacion"] and d["bitacora_integra"] is True
    # y al volver a arrancar el servidor, también (de bitacora.jsonl y de los avisos guardados en eventos.jsonl)
    otra = Gestor(tmp_path, permitir_simulado=True).obtener(c.id)
    assert otra.detalle()["bitacora"] == d["bitacora"] and otra.bitacora_viva == d["bitacora"]
