"""Informe de evaluación (evaluacion.md) con tabla, figura comparativa y discusión por plantilla."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .metricas import rasterizar, comparar_areas, tiempos_llegada_vs_focos
from ..outputs.figuras import Dibujante, recuadro_automatico, COL_OBS


def evaluar_corrida(res: dict, caso: dict, carpeta: Path, etiqueta: str) -> dict:
    """Métricas de una corrida contra el perímetro observado principal y los alternativos."""
    au = res["automata"]; g = au.capas.grilla
    sim = au.afectada
    out = {"variante": etiqueta, "carpeta": str(carpeta), "t_inicio": res["t0"].isoformat(), "ha_sim": round(au.area_quemada_ha(), 2),
           "toco_borde": bool(au.toco_borde), "perimetros": {}, "motivo_fin": getattr(au, "motivo_fin", None),
           "contencion": (res.get("metadata") or {}).get("contencion")}
    import geopandas as gpd
    obs_principal = res["perimetro_obs"]
    if obs_principal is not None and len(obs_principal):
        obs_m = rasterizar(obs_principal, g)
        out["perimetros"]["observado"] = comparar_areas(sim, obs_m, g)
        # comparación a igual superficie: instante en que el área simulada alcanza la observada (forma y rumbo
        # independientes de la supresión, que esta etapa no modela)
        tl = au.t_llegada[np.isfinite(au.t_llegada)]
        n_obs = int(obs_m.sum())
        if n_obs and len(tl) >= n_obs:
            t_iso = float(np.sort(tl)[n_obs - 1])
            m_iso = comparar_areas(au.t_llegada <= t_iso, obs_m, g)
            m_iso["t_min"] = round(t_iso, 0); m_iso["horas"] = round(t_iso / 60.0, 1)
            out["iso_area"] = m_iso
        else:
            out["iso_area"] = None
    for nombre, ruta in (caso.get("evaluacion", {}).get("perimetros_alternativos") or {}).items():
        p = Path(caso["_dir"]) / ruta
        if p.exists():
            gdf = gpd.read_file(p).to_crs(g.crs)
            from shapely.geometry import box
            gdf = gdf[gdf.intersects(box(*g.bounds))]
            out["perimetros"][nombre] = comparar_areas(sim, rasterizar(gdf, g), g)
    focos = res["focos"]
    df_f = tiempos_llegada_vs_focos(au, focos, res["t0"]) if focos is not None else pd.DataFrame()
    out["focos"] = df_f.to_dict("records") if len(df_f) else []
    if len(df_f) and df_f["dif_min"].notna().any():
        d = df_f["dif_min"].dropna()
        out["focos_resumen"] = {"n": int(len(d)), "sesgo_min": round(float(d.mean()), 0), "rmse_min": round(float(np.sqrt((d ** 2).mean())), 0),
                                "n_no_alcanzados": int(df_f["sim_min"].isna().sum())}
    else:
        out["focos_resumen"] = {"n": 0, "n_no_alcanzados": int(df_f["sim_min"].isna().sum()) if len(df_f) else 0}
    # figura comparativa
    recuadro = recuadro_automatico(au, obs_principal)
    dib = Dibujante(au, res["metadata"] and {"parametros": res["metadata"]["parametros"]} or {}, recuadro, obs_principal, focos, etiqueta)
    fig, ax = plt.subplots(figsize=(9, 7.5))
    dib._base(ax)
    rgba = np.zeros(sim.shape + (4,), "float32"); rgba[sim] = matplotlib.colors.to_rgba("#e41a1c", 0.55)
    ax.imshow(rgba, extent=dib.extent, interpolation="nearest", zorder=4)
    dib._isocronas(ax, float(np.nanmax(au.t_llegada)) if np.isfinite(au.t_llegada).any() else 0, color="k", lw=0.6)
    dib._observado(ax)
    for ig in au.igniciones:
        x, y = g.centros(ig.fila, ig.col); ax.plot(x, y, marker="*", color="yellow", markeredgecolor="k", ms=12, zorder=10)
    m = out["perimetros"].get("observado", {})
    dib._decoracion(ax, None, f"{etiqueta} · simulado (rojo) vs observado (cian) · Sørensen {m.get('sorensen')} · {out['ha_sim']} / {m.get('ha_obs')} ha")
    fig.tight_layout(); ruta_fig = carpeta / "comparacion_observado.png"; fig.savefig(ruta_fig, dpi=130); plt.close(fig)
    out["figura"] = str(ruta_fig)
    return out


def escribir_informe(caso: dict, resultados: list[dict], ruta: Path, extra_md: str = "", raiz: Path | None = None):
    nombre = caso.get("nombre", "caso")
    L = [f"# Evaluación · {nombre}", ""]
    L.append(caso.get("descripcion", "").strip())
    L.append("")
    L.append("## Métricas contra el perímetro observado")
    L.append("")
    L.append("| Variante | t0 (local) | ha sim | ha obs | Error ha | Error % | Sørensen | Jaccard | Comisión % | Omisión % | Dist. centroides (m) | Rumbo obs→sim | Borde |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for r in resultados:
        m = r["perimetros"].get("observado", {})
        t0 = pd.Timestamp(r["t_inicio"]).tz_convert("America/Argentina/San_Luis").strftime("%d-%m %H:%M")
        L.append(f"| {r['variante']} | {t0} | {r['ha_sim']} | {m.get('ha_obs','–')} | {m.get('error_ha','–')} | {m.get('error_pct','–')} | {m.get('sorensen','–')} | "
                 f"{m.get('jaccard','–')} | {m.get('comision_pct','–')} | {m.get('omision_pct','–')} | {m.get('centroide_dist_m','–')} | {m.get('centroide_rumbo_deg','–')}° | {'sí' if r['toco_borde'] else 'no'} |")
    if any(r.get("iso_area") for r in resultados):
        L.append("")
        L.append("## Comparación a igual superficie")
        L.append("")
        L.append("Instante en que el área simulada alcanza la observada. Mide forma y rumbo de la propagación con independencia de la "
                 "supresión, que esta etapa no modela (propagación libre).")
        L.append("")
        L.append("| Variante | t (h desde t0) | Sørensen | Jaccard | Comisión % | Omisión % | Dist. centroides (m) | Rumbo obs→sim |")
        L.append("|---|---:|---:|---:|---:|---:|---:|---:|")
        for r in resultados:
            m = r.get("iso_area")
            if m:
                L.append(f"| {r['variante']} | {m['horas']} | {m['sorensen']} | {m['jaccard']} | {m['comision_pct']} | {m['omision_pct']} | {m['centroide_dist_m']} | {m['centroide_rumbo_deg']}° |")
    if any(r.get("contencion") for r in resultados):
        L.append("")
        L.append("## Contención por combate")
        L.append("")
        L.append("| Variante | Despacho | Inicio (h) | Línea (km) | Celdas contenidas | Escapes | Fin de la corrida |")
        L.append("|---|---|---:|---:|---:|---:|---|")
        for r in resultados:
            c = r.get("contencion")
            if c:
                L.append(f"| {r['variante']} | {c['despacho']} | {c['inicio_min'] / 60:.2f} | {c['linea_km']} | {c['celdas_contenidas_final']} | "
                         f"{c['escapes']} | {r.get('motivo_fin') or '–'} |")
    alts = sorted({k for r in resultados for k in r["perimetros"] if k != "observado"})
    if alts:
        L.append("")
        L.append("## Perímetros alternativos")
        L.append("")
        L.append("| Variante | Perímetro | ha obs | Sørensen | Jaccard | Error % |")
        L.append("|---|---|---:|---:|---:|---:|")
        for r in resultados:
            for k in alts:
                m = r["perimetros"].get(k)
                if m:
                    L.append(f"| {r['variante']} | {k} | {m['ha_obs']} | {m['sorensen']} | {m['jaccard']} | {m['error_pct']} |")
    L.append("")
    L.append("## Tiempos de llegada contra focos VIIRS")
    L.append("")
    con_focos = [r for r in resultados if r.get("focos")]
    if not con_focos:
        L.append("No hay focos VIIRS dentro de la grilla de simulación para este caso: la comparación de tiempos de llegada no es aplicable.")
    for r in con_focos:
        fr = r["focos_resumen"]
        L.append(f"**{r['variante']}**: {fr.get('n', 0)} focos comparables, sesgo {fr.get('sesgo_min', '–')} min, RMSE {fr.get('rmse_min', '–')} min, "
                 f"{fr.get('n_no_alcanzados', 0)} focos no alcanzados por la simulación.")
        L.append("")
        if len(r["focos"]) <= 40:
            L.append("| id | detección | obs (min) | sim (min) | dif (min) | FRP |")
            L.append("|---|---|---:|---:|---:|---:|")
            for f in r["focos"]:
                L.append(f"| {f['id']} | {f['hora_deteccion']} | {f['obs_min']} | {f['sim_min']} | {f['dif_min']} | {f['frp']} |")
        else:
            df = pd.DataFrame(r["focos"])
            df["pase"] = pd.to_datetime(df["hora_deteccion"], utc=True).dt.tz_convert("America/Argentina/San_Luis").dt.strftime("%d-%m %H:%M")
            L.append("Resumen por pase satelital (hora local). dif = simulado − observado en minutos; negativo = la simulación llegó antes.")
            L.append("")
            L.append("| Pase | Focos | Alcanzados | No alcanzados | dif mediana (min) | dif p10 / p90 (min) | FRP máx |")
            L.append("|---|---:|---:|---:|---:|---|---:|")
            for pase, g in df.groupby("pase", sort=True):
                d = g["dif_min"].dropna()
                med = f"{d.median():.0f}" if len(d) else "–"
                p = f"{d.quantile(.1):.0f} / {d.quantile(.9):.0f}" if len(d) else "–"
                frp = g["frp"].max() if "frp" in g else None
                L.append(f"| {pase} | {len(g)} | {int(g['sim_min'].notna().sum())} | {int(g['sim_min'].isna().sum())} | {med} | {p} | {frp} |")
        L.append("")
    L.append("")
    L.append("## Figuras")
    L.append("")
    for r in resultados:
        rel = Path(r["figura"])
        for base in (ruta.parent, raiz):
            try:
                rel = rel.relative_to(base); break
            except (ValueError, TypeError):
                continue
        L.append(f"- {r['variante']}: `{str(rel).replace(chr(92), '/')}` (corrida `{Path(r['carpeta']).name}`)")
    L.append("")
    if extra_md:
        L.append(extra_md)
    Path(ruta).write_text("\n".join(L) + "\n", encoding="utf-8")
    return ruta
