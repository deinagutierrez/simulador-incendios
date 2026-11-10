"""Genera los campos de viento horarios de WindNinja (diurno; por dominio o por puntos) de cada evento (docs/v3.1/04).

Uso:
  python scripts/generar_viento_horario.py --fuente windninja_diurno --exe C:/ruta/WindNinja_cli.exe
  python scripts/generar_viento_horario.py --fuente windninja_puntos --eventos SL-2024-MESILLA --procs 3 --hilos 6

Horas: desde la ignición recomendada de la ficha hasta max(ignición + 24 h, último foco VIIRS + 2 h), sin pasar el fin de la
simulación ni --max-horas (Las Lagunas: 120 h cubren la fase de propagación principal). Fuera de ese período la simulación
usa la biblioteca unitaria. Reanuda: las horas ya generadas no se repiten.
Salida: datos/inputSimulacion/viento/horario/<evento>_<fuente>/<AAAAMMDDTHH>.npz y malla.json.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from incendios_sl import config as cfgmod  # noqa: E402


def horas_evento(evento: str, max_horas: float) -> list[pd.Timestamp]:
    ev = cfgmod.cargar_evento(evento)
    r = ev.get("recomendada") or {}
    t0 = pd.Timestamp(ev["inicio"]["hora_utc_hipotesis"][int(r.get("hipotesis", 0))]).floor("h")
    t_fin = pd.Timestamp(ev["fin"]["fin_simulacion_utc"])
    p = cfgmod.dir_catalogo() / "hotspots_v3.1" / f"viirs_{evento}.csv"
    fin = t0 + pd.Timedelta(hours=24)
    if p.exists():
        hs = pd.read_csv(p)
        if len(hs):
            ult = (pd.to_datetime(hs["date"]).dt.tz_localize("UTC") + pd.to_timedelta(hs["acq_time_s"], unit="s")).max()
            fin = max(fin, ult.ceil("h") + pd.Timedelta(hours=2))
    fin = min(fin, t_fin, t0 + pd.Timedelta(hours=max_horas))
    return list(pd.date_range(t0, fin, freq="h"))


def _trabajo(evento: str, fuente: str, hora: pd.Timestamp, hilos: int) -> dict:
    from incendios_sl.wind.horario import GeneradorHorario
    dem = next((cfgmod.dir_entradas() / "dem").glob("dem_copernicus_glo30_viento_*.tif"))
    return GeneradorHorario(evento, fuente, dem, hilos=hilos).correr_hora(hora) | {"evento": evento}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fuente", choices=["windninja_diurno", "windninja_puntos"], required=True)
    ap.add_argument("--eventos", default=None); ap.add_argument("--max-horas", type=float, default=120.0)
    ap.add_argument("--procs", type=int, default=3); ap.add_argument("--hilos", type=int, default=6)
    ap.add_argument("--exe", default=None, help="ruta de WindNinja_cli.exe (si no está en config/herramientas.yaml ni en WINDNINJA_CLI)")
    a = ap.parse_args()
    if a.exe:
        os.environ["WINDNINJA_CLI"] = a.exe
    eventos = a.eventos.split(",") if a.eventos else sorted(p.stem for p in (cfgmod.dir_escenarios() / "eventos").glob("SL-*.yaml"))
    tareas = [(e, h) for e in eventos for h in horas_evento(e, a.max_horas)]
    print(f"{len(tareas)} horas en {len(eventos)} eventos ({a.fuente})", flush=True)
    t0 = time.time(); n = 0
    with ProcessPoolExecutor(a.procs) as ex:
        fut = {ex.submit(_trabajo, e, a.fuente, h, a.hilos): (e, h) for e, h in tareas}
        for f in as_completed(fut):
            e, h = fut[f]; n += 1
            try:
                r = f.result()
                if n % 20 == 0 or r["estado"] != "ya estaba":
                    print(f"[{n}/{len(tareas)} {time.time() - t0:.0f} s] {e} {h:%Y-%m-%d %H} UTC {r['estado']} {r.get('segundos', '')}", flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f"ERROR {e} {h}: {exc!r}", flush=True)
    print("listo", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
