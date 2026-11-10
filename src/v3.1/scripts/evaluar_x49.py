"""Métricas de v3.1 (IoU a igual superficie, primeras detecciones VIIRS a tiempo, puntaje) para corridas de v3.1 y de v4.0 de un
evento, con la misma máscara válida (dominio y combustible > 0 de v3) y los mismos focos (hotspots_v3.1). Uso (desde src/v3.1):

  # tabla final: carpetas de corridas (globs relativos a la raíz del repositorio)
  python -I scripts/evaluar_x49.py --evento SL-2022-LATOTORA \
      --carpetas "resultados/v3.1/SL-2022-LATOTORA-*" "resultados/v4.0/SL-2022-LATOTORA/SL-2022-LATOTORA-*" \
      --salida ../../resultados/v3.1/paso2_hora_x49/comparacion_latotora_v31_v40.csv
  # corridas de la búsqueda con v4.0
  python -I scripts/evaluar_x49.py --evento SL-2022-LATOTORA --carpetas "resultados/v4.0/busqueda_punto_x49/SL-2022-LATOTORA/busq_*" \
      --salida ../../resultados/v4.0/busqueda_punto_x49/barrido_punto_unico_latotora_v40.csv

Una corrida de v3.1 se reconoce por `t_llegada_s.tif` (segundos desde t0, etiqueta t_inicio_utc); una de v4.0 por
`hora_llegada_min.tif` + `registro.json` (minutos desde `t_inicio_utc`). Escribe el CSV y un .md con la misma tabla.
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from incendios_sl import config as cfgmod  # noqa: E402
from incendios_sl.grilla import leer_raster  # noqa: E402
from incendios_sl.validation.metricas import iou_igual_superficie, metricas_primera_deteccion  # noqa: E402

COLS = ["version", "carpeta", "ignicion", "hipotesis", "punto", "lon", "lat", "t_inicio_utc", "iou_igual_sup", "horas_hasta_sup", "alcanza_sup",
        "n_primeras", "frac_a_tiempo", "frac_adelantado", "frac_atrasado", "frac_no_alcanzado", "error_mediano_h", "puntaje", "ha_final", "motivo_fin"]


def evaluar(d: Path, ref, valido, g, hs) -> dict | None:
    if (d / "t_llegada_s.tif").exists():
        ver = "v3.1"
        with rasterio.open(d / "t_llegada_s.tif") as s:
            t = s.read(1).astype("float64"); t[t == s.nodata] = np.inf; t0 = pd.Timestamp(s.tags()["t_inicio_utc"])
        reg = json.load(open(d / "registro.json", encoding="utf-8")) if (d / "registro.json").exists() else {}
        ent = reg.get("entradas") or {}
        ign, hip, punto = ent.get("ignicion"), ent.get("hipotesis_ignicion"), (ent.get("puntos_ignicion") or [{}])[0]
        ha_final, motivo = reg.get("ha_quemadas"), reg.get("motivo_fin")
    elif (d / "hora_llegada_min.tif").exists() and (d / "registro.json").exists():
        ver = "v4.0"
        with rasterio.open(d / "hora_llegada_min.tif") as s:
            t = s.read(1).astype("float64") * 60.0; t[~np.isfinite(t)] = np.inf
            if s.shape != ref.shape:
                raise ValueError(f"{d}: grilla {s.shape} distinta de la cicatriz {ref.shape}")
        reg = json.load(open(d / "registro.json", encoding="utf-8")); ent = reg.get("entradas") or {}
        t0 = pd.Timestamp(reg["t_inicio_utc"]).tz_convert("UTC")
        ign, hip = ent.get("ignicion"), ent.get("hipotesis_ignicion")
        p = (reg.get("igniciones_lonlat") or [{}])[0]; punto = {"nombre": p.get("id"), "lon": p.get("lon"), "lat": p.get("lat")}
        ha_final, motivo = reg.get("ha_quemadas"), reg.get("motivo_fin")
    else:
        return None
    f = iou_igual_superficie(t, ref, valido, g.res); tm = metricas_primera_deteccion(t, g, hs, t0); fa = tm.get("frac_a_tiempo")
    return {"version": ver, "carpeta": d.name, "ignicion": ign, "hipotesis": hip, "punto": punto.get("nombre"), "lon": punto.get("lon"), "lat": punto.get("lat"),
            "t_inicio_utc": str(t0), "iou_igual_sup": round(f["iou"], 3), "horas_hasta_sup": round(f["horas"], 1), "alcanza_sup": f["alcanza"],
            "n_primeras": tm.get("n_primeras"), "frac_a_tiempo": None if fa is None else round(fa, 3),
            "frac_adelantado": round(tm.get("frac_adelantado") or 0, 3), "frac_atrasado": round(tm.get("frac_atrasado") or 0, 3),
            "frac_no_alcanzado": round(tm.get("frac_no_alcanzado") or 0, 3), "error_mediano_h": None if tm.get("error_mediano_h") is None else round(tm["error_mediano_h"], 1),
            "puntaje": round((f["iou"] + fa) / 2, 3) if fa is not None else round(f["iou"], 3), "ha_final": ha_final, "motivo_fin": motivo}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evento", required=True); ap.add_argument("--carpetas", nargs="+", required=True, help="globs relativos a la raíz del repositorio")
    ap.add_argument("--salida", required=True)
    a = ap.parse_args()
    EV = a.evento; D = cfgmod.dir_entradas(); R = cfgmod.raiz_repositorio()
    ref, g, _ = leer_raster(D / "eventos" / EV / f"cicatriz_referencia_{EV}.tif"); ref = ref == 1
    dom = cfgmod.cargar_dominio(cfgmod.cargar_evento(EV)["dominio"])["id"]
    valido = (leer_raster(D / "grilla" / f"mascara_dominio_{dom}.tif")[0] == 1) & (leer_raster(D / "combustibles" / EV / f"combustible_clase_{EV}.tif")[0] > 0)
    hs = pd.read_csv(cfgmod.dir_catalogo() / "hotspots_v3.1" / f"viirs_{EV}.csv")
    filas = []
    for patron in a.carpetas:
        for d in sorted(glob.glob(str(R / patron))):
            r = evaluar(Path(d), ref, valido, g, hs)
            if r:
                filas.append(r)
    if not filas:
        print("ninguna corrida evaluable en", a.carpetas); return 1
    df = pd.DataFrame(filas, columns=COLS).sort_values("puntaje", ascending=False)
    sal = Path(a.salida); sal.parent.mkdir(parents=True, exist_ok=True); df.to_csv(sal, index=False)
    md = "| " + " | ".join(COLS) + " |\n|" + "---|" * len(COLS) + "\n" + "\n".join("| " + " | ".join(str(r[c]) for c in COLS) + " |" for _, r in df.iterrows()) + "\n"
    sal.with_suffix(".md").write_text(md, encoding="utf-8")
    pd.set_option("display.width", 250)
    print(df[["version", "carpeta", "punto", "t_inicio_utc", "iou_igual_sup", "horas_hasta_sup", "frac_a_tiempo", "frac_adelantado", "frac_atrasado", "error_mediano_h", "puntaje", "ha_final"]].head(25).to_string(index=False))
    print("salida:", sal)
    return 0


if __name__ == "__main__":
    sys.exit(main())
