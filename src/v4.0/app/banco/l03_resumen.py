"""Resumen de M1-L03 sobre los eventos de desarrollo (protocolo v1.3): por evento y por valor de P, la forma
(IoU a igual superficie o, si el modelo no alcanza A_obs, IoU de la huella final, §7), L y Δt contra T80, y la función
objetivo de §9: (1 − IoU) + 0,5·|L| + 0,5·min(|Δt|/24, 3) (instante degenerado → solo forma; Δt censurado → 3).

EXPLORATORIO: todos los eventos ya fueron vistos (Fase 1 usada). Esto NO es la calibración de la Fase 2, que exige
validación cruzada dejando un evento afuera.

CONFUSIÓN CONOCIDA: P = 0 es M1 de la Fase 1 (protocolo v1.2, sin parada SNMF, otra duración y otro commit), no "L03 con
P = 0"; y 41914 no tiene P500/P1000 (corridas incompletas), así que n difiere entre valores de P.

v4.0: la carpeta de cada corrida se resuelve con `registro.leer` (relativa al banco o ruta vieja reubicada); `--modelo`
elige las corridas por modelo de parámetros (`V.4` por defecto = las de V.4); con otro modelo las salidas llevan el
sufijo `_<modelo>`.

Uso (desde src/v4.0):  python -I app/banco/l03_resumen.py [--modelo V.4]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent)); sys.path.insert(0, str(AQUI.parent / "evaluador")); sys.path.insert(0, str(AQUI))
from rutas import Rutas  # noqa: E402
import registro  # noqa: E402


def objetivo(iou, L, dt, degenerado):
    forma = 1 - iou
    if degenerado:
        return forma
    t = 3.0 if (dt is None or not math.isfinite(dt)) else min(abs(dt) / 24, 3.0)
    return forma + 0.5 * abs(L) + 0.5 * t


def main(argv=None):
    import rasterio
    import evaluador as ev
    ap = argparse.ArgumentParser()
    ap.add_argument("--raiz", default=None, help="carpeta src/v4.0 (por defecto, la de este código)")
    ap.add_argument("--modelo", default=registro.MODELO_V4)
    a = ap.parse_args(argv)
    RT = Rutas(a.raiz); B = RT.banco
    suf = "" if a.modelo == registro.MODELO_V4 else f"_{a.modelo}"
    with rasterio.open(RT.mascara_dominio) as s:
        dominio = s.read(1) == 1
    reg = registro.leer(RT)
    reg = reg[(reg.estado == "ok") & (reg.modelo == a.modelo)]
    filas = []
    for r in reg.itertuples():
        caso = B / "casos" / r.id_evento / "caso.json"
        if not caso.exists():
            continue
        c = json.loads(caso.read_text(encoding="utf-8"))
        degen = bool(c["protocolo"]["instante_degenerado"])
        iou = r.iou_eq
        no_alcanza = pd.isna(iou)
        if no_alcanza:
            with rasterio.open(B / "casos" / r.id_evento / "obs_perimetro_final_30m.tif") as s:
                obs = s.read(1) == 1
            with rasterio.open(Path(r.carpeta_abs) / "toa_min.tif") as s:
                iou = ev.comparar(np.isfinite(s.read(1)) & dominio, obs)["iou"]
        P = None
        if "L03_P" in str(r.variante):
            P = float(str(r.variante).split("L03_P")[1])
        elif r.motor == "SIM" and str(r.variante) == "indices_previo":
            P = 0.0                                  # M1 sin supresión (Fase 1)
        else:
            continue
        dt = None if pd.isna(r.dt_h_T80) else float(r.dt_h_T80)
        filas.append(dict(id_evento=r.id_evento, P=P, iou=iou, no_alcanza=no_alcanza, L=r.L_T80, dt_h=dt, degenerado=degen,
                          ha_obs=r.ha_obs, ha_sim_T80=r.ha_sim_T80, objetivo=objetivo(iou, r.L_T80, dt, degen)))
    d = pd.DataFrame(filas).sort_values(["P", "id_evento"])
    d.to_csv(B / f"l03_sensibilidad_por_evento{suf}.csv", index=False, lineterminator="\n")
    res = d.groupby("P").agg(n=("id_evento", "size"), objetivo_medio=("objetivo", "mean"), iou_mediana=("iou", "median"),
                             absL_mediana=("L", lambda x: float(np.median(np.abs(x[~d.loc[x.index, "degenerado"]])))),
                             sesgo_L=("L", lambda x: float(np.median(x[~d.loc[x.index, "degenerado"]]))),
                             no_alcanza=("no_alcanza", "sum")).reset_index()
    res.to_csv(B / f"l03_sensibilidad_resumen{suf}.csv", index=False, lineterminator="\n")
    pd.set_option("display.width", 200)
    print(res.to_string(index=False))
    print(d.pivot_table(index="id_evento", columns="P", values="L").round(2).to_string())


if __name__ == "__main__":
    sys.exit(main())
