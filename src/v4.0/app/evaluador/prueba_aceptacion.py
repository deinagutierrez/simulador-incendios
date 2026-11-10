"""Prueba de aceptación del evaluador externo (protocolo v1.0 §10).

A1 reproduce `SIM/.../las_lagunas_potrerillos_2024/evaluacion.md` (base, 72 h, COE): 89.766,9 ha simuladas, Sørensen 0,343.
A2 (MOD/) no aplica en V.4.
A3 coincide con `CP/validacion/_sintetico/metricas_*.csv` (ToA sintéticos de SM01 y SM05).
A4 casos sintéticos con respuesta conocida (dos círculos desplazados; área de la elipse B1; orientación).

v4.0: A1 y A3 necesitan salidas de la entrega (`crudos.salidas_sim_entrega`, `crudos.conjunto_pruebas`) que no están
en este equipo: si faltan se marcan `no_disponible` y no cuentan para `todas_ok` (que queda en las pruebas corridas).
A4 no necesita datos externos (`prueba_a4()`; la usa test/v4.0/test_banco.py).

Uso (desde src/v4.0): python -I app/evaluador/prueba_aceptacion.py --salida ../../resultados/v4.0/banco/aceptacion_evaluador_v4.0.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import evaluador as ev  # noqa: E402
from rutas import Rutas  # noqa: E402


def cerca(a, b, tol):
    return a is not None and b is not None and abs(a - b) <= tol


def prueba_a4(G=None) -> dict:
    """A4: dos círculos desplazados (IoU teórico), corte a igual superficie de un ToA radial (10 m/min) y elipse B1 de
    500 ha con viento del N (eje al S)."""
    G = G or ev.grilla_dominio()
    T = G.transform
    rows, cols = np.indices(G.shape)
    X = T.c + (cols + 0.5) * T.a; Y = T.f + (rows + 0.5) * T.e
    cx, cy = 3538000.0, 6393000.0
    d = np.hypot(X - cx, Y - cy)
    toa = np.where(d <= 3000, d / 10.0, np.nan)          # 10 m/min
    obs = np.hypot(X - (cx + 600), Y - cy) <= 1500
    t0s = pd.Timestamp("2024-01-01T00:00:00Z")
    res, _ = ev.evaluar(toa, t0s, obs, {"t150": t0s + pd.Timedelta(minutes=150)}, destino=G)
    r_, dd = 1500.0, 600.0
    inter = 2 * r_ * r_ * math.acos(dd / (2 * r_)) - 0.5 * dd * math.sqrt(4 * r_ * r_ - dd * dd)
    iou_teo = inter / (2 * math.pi * r_ * r_ - inter)
    m = res["instantes"]["t150"]; eq = res["igual_superficie"]
    b1, info = ev.elipse_b1((cx, cy), 0.0, 8.0, 500.0, np.ones(G.shape, bool), G)   # viento del N a 8 m/s -> eje al S
    cb = ev.centroide(b1, T)
    return dict(iou_teorico=round(iou_teo, 4), iou_obtenido=round(m["iou"], 4), corte_igual_sup_min=eq["minutos_corte"],
                b1_ha=round(b1.sum() * ev.HA_CELDA, 2), b1_LB=round(info["LB"], 3), b1_centroide_dy_m=round(cb[1] - cy, 1),
                ok=cerca(m["iou"], iou_teo, 0.01) and cerca(b1.sum() * ev.HA_CELDA, 500.0, 0.5) and (cb[1] - cy) < 0 and cerca(eq["minutos_corte"], 150.0, 3.1))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--raiz", default=None)
    ap.add_argument("--salida", required=True)
    a = ap.parse_args(argv)
    RT = Rutas(a.raiz); R = RT.raiz
    G = ev.grilla_dominio()
    out = {}

    # A1 SIM/
    try:
        sal = RT.salidas_sim_entrega / "20261007_120529_las_lagunas_potrerillos_2024_base"
    except FileNotFoundError as e:
        sal = None; out["A1_SIM"] = {"no_disponible": str(e)}
    if sal is not None:
        toa, _, huella = ev.leer_toa(sal / "sim_SM05_2024_LAS_LAGUNAS_POTRERILLOS_simulador_toa.tif", "min", G)
        ref = ev.rasterizar_referencia(gpd.read_file(RT.sim_datos / "conjunto_prueba/las_lagunas_potrerillos_2024/perimetro_observado.geojson"), G, "centro")
        t0 = pd.Timestamp("2024-09-18T18:43:00Z")
        res, _ = ev.evaluar(toa, t0, ref, {"72h": t0 + pd.Timedelta(hours=72)}, region=huella, dominio=huella, destino=G)
        m = res["instantes"]["72h"]
        out["A1_SIM"] = dict(esperado=dict(ha_sim=89766.9, dice=0.343, iou=0.207), obtenido=dict(ha_sim=round(m["ha_sim"], 2), dice=round(m["dice"], 4), iou=round(m["iou"], 4)),
                             ok=cerca(m["ha_sim"], 89766.9, 0.5) and cerca(m["dice"], 0.343, 0.0005) and cerca(m["iou"], 0.207, 0.0005))

    # A2 (MOD/) no aplica en V.4: el proyecto trabaja solo con SIM/ (2026-10-22). Se conserva en el repo original.

    # A3 CP/ sintético
    try:
        CPd = RT.conjunto_pruebas
    except FileNotFoundError as e:
        CPd = None; out["A3_CP_sintetico"] = {"no_disponible": str(e)}
    a3 = {}
    for caso in (["SM01_2023_LAS_LAGUNAS_Y_LA_AGUADA", "SM05_2024_LAS_LAGUNAS_POTRERILLOS"] if CPd is not None else []):
        ficha = json.loads((CPd / "casos" / caso / "caso.json").read_text(encoding="utf-8"))
        toa, _, huella = ev.leer_toa(CPd / "validacion/_sintetico" / f"sim_{caso}_sintetico_toa.tif", "min", G)
        with rasterio.open(CPd / "casos" / caso / "obs_perimetro_final_30m.tif") as r:
            obs = ev.a_grilla(r.read(1).astype(float), r.transform, r.crs, G, relleno=0) == 1
        t0c = pd.Timestamp(ficha["t0_utc"])
        res, _ = ev.evaluar(toa, t0c, obs, {"ventana": t0c + pd.Timedelta(hours=int(ficha["ventana_sim_horas_sugerida"]))}, region=huella, dominio=huella, destino=G)
        m = res["instantes"]["ventana"]
        cp = pd.read_csv(CPd / "validacion/_sintetico" / f"metricas_{caso}.csv")
        cpv = {r_.metrica: r_.valor for r_ in cp[cp.hora.isna()].itertuples()}
        ok = all(cerca(m[k], float(cpv[k]), 1e-9) for k in ["dice", "iou", "comision", "omision"]) and cerca(m["ha_sim"], float(cpv["ha_sim"]), 1e-6)
        a3[caso] = dict(esperado={k: float(cpv[k]) for k in ["dice", "iou", "ha_sim", "ha_obs"]}, obtenido={k: m[k] for k in ["dice", "iou", "ha_sim"]} | {"ha_obs": m["ha_obs"]}, ok=ok)
    if CPd is not None:
        out["A3_CP_sintetico"] = a3 | {"ok": all(v["ok"] for v in a3.values())}

    # A4 sintéticos
    out["A4_sintetico"] = prueba_a4(G)
    out["todas_ok"] = all(v["ok"] for v in out.values() if isinstance(v, dict) and "ok" in v)
    out["no_disponibles"] = [k for k, v in out.items() if isinstance(v, dict) and "no_disponible" in v]
    out["evaluador_sha256"] = ev.sha256(Path(ev.__file__))
    Path(R / a.salida).write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps(out, indent=1, ensure_ascii=False, default=str))
    return 0 if out["todas_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
