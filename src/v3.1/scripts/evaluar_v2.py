"""Ablación y calibración del modelo v2 (barreras + contención; docs/10 §7).

Ablación (4 variantes por evento, parámetros del YAML):
    python scripts/evaluar_v2.py ablacion --eventos SL-2024-MESILLA,SL-2022-RENCA,SL-2022-PUERTAS,SL-2024-LASLAGUNAS
    -> resultados/v3.1/evaluacion_v2/ablacion.csv ; corridas <evento>_v2_{libre,barreras,contencion,ambas}
Barrido (ambos módulos activos) sobre los eventos de calibración:
    python scripts/evaluar_v2.py barrido --eventos SL-2024-MESILLA,SL-2022-RENCA --tasa 800,1000,1200,1500 --sostener 350,1700 --lambda 1.0,2.0
    -> resultados/v3.1/evaluacion_v2/barrido.csv ; corridas en calibracion_v2_<evento>/...
Despacho local del SNMF (docs/13): variantes `ambas` (tasa fija 1.000 m/h, retardo 2 h, sin ficha de combate = parametrización
global de docs/10), `local` (tasa escalonada con la superficie, retardo vial desde los cuarteles declarados, medios aéreos de
la ficha) y `local_pronostico` (lo mismo sin la ficha: cuartel más cercano y medios aéreos sorteados). Calibración de κ:
    python scripts/evaluar_v2.py kappa --eventos SL-2024-MESILLA --kappa 1,2,3,4,6,8
    -> resultados/v3.1/evaluacion_v2/kappa.csv ; corridas en calibracion_kappa_<evento>/k<κ>
Comparación con los días del SNMF (contención = día local del último crecimiento simulado, ficha `combate.snmf`):
    python scripts/evaluar_v2.py comparar --entradas ablacion_despacho.csv,ablacion_despacho_local.csv,ablacion_despacho_pron.csv
    -> resultados/v3.1/evaluacion_v2/comparacion_despacho.csv
Función objetivo sugerida: IoU al último instante de evaluación (extinción) sin degradar la omisión del primer instante.
"""
from __future__ import annotations

import argparse
import itertools
import json
import logging
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from incendios_sl import config as cfgmod  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validar import ejecutar_y_evaluar  # noqa: E402
from incendios_sl.simulation.entradas import PARCHES_DESPACHO  # noqa: E402

# ignición e hipótesis de referencia por evento (las usadas en las validaciones de las Etapas 6-7)
REFERENCIA = {"SL-2024-MESILLA": ("alt1", 0), "SL-2022-RENCA": ("alt0", 0), "SL-2022-PUERTAS": ("snmf", 0), "SL-2024-LASLAGUNAS": ("snmf", 1),
              "SL-2023-AGUADA": ("alt0", 0), "SL-2022-CHILCAS": ("snmf", 0), "SL-2022-PISCUYACU": ("snmf", 0), "SL-2022-PAMPITA": ("snmf", 0),
              "SL-2023-RINCON": ("snmf", 0), "SL-2023-CHACRAS": ("snmf", 0)}
# variante -> (modelo, barreras, contención, parche del YAML); `contencion`/`ambas` = parametrización global de docs/10
VARIANTES = {"libre": ("modelo_v1", None, None, None), "libre_v2": ("modelo_v2", False, False, None), "barreras": ("modelo_v2", True, False, None),
             "contencion": ("modelo_v2", False, True, PARCHES_DESPACHO["global"]), "ambas": ("modelo_v2", True, True, PARCHES_DESPACHO["global"]),
             "local": ("modelo_v2", True, True, PARCHES_DESPACHO["local"]), "local_pronostico": ("modelo_v2", True, True, PARCHES_DESPACHO["pronostico"]),
             "local_exacto": ("modelo_v2", True, True, {"contencion": PARCHES_DESPACHO["local"]["contencion"] | {"inicio_exacto": True}})}


def resumen(res: dict, etiqueta: dict) -> dict:
    e0, e1 = res["espacial"][0], res["espacial"][-1]
    tp = res.get("temporal", {}); v2 = res.get("v2", {}); dsp = v2.get("despacho") or {}; arr = dsp.get("arribo") or {}
    return etiqueta | {"iou_inicio": e0["iou"], "omision_inicio": e0["omision"], "comision_inicio": e0["comision"], "ha_sim_inicio": e0["ha_sim"],
                       "iou_fin": e1["iou"], "omision_fin": e1["omision"], "comision_fin": e1["comision"], "ha_sim_fin": e1["ha_sim"], "ha_ref": e1["ha_ref"],
                       "focos_a_tiempo": tp.get("fraccion_capturada_al_fin_del_dia"), "desfase_h": tp.get("desfase_mediano_h"),
                       "cruces": v2.get("cruces_barrera"), "bloqueos": v2.get("bloqueos_barrera"), "contenidas": v2.get("celdas_contenidas_final"),
                       "escapes": v2.get("escapes"), "metros_linea": v2.get("metros_linea"), "ultimo_crecimiento_utc": v2.get("ultimo_crecimiento_utc"),
                       "ha_sim_al_ultimo_crecimiento": v2.get("ha_sim_al_ultimo_crecimiento"), "contencion_inicio_utc": v2.get("contencion_inicio_utc"),
                       "region": dsp.get("region"), "cuartel_arribo": arr.get("cuartel"), "viaje_h": arr.get("t_viaje_h"),
                       "aereo_auto_desde_utc": v2.get("aereo_auto_desde_utc"),
                       "motivo_fin": res["motivo_fin"], "segundos": res["segundos_cpu"]}


def comparar(out: Path, entradas: list[str], salida: str) -> int:
    # "archivo.csv:etiqueta" reemplaza la columna variante (para comparar corridas de la misma variante con distinto YAML)
    partes = []
    for f in entradas:
        nombre, _, etiqueta = f.partition(":")
        d = pd.read_csv(out / nombre)
        partes.append(d.assign(variante=etiqueta) if etiqueta else d)
    df = pd.concat(partes, ignore_index=True)
    filas = []
    for _, r in df.iterrows():
        sn = (cfgmod.cargar_evento(r.evento).get("combate") or {}).get("snmf") or {}
        dia = None
        if isinstance(r.get("ultimo_crecimiento_utc"), str) and sn.get("inicio"):
            local = pd.Timestamp(r.ultimo_crecimiento_utc) - pd.Timedelta(hours=3)     # hora local (UTC-3)
            dia = (local.normalize().tz_localize(None) - pd.Timestamp(sn["inicio"])).days
        filas.append(r.to_dict() | {"dia_contencion_sim": dia, "dia_contencion_snmf": sn.get("contencion_dia"),
                                    "error_dia": None if dia is None or sn.get("contencion_dia") is None else dia - sn["contencion_dia"]})
    c = pd.DataFrame(filas); c.to_csv(out / salida, index=False)
    cols = ["evento", "variante", "ha_sim_inicio", "iou_inicio", "omision_inicio", "ha_sim_fin", "iou_fin", "comision_fin", "ha_ref",
            "focos_a_tiempo", "dia_contencion_sim", "dia_contencion_snmf"]
    print(c[cols].round(3).to_string(index=False))
    g = c.groupby("variante").agg(iou_inicio=("iou_inicio", "mean"), omision_inicio=("omision_inicio", "mean"), iou_fin=("iou_fin", "mean"),
                                  focos=("focos_a_tiempo", "mean"), err_dia_abs=("error_dia", lambda x: x.abs().median()),
                                  apagado_dia0=("ha_sim_fin", lambda x: int((x < 0.1 * c.loc[x.index, "ha_ref"]).sum())),
                                  sin_contener=("dia_contencion_sim", lambda x: int((x > c.loc[x.index, "dia_contencion_snmf"] + 2).sum())))
    print(g.round(3).to_string())
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("modo", choices=["ablacion", "barrido", "kappa", "comparar"])
    ap.add_argument("--entradas", default="ablacion_despacho.csv,ablacion_despacho_local.csv,ablacion_despacho_pron.csv")
    ap.add_argument("--kappa", default="1,2,3,4,6,8")
    ap.add_argument("--quiebre", default="inf", help="modo kappa: quiebre de kappa(A) en ha (docs/13 §8)")
    ap.add_argument("--gamma", default="0", help="modo kappa: exponente de decaimiento de kappa(A)")
    ap.add_argument("--kappa-min", dest="kappa_min", type=float, default=1.0)
    ap.add_argument("--exacto", action="store_true", help="modo kappa: combate desde el minuto de llegada (contencion.inicio_exacto)")
    ap.add_argument("--hipotesis", default="ref", help="ref (la de REFERENCIA) o lista de horas de ignición de la ficha, p. ej. 0,1,2")
    ap.add_argument("--eventos", default="SL-2024-MESILLA,SL-2022-RENCA,SL-2022-PUERTAS,SL-2024-LASLAGUNAS")
    ap.add_argument("--tasa", default="800,1000,1200,1500"); ap.add_argument("--sostener", default="350,1700"); ap.add_argument("--lambda", dest="lam", default="1.0")
    ap.add_argument("--retardo", default="2"); ap.add_argument("--figuras", action="store_true")
    ap.add_argument("--salida", default=None, help="nombre del CSV (por defecto ablacion.csv o barrido.csv); si existe se anexa y se omiten las combinaciones ya hechas")
    ap.add_argument("--sufijo", default="", help="sufijo de los run_id de la ablación, p. ej. _t1000")
    ap.add_argument("--variantes", default=",".join(VARIANTES), help="variantes de la ablación a correr (libre, libre_v2, barreras, contencion, ambas)")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    out = cfgmod.dir_resultados() / "evaluacion_v2"; out.mkdir(parents=True, exist_ok=True)
    csv = out / (a.salida or f"{a.modo}.csv")
    filas = pd.read_csv(csv).to_dict("records") if csv.exists() else []
    eventos = a.eventos.split(",")
    if a.modo == "comparar":
        return comparar(out, a.entradas.split(","), a.salida or "comparacion_despacho.csv")
    def hipotesis_de(ev: str, hip_ref: int) -> list[int]:
        """Horas de ignición a correr: la de referencia (por defecto) o las indicadas en --hipotesis (p. ej. 0,1,2)."""
        return [hip_ref] if a.hipotesis == "ref" else [int(x) for x in a.hipotesis.split(",")]

    def sufijo_hip(h: int) -> str:
        return "" if a.hipotesis == "ref" else f"_h{h}"

    if a.modo == "ablacion":
        hechas = {(f.get("evento"), f.get("variante"), int(f.get("hipotesis", -1)) if not pd.isna(f.get("hipotesis", -1)) else -1) for f in filas}
        for ev in eventos:
            ign, hip_ref = REFERENCIA.get(ev, ("snmf", 0))
            for hip in hipotesis_de(ev, hip_ref):
                for var in a.variantes.split(","):
                    modelo, barr, cont, parche = VARIANTES[var]
                    if (ev, var, hip) in hechas:
                        continue
                    rid = f"{ev}_v2_{var}{a.sufijo}{sufijo_hip(hip)}"
                    try:
                        res = ejecutar_y_evaluar(ev, hip, None, 1.0, rid, figs=a.figuras, ignicion=ign, modelo=modelo, barreras=barr, contencion=cont, parche_modelo=parche)
                        fila = resumen(res, {"evento": ev, "variante": var, "ignicion": ign, "hipotesis": hip})
                    except Exception as e:  # noqa: BLE001
                        fila = {"evento": ev, "variante": var, "hipotesis": hip, "error": str(e)[:200]}
                    filas.append(fila); print(fila, flush=True)
                    pd.DataFrame(filas).to_csv(csv, index=False)
    elif a.modo == "kappa":
        def _clave(f):
            q = f.get("quiebre_ha", float("inf")); g = f.get("gamma", 0.0); h = f.get("hipotesis", -1)
            return (f.get("evento"), f.get("kappa"), float("inf") if pd.isna(q) else float(q), 0.0 if pd.isna(g) else float(g),
                    -1 if pd.isna(h) else int(h))
        hechas = {_clave(f) for f in filas}
        combos = list(itertools.product([float(x) for x in a.kappa.split(",")], [float(x) for x in a.quiebre.split(",")], [float(x) for x in a.gamma.split(",")]))
        for ev in eventos:
            ign, hip_ref = REFERENCIA.get(ev, ("snmf", 0))
            for hip in hipotesis_de(ev, hip_ref):
                for k, q, g in combos:
                    if (ev, k, q, g, hip if a.hipotesis != "ref" else -1) in hechas or (a.hipotesis == "ref" and (ev, k, q, g, hip) in hechas):
                        continue
                    kt = {"quiebre_ha": q, "gamma": g, "minimo": a.kappa_min}
                    cont = PARCHES_DESPACHO["local"]["contencion"] | {"despacho": {"modo": "snmf", "kappa": k, "kappa_tamano": kt}}
                    if a.exacto:
                        cont = cont | {"inicio_exacto": True}
                    rid = f"calibracion_kappa_{ev}/k{k:g}" + (f"_q{q:g}_g{g:g}" if g else "") + ("_ex" if a.exacto else "") + sufijo_hip(hip)
                    etiqueta = {"evento": ev, "ignicion": ign, "kappa": k, "quiebre_ha": q, "gamma": g, "hipotesis": hip, "inicio_exacto": a.exacto}
                    try:
                        res = ejecutar_y_evaluar(ev, hip, None, 1.0, rid, figs=False, ignicion=ign, modelo="modelo_v2",
                                                 barreras=True, contencion=True, parche_modelo={"contencion": cont})
                        fila = resumen(res, etiqueta)
                    except Exception as e:  # noqa: BLE001
                        fila = etiqueta | {"error": str(e)[:200]}
                    filas.append(fila); print(fila, flush=True)
                    pd.DataFrame(filas).to_csv(csv, index=False)
    else:
        combos = list(itertools.product([float(x) for x in a.tasa.split(",")], [float(x) for x in a.sostener.split(",")],
                                        [float(x) for x in a.lam.split(",")], [float(x) for x in a.retardo.split(",")]))
        print(f"{len(combos)} combinaciones × {len(eventos)} eventos")
        hechas = {(f.get("evento"), f.get("tasa_linea_m_h"), f.get("intensidad_sostener_kw_m"), f.get("cruce_lambda"), f.get("contencion_retardo_h")) for f in filas}
        for ev in eventos:
            ign, hip = REFERENCIA.get(ev, ("snmf", 0))
            for tasa, sost, lam, ret in combos:
                if (ev, tasa, sost, lam, ret) in hechas:
                    continue
                rid = f"calibracion_v2_{ev}/t{tasa:.0f}_s{sost:.0f}_l{lam}_r{ret:.0f}"
                extra = {"tasa_linea_m_h": tasa, "intensidad_sostener_kw_m": sost, "cruce_lambda": lam, "contencion_retardo_h": ret}
                try:
                    res = ejecutar_y_evaluar(ev, hip, None, 1.0, rid, figs=False, ignicion=ign, modelo="modelo_v2", barreras=True, contencion=True, extra_cfg=extra)
                    fila = resumen(res, {"evento": ev, "ignicion": ign} | extra)
                except Exception as e:  # noqa: BLE001
                    fila = {"evento": ev, "error": str(e)[:200]} | extra
                filas.append(fila); print(fila, flush=True)
                pd.DataFrame(filas).to_csv(csv, index=False)
        df = pd.DataFrame(filas)
        if "iou_fin" in df:
            print(df.sort_values(["evento", "iou_fin"], ascending=[True, False]).groupby("evento").head(5).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
