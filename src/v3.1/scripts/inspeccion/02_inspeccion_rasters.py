import rasterio, numpy as np, json, glob, os
from rasterio.mask import mask
import geopandas as gpd
from rasterio.warp import transform_bounds
ROOT = r"C:\Users\lisan\OneDrive\Documentos\Proyectos\Datos_SL_Completo"
aoi = gpd.read_file(ROOT + r"\primero_cuadrado.geojson")
dom = aoi[aoi["tipo"]=="dominio_exacto_25_celdas"].geometry.iloc[0]
files = [ROOT+r"\Topografia\MDT_ASTER GDEM.tif"] + sorted(glob.glob(ROOT+r"\Uso_Cobertura_Suelo\Coleccion_3\*.tif")) + sorted(glob.glob(ROOT+r"\Fuego_MapBiomas\Coleccion_1\*.tif"))
for f in files:
    with rasterio.open(f) as ds:
        print("="*100); print(os.path.basename(f), f"{os.path.getsize(f)/1e6:.1f} MB")
        print(" driver", ds.driver, "| crs", ds.crs, "| size", ds.width, "x", ds.height, "| bands", ds.count, "| dtype", ds.dtypes, "| nodata", ds.nodata)
        print(" res", ds.res, "| transform", tuple(round(v,8) for v in ds.transform[:6]))
        print(" bounds", ds.bounds)
        if ds.crs and ds.crs.to_epsg()!=4326:
            print(" bounds wgs84", transform_bounds(ds.crs,"EPSG:4326",*ds.bounds))
        print(" overviews b1", ds.overviews(1), "| tiled", ds.profile.get("tiled"), "| blocks", ds.block_shapes[0], "| compress", ds.profile.get("compress"))
        print(" tags", {k:v for k,v in ds.tags().items() if len(str(v))<200})
        print(" descriptions", ds.descriptions)
        # clip to AOI
        g = gpd.GeoSeries([dom], crs="EPSG:4326").to_crs(ds.crs)
        try:
            arr, tr = mask(ds, [g.iloc[0].__geo_interface__], crop=True, all_touched=False, nodata=ds.nodata)
        except Exception as e:
            print(" clip error", e); continue
        print(" clipped shape", arr.shape)
        for b in range(arr.shape[0]):
            a = arr[b]
            nd = ds.nodata
            valid = a if nd is None else a[a!=nd]
            if a.dtype.kind=='f':
                valid = valid[np.isfinite(valid)]
            if valid.size==0: print(f"  band {b+1}: no valid"); continue
            if ds.count==1 and a.dtype.kind=='f' or 'GDEM' in f:
                print(f"  band {b+1}: n_valid={valid.size:,} n_nodata={a.size-valid.size:,} min={valid.min():.2f} max={valid.max():.2f} mean={valid.mean():.2f}")
            else:
                u,c = np.unique(valid, return_counts=True)
                tot = valid.size
                print(f"  band {b+1}: n_px={tot:,} uniques=", {int(k):f"{int(v):,} ({100*v/tot:.1f}%)" for k,v in zip(u,c)})
