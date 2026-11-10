"""Lista nominal de eventos de la Fase 1 (protocolo de evaluación v1.0, §3.2–§3.4, §4.1, §5).

Aplica solo los criterios 1–3 de §3.2 (no prepara insumos). Solo lectura sobre los datos de origen.

Uso (desde src/v4.0; `--salida` relativa a src/v4.0 o absoluta; NO apuntar a la lista congelada del protocolo):
    python -I app/evaluacion/eventos_fase1.py --salida ../../resultados/v4.0/banco/protocolo_regenerado
Salidas: eventos_fase1.csv (una fila por componente candidato, con motivo de descarte), focos_atribuidos.csv,
conciliacion_cp.csv, resumen_fase1.json (con sha256 de entradas y salidas).
En v4.0 necesita `crudos.conjunto_pruebas` (CP/ de la entrega: SM01 y conciliación), que no está en este equipo; la lista
vigente es la congelada en datos/inputSimulacion/banco_v4/protocolo/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import timedelta
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize, shapes
from scipy import ndimage
from shapely.geometry import shape
from shapely.ops import unary_union

SEMILLA = 20261015
HA_CELDA = 0.09
UMBRAL_HA = 100.0
FRAC_DENTRO_MIN = 0.95
DIST_BORDE_MIN_M = 3000.0
BUFFER_FOCOS_M = 1000.0
DIST_PARTE_M = 2000.0
HUECO_GRUPO_DIAS = 3
MIN_FOCOS_T80 = 20
VISTOS = {  # §3.4: eventos ya vistos por algún motor (oid MapBiomas, año calendario, mes) -> quién
    ("2024_41914", 2024, 9): "MOD (calibración) y SIM (SM05)",
    ("2022_43667", 2022, 9): "MOD (validación Renca)",
    ("2021_46201", 2022, 1): "MOD (validación Puertas Coloradas)",
}


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and np.isnan(x)) and str(x) != ""


def orden(id_evento: str) -> str:
    return hashlib.sha256(f"{SEMILLA}:{id_evento}".encode()).hexdigest()


def sup_smf(texto) -> float:
    m = re.search(r"Superficie:\s*([\d\.]+(?:,\d+)?)", str(texto))
    if not m:
        return np.nan
    try:
        return float(m.group(1).replace(".", "").replace(",", "."))
    except ValueError:
        return np.nan


def incidentes_snmf(csv: Path) -> pd.DataFrame:
    """Incidentes únicos según CP/ D09: (fecha_inicio, lat, lon a 4 decimales) y unión por evento_sat."""
    d = pd.read_csv(csv, encoding="utf-8-sig")
    d = d[d.coordenada_valida.astype(str) == "True"].copy()
    d["k"] = d.fecha_inicio.astype(str) + "|" + d.latitud_dec.round(4).astype(str) + "|" + d.longitud_dec.round(4).astype(str)
    d["ha_smf"] = d.observaciones.map(sup_smf)
    padre = {k: k for k in d.k.unique()}

    def raiz(k):
        while padre[k] != k:
            padre[k] = padre[padre[k]]
            k = padre[k]
        return k
    for _, g in d[d.evento_sat.notna() & (d.evento_sat.astype(str) != "")].groupby("evento_sat"):
        ks = g.k.unique()
        for k in ks[1:]:
            padre[raiz(k)] = raiz(ks[0])
    d["inc"] = d.k.map(raiz)
    filas = []
    for inc, g in d.groupby("inc"):
        est = g.sort_values("fecha_reporte")
        cont = est[est.estado.astype(str).str.contains("Conten|Control", case=False, na=False)]
        filas.append(dict(
            inc=inc, nombre=" / ".join(sorted(g.nombre.astype(str).unique())), fecha_inicio=g.fecha_inicio.min(),
            fecha_extincion=g.fecha_extincion.dropna().max() if g.fecha_extincion.notna().any() else None,
            fecha_contencion=cont.fecha_reporte.min() if len(cont) else None, n_partes=len(g),
            ha_smf=g.ha_smf.max(), ha_sat=g.superficie_ha_sat.max(), evento_sat=";".join(sorted(g.evento_sat.dropna().astype(str).unique())),
            puntos=sorted({(round(a, 6), round(b, 6)) for a, b in zip(g.longitud_dec, g.latitud_dec)})))
    return pd.DataFrame(filas)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--raiz", default=None, help="carpeta V.4 (por defecto, la de este código)")
    ap.add_argument("--salida", required=True)
    a = ap.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rutas import Rutas
    RT = Rutas(a.raiz); R = RT.raiz
    try:
        CP = RT.conjunto_pruebas
    except FileNotFoundError as e:
        raise SystemExit(f"{e}: la lista nominal no se puede regenerar aquí (usar la congelada en {RT.protocolo})")
    OUT = R / a.salida
    OUT.mkdir(parents=True, exist_ok=True)
    entradas = {
        "mascara": RT.mascara_dominio,
        "fuego_mensual": RT.fuego_mensual,
        "poligonos_mapbiomas": RT.poligonos_mapbiomas,
        "viirs_firms": RT.firms_viirs,
        "snmf": RT.snmf,
    }
    with rasterio.open(entradas["mascara"]) as r:
        mask = r.read(1) == 1
        T, shp, crs = r.transform, r.shape, r.crs
    with rasterio.open(entradas["fuego_mensual"]) as r:
        assert r.transform == T and r.shape == shp
        mens = {2022 + i: r.read(i + 1) for i in range(r.count)}
    dist_borde = ndimage.distance_transform_edt(mask) * 30.0
    dom = unary_union([shape(g) for g, v in shapes(mask.astype("uint8"), mask=mask, transform=T) if v == 1])
    xmin, ymin, xmax, ymax = dom.bounds

    pol = gpd.read_file(entradas["poligonos_mapbiomas"]).to_crs(crs)
    pol = pol[pol.intersects(dom)].copy()
    pol["frac_en_dominio"] = pol.geometry.intersection(dom).area / pol.geometry.area
    pol["ha_total_5345"] = pol.geometry.area / 1e4

    # focos VIIRS S-NPP (FIRMS), type 0, cerca del dominio
    v = pd.read_csv(entradas["viirs_firms"], encoding="utf-8-sig")
    v = v[v["type"] == 0].copy()
    v["t"] = pd.to_datetime(v.acq_date + " " + v.acq_time.astype(int).astype(str).str.zfill(4), format="%Y-%m-%d %H%M", utc=True)
    vg = gpd.GeoDataFrame(v, geometry=gpd.points_from_xy(v.longitude, v.latitude), crs=4326).to_crs(crs)
    vg = vg[(vg.geometry.x > xmin - 3000) & (vg.geometry.x < xmax + 3000) & (vg.geometry.y > ymin - 3000) & (vg.geometry.y < ymax + 3000)].copy()
    vg["fila"] = ((T.f - vg.geometry.y) / 30.0).astype(int)
    vg["col"] = ((vg.geometry.x - T.c) / 30.0).astype(int)
    vg = vg.reset_index(drop=True)
    vg["id_foco"] = np.arange(len(vg))

    inc = incidentes_snmf(entradas["snmf"])
    inc_pts = [(i, gpd.points_from_xy([p[0]], [p[1]], crs=4326).to_crs(crs)[0]) for i, row in inc.iterrows() for p in row.puntos]

    comps = []
    for _, p in pol.iterrows():
        y = int(p.calendar_year)
        if y not in mens:
            continue
        m_pol = rasterize([(p.geometry, 1)], out_shape=shp, transform=T, dtype="uint8").astype(bool) & mask
        meses = mens[y][m_pol]
        for mes in sorted(set(meses[(meses > 0) & (meses < 13)].tolist())):
            cm = m_pol & (mens[y] == mes)
            comps.append(dict(oid=p.oid, anio=y, meses=[mes], mask=cm, ha=cm.sum() * HA_CELDA,
                              frac_pol=float(p.frac_en_dominio), ha_pol=float(p.ha_total_5345)))

    def atribuir(c):
        """Focos a <= 1 km del componente en la ventana del/los mes(es) (§4.1); devuelve el grupo con más focos."""
        cm = c["mask"]
        rr, cc = np.nonzero(cm)
        r0, r1, c0, c1 = max(rr.min() - 40, 0), min(rr.max() + 41, shp[0]), max(cc.min() - 40, 0), min(cc.max() + 41, shp[1])
        dt = ndimage.distance_transform_edt(~cm[r0:r1, c0:c1]) * 30.0
        ini = pd.Timestamp(year=c["anio"], month=min(c["meses"]), day=1, tz="UTC") - timedelta(days=10)
        fin = pd.Timestamp(year=c["anio"], month=max(c["meses"]), day=1, tz="UTC") + pd.offsets.MonthEnd(0) + timedelta(days=4)
        cand = vg[(vg.t >= ini) & (vg.t < fin) & (vg.fila >= r0) & (vg.fila < r1) & (vg.col >= c0) & (vg.col < c1)]
        if len(cand):
            d = dt[cand.fila.values - r0, cand.col.values - c0]
            cand = cand[d <= BUFFER_FOCOS_M]
        if not len(cand):
            return cand, (r0, r1, c0, c1, dt)
        cand = cand.sort_values("t")
        grupo = (cand.t.diff() > timedelta(days=HUECO_GRUPO_DIAS)).cumsum()
        mejor = grupo.value_counts().idxmax()
        return cand[grupo == mejor], (r0, r1, c0, c1, dt)

    for c in comps:
        c["focos"], c["_ventana"] = atribuir(c)
    # unión de componentes del mismo polígono que comparten grupo de focos (§3.2)
    unidos = True
    while unidos:
        unidos = False
        for i in range(len(comps)):
            for j in range(i + 1, len(comps)):
                a_, b_ = comps[i], comps[j]
                if a_["oid"] == b_["oid"] and len(a_["focos"]) and len(b_["focos"]) and set(a_["focos"].id_foco) & set(b_["focos"].id_foco):
                    a_["mask"] = a_["mask"] | b_["mask"]
                    a_["meses"] = sorted(a_["meses"] + b_["meses"])
                    a_["ha"] = a_["mask"].sum() * HA_CELDA
                    a_["focos"], a_["_ventana"] = atribuir(a_)
                    comps.pop(j)
                    unidos = True
                    break
            if unidos:
                break

    # SM01 (visto por SIM): cicatriz COE del caso
    sm01 = gpd.read_file(CP / "casos/SM01_2023_LAS_LAGUNAS_Y_LA_AGUADA/perimetro_final.geojson").to_crs(crs)
    sm01_m = rasterize([(g, 1) for g in sm01.geometry], out_shape=shp, transform=T, dtype="uint8").astype(bool)

    filas, focos_out = [], []
    for c in comps:
        cm = c["mask"]
        ide = f"MB_{c['oid']}_{c['anio']}-" + "-".join(f"{m:02d}" for m in c["meses"])
        r0, r1, c0, c1, dt = c["_ventana"]
        ini = pd.Timestamp(year=c["anio"], month=min(c["meses"]), day=1) - timedelta(days=10)
        fin = pd.Timestamp(year=c["anio"], month=max(c["meses"]), day=1) + pd.offsets.MonthEnd(0) + timedelta(days=3)
        # parte SNMF (regla CP D12: punto <= 2 km, fecha en ventana, cociente en [0,5; 2] si hay dato)
        parte = None
        for i, pt in inc_pts:
            fila_, col_ = int((T.f - pt.y) / 30), int((pt.x - T.c) / 30)
            if not (r0 <= fila_ < r1 and c0 <= col_ < c1):
                continue
            if dt[fila_ - r0, col_ - c0] > DIST_PARTE_M:
                continue
            fi = pd.Timestamp(inc.loc[i, "fecha_inicio"])
            if not (ini <= fi <= fin):
                continue
            ref_ha = inc.loc[i, "ha_smf"] if pd.notna(inc.loc[i, "ha_smf"]) else inc.loc[i, "ha_sat"]
            ratio = c["ha"] / ref_ha if pd.notna(ref_ha) and ref_ha > 0 else np.nan
            if pd.notna(ratio) and not (0.5 <= ratio <= 2.0):
                continue
            d = float(dt[fila_ - r0, col_ - c0])
            if parte is None or d < parte["dist_m"]:
                parte = dict(i=i, dist_m=d, ratio=ratio, lon=pt.x, lat=pt.y)
        f = c["focos"]
        n_f = len(f)
        pases = f.groupby("t").size().sort_index() if n_f else pd.Series(dtype=int)
        t80 = t100 = None
        if n_f:
            acum = pases.cumsum() / n_f
            t80 = acum[acum >= 0.8].index[0] if n_f >= MIN_FOCOS_T80 else None
            t100 = pases.index[-1]
        ip = inc.loc[parte["i"]] if parte else None
        cont = pd.Timestamp(ip.fecha_contencion) + timedelta(hours=27) if parte and _ok(ip.fecha_contencion) else None  # fin del día local (24 h + 3 h UTC)
        if t80 is None and parte is not None:
            base = ip.fecha_contencion if _ok(ip.fecha_contencion) else (ip.fecha_extincion if _ok(ip.fecha_extincion) else None)
            t80 = pd.Timestamp(base, tz="UTC") + timedelta(hours=27) if base else None
            t80_fuente = "SNMF contención" if _ok(ip.fecha_contencion) else ("SNMF fin" if base else None)
        else:
            t80_fuente = "focos (80 %)" if t80 is not None else None
        if t100 is not None and cont is not None:
            t100_ref = min(t100, pd.Timestamp(cont, tz="UTC")); t100_fuente = "min(T100 focos, contención SNMF)"
        elif t100 is not None:
            t100_ref, t100_fuente = t100, "último pase con focos"
        elif cont is not None:
            t100_ref, t100_fuente = pd.Timestamp(cont, tz="UTC"), "contención SNMF"
        else:
            t100_ref, t100_fuente = None, None
        crit1_tam = c["ha"] >= UMBRAL_HA
        crit1_dentro = c["frac_pol"] >= FRAC_DENTRO_MIN
        dmin = float(dist_borde[cm].min()) if cm.any() else 0.0
        crit1_borde = dmin >= DIST_BORDE_MIN_M
        crit2 = n_f > 0 or parte is not None
        ign_fuente = "primer pase VIIRS" if n_f else ("punto SNMF" if parte else None)
        crit3 = ign_fuente is not None
        instante_ok = t80 is not None
        visto = VISTOS.get((c["oid"], c["anio"], min(c["meses"])))
        if visto is None and (cm & sm01_m).any() and c["anio"] == 2023:
            visto = "SIM (SM01)"
        motivos = []
        if not crit1_tam: motivos.append(f"componente < {UMBRAL_HA:.0f} ha")
        if not crit1_dentro: motivos.append(f"polígono {c['frac_pol']*100:.0f} % dentro del dominio (< 95 %)")
        if not crit1_borde: motivos.append(f"a {dmin/1000:.1f} km del borde (< 3 km)")
        if not crit2: motivos.append("sin parte SNMF ni focos VIIRS atribuibles")
        if crit2 and not instante_ok: motivos.append("T80 indeterminado (< 20 focos y sin parte SNMF)")
        elegible = crit1_tam and crit1_dentro and crit1_borde and crit2 and crit3 and instante_ok
        rol = ("desarrollo" if visto else "prueba_fase1") if elegible else "descartado"
        if visto and not elegible:
            rol = "desarrollo (no cumple §3.2)"
        primer = pases.index[0] if n_f else None
        mes_ini = min(c["meses"])
        filas.append(dict(
            id_evento=ide, oid=c["oid"], anio=c["anio"], meses="-".join(map(str, c["meses"])), ha_componente=round(c["ha"], 1),
            ha_poligono=round(c["ha_pol"], 1), frac_poligono_en_dominio=round(c["frac_pol"], 3), dist_borde_km=round(dmin / 1000, 2),
            n_focos_viirs=n_f, n_pases=len(pases), primer_pase_utc=str(primer) if primer is not None else "",
            ultimo_pase_utc=str(t100) if t100 is not None else "",
            parte_snmf=ip.nombre if parte else "", parte_fecha_inicio=ip.fecha_inicio if parte else "",
            parte_contencion=ip.fecha_contencion if parte else "", parte_extincion=ip.fecha_extincion if parte else "",
            parte_dist_m=round(parte["dist_m"]) if parte else "", parte_ratio=round(parte["ratio"], 2) if parte and pd.notna(parte["ratio"]) else "",
            ignicion=ign_fuente or "", T80_utc=str(t80) if t80 is not None else "", T80_fuente=t80_fuente or "",
            Tref_dt_utc=str(t100_ref) if t100_ref is not None else "", Tref_dt_fuente=t100_fuente or "",
            estrato_tamano="100-500" if c["ha"] < 500 else ("500-2000" if c["ha"] < 2000 else ">2000"),
            estrato_estacion="temporada (ago-nov)" if 8 <= mes_ini <= 11 else "fuera de temporada (dic-jul)",
            crit1=crit1_tam and crit1_dentro and crit1_borde, crit2=crit2, crit3=crit3, visto_por=visto or "",
            rol=rol, motivo_descarte="; ".join(motivos), orden=orden(ide)))
        if n_f:
            ff = f[["id_foco", "latitude", "longitude", "acq_date", "acq_time", "satellite", "confidence", "frp", "daynight"]].copy()
            ff.insert(0, "id_evento", ide)
            focos_out.append(ff)
    df = pd.DataFrame(filas).sort_values(["rol", "orden"])
    df.to_csv(OUT / "eventos_fase1.csv", index=False, encoding="utf-8")
    (pd.concat(focos_out) if focos_out else pd.DataFrame()).to_csv(OUT / "focos_atribuidos.csv", index=False, encoding="utf-8")

    # conciliación con CP/
    conc = []
    idx = pd.read_csv(CP / "indice_casos.csv")
    comp_masks = {f"MB_{c['oid']}_{c['anio']}-" + "-".join(f"{m:02d}" for m in c["meses"]): c["mask"] for c in comps}
    for _, k in idx.iterrows():
        per = gpd.read_file(CP / k.ruta_caso / "perimetro_final.geojson").to_crs(crs)
        ha_tot = per.geometry.area.sum() / 1e4
        pm = rasterize([(g, 1) for g in per.geometry], out_shape=shp, transform=T, dtype="uint8").astype(bool)
        ha_dentro = (pm & mask).sum() * HA_CELDA
        sol = []
        for ide, cm in comp_masks.items():
            inter = (pm & cm).sum()
            if inter and int(ide.split("_")[-1][:4]) == int(k.anio):
                sol.append(f"{ide} ({inter * HA_CELDA:.0f} ha comunes)")
        fila_ev = df[df.id_evento.isin([s.split(" ")[0] for s in sol])]
        conc.append(dict(case_id=k.case_id, anio=k.anio, ha_cicatriz_coe=round(ha_tot, 1), ha_en_dominio=round(ha_dentro, 1),
                         frac_en_dominio=round(ha_dentro / ha_tot, 3) if ha_tot else 0, rol_cp=k.rol, componentes_mapbiomas=" | ".join(sol),
                         rol_protocolo=" | ".join(fila_ev.rol.unique()) if len(fila_ev) else "sin componente MapBiomas"))
    pd.DataFrame(conc).to_csv(OUT / "conciliacion_cp.csv", index=False, encoding="utf-8")

    resumen = dict(
        protocolo="v1.0", semilla=SEMILLA, n_componentes=len(df),
        n_por_rol=df.rol.value_counts().to_dict(),
        entradas={k: sha(p) for k, p in entradas.items()},
        salidas={n: sha(OUT / n) for n in ["eventos_fase1.csv", "focos_atribuidos.csv", "conciliacion_cp.csv"]},
        script_sha256=sha(Path(__file__)))
    (OUT / "resumen_fase1.json").write_text(json.dumps(resumen, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resumen, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
