"""Corre la comparación del prerregistro E-E3-1: el proceso motor contra la corrida offline del mismo motor.

    python herramientas/e_e3_1.py                 todos los escenarios que tengan datos en este clon
    python herramientas/e_e3_1.py aguada_36h      solo uno
    python herramientas/e_e3_1.py --referencia docs/etapa3/prerregistros/E-E3-1_huellas.json
                                                  además compara los sha256 con los de otra máquina (sin tolerancia)
    python herramientas/e_e3_1.py --solo-offline  solo las corridas offline y sus sha256 (más rápido; no evalúa el criterio)

Por cada par escenario–motor hace tres corridas: la offline (`scripts/correr_escenario.py` del motor), el proceso sin
órdenes y el proceso con una pausa y una reanudación a mitad de camino. Cuenta las celdas cuyo tiempo de llegada difiere.
Criterio del prerregistro: 0 celdas distintas. Deja la tabla en resultados/app/E-E3-1/resultados.json y la imprime.
De paso anota segundos de cómputo y memoria pico (prerregistro E-E3-3).

Para comparar entre computadoras (D-E3-30, punto 6) cada fila lleva `sha256_t_llegada` de las tres corridas, y el
informe la ficha de la máquina. El hash se calcula sobre el arreglo normalizado (ver `huella`). Con `--referencia` se
comparan con una tabla de otra máquina: cualquier diferencia hace salir con código 2, y una tabla sin el par corrido (o
todavía pendiente) con código 3. No hay tolerancia: el criterio de E-E3-1 es 0 celdas. Además de resultados.json deja
huellas.json, con el formato de la tabla de referencia.

Para que el resultado se pueda rastrear, guarda también el cambio de git, si había archivos de código sin registrar, el
sha256 del congelado y, por cada evento, la lista de sus archivos de datos con sha256 y si están o no en el repositorio.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[1]
SALIDA = REPO / "resultados" / "app" / "E-E3-1"
MOTORES = {
    "v4.0": ("v4.0", {"variante": "barreras", "parar_en_cicatriz": "off"}, "hora_llegada_min.tif"),
    "v3.1-libre": ("v3.1", {"variante": "libre"}, "t_llegada_s.tif"),
    "v3.1-librev2": ("v3.1", {"variante": "libre_v2"}, "t_llegada_s.tif"),
}
SIN_FIGURAS = {"validar": False, "figuras": False}
ESCENARIOS = {
    "aguada_36h": {"motores": ["v4.0"], "horas": 36, "necesita": "datos/inputSimulacion/sim_v4/conjunto_prueba/las_lagunas_la_aguada_2023/caso.yaml",
                   "definicion": {"caso": "las_lagunas_la_aguada_2023", "variante_caso": "base", "modelo": "modelo_v3", **SIN_FIGURAS}},
    "laslagunas_48h": {"motores": ["v4.0", "v3.1-libre", "v3.1-librev2"], "horas": 48, "necesita": "datos/inputSimulacion/eventos/SL-2024-LASLAGUNAS",
                       "definicion": {"evento": "SL-2024-LASLAGUNAS", "hipotesis": 1, "ignicion": "snmf", "horas": 48, **SIN_FIGURAS}},
    "chacrasoct_72h": {"motores": ["v4.0", "v3.1-libre", "v3.1-librev2"], "horas": 72, "necesita": "datos/inputSimulacion/eventos/SL-2023-CHACRASOCT",
                       "definicion": {"evento": "SL-2023-CHACRASOCT", "hipotesis": 4, "ignicion": "alt4", "horas": 72, **SIN_FIGURAS}},
}


def entorno(version: str | None = None, resultados: Path | None = None) -> dict:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    env.pop("PYTHONPATH", None)
    if version:
        env["PYTHONPATH"] = str(REPO / "src" / version / "src")
    if resultados:
        env["INCENDIOS_SL_RESULTADOS"] = str(resultados)
    return env


def leer(tif: Path) -> np.ndarray:
    import rasterio
    with rasterio.open(tif) as s:
        return s.read(1)


# Valores fijos que reemplazan a los no finitos antes del hash: así el contenido de los NaN (que numpy no garantiza
# igual entre máquinas) no cambia el resultado. No coinciden con ningún valor que escriban los motores.
NAN_FIJO, MAS_INF_FIJO, MENOS_INF_FIJO = -9.0e30, -8.0e30, -7.0e30
FORMATO_HUELLAS = "incendios_sl.e_e3_1_huellas/1.0"


def huella(a: np.ndarray) -> str:
    """sha256 del ráster de llegada normalizado: dtype (en little endian), forma y bytes en orden C.

    En los reales, NaN, +inf y -inf se reemplazan por valores fijos y -0,0 por 0,0 (son iguales para `distintas`)."""
    a = np.asarray(a)
    a = np.ascontiguousarray(a, dtype=a.dtype.newbyteorder("<"))
    if a.dtype.kind == "f":
        a = np.where(np.isnan(a), NAN_FIJO, a)
        a = np.where(np.isposinf(a), MAS_INF_FIJO, a)
        a = np.where(np.isneginf(a), MENOS_INF_FIJO, a)
        a = np.where(a == 0, 0, a).astype(a.dtype, copy=False)
    cabecera = f"{a.dtype.str}|{'x'.join(str(n) for n in a.shape)}|".encode("ascii")
    return hashlib.sha256(cabecera + a.tobytes(order="C")).hexdigest()


def ficha_maquina() -> dict:
    """Lo que puede cambiar los últimos bits entre computadoras: sistema, procesador, AVX-512, versiones."""
    procesador, avx512_cpu = platform.processor(), None
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        texto = cpuinfo.read_text(encoding="utf-8", errors="replace")
        nombres = [l.split(":", 1)[1].strip() for l in texto.splitlines() if l.lower().startswith("model name")]
        procesador = nombres[0] if nombres else procesador
        banderas = next((l.split(":", 1)[1].split() for l in texto.splitlines() if l.startswith("flags")), [])
        avx512_cpu = "avx512f" in banderas
    elif sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                procesador = str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
    try:
        from numpy._core._multiarray_umath import __cpu_features__ as rasgos
        avx512_numpy = bool(rasgos.get("AVX512F", False))
    except ImportError:
        avx512_numpy = None
    import numba
    import psutil
    return {"sistema": platform.platform(), "procesador": procesador, "nucleos": os.cpu_count(),
            "nucleos_fisicos": psutil.cpu_count(logical=False), "ram_total_gb": round(psutil.virtual_memory().total / 2**30, 1),
            "avx512": avx512_numpy if avx512_numpy is not None else avx512_cpu, "avx512_segun_cpuinfo": avx512_cpu,
            "npy_disable_cpu_features": os.environ.get("NPY_DISABLE_CPU_FEATURES") or None,
            "python": sys.version.split()[0], "numpy": np.__version__, "numba": numba.__version__}


def comparar_con_referencia(filas: list, archivo: Path) -> dict:
    """Compara cada sha256 corrido con el de la tabla. Sin tolerancia: o es el mismo hash o se informa."""
    ref = json.loads(archivo.read_text(encoding="utf-8"))
    tabla = ref.get("huellas") or {}
    distintos, faltan = [], []
    for f in filas:
        if f["estado"] == "sin datos":
            faltan.append({"par": f["escenario"], "motivo": "sin datos en este clon"}); continue
        par = f"{f['escenario']}/{f['motor']}"
        esperado = (tabla.get(par) or {}).get("sha256_t_llegada")
        if not esperado:
            faltan.append({"par": par, "motivo": "la referencia no tiene este par"}); continue
        for corrida, h in f["sha256_t_llegada"].items():
            if h != esperado:
                distintos.append({"par": par, "corrida": corrida, "esperado": esperado, "obtenido": h})
    return {"archivo": str(archivo), "pendiente": ref.get("pendiente"), "equipo_de_referencia": ref.get("equipo"),
            "cambio_git_de_referencia": ref.get("cambio_git"), "distintos": distintos, "sin_referencia": faltan,
            "iguales": not distintos and not faltan}


def distintas(a: np.ndarray, b: np.ndarray) -> int:
    if a.shape != b.shape:
        return -1
    return int((~((a == b) | (np.isnan(a) & np.isnan(b)))).sum())


def offline(carpeta: Path, motor: str, definicion: dict) -> tuple[np.ndarray, float]:
    version, agregado, raster = MOTORES[motor]
    carpeta.mkdir(parents=True, exist_ok=True)
    esc = carpeta / "referencia.yaml"
    esc.write_text(yaml.safe_dump({**definicion, **agregado, "run_id": "referencia"}, sort_keys=False), encoding="utf-8")
    t = time.time()
    p = subprocess.run([sys.executable, "scripts/correr_escenario.py", "--archivo", str(esc)], cwd=REPO / "src" / version,
                       env=entorno(version, carpeta / "resultados"), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError(f"la corrida offline falló:\n{p.stdout[-1500:]}\n{p.stderr[-1500:]}")
    return leer(next((carpeta / "resultados").rglob(raster))), time.time() - t


def proceso(carpeta: Path, motor: str, definicion: dict, pausar_en_h: int | None = None) -> tuple[np.ndarray, dict, list]:
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "corrida.json").write_text(json.dumps({"formato": "incendios_sl.corrida/1.0", "motor": motor,
                                                      "base": {"definicion": definicion}}), encoding="utf-8")
    p = subprocess.Popen([sys.executable, str(REPO / "app" / "motores" / "proceso.py"), "--corrida", str(carpeta)], cwd=REPO,
                         env=entorno(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding="utf-8", bufsize=1)
    guardian = threading.Timer(3600, p.kill); guardian.daemon = True; guardian.start()
    pausas, final, pedida = [], None, False
    for linea in p.stdout:
        a = json.loads(linea)
        if a["aviso"] == "hora" and pausar_en_h is not None and a["h"] >= pausar_en_h and not pedida:
            pedida = True
            p.stdin.write('{"orden": "pausar"}\n'); p.stdin.flush()
        elif a["aviso"] == "pausado":
            pausas.append(a["t_sim_min"])
            p.stdin.write('{"orden": "reanudar"}\n'); p.stdin.flush()
        elif a["aviso"] == "final":
            final = a
        elif a["aviso"] == "error" and a.get("fatal"):
            raise RuntimeError(f"el proceso motor falló: {a['mensaje']}")
    p.wait(); guardian.cancel()
    if p.returncode != 0 or final is None:
        raise RuntimeError(f"el proceso motor terminó con código {p.returncode}; ver {carpeta / 'proceso.log'}")
    return leer(carpeta / "salida" / MOTORES[motor][2]), final, pausas


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout


def datos_del_evento(evento: str) -> dict:
    """Archivos de datos propios del evento, con sha256, y cuáles no están registrados en git (vienen de afuera)."""
    base = REPO / "datos" / "inputSimulacion"
    rutas = [q for q in base.rglob(f"*{evento}*") if q.is_file()]
    rutas += [q for d in base.rglob(evento) if d.is_dir() for q in d.rglob("*") if q.is_file()]
    rutas = sorted(set(rutas))
    en_git = set(git("ls-files", "datos/inputSimulacion").splitlines())
    archivos = []
    for q in rutas:
        rel = q.relative_to(REPO).as_posix()
        archivos.append({"archivo": rel, "bytes": q.stat().st_size, "sha256": hashlib.sha256(q.read_bytes()).hexdigest(),
                         "en_git": rel in en_git})
    todo = hashlib.sha256("".join(f"{a['archivo']}:{a['sha256']};" for a in archivos).encode()).hexdigest()
    return {"evento": evento, "n_archivos": len(archivos), "fuera_de_git": sum(not a["en_git"] for a in archivos),
            "sha256_del_conjunto": todo, "archivos": archivos}


def main() -> int:
    ap = argparse.ArgumentParser(description="Prerregistro E-E3-1: proceso motor contra corrida offline.")
    ap.add_argument("escenarios", nargs="*", metavar="ESCENARIO",
                    help="por defecto, todos: " + ", ".join(ESCENARIOS))
    ap.add_argument("--referencia", type=Path, metavar="ARCHIVO",
                    help="tabla de sha256 de otra máquina (formato de huellas.json); sale con código 2 si alguno difiere")
    ap.add_argument("--solo-offline", action="store_true",
                    help="solo las corridas offline y sus sha256: no evalúa el criterio de 0 celdas")
    args = ap.parse_args()
    pedidos = args.escenarios or list(ESCENARIOS)
    if desconocidos := [n for n in pedidos if n not in ESCENARIOS]:
        ap.error(f"escenarios desconocidos: {', '.join(desconocidos)} (hay: {', '.join(ESCENARIOS)})")
    if args.referencia and not args.referencia.is_file():
        ap.error(f"no existe la referencia {args.referencia}")
    if SALIDA.exists():
        shutil.rmtree(SALIDA)
    filas = []
    for nombre in pedidos:
        e = ESCENARIOS[nombre]
        if not (REPO / e["necesita"]).exists():
            print(f"{nombre}: sin datos en este clon ({e['necesita']}); hace falta el paquete histórico", flush=True)
            filas.append({"escenario": nombre, "estado": "sin datos"})
            continue
        for motor in e["motores"]:
            base = SALIDA / nombre / motor.replace(".", "_")
            print(f"{nombre} · {motor}: offline…", flush=True)
            ref, s_off = offline(base / "offline", motor, e["definicion"])
            if motor.startswith("v3.1"):
                n_ref = int((ref >= 0).sum())
            else:
                n_ref = int((~np.isnan(ref)).sum())
            if args.solo_offline:
                filas.append({"escenario": nombre, "motor": motor, "estado": "solo offline", "horas": e["horas"],
                              "celdas_quemadas": n_ref, "s_offline_total": round(s_off, 1),
                              "sha256_t_llegada": {"offline": huella(ref)}})
                print("   " + json.dumps(filas[-1], ensure_ascii=False), flush=True)
                continue
            print(f"{nombre} · {motor}: proceso…", flush=True)
            a, fin, _ = proceso(base / "proceso", motor, e["definicion"])
            print(f"{nombre} · {motor}: proceso con pausa…", flush=True)
            b, fin_p, pausas = proceso(base / "proceso_pausa", motor, e["definicion"], pausar_en_h=e["horas"] // 2)
            filas.append({"escenario": nombre, "motor": motor, "estado": "corrido", "horas": e["horas"], "celdas_quemadas": n_ref,
                          "ha": fin["ha"], "celdas_distintas": distintas(a, ref), "celdas_distintas_con_pausa": distintas(b, ref),
                          "pausa_en_min": pausas, "s_offline_total": round(s_off, 1), "s_computo_proceso": fin["s_computo"],
                          "s_por_hora_simulada": round(fin["s_computo"] / max(fin["t_sim_min"] / 60.0, 1e-9), 3),
                          "memoria_pico_mb": fin["memoria_pico_mb"], "motivo_fin": fin["motivo"],
                          "sha256_t_llegada": {"offline": huella(ref), "proceso": huella(a), "proceso_pausa": huella(b)}})
            print("   " + json.dumps(filas[-1], ensure_ascii=False), flush=True)
    SALIDA.mkdir(parents=True, exist_ok=True)
    cab = git("rev-parse", "HEAD").strip() or None
    sin_registrar = [l for l in git("status", "--porcelain", "--", "app", "herramientas", "src", "escenarios", "congelado.json").splitlines() if l.strip()]
    eventos = sorted({ESCENARIOS[n]["definicion"]["evento"] for n in pedidos if "evento" in ESCENARIOS[n]["definicion"]})
    equipo = ficha_maquina()
    congelado = json.loads((REPO / "congelado.json").read_text(encoding="utf-8"))["sha256_del_conjunto"]
    informe = {"fecha": time.strftime("%Y-%m-%d %H:%M"), "equipo": equipo, "cambio_git": cab,
               "codigo_sin_registrar": sin_registrar, "congelado_sha256": congelado, "solo_offline": args.solo_offline,
               "datos_por_evento": [datos_del_evento(ev) for ev in eventos], "filas": filas}
    if args.referencia:
        informe["comparacion_con_referencia"] = comparar_con_referencia(filas, args.referencia)
    (SALIDA / "resultados.json").write_text(json.dumps(informe, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    # Misma forma que docs/etapa3/prerregistros/E-E3-1_huellas.json: sirve de referencia si la corrida es de un commit limpio.
    huellas = {"formato": FORMATO_HUELLAS, "fecha": informe["fecha"], "cambio_git": cab, "codigo_sin_registrar": sin_registrar,
               "congelado_sha256": congelado, "equipo": equipo,
               "huellas": {f"{f['escenario']}/{f['motor']}": {"sha256_t_llegada": f["sha256_t_llegada"]["offline"],
                                                              "celdas_quemadas": f["celdas_quemadas"]}
                           for f in filas if "sha256_t_llegada" in f}}
    (SALIDA / "huellas.json").write_text(json.dumps(huellas, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\nescenario        motor          h    ha         distintas  con pausa  s/h sim  MB pico  sha256 (offline)")
    for f in filas:
        if f["estado"] == "sin datos":
            print(f"{f['escenario']:<16} sin datos"); continue
        if f["estado"] == "solo offline":
            print(f"{f['escenario']:<16} {f['motor']:<13} {f['horas']:>3}  {'':>9}  {'':>9}  {'':>9}  {'':>7}  {'':>7}  "
                  f"{f['sha256_t_llegada']['offline'][:16]}"); continue
        print(f"{f['escenario']:<16} {f['motor']:<13} {f['horas']:>3}  {f['ha']:>9.1f}  {f['celdas_distintas']:>9}  "
              f"{f['celdas_distintas_con_pausa']:>9}  {f['s_por_hora_simulada']:>7.2f}  {f['memoria_pico_mb']!s:>7}  "
              f"{f['sha256_t_llegada']['offline'][:16]}")
    print(f"\nMáquina: {equipo['procesador'] or '?'} · {equipo['nucleos']} hilos · {equipo['ram_total_gb']} GB · "
          f"AVX-512 {'sí' if equipo['avx512'] else 'no'} · Python {equipo['python']} · numpy {equipo['numpy']}")
    codigo = 0
    if args.solo_offline:
        print("\nCriterio (0 celdas distintas): no se evalúa con --solo-offline")
    else:
        corridos = [f for f in filas if f["estado"] == "corrido"]
        cumple = bool(corridos) and all(f["celdas_distintas"] == 0 and f["celdas_distintas_con_pausa"] == 0 for f in corridos)
        print("\nCriterio (0 celdas distintas): " + ("SE CUMPLE en lo corrido" if cumple else "NO se cumple"))
        codigo = 0 if cumple else 1
    if args.referencia:
        c = informe["comparacion_con_referencia"]
        print(f"\nComparación con {args.referencia} (sin tolerancia):")
        if c["pendiente"]:
            print(f"   la referencia está pendiente: {c['pendiente']}")
        for d in c["distintos"]:
            print(f"   DISTINTO {d['par']} ({d['corrida']}): esperado {d['esperado'][:16]}…, obtenido {d['obtenido'][:16]}…")
        for d in c["sin_referencia"]:
            print(f"   SIN COMPARAR {d['par']}: {d['motivo']}")
        if c["iguales"]:
            print("   todos los sha256 son iguales a los de la referencia")
        if c["distintos"]:
            codigo = codigo or 2
        elif c["sin_referencia"]:
            codigo = codigo or 3
    return codigo


if __name__ == "__main__":
    sys.exit(main())
