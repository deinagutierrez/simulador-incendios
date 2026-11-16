"""Pruebas del modo histórico (fase F6, D-E3-30 puntos 10 a 14).

Rápidas (segundos, sin motores): la lista de eventos con ficha, los rechazos, cómo se arma la corrida con la ignición
recomendada (sin iniciarla), las métricas de v3.1 sobre salidas sintéticas de v3.1 y de v4.0 (una huella igual a la
cicatriz da IoU 1), los focos coloreados y el zip de exportación con los archivos para la corrida offline (D-E3-31).

Lenta (unos 30 s acá; corre siempre, el repositorio no usa marcas de pytest): Las Chacras octubre 2023, alt4, hipótesis 4,
con v3.1 libre y librev2 por el servidor, y exige que las métricas salgan iguales a las filas de
docs/etapa3/historico_referencia.json (docs/v4.0/31 §7.2), redondeadas como allí.

Levantan el servidor de verdad en un puerto libre; no usan internet.
"""
from __future__ import annotations

import io
import json
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from servidor.corridas import escribir_json   # noqa: E402
from test_servidor import Servidor            # noqa: E402

EV = "SL-2023-CHACRASOCT"
ENTRADAS = REPO / "datos" / "inputSimulacion"
CICATRIZ = ENTRADAS / "eventos" / EV / f"cicatriz_referencia_{EV}.tif"
REFERENCIA = json.loads((REPO / "docs" / "etapa3" / "historico_referencia.json").read_text(encoding="utf-8"))
X49_SIN_RECOMENDADA = {"SL-2022-ALGARROBAL", "SL-2022-LAJULI", "SL-2022-LATOTORA", "SL-2023-LAGUNALARGA"}
T0 = "2023-10-17T06:00:00+00:00"
T_SIM_MIN = 30 * 60.0                      # la corrida sintética "termina" a las 30 h

pytestmark = pytest.mark.skipif(not CICATRIZ.exists(), reason=f"faltan los datos de {EV} en este clon")


# ---------------------------------------------------------------------------------------------- salidas sintéticas
def _corrida_sintetica(carpeta: Path, id_: str, motor: str, evento: str | None = EV) -> Path:
    """Una corrida terminada, escrita a mano como la deja el servidor, con la huella IGUAL a la cicatriz (llega a la 1 h)."""
    import rasterio
    c = carpeta / id_
    salida = c / "salida"
    salida.mkdir(parents=True)
    with rasterio.open(CICATRIZ) as s:
        ref = s.read(1) == 1
        perfil = s.profile.copy()
    ha = float(ref.sum()) * 0.09
    entradas = {"ignicion": "alt4", "hipotesis_ignicion": 4, "puntos_ignicion": [{"nombre": "sintético", "lon": -65.7679,
                                                                                    "lat": -32.6506}]}
    if motor.startswith("v3.1"):
        perfil.update(dtype="float32", nodata=-1.0, count=1, compress="deflate")
        with rasterio.open(salida / "t_llegada_s.tif", "w", **perfil) as d:
            d.write(np.where(ref, 3600.0, -1.0).astype("float32"), 1)
            d.update_tags(t_inicio_utc=T0)
        (salida / "registro.json").write_text(json.dumps({"entradas": entradas, "ha_quemadas": ha, "motivo_fin": 3}),
                                              encoding="utf-8")
    else:
        perfil.update(dtype="float32", nodata=float("nan"), count=1, compress="deflate")
        with rasterio.open(salida / "hora_llegada_min.tif", "w", **perfil) as d:
            d.write(np.where(ref, 60.0, np.nan).astype("float32"), 1)
        (salida / "registro.json").write_text(json.dumps({"t_inicio_utc": "2023-10-17T03:00:00-03:00", "entradas": entradas,
                                                          "ha_quemadas": ha, "motivo_fin": "sintetica"}), encoding="utf-8")
    base = {"definicion": {"evento": evento, "validar": False, "figuras": False}} if evento else {"escenario": "prueba"}
    escribir_json(c / "corrida.json", {"formato": "incendios_sl.corrida/1.2", "id": id_, "motor": motor, "base": base,
                                       "configuracion": {}, "resultados": {"t_simulado_min": T_SIM_MIN, "ha_final": ha}})
    escribir_json(c / "estado.json", {"id": id_, "motor": motor, "estado": "terminada", "creada_utc": "2026-11-14T00:00:00Z",
                                      "pedido": {"motor": motor, "evento": evento}})
    return c


@pytest.fixture(scope="module")
def servidor(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("historico")
    _corrida_sintetica(carpeta, "sint-v31", "v3.1-libre")
    _corrida_sintetica(carpeta, "sint-v40", "v4.0")
    _corrida_sintetica(carpeta, "sint-sin-evento", "v3.1-librev2", evento=None)
    c = _corrida_sintetica(carpeta, "sint-offline", "v4.0")
    (c / "intervenciones_v31" / "insumo").mkdir(parents=True)
    (c / "intervenciones_v31" / "barreras_enlaces.npz").write_bytes(b"npz de prueba")
    (c / "intervenciones_v31" / "insumo" / "procedencia.json").write_text("{}", encoding="utf-8")
    (c / "cortafuegos_aplicados.geojson").write_text('{"type": "FeatureCollection", "features": []}', encoding="utf-8")
    (c / "meteo_editada.csv").write_text("timestamp,temp_c\n", encoding="utf-8")
    s = Servidor(carpeta)
    yield s
    s.cerrar()


def _metricas(servidor, id_: str, tope_s: float = 60) -> dict:
    limite = time.monotonic() + tope_s
    while True:
        codigo, r = servidor.pedir(f"/api/corridas/{id_}/metricas_v31")
        if codigo == 200:
            return r
        assert codigo == 202, r
        assert time.monotonic() < limite, f"las métricas de {id_} siguen en {r['estado']} después de {tope_s} s"
        time.sleep(0.2)


# ---------------------------------------------------------------------------------------------- lista y rechazos
def test_lista_de_historicos(servidor):
    codigo, r = servidor.pedir("/api/historicos")
    assert codigo == 200
    ev = {e["id"]: e for e in r["eventos"]}
    assert len(ev) == 15
    for id_ in ("SL-2023-CHACRASOCT", "SL-2024-LASLAGUNAS"):
        assert ev[id_]["disponible"] and ev[id_]["se_puede_correr"] and ev[id_]["faltan"] == []
    ch = ev[EV]
    assert ch["rol"] == "no visto (X-49)" and "solo para mostrar" in ch["advertencia"]
    assert ch["recomendada"]["ignicion"] == "alt3" and ch["recomendada"]["hipotesis"] == 4
    assert ch["recomendada"]["t_inicio_utc"] == "2023-10-17T06:00:00Z" and ch["recomendada"]["horas_hasta_fin"] == 141
    assert ch["evaluacion_utc"] == ["2023-10-18T03:00:00Z", "2023-10-20T03:00:00Z", "2023-10-21T03:00:00Z",
                                    "2023-10-23T03:00:00Z"]
    assert ch["fin_simulacion_utc"] == "2023-10-23T03:00:00Z" and ch["n_focos"] == 46 and ch["n_pasadas"] == 7
    assert len(ch["cifras_documentadas"]) == 12
    assert ev["SL-2024-LASLAGUNAS"]["rol"] == "visto"
    assert ev["SL-2024-LASLAGUNAS"]["recomendada"]["v40"].startswith("ignición libre")
    for id_ in X49_SIN_RECOMENDADA:
        assert ev[id_]["rol"] == "no visto (X-49)" and not ev[id_]["se_puede_correr"] and "X-49" in ev[id_]["motivo"]
    sin_datos = [e for e in ev.values() if not e["disponible"]]
    assert len(sin_datos) == 13 and all(e["faltan"] for e in sin_datos)


@pytest.mark.parametrize("evento, cuerpo, codigo, texto", [
    ("SL-2022-LAJULI", {"motores": ["v4.0"]}, 409, "sin ignición recomendada"),
    ("SL-2022-CHILCAS", {"motores": ["v3.1-libre"]}, 409, "faltan datos"),
    ("NO-EXISTE", {"motores": ["v4.0"]}, 404, "no es un evento con ficha"),
    (EV, {"motores": ["v5"]}, 422, "opciones"),
    (EV, {"motores": ["v4.0", "v4.0"]}, 422, "repetidos"),
    (EV, {"motores": ["v4.0"], "horas": 142}, 422, "como mucho 141"),
    (EV, {"motores": ["v4.0", "v3.1-libre", "v3.1-librev2"]}, 409, "el máximo es 2"),
    (EV, {"motores": []}, 422, "motores"),
])
def test_rechazos(servidor, evento, cuerpo, codigo, texto):
    c, r = servidor.pedir(f"/api/historicos/{evento}/corrida", cuerpo)
    assert c == codigo and texto in json.dumps(r, ensure_ascii=False), r


def test_corrida_historica_con_la_ignicion_recomendada(servidor):
    """Sin iniciar: lo que queda en corrida.json. v3.1 y v4.0 por nombre en Las Chacras (las dos fichas coinciden); v4.0 con
    los puntos y la hora de la ficha de v3.1 en Las Lagunas (su ficha no tiene alt0), declarado."""
    codigo, r = servidor.pedir(f"/api/historicos/{EV}/corrida", {"motores": ["v3.1-librev2", "v4.0"], "iniciar": False})
    assert codigo == 201, r
    for c in r["corridas"]:
        cj = json.loads((servidor.app.state.gestor.obtener(c["id"]).carpeta / "corrida.json").read_text(encoding="utf-8"))
        assert {"evento": EV, "hipotesis": 4, "ignicion": "alt3"}.items() <= cj["base"]["definicion"].items()
        assert cj["configuracion"] == {} and cj["historico"]["ignicion"] == "alt3"
        assert any("X-49" in a for a in cj["advertencias"]) and c["pedido"]["historico"]["evento"] == EV
    codigo, r = servidor.pedir("/api/historicos/SL-2024-LASLAGUNAS/corrida", {"motores": ["v4.0"], "horas": 6, "iniciar": False})
    assert codigo == 201, r
    cj = json.loads((servidor.app.state.gestor.obtener(r["corridas"][0]["id"]).carpeta / "corrida.json").read_text(encoding="utf-8"))
    assert "ignicion" not in cj["base"]["definicion"] and "hipotesis" not in cj["base"]["definicion"]
    assert cj["configuracion"]["t_inicio_utc"] == "2024-09-18T13:00:00Z" and cj["configuracion"]["horas"] == 6
    assert [(p["lon"], p["lat"]) for p in cj["configuracion"]["ignicion"]] == \
        [(p["lon"], p["lat"]) for p in r["historico"]["recomendada"]["puntos"]]
    assert cj["historico"]["via_v40"] == "libre" and any("ignición libre" in a for a in cj["advertencias"])


# ---------------------------------------------------------------------------------------------- métricas y focos
@pytest.mark.parametrize("id_, version", [("sint-v31", "v3.1"), ("sint-v40", "v4.0")])
def test_metricas_sobre_salida_sintetica(servidor, id_, version):
    r = _metricas(servidor, id_)
    assert r["estado"] == "lista", r
    m = r["metricas_v31"]
    assert m["version_salida"] == version and m["evento"] == EV
    assert m["metricas"]["iou_igual_sup"] == 1.0 and m["metricas"]["alcanza_sup"] is True
    assert m["metricas"]["horas_hasta_sup"] == 1.0 and m["metricas"]["n_primeras"] > 0
    assert m["evaluador"]["congelado_sha256"] and all(x["igual_al_congelado"] for x in m["evaluador"]["codigo"].values())
    assert [x["despues_del_fin"] for x in m["por_instante"]] == [False, True, True, True]
    assert all(x["iou"] == 1.0 for x in m["por_instante"])
    assert m["focos"] is not None and len(m["focos"]) == 46
    assert sum(p["n"] for p in m["por_pasada"]) == m["metricas"]["n_primeras"] == sum(f["primera"] for f in m["focos"])
    assert any("después del final" in a for a in m["avisos"])


def test_metricas_que_no_corresponden(servidor):
    codigo, r = servidor.pedir("/api/corridas/sint-sin-evento/metricas_v31")
    assert codigo == 404 and "no es de un evento" in r["detail"]
    codigo, _ = servidor.pedir("/api/corridas/no-existe/metricas_v31")
    assert codigo == 404


def test_focos_del_evento(servidor):
    codigo, g = servidor.pedir(f"/api/historicos/{EV}/focos.geojson")
    assert codigo == 200 and len(g["features"]) == 46 and g["n_pasadas"] == 7
    assert {f["properties"]["pasada"] for f in g["features"]} == set(range(1, 8))
    _metricas(servidor, "sint-v31")
    codigo, g = servidor.pedir(f"/api/historicos/{EV}/focos.geojson?corrida=sint-v31")
    assert codigo == 200 and g["clase_por_foco"] is True and g["corrida"] == "sint-v31"
    clases = {"a_tiempo", "adelantado", "atrasado", "no_alcanzado"}
    for f in g["features"]:
        p = f["properties"]
        assert (p["clase"] in clases) if p["primera"] else p["clase"] is None
        assert p["clase_pasada"] in clases | {None}
    codigo, _ = servidor.pedir("/api/historicos/SL-2024-LASLAGUNAS/focos.geojson?corrida=sint-v31")
    assert codigo == 422
    codigo, _ = servidor.pedir("/api/historicos/NO-EXISTE/focos.geojson")
    assert codigo == 404


def test_exportar_incluye_los_archivos_para_la_corrida_offline(servidor):
    _metricas(servidor, "sint-offline")
    codigo, crudo = servidor.pedir("/api/corridas/sint-offline/exportar")
    assert codigo == 200
    nombres = set(zipfile.ZipFile(io.BytesIO(crudo)).namelist())
    for n in ("intervenciones_v31/barreras_enlaces.npz", "intervenciones_v31/insumo/procedencia.json",
              "cortafuegos_aplicados.geojson", "meteo_editada.csv", "metricas_v31.json", "salida/hora_llegada_min.tif"):
        assert f"sint-offline/{n}" in nombres, n
    assert "sint-offline/modificador_aplicado.tif" not in nombres          # no existe: no se inventa


# ---------------------------------------------------------------------------------------------- lenta: criterio de la F6
def test_las_chacras_alt4_v31_da_las_cifras_documentadas(servidor):
    """Criterio de la F6 (D-E3-30, punto 14): las filas de v3.1 alt4 de docs/v4.0/31 §7.2, regeneradas por el servidor con
    el pedido de historico_referencia.json, dan las mismas cifras redondeadas como en el documento."""
    precision = REFERENCIA["precision"]
    filas = [f for f in REFERENCIA["filas"] if f["motor"].startswith("v3.1") and f["ignicion"] == "alt4"]
    assert len(filas) == 2
    ids = {}
    for f in filas:
        assert f["regenerar"]["pedido"] == "POST /api/corridas"
        codigo, r = servidor.pedir("/api/corridas", f["regenerar"]["cuerpo"])
        assert codigo == 201, r
        ids[f["fila"]] = r["corridas"][0]["id"]
    for f in filas:
        fin = servidor.esperar(ids[f["fila"]], "terminada", tope_s=900)
        assert fin["resultados"]["completa"] is True
        m = _metricas(servidor, ids[f["fila"]], tope_s=120)["metricas_v31"]
        assert "error" not in m, m
        obtenido = {k: (round(float(m["metricas"][k])) if precision[k] == 0 else round(float(m["metricas"][k]), precision[k]))
                    for k in f["cifras"]}
        esperado = {k: (round(v) if precision[k] == 0 else round(v, precision[k])) for k, v in f["cifras"].items()}
        assert obtenido == esperado, f"fila {f['fila']} ({f['motor']}): {obtenido} contra {esperado}"
        assert m["metricas"]["n_primeras"] == 30
