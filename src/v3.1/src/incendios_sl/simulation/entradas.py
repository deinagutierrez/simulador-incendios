"""Carga de las entradas de simulación desde los productos de la Etapa 3 para un evento configurado."""
from __future__ import annotations

import glob
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .. import config as cfgmod
from ..data.preparar_dominio import grilla_dominio
from ..fuels.humedad import lfmc_desde_ndmi
from ..fuels.tabla import cargar_tabla
from ..grilla import Grilla, leer_raster
from ..wind.windninja import BibliotecaViento
from .motor import EntradasSimulacion, ConfigSimulacion

log = logging.getLogger(__name__)


def ruta_producto(patron: str) -> Path:
    c = sorted(glob.glob(patron))
    if not c:
        partes = sorted(glob.glob(patron + ".part*"))
        if partes:  # archivo dividido para GitHub: se une una vez y queda en disco
            return cfgmod.unir_partes(Path(partes[0]).with_suffix(""))

        raise FileNotFoundError(f"no existe el producto {patron}; ejecute scripts/preparar_evento.py")
    return Path(c[-1])


# parches del YAML del modelo para elegir la parametrización del combate (API, web y ablación; docs/13)
_LOCAL = {"despacho": {"modo": "snmf"}, "retardo_modo": "vial", "aereo_auto": {"activo": True}}
PARCHES_DESPACHO: dict[str, dict[str, Any] | None] = {
    "auto": None,                                                                          # lo que diga el YAML
    "global": {"contencion": {"despacho": {"modo": "fijo"}, "retardo_modo": "fijo", "aereo_auto": {"activo": False}, "usar_ficha": False}},  # docs/10
    "local": {"contencion": _LOCAL | {"usar_ficha": True}},                               # SNMF + cuarteles y medios aéreos de la ficha
    "pronostico": {"contencion": _LOCAL | {"usar_ficha": False}},                         # SNMF sin ficha: cuartel más cercano, aéreos sorteados
}


def fusionar(base: dict[str, Any], parche: dict[str, Any] | None) -> dict[str, Any]:
    """Copia de `base` con `parche` aplicado recursivamente (variantes de ablación sin duplicar el YAML del modelo)."""
    out = dict(base)
    for k, v in (parche or {}).items():
        out[k] = fusionar(out.get(k) or {}, v) if isinstance(v, dict) else v
    return out


def region_despacho(despacho: dict[str, Any], departamento: str | None) -> str:
    """Régimen territorial de la respuesta (docs/13 §2.1) según el departamento de la ignición."""
    d = (departamento or "").upper()
    for nombre, r in (despacho.get("regiones") or {}).items():
        if d and d in [x.upper() for x in r.get("departamentos", [])]:
            return nombre
    return str(despacho.get("region_defecto", "serrano"))


def departamento_de(dom: dict[str, Any], lon: float, lat: float) -> str | None:
    p = (dom.get("combate") or {}).get("departamentos")
    if not p or not cfgmod.ruta(p).exists():
        return None
    import geopandas as gpd
    from shapely.geometry import Point
    dep = gpd.read_file(cfgmod.ruta(p)).to_crs(4326)
    hit = dep[dep.contains(Point(lon, lat))]
    return str(hit["departamento"].iloc[0]) if len(hit) else None


def config_v2(mod: dict[str, Any], ev: dict[str, Any], t0: pd.Timestamp, barreras: bool | None = None, contencion: bool | None = None,
              region: str | None = None) -> dict[str, Any]:
    """Campos de ConfigSimulacion del modelo v2 (docs/10) a partir del YAML del modelo y de la ficha del evento.
    `barreras`/`contencion` = None respetan `activo` del YAML; True/False lo fuerzan (ablación). Con `contencion.usar_ficha:
    false` se ignora el bloque `combate:` de la ficha (modo pronóstico: despacho y medios aéreos sólo del modelo, docs/13)."""
    out: dict[str, Any] = {}
    inten = mod.get("intensidad", {})
    out["longitud_llama_a"] = float(inten.get("longitud_llama_a", 0.0775)); out["longitud_llama_b"] = float(inten.get("longitud_llama_b", 0.46))
    b = mod.get("barreras", {})
    out["barreras_activo"] = bool(b.get("activo", False)) if barreras is None else bool(barreras)
    cr = b.get("cruce", {})
    out["cruce_modo"] = str(cr.get("modo", "probabilistico")); out["cruce_lambda"] = float(cr.get("lambda", 1.0)); out["cruce_beta"] = float(cr.get("beta", 4.0))
    out["semilla"] = int(b.get("semilla", 20261015))
    c = mod.get("contencion", {})
    out["contencion_activo"] = bool(c.get("activo", False)) if contencion is None else bool(contencion)
    out["contencion_retardo_h"] = float(c.get("retardo_h", 2.0)); out["tasa_linea_m_h"] = float(c.get("tasa_linea_m_h", 300.0))
    out["contencion_inicio_exacto"] = bool(c.get("inicio_exacto", False))
    out["costo_celda_m"] = float(c.get("costo_celda_m", 30.0)); out["prioridad"] = str(c.get("prioridad", "flancos"))
    out["acumular_max_h"] = float(c.get("acumular_max_h", 1.0))
    out["intensidad_sostener_kw_m"] = float(c.get("intensidad_sostener_kw_m", 1700.0)); out["intensidad_sostener_aereo_kw_m"] = float(c.get("intensidad_sostener_aereo_kw_m", 3500.0))
    out["intensidad_escape_kw_m"] = float(c.get("intensidad_escape_kw_m", 3500.0)); out["p_escape_hora"] = float(c.get("p_escape_hora", 0.5))
    comb = (ev.get("combate", {}) or {}) if c.get("usar_ficha", True) else {}
    # despacho local (docs/13)
    dsp = c.get("despacho", {}) or {}
    out["despacho_modo"] = str(dsp.get("modo", "fijo")); out["despacho_kappa"] = float(dsp.get("kappa", 1.0))
    out["despacho_tasa_max_m_h"] = float(dsp.get("tasa_max_m_h", 20000.0))
    kt = dsp.get("kappa_tamano", {}) or {}
    out["despacho_kappa_quiebre_ha"] = float(kt.get("quiebre_ha", float("inf"))); out["despacho_kappa_gamma"] = float(kt.get("gamma", 0.0))
    out["despacho_kappa_min"] = float(kt.get("minimo", 1.0))
    reg = (dsp.get("regiones") or {}).get(region or str(dsp.get("region_defecto", "serrano")), {})
    out["despacho_a"] = float(reg.get("a", 17.3)); out["despacho_b"] = float(reg.get("b", 0.36))
    ae = c.get("aereo_auto", {}) or {}
    # medios aéreos observados en la ficha (aunque la lista esté vacía: el SNMF no registró ninguno) desactivan el sorteo
    out["aereo_auto"] = bool(ae.get("activo", False)) and "aereo" not in comb
    out["aereo_umbrales_ha"] = tuple(float(x) for x in ae.get("umbrales_ha", (10, 100, 1000, 10000)))
    out["aereo_prob_clase"] = tuple(float(x) for x in ae.get("prob_clase", (0.014, 0.103, 0.148, 0.259, 0.40)))
    out["aereo_demora_h"] = float(ae.get("demora_h", 24.0)); out["aereo_horas_vuelo_utc"] = tuple(float(x) for x in ae.get("horas_vuelo_utc", (11, 22)))
    if comb.get("inicio_utc"):
        out["contencion_inicio_s"] = max(0.0, (pd.Timestamp(comb["inicio_utc"]) - t0).total_seconds())
    if comb.get("bomberos"):
        out["tasa_linea_m_h"] = float(comb["bomberos"]) * float(c.get("m_h_por_bombero", 20.0))
    if comb.get("tasa_linea_m_h"):
        out["tasa_linea_m_h"] = float(comb["tasa_linea_m_h"])
    out["aereo_intervalos_s"] = [((pd.Timestamp(a) - t0).total_seconds(), (pd.Timestamp(b_) - t0).total_seconds()) for a, b_ in (comb.get("aereo") or [])]
    # humedad de extinción del muerto por clase (docs/11; sustituye a la del análogo de Scott & Burgan)
    out["mx_clase"] = {int(k): float(v) for k, v in (mod.get("humedad", {}).get("mx_muerto_pct_clase") or {}).items()}
    return out


def inicio_combate_vial(dom: dict[str, Any], cont: dict[str, Any], ev: dict[str, Any], puntos: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Retardo del ataque inicial = aviso + despacho + viaje por la red vial desde el cuartel más cercano a la ignición
    (entre los declarados en `combate.cuarteles_id` de la ficha, si hay). None si falta el producto de arribo."""
    from ..data.arribo import tiempo_arribo
    p = cfgmod.dir_derivados("infraestructura") / f"arribo_{dom['id']}.npz"
    if not p.exists():
        log.warning("retardo vial: falta %s (ejecute scripts/preparar_arribo.py); se usa retardo_h", p)
        return None
    arr = cont.get("arribo", {}) or {}
    ids = ((ev.get("combate") or {}).get("cuarteles_id")) or None
    r = tiempo_arribo(p, [(float(q["lon"]), float(q["lat"])) for q in puntos], ids)
    if not np.isfinite(r["t_viaje_h"]):
        log.warning("retardo vial: ignición fuera del alcance de los cuarteles; se usa retardo_h"); return None
    r["retardo_h"] = float(arr.get("t_aviso_h", 0.5)) + float(arr.get("t_despacho_h", 0.25)) + r["t_viaje_h"]
    log.info("retardo vial: %.2f h (viaje %.2f h desde %s)", r["retardo_h"], r["t_viaje_h"], r["cuartel"])
    return r


def viento_por_fuente(fuente: str, id_evento: str, lib: BibliotecaViento, g: Grilla, meteo: pd.DataFrame):
    """Función (vel, dir_desde, hora=None) -> (U10, V10) a la grilla según `viento.fuente_horaria` (v3.1, docs/v3.1/04).
    Las fuentes que dependen de la hora llevan el atributo `por_hora` y el motor les pasa la hora UTC."""
    from ..wind.horario import FUENTES, CamposHorarios, PesosIDW, meteo_puntos, viento_idw
    from ..wind.windninja import remuestrear_uv

    def base(vel, d, hora=None, _lib=lib, _g=g):
        U, V = _lib.campo(vel, d)
        return _lib.a_grilla(U, V, _g)
    if fuente not in FUENTES:
        raise ValueError(f"viento.fuente_horaria {fuente!r} desconocida; opciones: {', '.join(FUENTES)}")
    if fuente == "biblioteca":
        return base
    if fuente == "escalar":   # el motor lee wind_speed_10m_vectorial: se reemplaza por el promedio escalar
        meteo["wind_speed_10m_vectorial"] = meteo["wind_speed_10m"]
        log.info("viento: velocidad = promedio escalar de los puntos IFS")
        return base
    if fuente == "idw_puntos":
        pp, pts = meteo_puntos(id_evento)
        pesos = PesosIDW(lib, pts)
        tabla = {h: (x.set_index("punto_id").loc[pesos.ids, "wind_speed_10m"].to_numpy(), x.set_index("punto_id").loc[pesos.ids, "wind_direction_10m"].to_numpy())
                 for h, x in pp.groupby("time_utc")}

        def idw(vel, d, hora=None, _lib=lib, _g=g):
            if hora is None or pd.Timestamp(hora) not in tabla:
                return base(vel, d)
            U, V = viento_idw(_lib, pesos, *tabla[pd.Timestamp(hora)])
            return _lib.a_grilla(U, V, _g)
        idw.por_hora = True
        log.info("viento: 16 puntos IFS interpolados (IDW) × biblioteca")
        return idw
    campos = CamposHorarios(id_evento, fuente)
    faltan = {"n": 0}

    def horario(vel, d, hora=None, _lib=lib, _g=g):
        c = campos.campo(pd.Timestamp(hora)) if hora is not None else None
        if c is None:
            faltan["n"] += 1
            return base(vel, d)
        return remuestrear_uv(c[0], c[1], campos.grilla, _g)
    horario.por_hora = True; horario.faltan = faltan
    log.info("viento: campos WindNinja horarios %s (%d horas)", fuente, len(campos.horas))
    return horario


def cargar_entradas_evento(id_evento: str, hipotesis_ignicion: int = 0, k_clase: dict[int, float] | None = None,
                           sin_viento: bool = False, factor_waf: float = 1.0, k_global: float | None = None, ignicion: str = "snmf",
                           modelo: str = "modelo_v1", barreras: bool | None = None, contencion: bool | None = None,
                           extra_cfg: dict[str, Any] | None = None, parche_modelo: dict[str, Any] | None = None
                           ) -> tuple[EntradasSimulacion, ConfigSimulacion, Grilla, dict[str, Any]]:
    ev = cfgmod.cargar_evento(id_evento); dom = cfgmod.cargar_dominio(ev["dominio"]); mod = fusionar(cfgmod.cargar_modelo(modelo), parche_modelo)
    g = grilla_dominio(dom)
    D = cfgmod.dir_entradas()
    mascara, _, _ = leer_raster(ruta_producto(str(D / "grilla" / f"mascara_dominio_{dom['id']}.tif")))
    pend, _, _ = leer_raster(ruta_producto(str(D / "dem" / f"pendiente_*_{dom['id']}.tif")))
    orient, _, _ = leer_raster(ruta_producto(str(D / "dem" / f"orientacion_*_{dom['id']}.tif")))
    clase, _, _ = leer_raster(ruta_producto(str(D / "combustibles" / id_evento / f"combustible_clase_{id_evento}.tif")))
    curado, _, _ = leer_raster(ruta_producto(str(D / "combustibles" / id_evento / f"combustible_curado_{id_evento}.tif")))
    ndmi, _, nd = leer_raster(ruta_producto(str(D / "combustibles" / id_evento / f"ndmi_30m_{id_evento}.tif")))
    ndmi = np.where(ndmi == nd, np.nan, ndmi).astype(np.float32)
    lfmc_h = lfmc_desde_ndmi(ndmi, mod["humedad"]["vivo_herbaceo"]); lfmc_l = lfmc_desde_ndmi(ndmi, mod["humedad"]["vivo_lenoso"])
    meteo = pd.read_csv(ruta_producto(str(D / "meteo" / f"{id_evento}_*_dominio.csv")), parse_dates=["time_utc"])
    hum = pd.read_csv(ruta_producto(str(D / "eventos" / id_evento / f"humedad_muerto_{id_evento}.csv")), parse_dates=["time_utc"])
    variante_hum = str(mod["humedad"].get("muerto_1h", "ffmc_horario_vanwagner_1977"))
    if variante_hum == "retardo_simard":
        if "m_1h_pct_rt" not in hum:
            raise FileNotFoundError(f"la serie de humedad de {id_evento} no tiene la variante de retardo; ejecute scripts/actualizar_humedad.py")
        hum = hum.assign(m_1h_pct=hum["m_1h_pct_rt"], m_10h_pct=hum["m_10h_pct_rt"], m_100h_pct=hum["m_100h_pct_rt"])
        log.info("humedad muerta: variante retardo_simard (docs/11)")
    tabla = cargar_tabla()
    viento = None; lib = None
    fuente_viento = "biblioteca"
    if not sin_viento:
        vcfg = mod["viento"]
        lib = BibliotecaViento(ruta_producto(str(D / "viento" / f"viento_unitario_{dom['id']}_{int(vcfg['malla_m'])}m_{vcfg['vegetacion']}_*.nc")))
        fuente_viento = str(vcfg.get("fuente_horaria", "biblioteca"))
        viento = viento_por_fuente(fuente_viento, id_evento, lib, g, meteo)
    # igniciones: puntos SNMF con la hipótesis horaria elegida
    t0 = pd.Timestamp(ev["inicio"]["hora_utc_hipotesis"][hipotesis_ignicion])
    t_fin = pd.Timestamp(ev["fin"]["fin_simulacion_utc"])
    ign = []
    ref_path = D / "eventos" / id_evento / f"cicatriz_referencia_{id_evento}.tif"
    ref = leer_raster(ref_path)[0] if ref_path.exists() else None
    if ignicion == "snmf":
        puntos = ev["ignicion"]["puntos"]
    else:
        alt = ev["ignicion_alternativas"][int(ignicion.replace("alt", ""))]
        puntos = alt["puntos"]; log.warning("ignición alternativa (HIPÓTESIS): %s", alt.get("fuente"))
    for p in puntos:
        r, c = g.lonlat_a_rc(p["lon"], p["lat"]); r, c = int(r), int(c)
        if not (g.dentro(r, c) and mascara[r, c] == 1 and clase[r, c] > 0):
            # HIPÓTESIS documentada: desplazar a la celda combustible más cercana (dentro de la cicatriz si existe)
            cand = (clase > 0) & (mascara == 1)
            if ref is not None and (ref == 1).any():
                cand &= (ref == 1)
            rr, cc = np.nonzero(cand)
            k = np.argmin((rr - r) ** 2 + (cc - c) ** 2)
            d = float(np.hypot(rr[k] - r, cc[k] - c) * g.res)
            log.warning("ignición %s en celda no combustible/fuera (%d,%d); desplazada %.0f m a (%d,%d)", p["nombre"], r, c, d, rr[k], cc[k])
            r, c = int(rr[k]), int(cc[k])
        ign.append((r, c, 0.0))
        log.info("ignición %s -> celda (%d,%d) clase %d", p["nombre"], r, c, clase[r, c])
    ac = mod["automata"]
    cont = mod.get("contencion", {}) or {}
    depto = departamento_de(dom, puntos[0]["lon"], puntos[0]["lat"]) if cont else None
    region = region_despacho(cont.get("despacho", {}) or {}, depto) if cont else None
    v2 = config_v2(mod, ev, t0, barreras, contencion, region)
    arribo = None
    if cont.get("retardo_modo", "fijo") == "vial" and "contencion_inicio_s" not in v2 and "contencion_retardo_h" not in (extra_cfg or {}):
        arribo = inicio_combate_vial(dom, cont, ev if cont.get("usar_ficha", True) else {}, puntos)
        if arribo is not None:
            v2["contencion_inicio_s"] = arribo["retardo_h"] * 3600.0
    v2 = v2 | (extra_cfg or {})
    cfg = ConfigSimulacion(vecindad=int(ac["vecindad"]), dt_s=float(ac["dt_s"]), ros_min_m_min=float(ac["ros_min_m_min"]),
                           horas_sin_propagacion_para_terminar=int(ac["horas_sin_propagacion_para_terminar"]),
                           k_clase={int(k): (float(v) if k_global is None else float(k_global)) for k, v in (k_clase or mod["propagacion"]["k_clase"]).items()},
                           factor_waf=float(factor_waf),
                           lluvia_24h_mm_extincion=float(mod["humedad"]["lluvia_24h_mm_extincion"]), **v2)
    barr = ancho = None; ruta_barreras = None
    if cfg.barreras_activo:
        from ..data.preparar_dominio import cargar_barreras_enlaces
        ruta_barreras = ruta_producto(str(D / "barreras" / f"barreras_enlaces_{dom['id']}.npz"))
        barr, ancho, _ = cargar_barreras_enlaces(ruta_barreras)
    ent = EntradasSimulacion(res_m=g.res, mascara=mascara, clase=clase, pendiente_deg=pend, orientacion_deg=orient, curado=curado,
                             lfmc_herb=lfmc_h, lfmc_lenoso=lfmc_l, tabla=tabla, meteo=meteo, humedad=hum, viento=viento, igniciones=ign,
                             t_inicio_utc=t0, t_fin_utc=t_fin, barreras=barr, ancho_barrera_m=ancho)
    meta = {"evento": ev["id"], "dominio": dom["id"], "hipotesis_ignicion": hipotesis_ignicion, "factor_waf": factor_waf, "k_global": k_global, "ignicion": ignicion, "puntos_ignicion": puntos,
            "evaluacion_utc": ev["fin"].get("evaluacion_utc", []), "referencia": ev["referencia_espacial"], "t_inicio_utc": str(t0), "t_fin_utc": str(t_fin),
            "modelo": mod, "modelo_nombre": modelo, "biblioteca_viento": str(lib.path) if lib else None, "barreras": str(ruta_barreras) if ruta_barreras else None,
            "combate": ev.get("combate"), "humedad_muerta": variante_hum, "fuente_viento": fuente_viento,
            "despacho": {"departamento": depto, "region": region, "arribo": arribo, "usar_ficha": bool(cont.get("usar_ficha", True))} if cont else None}
    return ent, cfg, g, meta
