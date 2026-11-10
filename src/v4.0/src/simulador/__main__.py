"""CLI del simulador.

    python -m simulador validar                                   # valida el manifiesto
    python -m simulador run --config escenarios/x.yaml            # corre un escenario
    python -m simulador caso conjunto_prueba/<caso> [--variante V | --todas] [--sin-sha]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .rutas import raiz_datos, dir_salidas

RAIZ = raiz_datos()          # carpeta del manifiesto (datos/inputSimulacion/sim_v4)


def cmd_validar(args):
    from .io.manifiesto import Manifiesto
    man = Manifiesto.cargar(RAIZ / "manifiesto_datos.yaml")
    man.validar(verificar_sha=not args.sin_sha)
    print(f"Manifiesto v{man.version}: {len(man.entradas)} entradas válidas.")


def cmd_run(args):
    from .config import cargar_config
    from .corrida import ejecutar
    cfg = cargar_config(args.config)
    res = ejecutar(cfg, RAIZ, verificar_sha=not args.sin_sha)
    print(res["carpeta"])


def cargar_caso(carpeta: Path) -> dict:
    import yaml
    from .config import fusionar, DEFAULTS
    carpeta = Path(carpeta).resolve()
    d = yaml.safe_load((carpeta / "caso.yaml").read_text(encoding="utf-8"))
    d["_dir"] = str(carpeta)
    esc = fusionar(DEFAULTS, d.get("escenario", {}))
    esc["_dir"] = str(carpeta); esc["_ruta"] = str(carpeta / "caso.yaml")
    esc["nombre"] = esc.get("nombre") or d.get("nombre") or carpeta.name
    d["_escenario"] = esc
    return d


def cmd_caso(args):
    from .config import fusionar
    from .corrida import ejecutar, carpeta_salida
    from .evaluacion.informe import evaluar_corrida, escribir_informe
    caso = cargar_caso(args.carpeta)
    base = caso["_escenario"]
    variantes = caso.get("variantes") or {}
    if args.todas:
        seleccion = [("base", {})] + list(variantes.items())
    elif args.variante:
        if args.variante not in variantes:
            sys.exit(f"Variante desconocida '{args.variante}'. Disponibles: {list(variantes)}")
        seleccion = [(args.variante, variantes[args.variante])]
    else:
        seleccion = [("base", {})]
    resultados = []
    carpetas = []
    for etiqueta, cambios in seleccion:
        cfg = fusionar(base, cambios)
        cfg["nombre"] = f"{caso['nombre']}_{etiqueta}"
        cfg["_dir"] = base["_dir"]; cfg["_ruta"] = base["_ruta"]
        carpeta = carpeta_salida(RAIZ, cfg["nombre"])
        extras = {"caso": caso["nombre"], "variante": etiqueta, "nombre_toa": caso.get("evaluacion", {}).get("nombre_toa")}
        res = ejecutar(cfg, RAIZ, carpeta, verificar_sha=not args.sin_sha, extras_metadata=extras)
        ev = evaluar_corrida(res, caso, carpeta, etiqueta)
        import json
        (carpeta / "evaluacion.json").write_text(json.dumps(ev, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        resultados.append(ev); carpetas.append(carpeta)
    extra = (Path(caso["_dir"]) / "discusion.md").read_text(encoding="utf-8") if (Path(caso["_dir"]) / "discusion.md").exists() else ""
    ruta_inf = Path(caso["_dir"]) / "evaluacion.md" if args.todas else carpetas[-1] / "evaluacion.md"
    escribir_informe(caso, resultados, ruta_inf, extra, RAIZ)
    for c in carpetas:
        if ruta_inf.parent != c:
            escribir_informe(caso, [r for r in resultados if r["carpeta"] == str(c)], c / "evaluacion.md", "", RAIZ)
    print(f"Informe: {ruta_inf}")
    for c in carpetas:
        print(c)


def cmd_informe(args):
    """Reconstruye evaluacion.md del caso a partir de las corridas más recientes de cada variante (sin re-simular)."""
    import json
    from .evaluacion.informe import escribir_informe
    caso = cargar_caso(args.carpeta)
    nombres = ["base"] + list((caso.get("variantes") or {}).keys())
    resultados = []
    for v in nombres:
        cands = sorted(dir_salidas().glob(f"*_{caso['nombre']}_{v}"))
        cands = [c for c in cands if (c / "evaluacion.json").exists()]
        if cands:
            resultados.append(json.loads((cands[-1] / "evaluacion.json").read_text(encoding="utf-8")))
    if not resultados:
        sys.exit("No hay corridas evaluadas de este caso en resultados/v4.0/")
    extra = (Path(caso["_dir"]) / "discusion.md").read_text(encoding="utf-8") if (Path(caso["_dir"]) / "discusion.md").exists() else ""
    ruta = escribir_informe(caso, resultados, Path(caso["_dir"]) / "evaluacion.md", extra, RAIZ)
    print(f"Informe: {ruta} ({len(resultados)} variantes)")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="simulador", description="Simulador de propagación de incendios (AC + Rothermel + Scott & Burgan)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("validar", help="valida el manifiesto de datos"); p.add_argument("--sin-sha", action="store_true"); p.set_defaults(fn=cmd_validar)
    p = sub.add_parser("run", help="corre un escenario YAML"); p.add_argument("--config", required=True); p.add_argument("--sin-sha", action="store_true"); p.set_defaults(fn=cmd_run)
    p = sub.add_parser("caso", help="corre y evalúa un caso del conjunto de prueba"); p.add_argument("carpeta")
    p.add_argument("--variante"); p.add_argument("--todas", action="store_true"); p.add_argument("--sin-sha", action="store_true"); p.set_defaults(fn=cmd_caso)
    p = sub.add_parser("informe", help="reconstruye evaluacion.md con las corridas más recientes de cada variante"); p.add_argument("carpeta"); p.set_defaults(fn=cmd_informe)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
