"""Intervenciones en el motor v4.0 (fase F5, contrato 1.5; D-E3-28, puntos 4-6, 11-14 y 16): app/motores/barreras_v40.py y
motor_v40.py.

Dos partes:
- en el mismo proceso, sobre una grilla sintética del propio motor (`simulador.sintetico`, segundos): un cortafuego en pausa
  da lo mismo que su geometría reproducible (la de `cortafuegos_aplicados.geojson`) cargada desde el inicio, con 0 celdas
  distintas en tiempo de llegada, estado, cruces y bloqueos, en varios casos (trazo que cruza lo quemado, diagonal, suelo
  mineral, modo de barrera umbral); el viento manual en pausa da lo mismo que `meteo_editada.csv` desde el inicio (también
  con humedad `ffmc_vanwagner`, que usa el viento); los rechazos dejan el motor como estaba;
- con el proceso motor real sobre Las Lagunas 2024, 8 h (unos segundos por corrida): sin trazos la definición no cambia;
  cortafuegos y viento en pausa dan 0 celdas distintas contra `correr_escenario.py` con los archivos offline de la carpeta
  (comparación B de E-E3-4) y contra la reproducción desde la bitácora (comparación A); un trazo antes de iniciar da lo
  mismo que el mismo trazo aplicado en la pausa de t = 0.

Sin red. Las corridas del proceso que se comparan offline van en resultados/app/_prueba_v40_*/ (v4.0 solo lee insumos dentro
del repositorio) y se borran al terminar.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import numpy as np
import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
MOTORES = REPO / "app" / "motores"
PROCESO = MOTORES / "proceso.py"
sys.path.insert(0, str(MOTORES))
# al final: solo hace falta el paquete `simulador` de v4.0, y así no le gana a ningún `incendios_sl` de otra prueba
sys.path.append(str(REPO / "src" / "v4.0" / "src"))

import intervenciones as iv  # noqa: E402

TIEMPOS: dict[str, float] = {}


def _medir(nombre: str, t0: float) -> None:
    TIEMPOS[nombre] = round(time.perf_counter() - t0, 2)
    print(f"[tiempo] {nombre}: {TIEMPOS[nombre]} s")


def _distintas(a: np.ndarray, b: np.ndarray) -> int:
    return int((~((a == b) | (np.isnan(a) & np.isnan(b)))).sum())


# ================================================================================================ grilla sintética
N = 121
RES = 30.0
C = N // 2
T0 = "2024-01-01T12:00:00-03:00"


def _xy(puntos) -> list[list[float]]:
    """(col, fila) en celdas → EPSG:5345 de la grilla sintética (xmin = 0, ymax = N·RES)."""
    return [[round(c * RES, 2), round((N - f) * RES, 2)] for c, f in puntos]


def _sintetico():
    import barreras_v40 as bv
    from simulador import sintetico as S
    return bv, S


def _correr(capas, meteo, cfg, horas: float, al_pausar=None, horas_pausa=()):
    """Corre el autómata desde el centro; en cada hora de `horas_pausa`, antes del paso, llama a `al_pausar(au, t_min)`
    (lo mismo que hace `AutomataControlado` del conductor)."""
    import pandas as pd
    from simulador.ca.automata import Automata
    au = Automata(capas, meteo, cfg)
    t0 = pd.Timestamp(T0)
    au.preparar(t0, t0 + pd.Timedelta(hours=horas))
    au.encender(C, C, t0, "centro")
    for _ in range(int(round(horas * 60 / cfg["dt_min"]))):
        t = au.minutos(au.t)
        if al_pausar and abs(t / 60.0 - round(t / 60.0)) < 1e-9 and round(t / 60.0) in horas_pausa:
            al_pausar(au, t)
        au.paso_tiempo()
    return au


def _iguales(a, b) -> dict:
    return {"t_llegada": _distintas(a.t_llegada, b.t_llegada), "estado": int((a.estado != b.estado).sum()),
            "cruces": int((a.cruces_barrera != b.cruces_barrera).sum()),
            "bloqueos": int((a.bloqueos_barrera != b.bloqueos_barrera).sum())}


CERO = {"t_llegada": 0, "estado": 0, "cruces": 0, "bloqueos": 0}

# nombre: (trazos [(ancho, mineral, puntos (col, fila))], hora de la pausa, parámetros de barreras, vecindad)
CASOS = {
    "horizontal_cruza_lo_quemado": ([(10, False, [(10, C + 12.3), (110, C + 14.7)])], 2, None, 8),
    "diagonal": ([(6, False, [(C - 20, C - 15), (C + 25, C + 20)])], 3, None, 8),
    "diagonal_vecindad_16": ([(6, False, [(C - 20, C - 15), (C + 25, C + 20)])], 3, None, 16),
    "suelo_mineral": ([(25, True, [(20, C + 8), (100, C + 20)])], 2, None, 8),
    "norte_sur_por_el_foco": ([(15, False, [(C - 3.3, 10.2), (C + 4.1, 110.8)])], 3, None, 8),
    "dos_trazos_umbral": ([(3, False, [(5, C + 5.5), (115, C + 6.5)]), (25, False, [(C + 8.2, 5), (C + 9.7, 115)])], 2,
                          {"modo": "umbral"}, 8),
}


@pytest.mark.parametrize("nombre", sorted(CASOS))
def test_cortafuego_en_pausa_igual_a_su_geometria_desde_el_inicio(nombre, tmp_path):
    bv, S = _sintetico()
    from simulador.io.capas import rasterizar_barreras_extra
    trazos, h, barreras, vecindad = CASOS[nombre]
    cfg = S.config_sintetica(vecindad=vecindad, parametros={"barreras": barreras or {"modo": "probabilistico"}})
    meteo = S.meteo_constante(T0, horas=24, viento_kmh=25, viento_dir_deg=20)
    interv = bv.Intervenciones(tmp_path, [])
    respuestas = []

    def pausar(au, t):
        interv.au = au
        for ancho, mineral, puntos in trazos:
            e = iv.validar_entrada({"tipo": "cortafuego", "datos": {"ancho_m": ancho, "suelo_mineral": mineral,
                                                                   "xy_5345": _xy(puntos)}})
            respuestas.append(interv.aplicar(e, t))

    t0 = time.perf_counter()
    en_pausa = _correr(S.capas_sinteticas(N), meteo, cfg, 8, pausar, {h})
    _medir(f"sintético {nombre}, 8 h con pausa", t0)
    assert [r["estado"] for r in respuestas] and all(r["estado"] in ("aceptada", "recortada") for r in respuestas), respuestas
    for r in respuestas:
        d = r["datos"]
        assert r["t_vigor_min"] == 60.0 * h and d["celdas"] > 0 and d["geometria_offline"] in ("polilinea", "centros")
        assert len(d["celdas_sha256"]) == 64 and d["longitud_aplicada_m"] > 0
        iv.canon(d)                                       # entra en la bitácora (JSON sin NaN)
    if nombre in ("horizontal_cruza_lo_quemado", "norte_sur_por_el_foco"):
        assert respuestas[0]["estado"] == "recortada" and respuestas[0]["datos"]["celdas_recortadas"] > 0

    # desde el inicio, con lo que quedó en la carpeta para la corrida offline
    capas = S.capas_sinteticas(N)
    rasterizar_barreras_extra(capas, tmp_path / bv.CORTAFUEGOS_OFFLINE)
    mineral = any(m for _, m, _ in trazos)
    assert (tmp_path / bv.MODIFICADOR_OFFLINE).exists() == mineral
    if mineral:
        capas.modificador = bv.leer_modificador(tmp_path / bv.MODIFICADOR_OFFLINE, capas.base)
    desde_inicio = _correr(capas, meteo, cfg, 8)
    assert _iguales(en_pausa, desde_inicio) == CERO
    # y el cortafuego hace algo (si no, la comparación no probaría nada)
    sin = _correr(S.capas_sinteticas(N), meteo, cfg, 8)
    assert _distintas(en_pausa.t_llegada, sin.t_llegada) > 0


def test_el_recorte_del_plan_no_alcanza():
    """D-E3-28, punto 13: sin quitar las intermedias de diagonales entre celdas afectadas, el recorte deja celdas que la
    corrida desde el inicio ya habría sorteado. Se comprueba que la regla agrega celdas a quitar en un trazo por el foco."""
    bv, S = _sintetico()
    cfg = S.config_sintetica()
    meteo = S.meteo_constante(T0, horas=24, viento_kmh=25, viento_dir_deg=20)
    au = _correr(S.capas_sinteticas(N), meteo, cfg, 3)
    g = au.capas.grilla
    mascara = bv.rasterizar(g, [bv.linea_en_grilla(_xy([(C - 3.3, 10.2), (C + 4.1, 110.8)]), g.crs)], [15.0]) > 0
    afectada = np.isfinite(au.t_llegada)
    final = bv.recortar(mascara, afectada, au.df, au.dc, au.inter)
    assert not (final & afectada).any()
    assert int((mascara & ~afectada & ~final).sum()) > 0


@pytest.mark.parametrize("metodo", ["retardo", "ffmc_vanwagner"])
def test_viento_en_pausa_igual_a_la_serie_editada(metodo, tmp_path):
    bv, S = _sintetico()
    from simulador.io.meteo import SerieMeteo
    cfg = S.config_sintetica(parametros={"humedad": {"metodo_muerto": metodo}})
    meteo = S.meteo_constante(T0, horas=24, viento_kmh=25, viento_dir_deg=20)
    interv = bv.Intervenciones(tmp_path, [])
    respuestas = []

    def pausar(au, t):
        interv.au = au
        datos = {"vel_kmh": 30, "dir_desde": 110} if t < 200 else {"modo": "pronostico"}
        respuestas.append(interv.aplicar(iv.validar_entrada({"tipo": "viento_manual", "datos": datos}), t))

    en_pausa = _correr(S.capas_sinteticas(N), meteo, cfg, 8, pausar, {2, 5})
    assert [r["estado"] for r in respuestas] == ["aceptada", "aceptada"]
    assert respuestas[0]["t_vigor_min"] == 120.0 and respuestas[0]["pleno_min"] == 180.0
    assert respuestas[0]["datos"]["desde_utc"] == "2024-01-01T18:00:00Z"      # la fila siguiente a la pausa (17 h UTC)
    editada = SerieMeteo.cargar(tmp_path / bv.METEO_OFFLINE)
    texto = (tmp_path / bv.METEO_OFFLINE).read_text(encoding="utf-8")
    assert "-03:00" in texto and "\r" not in texto
    # la serie del archivo es la que usó el motor, número por número
    assert np.array_equal(editada.t, en_pausa.meteo.t)
    assert np.array_equal(editada.u, en_pausa.meteo.u) and np.array_equal(editada.v, en_pausa.meteo.v)
    df = editada.df.set_index("timestamp")
    import pandas as pd
    assert df.loc[pd.Timestamp("2024-01-01T18:00:00Z"), "viento_dir_deg"] == 110.0
    assert df.loc[pd.Timestamp("2024-01-01T20:00:00Z"), "viento_dir_deg"] == 110.0       # hasta la pausa de las 5 h
    assert df.loc[pd.Timestamp("2024-01-01T21:00:00Z"), "viento_dir_deg"] == 20.0        # de vuelta al pronóstico
    assert df.loc[pd.Timestamp("2024-01-01T17:00:00Z"), "viento_dir_deg"] == 20.0        # lo anterior no cambia
    desde_inicio = _correr(S.capas_sinteticas(N), editada, cfg, 8)
    assert _iguales(en_pausa, desde_inicio) == CERO
    sin = _correr(S.capas_sinteticas(N), meteo, cfg, 8)
    assert _distintas(en_pausa.t_llegada, sin.t_llegada) > 0


def _estado(au) -> dict:
    c = au.capas
    out = {k: getattr(au, k).copy() for k in ("factor_carga", "estado", "es_camino", "umbral_camino", "t_llegada")}
    out |= {"camino_ancho": c.camino_ancho.copy(), "camino_tipo": c.camino_tipo.copy(),
            "modificador": None if c.modificador is None else c.modificador.copy(), "meteo_u": au.meteo.u.copy()}
    return out


def _mismo_estado(a: dict, b: dict) -> bool:
    for k in a:
        if (a[k] is None) != (b[k] is None):
            return False
        if a[k] is not None and not np.array_equal(a[k], b[k], equal_nan=a[k].dtype.kind == "f"):
            return False
    return True


def test_rechazos_dejan_el_motor_como_estaba(tmp_path, monkeypatch):
    bv, S = _sintetico()
    meteo = S.meteo_constante(T0, horas=24, viento_kmh=25, viento_dir_deg=20)
    au = _correr(S.capas_sinteticas(N), meteo, S.config_sintetica(), 3)
    interv = bv.Intervenciones(tmp_path, [])
    interv.au = au
    t = 180.0
    antes = _estado(au)

    def cortafuego(puntos, ancho=10, mineral=False):
        return iv.validar_entrada({"tipo": "cortafuego", "datos": {"ancho_m": ancho, "suelo_mineral": mineral,
                                                                 "xy_5345": _xy(puntos)}})

    # fuera de la grilla
    r = interv.aplicar(cortafuego([(N + 50, 10), (N + 60, 20)]), t)
    assert r["estado"] == "rechazada" and "no toca" in r["motivo"]
    # todo sobre lo ya quemado
    r = interv.aplicar(cortafuego([(C - 0.4, C - 0.4), (C + 0.4, C + 0.4)]), t)
    assert r["estado"] == "rechazada" and "ya alcanzó" in r["motivo"]
    # viento con un campo externo
    au.viento.externo, externo = {"u": None, "v": None}, au.viento.externo
    r = interv.aplicar(iv.validar_entrada({"tipo": "viento_manual", "datos": {"vel_kmh": 10, "dir_desde": 0}}), t)
    au.viento.externo = externo
    assert r["estado"] == "rechazada" and "externo" in r["motivo"]
    # una falla a mitad de camino (después de rasterizar) deja todo como estaba
    monkeypatch.setattr(bv, "actualizar_derivadas", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("falla de prueba")))
    with pytest.raises(RuntimeError):
        interv.aplicar(cortafuego([(10, C + 10), (110, C + 10)], mineral=True), t)
    monkeypatch.undo()
    assert _mismo_estado(antes, _estado(au)) and interv.en_pausa == [] and interv.mineral_pausa == []
    assert not (tmp_path / bv.CORTAFUEGOS_OFFLINE).exists() and not (tmp_path / bv.METEO_OFFLINE).exists()

    # vecindad 16: el suelo mineral en pausa se rechaza (el resto se acepta)
    au16 = _correr(S.capas_sinteticas(N), meteo, S.config_sintetica(vecindad=16), 3)
    interv16 = bv.Intervenciones(tmp_path / "v16", [])
    (tmp_path / "v16").mkdir()
    interv16.au = au16
    antes16 = _estado(au16)
    r = interv16.aplicar(cortafuego([(10, C + 10), (110, C + 10)], mineral=True), t)
    assert r["estado"] == "rechazada" and "vecindad 16" in r["motivo"]
    assert _mismo_estado(antes16, _estado(au16))
    assert interv16.aplicar(cortafuego([(10, C + 10), (110, C + 10)]), t)["estado"] in ("aceptada", "recortada")


# ================================================================================================ proceso real
DEFINICION = {"evento": "SL-2024-LASLAGUNAS", "hipotesis": 1, "horas": 8, "validar": False, "figuras": False}
POR_DEFECTO = {"variante": "barreras", "parar_en_cicatriz": "off"}
TOPE_S = 300
# A las 5 h el foco este ocupa x 3.542.280-3.542.610, y 6.388.620-6.389.430 y el oeste x 3.535.320-3.535.500,
# y 6.388.260-6.388.860; avanzan hacia el sur. Un trazo cruza el foco este (se recorta), otro va delante de él y uno a
# suelo mineral delante del foco oeste.
CRUZA_FOCO = {"ancho_m": 15, "suelo_mineral": False, "xy_5345": [[3541900.0, 6388700.0], [3543000.0, 6388760.0]]}
DELANTE = {"ancho_m": 10, "suelo_mineral": False, "xy_5345": [[3541800.0, 6387700.0], [3542500.0, 6387650.0],
                                                            [3543200.0, 6387720.0]]}
MINERAL = {"ancho_m": 6, "suelo_mineral": True, "xy_5345": [[3535000.0, 6388000.0], [3536100.0, 6387950.0]]}
# antes de iniciar: delante del foco este, lejos de los puntos de ignición
INICIAL = {"ancho_m": 10, "suelo_mineral": True, "xy_5345": [[3541900.0, 6388300.0], [3543100.0, 6388250.0]]}


def _entorno(version: str | None = None, resultados: Path | None = None) -> dict:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    env.pop("PYTHONPATH", None)
    if version:
        env["PYTHONPATH"] = str(REPO / "src" / version / "src")
    if resultados:
        env["INCENDIOS_SL_RESULTADOS"] = str(resultados)
    return env


def _leer(tif: Path) -> np.ndarray:
    import rasterio
    with rasterio.open(tif) as s:
        return s.read(1)


def _carpeta(carpeta: Path, configuracion: dict | None = None, reproduccion: dict | None = None) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    corrida = {"formato": "incendios_sl.corrida/1.0", "motor": "v4.0", "base": {"definicion": DEFINICION}}
    if configuracion:
        corrida["configuracion"] = configuracion
    if reproduccion:
        corrida["reproduccion"] = reproduccion
    (carpeta / "corrida.json").write_text(json.dumps(corrida), encoding="utf-8")
    return carpeta


def _correr_proceso(carpeta: Path, ordenes_iniciales: list[dict] | None = None, al_recibir=None) -> tuple[list[dict], dict]:
    """Lanza el proceso motor, le manda `ordenes_iniciales` en el acto y `al_recibir(aviso, mandar)` las que quiera
    después. Devuelve (avisos, corrida.json final)."""
    p = subprocess.Popen([sys.executable, str(PROCESO), "--corrida", str(carpeta)], cwd=REPO, env=_entorno(),
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding="utf-8", bufsize=1)
    guardian = threading.Timer(TOPE_S, p.kill)
    guardian.daemon = True
    guardian.start()

    def mandar(o: dict) -> None:
        p.stdin.write(json.dumps(o) + "\n")
        p.stdin.flush()

    for o in ordenes_iniciales or []:
        mandar(o)
    avisos = []
    for linea in p.stdout:
        a = json.loads(linea)
        avisos.append(a)
        if al_recibir:
            al_recibir(a, mandar)
    p.wait(timeout=60)
    guardian.cancel()
    err = p.stderr.read()
    assert p.returncode == 0, err[-3000:] + (carpeta / "proceso.log").read_text(encoding="utf-8", errors="replace")[-3000:]
    return avisos, json.loads((carpeta / "corrida.json").read_text(encoding="utf-8"))


def _intervenir(ref, tipo: str, datos: dict) -> dict:
    return {"orden": "intervenir", "ref": ref, "entrada": {"tipo": tipo, "datos": datos}}


@pytest.fixture(scope="module")
def en_repo():
    """Carpeta dentro de resultados/app/ (v4.0 solo lee insumos dentro del repositorio), que se borra al terminar."""
    carpeta = REPO / "resultados" / "app" / f"_prueba_v40_{uuid.uuid4().hex[:10]}"
    carpeta.mkdir(parents=True)
    yield carpeta
    shutil.rmtree(carpeta, ignore_errors=True)


@pytest.fixture(scope="module")
def con_pausas(en_repo):
    """Corrida de 8 h con tres cortafuegos en la pausa de las 5 h, viento manual a las 6 h y vuelta al pronóstico a las 7 h."""
    carpeta = _carpeta(en_repo / "pausas")
    plan = {300.0: [_intervenir("cruza", "cortafuego", CRUZA_FOCO), _intervenir("delante", "cortafuego", DELANTE),
                    _intervenir("mineral", "cortafuego", MINERAL)],
            360.0: [_intervenir("viento", "viento_manual", {"vel_kmh": 30, "dir_desde": 90})],
            420.0: [_intervenir("pronostico", "viento_manual", {"modo": "pronostico"})]}
    horas = sorted(plan)
    respuestas = {}

    def al_recibir(a, mandar):
        # en cada pausa del plan: las intervenciones, reanudar y pedir la pausa siguiente (las órdenes se procesan en orden)
        if a["aviso"] == "pausado" and a["t_sim_min"] in plan:
            for o in plan[a["t_sim_min"]]:
                mandar(o)
            mandar({"orden": "reanudar"})
            siguientes = [h for h in horas if h > a["t_sim_min"]]
            if siguientes:
                mandar({"orden": "pausar", "en_t_sim_min": siguientes[0]})
        elif a["aviso"] == "intervencion":
            respuestas[a["ref"]] = a

    t0 = time.perf_counter()
    avisos, corrida = _correr_proceso(carpeta, [{"orden": "pausar", "en_t_sim_min": horas[0]}], al_recibir)
    _medir("proceso v4.0 Las Lagunas 8 h con 5 intervenciones", t0)
    return {"carpeta": carpeta, "avisos": avisos, "corrida": corrida, "respuestas": respuestas}


def test_proceso_con_intervenciones_en_pausa(con_pausas):
    r = con_pausas["respuestas"]
    assert set(r) == {"cruza", "delante", "mineral", "viento", "pronostico"}, r
    assert r["cruza"]["estado"] == "recortada" and r["cruza"]["entrada"]["datos"]["celdas_recortadas"] > 0
    assert r["delante"]["estado"] == "aceptada" and r["mineral"]["estado"] == "aceptada"
    for ref in ("cruza", "delante", "mineral"):
        d = r[ref]["entrada"]["datos"]
        assert r[ref]["t_vigor_min"] == 300.0 and d["celdas"] > 0 and len(d["celdas_sha256"]) == 64
        assert 0 < d["longitud_aplicada_m"] <= d["longitud_dibujada_m"]
    assert r["viento"]["estado"] == "aceptada" and r["viento"]["t_vigor_min"] == 360.0 and r["viento"]["pleno_min"] == 420.0
    corrida = con_pausas["corrida"]
    assert [e["tipo"] for e in corrida["bitacora"]] == ["pausa", "cortafuego", "cortafuego", "cortafuego", "reanudacion",
                                                        "pausa", "viento_manual", "reanudacion",
                                                        "pausa", "viento_manual", "reanudacion"]
    assert iv.verificar_cadena(corrida["bitacora_raiz"], corrida["bitacora"]) == (True, None)
    res = corrida["resultados"]
    assert res["completa"] is True and "cortafuegos_iniciales" not in res
    assert res["archivos_offline"] == {"barreras_extra": "cortafuegos_aplicados.geojson",
                                       "meteo": "meteo_editada.csv", "modificador_combustible": "modificador_aplicado.tif"}
    # sin trazos antes de iniciar, la definición que corre el motor no cambia (identidad E-E3-1)
    base = yaml.safe_load((con_pausas["carpeta"] / "escenario_base.yaml").read_text(encoding="utf-8"))
    assert "mitigacion" not in base and not (con_pausas["carpeta"] / "cortafuegos.geojson").exists()
    # nada se escribió fuera de la carpeta de la corrida
    g = json.loads((con_pausas["carpeta"] / "cortafuegos_aplicados.geojson").read_text(encoding="utf-8"))
    assert [f["properties"]["ancho_m"] for f in g["features"]] == [15.0, 10.0, 6.0]


def test_offline_con_los_archivos_de_la_carpeta_da_lo_mismo(con_pausas, tmp_path):
    """Comparación B de E-E3-4 en chico: `correr_escenario.py` con `mitigacion` y `parche.meteo` desde el inicio."""
    carpeta = con_pausas["carpeta"]
    esc = {**DEFINICION, **POR_DEFECTO, "run_id": "offline_b",
           "mitigacion": {"barreras_extra": str(carpeta / "cortafuegos_aplicados.geojson"),
                          "modificador_combustible": str(carpeta / "modificador_aplicado.tif")},
           "parche": {"meteo": str(carpeta / "meteo_editada.csv")}}
    archivo = tmp_path / "offline_b.yaml"
    archivo.write_text(yaml.safe_dump(esc, sort_keys=False), encoding="utf-8")
    t0 = time.perf_counter()
    p = subprocess.run([sys.executable, "scripts/correr_escenario.py", "--archivo", str(archivo)], cwd=REPO / "src" / "v4.0",
                       env=_entorno("v4.0", tmp_path / "resultados"), capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    _medir("offline B v4.0 8 h", t0)
    assert p.returncode == 0, p.stdout[-2000:] + p.stderr[-2000:]
    offline = _leer(next((tmp_path / "resultados").rglob("hora_llegada_min.tif")))
    propio = _leer(carpeta / "salida" / "hora_llegada_min.tif")
    assert _distintas(propio, offline) == 0
    # y las intervenciones cambiaron el resultado (si no, la comparación no probaría nada)
    sin = _carpeta(tmp_path / "sin")
    _correr_proceso(sin)
    assert _distintas(propio, _leer(sin / "salida" / "hora_llegada_min.tif")) > 0


def test_reproduccion_desde_la_bitacora(con_pausas, tmp_path):
    """Comparación A de E-E3-4 en chico: el proceso aplica la bitácora en su hora; misma cadena y 0 celdas distintas."""
    original = con_pausas["corrida"]
    carpeta = _carpeta(tmp_path / "reproduccion",
                       reproduccion={"de": "pausas", "raiz": original["bitacora_raiz"], "bitacora": original["bitacora"]})
    t0 = time.perf_counter()
    _, corrida = _correr_proceso(carpeta)
    _medir("reproducción v4.0 8 h", t0)
    rep = corrida["resultados"]["reproduccion"]
    assert rep["cadena_igual"] is True and rep["sin_aplicar"] == [], rep
    assert _distintas(_leer(carpeta / "salida" / "hora_llegada_min.tif"),
                      _leer(con_pausas["carpeta"] / "salida" / "hora_llegada_min.tif")) == 0


def test_cortafuego_antes_de_iniciar_igual_que_en_la_pausa_de_t0(tmp_path):
    t0 = time.perf_counter()
    antes = _carpeta(tmp_path / "antes", configuracion={"cortafuegos": [INICIAL]})
    _, c_antes = _correr_proceso(antes)
    _medir("proceso v4.0 8 h con un trazo antes de iniciar", t0)
    respuestas = {}

    def al_recibir(a, mandar):
        if a["aviso"] == "intervencion":
            respuestas[a["ref"]] = a

    en_t0 = _carpeta(tmp_path / "t0")
    _, c_t0 = _correr_proceso(en_t0, [{"orden": "pausar", "en_t_sim_min": 0}, _intervenir("t0", "cortafuego", INICIAL),
                                      {"orden": "reanudar"}], al_recibir)
    assert respuestas["t0"]["estado"] == "aceptada" and respuestas["t0"]["t_vigor_min"] == 0.0, respuestas
    a, b = _leer(antes / "salida" / "hora_llegada_min.tif"), _leer(en_t0 / "salida" / "hora_llegada_min.tif")
    assert _distintas(a, b) == 0
    # por la vía del motor: archivos en la carpeta de la corrida y `mitigacion` en la definición
    base = yaml.safe_load((antes / "escenario_base.yaml").read_text(encoding="utf-8"))
    assert Path(base["mitigacion"]["barreras_extra"]) == (antes / "cortafuegos.geojson").resolve()
    assert Path(base["mitigacion"]["modificador_combustible"]) == (antes / "modificador_cortafuegos.tif").resolve()
    g = json.loads((antes / "cortafuegos.geojson").read_text(encoding="utf-8"))
    assert g["crs"]["properties"]["name"].endswith("EPSG::5345")
    assert g["features"][0]["properties"]["ancho_m"] == 10.0 and g["features"][0]["properties"]["tipo"] == "cortafuego"
    import rasterio
    with rasterio.open(antes / "modificador_cortafuegos.tif") as s:
        m = s.read(1)
        assert s.nodata == 1.0 and (m == 0).sum() > 0 and set(np.unique(m)) == {0.0, 1.0}
    ini = c_antes["resultados"]["cortafuegos_iniciales"]
    d_t0 = respuestas["t0"]["entrada"]["datos"]
    assert len(ini) == 1 and ini[0]["estado"] == "aceptada" and ini[0]["xy_5345"] == INICIAL["xy_5345"]
    assert ini[0]["celdas"] == d_t0["celdas"] and ini[0]["celdas_sha256"] == d_t0["celdas_sha256"]
    assert ini[0]["longitud_aplicada_m"] == d_t0["longitud_aplicada_m"] == d_t0["longitud_dibujada_m"]
    # la raíz de la bitácora incluye los cortafuegos iniciales: las dos corridas no tienen la misma raíz
    assert c_antes["bitacora_raiz"] != c_t0["bitacora_raiz"]
    assert c_antes["resultados"]["archivos_offline"] == {"barreras_extra": "cortafuegos_aplicados.geojson",
                                                        "modificador_combustible": "modificador_aplicado.tif"}

