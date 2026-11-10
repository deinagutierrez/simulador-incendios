"""Prueba del modelo de humedad del combustible muerto contra los focos de calor (docs/11 §4).

Cada foco VIIRS (con hora) o MODIS (sin hora: se asume la pasada de Aqua, 17:30 UTC, HIPÓTESIS) dice que a esa hora y en
esa celda el fuego avanzaba. Para que el modelo pueda reproducirlo, la humedad muerta de 1 h simulada en esa hora debe ser
menor que la humedad de extinción (Mx) de la clase de combustible de la celda. Se informa, por evento y por variante de
humedad (FFMC v1 / retardo de Simard v2), la fracción de focos "no ardibles" según el modelo, y la sensibilidad a Mx.

Uso: python scripts/evaluar_humedad.py [--eventos A,B] [--mx 12,15,20,25]
Salida: resultados/v3.1/evaluacion_humedad/focos_vs_humedad.csv y resumen por pantalla.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from incendios_sl import config as cfgmod  # noqa: E402
from incendios_sl.data.preparar_dominio import grilla_dominio  # noqa: E402
from incendios_sl.fuels.tabla import cargar_tabla  # noqa: E402
from incendios_sl.grilla import leer_raster  # noqa: E402

HORA_MODIS_S = 17.5 * 3600


def focos_evento(ev: str) -> pd.DataFrame | None:
    D = cfgmod.dir_catalogo() / "hotspots"
    v = D / f"viirs_{ev}.csv"; m = D / f"modis_{ev}.csv"
    if v.exists() and v.stat().st_size > 10 and len(df := pd.read_csv(v)):
        df["t_utc"] = pd.to_datetime(df["date"], utc=True) + pd.to_timedelta(df["acq_time_s"].fillna(HORA_MODIS_S), unit="s"); df["fuente"] = "VIIRS"
        return df
    if m.exists() and m.stat().st_size > 10 and len(df := pd.read_csv(m)):
        df["t_utc"] = pd.to_datetime(df["date"], utc=True) + pd.to_timedelta(HORA_MODIS_S, unit="s"); df["fuente"] = "MODIS"
        return df
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--eventos", default=None); ap.add_argument("--mx", default="12,15,20,25")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    D = cfgmod.dir_entradas()
    eventos = a.eventos.split(",") if a.eventos else sorted(p.stem for p in (cfgmod.dir_escenarios() / "eventos").glob("*.yaml"))
    tabla = cargar_tabla().set_index("clase")
    mxs = [float(x) for x in a.mx.split(",")]
    filas = []
    for ev in eventos:
        hs = focos_evento(ev)
        p_h = D / "eventos" / ev / f"humedad_muerto_{ev}.csv"; p_c = D / "combustibles" / ev / f"combustible_clase_{ev}.tif"
        if hs is None or not p_h.exists() or not p_c.exists():
            print(f"{ev}: sin focos o sin datos preparados; se omite"); continue
        hum = pd.read_csv(p_h, parse_dates=["time_utc"]); hum["time_utc"] = pd.to_datetime(hum["time_utc"], utc=True)
        if "m_1h_pct_rt" not in hum:
            print(f"{ev}: serie sin variante de retardo (ejecute actualizar_humedad.py); se omite"); continue
        dom = cfgmod.cargar_dominio(cfgmod.cargar_evento(ev)["dominio"]); g = grilla_dominio(dom)
        clase, _, _ = leer_raster(p_c)
        r, c = g.lonlat_a_rc(hs.lon.to_numpy(), hs.lat.to_numpy())
        ok = g.dentro(r, c); hs = hs[ok].copy(); r = r[ok]; c = c[ok]
        hs["clase"] = clase[r, c]
        hs = hs[hs.clase > 0]
        hs["hora"] = hs.t_utc.dt.floor("h")
        hs = hs.merge(hum[["time_utc", "m_1h_pct", "m_1h_pct_rt", "emc_pct"]], left_on="hora", right_on="time_utc", how="left")
        hs = hs[hs.m_1h_pct.notna()]
        if not len(hs):
            print(f"{ev}: los focos quedan fuera de la ventana meteorológica; se omite"); continue
        hs["mx_analogo"] = hs.clase.map(tabla["mx_muerto_pct"])
        fila = {"evento": ev, "fuente": hs.fuente.iloc[0], "n_focos": int(len(hs)),
                "m1h_ffmc_mediana": float(hs.m_1h_pct.median()), "m1h_retardo_mediana": float(hs.m_1h_pct_rt.median()), "emc_mediana": float(hs.emc_pct.median()),
                "no_ardible_ffmc_mx_analogo": float((hs.m_1h_pct >= hs.mx_analogo).mean()), "no_ardible_retardo_mx_analogo": float((hs.m_1h_pct_rt >= hs.mx_analogo).mean())}
        for mx in mxs:
            fila[f"no_ardible_ffmc_mx{mx:.0f}"] = float((hs.m_1h_pct >= mx).mean()); fila[f"no_ardible_retardo_mx{mx:.0f}"] = float((hs.m_1h_pct_rt >= mx).mean())
        filas.append(fila)
    df = pd.DataFrame(filas)
    out = cfgmod.dir_resultados() / "evaluacion_humedad"; out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "focos_vs_humedad.csv", index=False)
    pd.set_option("display.width", 250)
    print(df.round(2).to_string(index=False))
    if len(df):
        w = df.n_focos / df.n_focos.sum()
        print("\nFracción de focos no ardibles ponderada por focos (todos los eventos):")
        for col in [c for c in df.columns if c.startswith("no_ardible")]:
            print(f"  {col}: {(df[col] * w).sum():.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
