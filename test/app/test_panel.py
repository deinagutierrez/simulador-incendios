"""Panel rediseñado: Bootstrap con copia local, combustible SB40 de v4.0 en las capas y formatos de la carga manual.

Sin internet y sin motores. La parte visual (secciones, pie fijo, focos) se revisa en el navegador.
"""
from __future__ import annotations

import base64
import hashlib
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from servidor import capas                            # noqa: E402
from test_servidor import Servidor                    # noqa: E402

WEB = REPO / "app" / "web"


@pytest.fixture(scope="module")
def servidor(tmp_path_factory):
    s = Servidor(tmp_path_factory.mktemp("corridas_panel"))
    yield s
    s.cerrar()


def test_bootstrap_de_la_cdn_con_integridad_y_copia_local_identica():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    for archivo in ("bootstrap.min.css", "bootstrap.bundle.min.js"):
        m = re.search(r'https://cdn\.jsdelivr\.net/npm/bootstrap@5\.3\.3/dist/(?:css|js)/' + re.escape(archivo) +
                      r'"\s+integrity="(sha384-[^"]+)"', html)
        assert m, f"{archivo}: falta en index.html con versión fija e integridad"
        local = (WEB / "vendor" / "bootstrap" / archivo).read_bytes()
        assert m.group(1) == "sha384-" + base64.b64encode(hashlib.sha384(local).digest()).decode(), archivo
        assert f"/web/vendor/bootstrap/{archivo}" in html, f"{archivo}: sin respaldo local"


def test_la_copia_local_de_bootstrap_se_sirve(servidor):
    for ruta in ("/web/vendor/bootstrap/bootstrap.min.css", "/web/vendor/bootstrap/bootstrap.bundle.min.js"):
        codigo, cuerpo = servidor.pedir(ruta)
        assert codigo == 200 and len(cuerpo) > 50_000, ruta


def test_capa_sb40_del_evento_con_leyenda():
    lista = {c["id"]: c for c in capas.lista("SL-2024-LASLAGUNAS")}
    assert "sb40" in lista and "combustible" in lista                   # junto al de 7 clases de v3.1
    c = lista["sb40"]
    assert c["titulo"] == "Combustible SB40 (v4.0)" and c["por_evento"] and c["grupo"] == "Vegetación"
    items = c["leyenda"]["items"]
    nombres = [i["nombre"] for i in items]
    assert any(n.startswith("GR") for n in nombres) and any(n.startswith("SH") for n in nombres)
    assert len(set(i["color"] for i in items)) == len(items)            # cada modelo con su color
    assert c["leyenda"]["nota"]
    png = capas.png("sb40", "SL-2024-LASLAGUNAS")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_sb40_sin_el_del_evento_usa_el_mapa_base_del_anio_anterior(tmp_path, monkeypatch):
    monkeypatch.setattr(capas, "SB40_PROCESADO", tmp_path)               # como si v4.0 no hubiera corrido el evento
    assert capas._sb40_ruta("SL-2025-PRUEBA").name == "sb40_2024.tif"
    assert capas._sb40_ruta("SL-2024-LASLAGUNAS").name == "sb40_2023.tif"
    c = {x["id"]: x for x in capas.lista("SL-2024-LASLAGUNAS")}["sb40"]
    assert c["archivo"] == "sb40_2023.tif" and "Mapa base 2023" in c["leyenda"]["nota"]


def test_formatos_de_carga_y_sus_ejemplos(servidor):
    codigo, doc = servidor.pedir("/formatos/formatos_de_carga.md")
    assert codigo == 200 and "Formatos de carga manual" in doc.decode("utf-8")
    for nombre in ("ejemplo_meteorologia_v40.csv", "ejemplo_meteorologia_v3x.csv", "ejemplo_ndvi.tif", "ejemplo_ndmi.tif"):
        assert f"formatos_de_carga/{nombre}" in doc.decode("utf-8"), nombre
        codigo, cuerpo = servidor.pedir(f"/formatos/formatos_de_carga/{nombre}")
        assert codigo == 200 and len(cuerpo) > 1000, nombre
    assert servidor.pedir("/formatos/formatos_de_carga/..%2F..%2Fapp%2Fservir.py")[0] == 404
    assert servidor.pedir("/formatos/formatos_de_carga/otro.csv")[0] == 404


def test_los_ejemplos_pasan_los_controles_de_la_carga():
    from datos import indices, meteo
    d = REPO / "docs" / "formatos_de_carga"
    for nombre, formato in (("ejemplo_meteorologia_v40.csv", "v4.0"), ("ejemplo_meteorologia_v3x.csv", "v3.x")):
        serie, f = meteo.leer_csv_manual((d / nombre).read_bytes())
        assert f == formato and len(serie) >= 24
    a = meteo.leer_csv_manual((d / "ejemplo_meteorologia_v40.csv").read_bytes())[0]
    b = meteo.leer_csv_manual((d / "ejemplo_meteorologia_v3x.csv").read_bytes())[0]
    assert (pd.to_datetime(a["time_utc"]) == pd.to_datetime(b["time_utc"])).all()          # las mismas horas
    for nombre in ("ejemplo_ndvi.tif", "ejemplo_ndmi.tif"):
        banda = indices.leer_tif_manual(d / nombre, nombre)
        assert banda.dtype == "int16"
