"""Tests de las correcciones de la verificación de V.4 (docs/v4.0/15) y de la compatibilidad con V.4.

- Compatibilidad: con los interruptores de `escenarios/v4.0/modelos/sim_v4_original.yaml` el motor reproduce
  EXACTAMENTE la salida del SIM original (`V.4\\V.4\\app\\simulador_incendios`, importado en un proceso aparte) en
  escenarios sintéticos con viento rotando, pendiente y orientación variables, mosaico de combustibles, caminos,
  índices, noche húmeda y lluvia. Se saltea si la carpeta de V.4 no existe.
- Pruebas propuestas en la auditoría (sección c): referencias GR2/SH2, EMC NFDRS, viento a 20 ft, sin encendido
  instantáneo con rotación de 90°, camino paralelo al viento cruzado solo por la cabeza, extinción reversible,
  retardo de ignición y pavesas invariantes al CFL.
"""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from simulador import sintetico
from simulador.config import fusionar
from simulador.ca.automata import Automata, u01, p_cruce
from simulador.ca import estados as E
from simulador.io.meteo import SerieMeteo
from simulador.fuel.sb40 import TablaCombustible
from simulador.physics.rothermel import rothermel, intensidad_byram
from simulador.physics.humedad import emc_simard
from simulador.physics.viento import F_10M_A_20FT, ParametrosViento, KMH_A_FT_MIN

REPO = Path(__file__).resolve().parents[2]
V4 = REPO.parent / "V.4" / "V.4" / "app" / "simulador_incendios"
MODELO_V4 = REPO / "escenarios" / "v4.0" / "modelos" / "sim_v4_original.yaml"
# interruptores del contrato (se usan si el YAML del modelo todavía no existe)
INTERRUPTORES_V4 = {"parametros": {
    "viento": {"factor_10m_20ft": 1.1494252873563218},
    "humedad": {"emc": "v4_original", "emc_min_pct": 2.0, "curado_solo_dinamicos": False},
    "huygens": None, "extincion": "definitiva", "limite_viento": "rothermel_1972",
    "barreras": {"activo": True, "modo": "umbral_tipo", "llama": "cabeza"},
    "contencion": {"activo": False}, "parada": {"horas_sin_avance": None, "contenido": False}}}
T = TablaCombustible()


def interruptores_v4() -> dict:
    if MODELO_V4.exists():
        return yaml.safe_load(MODELO_V4.read_text(encoding="utf-8")) or {}
    return INTERRUPTORES_V4


# --------------------------------------------------------------------------------------------- escenario común
# Se ejecuta igual en este proceso (paquete v4.0) y en el proceso de V.4 (paquete original).
ESCENARIO = r'''
import numpy as np
import pandas as pd

def construir(sintetico, SerieMeteo, n=81, horas=14):
    cap = sintetico.capas_sinteticas(n, 102, pendiente_deg=12, orientacion_deg=135)
    fil, col = np.indices((n, n))
    cap.pendiente = np.clip(10 + 12 * np.sin(fil / 9.0) * np.cos(col / 11.0), 0, None).astype("float32")
    cap.orientacion = ((fil * 7 + col * 13) % 360).astype("float32")
    cap.plano = cap.pendiente < 1.0
    cap.combustible[:28, :] = 122                      # GS2
    cap.combustible[52:, 44:] = 142                    # SH2
    cap.combustible[60:72, 8:24] = 161                 # TU1
    cap.combustible[10:16, 60:66] = 98                 # agua
    cap.camino_ancho[30, :] = 5.0; cap.camino_tipo[30, :] = 2      # camino de tierra
    cap.camino_ancho[:, 56] = 3.0; cap.camino_tipo[:, 56] = 3      # huella
    cap.ndmi_mes = (0.08 * np.sin(col / 7.0) - 0.05).astype("float32"); cap.ndmi_mes[:6, :6] = np.nan
    cap.ndvi_mes = (0.30 + 0.05 * np.cos(fil / 5.0)).astype("float32"); cap.ndvi_verano = np.full((n, n), 0.45, "float32")
    t0 = pd.Timestamp("2024-01-01T10:00:00-03:00")
    ts = pd.date_range(t0 - pd.Timedelta(hours=24), periods=horas + 26, freq="h")
    h = np.arange(len(ts))
    hr = 25 + 20 * np.sin(h / 24 * 2 * np.pi + 1.0) ** 2
    hr[30:36] = 92.0                                    # noche húmeda (extinción por humedad)
    pr = np.zeros(len(ts)); pr[33] = 2.0
    df = pd.DataFrame({"timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S%z").str.replace(r"(\d{2})(\d{2})$", r"\1:\2", regex=True),
                       "temp_c": 28 - 8 * np.sin(h / 24 * 2 * np.pi) ** 2, "hr_pct": hr,
                       "viento_kmh": 12 + 10 * np.abs(np.sin(h / 5.0)), "viento_dir_deg": (300 + 37 * h) % 360,
                       "precip_mm": pr, "fuente": "sintetico"})
    return cap, SerieMeteo(df), t0

def correr(Automata, cfg, cap, met, t0, horas):
    au = Automata(cap, met, cfg)
    au.preparar(t0, t0 + pd.Timedelta(hours=horas))
    n = cap.grilla.alto
    au.encender(n // 2, n // 2, t0, "a")
    segunda = t0 + pd.Timedelta(hours=3)
    for _ in range(int(round(horas * 60 / cfg["dt_min"]))):
        if segunda is not None and au.t >= segunda:
            au.encender(12, 15, au.t, "b"); segunda = None
        au.paso_tiempo()
    return au
'''

CASOS = {
    "det8": {"dt_min": 2.0, "vecindad": 8},
    "det16": {"dt_min": 5.0, "vecindad": 16},
    "esto8": {"dt_min": 2.0, "vecindad": 8, "modo": "estocastico", "semilla": 3},
    "spot": {"dt_min": 3.0, "vecindad": 8, "semilla": 11, "parametros": {"spotting": {"activo": True, "p_max": 0.02}}},
    "delay": {"dt_min": 2.0, "vecindad": 16, "parametros": {"ignicion_delay_min": 10.0}},   # H5: crédito desde la llegada
}
HORAS = 14

SCRIPT_V4 = r'''
import json, sys
import numpy as np
sys.path.insert(0, sys.argv[1])
from simulador import sintetico
from simulador.io.meteo import SerieMeteo
from simulador.ca.automata import Automata
exec(open(sys.argv[2], encoding="utf-8").read())
caso = json.loads(sys.argv[3])
cap, met, t0 = construir(sintetico, SerieMeteo)
cfg = sintetico.config_sintetica(**caso["over"])
au = correr(Automata, cfg, cap, met, t0, caso["horas"])
np.savez(sys.argv[4], t_llegada=au.t_llegada, estado=au.estado, ros_max=au.ros_max, llama_max=au.llama_max, spots=au.spots)
'''


def _ns_escenario():
    ns = {}
    exec(ESCENARIO, ns)
    return ns


@pytest.fixture(scope="module")
def salidas_v4(tmp_path_factory):
    if not (V4 / "simulador" / "ca" / "automata.py").exists():
        pytest.skip("no está la carpeta de V.4 original")
    d = tmp_path_factory.mktemp("v4")
    (d / "escenario.py").write_text(ESCENARIO, encoding="utf-8")
    (d / "script.py").write_text(SCRIPT_V4, encoding="utf-8")
    out = {}
    for nombre, over in CASOS.items():
        ruta = d / f"{nombre}.npz"
        subprocess.run([sys.executable, "-I", str(d / "script.py"), str(V4), str(d / "escenario.py"),
                        json.dumps({"over": over, "horas": HORAS}), str(ruta)], check=True, cwd=str(d))
        out[nombre] = dict(np.load(ruta))
    return out


@pytest.mark.parametrize("nombre", list(CASOS))
def test_reproduce_v4_original_exacto(salidas_v4, nombre):
    """Con los interruptores de sim_v4_original (el YAML tal cual, sin parches) el t_llegada es idéntico al de V.4
    (bit a bit), también con pavesas (H4) y con retardo de ignición (H5)."""
    assert MODELO_V4.exists()
    ns = _ns_escenario()
    cap, met, t0 = ns["construir"](sintetico, SerieMeteo)
    over = CASOS[nombre]
    cfg = fusionar(fusionar(sintetico.config_sintetica(**over), interruptores_v4()), over)
    au = ns["correr"](Automata, cfg, cap, met, t0, HORAS)
    ref = salidas_v4[nombre]
    assert np.isfinite(ref["t_llegada"]).sum() > 200          # el escenario propaga de verdad
    assert np.array_equal(au.t_llegada, ref["t_llegada"], equal_nan=True)
    assert np.array_equal(au.estado, ref["estado"])
    assert np.array_equal(au.ros_max, ref["ros_max"]) and np.array_equal(au.llama_max, ref["llama_max"])
    assert au.spots == int(ref["spots"])


def test_modelo_corregido_difiere_de_v4(salidas_v4):
    """Control: con los valores por defecto (modelo corregido) la salida NO es la de V.4 (y es menor)."""
    ns = _ns_escenario()
    cap, met, t0 = ns["construir"](sintetico, SerieMeteo)
    au = ns["correr"](Automata, sintetico.config_sintetica(**CASOS["det8"]), cap, met, t0, HORAS)
    ref = salidas_v4["det8"]
    assert not np.array_equal(au.t_llegada, ref["t_llegada"], equal_nan=True)
    assert np.isfinite(au.t_llegada).sum() < np.isfinite(ref["t_llegada"]).sum()


# --------------------------------------------------------------------------------------------- física puntual
def _d1l1(clave, U_ftmin=440.0):
    i = np.array([list(T.clave).index(clave)])
    sal = rothermel(T.w[i], T.sav[i], T.profundidad_ft[i], T.mx_muerto[i], T.calor_muerto[i], T.calor_vivo[i],
                    np.ones(1), np.full(1, .03), np.full(1, .04), np.full(1, .05), np.full(1, .30), np.full(1, .60),
                    np.full(1, U_ftmin), np.zeros(1))
    return sal, sal.R0 * (1 + sal.phi_w)


@pytest.mark.parametrize("clave, ref", [
    ("GR2", {"sigma": 1820, "IR": 1233, "R0": 2.90, "phi_w": 23.8, "R": 72.0, "L": 1.93}),
    ("SH2", {"sigma": 1671.6, "IR": 6343, "R0": 1.006, "phi_w": 11.20, "R": 12.27}),
])
def test_rothermel_referencia(clave, ref):
    """D1L1, curado 1, U = 5 mi/h, plano (cálculo a mano con Andrews 2018; ±2 %)."""
    sal, R = _d1l1(clave)
    val = {"sigma": sal.sigma[0], "IR": sal.IR[0], "R0": sal.R0[0], "phi_w": sal.phi_w[0], "R": R[0],
           "L": intensidad_byram(sal.IR, R, sal.tau_min)[1][0]}
    for k, v in ref.items():
        assert abs(val[k] - v) / v < 0.02, f"{clave} {k}: {val[k]:.4g} vs {v}"


def test_emc_nfdrs():
    e = emc_simard(np.array([30.0, 20.0, 30.0]), np.array([20.0, 50.0, 5.0])) * 100
    assert np.allclose(e, [4.158, 9.623, 1.189], atol=2e-3)
    # V.4 original (coeficientes °C con T en °F, piso 2 %)
    assert abs(emc_simard(30.0, 20.0, "v4_original", 2.0) * 100 - 2.674) < 2e-3
    assert emc_simard(30.0, 5.0, "v4_original", 2.0) == 0.02


def test_viento_altura():
    assert abs(F_10M_A_20FT - 0.87) < 1e-3 and ParametrosViento().factor_10m_20ft == F_10M_A_20FT
    i = list(T.clave).index("GR2")
    U_mf = 20 * KMH_A_FT_MIN * ParametrosViento().factor_10m_20ft * T.waf()[i] / 88.0
    assert abs(U_mf - 3.91) / 3.91 < 0.02


def test_u01_igual_a_v3():
    """El hash vectorizado coincide con la definición de v3.0 (splitmix64 con aritmética módulo 2^64)."""
    M = 2 ** 64 - 1
    def ref(s, i, j, k, h):
        x = (s * 0x9E3779B97F4A7C15) & M
        x ^= ((i + 1) * 0xBF58476D1CE4E5B9) & M
        x ^= ((j + 1) * 0x94D049BB133111EB) & M
        x ^= ((k + 1) * 0xD6E8FEB86659FD93) & M
        x ^= ((h + 1) * 0xA0761D6478BD642F) & M
        x ^= x >> 30; x = (x * 0xBF58476D1CE4E5B9) & M
        x ^= x >> 27; x = (x * 0x94D049BB133111EB) & M
        x ^= x >> 31
        return (x >> 11) / 9007199254740992.0
    i = np.array([0, 5, 1000, 3]); j = np.array([0, 7, 2000, 1]); k = np.array([0, 3, 15, 7]); h = np.array([0, 1, 50, 2])
    u = u01(20261015, i, j, k, h)
    assert np.array_equal(u, [ref(20261015, *t) for t in zip(i.tolist(), j.tolist(), k.tolist(), h.tolist())])
    v = u01(1, np.arange(20000) // 141, np.arange(20000) % 141, 3, 0)
    assert abs(v.mean() - 0.5) < 0.01 and 0 <= v.min() and v.max() < 1


def test_p_cruce():
    P = p_cruce(np.array([0.5, 1.0, 2.0, 1.0]), np.array([1.0, 1.0, 1.0, 0.0]), "probabilistico", 1.0, 4.0)
    assert P[0] < 0.5 and abs(P[1] - 0.5) < 1e-12 and P[2] > 0.5 and P[3] == 1.0
    assert list(p_cruce(np.array([0.9, 1.1]), np.array([1.0, 1.0]), "umbral", 1.0, 4.0)) == [0.0, 1.0]


# --------------------------------------------------------------------------------------------- autómata
def _meteo_serie(t0, horas, viento, direccion, hr, temp=30.0, precip=None):
    t0 = pd.Timestamp(t0)
    ts = pd.date_range(t0 - pd.Timedelta(hours=24), periods=horas + 26, freq="h")
    n = len(ts)
    f = lambda v: np.asarray(v(np.arange(n) - 24) if callable(v) else np.full(n, v), float)
    df = pd.DataFrame({"timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S%z").str.replace(r"(\d{2})(\d{2})$", r"\1:\2", regex=True),
                       "temp_c": f(temp), "hr_pct": f(hr), "viento_kmh": f(viento), "viento_dir_deg": f(direccion),
                       "precip_mm": f(precip) if precip is not None else 0.0, "fuente": "t"})
    return SerieMeteo(df)


def _violaciones_encendido(au):
    """Fracción de celdas encendidas antes que lo permitido por la física local: t(celda) − min t(vecinas
    encendidas antes) < 0,5·30 m / R_max local (máximo de la celda y sus vecinas)."""
    t = au.t_llegada; R = au.ros_max
    H, W = t.shape
    tp = np.pad(t, 1, constant_values=np.nan); Rp = np.pad(R, 1)
    vec_t = np.stack([tp[1 + a:1 + a + H, 1 + b:1 + b + W] for a in (-1, 0, 1) for b in (-1, 0, 1) if (a, b) != (0, 0)])
    vec_R = np.stack([Rp[1 + a:1 + a + H, 1 + b:1 + b + W] for a in (-1, 0, 1) for b in (-1, 0, 1)])
    antes = np.where(vec_t < t[None], vec_t, np.inf)
    t_prev = antes.min(0)
    m = np.isfinite(t) & np.isfinite(t_prev)
    Rloc = vec_R.max(0)
    viol = m & ((t - t_prev) < 0.5 * 30.0 / np.maximum(Rloc, 1e-6))
    return viol.sum() / max(m.sum(), 1)


@pytest.mark.parametrize("escenario", ["rotacion", "pendiente"])
def test_sin_encendido_instantaneo(escenario):
    """P3: con rotación de 90° del viento (o rumbo variable por pendiente) la herencia de origen de V.4 enciende
    celdas de golpe; con `huygens` el frente respeta d/R_max."""
    t0 = "2024-01-01T12:00:00-03:00"
    if escenario == "rotacion":
        cap = sintetico.capas_sinteticas(161, 102)
        met = _meteo_serie(t0, 4, 20.0, lambda h: np.where(h < 1, 0.0, 90.0), 20.0)
    else:
        cap = sintetico.capas_sinteticas(161, 102, pendiente_deg=20, orientacion_deg=0)
        cap.orientacion = np.random.default_rng(0).uniform(0, 360, cap.shape).astype("float32")
        met = _meteo_serie(t0, 4, 10.0, 0.0, 20.0)
    viol = {}
    for nombre, hy in (("v4", None), ("nuevo", {"tol_rumbo_deg": 15.0, "tol_e": 0.05})):
        cfg = sintetico.config_sintetica(parametros={"huygens": hy})
        au = sintetico.correr_sintetico(cap, met, cfg, horas=2.5 if escenario == "rotacion" else 2.0, t0=t0)
        viol[nombre] = _violaciones_encendido(au)
    assert viol["nuevo"] < 0.01, viol
    assert viol["v4"] > 3 * viol["nuevo"] + 0.005, viol


def _camino_vertical(llama):
    cap = sintetico.capas_sinteticas(121, 102)
    cap.camino_ancho[:, 64] = 5.0; cap.camino_tipo[:, 64] = 2          # tierra, umbral 1 m, paralelo al viento
    cap.camino_ancho[85, :] = 5.0; cap.camino_tipo[85, :] = 2          # perpendicular, delante de la cabeza
    met = sintetico.meteo_constante(viento_kmh=25, viento_dir_deg=0, hr_pct=12, temp_c=32)
    cfg = sintetico.config_sintetica(parametros={"barreras": {"activo": True, "modo": "umbral_tipo", "llama": llama}})
    au = sintetico.correr_sintetico(cap, met, cfg, horas=2.0, fila=40, col=60)
    return au


def test_camino_flancos():
    """P4: camino de tierra (1 m) paralelo al viento: con la llama direccional solo lo cruza la cabeza (el flanco
    no pasa al otro lado); con la llama de cabeza (V.4) el flanco también lo cruza."""
    au = _camino_vertical("direccional")
    assert au.llama_max.max() > 1.0                                    # la cabeza supera el umbral
    assert au.afectada[87:, :64].any()                                 # la cabeza cruzó el camino perpendicular
    lado_este_dir = au.afectada[:, 64:].sum()
    au_v4 = _camino_vertical("cabeza")
    lado_este_v4 = au_v4.afectada[:, 65:].sum()
    assert lado_este_dir == 0 and lado_este_v4 > 20, (lado_este_dir, lado_este_v4)


def test_extincion_reversible():
    """P5: noche con HR 95 % (R = 0) y después un día seco: con `reversible` el fuego retoma desde el perímetro;
    con `definitiva` (V.4) se apaga."""
    t0 = "2024-01-01T12:00:00-03:00"
    met = _meteo_serie(t0, 12, 10.0, 0.0, lambda h: np.where((h >= 1) & (h < 5), 95.0, 15.0), temp=lambda h: np.where((h >= 1) & (h < 5), 10.0, 30.0))
    areas = {}
    for ext in ("reversible", "definitiva"):
        cap = sintetico.capas_sinteticas(121, 102)
        au = Automata(cap, met, sintetico.config_sintetica(parametros={"extincion": ext}))
        au.preparar(pd.Timestamp(t0), pd.Timestamp(t0) + pd.Timedelta(hours=8))
        au.encender(60, 60, pd.Timestamp(t0))
        for _ in range(int(60 / au.dt)):
            au.paso_tiempo()
        a1 = au.area_quemada_ha()
        for _ in range(int(7 * 60 / au.dt)):
            au.paso_tiempo()
        areas[ext] = (a1, au.area_quemada_ha())
    assert areas["reversible"][1] > 1.5 * areas["reversible"][0]
    assert areas["definitiva"][1] < 1.2 * areas["definitiva"][0]


def test_delay_ignicion():
    """P7: con `ignicion_delay_min = 10` la primera vecina (que espera 10 min en IGNICION) enciende a las suyas
    ≥ 10 min más tarde que con 0 (V.4 anulaba el retardo con el crédito contado desde la llegada)."""
    cap = sintetico.capas_sinteticas(41, 102); met = sintetico.meteo_constante(viento_kmh=15, hr_pct=20)
    t2 = {}
    for d in (0.0, 10.0):
        au = sintetico.correr_sintetico(cap, met, sintetico.config_sintetica(parametros={"ignicion_delay_min": d}), horas=1.0)
        anillo2 = np.zeros(cap.shape, bool); anillo2[18:23, 18:23] = True; anillo2[19:22, 19:22] = False
        t2[d] = np.nanmin(np.where(anillo2, au.t_llegada, np.nan))
    assert t2[10.0] - t2[0.0] >= 10.0 - 1e-3, t2


def test_spotting_invariante_cfl():
    """P8: el número medio de pavesas no depende del CFL (sub-paso) con p ajustada a dt_sub (±15 %, ensamble 20)."""
    met = sintetico.meteo_constante(viento_kmh=25, viento_dir_deg=0, hr_pct=12, temp_c=32)
    medias = {}
    for cfl in (0.9, 0.3):
        n = []
        for s in range(20):
            cap = sintetico.capas_sinteticas(81, 102)
            cfg = sintetico.config_sintetica(semilla=100 + s, parametros={"cfl": cfl, "spotting": {"activo": True, "p_max": 0.1}})
            n.append(sintetico.correr_sintetico(cap, met, cfg, horas=1.0, fila=20, col=40).spots)
        medias[cfl] = np.mean(n)
    assert medias[0.9] > 5
    assert abs(medias[0.3] - medias[0.9]) / medias[0.9] < 0.15, medias


# --------------------------------------------------------------------------------------------- opciones
def test_barreras_probabilistico_reproducible_y_bloquea():
    cap = sintetico.capas_sinteticas(81, 102)
    cap.camino_ancho[55, :] = 8.0; cap.camino_tipo[55, :] = 0
    met = sintetico.meteo_constante(viento_kmh=15, viento_dir_deg=0, hr_pct=20)
    def correr(**b):
        cfg = sintetico.config_sintetica(parametros={"barreras": dict({"activo": True, "modo": "probabilistico"}, **b)})
        return sintetico.correr_sintetico(cap, met, cfg, horas=2.0, fila=40, col=40)
    a1, a2 = correr(), correr()
    assert np.array_equal(a1.t_llegada, a2.t_llegada, equal_nan=True)
    assert a1.bloqueos_barrera.sum() > 0
    libre = correr(activo=False)
    muro = correr(**{"lambda": 50.0, "beta": 20.0})
    assert not muro.afectada[56:].any() and libre.afectada[56:].any()


def test_k_y_factor_waf():
    cap = sintetico.capas_sinteticas(61, 102); met = sintetico.meteo_constante(viento_kmh=10, hr_pct=20)
    def area(**pp):
        return sintetico.correr_sintetico(cap, met, sintetico.config_sintetica(parametros={"propagacion": pp}), horas=1.0).area_quemada_ha()
    a0 = area()
    assert area(k_global=2.0) > 1.5 * a0
    assert area(k_grupo={"GR": 0.5}) < a0 and area(k_codigo={102: 0.5}) == area(k_grupo={"GR": 0.5})
    assert area(factor_waf=0.5) < a0


def test_lluvia_24h_extincion():
    t0 = "2024-01-01T12:00:00-03:00"
    met = _meteo_serie(t0, 4, 10.0, 0.0, 20.0, precip=lambda h: np.where(h == -2, 20.0, 0.0))
    cap = sintetico.capas_sinteticas(41, 102)
    cfg = sintetico.config_sintetica(parametros={"humedad": {"lluvia_24h_mm_extincion": 15.0, "metodo_muerto": "fija",
                                                             "fija_m1": 0.04, "fija_m10": 0.05, "fija_m100": 0.06}})
    au = sintetico.correr_sintetico(cap, met, cfg, horas=1.0, t0=t0)
    assert au.ultimo_lluvia_ext and au.afectada.sum() == 1


def test_humedad_viva_minmax_separada():
    cap = sintetico.capas_sinteticas(21, 121)
    cap.ndmi_mes = np.full(cap.shape, 0.15, "float32")
    au = Automata(cap, sintetico.meteo_constante(), sintetico.config_sintetica(parametros={"humedad": {"viva_metodo": "minmax"}}))
    assert abs(au.m_herb[0, 0] - 0.75) < 1e-6 and abs(au.m_lenoso[0, 0] - 1.05) < 1e-6
    au = Automata(cap, sintetico.meteo_constante(), sintetico.config_sintetica(parametros={"humedad": {"viva_metodo": "fija", "viva_fija": {"herb": 0.4, "lenoso": 0.9}}}))
    assert abs(au.m_herb[0, 0] - 0.4) < 1e-6 and abs(au.m_lenoso[0, 0] - 0.9) < 1e-6
    with pytest.raises(ValueError):
        Automata(cap, sintetico.meteo_constante(), sintetico.config_sintetica(parametros={"humedad": {"metodo_muerto": "fija"}}))


def test_mx_grupo_y_codigo():
    cap = sintetico.capas_sinteticas(21, 102)
    au = Automata(cap, sintetico.meteo_constante(), sintetico.config_sintetica(parametros={"humedad": {"mx_grupo": {"GR": 25}, "mx_codigo": {101: 0.3}}}))
    i = T.idx_por_codigo
    assert au.mx_modelo[i[102]] == 0.25 and au.mx_modelo[i[101]] == 0.3 and au.mx_modelo[i[142]] == 0.15


def test_credito_desde_activacion_v4():
    """H5: `credito_desde_activacion: false` (V.4) cuenta el crédito desde la llegada y anula el retardo de ignición;
    el YAML sim_v4_original lo trae en false y modelo_v3 en true."""
    cap = sintetico.capas_sinteticas(41, 102); met = sintetico.meteo_constante(viento_kmh=15, hr_pct=20)
    anillo2 = np.zeros(cap.shape, bool); anillo2[18:23, 18:23] = True; anillo2[19:22, 19:22] = False
    t2 = {}
    for cred in (True, False):
        for d in (0.0, 10.0):
            cfg = sintetico.config_sintetica(parametros={"ignicion_delay_min": d, "credito_desde_activacion": cred})
            au = sintetico.correr_sintetico(cap, met, cfg, horas=1.0)
            t2[cred, d] = np.nanmin(np.where(anillo2, au.t_llegada, np.nan))
    assert t2[True, 10.0] - t2[True, 0.0] >= 10.0 - 1e-3, t2
    assert t2[False, 10.0] - t2[False, 0.0] < 10.0 - 1e-3, t2
    assert t2[False, 0.0] == t2[True, 0.0]
    p4 = interruptores_v4()["parametros"]
    p3 = yaml.safe_load((MODELO_V4.parent / "modelo_v3.yaml").read_text(encoding="utf-8"))["parametros"]
    assert p4["credito_desde_activacion"] is False and p4["spotting"]["por_unidad_tiempo"] is False
    assert p3["credito_desde_activacion"] is True


def test_modelo_v3_andrews_y_normalizar():
    """H6 y límite de viento: modelo_v3 usa andrews_2013 (Andrews, Cruz y Rothermel 2013) y la logística normalizada."""
    p3 = yaml.safe_load((MODELO_V4.parent / "modelo_v3.yaml").read_text(encoding="utf-8"))["parametros"]
    assert p3["limite_viento"] == "andrews_2013" and p3["barreras"]["normalizar"] is True
    au = Automata(sintetico.capas_sinteticas(11, 102), sintetico.meteo_constante(), fusionar(sintetico.config_sintetica(), {"parametros": p3}))
    assert au.limite_viento == "andrews_2013" and au.bar_normalizar
    assert interruptores_v4()["parametros"]["limite_viento"] == "rothermel_1972"


def test_p_cruce_normalizado():
    """H6: P = (σ(x) − σ(0))/(1 − σ(0)): P(L=0) = 0, monótona, → 1; sin normalizar queda la de v3.0 (piso σ(0))."""
    x = np.linspace(0.0, 4.0, 81)
    P = p_cruce(x * 5.0, np.full_like(x, 5.0), "probabilistico", 1.0, 4.0, normalizar=True)
    P0 = p_cruce(x * 5.0, np.full_like(x, 5.0), "probabilistico", 1.0, 4.0)
    s0 = 1.0 / (1.0 + np.exp(4.0))
    assert P[0] == 0.0 and abs(P0[0] - s0) < 1e-12 and np.all(np.diff(P) > 0) and P[-1] > 0.9999
    assert np.allclose(P, (P0 - s0) / (1 - s0))
    assert p_cruce(0.0, 0.0, "probabilistico", 1.0, 4.0, normalizar=True) == 1.0      # sin camino → cruza
    # camino de tierra de 5 m paralelo al viento: el flanco (L ≈ 0) ya no lo cruza por el piso de la logística
    cap = sintetico.capas_sinteticas(121, 102)
    cap.camino_ancho[:, 64] = 5.0; cap.camino_tipo[:, 64] = 2
    met = sintetico.meteo_constante(viento_kmh=25, viento_dir_deg=0, hr_pct=12, temp_c=32)
    otro = {}
    for norm in (False, True):
        cfg = sintetico.config_sintetica(parametros={"barreras": {"activo": True, "modo": "probabilistico", "normalizar": norm}})
        au = sintetico.correr_sintetico(cap, met, cfg, horas=2.0, fila=40, col=60)
        otro[norm] = (int(au.afectada[:, 65:].sum()), int(au.cruces_barrera.sum()))
    assert otro[True][0] == 0 and otro[False][0] > 0 and otro[True][1] < otro[False][1], otro


@pytest.mark.parametrize("modo", ["probabilistico", "umbral"])
def test_barrera_por_enlace_vecindad16(modo):
    """H1: con vecindad 16 los saltos de caballo evalúan la barrera de las celdas intermedias: un camino de 8 m que
    funciona como muro deja 0 celdas del otro lado (antes 89); sin barreras sí cruza."""
    cap = sintetico.capas_sinteticas(81, 102)
    cap.camino_ancho[55, :] = 8.0; cap.camino_tipo[55, :] = 0
    met = sintetico.meteo_constante(viento_kmh=15, viento_dir_deg=0, hr_pct=20)
    muro = {"activo": True, "modo": modo, "lambda": 50.0, "beta": 20.0}
    for vec in (8, 16):
        au = sintetico.correr_sintetico(cap, met, sintetico.config_sintetica(vecindad=vec, parametros={"barreras": muro}), horas=2.0, fila=40, col=40)
        assert au.afectada[54].any() and not au.afectada[55:].any(), (vec, int(au.afectada[56:].sum()))
    libre = sintetico.correr_sintetico(cap, met, sintetico.config_sintetica(vecindad=16, parametros={"barreras": {"activo": False}}), horas=2.0, fila=40, col=40)
    assert libre.afectada[56:].sum() > 20


@pytest.mark.parametrize("vecindad", [8, 16])
def test_barrera_diagonal_esquinas(vecindad):
    """H3: cortafuego extra de 10 m a 45° exactos por los centros (cadena de 8 conexión, sin cierre ortogonal): las
    diagonales verifican sus dos ortogonales y los caballos las celdas que cruza el segmento → 0 celdas del otro lado."""
    import geopandas as gpd
    from shapely.geometry import LineString
    from simulador.io.capas import rasterizar_barreras_extra
    cap = sintetico.capas_sinteticas(81, 102); g = cap.grilla
    linea = LineString([(0.5 * 30, g.ymax - 0.5 * 30), (80.5 * 30, g.ymax - 80.5 * 30)])
    rasterizar_barreras_extra(cap, gpd.GeoDataFrame({"ancho_m": [10.0]}, geometry=[linea], crs=g.crs))
    m = cap.camino_ancho > 0
    assert (m[:-1, :-1] & m[1:, 1:] & ~m[:-1, 1:] & ~m[1:, :-1]).sum() > 50          # esquinas abiertas en el raster
    met = sintetico.meteo_constante(viento_kmh=15, viento_dir_deg=0, hr_pct=20)
    fi, ci = np.indices(cap.shape)
    muro = {"activo": True, "modo": "probabilistico", "lambda": 50.0, "beta": 20.0}
    au = sintetico.correr_sintetico(cap, met, sintetico.config_sintetica(vecindad=vecindad, parametros={"barreras": muro}), horas=2.0, fila=30, col=45)
    assert (au.afectada & (ci > fi)).sum() > 100
    assert not (au.afectada & (ci < fi)).any() and not (au.afectada & m).any()
    libre = sintetico.correr_sintetico(cap, met, sintetico.config_sintetica(vecindad=vecindad, parametros={"barreras": {"activo": False}}), horas=2.0, fila=30, col=45)
    assert (libre.afectada & (ci < fi)).sum() > 20


def test_intermedias_enlaces():
    """Celdas intermedias: diagonal → sus dos ortogonales; caballo → el par de V.4 más las que cruza el segmento."""
    f = Automata._intermedias
    assert f(-1, 0) == [] and sorted(f(1, -1)) == [(0, -1), (1, 0)]
    assert sorted(f(-2, 1)) == [(-2, 0), (-1, 0), (-1, 1)] and sorted(f(1, 2)) == [(0, 1), (0, 2), (1, 1)]


def test_n_latentes():
    """H2: con extinción reversible, en la noche húmeda (R = 0) las celdas del perímetro quedan latentes
    (`n_latentes` > 0); de día seco es 0, y con `definitiva` no quedan latentes al cumplir la residencia."""
    t0 = "2024-01-01T12:00:00-03:00"
    met = _meteo_serie(t0, 8, 10.0, 0.0, lambda h: np.where((h >= 1) & (h < 5), 95.0, 15.0), temp=lambda h: np.where((h >= 1) & (h < 5), 10.0, 30.0))
    for ext in ("reversible", "definitiva"):
        au = Automata(sintetico.capas_sinteticas(121, 102), met, sintetico.config_sintetica(parametros={"extincion": ext}))
        au.preparar(pd.Timestamp(t0), pd.Timestamp(t0) + pd.Timedelta(hours=8))
        au.encender(60, 60, pd.Timestamp(t0))
        serie = []
        for _ in range(int(7 * 60 / au.dt)):
            au.paso_tiempo()
            serie.append(au.n_latentes)
        serie = np.array(serie); paso_h = int(60 / au.dt)
        assert serie[: paso_h // 2].max() == 0                        # primera media hora seca (la HR se interpola)
        if ext == "reversible":
            assert serie[int(2.5 * paso_h)] > 10 and serie[-1] == 0, serie[::paso_h]
        else:
            assert serie[int(2.5 * paso_h)] == 0


# --------------------------------------------------------------------------------------------- ganchos (contención)
def _au_ganchos(**kw):
    cap = sintetico.capas_sinteticas(61, 102)
    met = sintetico.meteo_constante(viento_kmh=20, viento_dir_deg=0, hr_pct=15)
    cfg = sintetico.config_sintetica(**kw)
    au = Automata(cap, met, cfg)
    t0 = pd.Timestamp("2024-01-01T12:00:00-03:00")
    au.preparar(t0, t0 + pd.Timedelta(hours=2))
    return au, t0


def test_gancho_filtro_enlaces():
    """`filtro_enlaces` (n, K): None y un filtro todo True dan la misma salida; un filtro que prohíbe los enlaces hacia
    el S deja el fuego al N de la ignición."""
    sal = {}
    for nombre, filtro in (("none", None), ("true", lambda idx: np.ones((len(idx), 8), bool)),
                           ("sin_sur", lambda idx: np.broadcast_to(E.vecindad(8, 30.0)[0] <= 0, (len(idx), 8)))):
        au, t0 = _au_ganchos()
        au.filtro_enlaces = filtro
        au.encender(30, 30, t0)
        for _ in range(30):
            au.paso_tiempo()
        sal[nombre] = au
    assert np.array_equal(sal["none"].t_llegada, sal["true"].t_llegada, equal_nan=True)
    assert sal["none"].afectada[31:].sum() > 20 and not sal["sin_sur"].afectada[31:].any() and sal["sin_sur"].afectada.sum() > 1


def test_gancho_fisica_celdas():
    """`fisica_celdas` da lo mismo que `_ros_activas` sobre la banda y no toca la banda ni `ultimo_*`."""
    au, t0 = _au_ganchos()
    au.encender(30, 30, t0)
    for _ in range(5):
        au.paso_tiempo()
    act = au.act.copy(); um = au.ultimo_meteo; uh = au.ultimo_hum
    s = au.fisica_celdas(np.concatenate([act, [0, 61 * 61 - 1]]), au.t)
    assert set(s) == {"R_max", "rumbo", "e", "IB", "llama", "tau", "ext"} and len(s["R_max"]) == len(act) + 2
    assert np.array_equal(au.act, act) and au.ultimo_meteo is um and au.ultimo_hum == uh
    ref = au._ros_activas(au.t)
    for i, k in enumerate(("R_max", "rumbo", "e", "IB", "llama", "tau", "ext")):
        assert np.array_equal(np.asarray(ref[i]), np.asarray(s[k])[: len(act)])
    assert s["R_max"][-1] > 0 and len(au.fisica_celdas(np.zeros(0, np.int64), au.t)["IB"]) == 0


def test_gancho_intensidad_enlaces():
    """`intensidad_enlaces`: (n, K), 0 donde no hay pendiente, ≤ I de cabeza y = I_cab·R(θ_k)/R_max."""
    from simulador.physics.elipse import ros_direccional
    au, t0 = _au_ganchos()
    au.encender(30, 30, t0)
    for _ in range(10):
        au.paso_tiempo()
    I = au.intensidad_enlaces(slice(None))
    assert I.shape == (len(au.act), au.K) and np.all(I[~au.act_pend] == 0) and (I > 0).any()
    assert np.all(I <= au.act_IB[:, None] * (1 + 1e-6))
    sel = np.flatnonzero(au.act_pend.any(1))[:5]
    f, c = np.divmod(au.act[sel], au.W)
    rel = ros_direccional(1.0, au.excentricidad[f, c].astype(float)[:, None], au.rumbo[None, :] - au.rumbo_cab[f, c].astype(float)[:, None])
    assert np.allclose(au.intensidad_enlaces(sel), np.where(au.act_pend[sel], au.act_IB[sel, None] * rel, 0.0))
    m = np.zeros(len(au.act), bool); m[sel] = True                     # también acepta máscaras
    assert np.array_equal(au.intensidad_enlaces(m), au.intensidad_enlaces(np.sort(sel)))


def test_limite_viento_andrews():
    i = np.array([list(T.clave).index("GR1")])
    args = (T.w[i], T.sav[i], T.profundidad_ft[i], T.mx_muerto[i], T.calor_muerto[i], T.calor_vivo[i], np.ones(1),
            np.full(1, .03), np.full(1, .04), np.full(1, .05), np.full(1, .3), np.full(1, .6), np.full(1, 2500.0), np.zeros(1))
    from simulador.physics.rothermel import combinar_viento_pendiente
    def R(lim):
        sal = rothermel(*args, True, lim)
        return combinar_viento_pendiente(sal, np.zeros(1), np.zeros(1), np.ones(1, bool))
    r72, r13, r0 = R("rothermel_1972"), R("andrews_2013"), R("ninguno")
    sal = rothermel(*args, True, "andrews_2013")
    assert r13[2][0] <= 96.8 * np.cbrt(sal.IR[0]) + 1e-9 and r0[2][0] > r13[2][0]
    assert r72[0][0] < r0[0][0]
