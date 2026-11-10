"""Corrida estándar de v4.0 (escenarios/v4.0/corridas/*.yaml) → configuración completa de SIM.

Una corrida tiene exactamente una fuente de entradas:
- `evento`: ficha de v3.0 (escenarios/v4.0/eventos/<id>.yaml); los insumos se derivan con `incendios_sl.eventos`
  (`hipotesis` = índice de `inicio.hora_utc_hipotesis`, `ignicion` = snmf | altN, `horas` recorta la duración);
- `caso`: carpeta de `datos/inputSimulacion/sim_v4/conjunto_prueba` con su `caso.yaml` (`variante_caso`: base o una de
  sus variantes; `horas` reemplaza `duracion_h`);
- `sim`: un YAML nativo de SIM (escenarios/v4.0/sim/…), relativo a la corrida, a escenarios/v4.0/sim o al repositorio.

Orden de construcción: DEFAULTS de SIM → modelo (escenarios/v4.0/modelos/<modelo>.yaml, sin `descripcion` ni el bloque
`combate` de esta capa) → entradas (evento | caso + variante_caso | sim) → **variante → campos sueltos → despacho →
ajustes → parche** (esta es la precedencia del contrato: cada paso pisa al anterior).

| Variante | modelo | barreras | contención | despacho |
| --- | --- | --- | --- | --- |
| `libre` | modelo_v3 | off | off | — |
| `barreras` | modelo_v3 | on | off | — |
| `contencion` | modelo_v3 | off | on | global |
| `ambas` | modelo_v3 | on | on | global |
| `local` | modelo_v3 | on | on | local |
| `local_pronostico` | modelo_v3 | on | on | pronostico |
| `l03` | modelo_v3 | modelo | off | l03 |
| `v4_original` | sim_v4_original | modelo (umbral_tipo) | off | — (sin supresión) |

Despacho (`parametros.contencion` de SIM y el bloque `combate` de esta capa):
- `global` (docs/10): `despacho: fijo` con `tasa_linea_m_h`, retardo fijo (`retardo_h`), sin aéreo automático, sin ficha;
- `local` (docs/13): `despacho: snmf` con a/b de la región del departamento de la ignición, retardo vial desde los
  cuarteles (`incendios_sl.arribo`), aéreo automático salvo que la ficha registre medios (`combate.aereo`), y la ficha
  (`combate.inicio_utc`, `bomberos`, `tasa_linea_m_h`, `aereo`, `cuarteles_id`);
- `pronostico`: como local sin la ficha (cuartel más cercano y medios aéreos sorteados);
- `l03`: `parametros.supresion` de V.4 con las llegadas de los 3 cuarteles más rápidos (+30 min) y P = 500 m/h;
- `auto`: lo que diga el modelo (la ficha se usa si `combate.usar_ficha`, por defecto sí).

Inicio del combate (`contencion.inicio_min`, minutos desde t0), según `combate.precedencia`:
- `contrato` (por defecto): `inicio_min` o `retardo_h` en `ajustes`/`parche` (van después del despacho; con solo
  `retardo_h` se anula `inicio_min`) > `combate.inicio_utc` de la ficha > retardo vial (`combate.retardo_modo: vial`)
  > `retardo_h` de SIM (inicio_min null);
- `v3` (como v3.0 `entradas.py`): `inicio_min` de ajustes/parche > ficha > `retardo_h` de ajustes/parche (anula el vial)
  > retardo vial > `retardo_h`.
El retardo vial y las llegadas L03 se cuentan desde la ignición: se les suma el desfase ignición − t0 (corridas `caso`/`sim`).
`combate.inicio_utc` sin huso se toma como UTC.

Bloque `combate` (de esta capa; puede venir del modelo o de la corrida, y el de la corrida va DESPUÉS del preset del
despacho): `usar_ficha`, `retardo_modo` (fijo | vial), `precedencia` (contrato | v3), `arribo{t_aviso_h 0.5, t_despacho_h 0.25}`,
`regiones{nombre: {a, b, departamentos}}`, `region_defecto`, `m_h_por_bombero` (20),
`l03{n_cuarteles 3, demora_min 30, produccion_linea_m_h 500, llama_max_m 2.4}`.

Parada en la cicatriz (`parar_en_cicatriz`: auto | on | off → `parametros.parada.superficie_observada` de SIM): la corrida
termina cuando la superficie afectada iguala o supera la observada: con `evento`, la cicatriz de referencia sobre celdas
combustibles (la `ha_ref` de la validación); con `caso`/`sim`, las celdas del perímetro observado. `auto` = encendida con `evento` y `caso`
(tienen perímetro observado), también con la variante `v4_original` (D40); apagada con `sim`.
"""
from __future__ import annotations

import copy
import logging
import math
from pathlib import Path
from typing import Any

import pandas as pd

from . import arribo, eventos
from . import config as cfgmod

log = logging.getLogger(__name__)

DOMINIO_SIM = "las_lagunas_potrerillos"        # el manifiesto de SIM cubre este dominio
MODELO_DEFECTO = "modelo_v3"

VARIANTES: dict[str, dict[str, Any]] = {
    "libre": {"modelo": "modelo_v3", "barreras": False, "contencion": False},
    "barreras": {"modelo": "modelo_v3", "barreras": True, "contencion": False},
    "contencion": {"modelo": "modelo_v3", "barreras": False, "contencion": True, "despacho": "global"},
    "ambas": {"modelo": "modelo_v3", "barreras": True, "contencion": True, "despacho": "global"},
    "local": {"modelo": "modelo_v3", "barreras": True, "contencion": True, "despacho": "local"},
    "local_pronostico": {"modelo": "modelo_v3", "barreras": True, "contencion": True, "despacho": "pronostico"},
    "l03": {"modelo": "modelo_v3", "barreras": None, "contencion": False, "despacho": "l03"},
    "v4_original": {"modelo": "sim_v4_original", "barreras": None, "contencion": False, "supresion": False},
}
AYUDA_VARIANTES = {
    "libre": "SIM corregido sin mitigación (caminos solo reducen la carga)",
    "barreras": "solo barreras viales (cruce probabilístico según la llama)",
    "contencion": "solo combate con tasa fija y retardo fijo (docs/10)",
    "ambas": "barreras + combate con tasa fija (docs/10)",
    "local": "barreras + combate SNMF con la ficha y el arribo vial desde los cuarteles (docs/13)",
    "local_pronostico": "barreras + combate SNMF sin la ficha (como ante un incendio nuevo)",
    "l03": "supresión L03 de V.4: 3 cuarteles más rápidos por la red vial, 500 m/h por dotación",
    "v4_original": "SIM de V.4 tal como se entregó (modelo sim_v4_original), sin mitigación",
}
DESPACHOS = ("auto", "global", "local", "pronostico", "l03")
PRECEDENCIAS = ("contrato", "v3")                 # combate.precedencia del inicio del combate (ver el docstring)

COMBATE_DEFECTO: dict[str, Any] = {
    "usar_ficha": True, "retardo_modo": "fijo", "precedencia": "contrato",
    "arribo": {"t_aviso_h": 0.5, "t_despacho_h": 0.25},
    "regiones": arribo.REGIONES_SNMF, "region_defecto": arribo.REGION_DEFECTO, "m_h_por_bombero": 20.0,
    "l03": {"n_cuarteles": 3, "demora_min": 30.0, "produccion_linea_m_h": 500.0, "llama_max_m": 2.4},
}
PRESETS_DESPACHO: dict[str, dict[str, Any]] = {
    "global": {"contencion": {"despacho": "fijo", "aereo_auto": {"activo": False}, "aereo_intervalos": []},
               "combate": {"retardo_modo": "fijo", "usar_ficha": False}},
    "local": {"contencion": {"despacho": "snmf", "aereo_auto": {"activo": True}},
              "combate": {"retardo_modo": "vial", "usar_ficha": True}},
    "pronostico": {"contencion": {"despacho": "snmf", "aereo_auto": {"activo": True}, "aereo_intervalos": []},
                   "combate": {"retardo_modo": "vial", "usar_ficha": False}},
    "l03": {"supresion": {"activo": True}, "combate": {}},
}

CAMPOS = {"descripcion", "nombre", "run_id", "evento", "caso", "variante_caso", "sim", "dominio", "hipotesis", "ignicion", "horas",
          "variante", "modelo", "barreras", "contencion", "despacho", "ajustes", "parche", "k_grupo", "k_codigo", "k_global",
          "factor_waf", "humedad", "semilla", "ensemble", "mitigacion", "validar", "figuras", "combate", "regla_combustible", "viento",
          "parar_en_cicatriz"}


def fusionar(base: dict, extra: dict | None) -> dict:
    from simulador.config import fusionar as f
    return f(base or {}, extra or {})


def tri(v) -> bool | None:
    """auto | on | off (también true/false/1/0/si/no) → None | True | False."""
    if v is None or isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("auto", "", "—"):
        return None
    if s in ("on", "1", "true", "si", "sí", "yes"):
        return True
    if s in ("off", "0", "false", "no"):
        return False
    raise ValueError(f"valor {v!r} inválido: auto | on | off")


def resolver_ruta(v: str | Path, *bases: Path) -> Path:
    """Ruta de la corrida: absoluta, o relativa a la primera de `bases` donde exista (por defecto, la del YAML de la
    corrida, escenarios/v4.0 y el repositorio)."""
    p = Path(v)
    if p.is_absolute():
        return p
    cands = [Path(b) / p for b in (bases or ()) if b] + [cfgmod.dir_escenarios() / p, cfgmod.raiz_repositorio() / p]
    for c in cands:
        if c.exists():
            return c.resolve()
    raise FileNotFoundError(f"no existe {v} (buscado en {', '.join(str(c.parent) for c in cands)})")


def cargar_modelo(nombre: str) -> tuple[dict, str | None, dict]:
    """(YAML del modelo sin `descripcion` ni `combate`, descripción, bloque `combate`)."""
    m = copy.deepcopy(cfgmod.cargar_modelo(nombre))
    return m, m.pop("descripcion", None), m.pop("combate", None) or {}


def _puntos_lonlat(cfg: dict) -> list[tuple[float, float, pd.Timestamp | None]]:
    """(lon, lat, hora) de las igniciones del cfg (lista del YAML o GeoJSON con `usar`)."""
    from pyproj import Transformer
    ign = cfg.get("ignicion")
    if isinstance(ign, list):
        tr = Transformer.from_crs("EPSG:5345", "EPSG:4326", always_xy=True)
        out = []
        for p in ign:
            lon, lat = (float(p["lon"]), float(p["lat"])) if "lon" in p else tr.transform(float(p["x"]), float(p["y"]))
            out.append((lon, lat, pd.Timestamp(p["hora_ignicion"]) if p.get("hora_ignicion") else None))
        return out
    if isinstance(ign, str):
        import geopandas as gpd
        from simulador.config import resolver
        gdf = gpd.read_file(resolver(cfg, "ignicion"))
        if "usar" in gdf.columns:
            gdf = gdf[gdf["usar"].astype(bool)]
        gdf = gdf.to_crs(4326)
        return [(float(g.representative_point().x), float(g.representative_point().y),
                 pd.Timestamp(h) if h else None) for g, h in zip(gdf.geometry, gdf.get("hora_ignicion", [None] * len(gdf)))]
    return []


def a_utc(t) -> pd.Timestamp:
    """Instante en UTC; sin huso se toma como UTC (como `contencion._a_minutos` de SIM y el sufijo `_utc` de las fichas)."""
    t = pd.Timestamp(t)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def _t0(cfg: dict, puntos) -> pd.Timestamp | None:
    if cfg.get("t_inicio"):
        return pd.Timestamp(cfg["t_inicio"])
    hs = [h for *_, h in puntos if h is not None]
    return min(hs) if hs else None


def _hay(d: dict | None, *ruta: str) -> bool:
    for k in ruta[:-1]:
        d = (d or {}).get(k) if isinstance(d, dict) else None
    return isinstance(d, dict) and ruta[-1] in d


def traducir(esc: dict, ruta_esc: Path | None = None, run_id: str | None = None, preparar: bool = True) -> dict[str, Any]:
    """Traduce una corrida estándar a la configuración de SIM. Devuelve {cfg, entradas, modo, caso, variante_caso,
    validar, figuras}. `preparar=False` no genera insumos de eventos (para pruebas sin datos pesados)."""
    esc = copy.deepcopy(esc or {})
    fuentes = [k for k in ("evento", "caso", "sim") if esc.get(k)]
    if len(fuentes) != 1:
        raise ValueError("la corrida necesita exactamente una fuente de entradas: evento | caso | sim")
    modo = fuentes[0]
    extra = sorted(set(esc) - CAMPOS)
    if extra:
        log.warning("campos desconocidos en la corrida (se ignoran): %s", ", ".join(extra))
    dir_yaml = Path(ruta_esc).resolve().parent if ruta_esc else cfgmod.dir_escenarios() / "corridas"

    # --- variante y campos sueltos que eligen el modelo -------------------------------------------------------
    var = esc.get("variante")
    var = None if var in (None, "", "—", "auto") else str(var)
    if var is not None and var not in VARIANTES:
        raise ValueError(f"variante {var!r} desconocida; opciones: {', '.join(VARIANTES)}")
    v = VARIANTES.get(var, {})
    modelo_nombre = esc.get("modelo") if esc.get("modelo") not in (None, "", "auto") else (v.get("modelo") or MODELO_DEFECTO)
    b, c = tri(esc.get("barreras")), tri(esc.get("contencion"))           # auto = lo que diga la variante (o el modelo)
    barreras = b if b is not None else v.get("barreras")
    contencion = c if c is not None else v.get("contencion")
    despacho = str(esc.get("despacho") or "auto")
    if despacho == "auto":
        despacho = v.get("despacho") or "auto"
    if despacho not in DESPACHOS:
        raise ValueError(f"despacho {despacho!r} desconocido; opciones: {', '.join(DESPACHOS)}")
    if "k_clase" in esc:
        raise ValueError("k_clase (clases de combustible de v3.0) no aplica a SIM: usar k_grupo {GR: x, SH: y…}, k_codigo o k_global")

    from simulador.config import DEFAULTS
    modelo, modelo_desc, combate_modelo = cargar_modelo(modelo_nombre)
    # regla del combustible pre-evento (3.3 de V.4 | 3.3b, docs/v4.0/17): campo de la corrida o clave del modelo
    regla_comb = str(esc.get("regla_combustible") or modelo.get("regla_combustible") or "3.3")
    modelo = {k: x for k, x in modelo.items() if k != "regla_combustible"}
    cfg = fusionar(DEFAULTS, modelo)

    # --- entradas ----------------------------------------------------------------------------------------------
    ficha = None; caso = None; var_caso = None
    dominio = str(esc.get("dominio") or DOMINIO_SIM)
    if modo == "evento":
        dom_ev = cfgmod.cargar_evento(str(esc["evento"])).get("dominio")
        if dom_ev != DOMINIO_SIM:
            raise ValueError(f"{esc['evento']}: dominio {dom_ev!r}; el manifiesto de SIM (datos/inputSimulacion/sim_v4) solo cubre {DOMINIO_SIM!r}")
        parte, meta = eventos.insumos_evento(str(esc["evento"]), int(esc.get("hipotesis", 0) or 0), str(esc.get("ignicion") or "snmf"),
                                             esc.get("horas"), preparar=preparar, regla_combustible=regla_comb)
        meta["regla_combustible"] = regla_comb
        cfg = fusionar(cfg, parte)
        cfg["_dir"] = str(eventos.dir_evento(meta["evento"]))
        ficha = cfgmod.cargar_evento(meta["evento"]); dominio = ficha["dominio"]
    elif modo == "caso":
        import yaml
        from simulador.rutas import raiz_datos
        carpeta = raiz_datos() / "conjunto_prueba" / str(esc["caso"])
        if not (carpeta / "caso.yaml").exists():
            raise FileNotFoundError(f"no existe el caso {carpeta / 'caso.yaml'}")
        caso = yaml.safe_load((carpeta / "caso.yaml").read_text(encoding="utf-8"))
        caso["_dir"] = str(carpeta)
        var_caso = str(esc.get("variante_caso") or "base")
        cfg = fusionar(cfg, caso.get("escenario") or {})
        if var_caso != "base":
            if var_caso not in (caso.get("variantes") or {}):
                raise ValueError(f"variante_caso {var_caso!r} no existe en {esc['caso']}; opciones: base, {', '.join(caso.get('variantes') or {})}")
            cfg = fusionar(cfg, caso["variantes"][var_caso])
        cfg["_dir"] = str(carpeta); cfg["_ruta"] = str(carpeta / "caso.yaml")
        if esc.get("horas"):
            cfg["duracion_h"] = float(esc["horas"])
        meta = {"caso": str(esc["caso"]), "variante_caso": var_caso, "descripcion_caso": caso.get("descripcion"), "dominio": dominio}
    else:
        import yaml
        p = resolver_ruta(esc["sim"], dir_yaml, cfgmod.dir_escenarios() / "sim")
        cfg = fusionar(cfg, yaml.safe_load(p.read_text(encoding="utf-8")) or {})
        cfg["_dir"] = str(p.parent); cfg["_ruta"] = str(p)
        if esc.get("horas"):
            cfg["duracion_h"] = float(esc["horas"])
        meta = {"sim": eventos._rel(p), "dominio": dominio}

    P = cfg["parametros"]
    # --- campos sueltos ------------------------------------------------------------------------------------------
    if barreras is not None:
        P["barreras"]["activo"] = bool(barreras)
    if contencion is not None:
        P["contencion"]["activo"] = bool(contencion)
    if v.get("supresion") is False:
        P["supresion"]["activo"] = False
    pc = tri(esc.get("parar_en_cicatriz"))               # auto = encendida con evento y caso (cualquier variante, D40)
    parar_cicatriz = pc if pc is not None else modo in ("evento", "caso")
    P.setdefault("parada", {})["superficie_observada"] = bool(parar_cicatriz)
    if parar_cicatriz and modo == "evento" and P["parada"].get("superficie_objetivo_ha") is None:
        # tope = cicatriz sobre celdas combustibles (la ha_ref de la validación); sin insumos, SIM usa el perímetro observado
        P["parada"]["superficie_objetivo_ha"] = eventos.superficie_cicatriz_ha(meta["evento"], cfg.get("combustible"))
    prop = P.setdefault("propagacion", {})
    if esc.get("k_grupo") is not None:
        prop["k_grupo"] = {str(k).upper(): float(x) for k, x in esc["k_grupo"].items()}
    if esc.get("k_codigo") is not None:
        prop["k_codigo"] = {int(k): float(x) for k, x in esc["k_codigo"].items()}
    for k in ("k_global", "factor_waf"):
        if esc.get(k) is not None:
            prop[k] = float(esc[k])
    if esc.get("humedad"):
        P["humedad"] = fusionar(P.get("humedad") or {}, esc["humedad"])
    if esc.get("viento"):
        # atajo: `viento: windninja | serie` o un dict de ParametrosViento (fuente, biblioteca, factor_10m_20ft, …)
        vv = esc["viento"]
        P["viento"] = fusionar(P.get("viento") or {}, {"fuente": str(vv)} if isinstance(vv, str) else vv)
    if esc.get("semilla") is not None:                 # una sola semilla, como v3.0: estocástico, cruces y escapes
        s = int(esc["semilla"]); cfg["semilla"] = s; P["barreras"]["semilla"] = s; P["contencion"]["semilla"] = s
    if esc.get("ensemble") is not None:
        e = esc["ensemble"]
        cfg["ensemble"] = fusionar(cfg.get("ensemble") or {}, e) if isinstance(e, dict) else {"n": int(e)}
    mit = esc.get("mitigacion") or {}
    if mit.get("modificador_combustible"):
        cfg["modificador_combustible"] = str(resolver_ruta(mit["modificador_combustible"], dir_yaml))
    if mit.get("barreras_extra"):
        P["barreras"]["extra"] = str(resolver_ruta(mit["barreras_extra"], dir_yaml))
    figuras = bool(esc.get("figuras", True))
    if not figuras:
        cfg["salidas"]["png"] = False; cfg["salidas"]["gif"] = False
    elif float(cfg.get("duracion_h") or 0) > 48 and int(cfg["salidas"].get("png_cada_h") or 1) == 1:
        cfg["salidas"]["png_cada_h"] = int(math.ceil(float(cfg["duracion_h"]) / 48.0))   # ≤ ~48 mapas por corrida

    # --- despacho ------------------------------------------------------------------------------------------------
    pre = PRESETS_DESPACHO.get(despacho) or {}
    if pre.get("contencion"):
        P["contencion"] = fusionar(P["contencion"], pre["contencion"])
    if pre.get("supresion"):
        P["supresion"] = fusionar(P["supresion"], pre["supresion"])
    # el bloque `combate` de la corrida va después del preset del despacho (p. ej. `local` con `retardo_modo: fijo`)
    combate = fusionar(fusionar(fusionar(COMBATE_DEFECTO, combate_modelo), pre.get("combate") or {}), esc.get("combate") or {})
    precedencia = str(combate.get("precedencia") or "contrato")
    if precedencia not in PRECEDENCIAS:
        raise ValueError(f"combate.precedencia {precedencia!r} inválida: {' | '.join(PRECEDENCIAS)}")
    ajustes = esc.get("ajustes") or {}
    parche = esc.get("parche") or {}
    raras = sorted(set(ajustes) - set(DEFAULTS["parametros"]))
    if raras:
        log.warning("ajustes con claves que no son de `parametros` de SIM (¿van en `parche`?): %s", ", ".join(map(str, raras)))
    prov = fusionar(fusionar(cfg, {"parametros": ajustes}), parche)      # para saber qué queda activo al final
    puntos = _puntos_lonlat(prov)
    lonlat = [(lo, la) for lo, la, _ in puntos]
    t0 = _t0(prov, puntos)
    t0 = a_utc(t0) if t0 is not None else None
    hs = [a_utc(h) for *_, h in puntos if h is not None]
    desfase = max(0.0, (min(hs) - t0).total_seconds() / 60.0) if (hs and t0 is not None) else 0.0   # ignición − t0 (min)
    usar_ficha = bool(combate.get("usar_ficha", True)) and ficha is not None
    fc = (ficha.get("combate") or {}) if usar_ficha else {}
    desp: dict[str, Any] = {"modo": despacho, "usar_ficha": usar_ficha, "retardo_modo": combate.get("retardo_modo")}
    Pc = prov["parametros"]["contencion"]
    if Pc.get("activo"):
        if "aereo" in fc:                                 # medios observados (aunque la lista esté vacía): sin sorteo
            P["contencion"]["aereo_intervalos"] = [[str(a), str(b)] for a, b in (fc.get("aereo") or [])]
            P["contencion"]["aereo_auto"] = fusionar(P["contencion"].get("aereo_auto") or {}, {"activo": False})
        if fc.get("bomberos"):
            P["contencion"]["tasa_linea_m_h"] = float(fc["bomberos"]) * float(combate.get("m_h_por_bombero", 20.0))
        if fc.get("tasa_linea_m_h"):
            P["contencion"]["tasa_linea_m_h"] = float(fc["tasa_linea_m_h"])
        if Pc.get("despacho") == "snmf" and lonlat:
            depto = arribo.departamento_de(*lonlat[0])
            region = arribo.region_despacho(depto, combate.get("regiones"), combate.get("region_defecto", arribo.REGION_DEFECTO))
            r = (combate.get("regiones") or {}).get(region) or {}
            P["contencion"]["snmf"] = fusionar(P["contencion"].get("snmf") or {}, {k: float(r[k]) for k in ("a", "b") if k in r})
            desp |= {"departamento": depto, "region": region}
        en_ajustes = {k for k in ("inicio_min", "retardo_h") if _hay(ajustes, "contencion", k) or _hay(parche, "parametros", "contencion", k)}
        ficha_ini = fc.get("inicio_utc") and t0 is not None
        desp["precedencia"] = precedencia
        if en_ajustes and (precedencia == "contrato" or "inicio_min" in en_ajustes or not ficha_ini):
            # contrato: ajustes y parche van después del despacho y pisan ficha y arribo. v3: solo un inicio_min explícito
            # gana a la ficha; un retardo_h de ajustes gana al arribo vial pero no a la ficha (v3.0 entradas.py)
            if "inicio_min" not in en_ajustes:
                P["contencion"]["inicio_min"] = None      # solo retardo_h: SIM lo usa si inicio_min es null
            desp["inicio"] = "ajustes"
        elif ficha_ini:
            P["contencion"]["inicio_min"] = round(max(0.0, (a_utc(fc["inicio_utc"]) - t0).total_seconds() / 60.0), 2)
            desp["inicio"] = "ficha"
        elif combate.get("retardo_modo") == "vial" and lonlat:
            ar = (combate.get("arribo") or {})
            r = arribo.inicio_combate_vial(dominio, lonlat, fc.get("cuarteles_id"), ar.get("t_aviso_h", 0.5), ar.get("t_despacho_h", 0.25))
            desp["arribo"] = r
            if r is not None:                             # el arribo se cuenta desde la ignición, no desde t0
                P["contencion"]["inicio_min"] = round(r["retardo_h"] * 60.0 + desfase, 2)
                desp["inicio"] = "vial"
            else:
                desp["inicio"] = "retardo_h"
        else:
            desp["inicio"] = "retardo_h"
    if despacho == "l03" and not (_hay(ajustes, "supresion", "llegadas_min") or _hay(parche, "parametros", "supresion", "llegadas_min")):
        l3 = combate.get("l03") or {}
        lleg = arribo.llegadas_l03(dominio, lonlat, int(l3.get("n_cuarteles", 3)), float(l3.get("demora_min", 30.0))) if lonlat else []
        P["supresion"] = fusionar(P["supresion"], {"activo": True, "llegadas_min": [round(x["llegada_min"] + desfase, 1) for x in lleg],
                                                   "produccion_linea_m_h": float(l3.get("produccion_linea_m_h", 500.0)),
                                                   "llama_max_m": float(l3.get("llama_max_m", 2.4))})
        desp["llegadas_l03"] = lleg

    # --- ajustes y parche -----------------------------------------------------------------------------------------
    cfg["parametros"] = fusionar(P, ajustes)
    cfg = fusionar(cfg, parche)
    cfg["nombre"] = str(run_id or esc.get("run_id") or esc.get("nombre") or cfg.get("nombre") or "corrida")
    cfg["descripcion"] = str(esc.get("descripcion") or cfg.get("descripcion") or "")
    validar_cfg(cfg)

    Pf = cfg["parametros"]
    meta |= {"modelo_nombre": modelo_nombre, "modelo_descripcion": modelo_desc, "modelo": modelo, "variante": var,
             "barreras": bool(Pf["barreras"].get("activo")), "contencion": bool(Pf["contencion"].get("activo")),
             "supresion": bool((Pf.get("supresion") or {}).get("activo")), "despacho": desp, "combate_capa": combate,
             "parar_en_cicatriz": bool((Pf.get("parada") or {}).get("superficie_observada")),
             "mitigacion": {k: (eventos._rel(Path(x)) if x else None) for k, x in
                            (("modificador_combustible", cfg.get("modificador_combustible")), ("barreras_extra", Pf["barreras"].get("extra")))}}
    if modo != "evento" and t0 is not None:
        meta["t_inicio_utc"] = t0.tz_convert("UTC").isoformat()
        meta["t_fin_utc"] = (t0 + pd.Timedelta(hours=float(cfg["duracion_h"]))).tz_convert("UTC").isoformat()
        meta["puntos_ignicion"] = [{"lon": lo, "lat": la} for lo, la in lonlat]
    return {"cfg": cfg, "entradas": meta, "modo": modo, "caso": caso, "variante_caso": var_caso,
            "validar": bool(esc.get("validar", True)), "figuras": figuras}


def validar_cfg(cfg: dict) -> None:
    """Comprobaciones baratas antes de correr (SIM valida el resto al cargar)."""
    P = cfg["parametros"]
    if int(cfg.get("vecindad", 8)) not in (8, 16):
        raise ValueError(f"vecindad {cfg.get('vecindad')} inválida: 8 | 16")
    if float(cfg.get("duracion_h") or 0) <= 0:
        raise ValueError("duracion_h debe ser positiva")
    if not cfg.get("ignicion"):
        raise ValueError("la corrida no tiene ignición")
    if cfg.get("t_inicio") and pd.Timestamp(cfg["t_inicio"]).tzinfo is None:
        raise ValueError("t_inicio debe llevar huso horario")
    if str(P["contencion"].get("despacho", "fijo")) not in ("fijo", "snmf"):
        raise ValueError(f"contencion.despacho {P['contencion'].get('despacho')!r} inválido: fijo | snmf")
    if str(P["barreras"].get("modo", "probabilistico")) not in ("umbral_tipo", "umbral", "probabilistico"):
        raise ValueError(f"barreras.modo {P['barreras'].get('modo')!r} inválido: umbral_tipo | umbral | probabilistico")
    if str(P.get("limite_viento", "rothermel_1972")) not in ("rothermel_1972", "andrews_2013", "ninguno"):
        raise ValueError(f"limite_viento {P.get('limite_viento')!r} inválido")
    if str(P.get("extincion", "reversible")) not in ("reversible", "definitiva"):
        raise ValueError(f"extincion {P.get('extincion')!r} inválida: reversible | definitiva")
    if str(cfg.get("modo", "determinista")) not in ("determinista", "estocastico"):
        raise ValueError(f"modo {cfg.get('modo')!r} inválido: determinista | estocastico")


def cargar_corrida(nombre: str | None = None, archivo: str | Path | None = None) -> tuple[dict, Path, str]:
    """(YAML de la corrida, ruta, nombre del escenario). Con `archivo`, el nombre es su campo `nombre` o el del archivo."""
    import yaml
    if archivo:
        p = Path(archivo).resolve()
        esc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return esc, p, str(esc.get("nombre") or p.stem)
    if not nombre:
        raise ValueError("indicar el nombre de la corrida o un archivo")
    p = cfgmod.dir_escenarios() / "corridas" / f"{nombre}.yaml"
    return cfgmod.cargar_corrida(nombre), p, str(nombre)


def lista_corridas() -> list[str]:
    return sorted(p.stem for p in (cfgmod.dir_escenarios() / "corridas").glob("*.yaml"))
