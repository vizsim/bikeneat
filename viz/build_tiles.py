"""Build a PMTiles archive from BikeNEAT classification output.

Reads the GeoParquet written by run_bikeneat.py and tiles it with freestiler.

Two things happen here beyond plain tiling:

1. The classification category is split into `infra_left` and `infra_right`, so
   the map can draw each side of the street as its own offset line. BikeNEAT
   encodes the side in the category name ('bicycle_way_right_lane_left' is a way
   on the right and a lane on the left); resolving that here keeps the parsing
   testable instead of pushing it into MapLibre filter expressions.

2. Ways classified 'no' are dropped. They are ~88 % of the classified network and
   the map does not draw them, so carrying them would only inflate the archive —
   for Berlin, from about 8 MB to 55.7 MB. Pass --context to keep them as a
   separate, coalesced layer holding geometry and highway only; that is the form
   a comparison view would want, to show where BikeNEAT found nothing.
"""

import argparse
import json
import time
from pathlib import Path

import geopandas as gpd
from freestiler import FreestileLayer, freestile, freestile_layer
from shapely.geometry import LineString
from shapely.ops import linemerge

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


def merge_way_geometry(geom):
    """Join a way's segments into a single LineString where that is provably safe.

    pyrosm hands back each way as a MultiLineString split at its nodes — 19,838 of
    26,592 classified Berlin ways have more than one part. Drawn with a wide line
    every part boundary overlaps its neighbour, which shows up as a knot at every
    node once the line is semi-transparent, and it costs tile size for nothing.

    Direction is the catch: BikeNEAT's left/right is relative to the OSM way
    direction, and the map turns that into a line offset whose sign follows the
    rendered line. linemerge() is free to reverse parts to make them contiguous, so
    a merge that reordered them could silently swap the two sides. The merged line
    is therefore only accepted when it still starts where the first part started and
    ends where the last one ended; otherwise the original is kept.
    """
    if geom is None or geom.is_empty or not hasattr(geom, "geoms") or len(geom.geoms) < 2:
        return geom
    merged = linemerge(geom)
    if not isinstance(merged, LineString):
        return geom
    first, last = geom.geoms[0], geom.geoms[-1]
    if merged.coords[0] == first.coords[0] and merged.coords[-1] == last.coords[-1]:
        return merged
    return geom


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
    parser.add_argument("--context", action="store_true",
                        help="also tile the ways classified 'no' as a context layer")
    parser.add_argument("--context-min-zoom", type=int, default=11,
                        help="zoom at which the context layer appears, with --context")
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

    multipart_before = int(infra.geometry.map(
        lambda g: hasattr(g, "geoms") and len(g.geoms) > 1).sum())
    infra[infra.geometry.name] = infra.geometry.map(merge_way_geometry)
    multipart_after = int(infra.geometry.map(
        lambda g: hasattr(g, "geoms") and len(g.geoms) > 1).sum())
    print(f"merged way segments: {multipart_before - multipart_after} of {multipart_before}"
          f" multipart geometries joined, {multipart_after} left split")

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

    dropped = int((gdf["bicycle_infrastructure"] == NO_INFRA).sum())
    if args.context:
        context = subset(gdf[gdf["bicycle_infrastructure"] == NO_INFRA], CONTEXT_COLUMNS)
        layers["context"] = freestile_layer(context, min_zoom=args.context_min_zoom)
        print(f"context : {len(context)} features, {len(context.columns) - 1} attributes"
              f" (from zoom {args.context_min_zoom})")
    else:
        print(f"skipping {dropped} ways classified '{NO_INFRA}' (pass --context to keep them)")

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
