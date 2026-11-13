"""Pedidos HTTP del servidor local (fases F2 a F4).

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

  Datos que cambian (fase F4). Cada pedido que baja o prepara datos lanza un trabajo de datos (un proceso aparte, uno a la
  vez: si ya hay uno en marcha contesta 409) y devuelve 201 con {"trabajo": {...}} para seguirlo:
    GET  /api/datos                               tomas de meteorología e índices guardadas, eventos generados RT-…, el
                                                  trabajo en marcha (o el último), si hay Google Earth Engine, antigüedad
                                                  del pronóstico (horas) y de los índices (días) y avisos
    POST /api/datos/meteo                         {"fuente": "pronostico"}: baja el pronóstico de Open-Meteo
    POST /api/datos/meteo/archivo?nombre=x.csv    cuerpo: el CSV crudo (máx. 20 MB), formato de v3.x o de v4.0
    POST /api/datos/meteo/escenario               {desde_utc, horas, temp_c, hr_pct, viento_kmh, viento_dir_deg, precip_mm}:
                                                  valores fijos (modo escenario)
    POST /api/datos/indices                       {"fuente": "aws"|"gee", "fecha_corrida": "AAAA-MM-DD" (opcional)};
                                                  "gee" sin credenciales: 409 con el motivo
    POST /api/datos/indices/archivo?banda=ndvi|ndmi&nombre=x.tif   cuerpo: el GeoTIFF crudo (máx. 60 MB); queda en espera
                                                  (201, {"espera": {...}}; no lanza trabajo)
    POST /api/datos/indices/manual                {ventana: [d1, d2], ndmi_nir: "B08"|"B8A", descripcion}: carga los dos TIF
                                                  en espera
    POST /api/datos/evento                        {meteo?, indices?, nombre?}: arma un evento generado RT-… (por defecto con la
                                                  toma más nueva de cada tipo)
    DELETE /api/datos/eventos/<id>                borra un evento generado RT-… (no si una corrida en marcha lo usa)
    GET  /api/datos/trabajos/<id>                 estado de un trabajo de datos (progreso, resultado o error)
    GET  /api/datos/trabajos/<id>/eventos         avance en vivo (text/event-stream), como el de las corridas

    GET  /                                        la pantalla del simulador (app/web/index.html)
    GET  /prueba                                  página mínima de prueba de la fase F2

Seguridad: el servidor escucha solo en 127.0.0.1 y además rechaza los pedidos que no vengan de su propia página.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import io
import json
import re
import shutil
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import VERSION, capas, datos, huella
from . import trabajos as mod_trabajos
from .corridas import ACTIVOS, FINALES, MOTORES_REALES, Gestor, Rechazo, sha_congelado, escribir_json
from .trabajos import GestorDatos

# app/datos: el servidor solo usa las funciones que leen la caché (tomas(), eventos(), gee_disponible(), borrar()), que no
# cargan ningún motor. Lo que usa código de v3.1 corre en app/datos/proceso_datos.py.
from datos import evento_rt as d_evento_rt
from datos import indices as d_indices
from datos import meteo as d_meteo

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


class PedidoMeteo(BaseModel):
    fuente: str = "pronostico"


class PedidoEscenario(BaseModel):
    desde_utc: str
    horas: int = Field(ge=1, le=240)
    temp_c: float = Field(ge=-40, le=50)
    hr_pct: float = Field(ge=0, le=100)
    viento_kmh: float = Field(ge=0, le=216)          # 60 m/s, el tope del control de calidad
    viento_dir_deg: float = Field(ge=0, le=360)
    precip_mm: float = Field(default=0.0, ge=0, le=200)


class PedidoIndices(BaseModel):
    fuente: str
    fecha_corrida: str | None = None


class PedidoIndicesManual(BaseModel):
    ventana: list[str] = Field(min_length=2, max_length=2)
    ndmi_nir: str
    descripcion: str = Field(default="", max_length=2000)


class PedidoEvento(BaseModel):
    meteo: str | None = None
    indices: str | None = None
    nombre: str | None = Field(default=None, max_length=200)


MAX_CSV = 20 * 1024 * 1024
MAX_TIF = 60 * 1024 * 1024
HORAS_PRONOSTICO_VIEJO = 6               # el pronóstico se renueva a pedido o cada 6 h (D-E3-24, punto 5)
DIAS_INDICES_VIEJOS = 10                 # la ventana termina el día anterior a la corrida; con más días conviene renovar


def _nombre_de_archivo(nombre: str | None, extensiones: tuple[str, ...]) -> str:
    n = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(str(nombre or "")).name).strip("._")[:120]
    if not n or not n.lower().endswith(extensiones):
        raise HTTPException(422, f"nombre: un nombre de archivo terminado en {' o '.join(extensiones)}")
    return n


def _fecha(texto: str, campo: str) -> dt.date:
    try:
        return dt.date.fromisoformat(str(texto))
    except ValueError:
        raise HTTPException(422, f"{campo}: una fecha AAAA-MM-DD")


async def _cuerpo_crudo(request: Request, maximo: int) -> bytes:
    """El cuerpo del pedido sin pasar de `maximo` bytes (413 si pasa; 422 si está vacío)."""
    largo = request.headers.get("content-length")
    if largo and largo.isdigit() and int(largo) > maximo:
        raise HTTPException(413, f"el archivo pasa el máximo de {maximo // (1024 * 1024)} MB")
    partes, total = [], 0
    async for parte in request.stream():
        total += len(parte)
        if total > maximo:
            raise HTTPException(413, f"el archivo pasa el máximo de {maximo // (1024 * 1024)} MB")
        partes.append(parte)
    cuerpo = b"".join(partes)
    if not cuerpo:
        raise HTTPException(422, "el pedido no trae el archivo (va como cuerpo del pedido)")
    return cuerpo


def _horas_desde(texto: str | None, ahora: dt.datetime) -> float | None:
    try:
        t = dt.datetime.fromisoformat(str(texto).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return round((ahora - t.astimezone(dt.timezone.utc)).total_seconds() / 3600, 1)


def _sin_escenas(toma: dict) -> dict:
    """La toma sin la lista detallada de escenas (puede ser larga; la pantalla usa `n_escenas`)."""
    return {k: v for k, v in toma.items() if k != "escenas"}


def resumen_datos(gestor_datos: GestorDatos) -> dict:
    """Lo que muestra la zona de datos de la pantalla. Funciona con la caché vacía (sin red, primer arranque)."""
    ahora = dt.datetime.now(dt.timezone.utc)
    meteo = d_meteo.tomas()
    indices = [_sin_escenas(t) for t in d_indices.tomas()]
    eventos_rt = d_evento_rt.eventos()
    gee_ok, gee_motivo = d_indices.gee_disponible()
    avisos = []

    pronosticos = [t for t in meteo if str(t.get("id", "")).endswith("-pronostico")]
    ultimo_pron = pronosticos[0] if pronosticos else None
    pron_utc = (ultimo_pron.get("hora_de_la_toma_utc") or ultimo_pron.get("creada_utc")) if ultimo_pron else None
    pron_h = _horas_desde(pron_utc, ahora) if pron_utc else None
    if ultimo_pron is None:
        avisos.append("no hay ningún pronóstico guardado: actualizalo (hace falta red) o cargá la meteorología a mano")
    elif pron_h is not None and pron_h > HORAS_PRONOSTICO_VIEJO:
        avisos.append(f"el último pronóstico es de hace {pron_h:.0f} h: conviene actualizarlo")

    def ultima_fecha(t: dict) -> str | None:
        return t.get("ultima_fecha") or (t.get("ventana") or [None, None])[-1]

    fechas = sorted(f for f in (ultima_fecha(t) for t in indices) if f)
    ind_fecha = fechas[-1] if fechas else None
    ind_dias = None
    if ind_fecha:
        try:
            ind_dias = (ahora.date() - dt.date.fromisoformat(ind_fecha[:10])).days
        except ValueError:
            ind_fecha = None
    if not indices:
        avisos.append("no hay índices de vegetación guardados: actualizalos (hace falta red) o cargalos a mano")
    elif ind_dias is not None and ind_dias > DIAS_INDICES_VIEJOS:
        avisos.append(f"los índices más nuevos son de hace {ind_dias} días: conviene actualizarlos")
    if not eventos_rt:
        avisos.append("todavía no hay eventos de tiempo real: se ofrecen los eventos con ficha, rotulados EJEMPLO")

    t = gestor_datos.ultimo()
    return {"meteo": meteo, "indices": indices, "eventos_rt": eventos_rt, "trabajo": t.resumen() if t else None,
            "gee": {"disponible": gee_ok, "motivo": gee_motivo},
            "antiguedad": {"pronostico_utc": pron_utc, "pronostico_horas": pron_h, "indices_fecha": ind_fecha,
                           "indices_dias": ind_dias, "pronostico_viejo_horas": HORAS_PRONOSTICO_VIEJO,
                           "indices_viejos_dias": DIAS_INDICES_VIEJOS},
            "avisos": avisos}


def _canal(fuente, finales: set[str], request: Request, desde: int) -> StreamingResponse:
    """Avance en vivo de una corrida o de un trabajo de datos: sus eventos numerados (`n`), desde el siguiente al `desde`
    (o al del encabezado Last-Event-ID). Se cierra cuando `fuente` llega a un estado final."""
    ultimo = request.headers.get("last-event-id")
    n = int(ultimo) if ultimo and ultimo.isdigit() else max(0, desde)

    async def flujo():
        nonlocal n
        quieto = 0.0
        while True:
            nuevos = fuente.eventos[n:]
            for e in nuevos:
                yield f"id: {e['n']}\ndata: {json.dumps(e, ensure_ascii=False, default=str)}\n\n"
            n += len(nuevos)
            if fuente.estado in finales and n >= len(fuente.eventos):
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


def crear_app(carpeta_corridas: Path | None = None, permitir_simulado: bool = False, carpeta_trabajos: Path | None = None,
              guion_datos: Path | None = None) -> FastAPI:
    """`carpeta_trabajos` y `guion_datos` (el programa de los trabajos de datos) se cambian en las pruebas."""
    gestor = Gestor(carpeta_corridas, permitir_simulado=permitir_simulado)

    def al_terminar_trabajo(t) -> None:
        if t.tarea == "evento":
            datos.invalidar_eventos()

    gestor_datos = GestorDatos(carpeta_trabajos, guion_datos, al_terminar=al_terminar_trabajo)
    # eventos generados que quedaron a medio armar (proceso de datos cortado): no se ofrecen, se barren al arrancar
    if gestor_datos.en_marcha() is None:
        try:
            if d_evento_rt.barrer_incompletos():
                datos.invalidar_eventos()
        except OSError:
            pass

    @asynccontextmanager
    async def vida(_: FastAPI):
        yield
        await asyncio.to_thread(gestor_datos.cerrar)
        await asyncio.to_thread(gestor.cerrar)

    app = FastAPI(title="Simulador de incendios — San Luis", version=VERSION, lifespan=vida, docs_url=None, redoc_url=None,
                  openapi_url=None)
    app.state.gestor = gestor
    app.state.gestor_datos = gestor_datos

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
        return _canal(gestor.obtener(id_), FINALES, request, desde)

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
        # Un evento generado se puede borrar y volver a armar con el mismo id (RT-<fecha>-<n>): que el navegador no guarde
        # la imagen vieja.
        cache = "no-cache" if evento is not None and d_evento_rt.es_rt(evento) else "max-age=3600"
        return Response(imagen, media_type="image/png", headers={"Cache-Control": cache})

    @app.get("/api/vectores/{nombre}.geojson")
    def vector(nombre: str):
        texto = capas.geojson(nombre)
        if texto is None:
            raise HTTPException(404, f"no existe la capa {nombre}")
        return Response(texto, media_type="application/geo+json", headers={"Cache-Control": "max-age=3600"})

    # ------------------------------------------------------------------ datos que cambian (fase F4)
    def creado(t) -> JSONResponse:
        return JSONResponse({"trabajo": t.resumen()}, status_code=201)

    @app.get("/api/datos")
    def resumen_de_datos():
        return resumen_datos(gestor_datos)

    @app.post("/api/datos/meteo", status_code=201)
    def actualizar_pronostico(pedido: PedidoMeteo):
        if pedido.fuente != "pronostico":
            raise HTTPException(422, "fuente: 'pronostico' (para un CSV, /api/datos/meteo/archivo; para valores fijos, "
                                     "/api/datos/meteo/escenario)")
        return creado(gestor_datos.lanzar("pronostico", {}))

    @app.post("/api/datos/meteo/archivo", status_code=201)
    async def meteo_desde_archivo(request: Request, nombre: str = "meteo.csv"):
        n = _nombre_de_archivo(nombre, (".csv", ".txt"))
        cuerpo = await _cuerpo_crudo(request, MAX_CSV)
        t = await asyncio.to_thread(gestor_datos.lanzar, "meteo_manual", {"archivo": "entrada.csv", "nombre": n},
                                    {"entrada.csv": cuerpo})
        return creado(t)

    @app.post("/api/datos/meteo/escenario", status_code=201)
    def meteo_escenario(pedido: PedidoEscenario):
        try:
            desde = datos._utc(pedido.desde_utc)
        except ValueError as e:
            raise HTTPException(422, f"desde_utc: {e}")
        p = pedido.model_dump() | {"desde_utc": datos._iso(desde)}
        return creado(gestor_datos.lanzar("escenario", p))

    @app.post("/api/datos/indices", status_code=201)
    def actualizar_indices(pedido: PedidoIndices):
        if pedido.fuente not in ("aws", "gee"):
            raise HTTPException(422, "fuente: 'aws' o 'gee' (para cargar TIF, /api/datos/indices/archivo y /api/datos/indices/manual)")
        p = {}
        if pedido.fecha_corrida:
            p["fecha_corrida"] = _fecha(pedido.fecha_corrida, "fecha_corrida").isoformat()
        if pedido.fuente == "gee":
            ok, motivo = d_indices.gee_disponible()
            if not ok:
                raise HTTPException(409, f"Google Earth Engine no está disponible: {motivo}")
        return creado(gestor_datos.lanzar("indices_" + pedido.fuente, p))

    @app.post("/api/datos/indices/archivo", status_code=201)
    async def indice_desde_archivo(request: Request, banda: str, nombre: str | None = None):
        if banda not in ("ndvi", "ndmi"):
            raise HTTPException(422, "banda: 'ndvi' o 'ndmi'")
        n = _nombre_de_archivo(nombre or f"{banda}.tif", (".tif", ".tiff"))
        cuerpo = await _cuerpo_crudo(request, MAX_TIF)
        if cuerpo[:4] not in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"):
            raise HTTPException(422, f"{n}: no es un GeoTIFF")
        espera = gestor_datos.espera
        espera.mkdir(parents=True, exist_ok=True)
        (espera / f"{banda}.tif").write_bytes(cuerpo)
        escribir_json(espera / f"{banda}.json", {"nombre": n, "bytes": len(cuerpo), "subido_utc": datos._iso(dt.datetime.now(dt.timezone.utc))})
        return {"espera": _en_espera()}

    def _en_espera() -> dict:
        out = {}
        for banda in ("ndvi", "ndmi"):
            try:
                out[banda] = json.loads((gestor_datos.espera / f"{banda}.json").read_text(encoding="utf-8")) \
                    if (gestor_datos.espera / f"{banda}.tif").exists() else None
            except (OSError, json.JSONDecodeError):
                out[banda] = None
        return out

    @app.post("/api/datos/indices/manual", status_code=201)
    def indices_manuales(pedido: PedidoIndicesManual):
        d1, d2 = (_fecha(x, "ventana") for x in pedido.ventana)
        if d2 < d1:
            raise HTTPException(422, "ventana: el último día es anterior al primero")
        if pedido.ndmi_nir not in ("B08", "B8A"):
            raise HTTPException(422, "ndmi_nir: 'B08' o 'B8A' (la banda del infrarrojo cercano con la que se calculó el NDMI)")
        espera = _en_espera()
        faltan = [b for b, v in espera.items() if v is None]
        if faltan:
            raise HTTPException(409, f"falta subir {' y '.join(faltan)} (POST /api/datos/indices/archivo?banda=…)")
        # Si ya hay un trabajo en marcha, lanzar() contesta 409 antes de mover nada y los archivos siguen en espera.
        t = gestor_datos.lanzar("indices_manual", {
            "ndvi": "ndvi.tif", "ndmi": "ndmi.tif", "nombre_ndvi": espera["ndvi"]["nombre"],
            "nombre_ndmi": espera["ndmi"]["nombre"], "ventana": [d1.isoformat(), d2.isoformat()],
            "ndmi_nir": pedido.ndmi_nir, "descripcion": pedido.descripcion},
            {"ndvi.tif": gestor_datos.espera / "ndvi.tif", "ndmi.tif": gestor_datos.espera / "ndmi.tif"})
        shutil.rmtree(gestor_datos.espera, ignore_errors=True)
        return creado(t)

    @app.post("/api/datos/evento", status_code=201)
    def crear_evento(pedido: PedidoEvento):
        p = {}
        for clave, tomas, que in (("meteo", d_meteo.tomas(), "meteorología"), ("indices", d_indices.tomas(), "índices")):
            ids = [t["id"] for t in tomas if t.get("id")]
            elegido = getattr(pedido, clave)
            if elegido is None:
                if not ids:
                    raise HTTPException(409, f"no hay ninguna toma de {que} guardada: hay que bajarla o cargarla antes")
                elegido = ids[0]                     # las tomas vienen de la más nueva a la más vieja
            elif elegido not in ids:
                raise HTTPException(422, f"{clave}: no existe la toma {elegido!r}")
            p[clave] = elegido
        if pedido.nombre:
            p["nombre"] = pedido.nombre.strip()
        return creado(gestor_datos.lanzar("evento", p))

    @app.delete("/api/datos/eventos/{id_}")
    def borrar_evento(id_: str):
        if not d_evento_rt.es_rt(id_):
            raise HTTPException(422, f"{id_} no es un evento generado: solo se borran los RT-…")
        r = d_evento_rt.rutas(id_)
        if not (r["ficha_v40"].exists() or r["ficha_v31"].exists() or r["eventos"].exists() or r["combustibles"].exists()):
            raise HTTPException(404, f"no existe el evento {id_}")
        actual = gestor_datos.en_marcha()
        if actual is not None and actual.tarea == "evento":
            raise HTTPException(409, f"se está armando un evento generado ({actual.id}): esperá a que termine para borrar")
        for c in gestor.corridas.values():
            ev = c.pedido.get("evento") or (c.pedido.get("definicion") or {}).get("evento")
            if (c.estado in ACTIVOS or c.estado == "creada") and ev == id_:
                raise HTTPException(409, f"la corrida {c.id} está usando el evento {id_}: detenela o esperá a que termine")
        d_evento_rt.borrar(id_)
        datos.invalidar_eventos()
        return {"borrado": id_}

    @app.get("/api/datos/trabajos/{id_}")
    def trabajo(id_: str):
        return gestor_datos.obtener(id_).resumen()

    @app.get("/api/datos/trabajos/{id_}/eventos")
    async def eventos_del_trabajo(id_: str, request: Request, desde: int = 0):
        return _canal(gestor_datos.obtener(id_), mod_trabajos.FINALES, request, desde)

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
