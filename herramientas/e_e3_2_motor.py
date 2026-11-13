"""Proceso motor con otro juego de compuestos de verano para v4.0. Solo lo usa `herramientas/e_e3_2.py`, parte (c).

    python herramientas/e_e3_2_motor.py --verano CARPETA --corrida resultados/app/<id>

Hace exactamente lo mismo que `app/motores/proceso.py` (lo ejecuta tal cual), con una sola diferencia: antes de empezar,
hace que v4.0 busque los compuestos mensuales `NDVI_NDMI_AAAA_MM.tif` primero en CARPETA. Así el combustible SB40 (regla
3.3b) y el NDVI de verano salen de los compuestos de AWS sin tocar los del repositorio, que el manifiesto de v4.0 controla
por sha256. Es la opción A de `docs/etapa3/F4_informe.md` §5.1 (D-E3-27).

Cómo: `incendios_sl.eventos.ruta_compuesto` (v4.0) recorre la lista que devuelve `dirs_compuestos()` en el momento de
llamarla; acá se reemplaza esa función, dentro de este proceso, por una que pone CARPETA adelante. Ningún archivo de v4.0
cambia. Solo vale para corridas de v4.0: con otro motor se niega.
"""
from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def preparar(verano: Path) -> None:
    sys.path.insert(0, str(REPO / "src" / "v4.0" / "src"))
    from incendios_sl import eventos                      # v4.0
    original = eventos.dirs_compuestos

    def dirs_compuestos() -> list[Path]:
        return [verano] + list(original())

    eventos.dirs_compuestos = dirs_compuestos


def main() -> None:
    args = sys.argv[1:]
    if "--verano" not in args or "--corrida" not in args:
        raise SystemExit("uso: e_e3_2_motor.py --verano CARPETA --corrida CARPETA_DE_LA_CORRIDA")
    i = args.index("--verano")
    verano = Path(args[i + 1]).resolve()
    resto = args[:i] + args[i + 2:]
    if not verano.is_dir() or not list(verano.glob("NDVI_NDMI_*.tif")):
        raise SystemExit(f"--verano {verano}: no hay compuestos NDVI_NDMI_*.tif")
    corrida = Path(resto[resto.index("--corrida") + 1]).resolve()
    motor = json.loads((corrida / "corrida.json").read_text(encoding="utf-8")).get("motor")
    if motor != "v4.0":
        raise SystemExit(f"e_e3_2_motor.py solo sirve para v4.0 (la corrida es {motor})")
    preparar(verano)
    sys.argv = [str(REPO / "app" / "motores" / "proceso.py")] + resto
    runpy.run_path(sys.argv[0], run_name="__main__")      # termina con os._exit, como el proceso motor


if __name__ == "__main__":
    main()
