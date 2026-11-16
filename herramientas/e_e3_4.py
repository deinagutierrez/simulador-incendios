"""Evaluación del prerregistro E-E3-4: las intervenciones son reproducibles.

    python herramientas/e_e3_4.py --evaluador NOMBRE          las 5 corridas en los 3 motores, comparaciones A y B
    python herramientas/e_e3_4.py --solo-revisar              comprueba archivos, trazos, etiquetas y motores sin correr nada
    python herramientas/e_e3_4.py --humo CARPETA [--humo-motor M] [--humo-horas H]
                                                              prueba de humo de quien escribe: una corrida chica con un trazo
                                                              y viento manual; escribe solo en CARPETA (no es la evaluación)

Lo corre la otra persona (prerregistro `docs/etapa3/prerregistros/E-E3-4_intervenciones.md`, D-E3-28 punto 29), sin pasos
manuales. Los trazos y las horas salen de `E-E3-4_trazos.json` (etiqueta `prerregistro-E-E3-4-trazos`): cinco corridas de
48 h sobre Las Lagunas 2024, hipótesis 1 (2024-09-18T15:00Z), puntos de ignición de la ficha, en v4.0, v3.1 librev2 y
v3.1 libre. Para cada corrida y motor:

(0) Corrida en vivo con `app/motores/proceso.py`: los cortafuegos de `configuracion` entran antes de iniciar; las
    intervenciones, en su hora, con la corrida pausada de verdad: `pausar` con `en_t_sim_min`, `intervenir` por la entrada
    estándar y `reanudar` (el mismo camino que usa el servidor).
(A) Reproducción desde la bitácora: una corrida nueva con la configuración de la original y `reproduccion` =
    `{de, raiz, bitacora}`; la aplica el propio proceso motor, sin órdenes. Criterio: 0 celdas distintas en el tiempo de
    llegada y la cadena de hash igual (`resultados.reproduccion.cadena_igual`, sin entradas sin aplicar).
(B) Offline con `correr_escenario.py` del motor, con los mismos trazos desde el inicio (los recortados que guardó la corrida
    en vivo) y la serie meteorológica editada:
    - v4.0: el `escenario_base.yaml` de la corrida con `mitigacion.barreras_extra` = `cortafuegos_aplicados.geojson`,
      `mitigacion.modificador_combustible` = `modificador_aplicado.tif` (si hubo suelo mineral) y `parche.meteo` =
      `meteo_editada.csv` (si hubo viento manual), con rutas absolutas dentro del repositorio; variante `barreras` y
      `parar_en_cicatriz: off` (ya están en ese YAML).
    - v3.1: `INCENDIOS_SL_INPUT` apunta a un espejo de `datos/inputSimulacion` (`barreras_v31.armar_espejo`: enlaces duros
      con respaldo a copia, nunca simbólicos) con el NPZ de barreras con solo los enlaces aplicados, la serie meteorológica
      con el viento manual y la clase de combustible editada si hubo suelo mineral; `INCENDIOS_SL_RESULTADOS` dentro de
      `resultados/app/E-E3-4`; el YAML de la corrida (variante libre o libre_v2) con `barreras: on`; `--archivo --solo-simular`.
    Criterio: IoU de la huella final >= 0,99 y la misma longitud de cortafuego (la aplicada, D-E3-28 punto 14).
    En v4.0 el viento manual gira durante la hora siguiente y en v3.1 cambia de golpe: es lo esperado (prerregistro).

Salidas: `docs/etapa3/prerregistros/E-E3-4_resultados.json` y `E-E3-4_resultado.md`; lo intermedio en
`resultados/app/E-E3-4/`. Código de salida: 0 se cumple todo, 1 no se cumple (o quedó incompleto), 2 error.

Este proceso no importa ningún motor: cada corrida va en su propio `proceso.py` o `correr_escenario.py`. Importa solo
`app/motores/intervenciones.py` (hash y validación) y `app/motores/barreras_v31.py` (el espejo), que no cargan motores.
No escribe en ningún insumo del repositorio: se comprueba con el sha256 de los insumos antes y después.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "app"))
sys.path.insert(0, str(REPO / "app" / "motores"))

from datos import comun  # noqa: E402  (no importa motores)
import barreras_v31  # noqa: E402  (solo el espejo; no importa motores al cargarse)
import intervenciones as iv  # noqa: E402

DOCS = REPO / "docs" / "etapa3" / "prerregistros"
PRERREGISTRO = DOCS / "E-E3-4_intervenciones.md"
TRAZOS = DOCS / "E-E3-4_trazos.json"
SALIDA_JSON = DOCS / "E-E3-4_resultados.json"
SALIDA_MD = DOCS / "E-E3-4_resultado.md"
TRABAJO = REPO / "resultados" / "app" / "E-E3-4"
PROCESO = REPO / "app" / "motores" / "proceso.py"
ETIQUETAS = ("prerregistro-E-E3-4", "prerregistro-E-E3-4-trazos")
ENT = comun.ENTRADAS
# motor → (versión, ráster de llegada)
MOTORES = {"v4.0": ("v4.0", "hora_llegada_min.tif"), "v3.1-librev2": ("v3.1", "t_llegada_s.tif"),
           "v3.1-libre": ("v3.1", "t_llegada_s.tif")}
UMBRAL_IOU = 0.99
TOL_LONGITUD_M = 0.011          # las longitudes van redondeadas a 0,01 m
TOPE_CORRIDA_S = 4 * 3600

# Prueba de humo (solo para quien escribe): un trazo chico antes de iniciar y, en pausa, un trazo chico delante del foco este,
# viento manual a la 1 h y vuelta al pronóstico a las 2 h. Puntos en EPSG:5345.
HUMO = {"n": 0, "descripcion": "prueba de humo: un trazo antes de iniciar, un trazo y viento manual en pausa",
        "configuracion": {"cortafuegos": [{"ancho_m": 6, "suelo_mineral": False,
                                           "xy_5345": [[3535000, 6388000], [3536100, 6387950]]}]},
        "intervenciones": [
            {"t_sim_h": 1, "tipo": "cortafuego",
             "datos": {"ancho_m": 10, "suelo_mineral": False, "xy_5345": [[3541800, 6387700], [3542500, 6387650]]}},
            {"t_sim_h": 1, "tipo": "viento_manual", "datos": {"vel_kmh": 20.0, "dir_desde": 87.0}},
            {"t_sim_h": 2, "tipo": "viento_manual", "datos": {"modo": "pronostico"}}]}


# ------------------------------------------------------------------ insumos y utilidades
def leer_trazos() -> dict:
    return json.loads(TRAZOS.read_text(encoding="utf-8"))


def ficha_v31(evento: str) -> dict:
    return yaml.safe_load((REPO / "escenarios" / "v3.1" / "eventos" / f"{evento}.yaml").read_text(encoding="utf-8"))


def insumos(evento: str) -> dict[str, Path]:
    """Archivos de referencia (se informan con sha256 antes y después: la evaluación no tiene que cambiar ninguno)."""
    metas = sorted((ENT / "meteo").glob(f"{evento}_*_dominio.csv"))
    try:
        dom = ficha_v31(evento)["dominio"]
    except Exception:
        dom = "<dominio>"
    return {"prerregistro": PRERREGISTRO, "trazos": TRAZOS,
            "ficha_v31": REPO / "escenarios" / "v3.1" / "eventos" / f"{evento}.yaml",
            "ficha_v40": REPO / "escenarios" / "v4.0" / "eventos" / f"{evento}.yaml",
            "meteo_dominio": metas[-1] if metas else ENT / "meteo" / f"{evento}_<falta>_dominio.csv",
            "clase_v31": ENT / "combustibles" / evento / f"combustible_clase_{evento}.tif",
            "barreras_enlaces_v31": ENT / "barreras" / f"barreras_enlaces_{dom}.npz"}


def entorno(version: str | None = None, **extra: str) -> dict:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    for k in ("PYTHONPATH", "INCENDIOS_SL_INPUT", "INCENDIOS_SL_RESULTADOS"):
        env.pop(k, None)
    if version:
        env["PYTHONPATH"] = str(REPO / "src" / version / "src")
    env.update({k: str(v) for k, v in extra.items()})
    return env


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout


def git_bytes(*args: str) -> bytes | None:
    p = subprocess.run(["git", *args], cwd=REPO, capture_output=True)
    return p.stdout if p.returncode == 0 else None


def verificar_congelado() -> dict:
    p = subprocess.run([sys.executable, str(REPO / "herramientas" / "congelado.py"), "verificar"], cwd=REPO, env=entorno(),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return {"intacto": p.returncode == 0, "salida": (p.stdout + p.stderr).strip()[-2000:]}


def sha_congelado() -> str | None:
    return (comun.leer_json(REPO / "congelado.json", {}) or {}).get("sha256_del_conjunto")


def describir(ruta: Path) -> dict:
    ruta = Path(ruta)
    d = {"archivo": ruta.relative_to(REPO).as_posix() if ruta.is_relative_to(REPO) else str(ruta), "existe": ruta.exists()}
    if ruta.exists():
        d |= {"bytes": ruta.stat().st_size, "sha256": comun.sha256(ruta)}
    return d


def trazos_en_etiqueta() -> dict:
    """El archivo de trazos tiene que ser el de la etiqueta `prerregistro-E-E3-4-trazos` (D-E3-28, punto 3)."""
    rel = TRAZOS.relative_to(REPO).as_posix()
    en_tag = git_bytes("show", f"{ETIQUETAS[1]}:{rel}")
    if en_tag is None:
        return {"etiqueta": ETIQUETAS[1], "existe": False, "igual": None}
    import hashlib
    actual = TRAZOS.read_bytes() if TRAZOS.exists() else b""
    return {"etiqueta": ETIQUETAS[1], "existe": True, "igual": hashlib.sha256(en_tag).hexdigest() == hashlib.sha256(actual).hexdigest(),
            "sha256_etiqueta": hashlib.sha256(en_tag).hexdigest()}


def leer_raster(ruta: Path) -> tuple[np.ndarray, object, tuple]:
    import rasterio
    with rasterio.open(ruta) as s:
        return s.read(1).astype("float64"), s.transform, (s.nodata, s.crs.to_string() if s.crs else None)


def distintas(a: np.ndarray, b: np.ndarray) -> int:
    if a.shape != b.shape:
        raise ValueError(f"formas distintas: {a.shape} y {b.shape}")
    return int((~((a == b) | (np.isnan(a) & np.isnan(b)))).sum())


def huella_final(t: np.ndarray, nodata) -> np.ndarray:
    ok = np.isfinite(t) & (t >= 0)
    if nodata is not None and np.isfinite(nodata):
        ok &= t != nodata
    return ok


def iou(a: np.ndarray, b: np.ndarray) -> float | None:
    u = int((a | b).sum())
    return round(int((a & b).sum()) / u, 6) if u else None


def dentro_de(ruta: Path, raiz: Path) -> bool:
    try:
        Path(ruta).resolve().relative_to(Path(raiz).resolve())
        return True
    except ValueError:
        return False


# ------------------------------------------------------------------ corrida en vivo y reproducción
def corrida_json(motor: str, definicion: dict, configuracion: dict) -> dict:
    c = {"formato": "incendios_sl.corrida/1.0", "motor": motor, "base": {"definicion": dict(definicion)},
         "programa": {"version": "herramientas/e_e3_4.py", "congelado_sha256": sha_congelado()}}
    if configuracion:
        c["configuracion"] = json.loads(json.dumps(configuracion))
    return c


def guion_de(plan: dict) -> dict[float, list[dict]]:
    """{t_sim_min: [entradas {tipo, datos}]}, en el orden del archivo de trazos."""
    g: dict[float, list[dict]] = {}
    for e in plan.get("intervenciones") or []:
        g.setdefault(float(e["t_sim_h"]) * 60.0, []).append({"tipo": e["tipo"], "datos": e["datos"]})
    return dict(sorted(g.items()))


def correr_proceso(carpeta: Path, corrida: dict, guion: dict[float, list[dict]] | None = None, rotulo: str = "") -> dict:
    """Corre `proceso.py` con `corrida`. En cada hora de `guion`: pausa (pedida con `en_t_sim_min`), las intervenciones por la
    entrada estándar, reanudar y la pausa siguiente. Devuelve el resumen de avisos y `corrida.json` final."""
    if carpeta.exists():
        shutil.rmtree(carpeta)
    carpeta.mkdir(parents=True)
    (carpeta / "corrida.json").write_text(json.dumps(corrida, ensure_ascii=False, indent=1), encoding="utf-8")
    guion = dict(guion or {})
    horas = sorted(guion)
    t0 = time.perf_counter()
    p = subprocess.Popen([sys.executable, str(PROCESO), "--corrida", str(carpeta)], cwd=REPO, env=entorno(),
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                         bufsize=1)
    guardian = threading.Timer(TOPE_CORRIDA_S, p.kill)
    guardian.daemon = True
    guardian.start()

    def mandar(o: dict) -> None:
        try:
            p.stdin.write(json.dumps(o, ensure_ascii=False) + "\n")
            p.stdin.flush()
        except (BrokenPipeError, OSError):
            pass

    if horas:
        mandar({"orden": "pausar", "en_t_sim_min": horas[0]})
    final, error, ultima = None, None, -1
    respuestas, pausas, anomalias, no_fatales = [], [], [], []
    for linea in p.stdout:
        try:
            a = json.loads(linea)
        except json.JSONDecodeError:
            continue
        tipo = a.get("aviso")
        if tipo == "hora" and int(a.get("h", 0)) >= ultima + 6:
            ultima = int(a["h"])
            print(f"   {rotulo}: hora {ultima}, {a.get('ha', 0):.0f} ha", flush=True)
        elif tipo == "pausado" and not a.get("reproduccion"):
            t = float(a["t_sim_min"])
            pausas.append(t)
            if horas and abs(t - horas[0]) < 1e-6:
                h = horas.pop(0)
                for j, e in enumerate(guion[h]):
                    mandar({"orden": "intervenir", "ref": f"{h:g}-{j}", "entrada": e})
            else:
                anomalias.append(f"pausa inesperada en t = {t:g} min")
            mandar({"orden": "reanudar"})
            if horas:
                mandar({"orden": "pausar", "en_t_sim_min": horas[0]})
        elif tipo == "intervencion":
            respuestas.append({k: a.get(k) for k in ("ref", "n", "estado", "t_vigor_min", "pleno_min", "motivo")})
        elif tipo == "final":
            final = a
        elif tipo == "error":
            if a.get("fatal"):
                error = a.get("mensaje")
            else:
                no_fatales.append(a.get("mensaje"))
    try:
        p.stdin.close()
    except OSError:
        pass
    p.wait()
    guardian.cancel()
    s = round(time.perf_counter() - t0, 1)
    if p.returncode != 0 or final is None:
        raise RuntimeError(f"la corrida {rotulo} falló ({error or p.returncode}); ver {carpeta / 'proceso.log'}")
    if horas:
        anomalias.append("la corrida terminó sin llegar a las pausas de t = " + ", ".join(f"{h:g}" for h in horas) + " min")
    hecha = json.loads((carpeta / "corrida.json").read_text(encoding="utf-8"))
    return {"final": final, "respuestas": respuestas, "pausas_min": pausas, "anomalias": anomalias,
            "errores_no_fatales": no_fatales, "s": s, "corrida": hecha}


def reproduccion_de(original: dict, de: str) -> dict:
    """La corrida que pide `POST /api/corridas/<id>/reproducir`: formato, motor, base, configuración, insumos y programa tal
    cual, más `reproduccion`."""
    c = {k: original[k] for k in ("formato", "motor", "base", "configuracion", "insumos", "programa") if k in original}
    c["reproduccion"] = {"de": de, "raiz": original.get("bitacora_raiz"), "bitacora": original.get("bitacora") or []}
    return c


def llegada(carpeta: Path, motor: str) -> tuple[np.ndarray, object, tuple]:
    return leer_raster(carpeta / "salida" / MOTORES[motor][1])


# ------------------------------------------------------------------ comparación B: offline
def a_repo(archivos: dict[str, Path], destino_repo: Path) -> dict[str, Path]:
    """v4.0 solo lee insumos dentro del repositorio: si la corrida está fuera (prueba de humo), copia los archivos a
    `destino_repo` (dentro de resultados/app/)."""
    out = {}
    for k, ruta in archivos.items():
        if dentro_de(ruta, REPO):
            out[k] = Path(ruta).resolve()
        else:
            destino_repo.mkdir(parents=True, exist_ok=True)
            out[k] = destino_repo / Path(ruta).name
            shutil.copy2(ruta, out[k])
    return out


def offline_v40(vivo: Path, trabajo: Path, repo_tmp: Path) -> dict:
    res = json.loads((vivo / "corrida.json").read_text(encoding="utf-8")).get("resultados") or {}
    archivos = res.get("archivos_offline") or {}
    if res.get("archivos_offline_error"):
        raise RuntimeError(f"la corrida en vivo no pudo escribir los archivos offline: {res['archivos_offline_error']}")
    rutas = a_repo({k: vivo / v for k, v in archivos.items()}, repo_tmp)
    esc = yaml.safe_load((vivo / "escenario_base.yaml").read_text(encoding="utf-8"))
    esc["run_id"] = "offline_b"
    mit = {k: v for k, v in (esc.get("mitigacion") or {}).items() if k not in ("barreras_extra", "modificador_combustible")}
    for k in ("barreras_extra", "modificador_combustible"):
        if k in rutas:
            mit[k] = str(rutas[k])
    if mit:
        esc["mitigacion"] = mit
    else:
        esc.pop("mitigacion", None)
    if "meteo" in rutas:
        esc["parche"] = {**(esc.get("parche") or {}), "meteo": str(rutas["meteo"])}
    esc.setdefault("variante", "barreras")
    esc.setdefault("parar_en_cicatriz", "off")
    trabajo.mkdir(parents=True, exist_ok=True)
    archivo = trabajo / "offline_b.yaml"
    archivo.write_text(yaml.safe_dump(esc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    resultados = trabajo / "resultados"
    t0 = time.perf_counter()
    p = subprocess.run([sys.executable, "scripts/correr_escenario.py", "--archivo", str(archivo)], cwd=REPO / "src" / "v4.0",
                       env=entorno("v4.0", INCENDIOS_SL_RESULTADOS=resultados), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=TOPE_CORRIDA_S)
    (trabajo / "offline.log").write_text(p.stdout + "\n" + p.stderr, encoding="utf-8")
    if p.returncode != 0:
        raise RuntimeError(f"correr_escenario.py de v4.0 falló; ver {trabajo / 'offline.log'}")
    tifs = sorted(resultados.rglob(MOTORES["v4.0"][1]))
    if len(tifs) != 1:
        raise RuntimeError(f"se esperaba un {MOTORES['v4.0'][1]} en {resultados} y hay {len(tifs)}")
    return {"tif": tifs[0], "s": round(time.perf_counter() - t0, 1), "yaml": esc, "archivos": archivos}


def offline_v31(vivo: Path, trabajo: Path, evento: str, dominio: str) -> dict:
    trabajo.mkdir(parents=True, exist_ok=True)
    espejo = trabajo / "espejo"
    if espejo.exists():
        shutil.rmtree(espejo)
    t0 = time.perf_counter()
    info = barreras_v31.armar_espejo(vivo, espejo, evento, dominio)
    npz_espejo = espejo / "barreras" / f"barreras_enlaces_{dominio}.npz"
    info["sha256_barreras_espejo"] = comun.sha256(npz_espejo) if npz_espejo.exists() else None
    info["reemplazados"] = [Path(r).as_posix() for r in info["reemplazados"]]
    esc = yaml.safe_load((vivo / "escenario_base.yaml").read_text(encoding="utf-8"))
    esc["run_id"] = "offline_b"
    if info["barreras"]:
        esc["barreras"] = "on"
    archivo = trabajo / "offline_b.yaml"
    archivo.write_text(yaml.safe_dump(esc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    resultados = trabajo / "resultados"
    try:
        p = subprocess.run([sys.executable, "scripts/correr_escenario.py", "--archivo", str(archivo), "--solo-simular"],
                           cwd=REPO / "src" / "v3.1", env=entorno("v3.1", INCENDIOS_SL_INPUT=espejo,
                                                                  INCENDIOS_SL_RESULTADOS=resultados),
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TOPE_CORRIDA_S)
        (trabajo / "offline.log").write_text(p.stdout + "\n" + p.stderr, encoding="utf-8")
        if p.returncode != 0:
            raise RuntimeError(f"correr_escenario.py de v3.1 falló; ver {trabajo / 'offline.log'}")
    finally:
        shutil.rmtree(espejo, ignore_errors=True)          # enlaces duros y copias: no hace falta conservarlo
    tif = resultados / "offline_b" / MOTORES["v3.1-libre"][1]
    if not tif.exists():
        raise RuntimeError(f"no quedó {tif}")
    return {"tif": tif, "s": round(time.perf_counter() - t0, 1), "yaml": esc, "espejo": info}


# ------------------------------------------------------------------ longitud de cortafuego (criterio B)
def trazos_aplicados(corrida: dict) -> list[dict]:
    """Los cortafuegos de la corrida en vivo, en el orden en que se aplicaron: primero los de antes de iniciar
    (`resultados.cortafuegos_iniciales`), después los de la bitácora."""
    res = corrida.get("resultados") or {}
    out = []
    for i, c in enumerate(res.get("cortafuegos_iniciales") or []):
        out.append({"origen": "inicial", "i": i + 1, "t_sim_min": 0.0, "estado": c.get("estado"), "datos": c})
    for e in corrida.get("bitacora") or []:
        if e.get("tipo") == "cortafuego":
            out.append({"origen": "pausa", "n": e["n"], "t_sim_min": e["t_sim_min"], "estado": "aplicada", "datos": e["datos"]})
    return out


def _fila_longitud(t: dict) -> dict:
    d = t["datos"]
    return {"origen": t["origen"], "n_bitacora": t.get("n"), "t_sim_min": t["t_sim_min"], "estado": t["estado"],
            "ancho_m": d.get("ancho_m"), "longitud_dibujada_m": d.get("longitud_dibujada_m"),
            "longitud_aplicada_m": d.get("longitud_aplicada_m")}


def longitudes_v40(vivo: Path, corrida: dict) -> dict:
    """Cada geometría de `cortafuegos_aplicados.geojson` (lo que carga la corrida offline) contra lo aplicado en vivo:
    - longitud dentro de la grilla de la geometría offline (si es una línea) contra `longitud_aplicada_m`;
    - celdas que toca (all_touched, como `rasterizar_barreras_extra`) contra `celdas_sha256`.
    Si la geometría offline son los centros de las celdas (`geometria_offline: centros`), no tiene longitud: se compara
    solo que cargue las mismas celdas, y la longitud que se informa es la aplicada."""
    import geopandas as gpd
    from rasterio import features
    from shapely.geometry import box
    trazos = trazos_aplicados(corrida)
    ruta = vivo / ((corrida.get("resultados") or {}).get("archivos_offline") or {}).get("barreras_extra", "-")
    if not trazos:
        return {"trazos": [], "cumple": True, "nota": "sin cortafuegos"}
    if not ruta.exists():
        return {"trazos": [_fila_longitud(t) for t in trazos], "cumple": False,
                "nota": "falta cortafuegos_aplicados.geojson"}
    t_arr, tr, (_, crs) = llegada(vivo, "v4.0")
    forma = t_arr.shape
    caja = box(tr.c, tr.f + tr.e * forma[0], tr.c + tr.a * forma[1], tr.f)
    gdf = gpd.read_file(ruta)
    if crs and gdf.crs is not None and gdf.crs.to_string() != crs:
        gdf = gdf.to_crs(crs)
    props = gdf.drop(columns="geometry").to_dict("records")
    iniciales = [(p, g) for p, g in zip(props, gdf.geometry) if p.get("origen") != "pausa" and p.get("i") is not None]
    en_pausa = [(p, g) for p, g in zip(props, gdf.geometry) if p.get("origen") == "pausa"]
    filas, cumple, k_pausa = [], True, 0
    for t in trazos:
        fila = _fila_longitud(t)
        if t["origen"] == "inicial":
            par = next(((p, g) for p, g in iniciales if int(p.get("i")) == t["i"]), None)
        else:
            par = en_pausa[k_pausa] if k_pausa < len(en_pausa) else None
            k_pausa += 1
        if par is None:
            fila |= {"geometria_offline": None, "longitud_offline_m": None, "mismas_celdas": False, "misma_longitud": False}
            cumple = False
            filas.append(fila)
            continue
        p, g = par
        m = features.rasterize([(g.__geo_interface__, 1)], out_shape=forma, transform=tr, fill=0, all_touched=True,
                               dtype="uint8").astype(bool)
        mismas = iv.sha256_indices(np.flatnonzero(m.ravel())) == t["datos"].get("celdas_sha256")
        lineal = g.geom_type in ("LineString", "MultiLineString")
        largo = round(float(g.intersection(caja).length), 2) if lineal else None
        aplicada = t["datos"].get("longitud_aplicada_m")
        if lineal:
            misma = aplicada is not None and abs(largo - float(aplicada)) <= TOL_LONGITUD_M
        else:
            misma = mismas
        fila |= {"geometria_offline": "polilinea" if lineal else "centros", "longitud_offline_m": largo,
                 "celdas_offline": int(m.sum()), "celdas_vivo": t["datos"].get("celdas"), "mismas_celdas": bool(mismas),
                 "misma_longitud": bool(misma)}
        cumple &= bool(mismas and misma)
        filas.append(fila)
    sobran = len(iniciales) + len(en_pausa) - len(trazos)
    if sobran:
        cumple = False
    return {"trazos": filas, "cumple": cumple, "geometrias_sin_par": sobran,
            "longitud_aplicada_total_m": round(sum(float(f["longitud_aplicada_m"] or 0) for f in filas), 2)}


def longitudes_v31(vivo: Path, corrida: dict, info_espejo: dict | None) -> dict:
    """v3.1 no carga líneas: la corrida offline carga los ENLACES de la matriz `barreras_enlaces.npz` del espejo. Se
    comprueba que lo cargado sea exactamente lo aplicado: cada `cortafuego_NN.npz` con los enlaces de su entrada en la
    bitácora (`enlaces_sha256`), la matriz offline con la unión de todos y el espejo con esa misma matriz. Con lo cargado
    igual, la longitud de la línea que lo produjo es la aplicada (`longitud_aplicada_m`, D-E3-28 punto 14)."""
    trazos = [t for t in trazos_aplicados(corrida) if t["estado"] != "rechazada"]
    carpeta = vivo / barreras_v31.CARPETA
    if not trazos:
        return {"trazos": [], "cumple": True, "nota": "sin cortafuegos"}
    filas, cumple, union = [], True, []
    for k, t in enumerate(trazos, start=1):
        fila = _fila_longitud(t)
        z_ruta = carpeta / f"cortafuego_{k:02d}.npz"
        if not z_ruta.exists():
            fila |= {"enlaces_iguales": False, "misma_longitud": False}
            cumple = False
            filas.append(fila)
            continue
        z = np.load(z_ruta)
        enl = np.asarray(z["enlaces"], dtype="int64")
        union.append(enl)
        iguales = (iv.sha256_indices(enl) == t["datos"].get("enlaces_sha256") and len(enl) == t["datos"].get("enlaces")
                   and [list(map(float, p)) for p in z["xy_5345"].tolist()] == [list(map(float, p)) for p in t["datos"]["xy_5345"]])
        fila |= {"geometria_offline": "enlaces", "enlaces": int(len(enl)), "enlaces_recortados": t["datos"].get("enlaces_recortados"),
                 "enlaces_iguales": bool(iguales), "misma_longitud": bool(iguales)}
        cumple &= bool(iguales)
        filas.append(fila)
    matriz = carpeta / "barreras_enlaces.npz"
    out = {"trazos": filas}
    if matriz.exists():
        cod = np.load(matriz)["codigos"]
        u = np.unique(np.concatenate(union)) if union else np.zeros(0, "int64")
        out["matriz_es_la_union"] = bool(np.array_equal(np.flatnonzero(cod.reshape(-1)), u))
        out["espejo_es_la_matriz"] = bool(info_espejo is not None and info_espejo.get("sha256_barreras_espejo") == comun.sha256(matriz))
        cumple &= out["matriz_es_la_union"] and out["espejo_es_la_matriz"]
    else:
        out["matriz_es_la_union"] = False
        cumple = False
    extra = len(list(carpeta.glob("cortafuego_*.npz"))) - len(trazos)
    if extra:
        cumple = False
    out |= {"cumple": cumple, "npz_sin_par": extra,
            "longitud_aplicada_total_m": round(sum(float(f["longitud_aplicada_m"] or 0) for f in filas), 2)}
    return out


# ------------------------------------------------------------------ una corrida en un motor
def evaluar(plan: dict, motor: str, definicion: dict, carpeta: Path, evento: str, dominio: str, repo_tmp: Path) -> dict:
    rotulo = f"corrida {plan['n']} · {motor}"
    configuracion = dict(plan.get("configuracion") or {})
    guion = guion_de(plan)
    out: dict = {"corrida": plan["n"], "motor": motor, "descripcion": plan.get("descripcion")}

    print(f"(0) {rotulo}: en vivo", flush=True)
    vivo = carpeta / "vivo"
    r = correr_proceso(vivo, corrida_json(motor, definicion, configuracion), guion, rotulo)
    c = r["corrida"]
    res = c.get("resultados") or {}
    esperadas = sum(len(v) for v in guion.values())
    out["vivo"] = {"s": r["s"], "final": {k: r["final"].get(k) for k in ("motivo", "ha", "t_sim_min", "completa")},
                   "t_inicio_utc": (res.get("ignicion") or {}).get("t_inicio_utc"),
                   "pausas_min": r["pausas_min"], "intervenciones": r["respuestas"], "intervenciones_esperadas": esperadas,
                   "anomalias": r["anomalias"], "errores_no_fatales": r["errores_no_fatales"],
                   "bitacora": [{k: e.get(k) for k in ("n", "t_sim_min", "t_vigor_min", "tipo")} for e in c.get("bitacora") or []],
                   "bitacora_raiz": c.get("bitacora_raiz"), "cadena_integra": iv.verificar_cadena(c.get("bitacora_raiz"),
                                                                                                   c.get("bitacora"))[0],
                   "cortafuegos_iniciales": [{k: v for k, v in x.items() if k != "xy_5345"}
                                             for x in res.get("cortafuegos_iniciales") or []],
                   "archivos_offline": res.get("archivos_offline"), "intervenciones_v31": res.get("intervenciones_v31")}
    rechazadas = [x for x in r["respuestas"] if x["estado"] == "rechazada"]
    out["vivo"]["plan_cumplido"] = (not r["anomalias"] and len(r["respuestas"]) == esperadas and not rechazadas
                                    and all(x.get("estado") != "rechazada" for x in res.get("cortafuegos_iniciales") or []))
    t_vivo, _, (nd, _) = llegada(vivo, motor)

    print(f"(A) {rotulo}: reproducción desde la bitácora", flush=True)
    rep = correr_proceso(carpeta / "reproduccion", reproduccion_de(c, f"E-E3-4/{carpeta.name}/vivo"), None, rotulo + " (A)")
    info = (rep["corrida"].get("resultados") or {}).get("reproduccion") or {}
    t_rep, _, _ = llegada(carpeta / "reproduccion", motor)
    n_dist = distintas(t_vivo, t_rep)
    out["A"] = {"s": rep["s"], "celdas_distintas": n_dist, "reproduccion": info,
                "cumple": bool(n_dist == 0 and info.get("cadena_igual") is True and not info.get("sin_aplicar"))}

    print(f"(B) {rotulo}: offline", flush=True)
    version = MOTORES[motor][0]
    if version == "v4.0":
        off = offline_v40(vivo, carpeta / "offline", repo_tmp / carpeta.name)
        lon = longitudes_v40(vivo, c)
        detalle = {"archivos": off["archivos"]}
    else:
        off = offline_v31(vivo, carpeta / "offline", evento, dominio)
        lon = longitudes_v31(vivo, c, off["espejo"])
        detalle = {"espejo": off["espejo"]}
    t_off, _, (nd_off, _) = leer_raster(off["tif"])
    hv, ho = huella_final(t_vivo, nd), huella_final(t_off, nd_off)
    area_ha = None
    try:
        _, tr, _ = llegada(vivo, motor)
        area_ha = abs(tr.a * tr.e) / 1e4
    except Exception:
        pass
    v_iou = iou(hv, ho)
    out["B"] = {"s": off["s"], "iou_final": v_iou, "celdas_vivo": int(hv.sum()), "celdas_offline": int(ho.sum()),
                "ha_vivo": round(float(hv.sum()) * area_ha, 2) if area_ha else None,
                "ha_offline": round(float(ho.sum()) * area_ha, 2) if area_ha else None,
                "celdas_distintas_llegada": distintas(t_vivo, t_off) if t_vivo.shape == t_off.shape else None,
                "longitud": lon, **detalle,
                "cumple_iou": bool(v_iou is not None and v_iou >= UMBRAL_IOU), "cumple_longitud": bool(lon["cumple"])}
    out["B"]["cumple"] = out["B"]["cumple_iou"] and out["B"]["cumple_longitud"]
    print(f"    A: {n_dist} celdas distintas, cadena igual {info.get('cadena_igual')}; B: IoU {v_iou}, longitud "
          f"{'igual' if lon['cumple'] else 'DISTINTA'}", flush=True)
    return out


# ------------------------------------------------------------------ criterio
def veredicto(filas: list[dict], esperadas: int) -> dict:
    hechas = [f for f in filas if "A" in f and "B" in f]
    completo = len(hechas) == esperadas and all(f["vivo"]["plan_cumplido"] for f in hechas)
    ca = all(f["A"]["cumple"] for f in hechas) if hechas else None
    cb = all(f["B"]["cumple"] for f in hechas) if hechas else None
    if not completo:
        # lo que no se cumple sigue siendo "no se cumple" aunque falte algo; si todo lo hecho se cumple, queda incompleto
        ca = False if ca is False else None
        cb = False if cb is False else None
    crit = {"A_desde_la_bitacora": {"cumple": ca, "umbral": "0 celdas distintas en el tiempo de llegada y la misma cadena"},
            "B_offline": {"cumple": cb, "umbral": f"IoU de la huella final >= {UMBRAL_IOU} y la misma longitud de cortafuego"}}
    vals = [ca, cb]
    glob = "incompleto" if any(v is None for v in vals) else ("se cumple" if all(vals) else "no se cumple")
    return {"criterios": crit, "global": glob, "pares_hechos": len(hechas), "pares_esperados": esperadas,
            "planes_cumplidos": completo}


# ------------------------------------------------------------------ informe
def _n(x, d=4):
    if x is None:
        return "—"
    return f"{x:.{d}f}".replace(".", ",")


def _si(v):
    return {True: "**se cumple**", False: "**no se cumple**", None: "no evaluado"}[v]


def _sn(v):
    return {True: "sí", False: "NO", None: "—"}[v]


NOTAS = [
    "Ignición: la definición es la del evento con la hipótesis 1 y los puntos de la ficha (`hipotesis: 1`, `ignicion: snmf`), "
    "como en E-E3-1; se comprueba que la ficha diga la misma hora que el archivo de trazos y se informa la que usó cada "
    "corrida (`t_inicio_utc`).",
    "Intervenciones en vivo: `pausar` con `en_t_sim_min` y, en cada pausa, `intervenir` por la entrada estándar y `reanudar` "
    "(el camino del servidor). La reproducción (A) la hace el propio proceso motor con `reproduccion` = {de, raiz, bitacora}.",
    "Longitud de cortafuego (criterio B, D-E3-28 punto 14), cómo se mide (lo fijó quien escribe, antes de ver resultados): "
    "v4.0 carga geometrías; para las líneas se mide la longitud dentro de la grilla de la geometría que carga la corrida "
    "offline y se compara con la aplicada en vivo (tolerancia 0,011 m por el redondeo a 0,01 m), y además que toque las "
    "mismas celdas. Si la geometría offline son los centros de las celdas (cuando la polilínea recortada no rasteriza "
    "exacto), no tiene longitud: se compara que cargue las mismas celdas. v3.1 no carga líneas sino enlaces: se compara "
    "que la matriz offline tenga exactamente los enlaces aplicados (sha256 de cada trazo, unión y espejo); con eso, la "
    "longitud de lo cargado es la aplicada.",
    "En v4.0 el viento manual gira durante la hora siguiente a la pausa y en v3.1 cambia de golpe en la hora de la pausa; "
    "en los dos casos la corrida offline usa la serie editada del mismo modo, así que no cuenta como diferencia.",
    "B se mide sobre la huella final (celdas con tiempo de llegada); se informa también la cantidad de celdas con tiempo "
    "de llegada distinto, que no es criterio.",
    "Un solo evento (Las Lagunas 2024), como declara el prerregistro. No dice si un cortafuego real detendría el fuego.",
]


def markdown(inf: dict) -> str:
    v = inf["veredicto"]
    L = ["# Resultado del prerregistro E-E3-4 — Las intervenciones son reproducibles", ""]
    if inf.get("humo"):
        L += ["> **Prueba de humo de quien escribe: NO es la evaluación del prerregistro.**", ""]
    L += [f"Evaluación generada por `herramientas/e_e3_4.py`. Prerregistro: `E-E3-4_intervenciones.md` (etiqueta "
          f"`{ETIQUETAS[0]}`); trazos y horas: `E-E3-4_trazos.json` (etiqueta `{ETIQUETAS[1]}`: "
          f"{'el archivo es el de la etiqueta' if inf['trazos_etiqueta'].get('igual') else 'NO coincide con la etiqueta o no se encontró'}).",
          "", "## Veredicto", "", f"**Global: {v['global']}.** Pares corrida–motor hechos: {v['pares_hechos']} de "
          f"{v['pares_esperados']}; planes de intervención cumplidos en todos: {_sn(v['planes_cumplidos'])}.", "",
          "| Criterio | Umbral | Resultado |", "|---|---|---|",
          f"| A. Desde la bitácora | {v['criterios']['A_desde_la_bitacora']['umbral']} | {_si(v['criterios']['A_desde_la_bitacora']['cumple'])} |",
          f"| B. Offline | IoU ≥ {_n(UMBRAL_IOU, 2)} y la misma longitud de cortafuego (la aplicada) | {_si(v['criterios']['B_offline']['cumple'])} |",
          "", "## Quién y con qué", "", "| | |", "|---|---|",
          f"| Fecha | {inf['fecha']} |", f"| Evaluó | {inf['evaluador']} |",
          f"| Código | cambio de git `{(inf['git']['cambio'] or '—')[:12]}` (rama `{inf['git']['rama'] or '—'}`); "
          f"código sin registrar: {len(inf['git']['codigo_sin_registrar'])} archivo(s) |",
          f"| Motores congelados | sha256 del conjunto `{inf['congelado']['sha256_del_conjunto']}`; intactos antes: "
          f"{'sí' if (inf['congelado'].get('antes') or {}).get('intacto') else 'NO'}; después: "
          f"{'sí' if (inf['congelado'].get('despues') or {}).get('intacto') else 'NO o sin verificar'} |",
          f"| Insumos sin cambios | {_sn(inf.get('insumos_sin_cambios'))} |",
          f"| Equipo | {inf['equipo']['sistema']}, {inf['equipo']['nucleos']} núcleos, Python {inf['equipo']['python']} |",
          f"| Alcance | {inf['alcance']} |", "", "## Insumos (sha256)", "", "| Insumo | Archivo | sha256 |", "|---|---|---|"]
    for k, d in inf["insumos"].items():
        L.append(f"| {k} | `{d['archivo']}` | `{(d.get('sha256') or 'FALTA')[:16]}…` |")
    L += ["", "## Por corrida y motor", "",
          "| Corrida | Motor | Intervenciones (aplicadas / esperadas) | Plan cumplido | A: celdas distintas | A: cadena igual | "
          "B: IoU final | B: longitud aplicada | B: misma longitud | Sup. vivo / offline |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for f in inf["corridas"]:
        if "A" not in f or "B" not in f:
            L.append(f"| {f['corrida']} | {f['motor']} | — | — | — | — | — | — | — | error: {f.get('error', '?')} |")
            continue
        vi = f["vivo"]
        aplicadas = sum(1 for x in vi["intervenciones"] if x["estado"] != "rechazada")
        rep = f["A"]["reproduccion"]
        lon = f["B"]["longitud"]
        L.append(f"| {f['corrida']} | {f['motor']} | {aplicadas} / {vi['intervenciones_esperadas']} | {_sn(vi['plan_cumplido'])} | "
                 f"{f['A']['celdas_distintas']} | {_sn(rep.get('cadena_igual'))} | {_n(f['B']['iou_final'], 6)} | "
                 f"{_n(lon.get('longitud_aplicada_total_m'), 2) + ' m' if lon.get('longitud_aplicada_total_m') is not None else '—'} | "
                 f"{_sn(lon['cumple'])} | {_n(f['B']['ha_vivo'], 1)} / {_n(f['B']['ha_offline'], 1)} ha |")
    L += ["", "## Cortafuegos", "",
          "| Corrida | Motor | Origen | t (min) | Ancho | Dibujada | Aplicada | Offline | Geometría offline | Igual |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for f in inf["corridas"]:
        for t in ((f.get("B") or {}).get("longitud") or {}).get("trazos") or []:
            L.append(f"| {f['corrida']} | {f['motor']} | {t['origen']} | {_n(t['t_sim_min'], 0)} | {t.get('ancho_m')} m | "
                     f"{_n(t.get('longitud_dibujada_m'), 2)} m | {_n(t.get('longitud_aplicada_m'), 2)} m | "
                     f"{_n(t.get('longitud_offline_m'), 2) + ' m' if t.get('longitud_offline_m') is not None else '—'} | "
                     f"{t.get('geometria_offline') or '—'} | {_sn(t.get('misma_longitud'))} |")
    anom = [(f["corrida"], f["motor"], a) for f in inf["corridas"] for a in (f.get("vivo") or {}).get("anomalias") or []]
    rech = [(f["corrida"], f["motor"], x) for f in inf["corridas"] for x in (f.get("vivo") or {}).get("intervenciones") or []
            if x["estado"] != "aceptada"]
    if anom or rech:
        L += ["", "## Desvíos del plan e intervenciones recortadas o rechazadas", ""]
        L += [f"- corrida {c} · {m}: {a}" for c, m, a in anom]
        L += [f"- corrida {c} · {m}: `{x['ref']}` {x['estado']} — {x.get('motivo') or ''}" for c, m, x in rech]
    L += ["", "## Lo que hay que saber para leerlo", ""] + [f"- {n}" for n in inf["notas"]] + [""]
    if inf.get("errores"):
        L += ["## Errores", ""] + [f"- {e}" for e in inf["errores"]] + [""]
    L += ["## Cómo repetirlo", "", "```", "python herramientas/e_e3_4.py --evaluador NOMBRE", "```", ""]
    return "\n".join(L)


def informe_base(evaluador: str, alcance: str, evento: str, humo: bool) -> dict:
    return {"prerregistro": "E-E3-4", "humo": humo, "fecha": time.strftime("%Y-%m-%d %H:%M"), "evaluador": evaluador,
            "alcance": alcance,
            "equipo": {"sistema": platform.platform(), "procesador": platform.processor(), "nucleos": os.cpu_count(),
                       "python": sys.version.split()[0]},
            "git": {"cambio": git("rev-parse", "HEAD").strip() or None, "rama": git("branch", "--show-current").strip() or None,
                    "etiquetas": {t: (git("rev-list", "-n", "1", t).strip() or None) for t in ETIQUETAS},
                    "codigo_sin_registrar": [l for l in git("status", "--porcelain", "--", "app", "herramientas", "src",
                                                                "escenarios", "congelado.json").splitlines() if l.strip()]},
            "congelado": {"sha256_del_conjunto": sha_congelado()},
            "trazos_etiqueta": trazos_en_etiqueta(),
            "criterio": {"umbral_iou": UMBRAL_IOU, "tolerancia_longitud_m": TOL_LONGITUD_M},
            "insumos": {k: describir(p) for k, p in insumos(evento).items()}, "corridas": [], "notas": list(NOTAS),
            "errores": []}


# ------------------------------------------------------------------ revisión previa
def revisar() -> bool:
    ok = True

    def linea(bien: bool, texto: str) -> None:
        nonlocal ok
        ok &= bool(bien)
        print(f"  [{'ok' if bien else 'FALTA'}] {texto}", flush=True)

    print("Archivos y trazos:")
    try:
        tz = leer_trazos()
    except Exception as e:
        linea(False, f"{TRAZOS.relative_to(REPO).as_posix()}: {e}")
        print("\nRevisión: hay faltantes", flush=True)
        return False
    evento = tz.get("evento", "?")
    for k, p in insumos(evento).items():
        linea(p.exists(), f"{k}: {describir(p)['archivo']}")
    te = trazos_en_etiqueta()
    linea(te["existe"] and te["igual"], f"el archivo de trazos es el de la etiqueta {ETIQUETAS[1]}"
          + ("" if te["existe"] else " (no se encontró la etiqueta)"))
    for t in ETIQUETAS[:1]:
        linea(bool(git("rev-list", "-n", "1", t).strip()), f"etiqueta {t}")
    linea(set(tz.get("motores") or []) == set(MOTORES), f"motores del archivo: {tz.get('motores')}")
    linea(len(tz.get("corridas") or []) == 5, f"{len(tz.get('corridas') or [])} corridas (el diseño pide 5)")
    try:
        f = ficha_v31(evento)
        hora = f["inicio"]["hora_utc_hipotesis"][int(tz["hipotesis"])]
        linea(hora == tz["t_inicio_utc"], f"hipótesis {tz['hipotesis']} de la ficha: {hora} (archivo: {tz['t_inicio_utc']})")
        f40 = yaml.safe_load(insumos(evento)["ficha_v40"].read_text(encoding="utf-8"))
        linea(f["ignicion"]["puntos"] == f40["ignicion"]["puntos"], "las fichas v3.1 y v4.0 tienen los mismos puntos de ignición")
        iv.revisar_t_inicio(tz["t_inicio_utc"])
    except Exception as e:
        linea(False, f"ficha del evento: {type(e).__name__}: {e}")
    for plan in tz.get("corridas") or []:
        problemas = []
        try:
            for c in (plan.get("configuracion") or {}).get("cortafuegos") or []:
                nc = iv.validar_cortafuego(c)
                if c.get("longitud_dibujada_m") is not None and abs(nc["longitud_dibujada_m"] - c["longitud_dibujada_m"]) > 0.05:
                    problemas.append(f"longitud dibujada {c['longitud_dibujada_m']} y medida {nc['longitud_dibujada_m']}")
            for e in plan.get("intervenciones") or []:
                ne = iv.validar_entrada({"tipo": e["tipo"], "datos": e["datos"]})
                h = float(e["t_sim_h"])
                if h != int(h) or not 0 < h < float(tz["horas"]):
                    problemas.append(f"hora {h} no es una hora en punto dentro de la corrida")
                d = e["datos"]
                if ne["tipo"] == "cortafuego" and d.get("longitud_dibujada_m") is not None and \
                        abs(ne["datos"]["longitud_dibujada_m"] - d["longitud_dibujada_m"]) > 0.05:
                    problemas.append(f"longitud dibujada {d['longitud_dibujada_m']} y medida {ne['datos']['longitud_dibujada_m']}")
        except (ValueError, KeyError, TypeError) as err:
            problemas.append(f"{type(err).__name__}: {err}")
        linea(not problemas, f"corrida {plan.get('n')}: {plan.get('descripcion')}" + ("" if not problemas else " — " + "; ".join(problemas)))

    print("Programas:")
    linea(PROCESO.exists(), "app/motores/proceso.py")
    for version in ("v4.0", "v3.1"):
        linea((REPO / "src" / version / "scripts" / "correr_escenario.py").exists(), f"src/{version}/scripts/correr_escenario.py")
    print("Motores (importación en subprocesos separados):")
    for version, mod in (("v3.1", "incendios_sl.simulation.motor"), ("v4.0", "simulador.corrida")):
        p = subprocess.run([sys.executable, "-c", f"import {mod}"], cwd=REPO, env=entorno(version), capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        linea(p.returncode == 0, f"{version}: import {mod}" + ("" if p.returncode == 0 else f" — {p.stderr.strip()[-300:]}"))
    c = verificar_congelado()
    linea(c["intacto"], "congelado intacto (herramientas/congelado.py verificar)" + ("" if c["intacto"] else f"\n{c['salida']}"))
    linea(dentro_de(TRABAJO, REPO), f"carpeta de trabajo dentro del repositorio (v4.0 solo lee insumos ahí): "
          f"{TRABAJO.relative_to(REPO).as_posix()}")
    print("Estado previo (informativo):")
    print(f"  corridas: {len(tz.get('corridas') or [])} × {len(MOTORES)} motores, {tz.get('horas')} h cada una; por cada par, "
          "tres corridas (en vivo, reproducción y offline)")
    print(f"  salidas: {SALIDA_JSON.relative_to(REPO).as_posix()} y {SALIDA_MD.relative_to(REPO).as_posix()}"
          + (" (existen: se reemplazan)" if SALIDA_JSON.exists() else ""))
    print("\nRevisión: " + ("todo listo" if ok else "hay faltantes"), flush=True)
    return ok


# ------------------------------------------------------------------ principal
def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluación del prerregistro E-E3-4 (intervenciones reproducibles)")
    ap.add_argument("--evaluador", help="quién evalúa (obligatorio salvo con --solo-revisar o --humo)")
    ap.add_argument("--solo-revisar", action="store_true", help="comprueba archivos, trazos, etiquetas y motores sin correr nada")
    ap.add_argument("--humo", metavar="CARPETA", help="prueba de humo de quien escribe: una corrida chica, todo en CARPETA")
    ap.add_argument("--humo-motor", choices=sorted(MOTORES), default="v3.1-librev2")
    ap.add_argument("--humo-horas", type=int, default=3)
    a = ap.parse_args()
    if a.solo_revisar:
        return 0 if revisar() else 1
    if not a.evaluador and not a.humo:
        ap.error("--evaluador NOMBRE es obligatorio")

    tz = leer_trazos()
    evento = tz["evento"]
    dominio = ficha_v31(evento)["dominio"]
    if a.humo:
        base = Path(a.humo).resolve()
        if dentro_de(base, DOCS):
            ap.error("--humo no puede escribir en docs/etapa3/prerregistros")
        trabajo, salida_json, salida_md = base / "trabajo", base / "E-E3-4_resultados.json", base / "E-E3-4_resultado.md"
        horas = int(a.humo_horas)
        if horas <= max(float(e["t_sim_h"]) for e in HUMO["intervenciones"]):
            ap.error("--humo-horas tiene que pasar la última pausa de la prueba de humo (2 h)")
        planes, motores = [HUMO], [a.humo_motor]
        alcance = f"prueba de humo: {a.humo_motor}, {horas} h, un trazo antes de iniciar, un trazo y viento manual en pausa"
        evaluador = a.evaluador or "prueba de humo (quien escribe)"
    else:
        trabajo, salida_json, salida_md = TRABAJO, SALIDA_JSON, SALIDA_MD
        horas = int(tz["horas"])
        planes, motores = tz["corridas"], list(tz["motores"])
        alcance = f"{len(planes)} corridas × {len(motores)} motores, {horas} h, comparaciones A y B"
        evaluador = a.evaluador
    definicion = {"evento": evento, "hipotesis": int(tz["hipotesis"]), "ignicion": "snmf", "horas": horas,
                  "validar": False, "figuras": False}

    inf = informe_base(evaluador, alcance, evento, bool(a.humo))
    inf["definicion"] = definicion
    faltan = [k for k, d in inf["insumos"].items() if not d["existe"]]
    if faltan:
        print("faltan insumos: " + ", ".join(faltan) + " (ver --solo-revisar)", flush=True)
        return 2
    if not a.humo and not inf["trazos_etiqueta"].get("igual"):
        print(f"el archivo de trazos no es el de la etiqueta {ETIQUETAS[1]} (ver --solo-revisar)", flush=True)
        return 2
    inf["congelado"]["antes"] = verificar_congelado()
    if not inf["congelado"]["antes"]["intacto"]:
        print("el congelado no está intacto antes de empezar:\n" + inf["congelado"]["antes"]["salida"], flush=True)
        return 2
    if trabajo.exists():
        shutil.rmtree(trabajo)
    trabajo.mkdir(parents=True)
    # v4.0 offline solo lee insumos dentro del repositorio: en la prueba de humo (fuera del repositorio) se copian ahí y se borran
    repo_tmp = REPO / "resultados" / "app" / f"E-E3-4_humo_{uuid.uuid4().hex[:8]}" if a.humo else trabajo / "_no_se_usa"
    codigo = 0
    try:
        for plan in planes:
            for motor in motores:
                carpeta = trabajo / f"c{plan['n']}_{motor.replace('.', '_').replace('-', '_')}"
                try:
                    inf["corridas"].append(evaluar(plan, motor, definicion, carpeta, evento, dominio, repo_tmp))
                except Exception as e:
                    traceback.print_exc()
                    inf["corridas"].append({"corrida": plan["n"], "motor": motor, "error": f"{type(e).__name__}: {e}"})
                    inf["errores"].append(f"corrida {plan['n']} · {motor}: {type(e).__name__}: {e}")
                    codigo = 2
    except BaseException as e:                     # también Ctrl+C: se deja constancia de lo hecho
        traceback.print_exc()
        inf["errores"].append(f"{type(e).__name__}: {e}")
        codigo = 2
    finally:
        if a.humo:
            shutil.rmtree(repo_tmp, ignore_errors=True)
        inf["congelado"]["despues"] = verificar_congelado()
        despues = {k: describir(p) for k, p in insumos(evento).items()}
        inf["insumos_sin_cambios"] = all(despues[k].get("sha256") == d.get("sha256") for k, d in inf["insumos"].items())
        if "incendios_sl" in sys.modules or "simulador" in sys.modules:   # no debería pasar: este proceso no carga motores
            inf["errores"].append("el proceso principal cargó un motor")
    inf["veredicto"] = veredicto(inf["corridas"], len(planes) * len(motores))
    if not inf["congelado"]["despues"]["intacto"]:
        inf["errores"].append("el congelado cambió durante la evaluación")
        codigo = 2
    if not inf["insumos_sin_cambios"]:
        inf["errores"].append("un insumo cambió durante la evaluación")
        codigo = 2
    salida_json.parent.mkdir(parents=True, exist_ok=True)
    comun.escribir_json(salida_json, inf)
    salida_md.write_text(markdown(inf), encoding="utf-8")
    print(f"\nVeredicto global: {inf['veredicto']['global']}")
    for k, c in inf["veredicto"]["criterios"].items():
        print(f"  {k}: {c['cumple']}")
    print(f"Resultados: {salida_json} y {salida_md}", flush=True)
    if codigo:
        return codigo
    return 0 if inf["veredicto"]["global"] == "se cumple" else 1


if __name__ == "__main__":
    sys.exit(main())
