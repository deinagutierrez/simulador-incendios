"""Exporta una corrida de resultados/v4.0 a un visor HTML autónomo (mapa Leaflet + barra de tiempo + estadísticas).

Uso (desde src/v4.0):
  python scripts/exportar_visor.py --run-id prueba_rapida_v4_20261025-1800 [--salida resultados/v4.0/<run_id>/visor.html]

Embebe en el HTML (web/visor_plantilla.html) los perímetros horarios de SIM (`perimetros_horarios.geojson`, simplificados
a 15 m y, si hay más de 240 horas, una de cada k), la serie horaria (`serie_indicadores.csv`), el resumen de la corrida,
la ignición, el perímetro observado, los focos VIIRS y las barreras extra de mitigación. Leaflet 1.9.4 y los mosaicos
del mapa base se cargan de internet al abrirlo. Por defecto el visor queda en la carpeta de la corrida (`visor.html`).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from incendios_sl import config as cfgmod  # noqa: E402

MAX_CUADROS = 240
MAX_FOCOS = 6000
RUMBOS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"]


def _redondear(c, n=5):
    return [_redondear(x, n) for x in c] if isinstance(c, (list, tuple)) and c and isinstance(c[0], (list, tuple)) else [round(float(c[0]), n), round(float(c[1]), n)]


def geojson_compacto(gdf, columnas: list[str], tol_m: float = 15.0) -> dict:
    """GeoJSON WGS84 simplificado en metros (EPSG:5345) con coordenadas de 5 decimales (~1 m)."""
    if gdf is None or not len(gdf):
        return {"type": "FeatureCollection", "features": []}
    g = gdf.to_crs(5345).copy()
    g["geometry"] = g.geometry.simplify(tol_m, preserve_topology=True)
    for c in columnas:                      # pyogrio lee los ISO como fechas: se devuelven como texto ISO
        if c in g.columns and str(g[c].dtype).startswith("datetime"):
            g[c] = [None if pd.isna(x) else pd.Timestamp(x).isoformat() for x in g[c]]
    d = json.loads(g[[c for c in columnas if c in g.columns] + ["geometry"]].to_crs(4326).to_json(drop_id=True, default=str))
    for f in d["features"]:
        if f["geometry"]:
            f["geometry"]["coordinates"] = _redondear(f["geometry"]["coordinates"])
    return d


def _ruta_repo(rel: str | None, base: Path | None = None) -> Path | None:
    if not rel:
        return None
    p = Path(rel)
    for c in ([p] if p.is_absolute() else []) + ([base / p] if base else []) + [cfgmod.raiz_repositorio() / p]:
        if c.exists():
            return c
    return None


def paquete(carpeta: Path) -> dict:
    """Datos del visor de una corrida."""
    import geopandas as gpd
    carpeta = Path(carpeta)
    reg = json.loads((carpeta / "registro.json").read_text(encoding="utf-8"))
    ent = reg.get("entradas") or {}; cfg = reg.get("config") or {}
    res = sorted(carpeta.glob("resumen_*.json"))
    resumen = json.loads(res[-1].read_text(encoding="utf-8")) if res else {}
    met = json.loads((carpeta / "metricas.json").read_text(encoding="utf-8")) if (carpeta / "metricas.json").exists() else {}
    t0 = pd.Timestamp(reg["t_inicio_utc"])
    # perímetros horarios
    per = gpd.read_file(carpeta / "perimetros_horarios.geojson") if (carpeta / "perimetros_horarios.geojson").exists() else None
    if per is not None and len(per):
        per = per.sort_values("hora").reset_index(drop=True)
        if len(per) > MAX_CUADROS:
            k = int(np.ceil(len(per) / MAX_CUADROS))
            per = per[(per.index % k == 0) | (per.index == len(per) - 1)]
    perimetros = geojson_compacto(per, ["hora", "timestamp", "ha"])
    # serie horaria
    serie = []
    p_serie = carpeta / "serie_indicadores.csv"
    if p_serie.exists():
        s = pd.read_csv(p_serie)
        for r in s.itertuples():
            d = int(round(getattr(r, "meteo_viento_dir_deg", 0) or 0))
            serie.append({"h": int(r.hora), "ha": round(float(r.superficie_quemada_ha), 1), "inc": round(float(r.superficie_incremento_ha), 1),
                          "act": int(r.frente_celdas_activas), "V": round(float(r.meteo_viento_kmh), 1), "D": d, "Dtxt": RUMBOS[int(((d % 360) + 11.25) // 22.5) % 16],
                          "HR": round(float(r.meteo_hr_pct)), "T": round(float(r.meteo_temp_c), 1),
                          "m1": round(float(r.meteo_humedad_muerta_1h_pct), 1) if hasattr(r, "meteo_humedad_muerta_1h_pct") else None,
                          "I": round(float(r.frente_intensidad_max_kw_m)) if hasattr(r, "frente_intensidad_max_kw_m") and pd.notna(r.frente_intensidad_max_kw_m) else None})
    # observado, focos y mitigación
    base_caso = None
    if ent.get("caso"):
        from simulador.rutas import raiz_datos
        base_caso = raiz_datos() / "conjunto_prueba" / ent["caso"]
    ins = ent.get("insumos") or {}
    p_obs = _ruta_repo(ins.get("perimetro_observado") or cfg.get("perimetro_observado"), base_caso)
    observado = geojson_compacto(gpd.read_file(p_obs), ["fecha", "fuente", "ha"]) if p_obs else None
    focos = []
    p_focos = _ruta_repo(ins.get("focos") or cfg.get("focos"), base_caso)
    if p_focos:
        f = gpd.read_file(p_focos).to_crs(4326)
        if "hora_deteccion" in f.columns and len(f):
            if per is not None and len(per):
                x0, y0, x1, y1 = per.to_crs(4326).total_bounds
                f = f.cx[x0 - 0.1:x1 + 0.1, y0 - 0.1:y1 + 0.1]
            h = (pd.to_datetime(f["hora_deteccion"], utc=True) - t0).dt.total_seconds() / 3600.0
            f = f.assign(h=h.to_numpy()).sort_values("h")
            if len(f) > MAX_FOCOS:
                f = f.iloc[:: int(np.ceil(len(f) / MAX_FOCOS))]
            focos = [[round(p.x, 5), round(p.y, 5), round(float(hh), 2)] for p, hh in zip(f.geometry, f["h"])]
    extra = None
    p_extra = _ruta_repo((ent.get("mitigacion") or {}).get("barreras_extra"))
    if p_extra:
        extra = geojson_compacto(gpd.read_file(p_extra), ["id", "tipo", "ancho_m"], 5.0)
    evals = [{"h": float(m.get("horas_desde_ignicion") or 0), "iou": m.get("iou")} for m in met.get("espacial", [])]
    ha_ref = next((m.get("ha_ref") for m in met.get("espacial", [])), None) or ((ent.get("referencia") or {}).get("superficie_ha"))
    origen = (f"{ent.get('nombre_evento') or ent['evento']}" if ent.get("evento") else
              (f"caso {ent['caso']} ({ent.get('variante_caso')})" if ent.get("caso") else f"escenario SIM {ent.get('sim')}"))
    t0_local = t0.tz_convert("America/Argentina/San_Luis").strftime("%d/%m/%Y %H:%M")
    mitig = [n for n, v in (("barreras", ent.get("barreras")), ("contención", ent.get("contencion")), ("supresión L03", ent.get("supresion"))) if v]
    meta = {"titulo": f"{origen} — corrida {reg.get('run_id') or carpeta.name}", "run_id": reg.get("run_id") or carpeta.name,
            "subtitulo": f"SIM v{reg.get('version_simulador')} (autómata celular 30 m, Rothermel + Scott & Burgan 40) · modelo {ent.get('modelo_nombre')}"
                         f"{' · variante ' + ent['variante'] if ent.get('variante') else ''} · ignición {t0_local} local"
                         f"{' (hipótesis ' + str(ent['hipotesis_ignicion']) + ', ' + str(ent.get('ignicion')) + ')' if ent.get('evento') else ''}"
                         f" · {'mitigación: ' + ', '.join(mitig) if mitig else 'sin mitigación'}",
            "ha_ref": float(ha_ref) if ha_ref else None,
            "nota": "Perímetros = área afectada acumulada por hora. La línea punteada celeste es la cicatriz observada; los puntos violeta, focos de calor VIIRS hasta la hora elegida."}
    ign = reg.get("igniciones_lonlat") or [{"lon": p["lon"], "lat": p["lat"], "id": p.get("nombre")} for p in ent.get("puntos_ignicion") or []]
    return {"meta": meta, "perimetros": perimetros, "serie": serie, "resumen": resumen, "ignicion": ign, "observado": observado,
            "focos": focos, "extra": extra, "evals": evals}


def exportar(run_id: str, salida: Path | None = None, carpeta: Path | None = None) -> Path:
    carpeta = Path(carpeta) if carpeta else cfgmod.buscar_corrida(run_id)     # resultados/v4.0/[<grupo>/]<run_id>
    if not (carpeta / "registro.json").exists():
        raise FileNotFoundError(f"{carpeta} no tiene registro.json (¿corrida de scripts/correr_escenario.py?)")
    B = paquete(carpeta)
    plantilla = (Path(__file__).resolve().parents[1] / "web" / "visor_plantilla.html").read_text(encoding="utf-8")
    datos = json.dumps(B, ensure_ascii=False, separators=(",", ":"), default=str).replace("</", "<\\/")
    import html as _html
    out = plantilla.replace("__TITULO__", _html.escape(B["meta"]["titulo"])).replace("__DATOS__", datos)
    salida = Path(salida) if salida else carpeta / "visor.html"
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(out, encoding="utf-8")
    print(f"visor: {salida} ({salida.stat().st_size / 1e6:.1f} MB)")
    return salida


def main() -> int:
    ap = argparse.ArgumentParser(description="Visor HTML autónomo de una corrida de v4.0")
    ap.add_argument("--run-id", required=True, help="nombre de la corrida (carpeta de resultados/v4.0 o de resultados/v4.0/<grupo>)")
    ap.add_argument("--salida", help="archivo HTML (por defecto resultados/v4.0/<run_id>/visor.html)")
    a = ap.parse_args()
    exportar(a.run_id, Path(a.salida) if a.salida else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
