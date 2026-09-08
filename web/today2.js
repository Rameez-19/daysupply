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
  v2WriteUrl();
  loadToday2();
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
  v2FillPhcs();
  v2WriteUrl();
  loadToday2();
}

function v2OnDistrict() {
  const sel = document.getElementById('v2-district');
  v2District = sel ? sel.value : '';
  v2Phc = ''; v2PhcName = '';
  v2FillPhcs();
  v2WriteUrl();
  loadToday2();
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

function v2FillPhcs() {
  const sel = document.getElementById('v2-phc');
  if (!sel) return;
  if (!v2State || !v2District) {
    sel.innerHTML = `<option value="">${
      v2State ? 'Choose a district first' : 'Choose a state first'}</option>`;
    sel.disabled = true;
    v2Phc = ''; v2PhcName = '';
    return;
  }
  const rows = v2FacilitiesList();
  sel.disabled = false;
  // Every centre here reports, and the line count says how much, so a reader
  // can tell a well-covered centre from a thin one before choosing it.
  sel.innerHTML = `<option value="">All health centres (${rows.length})</option>`
    + rows.map(f =>
        `<option value="${v2Esc(f.facility_id)}">${v2Esc(f.name)} — `
        + `${f.lines} medicine${f.lines === 1 ? '' : 's'}</option>`).join('');
  sel.value = v2Phc;
  if (sel.value !== v2Phc) { v2Phc = ''; }
  v2PhcName = sel.selectedIndex > 0
    ? (v2FacilitiesList().find(f => f.facility_id === v2Phc) || {}).name || ''
    : '';
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
  return `
    <div class="v2-kpi ${missing ? 'unknown' : (tone || '')}">
      <div class="v2-kpi-value">${missing ? '—' : value}<span class="v2-kpi-unit">${missing ? '' : (unit || '')}</span></div>
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
      if (synced) {
        synced.className = 'last-synced';
        synced.textContent = `Last synced: ${new Date().toLocaleTimeString()}`;
      }
      return;
    }

    // One render path for all three resources: the server sends five tiles
    // already graded and worded, so this does not need to know whether it is
    // looking at medicines, beds or staff.
    host.innerHTML = d.kpis.map(k =>
      v2Kpi(k.value, k.unit, k.label, k.sub, k.tone, k.says)).join('');

    v2Distribution(d);
    v2Ranking(d);
    v2Quadrant(d);
    v2FourthPanel(d);

    if (synced) {
      synced.className = 'last-synced';
      synced.textContent = `Last synced: ${new Date().toLocaleTimeString()}`;
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
    if (note) note.textContent = 'Not enough here to compare districts.';
    return;
  }

  const pt = r => ({ x: r.x, y: r.y, r_: r });
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
            return [`${lab.x || 'x'}: ${r.x}%`, `${lab.y || 'y'}: ${r.y}%`];
          }
        } }
      },
      scales: {
        // The arrow points up on the vertical axis because up is more. It
        // pointed left once, which reads as "less is up".
        x: { title: { display: true, text: `${lab.x || ''} →`,
                      color: V2_INK, font: { size: 11 } },
             beginAtZero: true, grid: { color: V2_GRID },
             ticks: { color: V2_INK, font: { size: 10 }, callback: v => `${v}%` } },
        y: { title: { display: true, text: `${lab.y || ''} ↑`,
                      color: V2_INK, font: { size: 11 } },
             beginAtZero: true, grid: { color: V2_GRID },
             ticks: { color: V2_INK, font: { size: 10 }, callback: v => `${v}%` } }
      }
    }
  });

  const bad = rows.filter(r => r.critical).sort((a, b) => b.x - a.x || a.y - b.y);
  if (note) {
    note.innerHTML = bad.length
      ? `<strong>${v2n(bad.length)} in the danger corner</strong> — worst is `
        + `<strong>${v2Esc(bad[0].name)}${bad[0].sub ? ', ' + v2Esc(bad[0].sub) : ''}</strong>`
        + ` at ${bad[0].x}% against ${bad[0].y}%.`
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

// What an empty scope should say, in terms of the resource being viewed.
function v2EmptyMessage() {
  const what = v2Resource === 'bed' ? 'bed data'
             : v2Resource === 'personnel' ? 'staffing data'
             : 'medicines';
  return `No ${what} at this scope yet. Every health centre in the list does `
       + `report — try a wider area.`;
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
  if (v2Ready) { loadToday2(); return; }
  v2Ready = true;
  v2ReadUrl();
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
    v2FillPhcs();
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
