"""Mapas de comparación simulación / cicatriz para corridas ya ejecutadas (sin volver a simular).

Lee de resultados/v3.1/<run_id>/ los rasters guardados (t_llegada_s.tif y, si existe, t_contencion_s.tif) y metricas.json,
y dibuja un mapa por instante de evaluación más la animación, recortados a la extensión de la cicatriz y de lo simulado
(más un margen), porque a la escala del dominio (50 km) un incendio de 100 ha no se distingue.

Uso: python scripts/figuras_corrida.py SL-2022-RENCA_v2_local_snmf [otro_run ...] [--margen-km 1.5] [--sin-animacion]
Salida: resultados/v3.1/<run_id>/mapa_<AAAAMMDDTHH>.png y animacion.gif
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from incendios_sl import config as cfgmod  # noqa: E402
from incendios_sl.grilla import Grilla, leer_raster  # noqa: E402
from incendios_sl.validation import figuras  # noqa: E402


def focos(evento: str) -> pd.DataFrame | None:
    D = cfgmod.dir_catalogo() / "hotspots"
    for f in (D / f"viirs_{evento}.csv", D / f"modis_{evento}.csv"):
        if f.exists() and f.stat().st_size > 10 and len(df := pd.read_csv(f)):
            return df
    return None


def recorte(mascaras: list[np.ndarray], g: Grilla, margen_m: float) -> tuple[slice, slice, Grilla]:
    """Ventana que envuelve todas las máscaras, con margen, como sub-grilla alineada."""
    u = np.logical_or.reduce(mascaras)
    filas = np.flatnonzero(u.any(axis=1)); cols = np.flatnonzero(u.any(axis=0))
    m = int(np.ceil(margen_m / g.res))
    r0 = max(0, filas[0] - m); r1 = min(g.nfil, filas[-1] + m + 1); c0 = max(0, cols[0] - m); c1 = min(g.ncol, cols[-1] + m + 1)
    sub = Grilla(g.crs, g.res, g.xmin + c0 * g.res, g.ymax - r1 * g.res, g.xmin + c1 * g.res, g.ymax - r0 * g.res)
    return slice(r0, r1), slice(c0, c1), sub


def figuras_de(run_id: str, margen_km: float, animacion: bool) -> list[Path]:
    d = cfgmod.dir_resultados() / run_id
    met = json.loads((d / "metricas.json").read_text(encoding="utf-8"))
    reg = json.loads((d / "registro.json").read_text(encoding="utf-8"))
    ev = met["evento"]; ent = reg.get("entradas", {})
    t_arr, g, nd = leer_raster(d / "t_llegada_s.tif")
    t_arr = np.where(t_arr == nd, np.inf, t_arr).astype(np.float32)
    t_cont = None
    if (d / "t_contencion_s.tif").exists():
        tc, _, ndc = leer_raster(d / "t_contencion_s.tif"); t_cont = np.where(tc == ndc, np.inf, tc)
    ref, _, _ = leer_raster(cfgmod.dir_entradas() / "eventos" / ev / f"cicatriz_referencia_{ev}.tif")
    dem, _, _ = leer_raster(cfgmod.dir_entradas() / "dem" / f"dem_copernicus_glo30_{ent.get('dominio', 'las_lagunas_potrerillos')}.tif")
    fr, fc, sub = recorte([np.isfinite(t_arr), ref == 1], g, margen_km * 1000.0)
    # celdas de ignición: llegada en t = 0 (el cargador puede haber desplazado el punto informado a la celda combustible más cercana)
    ign = [(int(r) - fr.start, int(c) - fc.start, 0.0) for r, c in np.argwhere(t_arr == 0.0)]
    hs = focos(ev)
    t0 = pd.Timestamp(ent.get("t_inicio_utc") or reg["t_simulado_utc"])
    v2 = met.get("v2") or {}
    etiqueta = f"{met.get('modelo', 'modelo_v1')}" + (" + barreras" if v2.get("barreras_activo") else "") + \
        (f" + contención ({'despacho SNMF' if v2.get('despacho_modo') == 'snmf' else 'tasa fija'})" if v2.get("contencion_activo") else "") + \
        f" | ignición {met.get('ignicion')}"
    out = []
    for m in met["espacial"]:
        te = m["horas_desde_ignicion"] * 3600
        local = pd.Timestamp(m["t_eval_utc"]).tz_convert("America/Argentina/San_Luis").strftime("%d/%m/%Y %H:%M")
        p = d / f"mapa_{pd.Timestamp(m['t_eval_utc']).strftime('%Y%m%dT%H')}.png"
        figuras.mapa_comparacion(t_arr[fr, fc], ref[fr, fc], dem[fr, fc], sub, te, f"{ev} | {local} hora local\n{etiqueta}",
                                 p, hs, ign, m, t_cont=t_cont[fr, fc] if t_cont is not None else None)
        out.append(p)
    if animacion:
        t_fin = met["espacial"][-1]["horas_desde_ignicion"] * 3600
        out.append(figuras.animacion_diaria(t_arr[fr, fc], ref[fr, fc], dem[fr, fc], sub, t0, t_fin, d / "animacion.gif", paso_h=6.0,
                                            hotspots=hs, titulo=f"{ev} | {run_id}"))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("runs", nargs="+"); ap.add_argument("--margen-km", type=float, default=1.5)
    ap.add_argument("--sin-animacion", action="store_true")
    a = ap.parse_args(argv)
    for r in a.runs:
        for p in figuras_de(r, a.margen_km, not a.sin_animacion):
            print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
