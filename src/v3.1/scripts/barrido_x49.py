"""Barrido de hora y de punto único de ignición para un evento del lote X-49 con v3.1 (envoltorio de scripts/barrido_libre.py,
docs/v3.1/02), sin editar la ficha. Uso (desde src/v3.1):

  # 1) hora: cada 2 h en las 14 h previas al primer pase VIIRS + las hipótesis de la ficha, para cada ignición pedida
  python -I scripts/barrido_x49.py --modo hora --evento SL-2022-LATOTORA --igniciones snmf,alt0,alt1 --variante libre_v2 \
      --salida ../../resultados/v3.1/paso2_hora_x49/barrido_hora_latotora.csv
  # 2) punto único: 40 candidatos de grilla sobre la cicatriz + cada punto de `ignicion.puntos` por separado, a las horas dadas
  python -I scripts/barrido_x49.py --modo punto --evento SL-2022-LATOTORA --horas 2022-11-16T14:00Z,2022-11-16T16:00Z \
      --salida ../../resultados/v3.1/paso2_hora_x49/barrido_punto_unico_latotora.csv
  # 3) control de hora con los mejores puntos (lon,lat separados por ;)
  python -I scripts/barrido_x49.py --modo hora --evento SL-2022-LATOTORA --puntos "-65.7564,-32.6557;-65.7644,-32.6490" \
      --salida ../../resultados/v3.1/paso2_hora_x49/barrido_hora_punto_unico_latotora.csv

Métricas: IoU a igual superficie, fracción de primeras detecciones a tiempo (hotspots_v3.1) y puntaje = media de ambas.
`--listar` muestra las corridas sin ejecutarlas. Resultado: CSV ordenado por hora y puntaje.
"""
from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import barrido_libre as bl  # noqa: E402
from incendios_sl import config as cfgmod  # noqa: E402


def trabajos_de(a, ev: dict) -> list[tuple]:
    t = []
    if a.modo == "hora":
        cands = sorted(set(bl.candidatos_hora(ev, a.paso_h) + [pd.Timestamp(x) for x in ev["inicio"]["hora_utc_hipotesis"]]))
        if a.puntos:
            for k, s in enumerate(a.puntos.split(";")):
                lon, lat = (float(x) for x in s.split(","))
                t += [(f"pt{k}", h, [{"nombre": f"punto fijo {k}", "lon": lon, "lat": lat}]) for h in cands]
        else:
            for ign in a.igniciones.split(","):
                t += [(ign, h, None) for h in cands]
    else:
        pts = bl.puntos_candidatos(a.evento, a.n_puntos)
        pts += [{"nombre": f"foco {p.get('nombre')}", "lon": p["lon"], "lat": p["lat"]} for p in ev["ignicion"]["puntos"]]
        for h in a.horas.split(","):
            t += [(None, pd.Timestamp(h), [p]) for p in pts]
    return t


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modo", choices=["hora", "punto"], required=True); ap.add_argument("--evento", required=True)
    ap.add_argument("--igniciones", default="snmf", help="modo hora: snmf,alt0,… de la ficha"); ap.add_argument("--puntos", default="", help="modo hora: lon,lat;lon,lat")
    ap.add_argument("--horas", default="", help="modo punto: horas UTC separadas por coma"); ap.add_argument("--variante", default="libre_v2")
    ap.add_argument("--n-puntos", type=int, default=40); ap.add_argument("--paso-h", type=float, default=2.0)
    ap.add_argument("--procs", type=int, default=8); ap.add_argument("--salida", required=True); ap.add_argument("--listar", action="store_true")
    a = ap.parse_args()
    ev = cfgmod.cargar_evento(a.evento)
    trabajos = trabajos_de(a, ev)
    print(len(trabajos), "corridas", flush=True)
    if a.listar:
        for ign, h, p in trabajos:
            print(" ", ign or (p[0]["nombre"] if p else "?"), h, (p[0]["lon"], p[0]["lat"]) if p else "")
        return 0
    sal = Path(a.salida); sal.parent.mkdir(parents=True, exist_ok=True)
    filas = []; t_ini = time.time()
    with ProcessPoolExecutor(a.procs) as ex:
        fut = {ex.submit(bl.correr, a.evento, h, 1.0, a.variante, None if (ign is None or ign.startswith("pt")) else ign, p): (ign, h, p) for ign, h, p in trabajos}
        for f in as_completed(fut):
            ign, h, p = fut[f]
            try:
                r = f.result()
            except Exception as exc:  # noqa: BLE001
                print("ERROR", ign, h, repr(exc), flush=True); continue
            r["ignicion_pedida"] = ign; r["nombre_punto"] = p[0]["nombre"] if p else None; filas.append(r)
            print(f"{str(r['nombre_punto'] or r['ignicion']):28s} {r['t_inicio_utc'][:16]} ({r['lon']}, {r['lat']}) IoU={r['iou_igual_sup']} "
                  f"h_sup={r['horas_hasta_sup']} a_tiempo={r['frac_a_tiempo']} err={r['error_mediano_h']} puntaje={r['puntaje']} {r['segundos']}s", flush=True)
            pd.DataFrame(filas).sort_values(["t_inicio_utc", "puntaje"], ascending=[True, False]).to_csv(sal, index=False)
    print("salida:", sal, f"{time.time() - t_ini:.0f} s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
