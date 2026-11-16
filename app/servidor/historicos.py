"""Modo histórico (F6, D-E3-30 puntos 10 a 12): los 15 eventos con ficha, su ignición recomendada, sus focos VIIRS y las
métricas de v3.1 de cada corrida terminada.

- Fichas: la ignición recomendada (`recomendada: {ignicion, hipotesis}`), los instantes de evaluación y el fin de la
  simulación salen de la ficha de **v3.1** (`escenarios/v3.1/eventos`). Las fichas de v3.1 y v4.0 no son iguales (10 de 15
  difieren en los puntos alternativos o en las horas). Para v4.0 se usa la alternativa por nombre solo si su ficha tiene esos
  mismos puntos y esa misma hora; si no (Las Lagunas 2024 recomienda `alt0`, que v4.0 no tiene), se le pasan los puntos y la
  hora de la ficha de v3.1 como ignición libre (`configuracion.ignicion` y `t_inicio_utc`) y se declara: con la ignición
  libre, un punto sobre una celda que no quema se corre a la celda combustible más cercana sin mirar la cicatriz
  (app/motores/ignicion.py), no dentro de la cicatriz como en la corrida offline.
- Disponibles: solo los eventos con todos sus datos en el clon (decisión 12). Los demás aparecen con la lista de lo que les
  falta. Los del lote X-49 sin `recomendada` no se corren en esta etapa (plan §6.4).
- Métricas: al terminar una corrida de un evento con ficha (estado `terminada` o `detenida`), `Metricas` lanza
  app/motores/metricas_v31.py en un proceso aparte (el servidor no carga motores: v3.1 y v4.0 traen un paquete
  `incendios_sl` cada uno). Una a la vez, en un hilo; el resultado queda en `<corrida>/metricas_v31.json`.
- Focos: `catalogo/hotspots_v3.1/viirs_<ev>.csv` (los que usa la métrica de v3.1; `catalogo/hotspots/` es otro catálogo, el
  de v4.0, y no coincide en todos los eventos).
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import math
import os
import subprocess
import sys
import threading
from functools import lru_cache
from pathlib import Path

import yaml

from . import datos

REPO = Path(__file__).resolve().parents[2]
ESC31 = REPO / "escenarios" / "v3.1" / "eventos"
ESC40 = REPO / "escenarios" / "v4.0" / "eventos"
ENTRADAS = REPO / "datos" / "inputSimulacion"
X49 = ENTRADAS / "catalogo" / "eventos_no_vistos_X49.csv"
REFERENCIA = REPO / "docs" / "etapa3" / "historico_referencia.json"
GUION = REPO / "app" / "motores" / "metricas_v31.py"
ARCHIVO = "metricas_v31.json"
MOTORES_V31 = ("v3.1-libre", "v3.1-librev2")
MOTORES = MOTORES_V31 + ("v4.0",)
CON_METRICAS = ("terminada", "detenida")
MESES_VERANO = (1, 2, 3)                   # regla 3.3 de v4.0 (src/v4.0/src/incendios_sl/eventos.py)
ADVERTENCIA_NO_VISTO = ("evento no visto (lote X-49): solo para mostrar; no se usa para ajustar ningún parámetro "
                        "(DATOS.md, plan §6.4)")
ADVERTENCIA_VISTO = ("evento visto: las igniciones recomendadas se eligieron mirando la cicatriz y los focos, lo que "
                     "favorece el IoU (X-46); sirve para mostrar y detectar regresiones, no para calibrar")


class NoSePuede(Exception):
    """Un pedido del modo histórico que no se puede cumplir; `codigo` es el código HTTP."""

    def __init__(self, mensaje: str, codigo: int = 409):
        super().__init__(mensaje)
        self.codigo = codigo


def _utc(texto) -> dt.datetime:
    return datos._utc(texto)


def _iso(t: dt.datetime) -> str:
    return datos._iso(t)


# ---------------------------------------------------------------------------------------------- fichas y catálogos
def _firma(ruta: Path):
    try:
        return ruta.stat().st_mtime_ns
    except OSError:
        return None


@lru_cache(maxsize=64)
def _yaml(ruta: str, _firma_) -> dict | None:
    try:
        d = yaml.safe_load(Path(ruta).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, yaml.YAMLError):
        return None


def ficha(id_evento: str, version: str = "v3.1") -> dict | None:
    ruta = (ESC31 if version == "v3.1" else ESC40) / f"{id_evento}.yaml"
    return _yaml(str(ruta), _firma(ruta))


def ids() -> list[str]:
    """Los eventos con ficha de v3.1 (los 15; los generados RT-… no son históricos)."""
    return sorted(p.stem for p in ESC31.glob("*.yaml") if not datos.es_rt(p.stem))


@lru_cache(maxsize=2)
def _x49(_firma_) -> dict[str, dict]:
    try:
        with open(X49, encoding="utf-8", newline="") as f:
            return {r["id_evento"]: r for r in csv.DictReader(f)}
    except (OSError, KeyError):
        return {}


def no_vistos() -> dict[str, dict]:
    """Filas de `catalogo/eventos_no_vistos_X49.csv` por id de evento."""
    return _x49(_firma(X49))


@lru_cache(maxsize=2)
def _referencia(_firma_) -> dict:
    try:
        return json.loads(REFERENCIA.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def referencia() -> dict:
    return _referencia(_firma(REFERENCIA))


def cifras_documentadas(id_evento: str) -> list[dict]:
    r = referencia()
    if r.get("evento") != id_evento:
        return []
    return [{k: f.get(k) for k in ("fila", "motor", "variante", "ignicion", "ignicion_texto", "hipotesis", "hora_utc", "horas",
                                    "parada", "cifras", "medida", "regenerar", "verificada")} for f in r.get("filas") or []]


def puntos_de(f: dict, ignicion: str) -> list[dict] | None:
    """Los puntos de `snmf` (la ignición principal) o de `altN` en una ficha, o None si no existe."""
    if ignicion == "snmf":
        p = (f.get("ignicion") or {}).get("puntos")
    elif ignicion.startswith("alt") and ignicion[3:].isdigit():
        alt = f.get("ignicion_alternativas") or []
        i = int(ignicion[3:])
        p = alt[i].get("puntos") if i < len(alt) and isinstance(alt[i], dict) else None
    else:
        p = None
    return [{"nombre": str(x.get("nombre", "")), "lon": float(x["lon"]), "lat": float(x["lat"])} for x in p] if p else None


def hora_de(f: dict, hipotesis: int) -> str | None:
    horas = (f.get("inicio") or {}).get("hora_utc_hipotesis") or []
    return _iso(_utc(horas[hipotesis])) if 0 <= hipotesis < len(horas) else None


def ruta_focos(id_evento: str) -> Path:
    return ENTRADAS / "catalogo" / "hotspots_v3.1" / f"viirs_{id_evento}.csv"


def _verano_v40(f: dict) -> list[str]:
    """Compuestos de verano que le faltan a v4.0 (regla 3.3: enero a marzo del año del evento, o del anterior si el evento es
    de verano). Sin ellos v4.0 usa un respaldo y los resultados cambian (con aviso en el registro del motor)."""
    try:
        fecha = dt.date.fromisoformat(str((f.get("inicio") or {}).get("fecha_local")
                                          or (f.get("inicio") or {}).get("hora_utc_hipotesis")[0])[:10])
    except (TypeError, ValueError, IndexError):
        return ["fecha del evento"]
    anio = fecha.year if fecha.month > max(MESES_VERANO) else fecha.year - 1
    carpetas = [ENTRADAS / "sim_v4" / "dinamicos" / "indices", ENTRADAS / "banco_v4" / "entradas" / "indices_extra"]
    faltan = []
    for m in MESES_VERANO:
        nombre = f"NDVI_NDMI_{anio}_{m:02d}.tif"
        if not any((c / nombre).exists() or any(c.glob(nombre + ".part*")) for c in carpetas):
            faltan.append(f"datos/inputSimulacion/sim_v4/dinamicos/indices/{nombre}")
    return faltan


def faltantes(id_evento: str, f: dict) -> dict[str, list[str]]:
    """Archivos que faltan en el clon: `todos` (los dos motores y la métrica) y `v40` (solo para v4.0; no impiden correr,
    pero sin ellos v4.0 usa un respaldo y da otra cosa)."""
    ev = ENTRADAS / "eventos" / id_evento
    comb = ENTRADAS / "combustibles" / id_evento
    rel = lambda p: p.relative_to(REPO).as_posix()                                  # noqa: E731
    faltan = []
    for p in (ev / f"cicatriz_referencia_{id_evento}.tif", ev / f"humedad_muerto_{id_evento}.csv",
              comb / f"combustible_clase_{id_evento}.tif", ruta_focos(id_evento)):
        if not p.exists():
            faltan.append(rel(p))
    if not any((ENTRADAS / "meteo").glob(f"{id_evento}_*_dominio.csv")):
        faltan.append(f"datos/inputSimulacion/meteo/{id_evento}_*_dominio.csv (meteorología del evento)")
    try:
        dom = datos.dominio()["id"]
        if not (ENTRADAS / "grilla" / f"mascara_dominio_{dom}.tif").exists():
            faltan.append(f"datos/inputSimulacion/grilla/mascara_dominio_{dom}.tif")
    except (OSError, StopIteration, KeyError):
        faltan.append("ficha del dominio")
    return {"todos": faltan, "v40": _verano_v40(f)}


def _contar_focos(id_evento: str) -> tuple[int | None, int | None]:
    """(n de focos, n de pasadas) del catálogo hotspots_v3.1, o (None, None) si no está."""
    try:
        with open(ruta_focos(id_evento), encoding="utf-8", newline="") as fh:
            filas = list(csv.DictReader(fh))
    except OSError:
        return None, None
    return len(filas), len({(r.get("date"), r.get("acq_time_s")) for r in filas})


# ---------------------------------------------------------------------------------------------- lista y corrida
def resumen(id_evento: str) -> dict | None:
    f31 = ficha(id_evento, "v3.1")
    if f31 is None:
        return None
    f40 = ficha(id_evento, "v4.0") or {}
    x49 = no_vistos().get(id_evento)
    rec = f31.get("recomendada") or None
    fin = f31.get("fin") or {}
    falta = faltantes(id_evento, f31)
    n_focos, n_pasadas = _contar_focos(id_evento)
    e = {"id": id_evento, "nombre": f31.get("nombre"),
         "rol": "no visto (X-49)" if x49 else "visto",
         "advertencia": ADVERTENCIA_NO_VISTO if x49 else ADVERTENCIA_VISTO,
         "disponible": not falta["todos"], "faltan": falta["todos"], "faltan_v40": falta["v40"],
         "recomendada": None, "se_puede_correr": False, "motivo": None,
         "evaluacion_utc": [_iso(_utc(t)) for t in fin.get("evaluacion_utc") or []],
         "fin_simulacion_utc": _iso(_utc(fin["fin_simulacion_utc"])) if fin.get("fin_simulacion_utc") else None,
         "superficie_ha": (f31.get("referencia_espacial") or {}).get("superficie_ha"),
         "n_focos": n_focos, "n_pasadas": n_pasadas,
         "fichas_v31_v40_iguales": f31 == f40,
         "cifras_documentadas": cifras_documentadas(id_evento)}
    if x49:
        e["x49"] = {k: x49.get(k) for k in ("instante", "visto_por", "fijado", "sha256_ficha", "sha256_cicatriz")}
    if rec:
        ign, hip = str(rec.get("ignicion")), int(rec.get("hipotesis", 0))
        hora, puntos = hora_de(f31, hip), puntos_de(f31, ign)
        igual40 = puntos is not None and puntos_de(f40, ign) == puntos and hora_de(f40, hip) == hora
        horas_fin = (math.ceil((_utc(e["fin_simulacion_utc"]) - _utc(hora)).total_seconds() / 3600)
                     if hora and e["fin_simulacion_utc"] else None)
        e["recomendada"] = {"ignicion": ign, "hipotesis": hip, "t_inicio_utc": hora, "puntos": puntos,
                            "horas_hasta_fin": horas_fin,
                            "v40": "por nombre (la ficha de v4.0 tiene los mismos puntos y la misma hora)" if igual40 else
                                   "ignición libre con los puntos y la hora de la ficha de v3.1 (la ficha de v4.0 no tiene "
                                   f"{ign} con esos puntos y esa hora)"}
    if not rec:
        e["motivo"] = ("lote X-49 sin ignición recomendada: no se corre en esta etapa (plan §6.4)" if x49 else
                       "la ficha de v3.1 no tiene ignición recomendada (`recomendada`)")
    elif falta["todos"]:
        e["motivo"] = ("faltan datos en este clon (llegan con la publicación de datos históricos, F7): "
                       + ", ".join(falta["todos"]))
    elif not (e["recomendada"]["puntos"] and e["recomendada"]["t_inicio_utc"]):
        e["motivo"] = "la ignición recomendada no está completa en la ficha de v3.1"
    else:
        e["se_puede_correr"] = True
    return e


def lista() -> list[dict]:
    return [r for r in (resumen(i) for i in ids()) if r is not None]


def armar(id_evento: str, motores: list[str], horas: int | None) -> list[dict]:
    """Los pedidos para `Gestor.crear` (uno por motor) con la ignición y la hipótesis recomendadas, cada uno con su bloque
    `historico` (qué se corrió y qué se declara). NoSePuede con el motivo si el evento no se puede correr."""
    e = resumen(id_evento)
    if e is None:
        raise NoSePuede(f"{id_evento} no es un evento con ficha (modo histórico); eventos: {', '.join(ids())}", 404)
    if not e["se_puede_correr"]:
        raise NoSePuede(f"{id_evento}: {e['motivo']}")
    if not motores:
        raise NoSePuede("motores: al menos uno de " + ", ".join(MOTORES), 422)
    malos = [m for m in motores if m not in MOTORES]
    if malos or len(set(motores)) != len(motores):
        raise NoSePuede(f"motores: {', '.join(map(str, malos)) or 'repetidos'}; opciones: {', '.join(MOTORES)}", 422)
    rec = e["recomendada"]
    if horas is not None and rec["horas_hasta_fin"] is not None and horas > rec["horas_hasta_fin"]:
        raise NoSePuede(f"horas: como mucho {rec['horas_hasta_fin']} (hasta fin.fin_simulacion_utc de la ficha, "
                        f"{e['fin_simulacion_utc']})", 422)
    f40 = ficha(id_evento, "v4.0") or {}
    igual40 = puntos_de(f40, rec["ignicion"]) == rec["puntos"] and hora_de(f40, rec["hipotesis"]) == rec["t_inicio_utc"]
    base = {"evento": id_evento, "ignicion": rec["ignicion"], "hipotesis": rec["hipotesis"],
            "t_inicio_utc": rec["t_inicio_utc"], "horas": horas, "horas_hasta_fin": rec["horas_hasta_fin"],
            "rol": e["rol"], "advertencia": e["advertencia"], "ficha": "escenarios/v3.1/eventos"}
    pedidos = []
    for m in motores:
        declaracion = [f"modo histórico: ignición recomendada de la ficha de v3.1 ({rec['ignicion']}, hipótesis "
                       f"{rec['hipotesis']}, {rec['t_inicio_utc']})", e["advertencia"]]
        p = {"motor": m, "evento": id_evento, "horas": horas}
        if m in MOTORES_V31 or igual40:
            p |= {"hipotesis": rec["hipotesis"], "ignicion_ficha": rec["ignicion"]}
            via = "ficha"
        else:
            p |= {"ignicion": [dict(x) for x in rec["puntos"]], "t_inicio_utc": rec["t_inicio_utc"]}
            via = "libre"
            declaracion.append(f"v4.0: su ficha no tiene {rec['ignicion']} con esos puntos y esa hora; se pasan los puntos y "
                               "la hora de la ficha de v3.1 como ignición libre. Un punto sobre una celda que no quema se "
                               "corre a la celda combustible más cercana sin mirar la cicatriz (no como en la corrida offline)")
        if m == "v4.0":
            declaracion.append("v4.0 con la configuración del simulador: variante barreras, sin parada en la cicatriz "
                               "(D-E3-01); las cifras documentadas de v4.0 son con la variante libre")
        if e["faltan_v40"] and m == "v4.0":
            declaracion.append("v4.0 sin los compuestos de verano " + ", ".join(Path(x).name for x in e["faltan_v40"])
                               + ": usa un respaldo y los resultados cambian")
        if horas is None:
            declaracion.append(f"hasta fin.fin_simulacion_utc ({e['fin_simulacion_utc']}, {rec['horas_hasta_fin']} h)")
        p["historico"] = base | {"via_v40": None if m in MOTORES_V31 else via, "declaracion": declaracion}
        pedidos.append(p)
    return pedidos


# ---------------------------------------------------------------------------------------------- métricas de v3.1
def evento_de(corrida_json: dict | None) -> str | None:
    d = ((corrida_json or {}).get("base") or {}).get("definicion") or {}
    return str(d["evento"]) if d.get("evento") else None


def aplica(c) -> tuple[bool, str | None]:
    """(sí o no, motivo) si a la corrida `c` (de corridas.Corrida) le corresponden métricas de v3.1."""
    if c.motor not in MOTORES:
        return False, f"motor {c.motor}: sin salida de v3.1 ni de v4.0"
    ev = evento_de(c.corrida_json())
    if ev is None:
        return False, "la corrida no es de un evento"
    if datos.es_rt(ev) or ficha(ev, "v3.1") is None:
        return False, f"{ev} no es un evento con ficha (no tiene cicatriz ni focos)"
    falta = faltantes(ev, ficha(ev, "v3.1"))["todos"]
    if falta:
        return False, f"faltan datos de {ev}: {', '.join(falta)}"
    return True, None


def leer(c) -> dict | None:
    try:
        return json.loads((c.carpeta / ARCHIVO).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


class Metricas:
    """Lanza app/motores/metricas_v31.py para cada corrida terminada que lo necesite, de a una, en un hilo propio."""

    def __init__(self, gestor, guion: Path | None = None, cada_s: float = 1.0, espera_max_s: float = 900.0):
        self.gestor = gestor
        self.guion = Path(guion) if guion else GUION
        self.cada_s = cada_s
        self.espera_max_s = espera_max_s
        self.calculando: str | None = None
        self.no_aplica: dict[str, str] = {}
        self._fallidas: set[str] = set()
        self._parar = threading.Event()
        self._proceso: subprocess.Popen | None = None
        self._candado = threading.Lock()
        self._hilo = threading.Thread(target=self._vigilar, name="metricas-v31", daemon=True)

    def arrancar(self) -> None:
        self._hilo.start()

    def cerrar(self) -> None:
        self._parar.set()
        with self._candado:
            p = self._proceso
        if p is not None and p.poll() is None:
            p.kill()
        self._hilo.join(5)

    def estado(self, c) -> tuple[str, str | None]:
        """(estado, motivo): no_aplica | esperando_fin | pendiente | calculando | lista | error."""
        ok, motivo = aplica(c)
        if not ok:
            return "no_aplica", motivo
        d = leer(c)
        if d is not None:
            return ("error", d.get("error")) if d.get("error") else ("lista", None)
        if self.calculando == c.id:
            return "calculando", None
        if c.estado in ("error", "interrumpida"):
            return "no_aplica", f"la corrida terminó en {c.estado}: no dejó la salida completa del motor"
        if c.estado not in CON_METRICAS:
            return "esperando_fin", f"la corrida está {c.estado}"
        return "pendiente", None

    def _pendientes(self) -> list:
        out = []
        for c in sorted(list(self.gestor.corridas.values()), key=lambda c: c.creada_utc):
            if c.estado not in CON_METRICAS or c.id in self._fallidas or c.id in self.no_aplica:
                continue
            if (c.carpeta / ARCHIVO).exists():
                continue
            ok, motivo = aplica(c)
            if not ok:
                self.no_aplica[c.id] = motivo
                continue
            out.append(c)
        return out

    def _vigilar(self) -> None:
        while not self._parar.is_set():
            try:
                for c in self._pendientes():
                    if self._parar.is_set():
                        return
                    self.calcular(c)
            except Exception:                                  # el hilo no se cae por una corrida rara
                pass
            self._parar.wait(self.cada_s)

    def calcular(self, c) -> dict | None:
        """Corre metricas_v31.py para `c` y espera. Devuelve lo que escribió (o None)."""
        entorno = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
        entorno.pop("PYTHONPATH", None)
        aparte = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        self.calculando = c.id
        try:
            with open(c.carpeta / "metricas_v31.log", "w", encoding="utf-8", errors="replace") as registro:
                with self._candado:
                    if self._parar.is_set():
                        return None
                    self._proceso = subprocess.Popen([sys.executable, "-I", str(self.guion), "--corrida", str(c.carpeta)],
                                                     cwd=REPO, env=entorno, stdin=subprocess.DEVNULL, stdout=registro,
                                                     stderr=subprocess.STDOUT, **aparte)
                try:
                    codigo = self._proceso.wait(timeout=self.espera_max_s)
                except subprocess.TimeoutExpired:
                    self._proceso.kill()
                    codigo = None
            d = leer(c)
            if d is None:
                self._fallidas.add(c.id)
                if codigo is None:
                    msj = f"el cálculo de las métricas pasó los {self.espera_max_s:.0f} s"
                elif self._parar.is_set():
                    return None
                else:
                    msj = f"metricas_v31.py terminó con código {codigo} sin escribir {ARCHIVO} (ver metricas_v31.log)"
                from .corridas import escribir_json
                escribir_json(c.carpeta / ARCHIVO, {"formato": "incendios_sl.metricas_v31/1", "corrida": c.id, "error": msj})
                d = leer(c)
            return d
        finally:
            with self._candado:
                self._proceso = None
            self.calculando = None


# ---------------------------------------------------------------------------------------------- focos para el mapa
def _t_det(fecha: str, acq_time_s) -> dt.datetime:
    d = dt.datetime.fromisoformat(str(fecha)[:10]).replace(tzinfo=dt.timezone.utc)
    return d + dt.timedelta(seconds=float(acq_time_s or 0))


def _clave(lon, lat, t: dt.datetime) -> tuple:
    return round(float(lon), 5), round(float(lat), 5), _iso(t)


def focos_geojson(id_evento: str, metricas: dict | None = None) -> dict:
    """Los focos VIIRS del evento (hotspots_v3.1) como puntos, con su pasada. Con `metricas` (metricas_v31.json de una
    corrida): `primera` (es primera detección), `clase` (a_tiempo, adelantado, atrasado, no_alcanzado; null si no es primera
    detección), `error_h`, `t_sim_h` y, para toda la pasada, `clase_pasada` (la clase más frecuente entre sus primeras
    detecciones) y su cuenta."""
    with open(ruta_focos(id_evento), encoding="utf-8", newline="") as fh:
        filas = list(csv.DictReader(fh))
    tiempos = sorted({_t_det(r["date"], r.get("acq_time_s")) for r in filas})
    numero = {t: i + 1 for i, t in enumerate(tiempos)}
    por_foco: dict[tuple, list[dict]] = {}
    por_pasada: dict[str, dict] = {}
    if metricas:
        for f in metricas.get("focos") or []:
            t = _utc(str(f["t_det_utc"]).replace(" ", "T"))
            por_foco.setdefault(_clave(f["lon"], f["lat"], t), []).append(f)
        for p in metricas.get("por_pasada") or []:
            t = _iso(_utc(str(p["t_det_utc"]).replace(" ", "T")))
            cuenta = {k: int(p.get(k) or 0) for k in ("a_tiempo", "adelantado", "atrasado", "no_alcanzado")}
            por_pasada[t] = {"n_primeras": int(p.get("n") or 0), **cuenta,
                             "clase_pasada": max(cuenta, key=lambda k: (cuenta[k], k == "a_tiempo")) if any(cuenta.values()) else None,
                             "error_mediano_h": p.get("error_mediano_h")}
    features = []
    for r in filas:
        t = _t_det(r["date"], r.get("acq_time_s"))
        props = {"t_det_utc": _iso(t), "pasada": numero[t], "fecha_local": r.get("date"), "sat": r.get("sat"),
                 "frp": float(r["frp"]) if r.get("frp") not in (None, "") else None, "daynight": r.get("daynight")}
        if metricas:
            lista_f = por_foco.get(_clave(r["lon"], r["lat"], t)) or []
            f = lista_f.pop(0) if lista_f else None
            props |= {"primera": f.get("primera") if f else None, "clase": f.get("clase") if f else None,
                      "error_h": f.get("error_h") if f else None, "t_sim_h": f.get("t_sim_h") if f else None}
            pas = por_pasada.get(_iso(t))
            props |= {"clase_pasada": pas["clase_pasada"] if pas else None, "pasada_cuenta": pas}
        features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [float(r["lon"]), float(r["lat"])]},
                         "properties": props})
    out = {"type": "FeatureCollection", "evento": id_evento,
           "fuente": ruta_focos(id_evento).relative_to(REPO).as_posix(), "n_pasadas": len(tiempos), "features": features}
    if metricas:
        out["corrida"] = metricas.get("corrida")
        out["clase_por_foco"] = metricas.get("focos") is not None
    return out
