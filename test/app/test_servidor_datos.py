"""Pruebas del servidor para los datos que cambian (fase F4): trabajos de datos y pedidos /api/datos.

No usan internet ni lanzan el proceso de datos de verdad: el servidor lanza un proceso de datos FALSO (un guion que escribe
esta prueba) que emite los mismos avisos (`progreso`, `final`, `error`). La caché de datos (`datos/procesados/app`) y las
carpetas de eventos generados se redirigen a carpetas temporales: las tomas reales no se tocan.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))

from datos import comun, indices as d_indices                     # noqa: E402
from servidor import app as mod_app, datos as s_datos              # noqa: E402
from servidor.corridas import Corrida, Gestor                      # noqa: E402
from servidor.trabajos import GestorDatos                          # noqa: E402

FALSO = r'''
import json, pathlib, sys, time
aqui = pathlib.Path(__file__).resolve().parent
carpeta = pathlib.Path(sys.argv[sys.argv.index("--trabajo") + 1])
pedido = json.loads((carpeta / "pedido.json").read_text(encoding="utf-8"))
try:
    control = json.loads((aqui / "control.json").read_text(encoding="utf-8"))
except OSError:
    control = {}
modo = control.get(pedido["tarea"], "ok")

def avisar(**a):
    print(json.dumps(a, ensure_ascii=False), flush=True)

avisar(aviso="progreso", hechos=0, total=2, texto="empezando", s=0.0)
if modo == "esperar":
    limite = time.time() + 30
    while not (aqui / "soltar").exists() and time.time() < limite:
        time.sleep(0.05)
if modo == "error":
    avisar(aviso="error", mensaje="falla de prueba", clase="RuntimeError", s=0.1)
    sys.exit(1)
if modo == "muere":
    sys.exit(3)
print("una línea que no es un aviso", flush=True)
r = {"id": "X-prueba", "tarea": pedido["tarea"], "parametros": pedido["parametros"],
     "archivos": sorted(p.name for p in carpeta.iterdir())}
(carpeta / "resultado.json").write_text(json.dumps(r), encoding="utf-8")
avisar(aviso="progreso", hechos=2, total=2, texto="listo", s=0.1)
avisar(aviso="final", resultado=r, s=0.1)
'''
FINALES = {"terminado", "error", "interrumpido"}
TIF = b"II*\x00" + b"\x00" * 64                    # basta con la firma: el contenido lo revisa el proceso de datos


def escribir_falso(carpeta: Path) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    guion = carpeta / "proceso_falso.py"
    guion.write_text(FALSO, encoding="utf-8")
    return guion


class Servidor:
    def __init__(self, base: Path):
        import uvicorn
        self.dir_falso = base / "falso"
        self.guion = escribir_falso(self.dir_falso)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.puerto = s.getsockname()[1]
        self.base = f"http://127.0.0.1:{self.puerto}"
        self.app = mod_app.crear_app(base / "corridas", permitir_simulado=True, carpeta_trabajos=base / "trabajos",
                                     guion_datos=self.guion)
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

    def control(self, **modos) -> None:
        (self.dir_falso / "control.json").write_text(json.dumps(modos), encoding="utf-8")
        (self.dir_falso / "soltar").unlink(missing_ok=True)

    def soltar(self) -> None:
        (self.dir_falso / "soltar").write_text("", encoding="utf-8")

    def pedir(self, ruta: str, cuerpo=None, metodo: str | None = None):
        """(código, respuesta). `cuerpo`: dict (va como JSON) o bytes (cuerpo crudo, como una subida de archivo)."""
        if isinstance(cuerpo, (bytes, bytearray)):
            datos, tipo = bytes(cuerpo), "application/octet-stream"
        else:
            datos, tipo = (None if cuerpo is None else json.dumps(cuerpo).encode("utf-8")), "application/json"
        pedido = urllib.request.Request(self.base + ruta, data=datos, headers={"Content-Type": tipo},
                                        method=metodo or ("POST" if cuerpo is not None else "GET"))
        try:
            with urllib.request.urlopen(pedido, timeout=60) as r:
                codigo, crudo, tipo = r.status, r.read(), r.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            codigo, crudo, tipo = e.code, e.read(), e.headers.get("Content-Type", "")
        return codigo, (json.loads(crudo) if "json" in tipo else crudo)

    def lanzar(self, ruta: str, cuerpo) -> dict:
        codigo, r = self.pedir(ruta, cuerpo)
        assert codigo == 201, r
        return r["trabajo"]

    def esperar(self, id_: str, tope_s: float = 30) -> dict:
        limite = time.monotonic() + tope_s
        while True:
            codigo, t = self.pedir(f"/api/datos/trabajos/{id_}")
            assert codigo == 200, t
            if t["estado"] in FINALES:
                return t
            assert time.monotonic() < limite, f"el trabajo sigue en {t['estado']} después de {tope_s} s"
            time.sleep(0.05)

    def eventos(self, id_: str, desde: int = 0) -> list[dict]:
        out = []
        with urllib.request.urlopen(f"{self.base}/api/datos/trabajos/{id_}/eventos?desde={desde}", timeout=60) as r:
            assert r.headers.get("Content-Type", "").startswith("text/event-stream")
            for linea in r:
                linea = linea.decode("utf-8").rstrip("\n")
                if linea.startswith("data: ") and linea != "data: {}":
                    out.append(json.loads(linea[6:]))
                elif linea == "event: cierre":
                    break
        return out


@pytest.fixture(scope="module")
def cache(tmp_path_factory):
    """La caché de datos y la carpeta de entradas de los eventos generados, en una carpeta temporal vacía."""
    base = tmp_path_factory.mktemp("datos")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(comun, "CACHE", base / "cache")
        mp.setattr(comun, "ENTRADAS", base / "entradas")
        yield base


@pytest.fixture(scope="module")
def servidor(cache):
    s = Servidor(cache)
    s.control()
    yield s
    s.cerrar()


def escribir_toma(tipo: str, id_: str, creada_utc: str, **extra) -> None:
    d = comun.CACHE / tipo / id_
    d.mkdir(parents=True, exist_ok=True)
    comun.escribir_json(d / "info.json", {"id": id_, "tipo": tipo, "creada_utc": creada_utc, "rotulo": "de prueba"} | extra)


# ---------------------------------------------------------------------- importación y caché vacía
def test_el_servidor_no_carga_ningun_motor():
    codigo = ("import sys; sys.path.insert(0, 'app'); import servidor.app; "
              "malos = [m for m in sys.modules if m.split('.')[0] in ('incendios_sl', 'incendios_sl_v4')]; "
              "assert not malos, malos; print('ok')")
    r = subprocess.run([sys.executable, "-c", codigo], cwd=REPO, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr


def test_datos_con_la_cache_vacia(servidor):
    codigo, d = servidor.pedir("/api/datos")
    assert codigo == 200, d
    assert d["meteo"] == [] and d["indices"] == [] and d["eventos_rt"] == [] and d["trabajo"] is None
    assert set(d["gee"]) == {"disponible", "motivo"} and isinstance(d["gee"]["motivo"], str)
    assert d["antiguedad"]["pronostico_horas"] is None and d["antiguedad"]["indices_dias"] is None
    textos = " | ".join(d["avisos"])
    assert "pronóstico" in textos and "índices" in textos and "EJEMPLO" in textos


# ---------------------------------------------------------------------- ciclo de un trabajo
def test_ciclo_completo_de_un_trabajo(servidor):
    servidor.control()
    t = servidor.lanzar("/api/datos/meteo", {"fuente": "pronostico"})
    assert t["tarea"] == "pronostico" and t["estado"] in ("corriendo", "terminado")
    eventos = servidor.eventos(t["id"])                    # se queda leyendo hasta que el trabajo termina
    assert [e["n"] for e in eventos] == list(range(1, len(eventos) + 1))
    assert [e["estado"] for e in eventos if e["aviso"] == "estado"] == ["creado", "corriendo", "terminado"]
    assert sum(e["aviso"] == "final" for e in eventos) == 1
    assert any(e["aviso"] == "texto" for e in eventos)     # una línea suelta no rompe nada
    d = servidor.esperar(t["id"])
    assert d["estado"] == "terminado" and d["resultado"]["tarea"] == "pronostico" and d["error"] is None
    assert d["progreso"]["hechos"] == 2 and d["terminado_utc"]
    assert servidor.eventos(t["id"], desde=len(eventos) - 1) == eventos[-1:]
    carpeta = servidor.app.state.gestor_datos.carpeta / t["id"]
    assert json.loads((carpeta / "pedido.json").read_text(encoding="utf-8")) == {"tarea": "pronostico", "parametros": {}}
    assert json.loads((carpeta / "estado.json").read_text(encoding="utf-8"))["estado"] == "terminado"
    codigo, r = servidor.pedir("/api/datos")
    assert codigo == 200 and r["trabajo"]["id"] == t["id"]
    assert servidor.pedir("/api/datos/trabajos/no-existe")[0] == 404


def test_un_trabajo_de_datos_a_la_vez(servidor):
    servidor.control(pronostico="esperar")
    t = servidor.lanzar("/api/datos/meteo", {"fuente": "pronostico"})
    codigo, r = servidor.pedir("/api/datos/indices", {"fuente": "aws"})
    assert codigo == 409 and "uno a la vez" in r["detail"] and t["id"] in r["detail"]
    assert servidor.pedir("/api/datos")[1]["trabajo"]["id"] == t["id"]          # el trabajo en marcha
    servidor.soltar()
    assert servidor.esperar(t["id"])["estado"] == "terminado"
    t2 = servidor.lanzar("/api/datos/indices", {"fuente": "aws", "fecha_corrida": "2026-11-13"})
    d = servidor.esperar(t2["id"])
    assert d["estado"] == "terminado" and d["parametros"] == {"fecha_corrida": "2026-11-13"} and d["tarea"] == "indices_aws"


def test_error_y_caida_del_proceso_de_datos(servidor):
    servidor.control(escenario="error", pronostico="muere")
    t = servidor.lanzar("/api/datos/meteo/escenario", {"desde_utc": "2026-11-13T15:00:00Z", "horas": 24, "temp_c": 30,
                                                       "hr_pct": 15, "viento_kmh": 40, "viento_dir_deg": 315})
    d = servidor.esperar(t["id"])
    assert d["estado"] == "error" and d["error"] == "falla de prueba" and d["resultado"] is None
    assert d["parametros"]["precip_mm"] == 0.0 and d["parametros"]["desde_utc"] == "2026-11-13T15:00:00Z"
    d = servidor.esperar(servidor.lanzar("/api/datos/meteo", {"fuente": "pronostico"})["id"])
    assert d["estado"] == "error" and "terminó sin avisar (código 3)" in d["error"]
    servidor.control()
    assert servidor.esperar(servidor.lanzar("/api/datos/meteo", {})["id"])["estado"] == "terminado"   # sigue andando


# ---------------------------------------------------------------------- subidas de archivos
def test_meteorologia_desde_un_csv(servidor, monkeypatch):
    servidor.control()
    csv = b"time_utc,temperature_2m\n2026-11-13T00:00:00Z,20\n"
    t = servidor.lanzar("/api/datos/meteo/archivo?nombre=mi%20serie.csv", csv)
    d = servidor.esperar(t["id"])
    assert d["estado"] == "terminado" and d["parametros"] == {"archivo": "entrada.csv", "nombre": "mi_serie.csv"}
    assert "entrada.csv" in d["resultado"]["archivos"]
    assert (servidor.app.state.gestor_datos.carpeta / t["id"] / "entrada.csv").read_bytes() == csv
    assert servidor.pedir("/api/datos/meteo/archivo?nombre=x.csv", b"")[0] == 422
    assert servidor.pedir("/api/datos/meteo/archivo?nombre=x.exe", csv)[0] == 422
    monkeypatch.setattr(mod_app, "MAX_CSV", 10)
    codigo, r = servidor.pedir("/api/datos/meteo/archivo?nombre=x.csv", csv)
    assert codigo == 413 and "máximo" in r["detail"]


def test_indices_cargados_a_mano(servidor, monkeypatch):
    servidor.control()
    manual = {"ventana": ["2026-09-28", "2026-11-11"], "ndmi_nir": "B8A", "descripcion": "de prueba"}
    codigo, r = servidor.pedir("/api/datos/indices/manual", manual)
    assert codigo == 409 and "ndvi y ndmi" in r["detail"]
    codigo, r = servidor.pedir("/api/datos/indices/archivo?banda=ndvi&nombre=ndvi_oct.tif", TIF)
    assert codigo == 201 and r["espera"]["ndvi"]["nombre"] == "ndvi_oct.tif" and r["espera"]["ndmi"] is None
    codigo, r = servidor.pedir("/api/datos/indices/manual", manual)
    assert codigo == 409 and "ndmi" in r["detail"]
    assert servidor.pedir("/api/datos/indices/archivo?banda=ndmi&nombre=x.tif", b"no es un tif")[0] == 422
    assert servidor.pedir("/api/datos/indices/archivo?banda=evi&nombre=x.tif", TIF)[0] == 422
    monkeypatch.setattr(mod_app, "MAX_TIF", 10)
    assert servidor.pedir("/api/datos/indices/archivo?banda=ndmi&nombre=x.tif", TIF)[0] == 413
    monkeypatch.undo()
    assert servidor.pedir("/api/datos/indices/archivo?banda=ndmi&nombre=ndmi_oct.tif", TIF)[0] == 201
    for malo in ({**manual, "ndmi_nir": "B04"}, {**manual, "ventana": ["2026-11-11", "2026-09-28"]},
                 {**manual, "ventana": ["2026-09-28"]}, {**manual, "ventana": ["ayer", "hoy"]}):
        assert servidor.pedir("/api/datos/indices/manual", malo)[0] == 422, malo
    t = servidor.lanzar("/api/datos/indices/manual", manual)
    d = servidor.esperar(t["id"])
    assert d["estado"] == "terminado" and {"ndvi.tif", "ndmi.tif"} <= set(d["resultado"]["archivos"])
    assert d["parametros"] == {"ndvi": "ndvi.tif", "ndmi": "ndmi.tif", "nombre_ndvi": "ndvi_oct.tif", "nombre_ndmi": "ndmi_oct.tif",
                               "ventana": ["2026-09-28", "2026-11-11"], "ndmi_nir": "B8A", "descripcion": "de prueba"}
    assert not servidor.app.state.gestor_datos.espera.exists()                 # la espera se vació
    assert servidor.pedir("/api/datos/indices/manual", manual)[0] == 409       # hay que volver a subirlos


def test_google_earth_engine_segun_disponibilidad(servidor, monkeypatch):
    servidor.control()
    monkeypatch.setattr(d_indices, "gee_disponible", lambda: (False, "faltan las credenciales de prueba"))
    codigo, r = servidor.pedir("/api/datos/indices", {"fuente": "gee"})
    assert codigo == 409 and "faltan las credenciales de prueba" in r["detail"]
    assert servidor.pedir("/api/datos")[1]["gee"] == {"disponible": False, "motivo": "faltan las credenciales de prueba"}
    monkeypatch.setattr(d_indices, "gee_disponible", lambda: (True, "credenciales presentes"))
    d = servidor.esperar(servidor.lanzar("/api/datos/indices", {"fuente": "gee"})["id"])
    assert d["estado"] == "terminado" and d["tarea"] == "indices_gee" and d["parametros"] == {}


# ---------------------------------------------------------------------- validación
@pytest.mark.parametrize("ruta, cuerpo", [
    ("/api/datos/meteo", {"fuente": "satelite"}),
    ("/api/datos/meteo/escenario", {"desde_utc": "2026-11-13T15:00:00", "horas": 24, "temp_c": 30, "hr_pct": 15,
                                    "viento_kmh": 40, "viento_dir_deg": 315}),            # sin huso horario
    ("/api/datos/meteo/escenario", {"desde_utc": "2026-11-13T15:00:00Z", "horas": 0, "temp_c": 30, "hr_pct": 15,
                                    "viento_kmh": 40, "viento_dir_deg": 315}),
    ("/api/datos/meteo/escenario", {"desde_utc": "2026-11-13T15:00:00Z", "horas": 24, "temp_c": 80, "hr_pct": 15,
                                    "viento_kmh": 40, "viento_dir_deg": 315}),
    ("/api/datos/meteo/escenario", {"desde_utc": "2026-11-13T15:00:00Z", "horas": 24, "temp_c": 30, "hr_pct": 120,
                                    "viento_kmh": 40, "viento_dir_deg": 315}),
    ("/api/datos/meteo/escenario", {"desde_utc": "2026-11-13T15:00:00Z", "horas": 24, "temp_c": 30, "hr_pct": 15,
                                    "viento_kmh": -1, "viento_dir_deg": 315}),
    ("/api/datos/meteo/escenario", {"desde_utc": "2026-11-13T15:00:00Z", "horas": 24, "temp_c": 30, "hr_pct": 15,
                                    "viento_kmh": 40, "viento_dir_deg": 400}),
    ("/api/datos/meteo/escenario", {"desde_utc": "2026-11-13T15:00:00Z", "horas": 24, "temp_c": 30, "hr_pct": 15,
                                    "viento_kmh": 40, "viento_dir_deg": 315, "precip_mm": -2}),
    ("/api/datos/meteo/escenario", {"horas": 24}),
    ("/api/datos/indices", {"fuente": "landsat"}),
    ("/api/datos/indices", {"fuente": "aws", "fecha_corrida": "13/11/2026"}),
    ("/api/datos/evento", {"nombre": "x" * 300}),
])
def test_pedidos_de_datos_invalidos(servidor, ruta, cuerpo):
    codigo, r = servidor.pedir(ruta, cuerpo)
    assert codigo == 422, r
    assert servidor.app.state.gestor_datos.en_marcha() is None


# ---------------------------------------------------------------------- eventos generados
def test_crear_un_evento_generado(servidor):
    servidor.control()
    codigo, r = servidor.pedir("/api/datos/evento", {})
    assert codigo == 409 and "meteorología" in r["detail"]
    escribir_toma("meteo", "M-20261113T1200-pronostico", "2026-11-13T12:00:00Z", hora_de_la_toma_utc="2026-11-13T12:00:00Z")
    escribir_toma("meteo", "M-20261113T1800-pronostico", "2026-11-13T18:00:00Z", hora_de_la_toma_utc="2026-11-13T18:00:00Z")
    codigo, r = servidor.pedir("/api/datos/evento", {})
    assert codigo == 409 and "índices" in r["detail"]
    escribir_toma("indices", "I-20261112-aws", "2026-11-13T18:10:00Z", ultima_fecha="2026-11-07",
                  ventana=["2026-09-28", "2026-11-12"], escenas=[{"id": "S2A_x"}] * 3)
    d = servidor.esperar(servidor.lanzar("/api/datos/evento", {"nombre": " Prueba "})["id"])
    assert d["estado"] == "terminado" and d["parametros"] == {"meteo": "M-20261113T1800-pronostico",
                                                              "indices": "I-20261112-aws", "nombre": "Prueba"}
    d = servidor.esperar(servidor.lanzar("/api/datos/evento", {"meteo": "M-20261113T1200-pronostico"})["id"])
    assert d["parametros"] == {"meteo": "M-20261113T1200-pronostico", "indices": "I-20261112-aws"}
    codigo, r = servidor.pedir("/api/datos/evento", {"indices": "I-no-existe"})
    assert codigo == 422 and "I-no-existe" in r["detail"]
    codigo, r = servidor.pedir("/api/datos")
    assert [t["id"] for t in r["meteo"]][0] == "M-20261113T1800-pronostico"
    assert r["indices"][0]["id"] == "I-20261112-aws" and "escenas" not in r["indices"][0]
    assert r["antiguedad"]["pronostico_utc"] == "2026-11-13T18:00:00Z" and r["antiguedad"]["indices_fecha"] == "2026-11-07"


def _evento_rt_falso(repo: Path, entradas: Path, id_: str, escenarios: Path | None = None) -> None:
    """Los archivos de un evento generado, sin contenido real (para listar, borrar y armar corrida.json)."""
    for v in ("v3.1", "v4.0"):
        f = (escenarios or repo / "escenarios") / v / "eventos" / f"{id_}.yaml"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"id: {id_}\nnombre: Tiempo real de prueba\nmeteorologia:\n  inicio_utc: '2026-11-08T18:00:00Z'\n"
                     "  fin_utc: '2026-11-20T23:00:00Z'\ninicio:\n  hora_utc_hipotesis: ['2026-11-13T18:00:00Z']\n"
                     "ignicion:\n  puntos: [{nombre: centro, lon: -65.8, lat: -32.7}]\n", encoding="utf-8")
    (entradas / "combustibles" / id_).mkdir(parents=True, exist_ok=True)
    (entradas / "meteo").mkdir(parents=True, exist_ok=True)
    (entradas / "meteo" / f"{id_}_ecmwf_ifs025_dominio.csv").write_text("time_utc\n", encoding="utf-8")
    comun.escribir_json(entradas / "eventos" / id_ / f"insumos_{id_}.json", {
        "id": id_, "nombre": "Tiempo real de prueba", "creado_utc": "2026-11-13T18:20:00Z",
        "t_inicio_por_defecto_utc": "2026-11-13T18:00:00Z",
        "meteo": {"id": "M-20261113T1800-pronostico", "fuente": "Open-Meteo Forecast API, modelo ecmwf_ifs025",
                  "rotulo": "pronóstico", "modelo": "ecmwf_ifs025", "descargado_utc": "2026-11-13T18:18:50Z", "sha256": "a" * 64,
                  "aviso": "Open-Meteo entrega análisis y pronóstico de un modelo, no observaciones"},
        "indices": {"id": "I-20261112-aws", "fuente": "Sentinel-2 L2A, AWS", "rotulo": "Sentinel-2 por AWS (en prueba hasta E-E3-2)",
                    "via": "aws", "en_prueba": True, "ventana": ["2026-09-28", "2026-11-11"], "n_escenas": 29,
                    "ndmi_nir": "B08", "sha256": {"ndvi": "b" * 64, "ndmi": "c" * 64}},
        "cobertura_anio": 2025,
        "verano_v40": {"archivos": ["NDVI_NDMI_2026_01.tif", "NDVI_NDMI_2026_02.tif"], "faltan": ["NDVI_NDMI_2026_03.tif"],
                       "sha256": {"NDVI_NDMI_2026_01.tif": "d" * 64}},
        "archivos": {"ficha": f"escenarios/v4.0/eventos/{id_}.yaml"}, "sha256": {"ficha": "e" * 64},
        "rotulos": ["pronóstico", "Sentinel-2 por AWS (en prueba hasta E-E3-2)"],
        "avisos": ["índices por AWS en prueba: la vía se habilita cuando se cumpla E-E3-2"]})


def test_borrar_un_evento_generado(servidor, tmp_path, monkeypatch):
    monkeypatch.setattr(comun, "REPO", tmp_path)
    _evento_rt_falso(tmp_path, comun.ENTRADAS, "RT-20261113-7")
    codigo, r = servidor.pedir("/api/datos/eventos/SL-2024-LASLAGUNAS", metodo="DELETE")
    assert codigo == 422 and "RT-" in r["detail"]
    assert servidor.pedir("/api/datos/eventos/RT-20261113-9", metodo="DELETE")[0] == 404
    assert [e["id"] for e in servidor.pedir("/api/datos")[1]["eventos_rt"]] == ["RT-20261113-7"]
    gestor = servidor.app.state.gestor
    c = Corrida("c-prueba", tmp_path / "c-prueba", "v4.0", {"evento": "RT-20261113-7"}, estado="corriendo")
    gestor.corridas[c.id] = c
    try:
        codigo, r = servidor.pedir("/api/datos/eventos/RT-20261113-7", metodo="DELETE")
        assert codigo == 409 and "c-prueba" in r["detail"]
    finally:
        del gestor.corridas[c.id]
    codigo, r = servidor.pedir("/api/datos/eventos/RT-20261113-7", metodo="DELETE")
    assert codigo == 200 and r == {"borrado": "RT-20261113-7"}
    assert not (tmp_path / "escenarios" / "v4.0" / "eventos" / "RT-20261113-7.yaml").exists()
    assert not (comun.ENTRADAS / "eventos" / "RT-20261113-7").exists()
    assert not list((comun.ENTRADAS / "meteo").glob("RT-20261113-7_*"))
    assert servidor.pedir("/api/datos")[1]["eventos_rt"] == []


# ---------------------------------------------------------------------- recuperación y cierre
def test_al_volver_a_arrancar_los_trabajos_en_marcha_quedan_interrumpidos(tmp_path):
    carpeta = tmp_path / "trabajos"
    for id_, estado in (("t1", "corriendo"), ("t2", "terminado"), ("t3", "creado")):
        (carpeta / id_).mkdir(parents=True)
        comun.escribir_json(carpeta / id_ / "estado.json", {"id": id_, "tarea": "pronostico", "parametros": {},
                                                            "estado": estado, "creado_utc": f"2026-11-13T10:00:0{id_[1]}Z"})
    (carpeta / "sin-estado").mkdir()                       # una carpeta suelta no molesta
    g = GestorDatos(carpeta, escribir_falso(tmp_path / "falso"))
    assert {t.id: t.estado for t in g.trabajos.values()} == {"t1": "interrumpido", "t2": "terminado", "t3": "interrumpido"}
    assert "se cerró" in g.trabajos["t1"].error and g.en_marcha() is None
    assert json.loads((carpeta / "t1" / "estado.json").read_text(encoding="utf-8"))["estado"] == "interrumpido"
    assert g.ultimo().id == "t3"
    t = g.lanzar("evento", {"meteo": "M", "indices": "I"})     # se puede volver a pedir
    limite = time.monotonic() + 30
    while t.estado not in FINALES:
        assert time.monotonic() < limite
        time.sleep(0.05)
    assert t.estado == "terminado" and g.ultimo().id == t.id


def test_al_cerrar_el_servidor_el_trabajo_en_marcha_queda_interrumpido(tmp_path):
    falso = escribir_falso(tmp_path / "falso")
    (falso.parent / "control.json").write_text(json.dumps({"indices_aws": "esperar"}), encoding="utf-8")
    terminados = []
    g = GestorDatos(tmp_path / "trabajos", falso, al_terminar=terminados.append)
    t = g.lanzar("indices_aws", {})
    while not t.eventos or t.progreso is None:
        time.sleep(0.05)
    inicio = time.monotonic()
    g.cerrar()
    assert time.monotonic() - inicio < 10 and t.estado == "interrumpido" and t.proceso.poll() is not None
    assert GestorDatos(tmp_path / "trabajos", falso).trabajos[t.id].estado == "interrumpido"
    assert terminados == []                               # interrumpido por el cierre: no se avisa como terminado


# ---------------------------------------------------------------------- lista de eventos y corrida.json
def test_eventos_base_con_tiempo_real_y_ejemplo(tmp_path, monkeypatch):
    s_datos.dominio()                                     # queda en memoria con el dominio real
    escenarios, entradas = tmp_path / "escenarios", tmp_path / "entradas"
    real = s_datos.ESCENARIOS / "eventos" / "SL-2024-LASLAGUNAS.yaml"
    (escenarios / "v4.0" / "eventos").mkdir(parents=True)
    (escenarios / "v4.0" / "eventos" / real.name).write_text(real.read_text(encoding="utf-8"), encoding="utf-8")
    for k in ("eventos", "combustibles"):
        (entradas / k / "SL-2024-LASLAGUNAS").mkdir(parents=True)
    monkeypatch.setattr(s_datos, "ESCENARIOS", escenarios / "v4.0")
    monkeypatch.setattr(s_datos, "ENTRADAS", entradas)
    ev = s_datos.eventos_base()
    assert list(ev) == ["SL-2024-LASLAGUNAS"]
    lag = ev["SL-2024-LASLAGUNAS"]
    assert lag["tiempo_real"] is False and lag["rotulos"] == ["EJEMPLO"] and lag["ignicion_de_la_ficha"]

    # un evento generado a medio armar (sin insumos) no aparece; cuando se completa, aparece sin tocar nada más
    _evento_rt_falso(tmp_path, entradas, "RT-20261113-2", escenarios)
    insumos = entradas / "eventos" / "RT-20261113-2" / "insumos_RT-20261113-2.json"
    contenido = insumos.read_bytes()
    insumos.unlink()
    assert "RT-20261113-2" not in s_datos.eventos_base()
    insumos.write_bytes(contenido)
    rt = s_datos.eventos_base()["RT-20261113-2"]
    assert rt["tiempo_real"] is True and rt["ignicion_de_la_ficha"] == []
    assert rt["rotulos"] == ["pronóstico", "Sentinel-2 por AWS (en prueba hasta E-E3-2)"] and "E-E3-2" in rt["avisos"][0]
    assert rt["meteo_desde_utc"] == "2026-11-08T18:00:00Z" and rt["t_inicio_por_defecto_utc"] == "2026-11-13T18:00:00Z"

    # una corrida de un evento generado necesita el punto de ignición
    with pytest.raises(ValueError, match="ignición"):
        s_datos.revisar_pedido({"evento": "RT-20261113-2", "horas": 6})
    with pytest.raises(ValueError, match="ficha"):
        s_datos.revisar_pedido({"evento": "RT-20261113-2", "ignicion": [{"lon": -65.8, "lat": -32.7}], "ignicion_ficha": "centro"})
    s_datos.revisar_pedido({"evento": "RT-20261113-2", "horas": 6, "ignicion": [{"lon": -65.8, "lat": -32.7}],
                            "t_inicio_utc": "2026-11-13T18:00:00Z"})

    # corrida.json: bloque insumos y advertencias
    g = Gestor(tmp_path / "corridas")
    c = g.crear({"motor": "v4.0", "evento": "RT-20261113-2", "horas": 6, "ignicion": [{"lon": -65.8, "lat": -32.7}]})[0]
    cj = json.loads((c.carpeta / "corrida.json").read_text(encoding="utf-8"))
    assert cj["formato"] == "incendios_sl.corrida/1.2" and cj["programa"]["version"] == "0.3.0"
    ins = cj["insumos"]
    assert ins["meteo"]["modelo"] == "ecmwf_ifs025" and ins["meteo"]["sha256"] == "a" * 64
    assert ins["meteo"]["descargado_utc"] == "2026-11-13T18:18:50Z"
    assert ins["indices_ventana"] == {"toma": "I-20261112-aws", "fuente": "Sentinel-2 L2A, AWS",
                                      "rotulo": "Sentinel-2 por AWS (en prueba hasta E-E3-2)", "via": "aws",
                                      "ventana": ["2026-09-28", "2026-11-11"], "escenas": 29, "ndmi_nir": "B08",
                                      "sha256": {"ndvi": "b" * 64, "ndmi": "c" * 64}, "en_prueba": True}
    assert ins["indices_verano"]["anio"] == 2026 and ins["indices_verano"]["faltan"] == ["NDVI_NDMI_2026_03.tif"]
    assert ins["cobertura_anio"] == 2025 and ins["evento"]["id"] == "RT-20261113-2"
    adv = " | ".join(cj["advertencias"])
    assert "en prueba" in adv and "no observaciones" in adv and "sin cicatriz" in adv
    assert cj["base"]["definicion"]["evento"] == "RT-20261113-2" and cj["configuracion"]["ignicion"]

    c = g.crear({"motor": "v4.0", "evento": "SL-2024-LASLAGUNAS", "horas": 6})[0]
    cj = json.loads((c.carpeta / "corrida.json").read_text(encoding="utf-8"))
    assert "insumos" not in cj and cj["advertencias"] == ["EJEMPLO: datos de un evento histórico"]
    g2 = Gestor(tmp_path / "corridas2", permitir_simulado=True)
    cj = json.loads((g2.crear({"motor": "simulado", "horas": 3})[0].carpeta / "corrida.json").read_text(encoding="utf-8"))
    assert "insumos" not in cj and "advertencias" not in cj
