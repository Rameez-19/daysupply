// ===== IndexedDB =====
let db;
const dbReq = indexedDB.open("StockPulseDB", 1);
dbReq.onupgradeneeded = e => { db = e.target.result; db.createObjectStore("offline-queue", { keyPath: "id" }); };
dbReq.onsuccess = e => { db = e.target.result; checkOnlineStatus(); };

// ===== DOM =====
const sidebarItems = document.querySelectorAll('.nav-item');
const bottomItems  = document.querySelectorAll('.bottom-nav-item');
const allViews     = document.querySelectorAll('.view');
const micBtn       = document.getElementById('mic-btn');
const micRing      = document.getElementById('mic-ring');
const micStatus    = document.getElementById('mic-status');
const captureResult  = document.getElementById('capture-result');
const captureContent = document.getElementById('capture-result-content');
const reviewList   = document.getElementById('review-list');
const alertsList   = document.getElementById('alerts-list');
const transferList = document.getElementById('transfer-list');

// ===== Navigation =====
function switchTab(tabId) {
  allViews.forEach(v => { v.classList.remove('active-view'); v.classList.add('hidden-view'); });
  const target = document.getElementById(tabId);
  if (target) { target.classList.remove('hidden-view'); target.classList.add('active-view'); }
  sidebarItems.forEach(b => b.classList.remove('active'));
  const side = document.querySelector(`.nav-item[data-tab="${tabId}"]`);
  if (side) side.classList.add('active');
  bottomItems.forEach(b => b.classList.remove('active'));
  const bot = document.querySelector(`.bottom-nav-item[data-tab="${tabId}"]`);
  if (bot) bot.classList.add('active');

  // One dispatcher, shared with init and every filter change. Keeping a
  // second list here is exactly how init drifted out of step with the layout
  // and spent a release calling a loader for an element that no longer
  // existed.
  refreshAll();
}
sidebarItems.forEach(btn => btn.addEventListener('click', () => switchTab(btn.dataset.tab)));
bottomItems.forEach(btn  => btn.addEventListener('click', () => switchTab(btn.dataset.tab)));
window.switchTab = switchTab;
// Reachable from the inline onclick in panelError().

// ===== Online / Offline =====
function updateSyncUI(online) {
  document.querySelectorAll('.sync-dot').forEach(d => d.className = online ? 'sync-dot online' : 'sync-dot offline');
  document.querySelectorAll('.sync-label').forEach(l => l.textContent = online ? 'Online' : 'Offline');
}
window.addEventListener('online',  () => { updateSyncUI(true);  syncQueue(); });
window.addEventListener('offline', () => { updateSyncUI(false); });
function checkOnlineStatus() { updateSyncUI(navigator.onLine); if (navigator.onLine) syncQueue(); }

async function syncQueue() {
  if (!db) return;
  const tx = db.transaction(["offline-queue"], "readwrite");
  const req = tx.objectStore("offline-queue").getAll();
  req.onsuccess = async () => {
    for (const item of req.result) {
      try {
        const fd = new FormData();
        fd.append("facility_id", item.facility_id);
        fd.append("file", item.audioBlob, "recording.webm");
        const res = await fetch("/api/v1/voice-note", { method: "POST", body: fd });
        if (res.ok) db.transaction(["offline-queue"], "readwrite").objectStore("offline-queue").delete(item.id);
      } catch (e) { console.error(e); }
    }
  };
}

// ===== Cascading Filters =====
// The landing view is the national picture, so it opens on All India.
// It used to open hardcoded to Telangana, left over from when this page
// was a district dashboard: the header said "National picture" while the
// numbers underneath were one state's (201 stock lines, not 2,794).
// Empty scope is safe — loadDistricts and loadPHCs both guard on it.
let currentState = "";
let currentDistrict = "";
let currentPHC = "";
let currentChartDays = 7;
let currentPHCName = "";
// Medicines, beds and personnel are one platform with one filter bar, not
// three products with three pages. The selector swaps what the panel shows;
// the geography filters above it are untouched.
let currentResource = "medicine";

// Geography comes from BigQuery — the real 200,438-facility national master.
// Nothing here is hardcoded; the dropdowns list what is actually in the data.
function setOptions(select, placeholder, rows, valueKey, labelFn) {
  select.innerHTML = "";
  const first = document.createElement("option");
  first.value = ""; first.textContent = placeholder;
  select.appendChild(first);
  rows.forEach(r => {
    const opt = document.createElement("option");
    opt.value = r[valueKey];
    opt.textContent = labelFn(r);
    select.appendChild(opt);
  });
}

function setDropdownError(select, message) {
  select.innerHTML = `<option value="">${message}</option>`;
}

async function loadStates() {
  const sel = document.getElementById('state-filter');
  try {
    const res = await fetch('/api/v1/states');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const { states } = await res.json();
    setOptions(sel, `All States (${states.length})`, states, 'state',
      r => `${r.state} — ${r.facility_count.toLocaleString('en-IN')} facilities`);
    // No auto-selection: All India is the default and the dropdown says so.
    sel.value = currentState;
    await loadDistricts();
  } catch (e) {
    console.error('Failed to load states', e);
    setDropdownError(sel, 'States unavailable');
    // Geography failing means nothing below it can be scoped, so the header
    // must not go on claiming a successful sync.
    setSyncState(false, 'geography unavailable');
    throw e;
  }
}

async function loadDistricts() {
  const sel = document.getElementById('district-filter');
  currentDistrict = ""; currentPHC = ""; currentPHCName = "";
  if (!currentState) { setOptions(sel, 'All Districts', [], 'district', r => r); return; }
  try {
    const res = await fetch(`/api/v1/districts?state=${encodeURIComponent(currentState)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const { districts } = await res.json();
    // display_name differs from district only where two government sources
    // spell it differently; the value posted back is always the stored one.
    setOptions(sel, `All Districts (${districts.length})`, districts, 'district',
      r => `${r.display_name || r.district} — ${r.phc_count} PHCs`);
  } catch (e) {
    console.error('Failed to load districts', e);
    setDropdownError(sel, 'Districts unavailable');
  }
  await loadPHCs();
}

async function loadPHCs() {
  const sel = document.getElementById('phc-filter');
  currentPHC = ""; currentPHCName = "";
  if (!currentState || !currentDistrict) {
    setOptions(sel, 'All PHCs', [], 'facility_id', r => r.name);
    return;
  }
  try {
    const url = `/api/v1/facilities?state=${encodeURIComponent(currentState)}`
      + `&district=${encodeURIComponent(currentDistrict)}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const { facilities } = await res.json();
    setOptions(sel, `All PHCs (${facilities.length})`, facilities, 'facility_id',
      r => r.name);
  } catch (e) {
    console.error('Failed to load facilities', e);
    setDropdownError(sel, 'Facilities unavailable');
  }
}

async function onStateChange() {
  currentState = document.getElementById('state-filter').value;
  await loadDistricts();
  updateSubtitle();
  refreshAll();
}

async function onDistrictChange() {
  currentDistrict = document.getElementById('district-filter').value;
  await loadPHCs();
  updateSubtitle();
  refreshAll();
}

function onPHCChange() {
  const sel = document.getElementById('phc-filter');
  currentPHC = sel.value;
  currentPHCName = currentPHC ? sel.options[sel.selectedIndex].textContent : "";
  updateSubtitle();
  refreshAll();
}

function updateSubtitle() {
  const el = document.getElementById('dashboard-subtitle');
  if (!el) return;
  const scope = currentPHCName || currentDistrict || currentState || 'All India';
  // States what the page is, then what it is scoped to. The old version
  // replaced the whole line with "<scope> Network — Real-time overview", which
  // told a first-time reader the state and nothing about the product.
  el.innerHTML = 'Medicines, beds and staff across India&rsquo;s primary '
    + `health network &mdash; <strong>${scope}</strong>`;
}

function getFilterParams() {
  let params = `state=${encodeURIComponent(currentState)}`;
  if (currentDistrict) params += `&district=${encodeURIComponent(currentDistrict)}`;
  if (currentPHC) params += `&phc=${encodeURIComponent(currentPHC)}`;
  return params;
}

// The alerts and recommendations endpoints default to 50 rows. The front end
// never sent a limit, so the Action queue — which promises the whole queue —
// was quietly showing 50 of 597, and Today's hand-off read "Showing 5 of 50".
// Asking for more than exists means the row count IS the true total, so the
// hand-off can state it honestly without a separate count query.
const QUEUE_LIMIT = 1000;

// Which view the reader is actually looking at. Everything else is hidden, and
// refreshing it costs a BigQuery round trip the reader will never see.
function activeViewId() {
  const el = document.querySelector('.view.active-view');
  return el ? el.id : 'today-view';
}

// Refresh only what is on screen.
//
// This used to fire all five loaders on every filter change, regardless of
// which view was visible — so changing the state dropdown on Today also
// rebuilt the forecast chart, the network charts, the resource panel and the
// lead-time contrast, none of which were on screen. Four wasted round trips,
// and the slowest of them set how long the dropdown appeared to hang.
//
// Each view reloads when switched to, so nothing goes stale; it just no longer
// loads four views early.
function refreshAll() {
  const view = activeViewId();
  if (view === 'today-view') {
    loadExecutive();
    loadAlerts();
    loadTransfers();
    if (typeof loadSurgeBanner === 'function') loadSurgeBanner();
  } else if (view === 'network-view') {
    loadResourcePanel();
    loadChart(currentChartDays);   // also draws the two network charts
  } else if (view === 'plan-view') {
    loadChart(currentChartDays);
    if (typeof loadSurge === 'function') loadSurge();
  } else if (view === 'action-view') {
    // Same two loaders as Today; they render the preview and the full queue
    // from one fetch each, so opening the queue costs nothing extra.
    loadAlerts();
    loadTransfers();
  } else if (view === 'map-view') {
    if (typeof loadMap === 'function') loadMap();
  } else if (view === 'evidence-view') {
    loadLeadTimeContrast();
    if (typeof loadEvidence === 'function') loadEvidence();
  } else if (view === 'capture-view' || view === 'review-view') {
    loadReviewQueue();
  }
}

// Make filter functions global
// NOTE: no `window.<name> = () => <name>()` wrappers here. A global function
// declaration in a classic script is already a property of window, so
// that assignment REPLACES the binding, and the identifier inside the
// arrow then resolves to the arrow itself — infinite recursion. It cost
// the whole landing view. See the guard test.
window.onStateChange = onStateChange;
window.onDistrictChange = onDistrictChange;
window.onPHCChange = onPHCChange;

// ===== Honest panel states =====
// A blank card is the worst outcome: the reader cannot tell whether there is
// nothing to show, something is still loading, or the request failed. Every
// panel on Today uses these three, and the failure state offers a retry rather
// than leaving a dead end.

function panelLoading(message) {
  return `<div class="empty-state"><p class="panel-loading">${message}</p></div>`;
}

function panelEmpty(message) {
  return `<div class="empty-state"><p>${message}</p></div>`;
}

function panelError(message, retryFn) {
  return `<div class="empty-state panel-error">
    <p><strong>Could not load this.</strong></p>
    <p class="panel-error-detail">${message}</p>
    <button class="btn-primary" onclick="${retryFn}()">Try again</button>
  </div>`;
}

// One place that knows whether the last load worked, so the header cannot
// claim success while the panels are empty.
function setSyncState(ok, detail) {
  const el = document.getElementById('last-synced');
  if (!el) return;
  el.className = ok ? 'last-synced' : 'last-synced sync-failed';
  el.textContent = ok
    ? `Last synced: ${new Date().toLocaleTimeString()}`
    : `Not synced — ${detail || 'could not reach the server'}`;
}

// Three signal classes, three different things a district officer must not
// confuse. LEADING is a clinical warning that precedes the demand it drives;
// COINCIDENT means the presentation and the dispensing move together, so it is
// information rather than warning; PROGRAMME means a planned campaign, not an
// outbreak — a 22.64x Albendazole swing is National Deworming Day.
function signalBadge(cls) {
  if (cls === 'leading') {
    return '<span class="signal-badge leading" title="A clinical signal that '
      + 'rises before the medicine demand it drives">Early warning</span>';
  }
  if (cls === 'programme') {
    return '<span class="signal-badge programme" title="A planned campaign, '
      + 'not an outbreak">Planned campaign</span>';
  }
  return '<span class="signal-badge coincident" title="The presentation and '
    + 'the dispensing happen together">Happening now</span>';
}

// ===== Dashboard =====
async function loadDashboard() {
  try {
    const res = await fetch(`/api/v1/stats?${getFilterParams()}`);
    // A 500 with a JSON body would otherwise render as a dashboard full of
    // undefined, which reads as data rather than as a failure.
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const stats = await res.json();
    renderStats(stats);
    setSyncState(true);
  } catch (e) {
    setSyncState(false, e.message);
    // Facility counts come from BigQuery. If that fails we say so rather than
    // showing a number that is not real.
    console.error('Failed to load stats', e);
    const grid = document.getElementById('stats-grid');
    if (grid) grid.innerHTML = '<div class="stat-card"><div class="stat-info">'
      + '<span class="stat-value">—</span>'
      + '<span class="stat-label">Facility data unavailable</span>'
      + '</div></div>';
  }

  try {
    const res = await fetch(`/api/v1/alerts?${getFilterParams()}`);
    const data = await res.json();
    renderDashboardAlerts(data.alerts || []);
    const badge = document.getElementById('alert-badge');
    if (badge && data.alerts) badge.textContent = data.alerts.length;
  } catch (e) {}

  try {
    const res = await fetch(`/api/v1/review-queue?${getFilterParams()}`);
    const data = await res.json();
    const badge = document.getElementById('review-badge');
    if (badge && data.items) badge.textContent = data.items.length;
  } catch (e) {}
}

function deltaHtml(value) {
  if (value === undefined || value === null) return '';
  const arrow = value >= 0 ? '▲' : '▼';
  const cls = value >= 0 ? 'up' : 'down';
  return `<span class="stat-delta ${cls}">${value >= 0 ? '+' : ''}${value}% ${arrow}</span>`;
}

function renderStats(s) {
  // `stats-grid` was replaced by the posture cards on the national picture.
  // Guarded rather than deleted: an unguarded write here threw "Cannot set
  // properties of null" on every page load and stopped the whole init chain,
  // and cutting the function out with a regex took 434 unrelated lines with
  // it. One line, no blast radius.
  const grid = document.getElementById('stats-grid');
  if (!grid) return;
  grid.innerHTML = `
    <div class="stat-card clickable" onclick="switchTab('network-view')">
      <div class="stat-icon" style="background:linear-gradient(135deg,#1e3a8a,#3b82f6);">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
      </div>
      <div class="stat-info">
        <span class="stat-value">${(s.facilities ?? 0).toLocaleString('en-IN')}</span>
        <span class="stat-label">Health Facilities</span>
        <span class="stat-delta">${(s.phcs ?? 0).toLocaleString('en-IN')} PHCs</span>
      </div>
    </div>
    <div class="stat-card clickable" onclick="switchTab('today-view')">
      <div class="stat-icon" style="background:linear-gradient(135deg,#f97316,#fb923c);">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/></svg>
      </div>
      <div class="stat-info">
        <span class="stat-value">${s.stockout_alerts}</span>
        <span class="stat-label">Stockout Alerts</span>
        ${deltaHtml(s.delta_alerts)}
      </div>
    </div>
    <div class="stat-card clickable" onclick="switchTab('today-view')">
      <div class="stat-icon" style="background:linear-gradient(135deg,#ef4444,#f87171);">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>
      </div>
      <div class="stat-info">
        <span class="stat-value">${s.pending_transfers}</span>
        <span class="stat-label">Pending Transfers</span>
        ${deltaHtml(s.delta_transfers)}
      </div>
    </div>
  `;
}

// Vital / Essential / Desirable, per WHO and MoHFW practice. A vital-drug
// stock-out is not the same event as a desirable-drug one, so the badge is
// shown wherever an alert or a transfer is.
function venBadge(ven) {
  if (!ven) return '';
  const cls = ven === 'Vital' ? 'ven-vital'
            : ven === 'Essential' ? 'ven-essential' : 'ven-desirable';
  return `<span class="ven-badge ${cls}" title="${ven} (WHO/MoHFW VEN)">${ven[0]}</span>`;
}

function severityOf(alert) {
  if (alert.status === 'stocked_out') return 'critical';
  if (alert.status === 'critical') return 'critical';
  return 'warning';
}

function renderDashboardAlerts(alerts) {
  const el = document.getElementById('dashboard-alerts');
  if (!alerts.length) { el.innerHTML = '<p style="font-size:0.85rem; color:var(--gray-400);">No active alerts</p>'; return; }
  
  let html = alerts.slice(0, 4).map(a => `
    <div class="mini-alert">
      <div class="mini-alert-left">
        <span class="mini-alert-facility">${a.facility_name || a.facility_id}</span>
        <span class="mini-alert-item">${venBadge(a.ven_class)} ${a.item_name || a.item_id}</span>
      </div>
      <span class="mini-alert-days">${a.days_of_cover}d left</span>
    </div>
  `).join('');
  
  if (alerts.length > 0) {
  }
  el.innerHTML = html;
}

// ===== Review Queue =====
async function loadReviewQueue() {
  reviewList.innerHTML = '<div class="empty-state"><p>Loading…</p></div>';
  try {
    const res = await fetch(`/api/v1/review-queue?${getFilterParams()}`);
    const data = await res.json();
    if (!data.items || !data.items.length) {
      reviewList.innerHTML = '<div class="empty-state"><p>No items to review.</p></div>';
      return;
    }
    // An unlabelled example is indistinguishable from a real pending review.
    const exampleBanner = data.is_example_data
      ? `<div class="example-banner"><strong>Worked examples.</strong> ${data.basis}</div>`
      : '';
    reviewList.innerHTML = exampleBanner + data.items.map(item => `
      <div class="item-card" id="item-${item.event_id}">
        <div class="card-header">
          <span style="font-weight:700; color:var(--gray-900);">${item.item_name || item.item_id}</span>
          <span class="card-badge ${item.confidence < 0.4 ? 'badge-danger' : 'badge-warning'}">${Math.round(item.confidence * 100)}% confident</span>
        </div>
        <div class="card-facility">${item.facility_name || item.facility_id} · ${timeAgo(item.created_at)}</div>
        <div class="card-transcript">"${item.raw_transcript}"</div>
        <div class="card-details">
          <span class="card-detail-label">Quantity</span><span class="card-detail-value">${item.quantity} ${item.unit}</span>
          <span class="card-detail-label">Type</span><span class="card-detail-value">${item.event_type}</span>
        </div>
        <div class="card-actions">
          <button class="btn btn-primary" onclick="approveItem('${item.event_id}')">✓ Approve</button>
          <button class="btn btn-danger" onclick="rejectItem('${item.event_id}')">✗ Reject</button>
        </div>
      </div>
    `).join('');
  } catch (e) {
    reviewList.innerHTML = '<div class="empty-state"><p>Could not load review queue.</p></div>';
  }
}

// ===== Acting on a recommendation =====
// These used to fade the card and call nothing, which made the interface claim
// an action the system never took. Every one of them now hits a real endpoint
// and reports what actually happened, including when it fails.

const NEXT_STEP = { approve: 'dispatch', dispatch: 'receive', receive: null };
const STEP_LABEL = { approve: 'Approve transfer', dispatch: 'Mark dispatched',
                     receive: 'Confirm received' };

async function advanceTransfer(id, step) {
  const box = document.getElementById('lc-' + id);
  if (box) box.innerHTML = '<p class="lifecycle-note">Recording…</p>';
  try {
    const res = await fetch(`/api/v1/recommendations/${id}/${step}`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) {
      if (box) box.innerHTML =
        `<p class="lifecycle-error">${data.detail || 'Could not record this.'}</p>`;
      return;
    }
    const next = NEXT_STEP[step];
    const moved = data.stock_moved
      ? `<span class="lifecycle-moved">${data.stock_moved.quantity} ${data.unit}
         ${data.stock_moved.direction === 'out' ? 'left' : 'arrived at'}
         ${data.stock_moved.facility}</span>`
      : '';
    if (box) box.innerHTML = `
      <p class="lifecycle-state"><strong>${data.fulfilment_status}</strong> ${moved}</p>
      <p class="lifecycle-note">${data.note}</p>
      ${next ? `<button class="btn btn-primary btn-full"
                  onclick="advanceTransfer('${id}','${next}')">${STEP_LABEL[next]}</button>`
             : "<p class=\"lifecycle-note\">Complete — the stock is on the receiving facility's shelf.</p>"}`;
    // On-hand has changed at one of the two facilities, so the numbers on the
    // other screens are now stale.
    refreshAll();
  } catch (e) {
    if (box) box.innerHTML = '<p class="lifecycle-error">Could not reach the server.</p>';
  }
}

async function approveItem(id) {
  const el = document.getElementById('item-' + id);
  const qty = window.prompt(
    "Quantity to record?\n\nThis item is in review because the amount was "
    + "unclear. Approving needs the number.", "");
  if (qty === null) return;
  try {
    const url = `/api/v1/review-queue/${id}/approve`
      + (qty === '' ? '' : `?quantity=${encodeURIComponent(qty)}`);
    const res = await fetch(url, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) {
      const detail = data.detail || {};
      alert(detail.reason || 'Could not approve this item.');
      return;
    }
    if (el) { el.style.opacity = '0.35'; el.style.pointerEvents = 'none'; }
    refreshAll();
  } catch (e) {
    alert('Could not reach the server.');
  }
}

// Rejecting is a local dismissal only. There is deliberately no reject
// endpoint: nothing was written to the ledger for a held item, so there is
// nothing to undo. See HANDOVER §9e — no retraction, ever.
function rejectItem(id) {
  const el = document.getElementById('item-' + id);
  if (el) { el.style.opacity = '0.35'; el.style.pointerEvents = 'none'; }
}

function timeAgo(iso) {
  const ms = Date.now() - new Date(iso).getTime();
  const hrs = ms / 3600000;
  if (hrs < 1) return Math.round(hrs * 60) + 'm ago';
  return Math.floor(hrs / 24) + 'd ago';
}

// ===== Alerts =====
// How many rows the summary view shows before handing off to Action queue.
// Ninety stacked cards is not a dashboard; it is a log with a header.
const TODAY_PREVIEW = 5;

async function loadAlerts() {
  // Building 597 cards costs real time, so the full queue is only rendered
  // when the reader is actually on it. Today gets the preview either way.
  const full = activeViewId() === 'action-view'
    ? document.getElementById('alerts-full') : null;
  if (!alertsList && !full) return;
  const loading = panelLoading('Checking what is running out…');
  if (alertsList) alertsList.innerHTML = loading;
  if (full) full.innerHTML = loading;
  try {
    const res = await fetch(
      `/api/v1/alerts?${getFilterParams()}&limit=${QUEUE_LIMIT}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (!data.alerts || !data.alerts.length) {
      const empty = panelEmpty(
        'Nothing is below its reorder point in this scope. That is a real '
        + 'result, not a missing one.');
      if (alertsList) alertsList.innerHTML = empty;
      if (full) full.innerHTML = empty;
      setCount('alerts-count', 0);
      setBadge('action-badge', 0);
      return;
    }
    const cards = data.alerts.map(a => {
      const sev = severityOf(a);
      // The reorder point is this facility's own, not a flat network rule.
      const vsFlat = a.reorder_point > a.legacy_threshold
        ? `<span class="alert-note up">+${Math.round(a.reorder_point - a.legacy_threshold)} ${a.unit} above the old flat 14-day rule</span>`
        : `<span class="alert-note">${Math.round(a.legacy_threshold - a.reorder_point)} ${a.unit} below the old flat 14-day rule</span>`;
      return `
      <div class="alert-card severity-${sev}">
        <div class="alert-icon ${sev}">${sev === 'critical' ? '🚨' : '⚠️'}</div>
        <div class="alert-body">
          <div class="alert-title">${venBadge(a.ven_class)} ${a.item_name || a.item_id}</div>
          <div class="alert-meta">${a.facility_name || a.facility_id} · ${a.district || ''}</div>
          <div class="alert-detail">
            On hand ${Math.round(a.on_hand)} ${a.unit} ·
            reorder at ${Math.round(a.reorder_point)}
            (${Math.round(a.avg_daily_demand)}/day x ${a.lead_time_days}d lead
             + ${Math.round(a.safety_stock)} safety)
          </div>
          <div class="alert-detail">
            ${a.distance_to_hq_km} km from district HQ${a.lead_time_is_estimated ? ' (distance estimated)' : ''} · ${vsFlat}
          </div>
        </div>
        <div class="alert-days ${sev}">
          ${a.days_of_cover}<span class="alert-days-label">days left</span>
        </div>
      </div>`;
    });

    // One fetch, two audiences: the top of the queue on Today, the whole
    // queue on Action queue.
    if (alertsList) {
      alertsList.innerHTML = cards.slice(0, TODAY_PREVIEW).join('');
      setMore('alerts-more', cards.length, 'shortage');
    }
    if (full) full.innerHTML = cards.join('');
    setCount('alerts-count', cards.length);
    setBadge('action-badge', cards.length);
  } catch (e) {
    const err = panelError(e.message, 'loadAlerts');
    if (alertsList) alertsList.innerHTML = err;
    if (full) full.innerHTML = err;
  }
}

// "Showing 5 of 597" is the difference between a summary and a lie.
//
// This lives in its own element rather than at the end of the list, because
// the list scrolls: appended to the cards it would scroll out of sight, and
// the two columns would show their hand-off at different heights.
function setMore(id, total, noun) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = total <= TODAY_PREVIEW ? '' : `
    <button class="more-note" onclick="switchTab('action-view')">
      Showing ${TODAY_PREVIEW} of ${total.toLocaleString('en-IN')} ${noun}${total === 1 ? '' : 's'}
      &mdash; open the full queue &rarr;
    </button>`;
}

function setCount(id, n) {
  const el = document.getElementById(id);
  if (el) el.textContent = n ? `${n.toLocaleString('en-IN')} open` : '';
}

function setBadge(id, n) {
  const el = document.getElementById(id);
  if (el) el.textContent = n ? String(n) : '';
}

// ===== Transfers =====
async function loadTransfers() {
  const full = activeViewId() === 'action-view'
    ? document.getElementById('transfers-full') : null;
  if (!transferList && !full) return;
  const loading = panelLoading('Working out what can be moved…');
  if (transferList) transferList.innerHTML = loading;
  if (full) full.innerHTML = loading;
  try {
    const res = await fetch(
      `/api/v1/recommendations?${getFilterParams()}&limit=${QUEUE_LIMIT}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (!data.recommendations || !data.recommendations.length) {
      const empty = panelEmpty(
        'No transfer would help in this scope — either nothing is short, or '
        + 'no facility within reach has stock to spare.');
      if (transferList) transferList.innerHTML = empty;
      if (full) full.innerHTML = empty;
      setCount('transfers-count', 0);
      return;
    }
    // `interactive` controls the element ids and the approve button. Rendering
    // the same recommendation into both views with the same id would put two
    // `rec-<id>` nodes in the document, and advanceTransfer() would update
    // whichever came first — so approving from the Action queue would silently
    // redraw the card on Today instead. Today is read-only; the work happens
    // in the queue.
    const card = (rec, interactive) => `
      <div class="item-card"${interactive ? ` id="rec-${rec.recommendation_id}"` : ''}>
        <div class="card-header">
          <span style="font-weight:700; color:var(--gray-900);">
            ${venBadge(rec.ven_class)} ${rec.requested_item_name}
          </span>
          <span class="card-badge ${rec.status === 'stocked_out' ? 'badge-critical' : 'badge-info'}">${(rec.status || 'reorder').replace('_', ' ')}</span>
        </div>
        ${rec.is_substitution ? `
        <div class="substitution-note">
          <strong>Therapeutic substitute.</strong>
          ${rec.to_facility_name} needs <em>${rec.requested_item_name}</em>;
          this transfer supplies <em>${rec.supplied_item_name}</em>, the same
          ATC class. Confirm clinical suitability before dispensing.
        </div>` : ''}
        <div class="transfer-flow">
          <div class="transfer-node">
            <div class="transfer-node-label surplus">Surplus</div>
            <div class="transfer-node-name">${rec.from_facility_name || ''}</div>
            <div class="transfer-node-id">${rec.from_facility_id}</div>
            <div class="transfer-node-cover">${rec.donor_cover_before}d → ${rec.donor_cover_after}d</div>
          </div>
          <div class="transfer-arrow">
            <span class="transfer-qty">${rec.quantity} ${rec.unit || 'units'}</span>
            <span class="transfer-arrow-icon">→</span>
            <span class="transfer-dist">${Math.round(rec.distance_km)} km</span>
          </div>
          <div class="transfer-node">
            <div class="transfer-node-label deficit">Deficit</div>
            <div class="transfer-node-name">${rec.to_facility_name || ''}</div>
            <div class="transfer-node-id">${rec.to_facility_id}</div>
            <div class="transfer-node-cover">${rec.receiver_cover_before}d → ${rec.receiver_cover_after}d</div>
          </div>
        </div>
        <div class="fefo-note">
          <strong>FEFO</strong> · moving batch expiring
          ${rec.fefo_expiry_date} (${rec.fefo_days_to_expiry} days)
          ${rec.waste_avoided_units > 0
            ? ` · avoids ${rec.waste_avoided_units} ${rec.unit} of expiry waste`
            : ' · no expiry risk on this batch'}
        </div>
        ${interactive ? `
        <div class="lifecycle" id="lc-${rec.recommendation_id}">
          <button class="btn btn-primary btn-full"
                  onclick="advanceTransfer('${rec.recommendation_id}','approve')">
            Approve transfer
          </button>
        </div>` : ''}
      </div>
    `;

    const recs = data.recommendations;
    if (transferList) {
      transferList.innerHTML =
        recs.slice(0, TODAY_PREVIEW).map(r => card(r, false)).join('');
      setMore('transfers-more', recs.length, 'recommended transfer');
    }
    if (full) full.innerHTML = recs.map(r => card(r, true)).join('');
    setCount('transfers-count', recs.length);
  } catch (e) {
    const err = panelError(e.message, 'loadTransfers');
    if (transferList) transferList.innerHTML = err;
    if (full) full.innerHTML = err;
  }
}

// ===== MediaRecorder =====
let mediaRecorder, audioChunks = [];
micBtn.addEventListener('mousedown',  startRecording);
micBtn.addEventListener('mouseup',    stopRecording);
micBtn.addEventListener('touchstart', startRecording);
micBtn.addEventListener('touchend',   stopRecording);

async function startRecording(e) {
  e.preventDefault();
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];
    mediaRecorder.ondataavailable = e => { if (e.data.size > 0) audioChunks.push(e.data); };
    mediaRecorder.onstop = () => processAudio(new Blob(audioChunks, { type: 'audio/webm' }));
    mediaRecorder.start();
    micBtn.classList.add('recording'); micRing.classList.add('recording');
    micStatus.textContent = 'Listening… Release to submit';
    captureResult.classList.add('hidden');
  } catch (err) { micStatus.textContent = 'Microphone access denied'; }
}

function stopRecording(e) {
  e.preventDefault();
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.stop(); mediaRecorder.stream.getTracks().forEach(t => t.stop());
    micBtn.classList.remove('recording'); micRing.classList.remove('recording');
    micStatus.textContent = 'Processing…';
  }
}

async function processAudio(blob) {
  if (!navigator.onLine) {
    const id = Date.now().toString();
    const tx = db.transaction(["offline-queue"], "readwrite");
    tx.objectStore("offline-queue").put({ id, facility_id: "IN-101234", audioBlob: blob });
    micStatus.textContent = 'Saved offline — will sync when online';
    return;
  }
  try {
    const fd = new FormData();
    fd.append("facility_id", "IN-101234");
    fd.append("file", blob, "recording.webm");
    const res = await fetch("/api/v1/voice-note", { method: "POST", body: fd });
    const data = await res.json();
    micStatus.textContent = 'Press and hold to record';
    showCaptureResult(data);
  } catch (e) { micStatus.textContent = 'Error — try again'; }
}

function showCaptureResult(data) {
  captureResult.classList.remove('hidden');
  if (data.events && data.events.length) {
    captureContent.innerHTML = data.events.map(ev => `
      <div style="padding:8px 0; border-bottom:1px solid var(--gray-200);">
        <strong>${ev.item_name || 'Unknown'}</strong> — ${ev.quantity} ${ev.unit || ''}<br>
        <span style="color:var(--gray-500);font-size:0.8rem;">${ev.event_type || 'recorded'}</span>
      </div>
    `).join('');
  } else {
    captureContent.innerHTML = '<p style="color:var(--gray-500);">No items detected — try again.</p>';
  }
}

// ===== Init =====
// Geography loads first so the dashboard queries a state that actually exists
// in the facility master rather than a hardcoded default.
(async () => {
  // Geography first: everything below is scoped by it. Its own catch already
  // shows "States unavailable" in the dropdown, so a failure here must not
  // stop the panels rendering their own error states.
  try {
    await loadStates();
  } catch (e) {
    console.error('Geography failed; panels will show their own errors', e);
  }
  updateSubtitle();
  // One dispatcher, shared with switchTab and every filter change. This used
  // to name five loaders directly — the old single-dashboard list — which is
  // how it ended up calling a function that wrote into a deleted element.
  refreshAll();
})();

// ===== Analytics Charts =====
let forecastChart = null;
let doughnutChart = null;
let barChart = null;

async function loadChart(days) {
  currentChartDays = days;
  document.querySelectorAll('.chart-btn').forEach(btn => btn.classList.remove('active'));
  const activeBtn = document.querySelector(`.chart-btn[onclick="loadChart(${days})"]`);
  if(activeBtn) activeBtn.classList.add('active');

  // 1. Forecast — real history plus real ML.FORECAST output. Nothing about
  // this curve is computed in the browser.
  try {
    const res = await fetch(`/api/v1/forecast-chart?days=${days}&${getFilterParams()}`);
    if (!res.ok) throw new Error((await res.json()).detail || `HTTP ${res.status}`);
    const data = await res.json();
    const ctx = document.getElementById('forecastChart');
    if(ctx) {
      if(forecastChart) forecastChart.destroy();
      forecastChart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: data.labels,
          datasets: [
            { label: 'Dispensed (recorded)', data: data.historical, borderColor: '#94a3b8', backgroundColor: 'rgba(148,163,184,0.1)', fill: true, tension: 0.3, pointRadius: 0 },
            { label: 'ARIMA_PLUS forecast', data: data.forecast, borderColor: '#1e3a8a', backgroundColor: 'rgba(30,58,138,0.08)', borderDash: [5,5], fill: true, tension: 0.3, pointRadius: 2 },
            { label: `${Math.round(data.confidence_level*100)}% interval`, data: data.upper, borderColor: 'rgba(30,58,138,0.25)', borderWidth: 1, pointRadius: 0, fill: '+1' },
            { label: '', data: data.lower, borderColor: 'rgba(30,58,138,0.25)', borderWidth: 1, pointRadius: 0, fill: false }
          ]
        },
        options: {
          responsive:true, maintainAspectRatio:false,
          plugins:{
            legend:{ position:'bottom', labels:{ font:{ size:11, weight:'600' }, filter: it => it.text !== '' } },
            title:{ display:true, text: `${data.item_name} — ${data.facility_name}`, font:{ size:12, weight:'600' } }
          },
          scales:{ y:{ beginAtZero:true, title:{ display:true, text: data.unit || 'Qty', font:{ size:11 } } } }
        }
      });
    }
    setChartNote('forecast-note', `Source: ${data.source}`);
  } catch(e) {
    console.error('Forecast chart failed', e);
    setChartNote('forecast-note', `Forecast unavailable: ${e.message}`);
  }

  // 2 & 3. Network stock health and critical shortages — both derived from the
  // model and the dispensing ledger.
  try {
    const res = await fetch(`/api/v1/stock-health?${getFilterParams()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const h = await res.json();

    const ctxD = document.getElementById('healthDoughnutChart');
    if(ctxD) {
      if(doughnutChart) doughnutChart.destroy();
      doughnutChart = new Chart(ctxD, {
        type: 'doughnut',
        data: {
          labels: ['Healthy (14+ days)', 'Low (7-14 days)', 'Critical (<7 days)'],
          datasets: [{ data: [h.healthy, h.low, h.critical], backgroundColor: ['#16a34a','#f97316','#ef4444'], borderWidth:0 }]
        },
        options: { responsive:true, maintainAspectRatio:false, cutout:'72%', plugins:{ legend:{ position:'bottom', labels:{ font:{ size:11, weight:'600' } } } } }
      });
    }

    const ctxB = document.getElementById('shortagesBarChart');
    if(ctxB) {
      if(barChart) barChart.destroy();
      barChart = new Chart(ctxB, {
        type: 'bar',
        data: {
          labels: h.shortages.map(s => `${s.item_name} (${s.ven_class[0]})`),
          datasets: [{ label: 'Deficit', data: h.shortages.map(s => s.deficit_units), backgroundColor: '#1e3a8a', borderRadius:4 }]
        },
        options: {
          responsive:true, maintainAspectRatio:false,
          plugins:{
            legend:{ display:false },
            tooltip:{ callbacks:{ afterLabel: c => `${h.shortages[c.dataIndex].facilities_affected} facilities · ${h.shortages[c.dataIndex].ven_class}` } }
          },
          scales:{ y:{ beginAtZero:true, title:{ display:true, text:'Units short of 14-day cover', font:{ size:10 } } } }
        }
      });
    }
    setChartNote('health-note', `${h.total_series.toLocaleString('en-IN')} facility-item series · mean cover ${h.mean_days_of_cover} days · ${h.on_hand_basis}`);
  } catch(e) {
    console.error('Stock health failed', e);
    setChartNote('health-note', 'Stock health unavailable');
  }
}

// The single clearest illustration of the lead-time rule: two real PHCs,
// the same medicine, reorder points that differ only by distance to the
// district warehouse.
async function loadLeadTimeContrast() {
  const section = document.getElementById('contrast-section');
  const el = document.getElementById('lead-time-contrast');
  if (!el || !section) return;
  try {
    let url = `/api/v1/lead-time-contrast?state=${encodeURIComponent(currentState)}`;
    if (currentDistrict) url += `&district=${encodeURIComponent(currentDistrict)}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const c = await res.json();
    if (!c || !c.nearest || !c.furthest) { section.hidden = true; return; }
    section.hidden = false;

    const row = (f, label) => `
      <div class="contrast-col">
        <div class="contrast-label">${label}</div>
        <div class="contrast-name">${f.facility_name}</div>
        <div class="contrast-sub">${f.district}</div>
        <div class="contrast-km">${f.distance_to_hq_km} km from district HQ</div>
        <div class="contrast-lead">${f.lead_time_days}-day lead time</div>
        <div class="contrast-rp">${Math.round(f.reorder_point)}</div>
        <div class="contrast-rp-label">reorder at, ${c.unit}</div>
        <div class="contrast-formula">
          ${Math.round(f.avg_daily_demand)}/day &times; ${f.lead_time_days}d
          + ${Math.round(f.safety_stock)} safety
        </div>
      </div>`;

    el.innerHTML = `
      <p class="contrast-intro">
        ${venBadge(c.ven_class)} <strong>${c.item_name}</strong> at two real PHCs.
        ${c.furthest.facility_name} is
        ${c.furthest.distance_to_hq_km} km from its district warehouse and waits
        <strong>${c.extra_lead_days} days longer</strong> for resupply than
        ${c.nearest.facility_name}.
      </p>
      <p class="contrast-intro">
        Holding its own demand constant, that distance alone raises its reorder
        point from ${Math.round(c.furthest_reorder_if_near)} to
        <strong>${Math.round(c.furthest.reorder_point)} ${c.unit}</strong> —
        ${Math.round(c.extra_units_from_distance)} extra units to hit the same
        95% service level. The flat 14-day rule would have set it at
        ${Math.round(c.furthest_flat_threshold)}, leaving it
        <strong>${Math.round(c.flat_rule_shortfall)} ${c.unit} short</strong>.
      </p>
      <div class="contrast-grid">
        ${row(c.nearest, 'Near the warehouse')}
        <div class="contrast-vs">vs</div>
        ${row(c.furthest, 'Remote')}
      </div>
      <p class="chart-note">
        Lead time is derived from distance to the district hospital, a
        documented proxy — not a measured delivery time. See Data/README.md.
      </p>`;
  } catch (e) {
    console.error('Lead-time contrast failed', e);
    section.hidden = true;
  }
}

async function loadReporting() {
  const el = document.getElementById('reporting-summary');
  if (!el) return;
  try {
    const res = await fetch(`/api/v1/reporting?${getFilterParams()}&limit=5`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const s = data.summary || {};
    if (!s.facilities) { el.innerHTML = '<p class="chart-note">No facilities in scope.</p>'; return; }
    const worst = (data.facilities || []).filter(f => f.reporting_status !== 'complete').slice(0, 4);
    el.innerHTML = `
      <div class="reporting-bar">
        <div class="reporting-seg complete" style="flex:${s.complete}" title="${s.complete} reporting fully"></div>
        <div class="reporting-seg partial" style="flex:${s.partial}" title="${s.partial} reporting partially"></div>
        <div class="reporting-seg silent" style="flex:${s.silent}" title="${s.silent} silent"></div>
      </div>
      <p class="chart-note">
        <strong>${Math.round((s.mean_consistency || 0) * 100)}%</strong> of expected stock counts arrived
        across ${s.facilities} facilities —
        ${s.complete} complete, ${s.partial} partial,
        <strong>${s.silent} silent</strong>.
        A facility that stops reporting looks healthy on every dashboard above it.
      </p>
      ${worst.length ? `<div class="reporting-list">${worst.map(f => `
        <div class="reporting-row">
          <span>${f.facility_name} <span class="contrast-sub">${f.district}</span></span>
          <span class="reporting-pct ${f.reporting_status}">${Math.round(f.reporting_consistency * 100)}% · last report ${f.days_since_last_report}d ago</span>
        </div>`).join('')}</div>` : ''}`;
  } catch (e) {
    console.error('Reporting failed', e);
    el.innerHTML = '<p class="chart-note">Reporting data unavailable.</p>';
  }
}

// The resource selector is a segmented control on Network now, not a filter
// dropdown on the dashboard. Three resources, one model, visibly.
function onResourceSegment(resource) {
  setResource(resource);
}

// The resource selector is back on the national picture. Removing it was the
// wrong call: it looked dead only because the panel it drove had moved to
// Network, and deleting the control made "medicines only" permanent on the
// landing view. Two controls now exist — a dropdown beside the geography
// filters and the segmented control on Network — and this keeps them in step
// so they can never disagree about what is selected.
function setResource(resource) {
  if (resource === currentResource) return;
  currentResource = resource;
  document.querySelectorAll('#resource-segmented .segment').forEach(b =>
    b.classList.toggle('active', b.dataset.resource === resource));
  const sel = document.getElementById('resource-filter');
  if (sel && sel.value !== resource) sel.value = resource;
  refreshAll();
}

function onResourceChange() {
  const sel = document.getElementById('resource-filter');
  if (sel) setResource(sel.value);
}
window.onResourceChange = onResourceChange;
window.onResourceSegment = onResourceSegment;

// The resource dropdown that used to live in the Today filter bar is gone.
// It set `currentResource`, which drives the resource panel — and that panel
// moved to Network in the restructure. So changing it on Today updated a panel
// on a hidden view and appeared to do nothing at all. Resource is a Network
// concern, and the segmented control there is the only control for it.
window.onResourceSegment = onResourceSegment;

function pct(v) { return v === null || v === undefined ? '—' : `${Math.round(v)}%`; }

async function loadResourcePanel() {
  const panel = document.getElementById('resource-panel');
  const title = document.getElementById('resource-panel-title');
  const body  = document.getElementById('resource-panel-body');
  if (!panel || !body) return;

  if (currentResource === 'medicine') {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  body.innerHTML = '<p class="chart-note">Loading…</p>';

  try {
    if (currentResource === 'bed') {
      title.textContent = '🛏️ Bed capacity and pressure';
      const res = await fetch(`/api/v1/beds?${getFilterParams()}&limit=8`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const { summary, facilities } = await res.json();
      const ref = await (await fetch(`/api/v1/beds/referrals?${getFilterParams()}&limit=4`)).json();

      body.innerHTML = `
        <div class="resource-tiles">
          <div class="resource-tile"><span class="rt-value">${(summary.total_beds ?? 0).toLocaleString('en-IN')}</span><span class="rt-label">beds (IPHS norm)</span></div>
          <div class="resource-tile"><span class="rt-value">${pct(summary.mean_occupancy_pct)}</span><span class="rt-label">mean occupancy</span></div>
          <div class="resource-tile"><span class="rt-value">${(summary.free_beds ?? 0).toLocaleString('en-IN')}</span><span class="rt-label">free beds</span></div>
          <div class="resource-tile ${summary.turned_away_30d > 0 ? 'rt-alert' : ''}"><span class="rt-value">${(summary.turned_away_30d ?? 0).toLocaleString('en-IN')}</span><span class="rt-label">turned away, 30d</span></div>
        </div>
        <p class="chart-note">${summary.capacity_basis || ''}</p>
        ${(ref.referrals || []).length ? `
        <p class="resource-note"><strong>Beds cannot be transferred.</strong>
          Where a facility is full, the answer is a referral route:</p>
        <div class="reporting-list">${ref.referrals.map(r => `
          <div class="reporting-row">
            <span>${r.from_facility_name} <span class="contrast-sub">${r.from_turned_away} turned away</span></span>
            <span class="reporting-pct">→ ${r.to_facility_name}, ${r.to_free_beds} free, ${r.distance_km} km</span>
          </div>`).join('')}</div>` : ''}
        <div class="reporting-list">${(facilities || []).slice(0, 6).map(f => `
          <div class="reporting-row">
            <span>${f.facility_name} <span class="contrast-sub">${f.district}${f.beds_are_day_care ? ' · day-care' : ''}</span></span>
            <span class="reporting-pct ${f.status === 'over_capacity' ? 'silent' : f.status === 'under_pressure' ? 'partial' : ''}">${f.mean_occupied}/${f.bed_capacity} beds · ${pct((f.occupancy_rate || 0) * 100)}</span>
          </div>`).join('')}</div>`;
    } else {
      title.textContent = '👥 Personnel establishment and attendance';
      const res = await fetch(`/api/v1/personnel?${getFilterParams()}&limit=8`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const { summary, facilities } = await res.json();
      const alloc = await (await fetch(`/api/v1/personnel/reallocation?${getFilterParams()}&limit=4`)).json();

      body.innerHTML = `
        <div class="resource-tiles">
          <div class="resource-tile"><span class="rt-value">${(summary.sanctioned_posts ?? 0).toLocaleString('en-IN')}</span><span class="rt-label">sanctioned posts</span></div>
          <div class="resource-tile"><span class="rt-value">${pct(summary.attendance_pct)}</span><span class="rt-label">attendance</span></div>
          <div class="resource-tile ${summary.unstaffed > 0 ? 'rt-alert' : ''}"><span class="rt-value">${summary.unstaffed ?? 0}</span><span class="rt-label">unstaffed posts</span></div>
          <div class="resource-tile"><span class="rt-value">${summary.critically_short ?? 0}</span><span class="rt-label">critically short</span></div>
        </div>
        <p class="chart-note">${summary.basis || ''}</p>
        <div class="reporting-list">${(summary.by_cadre || []).map(c => `
          <div class="reporting-row">
            <span>${c.cadre} <span class="contrast-sub">${c.sanctioned_posts} posts · ${pct(c.vacancy_pct)} vacant (RHS 2017)</span></span>
            <span class="reporting-pct ${c.attendance_pct < 50 ? 'silent' : c.attendance_pct < 80 ? 'partial' : ''}">${pct(c.attendance_pct)} attending</span>
          </div>`).join('')}</div>
        ${alloc.constraint ? `
        <p class="resource-note"><strong>No reallocation is possible here.</strong>
          ${alloc.constraint.why}</p>` : `
        <div class="reporting-list">${(alloc.reallocations || []).map(r => `
          <div class="reporting-row">
            <span>${r.to_facility_name} needs a ${r.cadre}</span>
            <span class="reporting-pct">← ${r.from_facility_name}, ${r.distance_km} km</span>
          </div>`).join('')}</div>`}`;
    }
  } catch (e) {
    console.error('Resource panel failed', e);
    body.innerHTML = '<p class="chart-note">Resource data unavailable.</p>';
  }
}

function setChartNote(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

// ===== Barcode Scanner =====
let html5QrcodeScanner = null;

const CAPTURE_MODES = ['voice', 'scan', 'chat'];

function switchCaptureMode(mode) {
  CAPTURE_MODES.forEach(m => {
    const tab = document.getElementById(`tab-${m}`);
    if (tab) { tab.classList.remove('active'); tab.style.borderBottom = 'none'; }
    const panel = document.getElementById(`mode-${m}`);
    if (panel) panel.style.display = 'none';
  });
  const tab = document.getElementById(`tab-${mode}`);
  if (tab) {
    tab.classList.add('active');
    tab.style.borderBottom = '2px solid var(--brand-500)';
  }
  const panel = document.getElementById(`mode-${mode}`);
  if (panel) panel.style.display = 'block';
  if (mode !== 'scan') stopScanner();
}

// Chat capture. Same endpoint family as voice and barcode, same
// {events, review_queue} response shape.
async function sendChatNote() {
  const box = document.getElementById('chat-input');
  const message = (box.value || '').trim();
  if (!message) return;
  const status = document.getElementById('mic-status');
  if (status) status.textContent = 'Extracting…';
  try {
    const fd = new FormData();
    fd.append('message', message);
    fd.append('facility_id', currentPHC || 'IN-155740');
    const res = await fetch('/api/v1/chat-note', { method: 'POST', body: fd });
    const data = await res.json();
    showCaptureResult(data);
    if (!data.error) box.value = '';
  } catch (e) {
    showCaptureResult({ error: e.message, events: [], review_queue: [] });
  } finally {
    if (status) status.textContent = 'Press and hold to record';
  }
}
window.sendChatNote = sendChatNote;

function startScanner() {
  if (html5QrcodeScanner) stopScanner();
  html5QrcodeScanner = new Html5Qrcode("reader");
  const config = { fps: 10, qrbox: { width: 250, height: 250 } };
  html5QrcodeScanner.start({ facingMode: "environment" }, config, onScanSuccess, onScanFailure)
    .catch(err => { alert("Camera access denied or unavailable."); });
}

function stopScanner() {
  if (html5QrcodeScanner) {
    html5QrcodeScanner.stop().then(() => { html5QrcodeScanner.clear(); html5QrcodeScanner = null; }).catch(err => console.error(err));
  }
}

// The scanned code is resolved server-side against the catalogue, exactly like
// a spoken name. It is never turned into an item in the browser: an
// unrecognised code has to reach the review queue, not the ledger.
async function onScanSuccess(decodedText) {
  stopScanner();
  const status = document.getElementById('mic-status');
  if (status) status.textContent = `Scanned ${decodedText.substring(0, 24)} — matching…`;
  switchCaptureMode('voice');
  try {
    const fd = new FormData();
    fd.append('code', decodedText);
    fd.append('facility_id', currentPHC || 'IN-155740');
    const qty = window.prompt(`Scanned ${decodedText}

How many units?`, '');
    if (qty !== null && qty !== '') fd.append('quantity', parseInt(qty, 10));
    const res = await fetch('/api/v1/barcode-scan', { method: 'POST', body: fd });
    showCaptureResult(await res.json());
  } catch (e) {
    showCaptureResult({ error: e.message, events: [], review_queue: [] });
  } finally {
    if (status) status.textContent = 'Press and hold to record';
  }
}

function onScanFailure(error) { /* Silently ignore scan misses */ }


// ===== Evidence =====
// The methodology page. Judges want this; a district officer does not, which
// is why it is no longer competing for space on the daily view.
async function loadEvidence() {
  loadLeadTimeContrast();

  const evalEl = document.getElementById('exchange-eval');
  if (evalEl) {
    try {
      const d = await (await fetch('/api/v1/exchange/evaluation')).json();
      const arms = d.arms || d.evaluation || [];
      evalEl.innerHTML = arms.length ? `
        <div class="table-scroll"><table class="scenario-table">
          <thead><tr><th>Arm</th><th>Weighted MAPE</th></tr></thead>
          <tbody>${arms.map(a => `<tr class="${a.is_shipped ? 'row-warn' : ''}">
            <td>${a.label || a.arm}</td><td><strong>${a.wmape}%</strong></td></tr>`).join('')}
          </tbody></table></div>`
        : `<p class="section-note">${JSON.stringify(d).slice(0, 400)}</p>`;
    } catch (e) {
      evalEl.innerHTML = '<p class="section-note">Could not load the evaluation.</p>';
    }
  }

  const reachEl = document.getElementById('reach-panel');
  if (reachEl) {
    try {
      const d = await (await fetch('/api/v1/reach')).json();
      reachEl.innerHTML = `
        <div class="table-scroll"><table class="scenario-table">
          <thead><tr><th>Scope</th><th>Rural PHCs</th><th>Districts</th><th>People</th></tr></thead>
          <tbody>${d.tiers.map(t => `<tr>
            <td>${t.tier.replace(/_/g, ' ')}</td>
            <td>${t.phcs.toLocaleString()}</td>
            <td>${t.districts}</td>
            <td><strong>${(t.population / 1e6).toFixed(1)}M</strong></td></tr>`).join('')}
          </tbody></table></div>
        <p class="section-note">${d.counted} ${d.direction_of_error}</p>`;
    } catch (e) {
      reachEl.innerHTML = '<p class="section-note">Could not load reach.</p>';
    }
  }

  const qEl = document.getElementById('quality-panel');
  if (qEl) {
    try {
      const d = await (await fetch('/api/v1/data-quality')).json();
      qEl.innerHTML = `
        <div class="table-scroll"><table class="scenario-table">
          <thead><tr><th>Issue</th><th>Count</th><th>Effect</th></tr></thead>
          <tbody>${(d.exclusions || []).map(x => `<tr>
            <td>${x.issue}</td><td><strong>${x.count.toLocaleString()}</strong></td>
            <td>${x.effect}</td></tr>`).join('')}
          </tbody></table></div>
        <p class="section-note">Coordinates are never corrected — inferring a
        swapped latitude and longitude is a guess, and guesses do not go into a
        government dataset.</p>`;
    } catch (e) {
      qEl.innerHTML = '<p class="section-note">Could not load data quality.</p>';
    }
  }
}


// ===== The national picture =====
// Written for someone who has to decide something, not someone reading a
// dashboard. Every panel answers a question in the order it gets asked: is it
// holding, where is it not, what is coming, could we absorb a shock.
//
// One fetch. Nine panels fetched separately would stack nine ~1.3s BigQuery
// job floors, and the page would take fifteen seconds to say anything.

// A consultant leads with the answer, then supports it. Without this the page
// opens with three cards and leaves the reader to decide whether that is a
// good state of affairs or a bad one.
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

  return `
    <div class="verdict ${level}">
      <div class="verdict-main">
        <span class="verdict-label">${label}</span>
        <p class="verdict-line">
          <strong>${pct}%</strong> of the medicines we track are running low
          &mdash; <strong>${vital}</strong> of them life-saving, and
          <strong>${out}</strong> already completely out.
          ${absorb3 ? `If demand suddenly tripled, only <strong>${absorb3.pct}%</strong> of district medicine stocks could cope.` : ''}
        </p>
      </div>
      <div class="verdict-aside">
        <span class="verdict-figure">${d.transfer_only || 0}</span>
        <span class="verdict-caption">medicines would run out before a new
          order could reach the health centre.<br>
          Ordering cannot fix these &mdash; only moving stock that already exists.</span>
      </div>
    </div>`;
}

function postureCard(title, headline, figures, tone, provenance) {
  return `
    <div class="posture-card ${tone || ''}">
      <div class="posture-title">${title}</div>
      <p class="posture-headline">${headline}</p>
      <div class="posture-figures">
        ${figures.map(f => `<span><strong>${f[1]}</strong> ${f[0]}</span>`).join('')}
      </div>
      ${provenance ? `<p class="posture-provenance">${provenance}</p>` : ''}
    </div>`;
}

async function loadExecutive() {
  const grid = document.getElementById('posture-grid');
  const absorb = document.getElementById('absorption-panel');
  const warn = document.getElementById('early-warnings');
  if (grid) grid.innerHTML = panelLoading('Reading the national position…');

  try {
    const scope = currentState ? `?state=${encodeURIComponent(currentState)}` : '';
    const res = await fetch(`/api/v1/executive${scope}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const d = await res.json();
    const h = d.headline || {};
    const m = d.medicines || {}, b = d.beds || {}, s = d.personnel || {};

    // Tone is driven by the numbers, not chosen: a fifth of stock lines short
    // is not a green state and must not be coloured like one.
    const medTone = (m.vital_short > 0) ? 'bad' : (m.below_reorder > 0 ? 'warn' : 'ok');

    const verdict = document.getElementById('verdict-bar');
    if (verdict) verdict.innerHTML = verdictBar(d);

    renderKpis(d);
    renderCoverChart(d);
    renderDistrictChart(d);
    renderVen(d);

    grid.innerHTML =
      postureCard('Medicines', h.medicines, [
        ['tracked', (m.tracked || 0).toLocaleString('en-IN')],
        ['running low', (m.below_reorder || 0).toLocaleString('en-IN')],
        ['completely out', (m.stocked_out || 0).toLocaleString('en-IN')],
        ['life-saving, low', (m.vital_short || 0).toLocaleString('en-IN')],
      ], medTone, 'Stock counts come from the ledger; expected demand from the trained model.')
      + postureCard('Beds', h.beds, [
        ['health centres', (b.facilities || 0).toLocaleString('en-IN')],
        ['beds', (b.capacity || 0).toLocaleString('en-IN')],
        ['turned away', (b.turned_away || 0).toLocaleString('en-IN')],
      ], b.turned_away > 0 ? 'warn' : 'ok', 'Bed numbers are the IPHS 2022 government norm. How full they are is modelled from real HMIS admissions.')
      + postureCard('Staff', h.personnel, [
        ['health centres', (s.facilities || 0).toLocaleString('en-IN')],
        ['posts unfilled', `${Math.round(100 * (s.mean_vacancy || 0))}%`],
        ['roles with a gap', (s.cadres_with_a_gap || 0).toLocaleString('en-IN')],
      ], (s.mean_vacancy || 0) > 0.15 ? 'bad' : 'warn', 'Vacancy is from Rural Health Statistics 2017. Day-to-day attendance is modelled.');

    if (absorb) {
      const rows = d.absorption || [];
      absorb.innerHTML = rows.length ? `
        ${rows.map(a => `
          <div class="absorb-row">
            <span class="absorb-label">${a.multiplier}&times; demand</span>
            <div class="absorb-bar"><div class="absorb-fill ${a.pct < 35 ? 'bad' : a.pct < 70 ? 'warn' : 'ok'}" style="width:${a.pct}%"></div></div>
            <span class="absorb-pct">${a.pct}% hold</span>
          </div>`).join('')}
        <p class="section-note">${h.transfer_only || ''}</p>`
        : panelEmpty('Absorption not computed for this scope.');
    }

    if (warn) {
      const rows = d.early_warnings || [];
      warn.innerHTML = rows.length ? rows.map(w => `
        <div class="alert-card severity-${w.signal_class === 'leading' ? 'critical' : 'warning'}">
          <div class="alert-body">
            <div class="alert-title">${signalBadge(w.signal_class)} ${w.signal_indicator || w.atc_classes}</div>
            <div class="alert-detail">
              <strong>${w.signal_means || w.atc_classes} is ${w.surge_multiplier}&times; expected</strong>
              in ${w.district_key}, ${w.month}.
            </div>
            <div class="alert-detail muted">
              ${w.medicines
                ? `Medicines affected: ${w.medicines}`
                : `Affects ${w.class_count} medicine `
                  + `${w.class_count === 1 ? 'group' : 'groups'} (${w.atc_classes})`}
            </div>
          </div>
          <div class="alert-days ${w.signal_class === 'leading' ? 'critical' : 'warning'}">
            ${w.surge_multiplier}&times;<span class="alert-days-label">vs expected</span>
          </div>
        </div>`).join('')
        : panelEmpty('No signal in this scope departs from the pooled seasonal pattern.');
    }

    setSyncState(true);
  } catch (e) {
    if (grid) grid.innerHTML = panelError(e.message, 'loadExecutive');
    setSyncState(false, e.message);
  }
}

// ===== The visual layer =====
//
// This page used to be ninety stacked text cards. Every number was present and
// none of it was legible: a reader had to parse prose to find out whether the
// network was holding. The rule applied here is the boring one — the data's
// job picks the form, and colour comes last.
//
// PALETTE. Two colours carry meaning, and they were validated rather than
// chosen by eye: #b91c1c against #0369a1 scores dE 20.6 under protanopia and
// 29.6 in normal vision, both clear of the floors, and each clears 3:1 against
// the page surface. A five-step red-amber-green ramp was tried first for the
// cover buckets and failed: five hues from one family score dE 2.9 under
// deuteranopia, and the amber sat at 1.87:1 on a near-white surface. So the
// cover chart uses EMPHASIS instead — the buckets that need action are red,
// the rest are recessive grey — which is both safer and a clearer story.

const INK = '#334155';        // axis and label text, never a series colour
const GRID = '#e2e8f0';
const URGENT = '#b91c1c';     // needs action now
const CALM = '#94a3b8';       // context, deliberately recessive
const VITAL = '#b91c1c';
const OTHER = '#0369a1';

let coverChart = null, districtChart = null;

function kpiTile(value, label, note, tone) {
  return `
    <div class="kpi-tile ${tone || ''}">
      <div class="kpi-value">${value}</div>
      <div class="kpi-label">${label}</div>
      ${note ? `<div class="kpi-note">${note}</div>` : ''}
    </div>`;
}

// Five tiles, not eight, and worst first.
//
// The people who read this run health services; they are not analysts, and
// eight numbers in a row is a wall rather than a summary. So the row answers
// five questions in the order they get asked — what is gone, what is dangerous,
// how much in total, how far it has spread, and could we take a shock — and it
// answers them in the words a district officer would use, not in the words the
// schema uses. "Below reorder point" is a phrase from the model; "running low"
// is the thing it means.
//
// Beds and staff moved out of this row rather than off the page: they are the
// cards directly underneath, in sentences. A ninth number would not have been
// read; a sentence about patients turned away is.
//
// `transfer_only` also left the row because it was already the large red figure
// in the verdict bar immediately above, and saying it twice bought nothing.
function renderKpis(d) {
  const host = document.getElementById('kpi-row');
  if (!host) return;
  const m = d.medicines || {};
  const n = v => (v || 0).toLocaleString('en-IN');
  const absorb3 = (d.absorption || []).find(a => a.multiplier === 3);

  host.innerHTML =
      kpiTile(n(m.stocked_out), 'Completely out of stock',
              'Nothing on the shelf right now',
              m.stocked_out > 0 ? 'bad' : 'ok')
    + kpiTile(n(m.vital_short), 'Life-saving medicines running low',
              'Death or serious harm if these run out',
              m.vital_short > 0 ? 'bad' : 'ok')
    + kpiTile(n(m.below_reorder), 'Medicines running low in total',
              `Out of ${n(m.tracked)} being tracked`,
              m.below_reorder > 0 ? 'warn' : 'ok')
    + kpiTile(`${n(m.districts_short)}<span class="kpi-of"> of ${n(m.districts)}</span>`,
              'Districts affected',
              'Have at least one medicine running low',
              (m.districts_short || 0) > 0 ? 'warn' : 'ok')
    // Deliberately the share of district–medicine stocks, not of districts.
    // Saying "districts" would read better and be false.
    + kpiTile(absorb3 ? `${absorb3.pct}%` : '&mdash;',
              'Ready for a sudden surge',
              'Share of district medicine stocks that could cope if demand '
              + 'tripled, using supplies already nearby',
              absorb3 && absorb3.pct < 35 ? 'bad' : 'warn');
}

// A count of shortages is a number. A timetable is a plan. Emphasis, not a
// five-hue ramp: the two buckets that need action this week are red, the rest
// recede.
function renderCoverChart(d) {
  const el = document.getElementById('cover-chart');
  if (!el || typeof Chart === 'undefined') return;
  const rows = d.cover_buckets || [];
  const cap = document.getElementById('cover-caption');

  if (!rows.length) {
    if (cap) cap.innerHTML = 'No medicine here has enough usage history to project yet.';
    return;
  }

  const urgent = rows.filter(r => r.sort_order <= 2).reduce((a, r) => a + r.n, 0);
  const total = rows.reduce((a, r) => a + r.n, 0);

  if (coverChart) coverChart.destroy();
  coverChart = new Chart(el.getContext('2d'), {
    type: 'bar',
    data: {
      labels: rows.map(r => r.bucket),
      datasets: [{
        label: 'Medicines',
        data: rows.map(r => r.n),
        backgroundColor: rows.map(r => r.sort_order <= 2 ? URGENT : CALM),
        borderRadius: 4,
        borderSkipped: 'bottom',
        maxBarThickness: 64
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },   // one series; the heading names it
        tooltip: {
          callbacks: {
            label: c => `${c.parsed.y.toLocaleString('en-IN')} medicines`
                        + ` (${Math.round(100 * c.parsed.y / total)}%)`
          }
        }
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: INK, font: { size: 11 } } },
        y: { beginAtZero: true, grid: { color: GRID },
             ticks: { color: INK, font: { size: 11 },
                      callback: v => v.toLocaleString('en-IN') } }
      }
    }
  });

  if (cap) {
    cap.innerHTML = `<strong>${urgent.toLocaleString('en-IN')} medicines run out `
      + `within a week</strong> &mdash; ${Math.round(100 * urgent / total)}% of `
      + `everything we track. Medicines with no usage history yet are left out `
      + `rather than counted as healthy.`;
  }
}

// Districts are nominal, so a value-ramp across them would burn the colour
// channel on information the bar length already carries. The split that DOES
// carry information is Vital against the rest.
function renderDistrictChart(d) {
  const el = document.getElementById('district-chart');
  if (!el || typeof Chart === 'undefined') return;
  const rows = d.worst_districts || [];
  const cap = document.getElementById('district-caption');

  if (!rows.length) {
    if (cap) cap.innerHTML = 'No district here has a medicine running low.';
    return;
  }

  if (districtChart) districtChart.destroy();
  districtChart = new Chart(el.getContext('2d'), {
    type: 'bar',
    data: {
      labels: rows.map(r => r.district),
      datasets: [
        { label: 'Life-saving', data: rows.map(r => r.vital_short),
          backgroundColor: VITAL, borderRadius: 3, maxBarThickness: 22 },
        { label: 'Other medicines',
          data: rows.map(r => Math.max(0, (r.short || 0) - (r.vital_short || 0))),
          backgroundColor: OTHER, borderRadius: 3, maxBarThickness: 22 }
      ]
    },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: 'top', align: 'end',
                  labels: { color: INK, boxWidth: 10, boxHeight: 10,
                            usePointStyle: true, pointStyle: 'rectRounded',
                            font: { size: 11 } } },
        tooltip: {
          callbacks: {
            afterBody: items => {
              const r = rows[items[0].dataIndex];
              return r.stocked_out
                ? `${r.stocked_out} completely out of stock` : '';
            }
          }
        }
      },
      scales: {
        x: { stacked: true, beginAtZero: true, grid: { color: GRID },
             ticks: { color: INK, font: { size: 11 }, precision: 0 } },
        y: { stacked: true, grid: { display: false },
             ticks: { color: INK, font: { size: 11 } } }
      }
    }
  });

  const worst = rows[0];
  if (cap) {
    cap.innerHTML = `<strong>${worst.district}</strong> needs attention first: `
      + `${worst.vital_short} life-saving `
      + `${worst.vital_short === 1 ? 'medicine' : 'medicines'} running low`
      + `${worst.stocked_out ? `, and ${worst.stocked_out} already completely out` : ''}.`;
  }
}

// Three ordered classes and a share each: a meter reads this better than a pie,
// and the label carries the identity so colour need not.
function renderVen(d) {
  const host = document.getElementById('ven-panel');
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

// ===== Am I running the build the server is serving? =====
//
// Twice now a deploy reached the browser only partly — new HTML with an old
// stylesheet — and the page looked broken in a way no error surfaced. The
// asset URLs now carry a build stamp, which should make that impossible, but
// "should be impossible" is what was believed the first two times.
//
// So the page checks. The stamp in the footer is written by the server into
// the HTML this browser actually loaded; /api/v1/build reports what the server
// is serving now. If they differ, the browser is running something stale and
// says so, with a button, instead of leaving the reader to wonder why the
// layout is wrong.
async function checkBuild() {
  const el = document.getElementById('build-stamp');
  if (!el) return;
  const mine = (el.textContent || '').trim();
  try {
    const res = await fetch('/api/v1/build', { cache: 'no-store' });
    if (!res.ok) return;
    const { build } = await res.json();
    if (!build || !mine || build === mine) return;
    el.classList.add('stale');
    el.innerHTML = `${mine} &rarr; ${build}
      <button class="link-button" onclick="hardReload()">Update</button>`;
  } catch (e) {
    // Offline is a normal state here, not a failure worth reporting.
  }
}

// Drop every cache this origin owns and reload. A plain reload can be served
// by the very service worker that is holding the stale copy.
async function hardReload() {
  try {
    if (window.caches) {
      const keys = await caches.keys();
      await Promise.all(keys.map(k => caches.delete(k)));
    }
    if (navigator.serviceWorker) {
      const regs = await navigator.serviceWorker.getRegistrations();
      await Promise.all(regs.map(r => r.unregister()));
    }
  } catch (e) {
    console.warn('Could not clear caches; reloading anyway', e);
  }
  location.reload();
}

checkBuild();
