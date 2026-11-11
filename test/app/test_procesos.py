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


def _carpeta(tmp: Path, motor: str) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "corrida.json").write_text(json.dumps({"formato": "incendios_sl.corrida/1.0", "motor": motor,
                                                  "base": {"definicion": DEFINICION}}), encoding="utf-8")
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
