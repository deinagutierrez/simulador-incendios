"""Lo que el servidor necesita saber de los datos sin cargar ningún motor: qué eventos tienen datos en este clon (con
ficha o generados `RT-…`) y cuál es el recuadro del dominio. Lee los YAML de `escenarios/v4.0` (las fichas de v3.1 y v4.0
son las mismas) y, de los eventos generados, su `insumos_RT-….json`."""
from __future__ import annotations

import datetime as dt
import json
import re
from functools import lru_cache
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
ESCENARIOS = REPO / "escenarios" / "v4.0"
ENTRADAS = REPO / "datos" / "inputSimulacion"
PATRON_RT = re.compile(r"^RT-(\d{8})-(\d+)$")          # el mismo de app/datos/evento_rt.py
ROTULO_EJEMPLO = "EJEMPLO"
ADVERTENCIA_EJEMPLO = "EJEMPLO: datos de un evento histórico"


def es_rt(id_evento) -> bool:
    return bool(PATRON_RT.match(str(id_evento)))


def ruta_insumos(id_evento: str) -> Path:
    return ENTRADAS / "eventos" / id_evento / f"insumos_{id_evento}.json"


def insumos_rt(id_evento: str) -> dict | None:
    """El `insumos_RT-….json` que escribe `app/datos/evento_rt.py` (procedencia de todo el evento), o None."""
    try:
        return json.loads(ruta_insumos(id_evento).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


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


def _firma_eventos() -> tuple:
    """Lo que cambia cuando se agrega, se completa o se borra un evento: las fichas y los `insumos_RT-….json` con su hora
    de modificación. La lista de eventos se vuelve a leer solo cuando esto cambia."""
    firma = []
    for patron, carpeta in (("*.yaml", ESCENARIOS / "eventos"), ("RT-*/insumos_RT-*.json", ENTRADAS / "eventos")):
        for ruta in sorted(carpeta.glob(patron)):
            try:
                firma.append((ruta.name, ruta.stat().st_mtime_ns))
            except OSError:
                pass
    return str(ESCENARIOS), str(ENTRADAS), tuple(firma)


def eventos_base() -> dict[str, dict]:
    """Eventos cuyos datos están en este clon. De cada uno: nombre, rango de la serie meteorológica, horas de inicio de la
    ficha y puntos de ignición de la ficha; `tiempo_real` (evento generado `RT-…`), `rotulos` y `avisos`. Los eventos con
    ficha se rotulan EJEMPLO (plan §4.2). Un evento generado aparece cuando ya tiene su `insumos_RT-….json` (el último
    archivo que escribe el proceso de datos) y no trae puntos de ignición: el punto lo marca el usuario."""
    return _eventos_base(_firma_eventos())


def invalidar_eventos() -> None:
    _eventos_base.cache_clear()


@lru_cache(maxsize=4)
def _eventos_base(_firma: tuple) -> dict[str, dict]:
    out = {}
    for ruta in sorted((ESCENARIOS / "eventos").glob("*.yaml")):
        try:
            f = yaml.safe_load(ruta.read_text(encoding="utf-8"))
            id_ = str(f["id"])
        except (yaml.YAMLError, KeyError, TypeError, OSError):
            continue
        if not ((ENTRADAS / "eventos" / id_).is_dir() and (ENTRADAS / "combustibles" / id_).is_dir()):
            continue
        rt = es_rt(id_)
        insumos = insumos_rt(id_) if rt else None
        if rt and insumos is None:                   # a medio armar (o roto): no se ofrece
            continue
        met = f.get("meteorologia") or {}
        try:
            desde, hasta = _iso(_utc(met["inicio_utc"])), _iso(_utc(met["fin_utc"]))
        except (KeyError, ValueError):
            desde = hasta = None
        puntos = [] if rt else [{"lon": float(p["lon"]), "lat": float(p["lat"]), "nombre": str(p.get("nombre", ""))}
                                for p in ((f.get("ignicion") or {}).get("puntos") or [])]
        e = {"id": id_, "nombre": f.get("nombre"), "meteo_desde_utc": desde, "meteo_hasta_utc": hasta,
             "inicios_de_la_ficha_utc": [str(h) for h in ((f.get("inicio") or {}).get("hora_utc_hipotesis") or [])],
             "ignicion_de_la_ficha": puntos, "tiempo_real": rt}
        if rt:
            e |= {"rotulos": list(insumos.get("rotulos") or []), "avisos": list(insumos.get("avisos") or []),
                  "creado_utc": insumos.get("creado_utc"), "t_inicio_por_defecto_utc": insumos.get("t_inicio_por_defecto_utc"),
                  "meteo": (insumos.get("meteo") or {}).get("id"), "indices": (insumos.get("indices") or {}).get("id"),
                  "cobertura_anio": insumos.get("cobertura_anio")}
        else:
            e |= {"rotulos": [ROTULO_EJEMPLO], "avisos": [ADVERTENCIA_EJEMPLO]}
        out[id_] = e
    return out


def insumos_de_la_corrida(id_evento: str | None) -> tuple[dict | None, list[str]]:
    """Bloque `insumos` de `corrida.json` (Anexo C del plan) y sus advertencias. Para un evento con ficha: sin bloque y la
    advertencia EJEMPLO; sin evento (motor simulado, definición sin evento): nada."""
    if not id_evento:
        return None, []
    if not es_rt(id_evento):
        return None, [ADVERTENCIA_EJEMPLO]
    d = insumos_rt(id_evento)
    if d is None:
        return None, [f"evento generado {id_evento} sin registro de insumos (insumos_{id_evento}.json)"]
    m, i, v = d.get("meteo") or {}, d.get("indices") or {}, d.get("verano_v40") or {}
    anio_verano = next((int(x.group(1)) for n in list(v.get("archivos") or []) + list(v.get("faltan") or [])
                        if (x := re.search(r"NDVI_NDMI_(\d{4})_", str(n)))), None)
    insumos = {
        "evento": {"id": d.get("id"), "creado_utc": d.get("creado_utc"), "archivos": d.get("archivos"), "sha256": d.get("sha256")},
        "meteo": {"toma": m.get("id"), "fuente": m.get("fuente"), "modelo": m.get("modelo"), "rotulo": m.get("rotulo"),
                  "descargado_utc": m.get("descargado_utc") or m.get("creada_utc"), "desde_utc": m.get("desde_utc"),
                  "hasta_utc": m.get("hasta_utc"), "sha256": m.get("sha256")},
        "indices_ventana": {"toma": i.get("id"), "fuente": i.get("fuente"), "rotulo": i.get("rotulo"), "via": i.get("via"),
                            "ventana": i.get("ventana"), "escenas": i.get("n_escenas"), "ndmi_nir": i.get("ndmi_nir"),
                            "sha256": i.get("sha256"), "en_prueba": bool(i.get("en_prueba"))},
        "indices_verano": {"anio": anio_verano, "archivos": v.get("archivos"), "faltan": v.get("faltan"), "sha256": v.get("sha256")},
        "cobertura_anio": d.get("cobertura_anio"),
    }
    rotulos = list(d.get("rotulos") or [])
    advertencias = (([f"meteorología: {rotulos[0]}"] if len(rotulos) > 0 else []) +
                    ([f"índices: {rotulos[1]}"] if len(rotulos) > 1 else []) +
                    [str(x) for x in (m.get("aviso"), i.get("aviso")) if x] + [str(a) for a in d.get("avisos") or []] +
                    ["evento generado: sin cicatriz ni focos, no se valida contra observaciones"])
    return insumos, list(dict.fromkeys(advertencias))


def revisar_pedido(pedido: dict) -> None:
    """Controles que se pueden hacer sin lanzar el motor, para contestar en el acto. El proceso motor los repite."""
    ev = eventos_base().get(str(pedido.get("evento")))
    if ev is None:
        disponibles = ", ".join(eventos_base()) or "ninguno"
        raise ValueError(f"el evento {pedido.get('evento')!r} no tiene datos en este clon; disponibles: {disponibles}")
    if ev["tiempo_real"]:
        if not pedido.get("ignicion"):
            raise ValueError(f"el evento {ev['id']} es de tiempo real y no tiene puntos de ignición propios: "
                             "marcá el punto de ignición en el mapa")
        if pedido.get("ignicion_ficha"):
            raise ValueError(f"el evento {ev['id']} es de tiempo real: no tiene puntos de ignición de ficha")
    for i, p in enumerate(pedido.get("ignicion") or []):
        if not dentro_del_dominio(float(p["lon"]), float(p["lat"])):
            raise ValueError(f"el punto de ignición {i + 1} ({p['lon']:.5f}, {p['lat']:.5f}) cae fuera del dominio")
    if pedido.get("t_inicio_utc"):
        t = _utc(pedido["t_inicio_utc"])
        if ev["meteo_desde_utc"] and not (_utc(ev["meteo_desde_utc"]) <= t < _utc(ev["meteo_hasta_utc"])):
            raise ValueError(f"la hora de inicio cae fuera de la serie meteorológica del evento {ev['id']} "
                             f"(de {ev['meteo_desde_utc']} a {ev['meteo_hasta_utc']})")
