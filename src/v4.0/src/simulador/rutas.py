"""Rutas del simulador dentro del repositorio estándar Incendios_SanLuis (v4.0).

En V.4 el simulador vivía en una carpeta autocontenida (`simulador_incendios/` con `datos/`, `conjunto_prueba/` y
`salidas/`). En v4.0 sigue el estándar del repositorio:

    <repo>/datos/inputSimulacion/sim_v4/        manifiesto_datos.yaml, dominio/, estaticos/, dinamicos/, conjunto_prueba/
    <repo>/resultados/v4.0/                     una carpeta por corrida
    <repo>/escenarios/v4.0/                     YAML (eventos, modelos, corridas, sim/)

Variables de entorno (las mismas que usa `incendios_sl.config`): `INCENDIOS_SL_REPO`, `INCENDIOS_SL_RESULTADOS`, y
`INCENDIOS_SL_SIM_DATOS` para mover solo la carpeta de datos del simulador.
"""

from __future__ import annotations

import os
from pathlib import Path

VERSION_RESULTADOS = "v4.0"


def raiz_repositorio() -> Path:
    """<repo>: `INCENDIOS_SL_REPO` o, si el código está en <repo>/src/v4.0/src/simulador, cuatro niveles arriba."""
    v = os.environ.get("INCENDIOS_SL_REPO")
    if v:
        return Path(v).resolve()
    aqui = Path(__file__).resolve()
    return aqui.parents[4] if len(aqui.parents) > 4 and aqui.parents[3].name == "src" else aqui.parents[1]


def raiz_datos() -> Path:
    """Carpeta del manifiesto del simulador (datos estáticos y dinámicos del dominio y conjunto de prueba)."""
    v = os.environ.get("INCENDIOS_SL_SIM_DATOS")
    if v:
        return Path(v).resolve()
    return raiz_repositorio() / "datos" / "inputSimulacion" / "sim_v4"


def dir_salidas() -> Path:
    v = os.environ.get("INCENDIOS_SL_RESULTADOS")
    d = Path(v).resolve() if v else raiz_repositorio() / "resultados" / VERSION_RESULTADOS
    d.mkdir(parents=True, exist_ok=True)
    return d


def raices_permitidas() -> list[Path]:
    """Las rutas de un escenario deben quedar dentro del repositorio (o de la carpeta de datos, si se movió)."""
    out = [raiz_repositorio(), raiz_datos()]
    v = os.environ.get("INCENDIOS_SL_PROCESADOS")
    if v:
        out.append(Path(v).resolve())
    return out


def relativa(p: Path) -> str:
    """Ruta para metadatos: relativa al repositorio si se puede (los registros no guardan rutas de la máquina)."""
    p = Path(p).resolve()
    for base in (raiz_datos(), raiz_repositorio()):
        try:
            return p.relative_to(base).as_posix()
        except ValueError:
            continue
    return p.as_posix()
