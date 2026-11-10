"""Fase 2 del protocolo de evaluación (v1.3 §3.4 y §9): recalibración con validación cruzada N−1.

Candidato **M1-C**: SIM v4.0 (`modelo_v3`, física corregida y barreras) + contención por combate de v3.0 en modo
**pronóstico** (sin la ficha del SNMF: arribo vial desde el cuartel más cercano con el producto de v3.0, despacho SNMF
por región, medios aéreos sorteados) + parada SNMF de §4.3. Tres parámetros libres, el máximo que admite §9 con 10
eventos:
- `regla` del combustible pre-evento: 3.3 (V.4) | 3.3b (NDVI estructural de las leñosas sin la anomalía del verano);
- `I_s`, umbral de sostén de la línea (kW/m; el aéreo es max(3500, I_s));
- `kappa`, multiplicador de la tasa de despacho SNMF.
Además se corren las dos líneas de base sin contención (`M1v3`, una por regla), que no suman parámetros.

Eventos: los 10 elegibles del conjunto local (8 ex-prueba de la Fase 1 + 2024 + SM01); Renca y Puertas no cumplen §3.2.
Insumos por evento y regla en datos/procesados/v4.0/banco_fase2/<id>/<regla>/; corridas en resultados/v4.0/banco/fase2/.
Función objetivo (§9): (1 − IoU_eq) + 0,5·|L| + 0,5·min(|Δt|/24 h, 3); Δt censurado = 3; los eventos con instante
degenerado aportan solo la forma; si el modelo no alcanza A_obs, IoU de la huella final. Validación cruzada: la
configuración que minimiza la media sin el evento i se evalúa en i; solo esas evaluaciones son el resultado.

    python -I app/banco/fase2.py preparar
    python -I app/banco/fase2.py correr [--procesos 6] [--eventos id1,id2] [--configs c1,c2]
    python -I app/banco/fase2.py analizar
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
APP = AQUI.parent
RAIZ = APP.parent                                   # src/v4.0
for _p in (RAIZ / "scripts", RAIZ / "src", APP / "evaluador", APP, APP / "motores", AQUI):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
from rutas import Rutas  # noqa: E402

SEMILLA = 20261015
DOMINIO = "las_lagunas_potrerillos"
MODELO = "modelo_v3"
REGLAS = ("3.3", "3.3b")
GRILLA_IS = (800.0, 1700.0, 3500.0)
GRILLA_KAPPA = (1.0, 3.0, 10.0)
LN2, LN4 = math.log(2.0), math.log(4.0)
TOPE_DT = 3.0
SALIDAS = {"png": False, "gif": False, "geotiff": True, "geojson": False, "json": True, "descripcion": False}
CONSERVAR = ("hora_llegada_min.tif", "t_contencion_min.tif", "metadata.json", "serie_indicadores.csv", "log.txt")


def dir_fase2(RT) -> Path:
    d = RT.banco / "fase2"; d.mkdir(parents=True, exist_ok=True)
    return d


def dir_insumos(RT, ide: str, regla: str) -> Path:
    return RT.repo / "datos" / "procesados" / "v4.0" / "banco_fase2" / ide / regla.replace(".", "")


def eventos(RT) -> pd.DataFrame:
    """Los 10 elegibles (§3.4), en el orden de la semilla del protocolo."""
    ev = pd.read_csv(RT.protocolo / "eventos_fase1.csv")
    ev = ev[ev.rol.isin(["prueba_fase1", "desarrollo"])].copy()
    ev["orden"] = [hashlib.sha256(f"{SEMILLA}:{i}".encode()).hexdigest() for i in ev.id_evento]
    return ev.sort_values("orden").reset_index(drop=True)


def configuraciones() -> list[dict]:
    out = [{"id": f"r{r.replace('.', '')}_libre", "regla": r, "I_s": None, "kappa": None} for r in REGLAS]
    out += [{"id": f"r{r.replace('.', '')}_I{i:g}_k{k:g}", "regla": r, "I_s": i, "kappa": k}
            for r in REGLAS for i in GRILLA_IS for k in GRILLA_KAPPA]
    return out


# ------------------------------------------------------------------------------------------------ preparar
def preparar_evento(RT, fila: pd.Series, regla: str) -> dict:
    import geopandas as gpd
    import sim_adaptador as AD
    from incendios_sl import arribo
    ide = fila.id_evento
    out = dir_insumos(RT, ide, regla); out.mkdir(parents=True, exist_ok=True)
    previo = RT.insumos_banco / ide
    if (previo / "meteo_horaria.csv").exists() and not (out / "meteo_horaria.csv").exists():
        shutil.copy2(previo / "meteo_horaria.csv", out / "meteo_horaria.csv")       # serie ya descargada (E026)
    respaldo = previo / "indices_mes.tif"
    if not respaldo.exists():
        anio, mes = int(fila.anio), int(str(fila.meses).split("-")[0])
        respaldo = RT.ndvi_ndmi(anio, mes)                                            # mes del evento, declarado
    fo = pd.read_csv(RT.protocolo / "focos_atribuidos.csv")
    fo = fo[fo.id_evento == ide]
    cfg, proc = AD.preparar(RT, fila, fo, "previo", 48.0, descargar=False, l03=None, modelo=AD.cargar_modelo(RT, MODELO),
                            regla_combustible=regla, out=out, parada_snmf=True, indices_respaldo=respaldo)
    ctx = {"id_evento": ide, "regla": regla, "proc": proc, "cfg": cfg}
    if not proc["fallos"]:
        ign = gpd.read_file(out / "ignicion.geojson").to_crs(4326)
        pts = [(float(p.x), float(p.y)) for p in ign.geometry]
        vial = arribo.inicio_combate_vial(DOMINIO, pts)
        dep = arribo.departamento_de(float(np.mean([p[0] for p in pts])), float(np.mean([p[1] for p in pts])))
        reg = arribo.region_despacho(dep)
        ctx["contencion"] = {"inicio_min": round(vial["retardo_h"] * 60.0, 2) if vial else None, "arribo": vial,
                             "departamento": dep, "region": reg,
                             "a": arribo.REGIONES_SNMF[reg]["a"], "b": arribo.REGIONES_SNMF[reg]["b"]}
    (out / "fase2_contexto.json").write_text(json.dumps(ctx, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return {"id_evento": ide, "regla": regla, "fallos": proc["fallos"], "duracion_h": proc.get("duracion_h"),
            "inicio_min": (ctx.get("contencion") or {}).get("inicio_min"), "region": (ctx.get("contencion") or {}).get("region")}


# ------------------------------------------------------------------------------------------------ correr
def cfg_corrida(ctx: dict, conf: dict) -> dict:
    from simulador.config import fusionar
    cfg = fusionar(ctx["cfg"], {"salidas": SALIDAS, "nombre": f"fase2_{ctx['id_evento']}_{conf['id']}"})
    if conf["I_s"] is not None:
        c = ctx["contencion"]
        cfg = fusionar(cfg, {"parametros": {"contencion": {
            "activo": True, "despacho": "snmf", "inicio_min": c["inicio_min"],
            "snmf": {"a": c["a"], "b": c["b"], "kappa": float(conf["kappa"])},
            "intensidad_sostener_kw_m": float(conf["I_s"]), "intensidad_sostener_aereo_kw_m": max(3500.0, float(conf["I_s"])),
            "aereo_intervalos": [], "aereo_auto": {"activo": True}}}})
    return cfg


def correr_uno(raiz: str | None, ide: str, conf: dict) -> dict:
    """Una corrida (proceso aparte): simula, escribe toa_min.tif, evalúa y limpia los productos pesados."""
    import rasterio
    import sim_adaptador as AD
    from simulador.corrida import ejecutar
    RT = Rutas(raiz)
    fila = eventos(RT).set_index("id_evento").loc[ide]; fila["id_evento"] = ide
    destino = dir_fase2(RT) / "corridas" / f"{ide}__{conf['id']}"
    if (destino / "registro.json").exists():
        return json.loads((destino / "registro.json").read_text(encoding="utf-8"))["fila"]
    ctx = json.loads((dir_insumos(RT, ide, conf["regla"]) / "fase2_contexto.json").read_text(encoding="utf-8"))
    import sim_adaptador as _AD
    vigente = (_AD.cargar_modelo(RT, MODELO)[2].get("parametros") or {}).get("viento") or {}
    preparado = (ctx["cfg"].get("parametros") or {}).get("viento") or {}
    if any(preparado.get(k) != v for k, v in vigente.items()):
        # el contexto guarda el modelo del momento de preparar: si cambió (p. ej. viento serie → windninja) no se mezclan
        raise RuntimeError(f"{ide}: el contexto de la Fase 2 se preparó con otro viento ({preparado}) que el de {MODELO} "
                           f"({vigente}); correr primero `fase2.py preparar`")
    base = {"id_evento": ide, "config": conf["id"], "regla": conf["regla"], "I_s": conf["I_s"], "kappa": conf["kappa"]}
    if ctx["proc"]["fallos"]:
        return {**base, "estado": "fallo_preparacion"}
    if destino.exists():
        shutil.rmtree(destino)
    (destino / "sim").mkdir(parents=True)
    cfg = cfg_corrida(ctx, conf)
    t_ = time.time()
    res = ejecutar(cfg, RT.sim_datos, destino / "sim", verificar_sha=False, verbose=False)
    seg = round(time.time() - t_, 1)
    with rasterio.open(destino / "sim" / "hora_llegada_min.tif") as s:
        toa = s.read(1).astype("float32"); prof = s.profile
    prof.update(dtype="float32", nodata=np.nan, compress="deflate")
    with rasterio.open(destino / "toa_min.tif", "w", **prof) as d:
        d.write(toa, 1); d.update_tags(t0_utc=ctx["proc"]["t0_utc"], unidades="minutos desde t0", motor="SIM-C", config=conf["id"])
    fo = pd.read_csv(RT.protocolo / "focos_atribuidos.csv"); fo = fo[fo.id_evento == ide]
    resm, degen = AD.evaluar_corrida(RT, fila, fo, destino, f"{ide}__{conf['id']}", ctx["proc"]["t0_utc"])
    m, eq = resm["instantes"]["T80"], resm["igual_superficie"]
    iou_fin = None
    if eq.get("iou") is None or not np.isfinite(eq.get("iou") or np.nan):
        iou_fin = float(m.get("iou_huella_final", np.nan)) if "iou_huella_final" in m else _iou_huella_final(RT, fila, destino)
    meta = res["metadata"]
    filam = {**base, "estado": "ok", "degenerado": bool(degen), "ha_obs": resm["ha_obs"], "ha_sim_T80": m["ha_sim"], "L_T80": m["L"],
             "iou_T80": m["iou"], "iou_eq": eq.get("iou"), "dt_h": eq.get("dt_h"), "dt_censurado": bool(eq.get("dt_censurado", eq.get("iou") is None)),
             "truncado": m["truncado"], "iou_huella_final": iou_fin, "segundos": seg, "motivo_fin": meta.get("motivo_fin"),
             "ha_final": meta.get("superficie_final_ha"), "linea_km": ((meta.get("contencion") or {}).get("linea_km")),
             "celdas_contenidas": ((meta.get("contencion") or {}).get("celdas_contenidas")),
             "escapes": ((meta.get("contencion") or {}).get("escapes"))}
    for f in (destino / "sim").iterdir():                     # se conservan ToA, contención, serie, metadatos y log
        if f.name not in CONSERVAR:
            f.unlink()
    (destino / "registro.json").write_text(json.dumps({"fila": filam, "config": conf, "proc": ctx["proc"], "contexto_contencion": ctx.get("contencion"),
                                                       "modelo": MODELO}, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return filam


def _iou_huella_final(RT, fila, destino: Path) -> float:
    """IoU de la huella final contra la referencia (§7, modelo que no alcanza A_obs)."""
    import rasterio
    import evaluador as ev
    r = json.loads((destino / "metricas.json").read_text(encoding="utf-8"))
    if "iou_huella_final" in r:
        return float(r["iou_huella_final"])
    with rasterio.open(RT.mascara_dominio) as s:
        dominio = s.read(1) == 1
    with rasterio.open(destino / "toa_min.tif") as s:
        huella = np.isfinite(s.read(1)) & dominio
    with rasterio.open(RT.banco / "casos" / fila.id_evento / "obs_perimetro_final_30m.tif") as s:
        obs = s.read(1) == 1
    return float(ev.comparar(huella, obs)["iou"])


# ------------------------------------------------------------------------------------------------ analizar
def objetivo(r: pd.Series) -> float:
    """Función objetivo de §9 para una corrida."""
    iou = r.iou_eq if pd.notna(r.iou_eq) else r.iou_huella_final
    j = 1.0 - float(iou if pd.notna(iou) else 0.0)
    if r.degenerado:
        return j
    dt = TOPE_DT if (pd.isna(r.dt_h) or r.dt_censurado) else min(abs(float(r.dt_h)) / 24.0, TOPE_DT)
    return j + 0.5 * abs(float(r.L_T80)) + 0.5 * dt


def iou_b1(RT, ide: str) -> float:
    """IoU a igual superficie de la elipse B1 (de la Fase 1, o calculada igual para los eventos que no estaban)."""
    p = RT.banco / "fase1" / "b1" / f"{ide}.json"
    if p.exists():
        return float(json.loads(p.read_text(encoding="utf-8"))["iou_eq"])
    import geopandas as gpd
    import rasterio
    import evaluador as ev
    from fase1 import viento_medio
    G = ev.grilla_dominio()
    with rasterio.open(RT.mascara_dominio) as s:
        dominio = s.read(1) == 1
    caso = json.loads((RT.banco / "casos" / ide / "caso.json").read_text(encoding="utf-8"))
    t0 = pd.Timestamp(caso["t0_utc"]); t80 = pd.Timestamp(caso["protocolo"]["T80_utc"])
    with rasterio.open(RT.banco / "casos" / ide / "obs_perimetro_final_30m.tif") as s:
        obs = s.read(1) == 1
    ign = gpd.read_file(RT.banco / "casos" / ide / "ignicion.geojson").to_crs("EPSG:5345")
    ddesde, u10, fuente = viento_medio(RT, ide, t0, t80)
    b1, info = ev.elipse_b1((float(ign.geometry.x.mean()), float(ign.geometry.y.mean())), ddesde, u10, float(obs.sum() * ev.HA_CELDA), dominio, G)
    v = float(ev.comparar(b1, obs)["iou"])
    d = dir_fase2(RT) / "b1"; d.mkdir(exist_ok=True)
    (d / f"{ide}.json").write_text(json.dumps({"iou_eq": v, "viento_desde_deg": ddesde, "u10_ms": u10, "fuente_viento": fuente, **info},
                                              indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return v


def agregar(df: pd.DataFrame, rng) -> dict:
    """Agregados y criterios de §9 sobre una fila por evento (columnas iou_eq/iou_huella_final, skill_F, L_T80, dt_h…)."""
    from fase1 import bootstrap_mediana
    sk = df.skill_F.dropna().values
    e = df[~df.degenerado]
    absL = np.abs(e.L_T80.astype(float).values)
    absdt = np.where(e.dt_censurado | e.dt_h.isna(), np.inf, np.abs(e.dt_h.astype(float).fillna(np.inf)))
    skm = bootstrap_mediana(sk, rng)
    Lm = bootstrap_mediana(absL, rng)
    dtm = float(np.median(absdt)) if len(absdt) else math.nan
    frac4 = float(np.mean(absL > LN4)) if len(absL) else math.nan
    return {"n": int(len(df)), "n_extension": int(len(e)), "skill_F_mediana_IC90": skm, "absL_mediana_IC90": Lm,
            "absdt_mediana_h": dtm, "frac_absL_gt_ln4": frac4, "sesgo_L_mediana": float(np.median(e.L_T80.astype(float))) if len(e) else math.nan,
            "objetivo_medio": float(df.J.mean()),
            "acepta_forma": bool(skm[0] > 0 and skm[1] > 0),
            "acepta_extension": bool(Lm[0] <= LN2 and dtm <= 24.0 and frac4 <= 1 / 3),
            "no_alcanza": int(df.iou_eq.isna().sum())}


def analizar(RT) -> dict:
    F = dir_fase2(RT)
    filas = [json.loads(p.read_text(encoding="utf-8"))["fila"] for p in sorted((F / "corridas").glob("*/registro.json"))]
    df = pd.DataFrame(filas)
    df = df[df.estado == "ok"].copy()
    df["J"] = df.apply(objetivo, axis=1)
    b1 = {i: iou_b1(RT, i) for i in df.id_evento.unique()}
    df["iou_b1"] = df.id_evento.map(b1)
    iou = df.iou_eq.where(df.iou_eq.notna(), df.iou_huella_final).astype(float)
    df["skill_F"] = (iou - df.iou_b1) / (1 - df.iou_b1)
    df.sort_values(["config", "id_evento"]).to_csv(F / "corridas_fase2.csv", index=False, lineterminator="\n")
    evs = sorted(df.id_evento.unique())
    confs = [c for c in df.config.unique() if (df.config == c).sum() == len(evs)]   # configuraciones completas
    tabla = df.pivot_table(index="id_evento", columns="config", values="J")[confs]
    # bitácora de configuraciones (§9: cada configuración probada se registra)
    bit = df.groupby("config").agg(regla=("regla", "first"), I_s=("I_s", "first"), kappa=("kappa", "first"), n=("J", "size"),
                                   objetivo_medio=("J", "mean"), segundos=("segundos", "sum")).reset_index()
    bit.to_csv(F / "bitacora_configuraciones.csv", index=False, lineterminator="\n")
    # validación cruzada N−1 (solo los candidatos con contención; las bases sin contención se informan aparte)
    cand = [c for c in confs if not c.endswith("_libre")]
    cv = []
    for i in evs:
        resto = tabla.drop(index=i)[cand].mean()
        mejor = resto.idxmin()
        r = df[(df.id_evento == i) & (df.config == mejor)].iloc[0].to_dict()
        r.update({"config_elegida": mejor, "J_entrenamiento": float(resto.min())})
        cv.append(r)
    cv = pd.DataFrame(cv)
    cv.to_csv(F / "validacion_cruzada_por_evento.csv", index=False, lineterminator="\n")
    rng = np.random.default_rng(SEMILLA)
    final = tabla[cand].mean().idxmin()
    res = {"protocolo": "v1.3 §3.4 y §9 (Fase 2, validación cruzada N−1; no es validación independiente)",
           "modelo_base": MODELO, "eventos": evs, "parametros_libres": ["regla_combustible", "I_s", "kappa"],
           "configuraciones_probadas": int(len(confs)), "corridas": int(len(df)),
           "validacion_cruzada": agregar(cv, rng),
           "config_elegida_por_pliegue": cv.set_index("id_evento").config_elegida.to_dict(),
           "config_final_todos_los_eventos": final,
           "objetivo_medio_por_config": tabla.mean().sort_values().round(4).to_dict(),
           "bases": {}}
    for base in [c for c in confs if c.endswith("_libre")] + [final]:
        res["bases"][base] = agregar(df[df.config == base].copy(), np.random.default_rng(SEMILLA))
    (F / "resultados_fase2.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("accion", choices=["preparar", "correr", "analizar"])
    ap.add_argument("--raiz", default=None)
    ap.add_argument("--procesos", type=int, default=6)
    ap.add_argument("--eventos", default=None, help="lista separada por comas (por defecto, los 10 elegibles)")
    ap.add_argument("--configs", default=None, help="ids de configuración separados por comas (por defecto, todas)")
    a = ap.parse_args(argv)
    RT = Rutas(a.raiz)
    evs = eventos(RT)
    if a.eventos:
        evs = evs[evs.id_evento.isin(a.eventos.split(","))]
    if a.accion == "preparar":
        for _, f in evs.iterrows():
            for r in REGLAS:
                print(json.dumps(preparar_evento(RT, f, r), ensure_ascii=False, default=str), flush=True)
        return 0
    if a.accion == "correr":
        confs = configuraciones()
        if a.configs:
            confs = [c for c in confs if c["id"] in a.configs.split(",")]
        # los eventos largos primero, para repartir mejor la carga
        dur = {i: json.loads((dir_insumos(RT, i, "3.3") / "fase2_contexto.json").read_text(encoding="utf-8"))["proc"].get("duracion_h") or 0
               for i in evs.id_evento}
        tareas = sorted([(i, c) for i in evs.id_evento for c in confs], key=lambda t: -dur[t[0]])
        with ProcessPoolExecutor(max_workers=a.procesos) as pool:
            fut = {pool.submit(correr_uno, a.raiz, i, c): (i, c["id"]) for i, c in tareas}
            for k, f in enumerate(as_completed(fut), 1):
                i, c = fut[f]
                try:
                    r = f.result()
                    print(f"[{k}/{len(fut)}] {i} {c}: J-ins {r.get('estado')} iou_eq={r.get('iou_eq')} L={r.get('L_T80')} "
                          f"dt={r.get('dt_h')} ha={r.get('ha_final')} {r.get('segundos')} s", flush=True)
                except Exception as e:                                     # se registra y se sigue con el resto
                    print(f"[{k}/{len(fut)}] {i} {c}: ERROR {e!r}", flush=True)
        return 0
    res = analizar(RT)
    print(json.dumps({k: res[k] for k in ("validacion_cruzada", "config_final_todos_los_eventos", "config_elegida_por_pliegue", "bases")},
                     indent=1, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
