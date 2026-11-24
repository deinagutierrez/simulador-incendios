"""Ayudante de test_combate_v31.py: el combate común sobre el motor v3.1, que tiene que estar cargado en el mismo proceso.

Se corre como proceso aparte (cada proceso carga un solo `incendios_sl`) y escribe un JSON en la salida estándar:

    python test/app/ayudante_combate_v31.py

Todo sobre las entradas sintéticas del propio motor (`incendios_sl.simulation.sintetico`): grilla homogénea de 121 × 121
con viento, 8 horas. No usa red ni escribe en disco (salvo la caché de numba).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app" / "motores"))
sys.path.insert(0, str(REPO / "src" / "v3.1" / "src"))      # adelante: que no gane otro `incendios_sl` instalado en el sistema

import combate as cb  # noqa: E402
import intervenciones as iv  # noqa: E402

N = 121
HORAS = 8


def _distintas(a: np.ndarray, b: np.ndarray) -> int:
    return int((~((a == b) | (np.isinf(a) & np.isinf(b)))).sum())


def main() -> dict:
    import combate_v31
    from incendios_sl.simulation import automata as A
    from incendios_sl.simulation.motor import ConfigSimulacion, Simulacion
    from incendios_sl.simulation.sintetico import entradas_homogeneas, tabla_prueba
    tabla = tabla_prueba()
    out: dict = {}

    def correr(despachos=None, vecindad=16, al_paso=None, **cfg):
        """Con el orden del conductor (`motor_v31.SimulacionControlada`): las intervenciones de la hora en `_tablas_hora`
        (antes de la hora) y el paso de combate en `_contener_hora` (con las tablas y el viento de la hora nueva)."""
        ent = entradas_homogeneas(n=N, vel=6.0, dir_desde=20.0, horas=HORAS, tabla=tabla)
        respuestas = []

        class Sim(Simulacion):
            def _tablas_hora(self, *a, **k):
                h = int(round(self.t / 3600.0))
                if al_paso:
                    al_paso(h, self, co, ad)
                for d in (despachos or {}).get(h, []):
                    try:
                        respuestas.append(co.intervenir(iv.validar_entrada({"tipo": "dotacion", "datos": d}), self.t / 60.0))
                    except ValueError as e:
                        respuestas.append({"estado": "error", "motivo": str(e)})
                return super()._tablas_hora(*a, **k)

            def _contener_hora(self, hora_idx, fraccion=1.0):
                if not co.habilitado:
                    return super()._contener_hora(hora_idx, fraccion)
                co.paso_hora(self.t / 60.0)

        sim = Sim(ent, ConfigSimulacion(vecindad=vecindad, **cfg))
        ad = combate_v31.AdaptadorV31(sim)
        co = ad.combate = cb.Combate(ad)
        sim.ejecutar()
        return sim, co, respuestas

    celdas = lambda s: int(np.isfinite(s.t_arr).sum())  # noqa: E731

    # --- piezas comunes = las del motor
    f, c = np.divmod(np.arange(3000), 60)
    out["hash_igual"] = all(float(cb.u01(cb.SEMILLA, int(a), int(b), 99, 5)) == float(A.u01(cb.SEMILLA, int(a), int(b), 99, 5))
                            for a, b in zip(f[::37].tolist(), c[::37].tolist()))
    rng = np.random.default_rng(7)
    linea = rng.random((40, 40)) < 0.2
    estado = np.where(linea, A.CONTENIDA, A.COMB).astype(np.uint8)
    dy, dx, _, _ = A.estencil(16, 30.0)
    distintos = 0
    ff, cc = (a.ravel() for a in np.mgrid[2:38, 2:38])
    for k in range(16):
        comun = cb.cortado(linea, ff, cc, int(dy[k]), int(dx[k]))
        motor = np.array([A._cortado_por_contencion(estado, int(i), int(j), k, dy, dx) for i, j in zip(ff.tolist(), cc.tolist())])
        distintos += int((comun != motor).sum())
    out["corte_distinto"] = distintos

    # --- sin despachos: idéntico al motor solo
    solo = Simulacion(entradas_homogeneas(n=N, vel=6.0, dir_desde=20.0, horas=HORAS, tabla=tabla), ConfigSimulacion(vecindad=16))
    solo.ejecutar()
    sin, co, _ = correr()
    out["sin_despachos"] = {"llegada": _distintas(solo.t_arr, sin.t_arr), "estado": int((solo.estado != sin.estado).sum()),
                            "contencion_activo": bool(sin.c.contencion_activo), "habilitado": bool(co.habilitado),
                            "t_cont": list(sin.t_cont.shape), "celdas": celdas(solo), "motivo": int(sin.motivo)}

    # --- habilitado pero sin línea (una dotación que llega después del final): la propagación no cambia
    tarde, co, r = correr({1: [{"bomberos": 10, "llegada_min": 1000}]})
    out["habilitado_sin_linea"] = {"llegada": _distintas(solo.t_arr, tarde.t_arr), "estado": int((solo.estado != tarde.estado).sum()),
                                   "contencion_activo": bool(tarde.c.contencion_activo), "t_cont": list(tarde.t_cont.shape),
                                   "linea": int(co.linea.sum()), "respuesta": r[0]["estado"], "motivo": int(tarde.motivo)}

    # --- la línea frena el fuego, con las dos vecindades
    for vec in (8, 16):
        libre, _, _ = correr(vecindad=vec)
        sim, co, r = correr({1: [{"bomberos": 400}]}, vecindad=vec)
        h = {x["h"]: x for x in co.horas}
        out[f"frena_{vec}"] = {
            "respuesta": r[0]["estado"], "celdas": celdas(sim), "celdas_libre": celdas(libre),
            "ultima_llegada_s": float(np.max(sim.t_arr[np.isfinite(sim.t_arr)])),
            "frente_h2": h[2]["frente_celdas"], "nuevas_h2": h[2]["celdas_nuevas"],
            "nuevas_despues": [h[k]["celdas_nuevas"] for k in (3, 4, 5)], "linea": int(co.linea.sum()),
            "contenidas_motor": int((sim.estado == A.CONTENIDA).sum()), "n_cont": int(sim.n_cont), "motivo": int(sim.motivo),
            "linea_igual_a_contenidas": bool(np.array_equal(co.linea, sim.estado == A.CONTENIDA))}

    # --- pocas dotaciones: la misma producción por hora que en v4.0 (el método es el mismo)
    sim, co, _ = correr({1: [{"bomberos": 30}]})
    h = {x["h"]: x for x in co.horas}
    from scipy import ndimage
    out["pocas"] = {"linea_m_hora": [h[k]["linea_m_hora"] for k in (1, 2, 3, 4, 5)], "linea": int(co.linea.sum()),
                    "celdas": celdas(sim), "componentes": int(ndimage.label(co.linea, structure=np.ones((3, 3), int))[1]),
                    "activas_con_linea": int((sim.estado[co.linea] == A.ACTIVA).sum())}

    # --- reavivar: contenido desde la hora 2, a la hora 4 se sueltan 5 celdas
    nota = {}

    def soltar(h, sim, co, ad):
        if h == 4:
            idx = np.flatnonzero(co.linea.ravel())[:5]
            nota.update(idx=idx, celdas=celdas(sim), llegada=sim.t_arr.ravel()[idx].copy())
            co._quitar(idx, 240.0)
            ad.reavivar(idx, 240.0)
            ad.sincronizar(int(co.linea.sum()))

    sim, co, _ = correr({1: [{"bomberos": 400}], 2: [{"retirar": True}]}, al_paso=soltar)
    nuevas = np.isfinite(sim.t_arr) & (sim.t_arr > 7200.0 + 1e-3)
    fi, ci = np.divmod(nota["idx"], N)
    fn, cn = np.nonzero(nuevas)
    out["reavivar"] = {"celdas_antes": nota["celdas"], "celdas": celdas(sim),
                       "primera_llegada_nueva_s": float(sim.t_arr[nuevas].min()) if nuevas.any() else None,
                       "llegada_original_igual": bool(np.array_equal(sim.t_arr.ravel()[nota["idx"]], nota["llegada"])),
                       "lejos_max_celdas": float(np.min(np.hypot(fn[:, None] - fi[None, :], cn[:, None] - ci[None, :]), axis=1).max())
                       if nuevas.any() else None}

    # --- determinista
    a, ca, _ = correr({1: [{"bomberos": 30}], 3: [{"bomberos": 60, "prioridad": "cabeza", "llegada_min": 20}]})
    b, cbb, _ = correr({1: [{"bomberos": 30}], 3: [{"bomberos": 60, "prioridad": "cabeza", "llegada_min": 20}]})
    out["determinista"] = _distintas(a.t_arr, b.t_arr) == 0 and bool(np.array_equal(ca.linea, cbb.linea)) and ca.horas == cbb.horas

    # --- con la contención propia del motor encendida, el despacho se rechaza y corre la del motor
    sim, co, r = correr({1: [{"bomberos": 10}]}, contencion_activo=True, contencion_retardo_h=1.0, tasa_linea_m_h=6000.0)
    out["contencion_propia"] = {"respuesta": r[0]["estado"], "motivo": r[0]["motivo"], "habilitado": bool(co.habilitado),
                                "contenidas_motor": int((sim.estado == A.CONTENIDA).sum())}

    # ================================================================================================ descargas aéreas
    RES = 30.0
    punto = lambda fila, col: [round(col * RES, 2), round((N - fila) * RES, 2)]  # noqa: E731

    def barrera(fila, col0, col1, medio="avion", producto="agua"):
        paso = int(cb.MEDIOS[medio]["largo_m"] / RES)
        return [("descarga", {"medio": medio, "producto": producto, "xy_5345": [punto(fila + 0.5, c), punto(fila + 0.5, c + 1)]})
                for c in range(col0, col1, paso)]

    def con_acciones(acciones, vecindad=16, inicio="2024-01-01T15:00Z", horas=HORAS):
        """Como `correr`, con intervenciones de cualquier tipo y la corrida empezando a la hora `inicio` (para el día y la noche)."""
        import pandas as pd
        ent = entradas_homogeneas(n=N, vel=6.0, dir_desde=20.0, horas=horas, tabla=tabla)
        corrimiento = pd.Timestamp(inicio) - ent.t_inicio_utc
        ent.meteo["time_utc"] += corrimiento; ent.humedad["time_utc"] += corrimiento
        ent.t_inicio_utc += corrimiento; ent.t_fin_utc += corrimiento
        respuestas = []

        class Sim(Simulacion):
            def _tablas_hora(self, *a, **k):
                h = int(round(self.t / 3600.0))
                for tipo, datos in acciones.get(h, []):
                    respuestas.append(co.intervenir(iv.validar_entrada({"tipo": tipo, "datos": datos}), self.t / 60.0))
                return super()._tablas_hora(*a, **k)

            def _contener_hora(self, hora_idx, fraccion=1.0):
                if not co.habilitado:
                    return super()._contener_hora(hora_idx, fraccion)
                co.paso_hora(self.t / 60.0)

        sim = Sim(ent, ConfigSimulacion(vecindad=vecindad))
        ad = combate_v31.AdaptadorV31(sim)
        co = ad.combate = cb.Combate(ad)
        sim.ejecutar()
        return sim, co, respuestas

    def detras(sim, fila):
        t = sim.t_arr[fila + 1: fila + 4, 45:66]
        return float(t[np.isfinite(t)].min()) / 60.0 if np.isfinite(t).any() else None

    libre16, co, _ = con_acciones({})
    ad = co.ad
    ff, cc = ad.rc([punto(10.5, 20.25), punto(0, 0)])
    out["ubicacion"] = {"filas": [float(v) for v in ff], "cols": [float(v) for v in cc], "hora_0": ad.hora_utc(0.0), "hora_125": ad.hora_utc(125.0)}
    borde = int(np.nonzero(np.isfinite(libre16.t_arr) & (libre16.t_arr <= 7200.0))[0].max())
    F = borde + 4

    sim, co, r = con_acciones({2: barrera(F, 40, 70)})
    h = {x["h"]: x for x in co.horas}
    out["agua"] = {"estados": [x["estado"] for x in r], "mojadas": sum(x["datos"]["celdas_mojadas"] for x in r),
                   "vence": sorted({x["datos"]["vence_min"] for x in r}), "agua_h2": h[2]["celdas_agua"], "vencidas_h3": h[3]["vencidas_hora"],
                   "linea_final": int(co.linea.sum()), "contenidas_final": int((sim.estado == A.CONTENIDA).sum()),
                   "detras_min": detras(sim, F), "detras_libre_min": detras(libre16, F), "n_cont": int(sim.n_cont)}

    for vec in (8, 16):
        libre, _, _ = con_acciones({}, vecindad=vec)
        Fv = int(np.nonzero(np.isfinite(libre.t_arr) & (libre.t_arr <= 7200.0))[0].max()) + 4
        sim, co, r = con_acciones({2: barrera(Fv, 40, 70, producto="retardante")}, vecindad=vec)
        medio = sim.t_arr[Fv + 1, 53:58]; medio_libre = libre.t_arr[Fv + 1, 53:58]
        out[f"retardante_{vec}"] = {
            "estados": [x["estado"] for x in r], "vence": [x["datos"]["vence_min"] for x in r], "linea": int(co.linea.sum()),
            "vencidas": int(co.vencidas), "clase_ok": bool((co.clase[co.linea] == cb.RETARDANTE).all()),
            "franja_ardio": int(np.isfinite(sim.t_arr[co.linea]).sum()),
            "medio_min": float(medio[np.isfinite(medio)].min()) / 60.0 if np.isfinite(medio).any() else None,
            "medio_libre_min": float(medio_libre[np.isfinite(medio_libre)].min()) / 60.0,
            "celdas": celdas(sim), "celdas_libre": celdas(libre),
            "linea_igual_a_contenidas": bool(np.array_equal(co.linea, sim.estado == A.CONTENIDA))}

    punta = np.flatnonzero(np.isfinite(libre16.t_arr[borde]) & (libre16.t_arr[borde] <= 7200.0))     # columnas de la punta del fuego
    sim, co, r = con_acciones({2: barrera(borde, max(0, int(punta.min()) - 5), int(punta.max()) + 6)}, horas=3)
    out["sobre_el_frente"] = {"frenadas": sum(x["datos"]["celdas_frenadas"] for x in r), "mojadas": sum(x["datos"]["celdas_mojadas"] for x in r),
                              "linea_h2": co.horas[0]["celdas_linea"]}

    sim, co, r = con_acciones({1: [("dotacion", {"bomberos": 60})], 2: barrera(F, 40, 70)}, horas=6)
    h = {x["h"]: x for x in co.horas}
    # las aseguradas conservan el minuto de la descarga (120) y pasan a ser línea de bomberos; la línea nueva es posterior
    aseguradas = co.linea[F, 40:70] & (co.desde[F, 40:70] == 120.0)
    out["consolida"] = {"consolidadas_h3": h[3]["consolidadas_hora"], "vencidas_h3": h[3]["vencidas_hora"], "aseguradas": int(aseguradas.sum()),
                        "clase_ok": bool((co.clase[F, 40:70][aseguradas] == cb.LINEA_MANUAL).all()),
                        "no_vencen": bool(np.isinf(co.vence[F, 40:70][aseguradas]).all())}

    _, co, r = con_acciones({2: barrera(F, 40, 45)}, inicio="2024-01-01T23:00Z", horas=3)
    out["de_noche"] = {"estado": r[0]["estado"], "motivo": r[0]["motivo"], "habilitado": bool(co.habilitado)}
    _, co, r = con_acciones({2: barrera(F, 0, 120)[:14]}, horas=3)
    out["tope"] = {"aceptadas": [x["estado"] for x in r].count("aceptada"), "ultima": r[-1]["estado"]}
    acciones = {1: [("dotacion", {"bomberos": 30})], 2: barrera(F, 40, 70) + barrera(borde, 50, 60, medio="helicoptero")}
    a, ca, _ = con_acciones(acciones, horas=6)
    b, cbb, _ = con_acciones(acciones, horas=6)
    out["determinista_descargas"] = _distintas(a.t_arr, b.t_arr) == 0 and bool(np.array_equal(ca.capas(), cbb.capas(), equal_nan=True)) \
        and ca.horas == cbb.horas
    return out


if __name__ == "__main__":
    sys.stdout.write("\nRESULTADO " + json.dumps(main()) + "\n")
