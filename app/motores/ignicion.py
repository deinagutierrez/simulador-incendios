"""Ignición en un punto y una hora elegidos por el usuario (el clic en el mapa).

Los dos motores sacan los puntos y la hora de ignición de la ficha del evento, con `incendios_sl.config.cargar_evento`.
Acá se envuelve esa función dentro del proceso para que entregue la misma ficha con `ignicion.puntos` y
`inicio.hora_utc_hipotesis` reemplazados. Todo lo demás de la ficha (meteorología, índices, cobertura, cicatriz) queda igual,
y cada motor sigue aplicando sus propias reglas: por ejemplo, si el punto cae en una celda no combustible lo corre a la
combustible más cercana (dentro de la cicatriz de referencia, si el evento base tiene una). Ningún archivo de los motores
ni de `escenarios/` cambia.
"""
from __future__ import annotations

import copy


def aplicar(cfgmod, definicion: dict, configuracion: dict) -> tuple[dict, dict]:
    """Devuelve (definición para el motor, informe de lo pedido). `cfgmod` es `incendios_sl.config` del motor cargado."""
    d = dict(definicion)
    if configuracion.get("horas"):
        d["horas"] = float(configuracion["horas"])
    puntos = configuracion.get("ignicion")
    t_inicio = configuracion.get("t_inicio_utc")
    if not puntos and not t_inicio:
        return d, {}
    if not d.get("evento"):
        raise ValueError("la ignición o la hora libres necesitan `base.definicion.evento` (el evento que aporta los datos)")

    import pandas as pd
    from pyproj import Transformer

    original = cfgmod.cargar_evento
    ficha_base = original(str(d["evento"]))
    informe: dict = {}

    nuevos = None
    if puntos:
        if not isinstance(puntos, list) or not all(isinstance(p, dict) and "lon" in p and "lat" in p for p in puntos):
            raise ValueError("`configuracion.ignicion` debe ser una lista de puntos {lon, lat}")
        g = cfgmod.cargar_dominio(ficha_base["dominio"])["grilla"]
        a_grilla = Transformer.from_crs("EPSG:4326", cfgmod.cargar_dominio(ficha_base["dominio"])["crs"], always_xy=True)
        nuevos = []
        for i, p in enumerate(puntos):
            lon, lat = float(p["lon"]), float(p["lat"])
            x, y = a_grilla.transform(lon, lat)
            if not (g["xmin"] <= x < g["xmax"] and g["ymin"] < y <= g["ymax"]):
                raise ValueError(f"el punto de ignición {i + 1} ({lon:.5f}, {lat:.5f}) cae fuera del dominio")
            nuevos.append({"nombre": str(p.get("nombre") or f"punto {i + 1}"), "lon": lon, "lat": lat})
        informe["puntos_pedidos"] = [{"lon": p["lon"], "lat": p["lat"]} for p in nuevos]

    hora = None
    if t_inicio:
        t = pd.Timestamp(t_inicio)
        if t.tzinfo is None:
            raise ValueError("`configuracion.t_inicio_utc` debe llevar huso horario (por ejemplo 2024-09-18T15:00:00Z)")
        t = t.tz_convert("UTC")
        met = ficha_base.get("meteorologia") or {}
        if met.get("inicio_utc") and met.get("fin_utc"):
            desde, hasta = pd.Timestamp(met["inicio_utc"]), pd.Timestamp(met["fin_utc"])
            if not (desde <= t < hasta):
                raise ValueError(f"la hora de inicio {t:%Y-%m-%d %H:%M} UTC cae fuera de la serie meteorológica del evento "
                                 f"{d['evento']} (de {desde:%Y-%m-%d %H:%M} a {hasta:%Y-%m-%d %H:%M} UTC)")
        hora = t.strftime("%Y-%m-%dT%H:%M:%SZ")
        informe["t_inicio_utc"] = hora

    def cargar_evento(id_evento, *a, **k):
        ficha = copy.deepcopy(original(id_evento, *a, **k))
        if str(id_evento) != str(d["evento"]):
            return ficha
        if nuevos is not None:
            ficha["ignicion"] = {"fuente": "punto elegido en el simulador interactivo", "puntos": copy.deepcopy(nuevos)}
        if hora is not None:
            ficha.setdefault("inicio", {})["hora_utc_hipotesis"] = [hora]
        return ficha

    cfgmod.cargar_evento = cargar_evento
    if nuevos is not None:
        d["ignicion"] = "snmf"            # los motores llaman así a "los puntos de la ficha"
    if hora is not None:
        d["hipotesis"] = 0
    return d, informe
