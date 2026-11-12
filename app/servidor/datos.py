"""Lo que el servidor necesita saber de los datos sin cargar ningún motor: qué eventos con ficha tienen datos en este
clon y cuál es el recuadro del dominio. Lee los YAML de `escenarios/v4.0` (las fichas de v3.1 y v4.0 son las mismas)."""
from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
ESCENARIOS = REPO / "escenarios" / "v4.0"
ENTRADAS = REPO / "datos" / "inputSimulacion"


def _utc(texto) -> dt.datetime:
    t = dt.datetime.fromisoformat(str(texto).replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("la hora debe llevar huso horario, por ejemplo 2024-09-18T15:00:00Z")
    return t.astimezone(dt.timezone.utc)


def _iso(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


@lru_cache(maxsize=1)
def dominio() -> dict:
    """Recuadro del dominio en la proyección de la grilla y en grados (para centrar el mapa y validar el clic)."""
    from pyproj import Transformer
    d = yaml.safe_load(next((ESCENARIOS / "dominios").glob("dominio_*.yaml")).read_text(encoding="utf-8"))
    g = d["grilla"]
    res = float(d["resolucion_m"])
    xmax = g.get("xmax", g["xmin"] + g["ncol"] * res)
    ymin = g.get("ymin", g["ymax"] - g.get("nfil", 0) * res)
    a_grados = Transformer.from_crs(d["crs"], "EPSG:4326", always_xy=True)
    lons, lats = a_grados.transform([g["xmin"], xmax, g["xmin"], xmax], [ymin, ymin, g["ymax"], g["ymax"]])
    return {"id": d.get("id"), "crs": d["crs"], "res": res, "xmin": g["xmin"], "xmax": xmax, "ymin": ymin, "ymax": g["ymax"],
            "limites": [[min(lats), min(lons)], [max(lats), max(lons)]]}


def dentro_del_dominio(lon: float, lat: float) -> bool:
    from pyproj import Transformer
    d = dominio()
    x, y = Transformer.from_crs("EPSG:4326", d["crs"], always_xy=True).transform(lon, lat)
    return d["xmin"] <= x < d["xmax"] and d["ymin"] < y <= d["ymax"]


@lru_cache(maxsize=1)
def eventos_base() -> dict[str, dict]:
    """Eventos con ficha cuyos datos están en este clon. De cada uno: nombre, rango de la serie meteorológica, horas de
    inicio de la ficha y puntos de ignición de la ficha."""
    out = {}
    for ruta in sorted((ESCENARIOS / "eventos").glob("*.yaml")):
        try:
            f = yaml.safe_load(ruta.read_text(encoding="utf-8"))
            id_ = str(f["id"])
        except (yaml.YAMLError, KeyError, TypeError):
            continue
        if not ((ENTRADAS / "eventos" / id_).is_dir() and (ENTRADAS / "combustibles" / id_).is_dir()):
            continue
        met = f.get("meteorologia") or {}
        try:
            desde, hasta = _iso(_utc(met["inicio_utc"])), _iso(_utc(met["fin_utc"]))
        except (KeyError, ValueError):
            desde = hasta = None
        puntos = [{"lon": float(p["lon"]), "lat": float(p["lat"]), "nombre": str(p.get("nombre", ""))}
                  for p in ((f.get("ignicion") or {}).get("puntos") or [])]
        out[id_] = {"id": id_, "nombre": f.get("nombre"), "meteo_desde_utc": desde, "meteo_hasta_utc": hasta,
                    "inicios_de_la_ficha_utc": [str(h) for h in ((f.get("inicio") or {}).get("hora_utc_hipotesis") or [])],
                    "ignicion_de_la_ficha": puntos}
    return out


def revisar_pedido(pedido: dict) -> None:
    """Controles que se pueden hacer sin lanzar el motor, para contestar en el acto. El proceso motor los repite."""
    ev = eventos_base().get(str(pedido.get("evento")))
    if ev is None:
        disponibles = ", ".join(eventos_base()) or "ninguno"
        raise ValueError(f"el evento {pedido.get('evento')!r} no tiene datos en este clon; disponibles: {disponibles}")
    for i, p in enumerate(pedido.get("ignicion") or []):
        if not dentro_del_dominio(float(p["lon"]), float(p["lat"])):
            raise ValueError(f"el punto de ignición {i + 1} ({p['lon']:.5f}, {p['lat']:.5f}) cae fuera del dominio")
    if pedido.get("t_inicio_utc"):
        t = _utc(pedido["t_inicio_utc"])
        if ev["meteo_desde_utc"] and not (_utc(ev["meteo_desde_utc"]) <= t < _utc(ev["meteo_hasta_utc"])):
            raise ValueError(f"la hora de inicio cae fuera de la serie meteorológica del evento {ev['id']} "
                             f"(de {ev['meteo_desde_utc']} a {ev['meteo_hasta_utc']})")
