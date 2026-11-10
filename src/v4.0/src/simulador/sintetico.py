"""Escenarios sintéticos (terreno plano, combustible homogéneo, meteorología constante) para tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .io.grilla import Grilla
from .io.capas import Capas
from .io.meteo import SerieMeteo
from .config import fusionar, DEFAULTS


def grilla_sintetica(n: int = 201, res: float = 30.0) -> Grilla:
    return Grilla(crs="EPSG:5345", xmin=0.0, ymax=n * res, res=res, ancho=n, alto=n)


def capas_sinteticas(n: int = 201, codigo: int = 102, pendiente_deg: float = 0.0, orientacion_deg: float = 0.0,
                     res: float = 30.0, mdt_plano: bool = True) -> Capas:
    g = grilla_sintetica(n, res)
    shape = (n, n)
    if pendiente_deg > 0:
        # plano inclinado: la orientación es la dirección de bajada
        fil, col = np.indices(shape)
        x = col * res; y = -fil * res
        az = np.deg2rad(orientacion_deg)
        # el terreno sube en la dirección opuesta a la orientación
        z = -(x * np.sin(az) + y * np.cos(az)) * np.tan(np.deg2rad(pendiente_deg))
        mdt = (z - z.min() + 500).astype("int16")
        plano = np.zeros(shape, bool)
    else:
        mdt = np.full(shape, 500, "int16"); plano = np.ones(shape, bool)
    import geopandas as gpd
    vacio = gpd.GeoDataFrame(geometry=[], crs=g.crs)
    return Capas(grilla=g, base=g, ventana=None, mdt=mdt, nodata_mdt=-32768,
                 pendiente=np.full(shape, pendiente_deg, "float32"),
                 orientacion=np.full(shape, 0.0 if plano.all() else orientacion_deg, "float32"), plano=plano,
                 combustible=np.full(shape, codigo, "int16"), nodata_combustible=-9999,
                 camino_ancho=np.zeros(shape, "float32"), camino_tipo=np.full(shape, -1, "int8"),
                 vivienda=np.zeros(shape, bool), linea_mt=np.zeros(shape, bool),
                 caminos_gdf=vacio, viviendas_gdf=vacio, red_gdf=vacio)


def meteo_constante(t0: str = "2024-01-01T12:00:00-03:00", horas: int = 48, temp_c: float = 25.0, hr_pct: float = 25.0,
                    viento_kmh: float = 0.0, viento_dir_deg: float = 0.0, precip_mm: float = 0.0) -> SerieMeteo:
    t0 = pd.Timestamp(t0) - pd.Timedelta(hours=24)
    ts = pd.date_range(t0, periods=horas + 24, freq="h")
    df = pd.DataFrame({"timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S%z").str.replace(r"(\d{2})(\d{2})$", r"\1:\2", regex=True),
                       "temp_c": temp_c, "hr_pct": hr_pct, "viento_kmh": viento_kmh, "viento_dir_deg": viento_dir_deg,
                       "precip_mm": precip_mm, "fuente": "sintetico"})
    return SerieMeteo(df)


def config_sintetica(**kw) -> dict:
    cfg = fusionar(DEFAULTS, {"nombre": "sintetico", "dt_min": 2.0, "vecindad": 8, "parametros": {"viento": {"k_pendiente": 0.0, "k_relieve": 0.0}}})
    cfg = fusionar(cfg, kw)
    cfg["_dir"] = "."; cfg["_ruta"] = ""
    return cfg


def correr_sintetico(capas: Capas, meteo: SerieMeteo, cfg: dict, horas: float, t0: str = "2024-01-01T12:00:00-03:00",
                     fila: int | None = None, col: int | None = None):
    """Corre el autómata desde el centro (o (fila, col)) durante `horas`. Devuelve el autómata."""
    from .ca.automata import Automata
    au = Automata(capas, meteo, cfg)
    t0 = pd.Timestamp(t0)
    au.preparar(t0, t0 + pd.Timedelta(hours=horas))
    n = capas.grilla.alto
    au.encender(n // 2 if fila is None else fila, n // 2 if col is None else col, t0, "centro")
    pasos = int(round(horas * 60 / cfg["dt_min"]))
    for _ in range(pasos):
        au.paso_tiempo()
        if not au.activo():
            break
    return au


def simular_sintetico(capas: Capas, meteo: SerieMeteo, cfg: dict, horas: float, t0: str = "2024-01-01T12:00:00-03:00",
                      fila: int | None = None, col: int | None = None, miembro: int = 0):
    """Como `correr_sintetico` pero con el bucle de las corridas (`corrida._simular`): L03, contención por combate,
    parada anticipada e indicadores horarios, sin escribir archivos. Devuelve (autómata, indicadores)."""
    from .ca.automata import Automata
    from .corrida import _simular
    au = Automata(capas, meteo, cfg)
    t0 = pd.Timestamp(t0)
    au.preparar(t0, t0 + pd.Timedelta(hours=horas))
    n = capas.grilla.alto
    ign = [(n // 2 if fila is None else fila, n // 2 if col is None else col, t0, "centro")]
    ind = _simular(au, ign, t0, horas, cfg, cfg.get("nombre", "sintetico"), None, None, miembro=miembro)
    return au, ind
