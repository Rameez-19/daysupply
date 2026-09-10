// Exercise the focus path with a stubbed Leaflet: does clicking a table row
// find its feature, restyle it, and move the map to it?
const fs = require('fs');
const acc = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const mp  = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));

let fitCalls = [], popupCalls = 0;
const shape = () => {
  const o = {
    style: {}, radius: 0,
    setStyle(s) { Object.assign(o.style, s); return o; },
    setRadius(r) { o.radius = r; return o; },
    bindPopup() { return o; }, addTo() { return o; },
    openPopup() { popupCalls++; return o; }, bringToFront() { return o; },
  };
  return o;
};
global.L = {
  map: () => ({ setView: () => {}, fitBounds: b => fitCalls.push(b),
                removeLayer: () => {}, invalidateSize: () => {} }),
  tileLayer: () => ({ addTo: () => {} }),
  layerGroup: () => ({ addTo: () => {} }),
  circleMarker: shape, polyline: shape,
  latLngBounds: pts => ({ pts, pad: () => ({ pts }) }),
};
const el = () => ({ innerHTML: '', textContent: '', hidden: false, style: {},
  dataset: {}, classList: { add(){}, remove(){}, toggle(){} },
  addEventListener(){}, getContext: () => ({}), parentElement: null,
  scrollIntoView(){}, closest: () => null });
global.document = { getElementById: () => el(), querySelector: () => el(),
  querySelectorAll: () => [], addEventListener(){}, createElement: el };
global.window = { location: { search: '', hash: '', pathname: '/' } };
global.history = { replaceState(){} };
global.panelLoading = () => ''; global.panelError = () => ''; global.panelEmpty = () => '';
global.currentState = '';
global.fetch = async () => ({ ok: true, json: async () => ({}) });

// Evaluated in the global context so the declarations become globals, as
// they are in a browser. new Function() would scope them to itself.
require('vm').runInThisContext(fs.readFileSync('web/map.js', 'utf8'));

// Draw both layers from the real payloads.
mapInstance = L.map();
mapData = mp; accessData = acc;
drawFlows(); drawAccess();

let fail = 0;
// Every key the ACCESS table renders must exist as a drawn feature.
for (const c of acc.cases) {
  const k = accessKey(c);
  if (!accessFeatures[k]) { console.log('access row has no map feature:', k); fail++; }
}
// Same for the FLOW table.
for (const f of (mp.flows || []).slice(0, 25)) {
  const k = flowKey(f);
  if (!flowFeatures[k]) { console.log('flow row has no map feature:', k); fail++; }
}
console.log(`  access features drawn: ${Object.keys(accessFeatures).length} (table shows ${acc.cases.length})`);
console.log(`  flow features drawn  : ${Object.keys(flowFeatures).length} (table shows ${Math.min(25,(mp.flows||[]).length)})`);

// Clicking a row must move the map and open its popup.
const key = accessKey(acc.cases[0]);
focusAccess(key);
console.log(`  focusAccess -> fitBounds calls: ${fitCalls.length}, popups: ${popupCalls}, selected: ${selectedKey === key}`);
if (!fitCalls.length || selectedKey !== key) { console.log('FOCUS DID NOT TAKE'); fail++; }

// Clicking the same row again clears it.
focusAccess(key);
if (selectedKey !== null) { console.log('second click did not clear'); fail++; }
else console.log('  second click clears the selection');

// The others must be faded, not hidden.
const others = Object.entries(accessFeatures).filter(([k]) => k !== key);
focusAccess(key);
const faded = others.filter(([, f]) => f.marker && f.marker.style.fillOpacity < 0.3).length;
console.log(`  faded rather than hidden: ${faded} of ${others.length}`);
if (faded !== others.length) fail++;

process.exit(fail ? 1 : 0);
