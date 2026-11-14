"""Pruebas del servidor local (fase F2).

Levantan el servidor de verdad en un puerto libre de esta computadora y le hablan por HTTP, como lo hace el navegador.
Casi todas usan el motor simulado (un fuego de mentira) y tardan segundos. Una sola usa los motores reales: lanza por el
servidor 6 horas de Las Lagunas 2024 en modo "ambos" y compara cada huella con la corrida offline del motor (0 celdas
distintas). No usan internet.
"""
from __future__ import annotations

import json
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))

from servidor.app import crear_app                    # noqa: E402
from servidor.corridas import Gestor, escribir_json   # noqa: E402

FINALES = {"terminada", "detenida", "error", "interrumpida"}


class Servidor:
    def __init__(self, carpeta: Path):
        import uvicorn
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.puerto = s.getsockname()[1]
        self.base = f"http://127.0.0.1:{self.puerto}"
        self.app = crear_app(carpeta, permitir_simulado=True)
        self.uvicorn = uvicorn.Server(uvicorn.Config(self.app, host="127.0.0.1", port=self.puerto, log_level="warning"))
        self.hilo = threading.Thread(target=self.uvicorn.run, daemon=True)
        self.hilo.start()
        limite = time.monotonic() + 30
        while not self.uvicorn.started:
            assert time.monotonic() < limite, "el servidor no arrancó"
            time.sleep(0.05)

    def cerrar(self) -> None:
        self.uvicorn.should_exit = True
        self.hilo.join(60)

    def pedir(self, ruta: str, cuerpo: dict | None = None, encabezados: dict | None = None, metodo: str | None = None):
        """(código, respuesta). La respuesta es JSON ya leído, o bytes si no es JSON."""
        datos = None if cuerpo is None else json.dumps(cuerpo).encode("utf-8")
        pedido = urllib.request.Request(self.base + ruta, data=datos, method=metodo or ("POST" if cuerpo is not None else "GET"),
                                        headers={"Content-Type": "application/json", **(encabezados or {})})
        try:
            with urllib.request.urlopen(pedido, timeout=60) as r:
                codigo, crudo, tipo = r.status, r.read(), r.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            codigo, crudo, tipo = e.code, e.read(), e.headers.get("Content-Type", "")
        return codigo, (json.loads(crudo) if "json" in tipo else crudo)

    def crear(self, **pedido) -> dict:
        codigo, r = self.pedir("/api/corridas", pedido)
        assert codigo == 201, r
        return r["corridas"][0]

    def simulada(self, horas: int = 6, s_por_hora: float = 0.02, iniciar: bool = True, **simulado) -> str:
        return self.crear(motor="simulado", horas=horas, iniciar=iniciar, simulado={"s_por_hora": s_por_hora, **simulado})["id"]

    def detalle(self, id_: str) -> dict:
        codigo, r = self.pedir(f"/api/corridas/{id_}")
        assert codigo == 200, r
        return r

    def esperar(self, id_: str, estados, tope_s: float = 30) -> dict:
        estados = {estados} if isinstance(estados, str) else set(estados)
        limite = time.monotonic() + tope_s
        while True:
            d = self.detalle(id_)
            if d["estado"] in estados:
                return d
            assert d["estado"] not in FINALES, f"la corrida terminó en {d['estado']} y se esperaba {estados}: {d.get('error')}"
            assert time.monotonic() < limite, f"la corrida sigue en {d['estado']} después de {tope_s} s; se esperaba {estados}"
            time.sleep(0.05)

    def eventos(self, id_: str, desde: int = 0) -> list[dict]:
        """Lee el canal de avance hasta que el servidor lo cierra."""
        out = []
        with urllib.request.urlopen(f"{self.base}/api/corridas/{id_}/eventos?desde={desde}", timeout=60) as r:
            assert r.headers.get("Content-Type", "").startswith("text/event-stream")
            for linea in r:
                linea = linea.decode("utf-8").rstrip("\n")
                if linea.startswith("data: ") and linea != "data: {}":
                    out.append(json.loads(linea[6:]))
                elif linea == "event: cierre":
                    break
        return out


@pytest.fixture(scope="module")
def servidor(tmp_path_factory):
    s = Servidor(tmp_path_factory.mktemp("corridas"))
    yield s
    s.cerrar()


# ---------------------------------------------------------------------- con el motor simulado
def test_estado_general(servidor):
    codigo, e = servidor.pedir("/api/estado")
    assert codigo == 200
    assert {m["id"] for m in e["motores"]} == {"v4.0", "v3.1-libre", "v3.1-librev2", "ambos", "simulado"}
    assert "SL-2024-LASLAGUNAS" in {ev["id"] for ev in e["eventos_base"]}
    assert e["limite_corridas"] == 2 and len(e["congelado_sha256"]) == 64
    (sur, oeste), (norte, este) = e["dominio"]["limites"]
    assert -33.2 < sur < norte < -32.2 and -66.3 < oeste < este < -65.2


def test_corrida_completa_avance_y_huella(servidor):
    id_ = servidor.simulada(horas=6)
    eventos = servidor.eventos(id_)                              # se queda leyendo hasta que la corrida termina
    assert [e["n"] for e in eventos] == list(range(1, len(eventos) + 1))
    assert [e["h"] for e in eventos if e["aviso"] == "hora"] == list(range(7))
    assert [e["estado"] for e in eventos if e["aviso"] == "estado"] == ["creada", "iniciando", "corriendo", "terminada"]
    assert sum(e["aviso"] == "final" for e in eventos) == 1
    d = servidor.detalle(id_)
    assert d["estado"] == "terminada" and d["resultados"]["completa"] is True and d["resultados"]["ha_final"] > 0
    assert d["ultima_hora"]["h"] == 6
    (sur, oeste), (norte, este) = d["huella"]["limites"]
    assert sur < norte and oeste < este
    codigo, imagen = servidor.pedir(f"/api/corridas/{id_}/quemado.png")
    assert codigo == 200 and imagen[:8] == b"\x89PNG\r\n\x1a\n"
    codigo, temprana = servidor.pedir(f"/api/corridas/{id_}/quemado.png?hora=1")
    assert codigo == 200 and temprana != imagen                  # a la hora 1 hay menos quemado que al final
    assert servidor.eventos(id_, desde=len(eventos) - 1) == eventos[-1:]      # se puede retomar desde un evento


def test_pausar_intervenir_y_reanudar(servidor):
    id_ = servidor.simulada(horas=60, s_por_hora=0.05)
    servidor.esperar(id_, "corriendo")
    codigo, r = servidor.pedir(f"/api/corridas/{id_}/pausar", {})
    assert codigo == 200 and r["estado"] in ("pausando", "pausada")
    en_pausa = servidor.esperar(id_, "pausada")
    time.sleep(0.4)
    assert servidor.detalle(id_)["ultima_hora"]["h"] == en_pausa["ultima_hora"]["h"]         # en pausa no avanza
    assert servidor.pedir(f"/api/corridas/{id_}/intervenciones", {"tipo": "cortafuego"})[0] == 422     # sin datos
    codigo, r = servidor.pedir(f"/api/corridas/{id_}/intervenciones", {"tipo": "viento_manual",
                                                                       "datos": {"vel_kmh": 30, "dir_desde": 270}})
    assert codigo == 200 and r["aviso"] == "intervencion" and r["estado"] == "aceptada" and r["n"] == 2   # F5
    codigo, r = servidor.pedir(f"/api/corridas/{id_}/reanudar", {})
    assert codigo == 200 and r["estado"] == "corriendo"
    fin = servidor.esperar(id_, "terminada")
    assert [b["tipo"] for b in fin["bitacora"]] == ["pausa", "viento_manual", "reanudacion"]
    assert fin["bitacora"][0]["t_sim_min"] == en_pausa["ultima_hora"]["h"] * 60
    assert fin["ultima_hora"]["h"] == 60


def test_detener(servidor):
    id_ = servidor.simulada(horas=200, s_por_hora=0.05)
    servidor.esperar(id_, "corriendo")
    codigo, r = servidor.pedir(f"/api/corridas/{id_}/detener", {})
    assert codigo == 200
    fin = servidor.esperar(id_, "detenida")
    assert fin["resultados"]["completa"] is False and fin["resultados"]["motivo_fin"] == "detenida"
    assert 0 < fin["ultima_hora"]["h"] < 200
    codigo, r = servidor.pedir(f"/api/corridas/{id_}/pausar", {})
    assert codigo == 409                                         # ya no se le puede ordenar nada


def test_el_servidor_sobrevive_a_la_caida_de_un_proceso_motor(servidor):
    id_ = servidor.simulada(horas=20, fallar_en_h=2)
    limite = time.monotonic() + 30
    while (d := servidor.detalle(id_))["estado"] not in FINALES:
        assert time.monotonic() < limite
        time.sleep(0.05)
    assert d["estado"] == "error" and "código 3" in d["error"]
    assert servidor.pedir("/api/estado")[0] == 200
    otra = servidor.simulada(horas=3)                            # y sigue lanzando corridas
    assert servidor.esperar(otra, "terminada")["ultima_hora"]["h"] == 3


def test_dos_corridas_a_la_vez_y_la_tercera_se_rechaza(servidor):
    a = servidor.simulada(horas=240, s_por_hora=0.2)
    b = servidor.simulada(horas=240, s_por_hora=0.2)
    servidor.esperar(a, "corriendo"); servidor.esperar(b, "corriendo")
    tercera = servidor.simulada(horas=3, iniciar=False)
    codigo, r = servidor.pedir(f"/api/corridas/{tercera}/iniciar", {})
    assert codigo == 409 and "máximo" in r["detail"]
    for id_ in (a, b):
        assert servidor.pedir(f"/api/corridas/{id_}/detener", {})[0] == 200
    servidor.esperar(a, "detenida"); servidor.esperar(b, "detenida")
    assert servidor.pedir(f"/api/corridas/{tercera}/iniciar", {})[0] == 200      # ahora sí hay lugar
    servidor.esperar(tercera, "terminada")


def test_pedidos_de_otra_pagina_se_rechazan(servidor):
    propio = {"Origin": servidor.base, "Sec-Fetch-Site": "same-origin"}
    assert servidor.pedir("/api/estado", encabezados=propio)[0] == 200
    assert servidor.pedir("/api/estado", encabezados={"Origin": "http://otra-pagina.example"})[0] == 403
    assert servidor.pedir("/api/estado", encabezados={"Origin": f"http://127.0.0.1:{servidor.puerto + 1}"})[0] == 403
    assert servidor.pedir("/api/estado", encabezados={"Sec-Fetch-Site": "cross-site"})[0] == 403
    assert servidor.pedir("/api/estado", encabezados={"Host": "otra-pagina.example"})[0] == 403
    antes = len(servidor.pedir("/api/corridas")[1]["corridas"])
    codigo, _ = servidor.pedir("/api/corridas", {"motor": "simulado", "horas": 3, "iniciar": True},
                               encabezados={"Origin": "http://otra-pagina.example"})
    assert codigo == 403 and len(servidor.pedir("/api/corridas")[1]["corridas"]) == antes     # no creó nada


def test_pedidos_invalidos(servidor):
    lagunas = {"evento": "SL-2024-LASLAGUNAS", "horas": 3}
    assert servidor.pedir("/api/corridas", {"motor": "v9", **lagunas})[0] == 422
    codigo, r = servidor.pedir("/api/corridas", {"motor": "v4.0", "evento": "SL-1900-NADA", "horas": 3})
    assert codigo == 422 and "no tiene datos" in r["detail"]
    codigo, r = servidor.pedir("/api/corridas", {"motor": "v4.0", **lagunas, "ignicion": [{"lon": -64.0, "lat": -32.6}]})
    assert codigo == 422 and "fuera del dominio" in r["detail"]
    codigo, r = servidor.pedir("/api/corridas", {"motor": "v4.0", **lagunas, "t_inicio_utc": "2025-01-01T12:00:00Z"})
    assert codigo == 422 and "serie meteorológica" in r["detail"]
    assert servidor.pedir("/api/corridas", {"motor": "v4.0", **lagunas, "horas": 0})[0] == 422
    codigo, r = servidor.pedir("/api/corridas", {"motor": "v4.0", "evento": "SL-2024-LASLAGUNAS"})
    assert codigo == 422 and "horas" in r["detail"]
    assert servidor.pedir("/api/corridas/no-existe")[0] == 404
    creada = servidor.simulada(horas=3, iniciar=False)
    assert servidor.pedir(f"/api/corridas/{creada}/pausar", {})[0] == 409
    assert servidor.pedir(f"/api/corridas/{creada}/quemado.png")[0] == 404
    assert servidor.pedir("/")[0] == 200                         # la página mínima de prueba


# ---------------------------------------------------------------------- lo que usa la pantalla (fase F3)
def test_pantalla_y_archivos_de_la_interfaz(servidor):
    codigo, pagina = servidor.pedir("/")
    assert codigo == 200 and b"Simulador de incendios" in pagina and b"/web/app.js" in pagina
    for ruta in ("/web/app.js", "/web/estilo.css", "/web/vendor/leaflet/leaflet.js", "/web/vendor/leaflet/leaflet.css", "/prueba"):
        assert servidor.pedir(ruta)[0] == 200, ruta


def test_capas_de_fondo(servidor):
    codigo, r = servidor.pedir("/api/capas?evento=SL-2024-LASLAGUNAS")
    assert codigo == 200
    capas = {c["id"]: c for c in r["capas"]}
    assert {"relieve", "pendiente", "cobertura", "arribo", "ndvi", "ndmi", "combustible", "cicatriz",
            "dominio", "caminos", "red_mt", "viviendas", "cuarteles"} <= set(capas)
    (sur, oeste), (norte, este) = capas["relieve"]["limites"]
    assert -33.2 < sur < norte < -32.2 and -66.3 < oeste < este < -65.2
    assert {i["nombre"] for i in capas["combustible"]["leyenda"]["items"]} >= {"No combustible", "Pastizal natural", "Bosque cerrado"}
    assert capas["pendiente"]["leyenda"]["unidad"] == "grados"
    sin_evento = {c["id"] for c in servidor.pedir("/api/capas")[1]["capas"]}
    assert "relieve" in sin_evento and "ndvi" not in sin_evento             # las del evento solo aparecen con evento
    codigo, imagen = servidor.pedir("/api/capas/arribo.png")
    assert codigo == 200 and imagen[:8] == b"\x89PNG\r\n\x1a\n"
    codigo, imagen = servidor.pedir("/api/capas/cicatriz.png?evento=SL-2024-LASLAGUNAS")
    assert codigo == 200 and imagen[:4] == b"\x89PNG"
    assert servidor.pedir("/api/capas/no_existe.png")[0] == 404
    assert servidor.pedir("/api/capas/ndvi.png?evento=SL-1900-NADA")[0] == 404
    for nombre, tipos in (("dominio", {"LineString"}), ("cuarteles", {"Point"}), ("viviendas", {"Point"}), ("caminos", {"LineString", "MultiLineString"})):
        codigo, g = servidor.pedir(f"/api/vectores/{nombre}.geojson")
        assert codigo == 200 and g["type"] == "FeatureCollection" and len(g["features"]) > 0, nombre
        assert {f["geometry"]["type"] for f in g["features"]} <= tipos, nombre
        lon, lat = (g["features"][0]["geometry"]["coordinates"] if nombre in ("cuarteles", "viviendas") else
                    g["features"][0]["geometry"]["coordinates"][0] if g["features"][0]["geometry"]["type"] == "LineString" else
                    g["features"][0]["geometry"]["coordinates"][0][0])[:2]
        assert -67.5 < lon < -64.5 and -34.0 < lat < -31.5, (nombre, lon, lat)        # en grados y cerca del dominio
    assert servidor.pedir("/api/vectores/no_existe.geojson")[0] == 404


def test_contorno_comparacion_y_exportacion(servidor):
    import io
    import zipfile
    punto = [{"lon": -65.55, "lat": -32.64}]
    a = servidor.crear(motor="simulado", horas=8, iniciar=True, ignicion=punto, simulado={"s_por_hora": 0.02})["id"]
    b = servidor.crear(motor="simulado", horas=5, iniciar=True, ignicion=punto, simulado={"s_por_hora": 0.02})["id"]
    fin_a, fin_b = servidor.esperar(a, "terminada"), servidor.esperar(b, "terminada")

    codigo, g = servidor.pedir(f"/api/corridas/{a}/perimetro.geojson")
    assert codigo == 200 and g["features"][0]["geometry"]["type"] == "MultiPolygon"
    assert g["features"][0]["properties"]["ha"] == fin_a["ultima_hora"]["ha"]
    codigo, temprano = servidor.pedir(f"/api/corridas/{a}/perimetro.geojson?hora=2")
    assert 0 < temprano["features"][0]["properties"]["ha"] < g["features"][0]["properties"]["ha"]

    codigo, c = servidor.pedir(f"/api/comparacion?a={a}&b={b}&hora=5")
    assert codigo == 200 and c["iou"] == 1.0 and c["ha_a"] == c["ha_b"] == c["ha_comun"] == c["ha_envolvente"]     # mismo círculo a la misma hora
    codigo, c = servidor.pedir(f"/api/comparacion?a={a}&b={b}")                      # al final: 8 h contra 5 h
    assert codigo == 200 and 0 < c["iou"] < 1 and c["ha_comun"] == fin_b["ultima_hora"]["ha"] and c["ha_envolvente"] == fin_a["ultima_hora"]["ha"]

    codigo, plana = servidor.pedir(f"/api/corridas/{a}/quemado.png?color=2a78d6")
    assert codigo == 200 and plana[:4] == b"\x89PNG" and plana != servidor.pedir(f"/api/corridas/{a}/quemado.png")[1]
    assert servidor.pedir(f"/api/corridas/{a}/quemado.png?color=azul")[0] == 422

    codigo, paquete = servidor.pedir(f"/api/corridas/{a}/exportar")
    assert codigo == 200
    nombres = zipfile.ZipFile(io.BytesIO(paquete)).namelist()
    assert f"{a}/corrida.json" in nombres and f"{a}/perimetros_por_hora.geojson" in nombres
    por_hora = json.loads(zipfile.ZipFile(io.BytesIO(paquete)).read(f"{a}/perimetros_por_hora.geojson"))
    assert [f["properties"]["hora"] for f in por_hora["features"]] == list(range(9))
    larga = servidor.simulada(horas=240, s_por_hora=0.2)
    servidor.esperar(larga, "corriendo")
    assert servidor.pedir(f"/api/corridas/{larga}/exportar")[0] == 409              # en marcha no se exporta
    servidor.pedir(f"/api/corridas/{larga}/detener", {})
    servidor.esperar(larga, "detenida")


# ---------------------------------------------------------------------- el gestor, sin HTTP
def test_al_volver_a_arrancar_las_corridas_en_marcha_quedan_interrumpidas(tmp_path):
    for id_, estado in (("vieja-en-marcha", "corriendo"), ("vieja-terminada", "terminada")):
        (tmp_path / id_).mkdir()
        escribir_json(tmp_path / id_ / "estado.json", {"id": id_, "motor": "simulado", "estado": estado, "creada_utc": "2026-01-01T00:00:00Z",
                                                        "pedido": {}, "ultima_hora": {"h": 4, "ha": 10.0}})
    g = Gestor(tmp_path, permitir_simulado=True)
    assert g.obtener("vieja-en-marcha").estado == "interrumpida" and "se cerró" in g.obtener("vieja-en-marcha").error
    assert g.obtener("vieja-en-marcha").ultima_hora["h"] == 4            # conserva lo que había
    assert g.obtener("vieja-terminada").estado == "terminada"
    assert json.loads((tmp_path / "vieja-en-marcha" / "estado.json").read_text(encoding="utf-8"))["estado"] == "interrumpida"


def test_al_cerrar_el_servidor_las_corridas_en_marcha_guardan(tmp_path):
    g = Gestor(tmp_path, permitir_simulado=True)
    c = g.crear({"motor": "simulado", "horas": 500, "simulado": {"s_por_hora": 0.05}})[0]
    g.iniciar(c.id)
    limite = time.monotonic() + 20
    while c.estado != "corriendo":
        assert time.monotonic() < limite
        time.sleep(0.05)
    g.cerrar()
    assert c.estado == "detenida"
    assert json.loads((c.carpeta / "corrida.json").read_text(encoding="utf-8"))["resultados"]["completa"] is False
    assert Gestor(tmp_path).obtener(c.id).estado == "detenida"           # y así se la encuentra al volver


# ---------------------------------------------------------------------- con los motores reales
def test_modo_ambos_por_el_servidor_da_lo_mismo_que_la_corrida_offline(servidor, tmp_path):
    """6 horas de Las Lagunas 2024 con v4.0 y v3.1 librev2 a la vez, lanzadas por el servidor."""
    from test_procesos import MOTORES, _leer, _offline
    codigo, r = servidor.pedir("/api/corridas", {"motor": "ambos", "evento": "SL-2024-LASLAGUNAS", "hipotesis": 1, "horas": 6,
                                                 "iniciar": True})
    assert codigo == 201 and [c["motor"] for c in r["corridas"]] == ["v4.0", "v3.1-librev2"]
    assert r["corridas"][0]["grupo"] and r["corridas"][0]["grupo"] == r["corridas"][1]["grupo"]
    referencias = {m: _offline(tmp_path / m.replace(".", "_"), m) for m in ("v4.0", "v3.1-librev2")}
    for c in r["corridas"]:
        fin = servidor.esperar(c["id"], "terminada", tope_s=240)
        assert fin["ultima_hora"]["h"] == 6 and fin["resultados"]["completa"] is True
        carpeta = Path(servidor.app.state.gestor.obtener(c["id"]).carpeta)
        huella = _leer(carpeta / "salida" / MOTORES[c["motor"]][2])
        ref = referencias[c["motor"]]
        assert int((np.isfinite(ref) & (ref >= 0)).sum()) > 100, "la corrida de referencia casi no quemó: la comparación no diría nada"
        distintas = int((~((huella == ref) | (np.isnan(huella) & np.isnan(ref)))).sum())
        assert distintas == 0, f"{c['motor']}: {distintas} celdas distintas contra la corrida offline"
        codigo, imagen = servidor.pedir(f"/api/corridas/{c['id']}/quemado.png")
        assert codigo == 200 and imagen[:4] == b"\x89PNG"
