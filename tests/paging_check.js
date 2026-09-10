const fs = require('fs');
const acc = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const mp  = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const html = {};
const el = id => ({ id, set innerHTML(v){ html[id] = v; }, get innerHTML(){ return html[id] || ''; },
  textContent: '', hidden: false, style: {}, dataset: {},
  classList: { add(){}, remove(){}, toggle(){} }, addEventListener(){},
  getContext: () => ({}), parentElement: null, scrollIntoView(){}, closest: () => null });
global.document = { getElementById: id => el(id), querySelector: () => el('q'),
  querySelectorAll: () => [], addEventListener(){}, createElement: () => el('n') };
global.L = { map: () => ({ setView(){}, fitBounds(){}, removeLayer(){}, invalidateSize(){} }),
  tileLayer: () => ({ addTo(){} }), layerGroup: () => ({ addTo(){} }),
  circleMarker: () => ({ setStyle(){return this;}, setRadius(){return this;},
    bindPopup(){return this;}, addTo(){return this;}, openPopup(){}, bringToFront(){} }),
  polyline: () => ({ setStyle(){return this;}, bindPopup(){return this;},
    addTo(){return this;}, openPopup(){}, bringToFront(){} }),
  latLngBounds: p => ({ pad: () => p }) };
global.window = { location: { search: '', hash: '', pathname: '/' } };
global.history = { replaceState(){} };
global.panelLoading = () => ''; global.panelError = () => ''; global.panelEmpty = () => '';
global.currentState = ''; global.fetch = async () => ({ ok: true, json: async () => ({}) });
require('vm').runInThisContext(fs.readFileSync('web/map.js', 'utf8'));

mapInstance = L.map(); mapData = mp; accessData = acc;
const countFlow = () => (html['flow-table'] || '').split('data-focus="flow"').length - 1;
const countAcc  = () => (html['access-table'] || '').split('data-focus="access"').length - 1;

let fail = 0;
const check = (label, got, want) => {
  const ok = got === want;
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}: ${got} (expected ${want})`);
  if (!ok) fail++;
};

drawFlowTable();
check('flows, first page', countFlow(), 25);
showMoreFlows();
check('flows, after "show 25 more"', countFlow(), 50);
showMoreFlows();
check('flows, after another', countFlow(), 75);
showMoreFlows(true);
check('flows, after "show all"', countFlow(), mp.flows.length);
// Past the end must clamp, not overrun.
showMoreFlows();
check('flows, clamped at the total', countFlow(), mp.flows.length);
console.log('  control gone once all shown:', !(html['flow-table'] || '').includes('table-more'));
if ((html['flow-table'] || '').includes('table-more')) fail++;

drawAccessTable();
check('shortages, first page', countAcc(), 25);
showMoreAccess(true);
check('shortages, after "show all"', countAcc(), acc.all_cases.length);

// Every row must still resolve on the map after paging — the whole point of
// paging is that the later rows are clickable too.
drawAccess();
const keys = [...(html['access-table'] || '').matchAll(/data-key="([^"]+)" data-focus="access"/g)].map(m => m[1]);
const missing = keys.filter(k => !accessFeatures[k]);
check('paged-in rows that resolve on the map', keys.length - missing.length, keys.length);

process.exit(fail ? 1 : 0);
