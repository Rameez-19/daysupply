// Today v2 — the supply chain as a scorecard.
//
// Self-contained on purpose. v1 stays exactly as it is until this replaces it,
// so nothing here touches app.js state: its own filters, its own fetch, its own
// chart instances.
//
// DESIGN NOTES, because the choices are not arbitrary:
//
// * Availability leads, and it is the only figure where higher is better. A
//   page that opens with "597 short" frames the reader as a firefighter; one
//   that opens with "78.6% available" frames them as a manager of a system.
//   Both numbers are on the tile.
// * Every headline is a rate with its count beside it. A count cannot be
//   compared between Telangana and Assam; a rate can.
// * Every rate carries a verdict, because a percentage nobody can grade has
//   not communicated anything. The verdicts come from the server so the
//   wording and the colour cannot drift apart.
// * Four visuals, four different questions, four different forms — when, what,
//   where, how robust. Nothing here is the same chart twice.
//
// COLOUR. The same two validated hues as the rest of the product: #b91c1c
// against #0369a1 scores dE 20.6 under protanopia and 29.6 in normal vision,
// both clear of the floors, and each clears 3:1 on the page surface. Grey is
// the de-emphasis, not a third category.

const V2_INK = '#334155';
const V2_GRID = '#e2e8f0';
const V2_URGENT = '#b91c1c';
const V2_CALM = '#94a3b8';
const V2_VITAL = '#b91c1c';
const V2_OTHER = '#0369a1';

let v2State = '';
let v2District = '';
let v2Phc = '';
let v2PhcName = '';
let v2VitalOnly = false;
let v2Resource = 'medicine';
let v2Charts = { timeline: null, medicines: null, quadrant: null, shock: null };
let v2LastData = null;

const v2n = v => (v === null || v === undefined ? '—' : v.toLocaleString('en-IN'));

function v2Esc(s) {
  return String(s === null || s === undefined ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ===== Filters =====

function v2SetResource(kind) {
  v2Resource = kind;
  for (const [id, on] of [['v2-res-med', kind === 'medicine'],
                          ['v2-res-bed', kind === 'bed'],
                          ['v2-res-staff', kind === 'personnel']]) {
    const b = document.getElementById(id);
    if (b) b.classList.toggle('active', on);
  }
  // Life-saving is a medicine classification. Leaving the toggle live on beds
  // or staff would offer a filter that silently does nothing.
  const vitalGroup = document.getElementById('v2-vital-group');
  if (vitalGroup) vitalGroup.style.display = kind === 'medicine' ? '' : 'none';
  // Leaving it set while the control is hidden would apply a filter the reader
  // cannot see and cannot turn off.
  if (kind !== 'medicine' && v2VitalOnly) {
    v2VitalOnly = false;
    const a = document.getElementById('v2-all');
    const v = document.getElementById('v2-vital');
    if (a) a.classList.add('active');
    if (v) v.classList.remove('active');
  }
  v2WriteUrl();
  loadToday2();
  v2FillPhcs();   // relabel: the counts are medicine counts
}

// Back to the whole network. The resource stays, because which resource you
// are looking at is the view rather than a filter on it — resetting that too
// would throw away the thing the reader most recently chose on purpose.
function v2Reset() {
  v2State = ''; v2District = ''; v2Phc = ''; v2PhcName = '';
  if (v2VitalOnly) v2SetVitalControls(false);
  v2FillStates();
  v2FillDistricts();
  v2WriteUrl();
  loadToday2();
  v2FillPhcs();
}

function v2SetVitalControls(on) {
  v2VitalOnly = on;
  const a = document.getElementById('v2-all');
  const v = document.getElementById('v2-vital');
  if (a) a.classList.toggle('active', !on);
  if (v) v.classList.toggle('active', on);
}

// Shown only when there is something to clear.
function v2SyncReset() {
  const b = document.getElementById('v2-reset');
  if (!b) return;
  const filtered = !!(v2State || v2District || v2Phc || v2VitalOnly);
  b.hidden = !filtered;
}

function v2SetVital(on) {
  v2VitalOnly = on;
  const a = document.getElementById('v2-all');
  const v = document.getElementById('v2-vital');
  if (a) a.classList.toggle('active', !on);
  if (v) v.classList.toggle('active', on);
  v2WriteUrl();
  loadToday2();
}

function v2OnState() {
  const sel = document.getElementById('v2-state');
  v2State = sel ? sel.value : '';
  // Clear everything below, or the page would keep filtering by a district and
  // a facility that are not in the newly chosen state.
  v2District = ''; v2Phc = ''; v2PhcName = '';
  v2FillDistricts();
  v2WriteUrl();
  loadToday2();
  v2FillPhcs();
}

function v2OnDistrict() {
  const sel = document.getElementById('v2-district');
  v2District = sel ? sel.value : '';
  v2Phc = ''; v2PhcName = '';
  v2WriteUrl();
  loadToday2();
  v2FillPhcs();
}

function v2OnPhc() {
  const sel = document.getElementById('v2-phc');
  v2Phc = sel ? sel.value : '';
  v2PhcName = (v2FacilitiesList().find(f => f.facility_id === v2Phc) || {}).name || '';
  v2WriteUrl();
  loadToday2();
}

// ===== Geography that actually reports =====
//
// The dropdowns used to be fed from the facility register: 200,438 facilities
// across 668 districts. Only 200 facilities in 116 districts report stock, so
// choosing a health centre had roughly a one-in-a-thousand chance of landing
// on one with data — and every other choice emptied the page. The filter was
// working; the choices could not.
//
// The whole reporting tree is 200 rows, so it is fetched once and the cascade
// is then instant and offline-safe, instead of a round trip per level.
let v2Geo = null;

async function v2LoadGeography() {
  if (v2Geo) return v2Geo;
  const res = await fetch('/api/v1/today2/geography');
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  v2Geo = await res.json();
  return v2Geo;
}

function v2StatesList() { return (v2Geo && v2Geo.states) || []; }

function v2DistrictsList() {
  const st = v2StatesList().find(x => x.state === v2State);
  return st ? st.districts : [];
}

function v2FacilitiesList() {
  const di = v2DistrictsList().find(x => x.district === v2District);
  return di ? di.facilities : [];
}

function v2FillStates() {
  const sel = document.getElementById('v2-state');
  if (!sel) return;
  const states = v2StatesList();
  const t = (v2Geo && v2Geo.totals) || {};
  sel.innerHTML =
    `<option value="">All India (${t.states || states.length} reporting states)</option>`
    + states.map(x =>
        `<option value="${v2Esc(x.state)}">${v2Esc(x.state)} — `
        + `${x.districts.length} district${x.districts.length === 1 ? '' : 's'}</option>`).join('');
  sel.value = v2State;
  if (sel.value !== v2State) { v2State = ''; sel.value = ''; }
}

function v2FillDistricts() {
  const sel = document.getElementById('v2-district');
  if (!sel) return;
  if (!v2State) {
    sel.innerHTML = '<option value="">All districts</option>';
    sel.disabled = true;
    v2District = '';
    return;
  }
  const rows = v2DistrictsList();
  sel.disabled = false;
  sel.innerHTML = `<option value="">All districts (${rows.length})</option>`
    + rows.map(d =>
        `<option value="${v2Esc(d.district)}">${v2Esc(d.district)} — `
        + `${d.facilities.length} centre${d.facilities.length === 1 ? '' : 's'}</option>`).join('');
  sel.value = v2District;
  if (sel.value !== v2District) { v2District = ''; sel.value = ''; }
}

// Every PHC in the district, not only the ones reporting stock.
//
// Restricting the list to reporting centres fixed the blank-page problem and
// created a worse one: it hid the register. These five states hold 7,092 PHCs
// and 200 of them report, so a list of 200 makes a national facility master
// look like a pilot of two hundred clinics.
//
// So the list shows all of them, in two groups, and says which is which. The
// register is real government data and worth seeing; the reporting footprint
// is the demo's, and pretending otherwise in either direction would be
// misleading. Picking a non-reporting centre is answered with a sentence
// rather than an empty page.
const v2PhcCache = {};

async function v2DistrictPhcs() {
  if (!v2State || !v2District) return [];
  const key = `${v2State}|${v2District}`;
  if (v2PhcCache[key]) return v2PhcCache[key];
  const reporting = new Map(v2FacilitiesList().map(f => [f.facility_id, f]));
  let all = [];
  try {
    const res = await fetch(`/api/v1/facilities?state=${encodeURIComponent(v2State)}`
      + `&district=${encodeURIComponent(v2District)}`);
    if (res.ok) all = (await res.json()).facilities || [];
  } catch (e) {
    // The reporting list alone is better than nothing.
  }
  const seen = new Set(all.map(f => f.facility_id));
  const merged = all.map(f => ({
    facility_id: f.facility_id,
    name: f.name,
    lines: (reporting.get(f.facility_id) || {}).lines || 0,
    reports: reporting.has(f.facility_id),
  }));
  // A reporting centre missing from the register page would be unreachable.
  for (const [id, f] of reporting) {
    if (!seen.has(id)) merged.push({ ...f, reports: true });
  }
  merged.sort((a, b) => Number(b.reports) - Number(a.reports)
                     || a.name.localeCompare(b.name));
  v2PhcCache[key] = merged;
  return merged;
}

function v2PhcIsReporting(id) {
  return v2FacilitiesList().some(f => f.facility_id === id);
}

async function v2FillPhcs() {
  const sel = document.getElementById('v2-phc');
  if (!sel) return;
  if (!v2State || !v2District) {
    sel.innerHTML = `<option value="">${
      v2State ? 'Choose a district first' : 'Choose a state first'}</option>`;
    sel.disabled = true;
    v2Phc = ''; v2PhcName = '';
    return;
  }
  sel.disabled = true;
  sel.innerHTML = '<option value="">Loading health centres…</option>';
  const rows = await v2DistrictPhcs();
  const on = rows.filter(f => f.reports);
  const off = rows.filter(f => !f.reports);
  // The line count is a medicine count, so it is only shown when medicines
  // are what you are looking at. Under Beds it read "Gangaram — 10 medicines",
  // which is a true number attached to the wrong question. All three resources
  // cover the same 200 centres, so "reporting" is the fact that carries over.
  const opt = f =>
    `<option value="${v2Esc(f.facility_id)}">${v2Esc(f.name)}`
    + (f.reports
        ? (v2Resource === 'medicine'
            ? ` — ${f.lines} medicine${f.lines === 1 ? '' : 's'}`
            : ' — reporting')
        : '')
    + `</option>`;

  sel.disabled = false;
  sel.innerHTML =
    `<option value="">All reporting centres (${on.length} of ${rows.length})</option>`
    + (on.length ? `<optgroup label="Reporting stock (${on.length})">`
        + on.map(opt).join('') + '</optgroup>' : '')
    + (off.length ? `<optgroup label="In the register, not yet reporting (${off.length})">`
        + off.map(opt).join('') + '</optgroup>' : '');

  sel.value = v2Phc;
  if (sel.value !== v2Phc) { v2Phc = ''; sel.value = ''; }
  v2PhcName = (rows.find(f => f.facility_id === v2Phc) || {}).name || '';
}

// The scope line is drawn separately so it can be redrawn once the facility's
// NAME is known. The scorecard now fetches in parallel with the dropdowns, so
// on a shared link the numbers arrive before the facility list does, and the
// line briefly had only the id to work with — it read "IN-129024" where it
// should read "Jail Dispensary Sirohi".
function v2RenderScope(d) {
  const scope = document.getElementById('v2-scope');
  if (!scope || !d) return;
  // Counts and the noun come from the payload. Reading `scorecard.tracked`
  // and hardcoding "medicines" worked only for medicines, and printed
  // "Showing — medicines across — health centres" for beds and staff.
  // A centre on the register that has not started reporting gets its own
  // line. Two paths reach here — the early guard when the geography is
  // already loaded, and the empty payload when a cold link beats it — and
  // they must say the same thing. Falling through printed "Showing 0
  // medicines at 0 health centres", which reads as a fault rather than as an
  // explanation, under a panel that was explaining it correctly.
  if (v2Phc && (d.empty || (v2Geo && !v2PhcIsReporting(v2Phc)))) {
    scope.innerHTML =
      `Showing <strong>${v2Esc(v2PhcName || v2Phc)}</strong>, `
      + `${v2Esc(v2District)} &mdash; a centre on the national register that `
      + `has not started reporting.`;
    return;
  }

  const sum = d.summary || {};
  const where = v2Phc
    ? `${v2Esc(v2PhcName || v2Phc)}, ${v2Esc(v2District)}`
    : v2District ? `${v2Esc(v2District)}, ${v2Esc(v2State)}`
    : (v2State ? v2Esc(v2State) : 'All India');
  const stayed = (d.scope && d.scope.district_level_panels) || [];
  const centres = sum.centres || 0;
  scope.innerHTML = `
    Showing <strong>${v2n(sum.primary)}</strong>
    ${v2VitalOnly && d.resource === 'medicine' ? 'life-saving ' : ''}${v2Esc(sum.noun || '')}
    ${v2Phc ? 'at' : 'across'}
    <strong>${v2n(centres)}</strong> health centre${centres === 1 ? '' : 's'}
    ${v2Phc ? '' : `in <strong>${v2n(sum.districts)}</strong> district${sum.districts === 1 ? '' : 's'}`}
    &mdash; <strong>${where}</strong>.`
    + (stayed.length ? `<div class="v2-scope-caveat">
         Whether stock could absorb a surge is a district-level measure &mdash;
         it pools what every centre in the district holds &mdash; so
         &ldquo;${stayed.join('&rdquo; and &ldquo;')}&rdquo; still
         ${stayed.length === 1 ? 'covers' : 'cover'} the whole district.
       </div>` : '');
}

// ===== The scorecard =====

// A percentage can legitimately be null — a scope with no life-saving lines
// has no life-saving availability, and one with nothing tracked has no
// availability at all. That was reaching the page as the literal text "null%".
// Handled here, once, so no tile added later can reintroduce it.
function v2Kpi(value, unit, label, sub, tone, says) {
  const missing = value === null || value === undefined || value === '';
  const tip = String(says || '').replace(/<[^>]+>/g, '').replace(/"/g, '&quot;');
  return `
    <div class="v2-kpi ${missing ? 'unknown' : (tone || '')}" title="${tip}">
      <div class="v2-kpi-value">${missing ? '—' : (typeof value === 'number' ? v2n(value) : value)}<span class="v2-kpi-unit">${missing ? '' : (unit || '')}</span></div>
      <div class="v2-kpi-delta" data-label="${v2Esc(label)}"></div>
      <div class="v2-kpi-label">${label}</div>
      <div class="v2-kpi-sub">${sub || ''}</div>
      <div class="v2-kpi-says">${says || ''}</div>
    </div>`;
}

function loadToday2() {
  const host = document.getElementById('v2-kpis');
  if (!host) return;
  host.innerHTML = panelLoading('Grading the network…');
  v2Fetch();
}

async function v2Fetch() {
  const host = document.getElementById('v2-kpis');
  const synced = document.getElementById('v2-synced');
  const scope = document.getElementById('v2-scope');

  // A centre that does not report cannot have a scorecard, so do not ask the
  // server for one — answer it here, immediately.
  if (v2Phc && v2Geo && !v2PhcIsReporting(v2Phc)) {
    v2ShowNonReporting();
    return;
  }

  try {
    const q = new URLSearchParams();
    if (v2State) q.set('state', v2State);
    if (v2District) q.set('district', v2District);
    if (v2Phc) q.set('phc', v2Phc);
    // The life-saving split is a medicine classification; beds and staff have
    // no equivalent, so it is not sent for them.
    if (v2VitalOnly && v2Resource === 'medicine') q.set('vital_only', 'true');
    q.set('resource', v2Resource);
    const res = await fetch(`/api/v1/today2?${q}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const d = await res.json();
    if (d.error) throw new Error(d.error);

    v2LastData = d;
    v2RenderScope(d);

    if (d.empty || !(d.kpis || []).length) {
      host.innerHTML = panelEmpty(v2EmptyMessage());
      v2ClearCharts();
      v2InheritedPanels(d);
      if (synced) {
        synced.className = 'last-synced';
        synced.textContent = `Updated ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} · refreshes every 5 min`;
      }
      return;
    }

    // One render path for all three resources: the server sends five tiles
    // already graded and worded, so this does not need to know whether it is
    // looking at medicines, beds or staff.
    host.innerHTML = d.kpis.map(k =>
      v2Kpi(k.value, k.unit, k.label, k.sub, k.tone, k.says)).join('');
    v2Deltas(d);
    v2Tasks();

    v2Distribution(d);
    v2Ranking(d);
    v2Quadrant(d);
    v2FourthPanel(d);
    v2InheritedPanels(d);

    if (synced) {
      synced.className = 'last-synced';
      synced.textContent = `Updated ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} · refreshes every 5 min`;
    }
  } catch (e) {
    if (host) host.innerHTML = panelError(e.message, 'loadToday2');
    if (synced) {
      synced.className = 'last-synced sync-failed';
      synced.textContent = `Not synced — ${e.message}`;
    }
  }
}

function v2ClearCharts() {
  for (const k of Object.keys(v2Charts)) {
    if (v2Charts[k]) { v2Charts[k].destroy(); v2Charts[k] = null; }
  }
  for (const id of ['v2-timeline-note', 'v2-medicines-note',
                    'v2-quadrant-note', 'v2-shock-note']) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = '';
  }
}

// ===== Four charts, three resources, one implementation =====
//
// The server sends the same four blocks — distribution, ranking, quadrant, and
// a fourth panel — whatever resource is selected, along with the titles and
// axis labels. So these functions never ask what they are drawing. The
// alternative was three near-identical copies of each chart, which is three
// places for the same bug to be fixed twice and missed once.

function v2SetHeading(id, noteId, label) {
  const h = document.getElementById(id);
  const n = document.getElementById(noteId);
  if (h && label && label.title) h.textContent = label.title;
  if (n && label && label.note) n.textContent = label.note;
}

// A distribution over ordered buckets. Emphasis, not a colour ramp: the first
// two buckets are the ones that need action, and five hues from one family
// fail colour-blind separation anyway.
function v2Distribution(d) {
  const el = document.getElementById('v2-timeline');
  const note = document.getElementById('v2-timeline-note');
  const lab = (d.labels || {}).distribution || {};
  v2SetHeading('v2-t1', 'v2-n1', lab);
  if (!el || typeof Chart === 'undefined') return;

  const rows = d.distribution || [];
  if (v2Charts.timeline) { v2Charts.timeline.destroy(); v2Charts.timeline = null; }
  if (!rows.length) {
    if (note) note.textContent = 'Nothing to show at this scope.';
    return;
  }
  const urgent = rows.filter(r => r.sort_order <= 2).reduce((a, r) => a + r.n, 0);
  const total = rows.reduce((a, r) => a + r.n, 0);

  v2Charts.timeline = new Chart(el.getContext('2d'), {
    type: 'bar',
    data: {
      labels: rows.map(r => r.bucket),
      datasets: [{
        label: 'Count',
        data: rows.map(r => r.n),
        backgroundColor: rows.map(r => r.sort_order <= 2 ? V2_URGENT : V2_CALM),
        borderRadius: 4, borderSkipped: 'bottom', maxBarThickness: 60
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: {
          label: c => `${v2n(c.parsed.y)} (${Math.round(100 * c.parsed.y / total)}%)`
        } }
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: V2_INK, font: { size: 11 } } },
        y: { beginAtZero: true, grid: { color: V2_GRID },
             ticks: { color: V2_INK, font: { size: 11 }, callback: v => v2n(v) } }
      }
    }
  });

  if (note) {
    const worst = rows.find(r => r.sort_order <= 2 && r.n > 0);
    note.innerHTML = urgent
      ? `<strong>${v2n(urgent)} in the two most urgent bands</strong> — `
        + `${Math.round(100 * urgent / total)}% of everything counted here`
        + `${worst ? `, ${v2Esc(worst.bucket.toLowerCase())}` : ''}.`
      : `Nothing falls in the two most urgent bands at this scope.`;
  }
}

// A ranked horizontal bar. `flag` is the one thing worth colouring — a
// life-saving medicine, an over-capacity centre, a badly vacant role.
function v2Ranking(d) {
  const el = document.getElementById('v2-medicines');
  const note = document.getElementById('v2-medicines-note');
  const lab = (d.labels || {}).ranking || {};
  v2SetHeading('v2-t2', 'v2-n2', lab);
  if (!el || typeof Chart === 'undefined') return;

  const rows = d.ranking || [];
  if (v2Charts.medicines) { v2Charts.medicines.destroy(); v2Charts.medicines = null; }
  if (!rows.length) {
    if (note) note.textContent = 'Nothing to rank at this scope.';
    return;
  }

  v2Charts.medicines = new Chart(el.getContext('2d'), {
    type: 'bar',
    data: {
      labels: rows.map(r => r.name),
      datasets: [{
        label: lab.unit || 'Count',
        data: rows.map(r => r.value),
        backgroundColor: rows.map(r => r.flag ? V2_VITAL : V2_OTHER),
        borderRadius: 3, maxBarThickness: 20
      }]
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: {
          label: c => `${v2n(c.parsed.x)} ${lab.unit || ''}`.trim(),
          afterLabel: c => rows[c.dataIndex].sub || ''
        } }
      },
      scales: {
        x: { beginAtZero: true, grid: { color: V2_GRID },
             ticks: { color: V2_INK, font: { size: 11 } } },
        y: { grid: { display: false }, ticks: { color: V2_INK, font: { size: 11 } } }
      }
    }
  });

  const top = rows[0];
  const flagged = rows.filter(r => r.flag).length;
  if (note) {
    note.innerHTML = `<strong>${v2Esc(top.name)}</strong> leads with `
      + `${v2n(top.value)} ${v2Esc(lab.unit || '')}`
      + `${top.sub ? ` (${v2Esc(top.sub)})` : ''}`
      + (flagged ? `. ${flagged} of these ${rows.length} are flagged.` : '.');
  }
}

// Two measures that mislead apart and separate when plotted together.
function v2Quadrant(d) {
  const el = document.getElementById('v2-quadrant');
  const note = document.getElementById('v2-quadrant-note');
  const lab = (d.labels || {}).quadrant || {};
  v2SetHeading('v2-t3', 'v2-n3', lab);
  if (!el || typeof Chart === 'undefined') return;

  const rows = d.quadrant || [];
  if (v2Charts.quadrant) { v2Charts.quadrant.destroy(); v2Charts.quadrant = null; }
  if (!rows.length) {
    if (note) note.textContent = lab.empty
      || 'Not enough here to compare.';
    return;
  }

  const pt = r => ({ x: r.x, y: r.y, r_: r });
  // Both axes used to be hardcoded as percentages, which was true while this
  // plotted districts by vacancy against attendance. Staffing now plots the
  // size of the establishment up the y-axis, and a count of 450 sanctioned
  // posts rendered as "450%". The unit travels with the label instead.
  const xu = lab.x_unit === undefined ? '%' : lab.x_unit;
  const yu = lab.y_unit === undefined ? '%' : lab.y_unit;
  v2Charts.quadrant = new Chart(el.getContext('2d'), {
    type: 'scatter',
    data: {
      datasets: [
        { label: lab.critical || 'Needs attention',
          data: rows.filter(r => r.critical).map(pt),
          backgroundColor: V2_URGENT, pointRadius: 6, pointHoverRadius: 9 },
        { label: lab.other || 'Other districts',
          data: rows.filter(r => !r.critical).map(pt),
          backgroundColor: V2_CALM, pointRadius: 4, pointHoverRadius: 7 }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: 'top', align: 'end',
                  labels: { color: V2_INK, boxWidth: 8, boxHeight: 8,
                            usePointStyle: true, font: { size: 11 } } },
        tooltip: { callbacks: {
          title: items => {
            const r = items[0].raw.r_;
            return r.sub ? `${r.name}, ${r.sub}` : r.name;
          },
          label: c => {
            const r = c.raw.r_;
            return [`${lab.x || 'x'}: ${v2n(r.x)}${xu}`,
                    `${lab.y || 'y'}: ${v2n(r.y)}${yu}`];
          }
        } }
      },
      scales: {
        // The arrow points up on the vertical axis because up is more. It
        // pointed left once, which reads as "less is up".
        x: { title: { display: true, text: `${lab.x || ''} →`,
                      color: V2_INK, font: { size: 11 } },
             beginAtZero: true, grid: { color: V2_GRID },
             ticks: { color: V2_INK, font: { size: 10 },
                      callback: v => `${v2n(v)}${xu}` } },
        y: { title: { display: true, text: `${lab.y || ''} ↑`,
                      color: V2_INK, font: { size: 11 } },
             beginAtZero: true, grid: { color: V2_GRID },
             ticks: { color: V2_INK, font: { size: 10 },
                      callback: v => `${v2n(v)}${yu}` } }
      }
    }
  });

  const bad = rows.filter(r => r.critical).sort((a, b) => b.x - a.x || a.y - b.y);
  if (note) {
    note.innerHTML = bad.length
      ? `<strong>${v2n(bad.length)} ${v2Esc(lab.flagged || 'in the danger corner')}</strong> — worst is `
        + `<strong>${v2Esc(bad[0].name)}${bad[0].sub ? ', ' + v2Esc(bad[0].sub) : ''}</strong>`
        + ` at ${v2n(bad[0].x)}${xu} against ${v2n(bad[0].y)}${yu}.`
      : `None here falls in the danger corner.`;
  }
}

// Medicines have a fourth question — could the network take a shock — that
// beds and staff have no equivalent for. Rather than invent one, those two get
// the provenance panel, which matters more for them anyway: occupancy and
// attendance are modelled, and a reader would otherwise assume both were
// counted.
function v2FourthPanel(d) {
  const el = document.getElementById('v2-shock');
  const note = document.getElementById('v2-shock-note');
  const box = el ? el.parentElement : null;
  if (v2Charts.shock) { v2Charts.shock.destroy(); v2Charts.shock = null; }

  const rows = d.absorption || [];
  if (!rows.length) {
    if (box) box.style.display = 'none';
    v2SetHeading('v2-t4', 'v2-n4', {
      title: 'What these numbers are based on',
      note: 'Nothing on this page is presented as counted when it is modelled.'
    });
    if (note) {
      note.innerHTML = `<p class="section-note">`
        + `${v2Esc((d.labels || {}).provenance || '')}</p>`;
    }
    return;
  }

  if (box) box.style.display = '';
  v2SetHeading('v2-t4', 'v2-n4', {
    title: 'Could the network take a shock?',
    note: 'How much of each district’s medicine stock could meet a sudden '
        + 'jump in demand using supplies already nearby, before any new order '
        + 'could arrive.'
  });
  if (!el || typeof Chart === 'undefined') return;

  const said = { 2: 'If demand doubled', 3: 'If demand tripled',
                 5: 'If demand went 5× higher' };
  v2Charts.shock = new Chart(el.getContext('2d'), {
    type: 'bar',
    data: {
      labels: rows.map(r => said[r.multiplier] || `${r.multiplier}× demand`),
      datasets: [{
        label: 'Could cope',
        data: rows.map(r => r.pct),
        backgroundColor: rows.map(r => r.pct < 35 ? V2_URGENT
                                     : r.pct < 70 ? '#ea580c' : '#15803d'),
        borderRadius: 4, maxBarThickness: 26
      }]
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: {
          label: c => {
            const r = rows[c.dataIndex];
            return `${r.pct}% could cope (${v2n(r.holds)} of ${v2n(r.total)})`;
          }
        } }
      },
      scales: {
        x: { beginAtZero: true, max: 100, grid: { color: V2_GRID },
             ticks: { color: V2_INK, font: { size: 11 }, callback: v => `${v}%` } },
        y: { grid: { display: false }, ticks: { color: V2_INK, font: { size: 11 } } }
      }
    }
  });

  const r3 = ((d.grades || {}).resilience) || {};
  if (note) {
    note.innerHTML =
      `<span class="panel-verdict ${r3.tone || 'warn'}">${v2Esc(r3.says || '')}</span>`
      + `<p class="section-note" style="margin-top:8px">`
      + `${v2n(d.transfer_only)} medicines would run out before a new order `
      + `could physically reach the health centre. Ordering cannot fix those — `
      + `only moving stock that already exists.</p>`;
  }
}

// Drawn from both the early guard and again after the facility list arrives,
// because on a cold link the panel would otherwise name the centre by its id:
// "IN-156093 is in the national facility register" where it should read
// "Allapalli".
function v2ShowNonReporting() {
  const host = document.getElementById('v2-kpis');
  const synced = document.getElementById('v2-synced');
  if (host) host.innerHTML = panelEmpty(v2EmptyMessage());
  v2ClearCharts();
  v2RenderScope({ empty: true });
  if (synced) {
    synced.className = 'last-synced';
    synced.textContent = `Updated ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} · refreshes every 5 min`;
  }
}

// What an empty scope should say.
//
// "No data" is the least useful thing a page can say, because it does not tell
// the reader whether they chose badly, whether the thing is broken, or whether
// the answer is genuinely nothing. A centre in the register that has not
// started reporting is a different situation from a reporting centre with
// nothing short, and the two must not read the same.
function v2EmptyMessage() {
  const what = v2Resource === 'bed' ? 'bed data'
             : v2Resource === 'personnel' ? 'staffing data'
             : 'stock data';

  if (v2Phc && !v2PhcIsReporting(v2Phc)) {
    const reporting = v2FacilitiesList().length;
    return `<strong>${v2Esc(v2PhcName || v2Phc)}</strong> is in the national `
      + `facility register but is not yet reporting ${what}. It is one of `
      + `200,438 health facilities on file; the ${reporting} reporting `
      + `centre${reporting === 1 ? '' : 's'} in this district are grouped at `
      + `the top of the list.`;
  }
  return `No ${what} at this scope yet. Try a wider area.`;
}

// ===== Filters live in the URL =====
//
// Two reasons, one of them the important one.
//
// The obvious one: "look at Shahdara" becomes a link somebody can send. A
// filtered view that cannot be shared has to be re-created by hand at the
// other end, and usually is not.
//
// The one that mattered here: it makes the filters *verifiable*. Headless
// Chrome cannot click a dropdown, so without this the only proof the controls
// work would be that the endpoint behaves when called directly — which is a
// test of the backend, not of the page. With the state in the URL the whole
// chain can be loaded and checked in a real browser.
function v2ReadUrl() {
  const q = new URLSearchParams(window.location.search || '');
  v2State = q.get('state') || '';
  v2District = q.get('district') || '';
  v2Phc = q.get('phc') || '';
  v2VitalOnly = q.get('vital') === '1';
  const res = q.get('resource');
  if (res === 'bed' || res === 'personnel') v2Resource = res;
  for (const [id, on] of [['v2-res-med', v2Resource === 'medicine'],
                          ['v2-res-bed', v2Resource === 'bed'],
                          ['v2-res-staff', v2Resource === 'personnel']]) {
    const b = document.getElementById(id);
    if (b) b.classList.toggle('active', on);
  }
  const vitalGroup = document.getElementById('v2-vital-group');
  if (vitalGroup) vitalGroup.style.display = v2Resource === 'medicine' ? '' : 'none';
  const a = document.getElementById('v2-all');
  const v = document.getElementById('v2-vital');
  if (a) a.classList.toggle('active', !v2VitalOnly);
  if (v) v.classList.toggle('active', v2VitalOnly);
}

function v2WriteUrl() {
  v2SyncReset();
  v2SyncGlobals();
  const q = new URLSearchParams();
  if (v2State) q.set('state', v2State);
  if (v2District) q.set('district', v2District);
  if (v2Phc) q.set('phc', v2Phc);
  if (v2VitalOnly) q.set('vital', '1');
  if (v2Resource !== 'medicine') q.set('resource', v2Resource);
  const qs = q.toString();
  history.replaceState(null, '',
    `${window.location.pathname}${qs ? '?' + qs : ''}${window.location.hash}`);
}


// Initialise once, when the view is first opened.
let v2Ready = false;
async function initToday2() {
  if (v2Ready) {
    loadToday2();
    if (typeof loadSurgeBanner === 'function') loadSurgeBanner('v2-surge-banner');
    return;
  }
  v2Ready = true;
  v2ReadUrl();
  v2SyncGlobals();
  if (typeof loadSurgeBanner === 'function') loadSurgeBanner('v2-surge-banner');
  // Arriving on a shared filtered link is a change of state too, even though
  // nothing was clicked — without this the button stayed hidden on exactly the
  // page most likely to need it.
  v2SyncReset();
  const before = `${v2State}|${v2District}|${v2Phc}`;

  // The scorecard does not wait for the dropdowns. It needs only the scope,
  // which came from the URL, so it starts now and renders the moment it lands.
  // Chained behind three geography lookups it was four round trips of blank
  // page before a single number appeared.
  loadToday2();

  // One fetch for the whole reporting tree, then every dropdown is filled
  // from memory — no round trip per cascade level.
  try {
    await v2LoadGeography();
    v2FillStates();
    v2FillDistricts();
    await v2FillPhcs();
    // Names are known now. Redraw if the scope is a centre that does not
    // report, so the panel says "Allapalli" rather than "IN-156093".
    if (v2Phc && !v2PhcIsReporting(v2Phc)) {
      v2ShowNonReporting();
      return;
    }
    // A link naming a scope that does not report would otherwise leave the
    // dropdown blank while the numbers stayed filtered by it. The fill
    // functions clear anything they cannot honour, so compare and refetch.
    if (before !== `${v2State}|${v2District}|${v2Phc}`) {
      v2WriteUrl();
      loadToday2();
    } else {
      // The scope held; only the facility's NAME is new, so redraw the line.
      v2RenderScope(v2LastData);
    }
  } catch (e) {
    for (const id of ['v2-state', 'v2-district', 'v2-phc']) {
      const sel = document.getElementById(id);
      if (sel) sel.innerHTML = '<option value="">Geography unavailable</option>';
    }
  }
}


// ===== Inherited from Today v1 =====
//
// Four panels lived only on the old Today and nowhere else in the product: a
// single graded verdict for the whole network, a ranked "what should we do
// first", the Vital / Essential / Desirable split, and the surge banner. They
// moved here when that page was retired, renderers unchanged, reading the
// same payload keys — scorecard() now supplies them from the query it already
// ran. All four are medicine questions (the verdict grades on Vital
// stock-outs, the steps are transfers, VEN is a medicine classification), so
// they show for medicines and hide for beds and staff, exactly as the
// life-saving toggle does.

function verdictBar(d) {
  const m = d.medicines || {};
  const tracked = m.tracked || 0, short = m.below_reorder || 0;
  const vital = m.vital_short || 0, out = m.stocked_out || 0;
  const pct = tracked ? Math.round(100 * short / tracked) : 0;
  const absorb3 = (d.absorption || []).find(a => a.multiplier === 3.0);

  // Graded from the numbers, not chosen. Vital lines at zero is the line
  // between "gaps" and "under strain", because a Vital stock-out is the one a
  // patient feels the same day.
  let level, label;
  if (out > 0 && vital > 0) { level = 'bad';  label = 'Under strain'; }
  else if (short > 0)       { level = 'warn'; label = 'Holding, with gaps'; }
  else                      { level = 'ok';   label = 'Holding'; }

  // Four chips a reader takes in at a glance, every visit. The full sentence
  // is still there for anyone who switches on Explain.
  const chip = (n, l) => `<span class="verdict-chip"><strong>${n}</strong> ${l}</span>`;
  return `
    <div class="verdict ${level}">
      <div class="verdict-main">
        <span class="verdict-label">${label}</span>
        <div class="verdict-chips">
          ${chip(pct + '%', 'running low')}
          ${chip(vital.toLocaleString('en-IN'), 'life-saving short')}
          ${chip(out.toLocaleString('en-IN'), 'completely out')}
          ${absorb3 ? chip(absorb3.pct + '%', 'could take a 3× surge') : ''}
        </div>
        <p class="verdict-line explain-only">
          <strong>${pct}%</strong> of the medicines we track are running low
          &mdash; <strong>${vital}</strong> of them life-saving, and
          <strong>${out}</strong> already completely out.
          ${absorb3 ? `If demand suddenly tripled, only <strong>${absorb3.pct}%</strong> of district medicine stocks could cope.` : ''}
        </p>
      </div>
      <div class="verdict-aside">
        <span class="verdict-figure">${(d.transfer_only || 0).toLocaleString('en-IN')}</span>
        <span class="verdict-short">can't wait for an order</span>
        <span class="verdict-caption">medicines would run out before a new
          order could reach the health centre.<br>
          Ordering cannot fix these &mdash; only moving stock that already exists.</span>
      </div>
    </div>`;
}

// ===== Change since the last visit =====
// This page is opened every day, so the useful question is "what moved".
// Each scope keeps one snapshot per calendar day on this browser; the tiles
// compare against the most recent earlier day, or against this morning's
// first look if there is no earlier day yet.
function v2Deltas(d) {
  let store = {};
  const key = `stockpulse.kpi.${v2Resource}.${v2VitalOnly ? 'v' : 'a'}.${v2State}|${v2District}|${v2Phc}`;
  try { store = JSON.parse(localStorage.getItem(key) || '{}'); } catch (e) { store = {}; }
  const today = new Date().toISOString().slice(0, 10);
  const now = {};
  (d.kpis || []).forEach(k => { if (typeof k.value === 'number') now[k.label] = k.value; });
  const days = Object.keys(store).filter(x => x !== today).sort();
  let base = null, since = '';
  if (days.length) {
    base = store[days[days.length - 1]].values;
    const dd = new Date(days[days.length - 1]);
    since = days[days.length - 1] === new Date(Date.now() - 864e5).toISOString().slice(0, 10)
      ? 'since yesterday' : `since ${dd.toLocaleDateString([], { day: 'numeric', month: 'short' })}`;
  } else if (store[today] && Date.now() - store[today].ts > 15 * 60 * 1000) {
    base = store[today].values;
    since = `since ${new Date(store[today].ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
  }
  if (!store[today]) store[today] = { ts: Date.now(), values: now };
  const keep = Object.keys(store).sort().slice(-7);
  const trimmed = {}; keep.forEach(x => { trimmed[x] = store[x]; });
  try { localStorage.setItem(key, JSON.stringify(trimmed)); } catch (e) { /* private mode */ }
  document.querySelectorAll('#v2-kpis .v2-kpi-delta').forEach(el => {
    const label = el.dataset.label;
    if (!base || !(label in base) || !(label in now)) { el.textContent = ''; return; }
    const diff = Math.round((now[label] - base[label]) * 10) / 10;
    el.textContent = diff === 0 ? `no change ${since}` : `${diff > 0 ? '▲' : '▼'} ${Math.abs(diff).toLocaleString('en-IN')} ${since}`;
    el.className = 'v2-kpi-delta' + (diff === 0 ? ' flat' : '');
  });
}

// ===== Today's work =====
// Buttons with live counts, each opening the place where the work is done.
// This replaces reading a paragraph to find out what to do.
async function v2Tasks() {
  const host = document.getElementById('v2-tasks');
  if (!host) return;
  const q = new URLSearchParams();
  if (v2State) q.set('state', v2State);
  if (v2District) q.set('district', v2District);
  if (v2Phc) q.set('phc', v2Phc);
  const scope = q.toString();
  const get = async (url) => { try { const r = await fetch(url); return r.ok ? r.json() : null; } catch (e) { return null; } };
  const [aq, sig, rv] = await Promise.all([
    get(`/api/v1/action-queue?summary=true&${scope}`),
    get(`/api/v1/surge/signals?count_only=true&${scope}`),
    get(`/api/v1/review-queue?${scope}`),
  ]);
  const s = (aq && aq.summary) || {};
  const tasks = [
    ['bad', s.escalate, 'Escalate', 'nothing routine will fix', "v2Go('action-view','escalate-list')"],
    ['move', s.transfer, 'Approve transfers', 'stock that already exists', "v2Go('action-view','transfers-full')"],
    ['order', s.order, 'Place orders', 'arrive in time if ordered now', "v2Go('action-view','order-list')"],
    ['warn', sig ? sig.early_warning_districts : null, 'Early warnings', sig && sig.month ? `districts, ${sig.month}` : 'districts', "v2Go('plan-view','surge-signal-list')"],
    ['check', rv && rv.items ? rv.items.length : null, 'Check held reports', 'the model was not sure', "v2Go('capture-view','review-list')"],
  ];
  host.innerHTML = tasks.map(([cls, n, label, sub, go]) => `
    <button class="task ${cls} ${n ? '' : 'zero'}" onclick="${go}">
      <span class="task-n">${n === null || n === undefined ? '—' : Number(n).toLocaleString('en-IN')}</span>
      <span class="task-label">${label}</span>
      <span class="task-sub">${sub}</span>
    </button>`).join('');
}

function v2Go(view, anchorId) {
  switchTab(view);
  setTimeout(() => {
    const el = document.getElementById(anchorId);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, 350);
}
window.v2Go = v2Go;

function stepCard(n, title, body, action) {
  return `
    <div class="step">
      <div class="step-number">${n}</div>
      <div class="step-body">
        <div class="step-title">${title}</div>
        <p class="step-text">${body}</p>
        ${action || ''}
      </div>
    </div>`;
}

function renderNextSteps(d, hostId = 'v2-next-steps') {
  const host = document.getElementById(hostId);
  if (!host) return;

  const q = d.action_queue || {};
  const worst = (d.worst_districts || [])[0];
  const n = v => (v || 0).toLocaleString('en-IN');
  const steps = [];

  if ((q.recommended || 0) > 0) {
    steps.push(stepCard(steps.length + 1,
      'Approve the transfers that are already worked out',
      `<strong>${n(q.recommended)} transfers</strong> would move `
      + `<strong>${n(q.units)} units</strong> of medicine from places that have `
      + `spare stock to places that have run short &mdash; ${n(q.vital)} of them `
      + `life-saving. Nothing has to be bought, and the stock already exists.`,
      `<button class="btn btn-primary" onclick="switchTab('action-view')">
         Open the queue</button>`));
  }

  if ((d.transfer_only || 0) > 0) {
    steps.push(stepCard(steps.length + 1,
      `${n(d.transfer_only)} of them cannot wait for an order`,
      `These would run out <strong>before a delivery could physically reach the `
      + `health centre</strong>. Placing an order will not save them. Moving `
      + `stock that already exists is the only thing that works, which is why `
      + `they are at the top of the queue.`));
  }

  if (worst) {
    steps.push(stepCard(steps.length + 1,
      `Start with ${worst.district}, ${worst.state}`,
      `<strong>${worst.vital_short} life-saving `
      + `${worst.vital_short === 1 ? 'medicine is' : 'medicines are'} running low</strong>`
      + `${worst.stocked_out
          ? ` and ${worst.stocked_out} ${worst.stocked_out === 1 ? 'is' : 'are'} `
            + `completely out`
          : ''}`
      + ` &mdash; more than any other district. The map shows which neighbours `
      + `are close enough to help.`,
      `<button class="btn btn-secondary" onclick="switchTab('map-view')">
         See it on the map</button>`));
  }

  host.innerHTML = steps.length
    ? steps.join('')
    : panelEmpty('Nothing needs a decision right now. No medicine in this area '
                 + 'is below the level where it should be reordered.');
}

function renderVen(d, hostId = 'v2-ven') {
  const host = document.getElementById(hostId);
  if (!host) return;
  const rows = d.ven_breakdown || [];
  if (!rows.length) {
    host.innerHTML = panelEmpty('No medicines are being tracked here yet.');
    return;
  }
  const why = {
    Vital: 'Life-saving &mdash; death or serious harm if these run out',
    Essential: 'Significant harm if these run out',
    Desirable: 'Useful, but not life-threatening if short'
  };
  host.innerHTML = rows.map(r => `
    <div class="ven-row">
      <div class="ven-head">
        <span class="ven-name">${r.ven_class}</span>
        <span class="ven-figure"><strong>${r.short}</strong> of ${r.tracked} running low</span>
      </div>
      <div class="ven-track">
        <div class="ven-fill ${r.ven_class === 'Vital' ? 'vital' : ''}"
             style="width:${Math.min(100, r.pct)}%"></div>
      </div>
      <div class="ven-note">${r.pct}% &middot; ${why[r.ven_class] || ''}</div>
    </div>`).join('');
}

const V2_INHERITED = ['v2-verdict', 'v2-next-steps-section', 'v2-ven-section'];

function v2InheritedPanels(d) {
  const medicine = d && d.resource === 'medicine' && !d.empty;
  for (const id of V2_INHERITED) {
    const el = document.getElementById(id);
    if (el) el.hidden = !medicine;
  }
  if (!medicine) return;
  const v = document.getElementById('v2-verdict');
  if (v) v.innerHTML = verdictBar(d);
  renderNextSteps(d, 'v2-next-steps');
  renderVen(d, 'v2-ven');
}

// Today v2 owns the scope now. Every other view still reads the globals the
// old filter bar used to set, so they are kept in step here.
function v2SyncGlobals() {
  currentState = v2State;
  currentDistrict = v2District;
  currentPHC = v2Phc;
  currentPHCName = v2PhcName;
}
