"""Forma elíptica del fuego: relación largo/ancho de Anderson (1983) y ROS direccional.

LB(U) = 0.936·e^(0.2566·U) + 0.461·e^(−0.1548·U) − 0.397, con U el viento efectivo a media llama
en mi/h, acotada a LB ≤ 8 (FARSITE). Excentricidad e = √(LB² − 1) / LB.
R(θ) = R_max · (1 − e) / (1 − e·cos θ), θ medido desde el rumbo de la cabeza.
"""

from __future__ import annotations

import numpy as np

LB_MAX = 8.0


def relacion_largo_ancho(U_mih: np.ndarray) -> np.ndarray:
    U = np.maximum(np.asarray(U_mih, float), 0.0)
    lb = 0.936 * np.exp(0.2566 * U) + 0.461 * np.exp(-0.1548 * U) - 0.397
    return np.clip(lb, 1.0, LB_MAX)


def excentricidad(lb: np.ndarray) -> np.ndarray:
    lb = np.maximum(np.asarray(lb, float), 1.0)
    return np.sqrt(lb * lb - 1.0) / lb


def ros_direccional(R_max: np.ndarray, e: np.ndarray, theta_deg: np.ndarray) -> np.ndarray:
    """R(θ) para θ en grados (puede ser (N,1) y (1,K) → (N,K))."""
    return R_max * (1.0 - e) / (1.0 - e * np.cos(np.deg2rad(theta_deg)))
