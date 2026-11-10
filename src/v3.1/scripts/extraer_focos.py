"""Extrae los focos VIIRS de cada evento a partir del archivo provincial (FIRMS, VIIRS SNPP 2012-2026) y de los focos
ya descargados de GEE (que suman NOAA-20 en 2023-2024), sin depender de GEE.

Uso:
  python scripts/extraer_focos.py                       # los eventos de escenarios/v3.1/eventos
  python scripts/extraer_focos.py --eventos SL-2023-RINCON --radio-m 750

Criterio: detecciones entre el día anterior a la primera hipótesis de ignición y el fin de la simulación, a ≤ radio_m del
borde de la cicatriz de referencia (VIIRS 375 m: el centro del píxel puede caer fuera aunque el fuego esté dentro).
Salida: datos/inputSimulacion/catalogo/hotspots_v3.1/viirs_<evento>.csv (mismas columnas que catalogo/hotspots:
date, sat, acq_time_s, lon, lat, frp, conf, daynight, más dist_cicatriz_m y fuente) y resumen_focos.csv.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from incendios_sl import config as cfgmod  # noqa: E402
from incendios_sl.grilla import leer_raster  # noqa: E402

PROVINCIAL = "viirs_snpp_san_luis_recortado.csv"


def leer_provincial(path: Path) -> pd.DataFrame:
    """FIRMS (latitude, longitude, acq_date, acq_time HHMM UTC…) -> columnas del catálogo."""
    d = pd.read_csv(path, low_memory=False)
    hhmm = d["acq_time"].astype(int)
    return pd.DataFrame({"date": d["acq_date"].astype(str), "sat": "SNPP_VIIRS", "acq_time_s": (hhmm // 100) * 3600 + (hhmm % 100) * 60,
                         "lon": d["longitude"], "lat": d["latitude"], "frp": d["frp"], "conf": d["confidence"].astype(str),
                         "daynight": (d["daynight"] == "D").astype(int), "fuente": "FIRMS " + d["fuente_sensor"].astype(str)})


def extraer(evento: str, prov: pd.DataFrame, radio_m: float) -> pd.DataFrame:
    ev = cfgmod.cargar_evento(evento)
    ref, g, _ = leer_raster(cfgmod.dir_entradas() / "eventos" / evento / f"cicatriz_referencia_{evento}.tif")
    dist = ndimage.distance_transform_edt(ref != 1) * g.res      # m al píxel quemado más cercano
    t0 = min(pd.Timestamp(t) for t in ev["inicio"]["hora_utc_hipotesis"]).tz_convert(None).normalize() - pd.Timedelta(days=1)
    t1 = pd.Timestamp(ev["fin"]["fin_simulacion_utc"]).tz_convert(None)
    partes = [prov]
    gee = cfgmod.dir_catalogo() / "hotspots" / f"viirs_{evento}.csv"
    if gee.exists() and gee.stat().st_size > 10:
        x = pd.read_csv(gee); x["fuente"] = "GEE LANCE/FIRMS (obtener_focos.py)"; partes.append(x)
    d = pd.concat(partes, ignore_index=True)
    t = pd.to_datetime(d["date"]) + pd.to_timedelta(d["acq_time_s"], unit="s")
    d = d[(t >= t0) & (t <= t1)].copy(); d["_t"] = t[d.index]
    # una misma pasada puede venir de FIRMS y de GEE con 1-2 min de diferencia y posiciones distintas (punto vs centro de
    # píxel muestreado): se descartan las pasadas de GEE que tienen una de FIRMS del mismo satélite a ≤ 10 min (GEE sólo suma NOAA-20)
    firms = d[d.fuente.str.startswith("FIRMS")]
    pas_f = firms.groupby("sat")["_t"].unique()
    dup = d.apply(lambda r: (not r.fuente.startswith("FIRMS")) and r.sat in pas_f.index
                  and bool(np.any(np.abs(pas_f[r.sat] - r._t) <= pd.Timedelta(minutes=10))), axis=1) if len(d) else pd.Series(dtype=bool)
    d = d[~dup].drop(columns="_t")
    r, c = g.lonlat_a_rc(d["lon"].to_numpy(), d["lat"].to_numpy())
    ok = g.dentro(r, c)
    d = d[ok].copy(); d["dist_cicatriz_m"] = dist[r[ok], c[ok]]
    d = d[d["dist_cicatriz_m"] <= radio_m]
    # el mismo píxel puede venir de FIRMS y de GEE: se conserva una sola detección por satélite, pasada y posición
    d["_k"] = d["sat"] + d["date"] + d["acq_time_s"].astype(str) + d["lat"].round(3).astype(str) + d["lon"].round(3).astype(str)
    d = d.drop_duplicates("_k").drop(columns="_k").sort_values(["date", "acq_time_s"])
    return d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eventos", default=None, help="ids separados por coma (por defecto, todos los de escenarios/v3.1/eventos)")
    ap.add_argument("--radio-m", type=float, default=750.0)
    a = ap.parse_args()
    eventos = a.eventos.split(",") if a.eventos else sorted(p.stem for p in (cfgmod.dir_escenarios() / "eventos").glob("SL-*.yaml"))
    prov = leer_provincial(cfgmod.dir_crudos() / PROVINCIAL)
    out = cfgmod.dir_catalogo() / "hotspots_v3.1"; out.mkdir(parents=True, exist_ok=True)
    filas = []
    for e in eventos:
        d = extraer(e, prov, a.radio_m)
        d.to_csv(out / f"viirs_{e}.csv", index=False)
        pas = d.groupby(["date", "acq_time_s", "sat"]).size()
        filas.append({"evento": e, "focos": len(d), "pasadas": len(pas), "snpp": int((d.sat == "SNPP_VIIRS").sum()),
                      "noaa20": int((d.sat == "NOAA20_VIIRS").sum()), "primera": f"{d.date.iloc[0]} {d.acq_time_s.iloc[0] // 3600:02d}:{d.acq_time_s.iloc[0] % 3600 // 60:02d}" if len(d) else None,
                      "dias": ", ".join(sorted(d.date.unique()))})
        print(filas[-1], flush=True)
    pd.DataFrame(filas).to_csv(out / "resumen_focos.csv", index=False)
    print("salida:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
