"""Corre un escenario definido en escenarios/<versión>/corridas/<nombre>.yaml y deja el resultado en resultados/<versión>/.

Uso:
  python scripts/correr_escenario.py --escenario calibracion_2024            # simula y valida (si el YAML lo pide)
  python scripts/correr_escenario.py --escenario calibracion_2024 --solo-simular

Un escenario es un YAML con, al menos, `evento`. Campos opcionales: `hipotesis` (índice de hora de ignición, 0),
`horas` (limitar la duración), `k_clase` ({clase: factor}), `k_global`, `factor_waf`, `validar` (true/false),
`figuras` (true/false), `run_id` (por defecto <nombre>_<AAAAMMDD-HHMM>), `descripcion`.
Campos de v3 (docs/10-13): `variante` (atajo de la ablación de scripts/evaluar_v2.py: libre, libre_v2, barreras, contencion, ambas,
local, local_pronostico, local_exacto) o, uno por uno, `modelo` (modelo_v1 | modelo_v2), `barreras` y `contencion` (auto | on | off),
`despacho` (auto | global | local | pronostico), `parche` (dict fusionado con el YAML del modelo), `ajustes` (campos de ConfigSimulacion,
p. ej. {tasa_linea_m_h: 500}) e `ignicion` (snmf | alt0, alt1… de la ficha). Lo que no se indica sale del YAML del modelo.
El resultado lleva una copia del escenario y el resumen estadístico de la corrida.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from incendios_sl import config as cfgmod  # noqa: E402


def _tri(v) -> bool | None:
    if v is None or isinstance(v, bool):
        return v
    return None if str(v).lower() == "auto" else str(v).lower() in ("on", "1", "true", "si", "sí")


def opciones_v3(esc: dict) -> dict:
    """Modelo, barreras, contención y despacho del escenario (v3) como argumentos de validar.ejecutar_y_evaluar."""
    from incendios_sl.simulation.entradas import PARCHES_DESPACHO, fusionar
    modelo, barreras, contencion, parche = "modelo_v1", None, None, None
    if esc.get("variante"):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from evaluar_v2 import VARIANTES  # scripts/evaluar_v2.py
        if esc["variante"] not in VARIANTES:
            raise ValueError(f"variante {esc['variante']!r} desconocida; opciones: {', '.join(VARIANTES)}")
        modelo, barreras, contencion, parche = VARIANTES[esc["variante"]]
    modelo = esc.get("modelo", modelo)
    barreras = _tri(esc["barreras"]) if "barreras" in esc else barreras
    contencion = _tri(esc["contencion"]) if "contencion" in esc else contencion
    if esc.get("despacho"):
        parche = fusionar(parche or {}, PARCHES_DESPACHO[esc["despacho"]])
    if esc.get("parche"):
        parche = fusionar(parche or {}, esc["parche"])
    return {"modelo": modelo, "barreras": barreras, "contencion": contencion, "parche_modelo": parche or None,
            "extra_cfg": esc.get("ajustes") or None, "ignicion": str(esc.get("ignicion", "snmf"))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--escenario", help="nombre del YAML en escenarios/<versión>/corridas/")
    ap.add_argument("--archivo", help="ruta a un YAML de escenario fuera de la carpeta de corridas (alternativa a --escenario)")
    ap.add_argument("--solo-simular", action="store_true", help="no calcular métricas aunque el escenario pida validar")
    a = ap.parse_args()
    if a.archivo:
        import yaml
        ruta_esc = Path(a.archivo); esc = yaml.safe_load(open(ruta_esc, encoding="utf-8")); a.escenario = esc.get("nombre") or ruta_esc.stem
    elif a.escenario:
        ruta_esc = cfgmod.dir_escenarios() / "corridas" / f"{a.escenario}.yaml"; esc = cfgmod.cargar_corrida(a.escenario)
    else:
        ap.error("indicar --escenario o --archivo")
    run_id = esc.get("run_id") or f"{a.escenario}_{time.strftime('%Y%m%d-%H%M')}"
    hip = int(esc.get("hipotesis", 0))
    k_clase = {int(k): float(v) for k, v in (esc.get("k_clase") or {}).items()} or None
    validar = bool(esc.get("validar", True)) and not a.solo_simular
    v3 = opciones_v3(esc)
    print(f"escenario {a.escenario}: evento {esc['evento']}, hipótesis {hip}, run_id {run_id}, validar={validar}, modelo {v3['modelo']}"
          f" (barreras {v3['barreras']}, contención {v3['contencion']})")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    if validar:
        from validar import ejecutar_y_evaluar  # scripts/validar.py
        ejecutar_y_evaluar(esc["evento"], hip, esc.get("k_global"), float(esc.get("factor_waf", 1.0)), run_id, figs=bool(esc.get("figuras", True)),
                           horas=esc.get("horas"), k_clase=k_clase, **v3)
    else:
        from incendios_sl.simulation.entradas import cargar_entradas_evento
        from incendios_sl.simulation.motor import Simulacion
        ent, cfg, g, meta = cargar_entradas_evento(esc["evento"], hip, k_clase=k_clase, factor_waf=float(esc.get("factor_waf", 1.0)), k_global=esc.get("k_global"),
                                                   ignicion=v3["ignicion"], modelo=v3["modelo"], barreras=v3["barreras"], contencion=v3["contencion"],
                                                   extra_cfg=v3["extra_cfg"], parche_modelo=v3["parche_modelo"])
        if esc.get("horas"):
            import pandas as pd
            ent.t_fin_utc = min(ent.t_fin_utc, ent.t_inicio_utc + pd.Timedelta(hours=float(esc["horas"])))
        sim = Simulacion(ent, cfg); sim.ejecutar()
        sim.guardar(cfgmod.dir_resultados() / run_id, grilla=g, extra={"entradas": meta})
    out = cfgmod.dir_resultados() / run_id
    shutil.copy(ruta_esc, out / f"escenario_{a.escenario}.yaml")
    print("resultado en", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
