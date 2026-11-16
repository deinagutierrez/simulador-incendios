"""Arreglos de la F6 para Windows y caídas (D-E3-30, puntos 5, 17 y 20; D-E3-31).

- Punto 5: la huella parcial se reemplaza reintentando si el archivo está bloqueado (en Windows, mientras el servidor la
  lee); si no se puede, la corrida sigue con un aviso no fatal. El servidor tolera una lectura fallida o a medio escribir
  (reintenta y, si no, usa la última huella que leyó bien). `indices.py` no renombra sobre una carpeta que no se pudo
  borrar. En Linux un archivo abierto no impide reemplazarlo: el bloqueo se simula con un `os.replace` o un `np.load` que
  fallan las primeras veces.
- Punto 20: un cortafuego de `configuracion.cortafuegos` que el motor rechaza corta la corrida con un error fatal antes de
  simular (ningún aviso `hora`), en v3.1, v4.0 y el motor simulado.
- Punto 17: una corrida v3.1 real lanzada por el servidor, con el proceso motor matado a mitad: queda en `error` con un
  mensaje y el servidor sigue atendiendo y lanzando corridas.

No usan red. Las de los motores reales lanzan procesos (unos segundos a un minuto cada una).
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app" / "motores"))
sys.path.insert(0, str(REPO / "app"))

import control  # noqa: E402
from datos import comun, indices  # noqa: E402
from servidor import huella  # noqa: E402

TOPE_S = 240
GRILLA = {"crs": "EPSG:5345", "xmin": 4_400_000.0, "ymax": 6_400_000.0, "res": 30.0, "filas": 40, "cols": 50}


def _falla_las_primeras(n: int, original, error=PermissionError):
    """Una función que lanza `error` las primeras `n` veces y después llama a `original`. Cuenta las llamadas."""
    estado = {"llamadas": 0}

    def f(*a, **k):
        estado["llamadas"] += 1
        if estado["llamadas"] <= n:
            raise error(13, "simulado: el archivo está abierto por otro proceso")
        return original(*a, **k)
    f.estado = estado
    return f


def _control(carpeta: Path) -> tuple[control.Control, io.StringIO]:
    avisos = io.StringIO()
    return control.Control(carpeta, avisos, None), avisos


def _avisos_de(flujo: io.StringIO) -> list[dict]:
    return [json.loads(x) for x in flujo.getvalue().splitlines() if x.strip()]


def _huella(h: int) -> np.ndarray:
    t = np.full((GRILLA["filas"], GRILLA["cols"]), np.nan, dtype="float32")
    t[10:20, 10:10 + 5 * (h + 1)] = 30.0 * h
    return t


# =================================================================== punto 5: huella parcial (proceso motor)
def test_guardar_huella_reintenta_si_el_archivo_esta_bloqueado(tmp_path, monkeypatch):
    monkeypatch.setattr(control, "ESPERA_REEMPLAZO_S", 0.001)
    falso = _falla_las_primeras(5, os.replace)
    monkeypatch.setattr(os, "replace", falso)
    c, avisos = _control(tmp_path)
    assert c.guardar_huella(_huella(3)) is True
    assert falso.estado["llamadas"] == 6
    np.testing.assert_array_equal(np.load(tmp_path / control.HUELLA), _huella(3))
    assert not (tmp_path / (control.HUELLA + ".tmp")).exists()
    assert _avisos_de(avisos) == []


def test_guardar_huella_bloqueada_siempre_no_corta_la_corrida(tmp_path, monkeypatch):
    monkeypatch.setattr(control, "ESPERA_REEMPLAZO_S", 0.001)
    c, avisos = _control(tmp_path)
    assert c.guardar_huella(_huella(1)) is True
    falso = _falla_las_primeras(10 ** 6, os.replace)
    monkeypatch.setattr(os, "replace", falso)
    assert c.guardar_huella(_huella(2)) is False                 # no lanza
    assert falso.estado["llamadas"] == control.INTENTOS_REEMPLAZO
    np.testing.assert_array_equal(np.load(tmp_path / control.HUELLA), _huella(1))     # queda la anterior, entera
    assert not (tmp_path / (control.HUELLA + ".tmp")).exists()
    (a,) = _avisos_de(avisos)
    assert a["aviso"] == "error" and a["fatal"] is False and control.HUELLA in a["mensaje"]
    # y la hora se avisa igual: la corrida sigue
    c.hora(2, 120.0, 1.0, 3, _huella(2))
    assert [x["aviso"] for x in _avisos_de(avisos)] == ["error", "error", "hora"]


def test_reemplazar_deja_pasar_otros_errores_y_el_ultimo(tmp_path, monkeypatch):
    origen = tmp_path / "a.tmp"
    origen.write_text("x")
    with pytest.raises(FileNotFoundError):
        control.reemplazar(tmp_path / "no_existe", tmp_path / "b")
    monkeypatch.setattr(os, "replace", _falla_las_primeras(10 ** 6, os.replace))
    with pytest.raises(PermissionError):
        control.reemplazar(origen, tmp_path / "b", intentos=3, espera_s=0.0)


# =================================================================== punto 5: lectura de la huella (servidor)
def _escribir(carpeta: Path, t: np.ndarray) -> None:
    np.save(carpeta / huella.HUELLA, t)


def test_huella_tolera_un_bloqueo_pasajero(tmp_path, monkeypatch):
    monkeypatch.setattr(huella, "ESPERA_LECTURA_S", 0.001)
    _escribir(tmp_path, _huella(2))
    falso = _falla_las_primeras(2, np.load)
    monkeypatch.setattr(huella.np, "load", falso)
    p = huella.perimetro(tmp_path, GRILLA)
    assert p is not None and p["features"][0]["properties"]["celdas"] == int(np.isfinite(_huella(2)).sum())
    assert falso.estado["llamadas"] == 3


def test_huella_a_medio_escribir_usa_la_ultima_que_se_leyo_bien(tmp_path, monkeypatch):
    monkeypatch.setattr(huella, "ESPERA_LECTURA_S", 0.001)
    _escribir(tmp_path, _huella(1))
    imagen_1 = huella.png(tmp_path, GRILLA)
    assert imagen_1[:8] == b"\x89PNG\r\n\x1a\n"
    # a medio escribir: solo el principio del archivo .npy
    completo = (tmp_path / huella.HUELLA).read_bytes()
    _escribir(tmp_path, _huella(4))
    (tmp_path / huella.HUELLA).write_bytes(completo[:100])
    assert huella.png(tmp_path, GRILLA) == imagen_1                  # la anterior, sin romper
    assert huella.perimetro(tmp_path, GRILLA)["features"][0]["properties"]["celdas"] == int(np.isfinite(_huella(1)).sum())
    _escribir(tmp_path, _huella(4))                                  # cuando se puede leer, la nueva
    assert huella.png(tmp_path, GRILLA) != imagen_1


def test_huella_ilegible_sin_ninguna_anterior_responde_que_no_hay(tmp_path, monkeypatch):
    monkeypatch.setattr(huella, "ESPERA_LECTURA_S", 0.001)
    (tmp_path / huella.HUELLA).write_bytes(b"\x93NUMPY a medias")
    assert huella.png(tmp_path, GRILLA) is None
    assert huella.perimetro(tmp_path, GRILLA) is None
    monkeypatch.setattr(huella.np, "load", _falla_las_primeras(10 ** 6, np.load))
    otra = tmp_path / "otra"
    otra.mkdir()
    _escribir(otra, _huella(1))
    assert huella.comparar(otra, otra, GRILLA, GRILLA) is None       # bloqueada siempre y nunca leída: no hay


# =================================================================== punto 5: índices
@pytest.fixture
def cache(tmp_path, monkeypatch):
    c = tmp_path / "cache"
    monkeypatch.setattr(comun, "CACHE", c)
    monkeypatch.setattr(indices.time, "sleep", lambda s: None)
    return c


def test_vaciar_falla_con_un_mensaje_claro_si_queda_la_carpeta(cache, monkeypatch):
    carpeta = cache / "indices" / "I-20261111-aws"
    carpeta.mkdir(parents=True)
    (carpeta / "ndvi_I-20261111-aws.tif").write_bytes(b"abierto")
    monkeypatch.setattr(indices.shutil, "rmtree", lambda *a, **k: None)          # como un TIF abierto en Windows
    with pytest.raises(RuntimeError, match="no se pudo borrar la toma anterior.*ndvi_I-20261111-aws.tif"):
        indices._vaciar(carpeta)


def test_toma_aws_no_renombra_sobre_una_carpeta_que_quedo(cache, monkeypatch):
    from datos import sentinel2 as s2
    carpeta = indices.dir_tomas() / "I-20261111-aws"
    carpeta.mkdir(parents=True)
    (carpeta / "info.json").write_text('{"id": "vieja"}', encoding="utf-8")

    def compuesto(desde, hasta, destino, id_, progreso=None):
        destino.mkdir(parents=True)
        (destino / f"ndvi_{id_}.tif").write_bytes(b"nuevo")
        return {"n_escenas": 1, "fechas": ["2026-11-01"], "segundos": 0.0}
    monkeypatch.setattr(s2, "compuesto_ventana", compuesto)
    rmtree = indices.shutil.rmtree
    # el .tmp se borra bien; la toma anterior no (archivo abierto)
    monkeypatch.setattr(indices.shutil, "rmtree",
                        lambda ruta, *a, **k: None if Path(ruta) == carpeta else rmtree(ruta, *a, **k))
    renombres = _falla_las_primeras(0, Path.rename)
    monkeypatch.setattr(Path, "rename", renombres)
    with pytest.raises(RuntimeError, match="no se pudo borrar la toma anterior"):
        indices.toma_aws(__import__("datetime").date(2026, 11, 12))
    assert renombres.estado["llamadas"] == 0                             # no se intentó renombrar
    assert json.loads((carpeta / "info.json").read_text(encoding="utf-8")) == {"id": "vieja"}


def test_toma_manual_no_mezcla_con_una_carpeta_que_quedo(cache, monkeypatch):
    monkeypatch.setattr(indices.shutil, "rmtree", lambda *a, **k: None)
    monkeypatch.setattr(indices, "leer_tif_manual", lambda ruta, nombre: np.full((2, 2), 100, dtype="int16"))
    # la primera crea la carpeta; la segunda, con la carpeta imposible de borrar, falla antes de escribir
    escritos = []
    monkeypatch.setattr(comun, "escribir_tif", lambda ruta, *a, **k: (escritos.append(ruta), Path(ruta).write_bytes(b"t")))
    monkeypatch.setattr(comun, "grilla_dominio", lambda: None)
    monkeypatch.setattr(indices, "_info", lambda id_, carpeta, *a, **k: {"id": id_})
    id_ = indices.toma_manual(Path("a"), Path("b"), ["2026-10-01", "2026-11-01"], "B08", "a", "b")["id"]
    assert len(escritos) == 2
    with pytest.raises(RuntimeError, match="no se pudo borrar la toma anterior"):
        indices.toma_manual(Path("a"), Path("b"), ["2026-10-01", "2026-11-01"], "B08", "a", "b")
    assert len(escritos) == 2 and id_.startswith("I-20261101-manual-")


# =================================================================== punto 20: cortafuego inicial rechazado
def _entorno() -> dict:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    env.pop("PYTHONPATH", None)
    return env


def _correr(guion: str, carpeta: Path, corrida: dict) -> tuple[int, list[dict]]:
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "corrida.json").write_text(json.dumps(corrida), encoding="utf-8")
    p = subprocess.run([sys.executable, str(REPO / "app" / "motores" / guion), "--corrida", str(carpeta)], cwd=REPO,
                       env=_entorno(), stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                       timeout=TOPE_S)
    return p.returncode, [json.loads(x) for x in p.stdout.splitlines() if x.strip()]


def _lejos_del_dominio() -> list[list[float]]:
    """Un trazo válido (en EPSG:5345) a cientos de kilómetros de San Luis: el motor lo rechaza por no tocar la grilla."""
    from pyproj import Transformer
    t = Transformer.from_crs("EPSG:4326", "EPSG:5345", always_xy=True)
    return [list(t.transform(-60.0, -38.0)), list(t.transform(-59.99, -38.0))]


def _bueno() -> list[list[float]]:
    from pyproj import Transformer
    t = Transformer.from_crs("EPSG:4326", "EPSG:5345", always_xy=True)
    return [list(t.transform(-65.58, -32.62)), list(t.transform(-65.56, -32.62))]


def _comprobar_corte(codigo: int, avisos: list[dict]) -> None:
    assert codigo == 1, avisos
    tipos = [a["aviso"] for a in avisos]
    assert "hora" not in tipos and "final" not in tipos, tipos            # no se simuló nada
    fatales = [a for a in avisos if a["aviso"] == "error" and a.get("fatal")]
    assert len(fatales) == 1 and "cortafuego 2 de antes de iniciar rechazado" in fatales[0]["mensaje"], fatales


@pytest.mark.parametrize("motor", ["v3.1-librev2", "v4.0"])
def test_cortafuego_inicial_rechazado_corta_antes_de_simular(tmp_path, motor):
    cortafuegos = [{"ancho_m": 10, "suelo_mineral": False, "xy_5345": _bueno()},
                   {"ancho_m": 10, "suelo_mineral": False, "xy_5345": _lejos_del_dominio()}]
    corrida = {"formato": "incendios_sl.corrida/1.0", "motor": motor,
               "base": {"definicion": {"evento": "SL-2024-LASLAGUNAS", "hipotesis": 1, "horas": 2, "validar": False,
                                       "figuras": False}},
               "configuracion": {"cortafuegos": cortafuegos}}
    _comprobar_corte(*_correr("proceso.py", tmp_path, corrida))


def test_cortafuego_inicial_rechazado_corta_antes_de_simular_simulado(tmp_path):
    cortafuegos = [{"ancho_m": 10, "suelo_mineral": False, "xy_5345": _bueno()},
                   {"ancho_m": 10, "suelo_mineral": False, "xy_5345": _lejos_del_dominio()}]
    corrida = {"formato": "incendios_sl.corrida/1.0", "motor": "simulado", "simulado": {"s_por_hora": 0.0},
               "configuracion": {"horas": 3, "ignicion": [{"lon": -65.57, "lat": -32.62}], "cortafuegos": cortafuegos}}
    _comprobar_corte(*_correr("proceso_simulado.py", tmp_path, corrida))


# =================================================================== punto 17: caída de un motor real
def test_caida_de_un_motor_real_v31_por_el_servidor(tmp_path):
    from test_servidor import Servidor
    s = Servidor(tmp_path / "corridas")
    try:
        codigo, r = s.pedir("/api/corridas", {"motor": "v3.1-libre", "evento": "SL-2024-LASLAGUNAS", "hipotesis": 1,
                                              "horas": 48, "iniciar": True})
        assert codigo == 201, r
        id_ = r["corridas"][0]["id"]
        c = s.app.state.gestor.obtener(id_)
        limite = time.monotonic() + TOPE_S
        while not (c.ultima_hora and int(c.ultima_hora["h"]) >= 2):       # a mitad: ya avanzó un par de horas
            assert c.estado not in ("terminada", "detenida", "error"), (c.estado, c.error)
            assert time.monotonic() < limite, "la corrida v3.1 no llegó a la hora 2"
            time.sleep(0.1)
        c.proceso.kill()                                                 # caída: sin aviso, sin guardar
        limite = time.monotonic() + 60
        while (d := s.detalle(id_))["estado"] not in ("terminada", "detenida", "error", "interrumpida"):
            assert time.monotonic() < limite, "el servidor no notó la caída"
            time.sleep(0.05)
        assert d["estado"] == "error", d
        assert "terminó sin avisar" in d["error"] and "código" in d["error"], d["error"]
        assert d["ultima_hora"]["h"] >= 2
        # el servidor sigue atendiendo: estado, la huella que quedó, y una corrida nueva de punta a punta
        assert s.pedir("/api/estado")[0] == 200
        codigo, imagen = s.pedir(f"/api/corridas/{id_}/quemado.png")
        assert codigo == 200 and imagen[:4] == b"\x89PNG"
        otra = s.simulada(horas=3)
        assert s.esperar(otra, "terminada")["ultima_hora"]["h"] == 3
    finally:
        s.cerrar()
