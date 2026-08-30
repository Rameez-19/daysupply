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

  if (tabId === 'review-view')   loadReviewQueue();
  if (tabId === 'alerts-view')   loadAlerts();
  if (tabId === 'transfer-view') loadTransfers();
}
sidebarItems.forEach(btn => btn.addEventListener('click', () => switchTab(btn.dataset.tab)));
bottomItems.forEach(btn  => btn.addEventListener('click', () => switchTab(btn.dataset.tab)));
window.switchTab = switchTab;

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
let currentState = "Telangana";
let currentDistrict = "";
let currentPHC = "";
let currentChartDays = 7;
let currentPHCName = "";

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
    // Default to the first state that has demo coverage, else the first state.
    const preferred = states.find(s => s.state === currentState) || states[0];
    if (preferred) {
      currentState = preferred.state;
      sel.value = currentState;
    }
    await loadDistricts();
  } catch (e) {
    console.error('Failed to load states', e);
    setDropdownError(sel, 'States unavailable');
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
    setOptions(sel, `All Districts (${districts.length})`, districts, 'district',
      r => `${r.district} — ${r.phc_count} PHCs`);
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
  const scope = currentPHCName || currentDistrict
    || (currentState ? `${currentState} State` : 'All India');
  document.getElementById('dashboard-subtitle').textContent = `${scope} Network — Real-time overview`;
}

function getFilterParams() {
  let params = `state=${encodeURIComponent(currentState)}`;
  if (currentDistrict) params += `&district=${encodeURIComponent(currentDistrict)}`;
  if (currentPHC) params += `&phc=${encodeURIComponent(currentPHC)}`;
  return params;
}

function refreshAll() {
  loadDashboard();
  loadChart(currentChartDays);
  loadLeadTimeContrast();
  loadReporting();
}

// Make filter functions global
window.onStateChange = onStateChange;
window.onDistrictChange = onDistrictChange;
window.onPHCChange = onPHCChange;

// ===== Dashboard =====
async function loadDashboard() {
  try {
    const res = await fetch(`/api/v1/stats?${getFilterParams()}`);
    const stats = await res.json();
    renderStats(stats);
    // Update last synced
    const syncEl = document.getElementById('last-synced');
    if (syncEl) syncEl.textContent = `Last synced: ${new Date().toLocaleTimeString()}`;
  } catch (e) {
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
  document.getElementById('stats-grid').innerHTML = `
    <div class="stat-card clickable" onclick="switchTab('dashboard-view')">
      <div class="stat-icon" style="background:linear-gradient(135deg,#1e3a8a,#3b82f6);">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
      </div>
      <div class="stat-info">
        <span class="stat-value">${(s.facilities ?? 0).toLocaleString('en-IN')}</span>
        <span class="stat-label">Health Facilities</span>
        <span class="stat-delta">${(s.phcs ?? 0).toLocaleString('en-IN')} PHCs</span>
      </div>
    </div>
    <div class="stat-card clickable" onclick="switchTab('capture-view')">
      <div class="stat-icon" style="background:linear-gradient(135deg,#16a34a,#22c55e);">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
      </div>
      <div class="stat-info">
        <span class="stat-value">${s.captures_today}</span>
        <span class="stat-label">Voice Captures Today</span>
        ${deltaHtml(s.delta_captures)}
      </div>
    </div>
    <div class="stat-card clickable" onclick="switchTab('alerts-view')">
      <div class="stat-icon" style="background:linear-gradient(135deg,#f97316,#fb923c);">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/></svg>
      </div>
      <div class="stat-info">
        <span class="stat-value">${s.stockout_alerts}</span>
        <span class="stat-label">Stockout Alerts</span>
        ${deltaHtml(s.delta_alerts)}
      </div>
    </div>
    <div class="stat-card clickable" onclick="switchTab('transfer-view')">
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
    html += `<button onclick="switchTab('alerts-view')" style="width:100%; margin-top:8px; padding:8px; background:transparent; border:1px dashed var(--border); border-radius:6px; color:var(--brand-500); font-weight:600; cursor:pointer;">View all ${alerts.length} alerts →</button>`;
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
    reviewList.innerHTML = data.items.map(item => `
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

function approveItem(id) { const el = document.getElementById('item-'+id); if(el) { el.style.opacity='0.3'; el.style.pointerEvents='none'; } }
function rejectItem(id) { const el = document.getElementById('item-'+id); if(el) { el.style.opacity='0.3'; el.style.pointerEvents='none'; } }
function approveTransfer(id) { const el = document.getElementById('rec-'+id); if(el) { el.style.opacity='0.3'; el.style.pointerEvents='none'; } }

function timeAgo(iso) {
  const ms = Date.now() - new Date(iso).getTime();
  const hrs = ms / 3600000;
  if (hrs < 1) return Math.round(hrs * 60) + 'm ago';
  return Math.floor(hrs / 24) + 'd ago';
}

// ===== Alerts =====
async function loadAlerts() {
  alertsList.innerHTML = '<div class="empty-state"><p>Loading…</p></div>';
  try {
    const res = await fetch(`/api/v1/alerts?${getFilterParams()}`);
    const data = await res.json();
    if (!data.alerts || !data.alerts.length) {
      alertsList.innerHTML = '<div class="empty-state"><p>No active stockout alerts.</p></div>';
      return;
    }
    alertsList.innerHTML = data.alerts.map(a => {
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
    }).join('');
  } catch (e) {
    alertsList.innerHTML = '<div class="empty-state"><p>Could not load alerts.</p></div>';
  }
}

// ===== Transfers =====
async function loadTransfers() {
  transferList.innerHTML = '<div class="empty-state"><p>Loading…</p></div>';
  try {
    const res = await fetch(`/api/v1/recommendations?${getFilterParams()}`);
    const data = await res.json();
    if (!data.recommendations || !data.recommendations.length) {
      transferList.innerHTML = '<div class="empty-state"><p>Network is balanced — no transfers needed.</p></div>';
      return;
    }
    transferList.innerHTML = data.recommendations.map(rec => `
      <div class="item-card" id="rec-${rec.recommendation_id}">
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
        <button class="btn btn-primary btn-full" onclick="approveTransfer('${rec.recommendation_id}')">✓ Approve Transfer</button>
      </div>
    `).join('');
  } catch (e) {
    transferList.innerHTML = '<div class="empty-state"><p>Could not load transfer recommendations.</p></div>';
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
  await loadStates();
  updateSubtitle();
  loadDashboard();
  loadChart(7);
  loadLeadTimeContrast();
  loadReporting();
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

function setChartNote(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

// ===== Barcode Scanner =====
let html5QrcodeScanner = null;

function switchCaptureMode(mode) {
  document.getElementById('tab-voice').classList.remove('active');
  document.getElementById('tab-scan').classList.remove('active');
  document.getElementById('tab-voice').style.borderBottom = 'none';
  document.getElementById('tab-scan').style.borderBottom = 'none';
  document.getElementById(`tab-${mode}`).classList.add('active');
  document.getElementById(`tab-${mode}`).style.borderBottom = '2px solid var(--brand-500)';
  
  if (mode === 'voice') {
    document.getElementById('mode-voice').style.display = 'block';
    document.getElementById('mode-scan').style.display = 'none';
    stopScanner();
  } else {
    document.getElementById('mode-voice').style.display = 'none';
    document.getElementById('mode-scan').style.display = 'block';
  }
}

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

function onScanSuccess(decodedText, decodedResult) {
  stopScanner();
  const scanData = { events: [{ item_name: "Scanned Item: " + decodedText.substring(0, 15), quantity: 100, unit: "units", event_type: "stock_received" }] };
  switchCaptureMode('voice');
  document.getElementById('mic-status').textContent = 'Barcode Scanned Successfully!';
  showCaptureResult(scanData);
  setTimeout(() => { document.getElementById('mic-status').textContent = 'Press and hold to record'; }, 4000);
}

function onScanFailure(error) { /* Silently ignore scan misses */ }
