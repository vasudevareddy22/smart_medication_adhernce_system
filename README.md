# SMART MEDICATION ADHERENCE SYSTEM
> **Software-Only Prototype for Patient Prescription Scheduling, In-App Reminders, Compliance Tracking & Caregiver Alerts**

---

## 1. Project Overview

The **Smart Medication Adherence System** is a software-only medical adherence management platform designed to solve the critical problem of patient non-compliance with prescribed medication regimens. 

Patients often forget dosages, misplace schedules, or take medications at improper intervals. This prototype empowers patients with an intuitive dashboard, instant schedule tracking, in-app reminder prompts, and one-click dose confirmations (**TAKEN** or **MISSED**). Simultaneously, caregivers receive real-time notifications and missed-dose alerts alongside multi-day adherence analytics.

*Note: This is an academic software prototype. It does not use or require physical hardware, IoT sensors, microcontrollers (Arduino/ESP32), or smart pillboxes.*

---

## 2. Key Features

- **Modern SaaS Authentication**:
  - Split-card authentication interface with rich teal/turquoise (`#0B9F9C`) promotional left panel and dark navy right form panel.
  - Interactive password visibility toggle, client-side input validations, and keyboard accessibility.
  - **1-Click Demo Login Buttons** for rapid 5-minute academic presentations.
- **Medication Management (CRUD)**:
  - Add, edit, and delete medications with dose, frequency, scheduled time, and date range validations.
  - Cascade deletion protection for prescription adherence audit trails.
- **Dynamic "Today's Medications" Schedule**:
  - Automatically filters prescriptions active today and sorts by scheduled time.
  - Real-time status badges: `PENDING`, `TAKEN`, `MISSED`.
- **In-App Medication Reminder & Dose Confirmation**:
  - In-app reminder modal displaying medication name, dosage, and scheduled time.
  - Instant **"Test Reminder"** feature designed specifically for live college demonstrations (no waiting for actual clock times).
  - One-click confirmation:
    - **[ ✓ TAKEN ]**: Sets status to `TAKEN` and logs `confirmed_at` timestamp.
    - **[ ✕ MISSED ]**: Sets status to `MISSED`, logs `confirmed_at` timestamp, and raises caregiver alert.
- **Caregiver Dashboard & Missed Dose Alerts**:
  - Dedicated caregiver interface to monitor assigned patients.
  - High-visibility **Missed Medication Alerts** with patient, dosage, scheduled time, and alert timestamp.
- **Adherence Tracking & History**:
  - Multi-day audit log with filters: *Today*, *This Week*, *This Month*, and *All Time*.
  - Strict adherence calculation formula:
    $$\text{Adherence Percentage} = \frac{\text{Taken Doses}}{\text{Total Scheduled Doses}} \times 100$$
- **Visual Analytics (Chart.js)**:
  - 7-day adherence rate percentage trend bar chart.
  - Taken vs. Missed vs. Pending distribution doughnut chart.
  - Driven by live SQLite database queries (no hardcoded fake values).

---

## 3. Technology Stack

- **Backend**: Python Flask 3.1.x
- **Database**: SQLite 3 (`database.db`) with automatic table creation and demo seeding
- **Frontend**: HTML5, CSS3 (Modern SaaS design system, Inter typography), Vanilla JavaScript
- **Icons**: Lucide SVG Vector Icons (embedded, zero external network dependency)
- **Data Visualizations**: Chart.js 4.x
- **Testing**: Python `unittest` framework

---

## 4. Database Architecture

The SQLite database (`database.db`) consists of 4 normalized tables:

### `users`
| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | Unique user identifier |
| `name` | TEXT NOT NULL | Full name of patient or caregiver |
| `email` | TEXT UNIQUE NOT NULL | Account login email |
| `password` | TEXT NOT NULL | Secure salted password hash |
| `role` | TEXT NOT NULL | Role: `patient` or `caregiver` |

### `medications`
| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | Unique prescription identifier |
| `patient_id` | INTEGER NOT NULL | Foreign key referencing `users(id)` |
| `medicine_name` | TEXT NOT NULL | Name of the medicine (e.g., Paracetamol) |
| `dosage` | TEXT NOT NULL | Dosage (e.g., 500 mg, 1 Tablet) |
| `frequency` | TEXT NOT NULL | Frequency (e.g., Once Daily, Twice Daily) |
| `scheduled_time`| TEXT NOT NULL | Scheduled reminder time (e.g., 08:00 AM) |
| `start_date` | TEXT NOT NULL | Start date of prescription (YYYY-MM-DD) |
| `end_date` | TEXT NOT NULL | End date of prescription (YYYY-MM-DD) |

### `adherence`
| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | Unique adherence event identifier |
| `medication_id` | INTEGER NOT NULL | Foreign key referencing `medications(id)` |
| `scheduled_date`| TEXT NOT NULL | Date of scheduled dose (YYYY-MM-DD) |
| `scheduled_time`| TEXT NOT NULL | Scheduled time for the dose |
| `status` | TEXT NOT NULL | Status: `PENDING`, `TAKEN`, or `MISSED` |
| `confirmed_at` | TEXT | Timestamp when user confirmed dose |

### `notifications`
| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | Unique notification identifier |
| `patient_id` | INTEGER NOT NULL | Foreign key referencing `users(id)` |
| `medication_id` | INTEGER | Related medication ID (optional) |
| `message` | TEXT NOT NULL | Notification or alert description |
| `type` | TEXT NOT NULL | `MEDICATION_REMINDER` or `MISSED_DOSE` |
| `is_read` | INTEGER DEFAULT 0 | Read flag (0 for unread, 1 for read) |
| `created_at` | TEXT NOT NULL | Creation timestamp |

---

## 5. Demo Credentials

The database is pre-seeded with two demo accounts:

| Role | Email | Password |
|---|---|---|
| **Patient** | `patient@test.com` | `patient123` |
| **Caregiver** | `caregiver@test.com` | `caregiver123` |

*(You can also click the quick **👤 Patient** or **🩺 Caregiver** 1-Click demo pills on the login screen.)*

---

## 6. How to Run Locally

### Prerequisites
- Python 3.10+ installed
- Web browser (Chrome, Edge, Firefox, Safari)

### Step 1: Install Requirements
```bash
pip install -r requirements.txt
```

### Step 2: Start Application
Run from the workspace directory:
```bash
python app.py
```
Or run from inside `smart-medication-system/`:
```bash
cd smart-medication-system
python app.py
```

### Step 3: Open in Browser
Visit:
```
http://127.0.0.1:5000
```

---

## 7. Verification & Automated Test Results

Run the full automated test suite anytime with:
```bash
python test_system.py
```

### Test Case Execution Matrix:
| Test ID | Test Description | Input | Expected Result | Actual Result | Status |
|---|---|---|---|---|---|
| **TC01** | User Login | Demo credentials for patient & caregiver | Valid session established, correct role redirection | Redirected to respective dashboards | **PASS** |
| **TC02** | Add Medication | New medicine name, dosage, schedule, dates | Record saved to `medications` & today's `adherence` | Persisted to SQLite, rendered in table | **PASS** |
| **TC03** | Edit Medication | Updated dosage & schedule | Updated values persisted in SQLite | Database record and UI updated | **PASS** |
| **TC04** | Delete Medication | Medication ID | Cascade deletion of medication and adherence entries | Deleted cleanly from SQLite | **PASS** |
| **TC05** | Trigger Reminder | Medication ID via Test Reminder | JSON payload returned with medication details | Modal payload retrieved instantly | **PASS** |
| **TC06** | Confirm TAKEN | Status = `TAKEN` | Status updated in DB, `confirmed_at` timestamp saved | `status` = TAKEN, adherence % increases | **PASS** |
| **TC07** | Confirm MISSED | Status = `MISSED` | Status updated to MISSED, alert notification created | `status` = MISSED, alert created | **PASS** |
| **TC08** | Caregiver Alert | Caregiver views dashboard | Missed dose alert rendered in alerts section | Alert displayed with patient & medicine info | **PASS** |
| **TC09** | Adherence Calculation | Total doses vs. taken doses | Correct mathematical percentage calculated | Computed accurately via SQLite aggregations | **PASS** |
| **TC10** | History Display | Filter queries (today, week, month) | Filtered adherence history returned | Table displays audit trail correctly | **PASS** |
| **TC11** | Analytics Charts | `/api/analytics` endpoint | Chart.js 7-day labels & distribution dataset | Returns valid JSON structure for charts | **PASS** |
| **TC12** | User Logout | Logout request | Session cleared, redirected to login page | Session cleared, unauthorized access blocked | **PASS** |

---

## 8. 5-Minute Live Demonstration Guide

Follow these exact steps for your college project review:

1. **Step 1: Patient Login**
   - Open `http://127.0.0.1:5000`.
   - Show the modern teal split-card login page.
   - Click the **👤 Patient** 1-Click demo button (or enter `patient@test.com` / `patient123`).
   - Click **Sign In**.

2. **Step 2: Patient Dashboard & Add Medication**
   - Highlight **Today's Adherence** percentage card and **Today's Medications** schedule.
   - Click **+ Add Medication**, add a new medication (e.g., *Amoxicillin*, *250 mg*, *Once Daily*, *11:00 AM*), and click **Save Medication**.
   - Show that it immediately appears in Today's Medications list.

3. **Step 3: Test Dose Confirmation (TAKEN)**
   - Click the **🔔 Test Reminder** button next to a medicine.
   - Show the in-app reminder modal (*"Have you taken this medicine?"*).
   - Click **[ ✓ TAKEN ]**.
   - Show that the badge turns green (**✓ TAKEN**) and the adherence percentage increases.

4. **Step 4: Test Missed Dose & Alert Generation (MISSED)**
   - Click **🔔 Test Reminder** on another medicine.
   - Click **[ ✕ MISSED ]**.
   - Show that the badge turns crimson (**✕ MISSED**).

5. **Step 5: Caregiver Dashboard & Alert Verification**
   - Click the Logout button.
   - Click the **🩺 Caregiver** 1-Click demo button (or enter `caregiver@test.com` / `caregiver123`).
   - Show the **Missed Medication Alerts** section displaying the alert logged in Step 4.
   - Point out the patient compliance summary and recent activity log.

6. **Step 6: Adherence Analytics & History**
   - Click **Adherence History** in the navigation bar to demonstrate the audit trail and the *Today / This Week / This Month* filters.
   - Show the interactive 7-day adherence trend chart and the distribution doughnut chart.

---

## 9. Current Limitations

- **Simulated Reminder Triggers**: Due to browser sandbox limitations and lack of background SMS/push daemons, in-browser instant demonstration utilizes the "Test Reminder" trigger.
- **Single Caregiver Association**: Caregiver dashboard currently binds to the primary demo patient.
- **Local SQLite Storage**: Built for local single-host evaluation rather than multi-region distributed clustering.

---

## 10. Future Scope

- Integration with Web Push API for background operating system notifications.
- SMS / WhatsApp reminders via Twilio or WhatsApp Business Cloud API.
- Multi-patient assignment and caregiver permission matrix.
- Prescription OCR scanner using optical character recognition to auto-fill medication schedules from paper prescriptions.
