"""Pruebas de los procesos motor (fase F1, prerregistro E-E3-1 en chico).

Para cada motor, sobre 6 horas de Las Lagunas 2024:
- el proceso da exactamente el mismo tiempo de llegada que `scripts/correr_escenario.py` del motor (0 celdas distintas);
- avisa `listo`, una `hora` por hora simulada y `final`, y por la salida estándar solo salen avisos;
- pausar y reanudar no cambia el resultado;
- detener deja salidas válidas.

Cada caso lanza procesos reales; el conjunto tarda unos minutos. No usa red.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import numpy as np
import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
PROCESO = REPO / "app" / "motores" / "proceso.py"
DEFINICION = {"evento": "SL-2024-LASLAGUNAS", "hipotesis": 1, "horas": 6, "validar": False, "figuras": False}
HORAS = 6
# motor: (carpeta del motor, lo que el proceso agrega por defecto a la definición, ráster de tiempo de llegada)
MOTORES = {
    "v4.0": ("v4.0", {"variante": "barreras", "parar_en_cicatriz": "off"}, "hora_llegada_min.tif"),
    "v3.1-libre": ("v3.1", {"variante": "libre"}, "t_llegada_s.tif"),
    "v3.1-librev2": ("v3.1", {"variante": "libre_v2"}, "t_llegada_s.tif"),
}


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


def _offline(tmp: Path, motor: str) -> np.ndarray:
    """Corrida de referencia con el guion del propio motor, con los resultados en una carpeta temporal."""
    version, agregado, raster = MOTORES[motor]
    tmp.mkdir(parents=True, exist_ok=True)
    esc = tmp / "referencia.yaml"
    esc.write_text(yaml.safe_dump({**DEFINICION, **agregado, "run_id": "referencia"}, sort_keys=False), encoding="utf-8")
    p = subprocess.run([sys.executable, "scripts/correr_escenario.py", "--archivo", str(esc)], cwd=REPO / "src" / version,
                       env=_entorno(version, tmp / "resultados"), capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert p.returncode == 0, p.stdout[-2000:] + p.stderr[-2000:]
    encontrados = list((tmp / "resultados").rglob(raster))
    assert len(encontrados) == 1, encontrados
    return _leer(encontrados[0])


def _carpeta(tmp: Path, motor: str, definicion: dict | None = None, configuracion: dict | None = None) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    corrida = {"formato": "incendios_sl.corrida/1.0", "motor": motor, "base": {"definicion": definicion or DEFINICION}}
    if configuracion:
        corrida["configuracion"] = configuracion
    (tmp / "corrida.json").write_text(json.dumps(corrida), encoding="utf-8")
    return tmp


TOPE_S = 240          # si un proceso no termina en este tiempo, se lo mata y la prueba falla (no queda colgada)


def _lanzar(carpeta: Path) -> subprocess.Popen:
    p = subprocess.Popen([sys.executable, str(PROCESO), "--corrida", str(carpeta)], cwd=REPO, env=_entorno(),
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding="utf-8", bufsize=1)
    p.guardian = threading.Timer(TOPE_S, p.kill)
    p.guardian.daemon = True
    p.guardian.start()
    return p


def _ordenar(p: subprocess.Popen, orden: str) -> None:
    p.stdin.write(json.dumps({"orden": orden}) + "\n")
    p.stdin.flush()


def _avisos(p: subprocess.Popen, al_recibir=None) -> list[dict]:
    """Lee todos los avisos hasta que el proceso cierra su salida. Cada línea tiene que ser JSON con el campo `aviso`."""
    out = []
    for linea in p.stdout:
        a = json.loads(linea)
        assert "aviso" in a, linea
        out.append(a)
        if al_recibir:
            al_recibir(a)
    p.wait(timeout=60)
    p.guardian.cancel()
    assert p.returncode is not None and p.returncode >= 0, f"el proceso no terminó solo en {TOPE_S} s y se lo mató"
    return out


def _raster_del_proceso(carpeta: Path, motor: str) -> np.ndarray:
    return _leer(carpeta / "salida" / MOTORES[motor][2])


@pytest.fixture(scope="module", params=sorted(MOTORES))
def caso(request, tmp_path_factory):
    """Por motor: la referencia offline y una corrida completa del proceso, sin órdenes."""
    motor = request.param
    tmp = tmp_path_factory.mktemp(motor.replace(".", "_").replace("-", "_"))
    referencia = _offline(tmp / "offline", motor)
    carpeta = _carpeta(tmp / "proceso", motor)
    p = _lanzar(carpeta)
    avisos = _avisos(p)
    return {"motor": motor, "tmp": tmp, "referencia": referencia, "carpeta": carpeta, "avisos": avisos,
            "codigo": p.returncode, "stderr": p.stderr.read()}


def test_identico_a_la_corrida_offline(caso):
    assert caso["codigo"] == 0, caso["stderr"][-2000:]
    propio = _raster_del_proceso(caso["carpeta"], caso["motor"])
    ref = caso["referencia"]
    assert propio.shape == ref.shape
    distintas = int((~((propio == ref) | (np.isnan(propio) & np.isnan(ref)))).sum())
    assert distintas == 0, f"{distintas} celdas con distinto tiempo de llegada"


def test_avisos_y_archivos(caso):
    avisos = caso["avisos"]
    assert avisos[0]["aviso"] == "listo" and avisos[-1]["aviso"] == "final"
    g = avisos[0]["grilla"]
    horas = [a for a in avisos if a["aviso"] == "hora"]
    assert [a["h"] for a in horas] == list(range(HORAS + 1))
    assert [a["t_sim_min"] for a in horas] == [60.0 * h for h in range(HORAS + 1)]
    assert all(b["ha"] >= a["ha"] for a, b in zip(horas, horas[1:]))
    fin = avisos[-1]
    assert fin["completa"] is True and fin["ha"] == horas[-1]["ha"] and fin["t_sim_min"] == 60.0 * HORAS
    # la huella parcial quedó con la forma anunciada y coincide con el ráster final del motor (en minutos)
    huella = np.load(caso["carpeta"] / "t_llegada_parcial.npy")
    assert huella.shape == (g["filas"], g["cols"]) and huella.dtype == np.float32
    final = _raster_del_proceso(caso["carpeta"], caso["motor"]).astype("float64")
    if caso["motor"].startswith("v3.1"):
        final = np.where(final >= 0, final / 60.0, np.nan)          # v3.1 guarda segundos y −1 donde no llegó
    assert np.array_equal(np.isnan(huella), np.isnan(final))
    assert np.allclose(huella[~np.isnan(huella)], final[~np.isnan(final)], rtol=0, atol=1e-3)
    assert abs(np.count_nonzero(~np.isnan(huella)) * (g["res"] ** 2) / 1e4 - fin["ha"]) < 0.01
    # corrida.json quedó completado y el registro del motor no se mezcló con los avisos
    corrida = json.loads((caso["carpeta"] / "corrida.json").read_text(encoding="utf-8"))
    assert corrida["resultados"]["ha_final"] == fin["ha"] and corrida["resultados"]["completa"] is True
    assert (caso["carpeta"] / "proceso.log").stat().st_size > 0


SOLO_IDENTIDAD = "v3.1-libre"      # usa el mismo conductor que v3.1-librev2: pausa y detener se prueban con este último


def test_pausar_y_reanudar_no_cambia_el_resultado(caso, tmp_path):
    motor = caso["motor"]
    if motor == SOLO_IDENTIDAD:
        pytest.skip("mismo conductor que v3.1-librev2")
    carpeta = _carpeta(tmp_path / "pausa", motor)
    p = _lanzar(carpeta)
    visto = {"pausas": []}

    def al_recibir(a):
        if a["aviso"] == "hora" and a["h"] == 2 and not visto["pausas"]:
            _ordenar(p, "pausar")
        if a["aviso"] == "pausado":
            visto["pausas"].append(a["t_sim_min"])
            _ordenar(p, "reanudar")

    avisos = _avisos(p, al_recibir)
    assert p.returncode == 0, p.stderr.read()[-2000:]
    assert len(visto["pausas"]) == 1 and visto["pausas"][0] >= 120.0 and visto["pausas"][0] % 60.0 == 0.0
    assert avisos[-1]["aviso"] == "final" and avisos[-1]["completa"] is True
    propio = _raster_del_proceso(carpeta, motor)
    ref = caso["referencia"]
    assert int((~((propio == ref) | (np.isnan(propio) & np.isnan(ref)))).sum()) == 0
    tipos = [b["tipo"] for b in json.loads((carpeta / "corrida.json").read_text(encoding="utf-8"))["bitacora"]]
    assert tipos == ["pausa", "reanudacion"]


def test_detener_deja_salidas_validas(caso, tmp_path):
    motor = caso["motor"]
    if motor == SOLO_IDENTIDAD:
        pytest.skip("mismo conductor que v3.1-librev2")
    carpeta = _carpeta(tmp_path / "detener", motor)
    p = _lanzar(carpeta)

    def al_recibir(a):
        if a["aviso"] == "hora" and a["h"] == 3:
            _ordenar(p, "pausar")
        if a["aviso"] == "pausado":
            _ordenar(p, "detener")

    avisos = _avisos(p, al_recibir)
    assert p.returncode == 0, p.stderr.read()[-2000:]
    fin = avisos[-1]
    assert fin["aviso"] == "final" and fin["motivo"] == "detenida" and fin["completa"] is False
    assert 180.0 <= fin["t_sim_min"] < 60.0 * HORAS
    parcial = _raster_del_proceso(carpeta, motor)
    ref = caso["referencia"]
    # lo simulado hasta detener coincide con la corrida completa en las celdas alcanzadas antes del corte
    if motor.startswith("v3.1"):
        llegadas, total = parcial >= 0, int((ref >= 0).sum())          # v3.1 guarda −1 donde el fuego no llegó
    else:
        llegadas, total = ~np.isnan(parcial), int((~np.isnan(ref)).sum())
    assert np.array_equal(parcial[llegadas], ref[llegadas])
    assert 0 < int(llegadas.sum()) < total
    corrida = json.loads((carpeta / "corrida.json").read_text(encoding="utf-8"))
    assert corrida["resultados"]["motivo_fin"] == "detenida"
    assert [b["tipo"] for b in corrida["bitacora"]] == ["pausa", "detencion"]


# ---------------------------------------------------------------------------------------------------- ignición libre
PUNTOS_DE_LA_FICHA = [{"lon": -65.5477, "lat": -32.6367}, {"lon": -65.6232, "lat": -32.6422}]     # SL-2024-LASLAGUNAS, SNMF
HORA_HIPOTESIS_1 = "2024-09-18T15:00:00Z"


def test_ignicion_libre_en_los_puntos_de_la_ficha_da_lo_mismo(caso, tmp_path):
    """Los mismos puntos y la misma hora, pero pasados como ignición libre: tiene que dar la corrida de referencia.
    La definición base pide la hipótesis 0 (otra hora): la hora tiene que salir de `configuracion`."""
    motor = caso["motor"]
    carpeta = _carpeta(tmp_path / "libre", motor, {**DEFINICION, "hipotesis": 0},
                       {"ignicion": PUNTOS_DE_LA_FICHA, "t_inicio_utc": HORA_HIPOTESIS_1})
    p = _lanzar(carpeta)
    avisos = _avisos(p)
    assert p.returncode == 0, [a for a in avisos if a["aviso"] == "error"]
    assert avisos[0]["t0_utc"].startswith("2024-09-18 15:00")
    propio = _raster_del_proceso(carpeta, motor)
    ref = caso["referencia"]
    assert int((~((propio == ref) | (np.isnan(propio) & np.isnan(ref)))).sum()) == 0
    ign = json.loads((carpeta / "corrida.json").read_text(encoding="utf-8"))["resultados"]["ignicion"]
    assert len(ign["usada"]) == 2 and ign["pedida"]["t_inicio_utc"] == HORA_HIPOTESIS_1


def _celda_de_pastizal() -> tuple[int, int, float, float]:
    """(fila, columna, lon, lat) del centro de una celda de pastizal rodeada de pastizal, cerca del centro del dominio."""
    import rasterio
    from pyproj import Transformer
    from scipy.ndimage import minimum_filter
    ruta = REPO / "datos" / "inputSimulacion" / "combustibles" / "SL-2024-LASLAGUNAS" / "combustible_clase_SL-2024-LASLAGUNAS.tif"
    with rasterio.open(ruta) as s:
        clase, tr, crs = s.read(1), s.transform, s.crs
    homogeneo = minimum_filter((clase == 1).astype(np.uint8), size=7) == 1
    ff, cc = np.nonzero(homogeneo)
    k = int(np.argmin((ff - clase.shape[0] // 2) ** 2 + (cc - clase.shape[1] // 2) ** 2))
    f, c = int(ff[k]), int(cc[k])
    x, y = tr * (c + 0.5, f + 0.5)
    lon, lat = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform(x, y)
    return f, c, float(lon), float(lat)


def test_ignicion_en_un_punto_y_una_hora_elegidos(caso, tmp_path):
    motor = caso["motor"]
    f, c, lon, lat = _celda_de_pastizal()
    carpeta = _carpeta(tmp_path / "punto", motor, {"evento": "SL-2024-LASLAGUNAS", "validar": False, "figuras": False},
                       {"ignicion": [{"lon": lon, "lat": lat}], "t_inicio_utc": "2024-09-19T16:00:00Z", "horas": 3})
    p = _lanzar(carpeta)
    avisos = _avisos(p)
    assert p.returncode == 0, [a for a in avisos if a["aviso"] == "error"]
    assert avisos[0]["t0_utc"].startswith("2024-09-19 16:00")
    fin = avisos[-1]
    assert fin["completa"] is True and fin["t_sim_min"] == 180.0 and fin["ha"] > 0
    t = _raster_del_proceso(carpeta, motor).astype("float64")
    if motor.startswith("v3.1"):
        t = np.where(t >= 0, t, np.nan)
    assert t[f, c] == 0.0 and np.nanmin(t) == 0.0, "el fuego tiene que empezar en la celda pedida"
    # todo lo quemado en 3 horas queda cerca del punto pedido, lejos de los puntos de la ficha (a más de 5 km)
    ff, cc = np.nonzero(~np.isnan(t))
    assert float(np.hypot(ff - f, cc - c).max()) * 30.0 < 5000.0
    ign = json.loads((carpeta / "corrida.json").read_text(encoding="utf-8"))["resultados"]["ignicion"]
    assert len(ign["usada"]) == 1 and "desplazada_m" not in ign["usada"][0]
    assert abs(ign["usada"][0]["lon"] - lon) < 1e-3 and abs(ign["usada"][0]["lat"] - lat) < 1e-3


def test_ignicion_fuera_del_dominio_se_rechaza(tmp_path):
    carpeta = _carpeta(tmp_path / "fuera", "v4.0", {"evento": "SL-2024-LASLAGUNAS", "horas": 3, "validar": False, "figuras": False},
                       {"ignicion": [{"lon": -64.0, "lat": -32.6}]})
    p = _lanzar(carpeta)
    avisos = _avisos(p)
    assert p.returncode == 1
    assert avisos[-1]["aviso"] == "error" and avisos[-1]["fatal"] is True and "fuera del dominio" in avisos[-1]["mensaje"]


@pytest.mark.parametrize("motor", ["v4.0", "v3.1-librev2"])
def test_hora_fuera_de_la_serie_meteorologica_se_rechaza(tmp_path, motor):
    carpeta = _carpeta(tmp_path / "hora", motor, {"evento": "SL-2024-LASLAGUNAS", "horas": 3, "validar": False, "figuras": False},
                       {"t_inicio_utc": "2025-01-01T12:00:00Z"})
    p = _lanzar(carpeta)
    avisos = _avisos(p)
    assert p.returncode == 1
    assert avisos[-1]["aviso"] == "error" and avisos[-1]["fatal"] is True and "serie meteorológica" in avisos[-1]["mensaje"]


def _celda_que_no_quema_lejos_de_la_cicatriz() -> tuple[float, float, float, float]:
    """(lon, lat, metros a la celda combustible más cercana, metros a la cicatriz) de una celda no combustible de v3.1
    que está a más de 8 km de la cicatriz de Las Lagunas 2024."""
    import rasterio
    from pyproj import Transformer
    from scipy import ndimage
    base = REPO / "datos" / "inputSimulacion"
    with rasterio.open(base / "combustibles" / "SL-2024-LASLAGUNAS" / "combustible_clase_SL-2024-LASLAGUNAS.tif") as src:
        clase = src.read(1); tr = src.transform; crs = src.crs
    with rasterio.open(base / "eventos" / "SL-2024-LASLAGUNAS" / "cicatriz_referencia_SL-2024-LASLAGUNAS.tif") as src:
        cicatriz = src.read(1) == 1
    res = abs(tr.a)
    a_combustible = ndimage.distance_transform_edt(clase <= 0) * res
    a_cicatriz = ndimage.distance_transform_edt(~cicatriz) * res
    borde = np.zeros_like(clase, dtype=bool); borde[60:-60, 60:-60] = True
    candidatas = np.argwhere((clase <= 0) & (a_cicatriz > 8000) & (a_combustible < 400) & borde)
    assert len(candidatas), "no hay celdas no combustibles lejos de la cicatriz"
    f, c = (int(v) for v in candidatas[len(candidatas) // 2])
    x, y = tr.c + (c + 0.5) * tr.a, tr.f + (f + 0.5) * tr.e
    lon, lat = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform(x, y)
    return lon, lat, float(a_combustible[f, c]), float(a_cicatriz[f, c])


@pytest.mark.parametrize("motor", ["v4.0", "v3.1-librev2"])
def test_punto_que_no_quema_se_corre_cerca_del_clic_y_no_a_la_cicatriz(tmp_path, motor):
    """Decisión D-E3-20: con un punto elegido por el usuario, el corrimiento no mira la cicatriz del evento base."""
    lon, lat, m_combustible, m_cicatriz = _celda_que_no_quema_lejos_de_la_cicatriz()
    carpeta = _carpeta(tmp_path / "corrida", motor, {"evento": "SL-2024-LASLAGUNAS", "validar": False, "figuras": False},
                       {"ignicion": [{"lon": lon, "lat": lat}], "t_inicio_utc": "2024-09-19T16:00:00Z", "horas": 1})
    p = _lanzar(carpeta)
    avisos = _avisos(p)
    assert p.returncode == 0 and avisos[-1]["aviso"] == "final", avisos[-1]
    usada = json.loads((carpeta / "corrida.json").read_text(encoding="utf-8"))["resultados"]["ignicion"]["usada"]
    assert len(usada) == 1
    corrida_m = usada[0].get("desplazada_m", 0.0)
    assert corrida_m < 2000 and corrida_m < m_cicatriz / 4, (corrida_m, m_combustible, m_cicatriz)
    if motor.startswith("v3.1"):          # v3.1 usa justo este mapa de clases: el corrimiento es a su vecina más cercana
        assert abs(corrida_m - m_combustible) <= 30, (corrida_m, m_combustible)
