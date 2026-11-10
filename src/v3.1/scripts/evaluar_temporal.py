"""Evalúa corridas ya hechas (de cualquier versión) con las métricas de v3.1: forma (IoU a igual superficie) y velocidad
(primeras detecciones VIIRS de catalogo/hotspots_v3.1, docs/v3.1/01).

Uso:
  python scripts/evaluar_temporal.py --corridas ../../resultados/v3.0/SL-2022-RENCA-20220906-h0-alt1-librev2 [...] --salida tabla.csv
  python scripts/evaluar_temporal.py --lista corridas.txt --salida ../../resultados/v3.1/evaluacion_temporal/tabla.csv
Cada corrida necesita t_llegada_s.tif (con la etiqueta t_inicio_utc) y metricas.json o registro.json (evento).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from incendios_sl import config as cfgmod  # noqa: E402
from incendios_sl.grilla import Grilla, leer_raster  # noqa: E402
from incendios_sl.validation.metricas import iou_igual_superficie, metricas_primera_deteccion  # noqa: E402


def focos_evento(evento: str) -> pd.DataFrame | None:
    p = cfgmod.dir_catalogo() / "hotspots_v3.1" / f"viirs_{evento}.csv"
    d = pd.read_csv(p) if p.exists() and p.stat().st_size > 10 else None
    return d if d is not None and len(d) else None


def evaluar_corrida(d: Path, ventana_h: float = 13.0) -> dict:
    m = json.load(open(d / "metricas.json", encoding="utf-8")) if (d / "metricas.json").exists() else {}
    reg = json.load(open(d / "registro.json", encoding="utf-8")) if (d / "registro.json").exists() else {}
    evento = m.get("evento") or reg.get("entradas", {}).get("evento")
    with rasterio.open(d / "t_llegada_s.tif") as ds:
        ta = ds.read(1).astype(float); t0 = pd.Timestamp(ds.tags()["t_inicio_utc"])
    ta[ta < 0] = np.inf
    g = Grilla.desde_raster(d / "t_llegada_s.tif")
    E = cfgmod.dir_entradas()
    ref = leer_raster(E / "eventos" / evento / f"cicatriz_referencia_{evento}.tif")[0] == 1
    clase = leer_raster(E / "combustibles" / evento / f"combustible_clase_{evento}.tif")[0]
    masc = leer_raster(next((E / "grilla").glob("mascara_dominio_*.tif")))[0]
    forma = iou_igual_superficie(ta, ref, (masc == 1) & (clase > 0), g.res)
    tmp = metricas_primera_deteccion(ta, g, focos_evento(evento), t0, ventana_h=ventana_h)
    return {"corrida": d.name, "evento": evento, "t_inicio_utc": str(t0), "ignicion": m.get("ignicion"), "modelo": m.get("modelo"),
            "iou_igual_sup": round(forma["iou"], 3), "horas_hasta_sup": round(forma["horas"], 1), "alcanza_sup": forma["alcanza"],
            "n_primeras": tmp.get("n_primeras", 0),
            **{k: (round(tmp[k], 3) if isinstance(tmp.get(k), float) else tmp.get(k)) for k in
               ("frac_a_tiempo", "frac_adelantado", "frac_atrasado", "frac_no_alcanzado", "error_mediano_h", "error_absoluto_medio_h")},
            "_por_pasada": tmp.get("por_pasada")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corridas", nargs="*", default=[]); ap.add_argument("--lista", default=None)
    ap.add_argument("--salida", required=True); ap.add_argument("--ventana-h", type=float, default=13.0)
    a = ap.parse_args()
    dirs = [Path(x) for x in a.corridas] + ([Path(x.strip()) for x in open(a.lista, encoding="utf-8") if x.strip()] if a.lista else [])
    filas = [evaluar_corrida(d, a.ventana_h) for d in dirs]
    sal = Path(a.salida); sal.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(filas)
    df.drop(columns="_por_pasada").to_csv(sal, index=False)
    with open(sal.with_suffix(".por_pasada.json"), "w", encoding="utf-8") as f:
        json.dump({r["corrida"]: r["_por_pasada"] for r in filas}, f, indent=1, ensure_ascii=False)
    pd.set_option("display.width", 250)
    print(df.drop(columns=["_por_pasada", "t_inicio_utc"]).to_string(index=False))
    print("salida:", sal)
    return 0


if __name__ == "__main__":
    sys.exit(main())
