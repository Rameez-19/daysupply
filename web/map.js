// The supply chain drawn as geography.
//
// Two layers over the same 116 district nodes, because they answer different
// questions and colouring one by the other would be a lie:
//
//   RISK      — what is short right now, weighted by Vital lines.
//   HEADROOM  — could this district absorb a 3x spike from stock it already
//               holds? A district can be green on risk and red on headroom;
//               that is the interesting case, and it is invisible in a table.
//
// Over both, the recommended cross-district moves as arcs. Arc thickness is
// units moved, not distance — distance is already the length of the line, and
// encoding it twice would double-count it.

let mapInstance = null;
let districtLayer = null;
let flowLayer = null;
let mapData = null;
let accessLayer = null;
let currentLayer = 'risk';
let flowsVisible = true;

// India, framed so the demo states are all on screen at once.
const INDIA_CENTRE = [22.0, 80.0];
const INDIA_ZOOM = 5;

// Risk is ordinal, not continuous: a district short on a Vital line is a
// different kind of problem from one short on a Desirable line, not a worse
// amount of the same problem.
function riskTone(d) {
  if ((d.stocked_out || 0) > 0) return { c: '#b91c1c', label: 'Stocked out' };
  if ((d.vital_short || 0) > 0) return { c: '#ea580c', label: 'Vital short' };
  if ((d.short || 0) > 0) return { c: '#d97706', label: 'Below reorder' };
  return { c: '#15803d', label: 'Holding' };
}

// Headroom is continuous, so it gets a ramp. The 35% break is the same one the
// executive view uses for the absorption bars.
function headroomTone(d) {
  const p = d.pct_hold;
  if (p === null || p === undefined) return { c: '#94a3b8', label: 'Not computed' };
  if (p < 35) return { c: '#b91c1c', label: 'Could not absorb 3x' };
  if (p < 70) return { c: '#d97706', label: 'Partial headroom' };
  return { c: '#15803d', label: 'Absorbs 3x' };
}

function toneFor(d) {
  return currentLayer === 'risk' ? riskTone(d) : headroomTone(d);
}

// Radius carries scale so a district tracking 4 lines does not read as loudly
// as one tracking 40. Square root, because area is what the eye compares.
function radiusFor(d) {
  return 5 + Math.sqrt(d.tracked || 1) * 1.9;
}

function flowColour(sev) {
  return sev === 1 ? '#b91c1c' : sev === 2 ? '#ea580c' : '#0369a1';
}

function esc(s) {
  return String(s === null || s === undefined ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

async function loadMap() {
  const host = document.getElementById('supply-map');
  const summary = document.getElementById('map-summary');
  if (!host) return;

  if (typeof L === 'undefined') {
    if (summary) {
      summary.innerHTML = panelError(
        'The map library did not load. Everything else on this page works '
        + 'offline; the map needs the network once.', 'loadMap');
    }
    return;
  }

  if (summary) summary.innerHTML = panelLoading('Placing districts…');

  try {
    const scope = currentState ? `?state=${encodeURIComponent(currentState)}` : '';
    const res = await fetch(`/api/v1/map${scope}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    mapData = await res.json();
    // Scope changed, so the nearest-help answer is stale too.
    accessData = null;

    const s = mapData.summary || {};
    if (summary) {
      summary.innerHTML = mapSummaryCards();
    }

    if (!mapInstance) {
      mapInstance = L.map('supply-map', { scrollWheelZoom: false })
        .setView(INDIA_CENTRE, INDIA_ZOOM);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 12, minZoom: 4,
        attribution: '&copy; OpenStreetMap contributors'
      }).addTo(mapInstance);
    }

    drawDistricts();
    drawFlows();
    drawLegend();
    drawFlowTable();

    // A layer named in the URL is a shareable view — "look at nearest help" —
    // and the only way this can be checked without a click.
    const wanted = new URLSearchParams(window.location.search || '').get('layer');
    if (wanted === 'access' || wanted === 'headroom') {
      setMapLayer(wanted);
    }

    // Frame what is actually in scope, so picking one state does not leave the
    // reader looking at an empty ocean.
    const pts = (mapData.districts || [])
      .filter(d => d.lat && d.lon).map(d => [d.lat, d.lon]);
    if (pts.length) {
      mapInstance.fitBounds(L.latLngBounds(pts).pad(0.15));
    }
    // The container is sized by CSS after the view becomes visible, so Leaflet
    // has to be told to re-measure or it renders into a zero-height box.
    setTimeout(() => mapInstance && mapInstance.invalidateSize(), 80);
  } catch (e) {
    if (summary) summary.innerHTML = panelError(e.message, 'loadMap');
  }
}

// Written once and used twice: on first load, and again when returning from
// the Nearest help layer, which replaces the summary with its own.
function mapSummaryCards() {
  const s = (mapData && mapData.summary) || {};
  return `
        <div class="map-summary-row">
          <div class="map-stat">
            <div class="map-stat-value">${(s.districts || 0).toLocaleString('en-IN')}</div>
            <div class="map-stat-label">districts mapped</div>
          </div>
          <div class="map-stat">
            <div class="map-stat-value danger">${(s.districts_with_vital_short || 0).toLocaleString('en-IN')}</div>
            <div class="map-stat-label">short on a Vital line</div>
          </div>
          <div class="map-stat">
            <div class="map-stat-value danger">${(s.fragile_districts || 0).toLocaleString('en-IN')}</div>
            <div class="map-stat-label">cannot absorb a 3&times; spike</div>
          </div>
          <div class="map-stat">
            <div class="map-stat-value">${(s.units_in_flight || 0).toLocaleString('en-IN')}</div>
            <div class="map-stat-label">units in recommended moves</div>
          </div>
        </div>
        <p class="section-note">${esc(s.headline || '')} ${esc(s.flow_headline || '')}</p>`;
}

function drawDistricts() {
  if (!mapInstance || !mapData) return;
  if (districtLayer) mapInstance.removeLayer(districtLayer);

  districtLayer = L.layerGroup();
  for (const d of mapData.districts || []) {
    if (!d.lat || !d.lon) continue;
    const tone = toneFor(d);
    const hold = (d.pct_hold === null || d.pct_hold === undefined)
      ? 'not computed' : `${d.pct_hold}% of positions hold`;

    L.circleMarker([d.lat, d.lon], {
      radius: radiusFor(d), color: tone.c, weight: 1.5,
      fillColor: tone.c, fillOpacity: 0.55
    }).bindPopup(`
      <div class="map-popup">
        <strong>${esc(d.district)}</strong>
        <div class="map-popup-sub">${esc(d.state)} &middot; ${(d.reporting_facilities || 0)} reporting facilities</div>
        <table>
          <tr><td>Stock lines tracked</td><td>${(d.tracked || 0).toLocaleString('en-IN')}</td></tr>
          <tr><td>Below reorder</td><td>${(d.short || 0).toLocaleString('en-IN')}</td></tr>
          <tr><td>Vital short</td><td>${(d.vital_short || 0).toLocaleString('en-IN')}</td></tr>
          <tr><td>Stocked out</td><td>${(d.stocked_out || 0).toLocaleString('en-IN')}</td></tr>
          <tr><td>Units on hand</td><td>${(d.units_on_hand || 0).toLocaleString('en-IN')}</td></tr>
          <tr><td>Absorbs 3&times; spike</td><td>${hold}</td></tr>
        </table>
      </div>`).addTo(districtLayer);
  }
  districtLayer.addTo(mapInstance);
}

function drawFlows() {
  if (!mapInstance || !mapData) return;
  if (flowLayer) mapInstance.removeLayer(flowLayer);
  if (!flowsVisible) { flowLayer = null; return; }

  flowLayer = L.layerGroup();
  const maxUnits = Math.max(1, ...(mapData.flows || []).map(f => f.units || 0));

  for (const f of mapData.flows || []) {
    if (!f.from_lat || !f.to_lat) continue;
    const weight = 1 + 5 * Math.sqrt((f.units || 0) / maxUnits);
    L.polyline([[f.from_lat, f.from_lon], [f.to_lat, f.to_lon]], {
      color: flowColour(f.severity), weight, opacity: 0.65
    }).bindPopup(`
      <div class="map-popup">
        <strong>${esc(f.from_district)} &rarr; ${esc(f.to_district)}</strong>
        <div class="map-popup-sub">${esc(f.from_state)} &rarr; ${esc(f.to_state)}</div>
        <table>
          <tr><td>Units</td><td>${(f.units || 0).toLocaleString('en-IN')}</td></tr>
          <tr><td>Separate moves</td><td>${f.moves || 0}</td></tr>
          <tr><td>Vital among them</td><td>${f.vital_moves || 0}</td></tr>
          <tr><td>Distance</td><td>${f.km} km</td></tr>
        </table>
      </div>`).addTo(flowLayer);
  }
  flowLayer.addTo(mapInstance);
}

function drawLegend() {
  const host = document.getElementById('map-legend');
  if (!host) return;
  // The access layer answers a different question, so it gets its own legend
  // rather than a recolouring of the district one.
  if (currentLayer === 'access') {
    host.innerHTML = `
      <div class="legend-block">
        <span class="legend-title">Distance to the nearest supply</span>
        <span class="legend-key"><i style="background:#15803d"></i>Within ${ACCESS_NEAR} km</span>
        <span class="legend-key"><i style="background:#ea580c"></i>${ACCESS_NEAR} to ${ACCESS_FAR} km</span>
        <span class="legend-key"><i style="background:#b91c1c"></i>Over ${ACCESS_FAR} km</span>
        <span class="legend-note">Circle size is the population the centre serves.</span>
      </div>
      <div class="legend-block">
        <span class="legend-title">Points</span>
        <span class="legend-key"><i style="background:#0369a1"></i>Centre that has the medicine</span>
        <span class="legend-note">Straight-line distance, so every figure is a floor.</span>
      </div>`;
    return;
  }

  const keys = currentLayer === 'risk'
    ? [['#b91c1c', 'Stocked out'], ['#ea580c', 'Vital short'],
       ['#d97706', 'Below reorder'], ['#15803d', 'Holding']]
    : [['#b91c1c', 'Could not absorb 3&times;'], ['#d97706', 'Partial headroom'],
       ['#15803d', 'Absorbs 3&times;'], ['#94a3b8', 'Not computed']];

  host.innerHTML = `
    <div class="legend-block">
      <span class="legend-title">${currentLayer === 'risk' ? 'District risk' : 'Absorption headroom'}</span>
      ${keys.map(([c, l]) => `<span class="legend-key"><i style="background:${c}"></i>${l}</span>`).join('')}
      <span class="legend-note">Circle size is stock lines tracked.</span>
    </div>
    <div class="legend-block">
      <span class="legend-title">Recommended moves</span>
      <span class="legend-key"><i style="background:#b91c1c"></i>Receiver stocked out</span>
      <span class="legend-key"><i style="background:#ea580c"></i>Receiver critical</span>
      <span class="legend-key"><i style="background:#0369a1"></i>Receiver below reorder</span>
      <span class="legend-note">Line thickness is units moved.</span>
    </div>`;
}

function drawFlowTable() {
  const host = document.getElementById('flow-table');
  if (!host) return;
  const rows = (mapData && mapData.flows) || [];
  if (!rows.length) {
    host.innerHTML = panelEmpty(
      'No cross-district move is recommended in this scope. Where a shortage '
      + 'exists, the nearest surplus is inside the same district.');
    return;
  }
  host.innerHTML = `<div class="table-scroll">
    <table class="scenario-table">
      <thead><tr>
        <th>From</th><th>To</th><th>Units</th><th>Moves</th>
        <th>Vital</th><th>Distance</th>
      </tr></thead>
      <tbody>${rows.slice(0, 25).map(f => `
        <tr class="${f.severity === 1 ? 'row-critical' : ''}">
          <td><strong>${esc(f.from_district)}</strong><br><span class="muted">${esc(f.from_state)}</span></td>
          <td><strong>${esc(f.to_district)}</strong><br><span class="muted">${esc(f.to_state)}</span></td>
          <td>${(f.units || 0).toLocaleString('en-IN')}</td>
          <td>${f.moves || 0}</td>
          <td>${f.vital_moves || 0}</td>
          <td>${f.km} km</td>
        </tr>`).join('')}
      </tbody></table></div>
    ${rows.length > 25 ? `<p class="section-note">Showing the 25 largest of ${rows.length} moves.</p>` : ''}`;
}

async function setMapLayer(layer) {
  currentLayer = layer;
  const q = new URLSearchParams(window.location.search || '');
  if (layer === 'risk') q.delete('layer'); else q.set('layer', layer);
  const qs = q.toString();
  history.replaceState(null, '',
    `${window.location.pathname}${qs ? '?' + qs : ''}${window.location.hash}`);
  for (const [id, on] of [['layer-risk', layer === 'risk'],
                          ['layer-headroom', layer === 'headroom'],
                          ['layer-access', layer === 'access']]) {
    const b = document.getElementById(id);
    if (b) b.classList.toggle('active', on);
  }

  // Risk and headroom recolour the same district nodes. Nearest help replaces
  // them with facility-level points and lines, because "where can a patient be
  // treated" is not a district-level question — a district average cannot tell
  // anyone which clinic to drive to.
  const isAccess = layer === 'access';
  // The standing note describes district centroids and arc thickness. The
  // access layer draws neither, so leaving it up would explain the wrong map.
  const prov = document.querySelector('#map-view .section-note');
  if (prov) prov.hidden = isAccess;
  for (const [id, show] of [['access-section', isAccess],
                            ['flow-section', !isAccess]]) {
    const el = document.getElementById(id);
    if (el) el.hidden = !show;
  }
  const flowToggle = document.getElementById('show-flows');
  if (flowToggle && flowToggle.parentElement) {
    flowToggle.parentElement.style.display = isAccess ? 'none' : '';
  }

  if (isAccess) {
    const summary = document.getElementById('map-summary');
    if (districtLayer) { mapInstance.removeLayer(districtLayer); districtLayer = null; }
    if (flowLayer) { mapInstance.removeLayer(flowLayer); flowLayer = null; }
    try {
      if (summary && !accessData) summary.innerHTML = panelLoading('Finding the nearest supply for each shortage…');
      await loadAccess();
      if (summary) summary.innerHTML = accessSummaryCards();
      drawAccess();
      drawAccessTable();
      drawLegend();
      const pts = (accessData.all_cases || [])
        .filter(c => c.lat && c.lon).map(c => [c.lat, c.lon]);
      if (pts.length && mapInstance) mapInstance.fitBounds(L.latLngBounds(pts).pad(0.15));
    } catch (e) {
      if (summary) summary.innerHTML = panelError(e.message, "setMapLayer('access')");
    }
    return;
  }

  if (accessLayer) { mapInstance.removeLayer(accessLayer); accessLayer = null; }
  if (mapData) {
    const summary = document.getElementById('map-summary');
    if (summary) summary.innerHTML = mapSummaryCards();
    drawDistricts();
    drawFlows();
  }
  drawLegend();
}

function toggleFlows() {
  const box = document.getElementById('show-flows');
  flowsVisible = box ? box.checked : true;
  drawFlows();
}

// ===== Nearest help =====
//
// The layer that answers the question a person at the counter has, rather than
// the one a manager has: this centre does not have the medicine, so where is
// the nearest one that does, and how far?
//
// It is also the sharpest form of alert in the product. "126 Vital lines below
// reorder" is a statistic. "Koni is out of Oxytocin and the nearest supply is
// 353 km away" is an emergency with an address, and Oxytocin is what stops a
// postpartum haemorrhage.
//
// A source has to be above its OWN reorder point to count. Pulling from a
// facility that is already short just moves the shortage somewhere else.
//
// Distances are straight-line. Every number here is therefore a floor — the
// real journey is longer — and the page says that rather than implying a
// travel time we cannot compute without a road network.

let accessData = null;

const ACCESS_NEAR = 25;
const ACCESS_FAR = 100;

function accessTone(km) {
  if (km === null || km === undefined) return { c: '#7f1d1d', label: 'No source' };
  if (km > ACCESS_FAR) return { c: '#b91c1c', label: `Over ${ACCESS_FAR} km` };
  if (km > ACCESS_NEAR) return { c: '#ea580c', label: `${ACCESS_NEAR}–${ACCESS_FAR} km` };
  return { c: '#15803d', label: `Within ${ACCESS_NEAR} km` };
}

async function loadAccess() {
  if (accessData) return accessData;
  const scope = currentState ? `?state=${encodeURIComponent(currentState)}` : '';
  const res = await fetch(`/api/v1/access${scope}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  accessData = await res.json();
  return accessData;
}

function drawAccess() {
  if (!mapInstance || !accessData) return;
  if (accessLayer) mapInstance.removeLayer(accessLayer);
  accessLayer = L.layerGroup();

  for (const c of accessData.all_cases || []) {
    if (!c.lat || !c.lon) continue;
    const tone = accessTone(c.km);

    // The line to help is drawn first so the clinic marker sits on top of it.
    if (c.source_lat && c.source_lon) {
      L.polyline([[c.lat, c.lon], [c.source_lat, c.source_lon]], {
        color: tone.c, weight: c.km > ACCESS_FAR ? 2.5 : 1.5,
        opacity: 0.55, dashArray: '4 4'
      }).addTo(accessLayer);
      L.circleMarker([c.source_lat, c.source_lon], {
        radius: 3, color: '#0369a1', fillColor: '#0369a1',
        fillOpacity: 0.9, weight: 0
      }).bindPopup(`<div class="map-popup">
          <strong>${esc(c.source_name)}</strong>
          <div class="map-popup-sub">Has ${esc(c.item_name)} &middot; ${(c.source_on_hand || 0).toLocaleString('en-IN')} ${esc(c.unit || '')}</div>
        </div>`).addTo(accessLayer);
    }

    // Size by the population behind the clinic: a shortage at a centre serving
    // 80,000 people is not the same event as one serving 2,000.
    const pop = c.population || 0;
    L.circleMarker([c.lat, c.lon], {
      radius: 5 + Math.min(9, Math.sqrt(pop) / 90),
      color: tone.c, weight: 1.5, fillColor: tone.c, fillOpacity: 0.6
    }).bindPopup(`
      <div class="map-popup">
        <strong>${esc(c.facility_name)}</strong>
        <div class="map-popup-sub">${esc(c.district)}, ${esc(c.state)}
          ${pop ? ` &middot; serves ${pop.toLocaleString('en-IN')} people` : ''}</div>
        <table>
          <tr><td>Out of</td><td>${esc(c.item_name)}</td></tr>
          <tr><td>On hand</td><td>${(c.on_hand || 0).toLocaleString('en-IN')} ${esc(c.unit || '')}</td></tr>
          <tr><td>Days left</td><td>${c.days_of_cover === null ? '—' : c.days_of_cover}</td></tr>
          <tr><td>Nearest supply</td><td>${esc(c.source_name || 'none found')}</td></tr>
          <tr><td>Distance</td><td>${c.km === null ? '—' : c.km + ' km'}</td></tr>
        </table>
      </div>`).addTo(accessLayer);
  }
  accessLayer.addTo(mapInstance);
}

function drawAccessTable() {
  const host = document.getElementById('access-table');
  const note = document.getElementById('access-note');
  if (!host || !accessData) return;
  const s = accessData.summary || {};

  if (note) {
    note.innerHTML = `${esc(s.headline || '')} ${esc(s.detail || '')}
      <strong>${esc(s.alert || '')}</strong>
      Distances are straight-line between two real coordinates, so each one is
      a floor — the road journey is longer.`;
  }

  const rows = accessData.cases || [];
  if (!rows.length) {
    host.innerHTML = panelEmpty('Nothing is short in this area.');
    return;
  }
  host.innerHTML = `<div class="table-scroll">
    <table class="scenario-table">
      <thead><tr>
        <th>Health centre</th><th>Out of</th>
        <th class="net-num">Days left</th>
        <th>Nearest supply</th>
        <th class="net-num">Distance</th>
        <th class="net-num">People served</th>
      </tr></thead>
      <tbody>${rows.map(c => `
        <tr class="${c.km > ACCESS_FAR ? 'row-critical' : ''}">
          <td><strong>${esc(c.facility_name)}</strong><br>
            <span class="muted">${esc(c.district)}, ${esc(c.state)}</span></td>
          <td>${esc(c.item_name)}</td>
          <td class="net-num">${c.days_of_cover === null ? '—' : c.days_of_cover}</td>
          <td>${esc(c.source_name || 'none')}<br>
            <span class="muted">${esc(c.source_district || '')}</span></td>
          <td class="net-num"><strong>${c.km === null ? '—' : c.km + ' km'}</strong></td>
          <td class="net-num muted">${(c.population || 0).toLocaleString('en-IN')}</td>
        </tr>`).join('')}
      </tbody></table></div>`;
}

function accessSummaryCards() {
  const s = (accessData && accessData.summary) || {};
  const bands = (accessData && accessData.bands) || [];
  const far = bands.find(b => b.sort_order === 3);
  const none = bands.find(b => b.sort_order === 4);
  return `
    <div class="map-summary-row">
      <div class="map-stat">
        <div class="map-stat-value danger">${(s.cases || 0).toLocaleString('en-IN')}</div>
        <div class="map-stat-label">life-saving shortages</div>
      </div>
      <div class="map-stat">
        <div class="map-stat-value danger">${(s.people || 0).toLocaleString('en-IN')}</div>
        <div class="map-stat-label">people behind them</div>
      </div>
      <div class="map-stat">
        <div class="map-stat-value">${s.median_km === null || s.median_km === undefined ? '—' : s.median_km + ' km'}</div>
        <div class="map-stat-label">to the nearest supply, typically</div>
      </div>
      <div class="map-stat">
        <div class="map-stat-value danger">${far ? far.n : 0}</div>
        <div class="map-stat-label">further than ${ACCESS_FAR} km from help</div>
      </div>
    </div>
    <p class="section-note">${esc(s.detail || '')}
      ${none && none.n === 0
        ? 'Not one of them is unsolvable — every shortage has stock somewhere in the network.'
        : ''}</p>`;
}
