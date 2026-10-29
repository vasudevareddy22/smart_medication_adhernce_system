# SMART MEDICATION ADHERENCE SYSTEM WITH MEDIVOICE™
> **Software-Only Healthcare Web Platform for Patient Prescription Scheduling, In-App Reminders, Caregiver Compliance Alerts, and Conversational Voice AI**

---

## 1. Project Overview

The **Smart Medication Adherence System** is a software-only medical adherence management platform designed to solve the critical problem of patient non-compliance with prescribed medication regimens.

Patients often forget dosages, misplace schedules, or take medications at improper intervals. This platform empowers patients with an intuitive dashboard, schedule tracking, in-app reminder prompts, one-click dose confirmations (**TAKEN** or **MISSED**), and a voice assistant named **MediVoice**. Simultaneously, caregivers receive real-time notifications and missed-dose alerts alongside multi-day adherence analytics and dedicated caregiver voice intelligence.

*Note: This is an academic software prototype. It does not use or require physical hardware, IoT sensors, microcontrollers (Arduino/ESP32), or smart pillboxes.*

---

## 2. Key Features

- **Modern SaaS Authentication**:
  - Split-card authentication interface with rich teal/turquoise (`#0B9F9C`) promotional left panel and dark navy right form panel.
  - Interactive password visibility toggle, client-side input validations, and keyboard accessibility.
  - **1-Click Demo Login Buttons** (`👤 Patient` and `🩺 Caregiver`) for rapid 5-minute academic presentations.
- **MediVoice Conversational Voice AI**:
  - Voice-driven dialogue using browser Web Speech API (`SpeechRecognition` / `webkitSpeechRecognition`) and text-to-speech (`speechSynthesis`).
  - Strict database grounding: reads actual prescription records and calculates real adherence percentages.
  - Supports patient queries:
    - *"What medicines do I need to take today?"*
    - *"Have I missed any doses this week?"*
    - *"What is my adherence percentage?"*
    - *"Show my medication history"*
    - *"I took my medicine"* (guides and confirms dose safely).
  - Supports caregiver queries:
    - *"Which patients missed a dose today?"*
    - *"Show this patient's adherence for the last seven days"*
    - *"Which medicines have pending scheduled doses?"*
    - *"Summarize this patient's recent missed doses"*
  - **Medical Safety Guardrails**: Refuses advice on stopping medications or changing dosages; directs emergency queries immediately to emergency services.
  - Typed chat fallback with instant send for browsers without microphone access.
- **Medication Management (CRUD)**:
  - Add, edit, and delete medications with dose, frequency, scheduled time, date ranges, and optional doctor instructions.
  - Cascade deletion protection for prescription adherence audit trails.
- **Dynamic "Today's Medications" Schedule**:
  - Automatically filters prescriptions active today and sorts by scheduled time.
  - Real-time status badges: `PENDING`, `TAKEN`, `MISSED`.
- **In-App Medication Reminder & Dose Confirmation**:
  - In-app reminder modal displaying medication name, dosage, scheduled time, and instructions.
  - Instant **"Test Reminder"** feature designed specifically for live college demonstrations (no waiting for clock times).
  - One-click confirmation:
    - **[ ✓ TAKEN ]**: Sets status to `TAKEN` and logs `confirmed_at` timestamp.
    - **[ ✕ MISSED ]**: Sets status to `MISSED`, logs `confirmed_at` timestamp, and raises caregiver alert.
  - Duplicate confirmation prevention.
- **Caregiver Dashboard & Patient Authorization Isolation**:
  - Dedicated caregiver interface restricted strictly to authorized patients via `caregiver_patients` table (returns 403 on unauthorized access).
  - Multi-patient selector and date range filters (All, Today, 7 Days, 30 Days).
  - High-visibility **Missed Medication Alerts** with patient, dosage, scheduled time, and alert timestamp.
- **Account & Voice Settings (`/settings`)**:
  - Profile name management.
  - Password change with old password verification and secure hashing.
  - MediVoice audio preferences (mute speech output toggle, speech rate speed slider).
- **Visual Analytics (Chart.js)**:
  - 7-day adherence rate percentage trend bar chart.
  - Taken vs. Missed vs. Pending distribution doughnut chart.
  - Driven 100% by live SQLite database queries.

---

## 3. Technology Stack

- **Backend**: Python Flask 3.1.x, Werkzeug
- **Database**: SQLite 3 (`database.db`) with automatic table creation and demo seeding
- **Voice Intelligence**: Browser Web Speech API (`SpeechRecognition`, `speechSynthesis`) + Flask REST Service (`medivoice.py`)
- **Frontend**: HTML5, CSS3 (Modern SaaS design system, Inter typography), Vanilla JavaScript
- **Icons**: Lucide SVG Vector Icons (embedded, zero external network dependency)
- **Data Visualizations**: Chart.js 4.x
- **Testing**: Python `unittest` framework

---

## 4. Database Architecture

The SQLite database (`database.db`) consists of 5 normalized tables:

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
| `instructions` | TEXT DEFAULT '' | Optional doctor instructions/notes |

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
| `type` | TEXT NOT NULL | `MEDICATION_REMINDER`, `MISSED_DOSE`, `SYSTEM` |
| `is_read` | INTEGER DEFAULT 0 | Read flag (0 for unread, 1 for read) |
| `created_at` | TEXT NOT NULL | Creation timestamp |

### `caregiver_patients`
| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | Unique authorization record ID |
| `caregiver_id` | INTEGER NOT NULL | Foreign key referencing `users(id)` |
| `patient_id` | INTEGER NOT NULL | Foreign key referencing `users(id)` |
| `assigned_at` | TEXT NOT NULL | Assignment timestamp |

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

### Test Case Execution Matrix (TC01 - TC19):
| Test ID | Test Description | Input | Expected Result | Actual Result | Status |
|---|---|---|---|---|---|
| **TC01** | User Login | Demo credentials for patient & caregiver | Valid session established, correct role redirection | Redirected to respective dashboards | **PASS** |
| **TC02** | Add Medication | Medicine name, dosage, schedule, dates, notes | Record saved to `medications` & today's `adherence` | Persisted to SQLite, rendered in table | **PASS** |
| **TC03** | Edit Medication | Updated dosage, schedule, and notes | Updated values persisted in SQLite | Database record and UI updated | **PASS** |
| **TC04** | Delete Medication | Medication ID | Cascade deletion of medication and adherence entries | Deleted cleanly from SQLite | **PASS** |
| **TC05** | Trigger Reminder | Medication ID via Test Reminder | JSON payload returned with medication details | Modal payload retrieved instantly | **PASS** |
| **TC06** | Confirm TAKEN | Status = `TAKEN` | Status updated in DB, `confirmed_at` timestamp saved | `status` = TAKEN, adherence % increases | **PASS** |
| **TC07** | Confirm MISSED | Status = `MISSED` | Status updated to MISSED, alert notification created | `status` = MISSED, alert created | **PASS** |
| **TC08** | Caregiver Alert | Caregiver views dashboard | Missed dose alert rendered in alerts section | Alert displayed with patient & medicine info | **PASS** |
| **TC09** | Adherence Calculation | Total doses vs. taken doses | Correct mathematical percentage calculated | Computed accurately via SQLite aggregations | **PASS** |
| **TC10** | History Display | Filter queries (today, week, month) | Filtered adherence history returned | Table displays audit trail correctly | **PASS** |
| **TC11** | Analytics Charts | `/api/analytics` endpoint | Chart.js 7-day labels & distribution dataset | Returns valid JSON structure for charts | **PASS** |
| **TC12** | User Logout | Logout request | Session cleared, redirected to login page | Session cleared, unauthorized access blocked | **PASS** |
| **TC13** | Caregiver Authorization | Request unauthorized patient record | HTTP 403 Forbidden returned | Access Denied, patient isolation preserved | **PASS** |
| **TC14** | MediVoice Today's Meds | Voice/typed query for today's medicines | Grounded database reply with medicine names & times | Accurate spoken & written list returned | **PASS** |
| **TC15** | MediVoice Adherence % | "What is my adherence percentage?" | Accurately calculates compliance from SQLite | Exact rate and taken/scheduled counts returned | **PASS** |
| **TC16** | Medical Safety Guardrails | Emergency or dosage-change questions | Strict medical disclaimer and emergency directions | Refuses unsafe advice, gives emergency helpline | **PASS** |
| **TC17** | Caregiver MediVoice | "Which patients missed a dose today?" | Summarizes authorized patients' missed events | Scoped to authorized patients accurately | **PASS** |
| **TC18** | Settings & Password | Profile update and password change | Name updated in session, password rehashed | Profile and password successfully updated | **PASS** |
| **TC19** | Duplicate Dose Prevention | Repeat confirmation on same dose | Rejects duplicate log, returns already confirmed note | Prevents double-counting in adherence metrics | **PASS** |

---

## 8. 5-Minute Live Demonstration Guide

Follow these exact steps for your college project review:

1. **Step 1: Patient Login**
   - Open `http://127.0.0.1:5000`.
   - Show the modern teal split-card login page.
   - Click the **👤 Patient** 1-Click demo button and sign in.

2. **Step 2: MediVoice AI Voice Assistant**
   - Click the floating **MediVoice AI** button in the bottom right corner.
   - Click the microphone button and ask: *"What medicines do I need to take today?"* (or click the quick prompt chip).
   - MediVoice speaks aloud and displays the exact prescription list from SQLite.
   - Ask: *"What is my adherence percentage?"* to hear your live compliance score.

3. **Step 3: Dose Reminder & Confirmation**
   - Click **🔔 Test Reminder** next to a medicine in the table.
   - The reminder modal appears with dose details and doctor instructions.
   - Click **[ ✓ TAKEN ]**. The badge turns green and today's adherence percentage increases.
   - Test another medicine with **[ ✕ MISSED ]** to trigger an alert.

4. **Step 4: Caregiver Monitoring & Voice Intelligence**
   - Click Logout, then click the **🩺 Caregiver** 1-Click demo button and sign in.
   - Show the **Missed Medication Alerts** section displaying the alert logged in Step 3.
   - Open MediVoice on the caregiver dashboard and ask: *"Which patients missed a dose today?"*
   - Show that MediVoice reads only authorized patient alerts.

5. **Step 5: Settings & Adherence Analytics**
   - Visit **Settings** (`/settings`) to show profile and voice preferences (mute toggle, speech rate).
   - Visit **Adherence History** (`/history`) and show the 7-day adherence trend chart and doughnut distribution.
