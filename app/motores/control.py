"""Lo que comparten los dos conductores de motor: avisos al servidor, órdenes del servidor, pausa y huella parcial.

Contrato: docs/etapa3/contrato_servidor_motor.md.
- Avisos: una línea JSON por la salida estándar original del proceso. Todo lo demás que imprimen los motores va a proceso.log.
- Órdenes: una línea JSON por la entrada estándar (pausar, reanudar, detener, intervenir).
- La pausa cae en hora simulada en punto: el motor termina la hora en curso y espera. `pausar` puede traer `en_t_sim_min`.
- Intervenciones (F5): las aplica el conductor de cada motor por medio de `Control.aplicar`; Control las valida, las anota
  en la bitácora encadenada con hash (`intervenciones.py`) y responde con el aviso `intervencion` y el mismo `ref`.
- Bitácora: pausas, reanudaciones, detención e intervenciones aceptadas o recortadas, cada una con su hash encadenado desde
  la raíz (la configuración inicial). Se escribe en el acto en `bitacora.jsonl` y viaja en los avisos.
- Reproducción: si `corrida.json` trae `reproduccion`, Control aplica la bitácora original en su hora, sin órdenes.

Las órdenes se consultan SIN bloquear, en cada hora simulada. No hay ningún hilo esperando en la entrada estándar: en
Windows, un hilo bloqueado leyendo esa tubería congela la carga de bibliotecas que consultan la entrada estándar al
iniciarse (las de Fortran que usan scipy y numba), y el motor quedaba colgado en la primera hora (medido el 2026-11-11).
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import intervenciones as iv  # noqa: E402

HUELLA = "t_llegada_parcial.npy"
BITACORA = "bitacora.jsonl"
ESPERA_EN_PAUSA_S = 0.05


class Detenida(Exception):
    """El usuario pidió detener la corrida (se usa donde el motor no ofrece otra forma de cortar su bucle)."""


class CanalOrdenes:
    """Lectura no bloqueante de líneas JSON desde un descriptor (la entrada estándar del proceso)."""

    def __init__(self, fd: int | None):
        self.fd = fd
        self.cerrado = fd is None
        self._resto = b""
        if os.name == "nt" and fd is not None:
            import ctypes
            import msvcrt
            self._kernel32 = ctypes.windll.kernel32
            self._ctypes = ctypes
            try:
                self._handle = msvcrt.get_osfhandle(fd)
            except OSError:
                self.cerrado = True
            else:
                if not self._hay_bytes_windows()[0]:          # no es una tubería (consola, NUL): no hay canal de órdenes
                    self.cerrado = True

    def _hay_bytes_windows(self) -> tuple[bool, int]:
        disponibles = self._ctypes.c_ulong(0)
        ok = self._kernel32.PeekNamedPipe(self._ctypes.c_void_p(self._handle), None, 0, None,
                                          self._ctypes.byref(disponibles), None)
        return bool(ok), int(disponibles.value)

    def _leer_bytes(self) -> bytes:
        """Los bytes que haya en este momento (b"" si no hay). Marca `cerrado` si el otro extremo cerró."""
        if self.cerrado:
            return b""
        try:
            if os.name == "nt":
                ok, n = self._hay_bytes_windows()
                if not ok:
                    self.cerrado = True
                    return b""
                return os.read(self.fd, n) if n else b""
            import select
            listos, _, _ = select.select([self.fd], [], [], 0)
            if not listos:
                return b""
            datos = os.read(self.fd, 65536)
            if not datos:
                self.cerrado = True
            return datos
        except (OSError, ValueError):
            self.cerrado = True
            return b""

    def ordenes(self) -> list[dict]:
        self._resto += self._leer_bytes()
        out = []
        while b"\n" in self._resto:
            linea, self._resto = self._resto.split(b"\n", 1)
            texto = linea.decode("utf-8", errors="replace").strip()
            if not texto:
                continue
            try:
                out.append(json.loads(texto))
            except json.JSONDecodeError:
                out.append({"orden": "_invalida", "texto": texto[:200]})
        return out


class Control:
    """Avisos, órdenes, pausa, intervenciones y bitácora de una corrida.

    El conductor de cada motor pone `aplicar` (ver abajo) y llama a `atender(t_sim_min)` en cada hora simulada en punto.
    El proceso llama a `preparar(corrida)` al leer `corrida.json` y a `cerrar(corrida)` al terminar.

    `aplicar(entrada, t_sim_min) -> dict`: aplica en el motor una intervención ya validada (`intervenciones.validar_entrada`)
    con la corrida en pausa en `t_sim_min`, y devuelve `{"estado": "aceptada"|"recortada"|"rechazada", "t_vigor_min": float,
    "pleno_min": float (opcional), "motivo": str, "datos": dict}`. `datos` se suma a los datos de la entrada en la bitácora
    (longitud aplicada, celdas o enlaces aplicados…). Si devuelve `rechazada` o lanza una excepción, la intervención no
    entra en la bitácora; en los dos casos el motor tiene que quedar como estaba.
    """

    def __init__(self, carpeta: Path, flujo_avisos, fd_ordenes: int | None):
        self.carpeta = Path(carpeta)
        self._avisos = flujo_avisos
        self._canal = CanalOrdenes(fd_ordenes)
        self.aplicar = None                         # lo pone el conductor del motor
        self.detener = False
        self.bitacora: list[dict] = []
        self.raiz: str | None = None
        self.horas_avisadas = 0
        self.listo_avisado = False
        self._t0 = time.perf_counter()
        self._en_pausa_s = 0.0
        self._t = 0.0                               # hora simulada de la última llamada a atender
        self._pausa_en: float | None = None         # pausa pedida: se hace al llegar a esta hora simulada
        self._cola: list[dict] = []                 # órdenes leídas que esperan (detrás de una pausa con hora futura)
        self._reproduccion: dict | None = None
        self._plan: list[dict] = []                 # entradas de la bitácora original que faltan reproducir
        self._sin_aplicar: list[dict] = []          # entradas de la bitácora original cuya hora pasó sin aplicarlas
        self._ruta_bitacora = self.carpeta / BITACORA

    # ------------------------------------------------------------------ avisos
    def aviso(self, tipo: str, **campos) -> None:
        self._avisos.write(json.dumps({"aviso": tipo, **campos}, ensure_ascii=False, default=str) + "\n")
        self._avisos.flush()

    def segundos(self) -> float:
        """Segundos de cómputo desde el inicio, sin contar el tiempo en pausa."""
        return round(time.perf_counter() - self._t0 - self._en_pausa_s, 2)

    def listo(self, t0_utc, grilla: dict) -> None:
        if not self.listo_avisado:
            self.listo_avisado = True
            self.aviso("listo", t0_utc=str(t0_utc), grilla=grilla)

    def hora(self, h: int, t_sim_min: float, ha: float, activas: int, t_llegada_min: np.ndarray, **extra) -> None:
        """Avisa el fin de una hora simulada y deja la huella parcial en disco (escritura atómica)."""
        self.guardar_huella(t_llegada_min)
        self.horas_avisadas += 1
        self.aviso("hora", h=int(h), t_sim_min=round(float(t_sim_min), 3), ha=round(float(ha), 2), activas=int(activas),
                   s_computo=self.segundos(), huella=HUELLA, **extra)

    def guardar_huella(self, t_llegada_min: np.ndarray) -> None:
        tmp = self.carpeta / (HUELLA + ".tmp")
        with open(tmp, "wb") as f:
            np.save(f, np.asarray(t_llegada_min, dtype="float32"))
        os.replace(tmp, self.carpeta / HUELLA)

    # ------------------------------------------------------------------ bitácora y reproducción
    def preparar(self, corrida: dict) -> None:
        """Calcula la raíz de la cadena con la configuración inicial, empieza `bitacora.jsonl` vacía y, si la corrida es una
        reproducción, precarga la bitácora original para aplicarla en su hora."""
        self.raiz = iv.raiz(corrida)
        self._ruta_bitacora.write_text("", encoding="utf-8")
        rep = corrida.get("reproduccion")
        if rep:
            if not isinstance(rep, dict) or not isinstance(rep.get("bitacora"), list):
                raise ValueError("`reproduccion` tiene que ser {de, raiz, bitacora: [...]}")
            self._reproduccion = rep
            self._plan = sorted((dict(e) for e in rep["bitacora"]), key=lambda e: e.get("n", 0))

    def _anotar(self, tipo: str, t_sim_min: float, t_vigor_min: float | None = None, datos: dict | None = None) -> dict:
        """Agrega una entrada encadenada a la bitácora y la escribe en el acto en `bitacora.jsonl`."""
        e = {"n": len(self.bitacora) + 1, "t_sim_min": round(float(t_sim_min), 3),
             "t_vigor_min": round(float(t_sim_min if t_vigor_min is None else t_vigor_min), 3), "tipo": tipo,
             "datos": datos or {}}
        e["hash"] = iv.hash_entrada(self.bitacora[-1]["hash"] if self.bitacora else self.raiz, e)
        self.bitacora.append(e)
        try:
            with open(self._ruta_bitacora, "a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
        except OSError as err:                       # sin disco no se corta la corrida: la bitácora igual viaja en avisos
            self.aviso("error", mensaje=f"no se pudo escribir {BITACORA}: {err}", fatal=False)
        return e

    def cerrar(self, corrida: dict) -> dict | None:
        """Deja la bitácora en `corrida` (con su raíz) y devuelve el informe de la reproducción, si la hubo."""
        corrida["bitacora"] = list(self.bitacora)
        corrida["bitacora_raiz"] = self.raiz
        return self.informe_reproduccion()

    def informe_reproduccion(self) -> dict | None:
        rep = self._reproduccion
        if rep is None:
            return None
        original = rep.get("bitacora") or []
        integra, fallo = iv.verificar_cadena(rep.get("raiz"), original)
        h_orig = [e.get("hash") for e in original]
        h_nueva = [e["hash"] for e in self.bitacora]
        distinta = next((i + 1 for i, (a, b) in enumerate(zip(h_orig, h_nueva)) if a != b), None)
        if distinta is None and len(h_orig) != len(h_nueva):
            distinta = min(len(h_orig), len(h_nueva)) + 1
        return {"de": rep.get("de"), "raiz_original": rep.get("raiz"), "raiz": self.raiz,
                "raiz_igual": rep.get("raiz") == self.raiz, "original_integra": integra, "original_primer_fallo": fallo,
                "n_original": len(original), "n": len(self.bitacora),
                "cadena_igual": integra and rep.get("raiz") == self.raiz and h_orig == h_nueva,
                "primera_distinta": distinta, "sin_aplicar": [e.get("n") for e in self._sin_aplicar + self._plan]}

    def _reproducir(self, t: float) -> None:
        """Aplica, sin pasar por la entrada estándar, las entradas de la bitácora original de esta hora simulada."""
        while self._plan and abs(float(self._plan[0].get("t_sim_min", -1)) - round(t, 3)) < 1e-6:
            e = self._plan.pop(0)
            tipo = e.get("tipo")
            if tipo == "pausa":
                entrada = self._anotar("pausa", t)
                self.aviso("pausado", t_sim_min=round(t, 3), entrada=entrada, reproduccion=True)
            elif tipo == "reanudacion":
                entrada = self._anotar("reanudacion", t)
                self.aviso("reanudado", t_sim_min=round(t, 3), entrada=entrada, reproduccion=True)
            elif tipo == "detencion":
                self.detener = True                  # se anota al final de atender, como una detención pedida
            elif tipo in iv.TIPOS:
                self._intervenir({"tipo": tipo, "datos": e.get("datos")}, f"reproduccion-{e.get('n')}")
            else:
                self.aviso("error", mensaje=f"reproducción: entrada {e.get('n')} de tipo desconocido {tipo!r}", fatal=False)
        # lo que quedó con una hora ya pasada no se va a aplicar nunca: se saca del plan (sale en `sin_aplicar`)
        while self._plan and float(self._plan[0].get("t_sim_min", -1)) < round(t, 3) - 1e-6:
            self._sin_aplicar.append(self._plan.pop(0))

    # ------------------------------------------------------------------ intervenciones
    def _intervenir(self, cruda, ref) -> None:
        """Valida, aplica (con `self.aplicar`) y anota una intervención; avisa `intervencion` con el mismo `ref`."""
        t = self._t

        def rechazar(motivo: str) -> None:
            self.aviso("intervencion", ref=ref, n=None, estado="rechazada", t_vigor_min=None, motivo=motivo, entrada=None)

        try:
            entrada = iv.validar_entrada(cruda)
        except ValueError as e:
            return rechazar(str(e))
        if self.aplicar is None:
            return rechazar("este motor no acepta intervenciones")
        try:
            r = self.aplicar(entrada, t)
        except Exception as e:
            traceback.print_exc()
            return rechazar(f"falló al aplicarla: {type(e).__name__}: {e}")
        estado = (r or {}).get("estado")
        if estado not in iv.ESTADOS:
            return rechazar(f"el motor devolvió un estado inválido: {estado!r}")
        if estado == "rechazada":
            return rechazar(str(r.get("motivo") or "rechazada por el motor"))
        datos = {**entrada["datos"], **(r.get("datos") or {})}
        t_vigor = r.get("t_vigor_min")
        campos = {}
        if r.get("pleno_min") is not None:
            campos["pleno_min"] = round(float(r["pleno_min"]), 3)
            datos["pleno_min"] = campos["pleno_min"]
        try:
            anotada = self._anotar(entrada["tipo"], t, t if t_vigor is None else float(t_vigor), datos)
        except (ValueError, TypeError) as e:          # datos del motor que no se pueden encadenar
            return rechazar(f"el motor devolvió datos inválidos para la bitácora: {e}")
        self.aviso("intervencion", ref=ref, n=anotada["n"], estado=estado, t_vigor_min=anotada["t_vigor_min"],
                   motivo=str(r.get("motivo") or ""), entrada=anotada, **campos)

    # ------------------------------------------------------------------ órdenes
    def _procesar(self, o: dict, en_pausa: bool) -> bool:
        """Aplica una orden y devuelve si la corrida queda en pausa."""
        orden = o.get("orden") if isinstance(o, dict) else None
        if orden == "pausar":
            en = o.get("en_t_sim_min")
            if en is not None and (isinstance(en, bool) or not isinstance(en, (int, float)) or not np.isfinite(en) or en < 0):
                self.aviso("error", mensaje=f"pausar: `en_t_sim_min` inválido: {en!r}", fatal=False)
            elif en is None:
                if not en_pausa:                     # en pausa ya está pausada: no hace nada
                    self._pausa_en = self._t
            elif not en_pausa or float(en) > self._t + 1e-6:
                self._pausa_en = float(en)           # una hora ya pasada pausa en la hora actual
        elif orden == "reanudar":
            if not en_pausa:                         # todavía no pausó: se cancela la pausa pedida
                self._pausa_en = None
                return False
            if self._reproduccion is None:
                entrada = self._anotar("reanudacion", self._t)
            else:                                    # en una reproducción las pausas a mano no entran a la cadena
                entrada = None
            self.aviso("reanudado", t_sim_min=round(self._t, 3), entrada=entrada)
            return False
        elif orden == "detener":
            self.detener = True
        elif orden == "intervenir":
            ref = o.get("ref")
            if not en_pausa:
                self.aviso("intervencion", ref=ref, n=None, estado="rechazada", t_vigor_min=None,
                           motivo="solo se interviene con la corrida en pausa", entrada=None)
            elif self._reproduccion is not None:
                self.aviso("intervencion", ref=ref, n=None, estado="rechazada", t_vigor_min=None,
                           motivo="una reproducción aplica solo la bitácora original", entrada=None)
            else:
                self._intervenir(o.get("entrada"), ref)
        else:
            self.aviso("error", mensaje=f"orden desconocida: {str(o)[:200]}", fatal=False)
        return en_pausa

    def atender(self, t_sim_min: float) -> bool:
        """Se llama en cada hora simulada en punto. Aplica la bitácora a reproducir de esta hora, atiende las órdenes que
        hayan llegado y, si toca pausa, espera acá consultando el canal. Devuelve True si hay que detener la corrida.

        Las órdenes se procesan de a una, en el orden en que llegaron, con el estado de pausa al día: `pausar`,
        `intervenir` y `reanudar` mandadas juntas pausan, intervienen y siguen. Detrás de un `pausar` con `en_t_sim_min`
        futuro, las órdenes siguientes esperan a esa pausa (salvo `detener`, que se atiende en el acto)."""
        self._t = float(t_sim_min)
        if self._plan:
            self._reproducir(self._t)
        self._cola.extend(self._canal.ordenes())
        en_pausa = False
        t_espera = None
        while not self.detener:
            if not en_pausa and self._pausa_en is not None and self._pausa_en <= self._t + 1e-6:
                self._pausa_en = None
                en_pausa = True
                t_espera = time.perf_counter()
                entrada = self._anotar("pausa", self._t) if self._reproduccion is None else None
                self.aviso("pausado", t_sim_min=round(self._t, 3), entrada=entrada)
                continue
            if self._cola:
                if not en_pausa and self._pausa_en is not None:          # pausa con hora futura: lo demás espera
                    if any(isinstance(o, dict) and o.get("orden") == "detener" for o in self._cola):
                        self.detener = True
                    break
                en_pausa = self._procesar(self._cola.pop(0), en_pausa)
                if not en_pausa and t_espera is not None:
                    self._en_pausa_s += time.perf_counter() - t_espera
                    t_espera = None
                continue
            if not en_pausa:
                break
            if self._canal.cerrado:                  # el servidor ya no está: no se queda esperando para siempre
                self.detener = True
                break
            time.sleep(ESPERA_EN_PAUSA_S)
            self._cola.extend(self._canal.ordenes())
        if t_espera is not None:
            self._en_pausa_s += time.perf_counter() - t_espera
        if self.detener:
            entrada = self._anotar("detencion", self._t)
            self.aviso("detenido", t_sim_min=round(self._t, 3), entrada=entrada)
        return self.detener


def memoria_pico_mb() -> float | None:
    """Memoria pico del proceso, en MB (Windows y Linux)."""
    try:
        import psutil
        info = psutil.Process().memory_info()
        if hasattr(info, "peak_wset"):
            return round(info.peak_wset / 2 ** 20, 1)
    except Exception:
        pass
    try:
        import resource
        pico = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(pico / (2 ** 20 if sys.platform == "darwin" else 1024), 1)
    except Exception:
        return None
