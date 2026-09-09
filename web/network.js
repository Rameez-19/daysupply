// The Network view — comparison, which is the one job no other page does.
//
// Today v2 grades one scope. This ranks scopes against each other, and then
// does the thing a league table on its own gets wrong: it separates districts
// that are struggling from districts that are simply far from their supply.
//
// A ranking is the most quotable surface in the product and the easiest to be
// unfair with. Three deliberate choices guard against that:
//
//   * Both ends are shown. A table of failures teaches nobody what good looks
//     like, and the best performers are the evidence that the bad numbers are
//     achievable rather than inevitable.
//   * Districts with fewer than eight tracked lines are excluded, so nothing
//     tops or tails the table on a single bad reading.
//   * The distance panel sits under the ranking, because some districts are
//     hard to supply by geography and naming them without saying so blames
//     them for their own road network.
//
// The grain is not the same for every resource, and the server says which:
// medicines and beds vary district by district, staffing does not — vacancy is
// published at state level, so it is compared by state. Ranking 33 Rajasthan
// districts that all carry one Rajasthan figure would name places the number
// says nothing about.

const NET_INK = '#334155';
const NET_GRID = '#e2e8f0';
const NET_BAD = '#b91c1c';
const NET_CALM = '#94a3b8';
const NET_GOOD = '#15803d';

let netResource = 'medicine';
let netState = '';
let netCharts = { distribution: null, structure: null };
let netGeoLoaded = false;

const netN = v => (v === null || v === undefined ? '—' : v.toLocaleString('en-IN'));
const netPct = v => (v === null || v === undefined ? '—' : `${v}%`);

function netEsc(s) {
  return String(s === null || s === undefined ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function netSetResource(kind) {
  netResource = kind;
  for (const [id, on] of [['net-res-med', kind === 'medicine'],
                          ['net-res-bed', kind === 'bed'],
                          ['net-res-staff', kind === 'personnel']]) {
    const b = document.getElementById(id);
    if (b) b.classList.toggle('active', on);
  }
  loadNetwork();
}

function netOnState() {
  const sel = document.getElementById('net-state');
  netState = sel ? sel.value : '';
  loadNetwork();
}

// Reuses the reporting tree Today v2 already fetches, so switching pages does
// not pay for the same geography twice.
async function netFillStates() {
  const sel = document.getElementById('net-state');
  if (!sel || netGeoLoaded) return;
  try {
    const geo = (typeof v2LoadGeography === 'function')
      ? await v2LoadGeography()
      : await (await fetch('/api/v1/today2/geography')).json();
    const states = geo.states || [];
    sel.innerHTML = '<option value="">All India</option>'
      + states.map(x => `<option value="${netEsc(x.state)}">${netEsc(x.state)}</option>`).join('');
    sel.value = netState;
    netGeoLoaded = true;
  } catch (e) {
    sel.innerHTML = '<option value="">All India</option>';
  }
}

function netRow(r, rank, labels, grain) {
  const flag = r.score !== null && r.score < 60;
  return `
    <tr class="${flag ? 'row-critical' : ''}">
      <td class="net-rank">${rank}</td>
      <td><strong>${netEsc(r.district)}</strong><br>
        <span class="muted">${
          grain === 'district' && r.state ? netEsc(r.state) + ' · ' : ''
        }${netN(r.centres)} centre${r.centres === 1 ? '' : 's'}</span></td>
      <td class="net-num"><strong>${netPct(r.score)}</strong></td>
      <td class="net-num">${netPct(r.secondary)}</td>
      <td class="net-num">${r.failure === null || r.failure === undefined
        ? '—'
        : labels.failure_is_pct ? netPct(r.failure) : netN(r.failure)}</td>
    </tr>`;
}

function netTable(rows, labels, grain, startRank, countUp) {
  if (!rows.length) return panelEmpty('Nothing to rank at this scope.');
  const head = grain === 'state' ? 'State' : 'District';
  return `<div class="table-scroll">
    <table class="scenario-table net-table">
      <thead><tr>
        <th></th><th>${head}</th>
        <th class="net-num" title="${netEsc(labels.score)}">${netEsc(labels.score_short || labels.score)}</th>
        <th class="net-num" title="${netEsc(labels.secondary)}">${netEsc(labels.secondary_short || labels.secondary)}</th>
        <th class="net-num" title="${netEsc(labels.failure)}">${netEsc(labels.failure_short || labels.failure)}</th>
      </tr></thead>
      <tbody>${rows.map((r, i) =>
        netRow(r, countUp ? startRank + i : startRank - i, labels, grain)
      ).join('')}</tbody>
    </table></div>`;
}

function loadNetwork() {
  const host = document.getElementById('net-worst');
  if (!host) return;
  host.innerHTML = panelLoading('Ranking…');
  netFetch();
}

async function netFetch() {
  const synced = document.getElementById('net-synced');
  try {
    const q = new URLSearchParams({ resource: netResource });
    if (netState) q.set('state', netState);
    const res = await fetch(`/api/v1/network?${q}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const d = await res.json();

    const labels = d.labels || {};
    const grain = d.grain || 'district';
    const unit = grain === 'state' ? 'states' : 'districts';

    const scope = document.getElementById('net-scope');
    if (scope) {
      scope.innerHTML = d.empty
        ? 'Nothing to compare at this scope.'
        : `Comparing <strong>${netN(d.summary.districts)}</strong> ${unit} in `
          + `<strong>${netEsc(d.scope)}</strong>. Median `
          + `<strong>${netPct(d.summary.median)}</strong>, ranging from `
          + `${netPct(d.summary.lowest)} to ${netPct(d.summary.highest)}.`
          + (labels.grain_note
              ? `<div class="v2-scope-caveat">${netEsc(labels.grain_note)}</div>`
              : '');
    }

    for (const [id, text] of [['net-worst-title', `Needs help first`],
                              ['net-best-title', `Doing best`]]) {
      const el = document.getElementById(id);
      if (el) el.textContent = text;
    }
    const wn = document.getElementById('net-worst-note');
    if (wn) {
      wn.textContent = grain === 'state'
        ? 'States ranked by the measure below. Red is under 60%.'
        : 'Districts ranked by the measure below. Red is under 60%. Districts '
          + 'with fewer than eight tracked lines are left out, so nothing '
          + 'tops the table on a single bad reading.';
    }

    if (d.empty) {
      document.getElementById('net-worst').innerHTML =
        panelEmpty('Nothing to compare at this scope.');
      document.getElementById('net-best').innerHTML = '';
      netClear();
    } else {
      document.getElementById('net-worst').innerHTML =
        netTable(d.worst, labels, grain, 1, true);
      document.getElementById('net-best').innerHTML =
        netTable(d.best, labels, grain, d.summary.districts, false);
      netDistribution(d);
      netExtremes(d);
      netStructure(d);
    }

    if (synced) {
      synced.className = 'last-synced';
      synced.textContent = `Last synced: ${new Date().toLocaleTimeString()}`;
    }
  } catch (e) {
    const host = document.getElementById('net-worst');
    if (host) host.innerHTML = panelError(e.message, 'loadNetwork');
    if (synced) {
      synced.className = 'last-synced sync-failed';
      synced.textContent = `Not synced — ${e.message}`;
    }
  }
}

function netClear() {
  for (const k of Object.keys(netCharts)) {
    if (netCharts[k]) { netCharts[k].destroy(); netCharts[k] = null; }
  }
}

// Shared or concentrated? An average cannot answer it and the mean is what
// every other page shows.
function netDistribution(d) {
  const el = document.getElementById('net-distribution');
  const lab = (d.labels || {}).distribution || {};
  const t = document.getElementById('net-dist-title');
  const n = document.getElementById('net-dist-note');
  if (t && lab.title) t.textContent = lab.title;
  if (n && lab.note) n.textContent = lab.note;
  if (!el || typeof Chart === 'undefined') return;

  const rows = d.distribution || [];
  if (netCharts.distribution) netCharts.distribution.destroy();
  netCharts.distribution = new Chart(el.getContext('2d'), {
    type: 'bar',
    data: {
      labels: rows.map(r => r.bucket),
      datasets: [{
        label: 'Places',
        data: rows.map(r => r.n),
        // Only the failing band is coloured. A four-colour ramp here would
        // read as four categories rather than one scale.
        backgroundColor: rows.map(r =>
          r.sort_order === 1 ? NET_BAD : r.sort_order === 4 ? NET_GOOD : NET_CALM),
        borderRadius: 4, maxBarThickness: 64
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { color: NET_INK, font: { size: 11 } } },
        y: { beginAtZero: true, grid: { color: NET_GRID },
             ticks: { color: NET_INK, font: { size: 11 }, precision: 0 } }
      }
    }
  });

  const worst = rows.find(r => r.sort_order === 1);
  const best = rows.find(r => r.sort_order === 4);
  const total = rows.reduce((a, r) => a + r.n, 0);
  const cap = document.getElementById('net-dist-caption');
  if (cap && total) {
    cap.innerHTML = `<strong>${netN(worst ? worst.n : 0)} below 60%</strong> and `
      + `${netN(best ? best.n : 0)} at 90% or better. This is a spread, not a `
      + `single national figure &mdash; the places at each end need different `
      + `things.`;
  }
}

// A gap stated as two real places lands harder than a distribution.
function netExtremes(d) {
  const host = document.getElementById('net-extremes');
  const lab = (d.labels || {}).extremes || {};
  const t = document.getElementById('net-extremes-title');
  const n = document.getElementById('net-extremes-note');
  if (t && lab.title) t.textContent = lab.title;
  if (n && lab.note) n.textContent = lab.note;
  if (!host) return;

  const e = d.extremes;
  if (!e) { host.innerHTML = panelEmpty('Nothing to compare.'); return; }
  const labels = d.labels || {};
  // At state grain the place IS the state, so printing it twice reads as a
  // rendering fault: "Maharashtra / Maharashtra".
  const sub = r => (r.state && r.state !== r.district) ? netEsc(r.state) : '';

  const card = (r, tone, role) => `
    <div class="net-extreme ${tone}">
      <div class="net-extreme-role">${role}</div>
      <div class="net-extreme-value">${netPct(r.score)}</div>
      <div class="net-extreme-name">${netEsc(r.district)}</div>
      <div class="net-extreme-sub">${sub(r)}</div>
      <div class="net-extreme-meta">
        ${netEsc(labels.secondary)} ${netPct(r.secondary)}
        &middot; ${netN(r.centres)} centre${r.centres === 1 ? '' : 's'}
        ${r.lead_days ? `&middot; ${r.lead_days}d to resupply` : ''}
      </div>
    </div>`;

  // The middle of the pack, named. Two extremes cannot say whether the worst
  // is an outlier or whether the typical place is struggling too — and those
  // are different problems: one district to rescue, or a system to fix.
  const typ = e.typical;
  const typicalCard = typ ? `
    <div class="net-extreme typical">
      <div class="net-extreme-role">Typical</div>
      <div class="net-typical-line">
        <span class="net-extreme-value">${netPct(typ.score)}</span>
        <span class="net-typical-place">
          <strong>${netEsc(typ.district)}</strong>
          ${sub(typ) ? `<span class="net-extreme-sub">${sub(typ)}</span>` : ''}
        </span>
      </div>
      <div class="net-extreme-meta">
        ${netN(e.above_typical)} above it, ${netN(e.below_typical)} below —
        so the worst ${e.below_typical > e.above_typical
          ? 'sits in a crowded bottom half, not on its own'
          : 'is the tail of a mostly healthier network'}.
      </div>
    </div>` : '';

  host.innerHTML = `
    <div class="net-extremes-row">
      ${card(e.best, 'ok', 'Best')}
      ${card(e.worst, 'bad', 'Worst')}
    </div>
    ${typicalCard}
    <p class="panel-verdict ${e.gap >= 40 ? 'bad' : 'warn'}">
      <strong>${netPct(e.gap)}</strong> apart on the same measure, under the
      same rules. Whatever ${netEsc(e.best.district)} is doing is possible.
    </p>`;
}

// The panel that stops the ranking being unfair — and states its own limit.
function netStructure(d) {
  const section = document.getElementById('net-structure-section');
  const el = document.getElementById('net-structure');
  const lab = (d.labels || {}).structure || {};
  const rows = d.structure || [];

  // Only medicines carry a lead time. Rather than invent a distance measure
  // for beds and staff, the panel is removed for them.
  if (!rows.length) {
    if (section) section.hidden = true;
    if (netCharts.structure) { netCharts.structure.destroy(); netCharts.structure = null; }
    return;
  }
  if (section) section.hidden = false;

  const t = document.getElementById('net-structure-title');
  const n = document.getElementById('net-structure-note');
  if (t && lab.title) t.textContent = lab.title;
  if (n && lab.note) n.textContent = lab.note;
  if (!el || typeof Chart === 'undefined') return;

  if (netCharts.structure) netCharts.structure.destroy();
  netCharts.structure = new Chart(el.getContext('2d'), {
    type: 'bar',
    data: {
      labels: rows.map(r => r.band),
      datasets: [{
        label: 'Mean availability',
        data: rows.map(r => r.mean_score),
        backgroundColor: rows.map(r =>
          r.mean_score < 60 ? NET_BAD : r.mean_score < 80 ? '#ea580c' : NET_GOOD),
        borderRadius: 4, maxBarThickness: 56
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: {
          label: c => `${c.parsed.y}% available on average`,
          afterLabel: c => {
            const r = rows[c.dataIndex];
            return `${r.districts} districts · ${r.mean_km} km from the hub`;
          }
        } }
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: NET_INK, font: { size: 11 } } },
        y: { beginAtZero: true, max: 100, grid: { color: NET_GRID },
             ticks: { color: NET_INK, font: { size: 11 }, callback: v => `${v}%` } }
      }
    }
  });

  const first = rows[0], last = rows[rows.length - 1];
  const cap = document.getElementById('net-structure-caption');
  if (cap && first && last) {
    cap.innerHTML =
      `Districts within ${netEsc(first.band.toLowerCase())} of resupply average `
      + `<strong>${first.mean_score}%</strong>; those ${netEsc(last.band.toLowerCase())} `
      + `away average <strong>${last.mean_score}%</strong> — `
      + `<strong>${Math.round(first.mean_score - last.mean_score)} points</strong> `
      + `on distance alone.`
      + `<p class="section-note" style="margin-top:8px">`
      + `The furthest band holds only ${last.districts} district`
      + `${last.districts === 1 ? '' : 's'}, so read it as an indication rather `
      + `than a measurement. And distance explains under a tenth of the `
      + `difference between districts overall: it is one reason a district is `
      + `behind, never the whole reason.</p>`;
  }
}

let netReady = false;
async function initNetwork() {
  if (!netReady) {
    netReady = true;
    loadNetwork();
    await netFillStates();
  } else {
    loadNetwork();
  }
}
