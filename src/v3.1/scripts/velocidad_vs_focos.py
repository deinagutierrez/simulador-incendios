"""Velocidad de propagación contra los satélites: para cada primera detección VIIRS de un lugar, horas entre la llegada
simulada y la detección (docs/v3.1/velocidad_vs_focos.md).

Uso:
  python scripts/velocidad_vs_focos.py --corridas ../../resultados/v3.0/SL-2024-MESILLA-20240902-h2-alt2-librev2 [...] [--salida tabla.csv]
Cada corrida necesita t_llegada_s.tif (etiqueta t_inicio_utc); los focos salen de catalogo/hotspots_v3.1/viirs_<evento>.csv.
Lectura: el fuego llegó a un lugar entre la pasada anterior sin foco (≤ 13 h antes) y la detección, así que la diferencia
(sim − detección) debería caer en [−13 h, +1 h]: menos de −13 h = modelo demasiado rápido; más de +1 h = demasiado lento.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from incendios_sl import config as cfgmod  # noqa: E402
from incendios_sl.grilla import Grilla  # noqa: E402


def diferencias(d: Path, tolerancia_m: float = 375.0) -> tuple[str, pd.Timestamp, pd.DataFrame, pd.DataFrame]:
    """(evento, t_inicio, focos, primeras detecciones con dif_h = llegada simulada − detección)."""
    evento = "-".join(d.name.split("-")[:3])
    with rasterio.open(d / "t_llegada_s.tif") as ds:
        ta = ds.read(1).astype(float); t0 = pd.Timestamp(ds.tags()["t_inicio_utc"])
    ta[ta < 0] = np.inf
    g = Grilla.desde_raster(d / "t_llegada_s.tif")
    hs = pd.read_csv(cfgmod.dir_catalogo() / "hotspots_v3.1" / f"viirs_{evento}.csv")
    if not len(hs):
        return evento, t0, hs, pd.DataFrame(columns=["t_det", "dif_h"])
    hs["t_det"] = pd.to_datetime(hs["date"]).dt.tz_localize("UTC") + pd.to_timedelta(hs["acq_time_s"], unit="s")
    hs = hs.sort_values("t_det").reset_index(drop=True)
    r, c = g.lonlat_a_rc(hs.lon.to_numpy(), hs.lat.to_numpy()); hs["f"] = r; hs["c"] = c
    k = int(np.ceil(tolerancia_m / g.res)); visto = np.zeros(ta.shape, bool); prim = []
    for t, x in hs.groupby("t_det", sort=True):
        for q in x.itertuples():
            if not visto[q.f, q.c]:
                v = ta[max(0, q.f - k):q.f + k + 1, max(0, q.c - k):q.c + k + 1]; v = v[np.isfinite(v)]
                prim.append({"t_det": t, "dif_h": (v.min() - (t - t0).total_seconds()) / 3600 if v.size else np.nan})
        for q in x.itertuples():          # el entorno se marca al cerrar la pasada
            visto[max(0, q.f - k):q.f + k + 1, max(0, q.c - k):q.c + k + 1] = True
    return evento, t0, hs, pd.DataFrame(prim)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corridas", nargs="+", required=True); ap.add_argument("--salida", default=None)
    ap.add_argument("--ventana-h", type=float, default=13.0)
    a = ap.parse_args()
    filas = []
    for x in a.corridas:
        evento, t0, hs, p = diferencias(Path(x))
        fila = {"corrida": Path(x).name, "evento": evento, "ignicion_utc": str(t0), "focos": len(hs), "primeras_det": len(p)}
        if len(p):
            dh = p.dif_h.dropna()
            fila.update({"primer_foco_utc": str(hs.t_det.iloc[0]), "dif_mediana_h": round(dh.median(), 1),
                         "dif_p25_h": round(dh.quantile(.25), 1), "dif_p75_h": round(dh.quantile(.75), 1),
                         "rapido": round((dh < -a.ventana_h).mean(), 2), "en_ventana": round(((dh >= -a.ventana_h) & (dh <= 1)).mean(), 2),
                         "lento": round((dh > 1).mean(), 2), "no_alcanza": round(p.dif_h.isna().mean(), 2)})
        filas.append(fila)
    df = pd.DataFrame(filas)
    pd.set_option("display.width", 250); print(df.to_string(index=False))
    if a.salida:
        Path(a.salida).parent.mkdir(parents=True, exist_ok=True); df.to_csv(a.salida, index=False); print("salida:", a.salida)
    return 0


if __name__ == "__main__":
    sys.exit(main())
