"""Offline Streamlit wizard regression tests; never contacts Google."""
import unittest
import sys
import types
from datetime import date, time
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

    def choose(self, kind='Federation'):
        self.at.button(key='choose_'+kind).click().run()
        self.clean()

    def test_registration_is_its_own_screen_federation_first(self):
        self.assertEqual(self.at.session_state['current_page'], 'Registration')
        self.assertEqual([button.key for button in self.at.button], ['choose_Federation','choose_Individual'])
        self.assertFalse(list(self.at.text_input))
        self.assertFalse(list(self.at.number_input))
        self.assertFalse(list(self.at.radio))
        self.choose()
        self.assertEqual(self.at.session_state['registration_type'],'Federation')
        self.assertEqual(self.at.session_state['current_page'],'Personal')

    def test_old_config_is_blocked_before_country_can_be_lost(self):
        with patch('config.APP_SCHEMA_VERSION','2026-08-30-v2'):
            self.at=AppTest.from_file(str(ROOT/'app.py'),default_timeout=10).run()
            self.clean()
            self.assertTrue(any('matching v3 config.py' in item.value for item in self.at.error))
            self.assertFalse(list(self.at.button))

    def test_old_helpers_module_in_memory_does_not_break_app(self):
        import helpers
        old = types.ModuleType('helpers')
        old.__dict__.update(helpers.__dict__)
        del old.transport_schedule_dates
        with patch.dict(sys.modules, {'helpers': old}):
            with self.assertRaisesRegex(ImportError, 'transport_schedule_dates'):
                exec('from helpers import transport_schedule_dates', {})
            self.at = AppTest.from_file(str(ROOT/'app.py'), default_timeout=10).run()
            self.clean()
            self.choose()
            self.page('Transportation')
            self.at.checkbox(key='wants_transportation').check().run()
            ident = self.at.session_state['transport_ids'][0]
            prefix = f'tr_{ident}_'
            self.at.selectbox(key=prefix+'date_mode').set_value('Date range').run()
            self.at.date_input(key=prefix+'range_start').set_value(date(2026,10,1)).run()
            self.at.date_input(key=prefix+'range_end').set_value(date(2026,10,12)).run()
            self.clean()
            self.assertTrue(any('12 date(s)' in item.value for item in self.at.info))
            self.assertIs(sys.modules['helpers'], old)
            self.assertFalse(hasattr(old, 'transport_schedule_dates'))

    def test_empty_pages_and_next(self):
        self.choose()
        for page in ('Hotel','Transportation','Review','Complete','Personal'):
            self.page(page)
        self.at.button(key='next_Personal').click().run()
        self.clean()
        self.assertEqual(self.at.session_state['current_page'], 'Hotel')

    def test_individual_retains_fields_and_automatic_guests(self):
        self.choose('Individual')
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
        self.choose()
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
        self.choose()
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

    def test_switch_registration_keeps_each_forms_data(self):
        self.choose()
        self.at.text_input(key='federation_name').input('FEDERATION STORED').run()
        self.page('Registration')
        self.choose('Individual')
        self.at.text_input(key='guest_name').input('individual stored').run()
        self.page('Registration')
        self.choose()
        self.assertEqual(self.at.text_input(key='federation_name').value,'FEDERATION STORED')
        self.page('Registration')
        self.choose('Individual')
        self.assertEqual(self.at.text_input(key='guest_name').value,'INDIVIDUAL STORED')

    def test_federation_country_dropdown_preserved_and_reviewed(self):
        self.choose()
        self.assertIsNone(self.at.selectbox(key='federation_country').value)
        self.at.selectbox(key='federation_country').select('Germany').run()
        self.page('Review')
        self.assertTrue(any('Federation country: Germany' in item.value for item in self.at.markdown))
        self.page('Registration'); self.choose('Individual')
        self.assertNotIn('federation_country',[item.key for item in self.at.selectbox])
        self.page('Registration'); self.choose()
        self.assertEqual(self.at.selectbox(key='federation_country').value,'Germany')

    def test_checkout_warning_text(self):
        self.choose(); self.page('Hotel')
        self.at.date_input(key='check_in').set_value(date(2026,10,24)).run()
        self.at.date_input(key='check_out').set_value(date(2026,10,23)).run()
        self.clean()
        self.assertIn('Check out date must be after check in date.',[item.value for item in self.at.error])

    def transport(self):
        self.choose()
        self.page('Transportation')
        self.at.checkbox(key='wants_transportation').check().run()
        ident=self.at.session_state['transport_ids'][0]
        self.at.number_input(key=f'tr_{ident}_persons').set_value(60).run()
        self.at.number_input(key=f'tr_{ident}_v4').set_value(1).run()
        self.at.number_input(key=f'tr_{ident}_v2').set_value(1).run()
        return ident

    def test_daily_end_choices_respect_8_12_hours_and_detect_next_day(self):
        ident=self.transport(); prefix=f'tr_{ident}_'
        self.at.selectbox(key=prefix+'service').select('Daily 8 Hours').run()
        self.clean()
        self.assertEqual(self.at.selectbox(key=prefix+'end').value,time(17,0))
        self.assertNotIn('18:00',self.at.selectbox(key=prefix+'end').options)
        self.assertNotIn(prefix+'next_day',[item.key for item in self.at.checkbox])
        self.at.time_input(key=prefix+'start').set_value(time(20,0)).run()
        self.clean()
        self.assertEqual(self.at.selectbox(key=prefix+'end').value,time(4,0))
        self.assertTrue(self.at.session_state[prefix+'next_day'])
        self.assertNotIn('05:00 (next day)',self.at.selectbox(key=prefix+'end').options)
        self.at.selectbox(key=prefix+'service').select('Daily 12 Hours').run()
        self.clean()
        self.assertEqual(self.at.selectbox(key=prefix+'end').value,time(8,0))
        self.assertNotIn('09:00 (next day)',self.at.selectbox(key=prefix+'end').options)
        self.at.selectbox(key=prefix+'service').select('Daily 8 Hours').run()
        self.assertEqual(self.at.selectbox(key=prefix+'end').value,time(4,0))
        self.page('Review'); self.page('Transportation')
        self.assertEqual(self.at.selectbox(key=prefix+'end').value,time(4,0))
        self.at.selectbox(key=prefix+'service').select('Airport Transfer').run()
        self.at.time_input(key=prefix+'start').set_value(time(23,0)).run()
        self.at.time_input(key=prefix+'end').set_value(time(1,0)).run()
        self.clean()
        self.assertTrue(self.at.session_state[prefix+'next_day'])
        self.at.time_input(key=prefix+'end').set_value(time(23,30)).run()
        self.assertFalse(self.at.session_state[prefix+'next_day'])

    def test_twelve_dates_single_template_totals_payload_and_retry(self):
        ident=self.transport(); prefix=f'tr_{ident}_'
        self.at.selectbox(key=prefix+'date_mode').set_value('Date range').run()
        self.at.date_input(key=prefix+'range_start').set_value(date(2026,10,1)).run()
        self.at.date_input(key=prefix+'range_end').set_value(date(2026,10,12)).run()
        self.clean()
        self.assertTrue(any('12 date(s) × €250.00' in item.value and '€3,000.00' in item.value for item in self.at.info))
        # Still only one time pair and one group of vehicle inputs, not 12 forms.
        self.assertEqual(len(self.at.time_input),2)
        self.assertEqual(len(self.at.number_input),6)
        self.page('Review'); self.page('Transportation')
        self.assertEqual(self.at.date_input(key=prefix+'range_end').value,date(2026,10,12))
        self.at.multiselect(key=prefix+'excluded_dates').set_value([date(2026,10,5)]).run()
        self.clean()
        self.assertTrue(any('11 date(s) × €250.00' in item.value and '€2,750.00' in item.value for item in self.at.info))
        self.at.button(key='action_duplicate_'+ident).click().run()
        self.clean()
        clone=self.at.session_state['transport_ids'][1]
        self.at.selectbox(key=f'tr_{clone}_direction').select('Hotel to Airport').run()
        self.assertEqual(self.at.selectbox(key=prefix+'direction').value,'Airport to Hotel')
        self.assertEqual(self.at.multiselect(key=f'tr_{clone}_excluded_dates').value,[date(2026,10,5)])
        self.page('Personal')
        self.at.text_input(key='federation_name').input('TEST FEDERATION').run()
        self.at.selectbox(key='federation_country').select('Egypt').run()
        self.at.text_input(key='federation_email').input('example@example.com').run()
        self.at.text_input(key='federation_phone').input('+201012345678').run()
        with patch('sheets.backend_is_configured',return_value=True), patch('sheets.save_to_google_sheets',return_value=SaveResult(False,False,'Retry',{'error_code':'CONNECTION'})) as save:
            self.page('Complete')
            next(b for b in self.at.button if b.label=='Submit Booking Request').click().run()
            self.clean()
            record=save.call_args.args[0]
            self.assertEqual(record['federation_country'],'Egypt')
            self.assertEqual(record['federation_country_code'],'EG')
            self.assertEqual(len(record['transport_services']),22)
            self.assertEqual(record['transport_total_eur'],5500)
            self.assertNotIn('2026-10-05',[item['date'] for item in record['transport_services']])
            self.assertEqual(record['transport_services'][0]['date'],'2026-10-01')
            self.assertEqual(record['transport_services'][10]['date'],'2026-10-12')
            next(b for b in self.at.button if b.label=='Retry saving').click().run()
            self.clean()
            self.assertEqual(save.call_args.args[0],record)

    def test_specific_dates_no_duplicates_can_remove_and_preserve(self):
        ident=self.transport(); prefix=f'tr_{ident}_'
        self.at.selectbox(key=prefix+'date_mode').set_value('Specific dates').run()
        self.at.date_input(key=prefix+'pick_date').set_value(date(2026,10,3)).run()
        self.at.button(key='action_add_date_'+ident).click().run()
        self.at.button(key='action_add_date_'+ident).click().run()
        self.assertEqual(len(self.at.multiselect(key=prefix+'selected_dates').value),1)
        self.at.date_input(key=prefix+'pick_date').set_value(date(2026,10,8)).run()
        self.at.button(key='action_add_date_'+ident).click().run()
        self.clean()
        self.page('Review'); self.page('Transportation')
        self.assertEqual(self.at.multiselect(key=prefix+'selected_dates').value,[date(2026,10,3),date(2026,10,8)])
        self.at.multiselect(key=prefix+'selected_dates').set_value([date(2026,10,8)]).run()
        self.assertTrue(any('1 date(s) × €250.00' in item.value for item in self.at.info))

    def test_invalid_schedule_never_crashes_other_steps_or_submits(self):
        ident=self.transport(); prefix=f'tr_{ident}_'
        self.at.selectbox(key=prefix+'date_mode').set_value('Specific dates').run()
        for name in ('Personal','Hotel','Review','Complete'):
            self.page(name)
        submit=next(b for b in self.at.button if b.label=='Submit Booking Request')
        self.assertTrue(submit.disabled)
        self.assertTrue(any('Select at least one date' in item.value for item in self.at.error))

if __name__=='__main__': unittest.main()
