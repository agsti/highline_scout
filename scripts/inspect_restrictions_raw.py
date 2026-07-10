"""Print columns, CRS, and candidate type/name fields of the raw MITECO files.

Throwaway helper used once to discover the attribute schema the LAYERS registry
depends on. Safe to delete after the constants are recorded in the plan.
"""
import glob
import geopandas as gpd

for pattern in ("data/restrictions/raw/*.gml", "data/restrictions/raw/*.geojson",
                "data/restrictions/raw/*.json"):
    for path in glob.glob(pattern):
        gdf = gpd.read_file(path, rows=50)
        print(f"\n=== {path} ===")
        print("CRS:", gdf.crs)
        print("columns:", list(gdf.columns))
        for col in gdf.columns:
            if col == "geometry":
                continue
            if gdf[col].dtype != object and str(gdf[col].dtype) != "str":
                continue
            try:
                vals = gdf[col].dropna().unique()[:8]
            except TypeError:
                # Some GML fields (e.g. repeated INSPIRE sub-elements) come
                # back as array-valued cells, which pandas can't hash for
                # unique(); stringify first so we can still see the shape.
                vals = gdf[col].dropna().apply(
                    lambda v: tuple(v) if hasattr(v, "__iter__") and not isinstance(v, str) else v
                ).unique()[:8]
            print(f"  {col!r} sample: {list(vals)}")
