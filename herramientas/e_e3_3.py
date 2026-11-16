"""Evaluación del prerregistro E-E3-3: tiempo de cómputo y memoria de cada motor conducido por el simulador.

    python herramientas/e_e3_3.py --evaluador NOMBRE          la medición completa (más la corrida aparte de v4.0)
    python herramientas/e_e3_3.py --evaluador NOMBRE --sin-extra
                                                              sin la corrida "fuera del prerregistro" (unos 10 min menos)
    python herramientas/e_e3_3.py --solo-revisar              comprueba archivos, etiqueta, datos y motores sin correr nada
    python herramientas/e_e3_3.py --humo CARPETA [--humo-horas H]
                                                              prueba de humo de quien escribe: un par corto, una repetición y
                                                              el modo "ambos" de H horas; escribe solo en CARPETA (no es la
                                                              evaluación)

Prerregistro: `docs/etapa3/prerregistros/E-E3-3_rendimiento.md` (etiqueta `prerregistro-E-E3-3`). Escribe deinagutierrez,
evalúa LisandroV2002 (D-E3-30). Diseño fijado en el pedido de la F6, puntos 7 y 8 (aprobados en D-E3-30):

1. Los siete pares escenario–motor de E-E3-1 (`herramientas/e_e3_1.py`, misma definición de cada corrida), solo por el proceso
   motor (`app/motores/proceso.py`), sin corrida offline. **3 repeticiones** por par, una detrás de otra. La primera es **en
   frío**: `NUMBA_CACHE_DIR` apunta a una carpeta nueva y vacía (v3.1 compila con numba, `@njit(cache=True)`); las otras dos
   usan esa misma carpeta, ya con lo compilado (en caliente). v4.0 no usa numba: para v4.0 "frío" solo quiere decir primera.
   Por corrida: `s_computo` y `memoria_pico_mb` del aviso `final`; segundos por hora simulada (= s_computo / horas
   simuladas); reloj de pared desde `Popen` hasta el aviso `listo` (carga de insumos) y hasta el primer aviso `hora` con
   h >= 1; y el RSS máximo del árbol del proceso, muestreado cada 0,25 s.
   Se informa la mediana y el rango (mínimo–máximo) de las 3; la meta se compara con la mediana de las 3 (fijado antes de
   ver resultados). El tiempo hasta `listo` y hasta la primera hora se informa aparte en frío y en caliente.
2. Modo "ambos" en Las Lagunas 2024, 48 h (la definición de E-E3-1), dos formas:
   (i) por el servidor: `crear_app` con uvicorn en un hilo (como `test/app/test_servidor.py`), `POST /api/corridas` con
       motor "ambos" (v4.0 y v3.1 librev2, D-E3-01); los tiempos de pared van desde el POST y los toma el propio servidor
       al recibir cada aviso;
   (ii) dos `proceso.py` lanzados a la vez desde este programa.
   Un hilo con psutil suma cada 0,25 s el RSS de los árboles de procesos de los dos motores: se guardan el máximo y la serie.
   Se informa también la suma de las memorias pico de cada proceso (aviso `final`), que es una cota superior.
3. Metas del prerregistro: v3.1 <= 0,5 s por hora simulada; modo "ambos" dentro de 16 GB (con el máximo muestreado);
   v4.0 <= 3 s por hora con unas 30.000 ha: **no evaluable con el diseño** (ningún escenario de E-E3-1 llega a esa
   superficie con v4.0). Se informa la relación s/h contra ha de lo corrido y, **aparte, rotulada "fuera del
   prerregistro"**, una corrida de Las Chacras octubre 2023 con v4.0 variante libre, `parar_en_cicatriz: off`, ignición alt4,
   hipótesis 4, 141 h (la de `docs/v4.0/31` §7.2, 29.319 ha). `--sin-extra` la omite.

La memoria pico por proceso del aviso `final` es `peak_wset` en Windows y `ru_maxrss` en Linux: **no son la misma métrica**
y no se comparan entre sistemas. El RSS muestreado con psutil sí se mide igual en los dos (en Windows, psutil informa como RSS
el conjunto de trabajo), con la resolución del muestreo.

Salidas: `docs/etapa3/prerregistros/E-E3-3_resultados.json` y `E-E3-3_resultado.md`; lo intermedio en
`resultados/app/E-E3-3/`. Código de salida: 0 medición completa, 1 incompleta, 2 error.

Este proceso no importa ningún motor: cada corrida va en su propio `proceso.py`. Importa el servidor (`app/servidor`), que
tampoco carga motores, y de `herramientas/e_e3_1.py` solo la tabla de escenarios.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import socket
import statistics
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "herramientas"))
sys.path.insert(0, str(REPO / "app"))

from e_e3_1 import ESCENARIOS, MOTORES  # noqa: E402  (solo la tabla de los siete pares; no importa motores)

DOCS = REPO / "docs" / "etapa3" / "prerregistros"
PRERREGISTRO = DOCS / "E-E3-3_rendimiento.md"
SALIDA_JSON = DOCS / "E-E3-3_resultados.json"
SALIDA_MD = DOCS / "E-E3-3_resultado.md"
TRABAJO = REPO / "resultados" / "app" / "E-E3-3"
PROCESO = REPO / "app" / "motores" / "proceso.py"
ETIQUETA = "prerregistro-E-E3-3"
REPETICIONES = 3
MUESTREO_S = 0.25
TOPE_CORRIDA_S = 4 * 3600
FINALES = {"terminada", "detenida", "error", "interrumpida"}

META_V31_S_H = 0.5
META_AMBOS_MB = 16 * 1024
META_V40_S_H, META_V40_HA = 3.0, 30000.0
ESCENARIO_AMBOS = "laslagunas_48h"
MOTORES_AMBOS = ("v4.0", "v3.1-librev2")                 # los del servidor (`servidor.corridas.AMBOS`, D-E3-01)
EXTRA = {"rotulo": "fuera del prerregistro", "motor": "v4.0",
         "definicion": {"evento": "SL-2023-CHACRASOCT", "hipotesis": 4, "ignicion": "alt4", "horas": 141,
                        "variante": "libre", "parar_en_cicatriz": "off", "validar": False, "figuras": False},
         "referencia": "docs/v4.0/31 §7.2: v4.0 libre, alt4, 06 UTC, sin parada, 141 h, 29.319 ha; 2,7 s por hora en el "
                       "antecedente del prerregistro (corrida offline con figuras)"}
METRICA_PICO = "peak_wset" if sys.platform == "win32" else "ru_maxrss"


# ------------------------------------------------------------------ utilidades
def entorno(numba: Path | None = None) -> dict:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    for k in ("PYTHONPATH", "INCENDIOS_SL_INPUT", "INCENDIOS_SL_RESULTADOS", "NUMBA_CACHE_DIR"):
        env.pop(k, None)
    if numba is not None:
        env["NUMBA_CACHE_DIR"] = str(numba)
    return env


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout


def verificar_congelado() -> dict:
    p = subprocess.run([sys.executable, str(REPO / "herramientas" / "congelado.py"), "verificar"], cwd=REPO, env=entorno(),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return {"intacto": p.returncode == 0, "salida": (p.stdout + p.stderr).strip()[-2000:]}


def sha_congelado() -> str | None:
    try:
        return json.loads((REPO / "congelado.json").read_text(encoding="utf-8")).get("sha256_del_conjunto")
    except (OSError, json.JSONDecodeError):
        return None


def dentro_de(ruta: Path, raiz: Path) -> bool:
    try:
        Path(ruta).resolve().relative_to(Path(raiz).resolve())
        return True
    except ValueError:
        return False


def archivos_en(carpeta: Path) -> int:
    return sum(1 for q in carpeta.rglob("*") if q.is_file()) if carpeta.exists() else 0


def resumen_de(valores: list) -> dict | None:
    v = [float(x) for x in valores if x is not None]
    if not v:
        return None
    return {"mediana": round(statistics.median(v), 3), "min": round(min(v), 3), "max": round(max(v), 3), "n": len(v)}


def prerregistro_desde_la_etiqueta() -> dict:
    """Líneas del prerregistro que cambiaron desde la etiqueta (solo deberían ser los nombres de quién escribe y evalúa)."""
    rel = PRERREGISTRO.relative_to(REPO).as_posix()
    if not git("rev-list", "-n", "1", ETIQUETA).strip():
        return {"etiqueta": ETIQUETA, "existe": False}
    cambios = [l for l in git("diff", "--unified=0", ETIQUETA, "--", rel).splitlines()
               if l[:1] in "+-" and not l.startswith(("+++", "---"))]
    return {"etiqueta": ETIQUETA, "existe": True, "cambio": git("rev-list", "-n", "1", ETIQUETA).strip(),
            "lineas_cambiadas": cambios}


# ------------------------------------------------------------------ ficha de la máquina
def ficha_maquina(nota: str | None = None) -> dict:
    """Sistema, procesador, memoria, disco, versiones y carga de fondo al momento de medir."""
    import psutil
    procesador, avx512 = platform.processor(), None
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        texto = cpuinfo.read_text(encoding="utf-8", errors="replace")
        nombres = [l.split(":", 1)[1].strip() for l in texto.splitlines() if l.lower().startswith("model name")]
        procesador = nombres[0] if nombres else procesador
    elif sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                procesador = str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
    try:
        from numpy._core._multiarray_umath import __cpu_features__ as rasgos
        avx512 = bool(rasgos.get("AVX512F", False))
    except ImportError:
        pass
    versiones = {"python": sys.version.split()[0]}
    from importlib import metadata
    for paquete in ("numpy", "numba", "rasterio", "psutil", "uvicorn", "fastapi"):
        try:
            versiones[paquete] = metadata.version(paquete)
        except metadata.PackageNotFoundError:
            versiones[paquete] = None
    frec = None
    try:
        f = psutil.cpu_freq()
        frec = round(f.max or f.current) if f else None
    except Exception:
        pass
    disco = shutil.disk_usage(REPO)
    bateria = None
    try:
        b = psutil.sensors_battery()
        bateria = None if b is None else {"porcentaje": round(b.percent), "enchufada": b.power_plugged}
    except Exception:
        pass
    return {"sistema": platform.platform(), "procesador": procesador, "nucleos_logicos": os.cpu_count(),
            "nucleos_fisicos": psutil.cpu_count(logical=False), "frecuencia_max_mhz": frec, "avx512": avx512,
            "ram_total_gb": round(psutil.virtual_memory().total / 2 ** 30, 1),
            "disco_del_repositorio": {"total_gb": round(disco.total / 2 ** 30, 1), "libre_gb": round(disco.free / 2 ** 30, 1)},
            "bateria": bateria, "versiones": versiones, "metrica_memoria_pico": METRICA_PICO, "nota_de_quien_evalua": nota}


def carga_de_fondo() -> dict:
    """Uso del procesador (1 s) y memoria disponible en este momento: se toma al empezar y al terminar."""
    import psutil
    try:
        carga = [round(x, 2) for x in psutil.getloadavg()]
    except Exception:
        carga = None
    return {"momento": time.strftime("%Y-%m-%d %H:%M:%S"), "cpu_porcentaje_1s": psutil.cpu_percent(interval=1.0),
            "carga_media_1_5_15": carga, "ram_disponible_gb": round(psutil.virtual_memory().available / 2 ** 30, 1),
            "procesos": len(psutil.pids())}


# ------------------------------------------------------------------ muestreo de memoria
def rss_del_arbol_mb(pid: int) -> float | None:
    """RSS del proceso y de todos sus descendientes (en Windows el ejecutable de un entorno virtual puede ser un lanzador
    que corre Python como hijo: por eso el árbol)."""
    import psutil
    try:
        raiz = psutil.Process(pid)
        procs = [raiz] + raiz.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None
    total, alguno = 0, False
    for p in procs:
        try:
            total += p.memory_info().rss
            alguno = True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return round(total / 2 ** 20, 1) if alguno else None


class Muestreo:
    """Cada 0,25 s suma el RSS de los árboles de `raices()` ({nombre: pid}). Guarda el máximo del total, el máximo de cada
    árbol y, si se pide, la serie [t_s, total_mb, {nombre: mb}]."""

    def __init__(self, raices, con_serie: bool = False):
        self.raices, self.con_serie = raices, con_serie
        self.t0 = time.perf_counter()
        self.max_total, self.max_por, self.serie, self.n = 0.0, {}, [], 0
        self._fin = threading.Event()
        self._hilo = threading.Thread(target=self._correr, name="muestreo-rss", daemon=True)

    def iniciar(self) -> "Muestreo":
        self._hilo.start()
        return self

    def _tomar(self) -> None:
        try:
            raices = dict(self.raices())
        except Exception:
            return
        por = {}
        for nombre, pid in raices.items():
            mb = rss_del_arbol_mb(pid)
            if mb is not None:
                por[nombre] = mb
                self.max_por[nombre] = max(self.max_por.get(nombre, 0.0), mb)
        if not por:
            return
        total = round(sum(por.values()), 1)
        self.max_total = max(self.max_total, total)
        self.n += 1
        if self.con_serie:
            self.serie.append([round(time.perf_counter() - self.t0, 2), total, por])

    def _correr(self) -> None:
        self._tomar()
        while not self._fin.wait(MUESTREO_S):
            self._tomar()

    def parar(self) -> dict:
        self._fin.set()
        self._hilo.join(5)
        d = {"intervalo_s": MUESTREO_S, "muestras": self.n, "rss_max_total_mb": round(self.max_total, 1) if self.n else None,
             "rss_max_por_proceso_mb": self.max_por}
        if self.con_serie:
            d["serie"] = {"columnas": ["t_s", "total_mb", "por_proceso_mb"], "filas": self.serie}
        return d


# ------------------------------------------------------------------ una corrida por el proceso motor
class Corrida:
    """Lanza `proceso.py` con `corrida.json` y lee sus avisos en un hilo, anotando el reloj de pared desde `Popen`."""

    def __init__(self, carpeta: Path, motor: str, definicion: dict, numba: Path | None, rotulo: str):
        if carpeta.exists():
            shutil.rmtree(carpeta)
        carpeta.mkdir(parents=True)
        self.carpeta, self.motor, self.rotulo = carpeta, motor, rotulo
        (carpeta / "corrida.json").write_text(json.dumps(
            {"formato": "incendios_sl.corrida/1.0", "motor": motor, "base": {"definicion": dict(definicion)},
             "programa": {"version": "herramientas/e_e3_3.py", "congelado_sha256": sha_congelado()}},
            ensure_ascii=False, indent=1), encoding="utf-8")
        self.t_listo = self.t_primera_hora = self.t_final = None
        self.final, self.error, self.no_fatales = None, None, []
        self._ultima = -1
        self._err = open(carpeta / "stderr.txt", "w", encoding="utf-8", errors="replace")
        self.t0 = time.perf_counter()
        self.p = subprocess.Popen([sys.executable, str(PROCESO), "--corrida", str(carpeta)], cwd=REPO, env=entorno(numba),
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._err, text=True,
                                  encoding="utf-8", errors="replace", bufsize=1)
        self._guardian = threading.Timer(TOPE_CORRIDA_S, self.p.kill)
        self._guardian.daemon = True
        self._guardian.start()
        self._hilo = threading.Thread(target=self._leer, name=f"avisos-{rotulo}", daemon=True)
        self._hilo.start()

    def _leer(self) -> None:
        for linea in self.p.stdout:
            t = time.perf_counter() - self.t0
            try:
                a = json.loads(linea)
            except json.JSONDecodeError:
                continue
            tipo = a.get("aviso")
            if tipo == "listo" and self.t_listo is None:
                self.t_listo = t
            elif tipo == "hora":
                h = int(a.get("h", 0))
                if h >= 1 and self.t_primera_hora is None:
                    self.t_primera_hora = t
                if h >= self._ultima + 12:
                    self._ultima = h
                    print(f"   {self.rotulo}: hora {h}, {a.get('ha', 0):.0f} ha", flush=True)
            elif tipo == "final":
                self.final, self.t_final = a, t
            elif tipo == "error":
                if a.get("fatal"):
                    self.error = a.get("mensaje")
                else:
                    self.no_fatales.append(a.get("mensaje"))

    def esperar(self) -> None:
        self._hilo.join()
        self.p.wait()
        self._guardian.cancel()
        self.s_pared = time.perf_counter() - self.t0
        try:
            self.p.stdin.close()
        except OSError:
            pass
        self._err.close()
        if self.p.returncode != 0 or self.final is None:
            raise RuntimeError(f"{self.rotulo}: el proceso motor falló ({self.error or f'código {self.p.returncode}'}); "
                               f"ver {self.carpeta / 'proceso.log'}")


def fila_de_final(final: dict, t_listo, t_primera, s_pared) -> dict:
    t_h = float(final["t_sim_min"]) / 60.0
    return {"s_pared_hasta_listo": None if t_listo is None else round(t_listo, 2),
            "s_pared_hasta_primera_hora": None if t_primera is None else round(t_primera, 2),
            "s_pared_total": None if s_pared is None else round(s_pared, 2),
            "s_computo": final["s_computo"], "t_sim_h": round(t_h, 3),
            "s_por_hora_simulada": round(final["s_computo"] / max(t_h, 1e-9), 4),
            "memoria_pico_mb": final.get("memoria_pico_mb"), "metrica_memoria_pico": METRICA_PICO,
            "ha": final.get("ha"), "motivo_fin": final.get("motivo"), "completa": final.get("completa")}


def correr_una(carpeta: Path, motor: str, definicion: dict, numba: Path | None, rotulo: str, con_serie: bool = False) -> dict:
    c = Corrida(carpeta, motor, definicion, numba, rotulo)
    m = Muestreo(lambda: {motor: c.p.pid}, con_serie=con_serie).iniciar()
    try:
        c.esperar()
    finally:
        memoria = m.parar()
    return {**fila_de_final(c.final, c.t_listo, c.t_primera_hora, c.s_pared), "rss_max_muestreado_mb": memoria["rss_max_total_mb"],
            "muestreo": memoria if con_serie else {k: v for k, v in memoria.items() if k != "serie"},
            "errores_no_fatales": c.no_fatales}


# ------------------------------------------------------------------ 1. los siete pares
def definicion_de(escenario: str, horas: int | None = None) -> dict:
    d = dict(ESCENARIOS[escenario]["definicion"])
    if horas is not None:
        d["horas"] = int(horas)
    return d


def medir_par(trabajo: Path, escenario: str, motor: str, repeticiones: int, horas: int | None) -> dict:
    """Las repeticiones de un par. La primera con una carpeta de caché de numba nueva y vacía; las siguientes, con la misma."""
    base = trabajo / "pares" / f"{escenario}_{motor.replace('.', '_').replace('-', '_')}"
    numba = base / "numba_cache"
    if numba.exists():
        shutil.rmtree(numba)
    numba.mkdir(parents=True)
    definicion = definicion_de(escenario, horas)
    reps = []
    for i in range(1, repeticiones + 1):
        estado = "frío" if i == 1 else "caliente"
        antes = archivos_en(numba)
        print(f"{escenario} · {motor}: repetición {i} de {repeticiones} ({estado})…", flush=True)
        r = correr_una(base / f"rep{i}", motor, definicion, numba, f"{escenario} · {motor} · {i}")
        r |= {"repeticion": i, "numba": estado, "archivos_numba_antes": antes, "archivos_numba_despues": archivos_en(numba)}
        reps.append(r)
        print(f"   {r['s_por_hora_simulada']:.3f} s/h · {r['memoria_pico_mb']} MB pico · listo {r['s_pared_hasta_listo']} s · "
              f"primera hora {r['s_pared_hasta_primera_hora']} s · {r['ha']:.0f} ha", flush=True)
    calientes = [r for r in reps if r["numba"] == "caliente"]
    res = {k: resumen_de([r[k] for r in reps]) for k in ("s_por_hora_simulada", "s_computo", "memoria_pico_mb",
                                                        "rss_max_muestreado_mb", "s_pared_hasta_listo",
                                                        "s_pared_hasta_primera_hora", "s_pared_total")}
    frio = {k: reps[0][k] for k in ("s_por_hora_simulada", "s_pared_hasta_listo", "s_pared_hasta_primera_hora")}
    caliente = {k: resumen_de([r[k] for r in calientes]) for k in ("s_por_hora_simulada", "s_pared_hasta_listo",
                                                                    "s_pared_hasta_primera_hora")} if calientes else None
    return {"escenario": escenario, "motor": motor, "estado": "corrido", "horas": definicion.get("horas") or ESCENARIOS[escenario]["horas"],
            "definicion": definicion, "repeticiones": reps, "resumen": res, "frio": frio, "caliente": caliente,
            "ha": reps[0]["ha"], "ha_iguales_en_las_repeticiones": len({r["ha"] for r in reps}) == 1,
            "numba_cache": numba.relative_to(REPO).as_posix() if dentro_de(numba, REPO) else str(numba)}


# ------------------------------------------------------------------ 2. modo "ambos"
class Servidor:
    def __init__(self, carpeta: Path):
        import uvicorn
        from servidor.app import crear_app
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            puerto = s.getsockname()[1]
        self.base = f"http://127.0.0.1:{puerto}"
        self.app = crear_app(carpeta / "corridas", carpeta_trabajos=carpeta / "trabajos_datos")
        self.uvicorn = uvicorn.Server(uvicorn.Config(self.app, host="127.0.0.1", port=puerto, log_level="warning"))
        self.hilo = threading.Thread(target=self.uvicorn.run, daemon=True)
        self.hilo.start()
        limite = time.monotonic() + 60
        while not self.uvicorn.started:
            if time.monotonic() > limite:
                raise RuntimeError("el servidor no arrancó en 60 s")
            time.sleep(0.05)

    def cerrar(self) -> None:
        self.uvicorn.should_exit = True
        self.hilo.join(120)

    def pedir(self, ruta: str, cuerpo: dict | None = None) -> dict:
        datos = None if cuerpo is None else json.dumps(cuerpo).encode("utf-8")
        pedido = urllib.request.Request(self.base + ruta, data=datos, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(pedido, timeout=120) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{ruta}: {e.code} {e.read().decode('utf-8', 'replace')[:300]}")


def ambos_por_el_servidor(carpeta: Path, definicion: dict, numba: Path | None) -> dict:
    """POST de un grupo "ambos". Los instantes de cada aviso los anota el propio servidor al recibirlo (se envuelve
    `Gestor._atender_aviso` de esta instancia; el código del servidor no cambia)."""
    if carpeta.exists():
        shutil.rmtree(carpeta)
    carpeta.mkdir(parents=True)
    previo = os.environ.get("NUMBA_CACHE_DIR")
    if numba is not None:
        os.environ["NUMBA_CACHE_DIR"] = str(numba)           # el servidor lanza los motores con su propio entorno
    srv = Servidor(carpeta)
    try:
        gestor = srv.app.state.gestor
        marcas: dict[str, dict] = {}
        original = gestor._atender_aviso

        def con_reloj(c, a):
            t = time.perf_counter()
            m = marcas.setdefault(c.id, {})
            tipo = a.get("aviso")
            if tipo == "listo":
                m.setdefault("listo", t)
            elif tipo == "hora" and int(a.get("h", 0)) >= 1:
                m.setdefault("primera_hora", t)
            elif tipo == "final":
                m.setdefault("final", t)
            original(c, a)

        gestor._atender_aviso = con_reloj
        t0 = time.perf_counter()
        r = srv.pedir("/api/corridas", {"motor": "ambos", "definicion": definicion, "iniciar": True})
        s_post = time.perf_counter() - t0
        corridas = [gestor.obtener(c["id"]) for c in r["corridas"]]
        muestreo = Muestreo(lambda: {c.motor: c.proceso.pid for c in corridas if c.proceso is not None}, con_serie=True).iniciar()
        limite, avisado = time.monotonic() + TOPE_CORRIDA_S, -1
        try:
            while not all(c.estado in FINALES for c in corridas):
                if time.monotonic() > limite:
                    raise RuntimeError("el modo ambos por el servidor pasó el tope de tiempo")
                h = min(int((c.ultima_hora or {}).get("h", 0)) for c in corridas)
                if h >= avisado + 12:
                    avisado = h
                    print(f"   ambos por el servidor: hora {h}", flush=True)
                time.sleep(0.05)
        finally:
            memoria = muestreo.parar()
        s_pared = time.perf_counter() - t0
        por_motor = {}
        for c in corridas:
            if c.estado != "terminada" or not c.final:
                raise RuntimeError(f"{c.motor} por el servidor terminó en {c.estado}: {c.error}")
            m = marcas.get(c.id, {})
            rel = {k: (v - t0) for k, v in m.items()}
            por_motor[c.motor] = {"id": c.id, **fila_de_final(c.final, rel.get("listo"), rel.get("primera_hora"), rel.get("final"))}
    finally:
        srv.cerrar()
        if numba is not None:
            if previo is None:
                os.environ.pop("NUMBA_CACHE_DIR", None)
            else:
                os.environ["NUMBA_CACHE_DIR"] = previo
    return {"forma": "servidor", "descripcion": "POST /api/corridas {motor: ambos}; tiempos desde el POST, tomados por el servidor "
            "al recibir cada aviso", "s_post": round(s_post, 3), "s_pared_total": round(s_pared, 2), "por_motor": por_motor,
            "memoria": memoria}


def ambos_dos_procesos(carpeta: Path, definicion: dict, numba: Path | None) -> dict:
    if carpeta.exists():
        shutil.rmtree(carpeta)
    carpeta.mkdir(parents=True)
    t0 = time.perf_counter()
    cs = [Corrida(carpeta / m.replace(".", "_").replace("-", "_"), m, definicion, numba, f"ambos (dos procesos) · {m}")
          for m in MOTORES_AMBOS]
    muestreo = Muestreo(lambda: {c.motor: c.p.pid for c in cs}, con_serie=True).iniciar()
    try:
        for c in cs:
            c.esperar()
    except BaseException:
        for c in cs:                               # que no quede un motor corriendo solo
            if c.p.poll() is None:
                c.p.kill()
        raise
    finally:
        memoria = muestreo.parar()
    return {"forma": "dos_procesos", "descripcion": "dos proceso.py lanzados a la vez; tiempos desde cada Popen",
            "s_pared_total": round(time.perf_counter() - t0, 2),
            "por_motor": {c.motor: fila_de_final(c.final, c.t_listo, c.t_primera_hora, c.s_pared) for c in cs},
            "memoria": memoria}


def completar_ambos(r: dict) -> dict:
    picos = [f.get("memoria_pico_mb") for f in r["por_motor"].values()]
    r["suma_de_picos_individuales_mb"] = round(sum(picos), 1) if all(p is not None for p in picos) else None
    r["rss_max_total_mb"] = r["memoria"]["rss_max_total_mb"]
    r["cumple_16_gb"] = None if r["rss_max_total_mb"] is None else bool(r["rss_max_total_mb"] <= META_AMBOS_MB)
    return r


# ------------------------------------------------------------------ criterio
def veredicto(pares: list[dict], esperados: int, ambos: list[dict], extra: dict | None) -> dict:
    corridos = [p for p in pares if p.get("estado") == "corrido"]
    v31 = [p for p in corridos if p["motor"].startswith("v3.1")]
    v40 = [p for p in corridos if p["motor"] == "v4.0"]
    esperados_v31 = sum(1 for e in ESCENARIOS.values() for m in e["motores"] if m.startswith("v3.1"))
    por_par = {f"{p['escenario']} · {p['motor']}": p["resumen"]["s_por_hora_simulada"]["mediana"] for p in v31}
    if not v31:
        c31 = None
    elif any(x > META_V31_S_H for x in por_par.values()):
        c31 = False
    else:
        c31 = True if len(v31) == esperados_v31 else None
    ok_ambos = [a for a in ambos if "error" not in a]
    if any(a.get("cumple_16_gb") is False for a in ok_ambos):
        cab = False
    elif len(ok_ambos) == 2 and all(a.get("cumple_16_gb") for a in ok_ambos):
        cab = True
    else:
        cab = None
    max_ha_v40 = max((p["ha"] for p in v40), default=None)
    metas = {
        "v3.1": {"meta": f"<= {META_V31_S_H} s por hora simulada (mediana de las {REPETICIONES} repeticiones de cada par)",
                 "cumple": c31, "mediana_por_par": por_par},
        "v4.0_30000_ha": {"meta": f"<= {META_V40_S_H} s por hora simulada con unas 30.000 ha",
                          "cumple": "no evaluable con el diseño",
                          "motivo": f"ningún escenario de E-E3-1 llega a esa superficie con v4.0 (máximo medido: "
                                    f"{max_ha_v40} ha)" if max_ha_v40 is not None else "no se corrió v4.0",
                          "s_h_contra_ha": [{"escenario": p["escenario"], "ha": p["ha"],
                                             "s_por_hora_mediana": p["resumen"]["s_por_hora_simulada"]["mediana"]} for p in v40],
                          "fuera_del_prerregistro": None if not extra or "error" in extra else
                          {"ha": extra["ha"], "s_por_hora_simulada": extra["s_por_hora_simulada"],
                           "debajo_de_3_s_h": bool(extra["s_por_hora_simulada"] <= META_V40_S_H)}},
        "ambos": {"meta": "dentro de 16 GB (máximo del RSS sumado de los dos árboles, muestreado cada 0,25 s)",
                  "cumple": cab, "por_forma": {a["forma"]: a.get("rss_max_total_mb") for a in ambos}},
    }
    completa = len(corridos) == esperados and all(len(p["repeticiones"]) >= 1 for p in corridos) and len(ok_ambos) == 2
    return {"medicion": "completa" if completa else "incompleta", "pares_corridos": len(corridos), "pares_esperados": esperados,
            "metas": metas}


# ------------------------------------------------------------------ informe
def _n(x, d=2):
    if x is None:
        return "—"
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _r(res: dict | None, d=2) -> str:
    if not res:
        return "—"
    if res["n"] == 1:
        return _n(res["mediana"], d)
    return f"{_n(res['mediana'], d)} ({_n(res['min'], d)}–{_n(res['max'], d)})"


def _si(v) -> str:
    return {True: "**se cumple**", False: "**no se cumple**", None: "sin evaluar (faltan corridas)"}.get(v, f"**{v}**")


NOTAS = [
    f"Memoria pico por proceso (aviso `final`): en Windows es `peak_wset` (conjunto de trabajo pico) y en Linux `ru_maxrss` "
    f"(RSS máximo). **No son la misma métrica** y no se comparan entre sistemas; en E-E3-1, Linux dio 15–30 % más que Windows en "
    f"las mismas corridas. Esta máquina usa `{METRICA_PICO}`.",
    "RSS muestreado: psutil cada 0,25 s, sumando el proceso y sus descendientes. Es la misma medida en los dos sistemas (en "
    "Windows psutil informa el conjunto de trabajo como RSS), pero puede perder un pico más corto que el intervalo: por eso se "
    "informa además la suma de los picos individuales, que es una cota superior del total del modo \"ambos\".",
    "Segundos de cómputo (`s_computo`): los cuenta el proceso motor desde que crea su control, sin el tiempo en pausa; no "
    "incluye el arranque de Python ni las importaciones. Sí incluye la compilación de numba de v3.1 en la corrida fría. Por eso "
    "se informa también el reloj de pared desde `Popen` (o desde el POST) hasta `listo` y hasta la primera hora.",
    "Frío y caliente: la primera repetición de cada par usa una carpeta de caché de numba nueva y vacía (`NUMBA_CACHE_DIR`); "
    "las otras dos, la misma carpeta ya llena. No se vacía la caché de archivos del sistema operativo: la primera corrida de "
    "cada par puede leer los insumos del disco y las demás de la memoria. v4.0 no usa numba.",
    "La meta de v3.1 se compara con la mediana de las 3 repeticiones de cada par, y la de \"ambos\" con el máximo muestreado "
    "(fijado por quien escribe antes de ver resultados).",
    "Modo \"ambos\" por el servidor: los instantes de `listo`, primera hora y `final` los anota el servidor al recibir el aviso "
    "(se envuelve el método del gestor en esta instancia, sin cambiar el código); van desde el POST, que también incluye crear "
    "las dos carpetas. Con dos procesos lanzados a la vez, cada tiempo va desde su `Popen`.",
    "Las corridas son las de E-E3-1 (`herramientas/e_e3_1.py`: Las Lagunas 2023 aguada 36 h en v4.0; Las Lagunas 2024 48 h y "
    "Las Chacras octubre 2023 72 h con los tres motores), con la configuración por defecto del simulador (v4.0 variante "
    "barreras sin parada, D-E3-01).",
    "La meta de v4.0 con unas 30.000 ha **no se puede evaluar con el diseño del prerregistro**: ninguno de esos escenarios llega "
    "a esa superficie con v4.0. La corrida de Las Chacras v4.0 libre de 141 h se agrega aparte y va rotulada **fuera del "
    "prerregistro** (D-E3-30, punto 8): no cambia el diseño ni el criterio.",
    "Es una medición en una sola computadora: el resultado vale para esta máquina con la carga de fondo anotada. En la "
    "integración continua E-E3-3 es solo informativo (máquinas compartidas, con ruido).",
]


def markdown(inf: dict) -> str:
    v = inf["veredicto"]
    m = v["metas"]
    eq = inf["maquina"]
    L = ["# Resultado del prerregistro E-E3-3 — Tiempo de cómputo y memoria", ""]
    if inf.get("humo"):
        L += ["> **Prueba de humo de quien escribe: NO es la evaluación del prerregistro.**", ""]
    pre = inf["prerregistro"]
    L += [f"Medición generada por `herramientas/e_e3_3.py`. Prerregistro: `E-E3-3_rendimiento.md` (etiqueta `{ETIQUETA}`"
          + (f", líneas cambiadas desde la etiqueta: {len(pre.get('lineas_cambiadas') or [])}" if pre.get("existe") else
             ", **no se encontró la etiqueta**") + "). Escribe deinagutierrez; evalúa LisandroV2002 (D-E3-30).", "",
          "## Veredicto", "", f"**Medición: {v['medicion']}.** Pares hechos: {v['pares_corridos']} de {v['pares_esperados']}.", "",
          "| Meta | Valor | Resultado |", "|---|---|---|",
          f"| v3.1 | ≤ {_n(META_V31_S_H, 1)} s por hora simulada (mediana de cada par) | {_si(m['v3.1']['cumple'])} |",
          f"| v4.0 con unas 30.000 ha | ≤ {_n(META_V40_S_H, 0)} s por hora simulada | **no evaluable con el diseño**: "
          f"{m['v4.0_30000_ha']['motivo']} |",
          f"| Modo \"ambos\" | dentro de 16 GB | {_si(m['ambos']['cumple'])} |", "",
          "## Quién y con qué", "", "| | |", "|---|---|", f"| Fecha | {inf['fecha']} |", f"| Evaluó | {inf['evaluador']} |",
          f"| Código | cambio de git `{(inf['git']['cambio'] or '—')[:12]}` (rama `{inf['git']['rama'] or '—'}`); código sin "
          f"registrar: {len(inf['git']['codigo_sin_registrar'])} archivo(s) |",
          f"| Motores congelados | sha256 del conjunto `{inf['congelado']['sha256_del_conjunto']}`; intactos antes: "
          f"{'sí' if (inf['congelado'].get('antes') or {}).get('intacto') else 'NO'}; después: "
          f"{'sí' if (inf['congelado'].get('despues') or {}).get('intacto') else 'NO o sin verificar'} |",
          f"| Alcance | {inf['alcance']} |", "", "## Ficha de la máquina", "", "| | |", "|---|---|",
          f"| Sistema | {eq['sistema']} |", f"| Procesador | {eq['procesador']} ({eq['nucleos_fisicos']} núcleos, "
          f"{eq['nucleos_logicos']} hilos; {eq['frecuencia_max_mhz'] or '—'} MHz; AVX-512: "
          f"{ {True: 'sí', False: 'no', None: '—'}[eq['avx512']] }) |",
          f"| Memoria | {_n(eq['ram_total_gb'], 1)} GB |",
          f"| Disco del repositorio | {_n(eq['disco_del_repositorio']['total_gb'], 0)} GB, "
          f"{_n(eq['disco_del_repositorio']['libre_gb'], 0)} GB libres |",
          f"| Batería | {'sin batería' if not eq['bateria'] else ('enchufada' if eq['bateria']['enchufada'] else '**a batería**')} |",
          f"| Versiones | " + ", ".join(f"{k} {v_}" for k, v_ in eq["versiones"].items()) + " |",
          f"| Memoria pico por proceso | `{eq['metrica_memoria_pico']}` |"]
    for k in ("al_empezar", "al_terminar"):
        c = inf["carga_de_fondo"].get(k)
        if c:
            L.append(f"| Carga de fondo {k.replace('_', ' ')} | CPU {_n(c['cpu_porcentaje_1s'], 0)} %, carga media "
                     f"{c['carga_media_1_5_15'] or '—'}, {_n(c['ram_disponible_gb'], 1)} GB disponibles, {c['procesos']} procesos |")
    if eq.get("nota_de_quien_evalua"):
        L.append(f"| Nota de quien evalúa | {eq['nota_de_quien_evalua']} |")
    n_rep = inf["repeticiones"]
    L += ["", f"## Por par escenario–motor ({n_rep} {'repetición' if n_rep == 1 else 'repeticiones: mediana y rango'})", "",
          "| Escenario | Motor | h | ha | s/h simulada | s/h en frío | s cómputo | MB pico | RSS máx. muestreado (MB) | "
          "Hasta `listo`: frío / caliente (s) | Hasta la 1.ª hora: frío / caliente (s) |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for p in inf["pares"]:
        if p.get("estado") != "corrido":
            L.append(f"| {p['escenario']} | {p.get('motor', '—')} | — | — | — | — | — | — | — | — | {p.get('estado')}: "
                     f"{p.get('error', '')} |")
            continue
        r, f, c = p["resumen"], p["frio"], p["caliente"] or {}
        L.append(f"| {p['escenario']} | {p['motor']} | {p['horas']} | {_n(p['ha'], 0)}"
                 f"{'' if p['ha_iguales_en_las_repeticiones'] else ' (¡distintas!)'} | {_r(r['s_por_hora_simulada'], 3)} | "
                 f"{_n(f['s_por_hora_simulada'], 3)} | {_r(r['s_computo'], 1)} | {_r(r['memoria_pico_mb'], 0)} | "
                 f"{_r(r['rss_max_muestreado_mb'], 0)} | {_n(f['s_pared_hasta_listo'], 1)} / "
                 f"{_r(c.get('s_pared_hasta_listo'), 1)} | {_n(f['s_pared_hasta_primera_hora'], 1)} / "
                 f"{_r(c.get('s_pared_hasta_primera_hora'), 1)} |")
    L += ["", f"## Modo \"ambos\" (Las Lagunas 2024, {inf.get('ambos_horas', 48)} h; v4.0 y v3.1 librev2)", "",
          "| Forma | Motor | s/h simulada | s cómputo | MB pico (`final`) | RSS máx. del árbol (MB) | Hasta `listo` (s) | "
          "Hasta la 1.ª hora (s) | Fin (s) |", "|---|---|---|---|---|---|---|---|---|"]
    for a in inf["ambos"]:
        if "error" in a:
            L.append(f"| {a['forma']} | — | — | — | — | — | — | — | error: {a['error']} |")
            continue
        for mot, f in a["por_motor"].items():
            L.append(f"| {a['forma']} | {mot} | {_n(f['s_por_hora_simulada'], 3)} | {_n(f['s_computo'], 1)} | "
                     f"{_n(f['memoria_pico_mb'], 0)} | {_n(a['memoria']['rss_max_por_proceso_mb'].get(mot), 0)} | "
                     f"{_n(f['s_pared_hasta_listo'], 1)} | {_n(f['s_pared_hasta_primera_hora'], 1)} | {_n(f['s_pared_total'], 1)} |")
    L += ["", "| Forma | RSS máx. total muestreado (MB) | Suma de picos individuales (MB, cota superior) | Muestras | Dentro de 16 GB |",
          "|---|---|---|---|---|"]
    for a in inf["ambos"]:
        if "error" not in a:
            dentro = {True: "sí", False: "NO", None: "—"}[a["cumple_16_gb"]]
            L.append(f"| {a['forma']} | {_n(a['rss_max_total_mb'], 0)} | {_n(a['suma_de_picos_individuales_mb'], 0)} | "
                     f"{a['memoria']['muestras']} | {dentro} |")
    L += ["", "La serie del RSS (cada 0,25 s) está en el JSON, en `ambos[].memoria.serie`.", "",
          "## v4.0: segundos por hora contra superficie", "", "| Escenario | ha | s/h simulada (mediana) |", "|---|---|---|"]
    for x in m["v4.0_30000_ha"]["s_h_contra_ha"]:
        L.append(f"| {x['escenario']} | {_n(x['ha'], 0)} | {_n(x['s_por_hora_mediana'], 3)} |")
    ex = inf.get("extra")
    L += ["", "## Fuera del prerregistro: Las Chacras octubre 2023, v4.0 libre, 141 h", ""]
    if ex is None:
        L += ["No se corrió (`--sin-extra` o prueba de humo)."]
    elif "error" in ex:
        L += [f"Falló: {ex['error']}"]
    else:
        L += ["> **Fuera del prerregistro.** Se agrega porque la meta de v4.0 con unas 30.000 ha no se puede evaluar con el "
              "diseño (D-E3-30, punto 8). Una sola corrida, en caliente.", "",
              f"Definición: `{json.dumps(EXTRA['definicion'], ensure_ascii=False)}`. Referencia: {EXTRA['referencia']}.", "",
              "| ha al final | Horas simuladas | s cómputo | s/h simulada | MB pico | RSS máx. muestreado (MB) | Hasta `listo` (s) | "
              "Hasta la 1.ª hora (s) | Motivo de fin |", "|---|---|---|---|---|---|---|---|---|",
              f"| {_n(ex['ha'], 0)} | {_n(ex['t_sim_h'], 1)} | {_n(ex['s_computo'], 1)} | {_n(ex['s_por_hora_simulada'], 3)} | "
              f"{_n(ex['memoria_pico_mb'], 0)} | {_n(ex['rss_max_muestreado_mb'], 0)} | {_n(ex['s_pared_hasta_listo'], 1)} | "
              f"{_n(ex['s_pared_hasta_primera_hora'], 1)} | {ex['motivo_fin']} |"]
    L += ["", "## Lo que hay que saber para leerlo", ""] + [f"- {n}" for n in inf["notas"]] + [""]
    if inf.get("errores"):
        L += ["## Errores", ""] + [f"- {e}" for e in inf["errores"]] + [""]
    L += ["## Cómo repetirlo", "", "```", "python herramientas/e_e3_3.py --evaluador NOMBRE", "```", ""]
    return "\n".join(L)


def informe_base(evaluador: str, alcance: str, humo: bool, nota: str | None, repeticiones: int) -> dict:
    return {"prerregistro": "E-E3-3", "humo": humo, "fecha": time.strftime("%Y-%m-%d %H:%M"), "evaluador": evaluador,
            "escribe": "deinagutierrez", "alcance": alcance, "repeticiones": repeticiones, "maquina": ficha_maquina(nota),
            "carga_de_fondo": {},
            "git": {"cambio": git("rev-parse", "HEAD").strip() or None, "rama": git("branch", "--show-current").strip() or None,
                    "codigo_sin_registrar": [l for l in git("status", "--porcelain", "--", "app", "herramientas", "src",
                                                                "escenarios", "congelado.json").splitlines() if l.strip()]},
            "prerregistro_etiqueta": None, "congelado": {"sha256_del_conjunto": sha_congelado()},
            "metas": {"v3.1_s_por_hora": META_V31_S_H, "v4.0_s_por_hora": META_V40_S_H, "v4.0_ha": META_V40_HA,
                      "ambos_mb": META_AMBOS_MB},
            "muestreo_s": MUESTREO_S, "pares": [], "ambos": [], "extra": None, "notas": list(NOTAS), "errores": []}


# ------------------------------------------------------------------ revisión previa
def revisar() -> bool:
    ok = True

    def linea(bien: bool, texto: str) -> None:
        nonlocal ok
        ok &= bool(bien)
        print(f"  [{'ok' if bien else 'FALTA'}] {texto}", flush=True)

    print("Prerregistro:")
    linea(PRERREGISTRO.exists(), PRERREGISTRO.relative_to(REPO).as_posix())
    pre = prerregistro_desde_la_etiqueta()
    linea(pre["existe"], f"etiqueta {ETIQUETA}")
    if pre["existe"]:
        print(f"  (informativo) líneas cambiadas desde la etiqueta: {len(pre['lineas_cambiadas'])} (solo deberían ser los nombres)")
        for l in pre["lineas_cambiadas"]:
            print(f"      {l[:150]}")
    print("Datos de los escenarios de E-E3-1:")
    for nombre, e in ESCENARIOS.items():
        linea((REPO / e["necesita"]).exists(), f"{nombre} ({', '.join(e['motores'])}): {e['necesita']}")
    print("Corrida fuera del prerregistro (Las Chacras v4.0 libre, 141 h):")
    try:
        f = yaml.safe_load((REPO / "escenarios" / "v4.0" / "eventos" / "SL-2023-CHACRASOCT.yaml").read_text(encoding="utf-8"))
        d = EXTRA["definicion"]
        inicio = f["inicio"]["hora_utc_hipotesis"][d["hipotesis"]]
        n_alt = int(d["ignicion"].removeprefix("alt"))
        alternativas = f.get("ignicion_alternativas") or []
        linea(n_alt < len(alternativas), f"la ficha de v4.0 tiene la ignición {d['ignicion']}"
              + (f": {alternativas[n_alt]['puntos'][0].get('nombre')}" if n_alt < len(alternativas) else ""))
        import datetime as dt
        t0 = dt.datetime.fromisoformat(inicio.replace("Z", "+00:00"))
        fin = dt.datetime.fromisoformat(f["meteorologia"]["fin_utc"].replace("Z", "+00:00"))
        linea(t0 + dt.timedelta(hours=d["horas"]) <= fin, f"hipótesis {d['hipotesis']} = {inicio}; {d['horas']} h llegan a "
              f"{(t0 + dt.timedelta(hours=d['horas'])).isoformat()} y la meteorología termina {f['meteorologia']['fin_utc']}")
    except Exception as e:
        linea(False, f"ficha de Las Chacras en v4.0: {type(e).__name__}: {e}")
    print("Programas y bibliotecas:")
    linea(PROCESO.exists(), "app/motores/proceso.py")
    for mod in ("psutil", "uvicorn"):
        try:
            __import__(mod)
            linea(True, f"import {mod}")
        except ImportError as e:
            linea(False, f"import {mod}: {e}")
    try:
        from servidor.corridas import AMBOS
        linea(tuple(AMBOS) == MOTORES_AMBOS, f"el modo ambos del servidor es {AMBOS} (este guion espera {MOTORES_AMBOS})")
        from servidor.app import crear_app  # noqa: F401
        linea(True, "el servidor se importa (servidor.app.crear_app)")
    except Exception as e:
        linea(False, f"servidor: {type(e).__name__}: {e}")
    linea(set(MOTORES) >= set(MOTORES_AMBOS), "los motores del modo ambos están en la tabla de E-E3-1")
    print("Motores (importación en subprocesos separados):")
    for version, mod in (("v3.1", "incendios_sl.simulation.motor"), ("v4.0", "simulador.corrida")):
        env = entorno()
        env["PYTHONPATH"] = str(REPO / "src" / version / "src")
        p = subprocess.run([sys.executable, "-c", f"import {mod}"], cwd=REPO, env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        linea(p.returncode == 0, f"{version}: import {mod}" + ("" if p.returncode == 0 else f" — {p.stderr.strip()[-300:]}"))
    c = verificar_congelado()
    linea(c["intacto"], "congelado intacto (herramientas/congelado.py verificar)" + ("" if c["intacto"] else f"\n{c['salida']}"))
    print("Máquina (informativo):")
    eq = ficha_maquina()
    print(f"  {eq['sistema']} · {eq['procesador']} · {eq['nucleos_fisicos']} núcleos / {eq['nucleos_logicos']} hilos · "
          f"{eq['ram_total_gb']} GB · memoria pico por proceso: {eq['metrica_memoria_pico']}")
    n_pares = sum(len(e["motores"]) for e in ESCENARIOS.values())
    print(f"  corridas: {n_pares} pares × {REPETICIONES} repeticiones + 2 modos \"ambos\" de 48 h + 1 corrida aparte de 141 h")
    print(f"  salidas: {SALIDA_JSON.relative_to(REPO).as_posix()} y {SALIDA_MD.relative_to(REPO).as_posix()}"
          + (" (existen: se reemplazan)" if SALIDA_JSON.exists() else ""))
    print("\nRevisión: " + ("todo listo" if ok else "hay faltantes"), flush=True)
    return ok


# ------------------------------------------------------------------ principal
def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluación del prerregistro E-E3-3 (tiempo de cómputo y memoria)")
    ap.add_argument("--evaluador", help="quién evalúa (obligatorio salvo con --solo-revisar o --humo)")
    ap.add_argument("--solo-revisar", action="store_true", help="comprueba archivos, etiqueta, datos y motores sin correr nada")
    ap.add_argument("--sin-extra", action="store_true", help="omite la corrida fuera del prerregistro (Las Chacras v4.0, 141 h)")
    ap.add_argument("--nota-maquina", help="lo que quien evalúa quiera anotar de la máquina (tipo de disco, otros programas abiertos)")
    ap.add_argument("--humo", metavar="CARPETA", help="prueba de humo de quien escribe: todo en CARPETA")
    ap.add_argument("--humo-horas", type=int, default=2, help="horas del par y del modo ambos en la prueba de humo (2)")
    a = ap.parse_args()
    if a.solo_revisar:
        return 0 if revisar() else 1
    if not a.evaluador and not a.humo:
        ap.error("--evaluador NOMBRE es obligatorio")

    if a.humo:
        base = Path(a.humo).resolve()
        if dentro_de(base, DOCS):
            ap.error("--humo no puede escribir en docs/etapa3/prerregistros")
        trabajo, salida_json, salida_md = base / "trabajo", base / "E-E3-3_resultados.json", base / "E-E3-3_resultado.md"
        pares = [(ESCENARIO_AMBOS, "v3.1-librev2")]
        repeticiones, horas, con_extra = 1, int(a.humo_horas), False
        alcance = f"prueba de humo: {ESCENARIO_AMBOS} · v3.1-librev2 {horas} h, 1 repetición; ambos {horas} h (las dos formas)"
        evaluador = a.evaluador or "prueba de humo (quien escribe)"
    else:
        trabajo, salida_json, salida_md = TRABAJO, SALIDA_JSON, SALIDA_MD
        pares = [(n, m) for n, e in ESCENARIOS.items() for m in e["motores"]]
        repeticiones, horas, con_extra = REPETICIONES, None, not a.sin_extra
        alcance = (f"{len(pares)} pares × {repeticiones} repeticiones; modo ambos 48 h por el servidor y con dos procesos"
                   + ("; más la corrida fuera del prerregistro" if con_extra else "; sin la corrida fuera del prerregistro"))
        evaluador = a.evaluador

    inf = informe_base(evaluador, alcance, bool(a.humo), a.nota_maquina, repeticiones)
    inf["prerregistro"] = prerregistro_desde_la_etiqueta()
    if not a.humo and not inf["prerregistro"]["existe"]:
        print(f"no se encontró la etiqueta {ETIQUETA} (ver --solo-revisar)", flush=True)
        return 2
    inf["congelado"]["antes"] = verificar_congelado()
    if not inf["congelado"]["antes"]["intacto"]:
        print("el congelado no está intacto antes de empezar:\n" + inf["congelado"]["antes"]["salida"], flush=True)
        return 2
    if trabajo.exists():
        shutil.rmtree(trabajo)
    trabajo.mkdir(parents=True)
    inf["carga_de_fondo"]["al_empezar"] = carga_de_fondo()
    codigo = 0
    try:
        # 1. los siete pares
        for escenario, motor in pares:
            e = ESCENARIOS[escenario]
            if not (REPO / e["necesita"]).exists():
                print(f"{escenario}: sin datos en este clon ({e['necesita']})", flush=True)
                inf["pares"].append({"escenario": escenario, "motor": motor, "estado": "sin datos", "error": e["necesita"]})
                continue
            try:
                inf["pares"].append(medir_par(trabajo, escenario, motor, repeticiones, horas))
            except Exception as err:
                traceback.print_exc()
                inf["pares"].append({"escenario": escenario, "motor": motor, "estado": "error", "error": f"{type(err).__name__}: {err}"})
                inf["errores"].append(f"{escenario} · {motor}: {type(err).__name__}: {err}")
                codigo = 2
        # 2. modo ambos (en caliente: la caché de numba del par Las Lagunas · v3.1 librev2, si se corrió)
        numba = trabajo / "pares" / f"{ESCENARIO_AMBOS}_v3_1_librev2" / "numba_cache"
        if not numba.exists():
            numba = trabajo / "ambos" / "numba_cache"
            numba.mkdir(parents=True, exist_ok=True)
        definicion = definicion_de(ESCENARIO_AMBOS, horas)
        inf["ambos_horas"] = definicion["horas"]
        for forma, fn in (("servidor", ambos_por_el_servidor), ("dos_procesos", ambos_dos_procesos)):
            print(f"modo ambos ({forma}), {definicion['horas']} h…", flush=True)
            try:
                r = completar_ambos(fn(trabajo / "ambos" / forma, definicion, numba))
                r["numba"] = "caliente" if archivos_en(numba) else "frío"
                inf["ambos"].append(r)
                print(f"   RSS máx. total {r['rss_max_total_mb']} MB · suma de picos {r['suma_de_picos_individuales_mb']} MB", flush=True)
            except Exception as err:
                traceback.print_exc()
                inf["ambos"].append({"forma": forma, "error": f"{type(err).__name__}: {err}"})
                inf["errores"].append(f"ambos ({forma}): {type(err).__name__}: {err}")
                codigo = 2
        # 3. fuera del prerregistro
        if con_extra:
            print("fuera del prerregistro: Las Chacras octubre 2023, v4.0 libre, 141 h…", flush=True)
            try:
                inf["extra"] = {"rotulo": EXTRA["rotulo"], "motor": EXTRA["motor"], "definicion": EXTRA["definicion"],
                                "referencia": EXTRA["referencia"],
                                **correr_una(trabajo / "fuera_del_prerregistro", EXTRA["motor"], EXTRA["definicion"], None,
                                             "fuera del prerregistro · v4.0 libre 141 h", con_serie=True)}
            except Exception as err:
                traceback.print_exc()
                inf["extra"] = {"rotulo": EXTRA["rotulo"], "error": f"{type(err).__name__}: {err}"}
                inf["errores"].append(f"fuera del prerregistro: {type(err).__name__}: {err}")
    except BaseException as err:                      # también Ctrl+C: se deja constancia de lo hecho
        traceback.print_exc()
        inf["errores"].append(f"{type(err).__name__}: {err}")
        codigo = 2
    finally:
        inf["carga_de_fondo"]["al_terminar"] = carga_de_fondo()
        inf["congelado"]["despues"] = verificar_congelado()
        if "incendios_sl" in sys.modules or "simulador" in sys.modules:   # no debería pasar: este proceso no carga motores
            inf["errores"].append("el proceso principal cargó un motor")
    inf["veredicto"] = veredicto(inf["pares"], len(pares), inf["ambos"], inf["extra"])
    if not inf["congelado"]["despues"]["intacto"]:
        inf["errores"].append("el congelado cambió durante la medición")
        codigo = 2
    salida_json.parent.mkdir(parents=True, exist_ok=True)
    salida_json.write_text(json.dumps(inf, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    salida_md.write_text(markdown(inf), encoding="utf-8")
    v = inf["veredicto"]
    print(f"\nMedición: {v['medicion']}")
    for k, mt in v["metas"].items():
        print(f"  {k}: {mt['cumple']}")
    print(f"Resultados: {salida_json} y {salida_md}", flush=True)
    if codigo:
        return codigo
    return 0 if v["medicion"] == "completa" else 1


if __name__ == "__main__":
    sys.exit(main())
