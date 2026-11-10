"""Reevaluación a posteriori de un barrido de calibración a partir de los rasters de tiempo de llegada guardados.

Calcula, para cada corrida, IoU/Dice/omisión/comisión en varios instantes y el acuerdo con los focos de calor,
y genera una tabla (CSV) y un gráfico de IoU por hipótesis, k y factor WAF.
Uso: python scripts/evaluar_barrido.py --evento SL-2024-LASLAGUNAS [--tiempos 2024-09-21T03:00Z,2024-09-22T03:00Z,2024-09-25T03:00Z]
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from incendios_sl import config as cfgmod  # noqa: E402
from incendios_sl.data.preparar_dominio import grilla_dominio  # noqa: E402
from incendios_sl.grilla import leer_raster  # noqa: E402
from incendios_sl.validation.metricas import evaluar_tiempos, metricas_temporales  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--evento", default="SL-2024-LASLAGUNAS"); ap.add_argument("--tiempos", default=None)
    a = ap.parse_args(argv)
    ev = cfgmod.cargar_evento(a.evento); dom = cfgmod.cargar_dominio(ev["dominio"]); g = grilla_dominio(dom)
    tiempos = a.tiempos.split(",") if a.tiempos else ev["fin"]["evaluacion_utc"]
    ref, _, _ = leer_raster(cfgmod.dir_entradas() / "eventos" / a.evento / f"cicatriz_referencia_{a.evento}.tif")
    mascara, _, _ = leer_raster(cfgmod.dir_entradas() / "grilla" / f"mascara_dominio_{dom['id']}.tif")
    clase, _, _ = leer_raster(cfgmod.dir_entradas() / "combustibles" / a.evento / f"combustible_clase_{a.evento}.tif")
    valido = (mascara == 1) & (clase > 0)
    hs_path = cfgmod.dir_catalogo() / "hotspots" / f"viirs_{a.evento}.csv"
    hs = pd.read_csv(hs_path) if hs_path.exists() and hs_path.stat().st_size > 10 else None
    if hs is None or len(hs) == 0:
        hs_path = cfgmod.dir_catalogo() / "hotspots" / f"modis_{a.evento}.csv"; hs = pd.read_csv(hs_path) if hs_path.exists() else None; tol = 1000.0
    else:
        tol = 375.0
    filas = []
    for d in sorted(glob.glob(str(cfgmod.dir_resultados() / f"calibracion_{a.evento}" / "h*_k*_w*"))):
        m = re.search(r"h(\d+)_k([\d.]+)_w([\d.]+)$", d)
        if not m or not (Path(d) / "t_llegada_s.tif").exists():
            continue
        h, k, w = int(m.group(1)), float(m.group(2)), float(m.group(3))
        ta, _, nd = leer_raster(Path(d) / "t_llegada_s.tif"); ta = np.where(ta == nd, np.inf, ta).astype(np.float32)
        t0 = pd.Timestamp(ev["inicio"]["hora_utc_hipotesis"][h])
        reg = json.load(open(Path(d) / "registro.json", encoding="utf-8"))
        t_sim_fin = reg["t_simulado_s"]
        fila = {"hipotesis": h, "k_global": k, "factor_waf": w, "motivo_fin": reg["motivo_fin"]}
        for mt in evaluar_tiempos(ta, ref == 1, valido, g.res, t0, [t for t in tiempos if (pd.Timestamp(t) - t0).total_seconds() <= t_sim_fin + 1]):
            tag = pd.Timestamp(mt["t_eval_utc"]).strftime("%m%dT%H")
            fila[f"iou_{tag}"] = round(mt["iou"], 4); fila[f"ha_sim_{tag}"] = round(mt["ha_sim"]); fila[f"omi_{tag}"] = round(mt["omision"], 3); fila[f"com_{tag}"] = round(mt["comision"], 3)
        if hs is not None:
            tp = metricas_temporales(ta, g, hs, t0, tolerancia_m=tol)
            fila["focos_fin_dia"] = round(tp["fraccion_capturada_al_fin_del_dia"], 3); fila["focos_total"] = round(tp["fraccion_capturada_total"], 3)
            fila["desfase_h"] = None if tp["desfase_mediano_h"] is None else round(tp["desfase_mediano_h"], 1)
        filas.append(fila)
    df = pd.DataFrame(filas)
    out = cfgmod.dir_resultados() / f"calibracion_{a.evento}"
    df.to_csv(out / "barrido_reevaluado.csv", index=False)
    pd.set_option("display.width", 300); pd.set_option("display.max_columns", 40)
    print(df.to_string(index=False))
    # gráfico: IoU en cada instante vs k, una curva por waf, un panel por hipótesis
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    cols = [c for c in df.columns if c.startswith("iou_")]
    hips = sorted(df.hipotesis.unique()); fig, axes = plt.subplots(len(cols), len(hips), figsize=(5 * len(hips), 3.6 * len(cols)), squeeze=False)
    for i, c in enumerate(cols):
        for j, h in enumerate(hips):
            ax = axes[i, j]; sub = df[df.hipotesis == h]
            for w, s in sub.groupby("factor_waf"):
                s = s.sort_values("k_global"); ax.plot(s.k_global, s[c], "o-", label=f"WAF×{w}")
            ax.set_title(f"hipótesis {h} ({ev['inicio']['hora_utc_hipotesis'][h][11:16]} UTC) — {c}"); ax.set_xlabel("k global"); ax.set_ylabel("IoU"); ax.grid(alpha=0.3); ax.legend(fontsize=8)
    plt.tight_layout(); fig.savefig(out / "barrido_iou.png", dpi=100)
    print("guardado", out / "barrido_reevaluado.csv", out / "barrido_iou.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
