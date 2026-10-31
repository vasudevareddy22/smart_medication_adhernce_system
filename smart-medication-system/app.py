import os
import re
import io
import secrets
import sqlite3
from datetime import datetime, date, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file, abort
from werkzeug.security import generate_password_hash, check_password_hash
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
import requests
from medivoice import process_medivoice_query

# Initialize Flask application
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "smart-med-super-secret-key-2026")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, "database.db")


def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def validate_indian_phone(phone_str):
    """
    Validates Indian phone number format:
    Accepts 10 digits starting with 6-9, optionally prefixed by +91 or 91, with optional spaces or dashes.
    Returns tuple: (is_valid: bool, normalized_10_digit: str, formatted_e164: str)
    """
    if not phone_str:
        return False, "", ""
    cleaned = re.sub(r'[\s\-\(\)]', '', str(phone_str).strip())
    match = re.match(r'^(?:\+?91)?([6-9]\d{9})$', cleaned)
    if match:
        ten_digits = match.group(1)
        return True, ten_digits, f"+91{ten_digits}"
    return False, "", ""


def log_audit_event(user_id, action, details=""):
    """Records audit trail entry."""
    try:
        conn = get_db()
        cur = conn.cursor()
        ip = request.remote_addr if request else "127.0.0.1"
        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("""
            INSERT INTO audit_logs (user_id, action, details, ip_address, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, action, details, ip, now_ts))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Audit Log Warning]: {e}")


def send_notification(patient_id, message, notif_type="MEDICATION_REMINDER", medication_id=None, caregiver_id=None, channel="IN_APP"):
    """
    Dispatches notifications to patient and/or caregiver.
    Supports In-App, SMS, and WhatsApp with Twilio and MSG91 environment configuration.
    If credentials not provided, logs as SIMULATED and records status accurately without pretending live gateway delivery.
    """
    conn = get_db()
    cursor = conn.cursor()
    now_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Fetch recipient contact info
    cursor.execute("SELECT name, phone, notification_consent FROM users WHERE id = ?", (patient_id,))
    patient = cursor.fetchone()
    patient_phone = patient["phone"] if patient and patient["phone"] else "9989372530"

    cg_phone = None
    if caregiver_id:
        cursor.execute("SELECT name, phone FROM users WHERE id = ?", (caregiver_id,))
        cg = cursor.fetchone()
        if cg and cg["phone"]:
            cg_phone = cg["phone"]

    target_phone = cg_phone if caregiver_id and not patient_id else patient_phone

    status = "DELIVERED"
    error_message = None
    retry_count = 0

    # Mobile SMS / WhatsApp Provider Integration
    if channel in ["SMS", "WHATSAPP"]:
        twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID")
        twilio_token = os.environ.get("TWILIO_AUTH_TOKEN")
        twilio_phone = os.environ.get("TWILIO_PHONE_NUMBER")
        twilio_wa = os.environ.get("TWILIO_WHATSAPP_NUMBER")
        msg91_auth = os.environ.get("MSG91_AUTH_KEY")

        if twilio_sid and twilio_token and (twilio_phone or twilio_wa):
            try:
                from_num = twilio_wa if channel == "WHATSAPP" else twilio_phone
                to_num = f"whatsapp:{target_phone}" if channel == "WHATSAPP" else target_phone
                res = requests.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{twilio_sid}/Messages.json",
                    auth=(twilio_sid, twilio_token),
                    data={"From": from_num, "To": to_num, "Body": message},
                    timeout=5
                )
                if res.status_code in [200, 201]:
                    status = "DELIVERED"
                else:
                    status = "FAILED"
                    error_message = f"Twilio HTTP {res.status_code}: {res.text[:120]}"
                    retry_count = 1
            except Exception as e:
                status = "FAILED"
                error_message = f"Twilio connection error: {str(e)}"
                retry_count = 1
        elif msg91_auth:
            try:
                res = requests.post(
                    "https://control.msg91.com/api/v5/flow/",
                    headers={"authkey": msg91_auth, "content-type": "application/json"},
                    json={"template_id": os.environ.get("MSG91_TEMPLATE_ID", ""), "recipients": [{"mobiles": target_phone, "message": message}]},
                    timeout=5
                )
                status = "DELIVERED" if res.status_code == 200 else "FAILED"
                if status == "FAILED":
                    error_message = f"MSG91 error {res.status_code}"
            except Exception as e:
                status = "FAILED"
                error_message = str(e)
        else:
            # Phase 2 requirement: Do not pretend SMS/WhatsApp works without credentials
            status = "SIMULATED"
            error_message = "SMS/WhatsApp provider credentials not configured in environment. In-app notification logged."

    # Insert into notifications table
    cursor.execute("""
        INSERT INTO notifications (
            patient_id, caregiver_id, medication_id, recipient_phone,
            message, type, channel, status, error_message, retry_count, is_read, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
    """, (
        patient_id, caregiver_id, medication_id, target_phone,
        message, notif_type, channel, status, error_message, retry_count, now_time
    ))
    notif_id = cursor.lastrowid
    conn.commit()
    conn.close()

    log_audit_event(patient_id, f"NOTIFICATION_{status}", f"Type: {notif_type}, Channel: {channel}, Phone: {target_phone}")
    return notif_id, status


def init_db():
    """Initializes and safely migrates the database tables without dropping existing data."""
    conn = get_db()
    cursor = conn.cursor()

    # 1. users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """)

    # Safe column migrations for users
    cursor.execute("PRAGMA table_info(users)")
    u_cols = [c["name"] for c in cursor.fetchall()]
    if "phone" not in u_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN phone TEXT DEFAULT '9989372530'")
    if "phone_verified" not in u_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN phone_verified INTEGER DEFAULT 0")
    if "notification_consent" not in u_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN notification_consent INTEGER DEFAULT 1")
    if "notification_preferences" not in u_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN notification_preferences TEXT DEFAULT 'reminders,missed,alerts'")
    if "created_at" not in u_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN created_at TEXT DEFAULT ''")

    # 2. caregiver_profiles table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS caregiver_profiles (
            caregiver_id INTEGER PRIMARY KEY,
            relationship TEXT DEFAULT 'Family',
            preferred_channel TEXT DEFAULT 'SMS',
            emergency_contact TEXT DEFAULT '',
            notify_on_missed INTEGER DEFAULT 1,
            notify_on_taken INTEGER DEFAULT 0,
            notify_on_adherence INTEGER DEFAULT 1,
            updated_at TEXT,
            FOREIGN KEY (caregiver_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # 3. medications table (with optional instructions)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS medications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            medicine_name TEXT NOT NULL,
            dosage TEXT NOT NULL,
            frequency TEXT NOT NULL,
            scheduled_time TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            instructions TEXT DEFAULT '',
            FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("PRAGMA table_info(medications)")
    m_cols = [c["name"] for c in cursor.fetchall()]
    if "instructions" not in m_cols:
        cursor.execute("ALTER TABLE medications ADD COLUMN instructions TEXT DEFAULT ''")

    # 4. adherence table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS adherence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            medication_id INTEGER NOT NULL,
            scheduled_date TEXT NOT NULL,
            scheduled_time TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            confirmed_at TEXT,
            FOREIGN KEY (medication_id) REFERENCES medications(id) ON DELETE CASCADE
        )
    """)

    # 5. notifications table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            medication_id INTEGER,
            message TEXT NOT NULL,
            type TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (medication_id) REFERENCES medications(id) ON DELETE SET NULL
        )
    """)

    # Safe column migrations for notifications
    cursor.execute("PRAGMA table_info(notifications)")
    n_cols = [c["name"] for c in cursor.fetchall()]
    if "caregiver_id" not in n_cols:
        cursor.execute("ALTER TABLE notifications ADD COLUMN caregiver_id INTEGER")
    if "recipient_phone" not in n_cols:
        cursor.execute("ALTER TABLE notifications ADD COLUMN recipient_phone TEXT")
    if "channel" not in n_cols:
        cursor.execute("ALTER TABLE notifications ADD COLUMN channel TEXT DEFAULT 'IN_APP'")
    if "status" not in n_cols:
        cursor.execute("ALTER TABLE notifications ADD COLUMN status TEXT DEFAULT 'SENT'")
    if "error_message" not in n_cols:
        cursor.execute("ALTER TABLE notifications ADD COLUMN error_message TEXT")
    if "retry_count" not in n_cols:
        cursor.execute("ALTER TABLE notifications ADD COLUMN retry_count INTEGER DEFAULT 0")

    # 6. caregiver_patients table (Caregiver Authorization Mapping)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS caregiver_patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            caregiver_id INTEGER NOT NULL,
            patient_id INTEGER NOT NULL,
            assigned_at TEXT NOT NULL,
            FOREIGN KEY (caregiver_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(caregiver_id, patient_id)
        )
    """)

    # 7. audit_logs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            details TEXT,
            ip_address TEXT,
            timestamp TEXT NOT NULL
        )
    """)
    conn.commit()

    # Seed demo users if empty
    cursor.execute("SELECT COUNT(*) as count FROM users")
    user_count = cursor.fetchone()["count"]

    if user_count == 0:
        # Patient: patient@test.com / patient123
        # Caregiver: caregiver@test.com / caregiver123
        cursor.execute("""
            INSERT INTO users (name, email, password, role)
            VALUES (?, ?, ?, ?)
        """, (
            "Demo Patient",
            "patient@test.com",
            generate_password_hash("patient123"),
            "patient"
        ))
        patient_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO users (name, email, password, role)
            VALUES (?, ?, ?, ?)
        """, (
            "Demo Caregiver",
            "caregiver@test.com",
            generate_password_hash("caregiver123"),
            "caregiver"
        ))
        caregiver_id = cursor.lastrowid
        conn.commit()

        # Seed caregiver authorization link
        now_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT OR IGNORE INTO caregiver_patients (caregiver_id, patient_id, assigned_at)
            VALUES (?, ?, ?)
        """, (caregiver_id, patient_id, now_time))

        # Seed initial medications for demonstration
        today = date.today()
        start_d = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        end_d = (today + timedelta(days=21)).strftime("%Y-%m-%d")

        meds = [
            ("Paracetamol", "500 mg", "Twice Daily", "08:00 AM", start_d, end_d, "Take with full glass of water after food"),
            ("Vitamin D", "1 Tablet", "Once Daily", "01:00 PM", start_d, end_d, "Take with lunch"),
            ("Calcium", "500 mg", "Once Daily", "08:00 PM", start_d, end_d, "Take after evening meal")
        ]

        created_med_ids = []
        for m in meds:
            cursor.execute("""
                INSERT INTO medications (patient_id, medicine_name, dosage, frequency, scheduled_time, start_date, end_date, instructions)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (patient_id, m[0], m[1], m[2], m[3], m[4], m[5], m[6]))
            created_med_ids.append(cursor.lastrowid)
        conn.commit()

        # Seed historical 6-day adherence records for meaningful charts
        for day_offset in range(6, 0, -1):
            past_date = (today - timedelta(days=day_offset)).strftime("%Y-%m-%d")
            cursor.execute("""
                INSERT INTO adherence (medication_id, scheduled_date, scheduled_time, status, confirmed_at)
                VALUES (?, ?, ?, ?, ?)
            """, (created_med_ids[0], past_date, "08:00 AM", "TAKEN", f"{past_date} 08:05:00"))

            cursor.execute("""
                INSERT INTO adherence (medication_id, scheduled_date, scheduled_time, status, confirmed_at)
                VALUES (?, ?, ?, ?, ?)
            """, (created_med_ids[1], past_date, "01:00 PM", "TAKEN", f"{past_date} 01:03:00"))

            past_status = "TAKEN" if day_offset % 2 == 0 else "MISSED"
            conf_time = f"{past_date} 20:12:00" if past_status == "TAKEN" else None
            cursor.execute("""
                INSERT INTO adherence (medication_id, scheduled_date, scheduled_time, status, confirmed_at)
                VALUES (?, ?, ?, ?, ?)
            """, (created_med_ids[2], past_date, "08:00 PM", past_status, conf_time))

        # Seed Today's adherence:
        today_str = today.strftime("%Y-%m-%d")

        cursor.execute("""
            INSERT INTO adherence (medication_id, scheduled_date, scheduled_time, status, confirmed_at)
            VALUES (?, ?, ?, ?, ?)
        """, (created_med_ids[0], today_str, "08:00 AM", "TAKEN", now_time))

        cursor.execute("""
            INSERT INTO adherence (medication_id, scheduled_date, scheduled_time, status, confirmed_at)
            VALUES (?, ?, ?, ?, ?)
        """, (created_med_ids[1], today_str, "01:00 PM", "PENDING", None))

        cursor.execute("""
            INSERT INTO adherence (medication_id, scheduled_date, scheduled_time, status, confirmed_at)
            VALUES (?, ?, ?, ?, ?)
        """, (created_med_ids[2], today_str, "08:00 PM", "PENDING", None))

        cursor.execute("""
            INSERT INTO notifications (patient_id, medication_id, message, type, is_read, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            patient_id,
            created_med_ids[0],
            "Medication Paracetamol (500 mg) was taken on schedule at 08:00 AM.",
            "MEDICATION_REMINDER",
            0,
            now_time
        ))

        cursor.execute("""
            INSERT INTO notifications (patient_id, medication_id, message, type, is_read, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            patient_id,
            created_med_ids[1],
            "Reminder: Vitamin D (1 Tablet) is scheduled for 01:00 PM today.",
            "MEDICATION_REMINDER",
            0,
            now_time
        ))

        conn.commit()
    # Ensure default patient has initial contact number 9989372530
    cursor.execute("""
        UPDATE users 
        SET phone = '9989372530', notification_consent = 1 
        WHERE email = 'patient@test.com' AND (phone IS NULL OR phone = '' OR phone = 'None')
    """)

    # Ensure caregiver authorization link and profile exist
    cursor.execute("SELECT id FROM users WHERE email = 'caregiver@test.com'")
    cg = cursor.fetchone()
    cursor.execute("SELECT id FROM users WHERE email = 'patient@test.com'")
    pt = cursor.fetchone()
    if cg and pt:
        cursor.execute("""
            INSERT OR IGNORE INTO caregiver_patients (caregiver_id, patient_id, assigned_at)
            VALUES (?, ?, ?)
        """, (cg["id"], pt["id"], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

        cursor.execute("""
            INSERT OR IGNORE INTO caregiver_profiles (caregiver_id, relationship, preferred_channel, emergency_contact, updated_at)
            VALUES (?, 'Primary Family Caregiver', 'SMS', '9989372530', ?)
        """, (cg["id"], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    # Phase 4 & 5: Ensure secure administrator user exists in users table
    cursor.execute("SELECT id FROM users WHERE role = 'admin'")
    if not cursor.fetchone():
        admin_email = os.environ.get("ADMIN_EMAIL", "admin@smartmed.com").strip().lower()
        admin_pass = os.environ.get("ADMIN_PASSWORD", "Admin@Secure2026!")
        cursor.execute("""
            INSERT INTO users (name, email, password, role, phone, phone_verified, notification_consent, created_at)
            VALUES (?, ?, ?, 'admin', '9989372530', 1, 1, ?)
        """, ("System Administrator", admin_email, generate_password_hash(admin_pass), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    conn.commit()
    conn.close()


def ensure_today_adherence_records(patient_id):
    """Ensures that all active medications for today have an entry in adherence table for today."""
    conn = get_db()
    cursor = conn.cursor()
    today_str = date.today().strftime("%Y-%m-%d")

    cursor.execute("""
        SELECT * FROM medications
        WHERE patient_id = ?
          AND start_date <= ?
          AND end_date >= ?
    """, (patient_id, today_str, today_str))
    meds = cursor.fetchall()

    for med in meds:
        cursor.execute("""
            SELECT id FROM adherence
            WHERE medication_id = ? AND scheduled_date = ?
        """, (med["id"], today_str))
        existing = cursor.fetchone()
        if not existing:
            cursor.execute("""
                INSERT INTO adherence (medication_id, scheduled_date, scheduled_time, status)
                VALUES (?, ?, ?, 'PENDING')
            """, (med["id"], today_str, med["scheduled_time"]))
    conn.commit()
    conn.close()


def get_patient_today_stats(patient_id):
    """Calculates adherence stats for today."""
    conn = get_db()
    cursor = conn.cursor()
    today_str = date.today().strftime("%Y-%m-%d")

    cursor.execute("""
        SELECT a.status, COUNT(*) as cnt
        FROM adherence a
        JOIN medications m ON a.medication_id = m.id
        WHERE m.patient_id = ? AND a.scheduled_date = ?
        GROUP BY a.status
    """, (patient_id, today_str))
    rows = cursor.fetchall()
    conn.close()

    counts = {"TAKEN": 0, "MISSED": 0, "PENDING": 0}
    for r in rows:
        counts[r["status"]] = r["cnt"]

    total = sum(counts.values())
    taken = counts["TAKEN"]
    percentage = round((taken / total * 100), 1) if total > 0 else 0

    return {
        "percentage": percentage,
        "total": total,
        "taken": counts["TAKEN"],
        "missed": counts["MISSED"],
        "pending": counts["PENDING"]
    }


# ==========================================
# AUTHENTICATION ROUTES
# ==========================================

@app.route("/")
def index():
    if "user_id" in session:
        role = session.get("role")
        if role == "admin":
            return redirect(url_for("admin_dashboard"))
        elif role == "caregiver":
            return redirect(url_for("caregiver_dashboard"))
        return redirect(url_for("patient_dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        if not email or not password:
            flash("Please enter both email address and password.", "error")
            return render_template("login.html", email=email)

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE LOWER(email) = ?", (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["user_email"] = user["email"]
            session["role"] = user["role"]
            log_audit_event(user["id"], "LOGIN_SUCCESS", f"Role: {user['role']}")
            flash(f"Welcome back, {user['name']}!", "success")

            if user["role"] == "admin":
                return redirect(url_for("admin_dashboard"))
            elif user["role"] == "caregiver":
                return redirect(url_for("caregiver_dashboard"))
            return redirect(url_for("patient_dashboard"))
        else:
            log_audit_event(None, "LOGIN_FAILED", f"Attempted Email: {email}")
            flash("Invalid email or password. Please try again.", "error")
            return render_template("login.html", email=email)

    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "patient").strip().lower()
        phone_input = request.form.get("phone", "").strip()

        if not name or not email or not password:
            flash("Name, email, and password are required fields.", "error")
            return render_template("login.html", is_signup=True)

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("login.html", is_signup=True, name=name, email=email, phone=phone_input)

        valid_phone = "9989372530"
        if phone_input:
            is_valid, ten_digit, _ = validate_indian_phone(phone_input)
            if not is_valid:
                flash("Please enter a valid 10-digit Indian phone number (+91 or 10 digits starting with 6-9).", "error")
                return render_template("login.html", is_signup=True, name=name, email=email, phone=phone_input)
            valid_phone = ten_digit

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE LOWER(email) = ?", (email,))
        if cursor.fetchone():
            conn.close()
            flash("An account with this email already exists. Please log in.", "error")
            return render_template("login.html", email=email)

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO users (name, email, password, role, phone, phone_verified, notification_consent, created_at)
            VALUES (?, ?, ?, ?, ?, 1, 1, ?)
        """, (name, email, generate_password_hash(password), role, valid_phone, now_str))
        conn.commit()
        user_id = cursor.lastrowid

        # If caregiver signed up, setup caregiver profile and assign to first patient
        if role == "caregiver":
            cursor.execute("""
                INSERT OR IGNORE INTO caregiver_profiles (caregiver_id, relationship, preferred_channel, emergency_contact, updated_at)
                VALUES (?, 'Primary Caregiver', 'SMS', ?, ?)
            """, (user_id, valid_phone, now_str))

            cursor.execute("SELECT id FROM users WHERE role = 'patient' LIMIT 1")
            first_pt = cursor.fetchone()
            if first_pt:
                cursor.execute("""
                    INSERT OR IGNORE INTO caregiver_patients (caregiver_id, patient_id, assigned_at)
                    VALUES (?, ?, ?)
                """, (user_id, first_pt["id"], now_str))
                conn.commit()

        conn.commit()
        conn.close()

        session["user_id"] = user_id
        session["user_name"] = name
        session["user_email"] = email
        session["role"] = role

        log_audit_event(user_id, "USER_REGISTERED", f"Role: {role}, Phone: {valid_phone}")
        flash("Account created successfully! Welcome to SmartMed.", "success")
        if role == "caregiver":
            return redirect(url_for("caregiver_dashboard"))
        return redirect(url_for("patient_dashboard"))

    return render_template("login.html", is_signup=True)


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been securely logged out.", "info")
    return redirect(url_for("login"))


# ==========================================
# SETTINGS PAGE
# ==========================================

@app.route("/settings", methods=["GET", "POST"])
def settings():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "update_profile":
            name = request.form.get("name", "").strip()
            phone_raw = request.form.get("phone", "").strip()
            if not name:
                flash("Name cannot be empty.", "error")
            else:
                valid_phone = "9989372530"
                if phone_raw:
                    is_valid, ten_digit, _ = validate_indian_phone(phone_raw)
                    if not is_valid:
                        flash("Please enter a valid 10-digit Indian mobile number (+91 or 10 digits starting with 6-9).", "error")
                        return redirect(url_for("settings"))
                    valid_phone = ten_digit
                cursor.execute("UPDATE users SET name = ?, phone = ?, phone_verified = 1 WHERE id = ?", (name, valid_phone, user_id))
                conn.commit()
                session["user_name"] = name
                log_audit_event(user_id, "PROFILE_UPDATED", f"Phone: {valid_phone}")
                flash("Profile name and mobile contact updated successfully!", "success")

        elif action == "change_password":
            old_password = request.form.get("old_password", "").strip()
            new_password = request.form.get("new_password", "").strip()
            confirm_password = request.form.get("confirm_password", "").strip()

            cursor.execute("SELECT password FROM users WHERE id = ?", (user_id,))
            u = cursor.fetchone()

            if not (old_password and new_password and confirm_password):
                flash("All password fields are required.", "error")
            elif not check_password_hash(u["password"], old_password):
                flash("Current password is incorrect.", "error")
            elif len(new_password) < 6:
                flash("New password must be at least 6 characters.", "error")
            elif new_password != confirm_password:
                flash("New passwords do not match.", "error")
            else:
                cursor.execute("UPDATE users SET password = ? WHERE id = ?", (generate_password_hash(new_password), user_id))
                conn.commit()
                flash("Password changed successfully!", "success")

    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()

    return render_template("settings.html", user=user, user_name=session.get("user_name"), role=session.get("role"))


# ==========================================
# PATIENT DASHBOARD & MEDICATION CRUD
# ==========================================

@app.route("/dashboard")
def patient_dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    patient_id = session["user_id"]
    if session.get("role") == "caregiver":
        return redirect(url_for("caregiver_dashboard"))

    # Make sure today's adherence records exist
    ensure_today_adherence_records(patient_id)

    today_str = date.today().strftime("%Y-%m-%d")
    conn = get_db()
    cursor = conn.cursor()

    # Get Today's Medications with their adherence status
    cursor.execute("""
        SELECT 
            m.id as med_id,
            m.medicine_name,
            m.dosage,
            m.frequency,
            m.scheduled_time,
            m.start_date,
            m.end_date,
            m.instructions,
            COALESCE(a.id, 0) as adherence_id,
            COALESCE(a.status, 'PENDING') as status,
            a.confirmed_at
        FROM medications m
        LEFT JOIN adherence a ON m.id = a.medication_id AND a.scheduled_date = ?
        WHERE m.patient_id = ?
          AND m.start_date <= ?
          AND m.end_date >= ?
        ORDER BY 
            CASE 
                WHEN m.scheduled_time LIKE '%AM%' AND m.scheduled_time NOT LIKE '12%' THEN 1
                WHEN m.scheduled_time LIKE '12%PM%' THEN 2
                WHEN m.scheduled_time LIKE '%PM%' THEN 3
                ELSE 4
            END,
            m.scheduled_time ASC
    """, (today_str, patient_id, today_str, today_str))
    todays_medications = cursor.fetchall()

    # Get all active medications for reference/management list
    cursor.execute("""
        SELECT * FROM medications
        WHERE patient_id = ?
        ORDER BY medicine_name ASC
    """, (patient_id,))
    all_medications = cursor.fetchall()

    # Notifications count
    cursor.execute("""
        SELECT COUNT(*) as count FROM notifications
        WHERE patient_id = ? AND is_read = 0
    """, (patient_id,))
    unread_notifs = cursor.fetchone()["count"]

    conn.close()

    stats = get_patient_today_stats(patient_id)

    return render_template(
        "dashboard.html",
        user_name=session.get("user_name"),
        todays_medications=todays_medications,
        all_medications=all_medications,
        stats=stats,
        unread_notifs=unread_notifs,
        today_date=date.today().strftime("%A, %B %d, %Y")
    )


@app.route("/medications/add", methods=["GET", "POST"])
def add_medication():
    if "user_id" not in session:
        return redirect(url_for("login"))

    patient_id = session["user_id"]

    if request.method == "POST":
        medicine_name = request.form.get("medicine_name", "").strip()
        dosage = request.form.get("dosage", "").strip()
        frequency = request.form.get("frequency", "").strip()
        scheduled_time = request.form.get("scheduled_time", "").strip()
        start_date = request.form.get("start_date", "").strip()
        end_date = request.form.get("end_date", "").strip()
        instructions = request.form.get("instructions", "").strip()

        # Validation
        if not (medicine_name and dosage and frequency and scheduled_time and start_date and end_date):
            flash("All required fields must be filled out completely.", "error")
            return render_template("add_medicine.html", form_data=request.form)

        if start_date > end_date:
            flash("End Date cannot be earlier than Start Date.", "error")
            return render_template("add_medicine.html", form_data=request.form)

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO medications (patient_id, medicine_name, dosage, frequency, scheduled_time, start_date, end_date, instructions)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (patient_id, medicine_name, dosage, frequency, scheduled_time, start_date, end_date, instructions))
        new_med_id = cursor.lastrowid

        # If medication is active today, create today's adherence record
        today_str = date.today().strftime("%Y-%m-%d")
        if start_date <= today_str <= end_date:
            cursor.execute("""
                INSERT INTO adherence (medication_id, scheduled_date, scheduled_time, status)
                VALUES (?, ?, ?, 'PENDING')
            """, (new_med_id, today_str, scheduled_time))

        # Add notification
        cursor.execute("""
            INSERT INTO notifications (patient_id, medication_id, message, type, is_read, created_at)
            VALUES (?, ?, ?, 'SYSTEM', 0, ?)
        """, (
            patient_id,
            new_med_id,
            f"Medication '{medicine_name}' ({dosage}) successfully added to your schedule.",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

        conn.commit()
        conn.close()

        flash(f"Medication '{medicine_name}' added successfully!", "success")
        return redirect(url_for("patient_dashboard"))

    # Defaults for form
    today_str = date.today().strftime("%Y-%m-%d")
    default_end = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")
    return render_template("add_medicine.html", default_start=today_str, default_end=default_end)


@app.route("/medications/edit/<int:med_id>", methods=["GET", "POST"])
def edit_medication(med_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    patient_id = session["user_id"]
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM medications WHERE id = ? AND patient_id = ?", (med_id, patient_id))
    medication = cursor.fetchone()

    if not medication:
        conn.close()
        flash("Medication not found or unauthorized.", "error")
        return redirect(url_for("patient_dashboard"))

    if request.method == "POST":
        medicine_name = request.form.get("medicine_name", "").strip()
        dosage = request.form.get("dosage", "").strip()
        frequency = request.form.get("frequency", "").strip()
        scheduled_time = request.form.get("scheduled_time", "").strip()
        start_date = request.form.get("start_date", "").strip()
        end_date = request.form.get("end_date", "").strip()
        instructions = request.form.get("instructions", "").strip()

        if not (medicine_name and dosage and frequency and scheduled_time and start_date and end_date):
            conn.close()
            flash("All required fields must be filled out.", "error")
            return render_template("add_medicine.html", medication=medication, is_edit=True)

        if start_date > end_date:
            conn.close()
            flash("End Date cannot be before Start Date.", "error")
            return render_template("add_medicine.html", medication=medication, is_edit=True)

        cursor.execute("""
            UPDATE medications
            SET medicine_name = ?, dosage = ?, frequency = ?, scheduled_time = ?, start_date = ?, end_date = ?, instructions = ?
            WHERE id = ? AND patient_id = ?
        """, (medicine_name, dosage, frequency, scheduled_time, start_date, end_date, instructions, med_id, patient_id))

        conn.commit()
        conn.close()

        flash(f"Medication '{medicine_name}' updated successfully!", "success")
        return redirect(url_for("patient_dashboard"))

    conn.close()
    return render_template("add_medicine.html", medication=medication, is_edit=True)


@app.route("/medications/delete/<int:med_id>", methods=["POST"])
def delete_medication(med_id):
    if "user_id" not in session:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    patient_id = session["user_id"]
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT medicine_name FROM medications WHERE id = ? AND patient_id = ?", (med_id, patient_id))
    med = cursor.fetchone()
    if not med:
        conn.close()
        flash("Medication not found.", "error")
        return redirect(url_for("patient_dashboard"))

    med_name = med["medicine_name"]
    # Delete related adherence records and notifications
    cursor.execute("DELETE FROM adherence WHERE medication_id = ?", (med_id,))
    cursor.execute("DELETE FROM notifications WHERE medication_id = ?", (med_id,))
    cursor.execute("DELETE FROM medications WHERE id = ? AND patient_id = ?", (med_id, patient_id))
    conn.commit()
    conn.close()

    flash(f"Medication '{med_name}' deleted.", "info")
    return redirect(url_for("patient_dashboard"))


# ==========================================
# REMINDER & DOSE CONFIRMATION ENGINE
# ==========================================

@app.route("/reminder/test/<int:med_id>", methods=["POST"])
def test_reminder(med_id):
    """
    DEMO FEATURE: Immediately triggers a reminder response for the chosen medication
    so the user does not need to wait during their college presentation.
    """
    if "user_id" not in session:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM medications WHERE id = ?", (med_id,))
    med = cursor.fetchone()

    if not med:
        conn.close()
        return jsonify({"success": False, "message": "Medication not found"}), 404

    # Authorization guard: Ensure medication belongs to current patient
    if session.get("role") == "patient" and med["patient_id"] != session["user_id"]:
        conn.close()
        return jsonify({"success": False, "message": "Unauthorized access to medication."}), 403

    # Get or create today's adherence record
    today_str = date.today().strftime("%Y-%m-%d")
    cursor.execute("""
        SELECT * FROM adherence
        WHERE medication_id = ? AND scheduled_date = ?
    """, (med_id, today_str))
    adh = cursor.fetchone()

    if not adh:
        cursor.execute("""
            INSERT INTO adherence (medication_id, scheduled_date, scheduled_time, status)
            VALUES (?, ?, ?, 'PENDING')
        """, (med_id, today_str, med["scheduled_time"]))
        conn.commit()
        adh_id = cursor.lastrowid
        current_status = "PENDING"
    else:
        adh_id = adh["id"]
        current_status = adh["status"]

    conn.close()

    return jsonify({
        "success": True,
        "medication": {
            "id": med["id"],
            "adherence_id": adh_id,
            "medicine_name": med["medicine_name"],
            "dosage": med["dosage"],
            "scheduled_time": med["scheduled_time"],
            "instructions": med["instructions"] or "",
            "current_status": current_status
        }
    })


@app.route("/adherence/confirm", methods=["POST"])
def confirm_adherence():
    """
    Patient clicks TAKEN or MISSED:
    Updates adherence table status and timestamp.
    Prevents duplicate confirmations when dose is already recorded.
    If MISSED, generates a MISSED_DOSE alert for the caregiver.
    """
    if "user_id" not in session:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    patient_id = session["user_id"]
    data = request.get_json() or request.form

    medication_id = data.get("medication_id")
    adherence_id = data.get("adherence_id")
    new_status = data.get("status", "").upper()

    if new_status not in ["TAKEN", "MISSED"]:
        return jsonify({"success": False, "message": "Status must be TAKEN or MISSED"}), 400

    conn = get_db()
    cursor = conn.cursor()
    today_str = date.today().strftime("%Y-%m-%d")
    now_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    time_only = datetime.now().strftime("%I:%M %p")

    # Locate adherence entry
    if adherence_id and int(adherence_id) > 0:
        cursor.execute("SELECT * FROM adherence WHERE id = ?", (adherence_id,))
        adh = cursor.fetchone()
    elif medication_id:
        cursor.execute("""
            SELECT * FROM adherence
            WHERE medication_id = ? AND scheduled_date = ?
        """, (medication_id, today_str))
        adh = cursor.fetchone()
    else:
        adh = None

    if adh:
        # Check duplicate confirmation prevention
        if adh["status"] == new_status:
            conn.close()
            return jsonify({
                "success": True,
                "already_confirmed": True,
                "status": new_status,
                "message": f"This dose was already confirmed as {new_status} at {adh['confirmed_at'] or 'earlier'}."
            })

        adh_id = adh["id"]
        medication_id = adh["medication_id"]
        cursor.execute("""
            UPDATE adherence
            SET status = ?, confirmed_at = ?
            WHERE id = ?
        """, (new_status, now_time, adh_id))
    elif medication_id:
        cursor.execute("SELECT * FROM medications WHERE id = ?", (medication_id,))
        med = cursor.fetchone()
        if med:
            cursor.execute("""
                INSERT INTO adherence (medication_id, scheduled_date, scheduled_time, status, confirmed_at)
                VALUES (?, ?, ?, ?, ?)
            """, (medication_id, today_str, med["scheduled_time"], new_status, now_time))
            adh_id = cursor.lastrowid
        else:
            conn.close()
            return jsonify({"success": False, "message": "Medication record not found"}), 404
    else:
        conn.close()
        return jsonify({"success": False, "message": "Invalid medication or adherence ID"}), 400

    # Retrieve medicine details for notification
    cursor.execute("SELECT * FROM medications WHERE id = ?", (medication_id,))
    med_info = cursor.fetchone()
    med_name = med_info["medicine_name"] if med_info else "Medication"
    dosage = med_info["dosage"] if med_info else ""
    sched_time = med_info["scheduled_time"] if med_info else time_only

    # Notification generation
    if new_status == "MISSED":
        notif_msg = f"⚠ Patient missed {med_name} ({dosage}) scheduled for {sched_time}."
        cursor.execute("""
            INSERT INTO notifications (patient_id, medication_id, message, type, is_read, created_at)
            VALUES (?, ?, ?, 'MISSED_DOSE', 0, ?)
        """, (patient_id, medication_id, notif_msg, now_time))
    else:
        notif_msg = f"✓ Confirmed: {med_name} ({dosage}) marked TAKEN at {time_only}."
        cursor.execute("""
            INSERT INTO notifications (patient_id, medication_id, message, type, is_read, created_at)
            VALUES (?, ?, ?, 'MEDICATION_REMINDER', 0, ?)
        """, (patient_id, medication_id, notif_msg, now_time))

    conn.commit()
    conn.close()

    updated_stats = get_patient_today_stats(patient_id)

    return jsonify({
        "success": True,
        "already_confirmed": False,
        "status": new_status,
        "confirmed_at": now_time,
        "adherence_id": adh_id,
        "stats": updated_stats,
        "message": f"Dose successfully recorded as {new_status}!"
    })


# ==========================================
# MEDIVOICE CONVERSATIONAL AI ENDPOINT
# ==========================================

@app.route("/api/medivoice/chat", methods=["POST"])
def medivoice_chat():
    """
    Conversational AI endpoint for MediVoice.
    Handles voice and typed text queries, grounded in actual database records.
    Accessible to both logged-in users and unauthenticated users on Login page.
    """
    data = request.get_json() or {}
    user_text = data.get("message", "").strip()
    target_patient_id = data.get("target_patient_id")
    requested_lang = data.get("language")

    user_id = session.get("user_id")
    user_role = session.get("role", "guest" if not user_id else "patient")

    conn = get_db()
    result = process_medivoice_query(
        user_text=user_text,
        user_id=user_id,
        user_role=user_role,
        db_conn=conn,
        target_patient_id=target_patient_id,
        requested_lang=requested_lang
    )
    conn.close()

    return jsonify({
        "success": True,
        "language": result.get("lang"),
        **result
    })


# ==========================================
# CAREGIVER DASHBOARD & NOTIFICATIONS
# ==========================================

@app.route("/caregiver")
def caregiver_dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    caregiver_id = session["user_id"]
    conn = get_db()
    cursor = conn.cursor()

    # Retrieve all patients explicitly authorized for this caregiver
    cursor.execute("""
        SELECT u.id, u.name, u.email
        FROM caregiver_patients cp
        JOIN users u ON cp.patient_id = u.id
        WHERE cp.caregiver_id = ?
        ORDER BY u.name ASC
    """, (caregiver_id,))
    authorized_patients = cursor.fetchall()

    if not authorized_patients:
        conn.close()
        return render_template(
            "caregiver.html",
            user_name=session.get("user_name"),
            patient=None,
            authorized_patients=[],
            patient_meds=[],
            missed_alerts=[],
            recent_history=[],
            stats={"percentage": 0, "total": 0, "taken": 0, "missed": 0, "pending": 0},
            today_date=date.today().strftime("%A, %B %d, %Y")
        )

    # Determine selected patient from authorized list
    req_patient_id = request.args.get("patient_id")
    if req_patient_id:
        try:
            req_id = int(req_patient_id)
            # Authorization guard: Verify patient is authorized for this caregiver
            if not any(p["id"] == req_id for p in authorized_patients):
                conn.close()
                return "403 Forbidden: You are not authorized to view this patient's records.", 403
            patient = [p for p in authorized_patients if p["id"] == req_id][0]
        except ValueError:
            patient = authorized_patients[0]
    else:
        patient = authorized_patients[0]

    patient_id = patient["id"]
    ensure_today_adherence_records(patient_id)
    today_str = date.today().strftime("%Y-%m-%d")

    # Date filter for history: today, week, month, all
    history_filter = request.args.get("filter", "all")
    today = date.today()

    # Today's medicines for patient
    cursor.execute("""
        SELECT 
            m.id as med_id,
            m.medicine_name,
            m.dosage,
            m.scheduled_time,
            m.instructions,
            COALESCE(a.status, 'PENDING') as status,
            a.confirmed_at
        FROM medications m
        LEFT JOIN adherence a ON m.id = a.medication_id AND a.scheduled_date = ?
        WHERE m.patient_id = ?
          AND m.start_date <= ?
          AND m.end_date >= ?
        ORDER BY m.scheduled_time ASC
    """, (today_str, patient_id, today_str, today_str))
    patient_meds = cursor.fetchall()

    # Missed Medication Alerts for authorized patients
    cursor.execute("""
        SELECT 
            n.id,
            n.message,
            n.created_at,
            m.medicine_name,
            m.dosage,
            m.scheduled_time,
            u.name as patient_name
        FROM notifications n
        JOIN users u ON n.patient_id = u.id
        LEFT JOIN medications m ON n.medication_id = m.id
        WHERE n.type = 'MISSED_DOSE' AND n.patient_id = ?
        ORDER BY n.created_at DESC
        LIMIT 10
    """, (patient_id,))
    missed_alerts = cursor.fetchall()

    # Adherence history with period filter
    hist_query = """
        SELECT 
            a.scheduled_date,
            a.scheduled_time,
            a.status,
            a.confirmed_at,
            m.medicine_name,
            m.dosage
        FROM adherence a
        JOIN medications m ON a.medication_id = m.id
        WHERE m.patient_id = ?
    """
    hist_params = [patient_id]
    if history_filter == "today":
        hist_query += " AND a.scheduled_date = ?"
        hist_params.append(today_str)
    elif history_filter == "week":
        week_ago = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        hist_query += " AND a.scheduled_date >= ?"
        hist_params.append(week_ago)
    elif history_filter == "month":
        month_ago = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        hist_query += " AND a.scheduled_date >= ?"
        hist_params.append(month_ago)

    hist_query += " ORDER BY a.scheduled_date DESC, a.scheduled_time DESC LIMIT 15"
    cursor.execute(hist_query, hist_params)
    recent_history = cursor.fetchall()

    conn.close()

    stats = get_patient_today_stats(patient_id)

    return render_template(
        "caregiver.html",
        user_name=session.get("user_name"),
        patient=patient,
        authorized_patients=authorized_patients,
        patient_meds=patient_meds,
        missed_alerts=missed_alerts,
        recent_history=recent_history,
        history_filter=history_filter,
        stats=stats,
        today_date=date.today().strftime("%A, %B %d, %Y")
    )


@app.route("/notifications")
def get_notifications():
    if "user_id" not in session:
        return jsonify({"success": False, "notifications": []})

    user_id = session["user_id"]
    conn = get_db()
    cursor = conn.cursor()

    if session.get("role") == "caregiver":
        # Get notifications for authorized patients only
        cursor.execute("""
            SELECT n.*, u.name as patient_name
            FROM notifications n
            JOIN users u ON n.patient_id = u.id
            JOIN caregiver_patients cp ON n.patient_id = cp.patient_id
            WHERE cp.caregiver_id = ?
            ORDER BY n.created_at DESC
            LIMIT 20
        """, (user_id,))
    else:
        cursor.execute("""
            SELECT * FROM notifications
            WHERE patient_id = ?
            ORDER BY created_at DESC
            LIMIT 20
        """, (user_id,))

    notifs = cursor.fetchall()
    conn.close()

    return jsonify({
        "success": True,
        "notifications": [dict(n) for n in notifs]
    })


@app.route("/notifications/read/<int:notif_id>", methods=["POST"])
def mark_notification_read(notif_id):
    if "user_id" not in session:
        return jsonify({"success": False}), 401

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notif_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@app.route("/notifications/clear", methods=["POST"])
def clear_all_notifications():
    if "user_id" not in session:
        return jsonify({"success": False}), 401

    conn = get_db()
    cursor = conn.cursor()
    if session.get("role") == "caregiver":
        cursor.execute("""
            UPDATE notifications
            SET is_read = 1
            WHERE patient_id IN (SELECT patient_id FROM caregiver_patients WHERE caregiver_id = ?)
        """, (session["user_id"],))
    else:
        cursor.execute("UPDATE notifications SET is_read = 1 WHERE patient_id = ?", (session["user_id"],))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# ==========================================
# HISTORY & ANALYTICS
# ==========================================

@app.route("/history")
def history():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cursor = conn.cursor()

    # Determine patient ID with authorization check
    if session.get("role") == "caregiver":
        req_p = request.args.get("patient_id")
        cursor.execute("""
            SELECT u.id, u.name
            FROM caregiver_patients cp
            JOIN users u ON cp.patient_id = u.id
            WHERE cp.caregiver_id = ?
        """, (session["user_id"],))
        auth_pts = cursor.fetchall()

        if not auth_pts:
            conn.close()
            return "No authorized patients assigned to your account.", 403

        if req_p:
            match = [p for p in auth_pts if p["id"] == int(req_p)]
            if not match:
                conn.close()
                return "403 Forbidden: You are not authorized to view this patient.", 403
            patient_id = match[0]["id"]
            patient_name = match[0]["name"]
        else:
            patient_id = auth_pts[0]["id"]
            patient_name = auth_pts[0]["name"]
    else:
        patient_id = session["user_id"]
        patient_name = session.get("user_name")

    filter_period = request.args.get("filter", "all")  # today, week, month, all
    today = date.today()

    query = """
        SELECT 
            a.id,
            a.scheduled_date,
            a.scheduled_time,
            a.status,
            a.confirmed_at,
            m.medicine_name,
            m.dosage,
            m.frequency,
            m.instructions
        FROM adherence a
        JOIN medications m ON a.medication_id = m.id
        WHERE m.patient_id = ?
    """
    params = [patient_id]

    if filter_period == "today":
        query += " AND a.scheduled_date = ?"
        params.append(today.strftime("%Y-%m-%d"))
    elif filter_period == "week":
        week_ago = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        query += " AND a.scheduled_date >= ?"
        params.append(week_ago)
    elif filter_period == "month":
        month_ago = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        query += " AND a.scheduled_date >= ?"
        params.append(month_ago)

    query += " ORDER BY a.scheduled_date DESC, a.scheduled_time DESC"
    cursor.execute(query, params)
    history_records = cursor.fetchall()
    conn.close()

    return render_template(
        "history.html",
        records=history_records,
        active_filter=filter_period,
        patient_name=patient_name
    )


@app.route("/api/analytics")
def analytics_api():
    """
    Provides real data from SQLite for Chart.js:
    - Weekly adherence percentage trend (past 7 days)
    - Taken vs Missed vs Pending distribution
    - Summary metrics
    """
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db()
    cursor = conn.cursor()

    if session.get("role") == "caregiver":
        req_p = request.args.get("patient_id")
        cursor.execute("""
            SELECT patient_id FROM caregiver_patients WHERE caregiver_id = ?
        """, (session["user_id"],))
        auth_pts = [r["patient_id"] for r in cursor.fetchall()]

        if not auth_pts:
            conn.close()
            return jsonify({"error": "No authorized patients."}), 403

        if req_p and int(req_p) in auth_pts:
            patient_id = int(req_p)
        else:
            patient_id = auth_pts[0]
    else:
        patient_id = session["user_id"]

    today = date.today()

    # 1. Weekly adherence chart data (last 7 days)
    days_labels = []
    adherence_rates = []

    for i in range(6, -1, -1):
        target_day = today - timedelta(days=i)
        day_str = target_day.strftime("%Y-%m-%d")
        day_name = target_day.strftime("%a")

        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN a.status = 'TAKEN' THEN 1 ELSE 0 END) as taken_count
            FROM adherence a
            JOIN medications m ON a.medication_id = m.id
            WHERE m.patient_id = ? AND a.scheduled_date = ?
        """, (patient_id, day_str))
        row = cursor.fetchone()

        total = row["total"] or 0
        taken = row["taken_count"] or 0
        rate = round((taken / total * 100), 1) if total > 0 else 0

        days_labels.append(day_name)
        adherence_rates.append(rate)

    # 2. Overall counts (last 30 days)
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN a.status = 'TAKEN' THEN 1 ELSE 0 END) as taken,
            SUM(CASE WHEN a.status = 'MISSED' THEN 1 ELSE 0 END) as missed,
            SUM(CASE WHEN a.status = 'PENDING' THEN 1 ELSE 0 END) as pending
        FROM adherence a
        JOIN medications m ON a.medication_id = m.id
        WHERE m.patient_id = ?
    """, (patient_id,))
    totals_row = cursor.fetchone()
    conn.close()

    total_sched = totals_row["total"] or 0
    total_taken = totals_row["taken"] or 0
    total_missed = totals_row["missed"] or 0
    total_pending = totals_row["pending"] or 0

    today_stats = get_patient_today_stats(patient_id)

    # Calculate weekly overall adherence
    week_taken = sum([r for r in adherence_rates if r > 0])
    active_days = len([r for r in adherence_rates if r > 0])
    weekly_avg = round(week_taken / active_days, 1) if active_days > 0 else 0

    return jsonify({
        "today_percentage": today_stats["percentage"],
        "weekly_percentage": weekly_avg,
        "total_scheduled": total_sched,
        "total_taken": total_taken,
        "total_missed": total_missed,
        "total_pending": total_pending,
        "weekly_labels": days_labels,
        "weekly_adherence": adherence_rates,
        "distribution": {
            "taken": total_taken,
            "missed": total_missed,
            "pending": total_pending
        }
    })


# ==========================================
# CAREGIVER AUTHORIZATION & ISOLATION HELPERS
# ==========================================

def is_caregiver_authorized_for_patient(caregiver_id, patient_id):
    """Verifies that a caregiver is explicitly linked and authorized for a patient in database."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM caregiver_patients 
        WHERE caregiver_id = ? AND patient_id = ?
    """, (caregiver_id, patient_id))
    record = cursor.fetchone()
    conn.close()
    return record is not None


# ==========================================
# ADMIN ROLE PROTECTION DECORATOR
# ==========================================

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Administrator sign-in required.", "error")
            return redirect(url_for("admin_login"))
        if session.get("role") != "admin":
            return render_template("error_403.html", message="Forbidden: Administrator access required."), 403
        return f(*args, **kwargs)
    return decorated_function


# ==========================================
# EXCEL AND PDF REPORT GENERATORS
# ==========================================

def build_patient_excel_bytes(patient, meds, adherence_rows, stats):
    """Builds professional Excel clinical adherence report using openpyxl."""
    wb = openpyxl.Workbook()
    header_fill = PatternFill(start_color="0B9F9C", end_color="0B9F9C", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    title_font = Font(name="Calibri", size=15, bold=True, color="0B9F9C")

    # Sheet 1: Overview
    ws1 = wb.active
    ws1.title = "Adherence Overview"
    ws1["A1"] = "SMART MEDICATION ADHERENCE SYSTEM"
    ws1["A1"].font = title_font
    ws1["A2"] = f"Patient Clinical Report &bull; Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    ws1["A2"].font = Font(name="Calibri", size=10, italic=True)

    ws1["A4"] = "Patient Name:"
    ws1["B4"] = patient["name"]
    ws1["A5"] = "Registered Contact:"
    ws1["B5"] = patient["phone"] or "Not registered"
    ws1["A6"] = "Email Address:"
    ws1["B6"] = patient["email"]
    ws1["A7"] = "Overall Adherence Rate:"
    ws1["B7"] = f"{stats.get('percentage', 0)}%"

    for r in range(4, 8):
        ws1[f"A{r}"].font = Font(bold=True)

    ws1["A9"] = "Compliance Metric"
    ws1["B9"] = "Count"
    ws1["A9"].fill = header_fill
    ws1["B9"].fill = header_fill
    ws1["A9"].font = header_font
    ws1["B9"].font = header_font

    kpis = [
        ("Total Scheduled Doses", stats.get("total", 0)),
        ("Confirmed TAKEN Doses", stats.get("taken", 0)),
        ("Recorded MISSED Doses", stats.get("missed", 0)),
        ("PENDING Doses Today", stats.get("pending", 0)),
        ("Adherence Compliance Rate", f"{stats.get('percentage', 0)}%")
    ]
    for idx, (k, v) in enumerate(kpis, start=10):
        ws1[f"A{idx}"] = k
        ws1[f"B{idx}"] = v

    ws1.column_dimensions["A"].width = 28
    ws1.column_dimensions["B"].width = 28

    # Sheet 2: Prescriptions
    ws2 = wb.create_sheet(title="Prescriptions")
    m_cols = ["Medicine Name", "Dosage", "Frequency", "Scheduled Time", "Start Date", "End Date", "Instructions"]
    for c_i, h in enumerate(m_cols, start=1):
        cell = ws2.cell(row=1, column=c_i, value=h)
        cell.fill = header_fill
        cell.font = header_font
    for r_i, m in enumerate(meds, start=2):
        ws2.cell(row=r_i, column=1, value=m["medicine_name"])
        ws2.cell(row=r_i, column=2, value=m["dosage"])
        ws2.cell(row=r_i, column=3, value=m["frequency"])
        ws2.cell(row=r_i, column=4, value=m["scheduled_time"])
        ws2.cell(row=r_i, column=5, value=m["start_date"])
        ws2.cell(row=r_i, column=6, value=m["end_date"])
        ws2.cell(row=r_i, column=7, value=m["instructions"] or "")
    for col in ws2.columns:
        max_l = max(len(str(c.value or "")) for c in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws2.column_dimensions[col_letter].width = max(max_l + 3, 13)

    # Sheet 3: Adherence History
    ws3 = wb.create_sheet(title="Dose History")
    h_cols = ["Date", "Scheduled Time", "Medicine", "Dosage", "Status", "Confirmed At"]
    for c_i, h in enumerate(h_cols, start=1):
        cell = ws3.cell(row=1, column=c_i, value=h)
        cell.fill = header_fill
        cell.font = header_font
    for r_i, h in enumerate(adherence_rows, start=2):
        ws3.cell(row=r_i, column=1, value=h["scheduled_date"])
        ws3.cell(row=r_i, column=2, value=h["scheduled_time"])
        ws3.cell(row=r_i, column=3, value=h["medicine_name"])
        ws3.cell(row=r_i, column=4, value=h["dosage"])
        status_cell = ws3.cell(row=r_i, column=5, value=h["status"])
        if h["status"] == "TAKEN":
            status_cell.font = Font(color="10B981", bold=True)
        elif h["status"] == "MISSED":
            status_cell.font = Font(color="EF4444", bold=True)
        ws3.cell(row=r_i, column=6, value=h["confirmed_at"] or "")
    for col in ws3.columns:
        max_l = max(len(str(c.value or "")) for c in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws3.column_dimensions[col_letter].width = max(max_l + 3, 14)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def build_patient_pdf_bytes(patient, meds, adherence_rows, stats):
    """Builds professional PDF clinical adherence report using reportlab."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#0B9F9C')
    )
    sub_style = ParagraphStyle(
        'SubTitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#64748B')
    )
    h2_style = ParagraphStyle(
        'Heading2Style',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=colors.HexColor('#0F172A'),
        spaceBefore=10,
        spaceAfter=5
    )
    normal_style = ParagraphStyle(
        'NormalSmall',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#334155')
    )

    story = []
    story.append(Paragraph("SMART MEDICATION ADHERENCE SYSTEM", title_style))
    story.append(Paragraph(f"Patient Clinical Adherence Report &bull; Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", sub_style))
    story.append(Spacer(1, 12))

    # Patient Details Table
    p_data = [
        [Paragraph("<b>Patient Name:</b>", normal_style), Paragraph(str(patient["name"]), normal_style),
         Paragraph("<b>Adherence Rate:</b>", normal_style), Paragraph(f"<b>{stats.get('percentage', 0)}%</b>", normal_style)],
        [Paragraph("<b>Email:</b>", normal_style), Paragraph(str(patient["email"]), normal_style),
         Paragraph("<b>Contact Phone:</b>", normal_style), Paragraph(str(patient["phone"] or "Not registered"), normal_style)],
        [Paragraph("<b>Total Scheduled:</b>", normal_style), Paragraph(str(stats.get("total", 0)), normal_style),
         Paragraph("<b>Taken / Missed:</b>", normal_style), Paragraph(f"{stats.get('taken', 0)} Taken / {stats.get('missed', 0)} Missed", normal_style)]
    ]
    p_table = Table(p_data, colWidths=[105, 165, 105, 165])
    p_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8FAFC')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#CBD5E1')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(p_table)
    story.append(Spacer(1, 10))

    # Prescriptions Table
    story.append(Paragraph("Prescribed Medications & Schedule", h2_style))
    m_headers = ["Medicine", "Dosage", "Frequency", "Time", "Period", "Instructions"]
    m_data = [[Paragraph(f"<b>{h}</b>", normal_style) for h in m_headers]]
    for m in meds:
        m_data.append([
            Paragraph(str(m["medicine_name"]), normal_style),
            Paragraph(str(m["dosage"]), normal_style),
            Paragraph(str(m["frequency"]), normal_style),
            Paragraph(str(m["scheduled_time"]), normal_style),
            Paragraph(f"{m['start_date']} to {m['end_date']}", normal_style),
            Paragraph(str(m["instructions"] or "-")[:35], normal_style)
        ])
    if len(m_data) == 1:
        m_data.append([Paragraph("No active prescriptions found", normal_style)] * 6)
    m_table = Table(m_data, colWidths=[100, 70, 75, 75, 110, 110])
    m_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0B9F9C')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(m_table)
    story.append(Spacer(1, 10))

    # Adherence Confirmation Records
    story.append(Paragraph("Recent Adherence Confirmations", h2_style))
    h_headers = ["Date", "Time", "Medicine", "Dosage", "Status", "Confirmed At"]
    h_data = [[Paragraph(f"<b>{h}</b>", normal_style) for h in h_headers]]
    for row in adherence_rows[:15]:
        col_hex = "#10B981" if row["status"] == "TAKEN" else ("#EF4444" if row["status"] == "MISSED" else "#F59E0B")
        h_data.append([
            Paragraph(str(row["scheduled_date"]), normal_style),
            Paragraph(str(row["scheduled_time"]), normal_style),
            Paragraph(str(row["medicine_name"]), normal_style),
            Paragraph(str(row["dosage"]), normal_style),
            Paragraph(f"<font color='{col_hex}'><b>{row['status']}</b></font>", normal_style),
            Paragraph(str(row["confirmed_at"] or "-"), normal_style)
        ])
    if len(h_data) == 1:
        h_data.append([Paragraph("No recent dose confirmations", normal_style)] * 6)
    h_table = Table(h_data, colWidths=[90, 75, 110, 75, 80, 110])
    h_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0F172A')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(h_table)

    doc.build(story)
    buf.seek(0)
    return buf


def build_admin_summary_excel_bytes(patients, caregivers, stats):
    """Builds overall system adherence and registry summary in Excel."""
    wb = openpyxl.Workbook()
    header_fill = PatternFill(start_color="0B9F9C", end_color="0B9F9C", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")

    ws1 = wb.active
    ws1.title = "System Overview"
    ws1["A1"] = "SMART MEDICATION SYSTEM - ADMINISTRATIVE SUMMARY"
    ws1["A1"].font = Font(name="Calibri", size=15, bold=True, color="0B9F9C")
    ws1["A2"] = f"Report Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    ws1["A4"] = "SYSTEM METRIC"
    ws1["B4"] = "COUNT"
    ws1["A4"].fill = header_fill
    ws1["B4"].fill = header_fill
    ws1["A4"].font = header_font
    ws1["B4"].font = header_font

    metrics = [
        ("Total Registered Patients", stats.get("total_patients", 0)),
        ("Total Registered Caregivers", stats.get("total_caregivers", 0)),
        ("Total Active Prescriptions", stats.get("total_medications", 0)),
        ("Total Recorded Missed Doses", stats.get("total_missed", 0)),
        ("Overall System Adherence Compliance", f"{stats.get('overall_adherence', 0)}%"),
        ("Total Dispatched Notifications", stats.get("total_notifications", 0))
    ]
    for idx, (k, v) in enumerate(metrics, start=5):
        ws1[f"A{idx}"] = k
        ws1[f"B{idx}"] = v
    ws1.column_dimensions["A"].width = 35
    ws1.column_dimensions["B"].width = 25

    # Patients Sheet
    ws2 = wb.create_sheet(title="Patients Registry")
    p_headers = ["ID", "Name", "Email", "Phone", "Adherence %", "Total Meds", "Registration Date"]
    for c_i, h in enumerate(p_headers, start=1):
        cell = ws2.cell(row=1, column=c_i, value=h)
        cell.fill = header_fill
        cell.font = header_font
    for r_i, p in enumerate(patients, start=2):
        ws2.cell(row=r_i, column=1, value=p["id"])
        ws2.cell(row=r_i, column=2, value=p["name"])
        ws2.cell(row=r_i, column=3, value=p["email"])
        ws2.cell(row=r_i, column=4, value=p["phone"] or "")
        ws2.cell(row=r_i, column=5, value=f"{p['adherence_rate']}%")
        ws2.cell(row=r_i, column=6, value=p["med_count"])
        ws2.cell(row=r_i, column=7, value=p["created_at"] or "")
    for col in ws2.columns:
        max_l = max(len(str(c.value or "")) for c in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws2.column_dimensions[col_letter].width = max(max_l + 3, 12)

    # Caregivers Sheet
    ws3 = wb.create_sheet(title="Caregivers Registry")
    cg_headers = ["ID", "Name", "Email", "Phone", "Relationship", "Preferred Channel", "Assigned Patients"]
    for c_i, h in enumerate(cg_headers, start=1):
        cell = ws3.cell(row=1, column=c_i, value=h)
        cell.fill = header_fill
        cell.font = header_font
    for r_i, cg in enumerate(caregivers, start=2):
        ws3.cell(row=r_i, column=1, value=cg["id"])
        ws3.cell(row=r_i, column=2, value=cg["name"])
        ws3.cell(row=r_i, column=3, value=cg["email"])
        ws3.cell(row=r_i, column=4, value=cg["phone"] or "")
        ws3.cell(row=r_i, column=5, value=cg["relationship"] or "Family")
        ws3.cell(row=r_i, column=6, value=cg["preferred_channel"] or "SMS")
        ws3.cell(row=r_i, column=7, value=cg["assigned_patients"] or "None")
    for col in ws3.columns:
        max_l = max(len(str(c.value or "")) for c in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws3.column_dimensions[col_letter].width = max(max_l + 3, 14)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def build_admin_summary_pdf_bytes(patients, caregivers, stats):
    """Builds administrative overview report in PDF format."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=16,
        leading=20,
        textColor=colors.HexColor('#0B9F9C')
    )
    sub_style = ParagraphStyle('SubTitle', parent=styles['Normal'], fontName='Helvetica', fontSize=9, leading=13, textColor=colors.HexColor('#64748B'))
    h2_style = ParagraphStyle('Heading2Style', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=11, leading=15, textColor=colors.HexColor('#0F172A'), spaceBefore=10, spaceAfter=4)
    normal_style = ParagraphStyle('NormalSmall', parent=styles['Normal'], fontName='Helvetica', fontSize=8.5, leading=11, textColor=colors.HexColor('#334155'))

    story = [
        Paragraph("SMART MEDICATION ADHERENCE SYSTEM &bull; ADMIN SUMMARY", title_style),
        Paragraph(f"Overall System Adherence and Clinical Registry &bull; {datetime.now().strftime('%Y-%m-%d %H:%M')}", sub_style),
        Spacer(1, 10)
    ]

    # Metrics Table
    kpi_data = [
        [Paragraph("<b>Total Patients:</b>", normal_style), Paragraph(str(stats.get("total_patients", 0)), normal_style),
         Paragraph("<b>Total Caregivers:</b>", normal_style), Paragraph(str(stats.get("total_caregivers", 0)), normal_style)],
        [Paragraph("<b>Active Medications:</b>", normal_style), Paragraph(str(stats.get("total_medications", 0)), normal_style),
         Paragraph("<b>System Adherence:</b>", normal_style), Paragraph(f"<b>{stats.get('overall_adherence', 0)}%</b>", normal_style)],
        [Paragraph("<b>Recorded Missed Doses:</b>", normal_style), Paragraph(str(stats.get("total_missed", 0)), normal_style),
         Paragraph("<b>Dispatched Notifications:</b>", normal_style), Paragraph(str(stats.get("total_notifications", 0)), normal_style)]
    ]
    t_kpi = Table(kpi_data, colWidths=[130, 140, 130, 140])
    t_kpi.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8FAFC')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#CBD5E1')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(t_kpi)
    story.append(Spacer(1, 10))

    # Patients Registry Table
    story.append(Paragraph("Patient Directory", h2_style))
    p_headers = ["ID", "Name", "Email", "Phone", "Adherence %", "Medications"]
    p_data = [[Paragraph(f"<b>{h}</b>", normal_style) for h in p_headers]]
    for p in patients[:20]:
        p_data.append([
            Paragraph(str(p["id"]), normal_style),
            Paragraph(str(p["name"]), normal_style),
            Paragraph(str(p["email"]), normal_style),
            Paragraph(str(p["phone"] or "-"), normal_style),
            Paragraph(f"<b>{p['adherence_rate']}%</b>", normal_style),
            Paragraph(str(p["med_count"]), normal_style)
        ])
    t_patients = Table(p_data, colWidths=[30, 120, 160, 90, 75, 65])
    t_patients.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0B9F9C')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_patients)

    doc.build(story)
    buf.seek(0)
    return buf


def build_notifications_excel_bytes(notifications):
    """Builds Excel workbook for notification delivery logs."""
    wb = openpyxl.Workbook()
    header_fill = PatternFill(start_color="0B9F9C", end_color="0B9F9C", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")

    ws = wb.active
    ws.title = "Notification Logs"
    headers = ["ID", "Patient Name", "Recipient Phone", "Channel", "Type", "Status", "Message", "Timestamp", "Error"]
    for c_i, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=c_i, value=h)
        cell.fill = header_fill
        cell.font = header_font

    for r_i, n in enumerate(notifications, start=2):
        ws.cell(row=r_i, column=1, value=n["id"])
        ws.cell(row=r_i, column=2, value=n["patient_name"] or "System")
        ws.cell(row=r_i, column=3, value=n["recipient_phone"] or "")
        ws.cell(row=r_i, column=4, value=n["channel"] or "IN_APP")
        ws.cell(row=r_i, column=5, value=n["type"] or "")
        ws.cell(row=r_i, column=6, value=n["status"] or "DELIVERED")
        ws.cell(row=r_i, column=7, value=n["message"] or "")
        ws.cell(row=r_i, column=8, value=n["created_at"] or "")
        ws.cell(row=r_i, column=9, value=n["error_message"] or "")

    for col in ws.columns:
        max_l = max(len(str(c.value or "")) for c in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_l + 3, 12)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ==========================================
# ADMIN AUTHENTICATION & MANAGEMENT ROUTES
# ==========================================

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """Dedicated secure administrative login endpoint."""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        if not email or not password:
            flash("Admin email and password are required.", "error")
            return render_template("admin_login.html", email=email)

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE LOWER(email) = ? AND role = 'admin'", (email,))
        admin_user = cursor.fetchone()
        conn.close()

        if admin_user and check_password_hash(admin_user["password"], password):
            session["user_id"] = admin_user["id"]
            session["user_name"] = admin_user["name"]
            session["user_email"] = admin_user["email"]
            session["role"] = "admin"
            log_audit_event(admin_user["id"], "ADMIN_LOGIN_SUCCESS")
            flash("Administrator session authenticated.", "success")
            return redirect(url_for("admin_dashboard"))
        else:
            log_audit_event(None, "ADMIN_LOGIN_FAILED", f"Attempted Email: {email}")
            flash("Invalid administrator credentials.", "error")
            return render_template("admin_login.html", email=email)

    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    """Logs out administrator session."""
    if session.get("role") == "admin":
        log_audit_event(session.get("user_id"), "ADMIN_LOGOUT")
    session.clear()
    flash("Administrator session closed.", "info")
    return redirect(url_for("admin_login"))


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    """Comprehensive Admin & Clinical Doctor Dashboard."""
    conn = get_db()
    cursor = conn.cursor()

    # 1. Total counts
    cursor.execute("SELECT COUNT(*) as cnt FROM users WHERE role = 'patient'")
    total_patients = cursor.fetchone()["cnt"]

    cursor.execute("SELECT COUNT(*) as cnt FROM users WHERE role = 'caregiver'")
    total_caregivers = cursor.fetchone()["cnt"]

    cursor.execute("SELECT COUNT(*) as cnt FROM medications")
    total_medications = cursor.fetchone()["cnt"]

    cursor.execute("SELECT COUNT(*) as cnt FROM adherence WHERE status = 'MISSED'")
    total_missed = cursor.fetchone()["cnt"]

    cursor.execute("SELECT COUNT(*) as cnt FROM notifications")
    total_notifications = cursor.fetchone()["cnt"]

    # Overall adherence calculation
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status = 'TAKEN' THEN 1 ELSE 0 END) as taken
        FROM adherence
    """)
    adh_row = cursor.fetchone()
    total_doses = adh_row["total"] or 0
    taken_doses = adh_row["taken"] or 0
    overall_adherence = round((taken_doses / total_doses * 100), 1) if total_doses > 0 else 0

    stats = {
        "total_patients": total_patients,
        "total_caregivers": total_caregivers,
        "total_medications": total_medications,
        "total_missed": total_missed,
        "total_notifications": total_notifications,
        "overall_adherence": overall_adherence
    }

    # 2. Patient Directory with adherence rates
    cursor.execute("""
        SELECT 
            u.id, u.name, u.email, u.phone, u.created_at,
            COUNT(DISTINCT m.id) as med_count,
            COUNT(a.id) as dose_total,
            SUM(CASE WHEN a.status = 'TAKEN' THEN 1 ELSE 0 END) as dose_taken
        FROM users u
        LEFT JOIN medications m ON u.id = m.patient_id
        LEFT JOIN adherence a ON m.id = a.medication_id
        WHERE u.role = 'patient'
        GROUP BY u.id
        ORDER BY u.name ASC
    """)
    patient_rows = cursor.fetchall()
    patients = []
    for p in patient_rows:
        d_tot = p["dose_total"] or 0
        d_tak = p["dose_taken"] or 0
        rate = round((d_tak / d_tot * 100), 1) if d_tot > 0 else 0
        patients.append({
            "id": p["id"],
            "name": p["name"],
            "email": p["email"],
            "phone": p["phone"],
            "created_at": p["created_at"],
            "med_count": p["med_count"],
            "adherence_rate": rate
        })

    # 3. Caregiver Directory with assigned patient names
    cursor.execute("""
        SELECT 
            u.id, u.name, u.email, u.phone,
            cp.relationship, cp.preferred_channel,
            GROUP_CONCAT(p.name, ', ') as assigned_patients
        FROM users u
        LEFT JOIN caregiver_profiles cp ON u.id = cp.caregiver_id
        LEFT JOIN caregiver_patients rel ON u.id = rel.caregiver_id
        LEFT JOIN users p ON rel.patient_id = p.id
        WHERE u.role = 'caregiver'
        GROUP BY u.id
        ORDER BY u.name ASC
    """)
    caregivers = cursor.fetchall()

    # 4. Recent Notification Delivery Logs
    cursor.execute("""
        SELECT 
            n.id, n.recipient_phone, n.channel, n.type, n.status, n.message, n.created_at, n.error_message,
            u.name as patient_name
        FROM notifications n
        LEFT JOIN users u ON n.patient_id = u.id
        ORDER BY n.id DESC
        LIMIT 25
    """)
    notifications_log = cursor.fetchall()

    conn.close()

    return render_template(
        "admin_dashboard.html",
        stats=stats,
        patients=patients,
        caregivers=caregivers,
        notifications_log=notifications_log,
        today_date=date.today().strftime("%A, %B %d, %Y")
    )


@app.route("/admin/assign_caregiver", methods=["POST"])
@admin_required
def admin_assign_caregiver():
    """Assigns or updates relationship between a caregiver and a patient."""
    caregiver_id = request.form.get("caregiver_id")
    patient_id = request.form.get("patient_id")
    relationship = request.form.get("relationship", "Family Caregiver").strip()

    if not (caregiver_id and patient_id):
        flash("Both Caregiver and Patient must be selected.", "error")
        return redirect(url_for("admin_dashboard"))

    conn = get_db()
    cursor = conn.cursor()
    now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT OR REPLACE INTO caregiver_patients (caregiver_id, patient_id, assigned_at)
        VALUES (?, ?, ?)
    """, (caregiver_id, patient_id, now_ts))

    cursor.execute("""
        INSERT OR REPLACE INTO caregiver_profiles (caregiver_id, relationship, updated_at)
        VALUES (?, ?, ?)
    """, (caregiver_id, relationship, now_ts))

    conn.commit()
    conn.close()

    log_audit_event(session.get("user_id"), "ADMIN_ASSIGN_CAREGIVER", f"Caregiver {caregiver_id} -> Patient {patient_id}")
    flash("Caregiver-patient authorization link established successfully.", "success")
    return redirect(url_for("admin_dashboard"))


# ==========================================
# ADMINISTRATIVE EXPORT ROUTES
# ==========================================

@app.route("/admin/export/excel/summary")
@admin_required
def admin_export_excel_summary():
    """Exports overall clinical patient summary as Excel."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as cnt FROM users WHERE role = 'patient'")
    t_pat = cursor.fetchone()["cnt"]
    cursor.execute("SELECT COUNT(*) as cnt FROM users WHERE role = 'caregiver'")
    t_cg = cursor.fetchone()["cnt"]
    cursor.execute("SELECT COUNT(*) as cnt FROM medications")
    t_med = cursor.fetchone()["cnt"]
    cursor.execute("SELECT COUNT(*) as cnt FROM adherence WHERE status = 'MISSED'")
    t_mis = cursor.fetchone()["cnt"]
    cursor.execute("SELECT COUNT(*) as cnt FROM notifications")
    t_not = cursor.fetchone()["cnt"]
    cursor.execute("SELECT COUNT(*) as total, SUM(CASE WHEN status = 'TAKEN' THEN 1 ELSE 0 END) as taken FROM adherence")
    adh = cursor.fetchone()
    rate = round((adh["taken"] / adh["total"] * 100), 1) if adh["total"] else 0

    stats = {
        "total_patients": t_pat,
        "total_caregivers": t_cg,
        "total_medications": t_med,
        "total_missed": t_mis,
        "total_notifications": t_not,
        "overall_adherence": rate
    }

    cursor.execute("""
        SELECT u.id, u.name, u.email, u.phone, u.created_at,
               COUNT(DISTINCT m.id) as med_count,
               COUNT(a.id) as dose_total,
               SUM(CASE WHEN a.status = 'TAKEN' THEN 1 ELSE 0 END) as dose_taken
        FROM users u
        LEFT JOIN medications m ON u.id = m.patient_id
        LEFT JOIN adherence a ON m.id = a.medication_id
        WHERE u.role = 'patient'
        GROUP BY u.id
    """)
    patients = []
    for p in cursor.fetchall():
        dt = p["dose_total"] or 0
        d_tak = p["dose_taken"] or 0
        p_rate = round((d_tak / dt * 100), 1) if dt > 0 else 0
        patients.append({
            "id": p["id"], "name": p["name"], "email": p["email"], "phone": p["phone"],
            "created_at": p["created_at"], "med_count": p["med_count"], "adherence_rate": p_rate
        })

    cursor.execute("""
        SELECT u.id, u.name, u.email, u.phone, cp.relationship, cp.preferred_channel,
               GROUP_CONCAT(p.name, ', ') as assigned_patients
        FROM users u
        LEFT JOIN caregiver_profiles cp ON u.id = cp.caregiver_id
        LEFT JOIN caregiver_patients rel ON u.id = rel.caregiver_id
        LEFT JOIN users p ON rel.patient_id = p.id
        WHERE u.role = 'caregiver'
        GROUP BY u.id
    """)
    caregivers = cursor.fetchall()
    conn.close()

    excel_file = build_admin_summary_excel_bytes(patients, caregivers, stats)
    filename = f"SmartMed_System_Summary_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return send_file(excel_file, as_attachment=True, download_name=filename, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/admin/export/pdf/summary")
@admin_required
def admin_export_pdf_summary():
    """Exports overall adherence report as PDF."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as cnt FROM users WHERE role = 'patient'")
    t_pat = cursor.fetchone()["cnt"]
    cursor.execute("SELECT COUNT(*) as cnt FROM users WHERE role = 'caregiver'")
    t_cg = cursor.fetchone()["cnt"]
    cursor.execute("SELECT COUNT(*) as cnt FROM medications")
    t_med = cursor.fetchone()["cnt"]
    cursor.execute("SELECT COUNT(*) as cnt FROM adherence WHERE status = 'MISSED'")
    t_mis = cursor.fetchone()["cnt"]
    cursor.execute("SELECT COUNT(*) as cnt FROM notifications")
    t_not = cursor.fetchone()["cnt"]
    cursor.execute("SELECT COUNT(*) as total, SUM(CASE WHEN status = 'TAKEN' THEN 1 ELSE 0 END) as taken FROM adherence")
    adh = cursor.fetchone()
    rate = round((adh["taken"] / adh["total"] * 100), 1) if adh["total"] else 0

    stats = {
        "total_patients": t_pat,
        "total_caregivers": t_cg,
        "total_medications": t_med,
        "total_missed": t_mis,
        "total_notifications": t_not,
        "overall_adherence": rate
    }

    cursor.execute("""
        SELECT u.id, u.name, u.email, u.phone, u.created_at,
               COUNT(DISTINCT m.id) as med_count,
               COUNT(a.id) as dose_total,
               SUM(CASE WHEN a.status = 'TAKEN' THEN 1 ELSE 0 END) as dose_taken
        FROM users u
        LEFT JOIN medications m ON u.id = m.patient_id
        LEFT JOIN adherence a ON m.id = a.medication_id
        WHERE u.role = 'patient'
        GROUP BY u.id
    """)
    patients = []
    for p in cursor.fetchall():
        dt = p["dose_total"] or 0
        d_tak = p["dose_taken"] or 0
        p_rate = round((d_tak / dt * 100), 1) if dt > 0 else 0
        patients.append({
            "id": p["id"], "name": p["name"], "email": p["email"], "phone": p["phone"],
            "created_at": p["created_at"], "med_count": p["med_count"], "adherence_rate": p_rate
        })
    conn.close()

    pdf_file = build_admin_summary_pdf_bytes(patients, [], stats)
    filename = f"SmartMed_Admin_Summary_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    return send_file(pdf_file, as_attachment=True, download_name=filename, mimetype="application/pdf")


@app.route("/admin/export/excel/patient/<int:patient_id>")
@admin_required
def admin_export_excel_patient(patient_id):
    """Admin export of individual patient Excel report."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ? AND role = 'patient'", (patient_id,))
    patient = cursor.fetchone()
    if not patient:
        conn.close()
        flash("Patient not found.", "error")
        return redirect(url_for("admin_dashboard"))

    cursor.execute("SELECT * FROM medications WHERE patient_id = ?", (patient_id,))
    meds = cursor.fetchall()
    cursor.execute("""
        SELECT a.scheduled_date, a.scheduled_time, a.status, a.confirmed_at, m.medicine_name, m.dosage
        FROM adherence a
        JOIN medications m ON a.medication_id = m.id
        WHERE m.patient_id = ?
        ORDER BY a.scheduled_date DESC, a.scheduled_time DESC
    """, (patient_id,))
    adherence_rows = cursor.fetchall()
    conn.close()

    stats = get_patient_today_stats(patient_id)
    excel_file = build_patient_excel_bytes(patient, meds, adherence_rows, stats)
    clean_name = re.sub(r'[^a-zA-Z0-9]', '_', patient['name'])
    filename = f"Clinical_Report_{clean_name}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return send_file(excel_file, as_attachment=True, download_name=filename, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/admin/export/pdf/patient/<int:patient_id>")
@admin_required
def admin_export_pdf_patient(patient_id):
    """Admin export of individual patient PDF report."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ? AND role = 'patient'", (patient_id,))
    patient = cursor.fetchone()
    if not patient:
        conn.close()
        flash("Patient not found.", "error")
        return redirect(url_for("admin_dashboard"))

    cursor.execute("SELECT * FROM medications WHERE patient_id = ?", (patient_id,))
    meds = cursor.fetchall()
    cursor.execute("""
        SELECT a.scheduled_date, a.scheduled_time, a.status, a.confirmed_at, m.medicine_name, m.dosage
        FROM adherence a
        JOIN medications m ON a.medication_id = m.id
        WHERE m.patient_id = ?
        ORDER BY a.scheduled_date DESC, a.scheduled_time DESC
    """, (patient_id,))
    adherence_rows = cursor.fetchall()
    conn.close()

    stats = get_patient_today_stats(patient_id)
    pdf_file = build_patient_pdf_bytes(patient, meds, adherence_rows, stats)
    clean_name = re.sub(r'[^a-zA-Z0-9]', '_', patient['name'])
    filename = f"Clinical_Report_{clean_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(pdf_file, as_attachment=True, download_name=filename, mimetype="application/pdf")


@app.route("/admin/export/excel/notifications")
@admin_required
def admin_export_excel_notifications():
    """Exports notification delivery logs to Excel."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT n.id, n.recipient_phone, n.channel, n.type, n.status, n.message, n.created_at, n.error_message,
               u.name as patient_name
        FROM notifications n
        LEFT JOIN users u ON n.patient_id = u.id
        ORDER BY n.id DESC
    """)
    notifs = cursor.fetchall()
    conn.close()

    excel_file = build_notifications_excel_bytes(notifs)
    filename = f"Notification_Delivery_Log_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return send_file(excel_file, as_attachment=True, download_name=filename, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ==========================================
# CAREGIVER PATIENT REPORT & EXPORT ROUTES
# ==========================================

@app.route("/caregiver/patient/<int:patient_id>")
def caregiver_patient_detail(patient_id):
    """Dedicated Patient Report & Profile view for authorized Caregiver."""
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("role") != "caregiver":
        return render_template("error_403.html", message="Caregiver privileges required."), 403

    caregiver_id = session["user_id"]
    if not is_caregiver_authorized_for_patient(caregiver_id, patient_id):
        return render_template("error_403.html", message="Forbidden: You are not authorized to view this patient's records."), 403

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email, phone, created_at FROM users WHERE id = ?", (patient_id,))
    patient = cursor.fetchone()

    cursor.execute("SELECT * FROM medications WHERE patient_id = ? ORDER BY medicine_name ASC", (patient_id,))
    medications = cursor.fetchall()

    cursor.execute("""
        SELECT a.scheduled_date, a.scheduled_time, a.status, a.confirmed_at, m.medicine_name, m.dosage
        FROM adherence a
        JOIN medications m ON a.medication_id = m.id
        WHERE m.patient_id = ?
        ORDER BY a.scheduled_date DESC, a.scheduled_time DESC
        LIMIT 50
    """, (patient_id,))
    adherence_rows = cursor.fetchall()

    cursor.execute("""
        SELECT id, message, created_at, type, status, channel
        FROM notifications
        WHERE patient_id = ?
        ORDER BY id DESC
        LIMIT 15
    """, (patient_id,))
    notification_history = cursor.fetchall()
    conn.close()

    stats = get_patient_today_stats(patient_id)

    return render_template(
        "caregiver_patient_detail.html",
        patient=patient,
        medications=medications,
        adherence_rows=adherence_rows,
        notification_history=notification_history,
        stats=stats
    )


@app.route("/caregiver/export/excel/<int:patient_id>")
def caregiver_export_excel(patient_id):
    """Caregiver exports Excel report strictly for authorized patient."""
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("role") != "caregiver":
        return render_template("error_403.html", message="Caregiver credentials required."), 403

    caregiver_id = session["user_id"]
    if not is_caregiver_authorized_for_patient(caregiver_id, patient_id):
        return render_template("error_403.html", message="Forbidden: Access to this patient's records is denied."), 403

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email, phone FROM users WHERE id = ?", (patient_id,))
    patient = cursor.fetchone()

    cursor.execute("SELECT * FROM medications WHERE patient_id = ?", (patient_id,))
    meds = cursor.fetchall()

    cursor.execute("""
        SELECT a.scheduled_date, a.scheduled_time, a.status, a.confirmed_at, m.medicine_name, m.dosage
        FROM adherence a
        JOIN medications m ON a.medication_id = m.id
        WHERE m.patient_id = ?
        ORDER BY a.scheduled_date DESC, a.scheduled_time DESC
    """, (patient_id,))
    adherence_rows = cursor.fetchall()
    conn.close()

    stats = get_patient_today_stats(patient_id)
    excel_file = build_patient_excel_bytes(patient, meds, adherence_rows, stats)
    clean_name = re.sub(r'[^a-zA-Z0-9]', '_', patient['name'])
    filename = f"Patient_Adherence_{clean_name}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return send_file(excel_file, as_attachment=True, download_name=filename, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/caregiver/export/pdf/<int:patient_id>")
def caregiver_export_pdf(patient_id):
    """Caregiver exports PDF report strictly for authorized patient."""
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("role") != "caregiver":
        return render_template("error_403.html", message="Caregiver credentials required."), 403

    caregiver_id = session["user_id"]
    if not is_caregiver_authorized_for_patient(caregiver_id, patient_id):
        return render_template("error_403.html", message="Forbidden: Access to this patient's records is denied."), 403

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email, phone FROM users WHERE id = ?", (patient_id,))
    patient = cursor.fetchone()

    cursor.execute("SELECT * FROM medications WHERE patient_id = ?", (patient_id,))
    meds = cursor.fetchall()

    cursor.execute("""
        SELECT a.scheduled_date, a.scheduled_time, a.status, a.confirmed_at, m.medicine_name, m.dosage
        FROM adherence a
        JOIN medications m ON a.medication_id = m.id
        WHERE m.patient_id = ?
        ORDER BY a.scheduled_date DESC, a.scheduled_time DESC
    """, (patient_id,))
    adherence_rows = cursor.fetchall()
    conn.close()

    stats = get_patient_today_stats(patient_id)
    pdf_file = build_patient_pdf_bytes(patient, meds, adherence_rows, stats)
    clean_name = re.sub(r'[^a-zA-Z0-9]', '_', patient['name'])
    filename = f"Patient_Adherence_{clean_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(pdf_file, as_attachment=True, download_name=filename, mimetype="application/pdf")


@app.route("/caregiver/setup", methods=["GET", "POST"])
def caregiver_setup():
    """First-time or editable profile setup for caregivers."""
    if "user_id" not in session or session.get("role") != "caregiver":
        return redirect(url_for("login"))

    caregiver_id = session["user_id"]
    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        relationship = request.form.get("relationship", "Family Caregiver").strip()
        preferred_channel = request.form.get("preferred_channel", "SMS").strip()
        emergency_contact = request.form.get("emergency_contact", "").strip()

        is_valid, ten_digit, _ = validate_indian_phone(phone)
        if not is_valid:
            flash("Please enter a valid 10-digit Indian mobile number (+91 or 10 digits starting with 6-9).", "error")
            return redirect(url_for("caregiver_setup"))

        cursor.execute("UPDATE users SET name = ?, phone = ?, phone_verified = 1 WHERE id = ?", (name, ten_digit, caregiver_id))
        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT OR REPLACE INTO caregiver_profiles (caregiver_id, relationship, preferred_channel, emergency_contact, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (caregiver_id, relationship, preferred_channel, emergency_contact, now_ts))
        conn.commit()
        session["user_name"] = name
        log_audit_event(caregiver_id, "CAREGIVER_PROFILE_UPDATED")
        flash("Caregiver contact details and notification preferences saved successfully!", "success")
        return redirect(url_for("caregiver_dashboard"))

    cursor.execute("""
        SELECT u.name, u.email, u.phone, cp.relationship, cp.preferred_channel, cp.emergency_contact
        FROM users u
        LEFT JOIN caregiver_profiles cp ON u.id = cp.caregiver_id
        WHERE u.id = ?
    """, (caregiver_id,))
    profile = cursor.fetchone()
    conn.close()

    return render_template("caregiver_setup.html", profile=profile)


# ==========================================
# NOTIFICATION PREFERENCES & PHONE SETTINGS
# ==========================================

@app.route("/notification/settings", methods=["GET", "POST"])
def notification_settings():
    """Notification settings page for Patients and Caregivers."""
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        phone_raw = request.form.get("phone", "").strip()
        consent = 1 if request.form.get("consent") else 0
        reminders = request.form.get("notify_reminders")
        missed = request.form.get("notify_missed")
        weekly = request.form.get("notify_weekly")
        channel = request.form.get("preferred_channel", "SMS")

        is_valid, ten_digits, _ = validate_indian_phone(phone_raw)
        if not is_valid:
            flash("Please enter a valid 10-digit Indian phone number (+91 or 10 digits starting with 6-9).", "error")
            return redirect(url_for("notification_settings"))

        prefs = []
        if reminders: prefs.append("reminders")
        if missed: prefs.append("missed")
        if weekly: prefs.append("weekly")
        pref_str = ",".join(prefs) if prefs else "none"

        cursor.execute("""
            UPDATE users 
            SET phone = ?, notification_consent = ?, notification_preferences = ? 
            WHERE id = ?
        """, (ten_digits, consent, pref_str, user_id))

        if session.get("role") == "caregiver":
            cursor.execute("""
                UPDATE caregiver_profiles 
                SET preferred_channel = ?, updated_at = ?
                WHERE caregiver_id = ?
            """, (channel, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id))

        conn.commit()
        log_audit_event(user_id, "NOTIFICATION_SETTINGS_UPDATED", f"Phone: {ten_digits}, Channel: {channel}")
        flash("Mobile notification preferences and contact number updated successfully!", "success")
        return redirect(url_for("notification_settings"))

    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()

    cursor.execute("""
        SELECT * FROM notifications 
        WHERE patient_id = ? OR caregiver_id = ? 
        ORDER BY id DESC 
        LIMIT 20
    """, (user_id, user_id))
    recent_notifs = cursor.fetchall()
    conn.close()

    return render_template("notification_settings.html", user=user, recent_notifs=recent_notifs)


# ==========================================
# GOOGLE OAUTH WITH SELECT_ACCOUNT CHOOSER
# ==========================================

@app.route("/login/google")
def login_google():
    """
    Initiates Google OAuth authorization code flow.
    Enforces prompt=select_account consent so the browser displays Google's account chooser
    and never silently logs into the previous account.
    """
    state_token = secrets.token_urlsafe(16)
    session["oauth_state"] = state_token

    google_client_id = os.environ.get("GOOGLE_CLIENT_ID")
    redirect_uri = request.host_url.rstrip("/") + url_for("login_google_callback")

    if google_client_id:
        # Live Google OAuth 2.0 authorization endpoint with prompt=select_account consent
        google_auth_url = (
            "https://accounts.google.com/o/oauth2/v2/auth"
            f"?client_id={google_client_id}"
            f"&redirect_uri={redirect_uri}"
            "&response_type=code"
            "&scope=openid%20email%20profile"
            f"&state={state_token}"
            "&prompt=select_account%20consent"
        )
        return redirect(google_auth_url)

    # Local development / MVP simulated Google Account Chooser
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email, role FROM users WHERE role IN ('patient', 'caregiver') LIMIT 6")
    available_accounts = cursor.fetchall()
    conn.close()

    return render_template(
        "google_account_chooser.html",
        state=state_token,
        accounts=available_accounts,
        redirect_uri=redirect_uri
    )


@app.route("/login/google/callback", methods=["GET", "POST"])
def login_google_callback():
    """
    Handles Google OAuth code callback or explicit account chooser selection.
    Strict security rule: Google OAuth never grants admin privileges.
    """
    req_state = request.args.get("state") or request.form.get("state")
    expected_state = session.get("oauth_state")

    if not req_state or req_state != expected_state:
        flash("Invalid Google OAuth state token. Please try again.", "error")
        return redirect(url_for("login"))

    chosen_email = ""
    chosen_name = ""

    # Check for live Google OAuth code exchange
    auth_code = request.args.get("code")
    google_client_id = os.environ.get("GOOGLE_CLIENT_ID")
    google_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")

    if auth_code and google_client_id and google_client_secret:
        try:
            token_res = requests.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": auth_code,
                    "client_id": google_client_id,
                    "client_secret": google_client_secret,
                    "redirect_uri": request.host_url.rstrip("/") + url_for("login_google_callback"),
                    "grant_type": "authorization_code"
                },
                timeout=8
            )
            token_json = token_res.json()
            access_token = token_json.get("access_token")
            userinfo_res = requests.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=8
            )
            uinfo = userinfo_res.json()
            chosen_email = uinfo.get("email", "").strip().lower()
            chosen_name = uinfo.get("name", "Google User")
        except Exception as e:
            flash(f"Google OAuth verification failed: {str(e)}", "error")
            return redirect(url_for("login"))
    else:
        # Local development / Account chooser form POST
        chosen_email = (request.form.get("email") or request.args.get("email", "")).strip().lower()
        chosen_name = (request.form.get("name") or request.args.get("name", "Google User")).strip()

    if not chosen_email:
        flash("No Google account was selected.", "error")
        return redirect(url_for("login"))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE LOWER(email) = ?", (chosen_email,))
    user = cursor.fetchone()

    # Security check: Never grant admin privileges through Google sign-in
    if user and user["role"] == "admin":
        conn.close()
        flash("Administrator accounts cannot be authenticated via Google SSO. Please use the dedicated Admin Login.", "error")
        return redirect(url_for("admin_login"))

    if not user:
        # Register new patient via Google identity
        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO users (name, email, password, role, phone, phone_verified, notification_consent, created_at)
            VALUES (?, ?, ?, 'patient', '9989372530', 1, 1, ?)
        """, (chosen_name, chosen_email, generate_password_hash(secrets.token_urlsafe(12)), now_ts))
        conn.commit()
        user_id = cursor.lastrowid
        role = "patient"
        name = chosen_name
    else:
        user_id = user["id"]
        role = user["role"]
        name = user["name"]

    conn.close()

    session["user_id"] = user_id
    session["user_name"] = name
    session["user_email"] = chosen_email
    session["role"] = role

    log_audit_event(user_id, "GOOGLE_AUTH_SUCCESS", f"Email: {chosen_email}, Role: {role}")
    flash(f"Successfully authenticated as {name} via Google Account Chooser.", "success")

    if role == "caregiver":
        return redirect(url_for("caregiver_dashboard"))
    return redirect(url_for("patient_dashboard"))


# Ensure database is automatically initialized on application start
with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
