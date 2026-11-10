"""Viento: altura de referencia, factor de ajuste a media llama (WAF) y campo de viento.

- La meteorología trae viento a 10 m. Rothermel usa viento a media llama. Se pasa primero a
  20 ft (U_20ft = U_10m / 1,15 = 0,87·U_10m, perfil logarítmico; Turner & Lawson 1978; Lawson &
  Armitage 2008) y después se multiplica por el WAF (referido a 20 ft).
  v4.0: el factor es `ParametrosViento.factor_10m_20ft` (0,87). V.4 lo tenía invertido
  (1/0,87 = 1,149: viento a media llama ×1,32; docs/v4.0/15, P1); `sim_v4_original.yaml` lo
  reproduce con `viento.factor_10m_20ft: 1.1494252873563218`. La constante `F_10M_A_20FT` se
  conserva por compatibilidad de importación y vale el factor corregido.
- WAF sin dosel (Andrews 2012, RMRS-GTR-266, ec. 7): WAF = 1.83 / ln((20 + 0.36 δ) / (0.13 δ)),
  con δ la profundidad del lecho en ft. Bajo dosel se usan constantes (0.3 TU, 0.2 TL).
- Campo de viento v1: uniforme (serie horaria) más un ajuste topográfico simple:
      factor = 1 + k_pend · tan(θ) · cos(orientación − dir_desde) + k_relieve · relieve/escala
  barlovento acelera, sotavento frena, crestas aceleran, hondonadas frenan. Acotado a [0.7, 1.3].
  Es una simplificación declarada; la interfaz `CampoViento` permite cargar un campo externo
  (p. ej. WindNinja) como GeoTIFF u/v en la grilla del estándar.
- Campo WindNinja (v4.0, `fuente: windninja`, docs/v4.0/17): la biblioteca de campos unitarios de v3.0
  (`datos/inputSimulacion/viento/viento_unitario_<dominio>_100m_brush_*.nc`, solver de conservación de masa,
  72 direcciones cada 5°, 100 m, viento a 10 m, U este / V norte por m/s de entrada). La solución es lineal en
  la velocidad (verificado en v3.0, docs/v3.0/03): en cada instante, U,V = velocidad · campo unitario de la
  dirección meteorológica, interpolado entre las dos direcciones vecinas (como `BibliotecaViento.campo` de v3.0)
  y muestreado de forma bilineal en el centro de las celdas activas. Corrige **velocidad y dirección** por el
  relieve (canalización en valles, aceleración en crestas, desvío alrededor de los cerros); el factor
  topográfico simple no se aplica. Fuera de la biblioteca o sin dato: viento uniforme de la serie.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

KMH_A_FT_MIN = 1000.0 / 0.3048 / 60.0     # 1 km/h = 54.68 ft/min
KMH_A_MI_H = 0.621371
F_10M_A_20FT = 0.87                        # U_20ft / U_10m (corregido; V.4 usaba 1/0.87)
F_10M_A_20FT_V4 = 1.0 / 0.87               # valor de V.4 tal como se entregó (solo referencia)


def waf_sin_dosel(profundidad_ft: np.ndarray) -> np.ndarray:
    d = np.maximum(np.asarray(profundidad_ft, float), 0.05)
    return 1.83 / np.log((20.0 + 0.36 * d) / (0.13 * d))


@dataclass
class ParametrosViento:
    k_pendiente: float = 0.5      # ajuste barlovento/sotavento por tan(θ) (a calibrar)
    k_relieve: float = 0.3        # ajuste por relieve relativo (a calibrar)
    escala_relieve_m: float = 100.0
    ventana_relieve: int = 7      # celdas del filtro de media para el relieve relativo
    factor_min: float = 0.7
    factor_max: float = 1.3
    factor_10m_20ft: float = F_10M_A_20FT   # U_20ft = factor · U_10m (V.4 original: 1/0.87)
    fuente: str = "serie"         # serie (uniforme + factor topográfico, V.4) | windninja (biblioteca de v3.0)
    biblioteca: str | None = None # .nc de la biblioteca (absoluta o relativa al repositorio); null = la del dominio
    interpolar_direccion: bool = True   # interpolar entre las dos direcciones vecinas de la biblioteca (5°)


FUENTES_VIENTO = ("serie", "windninja")


def buscar_biblioteca(ruta: str | None = None) -> Path:
    """Biblioteca WindNinja: la indicada (relativa al repositorio si no es absoluta) o la más reciente del dominio."""
    from ..rutas import raiz_repositorio
    if ruta:
        p = Path(ruta)
        p = p if p.is_absolute() else raiz_repositorio() / p
        if not p.exists():
            raise FileNotFoundError(f"viento WindNinja: no existe la biblioteca {p}")
        return p
    d = raiz_repositorio() / "datos" / "inputSimulacion" / "viento"
    cand = sorted(d.glob("viento_unitario_*_100m_*.nc"), key=lambda q: q.stat().st_mtime)
    if not cand:
        raise FileNotFoundError(f"viento WindNinja: no hay biblioteca viento_unitario_*.nc en {d} (src/v3.0/scripts/preparar_evento.py "
                                "la genera con WindNinja); usar `viento.fuente: serie`")
    return cand[-1]


class BibliotecaWindNinja:
    """Campos unitarios de WindNinja (v3.0) leídos con el controlador netCDF de GDAL, sin xarray.

    Las direcciones se leen bajo demanda y quedan en memoria (2 × 1,9 MB por dirección a 100 m)."""

    def __init__(self, ruta: Path):
        import warnings
        self.ruta = Path(ruta)
        self._ds = None
        try:
            import rasterio
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")          # el NetCDF no trae geotransformación: se arma con x, y
                with rasterio.open(f'NETCDF:"{self.ruta}":x') as s:
                    xs = s.read(1).ravel().astype("float64")
                with rasterio.open(f'NETCDF:"{self.ruta}":y') as s:
                    ys = s.read(1).ravel().astype("float64")
                with rasterio.open(f'NETCDF:"{self.ruta}":direccion') as s:
                    self.dirs = s.read(1).ravel().astype("float64")
        except Exception as e:
            # GDAL sin controlador netCDF (p. ej. otra compilación de rasterio): xarray, como v3.0 (Colab lo trae)
            try:
                import xarray as xr
            except ImportError:
                raise RuntimeError(f"no se puede leer {self.ruta}: rasterio sin netCDF ({e}) y sin xarray "
                                   "(pip install xarray netCDF4) — o usar `viento: serie`") from e
            self._ds = xr.open_dataset(self.ruta)
            xs = self._ds["x"].values.astype("float64"); ys = self._ds["y"].values.astype("float64")
            self.dirs = self._ds["direccion"].values.astype("float64")
        if len(self.dirs) < 2 or not np.allclose(np.diff(self.dirs), self.dirs[1] - self.dirs[0]):
            raise ValueError(f"{self.ruta}: direcciones irregulares {self.dirs[:5]}…")
        self.paso = float(self.dirs[1] - self.dirs[0])
        self.res = float(xs[1] - xs[0])
        if ys[1] > ys[0]:
            raise ValueError(f"{self.ruta}: se esperaba y decreciente (fila 0 al norte)")
        self.x0, self.y0 = float(xs[0]), float(ys[0])   # centro de la celda (0, 0)
        self.forma = (len(ys), len(xs))
        self._uv: dict[int, tuple[np.ndarray, np.ndarray]] = {}

    def campo_unitario(self, k: int) -> tuple[np.ndarray, np.ndarray]:
        k = int(k) % len(self.dirs)
        if k not in self._uv and self._ds is not None:
            # xarray lee las filas en el orden guardado (fila 0 = y[0], norte): no hay que invertir
            self._uv[k] = (self._ds["U"].isel(direccion=k).values.astype("float32"),
                           self._ds["V"].isel(direccion=k).values.astype("float32"))
        if k not in self._uv:
            import rasterio
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                out = []
                for var in ("U", "V"):
                    with rasterio.open(f'NETCDF:"{self.ruta}":{var}') as s:
                        # GDAL entrega las variables 2-D de este NetCDF (sin grid_mapping) de abajo hacia arriba: se
                        # invierten las filas para que la fila 0 sea y[0] (norte), como las lee xarray en v3.0.
                        # Verificado: corr(velocidad, relieve) = +0,67…+0,74 invertido contra ≈ 0 sin invertir.
                        a = s.read(k + 1).astype("float32")[::-1].copy()
                    if a.shape != self.forma:
                        raise ValueError(f"{self.ruta}: {var} con forma {a.shape} ≠ {self.forma}")
                    out.append(a)
            self._uv[k] = (out[0], out[1])
        return self._uv[k]

    def muestrear(self, x: np.ndarray, y: np.ndarray, dir_desde: float, interpolar: bool = True) -> tuple[np.ndarray, np.ndarray]:
        """U, V unitarios (por m/s de entrada) en los puntos (x, y) EPSG:5345 para la dirección meteorológica dada."""
        from scipy.ndimage import map_coordinates
        pos = (float(dir_desde) % 360.0) / self.paso
        i0 = int(np.floor(pos)) % len(self.dirs); i1 = (i0 + 1) % len(self.dirs); w = pos - np.floor(pos)
        if not interpolar:
            i0, w = (i1 if w > 0.5 else i0), 0.0
        fil = (self.y0 - np.asarray(y, float)) / self.res
        col = (np.asarray(x, float) - self.x0) / self.res
        coords = np.vstack([fil.ravel(), col.ravel()])
        U = V = None
        for k, peso in ((i0, 1.0 - w), (i1, w)):
            if peso <= 1e-9:
                continue
            Uk, Vk = self.campo_unitario(k)
            u = map_coordinates(Uk, coords, order=1, mode="constant", cval=np.nan)
            v = map_coordinates(Vk, coords, order=1, mode="constant", cval=np.nan)
            U = peso * u if U is None else U + peso * u
            V = peso * v if V is None else V + peso * v
        return U.reshape(np.shape(x)), V.reshape(np.shape(x))


def relieve_relativo(mdt: np.ndarray, nodata: float, ventana: int) -> np.ndarray:
    """MDT − media móvil (ventana × ventana): positivo en crestas, negativo en hondonadas."""
    from scipy.ndimage import uniform_filter
    z = np.where(mdt == nodata, np.nan, mdt).astype("float32")
    z = np.where(np.isnan(z), np.nanmean(z), z)
    return z - uniform_filter(z, size=ventana, mode="nearest")


def factor_topografico(pendiente_deg: np.ndarray, orientacion_deg: np.ndarray, plano: np.ndarray,
                       relieve_m: np.ndarray, dir_desde_deg: float, p: ParametrosViento) -> np.ndarray:
    """Multiplicador del viento a 10 m por celda para la dirección `dir_desde_deg`."""
    tan_p = np.tan(np.deg2rad(pendiente_deg))
    # la ladera "mira" hacia su orientación; mira al viento si orientación ≈ dirección desde donde sopla
    cosang = np.cos(np.deg2rad(orientacion_deg - dir_desde_deg))
    f = 1.0 + p.k_pendiente * np.where(plano, 0.0, tan_p * cosang)
    f += p.k_relieve * np.clip(relieve_m / p.escala_relieve_m, -1.0, 1.0)
    return np.clip(f, p.factor_min, p.factor_max)


class CampoViento:
    """Fuente de viento por celda y hora: externo (GeoTIFF u/v por hora), biblioteca WindNinja, o uniforme + ajuste
    topográfico (serie)."""

    def __init__(self, capas, parametros: ParametrosViento, externo: dict | None = None, grilla=None, ventana=None):
        self.p = parametros
        self.capas = capas
        self.relieve = relieve_relativo(capas.mdt, capas.nodata_mdt, parametros.ventana_relieve)
        self.externo = None
        self.biblioteca = None
        if parametros.fuente not in FUENTES_VIENTO:
            raise ValueError(f"viento.fuente '{parametros.fuente}' desconocida (opciones: {', '.join(FUENTES_VIENTO)})")
        if externo:
            self.externo = _cargar_campo_externo(externo, grilla, ventana)
        elif parametros.fuente == "windninja":
            g = grilla if grilla is not None else capas.grilla
            self.biblioteca = BibliotecaWindNinja(buscar_biblioteca(parametros.biblioteca))
            self._x0, self._y0, self._res = float(g.xmin), float(g.ymax), float(g.res)
            # la biblioteca debe cubrir la ventana de simulación (si no, esas celdas usan la serie uniforme)
            b = self.biblioteca
            xb = (b.x0 - b.res / 2, b.x0 + (b.forma[1] - 0.5) * b.res); yb = (b.y0 - (b.forma[0] - 0.5) * b.res, b.y0 + b.res / 2)
            self.cubre = (xb[0] <= g.xmin and g.xmin + g.ancho * g.res <= xb[1] and yb[0] <= g.ymax - g.alto * g.res and g.ymax <= yb[1])

    def velocidad_dir(self, idx_f: np.ndarray, idx_c: np.ndarray, vel_kmh: float, dir_desde: float, hora_idx: int):
        """Devuelve (vel_kmh, dir_desde_deg) por celda para las celdas (idx_f, idx_c)."""
        if self.externo is not None:
            u = self.externo["u"][min(hora_idx, self.externo["u"].shape[0] - 1), idx_f, idx_c]
            v = self.externo["v"][min(hora_idx, self.externo["v"].shape[0] - 1), idx_f, idx_c]
            vel = np.hypot(u, v)
            d = (np.degrees(np.arctan2(-u, -v)) + 360) % 360
            return vel, d
        if self.biblioteca is not None:
            x = self._x0 + (np.asarray(idx_c, float) + 0.5) * self._res
            y = self._y0 - (np.asarray(idx_f, float) + 0.5) * self._res
            U, V = self.biblioteca.muestrear(x, y, dir_desde, self.p.interpolar_direccion)
            vel = vel_kmh * np.hypot(U, V)
            d = (np.degrees(np.arctan2(-U, -V)) + 360.0) % 360.0
            sin_dato = ~np.isfinite(vel)
            if sin_dato.any():
                vel = np.where(sin_dato, vel_kmh, vel); d = np.where(sin_dato, dir_desde, d)
            return vel, d
        f = factor_topografico(self.capas.pendiente[idx_f, idx_c], self.capas.orientacion[idx_f, idx_c],
                               self.capas.plano[idx_f, idx_c], self.relieve[idx_f, idx_c], dir_desde, self.p)
        return vel_kmh * f, np.full(idx_f.shape, dir_desde, float)


def _cargar_campo_externo(externo: dict, grilla, ventana) -> dict:
    """GeoTIFF multibanda u y v (km/h, componentes hacia donde va el viento); banda i = hora i."""
    import rasterio
    out = {}
    for k in ("u", "v"):
        ruta = Path(externo[k])
        with rasterio.open(ruta) as src:
            grilla_base = grilla.base if hasattr(grilla, "base") else grilla
            grilla_base.verificar_raster(src, f"viento {k}")
            out[k] = src.read(window=ventana).astype("float32") if ventana is not None else src.read().astype("float32")
    if out["u"].shape != out["v"].shape:
        raise ValueError("Los campos de viento u y v no tienen la misma forma")
    return out
