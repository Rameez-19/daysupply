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

// ===== Dashboard — load on start =====
async function loadDashboard() {
  try {
    const res = await fetch("/api/v1/stats");
    const stats = await res.json();
    renderStats(stats);
  } catch (e) {
    renderStats({ facilities: 200, captures_today: 47, stockout_alerts: 12, pending_transfers: 5 });
  }

  try {
    const res = await fetch("/api/v1/alerts");
    const data = await res.json();
    renderDashboardAlerts(data.alerts || []);
    const badge = document.getElementById('alert-badge');
    if (badge && data.alerts) badge.textContent = data.alerts.length;
  } catch (e) {}

  try {
    const res = await fetch("/api/v1/review-queue");
    const data = await res.json();
    const badge = document.getElementById('review-badge');
    if (badge && data.items) badge.textContent = data.items.length;
  } catch (e) {}
}

function renderStats(s) {
  const grid = document.getElementById('stats-grid');
  grid.innerHTML = `
    <div class="stat-card clickable" onclick="switchTab('capture-view')">
      <div class="stat-icon" style="background:linear-gradient(135deg,#0d9488,#10b981);">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
      </div>
      <div class="stat-info">
        <span class="stat-value">${s.facilities}</span>
        <span class="stat-label">Active Facilities</span>
      </div>
    </div>
    <div class="stat-card clickable" onclick="switchTab('capture-view')">
      <div class="stat-icon" style="background:linear-gradient(135deg,#6366f1,#8b5cf6);">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
      </div>
      <div class="stat-info">
        <span class="stat-value">${s.captures_today}</span>
        <span class="stat-label">Voice Captures Today</span>
      </div>
    </div>
    <div class="stat-card clickable" onclick="switchTab('alerts-view')">
      <div class="stat-icon" style="background:linear-gradient(135deg,#f59e0b,#f97316);">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
      </div>
      <div class="stat-info">
        <span class="stat-value">${s.stockout_alerts}</span>
        <span class="stat-label">Stockout Alerts</span>
      </div>
    </div>
    <div class="stat-card clickable" onclick="switchTab('transfer-view')">
      <div class="stat-icon" style="background:linear-gradient(135deg,#ec4899,#f43f5e);">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>
      </div>
      <div class="stat-info">
        <span class="stat-value">${s.pending_transfers}</span>
        <span class="stat-label">Pending Transfers</span>
      </div>
    </div>
  `;
}

function renderDashboardAlerts(alerts) {
  const el = document.getElementById('dashboard-alerts');
  if (!alerts.length) { el.innerHTML = '<p style="font-size:0.85rem; color:var(--gray-400);">No active alerts</p>'; return; }
  el.innerHTML = alerts.slice(0, 4).map(a => `
    <div class="mini-alert">
      <div class="mini-alert-left">
        <span class="mini-alert-facility">${a.facility_name || a.facility_id}</span>
        <span class="mini-alert-item">${a.item_name || a.item_id}</span>
      </div>
      <span class="mini-alert-days">${a.days_of_cover}d left</span>
    </div>
  `).join('');
}

// ===== Review Queue =====
async function loadReviewQueue() {
  reviewList.innerHTML = '<div class="empty-state"><p>Loading…</p></div>';
  try {
    const res = await fetch("/api/v1/review-queue");
    const data = await res.json();
    if (!data.items || !data.items.length) {
      reviewList.innerHTML = '<div class="empty-state"><p>All clear! No items need review.</p></div>';
      return;
    }
    reviewList.innerHTML = data.items.map(item => `
      <div class="item-card" id="review-${item.event_id}">
        <div class="card-header">
          <span class="card-badge badge-warning">Confidence: ${Math.round(item.confidence * 100)}%</span>
          <span class="card-facility">${item.facility_name || item.facility_id} · ${timeAgo(item.created_at)}</span>
        </div>
        <div class="card-transcript">"${item.raw_transcript}"</div>
        <div class="card-details">
          <div><span class="card-detail-label">Item</span><br><span class="card-detail-value">${item.item_name || item.item_id || 'Unknown'}</span></div>
          <div><span class="card-detail-label">Quantity</span><br><span class="card-detail-value">${item.quantity !== null ? item.quantity + ' ' + (item.unit || '') : 'Unknown'}</span></div>
          <div><span class="card-detail-label">Event Type</span><br><span class="card-detail-value" style="text-transform:capitalize;">${(item.event_type || 'unknown').replace('_', ' ')}</span></div>
          <div><span class="card-detail-label">Facility</span><br><span class="card-detail-value">${item.facility_name || item.facility_id}</span></div>
        </div>
        <div class="card-actions">
          <button class="btn btn-primary" onclick="resolveEvent('${item.event_id}')">✓ Approve</button>
          <button class="btn btn-danger" onclick="discardEvent('${item.event_id}')">✕ Discard</button>
        </div>
      </div>
    `).join('');
  } catch (e) {
    reviewList.innerHTML = '<div class="empty-state"><p>Could not load review queue.</p></div>';
  }
}

// ===== Alerts =====
async function loadAlerts() {
  alertsList.innerHTML = '<div class="empty-state"><p>Loading…</p></div>';
  try {
    const res = await fetch("/api/v1/alerts");
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
    const res = await fetch("/api/v1/recommendations");
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
    db.transaction(["offline-queue"], "readwrite").objectStore("offline-queue").add({ id: Date.now().toString(), facility_id: "IN-DEMO-001", audioBlob: blob, timestamp: Date.now() });
    micStatus.textContent = 'Saved offline — will sync when connected';
    return;
  }
  try {
    const fd = new FormData(); fd.append("facility_id", "IN-DEMO-001"); fd.append("file", blob, "recording.webm");
    const res = await fetch("/api/v1/voice-note", { method: "POST", body: fd });
    if (res.ok) { const data = await res.json(); micStatus.textContent = 'Captured successfully!'; showCaptureResult(data); }
    else micStatus.textContent = 'Error processing — try again';
  } catch (err) {
    micStatus.textContent = 'Network error — saved offline';
    db.transaction(["offline-queue"], "readwrite").objectStore("offline-queue").add({ id: Date.now().toString(), facility_id: "IN-DEMO-001", audioBlob: blob, timestamp: Date.now() });
  }
  setTimeout(() => { micStatus.textContent = 'Press and hold to record'; }, 4000);
}

function showCaptureResult(data) {
  captureResult.classList.remove('hidden');
  const events = data.events || data.results || [];
  if (!events.length) { captureContent.innerHTML = '<p style="color:var(--gray-500);">No items detected.</p>'; return; }
  captureContent.innerHTML = events.map(ev => `
    <div style="display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid var(--gray-200);">
      <span style="font-weight:600;">${ev.item_name || ev.item_id || 'Unknown'}</span>
      <span style="color:var(--gray-500);">${ev.quantity || '?'} ${ev.unit || 'units'}</span>
    </div>
  `).join('');
}

// ===== Actions =====
window.resolveEvent = id => { const el = document.getElementById(`review-${id}`); if (el) { el.style.opacity='0'; setTimeout(()=>el.remove(),300); } };
window.discardEvent = id => { const el = document.getElementById(`review-${id}`); if (el) { el.style.opacity='0'; setTimeout(()=>el.remove(),300); } };
window.approveTransfer = async id => {
  try { await fetch(`/api/v1/recommendations/${id}/approve`, { method:"POST" }); const el = document.getElementById(`rec-${id}`); if (el) { el.style.opacity='0'; setTimeout(()=>el.remove(),300); } }
  catch(e) { alert('Failed to approve.'); }
};

// ===== Helpers =====
function timeAgo(iso) {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return mins + 'm ago';
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return hrs + 'h ago';
  return Math.floor(hrs / 24) + 'd ago';
}

// ===== Init =====
loadDashboard();
loadChart(7);

// ===== Analytics Chart =====
let forecastChart = null;
async function loadChart(days) {
  // Update buttons
  document.querySelectorAll('.chart-btn').forEach(btn => btn.classList.remove('active'));
  const activeBtn = document.querySelector(`.chart-btn[onclick="loadChart(${days})"]`);
  if(activeBtn) activeBtn.classList.add('active');

  try {
    const res = await fetch(`/api/v1/forecast-chart?days=${days}`);
    const data = await res.json();
    
    const ctx = document.getElementById('forecastChart');
    if(!ctx) return;

    if(forecastChart) forecastChart.destroy();
    
    forecastChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: data.labels,
        datasets: [
          {
            label: 'Historical Demand',
            data: data.historical,
            borderColor: '#94a3b8',
            backgroundColor: 'rgba(148, 163, 184, 0.1)',
            fill: true,
            tension: 0.4
          },
          {
            label: 'AI Forecast',
            data: data.forecast,
            borderColor: '#0d9488',
            backgroundColor: 'rgba(13, 148, 136, 0.1)',
            borderDash: [5, 5],
            fill: true,
            tension: 0.4
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom' }
        },
        scales: {
          y: { beginAtZero: true, title: { display: true, text: 'Quantity' } }
        }
      }
    });
  } catch(e) { console.error('Chart load failed', e); }
}

// ===== Barcode Scanner =====
let html5QrcodeScanner = null;

function switchCaptureMode(mode) {
  document.getElementById('tab-voice').classList.remove('active');
  document.getElementById('tab-scan').classList.remove('active');
  document.getElementById(`tab-${mode}`).classList.add('active');
  
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
    .catch(err => {
      alert("Camera access denied or unavailable.");
    });
}

function stopScanner() {
  if (html5QrcodeScanner) {
    html5QrcodeScanner.stop().then(() => {
      html5QrcodeScanner.clear();
      html5QrcodeScanner = null;
    }).catch(err => console.error(err));
  }
}

function onScanSuccess(decodedText, decodedResult) {
  stopScanner();
  // Simulate successful parse from a barcode
  const scanData = {
    events: [
      {
        item_name: "Scanned Item: " + decodedText.substring(0, 15),
        quantity: 100,
        unit: "units",
        event_type: "stock_received"
      }
    ]
  };
  
  // Reuse the voice capture UI to show result
  switchCaptureMode('voice');
  document.getElementById('mic-status').textContent = 'Barcode Scanned Successfully!';
  showCaptureResult(scanData);
  setTimeout(() => { document.getElementById('mic-status').textContent = 'Press and hold to record'; }, 4000);
}

function onScanFailure(error) {
  // Ignore continuous scan failures
}

