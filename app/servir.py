"""Arranca el simulador: levanta el servidor local y abre el navegador.

    python app/servir.py                    en http://127.0.0.1:8000 (si el puerto está ocupado, prueba los siguientes)
    python app/servir.py --sin-navegador    no abre el navegador
    python app/servir.py --puerto 8010
    python app/servir.py --con-simulado     habilita el motor simulado (un fuego de mentira, para probar)

El servidor escucha solo en esta computadora (127.0.0.1). Se cierra con Ctrl+C: antes pide a las corridas en marcha que
guarden lo simulado.
"""
from __future__ import annotations

import argparse
import socket
import sys
import threading
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def puerto_libre(desde: int, intentos: int = 20) -> int:
    for puerto in range(desde, desde + intentos):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", puerto))
                return puerto
            except OSError:
                continue
    raise SystemExit(f"No hay un puerto libre entre {desde} y {desde + intentos - 1}. Probá con --puerto.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Simulador interactivo de incendios — servidor local")
    ap.add_argument("--puerto", type=int, default=8000)
    ap.add_argument("--sin-navegador", action="store_true")
    ap.add_argument("--con-simulado", action="store_true", help="habilita el motor simulado, para pruebas")
    a = ap.parse_args()

    import uvicorn
    from servidor.app import crear_app

    puerto = puerto_libre(a.puerto)
    direccion = f"http://127.0.0.1:{puerto}"
    print(f"Simulador en {direccion}   (Ctrl+C para cerrar)", flush=True)
    if puerto != a.puerto:
        print(f"El puerto {a.puerto} estaba ocupado; se usa el {puerto}.", flush=True)
    if not a.sin_navegador:
        threading.Timer(1.2, webbrowser.open, args=(direccion,)).start()
    uvicorn.run(crear_app(permitir_simulado=a.con_simulado), host="127.0.0.1", port=puerto, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
