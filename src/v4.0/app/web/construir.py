"""Construye la web unificada del banco de pruebas (D30): visor estático (Leaflet) que lee el registro común de
corridas. Cualquier motor que cumpla el contrato (`app/banco/registro.py`) aparece sin cambios en la web.

Por evento escribe GeoJSON en EPSG:4326: perímetro de referencia, ignición, focos atribuidos, elipse B1 y, por
corrida, la huella en T80, la huella a igual superficie y las isócronas (cada `--paso-h` horas hasta T80).
Copia `static/` (index.html, app.js, style.css) y escribe `datos/indice.json` con métricas y resultados de la Fase 1.

v4.0: la carpeta de cada corrida sale de `registro.leer` (relativa al banco o ruta vieja de V.4 reubicada por nombre).
La carpeta de salida se BORRA y se recrea (solo si está vacía o ya es una web generada: tiene index.html).

Uso (desde src/v4.0):  python -I app/web/construir.py [--salida <carpeta>] [--paso-h 6]   (por defecto resultados/v4.0/banco/web)
Servir:  python -m http.server 8765 --directory ../../resultados/v4.0/banco/web
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
sys.path.insert(0, str(AQUI.parent / "banco"))
from rutas import Rutas  # noqa: E402
import registro  # noqa: E402


def vectorizar(mask_o_clases: np.ndarray, T, crs, recorte, propiedad: str = "valor", simplificar_m: float = 15.0):
    import geopandas as gpd
    from rasterio.features import shapes
    from rasterio.transform import Affine
    from shapely.geometry import shape
    r0, r1, c0, c1 = recorte
    sub = mask_o_clases[r0:r1, c0:c1]
    Ts = T * Affine.translation(c0, r0)
    m = sub > 0
    if not m.any():
        return None
    geoms, vals = [], []
    for g, v in shapes(sub.astype("int32"), mask=m, transform=Ts):
        geoms.append(shape(g)); vals.append(int(v))
    gdf = gpd.GeoDataFrame({propiedad: vals}, geometry=geoms, crs=crs).dissolve(by=propiedad).reset_index()
    gdf["geometry"] = gdf.geometry.simplify(simplificar_m)
    return gdf.to_crs(4326)


def horario_corrida(motor: str, carpeta: Path, t0, ha_obs: float) -> list[dict]:
    """Registro por hora simulada, con campos comunes a todos los motores y extras cuando el motor los tiene."""
    filas = []
    if motor.startswith("SIM"):
        for f in sorted((carpeta / "sim").glob("estado_hora_*.json"), key=lambda p: int(p.stem.split("_")[-1])):
            d = json.loads(f.read_text(encoding="utf-8"))
            s, fr, me, ex = d["superficie"], d["frente"], d["meteo"], d["exposicion"]
            filas.append({"h": d["minutos_desde_t0"] / 60, "ts": d["timestamp"], "ha": s["quemada_ha"], "ha_combustion": s["en_combustion_ha"],
                          "temp_c": me["temp_c"], "hr_pct": me["hr_pct"], "viento_kmh": me["viento_kmh"], "viento_dir": me["viento_dir_texto"],
                          "precip_mm_h": me["precip_mm_h"], "h1_pct": me["humedad_muerta_1h_pct"], "h10_pct": me["humedad_muerta_10h_pct"],
                          "h100_pct": me["humedad_muerta_100h_pct"], "vel_cabeza_km_h": fr["velocidad_cabeza_km_h"], "rumbo_cabeza": fr["rumbo_cabeza_texto"],
                          "intensidad_max_kw_m": fr["intensidad_max_kw_m"], "llama_max_m": fr["longitud_llama_max_m"], "perimetro_activo_km": d["perimetro"]["activo_km"],
                          "viviendas_afectadas": ex["viviendas_afectadas"], "viviendas_amenazadas": ex["viviendas_amenazadas"], "caminos_cortados_km": ex["caminos_km_cortados"],
                          "dotaciones": (d.get("supresion") or {}).get("dotaciones"), "linea_km": (d.get("supresion") or {}).get("linea_km")})
    elif motor == "MOD":
        s = pd.read_csv(carpeta / "mod" / "serie_horaria.csv", parse_dates=["time_utc"])
        for r in s.itertuples():
            h = (pd.Timestamp(r.time_utc) - t0).total_seconds() / 3600
            if h < 0:
                continue
            dir_ = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"][int(((r.wind_direction_10m + 22.5) % 360) // 45)]
            filas.append({"h": h, "ts": pd.Timestamp(r.time_utc).tz_convert("America/Argentina/San_Luis").isoformat(), "ha": r.ha_quemadas,
                          "ha_combustion": r.celdas_activas * 0.09, "temp_c": r.temperature_2m, "hr_pct": r.relative_humidity_2m,
                          "viento_kmh": r.wind_speed_10m * 3.6, "viento_dir": dir_, "h1_pct": r.m_1h_pct})
    for f in filas:
        f["pct_obs"] = 100 * f["ha"] / ha_obs if ha_obs else None
    return filas


def main(argv=None):
    import geopandas as gpd
    import rasterio
    ap = argparse.ArgumentParser()
    ap.add_argument("--raiz", default=None, help="carpeta src/v4.0 (por defecto, la de este código)")
    ap.add_argument("--salida", default=None, help="carpeta de la web (relativa a src/v4.0 o absoluta); por defecto banco/web")
    ap.add_argument("--paso-h", type=float, default=6.0)
    a = ap.parse_args(argv)
    RT = Rutas(a.raiz); R = RT.raiz; B = RT.banco
    OUT = (R / a.salida).resolve() if a.salida else B / "web"
    if OUT.exists():
        if any(OUT.iterdir()) and not (OUT / "index.html").exists():
            raise SystemExit(f"{OUT} no está vacía y no es una web generada (sin index.html): no se borra")
        shutil.rmtree(OUT)
    shutil.copytree(AQUI / "static", OUT)
    D = OUT / "datos"; D.mkdir()
    reg = registro.leer(RT)
    reg = reg[reg.estado == "ok"]
    idx = pd.read_csv(B / "casos/indice_casos.csv")
    fase1 = json.loads((B / "fase1/resultados_fase1.json").read_text(encoding="utf-8")) if (B / "fase1/resultados_fase1.json").exists() else None
    por_evento = pd.read_csv(B / "fase1/por_evento.csv") if (B / "fase1/por_evento.csv").exists() else pd.DataFrame()
    eventos = []
    for c in idx.itertuples():
        ide = c.case_id
        corr = reg[reg.id_evento == ide]
        caso = json.loads((B / "casos" / ide / "caso.json").read_text(encoding="utf-8"))
        ed = D / ide; ed.mkdir()
        with rasterio.open(B / "casos" / ide / "obs_perimetro_final_30m.tif") as s:
            obs = s.read(1) == 1; T = s.transform; crs = s.crs; shp = s.shape
        t0 = pd.Timestamp(caso["t0_utc"]); t80 = pd.Timestamp(caso["protocolo"]["T80_utc"])
        m80 = (t80 - t0).total_seconds() / 60.0
        # recorte: referencia + huellas en T80 + B1, con 2 km de margen
        union = obs.copy()
        toas = {}
        for r in corr.itertuples():
            with rasterio.open(Path(r.carpeta_abs) / "toa_min.tif") as s:
                toa = s.read(1).astype("float32")
            toas[r.run_id] = toa
            union |= np.isfinite(toa) & (toa <= m80)
        b1p = B / "fase1/b1" / f"{ide}.tif"
        if b1p.exists():
            with rasterio.open(b1p) as s:
                b1 = s.read(1) == 1
            union |= b1
        rr, cc = np.nonzero(union)
        pad = 67
        rec = (max(rr.min() - pad, 0), min(rr.max() + pad + 1, shp[0]), max(cc.min() - pad, 0), min(cc.max() + pad + 1, shp[1]))
        capas = {}
        g = vectorizar(obs.astype("uint8"), T, crs, rec)
        g.to_file(ed / "referencia.geojson", driver="GeoJSON"); capas["referencia"] = "referencia.geojson"
        shutil.copy2(B / "casos" / ide / "ignicion.geojson", ed / "ignicion.geojson"); capas["ignicion"] = "ignicion.geojson"
        fc = B / "casos" / ide / "focos_calor.csv"
        if fc.exists():
            f = pd.read_csv(fc)
            if len(f):
                gpd.GeoDataFrame(f, geometry=gpd.points_from_xy(f.longitude, f.latitude), crs=4326).to_file(ed / "focos.geojson", driver="GeoJSON")
                capas["focos"] = "focos.geojson"
        if b1p.exists():
            g = vectorizar(b1.astype("uint8"), T, crs, rec)
            if g is not None:
                g.to_file(ed / "B1.geojson", driver="GeoJSON"); capas["B1"] = "B1.geojson"
        runs = []
        for r in corr.itertuples():
            toa = toas[r.run_id]
            met = json.loads((Path(r.carpeta_abs) / "metricas.json").read_text(encoding="utf-8"))
            huella80 = np.isfinite(toa) & (toa <= m80)
            corte = met.get("igual_superficie", {}).get("minutos_corte")
            arch = {}
            g = vectorizar(huella80.astype("uint8"), T, crs, rec)
            if g is not None:
                g.to_file(ed / f"{r.run_id}_T80.geojson", driver="GeoJSON"); arch["T80"] = f"{r.run_id}_T80.geojson"
            if corte is not None:
                g = vectorizar((np.isfinite(toa) & (toa <= corte)).astype("uint8"), T, crs, rec)
                if g is not None:
                    g.to_file(ed / f"{r.run_id}_igualsup.geojson", driver="GeoJSON"); arch["igual_superficie"] = f"{r.run_id}_igualsup.geojson"
            paso = a.paso_h * 60
            clases = np.where(huella80, np.ceil(np.maximum(toa, 1e-6) / paso), 0).astype("int32")
            g = vectorizar(clases, T, crs, rec, propiedad="banda")
            if g is not None:
                g["hasta_h"] = g.banda * a.paso_h
                g.to_file(ed / f"{r.run_id}_isocronas.geojson", driver="GeoJSON"); arch["isocronas"] = f"{r.run_id}_isocronas.geojson"
            # avance hora por hora (para la barra de tiempo): banda = hora en que arde la celda, hasta T80 + 24 h (tope 240 h)
            h_max = int(min(np.nanmax(toa) / 60 if np.isfinite(toa).any() else 0, m80 / 60 + 24, 240)) + 1
            horas = np.where(np.isfinite(toa) & (toa <= h_max * 60), np.ceil(np.maximum(toa, 1e-6) / 60), 0).astype("int32")
            g = vectorizar(horas, T, crs, rec, propiedad="hora")
            if g is not None:
                g.to_file(ed / f"{r.run_id}_horas.geojson", driver="GeoJSON"); arch["horas"] = f"{r.run_id}_horas.geojson"
            hor = horario_corrida(r.motor, Path(r.carpeta_abs), t0, float(obs.sum() * 0.09))
            (ed / f"{r.run_id}_horario.json").write_text(json.dumps(hor, ensure_ascii=False, default=str), encoding="utf-8")
            arch["horario"] = f"{r.run_id}_horario.json"
            i80 = met["instantes"].get("T80", {}); eq = met.get("igual_superficie", {})
            # Skill_F de la Fase 1 solo para la corrida que entró al cálculo (mismo run_id)
            fila_f1 = por_evento[por_evento.run_id == r.run_id] if "run_id" in por_evento else pd.DataFrame()
            runs.append({"run_id": r.run_id, "motor": r.motor, "modelo": r.modelo, "variante": r.variante, "rol": r.rol, "archivos": arch,
                         "metricas": {"ha_sim_T80": i80.get("ha_sim"), "L_T80": i80.get("L"), "iou_T80": i80.get("iou"), "dice_T80": i80.get("dice"),
                                      "iou_eq": eq.get("iou"), "dt_h_T80": eq.get("dt_h"), "truncado_T80": i80.get("truncado"),
                                      "skill_F": float(fila_f1.skill_F.iloc[0]) if len(fila_f1) and pd.notna(fila_f1.skill_F.iloc[0]) else None,
                                      "focos_frac_12h": (met.get("focos") or {}).get("frac_a_12h"),
                                      "precision_focos": (met.get("focos") or {}).get("precision_750m@T80")}})
        # avance observado: % de focos VIIRS atribuidos acumulados por hora desde t0
        focos_h = []
        if fc.exists():
            f = pd.read_csv(fc)
            if len(f):
                tt = pd.to_datetime(f.acq_date + " " + f.acq_time.astype(int).astype(str).str.zfill(4), format="%Y-%m-%d %H%M", utc=True)
                hh = np.sort(((tt - t0).dt.total_seconds() / 3600).values)
                focos_h = [{"h": float(x), "pct": 100.0 * (i + 1) / len(hh)} for i, x in enumerate(hh)]
        b1j = B / "fase1/b1" / f"{ide}.json"
        eventos.append({"id": ide, "nombre": caso.get("nombre") or "", "rol": caso["rol"], "anio": caso["anio"],
                        "ha_obs": caso["hectareas"]["cicatriz"], "t0_utc": caso["t0_utc"], "T80_utc": caso["protocolo"]["T80_utc"],
                        "degenerado": caso["protocolo"]["instante_degenerado"], "n_focos": caso["n_focos"], "capas": capas,
                        "T80_h": m80 / 60, "focos_acumulados": focos_h,
                        "B1": json.loads(b1j.read_text(encoding="utf-8")) if b1j.exists() else None, "corridas": runs})
        print(ide, len(runs), "corridas", flush=True)
    def limpio(o):
        """JSON estricto: NaN e infinitos -> null (el navegador no acepta NaN)."""
        if isinstance(o, dict):
            return {k: limpio(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [limpio(v) for v in o]
        if isinstance(o, (float, np.floating)):
            return None if not math.isfinite(float(o)) else float(o)
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.bool_,)):
            return bool(o)
        return o
    datos = {"generado": pd.Timestamp.now(tz="America/Argentina/San_Luis").isoformat(timespec="seconds"),
             "protocolo": "v1.2", "paso_isocronas_h": a.paso_h, "eventos": eventos, "fase1": fase1}
    (D / "indice.json").write_text(json.dumps(limpio(datos), ensure_ascii=False, allow_nan=False, default=str), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
