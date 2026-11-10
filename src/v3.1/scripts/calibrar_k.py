"""Recalibración de k por grupo de clases de combustible sobre varios eventos (docs/12).

Grupos: A = {1 pastizal, 2 pastura/cultivo, 3 arbustal abierto}, B = {4 arbustal cerrado, 5 bosque abierto},
C = {6 bosque cerrado, 7 plantación}. Objetivo: IoU medio (peso igual por evento) con la cicatriz al primer instante de
evaluación de cada ficha (fin del día de ignición), con la humedad de retardo (modelo_v2) y sin barreras ni contención.
Las corridas se limitan al primer instante para acelerar. Se reanuda desde el CSV si existe.

Uso:
  python scripts/calibrar_k.py --kA 0.15,0.3,0.5 --kB 0.5,1,2 --kC 1,3 \
      --calibracion SL-2024-LASLAGUNAS,SL-2024-MESILLA,SL-2022-RENCA,SL-2022-CHILCAS,SL-2023-AGUADA,SL-2022-PISCUYACU \
      --validacion SL-2022-PUERTAS,SL-2022-PAMPITA,SL-2023-RINCON,SL-2023-CHACRAS
Salida: resultados/v3.1/calibracion_k_v2/{barrido.csv, mejor.json, validacion.csv}
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
from evaluar_v2 import REFERENCIA  # noqa: E402

GRUPOS = {"A": (1, 2, 3), "B": (4, 5), "C": (6, 7)}
# Instante de evaluación usado como objetivo: índice en `evaluacion_utc` de la ficha. Por defecto el primero (fin del día de
# ignición, válido cuando la cicatriz se formó en un día). En los incendios de varios días la cicatriz final no es comparable
# con el primer día: se usa el fin de la propagación principal (Renca y Puertas: índice 1; Las Lagunas: índice 0 = 60 h).
INSTANTE_CAL = {"SL-2022-RENCA": 1, "SL-2022-PUERTAS": 1}


def k_clase(kA: float, kB: float, kC: float) -> dict[int, float]:
    return {c: k for g, k in (("A", kA), ("B", kB), ("C", kC)) for c in GRUPOS[g]}


def correr(ev: str, kc: dict[int, float], rid: str, horas_primer_instante: bool, modelo: str) -> dict:
    ign, hip = REFERENCIA.get(ev, ("snmf", 0))
    e = cfgmod.cargar_evento(ev)
    idx = INSTANTE_CAL.get(ev, 0)
    horas = None
    if horas_primer_instante:
        t0 = pd.Timestamp(e["inicio"]["hora_utc_hipotesis"][hip]); t1 = pd.Timestamp(e["fin"]["evaluacion_utc"][idx])
        horas = (t1 - t0).total_seconds() / 3600
    t = time.time()
    res = ejecutar_y_evaluar(ev, hip, None, 1.0, rid, figs=False, horas=horas, k_clase=kc, ignicion=ign, modelo=modelo, barreras=False, contencion=False)
    e0 = res["espacial"][min(idx, len(res["espacial"]) - 1)]; tp = res.get("temporal", {})
    return {"evento": ev, "ignicion": ign, "t_eval_utc": e0["t_eval_utc"], "iou": e0["iou"], "dice": e0["dice"], "omision": e0["omision"], "comision": e0["comision"],
            "ha_sim": e0["ha_sim"], "ha_ref": e0["ha_ref"], "focos_a_tiempo": tp.get("fraccion_capturada_al_fin_del_dia"), "segundos": round(time.time() - t, 1)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--kA", default="0.15,0.3,0.5"); ap.add_argument("--kB", default="0.5,1,2"); ap.add_argument("--kC", default="1,3")
    ap.add_argument("--calibracion", default="SL-2024-LASLAGUNAS,SL-2024-MESILLA,SL-2022-RENCA,SL-2022-CHILCAS,SL-2023-AGUADA,SL-2022-PISCUYACU")
    ap.add_argument("--validacion", default="SL-2022-PUERTAS,SL-2022-PAMPITA,SL-2023-RINCON,SL-2023-CHACRAS")
    ap.add_argument("--modelo", default="modelo_v2"); ap.add_argument("--solo-validacion", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    out = cfgmod.dir_resultados() / "calibracion_k_v2"; out.mkdir(parents=True, exist_ok=True)
    cal = a.calibracion.split(","); val = a.validacion.split(",")
    csv = out / "barrido.csv"
    filas = pd.read_csv(csv).to_dict("records") if csv.exists() else []
    hechas = {(f["evento"], f["kA"], f["kB"], f["kC"]) for f in filas}
    combos = list(itertools.product([float(x) for x in a.kA.split(",")], [float(x) for x in a.kB.split(",")], [float(x) for x in a.kC.split(",")]))
    if not a.solo_validacion:
        print(f"{len(combos)} combinaciones × {len(cal)} eventos de calibración", flush=True)
        for kA, kB, kC in combos:
            for ev in cal:
                if (ev, kA, kB, kC) in hechas:
                    continue
                rid = f"calibracion_k_v2/{ev}_A{kA}_B{kB}_C{kC}"
                try:
                    fila = correr(ev, k_clase(kA, kB, kC), rid, True, a.modelo) | {"kA": kA, "kB": kB, "kC": kC}
                except Exception as e:  # noqa: BLE001
                    fila = {"evento": ev, "kA": kA, "kB": kB, "kC": kC, "error": str(e)[:200]}
                filas.append(fila); print(fila, flush=True)
                pd.DataFrame(filas).to_csv(csv, index=False)
    df = pd.DataFrame(filas)
    df = df[df.evento.isin(cal)] if "evento" in df else df
    res = df.groupby(["kA", "kB", "kC"]).agg(iou_medio=("iou", "mean"), dice_medio=("dice", "mean"), omision_media=("omision", "mean"),
                                             comision_media=("comision", "mean"), n=("iou", "size")).reset_index().sort_values("iou_medio", ascending=False)
    res.to_csv(out / "resumen_barrido.csv", index=False)
    pd.set_option("display.width", 200)
    print("\nMejores combinaciones (IoU medio del primer día, eventos de calibración):"); print(res.head(10).round(3).to_string(index=False))
    mejor = res.iloc[0]
    kc = k_clase(float(mejor.kA), float(mejor.kB), float(mejor.kC))
    print(f"\nValidación con kA={mejor.kA}, kB={mejor.kB}, kC={mejor.kC} en {val}", flush=True)
    vfilas = []
    for ev in val + cal:
        rid = f"calibracion_k_v2/validacion_{ev}"
        try:
            vfilas.append(correr(ev, kc, rid, True, a.modelo) | {"conjunto": "validacion" if ev in val else "calibracion"})
        except Exception as e:  # noqa: BLE001
            vfilas.append({"evento": ev, "error": str(e)[:200]})
        print(vfilas[-1], flush=True)
    vdf = pd.DataFrame(vfilas); vdf.to_csv(out / "validacion.csv", index=False)
    with open(out / "mejor.json", "w", encoding="utf-8") as f:
        json.dump({"kA": float(mejor.kA), "kB": float(mejor.kB), "kC": float(mejor.kC), "k_clase": {str(k): v for k, v in kc.items()}, "iou_medio_calibracion": float(mejor.iou_medio),
                   "calibracion": cal, "validacion": val, "modelo": a.modelo, "objetivo": "IoU medio al primer instante de evaluación"}, f, indent=2, ensure_ascii=False)
    print(vdf.round(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
