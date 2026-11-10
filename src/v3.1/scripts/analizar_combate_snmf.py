"""Análisis del combate en los reportes diarios del SNMF para San Luis (2020-2026), base de la parametrización local
del módulo de contención del modelo v2 (docs/13).

El CSV del SNMF tiene un reporte por incendio y por día con `estado` (Activo / Contenido / Controlado / Extinguido) y un
campo `observaciones` en dos formatos: bloques estructurados `[ Tipo: rrhh. Subtipo: bomberos. Cantidad: 6. ]` (2020 y
2024-2026) y texto extraído de PDF con espacios espurios (`BB.VV. Merlo, Los Molles ... SNMF: 1 AT 802`, 2021-2023).
De cada reporte se extraen: superficie informada, personal por tipo, cuarteles de bomberos voluntarios nombrados, medios
aéreos (AT-802, helicóptero) y brigadistas nacionales. Los reportes se agrupan en eventos (misma fecha de inicio y mismo
nombre o puntos a menos de 3 km) y por evento se calculan los tiempos del SNMF (días desde el inicio hasta el primer
reporte, la primera contención y la extinción), las reactivaciones (Contenido/Controlado -> Activo) y la tasa efectiva
de línea = perímetro de la superficie final / horas de combate hasta la contención.

Los tiempos del SNMF tienen resolución diaria: las horas se informan como intervalo [mín, máx] (contenido el mismo día
del inicio -> 4-24 h; d días después -> 24·d-12 a 24·d+12 h). HIPÓTESIS documentadas en docs/13.

Uso: python scripts/analizar_combate_snmf.py [--csv ruta] [--salida dir]
Salida: resultados/v3.0/combate_snmf/{reportes,eventos,resumen_tamano,resumen_mes,ajuste_despacho}.csv y resumen por pantalla.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from incendios_sl import config as cfgmod  # noqa: E402

CSV_SNMF = "registros_incendios_san_luis_2020-2026(SNMF).csv"
CONTENIDO = ("Contenido", "Controlado", "Extinguido")
CLASES_HA = [0, 10, 100, 1000, 10000, np.inf]
ETIQ_HA = ["<10", "10-100", "100-1.000", "1.000-10.000", ">10.000"]
# régimen territorial de la respuesta (docs/13 §2.1): departamento -> régimen; el resto es "serrano"
REGIMEN_DEPTO = {"pueyrred": "periurbano", "pedernera": "periurbano", "dupuy": "llanura_sur"}   # subcadenas sin acentos (el CSV tiene acentos corruptos)
LB_PERIMETRO = 2.0            # relación largo/ancho de la elipse para el perímetro (HIPÓTESIS; Anderson 1983 con viento ~3-5 m/s)


# ------------------------------------------------------------------ extracción por reporte
def _num(s: str) -> float:
    """'1.700,0' -> 1700.0; '600,00' -> 600.0; '1606' -> 1606.0."""
    s = s.strip(".")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return np.nan


def _bloques(o: str) -> list[dict[str, str]]:
    out = []
    for b in re.findall(r"\[([^\]]*)\]", o):
        d: dict[str, str] = {}
        for k, v in re.findall(r"(Tipo|Subtipo|Cantidad|Modelo tipo|Instituci.n): *([^.\]]*)", b):
            k = "Institucion" if k.startswith("Instituci") else k
            d[k] = (d[k] + "|" + v.strip()) if k in d else v.strip()   # 'Institución' puede repetirse
        out.append(d)
    return out


def _cuarteles(o: str) -> set[str]:
    """Cuarteles de bomberos voluntarios nombrados en el texto libre ('BB.VV. Lafinur, Quines y Merlo')."""
    out: set[str] = set()
    for seg in re.findall(r"BB\s*\.?\s*V\s*V\s*\.?\s*([^.\[\]]*?)(?=SNMF|BB\s*\.?\s*PL|Bri\s*For|Vialidad|\(|\.\s|$|\s-\s|PROV)", o):
        for nom in re.split(r",|\s+y\s+", seg):
            nom = re.sub(r"\s+", "", nom).lower()
            nom = re.sub(r"^(de|del)", "", nom)
            if 2 < len(nom) < 30:
                out.add(nom)
    return out


def parsear_reporte(o: str) -> dict:
    o = o if isinstance(o, str) else ""
    comp = re.sub(r"\s+", "", o)
    r: dict = {"formato": "estructurado" if "Tipo:" in o else ("texto" if o else "vacio")}
    m = re.search(r"Superficie:?[A-Za-zÁÉÍÓÚÑ]*?(\d[\d.]*(?:,\d+)?)", comp)
    r["sup_ha_rep"] = _num(m.group(1)) if m else np.nan
    # personal
    pers = {"bomberos": 0.0, "policia": 0.0, "brigadistas_snmf": 0.0, "provincial": 0.0, "otros": 0.0}
    aereo_av = aereo_hel = 0.0; aereo_flag = False
    for b in _bloques(o):
        cant = _num(b["Cantidad"]) if b.get("Cantidad") else np.nan
        tipo, sub, inst = b.get("Tipo", ""), b.get("Subtipo", ""), b.get("Institucion", "").lower()
        if tipo == "aereo":
            aereo_flag = True
            n = cant if np.isfinite(cant) else 1.0
            if "helic" in sub:
                aereo_hel += n
            else:
                aereo_av += n
        elif tipo == "rrhh" and np.isfinite(cant):
            if "bnc" in inst or "brigad" in inst or ("snmf" in inst and sub in ("", "otros")):
                pers["brigadistas_snmf"] += cant
            elif sub == "bomberos":
                pers["bomberos"] += cant
            elif sub == "policia_provincial":
                pers["policia"] += cant
            elif sub == "plan_provincial_manejo_del_fuego":
                pers["provincial"] += cant
            else:
                pers["otros"] += cant
    # formato texto (PDF)
    m = re.search(r"PersonalBomb\.?:(\d+)", comp)
    if m:
        pers["bomberos"] += float(m.group(1))
    m = re.search(r"(\d+)BrigNac", comp)
    if m:
        pers["brigadistas_snmf"] += float(m.group(1))
    if r["formato"] == "texto":
        for m in re.finditer(r"(\d+)AT-?802", comp):
            aereo_av += float(m.group(1)); aereo_flag = True
        for m in re.finditer(r"(\d+)Helic", comp, re.I):
            aereo_hel += float(m.group(1)); aereo_flag = True
        if re.search(r"avi[oó�]nhidrante|hidroavi", comp, re.I):
            aereo_flag = True
    r.update({f"n_{k}": v for k, v in pers.items()})
    r["n_personal"] = sum(pers.values())
    cu = _cuarteles(o)
    for b in _bloques(o):     # formato estructurado: "Institución: El Trapiche, La Carolina, ... Subtipo: bomberos"
        if b.get("Subtipo") == "bomberos" and b.get("Institucion"):
            for nom in re.split(r",|\|", b["Institucion"]):
                nom = re.sub(r"\s+", "", nom).lower()
                if 2 < len(nom) < 30 and not nom.startswith(("bomberosde", "otros", "snmf")):
                    cu.add(nom)
    r["cuarteles"] = ";".join(sorted(cu)); r["n_cuarteles"] = len(cu)
    r["bb_policia"] = bool(re.search(r"BB\.?PL|Bomberosde(la)?Polic", comp))
    r["brifor"] = bool(re.search(r"BriFor", comp))
    r["aereo"] = aereo_flag; r["n_aviones"] = aereo_av; r["n_helicopteros"] = aereo_hel
    r["recursos_declarados"] = bool(r["n_personal"] or r["n_cuarteles"] or r["bb_policia"] or aereo_flag or "Subtipo: bomberos" in o)
    # vegetación (porcentajes)
    for k, pat in (("veg_bosque", r"BosqueNativo:?(\d+)"), ("veg_arbustal", r"Arbustal/?Matorral:?(\d+)"), ("veg_pastizal", r"Pastizal:?(\d+)")):
        m = re.search(pat, comp)
        r[k] = float(m.group(1)) if m else np.nan
    r["dificil_acceso"] = bool(re.search(r"dif[ií�]cilacceso", comp, re.I))
    r["reinicio"] = bool(re.search(r"reinicio|reactiv", comp, re.I))
    return r


# ------------------------------------------------------------------ agrupamiento en eventos
def _norm_nombre(s: str) -> str:
    s = re.sub(r"[^A-Z]", "", str(s).upper().replace("PJE", "").replace("PARAJE", ""))
    return s[:8]


def agrupar(df: pd.DataFrame) -> pd.Series:
    """Union-find: mismos fecha_inicio y (nombre normalizado igual o puntos a < 3 km), o mismo evento satelital
    (`evento_sat` del compilador dNBR) con inicios a <= 7 días (Las Lagunas / Potrerillos 2024)."""
    padre = list(range(len(df)))

    def raiz(i):
        while padre[i] != i:
            padre[i] = padre[padre[i]]; i = padre[i]
        return i
    for _, g in df.groupby("fecha_inicio"):
        idx = g.index.to_numpy()
        lat = g.latitud_dec.to_numpy(); lon = g.longitud_dec.to_numpy(); nom = g.nombre_n.to_numpy()
        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                d_km = np.hypot((lat[a] - lat[b]) * 111.0, (lon[a] - lon[b]) * 93.5)
                if nom[a] == nom[b] or (np.isfinite(d_km) and d_km < 3.0):
                    ra, rb = raiz(idx[a]), raiz(idx[b])
                    if ra != rb:
                        padre[rb] = ra
    for _, g in df[df.evento_sat.notna()].groupby("evento_sat"):
        idx = g.sort_values("fecha_inicio").index.to_numpy()
        for a, b in zip(idx, idx[1:]):
            if (df.at[b, "fecha_inicio"] - df.at[a, "fecha_inicio"]).days <= 7:
                ra, rb = raiz(a), raiz(b)
                if ra != rb:
                    padre[rb] = ra
    return pd.Series([raiz(i) for i in range(len(df))], index=df.index)


def resumir_evento(g: pd.DataFrame) -> dict:
    g = g.sort_values("fecha_reporte")
    t0 = g.fecha_inicio.min()
    est = g.estado.tolist()
    d_rep = (g.fecha_reporte.min() - t0).days
    cont = g[g.estado.isin(CONTENIDO)]
    ext = g.fecha_extincion.dropna()
    ext_rep = g[g.estado == "Extinguido"].fecha_reporte
    f_ext = ext.min() if len(ext) else (ext_rep.min() if len(ext_rep) else pd.NaT)
    d_ext = (f_ext - t0).days if pd.notna(f_ext) else np.nan
    # el SNMF publica con atraso (fecha_extincion anterior al primer reporte en 1 de cada 4 reportes): la contención
    # ocurrió a más tardar el primer reporte contenido y a más tardar la extinción
    d_cont = np.nanmin([(cont.fecha_reporte.min() - t0).days if len(cont) else np.nan, d_ext]) if (len(cont) or np.isfinite(d_ext)) else np.nan
    # reactivaciones: paso de un estado de contención a 'Activo'
    reac = sum(1 for a, b in zip(est, est[1:]) if a in CONTENIDO and b == "Activo")
    dias_cont = sum(1 for a in est[:-1] if a in CONTENIDO)     # reportes contenidos con un reporte posterior (exposición al escape)
    sup_rep = g.sup_ha_rep.max()
    sup_sat = g.superficie_ha_sat.max()
    sup = sup_sat if np.isfinite(sup_sat) else sup_rep
    cuart = set(";".join(g.cuarteles.fillna("")).split(";")) - {""}
    return {
        "evento": " / ".join(dict.fromkeys(g.nombre)), "fecha_inicio": t0.date(), "anio": t0.year, "mes": t0.month,
        "departamento": g.departamento.mode().iloc[0] if g.departamento.notna().any() else None,
        "lat": g.latitud_dec.median(), "lon": g.longitud_dec.median(),
        "n_reportes": len(g), "estados": ">".join(est),
        "d_primer_reporte": d_rep, "d_contencion": d_cont, "d_extincion": d_ext, "reactivaciones": reac, "dias_contenido_expuestos": dias_cont,
        "sup_ha_rep": sup_rep, "sup_ha_sat": sup_sat, "sup_ha": sup, "evento_sat": g.evento_sat.dropna().iloc[0] if g.evento_sat.notna().any() else None,
        "recursos_declarados": bool(g.recursos_declarados.any()),
        "max_personal": g.n_personal.max(), "max_bomberos": g.n_bomberos.max(), "max_policia": g.n_policia.max(),
        "max_brigadistas_snmf": g.n_brigadistas_snmf.max(), "max_provincial": g.n_provincial.max(),
        "n_cuarteles_total": len(cuart), "max_cuarteles_dia": g.n_cuarteles.max(), "cuarteles": ";".join(sorted(cuart)),
        "bb_policia": bool(g.bb_policia.any()), "brifor": bool(g.brifor.any()),
        "aereo": bool(g.aereo.any()), "dias_aereo": int(g.aereo.sum()), "max_aviones": g.n_aviones.max(), "max_helicopteros": g.n_helicopteros.max(),
        "d_primer_aereo": (g[g.aereo].fecha_reporte.min() - t0).days if g.aereo.any() else np.nan,
        "veg_bosque": g.veg_bosque.median(), "veg_arbustal": g.veg_arbustal.median(), "veg_pastizal": g.veg_pastizal.median(),
        "dificil_acceso": bool(g.dificil_acceso.any()),
    }


def regimen(depto) -> str:
    d = str(depto).lower()
    return next((v for k, v in REGIMEN_DEPTO.items() if k in d), "serrano")


def ajuste_despacho(ev: pd.DataFrame) -> pd.DataFrame:
    """Ajuste log-log tasa = a · A^b por régimen y global (base de `contencion.despacho` en modelo_v2.yaml), y
    probabilidad de medios aéreos por clase de tamaño final."""
    m = ev[ev.tasa_linea_m_h.notna() & (ev.sup_ha > 0)]
    filas = []
    for reg, g in [("todos", m)] + list(m.groupby("regimen")):
        b, la = np.polyfit(np.log10(g.sup_ha), np.log10(g.tasa_linea_m_h), 1)
        res = np.log10(g.tasa_linea_m_h) - (la + b * np.log10(g.sup_ha))
        filas.append({"regimen": reg, "n": len(g), "a": 10 ** la, "b": b, "dispersion_dex": res.std()})
    cl = ev[ev.sup_ha.notna()].groupby("clase_ha", observed=False).aereo.agg(["size", "mean"]).reset_index()
    for _, r in cl.iterrows():
        filas.append({"regimen": f"p_aereo {r.clase_ha}", "n": int(r["size"]), "a": r["mean"]})
    a = ev[ev.aereo]
    filas.append({"regimen": "d_primer_aereo (mediana días)", "n": len(a), "a": a.d_primer_aereo.median()})
    return pd.DataFrame(filas)


def tasa_efectiva(ev: pd.DataFrame) -> pd.DataFrame:
    """Perímetro de la elipse de superficie A y L/B dado (Ramanujan) / horas de combate hasta la contención (intervalo)."""
    A = ev.sup_ha * 1e4
    b = np.sqrt(A / (np.pi * LB_PERIMETRO)); a = LB_PERIMETRO * b
    h = 3 * ((a - b) / (a + b)) ** 2
    ev["perimetro_m"] = np.pi * (a + b) * (1 + h / (10 + np.sqrt(4 - h)))
    d = ev.d_contencion
    ev["h_cont_min"] = np.where(d <= 0, 4.0, 24.0 * d - 12.0)
    ev["h_cont_max"] = np.where(d <= 0, 24.0, 24.0 * d + 12.0)
    ev["tasa_linea_min_m_h"] = ev.perimetro_m / ev.h_cont_max
    ev["tasa_linea_max_m_h"] = ev.perimetro_m / ev.h_cont_min
    ev["tasa_linea_m_h"] = np.sqrt(ev.tasa_linea_min_m_h * ev.tasa_linea_max_m_h)   # media geométrica del intervalo
    ev["tasa_por_persona_m_h"] = ev.tasa_linea_m_h / ev.max_personal.where(ev.max_personal > 0)
    return ev


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--csv", default=None); ap.add_argument("--salida", default=None)
    a = ap.parse_args(argv)
    df = pd.read_csv(Path(a.csv) if a.csv else cfgmod.ruta(CSV_SNMF))
    for c in ("fecha_reporte", "fecha_inicio", "fecha_extincion"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df = df.join(pd.DataFrame([parsear_reporte(o) for o in df.observaciones], index=df.index))
    df["nombre_n"] = df.nombre.map(_norm_nombre)
    df["evento_id"] = agrupar(df)
    ev = pd.DataFrame([resumir_evento(g) | {"evento_id": k} for k, g in df.groupby("evento_id")])
    ev = tasa_efectiva(ev)
    ev["clase_ha"] = pd.cut(ev.sup_ha, CLASES_HA, labels=ETIQ_HA, right=False)
    ev["regimen"] = ev.departamento.map(regimen)
    out = Path(a.salida) if a.salida else cfgmod.dir_resultados() / "combate_snmf"
    out.mkdir(parents=True, exist_ok=True)
    df.drop(columns=["nombre_n"]).to_csv(out / "reportes.csv", index=False)
    ev.sort_values("fecha_inicio").to_csv(out / "eventos.csv", index=False)

    q = lambda s, p: float(np.nanpercentile(s, p)) if np.isfinite(s).any() else np.nan  # noqa: E731
    con_sup = ev[ev.sup_ha.notna()]
    filas = []
    for cl, g in list(con_sup.groupby("clase_ha", observed=False)) + [("todos", con_sup), ("sin superficie", ev[ev.sup_ha.isna()])]:
        if len(g) == 0:
            continue
        rec = g[g.recursos_declarados]
        filas.append({"clase_ha": cl, "n_eventos": len(g), "sup_ha_mediana": g.sup_ha.median(),
                      "frac_recursos_declarados": g.recursos_declarados.mean(),
                      "frac_aereo": g.aereo.mean(), "frac_aereo_entre_declarados": rec.aereo.mean() if len(rec) else np.nan,
                      "personal_mediana": rec.max_personal.replace(0, np.nan).median(), "personal_p90": q(rec.max_personal.replace(0, np.nan), 90),
                      "cuarteles_mediana": rec.n_cuarteles_total.replace(0, np.nan).median(),
                      "d_primer_reporte_mediana": g.d_primer_reporte.median(), "d_contencion_mediana": g.d_contencion.median(),
                      "d_contencion_p90": q(g.d_contencion, 90), "d_extincion_mediana": g.d_extincion.median(),
                      "frac_contenido_dia0": (g.d_contencion <= 0).mean(), "frac_contenido_dia1": (g.d_contencion <= 1).mean(),
                      "frac_reactivado": (g.reactivaciones > 0).mean(),
                      "tasa_linea_mediana_m_h": g.tasa_linea_m_h.median(), "tasa_linea_p25": q(g.tasa_linea_m_h, 25), "tasa_linea_p75": q(g.tasa_linea_m_h, 75),
                      "tasa_por_persona_mediana": g.tasa_por_persona_m_h.median()})
    rt = pd.DataFrame(filas); rt.to_csv(out / "resumen_tamano.csv", index=False)
    aj = ajuste_despacho(ev); aj.to_csv(out / "ajuste_despacho.csv", index=False)
    rm = ev.groupby("mes").agg(n_eventos=("evento", "size"), sup_ha_total=("sup_ha", "sum"), frac_aereo=("aereo", "mean"),
                               d_contencion_mediana=("d_contencion", "median")).reset_index()
    rm.to_csv(out / "resumen_mes.csv", index=False)

    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
    print(f"{len(df)} reportes -> {len(ev)} eventos ({ev.sup_ha.notna().sum()} con superficie; {ev.recursos_declarados.sum()} con recursos declarados)")
    print(f"formato de observaciones: {df.formato.value_counts().to_dict()}")
    print("\nPor clase de tamaño:\n", rt.round(2).to_string(index=False))
    print("\nPor mes:\n", rm.round(2).to_string(index=False))
    print("\nAjuste del despacho (tasa = a·A^b) y medios aéreos:\n", aj.round(3).to_string(index=False))
    print(f"\nSalidas en {out}")


if __name__ == "__main__":
    main()
