"""Capa estándar de v4.0 (`incendios_sl`): traducción de corridas a SIM, precedencias, insumos de eventos, arribo y L03.

Sin simulaciones: `escenario.traducir(..., preparar=False)` arma la configuración completa sin generar rásteres. Las
pruebas que necesitan datos del repositorio (fichas, arribo vial, departamentos, caché de insumos) se saltan si faltan.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from incendios_sl import arribo, config as cfgmod, escenario, eventos, resumen

LAGUNAS = "SL-2024-LASLAGUNAS"
MESILLA = "SL-2024-MESILLA"
DOMINIO = "las_lagunas_potrerillos"


def _hay_evento(ev=LAGUNAS):
    return (cfgmod.dir_escenarios() / "eventos" / f"{ev}.yaml").exists()


def _hay_arribo():
    return arribo.ruta_arribo(DOMINIO).exists()


necesita_evento = pytest.mark.skipif(not _hay_evento(), reason="falta la ficha del evento")
necesita_arribo = pytest.mark.skipif(not (_hay_evento() and _hay_arribo()), reason="falta el producto de arribo vial de v3.0")


def tr(**esc):
    """Traduce una corrida mínima (evento Las Lagunas 2024, hipótesis 1) sin generar insumos."""
    base = {"evento": LAGUNAS, "hipotesis": 1, "horas": 6}
    if "caso" in esc or "sim" in esc:
        base = {}
    return escenario.traducir(base | esc, preparar=False)


# ------------------------------------------------------------------------------------------------- config
def test_config_v40():
    assert cfgmod.VERSION_RESULTADOS == "v4.0"
    assert cfgmod.dir_escenarios().as_posix().endswith("escenarios/v4.0")
    assert cfgmod.dir_resultados().as_posix().endswith("resultados/v4.0")
    assert cfgmod.dir_entradas().as_posix().endswith("datos/inputSimulacion")
    assert cfgmod.dir_crudos().as_posix().endswith("datos/crudos")
    assert cfgmod.dir_procesados().as_posix().endswith("datos/procesados")
    assert eventos.dir_evento("PRUEBA-X").as_posix().endswith("datos/procesados/v4.0/PRUEBA-X")
    eventos.dir_evento("PRUEBA-X").rmdir()
    m, desc, comb = escenario.cargar_modelo("sim_v4_original")
    assert "descripcion" not in m and desc and comb == {}
    assert m["parametros"]["viento"]["factor_10m_20ft"] == pytest.approx(1 / 0.87)


# ------------------------------------------------------------------------------------------------- corridas incluidas
def test_las_diez_corridas_se_traducen():
    nombres = escenario.lista_corridas()
    assert len(nombres) >= 10 and "prueba_rapida_v4" in nombres
    if not (_hay_evento() and _hay_arribo()):
        pytest.skip("faltan fichas o arribo")
    esperado = {"libre_laslagunas_2024": ("modelo_v3", False, False, False), "local_laslagunas_2024": ("modelo_v3", True, True, False),
                "l03_laslagunas_2024": ("modelo_v3", True, False, True), "v4_original_aguada_2023": ("sim_v4_original", True, False, False),
                "caso_aguada_2023": ("modelo_v3", True, False, False), "prueba_rapida_v4": ("modelo_v3", True, True, False)}
    for n in nombres:
        esc, ruta, nombre = escenario.cargar_corrida(n)
        t = escenario.traducir(esc, ruta, run_id=f"{n}_20260101-0000", preparar=False)
        cfg = t["cfg"]; P = cfg["parametros"]
        assert cfg["nombre"] == f"{n}_20260101-0000" and cfg["duracion_h"] > 0 and cfg["ignicion"], n
        assert t["modo"] in ("evento", "caso", "sim")
        if n in esperado:
            e = t["entradas"]
            assert (e["modelo_nombre"], e["barreras"], e["contencion"], e["supresion"]) == esperado[n], n
    t = escenario.traducir(*escenario.cargar_corrida("prueba_rapida_v4")[:2], preparar=False)
    assert t["cfg"]["duracion_h"] == 6 and t["validar"] is False


@necesita_evento
def test_corridas_de_ejemplo_ejercitan_el_modelo():
    """prueba_rapida_v4 simula siempre las 6 h (sin parada anticipada); el ejemplo de cortafuego dura 36 h (a 24 h el frente
    no llegaba a la línea)."""
    t = escenario.traducir(*escenario.cargar_corrida("prueba_rapida_v4")[:2], preparar=False)
    P = t["cfg"]["parametros"]
    assert t["cfg"]["duracion_h"] == 6 and P["parada"]["contenido"] is False and P["parada"]["horas_sin_avance"] is None
    assert P["contencion"]["activo"] and P["barreras"]["activo"]
    t = escenario.traducir(*escenario.cargar_corrida("mitigacion_cortafuego_ejemplo")[:2], preparar=False)
    assert t["cfg"]["duracion_h"] == 36 and t["cfg"]["parametros"]["barreras"]["extra"].endswith("cortafuego_ejemplo.geojson")


def test_sim_nativo_y_caso():
    t = escenario.traducir({"sim": "sim/ejemplo_las_lagunas_2023.yaml", "horas": 3}, preparar=False)
    assert t["modo"] == "sim" and t["cfg"]["duracion_h"] == 3.0 and t["cfg"]["_ruta"].endswith("ejemplo_las_lagunas_2023.yaml")
    from simulador.rutas import raiz_datos
    if not (raiz_datos() / "conjunto_prueba" / "las_lagunas_la_aguada_2023" / "caso.yaml").exists():
        pytest.skip("falta el caso de prueba")
    t = escenario.traducir({"caso": "las_lagunas_la_aguada_2023", "variante_caso": "dt_5min", "variante": "v4_original"}, preparar=False)
    P = t["cfg"]["parametros"]
    assert t["cfg"]["dt_min"] == 5.0 and t["cfg"]["duracion_h"] == 36
    assert P["huygens"] is None and P["extincion"] == "definitiva" and P["barreras"]["modo"] == "umbral_tipo"
    assert P["parada"]["horas_sin_avance"] is None and P["parada"]["contenido"] is False
    assert not P["contencion"]["activo"] and not P["supresion"]["activo"]
    with pytest.raises(ValueError, match="variante_caso"):
        escenario.traducir({"caso": "las_lagunas_la_aguada_2023", "variante_caso": "no_existe"}, preparar=False)


def test_errores_de_corrida():
    with pytest.raises(ValueError, match="exactamente una fuente"):
        escenario.traducir({"evento": LAGUNAS, "caso": "x"}, preparar=False)
    with pytest.raises(ValueError, match="exactamente una fuente"):
        escenario.traducir({}, preparar=False)
    if not _hay_evento():
        return
    with pytest.raises(ValueError, match="variante"):
        tr(variante="inventada")
    with pytest.raises(ValueError, match="despacho"):
        tr(despacho="aereo")
    with pytest.raises(ValueError, match="k_clase"):
        tr(k_clase={1: 2.0})
    with pytest.raises(ValueError, match="hipótesis"):
        tr(hipotesis=9)
    with pytest.raises(ValueError, match="alt7"):
        tr(ignicion="alt7")


def test_tri():
    assert [escenario.tri(x) for x in (None, "auto", True, "on", "ON", "si", 1, False, "off", "no", 0)] == \
           [None, None, True, True, True, True, True, False, False, False, False]
    with pytest.raises(ValueError):
        escenario.tri("quizas")


# ------------------------------------------------------------------------------------------------- precedencias
@necesita_arribo
def test_variante_fija_modelo_barreras_contencion_despacho():
    for var, (mod, b, c, d) in {"libre": ("modelo_v3", False, False, "fijo"), "barreras": ("modelo_v3", True, False, "fijo"),
                                "contencion": ("modelo_v3", False, True, "fijo"), "ambas": ("modelo_v3", True, True, "fijo"),
                                "local": ("modelo_v3", True, True, "snmf"), "local_pronostico": ("modelo_v3", True, True, "snmf")}.items():
        t = tr(variante=var); P = t["cfg"]["parametros"]
        assert (t["entradas"]["modelo_nombre"], P["barreras"]["activo"], P["contencion"]["activo"], P["contencion"]["despacho"]) == (mod, b, c, d), var
    # global: tasa fija, sin aéreo automático ni intervalos, sin ficha, retardo fijo (inicio_min null)
    P = tr(variante="ambas")["cfg"]["parametros"]["contencion"]
    assert P["aereo_auto"]["activo"] is False and P["aereo_intervalos"] == [] and P["inicio_min"] is None
    # local: ficha + aéreo de la ficha (Las Lagunas tiene intervalos) + retardo vial; pronóstico: sin ficha, aéreo sorteado
    loc = tr(variante="local"); pro = tr(variante="local_pronostico")
    assert loc["entradas"]["despacho"]["usar_ficha"] and not pro["entradas"]["despacho"]["usar_ficha"]
    assert pro["cfg"]["parametros"]["contencion"]["aereo_auto"]["activo"] is True
    assert pro["cfg"]["parametros"]["contencion"]["aereo_intervalos"] == []
    for t in (loc, pro):
        assert t["entradas"]["despacho"]["inicio"] in ("vial", "ficha") and t["cfg"]["parametros"]["contencion"]["inicio_min"] > 0


@necesita_evento
def test_sueltos_pisan_variante():
    t = tr(variante="libre", barreras="on")
    assert t["cfg"]["parametros"]["barreras"]["activo"] is True and t["cfg"]["parametros"]["contencion"]["activo"] is False
    t = tr(variante="libre", barreras="auto")              # auto = lo que diga la variante
    assert t["cfg"]["parametros"]["barreras"]["activo"] is False
    t = tr(barreras="auto")                                # sin variante: lo que diga el modelo (modelo_v3: activas)
    assert t["cfg"]["parametros"]["barreras"]["activo"] is True
    t = tr(variante="v4_original", modelo="modelo_v3")
    assert t["entradas"]["modelo_nombre"] == "modelo_v3" and t["cfg"]["parametros"]["viento"]["factor_10m_20ft"] == pytest.approx(0.87)
    t = tr(variante="v4_original")
    P = t["cfg"]["parametros"]
    assert t["entradas"]["modelo_nombre"] == "sim_v4_original" and P["humedad"]["emc"] == "v4_original" and P["humedad"]["emc_min_pct"] == 2.0
    assert P["barreras"]["llama"] == "cabeza" and P["limite_viento"] == "rothermel_1972"
    t = tr(k_grupo={"gr": 0.5, "SH": 2}, k_global=1.2, factor_waf=0.8, k_codigo={102: 3},
           humedad={"metodo_muerto": "fija", "fija_m1": 0.05, "fija_m10": 0.06, "fija_m100": 0.07}, semilla=7, ensemble=3)
    P = t["cfg"]["parametros"]
    assert P["propagacion"] == {"k_global": 1.2, "k_grupo": {"GR": 0.5, "SH": 2.0}, "k_codigo": {102: 3.0}, "factor_waf": 0.8}
    assert P["humedad"]["metodo_muerto"] == "fija" and P["humedad"]["fija_m100"] == 0.07 and P["humedad"]["emc"] == "nfdrs"
    assert t["cfg"]["semilla"] == 7 and P["barreras"]["semilla"] == 7 and P["contencion"]["semilla"] == 7 and t["cfg"]["ensemble"] == {"n": 3}
    # el modelo entra sin su descripción: la del cfg es la de la corrida
    t = tr(descripcion="mi corrida")
    assert t["cfg"]["descripcion"] == "mi corrida" and "combate" not in t["cfg"]
    t = tr(figuras=False)
    assert t["cfg"]["salidas"]["png"] is False and t["cfg"]["salidas"]["gif"] is False and t["figuras"] is False


@necesita_arribo
def test_despacho_pisa_variante_y_ajustes_pisan_despacho():
    t = tr(variante="ambas", despacho="local")
    P = t["cfg"]["parametros"]["contencion"]
    assert P["despacho"] == "snmf" and t["entradas"]["despacho"]["modo"] == "local" and t["entradas"]["despacho"]["inicio"] in ("vial", "ficha")
    assert t["entradas"]["despacho"]["region"] == "serrano" and P["snmf"]["a"] == 17.3 and P["snmf"]["b"] == 0.36
    t = tr(variante="local", ajustes={"contencion": {"despacho": "fijo", "tasa_linea_m_h": 450}})
    P = t["cfg"]["parametros"]["contencion"]
    assert P["despacho"] == "fijo" and P["tasa_linea_m_h"] == 450
    # ajustes con retardo_h: anula el inicio de la ficha o del arribo vial (van después del despacho)
    t = tr(variante="local", ajustes={"contencion": {"retardo_h": 3}})
    P = t["cfg"]["parametros"]["contencion"]
    assert P["inicio_min"] is None and P["retardo_h"] == 3 and t["entradas"]["despacho"]["inicio"] == "ajustes"
    t = tr(variante="local", ajustes={"contencion": {"inicio_min": 42}})
    assert t["cfg"]["parametros"]["contencion"]["inicio_min"] == 42
    # parche (cfg completo) pisa a ajustes
    t = tr(variante="ambas", ajustes={"contencion": {"tasa_linea_m_h": 500}},
           parche={"dt_min": 1.0, "parametros": {"contencion": {"tasa_linea_m_h": 700}}, "salidas": {"png_cada_h": 6}})
    assert t["cfg"]["parametros"]["contencion"]["tasa_linea_m_h"] == 700 and t["cfg"]["dt_min"] == 1.0 and t["cfg"]["salidas"]["png_cada_h"] == 6
    t = tr(variante="local", parche={"parametros": {"contencion": {"retardo_h": 1}}})
    assert t["cfg"]["parametros"]["contencion"]["inicio_min"] is None and t["entradas"]["despacho"]["inicio"] == "ajustes"


@necesita_arribo
def test_ficha_combate_mesilla():
    t = escenario.traducir({"evento": MESILLA, "hipotesis": 0, "ignicion": "alt1", "variante": "local"}, preparar=False)
    P = t["cfg"]["parametros"]["contencion"]; d = t["entradas"]["despacho"]
    assert P["aereo_auto"]["activo"] is False and P["aereo_intervalos"] == []     # la ficha registra aereo: [] -> sin sorteo
    assert d["inicio"] == "vial" and d["arribo"]["restringido_a_ficha"] is True
    assert d["arribo"]["cuartel_id"] in [7, 29, 22, 21, 31, 18, 41, 30, 34]
    assert P["inicio_min"] == pytest.approx(d["arribo"]["retardo_h"] * 60, abs=0.01)
    assert d["arribo"]["retardo_h"] == pytest.approx(0.75 + d["arribo"]["t_viaje_h"])


@necesita_evento
def test_mitigacion_rutas():
    ruta = cfgmod.dir_escenarios() / "corridas" / "mitigacion_cortafuego_ejemplo.yaml"
    esc, p, _ = escenario.cargar_corrida(archivo=ruta)
    t = escenario.traducir(esc, p, preparar=False)
    extra = t["cfg"]["parametros"]["barreras"]["extra"]
    assert Path(extra).exists() and Path(extra).name == "cortafuego_ejemplo.geojson"
    assert t["entradas"]["mitigacion"]["barreras_extra"].endswith("escenarios/v4.0/mitigacion/cortafuego_ejemplo.geojson")
    with pytest.raises(FileNotFoundError):
        escenario.traducir({"evento": LAGUNAS, "hipotesis": 1, "mitigacion": {"barreras_extra": "no_existe.geojson"}}, preparar=False)


def _sim_desfasado(tmp_path) -> Path:
    """YAML nativo de SIM con t0 a las 10:00 y la ignición a las 12:00 (desfase de 120 min)."""
    p = tmp_path / "desfase.yaml"
    p.write_text('nombre: desfase\nt_inicio: "2023-08-31T10:00:00-03:00"\nduracion_h: 6\nmeteo: meteo.csv\n'
                 'ignicion:\n  - {lon: -65.70, lat: -32.60, hora_ignicion: "2023-08-31T12:00:00-03:00", id: p}\n', encoding="utf-8")
    return p


@necesita_arribo
def test_inicio_vial_suma_desfase_ignicion_t0(tmp_path):
    """Hallazgo 5: el retardo vial se cuenta desde la ignición (como las llegadas L03), no desde t0."""
    t = escenario.traducir({"sim": str(_sim_desfasado(tmp_path)), "variante": "local"}, preparar=False)
    d = t["entradas"]["despacho"]
    assert d["inicio"] == "vial"
    assert t["cfg"]["parametros"]["contencion"]["inicio_min"] == pytest.approx(d["arribo"]["retardo_h"] * 60 + 120.0, abs=0.01)
    t = escenario.traducir({"sim": str(_sim_desfasado(tmp_path)), "variante": "l03"}, preparar=False)
    assert t["cfg"]["parametros"]["supresion"]["llegadas_min"][0] == pytest.approx(t["entradas"]["despacho"]["llegadas_l03"][0]["llegada_min"] + 120.0, abs=0.11)


@necesita_arribo
def test_combate_de_la_corrida_despues_del_preset():
    """Hallazgo 6: el bloque `combate` de la corrida pisa al preset del despacho."""
    t = tr(variante="local", combate={"retardo_modo": "fijo", "usar_ficha": False})
    d = t["entradas"]["despacho"]; P = t["cfg"]["parametros"]["contencion"]
    assert d["retardo_modo"] == "fijo" and d["usar_ficha"] is False and d["inicio"] == "retardo_h" and P["inicio_min"] is None
    assert P["despacho"] == "snmf"                                   # el resto del preset local sigue
    t = tr(variante="ambas", combate={"retardo_modo": "vial"})       # global con arribo vial pedido en la corrida
    assert t["entradas"]["despacho"]["inicio"] == "vial" and t["cfg"]["parametros"]["contencion"]["inicio_min"] > 0


def _con_inicio_ficha(monkeypatch, inicio_utc):
    """La ficha de Las Lagunas con `combate.inicio_utc` (hoy ninguna ficha lo trae)."""
    orig = cfgmod.cargar_evento

    def cargar(i):
        f = orig(i)
        if i == LAGUNAS:
            f["combate"] = dict(f.get("combate") or {}, inicio_utc=inicio_utc)
        return f
    monkeypatch.setattr(cfgmod, "cargar_evento", cargar)


@necesita_arribo
def test_inicio_utc_sin_huso_es_utc(monkeypatch):
    """Hallazgo 8: `combate.inicio_utc` sin huso se toma como UTC (antes: TypeError tz-naive contra tz-aware)."""
    _con_inicio_ficha(monkeypatch, "2024-09-18T17:30:00")
    t = tr(variante="local")                                        # t0 = 15:00 UTC (hipótesis 1)
    assert t["entradas"]["despacho"]["inicio"] == "ficha" and t["cfg"]["parametros"]["contencion"]["inicio_min"] == 150.0
    _con_inicio_ficha(monkeypatch, "2024-09-18T14:30:00-03:00")
    assert tr(variante="local")["cfg"]["parametros"]["contencion"]["inicio_min"] == 150.0
    assert escenario.a_utc("2024-09-18T17:30:00") == pd.Timestamp("2024-09-18T17:30:00Z")


@necesita_arribo
def test_precedencia_contrato_y_v3(monkeypatch):
    """`combate.precedencia`: contrato (ajustes > ficha) por defecto; v3 (ficha > retardo_h de ajustes; inicio_min explícito gana)."""
    _con_inicio_ficha(monkeypatch, "2024-09-18T17:30:00Z")
    aj = {"contencion": {"retardo_h": 3}}
    t = tr(variante="local", ajustes=aj)
    P = t["cfg"]["parametros"]["contencion"]
    assert t["entradas"]["despacho"]["precedencia"] == "contrato" and P["inicio_min"] is None and P["retardo_h"] == 3
    t = tr(variante="local", ajustes=aj, combate={"precedencia": "v3"})
    P = t["cfg"]["parametros"]["contencion"]
    assert t["entradas"]["despacho"]["inicio"] == "ficha" and P["inicio_min"] == 150.0 and P["retardo_h"] == 3
    t = tr(variante="local", ajustes={"contencion": {"inicio_min": 42}}, combate={"precedencia": "v3"})
    assert t["cfg"]["parametros"]["contencion"]["inicio_min"] == 42 and t["entradas"]["despacho"]["inicio"] == "ajustes"
    t = tr(variante="local", parche={"parametros": {"contencion": {"retardo_h": 1}}}, combate={"precedencia": "v3"})
    assert t["cfg"]["parametros"]["contencion"]["inicio_min"] == 150.0
    monkeypatch.undo()                                               # sin inicio en la ficha: retardo_h de ajustes anula el vial (v3.0)
    t = tr(variante="local", ajustes=aj, combate={"precedencia": "v3"})
    assert t["entradas"]["despacho"]["inicio"] == "ajustes" and t["cfg"]["parametros"]["contencion"]["inicio_min"] is None
    assert tr(variante="local", combate={"precedencia": "v3"})["entradas"]["despacho"]["inicio"] in ("vial", "ficha")
    with pytest.raises(ValueError, match="precedencia"):
        tr(variante="local", combate={"precedencia": "v2"})


# ------------------------------------------------------------------------------------------------- combustible pre-evento
def test_indices_verano_regla_y_respaldo(monkeypatch, tmp_path):
    """Regla 3.3: verano ene–mar del año del evento (el anterior si el evento es de ene–mar), cobertura del año anterior
    (o la de la ficha si es anterior); con meses faltantes, mediana parcial o respaldo al compuesto del evento."""
    f = {"inicio": {"fecha_local": "2024-09-18"}, "cobertura_anio": 2023}
    assert eventos.anio_cobertura(f) == 2023 and eventos.anio_cobertura(f | {"cobertura_anio": 2021}) == 2021
    assert eventos.anio_cobertura(f | {"cobertura_anio": 2024}) == 2023 and eventos.anio_cobertura({"inicio": f["inicio"]}) == 2023
    hay = {(2024, 1), (2024, 2), (2024, 3), (2022, 1), (2022, 3)}
    monkeypatch.setattr(eventos, "ruta_compuesto", lambda a, m: tmp_path / f"{a}_{m}.tif" if (a, m) in hay else None)
    v = eventos.indices_verano(f)
    assert (v["anio"], v["meses"], v["regla"], v["faltan"]) == (2024, [1, 2, 3], "verano", [])
    v = eventos.indices_verano({"inicio": {"fecha_local": "2022-09-06"}})
    assert (v["anio"], v["meses"], v["regla"], v["faltan"]) == (2022, [1, 3], "verano_parcial", ["2022-02"])
    v = eventos.indices_verano({"inicio": {"hora_utc_hipotesis": ["2022-01-12T16:00:00Z"]}})    # evento de verano: el anterior
    assert (v["anio"], v["meses"], v["regla"]) == (2021, [], "respaldo_compuesto_evento")
    # mediana por celda con nodata (−32768 → NaN), como sim_adaptador
    import rasterio
    from rasterio.transform import from_origin
    ps = []
    for i, (nv, nm) in enumerate([(1000, 500), (3000, -32768), (2000, 1500)]):
        p = tmp_path / f"c{i}.tif"
        with rasterio.open(p, "w", driver="GTiff", height=1, width=2, count=2, dtype="int16", nodata=-32768,
                           crs="EPSG:5345", transform=from_origin(0, 0, 30, 30)) as d:
            d.write(np.array([[[nv, -32768]], [[nm, -32768]]], "int16"))
        ps.append(p)
    monkeypatch.setattr(eventos, "_grilla_sim", lambda: type("G", (), {"verificar_raster": lambda self, s, n: None})())
    ndvi, ndmi = eventos.mediana_verano(ps)
    assert ndvi[0, 0] == pytest.approx(0.2) and ndmi[0, 0] == pytest.approx(0.1) and np.isnan(ndvi[0, 1])


def _ref_v4(nombre):
    from simulador.rutas import raiz_datos
    return raiz_datos() / "conjunto_prueba" / nombre


@pytest.mark.parametrize("ev, ref", [(LAGUNAS, "las_lagunas_potrerillos_2024"), ("SL-2022-RENCA", "_banco/MB_2022_43580_2022-09-10")])
def test_combustible_pre_evento_igual_a_v4(ev, ref, tmp_path, monkeypatch):
    """El combustible pre-evento (regla 3.3) es idéntico al que arma V.4 para el mismo evento, y la caché vieja (índices
    del compuesto del evento, sin `version_regla`) se regenera sola."""
    if not (_hay_evento(ev) and (_ref_v4(ref) / "combustible_pre_evento.tif").exists()):
        pytest.skip("faltan la ficha o el combustible de referencia de V.4")
    import rasterio
    ficha = cfgmod.cargar_evento(ev)
    if eventos.indices_verano(ficha)["regla"] != "verano":
        pytest.skip("faltan compuestos de verano")
    monkeypatch.setattr(eventos, "dir_evento", lambda i: tmp_path)
    out = tmp_path / "combustible_pre_evento.tif"
    out.write_bytes(b"viejo")                                        # caché vieja con procedencia sin version_regla
    (tmp_path / "combustible_pre_evento.tif.json").write_text(json.dumps(
        {"version": eventos.VERSION_INSUMOS, "parametros": {"cobertura_anio": 2023, "regla": "generar_sb40 (… pre-evento de v3.0)"}, "entradas": []}),
        encoding="utf-8")
    p = eventos.preparar_combustible(ev, ficha)
    d = json.loads((tmp_path / "combustible_pre_evento.tif.json").read_text(encoding="utf-8"))
    assert d["parametros"]["version_regla"] == eventos.VERSION_COMBUSTIBLE and d["parametros"]["regla_indices"] == "verano"
    with rasterio.open(p) as a, rasterio.open(_ref_v4(ref) / "combustible_pre_evento.tif") as b:
        x, y = a.read(1), b.read(1)
    assert int((x != y).sum()) == 0
    combustible = x >= 101
    assert (x == 161).sum() / combustible.sum() < 0.40                # antes ~50 % TU1 con el compuesto de invierno
    pv = eventos.preparar_ndvi_verano(ev, ficha)
    with rasterio.open(pv) as a, rasterio.open(_ref_v4(ref) / "ndvi_verano_previo.tif") as b:
        assert np.array_equal(a.read(1), b.read(1))
    m1 = p.stat().st_mtime_ns
    assert eventos.preparar_combustible(ev, ficha).stat().st_mtime_ns == m1   # vigente: no se regenera


# ------------------------------------------------------------------------------------------------- L03
@necesita_arribo
def test_contrato_l03():
    t = tr(variante="l03")
    P = t["cfg"]["parametros"]; s = P["supresion"]; d = t["entradas"]["despacho"]
    assert s["activo"] is True and P["contencion"]["activo"] is False
    assert s["produccion_linea_m_h"] == 500.0 and s["llama_max_m"] == 2.4
    assert len(s["llegadas_min"]) == 3 == len(d["llegadas_l03"])
    assert s["llegadas_min"] == sorted(s["llegadas_min"])
    for x, lleg in zip(d["llegadas_l03"], s["llegadas_min"]):
        assert lleg == pytest.approx(30.0 + x["viaje_min"], abs=0.11)
    assert len({x["cuartel_id"] for x in d["llegadas_l03"]}) == 3
    lonlat = [(p["lon"], p["lat"]) for p in eventos.puntos_ignicion(cfgmod.cargar_evento(LAGUNAS))[0]]
    assert [x["llegada_min"] for x in arribo.llegadas_l03(DOMINIO, lonlat)] == s["llegadas_min"]
    # las llegadas de ajustes no se recalculan; v4_original no tiene supresión salvo que se pida despacho l03
    t = tr(variante="l03", ajustes={"supresion": {"llegadas_min": [10, 20]}})
    assert t["cfg"]["parametros"]["supresion"]["llegadas_min"] == [10, 20] and "llegadas_l03" not in t["entradas"]["despacho"]
    assert tr(variante="v4_original")["cfg"]["parametros"]["supresion"]["activo"] is False
    t = tr(variante="v4_original", despacho="l03")
    assert t["cfg"]["parametros"]["supresion"]["activo"] is True and t["entradas"]["modelo_nombre"] == "sim_v4_original"


# ------------------------------------------------------------------------------------------------- meteorología
def test_conversion_meteo_unidades_y_huso():
    t = pd.date_range("2024-09-18T12:00Z", periods=6, freq="1h")
    df = pd.DataFrame({"time_utc": t.astype(str), "temperature_2m": [20, 21, 22, 23, 24, 25.0], "relative_humidity_2m": [30, 29, 28, 101, 26, 25.0],
                       "wind_speed_10m": [99.0] * 6, "wind_speed_10m_vectorial": [5.0, 10.0, 0.0, 2.0, 4.0, 1.0],
                       "wind_direction_10m": [0.0, 90.0, 0.0, 180.0, 270.0, 350.0], "precipitation": [0, 0, 1.5, -0.1, 0, 0.0]})
    df = df.drop(index=4)                                   # hueco de 1 h: se interpola en u/v
    m = eventos.convertir_meteo(df)
    assert list(m.columns) == eventos.COLUMNAS_METEO_SIM and len(m) == 6
    assert m["timestamp"].iloc[0] == "2024-09-18T09:00:00-03:00" and all(s.endswith("-03:00") for s in m["timestamp"])
    assert m["viento_kmh"].iloc[0] == pytest.approx(18.0) and m["viento_kmh"].iloc[1] == pytest.approx(36.0)    # vectorial m/s × 3,6
    assert m["viento_dir_deg"].iloc[0] % 360 == pytest.approx(0.0, abs=1e-6) and m["viento_dir_deg"].iloc[1] == pytest.approx(90.0)
    assert m["viento_dir_deg"].iloc[3] == pytest.approx(180.0) and m["viento_dir_deg"].iloc[5] == pytest.approx(350.0)
    # hora 4 interpolada entre (2 m/s desde S) y (1 m/s desde 350°): u, v promediados
    assert 0 < m["viento_kmh"].iloc[4] < 7.2
    assert m["hr_pct"].max() <= 100 and m["precip_mm"].min() >= 0 and m["temp_c"].iloc[4] == pytest.approx(24.0)
    sin_vec = df.drop(columns="wind_speed_10m_vectorial").assign(wind_speed_10m=3.0)
    assert eventos.convertir_meteo(sin_vec)["viento_kmh"].iloc[0] == pytest.approx(10.8)
    hueco = df.drop(index=[1, 2, 3])                         # 4 h sin datos: error
    with pytest.raises(ValueError, match="huecos"):
        eventos.convertir_meteo(hueco)


def test_meteo_cacheada_de_simulacion():
    p = eventos.dir_evento(LAGUNAS) / "meteo_horaria.csv"
    if not p.exists():
        pytest.skip("sin caché de insumos")
    from simulador.io.manifiesto import validar_meteo_csv
    validar_meteo_csv(p)
    m = pd.read_csv(p)
    assert m["timestamp"].str.endswith("-03:00").all()
    src = pd.read_csv(eventos.ruta_meteo_v3(LAGUNAS))
    k = pd.to_datetime(src["time_utc"], utc=True) == pd.Timestamp(m["timestamp"].iloc[10]).tz_convert("UTC")
    assert m["viento_kmh"].iloc[10] == pytest.approx(float(src.loc[k, "wind_speed_10m_vectorial"].iloc[0]) * 3.6, abs=2e-3)


# ------------------------------------------------------------------------------------------------- igniciones
@necesita_evento
def test_igniciones_por_hipotesis_y_alternativa():
    f = cfgmod.cargar_evento(MESILLA)
    p, fuente = eventos.puntos_ignicion(f, "snmf")
    assert p[0]["lon"] == -65.8132 and "SNMF" in fuente
    assert eventos.puntos_ignicion(f, "alt1")[0][0]["lat"] == -32.53554
    with pytest.raises(ValueError, match="inválida"):
        eventos.puntos_ignicion(f, "norte")
    for h, hora in enumerate(f["inicio"]["hora_utc_hipotesis"]):
        t0, t_fin = eventos.tiempos(f, h)
        assert t0 == pd.Timestamp(hora) and t_fin == pd.Timestamp(f["fin"]["fin_simulacion_utc"])
        ign = eventos.igniciones(f, h, "alt0")
        assert ign[0]["hora_ignicion"] == t0.tz_convert(eventos.HUSO_SIM).isoformat() and ign[0]["hora_ignicion"].endswith("-03:00")
    t0, t_fin = eventos.tiempos(f, 1, horas=10)
    assert (t_fin - t0) == pd.Timedelta(hours=10)
    cfg, meta = eventos.insumos_evento(MESILLA, 2, "alt1", 24, preparar=False)
    assert cfg["t_inicio"] == "2024-09-02T08:00:00-03:00" and cfg["duracion_h"] == 24
    assert meta["ignicion"] == "alt1" and meta["hipotesis_ignicion"] == 2 and meta["t_fin_utc"] == "2024-09-03T11:00:00+00:00"
    assert cfg["meteo"].endswith("meteo_horaria.csv") and cfg["combustible"].endswith("combustible_pre_evento.tif")


def test_igniciones_desplazadas_a_combustible():
    comb = eventos.dir_evento(MESILLA) / "combustible_pre_evento.tif"
    if not comb.exists():
        pytest.skip("sin caché de insumos")
    import rasterio
    from pyproj import Transformer
    f = cfgmod.cargar_evento(MESILLA)
    ign = eventos.igniciones(f, 0, "snmf", comb, eventos.ruta_cicatriz(MESILLA))
    with rasterio.open(comb) as s:
        a = s.read(1); x, y = Transformer.from_crs(4326, s.crs, always_xy=True).transform(ign[0]["lon"], ign[0]["lat"])
        fi, co = s.index(x, y)
    assert a[fi, co] >= 101                                  # combustible (no NB ni sin dato)
    if "desplazada_m" in ign[0]:
        assert ign[0]["desplazada_m"] > 0


# ------------------------------------------------------------------------------------------------- región y arribo
def test_region_despacho():
    assert arribo.region_despacho("GENERAL PEDERNERA") == "periurbano"
    assert arribo.region_despacho("Juan Martin de Pueyrredon") == "periurbano"
    assert arribo.region_despacho("GOBERNADOR DUPUY") == "llanura_sur"
    assert arribo.region_despacho("LIBERTADOR GENERAL SAN MARTIN") == "serrano"
    assert arribo.region_despacho(None) == "serrano"
    assert arribo.region_despacho("X", {"r1": {"departamentos": ["X"]}}, "otra") == "r1"
    assert arribo.region_despacho("Y", {"r1": {"departamentos": ["X"]}}, "otra") == "otra"


def test_departamento_de():
    if not (cfgmod.dir_crudos() / "departamentos_san_luis_ign_conae.geojson").exists():
        pytest.skip("falta la capa de departamentos")
    assert arribo.departamento_de(-65.8132, -32.5466) == "LIBERTADOR GENERAL SAN MARTIN"
    assert arribo.departamento_de(-58.4, -34.6) is None      # Buenos Aires: fuera de la provincia


def _npz(tmp_path):
    """Producto de arribo sintético: 3 cuarteles, grilla 4×4 de 1 km en EPSG:5345."""
    T = np.full((3, 4, 4), np.inf)
    T[0] = 2.0; T[1, 1, 1] = 0.5; T[1, 2, 2] = 0.25; T[2, :2, :] = 1.0
    g = {"crs": "EPSG:5345", "res": 1000.0, "xmin": 3530000.0, "ymax": 6400000.0, "ncol": 4, "nfil": 4}
    p = tmp_path / "arribo_sintetico.npz"
    np.savez(p, tiempo_h=T, ids=np.array([10, 20, 30]), nombres=np.array(json.dumps(["A", "B", "C"])), grilla=np.array(json.dumps(g)))
    from pyproj import Transformer
    tr_ = Transformer.from_crs(5345, 4326, always_xy=True)
    centro = lambda f, c: tr_.transform(g["xmin"] + (c + 0.5) * 1000, g["ymax"] - (f + 0.5) * 1000)
    return p, centro


def test_tiempo_arribo_sintetico(tmp_path):
    p, centro = _npz(tmp_path)
    r = arribo.tiempo_arribo(p, [centro(1, 1)])
    assert r["cuartel_id"] == 20 and r["t_viaje_h"] == 0.5
    r = arribo.tiempo_arribo(p, [centro(1, 1), centro(2, 2)])          # mínimo sobre los puntos
    assert r["t_viaje_h"] == 0.25
    r = arribo.tiempo_arribo(p, [centro(1, 1)], ids_permitidos=[10, 30])
    assert r["cuartel_id"] == 30 and r["t_viaje_h"] == 1.0 and r["restringido_a_ficha"]
    r = arribo.tiempo_arribo(p, [centro(1, 1)], ids_permitidos=[99])    # ninguno en el producto: todos
    assert r["cuartel_id"] == 20 and not r["restringido_a_ficha"]
    t = arribo.tiempos_por_cuartel(p, [centro(3, 3)])
    assert t[0] == 2.0 and np.isinf(t[1]) and np.isinf(t[2])


def test_llegadas_l03_sinteticas(tmp_path, monkeypatch):
    p, centro = _npz(tmp_path)
    monkeypatch.setattr(arribo, "ruta_arribo", lambda dominio: p)
    ll = arribo.llegadas_l03("x", [centro(1, 1)])
    assert [x["cuartel_id"] for x in ll] == [20, 30, 10] and [x["llegada_min"] for x in ll] == [60.0, 90.0, 150.0]
    ll = arribo.llegadas_l03("x", [centro(3, 3)], n=3, demora_min=10)      # solo un cuartel alcanza
    assert [(x["cuartel"], x["llegada_min"]) for x in ll] == [("A", 130.0)]
    r = arribo.inicio_combate_vial("x", [centro(1, 1)], [10], t_aviso_h=0.5, t_despacho_h=0.25)
    assert r["retardo_h"] == pytest.approx(2.75) and r["cuartel"] == "A"
    assert arribo.inicio_combate_vial("x", [centro(3, 3)], [20]) is None                # el cuartel de la ficha no llega
    monkeypatch.setattr(arribo, "ruta_arribo", lambda dominio: tmp_path / "no_existe.npz")
    assert arribo.llegadas_l03("x", [centro(1, 1)]) == [] and arribo.inicio_combate_vial("x", [centro(1, 1)]) is None


# ------------------------------------------------------------------------------------------------- resumen
def test_resumen_y_registro(tmp_path):
    reg = {"run_id": "prueba_20261025-1800", "nombre_escenario": "prueba", "fecha_corrida": "2026-10-25T18:01:00-03:00",
           "version_codigo": "4.0.0", "modo_entrada": "evento", "motivo_fin": "contenido", "motivo_fin_texto": "Frente contenido.",
           "duracion_pedida_h": 48.0, "t_simulado_s": 3 * 3600.0, "ha_quemadas": 12.5, "segundos": 4.2,
           "entradas": {"evento": LAGUNAS, "hipotesis_ignicion": 1, "ignicion": "snmf", "modelo_nombre": "modelo_v3", "variante": "local",
                        "barreras": True, "contencion": True, "despacho": {"modo": "local", "inicio": "vial", "region": "serrano"}},
           "config": {"dt_min": 2.0, "parametros": {"contencion": {"inicio_min": 70.6, "despacho": "snmf"}}}}
    (tmp_path / "registro.json").write_text(json.dumps(reg), encoding="utf-8")
    pd.DataFrame({"hora": [0, 1, 2, 3], "timestamp": ["a", "b", "c", "d"], "superficie_quemada_ha": [0.2, 3, 10, 12.5],
                  "frente_celdas_activas": [1, 5, 3, 0], "meteo_viento_kmh": [10, 12, 14, 9], "meteo_hr_pct": [20, 22, 25, 30],
                  "meteo_temp_c": [25, 26, 27, 24]}).to_csv(tmp_path / "serie_indicadores.csv", index=False)
    pj, pm = resumen.escribir_resumen(tmp_path)
    assert pj.name == "resumen_prueba_20261025-1800_20261025-1801.json" and pm.exists()
    r = json.loads(pj.read_text(encoding="utf-8"))
    assert r["motivo_fin"] == "contenido" and r["horas_simuladas"] == 3.0 and r["serie"]["max_ha_por_hora"] == 7.0
    assert r["serie"]["ha_a_24h"] == 12.5 and r["serie"]["ha_a_72h"] is None      # parada anticipada: área congelada hasta 48 h
    assert "contenido" in pm.read_text(encoding="utf-8")
    assert resumen.motivo_fin({"metadata": {"motivo_fin": "sin_avance", "motivo_fin_texto": "x"}}) == ("sin_avance", "x")
    assert resumen.cfg_limpio({"_dir": "c:/x", "a": {"_ruta": 1, "b": 2}}) == {"a": {"b": 2}}


def test_resumen_inicio_de_combate_real(tmp_path):
    """Con despacho global el cfg deja inicio_min null (usa retardo_h): el resumen toma el inicio real de metadata.json."""
    reg = {"run_id": "g_20261025-1800", "fecha_corrida": "2026-10-25T18:01:00-03:00", "motivo_fin": "horizonte", "t_simulado_s": 3600.0,
           "entradas": {"evento": LAGUNAS, "contencion": True, "despacho": {"modo": "global", "inicio": "retardo_h"}},
           "config": {"parametros": {"contencion": {"inicio_min": None, "retardo_h": 2.0, "despacho": "fijo"}}}}
    (tmp_path / "registro.json").write_text(json.dumps(reg), encoding="utf-8")
    (tmp_path / "metadata.json").write_text(json.dumps({"contencion": {"inicio_min": 120.0, "inicio_utc": "2023-08-31T17:00:00+00:00"}}), encoding="utf-8")
    r = resumen.resumen_de_corrida(tmp_path)
    assert r["mitigacion"]["contencion_inicio_min"] == 120.0 and r["mitigacion"]["contencion_inicio_utc"].startswith("2023-08-31T17")
    assert "/ 120 min (2023-08-31T17:00 UTC)" in resumen._md(r)
    (tmp_path / "metadata.json").unlink()                            # sin metadata: retardo_h × 60
    assert resumen.resumen_de_corrida(tmp_path)["mitigacion"]["contencion_inicio_min"] == 120.0


def test_metricas_espaciales():
    sim = np.array([[1, 1, 0], [0, 1, 0]], bool); ref = np.array([[1, 0, 0], [0, 1, 1]], bool); val = np.ones_like(sim)
    m = resumen.metricas_espaciales(sim, ref, val, 30.0)
    assert m["iou"] == pytest.approx(2 / 4) and m["dice"] == pytest.approx(4 / 6)
    assert m["omision"] == pytest.approx(1 / 3) and m["comision"] == pytest.approx(1 / 3) and m["ha_sim"] == pytest.approx(0.27)
