"""Búsqueda de punto único y de hora de ignición con v4.0 (modelo_v3, variante libre, SIN parada en cicatriz, sin figuras ni
métricas) para un evento del lote X-49. Mismos candidatos que scripts/barrido_x49.py de v3.1: 40 puntos de grilla sobre la
cicatriz dilatada 300 m + cada punto de `ignicion.puntos` de la ficha por separado. Uso (desde src/v4.0):

  python -I scripts/busqueda_punto_x49.py --modo punto --evento SL-2022-LATOTORA --horas 2022-11-16T14:00Z,2022-11-16T16:00Z --procs 8
  python -I scripts/busqueda_punto_x49.py --modo hora  --evento SL-2022-LATOTORA --puntos "-65.7679,-32.6506;-65.7644,-32.6490" --procs 8

Cada corrida queda en resultados/v4.0/busqueda_punto_x49/<evento>/<run_id>/ (hora_llegada_min.tif, registro.json…) y dura hasta
el último foco VIIRS + 1 h (hotspots_v3.1), con un mínimo de 48 h y sin pasar `fin.fin_simulacion_utc` de la ficha. Las métricas de v3.1 se calculan después con src/v3.1/scripts/evaluar_x49.py
--carpeta resultados/v4.0/busqueda_punto_x49/<evento>. Al final conviene borrar las carpetas de corridas y dejar los CSV.
"""
from __future__ import annotations

import argparse
import copy
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve()
RAIZ_REPO = AQUI.parents[3]


def _init():
    os.environ["INCENDIOS_SL_RESULTADOS"] = str(RAIZ_REPO / "resultados" / "v4.0" / "busqueda_punto_x49")
    sys.path.insert(0, str(AQUI.parents[1] / "src")); sys.path.insert(0, str(AQUI.parent))
    import logging
    logging.disable(logging.WARNING)


def puntos_candidatos(evento: str, n: int = 40) -> list[dict]:
    """Igual que barrido_libre.puntos_candidatos de v3.1: grilla regular de ~n puntos sobre la cicatriz principal dilatada 300 m."""
    import rasterio
    from pyproj import Transformer
    from scipy import ndimage
    from incendios_sl import config as cfg4
    p = cfg4.dir_entradas() / "eventos" / evento / f"cicatriz_referencia_{evento}.tif"
    with rasterio.open(p) as s:
        ref = s.read(1) == 1; T = s.transform; crs = s.crs
    lab, nlab = ndimage.label(ref, structure=np.ones((3, 3)))
    tam = ndimage.sum(ref, lab, range(1, nlab + 1))
    principal = ndimage.binary_dilation(np.isin(lab, 1 + np.nonzero(tam >= 0.15 * ref.sum())[0]), iterations=10)
    rr, cc = np.nonzero(principal)
    paso = max(1, int(round(np.sqrt(len(rr) / n))))
    sel = (rr % paso == (rr.min() + paso // 2) % paso) & (cc % paso == (cc.min() + paso // 2) % paso)
    tr = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    out = []
    for k, (r, c) in enumerate(zip(rr[sel], cc[sel])):
        x, y = T * (c + 0.5, r + 0.5); lo, la = tr.transform(x, y)
        out.append({"nombre": f"grilla {k}", "lon": round(float(lo), 5), "lat": round(float(la), 5)})
    return out


def fin_focos(evento: str) -> pd.Timestamp:
    from incendios_sl import config as cfg4
    p = cfg4.dir_catalogo() / "hotspots_v3.1" / f"viirs_{evento}.csv"
    if not p.exists():
        p = cfg4.dir_catalogo() / "hotspots" / f"viirs_{evento}.csv"
    f = pd.read_csv(p)
    t = pd.to_datetime(f["date"]).dt.tz_localize("UTC") + pd.to_timedelta(f["acq_time_s"], unit="s")
    return (t.max() + pd.Timedelta(hours=1)).ceil("h")


def correr_uno(evento: str, etiqueta: str, lon: float, lat: float, t0_iso: str, fin_iso: str) -> dict:
    _init()
    import yaml
    from incendios_sl import config as cfg4
    import correr_escenario
    orig = cfg4.cargar_evento
    t0 = pd.Timestamp(t0_iso); fin = pd.Timestamp(fin_iso)

    def cargar_mod(i):
        e = copy.deepcopy(orig(i))
        if i == evento:
            e["inicio"]["hora_utc_hipotesis"] = list(e["inicio"]["hora_utc_hipotesis"]) + [t0.strftime("%Y-%m-%dT%H:%M:%SZ")]
            e["ignicion_alternativas"] = list(e.get("ignicion_alternativas") or []) + [{"fuente": "búsqueda v4.0", "puntos": [{"nombre": etiqueta, "lon": lon, "lat": lat}]}]
        return e
    cfg4.cargar_evento = cargar_mod
    e0 = orig(evento); n_hip = len(e0["inicio"]["hora_utc_hipotesis"]); n_alt = len(e0.get("ignicion_alternativas") or [])
    # al menos 48 h (que alcance la superficie de la cicatriz para el IoU a igual superficie), sin pasar el fin de la ficha
    fin = max(fin, t0 + pd.Timedelta(hours=48)); fin = min(fin, pd.Timestamp(e0["fin"]["fin_simulacion_utc"]))
    rid = "busq_" + "".join(ch for ch in etiqueta if ch.isalnum()) + f"_{t0.strftime('%d%H')}Z"
    esc = {"descripcion": f"búsqueda de punto único con v4.0: {etiqueta} ({lon}, {lat}) a las {t0}", "evento": evento, "hipotesis": n_hip,
           "ignicion": f"alt{n_alt}", "variante": "libre", "horas": round((fin - t0).total_seconds() / 3600.0, 2),
           "parar_en_cicatriz": "off", "validar": False, "figuras": False, "run_id": rid}
    ruta = Path(os.environ["INCENDIOS_SL_RESULTADOS"]) / "_escenarios" / f"{rid}.yaml"; ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(yaml.safe_dump(esc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    import contextlib, io
    t_ini = time.time()
    with contextlib.redirect_stdout(io.StringIO()):
        carpeta = correr_escenario.correr(esc, ruta, rid, verificar_sha=False, solo_simular=True, verbose=False)
    return {"run_id": rid, "etiqueta": etiqueta, "lon": lon, "lat": lat, "t0_utc": str(t0), "carpeta": str(carpeta), "segundos": round(time.time() - t_ini, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modo", choices=["punto", "hora"], required=True); ap.add_argument("--evento", required=True)
    ap.add_argument("--horas", default="", help="modo punto: horas UTC separadas por coma"); ap.add_argument("--puntos", default="", help="modo hora: lon,lat;lon,lat")
    ap.add_argument("--n-puntos", type=int, default=40); ap.add_argument("--procs", type=int, default=8); ap.add_argument("--listar", action="store_true")
    a = ap.parse_args()
    _init()
    from incendios_sl import config as cfg4
    ev = cfg4.cargar_evento(a.evento)
    fin = fin_focos(a.evento)
    trabajos = []
    if a.modo == "punto":
        pts = puntos_candidatos(a.evento, a.n_puntos) + [{"nombre": f"foco {p.get('nombre')}", "lon": p["lon"], "lat": p["lat"]} for p in ev["ignicion"]["puntos"]]
        for h in a.horas.split(","):
            trabajos += [(p["nombre"], p["lon"], p["lat"], str(pd.Timestamp(h))) for p in pts]
    else:
        cota = pd.Timestamp(ev["inicio"].get("cota_superior_utc") or ev["inicio"]["hora_utc_hipotesis"][0])
        ult = (cota - pd.Timedelta(minutes=30)).floor("h")
        horas = sorted(set([ult - pd.Timedelta(hours=k) for k in range(0, 14, 2)] + [pd.Timestamp(x) for x in ev["inicio"]["hora_utc_hipotesis"]]))
        for k, s in enumerate(a.puntos.split(";")):
            lon, lat = (float(x) for x in s.split(","))
            trabajos += [(f"punto fijo {k}", lon, lat, str(t)) for t in horas]
    print(len(trabajos), "corridas; fin de cada una:", fin, flush=True)
    if a.listar:
        for t in trabajos:
            print(" ", t)
        return 0
    filas = []; t_all = time.time()
    with ProcessPoolExecutor(a.procs) as ex:
        fut = {ex.submit(correr_uno, a.evento, et, lon, lat, h, str(fin)): (et, h) for et, lon, lat, h in trabajos}
        for f in as_completed(fut):
            try:
                r = f.result(); filas.append(r); print(f"{r['etiqueta']:28s} {r['t0_utc'][:16]} {r['segundos']} s", flush=True)
            except Exception as exc:  # noqa: BLE001
                print("ERROR", fut[f], repr(exc), flush=True)
    out = Path(os.environ["INCENDIOS_SL_RESULTADOS"]) / f"corridas_{a.modo}_{a.evento}.csv"
    prev = pd.read_csv(out) if out.exists() else pd.DataFrame()
    pd.concat([prev, pd.DataFrame(filas)], ignore_index=True).drop_duplicates("run_id", keep="last").to_csv(out, index=False)
    print("corridas:", out, f"{time.time() - t_all:.0f} s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
