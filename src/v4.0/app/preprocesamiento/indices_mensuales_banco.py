"""Compuestos mensuales NDVI/NDMI (Sentinel-2) para meses que no están en la entrega, con el MISMO método de
`descargar_ndvi_ndmi_gee.py` (copia idéntica de `AS/NDMI - NDVI/`): Cloud Score+ cs_cdf >= 0,60, mediana mensual,
2 bandas ×10000 int16, nodata −32768, grilla exacta del dominio (EPSG:5345, 30 m, 1672 × 1671).

Reutiliza `coleccion` y `descargar_mensuales` de ese script sin modificarlo. Las salidas van a una carpeta de
`datos/entradas/indices_extra/` (nunca a `Contexto/extraido/`).

Uso (desde src/v4.0; `--salida` por defecto `entradas.indices_extra` = datos/inputSimulacion/banco_v4/entradas/indices_extra):
    python -I app/preprocesamiento/indices_mensuales_banco.py \
        --meses 2023-09 2023-10 2024-08 [--proyecto miprojecto-508714]
Con --verificar 2023-01 regenera un mes ya entregado y lo compara celda a celda con el de `AS/` (en v4.0, la copia de
la entrega que usa SIM: primera carpeta de `entradas.indices_mensuales`). Necesita earthengine-api y credenciales de GEE.
Meses que faltan en este equipo para correr el banco con `--indices previo`: 2023-09, 2023-10 (26588, 26601) y 2024-08 (41914).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import descargar_ndvi_ndmi_gee as base  # noqa: E402  (copia idéntica del script de AS/, sha256 c972b40a…)


def geometria_dominio(raiz: Path):
    import ee
    sys.path.insert(0, str(AQUI.parent))
    from rutas import Rutas
    g = Rutas(raiz).dominio_geojson
    d = json.loads(g.read_text(encoding="utf-8"))
    for f in d["features"]:
        if f["properties"].get("tipo") == "dominio_exacto_25_celdas":
            return ee.Geometry(f["geometry"], None, False)
    raise SystemExit("no se encontró el dominio exacto en el GeoJSON")


def bajar_mes(col, aoi, mes: str, carpeta: Path):
    d = dt.date.fromisoformat(mes + "-01")
    sig = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return base.descargar_mensuales(col, aoi, str(d), str(sig), carpeta)


def main(argv=None):
    import ee
    import numpy as np
    import rasterio
    ap = argparse.ArgumentParser()
    ap.add_argument("--raiz", default=None, help="carpeta src/v4.0 (por defecto, la de este código)")
    ap.add_argument("--salida", default=None)
    ap.add_argument("--meses", nargs="*", default=[])
    ap.add_argument("--verificar", default=None, help="mes AAAA-MM ya entregado para comparar con AS/")
    ap.add_argument("--proyecto", default=base.PROJECT)
    a = ap.parse_args(argv)
    sys.path.insert(0, str(AQUI.parent))
    from rutas import Rutas
    RT = Rutas(a.raiz); R = RT.raiz
    out = (R / a.salida).resolve() if a.salida else RT.indices_extra
    out.mkdir(parents=True, exist_ok=True)
    ee.Initialize(project=a.proyecto)
    aoi = geometria_dominio(R)
    res = {"metodo": "descargar_ndvi_ndmi_gee.py (AS/), sha256 " + hashlib.sha256((AQUI / "descargar_ndvi_ndmi_gee.py").read_bytes()).hexdigest(),
           "proyecto": a.proyecto, "meses": {}}
    if a.verificar:
        vdir = out / "_verificacion"
        vdir.mkdir(exist_ok=True)
        d = dt.date.fromisoformat(a.verificar + "-01")
        sig = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        col = base.coleccion(aoi, str(d), str(sig))
        bajar_mes(col, aoi, a.verificar, vdir)
        nombre = f"NDVI_NDMI_{d:%Y_%m}.tif"
        orig = RT.carpetas_indices[0] / nombre            # copia de la entrega (AS/) en datos/inputSimulacion/sim_v4/dinamicos/indices
        with rasterio.open(vdir / nombre) as s1, rasterio.open(orig) as s2:
            A, B = s1.read(), s2.read()
            igual_grilla = s1.transform == s2.transform and s1.shape == s2.shape and s1.crs == s2.crs
        v = (A != -32768) & (B != -32768)
        dif = np.abs(A.astype(int) - B.astype(int))[v]
        res["verificacion"] = {"mes": a.verificar, "grilla_igual": bool(igual_grilla), "celdas_validas": int(v.sum()),
                               "frac_identicas": float((dif == 0).mean()), "dif_max_x10000": int(dif.max()) if dif.size else None,
                               "dif_p99_x10000": float(np.percentile(dif, 99)) if dif.size else None}
        print(json.dumps(res["verificacion"], ensure_ascii=False))
    for mes in a.meses:
        d = dt.date.fromisoformat(mes + "-01")
        sig = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        col = base.coleccion(aoi, str(d), str(sig))
        r = bajar_mes(col, aoi, mes, out)
        f = out / f"NDVI_NDMI_{d:%Y_%m}.tif"
        res["meses"][mes] = {"escenas": int(r.escenas.iloc[0]), "archivo": f.name,
                             "sha256": hashlib.sha256(f.read_bytes()).hexdigest() if f.exists() else None}
        print(mes, res["meses"][mes])
    res["fecha_descarga"] = dt.datetime.now().isoformat(timespec="seconds")
    previo = out / "procedencia_indices.json"
    hist = json.loads(previo.read_text(encoding="utf-8")) if previo.exists() else []
    hist.append(res)
    previo.write_text(json.dumps(hist, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
