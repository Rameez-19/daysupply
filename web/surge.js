// Surge & emergency early warning.
//
// Two different things share this view and the UI has to keep them apart.
// Detected surges are read from precomputed tables built from real HMIS
// months. Scenario mode is computed live from whatever multiplier the user
// picks — so the control is a continuous slider rather than three preset
// buttons, which is the honest affordance for something that really does
// recompute rather than replay.
//
// Loads after app.js and uses its globals: getFilterParams, venBadge.

let scenarioCombos = [];

async function loadSurge() {
  loadSurgeSignals();
  loadSurgeImpact();
  loadScenarioOptions();
}

// `signalBadge()` used to live here. It now lives in app.js, because
// loadExecutive() on the landing view calls it, app.js loads first, and
// its init runs immediately — so a helper the landing view needs must not
// sit in a file that has not executed yet. See the guard test.

// Where reordering physically cannot work, say so in those words. Showing an
// order quantity here would imply the problem is handled when it is not.
function surgeActionBadge(action) {
  if (action === 'transfer_only') {
    return '<span class="surge-badge only">Transfer only — an indent cannot arrive in time</span>';
  }
  if (action === 'reorder_now') {
    return '<span class="surge-badge warn">Reorder now</span>';
  }
  return '<span class="surge-badge ok">Holds</span>';
}

async function loadSurgeSignals() {
  const el = document.getElementById('surge-signal-list');
  el.innerHTML = '<div class="empty-state"><p>Loading…</p></div>';
  try {
    const res = await fetch(`/api/v1/surge/signals?limit=8&${getFilterParams()}`);
    const data = await res.json();
    const signals = data.signals || [];
    const badge = document.getElementById('surge-badge');
    if (badge) badge.textContent = signals.length ? String(signals.length) : '';
    if (!signals.length) {
      el.innerHTML = '<div class="empty-state"><p>No surge detected in this scope. Every month sits within what the pooled seasonal pattern explains.</p></div>';
      return;
    }
    const first = signals[0];
    document.getElementById('surge-thresh-z').textContent = first.threshold_z;
    document.getElementById('surge-thresh-ratio').textContent = first.threshold_ratio;
    document.getElementById('surge-thresh-abs').textContent = first.threshold_absolute;

    el.innerHTML = signals.map(s => `
      <div class="alert-card severity-warning">
        <div class="alert-icon warning">&#128200;</div>
        <div class="alert-body">
          <div class="alert-title">${signalBadge(s.signal_class)} ${s.signal_indicator || s.atc_class}</div>
          <div class="alert-meta">${s.district_key} &middot; ${s.month} &middot; ${s.atc_class}${s.example_items ? ' (' + s.example_items + ')' : ''}</div>
          <div class="alert-detail signal-line">
            <strong>${s.signal_means || s.atc_class} is ${s.surge_multiplier}&times; expected</strong>
            for this district in ${s.month}.
            ${s.signal_why ? `<span class="signal-why">${s.signal_why}</span>` : ''}
          </div>
          <div class="alert-detail">
            ${Math.round(s.observed).toLocaleString()} clinical events against
            ${Math.round(s.expected).toLocaleString()} expected &mdash; the district's own
            baseline of ${Math.round(s.baseline).toLocaleString()} shaped by the pooled
            ${s.pooled_multiplier}&times; multiplier for ${s.month}.
          </div>
          <div class="alert-detail muted">
            modified z ${s.z_modified} (fires at ${s.threshold_z}) &middot;
            classical z ${s.z_classical} &mdash; bounded at 3.175 by the twelve-month
            series, which is why it is not the test
          </div>
        </div>
        <div class="alert-days critical">${s.surge_multiplier}&times;<span class="alert-days-label">vs expected</span></div>
      </div>`).join('');
  } catch (e) {
    el.innerHTML = '<div class="empty-state"><p>Could not load surge signals.</p></div>';
  }
}

async function loadSurgeImpact() {
  const el = document.getElementById('surge-impact-list');
  el.innerHTML = '<div class="empty-state"><p>Loading…</p></div>';
  try {
    const res = await fetch(`/api/v1/surge/impact?limit=10&${getFilterParams()}`);
    const data = await res.json();
    const rows = data.impact || [];
    if (!rows.length) {
      el.innerHTML = '<div class="empty-state"><p>No facility in this scope has a supply answer that a detected surge changes.</p></div>';
      return;
    }
    el.innerHTML = rows.map(r => `
      <div class="alert-card severity-${r.lead_time_decisive ? 'critical' : 'warning'}">
        <div class="alert-icon ${r.lead_time_decisive ? 'critical' : 'warning'}">${r.lead_time_decisive ? '&#128680;' : '&#9888;'}</div>
        <div class="alert-body">
          <div class="alert-title">${venBadge(r.ven_class)} ${r.item_name} &mdash; ${r.facility_name}</div>
          <div class="alert-meta">${r.district} &middot; ${r.surge_month} surge ${r.surge_multiplier}&times;</div>
          <div class="alert-detail">
            Demand ${r.avg_daily_demand}/day &rarr; <strong>${r.avg_daily_demand_surge}/day</strong> &middot;
            reorder point ${Math.round(r.reorder_point)} &rarr; <strong>${Math.round(r.reorder_point_surge)}</strong> ${r.unit}
          </div>
          <div class="alert-detail">
            ${Math.round(r.on_hand)} ${r.unit} on hand runs out in
            <strong>${r.days_to_stockout} days</strong> against a
            ${r.lead_time_days}-day lead time${r.lead_time_is_estimated ? ' (estimated)' : ''}
            ${r.newly_at_risk ? ' &middot; <em>was fine before the surge</em>' : ''}
          </div>
          <div class="alert-detail">${surgeActionBadge(r.surge_action)}</div>
        </div>
        <div class="alert-days ${r.lead_time_decisive ? 'critical' : 'warning'}">
          ${r.days_to_stockout}<span class="alert-days-label">days left</span>
        </div>
      </div>`).join('');
  } catch (e) {
    el.innerHTML = '<div class="empty-state"><p>Could not load surge impact.</p></div>';
  }
}

let scenarioOptionsLoading = null;
async function loadScenarioOptions() {
  const sel = document.getElementById('scenario-combo');
  if (!sel) return;
  if (sel.options.length && scenarioCombos.length) return;
  if (scenarioOptionsLoading) return scenarioOptionsLoading;
  scenarioOptionsLoading = _loadScenarioOptions(sel);
  try { await scenarioOptionsLoading; } finally { scenarioOptionsLoading = null; }
}
async function _loadScenarioOptions(sel) {
  try {
    const res = await fetch('/api/v1/surge/scenario/options');
    const data = await res.json();
    scenarioCombos = data.combinations || [];
    sel.innerHTML = scenarioCombos.map((c, i) =>
      `<option value="${i}">${c.district} &middot; ${c.atc_class} (${c.example_items}) &mdash; ${c.facilities} facilities</option>`
    ).join('');
  } catch (e) {
    sel.innerHTML = '<option>Could not load options</option>';
  }
}

async function runScenario() {
  const out = document.getElementById('scenario-result');
  const sel = document.getElementById('scenario-combo');
  const combo = scenarioCombos[parseInt(sel.value, 10)];
  if (!combo) {
    out.innerHTML = '<div class="empty-state"><p>Pick a district and medicine class.</p></div>';
    return;
  }
  const m = document.getElementById('scenario-mult').value;
  out.innerHTML = '<div class="empty-state"><p>Computing against current stock…</p></div>';
  try {
    const res = await fetch(`/api/v1/surge/scenario?district=${encodeURIComponent(combo.district)}`
      + `&atc_class=${encodeURIComponent(combo.atc_class)}&multiplier=${m}`);
    if (!res.ok) {
      const err = await res.json();
      out.innerHTML = `<div class="empty-state"><p>${err.detail || 'Scenario could not run.'}</p></div>`;
      return;
    }
    const r = await res.json();
    out.innerHTML = `
      <div class="scenario-verdict ${r.district_holds ? 'holds' : 'fails'}">
        <div class="scenario-verdict-head">${r.district_holds ? 'District holds' : 'District does not hold'}</div>
        <p>${r.verdict}</p>
        <div class="scenario-figures">
          <span><strong>${r.facilities_failing}</strong> of ${r.facility_count} facility-items fail</span>
          <span><strong>${r.facilities_transfer_only}</strong> cannot be resupplied in time</span>
          <span>first stockout in <strong>${r.first_stockout_days}</strong> days</span>
          <span>district cover <strong>${r.absorption_days}</strong> days vs ${r.slowest_lead_time}-day slowest lead time</span>
          ${r.units_short ? `<span><strong>${r.units_short.toLocaleString()}</strong> units short</span>` : ''}
        </div>
        ${r.structurally_thin ? `
        <p class="scenario-finding">
          <strong>A finding about the network, not the model.</strong>
          This district absorbs at most <strong>${r.max_multiplier_absorbed}&times;</strong> &mdash;
          below 1.0, so its pooled stock does not cover even its
          <em>normal</em> demand across its own lead time. That is true before
          any surge is applied, and it is measured from the real stock
          position rather than produced by the scenario.
        </p>` : ''}
      </div>

      <h4 class="section-heading">Which facilities fail, and when</h4>
      <div class="table-scroll">
      <table class="scenario-table">
        <thead><tr><th>Facility</th><th>Item</th><th>On hand</th><th>Reorder point</th><th>Runs out</th><th>Lead time</th><th>Answer</th></tr></thead>
        <tbody>${r.facilities.map(f => `
          <tr class="${f.surge_action === 'transfer_only' ? 'row-critical' : f.surge_action === 'reorder_now' ? 'row-warn' : ''}">
            <td>${f.facility_name}</td>
            <td>${venBadge(f.ven_class)} ${f.item_name}</td>
            <td>${Math.round(f.on_hand)}</td>
            <td>${Math.round(f.reorder_point)} &rarr; <strong>${Math.round(f.reorder_point_surge)}</strong></td>
            <td>${f.days_to_stockout} d</td>
            <td>${f.lead_time_days} d</td>
            <td>${surgeActionBadge(f.surge_action)}</td>
          </tr>`).join('')}</tbody>
      </table>
      </div>

      <h4 class="section-heading">Recommended transfers at ${r.multiplier}&times;</h4>
      ${r.transfers.length ? `
      <div class="table-scroll">
      <table class="scenario-table">
        <thead><tr><th>Move</th><th>From</th><th>To</th><th>Distance</th><th>Why</th></tr></thead>
        <tbody>${r.transfers.map(tr => `
          <tr>
            <td><strong>${tr.quantity}</strong> ${tr.unit} ${tr.requested_item_name}${tr.is_substitution ? ` <em>(as ${tr.supplied_item_name})</em>` : ''}</td>
            <td>${tr.from_facility_name}</td>
            <td>${tr.to_facility_name}</td>
            <td>${tr.distance_km} km</td>
            <td>${tr.lead_time_decisive ? 'Only option — runs out before an indent lands' : 'Faster than the next indent'}</td>
          </tr>`).join('')}</tbody>
      </table>
      </div>` : `
      <div class="empty-state"><p>No transfer is possible at ${r.multiplier}&times;: at this level of demand
      every facility in the district needs its own stock, so there is no donor. The gap has to be
      closed from outside the district.</p></div>`}

      <p class="scenario-method">${r.method}</p>`;
  } catch (e) {
    out.innerHTML = '<div class="empty-state"><p>Scenario could not run.</p></div>';
  }
}

const scenarioSlider = document.getElementById('scenario-mult');
if (scenarioSlider) {
  scenarioSlider.addEventListener('input', () => {
    document.getElementById('scenario-mult-label').innerHTML = `${scenarioSlider.value}&times;`;
  });
}
const scenarioBtn = document.getElementById('scenario-run');
if (scenarioBtn) scenarioBtn.addEventListener('click', runScenario);

// The banner on Today names a district and a medicine class. Following it
// used to land on Plan ahead with the scenario picker still on its first
// option, so the reader had to find the same district again by hand — and if
// that district has no stock positions for the class, could not, and did not
// know why. Scenario mode is deliberately limited to combinations with real
// stock (see get_scenario_options); when the surge falls outside that set the
// page now says so in words instead of leaving the picker unrelated to the
// warning that brought the reader here.
async function openScenarioFor(districtKey, atcClass) {
  switchTab('plan-view');
  await loadScenarioOptions();
  const sel = document.getElementById('scenario-combo');
  const out = document.getElementById('scenario-result');
  if (!sel || !out) return;
  const want = String(districtKey || '').toUpperCase();
  const idx = scenarioCombos.findIndex(c =>
    String(c.district || '').toUpperCase() === want && c.atc_class === atcClass);
  const section = sel.closest('.dashboard-section') || sel;
  if (idx >= 0) {
    sel.value = String(idx);
    await runScenario();
  } else {
    out.innerHTML = `<div class="empty-state"><p>
      Scenario mode cannot run for <strong>${atcClass}</strong> in
      <strong>${districtKey}</strong>: the reporting centres in that district
      hold no stock positions for this class, and a scenario is only computed
      against real stock. The early warning itself stands &mdash; it comes from
      HMIS case counts, not from stock. Pick a district and class from the list
      to run a scenario there.</p></div>`;
  }
  if (section.scrollIntoView) section.scrollIntoView({ block: 'start' });
}
window.openScenarioFor = openScenarioFor;


// ===== Surge banner on Today =====
// Surge is not a separate mode. During an emergency this IS the daily view, so
// when a surge is active for the officer's scope Today says so at the top and
// links to the detail — rather than sitting on a tab they might not open.
//
// The signal class is carried into the banner deliberately. "Confirmed malaria
// is 14.11x expected" (early warning) and "Albendazole is 22.64x expected"
// (National Deworming Day) demand completely different responses, and a banner
// that showed only a multiplier would flatten that distinction.
async function loadSurgeBanner(hostId = 'v2-surge-banner') {
  const el = document.getElementById(hostId);
  if (!el) return;
  try {
    const res = await fetch(`/api/v1/surge/signals?limit=5&${getFilterParams()}`);
    const signals = (await res.json()).signals || [];
    const badge = document.getElementById('surge-badge');
    if (badge) badge.textContent = signals.length ? String(signals.length) : '';
    if (!signals.length) { el.innerHTML = ''; return; }

    // Lead with a genuine early warning if there is one; a planned campaign
    // must never be the headline.
    const ranked = ['leading', 'coincident', 'programme'];
    signals.sort((a, b) => ranked.indexOf(a.signal_class) - ranked.indexOf(b.signal_class));
    const s = signals[0];
    const others = signals.length - 1;

    el.innerHTML = `
      <div class="surge-banner ${s.signal_class}">
        <div class="surge-banner-head">
          ${signalBadge(s.signal_class)}
          <strong>${s.signal_means || s.atc_class} is ${s.surge_multiplier}&times; expected</strong>
          in ${s.district_key}, ${s.month}
        </div>
        <p class="surge-banner-body">
          ${s.signal_why || ''}
          ${s.example_items ? `Affects <strong>${s.example_items}</strong>.` : ''}
          ${others > 0 ? `${others} other signal${others > 1 ? 's' : ''} in this scope.` : ''}
        </p>
        <button class="btn-primary"
                onclick="openScenarioFor(${JSON.stringify(s.district_key || '')}, ${JSON.stringify(s.atc_class || '')})">
          See what it changes
        </button>
      </div>`;
  } catch (e) {
    el.innerHTML = '';
  }
}
