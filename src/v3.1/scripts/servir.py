"""Sirve la API y la interfaz web: python scripts/servir.py [--puerto 8000] [--host 127.0.0.1]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--puerto", type=int, default=8000); ap.add_argument("--host", default="127.0.0.1"); ap.add_argument("--recargar", action="store_true")
    a = ap.parse_args(argv)
    import uvicorn
    uvicorn.run("incendios_sl.api.app:app", host=a.host, port=a.puerto, reload=a.recargar, log_level="info")


if __name__ == "__main__":
    main()
