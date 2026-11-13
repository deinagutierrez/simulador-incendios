"""Gestor de trabajos de datos (fase F4): pronóstico, índices, carga manual, modo escenario y evento generado `RT-…`.

Cada trabajo lanza `app/datos/proceso_datos.py`, un proceso aparte con el camino de v3.1 (D-E3-24, punto 14): el servidor
no carga ningún motor. Se hace un trabajo de datos a la vez.

Cada trabajo vive en `datos/procesados/app/trabajos/<id>/`:
    pedido.json       {tarea, parametros} (lo escribe el servidor; lo lee el proceso de datos)
    estado.json       estado que lleva el servidor; con esto se reconstruye la lista al volver a arrancar
    eventos.jsonl     los avisos del proceso y los cambios de estado, numerados
    resultado.json, proceso.log   los escribe el proceso de datos
    arranque.log      lo que el proceso escribe antes de redirigir su salida (errores de importación, por ejemplo)

Estados: creado → corriendo → terminado | error | interrumpido.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import threading
from pathlib import Path

from .corridas import REPO, Rechazo, ahora, escribir_json

GUION = REPO / "app" / "datos" / "proceso_datos.py"
ACTIVOS = {"creado", "corriendo"}
FINALES = {"terminado", "error", "interrumpido"}
TAREAS = ("pronostico", "meteo_manual", "escenario", "indices_aws", "indices_gee", "indices_manual", "evento")


def carpeta_por_defecto() -> Path:
    from datos import comun                       # app/datos (no carga ningún motor)
    return comun.CACHE / "trabajos"


class Trabajo:
    def __init__(self, id_: str, carpeta: Path, tarea: str, parametros: dict, creado_utc: str | None = None,
                 estado: str = "creado"):
        self.id = id_
        self.carpeta = carpeta
        self.tarea = tarea
        self.parametros = parametros
        self.creado_utc = creado_utc or ahora()
        self.terminado_utc: str | None = None
        self.estado = estado
        self.progreso: dict | None = None
        self.resultado: dict | None = None
        self.error: str | None = None
        self.eventos: list[dict] = []
        self.proceso: subprocess.Popen | None = None
        self.candado = threading.RLock()
        self._archivo_eventos = None

    def resumen(self) -> dict:
        return {"id": self.id, "tarea": self.tarea, "parametros": self.parametros, "estado": self.estado,
                "creado_utc": self.creado_utc, "terminado_utc": self.terminado_utc, "progreso": self.progreso,
                "resultado": self.resultado, "error": self.error, "n_eventos": len(self.eventos)}

    def guardar(self) -> None:
        escribir_json(self.carpeta / "estado.json", self.resumen() | {"actualizado_utc": ahora()})

    def anotar(self, evento: dict) -> None:
        with self.candado:
            evento = {"n": len(self.eventos) + 1, **evento}
            self.eventos.append(evento)
            if self._archivo_eventos is None:
                self._archivo_eventos = open(self.carpeta / "eventos.jsonl", "a", encoding="utf-8", buffering=1)
            self._archivo_eventos.write(json.dumps(evento, ensure_ascii=False, default=str) + "\n")

    def cambiar_estado(self, estado: str, **extra) -> None:
        with self.candado:
            if self.estado == estado:
                return
            self.estado = estado
            if estado in FINALES:
                self.terminado_utc = ahora()
            self.anotar({"aviso": "estado", "estado": estado, **extra})
            self.guardar()
            if estado in FINALES and self._archivo_eventos is not None:
                self._archivo_eventos.close()
                self._archivo_eventos = None


class GestorDatos:
    """`guion`: el programa que hace el trabajo (por defecto `app/datos/proceso_datos.py`; las pruebas ponen uno falso).
    `al_terminar(trabajo)`: se llama cuando un trabajo llega a un estado final (el servidor refresca la lista de eventos)."""

    def __init__(self, carpeta: Path | None = None, guion: Path | None = None, al_terminar=None):
        self.carpeta = Path(carpeta) if carpeta else carpeta_por_defecto()
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self.guion = Path(guion) if guion else GUION
        self.al_terminar = al_terminar
        self.trabajos: dict[str, Trabajo] = {}
        self.candado = threading.RLock()
        self._recuperar()

    @property
    def espera(self) -> Path:
        """Carpeta donde quedan los TIF de índices subidos hasta que se lanza la carga manual."""
        return self.carpeta / "_espera"

    # ------------------------------------------------------------------ arranque
    def _recuperar(self) -> None:
        """Lee los trabajos que quedaron en disco. Los que estaban en marcha cuando el servidor se cerró quedan como
        interrumpidos: no se retoman (hay que pedirlos de nuevo)."""
        for ruta in sorted(self.carpeta.glob("*/estado.json")):
            try:
                e = json.loads(ruta.read_text(encoding="utf-8"))
                t = Trabajo(e["id"], ruta.parent, e["tarea"], e.get("parametros") or {}, e.get("creado_utc"), e["estado"])
            except (json.JSONDecodeError, OSError, KeyError):
                continue
            t.terminado_utc, t.progreso, t.resultado, t.error = (e.get("terminado_utc"), e.get("progreso"), e.get("resultado"),
                                                                 e.get("error"))
            archivo = ruta.parent / "eventos.jsonl"
            if archivo.exists():
                for linea in archivo.read_text(encoding="utf-8").splitlines():
                    try:
                        t.eventos.append(json.loads(linea))
                    except json.JSONDecodeError:
                        pass
            if t.estado in ACTIVOS:
                t.error = "El servidor se cerró mientras el trabajo estaba en marcha. Hay que pedirlo de nuevo."
                t.cambiar_estado("interrumpido", motivo=t.error)
            self.trabajos[t.id] = t

    # ------------------------------------------------------------------ consultas
    def obtener(self, id_: str) -> Trabajo:
        t = self.trabajos.get(id_)
        if t is None:
            raise Rechazo(f"no existe el trabajo de datos {id_}", 404)
        return t

    def en_marcha(self) -> Trabajo | None:
        return next((t for t in self.trabajos.values() if t.estado in ACTIVOS), None)

    def ultimo(self) -> Trabajo | None:
        """El trabajo en marcha o, si no hay, el último que se pidió."""
        return self.en_marcha() or max(self.trabajos.values(), key=lambda t: (t.creado_utc, t.id), default=None)

    def lista(self) -> list[dict]:
        return [t.resumen() for t in sorted(self.trabajos.values(), key=lambda t: (t.creado_utc, t.id), reverse=True)]

    # ------------------------------------------------------------------ crear y lanzar
    def lanzar(self, tarea: str, parametros: dict, archivos: dict[str, bytes | Path] | None = None) -> Trabajo:
        """Crea el trabajo y lanza su proceso. `archivos`: nombre en la carpeta del trabajo → contenido (bytes) o un
        archivo que se mueve ahí. Si ya hay un trabajo en marcha, se rechaza (409) y no se toca nada."""
        if tarea not in TAREAS:
            raise Rechazo(f"tarea de datos desconocida: {tarea!r}", 422)
        with self.candado:
            actual = self.en_marcha()
            if actual is not None:
                raise Rechazo(f"ya hay un trabajo de datos en marcha ({actual.tarea}, {actual.id}); se hace uno a la vez: "
                              "esperá a que termine")
            momento = dt.datetime.now(dt.timezone.utc)
            id_ = f"{momento:%Y%m%d-%H%M%S}-{tarea}-{secrets.token_hex(2)}"
            carpeta = self.carpeta / id_
            carpeta.mkdir(parents=True)
            for nombre, contenido in (archivos or {}).items():
                destino = carpeta / Path(nombre).name
                if isinstance(contenido, (bytes, bytearray)):
                    destino.write_bytes(contenido)
                else:
                    shutil.move(str(contenido), destino)
            escribir_json(carpeta / "pedido.json", {"tarea": tarea, "parametros": parametros})
            t = Trabajo(id_, carpeta, tarea, parametros)
            t.anotar({"aviso": "estado", "estado": "creado"})
            t.guardar()
            self.trabajos[id_] = t
            entorno = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
            entorno.pop("PYTHONPATH", None)
            for clave in [k for k in entorno if k.startswith("INCENDIOS_SL_")]:   # rutas propias del usuario: v3.1
                entorno.pop(clave)                                                  # escribiría fuera del repositorio
            # Grupo de procesos propio, como los procesos motor: un Ctrl+C en la consola no lo corta a mitad de una escritura.
            aparte = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True})
            try:
                with open(carpeta / "arranque.log", "w", encoding="utf-8", errors="replace") as arranque:
                    t.proceso = subprocess.Popen([sys.executable, str(self.guion), "--trabajo", str(carpeta)], cwd=REPO,
                                                 env=entorno, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=arranque,
                                                 text=True, encoding="utf-8", errors="replace", bufsize=1, **aparte)
            except OSError as e:
                t.error = f"no se pudo lanzar el proceso de datos: {e}"
                t.cambiar_estado("error", motivo=t.error)
                self._avisar_fin(t)
                return t
            t.cambiar_estado("corriendo")
            threading.Thread(target=self._leer_avisos, args=(t,), name=f"datos-{id_}", daemon=True).start()
        return t

    # ------------------------------------------------------------------ lectura de avisos
    def _leer_avisos(self, t: Trabajo) -> None:
        p = t.proceso
        try:
            for linea in p.stdout:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    a = json.loads(linea)
                except json.JSONDecodeError:
                    a = {"aviso": "texto", "texto": linea[:500]}
                self._atender_aviso(t, a)
        except (OSError, ValueError):
            pass
        codigo = p.wait()
        with t.candado:
            if t.estado == "interrumpido":            # lo cerró el servidor al apagarse
                return
            if t.resultado is not None and codigo == 0:
                t.cambiar_estado("terminado")
            else:
                if not t.error:
                    t.error = f"El proceso de datos terminó sin avisar (código {codigo})." + self._cola_del_registro(t)
                t.cambiar_estado("error", motivo=t.error)
        self._avisar_fin(t)

    def _atender_aviso(self, t: Trabajo, a: dict) -> None:
        with t.candado:
            tipo = a.get("aviso")
            t.anotar(a)
            if tipo == "progreso":
                t.progreso = {k: a.get(k) for k in ("hechos", "total", "texto", "s")}
            elif tipo == "final":
                r = a.get("resultado")
                t.resultado = r if isinstance(r, dict) else {"valor": r}
                t.guardar()
            elif tipo == "error":
                t.error = str(a.get("mensaje") or "error sin mensaje")
                t.guardar()

    def _avisar_fin(self, t: Trabajo) -> None:
        if self.al_terminar is not None:
            try:
                self.al_terminar(t)
            except Exception:                         # un error al refrescar no tiene que tumbar el hilo lector
                pass

    @staticmethod
    def _cola_del_registro(t: Trabajo, lineas: int = 6) -> str:
        for nombre in ("proceso.log", "arranque.log"):
            ruta = t.carpeta / nombre
            if ruta.exists():
                texto = ruta.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-lineas:]
                if texto:
                    return f" Últimas líneas de {nombre}: " + " | ".join(x.strip() for x in texto)
        return ""

    # ------------------------------------------------------------------ cierre
    def cerrar(self, espera_s: float = 5.0) -> None:
        """Al cerrar el servidor: un trabajo de datos no se puede pausar ni guardar a medias, así que se corta y queda
        interrumpido (lo que dejó a medio escribir no se usa: las tomas se escriben al final, de una vez)."""
        for t in list(self.trabajos.values()):
            p = t.proceso
            if p is None or p.poll() is not None:
                continue
            with t.candado:
                t.error = "El servidor se cerró con el trabajo en marcha. Hay que pedirlo de nuevo."
                t.cambiar_estado("interrumpido", motivo=t.error)
            try:
                if os.name == "nt":
                    p.terminate()
                else:
                    os.killpg(p.pid, signal.SIGTERM)
                p.wait(timeout=espera_s)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    p.kill()
                except OSError:
                    pass
