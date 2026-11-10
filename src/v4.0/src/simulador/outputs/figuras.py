"""Figuras: mapa por hora, GIF de la corrida y figura final de isócronas."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LightSource, ListedColormap, BoundaryNorm
from matplotlib.patches import Patch, Rectangle
from matplotlib.lines import Line2D

from .indicadores import mascaras_en

COLORES_SB = {
    91: "#d4271e", 92: "#ffffff", 93: "#f2d0f2", 98: "#2532e4", 99: "#b3b3b3",
    101: "#fff7bc", 102: "#fee391", 103: "#9ecae1", 104: "#fec44f", 105: "#6baed6", 106: "#4292c6", 107: "#ec7014", 108: "#2171b5", 109: "#08306b",
    121: "#d9f0a3", 122: "#addd8e", 123: "#78c679", 124: "#41ab5d",
    141: "#e0cda9", 142: "#bf9b6a", 143: "#a3875a", 144: "#c9a97f", 145: "#8c6239", 146: "#9c7a4a", 147: "#5a3a1a", 148: "#7a5a2a", 149: "#4a2a0a",
    161: "#74c476", 162: "#41ab5d", 163: "#238b45", 164: "#006d2c", 165: "#00441b",
    181: "#c7b299", 182: "#b09c7d", 183: "#9b8a6a", 184: "#8b7a5a", 185: "#7b6a4a", 186: "#a68f6a", 187: "#6b5a3a", 188: "#7a6c00", 189: "#5a4c00",
    201: "#e6e6e6", 202: "#cccccc", 203: "#b3b3b3", 204: "#999999",
}
COL_COMBUSTION = "#e41a1c"; COL_IGNICION = "#ffff33"; COL_QUEMADO = "#3b3b3b"; COL_OBS = "#00e5ff"; COL_LINEA = "#1f4fd1"


class Dibujante:
    def __init__(self, au, cfg: dict, recuadro: tuple | None, perimetro_obs=None, focos=None, nombre: str = ""):
        self.au = au; self.cfg = cfg; self.nombre = nombre
        g = au.capas.grilla
        self.g = g
        self.recuadro = recuadro or g.bounds
        self.perimetro_obs = perimetro_obs
        self.focos = focos
        cap = au.capas
        mdt = cap.mdt.astype("float32")
        mdt[mdt == cap.nodata_mdt] = np.nan
        ls = LightSource(azdeg=315, altdeg=45)
        self.hill = ls.hillshade(np.nan_to_num(mdt, nan=np.nanmean(mdt)), vert_exag=1.5, dx=g.res, dy=g.res)
        comb = cap.combustible
        cods = sorted(set(np.unique(comb).tolist()) - {cap.nodata_combustible})
        cmap = ListedColormap([COLORES_SB.get(c, "#dddddd") for c in cods]) if cods else ListedColormap(["#dddddd"])
        norm = BoundaryNorm(cods + [cods[-1] + 1], cmap.N) if cods else None
        self.comb_rgba = cmap(norm(np.ma.masked_equal(comb, cap.nodata_combustible))) if norm is not None else None
        self.extent = (g.xmin, g.xmax, g.ymin, g.ymax)
        self.cods = cods

    def _base(self, ax):
        ax.imshow(self.hill, cmap="gray", extent=self.extent, interpolation="nearest", vmin=0, vmax=1)
        if self.comb_rgba is not None:
            ax.imshow(self.comb_rgba, extent=self.extent, interpolation="nearest", alpha=0.45)
        cap = self.au.capas
        if len(cap.caminos_gdf):
            cap.caminos_gdf.plot(ax=ax, color="#555555", linewidth=0.6, alpha=0.9, zorder=3)
        if len(cap.red_gdf):
            cap.red_gdf.plot(ax=ax, color="#8e24aa", linewidth=0.8, linestyle="--", alpha=0.9, zorder=3)
        x0, x1, y0, y1 = self.recuadro[0], self.recuadro[2], self.recuadro[1], self.recuadro[3]
        ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
        ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])

    def _estados(self, ax, t_min):
        au = self.au
        af, comb, que, ign = mascaras_en(au, t_min)
        rgba = np.zeros(af.shape + (4,), "float32")
        rgba[que] = matplotlib.colors.to_rgba(COL_QUEMADO, 0.85)
        rgba[comb] = matplotlib.colors.to_rgba(COL_COMBUSTION, 0.95)
        rgba[ign] = matplotlib.colors.to_rgba(COL_IGNICION, 0.95)
        ax.imshow(rgba, extent=self.extent, interpolation="nearest", zorder=4)
        self._linea(ax, t_min)
        return af, comb

    def _linea(self, ax, t_min) -> bool:
        """Celdas contenidas por la línea de combate hasta t_min (si la contención está activa)."""
        cont = getattr(self.au, "contencion", None)
        if cont is None or cont.t_contencion is None:
            return False
        m = cont.t_contencion <= t_min + 1e-6
        if not m.any():
            return False
        rgba = np.zeros(m.shape + (4,), "float32"); rgba[m] = matplotlib.colors.to_rgba(COL_LINEA, 1.0)
        ax.imshow(rgba, extent=self.extent, interpolation="nearest", zorder=5)
        return True

    def _isocronas(self, ax, t_min, cada_min=60, color="white", lw=0.7, etiquetas=False):
        tl = self.au.t_llegada
        if not np.isfinite(tl).any():
            return
        niveles = np.arange(cada_min, t_min + 1e-6, cada_min)
        if len(niveles) == 0:
            return
        g = self.g
        xs = g.xmin + (np.arange(g.ancho) + 0.5) * g.res; ys = g.ymax - (np.arange(g.alto) + 0.5) * g.res
        z = np.where(np.isnan(tl), 1e9, tl)
        cs = ax.contour(xs, ys, z, levels=niveles, colors=color, linewidths=lw, zorder=5, alpha=0.9)
        if etiquetas:
            ax.clabel(cs, fmt=lambda v: f"{v/60:.0f} h", fontsize=6, colors=color)

    def _infra_dinamica(self, ax, af, comb, buffer_m):
        from .indicadores import poligonos
        cap = self.au.capas; viv = cap.viviendas_gdf
        if not len(viv):
            return
        pol_af = poligonos(af, self.g); pol_c = poligonos(comb, self.g)
        afect = viv.intersects(pol_af) if pol_af is not None else pd.Series(False, index=viv.index)
        amen = (viv.intersects(pol_c.buffer(buffer_m)) & ~afect) if pol_c is not None else pd.Series(False, index=viv.index)
        pts = viv.geometry.representative_point()
        ok = ~(afect | amen)
        if ok.any():
            ax.scatter(pts[ok].x, pts[ok].y, s=14, marker="s", c="#2ca02c", edgecolors="k", linewidths=0.3, zorder=6)
        if amen.any():
            ax.scatter(pts[amen].x, pts[amen].y, s=24, marker="s", c="#ff7f00", edgecolors="k", linewidths=0.3, zorder=7)
        if afect.any():
            ax.scatter(pts[afect].x, pts[afect].y, s=28, marker="s", c="#000000", edgecolors="w", linewidths=0.4, zorder=8)

    def _observado(self, ax):
        if self.perimetro_obs is not None and len(self.perimetro_obs):
            self.perimetro_obs.boundary.plot(ax=ax, color=COL_OBS, linewidth=1.6, zorder=9)
        if self.focos is not None and len(self.focos):
            ax.scatter(self.focos.geometry.x, self.focos.geometry.y, s=30, marker="^", c="#ff00ff", edgecolors="k", linewidths=0.3, zorder=9)

    def _decoracion(self, ax, d: dict | None, titulo: str):
        x0, x1, y0, y1 = self.recuadro[0], self.recuadro[2], self.recuadro[1], self.recuadro[3]
        w = x1 - x0; h = y1 - y0
        # escala
        largo = 10 ** np.floor(np.log10(w / 4)); largo = largo * (2 if w / 4 >= 2 * largo else 1)
        if w / 4 >= 5 * largo / 2:
            largo = largo * 2.5
        xs = x0 + 0.04 * w; ys = y0 + 0.04 * h
        ax.plot([xs, xs + largo], [ys, ys], color="k", lw=3, zorder=20, solid_capstyle="butt")
        ax.plot([xs, xs + largo], [ys, ys], color="w", lw=1, zorder=21, solid_capstyle="butt")
        ax.text(xs + largo / 2, ys + 0.012 * h, f"{largo/1000:g} km" if largo >= 1000 else f"{largo:g} m", ha="center", va="bottom", fontsize=8,
                color="k", zorder=21, bbox=dict(fc="w", ec="none", alpha=0.7, pad=1))
        # norte
        xn = x1 - 0.05 * w; yn = y1 - 0.12 * h
        ax.annotate("N", xy=(xn, yn + 0.06 * h), xytext=(xn, yn), ha="center", va="center", fontsize=10, fontweight="bold",
                    arrowprops=dict(arrowstyle="-|>", color="k", lw=1.5), zorder=21, bbox=dict(fc="w", ec="none", alpha=0.7, pad=1))
        # viento
        if d is not None:
            m = d["meteo"]; ang = np.deg2rad((m["viento_dir_deg"] + 180) % 360)   # hacia donde va
            xv = x0 + 0.10 * w; yv = y1 - 0.10 * h; L = 0.06 * min(w, h) * min(max(m["viento_kmh"] / 20.0, 0.3), 1.5)
            ax.annotate("", xy=(xv + L * np.sin(ang), yv + L * np.cos(ang)), xytext=(xv, yv),
                        arrowprops=dict(arrowstyle="-|>", color="#1f3b73", lw=2.5), zorder=21)
            ax.text(xv, yv - 0.05 * h, f"viento {m['viento_kmh']:.0f} km/h del {m['viento_dir_texto']}", ha="center", fontsize=7.5,
                    color="#1f3b73", zorder=21, bbox=dict(fc="w", ec="none", alpha=0.75, pad=1.5))
            s = d["superficie"]; fr = d["frente"]; ex = d["exposicion"]
            txt = (f"Superficie: {s['quemada_ha']:.1f} ha (+{s['incremento_ha']:.1f})\n"
                   f"Frente activo: {d['perimetro']['activo_km']:.2f} km\n"
                   f"ROS máx: {fr['velocidad_cabeza_m_min']:.1f} m/min · I máx: {fr['intensidad_max_kw_m']:.0f} kW/m\n"
                   f"T {m['temp_c']:.0f} °C · HR {m['hr_pct']:.0f} % · m1h {m['humedad_muerta_1h_pct']:.0f} %\n"
                   f"Viviendas: {ex['viviendas_afectadas']} afect. · {ex['viviendas_amenazadas']} amen.\n"
                   f"Tendido: {ex['tendido_km_quemado']:.2f} km · Caminos: {ex['caminos_km_afectados']:.2f} km")
            ax.text(0.99, 0.01, txt, transform=ax.transAxes, ha="right", va="bottom", fontsize=7.5, family="monospace", zorder=22,
                    bbox=dict(fc="w", ec="#666", alpha=0.9, pad=4))
        ax.set_title(titulo, fontsize=10, loc="left")

    def _leyenda(self, ax):
        items = [Patch(fc=COL_IGNICION, label="Ignición"), Patch(fc=COL_COMBUSTION, label="Combustión"), Patch(fc=COL_QUEMADO, label="Quemado"),
                 Line2D([], [], color="white", lw=1, label="Isócronas (1 h)"),
                 Line2D([], [], color="#555555", lw=1, label="Caminos"), Line2D([], [], color="#8e24aa", lw=1, ls="--", label="Red MT"),
                 Line2D([], [], marker="s", color="w", markerfacecolor="#2ca02c", markeredgecolor="k", ms=6, label="Vivienda a salvo"),
                 Line2D([], [], marker="s", color="w", markerfacecolor="#ff7f00", markeredgecolor="k", ms=6, label="Vivienda amenazada"),
                 Line2D([], [], marker="s", color="w", markerfacecolor="#000000", markeredgecolor="w", ms=6, label="Vivienda afectada")]
        if self.perimetro_obs is not None:
            items.append(Line2D([], [], color=COL_OBS, lw=1.6, label="Perímetro observado"))
        if self.focos is not None:
            items.append(Line2D([], [], marker="^", color="w", markerfacecolor="#ff00ff", markeredgecolor="k", ms=7, label="Focos VIIRS"))
        if getattr(self.au, "contencion", None) is not None:
            items.append(Patch(fc=COL_LINEA, label="Línea de contención"))
        ax.legend(handles=items, loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=7.5, frameon=False, title="Referencias", title_fontsize=8)

    def figura_hora(self, d: dict, ruta: Path, dpi: int = 110):
        t_min = d["minutos_desde_t0"]
        fig, ax = plt.subplots(figsize=(11, 8.5))
        self._base(ax)
        af, comb = self._estados(ax, t_min)
        self._isocronas(ax, t_min - 1e-6)
        self._infra_dinamica(ax, af, comb, float(self.cfg["parametros"]["viviendas_buffer_m"]))
        self._observado(ax)
        for ig in self.au.igniciones:
            x, y = self.g.centros(ig.fila, ig.col)
            ax.plot(x, y, marker="*", color="yellow", markeredgecolor="k", ms=12, zorder=10)
        titulo = f"{self.nombre} · hora {d['hora_indice']:02d} · {d['timestamp'][:16].replace('T', ' ')} local"
        self._decoracion(ax, d, titulo)
        self._leyenda(ax)
        fig.tight_layout()
        fig.savefig(ruta, dpi=dpi)
        plt.close(fig)
        return ruta

    def figura_final(self, ruta: Path, t_min: float, dpi: int = 130):
        fig, ax = plt.subplots(figsize=(11, 8.5))
        self._base(ax)
        tl = self.au.t_llegada
        af = tl <= t_min
        rgba = np.zeros(af.shape + (4,), "float32"); rgba[af] = matplotlib.colors.to_rgba("#fdae61", 0.55)
        ax.imshow(rgba, extent=self.extent, interpolation="nearest", zorder=4)
        hay_linea = self._linea(ax, t_min)
        self._isocronas(ax, t_min, color="k", lw=0.8, etiquetas=True)
        self._observado(ax)
        for ig in self.au.igniciones:
            x, y = self.g.centros(ig.fila, ig.col)
            ax.plot(x, y, marker="*", color="yellow", markeredgecolor="k", ms=12, zorder=10)
        self._decoracion(ax, None, f"{self.nombre} · isócronas horarias · área simulada {af.sum()*self.g.area_celda_ha:.1f} ha")
        items = [Patch(fc="#fdae61", alpha=0.55, label="Área simulada"), Line2D([], [], color="k", lw=0.8, label="Isócronas (1 h)")]
        if hay_linea:
            items.append(Patch(fc=COL_LINEA, label="Línea de contención"))
        if self.perimetro_obs is not None:
            items.append(Line2D([], [], color=COL_OBS, lw=1.6, label="Perímetro observado"))
        if self.focos is not None:
            items.append(Line2D([], [], marker="^", color="w", markerfacecolor="#ff00ff", markeredgecolor="k", ms=7, label="Focos VIIRS"))
        ax.legend(handles=items, loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=8, frameon=False)
        fig.tight_layout(); fig.savefig(ruta, dpi=dpi); plt.close(fig)
        return ruta


def gif(rutas_png: list[Path], ruta: Path, fps: float = 1.5):
    import imageio.v2 as imageio
    frames = [imageio.imread(p) for p in rutas_png]
    if not frames:
        return None
    h = min(f.shape[0] for f in frames); w = min(f.shape[1] for f in frames)
    frames = [f[:h, :w] for f in frames]
    imageio.mimsave(ruta, frames, duration=1000.0 / fps, loop=0)
    return ruta


def recuadro_automatico(au, perimetro_obs=None, margen_m: float = 1000.0, min_lado_m: float = 3000.0) -> tuple:
    g = au.capas.grilla
    af = au.afectada
    xs, ys = [], []
    if af.any():
        f, c = np.nonzero(af); x, y = g.centros(f, c); xs += [x.min(), x.max()]; ys += [y.min(), y.max()]
    if perimetro_obs is not None and len(perimetro_obs):
        b = perimetro_obs.total_bounds; xs += [b[0], b[2]]; ys += [b[1], b[3]]
    for ig in au.igniciones:
        x, y = g.centros(ig.fila, ig.col); xs.append(x); ys.append(y)
    if not xs:
        return g.bounds
    x0, x1, y0, y1 = min(xs) - margen_m, max(xs) + margen_m, min(ys) - margen_m, max(ys) + margen_m
    lado = max(x1 - x0, y1 - y0, min_lado_m)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    x0, x1, y0, y1 = cx - lado / 2, cx + lado / 2, cy - lado / 2, cy + lado / 2
    return (max(x0, g.xmin), max(y0, g.ymin), min(x1, g.xmax), min(y1, g.ymax))
