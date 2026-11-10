"""Pipeline reproducible de preparación de datos para un evento.

Uso:
    python scripts/preparar_evento.py --evento SL-2024-LASLAGUNAS [--sin-viento] [--sin-indices] [--sin-meteo]

Pasos: dominio (máscara, DEM, pendiente, orientación, cobertura, infraestructura, cicatriz mensual) ->
cicatriz de referencia del evento -> meteorología Open-Meteo -> NDVI/NDMI (GEE) -> biblioteca de viento
WindNinja -> mapa de combustibles -> serie de humedad -> manifiesto del evento.
Cada paso reutiliza productos vigentes (procedencia con los mismos parámetros).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from incendios_sl import config as cfgmod  # noqa: E402
from incendios_sl.data import preparar_dominio as pdm  # noqa: E402
from incendios_sl.procedencia import ahora_utc  # noqa: E402

log = logging.getLogger("preparar_evento")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--evento", required=True)
    ap.add_argument("--sin-viento", action="store_true")
    ap.add_argument("--sin-indices", action="store_true")
    ap.add_argument("--sin-meteo", action="store_true")
    ap.add_argument("--malla-viento", type=float, default=None)
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    ev = cfgmod.cargar_evento(a.evento)
    dom = cfgmod.cargar_dominio(ev["dominio"])
    modelo = cfgmod.cargar_modelo()
    g = pdm.grilla_dominio(dom)
    man: dict = {"evento": ev["id"], "dominio": dom["id"], "inicio_utc": ahora_utc(), "pasos": {}}
    t_all = time.time()

    def paso(nombre, fn):
        t = time.time()
        try:
            r = fn()
            man["pasos"][nombre] = {"estado": "ok", "segundos": round(time.time() - t, 1),
                                    "salida": {k: str(v) for k, v in r.items()} if isinstance(r, dict) else str(r)}
            return r
        except Exception as e:
            log.exception("paso %s falló", nombre)
            man["pasos"][nombre] = {"estado": "fallido", "segundos": round(time.time() - t, 1), "error": str(e)[:500]}
            return None

    anio_cob = int(ev.get("cobertura_anio", 2023))
    dominio = paso("dominio", lambda: pdm.preparar_todo_dominio(dom, sorted({anio_cob, 2021, 2022, 2023, 2024, 2025})))
    cic = paso("cicatriz_evento", lambda: {"cicatriz": pdm.preparar_cicatriz_evento(dom, ev)})
    # barreras lineales (modelo v2): producto por dominio, reutilizable; los anchos salen de escenarios/v3.1/modelos/modelo_v2.yaml
    try:
        m2 = cfgmod.cargar_modelo("modelo_v2")
    except FileNotFoundError:
        m2 = None
    if m2 and m2.get("barreras"):
        b = m2["barreras"]
        paso("barreras", lambda: {"barreras": pdm.preparar_barreras_enlaces(dom, b["ancho_m"], int(modelo["automata"]["vecindad"]),
                                                                            int(b.get("factor_fino", 4)), bool(b.get("excluir_duplicados", True)))})

    meteo = None
    if not a.sin_meteo:
        from incendios_sl.meteorology.openmeteo import adquirir, ConfigMeteo
        gv = pdm.grilla_viento(dom)
        cfg_m = ConfigMeteo(modelo=ev["meteorologia"].get("modelo", "ecmwf_ifs"))
        meteo = paso("meteorologia", lambda: {k: v for k, v in adquirir(gv, ev["meteorologia"]["inicio_utc"], ev["meteorologia"]["fin_utc"],
                                                                           cfg_m, etiqueta=ev["id"]).items() if k in ("csv", "parquet", "json", "dominio_csv")})

    idx = None
    if not a.sin_indices:
        from incendios_sl.remote_sensing.gee_indices import obtener_indices
        gi = pdm.grilla_indices(dom)
        idx = paso("indices", lambda: obtener_indices(ev, gi, escala=20.0))
    if idx is None and ev.get("indices", {}).get("respaldo_evento"):
        # Respaldo documentado: reutilizar el compuesto NDVI/NDMI de otro evento del mismo dominio y estación
        # cuando GEE no está disponible (la procedencia de los combustibles registra la ruta reutilizada).
        otro = str(ev["indices"]["respaldo_evento"])
        d_otro = cfgmod.dir_procesados() / "indices" / otro
        cand = {k: d_otro / f"{k}_{otro}.tif" for k in ("ndvi", "ndmi", "n_obs")}
        if all(p.exists() for p in cand.values()):
            log.warning("índices: se reutiliza el compuesto de %s como respaldo (HIPÓTESIS documentada en la ficha)", otro)
            idx = paso("indices_respaldo", lambda: cand | {"respaldo_de": otro})
        else:
            log.error("índices: respaldo %s no disponible en %s", otro, d_otro)

    if not a.sin_viento and dominio:
        from incendios_sl.wind.windninja import WindNinja
        vcfg = modelo["viento"]
        malla = a.malla_viento or float(vcfg["malla_m"])
        wn = WindNinja(dominio["dem_viento"], malla_m=malla, vegetacion=vcfg["vegetacion"], altura_salida_m=vcfg["altura_salida_m"])
        paso("viento", lambda: {"biblioteca": wn.biblioteca_unitaria(paso_deg=float(vcfg["bins_direccion_deg"]), etiqueta=dom["id"])})

    if dominio:
        from incendios_sl.fuels.tabla import generar_tabla
        from incendios_sl.fuels.clasificacion import generar_mapa_combustibles
        paso("tabla_combustibles", lambda: {"tabla": str(cfgmod.dir_derivados("combustibles") / "tabla_combustibles_v1.csv")} if generar_tabla() is not None else {})
        p_ndvi = Path(idx["ndvi"]) if idx else None
        p_ndmi = Path(idx["ndmi"]) if idx else None
        paso("combustibles", lambda: generar_mapa_combustibles(dom, ev, g, dominio["cobertura"][anio_cob], p_ndvi, p_ndmi))

    if meteo:
        import pandas as pd
        from incendios_sl.fuels.humedad import serie_humedad
        def _hum():
            dmn = pd.read_csv(meteo["dominio_csv"], parse_dates=["time_utc"])
            h = serie_humedad(dmn, modelo["humedad"])
            out = cfgmod.dir_derivados("eventos", ev["id"]) / f"humedad_muerto_{ev['id']}.csv"
            h.to_csv(out, index=False)
            return {"humedad_csv": out, "m_1h_min": float(h.m_1h_pct.min()), "m_1h_max": float(h.m_1h_pct.max())}
        paso("humedad", _hum)

    man["segundos_total"] = round(time.time() - t_all, 1)
    out = cfgmod.dir_derivados("eventos", ev["id"]) / f"manifiesto_{ev['id']}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(man, f, indent=2, ensure_ascii=False, default=str)
    fallidos = [k for k, v in man["pasos"].items() if v["estado"] != "ok"]
    log.info("manifiesto: %s | pasos fallidos: %s | %.0f s", out, fallidos or "ninguno", man["segundos_total"])
    return 1 if fallidos else 0


if __name__ == "__main__":
    sys.exit(main())
