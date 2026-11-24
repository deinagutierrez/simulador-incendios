"""Conduce al motor v3.1 sin modificarlo.

Sigue el camino de src/v3.1/scripts/correr_escenario.py sin validación (cargar_entradas_evento, Simulacion.ejecutar,
guardar) y solo agrega un punto de control: una subclase de `Simulacion` que redefine `_tablas_hora`, el método que el
motor llama al empezar cada hora simulada, antes de calcular el viento de esa hora. Ningún archivo de src/v3.1 cambia.

Intervenciones (F5, contrato 1.5): la simulación arranca con una matriz de barreras vacía completa (las dos variantes de la
app corren con las barreras apagadas; da lo mismo, ver barreras_v31.py), los cortafuegos de `configuracion.cortafuegos` se
aplican antes de ejecutar (igual que a t = 0; si el motor rechaza alguno, la corrida se corta con error antes de simular,
D-E3-31) y `control.aplicar` aplica cortafuegos y viento manual con la corrida en
pausa, dentro de `_tablas_hora`, antes de la hora que empieza. Todo está en barreras_v31.py.

Combate (decisión D-E3-36; el método está en combate.py y es el mismo que en v4.0): las intervenciones de combate
(`intervenciones.TIPOS_COMBATE`) van al objeto `Combate`, que trabaja sobre la simulación por medio de `combate_v31.py`. El
paso horario del combate corre en `_contener_hora`, que el motor llama en cada cambio de hora desde que el adaptador enciende
la contención (la primera vez que hay combate); la contención propia de v3.1 no corre nunca. `configuracion.dotaciones` se
despacha antes de ejecutar. Sin intervenciones de combate la simulación no se toca. El combate no tiene corrida offline
equivalente: su garantía es la reproducción desde la bitácora (comparación A).

Regla de cruce de los cortafuegos (D-E3-35): las dos variantes de la app corren con el cruce de barreras en modo `umbral`
(ver `cruce_por_umbral`). Como arrancan sin barreras de caminos, solo afecta a los cortafuegos dibujados.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import numpy as np

import barreras_v31
import combate as cb
import intervenciones as iv
from control import Control, exigir_cortafuegos_iniciales, malla_viento

REPO = Path(__file__).resolve().parents[2]
RAIZ = REPO / "src" / "v3.1"
VARIANTES_SIN_CAMINOS = ("libre", "libre_v2")          # las dos de la app: barreras de caminos apagadas (D-E3-29)


def cruce_por_umbral(esc: dict) -> bool:
    """Pone en la definición el cruce de barreras en modo `umbral` (decisión D-E3-35). Devuelve True si la cambió.

    La regla por defecto de v3.x es una logística en L/W (largo de llama sobre ancho de la barrera) que nunca baja de
    σ(0) = 1/(1 + e^(β·λ)) = 1,8 % con β = 4 y λ = 1: cada enlace deja pasar el fuego 1,8 % de las veces por hora aunque no
    haya llama, y se vuelve a sortear cada hora. Con un cortafuego dibujado eso da un cruce seguro en una o dos horas, sea
    del ancho que sea (medido el 2026-11-17: 13 cruces en 684 intentos con 10 m y 16 en 997 con 25 m). v4.0 lo corrige
    con `normalizar`; v3.1 no tiene esa opción, pero sí el modo `umbral` de su propio modelo: el fuego cruza solo si
    L/W > λ, sin sorteo y sin piso.

    Se pide por el camino que el motor ya ofrece (`parche` del escenario, que `correr_escenario.py` fusiona con el modelo),
    así queda escrito en `escenario_base.yaml` y la corrida offline equivalente usa la misma regla. No se toca si la
    definición trae otra variante, fuerza `barreras`, cambia de `modelo` o ya elige un modo de cruce: con barreras de
    caminos, la regla validada es la del modelo."""
    if esc.get("variante") not in VARIANTES_SIN_CAMINOS or "barreras" in esc or "modelo" in esc:
        return False
    parche = dict(esc.get("parche") or {})
    barreras = dict(parche.get("barreras") or {})
    cruce = dict(barreras.get("cruce") or {})
    if "modo" in cruce:
        return False
    cruce["modo"] = "umbral"
    barreras["cruce"] = cruce
    parche["barreras"] = barreras
    esc["parche"] = parche
    return True


def cargar(base: dict, configuracion: dict, carpeta: Path, variante_por_defecto: str) -> dict:
    """Entradas del motor para una corrida, por el camino de correr_escenario.py (sin validación).

    Devuelve `esc` (la definición que corre el motor), `pedido`, `ruta` y `nombre` del YAML, `ent`, `cfg`, `g` y `meta` de
    `cargar_entradas_evento`, `dom` (la ficha del dominio) y `cfgmod`. Escribe `escenario_base.yaml` en `carpeta` si la corrida
    viene por `definicion`. Lo usan `correr` y las pruebas (test/app/ayudante_v31.py)."""
    sys.path.insert(0, str(RAIZ / "scripts"))
    sys.path.insert(0, str(RAIZ / "src"))
    import pandas as pd
    import yaml
    import ignicion as ignicion_libre
    from correr_escenario import opciones_v3            # src/v3.1/scripts/correr_escenario.py
    from incendios_sl import config as cfgmod
    from incendios_sl.simulation.entradas import cargar_entradas_evento

    pedido = {}
    if base.get("escenario"):
        if any(k not in ("cortafuegos", "dotaciones") for k in configuracion):
            raise ValueError("`configuracion` solo se combina con `base.definicion`; `base.escenario` se corre tal cual "
                             "(salvo `cortafuegos` y `dotaciones`)")
        nombre = str(base["escenario"])
        esc = cfgmod.cargar_corrida(nombre)
        ruta = cfgmod.dir_escenarios() / "corridas" / f"{nombre}.yaml"
    else:
        esc, pedido = ignicion_libre.aplicar(cfgmod, dict(base["definicion"]), configuracion)
        esc.setdefault("variante", variante_por_defecto)
        cruce_por_umbral(esc)
        ruta = Path(carpeta) / "escenario_base.yaml"
        ruta.write_text(yaml.safe_dump(esc, allow_unicode=True, sort_keys=False), encoding="utf-8")
        nombre = str(esc.get("nombre") or ruta.stem)

    hip = int(esc.get("hipotesis", 0))
    k_clase = {int(k): float(v) for k, v in (esc.get("k_clase") or {}).items()} or None
    v3 = opciones_v3(esc)
    ent, cfg, g, meta = cargar_entradas_evento(esc["evento"], hip, k_clase=k_clase, factor_waf=float(esc.get("factor_waf", 1.0)),
                                               k_global=esc.get("k_global"), ignicion=v3["ignicion"], modelo=v3["modelo"],
                                               barreras=v3["barreras"], contencion=v3["contencion"], extra_cfg=v3["extra_cfg"],
                                               parche_modelo=v3["parche_modelo"])
    if esc.get("horas"):
        ent.t_fin_utc = min(ent.t_fin_utc, ent.t_inicio_utc + pd.Timedelta(hours=float(esc["horas"])))
    dom = cfgmod.cargar_dominio(cfgmod.cargar_evento(esc["evento"])["dominio"])
    return {"esc": esc, "pedido": pedido, "ruta": ruta, "nombre": nombre, "ent": ent, "cfg": cfg, "g": g, "meta": meta,
            "dom": dom, "cfgmod": cfgmod}


def correr(base: dict, configuracion: dict, carpeta: Path, control: Control, variante_por_defecto: str) -> dict:
    salida = carpeta / "salida"
    salida.mkdir(parents=True, exist_ok=True)
    trazos_iniciales = list(configuracion.get("cortafuegos") or [])
    c = cargar(base, configuracion, carpeta, variante_por_defecto)
    from incendios_sl.simulation.motor import MOTIVOS, Simulacion
    esc, pedido, ruta, nombre = c["esc"], c["pedido"], c["ruta"], c["nombre"]
    ent, cfg, g, meta = c["ent"], c["cfg"], c["g"], c["meta"]

    # puntos que usa el motor: la celda de cada ignición y cuánto la corrió respecto del punto pedido
    from pyproj import Transformer
    a_lonlat = Transformer.from_crs(g.crs, "EPSG:4326", always_xy=True)
    usada = []
    for p, (fila, col, _) in zip(meta.get("puntos_ignicion") or [], ent.igniciones):
        f0, c0 = (int(v) for v in g.lonlat_a_rc(p["lon"], p["lat"]))
        lon, lat = a_lonlat.transform(g.xmin + (col + 0.5) * g.res, g.ymax - (fila + 0.5) * g.res)
        u = {"id": str(p.get("nombre", "")), "lon": round(lon, 7), "lat": round(lat, 7)}
        if (f0, c0) != (fila, col):
            u["desplazada_m"] = round(float(np.hypot(fila - f0, col - c0) * g.res), 0)
        usada.append(u)
    ign = {"ignicion": {"pedida": pedido, "usada": usada, "t_inicio_utc": str(ent.t_inicio_utc)}}

    grilla = {"crs": g.crs, "xmin": g.xmin, "ymax": g.ymax, "res": g.res, "filas": g.nfil, "cols": g.ncol}
    area_celda_ha = g.res ** 2 / 1e4
    estado = {"horas": 0, "detenida": False}

    def huella_min(sim) -> np.ndarray:
        return np.where(np.isfinite(sim.t_arr), sim.t_arr / 60.0, np.nan).astype("float32")

    malla = malla_viento(grilla, medio_paso=True)       # intercalada con la de v4.0 cuando se ven los dos

    def guardar_viento(sim) -> None:
        """Viento de la hora que terminó (el motor deja U10, V10 en m/s, hacia donde va, en `u10` y `v10`): solo se lee."""
        k = estado["horas"] - 1
        if k < 0:
            return
        try:
            sel = np.ix_(malla["filas"], malla["cols"])
            control.guardar_viento(k, sim.u10[sel] * 3.6, sim.v10[sel] * 3.6, malla,
                                   "WindNinja (relieve) con la velocidad y la dirección de la hora", momento="intervalo")
        except Exception as e:                       # el mapa del viento no corta la corrida
            control.aviso("error", mensaje=f"viento para el mapa (hora {k}): {type(e).__name__}: {e}", fatal=False)

    def avisar_hora(sim) -> None:
        guardar_viento(sim)
        control.listo(ent.t_inicio_utc, grilla)
        ha = float(np.count_nonzero(np.isfinite(sim.t_arr))) * area_celda_ha
        control.hora(estado["horas"], sim.t / 60.0, ha, int(sim.n_act[0]), huella_min(sim))
        estado["horas"] += 1

    class SimulacionControlada(Simulacion):
        def _tablas_hora(self, *a, **k):
            avisar_hora(self)
            if control.atender(self.t / 60.0):
                estado["detenida"] = True
                self.c.max_pasos = 0          # el bucle del motor corta al terminar el paso en curso y guarda normalmente
            return super()._tablas_hora(*a, **k)

        def _contener_hora(self, hora_idx, fraccion=1.0):
            """El motor lo llama en cada cambio de hora cuando la contención está encendida (la enciende el adaptador la
            primera vez que hay combate), ya con las tablas, el viento y las velocidades de la hora nueva. Acá no corre la
            contención de v3.1 sino el paso del combate común (combate.py)."""
            if not combate.habilitado:        # la corrida trae la contención propia del motor encendida: es la que corre
                return super()._contener_hora(hora_idx, fraccion)
            if not estado["detenida"]:
                control.combate(combate.paso_hora(self.t / 60.0), combate.capas())

    sim = SimulacionControlada(ent, cfg)
    interv = barreras_v31.IntervencionesV31(sim, cfg, g, c["dom"], carpeta)
    interv.habilitar_barreras()
    import combate_v31                        # importa el motor: recién ahora está en sys.path
    adaptador = combate_v31.AdaptadorV31(sim, g)
    combate = adaptador.combate = cb.Combate(adaptador)
    for i, d in enumerate(configuracion.get("dotaciones") or []):   # antes de iniciar: igual que en la pausa de t = 0
        r = combate.intervenir({"tipo": "dotacion", "datos": d}, 0.0)
        if r["estado"] == "rechazada":
            raise ValueError(f"dotación {i + 1} de antes de iniciar rechazada ({r['motivo']}); la corrida no se simula")

    def aplicar(entrada: dict, t: float) -> dict:
        if entrada["tipo"] not in iv.TIPOS_COMBATE:
            return interv.aplicar(entrada, t)
        r = combate.intervenir(entrada, t)
        if r["estado"] != "rechazada":
            control.guardar_combate(combate.capas())
        print(f"intervención {entrada['tipo']} en t = {float(t):g} min: {r['estado']}, {r['motivo']}", flush=True)
        return r
    iniciales = []
    for d in trazos_iniciales:                # antes de iniciar: lo mismo que aplicarlos en la pausa de t = 0
        r = interv.cortafuego(d, 0.0, inicial=True)
        iniciales.append({"estado": r["estado"], "motivo": r["motivo"], **d, **r["datos"]})
    exigir_cortafuegos_iniciales(iniciales)   # D-E3-31: uno rechazado corta la corrida antes de simular
    control.aplicar = aplicar
    sim.ejecutar()
    if not estado["detenida"]:
        avisar_hora(sim)                      # estado final: el motor no vuelve a llamar a _tablas_hora al terminar
    else:
        control.guardar_huella(huella_min(sim))
    sim.guardar(salida, grilla=g, extra={"entradas": meta})
    shutil.copy(ruta, salida / f"escenario_{nombre}.yaml")
    resumen_interv = interv.cerrar()

    ha_final = float(np.count_nonzero(np.isfinite(sim.t_arr))) * area_celda_ha
    if estado["detenida"]:
        motivo, texto = "detenida", "Detenida por el usuario."
    else:
        motivo, texto = str(sim.motivo), MOTIVOS.get(sim.motivo, "?")
    res = {"motivo_fin": motivo, "motivo_fin_texto": texto, "ha_final": round(ha_final, 2),
           "t_simulado_min": round(sim.t / 60.0, 3), "salida": "salida", "completa": not estado["detenida"],
           "archivos": sorted(p.name for p in salida.iterdir() if p.is_file()),
           "barreras": {"anchos_m": [float(a) for a in sim.ancho_tab], "modo_cruce": int(sim.modo_cruce)}} | ign
    if trazos_iniciales:
        res["cortafuegos_iniciales"] = iniciales
    if resumen_interv:
        res["intervenciones_v31"] = resumen_interv
    if combate.informe():
        res["combate"] = combate.informe()
    return res
