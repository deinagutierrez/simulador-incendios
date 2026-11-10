"""Indicadores horarios calculados sobre el estado del autómata (contrato del JSON horario)."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd
from rasterio import features
from shapely.geometry import shape
from shapely.ops import unary_union
from scipy.ndimage import distance_transform_edt

VERSION_ESQUEMA = "1.0"


@dataclass
class Exposicion:
    viviendas_afectadas: int = 0
    viviendas_amenazadas: int = 0
    viviendas_a_salvo: int = 0
    viviendas_total: int = 0
    tendido_km_quemado: float = 0.0
    tendido_km_en_combustion: float = 0.0
    caminos_km_afectados: float = 0.0
    caminos_km_cortados: float = 0.0     # tramos con celdas en combustión
    ids_viviendas_afectadas: list = field(default_factory=list)
    ids_viviendas_amenazadas: list = field(default_factory=list)


def mascaras_en(au, t_min: float):
    """Máscaras reconstruidas desde los tiempos de llegada y fin: afectada, en combustión, quemada, ignición."""
    tl = au.t_llegada; tf = au.t_fin
    afectada = tl <= t_min
    quemada = afectada & (tf <= t_min)
    combustion = afectada & ~quemada
    ignicion = combustion & (t_min - tl <= max(au.dt, 2.0))
    return afectada, combustion, quemada, ignicion


def poligonos(mask: np.ndarray, grilla):
    """Polígonos (shapely, CRS del dominio) de una máscara."""
    if not mask.any():
        return None
    geoms = [shape(g) for g, v in features.shapes(mask.astype("uint8"), mask=mask, transform=grilla.transform) if v == 1]
    return unary_union(geoms) if geoms else None


def perimetro_km(afectada: np.ndarray, combustion: np.ndarray, res: float) -> tuple[float, float]:
    """Perímetro total del área afectada y su porción activa (bordes de celdas en combustión), en km."""
    a = np.pad(afectada, 1)
    bordes = (a[1:-1, 1:-1] & ~a[:-2, 1:-1]), (a[1:-1, 1:-1] & ~a[2:, 1:-1]), (a[1:-1, 1:-1] & ~a[1:-1, :-2]), (a[1:-1, 1:-1] & ~a[1:-1, 2:])
    total = sum(int(b.sum()) for b in bordes) * res / 1000.0
    activo = sum(int((b & combustion).sum()) for b in bordes) * res / 1000.0
    return total, activo


def exposicion(au, afectada, combustion, buffer_m: float) -> Exposicion:
    cap = au.capas; g = cap.grilla
    ex = Exposicion(viviendas_total=len(cap.viviendas_gdf))
    pol_af = poligonos(afectada, g)
    pol_comb = poligonos(combustion, g)
    viv = cap.viviendas_gdf
    if len(viv):
        if pol_af is not None:
            af = viv.intersects(pol_af)
        else:
            af = pd.Series(False, index=viv.index)
        if pol_comb is not None:
            amen = viv.intersects(pol_comb.buffer(buffer_m)) & ~af
        else:
            amen = pd.Series(False, index=viv.index)
        ex.viviendas_afectadas = int(af.sum()); ex.viviendas_amenazadas = int(amen.sum())
        ex.viviendas_a_salvo = int(len(viv) - af.sum() - amen.sum())
        ex.ids_viviendas_afectadas = [str(i) for i in viv.loc[af, "id"].tolist()][:200]
        ex.ids_viviendas_amenazadas = [str(i) for i in viv.loc[amen, "id"].tolist()][:200]
    red = cap.red_gdf
    if len(red) and pol_af is not None:
        ex.tendido_km_quemado = float(red.intersection(pol_af).length.sum() / 1000.0)
        if pol_comb is not None:
            ex.tendido_km_en_combustion = float(red.intersection(pol_comb).length.sum() / 1000.0)
    cam = cap.caminos_gdf
    if len(cam) and pol_af is not None:
        ex.caminos_km_afectados = float(cam.intersection(pol_af).length.sum() / 1000.0)
        if pol_comb is not None:
            ex.caminos_km_cortados = float(cam.intersection(pol_comb.buffer(buffer_m / 2)).length.sum() / 1000.0)
    return ex


def _rumbo_medio(rumbos: np.ndarray, pesos: np.ndarray | None = None) -> float:
    if rumbos.size == 0:
        return float("nan")
    r = np.deg2rad(rumbos); w = np.ones_like(r) if pesos is None else pesos
    x = (w * np.sin(r)).sum(); y = (w * np.cos(r)).sum()
    return float((np.degrees(np.arctan2(x, y)) + 360) % 360)


def indicadores_hora(au, hora: int, t_min: float, t_min_prev: float, anterior: dict | None, cfg: dict, nombre: str) -> dict:
    g = au.capas.grilla
    afectada, combustion, quemada, ignicion = mascaras_en(au, t_min)
    ha = float(afectada.sum()) * g.area_celda_ha
    ha_prev = anterior["superficie"]["quemada_ha"] if anterior else 0.0
    per_total, per_activo = perimetro_km(afectada, combustion, g.res)
    nuevas = (au.t_llegada > t_min_prev) & (au.t_llegada <= t_min)
    # cabeza: celdas encendidas en la última hora; rumbo medio ponderado por ROS; avance máximo desde la ignición
    if au.igniciones:
        f0 = np.mean([i.fila for i in au.igniciones]); c0 = np.mean([i.col for i in au.igniciones])
    else:
        f0 = c0 = 0
    f, c = np.nonzero(afectada)
    dist = np.hypot(f - f0, c - c0) * g.res if len(f) else np.array([0.0])
    alcance = float(dist.max()) if len(f) else 0.0
    alcance_prev = anterior["frente"]["alcance_max_m"] if anterior else 0.0
    if nuevas.any():
        rumbo = _rumbo_medio(au.rumbo_cab[nuevas][~np.isnan(au.rumbo_cab[nuevas])], au.ros_max[nuevas][~np.isnan(au.rumbo_cab[nuevas])])
        ros_h = float(au.ros_max[nuevas].max()); ib_h = float(au.intensidad_max[nuevas].max()); ll_h = float(au.llama_max[nuevas].max())
        ros_med = float(np.median(au.ros_max[nuevas]))
    else:
        rumbo = float("nan"); ros_h = ib_h = ll_h = ros_med = 0.0
    met = au.meteo.en(au.t0 + pd.Timedelta(minutes=t_min))
    m1, m10, m100 = au._humedad_muerta(au.t0 + pd.Timedelta(minutes=t_min))
    ex = exposicion(au, afectada, combustion, float(cfg["parametros"]["viviendas_buffer_m"]))
    pol = poligonos(afectada, g)
    if pol is not None:
        cx, cy = pol.centroid.x, pol.centroid.y
        from pyproj import Transformer
        lon, lat = Transformer.from_crs(g.crs, "EPSG:4326", always_xy=True).transform(cx, cy)
        bbox = list(pol.bounds)
    else:
        cx = cy = lon = lat = float("nan"); bbox = []
    alertas = []
    if au.toco_borde:
        alertas.append("El fuego alcanzó el borde del dominio de simulación: el dominio quedó chico.")
    if not au.activo() and hora > 0:
        alertas.append("Sin celdas activas: el incendio se extinguió en la simulación.")
    if au.spots:
        alertas.append(f"Focos secundarios (spotting experimental): {au.spots} igniciones.")
    t_local = (au.t0 + pd.Timedelta(minutes=t_min)).tz_convert("America/Argentina/San_Luis")
    d = {
        "version": VERSION_ESQUEMA,
        "corrida": nombre,
        "hora_indice": hora,
        "timestamp": t_local.isoformat(),
        "timestamp_utc": (au.t0 + pd.Timedelta(minutes=t_min)).tz_convert("UTC").isoformat(),
        "minutos_desde_t0": float(t_min),
        "superficie": {"quemada_ha": round(ha, 2), "incremento_ha": round(ha - ha_prev, 2),
                       "en_combustion_ha": round(float(combustion.sum()) * g.area_celda_ha, 2),
                       "consumida_ha": round(float(quemada.sum()) * g.area_celda_ha, 2)},
        "perimetro": {"total_km": round(per_total, 2), "activo_km": round(per_activo, 2)},
        "frente": {"rumbo_cabeza_deg": None if np.isnan(rumbo) else round(rumbo, 0),
                   "rumbo_cabeza_texto": None if np.isnan(rumbo) else rumbo_texto(rumbo),
                   "velocidad_cabeza_m_min": round(ros_h, 2), "velocidad_cabeza_km_h": round(ros_h * 0.06, 2),
                   "ros_mediana_m_min": round(ros_med, 2),
                   "intensidad_max_kw_m": round(ib_h, 0), "longitud_llama_max_m": round(ll_h, 2),
                   "alcance_max_m": round(alcance, 0), "avance_alcance_m": round(alcance - alcance_prev, 0),
                   "celdas_activas": int(len(au.act))},
        "meteo": {"temp_c": round(met.temp_c, 1), "hr_pct": round(met.hr_pct, 0), "viento_kmh": round(met.viento_kmh, 1),
                  "viento_dir_deg": round(met.viento_dir_deg, 0), "viento_dir_texto": rumbo_texto(met.viento_dir_deg),
                  "precip_mm_h": round(met.precip_mm_h, 1),
                  "humedad_muerta_1h_pct": round(m1 * 100, 1), "humedad_muerta_10h_pct": round(m10 * 100, 1),
                  "humedad_muerta_100h_pct": round(m100 * 100, 1)},
        "exposicion": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in asdict(ex).items()},
        "estado_celdas": {"ignicion": int(ignicion.sum()), "combustion": int(combustion.sum()), "quemado": int(quemada.sum()),
                          "afectada": int(afectada.sum())},
        "centroide": {"x": None if np.isnan(cx) else round(cx, 1), "y": None if np.isnan(cy) else round(cy, 1),
                      "lon": None if np.isnan(lon) else round(lon, 6), "lat": None if np.isnan(lat) else round(lat, 6)},
        "bbox": [round(b, 1) for b in bbox],
        "alertas": alertas,
    }
    if anterior:
        d["cambios"] = {
            "superficie_ha": round(ha - ha_prev, 2),
            "viviendas_afectadas": ex.viviendas_afectadas - anterior["exposicion"]["viviendas_afectadas"],
            "viviendas_amenazadas": ex.viviendas_amenazadas - anterior["exposicion"]["viviendas_amenazadas"],
            "tendido_km_quemado": round(ex.tendido_km_quemado - anterior["exposicion"]["tendido_km_quemado"], 2),
            "caminos_km_afectados": round(ex.caminos_km_afectados - anterior["exposicion"]["caminos_km_afectados"], 2),
            "viento_kmh": round(met.viento_kmh - anterior["meteo"]["viento_kmh"], 1),
            "hr_pct": round(met.hr_pct - anterior["meteo"]["hr_pct"], 0),
            "perimetro_activo_km": round(per_activo - anterior["perimetro"]["activo_km"], 2),
        }
    else:
        d["cambios"] = None
    return d


def rumbo_texto(deg: float) -> str:
    puntos = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"]
    return puntos[int(round(deg / 22.5)) % 16]
