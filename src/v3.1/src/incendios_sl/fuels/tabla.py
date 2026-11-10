"""Tabla de clases de combustible locales provisionales (v1) con parámetros físicos por analogía.

Los parámetros de los modelos análogos se leen de la tabla de Scott & Burgan (2005, RMRS-GTR-153) tal como
la distribuye el paquete `firebench` (data_ScottandBurgan40.csv). Ninguna clase está validada en campo:
cada fila lleva etiqueta de origen y un factor k_clase a calibrar.

Unidades de la tabla S&B: cargas en t/acre (short ton), SAV en 1/ft, profundidad en ft, Mx en %, calor en BTU/lb.
Se convierten a SI (kg/m², 1/m, m, %, kJ/kg) para el simulador.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .. import config as cfgmod
from ..procedencia import escribir_procedencia

log = logging.getLogger(__name__)

TON_ACRE_A_KG_M2 = 0.224170   # 1 short ton/acre = 2000 lb / 4046.856 m² × 0.45359237 kg/lb
FT_A_M = 0.3048
BTU_LB_A_KJ_KG = 2.326

# Clases locales provisionales (diseño §7.2). 'coberturas' = códigos MapBiomas Col. 3.
CLASES_V1: list[dict[str, Any]] = [
    {"clase": 0, "nombre": "no_combustible", "descripcion": "Agua, urbano, suelo desnudo/roca, no observado",
     "coberturas": [24, 25, 33, 34, 27], "analogo_sb": "NB", "etiqueta": "BIBLIO (no combustible)"},
    {"clase": 1, "nombre": "pastizal_natural", "descripcion": "Herbáceas naturales (pastizal serrano / llanura)",
     "coberturas": [12, 11], "analogo_sb": "GR2", "etiqueta": "HIPOTESIS analogia S&B"},
    {"clase": 2, "nombre": "pastura_cultivo", "descripcion": "Pasturas implantadas y cultivos (rastrojo en temporada seca)",
     "coberturas": [15, 19, 18, 36, 21], "analogo_sb": "GR1", "etiqueta": "HIPOTESIS analogia S&B"},
    {"clase": 3, "nombre": "arbustal_abierto", "descripcion": "Arbustal abierto y mosaico arbustivo-herbáceo",
     "coberturas": [77, 63], "analogo_sb": "GS2", "etiqueta": "HIPOTESIS analogia S&B"},
    {"clase": 4, "nombre": "arbustal_cerrado", "descripcion": "Arbustal cerrado",
     "coberturas": [66], "analogo_sb": "SH2", "etiqueta": "HIPOTESIS analogia S&B"},
    {"clase": 5, "nombre": "bosque_abierto", "descripcion": "Bosque abierto (Chaco serrano / Espinal) con sotobosque herbáceo-arbustivo",
     "coberturas": [4], "analogo_sb": "GS2", "etiqueta": "HIPOTESIS analogia S&B (alternativa TU1)"},
    {"clase": 6, "nombre": "bosque_cerrado", "descripcion": "Bosque cerrado y bosque inundable",
     "coberturas": [3, 6], "analogo_sb": "TU1", "etiqueta": "HIPOTESIS analogia S&B (alternativa TL2)"},
    {"clase": 7, "nombre": "plantacion", "descripcion": "Silvicultura / plantación forestal",
     "coberturas": [9], "analogo_sb": "TL2", "etiqueta": "HIPOTESIS analogia S&B"},
]

# Factor de abrigo del dosel sobre el viento a media llama (multiplica al WAF sin abrigo). HIPOTESIS.
FACTOR_DOSEL = {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 0.8, 5: 0.6, 6: 0.4, 7: 0.4}


def _tabla_sb() -> pd.DataFrame:
    import firebench
    p = Path(firebench.__file__).parent / "resources" / "data" / "fuel_models" / "data_ScottandBurgan40.csv"
    df = pd.read_csv(p)
    df["_origen"] = str(p)
    return df


def waf_sin_abrigo_baughman(altura_lecho_m: np.ndarray | float, altura_viento_m: float = 10.0) -> np.ndarray:
    """Factor de ajuste del viento (sin abrigo) de Baughman & Albini (1980) generalizado a una altura de
    entrada arbitraria (Andrews 2012, RMRS-GTR-266): perfil logarítmico con d0 = 0.64 H y z0 = 0.13 H,
    promediado entre la cima del lecho y 2H (viento a media llama). Devuelve U_mf / U(altura_viento)."""
    H = np.asarray(altura_lecho_m, dtype=float)
    H = np.where(H <= 0, 0.01, H)
    d0 = 0.64 * H; z0 = 0.13 * H
    # El viento de referencia está a `altura_viento_m` SOBRE LA VEGETACIÓN (convención WindNinja y 20-ft),
    # es decir a z = altura + H sobre el suelo; el perfil log usa (z - d0)/z0 -> (altura + 0.36 H)/(0.13 H).
    u_ref = np.log((altura_viento_m + H - d0) / z0)
    # velocidad media entre z = H y z = 2H: (1/H) * integral de ln((z-d0)/z0) dz = (z0/H) * [b(ln b - 1) - a(ln a - 1)]
    a = (H - d0) / z0; b = (2 * H - d0) / z0
    integral = (b * (np.log(b) - 1) - a * (np.log(a) - 1)) * z0 / H   # = 1.83 para todo H (Baughman & Albini 1980)
    return integral / u_ref


def generar_tabla(out: Path | None = None) -> pd.DataFrame:
    sb = _tabla_sb().set_index("fuel_model_code")
    filas = []
    for c in CLASES_V1:
        f = dict(c)
        f["coberturas"] = ",".join(map(str, c["coberturas"]))
        if c["analogo_sb"] == "NB":
            f.update({"w0_1h_kg_m2": 0, "w0_10h_kg_m2": 0, "w0_100h_kg_m2": 0, "w0_herb_kg_m2": 0, "w0_lenoso_kg_m2": 0,
                      "sav_1h_1_m": 0, "sav_herb_1_m": 0, "sav_lenoso_1_m": 0, "profundidad_m": 0, "mx_muerto_pct": 0,
                      "calor_kJ_kg": 0, "dinamico": False, "waf_sin_abrigo_10m": 0})
        else:
            r = sb.loc[c["analogo_sb"]]
            f.update({
                "w0_1h_kg_m2": r.fuel_load_1h * TON_ACRE_A_KG_M2, "w0_10h_kg_m2": r.fuel_load_10h * TON_ACRE_A_KG_M2,
                "w0_100h_kg_m2": r.fuel_load_100h * TON_ACRE_A_KG_M2, "w0_herb_kg_m2": r.fuel_load_live_herb * TON_ACRE_A_KG_M2,
                "w0_lenoso_kg_m2": r.fuel_load_live_woody * TON_ACRE_A_KG_M2,
                "sav_1h_1_m": r.sav_ratio_dead_1h / FT_A_M, "sav_herb_1_m": (0 if r.sav_ratio_live_herb == 9999 else r.sav_ratio_live_herb / FT_A_M),
                "sav_lenoso_1_m": (0 if r.sav_ratio_live_woody == 9999 else r.sav_ratio_live_woody / FT_A_M),
                "profundidad_m": r.fuel_bed_depth * FT_A_M, "mx_muerto_pct": r.dead_fuel_extinction_moisture,
                "calor_kJ_kg": r.heat_content * BTU_LB_A_KJ_KG, "dinamico": r.fuel_model_type == "dynamic",
                "waf_sin_abrigo_10m": float(waf_sin_abrigo_baughman(r.fuel_bed_depth * FT_A_M, 10.0)),
            })
        f["factor_dosel"] = FACTOR_DOSEL[c["clase"]]
        f["waf_efectivo_10m"] = f["waf_sin_abrigo_10m"] * f["factor_dosel"]
        f["k_clase"] = 1.0
        f["fuente_parametros"] = "Scott & Burgan 2005 RMRS-GTR-153 (tabla distribuida en firebench)" if c["analogo_sb"] != "NB" else "-"
        f["incertidumbre"] = "alta: analogía sin medición local de carga ni estructura" if c["analogo_sb"] != "NB" else "baja"
        f["limitaciones"] = "cargas, SAV, profundidad y Mx del modelo análogo; k_clase a calibrar con el evento 2024"
        filas.append(f)
    df = pd.DataFrame(filas)
    out = out or (cfgmod.dir_derivados("combustibles") / "tabla_combustibles_v1.csv")
    df.to_csv(out, index=False, encoding="utf-8")
    escribir_procedencia(out, "clases locales v1 + parámetros S&B 2005 por analogía", {"version": "v1"},
                         [sb["_origen"].iloc[0]], extra={"nota": "WAF sin abrigo: Baughman & Albini 1980 generalizado (Andrews 2012); factor_dosel = HIPOTESIS"})
    log.info("tabla de combustibles escrita: %s", out)
    return df


def cargar_tabla() -> pd.DataFrame:
    p = cfgmod.dir_derivados("combustibles") / "tabla_combustibles_v1.csv"
    return pd.read_csv(p) if p.exists() else generar_tabla(p)
