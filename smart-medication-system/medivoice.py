"""
MediVoice Conversational AI Assistant Service
Handles natural language intent parsing, database grounding, medical safety guardrails,
and patient/caregiver role-based authorization.
"""

import os
import re
from datetime import date, datetime, timedelta

# Check for optional external LLM key
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")


def process_medivoice_query(user_text, user_id, user_role, db_conn, target_patient_id=None):
    """
    Processes a natural language query from either a Patient or a Caregiver.
    Guarantees strict data isolation:
    - If user_role == 'patient', query MUST only inspect records for user_id.
    - If user_role == 'caregiver', query MUST only inspect explicitly authorized patients.
    Returns:
    {
        "reply": str,
        "action": dict or None,
        "mode": "rule_based" or "llm",
        "authorized": bool
    }
    """
    text = user_text.strip().lower()
    today_str = date.today().strftime("%Y-%m-%d")

    # Safety check: Empty text
    if not text:
        return {
            "reply": "I'm listening. You can ask about your medicines today, your adherence rate, or missed doses.",
            "action": None,
            "mode": "rule_based",
            "authorized": True
        }

    # =========================================================================
    # MEDICAL SAFETY & EMERGENCY GUARDRAILS (Highest Priority)
    # =========================================================================
    emergency_keywords = [
        "chest pain", "shortness of breath", "can't breathe", "cannot breathe",
        "overdose", "poison", "unconscious", "emergency", "severe allergic",
        "anaphylaxis", "heart attack", "stroke"
    ]
    if any(k in text for k in emergency_keywords):
        return {
            "reply": "🚨 IMPORTANT: If you are experiencing a medical emergency, severe chest pain, shortness of breath, or allergic reaction, please immediately contact your local emergency services (such as 911 or 112) or go to the nearest emergency department right away.",
            "action": None,
            "mode": "safety_guardrail",
            "authorized": True
        }

    dosage_change_keywords = [
        "stop taking", "stop my medicine", "increase dose", "decrease dose",
        "double my dose", "change dosage", "change my dose", "skip medicine"
    ]
    if any(k in text for k in dosage_change_keywords):
        return {
            "reply": "⚠️ For your safety, I cannot recommend changing dosages or stopping prescribed medications. Please consult your prescribing doctor or pharmacist before making any changes to your medication schedule.",
            "action": None,
            "mode": "safety_guardrail",
            "authorized": True
        }

    cursor = db_conn.cursor()

    # =========================================================================
    # PATIENT INTENT RESOLUTION
    # =========================================================================
    if user_role == "patient":
        patient_id = user_id

        # 1. Today's Medicines ("What medicines do I need to take today?")
        if any(phrase in text for phrase in ["medicines do i need to take", "medicines today", "what do i take today", "scheduled today", "today's medicine", "my medications today"]):
            cursor.execute("""
                SELECT m.medicine_name, m.dosage, m.scheduled_time, COALESCE(a.status, 'PENDING') as status
                FROM medications m
                LEFT JOIN adherence a ON m.id = a.medication_id AND a.scheduled_date = ?
                WHERE m.patient_id = ? AND m.start_date <= ? AND m.end_date >= ?
                ORDER BY m.scheduled_time ASC
            """, (today_str, patient_id, today_str, today_str))
            meds = cursor.fetchall()

            if not meds:
                return {
                    "reply": "You do not have any medications scheduled for today in your system.",
                    "action": None,
                    "mode": "rule_based",
                    "authorized": True
                }

            lines = []
            for m in meds:
                status_note = f" (Status: {m['status']})" if m['status'] != 'PENDING' else " (Pending)"
                lines.append(f"{m['medicine_name']} ({m['dosage']}) at {m['scheduled_time']}{status_note}")

            reply = f"Today you have {len(meds)} scheduled medicine{'s' if len(meds) > 1 else ''}: " + "; ".join(lines) + "."
            return {
                "reply": reply,
                "action": None,
                "mode": "rule_based",
                "authorized": True
            }

        # 2. Missed Doses ("Have I missed any doses this week?", "missed doses")
        if any(phrase in text for phrase in ["missed any doses", "missed dose", "have i missed", "any missed", "missed medicines"]):
            week_ago = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")
            cursor.execute("""
                SELECT a.scheduled_date, a.scheduled_time, m.medicine_name, m.dosage
                FROM adherence a
                JOIN medications m ON a.medication_id = m.id
                WHERE m.patient_id = ? AND a.scheduled_date >= ? AND a.status = 'MISSED'
                ORDER BY a.scheduled_date DESC
            """, (patient_id, week_ago))
            missed = cursor.fetchall()

            if not missed:
                return {
                    "reply": "Great job! You have not missed any medication doses in the past seven days.",
                    "action": None,
                    "mode": "rule_based",
                    "authorized": True
                }

            desc = [f"{m['medicine_name']} ({m['dosage']}) on {m['scheduled_date']} at {m['scheduled_time']}" for m in missed]
            return {
                "reply": f"You have {len(missed)} missed dose{'s' if len(missed) > 1 else ''} recorded this week: " + ", ".join(desc) + ". Remember to stay consistent with your schedule.",
                "action": None,
                "mode": "rule_based",
                "authorized": True
            }

        # 3. Adherence Percentage ("What is my adherence percentage?")
        if any(phrase in text for phrase in ["adherence percentage", "adherence rate", "my adherence", "compliance rate"]):
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN a.status = 'TAKEN' THEN 1 ELSE 0 END) as taken_count
                FROM adherence a
                JOIN medications m ON a.medication_id = m.id
                WHERE m.patient_id = ?
            """, (patient_id,))
            row = cursor.fetchone()
            total = row["total"] or 0
            taken = row["taken_count"] or 0
            pct = round((taken / total * 100), 1) if total > 0 else 0

            return {
                "reply": f"Your overall medication adherence rate is {pct}%, with {taken} doses confirmed taken out of {total} total scheduled doses.",
                "action": None,
                "mode": "rule_based",
                "authorized": True
            }

        # 4. Medication History ("Show my medication history")
        if any(phrase in text for phrase in ["medication history", "adherence history", "show my history", "history log"]):
            return {
                "reply": "You can view your full adherence history log on the History page. In the past 7 days, your records have been logged in the database.",
                "action": {"type": "navigate", "url": "/history"},
                "mode": "rule_based",
                "authorized": True
            }

        # 5. Next Scheduled Dose ("Remind me about my next scheduled medicine")
        if any(phrase in text for phrase in ["next scheduled medicine", "next medicine", "next dose", "when is my next"]):
            cursor.execute("""
                SELECT m.medicine_name, m.dosage, m.scheduled_time, COALESCE(a.status, 'PENDING') as status
                FROM medications m
                LEFT JOIN adherence a ON m.id = a.medication_id AND a.scheduled_date = ?
                WHERE m.patient_id = ? AND m.start_date <= ? AND m.end_date >= ?
                  AND (a.status IS NULL OR a.status = 'PENDING')
                ORDER BY m.scheduled_time ASC
                LIMIT 1
            """, (today_str, patient_id, today_str, today_str))
            next_med = cursor.fetchone()

            if next_med:
                return {
                    "reply": f"Your next scheduled pending dose today is {next_med['medicine_name']} ({next_med['dosage']}) scheduled for {next_med['scheduled_time']}.",
                    "action": None,
                    "mode": "rule_based",
                    "authorized": True
                }
            else:
                return {
                    "reply": "You have no remaining pending doses scheduled for today. All scheduled medications have been confirmed!",
                    "action": None,
                    "mode": "rule_based",
                    "authorized": True
                }

        # 6. Dose Confirmation Voice Trigger ("I took my medicine" / "I took Paracetamol")
        if any(phrase in text for phrase in ["i took my medicine", "i took", "confirm taken", "mark as taken"]):
            # Look for pending medicine today
            cursor.execute("""
                SELECT m.id, m.medicine_name, m.dosage, m.scheduled_time, a.id as adherence_id, COALESCE(a.status, 'PENDING') as status
                FROM medications m
                LEFT JOIN adherence a ON m.id = a.medication_id AND a.scheduled_date = ?
                WHERE m.patient_id = ? AND m.start_date <= ? AND m.end_date >= ?
            """, (today_str, patient_id, today_str, today_str))
            all_today = cursor.fetchall()

            # Filter for pending ones
            pending = [m for m in all_today if m["status"] == "PENDING"]

            # If user mentioned specific name
            matched = [m for m in pending if m["medicine_name"].lower() in text]
            if len(matched) == 1:
                target = matched[0]
                now_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                # Update adherence
                if target["adherence_id"]:
                    cursor.execute("UPDATE adherence SET status = 'TAKEN', confirmed_at = ? WHERE id = ?", (now_time, target["adherence_id"]))
                else:
                    cursor.execute("""
                        INSERT INTO adherence (medication_id, scheduled_date, scheduled_time, status, confirmed_at)
                        VALUES (?, ?, ?, 'TAKEN', ?)
                    """, (target["id"], today_str, target["scheduled_time"], now_time))
                db_conn.commit()

                return {
                    "reply": f"Confirmed! I have marked {target['medicine_name']} ({target['dosage']}) as TAKEN. Your adherence record has been updated.",
                    "action": {"type": "refresh_dashboard"},
                    "mode": "rule_based",
                    "authorized": True
                }
            elif len(pending) == 1:
                target = pending[0]
                now_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if target["adherence_id"]:
                    cursor.execute("UPDATE adherence SET status = 'TAKEN', confirmed_at = ? WHERE id = ?", (now_time, target["adherence_id"]))
                else:
                    cursor.execute("""
                        INSERT INTO adherence (medication_id, scheduled_date, scheduled_time, status, confirmed_at)
                        VALUES (?, ?, ?, 'TAKEN', ?)
                    """, (target["id"], today_str, target["scheduled_time"], now_time))
                db_conn.commit()

                return {
                    "reply": f"Confirmed! I have recorded your scheduled dose of {target['medicine_name']} ({target['dosage']}) as TAKEN.",
                    "action": {"type": "refresh_dashboard"},
                    "mode": "rule_based",
                    "authorized": True
                }
            elif len(pending) > 1:
                names = [m["medicine_name"] for m in pending]
                return {
                    "reply": f"You have multiple pending medications today ({', '.join(names)}). Which medicine did you take?",
                    "action": None,
                    "mode": "rule_based",
                    "authorized": True
                }
            else:
                return {
                    "reply": "All your medications for today are already confirmed as taken or missed.",
                    "action": None,
                    "mode": "rule_based",
                    "authorized": True
                }

        # Default fallback for patient
        return {
            "reply": f"I heard: '{user_text}'. As your MediVoice assistant, you can ask me: 'What medicines do I take today?', 'What is my adherence percentage?', 'Have I missed any doses this week?', or say 'I took my medicine' to confirm a dose.",
            "action": None,
            "mode": "rule_based",
            "authorized": True
        }

    # =========================================================================
    # CAREGIVER INTENT RESOLUTION (Strict Authorization Verified)
    # =========================================================================
    elif user_role == "caregiver":
        caregiver_id = user_id

        # Verify authorized patients for this caregiver
        cursor.execute("""
            SELECT cp.patient_id, u.name, u.email
            FROM caregiver_patients cp
            JOIN users u ON cp.patient_id = u.id
            WHERE cp.caregiver_id = ?
        """, (caregiver_id,))
        authorized_patients = cursor.fetchall()

        if not authorized_patients:
            return {
                "reply": "You do not currently have any assigned patients authorized in your caregiver profile.",
                "action": None,
                "mode": "rule_based",
                "authorized": True
            }

        # Select target patient
        patient_id = None
        patient_name = "your patient"
        if target_patient_id:
            # Verify target_patient_id belongs to authorized list
            auth_match = [p for p in authorized_patients if p["patient_id"] == int(target_patient_id)]
            if auth_match:
                patient_id = auth_match[0]["patient_id"]
                patient_name = auth_match[0]["name"]
            else:
                return {
                    "reply": "Access Denied: You are not authorized to view records for this patient.",
                    "action": None,
                    "mode": "security_guardrail",
                    "authorized": False
                }
        else:
            patient_id = authorized_patients[0]["patient_id"]
            patient_name = authorized_patients[0]["name"]

        # 1. "Which patients missed a dose today?"
        if any(phrase in text for phrase in ["which patients missed a dose", "who missed a dose", "missed a dose today", "missed today"]):
            auth_ids = [p["patient_id"] for p in authorized_patients]
            placeholders = ",".join("?" for _ in auth_ids)
            cursor.execute(f"""
                SELECT u.name, m.medicine_name, m.dosage, a.scheduled_time
                FROM adherence a
                JOIN medications m ON a.medication_id = m.id
                JOIN users u ON m.patient_id = u.id
                WHERE m.patient_id IN ({placeholders}) AND a.scheduled_date = ? AND a.status = 'MISSED'
            """, auth_ids + [today_str])
            missed_today = cursor.fetchall()

            if not missed_today:
                return {
                    "reply": "None of your assigned patients have missed any doses today. All checked prescriptions are on schedule.",
                    "action": None,
                    "mode": "rule_based",
                    "authorized": True
                }

            desc = [f"{r['name']} missed {r['medicine_name']} ({r['dosage']}) at {r['scheduled_time']}" for r in missed_today]
            return {
                "reply": f"Today, the following missed doses were detected: " + "; ".join(desc) + ".",
                "action": None,
                "mode": "rule_based",
                "authorized": True
            }

        # 2. "Show this patient's adherence for the last seven days"
        if any(phrase in text for phrase in ["adherence for the last seven days", "seven days adherence", "7 days adherence", "weekly adherence"]):
            week_ago = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN a.status = 'TAKEN' THEN 1 ELSE 0 END) as taken_count,
                    SUM(CASE WHEN a.status = 'MISSED' THEN 1 ELSE 0 END) as missed_count
                FROM adherence a
                JOIN medications m ON a.medication_id = m.id
                WHERE m.patient_id = ? AND a.scheduled_date >= ?
            """, (patient_id, week_ago))
            stats = cursor.fetchone()
            total = stats["total"] or 0
            taken = stats["taken_count"] or 0
            missed = stats["missed_count"] or 0
            pct = round((taken / total * 100), 1) if total > 0 else 0

            return {
                "reply": f"For {patient_name} over the last seven days ({week_ago} to {today_str}), adherence is {pct}%, with {taken} taken doses, {missed} missed doses, out of {total} scheduled doses.",
                "action": None,
                "mode": "rule_based",
                "authorized": True
            }

        # 3. "Which medicines have pending scheduled doses?"
        if any(phrase in text for phrase in ["pending scheduled doses", "pending doses", "what is pending", "medicines pending"]):
            cursor.execute("""
                SELECT m.medicine_name, m.dosage, m.scheduled_time
                FROM medications m
                LEFT JOIN adherence a ON m.id = a.medication_id AND a.scheduled_date = ?
                WHERE m.patient_id = ? AND m.start_date <= ? AND m.end_date >= ?
                  AND (a.status IS NULL OR a.status = 'PENDING')
                ORDER BY m.scheduled_time ASC
            """, (today_str, patient_id, today_str, today_str))
            pending_meds = cursor.fetchall()

            if not pending_meds:
                return {
                    "reply": f"{patient_name} has no pending scheduled doses remaining for today.",
                    "action": None,
                    "mode": "rule_based",
                    "authorized": True
                }

            desc = [f"{p['medicine_name']} ({p['dosage']}) at {p['scheduled_time']}" for p in pending_meds]
            return {
                "reply": f"{patient_name} currently has {len(pending_meds)} pending dose{'s' if len(pending_meds) > 1 else ''} today: " + ", ".join(desc) + ".",
                "action": None,
                "mode": "rule_based",
                "authorized": True
            }

        # 4. "Summarize this patient's recent missed doses"
        if any(phrase in text for phrase in ["recent missed doses", "summarize missed doses", "missed dose summary"]):
            cursor.execute("""
                SELECT a.scheduled_date, a.scheduled_time, m.medicine_name, m.dosage
                FROM adherence a
                JOIN medications m ON a.medication_id = m.id
                WHERE m.patient_id = ? AND a.status = 'MISSED'
                ORDER BY a.scheduled_date DESC, a.scheduled_time DESC
                LIMIT 5
            """, (patient_id,))
            recent_missed = cursor.fetchall()

            if not recent_missed:
                return {
                    "reply": f"{patient_name} has no recent missed doses logged.",
                    "action": None,
                    "mode": "rule_based",
                    "authorized": True
                }

            desc = [f"{m['medicine_name']} on {m['scheduled_date']} ({m['scheduled_time']})" for m in recent_missed]
            return {
                "reply": f"Recent missed doses for {patient_name}: " + ", ".join(desc) + ".",
                "action": None,
                "mode": "rule_based",
                "authorized": True
            }

        # Caregiver default
        return {
            "reply": f"As caregiver for {patient_name}, you can ask MediVoice: 'Which patients missed a dose today?', 'Show this patient's adherence for the last seven days', 'Which medicines have pending scheduled doses?', or 'Summarize this patient's recent missed doses'.",
            "action": None,
            "mode": "rule_based",
            "authorized": True
        }

    return {
        "reply": "Role unrecognized.",
        "action": None,
        "mode": "rule_based",
        "authorized": False
    }
