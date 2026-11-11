"""Lo que comparten los dos conductores de motor: avisos al servidor, órdenes del servidor, pausa y huella parcial.

Contrato: docs/etapa3/contrato_servidor_motor.md.
- Avisos: una línea JSON por la salida estándar original del proceso. Todo lo demás que imprimen los motores va a proceso.log.
- Órdenes: una línea JSON por la entrada estándar (pausar, reanudar, detener, intervenir).
- La pausa cae en hora simulada en punto: el motor termina la hora en curso y espera.

Las órdenes se consultan SIN bloquear, en cada hora simulada. No hay ningún hilo esperando en la entrada estándar: en
Windows, un hilo bloqueado leyendo esa tubería congela la carga de bibliotecas que consultan la entrada estándar al
iniciarse (las de Fortran que usan scipy y numba), y el motor quedaba colgado en la primera hora (medido el 2026-11-11).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np

HUELLA = "t_llegada_parcial.npy"
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
    def __init__(self, carpeta: Path, flujo_avisos, fd_ordenes: int | None):
        self.carpeta = Path(carpeta)
        self._avisos = flujo_avisos
        self._canal = CanalOrdenes(fd_ordenes)
        self._pedir_pausa = False
        self.detener = False
        self.bitacora: list[dict] = []
        self.horas_avisadas = 0
        self.listo_avisado = False
        self._t0 = time.perf_counter()
        self._en_pausa_s = 0.0

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

    # ------------------------------------------------------------------ órdenes
    def _anotar(self, tipo: str, t_sim_min: float) -> None:
        self.bitacora.append({"n": len(self.bitacora) + 1, "t_sim_min": round(float(t_sim_min), 3), "tipo": tipo})

    def _procesar(self, o: dict, en_pausa: bool) -> str | None:
        """Aplica una orden. Devuelve "reanudar" o "detener" cuando corresponde salir de la pausa."""
        orden = o.get("orden")
        if orden == "pausar":
            self._pedir_pausa = True
        elif orden == "reanudar":
            self._pedir_pausa = False
            return "reanudar"
        elif orden == "detener":
            self.detener = True
            return "detener"
        elif orden == "intervenir":
            motivo = "las intervenciones llegan con la fase F5" if en_pausa else "solo se interviene con la corrida en pausa"
            self.aviso("intervencion", n=None, estado="rechazada", t_vigor_min=None, motivo=motivo)
        else:
            self.aviso("error", mensaje=f"orden desconocida: {str(o)[:200]}", fatal=False)
        return None

    def atender(self, t_sim_min: float) -> bool:
        """Se llama en cada hora simulada en punto. Atiende las órdenes que hayan llegado y, si se pidió pausa, espera
        acá consultando el canal. Devuelve True si hay que detener la corrida."""
        for o in self._canal.ordenes():
            self._procesar(o, False)
        if self._pedir_pausa and not self.detener:
            t_espera = time.perf_counter()
            self._anotar("pausa", t_sim_min)
            self.aviso("pausado", t_sim_min=round(float(t_sim_min), 3))
            salida = None
            while salida is None:
                for o in self._canal.ordenes():
                    salida = self._procesar(o, True) or salida
                    if salida:
                        break
                if salida is None:
                    if self._canal.cerrado:            # el servidor ya no está: no se queda esperando para siempre
                        self.detener = True
                        salida = "detener"
                    else:
                        time.sleep(ESPERA_EN_PAUSA_S)
            self._en_pausa_s += time.perf_counter() - t_espera
            if salida == "reanudar":
                self._anotar("reanudacion", t_sim_min)
        if self.detener:
            self._anotar("detencion", t_sim_min)
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
