"""Proceso motor: conduce a un motor congelado (v3.1 o v4.0) para una corrida y habla con el servidor.

    python app/motores/proceso.py --corrida resultados/app/<id> [--motor v4.0|v3.1-libre|v3.1-librev2]

La carpeta de la corrida contiene `corrida.json`. En esta fase (F1) la corrida se define a partir de un escenario de los
motores, de una de dos formas:

    {"motor": "v4.0", "base": {"escenario": "prueba_rapida_v4"}}                       un YAML de escenarios/<versión>/corridas
    {"motor": "v3.1-librev2", "base": {"definicion": {"evento": "SL-2024-LASLAGUNAS", "hipotesis": 1, "horas": 6}}}

Con `definicion`, si no trae `variante` se usa la de la decisión D-E3-01: `barreras` en v4.0, `libre` o `libre_v2` en v3.1.

Salida estándar: solo avisos, una línea JSON cada uno (listo, hora, pausado, intervencion, final, error).
Entrada estándar: órdenes, una línea JSON cada una (pausar, reanudar, detener, intervenir).
Todo lo que imprimen los motores va a `<carpeta>/proceso.log`. Los resultados del motor quedan en `<carpeta>/salida/`,
con los mismos archivos que una corrida offline. Contrato: docs/etapa3/contrato_servidor_motor.md.

Cada proceso carga un solo motor: los dos traen un paquete llamado `incendios_sl` y no pueden convivir.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

MOTORES = {"v4.0": ("v4.0", "barreras"), "v3.1-libre": ("v3.1", "libre"), "v3.1-librev2": ("v3.1", "libre_v2")}


def main() -> int:
    ap = argparse.ArgumentParser(description="Conduce un motor congelado para una corrida del simulador interactivo")
    ap.add_argument("--corrida", required=True, help="carpeta de la corrida (contiene corrida.json)")
    ap.add_argument("--motor", choices=sorted(MOTORES), help="si se indica, tiene que coincidir con el de corrida.json")
    a = ap.parse_args()
    carpeta = Path(a.corrida).resolve()
    ruta_json = carpeta / "corrida.json"

    # Los avisos salen por la salida estándar original; desde acá, todo lo demás (también lo que escriben las bibliotecas
    # en C) va al archivo de registro, para que nada se mezcle con los avisos.
    avisos = os.fdopen(os.dup(1), "w", encoding="utf-8", newline="\n")
    try:
        ordenes = os.dup(0)                       # descriptor crudo: se consulta sin bloquear (ver control.py)
    except OSError:
        ordenes = None
    carpeta.mkdir(parents=True, exist_ok=True)
    registro = open(carpeta / "proceso.log", "a", encoding="utf-8", errors="replace", buffering=1)
    sys.stdout.flush(); sys.stderr.flush()
    os.dup2(registro.fileno(), 1)
    os.dup2(registro.fileno(), 2)
    sys.stdout = registro
    sys.stderr = registro

    # Diagnóstico opcional: con SIMULADOR_DIAGNOSTICO_S=N, cada N segundos vuelca al registro dónde está cada hilo.
    if os.environ.get("SIMULADOR_DIAGNOSTICO_S"):
        import faulthandler
        faulthandler.dump_traceback_later(float(os.environ["SIMULADOR_DIAGNOSTICO_S"]), repeat=True, file=registro)

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from control import Control, memoria_pico_mb
    control = Control(carpeta, avisos, ordenes)

    try:
        corrida = json.loads(ruta_json.read_text(encoding="utf-8"))
        motor = corrida.get("motor")
        if motor not in MOTORES:
            raise ValueError(f"corrida.json: motor {motor!r} desconocido; opciones: {', '.join(sorted(MOTORES))}")
        if a.motor and a.motor != motor:
            raise ValueError(f"--motor {a.motor} no coincide con el de corrida.json ({motor})")
        base = corrida.get("base") or {}
        if not (base.get("escenario") or base.get("definicion")):
            raise ValueError("corrida.json: falta `base.escenario` o `base.definicion`")
        version, variante = MOTORES[motor]
        print(f"proceso motor {motor} · corrida {carpeta.name}", flush=True)
        if version == "v4.0":
            import motor_v40
            res = motor_v40.correr(base, carpeta, control)
        else:
            import motor_v31
            res = motor_v31.correr(base, carpeta, control, variante)
    except Exception as e:                       # cualquier falla se informa como aviso y con código de salida 1
        traceback.print_exc()
        control.aviso("error", mensaje=f"{type(e).__name__}: {e}", fatal=True)
        registro.flush()
        return 1

    res["s_computo"] = control.segundos()
    res["memoria_pico_mb"] = memoria_pico_mb()
    res["horas_avisadas"] = control.horas_avisadas
    corrida["bitacora"] = (corrida.get("bitacora") or []) + control.bitacora
    corrida["resultados"] = {**res, "km2_final": round(res["ha_final"] / 100.0, 4),
                             "t_simulado_h": round(res["t_simulado_min"] / 60.0, 3)}
    tmp = ruta_json.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(corrida, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    os.replace(tmp, ruta_json)
    control.aviso("final", motivo=res["motivo_fin"], texto=res["motivo_fin_texto"], ha=res["ha_final"],
                  t_sim_min=res["t_simulado_min"], s_computo=res["s_computo"], memoria_pico_mb=res["memoria_pico_mb"],
                  completa=res["completa"], salida=res["salida"])
    registro.flush()
    return 0


if __name__ == "__main__":
    codigo = main()
    # Salida explícita: todo está guardado y avisado. Así el cierre no depende de hilos de los motores ni del hilo que
    # escucha órdenes, y el servidor ve terminar el proceso en el acto.
    try:
        sys.stdout.flush()
    except Exception:
        pass
    os._exit(codigo)
