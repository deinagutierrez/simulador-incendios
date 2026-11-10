"""Figuras de validación: mapa de comparación, mapa de tiempos de llegada con focos y animación diaria (GIF)."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ..grilla import Grilla


def _sombras(dem: np.ndarray, res: float) -> np.ndarray:
    dy, dx = np.gradient(dem.astype(float), res)
    sl = np.arctan(np.hypot(dx, dy)); asp = np.arctan2(-dx, dy)
    return np.sin(np.radians(45)) * np.cos(sl) + np.cos(np.radians(45)) * np.sin(sl) * np.cos(np.radians(315) - asp)


def mapa_comparacion(t_arr, ref, dem, g: Grilla, t_eval_s: float, titulo: str, out: Path, hotspots: pd.DataFrame | None = None,
                     igniciones=None, metr: dict | None = None, t_cont: np.ndarray | None = None):
    ext = [g.xmin / 1e3, g.xmax / 1e3, g.ymin / 1e3, g.ymax / 1e3]
    sim = np.isfinite(t_arr) & (t_arr >= 0) & (t_arr <= t_eval_s)
    hs = _sombras(dem, g.res)
    fig, ax = plt.subplots(1, 2, figsize=(17, 8))
    ax[0].imshow(hs, extent=ext, cmap="gray", alpha=0.6)
    h = np.where(sim, t_arr / 3600, np.nan)
    im = ax[0].imshow(h, extent=ext, cmap="inferno_r", vmin=0, vmax=max(t_eval_s / 3600, 1)); plt.colorbar(im, ax=ax[0], label="hora de llegada (h desde la ignición)")
    ax[0].contour((ref == 1).astype(int), levels=[0.5], colors="cyan", linewidths=1.0, extent=ext, origin="upper")
    if t_cont is not None:
        cont = np.isfinite(t_cont) & (t_cont >= 0) & (t_cont <= t_eval_s)
        if cont.any():
            ax[0].imshow(np.where(cont, 1, np.nan), extent=ext, cmap=mcolors.ListedColormap(["#1a3d8f"]), vmin=0, vmax=1, alpha=0.9)
            titulo += "\nazul oscuro: perímetro contenido"
    if hotspots is not None and len(hotspots):
        from pyproj import Transformer
        t = Transformer.from_crs("EPSG:4326", g.crs, always_xy=True)
        x, y = t.transform(hotspots.lon.to_numpy(), hotspots.lat.to_numpy())
        dias = pd.to_datetime(hotspots.date); d0 = dias.min()
        sc = ax[0].scatter(np.array(x) / 1e3, np.array(y) / 1e3, c=(dias - d0).dt.days, cmap="cool", s=2, alpha=0.6)
        plt.colorbar(sc, ax=ax[0], label=f"focos de calor: días desde {d0.date()}", fraction=0.03)
    if igniciones:
        for (r, c, _) in igniciones:
            x, y = g.rc_a_xy(r, c); ax[0].plot(x / 1e3, y / 1e3, "k*", ms=11)
    ax[0].set_title(titulo + "\ncontorno cian: cicatriz de referencia")
    cat = np.zeros(sim.shape, np.uint8); cat[sim & (ref == 1)] = 1; cat[sim & (ref != 1)] = 2; cat[~sim & (ref == 1)] = 3
    ax[1].imshow(hs, extent=ext, cmap="gray", alpha=0.6)
    ax[1].imshow(np.where(cat > 0, cat, np.nan), extent=ext, cmap=mcolors.ListedColormap(["#2ca02c", "#d62728", "#1f77b4"]), vmin=1, vmax=3, alpha=0.8)
    sub = "verde: acierto | rojo: comisión | azul: omisión"
    if metr:
        sub += f"\nIoU {metr['iou']:.3f} | Dice {metr['dice']:.3f} | sim {metr['ha_sim']:,.0f} ha | ref {metr['ha_ref']:,.0f} ha | omisión {metr['omision']:.2f} | comisión {metr['comision']:.2f}"
    ax[1].set_title(sub)
    for a in ax:
        a.set_xlabel("E (km, EPSG:5345)"); a.set_ylabel("N (km)")
        a.set_xlim(ext[0], ext[1]); a.set_ylim(ext[2], ext[3])     # los focos fuera de la extensión no la agrandan
    plt.tight_layout(); fig.savefig(out, dpi=100); plt.close(fig)
    return out


def animacion_diaria(t_arr, ref, dem, g: Grilla, t_inicio: pd.Timestamp, t_fin_s: float, out: Path, paso_h: float = 12.0,
                     hotspots: pd.DataFrame | None = None, titulo: str = ""):
    """GIF con un cuadro cada `paso_h` horas: superficie simulada acumulada (naranja), frente reciente (amarillo), referencia (cian)."""
    from PIL import Image
    ext = [g.xmin / 1e3, g.xmax / 1e3, g.ymin / 1e3, g.ymax / 1e3]
    hs = _sombras(dem, g.res)
    frames = []
    ts = np.arange(paso_h * 3600, t_fin_s + 1, paso_h * 3600)
    for te in ts:
        fig, ax = plt.subplots(figsize=(8.5, 8))
        ax.imshow(hs, extent=ext, cmap="gray", alpha=0.6)
        quem = np.isfinite(t_arr) & (t_arr >= 0) & (t_arr <= te)
        rec = quem & (t_arr > te - paso_h * 3600)
        ax.imshow(np.where(quem, 1, np.nan), extent=ext, cmap=mcolors.ListedColormap(["#d9541e"]), alpha=0.75, vmin=0, vmax=1)
        ax.imshow(np.where(rec, 1, np.nan), extent=ext, cmap=mcolors.ListedColormap(["#ffd500"]), alpha=0.9, vmin=0, vmax=1)
        ax.contour((ref == 1).astype(int), levels=[0.5], colors="cyan", linewidths=1.0, extent=ext, origin="upper")
        cuando = t_inicio + pd.Timedelta(seconds=float(te))
        if hotspots is not None and len(hotspots):
            from pyproj import Transformer
            t = Transformer.from_crs("EPSG:4326", g.crs, always_xy=True)
            sel = hotspots[pd.to_datetime(hotspots.date).dt.tz_localize("UTC") <= cuando]
            if len(sel):
                x, y = t.transform(sel.lon.to_numpy(), sel.lat.to_numpy()); ax.scatter(np.array(x) / 1e3, np.array(y) / 1e3, s=1.5, c="magenta", alpha=0.5)
        ha = quem.sum() * g.res ** 2 / 1e4
        ax.set_title(f"{titulo}\n{cuando.tz_convert('America/Argentina/San_Luis').strftime('%Y-%m-%d %H:%M')} hora local | {ha:,.0f} ha simuladas | naranja: quemado, amarillo: últimas {paso_h:.0f} h, cian: referencia, magenta: focos")
        ax.set_xlabel("E (km)"); ax.set_ylabel("N (km)"); ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3])
        fig.tight_layout(); fig.canvas.draw()
        frames.append(Image.fromarray(np.asarray(fig.canvas.buffer_rgba())[..., :3].copy())); plt.close(fig)
    if frames:
        frames[0].save(out, save_all=True, append_images=frames[1:], duration=600, loop=0, optimize=True)
    return out
