"""Orquestación de una corrida: carga, simulación por horas, productos y metadatos."""

from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from . import __version__
from .config import resolver, resolver_valor
from .rutas import dir_salidas, relativa
from .io.manifiesto import Manifiesto, sha256_archivo
from .io.capas import cargar_capas
from .io.meteo import SerieMeteo, HUSO
from .ca.automata import Automata
from .ca.supresion import Supresion
from .ca.contencion import Contencion, MOTIVOS, SUSPENSION
from .outputs.indicadores import indicadores_hora
from .outputs.descripcion import descripcion_hora
from .outputs import geo
from .outputs.figuras import Dibujante, gif, recuadro_automatico


def cargar_igniciones(cfg: dict, raiz: Path, grilla):
    """Lista de (fila, col, timestamp, id) desde un GeoJSON (id, hora_ignicion) o una lista en el YAML."""
    import geopandas as gpd
    from shapely.geometry import Point
    ign = cfg.get("ignicion")
    puntos = []
    if isinstance(ign, str):
        ruta = resolver(cfg, "ignicion", raiz)
        gdf = gpd.read_file(ruta)
        if gdf.crs is None:
            raise ValueError(f"{ruta} no declara CRS")
        gdf = gdf.to_crs(grilla.crs)
        if "hora_ignicion" not in gdf.columns:
            raise ValueError(f"{ruta}: falta el atributo hora_ignicion")
        if "usar" in gdf.columns:
            gdf = gdf[gdf["usar"].astype(bool)]
        for _, r in gdf.iterrows():
            geom = r.geometry if r.geometry.geom_type == "Point" else r.geometry.representative_point()
            puntos.append((geom.x, geom.y, pd.Timestamp(r["hora_ignicion"]), str(r.get("id", len(puntos)))))
    elif isinstance(ign, list):
        from pyproj import Transformer
        tr = Transformer.from_crs("EPSG:4326", grilla.crs, always_xy=True)
        for i, p in enumerate(ign):
            if "x" in p and "y" in p:
                x, y = float(p["x"]), float(p["y"])
            else:
                x, y = tr.transform(float(p["lon"]), float(p["lat"]))
            puntos.append((x, y, pd.Timestamp(p["hora_ignicion"]), str(p.get("id", i))))
    else:
        raise ValueError("El escenario necesita 'ignicion' (ruta GeoJSON o lista de puntos)")
    out = []
    for x, y, t, i in puntos:
        if t.tzinfo is None:
            raise ValueError(f"hora_ignicion sin huso horario: {t} (ignición {i})")
        f, c = grilla.indices(x, y)
        if not (0 <= f < grilla.alto and 0 <= c < grilla.ancho):
            raise ValueError(f"La ignición {i} ({x:.0f}, {y:.0f}) cae fuera de la grilla de simulación {grilla.bounds}")
        out.append((int(f), int(c), t, i))
    return out


def carpeta_salida(raiz: Path, nombre: str, base: Path | None = None) -> Path:
    base = base or dir_salidas()
    base.mkdir(parents=True, exist_ok=True)
    fecha = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    carpeta = base / f"{fecha}_{nombre}"
    k = 1
    while carpeta.exists():                      # nunca se pisa una corrida anterior
        carpeta = base / f"{fecha}_{nombre}_{k}"; k += 1
    carpeta.mkdir()
    return carpeta


def ejecutar(cfg: dict, raiz: Path, carpeta: Path | None = None, verificar_sha: bool = True, verbose: bool = True,
             extras_metadata: dict | None = None) -> dict:
    raiz = Path(raiz).resolve()
    man = Manifiesto.cargar(raiz / "manifiesto_datos.yaml")
    man.validar(verificar_sha=verificar_sha, verbose=False)
    nombre = cfg["nombre"]
    carpeta = carpeta or carpeta_salida(raiz, nombre)
    log = _Log(carpeta / "log.txt", verbose)
    log(f"Simulador v{__version__} · corrida '{nombre}' · salida {carpeta}")
    log(f"Manifiesto v{man.version} validado ({len(man.entradas)} entradas, sha256 {'verificado' if verificar_sha else 'omitido'})")

    caja = None
    if cfg.get("grilla"):
        gcfg = cfg["grilla"]; caja = (gcfg["xmin"], gcfg["ymin"], gcfg["xmax"], gcfg["ymax"])
    capas = cargar_capas(man, caja, combustible=resolver(cfg, "combustible", raiz), indices_mes=resolver(cfg, "indices_mes_evento", raiz),
                         ndvi_verano=resolver(cfg, "ndvi_verano", raiz), modificador=resolver(cfg, "modificador_combustible", raiz),
                         buffer_viviendas_m=float(cfg["parametros"]["viviendas_buffer_m"]),
                         barreras_extra=resolver_valor((cfg["parametros"].get("barreras") or {}).get("extra"), cfg, raiz, "barreras.extra"))
    g = capas.grilla
    log(f"Grilla de simulación: {g.ancho} × {g.alto} celdas, {g.bounds}")
    meteo = SerieMeteo.cargar(resolver(cfg, "meteo", raiz))
    igniciones = cargar_igniciones(cfg, raiz, g)
    t0 = pd.Timestamp(cfg["t_inicio"]) if cfg.get("t_inicio") else min(i[2] for i in igniciones)
    if t0.tzinfo is None:
        raise ValueError("t_inicio debe llevar huso horario")
    duracion = float(cfg["duracion_h"])
    t_fin = t0 + pd.Timedelta(hours=duracion)
    perimetro_obs = focos = None
    import geopandas as gpd
    if resolver(cfg, "perimetro_observado", raiz):
        perimetro_obs = gpd.read_file(resolver(cfg, "perimetro_observado", raiz)).to_crs(g.crs)
    if resolver(cfg, "focos", raiz):
        focos = gpd.read_file(resolver(cfg, "focos", raiz)).to_crs(g.crs)
        from shapely.geometry import box
        focos = focos[focos.intersects(box(*g.bounds))]
    par = cfg["parametros"].setdefault("parada", {})
    if par.get("superficie_observada") and par.get("superficie_objetivo_ha") is None:
        if perimetro_obs is None:
            log("parada.superficie_observada: la corrida no tiene perímetro observado; se simula sin ese tope")
        else:   # celdas del perímetro observado en la grilla, como `ha_obs` de la evaluación (queda en metadata.json → parametros)
            from .evaluacion.metricas import rasterizar
            par["superficie_objetivo_ha"] = round(float(rasterizar(perimetro_obs, g).sum()) * g.area_celda_ha, 2)
    if par.get("superficie_objetivo_ha") is not None:
        log(f"Parada al alcanzar {float(par['superficie_objetivo_ha']):.1f} ha (superficie observada)")

    n_ens = int(cfg.get("ensemble", {}).get("n", 0) or 0)
    if n_ens > 0 and cfg["modo"] != "estocastico":
        log("ensemble.n > 0: el modo pasa a 'estocastico'")
        cfg["modo"] = "estocastico"
    miembros = max(1, n_ens)
    prob = np.zeros(g.shape, "float32")
    resultado = None
    for m in range(miembros):
        cfg_m = dict(cfg); cfg_m["semilla"] = int(cfg.get("semilla", 42)) + m
        au = Automata(capas, meteo, cfg_m)
        au.preparar(t0, t_fin)
        indicadores = _simular(au, igniciones, t0, duracion, cfg_m, nombre, carpeta if m == 0 else None, log if m == 0 else None, miembro=m)
        prob += au.afectada
        if m == 0:
            resultado = (au, indicadores)
        if miembros > 1:
            log(f"  miembro {m+1}/{miembros}: {au.area_quemada_ha():.1f} ha · {au.motivo_fin}")
    au, indicadores = resultado
    prob /= miembros
    cont = getattr(au, "contencion", None)
    t_sim_min = float(indicadores[-1]["minutos_desde_t0"]) if indicadores else 0.0

    # ------------------------------------------------------------------ productos
    sal = cfg["salidas"]
    horas = [(d["hora_indice"], d["minutos_desde_t0"]) for d in indicadores]
    if sal.get("geotiff", True):
        nombre_toa = extras_metadata.get("nombre_toa") if extras_metadata else None
        geo.exportar_rasters(au, carpeta, nombre_toa)
        sup = getattr(au, "supresion", None)
        if sup is not None and sup.contenida is not None:
            geo.escribir_geotiff(carpeta / "linea_contenida.tif", sup.contenida.astype("uint8"), g, 0, "uint8", "celdas del frente contenidas por L03")
        if cont is not None:
            t_cont = cont.t_contencion if cont.t_contencion is not None else np.full(g.shape, np.nan, "float32")
            geo.escribir_geotiff(carpeta / "t_contencion_min.tif", t_cont, g, np.nan, "float32",
                                 "minuto desde t0 en que la celda quedó contenida por la línea (NaN = no contenida)")
        if miembros > 1:
            geo.escribir_geotiff(carpeta / "probabilidad_quemado.tif", prob, g, np.nan, "float32", f"fracción de {miembros} miembros")
    if sal.get("geojson", True):
        geo.exportar_perimetros(au, horas, carpeta)
    geo.exportar_csv(indicadores, carpeta)
    rutas_png = []
    if sal.get("png", True):
        recuadro = tuple(sal["recuadro"]) if sal.get("recuadro") else recuadro_automatico(au, perimetro_obs)
        dib = Dibujante(au, cfg, recuadro, perimetro_obs, focos, nombre)
        cada = max(1, int(sal.get("png_cada_h", 1) or 1))
        for d in indicadores:
            if d["hora_indice"] % cada == 0 or d is indicadores[-1]:
                rutas_png.append(dib.figura_hora(d, carpeta / f"mapa_hora_{d['hora_indice']:02d}.png", sal.get("dpi", 110)))
        dib.figura_final(carpeta / "isocronas_final.png", horas[-1][1], sal.get("dpi", 110) + 20)
        if miembros > 1:
            _figura_probabilidad(dib, prob, carpeta / "probabilidad_quemado.png")
        if sal.get("gif", True) and rutas_png:
            gif(rutas_png, carpeta / "animacion.gif")
    # metadatos y reproducibilidad
    if cfg.get("_ruta"):
        shutil.copy(cfg["_ruta"], carpeta / Path(cfg["_ruta"]).name)
    insumos = {}
    for clave in ("combustible", "indices_mes_evento", "ndvi_verano", "modificador_combustible", "meteo", "ignicion", "perimetro_observado", "focos"):
        r = resolver(cfg, clave, raiz)
        if r:
            insumos[clave] = {"ruta": relativa(r), "sha256": _sha_manifiesto(man, r, raiz)}
    for nombre_capa in ("mdt", "pendiente", "orientacion", "infraestructura", "dominio", "grilla", "parametros_sb40"):
        if nombre_capa in man.entradas:
            insumos[nombre_capa] = {"ruta": man.entradas[nombre_capa].ruta, "sha256": man.sha(nombre_capa)}
    if not resolver(cfg, "combustible", raiz) and "combustible" in man.entradas:
        insumos["combustible"] = {"ruta": man.entradas["combustible"].ruta, "sha256": man.sha("combustible")}
    meta = {
        "version_codigo": __version__, "version_manifiesto": man.version, "fecha_corrida": dt.datetime.now().isoformat(timespec="seconds"),
        "nombre": nombre, "semilla": int(cfg.get("semilla", 42)), "modo": cfg["modo"], "miembros_ensemble": miembros,
        "t_inicio": t0.isoformat(), "t_fin": t_fin.isoformat(), "duracion_h": duracion, "dt_min": cfg["dt_min"], "vecindad": cfg["vecindad"],
        "grilla": g.to_dict(), "igniciones": [{"id": i, "fila": f, "col": c, "t": t.isoformat()} for f, c, t, i in igniciones],
        "parametros": cfg["parametros"], "insumos": insumos, "toco_borde": bool(au.toco_borde), "spots": int(au.spots),
        "superficie_final_ha": au.area_quemada_ha(), "sub_pasos": int(au.n_subpasos),
        "supresion": au.supresion.resumen(duracion * 60) if getattr(au, "supresion", None) is not None else None,
        "contencion": cont.resumen(t_sim_min) if cont is not None else None,
        "motivo_fin": au.motivo_fin, "motivo_fin_texto": au.motivo_fin_texto,
        "superficie_objetivo_ha": getattr(au, "superficie_objetivo_ha", None),
        "t_superficie_objetivo": (t0 + pd.Timedelta(minutes=au.t_superficie_objetivo_min)).isoformat()
                                 if getattr(au, "t_superficie_objetivo_min", None) is not None else None,
        "parada_suspendida": dict(getattr(au, "parada_suspendida", {}) or {}),
        "t_fin_simulado": (t0 + pd.Timedelta(minutes=t_sim_min)).isoformat(), "duracion_simulada_h": round(t_sim_min / 60.0, 3),
    }
    if extras_metadata:
        meta.update({k: v for k, v in extras_metadata.items() if k != "nombre_toa"})
    geo.escribir_json(meta, carpeta / "metadata.json")
    log(f"Fin ({au.motivo_fin}): {au.area_quemada_ha():.1f} ha en {t_sim_min / 60.0:.0f} h de {duracion:.0f} · {len(indicadores)} horas · productos en {carpeta}")
    return {"carpeta": carpeta, "automata": au, "indicadores": indicadores, "capas": capas, "perimetro_obs": perimetro_obs,
            "focos": focos, "t0": t0, "probabilidad": prob if miembros > 1 else None, "metadata": meta,
            "motivo_fin": au.motivo_fin}


def _simular(au: Automata, igniciones, t0, duracion_h, cfg, nombre, carpeta, log, miembro: int = 0):
    """Bucle horario: igniciones programadas, paso del autómata, L03 y contención (en ese orden, combinables), estado
    horario y parada anticipada (`parametros.parada`). Deja en `au` el motivo de fin (`motivo_fin`, `motivo_fin_texto`),
    la supresión (`au.supresion`) y la contención (`au.contencion`, estado nuevo por miembro de ensemble).

    Parada anticipada (`parametros.parada`), evaluada en cada hora: `contenido` (frente contenido) o `sin_avance`
    (`horas_sin_avance` horas sin nuevas celdas afectadas). Se SUSPENDE mientras el incendio todavía puede crecer:
    - `escapes`: hay celdas contenidas con vecinas combustibles no cortadas y p_escape_hora > 0 (v3.0 seguía hasta t_fin
      "por posibles escapes"; `parada.escapes`: v3 (por defecto) | potencial (solo si alguna puede superar
      intensidad_escape_kw_m con la meteorología de las horas restantes) | ignorar (v4.0 anterior));
    - `pavesas`: spotting activo con celdas que emiten (I_B > 0);
    - `latentes` (solo `sin_avance`, H2): celdas latentes por humedad (`au.n_latentes` > 0, extinción reversible) mientras
      las horas sin avance no lleguen a max(horas_sin_avance, `parada.latentes_max_h` = 24).
    Con la parada suspendida la corrida sigue; si llega al horizonte el motivo de fin es `contenido` (frente contenido
    al final), `horizonte` o `extinguido`, y `motivo_fin_texto` agrega "Parada anticipada suspendida por: … (N h)". Las
    horas suspendidas por motivo quedan en `au.parada_suspendida` (metadata `parada_suspendida`).

    Parada por superficie observada (`parada.superficie_objetivo_ha`, la fija `ejecutar` con `parada.superficie_observada`):
    se evalúa en cada sub-paso y no se suspende; al alcanzarla se emite el estado de ese instante (hora parcial) y la
    corrida termina con motivo `superficie_observada` (`au.t_superficie_objetivo_min`)."""
    pasos = int(round(duracion_h * 60 / cfg["dt_min"]))
    pendientes = sorted(igniciones, key=lambda i: i[2])
    if not pendientes:
        raise ValueError("El escenario no tiene igniciones activas (revisar 'usar' en el GeoJSON de ignición)")
    encendidas = 0
    indicadores = []
    anterior = None
    hora = 0
    t_prev = 0.0
    d0 = None
    import time
    t_reloj = time.time()
    sup = Supresion.desde_cfg(cfg, au.res)          # L03 (None si está desactivada)
    au.supresion = sup
    cont = Contencion.desde_cfg(cfg, au.res, au.t0, miembro)    # contención por combate (None si está desactivada)
    au.contencion = cont
    par = cfg["parametros"].get("parada") or {}
    n_sin_avance = par.get("horas_sin_avance")
    n_sin_avance = int(n_sin_avance) if n_sin_avance else None
    parar_contenido = bool(par.get("contenido", False)) and cont is not None
    modo_escapes = str(par.get("escapes", "v3"))                 # v3 | potencial | ignorar (ver Contencion.escape_posible)
    if modo_escapes not in ("v3", "potencial", "ignorar"):
        raise ValueError(f"parada.escapes debe ser v3, potencial o ignorar (vino {modo_escapes!r})")
    h_latentes = float(par.get("latentes_max_h", 24.0) or 0.0)   # H2: noches húmedas con extinción reversible
    pavesas = bool((cfg["parametros"].get("spotting") or {}).get("activo"))
    objetivo = float(par["superficie_objetivo_ha"]) if par.get("superficie_objetivo_ha") is not None else None
    au.superficie_objetivo_ha = objetivo; au.t_superficie_objetivo_min = None
    alcanzada = False
    motivo = None
    suspendida: dict[str, int] = {}                              # horas en que la parada se suspendió, por motivo
    n_afectadas = 0; horas_sin = 0
    for paso in range(pasos + 1):
        # igniciones programadas
        while pendientes and pendientes[0][2] <= au.t + pd.Timedelta(seconds=1):
            f, c, t, i = pendientes.pop(0)
            ok = au.encender(f, c, max(t, au.t0), i)
            encendidas += int(ok)
            if not pendientes and encendidas == 0:
                raise ValueError("Ninguna ignición encontró combustible: la corrida no tiene sentido (revisar puntos de ignición)")
            if log:
                log(f"  ignición '{i}' en ({f}, {c}) a las {t.tz_convert(HUSO).strftime('%Y-%m-%d %H:%M')} local → {'OK' if ok else 'sin combustible cerca'}")
        t_min = au.minutos(au.t)
        emitido = False
        if paso == 0 or abs(t_min - hora * 60.0) < 1e-6 or paso == pasos or alcanzada:
            if paso == 0 or t_min >= hora * 60.0 - 1e-6 or alcanzada:
                d = indicadores_hora(au, hora, t_min, t_prev, anterior, cfg, nombre)
                if sup is not None:
                    d["supresion"] = sup.resumen(t_min)
                if cont is not None:
                    d["contencion"] = cont.resumen_hora(t_min)
                indicadores.append(d)
                if carpeta is not None:
                    geo.escribir_json(d, carpeta / f"estado_hora_{hora:02d}.json")
                    if cfg["salidas"].get("descripcion", True):
                        (carpeta / f"descripcion_hora_{hora:02d}.txt").write_text(descripcion_hora(d), encoding="utf-8")
                if log:
                    extra = f"contenidas {d['contencion']['celdas_contenidas']} · " if cont is not None else ""
                    log(f"  hora {hora:02d} · {d['timestamp'][:16]} · {d['superficie']['quemada_ha']:.1f} ha · activas {len(au.act)} · {extra}"
                        f"viento {d['meteo']['viento_kmh']:.0f} km/h {d['meteo']['viento_dir_texto']} · HR {d['meteo']['hr_pct']:.0f} % · {time.time()-t_reloj:.0f} s")
                anterior = d; t_prev = t_min; hora += 1; emitido = True
        if paso == pasos or alcanzada:
            break
        if emitido and paso > 0:
            # parada anticipada, evaluada en cada hora (después de los escapes de la hora)
            n_af = int(au.afectada.sum())
            horas_sin = horas_sin + 1 if n_af <= n_afectadas else 0
            n_afectadas = n_af
            candidato = None
            if parar_contenido and not pendientes and cont.frente_contenido(au):
                candidato = "contenido"
            elif n_sin_avance and horas_sin >= n_sin_avance and not pendientes:
                candidato = "sin_avance"
            if candidato:
                razon = razon_suspension(au, cont, candidato, t_min, duracion_h * 60.0, horas_sin, n_sin_avance,
                                         modo_escapes, pavesas, h_latentes)
                if razon:
                    suspendida[razon] = suspendida.get(razon, 0) + 1
                else:
                    motivo = candidato
            if motivo:
                if log:
                    log(f"  parada anticipada ({motivo}) a las {t_min / 60.0:.1f} h")
                break
        t_antes = au.minutos(au.t)
        au.paso_tiempo()
        if sup is not None:
            sup.aplicar(au, t_antes, au.minutos(au.t))
        if cont is not None:
            cont.aplicar(au, t_antes, au.minutos(au.t))
        if objetivo is not None and au.area_quemada_ha() >= objetivo:
            alcanzada = True; motivo = "superficie_observada"; au.t_superficie_objetivo_min = au.minutos(au.t)
            if log:
                log(f"  superficie observada alcanzada ({au.area_quemada_ha():.1f} ≥ {objetivo:.1f} ha) a las {au.minutos(au.t) / 60.0:.2f} h")
    if motivo is None:
        if cont is not None and cont.frente_contenido(au):
            motivo = "contenido"
        else:
            motivo = "horizonte" if au.activo() or pendientes else "extinguido"
    au.motivo_fin = motivo
    au.motivo_fin_texto = MOTIVOS[motivo].format(n=n_sin_avance)
    if objetivo is not None:
        au.motivo_fin_texto += (f" {au.area_quemada_ha():.1f} ha simuladas ≥ {objetivo:.1f} ha observadas a las {au.t_superficie_objetivo_min / 60.0:.2f} h."
                                if alcanzada else f" No alcanzó la superficie observada ({au.area_quemada_ha():.1f} de {objetivo:.1f} ha).")
    au.parada_suspendida = suspendida
    if suspendida:
        razones = "; ".join(f"{SUSPENSION[r].format(h=f'{h_latentes:g}')} ({n} h)" for r, n in suspendida.items())
        au.motivo_fin_texto += f" Parada anticipada suspendida por: {razones}."
    return indicadores


def razon_suspension(au, cont, candidato: str, t_min: float, t_fin_min: float, horas_sin: int, n_sin_avance: int | None,
                     modo_escapes: str = "v3", pavesas: bool = False, h_latentes: float = 24.0) -> str | None:
    """Motivo por el que la parada anticipada `candidato` (contenido | sin_avance) se suspende en t_min, o None: el
    incendio todavía puede crecer aunque no haya sumado celdas (`escapes` > `pavesas` > `latentes`; ver `_simular`)."""
    if cont is not None and cont.escape_posible(au, t_min, t_fin_min, modo_escapes):
        return "escapes"
    if pavesas and len(au.act_IB) and bool((au.act_IB > 0).any()):
        return "pavesas"
    if candidato == "sin_avance" and au.n_latentes > 0 and horas_sin < max(int(n_sin_avance or 0), h_latentes):
        return "latentes"
    return None


def _figura_probabilidad(dib, prob, ruta):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11, 8.5))
    dib._base(ax)
    m = np.ma.masked_less_equal(prob, 0)
    im = ax.imshow(m, extent=dib.extent, cmap="YlOrRd", vmin=0, vmax=1, interpolation="nearest", zorder=4, alpha=0.85)
    dib._observado(ax)
    plt.colorbar(im, ax=ax, fraction=0.03, label="Probabilidad de quemado")
    dib._decoracion(ax, None, f"{dib.nombre} · mapa de probabilidad de quemado (ensemble)")
    fig.tight_layout(); fig.savefig(ruta, dpi=120); plt.close(fig)


def _sha_manifiesto(man: Manifiesto, ruta: Path, raiz: Path) -> str:
    try:
        rel = str(ruta.relative_to(raiz)).replace("\\", "/")
    except ValueError:
        return sha256_archivo(ruta)
    for e in man.entradas.values():
        if e.ruta.replace("\\", "/") == rel:
            return e.sha256
    return sha256_archivo(ruta)


class _Log:
    def __init__(self, ruta: Path, verbose: bool):
        self.ruta = ruta; self.verbose = verbose
        self.ruta.write_text("", encoding="utf-8")

    def __call__(self, msg: str):
        if self.verbose:
            print(msg, flush=True)
        with open(self.ruta, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
