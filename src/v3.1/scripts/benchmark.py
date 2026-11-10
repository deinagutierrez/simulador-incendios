"""Pruebas de escalabilidad del simulador (Etapa 5).

Mide tiempo de ejecución, memoria pico y almacenamiento para:
  A) grillas crecientes (sintéticas, homogéneas) con frentes pequeños y con frentes grandes (varias igniciones);
  B) pasos temporales crecientes (Δt) sobre la misma configuración;
  C) el evento real completo (SL-2024-LASLAGUNAS, 21 días) con el pipeline de datos de la Etapa 3;
  D) costo de componer el viento horario (biblioteca WindNinja -> 30 m).
Salida: resultados/v3.1/benchmark/benchmark_<fecha>.json y tabla en consola.
"""
from __future__ import annotations

import json
import os
import sys
import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from incendios_sl import config as cfgmod  # noqa: E402
from incendios_sl.simulation.motor import Simulacion, ConfigSimulacion  # noqa: E402
from incendios_sl.simulation.sintetico import entradas_homogeneas, tabla_prueba  # noqa: E402

PROC = psutil.Process()


def pico_gb() -> float:
    mi = PROC.memory_info()
    return round(getattr(mi, "peak_wset", mi.rss) / 1e9, 3)


def rss_gb() -> float:
    return round(PROC.memory_info().rss / 1e9, 3)


def correr(ent, cfg, etiqueta, extra=None):
    r0 = rss_gb(); t0 = time.time()
    sim = Simulacion(ent, cfg); t1 = time.time()
    reg = sim.ejecutar(); t2 = time.time()
    act = max((x["celdas_activas"] for x in sim.serie), default=0)
    fila = {"prueba": etiqueta, "celdas_grilla": int(ent.mascara.size), "km2": round(ent.mascara.size * ent.res_m ** 2 / 1e6, 1),
            "horas": round((ent.t_fin_utc - ent.t_inicio_utc).total_seconds() / 3600, 1), "dt_s": cfg.dt_s, "pasos": reg["pasos"],
            "s_init": round(t1 - t0, 2), "s_simulacion": round(t2 - t1, 2), "ms_por_paso": round(1000 * (t2 - t1) / max(reg["pasos"], 1), 2),
            "celdas_quemadas": reg["celdas_quemadas"], "ha_quemadas": round(reg["ha_quemadas"], 1), "frente_max": act,
            "rss_antes_gb": r0, "rss_despues_gb": rss_gb(), "pico_proceso_gb": pico_gb(), "motivo_fin": reg["motivo_fin"]}
    fila.update(extra or {})
    with open(cfgmod.dir_resultados() / "benchmark" / "parcial.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(fila, ensure_ascii=False, default=str) + "\n")
    print({k: v for k, v in fila.items() if k not in ("rss_antes_gb",)})
    return fila, sim


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--secciones", default="ABCD"); a = ap.parse_args(); sec = a.secciones.upper()
    out_dir = cfgmod.dir_resultados() / "benchmark"; out_dir.mkdir(parents=True, exist_ok=True)
    tab = tabla_prueba(); filas = []
    # calentamiento (compilación numba)
    correr(entradas_homogeneas(n=101, clase=1, horas=2, vel=3.0, tabla=tab), ConfigSimulacion(), "calentamiento")

    # A) grillas crecientes: lados equivalentes a 500, 1000, 1500, 2000, 2500 km²
    lados = {"500 km2": 745, "1000 km2": 1054, "1500 km2": 1291, "2000 km2": 1491, "2500 km2": 1671}
    for nombre, n in (lados.items() if "A" in sec else []):
        # frente pequeño: una ignición, 48 h, viento 6 m/s
        e = entradas_homogeneas(n=n, clase=1, horas=48, vel=6.0, dir_desde=250.0, tabla=tab, ignicion=[(n // 2, n // 2, 0.0)])
        f, _ = correr(e, ConfigSimulacion(vecindad=16, dt_s=60), f"A1 una ignición 48 h | {nombre}"); filas.append(f)
        # frente grande: 9 igniciones en malla, 72 h -> quema una fracción importante del dominio
        k = n // 4
        ign = [(k * i, k * j, 0.0) for i in (1, 2, 3) for j in (1, 2, 3)]
        e = entradas_homogeneas(n=n, clase=1, horas=72, vel=6.0, dir_desde=250.0, tabla=tab, ignicion=ign)
        f, _ = correr(e, ConfigSimulacion(vecindad=16, dt_s=60), f"A2 nueve igniciones 72 h | {nombre}"); filas.append(f)

    # B) paso temporal
    for dt in ((30, 60, 120, 300, 600) if "B" in sec else ()):
        e = entradas_homogeneas(n=1291, clase=1, horas=48, vel=6.0, dir_desde=250.0, tabla=tab)
        f, _ = correr(e, ConfigSimulacion(vecindad=16, dt_s=dt), f"B dt={dt} s | 1500 km2"); filas.append(f)
    # B') 8 vs 16 vecinos
    if "B" in sec:
        e = entradas_homogeneas(n=1291, clase=1, horas=48, vel=6.0, dir_desde=250.0, tabla=tab)
        f, _ = correr(e, ConfigSimulacion(vecindad=8, dt_s=60), "B 8 vecinos | 1500 km2"); filas.append(f)

    # D) costo de composición del viento horario
    try:
        if not ("C" in sec or "D" in sec):
            raise StopIteration
        from incendios_sl.simulation.entradas import cargar_entradas_evento
        ent, cfg, g, meta = cargar_entradas_evento("SL-2024-LASLAGUNAS", 1)
        t0 = time.time(); n = 20
        for i in range(n):
            ent.viento(5.0, i * 17.0)
        filas.append({"prueba": "D composición viento horario (biblioteca -> 30 m)", "ms_por_hora": round(1000 * (time.time() - t0) / n, 1)})
        print(filas[-1])
        # C) evento real completo, dos pasos temporales
        for dt in ((60, 30) if "C" in sec else ()):
            ent, cfg, g, meta = cargar_entradas_evento("SL-2024-LASLAGUNAS", 1)
            cfg.dt_s = dt
            f, sim = correr(ent, cfg, f"C evento real 2024 completo (hipotesis 12:00) dt={dt}", {"t_fin_simulado": None})
            f["t_fin_simulado"] = sim.registro["t_simulado_utc"]; f["motivo_fin_texto"] = sim.registro["motivo_fin_texto"]
            rutas = sim.guardar(out_dir / f"evento_real_dt{dt}", grilla=g, extra={"entradas": meta})
            f["almacenamiento_MB"] = {k: round(os.path.getsize(v) / 1e6, 2) for k, v in rutas.items()}
            filas.append(f)
    except StopIteration:
        pass
    except Exception as e:  # pragma: no cover
        print("evento real no disponible:", e)
        filas.append({"prueba": "C evento real", "error": str(e)[:300]})

    res = {"fecha_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "cpu": psutil.cpu_count(logical=True), "ram_gb": round(psutil.virtual_memory().total / 1e9, 1), "filas": filas}
    p = out_dir / f"benchmark_{time.strftime('%Y%m%dT%H%M%S')}.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, ensure_ascii=False, default=str)
    print("guardado", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
