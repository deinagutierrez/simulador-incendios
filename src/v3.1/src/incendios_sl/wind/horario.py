"""Viento horario local (v3.1, docs/v3.1/04).

La v3.0 compone el viento de cada hora con la biblioteca unitaria de WindNinja (solver de masa, estabilidad neutra) y una
única entrada: el promedio vectorial de los 16 puntos IFS del dominio. Acá se agregan cuatro fuentes alternativas,
elegidas con `viento.fuente_horaria` del YAML del modelo:

- `biblioteca`          (v3.0) promedio vectorial × biblioteca.
- `escalar`             velocidad = promedio escalar de los 16 puntos (el promedio vectorial pierde velocidad cuando los
                        puntos no coinciden en dirección); dirección del promedio vectorial; × biblioteca.
- `idw_puntos`          cada punto IFS compone su campo con la biblioteca y los campos se mezclan con pesos de distancia
                        inversa (potencia 2): dirección y velocidad varían en el espacio.
- `windninja_diurno`    una corrida de WindNinja por hora con vientos diurnos (pendiente–valle, Forthofer 2009),
                        entrada = promedio vectorial, temperatura y nubosidad del dominio.
- `windninja_puntos`    una corrida por hora con los 16 puntos IFS como estaciones (inicialización por puntos, sin
                        `match_points`) y vientos diurnos.

Los campos de WindNinja se generan antes de simular (`scripts/generar_viento_horario.py`) y se guardan por hora en
`datos/inputSimulacion/viento/horario/<evento>_<fuente>/<AAAAMMDDTHH>.npz` (U, V en cm/s, int16). Las horas sin campo
usan la biblioteca con el promedio vectorial (se informa cuántas).
"""
from __future__ import annotations

import glob
import json
import logging
import os
import subprocess
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .. import config as cfgmod
from ..grilla import Grilla
from .windninja import BibliotecaViento, leer_asc, localizar_exe

log = logging.getLogger(__name__)

FUENTES = ("biblioteca", "escalar", "idw_puntos", "windninja_diurno", "windninja_puntos")
ZONA = "America/Argentina/San_Luis"   # UTC−3 sin horario de verano en el período
CABECERA_ESTACION = ["Station_Name", "Coord_Sys(PROJCS,GEOGCS)", "Datum(WGS84,NAD83,NAD27)", "Lat/YCoord", "Lon/XCoord", "Height",
                     "Height_Units(meters,feet)", "Speed", "Speed_Units(mph,kph,mps,kts)", "Direction(degrees)", "Temperature",
                     "Temperature_Units(F,C)", "Cloud_Cover(%)", "Radius_of_Influence", "Radius_of_Influence_Units(miles,feet,meters,km)", "date_time"]


# ----------------------------------------------------------------------
def meteo_puntos(evento: str) -> tuple[pd.DataFrame, dict[str, tuple[float, float]]]:
    """Serie horaria de los 16 puntos IFS del evento y sus coordenadas (lon, lat del modelo)."""
    D = cfgmod.dir_entradas() / "meteo"
    csv = [p for p in glob.glob(str(D / f"{evento}_*.csv")) if not p.endswith("_dominio.csv")]
    js = [p for p in glob.glob(str(D / f"{evento}_*.json")) if not p.endswith(".parquet.json")]
    if not csv or not js:
        raise FileNotFoundError(f"falta la meteorología por punto de {evento} en {D}")
    df = pd.read_csv(csv[0], parse_dates=["time_utc"])
    pts = {p["punto_id"]: (float(p["lon_modelo"]), float(p["lat_modelo"])) for p in json.load(open(js[0], encoding="utf-8"))["puntos"]}
    return df, pts


def nubosidad_pct(time_utc: pd.Series, onda_corta: pd.Series, lat: float = -32.6, lon: float = -65.6) -> np.ndarray:
    """Nubosidad (%) estimada como 1 − radiación / radiación de cielo despejado (Kasten–Czeplak simplificado); de noche
    se arrastra el último valor diurno. La radiación de Open-Meteo es el promedio de la hora anterior: se evalúa el sol a
    mitad de esa hora."""
    t = pd.to_datetime(time_utc) - pd.Timedelta(minutes=30)
    doy = t.dt.dayofyear.to_numpy(); hora = t.dt.hour.to_numpy() + t.dt.minute.to_numpy() / 60.0
    decl = np.radians(23.44) * np.sin(2 * np.pi * (284 + doy) / 365.0)
    ang = np.radians(15.0 * (hora + lon / 15.0 - 12.0))
    cosz = np.sin(np.radians(lat)) * np.sin(decl) + np.cos(np.radians(lat)) * np.cos(decl) * np.cos(ang)
    despejado = 910.0 * np.clip(cosz, 0, None) - 30.0
    out = np.full(len(t), np.nan)
    dia = cosz > 0.2
    out[dia] = np.clip(100.0 * (1.0 - onda_corta.to_numpy()[dia] / despejado[dia]), 0.0, 100.0)
    return pd.Series(out).ffill().fillna(0.0).to_numpy()


# ----------------------------------------------------------------------
class PesosIDW:
    """Pesos de distancia inversa de los puntos IFS sobre la malla de la biblioteca (n_puntos, ny, nx), suman 1."""

    def __init__(self, lib: BibliotecaViento, pts: dict[str, tuple[float, float]], potencia: float = 2.0):
        from pyproj import Transformer
        tr = Transformer.from_crs("EPSG:4326", lib.grilla.crs, always_xy=True)
        g = lib.grilla
        xs = g.xmin + (np.arange(g.ncol) + 0.5) * g.res; ys = g.ymax - (np.arange(g.nfil) + 0.5) * g.res
        X, Y = np.meshgrid(xs, ys)
        self.ids = list(pts)
        w = []
        for pid in self.ids:
            px, py = tr.transform(*pts[pid])
            w.append(1.0 / np.maximum(np.hypot(X - px, Y - py), 50.0) ** potencia)
        w = np.array(w, np.float32)
        self.w = w / w.sum(axis=0, keepdims=True)


def viento_idw(lib: BibliotecaViento, pesos: PesosIDW, vels: np.ndarray, dirs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Mezcla en la malla de WindNinja de los campos de cada punto (vel_i × campo unitario(dir_i))."""
    U = np.zeros(pesos.w.shape[1:], np.float32); V = np.zeros_like(U)
    for k in range(len(pesos.ids)):
        u, v = lib.campo(float(vels[k]), float(dirs[k]))
        U += pesos.w[k] * u; V += pesos.w[k] * v
    return U, V


# ----------------------------------------------------------------------
def dir_horario(evento: str, fuente: str) -> Path:
    return cfgmod.dir_entradas() / "viento" / "horario" / f"{evento}_{fuente}"


class CamposHorarios:
    """Campos U, V por hora generados con WindNinja (npz por hora, cm/s en int16) sobre la malla de la salida ASCII."""

    def __init__(self, evento: str, fuente: str):
        self.dir = dir_horario(evento, fuente)
        meta = json.load(open(self.dir / "malla.json", encoding="utf-8"))
        self.grilla = Grilla(meta["crs"], meta["res"], meta["xmin"], meta["ymin"], meta["xmax"], meta["ymax"])
        self.horas = {pd.to_datetime(p.stem, format="%Y%m%dT%H", utc=True): p for p in self.dir.glob("*.npz") if not p.stem.endswith(".tmp")}

    def campo(self, hora: pd.Timestamp) -> tuple[np.ndarray, np.ndarray] | None:
        p = self.horas.get(pd.Timestamp(hora))
        if p is None:
            return None
        z = np.load(p)
        U = z["U"].astype(np.float32) / 100.0; V = z["V"].astype(np.float32) / 100.0
        U[z["U"] == np.iinfo(np.int16).min] = np.nan; V[z["V"] == np.iinfo(np.int16).min] = np.nan
        return U, V


def _guardar_hora(path: Path, U: np.ndarray, V: np.ndarray) -> None:
    nd = np.iinfo(np.int16).min
    a = lambda A: np.where(np.isfinite(A), np.clip(np.round(A * 100.0), nd + 1, np.iinfo(np.int16).max), nd).astype(np.int16)  # noqa: E731
    tmp = path.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, U=a(U), V=a(V)); tmp.replace(path)


# ----------------------------------------------------------------------
class GeneradorHorario:
    """Corre WindNinja hora por hora (diurno; por dominio o por puntos) y guarda los campos. Reanuda las horas que faltan.
    Trabaja en una carpeta de ruta corta (WindNinja no escribe la salida ASCII si la ruta es larga)."""

    def __init__(self, evento: str, fuente: str, dem: Path, malla_m: float = 100.0, vegetacion: str = "brush", hilos: int = 6,
                 trabajo: Path | None = None):
        if fuente not in ("windninja_diurno", "windninja_puntos"):
            raise ValueError(fuente)
        self.evento, self.fuente, self.dem = evento, fuente, Path(dem).resolve()
        self.malla, self.veg, self.hilos = float(malla_m), vegetacion, int(hilos)
        self.exe = localizar_exe()
        self.out = dir_horario(evento, fuente); self.out.mkdir(parents=True, exist_ok=True)
        self.trabajo = Path(trabajo or Path(os.environ.get("TEMP", "/tmp")) / "wnh") / f"{evento[-8:]}_{fuente[10:13]}"
        self.dom = pd.read_csv(glob.glob(str(cfgmod.dir_entradas() / "meteo" / f"{evento}_*_dominio.csv"))[0], parse_dates=["time_utc"])
        self.dom["nubosidad_pct"] = nubosidad_pct(self.dom.time_utc, self.dom.shortwave_radiation)
        if fuente == "windninja_puntos":
            self.pp, self.pts = meteo_puntos(evento)
            self.pp = self.pp.merge(self.dom[["time_utc", "nubosidad_pct"]], on="time_utc", how="left")

    def _cfg_comun(self, d: Path) -> list[str]:
        return [f"num_threads = {self.hilos}", f"elevation_file = {self.dem.as_posix()}", "input_wind_height = 10.0", "units_input_wind_height = m",
                "output_wind_height = 10.0", "units_output_wind_height = m", "output_speed_units = mps", f"vegetation = {self.veg}",
                f"mesh_resolution = {self.malla:.1f}", "units_mesh_resolution = m", "write_ascii_output = true", "ascii_out_uv = true",
                f"ascii_out_resolution = {self.malla:.1f}", "units_ascii_out_resolution = m", "write_goog_output = false",
                "write_shapefile_output = false", "write_farsite_atm = false", f"time_zone = {ZONA}", "diurnal_winds = true",
                f"output_path = {d.as_posix()}"]

    def _cfg_hora(self, h: pd.Timestamp, d: Path) -> list[str]:
        loc = h.tz_convert(ZONA)
        if self.fuente == "windninja_diurno":
            f = self.dom[self.dom.time_utc == h].iloc[0]
            return ["initialization_method = domainAverageInitialization", f"input_speed = {f.wind_speed_10m_vectorial:.2f}", "input_speed_units = mps",
                    f"input_direction = {f.wind_direction_10m:.1f}", f"uni_air_temp = {f.temperature_2m:.1f}", "air_temp_units = C",
                    f"uni_cloud_cover = {f.nubosidad_pct:.0f}", "cloud_cover_units = percent",
                    f"year = {loc.year}", f"month = {loc.month}", f"day = {loc.day}", f"hour = {loc.hour}", "minute = 0"]
        # por puntos: un archivo por estación con la hora pedida (una sola fila) y el índice Station_File_List
        est = d / "est"; est.mkdir(exist_ok=True)
        x = self.pp[self.pp.time_utc == h]; nombres = []
        hdr = ",".join(f'"{c}"' for c in CABECERA_ESTACION)
        for r in x.itertuples():
            lon, lat = self.pts[r.punto_id]
            fila = [r.punto_id, "GEOGCS", "WGS84", lat, lon, 10, "meters", round(r.wind_speed_10m, 2), "mps", round(r.wind_direction_10m),
                    round(r.temperature_2m, 1), "C", round(r.nubosidad_pct), -1, "km", h.strftime("%Y-%m-%dT%H:%M:%SZ")]
            (est / f"{r.punto_id}.csv").write_text(hdr + "\n" + ",".join(str(v) for v in fila) + "\n"); nombres.append(f"{r.punto_id}.csv")
        (est / "lista.csv").write_text("Station_File_List,\n" + "\n".join(nombres) + "\n")
        t = [f"{loc.year}", f"{loc.month}", f"{loc.day}", f"{loc.hour}", "0"]
        return ["initialization_method = pointInitialization", f"wx_station_filename = {(est / 'lista.csv').as_posix()}", "match_points = false",
                *[f"start_{k} = {v}" for k, v in zip(("year", "month", "day", "hour", "minute"), t)],
                *[f"stop_{k} = {v}" for k, v in zip(("year", "month", "day", "hour", "minute"), t)], "number_time_steps = 1"]

    def correr_hora(self, h: pd.Timestamp) -> dict:
        destino = self.out / f"{h.strftime('%Y%m%dT%H')}.npz"
        if destino.exists():
            return {"hora": str(h), "estado": "ya estaba"}
        d = self.trabajo / h.strftime("%Y%m%dT%H"); d.mkdir(parents=True, exist_ok=True)
        for f in d.glob("*.asc"):
            f.unlink()
        cfg = d / "wn.cfg"; cfg.write_text("\n".join(self._cfg_comun(d) + self._cfg_hora(h, d)) + "\n")
        env = dict(os.environ, NINJA_DISABLE_CALL_HOME="TRUE", NINJA_DISABLE_THREDDS_UPDATE="TRUE")
        t0 = time.time(); r = subprocess.run([str(self.exe), str(cfg)], capture_output=True, text=True, env=env)
        u = glob.glob(str(d / "*_u.asc")); v = glob.glob(str(d / "*_v.asc"))
        if r.returncode != 0 or not u or not v:
            raise RuntimeError(f"WindNinja {self.evento} {h}: código {r.returncode}: {r.stdout[-400:]} {r.stderr[-300:]}")
        U, hdr = leer_asc(Path(u[0])); V, _ = leer_asc(Path(v[0]))
        malla = self.out / "malla.json"
        if not malla.exists():
            cs = hdr["cellsize"]; x0 = hdr["xllcorner"]; y0 = hdr["yllcorner"]
            malla.write_text(json.dumps({"crs": "EPSG:5345", "res": cs, "xmin": x0, "ymin": y0, "xmax": x0 + cs * U.shape[1], "ymax": y0 + cs * U.shape[0],
                                         "fuente": self.fuente, "dem": self.dem.name, "windninja": str(self.exe)}))
        _guardar_hora(destino, U, V)
        for f in d.glob("*"):
            if f.is_file():
                f.unlink()
        return {"hora": str(h), "estado": "ok", "segundos": round(time.time() - t0, 1)}
