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
