"""Resultados de la Fase 1 (protocolo v1.2 §7 y §9; apertura D33).

Para cada evento de prueba: B1 (elipse escalada con el viento medio IFS de M2 entre t0 y T80, §2.1), y para cada
motor del registro: IoU a igual superficie, Skill_F contra B1, L y Δt contra T80, truncamiento. Los eventos con
instante degenerado entran solo al eje de forma (§5). Un fallo de preparación cuenta como resultado (§3.3).

Agregación por motor: mediana y IC 90 % por bootstrap de eventos (10.000 remuestreos, semilla 20261015);
diferencias pareadas M1 − M2. Con n < 8 el IC no es concluyente (§7).

v4.0: el registro guarda la carpeta de la corrida relativa al banco (`registro.leer` la resuelve). `--modelo` elige las
corridas de SIM por modelo de parámetros: `V.4` (por defecto) = las corridas M1 de V.4 con las que se abrió la Fase 1
(reproduce resultados_fase1.json); `sim_v4_original`, `modelo_v3`, … = corridas hechas con el adaptador de v4.0, cuyos
resultados van a `fase1_<modelo>/` para no pisar los de la apertura.

Uso (desde src/v4.0):
    python -I app/banco/fase1.py [--modelo V.4|sim_v4_original|modelo_v3]
Salidas en resultados/v4.0/banco/fase1[_<modelo>]/: por_evento.csv, b1/<id>.json + .tif, resultados_fase1.json
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "evaluador"))
sys.path.insert(0, str(AQUI.parent))
sys.path.insert(0, str(AQUI))
from rutas import Rutas  # noqa: E402
import evaluador as ev  # noqa: E402
import registro  # noqa: E402

SEMILLA = 20261015
MOTORES = ("SIM",)          # V.4: solo SIM/ (cambio de planes del usuario, 2026-10-22)
N_BOOT = 10000


def viento_medio(RT, ide: str, t0, t80):
    """Vector medio ponderado por velocidad (IFS de M2, serie del dominio); si no existe, ERA5 del caso (se marca)."""
    c = sorted(glob.glob(str(RT.meteo_ifs / f"{ide}_*_dominio.csv")))
    if c:
        m = pd.read_csv(c[-1], parse_dates=["time_utc"]); fuente = "IFS (M2, serie del dominio)"
        m["time_utc"] = pd.to_datetime(m.time_utc, utc=True)
        spd, d = m.wind_speed_10m_vectorial, m.wind_direction_10m
    else:
        m = pd.read_csv(RT.banco / "casos" / ide / "meteo_horaria.csv"); fuente = "ERA5 del caso (IFS no disponible)"
        m["time_utc"] = pd.to_datetime(m.fecha_hora_utc, utc=True)
        spd, d = m.viento_vel_10m_ms, m.viento_dir_10m_grados
    sel = (m.time_utc >= t0.floor("h")) & (m.time_utc <= t80)
    if not sel.any():
        sel = (m.time_utc >= t0.floor("h")) & (m.time_utc <= t0.floor("h") + pd.Timedelta(hours=1))
    s = spd[sel].values; r = np.radians(d[sel].values)
    u = -(s * s * np.sin(r)).sum() / s.sum(); v = -(s * s * np.cos(r)).sum() / s.sum()
    return float((np.degrees(np.arctan2(-u, -v)) + 360) % 360), float(np.mean(s)), fuente


def bootstrap_mediana(x: np.ndarray, rng) -> tuple[float, float, float]:
    x = np.asarray(x, float)
    if len(x) == 0:
        return (math.nan, math.nan, math.nan)
    idx = rng.integers(0, len(x), size=(N_BOOT, len(x)))
    med = np.median(x[idx], axis=1)
    return float(np.median(x)), float(np.percentile(med, 5)), float(np.percentile(med, 95))


def main(argv=None):
    import geopandas as gpd
    import rasterio
    ap = argparse.ArgumentParser()
    ap.add_argument("--raiz", default=None, help="carpeta src/v4.0 (por defecto, la de este código)")
    ap.add_argument("--modelo", default=registro.MODELO_V4, help="modelo de las corridas de SIM (V.4 = corridas de la apertura)")
    a = ap.parse_args(argv)
    RT = Rutas(a.raiz); R = RT.raiz; B = RT.banco
    OUT = B / ("fase1" if a.modelo == registro.MODELO_V4 else f"fase1_{a.modelo}"); (OUT / "b1").mkdir(parents=True, exist_ok=True)
    G = ev.grilla_dominio()
    with rasterio.open(RT.mascara_dominio) as s:
        dominio = s.read(1) == 1
    idx = pd.read_csv(B / "casos/indice_casos.csv")
    prueba = idx[idx.rol == "prueba_fase1"].case_id.tolist()
    reg = registro.leer(RT)
    reg = reg[reg.modelo == a.modelo]
    filas = []
    for ide in prueba:
        caso = json.loads((B / "casos" / ide / "caso.json").read_text(encoding="utf-8"))
        t0 = pd.Timestamp(caso["t0_utc"]); t80 = pd.Timestamp(caso["protocolo"]["T80_utc"])
        degen = bool(caso["protocolo"]["instante_degenerado"])
        with rasterio.open(B / "casos" / ide / "obs_perimetro_final_30m.tif") as s:
            obs = s.read(1) == 1
        ign = gpd.read_file(B / "casos" / ide / "ignicion.geojson").to_crs("EPSG:5345")
        cx, cy = float(ign.geometry.x.mean()), float(ign.geometry.y.mean())
        ddesde, u10, fuente = viento_medio(RT, ide, t0, t80)
        b1, info = ev.elipse_b1((cx, cy), ddesde, u10, float(obs.sum() * ev.HA_CELDA), dominio, G)
        iou_b1 = ev.comparar(b1, obs)["iou"]
        perf = dict(driver="GTiff", height=G.shape[0], width=G.shape[1], count=1, dtype="uint8", crs=G.crs, transform=G.transform, nodata=0, compress="deflate")
        with rasterio.open(OUT / "b1" / f"{ide}.tif", "w", **perf) as d_:
            d_.write(b1.astype("uint8"), 1)
        (OUT / "b1" / f"{ide}.json").write_text(json.dumps({"iou_eq": iou_b1, "viento_desde_deg": ddesde, "u10_ms": u10, "fuente_viento": fuente, **info},
                                                           indent=1, ensure_ascii=False), encoding="utf-8")
        filas.append(dict(id_evento=ide, motor="B1", estado="ok", iou_eq=iou_b1, skill_F=0.0, L_T80=np.nan, dt_h_T80=np.nan, truncado_T80=None,
                          degenerado=degen, ha_obs=float(obs.sum() * ev.HA_CELDA), fuente_viento_B1=fuente))
        for motor in MOTORES:
            r = reg[(reg.id_evento == ide) & (reg.motor == motor) & (reg.rol == "prueba_fase1")]
            if r.empty:
                filas.append(dict(id_evento=ide, motor=motor, estado="sin_corrida", degenerado=degen)); continue
            r = r.iloc[-1]
            if r.estado != "ok":
                filas.append(dict(id_evento=ide, motor=motor, estado=r.estado, degenerado=degen)); continue
            sk = (r.iou_eq - iou_b1) / (1 - iou_b1) if pd.notna(r.iou_eq) else np.nan
            # corrección E023: si el modelo nunca alcanza A_obs, el IoU a igual superficie no está definido (el protocolo no
            # dice qué hacer). Principal: se excluye y se cuenta como "no alcanza". Sensibilidad: IoU de la huella final.
            iou_fin = np.nan
            if pd.isna(r.iou_eq):
                with rasterio.open(Path(r.carpeta_abs) / "toa_min.tif") as s_:
                    iou_fin = ev.comparar(np.isfinite(s_.read(1)) & dominio, obs)["iou"]
            sk_alt = sk if pd.notna(sk) else (iou_fin - iou_b1) / (1 - iou_b1)
            filas.append(dict(id_evento=ide, motor=motor, estado="ok", iou_eq=r.iou_eq, skill_F=sk, L_T80=r.L_T80, dt_h_T80=r.dt_h_T80,
                              truncado_T80=r.truncado_T80, degenerado=degen, ha_obs=r.ha_obs, ha_sim_T80=r.ha_sim_T80, run_id=r.run_id,
                              no_alcanza_A_obs=bool(pd.isna(r.iou_eq)), iou_huella_final=iou_fin, skill_F_sensibilidad=sk_alt))
    df = pd.DataFrame(filas)
    df.to_csv(OUT / "por_evento.csv", index=False, lineterminator="\n")
    rng = np.random.default_rng(SEMILLA)
    resumen = {"protocolo": "v1.2", "apertura": "D33", "modelo": a.modelo, "n_eventos_prueba": len(prueba), "motores": {}}
    for motor in MOTORES:
        d = df[df.motor == motor]
        ok = d[d.estado == "ok"]
        e = ok[~ok.degenerado.astype(bool)]
        skv = ok.skill_F.dropna().values
        sk = bootstrap_mediana(skv, rng)
        sk_sens = bootstrap_mediana(ok.skill_F_sensibilidad.dropna().values, rng) if "skill_F_sensibilidad" in ok else (math.nan,) * 3
        absL = bootstrap_mediana(np.abs(e.L_T80.dropna().values), rng)
        dt = e.dt_h_T80.replace([np.inf, -np.inf], np.nan)
        absdt = bootstrap_mediana(np.abs(dt.dropna().values), rng)
        frac_L4 = float((np.abs(e.L_T80) > math.log(4)).mean()) if len(e) else math.nan
        forma_ok = bool(sk[0] > 0 and sk[1] > 0)
        ext_ok = bool(absL[0] <= math.log(2) and absdt[0] <= 24 and frac_L4 <= 1 / 3)
        resumen["motores"][motor] = {
            "n_forma": int(len(skv)), "n_extension": int(len(e)),
            "no_alcanza_A_obs": ok[ok.get("no_alcanza_A_obs", False) == True].id_evento.tolist() if "no_alcanza_A_obs" in ok else [],
            "dt_censurado_por_defecto": int(np.isinf(e.dt_h_T80).sum()),
            "fallos": d[d.estado != "ok"][["id_evento", "estado"]].to_dict("records"),
            "skill_F_mediana_IC90": sk, "skill_F_sensibilidad_huella_final_IC90": sk_sens,
            "abs_L_mediana_IC90": absL, "abs_dt_h_mediana_IC90": absdt, "frac_abs_L_mayor_ln4": frac_L4,
            "sesgo_L_mediana": float(e.L_T80.median()) if len(e) else math.nan,
            "eje_forma_cumple": forma_ok, "eje_extension_cumple": ext_ok, "aceptable_s9": forma_ok and ext_ok,
            "concluyente_forma": bool(len(skv) >= 8), "concluyente_extension": bool(len(e) >= 8)}
    m = df.pivot_table(index="id_evento", columns="motor", values="skill_F")
    if {"SIM", "MOD"} <= set(m.columns):
        dif = (m["SIM"] - m["MOD"]).dropna().values
        resumen["pareado_skill_F_SIM_menos_MOD"] = bootstrap_mediana(dif, rng) + (int(len(dif)),)
    ml = df[~df.degenerado.astype(bool)].pivot_table(index="id_evento", columns="motor", values="L_T80")
    if {"SIM", "MOD"} <= set(ml.columns):
        dl = (ml["SIM"].abs() - ml["MOD"].abs()).dropna().values
        resumen["pareado_absL_SIM_menos_MOD"] = bootstrap_mediana(dl, rng) + (int(len(dl)),)
    resumen["b1_viento"] = df[df.motor == "B1"][["id_evento", "fuente_viento_B1"]].to_dict("records")
    resumen["script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (OUT / "resultados_fase1.json").write_text(json.dumps(resumen, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(df[["id_evento", "motor", "estado", "iou_eq", "skill_F", "L_T80", "dt_h_T80", "truncado_T80", "degenerado"]].to_string(index=False))
    print(json.dumps(resumen["motores"], indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
