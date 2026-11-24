"""Combate común sobre el motor v4.0 (app/motores/combate_v40.py; decisión D-E3-36).

En el mismo proceso, sobre la grilla sintética del propio motor (`simulador.sintetico`, segundos): las piezas comunes dan
lo mismo que las del motor (hash, corte de enlaces), el adaptador no toca el autómata hasta el primer despacho, la línea
frena el fuego (también con vecindad 16), una celda reavivada vuelve a propagar desde ese momento, y todo es determinista.
Descargas aéreas: el agua delante del fuego lo demora una hora y después el fuego sigue; el retardante aguanta y el fuego lo
rodea; sobre el frente frena lo que arde; con bomberos, el agua queda asegurada; de noche y pasado el tope se rechazan.
Las corridas con el proceso motor real están en test_combate_motores.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app" / "motores"))
# al final: solo hace falta el paquete `simulador` de v4.0, y así no le gana a ningún `incendios_sl` de otra prueba
sys.path.append(str(REPO / "src" / "v4.0" / "src"))

import combate as cb  # noqa: E402
import intervenciones as iv  # noqa: E402

N = 121
C = N // 2
T0 = "2024-01-01T12:00:00-03:00"


def _distintas(a: np.ndarray, b: np.ndarray) -> int:
    return int((~((a == b) | (np.isnan(a) & np.isnan(b)))).sum())


def _correr(horas: int, despachos: dict | None = None, vecindad: int = 8, al_paso=None, parametros: dict | None = None):
    """El autómata desde el centro con viento, con el orden del conductor (`motor_v40.AutomataControlado`): en cada hora en
    punto, las intervenciones de esa hora, el paso de combate y recién después el avance. `al_paso(h, au, co, ad)` se llama
    antes de las intervenciones de la hora h."""
    import pandas as pd
    import combate_v40
    from simulador import sintetico as S
    from simulador.ca.automata import Automata
    cfg = S.config_sintetica(vecindad=vecindad, **({"parametros": parametros} if parametros else {}))
    meteo = S.meteo_constante(T0, horas=48, viento_kmh=25, viento_dir_deg=20)
    au = Automata(S.capas_sinteticas(N), meteo, cfg)
    t0 = pd.Timestamp(T0)
    au.preparar(t0, t0 + pd.Timedelta(hours=horas))
    au.encender(C, C, t0, "centro")
    ad = combate_v40.AdaptadorV40(au)
    co = ad.combate = cb.Combate(ad)
    respuestas = []
    for _ in range(int(round(horas * 60 / cfg["dt_min"]))):
        t = au.minutos(au.t)
        if abs(t / 60.0 - round(t / 60.0)) < 1e-9:
            h = int(round(t / 60.0))
            if al_paso:
                al_paso(h, au, co, ad)
            for d in (despachos or {}).get(h, []):
                respuestas.append(co.intervenir(iv.validar_entrada({"tipo": "dotacion", "datos": d}), t))
            co.paso_hora(t)
        au.paso_tiempo()
    return au, co, respuestas


# ------------------------------------------------------------------------------------------------ piezas comunes = las del motor
def test_el_hash_comun_es_el_del_motor():
    from simulador.ca.automata import u01
    f, c = np.divmod(np.arange(5000), 70)
    for k, h in ((99, 0), (99, 17), (3, 240)):
        assert np.array_equal(cb.u01(cb.SEMILLA, f, c, k, h), u01(cb.SEMILLA, f, c, k, h))


def test_el_corte_de_enlaces_comun_es_el_del_motor():
    from simulador.ca import contencion, estados as E
    rng = np.random.default_rng(7)
    linea = rng.random((40, 40)) < 0.2
    f, c = (a.ravel() for a in np.mgrid[2:38, 2:38])
    df, dc, _, _ = E.vecindad(16, 30.0)
    for a, b in zip(df.tolist(), dc.tolist()):
        assert np.array_equal(cb.cortado(linea, f, c, a, b), contencion.cortado(linea, f, c, a, b)), (a, b)


def test_el_perimetro_exterior_comun_es_el_del_motor():
    from simulador.ca import contencion
    au, co, _ = _correr(3)
    ext, r0, c0 = cb.exterior(co.ad.afectada(), co.ad.combustible())
    ext_motor, r0m, c0m = contencion.exterior(au)
    assert (r0, c0) == (r0m, c0m) and np.array_equal(ext, ext_motor)


# ------------------------------------------------------------------------------------------------ el adaptador
def test_sin_despachos_el_automata_no_se_toca():
    import pandas as pd
    from simulador import sintetico as S
    from simulador.ca.automata import Automata
    con, co, _ = _correr(6)
    assert con.filtro_enlaces is None and not co.habilitado and co.informe() is None
    cfg = S.config_sintetica(vecindad=8)
    solo = Automata(S.capas_sinteticas(N), S.meteo_constante(T0, horas=48, viento_kmh=25, viento_dir_deg=20), cfg)
    t0 = pd.Timestamp(T0)
    solo.preparar(t0, t0 + pd.Timedelta(hours=6))
    solo.encender(C, C, t0, "centro")
    for _ in range(int(round(6 * 60 / cfg["dt_min"]))):
        solo.paso_tiempo()
    assert _distintas(solo.t_llegada, con.t_llegada) == 0 and int((solo.estado != con.estado).sum()) == 0


@pytest.mark.parametrize("vecindad", [8, 16])
def test_la_linea_frena_el_fuego(vecindad):
    libre, _, _ = _correr(6, vecindad=vecindad)
    au, co, r = _correr(6, {1: [{"bomberos": 400}]}, vecindad=vecindad)            # 8.000 m/h: alcanza para todo el borde
    assert r[0]["estado"] == "aceptada" and au.filtro_enlaces is not None
    h = {x["h"]: x for x in co.horas}
    assert h[2]["celdas_nuevas"] == h[2]["frente_celdas"] > 0 and h[2]["frente_sostenible"] == h[2]["frente_celdas"]
    assert all(h[k]["celdas_nuevas"] == 0 and h[k]["frente_celdas"] == 0 for k in (3, 4, 5))
    # nada se enciende después de la hora 2: ni por el costado de la línea, ni por las esquinas, ni saltándola
    assert np.nanmax(au.t_llegada) <= 120.0 + 1e-6
    assert au.area_quemada_ha() < 0.5 * libre.area_quemada_ha()
    assert co.linea.sum() == h[2]["celdas_nuevas"] and (au.t_llegada[co.linea] <= 120.0 + 1e-6).all()


def test_pocas_dotaciones_frenan_solo_donde_hay_linea():
    libre, _, _ = _correr(6)
    au, co, _ = _correr(6, {1: [{"bomberos": 30}]})                               # 600 m/h = 20 celdas por hora
    h = {x["h"]: x for x in co.horas}
    assert [h[k]["linea_m_hora"] for k in (1, 2, 3, 4, 5)] == [0.0, 600.0, 600.0, 600.0, 600.0]
    assert co.linea.sum() == 80 and 0 < au.area_quemada_ha() <= libre.area_quemada_ha()
    # ninguna celda con línea conserva enlaces por encender
    filas, esta = co.ad._filas(np.flatnonzero(co.linea.ravel()))
    assert not au.act_pend[filas].any()
    # la línea es una sola tira contigua (ancla y flancos): una única componente de 8 vecinas
    from scipy import ndimage
    assert ndimage.label(co.linea, structure=np.ones((3, 3), int))[1] == 1


def test_reavivar_vuelve_a_propagar_desde_ese_momento():
    elegidas = {}

    def soltar(h, au, co, ad):
        if h == 4:                                       # el fuego está contenido desde la hora 2: se sueltan 5 celdas
            idx = np.flatnonzero(co.linea.ravel())[:5]
            elegidas["idx"] = idx
            elegidas["ha"] = au.area_quemada_ha()
            elegidas["llegada"] = au.t_llegada.ravel()[idx].copy()
            co._quitar(idx, 240.0)
            ad.reavivar(idx, 240.0)

    au, co, _ = _correr(6, {1: [{"bomberos": 400}], 2: [{"retirar": True}]}, al_paso=soltar)
    assert elegidas["ha"] < au.area_quemada_ha()                                  # volvió a crecer
    nuevas = np.isfinite(au.t_llegada) & (au.t_llegada > 120.0 + 1e-6)
    assert nuevas.any() and float(np.nanmin(au.t_llegada[nuevas])) >= 240.0       # nada se enciende "en el pasado"
    assert np.array_equal(au.t_llegada.ravel()[elegidas["idx"]], elegidas["llegada"])   # la llegada original no cambia
    # lo nuevo sale de las celdas soltadas: está pegado a ellas, no en otro lado de la línea
    f, c = np.divmod(elegidas["idx"], au.W)
    fn, cn = np.nonzero(nuevas)
    assert np.min(np.hypot(fn[:, None] - f[None, :], cn[:, None] - c[None, :]), axis=1).max() < 40


def test_determinista():
    a, ca, _ = _correr(5, {1: [{"bomberos": 30}], 3: [{"bomberos": 60, "prioridad": "cabeza", "llegada_min": 20}]})
    b, cbb, _ = _correr(5, {1: [{"bomberos": 30}], 3: [{"bomberos": 60, "prioridad": "cabeza", "llegada_min": 20}]})
    assert _distintas(a.t_llegada, b.t_llegada) == 0 and np.array_equal(ca.linea, cbb.linea) and ca.horas == cbb.horas


def test_con_la_contencion_propia_del_motor_el_despacho_se_rechaza():
    # el motor con su contención encendida ya tiene su propia línea: el combate de la app no se le suma
    con_error = []

    def despachar(h, au, co, ad):
        if h == 1:
            try:
                co.intervenir(iv.validar_entrada({"tipo": "dotacion", "datos": {"bomberos": 10}}), 60.0)
            except ValueError as e:
                con_error.append(str(e))

    au, co, _ = _correr(2, al_paso=despachar, parametros={"contencion": {"activo": True}})
    assert con_error and "contención propia del motor v4.0" in con_error[0]
    assert not co.habilitado and au.filtro_enlaces is None


# ================================================================================================ descargas aéreas (etapa 2)
RES = 30.0


def _punto(fila: float, col: float) -> list[float]:
    """Esquina noroeste de la celda (fila, col) de la grilla sintética (xmin = 0, ymax = N·RES), en EPSG:5345."""
    return [round(col * RES, 2), round((N - fila) * RES, 2)]


def _barrera(fila: int, col0: int, col1: int, medio: str = "avion", producto: str = "agua") -> list[tuple[str, dict]]:
    """Descargas seguidas hacia el este por el medio de la fila `fila`, de la columna `col0` a la `col1`."""
    paso = int(cb.MEDIOS[medio]["largo_m"] / RES)
    return [("descarga", {"medio": medio, "producto": producto, "xy_5345": [_punto(fila + 0.5, c), _punto(fila + 0.5, c + 1)]})
            for c in range(col0, col1, paso)]


def _con_acciones(horas: int, acciones: dict, vecindad: int = 8, t0: str = T0):
    """Como `_correr`, con intervenciones de cualquier tipo: `acciones` = {hora: [(tipo, datos), …]}."""
    respuestas = []

    def aplicar(h, au, co, ad):
        for tipo, datos in acciones.get(h, []):
            respuestas.append(co.intervenir(iv.validar_entrada({"tipo": tipo, "datos": datos}), h * 60.0))

    global T0
    previo, T0 = T0, t0
    try:
        au, co, _ = _correr(horas, vecindad=vecindad, al_paso=aplicar)
    finally:
        T0 = previo
    return au, co, respuestas


@pytest.fixture(scope="module")
def frente() -> dict:
    """La corrida libre de 8 h y la fila hasta donde llegó el fuego a las 2 h (avanza hacia el sur: el viento viene del NNE)."""
    libre, _, _ = _correr(8)
    filas = np.nonzero(np.isfinite(libre.t_llegada) & (libre.t_llegada <= 120.0))[0]
    return {"libre": libre, "borde": int(filas.max()), "delante": int(filas.max()) + 4}


def _detras(au, fila: int) -> float:
    """Primera llegada (min) a las tres filas de detrás de la franja, en sus 20 columnas del medio."""
    t = au.t_llegada[fila + 1: fila + 4, 45:66]
    return float(np.nanmin(t)) if np.isfinite(t).any() else float("inf")


def test_el_adaptador_ubica_las_descargas(frente):
    ad = _correr(1)[1].ad
    ff, cc = ad.rc([_punto(10.5, 20.25), _punto(0, 0), _punto(N, N)])
    assert np.allclose(ff, [10.5, 0.0, N]) and np.allclose(cc, [20.25, 0.0, N])
    assert ad.hora_utc(0.0) == 15 and ad.hora_utc(125.0) == 17 and ad.hora_utc(9 * 60.0) == 0      # T0 = 12:00 −03:00


def test_agua_delante_del_fuego_lo_demora_y_al_secarse_sigue(frente):
    F = frente["delante"]
    au, co, r = _con_acciones(8, {2: _barrera(F, 40, 70)})
    assert [x["estado"] for x in r] == ["aceptada"] * 6 and sum(x["datos"]["celdas_mojadas"] for x in r) == 30
    assert all(x["datos"]["celdas_frenadas"] == 0 and x["datos"]["vence_min"] == 180.0 for x in r)
    h = {x["h"]: x for x in co.horas}
    assert h[2]["celdas_agua"] == 30 and h[3]["vencidas_hora"] == 30 and h[3]["celdas_agua"] == 0 and not co.linea.any()
    libre = _detras(frente["libre"], F)
    assert libre < 170.0                                 # sin la franja el fuego pasa antes de que el agua se seque
    assert 180.0 - 1e-6 <= _detras(au, F) < 240.0        # con la franja pasa recién cuando se seca, y pasa: el agua da tiempo
    assert au.filtro_enlaces is not None


@pytest.mark.parametrize("vecindad", [8, 16])
def test_el_retardante_aguanta_y_el_fuego_lo_rodea(frente, vecindad):
    libre, _, _ = _correr(8, vecindad=vecindad)
    filas = np.nonzero(np.isfinite(libre.t_llegada) & (libre.t_llegada <= 120.0))[0]
    F = int(filas.max()) + 4
    au, co, r = _con_acciones(8, {2: _barrera(F, 40, 70, producto="retardante")}, vecindad=vecindad)
    assert all(x["estado"] == "aceptada" and x["datos"]["vence_min"] is None for x in r)
    assert co.linea.sum() == 30 and co.vencidas == 0 and (co.clase[co.linea] == cb.RETARDANTE).all()
    assert not np.isfinite(au.t_llegada[co.linea]).any()                 # ninguna celda de la franja ardió
    # justo detrás del medio de la franja el fuego llega mucho más tarde (rodeando), o no llega
    medio_libre = float(np.nanmin(libre.t_llegada[F + 1, 53:58]))
    medio = au.t_llegada[F + 1, 53:58]
    assert not np.isfinite(medio).any() or float(np.nanmin(medio)) > medio_libre + 60.0
    assert au.area_quemada_ha() < libre.area_quemada_ha()


def test_descarga_sobre_el_frente_frena_lo_que_arde(frente):
    B = frente["borde"]
    au, co, r = _con_acciones(3, {2: _barrera(B, 45, 70)})
    frenadas = sum(x["datos"]["celdas_frenadas"] for x in r)
    assert frenadas > 0 and frenadas == int(co.horas[0]["celdas_linea"] - sum(x["datos"]["celdas_mojadas"] for x in r))
    # y con bomberos en el lugar, el agua en contacto con el fuego queda asegurada antes de secarse
    au, co, r = _con_acciones(6, {1: [("dotacion", {"bomberos": 60})], 2: _barrera(frente["delante"], 40, 70)})
    h = {x["h"]: x for x in co.horas}
    assert h[3]["consolidadas_hora"] > 0 and h[3]["consolidadas_hora"] + h[3]["vencidas_hora"] == 30
    # las aseguradas conservan el minuto de la descarga (120) y pasan a ser línea de bomberos, que no vence
    F = frente["delante"]
    aseguradas = co.linea[F, 40:70] & (co.desde[F, 40:70] == 120.0)
    assert aseguradas.sum() == h[3]["consolidadas_hora"] and (co.clase[F, 40:70][aseguradas] == cb.LINEA_MANUAL).all()
    assert np.isinf(co.vence[F, 40:70][aseguradas]).all()


def test_descargas_de_noche_tope_y_determinismo(frente):
    F = frente["delante"]
    _, co, r = _con_acciones(3, {2: _barrera(F, 40, 45)}, t0="2024-01-01T20:00:00-03:00")          # 22 h + 2 = medianoche local
    assert r[0]["estado"] == "rechazada" and "de día" in r[0]["motivo"] and not co.habilitado
    _, co, r = _con_acciones(3, {2: _barrera(F, 0, 120)[:14]})
    assert [x["estado"] for x in r].count("aceptada") == 12 and r[-1]["estado"] == "rechazada" and "máximo" in r[-1]["motivo"]
    acciones = {1: [("dotacion", {"bomberos": 30})], 2: _barrera(F, 40, 70) + _barrera(frente["borde"], 50, 60, medio="helicoptero")}
    a, ca, _ = _con_acciones(6, acciones)
    b, cb2, _ = _con_acciones(6, acciones)
    assert _distintas(a.t_llegada, b.t_llegada) == 0 and np.array_equal(ca.capas(), cb2.capas(), equal_nan=True) and ca.horas == cb2.horas
