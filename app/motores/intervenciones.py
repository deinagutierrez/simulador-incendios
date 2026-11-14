"""Intervenciones y bitácora encadenada (fase F5, contrato 1.5; decisión D-E3-28, puntos 4-6, 14 y 17-21).

Lo comparten los procesos motor (`control.py`, los conductores) y, si lo necesita, el servidor. No importa ningún motor:
solo la biblioteca estándar, numpy y (para la longitud) shapely.

- `validar_entrada(entrada)`: revisa y normaliza una intervención `{tipo, datos}` (cortafuego o viento manual).
- `validar_cortafuego(datos)` / `validar_cortafuegos(lista)`: lo mismo para los trazos de `configuracion.cortafuegos`.
- `revisar_t_inicio(t)`: las corridas empiezan en hora en punto UTC (punto 6).
- `canon(x)`: JSON canónico sobre el que se calculan los hash.
- `raiz(corrida)`: hash de la configuración inicial, primer eslabón de la cadena.
- `hash_entrada(anterior, entrada)` y `verificar_cadena(raiz, bitacora)`.

Números en el hash: las coordenadas se redondean a 0,01 m y los minutos son float con 3 decimales al armar cada entrada;
además, `canon` escribe todo float entero como entero (360.0 → 360), para que el mismo dato dé el mismo hash venga de Python o
de JavaScript (que escribe 360.0 como "360").
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math

TIPOS = ("cortafuego", "viento_manual")
ANCHOS_M = (3, 6, 10, 15, 25)
VEL_MAX_KMH = 216.0                 # el mismo tope que el escenario manual del servidor
MAX_PUNTOS = 10000
MAX_CORTAFUEGOS = 100
ESTADOS = ("aceptada", "recortada", "rechazada")
CAMPOS_HASH = ("n", "t_sim_min", "t_vigor_min", "tipo", "datos")


# ------------------------------------------------------------------------------------------------ JSON canónico y hash
def _norm(x):
    """Copia de `x` con los números normalizados para el hash. Rechaza NaN e infinito."""
    if isinstance(x, bool) or x is None or isinstance(x, str):
        return x
    if isinstance(x, int):
        return int(x)
    if isinstance(x, float):
        if not math.isfinite(x):
            raise ValueError(f"número no finito en una entrada de la bitácora: {x}")
        return int(x) if x.is_integer() else x
    if isinstance(x, dict):
        return {str(k): _norm(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_norm(v) for v in x]
    if hasattr(x, "item") and hasattr(x, "dtype"):          # escalar de numpy
        return _norm(x.item())
    raise TypeError(f"tipo no admitido en la bitácora: {type(x).__name__}")


def canon(x) -> bytes:
    """JSON canónico (UTF-8): claves ordenadas, sin espacios, sin escapar acentos, sin NaN, floats enteros como enteros."""
    return json.dumps(_norm(x), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256(x) -> str:
    return hashlib.sha256(canon(x)).hexdigest()


def sha256_indices(indices) -> str:
    """Huella de un conjunto de índices enteros (celdas o enlaces aplicados): sha256 de los índices ordenados, int64
    little-endian. Sirve para guardar en la bitácora qué se aplicó sin guardar la lista."""
    import numpy as np
    a = np.unique(np.asarray(indices, dtype="int64").ravel())
    return hashlib.sha256(a.astype("<i8").tobytes()).hexdigest()


def _sin_vacios(d: dict) -> dict:
    return {k: v for k, v in d.items() if v not in (None, [], "", {})}


def configuracion_inicial(corrida: dict) -> dict:
    """Lo que entra en la raíz: formato, motor, base, configuración completa (con los cortafuegos normalizados), insumos
    y el sha256 del congelado. Quedan fuera `id`, `creada_utc`, `grupo`, `advertencias`, `bitacora`, `resultados` y
    `reproduccion`, que cambian al reproducir o son derivados."""
    cfg = _sin_vacios(dict(corrida.get("configuracion") or {}))
    if cfg.get("cortafuegos"):
        cfg["cortafuegos"] = validar_cortafuegos(cfg["cortafuegos"])
    return {"formato": corrida.get("formato"), "motor": corrida.get("motor"), "base": corrida.get("base"),
            "configuracion": cfg, "insumos": corrida.get("insumos"),
            "congelado_sha256": (corrida.get("programa") or {}).get("congelado_sha256")}


def raiz(corrida: dict) -> str:
    return sha256({"configuracion_inicial": configuracion_inicial(corrida)})


def hash_entrada(anterior: str | None, entrada: dict) -> str:
    """sha256 de la entrada (sus campos `n, t_sim_min, t_vigor_min, tipo, datos`) junto con el hash anterior (o la raíz)."""
    return sha256({"anterior": anterior, **{k: entrada.get(k) for k in CAMPOS_HASH}})


def verificar_cadena(raiz_: str | None, bitacora: list[dict]) -> tuple[bool, int | None]:
    """(True, None) si la cadena está entera; si no, (False, n de la primera entrada que no verifica)."""
    anterior = raiz_
    for i, e in enumerate(bitacora or []):
        n = e.get("n") if isinstance(e, dict) else None
        try:
            ok = n == i + 1 and hash_entrada(anterior, e) == e.get("hash")
        except (ValueError, TypeError):
            ok = False
        if not ok:
            return False, (n if isinstance(n, int) else i + 1)
        anterior = e["hash"]
    return True, None


# ------------------------------------------------------------------------------------------------ validación
def _numero(v, nombre: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"`{nombre}` tiene que ser un número")
    v = float(v)
    if not math.isfinite(v):
        raise ValueError(f"`{nombre}` tiene que ser un número finito")
    return v


def longitud_m(xy) -> float:
    """Longitud de la polilínea (coordenadas planas en metros), con shapely."""
    from shapely.geometry import LineString
    return float(LineString([(float(x), float(y)) for x, y in xy]).length)


def validar_cortafuego(datos) -> dict:
    """Normaliza un trazo: `{ancho_m, suelo_mineral, xy_5345, longitud_dibujada_m}`. Lanza ValueError si no sirve.
    Los campos que no son del trazo dibujado (los que agrega el motor al aplicarlo) se descartan."""
    if not isinstance(datos, dict):
        raise ValueError("el cortafuego tiene que ser un objeto {ancho_m, suelo_mineral, xy_5345}")
    ancho = _numero(datos.get("ancho_m"), "ancho_m")
    if ancho not in ANCHOS_M:
        raise ValueError(f"`ancho_m` tiene que ser uno de {', '.join(map(str, ANCHOS_M))} (llegó {ancho:g})")
    mineral = datos.get("suelo_mineral", False)
    if not isinstance(mineral, bool):
        raise ValueError("`suelo_mineral` tiene que ser verdadero o falso")
    xy = datos.get("xy_5345")
    if not isinstance(xy, (list, tuple)) or len(xy) < 2:
        raise ValueError("`xy_5345` tiene que ser una lista de al menos dos puntos [x, y] en EPSG:5345")
    if len(xy) > MAX_PUNTOS:
        raise ValueError(f"el trazo tiene {len(xy)} puntos; el máximo es {MAX_PUNTOS}")
    puntos: list[list[float]] = []
    for i, p in enumerate(xy):
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            raise ValueError(f"`xy_5345`: el punto {i + 1} no es un par [x, y]")
        q = [round(_numero(p[0], "x"), 2), round(_numero(p[1], "y"), 2)]
        if not puntos or q != puntos[-1]:                 # repetidos seguidos (tras redondear a 0,01 m) no suman nada
            puntos.append(q)
    if len(puntos) < 2:
        raise ValueError("el trazo tiene un solo punto distinto: no tiene longitud")
    largo = round(longitud_m(puntos), 2)
    if largo <= 0:
        raise ValueError("el trazo mide 0 m")
    return {"ancho_m": int(ancho), "suelo_mineral": mineral, "xy_5345": puntos, "longitud_dibujada_m": largo}


def validar_cortafuegos(lista) -> list[dict]:
    if not isinstance(lista, (list, tuple)):
        raise ValueError("`configuracion.cortafuegos` tiene que ser una lista de trazos")
    if len(lista) > MAX_CORTAFUEGOS:
        raise ValueError(f"hay {len(lista)} cortafuegos; el máximo es {MAX_CORTAFUEGOS}")
    out = []
    for i, d in enumerate(lista):
        try:
            out.append(validar_cortafuego(d))
        except ValueError as e:
            raise ValueError(f"cortafuego {i + 1}: {e}") from None
    return out


def validar_viento(datos) -> dict:
    """`{vel_kmh, dir_desde}` (km/h, grados desde donde viene, 0-360) o `{modo: "pronostico"}` (volver al pronóstico)."""
    if not isinstance(datos, dict):
        raise ValueError("el viento manual tiene que ser un objeto {vel_kmh, dir_desde} o {modo: \"pronostico\"}")
    modo = datos.get("modo")
    if modo == "pronostico":
        if "vel_kmh" in datos or "dir_desde" in datos:
            raise ValueError("con `modo: \"pronostico\"` no van `vel_kmh` ni `dir_desde`")
        return {"modo": "pronostico"}
    if modo not in (None, "manual"):
        raise ValueError("`modo` tiene que ser \"pronostico\" (o no ir)")
    vel = _numero(datos.get("vel_kmh"), "vel_kmh")
    if not 0.0 <= vel <= VEL_MAX_KMH:
        raise ValueError(f"`vel_kmh` tiene que estar entre 0 y {VEL_MAX_KMH:g}")
    d = _numero(datos.get("dir_desde"), "dir_desde")
    if not 0.0 <= d <= 360.0:
        raise ValueError("`dir_desde` tiene que estar entre 0 y 360 grados")
    # primero se redondea y después se pasa a 0-<360: con el orden inverso, 359,999 quedaba en 360
    return {"vel_kmh": round(vel, 2), "dir_desde": round(d, 2) % 360.0}


def validar_entrada(entrada) -> dict:
    """Entrada normalizada `{tipo, datos}` o ValueError con el motivo (que se informa como `rechazada`)."""
    if not isinstance(entrada, dict):
        raise ValueError("la intervención tiene que ser un objeto {tipo, datos}")
    tipo = entrada.get("tipo")
    if tipo not in TIPOS:
        raise ValueError(f"tipo de intervención {tipo!r} desconocido; opciones: {', '.join(TIPOS)}")
    datos = entrada.get("datos")
    if datos is None:
        raise ValueError("falta `datos` en la intervención")
    return {"tipo": tipo, "datos": validar_cortafuego(datos) if tipo == "cortafuego" else validar_viento(datos)}


# ------------------------------------------------------------------------------------------------ hora de inicio
def revisar_t_inicio(t) -> None:
    """Las corridas empiezan en hora en punto UTC (D-E3-28, punto 6). Lanza ValueError si `t` trae minutos o segundos."""
    if t in (None, ""):
        return
    texto = str(t).strip()
    try:
        momento = dt.datetime.fromisoformat(texto[:-1] + "+00:00" if texto.endswith(("Z", "z")) else texto)
    except ValueError:
        raise ValueError(f"`configuracion.t_inicio_utc` no es una fecha y hora ISO 8601: {texto!r}") from None
    if momento.tzinfo is not None:
        momento = momento.astimezone(dt.timezone.utc)
    if (momento.minute, momento.second, momento.microsecond) != (0, 0, 0):
        raise ValueError(f"`configuracion.t_inicio_utc` tiene que caer en hora en punto UTC (llegó {texto}): las corridas "
                         "empiezan siempre en hora en punto, para que el viento manual no cambie lo ya simulado")
