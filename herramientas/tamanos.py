"""Falla si algún archivo versionado supera el límite (GitHub rechaza archivos de más de 100 MB).

    python herramientas/tamanos.py [limite_en_MB]      por defecto 95
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def main() -> int:
    limite = float(sys.argv[1]) if len(sys.argv) > 1 else 95.0
    try:
        lista = subprocess.check_output(["git", "-c", "core.quotepath=false", "ls-files", "-z"], cwd=RAIZ).decode("utf-8").split("\0")
    except (FileNotFoundError, subprocess.CalledProcessError):
        # sin git a mano: se recorre el árbol dejando fuera lo que .gitignore excluye
        fuera = (".git/", ".venv/", "resultados/", "datos/procesados/")
        lista = [p.relative_to(RAIZ).as_posix() for p in RAIZ.rglob("*") if p.is_file()]
        lista = [f for f in lista if not f.startswith(fuera) and "__pycache__" not in f
                 and not (f.startswith("datos/inputSimulacion/viento/") and f.endswith(".nc"))]
    tam = [(os.path.getsize(RAIZ / f), f) for f in lista if f and (RAIZ / f).exists()]
    grandes = sorted((t, f) for t, f in tam if t > limite * 2 ** 20)
    for t, f in grandes:
        print(f"{t / 2 ** 20:8.1f} MB  {f}")
    print(f"{len(tam)} archivos versionados, {sum(t for t, _ in tam) / 2 ** 20:.0f} MB; {len(grandes)} superan {limite:.0f} MB")
    return 1 if grandes else 0


if __name__ == "__main__":
    sys.exit(main())
