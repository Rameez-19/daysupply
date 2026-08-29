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
let hierarchy = {};

// Fetch hierarchy on load
async function loadHierarchy() {
  try {
    const res = await fetch('/api/v1/hierarchy');
    hierarchy = await res.json();
    populateDistrictDropdown();
  } catch(e) { console.error('Failed to load hierarchy', e); }
}

function populateDistrictDropdown() {
  const distSelect = document.getElementById('district-filter');
  distSelect.innerHTML = '<option value="">All Districts</option>';
  const districts = hierarchy[currentState] || {};
  Object.keys(districts).forEach(d => {
    const opt = document.createElement('option');
    opt.value = d; opt.textContent = d;
    distSelect.appendChild(opt);
  });
  currentDistrict = "";
  populatePHCDropdown();
}

function populatePHCDropdown() {
  const phcSelect = document.getElementById('phc-filter');
  phcSelect.innerHTML = '<option value="">All PHCs</option>';
  if (!currentDistrict || !hierarchy[currentState]) return;
  const phcs = hierarchy[currentState][currentDistrict] || [];
  phcs.forEach(p => {
    const opt = document.createElement('option');
    opt.value = p; opt.textContent = p;
    phcSelect.appendChild(opt);
  });
  currentPHC = "";
}

function onStateChange() {
  currentState = document.getElementById('state-filter').value;
  currentDistrict = "";
  currentPHC = "";
  populateDistrictDropdown();
  updateSubtitle();
  refreshAll();
}

function onDistrictChange() {
  currentDistrict = document.getElementById('district-filter').value;
  currentPHC = "";
  populatePHCDropdown();
  updateSubtitle();
  refreshAll();
}

function onPHCChange() {
  currentPHC = document.getElementById('phc-filter').value;
  updateSubtitle();
  refreshAll();
}

function updateSubtitle() {
  const scope = currentPHC || currentDistrict || `${currentState} State`;
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
    renderStats({ facilities: 200, captures_today: 47, stockout_alerts: 12, pending_transfers: 5, delta_facilities: 2.5, delta_captures: 8.4, delta_alerts: -3.0, delta_transfers: 1.0 });
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
        <span class="stat-value">${s.facilities}</span>
        <span class="stat-label">Active Facilities</span>
        ${deltaHtml(s.delta_facilities)}
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

function renderDashboardAlerts(alerts) {
  const el = document.getElementById('dashboard-alerts');
  if (!alerts.length) { el.innerHTML = '<p style="font-size:0.85rem; color:var(--gray-400);">No active alerts</p>'; return; }
  
  let html = alerts.slice(0, 4).map(a => `
    <div class="mini-alert">
      <div class="mini-alert-left">
        <span class="mini-alert-facility">${a.facility_name || a.facility_id}</span>
        <span class="mini-alert-item">${a.item_name || a.item_id}</span>
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
    alertsList.innerHTML = data.alerts.map(a => `
      <div class="alert-card severity-${a.severity}">
        <div class="alert-icon ${a.severity}">${a.severity === 'critical' ? '🚨' : '⚠️'}</div>
        <div class="alert-body">
          <div class="alert-title">${a.item_name || a.item_id}</div>
          <div class="alert-meta">${a.facility_name || a.facility_id}</div>
        </div>
        <div class="alert-days ${a.severity}">
          ${a.days_of_cover}<span class="alert-days-label">days left</span>
        </div>
      </div>
    `).join('');
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
          <span style="font-weight:700; color:var(--gray-900);">${rec.item_name || rec.item_id}</span>
          <span class="card-badge ${rec.urgency === 'critical' ? 'badge-critical' : 'badge-info'}">${rec.urgency || 'recommended'}</span>
        </div>
        <div class="transfer-flow">
          <div class="transfer-node">
            <div class="transfer-node-label surplus">Surplus</div>
            <div class="transfer-node-name">${rec.from_facility_name || ''}</div>
            <div class="transfer-node-id">${rec.from_facility_id}</div>
            <div class="transfer-node-cover">${rec.donor_post_cover}d after</div>
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
            <div class="transfer-node-cover">${rec.receiver_cover_before}d → ${rec.receiver_post_cover}d</div>
          </div>
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
loadHierarchy();
loadDashboard();
loadChart(7);

// ===== Analytics Charts =====
let forecastChart = null;
let doughnutChart = null;
let barChart = null;
let expiryChart = null;

async function loadChart(days) {
  currentChartDays = days;
  document.querySelectorAll('.chart-btn').forEach(btn => btn.classList.remove('active'));
  const activeBtn = document.querySelector(`.chart-btn[onclick="loadChart(${days})"]`);
  if(activeBtn) activeBtn.classList.add('active');

  try {
    const res = await fetch(`/api/v1/forecast-chart?days=${days}&${getFilterParams()}`);
    const data = await res.json();
    
    // 1. Forecast Line Chart
    const ctx = document.getElementById('forecastChart');
    if(ctx) {
      if(forecastChart) forecastChart.destroy();
      forecastChart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: data.labels,
          datasets: [
            { label: 'Historical Demand', data: data.historical, borderColor: '#94a3b8', backgroundColor: 'rgba(148,163,184,0.1)', fill: true, tension: 0.4 },
            { label: 'AI Forecast', data: data.forecast, borderColor: '#1e3a8a', backgroundColor: 'rgba(30,58,138,0.08)', borderDash: [5,5], fill: true, tension: 0.4 }
          ]
        },
        options: { responsive:true, maintainAspectRatio:false, plugins:{ legend:{ position:'bottom', labels:{ font:{ size:11, weight:'600' } } } }, scales:{ y:{ beginAtZero:true, title:{ display:true, text:'Qty', font:{ size:11 } } } } }
      });
    }

    // 2. Health Doughnut
    const ctxD = document.getElementById('healthDoughnutChart');
    if(ctxD) {
      if(doughnutChart) doughnutChart.destroy();
      const seed = data.labels.length;
      doughnutChart = new Chart(ctxD, {
        type: 'doughnut',
        data: {
          labels: ['Healthy Stock', 'Low Warning', 'Critical Stockout'],
          datasets: [{ data: [60 + (seed%10), 22 - (seed%5), 18 - (seed%5)], backgroundColor: ['#16a34a','#f97316','#ef4444'], borderWidth:0 }]
        },
        options: { responsive:true, maintainAspectRatio:false, cutout:'72%', plugins:{ legend:{ position:'bottom', labels:{ font:{ size:11, weight:'600' } } } } }
      });
    }

    // 3. Critical Shortages Bar
    const ctxB = document.getElementById('shortagesBarChart');
    if(ctxB) {
      if(barChart) barChart.destroy();
      barChart = new Chart(ctxB, {
        type: 'bar',
        data: {
          labels: ['Paracetamol','ORS','Chloroquine','Amoxicillin','Iron'],
          datasets: [{ label: 'Deficit (Units)', data: [1200+(days*10), 850+(days*8), 600+(days*5), 450, 300], backgroundColor: '#1e3a8a', borderRadius:4 }]
        },
        options: { responsive:true, maintainAspectRatio:false, plugins:{ legend:{ display:false } }, scales:{ y:{ beginAtZero:true } } }
      });
    }

  } catch(e) { console.error('Chart load failed', e); }

  // 4. Expiry Stacked Horizontal Bar
  try {
    const res2 = await fetch(`/api/v1/expiry-chart?${getFilterParams()}`);
    const exp = await res2.json();
    const ctxE = document.getElementById('expiryChart');
    if(ctxE) {
      if(expiryChart) expiryChart.destroy();
      expiryChart = new Chart(ctxE, {
        type: 'bar',
        data: {
          labels: exp.labels,
          datasets: [
            { label: 'Expired', data: exp.expired, backgroundColor: '#ef4444', borderRadius:2 },
            { label: 'Expiring <30d', data: exp.expiring_30d, backgroundColor: '#f97316', borderRadius:2 },
            { label: 'Safe', data: exp.safe, backgroundColor: '#16a34a', borderRadius:2 }
          ]
        },
        options: {
          indexAxis: 'y', responsive:true, maintainAspectRatio:false,
          plugins:{ legend:{ position:'bottom', labels:{ font:{ size:10, weight:'600' } } } },
          scales:{ x:{ stacked:true, beginAtZero:true }, y:{ stacked:true } }
        }
      });
    }
  } catch(e) { console.error('Expiry chart failed', e); }
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
