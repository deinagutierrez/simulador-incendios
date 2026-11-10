"""Carga de configuraciones YAML (no sensibles) y resolución de rutas del proyecto."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def raiz_proyecto() -> Path:
    """Raíz del proyecto: variable INCENDIOS_SL_RAIZ o el directorio que contiene `src/`."""
    env = os.environ.get("INCENDIOS_SL_RAIZ")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[2]


def raiz_datos() -> Path:
    """Raíz de los datos (insumos, data/derivados, data/resultados): variable INCENDIOS_SL_DATOS.
    Si no está definida, los datos se buscan en la raíz del proyecto (comportamiento de v1)."""
    env = os.environ.get("INCENDIOS_SL_DATOS")
    return Path(env).resolve() if env else raiz_proyecto()


def ruta(rel: str | os.PathLike) -> Path:
    """Convierte una ruta relativa en absoluta buscando primero en la raíz de datos y después en la del proyecto
    (las absolutas se devuelven tal cual). Así los insumos pesados pueden vivir fuera del repositorio."""
    p = Path(rel)
    if p.is_absolute():
        return p
    for base in (dir_crudos(), dir_entradas(), raiz_datos(), raiz_proyecto()):
        if (base / p).exists():
            return base / p
    return raiz_datos() / p


def dir_datos(*partes: str) -> Path:
    """Ruta bajo la raíz de datos (p. ej. dir_datos("data", "resultados")). Si no existe allí pero sí en el
    repositorio (caso de data/catalogo, que se versiona), devuelve la del repositorio."""
    d = raiz_datos().joinpath(*partes)
    alt = raiz_proyecto().joinpath(*partes)
    return alt if (not d.exists() and alt.exists()) else d


def _cargar_yaml(p: Path) -> dict[str, Any]:
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def cargar_dominio(id_dominio: str) -> dict[str, Any]:
    E = dir_escenarios()
    return _cargar_yaml(_yaml_escenario(E / "dominios" / f"dominio_{id_dominio}.yaml", E / f"dominio_{id_dominio}.yaml"))


def cargar_evento(id_evento: str) -> dict[str, Any]:
    return _cargar_yaml(_yaml_escenario(dir_escenarios() / "eventos" / f"{id_evento}.yaml"))


def cargar_modelo(nombre: str = "modelo_v1") -> dict[str, Any]:
    E = dir_escenarios()
    return _cargar_yaml(_yaml_escenario(E / "modelos" / f"{nombre}.yaml", E / f"{nombre}.yaml"))


def cargar_corrida(nombre: str) -> dict[str, Any]:
    """Escenario de corrida (escenarios/<versión>/corridas/<nombre>.yaml): evento, hipótesis, parámetros, horas."""
    return _cargar_yaml(_yaml_escenario(dir_escenarios() / "corridas" / f"{nombre}.yaml"))


def cargar_rutas_herramientas() -> dict[str, Any]:
    """Rutas locales de herramientas externas (config/herramientas.yaml, opcional)."""
    p = raiz_proyecto() / "config" / "herramientas.yaml"
    return _cargar_yaml(p) if p.exists() else {}


VERSION_RESULTADOS = "v3.1"


def raiz_repositorio() -> Path:
    """Raíz del repositorio Gemelos_Digitales_Incendios_UNSL (variable INCENDIOS_SL_REPO). Si el código está en
    <repo>/src/<versión> se deduce sola; si no, es la raíz del proyecto."""
    env = os.environ.get("INCENDIOS_SL_REPO")
    if env:
        return Path(env).resolve()
    p = raiz_proyecto()
    return p.parent.parent if p.parent.name == "src" else p


def _dir_repo(env: str, *partes: str) -> Path:
    v = os.environ.get(env)
    return Path(v).resolve() if v else raiz_repositorio().joinpath(*partes)


def dir_crudos() -> Path:
    """Fuentes externas sin modificar: <repo>/datos/crudos (INCENDIOS_SL_CRUDOS)."""
    return _dir_repo("INCENDIOS_SL_CRUDOS", "datos", "crudos")


def dir_procesados() -> Path:
    """Productos intermedios regenerables (índices Sentinel-2, caché de WindNinja): <repo>/datos/procesados."""
    d = _dir_repo("INCENDIOS_SL_PROCESADOS", "datos", "procesados"); d.mkdir(parents=True, exist_ok=True)
    return d


def dir_escenarios() -> Path:
    """Dominios, eventos, modelos y corridas: <repo>/escenarios/<versión> (INCENDIOS_SL_ESCENARIOS).
    Si no existe, se usa config/ dentro del código (compatibilidad v1)."""
    d = _dir_repo("INCENDIOS_SL_ESCENARIOS", "escenarios", VERSION_RESULTADOS)
    return d if d.exists() else raiz_proyecto() / "config"


def _yaml_escenario(*candidatos: Path) -> Path:
    for c in candidatos:
        if c.exists():
            return c
    raise FileNotFoundError("no existe " + " ni ".join(str(c) for c in candidatos))


def dir_entradas() -> Path:
    """Datos que alimentan la simulación: <repo>/datos/inputSimulacion (variable INCENDIOS_SL_INPUT para otra
    ubicación). Compatibilidad v1: si no existe y hay un data/derivados en la raíz de datos, se usa ese."""
    env = os.environ.get("INCENDIOS_SL_INPUT")
    d = Path(env).resolve() if env else raiz_repositorio() / "datos" / "inputSimulacion"
    if not _PARTES_UNIDAS:
        unir_todas_las_partes(d.parent if not env else d, dir_crudos())
    viejo = raiz_datos() / "data" / "derivados"
    return viejo if (not d.exists() and viejo.exists()) else d


def dir_resultados() -> Path:
    """Resultados de las corridas: <repo>/resultados/<VERSION_RESULTADOS> (variable INCENDIOS_SL_RESULTADOS)."""
    env = os.environ.get("INCENDIOS_SL_RESULTADOS")
    d = Path(env).resolve() if env else raiz_repositorio() / "resultados" / VERSION_RESULTADOS
    d.mkdir(parents=True, exist_ok=True)
    return d


def dir_catalogo() -> Path:
    """Catálogos de incendios y focos: datos/inputSimulacion/catalogo; si no está, data/catalogo del código."""
    d = dir_entradas() / "catalogo"
    alt = raiz_proyecto() / "data" / "catalogo"
    return alt if (not d.exists() and alt.exists()) else d


def unir_partes(destino: Path) -> Path:
    """Si `destino` no existe pero hay `destino.part00, .part01…` (archivos > 100 MB divididos para GitHub),
    los concatena y devuelve la ruta del archivo completo."""
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
    """Recorre datos/ (o las raíces dadas) y une cada archivo dividido (`x.part00, x.part01…`) que falte.
    Se llama una vez por proceso; los archivos de más de 25 MB se suben a GitHub divididos (límite de la carga web)."""
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


def dir_derivados(*partes: str) -> Path:
    d = dir_entradas()
    for parte in partes:
        d = d / parte
    d.mkdir(parents=True, exist_ok=True)
    return d
