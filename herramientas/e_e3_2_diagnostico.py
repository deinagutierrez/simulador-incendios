"""Diagnóstico del cambio de clase SB40 de E-E3-2 en v4.0: verano de GEE contra verano de AWS.

    python herramientas/e_e3_2_diagnostico.py

No es parte de la evaluación ni cambia su resultado: se corrió después de ver el veredicto de la primera evaluación (no se
cumple) para saber de dónde sale el cambio de clase de v4.0. Informe: `docs/etapa3/prerregistros/E-E3-2_diagnostico.md`.

Solo lee. Necesita lo que deja `herramientas/e_e3_2.py` en `resultados/app/E-E3-2/c/verano_aws/` (los compuestos de enero a
marzo de 2024 hechos por AWS); los de GEE son los del repositorio. Arma el SB40 de cada lado con las funciones de v4.0
(`simulador/fuel/generar_sb40.py`, cargado como archivo suelto: es numpy y pandas, no importa el motor) siguiendo lo que
hace `incendios_sl.eventos.preparar_combustible` con la regla 3.3b: cobertura MapBiomas 2023, MDT, mediana por celda de
los tres meses y corrimiento de las leñosas. La primera salida comprueba que el resultado coincide con el de la evaluación.
"""
from __future__ import annotations

import importlib.util
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

REPO = Path(__file__).resolve().parents[1]
ENT = REPO / "datos" / "inputSimulacion"
VERANO_AWS = REPO / "resultados" / "app" / "E-E3-2" / "c" / "verano_aws"
ANIO = 2024
SEMILLA = 0

_spec = importlib.util.spec_from_file_location("generar_sb40", REPO / "src" / "v4.0" / "src" / "simulador" / "fuel" / "generar_sb40.py")
g = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(g)
NOMBRE = {v: k for k, v in g.COD.items()}


def leer(p: Path):
    with rasterio.open(p) as s:
        return s.read(), s.nodata


def meses(carpeta: Path) -> tuple[np.ndarray, np.ndarray]:
    nd, nm = [], []
    for m in (1, 2, 3):
        a, nodata = leer(carpeta / f"NDVI_NDMI_{ANIO}_{m:02d}.tif")
        a = a.astype("float32")
        a[a == nodata] = np.nan
        nd.append(a[0] / 10000)
        nm.append(a[1] / 10000)
    return np.array(nd), np.array(nm)


def mediana(x: np.ndarray) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmedian(x, 0)


def main() -> int:
    if not VERANO_AWS.exists():
        print(f"falta {VERANO_AWS}: correr antes herramientas/e_e3_2.py")
        return 2
    lc = leer(ENT / "cobertura" / "cobertura_mapbiomas_col3_2023_las_lagunas_potrerillos.tif")[0][0]
    dem = leer(ENT / "sim_v4" / "estaticos" / "topografia" / "mdt.tif")[0][0]
    umb = pd.read_csv(ENT / "sim_v4" / "estaticos" / "combustible" / "umbrales_ndvi.csv", encoding="utf-8")
    nd_g, nm_g = meses(ENT / "sim_v4" / "dinamicos" / "indices")
    nd_a, nm_a = meses(VERANO_AWS)
    gee = (mediana(nd_g), mediana(nm_g))
    aws = (mediana(nd_a), mediana(nm_a))

    def sb40(ndvi, ndmi, corr_de=None):
        """SB40 con la regla 3.3b. `corr_de`: NDVI del que se toma el corrimiento de las leñosas (None = el propio)."""
        est, corr = g.ndvi_estructural_anomalia(lc, ndvi if corr_de is None else corr_de, umb)
        if corr_de is not None:
            est = np.array(ndvi, dtype="float32", copy=True)
            for clase, d in corr.items():
                est[lc == clase] += d
        return g.generar(lc, dem, ndvi, ndmi, umb, ndvi_estructural=est), corr

    def cambio(a, b) -> tuple[float, int, int]:
        val = (a != g.NODATA) & (b != g.NODATA)
        n = int(((a != b) & val).sum())
        return 100.0 * n / max(int(val.sum()), 1), n, int(val.sum())

    sb_g, corr_g = sb40(*gee)
    sb_a, corr_a = sb40(*aws)
    dist = (sb_g != sb_a) & (sb_g != g.NODATA) & (sb_a != g.NODATA)
    claves = np.where((lc == 12) & (dem >= g.COTA_ALTURA), -12, lc.astype("int16"))

    print("== 1. Reconstrucción (tiene que dar lo de E-E3-2_resultados.json de esa evaluación, partes.c.por_motor.v4.0.clases)")
    f, n, tot = cambio(sb_g, sb_a)
    print(f"  celdas con dato {tot}; distintas {n}; {f:.3f} %")
    print(f"  corrimiento del NDVI de las leñosas, GEE: {corr_g}")
    print(f"  corrimiento del NDVI de las leñosas, AWS: {corr_a}")

    print("\n== 2. Por cobertura MapBiomas (-12 = pastizal de altura)")
    for k in sorted(np.unique(claves)):
        m = claves == k
        if m.sum() < 1000:
            continue
        print(f"  {int(k):>4}: {int(m.sum()):>8} celdas, {100 * m.mean():5.1f} % del dominio; cambia {100 * dist[m].mean():5.1f} %;"
              f" aporta {100 * dist[m].sum() / max(dist.sum(), 1):5.1f} % de los cambios")

    print("\n== 3. Transiciones más frecuentes (GEE -> AWS)")
    par, cnt = np.unique(np.stack([sb_g[dist], sb_a[dist]]), axis=1, return_counts=True)
    for i in np.argsort(-cnt)[:12]:
        print(f"  {NOMBRE.get(int(par[0, i]), par[0, i])} -> {NOMBRE.get(int(par[1, i]), par[1, i])}: {int(cnt[i])} ({100 * cnt[i] / dist.sum():.1f} %)")

    print("\n== 4. Qué entrada lo causa (% de celdas que cambian respecto del SB40 de GEE)")
    casos = {
        "NDVI de AWS y NDMI de GEE": sb40(aws[0], gee[1])[0],
        "NDVI de GEE y NDMI de AWS": sb40(gee[0], aws[1])[0],
        "todo AWS, con el corrimiento de las leñosas de GEE": sb40(aws[0], aws[1], corr_de=gee[0])[0],
        "todo GEE, con el corrimiento de las leñosas de AWS": sb40(gee[0], gee[1], corr_de=aws[0])[0],
    }
    for m in range(3):
        nd, nm = nd_g.copy(), nm_g.copy()
        nd[m], nm[m] = nd_a[m], nm_a[m]
        casos[f"todo GEE salvo el mes {m + 1}, de AWS"] = sb40(mediana(nd), mediana(nm))[0]
    for nombre, s in casos.items():
        print(f"  {nombre}: {cambio(sb_g, s)[0]:.3f} %")

    print("\n== 5. Diferencia AWS - GEE por mes y de la mediana de verano")
    filas = [("enero", (nd_a[0], nm_a[0]), (nd_g[0], nm_g[0])), ("febrero", (nd_a[1], nm_a[1]), (nd_g[1], nm_g[1])),
             ("marzo", (nd_a[2], nm_a[2]), (nd_g[2], nm_g[2])), ("mediana de verano", aws, gee)]
    for nombre, a, b in filas:
        for ind, x, y in (("NDVI", a[0], b[0]), ("NDMI", a[1], b[1])):
            d = (x - y)[np.isfinite(x) & np.isfinite(y)]
            print(f"  {nombre:>17} {ind}: mediana con signo {np.median(d):+.4f}; media {d.mean():+.4f};"
                  f" |d| mediana {np.median(np.abs(d)):.4f}; percentil 95 {np.percentile(np.abs(d), 95):.4f}")

    print("\n== 6. Tamaño de la diferencia de NDVI de verano y celdas que cambian")
    ad = np.abs(aws[0] - gee[0])
    for t in (0.005, 0.01, 0.02, 0.05):
        print(f"  |d| < {t}: {100 * (ad < t).mean():.1f} % del dominio; {100 * (ad[dist] < t).mean():.1f} % de las celdas que cambiaron")
    print(f"  |d| >= 0.02: {100 * (ad >= 0.02).mean():.1f} % del dominio; de esas cambia de clase el {100 * dist[ad >= 0.02].mean():.1f} %")

    print("\n== 7. Cercanía a los umbrales de la regla (con el NDVI que usa el lado GEE)")
    est_g, _ = g.ndvi_estructural_anomalia(lc, gee[0], umb)
    u = {str(r.clave): (float(r.ndvi_p33), float(r.ndvi_p67)) for r in umb.itertuples()}
    cerca = {t: np.zeros(lc.shape, bool) for t in (0.005, 0.01, 0.02)}
    sensibles = np.zeros(lc.shape, bool)
    for clave, modelos in g.TABLA.items():
        m = claves == (-12 if clave == "12_alt" else clave)
        if not m.any() or str(clave) not in u or len(set(modelos)) == 1:
            continue
        sensibles |= m
        v = est_g if clave in g.LENOSAS else gee[0]
        p33, p67 = u[str(clave)]
        dmin = np.minimum(np.abs(v - p33) if modelos[0] != modelos[1] else np.inf,
                          np.abs(v - p67) if modelos[1] != modelos[2] else np.inf)
        for t in cerca:
            cerca[t] |= m & (dmin < t)
    print(f"  celdas en coberturas cuya clase depende del tercil de NDVI: {100 * sensibles.mean():.1f} % del dominio")
    for t, c in cerca.items():
        print(f"  a menos de {t} de un umbral que cambia la clase: {100 * c.mean():.1f} % del dominio;"
              f" ahí está el {100 * (dist & c).sum() / dist.sum():.1f} % de las celdas que cambiaron")
    print("  ancho del tercil medio (p67 - p33):",
          ", ".join(f"{k} {b - a:.3f}" for k, (a, b) in u.items() if k in ("3", "4", "12", "12_alt", "15", "63", "66", "77")))

    print("\n== 8. Humedad (NDMI > 0,15 pasa las herbáceas a GR6)")
    her = np.isin(claves, (12, -12, 15, 63))
    hg, ha = her & (gee[1] > g.UMBRAL_NDMI_HUMEDO), her & (aws[1] > g.UMBRAL_NDMI_HUMEDO)
    print(f"  herbáceas húmedas: GEE {int(hg.sum())}, AWS {int(ha.sum())}; distintas {int((hg ^ ha).sum())}"
          f" ({100 * (hg ^ ha).sum() / dist.sum():.1f} % de los cambios)")

    print(f"\n== 9. Sensibilidad de la regla: ruido gaussiano sin sesgo sobre el NDVI de verano de GEE (semilla {SEMILLA})")
    rng = np.random.default_rng(SEMILLA)
    for s in (0.002, 0.005, 0.01, 0.02):
        r = gee[0] + rng.normal(0, s, lc.shape).astype("float32")
        print(f"  desvío {s} (|d| mediana {0.6745 * s:.4f}): cambia {cambio(sb_g, sb40(r, gee[1])[0])[0]:.2f} %")

    print("\n== 10. Dónde están las diferencias grandes de febrero (|d NDVI| >= 0,05)")
    df = nd_a[1] - nd_g[1]
    grande = np.abs(df) >= 0.05
    print(f"  {100 * grande.mean():.1f} % del dominio; diferencia media ahí {df[grande].mean():+.3f}; AWS mayor en el {100 * (df[grande] > 0).mean():.0f} %")
    print("  % con diferencia grande en 10 franjas de norte a sur:",
          ", ".join(f"{100 * x.mean():.1f}" for x in np.array_split(grande.mean(1), 10)))
    print("  % con diferencia grande en 10 franjas de oeste a este:",
          ", ".join(f"{100 * x.mean():.1f}" for x in np.array_split(grande.mean(0), 10)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
