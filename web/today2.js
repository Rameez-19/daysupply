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

async function v2OnState() {
  const sel = document.getElementById('v2-state');
  v2State = sel ? sel.value : '';
  // Clear everything below, or the page would keep filtering by a district and
  // a facility that are not in the newly chosen state.
  v2District = ''; v2Phc = ''; v2PhcName = '';
  await v2LoadDistricts();
  await v2LoadPhcs();
  v2WriteUrl();
  loadToday2();
}

async function v2OnDistrict() {
  const sel = document.getElementById('v2-district');
  v2District = sel ? sel.value : '';
  v2Phc = ''; v2PhcName = '';
  await v2LoadPhcs();
  v2WriteUrl();
  loadToday2();
}

function v2OnPhc() {
  const sel = document.getElementById('v2-phc');
  v2Phc = sel ? sel.value : '';
  v2PhcName = sel && sel.selectedIndex > 0
    ? sel.options[sel.selectedIndex].textContent.trim() : '';
  v2WriteUrl();
  loadToday2();
}

async function v2LoadStates() {
  const sel = document.getElementById('v2-state');
  if (!sel) return;
  try {
    const res = await fetch('/api/v1/states');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const { states } = await res.json();
    if (!Array.isArray(states)) throw new Error('states missing from response');
    sel.innerHTML = `<option value="">All India (${states.length} states)</option>`
      + states.map(s => `<option value="${v2Esc(s.state)}">${v2Esc(s.state)}</option>`).join('');
  } catch (e) {
    sel.innerHTML = '<option value="">States unavailable</option>';
  }
}

async function v2LoadDistricts() {
  const sel = document.getElementById('v2-district');
  if (!sel) return;
  if (!v2State) {
    sel.innerHTML = '<option value="">All districts</option>';
    return;
  }
  try {
    const res = await fetch(`/api/v1/districts?state=${encodeURIComponent(v2State)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const { districts } = await res.json();
    sel.innerHTML = `<option value="">All districts (${districts.length})</option>`
      + districts.map(d => `<option value="${v2Esc(d.district)}">${v2Esc(d.display_name || d.district)}</option>`).join('');
  } catch (e) {
    sel.innerHTML = '<option value="">Districts unavailable</option>';
  }
}

// A facility list needs both a state and a district; the endpoint returns 422
// without them. Until both are chosen the control says what it needs rather
// than sitting empty and looking broken.
async function v2LoadPhcs() {
  const sel = document.getElementById('v2-phc');
  if (!sel) return;
  if (!v2State || !v2District) {
    sel.innerHTML = `<option value="">${
      v2State ? 'Choose a district first' : 'Choose a state first'}</option>`;
    sel.disabled = true;
    return;
  }
  sel.disabled = false;
  try {
    const res = await fetch(`/api/v1/facilities?state=${encodeURIComponent(v2State)}`
      + `&district=${encodeURIComponent(v2District)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const { facilities } = await res.json();
    sel.innerHTML = `<option value="">All health centres (${facilities.length})</option>`
      + facilities.map(f =>
          `<option value="${v2Esc(f.facility_id)}">${v2Esc(f.name)}</option>`).join('');
  } catch (e) {
    sel.innerHTML = '<option value="">Health centres unavailable</option>';
  }
}

// The scope line is drawn separately so it can be redrawn once the facility's
// NAME is known. The scorecard now fetches in parallel with the dropdowns, so
// on a shared link the numbers arrive before the facility list does, and the
// line briefly had only the id to work with — it read "IN-129024" where it
// should read "Jail Dispensary Sirohi".
function v2RenderScope(d) {
  const scope = document.getElementById('v2-scope');
  if (!scope || !d) return;
  const s = d.scorecard || {};
  const where = v2Phc
    ? `${v2Esc(v2PhcName || v2Phc)}, ${v2Esc(v2District)}`
    : v2District ? `${v2Esc(v2District)}, ${v2Esc(v2State)}`
    : (v2State ? v2Esc(v2State) : 'All India');
  const stayed = (d.scope && d.scope.district_level_panels) || [];
  scope.innerHTML = `
    Showing <strong>${v2n(s.tracked)}</strong>
    ${v2VitalOnly ? 'life-saving ' : ''}medicines
    ${v2Phc ? 'at' : 'across'}
    <strong>${v2n(s.facilities)}</strong> health centre${s.facilities === 1 ? '' : 's'}
    ${v2Phc ? '' : `in <strong>${v2n(s.districts)}</strong> districts`}
    &mdash; <strong>${where}</strong>.`
    + (stayed.length ? `<div class="v2-scope-caveat">
         Whether stock could absorb a surge is a district-level measure &mdash;
         it pools what every centre in the district holds &mdash; so
         &ldquo;${stayed.join('&rdquo; and &ldquo;')}&rdquo; still
         ${stayed.length === 1 ? 'covers' : 'cover'} the whole district.
       </div>` : '');
}

// ===== The scorecard =====

function v2Kpi(value, unit, label, sub, tone, says) {
  return `
    <div class="v2-kpi ${tone || ''}">
      <div class="v2-kpi-value">${value}<span class="v2-kpi-unit">${unit || ''}</span></div>
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

  // Beds and staff are not yet graded on this page. Saying so beats showing
  // medicine numbers under a "Beds" heading, which would be a lie the reader
  // could not detect.
  if (v2Resource !== 'medicine') {
    const what = v2Resource === 'bed' ? 'Beds' : 'Staff';
    if (host) {
      host.innerHTML = panelEmpty(
        `${what} are not graded on this page yet — only medicines are. `
        + `The ${what.toLowerCase()} figures are on the Today page, under `
        + `"How are medicines, beds and staff holding up?".`);
    }
    if (scope) scope.innerHTML = '';
    v2ClearCharts();
    return;
  }

  try {
    const q = new URLSearchParams();
    if (v2State) q.set('state', v2State);
    if (v2District) q.set('district', v2District);
    if (v2Phc) q.set('phc', v2Phc);
    if (v2VitalOnly) q.set('vital_only', 'true');
    const res = await fetch(`/api/v1/today2?${q}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const d = await res.json();
    if (d.error) throw new Error(d.error);

    const g = d.grades || {};
    const s = d.scorecard || {};

    v2LastData = d;
    v2RenderScope(d);

    // Five tiles: availability, failure, forward risk, equity, resilience.
    host.innerHTML =
        v2Kpi(g.availability.pct, '%', 'Medicines available',
              `${v2n(g.availability.count)} of ${v2n(g.availability.of)} at a safe level`,
              g.availability.tone, g.availability.says)
      + v2Kpi(g.vital_availability.pct, '%', 'Life-saving available',
              `${v2n(g.vital_availability.count)} of ${v2n(g.vital_availability.of)}`,
              g.vital_availability.tone, g.vital_availability.says)
      + v2Kpi(g.stocked_out.pct, '%', 'Completely out',
              `${v2n(g.stocked_out.count)} with nothing on the shelf`,
              g.stocked_out.tone, g.stocked_out.says)
      + v2Kpi(g.at_risk_week.pct, '%', 'Gone within a week',
              `${v2n(g.at_risk_week.count)} at the current rate of use`,
              g.at_risk_week.tone, g.at_risk_week.says)
      + v2Kpi(g.spread.pct === null ? '—' : g.spread.pct,
              g.spread.pct === null ? '' : '%', 'Districts affected',
              `${v2n(g.spread.count)} of ${v2n(g.spread.of)} district${g.spread.of === 1 ? '' : 's'}`,
              g.spread.tone, g.spread.says);

    v2Timeline(d);
    v2Medicines(d);
    v2Quadrant(d);
    v2Shock(d, g);

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

// WHEN. Emphasis rather than a five-step ramp: five hues from one family fail
// colour-blind separation, and the buckets needing action this week are the
// only ones that need to shout.
function v2Timeline(d) {
  const el = document.getElementById('v2-timeline');
  if (!el || typeof Chart === 'undefined') return;
  const rows = d.timeline || [];
  const note = document.getElementById('v2-timeline-note');
  if (!rows.length) {
    if (note) note.textContent = 'No medicine here has enough usage history yet.';
    return;
  }
  const urgent = rows.filter(r => r.sort_order <= 2).reduce((a, r) => a + r.n, 0);
  const total = rows.reduce((a, r) => a + r.n, 0);

  if (v2Charts.timeline) v2Charts.timeline.destroy();
  v2Charts.timeline = new Chart(el.getContext('2d'), {
    type: 'bar',
    data: {
      labels: rows.map(r => r.bucket),
      datasets: [{
        label: 'Medicines',
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
          label: c => `${v2n(c.parsed.y)} medicines (${Math.round(100 * c.parsed.y / total)}%)`
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
    note.innerHTML = urgent
      ? `<strong>${v2n(urgent)} run out within a week</strong> — `
        + `${Math.round(100 * urgent / total)}% of everything tracked here.`
      : `Nothing here runs out within a week. The earliest is `
        + `${v2Esc(rows.find(r => r.n > 0).bucket).toLowerCase()} away.`;
  }
}

// WHAT. By name, because "Vitamin A is short in 49 health centres" is a
// sentence someone can act on.
function v2Medicines(d) {
  const el = document.getElementById('v2-medicines');
  if (!el || typeof Chart === 'undefined') return;
  const rows = d.worst_medicines || [];
  const note = document.getElementById('v2-medicines-note');
  if (!rows.length) {
    if (note) note.textContent = 'Nothing is running low here.';
    if (v2Charts.medicines) { v2Charts.medicines.destroy(); v2Charts.medicines = null; }
    return;
  }

  if (v2Charts.medicines) v2Charts.medicines.destroy();
  v2Charts.medicines = new Chart(el.getContext('2d'), {
    type: 'bar',
    data: {
      labels: rows.map(r => r.item_name),
      datasets: [{
        label: 'Health centres short',
        data: rows.map(r => r.centres),
        backgroundColor: rows.map(r => r.ven_class === 'Vital' ? V2_VITAL : V2_OTHER),
        borderRadius: 3, maxBarThickness: 20
      }]
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: {
          label: c => `${v2n(c.parsed.x)} health centres`,
          afterLabel: c => {
            const r = rows[c.dataIndex];
            return `${r.districts} districts · ${r.ven_class === 'Vital'
              ? 'life-saving' : r.ven_class.toLowerCase()}`;
          }
        } }
      },
      scales: {
        x: { beginAtZero: true, grid: { color: V2_GRID },
             ticks: { color: V2_INK, font: { size: 11 }, precision: 0 } },
        y: { grid: { display: false }, ticks: { color: V2_INK, font: { size: 11 } } }
      }
    }
  });

  const vital = rows.filter(r => r.ven_class === 'Vital');
  const top = rows[0];
  const plural = (n, one, many) => `${v2n(n)} ${n === 1 ? one : many}`;
  if (note) {
    note.innerHTML = `<strong>${v2Esc(top.item_name)}</strong> is short in `
      + `${plural(top.centres, 'health centre', 'health centres')} across `
      + `${plural(top.districts, 'district', 'districts')}`
      + (vital.length
          ? `. ${vital.length} of ${rows.length === 1 ? 'it' : `these ${rows.length}`}`
            + ` ${vital.length === 1 ? 'is' : 'are'} life-saving.`
          : '.');
  }
}

// WHERE. Exposure against ability to cope. Read separately these two mislead;
// together they separate the districts that are both badly short and unable to
// help themselves — the bottom-right corner.
function v2Quadrant(d) {
  const el = document.getElementById('v2-quadrant');
  if (!el || typeof Chart === 'undefined') return;
  const rows = d.districts_plot || [];
  const note = document.getElementById('v2-quadrant-note');
  if (!rows.length) {
    if (note) note.textContent = 'Not enough tracked medicines here to compare districts.';
    if (v2Charts.quadrant) { v2Charts.quadrant.destroy(); v2Charts.quadrant = null; }
    return;
  }

  // "Needs help first" = badly short AND unable to absorb a surge. One hue
  // plus grey; a scatter cannot carry more than three colours safely and this
  // only needs two.
  const critical = r => r.pct_short >= 40 && r.pct_cope < 35;

  if (v2Charts.quadrant) v2Charts.quadrant.destroy();
  v2Charts.quadrant = new Chart(el.getContext('2d'), {
    type: 'scatter',
    data: {
      datasets: [
        { label: 'Needs help first',
          data: rows.filter(critical).map(r => ({ x: r.pct_short, y: r.pct_cope, r_: r })),
          backgroundColor: V2_URGENT, pointRadius: 6, pointHoverRadius: 9 },
        { label: 'Other districts',
          data: rows.filter(r => !critical(r)).map(r => ({ x: r.pct_short, y: r.pct_cope, r_: r })),
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
            return `${r.district}, ${r.state}`;
          },
          label: c => {
            const r = c.raw.r_;
            return [`${r.pct_short}% of its medicines running low`,
                    `${r.pct_cope}% could cope if demand tripled`,
                    `${r.tracked} medicines tracked, ${r.vital_short} life-saving short`];
          }
        } }
      },
      scales: {
        x: { title: { display: true, text: 'Share of medicines running low →',
                      color: V2_INK, font: { size: 11 } },
             beginAtZero: true, grid: { color: V2_GRID },
             ticks: { color: V2_INK, font: { size: 10 }, callback: v => `${v}%` } },
        // Up is more, so the arrow points up. It pointed left, which on a
        // vertical axis reads as "less is up" — the opposite of the truth.
        y: { title: { display: true, text: 'Could cope if demand tripled ↑',
                      color: V2_INK, font: { size: 11 } },
             beginAtZero: true, grid: { color: V2_GRID },
             ticks: { color: V2_INK, font: { size: 10 }, callback: v => `${v}%` } }
      }
    }
  });

  const worst = rows.filter(critical)
    .sort((a, b) => b.pct_short - a.pct_short || a.pct_cope - b.pct_cope);
  if (note) {
    note.innerHTML = worst.length
      ? `<strong>${v2n(worst.length)} districts are in the danger corner</strong> — `
        + `badly short and unable to cover themselves. The worst is `
        + `<strong>${v2Esc(worst[0].district)}, ${v2Esc(worst[0].state)}</strong>, with `
        + `${worst[0].pct_short}% of its medicines running low and only `
        + `${worst[0].pct_cope}% able to cope with a tripling of demand.`
      : `No district here is both badly short and unable to cover itself.`;
  }
}

// HOW ROBUST. Three ordered stress levels, so a bar reads better than a gauge.
function v2Shock(d, g) {
  const el = document.getElementById('v2-shock');
  if (!el || typeof Chart === 'undefined') return;
  const rows = d.absorption || [];
  const note = document.getElementById('v2-shock-note');
  if (!rows.length) {
    if (note) note.textContent = 'Not enough data here to work this out.';
    if (v2Charts.shock) { v2Charts.shock.destroy(); v2Charts.shock = null; }
    return;
  }
  const said = { 2: 'If demand doubled', 3: 'If demand tripled',
                 5: 'If demand went 5× higher' };

  if (v2Charts.shock) v2Charts.shock.destroy();
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

  const r3 = g.resilience || {};
  if (note) {
    note.innerHTML = `<span class="panel-verdict ${r3.tone || 'warn'}">${r3.says || ''}</span>`
      + `<p class="section-note" style="margin-top:8px">`
      + `${v2n(d.transfer_only)} medicines would run out before a new order `
      + `could physically reach the health centre. Ordering cannot fix those — `
      + `only moving stock that already exists.</p>`;
  }
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
  const qs = q.toString();
  history.replaceState(null, '',
    `${window.location.pathname}${qs ? '?' + qs : ''}${window.location.hash}`);
}

// Put the dropdowns where the state says they should be. Selecting a value
// that is not in the list is a silent no-op in the DOM, so this reports back
// whether it actually took.
function v2SyncControls() {
  let ok = true;
  for (const [id, want] of [['v2-state', v2State],
                            ['v2-district', v2District],
                            ['v2-phc', v2Phc]]) {
    const sel = document.getElementById(id);
    if (!sel) continue;
    sel.value = want;
    if (sel.value !== want) { ok = false; sel.value = ''; }
  }
  // v2PhcName is set when a person picks from the dropdown. Arriving by link
  // skips that, and the scope line then read "IN-129024" where it should have
  // read "Jail Dispensary Sirohi".
  const phcSel = document.getElementById('v2-phc');
  v2PhcName = phcSel && phcSel.selectedIndex > 0
    ? phcSel.options[phcSel.selectedIndex].textContent.trim() : '';
  return ok;
}

// Initialise once, when the view is first opened.
let v2Ready = false;
async function initToday2() {
  if (v2Ready) { loadToday2(); return; }
  v2Ready = true;
  v2ReadUrl();

  // The scorecard does not wait for the dropdowns. It needs only the scope,
  // which came from the URL, so it starts now and renders the moment it lands.
  // Chained behind three geography lookups it was four round trips of blank
  // page before a single number appeared.
  loadToday2();

  // The three lookups do not depend on each other either — each needs only the
  // state and district already known — so they run together rather than in a
  // queue three deep.
  await Promise.all([v2LoadStates(), v2LoadDistricts(), v2LoadPhcs()]);

  // A link naming a district or facility that does not exist would otherwise
  // leave the dropdown blank while the numbers stayed filtered by it. Only
  // then is a second fetch warranted.
  if (!v2SyncControls()) {
    v2District = document.getElementById('v2-district').value || '';
    v2Phc = document.getElementById('v2-phc').value || '';
    v2WriteUrl();
    loadToday2();
  } else {
    // The scope was valid, so no refetch is needed — but the facility's name
    // is only now available, so the line is redrawn from the payload we have.
    v2RenderScope(v2LastData);
  }
}
