"""Motor simulado: cumple el contrato servidor–motor con un fuego de mentira (un círculo que crece).

    python app/motores/proceso_simulado.py --corrida resultados/app/<id>

No simula nada: no hay viento, combustible ni relieve. Sirve para probar el servidor y la interfaz en segundos, sin cargar
datos ni motores. Recibe las mismas órdenes y manda los mismos avisos que `proceso.py` (contrato §3).

`corrida.json`:

    {"motor": "simulado",
     "configuracion": {"ignicion": [{"lon": -65.55, "lat": -32.64}], "t_inicio_utc": "2026-01-01T12:00:00Z", "horas": 12},
     "simulado": {"s_por_hora": 0.05, "fallar_en_h": null, "lado": 200}}

`s_por_hora`: segundos reales que tarda cada hora simulada. `fallar_en_h`: si se indica, el proceso se cae en esa hora sin
avisar, para probar que el servidor lo detecta. `lado`: tamaño de la grilla, en celdas de 30 m.

Intervenciones (F5, contrato 1.5), de juguete: un cortafuego vuelve incombustibles las celdas que toca su trazo (las que el
fuego todavía no alcanzó: el resto se recorta) y el fuego ya no llega a las celdas que quedan separadas del foco por los
cortafuegos; el ancho y el suelo mineral no cambian nada. El viento manual se acepta y no tiene efecto. Los cortafuegos de
`configuracion.cortafuegos` se aplican igual, antes de la hora 0. La bitácora y la reproducción son las de `control.py`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import intervenciones  # noqa: E402

CELDAS_POR_HORA = 3.0
RES = 30.0
CENTRO_5345 = (3538140.0, 6392850.0)          # centro del dominio Las Lagunas–Potrerillos, por si no se da un punto


class FuegoDeJuguete:
    """El círculo que crece, con cortafuegos: las celdas del trazo no queman y el fuego no pasa del otro lado."""

    def __init__(self, llegada_min: np.ndarray, grilla: dict, foco: tuple[int, int]):
        self.base = llegada_min
        self.llegada = llegada_min.copy()
        self.grilla = grilla
        self.foco = foco
        self.bloqueadas = np.zeros(llegada_min.shape, dtype=bool)

    def _celdas(self, xy: list) -> tuple[list[tuple[int, int, float]], float]:
        """Celdas (fila, columna, metros del trazo en ella) que toca la polilínea, muestreada cada 1/8 de celda."""
        g = self.grilla
        paso = g["res"] / 8.0
        tramos: list[tuple[int, int, float]] = []
        for (x0, y0), (x1, y1) in zip(xy, xy[1:]):
            largo = float(np.hypot(x1 - x0, y1 - y0))
            n = max(1, int(np.ceil(largo / paso)))
            s = (np.arange(n) + 0.5) / n                # punto medio de cada pedacito
            cols = np.floor((x0 + s * (x1 - x0) - g["xmin"]) / g["res"]).astype(int)
            fils = np.floor((g["ymax"] - (y0 + s * (y1 - y0))) / g["res"]).astype(int)
            tramos.extend(zip(fils.tolist(), cols.tolist(), [largo / n] * n))
        return tramos, paso

    def cortafuego(self, datos: dict, t: float) -> dict:
        tramos, _ = self._celdas(datos["xy_5345"])
        filas, cols = self.grilla["filas"], self.grilla["cols"]
        quemada = np.isfinite(self.llegada) & (self.llegada <= t)
        dentro = [(f, c, m) for f, c, m in tramos if 0 <= f < filas and 0 <= c < cols]
        if not dentro:
            return {"estado": "rechazada", "motivo": "el trazo cae fuera de la grilla", "t_vigor_min": t, "datos": {}}
        quedan = [(f, c, m) for f, c, m in dentro if not quemada[f, c]]
        if not quedan:
            return {"estado": "rechazada", "motivo": "el trazo cae entero sobre celdas ya quemadas", "t_vigor_min": t,
                    "datos": {}}
        celdas = sorted({(f, c) for f, c, _ in quedan})
        recortadas = len({(f, c) for f, c, _ in dentro}) - len(celdas)
        afuera = len(dentro) != len(tramos)
        for f, c in celdas:
            self.bloqueadas[f, c] = True
        from scipy import ndimage
        etiquetas, _ = ndimage.label(~self.bloqueadas)           # 4-vecinos: una línea en diagonal también corta
        alcanzable = etiquetas == etiquetas[self.foco]
        nueva = np.where(alcanzable, self.base, np.nan).astype("float32")
        self.llegada = np.where(quemada, self.llegada, nueva).astype("float32")      # lo ya quemado no cambia
        indices = [f * cols + c for f, c in celdas]
        recortado = recortadas > 0 or afuera
        motivo = []
        if recortadas:
            motivo.append(f"se quitaron {recortadas} celdas ya quemadas")
        if afuera:
            motivo.append("parte del trazo cae fuera de la grilla")
        return {"estado": "recortada" if recortado else "aceptada", "t_vigor_min": t, "motivo": "; ".join(motivo),
                "datos": {"longitud_aplicada_m": round(sum(m for _, _, m in quedan), 2), "celdas": len(celdas),
                          "celdas_recortadas": recortadas, "celdas_sha256": intervenciones.sha256_indices(indices)}}


def main() -> int:
    ap = argparse.ArgumentParser(description="Motor simulado para probar el servidor")
    ap.add_argument("--corrida", required=True)
    carpeta = Path(ap.parse_args().corrida).resolve()
    ruta_json = carpeta / "corrida.json"

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from control import Control
    avisos = os.fdopen(os.dup(1), "w", encoding="utf-8", newline="\n")
    try:
        ordenes = os.dup(0)
    except OSError:
        ordenes = None
    control = Control(carpeta, avisos, ordenes)

    try:
        corrida = json.loads(ruta_json.read_text(encoding="utf-8"))
        cfg = corrida.get("configuracion") or {}
        sim = corrida.get("simulado") or {}
        horas = int(cfg.get("horas") or 12)
        lado = int(sim.get("lado") or 200)
        s_por_hora = float(sim.get("s_por_hora", 0.05))
        fallar_en_h = sim.get("fallar_en_h")
        x, y = CENTRO_5345
        puntos = cfg.get("ignicion") or []
        if puntos:
            from pyproj import Transformer
            x, y = Transformer.from_crs("EPSG:4326", "EPSG:5345", always_xy=True).transform(float(puntos[0]["lon"]), float(puntos[0]["lat"]))
        xmin = round((x - lado * RES / 2) / RES) * RES
        ymax = round((y + lado * RES / 2) / RES) * RES
        grilla = {"crs": "EPSG:5345", "xmin": xmin, "ymax": ymax, "res": RES, "filas": lado, "cols": lado}
        ff, cc = np.mgrid[0:lado, 0:lado]
        distancia = np.hypot(ff - lado / 2, cc - lado / 2)
        llegada_min = (distancia / CELDAS_POR_HORA * 60.0).astype("float32")

        intervenciones.revisar_t_inicio(cfg.get("t_inicio_utc"))
        trazos = intervenciones.validar_cortafuegos(cfg["cortafuegos"]) if cfg.get("cortafuegos") else []
        if trazos:
            cfg["cortafuegos"] = trazos
        control.preparar(corrida)
        fuego = FuegoDeJuguete(llegada_min, grilla, (lado // 2, lado // 2))
        iniciales = []
        for d in trazos:                          # antes de iniciar: lo mismo que aplicarlo a t = 0
            r = fuego.cortafuego(d, 0.0)
            iniciales.append({"estado": r["estado"], "motivo": r["motivo"], **r["datos"]})
        llegada_min = fuego.llegada
        control.aplicar = lambda entrada, t: (fuego.cortafuego(entrada["datos"], t) if entrada["tipo"] == "cortafuego"
                                              else {"estado": "aceptada", "t_vigor_min": t, "datos": {"efecto": "ninguno"},
                                                    "motivo": "el motor simulado registra el viento sin efecto"})

        control.listo(cfg.get("t_inicio_utc") or "2026-01-01T12:00:00+00:00", grilla)
        detenida = False
        h = 0
        while True:
            llegada_min = fuego.llegada
            huella = np.where(llegada_min <= h * 60.0, llegada_min, np.nan).astype("float32")
            n = int(np.count_nonzero(np.isfinite(huella)))
            activas = int(np.count_nonzero(np.isfinite(huella) & (llegada_min > (h - 1) * 60.0)))
            control.hora(h, h * 60.0, n * RES * RES / 1e4, activas, huella)
            if fallar_en_h is not None and h >= int(fallar_en_h):
                avisos.flush()
                os._exit(3)                      # caída sin aviso, a propósito
            if h >= horas:
                break
            if control.atender(h * 60.0):
                detenida = True
                break
            time.sleep(s_por_hora)
            h += 1
    except Exception as e:
        control.aviso("error", mensaje=f"{type(e).__name__}: {e}", fatal=True)
        return 1

    ha = n * RES * RES / 1e4
    res = {"motivo_fin": "detenida" if detenida else "horizonte",
           "motivo_fin_texto": "Detenida por el usuario." if detenida else "Se cumplieron las horas pedidas (motor simulado).",
           "ha_final": round(ha, 2), "km2_final": round(ha / 100.0, 4), "t_simulado_min": h * 60.0, "t_simulado_h": float(h),
           "s_computo": control.segundos(), "memoria_pico_mb": None, "completa": not detenida, "salida": None, "archivos": [],
           "horas_avisadas": control.horas_avisadas}
    if iniciales:
        res["cortafuegos_iniciales"] = iniciales
    reproduccion = control.cerrar(corrida)
    if reproduccion is not None:
        res["reproduccion"] = reproduccion
    corrida["resultados"] = res
    tmp = ruta_json.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(corrida, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, ruta_json)
    control.aviso("final", motivo=res["motivo_fin"], texto=res["motivo_fin_texto"], ha=res["ha_final"], t_sim_min=res["t_simulado_min"],
                  s_computo=res["s_computo"], memoria_pico_mb=None, completa=res["completa"], salida=None)
    return 0


if __name__ == "__main__":
    codigo = main()
    try:
        sys.stdout.flush()
    except Exception:
        pass
    os._exit(codigo)
