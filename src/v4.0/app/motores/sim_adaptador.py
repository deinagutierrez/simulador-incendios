"""Adaptador de SIM (simulador de la Etapa 2, v4.0 en `src/v4.0/src/simulador`) para el banco de pruebas (D30) y el
protocolo v1.1/v1.3 (M1, M1-L03).

No modifica el código de SIM: arma los insumos de un evento con la regla de pre-evento de SIM
(`scripts/preparar_datos.py`, regla 3.3: cobertura del año anterior + NDVI/NDMI del verano ene–mar del año del
evento + índices de un mes), les suma el modelo de parámetros elegido y llama a `simulador.corrida.ejecutar`.

- Los insumos se escriben en `sim.insumos_banco/<id_evento>/` (datos/inputSimulacion/sim_v4/conjunto_prueba/_banco), dentro
  de la raíz de datos de SIM (`simulador.rutas.raiz_datos()`), que es contra la que corre.
- La corrida y las métricas van al registro común de corridas (`--salida`, por defecto resultados/v4.0/banco/corridas).
  `run_id = SIM_<evento>_ind-<indices>[_L03-P<P>]_<modelo>`; una corrida existente (con registro.json) no se pisa sin
  `--sobrescribir` (las de V.4, sin sufijo de modelo, nunca coinciden).
- Modelo (`--modelo`): YAML de `sim.modelos` (escenarios/v4.0/modelos) que se fusiona sobre DEFAULTS antes del escenario del
  evento. `sim_v4_original` (por defecto) reproduce SIM de V.4 (las corridas de la Fase 1 y de L03); `modelo_v3` es el
  modelo corregido de v4.0. También se acepta la ruta a un YAML. Se registra nombre, ruta y sha256 en registro.json.
- Ignición del protocolo (§4.1): celdas de las detecciones del primer pase VIIRS atribuido, t0 = hora del pase;
  sin focos, el punto SNMF a las 12:00 local que dejó `casos.py` en `banco/casos/<id>/ignicion.geojson` (tipo `parte`).
  SIM desplaza una ignición sin combustible a la celda combustible más cercana en un radio de 3 celdas, sin usar la
  cicatriz (sin fuga).
- `--indices previo` (por defecto) usa el compuesto mensual del **mes anterior** a la ignición; `--indices evento`
  usa el del mes del incendio, como hacen los casos de SIM. El compuesto del mes del evento incluye escenas
  posteriores a la ignición (información de la cicatriz): ver E018.
- Meteorología: la serie ERA5 del caso del banco si cubre la corrida; si no, Open-Meteo (red). Con `--sin-descarga` no
  se descarga: se reutiliza la `meteo_horaria.csv` ya convertida en la carpeta de insumos si cubre la corrida, y si no la
  preparación falla (`fallo_preparacion`, etapa meteo).
- `--reusar-insumos`: si falta algún compuesto NDVI/NDMI, reutiliza el combustible, el NDVI de verano y los índices ya
  preparados en la carpeta de insumos, solo si sus sha256 coinciden con los de una corrida registrada del mismo evento y
  criterio de índices (procedencia en registro.json).
- `--solo-preparar`: en seco; escribe solo los insumos y no crea la carpeta de la corrida ni registro.json.

Uso (desde src/v4.0, venv del proyecto):
    python -I app/motores/sim_adaptador.py --evento MB_2022_43644_2022-11 [--modelo sim_v4_original|modelo_v3]
        [--indices previo|evento] [--l03 P] [--sin-descarga] [--reusar-insumos] [--solo-preparar] [--horas-extra 48]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
APP = AQUI.parent
RAIZ = APP.parent                                   # src/v4.0
CODIGO_SIM = RAIZ / "src"
for _p in (RAIZ / "scripts", CODIGO_SIM, APP / "evaluador", APP, AQUI):   # con -I no se agrega la carpeta del script
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
from rutas import Rutas  # noqa: E402
HUSO = "America/Argentina/San_Luis"
MOTOR = "SIM"
MODELO_DEFECTO = "sim_v4_original"
INSUMOS_PRE_EVENTO = ("combustible_pre_evento.tif", "ndvi_verano_previo.tif", "indices_mes.tif")


def sha256(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def sha_paquete(d: Path) -> str:
    """sha256 del código de un paquete (todos los .py, ordenados por ruta relativa): sustituye al commit si no hay git."""
    h = hashlib.sha256()
    for f in sorted(Path(d).rglob("*.py")):
        if "__pycache__" in f.parts:
            continue
        h.update(f.relative_to(d).as_posix().encode()); h.update(f.read_bytes())
    return h.hexdigest()


def commit_repo(repo: Path) -> str:
    try:
        c = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        sucio = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--", "src/v4.0/src/simulador"],
                               capture_output=True, text=True).stdout.strip()
        return c + ("+cambios_en_simulador" if sucio else "")
    except Exception:
        return "desconocido"


def mes_anterior(anio: int, mes: int) -> tuple[int, int]:
    return (anio - 1, 12) if mes == 1 else (anio, mes - 1)


def cargar_modelo(RT: Rutas, modelo: str) -> tuple[str, Path, dict]:
    """(nombre, ruta, contenido) del modelo de parámetros: nombre de `sim.modelos` o ruta a un YAML."""
    import yaml
    p = Path(modelo)
    if p.suffix.lower() not in (".yaml", ".yml"):
        p = RT.modelos / f"{modelo}.yaml"
    elif not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    if not p.exists():
        disp = sorted(x.stem for x in RT.modelos.glob("*.yaml"))
        raise SystemExit(f"modelo '{modelo}' no encontrado ({p}); disponibles en {RT.modelos}: {disp}")
    return p.stem, p, yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def contencion_snmf(rutas, ide: str):
    """Parada de §4.3 (v1.3, D35): fin del día local del primer parte "Contenido", si después no hay ningún "Activo"."""
    p = rutas.banco / "casos" / ide / "partes_diarios.csv"
    if not p.exists():
        return None
    d = pd.read_csv(p)
    cont = d.loc[d.estado.astype(str).str.strip() == "Contenido", "fecha_reporte"].min()
    if not isinstance(cont, str):
        return None
    if ((d.estado.astype(str).str.strip() == "Activo") & (d.fecha_reporte > cont)).any():
        return None
    return (pd.Timestamp(cont).tz_localize(HUSO) + pd.Timedelta(days=1)).tz_convert("UTC")


def insumos_registrados(RT: Rutas, ide: str, indices: str, carpeta: Path) -> str | None:
    """run_id de una corrida registrada del evento, con el mismo criterio de índices, cuyos insumos pre-evento tienen el
    mismo sha256 que los de `carpeta`; None si ninguna coincide."""
    if not all((carpeta / n).exists() for n in INSUMOS_PRE_EVENTO):
        return None
    actuales = {n: sha256(carpeta / n) for n in INSUMOS_PRE_EVENTO}
    for rj in sorted(RT.corridas.glob("*/registro.json")):
        try:
            r = json.loads(rj.read_text(encoding="utf-8"))
        except Exception:
            continue
        pr = r.get("preparacion") or {}
        crit = ((pr.get("insumos_origen") or {}).get("indices_mes") or {}).get("criterio")
        reg = pr.get("insumos_sha256") or {}
        if r.get("id_evento") == ide and crit == indices and all(reg.get(n) == s for n, s in actuales.items()):
            return rj.parent.name
    return None


def meteo_cubre(ruta: Path, desde, hasta, columna: str) -> bool:
    if not ruta.exists():
        return False
    t = pd.to_datetime(pd.read_csv(ruta, usecols=[columna])[columna], utc=True)
    return bool(len(t)) and t.min() <= desde and t.max() >= hasta


def preparar(RT: Rutas, fila: pd.Series, focos: pd.DataFrame, indices: str, horas_extra: float, descargar: bool,
             l03: float | None = None, modelo: tuple[str, Path, dict] | None = None,
             reusar_insumos: bool = False, regla_combustible: str = "3.3", out: Path | None = None,
             parada_snmf: bool = False, indices_respaldo: Path | None = None) -> tuple[dict, dict]:
    """Escribe los insumos del evento en `sim.insumos_banco/<id>/` (u `out`) y devuelve (cfg de SIM, procedencia).

    `regla_combustible`: 3.3 (V.4) o 3.3b (NDVI estructural sin la anomalía interanual en las clases leñosas, Fase 2).
    `parada_snmf`: parada de §4.3 también sin L03 (candidatos de la Fase 2 con contención)."""
    import geopandas as gpd
    import rasterio
    import yaml
    from simulador.config import DEFAULTS, fusionar
    from simulador.fuel.generar_sb40 import generar, ndvi_estructural_anomalia, NODATA
    from simulador.io.manifiesto import validar_meteo_csv
    relativa = RT.relativa_repo
    if regla_combustible not in ("3.3", "3.3b"):
        raise ValueError(f"regla de combustible desconocida: {regla_combustible} (3.3 | 3.3b)")

    ide = fila.id_evento
    SIMD = RT.sim_datos
    out = Path(out) if out is not None else RT.insumos_banco / ide
    out.mkdir(parents=True, exist_ok=True)
    proc: dict = {"fallos": []}

    # --- ignición (§4.1) ------------------------------------------------------------------------------
    if len(focos):
        focos = focos.copy()
        focos["t"] = pd.to_datetime(focos.acq_date + " " + focos.acq_time.astype(int).astype(str).str.zfill(4), format="%Y-%m-%d %H%M", utc=True)
        t0 = focos.t.min()
        p = focos[focos.t == t0]
        ign = gpd.GeoDataFrame({"id": [f"viirs_{int(i)}" for i in p.id_foco], "hora_ignicion": [t0.tz_convert(HUSO).isoformat()] * len(p)},
                               geometry=gpd.points_from_xy(p.longitude, p.latitude), crs=4326)
        proc["ignicion"] = f"primer pase VIIRS ({len(p)} detecciones)"
    else:
        # rama SNMF (§4.1, regla 2): punto del parte a las 12:00 local, tal como lo dejó casos.py
        f_ign = RT.banco / "casos" / ide / "ignicion.geojson"
        g = gpd.read_file(f_ign) if f_ign.exists() else None
        if g is None or not len(g) or "parte" not in set(g.get("tipo", pd.Series(dtype=str)).astype(str)):
            proc["fallos"].append({"etapa": "ignicion", "error": f"sin focos atribuidos ni ignición SNMF en {f_ign}"})
            return {}, proc
        g = g[g.tipo.astype(str) == "parte"]
        t0 = pd.Timestamp(g.hora_ignicion.iloc[0]).tz_convert("UTC")
        ign = gpd.GeoDataFrame({"id": [f"snmf_{k}" for k in range(len(g))], "hora_ignicion": [t0.tz_convert(HUSO).isoformat()] * len(g)},
                               geometry=g.geometry.values, crs=g.crs).to_crs(4326)
        proc["ignicion"] = f"punto SNMF ({fila.parte_snmf}) a las 12:00 local, de {RT.relativa_banco(f_ign)}"
    ign.to_file(out / "ignicion.geojson", driver="GeoJSON")
    t80 = pd.Timestamp(fila.T80_utc)
    t100 = pd.Timestamp(fila.ultimo_pase_utc) if isinstance(fila.ultimo_pase_utc, str) and fila.ultimo_pase_utc else t80
    t_fin = max(t80, t100) + pd.Timedelta(hours=horas_extra)
    supresion = None
    if l03 is not None or parada_snmf:
        # M1-L03 (protocolo v1.3) y candidatos de la Fase 2: parada por contención del SNMF (§4.3)
        parada = contencion_snmf(RT, ide)
        proc["parada_snmf_utc"] = str(parada) if parada is not None else None
        if parada is not None:
            t_fin = parada
    if l03 is not None:
        # despacho desde cuarteles (§2.4)
        import despacho
        xy = ign.to_crs("EPSG:5345").geometry
        lleg = despacho.llegadas(RT, float(xy.x.mean()), float(xy.y.mean()), n=3)
        for f_ in lleg:
            f_["llegada_min"] = despacho.DEMORA_DESPACHO_MIN + f_["viaje_min"]
        proc["despacho"] = lleg
        supresion = {"activo": True, "llegadas_min": [f_["llegada_min"] for f_ in lleg], "produccion_linea_m_h": float(l03), "llama_max_m": 2.4}
    # ceil: la corrida puede pasar la parada SNMF hasta 59 min (comportamiento de V.4, se conserva para reproducir)
    duracion_h = float(np.ceil((t_fin - t0).total_seconds() / 3600.0))

    # --- combustible pre-evento (regla 3.3 de SIM) -------------------------------------------------------
    anio, mes = int(fila.anio), int(str(fila.meses).split("-")[0])
    cob = RT.cobertura(anio - 1)
    meses_verano = [RT.ndvi_ndmi(anio, m) for m in (1, 2, 3)]
    am, mm = (mes_anterior(anio, mes) if indices == "previo" else (anio, mes))
    f_ind = RT.ndvi_ndmi(am, mm)
    if not f_ind.exists() and indices_respaldo is not None and Path(indices_respaldo).exists():
        # el compuesto del mes no está en este equipo: índices ya preparados (registrados) o el del mes siguiente, declarado
        proc["indices_respaldo"] = {"falta": relativa(f_ind), "usado": relativa(Path(indices_respaldo))}
        f_ind = Path(indices_respaldo)
    faltan = [relativa(x) for x in [cob, *meses_verano, f_ind] if not x.exists()]
    if faltan:
        previa = insumos_registrados(RT, ide, indices, out) if reusar_insumos else None
        if previa is None:
            proc["fallos"].append({"etapa": "insumos", "faltan": faltan,
                                   "nota": "con --reusar-insumos se usan los insumos ya preparados si coinciden con una corrida registrada"})
            return {}, proc
        proc["insumos_origen"] = {"reutilizados_de": previa, "faltan_compuestos": faltan,
                                  "indices_mes": {"criterio": indices, "sha256": sha256(out / "indices_mes.tif")}}
    else:
        with rasterio.open(cob) as s:
            lc = s.read(1); perfil = s.profile; T = s.transform
        with rasterio.open(SIMD / "estaticos/topografia/mdt.tif") as s:
            dem = s.read(1)
            assert s.transform == T and s.shape == lc.shape, "la cobertura no está en la grilla del dominio"
        nd, nm = [], []
        for f in meses_verano:
            with rasterio.open(f) as s:
                a = s.read().astype("float32"); a[a == s.nodata] = np.nan
                nd.append(a[0] / 10000); nm.append(a[1] / 10000)
        ndvi_v = np.nanmedian(nd, 0); ndmi_v = np.nanmedian(nm, 0)
        umbrales = pd.read_csv(SIMD / "estaticos/combustible/umbrales_ndvi.csv")
        if regla_combustible == "3.3b":
            est, corr = ndvi_estructural_anomalia(lc, ndvi_v, umbrales)
            comb = generar(lc, dem, ndvi_v, ndmi_v, umbrales, ndvi_estructural=est)
            proc["combustible"] = {"regla": "3.3b", "corrimiento_ndvi_lenosas": {str(k): v for k, v in corr.items()}}
        else:
            comb = generar(lc, dem, ndvi_v, ndmi_v, umbrales)
        perfil.update(dtype="int16", nodata=NODATA, count=1, compress="deflate")
        with rasterio.open(out / "combustible_pre_evento.tif", "w", **perfil) as dst:
            dst.write(comb, 1)
            # etiquetas idénticas a las de V.4 (adaptador relativo a src/v4.0): mismo sha256 que los insumos registrados
            dst.update_tags(cobertura=f"MapBiomas Col.3 {anio - 1} (grilla del dominio, derivado de MOD/)", ndvi=f"verano {anio} (ene–mar), mediana",
                            regla="SIM/ preparar_datos.py regla 3.3" if regla_combustible == "3.3" else
                            "regla 3.3b: NDVI estructural de las leñosas sin la anomalía del verano (docs/v4.0/17)",
                            adaptador="app/motores/sim_adaptador.py")
        pv = dict(perfil); pv.update(nodata=-32768)
        with rasterio.open(out / "ndvi_verano_previo.tif", "w", **pv) as dst:
            dst.write(np.where(np.isnan(ndvi_v), -32768, np.round(ndvi_v * 10000)).astype("int16"), 1)
        (out / "indices_mes.tif").write_bytes(f_ind.read_bytes())
        proc["insumos_origen"] = {"cobertura": {"ruta": relativa(cob), "sha256": sha256(cob)},
                                  "ndvi_verano": [{"ruta": relativa(f), "sha256": sha256(f)} for f in meses_verano],
                                  "indices_mes": {"ruta": relativa(f_ind), "sha256": sha256(f_ind), "criterio": indices}}

    # --- meteorología ERA5 (Open-Meteo, mismo método que SIM y CP/) -----------------------------------------
    ruta_meteo = out / "meteo_horaria.csv"
    meteo_caso = RT.banco / "casos" / ide / "meteo_horaria.csv"
    desde, hasta = t0.floor("h"), t0 + pd.Timedelta(hours=duracion_h) + pd.Timedelta(hours=1)
    # la serie del caso tiene que cubrir hasta el fin de la corrida (con la parada de v1.3 puede ser más larga; E026)
    if meteo_cubre(meteo_caso, desde, hasta, "fecha_hora_utc"):
        # misma serie ERA5 del caso del banco (formato CP/), convertida con la función de SIM (E020)
        from preparar_datos import convertir_meteo_cp
        convertir_meteo_cp(meteo_caso, ruta_meteo)
        proc["meteo"] = f"ERA5 vía Open-Meteo del caso del banco ({RT.relativa_banco(meteo_caso)}, sha256 {sha256(meteo_caso)[:16]}…), convertida con convertir_meteo_cp de SIM"
    elif not descargar:
        if meteo_cubre(ruta_meteo, desde, hasta, "timestamp"):
            proc["meteo"] = f"meteo ya preparada en {relativa(ruta_meteo)} (sha256 {sha256(ruta_meteo)[:16]}…), reutilizada por --sin-descarga"
        else:
            proc["fallos"].append({"etapa": "meteo", "error": f"--sin-descarga: ni la serie del caso ni {relativa(ruta_meteo)} cubren {desde} – {hasta}"})
            return {}, proc
    else:
        from preparar_datos import descargar_era5
        lon = float(ign.geometry.x.mean()); lat = float(ign.geometry.y.mean())
        d_ = (t0.tz_convert(HUSO) - pd.Timedelta(hours=24)).date().isoformat()
        h_ = ((t0 + pd.Timedelta(hours=duracion_h)).tz_convert(HUSO) + pd.Timedelta(hours=24)).date().isoformat()
        try:
            proc["meteo"] = descargar_era5(lat, lon, d_, h_, ruta_meteo)
        except Exception as e:
            proc["fallos"].append({"etapa": "meteo", "error": repr(e)})
            return {}, proc
    validar_meteo_csv(ruta_meteo)

    esc = {
        "nombre": f"banco_{ide}", "grilla": None, "t_inicio": t0.tz_convert(HUSO).isoformat(), "duracion_h": duracion_h,
        "ignicion": "ignicion.geojson", "meteo": "meteo_horaria.csv", "combustible": "combustible_pre_evento.tif",
        "indices_mes_evento": "indices_mes.tif", "ndvi_verano": "ndvi_verano_previo.tif",
        "salidas": {"png": False, "gif": False, "geotiff": True, "geojson": False, "json": True, "descripcion": False},
    }
    if modelo is not None:
        # el escenario queda autocontenido: modelo (vecindad, dt_min, parametros) + supresión del evento
        nom, ruta_m, cont = modelo
        esc["descripcion"] = f"banco · modelo {nom}: {cont.get('descripcion', '')}".strip()
        esc = fusionar({k: v for k, v in cont.items() if k != "descripcion"}, esc)
    if supresion is not None:
        esc = fusionar(esc, {"parametros": {"supresion": supresion}})
    (out / "escenario.yaml").write_text(yaml.safe_dump(esc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    cfg = fusionar(DEFAULTS, esc)
    cfg["_dir"] = str(out); cfg["_ruta"] = str(out / "escenario.yaml")
    proc.update({"t0_utc": str(t0), "t_fin_utc": str(t0 + pd.Timedelta(hours=duracion_h)), "duracion_h": duracion_h,
                 "carpeta_insumos": relativa(out),
                 "insumos_sha256": {f.name: sha256(f) for f in sorted(out.iterdir()) if f.is_file()}})
    return cfg, proc


def evaluar_corrida(RT: Rutas, fila: pd.Series, fo: pd.DataFrame, destino: Path, run_id: str, t0_utc) -> tuple[dict, bool]:
    """Evalúa `destino/toa_min.tif` con el evaluador externo (protocolo v1.1: T80 para L y Δt) contra el polígono MapBiomas
    del evento (∩ dominio ∩ meses) y escribe metricas.json / metricas_largo.csv. Devuelve (métricas, instante degenerado)."""
    import geopandas as gpd
    import rasterio
    from rasterio.features import rasterize
    import evaluador as ev
    G = ev.grilla_dominio()
    with rasterio.open(RT.mascara_dominio) as s:
        dominio = s.read(1) == 1
    with rasterio.open(RT.fuego_mensual) as s:
        mens = s.read(int(fila.anio) - 2021)
    pol = gpd.read_file(RT.poligonos_mapbiomas).to_crs("EPSG:5345")
    pol = pol[pol.oid == fila.oid]
    meses = [int(m) for m in str(fila.meses).split("-")]
    obs = rasterize([(g, 1) for g in pol.geometry], out_shape=G.shape, transform=G.transform, dtype="uint8").astype(bool) & dominio & np.isin(mens, meses)
    toa_d, _, _ = ev.leer_toa(destino / "toa_min.tif", "min", G)
    focos = None
    if len(fo):
        fo2 = fo.copy()
        fo2["t"] = pd.to_datetime(fo2.acq_date + " " + fo2.acq_time.astype(int).astype(str).str.zfill(4), format="%Y-%m-%d %H%M", utc=True)
        fg = gpd.GeoDataFrame(fo2, geometry=gpd.points_from_xy(fo2.longitude, fo2.latitude), crs=4326).to_crs("EPSG:5345")
        focos = pd.DataFrame({"x": fg.geometry.x.values, "y": fg.geometry.y.values, "t": fo2.t.values})
    t80 = pd.Timestamp(fila.T80_utc)
    inst = {"T80": t80}
    if isinstance(fila.ultimo_pase_utc, str) and fila.ultimo_pase_utc:
        inst["T100"] = pd.Timestamp(fila.ultimo_pase_utc)
    resm, filas = ev.evaluar(toa_d, pd.Timestamp(t0_utc), obs, inst, dominio=dominio, focos=focos, t_ref_dt=t80,
                             destino=G, case_id=fila.id_evento, run=run_id)
    degenerado = int(fila.n_pases) < 2 or t80 <= pd.Timestamp(t0_utc)
    resm["instante_degenerado"] = bool(degenerado)
    ev.guardar(resm, filas, destino, {"toa_min": destino / "toa_min.tif"})
    return resm, bool(degenerado)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--raiz", default=None, help="carpeta src/v4.0 (por defecto, la de este código)")
    ap.add_argument("--evento", required=True, help="id_evento de eventos_fase1.csv")
    ap.add_argument("--salida", default=None, help="carpeta de corridas (por defecto banco/corridas)")
    ap.add_argument("--eventos", default=None, help="por defecto protocolo/eventos_fase1.csv")
    ap.add_argument("--focos", default=None, help="por defecto protocolo/focos_atribuidos.csv")
    ap.add_argument("--modelo", default=MODELO_DEFECTO, help="modelo de escenarios/v4.0/modelos (sim_v4_original | modelo_v3 | …) o ruta a un YAML")
    ap.add_argument("--indices", choices=["previo", "evento"], default="previo")
    ap.add_argument("--horas-extra", type=float, default=48.0)
    ap.add_argument("--sin-descarga", action="store_true", help="no descarga ERA5: usa la serie del caso o la meteo ya preparada en la carpeta de insumos")
    ap.add_argument("--reusar-insumos", action="store_true", help="si faltan compuestos NDVI/NDMI, reutiliza los insumos preparados verificados por sha256")
    ap.add_argument("--solo-preparar", action="store_true")
    ap.add_argument("--sobrescribir", action="store_true", help="permite pisar una corrida existente con el mismo run_id")
    ap.add_argument("--l03", type=float, default=None, help="M1-L03: producción de línea P (m/h por dotación); activa despacho, supresión y parada SNMF")
    a = ap.parse_args(argv)
    RT = Rutas(a.raiz); R = RT.raiz
    evs = pd.read_csv((R / a.eventos).resolve() if a.eventos else RT.protocolo / "eventos_fase1.csv")
    if not (evs.id_evento == a.evento).any():
        raise SystemExit(f"evento {a.evento} no está en la lista nominal")
    fila = evs[evs.id_evento == a.evento].iloc[0]
    fo = pd.read_csv((R / a.focos).resolve() if a.focos else RT.protocolo / "focos_atribuidos.csv")
    fo = fo[fo.id_evento == a.evento]
    modelo = cargar_modelo(RT, a.modelo)
    run_id = f"{MOTOR}_{a.evento}_ind-{a.indices}" + (f"_L03-P{a.l03:g}" if a.l03 is not None else "") + f"_{modelo[0]}"
    destino = (Path(a.salida).resolve() if a.salida else RT.corridas) / run_id
    if (destino / "registro.json").exists() and not (a.sobrescribir or a.solo_preparar):
        raise SystemExit(f"{destino} ya tiene una corrida registrada (usar --sobrescribir para rehacerla)")
    cfg, proc = preparar(RT, fila, fo, a.indices, a.horas_extra, not a.sin_descarga, a.l03, modelo, a.reusar_insumos)
    if a.solo_preparar:
        # en seco: solo los insumos (sim.insumos_banco/<id>); no se crea la carpeta de la corrida ni se toca el registro
        est = "fallo_preparacion" if proc["fallos"] else "preparado"
        print(json.dumps({"run_id": run_id, "estado": est, "modelo": modelo[0], "fallos": proc["fallos"],
                          **{k: proc.get(k) for k in ("t0_utc", "t_fin_utc", "duracion_h", "ignicion", "meteo", "carpeta_insumos")}},
                         ensure_ascii=False, default=str))
        return 2 if proc["fallos"] else 0
    destino.mkdir(parents=True, exist_ok=True)
    from simulador import __version__ as vsim
    relativa = RT.relativa_repo
    registro = {"motor": MOTOR if a.l03 is None else MOTOR + "-L03", "version_motor": vsim, "commit_repo": commit_repo(RT.repo),
                "simulador_sha256": sha_paquete(CODIGO_SIM / "simulador"),
                "protocolo": "v1.2" if a.l03 is None else "v1.3", "id_evento": a.evento,
                # desde v1.3 todos los eventos locales son de desarrollo (Fase 1 usada, E023)
                "rol": fila.rol if a.l03 is None else "desarrollo", "variante": f"indices_{a.indices}" + (f"_L03_P{a.l03:g}" if a.l03 is not None else ""),
                "modelo": modelo[0], "modelo_ruta": relativa(modelo[1]), "modelo_sha256": sha256(modelo[1]),
                "adaptador_sha256": sha256(Path(__file__)), "preparacion": proc,
                "supresion_sha256": sha256(CODIGO_SIM / "simulador" / "ca" / "supresion.py"), "despacho_sha256": sha256(AQUI / "despacho.py")}
    if proc["fallos"]:
        registro["estado"] = "fallo_preparacion"
        (destino / "registro.json").write_text(json.dumps(registro, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        print(json.dumps({"run_id": run_id, "estado": "fallo_preparacion", "fallos": proc["fallos"]}, ensure_ascii=False))
        return 2
    from simulador.corrida import ejecutar
    t_ = time.time()
    (destino / "sim").mkdir(exist_ok=True)
    res = ejecutar(cfg, RT.sim_datos, destino / "sim", verificar_sha=True, verbose=False)
    registro["segundos_reloj"] = round(time.time() - t_, 1)
    registro["metadata_sim"] = res["metadata"]
    # contrato común: toa_min.tif (minutos desde t0, NaN = no quema)
    toa_src = destino / "sim" / "hora_llegada_min.tif"
    import rasterio
    with rasterio.open(toa_src) as s:
        toa = s.read(1).astype("float32"); prof = s.profile
    prof.update(dtype="float32", nodata=np.nan, compress="deflate")
    with rasterio.open(destino / "toa_min.tif", "w", **prof) as d:
        d.write(toa, 1); d.update_tags(t0_utc=proc["t0_utc"], unidades="minutos desde t0", motor=MOTOR, modelo=modelo[0])
    resm, degenerado = evaluar_corrida(RT, fila, fo, destino, run_id, proc["t0_utc"])
    registro["estado"] = "ok"
    (destino / "registro.json").write_text(json.dumps(registro, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    m, eq = resm["instantes"]["T80"], resm["igual_superficie"]
    print(json.dumps({"run_id": run_id, "modelo": modelo[0], "segundos": registro["segundos_reloj"], "ha_obs": round(resm["ha_obs"], 1),
                      "ha_sim_T80": round(m["ha_sim"], 1), "L_T80": round(m["L"], 3), "iou_T80": round(m["iou"], 3), "iou_eq": eq.get("iou"),
                      "dt_h_T80": eq.get("dt_h"), "truncado": m["truncado"], "degenerado": degenerado}, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
