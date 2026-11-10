"""Corre una corrida de escenarios/v4.0/corridas/<nombre>.yaml con el simulador SIM y deja el resultado en
resultados/v4.0/<grupo>/<run_id>/ (grupo = id del evento, caso de prueba o «sim»; E032).

Uso (desde src/v4.0):
  python scripts/correr_escenario.py --escenario prueba_rapida_v4
  python scripts/correr_escenario.py --archivo /content/mi_corrida.yaml [--sin-sha] [--solo-simular]

Una corrida tiene `evento` (ficha de escenarios/v4.0/eventos), `caso` (conjunto de prueba de SIM) o `sim` (YAML nativo
de SIM), y los campos de v3.0: `hipotesis`, `ignicion` (snmf | altN), `horas`, `variante` (libre, barreras, contencion,
ambas, local, local_pronostico, l03, v4_original), `modelo` (modelo_v3 | sim_v4_original | propio), `barreras` y
`contencion` (auto | on | off), `despacho` (auto | global | local | pronostico | l03), `ajustes` (se fusiona en
`parametros` de SIM), `parche` (se fusiona en el cfg completo), `k_grupo`, `k_global`, `factor_waf`, `humedad`,
`semilla`, `ensemble`, `mitigacion` ({modificador_combustible, barreras_extra}), `validar`, `figuras`, `run_id`,
`descripcion` (ver escenarios/v4.0/README.md e incendios_sl.escenario).

Salida: todo lo de SIM (hora_llegada_min.tif, perimetros_horarios.geojson, serie_indicadores.csv, estado_hora_HH.json,
mapas, metadata.json…) + escenario_<nombre>.yaml, registro.json, resumen_<run_id>_<AAAAMMDD-HHMM>.json/.md y, si la
corrida valida, metricas.json. `--sin-sha` no recalcula el sha256 de cada insumo del manifiesto (más rápido).
"""
from __future__ import annotations

import argparse
import logging
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from incendios_sl import config as cfgmod  # noqa: E402

for _flujo in (sys.stdout, sys.stderr):      # Windows con salida redirigida (cp1252): el registro usa "→", "°", "Δ"
    if hasattr(_flujo, "reconfigure"):
        _flujo.reconfigure(encoding="utf-8", errors="replace")


def correr(esc: dict, ruta_esc: Path, nombre: str, verificar_sha: bool = True, solo_simular: bool = False, verbose: bool = True) -> Path:
    """Traduce, simula, registra, valida y resume una corrida. Devuelve la carpeta del resultado."""
    from simulador.corrida import ejecutar
    from simulador.rutas import raiz_datos
    from incendios_sl import escenario, resumen
    run_id = str(esc.get("run_id") or f"{nombre}_{time.strftime('%Y%m%d-%H%M')}")
    t_reloj = time.time()
    trad = escenario.traducir(esc, ruta_esc, run_id=run_id)
    ent = trad["entradas"]
    validar = trad["validar"] and not solo_simular
    origen = f"evento {ent['evento']} (hipótesis {ent['hipotesis_ignicion']}, ignición {ent['ignicion']})" if trad["modo"] == "evento" else \
             (f"caso {ent['caso']} ({ent['variante_caso']})" if trad["modo"] == "caso" else f"SIM {ent['sim']}")
    print(f"escenario {nombre}: {origen}, run_id {run_id}, modelo {ent['modelo_nombre']}, variante {ent['variante'] or '—'}, "
          f"barreras {ent['barreras']}, contención {ent['contencion']}, supresión {ent['supresion']}, despacho {ent['despacho']['modo']}, "
          f"{trad['cfg']['duracion_h']:g} h, validar={validar}", flush=True)
    carpeta = cfgmod.dir_corrida(run_id, cfgmod.grupo_corrida(esc))
    if (carpeta / "registro.json").exists():
        print(f"aviso: {carpeta} ya tenía una corrida; se sobrescriben sus archivos", flush=True)
    carpeta.mkdir(parents=True, exist_ok=True)
    extras = {"run_id": run_id, "escenario": nombre, "modelo": ent["modelo_nombre"], "variante": ent["variante"]}
    if trad["modo"] == "evento":
        extras |= {"evento": ent["evento"], "hipotesis": ent["hipotesis_ignicion"], "ignicion_ficha": ent["ignicion"]}
    elif trad["modo"] == "caso":
        extras |= {"caso": ent["caso"], "variante_caso": ent["variante_caso"], "nombre_toa": (trad["caso"].get("evaluacion") or {}).get("nombre_toa")}
    res = ejecutar(trad["cfg"], raiz_datos(), carpeta=carpeta, verificar_sha=verificar_sha, verbose=verbose, extras_metadata=extras)
    segundos = time.time() - t_reloj
    shutil.copy(ruta_esc, carpeta / f"escenario_{nombre}.yaml")
    resumen.escribir_registro(carpeta, res, trad, segundos, run_id, nombre)
    if validar:
        if trad["modo"] == "evento":
            reg = resumen._cargar(carpeta / "registro.json", {})
            met = resumen.metricas_evento(carpeta, trad, run_id, reg.get("t_simulado_utc"))
        elif trad["modo"] == "caso":
            met = resumen.metricas_caso(res, trad, carpeta, run_id)
        else:
            met = None
            print("validar: un escenario nativo de SIM no tiene referencia estándar; usar `caso` para evaluar", flush=True)
        if met is not None:
            resumen.escribir_json(met, carpeta / "metricas.json")
    pj, pm = resumen.escribir_resumen(carpeta)
    print(pm.read_text(encoding="utf-8"), flush=True)
    reg = resumen._cargar(carpeta / "registro.json", {})
    print(f"fin: {reg.get('motivo_fin')} · {reg.get('ha_quemadas')} ha en {reg.get('duracion_simulada_h')} h de {reg.get('duracion_pedida_h'):g}"
          f" · {reg.get('segundos')} s", flush=True)
    print("resultado en", carpeta, flush=True)
    return carpeta


def main() -> int:
    ap = argparse.ArgumentParser(description="Corre una corrida estándar de v4.0 con SIM")
    ap.add_argument("--escenario", help="nombre del YAML en escenarios/v4.0/corridas/")
    ap.add_argument("--archivo", help="ruta a un YAML de corrida fuera de la carpeta de corridas (alternativa a --escenario)")
    ap.add_argument("--sin-sha", action="store_true", help="no verificar el sha256 de los insumos del manifiesto de SIM")
    ap.add_argument("--solo-simular", action="store_true", help="no calcular métricas aunque la corrida pida validar")
    ap.add_argument("--silencioso", action="store_true", help="sin el registro hora a hora de SIM en pantalla")
    a = ap.parse_args()
    if not (a.escenario or a.archivo):
        ap.error("indicar --escenario o --archivo")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    from incendios_sl import escenario
    esc, ruta, nombre = escenario.cargar_corrida(a.escenario, a.archivo)
    correr(esc, ruta, nombre, verificar_sha=not a.sin_sha, solo_simular=a.solo_simular, verbose=not a.silencioso)
    return 0


if __name__ == "__main__":
    sys.exit(main())
