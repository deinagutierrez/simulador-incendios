"""Conduce al motor v3.1 sin modificarlo.

Sigue el camino de src/v3.1/scripts/correr_escenario.py sin validación (cargar_entradas_evento, Simulacion.ejecutar,
guardar) y solo agrega un punto de control: una subclase de `Simulacion` que redefine `_tablas_hora`, el método que el
motor llama al empezar cada hora simulada, antes de calcular el viento de esa hora. Ningún archivo de src/v3.1 cambia.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import numpy as np

from control import Control

REPO = Path(__file__).resolve().parents[2]
RAIZ = REPO / "src" / "v3.1"


def correr(base: dict, configuracion: dict, carpeta: Path, control: Control, variante_por_defecto: str) -> dict:
    sys.path.insert(0, str(RAIZ / "scripts"))
    sys.path.insert(0, str(RAIZ / "src"))
    import pandas as pd
    import yaml
    import ignicion as ignicion_libre
    from correr_escenario import opciones_v3            # src/v3.1/scripts/correr_escenario.py
    from incendios_sl import config as cfgmod
    from incendios_sl.simulation.entradas import cargar_entradas_evento
    from incendios_sl.simulation.motor import MOTIVOS, Simulacion

    salida = carpeta / "salida"
    salida.mkdir(parents=True, exist_ok=True)

    pedido = {}
    if base.get("escenario"):
        if configuracion:
            raise ValueError("`configuracion` solo se combina con `base.definicion`; `base.escenario` se corre tal cual")
        nombre = str(base["escenario"])
        esc = cfgmod.cargar_corrida(nombre)
        ruta = cfgmod.dir_escenarios() / "corridas" / f"{nombre}.yaml"
    else:
        esc, pedido = ignicion_libre.aplicar(cfgmod, dict(base["definicion"]), configuracion)
        esc.setdefault("variante", variante_por_defecto)
        ruta = carpeta / "escenario_base.yaml"
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

    def avisar_hora(sim) -> None:
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

    sim = SimulacionControlada(ent, cfg)
    sim.ejecutar()
    if not estado["detenida"]:
        avisar_hora(sim)                      # estado final: el motor no vuelve a llamar a _tablas_hora al terminar
    else:
        control.guardar_huella(huella_min(sim))
    sim.guardar(salida, grilla=g, extra={"entradas": meta})
    shutil.copy(ruta, salida / f"escenario_{nombre}.yaml")

    ha_final = float(np.count_nonzero(np.isfinite(sim.t_arr))) * area_celda_ha
    if estado["detenida"]:
        motivo, texto = "detenida", "Detenida por el usuario."
    else:
        motivo, texto = str(sim.motivo), MOTIVOS.get(sim.motivo, "?")
    return {"motivo_fin": motivo, "motivo_fin_texto": texto, "ha_final": round(ha_final, 2),
            "t_simulado_min": round(sim.t / 60.0, 3), "salida": "salida", "completa": not estado["detenida"],
            "archivos": sorted(p.name for p in salida.iterdir() if p.is_file())} | ign
