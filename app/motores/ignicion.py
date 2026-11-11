"""Ignición en un punto y una hora elegidos por el usuario (el clic en el mapa).

Los dos motores sacan los puntos y la hora de ignición de la ficha del evento, con `incendios_sl.config.cargar_evento`.
Acá se envuelve esa función dentro del proceso para que entregue la misma ficha con `ignicion.puntos` y
`inicio.hora_utc_hipotesis` reemplazados. Todo lo demás de la ficha (meteorología, índices, cobertura) queda igual, y cada
motor sigue aplicando sus propias reglas. Ningún archivo de los motores ni de `escenarios/` cambia.

Punto sobre una celda que no quema (decisión D-E3-20). Cada motor corre ese punto a la celda combustible más cercana, y si
el evento tiene cicatriz de referencia la busca dentro de la cicatriz: una regla pensada para validar incendios históricos,
que con un clic libre puede llevar el fuego lejos de donde se marcó. Cuando el punto lo elige el usuario, acá se le oculta
la cicatriz a ese único paso (`_ignorar_cicatriz`), y el motor corre el punto a la celda combustible más cercana al clic,
con su propio mapa de combustible. Es lo mismo que hará con un evento generado en tiempo real, que no tiene cicatriz.
"""
from __future__ import annotations

import copy
from pathlib import Path


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
        _ignorar_cicatriz(cfgmod)
    if hora is not None:
        d["hipotesis"] = 0
    return d, informe


def _ignorar_cicatriz(cfgmod) -> None:
    """Hace que el motor cargado corra los puntos de ignición sin mirar la cicatriz de referencia. Solo afecta a ese paso:
    la cicatriz sigue disponible para todo lo demás."""
    if str(getattr(cfgmod, "VERSION_RESULTADOS", "")).startswith("v4"):
        from incendios_sl import eventos                      # v4.0: la regla es una función que recibe la cicatriz
        original = eventos.igniciones

        def igniciones(ficha, hipotesis=0, ignicion="snmf", combustible=None, cicatriz=None):
            return original(ficha, hipotesis, ignicion, combustible, None)

        eventos.igniciones = igniciones
    else:
        import numpy as np
        from incendios_sl.simulation import entradas         # v3.1: la regla lee la cicatriz al cargar las entradas
        original = entradas.leer_raster

        def leer_raster(ruta, *a, **k):
            r = original(ruta, *a, **k)
            if Path(str(ruta)).name.startswith("cicatriz_referencia_"):
                return (np.zeros_like(r[0]), *r[1:])
            return r

        entradas.leer_raster = leer_raster
