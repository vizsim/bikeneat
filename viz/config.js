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

// Colours follow the radverkehrsatlas "details" style
// (viz/tiles/atlas_bikelanes_details_mapbox_style.json) so that a BikeNEAT
// classification and a radinfra.de layer can be read against each other
// without relearning the palette. `radinfra` names the layer each colour is
// taken from.
//
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
        radinfra: 'Fahrradstrasse',
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

// Taken verbatim from the atlas style so line weights match at every zoom.
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
