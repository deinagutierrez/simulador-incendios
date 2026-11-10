import json
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from incendios_sl import config as cfgmod
from incendios_sl.api.app import app
from incendios_sl.api import trabajos

cli = TestClient(app)


def _hay_resultados():
    base = cfgmod.dir_resultados()
    return [d.name for d in base.iterdir() if (d / "t_llegada_s.tif").exists() and (d / "serie_horaria.csv").exists()] if base.exists() else []


def test_info_y_catalogos():
    assert cli.get("/api/info").status_code == 200
    a = cli.get("/api/areas").json(); assert a and a[0]["resolucion_m"] == 30 and a[0]["celdas_grilla"] == 2_793_912
    e = cli.get("/api/incendios").json(); assert any(x["id"] == "SL-2024-LASLAGUNAS" for x in e)
    assert cli.get("/api/incendios/NO-EXISTE").status_code == 404


def test_estado_trabajo_persistido(tmp_path, monkeypatch):
    # estado.json atómico con los estados definidos
    monkeypatch.setattr(trabajos, "dir_run", lambda rid: tmp_path / rid)
    e = trabajos.escribir_estado("x", estado="pendiente", progreso=0.0)
    assert e["estado"] == "pendiente" and (tmp_path / "x" / "estado.json").exists()
    e = trabajos.escribir_estado("x", estado="ejecutando_simulacion", progreso=0.5)
    assert trabajos.leer_estado("x")["progreso"] == 0.5 and "creado_utc" in e
    ok, msg = trabajos.verificar_completada("x"); assert not ok and "faltan" in msg
    assert set(trabajos.ESTADOS) >= {"pendiente", "completada", "fallida", "cancelada"}


def test_simulacion_sin_datos_preparados_rechazada():
    r = cli.post("/api/simulaciones", json={"evento": "NO-EXISTE"})
    assert r.status_code == 404


@pytest.mark.skipif(not _hay_resultados(), reason="requiere resultados de simulación en data/resultados")
def test_resultados_existentes_png_serie_perimetro():
    rid = sorted(_hay_resultados())[0]
    r = cli.get(f"/api/simulaciones/{rid}"); assert r.status_code == 200 and r.json()["estado"]["estado"] == "completada"
    s = cli.get(f"/api/simulaciones/{rid}/serie").json(); assert len(s["filas"]) > 0 and "ha_quemadas" in s["columnas"]
    p = cli.get(f"/api/simulaciones/{rid}/estado/3600.png"); assert p.status_code == 200 and p.headers["content-type"] == "image/png" and len(p.content) > 100
    g = cli.get(f"/api/simulaciones/{rid}/perimetro/3600.geojson").json(); assert g["type"] == "FeatureCollection"
    lst = cli.get("/api/simulaciones").json(); assert any(x["run_id"] == rid for x in lst)


@pytest.mark.skipif(not (cfgmod.dir_entradas() / "grilla").exists(), reason="requiere productos de la Etapa 3")
def test_capas_estaticas():
    r = cli.get("/api/capas/las_lagunas_potrerillos/sombras/info"); assert r.status_code == 200 and "bounds_lonlat" in r.json()
    r = cli.get("/api/capas/las_lagunas_potrerillos/combustible.png?evento=SL-2024-LASLAGUNAS"); assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert cli.get("/api/capas/las_lagunas_potrerillos/inexistente.png").status_code == 404
    v = cli.get("/api/vectores/las_lagunas_potrerillos/caminos.geojson"); assert v.status_code == 200 and v.json()["type"] == "FeatureCollection"
