"""Ejecuta un evento con parámetros dados y produce métricas espaciales/temporales y figuras.

Uso:
    python scripts/validar.py --evento SL-2024-LASLAGUNAS --hipotesis 1 --k-global 0.5 --factor-waf 1.0 --run-id calib_x
Salida: resultados/v3.1/<run_id>/ (rasters, serie, registro, metricas.json, mapas PNG, animación GIF).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from incendios_sl import config as cfgmod  # noqa: E402
from incendios_sl.grilla import leer_raster  # noqa: E402
from incendios_sl.simulation.entradas import cargar_entradas_evento  # noqa: E402
from incendios_sl.simulation.motor import Simulacion  # noqa: E402
from incendios_sl.validation.metricas import evaluar_tiempos, metricas_temporales, mascara_simulada, metricas_espaciales  # noqa: E402
from incendios_sl.validation import figuras  # noqa: E402

log = logging.getLogger("validar")


def _tri(v: str | None) -> bool | None:
    return None if v in (None, "auto") else v in ("on", "1", "true", "si", "sí")


def ejecutar_y_evaluar(evento: str, hipotesis: int, k_global: float | None, factor_waf: float, run_id: str, figs: bool = True,
                       horas: float | None = None, dt: float | None = None, k_clase: dict | None = None, ignicion: str = "snmf",
                       estado_path: str | None = None, modelo: str = "modelo_v1", barreras: bool | None = None, contencion: bool | None = None,
                       extra_cfg: dict | None = None, parche_modelo: dict | None = None) -> dict:
    ent, cfg, g, meta = cargar_entradas_evento(evento, hipotesis, k_clase, factor_waf=factor_waf, k_global=k_global, ignicion=ignicion,
                                               modelo=modelo, barreras=barreras, contencion=contencion, extra_cfg=extra_cfg, parche_modelo=parche_modelo)
    if horas:
        ent.t_fin_utc = min(ent.t_fin_utc, ent.t_inicio_utc + pd.Timedelta(hours=horas))
    if dt:
        cfg.dt_s = dt
    out = cfgmod.dir_resultados() / run_id; out.mkdir(parents=True, exist_ok=True)
    def _estado(**c):
        if estado_path:
            from incendios_sl.api.trabajos import escribir_estado
            escribir_estado(run_id, **c)
    total_s = (ent.t_fin_utc - ent.t_inicio_utc).total_seconds()
    _estado(estado="ejecutando_simulacion", progreso=0.0, mensaje="simulando", t_inicio_utc=str(ent.t_inicio_utc), t_fin_utc=str(ent.t_fin_utc), celdas=int(ent.mascara.size),
            celdas_dominio=int((ent.mascara == 1).sum()), resolucion_m=ent.res_m)
    def cb(s):
        _estado(progreso=min(1.0, s["t_s"] / total_s), hora_simulada_utc=s["time_utc"], ha_quemadas=s["ha_quemadas"], celdas_activas=s["celdas_activas"], segundos_cpu=s["segundos_cpu"])
    sim = Simulacion(ent, cfg); reg = sim.ejecutar(callback=cb)
    _estado(estado="guardando_resultados", progreso=1.0, mensaje="guardando resultados y métricas")
    rutas = sim.guardar(out, grilla=g, extra={"entradas": meta})
    ref, _, _ = leer_raster(cfgmod.dir_entradas() / "eventos" / evento / f"cicatriz_referencia_{evento}.tif")
    valido = (ent.mascara == 1) & (ent.clase > 0)
    tiempos = [t for t in meta["evaluacion_utc"] if pd.Timestamp(t) <= ent.t_fin_utc] or [str(ent.t_fin_utc)]
    esp = evaluar_tiempos(sim.t_arr, ref == 1, valido, g.res, ent.t_inicio_utc, tiempos)
    hs_path = cfgmod.dir_catalogo() / "hotspots" / f"viirs_{evento}.csv"
    hs = pd.read_csv(hs_path) if hs_path.exists() and hs_path.stat().st_size > 10 else None
    if hs is None or len(hs) == 0:
        hs_path = cfgmod.dir_catalogo() / "hotspots" / f"modis_{evento}.csv"
        hs = pd.read_csv(hs_path) if hs_path.exists() and hs_path.stat().st_size > 10 else None
        tol = 1000.0
    else:
        tol = 375.0
    temp = metricas_temporales(sim.t_arr, g, hs, ent.t_inicio_utc, tolerancia_m=tol) if hs is not None else {"disponible": False}
    # v2: instante en que la simulación deja de crecer (comparable con 'Contenido' del SNMF) y crecimiento tras la contención
    serie = pd.DataFrame(sim.serie)
    crec = serie[serie.ha_quemadas.diff().fillna(serie.ha_quemadas) > 0]
    t_ult_crec = str(crec.time_utc.iloc[-1]) if len(crec) else None
    v2 = reg.get("v2", {}) | {"modelo": modelo, "ultimo_crecimiento_utc": t_ult_crec, "ha_final_sobre_ref": float(reg["ha_quemadas"] / max(esp[-1]["ha_ref"], 1e-9)),
                              "despacho": meta.get("despacho"), "ha_sim_al_ultimo_crecimiento": float(crec.ha_quemadas.iloc[-1]) if len(crec) else 0.0}
    res = {"run_id": run_id, "evento": evento, "hipotesis_ignicion": hipotesis, "ignicion": ignicion, "k_global": k_global, "k_clase": cfg.k_clase, "factor_waf": factor_waf,
           "modelo": modelo, "v2": v2,
           "motivo_fin": reg["motivo_fin_texto"], "t_fin_simulado_utc": reg["t_simulado_utc"], "segundos_cpu": reg["segundos_cpu"],
           "espacial": esp, "temporal": temp, "fuente_focos": str(hs_path) if hs is not None else None, "tolerancia_focos_m": tol}
    with open(out / "metricas.json", "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, ensure_ascii=False, default=str)
    from incendios_sl.validation.resumen import escribir_resumen
    escribir_resumen(out)  # vuelve a escribir el resumen, ahora con las métricas de validación
    if figs:
        dem, _, _ = leer_raster(cfgmod.dir_entradas() / "dem" / f"dem_copernicus_glo30_{meta['dominio']}.tif")
        t_cont = sim.t_cont if cfg.contencion_activo else None
        etiqueta = f"k={k_global}, waf×{factor_waf}, hip. {hipotesis}" + (f", {modelo}" if modelo != "modelo_v1" else "") + \
            (" +barreras" if cfg.barreras_activo else "") + (" +contención" if cfg.contencion_activo else "")
        for m in esp:
            te = m["horas_desde_ignicion"] * 3600
            figuras.mapa_comparacion(sim.t_arr, ref, dem, g, te, f"{evento} | {run_id} | evaluación {m['t_eval_utc'][:16]} UTC ({etiqueta})",
                                     out / f"mapa_{pd.Timestamp(m['t_eval_utc']).strftime('%Y%m%dT%H')}.png", hs, ent.igniciones, m, t_cont=t_cont)
        figuras.animacion_diaria(sim.t_arr, ref, dem, g, ent.t_inicio_utc, min(reg["t_simulado_s"], esp[-1]["horas_desde_ignicion"] * 3600), out / "animacion.gif",
                                 paso_h=12.0, hotspots=hs, titulo=f"{evento} | {run_id}")
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--evento", required=True); ap.add_argument("--hipotesis", type=int, default=0)
    ap.add_argument("--k-global", type=float, default=None); ap.add_argument("--factor-waf", type=float, default=1.0)
    ap.add_argument("--run-id", default=None); ap.add_argument("--sin-figuras", action="store_true")
    ap.add_argument("--horas", type=float, default=None); ap.add_argument("--dt", type=float, default=None)
    ap.add_argument("--k", default=None, help="factores por clase, p. ej. 1=0.5,2=0.5,3=0.5,5=4,6=4")
    ap.add_argument("--ignicion", default="snmf", help="snmf | alt0, alt1... (ignicion_alternativas de la ficha)")
    ap.add_argument("--estado", default=None, help="ruta de estado.json para informar progreso (API)")
    ap.add_argument("--modelo", default="modelo_v1", help="modelo_v1 | modelo_v2 (barreras + contención, docs/10)")
    ap.add_argument("--barreras", default="auto", help="auto (según el YAML del modelo) | on | off")
    ap.add_argument("--contencion", default="auto", help="auto | on | off")
    ap.add_argument("--v2", default=None, help="ajustes de ConfigSimulacion v2, p. ej. cruce_lambda=1.5,cruce_beta=4,contencion_retardo_h=3,tasa_linea_m_h=500")
    ap.add_argument("--parche", default=None, help='JSON fusionado con el YAML del modelo, p. ej. {"contencion": {"despacho": {"modo": "snmf"}, "retardo_modo": "vial"}}')
    a = ap.parse_args(argv)
    kc = {int(x.split("=")[0]): float(x.split("=")[1]) for x in a.k.split(",")} if a.k else None
    extra = {x.split("=")[0]: (x.split("=")[1] if x.split("=")[0] in ("cruce_modo", "prioridad", "despacho_modo") else float(x.split("=")[1])) for x in a.v2.split(",")} if a.v2 else None
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run_id = a.run_id or f"{a.evento}_h{a.hipotesis}_k{a.k_global}_w{a.factor_waf}_{time.strftime('%Y%m%dT%H%M%S')}"
    res = ejecutar_y_evaluar(a.evento, a.hipotesis, a.k_global, a.factor_waf, run_id, not a.sin_figuras, a.horas, a.dt, kc, a.ignicion, a.estado,
                             a.modelo, _tri(a.barreras), _tri(a.contencion), extra, json.loads(a.parche) if a.parche else None)
    for m in res["espacial"]:
        print(f"{m['t_eval_utc']}: IoU {m['iou']:.3f} Dice {m['dice']:.3f} sim {m['ha_sim']:.0f} ha ref {m['ha_ref']:.0f} ha omisión {m['omision']:.2f} comisión {m['comision']:.2f}")
    if res["temporal"].get("disponible"):
        t = res["temporal"]; print(f"focos: capturados {t['fraccion_capturada_total']:.2f} | al fin del día {t['fraccion_capturada_al_fin_del_dia']:.2f} | desfase mediano {t['desfase_mediano_h']} h")
    v2 = res.get("v2", {})
    if v2.get("barreras_activo") or v2.get("contencion_activo"):
        print(f"v2: cruces {v2.get('cruces_barrera')} | bloqueos {v2.get('bloqueos_barrera')} | contenidas {v2.get('celdas_contenidas_final')} | escapes {v2.get('escapes')} | línea {v2.get('metros_linea', 0):.0f} m | último crecimiento {v2.get('ultimo_crecimiento_utc')}")
    print("salida:", cfgmod.dir_resultados() / run_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
