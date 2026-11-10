"""Preparación de datos del simulador: copia los insumos a `datos/`, normaliza vectores, arma los casos de
prueba y escribe `manifiesto_datos.yaml` con el sha256 y el origen de cada archivo.

Este es el ÚNICO archivo del proyecto con rutas de origen (fuera de la carpeta del simulador).
El simulador nunca lee fuera de `datos/` y `conjunto_prueba/`.

Uso:
    python scripts/preparar_datos.py                 # dominio + todos los casos
    python scripts/preparar_datos.py --solo-dominio
    python scripts/preparar_datos.py --caso las_lagunas_potrerillos_2024
    python scripts/preparar_datos.py --sin-descarga  # no consulta Open-Meteo: usa la meteo de conjunto_pruebas
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import yaml

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from simulador.io.grilla import Grilla                       # noqa: E402
from simulador.io.manifiesto import Manifiesto, Entrada, sha256_archivo, VERSION_MANIFIESTO, validar_meteo_csv  # noqa: E402
from simulador.fuel import sb40                               # noqa: E402
from simulador.fuel.generar_sb40 import generar, NODATA       # noqa: E402

# ------------------------------------------------------------------ rutas de ORIGEN (únicas en el proyecto)
DOCS = RAIZ.parent
ORIGEN = {
    "dominio": DOCS / "Dominio_LasLagunas_30m",
    "conjunto_pruebas": DOCS / "conjunto_pruebas",
    "firms": DOCS / "Incendios_SanLuis/Datos/Procesados/FIRMS/viirs_snpp_san_luis_recortado.csv",
    "s2_anclado": DOCS / "Incendios_SanLuis/Datos/Procesados/Sentinel2_Areas_Quemadas/_anclado_viirs",
    "fuego_mapbiomas": DOCS / "Datos_SL_Completo/Fuego_MapBiomas/Coleccion_1/fuego_mensual_sanluis_2022_2025.tif",
}
HOY = dt.date.today().isoformat()
HUSO = "America/Argentina/San_Luis"

# ancho de camino por tipo estándar (m), cuando la fuente no trae ancho (ninguna lo trae)
ANCHO_TIPO = {"pavimentado": 8.0, "ripio": 7.0, "tierra": 5.0, "huella": 3.0}
ANCHO_AUTOPISTA = 20.0
# compuestos mensuales que usan los casos (verano previo + mes del evento); cada uno pesa ~9 MB
MESES_INDICES = ["2023_01", "2023_02", "2023_03", "2023_08", "2024_01", "2024_02", "2024_03", "2024_09"]


def log(msg):
    print(msg, flush=True)


def copiar(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return dst


def entrada(nombre, ruta_rel, tipo, origen, **kw) -> Entrada:
    ruta = RAIZ / ruta_rel
    e = Entrada(nombre=nombre, ruta=str(ruta_rel).replace("\\", "/"), tipo=tipo, sha256=sha256_archivo(ruta),
                origen=origen, fecha_preparacion=HOY)
    for k, v in kw.items():
        if k in Entrada.__dataclass_fields__:
            setattr(e, k, v)
        else:
            e.extra[k] = v
    return e


def info_raster(ruta: Path):
    with rasterio.open(ruta) as s:
        return s.crs.to_string(), s.dtypes[0], s.nodata, s.count


# ====================================================================== dominio
def preparar_dominio(entradas: list[Entrada]) -> Grilla:
    D = ORIGEN["dominio"]
    log("== Dominio ==")
    copiar(D / "dominio_lagunas_potrerillos.geojson", RAIZ / "datos/dominio/dominio.geojson")
    with rasterio.open(D / "Topografia/mdt_30m.tif") as s:
        grilla = Grilla.desde_raster(s)
    grilla.guardar(RAIZ / "datos/dominio/grilla.json")
    entradas.append(entrada("dominio", "datos/dominio/dominio.geojson", "geojson", {"ruta": str(D / "dominio_lagunas_potrerillos.geojson"), "fuente": "Dominio_LasLagunas_30m (recorte 30-09-2026)"},
                            crs="EPSG:4326", descripcion="Dominio Las Lagunas–Potrerillos y 25 celdas de 10 km (WGS84, RFC 7946)"))
    entradas.append(entrada("grilla", "datos/dominio/grilla.json", "json", {"ruta": str(D / "Topografia/mdt_30m.tif"), "fuente": "derivado del MDT del dominio"},
                            descripcion="CRS, transform, ancho, alto y resolución de la grilla de trabajo"))

    log("== Topografía ==")
    topo = [("mdt", "mdt_30m.tif", "mdt.tif", "m s.n.m.", [0, 7000], "MDT ASTER GDEM remuestreado bilineal a 30 m"),
            ("pendiente", "pendiente_grados.tif", "pendiente.tif", "grados", [0, 90], "Horn 3×3 sobre mdt.tif"),
            ("orientacion", "orientacion_grados.tif", "orientacion.tif", "grados (0 = N, horario); 361 = plano", [0, 361], "Horn 3×3 sobre mdt.tif; < 0,5° = plano (361)")]
    for nombre, src, dstn, unidades, rango, desc in topo:
        d = copiar(D / "Topografia" / src, RAIZ / "datos/estaticos/topografia" / dstn)
        with rasterio.open(d) as s:
            grilla.verificar_raster(s, nombre)
        crs, dtype, nodata, _ = info_raster(d)
        entradas.append(entrada(nombre, f"datos/estaticos/topografia/{dstn}", "raster", {"ruta": str(D / "Topografia" / src), "fuente": "Dominio_LasLagunas_30m/Topografia"},
                                crs=crs, dtype=dtype, nodata=nodata, unidades=unidades, rango=rango, bandas=1, descripcion=desc))

    log("== Combustible ==")
    for anio in (2023, 2024, 2025):
        d = copiar(D / f"Combustibles/modelos_SB40_{anio}.tif", RAIZ / f"datos/estaticos/combustible/sb40_{anio}.tif")
        with rasterio.open(d) as s:
            grilla.verificar_raster(s, f"sb40_{anio}")
        crs, dtype, nodata, _ = info_raster(d)
        entradas.append(entrada(f"combustible_{anio}" if anio != 2025 else "combustible", f"datos/estaticos/combustible/sb40_{anio}.tif", "raster",
                                {"ruta": str(D / f"Combustibles/modelos_SB40_{anio}.tif"), "fuente": "MapBiomas Col.3 + ASTER + S2 NDVI/NDMI verano (generar_modelos_combustible.py)"},
                                crs=crs, dtype=dtype, nodata=nodata, unidades="código FBFM40", bandas=1, codigos="combustible",
                                descripcion=f"Modelos Scott & Burgan {anio} (cobertura {anio} + NDVI verano {anio})"))
    sb40.escribir_csv(RAIZ / "datos/estaticos/combustible/parametros_sb40.csv")
    entradas.append(entrada("parametros_sb40", "datos/estaticos/combustible/parametros_sb40.csv", "tabla", {"fuente": "Scott & Burgan (2005) RMRS-GTR-153, transcripción en simulador/fuel/sb40.py"},
                            unidades="t/ac, 1/ft, ft, %, BTU/lb", descripcion="Parámetros de los 40 modelos estándar"))
    for extra in ("tabla_equivalencias.csv", "umbrales_ndvi.csv"):
        d = copiar(D / "Combustibles" / extra, RAIZ / "datos/estaticos/combustible" / extra)
        entradas.append(entrada(extra.replace(".csv", ""), f"datos/estaticos/combustible/{extra}", "tabla", {"ruta": str(D / "Combustibles" / extra)},
                                descripcion="Tablas del generador de modelos de combustible (MapBiomas → FBFM40)"))

    log("== Infraestructura ==")
    preparar_infraestructura(D / "Vectores/vectores_dominio.gpkg", RAIZ / "datos/estaticos/infraestructura.gpkg", grilla, entradas)

    log("== Índices espectrales ==")
    for mes in MESES_INDICES:
        src = D / f"Indices_Espectrales/mensual/NDVI_NDMI_{mes}.tif"
        d = copiar(src, RAIZ / f"datos/dinamicos/indices/NDVI_NDMI_{mes}.tif")
        with rasterio.open(d) as s:
            grilla.verificar_raster(s, f"NDVI_NDMI_{mes}")
        crs, dtype, nodata, n = info_raster(d)
        entradas.append(entrada(f"indices_{mes}", f"datos/dinamicos/indices/NDVI_NDMI_{mes}.tif", "raster",
                                {"ruta": str(src), "fuente": "Sentinel-2 L2A (GEE), compuesto mediano mensual, Cloud Score+ ≥ 0,60"},
                                crs=crs, dtype=dtype, nodata=nodata, unidades="índice ×10000 (banda 1 NDVI, banda 2 NDMI)", bandas=2, rango=[-10000, 10000],
                                descripcion=f"NDVI/NDMI {mes.replace('_', '-')}"))
    (RAIZ / "datos/dinamicos/meteo").mkdir(parents=True, exist_ok=True)
    (RAIZ / "datos/dinamicos/meteo/LEEME.md").write_text(
        "# Meteorología horaria\n\nLas series horarias del dominio van acá con el formato estándar (sección 2.3):\n\n"
        "`timestamp,temp_c,hr_pct,viento_kmh,viento_dir_deg,precip_mm,fuente`\n\n"
        "Por ahora cada caso de `conjunto_prueba/` trae su propia serie (`meteo_horaria.csv`). Las series de escenarios\n"
        "operativos (REM / SMN / pronóstico) se agregan acá y se registran en el manifiesto.\n", encoding="utf-8")
    return grilla


def tipo_camino(clase: str, superficie: str) -> str:
    clase = (clase or "").lower(); sup = (superficie or "").lower()
    if sup == "pavimentado" or clase == "autopista":
        return "pavimentado"
    if clase in ("huella", "senda"):
        return "huella"
    if clase == "ruta":
        return "ripio" if sup in ("consolidado", "desconocido") else "tierra"
    if clase == "ferrocarril":
        return "ripio"
    if sup == "consolidado":
        return "ripio"
    return "tierra"


def preparar_infraestructura(src: Path, dst: Path, grilla: Grilla, entradas: list[Entrada]):
    import geopandas as gpd
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    defaults = {}
    cam = gpd.read_file(src, layer="caminos")
    if not cam.crs or cam.crs.to_epsg() != 5345:
        cam = cam.to_crs(grilla.crs)
    cam["id"] = cam["id_camino"].astype(str)
    cam["tipo"] = [tipo_camino(a, b) for a, b in zip(cam["clase"], cam["superficie"])]
    cam["ancho_m"] = [ANCHO_AUTOPISTA if c == "autopista" else ANCHO_TIPO[t] for c, t in zip(cam["clase"], cam["tipo"])]
    defaults["caminos.ancho_m"] = f"inferido del tipo: {ANCHO_TIPO} (autopista {ANCHO_AUTOPISTA} m); la fuente no trae ancho"
    defaults["caminos.tipo"] = "derivado de clase+superficie: pavimentado/autopista→pavimentado; huella,senda→huella; ruta consolidado|desconocido→ripio; ferrocarril→ripio; consolidado→ripio; resto→tierra"
    cols = ["id", "tipo", "ancho_m", "clase", "superficie", "jerarquia", "nombre", "fuente", "longitud_m", "geometry"]
    cam[[c for c in cols if c in cam.columns]].to_file(dst, layer="caminos", driver="GPKG")
    viv = gpd.read_file(src, layer="viviendas").to_crs(grilla.crs)
    viv["id"] = viv["id_vivienda"].astype(str)
    cols = ["id", "tipo", "clase", "uso_residencial", "nombre", "fuente", "area_m2", "geometry"]
    viv[[c for c in cols if c in viv.columns]].to_file(dst, layer="viviendas", driver="GPKG")
    red = gpd.read_file(src, layer="elec_red_mt_edesal").to_crs(grilla.crs)
    red["id"] = [f"MT-{i:06d}" for i in range(len(red))]
    red["tension"] = "MT"
    red["tension_kv"] = red["tension_kv"].astype(str)
    defaults["red_electrica.id"] = "secuencial MT-000000; la fuente (EDESAL) no trae identificador"
    defaults["red_electrica.tension"] = "MT para toda la capa (13,2 y 33 kV); no hay AT ni BT en el dominio"
    red[["id", "tension", "tension_kv", "geometry"]].to_file(dst, layer="red_electrica", driver="GPKG")
    log(f"   caminos {len(cam)} · viviendas {len(viv)} · red_electrica {len(red)}")
    entradas.append(entrada("infraestructura", "datos/estaticos/infraestructura.gpkg", "vector",
                            {"ruta": str(src), "fuente": "vectores_dominio.gpkg (SIG San Luis + IGN + OSM; EDESAL vía Secretaría de Energía)", "capa_red_original": "elec_red_mt_edesal"},
                            crs="EPSG:5345", capas=["caminos", "viviendas", "red_electrica"], valores_por_defecto=defaults,
                            descripcion="Caminos (id, tipo, ancho_m), viviendas (id), red eléctrica (id, tension)"))


# ====================================================================== casos de prueba
CASOS = {
    "las_lagunas_la_aguada_2023": dict(
        sm="SM01_2023_LAS_LAGUNAS_Y_LA_AGUADA", anio=2023, cobertura=2022, verano=2023, mes_evento="2023_08",
        fecha_inicio="2023-08-31", fecha_fin="2023-09-01", fecha_perimetro="2023-09-04",
        meteo=("2023-08-30", "2023-09-02"), t0="2023-08-31T12:00:00-03:00", duracion_h=36,
        focos_ventana=("2023-08-28", "2023-09-06"), ignicion="parte_proyectado", s2_evento="2023-007",
        s2_nota="cicatriz distinta, 8 km al NO del perímetro COE; misma denominación en el parte SNMF", s2_mismo_incendio=False,
        titulo="Las Lagunas y La Aguada · 2023", nombre_parte="LAS LAGUNAS Y LA AGUADA",
        descripcion=("Incendio 'Las Lagunas y La Aguada' (parte SNMF, Libertador General San Martín), 31-08-2023 → 01-09-2023 (extinguido). "
                     "Cicatriz COE de 105,4 ha, 100 % dentro del dominio Las Lagunas–Potrerillos. Caso SM01 de conjunto_pruebas adaptado al estándar 7.1. "
                     "La hora de ignición es supuesta (12:00 local): no hay focos VIIRS sobre esta cicatriz."),
        variantes={
            "t0_06h": {"t_inicio": "2023-08-31T06:00:00-03:00", "ignicion": "ignicion_t0_06h.geojson"},
            "t0_09h": {"t_inicio": "2023-08-31T09:00:00-03:00", "ignicion": "ignicion_t0_09h.geojson"},
            "t0_15h": {"t_inicio": "2023-08-31T15:00:00-03:00", "ignicion": "ignicion_t0_15h.geojson"},
            "t0_18h": {"t_inicio": "2023-08-31T18:00:00-03:00", "ignicion": "ignicion_t0_18h.geojson"},
            "ignicion_snmf_original": {"ignicion": "ignicion_snmf_original.geojson"},
            "vecindad_16": {"vecindad": 16}, "dt_1min": {"dt_min": 1.0}, "dt_5min": {"dt_min": 5.0},
        },
        ignicion_variantes={"ignicion_t0_06h.geojson": ("hora", "2023-08-31T06:00:00-03:00"), "ignicion_t0_09h.geojson": ("hora", "2023-08-31T09:00:00-03:00"),
                            "ignicion_t0_15h.geojson": ("hora", "2023-08-31T15:00:00-03:00"), "ignicion_t0_18h.geojson": ("hora", "2023-08-31T18:00:00-03:00"),
                            "ignicion_snmf_original.geojson": ("usar", ["snmf_original"])},
        salidas={"png": True, "gif": True, "dpi": 110},
        incertidumbres=[
            "Hora de ignición desconocida: el parte da el día (31-08) pero no la hora. Variantes t0 06/09/12/15/18 h.",
            "Punto de ignición del parte a 88,7 m fuera de la cicatriz; se usa el punto proyectado al borde (derivado).",
            "El perímetro COE no tiene fecha propia; se asume el final del evento (01-09). La ventana de 36 h cubre hasta el fin del 01-09.",
            "La meteorología es reanálisis ERA5 (celda de 0,25°) en el punto de ignición; no hay estaciones.",
            "El evento Sentinel-2/VIIRS 2023-007 (145 ha, 8 km al NO) es otra cicatriz con el mismo nombre de parte; no se simula en el caso base.",
        ],
        leeme_extra="""## Dos cicatrices con el mismo nombre

El parte "Las Lagunas y La Aguada" (un único registro, 31-08-2023) tiene asociado el evento satelital 2023-007 (145,5 ha), pero ese
evento está **8 km al noroeste** de la cicatriz COE que coincide con las coordenadas del parte. Los 11 focos VIIRS del 01-09-2023
(18:26 UTC, FRP máx. 43,8 MW) caen sobre la cicatriz NO. MapBiomas Fuego marca **ambas** como quemadas en agosto de 2023.
Son dos incendios distintos (probablemente uno por paraje). El caso simula la cicatriz COE, que es la del punto del parte; la cicatriz
NO queda documentada para un caso futuro con focos (permitiría comparar tiempos de llegada).
""",
    ),
    "las_lagunas_potrerillos_2024": dict(
        sm="SM05_2024_LAS_LAGUNAS_POTRERILLOS", anio=2024, cobertura=2023, verano=2024, mes_evento="2024_09",
        fecha_inicio="2024-09-18", fecha_fin="2024-10-09", fecha_perimetro="2024-10-09",
        meteo=("2024-09-17", "2024-09-26"), t0="2024-09-18T15:43:00-03:00", duracion_h=72,
        focos_ventana=("2024-09-15", "2024-10-10"), ignicion="focos_primer_pase", s2_evento="2024-003",
        ids_partes={"LAS LAGUNAS POTRERILLOS": "parte_las_lagunas", "POTRERILLOS": "parte_potrerillos"},
        s2_nota="mismo evento (Sentinel-2 dNBR anclado en VIIRS, 25.437 ha); subestima la cicatriz COE", s2_mismo_incendio=True,
        titulo="Las Lagunas – Potrerillos · 2024 (caso de estrés)", nombre_parte="LAS LAGUNAS / POTRERILLOS",
        descripcion=("Complejo Las Lagunas–Potrerillos (partes SNMF 'LAS LAGUNAS' y 'POTRERILLOS' del 18-09-2024, unidos por el evento satelital 2024-003), "
                     "18-09-2024 → 09-10-2024 (extinguido). Cicatriz COE de 38.631 ha (un polígono de 38.541 ha + parches), 100 % dentro del dominio: "
                     "es el incendio que motivó el dominio Las Lagunas–Potrerillos. Caso SM05 de conjunto_pruebas (tipo estrés) adaptado al estándar 7.1. "
                     "Hay 2.006 focos VIIRS S-NPP: el primer pase (18-09 15:43 local) ya muestra 50 focos a lo largo de 9 km, por lo que la ignición base "
                     "es múltiple (los focos del primer pase) y t0 es la hora de ese pase."),
        variantes={
            "parte_potrerillos_12h": {"t_inicio": "2024-09-18T12:00:00-03:00", "ignicion": "ignicion_parte_potrerillos_12h.geojson"},
            "parte_las_lagunas_12h": {"t_inicio": "2024-09-18T12:00:00-03:00", "ignicion": "ignicion_parte_las_lagunas_12h.geojson"},
            "dos_partes_12h": {"t_inicio": "2024-09-18T12:00:00-03:00", "ignicion": "ignicion_dos_partes_12h.geojson"},
            "duracion_144h": {"duracion_h": 144, "salidas": {"png_cada_h": 6}},
            "dt_5min": {"dt_min": 5.0},
            # hipótesis de combustible (calibración): el fuego real cruzó en una noche el bosque TU5/TU1 y el agrícola NB3 del NE
            "bosque_gs2": {"combustible": "combustible_bosque_gs2.tif"},
            "agricola_gr1": {"combustible": "combustible_agricola_gr1.tif"},
            "bosque_gs2_agricola_gr1": {"combustible": "combustible_bosque_gs2_agricola_gr1.tif"},
        },
        combustibles_alternativos={
            "bosque_gs2": {165: 122, 161: 122},
            "agricola_gr1": {93: 101},
            "bosque_gs2_agricola_gr1": {165: 122, 161: 122, 93: 101},
        },
        ignicion_variantes={"ignicion_parte_potrerillos_12h.geojson": ("usar_hora", ["parte_potrerillos"], "2024-09-18T12:00:00-03:00"),
                            "ignicion_parte_las_lagunas_12h.geojson": ("usar_hora", ["parte_las_lagunas"], "2024-09-18T12:00:00-03:00"),
                            "ignicion_dos_partes_12h.geojson": ("usar_hora", ["parte_potrerillos", "parte_las_lagunas"], "2024-09-18T12:00:00-03:00")},
        salidas={"png": True, "gif": True, "dpi": 100, "png_cada_h": 2},
        incertidumbres=[
            "Ignición: dos partes SNMF a 7 km (Las Lagunas y Potrerillos) y 50 focos VIIRS a lo largo de 9 km en el primer pase (15:43 local): varias igniciones o un fuego de la mañana. Base = focos del primer pase; variantes desde cada parte a las 12:00.",
            "El perímetro COE es el acumulado de 21 días con supresión (6 brigadas, aviones); la corrida base es de 72 h de propagación libre. La variante de 144 h cubre el período de actividad VIIRS (18 → 24-09).",
            "Superficies discrepantes entre fuentes: COE 38.631 ha, SMF 48.226 ha, Sentinel-2 dNBR 25.437 ha.",
            "Un solo punto ERA5 (celda de 0,25°) para una caja de 46 × 41 km con relieve serrano: el viento real varió dentro del área.",
            "El combustible pre-evento usa cobertura 2023 + NDVI verano 2024; no se corrigen áreas quemadas en 2022–2023 dentro de la caja.",
            "Las variantes bosque_gs2 / agricola_gr1 reasignan TU5 y TU1 → GS2 y NB3 → GR1: son hipótesis de calibración, no datos.",
        ],
        leeme_extra="""## Focos VIIRS e ignición múltiple

El primer pase VIIRS S-NPP del evento (18-09-2024 18:43 UTC, 15:43 local) detecta 50 focos entre x 3.528.572 y 3.537.174 (9 km de
este a oeste, y ≈ 6.389.600), con FRP de hasta 110 MW. El parte "Potrerillos" (3.535.349, 6.388.840) cae dentro de ese cúmulo; el
parte "Las Lagunas" (3.542.442, 6.389.418) queda 5 km al este del foco más oriental. Los pases siguientes (19-09 01:00 y 03:00
local, 15:00 local; 20-09 02:00 y 15:00 local, con 544 y 579 focos) muestran la expansión hacia el norte y el este. La actividad
termina el 24-09; los partes siguen hasta el 09-10 (contenido desde el 28-09).

La ignición base reproduce el estado observado en el primer pase: los focos de ese pase que caen dentro de la cicatriz COE se
encienden a las 15:43. Es una ignición múltiple **observada**, no un supuesto. Las variantes desde los puntos de los partes a las
12:00 permiten ver si un único foco explica la extensión del primer pase.
""",
    ),
}


def preparar_caso(nombre: str, spec: dict, grilla: Grilla, entradas: list[Entrada], descargar: bool):
    import geopandas as gpd
    from shapely.geometry import box
    from rasterio.mask import mask as rmask
    from rasterio import features
    from shapely.geometry import shape
    log(f"== Caso {nombre} ==")
    CP = ORIGEN["conjunto_pruebas"]; C = CP / "casos" / spec["sm"]
    out = RAIZ / "conjunto_prueba" / nombre
    out.mkdir(parents=True, exist_ok=True)
    cj = json.loads((C / "caso.json").read_text(encoding="utf-8"))
    bb = cj["bbox_m"]
    caja = (bb["xmin"], bb["ymin"], bb["xmax"], bb["ymax"])
    sub, _ = grilla.ventana(*caja)
    log(f"   caja {caja} → {sub.ancho} × {sub.alto} celdas (alineada)")
    origen_caso = {"ruta": str(C), "fuente": f"conjunto_pruebas (formato anterior, {spec['sm']})"}
    anio = spec["anio"]

    # --- perímetro observado (COE) ----------------------------------------------------------------
    per = gpd.read_file(C / "perimetro_final.geojson")
    per["fecha"] = spec["fecha_perimetro"]
    per["fuente"] = f"COE San Luis, areas_quemadas_2017_2026 ({', '.join(cj['ids']['ids_fuente_cicatriz'])}), vía conjunto_pruebas {spec['sm']}"
    per["nota"] = "fecha = fin del evento según el parte; la cicatriz no tiene fecha propia"
    per[["fecha", "fuente", "nota", "ha", "geometry"]].to_crs("EPSG:4326").to_file(out / "perimetro_observado.geojson", driver="GeoJSON")
    per_m = per.to_crs(grilla.crs); u = per_m.union_all()

    # --- perímetros alternativos: Fuego MapBiomas (mes) y evento S2 -----------------------------------
    with rasterio.open(ORIGEN["fuego_mapbiomas"]) as s:
        caja_ll = gpd.GeoSeries([box(*caja)], crs=grilla.crs).to_crs(s.crs)
        arr, tr = rmask(s, caja_ll.geometry, crop=True, nodata=255)
        banda = arr[anio - 2022]
        geoms = [(shape(g), int(v)) for g, v in features.shapes(banda, mask=(banda > 0) & (banda != 255), transform=tr)]
        meses_mb = []
        if geoms:
            mb = gpd.GeoDataFrame({"mes": [v for _, v in geoms], "geometry": [g for g, _ in geoms]}, crs=s.crs).dissolve(by="mes").reset_index()
            mb["fecha"] = ["%d-%02d" % (anio, m) for m in mb["mes"]]; mb["fuente"] = f"MapBiomas Fuego Col.1, quemado mensual {anio}"
            mb.to_crs("EPSG:4326").to_file(out / f"perimetro_mapbiomas_fuego_{anio}.geojson", driver="GeoJSON")
            meses_mb = sorted(mb["mes"].tolist())
            log(f"   MapBiomas Fuego {anio} en la caja: meses {meses_mb}")
    s2 = gpd.read_file(ORIGEN["s2_anclado"] / f"evento_{spec['s2_evento']}.geojson")
    s2["fecha"] = spec["fecha_perimetro"]; s2["fuente"] = f"Sentinel-2 dNBR anclado en focos VIIRS, evento {spec['s2_evento']}"
    s2["nota"] = spec["s2_nota"]
    s2.to_crs("EPSG:4326").to_file(out / f"perimetro_s2_evento_{spec['s2_evento']}.geojson", driver="GeoJSON")
    s2_ha = round(s2.to_crs(grilla.crs).union_all().area / 1e4, 1)

    # --- focos VIIRS en la caja + 10 km ---------------------------------------------------------------
    f = pd.read_csv(ORIGEN["firms"], low_memory=False)
    f = f[(f.acq_date >= spec["focos_ventana"][0]) & (f.acq_date <= spec["focos_ventana"][1])]
    gf = gpd.GeoDataFrame(f, geometry=gpd.points_from_xy(f.longitude, f.latitude), crs="EPSG:4326").to_crs(grilla.crs)
    gf = gf[gf.intersects(box(*caja).buffer(10000))].copy()
    hhmm = gf["acq_time"].astype(int)
    gf["hora_deteccion"] = [pd.Timestamp(f"{d} {h//100:02d}:{h%100:02d}", tz="UTC").isoformat() for d, h in zip(gf.acq_date, hhmm)]
    gf["hora_deteccion_local"] = [pd.Timestamp(h).tz_convert(HUSO).isoformat() for h in gf["hora_deteccion"]]
    gf = gf.sort_values("hora_deteccion").reset_index(drop=True)
    gf["id"] = [f"VIIRS-{i:04d}" for i in range(len(gf))]
    gf["dentro_caja"] = gf.intersects(box(*caja))
    gf["dentro_cicatriz"] = gf.intersects(u)
    gf["dist_perimetro_coe_m"] = gf.distance(u).round(0)
    cols = ["id", "hora_deteccion", "hora_deteccion_local", "satellite", "instrument", "confidence", "frp", "daynight", "dentro_caja", "dentro_cicatriz", "dist_perimetro_coe_m", "geometry"]
    gf[cols].to_crs("EPSG:4326").to_file(out / "focos_viirs.geojson", driver="GeoJSON")
    n_focos, n_caja = len(gf), int(gf.dentro_caja.sum())
    log(f"   focos VIIRS {spec['focos_ventana'][0]} → {spec['focos_ventana'][1]} a < 10 km de la caja: {n_focos} ({n_caja} dentro de la caja)")

    # --- ignición -----------------------------------------------------------------------------------
    ign = gpd.read_file(C / "ignicion.geojson").to_crs(grilla.crs)
    t0 = spec["t0"]
    filas = []
    for _, r in ign.iterrows():
        tipo = r["tipo"]; nom = str(r.get("nombre", "")).strip().lower().replace(" ", "_")
        if tipo == "parte":
            idp = "snmf_original" if spec["ignicion"] == "parte_proyectado" else spec.get("ids_partes", {}).get(str(r.get("nombre", "")).strip(), f"parte_{nom}")
        else:
            idp = {"centroide_cicatriz": "centroide_cicatriz", "parte_proyectado_a_cicatriz": "snmf_proyectado"}.get(tipo, tipo)
        filas.append({"id": idp, "hora_ignicion": t0, "usar": (tipo == "parte_proyectado_a_cicatriz") if spec["ignicion"] == "parte_proyectado" else False,
                      "origen": r["origen"], "dentro_de_cicatriz": bool(r["dentro_de_cicatriz"]), "dist_a_cicatriz_m": float(r["dist_a_cicatriz_m"]),
                      "nota": "parte SNMF" if tipo == "parte" else "derivado", "frp": None, "geometry": r.geometry})
    if spec["ignicion"] == "focos_primer_pase":
        primer = gf[gf.hora_deteccion == gf.hora_deteccion.min()]
        primer = primer[primer.dentro_cicatriz]
        t0 = pd.Timestamp(primer.hora_deteccion.iloc[0]).tz_convert(HUSO).isoformat()
        spec["t0"] = t0
        for _, r in primer.iterrows():
            filas.append({"id": r["id"], "hora_ignicion": t0, "usar": True, "origen": "VIIRS S-NPP primer pase", "dentro_de_cicatriz": True,
                          "dist_a_cicatriz_m": 0.0, "nota": "foco del primer pase VIIRS dentro de la cicatriz", "frp": float(r["frp"]), "geometry": r.geometry})
        log(f"   ignición múltiple: {len(primer)} focos del primer pase ({t0})")
    base_ign = gpd.GeoDataFrame(filas, crs=grilla.crs)
    base_ign.to_crs("EPSG:4326").to_file(out / "ignicion.geojson", driver="GeoJSON")
    for archivo, regla in spec.get("ignicion_variantes", {}).items():
        g2 = base_ign.copy()
        if regla[0] == "hora":
            g2["hora_ignicion"] = regla[1]
        elif regla[0] == "usar":
            g2["usar"] = g2["id"].isin(regla[1])
        elif regla[0] == "usar_hora":
            g2["usar"] = g2["id"].isin(regla[1]); g2["hora_ignicion"] = regla[2]
        g2.to_crs("EPSG:4326").to_file(out / archivo, driver="GeoJSON")

    # --- combustible pre-evento: cobertura (anio−1) + NDVI/NDMI verano (anio) (regla 3.3) -------------
    D = ORIGEN["dominio"]
    with rasterio.open(D / f"Uso_Cobertura_Suelo/Coleccion_3/mapbiomas_col3_sanluis_{spec['cobertura']}.tif") as s:
        grilla.verificar_raster(s, f"mapbiomas {spec['cobertura']}"); lc = s.read(1); perfil = s.profile
    with rasterio.open(RAIZ / "datos/estaticos/topografia/mdt.tif") as s:
        dem = s.read(1)
    nd, nm = [], []
    for m in (1, 2, 3):
        with rasterio.open(RAIZ / f"datos/dinamicos/indices/NDVI_NDMI_{spec['verano']}_{m:02d}.tif") as s:
            a = s.read().astype("float32"); a[a == s.nodata] = np.nan
            nd.append(a[0] / 10000); nm.append(a[1] / 10000)
    ndvi_v = np.nanmedian(nd, 0); ndmi_v = np.nanmedian(nm, 0)
    umbrales = pd.read_csv(RAIZ / "datos/estaticos/combustible/umbrales_ndvi.csv")
    comb = generar(lc, dem, ndvi_v, ndmi_v, umbrales)
    perfil.update(dtype="int16", nodata=NODATA, count=1, compress="deflate")
    with rasterio.open(out / "combustible_pre_evento.tif", "w", **perfil) as dst:
        dst.write(comb, 1); dst.set_band_description(1, "FBFM40 Scott & Burgan 2005, pre-evento")
        dst.update_tags(cobertura=f"MapBiomas Col.3 {spec['cobertura']}", ndvi=f"verano {spec['verano']} (ene–mar), mediana", regla="Combustibles/README.md §3.3")
    for alt, mapa in spec.get("combustibles_alternativos", {}).items():
        comb_alt = comb.copy()
        for de, a in mapa.items():
            comb_alt[comb == de] = a
        with rasterio.open(out / f"combustible_{alt}.tif", "w", **perfil) as dst:
            dst.write(comb_alt, 1); dst.set_band_description(1, f"FBFM40 pre-evento, hipótesis {alt}: {mapa}")
            dst.update_tags(hipotesis=alt, reasignacion=json.dumps(mapa), base="combustible_pre_evento.tif")
    perfil_v = dict(perfil); perfil_v.update(dtype="int16", nodata=-32768)
    with rasterio.open(out / "ndvi_verano_previo.tif", "w", **perfil_v) as dst:
        dst.write(np.where(np.isnan(ndvi_v), -32768, np.round(ndvi_v * 10000)).astype("int16"), 1)
        dst.set_band_description(1, f"NDVI mediana ene–mar {spec['verano']} ×10000")
    copiar(RAIZ / f"datos/dinamicos/indices/NDVI_NDMI_{spec['mes_evento']}.tif", out / "indices_mes_evento.tif")
    with rasterio.open(out / "combustible_pre_evento.tif") as s:
        m_pre, _ = rmask(s, [u], crop=True, nodata=NODATA)
    with rasterio.open(RAIZ / f"datos/estaticos/combustible/sb40_{anio}.tif") as s:
        m_an, _ = rmask(s, [u], crop=True, nodata=NODATA); anual = s.read(1)
    dist_pre = _dist(m_pre); dist_an = _dist(m_an)
    log(f"   combustible pre-evento en el perímetro COE: {dist_pre}")
    coinciden = float((comb == anual).mean() * 100)

    # --- meteorología (punto: centroide de la cicatriz) ------------------------------------------------
    ruta_meteo = out / "meteo_horaria.csv"
    from pyproj import Transformer
    lon, lat = Transformer.from_crs(grilla.crs, "EPSG:4326", always_xy=True).transform(u.centroid.x, u.centroid.y)
    fuente_meteo = None
    if descargar:
        try:
            fuente_meteo = descargar_era5(lat, lon, *spec["meteo"], ruta_meteo)
            log(f"   meteo descargada: {fuente_meteo}")
        except Exception as e:  # sin red o API caída → se cae a la serie del conjunto anterior
            log(f"   AVISO: no se pudo descargar ERA5 ({e}); se convierte la serie de conjunto_pruebas")
    if fuente_meteo is None:
        fuente_meteo = convertir_meteo_cp(C / "meteo_horaria.csv", ruta_meteo)
    validar_meteo_csv(ruta_meteo)

    # --- caso.yaml -------------------------------------------------------------------------------------
    alternativos = {f"mapbiomas_fuego_{anio}": f"perimetro_mapbiomas_fuego_{anio}.geojson"}
    if spec["s2_mismo_incendio"]:
        alternativos[f"sentinel2_{spec['s2_evento']}"] = f"perimetro_s2_evento_{spec['s2_evento']}.geojson"
    caso = {
        "nombre": nombre, "descripcion": spec["descripcion"],
        "fechas": {"inicio": spec["fecha_inicio"], "fin": spec["fecha_fin"], "origen": "parte SNMF (fecha_inicio, fecha_extincion)"},
        "fuentes": {"perimetro": f"COE San Luis ({', '.join(cj['ids']['ids_fuente_cicatriz'])})",
                    "ignicion": {"parte_proyectado": "parte SNMF proyectado al borde de la cicatriz", "focos_primer_pase": "focos VIIRS S-NPP del primer pase dentro de la cicatriz"}[spec["ignicion"]],
                    "meteo": fuente_meteo + f"; punto = centroide de la cicatriz ({lat:.4f}, {lon:.4f})",
                    "combustible": f"MapBiomas Col.3 {spec['cobertura']} + NDVI/NDMI verano {spec['verano']} (regla 3.3)",
                    "indices_mes": f"NDVI/NDMI {spec['mes_evento'].replace('_', '-')} (compuesto mensual S2)", "focos": "FIRMS VIIRS S-NPP (archivo local del proyecto)"},
        "escenario": {
            "nombre": nombre, "grilla": {"xmin": caja[0], "ymin": caja[1], "xmax": caja[2], "ymax": caja[3]},
            "t_inicio": spec["t0"], "duracion_h": spec["duracion_h"], "dt_min": 2.0, "vecindad": 8, "modo": "determinista", "semilla": 42,
            "ignicion": "ignicion.geojson", "meteo": "meteo_horaria.csv", "combustible": "combustible_pre_evento.tif",
            "indices_mes_evento": "indices_mes_evento.tif", "ndvi_verano": "ndvi_verano_previo.tif",
            "perimetro_observado": "perimetro_observado.geojson", "focos": "focos_viirs.geojson",
            "salidas": spec["salidas"],
        },
        "variantes": spec["variantes"],
        "evaluacion": {"perimetros_alternativos": alternativos, "nombre_toa": f"sim_{spec['sm']}_simulador_toa.tif",
                       "tolerancias": {"sorensen_min": 0.5, "error_superficie_pct_max": 50}},
        "incertidumbres": spec["incertidumbres"],
    }
    (out / "caso.yaml").write_text(yaml.safe_dump(caso, allow_unicode=True, sort_keys=False, width=140), encoding="utf-8")
    escribir_leeme(out, nombre, spec, cj, sub, dist_pre, dist_an, coinciden, fuente_meteo, n_focos, n_caja, int(gf.dentro_cicatriz.sum()), s2_ha, meses_mb)

    # --- entradas del manifiesto para el caso --------------------------------------------------------
    rel = f"conjunto_prueba/{nombre}"; pref = f"caso_{nombre}"
    archivos = [
        ("combustible_pre_evento", "combustible_pre_evento.tif", "raster", dict(crs="EPSG:5345", dtype="int16", nodata=-9999, bandas=1, codigos="combustible", unidades="código FBFM40")),
        ("ndvi_verano", "ndvi_verano_previo.tif", "raster", dict(crs="EPSG:5345", dtype="int16", nodata=-32768, bandas=1, rango=[-10000, 10000])),
        ("indices_mes_evento", "indices_mes_evento.tif", "raster", dict(crs="EPSG:5345", dtype="int16", nodata=-32768, bandas=2, rango=[-10000, 10000])),
        ("meteo", "meteo_horaria.csv", "meteo", dict(unidades="°C, %, km/h, grados, mm")),
        ("ignicion", "ignicion.geojson", "geojson", dict(crs="EPSG:4326")),
        ("perimetro_observado", "perimetro_observado.geojson", "geojson", dict(crs="EPSG:4326")),
        ("perimetro_mapbiomas", f"perimetro_mapbiomas_fuego_{anio}.geojson", "geojson", dict(crs="EPSG:4326")),
        ("perimetro_s2", f"perimetro_s2_evento_{spec['s2_evento']}.geojson", "geojson", dict(crs="EPSG:4326")),
        ("focos_viirs", "focos_viirs.geojson", "geojson", dict(crs="EPSG:4326")),
        ("yaml", "caso.yaml", "yaml", {}),
    ] + [(archivo.replace(".geojson", ""), archivo, "geojson", dict(crs="EPSG:4326")) for archivo in spec.get("ignicion_variantes", {})] \
      + [(f"combustible_{alt}", f"combustible_{alt}.tif", "raster", dict(crs="EPSG:5345", dtype="int16", nodata=-9999, bandas=1, codigos="combustible", unidades="código FBFM40"))
         for alt in spec.get("combustibles_alternativos", {})]
    for suf, archivo, tipo, kw in archivos:
        if (out / archivo).exists():
            entradas.append(entrada(f"{pref}_{suf}", f"{rel}/{archivo}", tipo, origen_caso, descripcion=f"caso {nombre}", **kw))


def _dist(arr):
    v, c = np.unique(arr[arr != NODATA], return_counts=True)
    inv = {v: k for k, v in sb40.tabla().set_index("clave")["codigo"].items()}
    return {inv.get(int(a), int(a)): round(100 * b / c.sum(), 1) for a, b in sorted(zip(v, c), key=lambda t: -t[1])}


def descargar_era5(lat, lon, desde, hasta, ruta: Path) -> str:
    """ERA5 vía Open-Meteo Historical Weather API (mismo método que conjunto_pruebas/scripts/07_meteorologia.py)."""
    import urllib.parse, urllib.request
    params = dict(latitude=lat, longitude=lon, start_date=desde, end_date=hasta,
                  hourly="temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,precipitation",
                  models="era5", wind_speed_unit="kmh", timezone="GMT")
    url = "https://archive-api.open-meteo.com/v1/archive?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as r:
        js = json.load(r)
    h = pd.DataFrame(js["hourly"])
    ts = pd.to_datetime(h["time"], utc=True).dt.tz_convert(HUSO)
    df = pd.DataFrame({"timestamp": ts.dt.strftime("%Y-%m-%dT%H:%M:%S-03:00"), "temp_c": h["temperature_2m"], "hr_pct": h["relative_humidity_2m"],
                       "viento_kmh": h["wind_speed_10m"], "viento_dir_deg": h["wind_direction_10m"], "precip_mm": h["precipitation"],
                       "fuente": "era5_openmeteo"})
    if df.isna().any().any():
        df = df.interpolate(limit_direction="both"); df.loc[df.isna().any(axis=1), "fuente"] = "era5_openmeteo_interpolado"
    df.to_csv(ruta, index=False, lineterminator="\n")
    return f"ERA5 (ECMWF/C3S) vía Open-Meteo Historical Weather API, models=era5, celda ({js['latitude']}, {js['longitude']}), descargado {HOY}"


def convertir_meteo_cp(src: Path, dst: Path) -> str:
    m = pd.read_csv(src)
    df = pd.DataFrame({"timestamp": m["fecha_hora_local"], "temp_c": m["temp_2m_c"], "hr_pct": m["hr_2m_pct"],
                       "viento_kmh": (m["viento_vel_10m_ms"] * 3.6).round(2), "viento_dir_deg": m["viento_dir_10m_grados"],
                       "precip_mm": m["precipitacion_mm"], "fuente": "era5_openmeteo_conjunto_pruebas"})
    df.to_csv(dst, index=False, lineterminator="\n")
    return "ERA5 vía Open-Meteo, serie de conjunto_pruebas (desde las 00:00 del día de inicio), convertida al formato estándar"


def escribir_leeme(out, nombre, spec, cj, sub, dist_pre, dist_an, coinciden, fuente_meteo, n_focos, n_caja, n_cic, s2_ha, meses_mb):
    ign = cj["ignicion_por_defecto"]
    txt = f"""# Caso de prueba · {spec['titulo']}

Adaptación del caso `conjunto_pruebas/casos/{spec['sm']}` al estándar de la sección 7.1 del simulador.
**La carpeta original no se modificó.** Preparado el {HOY} por `scripts/preparar_datos.py`.

## Datos del evento

| | |
|---|---|
| Parte SNMF | {spec['nombre_parte']} · inicio {spec['fecha_inicio']} · fin {spec['fecha_fin']} ({cj['fechas']['estado_final_parte']}) |
| Punto SNMF por defecto | lat {ign['lat']}, lon {ign['lon']} (x {ign['x_m']}, y {ign['y_m']}) · {'dentro' if ign['dentro_de_cicatriz'] else 'fuera'} de la cicatriz |
| Cicatriz COE | {cj['hectareas']['cicatriz']} ha ({', '.join(cj['ids']['ids_fuente_cicatriz'])}), {cj['n_fragmentos_cicatriz']} fragmento(s), 100 % dentro del dominio |
| Otras superficies | SMF {cj['hectareas']['parte_smf']} ha · Sentinel-2 dNBR {cj['hectareas']['sat_dnbr']} ha (evento {spec['s2_evento']}: {s2_ha} ha recalculadas) |
| Caja de simulación | xmin {cj['bbox_m']['xmin']:.0f} · ymin {cj['bbox_m']['ymin']:.0f} · xmax {cj['bbox_m']['xmax']:.0f} · ymax {cj['bbox_m']['ymax']:.0f} → {sub.ancho} × {sub.alto} celdas, alineada a la grilla del dominio |
| t0 base | {spec['t0']} ({'hora del primer pase VIIRS' if spec['ignicion'] == 'focos_primer_pase' else 'supuesta, 12:00 local'}) |
| Ventana base | {spec['duracion_h']} h |

## Mapeo desde el formato anterior

| Estándar 7.1 | Origen en conjunto_pruebas | Transformación |
|---|---|---|
| `caso.yaml` | `caso.json` | reescrito; conserva fechas, bbox, ignición y notas |
| `ignicion.geojson` | `ignicion.geojson` + focos VIIRS | atributos `id`, `hora_ignicion`, `usar`; {'por defecto los focos del primer pase dentro de la cicatriz' if spec['ignicion'] == 'focos_primer_pase' else 'por defecto el punto `snmf_proyectado` (dentro de la cicatriz)'} |
| `meteo_horaria.csv` | `meteo_horaria.csv` (ERA5/Open-Meteo) | {fuente_meteo}; punto = centroide de la cicatriz; desde 24 h antes de t0 |
| `combustible_pre_evento.tif` | — (generado) | MapBiomas Col.3 **{spec['cobertura']}** + NDVI/NDMI **verano {spec['verano']}** con los terciles de `umbrales_ndvi.csv` (regla 3.3) |
| `indices_mes_evento.tif` | — | `NDVI_NDMI_{spec['mes_evento']}.tif` del dominio (mes del incendio) |
| `ndvi_verano_previo.tif` | — | mediana NDVI ene–mar {spec['verano']} (para el curado) |
| `perimetro_observado.geojson` | `perimetro_final.geojson` | + `fecha`, `fuente` |
| `perimetro_mapbiomas_fuego_{spec['anio']}.geojson` | `Datos_SL_Completo/Fuego_MapBiomas` | quemado mensual {spec['anio']} vectorizado dentro de la caja (meses {meses_mb}) |
| `perimetro_s2_evento_{spec['s2_evento']}.geojson` | `_anclado_viirs/evento_{spec['s2_evento']}.geojson` | {spec['s2_nota']} |
| `focos_viirs.geojson` | FIRMS local (`viirs_snpp_san_luis_recortado.csv`) | {spec['focos_ventana'][0]} → {spec['focos_ventana'][1]}, a < 10 km de la caja: {n_focos} focos, **{n_caja} dentro de la caja, {n_cic} dentro de la cicatriz** |
| `obs_perimetro_final_30m.tif`, `.gpkg`, `partes_diarios.csv`, `curva_area_tiempo.csv` | — | no se copian: la información está en `perimetro_observado.geojson` y en este LEEME |

El GeoTIFF `sim_{spec['sm']}_simulador_toa.tif` que escribe cada corrida es compatible con `conjunto_pruebas/validacion/evaluar_simulacion.py`
(misma grilla que `obs_perimetro_final_30m.tif`, minutos desde t0, NaN donde no arde).

## Combustible pre-evento dentro del perímetro COE

| Mapa | Distribución (%) |
|---|---|
| pre-evento (cob. {spec['cobertura']} + verano {spec['verano']}) | {dist_pre} |
| anual {spec['anio']} (cob. {spec['anio']} + verano {spec['anio']}) | {dist_an} |

Coincidencia celda a celda entre ambos mapas en todo el dominio: {coinciden:.1f} %. Para las clases leñosas el mapa anual usa el NDVI
promedio de tres veranos (2023–2025); el pre-evento usa solo el verano {spec['verano']} para no incorporar información posterior al incendio.

{spec['leeme_extra']}
## Incertidumbres

""" + "\n".join(f"- {i}" for i in spec["incertidumbres"]) + "\n"
    (out / "LEEME.md").write_text(txt, encoding="utf-8")


# ====================================================================== manifiesto
def escribir_manifiesto(grilla: Grilla, entradas: list[Entrada]):
    man = Manifiesto(raiz=RAIZ, version=VERSION_MANIFIESTO, grilla=grilla, entradas={e.nombre: e for e in entradas},
                     codigos_combustible=sb40.codigos_conocidos(), fecha=HOY,
                     notas=["Generado por scripts/preparar_datos.py; es el único script con rutas de origen.",
                            "El simulador lee solo las entradas listadas acá y verifica sha256, grilla, dtype, nodata y rangos al iniciar.",
                            "Las entradas 'caso_*' pertenecen a conjunto_prueba/<caso>/ y se referencian desde su caso.yaml."])
    man.guardar(RAIZ / "manifiesto_datos.yaml")
    log(f"== Manifiesto: {len(entradas)} entradas → manifiesto_datos.yaml ==")
    Manifiesto.cargar(RAIZ / "manifiesto_datos.yaml").validar(verbose=False)
    log("   validación OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo-dominio", action="store_true")
    ap.add_argument("--caso", action="append", help="preparar solo este caso (repetible); por defecto todos")
    ap.add_argument("--sin-descarga", action="store_true", help="no consulta Open-Meteo; usa la meteo de conjunto_pruebas")
    a = ap.parse_args()
    entradas: list[Entrada] = []
    grilla = preparar_dominio(entradas)
    if not a.solo_dominio:
        for nombre, spec in CASOS.items():
            if a.caso and nombre not in a.caso:
                continue
            preparar_caso(nombre, dict(spec), grilla, entradas, descargar=not a.sin_descarga)
    for carpeta in ("escenarios", "salidas"):
        (RAIZ / carpeta).mkdir(exist_ok=True)
    escribir_manifiesto(grilla, entradas)


if __name__ == "__main__":
    main()
