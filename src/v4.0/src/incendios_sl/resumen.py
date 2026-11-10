"""Registro, métricas y resumen estadístico de una corrida de v4.0 (misma forma que v3.0 `validation/resumen.py`).

- `escribir_registro`: `registro.json` con `version_codigo` 4.0.0, la configuración completa de SIM, las entradas
  (evento o caso, modelo, variante, despacho), `motivo_fin`, superficie, segundos y `fecha_corrida`. La celda 3 del
  cuaderno lo usa como marca de corrida válida.
- `metricas_evento`: IoU, Dice, omisión y comisión contra la cicatriz de referencia en cada `fin.evaluacion_utc` ≤ fin
  simulado (máscara simulada = `hora_llegada_min.tif` ≤ instante; dominio de comparación = celdas combustibles), y el
  acuerdo con los focos VIIRS (v3.0 `validation/metricas`). `metricas_caso`: `simulador.evaluacion` del caso de prueba.
- `escribir_resumen`: `resumen_<run_id>_<AAAAMMDD-HHMM>.json` y `.md` (parámetros, costo, superficie, modelo,
  mitigación, serie y validación).
"""
from __future__ import annotations

import datetime as dt
import json
import platform
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from . import __version__
from . import config as cfgmod
from . import eventos

TZ_LOCAL = "America/Argentina/San_Luis"


def _json(o):
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return None if np.isnan(o) else float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (pd.Timestamp, dt.datetime)):
        return o.isoformat()
    if isinstance(o, Path):
        return o.as_posix()
    return str(o)


def escribir_json(d: dict, ruta: Path) -> Path:
    Path(ruta).write_text(json.dumps(d, indent=2, ensure_ascii=False, default=_json), encoding="utf-8")
    return Path(ruta)


def _cargar(p: Path, defecto: Any = None) -> Any:
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return defecto


def cfg_limpio(cfg: dict) -> dict:
    """Configuración sin claves internas (`_dir`, `_ruta`) y con rutas relativas al repositorio."""
    def f(x):
        if isinstance(x, dict):
            return {k: f(v) for k, v in x.items() if not str(k).startswith("_")}
        if isinstance(x, list):
            return [f(v) for v in x]
        if isinstance(x, str) and len(x) > 3 and (x[1:3] == ":\\" or x.startswith("/")) and Path(x).exists():
            return eventos._rel(Path(x))
        return x
    return f(cfg)


def motivo_fin(res: dict) -> tuple[str, str]:
    """(motivo, texto) de fin que informa SIM (`horizonte`, `extinguido`, `sin_avance`, `contenido`; metadata o
    autómata) o, si no lo informa, el deducido de la serie."""
    meta = res.get("metadata") or {}; au = res.get("automata")
    m = res.get("motivo_fin") or meta.get("motivo_fin") or getattr(au, "motivo_fin", None)
    if m:
        return str(m), str(meta.get("motivo_fin_texto") or getattr(au, "motivo_fin_texto", "") or "")
    ind = res.get("indicadores") or []
    if ind and int(ind[-1]["frente"].get("celdas_activas", 0)) == 0:
        return "extinguido", "sin celdas activas al final (el fuego se extinguió o quedó contenido)"
    return "horizonte", "fin del tiempo simulado"


def igniciones_lonlat(meta_sim: dict) -> list[dict[str, Any]]:
    """Igniciones de metadata.json (fila, col de la grilla de la corrida) en lon/lat."""
    from pyproj import Transformer
    g = meta_sim.get("grilla") or {}
    if not g:
        return []
    tr = Transformer.from_crs(g["crs"], "EPSG:4326", always_xy=True)
    out = []
    for i in meta_sim.get("igniciones") or []:
        x = g["xmin"] + (i["col"] + 0.5) * g["res"]; y = g["ymax"] - (i["fila"] + 0.5) * g["res"]
        lon, lat = tr.transform(x, y)
        out.append({"id": i.get("id"), "lon": round(lon, 6), "lat": round(lat, 6), "t": i.get("t")})
    return out


def escribir_registro(carpeta: Path, res: dict, trad: dict, segundos: float, run_id: str, nombre: str) -> Path:
    import simulador
    meta = res.get("metadata") or {}
    au = res.get("automata")
    ind = res.get("indicadores") or []
    t0 = pd.Timestamp(res["t0"])
    t_min = float(ind[-1]["minutos_desde_t0"]) if ind else float(meta.get("duracion_h", 0)) * 60.0
    motivo, texto = motivo_fin(res)
    reg = {
        "run_id": run_id, "nombre_escenario": nombre, "descripcion": trad["cfg"].get("descripcion"),
        "version_codigo": __version__, "version_simulador": simulador.__version__, "version_resultados": cfgmod.VERSION_RESULTADOS,
        "fecha_corrida": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "maquina": platform.node(),
        "modo_entrada": trad["modo"], "motivo_fin": motivo, "motivo_fin_texto": texto,
        "duracion_pedida_h": float(trad["cfg"].get("duracion_h") or 0), "duracion_simulada_h": round(t_min / 60.0, 3),
        "t_inicio_utc": t0.tz_convert("UTC").isoformat(), "t_simulado_s": t_min * 60.0,
        "t_simulado_utc": (t0 + pd.Timedelta(minutes=t_min)).tz_convert("UTC").isoformat(),
        "segundos": round(float(segundos), 1), "sub_pasos": meta.get("sub_pasos"),
        "ha_quemadas": round(float(au.area_quemada_ha()), 2) if au is not None else meta.get("superficie_final_ha"),
        "celdas_quemadas": int(np.asarray(au.afectada).sum()) if au is not None else None,
        "toco_borde": meta.get("toco_borde"), "igniciones_lonlat": igniciones_lonlat(meta),
        "mitigacion": {k: meta.get(k) for k in ("supresion", "contencion", "barreras") if meta.get(k) is not None},
        "entradas": trad["entradas"], "config": cfg_limpio(trad["cfg"]),
    }
    return escribir_json(reg, Path(carpeta) / "registro.json")


# ---------------------------------------------------------------------------------------------------- métricas
def metricas_espaciales(sim: np.ndarray, ref: np.ndarray, valido: np.ndarray, res_m: float) -> dict[str, Any]:
    """IoU, Dice, superficies, omisión y comisión sobre el dominio de comparación `valido` (v3.0)."""
    s = sim & valido; r = ref & valido
    inter = int((s & r).sum()); uni = int((s | r).sum()); ns = int(s.sum()); nr = int(r.sum()); ha = res_m ** 2 / 1e4
    return {"celdas_sim": ns, "celdas_ref": nr, "ha_sim": ns * ha, "ha_ref": nr * ha, "diferencia_abs_ha": (ns - nr) * ha,
            "diferencia_rel": (ns - nr) / nr if nr else None, "interseccion_ha": inter * ha, "union_ha": uni * ha,
            "iou": inter / uni if uni else None, "dice": 2 * inter / (ns + nr) if (ns + nr) else None,
            "omision": 1 - inter / nr if nr else None, "comision": 1 - inter / ns if ns else None,
            "celdas_ref_fuera_de_valido": int((ref & ~valido).sum())}


def metricas_temporales(t_min: np.ndarray, transform, crs: str, focos: pd.DataFrame, t0: pd.Timestamp, tolerancia_m: float = 375.0) -> dict[str, Any]:
    """Acuerdo con los focos de calor (v3.0): un foco está capturado si alguna celda a ≤ `tolerancia_m` arde en la
    simulación; "al fin del día" si arde antes del fin del día local de la detección; desfase = llegada − detección."""
    if focos is None or not len(focos):
        return {"disponible": False}
    from pyproj import Transformer
    x, y = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(focos["lon"].to_numpy(float), focos["lat"].to_numpy(float))
    res = abs(transform.a)
    col = np.floor((np.asarray(x) - transform.c) / res).astype(int); fil = np.floor((transform.f - np.asarray(y)) / res).astype(int)
    H, W = t_min.shape
    dentro = (fil >= 0) & (fil < H) & (col >= 0) & (col < W)
    hs = focos[dentro].copy(); fil = fil[dentro]; col = col[dentro]
    if not len(hs):
        return {"disponible": False, "nota": "ningún foco dentro de la grilla de la corrida"}
    k = int(np.ceil(tolerancia_m / res))
    tsim = np.full(len(hs), np.inf)
    for i, (fi, ci) in enumerate(zip(fil, col)):
        v = t_min[max(0, fi - k):fi + k + 1, max(0, ci - k):ci + k + 1]
        v = v[np.isfinite(v)]
        if v.size:
            tsim[i] = v.min() * 60.0
    hs["t_sim_s"] = tsim
    fechas = pd.to_datetime(hs["date"]).dt.tz_localize(TZ_LOCAL)
    hs["fin_dia_s"] = ((fechas + pd.Timedelta(days=1)).dt.tz_convert("UTC") - t0).dt.total_seconds()
    hs["t_det_s"] = (pd.to_datetime(hs["hora_deteccion"], utc=True) - t0).dt.total_seconds()
    cap = np.isfinite(hs["t_sim_s"])
    out: dict[str, Any] = {"disponible": True, "n_focos": int(len(hs)), "por_dia": []}
    for d, g in hs.groupby("date"):
        c = np.isfinite(g["t_sim_s"])
        desf = (g["t_sim_s"] - g["t_det_s"])[c] / 3600
        out["por_dia"].append({"fecha": str(d), "n": int(len(g)), "fraccion_capturada_total": float(c.mean()),
                               "fraccion_capturada_al_fin_del_dia": float((c & (g["t_sim_s"] <= g["fin_dia_s"])).mean()),
                               "desfase_mediano_h": float(desf.median()) if len(desf) else None})
    d = (hs["t_sim_s"] - hs["t_det_s"])[cap] / 3600
    out |= {"fraccion_capturada_total": float(cap.mean()), "fraccion_capturada_al_fin_del_dia": float((cap & (hs["t_sim_s"] <= hs["fin_dia_s"])).mean()),
            "desfase_mediano_h": float(d.median()) if len(d) else None,
            "desfase_p10_p90_h": [float(d.quantile(0.1)), float(d.quantile(0.9))] if len(d) else None}
    return out


def _leer_en(ruta: Path, transform, shape) -> np.ndarray:
    """Banda 1 de `ruta` recortada a la ventana (transform, shape) de la corrida (misma grilla de 30 m)."""
    import rasterio
    from rasterio.windows import from_bounds
    with rasterio.open(ruta) as s:
        H, W = shape
        b = (transform.c, transform.f - H * abs(transform.e), transform.c + W * transform.a, transform.f)
        w = from_bounds(*b, transform=s.transform).round_offsets().round_lengths()
        return s.read(1, window=w, boundless=True, fill_value=0)


def metricas_evento(carpeta: Path, trad: dict, run_id: str, t_fin_utc: str | None = None) -> dict[str, Any]:
    import rasterio
    carpeta = Path(carpeta); ent = trad["entradas"]; cfg = trad["cfg"]
    with rasterio.open(carpeta / "hora_llegada_min.tif") as s:
        t_min = s.read(1).astype("float64"); tr = s.transform; crs = s.crs.to_string()
    t_min[~np.isfinite(t_min)] = np.nan
    ev = ent["evento"]
    ref = _leer_en(eventos.ruta_cicatriz(ev), tr, t_min.shape) == 1 if eventos.ruta_cicatriz(ev).exists() else np.zeros(t_min.shape, bool)
    valido = _leer_en(Path(cfg["combustible"]), tr, t_min.shape) >= 101
    t0 = pd.Timestamp(cfg["t_inicio"]).tz_convert("UTC")
    # horizonte pedido; si SIM paró antes (extinguido, contenido, sin_avance) el área quedó congelada y las evaluaciones
    # posteriores a la parada se calculan igual, marcadas con `despues_de_parada`
    t_pedido = pd.Timestamp(ent["t_fin_utc"]).tz_convert("UTC") if ent.get("t_fin_utc") else None
    t_sim = pd.Timestamp(t_fin_utc).tz_convert("UTC") if t_fin_utc else t_pedido
    t_fin = max(x for x in (t_pedido, t_sim) if x is not None)
    espacial = []
    for t in ent.get("evaluacion_utc") or []:
        te = pd.Timestamp(t).tz_convert("UTC")
        if te > t_fin + pd.Timedelta(seconds=1):
            continue
        m_eval = (te - t0).total_seconds() / 60.0
        m = metricas_espaciales(np.nan_to_num(t_min, nan=np.inf) <= m_eval, ref, valido, abs(tr.a))
        espacial.append(m | {"t_eval_utc": te.isoformat(), "horas_desde_ignicion": round(m_eval / 60.0, 2),
                             "despues_de_parada": bool(t_sim is not None and te > t_sim + pd.Timedelta(seconds=1))})
    focos = eventos.leer_focos_csv(cfgmod.dir_catalogo() / "hotspots" / f"viirs_{ev}.csv")
    P = cfg["parametros"]
    return {"run_id": run_id, "evento": ev, "hipotesis_ignicion": ent.get("hipotesis_ignicion"), "ignicion": ent.get("ignicion"),
            "modelo": ent.get("modelo_nombre"), "variante": ent.get("variante"), "propagacion": P.get("propagacion"),
            "barreras": ent.get("barreras"), "contencion": ent.get("contencion"), "supresion": ent.get("supresion"),
            "despacho": ent.get("despacho"), "t_inicio_utc": t0.isoformat(),
            "t_fin_simulado_utc": t_sim.isoformat() if t_sim is not None else None, "t_fin_pedido_utc": t_pedido.isoformat() if t_pedido is not None else None,
            "dominio_comparacion": "celdas combustibles (FBFM40 ≥ 101) de la grilla de la corrida",
            "espacial": espacial, "temporal": metricas_temporales(t_min, tr, crs, focos, t0), "fuente_focos": "VIIRS" if len(focos) else None,
            "tolerancia_focos_m": 375.0}


def metricas_caso(res: dict, trad: dict, carpeta: Path, run_id: str) -> dict[str, Any]:
    """Evaluación del caso con `simulador.evaluacion` (evaluacion.json/.md y comparacion_observado.png) + forma estándar."""
    from simulador.evaluacion.informe import evaluar_corrida, escribir_informe
    from simulador.rutas import raiz_datos
    caso = trad["caso"]; etiqueta = trad["variante_caso"] or "base"
    ev = evaluar_corrida(res, caso, Path(carpeta), etiqueta)
    escribir_json(ev, Path(carpeta) / "evaluacion.json")
    escribir_informe(caso, [ev], Path(carpeta) / "evaluacion.md", "", raiz_datos())
    obs = (ev.get("perimetros") or {}).get("observado") or {}
    fecha = None
    if res.get("perimetro_obs") is not None and "fecha" in res["perimetro_obs"].columns and len(res["perimetro_obs"]):
        fecha = str(res["perimetro_obs"]["fecha"].iloc[0])
    t_fin = res["metadata"].get("t_fin_simulado") or res["metadata"].get("t_fin")     # con parada anticipada, el fin real
    espacial = []
    if obs:
        pct = lambda x: None if x is None else x / 100.0
        espacial.append({"t_eval_utc": pd.Timestamp(t_fin).tz_convert("UTC").isoformat() if t_fin else None, "fecha_perimetro": fecha,
                         "horas_desde_ignicion": float(res["metadata"].get("duracion_simulada_h") or res["metadata"].get("duracion_h", 0)), "ha_sim": obs.get("ha_sim"), "ha_ref": obs.get("ha_obs"),
                         "iou": obs.get("jaccard"), "dice": obs.get("sorensen"), "omision": pct(obs.get("omision_pct")), "comision": pct(obs.get("comision_pct")),
                         "centroide_dist_m": obs.get("centroide_dist_m")})
    fr = ev.get("focos_resumen") or {}
    return {"run_id": run_id, "caso": trad["entradas"].get("caso"), "variante_caso": etiqueta, "modelo": trad["entradas"].get("modelo_nombre"),
            "variante": trad["entradas"].get("variante"), "espacial": espacial, "iso_area": ev.get("iso_area"),
            "perimetros": ev.get("perimetros"), "temporal": {"disponible": bool(fr.get("n")), **fr}, "evaluacion": "evaluacion.json"}


# ---------------------------------------------------------------------------------------------------- resumen
def _serie(carpeta: Path) -> dict[str, Any] | None:
    p = Path(carpeta) / "serie_indicadores.csv"
    if not p.exists():
        return None
    s = pd.read_csv(p)
    if not len(s):
        return None
    ha = s["superficie_quemada_ha"]
    inc = ha.diff().fillna(ha)
    i = int(inc.idxmax())
    en = lambda h: float(ha[s["hora"] <= h].iloc[-1]) if s["hora"].max() >= h else None     # None: la corrida no llegó a h
    r = {"horas": int(s["hora"].max()), "ha_a_24h": en(24), "ha_a_72h": en(72), "max_ha_por_hora": round(float(inc.max()), 1),
         "hora_pico": str(s["timestamp"].iloc[i]), "max_celdas_activas": int(s["frente_celdas_activas"].max()),
         "viento_10m_kmh": {"media": round(float(s["meteo_viento_kmh"].mean()), 1), "max": round(float(s["meteo_viento_kmh"].max()), 1)},
         "humedad_relativa_pct": {"media": round(float(s["meteo_hr_pct"].mean()), 1), "min": round(float(s["meteo_hr_pct"].min()), 1)},
         "temperatura_c": {"media": round(float(s["meteo_temp_c"].mean()), 1), "max": round(float(s["meteo_temp_c"].max()), 1)}}
    if "meteo_humedad_muerta_1h_pct" in s:
        r["humedad_muerta_1h_pct"] = {"media": round(float(s["meteo_humedad_muerta_1h_pct"].mean()), 1), "min": round(float(s["meteo_humedad_muerta_1h_pct"].min()), 1)}
    if "frente_intensidad_max_kw_m" in s:
        r["intensidad_max_kw_m"] = round(float(s["frente_intensidad_max_kw_m"].max()), 0)
    return r


def resumen_de_corrida(carpeta: Path) -> dict[str, Any]:
    carpeta = Path(carpeta)
    reg = _cargar(carpeta / "registro.json", {}); met = _cargar(carpeta / "metricas.json")
    ent = reg.get("entradas") or {}; cfg = reg.get("config") or {}; P = cfg.get("parametros") or {}
    meta_sim = _cargar(carpeta / "metadata.json", {})
    r: dict[str, Any] = {
        "run_id": reg.get("run_id") or carpeta.name, "nombre_escenario": reg.get("nombre_escenario"), "descripcion": reg.get("descripcion"),
        "fecha_corrida": reg.get("fecha_corrida") or dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "version_codigo": reg.get("version_codigo"), "version_simulador": reg.get("version_simulador"),
        "version_resultados": cfgmod.VERSION_RESULTADOS, "maquina": reg.get("maquina") or platform.node(),
        "modo_entrada": reg.get("modo_entrada"), "evento": ent.get("evento"), "caso": ent.get("caso"), "variante_caso": ent.get("variante_caso"),
        "dominio": ent.get("dominio"), "hipotesis_ignicion": ent.get("hipotesis_ignicion"), "ignicion": ent.get("ignicion"),
        "igniciones": reg.get("igniciones_lonlat"), "t_inicio_utc": reg.get("t_inicio_utc"), "t_fin_simulado_utc": reg.get("t_simulado_utc"),
        "horas_simuladas": round(float(reg.get("t_simulado_s") or 0) / 3600, 1), "horas_pedidas": reg.get("duracion_pedida_h"),
        "motivo_fin": reg.get("motivo_fin"), "motivo_fin_texto": reg.get("motivo_fin_texto"),
        "parametros": {"propagacion": P.get("propagacion"), "dt_min": cfg.get("dt_min"), "vecindad": cfg.get("vecindad"), "modo": cfg.get("modo"),
                       "semilla": cfg.get("semilla"), "limite_viento": P.get("limite_viento"), "extincion": P.get("extincion"),
                       "huygens": P.get("huygens"), "humedad": P.get("humedad"), "viento": P.get("viento")},
        "costo": {"segundos": reg.get("segundos"), "sub_pasos": reg.get("sub_pasos")},
        "superficie": {"ha_quemadas_final": reg.get("ha_quemadas"), "celdas_quemadas": reg.get("celdas_quemadas"), "toco_borde": reg.get("toco_borde")},
        "modelo": {"nombre": ent.get("modelo_nombre"), "variante": ent.get("variante"),
                   "humedad_muerta": (P.get("humedad") or {}).get("metodo_muerto", "retardo"),
                   "barreras": bool(ent.get("barreras")), "contencion": bool(ent.get("contencion")), "supresion_l03": bool(ent.get("supresion"))},
    }
    if ent.get("barreras") or ent.get("contencion") or ent.get("supresion") or any((ent.get("mitigacion") or {}).values()):
        Pc = P.get("contencion") or {}
        mc = meta_sim.get("contencion") or {}             # inicio real del combate según SIM (con retardo_h, inicio_min del cfg es null)
        ini = mc.get("inicio_min") if mc.get("inicio_min") is not None else Pc.get("inicio_min")
        if ini is None and ent.get("contencion") and Pc.get("retardo_h") is not None:
            ini = float(Pc["retardo_h"]) * 60.0
        r["mitigacion"] = {"despacho": ent.get("despacho"), "contencion_inicio_min": ini, "contencion_inicio_utc": mc.get("inicio_utc"),
                           "contencion_despacho": Pc.get("despacho"),
                           "tasa_linea_m_h": Pc.get("tasa_linea_m_h"), "snmf": Pc.get("snmf") if Pc.get("despacho") == "snmf" else None,
                           "supresion": (P.get("supresion") or {}) if ent.get("supresion") else None,
                           "insumos": ent.get("mitigacion"), "resultado_sim": reg.get("mitigacion") or {k: meta_sim.get(k) for k in ("supresion",) if meta_sim.get(k)}}
    s = _serie(carpeta)
    if s:
        if reg.get("motivo_fin") in ("extinguido", "contenido", "sin_avance"):     # parada anticipada: el área quedó congelada
            for h in (24, 72):
                if s[f"ha_a_{h}h"] is None and float(reg.get("duracion_pedida_h") or 0) >= h:
                    s[f"ha_a_{h}h"] = reg.get("ha_quemadas")
        r["serie"] = s
    if met:
        r["validacion"] = {"espacial": [{k: m.get(k) for k in ("t_eval_utc", "horas_desde_ignicion", "ha_sim", "ha_ref", "iou", "dice", "omision", "comision")}
                                        for m in met.get("espacial", [])], "temporal": met.get("temporal")}
    return r


def _f(x, d: int = 0) -> str:
    if x is None:
        return "—"
    try:
        return f"{float(x):,.{d}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    except (TypeError, ValueError):
        return str(x)


def _md(r: dict[str, Any]) -> str:
    f = _f
    ori = f"evento **{r['evento']}**, hipótesis de ignición {r.get('hipotesis_ignicion')}, ignición {r.get('ignicion')}" if r.get("evento") else \
          (f"caso **{r['caso']}** (variante {r.get('variante_caso')})" if r.get("caso") else f"escenario nativo de SIM")
    L = [f"# Resumen de la corrida `{r['run_id']}`", "",
         f"Fecha de la corrida: {r['fecha_corrida']} · código {r.get('version_codigo')} (SIM {r.get('version_simulador')}) · resultados {r['version_resultados']} · máquina {r['maquina']}", ""]
    if r.get("descripcion"):
        L += [f"_{r['descripcion']}_", ""]
    L += [f"{ori[0].upper() + ori[1:]} en el dominio {r.get('dominio')}, desde {r.get('t_inicio_utc')} hasta {r.get('t_fin_simulado_utc')} ({r['horas_simuladas']} h de {f(r.get('horas_pedidas'), 0)} pedidas). Fin: `{r.get('motivo_fin')}`"
          f"{' — ' + r['motivo_fin_texto'] if r.get('motivo_fin_texto') else '.'}", "",
          "| Indicador | Valor |", "| --- | --- |",
          f"| Superficie quemada final (ha) | {f(r['superficie']['ha_quemadas_final'], 1)} |",
          f"| Tiempo de cómputo (s) / sub-pasos | {f(r['costo']['segundos'], 1)} / {f(r['costo']['sub_pasos'])} |"]
    pa = r.get("parametros") or {}; pr = pa.get("propagacion") or {}
    L.append(f"| k global / k por grupo / factor WAF | {pr.get('k_global')} / {pr.get('k_grupo') or '—'} / {pr.get('factor_waf')} |")
    L.append(f"| dt (min) / vecindad / modo | {pa.get('dt_min')} / {pa.get('vecindad')} / {pa.get('modo')} |")
    mo = r.get("modelo") or {}
    L.append(f"| Modelo / variante / humedad muerta | {mo.get('nombre')} / {mo.get('variante') or '—'} / {mo.get('humedad_muerta') or '—'} |")
    L.append(f"| Barreras / contención / supresión L03 | {'sí' if mo.get('barreras') else 'no'} / {'sí' if mo.get('contencion') else 'no'} / {'sí' if mo.get('supresion_l03') else 'no'} |")
    mi = r.get("mitigacion")
    if mi:
        d = mi.get("despacho") or {}
        L.append(f"| Despacho / inicio del combate | {d.get('modo')} ({d.get('inicio') or '—'}) / {f(mi.get('contencion_inicio_min'), 0)} min"
                 f"{' (' + str(mi['contencion_inicio_utc'])[:16] + ' UTC)' if mi.get('contencion_inicio_utc') else ''} |")
        if d.get("region"):
            L.append(f"| Departamento / región SNMF | {d.get('departamento')} / {d.get('region')} |")
        if d.get("llegadas_l03"):
            L.append("| Llegadas L03 (min) | " + ", ".join(f"{x['cuartel']} {f(x['llegada_min'], 0)}" for x in d["llegadas_l03"]) + " |")
        ins = mi.get("insumos") or {}
        if any(ins.values()):
            L.append(f"| Mitigación (insumos) | {', '.join(f'{k}: {v}' for k, v in ins.items() if v)} |")
    s = r.get("serie")
    if s:
        L += [f"| Superficie a 24 h / 72 h (ha) | {f(s['ha_a_24h'], 1)} / {f(s['ha_a_72h'], 1)} |",
              f"| Máximo avance horario (ha/h) y hora | {f(s['max_ha_por_hora'], 1)} · {s['hora_pico']} |",
              f"| Viento 10 m media / máx (km/h) | {s['viento_10m_kmh']['media']} / {s['viento_10m_kmh']['max']} |",
              f"| Humedad relativa media / mín (%) | {s['humedad_relativa_pct']['media']} / {s['humedad_relativa_pct']['min']} |",
              f"| Temperatura media / máx (°C) | {s['temperatura_c']['media']} / {s['temperatura_c']['max']} |"]
        if s.get("humedad_muerta_1h_pct"):
            L.append(f"| Humedad muerta 1 h media / mín (%) | {s['humedad_muerta_1h_pct']['media']} / {s['humedad_muerta_1h_pct']['min']} |")
    v = r.get("validacion")
    if v and v.get("espacial"):
        L += ["", "## Ajuste contra la cicatriz", "", "| Evaluación (UTC) | h | ha sim | ha ref | IoU | Dice | Omisión | Comisión |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        n3 = lambda x, d=3: "—" if x is None else f"{x:.{d}f}"
        for m in v["espacial"]:
            L.append(f"| {m.get('t_eval_utc')} | {f(m.get('horas_desde_ignicion'), 0)} | {f(m.get('ha_sim'))} | {f(m.get('ha_ref'))} | {n3(m.get('iou'))} | "
                     f"{n3(m.get('dice'))} | {n3(m.get('omision'), 2)} | {n3(m.get('comision'), 2)} |")
        t = v.get("temporal") or {}
        if t.get("fraccion_capturada_total") is not None:
            dm = t.get("desfase_mediano_h")
            L += ["", f"Focos de calor: capturados {t['fraccion_capturada_total']:.2f} del total, {t.get('fraccion_capturada_al_fin_del_dia', 0):.2f} al fin del día; "
                      f"desfase mediano {'—' if dm is None else f'{float(dm):.1f}'} h."]
    return "\n".join(L) + "\n"


def escribir_resumen(carpeta: Path) -> tuple[Path, Path]:
    """Escribe resumen_<run_id>_<fecha>.json y .md en la carpeta de la corrida y devuelve sus rutas."""
    carpeta = Path(carpeta)
    r = resumen_de_corrida(carpeta)
    marca = dt.datetime.fromisoformat(r["fecha_corrida"]).strftime("%Y%m%d-%H%M")
    nombre = r["run_id"] if r["run_id"].endswith(marca) else f"{r['run_id']}_{marca}"
    pj = carpeta / f"resumen_{nombre}.json"; pm = pj.with_suffix(".md")
    escribir_json(r, pj)
    pm.write_text(_md(r), encoding="utf-8")
    return pj, pm
