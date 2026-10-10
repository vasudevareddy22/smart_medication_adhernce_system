"""
Automated Verification Suite for Smart Medication Adherence System
Executes and validates TC01 through TC12 without encoding issues on Windows.
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
            'end_date': next_month
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
            'end_date': next_month
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
        # Check notification in database
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM notifications WHERE type = 'MISSED_DOSE' ORDER BY id DESC LIMIT 1")
        notif = cur.fetchone()
        conn.close()
        self.assertIsNotNone(notif)
        self.assertIn("missed", notif['message'].lower())

        # Log in as caregiver and verify alert appears on dashboard
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
        # Accessing dashboard should redirect to login
        res_protected = self.client.get('/dashboard')
        self.assertEqual(res_protected.status_code, 302)
        print("[PASS] TC12 - Logout")


if __name__ == '__main__':
    unittest.main()
