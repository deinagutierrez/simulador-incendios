"""Pruebas de los datos dinámicos (fase F4, `app/datos`). No usan internet.

- Sentinel-2: compuesto con ítems STAC falsos y un lector de bandas falso (índices, máscara SCL, mosaico por fecha, mediana,
  n_obs, nodata, grilla de salida, procedencia) y búsqueda en el catálogo con una sesión falsa (paginado y nubes).
- Meteorología: CSV cargado a mano en los formatos de v3.x y v4.0 y sus rechazos; modo escenario.
- Índices cargados a mano: TIF aceptado y rechazos; ventana de tiempo real.
- Evento generado de punta a punta por el proceso de datos (escenario → índices a mano → evento), sin red. Esa prueba
  escribe en la caché y en las entradas reales y borra todo lo que crea.

Las demás usan una caché temporal (se reemplaza `comun.CACHE`).
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))

from datos import comun, evento_rt, indices, meteo, sentinel2 as s2   # noqa: E402

PROCESO_DATOS = REPO / "app" / "datos" / "proceso_datos.py"
LAGUNAS = REPO / "datos" / "inputSimulacion" / "combustibles" / "SL-2024-LASLAGUNAS"
ND = comun.NODATA_INDICES


@pytest.fixture
def cache(tmp_path, monkeypatch):
    """Caché temporal: nada de estas pruebas queda en `datos/procesados/app`."""
    c = tmp_path / "cache"
    monkeypatch.setattr(comun, "CACHE", c)
    return c


# =================================================================== Sentinel-2
# Dos fechas y dos teselas que se solapan. Valores de DN constantes por (fecha, tesela, banda):
#   tesela A cubre las columnas [0, mitad + 10); tesela B cubre [mitad − 10, ncol − 3); las 3 últimas columnas, ninguna.
#   2026-10-01 A: nubes (SCL 9) en las filas 0-9.       2026-10-11 B: B11 = 0 (sin dato) en las filas 20-29.
DN = {
    ("2026-10-01", "A"): {"B04": 1000, "B08": 3000, "B8A": 2600, "B11": 2000},   # NDVI 0,5  NDMI(B08) 0,2  NDMI(B8A) 0,130435
    ("2026-10-01", "B"): {"B04": 2000, "B08": 3000, "B8A": 3000, "B11": 1000},   # NDVI 0,2  NDMI 0,5
    ("2026-10-11", "A"): {"B04": 500, "B08": 4500, "B8A": 4500, "B11": 1500},    # NDVI 0,8  NDMI 0,5
    ("2026-10-11", "B"): {"B04": 1000, "B08": 1000, "B8A": 1000, "B11": 3000},   # NDVI 0    NDMI −0,5
}


def _item(fecha: str, tesela: str, nubes: float = 10.0) -> dict:
    id_ = f"S2X_T20H{tesela}_{fecha.replace('-', '')}_0_L2A"
    return {"id": id_, "properties": {"datetime": f"{fecha}T14:30:00Z", "grid:code": f"MGRS-20H{tesela}",
                                      "eo:cloud_cover": nubes, "s2:processing_baseline": "05.11",
                                      "earthsearch:boa_offset_applied": True},
            "assets": {a: {"href": f"falso://{fecha}/{tesela}/{b}"} for b, a in s2.ACTIVOS.items()}}


def _items() -> list[dict]:
    return [_item(f, t) for f, t in sorted(DN)]


class Lector:
    """Lector falso: devuelve la banda pedida en la grilla pedida y anota las lecturas."""

    def __init__(self):
        self.lecturas = []

    def __call__(self, href: str, grilla, remuestreo: str, nivel_20m: bool) -> np.ndarray:
        _, resto = href.split("://")
        fecha, tesela, banda = resto.split("/")
        self.lecturas.append((fecha, tesela, banda, remuestreo, nivel_20m))
        nf, nc = grilla.forma
        mitad = nc // 2
        cubre = np.zeros((nf, nc), bool)
        if tesela == "A":
            cubre[:, :mitad + 10] = True
        else:
            cubre[:, mitad - 10:nc - 3] = True
        if banda == "SCL":
            a = np.where(cubre, 4, 0).astype("uint16")             # 4 = vegetación
            if (fecha, tesela) == ("2026-10-01", "A"):
                a[:10][cubre[:10]] = 9                             # nube alta
            return a
        a = np.where(cubre, DN[(fecha, tesela)][banda], 0).astype("uint16")
        if (fecha, tesela, banda) == ("2026-10-11", "B", "B11"):
            a[20:30] = 0
        return a


def _celdas(nc: int) -> dict[str, tuple[int, int]]:
    mitad = nc // 2
    return {"A": (50, 5), "A_nube": (5, 5), "solape": (50, mitad), "solape_nube": (5, mitad), "B": (50, nc - 5),
            "B_sin_b11": (25, nc - 5), "nada": (50, nc - 1)}


def test_componer_indices_mascara_mosaico_mediana(cache):
    g = comun.Grilla("EPSG:5345", 30.0, 0.0, 0.0, 30.0 * 80, 30.0 * 60)
    lector = Lector()
    c = s2.componer(_items(), g, s2.metodo_ventana(), hilos=2, lector=lector)
    k = _celdas(g.ncol)
    esperado = {  # celda: (NDVI, NDMI, n_obs)
        "A": (0.65, 0.35, 2),               # mediana de A en las dos fechas
        "A_nube": (0.8, 0.5, 1),            # la nube de la primera fecha deja solo la segunda
        "solape": (0.65, 0.35, 2),          # en el solape gana la primera tesela con dato (A)
        "solape_nube": (0.5, 0.5, 2),       # A con nube el 1/10 → B (0,2; 0,5); el 11/10, A (0,8; 0,5)
        "B": (0.1, 0.0, 2),
        "B_sin_b11": (0.2, 0.5, 1),         # B11 = 0 es sin dato: la segunda fecha no cuenta
        "nada": (np.nan, np.nan, 0),
    }
    for nombre, (v, m, n) in esperado.items():
        f, col = k[nombre]
        np.testing.assert_allclose(c.ndvi[f, col], v, atol=1e-4, err_msg=f"NDVI en {nombre}")
        np.testing.assert_allclose(c.ndmi[f, col], m, atol=1e-4, err_msg=f"NDMI en {nombre}")
        assert c.n_obs[f, col] == n, nombre
    assert c.fechas == ["2026-10-01", "2026-10-11"]
    assert c.ndvi.dtype == np.float32 and c.n_obs.dtype == np.uint8 and c.ndvi.shape == g.forma
    assert len(c.escenas) == 4 and c.de_cache == 0
    # bandas pedidas: B04, B08, B11 (NDMI con B08) y SCL; las de 10 m desde su nivel de 20 m, promedio
    bandas = {(b, r, n20) for _, _, b, r, n20 in lector.lecturas}
    assert bandas == {("SCL", "nearest", False), ("B04", "average", True), ("B08", "average", True),
                      ("B11", "average", False)}
    # la segunda vez sale todo de la caché por escena, sin leer
    lector2 = Lector()
    c2 = s2.componer(_items(), g, s2.metodo_ventana(), lector=lector2)
    assert c2.de_cache == 4 and lector2.lecturas == []
    np.testing.assert_array_equal(np.nan_to_num(c2.ndvi, nan=9), np.nan_to_num(c.ndvi, nan=9))
    assert len(list((cache / "sentinel2" / "escenas").glob("ventana_*/*.npz"))) == 4


def test_componer_sin_escenas_o_todo_nublado(cache):
    g = comun.Grilla("EPSG:5345", 30.0, 0.0, 0.0, 300.0, 300.0)
    with pytest.raises(ValueError, match="no hay escenas"):
        s2.componer([], g, s2.metodo_ventana())

    def nublado(href, grilla, remuestreo, nivel_20m):
        return np.full(grilla.forma, 9 if href.endswith("SCL") else 1000, "uint16")
    with pytest.raises(ValueError, match="despejadas"):
        s2.componer([_item("2026-10-01", "A")], g, s2.metodo_ventana(), lector=nublado)


def _leer_tif(ruta: Path):
    import rasterio
    with rasterio.open(ruta) as s:
        return s.read(), s.profile, s.transform, s.crs


def test_compuesto_ventana_salida_y_procedencia(cache, tmp_path):
    salida = tmp_path / "ventana"
    r = s2.compuesto_ventana(dt.date(2026, 9, 27), dt.date(2026, 11, 10), salida, "prueba", items=_items(), lector=Lector())
    g = comun.grilla_indices_20m()
    assert r["fechas"] == ["2026-10-01", "2026-10-11"] and r["n_escenas"] == 4
    k = _celdas(g.ncol)
    for prod, esperado in (("ndvi", {"A": 6500, "A_nube": 8000, "B": 1000, "nada": ND}),
                           ("ndmi", {"A": 3500, "B_sin_b11": 5000, "B": 0, "nada": ND})):
        a, perfil, tr, crs = _leer_tif(Path(r[prod]))
        assert a.shape == (1, *g.forma) and perfil["dtype"] == "int16" and perfil["nodata"] == ND
        assert tr.almost_equals(g.transform) and crs.to_epsg() == 5345
        for nombre, v in esperado.items():
            assert a[0][k[nombre]] == v, (prod, nombre)
        proc = json.loads(Path(r[prod] + ".json").read_text(encoding="utf-8"))
        assert proc["sha256"] == comun.sha256(Path(r[prod]))
        assert proc["parametros"]["ventana"] == ["2026-09-27", "2026-11-10"]
        assert proc["parametros"]["metodo"]["ndmi"] == "(B08-B11)/(B08+B11)"
        assert proc["parametros"]["grilla"] == g.como_dict() and proc["n_fechas"] == 2
    n, perfil, tr, _ = _leer_tif(Path(r["n_obs"]))
    assert perfil["dtype"] == "uint8" and n[0][k["A"]] == 2 and n[0][k["A_nube"]] == 1 and n[0][k["nada"]] == 0
    meta = json.loads(Path(r["metadatos"]).read_text(encoding="utf-8"))
    assert meta["fechas"] == r["fechas"] and len(meta["escenas"]) == 4
    assert meta["escenas"][0]["tesela"] == "20HA" and meta["celdas_sin_dato_pct"] > 0


def test_compuesto_mensual_dos_bandas_b8a(cache, tmp_path):
    lector = Lector()
    r = s2.compuesto_mensual(2026, 10, tmp_path, items=_items(), lector=lector)
    g = comun.grilla_dominio()
    assert Path(r["ruta"]).name == "NDVI_NDMI_2026_10.tif"
    a, perfil, tr, crs = _leer_tif(Path(r["ruta"]))
    assert a.shape == (2, *g.forma) and perfil["dtype"] == "int16" and perfil["nodata"] == ND
    assert tr.almost_equals(g.transform) and crs.to_epsg() == 5345
    k = _celdas(g.ncol)
    assert a[0][k["A"]] == 6500
    # NDMI con B8A: mediana de 0,130435 (2026-10-01) y 0,5 (2026-10-11)
    esperado = np.median([round(600 / 4600 * 10000), 5000]) / 10000
    assert a[1][k["A"]] == int(round(esperado * 10000))
    assert a[0][k["nada"]] == ND and a[1][k["nada"]] == ND
    assert {b for _, _, b, *_ in lector.lecturas} == {"SCL", "B04", "B08", "B8A", "B11"}
    assert all(r_ == "nearest" for _, _, b, r_, _ in lector.lecturas)
    proc = json.loads(Path(r["ruta"] + ".json").read_text(encoding="utf-8"))
    assert proc["parametros"]["mes"] == "2026-10" and proc["parametros"]["metodo"]["ndmi"] == "(B8A-B11)/(B8A+B11)"
    assert proc["sha256"] == comun.sha256(Path(r["ruta"])) and proc["fechas"] == r["fechas"]


class _Respuesta:
    def __init__(self, datos):
        self.datos = datos

    def raise_for_status(self):
        pass

    def json(self):
        return self.datos


class _Sesion:
    """Catálogo falso con dos páginas; la siguiente se pide por POST con el cuerpo que indica el enlace `next`."""

    def __init__(self):
        self.pedidos = []

    def post(self, url, json=None, timeout=None):
        self.pedidos.append(("POST", url, json))
        if not (json or {}).get("token"):
            return _Respuesta({"features": [_item("2026-10-11", "B"), _item("2026-10-05", "A", nubes=85.0)],
                               "links": [{"rel": "next", "href": f"{s2.CATALOGO}/search", "method": "POST",
                                          "body": dict(json, token="pagina2")}]})
        return _Respuesta({"features": [_item("2026-10-01", "A"), _item("2026-10-11", "B")], "links": []})

    def get(self, url, timeout=None):        # pragma: no cover - no debe usarse
        raise AssertionError("se esperaba POST")


def test_buscar_paginado_y_nubes():
    s = _Sesion()
    out = s2.buscar((-66.0, -33.5, -65.5, -33.0), dt.date(2026, 9, 27), dt.date(2026, 11, 10), sesion=s)
    assert len(s.pedidos) == 2
    cuerpo = s.pedidos[0][2]
    assert cuerpo["collections"] == ["sentinel-2-l2a"] and cuerpo["bbox"] == [-66.0, -33.5, -65.5, -33.0]
    assert cuerpo["datetime"] == "2026-09-27T00:00:00Z/2026-11-10T23:59:59Z"
    assert s.pedidos[1][2]["token"] == "pagina2"
    # la escena con 85 % de nubes se descarta, la repetida aparece una vez, orden por fecha
    assert [it["id"] for it in out] == ["S2X_T20HA_20261001_0_L2A", "S2X_T20HB_20261011_0_L2A"]
    assert s2.resumen_escena(out[0]) == {"id": "S2X_T20HA_20261001_0_L2A", "fecha": "2026-10-01", "tesela": "20HA",
                                         "nubes_pct": 10.0, "linea_base": "05.11", "boa_offset_applied": True}


# =================================================================== meteorología
def _serie(horas: int = 48) -> pd.DataFrame:
    t = pd.date_range("2026-11-10 12:00", periods=horas, freq="1h", tz="UTC")
    i = np.arange(horas)
    return pd.DataFrame({"t": t, "temp": 20 + 5 * np.sin(i / 4), "hr": 40 + 10 * np.cos(i / 5), "vel": 5.0 + (i % 3),
                         "dir": (i * 15.0) % 360, "pp": np.where(i % 10 == 0, 0.4, 0.0)})


def _csv_v3(s: pd.DataFrame) -> bytes:
    return pd.DataFrame({"time_utc": [f"{x:%Y-%m-%d %H:%M:%S+00:00}" for x in s.t], "temperature_2m": s.temp,
                         "relative_humidity_2m": s.hr, "wind_speed_10m": s.vel, "wind_direction_10m": s.dir,
                         "precipitation": s.pp}).to_csv(index=False).encode()


def _csv_v4(s: pd.DataFrame, huso: bool = True) -> bytes:
    local = s.t.dt.tz_convert("-03:00")
    ts = [x.isoformat() if huso else f"{x:%Y-%m-%dT%H:%M:%S}" for x in local]
    return pd.DataFrame({"timestamp": ts, "temp_c": s.temp, "hr_pct": s.hr, "viento_kmh": s.vel * 3.6,
                         "viento_dir_deg": s.dir, "precip_mm": s.pp}).to_csv(index=False).encode()


def test_csv_manual_v3_y_v4_equivalentes():
    s = _serie()
    d3, f3 = meteo.leer_csv_manual(_csv_v3(s))
    d4, f4 = meteo.leer_csv_manual(_csv_v4(s))
    assert (f3, f4) == ("v3.x", "v4.0")
    assert list(d3.columns) == ["time_utc", "temperature_2m", "relative_humidity_2m", "wind_speed_10m", "wind_direction_10m",
                                "precipitation", "wind_speed_10m_vectorial", "u10", "v10", "n_puntos"]
    assert len(d3) == 48 and d3["time_utc"].iloc[0] == "2026-11-10 12:00:00+00:00"
    assert list(d4["time_utc"]) == list(d3["time_utc"])          # el huso −03:00 pasa a UTC
    for c in ["temperature_2m", "relative_humidity_2m", "wind_speed_10m", "wind_direction_10m", "precipitation", "u10", "v10"]:
        np.testing.assert_allclose(d4[c], d3[c], atol=1e-9, err_msg=c)
    np.testing.assert_allclose(d4["wind_speed_10m"], s.vel)      # km/h → m/s
    np.testing.assert_allclose(d3["wind_speed_10m_vectorial"], s.vel, atol=1e-9)
    # viento del oeste (270°) → u10 > 0, v10 ≈ 0
    i = int(np.flatnonzero(s.dir.to_numpy() == 270)[0])
    assert d3["u10"].iloc[i] > 0 and abs(d3["v10"].iloc[i]) < 1e-9


def test_csv_manual_hueco_de_dos_horas_se_rellena():
    s = _serie().drop(index=[10, 11]).reset_index(drop=True)
    d, _ = meteo.leer_csv_manual(_csv_v3(s))
    assert len(d) == 48 and d.notna().all().all()
    assert d["temperature_2m"].iloc[10] == pytest.approx((d["temperature_2m"].iloc[9] * 2 + d["temperature_2m"].iloc[12]) / 3)


@pytest.mark.parametrize("caso, mensaje", [
    ("columnas", "columnas no reconocidas"),
    ("sin_huso", "huso horario"),
    ("hueco", "falta más de 2 h"),
    ("fuera_de_rango", "relative_humidity_2m fuera de rango"),
    ("repetidas", "horas repetidas"),
    ("cortita", "menos de 24 horas"),
    ("no_en_punto", "en punto"),
])
def test_csv_manual_rechazos(caso, mensaje):
    s = _serie()
    if caso == "columnas":
        b = _csv_v3(s).replace(b"temperature_2m", b"temperatura")
    elif caso == "sin_huso":
        b = _csv_v4(s, huso=False)
    elif caso == "hueco":
        b = _csv_v3(s.drop(index=[10, 11, 12]))
    elif caso == "fuera_de_rango":
        s.loc[7, "hr"] = 120.0
        b = _csv_v3(s)
    elif caso == "repetidas":
        b = _csv_v3(pd.concat([s, s.iloc[[5]]]))
    elif caso == "cortita":
        b = _csv_v3(s.iloc[:23])
    else:
        s.loc[3:, "t"] = s.loc[3:, "t"] + pd.Timedelta(minutes=30)
        b = _csv_v3(s)
    with pytest.raises(ValueError, match=mensaje):
        meteo.leer_csv_manual(b)


def test_toma_manual_guarda_en_la_cache(cache):
    b = _csv_v4(_serie())
    info = meteo.toma_manual(b, "estacion.csv")
    d = cache / "meteo" / info["id"]
    assert info["formato"] == "v4.0" and info["horas"] == 48 and info["desde_utc"] == "2026-11-10T12:00:00Z"
    assert (d / "original_estacion.csv").read_bytes() == b
    assert info["sha256"] == comun.sha256(d / info["archivo"])
    assert [t["id"] for t in meteo.tomas()] == [info["id"]]


@pytest.mark.parametrize("horas", [0, 241, -5])
def test_escenario_horas_fuera_de_rango(cache, horas):
    with pytest.raises(ValueError, match="1 a 240"):
        meteo.toma_escenario("2026-11-13T15:00:00Z", horas, 30, 20, 36, 315)
    assert not (cache / "meteo").exists() or not any((cache / "meteo").iterdir())


def test_escenario_serie_constante_con_dias_previos(cache):
    info = meteo.toma_escenario("2026-11-13T15:20:00Z", 24, 31.5, 18, 36, 675, 0.0)
    d = pd.read_csv(cache / "meteo" / info["id"] / info["archivo"])
    assert info["inicio_escenario_utc"] == "2026-11-13T15:00:00Z"           # a la hora en punto
    assert info["desde_utc"] == "2026-11-08T15:00:00Z" and info["hasta_utc"] == "2026-11-14T16:00:00Z"
    assert len(d) == 5 * 24 + 24 + 2 == info["horas"]
    assert (d["temperature_2m"] == 31.5).all() and (d["relative_humidity_2m"] == 18).all()
    np.testing.assert_allclose(d["wind_speed_10m"], 10.0)                    # 36 km/h
    np.testing.assert_allclose(d["wind_direction_10m"], 315.0)               # 675 % 360
    assert (d["precipitation"] == 0).all() and info["valores"]["viento_dir_deg"] == 315.0
    assert info["dias_previos"] == 5


# =================================================================== índices cargados a mano
def _tif(ruta: Path, a: np.ndarray, crs: str | None = None, transform=None, dtype: str = "int16", nodata=ND) -> Path:
    import rasterio
    g = comun.grilla_dominio()
    with rasterio.open(ruta, "w", driver="GTiff", height=a.shape[0], width=a.shape[1], count=1, dtype=dtype,
                       crs=crs or g.crs, transform=transform or g.transform, nodata=nodata) as s:
        s.write(a.astype(dtype), 1)
    return ruta


def _indice(valor: int = 3000) -> np.ndarray:
    a = np.full(comun.grilla_dominio().forma, valor, "int16")
    a[:5, :5] = ND
    return a


def test_toma_manual_indices_aceptada(cache, tmp_path):
    ndvi = _tif(tmp_path / "ndvi.tif", _indice(4000))
    ndmi = _tif(tmp_path / "ndmi.tif", _indice(-1500))
    info = indices.toma_manual(ndvi, ndmi, ["2026-09-28", "2026-11-11"], "B8A", "ndvi.tif", "ndmi.tif", "prueba")
    d = cache / "indices" / info["id"]
    assert info["id"].startswith("I-20261111-manual-") and info["ndmi_nir"] == "B8A"
    assert info["ventana"] == ["2026-09-28", "2026-11-11"] and info["resolucion_m"] == 30
    a, perfil, tr, _ = _leer_tif(d / info["ndmi"])
    assert perfil["dtype"] == "int16" and perfil["nodata"] == ND and tr.almost_equals(comun.grilla_dominio().transform)
    assert a[0][0, 0] == ND and a[0][100, 100] == -1500
    assert info["sha256"]["ndvi"] == comun.sha256(d / info["ndvi"])
    assert info["celdas_sin_dato_pct"] == pytest.approx(100 * 25 / a[0].size, abs=1e-3)
    assert [t["id"] for t in indices.tomas()] == [info["id"]]


@pytest.mark.parametrize("caso, mensaje", [
    ("crs", "sistema de coordenadas"),
    ("forma", "celdas"),
    ("transformacion", "transformación"),
    ("float", "se espera int16"),
    ("nodata", "valor sin dato"),
    ("rango", "fuera de"),
    ("vacio", "ninguna celda"),
])
def test_leer_tif_manual_rechazos(tmp_path, caso, mensaje):
    from affine import Affine
    g = comun.grilla_dominio()
    a = _indice()
    ruta = tmp_path / f"{caso}.tif"
    if caso == "crs":
        _tif(ruta, a, crs="EPSG:32719")
    elif caso == "forma":
        _tif(ruta, a[:-1])
    elif caso == "transformacion":
        _tif(ruta, a, transform=Affine(g.res, 0, g.xmin + g.res, 0, -g.res, g.ymax))
    elif caso == "float":
        _tif(ruta, a / 10000.0, dtype="float32", nodata=ND)
    elif caso == "nodata":
        _tif(ruta, a, nodata=-9999)
    elif caso == "rango":
        a[100, 100] = 12000
        _tif(ruta, a)
    else:
        _tif(ruta, np.full(g.forma, ND, "int16"))
    with pytest.raises(ValueError, match=mensaje):
        indices.leer_tif_manual(ruta, ruta.name)


@pytest.mark.parametrize("ventana, nir, mensaje", [
    (["2026-09-28", "2026-11-11"], "B12", "ndmi_nir"),
    (["2026-11-11", "2026-09-28"], "B08", "anterior al primero"),
    (["2026-09-28"], "B08", "dos fechas"),
    (["ayer", "hoy"], "B08", "dos fechas"),
])
def test_toma_manual_indices_parametros_invalidos(cache, tmp_path, ventana, nir, mensaje):
    ruta = _tif(tmp_path / "i.tif", _indice())
    with pytest.raises(ValueError, match=mensaje):
        indices.toma_manual(ruta, ruta, ventana, nir, "i.tif", "i.tif")
    assert indices.tomas() == []


def test_ventana_de_tiempo_real():
    desde, hasta = indices.ventana_para(dt.date(2026, 11, 13))
    assert hasta == dt.date(2026, 11, 12) and desde == dt.date(2026, 9, 29)
    assert (hasta - desde).days + 1 == 45
    assert indices.ventana_para(dt.date(2026, 3, 1), 10) == (dt.date(2026, 2, 19), dt.date(2026, 2, 28))


# =================================================================== proceso de datos
def _correr(carpeta: Path, tarea: str, parametros: dict) -> tuple[int, list[dict]]:
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "pedido.json").write_text(json.dumps({"tarea": tarea, "parametros": parametros}), encoding="utf-8")
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    env.pop("PYTHONPATH", None)
    p = subprocess.run([sys.executable, str(PROCESO_DATOS), "--trabajo", str(carpeta)], capture_output=True, text=True,
                       encoding="utf-8", env=env, timeout=300, cwd=str(REPO))
    avisos = [json.loads(l) for l in p.stdout.splitlines() if l.strip()]       # solo avisos JSON por la salida estándar
    return p.returncode, avisos


def test_proceso_tarea_desconocida(tmp_path):
    codigo, avisos = _correr(tmp_path / "t", "inventada", {})
    assert codigo == 1
    assert avisos[-1]["aviso"] == "error" and "tarea desconocida" in avisos[-1]["mensaje"]
    assert avisos[-1]["clase"] == "ValueError"
    assert (tmp_path / "t" / "proceso.log").exists() and not (tmp_path / "t" / "resultado.json").exists()


def test_evento_rt_de_punta_a_punta_sin_red(tmp_path):
    """escenario → índices cargados a mano (Las Lagunas 2024 en int16) → evento RT; después lo borra todo."""
    import rasterio
    creados_meteo, creados_indices, id_evento = [], [], None
    previos_indices = {p.name for p in (REPO / "datos" / "procesados" / "app" / "indices").glob("*")}
    trabajos = tmp_path / "trabajos"
    try:
        # 1. meteorología: escenario fijo el 10/02/2025 a las 12 h locales
        codigo, av = _correr(trabajos / "esc", "escenario", {"desde_utc": "2025-02-10T15:00:00Z", "horas": 12, "temp_c": 32,
                                                            "hr_pct": 15, "viento_kmh": 30, "viento_dir_deg": 0})
        assert codigo == 0, av
        m = av[-1]["resultado"]
        creados_meteo.append(m["id"])
        assert av[-1]["aviso"] == "final" and "-escenario-" in m["id"]

        # 2. índices: los de Las Lagunas pasados a int16 × 10000, ventana de tiempo real del 10/02/2025
        dind = trabajos / "ind"
        dind.mkdir(parents=True)
        for k in ("ndvi", "ndmi"):
            with rasterio.open(LAGUNAS / f"{k}_30m_SL-2024-LASLAGUNAS.tif") as s:
                a = s.read(1)
                nd = s.nodata
            a = np.where((a == nd) | ~np.isfinite(a), ND, np.clip(np.round(a * 10000), -10000, 10000)).astype("int16")
            _tif(dind / f"{k}.tif", a)
        desde, hasta = indices.ventana_para(dt.date(2025, 2, 10))
        codigo, av = _correr(dind, "indices_manual", {"ndvi": "ndvi.tif", "ndmi": "ndmi.tif", "ventana": [f"{desde}", f"{hasta}"],
                                                     "ndmi_nir": "B08", "nombre_ndvi": "ndvi_lagunas.tif"})
        assert codigo == 0, av
        i = av[-1]["resultado"]
        if i["id"] not in previos_indices:
            creados_indices.append(i["id"])
        assert i["id"].startswith("I-20250209-manual-") and i["fuente"].startswith("TIF cargados a mano (ndvi_lagunas.tif, ndmi.tif)")

        # 3. evento
        codigo, av = _correr(trabajos / "ev", "evento", {"meteo": m["id"], "indices": i["id"], "nombre": "prueba F4"})
        assert codigo == 0, av
        assert all(x["aviso"] in ("progreso", "final") for x in av)
        ev = av[-1]["resultado"]
        id_evento = ev["id"]
        assert id_evento.startswith("RT-20250210-") and evento_rt.es_rt(id_evento)
        r = evento_rt.rutas(id_evento)
        assert r["ficha_v31"].read_text(encoding="utf-8") == r["ficha_v40"].read_text(encoding="utf-8")
        import yaml
        f = yaml.safe_load(r["ficha_v40"].read_text(encoding="utf-8"))
        assert f["id"] == id_evento and f["nombre"] == "prueba F4" and f["tipo"] == "tiempo_real"
        assert f["inicio"]["hora_utc_hipotesis"] == ["2025-02-10T15:00:00Z"] and f["cobertura_anio"] == 2024
        assert f["meteorologia"]["toma"] == m["id"] and f["indices"]["toma"] == i["id"]
        meteo_csv = list(r["meteo_dir"].glob(f"{id_evento}_*_dominio.csv"))
        assert len(meteo_csv) == 1 and len(pd.read_csv(meteo_csv[0])) == m["horas"]
        for k in ("clase", "curado", "calidad"):
            assert (r["combustibles"] / f"combustible_{k}_{id_evento}.tif").exists(), k
        for k in ("ndvi", "ndmi"):
            assert (r["combustibles"] / f"{k}_30m_{id_evento}.tif").exists(), k
        assert (r["eventos"] / f"humedad_muerto_{id_evento}.csv").exists()
        insumos = json.loads(r["insumos"].read_text(encoding="utf-8"))
        assert insumos["id"] == id_evento and insumos["meteo"]["id"] == m["id"] and insumos["indices"]["id"] == i["id"]
        assert insumos["t_inicio_por_defecto_utc"] == "2025-02-10T15:00:00Z"
        for k, rel in insumos["archivos"].items():
            assert insumos["sha256"][k] == comun.sha256(REPO / rel), k
        # febrero: el verano de v4.0 es enero a marzo del año anterior, que está en las entradas
        assert insumos["verano_v40"]["archivos"] == [f"NDVI_NDMI_2024_{x:02d}.tif" for x in (1, 2, 3)]
        assert insumos["verano_v40"]["faltan"] == [] and insumos["cobertura_anio"] == 2024
        assert id_evento in {e["id"] for e in evento_rt.eventos()}

        # 4. las versiones congeladas siguen intactas (los RT-* se ignoran)
        c = subprocess.run([sys.executable, str(REPO / "herramientas" / "congelado.py"), "verificar"], capture_output=True,
                           text=True, cwd=str(REPO))
        assert c.returncode == 0, c.stdout
    finally:
        if id_evento:
            evento_rt.borrar(id_evento)
        for x in creados_meteo:
            shutil.rmtree(REPO / "datos" / "procesados" / "app" / "meteo" / x, ignore_errors=True)
        for x in creados_indices:
            shutil.rmtree(REPO / "datos" / "procesados" / "app" / "indices" / x, ignore_errors=True)
    r = evento_rt.rutas(id_evento)
    assert not r["ficha_v31"].exists() and not r["ficha_v40"].exists() and not r["combustibles"].exists()
    assert not r["eventos"].exists() and not list(r["meteo_dir"].glob(f"{id_evento}_*"))
