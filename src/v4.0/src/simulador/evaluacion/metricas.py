"""Métricas de evaluación de una simulación contra observaciones."""

from __future__ import annotations

import numpy as np
import pandas as pd
from rasterio import features


def rasterizar(gdf, grilla, umbral_cobertura: float = 0.5) -> np.ndarray:
    """Máscara de celdas con ≥ `umbral_cobertura` de su superficie dentro de los polígonos (supermuestreo 5×)."""
    if gdf is None or not len(gdf):
        return np.zeros(grilla.shape, bool)
    gdf = gdf.to_crs(grilla.crs)
    k = 5
    from affine import Affine
    tr = Affine(grilla.res / k, 0, grilla.xmin, 0, -grilla.res / k, grilla.ymax)
    fino = features.rasterize(((g, 1) for g in gdf.geometry if g is not None and not g.is_empty), out_shape=(grilla.alto * k, grilla.ancho * k),
                              transform=tr, fill=0, dtype="uint8")
    cob = fino.reshape(grilla.alto, k, grilla.ancho, k).mean(axis=(1, 3))
    return cob >= umbral_cobertura


def comparar_areas(sim: np.ndarray, obs: np.ndarray, grilla) -> dict:
    inter = (sim & obs).sum(); s = sim.sum(); o = obs.sum(); union = (sim | obs).sum()
    ha = grilla.area_celda_ha
    d = {
        "ha_sim": round(float(s * ha), 2), "ha_obs": round(float(o * ha), 2),
        "error_ha": round(float((s - o) * ha), 2), "error_pct": round(float(100.0 * (s - o) / o), 1) if o else None,
        "sorensen": round(float(2 * inter / (s + o)), 3) if (s + o) else None,
        "jaccard": round(float(inter / union), 3) if union else None,
        "comision_pct": round(float(100.0 * (s - inter) / s), 1) if s else None,   # simulado fuera de lo observado
        "omision_pct": round(float(100.0 * (o - inter) / o), 1) if o else None,     # observado no simulado
    }
    if s and o:
        fs, cs = np.nonzero(sim); fo, co = np.nonzero(obs)
        xs, ys = grilla.centros(fs.mean(), cs.mean()); xo, yo = grilla.centros(fo.mean(), co.mean())
        dx, dy = xs - xo, ys - yo
        d["centroide_dist_m"] = round(float(np.hypot(dx, dy)), 0)
        d["centroide_rumbo_deg"] = round(float((np.degrees(np.arctan2(dx, dy)) + 360) % 360), 0)   # del observado al simulado
    else:
        d["centroide_dist_m"] = d["centroide_rumbo_deg"] = None
    return d


def tiempos_llegada_vs_focos(au, focos, t0: pd.Timestamp, radio_m: float = 375.0) -> pd.DataFrame:
    """Para cada foco VIIRS dentro de la grilla: hora de detección vs. hora simulada de llegada a la celda
    (o a la celda quemada más cercana dentro de `radio_m`, mitad del píxel VIIRS). Minutos desde t0."""
    g = au.capas.grilla
    filas = []
    if focos is None or not len(focos):
        return pd.DataFrame(filas)
    focos = focos.to_crs(g.crs)
    fq, cq = np.nonzero(np.isfinite(au.t_llegada))
    for _, r in focos.iterrows():
        x, y = r.geometry.x, r.geometry.y
        f, c = g.indices(x, y)
        if not (0 <= f < g.alto and 0 <= c < g.ancho):
            continue
        t_det = pd.Timestamp(r["hora_deteccion"]) if "hora_deteccion" in r else None
        obs_min = (t_det - t0).total_seconds() / 60.0 if t_det is not None else np.nan
        sim_min = float(au.t_llegada[f, c]) if np.isfinite(au.t_llegada[f, c]) else np.nan
        dist = 0.0
        if np.isnan(sim_min) and len(fq):
            d = np.hypot(fq - f, cq - c) * g.res
            j = int(d.argmin())
            if d[j] <= radio_m:
                sim_min = float(au.t_llegada[fq[j], cq[j]]); dist = float(d[j])
        filas.append({"id": r.get("id", ""), "hora_deteccion": t_det.isoformat() if t_det is not None else None,
                      "obs_min": round(obs_min, 0) if np.isfinite(obs_min) else None,
                      "sim_min": round(sim_min, 0) if np.isfinite(sim_min) else None,
                      "dif_min": round(sim_min - obs_min, 0) if np.isfinite(sim_min) and np.isfinite(obs_min) else None,
                      "dist_celda_m": dist, "frp": r.get("frp", None)})
    return pd.DataFrame(filas)
