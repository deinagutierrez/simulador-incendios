"""Cortafuegos y viento manual en el motor v4.0 (fase F5, contrato 1.5; decisión D-E3-28, puntos 4-6, 11-14 y 16).

Lo usa `motor_v40.py`. No cambia ningún archivo de src/v4.0: todo pasa por las funciones del propio motor
(`simulador.io.capas.rasterizar_barreras_extra`, `simulador.io.meteo.SerieMeteo`, `simulador.physics.humedad`) y por el
recálculo, en las celdas tocadas, de las tablas que `Automata.__init__` deriva de las capas (automata.py:194-205).
Los módulos de v4.0 se importan dentro de cada función: este archivo se carga con el motor ya en `sys.path`.

Cortafuegos antes de iniciar (punto 12), por la vía que ya tiene el motor (`Intervenciones.preparar_iniciales`):
- `cortafuegos.geojson` (EPSG:5345, `ancho_m`, `tipo: cortafuego`) va como `mitigacion.barreras_extra`;
- si hay trazos a suelo mineral, `modificador_cortafuegos.tif` (0 en las celdas que toca el trazo, 1 en el resto,
  nodata = 1, en la grilla base del dominio) va como `mitigacion.modificador_combustible`;
- si la definición ya traía alguno de los dos, se combinan (sus geometrías y su modificador siguen valiendo).
Sin trazos no se llama: la definición queda igual (identidad E-E3-1).

Cortafuego en pausa (`Intervenciones.aplicar`):
- máscara del trazo = celdas que toca `rasterizar_barreras_extra` (all_touched) sobre una grilla vacía;
- recorte (punto 13): se quitan las celdas ya afectadas (con tiempo de llegada) y las que son intermedias de un enlace
  entre dos celdas afectadas (ese enlace ya se sorteó contra la barrera antes de la pausa en la corrida offline). Con
  vecindad 8 son las celdas no afectadas con una vecina afectada al N o al S y otra al E o al O;
- geometría reproducible: la polilínea menos los cuadrados de las celdas quitadas (con 1 cm de margen) si se rasteriza
  exactamente en la máscara final; si no, los centros de las celdas de la máscara final (MultiPoint). Es la que se aplica en
  memoria y la que se guarda para la corrida offline, así que las dos rasterizan lo mismo por construcción;
- suelo mineral: `capas.modificador` = 0 en la máscara final (y factor de carga 0, no combustible). Con vecindad 16 se
  rechaza: el motor revisa las intermedias de los saltos de caballo solo al activar cada celda, así que una celda que pasa
  a no combustible en pausa no corta los saltos de las celdas que ya estaban activas (no sería reproducible offline).
- `datos` que se suman a la bitácora: `longitud_aplicada_m` (la de la polilínea recortada, dentro de la grilla),
  `celdas`, `celdas_recortadas`, `celdas_sha256` (índices planos en la grilla de la simulación) y `geometria_offline`
  (`polilinea` | `centros`).

Viento manual (puntos 5 y 16): se reemplaza la serie (`SerieMeteo`, que deriva u y v al construirse) con las filas
posteriores a la pausa editadas; el motor interpola entre filas, así que el viento gira durante la hora siguiente
(`pleno_min` = t + 60). Con humedad `ffmc_vanwagner` (que usa el viento) se recalcula la serie de humedad muerta. "Volver al
pronóstico" restaura esas filas desde la serie original. Con un campo de viento externo (u/v horarios de WindNinja) se
rechaza: ese campo no usa la serie.

Para la corrida offline (comparación B de E-E3-4) quedan en la carpeta de la corrida, y se reescriben tras cada intervención:
- `cortafuegos_aplicados.geojson`: las barreras extra con que arrancó la corrida (los trazos iniciales) más las geometrías
  reproducibles de los trazos en pausa, con `ancho_m` → `mitigacion.barreras_extra`;
- `modificador_aplicado.tif` (si hubo suelo mineral en pausa o antes de iniciar): el modificador con que arrancó la corrida
  con 0 en las celdas a suelo mineral → `mitigacion.modificador_combustible`;
- `meteo_editada.csv` (si hubo viento manual): la serie completa como la usa el motor, con -03:00 → `parche.meteo` (con ruta
  absoluta: una relativa se busca en la carpeta del YAML).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import intervenciones as iv

MARGEN_M = 0.01                     # margen de los cuadrados que se restan a la polilínea recortada
HUSO_CSV = dt.timezone(dt.timedelta(hours=-3))      # las series de v4.0 se escriben con -03:00
COLUMNAS_METEO = ["timestamp", "temp_c", "hr_pct", "viento_kmh", "viento_dir_deg", "precip_mm", "fuente"]
FUENTE_MANUAL = "viento manual (simulador interactivo)"
CORTAFUEGOS_INICIALES = "cortafuegos.geojson"
MODIFICADOR_INICIAL = "modificador_cortafuegos.tif"
CORTAFUEGOS_OFFLINE = "cortafuegos_aplicados.geojson"
MODIFICADOR_OFFLINE = "modificador_aplicado.tif"
METEO_OFFLINE = "meteo_editada.csv"


# ------------------------------------------------------------------------------------------------ geometría y grilla
def _urn(crs) -> str:
    from pyproj import CRS
    epsg = CRS.from_user_input(crs).to_epsg()
    return f"urn:ogc:def:crs:EPSG::{epsg}" if epsg else str(crs)


def mismo_crs(a, b) -> bool:
    from pyproj import CRS
    return CRS.from_user_input(a) == CRS.from_user_input(b)


def linea_en_grilla(xy_5345, crs_grilla):
    """LineString del trazo (EPSG:5345) en el CRS de la grilla."""
    from shapely.geometry import LineString
    linea = LineString([(float(x), float(y)) for x, y in xy_5345])
    if mismo_crs("EPSG:5345", crs_grilla):
        return linea
    from pyproj import Transformer
    from shapely.ops import transform
    return transform(Transformer.from_crs("EPSG:5345", crs_grilla, always_xy=True).transform, linea)


def _gdf(geoms, anchos, crs):
    import geopandas as gpd
    return gpd.GeoDataFrame({"ancho_m": [float(a) for a in anchos], "tipo": ["cortafuego"] * len(geoms)},
                            geometry=list(geoms), crs=crs)


def rasterizar(grilla, geoms, anchos) -> np.ndarray:
    """Anchos (m, float32) que deja `rasterizar_barreras_extra` de v4.0 sobre una grilla sin caminos."""
    from simulador.io.capas import rasterizar_barreras_extra
    vacia = SimpleNamespace(grilla=grilla, camino_ancho=np.zeros(grilla.shape, "float32"),
                            camino_tipo=np.full(grilla.shape, -1, "int8"), barreras_gdf=None, fuentes={})
    rasterizar_barreras_extra(vacia, _gdf(geoms, anchos, grilla.crs))
    return vacia.camino_ancho


def _desplazar(a: np.ndarray, df: int, dc: int) -> np.ndarray:
    """out[i, j] = a[i + df, j + dc] (False fuera)."""
    out = np.zeros_like(a)
    H, W = a.shape
    i0, i1, j0, j1 = max(0, -df), min(H, H - df), max(0, -dc), min(W, W - dc)
    if i0 < i1 and j0 < j1:
        out[i0:i1, j0:j1] = a[i0 + df:i1 + df, j0 + dc:j1 + dc]
    return out


def recortar(mascara: np.ndarray, afectada: np.ndarray, df, dc, inter) -> np.ndarray:
    """Máscara final del trazo en pausa: sin las celdas afectadas ni las intermedias de enlaces entre dos afectadas.

    `df`, `dc`, `inter`: los desplazamientos de la vecindad y las intermedias de cada enlace del autómata
    (`Automata.df`, `.dc`, `.inter`). Se calcula en una ventana alrededor del trazo (las intermedias están a 2 celdas como
    mucho de los extremos del enlace)."""
    if not mascara.any():
        return mascara.copy()
    ff, cc = np.nonzero(mascara)
    m = 3
    r0, r1 = max(0, ff.min() - m), min(mascara.shape[0], ff.max() + m + 1)
    c0, c1 = max(0, cc.min() - m), min(mascara.shape[1], cc.max() + m + 1)
    af = afectada[r0:r1, c0:c1]
    intermedia = np.zeros_like(af)
    for k, pares in enumerate(inter):
        for a, b in pares:              # X = E + (a, b), con E y R = E + (df, dc) afectadas
            intermedia |= _desplazar(af, -a, -b) & _desplazar(af, int(df[k]) - a, int(dc[k]) - b)
    final = mascara.copy()
    final[r0:r1, c0:c1] &= ~af & ~intermedia
    return final


def _cuadrados(grilla, filas, cols):
    from shapely.geometry import box
    from shapely.ops import unary_union
    r = grilla.res
    return unary_union([box(grilla.xmin + c * r, grilla.ymax - (f + 1) * r, grilla.xmin + (c + 1) * r, grilla.ymax - f * r)
                        for f, c in zip(filas, cols)])


def centros(grilla, mascara: np.ndarray):
    from shapely.geometry import MultiPoint
    ff, cc = np.nonzero(mascara)
    r = grilla.res
    return MultiPoint([(grilla.xmin + (c + 0.5) * r, grilla.ymax - (f + 0.5) * r) for f, c in zip(ff, cc)])


def geometria_reproducible(linea, quitadas: np.ndarray, final: np.ndarray, grilla, ancho: float):
    """(geometría, "polilinea"|"centros", longitud aplicada en m). La geometría rasteriza exactamente en `final`
    (se comprueba en los dos casos)."""
    from shapely.geometry import box
    caja = box(*grilla.bounds)
    if quitadas.any():
        ff, cc = np.nonzero(quitadas)
        recortada = linea.difference(_cuadrados(grilla, ff, cc).buffer(MARGEN_M))
    else:
        recortada = linea
    largo = round(float(recortada.intersection(caja).length), 2)
    if not recortada.is_empty and np.array_equal(rasterizar(grilla, [recortada], [ancho]) > 0, final):
        return recortada, "polilinea", largo
    puntos = centros(grilla, final)
    if not np.array_equal(rasterizar(grilla, [puntos], [ancho]) > 0, final):
        raise RuntimeError("los centros de las celdas del trazo no se rasterizan en las mismas celdas")
    return puntos, "centros", largo


def indices(mascara: np.ndarray) -> np.ndarray:
    return np.flatnonzero(mascara.ravel()).astype("int64")


# ------------------------------------------------------------------------------------------------ autómata
def actualizar_derivadas(au, ancho_antes: np.ndarray, tipo_antes: np.ndarray, mineral: np.ndarray | None = None) -> np.ndarray:
    """Recalcula en las celdas tocadas lo que `Automata.__init__` deriva de las capas (automata.py:194-205), con las mismas
    operaciones y el mismo orden (así da los mismos float32): `factor_carga`, `estado` (solo celdas COMBUSTIBLE),
    `es_camino` y `umbral_camino`. Con `mineral`, antes pone `capas.modificador` = 0 en esas celdas. Devuelve la máscara
    de celdas tocadas."""
    from simulador.ca import estados as E
    from simulador.io.capas import TIPOS_CAMINO
    capas = au.capas
    tocadas = (capas.camino_ancho != ancho_antes) | (capas.camino_tipo != tipo_antes)
    if mineral is not None and mineral.any():
        if capas.modificador is None:
            capas.modificador = np.ones(capas.grilla.shape, "float32")
        capas.modificador[mineral] = 0.0
        tocadas |= mineral
    f, c = np.nonzero(tocadas)
    if not len(f):
        return tocadas
    pc = au.cfg["parametros"]["caminos"]
    comb = (au.idx_modelo[f, c] >= 0) & au.tabla.combustible[np.clip(au.idx_modelo[f, c], 0, None)]
    fc = np.ones(len(f), "float32")
    if pc.get("factor_carga_por_ancho", True):
        fc *= np.clip(1.0 - capas.camino_ancho[f, c] / au.res, 0.0, 1.0)
    if capas.modificador is not None:
        fc *= capas.modificador[f, c]
    au.factor_carga[f, c] = fc
    libre = au.estado[f, c] == E.COMBUSTIBLE
    sin = libre & comb & ((capas.camino_ancho[f, c] >= au.res) | (fc <= 0))
    au.estado[f[sin], c[sin]] = E.NO_COMBUSTIBLE
    au.es_camino[f, c] = capas.camino_ancho[f, c] > 0
    for i, t in enumerate(TIPOS_CAMINO):
        m = capas.camino_tipo[f, c] == i
        au.umbral_camino[f[m], c[m]] = pc["umbral_llama_m"].get(t, 1.0)
    return tocadas


# ------------------------------------------------------------------------------------------------ archivos
def _reemplazar(ruta: Path, escribir) -> None:
    """Escribe en un temporal y lo pone en su lugar (nunca queda un archivo a medias)."""
    ruta = Path(ruta)
    tmp = ruta.with_name(ruta.name + ".tmp")
    try:
        escribir(tmp)
        os.replace(tmp, ruta)
    finally:
        if tmp.exists():
            tmp.unlink()


def escribir_geojson(ruta: Path, elementos: list[dict], crs) -> None:
    """FeatureCollection con `elementos` = [{"geometria": shapely, **propiedades}] (coordenadas sin redondear: JSON escribe
    cada float de forma que se lee igual)."""
    from shapely.geometry import mapping
    fc = {"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": _urn(crs)}},
          "features": [{"type": "Feature", "properties": {k: v for k, v in e.items() if k != "geometria"},
                        "geometry": mapping(e["geometria"])} for e in elementos]}

    def escribir(tmp):
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(fc, f, ensure_ascii=False, indent=1)
    _reemplazar(ruta, escribir)


def leer_barreras(ruta: Path, crs) -> list[dict]:
    """Elementos (`geometria` + `ancho_m`, `tipo` y el resto de las propiedades) de un archivo de barreras extra, en `crs`."""
    import geopandas as gpd
    gdf = gpd.read_file(ruta)
    if gdf.crs is not None and not mismo_crs(gdf.crs, crs):
        gdf = gdf.to_crs(crs)
    props = [c for c in gdf.columns if c != gdf.geometry.name]
    out = []
    for i in range(len(gdf)):
        e = {"geometria": gdf.geometry.iloc[i]}
        for c in props:
            v = gdf[c].iloc[i]
            if hasattr(v, "item"):
                v = v.item()
            if isinstance(v, float) and not np.isfinite(v):
                v = None
            e[c] = v
        out.append(e)
    return out


def leer_modificador(ruta: Path | None, base) -> np.ndarray:
    """Modificador en la grilla base, float32, con el nodata como 1 (lo mismo que hace `cargar_capas`); unos sin `ruta`."""
    if not ruta:
        return np.ones(base.shape, "float32")
    import rasterio
    with rasterio.open(ruta) as src:
        base.verificar_raster(src, "modificador_combustible")
        a = src.read(1).astype("float32")
        if src.nodata is not None:
            a = np.where(a == src.nodata, 1.0, a).astype("float32")
    return a


def escribir_modificador(ruta: Path, base, a: np.ndarray) -> None:
    """GeoTIFF float32 en la grilla `base` del dominio (la que exige `modificador_combustible`), nodata = 1 (v4.0 lee el
    nodata como 1, así que da lo mismo)."""
    import rasterio
    a = np.asarray(a, "float32")

    def escribir(tmp):
        with rasterio.open(tmp, "w", driver="GTiff", height=base.alto, width=base.ancho, count=1, dtype="float32",
                           crs=base.crs, transform=base.transform, nodata=1.0, compress="deflate") as dst:
            dst.write(a, 1)
    _reemplazar(ruta, escribir)


def a_indices_base(capas, mascara: np.ndarray) -> np.ndarray:
    """Índices planos en la grilla base del dominio de las celdas de `mascara` (en la grilla de la ventana)."""
    ff, cc = np.nonzero(mascara)
    v = capas.ventana
    if v is not None:
        ff = ff + int(v.row_off)
        cc = cc + int(v.col_off)
    return (ff.astype("int64") * int(capas.base.ancho) + cc).astype("int64")


def escribir_meteo(ruta: Path, df) -> None:
    """La serie con el formato de v4.0 (timestamp con -03:00, columnas del estándar), fin de línea \\n en todo sistema."""
    import pandas as pd
    x = df.copy()
    ts = pd.to_datetime(x["timestamp"], utc=True).dt.tz_convert(HUSO_CSV)
    x["timestamp"] = ts.dt.strftime("%Y-%m-%dT%H:%M:%S") + "-03:00"
    columnas = [c for c in COLUMNAS_METEO if c in x.columns] + [c for c in x.columns if c not in COLUMNAS_METEO]

    def escribir(tmp):
        x[columnas].to_csv(tmp, index=False, lineterminator="\n")
    _reemplazar(ruta, escribir)


# ------------------------------------------------------------------------------------------------ viento
def editar_serie(df_actual, df_original, t_pausa, datos: dict):
    """(df editado, filas editadas). Cambia las filas con timestamp > t_pausa: viento manual o las del pronóstico."""
    import pandas as pd
    df = df_actual.copy()
    for c in ("viento_kmh", "viento_dir_deg"):
        df[c] = df[c].astype("float64")
    m = (pd.to_datetime(df["timestamp"], utc=True) > pd.Timestamp(t_pausa).tz_convert("UTC")).to_numpy()
    if datos.get("modo") == "pronostico":
        if len(df_original) != len(df) or not (pd.to_datetime(df_original["timestamp"], utc=True).to_numpy()
                                               == pd.to_datetime(df["timestamp"], utc=True).to_numpy()).all():
            raise ValueError("la serie original y la editada no tienen las mismas filas")
        for c in df.columns:
            if c in df_original.columns and c != "timestamp":
                numericas = pd.api.types.is_numeric_dtype(df[c]) and pd.api.types.is_numeric_dtype(df_original[c])
                if not numericas:
                    df[c] = df[c].astype(object)
                df.loc[m, c] = df_original[c].to_numpy()[m]
    else:
        df.loc[m, "viento_kmh"] = float(datos["vel_kmh"])
        df.loc[m, "viento_dir_deg"] = float(datos["dir_desde"])
        if "fuente" in df.columns:
            df["fuente"] = df["fuente"].astype(object)
            df.loc[m, "fuente"] = FUENTE_MANUAL
    return df, int(m.sum())


# ------------------------------------------------------------------------------------------------ conductor
def _rechazada(t: float, motivo: str) -> dict:
    return {"estado": "rechazada", "t_vigor_min": float(t), "motivo": motivo, "datos": {}}


class Intervenciones:
    """Cortafuegos (antes de iniciar y en pausa) y viento manual de una corrida v4.0.

    `motor_v40.py` pone `au` (el autómata, al crearse) y `control.aplicar = interv.aplicar`; antes de cargar el escenario
    llama a `preparar_iniciales` si hay trazos, y al final suma `informe()` a los resultados."""

    def __init__(self, carpeta: Path, iniciales: list[dict]):
        self.carpeta = Path(carpeta)
        self.iniciales = [dict(d) for d in iniciales or []]
        self.au = None
        self.en_pausa: list[dict] = []          # trazos aplicados en pausa: geometría reproducible y propiedades
        self.mineral_pausa: list[np.ndarray] = []   # índices (grilla base) que pasaron a suelo mineral en pausa
        self.serie_original = None
        self.viento_editado = False
        self.archivos_offline: dict[str, str] = {}

    # -------------------------------------------------------------------------------------------- antes de iniciar
    def preparar_iniciales(self, definicion: dict, raiz_datos: Path, dir_yaml: Path | None = None) -> dict:
        """Escribe `cortafuegos.geojson` (y `modificador_cortafuegos.tif` si hay suelo mineral) y devuelve la definición con
        `mitigacion.barreras_extra` / `modificador_combustible` (rutas absolutas). Combina lo que la definición ya traía."""
        from shapely.geometry import LineString
        from simulador.io.manifiesto import Manifiesto
        from incendios_sl import escenario
        d = dict(definicion)
        mit = dict(d.get("mitigacion") or {})
        bases = [b for b in (dir_yaml, self.carpeta) if b]
        elementos = []
        if mit.get("barreras_extra"):
            elementos += leer_barreras(escenario.resolver_ruta(mit["barreras_extra"], *bases), "EPSG:5345")
        for i, c in enumerate(self.iniciales):
            elementos.append({"geometria": LineString([tuple(p) for p in c["xy_5345"]]), "ancho_m": float(c["ancho_m"]),
                              "tipo": "cortafuego", "suelo_mineral": bool(c.get("suelo_mineral")), "i": i + 1})
        ruta = self.carpeta / CORTAFUEGOS_INICIALES
        escribir_geojson(ruta, elementos, "EPSG:5345")
        mit["barreras_extra"] = str(ruta.resolve())
        minerales = [c for c in self.iniciales if c.get("suelo_mineral")]
        if minerales:
            base = Manifiesto.cargar(Path(raiz_datos) / "manifiesto_datos.yaml").grilla
            previo = escenario.resolver_ruta(mit["modificador_combustible"], *bases) if mit.get("modificador_combustible") else None
            a = leer_modificador(previo, base)
            lineas = [linea_en_grilla(c["xy_5345"], base.crs) for c in minerales]
            a[rasterizar(base, lineas, [c["ancho_m"] for c in minerales]) > 0] = 0.0
            ruta_mod = self.carpeta / MODIFICADOR_INICIAL
            escribir_modificador(ruta_mod, base, a)
            mit["modificador_combustible"] = str(ruta_mod.resolve())
        d["mitigacion"] = mit
        return d

    # -------------------------------------------------------------------------------------------- en pausa
    def aplicar(self, entrada: dict, t: float) -> dict:
        if self.au is None:
            return _rechazada(t, "el motor todavía no creó el autómata")
        t0 = time.perf_counter()
        if entrada["tipo"] == "cortafuego":
            r = self._cortafuego(entrada["datos"], float(t))
        else:
            r = self._viento(entrada["datos"], float(t))
        print(f"intervención {entrada['tipo']} en t = {float(t):g} min: {r['estado']}, {r['motivo']} "
              f"({time.perf_counter() - t0:.2f} s)", flush=True)
        return r

    def _cortafuego(self, d: dict, t: float) -> dict:
        from shapely.geometry import box
        from simulador.io.capas import rasterizar_barreras_extra
        au = self.au
        capas = au.capas
        g = capas.grilla
        ancho = float(d["ancho_m"])
        mineral = bool(d.get("suelo_mineral"))
        if mineral and au.K > 8:
            return _rechazada(t, "a suelo mineral no se aplica en pausa con vecindad 16: el motor revisa los saltos de caballo "
                                 "solo al encender cada celda y no sería reproducible desde el inicio")
        linea = linea_en_grilla(d["xy_5345"], g.crs)
        mascara = rasterizar(g, [linea], [ancho]) > 0
        if not mascara.any():
            return _rechazada(t, "el trazo no toca la zona que se simula")
        final = recortar(mascara, np.isfinite(au.t_llegada), au.df, au.dc, au.inter)
        quitadas = mascara & ~final
        if not final.any():
            return _rechazada(t, "todo el trazo cae sobre celdas que el fuego ya alcanzó")
        geom, forma, largo = geometria_reproducible(linea, quitadas, final, g, ancho)
        fuera = float(linea.length) - float(linea.intersection(box(*g.bounds)).length) > 0.005

        # copia de lo que se toca, para dejar el motor como estaba si algo falla
        copia = {"camino_ancho": capas.camino_ancho.copy(), "camino_tipo": capas.camino_tipo.copy(),
                 "modificador": None if capas.modificador is None else capas.modificador.copy(),
                 "barreras_gdf": capas.barreras_gdf}
        copia_au = {k: getattr(au, k).copy() for k in ("factor_carga", "estado", "es_camino", "umbral_camino")}
        n_pausa, n_mineral = len(self.en_pausa), len(self.mineral_pausa)
        try:
            previas = capas.barreras_gdf
            rasterizar_barreras_extra(capas, _gdf([geom], [ancho], g.crs))
            if previas is not None and len(previas):
                import pandas as pd
                capas.barreras_gdf = pd.concat([previas, capas.barreras_gdf], ignore_index=True)
            actualizar_derivadas(au, copia["camino_ancho"], copia["camino_tipo"], final if mineral else None)
            self.en_pausa.append({"geometria": geom, "ancho_m": ancho, "tipo": "cortafuego", "origen": "pausa",
                                  "t_sim_min": round(t, 3), "suelo_mineral": mineral, "geometria_offline": forma})
            if mineral:
                self.mineral_pausa.append(a_indices_base(capas, final))
            self.guardar_offline()
        except BaseException:
            for k in ("camino_ancho", "camino_tipo"):
                getattr(capas, k)[...] = copia[k]
            capas.modificador = copia["modificador"]
            capas.barreras_gdf = copia["barreras_gdf"]
            for k, v in copia_au.items():
                getattr(au, k)[...] = v
            del self.en_pausa[n_pausa:]
            del self.mineral_pausa[n_mineral:]
            raise
        recortes = []
        if quitadas.any():
            recortes.append(f"{int(quitadas.sum())} celdas ya alcanzadas por el fuego o entre celdas alcanzadas")
        if fuera:
            recortes.append("una parte queda fuera de la zona simulada")
        motivo = f"{int(final.sum())} celdas, {largo:.2f} m aplicados"
        if mineral:
            motivo += ", a suelo mineral (supuesto)"
        if recortes:
            motivo += "; se quitaron: " + "; ".join(recortes)
        datos = {"longitud_aplicada_m": largo, "celdas": int(final.sum()), "celdas_recortadas": int(quitadas.sum()),
                 "celdas_sha256": iv.sha256_indices(indices(final)), "geometria_offline": forma}
        return {"estado": "recortada" if recortes else "aceptada", "t_vigor_min": t, "motivo": motivo, "datos": datos}

    def _viento(self, d: dict, t: float) -> dict:
        import pandas as pd
        from simulador.io.meteo import SerieMeteo
        from simulador.physics.humedad import serie_humedad_muerta
        au = self.au
        if getattr(au.viento, "externo", None) is not None:
            return _rechazada(t, "la corrida usa un campo de viento externo (WindNinja, u/v por hora), que no lee la serie "
                                 "meteorológica: el viento manual no se puede aplicar")
        actual = au.meteo
        if self.serie_original is None:
            self.serie_original = actual.df.copy()
        t_pausa = au.t0 + pd.Timedelta(minutes=t)
        df, n = editar_serie(actual.df, self.serie_original, t_pausa, d)
        if n == 0:
            return _rechazada(t, "la serie meteorológica no tiene horas después de la pausa")
        nueva = SerieMeteo(df, actual.fuente_archivo)
        hum = None
        if au.hum is not None and au.p_hum.metodo_muerto == "ffmc_vanwagner":
            hum = serie_humedad_muerta(nueva.horas(nueva.inicio, au.hum["timestamp"].iloc[-1]), au.p_hum)
        escribir_meteo(self.carpeta / METEO_OFFLINE, nueva.df)
        self.archivos_offline["meteo"] = METEO_OFFLINE
        self.viento_editado = True
        au.meteo = nueva
        if hum is not None:
            au.hum = hum
            au.hum_t = hum["timestamp"].values.astype("datetime64[s]").astype("int64")
        desde = nueva.df["timestamp"][nueva.df["timestamp"] > t_pausa.tz_convert("UTC")].iloc[0]
        datos = {"filas_editadas": n, "desde_utc": desde.strftime("%Y-%m-%dT%H:%M:%SZ")}
        if d.get("modo") == "pronostico":
            motivo = f"vuelve al pronóstico desde la fila de {datos['desde_utc']}; gira durante la hora siguiente"
        else:
            motivo = (f"{d['vel_kmh']:g} km/h desde {d['dir_desde']:g}° desde la fila de {datos['desde_utc']}; gira durante la "
                      "hora siguiente")
        return {"estado": "aceptada", "t_vigor_min": t, "pleno_min": t + 60.0, "motivo": motivo, "datos": datos}

    # -------------------------------------------------------------------------------------------- para la corrida offline
    def guardar_offline(self) -> None:
        """Reescribe los archivos de la corrida offline (comparación B de E-E3-4) con todo lo aplicado hasta ahora."""
        au = self.au
        if au is None:
            return
        capas = au.capas
        crs = capas.grilla.crs
        fuente = capas.fuentes.get("barreras_extra")
        if self.en_pausa or fuente:
            elementos = leer_barreras(Path(fuente), crs) if fuente else []
            for e in elementos:
                e.setdefault("origen", "inicial")
            escribir_geojson(self.carpeta / CORTAFUEGOS_OFFLINE, elementos + self.en_pausa, crs)
            self.archivos_offline["barreras_extra"] = CORTAFUEGOS_OFFLINE
        if self.mineral_pausa or capas.fuentes.get("modificador"):
            a = leer_modificador(capas.fuentes.get("modificador"), capas.base)
            for idx in self.mineral_pausa:
                a.ravel()[idx] = 0.0
            escribir_modificador(self.carpeta / MODIFICADOR_OFFLINE, capas.base, a)
            self.archivos_offline["modificador_combustible"] = MODIFICADOR_OFFLINE

    def informe(self) -> dict:
        """Lo que se suma a `resultados`: `cortafuegos_iniciales` (uno por trazo de `configuracion.cortafuegos`, con lo que
        tocó en la grilla de la simulación) y `archivos_offline` (nombres dentro de la carpeta de la corrida)."""
        out: dict = {}
        if self.au is not None:
            try:
                self.guardar_offline()
            except Exception as e:                  # no se pierde la corrida por los archivos de la comparación offline
                out["archivos_offline_error"] = f"{type(e).__name__}: {e}"
        if self.iniciales:
            out["cortafuegos_iniciales"] = [self._informe_inicial(c) for c in self.iniciales]
        if self.archivos_offline:
            out["archivos_offline"] = dict(sorted(self.archivos_offline.items()))
        return out

    def _informe_inicial(self, c: dict) -> dict:
        r = {"estado": "aceptada", "motivo": "aplicado antes de iniciar", **c}
        if self.au is None:
            return r
        from shapely.geometry import box
        g = self.au.capas.grilla
        linea = linea_en_grilla(c["xy_5345"], g.crs)
        m = rasterizar(g, [linea], [c["ancho_m"]]) > 0
        dentro = float(linea.intersection(box(*g.bounds)).length)
        if not m.any():
            r |= {"estado": "rechazada", "motivo": "el trazo no toca la zona que se simula"}
        elif float(linea.length) - dentro > 0.005:
            r |= {"estado": "recortada", "motivo": "aplicado antes de iniciar; una parte queda fuera de la zona simulada"}
        return r | {"longitud_aplicada_m": round(dentro, 2), "celdas": int(m.sum()),
                    "celdas_sha256": iv.sha256_indices(indices(m))}
