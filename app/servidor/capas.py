"""Capas de fondo para el mapa: relieve, pendiente, cobertura, tiempo de arribo, índices y combustible del evento,
cicatriz, y los vectores (caminos, viviendas, red de media tensión, cuarteles, borde del dominio).

Los rásteres están en la grilla del dominio (EPSG:5345). Un mapa web los necesita en Web Mercator, así que cada capa se
pasa a esa proyección, se pinta y se guarda como PNG en `datos/procesados/app/capas/` (caché que se rehace sola si el
archivo de origen cambia). Los vectores se entregan como GeoJSON en grados. No se carga ningún motor.
"""
from __future__ import annotations

import io
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
ENTRADAS = REPO / "datos" / "inputSimulacion"
CACHE = REPO / "datos" / "procesados" / "app" / "capas"

# Clases de combustible de v3.1 (src/v3.1/src/incendios_sl/fuels/tabla.py, CLASES_V1) y cómo agrupa la cobertura MapBiomas.
COLOR_CLASE = {0: (158, 158, 158), 1: (230, 211, 107), 2: (242, 233, 160), 3: (201, 163, 90), 4: (154, 107, 47),
               5: (127, 176, 105), 6: (47, 125, 74), 7: (27, 94, 90)}
NOMBRE_CLASE = {0: "No combustible", 1: "Pastizal natural", 2: "Pastura o cultivo", 3: "Arbustal abierto",
                4: "Arbustal cerrado", 5: "Bosque abierto", 6: "Bosque cerrado", 7: "Plantación"}
COBERTURA = {3: ("Bosque cerrado", (47, 125, 74)), 4: ("Bosque abierto", (127, 176, 105)), 9: ("Plantación forestal", (27, 94, 90)),
             12: ("Pastizal natural", (230, 211, 107)), 15: ("Pastura", (242, 233, 160)), 19: ("Cultivo", (222, 170, 200)),
             24: ("Urbano", (192, 57, 43)), 25: ("Suelo desnudo o roca", (200, 185, 166)), 33: ("Agua", (59, 125, 216)),
             63: ("Arbustal abierto", (201, 163, 90)), 77: ("Arbustal abierto", (201, 163, 90)), 66: ("Arbustal cerrado", (154, 107, 47))}


def _rampa(paradas: list[tuple]) -> dict:
    """paradas: (valor, r, g, b, alfa). Devuelve el estilo continuo y su leyenda."""
    return {"tipo": "continua", "paradas": paradas}


def _categorica(colores: dict[int, tuple], nombres: dict[int, str], alfa: int = 190) -> dict:
    return {"tipo": "categorica", "colores": colores, "nombres": nombres, "alfa": alfa}


# id: (título, grupo, patrón del archivo dentro de datos/inputSimulacion, estilo, unidad, por_evento)
RASTERES = {
    "relieve": ("Relieve sombreado", "Terreno", "dem/dem_copernicus_glo30_las_lagunas_potrerillos.tif",
                {"tipo": "sombreado"}, None, False),
    "pendiente": ("Pendiente", "Terreno", "dem/pendiente_copernicus_glo30_las_lagunas_potrerillos.tif",
                  _rampa([(0, 255, 255, 255, 0), (5, 254, 232, 200, 110), (15, 253, 187, 132, 170), (30, 227, 74, 51, 200), (45, 127, 0, 0, 220)]),
                  "grados", False),
    "cobertura": ("Cobertura del suelo (MapBiomas)", "Vegetación", "cobertura/cobertura_mapbiomas_col3_*_las_lagunas_potrerillos.tif",
                  _categorica({k: v[1] for k, v in COBERTURA.items()}, {k: v[0] for k, v in COBERTURA.items()}), None, False),
    "arribo": ("Tiempo de arribo desde cuarteles", "Infraestructura", "infraestructura/tiempo_arribo_las_lagunas_potrerillos.tif",
               _rampa([(0, 247, 252, 245, 60), (0.5, 199, 233, 192, 150), (1, 116, 196, 118, 170), (2, 35, 139, 69, 190), (4, 0, 68, 27, 210)]),
               "horas", False),
    "ndvi": ("NDVI (verdor)", "Vegetación", "combustibles/{evento}/ndvi_30m_{evento}.tif",
             _rampa([(-0.1, 140, 81, 10, 200), (0.15, 216, 179, 101, 200), (0.3, 246, 232, 195, 200), (0.5, 127, 191, 123, 200), (0.8, 27, 120, 55, 210)]),
             "índice", True),
    "ndmi": ("NDMI (humedad de la vegetación)", "Vegetación", "combustibles/{evento}/ndmi_30m_{evento}.tif",
             _rampa([(-0.3, 166, 97, 26, 200), (-0.1, 223, 194, 125, 200), (0.05, 245, 245, 245, 200), (0.2, 128, 205, 193, 200), (0.4, 1, 133, 113, 210)]),
             "índice", True),
    "combustible": ("Combustible, 7 clases (v3.1)", "Vegetación", "combustibles/{evento}/combustible_clase_{evento}.tif",
                    _categorica(COLOR_CLASE, NOMBRE_CLASE), None, True),
    "cicatriz": ("Cicatriz observada del incendio histórico", "Histórico", "eventos/{evento}/cicatriz_referencia_{evento}.tif",
                 _categorica({1: (60, 60, 60)}, {1: "Área quemada observada"}, alfa=110), None, True),
}

# id: (título, grupo, archivo, columnas que se conservan, tipo de geometría para dibujar)
VECTORES = {
    "dominio": ("Borde del dominio", "Terreno", None, [], "linea"),
    "caminos": ("Caminos", "Infraestructura", "infraestructura/caminos_las_lagunas_potrerillos.gpkg", ["clase", "nombre", "superficie"], "linea"),
    "red_mt": ("Red eléctrica de media tensión", "Infraestructura", "infraestructura/electricidad_mt_las_lagunas_potrerillos.gpkg", ["tension_kv"], "linea"),
    "viviendas": ("Viviendas", "Infraestructura", "infraestructura/viviendas_las_lagunas_potrerillos.gpkg", ["nombre", "tipo"], "punto"),
    "cuarteles": ("Cuarteles de bomberos", "Infraestructura", "__cuarteles__", ["nombre", "localidad"], "punto"),
}


def _archivo(patron: str, evento: str | None) -> Path | None:
    if "{evento}" in patron:
        if not evento:
            return None
        patron = patron.replace("{evento}", evento)
    candidatos = sorted(ENTRADAS.glob(patron))
    return candidatos[-1] if candidatos else None                  # con varios años de cobertura, el más nuevo


def _leyenda(estilo: dict, unidad: str | None) -> dict | None:
    if estilo["tipo"] == "continua":
        return {"tipo": "continua", "unidad": unidad,
                "paradas": [{"valor": p[0], "color": "#%02x%02x%02x" % p[1:4]} for p in estilo["paradas"]]}
    if estilo["tipo"] == "categorica":
        vistos, items = set(), []
        for k, nombre in estilo["nombres"].items():
            if nombre not in vistos:
                vistos.add(nombre)
                items.append({"nombre": nombre, "color": "#%02x%02x%02x" % estilo["colores"][k]})
        return {"tipo": "categorica", "items": items}
    return None


@lru_cache(maxsize=64)
def _destino(ruta: str):
    """Transformación a Web Mercator de un ráster y su recuadro en grados."""
    import rasterio
    from rasterio.transform import array_bounds
    from rasterio.warp import calculate_default_transform, transform_bounds
    with rasterio.open(ruta) as src:
        destino, ancho, alto = calculate_default_transform(src.crs, "EPSG:3857", src.width, src.height, *src.bounds)
    oeste, sur, este, norte = transform_bounds("EPSG:3857", "EPSG:4326", *array_bounds(alto, ancho, destino))
    return destino, int(ancho), int(alto), [[sur, oeste], [norte, este]]


def lista(evento: str | None = None) -> list[dict]:
    """Capas disponibles para el mapa, con su leyenda. Las del evento solo aparecen si sus archivos están."""
    out = []
    for id_, (titulo, grupo, patron, estilo, unidad, por_evento) in RASTERES.items():
        ruta = _archivo(patron, evento)
        if ruta is None:
            continue
        url = f"/api/capas/{id_}.png" + (f"?evento={evento}" if por_evento else "")
        out.append({"id": id_, "titulo": titulo, "grupo": grupo, "tipo": "imagen", "url": url, "por_evento": por_evento,
                    "limites": _destino(str(ruta))[3], "leyenda": _leyenda(estilo, unidad), "archivo": ruta.name})
    for id_, (titulo, grupo, archivo, _, forma) in VECTORES.items():
        out.append({"id": id_, "titulo": titulo, "grupo": grupo, "tipo": "vector", "forma": forma,
                    "url": f"/api/vectores/{id_}.geojson", "por_evento": False, "leyenda": None})
    return out


def _pintar(valores: np.ndarray, estilo: dict) -> np.ndarray:
    """Matriz de valores (NaN = sin dato) → RGBA."""
    alto, ancho = valores.shape
    rgba = np.zeros((alto, ancho, 4), dtype="uint8")
    con_dato = np.isfinite(valores)
    if estilo["tipo"] == "categorica":
        enteros = np.where(con_dato, valores, -1).astype("int32")
        for clase, color in estilo["colores"].items():
            donde = enteros == clase
            rgba[donde, :3] = color
            rgba[donde, 3] = estilo["alfa"]
        return rgba
    paradas = np.array(estilo["paradas"], dtype="float64")
    v = valores[con_dato]
    for canal in range(4):
        rgba[..., canal][con_dato] = np.interp(v, paradas[:, 0], paradas[:, canal + 1]).astype("uint8")
    return rgba


def _sombreado(elevacion: np.ndarray, res: float) -> np.ndarray:
    """Relieve sombreado clásico: luz desde el noroeste, a 45° de altura."""
    exageracion = 1.6                                              # para que el relieve se lea
    hacia_abajo, hacia_el_este = np.gradient(elevacion.astype("float64"), res)
    dz_este, dz_norte = hacia_el_este * exageracion, -hacia_abajo * exageracion      # las filas crecen hacia el sur
    acimut, altura = np.radians(315.0), np.radians(45.0)
    luz_este, luz_norte, luz_arriba = np.sin(acimut) * np.cos(altura), np.cos(acimut) * np.cos(altura), np.sin(altura)
    # producto de la normal del terreno (-dz_este, -dz_norte, 1) con la dirección de la luz
    luz = (-dz_este * luz_este - dz_norte * luz_norte + luz_arriba) / np.sqrt(dz_este ** 2 + dz_norte ** 2 + 1.0)
    return np.clip(luz, 0, 1).astype("float32")


def png(id_: str, evento: str | None = None) -> bytes | None:
    """PNG de una capa ráster, desde la caché si está al día."""
    if id_ not in RASTERES:
        return None
    _, _, patron, estilo, _, por_evento = RASTERES[id_]
    ruta = _archivo(patron, evento)
    if ruta is None:
        return None
    guardado = CACHE / (f"{id_}__{evento}.png" if por_evento else f"{id_}__{ruta.stem}.png")
    if guardado.exists() and guardado.stat().st_mtime >= ruta.stat().st_mtime:
        return guardado.read_bytes()

    import rasterio
    from PIL import Image
    from rasterio.warp import Resampling, reproject
    with rasterio.open(ruta) as src:
        datos = src.read(1).astype("float32")
        if src.nodata is not None:
            datos[datos == src.nodata] = np.nan
        origen, crs, res = src.transform, src.crs, abs(src.transform.a)
    if estilo["tipo"] == "sombreado":
        datos = _sombreado(datos, res)
    if id_ == "cicatriz":
        datos[datos != 1] = np.nan
    destino, ancho, alto, _ = _destino(str(ruta))
    salida = np.full((alto, ancho), np.nan, dtype="float32")
    suave = estilo["tipo"] in ("continua", "sombreado")
    reproject(datos, salida, src_transform=origen, src_crs=crs, src_nodata=np.nan, dst_transform=destino, dst_crs="EPSG:3857",
              dst_nodata=np.nan, resampling=Resampling.bilinear if suave else Resampling.nearest)
    if estilo["tipo"] == "sombreado":
        gris = np.where(np.isfinite(salida), 70 + salida * 185, 0).astype("uint8")
        rgba = np.dstack([gris, gris, gris, np.where(np.isfinite(salida), 255, 0).astype("uint8")])
    else:
        rgba = _pintar(salida, estilo)
    memoria = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(memoria, format="PNG")
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = guardado.with_suffix(".tmp")
    tmp.write_bytes(memoria.getvalue())
    tmp.replace(guardado)
    return memoria.getvalue()


def geojson(id_: str) -> str | None:
    """GeoJSON en grados de una capa vectorial, desde la caché si está al día."""
    if id_ not in VECTORES:
        return None
    _, _, archivo, columnas, forma = VECTORES[id_]
    from . import datos
    dom = datos.dominio()
    if archivo is None:                                             # borde del dominio
        (sur, oeste), (norte, este) = dom["limites"]
        from pyproj import Transformer
        a_grados = Transformer.from_crs(dom["crs"], "EPSG:4326", always_xy=True)
        esquinas = [(dom["xmin"], dom["ymin"]), (dom["xmax"], dom["ymin"]), (dom["xmax"], dom["ymax"]), (dom["xmin"], dom["ymax"]),
                    (dom["xmin"], dom["ymin"])]
        anillo = [list(a_grados.transform(x, y)) for x, y in esquinas]
        return json.dumps({"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"nombre": "Dominio Las Lagunas–Potrerillos"}, "geometry": {"type": "LineString", "coordinates": anillo}}]})
    ruta = REPO / "datos" / "crudos" / "bomberos_san_luis.geojson" if archivo == "__cuarteles__" else ENTRADAS / archivo
    if not ruta.exists():
        return None
    guardado = CACHE / f"{id_}.geojson"
    if guardado.exists() and guardado.stat().st_mtime >= ruta.stat().st_mtime:
        return guardado.read_text(encoding="utf-8")

    import warnings
    import geopandas as gpd
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        g = gpd.read_file(ruta)
        if forma == "punto" and not (g.geom_type == "Point").all():
            g["geometry"] = g.geometry.centroid                     # viviendas: polígonos chicos, se dibujan como puntos
        if forma == "linea":
            g["geometry"] = g.geometry.simplify(10.0) if g.crs and g.crs.is_projected else g.geometry
        g = g.to_crs("EPSG:4326")
    if id_ == "cuarteles":                                          # los de la provincia: se dejan los cercanos al dominio
        (sur, oeste), (norte, este) = dom["limites"]
        g = g.cx[oeste - 0.35:este + 0.35, sur - 0.35:norte + 0.35]
    g = g[[c for c in columnas if c in g.columns] + ["geometry"]]
    texto = g.to_json(drop_id=True)
    texto = json.dumps(_redondear(json.loads(texto)), ensure_ascii=False, separators=(",", ":"))
    CACHE.mkdir(parents=True, exist_ok=True)
    guardado.write_text(texto, encoding="utf-8")
    return texto


def _redondear(o, cifras: int = 6):
    """Coordenadas con 6 decimales (unos 10 cm): el archivo pesa la mitad."""
    if isinstance(o, float):
        return round(o, cifras)
    if isinstance(o, list):
        return [_redondear(v, cifras) for v in o]
    if isinstance(o, dict):
        return {k: _redondear(v, cifras) for k, v in o.items()}
    return o
