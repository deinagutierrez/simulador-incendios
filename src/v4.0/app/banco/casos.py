"""Casos del banco de pruebas (D30) para la Fase 1 y el desarrollo, con el estándar de `CP/` (protocolo v1.2 §3.7).

Por cada evento de `eventos_fase1.csv` con rol `prueba_fase1` o `desarrollo` escribe `casos/<id_evento>/`:
  caso.json                 claves de `CP/00_metadatos/esquema_columnas.md` + campos del protocolo (T80, T100,
                            instante degenerado, rol, ejes que evalúa)
  perimetro_final.geojson   componente MapBiomas Fuego (polígono, mes) vectorizado, EPSG:4326
  obs_perimetro_final_30m.tif  el mismo componente en la grilla del dominio (uint8, 1 = quemado)
  ignicion.geojson          §4.1: detecciones del primer pase VIIRS (`tipo = primer_foco`) o punto SNMF (`parte`)
  focos_calor.csv           columnas FIRMS + `dentro_cicatriz` + `sensor_fuente` (focos atribuidos, E011)
  partes_diarios.csv        filas del CSV SNMF del incidente emparejado (si lo hay)
  meteo_horaria.csv         ERA5 vía Open-Meteo con la función y las columnas de `CP/scripts/07_meteorologia.py`
y en la raíz `indice_casos.csv` (orden de columnas de `CP/`) y `procedencia_casos.json` (sha256).

Diferencias con `CP/` (documentadas en el protocolo §3.7): grilla = dominio completo (no bbox + 5 km), referencia =
MapBiomas, t0 = primer pase VIIRS, meteo desde el día anterior a t0 hasta T_fin + 1 día.

Uso (desde src/v4.0):  python -I app/banco/casos.py [--salida <carpeta>] [--sin-meteo]
Por defecto: eventos y focos de `protocolo` (datos/inputSimulacion/banco_v4/protocolo) y salida en banco/casos
(resultados/v4.0/banco/casos); `--salida`, `--eventos` y `--focos` relativas a src/v4.0 o absolutas. La meteo existente
no se vuelve a descargar.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "conjunto_pruebas" / "scripts"))
sys.path.insert(0, str(AQUI.parent))
from rutas import Rutas  # noqa: E402
HUSO = "America/Argentina/San_Luis"
COLS_INDICE = ["case_id", "nombre", "anio", "fecha_inicio", "fecha_fin", "fecha_inicio_origen", "fecha_fin_origen", "fecha_inferida",
               "t0_utc", "hora_t0_origen", "duracion_dias", "ha_cicatriz", "ha_parte_smf", "ha_sat_dnbr", "ratio_cicatriz_parte",
               "n_focos", "n_dias_con_focos", "cuadrantes", "lat_ign", "lon_ign", "bbox_oeste", "bbox_sur", "bbox_este", "bbox_norte",
               "niveles_disponibles", "rol", "tipo", "calidad", "ventana_sim_horas_sugerida", "ruta_caso", "notas"]


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main(argv=None):
    import geopandas as gpd
    import rasterio
    from rasterio.features import rasterize, shapes
    from shapely.geometry import shape
    ap = argparse.ArgumentParser()
    ap.add_argument("--raiz", default=None, help="carpeta src/v4.0 (por defecto, la de este código)")
    ap.add_argument("--salida", default=None)
    ap.add_argument("--eventos", default=None)
    ap.add_argument("--focos", default=None)
    ap.add_argument("--horas-extra", type=float, default=48.0)
    ap.add_argument("--sin-meteo", action="store_true")
    a = ap.parse_args(argv)
    RT = Rutas(a.raiz); R = RT.raiz
    OUT = (R / a.salida).resolve() if a.salida else RT.banco / "casos"; OUT.mkdir(parents=True, exist_ok=True)
    entradas = {
        "eventos": (R / a.eventos).resolve() if a.eventos else RT.protocolo / "eventos_fase1.csv",
        "focos": (R / a.focos).resolve() if a.focos else RT.protocolo / "focos_atribuidos.csv",
        "mascara": RT.mascara_dominio,
        "fuego_mensual": RT.fuego_mensual,
        "poligonos": RT.poligonos_mapbiomas,
        "snmf": RT.snmf,
    }
    evs = pd.read_csv(entradas["eventos"])
    evs = evs[evs.rol.isin(["prueba_fase1", "desarrollo"])].sort_values("orden")
    fo_all = pd.read_csv(entradas["focos"])
    snmf = pd.read_csv(entradas["snmf"], encoding="utf-8-sig")
    with rasterio.open(entradas["mascara"]) as s:
        dominio = s.read(1) == 1; T = s.transform; shp = s.shape; perfil = s.profile
    with rasterio.open(entradas["fuego_mensual"]) as s:
        mens = {2022 + i: s.read(i + 1) for i in range(s.count)}
    pol = gpd.read_file(entradas["poligonos"]).to_crs("EPSG:5345")
    if not a.sin_meteo:
        from importlib import import_module
        m07 = import_module("07_meteorologia")      # consultar() y VARS de CP/, sin modificar
    filas_idx, proc = [], {"entradas_sha256": {k: sha(v) for k, v in entradas.items()}, "casos": {}}
    for f in evs.itertuples():
        ide = f.id_evento
        d = OUT / ide; d.mkdir(exist_ok=True)
        meses = [int(m) for m in str(f.meses).split("-")]
        p = pol[pol.oid == f.oid]
        obs = rasterize([(g, 1) for g in p.geometry], out_shape=shp, transform=T, dtype="uint8").astype(bool) & dominio & np.isin(mens[int(f.anio)], meses)
        pf = dict(perfil); pf.update(dtype="uint8", nodata=255, compress="deflate")
        with rasterio.open(d / "obs_perimetro_final_30m.tif", "w", **pf) as dst:
            dst.write(obs.astype("uint8"), 1); dst.update_tags(fuente=f"MapBiomas Fuego Col. 1, polígono {f.oid}, meses {f.meses} de {f.anio}")
        geoms = [shape(g) for g, v in shapes(obs.astype("uint8"), mask=obs, transform=T) if v == 1]
        per = gpd.GeoDataFrame({"fecha": [f"{f.anio}-{meses[-1]:02d}"], "fuente": ["MapBiomas Fuego Col. 1 (componente polígono-mes)"],
                                "ha": [obs.sum() * 0.09]}, geometry=[gpd.GeoSeries(geoms, crs="EPSG:5345").union_all()], crs="EPSG:5345")
        per.to_crs(4326).to_file(d / "perimetro_final.geojson", driver="GeoJSON")
        fo = fo_all[fo_all.id_evento == ide].copy()
        if len(fo):
            fo["t"] = pd.to_datetime(fo.acq_date + " " + fo.acq_time.astype(int).astype(str).str.zfill(4), format="%Y-%m-%d %H%M", utc=True)
            fg = gpd.GeoDataFrame(fo, geometry=gpd.points_from_xy(fo.longitude, fo.latitude), crs=4326)
            xy = fg.to_crs("EPSG:5345").geometry
            rr = ((T.f - xy.y) / 30).astype(int).clip(0, shp[0] - 1); cc = ((xy.x - T.c) / 30).astype(int).clip(0, shp[1] - 1)
            fo["dentro_cicatriz"] = obs[rr.values, cc.values]
            fo["sensor_fuente"] = "VIIRS_SNPP (FIRMS, REPO/datos/crudos/FIRMS)"
            fo["instrument"] = "VIIRS"
            fo[["latitude", "longitude", "acq_date", "acq_time", "satellite", "instrument", "confidence", "frp", "daynight", "dentro_cicatriz", "sensor_fuente"]] \
                .to_csv(d / "focos_calor.csv", index=False, lineterminator="\n")
            t0 = fo.t.min()
            prim = fg[fo.t == t0]
            ign = gpd.GeoDataFrame({"tipo": "primer_foco", "nombre": [f"VIIRS {t0:%Y-%m-%d %H:%M} UTC"] * len(prim), "origen": "FIRMS VIIRS S-NPP",
                                    "dentro_de_cicatriz": fo.loc[prim.index, "dentro_cicatriz"].values, "dist_a_cicatriz_m": np.nan,
                                    "uso_por_defecto": True, "hora_ignicion": t0.tz_convert(HUSO).isoformat()}, geometry=prim.geometry.values, crs=4326)
            hora_origen = "primer_foco"
        else:
            # rama SNMF (§4.1, regla 2): punto del parte, 12:00 local del día de inicio
            fi = pd.Timestamp(f.parte_fecha_inicio)
            t0 = pd.Timestamp(f"{fi.date()} 12:00", tz=HUSO).tz_convert("UTC")
            g_ = snmf[(snmf.fecha_inicio == f.parte_fecha_inicio) & snmf.nombre.astype(str).isin(str(f.parte_snmf).split(" / "))]
            pt = g_.groupby(["longitud_dec", "latitud_dec"]).size().idxmax()
            ign = gpd.GeoDataFrame({"tipo": ["parte"], "nombre": [f.parte_snmf], "origen": ["parte_SNMF"], "dentro_de_cicatriz": [None],
                                    "dist_a_cicatriz_m": [f.parte_dist_m], "uso_por_defecto": [True], "hora_ignicion": [t0.tz_convert(HUSO).isoformat()]},
                                   geometry=gpd.points_from_xy([pt[0]], [pt[1]]), crs=4326)
            hora_origen = "supuesta"
        ign.to_file(d / "ignicion.geojson", driver="GeoJSON")
        if isinstance(f.parte_snmf, str) and f.parte_snmf:
            snmf[(snmf.fecha_inicio == f.parte_fecha_inicio) & snmf.nombre.astype(str).isin(f.parte_snmf.split(" / "))].to_csv(d / "partes_diarios.csv", index=False, lineterminator="\n")
        t80 = pd.Timestamp(f.T80_utc)
        t100 = pd.Timestamp(f.ultimo_pase_utc) if isinstance(f.ultimo_pase_utc, str) and f.ultimo_pase_utc else None
        degenerado = bool(int(f.n_pases) == 1 or t80 <= t0)      # §5 v1.1: un solo pase con focos, o T80 <= t0
        t_fin = max([x for x in (t80, t100) if x is not None]) + pd.Timedelta(hours=a.horas_extra)
        cen = ign.geometry.union_all().centroid
        lat_ign, lon_ign = float(cen.y), float(cen.x)
        if not a.sin_meteo and not (d / "meteo_horaria.csv").exists():
            ini_utc = (t0.tz_convert(HUSO).normalize() - pd.Timedelta(days=1)).tz_convert("UTC").tz_localize(None)
            fin_utc = (t_fin.tz_convert(HUSO).normalize() + pd.Timedelta(hours=47)).tz_convert("UTC").tz_localize(None)
            js = m07.consultar(lat_ign, lon_ign, ini_utc.date().isoformat(), fin_utc.date().isoformat())
            h = pd.DataFrame(js["hourly"]); utc = pd.to_datetime(h.pop("time"))
            h = h[(utc >= ini_utc) & (utc <= fin_utc)].rename(columns=m07.VARS); utc = utc[h.index]
            met = pd.DataFrame({"case_id": ide, "fecha_hora_local": (utc - pd.Timedelta(hours=3)).dt.strftime("%Y-%m-%dT%H:%M:%S-03:00"),
                                "fecha_hora_utc": utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                "minutos_desde_t0": ((utc - t0.tz_localize(None)).dt.total_seconds() // 60).astype(int),
                                "lat_consulta": lat_ign, "lon_consulta": lon_ign, "lat_celda_era5": round(js["latitude"], 4),
                                "lon_celda_era5": round(js["longitude"], 4), "elevacion_dem_m": js["elevation"]})
            met = pd.concat([met, h[list(m07.VARS.values())]], axis=1); met["fuente"] = m07.FUENTE
            met.to_csv(d / "meteo_horaria.csv", index=False, lineterminator="\n")
            time.sleep(1)
        b = per.to_crs(4326).total_bounds
        ficha = {
            "case_id": ide, "nombre": f.parte_snmf if isinstance(f.parte_snmf, str) else "", "anio": int(f.anio), "tipo": "nominal",
            "rol": "prueba_fase1" if f.rol == "prueba_fase1" else "desarrollo", "calidad": None,
            "ids": {"oid_mapbiomas": f.oid, "meses": f.meses, "parte_snmf": f.parte_snmf if isinstance(f.parte_snmf, str) else None},
            "fechas": {"fecha_inicio": str(t0.tz_convert(HUSO).date()), "fecha_fin": str(t_fin.tz_convert(HUSO).date()),
                       "fecha_inicio_origen": "primer_foco" if hora_origen == "primer_foco" else "parte", "fecha_inferida": "no"},
            "t0_utc": t0.strftime("%Y-%m-%dT%H:%M:%SZ"), "t0_local": t0.tz_convert(HUSO).isoformat(), "hora_t0_origen": hora_origen,
            "ignicion_por_defecto": {"tipo": ign.tipo.iloc[0], "lat": lat_ign, "lon": lon_ign, "n_puntos": len(ign)},
            "crs_metrico": "EPSG:5345", "resolucion_m": 30.0, "grilla_caso": {"ncols": shp[1], "nrows": shp[0], "transform_affine": list(T)[:6], "nota": "dominio completo"},
            "hectareas": {"cicatriz": round(float(obs.sum() * 0.09), 2), "fuente_cicatriz": "MapBiomas Fuego Col. 1 (componente polígono-mes)"},
            "n_focos": int(len(fo)), "estado_focos": "OK" if len(fo) else "sin focos",
            "protocolo": {"version": "v1.2", "T80_utc": str(t80), "T80_fuente": f.T80_fuente, "T100_utc": str(t100) if t100 is not None else None,
                          "instante_degenerado": degenerado, "ejes": ["forma"] if degenerado else ["forma", "extension_tiempo"],
                          "t_fin_simulacion_utc": str(t_fin), "estrato_tamano": f.estrato_tamano, "estrato_estacion": f.estrato_estacion,
                          "orden_semilla_20261015": f.orden},
            "ventana_sim_horas_sugerida": float(np.ceil((t_fin - t0).total_seconds() / 3600)),
            "notas": ["Formato de CP/ (esquema_columnas.md) con campos del protocolo v1.2; grilla = dominio completo."],
        }
        (d / "caso.json").write_text(json.dumps(ficha, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        filas_idx.append({"case_id": ide, "nombre": ficha["nombre"], "anio": int(f.anio), "fecha_inicio": ficha["fechas"]["fecha_inicio"],
                          "fecha_fin": ficha["fechas"]["fecha_fin"], "fecha_inicio_origen": ficha["fechas"]["fecha_inicio_origen"],
                          "fecha_fin_origen": "T80/T100 + 48 h", "fecha_inferida": "no", "t0_utc": ficha["t0_utc"], "hora_t0_origen": hora_origen,
                          "duracion_dias": round((t_fin - t0).total_seconds() / 86400, 2), "ha_cicatriz": ficha["hectareas"]["cicatriz"],
                          "ha_parte_smf": None, "ha_sat_dnbr": None, "ratio_cicatriz_parte": f.parte_ratio if pd.notna(f.parte_ratio) else None,
                          "n_focos": int(len(fo)), "n_dias_con_focos": int(fo.acq_date.nunique()) if len(fo) else 0, "cuadrantes": None,
                          "lat_ign": round(lat_ign, 6), "lon_ign": round(lon_ign, 6), "bbox_oeste": b[0], "bbox_sur": b[1], "bbox_este": b[2], "bbox_norte": b[3],
                          "niveles_disponibles": "N1;focos", "rol": ficha["rol"], "tipo": "nominal", "calidad": None,
                          "ventana_sim_horas_sugerida": ficha["ventana_sim_horas_sugerida"], "ruta_caso": f"casos/{ide}",
                          "notas": "instante degenerado: solo eje de forma" if degenerado else ""})
        proc["casos"][ide] = {n.name: sha(n) for n in sorted(d.iterdir()) if n.is_file()}
        print(ide, ficha["rol"], f"{ficha['hectareas']['cicatriz']} ha", f"t0 {ficha['t0_utc']}", f"focos {len(fo)}", "degenerado" if degenerado else "", flush=True)
    pd.DataFrame(filas_idx, columns=COLS_INDICE).to_csv(OUT / "indice_casos.csv", index=False, lineterminator="\n")
    proc["indice_casos_sha256"] = sha(OUT / "indice_casos.csv")
    proc["script_sha256"] = sha(Path(__file__))
    (OUT / "procedencia_casos.json").write_text(json.dumps(proc, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
