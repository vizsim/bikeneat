"""Build a PMTiles archive from BikeNEAT classification output.

Reads the GeoParquet written by run_bikeneat.py and tiles it with freestiler.

The output holds two layers, because ~88 % of classified ways carry no cycling
infrastructure and would otherwise dominate the archive:

  bikeneat  the classified infrastructure, full attributes, from --min-zoom
  context   the remaining road network, geometry plus highway only, coalesced,
            from --context-min-zoom

For Berlin that is 17.8 MB instead of 55.7 MB for a flat single-layer archive.
The saving comes from the attributes, not the geometry: 'id', 'name' and
'length' are unique per feature, so they cannot be coalesced and cost roughly
38 MB across the 190k context ways that do not need them.
"""

import argparse
import time
from pathlib import Path

import geopandas as gpd
from freestiler import FreestileLayer, freestile, freestile_layer

# Carried into the infrastructure layer. Everything else in the classification
# output (raw OSM tag columns, the 'tags' JSON blob, timestamp, version) is
# dropped — it would bloat the tiles for no benefit on the map.
INFRA_COLUMNS = [
    "id",                       # OSM way id, for linking back to osm.org
    "bicycle_infrastructure",   # the classification itself
    "highway",
    "name",
    "length",
]

# The context layer only needs enough to draw and style a road casing.
CONTEXT_COLUMNS = ["highway"]

NO_INFRA = "no"


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("parquet", help="GeoParquet from run_bikeneat.py")
    parser.add_argument("-o", "--out", required=True, help="output .pmtiles path")
    parser.add_argument("--min-zoom", type=int, default=8)
    parser.add_argument("--max-zoom", type=int, default=14)
    parser.add_argument("--context-min-zoom", type=int, default=11,
                        help="zoom at which the unclassified road network appears")
    parser.add_argument("--no-context", action="store_true",
                        help="omit the context layer entirely (smallest output)")
    parser.add_argument("--flat", action="store_true",
                        help="one layer with all features and all attributes")
    args = parser.parse_args()

    t0 = time.perf_counter()
    gdf = gpd.read_parquet(args.parquet)
    read_s = time.perf_counter() - t0

    # Ways present only in the driving network come out of the classification
    # with no geometry at all: the outer merge keeps the cycling-side geometry
    # column and drops the driving-side one. They carry an id and nothing else,
    # and are always classified 'no'.
    no_geom = gdf.geometry.isna() | gdf.geometry.is_empty
    if no_geom.any():
        print(f"dropping {int(no_geom.sum())} features without geometry")
        gdf = gdf[~no_geom]

    geom = gdf.geometry.name

    def subset(frame, columns):
        keep = [c for c in columns if c in frame.columns]
        return frame[keep + [geom]]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    layers: gpd.GeoDataFrame | dict[str, gpd.GeoDataFrame | FreestileLayer]
    if args.flat:
        layers = subset(gdf, [c for c in gdf.columns if c != geom])
        print(f"flat: {len(gdf)} features, {len(gdf.columns) - 1} attributes")
    else:
        infra = subset(gdf[gdf["bicycle_infrastructure"] != NO_INFRA], INFRA_COLUMNS)
        layers = {"bikeneat": freestile_layer(infra, min_zoom=args.min_zoom)}
        print(f"bikeneat: {len(infra)} features, {len(infra.columns) - 1} attributes")

        if not args.no_context:
            context = subset(gdf[gdf["bicycle_infrastructure"] == NO_INFRA], CONTEXT_COLUMNS)
            layers["context"] = freestile_layer(context, min_zoom=args.context_min_zoom)
            print(f"context : {len(context)} features, {len(context.columns) - 1} attributes"
                  f" (from zoom {args.context_min_zoom})")

    t0 = time.perf_counter()
    freestile(
        layers,
        out,
        layer_name="bikeneat" if args.flat else None,
        min_zoom=args.min_zoom,
        max_zoom=args.max_zoom,
        coalesce=not args.flat,
        quiet=True,
    )
    tile_s = time.perf_counter() - t0

    print(f"\nread   {read_s:6.2f}s")
    print(f"tile   {tile_s:6.2f}s")
    print(f"size   {out.stat().st_size / 1e6:6.1f} MB  ->  {out}")


if __name__ == "__main__":
    main()
