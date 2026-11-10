"""Recalcula las series de humedad del combustible muerto (ambas variantes: FFMC y retardo de Simard) para los eventos
indicados, a partir de la meteorología del dominio ya descargada. No toca índices, combustibles ni viento.

Uso: python scripts/actualizar_humedad.py [--eventos A,B,...]   (por defecto, todos los eventos con meteorología)
"""
from __future__ import annotations

import argparse
import glob
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from incendios_sl import config as cfgmod  # noqa: E402
from incendios_sl.fuels.humedad import serie_humedad  # noqa: E402

log = logging.getLogger("actualizar_humedad")


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--eventos", default=None); ap.add_argument("--modelo", default="modelo_v2")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg_h = cfgmod.cargar_modelo(a.modelo)["humedad"]
    D = cfgmod.dir_entradas()
    eventos = a.eventos.split(",") if a.eventos else sorted(p.stem for p in (cfgmod.dir_escenarios() / "eventos").glob("*.yaml"))
    for ev in eventos:
        c = sorted(glob.glob(str(D / "meteo" / f"{ev}_*_dominio.csv")))
        if not c:
            log.warning("%s: sin meteorología del dominio; se omite", ev); continue
        dmn = pd.read_csv(c[-1], parse_dates=["time_utc"])
        h = serie_humedad(dmn, cfg_h)
        out = cfgmod.dir_derivados("eventos", ev) / f"humedad_muerto_{ev}.csv"
        h.to_csv(out, index=False)
        log.info("%s: %d horas | 1h FFMC %.1f-%.1f %% | 1h retardo %.1f-%.1f %%", ev, len(h), h.m_1h_pct.min(), h.m_1h_pct.max(), h.m_1h_pct_rt.min(), h.m_1h_pct_rt.max())
    return 0


if __name__ == "__main__":
    sys.exit(main())
