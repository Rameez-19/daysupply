// ===== IndexedDB setup for offline queue =====
let db;
const dbReq = indexedDB.open("StockPulseDB", 1);
dbReq.onupgradeneeded = e => {
  db = e.target.result;
  db.createObjectStore("offline-queue", { keyPath: "id" });
};
dbReq.onsuccess = e => {
  db = e.target.result;
  checkOnlineStatus();
};

// ===== DOM References =====
const sidebarItems = document.querySelectorAll('.nav-item');
const bottomItems  = document.querySelectorAll('.bottom-nav-item');
const allViews     = document.querySelectorAll('.view');
const micBtn       = document.getElementById('mic-btn');
const micRing      = document.getElementById('mic-ring');
const micStatus    = document.getElementById('mic-status');
const captureResult    = document.getElementById('capture-result');
const captureContent   = document.getElementById('capture-result-content');
const reviewList   = document.getElementById('review-list');
const transferList = document.getElementById('transfer-list');

// ===== Navigation =====
function switchTab(tabId) {
  // Update views
  allViews.forEach(v => { v.classList.remove('active-view'); v.classList.add('hidden-view'); });
  const target = document.getElementById(tabId);
  if (target) { target.classList.remove('hidden-view'); target.classList.add('active-view'); }

  // Update sidebar
  sidebarItems.forEach(b => b.classList.remove('active'));
  const sideBtn = document.querySelector(`.nav-item[data-tab="${tabId}"]`);
  if (sideBtn) sideBtn.classList.add('active');

  // Update bottom nav
  bottomItems.forEach(b => b.classList.remove('active'));
  const botBtn = document.querySelector(`.bottom-nav-item[data-tab="${tabId}"]`);
  if (botBtn) botBtn.classList.add('active');

  // Load data for views
  if (tabId === 'review-view')   loadReviewQueue();
  if (tabId === 'transfer-view') loadTransfers();
}

sidebarItems.forEach(btn => btn.addEventListener('click', () => switchTab(btn.dataset.tab)));
bottomItems.forEach(btn  => btn.addEventListener('click', () => switchTab(btn.dataset.tab)));

// ===== Online / Offline =====
function updateSyncUI(online) {
  const dots   = document.querySelectorAll('.sync-dot');
  const labels = document.querySelectorAll('.sync-label');
  dots.forEach(d => { d.className = online ? 'sync-dot online' : 'sync-dot offline'; });
  labels.forEach(l => { l.textContent = online ? 'Online' : 'Offline'; });
}

window.addEventListener('online',  () => { updateSyncUI(true);  syncQueue(); });
window.addEventListener('offline', () => { updateSyncUI(false); });

function checkOnlineStatus() {
  updateSyncUI(navigator.onLine);
  if (navigator.onLine) syncQueue();
}

async function syncQueue() {
  if (!db) return;
  const tx = db.transaction(["offline-queue"], "readwrite");
  const store = tx.objectStore("offline-queue");
  const req = store.getAll();

  req.onsuccess = async () => {
    const items = req.result;
    if (!items.length) return;

    for (const item of items) {
      try {
        const fd = new FormData();
        fd.append("facility_id", item.facility_id);
        fd.append("file", item.audioBlob, "recording.webm");
        const res = await fetch("/api/v1/voice-note", { method: "POST", body: fd });
        if (res.ok) {
          db.transaction(["offline-queue"], "readwrite").objectStore("offline-queue").delete(item.id);
        }
      } catch (err) { console.error("Sync failed", item.id, err); }
    }
  };
}

// ===== MediaRecorder =====
let mediaRecorder;
let audioChunks = [];

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
    mediaRecorder.onstop = () => {
      const blob = new Blob(audioChunks, { type: 'audio/webm' });
      processAudio(blob);
    };

    mediaRecorder.start();
    micBtn.classList.add('recording');
    micRing.classList.add('recording');
    micStatus.textContent = 'Listening… Release to submit';
    captureResult.classList.add('hidden');
  } catch (err) {
    console.error(err);
    micStatus.textContent = 'Microphone access denied';
  }
}

function stopRecording(e) {
  e.preventDefault();
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.stop();
    mediaRecorder.stream.getTracks().forEach(t => t.stop());
    micBtn.classList.remove('recording');
    micRing.classList.remove('recording');
    micStatus.textContent = 'Processing…';
  }
}

async function processAudio(blob) {
  if (!navigator.onLine) {
    const tx = db.transaction(["offline-queue"], "readwrite");
    tx.objectStore("offline-queue").add({
      id: Date.now().toString(),
      facility_id: "IN-DEMO-001",
      audioBlob: blob,
      timestamp: Date.now()
    });
    micStatus.textContent = 'Saved offline — will sync when connected';
    return;
  }

  try {
    const fd = new FormData();
    fd.append("facility_id", "IN-DEMO-001");
    fd.append("file", blob, "recording.webm");

    const res = await fetch("/api/v1/voice-note", { method: "POST", body: fd });

    if (res.ok) {
      const data = await res.json();
      micStatus.textContent = 'Captured successfully!';
      showCaptureResult(data);
    } else {
      micStatus.textContent = 'Error processing — try again';
    }
  } catch (err) {
    micStatus.textContent = 'Network error — saved offline';
    const tx = db.transaction(["offline-queue"], "readwrite");
    tx.objectStore("offline-queue").add({
      id: Date.now().toString(),
      facility_id: "IN-DEMO-001",
      audioBlob: blob,
      timestamp: Date.now()
    });
  }

  setTimeout(() => {
    if (micStatus.textContent.includes('success') || micStatus.textContent.includes('offline')) {
      micStatus.textContent = 'Press and hold to record';
    }
  }, 4000);
}

function showCaptureResult(data) {
  captureResult.classList.remove('hidden');
  const events = data.events || data.results || [];
  if (events.length === 0) {
    captureContent.innerHTML = '<p style="color:var(--gray-500);">No items detected. Try speaking more clearly.</p>';
    return;
  }
  captureContent.innerHTML = events.map(ev => `
    <div style="display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid var(--gray-200);">
      <span style="font-weight:600;">${ev.item_name || ev.item_id || 'Unknown'}</span>
      <span style="color:var(--gray-500);">${ev.quantity || '?'} ${ev.unit || 'units'}</span>
    </div>
  `).join('');
}

// ===== Review Queue =====
async function loadReviewQueue() {
  reviewList.innerHTML = renderEmptyState('Loading review items…');
  try {
    const res = await fetch("/api/v1/review-queue");
    if (!res.ok) throw new Error("Failed");
    const data = await res.json();

    if (!data.items || data.items.length === 0) {
      reviewList.innerHTML = renderEmptyState('All clear! No items need review.');
      return;
    }

    reviewList.innerHTML = data.items.map(item => `
      <div class="item-card" id="review-${item.event_id}">
        <div class="card-header">
          <span class="card-badge badge-warning">Confidence: ${Math.round(item.confidence * 100)}%</span>
          <span class="card-facility">${item.facility_id}</span>
        </div>
        <div class="card-transcript">"${item.raw_transcript}"</div>
        <div class="card-details">
          <div>
            <span class="card-detail-label">Item</span><br>
            <span class="card-detail-value">${item.item_id || 'Unknown'}</span>
          </div>
          <div>
            <span class="card-detail-label">Quantity</span><br>
            <span class="card-detail-value">${item.quantity !== null ? item.quantity : 'Unknown'}</span>
          </div>
        </div>
        <div class="card-actions">
          <button class="btn btn-primary" onclick="resolveEvent('${item.event_id}')">Approve</button>
          <button class="btn btn-danger" onclick="discardEvent('${item.event_id}')">Discard</button>
        </div>
      </div>
    `).join('');
  } catch (err) {
    reviewList.innerHTML = renderEmptyState('Could not load review queue.');
  }
}

// ===== Transfers =====
async function loadTransfers() {
  transferList.innerHTML = renderEmptyState('Loading transfer recommendations…');
  try {
    const res = await fetch("/api/v1/recommendations");
    if (!res.ok) throw new Error("Failed");
    const data = await res.json();

    if (!data.recommendations || data.recommendations.length === 0) {
      transferList.innerHTML = renderEmptyState('Network is balanced — no transfers needed.');
      return;
    }

    transferList.innerHTML = data.recommendations.map(rec => `
      <div class="item-card" id="rec-${rec.recommendation_id}">
        <div class="card-header">
          <span style="font-weight:700; color:var(--gray-900);">${rec.item_id}</span>
          <span class="card-badge badge-info">${Math.round(rec.distance_km)} km</span>
        </div>
        <div class="transfer-flow">
          <div class="transfer-node">
            <div class="transfer-node-label surplus">Surplus</div>
            <div class="transfer-node-id">${rec.from_facility_id}</div>
            <div class="transfer-node-cover">Post: ${rec.donor_post_cover}d cover</div>
          </div>
          <div class="transfer-arrow">
            <span class="transfer-qty">${rec.quantity} units</span>
            <span class="transfer-arrow-icon">→</span>
            <span class="transfer-dist">${Math.round(rec.distance_km)} km</span>
          </div>
          <div class="transfer-node">
            <div class="transfer-node-label deficit">Deficit</div>
            <div class="transfer-node-id">${rec.to_facility_id}</div>
            <div class="transfer-node-cover">Post: ${rec.receiver_post_cover}d cover</div>
          </div>
        </div>
        <button class="btn btn-primary btn-full" onclick="approveTransfer('${rec.recommendation_id}')">Approve Transfer</button>
      </div>
    `).join('');
  } catch (err) {
    transferList.innerHTML = renderEmptyState('Could not load transfer recommendations.');
  }
}

// ===== Actions =====
window.resolveEvent = async (id) => {
  const el = document.getElementById(`review-${id}`);
  if (el) { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }
};

window.discardEvent = async (id) => {
  const el = document.getElementById(`review-${id}`);
  if (el) { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }
};

window.approveTransfer = async (id) => {
  try {
    await fetch(`/api/v1/recommendations/${id}/approve`, { method: "POST" });
    const el = document.getElementById(`rec-${id}`);
    if (el) { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }
  } catch (err) {
    alert('Failed to approve transfer.');
  }
};

// ===== Helpers =====
function renderEmptyState(msg) {
  return `<div class="empty-state">
    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>
    <p>${msg}</p>
  </div>`;
}

// Expose switchTab globally for quick-action buttons
window.switchTab = switchTab;
