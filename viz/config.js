// Configuration for the BikeNEAT visualization.

const REPO_OWNER = 'vizsim';
const REPO_NAME = 'bikeneat';
const PMTILES_PREFIX = 'pmtiles://';
const TILES_FILE = 'berlin_bikeneat.pmtiles';

const hasWindow = typeof window !== 'undefined';
const hostname = hasWindow ? window.location.hostname : '';
const isLocalDev = hostname === 'localhost' || hostname === '127.0.0.1';

// Locally the archive is served from viz/tiles next to this page; in production
// it is read straight out of the repository, as in mapillary_coverage_analysis.
const tilesBaseURL = isLocalDev && hasWindow
    ? new URL('./tiles/', window.location.href).href
    : `https://raw.githubusercontent.com/${REPO_OWNER}/${REPO_NAME}/main/viz/tiles/`;

export const PMTILES_URL = `${PMTILES_PREFIX}${tilesBaseURL}${TILES_FILE}`;

// Sidecar written by build_tiles.py: which bicycle_infrastructure values feed
// each legend colour, with counts. Plain fetch, so no pmtiles:// prefix.
export const CATEGORIES_URL =
    `${tilesBaseURL}${TILES_FILE.replace(/\.pmtiles$/, '.categories.json')}`;

// radinfra.de (tilda) as a comparison overlay. Its layers are read
// from the tilda style file kept in this repo rather than restated here, so the
// overlay keeps radinfra's own colours, widths, dashes and filters, and picking
// up a newer style is a matter of replacing the file.
//
// The style's own source ('vt') is renamed on load to avoid colliding with ours.
export const RADINFRA = {
    styleURL: `${tilesBaseURL}atlas_bikelanes_details_mapbox_style.json`,
    sourceId: 'radinfra',
    layerPrefix: 'radinfra-',
    // Invisible click target in the tilda style; nothing to draw, so it is skipped.
    skipLayerIds: ['hitarea-bikelanes-details'],
    label: 'radinfra.de (tilda)',
    // Deep link target, so a click lands on the same place in radinfra.de.
    siteURL: 'https://tilda-geo.de/regionen/radinfra',
    // Opaque hash from a shared radinfra.de link; it selects which layers the
    // target page shows. Replace it to change that selection.
    siteConfig: '1p2va4k.7h3d.9fm70g',
    // The overlay draws above the BikeNEAT lines, otherwise turning it on would
    // change almost nothing where the two datasets agree on a street.
    insertAbove: true,
};

// radinfra.de shows friendlier names in its own legend than the style's layer ids.
// Only the ones that actually differ are listed; anything else falls back to the
// layer id, so a newer tilda style with new layers still appears, just with its raw
// name. 'Geschuetzter Radfahrstreifen' is deliberately absent — radinfra.de spells
// it that way too.
const RADINFRA_LABELS = {
    'needsClarification-details': 'Führungsform unklar',
    'Gemeinsamer Fahrstreifen mit Kfz Markiert': 'Gem. Fahrstreifen mit Kfz (Markiert)',
    'Gemeinsamer Fahrstreifen mit Bus': 'Gem. Fahrstreifen mit Bus',
    'Fahrradstrasse Mischverkehr': 'Fahrradstraße (Mischverkehr)',
    'Fahrradstrasse keine Kfz': 'Fahrradstraße (keine Kfz)',
    'Gehweg Rad frei -details': 'Gehweg mit Rad frei',
    'Gemeinsamer Geh u Radweg': 'Gemeinsamer Geh- & Radweg',
};

export function radinfraLabel(layerId) {
    return RADINFRA_LABELS[layerId] ?? layerId;
}

// Build a radinfra.de URL for the current view, optionally selecting one OSM way.
//
// The parameters are taken from a shared radinfra.de link:
//   map=<zoom>/<lat>/<lng>   the view
//   config=<hash>            layer selection
//   v=2                      link format version
//   f=10|way/<id>|<w>|<s>|<e>|<n>   preselect a feature
//
// `map`, `config` and `v` are straightforward. The `f` grammar is inferred from
// that single example, so treat it as best effort: if radinfra.de reads it
// differently the link still lands at the right place and zoom, it just will not
// preselect the way. Built by hand rather than with URLSearchParams so the '/'
// and '|' stay unescaped, as in the original link.
export function radinfraURL({ zoom, lat, lng, wayId = null, bounds = null }) {
    const parts = [
        `map=${zoom.toFixed(1)}/${lat.toFixed(4)}/${lng.toFixed(4)}`,
        `config=${RADINFRA.siteConfig}`,
        'v=2',
    ];
    if (wayId && bounds) {
        const [west, south, east, north] = bounds.map((n) => n.toFixed(6));
        parts.push(`f=10|way/${wayId}|${west}|${south}|${east}|${north}`);
    }
    return `${RADINFRA.siteURL}?${parts.join('&')}`;
}

export const BASEMAP_STYLE = 'https://tiles.openfreemap.org/styles/positron';

export const CLASSIFICATION_FIELD = 'bicycle_infrastructure';

export const INFRA_SOURCE_LAYER = 'bikeneat';
export const CONTEXT_SOURCE_LAYER = 'context';

export const initialMapConfig = {
    center: [13.4134, 52.5049],
    zoom: 11,
    minZoom: 8,
    maxZoom: 18,
};

// Highway types whose geometry *is* the cycling infrastructure rather than a
// carriageway carrying it on its sides. Drawing two offset lines for
// 'bicycle_way_both' on a standalone cycleway would suggest two separate paths,
// so these get a single centred line instead.
//
// In the Berlin extract cycleway (10,787), path (2,500) and track (164) carry no
// asymmetric or one-sided category at all, so collapsing their two sides loses
// nothing. 'pedestrian' has 3 ways whose sides differ; those are drawn as one
// line too, which means their asymmetry is not visible on the map. build_tiles.py
// prints a warning listing exactly those cases on every build.
export const STANDALONE_HIGHWAYS = ['cycleway', 'path', 'track', 'pedestrian'];

// Colours follow the radinfra.de (tilda) "details" style
// (viz/tiles/atlas_bikelanes_details_mapbox_style.json) so that a BikeNEAT layer
// and a radinfra.de layer can be read against each other without relearning the
// palette.
//
// The two schemes are not equivalent: BikeNEAT has five forms and records which
// side of the street carries each, radinfra.de has thirteen categories and no side.
// `radinfra` records which tilda layer a colour was taken from and is documentation
// only — nothing renders it, deliberately, because a per-category label in the UI
// would claim a correspondence that does not exist. The legend says it once instead.
//
// `id` is the value build_tiles.py writes into infra_left / infra_right.
//
// Which bicycle_infrastructure values feed each colour is not listed here: it is
// derived from the tiled data by build_tiles.py into a sidecar JSON next to the
// archive, so the legend cannot drift from what was actually built and can show
// real counts. See CATEGORIES_URL.
export const categoryGroups = [
    {
        id: 'bicycle_road',
        label: 'Fahrradstraße',
        color: '#fb923c',
        // Collective name: tilda splits this into 'Fahrradstrasse keine Kfz' and
        // 'Fahrradstrasse Mischverkehr', which share the colour.
        radinfra: 'Fahrradstraße',
        // A Fahrradstraße applies to the whole carriageway, so it is drawn as a
        // single centred line rather than one line per side.
        centered: true,
    },
    {
        id: 'bicycle_way',
        label: 'Radweg, baulich getrennt',
        color: '#174ed9',
        radinfra: 'Getrennter Radweg',
    },
    {
        id: 'bicycle_lane',
        label: 'Radfahrstreifen',
        color: '#2dd4bf',
        radinfra: 'Radfahrstreifen',
    },
    {
        id: 'shared_way',
        label: 'Gemeinsamer Geh- und Radweg',
        color: '#e949ac',
        radinfra: 'Gemeinsamer Geh u Radweg',
    },
    {
        id: 'bus_lane',
        label: 'Busspur mit Radverkehr',
        color: '#059669',
        radinfra: 'Gemeinsamer Fahrstreifen mit Bus',
    },
];

export const contextStyle = {
    color: '#c9cdd2',
    minZoom: 11,
};

// Hover highlight for the way under the cursor. Drawn as a wide, blurred halo
// beneath the category lines so their colour stays readable on top of it.
export const hoverStyle = {
    color: '#fb923c',
    opacity: 0.55,
    width: ['interpolate', ['linear'], ['zoom'], 10, 5, 14, 9, 18, 16],
};

// Taken verbatim from the tilda style so line weights match at every zoom.
export const LINE_WIDTH = ['interpolate', ['linear'], ['zoom'], 10, 1.5, 14, 2, 16, 3];

// Which side of the street carries which infrastructure is shown by drawing the
// left and right classification as separate lines, offset in opposite
// directions — the pattern used for the maxspeed layers in vizsim/unfallkarte.
// A positive line-offset is to the right of the way direction, which is the same
// reference OSM (and therefore BikeNEAT) uses for left/right.
// Stops are [zoom, offset at that zoom]; the sign is applied per side.
export const SIDE_OFFSET_STOPS = [
    [10, 1],
    [14, 2],
    [18, 5],
    [20, 8],
];
