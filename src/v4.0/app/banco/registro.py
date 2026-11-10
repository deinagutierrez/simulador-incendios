"""Registro de corridas del banco de pruebas (D30).

Contrato de una corrida (una carpeta por corrida en `resultados/v4.0/banco/corridas/<motor>_<id_evento>_<variante>/`):
  toa_min.tif        minutos desde t0 (float32, NaN = no quema), grilla del dominio, etiqueta `t0_utc`
  registro.json      motor, versión, commit, protocolo, id_evento, rol, variante, modelo (v4.0), sha256 del adaptador,
                     procedencia de insumos, estado (`ok` | `fallo_preparacion` | `fallo_corrida`)
  metricas.json      salida del evaluador externo (`app/evaluador/`), más `instante_degenerado`
  metricas_largo.csv formato largo de `CP/validacion/plantilla_metricas.csv`
Cualquier motor nuevo (adaptador en `app/motores/`) que deje esos archivos entra al registro y a la web.

`indexar()` recorre las carpetas y escribe `registro_corridas.csv` en la raíz del banco (una fila por corrida; las
carpetas sin `registro.json` se ignoran). La columna `carpeta` es relativa a la raíz del banco (`corridas/<run_id>`), para
que el registro sea portable; los lectores la resuelven con `Rutas.carpeta_corrida`. La columna `modelo` es el modelo de
parámetros de v4.0 (`sim_v4_original`, `modelo_v3`, …); las corridas hechas con V.4 (SIM 0.1.0) llevan `V.4`.

Uso (desde src/v4.0):  python -I app/banco/registro.py [--corridas <carpeta>]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rutas import Rutas  # noqa: E402

MODELO_V4 = "V.4"           # corridas del banco de V.4 (registro.json sin campo `modelo`)
COLUMNAS = ["run_id", "motor", "version_motor", "modelo", "variante", "id_evento", "rol", "protocolo", "estado", "commit_repo",
            "adaptador_sha256", "t0_utc", "ha_obs", "ha_sim_T80", "L_T80", "iou_T80", "dice_T80", "iou_eq", "dt_h_T80",
            "truncado_T80", "instante_degenerado", "focos_frac_12h", "precision_focos_750m", "segundos_reloj", "carpeta"]


def fila_corrida(d: Path, RT: Rutas | None = None) -> dict | None:
    rj = d / "registro.json"
    if not rj.exists():
        return None
    RT = RT or Rutas()
    r = json.loads(rj.read_text(encoding="utf-8"))
    f = {"run_id": d.name, "motor": r.get("motor"), "version_motor": r.get("version_motor"), "modelo": r.get("modelo") or MODELO_V4,
         "variante": r.get("variante"), "id_evento": r.get("id_evento"), "rol": r.get("rol"), "protocolo": r.get("protocolo"),
         "estado": r.get("estado"), "commit_repo": r.get("commit_repo"), "adaptador_sha256": (r.get("adaptador_sha256") or "")[:16],
         "segundos_reloj": r.get("segundos_reloj"), "carpeta": RT.relativa_banco(d)}
    mj = d / "metricas.json"
    if mj.exists():
        m = json.loads(mj.read_text(encoding="utf-8"))
        t80 = m.get("instantes", {}).get("T80", {}); eq = m.get("igual_superficie", {}); fo = m.get("focos", {}) or {}
        f.update({"t0_utc": m.get("t0_utc"), "ha_obs": m.get("ha_obs"), "ha_sim_T80": t80.get("ha_sim"), "L_T80": t80.get("L"),
                  "iou_T80": t80.get("iou"), "dice_T80": t80.get("dice"), "iou_eq": eq.get("iou"), "dt_h_T80": eq.get("dt_h"),
                  "truncado_T80": t80.get("truncado"), "instante_degenerado": m.get("instante_degenerado"),
                  "focos_frac_12h": fo.get("frac_a_12h"), "precision_focos_750m": fo.get("precision_750m@T80")})
    return f


def indexar(corridas: Path | None = None, RT: Rutas | None = None, destino: Path | None = None) -> pd.DataFrame:
    """Indexa `corridas` (por defecto `banco/corridas`) y escribe `registro_corridas.csv` en `destino` (por defecto la raíz
    del banco)."""
    RT = RT or Rutas()
    corridas = Path(corridas) if corridas else RT.corridas
    filas = [x for x in (fila_corrida(d, RT) for d in sorted(corridas.iterdir()) if d.is_dir()) if x]
    df = pd.DataFrame(filas, columns=COLUMNAS)
    df.to_csv(Path(destino) if destino else RT.banco / "registro_corridas.csv", index=False, lineterminator="\n")
    return df


def leer(RT: Rutas | None = None) -> pd.DataFrame:
    """`registro_corridas.csv` con la columna `carpeta` resuelta a rutas absolutas de este equipo (`carpeta_abs`)."""
    RT = RT or Rutas()
    reg = pd.read_csv(RT.banco / "registro_corridas.csv")
    if "modelo" not in reg:
        reg["modelo"] = MODELO_V4
    reg["modelo"] = reg.modelo.fillna(MODELO_V4)
    reg["carpeta_abs"] = [RT.carpeta_corrida(c) if isinstance(c, str) else RT.corridas / r for c, r in zip(reg.carpeta, reg.run_id)]
    return reg


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--raiz", default=None, help="carpeta src/v4.0 (por defecto, la de este código)")
    ap.add_argument("--corridas", default=None, help="carpeta de corridas (por defecto banco/corridas de config/rutas.yaml)")
    a = ap.parse_args(argv)
    RT = Rutas(a.raiz)
    df = indexar(Path(a.corridas).resolve() if a.corridas else None, RT)
    pd.set_option("display.width", 200)
    print(df[["run_id", "motor", "modelo", "rol", "estado", "iou_eq", "L_T80", "dt_h_T80"]].to_string(index=False))


if __name__ == "__main__":
    sys.exit(main())
