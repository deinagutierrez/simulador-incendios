"""Intervenciones en el motor v3.1: cortafuegos y viento manual (fase F5, contrato 1.5; D-E3-28, puntos 7, 8, 10-12 y 14).

Lo usa `motor_v31.py` sobre la `Simulacion` ya creada, sin tocar ningún archivo de src/v3.1. El motor lee `barrera`,
`ancho_tab`, `bloq`, `estado` y `e.clase` en cada paso y `e.viento` en cada hora, así que lo que se cambia acá con la corrida en
pausa (dentro de `_tablas_hora`, antes de la hora) rige desde esa misma hora.

Matriz de barreras (punto 8). Las dos variantes de la app (`libre` y `libre_v2`) corren con las barreras apagadas. Para poder
recibir cortafuegos arrancan con una matriz VACÍA completa: `barrera` (filas, cols, vecindad) en cero, `ancho_tab` =
[0, 3, 6, 10, 15, 25], `bloq`, `cruces` y `bloqueos` (filas, cols) y `modo_cruce` según la configuración. Los cuatro
arreglos van juntos: con `usar_barreras` y los arreglos de forma (1, 1) el autómata leería fuera de rango sin aviso. Con la
matriz en cero el resultado es idéntico a barreras apagadas (comprobado; prueba en test/app/test_intervenciones_v31.py). Si
la variante ya trae barreras de caminos, se conservan y la tabla de anchos se amplía con los de los cortafuegos (los
códigos siguen ordenados por ancho).

Códigos de un trazo (punto 7): con la función REAL `preparar_barreras_enlaces` del motor, envuelta. La función solo acepta
geometrías propias como archivo del dominio (`barreras_extra`), siempre suma los caminos y escribe su resultado en el
directorio de derivados compartido. Por eso, en cada llamada:
- `INCENDIOS_SL_INPUT` se desvía a `<corrida>/intervenciones_v31/insumo/` (copias, no enlaces), donde está solo lo que la
  función lee: la capa de caminos del dominio, VACÍA, con su procedencia. La grilla sale de la ficha del dominio;
- `barreras_extra` es un GeoPackage único por llamada (`trazos/trazo_NNN.gpkg`, con `ancho_m`): la función reutiliza su
  producto si coincide la RUTA de `barreras_extra`, no el contenido;
- antes y después se comprueba que el producto quede dentro de la carpeta de la corrida: nunca se escribe en
  datos/inputSimulacion/barreras.
La grilla sale de la ficha del dominio (`grilla_dominio`), así que no hace falta copiar nada más. Tarda unos 4,7 s por trazo
en Las Lagunas (todo el dominio; medido el 2026-11-14). La prueba de los lectores (test/app/test_intervenciones_v31.py) la
compara con una copia de su núcleo que calcula los enlaces solo en una ventana alrededor del trazo: da lo mismo bit a bit en
unos 40 ms, pero solo si el raster fino se arma con la transformación de la grilla entera. Con el origen en la ventana (la
copia de 8 ms del pedido F5) GDAL redondea distinto y all_touched cambia píxeles cuando el trazo pasa justo por una esquina:
un trazo casi horizontal dio 12 enlaces de más.

Combinación: cada trazo da un código (0/1) por enlace; el 1 pasa al código de su ancho en `ancho_tab` y se combina con
`np.maximum` (por ancho, porque los códigos están ordenados por ancho).

Recorte (punto 10): se quitan los enlaces que llegan a una celda que ya no está en COMB en el momento de la pausa (ya
alcanzada por el fuego, o sin combustible: estos nunca se usan). Se conservan los que salen de celdas en llamas, que son los
que frenan el frente pegado a la línea. `recortada` si se quitaron enlaces hacia celdas ya alcanzadas o si parte del trazo
cae fuera del dominio; `rechazada` si no queda ningún enlace (y entonces no se toca nada).

Suelo mineral (punto 11): en las celdas que toca el trazo (rasterizado a 30 m con all_touched) que siguen en COMB, clase 0 y
estado NOCOMB, siempre junto con la barrera de enlace (una línea de clase 0 de una celda la cruzan los saltos de caballo).

Longitudes (punto 14): `longitud_dibujada_m` es la de la polilínea (la pone `intervenciones.validar_cortafuego`);
`longitud_aplicada_m`, la de la parte que queda dentro del dominio y fuera de las celdas ya alcanzadas por el fuego.

Viento manual (punto 5): desde la hora de la pausa se envuelve `e.viento` para que devuelva el campo de la velocidad y la
dirección pedidas (cambio de golpe en la hora en punto); "volver al pronóstico" restaura la función original. No sirve
editar `e.meteo`: el motor arma su tabla horaria una sola vez, al empezar. Con una fuente de viento por hora (campos
WindNinja horarios o IDW) se rechaza: esas fuentes no usan la velocidad ni la dirección de la serie. La humedad muerta es una
serie precalculada y no cambia.

Para la corrida offline (comparación B de E-E3-4) quedan en `<corrida>/intervenciones_v31/`:
- `cortafuego_NN.npz`: lo aplicado por cada cortafuego (índices planos de los enlaces en (filas, cols, vecindad), código y
  ancho, celdas a suelo mineral);
- `barreras_enlaces.npz`: la matriz final, con el formato de `cargar_barreras_enlaces` (`codigos`, `ancho_m`, `nombres`),
  que es la que lee el motor offline con `barreras: on`;
- `suelo_mineral.npz`: las celdas que pasaron a clase 0 (índices planos en (filas, cols));
- `viento_horario.csv`: las horas con viento manual (`time_utc`, `wind_speed_10m` en m/s, `wind_direction_10m`): con la
  fuente `escalar` de las configuraciones congeladas, el offline las toma de esas columnas del CSV meteorológico
  (y de `wind_speed_10m_vectorial` con la fuente `biblioteca`);
- `intervenciones.json`: el índice de lo aplicado, con los tiempos de cómputo.
`armar_espejo` arma con eso el espejo de datos/inputSimulacion para correr offline `correr_escenario.py` (ver la función).

En `datos` de la bitácora, cada cortafuego agrega `longitud_aplicada_m`, `enlaces` (enlaces aplicados), `enlaces_recortados`
(los que llegaban a celdas ya alcanzadas), `enlaces_sha256` (índices planos en (filas, cols, vecindad)), `celdas` y
`celdas_sha256` (celdas de origen de los enlaces aplicados, índices planos en (filas, cols)) y, con suelo mineral,
`celdas_mineral` y `celdas_mineral_sha256`. El viento manual agrega `vel_ms` (la velocidad que usa el motor, en m/s, con 6
decimales).
"""
from __future__ import annotations

import contextlib
import json
import os
import time
from pathlib import Path

import numpy as np

import intervenciones as iv

ANCHOS_TAB = (0.0, 3.0, 6.0, 10.0, 15.0, 25.0)   # código 0 = sin barrera; 1..5 = los anchos de los cortafuegos
CARPETA = "intervenciones_v31"
FACTOR_FINO = 4                                  # el de escenarios/v3.1/modelos/modelo_v2.yaml (barreras.factor_fino)
FUERA, NOCOMB, COMB = 255, 0, 1                  # estados del autómata (src/v3.1/.../simulation/automata.py)


# ------------------------------------------------------------------------------------------------ función real, envuelta
def _dentro_de(ruta: Path, raiz: Path) -> Path:
    ruta, raiz = Path(ruta).resolve(), Path(raiz).resolve()
    try:
        ruta.relative_to(raiz)
    except ValueError:
        raise RuntimeError(f"preparar_barreras_enlaces escribiría fuera de la carpeta de la corrida: {ruta}") from None
    return ruta


@contextlib.contextmanager
def _entradas_desviadas(insumo: Path):
    """`INCENDIOS_SL_INPUT` apuntando a `insumo` mientras dura el bloque (el proceso motor no tiene otros hilos que lo lean)."""
    antes = os.environ.get("INCENDIOS_SL_INPUT")
    os.environ["INCENDIOS_SL_INPUT"] = str(Path(insumo).resolve())
    try:
        yield
    finally:
        if antes is None:
            os.environ.pop("INCENDIOS_SL_INPUT", None)
        else:
            os.environ["INCENDIOS_SL_INPUT"] = antes


def _preparar_insumo(dom: dict, insumo: Path) -> None:
    """Deja en `insumo/infraestructura/` la capa de caminos del dominio VACÍA con su procedencia, para que
    `preparar_infraestructura` la tome como vigente y no la recorte de nuevo desde los datos crudos."""
    import geopandas as gpd
    import pandas as pd
    from incendios_sl.data import preparar_dominio as pdm
    from incendios_sl.procedencia import escribir_procedencia, producto_vigente

    dst = insumo / "infraestructura" / f"caminos_{dom['id']}.gpkg"
    g = pdm.grilla_dominio(dom).ampliar(1000)
    params = {"bbox": g.bounds, "crs": g.crs}                 # los mismos que arma preparar_infraestructura
    if dst.exists() and producto_vigente(dst, params):
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    vacia = gpd.GeoDataFrame({"clase": pd.Series([], dtype="object"), "superficie": pd.Series([], dtype="object")},
                             geometry=gpd.GeoSeries([], crs=g.crs))
    vacia.to_file(dst, layer="linestring", driver="GPKG", geometry_type="LineString")
    escribir_procedencia(dst, "capa de caminos vacía: solo los cortafuegos del usuario (app/motores/barreras_v31.py)",
                         params, [], extra={"entidades": 0, "capas": ["linestring"]})
    if not producto_vigente(dst, params):
        raise RuntimeError("la capa de caminos vacía no quedó vigente para preparar_infraestructura")


def enlaces_funcion_real(dom: dict, crs: str, vecindad: int, carpeta: Path, datos: dict, n: int) -> tuple[np.ndarray, float]:
    """Enlaces que corta un trazo, con la función real `preparar_barreras_enlaces` de v3.1 envuelta (ver el encabezado).

    `datos` es un cortafuego normalizado; `carpeta` es `<corrida>/intervenciones_v31`; `n` numera el archivo del trazo.
    Devuelve (índices planos ordenados de los enlaces con barrera en (filas, cols, vecindad), segundos)."""
    import geopandas as gpd
    from shapely.geometry import LineString
    from incendios_sl import config as cfgmod
    from incendios_sl.data import preparar_dominio as pdm

    t0 = time.perf_counter()
    carpeta = Path(carpeta)
    insumo = carpeta / "insumo"
    cfgmod.dir_entradas()                      # une los archivos partidos (una vez por proceso) en su lugar de siempre
    _preparar_insumo(dom, insumo)
    trazo = carpeta / "trazos" / f"trazo_{n:03d}.gpkg"
    trazo.parent.mkdir(parents=True, exist_ok=True)
    trazo.unlink(missing_ok=True)
    gpd.GeoDataFrame({"ancho_m": [float(datos["ancho_m"])]}, geometry=[LineString(datos["xy_5345"])],
                     crs=crs).to_file(trazo, driver="GPKG")
    solo_caminos = {"caminos": dom["infraestructura"]["caminos"]}             # viviendas y red eléctrica no hacen falta
    dom_trazo = {**dom, "infraestructura": solo_caminos, "barreras_extra": str(trazo.resolve())}
    with _entradas_desviadas(insumo):
        destino = _dentro_de(cfgmod.dir_derivados("barreras") / f"barreras_enlaces_{dom['id']}.npz", insumo)
        destino.unlink(missing_ok=True)       # además de la ruta única: nunca se reutiliza un producto anterior
        ruta = _dentro_de(pdm.preparar_barreras_enlaces(dom_trazo, {}, int(vecindad), FACTOR_FINO), insumo)
        codigos, ancho_m, _ = pdm.cargar_barreras_enlaces(ruta)
    for p in (ruta, ruta.with_name(ruta.name + ".json")):
        p.unlink(missing_ok=True)
    ancho_m = np.asarray(ancho_m, dtype="float64")
    idx = np.flatnonzero(codigos)
    if len(idx) and not (len(ancho_m) == 2 and ancho_m[1] == float(datos["ancho_m"]) and int(codigos.max()) == 1):
        raise RuntimeError(f"preparar_barreras_enlaces devolvió una tabla inesperada: {ancho_m.tolist()}")
    return idx.astype("int64"), time.perf_counter() - t0


# ------------------------------------------------------------------------------------------------ intervenciones
class IntervencionesV31:
    """Cortafuegos y viento manual sobre una `Simulacion` de v3.1. `aplicar` es el `control.aplicar` del conductor."""

    def __init__(self, sim, cfg, g, dom: dict, carpeta: Path):
        from incendios_sl.simulation.automata import estencil
        self.sim, self.cfg, self.g, self.dom = sim, cfg, g, dom
        self.dir = Path(carpeta) / CARPETA
        self.vec = int(cfg.vecindad)
        self.dy, self.dx, _, _ = estencil(self.vec, g.res)
        self.forma = tuple(sim.estado.shape)
        self.codigo: dict[float, int] = {}
        self.indice: list[dict] = []
        self.mineral = np.zeros(self.forma, dtype=bool)
        self.n_trazos = 0                          # llamadas a la función real (numeran los GeoPackage)
        self.n_cortafuegos = 0                     # cortafuegos aplicados (numeran los npz)
        self._viento_original = None               # la función de viento del pronóstico, mientras rige uno manual
        self.viento_horas: list[dict] = []

    # ---------------------------------------------------------------- matriz de barreras
    def habilitar_barreras(self) -> None:
        """Matriz de barreras vacía completa (o la de caminos, con la tabla de anchos ampliada). Ver el encabezado."""
        s, forma = self.sim, self.forma
        if s.usar_barreras:
            viejo = np.asarray(s.ancho_tab, dtype="float64")
            if viejo[0] != 0.0 or np.any(np.diff(viejo) <= 0):
                raise ValueError(f"la tabla de anchos de las barreras no está ordenada: {viejo.tolist()}")
            tabla = np.array(sorted(set(viejo.tolist()) | set(ANCHOS_TAB)), dtype="float64")
            if len(tabla) > 255:
                raise ValueError("demasiados anchos de barrera para códigos uint8")
            nuevo = np.searchsorted(tabla, viejo).astype("uint8")
            if not np.array_equal(nuevo, np.arange(len(viejo))):
                s.barrera = np.ascontiguousarray(nuevo[s.barrera])
            s.ancho_tab = tabla
        else:
            s.barrera = np.zeros(forma + (self.vec,), dtype=np.uint8)
            s.ancho_tab = np.array(ANCHOS_TAB, dtype="float64")
            s.bloq = np.zeros(forma, dtype=np.uint16)
            s.cruces = np.zeros(forma, dtype=np.uint16)
            s.bloqueos = np.zeros(forma, dtype=np.uint16)
            s.modo_cruce = 2 if self.cfg.cruce_modo == "umbral" else 1
            s.usar_barreras = True                 # al final: nunca con los arreglos de forma (1, 1)
        if s.barrera.shape != forma + (self.vec,) or s.bloq.shape != forma or not s.barrera.flags["C_CONTIGUOUS"]:
            raise RuntimeError("la matriz de barreras no quedó completa")
        self.codigo = {float(a): int(i) for i, a in enumerate(s.ancho_tab)}

    # ---------------------------------------------------------------- cortafuego
    def _celdas_del_trazo(self, xy) -> np.ndarray:
        from rasterio import features
        from rasterio.transform import Affine
        from shapely.geometry import LineString
        g = self.g
        return features.rasterize([(LineString(xy).__geo_interface__, 1)], out_shape=self.forma,
                                  transform=Affine(g.res, 0.0, g.xmin, 0.0, -g.res, g.ymax), fill=0, all_touched=True,
                                  dtype="uint8").astype(bool)

    def _longitud_aplicada(self, xy, excluidas: np.ndarray) -> tuple[float, float]:
        """(longitud dentro de la grilla y fuera de las celdas excluidas, longitud fuera de la grilla), en m."""
        from shapely.geometry import LineString, box
        from shapely.ops import unary_union
        g = self.g
        nfil, ncol = self.forma
        linea = LineString(xy)
        adentro = linea.intersection(box(g.xmin, g.ymax - nfil * g.res, g.xmin + ncol * g.res, g.ymax))
        afuera = linea.length - adentro.length
        ff, cc = np.nonzero(excluidas)
        if len(ff):
            cuadros = unary_union([box(g.xmin + c * g.res, g.ymax - (f + 1) * g.res, g.xmin + (c + 1) * g.res, g.ymax - f * g.res)
                                   for f, c in zip(ff.tolist(), cc.tolist())])
            adentro = adentro.difference(cuadros)
        return float(adentro.length), float(afuera)

    def cortafuego(self, datos: dict, t: float, inicial: bool = False) -> dict:
        """Aplica un cortafuego normalizado con la corrida en `t` (minutos). Devuelve lo que espera `control.aplicar`."""
        s = self.sim
        ancho = float(datos["ancho_m"])
        if ancho not in self.codigo:
            raise ValueError(f"ancho {ancho:g} m sin código en la tabla de barreras")
        self.n_trazos += 1
        idx, segundos = enlaces_funcion_real(self.dom, self.g.crs, self.vec, self.dir, datos, self.n_trazos)
        fila, resto = np.divmod(idx, self.forma[1] * self.vec)
        col, k = np.divmod(resto, self.vec)
        fd, cd = fila + self.dy[k], col + self.dx[k]                 # la función solo marca enlaces con destino en la grilla
        estado_destino = s.estado[fd, cd]
        alcanzado = np.isfinite(s.t_arr[fd, cd])
        queda = estado_destino == COMB
        aplicados = idx[queda]
        tocadas = self._celdas_del_trazo(datos["xy_5345"])
        largo, afuera = self._longitud_aplicada(datos["xy_5345"], tocadas & (np.isfinite(s.t_arr) | (s.estado == FUERA)))
        if len(aplicados) == 0:
            motivo = ("el trazo cae fuera del dominio" if len(idx) == 0 else
                      "todo el trazo cae sobre celdas ya alcanzadas por el fuego o sin combustible")
            return {"estado": "rechazada", "t_vigor_min": t, "motivo": motivo, "datos": {}}

        # desde acá se cambia el motor
        codigo = self.codigo[ancho]
        plana = s.barrera.reshape(-1)                                # vista: la matriz es C-contigua
        plana[aplicados] = np.maximum(plana[aplicados], np.uint8(codigo))
        mineral = np.zeros(0, dtype="int64")
        if datos.get("suelo_mineral"):
            m = tocadas & (s.estado == COMB)
            s.e.clase[m] = 0
            s.estado[m] = NOCOMB
            self.mineral |= m
            mineral = np.flatnonzero(m).astype("int64")

        recortados = int(np.count_nonzero(~queda & alcanzado))
        motivos = []
        if recortados:
            motivos.append(f"se quitaron {recortados} enlaces que llegan a celdas ya alcanzadas por el fuego")
        if afuera > 0.01:
            motivos.append(f"{afuera:.0f} m del trazo caen fuera de la grilla del dominio")
        celdas = np.unique(aplicados // self.vec)                    # celdas de origen de los enlaces aplicados
        extra = {"longitud_aplicada_m": round(largo, 2), "enlaces": int(len(aplicados)), "enlaces_recortados": recortados,
                 "enlaces_sha256": iv.sha256_indices(aplicados), "celdas": int(len(celdas)),
                 "celdas_sha256": iv.sha256_indices(celdas)}
        if datos.get("suelo_mineral"):
            extra.update(celdas_mineral=int(len(mineral)), celdas_mineral_sha256=iv.sha256_indices(mineral))

        self.n_cortafuegos += 1
        archivo = f"cortafuego_{self.n_cortafuegos:02d}.npz"
        self.dir.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(self.dir / archivo, enlaces=aplicados, codigo=np.uint8(codigo), ancho_m=ancho,
                            forma=np.array(self.forma + (self.vec,), dtype="int64"), celdas_mineral=mineral,
                            t_sim_min=float(t), xy_5345=np.array(datos["xy_5345"], dtype="float64"))
        self.indice.append({"tipo": "cortafuego", "inicial": bool(inicial), "t_sim_min": round(float(t), 3),
                            "archivo": archivo, "trazo": f"trazos/trazo_{self.n_trazos:03d}.gpkg",
                            "segundos_funcion_real": round(segundos, 2), **{**datos, **extra}})
        print(f"cortafuego {self.n_cortafuegos} en t={t:g} min: {extra['enlaces']} enlaces ({recortados} recortados), "
              f"{extra['longitud_aplicada_m']} m aplicados; función real {segundos:.1f} s", flush=True)
        return {"estado": "recortada" if motivos else "aceptada", "t_vigor_min": t, "motivo": "; ".join(motivos),
                "datos": extra}

    # ---------------------------------------------------------------- viento manual
    def viento(self, datos: dict, t: float) -> dict:
        s = self.sim
        if s.e.viento is None:
            return {"estado": "rechazada", "t_vigor_min": t, "motivo": "esta corrida no tiene viento", "datos": {}}
        if datos.get("modo") == "pronostico":
            if self._viento_original is None:
                return {"estado": "rechazada", "t_vigor_min": t, "motivo": "el viento ya es el del pronóstico", "datos": {}}
            s.e.viento, self._viento_original = self._viento_original, None
            self.indice.append({"tipo": "viento_manual", "t_sim_min": round(float(t), 3), **datos})
            return {"estado": "aceptada", "t_vigor_min": t, "motivo": "", "datos": {}}
        original = self._viento_original or s.e.viento
        if getattr(original, "por_hora", False):
            return {"estado": "rechazada", "t_vigor_min": t, "datos": {},
                    "motivo": "con viento por hora (campos horarios o IDW) el viento manual no se aplica: esas fuentes no "
                              "usan la velocidad ni la dirección de la serie"}
        # la serie meteorológica de v3.1 está en m/s; con 6 decimales el valor pasa sin cambios por el CSV de la corrida
        # offline (cualquier lector de CSV lo lee exacto)
        vel_ms = round(float(datos["vel_kmh"]) / 3.6, 6)
        direccion = float(datos["dir_desde"])
        registro = self.viento_horas
        t_inicio = s.e.t_inicio_utc

        def viento_manual(vel, dir_desde, hora=None, _original=original):
            import pandas as pd
            registro.append({"time_utc": str((t_inicio + pd.Timedelta(seconds=s.t)).floor("h")),
                             "wind_speed_10m": vel_ms, "wind_direction_10m": direccion})
            return _original(vel_ms, direccion)

        s.e.viento = viento_manual
        self._viento_original = original
        self.indice.append({"tipo": "viento_manual", "t_sim_min": round(float(t), 3), **datos, "vel_ms": vel_ms})
        return {"estado": "aceptada", "t_vigor_min": t, "motivo": "", "datos": {"vel_ms": vel_ms}}

    # ---------------------------------------------------------------- para el conductor
    def aplicar(self, entrada: dict, t: float) -> dict:
        if entrada["tipo"] == "cortafuego":
            return self.cortafuego(entrada["datos"], t)
        if entrada["tipo"] == "viento_manual":
            return self.viento(entrada["datos"], t)
        return {"estado": "rechazada", "t_vigor_min": t, "motivo": f"tipo {entrada['tipo']!r} no admitido", "datos": {}}

    def cerrar(self) -> dict | None:
        """Escribe lo que necesita la corrida offline (ver el encabezado) y devuelve el resumen para `resultados`."""
        if not self.indice:
            return None
        s = self.sim
        self.dir.mkdir(parents=True, exist_ok=True)
        archivos = []
        if self.n_cortafuegos:
            nombres = {str(i): (["cortafuego"] if float(a) in ANCHOS_TAB else ["camino"])
                       for i, a in enumerate(s.ancho_tab) if i}
            np.savez_compressed(self.dir / "barreras_enlaces.npz", codigos=s.barrera, ancho_m=np.asarray(s.ancho_tab, "float64"),
                                nombres=json.dumps(nombres, ensure_ascii=False))
            archivos.append("barreras_enlaces.npz")
            if self.mineral.any():
                np.savez_compressed(self.dir / "suelo_mineral.npz", celdas=np.flatnonzero(self.mineral).astype("int64"),
                                    forma=np.array(self.forma, dtype="int64"))
                archivos.append("suelo_mineral.npz")
        if self.viento_horas:
            import pandas as pd
            df = pd.DataFrame(self.viento_horas).drop_duplicates("time_utc", keep="last")
            df["wind_speed_10m_vectorial"] = df["wind_speed_10m"]
            df.to_csv(self.dir / "viento_horario.csv", index=False)
            archivos.append("viento_horario.csv")
        (self.dir / "intervenciones.json").write_text(json.dumps(self.indice, indent=1, ensure_ascii=False) + "\n",
                                                      encoding="utf-8")
        archivos.append("intervenciones.json")
        return {"carpeta": CARPETA, "cortafuegos": self.n_cortafuegos, "horas_viento_manual": len(self.viento_horas),
                "celdas_suelo_mineral": int(self.mineral.sum()),
                "enlaces_con_barrera": int(np.count_nonzero(s.barrera)), "archivos": archivos}


# ------------------------------------------------------------------------------------------------ corrida offline
# Lo que lee `cargar_entradas_evento` de v3.1 para un evento (subcarpetas de datos/inputSimulacion). El resto (sim_v4,
# infraestructura, catálogo…) no hace falta para correr sin validar.
_ESPEJO = ("grilla", "dem", "combustibles", "eventos", "meteo", "viento")


def _enlazar_o_copiar(src: Path, dst: Path) -> str:
    """Enlace duro (sin costo, mismo disco) o, si no se puede (otro disco, sistema sin enlaces), copia."""
    import shutil
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
        return "enlace"
    except OSError:
        shutil.copy2(src, dst)
        return "copia"


def armar_espejo(corrida: Path, destino: Path, evento: str, id_dominio: str, origen: Path | None = None) -> dict:
    """Espejo de `datos/inputSimulacion` para correr offline (comparación B de E-E3-4) lo que aplicó una corrida de la app.

    Se corre `src/v3.1/scripts/correr_escenario.py` con `INCENDIOS_SL_INPUT=<destino>` y el YAML de la corrida
    (`escenario_base.yaml`) con `barreras: on` si hubo cortafuegos. En el espejo:
    - `barreras/barreras_enlaces_<dominio>.npz` es la matriz final de la corrida (`intervenciones_v31/barreras_enlaces.npz`);
    - la clase de combustible lleva 0 en las celdas a suelo mineral (`suelo_mineral.npz`);
    - la serie meteorológica del dominio lleva el viento manual en sus horas (`viento_horario.csv`);
    - todo lo demás son enlaces duros a los archivos originales (o copias, si el destino está en otro disco).
    Los archivos editados se escriben siempre como archivos NUEVOS (nunca a través de un enlace): el original no cambia.
    El motor offline solo lee de este espejo cuando no valida (`validar: false`). No usar el espejo para otra cosa.

    Devuelve `{"barreras": bool, "reemplazados": [...], "enlaces": n, "copias": n}`."""
    import pandas as pd
    origen = Path(origen) if origen else Path(__file__).resolve().parents[2] / "datos" / "inputSimulacion"
    origen, destino = origen.resolve(), Path(destino).resolve()
    if destino == origen or origen in destino.parents or destino in origen.parents:
        raise ValueError("el espejo tiene que estar fuera de los datos originales")
    if destino.exists() and any(destino.iterdir()):
        raise ValueError(f"el destino del espejo no está vacío: {destino}")
    interv = Path(corrida) / CARPETA
    barreras = interv / "barreras_enlaces.npz"
    mineral = interv / "suelo_mineral.npz"
    viento = interv / "viento_horario.csv"
    rel_clase = Path("combustibles") / evento / f"combustible_clase_{evento}.tif"
    metas = sorted((origen / "meteo").glob(f"{evento}_*_dominio.csv"))
    if not metas:
        raise FileNotFoundError(f"no hay serie meteorológica del dominio para {evento}")
    rel_meteo = metas[-1].relative_to(origen)                 # la que elige ruta_producto (la última en orden)
    reemplazar = set()
    if mineral.exists():
        reemplazar.add(rel_clase)
    if viento.exists():
        reemplazar.add(rel_meteo)
    cuenta = {"enlace": 0, "copia": 0}
    for sub in _ESPEJO:
        for src in sorted((origen / sub).rglob("*")):
            rel = src.relative_to(origen)
            if not src.is_file() or ".part" in src.suffix or rel in reemplazar:
                continue
            if sub in ("combustibles", "eventos") and len(rel.parts) > 2 and rel.parts[1] != evento:
                continue
            if sub == "meteo" and not src.name.startswith(evento):
                continue
            cuenta[_enlazar_o_copiar(src, destino / rel)] += 1

    hechos = []
    if barreras.exists():
        dst = destino / "barreras" / f"barreras_enlaces_{id_dominio}.npz"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(barreras.read_bytes())
        hechos.append(str(dst.relative_to(destino)))
    if mineral.exists():
        import rasterio
        z = np.load(mineral)
        with rasterio.open(origen / rel_clase) as f:
            perfil, clase = f.profile, f.read(1)
        if tuple(int(v) for v in z["forma"]) != clase.shape:
            raise ValueError("suelo_mineral.npz no tiene la forma de la grilla del evento")
        clase.reshape(-1)[z["celdas"]] = 0
        dst = destino / rel_clase
        dst.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(dst, "w", **perfil) as f:
            f.write(clase, 1)
        hechos.append(str(rel_clase))
    if viento.exists():
        # edición de texto: las demás filas y columnas quedan byte a byte como en el original (sin pasar por pandas)
        lineas = (origen / rel_meteo).read_text(encoding="utf-8").splitlines()
        cab = lineas[0].split(",")
        col = {c: cab.index(c) for c in ("time_utc", "wind_speed_10m", "wind_speed_10m_vectorial", "wind_direction_10m")}
        fila_de = {pd.Timestamp(x.split(",")[col["time_utc"]]): i for i, x in enumerate(lineas[1:], start=1)}
        for _, h in pd.read_csv(viento, float_precision="round_trip").iterrows():
            i = fila_de.get(pd.Timestamp(h["time_utc"]))
            if i is None:
                raise ValueError(f"la hora {h['time_utc']} no está en la serie meteorológica")
            campos = lineas[i].split(",")
            for c in ("wind_speed_10m", "wind_speed_10m_vectorial", "wind_direction_10m"):
                campos[col[c]] = repr(float(h[c]))
            lineas[i] = ",".join(campos)
        dst = destino / rel_meteo
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text("\n".join(lineas) + "\n", encoding="utf-8", newline="\n")
        hechos.append(str(rel_meteo))
    return {"barreras": barreras.exists(), "reemplazados": hechos, "enlaces": cuenta["enlace"], "copias": cuenta["copia"]}
