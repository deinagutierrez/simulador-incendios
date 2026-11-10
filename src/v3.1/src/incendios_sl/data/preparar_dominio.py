"""Preparación geoespacial del dominio: máscara, DEM y derivados, cobertura, infraestructura, cicatrices.

Todos los productos se escriben en datos/inputSimulacion/<subcarpeta>/ con su JSON de procedencia y se
reutilizan si los parámetros coinciden.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.enums import Resampling

from .. import config as cfgmod
from ..grilla import Grilla, alinear_raster, guardar_raster, pendiente_orientacion, leer_raster
from ..procedencia import escribir_procedencia, producto_vigente

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
def grilla_dominio(dom: dict[str, Any]) -> Grilla:
    return Grilla.desde_config(dom)


def grilla_viento(dom: dict[str, Any]) -> Grilla:
    return grilla_dominio(dom).ampliar(float(dom["margen_viento_m"]))


def grilla_indices(dom: dict[str, Any]) -> Grilla:
    return grilla_dominio(dom).ampliar(float(dom["margen_indices_m"]))


# ---------------------------------------------------------------------------
def preparar_mascara(dom: dict[str, Any]) -> Path:
    """Máscara del dominio exacto (1 dentro, 0 fuera) sobre la grilla maestra."""
    g = grilla_dominio(dom)
    out = cfgmod.dir_derivados("grilla") / f"mascara_dominio_{dom['id']}.tif"
    src = cfgmod.ruta(dom["mascara_dominio"]["archivo"])
    params = {"grilla": g.como_dict(), "filtro": dom["mascara_dominio"]["filtro"]}
    if producto_vigente(out, params):
        return out
    gdf = gpd.read_file(src)
    for k, v in dom["mascara_dominio"]["filtro"].items():
        gdf = gdf[gdf[k] == v]
    if len(gdf) != 1:
        raise ValueError(f"el filtro de máscara seleccionó {len(gdf)} entidades (se esperaba 1)")
    geom = gdf.to_crs(g.crs).geometry.iloc[0]
    mask = g.rasterizar([(geom, 1)], dtype="uint8", fill=0, all_touched=False)
    area_km2 = float(mask.sum()) * g.area_celda_m2 / 1e6
    guardar_raster(out, mask, g, nodata=None, tags={"area_km2": f"{area_km2:.3f}", "celdas_dentro": str(int(mask.sum()))})
    escribir_procedencia(out, "primero_cuadrado.geojson (dominio exacto) rasterizado", params, [src],
                         extra={"celdas_dentro": int(mask.sum()), "area_km2": area_km2})
    log.info("máscara: %d celdas dentro (%.2f km²)", mask.sum(), area_km2)
    return out


# ---------------------------------------------------------------------------
def preparar_dem(dom: dict[str, Any]) -> dict[str, Path]:
    """DEM sobre la grilla maestra + pendiente + orientación; DEM ampliado para WindNinja.

    Fuente según dom['dem']['fuente']: 'copernicus_glo30' (archivo ampliado generado vía GEE por
    remote_sensing.gee_dem) o 'aster' (archivo original provisto, reproyectado bilinealmente)."""
    g = grilla_dominio(dom)
    gv = grilla_viento(dom)
    ddir = cfgmod.dir_derivados("dem")
    fuente = dom["dem"]["fuente"]
    out = {
        "dem_viento": ddir / f"dem_{fuente}_viento_{dom['id']}.tif",
        "dem": ddir / f"dem_{fuente}_{dom['id']}.tif",
        "pendiente": ddir / f"pendiente_{fuente}_{dom['id']}.tif",
        "orientacion": ddir / f"orientacion_{fuente}_{dom['id']}.tif",
    }
    params = {"fuente": fuente, "grilla": g.como_dict(), "grilla_viento": gv.como_dict()}
    if out["dem_viento"].exists() and all(producto_vigente(out[k], params) for k in ("dem", "pendiente", "orientacion")):
        return out

    if fuente == "copernicus_glo30":
        from ..remote_sensing.gee_dem import exportar_copernicus_glo30
        src = exportar_copernicus_glo30(gv, out["dem_viento"])
        arr_v, _, nd = leer_raster(src)
        arr_v = arr_v.astype(np.float32)
    elif fuente == "aster":
        src = cfgmod.ruta(dom["dem"]["archivo_aster"])
        arr_v = alinear_raster(src, gv, Resampling.bilinear, dtype="float32", nodata_dst=-9999.0)
        nd = -9999.0
        # relleno de vacíos residuales por interpolación simple (vecino más cercano válido)
        if np.any(arr_v == nd):
            from scipy import ndimage
            huecos = arr_v == nd
            idx = ndimage.distance_transform_edt(huecos, return_distances=False, return_indices=True)
            arr_v = arr_v[tuple(idx)]
            log.warning("DEM ASTER: %d celdas sin dato rellenadas por vecino más cercano", int(huecos.sum()))
        guardar_raster(out["dem_viento"], arr_v, gv, nodata=None)
        escribir_procedencia(out["dem_viento"], "ASTER GDEM provisto, reproyectado bilinealmente", params, [src])
    else:
        raise ValueError(f"fuente de DEM desconocida: {fuente}")

    r0, c0 = g.ventana_en(gv)
    dem = arr_v[r0:r0 + g.nfil, c0:c0 + g.ncol]
    pend, asp = pendiente_orientacion(dem, g.res)
    guardar_raster(out["dem"], dem.astype(np.float32), g, nodata=None, tags={"unidades": "m"})
    guardar_raster(out["pendiente"], pend, g, nodata=None, tags={"unidades": "grados", "metodo": "Horn 3x3"})
    guardar_raster(out["orientacion"], asp, g, nodata=-1.0, tags={"unidades": "grados azimut (0 N, 90 E)", "metodo": "Horn 3x3"})
    for k in ("dem", "pendiente", "orientacion"):
        escribir_procedencia(out[k], f"derivado de {out['dem_viento'].name}", params, [out["dem_viento"]])
    log.info("DEM listo: %s (pendiente p50=%.1f°, p99=%.1f°)", fuente, np.percentile(pend, 50), np.percentile(pend, 99))
    return out


# ---------------------------------------------------------------------------
def preparar_cobertura(dom: dict[str, Any], anios: list[int]) -> dict[int, Path]:
    """Cobertura MapBiomas por año alineada a la grilla (vecino más cercano)."""
    g = grilla_dominio(dom)
    cdir = cfgmod.dir_derivados("cobertura")
    out: dict[int, Path] = {}
    for a in anios:
        src = cfgmod.ruta(dom["cobertura"]["patron"].format(anio=a))
        dst = cdir / f"cobertura_mapbiomas_col3_{a}_{dom['id']}.tif"
        params = {"anio": a, "grilla": g.como_dict(), "remuestreo": "nearest"}
        if not producto_vigente(dst, params):
            arr = alinear_raster(src, g, Resampling.nearest, dtype="uint8", nodata_dst=0)
            guardar_raster(dst, arr, g, nodata=0)
            u, c = np.unique(arr, return_counts=True)
            escribir_procedencia(dst, "MapBiomas Argentina Col. 3 (recorte provincial provisto)", params, [src],
                                 extra={"conteo_clases": {int(k): int(v) for k, v in zip(u, c)}})
        out[a] = dst
    return out


# ---------------------------------------------------------------------------
def preparar_infraestructura(dom: dict[str, Any]) -> dict[str, Path]:
    """Recorta caminos, viviendas y red MT al dominio ampliado (1 km) y guarda GPKG en EPSG:5345."""
    g = grilla_dominio(dom).ampliar(1000)
    idir = cfgmod.dir_derivados("infraestructura")
    from shapely.geometry import box
    caja = box(*g.bounds)
    out: dict[str, Path] = {}
    for nombre, rel in dom["infraestructura"].items():
        src = cfgmod.ruta(rel)
        dst = idir / f"{nombre}_{dom['id']}.gpkg"
        params = {"bbox": g.bounds, "crs": g.crs}
        if producto_vigente(dst, params):
            out[nombre] = dst
            continue
        gdf = gpd.read_file(src, bbox=tuple(gpd.GeoSeries([caja], crs=g.crs).to_crs(4326).total_bounds))
        gdf = gdf.to_crs(g.crs)
        gdf = gdf[gdf.intersects(caja)].copy()
        gdf["geometry"] = gdf.geometry.intersection(caja)
        gdf = gdf[~gdf.geometry.is_empty]
        # geometrías mixtas (viviendas): separar por tipo geométrico en capas
        tipos = gdf.geom_type.str.replace("Multi", "").unique()
        dst.unlink(missing_ok=True)
        for t in tipos:
            sub = gdf[gdf.geom_type.str.replace("Multi", "") == t]
            sub.to_file(dst, layer=t.lower(), driver="GPKG")
        escribir_procedencia(dst, f"{src.name} recortado al dominio + 1 km", params, [src],
                             extra={"entidades": int(len(gdf)), "capas": [t.lower() for t in tipos]})
        out[nombre] = dst
        log.info("infraestructura %s: %d entidades", nombre, len(gdf))
    return out


# ---------------------------------------------------------------------------
def preparar_cicatriz_evento(dom: dict[str, Any], ev: dict[str, Any]) -> Path:
    """Raster de referencia del evento (1 = quemado según el polígono MapBiomas, 0 = no) sobre la grilla."""
    g = grilla_dominio(dom)
    edir = cfgmod.dir_derivados("eventos", ev["id"])
    out = edir / f"cicatriz_referencia_{ev['id']}.tif"
    src = cfgmod.ruta(dom["cicatrices"]["poligonos"])
    oid = str(ev["referencia_espacial"]["oid"])
    mes = ev["referencia_espacial"].get("mes")
    anio = ev["referencia_espacial"].get("calendar_year")
    params = {"oid": oid, "grilla": g.como_dict(), "mes": mes, "calendar_year": anio}
    if producto_vigente(out, params):
        return out
    gdf = gpd.read_file(src, where=f"oid = '{oid}'")
    if len(gdf) != 1:
        raise ValueError(f"oid {oid}: {len(gdf)} polígonos")
    geom = gdf.to_crs(g.crs).geometry.iloc[0]
    arr = g.rasterizar([(geom, 1)], dtype="uint8")
    if mes is not None:
        # restringir a los píxeles quemados en el mes indicado (separación de eventos fusionados en un polígono anual)
        mensual = preparar_cicatriz_mensual(dom)
        with rasterio.open(mensual) as ds:
            descr = list(ds.descriptions)
            banda = descr.index(f"burned_monthly_{anio}") + 1
            m = ds.read(banda)
        arr = (arr & (m == int(mes))).astype(np.uint8)
    area_ha = float(arr.sum()) * g.area_celda_m2 / 1e4
    guardar_raster(out, arr, g, nodata=None, tags={"oid": oid, "area_ha": f"{area_ha:.1f}"})
    escribir_procedencia(out, "MapBiomas Fuego Col. 1 polígono rasterizado", params, [src],
                         extra={"area_ha_rasterizada": area_ha, "area_ha_poligono_5345": float(geom.area / 1e4)})
    return out


def preparar_cicatriz_mensual(dom: dict[str, Any]) -> Path:
    g = grilla_dominio(dom)
    src = cfgmod.ruta(dom["cicatrices"]["mensual"])
    out = cfgmod.dir_derivados("cicatrices") / f"fuego_mensual_{dom['id']}.tif"
    params = {"grilla": g.como_dict()}
    if producto_vigente(out, params):
        return out
    with rasterio.open(src) as ds:
        n = ds.count
        descr = list(ds.descriptions)
    bandas = [alinear_raster(src, g, Resampling.nearest, dtype="uint8", nodata_dst=255, banda=b) for b in range(1, n + 1)]
    guardar_raster(out, np.stack(bandas), g, nodata=255, descripciones=descr)
    escribir_procedencia(out, "MapBiomas Fuego Col. 1 mensual alineado", params, [src])
    return out


# ---------------------------------------------------------------------------
def _clave_ancho(clase: str, superficie: str) -> str:
    if clase == "ruta" and superficie == "pavimentado":
        return "ruta_pavimentado"
    return clase


def preparar_barreras_enlaces(dom: dict[str, Any], anchos: dict[str, float], vecindad: int = 16, factor_fino: int = 4,
                              excluir_duplicados: bool = True) -> Path:
    """Barreras lineales sobre los enlaces del estencil (modelo v2, docs/10).

    Para cada celda y cada vecino k se registra el código de la barrera más ancha que cruza el segmento entre centros
    (0 = ninguna). Las vías se rasterizan a `res/factor_fino` con all_touched y el segmento se muestrea a esa misma
    separación, excluyendo los extremos (una vía que pasa por el centro de la celda no bloquea los enlaces del mismo lado).
    Salida: NPZ con `codigos` uint8 (nfil, ncol, vecindad), `ancho_m` float64 por código (índice 0 = sin barrera) y
    `nombres`; procedencia en el JSON adjunto."""
    from ..simulation.automata import estencil
    from rasterio import features
    g = grilla_dominio(dom)
    out = cfgmod.dir_derivados("barreras") / f"barreras_enlaces_{dom['id']}.npz"
    infra = preparar_infraestructura(dom)
    extra = dom.get("barreras_extra")
    params = {"grilla": g.como_dict(), "anchos": dict(sorted(anchos.items())), "vecindad": vecindad, "factor_fino": factor_fino,
              "excluir_duplicados": excluir_duplicados, "barreras_extra": extra, "version": "v2.0"}
    if producto_vigente(out, params):
        return out
    cam = gpd.read_file(infra["caminos"])
    if excluir_duplicados and "dup_probable" in cam:
        cam = cam[~cam["dup_probable"].astype(bool)]
    claves = [_clave_ancho(str(c), str(s)) for c, s in zip(cam.get("clase", ""), cam.get("superficie", ""))]
    cam = cam.assign(ancho_m=[anchos.get(k, anchos.get("otro")) for k in claves], clave=claves)
    sin_ancho = cam["ancho_m"].isna()
    if sin_ancho.any():
        log.warning("barreras: %d tramos sin ancho asignado (clases %s) se omiten", int(sin_ancho.sum()), sorted(set(cam.loc[sin_ancho, "clave"])))
        cam = cam[~sin_ancho]
    geoms = list(zip(cam.geometry, cam["ancho_m"].astype(float), cam["clave"]))
    entradas = [infra["caminos"]]
    if extra:
        ex = gpd.read_file(cfgmod.ruta(extra)).to_crs(g.crs)
        if "ancho_m" not in ex:
            raise ValueError("barreras_extra requiere el atributo ancho_m")
        geoms += [(geom, float(a), "extra") for geom, a in zip(ex.geometry, ex["ancho_m"])]
        entradas.append(cfgmod.ruta(extra))
    anchos_unicos = sorted({a for _, a, _ in geoms})
    codigo_de = {a: i + 1 for i, a in enumerate(anchos_unicos)}
    nombres = {codigo_de[a]: sorted({n for _, aa, n in geoms if aa == a}) for a in anchos_unicos}
    # raster fino: el código mayor (más ancho) se pinta último y prevalece
    res_f = g.res / factor_fino
    shape_f = (g.nfil * factor_fino, g.ncol * factor_fino)
    from rasterio.transform import Affine
    tr_f = Affine(res_f, 0.0, g.xmin, 0.0, -res_f, g.ymax)
    pares = [(geom.__geo_interface__, codigo_de[a]) for geom, a, _ in sorted(geoms, key=lambda x: x[1]) if not geom.is_empty]
    fino = features.rasterize(pares, out_shape=shape_f, transform=tr_f, fill=0, all_touched=True, dtype="uint8") if pares else np.zeros(shape_f, np.uint8)
    dy, dx, dist, _ = estencil(vecindad, g.res)
    cod = np.zeros((g.nfil, g.ncol, vecindad), np.uint8)
    rr, cc = np.mgrid[0:g.nfil, 0:g.ncol]
    x0 = g.xmin + (cc + 0.5) * g.res; y0 = g.ymax - (rr + 0.5) * g.res
    for k in range(vecindad):
        n_s = int(np.ceil(dist[k] / res_f)) + 1
        s_vals = np.linspace(0.0, 1.0, n_s + 2)[1:-1]
        dentro = (rr + dy[k] >= 0) & (rr + dy[k] < g.nfil) & (cc + dx[k] >= 0) & (cc + dx[k] < g.ncol)
        acum = np.zeros((g.nfil, g.ncol), np.uint8)
        for s in s_vals:
            xs = x0 + s * dx[k] * g.res; ys = y0 - s * dy[k] * g.res
            cf = np.clip(np.floor((xs - g.xmin) / res_f).astype(np.int64), 0, shape_f[1] - 1)
            rf = np.clip(np.floor((g.ymax - ys) / res_f).astype(np.int64), 0, shape_f[0] - 1)
            np.maximum(acum, fino[rf, cf], out=acum)
        cod[:, :, k] = np.where(dentro, acum, 0)
    ancho_arr = np.array([0.0] + anchos_unicos, np.float64)
    np.savez_compressed(out, codigos=cod, ancho_m=ancho_arr, nombres=json.dumps(nombres, ensure_ascii=False))
    n_enl = int((cod > 0).sum()); n_cel = int((cod > 0).any(axis=2).sum())
    escribir_procedencia(out, "caminos (OSM/SIG SL/IGN) + barreras_extra sobre enlaces del estencil", params, entradas,
                         extra={"enlaces_con_barrera": n_enl, "celdas_con_barrera": n_cel, "codigos": {str(k): {"ancho_m": a, "clases": nombres[k]} for a, k in codigo_de.items()},
                                "tramos_usados": int(len(cam)), "nota": "anchos por clase = HIPÓTESIS (docs/10 §3.1)"})
    log.info("barreras: %d enlaces con barrera en %d celdas (%d tramos, %d anchos)", n_enl, n_cel, len(cam), len(anchos_unicos))
    return out


def cargar_barreras_enlaces(path: Path) -> tuple[np.ndarray, np.ndarray, dict]:
    z = np.load(path, allow_pickle=False)
    return z["codigos"], z["ancho_m"], json.loads(str(z["nombres"]))


def preparar_todo_dominio(dom: dict[str, Any], anios: list[int]) -> dict[str, Any]:
    res: dict[str, Any] = {"mascara": preparar_mascara(dom)}
    res.update(preparar_dem(dom))
    res["cobertura"] = preparar_cobertura(dom, anios)
    res["infraestructura"] = preparar_infraestructura(dom)
    res["cicatriz_mensual"] = preparar_cicatriz_mensual(dom)
    man = cfgmod.dir_derivados("grilla") / f"manifiesto_dominio_{dom['id']}.json"
    with open(man, "w", encoding="utf-8") as f:
        json.dump({k: (str(v) if not isinstance(v, dict) else {kk: str(vv) for kk, vv in v.items()}) for k, v in res.items()},
                  f, indent=2, ensure_ascii=False)
    return res
