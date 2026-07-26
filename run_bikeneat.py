"""Command line runner for BikeNEAT classification."""

import argparse
import json
from pathlib import Path

from bikeneat_functions import aggregate_the_no_infra_category, classify_with_bikeneat


def _serialise_for_export(gdf):
    """Convert dict/list columns to JSON strings so OGR drivers can write them."""
    gdf = gdf.copy()
    for col in gdf.columns:
        if col == gdf.geometry.name:
            continue
        sample = gdf[col].dropna()
        if not sample.empty and isinstance(sample.iloc[0], (dict, list)):
            gdf[col] = gdf[col].map(lambda v: json.dumps(v) if isinstance(v, (dict, list)) else v)
    return gdf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pbf", help="input .osm.pbf file")
    parser.add_argument("-o", "--out", help="output file (.gpkg, .geojson, .parquet or .csv)")
    parser.add_argument("--single", action="store_true",
                        help="classify one category per way instead of left/right")
    parser.add_argument("--no-aggregate", action="store_true",
                        help="keep detailed no-infrastructure categories")
    parser.add_argument("--indicators", action="store_true",
                        help="include the individual indicator columns")
    parser.add_argument("--export-pbf", action="store_true",
                        help="also write a PBF tagged with bicycle_infrastructure")
    args = parser.parse_args()

    gdf = classify_with_bikeneat(
        args.pbf,
        single=args.single,
        aggregated=not args.no_aggregate,
        output_arg={"include_indicators": args.indicators, "export_pbf": args.export_pbf},
    )

    if gdf is None:
        raise SystemExit("classification failed")

    counts = gdf["bicycle_infrastructure"].value_counts()
    # count via the aggregation map so --no-aggregate subcategories such as
    # service_misc or mit_road are still recognised as "no infrastructure"
    with_infra = int(
        sum(n for cat, n in counts.items() if aggregate_the_no_infra_category(cat) != "no")
    )
    print(f"\n{len(gdf)} ways classified, {with_infra} with cycling infrastructure\n")
    print(counts.to_string())

    if args.out:
        out = Path(args.out)
        export = _serialise_for_export(gdf)
        if out.suffix == ".csv":
            export.drop(columns=export.geometry.name).to_csv(out, index=False)
        elif out.suffix == ".parquet":
            export.to_parquet(out)
        else:
            export.to_file(out)
        print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
