"""Gestor de corridas: crea la carpeta de cada corrida, lanza su proceso motor, lee sus avisos y le manda órdenes.

Cada corrida vive en `resultados/app/<id>/`:
    corrida.json      lo que se pidió (lo escribe el servidor) y, al final, bitácora y resultados (los agrega el proceso)
    estado.json       estado que lleva el servidor; con esto se reconstruye la lista al volver a arrancar
    eventos.jsonl     todos los avisos del proceso y los cambios de estado, numerados
    t_llegada_parcial.npy, salida/, proceso.log   los escribe el proceso motor

Estados: creada → iniciando → corriendo ⇄ (pausando →) pausada → terminada | detenida | error | interrumpida.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import VERSION

REPO = Path(__file__).resolve().parents[2]
MOTORES_REALES = ("v4.0", "v3.1-libre", "v3.1-librev2")
AMBOS = ("v4.0", "v3.1-librev2")              # modo "ambos": la línea principal y el control (decisión D-E3-01)
CORTO = {"v4.0": "v40", "v3.1-libre": "v31libre", "v3.1-librev2": "v31librev2", "simulado": "sim"}
ACTIVOS = {"iniciando", "corriendo", "pausando", "pausada", "deteniendo"}
FINALES = {"terminada", "detenida", "error", "interrumpida"}
LIMITE_ACTIVAS = 2
FORMATO = "incendios_sl.corrida/1.1"


class Rechazo(Exception):
    """Un pedido que no se puede cumplir. `codigo` es el código HTTP que le corresponde."""

    def __init__(self, mensaje: str, codigo: int = 409):
        super().__init__(mensaje)
        self.codigo = codigo


def ahora() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def escribir_json(ruta: Path, datos: dict) -> None:
    tmp = ruta.with_name(ruta.name + ".tmp")
    tmp.write_text(json.dumps(datos, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    os.replace(tmp, ruta)


class Corrida:
    def __init__(self, id_: str, carpeta: Path, motor: str, pedido: dict, grupo: str | None = None,
                 creada_utc: str | None = None, estado: str = "creada"):
        self.id = id_
        self.carpeta = carpeta
        self.motor = motor
        self.pedido = pedido
        self.grupo = grupo
        self.creada_utc = creada_utc or ahora()
        self.estado = estado
        self.listo: dict | None = None
        self.ultima_hora: dict | None = None
        self.final: dict | None = None
        self.error: str | None = None
        self.eventos: list[dict] = []
        self.proceso: subprocess.Popen | None = None
        self.candado = threading.RLock()
        self._archivo_eventos = None

    # ------------------------------------------------------------------ estado en disco
    def resumen(self) -> dict:
        return {"id": self.id, "motor": self.motor, "grupo": self.grupo, "estado": self.estado, "creada_utc": self.creada_utc,
                "pedido": self.pedido, "listo": self.listo, "ultima_hora": self.ultima_hora, "final": self.final,
                "error": self.error, "n_eventos": len(self.eventos)}

    def guardar(self) -> None:
        escribir_json(self.carpeta / "estado.json", self.resumen() | {"actualizado_utc": ahora()})

    def anotar(self, evento: dict) -> None:
        """Suma un evento a la lista (y al archivo). Los eventos van numerados desde 1."""
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
            self.anotar({"aviso": "estado", "estado": estado, **extra})
            self.guardar()
            if estado in FINALES and self._archivo_eventos is not None:
                self._archivo_eventos.close()
                self._archivo_eventos = None

    def detalle(self) -> dict:
        d = self.resumen()
        ruta = self.carpeta / "corrida.json"
        if self.estado in FINALES and ruta.exists():
            try:
                c = json.loads(ruta.read_text(encoding="utf-8"))
                d["bitacora"] = c.get("bitacora") or []
                d["resultados"] = c.get("resultados")
            except (json.JSONDecodeError, OSError):
                pass
        return d


class Gestor:
    def __init__(self, carpeta: Path | None = None, permitir_simulado: bool = False, limite_activas: int = LIMITE_ACTIVAS):
        self.carpeta = Path(carpeta) if carpeta else REPO / "resultados" / "app"
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self.permitir_simulado = permitir_simulado
        self.limite_activas = limite_activas
        self.corridas: dict[str, Corrida] = {}
        self.candado = threading.RLock()
        self._recuperar()

    # ------------------------------------------------------------------ arranque
    def _recuperar(self) -> None:
        """Lee las corridas que quedaron en disco. Las que estaban en marcha cuando el servidor se cerró quedan
        como interrumpidas: no se retoman (decisión D-E3-19)."""
        for ruta in sorted(self.carpeta.glob("*/estado.json")):
            try:
                e = json.loads(ruta.read_text(encoding="utf-8"))
                c = Corrida(e["id"], ruta.parent, e["motor"], e.get("pedido") or {}, e.get("grupo"), e.get("creada_utc"), e["estado"])
            except (json.JSONDecodeError, OSError, KeyError):
                continue
            c.listo, c.ultima_hora, c.final, c.error = e.get("listo"), e.get("ultima_hora"), e.get("final"), e.get("error")
            archivo = ruta.parent / "eventos.jsonl"
            if archivo.exists():
                for linea in archivo.read_text(encoding="utf-8").splitlines():
                    try:
                        c.eventos.append(json.loads(linea))
                    except json.JSONDecodeError:
                        pass
            if c.estado in ACTIVOS:
                c.error = "El servidor se cerró mientras la corrida estaba en marcha. Queda lo que se había guardado."
                c.cambiar_estado("interrumpida", motivo=c.error)
            self.corridas[c.id] = c

    # ------------------------------------------------------------------ consultas
    def obtener(self, id_: str) -> Corrida:
        c = self.corridas.get(id_)
        if c is None:
            raise Rechazo(f"no existe la corrida {id_}", 404)
        return c

    def lista(self) -> list[dict]:
        return [c.resumen() for c in sorted(self.corridas.values(), key=lambda c: c.creada_utc, reverse=True)]

    def activas(self) -> int:
        return sum(c.estado in ACTIVOS for c in self.corridas.values())

    # ------------------------------------------------------------------ crear
    def crear(self, pedido: dict) -> list[Corrida]:
        """Crea una corrida, o dos si el motor pedido es "ambos". No la inicia."""
        motor = pedido.get("motor")
        if motor == "ambos":
            motores, grupo = AMBOS, "G-" + secrets.token_hex(3)
        elif motor in MOTORES_REALES or (motor == "simulado" and self.permitir_simulado):
            motores, grupo = (motor,), None
        else:
            opciones = list(MOTORES_REALES) + ["ambos"] + (["simulado"] if self.permitir_simulado else [])
            raise Rechazo(f"motor {motor!r} desconocido; opciones: {', '.join(opciones)}", 422)
        with self.candado:
            return [self._crear_una(m, pedido, grupo) for m in motores]

    def _crear_una(self, motor: str, pedido: dict, grupo: str | None) -> Corrida:
        momento = dt.datetime.now(dt.timezone.utc)
        id_ = f"{momento:%Y%m%d-%H%M%S}-{CORTO[motor]}-{secrets.token_hex(2)}"
        carpeta = self.carpeta / id_
        carpeta.mkdir(parents=True)
        configuracion = {k: pedido[k] for k in ("ignicion", "t_inicio_utc", "horas") if pedido.get(k) not in (None, [], "")}
        corrida = {"formato": FORMATO, "id": id_, "creada_utc": ahora(), "grupo": grupo,
                   "programa": {"version": VERSION, "congelado_sha256": sha_congelado()}, "motor": motor}
        if motor == "simulado":
            corrida |= {"configuracion": configuracion, "simulado": pedido.get("simulado") or {}}
        else:
            definicion = {"evento": pedido["evento"], "validar": False, "figuras": False}
            if pedido.get("hipotesis") is not None:
                definicion["hipotesis"] = int(pedido["hipotesis"])
            if pedido.get("ignicion_ficha") and not pedido.get("ignicion"):
                definicion["ignicion"] = str(pedido["ignicion_ficha"])
            corrida |= {"base": {"definicion": definicion}, "configuracion": configuracion}
        escribir_json(carpeta / "corrida.json", corrida)
        guardado = {k: v for k, v in pedido.items() if k not in ("iniciar",) and v is not None} | {"motor": motor}
        c = Corrida(id_, carpeta, motor, guardado, grupo)
        c.anotar({"aviso": "estado", "estado": "creada"})
        c.guardar()
        self.corridas[id_] = c
        return c

    # ------------------------------------------------------------------ control
    def iniciar(self, id_: str) -> Corrida:
        c = self.obtener(id_)
        with self.candado:
            if c.estado != "creada":
                raise Rechazo(f"la corrida ya se inició (estado: {c.estado})")
            if self.activas() >= self.limite_activas:
                raise Rechazo(f"ya hay {self.limite_activas} corridas en marcha, que es el máximo; esperá a que termine una o detenela")
            guion = "proceso_simulado.py" if c.motor == "simulado" else "proceso.py"
            entorno = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
            entorno.pop("PYTHONPATH", None)
            # Grupo de procesos propio: un Ctrl+C en la consola del servidor no mata al motor de golpe; lo cierra el servidor.
            aparte = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True})
            arranque = open(c.carpeta / "arranque.log", "w", encoding="utf-8", errors="replace")
            c.proceso = subprocess.Popen([sys.executable, str(REPO / "app" / "motores" / guion), "--corrida", str(c.carpeta)],
                                         cwd=REPO, env=entorno, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=arranque,
                                         text=True, encoding="utf-8", errors="replace", bufsize=1, **aparte)
            arranque.close()
            c.cambiar_estado("iniciando")
            threading.Thread(target=self._leer_avisos, args=(c,), name=f"avisos-{c.id}", daemon=True).start()
        return c

    def _ordenar(self, c: Corrida, orden: dict) -> None:
        p = c.proceso
        if p is None or p.poll() is not None:
            raise Rechazo("el proceso motor de esta corrida ya no está en marcha")
        try:
            with c.candado:
                p.stdin.write(json.dumps(orden, ensure_ascii=False) + "\n")
                p.stdin.flush()
        except (OSError, ValueError):
            raise Rechazo("no se pudo enviar la orden: el proceso motor cerró su entrada")

    def pausar(self, id_: str) -> Corrida:
        c = self.obtener(id_)
        with c.candado:
            if c.estado not in ("iniciando", "corriendo"):
                raise Rechazo(f"solo se pausa una corrida en marcha (estado: {c.estado})")
            self._ordenar(c, {"orden": "pausar"})
            c.cambiar_estado("pausando")
        return c

    def reanudar(self, id_: str) -> Corrida:
        c = self.obtener(id_)
        with c.candado:
            if c.estado not in ("pausando", "pausada"):
                raise Rechazo(f"solo se reanuda una corrida en pausa (estado: {c.estado})")
            self._ordenar(c, {"orden": "reanudar"})
            c.cambiar_estado("corriendo")
        return c

    def detener(self, id_: str) -> Corrida:
        c = self.obtener(id_)
        with c.candado:
            if c.estado not in ACTIVOS:
                raise Rechazo(f"la corrida no está en marcha (estado: {c.estado})")
            self._ordenar(c, {"orden": "detener"})
            c.cambiar_estado("deteniendo")
        return c

    def intervenir(self, id_: str, entrada: dict, espera_s: float = 5.0) -> dict:
        """Manda una intervención al proceso y devuelve su respuesta. Solo con la corrida en pausa."""
        c = self.obtener(id_)
        with c.candado:
            if c.estado != "pausada":
                raise Rechazo("solo se interviene con la corrida en pausa")
            desde = len(c.eventos)
            self._ordenar(c, {"orden": "intervenir", "entrada": entrada})
        limite = time.monotonic() + espera_s
        while time.monotonic() < limite:
            for e in c.eventos[desde:]:
                if e.get("aviso") == "intervencion":
                    return e
            time.sleep(0.05)
        raise Rechazo("el proceso motor no respondió a la intervención", 504)

    # ------------------------------------------------------------------ lectura de avisos (un hilo por corrida en marcha)
    def _leer_avisos(self, c: Corrida) -> None:
        p = c.proceso
        try:
            for linea in p.stdout:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    a = json.loads(linea)
                except json.JSONDecodeError:
                    a = {"aviso": "error", "mensaje": f"línea que no es un aviso: {linea[:200]}", "fatal": False}
                self._atender_aviso(c, a)
        except (OSError, ValueError):
            pass
        codigo = p.wait()
        with c.candado:
            if c.estado == "interrumpida":             # la cerró el servidor al apagarse
                return
            if c.final is not None and codigo == 0:
                c.cambiar_estado("terminada" if c.final.get("completa", True) else "detenida")
            else:
                if not c.error:
                    c.error = f"El proceso motor terminó sin avisar (código {codigo})." + self._cola_del_registro(c)
                c.cambiar_estado("error", motivo=c.error)

    def _atender_aviso(self, c: Corrida, a: dict) -> None:
        with c.candado:
            tipo = a.get("aviso")
            c.anotar(a)
            if tipo == "listo":
                c.listo = a
                if c.estado == "iniciando":
                    c.cambiar_estado("corriendo")
            elif tipo == "hora":
                c.ultima_hora = a
                if c.estado == "iniciando":
                    c.cambiar_estado("corriendo")
            elif tipo == "pausado":
                if c.estado == "pausando":
                    c.cambiar_estado("pausada", t_sim_min=a.get("t_sim_min"))
            elif tipo == "final":
                c.final = a
            elif tipo == "error" and a.get("fatal"):
                c.error = str(a.get("mensaje"))
            if tipo in ("listo", "hora", "final") or (tipo == "error" and a.get("fatal")):
                c.guardar()

    @staticmethod
    def _cola_del_registro(c: Corrida, lineas: int = 6) -> str:
        for nombre in ("proceso.log", "arranque.log"):
            ruta = c.carpeta / nombre
            if ruta.exists():
                texto = ruta.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-lineas:]
                if texto:
                    return f" Últimas líneas de {nombre}: " + " | ".join(t.strip() for t in texto)
        return ""

    # ------------------------------------------------------------------ cierre
    def cerrar(self, espera_s: float = 15.0) -> None:
        """Al cerrar el servidor: pide detener a las corridas en marcha, espera un poco y mata a las que no cerraron."""
        vivas = [c for c in self.corridas.values() if c.proceso is not None and c.proceso.poll() is None]
        for c in vivas:
            try:
                self._ordenar(c, {"orden": "detener"})
            except Rechazo:
                pass
        limite = time.monotonic() + espera_s
        for c in vivas:
            try:
                c.proceso.wait(timeout=max(0.1, limite - time.monotonic()))
            except subprocess.TimeoutExpired:
                c.proceso.kill()
                c.error = "El servidor se cerró y el proceso motor no llegó a guardar."
                c.cambiar_estado("interrumpida", motivo=c.error)
        time.sleep(0.2)                              # deja que los hilos lectores anoten el estado final


_SHA_CONGELADO: list[str | None] = []


def sha_congelado() -> str | None:
    if not _SHA_CONGELADO:
        try:
            _SHA_CONGELADO.append(json.loads((REPO / "congelado.json").read_text(encoding="utf-8"))["sha256_del_conjunto"])
        except (OSError, json.JSONDecodeError, KeyError):
            _SHA_CONGELADO.append(None)
    return _SHA_CONGELADO[0]
