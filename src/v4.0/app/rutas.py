"""Rutas del banco de pruebas de V.4 en v4.0, leídas de `config/rutas.yaml` (relativas a `src/v4.0/` o absolutas).

    from rutas import Rutas
    r = Rutas()                      # o Rutas(raiz) para otra copia de src/v4.0
    r.mascara_dominio, r.cobertura(2023), r.banco / "casos", r.ndvi_ndmi(2022, 9), r.carpeta_corrida(fila.carpeta)

Disposición estándar: datos de entrada en `REPO/datos/` (crudos/ e inputSimulacion/), resultados del banco en
`REPO/resultados/v4.0/banco/`, código de SIM en `src/v4.0/src/simulador`. El registro de corridas guarda la carpeta de
cada corrida relativa a la raíz del banco; `carpeta_corrida` también reubica las rutas absolutas viejas de V.4
(`C:\\Users\\Usuario\\...\\datos\\banco\\corridas\\<run_id>`) por el nombre de la carpeta.
"""
from __future__ import annotations

import sys
from pathlib import Path, PureWindowsPath

import yaml

RAIZ_BANCO = Path(__file__).resolve().parents[1]          # src/v4.0
RAIZ_V4 = RAIZ_BANCO                                       # nombre de V.4 (compatibilidad)


class Rutas:
    def __init__(self, raiz: str | Path | None = None):
        self.raiz = Path(raiz).resolve() if raiz else RAIZ_BANCO
        self.cfg = yaml.safe_load((self.raiz / "config" / "rutas.yaml").read_text(encoding="utf-8"))

    def _p(self, v) -> Path | None:
        if v is None or v == "":
            return None
        p = Path(v)
        return (p if p.is_absolute() else (self.raiz / p)).resolve()

    def _exigir(self, seccion: str, clave: str) -> Path:
        p = self._p((self.cfg.get(seccion) or {}).get(clave))
        if p is None:
            raise FileNotFoundError(f"config/rutas.yaml: '{seccion}.{clave}' no está disponible en este equipo")
        return p

    # --- repositorio ---
    @property
    def repo(self) -> Path: return self.raiz.parents[1]
    @property
    def codigo_sim(self) -> Path: return self.raiz / "src"

    # --- crudos (solo lectura) ---
    @property
    def crudos(self) -> Path: return self._exigir("crudos", "carpeta")
    @property
    def analisis(self) -> Path:
        """Equivalente de `Contexto/extraido/.../Analisis de Situación de Incendios` de V.4: `datos/crudos`."""
        return self.crudos
    @property
    def snmf(self) -> Path: return self._exigir("crudos", "snmf")
    @property
    def dominio_geojson(self) -> Path: return self._exigir("crudos", "dominio_geojson")
    @property
    def caminos(self) -> Path: return self._exigir("crudos", "caminos")
    @property
    def cuarteles(self) -> Path: return self._exigir("crudos", "cuarteles")
    @property
    def conjunto_pruebas(self) -> Path: return self._exigir("crudos", "conjunto_pruebas")
    @property
    def salidas_sim_entrega(self) -> Path: return self._exigir("crudos", "salidas_sim_entrega")

    # --- entradas ---
    @property
    def mascara_dominio(self) -> Path: return self._exigir("entradas", "mascara_dominio")
    @property
    def fuego_mensual(self) -> Path: return self._exigir("entradas", "fuego_mensual")
    @property
    def poligonos_mapbiomas(self) -> Path: return self._exigir("entradas", "poligonos_mapbiomas")
    @property
    def meteo_ifs(self) -> Path: return self._exigir("entradas", "meteo_ifs")
    @property
    def indices_extra(self) -> Path: return self._exigir("entradas", "indices_extra")
    @property
    def firms_viirs(self) -> Path: return self._exigir("entradas", "firms_viirs")
    @property
    def red_vial_grafo(self) -> Path: return self._exigir("entradas", "red_vial_grafo")
    @property
    def carpetas_indices(self) -> list[Path]:
        v = self.cfg["entradas"].get("indices_mensuales") or [self.cfg["entradas"]["indices_extra"]]
        return [self._p(x) for x in ([v] if isinstance(v, str) else v)]

    def cobertura(self, anio: int) -> Path:
        return self._p(self.cfg["entradas"]["cobertura"].format(anio=anio))

    def ndvi_ndmi(self, anio: int, mes: int) -> Path:
        """Compuesto mensual NDVI/NDMI: el primero que exista en `entradas.indices_mensuales` (la entrega copiada por SIM,
        luego los generados con el mismo método). Si no existe en ninguna, devuelve la ruta en la última carpeta."""
        nombre = f"NDVI_NDMI_{anio}_{mes:02d}.tif"
        cands = [c / nombre for c in self.carpetas_indices]
        return next((f for f in cands if f.exists()), cands[-1])

    # --- protocolo y salidas del banco ---
    @property
    def protocolo(self) -> Path: return self._p(self.cfg["protocolo"])
    @property
    def banco(self) -> Path: return self._p(self.cfg["banco"])
    @property
    def corridas(self) -> Path: return self.banco / "corridas"

    # --- simulador SIM ---
    @property
    def sim_datos(self) -> Path:
        """Raíz de datos del simulador (manifiesto_datos.yaml): `sim.datos` o `simulador.rutas.raiz_datos()`."""
        v = self._p((self.cfg.get("sim") or {}).get("datos"))
        if v is not None:
            return v
        if str(self.codigo_sim) not in sys.path:
            sys.path.insert(0, str(self.codigo_sim))
        from simulador.rutas import raiz_datos
        return raiz_datos()
    @property
    def insumos_banco(self) -> Path: return self._exigir("sim", "insumos_banco")
    @property
    def modelos(self) -> Path: return self._exigir("sim", "modelos")

    # --- rutas del registro de corridas ---
    def relativa_repo(self, p: Path) -> str:
        """Ruta para metadatos: relativa al repositorio (posix) si se puede; si no, absoluta."""
        p = Path(p).resolve()
        try:
            return p.relative_to(self.repo).as_posix()
        except ValueError:
            return p.as_posix()

    def relativa_banco(self, p: Path) -> str:
        """Ruta para el registro: relativa a la raíz del banco (posix) si se puede; si no, absoluta."""
        p = Path(p).resolve()
        try:
            return p.relative_to(self.banco).as_posix()
        except ValueError:
            return p.as_posix()

    def carpeta_corrida(self, valor) -> Path:
        """Carpeta de una corrida a partir de la columna `carpeta` del registro: relativa a la raíz del banco, absoluta
        existente, o absoluta de otra máquina (V.4: `...\\datos\\banco\\corridas\\<run_id>`), que se reubica por el nombre
        de la carpeta dentro de `resultados/v4.0/banco/corridas/`."""
        s = str(valor).strip()
        win = PureWindowsPath(s)
        if not (win.is_absolute() or Path(s).is_absolute()):
            return (self.banco / Path(s.replace("\\", "/"))).resolve()
        p = Path(s)
        if p.exists():
            return p.resolve()
        partes = [x for x in s.replace("\\", "/").split("/") if x]
        k = len(partes) - 1 - partes[::-1].index("corridas") if "corridas" in partes else -1
        if 0 <= k < len(partes) - 1:
            return (self.corridas / Path(*partes[k + 1:])).resolve()
        return (self.corridas / partes[-1]).resolve()
