"""Proceso de datos: hace un trabajo de datos y avisa al servidor, como los procesos motor.

    python app/datos/proceso_datos.py --trabajo datos/procesados/app/trabajos/<id>

La carpeta contiene `pedido.json` = {"tarea": …, "parametros": {…}}. Tareas:

| Tarea | Parámetros | Resultado |
|---|---|---|
| `pronostico` | `modelo`, `respaldo` (opcionales) | toma de meteorología (Open-Meteo, cliente de v3.1) |
| `meteo_manual` | `archivo` (en la carpeta del trabajo), `nombre` | toma de meteorología desde un CSV |
| `escenario` | `desde_utc`, `horas`, `temp_c`, `hr_pct`, `viento_kmh`, `viento_dir_deg`, `precip_mm` | toma con valores fijos |
| `indices_aws` | `fecha_corrida` (AAAA-MM-DD; por defecto hoy) | toma de índices por AWS |
| `indices_gee` | `fecha_corrida` | toma de índices por Google Earth Engine (código de v3.1) |
| `indices_manual` | `ndvi`, `ndmi` (archivos en la carpeta), `ventana`, `ndmi_nir`, nombres | toma de índices cargados a mano |
| `evento` | `meteo`, `indices` (id de las tomas), `nombre` | evento generado `RT-…` |

Salida estándar: una línea JSON por aviso: `progreso` {hechos, total, texto}, `final` {resultado} o `error` {mensaje}.
Todo lo demás va a `<carpeta>/proceso.log`. Este proceso usa el camino de v3.1 (cliente de Open-Meteo, mapa de 7 clases,
humedad muerta, GEE); nunca carga v4.0 (D-E3-24, punto 14).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import signal
import sys
import time
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
REPO = APP.parent
sys.path.insert(0, str(REPO / "src" / "v3.1" / "src"))
sys.path.insert(0, str(APP))


def _cortado(_num, _marco) -> None:
    """El servidor corta el trabajo con SIGTERM al cerrarse (en Linux y macOS). Se convierte en una excepción para que
    `evento_rt.crear` borre lo que dejó a medio armar y el aviso de error salga igual."""
    raise InterruptedError("el servidor cortó el trabajo de datos (se cerró)")


def main() -> int:
    if os.name != "nt":
        signal.signal(signal.SIGTERM, _cortado)
    ap = argparse.ArgumentParser(description="Trabajo de datos del simulador (pronóstico, índices, evento generado)")
    ap.add_argument("--trabajo", required=True)
    a = ap.parse_args()
    carpeta = Path(a.trabajo).resolve()

    avisos = os.fdopen(os.dup(1), "w", encoding="utf-8", newline="\n")
    registro = open(carpeta / "proceso.log", "a", encoding="utf-8", errors="replace", buffering=1)
    sys.stdout.flush(); sys.stderr.flush()
    os.dup2(registro.fileno(), 1); os.dup2(registro.fileno(), 2)
    sys.stdout = registro; sys.stderr = registro
    logging.basicConfig(level=logging.INFO, stream=registro, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    t0 = time.time()

    def avisar(tipo: str, **campos) -> None:
        avisos.write(json.dumps({"aviso": tipo, **campos}, ensure_ascii=False, default=str) + "\n")
        avisos.flush()

    def progreso(hechos: int, total: int, texto: str) -> None:
        avisar("progreso", hechos=int(hechos), total=int(total), texto=str(texto), s=round(time.time() - t0, 1))

    def texto(t: str) -> None:
        print(t, flush=True)
        progreso(0, 0, t)

    try:
        pedido = json.loads((carpeta / "pedido.json").read_text(encoding="utf-8"))
        tarea, p = pedido["tarea"], pedido.get("parametros") or {}
        from datos import evento_rt, indices, meteo
        if tarea == "pronostico":
            r = meteo.pronostico(modelo=p.get("modelo", meteo.MODELO), respaldo=p.get("respaldo", meteo.RESPALDO), aviso=texto)
        elif tarea == "meteo_manual":
            r = meteo.toma_manual((carpeta / p["archivo"]).read_bytes(), p.get("nombre") or p["archivo"])
        elif tarea == "escenario":
            r = meteo.toma_escenario(p["desde_utc"], int(p["horas"]), p["temp_c"], p["hr_pct"], p["viento_kmh"],
                                     p["viento_dir_deg"], p.get("precip_mm", 0.0))
        elif tarea in ("indices_aws", "indices_gee"):
            fecha = dt.date.fromisoformat(p["fecha_corrida"]) if p.get("fecha_corrida") else \
                dt.datetime.now(evento_rt.HUSO_LOCAL).date()
            r = indices.toma_aws(fecha, progreso) if tarea == "indices_aws" else indices.toma_gee(fecha)
        elif tarea == "indices_manual":
            r = indices.toma_manual(carpeta / p["ndvi"], carpeta / p["ndmi"], p["ventana"], p["ndmi_nir"],
                                    p.get("nombre_ndvi") or p["ndvi"], p.get("nombre_ndmi") or p["ndmi"], p.get("descripcion", ""))
        elif tarea == "evento":
            tm = {t["id"]: t for t in meteo.tomas()}
            ti = {t["id"]: t for t in indices.tomas()}
            if p.get("meteo") not in tm:
                raise ValueError(f"no existe la toma de meteorología {p.get('meteo')!r}")
            if p.get("indices") not in ti:
                raise ValueError(f"no existe la toma de índices {p.get('indices')!r}")
            r = evento_rt.crear(tm[p["meteo"]], ti[p["indices"]], p.get("nombre"), aviso=texto)
        else:
            raise ValueError(f"tarea desconocida: {tarea!r}")
    except Exception as e:
        traceback.print_exc()
        avisar("error", mensaje=f"{e}", clase=type(e).__name__, s=round(time.time() - t0, 1))
        return 1
    (carpeta / "resultado.json").write_text(json.dumps(r, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    avisar("final", resultado=r, s=round(time.time() - t0, 1))
    return 0


if __name__ == "__main__":
    codigo = main()
    try:
        sys.stdout.flush()
    except Exception:
        pass
    os._exit(codigo)
