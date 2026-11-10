"""Tests de grilla, manifiesto, meteorología y carga de capas (usan los datos preparados si existen)."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from simulador.io.grilla import Grilla, ErrorGrilla
from simulador.io.manifiesto import Manifiesto, ErrorManifiesto, validar_meteo_csv
from simulador.io.meteo import SerieMeteo

RAIZ = Path(__file__).resolve().parents[2] / "datos" / "inputSimulacion" / "sim_v4"   # carpeta del manifiesto en v4.0
MAN = RAIZ / "manifiesto_datos.yaml"


def test_grilla_ventana_alineada():
    g = Grilla("EPSG:5345", 3513060, 6417900, 30, 1672, 1671)
    sub, win = g.ventana(3529230, 6388890, 3540540, 6400170)
    assert (sub.ancho, sub.alto) == (377, 376) and win.col_off == 539 and win.row_off == 591
    with pytest.raises(ErrorGrilla):
        g.ventana(3529235, 6388890, 3540540, 6400170)      # no alineada
    with pytest.raises(ErrorGrilla):
        g.ventana(3500000, 6388890, 3540540, 6400170)      # fuera del dominio


def test_meteo_csv_invalido(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text("timestamp,temp_c,hr_pct,viento_kmh,viento_dir_deg,precip_mm,fuente\n2024-01-01T00:00:00,20,50,10,0,0,x\n2024-01-01T01:00:00,20,50,10,0,0,x\n")
    with pytest.raises(ErrorManifiesto):
        validar_meteo_csv(p)        # sin huso horario
    p.write_text("timestamp,temp_c,hr_pct,viento_kmh,viento_dir_deg,precip_mm,fuente\n2024-01-01T00:00:00-03:00,20,50,10,0,0,x\n2024-01-01T02:00:00-03:00,20,50,10,0,0,x\n")
    with pytest.raises(ErrorManifiesto):
        validar_meteo_csv(p)        # hueco


def test_interpolacion_viento_por_componentes():
    df = pd.DataFrame({"timestamp": ["2024-01-01T00:00:00-03:00", "2024-01-01T01:00:00-03:00"], "temp_c": [20, 22], "hr_pct": [50, 40],
                       "viento_kmh": [10, 10], "viento_dir_deg": [350, 10], "precip_mm": [0, 0], "fuente": "t"})
    s = SerieMeteo(df)
    e = s.en(pd.Timestamp("2024-01-01T00:30:00-03:00"))
    assert abs(e.viento_dir_deg - 0) < 1e-6 or abs(e.viento_dir_deg - 360) < 1e-6   # no 180
    assert abs(e.temp_c - 21) < 1e-9


def test_barreras_extra_rasterizadas(tmp_path):
    """`barreras.extra`: líneas con ancho_m (y tipo opcional) → camino tipo cortafuego; gana la más ancha."""
    import geopandas as gpd
    from shapely.geometry import LineString
    from simulador.io.capas import rasterizar_barreras_extra, TIPOS_CAMINO
    from simulador.sintetico import capas_sinteticas
    cap = capas_sinteticas(21, 102)
    cap.camino_ancho[:, 10] = 8.0; cap.camino_tipo[:, 10] = TIPOS_CAMINO.index("pavimentado")
    y = 21 * 30 - 5 * 30 - 15                                         # centro de la fila 5
    gdf = gpd.GeoDataFrame({"ancho_m": [12.0, 4.0], "tipo": [None, "huella"]},
                           geometry=[LineString([(0, y), (630, y)]), LineString([(15 * 30 + 15, 0), (15 * 30 + 15, 630)])], crs=cap.grilla.crs)
    ruta = tmp_path / "barreras.geojson"; gdf.to_file(ruta, driver="GeoJSON")
    rasterizar_barreras_extra(cap, ruta)
    assert TIPOS_CAMINO.index("cortafuego") == 4
    assert cap.camino_tipo[5, 3] == 4 and cap.camino_ancho[5, 3] == 12.0
    assert cap.camino_tipo[5, 10] == 4 and cap.camino_ancho[5, 10] == 12.0      # el cortafuego (12 m) pisa el pavimento (8 m)
    assert cap.camino_tipo[12, 10] == 0 and cap.camino_ancho[12, 10] == 8.0
    assert cap.camino_tipo[12, 15] == TIPOS_CAMINO.index("huella") and cap.camino_ancho[12, 15] == 4.0
    assert cap.fuentes["barreras_extra"] == str(ruta) and len(cap.barreras_gdf) == 2


@pytest.mark.skipif(not MAN.exists(), reason="manifiesto no preparado")
def test_manifiesto_valida():
    man = Manifiesto.cargar(MAN)
    assert man.validar(verificar_sha=False, verbose=False)


@pytest.mark.skipif(not MAN.exists(), reason="manifiesto no preparado")
def test_manifiesto_detecta_sha_alterado(tmp_path):
    import shutil, yaml
    man = Manifiesto.cargar(MAN)
    d = yaml.safe_load(MAN.read_text(encoding="utf-8"))
    d["entradas"][0]["sha256"] = "0" * 64
    p = tmp_path / "manifiesto_datos.yaml"
    p.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    # mismas rutas relativas: se copia la raíz como enlace lógico
    m2 = Manifiesto.cargar(p); m2.raiz = RAIZ
    with pytest.raises(ErrorManifiesto):
        m2.validar(verificar_sha=True, verbose=False)


@pytest.mark.skipif(not MAN.exists(), reason="manifiesto no preparado")
def test_carga_capas_ventana():
    from simulador.io.capas import cargar_capas
    man = Manifiesto.cargar(MAN)
    cap = cargar_capas(man, (3529230, 6388890, 3540540, 6400170))
    assert cap.shape == (376, 377) and cap.combustible.dtype == np.int16
    assert cap.camino_ancho.max() > 0 and cap.linea_mt.any()
