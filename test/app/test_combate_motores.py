"""El combate común con los motores reales, por el servidor (contrato 1.6; decisión D-E3-36).

Las Lagunas 2024 en modo "ambos" (v4.0 y v3.1 librev2), 8 horas: una dotación desde el inicio y otra despachada al grupo en
la pausa de la hora 3, junto con dos descargas de avión (agua y retardante). Comprueba que los dos motores reciben las mismas
intervenciones y arman su línea con el mismo método, que el combate cambia el resultado, y que la reproducción desde la
bitácora da 0 celdas distintas en la huella y en la línea
(comparación A: es la garantía del combate, que no tiene corrida offline equivalente). Unos 40 segundos; sin red.

Que una corrida SIN combate siga dando lo mismo que la corrida offline lo comprueba, como siempre,
test_servidor.py::test_modo_ambos_por_el_servidor_da_lo_mismo_que_la_corrida_offline.
"""
from __future__ import annotations

import shutil
import sys
import time
import uuid
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_servidor import FINALES, Servidor   # noqa: E402

EVENTO = "SL-2024-LASLAGUNAS"
HORAS = 8
TOPE_S = 600


@pytest.fixture(scope="module")
def servidor():
    # dentro del repositorio: v4.0 solo lee insumos del repositorio o de la carpeta de datos (resultados/ no se versiona)
    carpeta = REPO / "resultados" / "app" / f"_prueba_combate_{uuid.uuid4().hex[:8]}"
    carpeta.mkdir(parents=True)
    s = Servidor(carpeta)
    yield s
    s.cerrar()
    shutil.rmtree(carpeta, ignore_errors=True)


def _esperar(servidor, ids, estados) -> list[dict]:
    limite = time.monotonic() + TOPE_S
    while True:
        ds = [servidor.pedir(f"/api/corridas/{i}")[1] for i in ids]
        if all(d["estado"] in estados for d in ds):
            return ds
        assert not any(d["estado"] == "error" for d in ds), [d.get("error") or d.get("motivo") for d in ds]
        assert time.monotonic() < limite, [d["estado"] for d in ds]
        time.sleep(0.2)


def _distintas(a: np.ndarray, b: np.ndarray) -> int:
    return int((~((a == b) | (np.isnan(a) & np.isnan(b)))).sum())


def test_combate_en_los_dos_motores_y_reproduccion(servidor):
    gestor = servidor.app.state.gestor
    pedido = {"motor": "ambos", "evento": EVENTO, "hipotesis": 1, "horas": HORAS}

    # referencia sin combate
    codigo, r = servidor.pedir("/api/corridas", pedido | {"iniciar": True})
    assert codigo == 201, r
    libres = _esperar(servidor, [x["id"] for x in r["corridas"]], FINALES)
    for d in libres:
        assert d["estado"] == "terminada" and "combate" not in d["resultados"] and d["combate"] == []
        assert not (gestor.obtener(d["id"]).carpeta / "combate_parcial.npy").exists()
    ha_libre = {d["motor"]: d["resultados"]["ha_final"] for d in libres}

    # con combate: 20 bomberos desde el inicio (llegan a la hora) y 150 más despachados en la pausa de la hora 3
    codigo, r = servidor.pedir("/api/corridas", pedido | {"iniciar": True, "dotaciones": [{"bomberos": 20, "llegada_min": 60}]})
    assert codigo == 201, r
    ids, grupo = [x["id"] for x in r["corridas"]], r["corridas"][0]["grupo"]
    assert servidor.pedir(f"/api/grupos/{grupo}/pausar", {"en_t_sim_min": 180})[0] == 200
    _esperar(servidor, ids, {"pausada"})
    codigo, r = servidor.pedir(f"/api/grupos/{grupo}/intervenciones",
                               {"tipo": "dotacion", "datos": {"bomberos": 150, "llegada_min": 30, "prioridad": "cabeza"}})
    assert codigo == 200, r
    avisos = {x["motor"]: x["aviso"] for x in r["respuestas"]}
    assert set(avisos) == {"v4.0", "v3.1-librev2"}
    for a in avisos.values():                           # el mismo despacho, con la misma cuenta, en los dos motores
        assert a["estado"] == "aceptada" and a["t_vigor_min"] == 210.0
        assert a["entrada"]["datos"] == {"bomberos": 150, "llegada_min": 30, "prioridad": "cabeza", "dotacion": 2,
                                         "tasa_m_h": 3000.0, "desde_min": 210.0}
    # dos descargas de avión al grupo (la pausa cae de día), una con agua y otra con retardante, delante del fuego de v3.1,
    # que es el más grande: 4 y 8 celdas al sur de su borde sur. Cada motor las aplica sobre su propio fuego (una descarga
    # sobre celdas que en un motor ya tienen línea o ya se apagaron se rechaza en ese motor: por eso van delante del fuego)
    v31_id = next(i for i in ids if gestor.obtener(i).motor.startswith("v3.1"))
    g = gestor.obtener(v31_id).listo["grilla"]
    quemado = np.isfinite(np.load(gestor.obtener(v31_id).carpeta / "t_llegada_parcial.npy"))
    fila_sur = int(np.flatnonzero(quemado.any(axis=1)).max())
    col = int(np.flatnonzero(quemado[fila_sur]).mean())
    centro = lambda fila, c: [g["xmin"] + (c + 0.5) * g["res"], g["ymax"] - (fila + 0.5) * g["res"]]  # noqa: E731
    for producto, fila in (("agua", fila_sur + 4), ("retardante", fila_sur + 8)):
        codigo, r = servidor.pedir(f"/api/grupos/{grupo}/intervenciones",
                                   {"tipo": "descarga", "datos": {"medio": "avion", "producto": producto,
                                                                  "xy_5345": [centro(fila, col - 2), centro(fila, col - 1)]}})
        assert codigo == 200, r
        for x in r["respuestas"]:
            a = x["aviso"]
            assert a["estado"] in ("aceptada", "recortada"), (x["motor"], producto, a["motivo"])
            d = a["entrada"]["datos"]
            assert d["producto"] == producto and d["largo_m"] == 150.0 and d["celdas_mojadas"] + d["celdas_frenadas"] > 0
            assert d["vence_min"] == (240.0 if producto == "agua" else None)
        # la franja es la misma para los dos motores (el mismo punto de inicio y de fin, en EPSG:5345)
        assert len({str(x["aviso"]["entrada"]["datos"]["xy_fin_5345"]) for x in r["respuestas"]}) == 1
    for i in ids:
        assert servidor.pedir(f"/api/corridas/{i}/reanudar", {})[0] == 200
    con = _esperar(servidor, ids, FINALES)

    for d in con:
        motor, res = d["motor"], d["resultados"]
        assert d["estado"] == "terminada" and d["bitacora_integra"] is True, (motor, d.get("error"))
        assert [e["tipo"] for e in d["bitacora"]] == ["pausa", "dotacion", "descarga", "descarga", "reanudacion"]
        co = res["combate"]
        assert co["parametros"]["m_h_por_bombero"] == 20.0 and len(co["dotaciones"]) == 2 and len(co["descargas"]) == 2
        codigo, fc = servidor.pedir(f"/api/corridas/{d['id']}/descargas.geojson")
        assert codigo == 200 and [f["properties"]["producto"] for f in fc["features"]] == ["agua", "retardante"]
        assert co["linea_m"] > 0 and co["celdas_linea_final"] > 0 and co["escapes"] >= 0
        h = {x["h"]: x for x in d["combate"]}
        assert sorted(h) == list(range(len(h))) and h[0]["linea_m_hora"] == 0 and h[1]["linea_m_hora"] == 0
        # hora 2: la primera hora de trabajo de los 20 bomberos (400 m = 13 celdas, o todo el borde si es más chico)
        assert h[2]["bomberos"] == 20 and h[2]["celdas_nuevas"] == min(13, h[2]["frente_celdas"]) > 0
        assert res["ha_final"] < ha_libre[motor], (motor, res["ha_final"], ha_libre[motor])
        carpeta = gestor.obtener(d["id"]).carpeta
        huella, capas = np.load(carpeta / "t_llegada_parcial.npy"), np.load(carpeta / "combate_parcial.npy")
        assert capas.shape == (3,) + huella.shape
        en_pie = (capas[2] > 0) & np.isnan(capas[1])
        assert int(en_pie.sum()) == co["celdas_linea_final"]
        de_bomberos = (capas[2] == 1) & (capas[0] != 180.0)             # sin el agua que aseguraron (conserva el minuto 180)
        assert np.isfinite(huella[de_bomberos]).all()                   # la línea nueva está sobre celdas que el fuego alcanzó
        assert int((capas[2] == 3).sum()) > 0 and np.isnan(capas[1][capas[2] == 3]).all()      # el retardante sigue en pie
        agua = capas[2] == 2                                            # el agua que nadie aseguró se secó a la hora
        assert (capas[1][agua] == 240.0).all()
        codigo, png = servidor.pedir(f"/api/corridas/{d['id']}/combate.png?hora={HORAS}")
        assert codigo == 200 and png[:4] == b"\x89PNG"
    # v3.1 sigue con la contención encendida solo por el combate común, y su estado final lo refleja
    v31 = next(d for d in con if d["motor"].startswith("v3.1"))
    import rasterio
    with rasterio.open(gestor.obtener(v31["id"]).carpeta / "salida" / "estado_final.tif") as s:
        assert int((s.read(1) == 4).sum()) == v31["resultados"]["combate"]["celdas_linea_final"]      # 4 = CONTENIDA
    for d in con:                                       # lo que informó cada motor de sus descargas (para leer con -s)
        print(d["motor"], [{k: x[k] for k in ("producto", "celdas_mojadas", "celdas_frenadas", "celdas_intensas")}
                           for x in d["resultados"]["combate"]["descargas"]],
              {k: d["resultados"]["combate"][k] for k in ("vencidas", "brechas", "consolidadas", "escapes", "celdas_linea_final")})

    # reproducción desde la bitácora (comparación A): misma cadena, 0 celdas distintas en la huella y en la línea
    nuevos = []
    for i in ids:
        codigo, r = servidor.pedir(f"/api/corridas/{i}/reproducir", {"iniciar": True})
        assert codigo == 201, r
        nuevos.append(r["corridas"][0]["id"])
    for d, d2 in zip(con, _esperar(servidor, nuevos, FINALES)):
        rep = d2["resultados"]["reproduccion"]
        assert d2["estado"] == "terminada" and rep["cadena_igual"] is True and rep["sin_aplicar"] == [], (d["motor"], rep)
        a, b = gestor.obtener(d["id"]).carpeta, gestor.obtener(d2["id"]).carpeta
        assert _distintas(np.load(a / "t_llegada_parcial.npy"), np.load(b / "t_llegada_parcial.npy")) == 0, d["motor"]
        assert _distintas(np.load(a / "combate_parcial.npy"), np.load(b / "combate_parcial.npy")) == 0, d["motor"]
        assert d2["resultados"]["combate"]["celdas_linea_sha256"] == d["resultados"]["combate"]["celdas_linea_sha256"]
        assert d2["resultados"]["ha_final"] == d["resultados"]["ha_final"]
