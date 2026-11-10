"""Los 40 modelos de combustible estándar de Scott & Burgan (2005), RMRS-GTR-153.

Unidades de la tabla original (se conservan en el CSV y se convierten en `physics.rothermel`):
- cargas en t/ac (1 h, 10 h, 100 h, herbáceo vivo, leñoso vivo);
- SAV en 1/ft (1 h, herbáceo vivo, leñoso vivo; 10 h = 109, 100 h = 30 fijos);
- profundidad del lecho en ft;
- humedad de extinción del combustible muerto (Mx) en %;
- calor de combustión en BTU/lb (muerto y vivo).
`dinamico` = 1 cuando el modelo transfiere carga herbácea viva → muerta según el curado.

Transcripción de la tabla publicada (Scott & Burgan 2005, tabla 7 y fichas por modelo). Los NB
(91–99) son no combustibles. Columnas: código, clave, descripción, w1h, w10h, w100h, wherb, wwoody,
sav1h, savherb, savwoody, profundidad_ft, mx_muerto_pct, calor_muerto, calor_vivo, dinamico.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

COLUMNAS = ["codigo", "clave", "descripcion", "w1h", "w10h", "w100h", "wherb", "wwoody",
            "sav1h", "savherb", "savwoody", "profundidad_ft", "mx_muerto_pct", "calor_muerto", "calor_vivo", "dinamico"]

# fmt: off
_TABLA = [
    # NB: no combustibles
    (91, "NB1", "Urbano / desarrollado",                     0,0,0,0,0,       0,0,0,       0,   0,  0,0, 0),
    (92, "NB2", "Nieve / hielo",                             0,0,0,0,0,       0,0,0,       0,   0,  0,0, 0),
    (93, "NB3", "Agrícola",                                  0,0,0,0,0,       0,0,0,       0,   0,  0,0, 0),
    (98, "NB8", "Agua",                                      0,0,0,0,0,       0,0,0,       0,   0,  0,0, 0),
    (99, "NB9", "Suelo desnudo / roca",                      0,0,0,0,0,       0,0,0,       0,   0,  0,0, 0),
    # GR: pastizales (dinámicos)
    (101,"GR1", "Pasto corto, carga muy baja, seco",         0.10,0.00,0.00,0.30,0.00,  2200,2000,9999, 0.4, 15, 8000,8000, 1),
    (102,"GR2", "Pasto, carga baja, seco",                   0.10,0.00,0.00,1.00,0.00,  2000,1800,9999, 1.0, 15, 8000,8000, 1),
    (103,"GR3", "Pasto grueso, carga baja, húmedo",          0.10,0.40,0.00,1.50,0.00,  1500,1300,9999, 2.0, 30, 8000,8000, 1),
    (104,"GR4", "Pasto, carga moderada, seco",               0.25,0.00,0.00,1.90,0.00,  2000,1800,9999, 2.0, 15, 8000,8000, 1),
    (105,"GR5", "Pasto, carga baja, húmedo",                 0.40,0.00,0.00,2.50,0.00,  1800,1600,9999, 1.5, 40, 8000,8000, 1),
    (106,"GR6", "Pasto, carga moderada, húmedo",             0.10,0.00,0.00,3.40,0.00,  2200,2000,9999, 1.5, 40, 9000,9000, 1),
    (107,"GR7", "Pasto alto, carga alta, seco",              1.00,0.00,0.00,5.40,0.00,  2000,1800,9999, 3.0, 15, 8000,8000, 1),
    (108,"GR8", "Pasto alto, carga alta, húmedo",            0.50,1.00,0.00,7.30,0.00,  1500,1300,9999, 4.0, 30, 8000,8000, 1),
    (109,"GR9", "Pasto muy alto, carga muy alta, húmedo",    1.00,1.00,0.00,9.00,0.00,  1800,1600,9999, 5.0, 40, 8000,8000, 1),
    # GS: pasto-arbusto (dinámicos)
    (121,"GS1", "Pasto-arbusto, carga baja, seco",           0.20,0.00,0.00,0.50,0.65,  2000,1800,1800, 0.9, 15, 8000,8000, 1),
    (122,"GS2", "Pasto-arbusto, carga moderada, seco",       0.50,0.50,0.00,0.60,1.00,  2000,1800,1800, 1.5, 15, 8000,8000, 1),
    (123,"GS3", "Pasto-arbusto, carga moderada, húmedo",     0.30,0.25,0.00,1.45,1.25,  1800,1600,1600, 1.8, 40, 8000,8000, 1),
    (124,"GS4", "Pasto-arbusto, carga alta, húmedo",         1.90,0.30,0.10,3.40,7.10,  1800,1600,1600, 2.1, 40, 8000,8000, 1),
    # SH: arbustales
    (141,"SH1", "Arbustal, carga baja, seco",                0.25,0.25,0.00,0.15,1.30,  2000,1800,1600, 1.0, 15, 8000,8000, 1),
    (142,"SH2", "Arbustal, carga moderada, seco",            1.35,2.40,0.75,0.00,3.85,  2000,9999,1600, 1.0, 15, 8000,8000, 0),
    (143,"SH3", "Arbustal, carga moderada, húmedo",          0.45,3.00,0.00,0.00,6.20,  1600,9999,1400, 2.4, 40, 8000,8000, 0),
    (144,"SH4", "Arbustal, carga baja, húmedo",              0.85,1.15,0.20,0.00,2.55,  2000,1800,1600, 3.0, 30, 8000,8000, 0),
    (145,"SH5", "Arbustal, carga alta, seco",                3.60,2.10,0.00,0.00,2.90,   750,9999,1600, 6.0, 15, 8000,8000, 0),
    (146,"SH6", "Arbustal, carga baja, húmedo",              2.90,1.45,0.00,0.00,1.40,   750,9999,1600, 2.0, 30, 8000,8000, 0),
    (147,"SH7", "Arbustal, carga muy alta, seco",            3.50,5.30,2.20,0.00,3.40,   750,9999,1600, 6.0, 15, 8000,8000, 0),
    (148,"SH8", "Arbustal, carga alta, húmedo",              2.05,3.40,0.85,0.00,4.35,   750,9999,1600, 3.0, 40, 8000,8000, 0),
    (149,"SH9", "Arbustal, carga muy alta, húmedo",          4.50,2.45,0.00,1.55,7.00,   750,1800,1500, 4.4, 40, 8000,8000, 1),
    # TU: bosque con sotobosque
    (161,"TU1", "Bosque-pasto-arbusto, carga baja, seco",    0.20,0.90,1.50,0.20,0.90,  2000,1800,1600, 0.6, 20, 8000,8000, 1),
    (162,"TU2", "Bosque-arbusto, carga moderada, húmedo",    0.95,1.80,1.25,0.00,0.20,  2000,9999,1600, 1.0, 30, 8000,8000, 0),
    (163,"TU3", "Bosque-pasto-arbusto, carga moderada, húmedo",1.10,0.15,0.25,0.65,1.10,1800,1600,1400, 1.3, 30, 8000,8000, 1),
    (164,"TU4", "Bosque-arbusto, hojarasca de acícula corta",4.50,0.00,0.00,0.00,2.00,  2300,9999,2000, 0.5, 12, 8000,8000, 0),
    (165,"TU5", "Bosque-arbusto, carga muy alta, seco",      4.00,4.00,3.00,0.00,3.00,  1500,9999, 750, 1.0, 25, 8000,8000, 0),
    # TL: hojarasca
    (181,"TL1", "Hojarasca compacta, carga baja",            1.00,2.20,3.60,0.00,0.00,  2000,9999,9999, 0.2, 30, 8000,8000, 0),
    (182,"TL2", "Hojarasca de latifoliada, carga baja",      1.40,2.30,2.20,0.00,0.00,  2000,9999,9999, 0.2, 25, 8000,8000, 0),
    (183,"TL3", "Hojarasca de conífera, carga moderada",     0.50,2.20,2.80,0.00,0.00,  2000,9999,9999, 0.3, 20, 8000,8000, 0),
    (184,"TL4", "Hojarasca con troncos pequeños",            0.50,1.50,4.20,0.00,0.00,  2000,9999,9999, 0.4, 25, 8000,8000, 0),
    (185,"TL5", "Hojarasca de conífera, carga alta",         1.15,2.50,4.40,0.00,0.00,  2000,9999,9999, 0.6, 25, 8000,8000, 0),
    (186,"TL6", "Hojarasca de latifoliada, carga moderada",  2.40,1.20,1.20,0.00,0.00,  2000,9999,9999, 0.3, 25, 8000,8000, 0),
    (187,"TL7", "Hojarasca con troncos grandes",             0.30,1.40,8.10,0.00,0.00,  2000,9999,9999, 0.4, 25, 8000,8000, 0),
    (188,"TL8", "Hojarasca de acícula larga",                5.80,1.40,1.10,0.00,0.00,  1800,9999,9999, 0.3, 35, 8000,8000, 0),
    (189,"TL9", "Hojarasca de latifoliada, carga muy alta",  6.65,3.30,4.15,0.00,0.00,  1800,9999,9999, 0.6, 35, 8000,8000, 0),
    # SB: restos de corta / explosión
    (201,"SB1", "Restos, carga baja",                        1.50,3.00,11.00,0.00,0.00, 2000,9999,9999, 1.0, 25, 8000,8000, 0),
    (202,"SB2", "Restos, carga moderada",                    4.50,4.25,4.00,0.00,0.00,  2000,9999,9999, 1.0, 25, 8000,8000, 0),
    (203,"SB3", "Restos, carga alta",                        5.50,2.75,3.00,0.00,0.00,  2000,9999,9999, 1.2, 25, 8000,8000, 0),
    (204,"SB4", "Restos, carga muy alta",                    5.25,3.50,5.25,0.00,0.00,  2000,9999,9999, 2.7, 25, 8000,8000, 0),
]
# fmt: on

SAV_10H = 109.0
SAV_100H = 30.0
CODIGOS_NB = {91, 92, 93, 98, 99}


def tabla() -> pd.DataFrame:
    df = pd.DataFrame(_TABLA, columns=COLUMNAS)
    # 9999 = clase ausente (carga 0); se deja un SAV neutro para evitar divisiones por cero
    return df


def codigos_conocidos() -> list[int]:
    return [int(c) for c in tabla()["codigo"]]


def escribir_csv(ruta: Path) -> Path:
    df = tabla()
    df.to_csv(ruta, index=False, encoding="utf-8", lineterminator="\n")
    return Path(ruta)


def cargar_csv(ruta: Path) -> pd.DataFrame:
    df = pd.read_csv(ruta)
    faltan = [c for c in COLUMNAS if c not in df.columns]
    if faltan:
        raise ValueError(f"parametros_sb40.csv: faltan columnas {faltan}")
    return df


class TablaCombustible:
    """Parámetros por código, en arrays indexables por `idx` (posición en la tabla)."""

    def __init__(self, df: pd.DataFrame | None = None):
        df = tabla() if df is None else df.reset_index(drop=True)
        self.df = df
        self.codigo = df["codigo"].to_numpy(int)
        self.clave = df["clave"].to_numpy(str)
        self.idx_por_codigo = {int(c): i for i, c in enumerate(self.codigo)}
        self.n = len(df)
        # cargas (t/ac) por clase: 1h, 10h, 100h, herb, woody
        self.w = df[["w1h", "w10h", "w100h", "wherb", "wwoody"]].to_numpy(float)
        self.sav = np.column_stack([df["sav1h"], np.full(self.n, SAV_10H), np.full(self.n, SAV_100H),
                                    df["savherb"], df["savwoody"]]).astype(float)
        self.profundidad_ft = df["profundidad_ft"].to_numpy(float)
        self.mx_muerto = df["mx_muerto_pct"].to_numpy(float) / 100.0
        self.calor_muerto = df["calor_muerto"].to_numpy(float)
        self.calor_vivo = df["calor_vivo"].to_numpy(float)
        self.dinamico = df["dinamico"].to_numpy(bool)
        self.combustible = (self.w.sum(1) > 0) & (self.profundidad_ft > 0)
        self.grupo = np.array([k[:2] for k in self.clave])

    def mapa_indices(self, codigos: np.ndarray, nodata: int) -> np.ndarray:
        """Raster de códigos → raster de índices en la tabla (-1 = sin datos / desconocido).

        Los códigos que no están en la tabla (ni son NoData) se tratan como no combustibles y se avisa (P9)."""
        out = np.full(codigos.shape, -1, dtype=np.int16)
        for c, i in self.idx_por_codigo.items():
            out[codigos == c] = i
        out[codigos == nodata] = -1
        desconocidos = ~np.isin(codigos, self.codigo) & (codigos != nodata)
        if desconocidos.any():
            import warnings
            cods = np.unique(codigos[desconocidos])
            warnings.warn(f"Códigos de combustible desconocidos tratados como no combustibles: {cods[:20].tolist()}"
                          f" ({int(desconocidos.sum())} celdas)", stacklevel=2)
        return out

    def _por_modelo(self, base: np.ndarray, por_grupo: dict | None, por_codigo: dict | None, conv=float) -> np.ndarray:
        """Valor por modelo: `base`, pisado por familia S&B (GR, SH, …) y después por código."""
        out = np.array(base, float, copy=True)
        for g, v in (por_grupo or {}).items():
            m = self.grupo == str(g).upper()
            if not m.any():
                raise ValueError(f"familia de combustible '{g}' desconocida (opciones: {sorted(set(self.grupo))})")
            out[m] = conv(v)
        for c, v in (por_codigo or {}).items():
            i = self.idx_por_codigo.get(int(c))
            if i is None:
                raise ValueError(f"código de combustible {c} desconocido")
            out[i] = conv(v)
        return out

    def mx_ajustada(self, mx_grupo: dict | None = None, mx_codigo: dict | None = None) -> np.ndarray:
        """Humedad de extinción del muerto (fracción) con `mx_grupo` / `mx_codigo` (valores > 1 se leen como %)."""
        return self._por_modelo(self.mx_muerto, mx_grupo, mx_codigo, lambda v: float(v) / 100.0 if float(v) > 1.0 else float(v))

    def factores_ros(self, k_global: float = 1.0, k_grupo: dict | None = None, k_codigo: dict | None = None) -> np.ndarray:
        """Multiplicador de R0 por modelo: k_global × (k_codigo si está, si no k_grupo, si no 1) (v3.0 `k_clase`)."""
        return float(k_global) * self._por_modelo(np.ones(self.n), k_grupo, k_codigo)

    def waf(self) -> np.ndarray:
        """Factor de ajuste del viento (10 m → media llama) por modelo. Ver physics.viento."""
        from ..physics.viento import waf_sin_dosel
        f = waf_sin_dosel(self.profundidad_ft)
        # bajo dosel (TU, TL): valores de Andrews (2012) para dosel abierto / cerrado
        f = np.where(self.grupo == "TU", 0.3, f)
        f = np.where(self.grupo == "TL", 0.2, f)
        return np.where(self.combustible, f, 0.0)
