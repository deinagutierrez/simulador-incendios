"""Pruebas de las intervenciones en el motor v3.1 (fase F5; D-E3-28, puntos 7, 8, 10-12 y 28).

Sobre Las Lagunas 2024 (hipótesis 1, inicio 15:00 UTC), con pocas horas:
- la matriz de barreras vacía completa da lo mismo que las barreras apagadas, en `libre` y en `libre_v2` (12 h);
- los enlaces de un trazo con la función real `preparar_barreras_enlaces` envuelta son los mismos que los de una copia de su
  núcleo limitada a una ventana (prueba de los lectores), y la función nunca escribe en datos/inputSimulacion/barreras;
- un trazo antes de iniciar da lo mismo que el mismo trazo aplicado en la pausa de t = 0;
- cortafuegos y viento manual aplicados en pausa dan lo mismo que la corrida offline (`correr_escenario.py` del motor) con
  los trazos recortados cargados desde el inicio y la serie meteorológica editada, por medio de un espejo de
  datos/inputSimulacion en una carpeta temporal (`barreras_v31.armar_espejo`);
- estados `aceptada`, `recortada` y `rechazada`, y lo que queda en la bitácora y en la carpeta de la corrida.
- la reproducción desde la bitácora (comparación A de E-E3-4) da la misma cadena y 0 celdas distintas.

Tiempos medidos (2026-11-14, Linux): la función real tarda unos 4,7 s por trazo (la copia en ventana, unos 40 ms); una
corrida de 6 h sin trazos, unos 4 s (con dos trazos en pausa, unos 19 s); el espejo y la corrida offline, unos 4,5 s; el
conjunto, unos dos minutos. No usa red. Lo que necesita el motor cargado en el
mismo proceso lo hace test/app/ayudante_v31.py, en un proceso aparte.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
PROCESO = REPO / "app" / "motores" / "proceso.py"
AYUDANTE = Path(__file__).resolve().parent / "ayudante_v31.py"
sys.path.insert(0, str(REPO / "app" / "motores"))
import barreras_v31  # noqa: E402
import intervenciones  # noqa: E402

EVENTO, DOMINIO = "SL-2024-LASLAGUNAS", "las_lagunas_potrerillos"
DEFINICION = {"evento": EVENTO, "hipotesis": 1, "validar": False, "figuras": False}
TOPE_S = 300

# Trazos (EPSG:5345). Sin intervenciones, a las 2 h hay dos manchas quemadas: x ≈ 3.535.170-3.535.440 y 3.542.130-3.542.670,
# y ≈ 6.388.290-6.389.520; el frente avanza hacia el sur (borde sur en y ≈ 6.385.950 a las 6 h).
DELANTE = {"ancho_m": 10, "xy_5345": [[3534000, 6387500], [3539000, 6387400], [3544500, 6387500]]}
SOBRE_LO_QUEMADO = {"ancho_m": 25, "suelo_mineral": True, "xy_5345": [[3542400, 6390500], [3542400, 6386500]]}
AFUERA = {"ancho_m": 6, "xy_5345": [[3600000, 6300000], [3601000, 6300500]]}
CERCA_DEL_FOCO = {"ancho_m": 10, "suelo_mineral": True, "xy_5345": [[3534000, 6388100], [3539000, 6388000], [3544000, 6388100]]}
VIENTO = {"vel_kmh": 20, "dir_desde": 87}
PRONOSTICO = {"modo": "pronostico"}


# ------------------------------------------------------------------------------------------------ utilidades
def _entorno(**extra) -> dict:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    env.pop("PYTHONPATH", None)
    env.pop("INCENDIOS_SL_INPUT", None)
    env.update(extra)
    return env


def _leer(tif: Path) -> np.ndarray:
    import rasterio
    with rasterio.open(tif) as s:
        return s.read(1)


def _distintas(a: np.ndarray, b: np.ndarray) -> int:
    assert a.shape == b.shape
    return int((~((a == b) | (np.isnan(a) & np.isnan(b)))).sum())


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _ayudante(*args) -> dict:
    p = subprocess.run([sys.executable, str(AYUDANTE), *map(str, args)], cwd=REPO, env=_entorno(), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=TOPE_S)
    assert p.returncode == 0, p.stdout[-2000:] + p.stderr[-3000:]
    return json.loads(p.stdout.rsplit("RESULTADO ", 1)[1])


def _correr(carpeta: Path, motor: str, horas: float, configuracion: dict | None = None, guion: list | None = None,
            corrida: dict | None = None) -> dict:
    """Corre el proceso motor. `guion` = [(t_sim_min, [entradas]), …]: pausa en cada hora, manda las entradas y reanuda.
    `corrida`, si se da, es el `corrida.json` entero (y `motor`, `horas` y `configuracion` no se usan).
    Devuelve los avisos, `corrida.json` final y los segundos."""
    carpeta.mkdir(parents=True, exist_ok=True)
    if corrida is None:
        corrida = {"formato": "incendios_sl.corrida/1.0", "motor": motor,
                   "base": {"definicion": {**DEFINICION, "horas": horas}}}
        if configuracion:
            corrida["configuracion"] = configuracion
    (carpeta / "corrida.json").write_text(json.dumps(corrida), encoding="utf-8")
    t0 = time.perf_counter()
    p = subprocess.Popen([sys.executable, str(PROCESO), "--corrida", str(carpeta)], cwd=REPO, env=_entorno(),
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                         bufsize=1)
    guardian = threading.Timer(TOPE_S, p.kill)
    guardian.daemon = True
    guardian.start()
    pendientes = list(guion or [])

    def mandar(o):
        p.stdin.write(json.dumps(o) + "\n")
        p.stdin.flush()

    if pendientes:
        mandar({"orden": "pausar", "en_t_sim_min": pendientes[0][0]})
    avisos = []
    for linea in p.stdout:
        a = json.loads(linea)
        avisos.append(a)
        if a["aviso"] == "pausado" and pendientes:
            _, entradas = pendientes.pop(0)
            for i, e in enumerate(entradas):
                mandar({"orden": "intervenir", "ref": f"{a['t_sim_min']:g}-{i}", "entrada": e})
            if pendientes:
                mandar({"orden": "pausar", "en_t_sim_min": pendientes[0][0]})
            mandar({"orden": "reanudar"})
    p.wait(timeout=60)
    guardian.cancel()
    assert p.returncode == 0, p.stderr.read()[-3000:] + (carpeta / "proceso.log").read_text(encoding="utf-8")[-3000:]
    return {"avisos": avisos, "corrida": json.loads((carpeta / "corrida.json").read_text(encoding="utf-8")),
            "s": time.perf_counter() - t0}


def _llegada(carpeta: Path) -> np.ndarray:
    return _leer(carpeta / "salida" / "t_llegada_s.tif")


def _offline(tmp: Path, carpeta_app: Path) -> tuple[np.ndarray, dict]:
    """La corrida offline de la comparación B: `correr_escenario.py` de v3.1 con el YAML de la corrida de la app, sobre un
    espejo de datos/inputSimulacion con lo que aplicó la corrida (barreras, suelo mineral y viento manual)."""
    origen = REPO / "datos" / "inputSimulacion"
    vigilados = [origen / "barreras" / f"barreras_enlaces_{DOMINIO}.npz",
                 origen / "combustibles" / EVENTO / f"combustible_clase_{EVENTO}.tif",
                 *sorted((origen / "meteo").glob(f"{EVENTO}_*_dominio.csv"))]
    antes = {p: _sha(p) for p in vigilados}
    t0 = time.perf_counter()
    info = barreras_v31.armar_espejo(carpeta_app, tmp / "espejo", EVENTO, DOMINIO)
    info["s_espejo"] = round(time.perf_counter() - t0, 2)
    esc = yaml.safe_load((carpeta_app / "escenario_base.yaml").read_text(encoding="utf-8"))
    esc["run_id"] = "offline"
    if info["barreras"]:
        esc["barreras"] = "on"
    (tmp / "offline.yaml").write_text(yaml.safe_dump(esc, sort_keys=False), encoding="utf-8")
    t0 = time.perf_counter()
    p = subprocess.run([sys.executable, "scripts/correr_escenario.py", "--archivo", str(tmp / "offline.yaml")],
                       cwd=REPO / "src" / "v3.1", capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=_entorno(PYTHONPATH=str(REPO / "src" / "v3.1" / "src"), INCENDIOS_SL_INPUT=str(tmp / "espejo"),
                                    INCENDIOS_SL_RESULTADOS=str(tmp / "resultados")), timeout=TOPE_S)
    assert p.returncode == 0, p.stdout[-2000:] + p.stderr[-3000:]
    info["s_offline"] = round(time.perf_counter() - t0, 2)
    assert {p: _sha(p) for p in vigilados} == antes, "el espejo cambió un insumo original"
    return _leer(tmp / "resultados" / "offline" / "t_llegada_s.tif"), info


def _intervenciones(avisos: list) -> list[dict]:
    return [a for a in avisos if a["aviso"] == "intervencion"]


# ------------------------------------------------------------------------------------------------ matriz vacía
@pytest.mark.parametrize("variante", ["libre", "libre_v2"])
def test_matriz_vacia_igual_a_barreras_apagadas(variante, tmp_path):
    r = _ayudante("vacia", variante, 12, tmp_path)
    print(f"{variante}, 12 h: {r}")
    assert r["celdas_quemadas"] > 1000
    assert r["distintas_llegada"] == 0 and r["distintas_estado"] == 0


# ------------------------------------------------------------------------------------------------ códigos del trazo
def test_codigos_con_la_funcion_real_igual_a_la_copia_en_ventana(tmp_path):
    trazos = [intervenciones.validar_cortafuego(d) for d in (DELANTE, SOBRE_LO_QUEMADO, CERCA_DEL_FOCO)]
    # uno que sale de la grilla por la esquina noroeste, con coordenadas que no caen en bordes de celda
    trazos.append(intervenciones.validar_cortafuego(
        {"ancho_m": 3, "xy_5345": [[3513000, 6417950], [3513500.33, 6417000.71], [3514012.5, 6417100.25]]}))
    (tmp_path / "trazos.json").write_text(json.dumps(trazos), encoding="utf-8")
    r = _ayudante("codigos", tmp_path / "corrida", tmp_path / "trazos.json")
    print(r)
    assert all(c["iguales"] and c["enlaces_real"] > 0 for c in r["casos"]), r["casos"]
    assert r["compartido_sin_cambios"] and r["entorno_restaurado"]
    assert r["productos_que_quedaron"] == []              # el producto de cada llamada se borra después de leerlo


# ------------------------------------------------------------------------------------------------ antes de iniciar = t 0
def test_trazo_antes_de_iniciar_igual_a_t0(tmp_path):
    antes = _correr(tmp_path / "antes", "v3.1-librev2", 4, configuracion={"cortafuegos": [CERCA_DEL_FOCO]})
    en_t0 = _correr(tmp_path / "t0", "v3.1-librev2", 4, guion=[(0, [{"tipo": "cortafuego", "datos": CERCA_DEL_FOCO}])])
    print(f"antes de iniciar {antes['s']:.1f} s, en la pausa de t = 0 {en_t0['s']:.1f} s")
    ini = antes["corrida"]["resultados"]["cortafuegos_iniciales"]
    assert len(ini) == 1 and ini[0]["estado"] == "aceptada"
    (aviso,) = _intervenciones(en_t0["avisos"])
    assert aviso["estado"] == "aceptada" and aviso["t_vigor_min"] == 0.0
    for clave in ("enlaces", "enlaces_sha256", "celdas_mineral", "celdas_mineral_sha256", "longitud_aplicada_m"):
        assert ini[0][clave] == aviso["entrada"]["datos"][clave], clave
    assert ini[0]["celdas_mineral"] > 0
    assert _distintas(_llegada(tmp_path / "antes"), _llegada(tmp_path / "t0")) == 0
    # y el trazo hace algo: sin él la corrida es otra
    assert antes["corrida"]["resultados"]["ha_final"] != _correr(tmp_path / "sin", "v3.1-librev2", 4)["corrida"]["resultados"]["ha_final"]


# ------------------------------------------------------------------------------------------------ en pausa = offline
@pytest.fixture(scope="module")
def en_pausa(tmp_path_factory):
    """libre_v2, 6 h: en la pausa de las 2 h un trazo delante del frente, uno sobre lo quemado (con suelo mineral), uno
    fuera del dominio, "volver al pronóstico" sin viento manual y viento manual; en la de las 4 h, vuelta al pronóstico."""
    tmp = tmp_path_factory.mktemp("v31_en_pausa")
    guion = [(120, [{"tipo": "cortafuego", "datos": DELANTE}, {"tipo": "cortafuego", "datos": SOBRE_LO_QUEMADO},
                    {"tipo": "cortafuego", "datos": AFUERA}, {"tipo": "viento_manual", "datos": PRONOSTICO},
                    {"tipo": "viento_manual", "datos": VIENTO}]),
             (240, [{"tipo": "viento_manual", "datos": PRONOSTICO}])]
    r = _correr(tmp / "app", "v3.1-librev2", 6, guion=guion)
    return {**r, "tmp": tmp, "carpeta": tmp / "app"}


def test_estados_y_bitacora_de_las_intervenciones(en_pausa):
    iv = _intervenciones(en_pausa["avisos"])
    assert [a["estado"] for a in iv] == ["aceptada", "recortada", "rechazada", "rechazada", "aceptada", "aceptada"]
    delante, sobre, afuera, sin_manual, viento, vuelta = iv
    assert afuera["n"] is None and afuera["entrada"] is None and "fuera" in afuera["motivo"]
    assert sin_manual["n"] is None
    d = delante["entrada"]["datos"]
    assert d["enlaces_recortados"] == 0 and d["longitud_aplicada_m"] == d["longitud_dibujada_m"]
    s = sobre["entrada"]["datos"]
    assert s["enlaces_recortados"] > 0 and s["longitud_aplicada_m"] < s["longitud_dibujada_m"] and s["celdas_mineral"] > 0
    assert "alcanzadas" in sobre["motivo"]
    assert viento["t_vigor_min"] == 120.0 and viento["entrada"]["datos"]["vel_ms"] == round(20 / 3.6, 6)
    assert vuelta["t_vigor_min"] == 240.0
    c = en_pausa["corrida"]
    assert [b["tipo"] for b in c["bitacora"]] == ["pausa", "cortafuego", "cortafuego", "viento_manual", "reanudacion",
                                                  "pausa", "viento_manual", "reanudacion"]
    assert intervenciones.verificar_cadena(c["bitacora_raiz"], c["bitacora"]) == (True, None)
    # lo que queda para la corrida offline, coherente con la bitácora
    carpeta = en_pausa["carpeta"] / barreras_v31.CARPETA
    for n, datos in ((1, d), (2, s)):
        z = np.load(carpeta / f"cortafuego_{n:02d}.npz")
        assert intervenciones.sha256_indices(z["enlaces"]) == datos["enlaces_sha256"] and len(z["enlaces"]) == datos["enlaces"]
    z = np.load(carpeta / "barreras_enlaces.npz")
    assert z["codigos"].shape == (1671, 1672, 16) and list(z["ancho_m"]) == list(barreras_v31.ANCHOS_TAB)
    assert int(np.count_nonzero(z["codigos"])) == d["enlaces"] + s["enlaces"] - int(
        len(np.intersect1d(np.load(carpeta / "cortafuego_01.npz")["enlaces"], np.load(carpeta / "cortafuego_02.npz")["enlaces"])))
    assert int(len(np.load(carpeta / "suelo_mineral.npz")["celdas"])) == s["celdas_mineral"]
    horas = (carpeta / "viento_horario.csv").read_text(encoding="utf-8").splitlines()[1:]
    assert [h.split(",")[0] for h in horas] == ["2024-09-18 17:00:00+00:00", "2024-09-18 18:00:00+00:00"]
    res = c["resultados"]["intervenciones_v31"]
    assert res["cortafuegos"] == 2 and res["horas_viento_manual"] == 2
    # nada fuera de la carpeta de la corrida: el producto compartido no cambió (ver también la prueba de los códigos)
    assert not (en_pausa["carpeta"] / barreras_v31.CARPETA / "insumo" / "barreras" / f"barreras_enlaces_{DOMINIO}.npz").exists()


def test_en_pausa_igual_al_trazo_recortado_desde_el_inicio(en_pausa):
    offline, info = _offline(en_pausa["tmp"] / "offline", en_pausa["carpeta"])
    print(f"app {en_pausa['s']:.1f} s; espejo y offline: {info}")
    assert info["barreras"] and len(info["reemplazados"]) == 3
    assert _distintas(_llegada(en_pausa["carpeta"]), offline) == 0


def test_reproduccion_desde_la_bitacora(en_pausa):
    """Comparación A de E-E3-4: el proceso repite la corrida aplicando su bitácora; misma cadena y 0 celdas distintas."""
    original = en_pausa["corrida"]
    corrida = {k: original[k] for k in ("formato", "motor", "base", "configuracion") if k in original}
    corrida["reproduccion"] = {"de": "app", "raiz": original["bitacora_raiz"], "bitacora": original["bitacora"]}
    carpeta = en_pausa["tmp"] / "reproduccion"
    r = _correr(carpeta, "", 0, corrida=corrida)
    rep = r["corrida"]["resultados"]["reproduccion"]
    print(f"reproducción {r['s']:.1f} s: {rep}")
    assert rep["cadena_igual"] and rep["sin_aplicar"] == []
    assert _distintas(_llegada(en_pausa["carpeta"]), _llegada(carpeta)) == 0


def test_viento_manual_en_pausa_igual_a_la_serie_editada(tmp_path):
    guion = [(120, [{"tipo": "viento_manual", "datos": VIENTO}]), (240, [{"tipo": "viento_manual", "datos": PRONOSTICO}])]
    app = _correr(tmp_path / "app", "v3.1-libre", 6, guion=guion)
    offline, info = _offline(tmp_path / "offline", tmp_path / "app")
    print(f"app {app['s']:.1f} s; espejo y offline: {info}")
    assert not info["barreras"] and info["reemplazados"] == [str(Path("meteo") / next(
        (REPO / "datos" / "inputSimulacion" / "meteo").glob(f"{EVENTO}_*_dominio.csv")).name)]
    assert _distintas(_llegada(tmp_path / "app"), offline) == 0
    # y el viento manual hace algo: sin él la corrida es otra
    sin = _correr(tmp_path / "sin", "v3.1-libre", 6)
    assert _distintas(_llegada(tmp_path / "app"), _llegada(tmp_path / "sin")) > 0
