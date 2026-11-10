"""Carga de configuraciones YAML (no sensibles) y resolución de rutas del proyecto (misma API que v3.0).

`VERSION_RESULTADOS` es el único interruptor de versión: hace que el código lea `escenarios/v4.0` y escriba en
`resultados/v4.0`. Variables de entorno (las mismas de v3.0, las define el cuaderno): `INCENDIOS_SL_RAIZ` (código,
src/v4.0), `INCENDIOS_SL_REPO` (repositorio), `INCENDIOS_SL_DATOS`, `INCENDIOS_SL_INPUT`, `INCENDIOS_SL_CRUDOS`,
`INCENDIOS_SL_PROCESADOS`, `INCENDIOS_SL_ESCENARIOS` e `INCENDIOS_SL_RESULTADOS`.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

VERSION_RESULTADOS = "v4.0"


def raiz_proyecto() -> Path:
    """Raíz del código: variable INCENDIOS_SL_RAIZ o el directorio que contiene `src/` (src/v4.0)."""
    env = os.environ.get("INCENDIOS_SL_RAIZ")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[2]


def raiz_datos() -> Path:
    """Raíz de datos heredada de v1 (variable INCENDIOS_SL_DATOS); si no está definida, la raíz del proyecto."""
    env = os.environ.get("INCENDIOS_SL_DATOS")
    return Path(env).resolve() if env else raiz_proyecto()


def raiz_repositorio() -> Path:
    """Raíz del repositorio (variable INCENDIOS_SL_REPO). Si el código está en <repo>/src/<versión> se deduce sola."""
    env = os.environ.get("INCENDIOS_SL_REPO")
    if env:
        return Path(env).resolve()
    p = raiz_proyecto()
    return p.parent.parent if p.parent.name == "src" else p


def ruta(rel: str | os.PathLike) -> Path:
    """Ruta relativa → absoluta buscando en crudos, inputSimulacion, la raíz de datos y la del proyecto (en ese orden)."""
    p = Path(rel)
    if p.is_absolute():
        return p
    for base in (dir_crudos(), dir_entradas(), raiz_datos(), raiz_proyecto()):
        if (base / p).exists():
            return base / p
    return dir_crudos() / p


def dir_datos(*partes: str) -> Path:
    d = raiz_datos().joinpath(*partes)
    alt = raiz_proyecto().joinpath(*partes)
    return alt if (not d.exists() and alt.exists()) else d


def _dir_repo(env: str, *partes: str) -> Path:
    v = os.environ.get(env)
    return Path(v).resolve() if v else raiz_repositorio().joinpath(*partes)


def dir_crudos() -> Path:
    """Fuentes externas sin modificar: <repo>/datos/crudos (INCENDIOS_SL_CRUDOS)."""
    return _dir_repo("INCENDIOS_SL_CRUDOS", "datos", "crudos")


def dir_procesados() -> Path:
    """Productos intermedios regenerables: <repo>/datos/procesados (INCENDIOS_SL_PROCESADOS). v4.0 usa la subcarpeta
    `v4.0/<evento>/` para los insumos de SIM derivados de las fichas de v3.0."""
    d = _dir_repo("INCENDIOS_SL_PROCESADOS", "datos", "procesados"); d.mkdir(parents=True, exist_ok=True)
    return d


def dir_escenarios() -> Path:
    """Dominios, eventos, modelos y corridas: <repo>/escenarios/<versión> (INCENDIOS_SL_ESCENARIOS)."""
    d = _dir_repo("INCENDIOS_SL_ESCENARIOS", "escenarios", VERSION_RESULTADOS)
    return d if d.exists() else raiz_proyecto() / "config"


def dir_entradas() -> Path:
    """Datos que alimentan la simulación: <repo>/datos/inputSimulacion (INCENDIOS_SL_INPUT). La primera llamada une los
    archivos divididos para GitHub (`x.part00, x.part01…`)."""
    env = os.environ.get("INCENDIOS_SL_INPUT")
    d = Path(env).resolve() if env else raiz_repositorio() / "datos" / "inputSimulacion"
    if not _PARTES_UNIDAS:
        unir_todas_las_partes(d.parent if not env else d, dir_crudos())
    viejo = raiz_datos() / "data" / "derivados"
    return viejo if (not d.exists() and viejo.exists()) else d


def dir_resultados() -> Path:
    """Resultados de las corridas: <repo>/resultados/<VERSION_RESULTADOS> (INCENDIOS_SL_RESULTADOS)."""
    env = os.environ.get("INCENDIOS_SL_RESULTADOS")
    d = Path(env).resolve() if env else raiz_repositorio() / "resultados" / VERSION_RESULTADOS
    d.mkdir(parents=True, exist_ok=True)
    return d


def grupo_corrida(esc: dict) -> str:
    """Subcarpeta de resultados/v4.0 que agrupa una corrida: el id del evento, el caso de prueba o «sim» (E032)."""
    return str(esc.get("evento") or esc.get("caso") or "sim")


def dir_corrida(run_id: str, grupo: str | None = None) -> Path:
    """Carpeta de una corrida nueva: resultados/v4.0/<grupo>/<run_id> (sin grupo, resultados/v4.0/<run_id>)."""
    return dir_resultados() / grupo / run_id if grupo else dir_resultados() / run_id


def buscar_corrida(run_id: str) -> Path:
    """Carpeta existente de `run_id`: resultados/v4.0/<run_id> (corridas anteriores a E032) o resultados/v4.0/<grupo>/<run_id>.
    Si no existe, devuelve la primera."""
    R = dir_resultados()
    if (R / run_id).is_dir():
        return R / run_id
    return next((d for d in sorted(R.glob(f"*/{run_id}")) if d.is_dir()), R / run_id)


def corridas_guardadas() -> list[Path]:
    """Carpetas con registro.json en resultados/v4.0 (primer nivel y dentro de cada grupo), de la más nueva a la más vieja."""
    R = dir_resultados()
    ds = [p.parent for p in list(R.glob("*/registro.json")) + list(R.glob("*/*/registro.json"))]
    return sorted(ds, key=lambda d: (d / "registro.json").stat().st_mtime, reverse=True)


def dir_catalogo() -> Path:
    """Catálogos de incendios y focos: datos/inputSimulacion/catalogo."""
    d = dir_entradas() / "catalogo"
    alt = raiz_proyecto() / "data" / "catalogo"
    return alt if (not d.exists() and alt.exists()) else d


def dir_derivados(*partes: str) -> Path:
    d = dir_entradas().joinpath(*partes)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cargar_yaml(p: Path) -> dict[str, Any]:
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _yaml_escenario(*candidatos: Path) -> Path:
    for c in candidatos:
        if c.exists():
            return c
    raise FileNotFoundError("no existe " + " ni ".join(str(c) for c in candidatos))


def cargar_dominio(id_dominio: str) -> dict[str, Any]:
    E = dir_escenarios()
    return _cargar_yaml(_yaml_escenario(E / "dominios" / f"dominio_{id_dominio}.yaml", E / f"dominio_{id_dominio}.yaml"))


def cargar_evento(id_evento: str) -> dict[str, Any]:
    return _cargar_yaml(_yaml_escenario(dir_escenarios() / "eventos" / f"{id_evento}.yaml"))


def cargar_modelo(nombre: str = "modelo_v3") -> dict[str, Any]:
    """YAML parcial de escenarios/v4.0/modelos/<nombre>.yaml (se fusiona sobre simulador.config.DEFAULTS)."""
    E = dir_escenarios()
    return _cargar_yaml(_yaml_escenario(E / "modelos" / f"{nombre}.yaml", E / f"{nombre}.yaml"))


def cargar_corrida(nombre: str) -> dict[str, Any]:
    """Escenario de corrida (escenarios/<versión>/corridas/<nombre>.yaml)."""
    return _cargar_yaml(_yaml_escenario(dir_escenarios() / "corridas" / f"{nombre}.yaml"))


def cargar_rutas_herramientas() -> dict[str, Any]:
    """Rutas locales de herramientas externas (config/herramientas.yaml, opcional)."""
    p = raiz_proyecto() / "config" / "herramientas.yaml"
    return _cargar_yaml(p) if p.exists() else {}


def unir_partes(destino: Path) -> Path:
    """Si `destino` no existe pero hay `destino.part00, .part01…`, los concatena y devuelve la ruta del archivo completo."""
    destino = Path(destino)
    if destino.exists():
        return destino
    partes = sorted(destino.parent.glob(destino.name + ".part*"))
    if partes:
        with open(destino, "wb") as out:
            for parte in partes:
                out.write(parte.read_bytes())
    return destino


_PARTES_UNIDAS = False


def unir_todas_las_partes(*raices: Path) -> list[Path]:
    """Recorre datos/ (o las raíces dadas) y une cada archivo dividido que falte. Se llama una vez por proceso."""
    global _PARTES_UNIDAS
    unidos: list[Path] = []
    for raiz in raices or (raiz_repositorio() / "datos",):
        if not Path(raiz).exists():
            continue
        for p0 in Path(raiz).rglob("*.part00"):
            dest = p0.with_name(p0.name[: -len(".part00")])
            if not dest.exists():
                unir_partes(dest); unidos.append(dest)
    _PARTES_UNIDAS = True
    return unidos
