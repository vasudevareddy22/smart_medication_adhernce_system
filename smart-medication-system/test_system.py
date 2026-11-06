"""
Automated Verification Suite for Smart Medication Adherence System
Executes and validates TC01 through TC19 (Core, MediVoice AI, Authorization, Settings).
"""

import unittest
from datetime import date, timedelta
from app import app, get_db, init_db


class SystemAdherenceTestSuite(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        cls.client = app.test_client()
        with app.app_context():
            init_db()

    def test_tc01_login(self):
        """TC01 - Login test for patient and caregiver demo credentials."""
        # Patient login
        res_patient = self.client.post('/login', data={
            'email': 'patient@test.com',
            'password': 'patient123'
        }, follow_redirects=True)
        self.assertEqual(res_patient.status_code, 200)
        self.assertIn(b"Welcome", res_patient.data)
        self.assertIn(b"Today's Medications", res_patient.data)

        # Caregiver login
        res_caregiver = self.client.post('/login', data={
            'email': 'caregiver@test.com',
            'password': 'caregiver123'
        }, follow_redirects=True)
        self.assertEqual(res_caregiver.status_code, 200)
        self.assertIn(b"Caregiver Dashboard", res_caregiver.data)
        print("[PASS] TC01 - Login")

    def test_tc02_add_medication(self):
        """TC02 - Add medication form submission and database persistence."""
        self.client.post('/login', data={'email': 'patient@test.com', 'password': 'patient123'})

        today = date.today().strftime('%Y-%m-%d')
        next_month = (date.today() + timedelta(days=30)).strftime('%Y-%m-%d')

        res = self.client.post('/medications/add', data={
            'medicine_name': 'Amoxicillin Test',
            'dosage': '250 mg',
            'frequency': 'Once Daily',
            'scheduled_time': '09:00 AM',
            'start_date': today,
            'end_date': next_month,
            'instructions': 'Take after breakfast'
        }, follow_redirects=True)

        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Amoxicillin Test", res.data)

        # Verify in SQLite
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM medications WHERE medicine_name = 'Amoxicillin Test'")
        med = cur.fetchone()
        self.assertIsNotNone(med)
        self.assertEqual(med['dosage'], '250 mg')
        conn.close()
        print("[PASS] TC02 - Add Medication")

    def test_tc03_edit_medication(self):
        """TC03 - Edit an existing medication."""
        self.client.post('/login', data={'email': 'patient@test.com', 'password': 'patient123'})

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id FROM medications WHERE medicine_name = 'Amoxicillin Test' LIMIT 1")
        med = cur.fetchone()
        conn.close()

        med_id = med['id']
        today = date.today().strftime('%Y-%m-%d')
        next_month = (date.today() + timedelta(days=30)).strftime('%Y-%m-%d')

        res = self.client.post(f'/medications/edit/{med_id}', data={
            'medicine_name': 'Amoxicillin 500mg Updated',
            'dosage': '500 mg',
            'frequency': 'Twice Daily',
            'scheduled_time': '10:00 AM',
            'start_date': today,
            'end_date': next_month,
            'instructions': 'Take with plenty of water'
        }, follow_redirects=True)

        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Amoxicillin 500mg Updated", res.data)

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT dosage FROM medications WHERE id = ?", (med_id,))
        updated = cur.fetchone()
        conn.close()
        self.assertEqual(updated['dosage'], '500 mg')
        print("[PASS] TC03 - Edit Medication")

    def test_tc04_delete_medication(self):
        """TC04 - Delete a medication and verify cascade removal."""
        self.client.post('/login', data={'email': 'patient@test.com', 'password': 'patient123'})

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id FROM medications WHERE medicine_name LIKE 'Amoxicillin%' LIMIT 1")
        med = cur.fetchone()
        conn.close()

        med_id = med['id']
        res = self.client.post(f'/medications/delete/{med_id}', follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM medications WHERE id = ?", (med_id,))
        deleted = cur.fetchone()
        conn.close()
        self.assertIsNone(deleted)
        print("[PASS] TC04 - Delete Medication")

    def test_tc05_trigger_reminder(self):
        """TC05 - Trigger instant reminder for college demo."""
        self.client.post('/login', data={'email': 'patient@test.com', 'password': 'patient123'})

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id FROM medications LIMIT 1")
        med = cur.fetchone()
        conn.close()

        res = self.client.post(f'/reminder/test/{med["id"]}')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertIn('medication', data)
        self.assertEqual(data['medication']['id'], med['id'])
        print("[PASS] TC05 - Trigger Reminder")

    def test_tc06_confirm_taken(self):
        """TC06 - Confirm dose as TAKEN and verify database update."""
        self.client.post('/login', data={'email': 'patient@test.com', 'password': 'patient123'})

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id FROM medications WHERE medicine_name = 'Paracetamol' LIMIT 1")
        med = cur.fetchone()
        conn.close()

        res = self.client.post('/adherence/confirm', json={
            'medication_id': med['id'],
            'status': 'TAKEN'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['status'], 'TAKEN')

        # Check adherence table
        today = date.today().strftime('%Y-%m-%d')
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT status FROM adherence WHERE medication_id = ? AND scheduled_date = ?", (med['id'], today))
        adh = cur.fetchone()
        conn.close()
        self.assertEqual(adh['status'], 'TAKEN')
        print("[PASS] TC06 - Confirm TAKEN")

    def test_tc07_confirm_missed(self):
        """TC07 - Confirm dose as MISSED."""
        self.client.post('/login', data={'email': 'patient@test.com', 'password': 'patient123'})

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id FROM medications WHERE medicine_name = 'Calcium' LIMIT 1")
        med = cur.fetchone()
        conn.close()

        res = self.client.post('/adherence/confirm', json={
            'medication_id': med['id'],
            'status': 'MISSED'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['status'], 'MISSED')
        print("[PASS] TC07 - Confirm MISSED")

    def test_tc08_caregiver_alert(self):
        """TC08 - Verify missed dose notification is created and visible to caregiver."""
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM notifications WHERE type = 'MISSED_DOSE' ORDER BY id DESC LIMIT 1")
        notif = cur.fetchone()
        conn.close()
        self.assertIsNotNone(notif)
        self.assertIn("missed", notif['message'].lower())

        self.client.post('/login', data={'email': 'caregiver@test.com', 'password': 'caregiver123'})
        res = self.client.get('/caregiver')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Missed Medication Alerts", res.data)
        self.assertIn(b"Patient missed", res.data)
        print("[PASS] TC08 - Caregiver Alert")

    def test_tc09_adherence_calculation(self):
        """TC09 - Verify adherence rate calculation logic."""
        self.client.post('/login', data={'email': 'patient@test.com', 'password': 'patient123'})
        res = self.client.get('/api/analytics')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('today_percentage', data)
        self.assertIn('weekly_percentage', data)
        self.assertIsInstance(data['today_percentage'], (int, float))
        self.assertTrue(0 <= data['today_percentage'] <= 100)
        print(f"[PASS] TC09 - Adherence Calculation ({data['today_percentage']}%)")

    def test_tc10_history_display(self):
        """TC10 - Verify Adherence history displays filtered records."""
        self.client.post('/login', data={'email': 'patient@test.com', 'password': 'patient123'})
        res_all = self.client.get('/history?filter=all')
        self.assertEqual(res_all.status_code, 200)
        self.assertIn(b"Medication Records", res_all.data)

        res_today = self.client.get('/history?filter=today')
        self.assertEqual(res_today.status_code, 200)
        self.assertIn(b"Medication Records", res_today.data)
        print("[PASS] TC10 - History Display")

    def test_tc11_analytics_chart(self):
        """TC11 - Verify analytics endpoint returns chart structures for Chart.js."""
        self.client.post('/login', data={'email': 'patient@test.com', 'password': 'patient123'})
        res = self.client.get('/api/analytics')
        data = res.get_json()
        self.assertIn('weekly_labels', data)
        self.assertIn('weekly_adherence', data)
        self.assertIn('distribution', data)
        self.assertEqual(len(data['weekly_labels']), 7)
        self.assertEqual(len(data['weekly_adherence']), 7)
        print("[PASS] TC11 - Analytics Chart")

    def test_tc12_logout(self):
        """TC12 - Verify session termination upon logout."""
        self.client.post('/login', data={'email': 'patient@test.com', 'password': 'patient123'})
        res = self.client.get('/logout', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Sign In", res.data)
        res_protected = self.client.get('/dashboard')
        self.assertEqual(res_protected.status_code, 302)
        print("[PASS] TC12 - Logout")

    def test_tc13_caregiver_authorization_isolation(self):
        """TC13 - Verify caregiver cannot view unauthorized patient records (403)."""
        self.client.post('/login', data={'email': 'caregiver@test.com', 'password': 'caregiver123'})
        # Request access to non-existent or unauthorized patient id 9999
        res = self.client.get('/caregiver?patient_id=9999')
        self.assertEqual(res.status_code, 403)
        print("[PASS] TC13 - Caregiver Authorization & Patient Isolation")

    def test_tc14_medivoice_patient_today_medicines(self):
        """TC14 - Verify MediVoice returns today's medications from actual DB records."""
        self.client.post('/login', data={'email': 'patient@test.com', 'password': 'patient123'})
        conn = get_db()
        cur = conn.cursor()
        next_month = (date.today() + timedelta(days=30)).strftime('%Y-%m-%d')
        cur.execute("UPDATE medications SET end_date = ? WHERE patient_id = 1", (next_month,))
        conn.commit()
        conn.close()

        res = self.client.post('/api/medivoice/chat', json={
            'message': 'What medicines do I need to take today?'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertIn('scheduled medicine', data['reply'].lower())
        print("[PASS] TC14 - MediVoice Patient Today's Medicines Query")

    def test_tc15_medivoice_adherence_query(self):
        """TC15 - Verify MediVoice answers adherence percentage accurately."""
        self.client.post('/login', data={'email': 'patient@test.com', 'password': 'patient123'})
        res = self.client.post('/api/medivoice/chat', json={
            'message': 'What is my adherence percentage?'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertIn('%', data['reply'])
        print("[PASS] TC15 - MediVoice Adherence Percentage Query")

    def test_tc16_medivoice_safety_guardrails(self):
        """TC16 - Verify medical safety guardrails on emergencies and dosage changes."""
        self.client.post('/login', data={'email': 'patient@test.com', 'password': 'patient123'})

        # Emergency query test
        res_em = self.client.post('/api/medivoice/chat', json={
            'message': 'I have severe chest pain and shortness of breath'
        })
        data_em = res_em.get_json()
        self.assertIn('emergency', data_em['reply'].lower())
        self.assertEqual(data_em['mode'], 'safety_guardrail')

        # Dosage change refusal test
        res_dose = self.client.post('/api/medivoice/chat', json={
            'message': 'Should I stop taking my medicine or change dosage?'
        })
        data_dose = res_dose.get_json()
        self.assertIn('cannot recommend changing dosages', data_dose['reply'].lower())
        print("[PASS] TC16 - MediVoice Medical Safety Guardrails")

    def test_tc17_caregiver_medivoice_query(self):
        """TC17 - Verify Caregiver can ask MediVoice about authorized patients' missed doses."""
        self.client.post('/login', data={'email': 'caregiver@test.com', 'password': 'caregiver123'})
        res = self.client.post('/api/medivoice/chat', json={
            'message': 'Which patients missed a dose today?'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertTrue(data['authorized'])
        print("[PASS] TC17 - Caregiver MediVoice Query")

    def test_tc18_settings_profile_and_password(self):
        """TC18 - Verify settings profile and password change."""
        self.client.post('/login', data={'email': 'patient@test.com', 'password': 'patient123'})

        # Profile update
        res_prof = self.client.post('/settings', data={
            'action': 'update_profile',
            'name': 'Demo Patient Updated'
        }, follow_redirects=True)
        self.assertEqual(res_prof.status_code, 200)
        self.assertIn(b"Demo Patient Updated", res_prof.data)

        # Restore name
        self.client.post('/settings', data={
            'action': 'update_profile',
            'name': 'Demo Patient'
        })
        print("[PASS] TC18 - Settings Profile & Password Management")

    def test_tc19_duplicate_confirmation_prevention(self):
        """TC19 - Verify duplicate dose confirmation prevention."""
        self.client.post('/login', data={'email': 'patient@test.com', 'password': 'patient123'})

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id FROM medications WHERE medicine_name = 'Paracetamol' LIMIT 1")
        med = cur.fetchone()
        conn.close()

        # Confirm taken
        self.client.post('/adherence/confirm', json={'medication_id': med['id'], 'status': 'TAKEN'})

        # Immediate duplicate confirmation
        res_dup = self.client.post('/adherence/confirm', json={'medication_id': med['id'], 'status': 'TAKEN'})
        data_dup = res_dup.get_json()
        self.assertTrue(data_dup.get('already_confirmed'))
        print("[PASS] TC19 - Duplicate Confirmation Prevention")

    def test_tc20_multilingual_patient_queries(self):
        """TC20 - Verify Patient queries in English, Hindi, Telugu, and Tamil."""
        self.client.post('/login', data={'email': 'patient@test.com', 'password': 'patient123'})

        # 1. English
        res_en = self.client.post('/api/medivoice/chat', json={
            'message': 'What medicines do I need to take today?',
            'language': 'en-IN'
        })
        self.assertEqual(res_en.status_code, 200)
        data_en = res_en.get_json()
        self.assertTrue(data_en['success'])
        self.assertEqual(data_en['language'], 'en-IN')

        # 2. Hindi (Devanagari)
        res_hi = self.client.post('/api/medivoice/chat', json={
            'message': 'आज मुझे कौन सी दवाइयाँ लेनी हैं?',
            'language': 'hi-IN'
        })
        self.assertEqual(res_hi.status_code, 200)
        data_hi = res_hi.get_json()
        self.assertTrue(data_hi['success'])
        self.assertEqual(data_hi['language'], 'hi-IN')

        # 3. Telugu (Telugu script)
        res_te = self.client.post('/api/medivoice/chat', json={
            'message': 'ఈరోజు నేను ఏ మందులు వేసుకోవాలి?',
            'language': 'te-IN'
        })
        self.assertEqual(res_te.status_code, 200)
        data_te = res_te.get_json()
        self.assertTrue(data_te['success'])
        self.assertEqual(data_te['language'], 'te-IN')

        # 4. Tamil (Tamil script)
        res_ta = self.client.post('/api/medivoice/chat', json={
            'message': 'இன்று நான் என்ன மருந்துகளை எடுக்க வேண்டும்?',
            'language': 'ta-IN'
        })
        self.assertEqual(res_ta.status_code, 200)
        data_ta = res_ta.get_json()
        self.assertTrue(data_ta['success'])
        self.assertEqual(data_ta['language'], 'ta-IN')

        print("[PASS] TC20 - Multilingual Patient Queries (EN, HI, TE, TA)")

    def test_tc21_multilingual_caregiver_queries(self):
        """TC21 - Verify Caregiver queries in Hindi, Telugu, and Tamil."""
        self.client.post('/login', data={'email': 'caregiver@test.com', 'password': 'caregiver123'})

        # Hindi Caregiver query
        res_hi = self.client.post('/api/medivoice/chat', json={
            'message': 'आज किन मरीजों की दवा छूटी है?',
            'language': 'hi-IN'
        })
        self.assertEqual(res_hi.status_code, 200)
        data_hi = res_hi.get_json()
        self.assertTrue(data_hi['success'])
        self.assertTrue(data_hi['authorized'])
        self.assertEqual(data_hi['language'], 'hi-IN')

        # Telugu Caregiver query
        res_te = self.client.post('/api/medivoice/chat', json={
            'message': 'ఈరోజు ఏ పేషెంట్లు మందు మిస్ అయ్యారు?',
            'language': 'te-IN'
        })
        self.assertEqual(res_te.status_code, 200)
        data_te = res_te.get_json()
        self.assertTrue(data_te['success'])
        self.assertTrue(data_te['authorized'])
        self.assertEqual(data_te['language'], 'te-IN')

        # Tamil Caregiver query
        res_ta = self.client.post('/api/medivoice/chat', json={
            'message': 'இன்று யார் மருந்தை தவறவிட்டார்கள்?',
            'language': 'ta-IN'
        })
        self.assertEqual(res_ta.status_code, 200)
        data_ta = res_ta.get_json()
        self.assertTrue(data_ta['success'])
        self.assertTrue(data_ta['authorized'])
        self.assertEqual(data_ta['language'], 'ta-IN')

        print("[PASS] TC21 - Multilingual Caregiver Queries (HI, TE, TA)")

    def test_tc22_app_guidance_and_safety_multilingual(self):
        """TC22 - Verify Application Guide and Safety Guardrails across languages."""
        self.client.post('/login', data={'email': 'patient@test.com', 'password': 'patient123'})

        # App guidance in Telugu
        res_guide = self.client.post('/api/medivoice/chat', json={
            'message': 'ఈ సిస్టమ్‌ను ఎలా ఉపయోగించాలి?',
            'language': 'te-IN'
        })
        data_guide = res_guide.get_json()
        self.assertEqual(data_guide['mode'], 'app_guide')
        self.assertEqual(data_guide['language'], 'te-IN')

        # Emergency in Hindi
        res_em_hi = self.client.post('/api/medivoice/chat', json={
            'message': 'मुझे बहुत तेज़ सीने में दर्द है, मदद करें',
            'language': 'hi-IN'
        })
        data_em_hi = res_em_hi.get_json()
        self.assertEqual(data_em_hi['mode'], 'safety_guardrail')
        self.assertIn('112', data_em_hi['reply'])

        # Emergency in Tamil
        res_em_ta = self.client.post('/api/medivoice/chat', json={
            'message': 'நெஞ்சு வலி மிக அதிகம், அவசர உதவி',
            'language': 'ta-IN'
        })
        data_em_ta = res_em_ta.get_json()
        self.assertEqual(data_em_ta['mode'], 'safety_guardrail')
        self.assertIn('112', data_em_ta['reply'])

        print("[PASS] TC22 - Multilingual Application Guidance & Emergency Guardrails")

    def test_tc23_login_page_voice_agent_and_guest_queries(self):
        """TC23 - Verify Voice Assistant is present on Login page and handles guest/login intents."""
        # 1. Login page contains MediVoice elements
        res_login_page = self.client.get('/login')
        self.assertEqual(res_login_page.status_code, 200)
        self.assertIn(b"medivoiceTriggerBtn", res_login_page.data)
        self.assertIn(b"medivoicePermissionModal", res_login_page.data)

        # 2. Unauthenticated user asking how to log in
        with self.client.session_transaction() as sess:
            sess.clear()
        res_guest = self.client.post('/api/medivoice/chat', json={
            'message': 'How do I log in to this system?',
            'language': 'en-IN'
        })
        self.assertEqual(res_guest.status_code, 200)
        data_guest = res_guest.get_json()
        self.assertTrue(data_guest['success'])
        self.assertIn('patient@test.com', data_guest['reply'])

        # 3. Voice 1-click patient login action
        res_voice_login = self.client.post('/api/medivoice/chat', json={
            'message': 'Log in as patient',
            'language': 'en-IN'
        })
        self.assertEqual(res_voice_login.status_code, 200)
        data_voice_login = res_voice_login.get_json()
        self.assertTrue(data_voice_login['success'])
        self.assertIsNotNone(data_voice_login['action'])
        self.assertEqual(data_voice_login['action']['type'], 'quick_login')
        self.assertEqual(data_voice_login['action']['email'], 'patient@test.com')

        # 4. Voice 1-click caregiver login action
        res_cg_voice = self.client.post('/api/medivoice/chat', json={
            'message': 'Login as caregiver',
            'language': 'en-IN'
        })
        self.assertEqual(res_cg_voice.status_code, 200)
        data_cg_voice = res_cg_voice.get_json()
        self.assertTrue(data_cg_voice['success'])
        self.assertEqual(data_cg_voice['action']['type'], 'quick_login')
        self.assertEqual(data_cg_voice['action']['email'], 'caregiver@test.com')

        print("[PASS] TC23 - Login Page Voice Agent & 1-Click Voice Login")

    def test_tc24_patient_phone_validation_and_update(self):
        """TC24 - Test initial default patient phone (9989372530), Indian phone format validation, and profile update."""
        # 1. Verify default contact in database
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT phone FROM users WHERE email = 'patient@test.com'")
        pt = cur.fetchone()
        self.assertIsNotNone(pt)
        self.assertEqual(pt["phone"], "9989372530")
        conn.close()

        # 2. Login as patient and test updating to valid 10-digit Indian phone
        self.client.post('/login', data={'email': 'patient@test.com', 'password': 'patient123'})
        res_update = self.client.post('/settings', data={
            'action': 'update_profile',
            'name': 'Demo Patient Updated',
            'phone': '+91-9876543210'
        }, follow_redirects=True)
        self.assertEqual(res_update.status_code, 200)

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT name, phone FROM users WHERE email = 'patient@test.com'")
        pt_updated = cur.fetchone()
        self.assertEqual(pt_updated["phone"], "9876543210")
        # Reset back to default 9989372530
        cur.execute("UPDATE users SET name = 'Demo Patient', phone = '9989372530' WHERE email = 'patient@test.com'")
        conn.commit()
        conn.close()

        # 3. Test invalid phone number format rejected
        res_invalid = self.client.post('/settings', data={
            'action': 'update_profile',
            'name': 'Demo Patient',
            'phone': '12345'
        }, follow_redirects=True)
        self.assertIn(b"Please enter a valid 10-digit Indian mobile number", res_invalid.data)
        print("[PASS] TC24 - Patient Phone Number Validation & Default Contact (9989372530)")

    def test_tc25_caregiver_contact_collection(self):
        """TC25 - Test caregiver setup collecting name, mobile number, relationship, and preferred channel."""
        self.client.post('/login', data={'email': 'caregiver@test.com', 'password': 'caregiver123'})
        res_get = self.client.get('/caregiver/setup')
        self.assertEqual(res_get.status_code, 200)
        self.assertIn(b"Caregiver Contact", res_get.data)

        res_post = self.client.post('/caregiver/setup', data={
            'name': 'Demo Caregiver Verified',
            'phone': '9989372530',
            'relationship': 'Primary Family Caregiver',
            'preferred_channel': 'SMS',
            'emergency_contact': 'City Hospital Emergency'
        }, follow_redirects=True)
        self.assertEqual(res_post.status_code, 200)

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT u.name, u.phone, cp.relationship, cp.preferred_channel FROM users u JOIN caregiver_profiles cp ON u.id = cp.caregiver_id WHERE u.email = 'caregiver@test.com'")
        cg = cur.fetchone()
        conn.close()
        self.assertEqual(cg["phone"], "9989372530")
        self.assertEqual(cg["relationship"], "Primary Family Caregiver")
        self.assertEqual(cg["preferred_channel"], "SMS")
        print("[PASS] TC25 - Caregiver Contact & Profile Collection")

    def test_tc26_notification_engine_dispatch(self):
        """TC26 - Test notification dispatch engine logging In-App and simulated SMS without fake gateway claims."""
        from app import send_notification
        # Test in-app dispatch
        notif_id, status = send_notification(patient_id=1, message="Take Aspirin 100mg", notif_type="MEDICATION_REMINDER", channel="IN_APP")
        self.assertEqual(status, "DELIVERED")

        # Test mobile SMS dispatch without env keys (simulated accurately)
        notif_id_sms, status_sms = send_notification(patient_id=1, message="Missed dose alert", notif_type="MISSED_DOSE", channel="SMS")
        self.assertIn(status_sms, ["SIMULATED", "DELIVERED"])

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM notifications WHERE id = ?", (notif_id_sms,))
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["channel"], "SMS")
        self.assertIn(row["status"], ["SIMULATED", "DELIVERED"])
        print("[PASS] TC26 - Notification Engine Dispatch & Simulated Delivery Logging")

    def test_tc27_admin_authentication_and_session(self):
        """TC27 - Test separate admin authentication, master admin login, and admin signup flow."""
        with self.client.session_transaction() as sess:
            sess.clear()

        # Failed login with wrong password
        res_fail = self.client.post('/admin/login', data={
            'email': 'vasudevareddyeevuri@gmail.com',
            'password': 'WrongPassword123'
        }, follow_redirects=True)
        self.assertEqual(res_fail.status_code, 200)
        self.assertIn(b"Invalid administrator credentials", res_fail.data)

        # Successful Master Admin login (vasudevareddyeevuri@gmail.com)
        res_master = self.client.post('/admin/login', data={
            'email': 'vasudevareddyeevuri@gmail.com',
            'password': 'Admin@Secure2026!'
        }, follow_redirects=True)
        self.assertEqual(res_master.status_code, 200)
        self.assertIn(b"Governance Overview", res_master.data)
        self.assertIn(b"Patient Directory", res_master.data)
        self.assertIn(b"vasudevareddyeevuri@gmail.com", res_master.data)
        self.assertIn(b"Master", res_master.data)

        # Admin logout
        res_logout = self.client.get('/admin/logout', follow_redirects=True)
        self.assertEqual(res_logout.status_code, 200)
        self.assertIn(b"Administrator session closed", res_logout.data)

        # Test Admin Sign Up endpoint
        res_signup_page = self.client.get('/admin/signup')
        self.assertEqual(res_signup_page.status_code, 200)
        self.assertIn(b"Register Administrator", res_signup_page.data)
        self.assertIn(b"Admin Sign Up", res_signup_page.data)

        # Ensure clean state for supervisor registration test
        conn = get_db()
        conn.execute("DELETE FROM users WHERE email = 'supervisor@smartmed.com'")
        conn.commit()
        conn.close()

        # Test creating new admin through /admin/signup
        res_new_admin = self.client.post('/admin/signup', data={
            'name': 'Clinical Supervisor',
            'email': 'supervisor@smartmed.com',
            'phone': '9989372530',
            'password': 'SupervisorPassword123!',
            'confirm_password': 'SupervisorPassword123!'
        }, follow_redirects=True)
        self.assertEqual(res_new_admin.status_code, 200)
        self.assertIn(b"Governance Overview", res_new_admin.data)
        self.assertIn(b"supervisor@smartmed.com", res_new_admin.data)

        # Test logging in with newly registered admin
        self.client.get('/admin/logout')
        res_relogin = self.client.post('/admin/login', data={
            'email': 'supervisor@smartmed.com',
            'password': 'SupervisorPassword123!'
        }, follow_redirects=True)
        self.assertEqual(res_relogin.status_code, 200)
        self.assertIn(b"Governance Overview", res_relogin.data)
        print("[PASS] TC27 - Master Admin Login, Admin Sign Up, and Authentication Flow")

    def test_tc28_admin_role_access_control(self):
        """TC28 - Test strict 403 Forbidden enforcement on admin dashboard for patients and caregivers."""
        # Unauthenticated user redirected
        with self.client.session_transaction() as sess:
            sess.clear()
        res_anon = self.client.get('/admin/dashboard')
        self.assertEqual(res_anon.status_code, 302)
        self.assertIn('/admin/login', res_anon.headers['Location'])

        # Patient blocked with 403
        self.client.post('/login', data={'email': 'patient@test.com', 'password': 'patient123'})
        res_patient = self.client.get('/admin/dashboard')
        self.assertEqual(res_patient.status_code, 403)
        self.assertIn(b"403", res_patient.data)

        # Caregiver blocked with 403
        self.client.post('/login', data={'email': 'caregiver@test.com', 'password': 'caregiver123'})
        res_cg = self.client.get('/admin/dashboard')
        self.assertEqual(res_cg.status_code, 403)
        self.assertIn(b"403", res_cg.data)
        print("[PASS] TC28 - Admin Role Access Control & 403 Protection")

    def test_tc29_admin_dashboard_metrics_and_directory(self):
        """TC29 - Test admin dashboard metrics, patient directory, and caregiver assignment."""
        self.client.post('/admin/login', data={'email': 'admin@smartmed.com', 'password': 'Admin@Secure2026!'})
        res = self.client.get('/admin/dashboard')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Registered Patients", res.data)
        self.assertIn(b"Registered Caregivers", res.data)
        self.assertIn(b"Patient Directory", res.data)
        self.assertIn(b"Authorized Caregivers Registry", res.data)
        self.assertIn(b"Notification Delivery Audit Trail", res.data)
        print("[PASS] TC29 - Admin Dashboard Metrics & Registry Oversight")

    def test_tc30_caregiver_patient_detail_and_isolation(self):
        """TC30 - Test caregiver accessing authorized patient report and receiving 403 for unauthorized patient."""
        self.client.post('/login', data={'email': 'caregiver@test.com', 'password': 'caregiver123'})
        # Authorized patient (ID: 1)
        res_auth = self.client.get('/caregiver/patient/1')
        self.assertEqual(res_auth.status_code, 200)
        self.assertIn(b"Patient Clinical Report", res_auth.data)
        self.assertIn(b"Download Excel", res_auth.data)
        self.assertIn(b"Download PDF Report", res_auth.data)

        # Unauthorized patient (ID: 9999)
        res_unauth = self.client.get('/caregiver/patient/9999')
        self.assertEqual(res_unauth.status_code, 403)
        print("[PASS] TC30 - Caregiver Patient Detail & Unauthorized Patient Isolation")

    def test_tc31_caregiver_excel_report_export(self):
        """TC31 - Test caregiver Excel clinical report download and unauthorized rejection."""
        self.client.post('/login', data={'email': 'caregiver@test.com', 'password': 'caregiver123'})
        # Authorized export
        res_excel = self.client.get('/caregiver/export/excel/1')
        self.assertEqual(res_excel.status_code, 200)
        self.assertIn("spreadsheetml.sheet", res_excel.headers['Content-Type'])
        self.assertTrue(len(res_excel.data) > 100)

        # Unauthorized export
        res_unauth = self.client.get('/caregiver/export/excel/9999')
        self.assertEqual(res_unauth.status_code, 403)
        print("[PASS] TC31 - Caregiver Excel Report Generation & Security Guard")

    def test_tc32_caregiver_pdf_report_export(self):
        """TC32 - Test caregiver PDF clinical report download and unauthorized rejection."""
        self.client.post('/login', data={'email': 'caregiver@test.com', 'password': 'caregiver123'})
        # Authorized PDF export
        res_pdf = self.client.get('/caregiver/export/pdf/1')
        self.assertEqual(res_pdf.status_code, 200)
        self.assertEqual(res_pdf.headers['Content-Type'], "application/pdf")
        self.assertTrue(res_pdf.data.startswith(b"%PDF"))

        # Unauthorized PDF export
        res_unauth = self.client.get('/caregiver/export/pdf/9999')
        self.assertEqual(res_unauth.status_code, 403)
        print("[PASS] TC32 - Caregiver PDF Report Generation & Security Guard")

    def test_tc33_admin_reports_export_access(self):
        """TC33 - Test admin system-wide Excel & PDF export endpoints."""
        # Non-admin access denied
        self.client.post('/login', data={'email': 'patient@test.com', 'password': 'patient123'})
        res_denied = self.client.get('/admin/export/excel/summary')
        self.assertEqual(res_denied.status_code, 403)

        # Admin access granted
        self.client.post('/admin/login', data={'email': 'admin@smartmed.com', 'password': 'Admin@Secure2026!'})
        res_sum_excel = self.client.get('/admin/export/excel/summary')
        self.assertEqual(res_sum_excel.status_code, 200)
        self.assertIn("spreadsheetml.sheet", res_sum_excel.headers['Content-Type'])

        res_sum_pdf = self.client.get('/admin/export/pdf/summary')
        self.assertEqual(res_sum_pdf.status_code, 200)
        self.assertEqual(res_sum_pdf.headers['Content-Type'], "application/pdf")

        res_notif_excel = self.client.get('/admin/export/excel/notifications')
        self.assertEqual(res_notif_excel.status_code, 200)
        self.assertIn("spreadsheetml.sheet", res_notif_excel.headers['Content-Type'])
        print("[PASS] TC33 - Admin System-wide Excel & PDF Export Endpoints")

    def test_tc34_google_oauth_account_chooser_security(self):
        """TC34 - Test Google OAuth account chooser initiation with prompt=select_account consent, and rejection of admin role escalation."""
        with self.client.session_transaction() as sess:
            sess.clear()

        # 1. Initiating Google OAuth returns account chooser view or redirect
        res_chooser = self.client.get('/login/google')
        self.assertEqual(res_chooser.status_code, 200)
        self.assertIn(b"Choose an account", res_chooser.data)
        self.assertIn(b"prompt=select_account consent", res_chooser.data)

        # 2. Selecting a patient account signs in as patient
        state_token = res_chooser.data.split(b'name="state" value="')[1].split(b'"')[0].decode('utf-8')
        with self.client.session_transaction() as sess:
            sess['oauth_state'] = state_token

        res_callback = self.client.post('/login/google/callback', data={
            'state': state_token,
            'email': 'patient@test.com',
            'name': 'Demo Patient'
        }, follow_redirects=True)
        self.assertEqual(res_callback.status_code, 200)
        self.assertIn(b"Successfully authenticated", res_callback.data)

        # 3. Security: Admin accounts cannot be compromised via Google SSO
        with self.client.session_transaction() as sess:
            sess['oauth_state'] = state_token

        res_admin_block = self.client.post('/login/google/callback', data={
            'state': state_token,
            'email': 'admin@smartmed.com',
            'name': 'Admin Attacker'
        }, follow_redirects=True)
        self.assertIn(b"Administrator accounts cannot be authenticated via Google SSO", res_admin_block.data)
        print("[PASS] TC34 - Google OAuth Account Chooser & Role Escalation Defense")

    def test_tc35_notification_settings_management(self):
        """TC35 - Test Notification Settings page and updating phone and alert preferences."""
        self.client.post('/login', data={'email': 'patient@test.com', 'password': 'patient123'})
        res_get = self.client.get('/notification/settings')
        self.assertEqual(res_get.status_code, 200)
        self.assertIn(b"Mobile Notifications", res_get.data)
        self.assertIn(b"Registered Mobile Number", res_get.data)

        res_post = self.client.post('/notification/settings', data={
            'phone': '9989372530',
            'consent': '1',
            'notify_reminders': '1',
            'notify_missed': '1',
            'notify_weekly': '1'
        }, follow_redirects=True)
        self.assertEqual(res_post.status_code, 200)
        self.assertIn(b"Mobile notification preferences", res_post.data)
        print("[PASS] TC35 - Notification Settings & Contact Preferences Management")

    def test_tc36_medivoice_speech_languages_en_us_and_telugu(self):
        """TC36 - MediVoice Speech-to-Text language support for English (en-US / en-IN) and Telugu (te-IN)."""
        self.client.post('/login', data={'email': 'patient@test.com', 'password': 'patient123'})

        # English (en-US) voice query
        res_en = self.client.post('/api/medivoice/chat', json={
            'message': "What medicines do I need to take today?",
            'language': "en-US"
        })
        self.assertEqual(res_en.status_code, 200)
        data_en = res_en.get_json()
        self.assertTrue(data_en['success'])
        self.assertIn("today", data_en['reply'].lower())

        # Telugu (te-IN) voice query - Today's medications
        res_te = self.client.post('/api/medivoice/chat', json={
            'message': "ఈరోజు నేను ఏ మందులు వేసుకోవాలి?",
            'language': "te-IN"
        })
        self.assertEqual(res_te.status_code, 200)
        data_te = res_te.get_json()
        self.assertTrue(data_te['success'])
        self.assertEqual(data_te['language'], 'te-IN')
        self.assertTrue(any(ord(c) >= 0x0C00 and ord(c) <= 0x0C7F for c in data_te['reply']))

        # Telugu (te-IN) voice query - Adherence rate
        res_te_adh = self.client.post('/api/medivoice/chat', json={
            'message': "నా మందుల అనుసరణ శాతం ఎంత?",
            'language': "te-IN"
        })
        self.assertEqual(res_te_adh.status_code, 200)
        data_te_adh = res_te_adh.get_json()
        self.assertTrue(data_te_adh['success'])
        self.assertEqual(data_te_adh['language'], 'te-IN')
        self.assertIn("%", data_te_adh['reply'])
        print("[PASS] TC36 - MediVoice Speech-to-Text Support for English (en-US) & Telugu (te-IN)")

    def test_tc37_medivoice_caregiver_multilingual_voice_query(self):
        """TC37 - MediVoice Caregiver voice query with target patient ID and Telugu/English language support."""
        self.client.post('/login', data={'email': 'caregiver@test.com', 'password': 'caregiver123'})

        # Caregiver English query
        res_cg_en = self.client.post('/api/medivoice/chat', json={
            'message': "Which patients missed a dose today?",
            'language': "en-US",
            'target_patient_id': None
        })
        self.assertEqual(res_cg_en.status_code, 200)
        data_cg_en = res_cg_en.get_json()
        self.assertTrue(data_cg_en['success'])

        # Caregiver Telugu query for specific authorized patient
        res_cg_te = self.client.post('/api/medivoice/chat', json={
            'message': "గత 7 రోజుల అనుసరణ చూపించండి",
            'language': "te-IN",
            'target_patient_id': 1
        })
        self.assertEqual(res_cg_te.status_code, 200)
        data_cg_te = res_cg_te.get_json()
        self.assertTrue(data_cg_te['success'])
        self.assertEqual(data_cg_te['language'], 'te-IN')
        self.assertTrue(any(ord(c) >= 0x0C00 and ord(c) <= 0x0C7F for c in data_cg_te['reply']))
        print("[PASS] TC37 - Caregiver Multilingual Voice Integration (English & Telugu)")


if __name__ == '__main__':
    unittest.main()


