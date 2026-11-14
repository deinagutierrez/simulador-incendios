"""Cortafuegos e intervenciones del lado del servidor (fase F5, contrato 1.5 §4.2).

- Pasa los trazos que dibuja la pantalla (en grados, `lonlat`) a EPSG:5345, los valida y normaliza con las mismas reglas que
  el proceso motor (`app/motores/intervenciones.py`) y revisa que toquen el dominio.
- Arma `cortafuegos.geojson` (en grados, para el mapa y la exportación) con los trazos de la configuración inicial y los de
  la bitácora.

`app/motores/intervenciones.py` no importa ningún motor (solo la biblioteca estándar, numpy y shapely): se carga por su ruta,
sin poner `app/motores` en `sys.path`, para que el servidor no pueda importar por error un conductor de motor.
"""
from __future__ import annotations

import importlib.util
import sys
from functools import lru_cache
from pathlib import Path

from . import datos

CRS_TRAZOS = "EPSG:5345"


def _cargar_intervenciones():
    nombre = "_simulador_intervenciones"
    if nombre in sys.modules:
        return sys.modules[nombre]
    ruta = Path(__file__).resolve().parents[1] / "motores" / "intervenciones.py"
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = modulo
    spec.loader.exec_module(modulo)
    return modulo


iv = _cargar_intervenciones()
ANCHOS_M = iv.ANCHOS_M
VEL_MAX_KMH = iv.VEL_MAX_KMH


@lru_cache(maxsize=2)
def _transformador(origen: str, destino: str):
    from pyproj import Transformer
    return Transformer.from_crs(origen, destino, always_xy=True)


def a_5345(lonlat) -> list[list[float]]:
    """[[lon, lat], …] en grados → [[x, y], …] en EPSG:5345."""
    lon = [float(p[0]) for p in lonlat]
    lat = [float(p[1]) for p in lonlat]
    xs, ys = _transformador("EPSG:4326", CRS_TRAZOS).transform(lon, lat)
    return [[float(x), float(y)] for x, y in zip(xs, ys)]


def a_grados(xy) -> list[list[float]]:
    xs, ys = _transformador(CRS_TRAZOS, "EPSG:4326").transform([float(p[0]) for p in xy], [float(p[1]) for p in xy])
    return [[round(float(x), 7), round(float(y), 7)] for x, y in zip(xs, ys)]


def toca_el_dominio(xy) -> bool:
    from shapely.geometry import LineString, box
    d = datos.dominio()
    return LineString([(float(x), float(y)) for x, y in xy]).intersects(box(d["xmin"], d["ymin"], d["xmax"], d["ymax"]))


def cortafuego(d: dict) -> dict:
    """Un trazo del pedido (`{ancho_m, suelo_mineral?, lonlat | xy_5345}`) normalizado como en el proceso motor:
    `{ancho_m, suelo_mineral, xy_5345, longitud_dibujada_m}`. ValueError con el motivo si no sirve."""
    if not isinstance(d, dict):
        raise ValueError("el cortafuego tiene que ser un objeto {ancho_m, suelo_mineral, lonlat | xy_5345}")
    tiene_ll, tiene_xy = d.get("lonlat") is not None, d.get("xy_5345") is not None
    if tiene_ll == tiene_xy:
        raise ValueError("el cortafuego lleva `lonlat` (grados) o `xy_5345` (metros), uno de los dos")
    xy = a_5345(d["lonlat"]) if tiene_ll else d["xy_5345"]
    norm = iv.validar_cortafuego({"ancho_m": d.get("ancho_m"), "suelo_mineral": bool(d.get("suelo_mineral", False)),
                                  "xy_5345": xy})
    if not toca_el_dominio(norm["xy_5345"]):
        raise ValueError("el trazo cae entero fuera del dominio")
    return norm


def cortafuegos(lista) -> list[dict]:
    out = []
    for i, d in enumerate(lista or []):
        try:
            out.append(cortafuego(d))
        except ValueError as e:
            raise ValueError(f"cortafuego {i + 1}: {e}") from None
    if len(out) > iv.MAX_CORTAFUEGOS:
        raise ValueError(f"hay {len(out)} cortafuegos; el máximo es {iv.MAX_CORTAFUEGOS}")
    return out


def entrada(tipo: str, d: dict) -> dict:
    """La entrada `{tipo, datos}` que se le manda al proceso motor, ya normalizada. ValueError si no sirve."""
    if tipo == "cortafuego":
        norm = cortafuego(d)
        return {"tipo": "cortafuego", "datos": {k: norm[k] for k in ("ancho_m", "suelo_mineral", "xy_5345")}}
    return iv.validar_entrada({"tipo": tipo, "datos": d})


def geojson(corrida: dict, bitacora: list[dict], estados: dict[int, str] | None = None) -> dict:
    """Cortafuegos de una corrida en grados: los de la configuración inicial (`origen: "inicial"`, con lo que informó el
    motor en `resultados.cortafuegos_iniciales` si ya terminó) y los de la bitácora (`origen: "intervencion"`, con `n`,
    `t_sim_min`, `t_vigor_min` y lo que agregó el motor: longitud aplicada, celdas…). `estados`: n → estado del aviso
    `intervencion` (aceptada o recortada)."""
    figuras = []
    iniciales = list((corrida.get("configuracion") or {}).get("cortafuegos") or [])
    informe = list((corrida.get("resultados") or {}).get("cortafuegos_iniciales") or [])
    for i, d in enumerate(iniciales):
        try:
            norm = iv.validar_cortafuego(d)
        except ValueError:
            continue
        props = {"origen": "inicial", "i": i + 1, "t_sim_min": 0, "t_vigor_min": 0,
                 **{k: v for k, v in norm.items() if k != "xy_5345"}}
        if i < len(informe) and isinstance(informe[i], dict):
            props |= {k: v for k, v in informe[i].items() if k != "xy_5345"}
        figuras.append({"type": "Feature", "properties": props,
                        "geometry": {"type": "LineString", "coordinates": a_grados(norm["xy_5345"])}})
    for e in bitacora or []:
        if e.get("tipo") != "cortafuego" or not isinstance(e.get("datos"), dict) or not e["datos"].get("xy_5345"):
            continue
        props = {"origen": "intervencion", "n": e.get("n"), "t_sim_min": e.get("t_sim_min"), "t_vigor_min": e.get("t_vigor_min"),
                 **{k: v for k, v in e["datos"].items() if k != "xy_5345"}}
        if estados and e.get("n") in estados:
            props["estado"] = estados[e["n"]]
        figuras.append({"type": "Feature", "properties": props,
                        "geometry": {"type": "LineString", "coordinates": a_grados(e["datos"]["xy_5345"])}})
    return {"type": "FeatureCollection", "features": figuras}
