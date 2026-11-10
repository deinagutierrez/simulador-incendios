"""Carga de capas estáticas y dinámicas en una ventana de la grilla de trabajo."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import rasterio
from rasterio import features

from .grilla import Grilla, ErrorGrilla
from .manifiesto import Manifiesto, ErrorManifiesto

ANCHO_POR_TIPO = {"pavimentado": 8.0, "ripio": 7.0, "tierra": 5.0, "huella": 3.0, "cortafuego": 10.0}
# índice de `camino_tipo` = posición en esta lista; `cortafuego` (4) = barreras extra (parametros.barreras.extra)
TIPOS_CAMINO = list(ANCHO_POR_TIPO)


@dataclass
class Capas:
    grilla: Grilla                    # grilla de la ventana
    base: Grilla                      # grilla completa del dominio
    ventana: object                   # rasterio Window (None = dominio completo)
    mdt: np.ndarray
    nodata_mdt: float
    pendiente: np.ndarray             # grados, float32
    orientacion: np.ndarray           # grados, float32 (361 = plano)
    plano: np.ndarray                 # bool
    combustible: np.ndarray           # códigos FBFM40 int16
    nodata_combustible: int
    # infraestructura rasterizada
    camino_ancho: np.ndarray          # m, 0 donde no hay camino (float32)
    camino_tipo: np.ndarray           # índice del tipo (-1 sin camino)
    vivienda: np.ndarray              # bool
    linea_mt: np.ndarray              # bool (celda con tendido)
    # vectores (GeoDataFrames en EPSG del dominio, recortados a la ventana)
    caminos_gdf: object = None
    viviendas_gdf: object = None
    red_gdf: object = None
    # dinámicas (opcionales)
    ndvi_mes: np.ndarray | None = None
    ndmi_mes: np.ndarray | None = None
    ndvi_verano: np.ndarray | None = None
    modificador: np.ndarray | None = None     # factor multiplicativo de carga (mitigación futura)
    fuentes: dict = field(default_factory=dict)
    barreras_gdf: object = None               # barreras extra (líneas con ancho_m) rasterizadas sobre los caminos

    @property
    def shape(self):
        return self.grilla.shape


def _leer(ruta: Path, grilla_base: Grilla, ventana, nombre: str, banda: int = 1):
    with rasterio.open(ruta) as src:
        try:
            grilla_base.verificar_raster(src, nombre)
        except ErrorGrilla as e:
            raise ErrorManifiesto(str(e)) from e
        a = src.read(banda, window=ventana) if ventana is not None else src.read(banda)
        return a, src.nodata


def cargar_capas(man: Manifiesto, caja: tuple | None = None, combustible: Path | None = None,
                 indices_mes: Path | None = None, ndvi_verano: Path | None = None,
                 modificador: Path | None = None, buffer_viviendas_m: float = 100.0,
                 barreras_extra: Path | None = None) -> Capas:
    """Lee las capas del manifiesto (y las sobreescrituras del caso) en la ventana `caja`."""
    base = man.grilla
    if caja is None:
        grilla, ventana = base, None
    else:
        grilla, ventana = base.ventana(*caja)

    mdt, nd_mdt = _leer(man.ruta("mdt"), base, ventana, "mdt")
    pend, nd_p = _leer(man.ruta("pendiente"), base, ventana, "pendiente")
    ori, nd_o = _leer(man.ruta("orientacion"), base, ventana, "orientacion")
    ruta_comb = Path(combustible) if combustible else man.ruta("combustible")
    comb, nd_c = _leer(ruta_comb, base, ventana, "combustible")

    pend = np.where(pend == nd_p, 0, pend).astype("float32")
    plano = (ori == 361) | (ori == nd_o)
    ori = np.where(plano, 0, ori).astype("float32")
    comb = comb.astype("int16")
    nd_c = int(nd_c) if nd_c is not None else -9999

    # --- infraestructura -------------------------------------------------------------------
    import geopandas as gpd
    from shapely.geometry import box
    ruta_infra = man.ruta("infraestructura")
    bbox = box(*grilla.bounds)
    caminos = gpd.read_file(ruta_infra, layer="caminos", bbox=tuple(grilla.bounds))
    viviendas = gpd.read_file(ruta_infra, layer="viviendas", bbox=tuple(grilla.bounds))
    red = gpd.read_file(ruta_infra, layer="red_electrica", bbox=tuple(grilla.bounds))
    for g in (caminos, viviendas, red):
        if len(g) and not _mismo_crs(g.crs, grilla.crs):
            raise ErrorManifiesto(f"infraestructura.gpkg en {g.crs}, se esperaba {grilla.crs}")
    caminos = caminos[caminos.intersects(bbox)].copy()
    viviendas = viviendas[viviendas.intersects(bbox)].copy()
    red = red[red.intersects(bbox)].copy()

    shape = grilla.shape; tr = grilla.transform
    camino_ancho = np.zeros(shape, "float32"); camino_tipo = np.full(shape, -1, "int8")
    tipos = TIPOS_CAMINO
    if len(caminos):
        # los más anchos pisan a los más angostos
        for i, t in sorted(enumerate(tipos), key=lambda kv: ANCHO_POR_TIPO[kv[1]]):
            sub = caminos[caminos.tipo == t]
            if not len(sub):
                continue
            m = features.rasterize(((geom, 1) for geom in sub.geometry), out_shape=shape, transform=tr,
                                   fill=0, all_touched=True, dtype="uint8").astype(bool)
            camino_tipo[m] = i
            anchos = features.rasterize(((geom, float(a)) for geom, a in zip(sub.geometry, sub.ancho_m)),
                                        out_shape=shape, transform=tr, fill=0, all_touched=True, dtype="float32")
            camino_ancho = np.where(m, np.maximum(camino_ancho, anchos), camino_ancho)
    vivienda = np.zeros(shape, bool)
    if len(viviendas):
        vivienda = features.rasterize(((geom, 1) for geom in viviendas.geometry), out_shape=shape, transform=tr,
                                      fill=0, all_touched=True, dtype="uint8").astype(bool)
    linea = np.zeros(shape, bool)
    if len(red):
        linea = features.rasterize(((geom, 1) for geom in red.geometry), out_shape=shape, transform=tr,
                                   fill=0, all_touched=True, dtype="uint8").astype(bool)

    capas = Capas(grilla=grilla, base=base, ventana=ventana, mdt=mdt, nodata_mdt=nd_mdt, pendiente=pend,
                  orientacion=ori, plano=plano, combustible=comb, nodata_combustible=nd_c,
                  camino_ancho=camino_ancho, camino_tipo=camino_tipo, vivienda=vivienda, linea_mt=linea,
                  caminos_gdf=caminos, viviendas_gdf=viviendas, red_gdf=red,
                  fuentes={"combustible": str(ruta_comb), "mdt": str(man.ruta("mdt")), "infraestructura": str(ruta_infra)})

    # --- dinámicas ---------------------------------------------------------------------------
    if indices_mes:
        with rasterio.open(indices_mes) as src:
            base.verificar_raster(src, "indices_mes_evento")
            if src.count < 2:
                raise ErrorManifiesto("indices_mes_evento.tif debe tener 2 bandas (NDVI, NDMI) ×10000")
            a = src.read(window=ventana).astype("float32") if ventana is not None else src.read().astype("float32")
            a[a == src.nodata] = np.nan
            capas.ndvi_mes = a[0] / 10000.0
            capas.ndmi_mes = a[1] / 10000.0
        capas.fuentes["indices_mes"] = str(indices_mes)
    if ndvi_verano:
        with rasterio.open(ndvi_verano) as src:
            base.verificar_raster(src, "ndvi_verano")
            a = (src.read(1, window=ventana) if ventana is not None else src.read(1)).astype("float32")
            a[a == src.nodata] = np.nan
            capas.ndvi_verano = a / 10000.0
        capas.fuentes["ndvi_verano"] = str(ndvi_verano)
    if modificador:
        with rasterio.open(modificador) as src:
            base.verificar_raster(src, "modificador_combustible")
            a = (src.read(1, window=ventana) if ventana is not None else src.read(1)).astype("float32")
            a = np.where(a == src.nodata, 1.0, a)
            capas.modificador = np.clip(a, 0.0, 2.0)
        capas.fuentes["modificador"] = str(modificador)
    if barreras_extra:
        rasterizar_barreras_extra(capas, barreras_extra)
    return capas


def rasterizar_barreras_extra(capas: Capas, fuente) -> Capas:
    """Suma barreras lineales (cortafuegos, líneas de control; v3.0 `barreras_extra`) a los caminos de `capas`.

    `fuente`: ruta a un GeoJSON / GPKG de líneas o un GeoDataFrame, con `ancho_m` (m) y `tipo` opcional (uno de
    TIPOS_CAMINO; si falta o no es conocido, `cortafuego`). Se rasterizan con all_touched como los caminos sobre
    `camino_ancho` / `camino_tipo`: en cada celda gana la barrera más ancha (a igual ancho, la extra). Se reproyectan
    al CRS de la grilla si hace falta. Modifica `capas` en el lugar y la devuelve."""
    import geopandas as gpd
    from shapely.geometry import box
    if isinstance(fuente, (str, Path)):
        gdf = gpd.read_file(fuente)
        capas.fuentes["barreras_extra"] = str(fuente)
    else:
        gdf = fuente.copy()
    if not len(gdf):
        capas.barreras_gdf = gdf
        return capas
    if gdf.crs is not None and not _mismo_crs(gdf.crs, capas.grilla.crs):
        gdf = gdf.to_crs(capas.grilla.crs)
    gdf = gdf[gdf.intersects(box(*capas.grilla.bounds))].copy()
    if "tipo" not in gdf.columns:
        gdf["tipo"] = "cortafuego"
    gdf["tipo"] = [t if isinstance(t, str) and t in ANCHO_POR_TIPO else "cortafuego" for t in gdf["tipo"]]
    if "ancho_m" not in gdf.columns:
        gdf["ancho_m"] = np.nan
    gdf["ancho_m"] = [float(a) if a is not None and np.isfinite(float(a)) and float(a) > 0 else ANCHO_POR_TIPO[t]
                      for a, t in zip(gdf["ancho_m"], gdf["tipo"])]
    capas.barreras_gdf = gdf
    if not len(gdf):
        return capas
    shape = capas.grilla.shape; tr = capas.grilla.transform
    for t in sorted(set(gdf["tipo"]), key=lambda t: ANCHO_POR_TIPO[t]):
        sub = gdf[gdf["tipo"] == t].sort_values("ancho_m")      # las más anchas se escriben al final
        anchos = features.rasterize(((g, float(a)) for g, a in zip(sub.geometry, sub["ancho_m"])), out_shape=shape,
                                    transform=tr, fill=0, all_touched=True, dtype="float32", merge_alg=features.MergeAlg.replace)
        m = anchos > 0
        gana = m & (anchos >= capas.camino_ancho)
        capas.camino_tipo[gana] = TIPOS_CAMINO.index(t)
        capas.camino_ancho[:] = np.where(m, np.maximum(capas.camino_ancho, anchos), capas.camino_ancho)
    return capas


def _mismo_crs(a, b) -> bool:
    from pyproj import CRS
    try:
        return CRS.from_user_input(a) == CRS.from_user_input(b)
    except Exception:
        return str(a) == str(b)
