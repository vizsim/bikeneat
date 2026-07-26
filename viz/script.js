import {
    BASEMAP_STYLE,
    CATEGORIES_URL,
    CLASSIFICATION_FIELD,
    CONTEXT_SOURCE_LAYER,
    INFRA_SOURCE_LAYER,
    LINE_WIDTH,
    PMTILES_URL,
    SIDE_OFFSET_STOPS,
    STANDALONE_HIGHWAYS,
    categoryGroups,
    contextStyle,
    initialMapConfig,
} from './config.js';

const SOURCE_ID = 'bikeneat';

// Positive offset is to the right of the way direction, matching the sense in
// which OSM and BikeNEAT mean left/right.
function sideOffset(side) {
    const factor = side === 'right' ? 1 : -1;
    const expr = ['interpolate', ['linear'], ['zoom']];
    for (const [zoom, offset] of SIDE_OFFSET_STOPS) expr.push(zoom, factor * offset);
    return expr;
}

// A standalone cycleway or path is itself the infrastructure, so its two sides
// are drawn as one centred line rather than as an offset pair.
const isStandalone = ['in', ['get', 'highway'], ['literal', STANDALONE_HIGHWAYS]];
const onCarriageway = ['!', isStandalone];

export function layerIdsFor(group) {
    if (group.centered) return [`bikeneat-${group.id}`];
    return [
        `bikeneat-${group.id}-right`,
        `bikeneat-${group.id}-left`,
        `bikeneat-${group.id}-single`,
    ];
}

function infraLayerSpecs() {
    const specs = [];
    // Reverse order so the highest-grade infrastructure ends up drawn on top.
    for (const group of [...categoryGroups].reverse()) {
        const base = {
            type: 'line',
            source: SOURCE_ID,
            'source-layer': INFRA_SOURCE_LAYER,
            // Deliberately no 'line-cap': 'round' — the atlas style sets round caps
            // only on its hitarea layer, and round caps would bleed past the ends
            // of short segments drawn side by side.
            layout: { visibility: 'visible' },
            paint: { 'line-color': group.color, 'line-width': LINE_WIDTH },
        };
        if (group.centered) {
            specs.push({
                ...base,
                id: `bikeneat-${group.id}`,
                filter: ['==', ['get', 'infra_right'], group.id],
            });
            continue;
        }
        for (const side of ['right', 'left']) {
            specs.push({
                ...base,
                id: `bikeneat-${group.id}-${side}`,
                filter: ['all', onCarriageway, ['==', ['get', `infra_${side}`], group.id]],
                paint: { ...base.paint, 'line-offset': sideOffset(side) },
            });
        }
        // Matching either side keeps the line if a standalone way ever does turn up
        // with an asymmetric category, rather than dropping one of the two values.
        specs.push({
            ...base,
            id: `bikeneat-${group.id}-single`,
            filter: ['all', isStandalone, ['any',
                ['==', ['get', 'infra_right'], group.id],
                ['==', ['get', 'infra_left'], group.id],
            ]],
        });
    }
    return specs;
}

function buildLegend(map) {
    const list = document.getElementById('legend-items');
    for (const group of categoryGroups) {
        const entry = document.createElement('div');
        entry.className = 'legend-entry';

        const row = document.createElement('label');
        row.className = 'legend-item';
        row.title = `radverkehrsatlas: ${group.radinfra}`;

        const box = document.createElement('input');
        box.type = 'checkbox';
        box.checked = true;
        box.addEventListener('change', () => {
            const visibility = box.checked ? 'visible' : 'none';
            for (const id of layerIdsFor(group)) {
                if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', visibility);
            }
        });

        const swatch = document.createElement('span');
        swatch.className = 'legend-color';
        swatch.style.background = group.color;

        const text = document.createElement('span');
        text.textContent = group.label;

        row.append(box, swatch, text);
        entry.appendChild(row);

        const detail = document.createElement('ul');
        detail.className = 'legend-detail';
        detail.dataset.group = group.id;
        entry.appendChild(detail);

        list.appendChild(entry);
    }

    const details = document.getElementById('toggle-details');
    const apply = () => list.classList.toggle('legend-items--details', details.checked);
    details.addEventListener('change', apply);
    apply();

    void fillCategoryDetail(list);
}

// Populate each legend entry with the bicycle_infrastructure values that feed it,
// read from the sidecar build_tiles.py writes next to the archive.
async function fillCategoryDetail(list) {
    let payload;
    try {
        const response = await fetch(CATEGORIES_URL);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        payload = await response.json();
    } catch (error) {
        console.warn('category index unavailable:', error);
        for (const ul of list.querySelectorAll('.legend-detail')) {
            const li = document.createElement('li');
            li.className = 'legend-detail__note';
            li.textContent = 'Kategorieliste nicht verfügbar.';
            ul.appendChild(li);
        }
        return;
    }

    for (const ul of list.querySelectorAll('.legend-detail')) {
        const group = payload.groups?.[ul.dataset.group];
        if (!group) continue;

        const head = document.createElement('li');
        head.className = 'legend-detail__note';
        head.textContent = `${group.total.toLocaleString('de-DE')} Wege, `
            + `${group.categories.length} Kategorie${group.categories.length === 1 ? '' : 'n'}`;
        ul.appendChild(head);

        for (const entry of group.categories) {
            const li = document.createElement('li');
            const name = document.createElement('code');
            name.textContent = entry.name;
            const meta = document.createElement('span');
            meta.className = 'legend-detail__meta';
            meta.textContent = `${entry.side} · ${entry.count.toLocaleString('de-DE')}`;
            li.append(name, meta);
            ul.appendChild(li);
        }
    }
}

const groupLabels = new Map(categoryGroups.map((g) => [g.id, g.label]));

function sideLabel(value) {
    if (!value) return '<em>keine</em>';
    return groupLabels.get(value) ?? value;
}

function popupHtml(props) {
    const category = props[CLASSIFICATION_FIELD] ?? '–';
    const name = props.name || 'ohne Namen';
    const standalone = STANDALONE_HIGHWAYS.includes(props.highway);

    let categoryCell = `<code>${category}</code>`;
    let rows;
    if (standalone) {
        // On a standalone cycleway or path the left/right part of the category name
        // does not describe two sides of a carriageway, so showing them as separate
        // rows would be misleading.
        categoryCell += `<span class="popup-hint">Eigenständiger Weg — die Seitenangabe
            in der Kategorie bezieht sich nicht auf eine Fahrbahn, deshalb eine Linie.</span>`;
        rows = [['Kategorie', categoryCell]];
    } else {
        rows = [
            ['Links', sideLabel(props.infra_left)],
            ['Rechts', sideLabel(props.infra_right)],
            ['Kategorie', categoryCell],
        ];
    }
    rows.push(
        ['Straßentyp', props.highway ?? '–'],
        ['Länge', props.length != null ? `${Math.round(props.length)} m` : '–'],
    );
    const body = rows
        .map(([k, v]) => `<tr><th>${k}</th><td>${v}</td></tr>`)
        .join('');
    const osm = props.id
        ? `<a href="https://www.openstreetmap.org/way/${props.id}" target="_blank" rel="noopener">Way ${props.id} auf osm.org</a>`
        : '';
    return `<h4>${name}</h4><table>${body}</table>${osm}`;
}

function main() {
    const protocol = new pmtiles.Protocol();
    maplibregl.addProtocol('pmtiles', protocol.tile);

    const map = new maplibregl.Map({
        container: 'map',
        style: BASEMAP_STYLE,
        center: initialMapConfig.center,
        zoom: initialMapConfig.zoom,
        minZoom: initialMapConfig.minZoom,
        maxZoom: initialMapConfig.maxZoom,
        hash: true,
    });

    // Exposed for console inspection and for the smoke test in viz/README.md.
    window.bikeneatMap = map;

    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    map.addControl(new maplibregl.ScaleControl({ maxWidth: 120 }));

    map.on('load', () => {
        map.addSource(SOURCE_ID, { type: 'vector', url: PMTILES_URL });

        map.addLayer({
            id: 'bikeneat-context',
            type: 'line',
            source: SOURCE_ID,
            'source-layer': CONTEXT_SOURCE_LAYER,
            minzoom: contextStyle.minZoom,
            paint: {
                'line-color': contextStyle.color,
                'line-width': ['interpolate', ['linear'], ['zoom'], 11, 0.5, 16, 1.5],
            },
        });

        const infraLayers = infraLayerSpecs();
        for (const spec of infraLayers) map.addLayer(spec);

        // Invisible wide line on top to make thin lines clickable, as the atlas
        // style does with its hitarea layer.
        const clickableIds = infraLayers.map((spec) => spec.id);
        map.addLayer({
            id: 'bikeneat-hitarea',
            type: 'line',
            source: SOURCE_ID,
            'source-layer': INFRA_SOURCE_LAYER,
            layout: { 'line-cap': 'round' },
            paint: {
                'line-opacity': 0,
                'line-color': '#000000',
                'line-width': ['interpolate', ['linear'], ['zoom'], 9, 4, 14, 10, 18, 14],
            },
        });

        buildLegend(map);

        const popup = new maplibregl.Popup({ closeButton: true, maxWidth: '320px' });

        map.on('click', 'bikeneat-hitarea', (event) => {
            // Query the visible styled layers so a hidden group is not clickable.
            const hits = map.queryRenderedFeatures(event.point, { layers: clickableIds });
            if (!hits.length) return;
            popup.setLngLat(event.lngLat).setHTML(popupHtml(hits[0].properties)).addTo(map);
        });

        map.on('mouseenter', 'bikeneat-hitarea', () => {
            map.getCanvas().style.cursor = 'pointer';
        });
        map.on('mouseleave', 'bikeneat-hitarea', () => {
            map.getCanvas().style.cursor = '';
        });
    });

    map.on('error', (event) => {
        console.error('map error', event && event.error ? event.error : event);
    });
}

main();
