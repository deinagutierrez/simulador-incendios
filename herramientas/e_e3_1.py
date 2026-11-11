"""Corre la comparación del prerregistro E-E3-1: el proceso motor contra la corrida offline del mismo motor.

    python herramientas/e_e3_1.py                 todos los escenarios que tengan datos en este clon
    python herramientas/e_e3_1.py aguada_36h      solo uno

Por cada par escenario–motor hace tres corridas: la offline (`scripts/correr_escenario.py` del motor), el proceso sin
órdenes y el proceso con una pausa y una reanudación a mitad de camino. Cuenta las celdas cuyo tiempo de llegada difiere.
Criterio del prerregistro: 0 celdas distintas. Deja la tabla en resultados/app/E-E3-1/resultados.json y la imprime.
De paso anota segundos de cómputo y memoria pico (prerregistro E-E3-3).
"""
from __future__ import annotations

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


def main() -> int:
    pedidos = sys.argv[1:] or list(ESCENARIOS)
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
            print(f"{nombre} · {motor}: proceso…", flush=True)
            a, fin, _ = proceso(base / "proceso", motor, e["definicion"])
            print(f"{nombre} · {motor}: proceso con pausa…", flush=True)
            b, fin_p, pausas = proceso(base / "proceso_pausa", motor, e["definicion"], pausar_en_h=e["horas"] // 2)
            if motor.startswith("v3.1"):
                n_ref = int((ref >= 0).sum())
            else:
                n_ref = int((~np.isnan(ref)).sum())
            filas.append({"escenario": nombre, "motor": motor, "estado": "corrido", "horas": e["horas"], "celdas_quemadas": n_ref,
                          "ha": fin["ha"], "celdas_distintas": distintas(a, ref), "celdas_distintas_con_pausa": distintas(b, ref),
                          "pausa_en_min": pausas, "s_offline_total": round(s_off, 1), "s_computo_proceso": fin["s_computo"],
                          "s_por_hora_simulada": round(fin["s_computo"] / max(fin["t_sim_min"] / 60.0, 1e-9), 3),
                          "memoria_pico_mb": fin["memoria_pico_mb"], "motivo_fin": fin["motivo"]})
            print("   " + json.dumps(filas[-1], ensure_ascii=False), flush=True)
    SALIDA.mkdir(parents=True, exist_ok=True)
    cab = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip() or None
    informe = {"fecha": time.strftime("%Y-%m-%d %H:%M"), "equipo": {"sistema": platform.platform(), "procesador": platform.processor(),
               "nucleos": os.cpu_count(), "python": sys.version.split()[0]}, "cambio_git": cab,
               "congelado_sha256": json.loads((REPO / "congelado.json").read_text(encoding="utf-8"))["sha256_del_conjunto"], "filas": filas}
    (SALIDA / "resultados.json").write_text(json.dumps(informe, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\nescenario        motor          h    ha         distintas  con pausa  s/h sim  MB pico")
    for f in filas:
        if f["estado"] != "corrido":
            print(f"{f['escenario']:<16} sin datos"); continue
        print(f"{f['escenario']:<16} {f['motor']:<13} {f['horas']:>3}  {f['ha']:>9.1f}  {f['celdas_distintas']:>9}  "
              f"{f['celdas_distintas_con_pausa']:>9}  {f['s_por_hora_simulada']:>7.2f}  {f['memoria_pico_mb']}")
    corridos = [f for f in filas if f["estado"] == "corrido"]
    cumple = bool(corridos) and all(f["celdas_distintas"] == 0 and f["celdas_distintas_con_pausa"] == 0 for f in corridos)
    print("\nCriterio (0 celdas distintas): " + ("SE CUMPLE en lo corrido" if cumple else "NO se cumple"))
    return 0 if cumple else 1


if __name__ == "__main__":
    sys.exit(main())
