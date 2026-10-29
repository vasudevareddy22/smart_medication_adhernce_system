import os
import sqlite3
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
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


def init_db():
    """Initializes the database tables and seeds demo accounts and records if not present."""
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

    # 2. medications table (with optional instructions)
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

    # Ensure instructions column exists if table was created previously
    cursor.execute("PRAGMA table_info(medications)")
    cols = [c["name"] for c in cursor.fetchall()]
    if "instructions" not in cols:
        cursor.execute("ALTER TABLE medications ADD COLUMN instructions TEXT DEFAULT ''")

    # 3. adherence table
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

    # 4. notifications table
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

    # 5. caregiver_patients table (Caregiver Authorization Mapping)
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
    else:
        # Ensure demo caregiver and patient authorization exists
        cursor.execute("SELECT id FROM users WHERE email = 'caregiver@test.com'")
        cg = cursor.fetchone()
        cursor.execute("SELECT id FROM users WHERE email = 'patient@test.com'")
        pt = cursor.fetchone()
        if cg and pt:
            cursor.execute("""
                INSERT OR IGNORE INTO caregiver_patients (caregiver_id, patient_id, assigned_at)
                VALUES (?, ?, ?)
            """, (cg["id"], pt["id"], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
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
        if session.get("role") == "caregiver":
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
            flash(f"Welcome back, {user['name']}!", "success")

            if user["role"] == "caregiver":
                return redirect(url_for("caregiver_dashboard"))
            return redirect(url_for("patient_dashboard"))
        else:
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

        if not name or not email or not password:
            flash("All fields are required.", "error")
            return render_template("login.html", is_signup=True)

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("login.html", is_signup=True, name=name, email=email)

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE LOWER(email) = ?", (email,))
        if cursor.fetchone():
            conn.close()
            flash("An account with this email already exists. Please log in.", "error")
            return render_template("login.html", email=email)

        cursor.execute("""
            INSERT INTO users (name, email, password, role)
            VALUES (?, ?, ?, ?)
        """, (name, email, generate_password_hash(password), role))
        conn.commit()
        user_id = cursor.lastrowid

        # If caregiver signed up, assign to demo patient by default
        if role == "caregiver":
            cursor.execute("SELECT id FROM users WHERE role = 'patient' LIMIT 1")
            first_pt = cursor.fetchone()
            if first_pt:
                cursor.execute("""
                    INSERT OR IGNORE INTO caregiver_patients (caregiver_id, patient_id, assigned_at)
                    VALUES (?, ?, ?)
                """, (user_id, first_pt["id"], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()

        conn.close()

        session["user_id"] = user_id
        session["user_name"] = name
        session["user_email"] = email
        session["role"] = role

        flash("Account created successfully!", "success")
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
            if not name:
                flash("Name cannot be empty.", "error")
            else:
                cursor.execute("UPDATE users SET name = ? WHERE id = ?", (name, user_id))
                conn.commit()
                session["user_name"] = name
                flash("Profile name updated successfully!", "success")

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
    """
    if "user_id" not in session:
        return jsonify({"success": False, "reply": "Please log in to speak with MediVoice."}), 401

    data = request.get_json() or {}
    user_text = data.get("message", "").strip()
    target_patient_id = data.get("target_patient_id")

    conn = get_db()
    result = process_medivoice_query(
        user_text=user_text,
        user_id=session["user_id"],
        user_role=session.get("role", "patient"),
        db_conn=conn,
        target_patient_id=target_patient_id
    )
    conn.close()

    return jsonify({
        "success": True,
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


# Ensure database is automatically initialized on application start
with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
