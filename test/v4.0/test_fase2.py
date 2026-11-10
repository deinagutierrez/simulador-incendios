"""Fase 2 (docs/v4.0/17): regla de combustible 3.3b, función objetivo de §9 y validación cruzada N−1."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "src" / "v4.0" / "app"
for p in (APP, APP / "banco", APP / "motores", APP / "evaluador"):
    sys.path.insert(0, str(p))

from simulador.fuel.generar_sb40 import generar, ndvi_estructural_anomalia, COD  # noqa: E402

UMB = pd.DataFrame({"clave": ["3", "4", "12", "77"], "clase": ["b", "ba", "h", "aa"],
                    "ndvi_p33": [0.533, 0.491, 0.393, 0.408], "ndvi_p67": [0.597, 0.541, 0.468, 0.455]})


def _paisaje(desvio):
    rng = np.random.default_rng(0)
    lc = np.repeat(np.array([3, 4, 12, 77], "uint8"), 2500).reshape(100, 100)
    ref = {3: 0.565, 4: 0.516, 12: 0.4305, 77: 0.4315}
    ndvi = np.vectorize(ref.get)(lc).astype("float32") + rng.normal(0, 0.04, lc.shape).astype("float32") + desvio
    return lc, ndvi, np.full(lc.shape, 1000.0, "float32"), np.full(lc.shape, 0.0, "float32")


def test_33b_quita_la_anomalia_de_las_lenosas():
    lc, nd0, dem, ndmi = _paisaje(0.0)
    _, nd_seco, _, _ = _paisaje(-0.10)                    # verano seco: el verdor baja parejo en todo el dominio
    est_seco, corr = ndvi_estructural_anomalia(lc, nd_seco, UMB)
    assert corr[3] == pytest.approx(0.10, abs=0.01) and corr[77] == pytest.approx(0.10, abs=0.01)
    assert 12 not in corr                                 # las herbáceas conservan el NDVI del año
    a = generar(lc, dem, nd0, ndmi, UMB)
    b = generar(lc, dem, nd_seco, ndmi, UMB)
    c = generar(lc, dem, nd_seco, ndmi, UMB, ndvi_estructural=est_seco)
    tu1 = COD["TU1"]
    assert (b == tu1).mean() > 2 * (a == tu1).mean()      # regla 3.3: el año seco "adelgaza" el bosque
    assert abs((c == tu1).mean() - (a == tu1).mean()) < 0.02   # regla 3.3b: estructura leñosa estable
    herb = lc == 12
    assert (c[herb] == b[herb]).all()                     # el pasto sigue respondiendo a la sequía


def test_33b_sin_anomalia_casi_identica():
    lc, nd, dem, ndmi = _paisaje(0.0)
    est, corr = ndvi_estructural_anomalia(lc, nd, UMB)
    assert all(abs(v) < 0.01 for v in corr.values())
    assert (generar(lc, dem, nd, ndmi, UMB, ndvi_estructural=est) == generar(lc, dem, nd, ndmi, UMB)).mean() > 0.97


def test_objetivo_y_validacion_cruzada():
    import fase2
    base = dict(degenerado=False, iou_huella_final=np.nan, dt_censurado=False)
    r = pd.Series({**base, "iou_eq": 0.4, "L_T80": np.log(2), "dt_h": 12.0})
    assert fase2.objetivo(r) == pytest.approx(0.6 + 0.5 * np.log(2) + 0.25)
    r = pd.Series({**base, "iou_eq": np.nan, "iou_huella_final": 0.1, "L_T80": -1.0, "dt_h": np.inf, "dt_censurado": True})
    assert fase2.objetivo(r) == pytest.approx(0.9 + 0.5 + 0.5 * 3)
    r = pd.Series({**base, "degenerado": True, "iou_eq": 0.3, "L_T80": -5.5, "dt_h": 8.0})
    assert fase2.objetivo(r) == pytest.approx(0.7)       # instante degenerado: solo la forma
    confs = fase2.configuraciones()
    ids = [c["id"] for c in confs]
    assert len(ids) == len(set(ids)) == 2 + 2 * 3 * 3
    assert {c["regla"] for c in confs} == {"3.3", "3.3b"}
