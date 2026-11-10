"""Estados de la celda y diagrama de transiciones.

    NO_COMBUSTIBLE ──(nunca)──►
    COMBUSTIBLE ──[avance desde una vecina en combustión ≥ d_ij
                   y, si es camino, cruce de la barrera (parametros.barreras)]──► IGNICION
    IGNICION ──[retardo `ignicion_delay_min` (0 = el sub-paso siguiente)]──► COMBUSTION
    COMBUSTION ──[todas las vecinas combustibles ya encendidas y t ≥ t_ign + τ]──► QUEMADO
    COMBUSTION ──[humedad muerta ≥ Mx (ROS = 0) y t ≥ t_ign + τ]──► QUEMADO   (solo `extincion: definitiva`, V.4;
                  con `reversible` la celda queda latente en COMBUSTION y retoma cuando la humedad baja)
    QUEMADO ──(nunca)──►

Barreras: la celda con camino (ancho W < resolución) es combustible con carga × (1 − W/res); el cruce hacia
ella se decide por la longitud de llama (`umbral_tipo` de V.4, `umbral` L/W > λ o `probabilistico`). Con
W ≥ resolución la celda es NO_COMBUSTIBLE.

τ = 384/σ min es el tiempo de residencia de la llama (Anderson 1969). Una celda en COMBUSTION
propaga hacia cada vecina acumulando avance = Σ R(θ_ij)·Δt; la vecina se enciende cuando el
avance alcanza la distancia d_ij (30 m ortogonal, 42,43 m diagonal, 67,08 m en los saltos de
caballo de la vecindad de 16).
"""

from __future__ import annotations

import numpy as np

NO_COMBUSTIBLE = 0
COMBUSTIBLE = 1
IGNICION = 2
COMBUSTION = 3
QUEMADO = 4

NOMBRES = {NO_COMBUSTIBLE: "NO_COMBUSTIBLE", COMBUSTIBLE: "COMBUSTIBLE", IGNICION: "IGNICION",
           COMBUSTION: "COMBUSTION", QUEMADO: "QUEMADO"}


def vecindad(n: int, res: float):
    """Desplazamientos (dfila, dcol), distancias (m) y rumbos (grados desde el N, horario)."""
    if n == 8:
        d = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]
    elif n == 16:
        d = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1),
             (-2, 1), (-1, 2), (1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1)]
    else:
        raise ValueError("vecindad debe ser 8 o 16")
    df = np.array([a for a, _ in d]); dc = np.array([b for _, b in d])
    dist = np.hypot(df, dc) * res
    rumbo = (np.degrees(np.arctan2(dc, -df)) + 360.0) % 360.0   # dc → este, −df → norte
    return df, dc, dist.astype("float64"), rumbo
