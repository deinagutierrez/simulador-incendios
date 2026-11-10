"""Evaluador externo común (protocolo de evaluación v1.0, §7 y §10). No importa nada de `SIM/` ni de `MOD/`.

Entrada: ToA (minutos o segundos desde t0; NaN o nodata = no quema) o estado horario (GeoTIFF multibanda; banda i =
quemado hasta t0 + i h), referencia (polígono o ráster), instantes y focos opcionales.
Salida: dict de métricas + filas en el formato largo de `CP/validacion/plantilla_metricas.csv`
(case_id, run, metrica, hora, valor).

Decisiones de implementación (registradas en E013):
- Grilla común: la del dominio (EPSG:5345, 30 m, origen 3513060 / 6417900, 1672 × 1671). Una entrada alineada a
  múltiplos de 30 m (caja de `SIM/`, bbox de `CP/`) se ubica por desplazamiento entero; otra, por vecino más cercano.
- IoU, Dice, omisión y comisión se calculan dentro de la máscara de evaluación (por defecto el dominio). No se
  restringe a "celdas combustibles" porque cada motor tiene su propio mapa de combustible y eso haría no comparables
  las cifras (la máscara de combustible solo se aplica si se pasa explícitamente, p. ej. para reproducir a `MOD/`).
- Rasterización de la referencia: `cobertura50` (≥ 50 % de la celda, supermuestreo a 5 m, estándar `CP/` D23) por
  defecto; `centro` reproduce `rasterio.features.rasterize` por defecto (lo que usa `SIM/`).
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.transform import Affine
from rasterio.warp import reproject, Resampling

VERSION = "0.1.0"
PROTOCOLO = "v1.0"
GRILLA_DOMINIO = dict(crs="EPSG:5345", transform=Affine(30.0, 0.0, 3513060.0, 0.0, -30.0, 6417900.0), shape=(1671, 1672))
HA_CELDA = 0.09


def sha256(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


@dataclass
class Grilla:
    crs: str
    transform: Affine
    shape: tuple[int, int]


def grilla_dominio() -> Grilla:
    return Grilla(**GRILLA_DOMINIO)


# ----------------------------------------------------------------------------- lectura y alineación
def a_grilla(arr: np.ndarray, tr: Affine, crs, destino: Grilla, relleno=np.nan) -> np.ndarray:
    """Ubica `arr` en la grilla destino: por desplazamiento entero si está alineada, si no por vecino más cercano."""
    out = np.full(destino.shape, relleno, dtype=np.float64)
    T = destino.transform
    alineada = (str(crs).upper().endswith("5345") and abs(tr.a - T.a) < 1e-9 and abs(tr.e - T.e) < 1e-9
                and abs(((tr.c - T.c) / T.a) - round((tr.c - T.c) / T.a)) < 1e-6 and abs(((T.f - tr.f) / T.a) - round((T.f - tr.f) / T.a)) < 1e-6)
    if alineada:
        c0 = int(round((tr.c - T.c) / T.a)); r0 = int(round((T.f - tr.f) / T.a))
        h, w = arr.shape
        rs, cs = max(r0, 0), max(c0, 0)
        re_, ce = min(r0 + h, destino.shape[0]), min(c0 + w, destino.shape[1])
        if re_ > rs and ce > cs:
            out[rs:re_, cs:ce] = arr[rs - r0:re_ - r0, cs - c0:ce - c0]
        return out
    reproject(arr.astype(np.float64), out, src_transform=tr, src_crs=crs, dst_transform=T, dst_crs=destino.crs,
              resampling=Resampling.nearest, src_nodata=np.nan, dst_nodata=np.nan)
    return out


def leer_toa(path, unidades: str = "min", destino: Grilla | None = None, nodata_extra: float | None = None):
    """Devuelve (toa_min en la grilla destino, NaN = no quema; t0 de la etiqueta `t_inicio_utc` o `t0_utc` si está;
    huella de la entrada)."""
    destino = destino or grilla_dominio()
    with rasterio.open(path) as r:
        a = r.read(1).astype(np.float64)
        nd = r.nodata
        tags = r.tags()
        tr, crs = r.transform, r.crs
        huella = np.ones(a.shape)
    if nd is not None and not (isinstance(nd, float) and math.isnan(nd)):
        a[a == nd] = np.nan
    if nodata_extra is not None:
        a[a == nodata_extra] = np.nan
    a[~np.isfinite(a)] = np.nan
    if unidades == "s":
        a = a / 60.0
    elif unidades == "h":
        a = a * 60.0
    t0 = tags.get("t_inicio_utc") or tags.get("t0_utc")      # t0_utc = etiqueta que escribe el adaptador de SIM
    return a_grilla(a, tr, crs, destino), (pd.Timestamp(t0) if t0 else None), a_grilla(huella, tr, crs, destino, relleno=0.0) > 0


def leer_estado_horario(path, destino: Grilla | None = None):
    """Estado horario multibanda (banda i = quemado hasta t0 + i h) -> ToA en minutos (primera hora quemada)."""
    destino = destino or grilla_dominio()
    with rasterio.open(path) as r:
        toa = np.full((r.height, r.width), np.nan)
        for i in range(1, r.count + 1):
            q = r.read(i) > 0
            toa[q & np.isnan(toa)] = i * 60.0
        return a_grilla(toa, r.transform, r.crs, destino)


def rasterizar_referencia(geoms_gdf, destino: Grilla | None = None, metodo: str = "cobertura50") -> np.ndarray:
    destino = destino or grilla_dominio()
    g = geoms_gdf.to_crs(destino.crs)
    shapes_ = [(geom, 1) for geom in g.geometry if geom is not None and not geom.is_empty]
    if metodo == "centro":
        return rasterize(shapes_, out_shape=destino.shape, transform=destino.transform, dtype="uint8").astype(bool)
    if metodo != "cobertura50":
        raise ValueError(metodo)
    # supermuestreo a 5 m (6 × 6) por bloques de filas para acotar memoria
    T = destino.transform; f = 6
    out = np.zeros(destino.shape, dtype=bool)
    paso = 200
    for r0 in range(0, destino.shape[0], paso):
        r1 = min(r0 + paso, destino.shape[0])
        Tf = Affine(T.a / f, 0, T.c, 0, T.e / f, T.f + r0 * T.e)
        sub = rasterize(shapes_, out_shape=((r1 - r0) * f, destino.shape[1] * f), transform=Tf, dtype="uint8")
        frac = sub.reshape(r1 - r0, f, destino.shape[1], f).mean(axis=(1, 3))
        out[r0:r1] = frac >= 0.5
    return out


# ----------------------------------------------------------------------------- métricas
def comparar(sim: np.ndarray, obs: np.ndarray) -> dict:
    inter = float((sim & obs).sum()); s = float(sim.sum()); o = float(obs.sum())
    return dict(ha_sim=s * HA_CELDA, ha_obs=o * HA_CELDA, iou=inter / (s + o - inter) if (s + o - inter) else np.nan,
                dice=2 * inter / (s + o) if (s + o) else np.nan, omision=1 - inter / o if o else np.nan,
                comision=1 - inter / s if s else np.nan, L=math.log(s / o) if s and o else (-math.inf if o else np.nan))


def centroide(m: np.ndarray, T: Affine):
    r, c = np.nonzero(m)
    if not len(r):
        return None
    return T.c + (c.mean() + 0.5) * T.a, T.f + (r.mean() + 0.5) * T.e


def igual_superficie(toa: np.ndarray, obs: np.ndarray, region: np.ndarray):
    """Corta el ToA donde A_sim = A_obs (dentro de la región). Devuelve (minutos de corte o None si no alcanza, máscara)."""
    n = int((obs & region).sum())
    v = np.sort(toa[region & np.isfinite(toa)])
    if n == 0 or len(v) < n:
        return None, np.isfinite(toa) & region
    tc = v[n - 1]
    return float(tc), np.isfinite(toa) & (toa <= tc) & region


def toca_borde(m: np.ndarray, dominio: np.ndarray) -> bool:
    from scipy import ndimage
    borde = dominio & ~ndimage.binary_erosion(dominio, border_value=0)
    return bool((m & borde).any())


def elipse_b1(ign_xy, viento_desde_deg: float, u10_ms: float, area_ha: float, region: np.ndarray, destino: Grilla | None = None):
    """B1: elipse de Anderson (1983) con foco trasero en la ignición, eje hacia donde va el viento, escalada a `area_ha`
    dentro de `region` (búsqueda binaria sobre el semieje mayor)."""
    destino = destino or grilla_dominio()
    T = destino.transform
    U = 0.4 * u10_ms * 2.23694                     # media llama (mph)
    LB = min(0.936 * math.exp(0.2566 * U) + 0.461 * math.exp(-0.1548 * U) - 0.397, 8.0)
    LB = max(LB, 1.0)
    rumbo = math.radians((viento_desde_deg + 180.0) % 360.0)   # hacia donde va
    ux, uy = math.sin(rumbo), math.cos(rumbo)
    rows, cols = np.indices(destino.shape)
    X = T.c + (cols + 0.5) * T.a; Y = T.f + (rows + 0.5) * T.e
    dx, dy = X - ign_xy[0], Y - ign_xy[1]
    objetivo = area_ha / HA_CELDA

    def mascara(a):
        b = a / LB; c = math.sqrt(max(a * a - b * b, 0.0))
        lx = dx * ux + dy * uy - c; ly = -dx * uy + dy * ux
        return ((lx / a) ** 2 + (ly / b) ** 2 <= 1.0) & region
    lo, hi = 15.0, 200000.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if mascara(mid).sum() < objetivo:
            lo = mid
        else:
            hi = mid
    return mascara(hi), dict(LB=LB, semieje_mayor_m=hi, rumbo_hacia_deg=math.degrees(rumbo) % 360)


def evaluar(toa_min: np.ndarray, t0_utc, obs: np.ndarray, instantes: dict, region: np.ndarray | None = None,
            dominio: np.ndarray | None = None, focos: pd.DataFrame | None = None, t_ref_dt=None,
            destino: Grilla | None = None, case_id="", run="") -> tuple[dict, list[dict]]:
    """Métricas §7. `instantes`: {nombre: Timestamp UTC}. `t_ref_dt`: T100/contención para Δt.
    `focos`: DataFrame con x, y (EPSG:5345) y t (UTC)."""
    destino = destino or grilla_dominio()
    T = destino.transform
    dominio = np.ones(destino.shape, bool) if dominio is None else dominio
    region = dominio if region is None else region
    t0 = pd.Timestamp(t0_utc)
    obs_r = obs & region
    res = {"evaluador": VERSION, "protocolo": PROTOCOLO, "t0_utc": str(t0), "instantes": {}, "ha_obs": float(obs_r.sum() * HA_CELDA)}
    filas = []

    def add(m, v, h=""):
        filas.append(dict(case_id=case_id, run=run, metrica=m, hora=h, valor=v))
    for nombre, t in instantes.items():
        mins = (pd.Timestamp(t) - t0).total_seconds() / 60.0
        sim = np.isfinite(toa_min) & (toa_min <= mins) & region
        m = comparar(sim, obs_r)
        m["minutos_desde_t0"] = mins
        m["truncado"] = toca_borde(np.isfinite(toa_min) & (toa_min <= mins), dominio)
        res["instantes"][nombre] = m
        for k, v in m.items():
            add(f"{k}@{nombre}", float(v) if isinstance(v, (int, float, np.floating, bool)) else v)
    tc, sim_eq = igual_superficie(toa_min, obs_r, region)
    eq = comparar(sim_eq, obs_r) if tc is not None else {}
    eq["minutos_corte"] = tc
    eq["t_corte_utc"] = str(t0 + pd.Timedelta(minutes=tc)) if tc is not None else None
    if tc is not None:
        c_s, c_o = centroide(sim_eq, T), centroide(obs_r, T)
        eq["desplazamiento_centroide_m"] = float(math.hypot(c_s[0] - c_o[0], c_s[1] - c_o[1]))
        eq["rumbo_obs_a_sim_deg"] = float(math.degrees(math.atan2(c_s[0] - c_o[0], c_s[1] - c_o[1])) % 360)
    if t_ref_dt is not None:
        eq["dt_h"] = ((t0 + pd.Timedelta(minutes=tc)) - pd.Timestamp(t_ref_dt)).total_seconds() / 3600 if tc is not None else math.inf
        eq["dt_censurado"] = tc is None
    res["igual_superficie"] = eq
    for k, v in eq.items():
        if isinstance(v, (int, float, np.floating, bool)) or v is None:
            add(f"{k}@igual_superficie", None if v is None else float(v))
    if focos is not None and len(focos):
        cols = ((focos.x.values - T.c) / T.a).astype(int); rows = ((focos.y.values - T.f) / T.e).astype(int)
        ok = (rows >= 0) & (rows < destino.shape[0]) & (cols >= 0) & (cols < destino.shape[1])
        f = focos[ok].copy(); f["toa_sim_min"] = toa_min[rows[ok], cols[ok]]
        f["toa_obs_min"] = (pd.to_datetime(f.t, utc=True) - t0).dt.total_seconds() / 60.0
        d = (f.toa_sim_min - f.toa_obs_min).dropna()
        res["focos"] = dict(n=int(len(f)), alcanzados=int(f.toa_sim_min.notna().sum()),
                            dif_mediana_h=float(d.median() / 60) if len(d) else None,
                            frac_a_12h=float((d.abs() <= 720).sum() / len(f)) if len(f) else None)
        if "T80" in instantes:
            from scipy import ndimage
            mins = (pd.Timestamp(instantes["T80"]) - t0).total_seconds() / 60.0
            sim = np.isfinite(toa_min) & (toa_min <= mins) & region
            fm = np.zeros(destino.shape, bool)
            sel = f[f.toa_obs_min <= mins]
            fm[((sel.y.values - T.f) / T.e).astype(int), ((sel.x.values - T.c) / T.a).astype(int)] = True
            dist = ndimage.distance_transform_edt(~fm) * T.a if fm.any() else np.full(destino.shape, np.inf)
            res["focos"]["precision_750m@T80"] = float((sim & (dist <= 750)).sum() / sim.sum()) if sim.sum() else None
        for k, v in res["focos"].items():
            add(f"focos_{k}", v)
    return res, filas


def guardar(res: dict, filas: list[dict], out: Path, entradas: dict | None = None):
    out.mkdir(parents=True, exist_ok=True)
    res = dict(res); res["entradas_sha256"] = {k: sha256(v) for k, v in (entradas or {}).items()}
    (out / "metricas.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    pd.DataFrame(filas, columns=["case_id", "run", "metrica", "hora", "valor"]).to_csv(out / "metricas_largo.csv", index=False)
