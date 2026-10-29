/**
 * SMART MEDICATION ADHERENCE SYSTEM - CLIENT SCRIPT
 * Manages Reminders, Dose Confirmations (TAKEN/MISSED), Analytics Charts, and UI Modals.
 */

let activeMedicationId = null;
let activeAdherenceId = null;
let adherenceWeeklyChart = null;
let adherenceDoughnutChart = null;

document.addEventListener('DOMContentLoaded', () => {
  // Check if charts should be initialized on this page
  if (document.getElementById('weeklyAdherenceChart')) {
    loadAnalyticsCharts();
  }

  // Setup notification bell toggle if present
  const bellBtn = document.getElementById('notifBellBtn');
  if (bellBtn) {
    bellBtn.addEventListener('click', toggleNotificationsDrawer);
  }
});

/**
 * Trigger Instant Test Reminder (For College Demo)
 * Called when patient clicks "🔔 Test Reminder" button in the table.
 */
async function triggerTestReminder(medId) {
  try {
    const response = await fetch(`/reminder/test/${medId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });

    const data = await response.json();
    if (data.success && data.medication) {
      showReminderModal(data.medication);
    } else {
      alert(data.message || 'Error triggering reminder');
    }
  } catch (err) {
    console.error('Error fetching reminder:', err);
    alert('Failed to connect to reminder engine.');
  }
}

/**
 * Display the In-App Reminder Modal
 */
function showReminderModal(med) {
  activeMedicationId = med.id;
  activeAdherenceId = med.adherence_id;

  const modal = document.getElementById('reminderModal');
  const nameEl = document.getElementById('modalMedName');
  const dosageEl = document.getElementById('modalMedDosage');
  const timeEl = document.getElementById('modalMedTime');

  if (nameEl) nameEl.textContent = med.medicine_name;
  if (dosageEl) dosageEl.textContent = med.dosage;
  if (timeEl) timeEl.textContent = `Scheduled: ${med.scheduled_time}`;

  if (modal) {
    modal.classList.add('active');
  }
}

/**
 * Close the Reminder Modal
 */
function closeReminderModal() {
  const modal = document.getElementById('reminderModal');
  if (modal) {
    modal.classList.remove('active');
  }
  activeMedicationId = null;
  activeAdherenceId = null;
}

/**
 * Confirm Dose as TAKEN or MISSED
 */
async function confirmDose(status) {
  if (!activeMedicationId && !activeAdherenceId) {
    alert('No active medication selected.');
    return;
  }

  try {
    const payload = {
      medication_id: activeMedicationId,
      adherence_id: activeAdherenceId,
      status: status
    };

    const response = await fetch('/adherence/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const result = await response.json();

    if (result.success) {
      closeReminderModal();
      // Show feedback and reload dashboard to update all tables, status pills, and charts
      window.location.reload();
    } else {
      alert(result.message || 'Error recording dose status.');
    }
  } catch (err) {
    console.error('Error confirming dose:', err);
    alert('Server error occurred during confirmation.');
  }
}

/**
 * Open Delete Confirmation Modal
 */
function confirmDelete(medId, medName) {
  const isConfirmed = window.confirm(`Are you sure you want to delete "${medName}"? All scheduled adherence logs for this medicine will also be removed.`);
  if (isConfirmed) {
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = `/medications/delete/${medId}`;
    document.body.appendChild(form);
    form.submit();
  }
}

/**
 * Toggle Notifications Drawer
 */
async function toggleNotificationsDrawer() {
  const drawer = document.getElementById('notifDrawer');
  if (!drawer) return;

  const isVisible = drawer.classList.contains('active');
  if (isVisible) {
    drawer.classList.remove('active');
  } else {
    drawer.classList.add('active');
    // Fetch latest notifications
    try {
      const resp = await fetch('/notifications');
      const data = await resp.json();
      const listContainer = document.getElementById('notifList');
      if (listContainer && data.notifications) {
        if (data.notifications.length === 0) {
          listContainer.innerHTML = '<p style="color:var(--text-dim); font-size:0.8rem; text-align:center; padding:12px;">No notifications yet.</p>';
        } else {
          listContainer.innerHTML = data.notifications.map(n => `
            <div class="notif-item ${n.type === 'MISSED_DOSE' ? 'missed' : ''}">
              <div style="font-weight:600; color:#FFFFFF; margin-bottom:2px;">
                ${n.type === 'MISSED_DOSE' ? '⚠ Missed Dose Alert' : '🔔 Reminder'}
              </div>
              <div>${n.message}</div>
              <div style="font-size:0.7rem; color:var(--text-dim); margin-top:4px;">${n.created_at}</div>
            </div>
          `).join('');
        }
      }
    } catch (e) {
      console.error('Failed to load notifications:', e);
    }
  }
}

/**
 * Load Analytics Charts using Chart.js with real SQLite backend data
 */
async function loadAnalyticsCharts() {
  try {
    const response = await fetch('/api/analytics');
    const data = await response.json();

    if (!data || data.error) return;

    // Update KPI counters if present
    const todayPctEl = document.getElementById('statTodayPct');
    if (todayPctEl) todayPctEl.textContent = `${data.today_percentage}%`;

    const weekPctEl = document.getElementById('statWeeklyPct');
    if (weekPctEl) weekPctEl.textContent = `${data.weekly_percentage}%`;

    // 1. Weekly Adherence Bar Chart
    const weeklyCanvas = document.getElementById('weeklyAdherenceChart');
    if (weeklyCanvas) {
      const ctx = weeklyCanvas.getContext('2d');
      if (adherenceWeeklyChart) adherenceWeeklyChart.destroy();

      adherenceWeeklyChart = new Chart(ctx, {
        type: 'bar',
        data: {
          labels: data.weekly_labels,
          datasets: [{
            label: 'Adherence Rate (%)',
            data: data.weekly_adherence,
            backgroundColor: 'rgba(0, 242, 254, 0.65)',
            borderColor: '#00F2FE',
            borderWidth: 1.5,
            borderRadius: 6,
            hoverBackgroundColor: '#00F2FE'
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            y: {
              beginAtZero: true,
              max: 100,
              ticks: { color: '#94A3B8', font: { family: 'Inter', size: 11 } },
              grid: { color: 'rgba(255, 255, 255, 0.05)' }
            },
            x: {
              ticks: { color: '#94A3B8', font: { family: 'Inter', size: 11 } },
              grid: { display: false }
            }
          },
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (ctx) => `Adherence: ${ctx.parsed.y}%`
              }
            }
          }
        }
      });
    }

    // 2. Taken vs Missed vs Pending Doughnut Chart
    const doughnutCanvas = document.getElementById('distributionChart');
    if (doughnutCanvas) {
      const ctx2 = doughnutCanvas.getContext('2d');
      if (adherenceDoughnutChart) adherenceDoughnutChart.destroy();

      const dist = data.distribution;
      adherenceDoughnutChart = new Chart(ctx2, {
        type: 'doughnut',
        data: {
          labels: ['Taken', 'Missed', 'Pending'],
          datasets: [{
            data: [dist.taken, dist.missed, dist.pending],
            backgroundColor: [
              '#10B981', // Taken
              '#EF4444', // Missed
              '#F59E0B'  // Pending
            ],
            borderColor: '#0E1729',
            borderWidth: 3
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              position: 'bottom',
              labels: { color: '#E2E8F0', font: { family: 'Inter', size: 12 }, boxWidth: 14 }
            }
          },
          cutout: '70%'
        }
      });
    }

  } catch (err) {
    console.error('Error loading analytics charts:', err);
  }
}

/* ==========================================================================
   MEDIVOICE MULTILINGUAL AI VOICE ASSISTANT CONTROLLER
   Supports English (en-IN), Hindi (hi-IN), Telugu (te-IN), Tamil (ta-IN)
   ========================================================================== */

let recognition = null;
let isListening = false;
let isSpeaking = false;
let currentLang = localStorage.getItem('medivoice_lang') || 'en-IN';
let availableVoices = [];

// Cache system voices when loaded
if ('speechSynthesis' in window) {
  availableVoices = window.speechSynthesis.getVoices();
  window.speechSynthesis.onvoiceschanged = () => {
    availableVoices = window.speechSynthesis.getVoices();
  };
}

document.addEventListener('DOMContentLoaded', () => {
  // Initialize current language dropdowns
  const langSelect = document.getElementById('medivoiceLangSelect');
  if (langSelect) {
    langSelect.value = currentLang;
  }

  // Sync speaker toggle icon
  syncSpeakerIcon();

  // Render localized quick prompt chips
  renderQuickPromptChips();

  // Load chat history from sessionStorage
  restoreMediVoiceChatHistory();

  // Initialize Speech Recognition
  initSpeechRecognition();

  // Enter key support for MediVoice text input
  const textInput = document.getElementById('medivoiceInput');
  if (textInput) {
    textInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        sendMediVoiceMessage();
      }
    });
  }
});

/**
 * Handle explicit language change from dropdown or settings
 */
function onMediVoiceLanguageChange(newLang) {
  if (!newLang) return;
  currentLang = newLang;
  localStorage.setItem('medivoice_lang', newLang);

  const langSelect = document.getElementById('medivoiceLangSelect');
  if (langSelect && langSelect.value !== newLang) {
    langSelect.value = newLang;
  }
  const settingsSelect = document.getElementById('voiceLangPreference');
  if (settingsSelect && settingsSelect.value !== newLang) {
    settingsSelect.value = newLang;
  }

  // Update speech recognition language
  if (recognition) {
    recognition.lang = currentLang;
  }

  // Update quick prompt chips to match new language
  renderQuickPromptChips();

  // Update placeholder
  const input = document.getElementById('medivoiceInput');
  if (input) {
    const placeholders = {
      'en-IN': 'Speak or type a question in English...',
      'hi-IN': 'हिन्दी में बोलें या टाइप करें...',
      'te-IN': 'తెలుగులో మాట్లాడండి లేదా టైప్ చేయండి...',
      'ta-IN': 'தமிழில் பேசவும் அல்லது தட்டச்சு செய்யவும்...'
    };
    input.placeholder = placeholders[newLang] || 'Speak or type a question...';
  }
}

/**
 * Render dynamic quick prompt chips according to current language and user role
 */
function renderQuickPromptChips() {
  const container = document.getElementById('medivoiceQuickPrompts');
  if (!container) return;

  const isCaregiver = window.location.pathname.includes('/caregiver') || !!document.getElementById('caregiverPatientSelect');

  const prompts = {
    'en-IN': isCaregiver ? [
      { label: "🚨 Missed Today", text: "Which patients missed a dose today?" },
      { label: "📈 7-Day Adherence", text: "Show this patient's adherence for the last seven days" },
      { label: "⏳ Pending Doses", text: "Which medicines have pending scheduled doses?" },
      { label: "📋 Missed Summary", text: "Summarize this patient's recent missed doses" }
    ] : [
      { label: "💊 Today's Medicines", text: "What medicines do I need to take today?" },
      { label: "📊 My Adherence", text: "What is my adherence percentage?" },
      { label: "⚠️ Missed Doses", text: "Have I missed any doses this week?" },
      { label: "✓ Mark Taken", text: "I took my medicine" },
      { label: "❓ How to use app", text: "How do I use this system?" }
    ],
    'hi-IN': isCaregiver ? [
      { label: "🚨 आज छूटी दवाएँ", text: "आज किन मरीजों की दवा छूटी है?" },
      { label: "📈 7 दिन का रिकॉर्ड", text: "पिछले 7 दिनों का अनुपालन रिकॉर्ड दिखाएं" },
      { label: "⏳ लंबित दवाएँ", text: "किन दवाओं की खुराक अभी बाकी है?" },
      { label: "📋 छूटी खुराकें", text: "छूटी हुई दवाओं का विवरण दें" }
    ] : [
      { label: "💊 आज की दवाइयाँ", text: "आज मुझे कौन सी दवाइयाँ लेनी हैं?" },
      { label: "📊 अनुपालन प्रतिशत", text: "मेरा अनुपालन प्रतिशत कितना है?" },
      { label: "⚠️ छूटी खुराकें", text: "क्या मेरी कोई खुराक छूटी है?" },
      { label: "✓ दवा ले ली", text: "मैंने अपनी दवा ले ली है" },
      { label: "❓ ऐप का उपयोग", text: "मैं इस ऐप का उपयोग कैसे करूँ?" }
    ],
    'te-IN': isCaregiver ? [
      { label: "🚨 మిస్ అయిన డోస్‌లు", text: "ఈరోజు ఏ పేషెంట్లు మందు మిస్ అయ్యారు?" },
      { label: "📈 7 రోజుల రిపోర్ట్", text: "గత 7 రోజుల అనుసరణ చూపించండి" },
      { label: "⏳ పెండింగ్ డోస్‌లు", text: "ఏ మందులు ఇంకా వేసుకోవాల్సి ఉంది?" },
      { label: "📋 వివరాలు", text: "మిస్ అయిన డోస్‌ల వివరాలు ఇవ్వండి" }
    ] : [
      { label: "💊 ఈరోజు మందులు", text: "ఈరోజు నేను ఏ మందులు వేసుకోవాలి?" },
      { label: "📊 నా అనుసరణ శాతం", text: "నా మందుల అనుసరణ శాతం ఎంత?" },
      { label: "⚠️ మిస్ అయిన డోస్‌లు", text: "ఈ వారం నేను ఏమైనా మందులు మిస్ అయ్యానా?" },
      { label: "✓ మందు వేసుకున్నాను", text: "నేను మందు వేసుకున్నాను" },
      { label: "❓ యాప్ ఎలా వాడాలి", text: "ఈ సిస్టమ్‌ను ఎలా ఉపయోగించాలి?" }
    ],
    'ta-IN': isCaregiver ? [
      { label: "🚨 இன்று தவறவிட்டவர்கள்", text: "இன்று யார் மருந்தை தவறவிட்டார்கள்?" },
      { label: "📈 7 நாள் அறிக்கை", text: "கடந்த 7 நாட்களின் பின்பற்றுதலைக் காட்டுங்கள்" },
      { label: "⏳ நிலுவை மருந்துகள்", text: "எந்த மருந்துகள் நிலுவையில் உள்ளன?" },
      { label: "📋 சுருக்கம்", text: "தவறவிட்ட மருந்துகளின் சுருக்கத்தைக் கொடுங்கள்" }
    ] : [
      { label: "💊 இன்றைய மருந்துகள்", text: "இன்று நான் என்ன மருந்துகளை எடுக்க வேண்டும்?" },
      { label: "📊 பின்பற்றுதல் விகிதம்", text: "எனது மருந்து பின்பற்றுதல் சதவீதம் என்ன?" },
      { label: "⚠️ தவறவிட்ட மருந்துகள்", text: "நான் ஏதேனும் மருந்துகளை தவறவிட்டேனா?" },
      { label: "✓ மருந்து எடுத்தேன்", text: "நான் மருந்து எடுத்துக்கொண்டேன்" },
      { label: "❓ செயலியை பயன்படுத்த", text: "இந்த அமைப்பை எவ்வாறு பயன்படுத்துவது?" }
    ]
  };

  const list = prompts[currentLang] || prompts['en-IN'];
  container.innerHTML = '';
  list.forEach(item => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'medivoice-chip';
    btn.textContent = item.label;
    btn.onclick = () => sendQuickChip(item.text);
    container.appendChild(btn);
  });
}

/**
 * Initialize Web Speech API SpeechRecognition with Multilingual Support
 */
function initSpeechRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    console.warn('Web Speech Recognition API is not supported in this browser. Fallback to typed chat.');
    return;
  }

  recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.lang = currentLang;

  recognition.onstart = () => {
    isListening = true;
    updateMediVoiceStatus('listening', 'Listening in ' + currentLang + '...');
    const micBtn = document.getElementById('medivoiceMicBtn');
    if (micBtn) micBtn.classList.add('listening');
    const preview = document.getElementById('medivoiceLivePreview');
    if (preview) {
      preview.textContent = 'Listening... Speak clearly in your selected language';
      preview.classList.add('active');
    }
  };

  recognition.onresult = (event) => {
    let interimTranscript = '';
    let finalTranscript = '';

    for (let i = event.resultIndex; i < event.results.length; ++i) {
      if (event.results[i].isFinal) {
        finalTranscript += event.results[i][0].transcript;
      } else {
        interimTranscript += event.results[i][0].transcript;
      }
    }

    const preview = document.getElementById('medivoiceLivePreview');
    if (preview) {
      preview.textContent = interimTranscript || finalTranscript;
      preview.classList.add('active');
    }

    if (finalTranscript) {
      appendMediVoiceMessage('user', finalTranscript);
      processMediVoiceBackend(finalTranscript);
    }
  };

  recognition.onerror = (event) => {
    console.warn('Speech recognition error event:', event.error);
    isListening = false;
    const micBtn = document.getElementById('medivoiceMicBtn');
    if (micBtn) micBtn.classList.remove('listening');

    let msg = 'Voice recognition error.';
    if (event.error === 'not-allowed') {
      msg = 'Microphone permission denied. You can enable microphone permissions in your browser or type your question below.';
    } else if (event.error === 'no-speech') {
      msg = 'No speech was detected. Please click the microphone button again or type your message.';
    } else if (event.error === 'network') {
      msg = 'Speech recognition network error. Please verify your connection or type your question.';
    }
    updateMediVoiceStatus('idle', 'Online • Ready');
    appendMediVoiceMessage('assistant', `⚠️ ${msg}`);
  };

  recognition.onend = () => {
    isListening = false;
    const micBtn = document.getElementById('medivoiceMicBtn');
    if (micBtn) micBtn.classList.remove('listening');
    const preview = document.getElementById('medivoiceLivePreview');
    if (preview) preview.classList.remove('active');
    if (!isSpeaking) {
      updateMediVoiceStatus('idle', 'Online • Ready');
    }
  };
}

/**
 * Toggle MediVoice Drawer
 */
function toggleMediVoice() {
  const drawer = document.getElementById('medivoiceDrawer');
  if (!drawer) return;
  drawer.classList.toggle('active');

  // Cancel speech synthesis if closing
  if (!drawer.classList.contains('active')) {
    stopSpeaking();
  } else {
    // Focus input when opened
    const input = document.getElementById('medivoiceInput');
    if (input) input.focus();
  }
}

/**
 * Trigger voice listening
 */
function toggleListening() {
  if (!recognition) {
    alert('Speech recognition is not supported in this browser. Please use the text input below to chat with MediVoice.');
    return;
  }

  // If assistant is currently speaking, stop it first
  stopSpeaking();

  if (isListening) {
    recognition.stop();
  } else {
    try {
      recognition.lang = currentLang; // ensure matching language before recording
      recognition.start();
    } catch (err) {
      console.warn('Recognition start error:', err);
    }
  }
}

/**
 * Send typed message
 */
function sendMediVoiceMessage() {
  const input = document.getElementById('medivoiceInput');
  if (!input) return;
  const text = input.value.trim();
  if (!text) return;

  input.value = '';
  appendMediVoiceMessage('user', text);
  processMediVoiceBackend(text);
}

/**
 * Send Quick Chip prompt
 */
function sendQuickChip(promptText) {
  appendMediVoiceMessage('user', promptText);
  processMediVoiceBackend(promptText);
}

/**
 * Call Flask backend endpoint: POST /api/medivoice/chat
 */
async function processMediVoiceBackend(messageText) {
  updateMediVoiceStatus('thinking', 'Processing query...');

  try {
    // Check if target patient ID is present (e.g., on Caregiver dashboard)
    const patientSelect = document.getElementById('caregiverPatientSelect');
    const targetPatientId = patientSelect ? patientSelect.value : null;

    const response = await fetch('/api/medivoice/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: messageText,
        language: currentLang,
        target_patient_id: targetPatientId
      })
    });

    const data = await response.json();
    if (data.success && data.reply) {
      const detectedLang = data.language || currentLang;
      appendMediVoiceMessage('assistant', data.reply, detectedLang);
      speakText(data.reply, detectedLang);

      // Handle safe navigation actions
      if (data.action) {
        if (data.action.type === 'navigate' && data.action.url) {
          setTimeout(() => { window.location.href = data.action.url; }, 2200);
        } else if (data.action.type === 'refresh_dashboard') {
          setTimeout(() => { window.location.reload(); }, 2400);
        }
      }
    } else {
      appendMediVoiceMessage('assistant', data.reply || 'Sorry, I encountered an issue processing your request.', currentLang);
      updateMediVoiceStatus('idle', 'Online • Ready');
    }
  } catch (err) {
    console.error('MediVoice backend error:', err);
    appendMediVoiceMessage('assistant', '⚠️ Unable to reach MediVoice service. Please check your connection.', currentLang);
    updateMediVoiceStatus('idle', 'Online • Ready');
  }
}

/**
 * Speak assistant text aloud using SpeechSynthesis API in the requested language
 */
function speakText(text, lang) {
  const isMuted = localStorage.getItem('medivoice_mute') === 'true';
  if (isMuted || !('speechSynthesis' in window)) {
    updateMediVoiceStatus('idle', 'Online • Ready');
    return;
  }

  window.speechSynthesis.cancel(); // Stop any pending speech

  const targetLang = lang || currentLang || 'en-IN';
  const cleanText = text.replace(/[*_#`~🚨⚠️✓✕•]/g, '').trim();
  const utterance = new SpeechSynthesisUtterance(cleanText);
  utterance.lang = targetLang;
  utterance.rate = parseFloat(localStorage.getItem('medivoice_rate') || '1.0');

  // Match best voice from available voices
  if (availableVoices && availableVoices.length > 0) {
    const langCode = targetLang.toLowerCase().split('-')[0]; // e.g. 'te', 'hi', 'ta', 'en'
    const matchedVoice = availableVoices.find(v => {
      const vLang = v.lang.toLowerCase();
      return vLang === targetLang.toLowerCase() || vLang.startsWith(langCode);
    });
    if (matchedVoice) {
      utterance.voice = matchedVoice;
    }
  }

  utterance.onstart = () => {
    isSpeaking = true;
    updateMediVoiceStatus('speaking', 'Speaking response...');
    const stopBtn = document.getElementById('medivoiceStopBtn');
    if (stopBtn) stopBtn.classList.add('active');
  };

  utterance.onend = () => {
    isSpeaking = false;
    updateMediVoiceStatus('idle', 'Online • Ready');
    const stopBtn = document.getElementById('medivoiceStopBtn');
    if (stopBtn) stopBtn.classList.remove('active');
  };

  utterance.onerror = (e) => {
    console.warn('Speech synthesis utterance error:', e);
    isSpeaking = false;
    updateMediVoiceStatus('idle', 'Online • Ready');
    const stopBtn = document.getElementById('medivoiceStopBtn');
    if (stopBtn) stopBtn.classList.remove('active');
  };

  window.speechSynthesis.speak(utterance);
}

/**
 * Replay an assistant message
 */
function replayMessage(text, lang) {
  stopSpeaking();
  speakText(text, lang || currentLang);
}

/**
 * Stop Speaking immediately
 */
function stopSpeaking() {
  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel();
  }
  isSpeaking = false;
  const stopBtn = document.getElementById('medivoiceStopBtn');
  if (stopBtn) stopBtn.classList.remove('active');
  updateMediVoiceStatus('idle', 'Online • Ready');
}

/**
 * Toggle Speaker Mute State
 */
function toggleSpeakerMute() {
  const isMuted = localStorage.getItem('medivoice_mute') === 'true';
  const newMuted = !isMuted;
  localStorage.setItem('medivoice_mute', newMuted ? 'true' : 'false');
  if (newMuted) {
    stopSpeaking();
  }
  syncSpeakerIcon();

  const settingsCheckbox = document.getElementById('voiceMuteToggle');
  if (settingsCheckbox) settingsCheckbox.checked = newMuted;
}

/**
 * Sync Speaker Icon based on mute state
 */
function syncSpeakerIcon() {
  const isMuted = localStorage.getItem('medivoice_mute') === 'true';
  const onIcon = document.getElementById('speakerOnIcon');
  const offIcon = document.getElementById('speakerOffIcon');
  if (onIcon && offIcon) {
    if (isMuted) {
      onIcon.style.display = 'none';
      offIcon.style.display = 'block';
    } else {
      onIcon.style.display = 'block';
      offIcon.style.display = 'none';
    }
  }
}

/**
 * Append message bubble to chat window with persistent storage and replay button
 */
function appendMediVoiceMessage(sender, text, lang) {
  const messagesBox = document.getElementById('medivoiceMessages');
  if (!messagesBox) return;

  const wrapper = document.createElement('div');
  wrapper.className = `medivoice-msg-wrapper ${sender}`;

  const msgDiv = document.createElement('div');
  msgDiv.className = `medivoice-msg ${sender}`;
  msgDiv.textContent = text;
  wrapper.appendChild(msgDiv);

  if (sender === 'assistant') {
    const replayBtn = document.createElement('button');
    replayBtn.type = 'button';
    replayBtn.className = 'medivoice-replay-btn';
    replayBtn.innerHTML = `
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
        <path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>
      </svg>
      <span>Replay</span>
    `;
    replayBtn.onclick = () => replayMessage(text, lang || currentLang);
    wrapper.appendChild(replayBtn);
  }

  messagesBox.appendChild(wrapper);
  messagesBox.scrollTop = messagesBox.scrollHeight;

  // Persist to sessionStorage
  saveMediVoiceChatHistory(sender, text, lang);
}

/**
 * Session storage conversation persistence
 */
function saveMediVoiceChatHistory(sender, text, lang) {
  try {
    let history = JSON.parse(sessionStorage.getItem('medivoice_history') || '[]');
    history.push({ sender, text, lang: lang || currentLang, time: Date.now() });
    if (history.length > 50) history = history.slice(-50);
    sessionStorage.setItem('medivoice_history', JSON.stringify(history));
  } catch (e) {
    console.warn('Error saving chat history:', e);
  }
}

function restoreMediVoiceChatHistory() {
  const messagesBox = document.getElementById('medivoiceMessages');
  if (!messagesBox) return;

  try {
    const history = JSON.parse(sessionStorage.getItem('medivoice_history') || '[]');
    if (history.length > 0) {
      messagesBox.innerHTML = '';
      history.forEach(item => {
        const wrapper = document.createElement('div');
        wrapper.className = `medivoice-msg-wrapper ${item.sender}`;

        const msgDiv = document.createElement('div');
        msgDiv.className = `medivoice-msg ${item.sender}`;
        msgDiv.textContent = item.text;
        wrapper.appendChild(msgDiv);

        if (item.sender === 'assistant') {
          const replayBtn = document.createElement('button');
          replayBtn.type = 'button';
          replayBtn.className = 'medivoice-replay-btn';
          replayBtn.innerHTML = `
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
              <path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>
            </svg>
            <span>Replay</span>
          `;
          replayBtn.onclick = () => replayMessage(item.text, item.lang || currentLang);
          wrapper.appendChild(replayBtn);
        }
        messagesBox.appendChild(wrapper);
      });
      messagesBox.scrollTop = messagesBox.scrollHeight;
      return;
    }
  } catch (e) {
    console.warn('Error restoring chat history:', e);
  }

  // If no history, show localized initial greeting
  renderDefaultGreeting();
}

function renderDefaultGreeting() {
  const messagesBox = document.getElementById('medivoiceMessages');
  if (!messagesBox) return;

  const greetings = {
    'en-IN': "👋 Hello! I am MediVoice, your multilingual medication assistant. You can speak to me or type your questions in English, Hindi, Telugu, or Tamil.",
    'hi-IN': "👋 नमस्ते! मैं मेडीवॉइस (MediVoice) हूँ, आपका बहुभाषी दवा सहायक। आप मुझसे हिन्दी, अंग्रेज़ी, तेलुगु या तमिल में बोलकर या लिखकर पूछ सकते हैं।",
    'te-IN': "👋 నమస్కారం! నేను మెడివాయిస్ (MediVoice), మీ బహుభాషా ఔషధ సహాయకుడిని. మీరు నాతో తెలుగు, ఇంగ్లీష్, హిందీ లేదా తమిళంలో మాట్లాడవచ్చు లేదా టైప్ చేయవచ్చు.",
    'ta-IN': "👋 வணக்கம்! நான் மெடிவாய்ஸ் (MediVoice), உங்கள் பன்மொழி மருந்து உதவியாளர். நீங்கள் என்னுடன் தமிழ், ஆங்கிலம், இந்தி அல்லது தெலுங்கில் பேசலாம் அல்லது தட்டச்சு செய்யலாம்."
  };

  messagesBox.innerHTML = `
    <div class="medivoice-msg-wrapper assistant">
      <div class="medivoice-msg assistant">${greetings[currentLang] || greetings['en-IN']}</div>
    </div>
  `;
}

/**
 * Clear MediVoice conversation history
 */
function clearMediVoiceConversation() {
  sessionStorage.removeItem('medivoice_history');
  stopSpeaking();
  renderDefaultGreeting();
  updateMediVoiceStatus('idle', 'Online • Ready');
}

/**
 * Update Status indicator dot and text
 */
function updateMediVoiceStatus(state, text) {
  const dot = document.getElementById('medivoiceStatusDot');
  const sub = document.getElementById('medivoiceStatusText');

  if (dot) {
    dot.className = `medivoice-status-dot ${state}`;
  }
  if (sub) {
    sub.textContent = text;
  }
}

