"""Build a PMTiles archive from BikeNEAT classification output.

Reads the GeoParquet written by run_bikeneat.py and tiles it with freestiler.

Two things happen here beyond plain tiling:

1. The classification category is split into `infra_left` and `infra_right`, so
   the map can draw each side of the street as its own offset line. BikeNEAT
   encodes the side in the category name ('bicycle_way_right_lane_left' is a way
   on the right and a lane on the left); resolving that here keeps the parsing
   testable instead of pushing it into MapLibre filter expressions.

2. The output holds two layers, because ~88 % of classified ways carry no
   cycling infrastructure and would otherwise dominate the archive:

     bikeneat  the classified infrastructure, full attributes, from --min-zoom
     context   the remaining road network, geometry plus highway only,
               coalesced, from --context-min-zoom

   For Berlin that is ~16 MB instead of 55.7 MB for a flat single-layer archive.
   The saving comes from the attributes, not the geometry: 'id', 'name' and
   'length' are unique per feature, so they cannot be coalesced and cost roughly
   38 MB across the 190k context ways that do not need them.
"""

import argparse
import json
import time
from pathlib import Path

import geopandas as gpd
from freestiler import FreestileLayer, freestile, freestile_layer

NO_INFRA = "no"
BICYCLE_ROAD = "bicycle_road"

# Kept in sync with STANDALONE_HIGHWAYS in config.js, which decides where the map
# draws one centred line instead of an offset pair.
STANDALONE_HIGHWAYS = ["cycleway", "path", "track", "pedestrian"]

# Category grammar: '<primary>_both' or '<primary>_<side>_<secondary>_<side>'.
# The primary type is always the higher-grade one, which is why grouping by
# prefix is meaningful elsewhere.
PRIMARY_TYPES = ["bicycle_way", "bicycle_lane", "shared_way", "bus_lane"]
SECONDARY_TOKENS = {
    "no": None,
    "lane": "bicycle_lane",
    "shared": "shared_way",
    "bus": "bus_lane",
    "way": "bicycle_way",
}


def split_sides(category):
    """Return (left, right) infrastructure type for a BikeNEAT category.

    Either side may be None, meaning nothing on that side. Raises ValueError on
    a category that does not fit the grammar, so an unrecognised value fails the
    build instead of silently disappearing from the map.
    """
    if category == NO_INFRA:
        return None, None
    # A Fahrradstraße applies to the whole carriageway, not to one side.
    if category == BICYCLE_ROAD:
        return BICYCLE_ROAD, BICYCLE_ROAD

    for primary in PRIMARY_TYPES:
        if not category.startswith(primary + "_"):
            continue
        rest = category[len(primary) + 1:]
        if rest == "both":
            return primary, primary

        parts = rest.split("_")
        primary_side, secondary_side = parts[0], parts[-1]
        secondary_token = "_".join(parts[1:-1])
        if (
            primary_side not in ("left", "right")
            or secondary_side not in ("left", "right")
            or primary_side == secondary_side
            or secondary_token not in SECONDARY_TOKENS
        ):
            break
        sides = {primary_side: primary, secondary_side: SECONDARY_TOKENS[secondary_token]}
        return sides["left"], sides["right"]

    raise ValueError(f"unrecognised BikeNEAT category: {category!r}")


def write_category_index(infra, out_path):
    """Write which bicycle_infrastructure values feed each legend colour.

    The map groups 23 category values into five colours by looking at
    infra_left / infra_right, so a single category can feed two colours — a
    'bicycle_way_right_lane_left' contributes to both the way and the lane
    colour. Deriving the mapping from the tiled data keeps the legend honest for
    whatever extract was built, and carries the real counts with it.
    """
    counts = infra["bicycle_infrastructure"].value_counts()
    groups: dict[str, list[dict]] = {}

    for category, count in counts.items():
        left, right = split_sides(category)
        for group in {left, right} - {None}:
            if left == right:
                side = "beidseitig" if left != BICYCLE_ROAD else "ganze Fahrbahn"
            else:
                side = "links" if left == group else "rechts"
            groups.setdefault(group, []).append(
                {"name": category, "count": int(count), "side": side}
            )

    payload = {
        "source": Path(out_path).name,
        "groups": {
            group: {
                "total": sum(e["count"] for e in entries),
                "categories": sorted(entries, key=lambda e: -e["count"]),
            }
            for group, entries in groups.items()
        },
    }

    sidecar = Path(out_path).with_suffix("").with_suffix(".categories.json")
    sidecar.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return sidecar


INFRA_COLUMNS = [
    "id",                       # OSM way id, for linking back to osm.org
    "bicycle_infrastructure",   # the precise category, shown in the popup
    "infra_left",               # derived: what is on the left, or absent
    "infra_right",              # derived: what is on the right, or absent
    "highway",
    "name",
    "length",
]

# The context layer only needs enough to draw and style a road casing.
CONTEXT_COLUMNS = ["highway"]


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
    infra = gdf[gdf["bicycle_infrastructure"] != NO_INFRA].copy()

    sides = {c: split_sides(c) for c in infra["bicycle_infrastructure"].unique()}
    infra["infra_left"] = infra["bicycle_infrastructure"].map(lambda c: sides[c][0])
    infra["infra_right"] = infra["bicycle_infrastructure"].map(lambda c: sides[c][1])

    # The map draws a standalone cycleway or path as one centred line instead of an
    # offset pair, which only holds while both sides agree. Warn rather than fail,
    # since the drawing still shows the way, just not the asymmetry.
    standalone = infra[infra["highway"].isin(STANDALONE_HIGHWAYS)]
    asymmetric = standalone[standalone["infra_left"] != standalone["infra_right"]]
    if len(asymmetric):
        counts = asymmetric["bicycle_infrastructure"].value_counts().to_dict()
        print(f"warning: {len(asymmetric)} standalone ways have differing sides "
              f"and will be drawn as a single line: {counts}")

    def subset(frame, columns):
        keep = [c for c in columns if c in frame.columns]
        return frame[keep + [geom]]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    infra = subset(infra, INFRA_COLUMNS)
    layers: dict[str, gpd.GeoDataFrame | FreestileLayer] = {
        "bikeneat": freestile_layer(infra, min_zoom=args.min_zoom),
    }
    print(f"bikeneat: {len(infra)} features, {len(infra.columns) - 1} attributes")
    print(f"          left  {infra['infra_left'].notna().sum()},"
          f" right {infra['infra_right'].notna().sum()}")

    if not args.no_context:
        context = subset(gdf[gdf["bicycle_infrastructure"] == NO_INFRA], CONTEXT_COLUMNS)
        layers["context"] = freestile_layer(context, min_zoom=args.context_min_zoom)
        print(f"context : {len(context)} features, {len(context.columns) - 1} attributes"
              f" (from zoom {args.context_min_zoom})")

    sidecar = write_category_index(infra, out)

    t0 = time.perf_counter()
    freestile(layers, out, min_zoom=args.min_zoom, max_zoom=args.max_zoom,
              coalesce=True, quiet=True)
    tile_s = time.perf_counter() - t0

    print(f"index  {sidecar.name}")

    print(f"\nread   {read_s:6.2f}s")
    print(f"tile   {tile_s:6.2f}s")
    print(f"size   {out.stat().st_size / 1e6:6.1f} MB  ->  {out}")


if __name__ == "__main__":
    main()
