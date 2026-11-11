"""Pedidos HTTP del servidor local (fase F2).

    GET  /api/estado                              versión, motores, eventos con datos, dominio, corridas en marcha
    POST /api/corridas                            crea una corrida (o dos con motor "ambos"); con "iniciar": true la lanza
                                                  cuerpo: motor, evento, ignicion [{lon, lat}], t_inicio_utc, horas;
                                                  o `definicion` (uso avanzado: un caso de prueba, otra hipótesis…)
    GET  /api/corridas                            lista
    GET  /api/corridas/<id>                       estado; al terminar, también bitácora y resultados
    POST /api/corridas/<id>/iniciar|pausar|reanudar|detener
    POST /api/corridas/<id>/intervenciones        solo en pausa; hoy el motor contesta "rechazada" (llega con la fase F5)
    GET  /api/corridas/<id>/eventos               avance en vivo, por un canal de una sola vía (text/event-stream)
    GET  /api/corridas/<id>/quemado.png?hora=N    huella para el mapa, hasta la hora simulada N (o completa);
                                                  con color=rrggbb, de un solo color (para comparar dos motores)
    GET  /api/corridas/<id>/perimetro.geojson?hora=N   contorno del área quemada hasta la hora N
    GET  /api/corridas/<id>/exportar              zip con corrida.json, los resultados del motor y los perímetros por hora
    GET  /api/comparacion?a=<id>&b=<id>&hora=N    coincidencia entre dos huellas (superficies, envolvente, IoU)
    GET  /api/capas?evento=<id>                   capas de fondo disponibles, con su leyenda
    GET  /api/capas/<capa>.png?evento=<id>        capa ráster lista para superponer en un mapa web
    GET  /api/vectores/<capa>.geojson             caminos, viviendas, red de media tensión, cuarteles, borde del dominio
    GET  /                                        la pantalla del simulador (app/web/index.html)
    GET  /prueba                                  página mínima de prueba de la fase F2

Seguridad: el servidor escucha solo en 127.0.0.1 y además rechaza los pedidos que no vengan de su propia página.
"""
from __future__ import annotations

import asyncio
import io
import json
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import VERSION, capas, datos, huella
from .corridas import ACTIVOS, FINALES, MOTORES_REALES, Gestor, Rechazo, sha_congelado

WEB = Path(__file__).resolve().parents[1] / "web"
NOMBRES_LOCALES = {"127.0.0.1", "localhost"}


class Punto(BaseModel):
    lon: float
    lat: float
    nombre: str | None = None


class PedidoCorrida(BaseModel):
    motor: str
    evento: str | None = None
    ignicion: list[Punto] | None = None
    t_inicio_utc: str | None = None
    horas: int | None = Field(default=None, ge=1, le=240)
    hipotesis: int | None = Field(default=None, ge=0)
    ignicion_ficha: str | None = None
    definicion: dict | None = None            # uso avanzado: lo mismo que `base.definicion` del contrato
    simulado: dict | None = None
    iniciar: bool = False


def _pedido_ajeno(request: Request) -> str | None:
    """Motivo por el que el pedido no viene de la página del propio servidor, o None si está bien."""
    anfitrion = urlsplit("//" + request.headers.get("host", ""))
    if anfitrion.hostname not in NOMBRES_LOCALES:
        return "el servidor solo atiende a 127.0.0.1 o localhost"
    origen = request.headers.get("origin")
    if origen:
        o = urlsplit(origen)
        if o.scheme != "http" or o.hostname not in NOMBRES_LOCALES or (o.port or 80) != (anfitrion.port or 80):
            return "el pedido viene de otra página"
    if request.headers.get("sec-fetch-site") not in (None, "same-origin", "none"):
        return "el pedido viene de otra página"
    return None


def crear_app(carpeta_corridas: Path | None = None, permitir_simulado: bool = False) -> FastAPI:
    gestor = Gestor(carpeta_corridas, permitir_simulado=permitir_simulado)

    @asynccontextmanager
    async def vida(_: FastAPI):
        yield
        await asyncio.to_thread(gestor.cerrar)

    app = FastAPI(title="Simulador de incendios — San Luis", version=VERSION, lifespan=vida, docs_url=None, redoc_url=None,
                  openapi_url=None)
    app.state.gestor = gestor

    @app.middleware("http")
    async def solo_la_propia_pagina(request: Request, seguir):
        motivo = _pedido_ajeno(request)
        if motivo:
            return JSONResponse({"detail": motivo}, status_code=403)
        return await seguir(request)

    @app.exception_handler(Rechazo)
    async def rechazo(_: Request, e: Rechazo):
        return JSONResponse({"detail": str(e)}, status_code=e.codigo)

    # ------------------------------------------------------------------ estado general
    @app.get("/api/estado")
    def estado():
        motores = [{"id": m, "de_prueba": False} for m in MOTORES_REALES] + [{"id": "ambos", "de_prueba": False}]
        if gestor.permitir_simulado:
            motores.append({"id": "simulado", "de_prueba": True})
        return {"programa": {"nombre": "Simulador de incendios — San Luis", "version": VERSION},
                "congelado_sha256": sha_congelado(), "motores": motores, "eventos_base": list(datos.eventos_base().values()),
                "dominio": datos.dominio(), "limite_corridas": gestor.limite_activas, "corridas_en_marcha": gestor.activas()}

    # ------------------------------------------------------------------ corridas
    @app.post("/api/corridas", status_code=201)
    def crear(pedido: PedidoCorrida):
        p = pedido.model_dump()
        if p["horas"] is None and not p.get("definicion"):
            raise HTTPException(422, "faltan las horas a simular")
        if p["motor"] != "simulado" and not p.get("definicion"):
            try:
                datos.revisar_pedido(p)
            except ValueError as e:
                raise HTTPException(422, str(e))
        corridas = gestor.crear(p)
        if pedido.iniciar:
            for c in corridas:
                gestor.iniciar(c.id)
        return {"corridas": [c.resumen() for c in corridas]}

    @app.get("/api/corridas")
    def lista():
        return {"corridas": gestor.lista(), "en_marcha": gestor.activas(), "limite": gestor.limite_activas}

    @app.get("/api/corridas/{id_}")
    def detalle(id_: str):
        c = gestor.obtener(id_)
        d = c.detalle()
        if c.listo:
            d["huella"] = {"limites": huella.limites(c.listo["grilla"]), "url": f"/api/corridas/{id_}/quemado.png"}
        return d

    @app.post("/api/corridas/{id_}/iniciar")
    def iniciar(id_: str):
        return gestor.iniciar(id_).resumen()

    @app.post("/api/corridas/{id_}/pausar")
    def pausar(id_: str):
        return gestor.pausar(id_).resumen()

    @app.post("/api/corridas/{id_}/reanudar")
    def reanudar(id_: str):
        return gestor.reanudar(id_).resumen()

    @app.post("/api/corridas/{id_}/detener")
    def detener(id_: str):
        return gestor.detener(id_).resumen()

    @app.post("/api/corridas/{id_}/intervenciones")
    def intervenir(id_: str, entrada: dict = Body(default={})):
        return gestor.intervenir(id_, entrada)

    @app.get("/api/corridas/{id_}/eventos")
    async def eventos(id_: str, request: Request, desde: int = 0):
        """Avance en vivo. Cada evento es un aviso del proceso motor o un cambio de estado, numerado (`n`). Con `desde=N`
        (o el encabezado Last-Event-ID) manda solo los posteriores al N. Se cierra cuando la corrida llega a un estado final."""
        c = gestor.obtener(id_)
        ultimo = request.headers.get("last-event-id")
        n = int(ultimo) if ultimo and ultimo.isdigit() else max(0, desde)

        async def flujo():
            nonlocal n
            quieto = 0.0
            while True:
                nuevos = c.eventos[n:]
                for e in nuevos:
                    yield f"id: {e['n']}\ndata: {json.dumps(e, ensure_ascii=False, default=str)}\n\n"
                n += len(nuevos)
                if c.estado in FINALES and n >= len(c.eventos):
                    yield "event: cierre\ndata: {}\n\n"
                    return
                if await request.is_disconnected():
                    return
                await asyncio.sleep(0.15)
                quieto = 0.0 if nuevos else quieto + 0.15
                if quieto >= 15.0:                       # para que el navegador no corte por silencio
                    quieto = 0.0
                    yield ": sigo aca\n\n"

        return StreamingResponse(flujo(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/corridas/{id_}/quemado.png")
    def quemado(id_: str, hora: float | None = None, color: str | None = None):
        c = gestor.obtener(id_)
        if not c.listo:
            raise HTTPException(404, "la corrida todavía no tiene huella")
        rgb = None
        if color:
            if len(color) != 6 or any(ch not in "0123456789abcdefABCDEF" for ch in color):
                raise HTTPException(422, "color: seis cifras hexadecimales, por ejemplo 2a78d6")
            rgb = tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))
        imagen = huella.png(c.carpeta, c.listo["grilla"], hora, rgb)
        if imagen is None:
            raise HTTPException(404, "la corrida todavía no tiene huella")
        return Response(imagen, media_type="image/png", headers={"Cache-Control": "no-store"})

    @app.get("/api/corridas/{id_}/perimetro.geojson")
    def perimetro(id_: str, hora: float | None = None):
        c = gestor.obtener(id_)
        figura = huella.perimetro(c.carpeta, c.listo["grilla"], hora) if c.listo else None
        if figura is None:
            raise HTTPException(404, "la corrida todavía no tiene huella")
        return JSONResponse(figura, media_type="application/geo+json")

    @app.get("/api/corridas/{id_}/exportar")
    def exportar(id_: str):
        """Zip con lo que deja la corrida: lo pedido y los resultados, las salidas del motor y los perímetros por hora."""
        c = gestor.obtener(id_)
        if c.estado not in FINALES:
            raise HTTPException(409, "la corrida todavía está en marcha; se exporta cuando termina")
        memoria = io.BytesIO()
        with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as z:
            for nombre in ("corrida.json", "estado.json", "eventos.jsonl", "escenario_base.yaml"):
                if (c.carpeta / nombre).exists():
                    z.write(c.carpeta / nombre, f"{id_}/{nombre}")
            salida = c.carpeta / "salida"
            if salida.is_dir():
                for ruta in sorted(q for q in salida.rglob("*") if q.is_file()):
                    z.write(ruta, f"{id_}/salida/{ruta.relative_to(salida).as_posix()}")
            if c.listo and c.ultima_hora:
                figuras = []
                for h in range(int(c.ultima_hora["h"]) + 1):
                    f = huella.perimetro(c.carpeta, c.listo["grilla"], h)
                    if f:
                        figuras += f["features"]
                z.writestr(f"{id_}/perimetros_por_hora.geojson", json.dumps({"type": "FeatureCollection", "features": figuras}))
        return Response(memoria.getvalue(), media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{id_}.zip"'})

    @app.get("/api/comparacion")
    def comparacion(a: str, b: str, hora: float | None = None):
        ca, cb = gestor.obtener(a), gestor.obtener(b)
        r = huella.comparar(ca.carpeta, cb.carpeta, ca.listo["grilla"], cb.listo["grilla"], hora) if ca.listo and cb.listo else None
        if r is None:
            raise HTTPException(409, "las dos corridas tienen que tener huella y la misma grilla")
        return r | {"a": {"id": a, "motor": ca.motor}, "b": {"id": b, "motor": cb.motor}}

    # ------------------------------------------------------------------ capas de fondo
    @app.get("/api/capas")
    def lista_de_capas(evento: str | None = None):
        if evento is not None and evento not in datos.eventos_base():
            raise HTTPException(404, f"el evento {evento} no tiene datos en este clon")
        return {"capas": capas.lista(evento)}

    @app.get("/api/capas/{nombre}.png")
    def capa(nombre: str, evento: str | None = None):
        if evento is not None and evento not in datos.eventos_base():
            raise HTTPException(404, f"el evento {evento} no tiene datos en este clon")
        imagen = capas.png(nombre, evento)
        if imagen is None:
            raise HTTPException(404, f"no existe la capa {nombre}")
        return Response(imagen, media_type="image/png", headers={"Cache-Control": "max-age=3600"})

    @app.get("/api/vectores/{nombre}.geojson")
    def vector(nombre: str):
        texto = capas.geojson(nombre)
        if texto is None:
            raise HTTPException(404, f"no existe la capa {nombre}")
        return Response(texto, media_type="application/geo+json", headers={"Cache-Control": "max-age=3600"})

    # ------------------------------------------------------------------ páginas
    @app.get("/")
    def pantalla():
        return FileResponse(WEB / "index.html", media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-cache"})

    @app.get("/prueba")
    def pagina_de_prueba():
        return FileResponse(WEB / "prueba.html", media_type="text/html; charset=utf-8")

    app.mount("/web", StaticFiles(directory=WEB), name="web")

    return app


__all__ = ["crear_app", "ACTIVOS", "FINALES"]
