"""Cortafuegos e intervenciones del lado del servidor (fase F5, contrato 1.5 §4.2).

- Pasa los trazos que dibuja la pantalla (en grados, `lonlat`) a EPSG:5345, los valida y normaliza con las mismas reglas que
  el proceso motor (`app/motores/intervenciones.py`) y revisa que toquen el dominio.
- Arma `cortafuegos.geojson` (en grados, para el mapa y la exportación) con los trazos de la configuración inicial y los de
  la bitácora.
- Combate (contrato 1.6): normaliza las dotaciones del pedido e informa los parámetros del método común
  (`app/motores/combate.py`).

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


def _cargar_combate():
    """`app/motores/combate.py` (el método común de combate) tampoco importa motores: se carga igual, por su ruta, para
    informar sus parámetros a la pantalla."""
    nombre = "_simulador_combate"
    if nombre in sys.modules:
        return sys.modules[nombre]
    ruta = Path(__file__).resolve().parents[1] / "motores" / "combate.py"
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = modulo
    spec.loader.exec_module(modulo)
    return modulo


iv = _cargar_intervenciones()
cb = _cargar_combate()
ANCHOS_M = iv.ANCHOS_M
VEL_MAX_KMH = iv.VEL_MAX_KMH


def combate() -> dict:
    """Lo que la pantalla necesita del combate: límites de los pedidos y parámetros del método (para mostrar las cuentas)."""
    return {"max_bomberos": iv.MAX_BOMBEROS, "max_llegada_min": iv.MAX_LLEGADA_MIN,
            "max_dotaciones_iniciales": iv.MAX_DOTACIONES_INICIALES, "prioridades": list(iv.PRIORIDADES),
            "medios": list(iv.MEDIOS_AEREOS), "productos": list(iv.PRODUCTOS), "parametros": cb.parametros()}


def dotaciones(lista) -> list[dict]:
    """Las dotaciones del pedido de una corrida (despachadas antes de iniciar), normalizadas. ValueError si no sirven."""
    return iv.validar_dotaciones(list(lista or []))


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


def descarga(d: dict) -> dict:
    """Una descarga aérea del pedido (`{medio, producto?, lonlat | xy_5345}`: dos puntos, dónde empieza y hacia dónde va)
    normalizada como en el proceso motor: `{medio, producto, xy_5345}`. ValueError con el motivo si no sirve."""
    if not isinstance(d, dict):
        raise ValueError("la descarga tiene que ser un objeto {medio, producto, lonlat | xy_5345}")
    tiene_ll, tiene_xy = d.get("lonlat") is not None, d.get("xy_5345") is not None
    if tiene_ll == tiene_xy:
        raise ValueError("la descarga lleva `lonlat` (grados) o `xy_5345` (metros), uno de los dos")
    xy = a_5345(d["lonlat"]) if tiene_ll else d["xy_5345"]
    norm = iv.validar_descarga({"medio": d.get("medio"), "producto": d.get("producto", "agua"), "xy_5345": xy})
    dom = datos.dominio()
    x, y = norm["xy_5345"][0]
    if not (dom["xmin"] <= x <= dom["xmax"] and dom["ymin"] <= y <= dom["ymax"]):
        raise ValueError("la descarga empieza fuera del dominio")
    return norm


def entrada(tipo: str, d: dict) -> dict:
    """La entrada `{tipo, datos}` que se le manda al proceso motor, ya normalizada. ValueError si no sirve."""
    if tipo == "cortafuego":
        norm = cortafuego(d)
        return {"tipo": "cortafuego", "datos": {k: norm[k] for k in ("ancho_m", "suelo_mineral", "xy_5345")}}
    if tipo == "descarga":
        return {"tipo": "descarga", "datos": descarga(d)}
    return iv.validar_entrada({"tipo": tipo, "datos": d})


def descargas_geojson(bitacora: list[dict], estados: dict[int, str] | None = None) -> dict:
    """Las descargas aéreas de la bitácora como franjas (polígonos en grados): el rectángulo que va del punto de inicio al
    de fin que informó el motor (`xy_fin_5345`), con su ancho. Propiedades: `n`, `t_sim_min`, `medio`, `producto`, lo que
    agregó el motor (celdas mojadas y frenadas, `vence_min`…) y `estado` (aceptada o recortada)."""
    figuras = []
    for e in bitacora or []:
        d = e.get("datos") if isinstance(e.get("datos"), dict) else None
        if e.get("tipo") != "descarga" or not d or not d.get("xy_5345") or not d.get("xy_fin_5345") or not d.get("ancho_m"):
            continue
        (x0, y0), (x1, y1) = (float(d["xy_5345"][0][0]), float(d["xy_5345"][0][1])), (float(d["xy_fin_5345"][0]), float(d["xy_fin_5345"][1]))
        largo = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        if largo <= 0:
            continue
        nx, ny = -(y1 - y0) / largo * float(d["ancho_m"]) / 2.0, (x1 - x0) / largo * float(d["ancho_m"]) / 2.0
        anillo = a_grados([[x0 + nx, y0 + ny], [x1 + nx, y1 + ny], [x1 - nx, y1 - ny], [x0 - nx, y0 - ny], [x0 + nx, y0 + ny]])
        props = {"n": e.get("n"), "t_sim_min": e.get("t_sim_min"), **{k: v for k, v in d.items() if k not in ("xy_5345", "xy_fin_5345")}}
        if estados and e.get("n") in estados:
            props["estado"] = estados[e["n"]]
        figuras.append({"type": "Feature", "properties": props, "geometry": {"type": "Polygon", "coordinates": [anillo]}})
    return {"type": "FeatureCollection", "features": figuras}


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
