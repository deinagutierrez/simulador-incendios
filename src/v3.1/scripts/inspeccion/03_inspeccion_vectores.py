import geopandas as gpd, pandas as pd, glob, os, warnings
warnings.filterwarnings("ignore")
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.max_colwidth", 60)
ROOT = r"C:\Users\lisan\OneDrive\Documentos\Proyectos\Datos_SL_Completo"
aoi = gpd.read_file(ROOT + r"\primero_cuadrado.geojson")
dom = aoi[aoi["tipo"]=="dominio_exacto_25_celdas"].geometry.iloc[0]
dom5345 = gpd.GeoSeries([dom], crs=4326).to_crs(5345).iloc[0]

def info(path, layer=None):
    import pyogrio
    print("="*110); print(os.path.relpath(path, ROOT), layer or "", f"{os.path.getsize(path)/1e6:.1f} MB")
    try:
        print(" layers:", pyogrio.list_layers(path).tolist())
    except Exception as e: print(" list_layers err", e)
    g = gpd.read_file(path, layer=layer)
    print(" crs:", g.crs, "| n:", len(g), "| geom types:", g.geom_type.value_counts().to_dict())
    print(" bounds:", g.total_bounds)
    print(" valid:", g.is_valid.value_counts().to_dict(), "| empty:", int(g.is_empty.sum()))
    print(" columns:", list(g.columns))
    print(g.drop(columns="geometry").head(3).to_string())
    return g

# --- fire polygons
fire = info(ROOT + r"\Fuego_MapBiomas\Coleccion_1\incendios_mapbiomas_fuego_sanluis.gpkg")
print(fire.drop(columns="geometry").describe(include="all").T.to_string())
for c in fire.columns:
    if c!="geometry" and fire[c].nunique()<30: print("  ", c, "->", fire[c].value_counts(dropna=False).to_dict())
inter = fire[fire.intersects(dom)].copy()
inter5 = inter.to_crs(5345)
inter["area_total_ha"] = inter5.area/1e4
inter["area_in_aoi_ha"] = inter5.intersection(dom5345).area/1e4
inter["frac_in_aoi"] = inter["area_in_aoi_ha"]/inter["area_total_ha"]
print("\n### fire polygons intersecting AOI:", len(inter))
cols = [c for c in inter.columns if c!="geometry"]
print(inter.sort_values("area_in_aoi_ha", ascending=False)[cols].head(40).to_string())
inter.drop(columns="geometry").to_csv(os.environ["SCR"]+"/fire_polys_in_aoi.csv", index=False)
# yearly gpkgs: compare
for y in [2022,2023,2024,2025]:
    p = ROOT + rf"\Fuego_MapBiomas\Coleccion_1\incendios_mapbiomas_fuego_sanluis_{y}.gpkg"
    import pyogrio
    gy = gpd.read_file(p)
    print(f" yearly {y}: n={len(gy)} cols={list(gy.columns)}")

# --- other vectors
for p in [ROOT+r"\caminos_sanluis_integrado.geojson", ROOT+r"\viviendas_sanluis_integrado.geojson", ROOT+r"\departamentos_san_luis_ign_conae.geojson"] + sorted(glob.glob(ROOT+r"\Electricidad\*.geojson")):
    g = info(p)
    n_in = int(g.intersects(dom).sum())
    print(f" >>> intersect AOI: {n_in}")
    for c in g.columns:
        if c!="geometry" and g[c].nunique()<25: print("  ", c, "->", g[c].value_counts(dropna=False).head(25).to_dict())
    if "caminos" in p:
        gi = g[g.intersects(dom)].to_crs(5345)
        print("  length km in AOI by tipo:", (gi.intersection(dom5345).length/1e3).groupby(gi[[c for c in gi.columns if 'tipo' in c.lower() or 'highway' in c.lower()][0]]).sum().round(1).to_dict() if any('tipo' in c.lower() or 'highway' in c.lower() for c in gi.columns) else (gi.length.sum()/1e3))
