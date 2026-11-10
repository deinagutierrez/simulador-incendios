"""Generación del mapa de modelos Scott & Burgan a partir de MapBiomas + MDT + NDVI/NDMI de verano.

Misma lógica que `Dominio_LasLagunas_30m/Combustibles/generar_modelos_combustible.py` (reglas 1–4 de su
README), pero parametrizada para reconstruir el combustible **pre-evento** de un caso (regla 3.3):
cobertura del año anterior al incendio + NDVI/NDMI del verano anterior al incendio, con los
terciles ya calculados (`umbrales_ndvi.csv`) para no cambiar la clasificación respecto de los mapas
anuales.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

COTA_ALTURA = 1300
UMBRAL_NDMI_HUMEDO = 0.15
NODATA = -9999
COD = {"NB1": 91, "NB3": 93, "NB8": 98, "NB9": 99, "GR1": 101, "GR2": 102, "GR3": 103, "GR4": 104, "GR6": 106, "GR7": 107,
       "GS1": 121, "GS2": 122, "SH2": 142, "SH5": 145, "SH7": 147, "TU1": 161, "TU5": 165, "TL8": 188}
TABLA = {
    3: ("TU1", "TU5", "TU5"), 4: ("TU1", "GS2", "TU5"), 6: ("TU1", "TU1", "TU1"), 9: ("TL8", "TL8", "TL8"),
    11: ("GR3", "GR3", "GR6"), 12: ("GR1", "GR2", "GR4"), "12_alt": ("GR2", "GR4", "GR7"), 15: ("GR2", "GR4", "GR7"),
    18: ("NB3", "NB3", "NB3"), 19: ("NB3", "NB3", "NB3"), 21: ("GR1", "GR2", "GS1"), 24: ("NB1", "NB1", "NB1"),
    25: ("NB9", "NB9", "NB9"), 33: ("NB8", "NB8", "NB8"), 36: ("NB3", "NB3", "NB3"), 63: ("GS1", "GS2", "GS2"),
    66: ("SH2", "SH5", "SH7"), 73: ("GR6", "GR6", "GR6"), 77: ("GS2", "SH2", "SH5"),
}
LENOSAS = (3, 4, 6, 9, 66, 77)
HERBACEAS = (12, "12_alt", 15, 63)


def ndvi_estructural_anomalia(lc: np.ndarray, ndvi_verano: np.ndarray, umbrales: pd.DataFrame,
                              clases=LENOSAS, min_celdas: int = 500) -> tuple[np.ndarray, dict]:
    """Regla 3.3b (v4.0, docs/v4.0/17): NDVI estructural de las clases leñosas sin la anomalía interanual de verdor.

    Los terciles de `umbrales_ndvi.csv` son fijos, pero el NDVI de un solo verano lleva la señal del año: en el verano
    seco 2021/22 la mediana de los bosques estables bajó 0,10 y el 69 % cayó en el tercil bajo (TU1), contra 15 % en 2024
    (en invierno las dos fuentes coinciden). La estructura leñosa no cambia en un año: para cada clase leñosa se resta
    la diferencia entre la mediana del dominio en ese verano y la mediana de referencia implícita en sus terciles,
    (p33 + p67)/2. Las herbáceas conservan el NDVI del año (la carga de pasto sí responde a la sequía).
    Devuelve (ndvi estructural, {clase: corrimiento})."""
    umb = {str(r.clave): (float(r.ndvi_p33), float(r.ndvi_p67)) for r in umbrales.itertuples()}
    out = np.array(ndvi_verano, dtype="float32", copy=True)
    corr = {}
    for clase in clases:
        if str(clase) not in umb:
            continue
        m = (lc == clase) & np.isfinite(ndvi_verano)
        if m.sum() < min_celdas:
            continue
        ref = 0.5 * sum(umb[str(clase)])
        d = float(ref - np.median(ndvi_verano[m]))
        out[lc == clase] += d
        corr[clase] = round(d, 4)
    return out, corr


def generar(lc: np.ndarray, dem: np.ndarray, ndvi_verano: np.ndarray, ndmi_verano: np.ndarray, umbrales: pd.DataFrame,
            ndvi_estructural: np.ndarray | None = None, pasturas_gr1: bool = False) -> np.ndarray:
    """lc: MapBiomas Col.3 (uint8, 0 = nodata); dem: m; ndvi/ndmi de verano (float, NaN sin dato).
    ndvi_estructural: NDVI para las clases leñosas (si None, se usa ndvi_verano).
    pasturas_gr1 (regla 3.3c, docs/v4.0/24): las pasturas (MapBiomas 15) pasan a GR1 en todos los terciles y también con NDMI
    húmedo (sin GR6): pasto pastoreado, corto y escaso; en los 10 eventos el fuego las evitó (dentro/anillo 0,10)."""
    if ndvi_estructural is None:
        ndvi_estructural = ndvi_verano
    umb = {str(r.clave): (float(r.ndvi_p33), float(r.ndvi_p67)) for r in umbrales.itertuples()}
    out = np.full(lc.shape, NODATA, dtype="int16")
    claves = np.where((lc == 12) & (dem >= COTA_ALTURA), -12, lc.astype("int16"))
    for clave, modelos in TABLA.items():
        m = claves == (-12 if clave == "12_alt" else clave)
        if not m.any():
            continue
        p33, p67 = umb.get(str(clave), (np.inf, np.inf))
        v = ndvi_estructural if clave in LENOSAS else ndvi_verano
        nivel = np.where(v < p33, 0, np.where(v < p67, 1, 2))
        nivel = np.where(np.isnan(v), 1, nivel)
        for i, sb in enumerate(modelos):
            out[m & (nivel == i)] = COD[sb]
        if clave in HERBACEAS:
            out[m & (ndmi_verano > UMBRAL_NDMI_HUMEDO)] = COD["GR6"]
    if pasturas_gr1:
        out[claves == 15] = COD["GR1"]
    return out
