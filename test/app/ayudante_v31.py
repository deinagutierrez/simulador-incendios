"""Ayudante de test_intervenciones_v31.py: comprobaciones que necesitan el motor v3.1 cargado en el mismo proceso.

Se corre como proceso aparte (cada proceso carga un solo `incendios_sl`) y escribe un JSON en la salida estándar:

    python test/app/ayudante_v31.py vacia <variante> <horas> <carpeta>
        Las Lagunas 2024 (hipótesis 1): la misma corrida con las barreras apagadas (como la deja `cargar_entradas_evento`)
        y con la matriz de barreras vacía completa de la app (`IntervencionesV31.habilitar_barreras`). Devuelve las celdas
        con distinto tiempo de llegada y estado, y los segundos de cada una.

    python test/app/ayudante_v31.py codigos <carpeta> <trazos.json>
        Para cada trazo (cortafuego normalizado), los enlaces de la función real envuelta (`enlaces_funcion_real`) y los
        de una copia del núcleo de `preparar_barreras_enlaces` limitada a una ventana alrededor del trazo (la de 8 ms del
        pedido F5, punto 7). Devuelve si coinciden, los tiempos y si cambió algo en datos/inputSimulacion/barreras.

No usa red ni escribe fuera de `<carpeta>`.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app" / "motores"))
DEFINICION = {"evento": "SL-2024-LASLAGUNAS", "hipotesis": 1, "validar": False, "figuras": False}


def _foto(carpeta: Path) -> dict:
    """Nombre → (bytes, mtime, sha256) de cada archivo de la carpeta (para ver que no se tocó)."""
    if not carpeta.exists():
        return {}
    return {str(p.relative_to(carpeta)): (p.stat().st_size, p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
            for p in sorted(carpeta.rglob("*")) if p.is_file()}


def vacia(variante: str, horas: float, carpeta: Path) -> dict:
    import motor_v31
    import barreras_v31
    out = {}
    llegadas, estados = [], []
    for caso in ("apagadas", "vacia"):
        c = motor_v31.cargar({"definicion": {**DEFINICION, "horas": horas}}, {}, carpeta, variante)
        from incendios_sl.simulation.motor import Simulacion
        sim = Simulacion(c["ent"], c["cfg"])
        if caso == "vacia":
            assert not sim.usar_barreras, "la variante ya trae barreras"
            barreras_v31.IntervencionesV31(sim, c["cfg"], c["g"], c["dom"], carpeta).habilitar_barreras()
            assert sim.usar_barreras and sim.barrera.shape == sim.estado.shape + (c["cfg"].vecindad,)
        t0 = time.perf_counter()
        sim.ejecutar()
        out[f"s_{caso}"] = round(time.perf_counter() - t0, 2)
        llegadas.append(sim.t_arr.copy())
        estados.append(sim.estado.copy())
    a, b = llegadas
    out["celdas_quemadas"] = int(np.isfinite(a).sum())
    out["distintas_llegada"] = int((~((a == b) | (np.isinf(a) & np.isinf(b)))).sum())
    out["distintas_estado"] = int((estados[0] != estados[1]).sum())
    return out


def enlaces_ventana(g, xy, vecindad: int, factor_fino: int, margen: int = 6) -> np.ndarray:
    """Copia del núcleo de `preparar_barreras_enlaces` (src/v3.1/.../data/preparar_dominio.py) para un solo trazo: el raster
    fino de la grilla entera y los enlaces solo en una ventana de celdas alrededor del trazo. Mismas cuentas, en coordenadas
    globales, para dar lo mismo bit a bit.
    Devuelve los índices planos de los enlaces con barrera en (filas, cols, vecindad)."""
    from rasterio import features
    from rasterio.transform import Affine
    from shapely.geometry import LineString
    from incendios_sl.simulation.automata import estencil
    linea = LineString(xy)
    bx0, by0, bx1, by1 = linea.bounds
    c0 = max(int(np.floor((bx0 - g.xmin) / g.res)) - margen, 0)
    c1 = min(int(np.floor((bx1 - g.xmin) / g.res)) + margen + 1, g.ncol)
    r0 = max(int(np.floor((g.ymax - by1) / g.res)) - margen, 0)
    r1 = min(int(np.floor((g.ymax - by0) / g.res)) + margen + 1, g.nfil)
    if r0 >= r1 or c0 >= c1:
        return np.zeros(0, dtype="int64")
    res_f = g.res / factor_fino
    shape_f = (g.nfil * factor_fino, g.ncol * factor_fino)
    # el raster fino se arma con la transformación de la grilla entera, como la función: con el origen de la ventana, GDAL
    # redondea distinto las coordenadas de píxel y all_touched cambia algunos píxeles cuando el trazo pasa justo por una
    # esquina (pasó con un trazo casi horizontal: 12 enlaces de más). Solo las cuentas de los enlaces van por ventana.
    fino = features.rasterize([(linea.__geo_interface__, 1)], out_shape=shape_f,
                              transform=Affine(res_f, 0.0, g.xmin, 0.0, -res_f, g.ymax), fill=0, all_touched=True,
                              dtype="uint8")[r0 * factor_fino:r1 * factor_fino, c0 * factor_fino:c1 * factor_fino]
    dy, dx, dist, _ = estencil(vecindad, g.res)
    rr, cc = np.mgrid[r0:r1, c0:c1]
    x0 = g.xmin + (cc + 0.5) * g.res; y0 = g.ymax - (rr + 0.5) * g.res
    partes = []
    for k in range(vecindad):
        n_s = int(np.ceil(dist[k] / res_f)) + 1
        s_vals = np.linspace(0.0, 1.0, n_s + 2)[1:-1]
        dentro = (rr + dy[k] >= 0) & (rr + dy[k] < g.nfil) & (cc + dx[k] >= 0) & (cc + dx[k] < g.ncol)
        acum = np.zeros(rr.shape, np.uint8)
        for s in s_vals:
            xs = x0 + s * dx[k] * g.res; ys = y0 - s * dy[k] * g.res
            cf = np.clip(np.floor((xs - g.xmin) / res_f).astype(np.int64), 0, shape_f[1] - 1) - c0 * factor_fino
            rf = np.clip(np.floor((g.ymax - ys) / res_f).astype(np.int64), 0, shape_f[0] - 1) - r0 * factor_fino
            ok = (cf >= 0) & (cf < fino.shape[1]) & (rf >= 0) & (rf < fino.shape[0])
            np.maximum(acum, np.where(ok, fino[np.clip(rf, 0, fino.shape[0] - 1), np.clip(cf, 0, fino.shape[1] - 1)], 0), out=acum)
        f, c = np.nonzero(np.where(dentro, acum, 0))
        partes.append(((rr[f, c] * g.ncol + cc[f, c]) * vecindad + k).astype("int64"))
    return np.sort(np.concatenate(partes))


def codigos(carpeta: Path, trazos: list[dict]) -> dict:
    import barreras_v31
    sys.path.insert(0, str(REPO / "src" / "v3.1" / "src"))
    from incendios_sl import config as cfgmod
    from incendios_sl.data.preparar_dominio import grilla_dominio
    compartido = REPO / "datos" / "inputSimulacion" / "barreras"
    antes = _foto(compartido)
    entorno_antes = os.environ.get("INCENDIOS_SL_INPUT")
    dom = cfgmod.cargar_dominio(cfgmod.cargar_evento(DEFINICION["evento"])["dominio"])
    g = grilla_dominio(dom)
    vecindad = int(cfgmod.cargar_modelo("modelo_v2")["automata"]["vecindad"])
    casos = []
    for n, d in enumerate(trazos, start=1):
        real, s_real = barreras_v31.enlaces_funcion_real(dom, g.crs, vecindad, carpeta, d, n)
        t0 = time.perf_counter()
        copia = enlaces_ventana(g, d["xy_5345"], vecindad, barreras_v31.FACTOR_FINO)
        s_copia = time.perf_counter() - t0
        casos.append({"enlaces_real": int(len(real)), "enlaces_copia": int(len(copia)), "iguales": bool(np.array_equal(real, copia)),
                      "s_real": round(s_real, 3), "s_copia": round(s_copia, 4)})
    return {"casos": casos, "compartido_sin_cambios": _foto(compartido) == antes, "archivos_compartido": len(antes),
            "entorno_restaurado": os.environ.get("INCENDIOS_SL_INPUT") == entorno_antes,
            "productos_que_quedaron": sorted(str(p.relative_to(carpeta)) for p in carpeta.rglob("barreras_enlaces_*"))}


def main() -> int:
    orden = sys.argv[1]
    if orden == "vacia":
        out = vacia(sys.argv[2], float(sys.argv[3]), Path(sys.argv[4]))
    elif orden == "codigos":
        out = codigos(Path(sys.argv[2]), json.loads(Path(sys.argv[3]).read_text(encoding="utf-8")))
    else:
        raise SystemExit(f"orden desconocida: {orden}")
    sys.stdout.write("\nRESULTADO " + json.dumps(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
