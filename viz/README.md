# viz

A sample map for comparing the BikeNEAT classification with
[radinfra.de](https://radinfra.de) (tilda) — two classifications of OpenStreetMap,
side by side. BikeNEAT is tiled from a fixed extract (Berlin, 2026-07-25),
radinfra.de is served live from tilda-geo.de and is therefore current — so a
difference between the two can be an OSM edit rather than a difference in method.

BikeNEAT itself is the work of Mirosława Łukawska, Emely Richter, Iwan Porojkow and
Stefan Huber at TU Dresden, published open access under CC BY 4.0:
[Journal of Geovisualization and Spatial Analysis 10:30
(2026)](https://doi.org/10.1007/s41651-026-00271-6), code at
[mirlu-tud/bikeneat](https://github.com/mirlu-tud/bikeneat).

## Pipeline

```bash
# 1. classify to GeoParquet
uv run python run_bikeneat.py data/raw/berlin-260725.osm.pbf \
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
returns the whole file with status 200. In production this does not come up,
because raw.githubusercontent.com honours ranges.

Ways classified `no` are dropped at build time — they are ~88 % of the network
and the map does not draw them. For Berlin the archive is 7.4 MB and takes 1.5 s to
tile; with `--context` it is 15.1 MB and 6.3 s. Pass `--context` to keep them as a separate,
coalesced layer holding geometry and highway only; the page already has a
`bikeneat-context` layer that draws it when present.

## Way geometry

pyrosm hands back each way as a MultiLineString split at its nodes — 21,098 of the
28,695 classified Berlin ways have more than one part, one of them 115.
`merge_way_geometry()` joins them back into one LineString, which takes the archive
from 9.0 MB to 7.4 MB and removes a rendering artifact: a wide semi-transparent line
drawn over abutting parts doubles up at every join, so the hover halo showed a knot
at each node.

Direction is the catch. BikeNEAT's left/right is relative to the OSM way direction,
and the map turns that into a `line-offset` whose sign follows the rendered line, so
a merge that reversed or reordered parts would silently swap the two sides.
`linemerge()` is allowed to do exactly that. The merged line is therefore only
accepted when it still starts where the first part started and ends where the last
one ended. For the July 2026 Berlin extract that keeps 21,081 merges and leaves 17
geometries split, which the build reports.

Note that `queryRenderedFeatures` reports line geometry split into segments
regardless; that is MapLibre reconstructing the query result, not what is stored.
Check the archive with `pmtiles tile` if you want the real part counts.

## Colours

Taken from `tiles/atlas_bikelanes_details_mapbox_style.json`, with the mapping
declared in [config.js](config.js):

| BikeNEAT | tilda layer | colour |
| --- | --- | --- |
| `bicycle_road` | Fahrradstraße (beide Varianten) | `#fb923c` |
| `bicycle_way_*` | Getrennter Radweg | `#174ed9` |
| `bicycle_lane_*` | Radfahrstreifen | `#2dd4bf` |
| `shared_way_*` | Gemeinsamer Geh u Radweg | `#e949ac` |
| `bus_lane_*` | Gemeinsamer Fahrstreifen mit Bus | `#059669` |

Line widths are copied verbatim from the tilda style so weights match at every
zoom.

**The two schemes are not equivalent**, and the page says so rather than implying
otherwise. Borrowing the palette makes them readable next to each other, nothing
more. `categoryGroups[].radinfra` records where each colour came from but is
documentation only — deliberately nothing renders it, since a per-category label in
the UI would assert a correspondence that does not exist.

Two things worth knowing before reading differences as method differences, both
measured from the tiles rather than assumed:

- The 13 entries in the radinfra legend are the **style's layers**, not its
  categories. The style's filters reference 24 distinct `category` values, and a
  single z12 tile over Berlin Mitte carries 25.
- **radinfra encodes sides too**, just differently: it splits a street into separate
  features whose ids end in `/left` or `/right` (`way/1110388548/cycleway/left` and
  `…/right`), where BikeNEAT keeps one feature and puts both sides in the category
  name. 55 % of the features in that tile are side-specific.

Beyond that, this README does not characterise radinfra's taxonomy — it has not been
checked against their documentation.

## Sides

BikeNEAT records which side of the road carries which infrastructure in the category
value itself, where radinfra.de keeps the side out of the category and splits the
street into separate features instead. Each side is drawn here as its own line,
offset in opposite directions — the pattern used for the maxspeed layers in
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
- **`highway=cycleway`, `path`, `track` and `pedestrian`** — the way's own
  geometry *is* the infrastructure, so an offset pair would read as two separate
  paths (`STANDALONE_HIGHWAYS`). In the July 2026 Berlin extract cycleway (11,129),
  path (2,618) and track (162) carry no way whose two sides differ, so collapsing
  them loses nothing; `pedestrian` (184) has one. That one is drawn as a single line
  too, so its asymmetry is not visible and the higher-grade form is what shows.
  `build_tiles.py` prints a warning naming exactly those cases on every build, so
  the collapse cannot go unnoticed — the count is data-dependent and will move with
  the extract.

The popup notes this case rather than showing left/right rows that would not mean
anything.

The styled layers deliberately do not set `line-cap: round`; the tilda style sets
round caps only on its hitarea layer.

## Hover and click

Hovering a way draws a wide, blurred orange halo beneath it, so the category colour
stays readable. Both datasets have one: `bikeneat-hover` and `radinfra-hover`,
filtered to the hovered feature id. Only ever one is active — both layer sets are
queried in a single call, so the topmost drawn line wins, which is the overlay
wherever it is switched on.

Clicks are resolved from the same query, so a click always acts on whatever the
halo is highlighting:

- a **BikeNEAT** way opens the popup, which reports the classification;
- a **radinfra** way opens radinfra.de in a new tab, deep-linked to that feature —
  this page has nothing to add about it.

radinfra ids identify a side of a way rather than the way (`way/1460141762` but
also `way/1460141762/cycleway/left`), so `osmWayId()` reduces them to the OSM way
the deep link needs. If it cannot, the link still opens the current view.

Note that BikeNEAT ids are numbers and radinfra ids strings (`way/123/cycleway/left`),
so each halo needs its own "match nothing" sentinel.

**Pointer events are bound to the map, not to a layer**, and hit testing uses a
small box around the cursor rather than the exact point. The earlier approach — a
wide line with `line-opacity: 0` as a hit target, with handlers bound to it, as the
tilda style does — does not work here: a layer-scoped handler never fires for a
fully transparent line, even though `queryRenderedFeatures` keeps returning its
features. Querying the drawn layers directly also means a hidden category cannot
be hovered or clicked.

## Legend controls

Switches use the same markup and styling as
[vizsim/mapillary_coverage_analysis](https://github.com/vizsim/mapillary_coverage_analysis)
(`.toggle-switch.toggle-switch-sm`), in the small variant.

The legend has two groups, each with a master switch and an indented list of
category rows:

- **BikeNEAT** — master switch for the whole classification, hover halo included.
  The **Details** switch sits inside this group, since it only concerns BikeNEAT.
- **Vergleich: radinfra.de** — master switch for the overlay, with its 13 tilda
  categories below.

Category rows are buttons, not switches: clicking the legend line hides that
category, which dims the row and greys its colour swatch. They carry
`role="switch"` and `aria-checked`, so they stay keyboard-operable.

Both groups use the same model — effective visibility is the master AND the
per-category state — so switching a master off and back on restores whichever
categories were left showing rather than turning everything back on.

Rows in both lists come from the same `createCategoryRow()`, so they are the same
size by construction rather than by two CSS rules that have to be kept in step.

The radinfra list is collapsed until its overlay is on; 13 entries otherwise push
the rest of the legend off the panel.

Hovering a category row tints it orange, in both lists.

## Deep links into radinfra.de

`radinfraURL()` in [config.js](config.js) builds links to
`tilda-geo.de/regionen/radinfra`:

- the **radinfra.de link in the legend** carries the current view and is rewritten
  on every `moveend`, so it always opens what is on screen;
- the **popup** adds one for the clicked way, preselecting it.

Parameters were read off a shared radinfra.de link: `map=<zoom>/<lat>/<lng>`,
`config=<hash>` for the layer selection, `v=2`, and
`f=10|way/<id>|<west>|<south>|<east>|<north>` to preselect a feature. The first
three are clear; the `f` grammar is inferred from that single example, so it is
best effort — if radinfra.de reads it differently the link still lands at the
right place and zoom, it just will not preselect the way. The bounding box is
taken from the tiled geometry, which is clipped at tile edges, so for a long way
it can cover only the loaded part.

`RADINFRA.siteConfig` is an opaque hash from that link and decides which layers
the target page shows; replace it to change that.

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

## radinfra.de overlay

A checkbox in the legend overlays the radinfra.de classification, served live
from `tiles.tilda-geo.de`. It is off by default and draws above the BikeNEAT
lines, since otherwise switching it on would change almost nothing where the two
datasets agree.

The legend lists the categories in the same order radinfra.de does. A style's layer
array runs bottom-to-top because that is drawing order, so the list is reversed for
display only; the layers keep the z-order the style asked for.

Labels come from `RADINFRA_LABELS` in [config.js](config.js), which carries the names
radinfra.de shows in its own legend — the style's layer ids read rather raw
(`needsClarification-details` for "Führungsform unklar"). Only the ids that actually
differ are listed; anything else falls back to the id, so a newer tilda style with new
layers still appears, just with its raw name.

The layers are not restated in this repo's config. `addRadinfraLayers()` fetches
`tiles/atlas_bikelanes_details_mapbox_style.json`, renames its source, and adds
its 13 styled layers as-is, so the overlay keeps radinfra's own colours, widths,
dashes and filters — and picking up a newer tilda style means replacing that one
file. The style's own `hitarea` layer is skipped, since hit testing here does not
use one.

**Caveat for the comparison.** The BikeNEAT colours were deliberately taken from
this same tilda style so the two can be read against each other. That makes them
hard to tell apart when both are drawn at once — teal over teal, orange over
orange. Overlaying is enough to spot where one dataset has geometry and the other
does not, but a real side-by-side comparison needs either two synchronised maps, a
swipe, or a distinct visual treatment for one of the layers.

Note also that the overlay is current OSM data while the tiled BikeNEAT layer is a
fixed extract (2026-07-25 for Berlin), so some differences are edits, not method.

## Smoke test

`window.bikeneatMap` is exposed for console access. To check a build:

```js
const m = window.bikeneatMap;
m.getStyle().layers.filter(l => l.id.startsWith('bikeneat'))
    .map(l => [l.id, m.queryRenderedFeatures({layers: [l.id]}).length]);
```

Every `bikeneat-*` layer should report features at zoom 11 over Berlin, except
`bikeneat-context`, which is empty unless the archive was built with `--context`,
and `bikeneat-hover`, which only matches while a way is hovered.

Test pointer behaviour with real mouse events, not `map.fire('click')`. Firing the
event directly bypasses hit testing entirely, so it reports success even when
nothing on the map is actually clickable.

One console warning is expected and is not ours: *"Expected value to be of type
number, but found null instead."* comes from the openfreemap positron style, and
reproduces with that basemap alone and no BikeNEAT layers added.
