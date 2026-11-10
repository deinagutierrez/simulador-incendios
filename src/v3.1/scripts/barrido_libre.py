"""Barrido de la simulación libre (sin barreras ni contención) evaluado con forma + tiempo (docs/v3.1/01-02).

Uso:
  # paso 2a: hora de ignición, candidatos cada 2 h en las 14 h previas a la primera detección VIIRS del evento
  python scripts/barrido_libre.py --modo hora --salida ../../resultados/v3.1/paso2_hora/barrido.csv
  # paso 2b: factor_waf con la hipótesis horaria recomendada de cada ficha
  python scripts/barrido_libre.py --modo waf --waf 0.6,0.8,1.0,1.25,1.5 --salida ../../resultados/v3.1/paso2_waf/barrido.csv

Cada corrida: ignición espacial recomendada (`recomendada.ignicion` de la ficha, o la tabla IGNICION_REC), variante libre_v2
salvo --variante. Se corta cuando ya pasó la última detección (+1 h) y la superficie simulada alcanzó la de la cicatriz.
Métricas: iou_igual_superficie y metricas_primera_deteccion; puntaje = (iou + frac_a_tiempo) / 2 (sin focos: sólo iou).
"""
from __future__ import annotations

import argparse
import copy
import logging
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from incendios_sl import config as cfgmod  # noqa: E402

# ignición espacial recomendada (búsqueda inversa 2026-10-27, docs/v3.1/README); se usa si la ficha no trae `recomendada`
IGNICION_REC = {"SL-2022-CHILCAS": "alt1", "SL-2022-PAMPITA": "snmf", "SL-2022-PISCUYACU": "alt0", "SL-2022-PUERTAS": "alt0",
                "SL-2022-RENCA": "alt1", "SL-2023-AGUADA": "alt1", "SL-2023-CHACRAS": "alt1", "SL-2023-RINCON": "alt1",
                "SL-2024-MESILLA": "alt2", "SL-2024-LASLAGUNAS": "alt0"}


def focos(evento: str) -> pd.DataFrame | None:
    p = cfgmod.dir_catalogo() / "hotspots_v3.1" / f"viirs_{evento}.csv"
    d = pd.read_csv(p) if p.exists() and p.stat().st_size > 10 else None
    return d if d is not None and len(d) else None


def t_deteccion(hs: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(hs["date"]).dt.tz_localize("UTC") + pd.to_timedelta(hs["acq_time_s"], unit="s")


def recomendada(ev: dict) -> tuple[str, int]:
    r = ev.get("recomendada") or {}
    return r.get("ignicion", IGNICION_REC.get(ev["id"], "snmf")), int(r.get("hipotesis", 0))


def primera_deteccion(ev: dict) -> pd.Timestamp | None:
    """La más temprana entre el primer foco de hotspots_v3.1 y la `cota_superior_utc` de la ficha (focos que sólo están en GEE)."""
    hs = focos(ev["id"]); cota = ev["inicio"].get("cota_superior_utc")
    ts = ([t_deteccion(hs).min()] if hs is not None else []) + ([pd.Timestamp(cota)] if cota else [])
    return min(ts) if ts else None


def candidatos_hora(ev: dict, paso_h: float = 2.0, ventana_h: float = 14.0) -> list[pd.Timestamp]:
    """Horas en punto anteriores a la primera detección, cada `paso_h`, dentro de las `ventana_h` previas
    (la pasada anterior sin detección está ≤ 13 h antes con SNPP + NOAA-20)."""
    t1 = primera_deteccion(ev)
    if t1 is None:
        return []
    ult = (t1 - pd.Timedelta(minutes=30)).floor("h")
    return [ult - pd.Timedelta(hours=h) for h in np.arange(0.0, ventana_h - 0.5 + 1e-9, paso_h)][::-1]


def puntos_candidatos(evento: str, n: int = 40) -> list[dict]:
    """Grilla regular de ~n puntos sobre la cicatriz principal (partes ≥ 15 % del total) dilatada 300 m."""
    from pyproj import Transformer
    from scipy import ndimage
    from incendios_sl.grilla import leer_raster
    ref, g, _ = leer_raster(cfgmod.dir_entradas() / "eventos" / evento / f"cicatriz_referencia_{evento}.tif")
    ref = ref == 1
    lab, nlab = ndimage.label(ref, structure=np.ones((3, 3)))
    tam = ndimage.sum(ref, lab, range(1, nlab + 1))
    principal = ndimage.binary_dilation(np.isin(lab, 1 + np.nonzero(tam >= 0.15 * ref.sum())[0]), iterations=10)
    rr, cc = np.nonzero(principal)
    paso = max(1, int(round(np.sqrt(len(rr) / n))))
    sel = (rr % paso == (rr.min() + paso // 2) % paso) & (cc % paso == (cc.min() + paso // 2) % paso)
    tr = Transformer.from_crs(g.crs, "EPSG:4326", always_xy=True)
    return [{"nombre": f"grilla {k}", "lon": round(float(lo), 5), "lat": round(float(la), 5)}
            for k, (lo, la) in enumerate(tr.transform(*g.rc_a_xy(r, c)) for r, c in zip(rr[sel], cc[sel]))]


GRUPOS_K = {"A": (1, 2, 3), "B": (4, 5), "C": (6, 7)}   # pastizal-pastura-arbustal abierto / arbustal cerrado-bosque abierto / bosque cerrado-plantación


def k_de_grupos(kA: float, kB: float, kC: float) -> dict[int, float]:
    return {c: k for g, k in zip("ABC", (kA, kB, kC)) for c in GRUPOS_K[g]}


def correr(evento: str, t0: pd.Timestamp | None, factor_waf: float, variante: str, ignicion: str | None = None,
           puntos: list[dict] | None = None, k_grupos: tuple[float, float, float] | None = None, fuente_viento: str | None = None) -> dict:
    logging.disable(logging.WARNING)
    from evaluar_v2 import VARIANTES
    from incendios_sl.grilla import leer_raster
    from incendios_sl.simulation.entradas import cargar_entradas_evento
    from incendios_sl.simulation.motor import Simulacion
    from incendios_sl.validation.metricas import iou_igual_superficie, metricas_primera_deteccion
    orig = cfgmod.cargar_evento
    ev0 = orig(evento); ign, hip = recomendada(ev0)
    ign = ignicion or ign
    if t0 is not None or puntos:   # hora o puntos candidatos: se agregan a la ficha sólo para esta corrida
        n_hip = len(ev0["inicio"]["hora_utc_hipotesis"]); n_alt = len(ev0.get("ignicion_alternativas") or [])

        def cargar_mod(i, _o=orig):
            e = copy.deepcopy(_o(i))
            if i == evento and t0 is not None:
                e["inicio"]["hora_utc_hipotesis"] = list(e["inicio"]["hora_utc_hipotesis"]) + [t0.strftime("%Y-%m-%dT%H:%M:%SZ")]
            if i == evento and puntos:
                e["ignicion_alternativas"] = list(e.get("ignicion_alternativas") or []) + [{"fuente": "barrido", "puntos": puntos}]
            return e
        cfgmod.cargar_evento = cargar_mod
        hip = n_hip if t0 is not None else hip
        ign = f"alt{n_alt}" if puntos else ign
    modelo, barreras, contencion, parche = VARIANTES[variante]
    if fuente_viento:
        from incendios_sl.simulation.entradas import fusionar
        parche = fusionar(parche or {}, {"viento": {"fuente_horaria": fuente_viento}})
    t_ini = time.time()
    ent, cfg, g, meta = cargar_entradas_evento(evento, hip, k_clase=k_de_grupos(*k_grupos) if k_grupos else None, factor_waf=factor_waf,
                                               ignicion=ign, modelo=modelo, barreras=barreras, contencion=contencion, parche_modelo=parche)
    E = cfgmod.dir_entradas()
    ref = leer_raster(E / "eventos" / evento / f"cicatriz_referencia_{evento}.tif")[0] == 1
    valido = (ent.mascara == 1) & (ent.clase > 0)
    ha_ref = float((ref & valido).sum()) * g.res ** 2 / 1e4
    hs = focos(evento)
    t_ult = (t_deteccion(hs).max() - ent.t_inicio_utc).total_seconds() + 3600 if hs is not None else 0.0

    class _Parar(Exception):
        pass

    def cb(s):
        if s["ha_quemadas"] >= ha_ref and s["t_s"] >= t_ult:
            raise _Parar
    sim = Simulacion(ent, cfg)
    try:
        sim.ejecutar(callback=cb)
    except _Parar:
        pass
    forma = iou_igual_superficie(sim.t_arr, ref, valido, g.res)
    tmp = metricas_primera_deteccion(sim.t_arr, g, hs, ent.t_inicio_utc)
    fa = tmp.get("frac_a_tiempo")
    return {"evento": evento, "ignicion": ign, "t_inicio_utc": str(ent.t_inicio_utc), "factor_waf": factor_waf, "variante": variante,
            "lon": puntos[0]["lon"] if puntos else None, "lat": puntos[0]["lat"] if puntos else None,
            "kA": cfg.k_clase.get(1), "kB": cfg.k_clase.get(4), "kC": cfg.k_clase.get(6), "fuente_viento": meta.get("fuente_viento"),
            "horas_sin_campo_horario": getattr(ent.viento, "faltan", {}).get("n") if ent.viento is not None else None,
            "iou_igual_sup": round(forma["iou"], 3), "horas_hasta_sup": round(forma["horas"], 1), "alcanza_sup": forma["alcanza"],
            "n_primeras": tmp.get("n_primeras", 0), "frac_a_tiempo": fa, "frac_adelantado": tmp.get("frac_adelantado"),
            "frac_atrasado": tmp.get("frac_atrasado"), "frac_no_alcanzado": tmp.get("frac_no_alcanzado"),
            "error_mediano_h": tmp.get("error_mediano_h"), "error_absoluto_medio_h": tmp.get("error_absoluto_medio_h"),
            "puntaje": round((forma["iou"] + fa) / 2 if fa is not None else forma["iou"], 3), "segundos": round(time.time() - t_ini, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modo", choices=["hora", "punto", "waf", "k", "viento"], required=True)
    ap.add_argument("--fuentes", default="biblioteca", help="viento.fuente_horaria separadas por coma (modo viento, docs/v3.1/04)")
    ap.add_argument("--ka", default="0.75"); ap.add_argument("--kb", default="2"); ap.add_argument("--kc", default="5")
    ap.add_argument("--k", default="", help="lista explícita kA/kB/kC separada por coma, p. ej. 0.75/2/5,1/3/5 (modo k)")
    ap.add_argument("--eventos", default=None); ap.add_argument("--variante", default="libre_v2")
    ap.add_argument("--waf", default="1.0"); ap.add_argument("--paso-h", type=float, default=2.0)
    ap.add_argument("--hora", default="", help="EVENTO=AAAA-MM-DDTHH:MMZ,… hora de ignición fija (modos punto y waf)")
    ap.add_argument("--n-puntos", type=int, default=40)
    ap.add_argument("--procs", type=int, default=12); ap.add_argument("--salida", required=True)
    a = ap.parse_args()
    horas = dict(x.split("=", 1) for x in a.hora.split(",") if x)
    eventos = a.eventos.split(",") if a.eventos else sorted(p.stem for p in (cfgmod.dir_escenarios() / "eventos").glob("SL-*.yaml"))
    trabajos = []
    for e in eventos:
        if a.modo == "hora":
            ev = cfgmod.cargar_evento(e); _, hip = recomendada(ev)
            cands = candidatos_hora(ev, a.paso_h)
            # también las tres hipótesis de la ficha, como referencia
            cands += [pd.Timestamp(t) for t in ev["inicio"]["hora_utc_hipotesis"][:3]]
            trabajos += [(e, t, 1.0) for t in sorted(set(cands))]
        elif a.modo == "punto":
            t = pd.Timestamp(horas[e]) if e in horas else None
            trabajos += [(e, t, 1.0, [p]) for p in puntos_candidatos(e, a.n_puntos)]
        elif a.modo == "k":
            ks = [tuple(float(v) for v in x.split("/")) for x in a.k.split(",")] if a.k else \
                [(ka, kb, kc) for ka in map(float, a.ka.split(",")) for kb in map(float, a.kb.split(",")) for kc in map(float, a.kc.split(","))]
            trabajos += [(e, None, 1.0, None, k) for k in ks]
        elif a.modo == "viento":
            trabajos += [(e, None, 1.0, None, None, f) for f in a.fuentes.split(",")]
        else:
            trabajos += [(e, pd.Timestamp(horas[e]) if e in horas else None, float(w)) for w in a.waf.split(",")]
    trabajos = [x + (None,) * (6 - len(x)) for x in trabajos]
    print(f"{len(trabajos)} corridas", flush=True)
    sal = Path(a.salida); sal.parent.mkdir(parents=True, exist_ok=True)
    filas = []
    with ProcessPoolExecutor(a.procs) as ex:
        fut = {ex.submit(correr, e, t, w, a.variante, None, p, k, fv): (e, t, w) for e, t, w, p, k, fv in sorted(trabajos, key=lambda x: "LASLAGUNAS" not in x[0])}
        for f in as_completed(fut):
            e, t, w = fut[f]
            try:
                r = f.result()
            except Exception as exc:  # noqa: BLE001
                print("ERROR", e, t, w, repr(exc), flush=True); continue
            filas.append(r)
            print(f"{e:20s} {r['t_inicio_utc'][:16]} viento={r['fuente_viento']} waf={w} k={r['kA']}/{r['kB']}/{r['kC']} ({r['lon']}, {r['lat']}) IoU={r['iou_igual_sup']} a_tiempo={r['frac_a_tiempo']} err={r['error_mediano_h']} puntaje={r['puntaje']}", flush=True)
            pd.DataFrame(filas).sort_values(["evento", "t_inicio_utc", "factor_waf"]).to_csv(sal, index=False)
    print("salida:", sal)
    return 0


if __name__ == "__main__":
    sys.exit(main())
