# viz

MapLibre page showing the BikeNEAT classification, styled after the
[radverkehrsatlas](https://radverkehrsatlas.de) so that a BikeNEAT layer and a
radinfra.de layer can be read against each other.

## Pipeline

```bash
# 1. classify to GeoParquet
uv run python run_bikeneat.py data/raw/berlin-251109.osm.pbf \
    -o data/results/berlin_bikeneat.parquet

# 2. tile to PMTiles
uv sync --extra viz
uv run python viz/build_tiles.py data/results/berlin_bikeneat.parquet \
    -o viz/tiles/berlin_bikeneat.pmtiles

# 3. serve
uv run python viz/serve.py     # http://127.0.0.1:8765
```

Step 3 needs `viz/serve.py` rather than `python -m http.server`: PMTiles reads
byte ranges out of the archive, and the stock handler ignores `Range` and
returns the whole 15 MB file with status 200. In production this does not come
up, because raw.githubusercontent.com honours ranges.

## Colours

Taken from `tiles/atlas_bikelanes_details_mapbox_style.json`, with the mapping
declared in [config.js](config.js):

| BikeNEAT | atlas layer | colour |
| --- | --- | --- |
| `bicycle_road` | Fahrradstrasse | `#fb923c` |
| `bicycle_way_*` | Getrennter Radweg | `#174ed9` |
| `bicycle_lane_*` | Radfahrstreifen | `#2dd4bf` |
| `shared_way_*` | Gemeinsamer Geh u Radweg | `#e949ac` |
| `bus_lane_*` | Gemeinsamer Fahrstreifen mit Bus | `#059669` |

Line widths are copied verbatim from the atlas style so weights match at every
zoom.

## Sides

BikeNEAT records which side of the road carries which infrastructure, which the
atlas categories do not. Each side is drawn as its own line, offset in opposite
directions — the pattern used for the maxspeed layers in
[vizsim/unfallkarte](https://github.com/vizsim/unfallkarte). A positive
`line-offset` is to the right of the way direction, the same reference OSM and
BikeNEAT use for left/right.

So two lines means both sides are served, one line means one side only, and
**two different colours side by side means different infrastructure per side** —
`bicycle_lane_left_shared_right` draws teal on the left and magenta on the right.

`build_tiles.py` resolves the category name into `infra_left` and `infra_right`
so the style can filter on a plain value instead of parsing 23 category strings
in a MapLibre expression. `split_sides()` raises on an unrecognised category, so
a new value fails the build rather than vanishing from the map.

Two cases are drawn as a single centred line instead of an offset pair, because
there is no carriageway for "left" and "right" to refer to:

- **`bicycle_road`** — a Fahrradstraße applies to the whole carriageway
  (`centered: true` in the config).
- **`highway=cycleway` and `highway=path`** — the way's own geometry *is* the
  infrastructure, so an offset pair would read as two separate paths
  (`STANDALONE_HIGHWAYS`). Safe for Berlin: of 10,787 cycleway and 2,500 path
  features, none carries an asymmetric or one-sided category, so collapsing the
  two sides loses nothing. `track` (164 features) is equally unambiguous and
  could be added; `pedestrian` has 3 asymmetric cases and is left out.
  `build_tiles.py` prints a warning if that ever stops holding.

The popup notes this case rather than showing left/right rows that would not mean
anything.

The styled layers deliberately do not set `line-cap: round`; the atlas sets round
caps only on its hitarea layer.

## Legend details view

The legend has a **Details** toggle that lists, per colour, which
`bicycle_infrastructure` values feed it, with counts and which side they land on.

That list is not hardcoded. `build_tiles.py` derives it from the tiled data and
writes a sidecar next to the archive — `berlin_bikeneat.categories.json` for
`berlin_bikeneat.pmtiles` — which the page fetches. So it always matches the
extract that was actually built, and it makes the cross-membership visible: a
category can feed two colours at once, because `bicycle_lane_left_shared_right`
is a lane on the left *and* a shared way on the right. It shows up under
`bicycle_lane` as "links" and under `shared_way` as "rechts".

If the sidecar is missing the toggle still works; the lists just say so.

## Smoke test

`window.bikeneatMap` is exposed for console access. To check a build:

```js
const m = window.bikeneatMap;
m.getStyle().layers.filter(l => l.id.startsWith('bikeneat'))
    .map(l => [l.id, m.queryRenderedFeatures({layers: [l.id]}).length]);
```

Every `bikeneat-*` layer should report features at zoom 11 over Berlin. Note that
`bikeneat-context` is styled close to the basemap's own road colour and is
largely redundant with it; it accounts for roughly 8 MB of the archive. Build
with `--no-context` to drop it.

One console warning is expected and is not ours: *"Expected value to be of type
number, but found null instead."* comes from the openfreemap positron style, and
reproduces with that basemap alone and no BikeNEAT layers added.
