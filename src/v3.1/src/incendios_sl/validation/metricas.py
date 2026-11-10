"""Métricas de validación espacial (cicatriz final) y temporal (focos de calor diarios).

Dominio de comparación: celdas dentro de la máscara del dominio y con combustible (las celdas no combustibles
no pueden quemarse en el modelo ni figuran como quemadas en la referencia salvo error de clasificación; se
informa aparte cuántas celdas de referencia caen en no combustible).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..grilla import Grilla


def mascara_simulada(t_arr: np.ndarray, t_eval_s: float) -> np.ndarray:
    return np.isfinite(t_arr) & (t_arr >= 0) & (t_arr <= t_eval_s)


def metricas_espaciales(sim: np.ndarray, ref: np.ndarray, valido: np.ndarray, res_m: float) -> dict[str, Any]:
    """IoU, Dice, superficies, diferencias, omisión y comisión sobre el dominio de comparación `valido`."""
    s = sim & valido; r = ref & valido
    inter = int((s & r).sum()); uni = int((s | r).sum())
    ns = int(s.sum()); nr = int(r.sum()); ha = res_m ** 2 / 1e4
    return {
        "celdas_sim": ns, "celdas_ref": nr, "ha_sim": ns * ha, "ha_ref": nr * ha,
        "diferencia_abs_ha": (ns - nr) * ha, "diferencia_rel": (ns - nr) / nr if nr else None,
        "interseccion_ha": inter * ha, "union_ha": uni * ha,
        "iou": inter / uni if uni else None, "dice": 2 * inter / (ns + nr) if (ns + nr) else None,
        "omision": 1 - inter / nr if nr else None, "comision": 1 - inter / ns if ns else None,
        "celdas_ref_fuera_de_valido": int((ref & ~valido).sum()),
    }


def evaluar_tiempos(t_arr: np.ndarray, ref: np.ndarray, valido: np.ndarray, res_m: float, t_inicio: pd.Timestamp,
                    tiempos_utc: list[str]) -> list[dict[str, Any]]:
    out = []
    for t in tiempos_utc:
        te = (pd.Timestamp(t) - t_inicio).total_seconds()
        m = metricas_espaciales(mascara_simulada(t_arr, te), ref, valido, res_m)
        m["t_eval_utc"] = str(pd.Timestamp(t)); m["horas_desde_ignicion"] = te / 3600
        out.append(m)
    return out


def metricas_temporales(t_arr: np.ndarray, g: Grilla, hotspots: pd.DataFrame, t_inicio: pd.Timestamp, tz_local: str = "America/Argentina/San_Luis",
                        tolerancia_m: float = 375.0) -> dict[str, Any]:
    """Acuerdo con focos de calor diarios.

    Para cada foco (lon, lat, fecha, hora de adquisición si existe) se toma la celda más cercana y las celdas en un
    radio `tolerancia_m` (resolución del sensor); el foco se considera "capturado al día d" si alguna celda de ese
    entorno tiene t_llegada ≤ fin del día local d. Se informa por día la fracción capturada, la fracción capturada
    con retraso (quemada en la simulación después del día de detección) y, cuando hay hora de adquisición, la
    mediana del desfase (horas) entre la llegada simulada y la detección."""
    if hotspots is None or len(hotspots) == 0:
        return {"disponible": False}
    hs = hotspots.copy()
    r, c = g.lonlat_a_rc(hs["lon"].to_numpy(), hs["lat"].to_numpy())
    hs["fila"] = r; hs["col"] = c
    hs = hs[g.dentro(hs.fila, hs.col)]
    k = int(np.ceil(tolerancia_m / g.res))
    filas = []
    t_min = np.full(len(hs), np.inf)
    for i, (fi, ci) in enumerate(zip(hs.fila.to_numpy(), hs.col.to_numpy())):
        v = t_arr[max(0, fi - k):fi + k + 1, max(0, ci - k):ci + k + 1]
        v = v[np.isfinite(v)]
        if v.size:
            t_min[i] = v.min()
    hs["t_sim_min_s"] = t_min
    fechas = pd.to_datetime(hs["date"]).dt.tz_localize(tz_local)
    fin_dia = (fechas + pd.Timedelta(days=1)).dt.tz_convert("UTC")
    hs["fin_dia_s"] = (fin_dia - t_inicio).dt.total_seconds()
    if "acq_time_s" in hs and hs["acq_time_s"].notna().any():
        det = pd.to_datetime(hs["date"]).dt.tz_localize("UTC") + pd.to_timedelta(hs["acq_time_s"].fillna(0), unit="s")
        hs["t_det_s"] = (det - t_inicio).dt.total_seconds()
    else:
        hs["t_det_s"] = np.nan
    res: dict[str, Any] = {"disponible": True, "n_focos": int(len(hs)), "por_dia": []}
    for d, grp in hs.groupby("date"):
        cap = np.isfinite(grp.t_sim_min_s)
        a_tiempo = cap & (grp.t_sim_min_s <= grp.fin_dia_s)
        desf = (grp.t_sim_min_s - grp.t_det_s)[cap & grp.t_det_s.notna()] / 3600
        res["por_dia"].append({"fecha": str(d), "n": int(len(grp)), "fraccion_capturada_total": float(cap.mean()),
                               "fraccion_capturada_al_fin_del_dia": float(a_tiempo.mean()),
                               "desfase_mediano_h": float(desf.median()) if len(desf) else None})
    cap = np.isfinite(hs.t_sim_min_s)
    res["fraccion_capturada_total"] = float(cap.mean())
    res["fraccion_capturada_al_fin_del_dia"] = float((cap & (hs.t_sim_min_s <= hs.fin_dia_s)).mean())
    d = (hs.t_sim_min_s - hs.t_det_s)[cap & hs.t_det_s.notna()] / 3600
    res["desfase_mediano_h"] = float(d.median()) if len(d) else None
    res["desfase_p10_p90_h"] = [float(d.quantile(0.1)), float(d.quantile(0.9))] if len(d) else None
    return res


def iou_igual_superficie(t_arr: np.ndarray, ref: np.ndarray, valido: np.ndarray, res_m: float) -> dict[str, Any]:
    """IoU en el instante en que la simulación alcanza la superficie de la cicatriz (las n_ref primeras celdas en arder):
    mide la forma con independencia de la velocidad (v3.1, docs/v3.1/01)."""
    R = ref & valido; nR = int(R.sum())
    t = np.where(valido & np.isfinite(t_arr) & (t_arr >= 0), t_arr, np.inf); fin = np.isfinite(t); n = int(fin.sum())
    if n >= nR:
        t_star = float(np.partition(t[fin], nR - 1)[nR - 1]); S = fin & (t <= t_star); alcanza = True
    else:
        t_star = float(t[fin].max()) if n else 0.0; S = fin; alcanza = False
    inter = int((S & R).sum()); uni = nR + int(S.sum()) - inter
    return {"iou": inter / uni if uni else None, "omision": 1 - inter / nR if nR else None, "horas": t_star / 3600,
            "alcanza": alcanza, "ha_sim": int(S.sum()) * res_m ** 2 / 1e4, "ha_ref": nR * res_m ** 2 / 1e4}


def metricas_primera_deteccion(t_arr: np.ndarray, g: Grilla, hotspots: pd.DataFrame, t_inicio: pd.Timestamp,
                               tolerancia_m: float = 375.0, ventana_h: float = 13.0, holgura_h: float = 1.0) -> dict[str, Any]:
    """Velocidad de propagación contra las pasadas satelitales (v3.1, docs/v3.1/01).

    Se usan sólo las **primeras detecciones** de cada lugar (focos sin otro foco anterior a ≤ tolerancia_m): un píxel que
    sigue ardiendo en pasadas posteriores no dice cuándo llegó el fuego. El fuego llegó a ese lugar entre la pasada anterior
    y la detección; con dos satélites/pasadas por día la pasada anterior está, como mucho, `ventana_h` antes. Por foco:
    t_sim = llegada simulada más temprana en el entorno de tolerancia_m; clase
      a_tiempo    t_det − ventana_h ≤ t_sim ≤ t_det + holgura_h
      adelantado  t_sim < t_det − ventana_h       (el modelo llega antes: propagación demasiado rápida)
      atrasado    t_sim > t_det + holgura_h       (demasiado lenta, o ignición posterior a la detección)
      no_alcanzado  la simulación nunca llega
    y un error con signo (h): 0 a tiempo, t_sim − (t_det − ventana_h) si adelantado, t_sim − t_det si atrasado."""
    if hotspots is None or len(hotspots) == 0:
        return {"disponible": False}
    hs = hotspots.copy()
    hs["t_det_s"] = ((pd.to_datetime(hs["date"]).dt.tz_localize("UTC") + pd.to_timedelta(hs["acq_time_s"], unit="s")) - t_inicio).dt.total_seconds()
    hs = hs.sort_values("t_det_s").reset_index(drop=True)
    r, c = g.lonlat_a_rc(hs["lon"].to_numpy(), hs["lat"].to_numpy())
    hs["fila"] = r; hs["col"] = c
    hs = hs[g.dentro(hs.fila, hs.col)].reset_index(drop=True)
    k = int(np.ceil(tolerancia_m / g.res))
    # primeras detecciones: se recorre en orden temporal marcando el entorno de los focos ya vistos; el entorno se marca al
    # cerrar cada pasada, así dos focos de la misma pasada a < tolerancia son ambos "primeros"
    visto = np.zeros(t_arr.shape, bool); primera = np.zeros(len(hs), bool)
    for i, (fi, ci) in enumerate(zip(hs.fila.to_numpy(), hs.col.to_numpy())):
        primera[i] = not visto[fi, ci]
        if i + 1 == len(hs) or hs.t_det_s.iat[i + 1] != hs.t_det_s.iat[i]:
            for j in np.nonzero(hs.t_det_s.to_numpy() == hs.t_det_s.iat[i])[0]:
                fj, cj = hs.fila.iat[j], hs.col.iat[j]
                visto[max(0, fj - k):fj + k + 1, max(0, cj - k):cj + k + 1] = True
    hs = hs[primera].copy()
    t_sim = np.full(len(hs), np.inf)
    for i, (fi, ci) in enumerate(zip(hs.fila.to_numpy(), hs.col.to_numpy())):
        v = t_arr[max(0, fi - k):fi + k + 1, max(0, ci - k):ci + k + 1]
        v = v[np.isfinite(v) & (v >= 0)]
        if v.size:
            t_sim[i] = v.min()
    hs["t_sim_s"] = t_sim
    lo = hs.t_det_s - ventana_h * 3600; hi = hs.t_det_s + holgura_h * 3600
    alc = np.isfinite(hs.t_sim_s)
    hs["clase"] = np.select([~alc, hs.t_sim_s < lo, hs.t_sim_s > hi], ["no_alcanzado", "adelantado", "atrasado"], "a_tiempo")
    hs["error_h"] = np.select([~alc, hs.t_sim_s < lo, hs.t_sim_s > hi], [np.nan, (hs.t_sim_s - lo) / 3600, (hs.t_sim_s - hs.t_det_s) / 3600], 0.0)
    frac = hs["clase"].value_counts(normalize=True)
    res: dict[str, Any] = {"disponible": True, "n_primeras": int(len(hs)), "ventana_h": ventana_h, "tolerancia_m": tolerancia_m}
    for cl in ("a_tiempo", "adelantado", "atrasado", "no_alcanzado"):
        res[f"frac_{cl}"] = float(frac.get(cl, 0.0))
    e = hs.error_h.dropna()
    res["error_mediano_h"] = float(e.median()) if len(e) else None
    res["error_absoluto_medio_h"] = float(e.abs().mean()) if len(e) else None
    res["por_pasada"] = [{"t_det_utc": str(t_inicio + pd.Timedelta(seconds=float(t))), "n": int(len(x)),
                          **{cl: int((x.clase == cl).sum()) for cl in ("a_tiempo", "adelantado", "atrasado", "no_alcanzado")},
                          "error_mediano_h": float(x.error_h.median()) if x.error_h.notna().any() else None}
                         for t, x in hs.groupby("t_det_s")]
    return res
