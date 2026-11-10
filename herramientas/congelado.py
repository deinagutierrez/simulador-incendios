"""Control de versiones congeladas: los motores v3.1 y v4.0 no se modifican.

    python herramientas/congelado.py verificar     compara cada archivo con congelado.json (sha256)
    python herramientas/congelado.py generar       escribe congelado.json (solo en la primera subida o por decisión registrada)

Cubre el código, las pruebas y los escenarios de las dos versiones. Ignora lo que se genera al usar (cachés, corridas RT-).
Sale con código 1 si un archivo cambió, falta o sobra.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MANIFIESTO = RAIZ / "congelado.json"
CARPETAS = ["src/v3.1", "src/v4.0", "test/v3.1", "test/v4.0", "escenarios/v3.1", "escenarios/v4.0"]
IGNORAR_DIR = {"__pycache__", ".pytest_cache"}


def _ignorado(p: Path) -> bool:
    partes = p.relative_to(RAIZ).parts
    return (any(x in IGNORAR_DIR or x.endswith(".egg-info") for x in partes) or p.suffix == ".pyc"
            or p.name.startswith("RT-") or any(x.startswith("RT-") for x in partes))


def _archivos() -> dict[str, str]:
    out = {}
    for c in CARPETAS:
        for p in sorted((RAIZ / c).rglob("*")):
            if p.is_file() and not _ignorado(p):
                out[p.relative_to(RAIZ).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def generar() -> int:
    arch = _archivos()
    total = hashlib.sha256("\n".join(f"{k} {v}" for k, v in sorted(arch.items())).encode()).hexdigest()
    MANIFIESTO.write_text(json.dumps({"algoritmo": "sha256", "carpetas": CARPETAS, "n_archivos": len(arch),
                                      "sha256_del_conjunto": total, "archivos": arch}, indent=1, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    print(f"congelado.json: {len(arch)} archivos, sha256 del conjunto {total}")
    return 0


def verificar() -> int:
    if not MANIFIESTO.exists():
        print("falta congelado.json"); return 1
    esperado = json.loads(MANIFIESTO.read_text(encoding="utf-8"))["archivos"]
    actual = _archivos()
    cambiados = sorted(k for k in esperado if k in actual and actual[k] != esperado[k])
    faltan = sorted(k for k in esperado if k not in actual)
    sobran = sorted(k for k in actual if k not in esperado)
    for titulo, lista in (("CAMBIADO", cambiados), ("FALTA", faltan), ("SOBRA", sobran)):
        for k in lista:
            print(f"{titulo}: {k}")
    if cambiados or faltan or sobran:
        print(f"versiones congeladas alteradas: {len(cambiados)} cambiados, {len(faltan)} faltan, {len(sobran)} sobran")
        return 1
    print(f"versiones congeladas intactas ({len(esperado)} archivos)")
    return 0


if __name__ == "__main__":
    orden = sys.argv[1] if len(sys.argv) > 1 else "verificar"
    sys.exit({"generar": generar, "verificar": verificar}.get(orden, verificar)())
