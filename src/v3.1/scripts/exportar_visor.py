"""Exporta una corrida a un visor HTML autónomo (mapa Leaflet + línea de tiempo + estadísticas), sin servidor.

Uso:
  python scripts/exportar_visor.py --run-id calibracion_2024_20261016-1200 [--salida docs/visor/<run_id>.html]

El visor incluye el tiempo de llegada remuestreado a 120 m, relieve, combustibles, cicatriz, caminos, viviendas,
red eléctrica, focos de calor, localidades y departamentos; todo embebido (unos 3–5 MB) para publicarlo en GitHub Pages.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from PIL import Image  # noqa: E402
from rasterio.enums import Resampling  # noqa: E402

from incendios_sl import config as cfgmod  # noqa: E402
from incendios_sl.api import capas  # noqa: E402
from incendios_sl.grilla import leer_raster  # noqa: E402

RES = 120.0


def png64(rgba: np.ndarray) -> str:
    buf = io.BytesIO(); Image.fromarray(rgba, "RGBA").save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def rnd(cs):
    return [rnd(x) for x in cs] if isinstance(cs[0], list) else [round(cs[0], 4), round(cs[1], 4)]


def geojson_compacto(gdf, cols, tol_m):
    gdf = gdf.copy(); gdf["geometry"] = gdf.geometry.simplify(tol_m)
    g = json.loads(gdf[[c for c in cols if c in gdf.columns] + ["geometry"]].to_crs(4326).to_json(drop_id=True))
    for f in g["features"]:
        f["geometry"]["coordinates"] = rnd(f["geometry"]["coordinates"])
    return g


def sombreado(dem: np.ndarray, res: float) -> np.ndarray:
    dy, dx = np.gradient(dem.astype(float), res); sl = np.arctan(np.hypot(dx, dy)); asp = np.arctan2(-dx, dy)
    return np.sin(np.radians(45)) * np.cos(sl) + np.cos(np.radians(45)) * np.sin(sl) * np.cos(np.radians(315) - asp)


def exportar(run_id: str, salida: Path | None = None) -> Path:
    import geopandas as gpd
    import pyogrio
    R = cfgmod.dir_resultados() / run_id
    reg = json.load(open(R / "registro.json", encoding="utf-8")); ent = reg["entradas"]
    ev_id, dom_id = ent["evento"], ent["dominio"]
    ev = cfgmod.cargar_evento(ev_id); dom = cfgmod.cargar_dominio(dom_id)
    g = capas.Grilla.desde_config(dom); D = cfgmod.dir_entradas()
    met = json.load(open(R / "metricas.json", encoding="utf-8")) if (R / "metricas.json").exists() else None
    B: dict = {}
    # tiempo de llegada (minutos, uint16) remuestreado a 120 m
    ta, _, nd = leer_raster(R / "t_llegada_s.tif"); ta = np.where(ta == nd, -1.0, ta).astype(np.float32)
    m, b = capas.a_mercator(ta, g, -2.0, "float32", Resampling.min, res_m=RES)
    mins = np.full(m.shape, 65535, np.uint16); mins[m == -2] = 65534; ok = m >= 0; mins[ok] = np.round(m[ok] / 60).astype(np.uint16)
    B["ta"] = {"w": int(m.shape[1]), "h": int(m.shape[0]), "bounds": b, "b64": base64.b64encode(mins.tobytes()).decode()}
    # relieve (dominio y, si existe, el DEM con margen de viento)
    for clave, nombre in (("sombras", f"dem_{dom['dem']['fuente']}_{dom_id}.tif"), ("sombras_norte", f"dem_{dom['dem']['fuente']}_viento_{dom_id}.tif")):
        p = D / "dem" / nombre
        if not p.exists():
            continue
        dem, gd, ndd = leer_raster(p); dem = np.where(dem == ndd, np.nan, dem).astype(float)
        hs = sombreado(dem, gd.res); hs = np.where(np.isnan(hs), -1, (hs + 1) / 2 * 255).astype(np.float32)
        mh, bh = capas.a_mercator(hs, gd, -1.0, "float32", Resampling.bilinear, res_m=RES)
        v = np.clip(mh, 0, 255).astype(np.uint8); a = np.where(mh < 0, 0, 255).astype(np.uint8)
        B[clave] = {"bounds": bh, "png": png64(np.dstack([v, v, v, a]))}
    # combustible, cicatriz, máscara
    c, _, _ = leer_raster(D / "combustibles" / ev_id / f"combustible_clase_{ev_id}.tif")
    mc, bc = capas.a_mercator(c, g, 255, "uint8", Resampling.nearest, res_m=RES)
    rgba = np.zeros(mc.shape + (4,), np.uint8)
    for k, col in capas.COLORES_CLASE.items():
        rgba[mc == k] = (*col, 200)
    B["combustible"] = {"bounds": bc, "png": png64(rgba), "clases": [{"codigo": k, "nombre": capas.NOMBRES_CLASE[k], "color": "#%02x%02x%02x" % cc} for k, cc in capas.COLORES_CLASE.items()]}
    pref = D / "eventos" / ev_id / f"cicatriz_referencia_{ev_id}.tif"
    if pref.exists():
        r, _, _ = leer_raster(pref); mr, br = capas.a_mercator(r, g, 255, "uint8", Resampling.nearest, res_m=RES)
        rgba = np.zeros(mr.shape + (4,), np.uint8); rgba[mr == 1] = (0, 200, 255, 150); B["cicatriz"] = {"bounds": br, "png": png64(rgba)}
    else:
        B["cicatriz"] = {"bounds": b, "png": png64(np.zeros((2, 2, 4), np.uint8))}
    mk, _, _ = leer_raster(D / "grilla" / f"mascara_dominio_{dom_id}.tif")
    mm, bm = capas.a_mercator(mk, g, 255, "uint8", Resampling.nearest, res_m=RES)
    rgba = np.zeros(mm.shape + (4,), np.uint8); rgba[mm == 0] = (0, 0, 0, 90); B["mascara"] = {"bounds": bm, "png": png64(rgba)}
    # vectores del dominio
    for nombre, cols, tol in (("caminos", ["clase", "nombre"], 60), ("electricidad_mt", ["tension_kv"], 60), ("viviendas", ["tipo", "uso_residencial"], 60)):
        p = D / "infraestructura" / f"{nombre}_{dom_id}.gpkg"
        partes = [gpd.read_file(p, layer=l) for l in pyogrio.list_layers(p)[:, 0]] if p.exists() else []
        gdf = gpd.GeoDataFrame(pd.concat(partes, ignore_index=True), crs=partes[0].crs) if partes else gpd.GeoDataFrame(geometry=[], crs=4326)
        B["electricidad" if nombre == "electricidad_mt" else nombre] = geojson_compacto(gdf, cols, tol) if len(gdf) else {"type": "FeatureCollection", "features": []}
    # contexto desde datos/crudos (opcional): departamentos, rutas, red MT, viviendas, cobertura
    C = cfgmod.dir_crudos()
    lonmin, latmin, lonmax, latmax = b[1] - 0.25, b[0] - 0.25, b[3] + 0.25, b[2] + 0.25
    try:
        d = gpd.read_file(C / "departamentos_san_luis_ign_conae.geojson").to_crs(4326)
        B["departamentos"] = geojson_compacto(d.rename(columns={"departamento": "nombre"}), ["nombre"], 0.002)
    except Exception:
        pass
    try:
        cam = gpd.read_file(C / "caminos_sanluis_integrado.geojson").cx[lonmin:lonmax, latmin:latmax]
        B["rutas_norte"] = geojson_compacto(cam[cam.clase.isin(["ruta", "autopista"])].to_crs(5345), ["clase", "nombre"], 150)
        viv = gpd.read_file(C / "viviendas_sanluis_integrado.geojson").cx[lonmin:lonmax, latmin:latmax].to_crs(5345)
        pt = viv.geometry.centroid.to_crs(4326); B["viv_norte"] = [[round(x, 4), round(y, 4)] for x, y in zip(pt.x, pt.y)]
        # localidades: nombres de las viviendas con nombre (centro de cada grupo)
        vn = viv[viv.nombre.notna() & ~viv.nombre.str.contains("Estancia|Estacion|Puesto|Escuela|Centro|Cuartel|Municipalidad|Terminal|Reserva|Planta|Balneario", case=False)]
        vn = vn.assign(x=vn.geometry.centroid.x, y=vn.geometry.centroid.y).groupby("nombre").agg(x=("x", "median"), y=("y", "median"), n=("x", "size")).reset_index()
        loc = gpd.GeoDataFrame(vn, geometry=gpd.points_from_xy(vn.x, vn.y), crs=5345).to_crs(4326)
        B["localidades"] = [{"n": r.nombre, "lon": round(r.geometry.x, 4), "lat": round(r.geometry.y, 4), "k": "ciudad" if r.n >= 3 else "paraje"} for r in loc.itertuples()]
        from shapely.ops import linemerge, unary_union
        e = gpd.read_file(C / "Electricidad" / "red_distribucion_MT_EDESAL_SL.geojson").cx[lonmin:lonmax, latmin:latmax].to_crs(5345)
        ge = gpd.GeoDataFrame(geometry=[linemerge(unary_union(e.geometry.values))], crs=5345).explode(index_parts=False)
        B["elec_norte"] = geojson_compacto(ge[ge.length > 500], [], 300)
    except Exception as ex:  # el contexto es opcional
        print("contexto parcial:", ex)
    # focos de calor del evento
    hs = cfgmod.dir_catalogo() / "hotspots" / f"viirs_{ev_id}.csv"
    if not hs.exists() or hs.stat().st_size < 10:
        hs = cfgmod.dir_catalogo() / "hotspots" / f"modis_{ev_id}.csv"
    t0 = pd.Timestamp(ent["t_inicio_utc"])
    if hs.exists() and hs.stat().st_size > 10:
        f = pd.read_csv(hs)
        seg = f["acq_time_s"] if "acq_time_s" in f.columns else 13.5 * 3600  # MODIS diario: se asume paso de mediodía
        tt = (pd.to_datetime(f["date"], utc=True) + pd.to_timedelta(seg, unit="s") - t0).dt.total_seconds() / 3600
        B["focos"] = {"t0": str(t0), "pts": [[round(x, 4), round(y, 4), round(t, 1)] for x, y, t in zip(f.lon, f.lat, tt)]}
    else:
        B["focos"] = {"t0": str(t0), "pts": []}
    # serie, métricas, registro, ignición
    s = pd.read_csv(R / "serie_horaria.csv")
    B["serie"] = [{"t": r.time_utc[:16], "h": round(r.t_s / 3600), "ha": round(r.ha_quemadas), "act": int(r.celdas_activas), "T": round(r.temperature_2m, 1), "HR": round(r.relative_humidity_2m),
                   "V": round(r.wind_speed_10m * 3.6, 1), "D": round(r.wind_direction_10m), "m1": round(r.m_1h_pct, 1)} for r in s.itertuples()]
    B["metricas"] = (met or {}).get("espacial", [])
    B["registro"] = {k: reg.get(k) for k in ("version_codigo", "pasos", "segundos_cpu", "t_simulado_utc", "ha_quemadas", "fecha_corrida")} | {"run_id": run_id}
    B["ignicion"] = ent.get("igniciones") or ev["ignicion"]["puntos"]
    # metadatos para la interfaz
    ha_ref = (B["metricas"][0]["ha_ref"] if B["metricas"] else ev.get("referencia_espacial", {}).get("superficie_ha"))
    evals = [{"h": int(mm_["horas_desde_ignicion"]), "label": pd.Timestamp(mm_["t_eval_utc"]).tz_convert("America/Argentina/San_Luis").strftime("%d/%m")} for mm_ in B["metricas"][:4]]
    h_eval = evals[0]["h"] if evals else min(72, B["serie"][-1]["h"])
    ymax = max(ha_ref * 1.5 if ha_ref else 0, (B["serie"][min(len(B["serie"]) - 1, h_eval)]["ha"]) * 1.2, 100)
    fin = ev.get("fin", {}); ini = ev.get("inicio", {})
    fmt = lambda d: pd.Timestamp(d).strftime("%d/%m/%Y") if d else None
    fechas = f"Ignición {fmt(ini.get('fecha_local')) or t0.tz_convert('America/Argentina/San_Luis').strftime('%d/%m/%Y')}"
    if fin.get("fecha_contenido_snmf"): fechas += f" · contenido {fmt(fin['fecha_contenido_snmf'])}"
    if fin.get("fecha_extincion_snmf"): fechas += f" · extinguido {fmt(fin['fecha_extincion_snmf'])}"
    B["meta"] = {"titulo": f"{ev['nombre']} — corrida {run_id}", "t0": t0.isoformat(), "fechas": fechas,
                 "fechas2": f"fechas informadas por el SNMF · simulado hasta {pd.Timestamp(reg['t_simulado_utc']).tz_convert('America/Argentina/San_Luis').strftime('%d/%m/%Y %H:%M')} ({round(float(reg.get('t_simulado_s', 0)) / 3600)} h)",
                 "subtitulo": f"Autómata celular a 30 m, sin combate. Evento {ev_id}, hipótesis de ignición {ent.get('hipotesis_ignicion')}, corrida del {str(reg.get('fecha_corrida', ''))[:16].replace('T', ' ')}."
                              + (f" Referencia: cicatriz MapBiomas de {ha_ref:,.0f} ha.".replace(",", ".") if ha_ref else ""),
                 "ha_ref": ha_ref, "evals": evals, "h_eval": h_eval, "eval_label": evals[0]["label"] if evals else "fin",
                 "aviso": "La corrida no modela el combate: desde acá supera la superficie real del incendio." if ha_ref else "", "ymax": ymax}
    plantilla = (Path(__file__).resolve().parents[1] / "web" / "visor_plantilla.html").read_text(encoding="utf-8")
    html = plantilla.replace("__TITULO__", B["meta"]["titulo"]).replace("__BUNDLE__", json.dumps(B, ensure_ascii=False, separators=(",", ":")))
    salida = salida or (cfgmod.raiz_repositorio() / "docs" / "visor" / f"{run_id}.html")
    salida.parent.mkdir(parents=True, exist_ok=True); salida.write_text(html, encoding="utf-8")
    print(f"visor: {salida} ({salida.stat().st_size / 1e6:.1f} MB)")
    return salida


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--run-id", required=True); ap.add_argument("--salida")
    a = ap.parse_args(); exportar(a.run_id, Path(a.salida) if a.salida else None); return 0


if __name__ == "__main__":
    sys.exit(main())
