"""Gestor de corridas: crea la carpeta de cada corrida, lanza su proceso motor, lee sus avisos y le manda órdenes.

Cada corrida vive en `resultados/app/<id>/`:
    corrida.json      lo que se pidió (lo escribe el servidor) y, al final, bitácora y resultados (los agrega el proceso)
    estado.json       estado que lleva el servidor; con esto se reconstruye la lista al volver a arrancar
    eventos.jsonl     todos los avisos del proceso y los cambios de estado, numerados
    t_llegada_parcial.npy, salida/, proceso.log   los escribe el proceso motor
    bitacora.jsonl    (F5) la bitácora encadenada, entrada por entrada en el momento; la escribe el proceso motor

`corrida.json` lleva además, desde el formato 1.2, el bloque `insumos` (procedencia de los datos de un evento generado
`RT-…`, Anexo C del plan) y `advertencias` (sus rótulos y avisos, o "EJEMPLO" para un evento con ficha).

Estados: creada → iniciando → corriendo ⇄ (pausando →) pausada → terminada | detenida | error | interrumpida.

Intervenciones (F5, contrato 1.5 §4.2): con la corrida en pausa, el servidor manda `intervenir` con un `ref` propio y espera
el aviso `intervencion` con ese `ref`. La bitácora se junta de los avisos mientras la corrida está en marcha. En un grupo
"ambos", las dos corridas se pausan en la misma hora (`pausar` con `en_t_sim_min`) y reciben la misma intervención. Una
corrida se puede reproducir desde su bitácora: la nueva copia tal cual la configuración de `corrida.json` y lleva
`reproduccion`; la aplica el propio proceso motor.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import secrets
import subprocess
import sys
import threading
import math
import time
from pathlib import Path

from . import VERSION, datos
from .trazos import iv

REPO = Path(__file__).resolve().parents[2]
MOTORES_REALES = ("v4.0", "v3.1-libre", "v3.1-librev2")
AMBOS = ("v4.0", "v3.1-librev2")              # modo "ambos": la línea principal y el control (decisión D-E3-01)
CORTO = {"v4.0": "v40", "v3.1-libre": "v31libre", "v3.1-librev2": "v31librev2", "simulado": "sim"}
ACTIVOS = {"iniciando", "corriendo", "pausando", "pausada", "deteniendo"}
FINALES = {"terminada", "detenida", "error", "interrumpida"}
LIMITE_ACTIVAS = 2
FORMATO = "incendios_sl.corrida/1.2"
ESPERA_INTERVENCION_S = 30.0              # el trazo de v3.1 tarda unos 5 s (D-E3-28, punto 21)
AVISOS_CON_ENTRADA = ("pausado", "reanudado", "intervencion", "detenido")
# lo que una reproducción copia tal cual de la corrida original (contrato §1.3); `simulado` y `advertencias` también, para
# que el motor simulado use la misma grilla y la pantalla muestre los mismos rótulos
COPIA_REPRODUCCION = ("formato", "motor", "base", "configuracion", "insumos", "programa", "simulado", "advertencias")


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
        self.t_pausa: float | None = None          # hora simulada de la pausa actual (con estado "pausada")
        self.pausa_en: float | None = None         # hora simulada pedida para la próxima pausa (con estado "pausando")
        self.bitacora_viva: list[dict] = []        # entradas de la bitácora que llegaron en los avisos

    @property
    def reproduccion_de(self) -> str | None:
        return self.pedido.get("reproduccion_de")

    # ------------------------------------------------------------------ estado en disco
    def resumen(self) -> dict:
        return {"id": self.id, "motor": self.motor, "grupo": self.grupo, "estado": self.estado, "creada_utc": self.creada_utc,
                "pedido": self.pedido, "listo": self.listo, "ultima_hora": self.ultima_hora, "final": self.final,
                "error": self.error, "n_eventos": len(self.eventos), "pausa_t_sim_min": self.t_pausa,
                "pausa_en_t_sim_min": self.pausa_en, "reproduccion_de": self.reproduccion_de}

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

    def sumar_a_la_bitacora(self, entrada) -> None:
        if isinstance(entrada, dict) and isinstance(entrada.get("n"), int):
            if all(e.get("n") != entrada["n"] for e in self.bitacora_viva):
                self.bitacora_viva.append(entrada)
                self.bitacora_viva.sort(key=lambda e: e["n"])

    def corrida_json(self) -> dict | None:
        try:
            return json.loads((self.carpeta / "corrida.json").read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def bitacora_jsonl(self) -> list[dict]:
        ruta = self.carpeta / "bitacora.jsonl"
        out = []
        try:
            lineas = ruta.read_text(encoding="utf-8").splitlines()
        except OSError:
            return out
        for linea in lineas:
            try:
                out.append(json.loads(linea))
            except json.JSONDecodeError:
                break                                # una línea a medio escribir: lo anterior vale
        return out

    def bitacora(self, corrida: dict | None = None) -> tuple[list[dict], str | None]:
        """(bitácora, raíz). Terminada: la de `corrida.json`. En marcha, con error o interrumpida: la más larga entre la que
        llegó en los avisos y `bitacora.jsonl`. La raíz, la que dejó el proceso o, mientras tanto, la calculada con la
        configuración inicial de `corrida.json` (la misma cuenta que hace el proceso)."""
        c = corrida if corrida is not None else self.corrida_json()
        if c is not None and self.estado in FINALES and isinstance(c.get("bitacora"), list):
            return c["bitacora"], c.get("bitacora_raiz")
        viva, disco = list(self.bitacora_viva), self.bitacora_jsonl()
        raiz = None
        if c is not None:
            try:
                raiz = c.get("bitacora_raiz") or iv.raiz(c)
            except (ValueError, TypeError):
                raiz = None
        return (disco if len(disco) > len(viva) else viva), raiz

    def estados_intervenciones(self) -> dict[int, str]:
        """n de la bitácora → estado del aviso `intervencion` (aceptada o recortada)."""
        return {e["n"]: e.get("estado") for e in self.eventos
                if e.get("aviso") == "intervencion" and isinstance(e.get("n"), int)}

    def detalle(self) -> dict:
        d = self.resumen()
        c = self.corrida_json()
        if c is not None and self.estado in FINALES:
            d["resultados"] = c.get("resultados")
        bitacora, raiz = self.bitacora(c)
        d["bitacora"] = bitacora
        d["bitacora_raiz"] = raiz
        d["bitacora_integra"] = iv.verificar_cadena(raiz, bitacora)[0] if raiz else None
        if c is not None:
            d["cortafuegos_iniciales"] = list((c.get("configuracion") or {}).get("cortafuegos") or [])
        return d


class Gestor:
    def __init__(self, carpeta: Path | None = None, permitir_simulado: bool = False, limite_activas: int = LIMITE_ACTIVAS):
        self.carpeta = Path(carpeta) if carpeta else REPO / "resultados" / "app"
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self.permitir_simulado = permitir_simulado
        self.limite_activas = limite_activas
        self.corridas: dict[str, Corrida] = {}
        self.candado = threading.RLock()
        self._alineando: dict[str, str] = {}
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
            for ev in c.eventos:
                if ev.get("aviso") in AVISOS_CON_ENTRADA:
                    c.sumar_a_la_bitacora(ev.get("entrada"))
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

    def del_grupo(self, grupo: str) -> list[Corrida]:
        cs = sorted((c for c in self.corridas.values() if c.grupo == grupo), key=lambda c: c.id)
        if not cs:
            raise Rechazo(f"no existe el grupo {grupo}", 404)
        return cs

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
        configuracion = {k: pedido[k] for k in ("ignicion", "t_inicio_utc", "horas", "cortafuegos")
                         if pedido.get(k) not in (None, [], "")}
        corrida = {"formato": FORMATO, "id": id_, "creada_utc": ahora(), "grupo": grupo,
                   "programa": {"version": VERSION, "congelado_sha256": sha_congelado()}, "motor": motor}
        if motor == "simulado":
            corrida |= {"configuracion": configuracion, "simulado": pedido.get("simulado") or {}}
        else:
            if pedido.get("definicion"):              # uso avanzado: la definición llega armada; la valida el proceso motor
                definicion = {"validar": False, "figuras": False} | dict(pedido["definicion"])
            else:
                definicion = {"evento": pedido["evento"], "validar": False, "figuras": False}
                if pedido.get("hipotesis") is not None:
                    definicion["hipotesis"] = int(pedido["hipotesis"])
                if pedido.get("ignicion_ficha") and not pedido.get("ignicion"):
                    definicion["ignicion"] = str(pedido["ignicion_ficha"])
            corrida |= {"base": {"definicion": definicion}, "configuracion": configuracion}
            # Procedencia de los insumos (Anexo C del plan): la de un evento generado RT-…, o el rótulo EJEMPLO.
            insumos, advertencias = datos.insumos_de_la_corrida(definicion.get("evento"))
            if insumos is not None:
                corrida["insumos"] = insumos
            if advertencias:
                corrida["advertencias"] = advertencias
        escribir_json(carpeta / "corrida.json", corrida)
        guardado = {k: v for k, v in pedido.items() if k not in ("iniciar",) and v is not None} | {"motor": motor}
        return self._registrar(id_, carpeta, motor, guardado, grupo)

    def _registrar(self, id_: str, carpeta: Path, motor: str, pedido: dict, grupo: str | None) -> Corrida:
        c = Corrida(id_, carpeta, motor, pedido, grupo)
        c.anotar({"aviso": "estado", "estado": "creada"})
        c.guardar()
        self.corridas[id_] = c
        return c

    def reproducir(self, id_: str) -> Corrida:
        """Crea una corrida que reproduce a `id_` desde su bitácora (contrato §1.3 y §4.2): su `corrida.json` copia tal cual
        la configuración de la original, con `id`, `creada_utc` y grupo nuevos, y agrega `reproduccion`. No la inicia."""
        o = self.obtener(id_)
        if o.estado not in ("terminada", "detenida"):
            raise Rechazo(f"solo se reproduce una corrida terminada o detenida (estado: {o.estado})")
        original = o.corrida_json()
        if original is None or not isinstance(original.get("bitacora"), list) or not original.get("bitacora_raiz"):
            raise Rechazo("la corrida no tiene bitácora encadenada (es anterior a la F5 o no llegó a guardarla)")
        if o.motor == "simulado" and not self.permitir_simulado:
            raise Rechazo("el motor simulado no está habilitado en este servidor (--con-simulado)", 422)
        with self.candado:
            momento = dt.datetime.now(dt.timezone.utc)
            nuevo = f"{momento:%Y%m%d-%H%M%S}-{CORTO[o.motor]}-{secrets.token_hex(2)}"
            carpeta = self.carpeta / nuevo
            carpeta.mkdir(parents=True)
            corrida = {"id": nuevo, "creada_utc": ahora(), "grupo": None}
            corrida |= {k: original[k] for k in COPIA_REPRODUCCION if k in original}
            actual = sha_congelado()
            previo = (original.get("programa") or {}).get("congelado_sha256")
            if previo != actual:
                corrida["advertencias"] = list(corrida.get("advertencias") or []) + [
                    f"el congelado de los motores cambió desde la corrida original ({str(previo)[:12]}… → {str(actual)[:12]}…): "
                    "la reproducción puede no dar lo mismo"]
            corrida["reproduccion"] = {"de": id_, "raiz": original["bitacora_raiz"], "bitacora": original["bitacora"]}
            escribir_json(carpeta / "corrida.json", corrida)
            pedido = {k: v for k, v in o.pedido.items() if k not in ("reproduccion_de",)} | {"motor": o.motor,
                                                                                             "reproduccion_de": id_}
            return self._registrar(nuevo, carpeta, o.motor, pedido, None)

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

    @staticmethod
    def hora_en_punto(en_t_sim_min) -> float:
        """La hora objetivo de una pausa, redondeada hacia arriba a la hora en punto (las pausas caen en hora en punto)."""
        if isinstance(en_t_sim_min, bool) or not isinstance(en_t_sim_min, (int, float)) or not math.isfinite(en_t_sim_min) \
                or en_t_sim_min < 0:
            raise Rechazo("`en_t_sim_min` tiene que ser un número de minutos simulados, 0 o más", 422)
        return float(math.ceil(float(en_t_sim_min) / 60.0 - 1e-9) * 60)

    def pausar(self, id_: str, en_t_sim_min: float | None = None) -> Corrida:
        """Pide la pausa: en la próxima hora en punto o, con `en_t_sim_min`, al llegar a esa hora simulada (si ya pasó, en la
        próxima). Con una pausa ya pedida (`pausando`) y otra hora, la reemplaza."""
        c = self.obtener(id_)
        objetivo = None if en_t_sim_min is None else self.hora_en_punto(en_t_sim_min)
        with c.candado:
            if c.estado not in ("iniciando", "corriendo") and not (c.estado == "pausando" and objetivo is not None):
                raise Rechazo(f"solo se pausa una corrida en marcha (estado: {c.estado})")
            self._ordenar(c, {"orden": "pausar"} if objetivo is None else {"orden": "pausar", "en_t_sim_min": objetivo})
            c.pausa_en = objetivo
            c.cambiar_estado("pausando")
        return c

    def reanudar(self, id_: str) -> Corrida:
        c = self.obtener(id_)
        with c.candado:
            if c.estado not in ("pausando", "pausada"):
                raise Rechazo(f"solo se reanuda una corrida en pausa (estado: {c.estado})")
            self._ordenar(c, {"orden": "reanudar"})
            c.t_pausa = c.pausa_en = None
            c.cambiar_estado("corriendo")
        return c

    # ------------------------------------------------------------------ grupo "ambos": pausa en la misma hora
    @staticmethod
    def _proxima_pausa_posible(c: Corrida) -> float:
        if c.estado == "pausada" and c.t_pausa is not None:
            return float(c.t_pausa)
        t = float((c.ultima_hora or {}).get("t_sim_min") or 0.0)
        return t + 60.0 if c.ultima_hora else 0.0

    def _pausar_en(self, c: Corrida, objetivo: float) -> None:
        """Deja a `c` pausada en `objetivo`, o encaminada a pausarse ahí (si está pausada antes, la reanuda hasta esa hora)."""
        with c.candado:
            if c.estado == "pausada":
                if c.t_pausa is not None and abs(c.t_pausa - objetivo) < 1e-6:
                    return
                self._ordenar(c, {"orden": "reanudar"})
                c.t_pausa = None
            self._ordenar(c, {"orden": "pausar", "en_t_sim_min": objetivo})
            c.pausa_en = objetivo
            c.cambiar_estado("pausando")

    def pausar_grupo(self, grupo: str, en_t_sim_min: float | None = None) -> dict:
        """Pausa las corridas de un grupo en la misma hora simulada: la pedida o, si no se pide o ya pasó para alguna, la
        primera hora en punto a la que todas pueden llegar. Si igual alguna se pasa (sus avisos van atrasados), un hilo las
        vuelve a alinear en la hora de la que quedó más adelante."""
        cs = self.del_grupo(grupo)
        with self.candado:
            for c in cs:
                if c.estado not in ("iniciando", "corriendo", "pausando", "pausada"):
                    raise Rechazo(f"la corrida {c.id} no está en marcha (estado: {c.estado})")
            objetivo = max(self._proxima_pausa_posible(c) for c in cs)
            if en_t_sim_min is not None:
                objetivo = max(objetivo, self.hora_en_punto(en_t_sim_min))
            for c in cs:
                self._pausar_en(c, objetivo)
            ficha = secrets.token_hex(4)
            self._alineando[grupo] = ficha
        threading.Thread(target=self._alinear, args=(grupo, cs, ficha), name=f"alinear-{grupo}", daemon=True).start()
        return {"grupo": grupo, "en_t_sim_min": objetivo, "corridas": [c.resumen() for c in cs]}

    def _alinear(self, grupo: str, cs: list[Corrida], ficha: str, vueltas: int = 5) -> None:
        for _ in range(vueltas):
            while True:
                if self._alineando.get(grupo) != ficha:
                    return                           # otro pedido de pausa del grupo tomó el control
                if any(c.estado not in ("pausando", "pausada") for c in cs):
                    return                           # alguna se reanudó, se detuvo o terminó: no se insiste
                if all(c.estado == "pausada" for c in cs):
                    break
                time.sleep(0.05)
            horas = [c.t_pausa for c in cs]
            if None in horas or max(horas) - min(horas) < 1e-6:
                return
            with self.candado:
                if self._alineando.get(grupo) != ficha:
                    return
                try:
                    for c in cs:
                        self._pausar_en(c, max(horas))
                except Rechazo:
                    return

    def intervenir_grupo(self, grupo: str, entrada: dict, espera_s: float = ESPERA_INTERVENCION_S) -> dict:
        """La misma intervención a todas las corridas del grupo, que tienen que estar en pausa en la misma hora."""
        cs = self.del_grupo(grupo)
        with self.candado:
            for c in cs:
                if c.estado != "pausada":
                    raise Rechazo(f"la corrida {c.id} ({c.motor}) no está en pausa (estado: {c.estado}); "
                                  "pausá el grupo con /api/grupos/<grupo>/pausar")
                if c.reproduccion_de:
                    raise Rechazo(f"la corrida {c.id} es una reproducción: no acepta intervenciones nuevas")
            horas = {c.t_pausa for c in cs}
            if len(horas) != 1:
                detalle = ", ".join(f"{c.motor}: {c.t_pausa:g} min" for c in cs)
                raise Rechazo(f"las corridas del grupo están en pausa en horas distintas ({detalle}); pausalas juntas "
                              "con /api/grupos/<grupo>/pausar")
            enviados = [(c, *self._enviar_intervencion(c, entrada)) for c in cs]
        limite = time.monotonic() + espera_s
        respuestas = []
        for c, ref, desde in enviados:
            aviso = self._esperar_intervencion(c, ref, desde, limite)
            respuestas.append({"id": c.id, "motor": c.motor, "aviso": aviso,
                               **({} if aviso else {"error": "el proceso motor no respondió a la intervención"})})
        if all(r["aviso"] is None for r in respuestas):
            raise Rechazo("ningún proceso motor del grupo respondió a la intervención", 504)
        return {"grupo": grupo, "t_sim_min": horas.pop(), "respuestas": respuestas}

    def detener(self, id_: str) -> Corrida:
        c = self.obtener(id_)
        with c.candado:
            if c.estado not in ACTIVOS:
                raise Rechazo(f"la corrida no está en marcha (estado: {c.estado})")
            self._ordenar(c, {"orden": "detener"})
            c.cambiar_estado("deteniendo")
        return c

    def _enviar_intervencion(self, c: Corrida, entrada: dict) -> tuple[str, int]:
        with c.candado:
            if c.estado != "pausada":
                raise Rechazo(f"solo se interviene con la corrida en pausa (estado: {c.estado})")
            if c.reproduccion_de:
                raise Rechazo("una reproducción aplica solo la bitácora original: no acepta intervenciones nuevas")
            ref = "i-" + secrets.token_hex(6)
            desde = len(c.eventos)
            self._ordenar(c, {"orden": "intervenir", "ref": ref, "entrada": entrada})
        return ref, desde

    @staticmethod
    def _esperar_intervencion(c: Corrida, ref: str, desde: int, limite: float) -> dict | None:
        while True:
            for e in c.eventos[desde:]:
                if e.get("aviso") == "intervencion" and e.get("ref") == ref:
                    return e
            if time.monotonic() >= limite or c.estado in FINALES:
                return None
            time.sleep(0.05)

    def intervenir(self, id_: str, entrada: dict, espera_s: float = ESPERA_INTERVENCION_S) -> dict:
        """Manda una intervención al proceso (con un `ref` propio) y devuelve el aviso `intervencion` con ese `ref`.
        Solo con la corrida en pausa. Espera hasta `espera_s` segundos (504 si no llega)."""
        c = self.obtener(id_)
        ref, desde = self._enviar_intervencion(c, entrada)
        aviso = self._esperar_intervencion(c, ref, desde, time.monotonic() + espera_s)
        if aviso is None:
            raise Rechazo("el proceso motor no respondió a la intervención", 504)
        return aviso

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
                # las pausas que anota una reproducción no esperan órdenes: no cambian el estado
                if c.estado == "pausando" and not a.get("reproduccion"):
                    c.t_pausa = float(a.get("t_sim_min") or 0.0)
                    c.pausa_en = None
                    c.cambiar_estado("pausada", t_sim_min=a.get("t_sim_min"))
            elif tipo == "final":
                c.final = a
            elif tipo == "error" and a.get("fatal"):
                c.error = str(a.get("mensaje"))
            if tipo in AVISOS_CON_ENTRADA:
                c.sumar_a_la_bitacora(a.get("entrada"))
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
