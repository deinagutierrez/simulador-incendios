"""Comprueba que un clon funciona: versiones congeladas intactas, datos presentes, pruebas de los dos motores y una
corrida corta con cada uno. Lo usan instalar.bat / instalar.sh, probar.bat / probar.sh y la integración continua.

    python herramientas/probar.py            todo
    python herramientas/probar.py --rapido   sin las corridas de humo

Los motores no se instalan: cada uno se ejecuta con PYTHONPATH apuntando a su carpeta, porque los dos paquetes se llaman
incendios_sl. Sale con código 1 si algo falla.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MOTORES = {"v3.1": "prueba_rapida_v3", "v4.0": "prueba_rapida_v4"}
DATOS_CLAVE = [
    "datos/inputSimulacion/grilla/mascara_dominio_las_lagunas_potrerillos.tif",
    "datos/inputSimulacion/dem/dem_copernicus_glo30_las_lagunas_potrerillos.tif",
    "datos/inputSimulacion/infraestructura/caminos_las_lagunas_potrerillos.gpkg",
    "datos/inputSimulacion/infraestructura/viviendas_las_lagunas_potrerillos.gpkg",
    "datos/inputSimulacion/infraestructura/electricidad_mt_las_lagunas_potrerillos.gpkg",
    "datos/inputSimulacion/barreras/barreras_enlaces_las_lagunas_potrerillos.npz",
    "datos/inputSimulacion/cobertura/cobertura_mapbiomas_col3_2025_las_lagunas_potrerillos.tif",
    "datos/inputSimulacion/sim_v4/manifiesto_datos.yaml",
    "datos/inputSimulacion/sim_v4/estaticos/topografia/mdt.tif",
]


def entorno(version: str) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(RAIZ / "src" / version / "src")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["NUMBA_CACHE_DIR"] = str(Path(tempfile.gettempdir()) / f"numba_cache_simulador_{version}")
    return env


def correr(cmd: list[str], cwd: Path, env: dict[str, str]) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def excluidas(version: str) -> list[str]:
    out = []
    for linea in (RAIZ / "herramientas" / "pruebas_excluidas.txt").read_text(encoding="utf-8").splitlines():
        if linea.strip() and not linea.startswith("#"):
            v, ident, _ = [x.strip() for x in linea.split("|", 2)]
            if v == version:
                out.append(ident)
    return out


def paso_datos() -> bool:
    faltan = [d for d in DATOS_CLAVE if not (RAIZ / d).exists()]
    viento = RAIZ / "datos" / "inputSimulacion" / "viento"
    if not (list(viento.glob("*.nc")) or list(viento.glob("*.nc.part00"))):
        faltan.append("datos/inputSimulacion/viento/*.nc o *.nc.part00")
    for f in faltan:
        print(f"   falta {f}")
    return not faltan


def paso_pruebas(version: str) -> bool:
    cmd = [sys.executable, "-m", "pytest", "-q", f"../../test/{version}", "-p", "no:cacheprovider"]
    for ident in excluidas(version):
        cmd += ["--deselect", ident]
    cod, salida = correr(cmd, RAIZ / "src" / version, entorno(version))
    ultima = [x for x in salida.strip().splitlines() if x.strip()][-1] if salida.strip() else "(sin salida)"
    print(f"   {ultima}")
    if cod != 0:
        print("\n".join("   " + x for x in salida.strip().splitlines()[-30:]))
    return cod == 0


def paso_pruebas_app() -> bool:
    """Pruebas del programa nuevo. Lanzan los dos motores por su cuenta, así que corren sin PYTHONPATH."""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    env.pop("PYTHONPATH", None)
    cod, salida = correr([sys.executable, "-m", "pytest", "-q", "test/app", "-p", "no:cacheprovider"], RAIZ, env)
    ultima = [x for x in salida.strip().splitlines() if x.strip()][-1] if salida.strip() else "(sin salida)"
    print(f"   {ultima}")
    if cod != 0:
        print("\n".join("   " + x for x in salida.strip().splitlines()[-40:]))
    return cod == 0


def paso_humo(version: str, escenario: str) -> bool:
    t = time.time()
    cod, salida = correr([sys.executable, "scripts/correr_escenario.py", "--escenario", escenario], RAIZ / "src" / version, entorno(version))
    lineas = [x for x in salida.strip().splitlines() if x.strip()]
    print(f"   {lineas[-1] if lineas else '(sin salida)'}")
    print(f"   {time.time() - t:.0f} s")
    if cod != 0:
        print("\n".join("   " + x for x in lineas[-20:]))
    return cod == 0


def main() -> int:
    rapido = "--rapido" in sys.argv
    print(f"Python {sys.version.split()[0]} en {sys.platform} · repositorio {RAIZ}")
    pasos: list[tuple[str, bool]] = []

    print("1. Versiones congeladas (sha256)")
    cod, salida = correr([sys.executable, "herramientas/congelado.py", "verificar"], RAIZ, dict(os.environ))
    print("   " + salida.strip().replace("\n", "\n   "))
    pasos.append(("versiones congeladas", cod == 0))

    print("2. Datos del dominio")
    pasos.append(("datos del dominio", paso_datos()))

    for n, version in enumerate(MOTORES, start=3):
        print(f"{n}. Pruebas del motor {version}")
        pasos.append((f"pruebas {version}", paso_pruebas(version)))

    if not rapido:
        for n, (version, escenario) in enumerate(MOTORES.items(), start=5):
            print(f"{n}. Corrida corta con el motor {version} ({escenario}, 6 horas simuladas)")
            pasos.append((f"corrida {version}", paso_humo(version, escenario)))
        if (RAIZ / "test" / "app").exists():
            print("7. Pruebas del simulador (test/app): el proceso motor da lo mismo que la corrida offline")
            pasos.append(("pruebas del simulador", paso_pruebas_app()))

    print("\nResumen")
    for nombre, ok in pasos:
        print(f"   {'BIEN ' if ok else 'FALLA'}  {nombre}")
    todo = all(ok for _, ok in pasos)
    print("\nTodo funciona." if todo else "\nHay fallas: revisar arriba.")
    return 0 if todo else 1


if __name__ == "__main__":
    sys.exit(main())
