"""Ejecuta una simulación de un evento configurado y guarda los resultados.

Uso:
    python scripts/simular.py --evento SL-2024-LASLAGUNAS [--hipotesis 0] [--run-id nombre] [--k 1=1.0,3=1.2] [--horas 48]
Salidas en resultados/v3.1/<run_id>/: t_llegada_s.tif, estado_final.tif, serie_horaria.csv, registro.json.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from incendios_sl import config as cfgmod  # noqa: E402
from incendios_sl.simulation.entradas import cargar_entradas_evento  # noqa: E402
from incendios_sl.simulation.motor import Simulacion  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--evento", required=True)
    ap.add_argument("--hipotesis", type=int, default=0, help="índice de hora de ignición en la ficha del evento")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--k", default=None, help="factores k_clase, p. ej. 1=1.0,3=1.2")
    ap.add_argument("--horas", type=float, default=None, help="limitar la duración simulada (h)")
    ap.add_argument("--sin-viento", action="store_true")
    ap.add_argument("--dt", type=float, default=None)
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    k = {int(x.split("=")[0]): float(x.split("=")[1]) for x in a.k.split(",")} if a.k else None
    ent, cfg, g, meta = cargar_entradas_evento(a.evento, a.hipotesis, k, sin_viento=a.sin_viento)
    if a.horas:
        ent.t_fin_utc = min(ent.t_fin_utc, ent.t_inicio_utc + pd.Timedelta(hours=a.horas))
    if a.dt:
        cfg.dt_s = a.dt
    run_id = a.run_id or f"{a.evento}_h{a.hipotesis}_{time.strftime('%Y%m%dT%H%M%S')}"
    out = cfgmod.dir_resultados() / run_id
    sim = Simulacion(ent, cfg)
    def cb(s):
        logging.info("%s | quemadas %s ha | activas %d | T %.1f HR %.0f v %.1f dir %.0f m1h %.1f | %.0fs", s["time_utc"], f"{s['ha_quemadas']:.0f}", s["celdas_activas"],
                     s["temperature_2m"], s["relative_humidity_2m"], s["wind_speed_10m"], s["wind_direction_10m"], s["m_1h_pct"], s["segundos_cpu"])
    reg = sim.ejecutar(callback=cb)
    rutas = sim.guardar(out, grilla=g, extra={"entradas": meta})
    print("Resultados:", {k: str(v) for k, v in rutas.items()})
    print({k: reg[k] for k in ("motivo_fin_texto", "t_simulado_utc", "pasos", "segundos_cpu", "celdas_quemadas", "ha_quemadas")})
    return 0


if __name__ == "__main__":
    sys.exit(main())
