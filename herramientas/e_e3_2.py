"""Evaluación del prerregistro E-E3-2: los índices por AWS equivalen a los de Google Earth Engine.

    python herramientas/e_e3_2.py --evaluador NOMBRE                 todo: (a), (b) y (c)
    python herramientas/e_e3_2.py --evaluador NOMBRE --sin-corridas  solo (a) y (b)
    python herramientas/e_e3_2.py --solo-revisar                     comprueba archivos, red y motores sin calcular nada

Lo corre la otra persona (prerregistro `docs/etapa3/prerregistros/E-E3-2_indices_aws.md`, D-E3-25), sin pasos manuales:

(a) Compuesto de ventana por AWS de Las Lagunas 2024 (30/07 a 16/09/2024 inclusive, la ventana `["2024-07-30",
    "2024-09-17")` de la ficha), reflectancia DN/10000 sin desplazamiento (elegido en `E-E3-2_escala.md`), leído a 20 m y
    llevado a 30 m con la función de v3.1 `indices_a_grilla` (en un subproceso con el camino de v3.1). Se compara con
    `ndvi_30m` y `ndmi_30m` del evento (GEE).
(b) Compuesto mensual por AWS de septiembre de 2024 contra `sim_v4/dinamicos/indices/NDVI_NDMI_2024_09.tif` (GEE).
(c) Efecto en el modelo. Se arman dos eventos generados `RT-…` con `app/datos/evento_rt.py` (el mismo camino del
    simulador) que solo difieren en los índices: la misma toma de meteorología (la serie del dominio del evento, cargada
    como CSV) y, como índices, una toma cargada a mano con los de GEE (`ndvi_30m`/`ndmi_30m` del evento) y otra con los de
    AWS de (a), los dos a 30 m en int16 × 10000, así recorren el mismo camino. Cada evento se corre 48 h en v4.0 y en v3.1
    librev2 con `app/motores/proceso.py`, con los puntos de ignición de la ficha y la hora de la hipótesis 1
    (`configuracion.ignicion` y `configuracion.t_inicio_utc`). Se mide la fracción de celdas que cambian de clase de
    combustible (7 clases de v3.1; SB40 de v4.0), el IoU de las huellas a 24 h y a 48 h y la diferencia de superficie.
    Verano de v4.0 (opción A, D-E3-27): el SB40 de la regla 3.3b y el NDVI de verano salen de los compuestos de enero a
    marzo, no de la ventana. Para que el lado AWS lo sea también ahí, se generan por AWS enero, febrero y marzo de 2024 con
    el método de SIM y la corrida "AWS" de v4.0 los usa (`herramientas/e_e3_2_motor.py`, que se los da a v4.0 sin tocar los
    del repositorio); la corrida "GEE" usa los de `sim_v4/dinamicos/indices`. Se comprueba en la procedencia del SB40 que
    cada lado haya usado los suyos. v3.1 no usa el verano.
    Al final se borran los eventos y las tomas que se crearon (`evento_rt.borrar`).

Criterio (fijado en el prerregistro): se habilita AWS si (1) la diferencia absoluta mediana es ≤ 0,02 en NDVI y NDMI, en
(a) y en (b); (2) menos del 3 % de las celdas cambia de clase, en cada motor; (3) IoU ≥ 0,95 a las 48 h, en cada motor.

Salidas: `docs/etapa3/prerregistros/E-E3-2_resultados.json` y `E-E3-2_resultado.md`; lo intermedio en
`resultados/app/E-E3-2/`. Código de salida: 0 se cumple todo, 1 no se cumple (o quedó incompleto), 2 error.

Este proceso no importa ningún motor: v3.1 corre en subprocesos (la conversión a 30 m y `proceso_datos.py`), y cada
corrida en su propio `proceso.py`. v3.1 y v4.0 nunca conviven en un proceso.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "app"))

from datos import comun, evento_rt, indices, meteo, sentinel2  # noqa: E402  (no importan motores)

EVENTO = "SL-2024-LASLAGUNAS"
VENTANA = (dt.date(2024, 7, 30), dt.date(2024, 9, 16))       # inclusive; la ficha dice ["2024-07-30", "2024-09-17")
MES = (2024, 9)
DESPLAZAMIENTO = 0.0                                          # E-E3-2_escala.md
HIPOTESIS = 1                                                 # 2024-09-18T15:00:00Z
HORAS = 48
CORTES_H = (24, 48)
UMBRAL_DIF = 0.02
UMBRAL_CLASE = 0.03
UMBRAL_IOU = 0.95
# motor → (versión, ráster de llegada, factor a minutos)
MOTORES = {"v4.0": ("v4.0", "hora_llegada_min.tif", 1.0), "v3.1-librev2": ("v3.1", "t_llegada_s.tif", 1 / 60.0)}
TRABAJO = REPO / "resultados" / "app" / "E-E3-2"
DOCS = REPO / "docs" / "etapa3" / "prerregistros"
SALIDA_JSON = DOCS / "E-E3-2_resultados.json"
SALIDA_MD = DOCS / "E-E3-2_resultado.md"
ENT = comun.ENTRADAS
MOTOR_VERANO = REPO / "herramientas" / "e_e3_2_motor.py"
ANIO_VERANO = 2024                                            # verano previo al evento (septiembre de 2024)


def insumos() -> dict[str, Path]:
    """Archivos de referencia que usa la evaluación. La serie meteorológica se busca por nombre."""
    meteo_csv = sorted((ENT / "meteo").glob(f"{EVENTO}_*_dominio.csv"))
    dom = comun.dominio_yaml()["id"]
    r = {"ficha_v31": REPO / "escenarios" / "v3.1" / "eventos" / f"{EVENTO}.yaml",
         "ficha_v40": REPO / "escenarios" / "v4.0" / "eventos" / f"{EVENTO}.yaml",
         "ndvi_30m_gee": ENT / "combustibles" / EVENTO / f"ndvi_30m_{EVENTO}.tif",
         "ndmi_30m_gee": ENT / "combustibles" / EVENTO / f"ndmi_30m_{EVENTO}.tif",
         "clase_v31_evento": ENT / "combustibles" / EVENTO / f"combustible_clase_{EVENTO}.tif",
         "mensual_gee": ENT / "sim_v4" / "dinamicos" / "indices" / f"NDVI_NDMI_{MES[0]}_{MES[1]:02d}.tif",
         "meteo_dominio": meteo_csv[0] if len(meteo_csv) == 1 else ENT / "meteo" / f"{EVENTO}_<una sola>_dominio.csv",
         "cobertura": ENT / "cobertura" / f"cobertura_mapbiomas_col3_{{anio}}_{dom}.tif",
         **{f"verano_v40_{m:02d}": ENT / "sim_v4" / "dinamicos" / "indices" / f"NDVI_NDMI_2024_{m:02d}.tif" for m in (1, 2, 3)}}
    return r


def ficha_evento() -> dict:
    return yaml.safe_load(insumos()["ficha_v31"].read_text(encoding="utf-8"))


def ruta_cobertura(anio: int) -> Path:
    return Path(str(insumos()["cobertura"]).replace("{anio}", str(anio)))


# ------------------------------------------------------------------ utilidades
def entorno(version: str | None = None) -> dict:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    env.pop("PYTHONPATH", None)
    if version:
        env["PYTHONPATH"] = str(REPO / "src" / version / "src")
    return env


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout


def verificar_congelado() -> dict:
    p = subprocess.run([sys.executable, str(REPO / "herramientas" / "congelado.py"), "verificar"], cwd=REPO, env=entorno(),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return {"intacto": p.returncode == 0, "salida": (p.stdout + p.stderr).strip()[-2000:]}


def sha_congelado() -> str | None:
    d = comun.leer_json(REPO / "congelado.json", {}) or {}
    return d.get("sha256_del_conjunto")


def describir(ruta: Path) -> dict:
    ruta = Path(ruta)
    d = {"archivo": ruta.relative_to(REPO).as_posix() if ruta.is_relative_to(REPO) else str(ruta), "existe": ruta.exists()}
    if ruta.exists():
        d |= {"bytes": ruta.stat().st_size, "sha256": comun.sha256(ruta)}
    return d


def leer_indice(ruta: Path, banda: int = 1) -> np.ndarray:
    """Índice como float (NaN sin dato). Acepta float con −9999 (productos de v3.1) o int16 × 10000 con −32768."""
    import rasterio
    with rasterio.open(ruta) as s:
        a = s.read(banda).astype("float64")
        nd = s.nodata
        entero = np.issubdtype(np.dtype(s.dtypes[banda - 1]), np.integer)
    malo = ~np.isfinite(a)
    if nd is not None:
        malo |= a == nd
    a[malo] = np.nan
    return a / comun.ESCALA_INDICES if entero else a


def leer_banda(ruta: Path) -> tuple[np.ndarray, object]:
    import rasterio
    with rasterio.open(ruta) as s:
        return s.read(1), s.nodata


def comparar_indices(aws: np.ndarray, ref: np.ndarray) -> dict:
    """Métricas del prerregistro sobre las celdas con dato en los dos productos."""
    if aws.shape != ref.shape:
        raise ValueError(f"formas distintas: AWS {aws.shape}, referencia {ref.shape}")
    ambos = np.isfinite(aws) & np.isfinite(ref)
    out = {"celdas_total": int(aws.size), "celdas_comparadas": int(ambos.sum()),
           "fraccion_sin_dato_aws": round(float(np.mean(~np.isfinite(aws))), 6),
           "fraccion_sin_dato_gee": round(float(np.mean(~np.isfinite(ref))), 6)}
    if not ambos.any():
        return out | {"mediana_abs": None, "p95_abs": None, "mediana_con_signo": None}
    d = aws[ambos] - ref[ambos]
    return out | {"mediana_abs": round(float(np.median(np.abs(d))), 6), "p95_abs": round(float(np.percentile(np.abs(d), 95)), 6),
                  "mediana_con_signo": round(float(np.median(d)), 6)}


def fraccion_cambio_clase(a: np.ndarray, b: np.ndarray, nodata=None) -> dict:
    """Fracción de celdas con clase distinta entre dos mapas, sobre las celdas con dato en los dos (denominador del
    criterio). Se informa también sobre las celdas combustibles en alguno de los dos (clase distinta de 0 en v3.1; en
    SB40, códigos de combustible, mayores que 100 y fuera de 91–99)."""
    if a.shape != b.shape:
        raise ValueError(f"formas distintas: {a.shape} y {b.shape}")
    valido = np.ones(a.shape, bool)
    if nodata is not None:
        valido &= (a != nodata) & (b != nodata)
    distinta = valido & (a != b)
    n = int(valido.sum())
    return {"celdas_con_dato": n, "celdas_distintas": int(distinta.sum()),
            "fraccion": round(float(distinta.sum()) / n, 6) if n else None}


def es_combustible(clase: np.ndarray, motor: str) -> np.ndarray:
    if motor.startswith("v3.1"):
        return clase != 0
    return (clase > 100) & (clase != -9999)


def huella(salida: Path, motor: str, horas: float) -> np.ndarray:
    _, nombre, a_min = MOTORES[motor]
    t, nd = leer_banda(salida / nombre)
    t = t.astype("float64")
    ok = np.isfinite(t)
    if nd is not None and np.isfinite(nd):
        ok &= t != nd
    ok &= t >= 0
    return ok & (t * a_min <= horas * 60.0 + 1e-6)


def iou(a: np.ndarray, b: np.ndarray) -> float | None:
    u = int((a | b).sum())
    return round(int((a & b).sum()) / u, 6) if u else None


# ------------------------------------------------------------------ (a) y (b)
def progreso_consola(prefijo: str):
    estado = {"t": 0.0}

    def f(hechos: int, total: int, texto: str) -> None:
        if time.time() - estado["t"] > 10 or hechos == total:
            estado["t"] = time.time()
            print(f"   {prefijo}: {hechos}/{total} {texto}", flush=True)
    return f


def a_30m_v31(ndvi20: Path, ndmi20: Path, salida: Path) -> dict[str, Path]:
    """Lleva el compuesto de 20 m a 30 m con `indices_a_grilla` de v3.1, en un subproceso con el camino de v3.1."""
    salida.mkdir(parents=True, exist_ok=True)
    p = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--interno-a-30m", str(ndvi20), str(ndmi20), str(salida)],
                       cwd=REPO, env=entorno("v3.1"), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError(f"la conversión a 30 m con v3.1 falló:\n{p.stdout[-1500:]}\n{p.stderr[-1500:]}")
    return {"ndvi": salida / "ndvi_30m_aws.tif", "ndmi": salida / "ndmi_30m_aws.tif"}


def _interno_a_30m(ndvi20: str, ndmi20: str, salida: str) -> int:
    """Corre en el subproceso con el camino de v3.1: como `generar_mapa_combustibles` (float32, −9999 sin dato)."""
    sys.path.insert(0, str(REPO / "src" / "v3.1" / "src"))
    from incendios_sl import config as cfgmod
    from incendios_sl.data import preparar_dominio as pdm
    from incendios_sl.fuels.clasificacion import indices_a_grilla
    from incendios_sl.grilla import guardar_raster
    g = pdm.grilla_dominio(cfgmod.cargar_dominio(comun.dominio_yaml()["id"]))
    gd = comun.grilla_dominio()
    if (g.nfil, g.ncol) != gd.forma or abs(g.xmin - gd.xmin) > 1e-6 or abs(g.ymax - gd.ymax) > 1e-6:
        raise RuntimeError(f"la grilla de v3.1 no coincide con la del dominio: {g.como_dict()} vs {gd.como_dict()}")
    for nombre, ruta in (("ndvi", ndvi20), ("ndmi", ndmi20)):
        x, val = indices_a_grilla(Path(ruta), g)
        guardar_raster(Path(salida) / f"{nombre}_30m_aws.tif", np.where(val, x, -9999).astype(np.float32), g, nodata=-9999.0)
    return 0


def parte_a(carpeta: Path) -> dict:
    print(f"(a) compuesto de ventana por AWS {VENTANA[0]} a {VENTANA[1]}", flush=True)
    r = sentinel2.compuesto_ventana(VENTANA[0], VENTANA[1], carpeta / "20m", "E-E3-2-a", desplazamiento=DESPLAZAMIENTO,
                                    progreso=progreso_consola("(a)"))
    meta = comun.leer_json(Path(r["metadatos"]), {}) or {}
    print("(a) a 30 m con indices_a_grilla de v3.1", flush=True)
    r30 = a_30m_v31(Path(r["ndvi"]), Path(r["ndmi"]), carpeta / "30m")
    ins = insumos()
    metricas = {"NDVI": comparar_indices(leer_indice(r30["ndvi"]), leer_indice(ins["ndvi_30m_gee"])),
                "NDMI": comparar_indices(leer_indice(r30["ndmi"]), leer_indice(ins["ndmi_30m_gee"]))}
    return {"ventana_inclusive": [f"{VENTANA[0]}", f"{VENTANA[1]}"], "desplazamiento": DESPLAZAMIENTO,
            "n_escenas": r["n_escenas"], "fechas": r["fechas"], "segundos": r["segundos"],
            "escenas_de_cache": meta.get("escenas_de_cache"), "escenas": [e.get("id") for e in meta.get("escenas") or []],
            "metodo": (meta.get("parametros") or {}).get("metodo"),
            "productos": {"ndvi_20m": describir(Path(r["ndvi"])), "ndmi_20m": describir(Path(r["ndmi"])),
                          "ndvi_30m": describir(r30["ndvi"]), "ndmi_30m": describir(r30["ndmi"])},
            "metricas": metricas, "_rutas_30m": {k: str(v) for k, v in r30.items()}}


def parte_b(carpeta: Path) -> dict:
    print(f"(b) compuesto mensual por AWS {MES[0]}-{MES[1]:02d}", flush=True)
    nombre = f"NDVI_NDMI_{MES[0]}_{MES[1]:02d}_aws.tif"
    r = sentinel2.compuesto_mensual(MES[0], MES[1], carpeta, desplazamiento=DESPLAZAMIENTO, progreso=progreso_consola("(b)"),
                                    nombre=nombre)
    ruta = Path(r["ruta"])
    ref = insumos()["mensual_gee"]
    metricas = {"NDVI": comparar_indices(leer_indice(ruta, 1), leer_indice(ref, 1)),
                "NDMI": comparar_indices(leer_indice(ruta, 2), leer_indice(ref, 2))}
    proc = comun.leer_json(Path(str(ruta) + ".json"), {}) or {}
    return {"mes": f"{MES[0]}-{MES[1]:02d}", "desplazamiento": DESPLAZAMIENTO, "n_escenas": r["n_escenas"], "fechas": r["fechas"],
            "segundos": r["segundos"], "escenas": [e.get("id") for e in proc.get("escenas") or []],
            "metodo": (proc.get("parametros") or {}).get("metodo"), "producto": describir(ruta), "metricas": metricas}


# ------------------------------------------------------------------ (c)
def a_int16_tif(ruta_float: Path, destino: Path, descripcion: str) -> Path:
    """Índice float (NaN o −9999 sin dato) → int16 × 10000 en la grilla del dominio, el formato de la carga manual."""
    x = leer_indice(ruta_float)
    return comun.escribir_tif(destino, [comun.a_int16(x)], comun.grilla_dominio(), "int16", comun.NODATA_INDICES, [descripcion])


def proceso_datos(carpeta: Path, tarea: str, parametros: dict) -> dict:
    """Un trabajo de `app/datos/proceso_datos.py` (camino de v3.1), igual que lo lanza el servidor."""
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "pedido.json").write_text(json.dumps({"tarea": tarea, "parametros": parametros}, ensure_ascii=False), encoding="utf-8")
    p = subprocess.run([sys.executable, str(REPO / "app" / "datos" / "proceso_datos.py"), "--trabajo", str(carpeta)], cwd=REPO,
                       env=entorno(), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3600)
    final, error = None, None
    for linea in p.stdout.splitlines():
        try:
            a = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if a.get("aviso") == "final":
            final = a["resultado"]
        elif a.get("aviso") == "error":
            error = a.get("mensaje")
    if p.returncode != 0 or final is None:
        raise RuntimeError(f"proceso_datos ({tarea}) falló: {error or p.stderr[-1500:]}; ver {carpeta / 'proceso.log'}")
    return final


def correr(carpeta: Path, motor: str, evento: str, puntos: list[dict], t_inicio: str, horas: int,
           verano: Path | None = None) -> dict:
    """Una corrida con `app/motores/proceso.py`; devuelve el aviso final. Con `verano` (solo v4.0), la corrida pasa por
    `herramientas/e_e3_2_motor.py`, que hace que v4.0 tome los compuestos de verano de esa carpeta."""
    if carpeta.exists():
        shutil.rmtree(carpeta)
    carpeta.mkdir(parents=True)
    corrida = {"formato": "incendios_sl.corrida/1.0", "motor": motor,
               "base": {"definicion": {"evento": evento, "hipotesis": 0, "ignicion": "snmf", "horas": horas,
                                       "validar": False, "figuras": False}},
               "configuracion": {"ignicion": [{"nombre": p.get("nombre"), "lon": p["lon"], "lat": p["lat"]} for p in puntos],
                                 "t_inicio_utc": t_inicio, "horas": horas}}
    (carpeta / "corrida.json").write_text(json.dumps(corrida, ensure_ascii=False, indent=1), encoding="utf-8")
    if verano is not None and motor != "v4.0":
        raise ValueError("otro verano solo tiene sentido en v4.0")
    orden = ([sys.executable, str(MOTOR_VERANO), "--verano", str(verano), "--corrida", str(carpeta)] if verano is not None
             else [sys.executable, str(REPO / "app" / "motores" / "proceso.py"), "--corrida", str(carpeta)])
    p = subprocess.Popen(orden, cwd=REPO,
                         env=entorno(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding="utf-8", bufsize=1)
    guardian = threading.Timer(4 * 3600, p.kill)
    guardian.daemon = True
    guardian.start()
    final, error, ultima = None, None, -1
    for linea in p.stdout:
        try:
            a = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if a.get("aviso") == "hora" and int(a.get("h", 0)) >= ultima + 6:
            ultima = int(a["h"])
            print(f"   {motor} · {evento}: hora {ultima}, {a.get('ha', 0):.0f} ha", flush=True)
        elif a.get("aviso") == "final":
            final = a
        elif a.get("aviso") == "error" and a.get("fatal"):
            error = a.get("mensaje")
    p.wait()
    guardian.cancel()
    if p.returncode != 0 or final is None:
        raise RuntimeError(f"la corrida {motor} de {evento} falló ({error or p.returncode}); ver {carpeta / 'proceso.log'}")
    hecha = comun.leer_json(carpeta / "corrida.json", {}) or {}
    return final | {"ignicion": (hecha.get("resultados") or {}).get("ignicion")}


def crear_tomas_y_eventos(carpeta: Path, a30: dict[str, str], creados: dict) -> dict:
    """La toma de meteorología común, las dos tomas de índices y los dos eventos RT. Anota en `creados` lo que hay que
    borrar al final (solo lo que no existía antes)."""
    ins = insumos()
    previas_ind = {p.name for p in indices.dir_tomas().iterdir()}
    previas_met = {p.name for p in meteo.dir_tomas().iterdir()}
    m = meteo.toma_manual(ins["meteo_dominio"].read_bytes(), ins["meteo_dominio"].name)
    if m["id"] not in previas_met:
        creados["tomas_meteo"].append(m["id"])
    ventana = [f"{VENTANA[0]}", f"{VENTANA[1]}"]
    tomas = {}
    for via, ndvi, ndmi in (("gee", ins["ndvi_30m_gee"], ins["ndmi_30m_gee"]), ("aws", Path(a30["ndvi"]), Path(a30["ndmi"]))):
        d = carpeta / "tomas" / via
        rn = a_int16_tif(ndvi, d / f"ndvi_{via}.tif", "NDVI x10000")
        rm = a_int16_tif(ndmi, d / f"ndmi_{via}.tif", "NDMI x10000 (B08)")
        t = indices.toma_manual(rn, rm, ventana, "B08", rn.name, rm.name,
                                f"E-E3-2 (c): índices de ventana de {EVENTO} por {via.upper()}, a 30 m")
        if t["id"] not in previas_ind:
            creados["tomas_indices"].append(t["id"])
        tomas[via] = t
    if tomas["gee"]["id"] == tomas["aws"]["id"]:
        raise RuntimeError("las tomas de GEE y de AWS resultaron idénticas (mismo sha256): no hay nada que comparar en (c)")
    eventos = {}
    for via in ("gee", "aws"):
        print(f"(c) evento generado con los índices de {via.upper()}", flush=True)
        r = proceso_datos(carpeta / "trabajos" / f"evento_{via}", "evento",
                          {"meteo": m["id"], "indices": tomas[via]["id"], "nombre": f"E-E3-2 {EVENTO} índices {via.upper()}"})
        creados["eventos"].append(r["id"])
        eventos[via] = r
    return {"meteo": m, "tomas": tomas, "eventos": eventos}


def parte_c(carpeta: Path, a30: dict[str, str], creados: dict, horas: int = HORAS, motores: tuple[str, ...] = tuple(MOTORES)) -> dict:
    ficha = ficha_evento()
    puntos = ficha["ignicion"]["puntos"]
    t_inicio = ficha["inicio"]["hora_utc_hipotesis"][HIPOTESIS]
    cob_evento = int(ficha["cobertura_anio"])
    armado = crear_tomas_y_eventos(carpeta, a30, creados)
    ev = armado["eventos"]
    # cobertura: evento_rt elige el año anterior a la fecha local de inicio por defecto del evento
    cob = {via: int(ev[via]["cobertura_anio"]) for via in ev}
    fichas_rt = {via: yaml.safe_load((REPO / ev[via]["archivos"]["ficha"]).read_text(encoding="utf-8")) for via in ev}
    cobertura = {"evento_real": cob_evento, "rt": cob, "ficha_rt": {v: f.get("cobertura_anio") for v, f in fichas_rt.items()},
                 "t_inicio_por_defecto_rt": {v: ev[v]["t_inicio_por_defecto_utc"] for v in ev}}
    cobertura["coincide"] = all(c == cob_evento for c in list(cob.values()) + list(cobertura["ficha_rt"].values()))
    if not cobertura["coincide"]:
        raise RuntimeError(f"los eventos generados usan cobertura {cob} y el evento real {cob_evento}: (c) no sería comparable")
    if ev["gee"]["sha256"]["meteo"] != ev["aws"]["sha256"]["meteo"]:
        raise RuntimeError("los dos eventos generados no tienen la misma meteorología")

    verano = verano_aws(carpeta / "verano_aws")

    # clases de v3.1 (las arma evento_rt al crear el evento)
    clases = {}
    cl = {v: leer_banda(REPO / ev[v]["archivos"]["clase"])[0] for v in ev}
    clases["v3.1-librev2"] = fraccion_cambio_clase(cl["gee"], cl["aws"]) | {
        "fraccion_sobre_combustibles": _sobre_combustibles(cl["gee"], cl["aws"], "v3.1-librev2"),
        "control_rt_gee_vs_evento": fraccion_cambio_clase(cl["gee"], leer_banda(insumos()["clase_v31_evento"])[0])}

    corridas, huellas = {}, {}
    for motor in motores:
        for via in ("gee", "aws"):
            print(f"(c) corrida {motor} · índices {via.upper()} · {horas} h", flush=True)
            dc = carpeta / "corridas" / f"{motor.replace('.', '_')}_{via}"
            fin = correr(dc, motor, ev[via]["id"], puntos, t_inicio, horas,
                         verano=verano["carpeta"] if (motor == "v4.0" and via == "aws") else None)
            corridas[f"{motor}|{via}"] = {"evento": ev[via]["id"], "final": fin}
            huellas[(motor, via)] = {h: huella(dc / "salida", motor, h) for h in CORTES_H}
        if motor == "v4.0":
            sb = {}
            for via in ("gee", "aws"):
                ruta = REPO / "datos" / "procesados" / "v4.0" / ev[via]["id"] / "combustible_pre_evento_33b.tif"
                sb[via], nd = leer_banda(ruta)
                proc = comun.leer_json(Path(str(ruta) + ".json"), {}) or {}
                cobertura.setdefault("v40_sb40", {})[via] = (proc.get("parametros") or {}).get("cobertura_anio")
                cobertura.setdefault("v40_sb40_regla", {})[via] = (proc.get("parametros") or {}).get("regla_indices")
                usados = [e.get("archivo", "") for e in proc.get("entradas") or [] if "NDVI_NDMI_" in e.get("archivo", "")]
                cobertura.setdefault("v40_sb40_verano", {})[via] = usados
            # cada lado tiene que haber usado su verano: AWS los de verano_aws, GEE los del repositorio
            u = cobertura["v40_sb40_verano"]
            bien_aws = len(u["aws"]) == 3 and all("verano_aws" in x for x in u["aws"])
            bien_gee = len(u["gee"]) == 3 and all("sim_v4/dinamicos/indices" in x for x in u["gee"])
            if not (bien_aws and bien_gee):
                raise RuntimeError(f"v4.0 no usó el verano que correspondía a cada lado: {u}")
            ctrl = REPO / "datos" / "procesados" / "v4.0" / EVENTO / "combustible_pre_evento_33b.tif"
            clases["v4.0"] = fraccion_cambio_clase(sb["gee"], sb["aws"], nd) | {
                "fraccion_sobre_combustibles": _sobre_combustibles(sb["gee"], sb["aws"], "v4.0", nd),
                "control_rt_gee_vs_evento": fraccion_cambio_clase(sb["gee"], leer_banda(ctrl)[0], nd) if ctrl.exists() else None}
    if "v40_sb40" in cobertura:
        cobertura["coincide"] = cobertura["coincide"] and all(c == cob_evento for c in cobertura["v40_sb40"].values())

    area_ha = comun.grilla_dominio().res ** 2 / 1e4
    por_motor = {}
    for motor in motores:
        filas = {}
        for h in CORTES_H:
            g, a = huellas[(motor, "gee")][h], huellas[(motor, "aws")][h]
            ha_g, ha_a = float(g.sum()) * area_ha, float(a.sum()) * area_ha
            filas[f"{h}h"] = {"iou": iou(g, a), "ha_gee": round(ha_g, 2), "ha_aws": round(ha_a, 2),
                              "dif_ha": round(ha_a - ha_g, 2), "dif_pct": round(100 * (ha_a - ha_g) / ha_g, 3) if ha_g else None}
        por_motor[motor] = {"huellas": filas, "clases": clases.get(motor)}
    return {"evento_real": EVENTO, "hipotesis": HIPOTESIS, "t_inicio_utc": t_inicio, "horas": horas,
            "puntos_ignicion": puntos, "cobertura": cobertura,
            "meteo": {"toma": armado["meteo"]["id"], "archivo_original": describir(insumos()["meteo_dominio"]),
                      "sha256_serie": armado["meteo"]["sha256"]},
            "tomas_indices": {v: {"id": t["id"], "sha256": t["sha256"], "celdas_sin_dato_pct": t.get("celdas_sin_dato_pct")}
                              for v, t in armado["tomas"].items()},
            "eventos": {v: {"id": e["id"], "sha256": e["sha256"], "avisos": e.get("avisos"), "verano_v40": e.get("verano_v40")}
                        for v, e in ev.items()},
            "verano_aws": {k: v for k, v in verano.items() if k != "carpeta"},
            "corridas": corridas, "por_motor": por_motor}


def verano_aws(carpeta: Path) -> dict:
    """Enero a marzo de `ANIO_VERANO` por AWS con el método de SIM (el de `NDVI_NDMI_AAAA_MM.tif`), para el lado AWS de
    v4.0. Informa además la diferencia con los compuestos de GEE del repositorio (informativo: no entra en el criterio, que
    mide (a) y (b))."""
    meses, comparacion = {}, {}
    for m in (1, 2, 3):
        print(f"(c) verano por AWS {ANIO_VERANO}-{m:02d} (para v4.0)", flush=True)
        r = sentinel2.compuesto_mensual(ANIO_VERANO, m, carpeta, desplazamiento=DESPLAZAMIENTO,
                                        progreso=progreso_consola(f"(c) verano {m:02d}"))
        ruta = Path(r["ruta"])
        ref = ENT / "sim_v4" / "dinamicos" / "indices" / ruta.name
        meses[ruta.name] = {"n_escenas": r["n_escenas"], "fechas": r["fechas"], "segundos": r["segundos"],
                            "producto": describir(ruta), "gee": describir(ref)}
        comparacion[ruta.name] = {"NDVI": comparar_indices(leer_indice(ruta, 1), leer_indice(ref, 1)),
                                  "NDMI": comparar_indices(leer_indice(ruta, 2), leer_indice(ref, 2))}
    return {"carpeta": carpeta, "anio": ANIO_VERANO, "meses": meses, "comparacion_con_gee_informativa": comparacion}


def _sobre_combustibles(a: np.ndarray, b: np.ndarray, motor: str, nodata=None) -> float | None:
    comb = es_combustible(a, motor) | es_combustible(b, motor)
    if nodata is not None:
        comb &= (a != nodata) & (b != nodata)
    n = int(comb.sum())
    return round(float((comb & (a != b)).sum()) / n, 6) if n else None


def limpiar(creados: dict) -> list[str]:
    hechos = []
    for id_ in creados["eventos"]:
        try:
            evento_rt.borrar(id_)
            hechos.append(f"evento {id_}")
        except Exception as e:                       # se informa y se sigue limpiando
            hechos.append(f"evento {id_}: no se pudo borrar ({e})")
    for id_ in creados["tomas_indices"]:
        shutil.rmtree(indices.dir_tomas() / id_, ignore_errors=True)
        hechos.append(f"toma de índices {id_}")
    for id_ in creados["tomas_meteo"]:
        shutil.rmtree(meteo.dir_tomas() / id_, ignore_errors=True)
        hechos.append(f"toma de meteorología {id_}")
    return hechos


# ------------------------------------------------------------------ criterio
def veredicto(a: dict | None, b: dict | None, c: dict | None) -> dict:
    def cumple_dif(parte):
        if not parte:
            return None
        return all(parte["metricas"][i]["mediana_abs"] is not None and parte["metricas"][i]["mediana_abs"] <= UMBRAL_DIF
                   for i in ("NDVI", "NDMI"))
    ca, cb = cumple_dif(a), cumple_dif(b)
    c1 = None if ca is None or cb is None else (ca and cb)
    c2 = c3 = None
    if c:
        c2 = all(m["clases"] is not None and m["clases"]["fraccion"] is not None and m["clases"]["fraccion"] < UMBRAL_CLASE
                 for m in c["por_motor"].values())
        c3 = all(m["huellas"][f"{HORAS}h"]["iou"] is not None and m["huellas"][f"{HORAS}h"]["iou"] >= UMBRAL_IOU
                 for m in c["por_motor"].values())
    criterios = {"1_diferencia_mediana": {"cumple": c1, "a": ca, "b": cb, "umbral": f"<= {UMBRAL_DIF}"},
                 "2_cambio_de_clase": {"cumple": c2, "umbral": f"< {UMBRAL_CLASE:.0%} en cada motor"},
                 "3_iou_48h": {"cumple": c3, "umbral": f">= {UMBRAL_IOU} en cada motor"}}
    vals = [c1, c2, c3]
    glob = "incompleto" if any(v is None for v in vals) else ("se cumple" if all(vals) else "no se cumple")
    return {"criterios": criterios, "global": glob}


# ------------------------------------------------------------------ informe
def _n(x, d=4):
    if x is None:
        return "—"
    return f"{x:.{d}f}".replace(".", ",")


def _si(v):
    return {True: "**se cumple**", False: "**no se cumple**", None: "no evaluado"}[v]


def markdown(inf: dict) -> str:
    v = inf["veredicto"]
    L = ["# Resultado del prerregistro E-E3-2 — Índices por AWS frente a Google Earth Engine", "",
         f"Evaluación formal generada por `herramientas/e_e3_2.py`. Prerregistro: `E-E3-2_indices_aws.md` (etiqueta "
         f"`prerregistro-E-E3-2`); escala elegida antes de medir: `E-E3-2_escala.md` (desplazamiento {inf['desplazamiento']}).",
         "", "## Veredicto", "", f"**Global: {v['global']}.**", "",
         "| Criterio | Umbral | Resultado |", "|---|---|---|",
         f"| 1. Diferencia absoluta mediana de NDVI y NDMI, en (a) y en (b) | ≤ {_n(UMBRAL_DIF, 2)} | {_si(v['criterios']['1_diferencia_mediana']['cumple'])} "
         f"((a): {_si(v['criterios']['1_diferencia_mediana']['a'])}; (b): {_si(v['criterios']['1_diferencia_mediana']['b'])}) |",
         f"| 2. Celdas que cambian de clase de combustible, en cada motor | < 3 % | {_si(v['criterios']['2_cambio_de_clase']['cumple'])} |",
         f"| 3. IoU entre huellas a las 48 h, en cada motor | ≥ {_n(UMBRAL_IOU, 2)} | {_si(v['criterios']['3_iou_48h']['cumple'])} |",
         "", "## Quién y con qué", "", "| | |", "|---|---|",
         f"| Fecha | {inf['fecha']} |", f"| Evaluó | {inf['evaluador']} |",
         f"| Código | cambio de git `{(inf['git']['cambio'] or '—')[:12]}` (rama `{inf['git']['rama'] or '—'}`); "
         f"código sin registrar: {len(inf['git']['codigo_sin_registrar'])} archivo(s) |",
         f"| Motores congelados | sha256 del conjunto `{inf['congelado']['sha256_del_conjunto']}`; intactos antes: "
         f"{'sí' if inf['congelado']['antes']['intacto'] else 'NO'}; después: "
         f"{'sí' if (inf['congelado'].get('despues') or {}).get('intacto') else 'NO o sin verificar'} |",
         f"| Equipo | {inf['equipo']['sistema']}, {inf['equipo']['nucleos']} núcleos, Python {inf['equipo']['python']} |",
         f"| Alcance | {inf['alcance']} |", f"| Archivo completo | `E-E3-2_resultados.json` |", ""]
    L += ["## Insumos (sha256)", "", "| Insumo | Archivo | sha256 |", "|---|---|---|"]
    for k, d in inf["insumos"].items():
        L.append(f"| {k} | `{d['archivo']}` | `{d.get('sha256', 'FALTA')[:16]}…` |")
    L.append("")
    for clave, titulo in (("a", "(a) Compuesto de ventana, Las Lagunas 2024, a 30 m"), ("b", "(b) Compuesto mensual, septiembre de 2024")):
        p = inf["partes"].get(clave)
        if not p:
            continue
        L += [f"## {titulo}", "", f"{p['n_escenas']} escenas en el catálogo (≤ {sentinel2.MAX_NUBES_TESELA:.0f} % de nubes por "
              f"tesela), {len(p['fechas'])} fechas con datos. Celdas con dato en los dos productos.", "",
              "| Índice | Celdas comparadas | Dif. abs. mediana | Percentil 95 | Dif. mediana (AWS − GEE) | Sin dato AWS | Sin dato GEE |",
              "|---|---|---|---|---|---|---|"]
        for i in ("NDVI", "NDMI"):
            m = p["metricas"][i]
            n = f"{m['celdas_comparadas']:,}".replace(",", ".")
            L.append(f"| {i} | {n} | {_n(m['mediana_abs'])} | {_n(m['p95_abs'], 3)} | {_n(m['mediana_con_signo'])} | "
                     f"{_n(100 * m['fraccion_sin_dato_aws'], 2)} % | {_n(100 * m['fraccion_sin_dato_gee'], 2)} % |")
        L.append("")
    c = inf["partes"].get("c")
    if c:
        L += ["## (c) Efecto en el modelo", "",
              f"Dos eventos generados con `app/datos/evento_rt.py` ({c['eventos']['gee']['id']} con índices de GEE, "
              f"{c['eventos']['aws']['id']} con índices de AWS), la misma serie meteorológica del evento, ignición en los puntos "
              f"de la ficha a las {c['t_inicio_utc']} (hipótesis {c['hipotesis']}), {c['horas']} h. "
              f"Cobertura: evento real {c['cobertura']['evento_real']}, eventos generados {c['cobertura']['rt']}"
              + (f", SB40 de v4.0 {c['cobertura'].get('v40_sb40')}" if c['cobertura'].get('v40_sb40') else "")
              + f" ({'coincide' if c['cobertura']['coincide'] else 'NO coincide'}).", "",
              "| Motor | Cambio de clase | Sobre celdas combustibles | IoU 24 h | IoU 48 h | Sup. 48 h GEE | Sup. 48 h AWS | Dif. 48 h |",
              "|---|---|---|---|---|---|---|---|"]
        for motor, m in c["por_motor"].items():
            k = m["clases"] or {}
            h24, h48 = m["huellas"]["24h"], m["huellas"][f"{HORAS}h"]
            L.append(f"| {motor} | {_n(100 * k['fraccion'], 3) + ' %' if k.get('fraccion') is not None else '—'} | "
                     f"{_n(100 * k['fraccion_sobre_combustibles'], 3) + ' %' if k.get('fraccion_sobre_combustibles') is not None else '—'} | "
                     f"{_n(h24['iou'])} | {_n(h48['iou'])} | {_n(h48['ha_gee'], 0)} ha | {_n(h48['ha_aws'], 0)} ha | "
                     f"{_n(h48['dif_ha'], 0)} ha ({_n(h48['dif_pct'], 2)} %) |")
        L += ["", "Control (no es criterio): fracción de celdas con clase distinta entre el evento generado con GEE y el mapa del "
              "evento real; mide cuánto agrega el camino de los eventos generados (paso por int16 × 10000).", ""]
        for motor, m in c["por_motor"].items():
            ctrl = (m["clases"] or {}).get("control_rt_gee_vs_evento")
            L.append(f"- {motor}: " + (f"{_n(100 * ctrl['fraccion'], 4)} %" if ctrl and ctrl.get("fraccion") is not None else "sin dato"))
        L.append("")
    L += ["## Lo que hay que saber para leerlo", ""] + [f"- {n}" for n in inf["notas"]] + [""]
    if inf.get("errores"):
        L += ["## Errores", ""] + [f"- {e}" for e in inf["errores"]] + [""]
    L += ["## Cómo repetirlo", "", "```", f"python herramientas/e_e3_2.py --evaluador NOMBRE{' --sin-corridas' if 'c' not in inf['partes'] else ''}",
          "```", ""]
    return "\n".join(L)


NOTAS = [
    "Denominador del cambio de clase (criterio 2): todas las celdas del dominio con dato en los dos mapas; se informa "
    "también sobre las celdas combustibles en alguno de los dos. Lo fijó quien escribe, antes de ver resultados.",
    "En (c) los dos eventos generados reciben los índices a 30 m en int16 × 10000 (la carga manual de índices); los de GEE "
    "salen de `ndvi_30m`/`ndmi_30m` del evento y los de AWS de (a). Recorren el mismo camino; la única diferencia es el índice.",
    "En v4.0 los índices de la ventana entran como `indices_mes_evento`, y el combustible SB40 (regla 3.3b) y el NDVI de "
    "verano salen de los compuestos de enero a marzo. Opción A (D-E3-27, decidida antes de evaluar): el lado AWS de v4.0 usa "
    "enero a marzo de 2024 hechos por AWS (`verano_aws`) y el lado GEE los del repositorio; la procedencia del SB40 lo "
    "comprueba. La comparación de esos compuestos con los de GEE es informativa: no entra en el criterio.",
    "La cobertura MapBiomas la elige `evento_rt` (año anterior a la fecha de inicio por defecto del evento generado); se "
    "comprueba que coincida con la del evento real (`cobertura_anio` de la ficha) y si no coincide (c) no se corre.",
    "Un solo evento y una sola época (fin de invierno de un año seco); la comparación (c) usa un evento visto (límites "
    "declarados en el prerregistro).",
]


def informe_base(evaluador: str, alcance: str) -> dict:
    ins = insumos()
    anio = int(ficha_evento()["cobertura_anio"])
    lista = {k: v for k, v in ins.items() if k != "cobertura"} | {f"cobertura_{anio}": ruta_cobertura(anio)}
    return {"prerregistro": "E-E3-2", "fecha": time.strftime("%Y-%m-%d %H:%M"), "evaluador": evaluador, "alcance": alcance,
            "equipo": {"sistema": platform.platform(), "procesador": platform.processor(), "nucleos": os.cpu_count(),
                       "python": sys.version.split()[0]},
            "git": {"cambio": git("rev-parse", "HEAD").strip() or None, "rama": git("branch", "--show-current").strip() or None,
                    "codigo_sin_registrar": [l for l in git("status", "--porcelain", "--", "app", "herramientas", "src",
                                                                "escenarios", "congelado.json").splitlines() if l.strip()]},
            "congelado": {"sha256_del_conjunto": sha_congelado()},
            "desplazamiento": DESPLAZAMIENTO,
            "criterio": {"umbral_dif_mediana": UMBRAL_DIF, "umbral_cambio_clase": UMBRAL_CLASE, "umbral_iou_48h": UMBRAL_IOU},
            "insumos": {k: describir(p) for k, p in lista.items()}, "partes": {}, "notas": list(NOTAS), "errores": []}


def cobertura_que_elegiria_evento_rt() -> tuple[int, dt.date]:
    """El año de cobertura que pondrá `evento_rt.crear` con la serie del evento cargada como CSV (sin hora de toma: inicio
    por defecto cinco días después del comienzo de la serie)."""
    import pandas as pd
    t = pd.to_datetime(pd.read_csv(insumos()["meteo_dominio"], usecols=["time_utc"])["time_utc"], utc=True)
    t0 = evento_rt._hora_inicio({"desde_utc": f"{t.min():%Y-%m-%dT%H:%M:%SZ}", "hasta_utc": f"{t.max():%Y-%m-%dT%H:%M:%SZ}"})
    fecha = t0.tz_convert(evento_rt.HUSO_LOCAL).date()
    return evento_rt.anio_cobertura(fecha)[0], fecha


# ------------------------------------------------------------------ revisión previa
def revisar() -> bool:
    ok = True

    def linea(bien: bool, texto: str) -> None:
        nonlocal ok
        ok &= bien
        print(f"  [{'ok' if bien else 'FALTA'}] {texto}", flush=True)

    print("Archivos:")
    ins = insumos()
    cands = sorted((ENT / "meteo").glob(f"{EVENTO}_*_dominio.csv"))
    linea(len(cands) == 1, f"serie meteorológica del evento: {len(cands)} archivo(s) {EVENTO}_*_dominio.csv (hace falta uno)")
    for k, p in ins.items():
        if k in ("meteo_dominio", "cobertura"):
            continue
        linea(p.exists(), f"{k}: {p.relative_to(REPO).as_posix()}")
    try:
        f = ficha_evento()
        f40 = yaml.safe_load(ins["ficha_v40"].read_text(encoding="utf-8"))
        linea(f["ignicion"]["puntos"] == f40["ignicion"]["puntos"], "las fichas v3.1 y v4.0 tienen los mismos puntos de ignición")
        linea(len(f["inicio"]["hora_utc_hipotesis"]) > HIPOTESIS,
              f"hipótesis {HIPOTESIS} de la ficha: {f['inicio']['hora_utc_hipotesis'][HIPOTESIS]}")
        linea(ruta_cobertura(int(f["cobertura_anio"])).exists(), f"cobertura {f['cobertura_anio']} (la del evento real)")
        anio, fecha = cobertura_que_elegiria_evento_rt()
        linea(anio == int(f["cobertura_anio"]),
              f"evento_rt elegiría cobertura {anio} (inicio por defecto {fecha}; evento real: {f['cobertura_anio']})")
    except Exception as e:
        linea(False, f"ficha del evento: {e}")
    linea((REPO / "app" / "datos" / "proceso_datos.py").exists() and (REPO / "app" / "motores" / "proceso.py").exists(),
          "app/datos/proceso_datos.py y app/motores/proceso.py")

    linea(MOTOR_VERANO.exists(), "herramientas/e_e3_2_motor.py (verano de AWS para v4.0, opción A)")
    q = subprocess.run([sys.executable, "-c", "import sys; sys.argv=['x']; sys.path.insert(0, 'herramientas'); "
                        "import e_e3_2_motor as m, pathlib; m.preparar(pathlib.Path('VERANO')); "
                        "from incendios_sl import eventos; assert eventos.dirs_compuestos()[0] == pathlib.Path('VERANO')"],
                       cwd=REPO, env=entorno(), capture_output=True, text=True, encoding="utf-8", errors="replace")
    linea(q.returncode == 0, "v4.0 toma primero la carpeta de verano que se le da" + ("" if q.returncode == 0 else f" — {q.stderr.strip()[-300:]}"))

    print("Motores (importación en subprocesos separados):")
    for version, mod in (("v3.1", "incendios_sl.fuels.clasificacion"), ("v4.0", "simulador.corrida")):
        p = subprocess.run([sys.executable, "-c", f"import {mod}"], cwd=REPO, env=entorno(version), capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        linea(p.returncode == 0, f"{version}: import {mod}" + ("" if p.returncode == 0 else f" — {p.stderr.strip()[-300:]}"))
    c = verificar_congelado()
    linea(c["intacto"], "congelado intacto (herramientas/congelado.py verificar)" + ("" if c["intacto"] else f"\n{c['salida']}"))

    print("Red:")
    try:
        import requests
        r = requests.get(f"{sentinel2.CATALOGO}/collections/{sentinel2.COLECCION}", timeout=30)
        linea(r.status_code == 200, f"catálogo Earth Search ({sentinel2.CATALOGO}): HTTP {r.status_code}")
    except Exception as e:
        linea(False, f"catálogo Earth Search: {type(e).__name__}: {e}")

    print("Estado previo (informativo):")
    rt = [p.stem for p in (REPO / "escenarios" / "v4.0" / "eventos").glob("RT-*.yaml")]
    print(f"  eventos RT existentes: {', '.join(rt) or 'ninguno'} (no se tocan)")
    print(f"  salidas: {SALIDA_JSON.relative_to(REPO)} y {SALIDA_MD.relative_to(REPO)}"
          + (" (existen: se reemplazan)" if SALIDA_JSON.exists() else ""))
    print("\nRevisión: " + ("todo listo" if ok else "hay faltantes"), flush=True)
    return ok


# ------------------------------------------------------------------ principal
def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluación del prerregistro E-E3-2 (índices por AWS frente a GEE)")
    ap.add_argument("--evaluador", help="quién evalúa (obligatorio salvo con --solo-revisar)")
    ap.add_argument("--solo-revisar", action="store_true", help="comprueba archivos, red y motores sin calcular nada")
    ap.add_argument("--sin-corridas", action="store_true", help="solo (a) y (b), sin eventos ni corridas")
    ap.add_argument("--conservar-eventos", action="store_true", help="no borrar los eventos RT y las tomas al terminar")
    ap.add_argument("--interno-a-30m", nargs=3, metavar=("NDVI20", "NDMI20", "SALIDA"), help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.interno_a_30m:
        return _interno_a_30m(*a.interno_a_30m)
    if a.solo_revisar:
        return 0 if revisar() else 1
    if not a.evaluador:
        ap.error("--evaluador NOMBRE es obligatorio")

    alcance = "(a) y (b), sin corridas" if a.sin_corridas else "(a), (b) y (c)"
    inf = informe_base(a.evaluador, alcance)
    faltan = [k for k, d in inf["insumos"].items() if not d["existe"]]
    if faltan:
        print("faltan insumos: " + ", ".join(faltan) + " (ver --solo-revisar)", flush=True)
        return 2
    inf["congelado"]["antes"] = verificar_congelado()
    if not inf["congelado"]["antes"]["intacto"]:
        print("el congelado no está intacto antes de empezar:\n" + inf["congelado"]["antes"]["salida"], flush=True)
        return 2
    if TRABAJO.exists():
        shutil.rmtree(TRABAJO)
    TRABAJO.mkdir(parents=True)
    creados = {"eventos": [], "tomas_indices": [], "tomas_meteo": []}
    codigo = 0
    try:
        inf["partes"]["a"] = parte_a(TRABAJO / "a")
        inf["partes"]["b"] = parte_b(TRABAJO / "b")
        if not a.sin_corridas:
            inf["partes"]["c"] = parte_c(TRABAJO / "c", inf["partes"]["a"]["_rutas_30m"], creados)
    except BaseException as e:                    # también Ctrl+C: se limpia y se deja constancia
        traceback.print_exc()
        inf["errores"].append(f"{type(e).__name__}: {e}")
        codigo = 2
    finally:
        if creados["eventos"] or creados["tomas_indices"] or creados["tomas_meteo"]:
            if a.conservar_eventos:
                inf["limpieza"] = ["conservados por --conservar-eventos: " + json.dumps(creados)]
            else:
                inf["limpieza"] = limpiar(creados)
        inf["congelado"]["despues"] = verificar_congelado()
        if "incendios_sl" in sys.modules:         # no debería pasar: este proceso no carga motores
            inf["errores"].append("el proceso principal cargó incendios_sl")
    if "a" in inf["partes"]:
        inf["partes"]["a"].pop("_rutas_30m", None)
    inf["veredicto"] = veredicto(inf["partes"].get("a"), inf["partes"].get("b"), inf["partes"].get("c"))
    if not inf["congelado"]["despues"]["intacto"]:
        inf["errores"].append("el congelado cambió durante la evaluación")
        codigo = 2
    DOCS.mkdir(parents=True, exist_ok=True)
    comun.escribir_json(SALIDA_JSON, inf)
    SALIDA_MD.write_text(markdown(inf), encoding="utf-8")
    print(f"\nVeredicto global: {inf['veredicto']['global']}")
    for k, c in inf["veredicto"]["criterios"].items():
        print(f"  {k}: {c['cumple']}")
    print(f"Resultados: {SALIDA_JSON.relative_to(REPO)} y {SALIDA_MD.relative_to(REPO)}", flush=True)
    if codigo:
        return codigo
    return 0 if inf["veredicto"]["global"] == "se cumple" else 1


if __name__ == "__main__":
    sys.exit(main())
