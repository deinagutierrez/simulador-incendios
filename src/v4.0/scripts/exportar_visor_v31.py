"""Visor de v3.1 (mapa Leaflet con tiempo de llegada, relieve, combustibles, cicatriz, infraestructura, focos, línea de
tiempo y tabla de ajuste) para una corrida de v4.0.

Uso (desde src/v4.0):
  python -I scripts/exportar_visor_v31.py --run-id SL-2023-CHACRASOCT-20231017-h4-snmf-libre [--salida <html>]

Traduce las salidas de SIM a lo que lee `src/v3.1/scripts/exportar_visor.py` y lo llama tal cual:

| v3.1 espera | se arma desde (carpeta de la corrida v4.0) |
|---|---|
| `t_llegada_s.tif` (s desde t0, nodata -1) | `hora_llegada_min.tif` x 60 (NaN -> -1) |
| `serie_horaria.csv` (time_utc, t_s, ha_quemadas, celdas_activas, T, HR, viento m/s, dirección, m_1h_pct) | `serie_indicadores.csv` |
| `metricas.json` (espacial: ha_sim, ha_ref, iou, dice, t_eval_utc, horas_desde_ignicion) | el mismo `metricas.json` |
| `registro.json` (version_codigo, pasos, segundos_cpu, t_simulado_utc/_s, ha_quemadas, fecha_corrida, entradas) | `registro.json` + `resumen_*.json` |

La ficha del evento se toma de `escenarios/v3.1/eventos` si existe y, si no, de `escenarios/v4.0/eventos` (mismo formato).
Por defecto escribe `visor.html` en la carpeta de la corrida; el visor nativo de SIM, si ya estaba, queda como `visor_sim.html`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

AQUI = Path(__file__).resolve()
sys.path.insert(0, str(AQUI.parents[1] / "src"))
from incendios_sl import config as cfg4  # noqa: E402

V31 = AQUI.parents[2] / "v3.1"


def preparar_insumos_v31(carpeta: Path, destino: Path) -> str:
    """Escribe en `destino/<run_id>/` lo que lee el exportador de v3.1. Devuelve el run_id."""
    reg = json.loads((carpeta / "registro.json").read_text(encoding="utf-8")); ent = reg["entradas"]
    res = sorted(carpeta.glob("resumen_*.json"))
    resumen = json.loads(res[-1].read_text(encoding="utf-8")) if res else {}
    run_id = reg.get("run_id") or carpeta.name
    d = destino / run_id; d.mkdir(parents=True, exist_ok=True)
    t0 = pd.Timestamp(reg["t_inicio_utc"]).tz_convert("UTC")
    # tiempo de llegada
    with rasterio.open(carpeta / "hora_llegada_min.tif") as s:
        h = s.read(1).astype("float64"); perfil = s.profile
    t = np.where(np.isfinite(h) & (h >= 0), h * 60.0, -1.0).astype("float32")
    perfil.update(dtype="float32", nodata=-1.0, count=1, compress="deflate")
    with rasterio.open(d / "t_llegada_s.tif", "w", **perfil) as dst:
        dst.write(t, 1); dst.update_tags(t_inicio_utc=str(t0), unidades="segundos desde t_inicio", origen="hora_llegada_min.tif de SIM v4.0")
    # serie horaria
    si = pd.read_csv(carpeta / "serie_indicadores.csv")
    serie = pd.DataFrame({
        "time_utc": [str(t0 + pd.Timedelta(hours=float(x))) for x in si["hora"]], "t_s": si["hora"].astype(float) * 3600.0,
        "celdas_quemadas": si.get("celdas_quemado", 0), "ha_quemadas": si["superficie_quemada_ha"], "celdas_activas": si["frente_celdas_activas"],
        "temperature_2m": si["meteo_temp_c"], "relative_humidity_2m": si["meteo_hr_pct"], "wind_speed_10m": si["meteo_viento_kmh"] / 3.6,
        "wind_direction_10m": si["meteo_viento_dir_deg"], "m_1h_pct": si.get("meteo_humedad_muerta_1h_pct", np.nan),
        "intensidad_max_kw_m": si.get("frente_intensidad_max_kw_m", np.nan)})
    serie = serie[serie["t_s"] > 0] if len(serie) > 1 else serie      # v3.1 empieza en la hora 1
    serie.to_csv(d / "serie_horaria.csv", index=False)
    # métricas y registro
    if (carpeta / "metricas.json").exists():
        (d / "metricas.json").write_bytes((carpeta / "metricas.json").read_bytes())
    ign = reg.get("igniciones_lonlat") or [{"id": p.get("nombre"), "lon": p["lon"], "lat": p["lat"]} for p in ent.get("puntos_ignicion") or []]
    costo = resumen.get("costo") or {}
    reg31 = {"version_codigo": f"SIM {reg.get('version_simulador') or reg.get('version_codigo')} (v4.0)",
             "pasos": reg.get("sub_pasos") or costo.get("sub_pasos"), "segundos_cpu": reg.get("segundos") or costo.get("segundos"),
             "t_simulado_s": reg.get("t_simulado_s") or float(resumen.get("horas_simuladas", 0)) * 3600.0,
             "t_simulado_utc": str(pd.Timestamp(reg.get("t_simulado_utc") or resumen.get("t_fin_simulado_utc")).tz_convert("UTC")),
             "ha_quemadas": reg.get("ha_quemadas") or (resumen.get("superficie") or {}).get("ha_quemadas_final"),
             "fecha_corrida": reg.get("fecha_corrida"), "motivo_fin": reg.get("motivo_fin"), "motivo_fin_texto": reg.get("motivo_fin_texto"),
             "entradas": {"evento": ent["evento"], "dominio": ent["dominio"], "t_inicio_utc": str(t0), "hipotesis_ignicion": ent.get("hipotesis_ignicion"),
                          "ignicion": ent.get("ignicion"), "modelo_nombre": ent.get("modelo_nombre"), "variante": ent.get("variante"),
                          "igniciones": [{"nombre": p.get("id"), "lon": p["lon"], "lat": p["lat"]} for p in ign]}}
    (d / "registro.json").write_text(json.dumps(reg31, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return run_id


def exportar(run_id: str, salida: Path | None = None) -> Path:
    carpeta = cfg4.buscar_corrida(run_id)
    if not (carpeta / "hora_llegada_min.tif").exists():
        raise FileNotFoundError(f"{carpeta} no tiene hora_llegada_min.tif")
    staging = carpeta / "_visor_v31"
    rid = preparar_insumos_v31(carpeta, staging)
    reg = json.loads((carpeta / "registro.json").read_text(encoding="utf-8")); ent = reg["entradas"]
    # el exportador de v3.1 lee resultados, escenarios y datos por sus propias rutas: resultados -> staging, escenarios -> v3.1 o v4.0
    esc31 = cfg4.raiz_repositorio() / "escenarios" / "v3.1"
    os.environ["INCENDIOS_SL_RESULTADOS"] = str(staging)
    os.environ["INCENDIOS_SL_ESCENARIOS"] = str(esc31 if (esc31 / "eventos" / f"{ent['evento']}.yaml").exists() else cfg4.dir_escenarios())
    sys.path.insert(0, str(V31 / "src")); sys.path.insert(0, str(V31 / "scripts"))
    for m in [m for m in list(sys.modules) if m == "incendios_sl" or m.startswith("incendios_sl.")]:
        del sys.modules[m]                       # que el visor importe el paquete de v3.1, no el de v4.0
    import exportar_visor as ev31  # noqa: E402  (src/v3.1/scripts)
    salida = Path(salida) if salida else carpeta / "visor.html"
    if salida.exists() and salida.name == "visor.html" and not (carpeta / "visor_sim.html").exists() and "__DATOS__" not in salida.read_text(encoding="utf-8")[:0]:
        txt = salida.read_text(encoding="utf-8")
        if '"perimetros"' in txt[:200000] and "sombras" not in txt[:200000]:
            salida.rename(carpeta / "visor_sim.html")
    out = ev31.exportar(rid, salida)
    html = out.read_text(encoding="utf-8")
    html = html.replace("Autómata celular a 30 m, sin combate.",
                        f"SIM v4.0 (autómata celular a 30 m, Rothermel + Scott & Burgan 40), modelo {ent.get('modelo_nombre')}"
                        f"{', variante ' + str(ent.get('variante')) if ent.get('variante') else ''}, sin combate.")
    out.write_text(html, encoding="utf-8")
    import shutil
    shutil.rmtree(staging, ignore_errors=True)   # los insumos traducidos son temporales
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Visor de v3.1 para una corrida de v4.0")
    ap.add_argument("--run-id", required=True); ap.add_argument("--salida")
    a = ap.parse_args()
    exportar(a.run_id, Path(a.salida) if a.salida else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
