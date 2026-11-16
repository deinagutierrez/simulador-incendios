"""Prueba con red, aparte y opcional (pedido F4, punto 24): la cadena completa de una corrida en tiempo real.

    python herramientas/probar_red.py            baja el pronóstico de hoy y los índices AWS, arma un evento RT y lo corre
                                                 6 h con v3.1 librev2 y con v4.0; al final borra el evento
    python herramientas/probar_red.py --dejar    no borra el evento ni las corridas

No entra en la integración continua: depende de Open-Meteo y del catálogo de AWS, que pueden estar caídos. Usa los mismos
procesos que el servidor (`app/datos/proceso_datos.py` y `app/motores/proceso.py`). Mide el tiempo de cada paso; el plan pide
el pronóstico en menos de 10 s.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "app"))


def entorno() -> dict:
    e = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    for k in [k for k in e if k == "PYTHONPATH" or k.startswith("INCENDIOS_SL_")]:
        e.pop(k)
    return e


def trabajo(tarea: str, parametros: dict | None = None) -> tuple[dict, float]:
    carpeta = REPO / "datos" / "procesados" / "app" / "trabajos" / f"probar-red-{tarea}-{secrets.token_hex(2)}"
    carpeta.mkdir(parents=True)
    (carpeta / "pedido.json").write_text(json.dumps({"tarea": tarea, "parametros": parametros or {}}), encoding="utf-8")
    t0 = time.time()
    p = subprocess.run([sys.executable, str(REPO / "app" / "datos" / "proceso_datos.py"), "--trabajo", str(carpeta)],
                       cwd=REPO, env=entorno(), capture_output=True, text=True, encoding="utf-8")
    segundos = time.time() - t0
    avisos = [json.loads(l) for l in p.stdout.splitlines() if l.strip().startswith("{")]
    ultimo = avisos[-1] if avisos else {}
    shutil.rmtree(carpeta, ignore_errors=True)
    if p.returncode != 0 or ultimo.get("aviso") != "final":
        raise SystemExit(f"{tarea}: falló — {ultimo.get('mensaje') or p.stderr[-500:]}")
    return ultimo["resultado"], segundos


def correr(motor: str, evento: str, punto: dict, t0: str, horas: int, carpeta: Path) -> dict:
    carpeta.mkdir(parents=True, exist_ok=True)
    corrida = {"motor": motor, "base": {"definicion": {"evento": evento, "validar": False, "figuras": False}},
               "configuracion": {"ignicion": [punto], "t_inicio_utc": t0, "horas": horas}}
    (carpeta / "corrida.json").write_text(json.dumps(corrida), encoding="utf-8")
    p = subprocess.run([sys.executable, str(REPO / "app" / "motores" / "proceso.py"), "--corrida", str(carpeta)], cwd=REPO,
                       env=entorno(), stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8")
    avisos = [json.loads(l) for l in p.stdout.splitlines() if l.strip().startswith("{")]
    final = next((a for a in reversed(avisos) if a.get("aviso") == "final"), None)
    if p.returncode != 0 or final is None:
        error = next((a.get("mensaje") for a in avisos if a.get("aviso") == "error"), p.stderr[-500:])
        raise SystemExit(f"{motor}: la corrida falló — {error}")
    return final


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dejar", action="store_true", help="no borrar el evento generado ni las corridas")
    ap.add_argument("--horas", type=int, default=6)
    a = ap.parse_args()
    from datos import evento_rt

    print("1. Pronóstico de Open-Meteo")
    meteo, s = trabajo("pronostico")
    print(f"   {meteo['id']}: {meteo['horas']} h, de {meteo['desde_utc']} a {meteo['hasta_utc']}, modelo {meteo.get('modelo')}"
          f" · {s:.1f} s (descarga {meteo.get('segundos')} s; criterio del plan: menos de 10 s)")
    print("2. Índices de Sentinel-2 por AWS (45 días hasta ayer)")
    ind, s = trabajo("indices_aws")
    print(f"   {ind['id']}: {ind['n_escenas']} escenas, {len(ind['fechas'])} fechas, ventana {ind['ventana']} · {s:.0f} s")
    print("3. Evento generado")
    ev, s = trabajo("evento", {"meteo": meteo["id"], "indices": ind["id"]})
    print(f"   {ev['id']}: cobertura {ev['cobertura_anio']}, verano v4.0 {ev['verano_v40']['archivos']} · {s:.1f} s")
    for x in ev.get("avisos") or []:
        print(f"   aviso: {x}")
    ficha = evento_rt.rutas(ev["id"])["ficha_v40"]
    import yaml
    punto = yaml.safe_load(ficha.read_text(encoding="utf-8"))["ignicion"]["puntos"][0]
    punto = {"lon": punto["lon"], "lat": punto["lat"]}
    carpetas = []
    try:
        for i, motor in enumerate(("v3.1-librev2", "v4.0"), 4):
            print(f"{i}. Corrida de {a.horas} h con {motor} desde el centro del dominio")
            c = REPO / "resultados" / "app" / f"probar-red-{ev['id']}-{motor}"
            carpetas.append(c)
            f = correr(motor, ev["id"], punto, ev["t_inicio_por_defecto_utc"], a.horas, c)
            print(f"   {f['ha']} ha · {f['texto']} · {f['s_computo']} s de cómputo")
    finally:
        if not a.dejar:
            evento_rt.borrar(ev["id"])
            for c in carpetas:
                shutil.rmtree(c, ignore_errors=True)
            print(f"Se borró {ev['id']} y sus corridas (las tomas de datos quedan en la caché).")
    print("La cadena en tiempo real funciona.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
