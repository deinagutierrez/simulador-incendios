"""Pruebas del combate común (app/motores/combate.py; decisión D-E3-36), sin ningún motor.

El método se prueba sobre un fuego de prueba mínimo (`Juguete`: cada hora avanza una celda hacia las 8 vecinas), que cumple
el mismo contrato de adaptador que los dos motores. Rápidas (menos de un segundo) y sin red. Las de cada motor están en
test_combate_v40.py y test_combate_v31.py; las del servidor, en test_servidor_combate.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app" / "motores"))

import combate as cb  # noqa: E402
import intervenciones as iv  # noqa: E402

VEC8 = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]


class Juguete:
    """Fuego de prueba y, a la vez, su adaptador: desde cada celda que arde y no está frenada, el fuego pasa en una hora a
    las 8 vecinas combustibles (sin atravesar la línea). La intensidad de cada celda es la de `I`, igual hacia todas."""

    def __init__(self, n: int = 41, intensidad: float = 500.0):
        self.forma = (n, n)
        self.res = 30.0
        self.df = np.array([a for a, _ in VEC8]); self.dc = np.array([b for _, b in VEC8])
        self.fuel = np.ones(self.forma, bool)
        self.llegada = np.full(self.forma, np.nan)
        self.activa = np.zeros(self.forma, bool)
        self.I = np.full(self.forma, float(intensidad))
        self.t = 0.0
        self.combate = None
        self.habilitaciones = 0
        self.reavivadas: list[int] = []
        self.bloqueadas: list[int] = []
        self.desbloqueadas: list[int] = []
        self.hora0 = 12                                  # hora UTC del inicio (para las descargas, que son de día)
        self.n_linea = None
        self.llegada[n // 2, n // 2] = 0.0
        self.activa[n // 2, n // 2] = True

    # ---- adaptador
    def habilitar(self): self.habilitaciones += 1
    def sincronizar(self, n): self.n_linea = n
    def afectada(self): return np.isfinite(self.llegada)
    def combustible(self): return self.fuel & ~self.afectada()

    def activas(self):
        libre = self.combustible()
        f, c = np.nonzero(self.activa)
        con = np.zeros(len(f), bool)
        for a, b in VEC8:
            ff, cc = f + a, c + b
            ok = (ff >= 0) & (ff < self.forma[0]) & (cc >= 0) & (cc < self.forma[1])
            con[ok] |= libre[ff[ok], cc[ok]]
        return f[con] * self.forma[1] + c[con]

    def intensidad(self, idx):
        f, c = np.divmod(np.asarray(idx, np.int64), self.forma[1])
        return np.repeat(self.I[f, c][:, None], 8, axis=1)

    def frenar(self, idx, t): self.activa.ravel()[np.asarray(idx, np.int64)] = False
    def bloquear(self, idx, t): self.bloqueadas += [int(i) for i in idx]          # `paso` ya respeta la línea
    def desbloquear(self, idx, t): self.desbloqueadas += [int(i) for i in idx]
    def hora_utc(self, t): return int((self.hora0 + t // 60) % 24)

    def rc(self, xy):
        xy = np.asarray(xy, float)
        return (self.forma[0] * self.res - xy[:, 1]) / self.res, xy[:, 0] / self.res

    def reavivar(self, idx, t):
        self.activa.ravel()[np.asarray(idx, np.int64)] = True
        self.reavivadas += [int(i) for i in idx]

    # ---- el fuego
    def paso(self):
        libre = self.combustible()
        linea = self.combate.linea if self.combate is not None else np.zeros(self.forma, bool)
        nuevas = np.zeros(self.forma, bool)
        f, c = np.nonzero(self.activa)
        for a, b in VEC8:
            ff, cc = f + a, c + b
            ok = (ff >= 0) & (ff < self.forma[0]) & (cc >= 0) & (cc < self.forma[1])
            ok[ok] &= libre[ff[ok], cc[ok]] & ~linea[ff[ok], cc[ok]] & ~cb.cortado(linea, f[ok], c[ok], a, b)
            nuevas[ff[ok], cc[ok]] = True
        self.t += 60.0
        self.llegada[nuevas] = self.t
        self.activa[nuevas] = True
        # una celda sin vecinas por encender se apaga (como en los motores): solo vuelve a arder si la reavivan
        libre = self.combustible() & ~linea
        f, c = np.nonzero(self.activa)
        con = np.zeros(len(f), bool)
        for a, b in VEC8:
            ff, cc = f + a, c + b
            ok = (ff >= 0) & (ff < self.forma[0]) & (cc >= 0) & (cc < self.forma[1])
            con[ok] |= libre[ff[ok], cc[ok]]
        self.activa[f[~con], c[~con]] = False

    def celdas(self) -> int:
        return int(np.isfinite(self.llegada).sum())


def _entrada(**datos) -> dict:
    return iv.validar_entrada({"tipo": "dotacion", "datos": datos})


def _correr(horas: int, despachos: dict | None = None, **kw):
    """Corre `horas` con el orden de los conductores: intervenciones de la hora, paso de combate, avance del fuego."""
    j = Juguete(**kw)
    co = j.combate = cb.Combate(j)
    respuestas = []
    for h in range(horas):
        for d in (despachos or {}).get(h, []):
            respuestas.append(co.intervenir(_entrada(**d), h * 60.0))
        co.paso_hora(h * 60.0)
        j.paso()
    return j, co, respuestas


# ------------------------------------------------------------------------------------------------ validación
def test_validar_dotacion_normaliza():
    e = iv.validar_entrada({"tipo": "dotacion", "datos": {"bomberos": 12.0, "tasa_m_h": 240, "dotacion": 3, "desde_min": 5}})
    assert e == {"tipo": "dotacion", "datos": {"bomberos": 12, "llegada_min": 0, "prioridad": "flancos"}}
    assert isinstance(e["datos"]["bomberos"], int)
    assert iv.validar_entrada(e) == e                                   # idempotente: así se reproduce desde la bitácora
    assert iv.validar_entrada({"tipo": "dotacion", "datos": {"retirar": True, "bomberos_retirados": 9}})["datos"] == {"retirar": True}
    assert "dotacion" in iv.TIPOS and "descarga" in iv.TIPOS and iv.TIPOS_COMBATE == cb.Combate.TIPOS
    iv.canon(e)


@pytest.mark.parametrize("datos, texto", [
    ({}, "`bomberos` tiene que ser un número"),
    ({"bomberos": 0}, "entre 1 y 500"),
    ({"bomberos": 501}, "entre 1 y 500"),
    ({"bomberos": 2.5}, "entero"),
    ({"bomberos": True}, "tiene que ser un número"),
    ({"bomberos": 10, "llegada_min": -1}, "entre 0 y 1440"),
    ({"bomberos": 10, "llegada_min": 1441}, "entre 0 y 1440"),
    ({"bomberos": 10, "prioridad": "cola"}, "prioridad"),
    ({"retirar": True, "bomberos": 3}, "con `retirar` no van"),
    ({"retirar": "si"}, "verdadero"),
    ([1, 2], "tiene que ser un objeto"),
])
def test_validar_dotacion_rechaza(datos, texto):
    with pytest.raises(ValueError, match=texto):
        iv.validar_entrada({"tipo": "dotacion", "datos": datos})


def test_validar_dotaciones_iniciales():
    assert iv.validar_dotaciones([{"bomberos": 5}, {"bomberos": 8, "llegada_min": 45, "prioridad": "cabeza"}]) == [
        {"bomberos": 5, "llegada_min": 0, "prioridad": "flancos"}, {"bomberos": 8, "llegada_min": 45, "prioridad": "cabeza"}]
    with pytest.raises(ValueError, match="dotación 2: antes de iniciar no hay nada que retirar"):
        iv.validar_dotaciones([{"bomberos": 5}, {"retirar": True}])
    with pytest.raises(ValueError, match="el máximo antes de iniciar"):
        iv.validar_dotaciones([{"bomberos": 1}] * (iv.MAX_DOTACIONES_INICIALES + 1))
    with pytest.raises(ValueError, match="lista"):
        iv.validar_dotaciones({"bomberos": 1})
    # entran en la raíz de la cadena ya normalizadas: el mismo pedido escrito de dos formas da la misma raíz
    a = iv.raiz({"motor": "v4.0", "configuracion": {"dotaciones": [{"bomberos": 5.0}]}})
    b = iv.raiz({"motor": "v4.0", "configuracion": {"dotaciones": [{"bomberos": 5, "llegada_min": 0, "prioridad": "flancos"}]}})
    assert a == b != iv.raiz({"motor": "v4.0", "configuracion": {}})


# ------------------------------------------------------------------------------------------------ piezas del método
def test_u01_es_determinista_y_uniforme():
    f, c = np.divmod(np.arange(20000), 200)
    u = cb.u01(cb.SEMILLA, f, c, 99, 7)
    assert u.min() >= 0.0 and u.max() < 1.0 and abs(u.mean() - 0.5) < 0.02
    assert np.array_equal(u, cb.u01(cb.SEMILLA, f, c, 99, 7))
    assert not np.array_equal(u, cb.u01(cb.SEMILLA, f, c, 99, 8)) and not np.array_equal(u, cb.u01(cb.SEMILLA + 1, f, c, 99, 7))
    # no depende del orden en que se piden las celdas
    orden = np.random.default_rng(1).permutation(len(f))
    assert np.array_equal(cb.u01(cb.SEMILLA, f[orden], c[orden], 99, 7), u[orden])


def test_cortado_diagonales_y_saltos_de_caballo():
    linea = np.zeros((7, 7), bool)
    linea[3, 4] = True                                   # una celda de línea al este de (3, 3)
    f, c = np.array([3]), np.array([3])
    assert not cb.cortado(linea, f, c, 0, 1)[0]          # ortogonal: nunca (cuenta la propia vecina)
    assert cb.cortado(linea, f, c, -1, 1)[0] and cb.cortado(linea, f, c, 1, 1)[0]        # diagonales que rozan la celda
    assert not cb.cortado(linea, f, c, -1, -1)[0] and not cb.cortado(linea, f, c, 1, -1)[0]
    assert cb.cortado(linea, f, c, -1, 2)[0] and cb.cortado(linea, f, c, 1, 2)[0]        # saltos de caballo que la cruzan
    assert not cb.cortado(linea, f, c, -2, 1)[0] and not cb.cortado(linea, f, c, 2, -1)[0]
    # en el borde de la grilla no se sale del arreglo
    assert cb.cortado(linea, np.array([0, 6]), np.array([0, 6]), -2, 1).tolist() == [False, False]


def test_exterior_deja_afuera_las_islas():
    afectada = np.zeros((15, 15), bool)
    afectada[4:11, 4:11] = True
    afectada[6:9, 6:9] = False                           # una isla sin quemar adentro del incendio
    ext, r0, c0 = cb.exterior(afectada, ~afectada)
    completa = np.zeros((15, 15), bool)
    completa[r0:r0 + ext.shape[0], c0:c0 + ext.shape[1]] = ext
    assert not completa[6:9, 6:9].any() and completa[3, 3] and completa[11, 7]
    assert cb.exterior(np.zeros((5, 5), bool), np.ones((5, 5), bool))[0].shape == (1, 1)


def test_elegir_linea_ancla_y_flancos():
    # ocho candidatas en fila (columnas 0 a 7 de la fila 5), con intensidad creciente hacia el este
    f = np.full(8, 5); c = np.arange(8); I = np.arange(8) * 100.0
    sin_linea = np.zeros((10, 10), bool)
    assert cb.elegir_linea(f, c, I, 3, sin_linea, "flancos").tolist() == [0, 1, 2]       # ancla en la menor y sigue contigua
    assert cb.elegir_linea(f, c, I, 3, sin_linea, "cabeza").tolist() == [0, 1, 2]        # igual: solo hay una contigua
    linea = sin_linea.copy(); linea[4, 4] = True                                        # ya hay línea junto a las columnas 3, 4 y 5
    assert cb.elegir_linea(f, c, I, 3, linea, "flancos").tolist() == [3, 2, 1]           # de las contiguas, la de menor intensidad
    assert cb.elegir_linea(f, c, I, 3, linea, "cabeza").tolist() == [5, 6, 7]            # de las contiguas, la de mayor
    assert cb.elegir_linea(f, c, I, 20, linea, "flancos").size == 8 and cb.elegir_linea(f, c, I, 0, linea).size == 0
    # sin contiguas: ancla nueva en la de menor intensidad, esté donde esté
    lejos = sin_linea.copy(); lejos[9, 9] = True
    assert cb.elegir_linea(np.array([0, 0]), np.array([0, 5]), np.array([300.0, 50.0]), 1, lejos, "cabeza").tolist() == [1]


# ------------------------------------------------------------------------------------------------ el método completo
def test_sin_combate_no_toca_nada():
    j, co, _ = _correr(6)
    assert j.habilitaciones == 0 and co.informe() is None and co.paso_hora(360.0) is None and not co.linea.any()
    assert j.celdas() == 13 * 13                         # el cuadrado crece una celda por hora hacia cada lado


def test_la_linea_de_cada_hora_se_coloca_al_cumplirse():
    # 30 bomberos = 600 m/h = 20 celdas por hora. Despachados en la hora 1: la primera línea aparece en la hora 2.
    j, co, r = _correr(6, {1: [{"bomberos": 30}]})
    assert r[0]["estado"] == "aceptada" and r[0]["t_vigor_min"] == 60.0
    assert r[0]["datos"] == {"dotacion": 1, "tasa_m_h": 600.0, "desde_min": 60.0}
    assert j.habilitaciones == 1
    h = {x["h"]: x for x in co.horas}
    assert h[1]["linea_m_hora"] == 0 and h[1]["bomberos"] == 0
    # en la hora 2 el borde son las 16 celdas del anillo de 5 × 5: alcanza para todas y el fuego queda contenido
    assert h[2]["frente_celdas"] == 16 and h[2]["frente_sostenible"] == 16 and h[2]["celdas_nuevas"] == 16
    assert h[2]["linea_m_hora"] == 480.0 and h[2]["bomberos"] == 30 and h[2]["tasa_m_h"] == 600.0
    assert j.celdas() == 25 and h[5]["frente_celdas"] == 0 and h[5]["celdas_linea"] == 16 and h[5]["linea_en_pie_m"] == 480.0
    assert h[5]["banco_m"] == 600.0                      # sin dónde trabajar, guarda a lo sumo una hora de producción
    assert j.n_linea == 16
    capas = co.capas()
    assert capas.shape == (3, 41, 41) and capas.dtype == np.float32
    en_linea = capas[2] == cb.LINEA_MANUAL
    assert en_linea.sum() == 16 and (capas[0][en_linea] == 120.0).all() and np.isnan(capas[1][en_linea]).all()
    inf = co.informe()
    assert inf["linea_m"] == 480.0 and inf["celdas_linea_final"] == 16 and inf["escapes"] == 0 and len(inf["celdas_linea_sha256"]) == 64
    assert inf["parametros"]["m_h_por_bombero"] == cb.M_H_POR_BOMBERO and inf["dotaciones"][0]["linea_m"] == 480.0
    iv.canon(inf)                                        # entra en corrida.json sin NaN


def test_llegada_a_mitad_de_hora_prorratea():
    # llegan 30 minutos después del despacho de la hora 1: en la hora 2 solo trabajaron media hora (300 m = 10 celdas)
    j, co, r = _correr(3, {1: [{"bomberos": 30, "llegada_min": 30}]})
    assert r[0]["t_vigor_min"] == 90.0 and r[0]["datos"]["desde_min"] == 90.0
    h2 = {x["h"]: x for x in co.horas}[2]                # el resumen horario empieza en la hora del primer despacho
    assert h2["linea_m_hora"] == 300.0 and h2["celdas_nuevas"] == 10 and h2["frente_celdas"] == 16


def test_pocas_dotaciones_no_contienen_y_el_retiro_corta_la_produccion():
    libre, _, _ = _correr(8)
    j, co, r = _correr(8, {1: [{"bomberos": 6}], 5: [{"retirar": True}]})        # 120 m/h = 4 celdas por hora
    assert [x["estado"] for x in r] == ["aceptada", "aceptada"] and r[1]["datos"] == {"dotaciones_retiradas": 1, "bomberos_retirados": 6}
    por_hora = {x["h"]: x["celdas_nuevas"] for x in co.horas}
    assert por_hora == {1: 0, 2: 4, 3: 4, 4: 4, 5: 4, 6: 0, 7: 0}    # la hora 4 → 5 todavía la trabajaron; después, nada
    assert 25 < j.celdas() < libre.celdas()
    assert co.horas[-1]["bomberos"] == 0 and co.horas[-1]["banco_m"] == 0
    # las celdas con línea no vuelven a propagar: la línea es contigua (ancla y flancos) y sigue en pie
    assert co.linea.sum() == 16 and not j.activa[co.linea].any()
    assert co.intervenir(_entrada(retirar=True), 480.0)["estado"] == "rechazada"   # ya no queda nadie


def test_dos_dotaciones_con_distinta_prioridad():
    j = Juguete()
    j.I = np.tile(np.arange(41) * 30.0, (41, 1))         # más intenso hacia el este: la cabeza está del lado este
    co = j.combate = cb.Combate(j)
    for h in range(4):
        if h == 2:
            co.intervenir(_entrada(bomberos=3, prioridad="flancos"), 120.0)      # 60 m/h = 2 celdas
            co.intervenir(_entrada(bomberos=3, prioridad="cabeza"), 120.0)
        co.paso_hora(h * 60.0)
        j.paso()
    f, c = np.nonzero(co.linea)
    assert len(f) == 4
    # la de flancos ancla en la celda de menor intensidad (columna más al oeste) y sigue por la contigua de menor
    # intensidad; la de cabeza se apoya en esa línea y toma las contiguas de mayor intensidad
    assert c.min() == 20 - 3 and sorted(c.tolist())[:2] == [17, 17]
    assert co.dotaciones[0]["linea_m"] == 60.0 and co.dotaciones[1]["linea_m"] == 60.0


def test_frente_demasiado_intenso_no_recibe_linea():
    j, co, _ = _correr(5, {1: [{"bomberos": 100}]}, intensidad=cb.I_SOSTENER_KW_M)        # justo en el umbral: no se sostiene
    assert not co.linea.any() and j.celdas() == 11 * 11
    h = co.horas[-1]
    assert h["frente_celdas"] == 32 and h["frente_sostenible"] == 0 and h["banco_m"] == 2000.0   # una hora de producción
    j, co, _ = _correr(5, {1: [{"bomberos": 100}]}, intensidad=cb.I_SOSTENER_KW_M - 1)
    assert co.linea.sum() == 16 and j.celdas() == 25


def test_escapes_deterministas_por_celda_y_hora():
    def corrida():
        j = Juguete()
        co = j.combate = cb.Combate(j)
        co.intervenir(_entrada(bomberos=100), 0.0)
        for h in range(3):                               # hora 1: las 8 celdas del anillo de 3 × 3 quedan con línea
            co.paso_hora(h * 60.0)
            j.paso()
        co.intervenir(_entrada(retirar=True), 180.0)
        j.I[:] = cb.I_ESCAPE_KW_M + 1                    # el tiempo empeora: ahora la línea puede escapar
        antes = co.linea.copy()
        r = co.paso_hora(180.0)
        return j, co, antes, r

    j, co, antes, r = corrida()
    f, c = np.nonzero(antes)
    esperadas = cb.u01(cb.SEMILLA, f, c, 99, 3) < cb.P_ESCAPE_HORA
    assert antes.sum() == 8 and 0 < esperadas.sum() < 8
    assert r["escapes_hora"] == int(esperadas.sum()) and r["escapes"] == r["escapes_hora"]
    assert sorted(j.reavivadas) == sorted((f[esperadas] * 41 + c[esperadas]).tolist())
    assert co.linea.sum() == 8 - esperadas.sum() and (co.hasta[f[esperadas], c[esperadas]] == 180.0).all()
    assert j.activa[f[esperadas], c[esperadas]].all() and j.n_linea == co.linea.sum()
    j2, co2, _, r2 = corrida()
    assert r2 == r and np.array_equal(co2.linea, co.linea)
    # por debajo del umbral de escape la línea no se mueve
    j.I[:] = cb.I_ESCAPE_KW_M
    assert co.paso_hora(240.0)["escapes_hora"] == 0
    # y lo que escapó vuelve a avanzar
    n = j.celdas()
    j.paso()
    assert j.celdas() > n


def test_limite_de_dotaciones_y_tipo_ajeno():
    j = Juguete()
    co = j.combate = cb.Combate(j)
    for _ in range(cb.MAX_DOTACIONES):
        assert co.intervenir(_entrada(bomberos=1), 0.0)["estado"] == "aceptada"
    r = co.intervenir(_entrada(bomberos=1), 0.0)
    assert r["estado"] == "rechazada" and "retiralas" in r["motivo"] and j.habilitaciones == 1
    assert co.intervenir({"tipo": "cortafuego", "datos": {}}, 0.0)["estado"] == "rechazada"
    # retirar sin nadie despachado se rechaza y no prepara el motor
    j2 = Juguete()
    co2 = j2.combate = cb.Combate(j2)
    assert co2.intervenir(_entrada(retirar=True), 0.0)["estado"] == "rechazada" and j2.habilitaciones == 0 and not co2.habilitado


# ================================================================================================ descargas aéreas (etapa 2)
# En el fuego de prueba la celda (fila, col) va de x = col·30 a (col + 1)·30 y de y = (41 − fila − 1)·30 a (41 − fila)·30.
def _punto(fila: float, col: float) -> list[float]:
    return [round(col * 30.0, 2), round((41 - fila) * 30.0, 2)]


def _descarga(fila: float, col: float, hacia: str = "este", medio: str = "avion", producto: str = "agua") -> dict:
    """Una descarga que empieza en (fila, col) y va hacia el este o el sur."""
    df, dc = {"este": (0.0, 1.0), "sur": (1.0, 0.0)}[hacia]
    return iv.validar_entrada({"tipo": "descarga", "datos": {"medio": medio, "producto": producto,
                                                              "xy_5345": [_punto(fila, col), _punto(fila + df, col + dc)]}})


def _pared(co, fila: int, t: float, producto: str = "agua") -> list[dict]:
    """Franja de lado a lado de la grilla sobre la fila `fila`: 9 descargas de avión (150 m = 5 celdas cada una)."""
    return [co.intervenir(_descarga(fila + 0.5, c, producto=producto), t) for c in range(0, 41, 5)]


def test_validar_descarga():
    e = iv.validar_entrada({"tipo": "descarga", "datos": {"medio": "avion", "xy_5345": [[100.004, 200], [130, 200.0]],
                                                          "celdas_mojadas": 5, "vence_min": 240, "xy_fin_5345": [250, 200]}})
    assert e == {"tipo": "descarga", "datos": {"medio": "avion", "producto": "agua", "xy_5345": [[100.0, 200.0], [130.0, 200.0]]}}
    assert iv.validar_entrada(e) == e and iv.TIPOS_COMBATE == ("dotacion", "descarga") == cb.Combate.TIPOS
    assert set(iv.MEDIOS_AEREOS) == set(cb.MEDIOS) and set(iv.PRODUCTOS) == set(cb.PRODUCTOS)
    iv.canon(e)
    for datos, texto in (({"medio": "dron", "xy_5345": [[0, 0], [9, 9]]}, "`medio` tiene que ser"),
                         ({"medio": "avion", "producto": "espuma", "xy_5345": [[0, 0], [9, 9]]}, "`producto` tiene que ser"),
                         ({"medio": "avion", "xy_5345": [[0, 0]]}, "dos puntos"),
                         ({"medio": "avion", "xy_5345": [[0, 0], [1, 1], [2, 2]]}, "dos puntos"),
                         ({"medio": "avion", "xy_5345": [[0, 0], [0.4, 0.3]]}, "mismo lugar"),
                         ({"medio": "avion", "xy_5345": [[0, 0], [float("nan"), 1]]}, "finito"),
                         ({"medio": "helicoptero", "xy_5345": [[0, 0], "ab"]}, "no es un par")):
        with pytest.raises(ValueError, match=texto):
            iv.validar_entrada({"tipo": "descarga", "datos": datos})


def test_celdas_de_tramo():
    forma = (10, 12)
    # horizontal por el medio de la fila 5: las celdas en orden, sin repetir
    assert cb.celdas_de_tramo(5.5, 2.0, 5.5, 7.0, 0.5, forma).tolist() == [5 * 12 + c for c in range(2, 7)]
    # al revés, el orden es el del recorrido
    assert cb.celdas_de_tramo(5.5, 7.0, 5.5, 2.0, 0.5, forma).tolist() == [5 * 12 + c for c in range(6, 1, -1)]
    # en diagonal: cada celda toca a la siguiente (la franja no deja huecos)
    idx = cb.celdas_de_tramo(1.2, 1.3, 8.7, 9.9, 0.5, forma)
    f, c = np.divmod(idx, 12)
    assert len(np.unique(idx)) == len(idx) and (np.abs(np.diff(f)) <= 1).all() and (np.abs(np.diff(c)) <= 1).all()
    assert (f[0], c[0]) == (1, 1) and (f[-1], c[-1]) == (8, 9)
    # lo que cae fuera de la grilla se descarta; todo afuera: nada
    assert cb.celdas_de_tramo(5.5, 9.0, 5.5, 20.0, 0.5, forma).tolist() == [5 * 12 + 9, 5 * 12 + 10, 5 * 12 + 11]
    assert cb.celdas_de_tramo(-5.0, -5.0, -1.0, -1.0, 0.5, forma).size == 0
    # una franja de 3 celdas de ancho suma las de los costados cuyo centro queda a menos de 1,5 celdas
    ancha = set(cb.celdas_de_tramo(5.5, 2.0, 5.5, 7.0, 3.0, forma).tolist())
    assert {4 * 12 + 4, 5 * 12 + 4, 6 * 12 + 4} <= ancha and 3 * 12 + 4 not in ancha and 7 * 12 + 4 not in ancha


def test_agua_delante_del_fuego_lo_demora_y_al_secarse_sigue():
    def corrida(intensidad_al_vencer=None):
        j = Juguete()
        co = j.combate = cb.Combate(j)
        respuestas = []
        for h in range(11):
            if h == 4:                                   # el fuego ocupa las filas 16 a 24: la franja va en la 25, pegada
                respuestas = _pared(co, 25, 240.0)
            if h == 5 and intensidad_al_vencer is not None:
                j.I[:] = intensidad_al_vencer
            co.paso_hora(h * 60.0)
            j.paso()
        return j, co, respuestas

    libre, _, _ = _correr(11)
    j, co, r = corrida()
    assert all(x["estado"] == "aceptada" for x in r) and j.habilitaciones == 1
    d = r[0]["datos"]
    assert d["largo_m"] == 150.0 and d["ancho_m"] == 20.0 and d["celdas_mojadas"] == 5 and d["celdas_frenadas"] == 0
    assert d["vence_min"] == 300.0 and d["xy_fin_5345"] == _punto(25.5, 5) and len(d["celdas_sha256"]) == 64
    assert r[0]["t_vigor_min"] == 240.0 and "dura hasta la hora 5" in r[0]["motivo"]
    assert sum(x["datos"]["celdas_mojadas"] for x in r) == 41 and len(j.bloqueadas) == 41
    h = {x["h"]: x for x in co.horas}
    assert h[4]["celdas_agua"] == 41 and h[4]["descargas"] == 9 and h[5]["vencidas_hora"] == 41 and h[5]["celdas_agua"] == 0
    assert len(j.desbloqueadas) == 41 and not co.linea.any()
    # sin la franja el fuego entra a la fila 25 en la hora 5; con ella, recién en la 6 (el agua da una hora)
    assert libre.llegada[25, 20] == 300.0 and j.llegada[25, 20] == 360.0
    # y sigue porque las celdas ya quemadas pegadas a la franja vuelven a propagar al secarse
    f, c = np.divmod(np.array(j.reavivadas), 41)
    assert (f == 24).all() and 20 in c.tolist()
    capas = co.capas()
    assert (capas[2][25] == cb.AGUA).all() and (capas[0][25] == 240.0).all() and (capas[1][25] == 300.0).all()
    # si al secarse el fuego no puede avanzar (intensidad cero), esas celdas quedan apagadas: solo entra por los costados
    j0, co0, _ = corrida(intensidad_al_vencer=0.0)
    assert j0.reavivadas == [] and j0.llegada[25, 20] > 360.0


def test_retardante_no_vence_y_cede_por_brechas():
    j = Juguete()
    co = j.combate = cb.Combate(j)
    for h in range(12):
        if h == 4:
            r = _pared(co, 25, 240.0, "retardante")
            assert all(x["estado"] == "aceptada" and x["datos"]["vence_min"] is None and "no vence" in x["motivo"] for x in r)
        co.paso_hora(h * 60.0)
        j.paso()
    # la pared de lado a lado aguanta: nada arde de la fila 25 para abajo, y no venció ni cedió nada
    assert not np.isfinite(j.llegada[25:]).any() and co.vencidas == 0 and co.brechas == 0 and co.linea.sum() == 41
    assert (co.capas()[2][25] == cb.RETARDANTE).all() and j.n_linea == 41
    # con el fuego llegando muy intenso, cada celda de la pared con fuego al lado cede con probabilidad 0,5 por hora
    j.I[:] = cb.I_ESCAPE_KW_M + 1
    con_fuego = np.flatnonzero(np.isfinite(j.llegada[24]))            # columnas de la fila 24 que ardieron
    cerca = np.arange(max(0, con_fuego.min() - 1), min(40, con_fuego.max() + 1) + 1)
    esperadas = cerca[cb.u01(cb.SEMILLA, np.full(len(cerca), 25), cerca, 98, 12) < cb.P_ESCAPE_HORA]
    paso = co.paso_hora(720.0)
    assert 0 < len(esperadas) < len(cerca) and paso["brechas_hora"] == len(esperadas) and co.brechas == len(esperadas)
    assert sorted(np.flatnonzero(~co.linea[25]).tolist()) == sorted(esperadas.tolist())
    j.paso()
    assert np.isfinite(j.llegada[25, esperadas]).all()                # por la brecha, el fuego pasa


def test_descarga_sobre_el_frente_frena_lo_que_arde():
    j = Juguete()
    co = j.combate = cb.Combate(j)
    for h in range(3):
        co.paso_hora(h * 60.0)
        j.paso()
    # hora 3: el fuego ocupa de la fila 17 a la 23 y de la columna 17 a la 23; la descarga va sobre su borde sur
    r = [co.intervenir(_descarga(23.5, c), 180.0) for c in (15, 20)]              # columnas 15 a 24
    assert [x["estado"] for x in r] == ["aceptada", "aceptada"]
    assert sum(x["datos"]["celdas_frenadas"] for x in r) == 7 and sum(x["datos"]["celdas_mojadas"] for x in r) == 3
    assert co.frenada[23, 17:24].all() and not co.frenada[23, [15, 16, 24]].any() and co.linea[23, 15:25].all()
    assert not j.activa[23, 17:24].any() and sorted(j.bloqueadas) == [23 * 41 + c for c in (15, 16, 24)]
    j.paso()
    assert not np.isfinite(j.llegada[24, 16:25]).any()                 # por ahí no pasó (ni por las esquinas)
    assert np.isfinite(j.llegada[16, 20])                              # por el norte siguió
    # demasiado intenso: lo que arde no se frena. Una descarga solo sobre fuego intenso se rechaza
    j2 = Juguete(intensidad=cb.I_AEREO_KW_M)
    co2 = j2.combate = cb.Combate(j2)
    for h in range(3):
        co2.paso_hora(h * 60.0)
        j2.paso()
    r = co2.intervenir(_descarga(23.5, 15), 180.0)                     # columnas 15 a 19: 2 sin quemar y 3 del frente
    assert r["estado"] == "recortada" and r["datos"]["celdas_intensas"] == 3 and r["datos"]["celdas_frenadas"] == 0
    assert r["datos"]["celdas_mojadas"] == 2 and "demasiada intensidad" in r["motivo"] and "moja 2 celdas sin quemar" in r["motivo"]
    r = co2.intervenir(_descarga(23.5, 18, medio="helicoptero"), 180.0)           # 45 m: columnas 18 y 19, las dos con fuego
    assert r["estado"] == "rechazada" and "demasiado intenso" in r["motivo"] and len(co2.descargas) == 1


def test_los_bomberos_aseguran_el_agua_antes_de_que_se_seque():
    j = Juguete()
    co = j.combate = cb.Combate(j)
    co.intervenir(_entrada(bomberos=6, llegada_min=180), 0.0)          # 120 m/h = 4 celdas por hora, desde la hora 3
    for h in range(7):
        if h == 3:
            co.intervenir(_descarga(23.5, 17), 180.0)                  # columnas 17 a 21 del borde sur, que arden: frenadas
        co.paso_hora(h * 60.0)
        j.paso()
    h = {x["h"]: x for x in co.horas}
    assert h[3]["celdas_agua"] == 5 and h[3]["consolidadas_hora"] == 0  # todavía no trabajaron
    # hora 4: lo producido de la 3 a la 4 (4 celdas) asegura agua antes de que venza; la quinta celda se seca
    assert h[4]["consolidadas_hora"] == 4 and h[4]["vencidas_hora"] == 1 and h[4]["celdas_nuevas"] == 0
    assert h[4]["linea_m_hora"] == 120.0 and h[4]["celdas_agua"] == 0 and co.consolidadas == 4 and co.vencidas == 1
    aseguradas = co.clase[23, 17:22] == cb.LINEA_MANUAL
    assert aseguradas.sum() == 4 and np.isinf(co.vence[23, 17:22][aseguradas]).all()
    assert co.linea[23, 17:22][aseguradas].all()                       # siguen siendo línea hasta el final
    assert h[5]["celdas_nuevas"] == 4                                  # después siguen con línea nueva


def test_descargas_de_noche_tope_por_hora_y_fuera_de_la_grilla():
    j = Juguete()
    co = j.combate = cb.Combate(j)
    j.hora0 = 20                                                       # 20 UTC + 3 h = 23 UTC: de noche
    r = co.intervenir(_descarga(30.5, 10), 180.0)
    assert r["estado"] == "rechazada" and "de día" in r["motivo"] and not co.habilitado and j.habilitaciones == 0
    j.hora0 = 12
    r = co.intervenir(_descarga(60.5, 10), 180.0)                      # fuera de la grilla
    assert r["estado"] == "rechazada" and "fuera de la zona" in r["motivo"] and not co.habilitado
    # el tope es por medio y por hora
    tope = cb.MEDIOS["avion"]["max_por_hora"]
    estados = [co.intervenir(_descarga(30.5 + (k % 5), 2 + 5 * (k % 7)), 180.0)["estado"] for k in range(tope + 2)]
    assert estados[:tope].count("aceptada") == tope and estados[tope:] == ["rechazada", "rechazada"]
    assert co.intervenir(_descarga(36.5, 2, medio="helicoptero"), 180.0)["estado"] == "aceptada"   # otro medio: tiene su cupo
    assert co.intervenir(_descarga(37.5, 2), 240.0)["estado"] == "aceptada"                        # otra hora: cupo nuevo
    # sobre agua que sigue en pie: se moja otra vez (vence más tarde); con retardante encima, ya no vence
    antes = co.vence[30, 2]
    r = co.intervenir(_descarga(30.5, 2), 240.0)
    assert r["estado"] == "aceptada" and r["datos"]["celdas_renovadas"] == 5 and co.vence[30, 2] == antes + 60.0
    r = co.intervenir(_descarga(30.5, 2, producto="retardante"), 240.0)
    assert r["datos"]["celdas_renovadas"] == 5 and np.isinf(co.vence[30, 2:7]).all() and (co.clase[30, 2:7] == cb.RETARDANTE).all()
    # donde no hay fuego ni combustible sin quemar, la descarga se rechaza
    j.fuel[39] = False
    assert co.intervenir(_descarga(39.5, 2), 240.0)["estado"] == "rechazada"
    inf = co.informe()
    assert len(inf["descargas"]) == len(co.descargas) and inf["parametros"]["medios"]["avion"]["largo_m"] == 150.0
    iv.canon(inf)
