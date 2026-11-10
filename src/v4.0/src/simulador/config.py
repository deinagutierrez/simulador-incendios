"""Configuración de una corrida (YAML) con valores por defecto documentados.

v4.0: los valores por defecto son los del modelo corregido (`escenarios/v4.0/modelos/modelo_v3.yaml`). El
comportamiento de V.4 tal como se entregó se reproduce con `escenarios/v4.0/modelos/sim_v4_original.yaml`, que
solo cambia los interruptores marcados "V.4 original" (docs/v4.0/14 y 15).
"""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

DEFAULTS = {
    "nombre": "corrida",
    "descripcion": "",
    "grilla": None,                 # {xmin, ymin, xmax, ymax} alineada a la grilla del dominio; null = dominio completo
    "t_inicio": None,               # ISO 8601 con huso; si es null se toma la primera ignición
    "duracion_h": 24,
    "dt_min": 2.0,
    "vecindad": 8,                  # 8 (Moore) o 16 (con saltos de caballo)
    "modo": "determinista",         # determinista | estocastico
    "semilla": 42,
    "ignicion": None,               # ruta a GeoJSON (id, hora_ignicion) o lista de {x, y | lon, lat, hora_ignicion}
    "meteo": None,                  # CSV estándar
    "combustible": None,            # GeoTIFF que reemplaza al del manifiesto (p. ej. pre-evento)
    "indices_mes_evento": None,     # GeoTIFF 2 bandas NDVI/NDMI ×10000
    "ndvi_verano": None,            # GeoTIFF 1 banda NDVI ×10000
    "modificador_combustible": None,  # GeoTIFF factor de carga (tratamientos de mitigación; 0 = cortafuego)
    "viento_externo": None,         # {u: ruta.tif, v: ruta.tif}
    "perimetro_observado": None,    # GeoJSON (casos de prueba)
    "focos": None,                  # GeoJSON de focos VIIRS
    "parametros": {
        "humedad": {},              # ver physics.humedad.ParametrosHumedad (método del muerto, EMC, fijas, viva, Mx por grupo)
        "viento": {},               # ver physics.viento.ParametrosViento: fuente serie | windninja (modelo_v3), biblioteca, factor_10m_20ft
        "limitar_viento": True,
        "limite_viento": "andrews_2013",  # andrews_2013 (U_eff ≤ 96,8·I_R^⅓) | rothermel_1972 (U ≤ 0,9·I_R, V.4 original) | ninguno
        "ignicion_delay_min": 0.0,  # minutos en estado IGNICION antes de propagar
        "credito_desde_activacion": True,   # P7: el crédito de una celda nueva cuenta desde llegada + retardo (false = V.4)
        "cfl": 0.9,                 # avance máximo del frente por sub-paso, en fracción de celda
        "dt_sub_min": 0.1,          # sub-paso mínimo (min)
        "radio_huygens_m": 300.0,   # distancia máxima al origen heredado antes de re-anclar la elipse
        # re-anclaje del origen heredado cuando la forma de la elipse cambió (rotación de viento, pendiente):
        # sin esto la elipse se redibuja hacia atrás en el tiempo (docs/v4.0/15, P3). null = V.4 original
        "huygens": {"tol_rumbo_deg": 15.0, "tol_e": 0.05},
        "extincion": "reversible",  # reversible (celdas con R = 0 quedan latentes) | definitiva (V.4 original)
        # factores de propagación (v3.0 `k_clase`/`k_global`/`factor_waf`), por familia S&B (GR, GS, SH, TU, TL, SB) o código
        "propagacion": {"k_global": 1.0, "k_grupo": {}, "k_codigo": {}, "factor_waf": 1.0},
        "caminos": {
            "umbral_llama_m": {"pavimentado": 2.0, "ripio": 1.5, "tierra": 1.0, "huella": 0.5, "cortafuego": 0.5},
            "factor_carga_por_ancho": True,   # carga × (1 − ancho/res)
        },
        # barreras lineales (v3.0 docs/10): cruce de caminos y cortafuegos según la longitud de llama
        "barreras": {
            "activo": True,
            "modo": "probabilistico",   # umbral_tipo (V.4 original: llama ≥ umbral del tipo) | umbral (L/W > λ) | probabilistico
            "llama": "direccional",     # direccional (L·(R(θ)/R_max)^0,46) | cabeza (V.4 original)
            "lambda": 1.0,              # L/W con P(cruce) = 0,5
            "beta": 4.0,                # pendiente de la logística P = 1/(1+exp(−β(L/W − λ)))
            "semilla": 20261015,        # sorteo por enlace y hora (hash, reproducible e independiente del orden)
            "normalizar": True,         # P = (σ(x)−σ(0))/(1−σ(0)): P(L=0) = 0 (false = logística de v3.0, piso de 1,8 %/h)
            "extra": None,              # GeoJSON de líneas (cortafuegos, líneas de control) con `ancho_m` (y `tipo`)
        },
        "viviendas_buffer_m": 100.0,
        "spotting": {"activo": False, "intensidad_ref_kw_m": 3000.0, "p_max": 0.05,
                     "dist_mediana_m": 150.0, "sigma_log": 0.6, "max_por_paso": 20,
                     "por_unidad_tiempo": True},   # P8: p_max por paso nominal Δt, ajustada al sub-paso (false = V.4)
        "estocastico": {"factor_p": 1.0},
        # L03 (protocolo v1.3 §2.4): dotaciones que llegan en `llegadas_min` (minutos desde t0) y construyen línea
        "supresion": {"activo": False, "llegadas_min": [], "produccion_linea_m_h": 500.0, "llama_max_m": 2.4,
                      "intensidad": "avance"},     # avance (V.4: llama en la dirección origen → celda) | v3 (máximo hacia las vecinas)
        # contención por combate (v3.0 docs/10 y 13): línea con anclaje y flancos, despacho SNMF, escapes, medios aéreos
        "contencion": {
            "activo": False,
            "inicio_min": None,             # minutos desde t0 (lo calcula la capa de escenarios: ficha, retardo vial o fijo)
            "retardo_h": 2.0,               # si inicio_min es null
            "despacho": "fijo",             # fijo (tasa_linea_m_h) | snmf (tasa escalonada con la superficie)
            "tasa_linea_m_h": 1000.0,
            "snmf": {"a": 17.3, "b": 0.36, "kappa": 10.0, "tasa_max_m_h": 20000.0,
                     "kappa_quiebre_ha": 3000.0, "kappa_gamma": 0.62, "kappa_min": 1.0},
            "costo_celda_m": None,          # metros de línea por celda (null = resolución de la grilla)
            "seleccion": "contigua",        # contigua (línea con anclaje, v3.0) | menor_llama (L03)
            "intensidad": "v3",             # v3 (máximo I_B·P(cruce) hacia las vecinas pendientes) | avance (dirección origen → celda)
            "prioridad": "flancos",         # flancos | cabeza
            "acumular_max_h": 8.0,          # horas de producción que se pueden acumular (1 = sin línea indirecta)
            "intensidad_sostener_kw_m": 1700.0,
            "intensidad_sostener_aereo_kw_m": 3500.0,
            "intensidad_escape_kw_m": 3500.0,
            "p_escape_hora": 0.5,
            "aereo_intervalos": [],         # [[inicio ISO, fin ISO], …] con medio aéreo activo (ficha del evento)
            "aereo_auto": {"activo": False, "umbrales_ha": [10, 100, 1000, 10000],
                           "prob_clase": [0.014, 0.103, 0.148, 0.259, 0.40], "demora_h": 24, "horas_vuelo_utc": [11, 22]},
            "semilla": 20261015,
        },
        # parada anticipada: N horas sin avance (null = nunca) y fin cuando todo el frente quedó contenido. Se suspende
        # mientras puede haber escapes (escapes: v3 | potencial | ignorar), pavesas o celdas latentes (hasta latentes_max_h).
        # superficie_observada: fin en el sub-paso en que la superficie afectada iguala o supera la del perímetro observado
        # (o superficie_objetivo_ha si se da); no se suspende. Apagada por defecto: la enciende la corrida (`parar_en_cicatriz`)
        "parada": {"horas_sin_avance": 12, "contenido": True, "escapes": "v3", "latentes_max_h": 24,
                   "superficie_observada": False, "superficie_objetivo_ha": None},
    },
    "salidas": {"png": True, "gif": True, "geotiff": True, "geojson": True, "json": True,
                "descripcion": True, "dpi": 110, "recuadro": None,    # recuadro: [xmin, ymin, xmax, ymax] del zoom
                "png_cada_h": 1},                                      # mapa cada N horas (JSON y descripción siempre cada hora)
    "ensemble": {"n": 0},
}


def fusionar(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = fusionar(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def cargar_config(ruta: Path) -> dict:
    ruta = Path(ruta)
    d = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
    cfg = fusionar(DEFAULTS, d)
    cfg["_ruta"] = str(ruta)
    cfg["_dir"] = str(ruta.parent)
    return cfg


def resolver_valor(v, cfg: dict, raiz: Path | None = None, clave: str = "") -> Path | None:
    """Ruta de un escenario: relativa a la carpeta del YAML; debe quedar dentro del repositorio (o de `raiz`)."""
    from .rutas import raices_permitidas
    if not v or not isinstance(v, (str, Path)):
        return None
    p = Path(v)
    if not p.is_absolute():
        p = (Path(cfg.get("_dir") or ".") / p).resolve()
    permitidas = raices_permitidas() + ([Path(raiz).resolve()] if raiz else [])
    if not any(b == p or b in p.parents for b in permitidas):
        raise ValueError(f"La ruta '{v}' ({clave}) queda fuera del repositorio {permitidas[0]}")
    return p


def resolver(cfg: dict, clave: str, raiz: Path | None = None) -> Path | None:
    """Rutas relativas se resuelven respecto de la carpeta del YAML; nunca se admiten rutas fuera del repositorio."""
    return resolver_valor(cfg.get(clave), cfg, raiz, clave)
