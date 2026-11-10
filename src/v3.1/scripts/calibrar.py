"""Calibración por barrido de parámetros sobre el evento de calibración (SL-2024-LASLAGUNAS).

Parámetros barridos: hipótesis de hora de ignición, factor global k (multiplica la ROS de todas las clases) y
factor del viento a media llama (multiplica el WAF). Función objetivo: IoU con la cicatriz de referencia en el
instante de evaluación elegido (por defecto el primero de la ficha: fin de la propagación principal).
Las corridas se limitan en duración hasta el instante de evaluación para acelerar el barrido.

Uso: python scripts/calibrar.py --evento SL-2024-LASLAGUNAS --hipotesis 0,1,2 --k 0.3,0.5,0.7,1.0 --waf 0.5,1.0 --eval 0
Salida: resultados/v3.1/calibracion_<evento>/barrido.csv y mejor.json
"""
from __future__ import annotations

import argparse
import itertools
import json
import logging
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from incendios_sl import config as cfgmod  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validar import ejecutar_y_evaluar  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--evento", default="SL-2024-LASLAGUNAS")
    ap.add_argument("--hipotesis", default="0,1,2"); ap.add_argument("--k", default="0.3,0.5,0.7,1.0"); ap.add_argument("--waf", default="0.5,1.0")
    ap.add_argument("--eval", type=int, default=0, help="índice del instante de evaluación de la ficha para la función objetivo")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    ev = cfgmod.cargar_evento(a.evento)
    t_eval = pd.Timestamp(ev["fin"]["evaluacion_utc"][a.eval])
    out = cfgmod.dir_resultados() / f"calibracion_{a.evento}"; out.mkdir(parents=True, exist_ok=True)
    filas = []
    combos = list(itertools.product([int(x) for x in a.hipotesis.split(",")], [float(x) for x in a.k.split(",")], [float(x) for x in a.waf.split(",")]))
    print(f"{len(combos)} corridas; evaluación en {t_eval}")
    for i, (h, k, w) in enumerate(combos):
        t0 = pd.Timestamp(ev["inicio"]["hora_utc_hipotesis"][h]); horas = (t_eval - t0).total_seconds() / 3600
        rid = f"calibracion_{a.evento}/h{h}_k{k}_w{w}"
        t = time.time()
        res = ejecutar_y_evaluar(a.evento, h, k, w, rid, figs=False, horas=horas)
        m = [x for x in res["espacial"] if pd.Timestamp(x["t_eval_utc"]) == t_eval][0]
        tp = res["temporal"]
        fila = {"hipotesis": h, "k_global": k, "factor_waf": w, "iou": m["iou"], "dice": m["dice"], "ha_sim": m["ha_sim"], "ha_ref": m["ha_ref"],
                "omision": m["omision"], "comision": m["comision"], "focos_capturados": tp.get("fraccion_capturada_al_fin_del_dia"),
                "desfase_h": tp.get("desfase_mediano_h"), "motivo_fin": res["motivo_fin"], "segundos": round(time.time() - t, 1)}
        filas.append(fila); print(i + 1, fila, flush=True)
        pd.DataFrame(filas).to_csv(out / "barrido.csv", index=False)
    df = pd.DataFrame(filas).sort_values("iou", ascending=False)
    mejor = df.iloc[0].to_dict()
    with open(out / "mejor.json", "w", encoding="utf-8") as f:
        json.dump({"t_eval_utc": str(t_eval), "mejor": mejor, "n_corridas": len(df)}, f, indent=2, ensure_ascii=False, default=str)
    print(df.head(10).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
