"""Gestor de trabajos: cada simulación o preparación corre en un proceso independiente (subprocess) y su estado se
persiste en resultados/v3.1/<run_id>/estado.json, de modo que sobrevive a reinicios de la API.

Estados: pendiente, preparando_datos, calculando_viento, ejecutando_simulacion, guardando_resultados, completada,
fallida, cancelada. Solo se marca "completada" tras verificar que los archivos de salida existen y se abren.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from .. import config as cfgmod
from ..procedencia import ahora_utc

log = logging.getLogger(__name__)
_procesos: dict[str, subprocess.Popen] = {}
_lock = threading.Lock()
ESTADOS = ["pendiente", "preparando_datos", "calculando_viento", "ejecutando_simulacion", "guardando_resultados", "completada", "fallida", "cancelada"]


def dir_run(run_id: str) -> Path:
    return cfgmod.dir_resultados() / run_id


def leer_estado(run_id: str) -> dict[str, Any]:
    p = dir_run(run_id) / "estado.json"
    if p.exists():
        try:
            return json.load(open(p, encoding="utf-8"))
        except json.JSONDecodeError:
            time.sleep(0.1)
            return json.load(open(p, encoding="utf-8"))
    # corridas antiguas sin estado.json: inferir de los archivos
    d = dir_run(run_id)
    if (d / "registro.json").exists() and (d / "t_llegada_s.tif").exists():
        return {"run_id": run_id, "estado": "completada", "progreso": 1.0, "mensaje": "resultados previos", "inferido": True}
    return {"run_id": run_id, "estado": "desconocido", "progreso": 0.0}


def escribir_estado(run_id: str, **campos) -> dict[str, Any]:
    d = dir_run(run_id); d.mkdir(parents=True, exist_ok=True)
    est = leer_estado(run_id) if (d / "estado.json").exists() else {"run_id": run_id, "creado_utc": ahora_utc()}
    est.update(campos); est["actualizado_utc"] = ahora_utc()
    tmp = d / "estado.json.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(est, f, indent=2, ensure_ascii=False, default=str)
    tmp.replace(d / "estado.json")
    return est


def verificar_completada(run_id: str) -> tuple[bool, str]:
    d = dir_run(run_id)
    faltan = [n for n in ("t_llegada_s.tif", "estado_final.tif", "serie_horaria.csv", "registro.json", "metricas.json") if not (d / n).exists()]
    if faltan:
        return False, f"faltan archivos: {faltan}"
    try:
        import rasterio
        with rasterio.open(d / "t_llegada_s.tif") as ds:
            ds.read(1, window=((0, 1), (0, 1)))
        json.load(open(d / "registro.json", encoding="utf-8"))
    except Exception as e:
        return False, f"archivos ilegibles: {e}"
    return True, "ok"


def lanzar_simulacion(run_id: str, evento: str, hipotesis: int = 0, k_global: float | None = None, factor_waf: float = 1.0,
                      horas: float | None = None, ignicion: str = "snmf", k_clase: dict[int, float] | None = None, figuras: bool = False,
                      modelo: str = "modelo_v1", barreras: str = "auto", contencion: str = "auto", v2: dict[str, float] | None = None,
                      despacho: str = "auto") -> dict[str, Any]:
    d = dir_run(run_id)
    if d.exists() and (d / "estado.json").exists():
        raise FileExistsError(f"run_id {run_id} ya existe")
    escribir_estado(run_id, estado="pendiente", progreso=0.0, evento=evento, parametros={"hipotesis": hipotesis, "k_global": k_global, "factor_waf": factor_waf,
                    "horas": horas, "ignicion": ignicion, "k_clase": k_clase, "modelo": modelo, "barreras": barreras, "contencion": contencion, "v2": v2,
                    "despacho": despacho}, mensaje="en cola")
    script = cfgmod.raiz_proyecto() / "scripts" / "validar.py"
    cmd = [sys.executable, "-u", str(script), "--evento", evento, "--hipotesis", str(hipotesis), "--run-id", run_id, "--factor-waf", str(factor_waf),
           "--ignicion", ignicion, "--estado", str(d / "estado.json"), "--modelo", modelo, "--barreras", barreras, "--contencion", contencion]
    if v2:
        cmd += ["--v2", ",".join(f"{k}={v}" for k, v in v2.items())]
    from ..simulation.entradas import PARCHES_DESPACHO
    if PARCHES_DESPACHO.get(despacho):
        cmd += ["--parche", json.dumps(PARCHES_DESPACHO[despacho])]
    if k_global is not None:
        cmd += ["--k-global", str(k_global)]
    if horas:
        cmd += ["--horas", str(horas)]
    if k_clase:
        cmd += ["--k", ",".join(f"{k}={v}" for k, v in k_clase.items())]
    if not figuras:
        cmd += ["--sin-figuras"]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    logf = open(d / "registro_proceso.log", "a", encoding="utf-8")
    p = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT, env=env, cwd=str(cfgmod.raiz_proyecto()))
    with _lock:
        _procesos[run_id] = p
    threading.Thread(target=_vigilar, args=(run_id, p), daemon=True).start()
    return leer_estado(run_id)


def lanzar_preparacion(evento: str, sin_viento: bool = False) -> dict[str, Any]:
    run_id = f"preparacion_{evento}_{time.strftime('%Y%m%dT%H%M%S')}"
    d = dir_run(run_id)
    escribir_estado(run_id, estado="preparando_datos", progreso=0.0, evento=evento, mensaje="preparando datos (meteorología, índices, combustibles, viento)")
    script = cfgmod.raiz_proyecto() / "scripts" / "preparar_evento.py"
    cmd = [sys.executable, "-u", str(script), "--evento", evento] + (["--sin-viento"] if sin_viento else [])
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    logf = open(d / "registro_proceso.log", "a", encoding="utf-8")
    p = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT, env=env, cwd=str(cfgmod.raiz_proyecto()))
    with _lock:
        _procesos[run_id] = p
    threading.Thread(target=_vigilar, args=(run_id, p, True), daemon=True).start()
    return leer_estado(run_id)


def _vigilar(run_id: str, p: subprocess.Popen, preparacion: bool = False):
    code = p.wait()
    est = leer_estado(run_id)
    if est.get("estado") == "cancelada":
        return
    if preparacion:
        man = sorted((cfgmod.dir_entradas() / "eventos" / est.get("evento", "")).glob("manifiesto_*.json"))
        ok = code == 0 and bool(man)
        escribir_estado(run_id, estado="completada" if ok else "fallida", progreso=1.0, codigo_salida=code,
                        mensaje="datos preparados" if ok else f"la preparación terminó con código {code}; ver registro_proceso.log")
        return
    if code == 0:
        ok, msg = verificar_completada(run_id)
        escribir_estado(run_id, estado="completada" if ok else "fallida", progreso=1.0, codigo_salida=code, mensaje="resultados verificados" if ok else msg)
    else:
        cola = ""
        try:
            cola = (dir_run(run_id) / "registro_proceso.log").read_text(encoding="utf-8", errors="replace")[-600:]
        except OSError:
            pass
        escribir_estado(run_id, estado="fallida", codigo_salida=code, mensaje=f"el proceso terminó con código {code}", error=cola)
    with _lock:
        _procesos.pop(run_id, None)


def cancelar(run_id: str) -> dict[str, Any]:
    with _lock:
        p = _procesos.get(run_id)
    if p and p.poll() is None:
        p.kill()
        escribir_estado(run_id, estado="cancelada", mensaje="cancelada por el usuario")
    else:
        est = leer_estado(run_id)
        if est.get("estado") in ("pendiente", "ejecutando_simulacion", "preparando_datos"):
            escribir_estado(run_id, estado="cancelada", mensaje="proceso no encontrado; marcada como cancelada")
    return leer_estado(run_id)


def listar() -> list[dict[str, Any]]:
    base = cfgmod.dir_resultados()
    out = []
    for d in sorted(base.iterdir()) if base.exists() else []:
        if not d.is_dir() or d.name.startswith("benchmark") or d.name.startswith("calibracion"):
            continue
        est = leer_estado(d.name)
        reg = {}
        if (d / "registro.json").exists():
            try:
                r = json.load(open(d / "registro.json", encoding="utf-8"))
                reg = {"evento": r.get("entradas", {}).get("evento"), "t_inicio_utc": r.get("entradas", {}).get("t_inicio_utc"), "t_fin_simulado_utc": r.get("t_simulado_utc"),
                       "ha_quemadas": r.get("ha_quemadas"), "motivo_fin": r.get("motivo_fin_texto"), "segundos_cpu": r.get("segundos_cpu")}
            except Exception:
                pass
        m = {}
        if (d / "metricas.json").exists():
            try:
                mm = json.load(open(d / "metricas.json", encoding="utf-8"))
                e0 = mm.get("espacial", [{}])[0]
                m = {"iou": e0.get("iou"), "t_eval_utc": e0.get("t_eval_utc")}
            except Exception:
                pass
        out.append({"run_id": d.name, **est, **reg, **m})
    return out
