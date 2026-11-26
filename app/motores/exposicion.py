"""Exposición y meteorología de cada hora para los motores que no las informan (v3.1).

v4.0 escribe en su JSON horario la exposición (viviendas, red eléctrica y caminos alcanzados) y el tiempo de la hora;
v3.1 no. Para que la tarjeta de los dos motores muestre las mismas cifras, el adaptador de v3.1 las calcula acá, desde su
estado (celdas afectadas y en combustión) y la misma capa de infraestructura que usa v4.0
(`datos/inputSimulacion/sim_v4/estaticos/infraestructura.gpkg`), con la misma regla que
`src/v4.0/src/simulador/outputs/indicadores.py` (`exposicion`):

- vivienda afectada: toca el área afectada; amenazada: no afectada y a menos de `buffer_m` (100 m, el valor por defecto
  de v4.0) de una celda en combustión;
- red eléctrica quemada y caminos afectados: km de líneas dentro del área afectada.

Solo lee el estado del motor: no cambia la simulación.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[2]
INFRAESTRUCTURA = RAIZ / "datos" / "inputSimulacion" / "sim_v4" / "estaticos" / "infraestructura.gpkg"
BUFFER_VIVIENDAS_M = 100.0                  # config.py de v4.0: parametros.viviendas_buffer_m
PUNTOS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"]


def rumbo_texto(deg: float) -> str:
    return PUNTOS[int(round(float(deg) / 22.5)) % 16]


class Exposicion:
    """Capas de infraestructura recortadas a la grilla del motor; `en(afectada, combustion)` da las cifras de la hora."""

    def __init__(self, grilla: dict, ruta: Path = INFRAESTRUCTURA, buffer_m: float = BUFFER_VIVIENDAS_M):
        import geopandas as gpd
        from rasterio.transform import from_origin
        from shapely.geometry import box
        self.transform = from_origin(grilla["xmin"], grilla["ymax"], grilla["res"], grilla["res"])
        x0, y1 = grilla["xmin"], grilla["ymax"]
        x1, y0 = x0 + grilla["cols"] * grilla["res"], y1 - grilla["filas"] * grilla["res"]
        caja = box(x0, y0, x1, y1)
        self.buffer_m = float(buffer_m)
        self.capas = {}
        for capa in ("viviendas", "red_electrica", "caminos"):
            g = gpd.read_file(ruta, layer=capa)
            if len(g) and g.crs is not None and grilla.get("crs") and not g.crs.equals(grilla["crs"]):
                g = g.to_crs(grilla["crs"])
            self.capas[capa] = g[g.intersects(caja)]

    def _poligono(self, mascara: np.ndarray):
        from rasterio import features
        from shapely.geometry import shape
        from shapely.ops import unary_union
        if not mascara.any():
            return None
        geoms = [shape(g) for g, v in features.shapes(mascara.astype("uint8"), mask=mascara, transform=self.transform) if v == 1]
        return unary_union(geoms) if geoms else None

    def en(self, afectada: np.ndarray, combustion: np.ndarray) -> dict:
        viv, red, cam = self.capas["viviendas"], self.capas["red_electrica"], self.capas["caminos"]
        pol_af, pol_comb = self._poligono(afectada), self._poligono(combustion)
        af = viv.intersects(pol_af) if pol_af is not None and len(viv) else np.zeros(len(viv), bool)
        amen = (viv.intersects(pol_comb.buffer(self.buffer_m)) & ~af) if pol_comb is not None and len(viv) else np.zeros(len(viv), bool)
        km = lambda lineas: round(float(lineas.intersection(pol_af).length.sum() / 1000.0), 2) if pol_af is not None and len(lineas) else 0.0
        n_af, n_amen = int(np.sum(af)), int(np.sum(amen))
        return {"viviendas_afectadas": n_af, "viviendas_amenazadas": n_amen, "viviendas_a_salvo": len(viv) - n_af - n_amen,
                "viviendas_total": len(viv), "tendido_km_quemado": km(red), "caminos_km_afectados": km(cam)}


def meteo_v31(fila) -> dict:
    """Tiempo de la hora desde una fila de la serie del dominio de v3.1 (viento en m/s, de donde viene)."""
    d = float(fila.wind_direction_10m)
    return {"temp_c": round(float(fila.temperature_2m), 1), "hr_pct": round(float(fila.relative_humidity_2m), 0),
            "viento_kmh": round(float(fila.wind_speed_10m_vectorial) * 3.6, 1), "viento_dir_deg": round(d, 0),
            "viento_dir_texto": rumbo_texto(d), "precip_mm_h": round(float(getattr(fila, "precipitation", 0.0) or 0.0), 1)}
