"""Evento generado `RT-<fecha>-<n>`: una toma de meteorología y una de índices escritas como un evento con ficha, para que
los cargadores congelados de los dos motores lo corran sin cambios (plan §2.2; D-E3-24, punto 13).

Dónde queda cada cosa (git y la comprobación del congelado ignoran los nombres `RT-*`, F0):

| Archivo | Lo lee |
|---|---|
| `escenarios/v3.1/eventos/RT-….yaml`, `escenarios/v4.0/eventos/RT-….yaml` (la misma ficha) | `cargar_evento` de cada motor |
| `datos/inputSimulacion/meteo/RT-…_<fuente>_dominio.csv` | v3.1 `cargar_entradas_evento`; v4.0 `ruta_meteo_v3` |
| `datos/inputSimulacion/combustibles/RT-…/` (clase, curado, calidad, `ndvi_30m`, `ndmi_30m`) | v3.1; v4.0 toma `ndvi_30m` y `ndmi_30m` como `indices_mes_evento` |
| `datos/inputSimulacion/eventos/RT-…/humedad_muerto_RT-….csv` | v3.1 |
| `datos/inputSimulacion/eventos/RT-…/insumos_RT-….json` | el simulador: procedencia de todo lo anterior, para `corrida.json` |

Los productos de v3.1 (mapa de 7 clases y humedad muerta) se arman con sus funciones congeladas, igual que
`scripts/preparar_evento.py`, así que esto corre en el proceso de datos con el camino de v3.1. v4.0 arma su combustible
SB40 (regla 3.3b, cobertura del año anterior y verano del año) al correr, en su propia caché.
"""
from __future__ import annotations

import datetime as dt
import re
import shutil
from pathlib import Path

import pandas as pd
import yaml

from . import comun

HUSO_LOCAL = dt.timezone(dt.timedelta(hours=-3))      # San Luis, sin horario de verano
PATRON = re.compile(r"^RT-(\d{8})-(\d+)$")


def es_rt(id_evento: str) -> bool:
    return bool(PATRON.match(str(id_evento)))


def rutas(id_: str) -> dict[str, Path]:
    E, D = comun.REPO / "escenarios", comun.ENTRADAS
    return {"ficha_v31": E / "v3.1" / "eventos" / f"{id_}.yaml", "ficha_v40": E / "v4.0" / "eventos" / f"{id_}.yaml",
            "meteo_dir": D / "meteo", "combustibles": D / "combustibles" / id_, "eventos": D / "eventos" / id_,
            "insumos": D / "eventos" / id_ / f"insumos_{id_}.json"}


def nuevo_id(fecha: dt.date) -> str:
    usados = {int(m.group(2)) for p in (comun.REPO / "escenarios" / "v4.0" / "eventos").glob(f"RT-{fecha:%Y%m%d}-*.yaml")
              if (m := PATRON.match(p.stem))}
    return f"RT-{fecha:%Y%m%d}-{max(usados, default=0) + 1}"


def anio_cobertura(fecha: dt.date) -> tuple[int, str | None]:
    """Cobertura MapBiomas del año anterior (regla de los dos motores); si todavía no está publicada, la última que haya."""
    dom = comun.dominio_yaml()["id"]
    hay = sorted(int(m.group(1)) for p in (comun.ENTRADAS / "cobertura").glob(f"cobertura_mapbiomas_col3_*_{dom}.tif")
                 if (m := re.search(r"col3_(\d{4})_", p.name)))
    pedido = fecha.year - 1
    if pedido in hay:
        return pedido, None
    previos = [a for a in hay if a < pedido]
    if not previos:
        raise FileNotFoundError(f"no hay cobertura MapBiomas de {pedido} ni de años anteriores")
    return previos[-1], f"no hay cobertura MapBiomas de {pedido}: se usa la de {previos[-1]}"


def _hora_inicio(meteo: dict) -> pd.Timestamp:
    """Hora de ignición por defecto (el usuario la cambia al crear la corrida): la de la toma de pronóstico, el inicio
    del escenario o, en un CSV manual, cinco días después del comienzo (para la humedad muerta), dentro de la serie."""
    desde, hasta = pd.Timestamp(meteo["desde_utc"]), pd.Timestamp(meteo["hasta_utc"])
    t = pd.Timestamp(meteo.get("hora_de_la_toma_utc") or meteo.get("inicio_escenario_utc") or (desde + pd.Timedelta(days=5)))
    return min(max(t, desde), hasta - pd.Timedelta(hours=1))


def ficha(id_: str, meteo: dict, indices: dict, t0: pd.Timestamp, cobertura: int, nombre: str | None) -> dict:
    g = comun.grilla_dominio()
    from pyproj import Transformer
    lon, lat = Transformer.from_crs(g.crs, "EPSG:4326", always_xy=True).transform((g.xmin + g.xmax) / 2, (g.ymin + g.ymax) / 2)
    fecha_local = t0.tz_convert(HUSO_LOCAL).date()
    return {
        "id": id_,
        "nombre": nombre or f"Tiempo real {fecha_local:%d/%m/%Y} ({meteo['rotulo']}; {indices['rotulo']})",
        "dominio": comun.dominio_yaml()["id"],
        "tipo": "tiempo_real",
        "generado_por": "simulador interactivo (app/datos/evento_rt.py)",
        "referencia_espacial": None,            # sin cicatriz: no es un incendio histórico
        "inicio": {"fecha_local": f"{fecha_local}", "hora_utc_hipotesis": [f"{t0:%Y-%m-%dT%H:%M:%SZ}"]},
        "fin": {"fin_simulacion_utc": meteo["hasta_utc"], "evaluacion_utc": []},
        "ignicion": {"fuente": "centro del dominio; el simulador la reemplaza por el clic del usuario",
                     "puntos": [{"nombre": "centro del dominio", "lon": round(float(lon), 5), "lat": round(float(lat), 5)}]},
        "meteorologia": {"fuente": meteo["fuente"], "modelo": meteo.get("modelo", meteo["rotulo"]), "toma": meteo["id"],
                         "inicio_utc": meteo["desde_utc"], "fin_utc": meteo["hasta_utc"]},
        "indices": {"fuente": indices["fuente"], "toma": indices["id"], "ventana": indices.get("ventana"),
                    "ndmi_nir": indices.get("ndmi_nir")},
        "cobertura_anio": int(cobertura),
        "notas": ["Evento generado: no tiene cicatriz ni focos; no se valida contra observaciones."],
    }


def crear(meteo: dict, indices: dict, nombre: str | None = None, aviso=print) -> dict:
    """Arma el evento con la toma de meteorología `meteo` y la de índices `indices` (sus `info.json`). Devuelve el resumen
    que guarda en `insumos_RT-….json`."""
    from incendios_sl import config as cfgmod                         # v3.1 (proceso de datos)
    from incendios_sl.data import preparar_dominio as pdm
    from incendios_sl.fuels.clasificacion import generar_mapa_combustibles
    from incendios_sl.fuels.humedad import serie_humedad

    t0 = _hora_inicio(meteo)
    fecha_local = t0.tz_convert(HUSO_LOCAL).date()
    id_ = nuevo_id(fecha_local)
    r = rutas(id_)
    cobertura, aviso_cob = anio_cobertura(fecha_local)
    avisos = [a for a in (aviso_cob,) if a]
    try:
        # 1. ficha (la misma para los dos motores)
        f = ficha(id_, meteo, indices, t0, cobertura, nombre)
        texto = "# Evento generado por el simulador interactivo. No editar: se regenera.\n" + \
                yaml.safe_dump(f, allow_unicode=True, sort_keys=False)
        for k in ("ficha_v31", "ficha_v40"):
            r[k].write_text(texto, encoding="utf-8")
        # 2. meteorología, con el nombre que buscan los dos cargadores
        etiqueta = re.sub(r"[^A-Za-z0-9]+", "_", str(meteo.get("modelo") or meteo["id"].split("-")[2])).strip("_")
        dmeteo = comun.dir_cache("meteo") / meteo["id"]
        destino_meteo = r["meteo_dir"] / f"{id_}_{etiqueta}_dominio.csv"
        shutil.copy(dmeteo / meteo["archivo"], destino_meteo)
        # 3. combustible y humedad de v3.1, con sus funciones
        aviso("mapa de combustible de v3.1 (7 clases) con la cobertura y los índices")
        ev = cfgmod.cargar_evento(id_)
        dom = cfgmod.cargar_dominio(ev["dominio"])
        g = pdm.grilla_dominio(dom)
        p_cob = cfgmod.dir_entradas() / "cobertura" / f"cobertura_mapbiomas_col3_{cobertura}_{dom['id']}.tif"
        dind = comun.dir_cache("indices") / indices["id"]
        comb = generar_mapa_combustibles(dom, ev, g, p_cob, dind / indices["ndvi"], dind / indices["ndmi"])
        aviso("humedad del combustible muerto (v3.1)")
        r["eventos"].mkdir(parents=True, exist_ok=True)
        dominio = pd.read_csv(destino_meteo, parse_dates=["time_utc"])
        h = serie_humedad(dominio, cfgmod.cargar_modelo()["humedad"])
        p_hum = r["eventos"] / f"humedad_muerto_{id_}.csv"
        h.to_csv(p_hum, index=False)
        # 4. procedencia
        verano = [comun.ENTRADAS / "sim_v4" / "dinamicos" / "indices" / f"NDVI_NDMI_{fecha_local.year if fecha_local.month > 3 else fecha_local.year - 1}_{m:02d}.tif"
                  for m in (1, 2, 3)]
        faltan = [p.name for p in verano if not p.exists()]
        if faltan:
            avisos.append("faltan compuestos de verano para v4.0: " + ", ".join(faltan) + " (v4.0 usará su respaldo y lo anota)")
        rotulos = [meteo["rotulo"], indices["rotulo"]]
        if indices.get("en_prueba"):
            avisos.append("índices por AWS en prueba: la vía se habilita cuando se cumpla E-E3-2")
        archivos = {"ficha": r["ficha_v40"], "meteo": destino_meteo, "humedad_muerto": p_hum,
                    **{k: Path(comb[k]) for k in ("clase", "curado", "calidad", "ndvi30", "ndmi30")}}
        resumen = {"id": id_, "nombre": f["nombre"], "creado_utc": comun.ahora_utc(), "t_inicio_por_defecto_utc": f"{t0:%Y-%m-%dT%H:%M:%SZ}",
                   "meteo": meteo, "indices": {k: v for k, v in indices.items() if k != "escenas"},
                   "cobertura_anio": cobertura,
                   "verano_v40": {"archivos": [p.name for p in verano if p.exists()], "faltan": faltan,
                                  "sha256": {p.name: comun.sha256(p) for p in verano if p.exists()}},
                   "archivos": {k: Path(v).relative_to(comun.REPO).as_posix() for k, v in archivos.items()},
                   "sha256": {k: comun.sha256(Path(v)) for k, v in archivos.items()},
                   "rotulos": rotulos, "avisos": avisos}
        comun.escribir_json(r["insumos"], resumen)
        return resumen
    except Exception:
        borrar(id_)
        raise


def borrar(id_: str) -> None:
    """Quita todo lo del evento generado (no toca nada que no empiece con RT-)."""
    if not es_rt(id_):
        raise ValueError(f"{id_} no es un evento generado")
    r = rutas(id_)
    for k in ("ficha_v31", "ficha_v40"):
        r[k].unlink(missing_ok=True)
    for p in r["meteo_dir"].glob(f"{id_}_*"):
        p.unlink(missing_ok=True)
    for k in ("combustibles", "eventos"):
        shutil.rmtree(r[k], ignore_errors=True)
    shutil.rmtree(comun.REPO / "datos" / "procesados" / "v4.0" / id_, ignore_errors=True)


def barrer_incompletos() -> list[str]:
    """Borra los eventos generados que quedaron a medio armar (sin `insumos_RT-….json`), por ejemplo si se cortó el
    proceso de datos. El servidor lo llama al arrancar, cuando no hay ningún trabajo de datos en marcha."""
    E, D = comun.REPO / "escenarios", comun.ENTRADAS
    candidatos = {p.stem for v in ("v3.1", "v4.0") for p in (E / v / "eventos").glob("RT-*.yaml")}
    candidatos |= {p.name for k in ("eventos", "combustibles") for p in (D / k).glob("RT-*") if p.is_dir()}
    borrados = []
    for id_ in sorted(c for c in candidatos if es_rt(c)):
        if not rutas(id_)["insumos"].exists():
            borrar(id_)
            borrados.append(id_)
    return borrados


def eventos() -> list[dict]:
    out = []
    for p in sorted((comun.ENTRADAS / "eventos").glob("RT-*/insumos_RT-*.json"), reverse=True):
        d = comun.leer_json(p)
        if d and es_rt(d.get("id", "")):
            out.append(d)
    return out
