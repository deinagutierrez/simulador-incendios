"""API FastAPI del simulador. Ejecutar: python scripts/servir.py  (o uvicorn incendios_sl.api.app:app)."""
from __future__ import annotations

import glob
import json
import logging
import time
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import __version__, config as cfgmod
from ..grilla import Grilla, bbox_a_lonlat
from . import capas, trabajos

log = logging.getLogger(__name__)
app = FastAPI(title="Simulador de incendios San Luis", version=__version__)
RAIZ = cfgmod.raiz_proyecto()
WEB = RAIZ / "web"


def _dominios() -> list[dict[str, Any]]:
    out = []
    for p in sorted(list((cfgmod.dir_escenarios() / "dominios").glob("dominio_*.yaml")) + list(cfgmod.dir_escenarios().glob("dominio_*.yaml"))):
        dom = cfgmod.cargar_dominio(p.stem.replace("dominio_", ""))
        g = Grilla.desde_config(dom)
        D = cfgmod.dir_entradas()
        mk = D / "grilla" / f"mascara_dominio_{dom['id']}.tif"
        celdas_dentro = None
        if mk.exists():
            pr = json.load(open(mk.with_suffix(".tif.json"), encoding="utf-8")) if mk.with_suffix(".tif.json").exists() else {}
            celdas_dentro = pr.get("celdas_dentro")
        lonmin, latmin, lonmax, latmax = bbox_a_lonlat(g)
        out.append({"id": dom["id"], "nombre": dom["nombre"], "crs": dom["crs"], "resolucion_m": dom["resolucion_m"], "ncol": g.ncol, "nfil": g.nfil,
                    "celdas_grilla": g.n_celdas, "celdas_dominio": celdas_dentro, "superficie_grilla_km2": g.n_celdas * g.area_celda_m2 / 1e6,
                    "superficie_dominio_km2": (celdas_dentro or 0) * g.area_celda_m2 / 1e6, "bounds_lonlat": [[latmin, lonmin], [latmax, lonmax]],
                    "dem": dom["dem"]["fuente"], "viento_preparado": bool(glob.glob(str(D / "viento" / f"viento_unitario_{dom['id']}_*.nc")))})
    return out


def _eventos() -> list[dict[str, Any]]:
    out = []
    for p in sorted((cfgmod.dir_escenarios() / "eventos").glob("*.yaml")):
        ev = cfgmod.cargar_evento(p.stem)
        man = cfgmod.dir_entradas() / "eventos" / ev["id"] / f"manifiesto_{ev['id']}.json"
        out.append({"id": ev["id"], "nombre": ev["nombre"], "dominio": ev["dominio"], "referencia": ev["referencia_espacial"], "inicio": ev["inicio"], "fin": ev["fin"],
                    "ignicion": ev["ignicion"], "ignicion_alternativas": ev.get("ignicion_alternativas", []), "meteorologia": ev["meteorologia"], "indices": ev["indices"],
                    "cobertura_anio": ev.get("cobertura_anio"), "notas": ev.get("notas", []), "datos_preparados": man.exists(),
                    "hipotesis_hora_utc": ev["inicio"]["hora_utc_hipotesis"], "evaluacion_utc": ev["fin"].get("evaluacion_utc", [])})
    return out


@app.get("/api/info")
def info():
    return {"version": __version__, "modelo": cfgmod.cargar_modelo(), "estados": trabajos.ESTADOS}


@app.get("/api/areas")
def areas():
    return _dominios()


@app.get("/api/incendios")
def incendios():
    return _eventos()


@app.get("/api/incendios/{id_evento}")
def incendio(id_evento: str):
    for e in _eventos():
        if e["id"] == id_evento:
            hs = cfgmod.dir_catalogo() / "hotspots"
            e["focos"] = {k: str(hs / f"{k}_{id_evento}.csv") for k in ("viirs", "modis") if (hs / f"{k}_{id_evento}.csv").exists()}
            return e
    raise HTTPException(404, "incendio no encontrado")


@app.get("/api/incendios/{id_evento}/focos")
def focos(id_evento: str):
    hs = cfgmod.dir_catalogo() / "hotspots"
    for k in ("viirs", "modis"):
        p = hs / f"{k}_{id_evento}.csv"
        if p.exists() and p.stat().st_size > 10:
            df = pd.read_csv(p)
            if len(df):
                return {"fuente": k, "n": int(len(df)), "focos": df[["date", "lon", "lat"] + ([c for c in ("acq_time_s", "frp") if c in df])].round(4).to_dict("records")}
    return {"fuente": None, "n": 0, "focos": []}


class PedidoPreparacion(BaseModel):
    evento: str
    sin_viento: bool = False


@app.post("/api/preparacion")
def preparacion(p: PedidoPreparacion):
    if p.evento not in {e["id"] for e in _eventos()}:
        raise HTTPException(404, "incendio no encontrado")
    return trabajos.lanzar_preparacion(p.evento, p.sin_viento)


class PedidoSimulacion(BaseModel):
    evento: str
    hipotesis: int = 0
    k_global: float | None = None
    k_clase: dict[int, float] | None = None
    factor_waf: float = 1.0
    horas: float | None = Field(default=None, description="limitar la duración simulada (h)")
    ignicion: str = "snmf"
    run_id: str | None = None
    figuras: bool = False
    modelo: str = Field(default="modelo_v1", description="modelo_v1 | modelo_v2 (barreras + contención)")
    barreras: str = Field(default="auto", description="auto | on | off")
    contencion: str = Field(default="auto", description="auto | on | off")
    v2: dict[str, float] | None = Field(default=None, description="ajustes v2: cruce_lambda, cruce_beta, contencion_retardo_h, tasa_linea_m_h, ...")
    despacho: str = Field(default="auto", description="auto (YAML) | global (tasa fija, docs/10) | local (SNMF con la ficha) | pronostico (SNMF sin la ficha); docs/13")


@app.post("/api/simulaciones")
def crear_simulacion(p: PedidoSimulacion):
    evs = {e["id"]: e for e in _eventos()}
    if p.evento not in evs:
        raise HTTPException(404, "incendio no encontrado")
    if not evs[p.evento]["datos_preparados"]:
        raise HTTPException(409, "los datos del incendio no están preparados; solicite /api/preparacion")
    if p.modelo not in ("modelo_v1", "modelo_v2") or p.barreras not in ("auto", "on", "off") or p.contencion not in ("auto", "on", "off")             or p.despacho not in ("auto", "global", "local", "pronostico"):
        raise HTTPException(422, "modelo debe ser modelo_v1|modelo_v2; barreras/contencion auto|on|off; despacho auto|global|local|pronostico")
    run_id = p.run_id or f"{p.evento}_h{p.hipotesis}_{time.strftime('%Y%m%dT%H%M%S')}"
    try:
        return trabajos.lanzar_simulacion(run_id, p.evento, p.hipotesis, p.k_global, p.factor_waf, p.horas, p.ignicion, p.k_clase, p.figuras,
                                          p.modelo, p.barreras, p.contencion, p.v2, p.despacho)
    except FileExistsError as e:
        raise HTTPException(409, str(e))


@app.get("/api/simulaciones")
def simulaciones():
    return trabajos.listar()


@app.get("/api/simulaciones/{run_id}")
def simulacion(run_id: str):
    d = trabajos.dir_run(run_id)
    if not d.exists():
        raise HTTPException(404, "simulación no encontrada")
    est = trabajos.leer_estado(run_id)
    out: dict[str, Any] = {"estado": est}
    for n in ("registro", "metricas"):
        p = d / f"{n}.json"
        if p.exists():
            out[n] = json.load(open(p, encoding="utf-8"))
    if est.get("estado") == "completada":
        r = capas.resultado(run_id)
        out["bounds_lonlat"] = [[r.bounds[0], r.bounds[1]], [r.bounds[2], r.bounds[3]]]
        out["t_fin_s"] = r.t_fin
        out["bounds_incendio_lonlat"] = r.bounds_incendio
    return out


@app.delete("/api/simulaciones/{run_id}")
def cancelar(run_id: str):
    return trabajos.cancelar(run_id)


@app.get("/api/simulaciones/{run_id}/serie")
def serie(run_id: str):
    p = trabajos.dir_run(run_id) / "serie_horaria.csv"
    if not p.exists():
        raise HTTPException(404, "serie no disponible")
    df = pd.read_csv(p)
    # NaN (p. ej. intensidad_max_kw_m sin contención) -> null, que JSON sí admite
    return {"columnas": list(df.columns), "filas": json.loads(df.round(3).to_json(orient="records"))}


@app.get("/api/simulaciones/{run_id}/estado/{t_s}.png")
def estado_png(run_id: str, t_s: float, ventana_s: float = 3600.0):
    try:
        r = capas.resultado(run_id)
    except FileNotFoundError:
        raise HTTPException(404, "resultados no disponibles")
    return Response(r.png(t_s, ventana_s), media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})


@app.get("/api/simulaciones/{run_id}/perimetro/{t_s}.geojson")
def perimetro(run_id: str, t_s: float):
    return JSONResponse(capas.resultado(run_id).perimetro_geojson(t_s))


@app.get("/api/simulaciones/{run_id}/viento/{t_s}.geojson")
def viento(run_id: str, t_s: float):
    return JSONResponse(capas.flechas_viento(run_id, t_s))


@app.get("/api/simulaciones/{run_id}/archivo/{nombre}")
def archivo(run_id: str, nombre: str):
    p = trabajos.dir_run(run_id) / Path(nombre).name
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p)


@app.get("/api/capas/{id_dominio}/{nombre}.png")
def capa_png(id_dominio: str, nombre: str, evento: str | None = Query(default=None)):
    try:
        png, b, ley = capas.capa_estatica(id_dominio, nombre, evento)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    return Response(png, media_type="image/png", headers={"X-Bounds": json.dumps(b), "Cache-Control": "public, max-age=86400"})


@app.get("/api/capas/{id_dominio}/{nombre}/info")
def capa_info(id_dominio: str, nombre: str, evento: str | None = Query(default=None)):
    try:
        _, b, ley = capas.capa_estatica(id_dominio, nombre, evento)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    return {"bounds_lonlat": [[b[0], b[1]], [b[2], b[3]]], "leyenda": ley}


@app.get("/api/vectores/{id_dominio}/{nombre}.geojson")
def vector(id_dominio: str, nombre: str):
    try:
        return JSONResponse(capas.vector_geojson(id_dominio, nombre), headers={"Cache-Control": "public, max-age=86400"})
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


if WEB.exists():
    app.mount("/", StaticFiles(directory=str(WEB), html=True), name="web")
