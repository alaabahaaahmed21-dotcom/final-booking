"""Offline Streamlit wizard regression tests; never contacts Google."""
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from sheets import SaveResult

ROOT = Path(__file__).resolve().parents[1]

class WizardTests(unittest.TestCase):
    def setUp(self):
        self.config = patch('sheets.backend_is_configured', return_value=False)
        self.config.start()
        self.addCleanup(self.config.stop)
        self.at = AppTest.from_file(str(ROOT/'app.py'), default_timeout=10).run()
        self.clean()

    def clean(self):
        self.assertFalse(list(self.at.exception), [e.message for e in self.at.exception])

    def page(self, name):
        self.at.button(key='nav_'+name).click().run()
        self.clean()

    def test_empty_pages_and_next(self):
        for page in ('Hotel','Transportation','Review','Complete','Personal'):
            self.page(page)
        self.at.button(key='next_Personal').click().run()
        self.clean()
        self.assertEqual(self.at.session_state['current_page'], 'Hotel')

    def test_individual_retains_fields_and_automatic_guests(self):
        self.at.text_input(key='guest_name').input('alaa bahaa').run()
        self.at.text_input(key='passport_number').input('ab123456').run()
        self.at.date_input(key='date_of_birth').set_value(date(1995,3,21)).run()
        self.page('Hotel')
        self.at.selectbox(key='room_type').select('Triple').run()
        self.clean()
        self.assertTrue(any('Number of guests: 3' in m.value for m in self.at.info))
        self.page('Personal')
        self.assertEqual(self.at.text_input(key='guest_name').value,'ALAA BAHAA')
        self.assertEqual(self.at.text_input(key='passport_number').value,'AB123456')
        self.assertEqual(self.at.date_input(key='date_of_birth').value,date(1995,3,21))
        self.assertFalse(list(self.at.get('file_uploader')))

    def test_federation_rooms_and_transport_retained(self):
        self.at.radio(key='registration_type').set_value('Federation').run()
        self.at.text_input(key='federation_name').input('TEST FEDERATION').run()
        self.at.text_input(key='federation_phone').input('+201012345678').run()
        self.at.text_input(key='federation_email').input('example@example.com').run()
        self.page('Hotel')
        key='rq_Tiba Rose El Golf_Double'
        self.at.number_input(key=key).set_value(3).run()
        self.page('Transportation')
        self.at.checkbox(key='wants_transportation').check().run()
        ident=self.at.session_state['transport_ids'][0]
        self.at.number_input(key=f'tr_{ident}_persons').set_value(60).run()
        self.at.number_input(key=f'tr_{ident}_v4').set_value(1).run()
        self.at.number_input(key=f'tr_{ident}_v2').set_value(1).run()
        self.clean()
        self.page('Review'); self.page('Transportation')
        self.assertEqual(self.at.number_input(key=f'tr_{ident}_v2').value,1)
        add=next(b for b in self.at.button if 'Add another' in b.label)
        add.click().run()
        self.clean()
        self.assertEqual(len(self.at.session_state['transport_ids']),2)
        self.at.button(key=f'tr_{ident}_remove').click().run()
        self.clean()
        self.assertEqual(len(self.at.session_state['transport_ids']),1)
        self.page('Hotel')
        self.assertEqual(self.at.number_input(key=key).value,3)
        self.page('Personal')
        self.assertEqual(self.at.text_input(key='federation_name').value,'TEST FEDERATION')

    def test_unknown_save_retries_same_request(self):
        from test_request import example
        from helpers import calculate_booking_totals
        record=example(); record.update(calculate_booking_totals(record))
        self.at.session_state['pending_submission']=record
        self.page('Complete')
        with patch('sheets.save_to_google_sheets',return_value=SaveResult(False,False,'Retry',{'error_code':'CONNECTION'})) as save:
            next(b for b in self.at.button if b.label=='Retry saving').click().run()
            self.clean()
            self.assertEqual(save.call_args.args[0]['booking_id'],record['booking_id'])
            self.assertEqual(self.at.session_state['pending_submission']['booking_id'],record['booking_id'])
        saved={'booking_id':record['booking_id'],'invoice_no':'INV-TEST','invoice_created':False,'customer_email_sent':False}
        with patch('sheets.save_to_google_sheets',return_value=SaveResult(True,True,data=saved)):
            next(b for b in self.at.button if b.label=='Retry saving').click().run()
            self.clean()
            self.assertTrue(any('received successfully' in m.value for m in self.at.success))

if __name__=='__main__': unittest.main()
