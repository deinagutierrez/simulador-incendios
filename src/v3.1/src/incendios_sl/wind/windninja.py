"""Integración con WindNinja 4.x (CLI) — solver de conservación de masa.

Estrategia (verificada en la Etapa 2): la solución del solver de masa con estabilidad neutra es lineal en la
velocidad de entrada, por lo que se construye una biblioteca de campos unitarios por clase de dirección
(p. ej. 72 clases de 5°) y cada hora se obtiene como velocidad_h × campo_unitario(dirección_h).

Convenciones (verificadas): `input_direction` y las salidas `*_ang` son dirección meteorológica (desde);
`*_u.asc` / `*_v.asc` son componentes este/norte en las unidades de `output_speed_units`.
"""
from __future__ import annotations

import glob
import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import numpy as np
import psutil
import rasterio
import xarray as xr
from rasterio.enums import Resampling
from rasterio.warp import reproject

from .. import config as cfgmod
from ..grilla import Grilla
from ..procedencia import hash_archivo, hash_dict, ahora_utc

log = logging.getLogger(__name__)


def localizar_exe() -> Path:
    h = cfgmod.cargar_rutas_herramientas()
    cand = [h.get("windninja_cli")] if h.get("windninja_cli") else []
    cand += [os.environ.get("WINDNINJA_CLI"), Path.home() / "tools" / "WindNinja-4.0.0" / "install" / "bin" / "WindNinja_cli.exe"]
    for c in cand:
        if c and Path(c).exists():
            return Path(c)
    raise FileNotFoundError("WindNinja_cli.exe no encontrado; indique la ruta en config/herramientas.yaml (windninja_cli) o WINDNINJA_CLI")


def leer_asc(path: Path) -> tuple[np.ndarray, dict[str, float]]:
    hdr: dict[str, float] = {}
    with open(path) as f:
        for _ in range(6):
            k, v = f.readline().split()
            hdr[k.lower()] = float(v)
    arr = np.loadtxt(path, skiprows=6, dtype=np.float32)
    if "nodata_value" in hdr:
        arr = np.where(arr == hdr["nodata_value"], np.nan, arr)
    return arr, hdr


class WindNinja:
    def __init__(self, dem_path: Path, malla_m: float = 100.0, vegetacion: str = "brush", altura_salida_m: float = 10.0,
                 hilos: int = 12, dir_trabajo: Path | None = None, exe: Path | None = None):
        self.exe = exe or localizar_exe()
        self.dem = Path(dem_path).resolve()
        self.malla = float(malla_m)
        self.veg = vegetacion
        self.altura = float(altura_salida_m)
        self.hilos = int(hilos)
        self.dir = Path(dir_trabajo or cfgmod.dir_derivados("viento"))
        self.dir.mkdir(parents=True, exist_ok=True)
        self.version = self._version()

    def _version(self) -> str:
        try:
            r = subprocess.run([str(self.exe), "--version"], capture_output=True, text=True, timeout=60)
            m = re.search(r"WindNinja version:\s*(\S+)", r.stdout)
            return m.group(1) if m else "?"
        except Exception:  # pragma: no cover
            return "?"

    def parametros(self) -> dict[str, Any]:
        return {"windninja_version": self.version, "dem_sha256": hash_archivo(self.dem), "malla_m": self.malla,
                "vegetacion": self.veg, "altura_salida_m": self.altura, "solver": "conservacion_de_masa",
                "diurnal_winds": False, "non_neutral_stability": False}

    # ------------------------------------------------------------------
    def cfg_texto(self, velocidad_ms: float, direccion_desde: float, out_dir: Path) -> str:
        return "\n".join([
            f"num_threads              = {self.hilos}",
            f"elevation_file           = {self.dem.as_posix()}",
            "initialization_method    = domainAverageInitialization",
            # momentum_flag / non_neutral_stability / diurnal_winds: valores por defecto (false); declararlos juntos
            # provoca "Conflicting options" en el CLI 4.0.0 (verificado)
            f"input_speed              = {velocidad_ms:.3f}",
            "input_speed_units        = mps",
            f"input_direction          = {direccion_desde:.2f}",
            "input_wind_height        = 10.0",
            "units_input_wind_height  = m",
            f"output_wind_height       = {self.altura:.1f}",
            "units_output_wind_height = m",
            "output_speed_units       = mps",
            f"vegetation               = {self.veg}",
            f"mesh_resolution          = {self.malla:.1f}",
            "units_mesh_resolution    = m",
            "write_ascii_output       = true",
            "ascii_out_uv             = true",
            f"ascii_out_resolution     = {self.malla:.1f}",
            "units_ascii_out_resolution = m",
            "write_goog_output        = false",
            "write_shapefile_output   = false",
            "write_farsite_atm        = false",
            f"output_path              = {out_dir.as_posix()}",
            "",
        ])

    def ejecutar(self, velocidad_ms: float, direccion_desde: float, out_dir: Path) -> dict[str, Any]:
        """Ejecuta una corrida y devuelve U, V (m/s), cabecera y registro (tiempo, memoria, código)."""
        out_dir.mkdir(parents=True, exist_ok=True)
        for f in out_dir.glob("*"):
            f.unlink()
        cfg = out_dir / "windninja.cfg"
        cfg.write_text(self.cfg_texto(velocidad_ms, direccion_desde, out_dir))
        env = dict(os.environ, NINJA_DISABLE_CALL_HOME="TRUE", NINJA_DISABLE_THREDDS_UPDATE="TRUE")
        t0 = time.time()
        p = subprocess.Popen([str(self.exe), str(cfg)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
        pico = 0
        try:
            pp = psutil.Process(p.pid)
            while p.poll() is None:
                try:
                    pico = max(pico, pp.memory_info().rss)
                except psutil.Error:
                    pass
                time.sleep(0.25)
        finally:
            out = p.stdout.read() if p.stdout else ""
        reg = {"velocidad_ms": velocidad_ms, "direccion_desde": direccion_desde, "codigo_salida": p.returncode,
               "segundos": round(time.time() - t0, 2), "memoria_pico_gb": round(pico / 1e9, 3), "stdout_final": out[-800:]}
        (out_dir / "registro.json").write_text(json.dumps(reg, indent=2))
        if p.returncode != 0:
            raise RuntimeError(f"WindNinja terminó con código {p.returncode}: {out[-500:]}")
        u_files = glob.glob(str(out_dir / "*_u.asc")); v_files = glob.glob(str(out_dir / "*_v.asc"))
        if not u_files or not v_files:
            raise RuntimeError("WindNinja no produjo archivos *_u.asc/*_v.asc")
        U, hdr = leer_asc(Path(u_files[0])); V, _ = leer_asc(Path(v_files[0]))
        return {"U": U, "V": V, "cabecera": hdr, "registro": reg}

    # ------------------------------------------------------------------
    def biblioteca_unitaria(self, paso_deg: float = 5.0, velocidad_ref: float = 10.0, etiqueta: str = "dominio") -> Path:
        """Campos unitarios (por m/s de entrada) para cada clase de dirección; NetCDF con dims (direccion, y, x).

        Cada dirección se guarda en un .npz propio en una carpeta de caché (robusto ante interrupciones y lecturas
        concurrentes); el NetCDF se ensambla al final de forma atómica. Reanuda las direcciones faltantes."""
        params = self.parametros() | {"paso_deg": paso_deg, "velocidad_ref": velocidad_ref}
        clave = hash_dict(params)[:12]
        out = self.dir / f"viento_unitario_{etiqueta}_{int(self.malla)}m_{self.veg}_{clave}.nc"
        from .. import config as _cfg; cache = _cfg.dir_procesados() / "windninja" / f"_campos_{etiqueta}_{int(self.malla)}m_{self.veg}_{clave}"
        cache.mkdir(parents=True, exist_ok=True)
        direcciones = np.arange(0.0, 360.0, paso_deg)
        if out.exists():
            try:
                with xr.open_dataset(out) as ds:
                    Uds = ds["U"].values; Vds = ds["V"].values
                    completo = len(ds["direccion"]) == len(direcciones) and not np.isnan(Uds[:, 0, 0]).any()
                    if completo:
                        log.info("biblioteca de viento reutilizada: %s", out.name)
                        return out
                    # NetCDF parcial (versión anterior del módulo): volcar lo válido a la caché
                    h = {"x0": float(ds["x"].values[0]), "y0": float(ds["y"].values[0]), "res": float(ds["x"].values[1] - ds["x"].values[0])}
                    for i, d in enumerate(ds["direccion"].values):
                        f = cache / f"dir_{d:06.1f}.npz"
                        if not f.exists() and not np.isnan(Uds[i, 0, 0]):
                            np.savez_compressed(f, U=Uds[i].astype(np.float32), V=Vds[i].astype(np.float32), hdr=json.dumps(h))
            except Exception as e:  # pragma: no cover
                log.warning("no se pudo leer el NetCDF previo (%s); se reconstruye desde la caché", e)
        tmp = self.dir / "_tmp_run"
        registros = []
        for d in direcciones:
            f = cache / f"dir_{d:06.1f}.npz"
            if f.exists():
                continue
            r = self.ejecutar(velocidad_ref, float(d), tmp)
            hdr = r["cabecera"]
            h = {"x0": hdr["xllcorner"] + hdr["cellsize"] / 2, "y0": hdr["yllcorner"] + (r["U"].shape[0] - 0.5) * hdr["cellsize"], "res": hdr["cellsize"]}
            np.savez_compressed(f, U=(r["U"] / velocidad_ref).astype(np.float32), V=(r["V"] / velocidad_ref).astype(np.float32), hdr=json.dumps(h))
            registros.append(r["registro"])
            log.info("WindNinja dir %5.1f°: %.1fs, %.2f GB", d, r["registro"]["segundos"], r["registro"]["memoria_pico_gb"])
        U_all = V_all = None
        for i, d in enumerate(direcciones):
            z = np.load(cache / f"dir_{d:06.1f}.npz")
            if U_all is None:
                U_all = np.empty((len(direcciones),) + z["U"].shape, np.float32); V_all = U_all.copy()
                h = json.loads(str(z["hdr"]))
                xs = h["x0"] + np.arange(z["U"].shape[1]) * h["res"]; ys = h["y0"] - np.arange(z["U"].shape[0]) * h["res"]
            U_all[i] = z["U"]; V_all[i] = z["V"]
        ds = xr.Dataset({"U": (("direccion", "y", "x"), U_all), "V": (("direccion", "y", "x"), V_all)},
                        coords={"direccion": direcciones, "y": ys, "x": xs},
                        attrs={"descripcion": "campos unitarios WindNinja (m/s por m/s de entrada a 10 m)",
                               "convencion": "direccion = meteorologica (desde); U este, V norte", "crs": "EPSG:5345",
                               "parametros": json.dumps(params), "generado_utc": ahora_utc()})
        tmp_nc = out.with_name(out.stem + ".tmp.nc")
        ds.to_netcdf(tmp_nc, encoding={"U": {"zlib": True, "complevel": 4}, "V": {"zlib": True, "complevel": 4}})
        ds.close()
        tmp_nc.replace(out)
        if registros:
            with open(out.with_suffix(".registro.json"), "a", encoding="utf-8") as f:
                for rg in registros:
                    f.write(json.dumps(rg) + "\n")
        return out


# ----------------------------------------------------------------------
class BibliotecaViento:
    """Lectura de la biblioteca unitaria y composición de campos horarios remuestreados a la grilla de simulación."""

    def __init__(self, path_nc: Path):
        self.path = Path(path_nc)
        self.ds = xr.open_dataset(self.path)
        self.dirs = self.ds["direccion"].values
        self.paso = float(self.dirs[1] - self.dirs[0]) if len(self.dirs) > 1 else 360.0
        self.U = self.ds["U"].values; self.V = self.ds["V"].values
        if np.isnan(self.U[:, 0, 0]).any():
            raise ValueError("biblioteca de viento incompleta")
        xs = self.ds["x"].values; ys = self.ds["y"].values
        res = float(xs[1] - xs[0])
        self.grilla = Grilla(self.ds.attrs.get("crs", "EPSG:5345"), res, float(xs[0] - res / 2), float(ys[-1] - res / 2),
                             float(xs[-1] + res / 2), float(ys[0] + res / 2))

    def campo(self, velocidad_ms: float, direccion_desde: float, interpolar: bool = True) -> tuple[np.ndarray, np.ndarray]:
        """U, V (m/s) en la malla de WindNinja para la condición dada (escalado lineal verificado)."""
        d = float(direccion_desde) % 360.0
        pos = d / self.paso
        i0 = int(np.floor(pos)) % len(self.dirs); i1 = (i0 + 1) % len(self.dirs); w = pos - np.floor(pos)
        if interpolar and w > 1e-6:
            U = (1 - w) * self.U[i0] + w * self.U[i1]; V = (1 - w) * self.V[i0] + w * self.V[i1]
        else:
            k = i1 if w > 0.5 else i0
            U = self.U[k]; V = self.V[k]
        return (velocidad_ms * U).astype(np.float32), (velocidad_ms * V).astype(np.float32)

    def a_grilla(self, U: np.ndarray, V: np.ndarray, destino: Grilla) -> tuple[np.ndarray, np.ndarray]:
        """Remuestreo bilineal de U y V (nunca de la dirección) a la grilla destino (p. ej. 30 m)."""
        return remuestrear_uv(U, V, self.grilla, destino)

    def cerrar(self):
        self.ds.close()


def remuestrear_uv(U: np.ndarray, V: np.ndarray, origen: Grilla, destino: Grilla) -> tuple[np.ndarray, np.ndarray]:
    """Remuestreo bilineal de U y V (nunca de la dirección) de la malla de WindNinja a la grilla destino."""
    outs = []
    for A in (U, V):
        dst = np.full(destino.shape, np.nan, np.float32)
        reproject(A, dst, src_transform=origen.transform, src_crs=origen.crs,
                  dst_transform=destino.transform, dst_crs=destino.crs, src_nodata=np.nan, dst_nodata=np.nan,
                  resampling=Resampling.bilinear)
        outs.append(dst)
    return outs[0], outs[1]
