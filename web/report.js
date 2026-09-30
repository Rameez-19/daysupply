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
    'lang.other': 'Language',
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
    'voice.hold': 'Tap the button and speak', 'voice.listening': 'Listening… tap again when you finish',
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
    'voice.short': 'That was too short. Tap, speak, then tap again.',
    'voice.unsupported': 'This phone cannot record here. Use Tap or Type instead.',
    'rv.approve': 'Approve',
    'rv.reject': 'Reject',
    'rv.qty': 'Quantity',
    'rv.type': 'What happened',
    'rv.sure': 'sure',
    'rv.notstated': 'not said',
    'rv.empty': 'Nothing is waiting. Every recent report was clear enough to save directly.',
    'rv.loading': 'Loading…',
    'rv.loaderror': 'Could not load the list. Check the network and try again.',
    'rv.askqty': 'How many? This report is waiting because the amount was not clear.',
    'rv.cannot': 'Could not approve this.',
    'rv.ago.min': 'min ago',
    'rv.ago.hr': 'h ago',
    'rv.ago.day': 'd ago',
    'reason.noqty': 'The amount was not said',
    'reason.lowconf': 'The system was not sure what it heard',
    'reason.nomatch': 'The medicine name was not recognised',
    'reason.badevent': 'It was not clear what happened to the stock',
    'photo.error': 'Could not read that photo. Try again in good light, with the page flat.',
    'scan.matching': 'Scanned. Finding the medicine…',
    'scan.askqty': 'How many?',
    'scan.denied': 'The camera could not be opened.',
    'work.busy': 'Working… this takes a few seconds',
    'work.retry': 'The system is busy. Nothing was lost; try again in a minute.',
    'chat.ph': 'e.g. paracetamol 200 tablets came in, ORS half a box left',
    'how.title': 'How it works',
    'how.1': 'Tap, speak, photograph, scan or type your report.',
    'how.2': 'Gemini turns speech, text or a photo of the register into medicines and amounts.',
    'how.3': 'Every medicine is matched to the national list. The AI never invents a drug code.',
    'how.4': 'You hear it read back and say yes. Anything unclear waits for the pharmacist.',
    'reason.overstock': 'More was given out than the stock on record',
  },
  hi: {
    'report.title': 'स्टॉक बताएँ',
    'report.sub': 'दबाएँ, बोलें, फ़ोटो लें या लिखें। सेव करने से पहले हर रिपोर्ट आपको पढ़कर सुनाई जाएगी।',
    'lang.other': 'भाषा',
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
    'voice.hold': 'बटन दबाएँ और बोलें', 'voice.listening': 'सुन रहे हैं… बोलकर फिर से दबाएँ',
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
    'voice.short': 'बहुत छोटा था। दबाएँ, बोलें, फिर दबाएँ।',
    'voice.unsupported': 'यह फ़ोन यहाँ रिकॉर्ड नहीं कर सकता। दबाएँ या लिखें का इस्तेमाल करें।',
    'rv.approve': 'मंज़ूर करें',
    'rv.reject': 'रद्द करें',
    'rv.qty': 'मात्रा',
    'rv.type': 'क्या हुआ',
    'rv.sure': 'भरोसा',
    'rv.notstated': 'नहीं बताया',
    'rv.empty': 'कुछ बाकी नहीं है। हाल की हर रिपोर्ट सीधे सेव हो गई।',
    'rv.loading': 'लोड हो रहा है…',
    'rv.loaderror': 'सूची लोड नहीं हुई। नेटवर्क देखें और फिर कोशिश करें।',
    'rv.askqty': 'कितनी? यह रिपोर्ट रुकी है क्योंकि मात्रा साफ़ नहीं थी।',
    'rv.cannot': 'यह मंज़ूर नहीं हो सका।',
    'rv.ago.min': 'मिनट पहले',
    'rv.ago.hr': 'घंटे पहले',
    'rv.ago.day': 'दिन पहले',
    'reason.noqty': 'मात्रा नहीं बताई गई',
    'reason.lowconf': 'सिस्टम को ठीक से समझ नहीं आया',
    'reason.nomatch': 'दवा का नाम पहचाना नहीं गया',
    'reason.badevent': 'साफ़ नहीं था कि स्टॉक के साथ क्या हुआ',
    'photo.error': 'फ़ोटो पढ़ी नहीं जा सकी। अच्छी रोशनी में, पन्ना सीधा रखकर फिर से लें।',
    'scan.matching': 'स्कैन हो गया। दवा ढूँढ रहे हैं…',
    'scan.askqty': 'कितनी?',
    'scan.denied': 'कैमरा नहीं खुल सका।',
    'work.busy': 'काम हो रहा है… कुछ सेकंड लगेंगे',
    'work.retry': 'सिस्टम व्यस्त है। कुछ खोया नहीं; एक मिनट बाद फिर कोशिश करें।',
    'chat.ph': 'जैसे: पैरासिटामोल की 200 गोलियाँ आईं, ORS आधा डिब्बा बचा',
    'how.title': 'यह कैसे काम करता है',
    'how.1': 'अपनी रिपोर्ट दबाकर, बोलकर, फ़ोटो लेकर, स्कैन करके या लिखकर दें।',
    'how.2': 'Gemini आवाज़, लिखे शब्दों या रजिस्टर की फ़ोटो से दवा और मात्रा निकालता है।',
    'how.3': 'हर दवा राष्ट्रीय सूची से मिलाई जाती है। AI कभी दवा का कोड नहीं बनाता।',
    'how.4': 'आप इसे सुनकर हाँ कहते हैं। जो साफ़ नहीं है वह फार्मासिस्ट के लिए रुकता है।',
    'reason.overstock': 'रिकॉर्ड में जितना स्टॉक है, उससे ज़्यादा दिया गया',
  },
  mr: {
    'report.title': 'साठा नोंदवा',
    'report.sub': 'दाबा, बोला, फोटो काढा किंवा लिहा. जतन करण्यापूर्वी प्रत्येक नोंद तुम्हाला वाचून दाखवली जाते.',
    'lang.other': 'भाषा',
    'centre.which': 'तुम्ही कोणत्या केंद्रासाठी नोंद करत आहात?',
    'centre.state': 'राज्य',
    'centre.district': 'जिल्हा',
    'centre.phc': 'केंद्र',
    'centre.pick': 'निवडा…',
    'centre.change': 'बदला',
    'centre.remembered': 'या फोनवर लक्षात ठेवले आहे.',
    'centre.needed': 'आधी तुमचे केंद्र निवडा.',
    'mode.tap': 'दाबा',
    'mode.voice': 'बोला',
    'mode.photo': 'फोटो',
    'mode.scan': 'स्कॅन',
    'mode.chat': 'लिहा',
    'mode.staff': 'आजचे कर्मचारी',
    'step.what': 'काय झाले?',
    'ev.received': 'औषध आले',
    'ev.dispensed': 'रुग्णांना दिले',
    'ev.count': 'साठा मोजला',
    'ev.lost': 'तुटले, मुदत संपली किंवा हरवले',
    'step.which': 'कोणते औषध?',
    'tile.other': 'दुसरे औषध',
    'tile.other.sub': 'नाव बोला किंवा लिहा',
    'step.howmany': 'किती?',
    'step.why': 'का?',
    'loss.broken': 'तुटले',
    'loss.damaged': 'खराब झाले',
    'loss.expired': 'मुदत संपली',
    'loss.spilled': 'सांडले',
    'loss.stolen': 'चोरी',
    'loss.unknown': 'माहीत नाही',
    'kp.clear': 'पुसा',
    'kp.back': 'मागे',
    'kp.next': 'पुढे',
    'rb.title': 'हे बरोबर आहे का?',
    'rb.yes': 'हो, जतन करा',
    'rb.no': 'नाही, पुन्हा करा',
    'rb.listen': 'ऐका',
    'rb.nothing': 'साठ्याची कोणतीही नोंद ओळखता आली नाही. पुन्हा प्रयत्न करा, किंवा औषध दाबून निवडा.',
    'rb.remove': 'काढा',
    'saving': 'जतन होत आहे…',
    'saved': 'जतन झाले',
    'held': 'फार्मासिस्टच्या तपासणीसाठी थांबवले',
    'saved.why': 'आता साठ्याच्या हिशोबात धरले आहे.',
    'offline.saved': 'नेटवर्क नाही. या फोनवर जतन केले; नेटवर्क आल्यावर पाठवले जाईल.',
    'offline.now': 'आत्ता नेटवर्क नाही.',
    'offline.unsent': 'नोंदी या फोनवरून पाठवायच्या बाकी.',
    'online.unsent': 'नोंदी अजून पाठवायच्या बाकी.',
    'voice.hold': 'बटण दाबा आणि बोला',
    'voice.listening': 'ऐकत आहे… बोलून झाल्यावर पुन्हा दाबा',
    'voice.working': 'समजून घेत आहे…',
    'voice.hint': 'मराठी, हिंदी, इंग्रजी किंवा मिसळून. उदा.: “पॅरासिटामॉलच्या २०० गोळ्या आल्या”',
    'voice.denied': 'मायक्रोफोनची परवानगी मिळाली नाही',
    'photo.hint': 'साठा रजिस्टरच्या पानाचा फोटो काढा. प्रत्येक ओळ तुम्हाला तपासायला दिसेल; तुम्ही हो म्हणेपर्यंत काहीही जतन होणार नाही.',
    'photo.take': 'फोटो काढा',
    'photo.reading': 'पान वाचत आहे…',
    'scan.hint': 'पाकिटावरील बारकोडकडे कॅमेरा धरा.',
    'scan.start': 'कॅमेरा सुरू करा',
    'scan.stop': 'थांबवा',
    'chat.hint': 'जसे बोलता तसेच लिहा.',
    'chat.send': 'पाठवा',
    'staff.title': 'आज कामावर कोण आहे?',
    'staff.sub': 'प्रत्येक पदासाठी उपस्थित लोकांची संख्या लिहा. प्रणालीकडे उपस्थितीचा हाच एक आकडा आहे: केंद्रे जे कळवतात.',
    'staff.doctor': 'डॉक्टर',
    'staff.nurse': 'परिचारिका / ANM',
    'staff.pharmacist': 'फार्मासिस्ट',
    'staff.hamale': 'आरोग्य सहाय्यक (पुरुष)',
    'staff.hafemale': 'आरोग्य सहाय्यक (स्त्री)',
    'staff.save': 'उपस्थिती जतन करा',
    'review.title': 'फार्मासिस्टसाठी: तपासणी बाकी',
    'review.sub': 'ज्याबद्दल मॉडेलला खात्री नव्हती. हे अजून साठ्याच्या हिशोबात नाही.',
    'error': 'सर्व्हरशी संपर्क झाला नाही. काहीही जतन झाले नाही.',
    'unit.tablet': 'गोळ्या',
    'unit.capsule': 'कॅप्सूल',
    'unit.vial': 'व्हायल',
    'unit.bottle': 'बाटल्या',
    'unit.strip': 'पट्ट्या',
    'unit.unit': 'युनिट',
    'unit.unknown': '',
    'unit.person': 'जण',
    'evs.received': 'आले',
    'evs.dispensed': 'दिले',
    'evs.count': 'साठ्यात',
    'evs.lost': 'हरवले किंवा खराब',
    'evs.dispatched': 'पाठवले',
    'evs.expired': 'मुदत संपली',
    'staff.present': 'कामावर',
    'mode.beds': 'आजचे बेड',
    'beds.title': 'आत्ता किती बेडवर रुग्ण आहेत?',
    'beds.sub': 'ज्या बेडवर रुग्ण आहे ते मोजा. प्रणालीकडे बेडचा हाच एक आकडा आहे जो अंदाजावर आधारित नाही.',
    'beds.inpatient': 'दाखल रुग्णांचे वापरातील बेड',
    'beds.daycare': 'डे-केअरचे वापरातील बेड',
    'beds.save': 'बेडची संख्या जतन करा',
    'unit.bed': 'बेड',
    'beds.inuse': 'वापरात',
    'voice.short': 'खूप लहान होते. दाबा, बोला, मग पुन्हा दाबा.',
    'voice.unsupported': 'हा फोन इथे रेकॉर्ड करू शकत नाही. दाबा किंवा लिहा वापरा.',
    'rv.approve': 'मंजूर करा',
    'rv.reject': 'नाकारा',
    'rv.qty': 'संख्या',
    'rv.type': 'काय झाले',
    'rv.sure': 'खात्री',
    'rv.notstated': 'सांगितले नाही',
    'rv.empty': 'काहीही बाकी नाही. अलीकडची प्रत्येक नोंद थेट जतन झाली.',
    'rv.loading': 'लोड होत आहे…',
    'rv.loaderror': 'यादी लोड झाली नाही. नेटवर्क तपासा आणि पुन्हा प्रयत्न करा.',
    'rv.askqty': 'किती? ही नोंद थांबली आहे कारण संख्या स्पष्ट नव्हती.',
    'rv.cannot': 'हे मंजूर होऊ शकले नाही.',
    'rv.ago.min': 'मिनिटांपूर्वी',
    'rv.ago.hr': 'तासांपूर्वी',
    'rv.ago.day': 'दिवसांपूर्वी',
    'reason.noqty': 'संख्या सांगितली नाही',
    'reason.lowconf': 'प्रणालीला नीट समजले नाही',
    'reason.nomatch': 'औषधाचे नाव ओळखता आले नाही',
    'reason.badevent': 'साठ्याचे काय झाले ते स्पष्ट नव्हते',
    'photo.error': 'फोटो वाचता आला नाही. चांगल्या प्रकाशात, पान सरळ ठेवून पुन्हा काढा.',
    'scan.matching': 'स्कॅन झाले. औषध शोधत आहे…',
    'scan.askqty': 'किती?',
    'scan.denied': 'कॅमेरा उघडता आला नाही.',
    'work.busy': 'काम सुरू आहे… काही सेकंद लागतील',
    'work.retry': 'प्रणाली व्यस्त आहे. काहीही हरवले नाही; एका मिनिटाने पुन्हा प्रयत्न करा.',
    'chat.ph': 'उदा.: पॅरासिटामॉलच्या 200 गोळ्या आल्या, ORS अर्धा डबा उरला',
    'how.title': 'हे कसे काम करते',
    'how.1': 'तुमची नोंद दाबून, बोलून, फोटो काढून, स्कॅन करून किंवा लिहून द्या.',
    'how.2': 'Gemini आवाज, लिहिलेला मजकूर किंवा रजिस्टरच्या फोटोतून औषध आणि संख्या काढते.',
    'how.3': 'प्रत्येक औषध राष्ट्रीय यादीशी जुळवले जाते. AI कधीही औषधाचा कोड तयार करत नाही.',
    'how.4': 'तुम्ही ते ऐकून हो म्हणता. जे स्पष्ट नाही ते फार्मासिस्टसाठी थांबते.',
    'reason.overstock': 'नोंदीतील साठ्यापेक्षा जास्त दिले गेले',
  },
  te: {
    'report.title': 'స్టాక్ నమోదు చేయండి',
    'report.sub': 'నొక్కండి, మాట్లాడండి, ఫోటో తీయండి లేదా టైప్ చేయండి. సేవ్ చేసే ముందు ప్రతి నమోదు మీకు చదివి వినిపిస్తుంది.',
    'lang.other': 'భాష',
    'centre.which': 'మీరు ఏ కేంద్రం కోసం నమోదు చేస్తున్నారు?',
    'centre.state': 'రాష్ట్రం',
    'centre.district': 'జిల్లా',
    'centre.phc': 'కేంద్రం',
    'centre.pick': 'ఎంచుకోండి…',
    'centre.change': 'మార్చండి',
    'centre.remembered': 'ఈ ఫోన్‌లో గుర్తుంచుకోబడింది.',
    'centre.needed': 'ముందుగా మీ కేంద్రాన్ని ఎంచుకోండి.',
    'mode.tap': 'నొక్కండి',
    'mode.voice': 'మాట్లాడండి',
    'mode.photo': 'ఫోటో',
    'mode.scan': 'స్కాన్',
    'mode.chat': 'టైప్',
    'mode.staff': 'నేటి సిబ్బంది',
    'step.what': 'ఏమి జరిగింది?',
    'ev.received': 'మందులు వచ్చాయి',
    'ev.dispensed': 'రోగులకు ఇచ్చాము',
    'ev.count': 'షెల్ఫ్ లెక్కించాము',
    'ev.lost': 'పగిలినవి, గడువు ముగిసినవి లేదా పోయినవి',
    'step.which': 'ఏ మందు?',
    'tile.other': 'వేరే మందు',
    'tile.other.sub': 'పేరు చెప్పండి లేదా టైప్ చేయండి',
    'step.howmany': 'ఎన్ని?',
    'step.why': 'ఎందుకు?',
    'loss.broken': 'పగిలింది',
    'loss.damaged': 'పాడైంది',
    'loss.expired': 'గడువు ముగిసింది',
    'loss.spilled': 'ఒలికిపోయింది',
    'loss.stolen': 'దొంగిలించబడింది',
    'loss.unknown': 'తెలియదు',
    'kp.clear': 'తుడిచివేయి',
    'kp.back': 'వెనుకకు',
    'kp.next': 'తదుపరి',
    'rb.title': 'ఇది సరైనదేనా?',
    'rb.yes': 'అవును, సేవ్ చేయండి',
    'rb.no': 'కాదు, మళ్ళీ మొదలుపెట్టండి',
    'rb.listen': 'వినండి',
    'rb.nothing': 'స్టాక్ సమాచారం ఏదీ గుర్తించబడలేదు. మళ్ళీ ప్రయత్నించండి, లేదా మందును నొక్కి ఎంచుకోండి.',
    'rb.remove': 'తొలగించు',
    'saving': 'సేవ్ అవుతోంది…',
    'saved': 'సేవ్ అయింది',
    'held': 'ఫార్మసిస్ట్ తనిఖీ కోసం ఆపబడింది',
    'saved.why': 'ఇప్పుడు స్టాక్ లెక్కలో చేరింది.',
    'offline.saved': 'నెట్‌వర్క్ లేదు. ఈ ఫోన్‌లో సేవ్ అయింది; నెట్‌వర్క్ వచ్చాక పంపబడుతుంది.',
    'offline.now': 'ప్రస్తుతం నెట్‌వర్క్ లేదు.',
    'offline.unsent': 'నమోదులు ఈ ఫోన్ నుండి పంపవలసి ఉంది.',
    'online.unsent': 'నమోదులు ఇంకా పంపవలసి ఉంది.',
    'voice.hold': 'బటన్ నొక్కి మాట్లాడండి',
    'voice.listening': 'వింటోంది… పూర్తయ్యాక మళ్ళీ నొక్కండి',
    'voice.working': 'అర్థం చేసుకుంటోంది…',
    'voice.hint': 'తెలుగు, హిందీ, ఇంగ్లీష్ లేదా కలిపి. ఉదా: “పారాసిటమాల్ 200 మాత్రలు వచ్చాయి”',
    'voice.denied': 'మైక్రోఫోన్ అనుమతి లభించలేదు',
    'photo.hint': 'స్టాక్ రిజిస్టర్ పేజీని ఫోటో తీయండి. ప్రతి వరుస మీరు తనిఖీ చేయడానికి చూపబడుతుంది; మీరు అవును అనే వరకు ఏదీ సేవ్ కాదు.',
    'photo.take': 'ఫోటో తీయండి',
    'photo.reading': 'పేజీని చదువుతోంది…',
    'scan.hint': 'ప్యాక్‌పై ఉన్న బార్‌కోడ్ వైపు కెమెరా పెట్టండి.',
    'scan.start': 'కెమెరా ప్రారంభించండి',
    'scan.stop': 'ఆపండి',
    'chat.hint': 'మాట్లాడినట్లే టైప్ చేయండి.',
    'chat.send': 'పంపండి',
    'staff.title': 'ఈ రోజు డ్యూటీలో ఎవరు ఉన్నారు?',
    'staff.sub': 'ప్రతి పదవికి హాజరైన వారి సంఖ్య నమోదు చేయండి. వ్యవస్థ వద్ద ఉన్న హాజరు సంఖ్య ఇదొక్కటే: కేంద్రాలు తెలిపేది.',
    'staff.doctor': 'డాక్టర్',
    'staff.nurse': 'నర్సు / ANM',
    'staff.pharmacist': 'ఫార్మసిస్ట్',
    'staff.hamale': 'ఆరోగ్య సహాయకుడు (పురుషుడు)',
    'staff.hafemale': 'ఆరోగ్య సహాయకురాలు (స్త్రీ)',
    'staff.save': 'హాజరు సేవ్ చేయండి',
    'review.title': 'ఫార్మసిస్ట్ కోసం: తనిఖీ మిగిలి ఉంది',
    'review.sub': 'మోడల్‌కు ఖచ్చితంగా తెలియనివి. ఇవి ఇంకా స్టాక్ లెక్కలో లేవు.',
    'error': 'సర్వర్‌ను చేరుకోలేకపోయాము. ఏదీ సేవ్ కాలేదు.',
    'unit.tablet': 'మాత్రలు',
    'unit.capsule': 'క్యాప్సూల్స్',
    'unit.vial': 'వయల్స్',
    'unit.bottle': 'సీసాలు',
    'unit.strip': 'స్ట్రిప్స్',
    'unit.unit': 'యూనిట్లు',
    'unit.unknown': '',
    'unit.person': 'మంది',
    'evs.received': 'వచ్చాయి',
    'evs.dispensed': 'ఇచ్చాము',
    'evs.count': 'షెల్ఫ్‌లో ఉన్నాయి',
    'evs.lost': 'పోయాయి లేదా పాడయ్యాయి',
    'evs.dispatched': 'పంపాము',
    'evs.expired': 'గడువు ముగిసింది',
    'staff.present': 'డ్యూటీలో',
    'mode.beds': 'నేటి పడకలు',
    'beds.title': 'ఇప్పుడు ఎన్ని పడకలపై రోగులు ఉన్నారు?',
    'beds.sub': 'రోగి ఉన్న పడకలను లెక్కించండి. వ్యవస్థ వద్ద అంచనా కాని పడకల సంఖ్య ఇదొక్కటే.',
    'beds.inpatient': 'వాడుకలో ఉన్న ఇన్‌పేషెంట్ పడకలు',
    'beds.daycare': 'వాడుకలో ఉన్న డే-కేర్ పడకలు',
    'beds.save': 'పడకల సంఖ్య సేవ్ చేయండి',
    'unit.bed': 'పడకలు',
    'beds.inuse': 'వాడుకలో',
    'voice.short': 'చాలా చిన్నది. నొక్కండి, మాట్లాడండి, మళ్ళీ నొక్కండి.',
    'voice.unsupported': 'ఈ ఫోన్ ఇక్కడ రికార్డ్ చేయలేదు. నొక్కండి లేదా టైప్ ఉపయోగించండి.',
    'rv.approve': 'ఆమోదించు',
    'rv.reject': 'తిరస్కరించు',
    'rv.qty': 'సంఖ్య',
    'rv.type': 'ఏమి జరిగింది',
    'rv.sure': 'నమ్మకం',
    'rv.notstated': 'చెప్పలేదు',
    'rv.empty': 'ఏదీ పెండింగ్‌లో లేదు. ఇటీవలి ప్రతి నమోదు నేరుగా సేవ్ అయింది.',
    'rv.loading': 'లోడ్ అవుతోంది…',
    'rv.loaderror': 'జాబితా లోడ్ కాలేదు. నెట్‌వర్క్ చూసి మళ్ళీ ప్రయత్నించండి.',
    'rv.askqty': 'ఎన్ని? సంఖ్య స్పష్టంగా లేనందున ఈ నమోదు ఆగింది.',
    'rv.cannot': 'దీన్ని ఆమోదించలేకపోయాము.',
    'rv.ago.min': 'నిమిషాల క్రితం',
    'rv.ago.hr': 'గంటల క్రితం',
    'rv.ago.day': 'రోజుల క్రితం',
    'reason.noqty': 'సంఖ్య చెప్పలేదు',
    'reason.lowconf': 'వ్యవస్థకు సరిగ్గా అర్థం కాలేదు',
    'reason.nomatch': 'మందు పేరు గుర్తించబడలేదు',
    'reason.badevent': 'స్టాక్‌కు ఏమి జరిగిందో స్పష్టంగా లేదు',
    'photo.error': 'ఫోటో చదవలేకపోయాము. మంచి వెలుతురులో, పేజీని నిటారుగా ఉంచి మళ్ళీ తీయండి.',
    'scan.matching': 'స్కాన్ అయింది. మందు కోసం వెతుకుతోంది…',
    'scan.askqty': 'ఎన్ని?',
    'scan.denied': 'కెమెరా తెరవలేకపోయాము.',
    'work.busy': 'పని జరుగుతోంది… కొన్ని సెకన్లు పడుతుంది',
    'work.retry': 'వ్యవస్థ బిజీగా ఉంది. ఏదీ పోలేదు; ఒక నిమిషం తర్వాత మళ్ళీ ప్రయత్నించండి.',
    'chat.ph': 'ఉదా: పారాసిటమాల్ 200 మాత్రలు వచ్చాయి, ORS సగం పెట్టె మిగిలింది',
    'how.title': 'ఇది ఎలా పనిచేస్తుంది',
    'how.1': 'మీ నమోదును నొక్కి, మాట్లాడి, ఫోటో తీసి, స్కాన్ చేసి లేదా టైప్ చేసి ఇవ్వండి.',
    'how.2': 'Gemini మాట, టైప్ చేసిన పాఠం లేదా రిజిస్టర్ ఫోటో నుండి మందు మరియు సంఖ్యను తీస్తుంది.',
    'how.3': 'ప్రతి మందు జాతీయ జాబితాతో సరిపోల్చబడుతుంది. AI ఎప్పుడూ మందు కోడ్‌ను సృష్టించదు.',
    'how.4': 'మీరు విని అవును అంటారు. స్పష్టంగా లేనిది ఫార్మసిస్ట్ కోసం ఆగుతుంది.',
    'reason.overstock': 'రికార్డులో ఉన్న స్టాక్ కంటే ఎక్కువ ఇచ్చారు',
  },
  bn: {
    'report.title': 'স্টক জানান',
    'report.sub': 'চাপুন, বলুন, ছবি তুলুন বা লিখুন। সেভ করার আগে প্রতিটি রিপোর্ট আপনাকে পড়ে শোনানো হবে।',
    'lang.other': 'ভাষা',
    'centre.which': 'আপনি কোন কেন্দ্রের জন্য রিপোর্ট করছেন?',
    'centre.state': 'রাজ্য',
    'centre.district': 'জেলা',
    'centre.phc': 'কেন্দ্র',
    'centre.pick': 'বেছে নিন…',
    'centre.change': 'বদলান',
    'centre.remembered': 'এই ফোনে মনে রাখা হয়েছে।',
    'centre.needed': 'আগে আপনার কেন্দ্র বেছে নিন।',
    'mode.tap': 'চাপুন',
    'mode.voice': 'বলুন',
    'mode.photo': 'ছবি',
    'mode.scan': 'স্ক্যান',
    'mode.chat': 'লিখুন',
    'mode.staff': 'আজকের কর্মী',
    'step.what': 'কী হয়েছে?',
    'ev.received': 'ওষুধ এসেছে',
    'ev.dispensed': 'রোগীদের দেওয়া হয়েছে',
    'ev.count': 'তাক গুনেছি',
    'ev.lost': 'ভাঙা, মেয়াদোত্তীর্ণ বা হারানো',
    'step.which': 'কোন ওষুধ?',
    'tile.other': 'অন্য ওষুধ',
    'tile.other.sub': 'নাম বলুন বা লিখুন',
    'step.howmany': 'কতগুলো?',
    'step.why': 'কেন?',
    'loss.broken': 'ভেঙে গেছে',
    'loss.damaged': 'নষ্ট হয়েছে',
    'loss.expired': 'মেয়াদ শেষ',
    'loss.spilled': 'পড়ে গেছে',
    'loss.stolen': 'চুরি',
    'loss.unknown': 'জানি না',
    'kp.clear': 'মুছুন',
    'kp.back': 'পিছনে',
    'kp.next': 'পরের',
    'rb.title': 'এটা কি ঠিক?',
    'rb.yes': 'হ্যাঁ, সেভ করুন',
    'rb.no': 'না, আবার শুরু করুন',
    'rb.listen': 'শুনুন',
    'rb.nothing': 'কোনো স্টকের তথ্য চেনা যায়নি। আবার চেষ্টা করুন, অথবা ওষুধে চেপে বেছে নিন।',
    'rb.remove': 'সরান',
    'saving': 'সেভ হচ্ছে…',
    'saved': 'সেভ হয়েছে',
    'held': 'ফার্মাসিস্টের যাচাইয়ের জন্য রাখা হয়েছে',
    'saved.why': 'এখন স্টকের হিসাবে যোগ হয়েছে।',
    'offline.saved': 'নেটওয়ার্ক নেই। এই ফোনে সেভ হয়েছে; নেটওয়ার্ক এলে পাঠানো হবে।',
    'offline.now': 'এখন নেটওয়ার্ক নেই।',
    'offline.unsent': 'রিপোর্ট এই ফোন থেকে পাঠানো বাকি।',
    'online.unsent': 'রিপোর্ট এখনও পাঠানো বাকি।',
    'voice.hold': 'বোতাম চেপে বলুন',
    'voice.listening': 'শুনছি… বলা শেষ হলে আবার চাপুন',
    'voice.working': 'বুঝছি…',
    'voice.hint': 'বাংলা, হিন্দি, ইংরেজি বা মিশিয়ে। যেমন: “প্যারাসিটামল ২০০টা ট্যাবলেট এসেছে”',
    'voice.denied': 'মাইক্রোফোনের অনুমতি পাওয়া যায়নি',
    'photo.hint': 'স্টক রেজিস্টারের পাতার ছবি তুলুন। প্রতিটি সারি আপনাকে যাচাই করতে দেখানো হবে; আপনি হ্যাঁ না বলা পর্যন্ত কিছুই সেভ হবে না।',
    'photo.take': 'ছবি তুলুন',
    'photo.reading': 'পাতা পড়ছি…',
    'scan.hint': 'প্যাকেটের বারকোডের দিকে ক্যামেরা ধরুন।',
    'scan.start': 'ক্যামেরা চালু করুন',
    'scan.stop': 'থামান',
    'chat.hint': 'যেভাবে বলেন সেভাবেই লিখুন।',
    'chat.send': 'পাঠান',
    'staff.title': 'আজ ডিউটিতে কে আছেন?',
    'staff.sub': 'প্রতিটি পদের জন্য উপস্থিত লোকের সংখ্যা লিখুন। সিস্টেমের কাছে উপস্থিতির এই একটিই সংখ্যা আছে: কেন্দ্রগুলো যা জানায়।',
    'staff.doctor': 'ডাক্তার',
    'staff.nurse': 'নার্স / ANM',
    'staff.pharmacist': 'ফার্মাসিস্ট',
    'staff.hamale': 'স্বাস্থ্য সহকারী (পুরুষ)',
    'staff.hafemale': 'স্বাস্থ্য সহকারী (মহিলা)',
    'staff.save': 'উপস্থিতি সেভ করুন',
    'review.title': 'ফার্মাসিস্টের জন্য: যাচাই বাকি',
    'review.sub': 'যেগুলো নিয়ে মডেল নিশ্চিত ছিল না। এগুলো এখনও স্টকের হিসাবে নেই।',
    'error': 'সার্ভারে পৌঁছানো যায়নি। কিছুই সেভ হয়নি।',
    'unit.tablet': 'ট্যাবলেট',
    'unit.capsule': 'ক্যাপসুল',
    'unit.vial': 'ভায়াল',
    'unit.bottle': 'বোতল',
    'unit.strip': 'স্ট্রিপ',
    'unit.unit': 'ইউনিট',
    'unit.unknown': '',
    'unit.person': 'জন',
    'evs.received': 'এসেছে',
    'evs.dispensed': 'দেওয়া হয়েছে',
    'evs.count': 'তাকে আছে',
    'evs.lost': 'হারিয়েছে বা নষ্ট',
    'evs.dispatched': 'পাঠানো হয়েছে',
    'evs.expired': 'মেয়াদ শেষ',
    'staff.present': 'ডিউটিতে',
    'mode.beds': 'আজকের বেড',
    'beds.title': 'এখন কতগুলো বেডে রোগী আছেন?',
    'beds.sub': 'যে বেডে রোগী আছেন সেগুলো গুনুন। সিস্টেমের কাছে বেডের এই একটিই সংখ্যা আছে যা অনুমান নয়।',
    'beds.inpatient': 'ভর্তি রোগীর ব্যবহৃত বেড',
    'beds.daycare': 'ডে-কেয়ারের ব্যবহৃত বেড',
    'beds.save': 'বেডের সংখ্যা সেভ করুন',
    'unit.bed': 'বেড',
    'beds.inuse': 'ব্যবহারে',
    'voice.short': 'খুব ছোট ছিল। চাপুন, বলুন, তারপর আবার চাপুন।',
    'voice.unsupported': 'এই ফোন এখানে রেকর্ড করতে পারে না। চাপুন বা লিখুন ব্যবহার করুন।',
    'rv.approve': 'অনুমোদন',
    'rv.reject': 'বাতিল',
    'rv.qty': 'সংখ্যা',
    'rv.type': 'কী হয়েছে',
    'rv.sure': 'নিশ্চিত',
    'rv.notstated': 'বলা হয়নি',
    'rv.empty': 'কিছুই বাকি নেই। সাম্প্রতিক প্রতিটি রিপোর্ট সরাসরি সেভ হয়েছে।',
    'rv.loading': 'লোড হচ্ছে…',
    'rv.loaderror': 'তালিকা লোড হয়নি। নেটওয়ার্ক দেখে আবার চেষ্টা করুন।',
    'rv.askqty': 'কতগুলো? সংখ্যা পরিষ্কার না থাকায় এই রিপোর্টটি আটকে আছে।',
    'rv.cannot': 'এটি অনুমোদন করা যায়নি।',
    'rv.ago.min': 'মিনিট আগে',
    'rv.ago.hr': 'ঘণ্টা আগে',
    'rv.ago.day': 'দিন আগে',
    'reason.noqty': 'সংখ্যা বলা হয়নি',
    'reason.lowconf': 'সিস্টেম ঠিকমতো বুঝতে পারেনি',
    'reason.nomatch': 'ওষুধের নাম চেনা যায়নি',
    'reason.badevent': 'স্টকের কী হয়েছে তা পরিষ্কার ছিল না',
    'photo.error': 'ছবিটি পড়া যায়নি। ভালো আলোয়, পাতা সোজা রেখে আবার তুলুন।',
    'scan.matching': 'স্ক্যান হয়েছে। ওষুধ খোঁজা হচ্ছে…',
    'scan.askqty': 'কতগুলো?',
    'scan.denied': 'ক্যামেরা খোলা যায়নি।',
    'work.busy': 'কাজ চলছে… কয়েক সেকেন্ড লাগবে',
    'work.retry': 'সিস্টেম ব্যস্ত। কিছুই হারায়নি; এক মিনিট পরে আবার চেষ্টা করুন।',
    'chat.ph': 'যেমন: প্যারাসিটামল ২০০টা ট্যাবলেট এসেছে, ORS অর্ধেক বাক্স বাকি',
    'how.title': 'এটি কীভাবে কাজ করে',
    'how.1': 'আপনার রিপোর্ট চেপে, বলে, ছবি তুলে, স্ক্যান করে বা লিখে দিন।',
    'how.2': 'Gemini কথা, লেখা বা রেজিস্টারের ছবি থেকে ওষুধ আর সংখ্যা বের করে।',
    'how.3': 'প্রতিটি ওষুধ জাতীয় তালিকার সঙ্গে মেলানো হয়। AI কখনও ওষুধের কোড বানায় না।',
    'how.4': 'আপনি শুনে হ্যাঁ বলেন। যা পরিষ্কার নয় তা ফার্মাসিস্টের জন্য অপেক্ষা করে।',
    'reason.overstock': 'রেকর্ডে থাকা স্টকের চেয়ে বেশি দেওয়া হয়েছে',
  },
};

// Every language the page reads in, with the name it is written in and the
// voice the read-back asks the phone for. Marathi, Telugu and Bengali cover
// the working languages of Maharashtra, Telangana and Assam's Barak Valley;
// Hindi covers Rajasthan, Delhi and Uttar Pradesh. Adding a language is one
// dictionary above and one line here.
const REPORT_LANGS = [
  ['en', 'English', 'en-IN'], ['hi', 'हिंदी', 'hi-IN'], ['mr', 'मराठी', 'mr-IN'],
  ['te', 'తెలుగు', 'te-IN'], ['bn', 'বাংলা', 'bn-IN'],
];
// Scripts in which the catalogue's Devanagari drug names are readable.
const DEVANAGARI_LANGS = ['hi', 'mr'];

let reportLang = 'en';
try {
  const saved = localStorage.getItem(REPORT_LANG_KEY);
  if (REPORT_LANGS.some(l => l[0] === saved)) reportLang = saved;
} catch (e) { /* private mode */ }

function t(key) {
  const table = REPORT_STRINGS[reportLang] || REPORT_STRINGS.en;
  return table[key] !== undefined ? table[key] : (REPORT_STRINGS.en[key] || key);
}

function rq(id) { return document.getElementById(id); }

function setLang(code) {
  if (!REPORT_LANGS.some(l => l[0] === code)) code = 'en';
  reportLang = code;
  try { localStorage.setItem(REPORT_LANG_KEY, reportLang); } catch (e) { /* ignore */ }
  applyReportStrings();
  renderTapStep();
  renderStaffForm();
  renderBedsForm();
  renderCentre();
  updateOfflineLine();
  if (typeof loadReviewQueue === 'function' && rq('review-list')) loadReviewQueue();
  // A read-back on screen is re-spoken in the new language, so the worker
  // who switched because they did not follow it hears it again.
  const rb = rq('report-readback');
  if (rb && !rb.hidden && readbackRows.length) showReadback(readbackRows, readbackSource, readbackTranscript, readbackResourceType);
}
window.setLang = setLang;

function applyReportStrings() {
  document.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll('[data-i18n-ph]').forEach(el => { el.placeholder = t(el.dataset.i18nPh); });
  const html = document.documentElement;
  if (html) html.setAttribute('data-report-lang', reportLang);
  const sel = document.getElementById('lang-select');
  if (sel) {
    if (!sel.options.length) {
      sel.innerHTML = REPORT_LANGS.map(([c, n]) => `<option value="${c}">${n}</option>`).join('');
    }
    sel.value = reportLang;
  }
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
          <span class="tile-name">${escapeHtml(DEVANAGARI_LANGS.includes(reportLang) && it.hindi_name ? it.hindi_name : it.display_name)}</span>
          <span class="tile-sub">${escapeHtml(DEVANAGARI_LANGS.includes(reportLang) && it.hindi_name ? it.display_name : (it.spoken || ''))}</span>
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

function tileName(it) { return DEVANAGARI_LANGS.includes(reportLang) && it.hindi_name ? it.hindi_name : it.display_name; }

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
  const name = DEVANAGARI_LANGS.includes(reportLang) && r.hindi_name ? r.hindi_name : (r.item_name || r.local_name || '?');
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
        ${r.review_reason ? `<span class="rb-reason">${escapeHtml(reasonText(r.review_reason))}</span>` : ''}
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
  stopSpeech();
}

// Why a report was held, in the worker's language. The server gives the
// reason in English for the audit trail; the page shows it translated.
function reasonText(reason) {
  const r = String(reason || '');
  if (/no quantity/i.test(r)) return t('reason.noqty');
  if (/confidence/i.test(r)) return t('reason.lowconf');
  if (/did not match/i.test(r)) return t('reason.nomatch');
  if (/not a stock movement/i.test(r)) return t('reason.badevent');
  if (/on record/i.test(r)) return t('reason.overstock');
  return r;
}
window.reasonText = reasonText;

// The read-back is spoken by Cloud Text-to-Speech. Phones have no Telugu,
// Marathi or Bengali voice of their own: the phone engine skipped every word
// it could not say and read out only the digits. The phone engine stays as
// the fallback when the network call fails.
let rbAudio = null;
function stopSpeech() {
  if (rbAudio) { try { rbAudio.pause(); } catch (e) { /* ignore */ } rbAudio = null; }
  if (window.speechSynthesis) window.speechSynthesis.cancel();
}
function speakWithPhone(text) {
  if (!window.speechSynthesis) return;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = (REPORT_LANGS.find(l => l[0] === reportLang) || REPORT_LANGS[0])[2];
  u.rate = 0.95;
  window.speechSynthesis.speak(u);
}
async function speakReadback() {
  if (!readbackRows.length) return;
  stopSpeech();
  const text = t('rb.title') + ' ' + readbackRows.map(rowSentence).join('. ');
  let blob = null;
  try {
    const res = await fetch('/api/v1/speak', { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, lang: reportLang }) });
    if (res.ok) blob = await res.blob();
  } catch (e) { blob = null; }
  if (!blob) { speakWithPhone(text); return; }
  rbAudio = new Audio(URL.createObjectURL(blob));
  // A phone may refuse to play sound the worker did not tap for; the
  // Listen button is that tap.
  rbAudio.play().catch(() => {});
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
  if (data.error) {
    setReportNote(data.retryable ? t('work.retry') : (source === 'photo' ? t('photo.error') : t('work.retry')), 'error');
    return;
  }
  setReportNote('');
  const rows = [].concat(data.events || [], data.review_queue || []);
  showReadback(rows, source, transcript || data.raw_transcript || null);
}
window.handlePreviewResponse = handlePreviewResponse;

function setReportNote(text, kind) {
  const el = rq('report-note');
  if (!el) return;
  el.textContent = text || '';
  el.className = 'report-note' + (text && kind ? ' ' + kind : '');
}
window.setReportNote = setReportNote;

// ===== Photo of the register =====
async function onPhotoChosen(input) {
  if (!requireCentre()) { input.value = ''; return; }
  const file = input.files && input.files[0];
  if (!file) return;
  const prev = rq('photo-preview');
  if (prev) { prev.src = URL.createObjectURL(file); prev.hidden = false; }
  setReportNote(t('photo.reading'), 'busy');
  try {
    const small = await shrinkImage(file);
    const fd = new FormData();
    fd.append('file', small, 'register.jpg');
    fd.append('facility_id', reportFacilityId());
    const res = await fetch('/api/v1/photo-note', { method: 'POST', body: fd });
    const data = await res.json();
    handlePreviewResponse(data, 'photo', null);
  } catch (e) {
    setReportNote(t('error'), 'error');
  } finally {
    input.value = '';
  }
}
window.onPhotoChosen = onPhotoChosen;

// A phone photo is 3-12 MB. Sent as it is, it crawls over a rural data
// connection; the model needs nothing like that resolution to read a page.
async function shrinkImage(file, maxSide = 1600, quality = 0.85) {
  try {
    const bmp = await createImageBitmap(file);
    const scale = Math.min(1, maxSide / Math.max(bmp.width, bmp.height));
    const c = document.createElement('canvas');
    c.width = Math.round(bmp.width * scale); c.height = Math.round(bmp.height * scale);
    c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height);
    const blob = await new Promise(r => c.toBlob(r, 'image/jpeg', quality));
    return blob && blob.size < file.size ? blob : file;
  } catch (e) {
    return file;
  }
}

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
