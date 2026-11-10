import json, math
import geopandas as gpd
from shapely.geometry import shape
from shapely.validation import explain_validity
from pyproj import CRS, Transformer

ROOT = r"C:\Users\lisan\OneDrive\Documentos\Proyectos\Datos_SL_Completo"
p = ROOT + r"\primero_cuadrado.geojson"
raw = json.load(open(p, encoding="utf-8"))
print("type:", raw.get("type"), "| crs member:", raw.get("crs"), "| n features:", len(raw.get("features", [])))
for i, f in enumerate(raw["features"]):
    g = shape(f["geometry"])
    print(f"feature {i}: geom={g.geom_type} valid={g.is_valid} ({explain_validity(g)}) props={f.get('properties')}")
    print("  n coords:", len(g.exterior.coords) if g.geom_type=="Polygon" else "-")
    print("  bounds (lon/lat):", g.bounds)
    print("  coords:", list(g.exterior.coords)[:6] if g.geom_type=="Polygon" else "-")

gdf = gpd.read_file(p)
print("gpd CRS:", gdf.crs)
g = gdf.geometry.iloc[0]
cx, cy = g.centroid.x, g.centroid.y
print("centroid lon/lat:", cx, cy)
# candidate projected CRSs
cands = {
 "EPSG:5345 POSGAR2007 faja 3":"EPSG:5345",
 "EPSG:5344 POSGAR2007 faja 2":"EPSG:5344",
 "EPSG:32719 UTM19S":"EPSG:32719",
 "EPSG:32720 UTM20S":"EPSG:32720",
 "ESRI:102033 SA Albers":"ESRI:102033",
 "EPSG:3857 WebMerc":"EPSG:3857",
}
for name, code in cands.items():
    gp = gdf.to_crs(code).geometry.iloc[0]
    minx,miny,maxx,maxy = gp.bounds
    print(f"{name:32s} area={gp.area/1e6:10.2f} km2  bbox W={maxx-minx:9.1f} m  H={maxy-miny:9.1f} m  perim={gp.length/1e3:8.2f} km  bboxarea={(maxx-minx)*(maxy-miny)/1e6:9.2f}")
# geodesic area
from pyproj import Geod
geod = Geod(ellps="WGS84")
a, per = geod.geometry_area_perimeter(g)
print(f"geodesic area = {abs(a)/1e6:.2f} km2, perimeter={per/1e3:.2f} km")
# edge lengths geodesic
coords = list(g.exterior.coords)
for i in range(len(coords)-1):
    (x1,y1),(x2,y2) = coords[i], coords[i+1]
    _,_,d = geod.inv(x1,y1,x2,y2)
    print(f" edge {i}: {d/1e3:.3f} km  from {coords[i]} to {coords[i+1]}")
# cells at 30 m in POSGAR faja 3
gp = gdf.to_crs("EPSG:5345").geometry.iloc[0]
minx,miny,maxx,maxy = gp.bounds
ncols = math.ceil((maxx-minx)/30); nrows = math.ceil((maxy-miny)/30)
print(f"EPSG:5345 grid 30m: cols={ncols} rows={nrows} total={ncols*nrows:,} ; polygon-area cells={gp.area/900:,.0f}")
print("EPSG:5345 bounds:", gp.bounds)
# convergence/ scale factor at centroid for faja 3 (central meridian -66)
print("Lon offset from -66 central meridian:", cx+66)
