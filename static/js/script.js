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
   MEDIVOICE AI VOICE ASSISTANT CONTROLLER
   ========================================================================== */

let recognition = null;
let isListening = false;
let isSpeaking = false;

document.addEventListener('DOMContentLoaded', () => {
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
 * Initialize Web Speech API SpeechRecognition
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
  recognition.lang = 'en-US';

  recognition.onstart = () => {
    isListening = true;
    updateMediVoiceStatus('listening', 'Listening to you...');
    const micBtn = document.getElementById('medivoiceMicBtn');
    if (micBtn) micBtn.classList.add('listening');
    const preview = document.getElementById('medivoiceLivePreview');
    if (preview) {
      preview.textContent = 'Listening... Speak clearly';
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
    console.error('Speech recognition error:', event.error);
    isListening = false;
    const micBtn = document.getElementById('medivoiceMicBtn');
    if (micBtn) micBtn.classList.remove('listening');

    let msg = 'Voice recognition error.';
    if (event.error === 'not-allowed') {
      msg = 'Microphone permission denied. You can type your question in the text box below.';
    } else if (event.error === 'no-speech') {
      msg = 'No speech detected. Please click the mic and try again, or type below.';
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
        target_patient_id: targetPatientId
      })
    });

    const data = await response.json();
    if (data.success && data.reply) {
      appendMediVoiceMessage('assistant', data.reply);
      speakText(data.reply);

      // Handle safe actions
      if (data.action) {
        if (data.action.type === 'navigate' && data.action.url) {
          setTimeout(() => { window.location.href = data.action.url; }, 2000);
        } else if (data.action.type === 'refresh_dashboard') {
          setTimeout(() => { window.location.reload(); }, 2200);
        }
      }
    } else {
      appendMediVoiceMessage('assistant', data.reply || 'Sorry, I encountered an issue processing your request.');
      updateMediVoiceStatus('idle', 'Online • Ready');
    }
  } catch (err) {
    console.error('MediVoice backend error:', err);
    appendMediVoiceMessage('assistant', '⚠️ Unable to reach MediVoice service. Please check your connection.');
    updateMediVoiceStatus('idle', 'Online • Ready');
  }
}

/**
 * Speak assistant text aloud using SpeechSynthesis API
 */
function speakText(text) {
  const isMuted = localStorage.getItem('medivoice_mute') === 'true';
  if (isMuted || !('speechSynthesis' in window)) {
    updateMediVoiceStatus('idle', 'Online • Ready');
    return;
  }

  window.speechSynthesis.cancel(); // Stop any pending speech

  const cleanText = text.replace(/[*_#`~🚨⚠️✓✕]/g, '');
  const utterance = new SpeechSynthesisUtterance(cleanText);
  utterance.lang = 'en-US';
  utterance.rate = parseFloat(localStorage.getItem('medivoice_rate') || '1.0');

  utterance.onstart = () => {
    isSpeaking = true;
    updateMediVoiceStatus('speaking', 'Speaking...');
    const stopBtn = document.getElementById('medivoiceStopBtn');
    if (stopBtn) stopBtn.classList.add('active');
  };

  utterance.onend = () => {
    isSpeaking = false;
    updateMediVoiceStatus('idle', 'Online • Ready');
    const stopBtn = document.getElementById('medivoiceStopBtn');
    if (stopBtn) stopBtn.classList.remove('active');
  };

  utterance.onerror = () => {
    isSpeaking = false;
    updateMediVoiceStatus('idle', 'Online • Ready');
    const stopBtn = document.getElementById('medivoiceStopBtn');
    if (stopBtn) stopBtn.classList.remove('active');
  };

  window.speechSynthesis.speak(utterance);
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
 * Append message bubble to chat window
 */
function appendMediVoiceMessage(sender, text) {
  const messagesBox = document.getElementById('medivoiceMessages');
  if (!messagesBox) return;

  const msgDiv = document.createElement('div');
  msgDiv.className = `medivoice-msg ${sender}`;
  msgDiv.textContent = text;
  messagesBox.appendChild(msgDiv);
  messagesBox.scrollTop = messagesBox.scrollHeight;
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
