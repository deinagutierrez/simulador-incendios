"""Pruebas del núcleo de las intervenciones (fase F5, contrato 1.5): validación, bitácora encadenada, órdenes en bloque,
pausa con hora objetivo y reproducción desde la bitácora con el motor simulado.

Rápidas (segundos) y sin red. Las de los motores reales están en test_procesos.py.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
MOTORES = REPO / "app" / "motores"
sys.path.insert(0, str(MOTORES))

import intervenciones as iv  # noqa: E402
from control import BITACORA, Control  # noqa: E402

SIMULADO = MOTORES / "proceso_simulado.py"
PROCESO = MOTORES / "proceso.py"
RES = 30.0
LADO = 60
CENTRO = (3538140.0, 6392850.0)               # el del motor simulado cuando no se da ignición
XMIN = round((CENTRO[0] - LADO * RES / 2) / RES) * RES
YMAX = round((CENTRO[1] + LADO * RES / 2) / RES) * RES


def _xy(fila: float, col: float) -> list[float]:
    """Centro de una celda de la grilla del motor simulado, en EPSG:5345."""
    return [XMIN + (col + 0.5) * RES, YMAX - (fila + 0.5) * RES]


# Una línea de borde a borde 15 celdas al sur del foco (el fuego llega en 5 h) y otra al norte, que llega hasta 2 celdas
# del foco (a las 6 h ya está casi toda quemada).
LINEA_SUR = {"ancho_m": 10, "suelo_mineral": False, "xy_5345": [_xy(LADO / 2 + 15, 0), _xy(LADO / 2 + 15, LADO - 1)]}
LINEA_FOCO = {"ancho_m": 25, "suelo_mineral": True, "xy_5345": [_xy(LADO / 2 - 20, LADO / 2 + 0.3), _xy(LADO / 2 - 2, LADO / 2 + 0.3)]}


# ------------------------------------------------------------------------------------------------ validación
def test_validar_cortafuego_normaliza():
    e = iv.validar_entrada({"tipo": "cortafuego", "datos": {"ancho_m": 10.0, "xy_5345": [[3536000.123456, 6384600], [3536000.12, 6384600.0],
                                                                                      [3540000, 6384400.004]],
                                                            "longitud_aplicada_m": 5, "otra": 1}})
    d = e["datos"]
    assert d["ancho_m"] == 10 and isinstance(d["ancho_m"], int) and d["suelo_mineral"] is False
    assert d["xy_5345"] == [[3536000.12, 6384600.0], [3540000.0, 6384400.0]]          # 0,01 m y sin repetidos
    assert d["longitud_dibujada_m"] == round(float(np.hypot(3999.88, 200.0)), 2)
    assert set(d) == {"ancho_m", "suelo_mineral", "xy_5345", "longitud_dibujada_m"}        # lo del motor se descarta
    assert iv.validar_entrada(e) == e                                                   # idempotente


@pytest.mark.parametrize("entrada, texto", [
    ({"tipo": "cortafuego"}, "falta `datos`"),
    ({"tipo": "cortafuego", "datos": {"ancho_m": 12, "xy_5345": [[0, 0], [1, 1]]}}, "ancho_m"),
    ({"tipo": "cortafuego", "datos": {"ancho_m": 10, "xy_5345": [[0, 0]]}}, "al menos dos puntos"),
    ({"tipo": "cortafuego", "datos": {"ancho_m": 10, "xy_5345": [[0, 0], [0.001, 0]]}}, "un solo punto"),
    ({"tipo": "cortafuego", "datos": {"ancho_m": 10, "suelo_mineral": "si", "xy_5345": [[0, 0], [1, 1]]}}, "suelo_mineral"),
    ({"tipo": "cortafuego", "datos": {"ancho_m": 10, "xy_5345": [[0, 0], [float("nan"), 1]]}}, "finito"),
    ({"tipo": "viento_manual", "datos": {"vel_kmh": 300, "dir_desde": 10}}, "vel_kmh"),
    ({"tipo": "viento_manual", "datos": {"vel_kmh": 20, "dir_desde": -5}}, "dir_desde"),
    ({"tipo": "viento_manual", "datos": {"modo": "otro"}}, "modo"),
    ({"tipo": "lluvia", "datos": {}}, "desconocido"),
])
def test_entradas_invalidas(entrada, texto):
    with pytest.raises(ValueError, match=texto):
        iv.validar_entrada(entrada)


def test_validar_viento():
    assert iv.validar_entrada({"tipo": "viento_manual", "datos": {"vel_kmh": 20, "dir_desde": 360}})["datos"] == {"vel_kmh": 20.0, "dir_desde": 0.0}
    assert iv.validar_entrada({"tipo": "viento_manual", "datos": {"modo": "pronostico"}})["datos"] == {"modo": "pronostico"}
    # se redondea antes de pasar a 0-<360: 359,999 no puede quedar en 360
    assert iv.validar_viento({"vel_kmh": 5, "dir_desde": 359.999})["dir_desde"] == 0.0
    assert iv.validar_viento({"vel_kmh": 5, "dir_desde": 10.123})["dir_desde"] == 10.12


@pytest.mark.parametrize("t, ok", [("2024-09-18T15:00:00Z", True), ("2024-09-18T15:00:00+00:00", True), (None, True),
                                   ("2024-09-18T12:00:00-03:00", True), ("2024-09-18T15:30:00Z", False),
                                   ("2024-09-18T15:00:10Z", False), ("2024-09-18T15:00:00+05:30", False), ("ayer", False)])
def test_revisar_t_inicio(t, ok):
    if ok:
        iv.revisar_t_inicio(t)
    else:
        with pytest.raises(ValueError):
            iv.revisar_t_inicio(t)


# ------------------------------------------------------------------------------------------------ hash
def test_canon_normaliza_numeros():
    assert iv.canon({"b": 360.0, "a": [1.0, 2.5]}) == iv.canon({"a": [1, 2.5], "b": 360})
    assert iv.canon({"ñ": True}) == '{"ñ":true}'.encode("utf-8")
    with pytest.raises(ValueError):
        iv.canon({"x": float("nan")})


def test_raiz_ignora_lo_que_cambia_al_reproducir():
    a = {"formato": "f", "id": "1", "creada_utc": "x", "grupo": "g", "motor": "simulado", "configuracion": {"horas": 6, "cortafuegos": []},
         "programa": {"version": "1", "congelado_sha256": "abc"}, "advertencias": ["x"], "bitacora": [1], "resultados": {}}
    b = {**a, "id": "2", "creada_utc": "y", "grupo": None, "configuracion": {"horas": 6.0}, "advertencias": [],
         "programa": {"version": "2", "congelado_sha256": "abc"}, "reproduccion": {"de": "1"}}
    assert iv.raiz(a) == iv.raiz(b)
    assert iv.raiz(a) != iv.raiz({**a, "programa": {"congelado_sha256": "otro"}})
    assert iv.raiz(a) != iv.raiz({**a, "configuracion": {"horas": 7}})


class _Ordenes:
    """Una tubería para mandarle órdenes a un Control en el mismo proceso."""

    def __init__(self):
        self.r, self.w = os.pipe()

    def mandar(self, *ordenes: dict) -> None:
        os.write(self.w, "".join(json.dumps(o) + "\n" for o in ordenes).encode("utf-8"))


def _control(tmp_path: Path, aplicar=None, corrida: dict | None = None):
    canal = _Ordenes()
    avisos = io.StringIO()
    c = Control(tmp_path, avisos, canal.r)
    c.preparar(corrida or {"motor": "simulado", "configuracion": {"horas": 6}})
    c.aplicar = aplicar
    leer = lambda: [json.loads(x) for x in avisos.getvalue().splitlines()]            # noqa: E731
    return c, canal, leer


def _aplicar_eco(entrada, t):
    if entrada["tipo"] == "cortafuego":
        return {"estado": "recortada", "t_vigor_min": t, "motivo": "prueba", "datos": {"longitud_aplicada_m": 12.5}}
    return {"estado": "aceptada", "t_vigor_min": t, "pleno_min": t + 60, "motivo": "", "datos": {}}


VIENTO = {"tipo": "viento_manual", "datos": {"vel_kmh": 20.0, "dir_desde": 87.0}}
CORTE = {"tipo": "cortafuego", "datos": LINEA_SUR}


def test_bloque_pausar_intervenir_reanudar(tmp_path):
    c, canal, avisos = _control(tmp_path, _aplicar_eco)
    canal.mandar({"orden": "pausar"}, {"orden": "intervenir", "ref": "a", "entrada": VIENTO},
                 {"orden": "intervenir", "ref": "b", "entrada": CORTE}, {"orden": "intervenir", "ref": "c", "entrada": {"tipo": "x"}},
                 {"orden": "reanudar"})
    assert c.atender(120.0) is False
    tipos = [b["tipo"] for b in c.bitacora]
    assert tipos == ["pausa", "viento_manual", "cortafuego", "reanudacion"]          # la rechazada no entra
    a = {x.get("ref"): x for x in avisos() if x["aviso"] == "intervencion"}
    assert a["a"]["estado"] == "aceptada" and a["a"]["pleno_min"] == 180.0 and a["a"]["n"] == 2
    assert a["b"]["estado"] == "recortada" and a["b"]["entrada"] == c.bitacora[2]
    assert c.bitacora[2]["datos"]["longitud_aplicada_m"] == 12.5 and c.bitacora[2]["datos"]["ancho_m"] == 10
    assert a["c"]["estado"] == "rechazada" and a["c"]["n"] is None
    assert [x["aviso"] for x in avisos()][0] == "pausado" and avisos()[0]["entrada"]["n"] == 1
    # escrita en el momento, igual a la que tiene en memoria, y la cadena verifica
    en_disco = [json.loads(x) for x in (tmp_path / BITACORA).read_text(encoding="utf-8").splitlines()]
    assert en_disco == c.bitacora
    assert iv.verificar_cadena(c.raiz, c.bitacora) == (True, None)


def test_sin_aplicar_se_rechaza(tmp_path):
    c, canal, avisos = _control(tmp_path, None)
    canal.mandar({"orden": "pausar"}, {"orden": "intervenir", "ref": 7, "entrada": VIENTO}, {"orden": "reanudar"})
    c.atender(60.0)
    i = [x for x in avisos() if x["aviso"] == "intervencion"][0]
    assert i["ref"] == 7 and i["estado"] == "rechazada" and "no acepta" in i["motivo"]
    assert [b["tipo"] for b in c.bitacora] == ["pausa", "reanudacion"]


def test_intervenir_fuera_de_pausa_se_rechaza(tmp_path):
    c, canal, avisos = _control(tmp_path, _aplicar_eco)
    canal.mandar({"orden": "intervenir", "ref": "x", "entrada": VIENTO})
    c.atender(60.0)
    assert avisos()[0]["estado"] == "rechazada" and "en pausa" in avisos()[0]["motivo"] and c.bitacora == []


def test_aplicar_que_falla_se_rechaza(tmp_path):
    def falla(entrada, t):
        raise RuntimeError("se rompió")
    c, canal, avisos = _control(tmp_path, falla)
    canal.mandar({"orden": "pausar"}, {"orden": "intervenir", "ref": "x", "entrada": VIENTO}, {"orden": "reanudar"})
    c.atender(60.0)
    i = [x for x in avisos() if x["aviso"] == "intervencion"][0]
    assert i["estado"] == "rechazada" and "se rompió" in i["motivo"]


def test_pausar_en_t_sim_min(tmp_path):
    c, canal, avisos = _control(tmp_path, _aplicar_eco)
    canal.mandar({"orden": "pausar", "en_t_sim_min": 180}, {"orden": "intervenir", "ref": "v", "entrada": VIENTO}, {"orden": "reanudar"})
    for t in (0.0, 60.0, 120.0):
        assert c.atender(t) is False
        assert c.bitacora == [] and avisos() == []             # todo espera a la hora pedida
    assert c.atender(180.0) is False
    assert [(b["tipo"], b["t_sim_min"]) for b in c.bitacora] == [("pausa", 180.0), ("viento_manual", 180.0), ("reanudacion", 180.0)]
    assert c.atender(240.0) is False and len(c.bitacora) == 3


def test_detener_no_espera_a_la_pausa_futura(tmp_path):
    c, canal, _ = _control(tmp_path, _aplicar_eco)
    canal.mandar({"orden": "pausar", "en_t_sim_min": 600}, {"orden": "intervenir", "entrada": VIENTO}, {"orden": "detener"})
    assert c.atender(60.0) is True
    assert [b["tipo"] for b in c.bitacora] == ["detencion"]


def test_hash_detecta_una_edicion_y_resiste_la_ida_y_vuelta(tmp_path):
    c, canal, _ = _control(tmp_path, _aplicar_eco)
    canal.mandar({"orden": "pausar"}, {"orden": "intervenir", "entrada": CORTE}, {"orden": "intervenir", "entrada": VIENTO},
                 {"orden": "reanudar"})
    c.atender(360.0)
    # ida y vuelta como la guarda proceso.py, y como la escribiría JavaScript (360.0 → 360)
    vuelta = json.loads(json.dumps(c.bitacora, indent=1, ensure_ascii=False, default=str))
    assert iv.verificar_cadena(c.raiz, vuelta) == (True, None)
    js = json.loads(json.dumps(vuelta).replace("360.0", "360"))
    assert js[0]["t_sim_min"] == 360 and iv.verificar_cadena(c.raiz, js) == (True, None)
    editada = json.loads(json.dumps(vuelta))
    editada[1]["datos"]["ancho_m"] = 25
    assert iv.verificar_cadena(c.raiz, editada) == (False, 2)
    sin_una = vuelta[:1] + vuelta[2:]
    assert iv.verificar_cadena(c.raiz, sin_una)[0] is False
    assert iv.verificar_cadena("otra raiz", vuelta) == (False, 1)


def test_reproduccion_en_control(tmp_path):
    corrida = {"motor": "simulado", "configuracion": {"horas": 6}}
    (tmp_path / "a").mkdir()
    c, canal, _ = _control(tmp_path / "a", _aplicar_eco, corrida)
    canal.mandar({"orden": "pausar", "en_t_sim_min": 120}, {"orden": "intervenir", "entrada": CORTE}, {"orden": "reanudar"},
                 {"orden": "pausar", "en_t_sim_min": 240}, {"orden": "intervenir", "entrada": VIENTO}, {"orden": "reanudar"})
    for t in (0.0, 60.0, 120.0, 180.0, 240.0):
        assert c.atender(t) is False
    canal.mandar({"orden": "detener"})
    assert c.atender(300.0) is True
    original = json.loads(json.dumps(c.bitacora))
    assert [b["tipo"] for b in original] == ["pausa", "cortafuego", "reanudacion", "pausa", "viento_manual", "reanudacion",
                                             "detencion"]
    (tmp_path / "b").mkdir()
    rep = {**corrida, "reproduccion": {"de": "a", "raiz": c.raiz, "bitacora": original}}
    r, canal_r, avisos_r = _control(tmp_path / "b", _aplicar_eco, rep)
    canal_r.mandar({"orden": "pausar"}, {"orden": "intervenir", "ref": "nueva", "entrada": VIENTO}, {"orden": "reanudar"})
    t = 0.0
    while not r.atender(t):
        t += 60.0
    assert t == 300.0
    informe = r.informe_reproduccion()
    assert informe["cadena_igual"] is True and informe["raiz_igual"] and informe["original_integra"] and informe["sin_aplicar"] == []
    assert [b["hash"] for b in r.bitacora] == [b["hash"] for b in original]
    nueva = [x for x in avisos_r() if x.get("ref") == "nueva"][0]
    assert nueva["estado"] == "rechazada" and "reproducción" in nueva["motivo"]


# ------------------------------------------------------------------------------------------------ motor simulado
def _carpeta(tmp: Path, configuracion: dict | None = None, horas: int = 12, **extra) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    corrida = {"formato": "incendios_sl.corrida/1.2", "id": tmp.name, "motor": "simulado",
               "programa": {"congelado_sha256": "prueba"},
               "configuracion": {"horas": horas, **(configuracion or {})}, "simulado": {"s_por_hora": 0.0, "lado": LADO}, **extra}
    (tmp / "corrida.json").write_text(json.dumps(corrida), encoding="utf-8")
    return tmp


def _correr(guion: Path, carpeta: Path, ordenes: list[dict] | None = None) -> tuple[list[dict], int]:
    """Lanza el proceso con las órdenes ya escritas en su entrada estándar (se leen cuando corresponde)."""
    p = subprocess.Popen([sys.executable, str(guion), "--corrida", str(carpeta)], cwd=REPO,
                         env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1"),
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
    guardian = threading.Timer(60, p.kill)
    guardian.daemon = True
    guardian.start()
    p.stdin.write("".join(json.dumps(o) + "\n" for o in ordenes or []))
    p.stdin.flush()
    avisos = [json.loads(linea) for linea in p.stdout]
    p.wait(timeout=30)
    guardian.cancel()
    p.stdin.close()
    return avisos, p.returncode


def _leer(carpeta: Path) -> tuple[dict, np.ndarray]:
    return (json.loads((carpeta / "corrida.json").read_text(encoding="utf-8")), np.load(carpeta / "t_llegada_parcial.npy"))


def _iguales(a: np.ndarray, b: np.ndarray) -> bool:
    return a.shape == b.shape and bool(((a == b) | (np.isnan(a) & np.isnan(b))).all())


ORDENES = [{"orden": "pausar", "en_t_sim_min": 180}, {"orden": "intervenir", "ref": "sur", "entrada": CORTE}, {"orden": "reanudar"},
           {"orden": "pausar", "en_t_sim_min": 360},
           {"orden": "intervenir", "ref": "foco", "entrada": {"tipo": "cortafuego", "datos": LINEA_FOCO}},
           {"orden": "intervenir", "ref": "viento", "entrada": VIENTO}, {"orden": "reanudar"}]


def test_simulado_intervenciones_y_reproduccion(tmp_path):
    libre, codigo = _correr(SIMULADO, _carpeta(tmp_path / "libre"))
    assert codigo == 0
    _, huella_libre = _leer(tmp_path / "libre")

    avisos, codigo = _correr(SIMULADO, _carpeta(tmp_path / "original"), ORDENES)
    assert codigo == 0, avisos[-1]
    corrida, huella = _leer(tmp_path / "original")
    resp = {a["ref"]: a for a in avisos if a["aviso"] == "intervencion"}
    assert resp["sur"]["estado"] == "aceptada" and resp["sur"]["t_vigor_min"] == 180.0
    assert resp["foco"]["estado"] == "recortada" and resp["foco"]["entrada"]["datos"]["celdas_recortadas"] > 0
    assert resp["viento"]["estado"] == "aceptada"
    bit = corrida["bitacora"]
    assert [b["tipo"] for b in bit] == ["pausa", "cortafuego", "reanudacion", "pausa", "cortafuego", "viento_manual", "reanudacion"]
    assert [json.loads(x) for x in (tmp_path / "original" / BITACORA).read_text(encoding="utf-8").splitlines()] == bit
    assert corrida["bitacora_raiz"] == iv.raiz(corrida)
    assert iv.verificar_cadena(corrida["bitacora_raiz"], bit) == (True, None)
    sur = bit[1]["datos"]
    assert sur["longitud_dibujada_m"] == round((LADO - 1) * RES, 2) and sur["longitud_aplicada_m"] > 0 and sur["celdas"] == LADO
    # el cortafuego frenó el fuego: al sur de la línea no quemó nada, y antes de la hora 3 todo es igual
    fila = LADO // 2 + 15
    assert np.isnan(huella[fila:, :]).all() and not np.isnan(huella_libre[fila + 1:, :]).all()
    temprano = lambda h: np.where(h <= 180.0, h, np.nan)                                      # noqa: E731
    assert _iguales(temprano(huella), temprano(huella_libre))

    # reproducción: copia de la configuración tal cual, con la bitácora original; sin órdenes
    base = {k: corrida[k] for k in ("formato", "motor", "programa", "configuracion", "simulado")}
    carpeta_r = tmp_path / "reproduccion"
    carpeta_r.mkdir()
    (carpeta_r / "corrida.json").write_text(json.dumps({**base, "id": "otra", "reproduccion": {
        "de": corrida["id"], "raiz": corrida["bitacora_raiz"], "bitacora": bit}}), encoding="utf-8")
    avisos_r, codigo = _correr(SIMULADO, carpeta_r)
    assert codigo == 0, avisos_r[-1]
    corrida_r, huella_r = _leer(carpeta_r)
    assert [b["hash"] for b in corrida_r["bitacora"]] == [b["hash"] for b in bit]
    assert corrida_r["resultados"]["reproduccion"]["cadena_igual"] is True
    assert _iguales(huella_r, huella)


def test_simulado_cortafuego_antes_de_iniciar_igual_que_a_t0(tmp_path):
    antes, codigo = _correr(SIMULADO, _carpeta(tmp_path / "antes", {"cortafuegos": [LINEA_SUR, LINEA_FOCO]}))
    assert codigo == 0, antes[-1]
    corrida_a, huella_a = _leer(tmp_path / "antes")
    ini = corrida_a["resultados"]["cortafuegos_iniciales"]
    assert [x["estado"] for x in ini] == ["aceptada", "aceptada"]           # a t = 0 solo quemó el foco
    assert corrida_a["bitacora"] == []
    en_t0 = [{"orden": "pausar", "en_t_sim_min": 0}, {"orden": "intervenir", "entrada": CORTE},
             {"orden": "intervenir", "entrada": {"tipo": "cortafuego", "datos": LINEA_FOCO}}, {"orden": "reanudar"}]
    avisos, codigo = _correr(SIMULADO, _carpeta(tmp_path / "t0"), en_t0)
    assert codigo == 0, avisos[-1]
    _, huella_0 = _leer(tmp_path / "t0")
    assert _iguales(huella_a, huella_0)


def test_t_inicio_con_minutos_se_rechaza_en_el_simulado(tmp_path):
    avisos, codigo = _correr(SIMULADO, _carpeta(tmp_path / "c", {"t_inicio_utc": "2026-01-01T12:30:00Z"}))
    assert codigo == 1 and avisos[-1]["aviso"] == "error" and avisos[-1]["fatal"] and "hora en punto" in avisos[-1]["mensaje"]


def test_t_inicio_con_minutos_se_rechaza_en_el_proceso_motor(tmp_path):
    """Se rechaza antes de cargar el motor: la prueba no corre ningún motor."""
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "corrida.json").write_text(json.dumps({
        "motor": "v4.0", "base": {"definicion": {"evento": "SL-2024-LASLAGUNAS", "horas": 3}},
        "configuracion": {"t_inicio_utc": "2024-09-18T15:30:00Z"}}), encoding="utf-8")
    avisos, codigo = _correr(PROCESO, tmp_path)
    assert codigo == 1 and avisos[-1]["aviso"] == "error" and avisos[-1]["fatal"] and "hora en punto" in avisos[-1]["mensaje"]


def test_cortafuego_invalido_en_la_configuracion_se_rechaza(tmp_path):
    avisos, codigo = _correr(SIMULADO, _carpeta(tmp_path / "c", {"cortafuegos": [{"ancho_m": 7, "xy_5345": [[0, 0], [1, 1]]}]}))
    assert codigo == 1 and "cortafuego 1" in avisos[-1]["mensaje"]
