// Report stock — the PHC worker's page, built for an ASHA or a pharmacist
// holding a phone at the end of a shift, not for an analyst.
//
// Design rules, each of which came out of the audit:
//   * Nothing is written until the worker has heard it read back and said
//     yes. Voice, photo and typed notes all preview first; the one exception
//     is the offline queue, which syncs hours later with nobody holding the
//     phone, so it goes straight through the confidence gate as before.
//   * The default mode needs no reading beyond a medicine name and no typing
//     beyond a number: tap what happened, tap the medicine, tap the count.
//   * The whole page reads in Hindi or English from one dictionary below,
//     and the read-back is spoken in the same language.
//   * The centre is chosen once and remembered on the phone. The old page
//     posted every voice note against a hardcoded facility id.
//   * Offline is a plain sentence and a count of what is waiting, not a
//     coloured dot.
//
// Loads after app.js and uses its globals: db, switchTab, refreshAll,
// showCaptureResult, loadReviewQueue, syncQueue.

const REPORT_LANG_KEY = 'stockpulse.lang';
const REPORT_FACILITY_KEY = 'stockpulse.facility';

const REPORT_STRINGS = {
  en: {
    'report.title': 'Report stock',
    'report.sub': 'Tap, speak, photograph or type. Every report is read back to you before it is saved.',
    'lang.other': 'हिंदी',
    'centre.which': 'Which centre are you reporting for?',
    'centre.state': 'State', 'centre.district': 'District', 'centre.phc': 'Centre',
    'centre.pick': 'Choose…', 'centre.change': 'Change',
    'centre.remembered': 'Remembered on this phone.',
    'centre.needed': 'Choose your centre first.',
    'mode.tap': 'Tap', 'mode.voice': 'Speak', 'mode.photo': 'Photo',
    'mode.scan': 'Scan', 'mode.chat': 'Type', 'mode.staff': 'Staff today',
    'step.what': 'What happened?',
    'ev.received': 'Stock came in', 'ev.dispensed': 'Given to patients',
    'ev.count': 'Counted the shelf', 'ev.lost': 'Broken, expired or missing',
    'step.which': 'Which medicine?',
    'tile.other': 'Another medicine', 'tile.other.sub': 'say or type its name',
    'step.howmany': 'How many?',
    'step.why': 'Why?',
    'loss.broken': 'Broken', 'loss.damaged': 'Damaged', 'loss.expired': 'Expired',
    'loss.spilled': 'Spilled', 'loss.stolen': 'Stolen', 'loss.unknown': "Don't know",
    'kp.clear': 'Clear', 'kp.back': 'Back', 'kp.next': 'Next',
    'rb.title': 'Is this right?',
    'rb.yes': 'Yes, save', 'rb.no': 'No, start again', 'rb.listen': 'Listen',
    'rb.nothing': 'Nothing was recognised as a stock update. Try again, or tap the medicine instead.',
    'rb.remove': 'Remove',
    'saving': 'Saving…',
    'saved': 'Saved', 'held': 'Held for the pharmacist to check',
    'saved.why': 'Now counted in the stock position.',
    'offline.saved': 'No network. Saved on this phone; it will be sent when the network returns.',
    'offline.now': 'No network right now.',
    'offline.unsent': 'reports waiting to send from this phone.',
    'online.unsent': 'reports still waiting to send.',
    'voice.hold': 'Press and hold to speak', 'voice.listening': 'Listening… release when done',
    'voice.working': 'Understanding…',
    'voice.hint': 'Hindi, English or both. Example: “Paracetamol ke 200 tablet aaye hain”',
    'voice.denied': 'Microphone access was refused',
    'photo.hint': 'Photograph the stock register page. Each row is shown for you to check; nothing is saved until you say yes.',
    'photo.take': 'Take photo', 'photo.reading': 'Reading the page…',
    'scan.hint': 'Point the camera at the barcode on the pack.',
    'scan.start': 'Start camera', 'scan.stop': 'Stop',
    'chat.hint': 'Type it the way you would say it.',
    'chat.send': 'Send',
    'staff.title': 'Who is on duty today?',
    'staff.sub': 'Enter the number present for each role. This is the only attendance figure the system holds: what centres report.',
    'staff.doctor': 'Doctor', 'staff.nurse': 'Nurse / ANM', 'staff.pharmacist': 'Pharmacist',
    'staff.hamale': 'Health assistant (male)', 'staff.hafemale': 'Health assistant (female)',
    'staff.save': 'Save attendance',
    'review.title': 'For the pharmacist: waiting for a check',
    'review.sub': 'What the model was not sure about. Nothing here is in the stock position yet.',
    'error': 'Could not reach the server. Nothing was saved.',
    'unit.tablet': 'tablets', 'unit.capsule': 'capsules', 'unit.vial': 'vials',
    'unit.bottle': 'bottles', 'unit.strip': 'strips', 'unit.unit': 'units', 'unit.unknown': '', 'unit.person': 'people',
    'evs.received': 'came in', 'evs.dispensed': 'given out', 'evs.count': 'on the shelf',
    'evs.lost': 'lost', 'evs.dispatched': 'sent out', 'evs.expired': 'expired',
    'staff.present': 'on duty',
    'mode.beds': 'Beds today',
    'beds.title': 'How many beds are in use right now?',
    'beds.sub': 'Count the beds with a patient in them. This is the only bed count the system holds that is not modelled.',
    'beds.inpatient': 'Inpatient beds in use', 'beds.daycare': 'Day-care beds in use',
    'beds.save': 'Save bed count', 'unit.bed': 'beds', 'beds.inuse': 'in use',
  },
  hi: {
    'report.title': 'स्टॉक बताएँ',
    'report.sub': 'दबाएँ, बोलें, फ़ोटो लें या लिखें। सेव करने से पहले हर रिपोर्ट आपको पढ़कर सुनाई जाएगी।',
    'lang.other': 'English',
    'centre.which': 'आप किस केंद्र के लिए रिपोर्ट कर रहे हैं?',
    'centre.state': 'राज्य', 'centre.district': 'ज़िला', 'centre.phc': 'केंद्र',
    'centre.pick': 'चुनें…', 'centre.change': 'बदलें',
    'centre.remembered': 'इस फ़ोन पर याद रखा गया।',
    'centre.needed': 'पहले अपना केंद्र चुनें।',
    'mode.tap': 'दबाएँ', 'mode.voice': 'बोलें', 'mode.photo': 'फ़ोटो',
    'mode.scan': 'स्कैन', 'mode.chat': 'लिखें', 'mode.staff': 'आज का स्टाफ़',
    'step.what': 'क्या हुआ?',
    'ev.received': 'दवा आई', 'ev.dispensed': 'मरीज़ों को दी',
    'ev.count': 'गिनती की', 'ev.lost': 'टूटी, एक्सपायर या गायब',
    'step.which': 'कौन सी दवा?',
    'tile.other': 'कोई और दवा', 'tile.other.sub': 'नाम बोलें या लिखें',
    'step.howmany': 'कितनी?',
    'step.why': 'क्यों?',
    'loss.broken': 'टूटी', 'loss.damaged': 'खराब', 'loss.expired': 'एक्सपायर',
    'loss.spilled': 'गिरी', 'loss.stolen': 'चोरी', 'loss.unknown': 'पता नहीं',
    'kp.clear': 'साफ़', 'kp.back': 'पीछे', 'kp.next': 'आगे',
    'rb.title': 'क्या यह सही है?',
    'rb.yes': 'हाँ, सेव करें', 'rb.no': 'नहीं, फिर से', 'rb.listen': 'सुनें',
    'rb.nothing': 'कोई स्टॉक जानकारी समझ नहीं आई। फिर से कोशिश करें, या दवा दबाकर चुनें।',
    'rb.remove': 'हटाएँ',
    'saving': 'सेव हो रहा है…',
    'saved': 'सेव हो गया', 'held': 'फार्मासिस्ट की जाँच के लिए रोका गया',
    'saved.why': 'अब स्टॉक की गिनती में शामिल है।',
    'offline.saved': 'नेटवर्क नहीं है। फ़ोन में सेव हो गया, नेटवर्क आने पर भेज दिया जाएगा।',
    'offline.now': 'अभी नेटवर्क नहीं है।',
    'offline.unsent': 'रिपोर्ट इस फ़ोन से भेजने को बाकी।',
    'online.unsent': 'रिपोर्ट अभी भी भेजने को बाकी।',
    'voice.hold': 'दबाकर रखें और बोलें', 'voice.listening': 'सुन रहे हैं… बोलकर छोड़ दें',
    'voice.working': 'समझ रहे हैं…',
    'voice.hint': 'हिंदी, अंग्रेज़ी या दोनों। जैसे: “Paracetamol ke 200 tablet aaye hain”',
    'voice.denied': 'माइक्रोफ़ोन की अनुमति नहीं मिली',
    'photo.hint': 'स्टॉक रजिस्टर का पन्ना फ़ोटो लें। हर पंक्ति आपको जाँचने के लिए दिखेगी; आपके हाँ कहने तक कुछ सेव नहीं होगा।',
    'photo.take': 'फ़ोटो लें', 'photo.reading': 'पन्ना पढ़ रहे हैं…',
    'scan.hint': 'पैकेट के बारकोड पर कैमरा रखें।',
    'scan.start': 'कैमरा चालू करें', 'scan.stop': 'बंद करें',
    'chat.hint': 'जैसे बोलते हैं वैसे ही लिखें।',
    'chat.send': 'भेजें',
    'staff.title': 'आज ड्यूटी पर कौन है?',
    'staff.sub': 'हर भूमिका के लिए मौजूद लोगों की संख्या लिखें। सिस्टम के पास हाज़िरी का यही एक आँकड़ा है: जो केंद्र बताते हैं।',
    'staff.doctor': 'डॉक्टर', 'staff.nurse': 'नर्स / ANM', 'staff.pharmacist': 'फार्मासिस्ट',
    'staff.hamale': 'स्वास्थ्य सहायक (पुरुष)', 'staff.hafemale': 'स्वास्थ्य सहायक (महिला)',
    'staff.save': 'हाज़िरी सेव करें',
    'review.title': 'फार्मासिस्ट के लिए: जाँच बाकी',
    'review.sub': 'जिस पर मॉडल को भरोसा नहीं था। यह अभी स्टॉक की गिनती में नहीं है।',
    'error': 'सर्वर से संपर्क नहीं हो सका। कुछ सेव नहीं हुआ।',
    'unit.tablet': 'गोली', 'unit.capsule': 'कैप्सूल', 'unit.vial': 'शीशी',
    'unit.bottle': 'बोतल', 'unit.strip': 'पत्ता', 'unit.unit': 'यूनिट', 'unit.unknown': '', 'unit.person': 'लोग',
    'evs.received': 'आई', 'evs.dispensed': 'दी गई', 'evs.count': 'स्टॉक में',
    'evs.lost': 'गायब या खराब', 'evs.dispatched': 'भेजी गई', 'evs.expired': 'एक्सपायर',
    'staff.present': 'ड्यूटी पर',
    'mode.beds': 'आज के बेड',
    'beds.title': 'अभी कितने बेड पर मरीज़ हैं?',
    'beds.sub': 'जिन बेड पर मरीज़ है उन्हें गिनें। सिस्टम के पास बेड का यही एक आँकड़ा है जो अनुमान नहीं है।',
    'beds.inpatient': 'भर्ती बेड जिन पर मरीज़ हैं', 'beds.daycare': 'डे-केयर बेड जिन पर मरीज़ हैं',
    'beds.save': 'बेड गिनती सेव करें', 'unit.bed': 'बेड', 'beds.inuse': 'पर मरीज़',
  },
};

let reportLang = 'en';
try { reportLang = localStorage.getItem(REPORT_LANG_KEY) === 'hi' ? 'hi' : 'en'; } catch (e) { /* private mode */ }

function t(key) {
  const table = REPORT_STRINGS[reportLang] || REPORT_STRINGS.en;
  return table[key] !== undefined ? table[key] : (REPORT_STRINGS.en[key] || key);
}

function rq(id) { return document.getElementById(id); }

function toggleLang() {
  reportLang = reportLang === 'hi' ? 'en' : 'hi';
  try { localStorage.setItem(REPORT_LANG_KEY, reportLang); } catch (e) { /* ignore */ }
  applyReportStrings();
  renderTapStep();
  renderStaffForm();
  renderBedsForm();
  renderCentre();
  updateOfflineLine();
  // A read-back on screen is re-spoken in the new language, so the worker
  // who switched because they did not follow it hears it again.
  const rb = rq('report-readback');
  if (rb && !rb.hidden && readbackRows.length) showReadback(readbackRows, readbackSource, readbackTranscript, readbackResourceType);
}
window.toggleLang = toggleLang;

function applyReportStrings() {
  document.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll('[data-i18n-ph]').forEach(el => { el.placeholder = t(el.dataset.i18nPh); });
  const html = document.documentElement;
  if (html) html.setAttribute('data-report-lang', reportLang);
}

// ===== The centre =====
// Stored as {id, name, state, district}. The Today filters' PHC is used when
// the phone has never chosen one, so an officer trying the page sees their
// own scope; a worker's stored choice wins after that.
let reportFacility = null;
try { reportFacility = JSON.parse(localStorage.getItem(REPORT_FACILITY_KEY) || 'null'); } catch (e) { reportFacility = null; }

function reportFacilityId() {
  if (reportFacility && reportFacility.id) return reportFacility.id;
  if (typeof currentPHC !== 'undefined' && currentPHC) return currentPHC;
  return '';
}

function renderCentre() {
  const host = rq('report-centre');
  if (!host) return;
  const id = reportFacilityId();
  if (id) {
    const name = (reportFacility && reportFacility.id === id && reportFacility.name)
      || (typeof currentPHCName !== 'undefined' && currentPHCName) || id;
    const where = reportFacility && reportFacility.id === id
      ? [reportFacility.district, reportFacility.state].filter(Boolean).join(', ') : '';
    host.innerHTML = `
      <div class="centre-chosen">
        <div>
          <div class="centre-name">${escapeHtml(name)}</div>
          <div class="centre-where">${escapeHtml(where)} <span class="centre-id">${escapeHtml(id)}</span></div>
        </div>
        <button class="btn btn-secondary" onclick="changeCentre()">${t('centre.change')}</button>
      </div>`;
    return;
  }
  host.innerHTML = `
    <div class="centre-pick">
      <div class="centre-question">${t('centre.which')}</div>
      <div class="centre-selects">
        <label><span>${t('centre.state')}</span><select id="rc-state" onchange="onCentreState()"><option value="">${t('centre.pick')}</option></select></label>
        <label><span>${t('centre.district')}</span><select id="rc-district" onchange="onCentreDistrict()" disabled><option value="">${t('centre.pick')}</option></select></label>
        <label><span>${t('centre.phc')}</span><select id="rc-phc" onchange="onCentrePhc()" disabled><option value="">${t('centre.pick')}</option></select></label>
      </div>
    </div>`;
  fillCentreStates();
}

async function fillCentreStates() {
  const sel = rq('rc-state');
  if (!sel) return;
  try {
    const res = await fetch('/api/v1/states');
    const data = await res.json();
    (data.states || []).forEach(s => {
      const o = document.createElement('option');
      o.value = s.state; o.textContent = s.state;
      sel.appendChild(o);
    });
  } catch (e) { /* offline: the chooser stays empty and the line below says why */ }
}

async function onCentreState() {
  const st = rq('rc-state').value;
  const dsel = rq('rc-district'); const psel = rq('rc-phc');
  dsel.innerHTML = `<option value="">${t('centre.pick')}</option>`; dsel.disabled = !st;
  psel.innerHTML = `<option value="">${t('centre.pick')}</option>`; psel.disabled = true;
  if (!st) return;
  const res = await fetch(`/api/v1/districts?state=${encodeURIComponent(st)}`);
  const data = await res.json();
  (data.districts || []).forEach(d => {
    const o = document.createElement('option');
    o.value = d.district; o.textContent = d.display_name || d.district;
    dsel.appendChild(o);
  });
}

async function onCentreDistrict() {
  const st = rq('rc-state').value; const di = rq('rc-district').value;
  const psel = rq('rc-phc');
  psel.innerHTML = `<option value="">${t('centre.pick')}</option>`; psel.disabled = !di;
  if (!di) return;
  const res = await fetch(`/api/v1/facilities?state=${encodeURIComponent(st)}&district=${encodeURIComponent(di)}`);
  const data = await res.json();
  (data.facilities || []).forEach(f => {
    const o = document.createElement('option');
    o.value = f.facility_id; o.textContent = f.name || f.facility_id;
    psel.appendChild(o);
  });
}

function onCentrePhc() {
  const psel = rq('rc-phc');
  const id = psel.value;
  if (!id) return;
  reportFacility = {
    id, name: psel.options[psel.selectedIndex].textContent,
    state: rq('rc-state').value, district: rq('rc-district').value,
  };
  try { localStorage.setItem(REPORT_FACILITY_KEY, JSON.stringify(reportFacility)); } catch (e) { /* ignore */ }
  renderCentre();
}

function changeCentre() {
  reportFacility = null;
  try { localStorage.removeItem(REPORT_FACILITY_KEY); } catch (e) { /* ignore */ }
  // The Today filter would immediately re-fill it; clear the chooser's view
  // of that too so the worker can pick afresh.
  if (typeof currentPHC !== 'undefined') { currentPHC = ''; }
  renderCentre();
}
window.onCentreState = onCentreState; window.onCentreDistrict = onCentreDistrict;
window.onCentrePhc = onCentrePhc; window.changeCentre = changeCentre;

function requireCentre() {
  if (reportFacilityId()) return true;
  const host = rq('report-centre');
  if (host) { host.classList.add('centre-missing'); host.scrollIntoView({ block: 'start' }); setTimeout(() => host.classList.remove('centre-missing'), 1600); }
  const note = rq('report-note');
  if (note) note.textContent = t('centre.needed');
  return false;
}

// ===== Modes =====
const REPORT_MODES = ['tap', 'voice', 'photo', 'scan', 'chat', 'staff', 'beds'];
let reportMode = 'tap';

function setReportMode(mode) {
  if (REPORT_MODES.indexOf(mode) < 0) mode = 'tap';
  reportMode = mode;
  REPORT_MODES.forEach(m => {
    const panel = rq(`mode-${m}`);
    if (panel) panel.hidden = (m !== mode);
    const btn = rq(`rm-${m}`);
    if (btn) btn.classList.toggle('active', m === mode);
  });
  hideReadback();
  const result = rq('capture-result');
  if (result) result.classList.add('hidden');
  if (mode !== 'scan' && typeof stopScanner === 'function') stopScanner();
  if (mode === 'tap') { tapState = { step: 'what', event_type: null, item: null, qty: '', loss_reason: null }; renderTapStep(); }
  if (mode === 'staff') renderStaffForm();
  if (mode === 'beds') renderBedsForm();
}
window.setReportMode = setReportMode;

// ===== Tap mode =====
let quickItems = [];
let tapState = { step: 'what', event_type: null, item: null, qty: '', loss_reason: null };

async function loadQuickItems() {
  if (quickItems.length) return quickItems;
  try {
    const res = await fetch('/api/v1/items/quick');
    const data = await res.json();
    quickItems = data.items || [];
    try { localStorage.setItem('stockpulse.quickItems', JSON.stringify(quickItems)); } catch (e) { /* ignore */ }
  } catch (e) {
    // Offline: the last list this phone saw is better than an empty grid.
    try { quickItems = JSON.parse(localStorage.getItem('stockpulse.quickItems') || '[]'); } catch (e2) { quickItems = []; }
  }
  return quickItems;
}

function unitWord(unit) { return t('unit.' + (unit || 'unknown')); }

function renderTapStep() {
  const host = rq('tap-flow');
  if (!host) return;
  const s = tapState;
  const crumbs = [];
  if (s.event_type) crumbs.push(t('ev.' + s.event_type));
  if (s.item) crumbs.push(tileName(s.item));
  const crumbHtml = crumbs.length ? `<div class="tap-crumbs">${crumbs.map(escapeHtml).join(' › ')}</div>` : '';

  if (s.step === 'what') {
    host.innerHTML = `
      <div class="tap-question">${t('step.what')}</div>
      <div class="tap-events">
        <button class="tap-event ev-received" onclick="tapEvent('received')"><span class="tap-ico">📦</span>${t('ev.received')}</button>
        <button class="tap-event ev-dispensed" onclick="tapEvent('dispensed')"><span class="tap-ico">💊</span>${t('ev.dispensed')}</button>
        <button class="tap-event ev-count" onclick="tapEvent('count')"><span class="tap-ico">🔢</span>${t('ev.count')}</button>
        <button class="tap-event ev-lost" onclick="tapEvent('lost')"><span class="tap-ico">⚠️</span>${t('ev.lost')}</button>
      </div>`;
    return;
  }
  if (s.step === 'which') {
    host.innerHTML = `${crumbHtml}<div class="tap-question">${t('step.which')}</div><div class="tile-grid" id="tile-grid"><div class="empty-state"><p>…</p></div></div>
      <button class="btn btn-secondary tap-back" onclick="tapBack()">${t('kp.back')}</button>`;
    loadQuickItems().then(items => {
      const grid = rq('tile-grid');
      if (!grid) return;
      grid.innerHTML = items.map((it, i) => `
        <button class="tile ven-${(it.ven_class || '').toLowerCase()}" onclick="tapItem(${i})">
          <span class="tile-name">${escapeHtml(reportLang === 'hi' && it.hindi_name ? it.hindi_name : it.display_name)}</span>
          <span class="tile-sub">${escapeHtml(reportLang === 'hi' && it.hindi_name ? it.display_name : (it.spoken || ''))}</span>
          <span class="tile-unit">${escapeHtml(unitWord(it.unit))}</span>
        </button>`).join('') + `
        <button class="tile tile-other" onclick="setReportMode('voice')">
          <span class="tile-name">${t('tile.other')}</span><span class="tile-sub">${t('tile.other.sub')}</span></button>`;
    });
    return;
  }
  if (s.step === 'why') {
    host.innerHTML = `${crumbHtml}<div class="tap-question">${t('step.why')}</div>
      <div class="tap-events">${['broken', 'damaged', 'expired', 'spilled', 'stolen', 'unknown'].map(r =>
        `<button class="tap-event" onclick="tapWhy('${r}')">${t('loss.' + r)}</button>`).join('')}</div>
      <button class="btn btn-secondary tap-back" onclick="tapBack()">${t('kp.back')}</button>`;
    return;
  }
  if (s.step === 'howmany') {
    host.innerHTML = `${crumbHtml}<div class="tap-question">${t('step.howmany')}</div>
      <div class="keypad-display"><span id="kp-value">${escapeHtml(s.qty || '0')}</span> <span class="kp-unit">${escapeHtml(unitWord(s.item.unit))}</span></div>
      <div class="keypad">
        ${[1,2,3,4,5,6,7,8,9].map(n => `<button class="kp" onclick="kpPress('${n}')">${n}</button>`).join('')}
        <button class="kp kp-clear" onclick="kpPress('C')">${t('kp.clear')}</button>
        <button class="kp" onclick="kpPress('0')">0</button>
        <button class="kp kp-next" onclick="tapReadback()">${t('kp.next')}</button>
      </div>
      <button class="btn btn-secondary tap-back" onclick="tapBack()">${t('kp.back')}</button>`;
  }
}

function tileName(it) { return reportLang === 'hi' && it.hindi_name ? it.hindi_name : it.display_name; }

function tapEvent(ev) { tapState.event_type = ev; tapState.step = 'which'; renderTapStep(); }
function tapItem(i) {
  tapState.item = quickItems[i];
  tapState.step = tapState.event_type === 'lost' ? 'why' : 'howmany';
  tapState.qty = '';
  renderTapStep();
}
function tapWhy(r) { tapState.loss_reason = r; tapState.step = 'howmany'; renderTapStep(); }
function tapBack() {
  const s = tapState;
  if (s.step === 'which') s.step = 'what';
  else if (s.step === 'why') s.step = 'which';
  else if (s.step === 'howmany') s.step = s.event_type === 'lost' ? 'why' : 'which';
  renderTapStep();
}
function kpPress(k) {
  if (k === 'C') tapState.qty = '';
  else if (tapState.qty.length < 6) tapState.qty = (tapState.qty === '0' ? '' : tapState.qty) + k;
  const v = rq('kp-value'); if (v) v.textContent = tapState.qty || '0';
}
window.tapEvent = tapEvent; window.tapItem = tapItem; window.tapWhy = tapWhy;
window.tapBack = tapBack; window.kpPress = kpPress;

function tapReadback() {
  if (!requireCentre()) return;
  const s = tapState;
  if (!s.item) return;
  const rows = [{
    item_id: s.item.item_id, local_name: s.item.display_name, item_name: s.item.display_name,
    event_type: s.event_type, quantity: s.qty === '' ? null : parseInt(s.qty, 10),
    unit: s.item.unit, loss_reason: s.loss_reason, hindi_name: s.item.hindi_name,
  }];
  showReadback(rows, 'tap', null);
}
window.tapReadback = tapReadback;

// ===== Read-back =====
// One panel for every mode. Rows are what the server would write; the worker
// hears them, removes any that are wrong, and says yes.
let readbackRows = [];
let readbackSource = 'tap';
let readbackTranscript = null;
let readbackResourceType = 'medicine';

function rowSentence(r) {
  const name = reportLang === 'hi' && r.hindi_name ? r.hindi_name : (r.item_name || r.local_name || '?');
  const qty = (r.quantity === null || r.quantity === undefined) ? '?' : r.quantity;
  if (readbackResourceType === 'personnel') return `${name}: ${qty} ${t('staff.present')}`;
  if (readbackResourceType === 'bed') return `${name}: ${qty} ${t('beds.inuse')}`;
  const unit = unitWord(r.unit);
  const ev = t('evs.' + r.event_type);
  const why = r.event_type === 'lost' && r.loss_reason ? ` (${t('loss.' + r.loss_reason)})` : '';
  return `${name}, ${qty} ${unit}, ${ev}${why}`;
}

function showReadback(rows, source, transcript, resourceType = 'medicine') {
  readbackRows = rows; readbackSource = source; readbackTranscript = transcript;
  readbackResourceType = resourceType;
  const host = rq('report-readback');
  if (!host) return;
  const result = rq('capture-result'); if (result) result.classList.add('hidden');
  if (!rows.length) {
    host.hidden = false;
    host.innerHTML = `<div class="rb-title">${t('rb.title')}</div><p class="rb-nothing">${t('rb.nothing')}</p>
      <div class="rb-actions"><button class="btn btn-secondary" onclick="hideReadback()">${t('rb.no')}</button></div>`;
    return;
  }
  host.hidden = false;
  host.innerHTML = `
    <div class="rb-title">${t('rb.title')}</div>
    ${transcript ? `<div class="rb-transcript">“${escapeHtml(transcript)}”</div>` : ''}
    <ul class="rb-rows">${rows.map((r, i) => `
      <li class="rb-row ${r.review_reason ? 'rb-held' : ''}">
        <span class="rb-text">${escapeHtml(rowSentence(r))}</span>
        ${r.review_reason ? `<span class="rb-reason">${escapeHtml(r.review_reason)}</span>` : ''}
        <button class="rb-remove" onclick="removeReadbackRow(${i})" aria-label="${t('rb.remove')}">✕</button>
      </li>`).join('')}</ul>
    <div class="rb-actions">
      <button class="btn btn-secondary" onclick="speakReadback()">🔊 ${t('rb.listen')}</button>
      <button class="btn btn-danger" onclick="hideReadback()">${t('rb.no')}</button>
      <button class="btn btn-primary rb-yes" onclick="confirmReadback()">${t('rb.yes')}</button>
    </div>`;
  host.scrollIntoView({ block: 'nearest' });
  speakReadback();
}

function removeReadbackRow(i) {
  readbackRows.splice(i, 1);
  showReadback(readbackRows, readbackSource, readbackTranscript, readbackResourceType);
}
function hideReadback() {
  const host = rq('report-readback');
  if (host) { host.hidden = true; host.innerHTML = ''; }
  if (window.speechSynthesis) window.speechSynthesis.cancel();
}
function speakReadback() {
  if (!window.speechSynthesis || !readbackRows.length) return;
  window.speechSynthesis.cancel();
  const text = t('rb.title') + ' ' + readbackRows.map(rowSentence).join('. ');
  const u = new SpeechSynthesisUtterance(text);
  u.lang = reportLang === 'hi' ? 'hi-IN' : 'en-IN';
  u.rate = 0.95;
  window.speechSynthesis.speak(u);
}
window.removeReadbackRow = removeReadbackRow; window.hideReadback = hideReadback;
window.speakReadback = speakReadback;

async function confirmReadback() {
  if (!requireCentre()) return;
  const rows = readbackRows.map(r => ({
    item_id: r.item_id, local_name: r.local_name || r.item_name, event_type: r.event_type,
    quantity: r.quantity, unit: r.unit, loss_reason: r.loss_reason || r.resource_subtype,
  }));
  const source = readbackSource;
  const transcript = readbackTranscript;
  const resourceType = readbackResourceType;
  hideReadback();
  const facility_id = reportFacilityId();
  if (!navigator.onLine) {
    queueOffline({ kind: 'rows', facility_id, source, rows, raw_transcript: transcript, resource_type: resourceType });
    setReportNote(t('offline.saved'));
    updateOfflineLine();
    return;
  }
  setReportNote(t('saving'));
  try {
    const fd = new FormData();
    fd.append('rows', JSON.stringify(rows));
    fd.append('facility_id', facility_id);
    fd.append('source', source);
    fd.append('resource_type', resourceType);
    if (transcript) fd.append('raw_transcript', transcript);
    const res = await fetch('/api/v1/confirm-note', { method: 'POST', body: fd });
    const data = await res.json();
    if (!res.ok) { setReportNote((data.detail && (data.detail.reason || data.detail)) || t('error')); return; }
    setReportNote('');
    showCaptureResult(data);
    if (typeof refreshAll === 'function' && source !== 'tap') { /* other views refresh on their own next open */ }
    if (typeof loadReviewQueue === 'function') loadReviewQueue();
    if (reportMode === 'tap') { tapState = { step: 'what', event_type: null, item: null, qty: '', loss_reason: null }; renderTapStep(); }
  } catch (e) {
    setReportNote(t('error'));
  }
}
window.confirmReadback = confirmReadback;

// The server's preview reply becomes read-back rows. Called by app.js after a
// voice or typed note, and here after a photo.
function handlePreviewResponse(data, source, transcript) {
  if (data.error) { setReportNote(data.error); return; }
  const rows = [].concat(data.events || [], data.review_queue || []);
  showReadback(rows, source, transcript || data.raw_transcript || null);
}
window.handlePreviewResponse = handlePreviewResponse;

function setReportNote(text) {
  const el = rq('report-note');
  if (el) el.textContent = text || '';
}

// ===== Photo of the register =====
async function onPhotoChosen(input) {
  if (!requireCentre()) { input.value = ''; return; }
  const file = input.files && input.files[0];
  if (!file) return;
  const prev = rq('photo-preview');
  if (prev) { prev.src = URL.createObjectURL(file); prev.hidden = false; }
  setReportNote(t('photo.reading'));
  try {
    const fd = new FormData();
    fd.append('file', file, file.name || 'register.jpg');
    fd.append('facility_id', reportFacilityId());
    const res = await fetch('/api/v1/photo-note', { method: 'POST', body: fd });
    const data = await res.json();
    setReportNote('');
    handlePreviewResponse(data, 'photo', null);
  } catch (e) {
    setReportNote(t('error'));
  } finally {
    input.value = '';
  }
}
window.onPhotoChosen = onPhotoChosen;

// ===== Staff on duty today =====
// The one attendance figure the system will hold: what a centre reports,
// through the same pipeline, as personnel `count` events.
const STAFF_ROLES = [
  ['doctor', 'staff.doctor'], ['nurse', 'staff.nurse'], ['pharmacist', 'staff.pharmacist'],
  ['health assistant male', 'staff.hamale'], ['health assistant female', 'staff.hafemale'],
];
function renderStaffForm() {
  const host = rq('staff-form');
  if (!host) return;
  host.innerHTML = `
    <div class="tap-question">${t('staff.title')}</div>
    <p class="capture-hint">${t('staff.sub')}</p>
    <div class="staff-rows">${STAFF_ROLES.map(([key, label]) => `
      <label class="staff-row"><span>${t(label)}</span>
        <input type="number" min="0" max="99" inputmode="numeric" data-staff="${key}" placeholder="0"></label>`).join('')}</div>
    <button class="btn btn-primary btn-full" onclick="staffReadback()">${t('staff.save')}</button>`;
}
function staffReadback() {
  if (!requireCentre()) return;
  const rows = [];
  document.querySelectorAll('#staff-form input[data-staff]').forEach(inp => {
    if (inp.value === '') return;
    const key = inp.dataset.staff;
    const label = STAFF_ROLES.find(r => r[0] === key)[1];
    rows.push({ local_name: key, item_name: t(label), event_type: 'count',
                quantity: parseInt(inp.value, 10), unit: 'person' });
  });
  showReadback(rows, 'tap', null, 'personnel');
}
window.staffReadback = staffReadback;

// ===== Beds in use right now =====
// Bed occupancy on Today is modelled from admission volumes. This is the one
// path by which a real count reaches the ledger: bed `count` events, through
// the same pipeline, matched against the closed bed vocabulary.
const BED_KINDS = [['bed', 'beds.inpatient'], ['day care bed', 'beds.daycare']];
function renderBedsForm() {
  const host = rq('beds-form');
  if (!host) return;
  host.innerHTML = `
    <div class="tap-question">${t('beds.title')}</div>
    <p class="capture-hint">${t('beds.sub')}</p>
    <div class="staff-rows">${BED_KINDS.map(([key, label]) => `
      <label class="staff-row"><span>${t(label)}</span>
        <input type="number" min="0" max="999" inputmode="numeric" data-bed="${key}" placeholder="0"></label>`).join('')}</div>
    <button class="btn btn-primary btn-full" onclick="bedsReadback()">${t('beds.save')}</button>`;
}
function bedsReadback() {
  if (!requireCentre()) return;
  const rows = [];
  document.querySelectorAll('#beds-form input[data-bed]').forEach(inp => {
    if (inp.value === '') return;
    const key = inp.dataset.bed;
    const label = BED_KINDS.find(r => r[0] === key)[1];
    rows.push({ local_name: key, item_name: t(label), event_type: 'count',
                quantity: parseInt(inp.value, 10), unit: 'bed' });
  });
  showReadback(rows, 'tap', null, 'bed');
}
window.bedsReadback = bedsReadback;

// ===== Offline =====
function queueOffline(item) {
  if (!db) return;
  const id = Date.now().toString() + Math.random().toString(16).slice(2, 6);
  db.transaction(['offline-queue'], 'readwrite').objectStore('offline-queue').put({ id, ...item });
}
window.queueOffline = queueOffline;

function updateOfflineLine() {
  const el = rq('report-offline');
  if (!el) return;
  const render = (n) => {
    if (!navigator.onLine) {
      el.hidden = false;
      el.innerHTML = `<strong>${t('offline.now')}</strong> ${n ? `${n} ${t('offline.unsent')}` : ''}`;
    } else if (n) {
      el.hidden = false;
      el.innerHTML = `${n} ${t('online.unsent')}`;
    } else { el.hidden = true; el.innerHTML = ''; }
  };
  if (!db) { render(0); return; }
  try {
    const req = db.transaction(['offline-queue'], 'readonly').objectStore('offline-queue').count();
    req.onsuccess = () => render(req.result || 0);
    req.onerror = () => render(0);
  } catch (e) { render(0); }
}
window.updateOfflineLine = updateOfflineLine;
window.addEventListener('online', () => setTimeout(updateOfflineLine, 1500));
window.addEventListener('offline', updateOfflineLine);

function escapeHtml(s) {
  return String(s === null || s === undefined ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ===== Init =====
let reportReady = false;
function initReport() {
  applyReportStrings();
  renderCentre();
  updateOfflineLine();
  if (!reportReady) {
    reportReady = true;
    setReportMode('tap');
    loadQuickItems();
  } else if (reportMode === 'tap') {
    renderTapStep();
  }
}
window.initReport = initReport;
