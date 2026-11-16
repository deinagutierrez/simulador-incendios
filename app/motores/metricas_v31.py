"""Métricas del modo histórico con el código de v3.1 (F6, D-E3-30 punto 10), sobre una corrida terminada del simulador.

    python -I app/motores/metricas_v31.py --corrida resultados/app/<id>

Lee `<corrida>/corrida.json` (el evento sale de `base.definicion.evento`) y la salida del motor en `<corrida>/salida/`:
`t_llegada_s.tif` (v3.1) o `hora_llegada_min.tif` + `registro.json` (v4.0). Escribe `<corrida>/metricas_v31.json`.

Las métricas son las de `src/v3.1/scripts/evaluar_x49.py` (función `evaluar`) y `incendios_sl/validation/metricas.py`, con la
misma referencia que `evaluar_x49.main`: la cicatriz `eventos/<ev>/cicatriz_referencia_<ev>.tif` (== 1), la máscara válida
(máscara del dominio == 1 y clase de combustible de v3 > 0) y los focos de `catalogo/hotspots_v3.1/viirs_<ev>.csv`:

- `iou_igual_sup`, `horas_hasta_sup`, `alcanza_sup`: IoU en el instante en que la simulación iguala la superficie de la
  cicatriz. Con `alcanza_sup` = false la simulación nunca la iguala y el IoU es el de toda la huella (no es "a igual
  superficie": se avisa);
- `n_primeras`, `frac_a_tiempo`, `frac_adelantado`, `frac_atrasado`, `frac_no_alcanzado`, `error_mediano_h`: primeras
  detecciones VIIRS (ventana 13 h, holgura 1 h, tolerancia 375 m);
- `puntaje` = (IoU a igual superficie + fracción a tiempo) / 2;
- `por_pasada`: por pasada satelital, cuántas primeras detecciones caen en cada clase (lo devuelve `metricas.py`);
- `focos`: la clase de cada foco (para colorearlo en el mapa). `metricas.py` no la devuelve foco por foco: se repite su
  cuenta paso por paso y se comprueba que sume lo mismo que `por_pasada` en cada pasada; si no coincide, `focos` = null;
- `por_instante`: IoU (y superficies) en cada `fin.evaluacion_utc` de la ficha de v3.1, con `despues_del_fin` = true
  cuando el instante cae después del final de la corrida (la huella ya no cambia: quedó congelada).

Este proceso carga el camino de v3.1 (src/v3.1/src y src/v3.1/scripts) y nada de v4.0: los dos motores traen un paquete
`incendios_sl` y no pueden convivir. El servidor no lo importa: lo lanza aparte (app/servidor/historicos.py).

Salida estándar: una línea JSON al terminar ({"aviso": "final", ...} o {"aviso": "error", "mensaje": ...}). Si falla, el
archivo igual se escribe, con `error`, para que el servidor no lo vuelva a lanzar.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RAIZ_V31 = REPO / "src" / "v3.1"
FORMATO = "incendios_sl.metricas_v31/1"
ARCHIVO = "metricas_v31.json"
CODIGO = ("src/v3.1/scripts/evaluar_x49.py", "src/v3.1/src/incendios_sl/validation/metricas.py")
CLASES = ("a_tiempo", "adelantado", "atrasado", "no_alcanzado")


def _ahora() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _escribir(ruta: Path, datos: dict) -> None:
    tmp = ruta.with_name(ruta.name + ".tmp")
    tmp.write_text(json.dumps(datos, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    for intento in range(20):                    # en Windows falla si el servidor justo lo está leyendo
        try:
            os.replace(tmp, ruta)
            return
        except PermissionError:
            if intento == 19:
                raise
            time.sleep(0.05)


def evaluador() -> dict:
    """Qué código evaluó y en qué versión: sha256 de los dos archivos (y si coinciden con congelado.json) y el sha256 del
    conjunto congelado."""
    try:
        congelado = json.loads((REPO / "congelado.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        congelado = {}
    archivos = {}
    for rel in CODIGO:
        sha = hashlib.sha256((REPO / rel).read_bytes()).hexdigest()
        archivos[rel] = {"sha256": sha, "igual_al_congelado": (congelado.get("archivos") or {}).get(rel) == sha}
    sha_conjunto = congelado.get("sha256_del_conjunto")
    return {"rotulo": f"evaluador: src/v3.1 (evaluar_x49.evaluar + validation/metricas.py), congelado {str(sha_conjunto)[:12]}",
            "codigo": archivos, "congelado_sha256": sha_conjunto}


def _evento(corrida: dict) -> str:
    d = (corrida.get("base") or {}).get("definicion") or {}
    if not d.get("evento"):
        raise ValueError("la corrida no es de un evento (`base.definicion.evento`): no hay cicatriz contra la cual medir")
    return str(d["evento"])


def _salida(carpeta: Path) -> Path:
    for d in (carpeta / "salida", carpeta):
        if (d / "t_llegada_s.tif").exists() or (d / "hora_llegada_min.tif").exists():
            return d
    raise ValueError(f"{carpeta}: no hay t_llegada_s.tif (v3.1) ni hora_llegada_min.tif (v4.0) en la salida")


def _llegada(d: Path):
    """(t en segundos desde t0 con inf donde no llegó, t0): la misma lectura que `evaluar_x49.evaluar`."""
    import numpy as np
    import pandas as pd
    import rasterio
    if (d / "t_llegada_s.tif").exists():
        with rasterio.open(d / "t_llegada_s.tif") as s:
            t = s.read(1).astype("float64"); t[t == s.nodata] = np.inf; t0 = pd.Timestamp(s.tags()["t_inicio_utc"])
        return t, t0
    with rasterio.open(d / "hora_llegada_min.tif") as s:
        t = s.read(1).astype("float64") * 60.0; t[~np.isfinite(t)] = np.inf
    reg = json.loads((d / "registro.json").read_text(encoding="utf-8"))
    return t, pd.Timestamp(reg["t_inicio_utc"]).tz_convert("UTC")


def clases_por_foco(t_arr, g, hotspots, t_inicio, tolerancia_m: float = 375.0, ventana_h: float = 13.0,
                    holgura_h: float = 1.0) -> list[dict]:
    """La cuenta de `metricas.metricas_primera_deteccion`, paso por paso y con los mismos parámetros por defecto, pero
    devolviendo la clase de cada foco (las primeras detecciones) y marcando los focos que no son primera detección.
    No reemplaza a esa función: se usa para colorear los focos y se comprueba contra su `por_pasada`."""
    import numpy as np
    import pandas as pd
    hs = hotspots.copy()
    hs["t_det_s"] = ((pd.to_datetime(hs["date"]).dt.tz_localize("UTC") + pd.to_timedelta(hs["acq_time_s"], unit="s"))
                     - t_inicio).dt.total_seconds()
    hs = hs.sort_values("t_det_s").reset_index(drop=True)
    r, c = g.lonlat_a_rc(hs["lon"].to_numpy(), hs["lat"].to_numpy())
    hs["fila"] = r; hs["col"] = c
    dentro = np.asarray(g.dentro(hs.fila, hs.col), bool)
    fuera = hs[~dentro]
    hs = hs[dentro].reset_index(drop=True)
    k = int(np.ceil(tolerancia_m / g.res))
    visto = np.zeros(t_arr.shape, bool); primera = np.zeros(len(hs), bool)
    for i, (fi, ci) in enumerate(zip(hs.fila.to_numpy(), hs.col.to_numpy())):
        primera[i] = not visto[fi, ci]
        if i + 1 == len(hs) or hs.t_det_s.iat[i + 1] != hs.t_det_s.iat[i]:
            for j in np.nonzero(hs.t_det_s.to_numpy() == hs.t_det_s.iat[i])[0]:
                fj, cj = hs.fila.iat[j], hs.col.iat[j]
                visto[max(0, fj - k):fj + k + 1, max(0, cj - k):cj + k + 1] = True
    t_sim = np.full(len(hs), np.inf)
    for i, (fi, ci) in enumerate(zip(hs.fila.to_numpy(), hs.col.to_numpy())):
        v = t_arr[max(0, fi - k):fi + k + 1, max(0, ci - k):ci + k + 1]
        v = v[np.isfinite(v) & (v >= 0)]
        if v.size:
            t_sim[i] = v.min()
    lo = hs.t_det_s.to_numpy() - ventana_h * 3600; hi = hs.t_det_s.to_numpy() + holgura_h * 3600
    alc = np.isfinite(t_sim)
    clase = np.select([~alc, t_sim < lo, t_sim > hi], ["no_alcanzado", "adelantado", "atrasado"], "a_tiempo")
    error = np.select([~alc, t_sim < lo, t_sim > hi], [np.nan, (t_sim - lo) / 3600, (t_sim - hs.t_det_s.to_numpy()) / 3600], 0.0)
    out = []
    for i in range(len(hs)):
        t_det = t_inicio + pd.Timedelta(seconds=float(hs.t_det_s.iat[i]))
        out.append({"lon": float(hs.lon.iat[i]), "lat": float(hs.lat.iat[i]), "t_det_utc": str(t_det),
                    "primera": bool(primera[i]), "clase": str(clase[i]) if primera[i] else None,
                    "error_h": (None if not primera[i] or not np.isfinite(error[i]) else round(float(error[i]), 2)),
                    "t_sim_h": (round(float(t_sim[i]) / 3600, 2) if np.isfinite(t_sim[i]) else None)})
    for _, f in fuera.iterrows():
        out.append({"lon": float(f.lon), "lat": float(f.lat), "t_det_utc": str(t_inicio + pd.Timedelta(seconds=float(f.t_det_s))),
                    "primera": False, "clase": None, "error_h": None, "t_sim_h": None, "fuera_de_la_grilla": True})
    return out


def _coincide_con_por_pasada(focos: list[dict], por_pasada: list[dict]) -> bool:
    cuenta: dict[str, dict] = {}
    for f in focos:
        if f["primera"]:
            x = cuenta.setdefault(f["t_det_utc"], {"n": 0, **{cl: 0 for cl in CLASES}})
            x["n"] += 1; x[f["clase"]] += 1
    esperado = {p["t_det_utc"]: {"n": p["n"], **{cl: p[cl] for cl in CLASES}} for p in por_pasada}
    return cuenta == esperado


def calcular(carpeta: Path) -> dict:
    carpeta = Path(carpeta).resolve()
    t_reloj = time.time()
    corrida = json.loads((carpeta / "corrida.json").read_text(encoding="utf-8"))
    ev = _evento(corrida)
    salida = _salida(carpeta)

    sys.path.insert(0, str(RAIZ_V31 / "scripts"))
    sys.path.insert(0, str(RAIZ_V31 / "src"))
    import numpy as np
    import pandas as pd
    import evaluar_x49                                         # src/v3.1/scripts/evaluar_x49.py
    from incendios_sl import config as cfgmod
    from incendios_sl.grilla import leer_raster
    from incendios_sl.validation.metricas import evaluar_tiempos, metricas_primera_deteccion

    # referencia, máscara y focos: como evaluar_x49.main
    D = cfgmod.dir_entradas()
    ficha = cfgmod.cargar_evento(ev)
    ruta_ref = D / "eventos" / ev / f"cicatriz_referencia_{ev}.tif"
    ref, g, _ = leer_raster(ruta_ref); ref = ref == 1
    dom = cfgmod.cargar_dominio(ficha["dominio"])["id"]
    valido = (leer_raster(D / "grilla" / f"mascara_dominio_{dom}.tif")[0] == 1) & \
             (leer_raster(D / "combustibles" / ev / f"combustible_clase_{ev}.tif")[0] > 0)
    ruta_focos = cfgmod.dir_catalogo() / "hotspots_v3.1" / f"viirs_{ev}.csv"
    hs = pd.read_csv(ruta_focos)

    r = evaluar_x49.evaluar(salida, ref, valido, g, hs)
    if r is None:
        raise ValueError(f"{salida}: evaluar_x49 no la reconoce como corrida de v3.1 ni de v4.0 (¿falta registro.json?)")

    t, t0 = _llegada(salida)
    tm = metricas_primera_deteccion(t, g, hs, t0)
    resultados = corrida.get("resultados") or {}
    t_sim_min = resultados.get("t_simulado_min")
    instantes = []
    for m in evaluar_tiempos(t, ref, valido, g.res, t0, list((ficha.get("fin") or {}).get("evaluacion_utc") or [])):
        h = float(m["horas_desde_ignicion"])
        instantes.append({"t_eval_utc": m["t_eval_utc"], "horas_desde_ignicion": round(h, 2),
                          "iou": None if m["iou"] is None else round(float(m["iou"]), 3),
                          "dice": None if m["dice"] is None else round(float(m["dice"]), 3),
                          "ha_sim": round(float(m["ha_sim"]), 1), "ha_ref": round(float(m["ha_ref"]), 1),
                          "antes_de_la_ignicion": h < 0,
                          "despues_del_fin": None if t_sim_min is None else bool(h * 60.0 > float(t_sim_min) + 1e-6)})

    focos = clases_por_foco(t, g, hs, t0) if tm.get("disponible") else []
    focos_ok = bool(tm.get("disponible")) and _coincide_con_por_pasada(focos, tm.get("por_pasada") or [])
    iou_sup = evaluar_x49.iou_igual_superficie(t, ref, valido, g.res)

    avisos = []
    if not r["alcanza_sup"]:
        avisos.append(f"la simulación no alcanza la superficie de la cicatriz ({iou_sup['ha_sim']:.0f} ha contra "
                      f"{iou_sup['ha_ref']:.0f} ha): el IoU es el de toda la huella, no 'a igual superficie'")
    tarde = [x["t_eval_utc"] for x in instantes if x["despues_del_fin"]]
    if tarde:
        avisos.append(f"{len(tarde)} instante(s) de evaluación caen después del final de la corrida "
                      f"({(t_sim_min or 0) / 60:.1f} h simuladas): la huella ya no cambia")
    if not focos_ok and tm.get("disponible"):
        avisos.append("la clase foco por foco no coincidió con la cuenta por pasada de metricas.py: no se colorean")

    claves = ("iou_igual_sup", "horas_hasta_sup", "alcanza_sup", "n_primeras", "frac_a_tiempo", "frac_adelantado",
              "frac_atrasado", "frac_no_alcanzado", "error_mediano_h", "puntaje", "ha_final", "motivo_fin")
    return {
        "formato": FORMATO, "corrida": carpeta.name, "motor": corrida.get("motor"), "evento": ev,
        "calculado_utc": _ahora(), "s_calculo": round(time.time() - t_reloj, 2),
        "evaluador": evaluador(),
        "referencia": {"cicatriz": ruta_ref.relative_to(REPO).as_posix() if REPO in ruta_ref.parents else str(ruta_ref),
                       "ha_ref_valida": round(float(iou_sup["ha_ref"]), 1),
                       "mascara": f"mascara_dominio_{dom}.tif == 1 y combustible_clase_{ev}.tif > 0 (v3)",
                       "focos": ruta_focos.relative_to(REPO).as_posix() if REPO in ruta_focos.parents else str(ruta_focos),
                       "n_focos": int(len(hs)), "ventana_h": tm.get("ventana_h"), "tolerancia_m": tm.get("tolerancia_m")},
        "version_salida": r["version"], "t_inicio_utc": r["t_inicio_utc"], "t_simulado_min": t_sim_min,
        "ignicion": {"ignicion": r["ignicion"], "hipotesis": r["hipotesis"], "punto": r["punto"], "lon": r["lon"], "lat": r["lat"]},
        "metricas": {k: (v.item() if isinstance(v, np.generic) else v) for k, v in r.items() if k in claves},
        "error_absoluto_medio_h": tm.get("error_absoluto_medio_h"),
        "por_pasada": tm.get("por_pasada") or [],
        "por_instante": instantes,
        "focos": focos if focos_ok else None,
        "avisos": avisos,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Métricas de v3.1 (cicatriz y focos) para una corrida del simulador")
    ap.add_argument("--corrida", required=True, help="carpeta de la corrida (con corrida.json y salida/)")
    a = ap.parse_args()
    carpeta = Path(a.corrida).resolve()
    destino = carpeta / ARCHIVO
    try:
        datos = calcular(carpeta)
    except Exception as e:                                     # se deja escrito el motivo: el servidor no reintenta
        traceback.print_exc(file=sys.stderr)
        mensaje = f"{type(e).__name__}: {e}"
        try:
            _escribir(destino, {"formato": FORMATO, "corrida": carpeta.name, "calculado_utc": _ahora(), "error": mensaje})
        except OSError:
            pass
        print(json.dumps({"aviso": "error", "mensaje": mensaje}, ensure_ascii=False), flush=True)
        return 1
    _escribir(destino, datos)
    print(json.dumps({"aviso": "final", "archivo": str(destino), "puntaje": datos["metricas"].get("puntaje")},
                     ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
