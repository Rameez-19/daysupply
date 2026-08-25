// IndexedDB setup for offline queue
let db;
const request = indexedDB.open("DaySupplyDB", 1);
request.onupgradeneeded = event => {
  db = event.target.result;
  db.createObjectStore("offline-queue", { keyPath: "id" });
};
request.onsuccess = event => {
  db = event.target.result;
  checkOnlineStatus();
};

// UI Elements
const tabs = document.querySelectorAll('.tab-btn');
const views = document.querySelectorAll('.view');
const micBtn = document.getElementById('mic-btn');
const micStatus = document.getElementById('mic-status');
const syncStatus = document.getElementById('sync-status');
const reviewList = document.getElementById('review-list');
const transferList = document.getElementById('transfer-list');

// Navigation
tabs.forEach(tab => {
  tab.addEventListener('click', () => {
    tabs.forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    
    views.forEach(v => {
      v.classList.remove('active-view');
      v.classList.add('hidden-view');
    });
    
    const target = document.getElementById(tab.dataset.tab);
    target.classList.remove('hidden-view');
    target.classList.add('active-view');
    
    if (tab.dataset.tab === 'review-view') loadReviewQueue();
    if (tab.dataset.tab === 'transfer-view') loadTransfers();
  });
});

// Network Status & Sync
window.addEventListener('online', () => {
  syncStatus.textContent = 'Online';
  syncStatus.className = 'status-online';
  syncQueue();
});
window.addEventListener('offline', () => {
  syncStatus.textContent = 'Offline (Queueing)';
  syncStatus.className = 'status-offline';
});

function checkOnlineStatus() {
  if (navigator.onLine) {
    syncStatus.textContent = 'Online';
    syncStatus.className = 'status-online';
    syncQueue();
  } else {
    syncStatus.textContent = 'Offline (Queueing)';
    syncStatus.className = 'status-offline';
  }
}

async function syncQueue() {
  if (!db) return;
  const transaction = db.transaction(["offline-queue"], "readwrite");
  const store = transaction.objectStore("offline-queue");
  const getReq = store.getAll();
  
  getReq.onsuccess = async () => {
    const items = getReq.result;
    if (items.length === 0) return;
    
    syncStatus.textContent = `Syncing ${items.length} items...`;
    
    for (const item of items) {
      try {
        const formData = new FormData();
        formData.append("facility_id", item.facility_id);
        formData.append("file", item.audioBlob, "recording.webm");
        
        const res = await fetch("/api/v1/voice-note", {
          method: "POST",
          body: formData
        });
        
        if (res.ok) {
          db.transaction(["offline-queue"], "readwrite").objectStore("offline-queue").delete(item.id);
        }
      } catch (err) {
        console.error("Sync failed for item", item.id, err);
      }
    }
    syncStatus.textContent = 'Online';
  };
}

// MediaRecorder setup
let mediaRecorder;
let audioChunks = [];

micBtn.addEventListener('mousedown', startRecording);
micBtn.addEventListener('mouseup', stopRecording);
micBtn.addEventListener('touchstart', startRecording);
micBtn.addEventListener('touchend', stopRecording);

async function startRecording(e) {
  e.preventDefault(); // prevent double firing on touch
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];
    
    mediaRecorder.ondataavailable = e => {
      if (e.data.size > 0) audioChunks.push(e.data);
    };
    
    mediaRecorder.onstop = () => {
      const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
      processAudio(audioBlob);
    };
    
    mediaRecorder.start();
    micBtn.classList.add('recording');
    micStatus.textContent = 'Listening... (Release to submit)';
  } catch (err) {
    console.error(err);
    alert('Microphone access required.');
  }
}

function stopRecording(e) {
  e.preventDefault();
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.stop();
    mediaRecorder.stream.getTracks().forEach(t => t.stop());
    micBtn.classList.remove('recording');
    micStatus.textContent = 'Processing...';
  }
}

async function processAudio(blob) {
  if (!navigator.onLine) {
    // Save to IndexedDB
    const tx = db.transaction(["offline-queue"], "readwrite");
    const store = tx.objectStore("offline-queue");
    store.add({
      id: Date.now().toString(),
      facility_id: "IN-DEMO-001",
      audioBlob: blob,
      timestamp: Date.now()
    });
    micStatus.textContent = 'Saved offline. Ready.';
    return;
  }
  
  try {
    const formData = new FormData();
    formData.append("facility_id", "IN-DEMO-001");
    formData.append("file", blob, "recording.webm");
    
    const res = await fetch("/api/v1/voice-note", {
      method: "POST",
      body: formData
    });
    
    if (res.ok) {
      micStatus.textContent = 'Success! Ready.';
    } else {
      micStatus.textContent = 'Error processing note.';
    }
  } catch (err) {
    micStatus.textContent = 'Network error. Saved offline.';
    const tx = db.transaction(["offline-queue"], "readwrite");
    const store = tx.objectStore("offline-queue");
    store.add({
      id: Date.now().toString(),
      facility_id: "IN-DEMO-001",
      audioBlob: blob,
      timestamp: Date.now()
    });
  }
  
  setTimeout(() => {
    if (micStatus.textContent.includes('Success') || micStatus.textContent.includes('offline')) {
      micStatus.textContent = 'Ready';
    }
  }, 3000);
}

// API Fetching
async function loadReviewQueue() {
  reviewList.innerHTML = 'Loading...';
  try {
    const res = await fetch("/api/v1/review-queue");
    if (!res.ok) throw new Error("Failed");
    const data = await res.json();
    
    if (!data.items || data.items.length === 0) {
      reviewList.innerHTML = '<p>No items pending review.</p>';
      return;
    }
    
    reviewList.innerHTML = data.items.map(item => `
      <div class="card" id="review-${item.event_id}">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <span style="font-size:12px; background:#fef3c7; color:#92400e; padding:2px 6px; border-radius:4px;">
            Confidence: ${Math.round(item.confidence * 100)}%
          </span>
          <span style="font-size:12px; color:var(--text-muted);">${item.facility_id}</span>
        </div>
        <p style="margin-top:8px; font-style:italic; font-weight:500; color:#1e293b;">"${item.raw_transcript}"</p>
        <div style="font-size:13px; margin-bottom:12px;">
          <strong>Item:</strong> ${item.item_id || 'Unknown'} <br/>
          <strong>Qty:</strong> ${item.quantity !== null ? item.quantity : 'Unknown'}
        </div>
        <div style="display:flex; gap:8px;">
          <button class="action-btn" style="background:var(--success);" onclick="resolveEvent('${item.event_id}')">Approve</button>
          <button class="action-btn" style="background:var(--danger);" onclick="discardEvent('${item.event_id}')">Discard</button>
        </div>
      </div>
    `).join('');
  } catch (err) {
    reviewList.innerHTML = '<p>Error loading queue.</p>';
  }
}

async function loadTransfers() {
  transferList.innerHTML = 'Loading...';
  try {
    const res = await fetch("/api/v1/recommendations");
    if (!res.ok) throw new Error("Failed");
    const data = await res.json();
    
    if (!data.recommendations || data.recommendations.length === 0) {
      transferList.innerHTML = '<p>No transfers recommended. Network is optimal.</p>';
      document.getElementById('transfer-arrows').innerHTML = '';
      return;
    }
    
    transferList.innerHTML = data.recommendations.map(rec => `
      <div class="card" id="rec-${rec.recommendation_id}">
        <h3>${rec.item_id}</h3>
        <div style="display:flex; justify-content:space-between; text-align:center; margin:16px 0;">
          <div>
            <div style="font-size:12px; color:var(--text-muted); font-weight:bold;">FROM SURPLUS</div>
            <div>${rec.from_facility_id}</div>
            <div style="color:var(--success); font-size:12px;">Post: ${rec.donor_post_cover} days</div>
          </div>
          <div style="display:flex; flex-direction:column; justify-content:center; align-items:center;">
            <div style="background:#dbeafe; color:#1e40af; font-size:12px; font-weight:bold; padding:2px 8px; border-radius:12px; margin-bottom:4px;">
              ${rec.quantity} units
            </div>
            <div style="color:var(--text-muted);">➡️</div>
            <div style="font-size:10px; color:var(--text-muted); margin-top:2px;">${Math.round(rec.distance_km)} km</div>
          </div>
          <div>
            <div style="font-size:12px; color:var(--text-muted); font-weight:bold;">TO DEFICIT</div>
            <div>${rec.to_facility_id}</div>
            <div style="color:#d97706; font-size:12px;">Post: ${rec.receiver_post_cover} days</div>
          </div>
        </div>
        <button class="action-btn" style="width:100%;" onclick="approveTransfer('${rec.recommendation_id}')">Approve Transfer</button>
      </div>
    `).join('');
    
    // Map Visualization
    document.getElementById('transfer-arrows').innerHTML = data.recommendations.map(rec => 
      `<div>${rec.from_facility_id} ➝ ${rec.to_facility_id} (${rec.item_id})</div>`
    ).join('');
    
  } catch (err) {
    transferList.innerHTML = '<p>Error loading transfers.</p>';
  }
}

window.resolveEvent = async (id) => {
  document.getElementById(`review-${id}`).remove();
  alert('Event approved.');
};
window.discardEvent = async (id) => {
  document.getElementById(`review-${id}`).remove();
};
window.approveTransfer = async (id) => {
  try {
    await fetch(`/api/v1/recommendations/${id}/approve`, { method: "POST" });
    document.getElementById(`rec-${id}`).remove();
    alert('Transfer approved and dispatched.');
  } catch (err) {
    alert('Failed to approve transfer.');
  }
};
