"""Repite los siete pares del prerregistro E-E3-1, pero lanzando las corridas por el servidor (fase F2).

    python herramientas/e_e3_1_servidor.py                 todos los escenarios
    python herramientas/e_e3_1_servidor.py aguada_36h      solo uno

Es una comprobación al cierre de la F2 (decisión D-E3-19, punto 23 del pedido de aprobación). No reemplaza a la evaluación
formal de E-E3-1, que se hizo sobre el proceso motor con `herramientas/e_e3_1.py`.

Levanta el servidor en un puerto libre y, por cada par escenario–motor, hace por HTTP:
  1. una corrida sin órdenes;
  2. una corrida con una pausa y una reanudación a mitad de camino;
  3. solo en Las Lagunas 48 h: una corrida que se detiene a mitad de camino.
Compara cada una con la corrida offline del motor. Criterio: 0 celdas distintas; en la corrida detenida, 0 celdas distintas
entre lo que alcanzó a quemar y la misma parte de la corrida offline. Deja la tabla en
resultados/app/E-E3-1-servidor/resultados.json.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "herramientas"))
sys.path.insert(0, str(REPO / "app"))

from e_e3_1 import ESCENARIOS, MOTORES, datos_del_evento, distintas, git, leer, offline      # noqa: E402

SALIDA = REPO / "resultados" / "app" / "E-E3-1-servidor"
FINALES = {"terminada", "detenida", "error", "interrumpida"}
SEGUNDOS_POR_UNIDAD = {"v4.0": 60.0, "v3.1-libre": 1.0, "v3.1-librev2": 1.0}      # el ráster de v4.0 va en minutos; el de v3.1, en segundos


class Servidor:
    def __init__(self, carpeta: Path):
        import uvicorn
        from servidor.app import crear_app
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            puerto = s.getsockname()[1]
        self.base = f"http://127.0.0.1:{puerto}"
        self.app = crear_app(carpeta)
        self.uvicorn = uvicorn.Server(uvicorn.Config(self.app, host="127.0.0.1", port=puerto, log_level="warning"))
        self.hilo = threading.Thread(target=self.uvicorn.run, daemon=True)
        self.hilo.start()
        while not self.uvicorn.started:
            time.sleep(0.05)

    def cerrar(self) -> None:
        self.uvicorn.should_exit = True
        self.hilo.join(60)

    def pedir(self, ruta: str, cuerpo: dict | None = None) -> dict:
        datos = None if cuerpo is None else json.dumps(cuerpo).encode("utf-8")
        pedido = urllib.request.Request(self.base + ruta, data=datos, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(pedido, timeout=120) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{ruta}: {e.code} {e.read().decode('utf-8', 'replace')[:300]}")

    def correr(self, motor: str, definicion: dict, pausar_en_h: int | None = None, detener_en_h: int | None = None) -> dict:
        """Lanza una corrida y la sigue por el canal de avance. Devuelve su detalle final, con la carpeta y las pausas."""
        c = self.pedir("/api/corridas", {"motor": motor, "definicion": definicion, "iniciar": True})["corridas"][0]
        pedida, pausas = False, []
        with urllib.request.urlopen(f"{self.base}/api/corridas/{c['id']}/eventos", timeout=3600) as flujo:
            for linea in flujo:
                linea = linea.decode("utf-8").rstrip("\n")
                if linea == "event: cierre":
                    break
                if not linea.startswith("data: ") or linea == "data: {}":
                    continue
                e = json.loads(linea[6:])
                if e["aviso"] == "hora" and not pedida:
                    if pausar_en_h is not None and e["h"] >= pausar_en_h:
                        pedida = True
                        self.pedir(f"/api/corridas/{c['id']}/pausar", {})
                    elif detener_en_h is not None and e["h"] >= detener_en_h:
                        pedida = True
                        self.pedir(f"/api/corridas/{c['id']}/detener", {})
                elif e["aviso"] == "estado" and e["estado"] == "pausada":
                    pausas.append(e.get("t_sim_min"))
                    self.pedir(f"/api/corridas/{c['id']}/reanudar", {})
        d = self.pedir(f"/api/corridas/{c['id']}")
        if d["estado"] == "error":
            raise RuntimeError(f"la corrida {c['id']} terminó con error: {d['error']}")
        d["carpeta"] = Path(self.app.state.gestor.obtener(c["id"]).carpeta)
        d["pausas"] = pausas
        return d


def hasta(a: np.ndarray, tope: float) -> np.ndarray:
    """La parte de la huella que ardió hasta `tope` (en las unidades del ráster); lo demás, NaN."""
    a = a.astype("float64")
    return np.where(np.isfinite(a) & (a >= 0) & (a <= tope), a, np.nan)


def main() -> int:
    pedidos = sys.argv[1:] or list(ESCENARIOS)
    if SALIDA.exists():
        shutil.rmtree(SALIDA)
    servidor = Servidor(SALIDA / "corridas")
    filas = []
    try:
        for nombre in pedidos:
            e = ESCENARIOS[nombre]
            if not (REPO / e["necesita"]).exists():
                filas.append({"escenario": nombre, "estado": "sin datos"})
                continue
            for motor in e["motores"]:
                raster = MOTORES[motor][2]
                print(f"{nombre} · {motor}: offline…", flush=True)
                ref, _ = offline(SALIDA / "offline" / nombre / motor.replace(".", "_"), motor, e["definicion"])
                print(f"{nombre} · {motor}: por el servidor…", flush=True)
                a = servidor.correr(motor, e["definicion"])
                print(f"{nombre} · {motor}: por el servidor, con pausa…", flush=True)
                b = servidor.correr(motor, e["definicion"], pausar_en_h=e["horas"] // 2)
                fila = {"escenario": nombre, "motor": motor, "estado": "corrido", "horas": e["horas"],
                        "horas_simuladas": a["resultados"]["t_simulado_h"], "ha": a["resultados"]["ha_final"],
                        "celdas_distintas": distintas(leer(a["carpeta"] / "salida" / raster), ref),
                        "celdas_distintas_con_pausa": distintas(leer(b["carpeta"] / "salida" / raster), ref),
                        "pausa_en_min": b["pausas"], "estado_final": [a["estado"], b["estado"]],
                        "s_computo": a["resultados"]["s_computo"], "memoria_pico_mb": a["resultados"]["memoria_pico_mb"]}
                if nombre == "laslagunas_48h":
                    print(f"{nombre} · {motor}: por el servidor, detenida a mitad…", flush=True)
                    c = servidor.correr(motor, e["definicion"], detener_en_h=e["horas"] // 2)
                    t_min = float(c["resultados"]["t_simulado_min"])
                    # se compara hasta la última hora en punto cumplida antes de detener
                    tope = (np.floor(t_min / 60.0) * 3600.0) / SEGUNDOS_POR_UNIDAD[motor]
                    parcial = leer(c["carpeta"] / "salida" / raster)
                    fila |= {"detenida_en_min": t_min, "detenida_estado": c["estado"],
                             "detenida_celdas_quemadas": int(np.isfinite(hasta(parcial, tope)).sum()),
                             "detenida_celdas_distintas": distintas(hasta(parcial, tope), hasta(ref, tope))}
                filas.append(fila)
                print("   " + json.dumps(fila, ensure_ascii=False, default=str), flush=True)
    finally:
        servidor.cerrar()

    cab = git("rev-parse", "HEAD").strip() or None
    sin_registrar = [l for l in git("status", "--porcelain", "--", "app", "herramientas", "src", "escenarios", "congelado.json").splitlines() if l.strip()]
    eventos = sorted({ESCENARIOS[n]["definicion"]["evento"] for n in pedidos if "evento" in ESCENARIOS[n]["definicion"]})
    informe = {"fecha": time.strftime("%Y-%m-%d %H:%M"), "via": "servidor (HTTP)",
               "equipo": {"sistema": platform.platform(), "nucleos": os.cpu_count(), "python": sys.version.split()[0]},
               "cambio_git": cab, "codigo_sin_registrar": sin_registrar,
               "congelado_sha256": json.loads((REPO / "congelado.json").read_text(encoding="utf-8"))["sha256_del_conjunto"],
               "datos_por_evento": [{k: v for k, v in datos_del_evento(ev).items() if k != "archivos"} for ev in eventos],
               "filas": filas}
    (SALIDA / "resultados.json").write_text(json.dumps(informe, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")

    print("\nescenario        motor          h sim  ha         distintas  con pausa  detenida (distintas / quemadas)")
    for f in filas:
        if f["estado"] != "corrido":
            print(f"{f['escenario']:<16} sin datos"); continue
        det = f"{f['detenida_celdas_distintas']} / {f['detenida_celdas_quemadas']}" if "detenida_celdas_distintas" in f else "—"
        print(f"{f['escenario']:<16} {f['motor']:<13} {f['horas_simuladas']:>6}  {f['ha']:>9.1f}  {f['celdas_distintas']:>9}  "
              f"{f['celdas_distintas_con_pausa']:>9}  {det}")
    corridos = [f for f in filas if f["estado"] == "corrido"]
    cumple = bool(corridos) and all(f["celdas_distintas"] == 0 and f["celdas_distintas_con_pausa"] == 0
                                    and f.get("detenida_celdas_distintas", 0) == 0 for f in corridos)
    print("\nCriterio (0 celdas distintas): " + ("SE CUMPLE en lo corrido" if cumple else "NO se cumple"))
    return 0 if cumple else 1


if __name__ == "__main__":
    sys.exit(main())
