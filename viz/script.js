import {
    BASEMAP_STYLE,
    CATEGORIES_URL,
    CLASSIFICATION_FIELD,
    CONTEXT_SOURCE_LAYER,
    INFRA_SOURCE_LAYER,
    LINE_WIDTH,
    PMTILES_URL,
    RADINFRA,
    SIDE_OFFSET_STOPS,
    STANDALONE_HIGHWAYS,
    categoryGroups,
    contextStyle,
    hoverStyle,
    initialMapConfig,
    radinfraLabel,
    radinfraURL,
} from './config.js';

const SOURCE_ID = 'bikeneat';
const HOVER_LAYER_ID = 'bikeneat-hover';
const RADINFRA_HOVER_LAYER_ID = 'radinfra-hover';

// Pointer events are bound to the map, not to a layer, and hit testing is a small
// box rather than a point. A layer-scoped handler never fires for a line with
// line-opacity 0, which is how the previous invisible hitarea layer was styled —
// queryRenderedFeatures still returned it, so the layer looked fine while no
// click or hover ever reached it. Querying the drawn layers directly also means
// a hidden category cannot be hovered or clicked.
const HIT_PADDING = 6;

// How long the pointer has to sit still before the halo follows it. Long enough that
// sweeping across the map costs nothing, short enough not to feel like a delay.
const HOVER_DELAY_MS = 60;

function hitBox(point) {
    return [
        [point.x - HIT_PADDING, point.y - HIT_PADDING],
        [point.x + HIT_PADDING, point.y + HIT_PADDING],
    ];
}

// bikeneat ids are numbers, radinfra ids strings like 'way/123', so each needs its
// own "match nothing" sentinel.
function setHoverFilter(map, layerId, id, sentinel) {
    if (!map.getLayer(layerId)) return;
    map.setFilter(layerId, ['==', ['get', 'id'], id ?? sentinel]);
}

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
            // Deliberately no 'line-cap': 'round' — the tilda style sets round caps
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

// Both legends are built from this, so a BikeNEAT category row and a radinfra
// category row are identical by construction rather than by matching CSS.
function createCategoryRow({ label, color, title, onToggle }) {
    const row = document.createElement('button');
    row.type = 'button';
    row.className = 'legend-item legend-item--toggle';
    row.setAttribute('role', 'switch');
    row.setAttribute('aria-checked', 'true');
    if (title) row.title = title;

    const swatch = document.createElement('span');
    swatch.className = 'legend-color';
    swatch.style.background = typeof color === 'string' ? color : '#888';

    const text = document.createElement('span');
    text.textContent = label;

    row.append(swatch, text);
    row.addEventListener('click', () => {
        const next = row.getAttribute('aria-checked') !== 'true';
        row.setAttribute('aria-checked', String(next));
        onToggle(next);
    });
    return row;
}

// Visibility is the master switch AND the per-category state, so switching the
// master back on restores whichever categories were left showing.
const groupVisible = new Map(categoryGroups.map((group) => [group.id, true]));
let bikeneatVisible = true;

function applyBikeneatVisibility(map) {
    for (const group of categoryGroups) {
        const on = bikeneatVisible && groupVisible.get(group.id);
        for (const id of layerIdsFor(group)) {
            if (map.getLayer(id)) {
                map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
            }
        }
    }
    // The context layer and the hover halo follow the master only.
    for (const id of ['bikeneat-context', HOVER_LAYER_ID]) {
        if (map.getLayer(id)) {
            map.setLayoutProperty(id, 'visibility', bikeneatVisible ? 'visible' : 'none');
        }
    }
}

function buildLegend(map) {
    const list = document.getElementById('legend-items');
    for (const group of categoryGroups) {
        const entry = document.createElement('div');
        entry.className = 'legend-entry';

        // Deliberately no tooltip naming a radinfra category: the colour is borrowed
        // from there, but the two schemes do not correspond one to one, and a
        // per-row label would claim they do. The legend note says it once instead.
        entry.appendChild(createCategoryRow({
            label: group.label,
            color: group.color,
            onToggle: (on) => {
                groupVisible.set(group.id, on);
                applyBikeneatVisibility(map);
            },
        }));

        const detail = document.createElement('ul');
        detail.className = 'legend-detail';
        detail.dataset.group = group.id;
        entry.appendChild(detail);

        list.appendChild(entry);
    }

    const master = document.getElementById('toggle-bikeneat');
    master.addEventListener('change', () => {
        bikeneatVisible = master.checked;
        list.classList.toggle('legend-items--off', !bikeneatVisible);
        applyBikeneatVisibility(map);
    });

    const details = document.getElementById('toggle-details');
    const apply = () => list.classList.toggle('legend-items--details', details.checked);
    details.addEventListener('change', apply);
    apply();

    void fillCategoryDetail(list);
}

// Load the radinfra.de overlay from the tilda style file, adapting each layer to
// our source id. Returns the added layer ids with their colours for the legend,
// or an empty list if the style could not be read.
async function addRadinfraLayers(map) {
    let style;
    try {
        const response = await fetch(RADINFRA.styleURL);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        style = await response.json();
    } catch (error) {
        console.warn('radinfra style unavailable:', error);
        return [];
    }

    const source = Object.values(style.sources ?? {})[0];
    if (!source) {
        console.warn('radinfra style has no source');
        return [];
    }
    if (!map.getSource(RADINFRA.sourceId)) map.addSource(RADINFRA.sourceId, source);

    // Hover halo for the overlay, added before its styled layers so it sits below.
    // The source layer name comes from the style's own layers rather than being
    // hardcoded, so it follows whatever tilda names it.
    const sourceLayer = (style.layers ?? []).find((l) => l['source-layer'])?.['source-layer'];
    map.addLayer({
        id: RADINFRA_HOVER_LAYER_ID,
        type: 'line',
        source: RADINFRA.sourceId,
        'source-layer': sourceLayer,
        filter: ['==', ['get', 'id'], ''],
        // Butt caps, not round: a round cap overshoots the end of each part by half
        // the line width, so where a way arrives in several parts — across a tile
        // boundary, or as an unmerged MultiLineString — the halos overlap and the
        // translucency doubles up into a knot at every join.
        layout: { 'line-cap': 'butt' },
        paint: {
            'line-color': hoverStyle.color,
            'line-width': hoverStyle.width,
            'line-opacity': hoverStyle.opacity,
            'line-blur': 1,
        },
    });

    const added = [];
    for (const layer of style.layers ?? []) {
        if (RADINFRA.skipLayerIds.includes(layer.id)) continue;
        const spec = {
            ...layer,
            id: RADINFRA.layerPrefix + layer.id,
            source: RADINFRA.sourceId,
            layout: { ...(layer.layout ?? {}), visibility: 'none' },
        };
        map.addLayer(spec);
        added.push({
            id: spec.id,
            label: radinfraLabel(layer.id),
            color: layer.paint?.['line-color'],
        });
    }
    return added;
}

function buildRadinfraLegend(map, layers) {
    const container = document.getElementById('radinfra-legend');
    const toggle = document.getElementById('toggle-radinfra');

    if (!layers.length) {
        toggle.disabled = true;
        toggle.closest('.legend-item').title = 'tilda-Style nicht ladbar';
        const note = document.createElement('p');
        note.className = 'legend-note';
        note.textContent = 'Overlay nicht verfügbar.';
        container.appendChild(note);
        return;
    }

    // Same master-AND-category model as BikeNEAT, so switching the overlay off and
    // on again keeps whichever radinfra categories were deselected.
    const layerVisible = new Map(layers.map((layer) => [layer.id, true]));
    const apply = () => {
        for (const layer of layers) {
            if (!map.getLayer(layer.id)) continue;
            const on = toggle.checked && layerVisible.get(layer.id);
            map.setLayoutProperty(layer.id, 'visibility', on ? 'visible' : 'none');
        }
        if (map.getLayer(RADINFRA_HOVER_LAYER_ID)) {
            map.setLayoutProperty(RADINFRA_HOVER_LAYER_ID, 'visibility',
                toggle.checked ? 'visible' : 'none');
        }
    };
    apply();

    // A style's layer array runs bottom-to-top, since that is drawing order, which
    // is the reverse of how radinfra.de lists the same categories in its own
    // legend. Only the display order is reversed — the layers keep the z-order the
    // style asked for.
    for (const layer of [...layers].reverse()) {
        container.appendChild(createCategoryRow({
            label: layer.label,
            color: layer.color,
            onToggle: (on) => {
                layerVisible.set(layer.id, on);
                apply();
            },
        }));
    }

    // The list is only worth its vertical space while the overlay is on — with 13
    // entries it otherwise pushes the rest of the legend off the panel.
    toggle.addEventListener('change', () => {
        container.classList.toggle('is-open', toggle.checked);
        apply();
    });
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

// Keep every radinfra.de link in the legend pointing at whatever is currently on
// screen, so clicking one opens the same place there rather than the front page.
function bindRadinfraDeepLinks(map) {
    const links = document.querySelectorAll('.radinfra-deeplink');
    if (!links.length) return;
    const update = () => {
        const center = map.getCenter();
        const href = radinfraURL({ zoom: map.getZoom(), lat: center.lat, lng: center.lng });
        for (const link of links) link.href = href;
    };
    map.on('moveend', update);
    update();
}

// radinfra ids identify a side of a way, not just the way: 'way/1460141762' but
// also 'way/1460141762/cycleway/left'. The deep link only takes the OSM way.
function osmWayId(radinfraId) {
    const match = /^way\/(\d+)/.exec(String(radinfraId ?? ''));
    return match ? match[1] : null;
}

// Tile geometry is clipped at tile edges, so this is the bounding box of the part
// of the way in the tiles that are loaded, not necessarily of the whole way. Good
// enough to frame it in radinfra.de.
function featureBounds(geometry) {
    if (!geometry) return null;
    const lines = geometry.type === 'MultiLineString' ? geometry.coordinates : [geometry.coordinates];
    let west = Infinity, south = Infinity, east = -Infinity, north = -Infinity;
    for (const line of lines) {
        for (const [lng, lat] of line) {
            if (lng < west) west = lng;
            if (lng > east) east = lng;
            if (lat < south) south = lat;
            if (lat > north) north = lat;
        }
    }
    return Number.isFinite(west) ? [west, south, east, north] : null;
}

const groupLabels = new Map(categoryGroups.map((g) => [g.id, g.label]));

function sideLabel(value) {
    if (!value) return '<em>keine</em>';
    return groupLabels.get(value) ?? value;
}

function popupHtml(props, radinfraHref) {
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
    const links = [];
    if (props.id) {
        links.push(`<a href="https://www.openstreetmap.org/way/${props.id}"
            target="_blank" rel="noopener">Way ${props.id} auf osm.org</a>`);
    }
    if (radinfraHref) {
        links.push(`<a href="${radinfraHref}" target="_blank" rel="noopener">bei radinfra.de ansehen</a>`);
    }
    const linkList = links.length ? `<p class="popup-links">${links.join('<br />')}</p>` : '';
    return `<h4>${name}</h4><table>${body}</table>${linkList}`;
}

// Most of the wait when zooming is the basemap decoding its tiles, not this archive,
// so the indicator follows the map's own load state rather than our source.
// `idle` is the definitive "nothing left to do" signal; areTilesLoaded() can be true
// while glyphs or the style are still arriving.
const LOADING_DELAY_MS = 250;

function bindLoadingIndicator(map) {
    const el = document.getElementById('loading');
    if (!el) return;
    let timer = null;
    // Tracked rather than probed: at `movestart` the previous tiles are still
    // loaded, so areTilesLoaded() reports true and the first seconds of the wait —
    // measured at about two, before `dataloading` even fires — would show nothing.
    let idle = true;

    const show = () => {
        idle = false;
        if (timer !== null || el.classList.contains('is-visible')) return;
        // Delayed, so a fast load never flashes the indicator for a moment.
        timer = window.setTimeout(() => {
            timer = null;
            if (!idle) el.classList.add('is-visible');
        }, LOADING_DELAY_MS);
    };

    const hide = () => {
        idle = true;
        if (timer !== null) {
            window.clearTimeout(timer);
            timer = null;
        }
        el.classList.remove('is-visible');
    };

    map.on('movestart', show);
    map.on('dataloading', show);
    map.on('idle', hide);
}

// Collapsing leaves the header, so the panel stays identifiable and re-openable
// while the map gets the space back. On a phone the legend covers the top half of
// the screen, which is where this matters.
function bindPanelToggle() {
    const panel = document.querySelector('.panel');
    const button = document.getElementById('panel-toggle');
    if (!panel || !button) return;

    const apply = (collapsed) => {
        // The minus/plus itself is CSS, keyed off this class; only the name is set here.
        panel.classList.toggle('is-collapsed', collapsed);
        button.setAttribute('aria-expanded', String(!collapsed));
        const label = collapsed ? 'Panel ausklappen' : 'Panel einklappen';
        button.setAttribute('aria-label', label);
        button.title = label;
    };

    button.addEventListener('click', () => {
        apply(button.getAttribute('aria-expanded') === 'true');
    });
}

function main() {
    // Bound before the map, so the panel folds away even if tiles or the style fail.
    bindPanelToggle();

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

    // Bound outside the load handler so the first tile load is covered too.
    bindLoadingIndicator(map);

    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    map.addControl(new maplibregl.ScaleControl({ maxWidth: 120 }));

    map.on('load', () => {
        map.addSource(SOURCE_ID, { type: 'vector', url: PMTILES_URL });

        // Only draws anything when the archive was built with --context; by default
        // build_tiles.py drops the ways classified 'no' altogether. Harmless when
        // the source layer is absent, and ready if a comparison view wants it.
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

        // Added before the category layers so the halo sits underneath them. The
        // filter matches nothing until something is hovered.
        map.addLayer({
            id: HOVER_LAYER_ID,
            type: 'line',
            source: SOURCE_ID,
            'source-layer': INFRA_SOURCE_LAYER,
            filter: ['==', ['get', 'id'], -1],
            // Butt caps for the same reason as the radinfra halo: round caps
            // overshoot each part and the overlap darkens at every join.
            layout: { 'line-cap': 'butt' },
            paint: {
                'line-color': hoverStyle.color,
                'line-width': hoverStyle.width,
                'line-opacity': hoverStyle.opacity,
                'line-blur': 1,
            },
        });

        const infraLayers = infraLayerSpecs();
        for (const spec of infraLayers) map.addLayer(spec);

        const bikeneatIds = infraLayers.map((spec) => spec.id);
        let radinfraIds = [];

        buildLegend(map);

        // Added last so the overlay draws on top of the BikeNEAT lines.
        addRadinfraLayers(map).then((layers) => {
            radinfraIds = layers.map((layer) => layer.id);
            buildRadinfraLegend(map, layers);
        });

        const popup = new maplibregl.Popup({ closeButton: true, maxWidth: '320px' });

        bindRadinfraDeepLinks(map);

        const present = (ids) => ids.filter((id) => map.getLayer(id));

        function query(point, ids) {
            const layers = present(ids);
            return layers.length ? map.queryRenderedFeatures(hitBox(point), { layers }) : [];
        }

        // One hovered feature at a time across both datasets. Querying both layer
        // sets in one call means the topmost drawn line wins, which is the overlay
        // where it is switched on.
        //
        // The two costs here are not comparable. Changing a filter repaints the whole
        // map, and running that on every mousemove is the entire cost of hovering:
        // sweeping the pointer across Berlin at z13 takes 142 ms a frame, and 16.7 ms
        // with the two setHoverFilter calls stubbed out — the same as with hovering
        // switched off altogether. The query itself is 0.3–1.5 ms and does not show up.
        //
        // So the query runs on the pointer, at most once a frame, which keeps the
        // cursor honest, and only the halo waits for the pointer to settle. That also
        // stops every way under a fast sweep from lighting up on the way past.
        let shown = null;
        let target = null;
        let point = null;
        let frame = null;
        let timer = null;

        const applyHover = () => {
            timer = null;
            if (target?.key === shown?.key) return;
            shown = target;
            const isRadinfra = Boolean(shown?.layerId.startsWith(RADINFRA.layerPrefix));
            setHoverFilter(map, HOVER_LAYER_ID, isRadinfra ? null : shown?.id ?? null, -1);
            setHoverFilter(map, RADINFRA_HOVER_LAYER_ID, isRadinfra ? shown?.id ?? null : null, '');
        };

        const runHoverQuery = () => {
            frame = null;
            const top = query(point, [...radinfraIds, ...bikeneatIds])[0] ?? null;
            const cursor = top ? 'pointer' : '';
            const canvas = map.getCanvas();
            if (canvas.style.cursor !== cursor) canvas.style.cursor = cursor;

            const next = top
                ? { key: `${top.layer.id}:${top.properties.id}`, layerId: top.layer.id, id: top.properties.id }
                : null;
            if (next?.key === target?.key) return;
            target = next;
            if (timer !== null) window.clearTimeout(timer);
            timer = window.setTimeout(applyHover, HOVER_DELAY_MS);
        };

        map.on('mousemove', (event) => {
            point = event.point;
            if (frame === null) frame = requestAnimationFrame(runHoverQuery);
        });

        map.on('mouseout', () => {
            if (frame !== null) cancelAnimationFrame(frame);
            if (timer !== null) window.clearTimeout(timer);
            frame = null;
            timer = null;
            target = null;
            shown = null;
            map.getCanvas().style.cursor = '';
            setHoverFilter(map, HOVER_LAYER_ID, null, -1);
            setHoverFilter(map, RADINFRA_HOVER_LAYER_ID, null, '');
        });

        // Queried the same way as the hover, so a click always acts on whatever the
        // halo is highlighting. A BikeNEAT way opens the popup; a radinfra way opens
        // radinfra.de itself, since this page has nothing to add about it.
        map.on('click', (event) => {
            const hits = query(event.point, [...radinfraIds, ...bikeneatIds]);
            const top = hits[0] ?? null;
            if (!top) {
                popup.remove();
                return;
            }

            const link = (wayId) => radinfraURL({
                zoom: Math.max(map.getZoom(), 16),
                lat: event.lngLat.lat,
                lng: event.lngLat.lng,
                wayId,
                bounds: featureBounds(top.geometry),
            });

            if (top.layer.id.startsWith(RADINFRA.layerPrefix)) {
                const wayId = osmWayId(top.properties.id);
                window.open(wayId ? link(wayId) : radinfraURL({
                    zoom: map.getZoom(),
                    lat: event.lngLat.lat,
                    lng: event.lngLat.lng,
                }), '_blank', 'noopener');
                return;
            }

            const href = top.properties.id && featureBounds(top.geometry)
                ? link(top.properties.id)
                : null;
            popup.setLngLat(event.lngLat).setHTML(popupHtml(top.properties, href)).addTo(map);
        });
    });

    map.on('error', (event) => {
        console.error('map error', event && event.error ? event.error : event);
    });
}

main();
