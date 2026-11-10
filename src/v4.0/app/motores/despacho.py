"""Despacho de L03 (protocolo v1.3 §2.4): tiempo de llegada de los cuarteles de bomberos a una ignición por la red vial.

Red: `caminos_sanluis_integrado.geojson` (provincial; se excluye el ferrocarril). Grafo no dirigido sobre los vértices
de las líneas (redondeados a 1 m en EPSG:5345), con peso = longitud / velocidad de la clase de camino. Los tramos
`dup_probable` se conservan: duplicar una arista no cambia el camino mínimo. El grafo se guarda en caché (npz).
Del cuartel al nodo más cercano y del último nodo a la ignición se camina a 4 km/h. Valores = supuestos (§2.4).

Rutas (v4.0, `config/rutas.yaml`): red `crudos.caminos`, cuarteles `crudos.cuarteles`, caché `entradas.red_vial_grafo`.
La caché se lee ANTES de mirar el GeoJSON: si el GeoJSON no está, se usa la caché tal cual (no se puede validar la clave);
si está, la clave (velocidades + tamaño del GeoJSON) tiene que coincidir o el grafo se reconstruye.

    from despacho import llegadas
    llegadas(rutas, x_ign, y_ign, n=3) -> [{"cuartel", "localidad", "viaje_min", "acceso_m", "dist_recta_km"}, ...]
`dist_recta_km` es la distancia en línea recta cuartel–ignición (no la longitud del camino).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

VELOCIDAD_KMH = {"autopista": 80, "ruta": 60, "calle": 30, "camino": 30, "servicio": 25, "huella": 15, "vado": 10, "otro": 10, "senda": 5}
A_PIE_KMH = 4.0
DEMORA_DESPACHO_MIN = 30.0


def clave_grafo(origen: Path) -> str:
    return hashlib.sha256((str(VELOCIDAD_KMH) + str(Path(origen).stat().st_size)).encode()).hexdigest()[:16]


def _grafo(rutas):
    """(coords Nx2, sparse csr de tiempos en minutos), con caché en `entradas.red_vial_grafo` (npz)."""
    import scipy.sparse as sp
    cache = Path(rutas.red_vial_grafo)
    try:
        origen = Path(rutas.caminos)
    except FileNotFoundError:
        origen = None
    hay_origen = origen is not None and origen.exists()
    if cache.exists():
        z = np.load(cache, allow_pickle=False)
        if not hay_origen or str(z["clave"]) == clave_grafo(origen):
            n = len(z["xy"])
            return z["xy"], sp.csr_matrix((z["w"], (z["i"], z["j"])), shape=(n, n))
    if not hay_origen:
        raise FileNotFoundError(f"despacho: no hay caché del grafo vial ({cache}) ni red vial ({origen})")
    clave = clave_grafo(origen)
    import geopandas as gpd
    from shapely import get_coordinates
    g = gpd.read_file(origen, columns=["clase"]).to_crs("EPSG:5345")
    g = g[g.clase.isin(VELOCIDAD_KMH.keys())]
    nodos: dict[tuple[int, int], int] = {}
    I, J, W = [], [], []
    for geom, clase in zip(g.geometry, g.clase):
        if geom is None or geom.is_empty:
            continue
        v_m_min = VELOCIDAD_KMH[clase] * 1000 / 60
        partes = geom.geoms if geom.geom_type.startswith("Multi") else [geom]
        for parte in partes:
            xy = np.round(get_coordinates(parte)).astype(np.int64)
            ids = []
            for x, y in xy:
                k = (int(x), int(y))
                if k not in nodos:
                    nodos[k] = len(nodos)
                ids.append(nodos[k])
            d = np.hypot(np.diff(xy[:, 0]), np.diff(xy[:, 1]))
            I += ids[:-1]; J += ids[1:]; W += list(d / v_m_min)
    xy = np.array(list(nodos.keys()), dtype=np.float64)
    I = np.array(I + J); J2 = np.array(J + I[: len(J)].tolist()); W = np.array(W + W)
    np.savez_compressed(cache, xy=xy, i=I, j=J2, w=W, clave=clave)
    n = len(xy)
    return xy, sp.csr_matrix((W, (I, J2)), shape=(n, n))


def _nodo(arbol, xy_q, ok: np.ndarray | None, k0: int = 16) -> tuple[float, int]:
    """Nodo más cercano a `xy_q`; con `ok` (máscara de nodos válidos), el más cercano entre los válidos."""
    if ok is None:
        d, i = arbol.query(xy_q)
        return float(d), int(i)
    k = k0
    while True:
        d, i = arbol.query(xy_q, k=min(k, arbol.n))
        sel = ok[i]
        if sel.any():
            j = int(np.argmax(sel))
            return float(d[j]), int(i[j])
        if k >= arbol.n:
            return float("inf"), -1
        k *= 4


def llegadas(rutas, x_ign: float, y_ign: float, n: int = 3, nodo: str = "alcanzable") -> list[dict]:
    """Los n cuarteles con menor tiempo de viaje (minutos, sin la demora de despacho) a la ignición (EPSG:5345).

    `nodo`: cómo se entra a la red. `cercano` (V.4) = el vértice más cercano, aunque sea un tramo aislado (el cuartel queda
    sin llegada: con `bomberos_san_luis.geojson` el Cuartel N° 28 cae a 21 m de un tramo suelto). `alcanzable` (v4.0) = la
    ignición entra por el vértice más cercano de la componente conexa más grande y cada cuartel por el vértice más cercano
    de esa misma componente (se camina hasta él a 4 km/h)."""
    import geopandas as gpd
    from scipy.sparse.csgraph import connected_components, dijkstra
    from scipy.spatial import cKDTree
    if nodo not in ("cercano", "alcanzable"):
        raise ValueError(f"despacho: nodo '{nodo}' (cercano | alcanzable)")
    xy, G = _grafo(rutas)
    arbol = cKDTree(xy)
    ok = None
    if nodo == "alcanzable":
        _, comp = connected_components(G, directed=False)
        ok = comp == np.bincount(comp).argmax()
    d_ign, n_ign = _nodo(arbol, [x_ign, y_ign], ok)
    tiempos = dijkstra(G, directed=False, indices=int(n_ign))
    c = gpd.read_file(rutas.cuarteles).to_crs("EPSG:5345")
    # V.4 leía `localidad_mas_cercana` (cuarteles_bomberos_san_luis.geojson); datos/crudos/bomberos_san_luis.geojson trae `localidad`
    col_loc = next((k for k in ("localidad_mas_cercana", "localidad") if k in c.columns), None)
    filas = []
    for _, r in c.iterrows():
        if r.geometry is None or r.geometry.is_empty:
            continue
        d_c, n_c = _nodo(arbol, [r.geometry.x, r.geometry.y], ok)
        if n_c < 0:
            continue
        t = tiempos[n_c]
        if not np.isfinite(t):
            continue
        a_pie = (d_c + d_ign) / (A_PIE_KMH * 1000 / 60)
        nombre = next((str(r[k]).strip() for k in ("cuartel", "nombre") if k in c.columns and isinstance(r[k], str) and r[k].strip()), str(_))
        loc = r[col_loc] if col_loc and isinstance(r[col_loc], str) else None
        filas.append({"cuartel": nombre, "localidad": loc, "viaje_min": float(t + a_pie),
                      "acceso_m": float(d_c + d_ign), "dist_recta_km": float(np.hypot(r.geometry.x - x_ign, r.geometry.y - y_ign) / 1000)})
    return sorted(filas, key=lambda f: f["viaje_min"])[:n]
