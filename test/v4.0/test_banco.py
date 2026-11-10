"""Banco de pruebas de V.4 portado a v4.0 (src/v4.0/app): rutas, registro portable, despacho con caché y evaluador.

Pruebas livianas: no corren SIM ni descargan nada. Las que necesitan datos del repositorio se saltean si faltan.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

CODIGO = Path(__file__).resolve().parents[2] / "src" / "v4.0"
APP = CODIGO / "app"
for _p in (APP, APP / "motores", APP / "evaluador", APP / "banco"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from rutas import Rutas  # noqa: E402

RT = Rutas()


def test_rutas_resuelven_a_archivos_existentes():
    assert RT.raiz == CODIGO.resolve()
    assert RT.repo.name == "Incendios_SanLuis" or (RT.repo / "datos").is_dir()
    archivos = [RT.mascara_dominio, RT.fuego_mensual, RT.poligonos_mapbiomas, RT.firms_viirs, RT.red_vial_grafo, RT.snmf,
                RT.dominio_geojson, RT.cuarteles, RT.protocolo / "eventos_fase1.csv", RT.protocolo / "focos_atribuidos.csv",
                RT.modelos / "sim_v4_original.yaml", RT.modelos / "modelo_v3.yaml", RT.sim_datos / "manifiesto_datos.yaml"]
    archivos += [RT.cobertura(a) for a in range(2021, 2026)]
    faltan = [str(f) for f in archivos if not f.is_file()]
    assert not faltan, faltan
    for d in [RT.meteo_ifs, RT.indices_extra, RT.banco, RT.insumos_banco, *RT.carpetas_indices]:
        assert d.is_dir(), d
    # todo dentro del repositorio estándar (nada de ../Contexto ni de V.4)
    for f in archivos:
        assert RT.repo in f.resolve().parents, f
    # duplicados de V.4 -> archivos de v3.0 en datos/inputSimulacion
    assert RT.mascara_dominio.parent.name == "grilla" and RT.fuego_mensual.parent.name == "cicatrices"
    assert RT.cobertura(2022).parent.name == "cobertura"
    assert RT.banco == (RT.repo / "resultados" / "v4.0" / "banco").resolve()


def test_compuestos_ndvi_ndmi_y_faltantes():
    assert RT.ndvi_ndmi(2022, 9).is_file()                       # indices_extra (generados con el método de AS/)
    f23 = RT.ndvi_ndmi(2023, 1)
    assert f23.is_file() and f23.parent == RT.carpetas_indices[0]  # copia de la entrega en sim_v4/dinamicos/indices
    assert not RT.ndvi_ndmi(2023, 9).exists()                     # mes previo de 26601: no está en este equipo
    with pytest.raises(FileNotFoundError):
        RT.conjunto_pruebas                                       # CP/ de la entrega: no está en este equipo


def test_simulador_raiz_datos():
    from simulador.rutas import raiz_datos
    assert RT.sim_datos == raiz_datos()
    assert RT.sim_datos in RT.insumos_banco.parents


def test_carpeta_corrida_relativa_y_absoluta_vieja():
    rel = RT.carpeta_corrida("corridas/SIM_X_ind-previo")
    assert rel == (RT.banco / "corridas" / "SIM_X_ind-previo").resolve()
    vieja = r"C:\Users\Usuario\Documents\Sim_incendios\V.4\datos\banco\corridas\SIM_MB_2022_43580_2022-09-10_ind-previo"
    assert RT.carpeta_corrida(vieja) == (RT.corridas / "SIM_MB_2022_43580_2022-09-10_ind-previo").resolve()
    assert RT.relativa_banco(RT.corridas / "abc") == "corridas/abc"


def test_registro_rutas_relativas(tmp_path):
    import registro
    if not RT.corridas.is_dir() or not any(RT.corridas.glob("*/registro.json")):
        pytest.skip("sin corridas del banco")
    df = registro.indexar(RT=RT, destino=tmp_path / "registro_corridas.csv")
    assert len(df) > 0
    assert df.carpeta.str.startswith("corridas/").all()
    assert not df.carpeta.str.contains(":").any() and not df.carpeta.str.contains("\\\\", regex=False).any()
    for c, run in zip(df.carpeta, df.run_id):
        d = RT.carpeta_corrida(c)
        assert (d / "registro.json").is_file() and d.name == run
    assert set(df.modelo) >= {registro.MODELO_V4}
    # el registro guardado del banco también es portable
    guardado = registro.leer(RT)
    assert not guardado.carpeta.str.contains(":").any()
    assert all((Path(p) / "registro.json").is_file() for p in guardado.carpeta_abs)


def test_despacho_usa_cache_sin_geojson(tmp_path):
    import despacho
    if not RT.red_vial_grafo.is_file() or not RT.cuarteles.is_file():
        pytest.skip("sin caché del grafo vial o sin cuarteles")

    class SinGeojson(Rutas):
        @property
        def caminos(self):
            return tmp_path / "no_existe.geojson"
    rs = SinGeojson()
    # ignición de MB_2022_43580 (registrada en V.4: Cuartel N° 28 a 58,1 min de viaje)
    caso = RT.banco / "casos" / "MB_2022_43580_2022-09-10" / "ignicion.geojson"
    if not caso.is_file():
        pytest.skip("sin el caso del banco")
    import geopandas as gpd
    xy = gpd.read_file(caso).to_crs("EPSG:5345").geometry
    lleg = despacho.llegadas(rs, float(xy.x.mean()), float(xy.y.mean()), n=3)
    assert len(lleg) == 3 and all(np.isfinite(f["viaje_min"]) for f in lleg)
    assert {"cuartel", "localidad", "viaje_min", "acceso_m", "dist_recta_km"} <= set(lleg[0])
    assert "28" in lleg[0]["cuartel"] and abs(lleg[0]["viaje_min"] - 58.1) < 0.1
    assert lleg[0]["localidad"]                                   # campo `localidad` (alternativa a localidad_mas_cercana)

    class SinNada(SinGeojson):
        @property
        def red_vial_grafo(self):
            return tmp_path / "no_existe.npz"
    with pytest.raises(FileNotFoundError):
        despacho._grafo(SinNada())


def test_evaluador_sintetico_a4():
    import prueba_aceptacion
    r = prueba_aceptacion.prueba_a4()
    assert r["ok"], r
    assert abs(r["iou_obtenido"] - r["iou_teorico"]) <= 0.01 and abs(r["b1_ha"] - 500.0) <= 0.5 and r["b1_centroide_dy_m"] < 0


def test_leer_toa_acepta_t0_utc(tmp_path):
    import rasterio
    import evaluador as ev
    G = ev.grilla_dominio()
    a = np.full((10, 12), np.nan, "float32"); a[2:5, 3:6] = 30.0
    from rasterio.transform import Affine
    tr = G.transform @ Affine.translation(100, 200)
    with rasterio.open(tmp_path / "toa.tif", "w", driver="GTiff", height=10, width=12, count=1, dtype="float32", crs=G.crs,
                       transform=tr, nodata=np.nan) as d:
        d.write(a, 1); d.update_tags(t0_utc="2023-10-17 17:22:00+00:00")
    toa, t0, huella = ev.leer_toa(tmp_path / "toa.tif", "min", G)
    assert t0 == pd.Timestamp("2023-10-17 17:22:00+00:00")
    assert np.nansum(toa == 30.0) == 9 and toa[202, 103] == 30.0 and huella.sum() == 120


def test_adaptador_modelos():
    import sim_adaptador as sa
    nom, ruta, cont = sa.cargar_modelo(RT, "sim_v4_original")
    assert nom == "sim_v4_original" and cont["parametros"]["huygens"] is None
    assert cont["parametros"]["viento"]["factor_10m_20ft"] == pytest.approx(1 / 0.87)
    nom3, _, cont3 = sa.cargar_modelo(RT, "modelo_v3")
    assert nom3 == "modelo_v3" and cont3["parametros"]["extincion"] == "reversible"
    with pytest.raises(SystemExit):
        sa.cargar_modelo(RT, "no_existe")
    assert sa.mes_anterior(2023, 1) == (2022, 12) and sa.mes_anterior(2023, 10) == (2023, 9)
    assert sa.MODELO_DEFECTO == "sim_v4_original"


def test_adaptador_solo_preparar_en_seco(tmp_path, monkeypatch):
    """--solo-preparar no crea la carpeta de la corrida ni registro.json (ni con fallo de preparación)."""
    import sim_adaptador as sa
    if not (RT.protocolo / "eventos_fase1.csv").is_file():
        pytest.skip("sin la lista nominal")
    llamadas = []

    def falso(RT_, fila, focos, indices, horas_extra, descargar, l03, modelo, reusar):
        llamadas.append((fila.id_evento, descargar, modelo[0]))
        return {}, {"fallos": [] if not llamadas[1:] else [{"etapa": "meteo"}], "t0_utc": "2022-10-01 18:07:00+00:00", "duracion_h": 48.0}
    monkeypatch.setattr(sa, "preparar", falso)
    arg = ["--evento", "MB_2022_43580_2022-09-10", "--solo-preparar", "--sin-descarga", "--salida", str(tmp_path)]
    assert sa.main(arg) == 0
    assert sa.main(arg + ["--modelo", "modelo_v3"]) == 2
    assert llamadas == [("MB_2022_43580_2022-09-10", False, "sim_v4_original"), ("MB_2022_43580_2022-09-10", False, "modelo_v3")]
    assert not any(tmp_path.iterdir())


def test_meteo_cubre(tmp_path):
    import sim_adaptador as sa
    f = tmp_path / "m.csv"
    pd.DataFrame({"timestamp": pd.date_range("2022-10-01 12:00", periods=60, freq="h", tz="UTC").astype(str)}).to_csv(f, index=False)
    t0 = pd.Timestamp("2022-10-01 18:07", tz="UTC")
    assert sa.meteo_cubre(f, t0.floor("h"), t0 + pd.Timedelta(hours=49), "timestamp")
    assert not sa.meteo_cubre(f, t0.floor("h"), t0 + pd.Timedelta(hours=60), "timestamp")
    assert not sa.meteo_cubre(tmp_path / "no.csv", t0, t0, "timestamp")


def test_resultados_fase1_regenerados():
    """La Fase 1 regenerada en v4.0 con las corridas de V.4 reproduce la apertura (E023)."""
    f = RT.banco / "fase1" / "resultados_fase1.json"
    if not f.is_file():
        pytest.skip("sin resultados de la Fase 1")
    m = json.loads(f.read_text(encoding="utf-8"))["motores"]["SIM"]
    assert m["skill_F_mediana_IC90"][0] == pytest.approx(0.028379864, abs=1e-6)
    assert m["abs_L_mediana_IC90"][0] == pytest.approx(2.46312933, abs=1e-6)
    assert m["abs_dt_h_mediana_IC90"][0] == pytest.approx(39.195434, abs=1e-5)
    assert m["frac_abs_L_mayor_ln4"] == pytest.approx(2 / 3) and m["aceptable_s9"] is False
