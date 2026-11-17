"""Compuestos de verano (enero a marzo) de NDVI y NDMI por Google Earth Engine, para la regla 3.3b de v4.0.

    python herramientas/verano_gee.py --anio 2026                 genera NDVI_NDMI_2026_01, _02 y _03
    python herramientas/verano_gee.py --anio 2026 --reemplazar    también si ya existen (los pisa)
    python herramientas/verano_gee.py --verificar 2024-02         regenera un mes ya entregado y lo compara celda a celda
    python herramientas/verano_gee.py --solo-revisar              comprueba biblioteca, credenciales y acceso, sin generar nada

Por qué existe: E-E3-2 no se cumplió para v4.0 ni después de la revisión única de la máscara de nubes (D-E3-32, D-E3-33), así
que la vía verificada para los índices de v4.0 es Earth Engine. El combustible SB40 de v4.0 sale de estos tres compuestos,
no del compuesto de ventana. Se hacen una vez por año y se suben al repositorio: quien clona no necesita cuenta de GEE.

No escribe código de Earth Engine propio: ejecuta, sin tocarlo, el programa congelado de v4.0
`src/v4.0/app/preprocesamiento/indices_mensuales_banco.py`, que usa las funciones de `descargar_ndvi_ndmi_gee.py` (el
método con el que se calibró v4.0: Sentinel-2 SR armonizado, Cloud Score+ `cs_cdf >= 0,60`, mediana mensual, 2 bandas
× 10000 en int16, nodata −32768, grilla exacta del dominio). Va en un subproceso con `-I`, como pide ese programa.

Salida: `datos/inputSimulacion/sim_v4/dinamicos/indices/NDVI_NDMI_AAAA_MM.tif` y, al lado, `<archivo>.json` con la
procedencia (fuente, método, escenas, sha256). El simulador lee esa procedencia para saber si un verano viene de GEE o de
AWS (`app/datos/evento_rt.py`): un verano hecho por AWS sigue funcionando, rotulado "en prueba".

Necesita la biblioteca `earthengine-api` (opcional en `requirements.txt`) y credenciales (`earthengine authenticate`). El
proyecto de Google Cloud sale de `--proyecto`, de la variable `EARTHENGINE_PROJECT` o del guardado con
`earthengine set_project`. No se anota en la procedencia.
Código de salida: 0 bien, 1 no se generó algo (por ejemplo, ya existía), 2 error.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
V40 = REPO / "src" / "v4.0"
PROGRAMA = V40 / "app" / "preprocesamiento" / "indices_mensuales_banco.py"
METODO = V40 / "app" / "preprocesamiento" / "descargar_ndvi_ndmi_gee.py"
DESTINO = REPO / "datos" / "inputSimulacion" / "sim_v4" / "dinamicos" / "indices"
TRABAJO = REPO / "resultados" / "app" / "verano_gee"
FUENTE = "Sentinel-2 SR armonizado, Google Earth Engine, Cloud Score+ cs_cdf >= 0,60, compuesto mensual"
MESES_VERANO = (1, 2, 3)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def proyecto_de_credenciales() -> str | None:
    cred = Path.home() / ".config" / "earthengine" / "credentials"
    try:
        return json.loads(cred.read_text(encoding="utf-8")).get("project") or None
    except (OSError, ValueError):
        return None


def revisar(proyecto: str | None) -> list[str]:
    """Problemas que impiden generar (lista vacía = todo listo)."""
    faltas = []
    for p in (PROGRAMA, METODO):
        if not p.exists():
            faltas.append(f"falta {p.relative_to(REPO).as_posix()}")
    try:
        import ee  # noqa: F401
    except ImportError:
        return faltas + ["falta la biblioteca earthengine-api (pip install earthengine-api==1.7.43)"]
    if not (Path.home() / ".config" / "earthengine" / "credentials").exists():
        return faltas + ["faltan las credenciales de Earth Engine (ejecutar: earthengine authenticate)"]
    if not proyecto:
        return faltas + ["no hay proyecto de Google Cloud: usar --proyecto, EARTHENGINE_PROJECT o `earthengine set_project`"]
    try:
        import ee
        ee.Initialize(project=proyecto)
        ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED").limit(1).size().getInfo()
    except Exception as e:                                   # depende de la red y de la cuenta
        faltas.append(f"Earth Engine no respondió con ese proyecto: {type(e).__name__}: {str(e)[:200]}")
    return faltas


def ejecutar(args: list[str], salida: Path, proyecto: str) -> tuple[int, str]:
    """Corre el programa congelado de v4.0 en un subproceso aislado. Devuelve (código, texto)."""
    orden = [sys.executable, "-I", str(PROGRAMA.relative_to(V40)), "--salida", str(salida), "--proyecto", proyecto, *args]
    r = subprocess.run(orden, cwd=V40, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=os.environ | {"PYTHONIOENCODING": "utf-8"})
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def procedencia(tif: Path, mes: str, escenas: int | None) -> dict:
    import rasterio
    with rasterio.open(tif) as s:
        grilla = {"crs": str(s.crs), "res": abs(s.transform.a), "xmin": s.bounds.left, "ymin": s.bounds.bottom,
                  "xmax": s.bounds.right, "ymax": s.bounds.top, "ncol": s.width, "nfil": s.height}
        a = s.read(1)
        sin_dato = round(100.0 * float((a == s.nodata).mean()), 4)
    d = {"producto": tif.name, "fuente": FUENTE, "generado_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "codigo": "herramientas/verano_gee.py, que ejecuta src/v4.0/app/preprocesamiento/indices_mensuales_banco.py sin modificarlo",
         "parametros": {"producto": "mensual", "mes": mes, "grilla": grilla,
                        "metodo": {"nombre": "mensual", "via": "gee", "ndvi": "(B8-B4)/(B8+B4)", "ndmi": "(B8A-B11)/(B8A+B11)",
                                   "mascara": "Cloud Score+ cs_cdf >= 0.60", "compuesto": "mediana de las escenas del mes",
                                   "programa": "descargar_ndvi_ndmi_gee.py (v4.0, congelado)", "programa_sha256": sha256(METODO)}},
         "sha256": sha256(tif), "n_escenas": escenas, "celdas_sin_dato_pct": sin_dato}
    Path(str(tif) + ".json").write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return d


def generar(anio: int, proyecto: str, reemplazar: bool) -> int:
    meses = [f"{anio}-{m:02d}" for m in MESES_VERANO]
    nombres = {m: f"NDVI_NDMI_{m.replace('-', '_')}.tif" for m in meses}
    existen = [n for n in nombres.values() if (DESTINO / n).exists()]
    if existen and not reemplazar:
        print("ya existen: " + ", ".join(existen) + ". Para pisarlos, agregar --reemplazar.")
        return 1
    TRABAJO.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f"{anio}_", dir=TRABAJO))
    print(f"generando {', '.join(meses)} por Earth Engine (carpeta de trabajo {tmp.relative_to(REPO).as_posix()})", flush=True)
    codigo, texto = ejecutar(["--meses", *meses], tmp, proyecto)
    print(texto.strip())
    if codigo != 0:
        print(f"el programa de v4.0 terminó con código {codigo}")
        return 2
    hist = json.loads((tmp / "procedencia_indices.json").read_text(encoding="utf-8"))
    info = hist[-1]["meses"]
    faltan = [m for m in meses if not (tmp / nombres[m]).exists()]
    if faltan:
        print("no se generó: " + ", ".join(faltan) + " (¿mes sin escenas?). No se copió nada al repositorio.")
        return 1
    DESTINO.mkdir(parents=True, exist_ok=True)
    for m in meses:
        destino = DESTINO / nombres[m]
        shutil.copyfile(tmp / nombres[m], destino)
        d = procedencia(destino, m, (info.get(m) or {}).get("escenas"))
        print(f"  {destino.relative_to(REPO).as_posix()}: {d['n_escenas']} escenas, {d['celdas_sin_dato_pct']} % sin dato, sha256 {d['sha256'][:16]}…")
    return 0


def verificar(mes: str, proyecto: str) -> int:
    TRABAJO.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f"verificar_{mes}_", dir=TRABAJO))
    codigo, texto = ejecutar(["--verificar", mes], tmp, proyecto)
    print(texto.strip())
    if codigo != 0:
        return 2
    v = json.loads((tmp / "procedencia_indices.json").read_text(encoding="utf-8"))[-1].get("verificacion") or {}
    return 0 if v.get("grilla_igual") and v.get("frac_identicas") == 1.0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Compuestos de verano de v4.0 por Google Earth Engine")
    ap.add_argument("--anio", type=int, help="año del verano (enero a marzo de ese año)")
    ap.add_argument("--reemplazar", action="store_true", help="pisar los compuestos que ya existan")
    ap.add_argument("--verificar", metavar="AAAA-MM", help="regenerar un mes ya entregado y compararlo celda a celda")
    ap.add_argument("--solo-revisar", action="store_true")
    ap.add_argument("--proyecto", default=None, help="proyecto de Google Cloud (por defecto EARTHENGINE_PROJECT o el guardado)")
    a = ap.parse_args()
    proyecto = a.proyecto or os.environ.get("EARTHENGINE_PROJECT") or proyecto_de_credenciales()
    faltas = revisar(proyecto)
    if faltas:
        print("No se puede usar Earth Engine:\n  " + "\n  ".join(faltas))
        return 2
    print("Earth Engine: biblioteca, credenciales y proyecto listos")
    if a.solo_revisar:
        return 0
    if a.verificar:
        return verificar(a.verificar, proyecto)
    if not a.anio:
        ap.error("falta --anio (o --verificar, o --solo-revisar)")
    return generar(a.anio, proyecto, a.reemplazar)


if __name__ == "__main__":
    raise SystemExit(main())
