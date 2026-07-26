# BikeNEAT

A framework for classifying bicycle infrastructure in OpenStreetMap.


## This fork

This is a checkout of the upstream framework with a runnable local environment, a command
line entry point and a few compatibility fixes. Nothing about the classification logic
itself was changed — the category definitions and indicator rules are untouched.

### Setup

```bash
uv sync --extra test
uv run pytest bikeneat_tests.py
```

Requires a C compiler: `cykhash` (a `pyrosm` dependency) ships no wheels and is built from
source.

### Added

- **[run_bikeneat.py](run_bikeneat.py)** — command line runner around
  `classify_with_bikeneat`, with output to GeoPackage, GeoParquet, GeoJSON or CSV. Columns
  holding dicts (`tags`) are JSON-serialised so the OGR drivers can write them.
- **`pyproject.toml` / `uv.lock`** — pinned environment, including `pyarrow` for GeoParquet.
- **`data/` layout** — `data/raw/` for OSM extracts, `data/results/` for outputs. Results and
  large extracts are gitignored; the small Wedel sample stays tracked.

### Fixed

Four bugs surfaced when running the framework on current dependencies and on a city-sized
extract:

| Issue | Cause |
| --- | --- |
| `['area'] not found in axis` | `pyrosm` 0.12 no longer returns an `area` column; it is now only used internally to decide polygon vs. linestring. The column was in a hardcoded drop list. |
| PBF export silently skipped | `_export_to_pbf` built its output path as `'bikeneat_' + input_pbf`, which yields `bikeneat_data/raw/x.pbf` — a nonexistent directory — for any input in a subfolder. The surrounding `except` swallowed it as a warning. |
| `the JSON object must be str, bytes or bytearray, not float` | `pyrosm` leaves `tags` as `NaN` for ways with no tags beyond the standard columns, and `json.loads` was applied unconditionally. Affects 235 of 216,398 ways in Berlin and **none** in the Wedel sample, so it only appears at scale. |
| PBF export failed on every repeated run | `osmium.SimpleWriter` refuses to open an existing file, so `--export-pbf` only ever worked once per output path. Now opened with `overwrite=True`. |

The `NaN` tags case is covered by a regression test
(`test_prepare_way_tolerates_missing_tags`), since a small extract does not reproduce it.

Note that `classify_with_bikeneat` catches every exception, prints it and returns `None`. A
failed run therefore looks like a successful one unless the caller checks the return value —
`run_bikeneat.py` does, but direct callers should too.

### Performance

Measured on an AMD Ryzen 7 PRO 8840HS (8 cores), Python 3.12.3, `pyrosm` 0.12.0,
`geopandas` 1.1.4, `pandas` 3.0.5, GDAL 3.12.4. Single run per configuration, so expect a few
percent variance. Classification was timed once per region; both formats were then written
from the same in-memory GeoDataFrame to isolate the export cost.

| Region | PBF | Ways | Classification | Peak RSS |
| --- | --- | --- | --- | --- |
| Wedel | 1.6 MB | 18,146 | 4.5 s | 350 MB |
| Berlin | 94.6 MB | 216,398 | 116.9 s | 7.8 GB |

Runtime scales roughly with way count; memory is the resource to watch, since the outer merge
of the cycling and driving networks is held in full. Berlin peaks near 8 GB from a 95 MB
extract — a whole-country extract will not fit on a typical laptop without tiling the input.

Classification results:

| Region | Ways | With cycling infrastructure | Share |
| --- | --- | --- | --- |
| Wedel | 18,146 | 1,203 | 6.6 % |
| Berlin | 216,398 | 26,592 | 12.3 % |

### GeoPackage vs. GeoParquet

| Region | Format | Write | Read | Size |
| --- | --- | --- | --- | --- |
| Wedel | GeoPackage | 0.44 s | 0.30 s | 8.5 MB |
| Wedel | GeoParquet | 0.12 s | 0.19 s | 2.4 MB |
| Berlin | GeoPackage | 5.92 s | 3.30 s | 120.0 MB |
| Berlin | GeoParquet | 0.64 s | 0.52 s | 27.2 MB |

At Berlin size GeoParquet is 4.4× smaller, writes 9.3× faster and reads 6.3× faster. Both
roundtrip without row loss. The gap widens with size, because GeoPackage is SQLite and pays
per-row insert overhead where Parquet writes columnar batches.

GeoPackage remains the better choice for handing a layer to QGIS interactively; GeoParquet is
the better archive and analysis format. One practical caveat: GeoPackage needs working file
locking, so it cannot reliably be opened across a network share — including a WSL filesystem
accessed from Windows. GeoParquet has no such constraint.

```bash
# GeoPackage for QGIS
uv run python run_bikeneat.py data/raw/berlin-251109.osm.pbf -o data/results/berlin.gpkg

# GeoParquet for analysis, plus indicator columns and a tagged PBF
uv run python run_bikeneat.py data/raw/berlin-251109.osm.pbf \
    -o data/results/berlin.parquet --indicators --export-pbf
```

## Publications

- **Łukawska, M., Richter, E., Porojkow, I., & Huber, S. (2026)**: *BikeNEAT: a framework for classifying bicycle infrastructure in OpenStreetMap.* Journal of Geovisualization and Spatial Analysis, 30. https://doi.org/10.1007/s41651-026-00271-6.

## Licence and attribution

The upstream repository carries no licence file. The paper describes the implementation as
"the open-source code" and states that it is publicly available on GitHub, and the article
itself is published under CC BY 4.0. I have read that as intent for reuse and am building on
it here in good faith — non-commercially, with attribution, and with the classification logic
itself unchanged.

To be explicit about what that does and does not mean:

- Copyright in the original code remains with the authors (TU Dresden). No rights to it are
  claimed here.
- This fork deliberately adds no licence file of its own, since it cannot grant terms for
  someone else's code.
- The framework specification — indicators, OSM tag combinations, category hierarchy — is
  published in the paper's Supplementary Material under CC BY 4.0, which does permit
  adaptation with attribution.
- Classification outputs are derived from OpenStreetMap and therefore fall under ODbL,
  independently of this repository.

Please cite the paper, not this fork, when referring to BikeNEAT.

