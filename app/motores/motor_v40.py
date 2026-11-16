"""Conduce al motor v4.0 (SIM) sin modificarlo.

Sigue los mismos pasos que src/v4.0/scripts/correr_escenario.py (traducir, ejecutar, registrar, resumir) y solo agrega
un punto de control: una subclase de `Automata` que, en cada hora simulada en punto y antes de avanzar, avisa el avance,
deja la huella parcial y atiende las órdenes. La subclase reemplaza a `simulador.corrida.Automata` dentro de este proceso;
ningún archivo de src/v4.0 cambia.

Intervenciones (F5, contrato 1.5; el detalle está en barreras_v40.py):
- Cortafuegos antes de iniciar (`configuracion.cortafuegos`): por la vía que ya tiene el motor. Se escriben
  `cortafuegos.geojson` (EPSG:5345, `ancho_m`, `tipo: cortafuego`) y, si hay trazos a suelo mineral,
  `modificador_cortafuegos.tif` (0 en las celdas del trazo, nodata = 1, en la grilla base), y se agregan a la definición como
  `mitigacion.barreras_extra` / `mitigacion.modificador_combustible`. Sin trazos no se agrega nada (identidad E-E3-1).
  Se informan en `resultados.cortafuegos_iniciales`. Con `base.escenario` se acepta `configuracion.cortafuegos` (y nada
  más) y los trazos se combinan con la `mitigacion` que ya traiga el escenario.
- En pausa, `control.aplicar` (cortafuego o viento manual) cambia el autómata en memoria. Un cortafuego entra con
  `rasterizar_barreras_extra`, recortado a las celdas no afectadas ni intermedias de enlaces entre afectadas (D-E3-28, 13);
  agrega a `datos` `longitud_aplicada_m`, `celdas`, `celdas_recortadas`, `celdas_sha256` y `geometria_offline`. El viento
  manual reemplaza las filas de la serie posteriores a la pausa: gira durante la hora siguiente (`pleno_min` = t + 60).
- Para la corrida offline (comparación B de E-E3-4) quedan en la carpeta `cortafuegos_aplicados.geojson` (todos los trazos,
  también los iniciales, con la geometría que se aplicó), `modificador_aplicado.tif` (si hubo suelo mineral) y
  `meteo_editada.csv` (si hubo viento manual), listados en `resultados.archivos_offline`: van en el YAML como
  `mitigacion.barreras_extra`, `mitigacion.modificador_combustible` y `parche.meteo` (esta, con ruta absoluta dentro del
  repositorio, porque una relativa se busca en la carpeta del evento).
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import barreras_v40 as bv
from control import Control, Detenida

REPO = Path(__file__).resolve().parents[2]
RAIZ = REPO / "src" / "v4.0"
# Decisión D-E3-01: variante `barreras` y sin parada en la cicatriz (en tiempo real no hay cicatriz; con un evento histórico,
# v4.0 la activaría sola y congelaría la huella al igualar la superficie observada).
POR_DEFECTO = {"variante": "barreras", "parar_en_cicatriz": "off"}


def _sin_listas(d: dict | None) -> dict:
    return {k: v for k, v in (d or {}).items() if not isinstance(v, (list, dict))}


def correr(base: dict, configuracion: dict, carpeta: Path, control: Control) -> dict:
    sys.path.insert(0, str(RAIZ / "src"))
    import yaml
    import ignicion as ignicion_libre
    from incendios_sl import config as cfgmod, escenario, resumen
    from simulador import corrida as corrida_mod
    from simulador.ca.automata import Automata
    from simulador import rutas
    from simulador.outputs import geo
    from simulador.rutas import raiz_datos

    carpeta = Path(carpeta).resolve()
    salida = carpeta / "salida"
    salida.mkdir(parents=True, exist_ok=True)
    iniciales = list(configuracion.get("cortafuegos") or [])
    estado = {"au": None, "ultima_hora": -1}
    # v4.0 solo admite insumos dentro del repositorio o de la carpeta de datos. Los de las intervenciones están en la carpeta
    # de la corrida, que en la app ya está en el repositorio (resultados/app/<id>); si se la puso en otro lado (pruebas), se
    # la suma a las raíces permitidas solo dentro de este proceso.
    permitidas = rutas.raices_permitidas
    if not any(b == carpeta or b in carpeta.parents for b in permitidas()):
        rutas.raices_permitidas = lambda: permitidas() + [carpeta]

    def grilla_de(au) -> dict:
        g = au.capas.grilla
        return {"crs": g.crs, "xmin": g.xmin, "ymax": g.ymax, "res": g.res, "filas": g.alto, "cols": g.ancho}

    def hora_en_punto(au, h: int, t_min: float) -> None:
        """Estado al cumplirse la hora h. SIM ya escribió estado_hora_HH.json de esta hora."""
        control.listo(au.t0.tz_convert("UTC"), grilla_de(au))
        extra = {}
        p = salida / f"estado_hora_{h:02d}.json"
        if p.exists():
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                extra = {"exposicion": _sin_listas(d.get("exposicion")), "meteo": _sin_listas(d.get("meteo"))}
            except (json.JSONDecodeError, OSError):
                pass
        control.hora(h, t_min, au.area_quemada_ha(), len(au.act), au.t_llegada, **extra)
        estado["ultima_hora"] = h

    class AutomataControlado(Automata):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            estado["au"] = self
            interv.au = self

        def paso_tiempo(self):
            t_min = self.minutos(self.t)
            h = int(round(t_min / 60.0))
            if abs(t_min - h * 60.0) < 1e-6 and h > estado["ultima_hora"]:
                hora_en_punto(self, h, t_min)
                if control.atender(t_min):
                    raise Detenida()
            return super().paso_tiempo()

    corrida_mod.Automata = AutomataControlado

    interv = bv.Intervenciones(carpeta, iniciales)
    control.aplicar = interv.aplicar

    # --- escenario: uno existente o una definición propia (se escribe como YAML y se carga igual que offline)
    pedido = {}
    if base.get("escenario"):
        if any(k != "cortafuegos" for k in configuracion):
            raise ValueError("`configuracion` solo se combina con `base.definicion`; `base.escenario` se corre tal cual "
                             "(salvo `cortafuegos`)")
        esc, ruta, nombre = escenario.cargar_corrida(str(base["escenario"]), None)
        if iniciales:
            esc = interv.preparar_iniciales(esc, raiz_datos(), Path(ruta).parent)
    else:
        definicion, pedido = ignicion_libre.aplicar(cfgmod, dict(base["definicion"]), configuracion)
        for clave, valor in POR_DEFECTO.items():
            definicion.setdefault(clave, valor)
        if iniciales:
            definicion = interv.preparar_iniciales(definicion, raiz_datos(), carpeta)
        archivo = carpeta / "escenario_base.yaml"
        archivo.write_text(yaml.safe_dump(definicion, allow_unicode=True, sort_keys=False), encoding="utf-8")
        esc, ruta, nombre = escenario.cargar_corrida(None, archivo)

    run_id = str(esc.get("run_id") or carpeta.name)
    t_reloj = time.time()
    trad = escenario.traducir(esc, ruta, run_id=run_id)
    ent = trad["entradas"]
    extras = {"run_id": run_id, "escenario": nombre, "modelo": ent["modelo_nombre"], "variante": ent["variante"]}
    if trad["modo"] == "evento":
        extras |= {"evento": ent["evento"], "hipotesis": ent["hipotesis_ignicion"], "ignicion_ficha": ent["ignicion"]}
    elif trad["modo"] == "caso":
        extras |= {"caso": ent["caso"], "variante_caso": ent["variante_caso"],
                   "nombre_toa": (trad["caso"].get("evaluacion") or {}).get("nombre_toa")}
    # puntos que usa el motor, ya corridos a celda combustible si hizo falta (`desplazada_m`)
    usada = [{k: p[k] for k in ("id", "lon", "lat", "desplazada_m") if k in p} for p in (ent.get("igniciones") or [])]
    ign = {"ignicion": {"pedida": pedido, "usada": usada, "t_inicio_utc": ent.get("t_inicio_utc")}}

    try:
        res = corrida_mod.ejecutar(trad["cfg"], raiz_datos(), carpeta=salida, verificar_sha=True, verbose=True,
                                   extras_metadata=extras)
    except Detenida:
        au = estado["au"]
        geo.exportar_rasters(au, salida, None)
        control.guardar_huella(au.t_llegada)
        t_min = au.minutos(au.t)
        return {"motivo_fin": "detenida", "motivo_fin_texto": "Detenida por el usuario.", "ha_final": round(au.area_quemada_ha(), 2),
                "t_simulado_min": round(t_min, 3), "salida": "salida", "completa": False,
                "archivos": sorted(p.name for p in salida.iterdir() if p.is_file())} | ign | interv.informe()

    segundos = time.time() - t_reloj
    shutil.copy(ruta, salida / f"escenario_{nombre}.yaml")
    resumen.escribir_registro(salida, res, trad, segundos, run_id, nombre)
    if trad["validar"]:
        met = None
        if trad["modo"] == "evento":
            reg = resumen._cargar(salida / "registro.json", {})
            met = resumen.metricas_evento(salida, trad, run_id, reg.get("t_simulado_utc"))
        elif trad["modo"] == "caso":
            met = resumen.metricas_caso(res, trad, salida, run_id)
        if met is not None:
            resumen.escribir_json(met, salida / "metricas.json")
    resumen.escribir_resumen(salida)

    au = res["automata"]
    ind = res["indicadores"]
    if ind and int(ind[-1]["hora_indice"]) > estado["ultima_hora"]:      # la última hora no pasa por paso_tiempo
        d = ind[-1]
        control.listo(au.t0.tz_convert("UTC"), grilla_de(au))
        control.hora(int(d["hora_indice"]), float(d["minutos_desde_t0"]), float(d["superficie"]["quemada_ha"]),
                     int((d.get("frente") or {}).get("celdas_activas", len(au.act))), au.t_llegada,
                     exposicion=_sin_listas(d.get("exposicion")), meteo=_sin_listas(d.get("meteo")))
    else:
        control.guardar_huella(au.t_llegada)
    t_min = float(ind[-1]["minutos_desde_t0"]) if ind else 0.0
    return {"motivo_fin": au.motivo_fin, "motivo_fin_texto": au.motivo_fin_texto, "ha_final": round(au.area_quemada_ha(), 2),
            "t_simulado_min": round(t_min, 3), "salida": "salida", "completa": True,
            "archivos": sorted(p.name for p in salida.iterdir() if p.is_file())} | ign | interv.informe()
