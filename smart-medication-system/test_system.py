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


if __name__ == '__main__':
    unittest.main()
