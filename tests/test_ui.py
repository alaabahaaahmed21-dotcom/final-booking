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

    def widget(self, kind, key):
        return getattr(self.at, kind)(key='_ui_'+key)

    def complete_personal(self):
        kind = self.at.session_state['registration_type']
        if kind == 'Federation':
            if not self.widget('text_input', 'federation_name').value:
                self.widget('text_input', 'federation_name').input('TEST FEDERATION').run()
            if not self.widget('selectbox', 'federation_country').value:
                self.widget('selectbox', 'federation_country').select('Egypt').run()
        else:
            if not self.widget('text_input', 'guest_name').value:
                self.widget('text_input', 'guest_name').input('test guest').run()
            if not self.widget('text_input', 'passport_number').value:
                self.widget('text_input', 'passport_number').input('TEST12345').run()
            if not self.widget('date_input', 'date_of_birth').value:
                self.widget('date_input', 'date_of_birth').set_value(date(1995,3,21)).run()
        prefix = kind.lower()
        self.widget('text_input', prefix+'_email').input('example@example.com').run()
        self.widget('text_input', prefix+'_phone').input('+201012345678').run()
        self.clean()

    def ready(self, kind='Federation'):
        self.choose(kind)
        self.complete_personal()

    def test_registration_is_its_own_screen_federation_first(self):
        self.assertEqual(self.at.session_state['current_page'], 'Registration')
        self.assertEqual([button.key for button in self.at.button], ['choose_Federation','choose_Individual','manage_existing'])
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
            self.assertTrue(any('matching v5 config.py' in item.value for item in self.at.error))
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
            self.complete_personal()
            self.page('Transportation')
            self.widget('checkbox', key='wants_transportation').check().run()
            ident = self.at.session_state['transport_ids'][0]
            prefix = f'tr_{ident}_'
            self.widget('selectbox', key=prefix+'date_mode').set_value('Date range').run()
            self.widget('date_input', key=prefix+'range_start').set_value(date(2026,10,1)).run()
            self.widget('date_input', key=prefix+'range_end').set_value(date(2026,10,12)).run()
            self.clean()
            self.assertTrue(any('12 date(s)' in item.value for item in self.at.info))
            self.assertIs(sys.modules['helpers'], old)
            self.assertFalse(hasattr(old, 'transport_schedule_dates'))

    def test_empty_personal_blocks_next_but_all_tabs_remain_free(self):
        self.choose()
        self.at.button(key='next_Personal').click().run()
        self.clean()
        self.assertEqual(self.at.session_state['current_page'], 'Personal')
        self.assertIn('Federation name is required.', [m.value for m in self.at.error])
        self.assertIn('Please select the federation country.', [m.value for m in self.at.error])
        self.assertIn('Enter a valid email address.', [m.value for m in self.at.error])
        for page in ('Hotel','Transportation','Review','Complete'):
            self.page(page)
            self.assertEqual(self.at.session_state['current_page'], page)
        submit=next(b for b in self.at.button if b.label=='Submit Booking Request')
        self.assertTrue(submit.disabled)
        self.page('Personal')
        self.complete_personal()
        self.at.button(key='next_Personal').click().run()
        self.clean()
        self.assertEqual(self.at.session_state['current_page'], 'Hotel')

    def test_individual_retains_fields_and_automatic_guests(self):
        self.choose('Individual')
        self.widget('text_input', key='guest_name').input('alaa bahaa').run()
        self.widget('text_input', key='passport_number').input('ab123456').run()
        self.widget('date_input', key='date_of_birth').set_value(date(1995,3,21)).run()
        self.complete_personal()
        self.page('Hotel')
        self.widget('selectbox', key='room_type').select('Triple').run()
        self.clean()
        self.assertTrue(any('Number of guests: 3' in m.value for m in self.at.info))
        self.page('Personal')
        self.assertEqual(self.widget('text_input', key='guest_name').value,'ALAA BAHAA')
        self.assertEqual(self.widget('text_input', key='passport_number').value,'AB123456')
        self.assertEqual(self.widget('date_input', key='date_of_birth').value,date(1995,3,21))
        self.assertFalse(list(self.at.get('file_uploader')))

    def test_federation_rooms_and_transport_retained(self):
        self.choose()
        self.widget('text_input', key='federation_name').input('TEST FEDERATION').run()
        self.widget('text_input', key='federation_phone').input('+201012345678').run()
        self.widget('text_input', key='federation_email').input('example@example.com').run()
        self.widget('selectbox', key='federation_country').select('Egypt').run()
        self.page('Hotel')
        key='rq_Tiba Rose El Golf_Double'
        self.widget('number_input', key=key).set_value(3).run()
        self.page('Transportation')
        self.widget('checkbox', key='wants_transportation').check().run()
        ident=self.at.session_state['transport_ids'][0]
        self.widget('number_input', key=f'tr_{ident}_persons').set_value(60).run()
        self.widget('number_input', key=f'tr_{ident}_v4').set_value(1).run()
        self.widget('number_input', key=f'tr_{ident}_v2').set_value(1).run()
        self.clean()
        self.page('Review'); self.page('Transportation')
        self.assertEqual(self.widget('number_input', key=f'tr_{ident}_v2').value,1)
        add=next(b for b in self.at.button if 'Add another' in b.label)
        add.click().run()
        self.clean()
        self.assertEqual(len(self.at.session_state['transport_ids']),2)
        self.at.button(key=f'tr_{ident}_remove').click().run()
        self.clean()
        self.assertEqual(len(self.at.session_state['transport_ids']),1)
        self.page('Hotel')
        self.assertEqual(self.widget('number_input', key=key).value,3)
        self.page('Personal')
        self.assertEqual(self.widget('text_input', key='federation_name').value,'TEST FEDERATION')

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
        self.widget('text_input', key='federation_name').input('FEDERATION STORED').run()
        self.page('Registration')
        self.choose('Individual')
        self.widget('text_input', key='guest_name').input('individual stored').run()
        self.page('Registration')
        self.choose()
        self.assertEqual(self.widget('text_input', key='federation_name').value,'FEDERATION STORED')
        self.page('Registration')
        self.choose('Individual')
        self.assertEqual(self.widget('text_input', key='guest_name').value,'INDIVIDUAL STORED')

    def test_federation_country_dropdown_preserved_and_reviewed(self):
        self.choose()
        self.assertIsNone(self.widget('selectbox', key='federation_country').value)
        self.widget('selectbox', key='federation_country').select('Germany').run()
        self.complete_personal()
        self.page('Review')
        self.assertTrue(any('Federation country: Germany' in item.value for item in self.at.markdown))
        self.page('Registration'); self.choose('Individual')
        self.assertNotIn('federation_country',[item.key for item in self.at.selectbox])
        self.page('Registration'); self.choose()
        self.assertEqual(self.widget('selectbox', key='federation_country').value,'Germany')

    def test_checkout_warning_text(self):
        self.ready(); self.page('Hotel')
        self.widget('date_input', key='check_in').set_value(date(2026,10,24)).run()
        self.widget('date_input', key='check_out').set_value(date(2026,10,23)).run()
        self.clean()
        self.assertIn('The check-out date must be after the check-in date.',[item.value for item in self.at.error])

    def test_input_batch_with_next_survives_widget_cleanup(self):
        self.choose()
        # No separate rerun/blur between these changes and the navigation click.
        self.widget('text_input', 'federation_name').input('BATCH FEDERATION')
        self.widget('selectbox', 'federation_country').select('Germany')
        self.widget('text_input', 'federation_email').input('batch@example.com')
        self.widget('text_input', 'federation_phone').input('+201012345678')
        self.at.button(key='next_Personal').click().run()
        self.clean()
        self.assertEqual(self.at.session_state['current_page'],'Hotel')
        # These permanent model values are not owned by any widget.
        self.assertEqual(self.at.session_state['federation_name'],'BATCH FEDERATION')
        self.assertNotIn('_ui_federation_name', self.at.session_state.filtered_state)
        for name in ('Transportation','Review','Complete','Personal'):
            self.page(name)
        self.assertEqual(self.widget('text_input','federation_name').value,'BATCH FEDERATION')
        self.assertEqual(self.widget('selectbox','federation_country').value,'Germany')
        self.assertEqual(self.widget('text_input','federation_email').value,'batch@example.com')
        self.assertEqual(self.widget('text_input','federation_phone').value,'+201012345678')

    def test_required_individual_fields_and_invalid_text_preserved(self):
        self.choose('Individual')
        self.widget('text_input','guest_name').input('  test   guest  ')
        self.widget('text_input','individual_email').input('not-an-email')
        self.at.button(key='next_Personal').click().run()
        self.clean()
        self.assertEqual(self.at.session_state['current_page'],'Personal')
        errors=[m.value for m in self.at.error]
        self.assertIn('Please enter a valid date of birth.',errors)
        self.assertIn('Passport number is required (5 to 20 letters or numbers).',errors)
        self.assertIn('Enter a valid email address.',errors)
        self.assertEqual(self.widget('text_input','guest_name').value,'TEST GUEST')
        self.page('Registration'); self.choose(); self.page('Registration'); self.choose('Individual')
        self.assertEqual(self.widget('text_input','individual_email').value,'not-an-email')
        self.assertEqual(self.widget('text_input','guest_name').value,'TEST GUEST')

    def test_hotel_zero_rooms_invalid_dates_block_here_and_back_still_works(self):
        self.ready(); self.page('Hotel')
        self.widget('number_input','rq_Tiba Rose El Golf_Single').set_value(0)
        self.widget('date_input','check_in').set_value(date(2026,10,24))
        self.widget('date_input','check_out').set_value(date(2026,10,23))
        self.at.button(key='next_Hotel').click().run()
        self.clean()
        self.assertEqual(self.at.session_state['current_page'],'Hotel')
        errors=[m.value for m in self.at.error]
        self.assertIn('Select at least one room.',errors)
        self.assertIn('The check-out date must be after the check-in date.',errors)
        self.page('Complete')
        self.assertEqual(self.at.session_state['current_page'],'Complete')
        self.assertTrue(next(b for b in self.at.button if b.label=='Submit Booking Request').disabled)
        self.page('Hotel')
        self.at.button(key='back_Hotel').click().run()
        self.assertEqual(self.at.session_state['current_page'],'Personal')
        self.page('Hotel')
        self.assertEqual(self.widget('date_input','check_out').value,date(2026,10,23))
        self.assertEqual(self.widget('number_input','rq_Tiba Rose El Golf_Single').value,0)
        self.widget('number_input','rq_Tiba Rose El Golf_Double').set_value(2)
        self.widget('date_input','check_out').set_value(date(2026,10,26))
        self.at.button(key='next_Hotel').click().run()
        self.clean()
        self.assertEqual(self.at.session_state['current_page'],'Transportation')

    def test_short_capacity_blocks_but_surplus_submits(self):
        ident=self.transport(); prefix=f'tr_{ident}_'
        self.widget('number_input',prefix+'v2').set_value(0)
        self.at.button(key='next_Transportation').click().run()
        self.clean()
        self.assertEqual(self.at.session_state['current_page'],'Transportation')
        self.assertTrue(any('10 remaining passengers' in m.value for m in self.at.error))
        self.page('Complete')
        self.assertEqual(self.at.session_state['current_page'],'Complete')
        self.assertTrue(next(b for b in self.at.button if b.label=='Submit Booking Request').disabled)
        self.page('Transportation')
        self.widget('number_input',prefix+'persons').set_value(40)
        self.at.button(key='next_Transportation').click().run()
        self.clean()
        self.assertEqual(self.at.session_state['current_page'],'Review')
        self.assertTrue(any('Passengers: 40 · Seats: 50' in m.value for m in self.at.markdown))
        with patch('sheets.backend_is_configured',return_value=True), patch('sheets.save_to_google_sheets',return_value=SaveResult(False,False,'Retry',{'error_code':'CONNECTION'})) as save:
            self.at.button(key='next_Review').click().run()
            next(b for b in self.at.button if b.label=='Submit Booking Request').click().run()
            self.clean()
            record=save.call_args.args[0]
            self.assertEqual(record['transport_services'][0]['persons'],40)
            self.assertEqual(record['transport_services'][0]['seats'],50)
            self.assertEqual(record['transport_total_eur'],190)

    def test_hidden_transport_and_hotel_choices_keep_their_drafts(self):
        ident=self.transport(); prefix=f'tr_{ident}_'
        self.widget('selectbox',prefix+'date_mode').select('Date range').run()
        self.widget('date_input',prefix+'range_start').set_value(date(2026,10,1))
        self.widget('date_input',prefix+'range_end').set_value(date(2026,10,12)).run()
        self.widget('checkbox','wants_transportation').uncheck().run()
        self.page('Review'); self.page('Transportation')
        self.widget('checkbox','wants_transportation').check().run()
        self.clean()
        self.assertEqual(self.at.session_state['transport_ids'],[ident])
        self.assertEqual(self.widget('number_input',prefix+'persons').value,60)
        self.assertEqual(self.widget('number_input',prefix+'v4').value,1)
        self.assertEqual(self.widget('date_input',prefix+'range_end').value,date(2026,10,12))
        self.widget('selectbox',prefix+'date_mode').select('One date').run()
        self.page('Hotel')
        self.widget('number_input','rq_Tiba Rose El Golf_Double').set_value(3).run()
        self.widget('selectbox','hotel').select('Baron Hotel Cairo').run()
        self.widget('selectbox','hotel').select('Tiba Rose El Golf').run()
        self.assertEqual(self.widget('number_input','rq_Tiba Rose El Golf_Double').value,3)
        self.page('Transportation')
        self.widget('selectbox',prefix+'date_mode').select('Date range').run()
        self.assertEqual(self.widget('date_input',prefix+'range_end').value,date(2026,10,12))

    def test_cleared_dates_show_errors_without_crashing(self):
        self.ready(); self.page('Hotel')
        self.widget('date_input','check_in').set_value(None)
        self.widget('date_input','check_out').set_value(None)
        self.at.button(key='next_Hotel').click().run()
        self.clean()
        self.assertEqual(self.at.session_state['current_page'],'Hotel')
        self.assertIn('Please enter a valid check-in date.',[m.value for m in self.at.error])
        self.assertIn('Please enter a valid check-out date.',[m.value for m in self.at.error])

    def transport(self):
        self.ready()
        self.page('Transportation')
        self.widget('checkbox', key='wants_transportation').check().run()
        ident=self.at.session_state['transport_ids'][0]
        self.widget('number_input', key=f'tr_{ident}_persons').set_value(60).run()
        self.widget('number_input', key=f'tr_{ident}_v4').set_value(1).run()
        self.widget('number_input', key=f'tr_{ident}_v2').set_value(1).run()
        return ident

    def test_daily_end_choices_respect_8_12_hours_and_detect_next_day(self):
        ident=self.transport(); prefix=f'tr_{ident}_'
        self.widget('selectbox', key=prefix+'service').select('Daily 8 Hours').run()
        self.clean()
        self.assertEqual(self.widget('selectbox', key=prefix+'end').value,time(17,0))
        self.assertNotIn('18:00',self.widget('selectbox', key=prefix+'end').options)
        self.assertNotIn(prefix+'next_day',[item.key for item in self.at.checkbox])
        self.widget('time_input', key=prefix+'start').set_value(time(20,0)).run()
        self.clean()
        self.assertEqual(self.widget('selectbox', key=prefix+'end').value,time(4,0))
        self.assertTrue(self.at.session_state[prefix+'next_day'])
        self.assertNotIn('05:00 (next day)',self.widget('selectbox', key=prefix+'end').options)
        self.widget('selectbox', key=prefix+'service').select('Daily 12 Hours').run()
        self.clean()
        self.assertEqual(self.widget('selectbox', key=prefix+'end').value,time(8,0))
        self.assertNotIn('09:00 (next day)',self.widget('selectbox', key=prefix+'end').options)
        self.widget('selectbox', key=prefix+'service').select('Daily 8 Hours').run()
        self.assertEqual(self.widget('selectbox', key=prefix+'end').value,time(4,0))
        self.page('Review'); self.page('Transportation')
        self.assertEqual(self.widget('selectbox', key=prefix+'end').value,time(4,0))
        self.widget('selectbox', key=prefix+'service').select('Airport Transfer').run()
        self.widget('time_input', key=prefix+'start').set_value(time(23,0)).run()
        self.widget('time_input', key=prefix+'end').set_value(time(1,0)).run()
        self.clean()
        self.assertTrue(self.at.session_state[prefix+'next_day'])
        self.widget('time_input', key=prefix+'end').set_value(time(23,30)).run()
        self.assertFalse(self.at.session_state[prefix+'next_day'])

    def test_twelve_dates_single_template_totals_payload_and_retry(self):
        ident=self.transport(); prefix=f'tr_{ident}_'
        self.widget('selectbox', key=prefix+'date_mode').set_value('Date range').run()
        self.widget('date_input', key=prefix+'range_start').set_value(date(2026,10,1)).run()
        self.widget('date_input', key=prefix+'range_end').set_value(date(2026,10,12)).run()
        self.clean()
        self.assertTrue(any('12 date(s) × €250.00' in item.value and '€3,000.00' in item.value for item in self.at.info))
        # Still only one time pair and one group of vehicle inputs, not 12 forms.
        self.assertEqual(len(self.at.time_input),2)
        self.assertEqual(len(self.at.number_input),6)
        self.page('Review'); self.page('Transportation')
        self.assertEqual(self.widget('date_input', key=prefix+'range_end').value,date(2026,10,12))
        self.widget('multiselect', key=prefix+'excluded_dates').set_value([date(2026,10,5)]).run()
        self.clean()
        self.assertTrue(any('11 date(s) × €250.00' in item.value and '€2,750.00' in item.value for item in self.at.info))
        self.at.button(key='action_duplicate_'+ident).click().run()
        self.clean()
        clone=self.at.session_state['transport_ids'][1]
        self.widget('selectbox', key=f'tr_{clone}_direction').select('Hotel to Airport').run()
        self.assertEqual(self.widget('selectbox', key=prefix+'direction').value,'Airport to Hotel')
        self.assertEqual(self.widget('multiselect', key=f'tr_{clone}_excluded_dates').value,[date(2026,10,5)])
        self.page('Personal')
        self.widget('text_input', key='federation_name').input('TEST FEDERATION').run()
        self.widget('selectbox', key='federation_country').select('Egypt').run()
        self.widget('text_input', key='federation_email').input('example@example.com').run()
        self.widget('text_input', key='federation_phone').input('+201012345678').run()
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
        self.widget('selectbox', key=prefix+'date_mode').set_value('Specific dates').run()
        self.widget('date_input', key=prefix+'pick_date').set_value(date(2026,10,3)).run()
        self.at.button(key='action_add_date_'+ident).click().run()
        self.at.button(key='action_add_date_'+ident).click().run()
        self.assertEqual(len(self.widget('multiselect', key=prefix+'selected_dates').value),1)
        self.widget('date_input', key=prefix+'pick_date').set_value(date(2026,10,8)).run()
        self.at.button(key='action_add_date_'+ident).click().run()
        self.clean()
        self.page('Review'); self.page('Transportation')
        self.assertEqual(self.widget('multiselect', key=prefix+'selected_dates').value,[date(2026,10,3),date(2026,10,8)])
        self.widget('multiselect', key=prefix+'selected_dates').set_value([date(2026,10,8)]).run()
        self.assertTrue(any('1 date(s) × €250.00' in item.value for item in self.at.info))

    def test_invalid_schedule_never_crashes_other_steps_or_submits(self):
        ident=self.transport(); prefix=f'tr_{ident}_'
        self.widget('selectbox', key=prefix+'date_mode').set_value('Specific dates').run()
        for name in ('Personal','Hotel','Review','Complete'):
            self.page(name)
            self.assertEqual(self.at.session_state['current_page'], name)
        self.assertTrue(next(b for b in self.at.button if b.label=='Submit Booking Request').disabled)
        self.assertTrue(any('Select at least one date' in item.value for item in self.at.error))
        self.page('Transportation')
        self.at.button(key='next_Transportation').click().run()
        self.clean()
        self.assertEqual(self.at.session_state['current_page'], 'Transportation')

    def test_preview_tabs_never_submit_even_when_backend_configured(self):
        self.choose()
        self.widget('text_input','federation_name').input('PREVIEW DRAFT')
        with patch('sheets.backend_is_configured',return_value=True), patch('sheets.save_to_google_sheets') as save:
            for name in ('Hotel','Transportation','Review','Complete','Personal'):
                self.page(name)
                self.assertEqual(self.at.session_state['current_page'],name)
                if name=='Complete':
                    self.assertTrue(next(b for b in self.at.button if b.label=='Submit Booking Request').disabled)
            save.assert_not_called()
        self.assertEqual(self.widget('text_input','federation_name').value,'PREVIEW DRAFT')

    def test_next_checks_missing_earlier_steps_after_preview_jump(self):
        self.choose()
        self.page('Review')
        self.at.button(key='next_Review').click().run()
        self.clean()
        self.assertEqual(self.at.session_state['current_page'],'Personal')
        self.assertIn('Federation name is required.',[m.value for m in self.at.error])
        self.page('Review')
        self.assertEqual(self.at.session_state['current_page'],'Review')

    def test_federation_without_phone_can_next_and_submit(self):
        self.choose()
        phone=self.widget('text_input','federation_phone')
        self.assertEqual(phone.value,'')
        self.assertIn('optional',phone.label)
        self.assertNotIn('*',phone.label)
        self.widget('text_input','federation_name').input('NO PHONE FEDERATION')
        self.widget('selectbox','federation_country').select('Egypt')
        self.widget('text_input','federation_email').input('example@example.com')
        self.at.button(key='next_Personal').click().run()
        self.clean()
        self.assertEqual(self.at.session_state['current_page'],'Hotel')
        self.at.button(key='next_Hotel').click().run()
        self.at.button(key='next_Transportation').click().run()
        self.at.button(key='next_Review').click().run()
        self.clean()
        self.assertEqual(self.at.session_state['current_page'],'Complete')
        with patch('sheets.backend_is_configured',return_value=True), patch('sheets.save_to_google_sheets',return_value=SaveResult(False,False,'Retry',{'error_code':'CONNECTION'})) as save:
            self.at.run()
            submit=next(b for b in self.at.button if b.label=='Submit Booking Request')
            self.assertFalse(submit.disabled)
            submit.click().run()
            self.clean()
            self.assertEqual(save.call_args.args[0]['phone'],'')
            self.assertFalse(save.call_args.args[0]['phone_valid'])

    def test_optional_phone_invalid_if_provided_individual_still_required(self):
        self.ready()
        self.widget('text_input','federation_phone').input('abc')
        self.at.button(key='next_Personal').click().run()
        self.clean()
        self.assertEqual(self.at.session_state['current_page'],'Personal')
        self.assertTrue(any('international phone' in m.value for m in self.at.error))
        # A preview does not erase or silently treat an invalid value as blank.
        self.page('Complete')
        self.assertTrue(next(b for b in self.at.button if b.label=='Submit Booking Request').disabled)
        self.page('Personal')
        self.assertEqual(self.widget('text_input','federation_phone').value,'abc')
        self.widget('text_input','federation_phone').input('')
        self.at.button(key='next_Personal').click().run()
        self.assertEqual(self.at.session_state['current_page'],'Hotel')
        self.page('Registration'); self.ready('Individual')
        self.widget('text_input','individual_phone').input('')
        self.at.button(key='next_Personal').click().run()
        self.clean()
        self.assertEqual(self.at.session_state['current_page'],'Personal')
        self.assertTrue(any('international phone' in m.value for m in self.at.error))

    def managed_fixture(self, kind='Federation', repeated=False):
        from test_request import example, service
        from helpers import calculate_booking_totals
        b=example(kind)
        if repeated:
            b['transport_services']=[dict(service(),date=f'2026-10-{day:02d}') for day in range(1,13)]
            b['transport_services'].append(service())
        b.update(calculate_booking_totals(b))
        b.update(revision=1,invoice_no='INV-20260830-ABCDEF123456',invoice_verification_code='TEST-CODE')
        self.at.session_state['current_page']='Manage'
        self.at.session_state['manage_token']='test-private-grant'
        self.at.session_state['manage_verified_id']=b['booking_id']
        self.at.session_state['managed_request']={'ok':True,'saved':True,'booking':b,'revision':1,'editable':True,
            'status':'Received','invoice_created':True,'customer_email_sent':True}
        self.at.run();self.clean()
        return b

    def test_details_label_and_existing_request_entry(self):
        self.at.button(key='manage_existing').click().run();self.clean()
        self.assertEqual(self.at.session_state['current_page'],'Manage')
        self.assertTrue(any(w.label=='Request ID' for w in self.at.text_input))
        self.at.button(key='manage_back').click().run();self.choose()
        self.assertEqual(self.at.button(key='nav_Personal').label,'Details')

    def test_edit_restores_federation_and_repeated_dates(self):
        b=self.managed_fixture(repeated=True)
        self.at.button(key='manage_start_edit').click().run();self.clean()
        self.assertEqual(self.widget('text_input','federation_name').value,b['federation_name'])
        self.assertTrue(self.widget('text_input','federation_email').disabled)
        self.assertEqual(self.at.session_state['edit_original']['booking_id'],b['booking_id'])
        self.page('Hotel')
        self.assertEqual(self.widget('number_input','rq_Tiba Rose El Golf_Double').value,1)
        self.assertEqual(self.widget('number_input','rq_Tiba Rose El Golf_Single').value,0)
        self.page('Transportation')
        self.assertEqual(len(self.at.session_state['transport_ids']),1)
        ident=self.at.session_state['transport_ids'][0]
        self.assertEqual(len(self.at.session_state[f'tr_{ident}_selected_dates']),13)
        self.page('Review')
        self.assertTrue(any('€3,350.00' in m.value for m in self.at.markdown))

    def test_amendment_submit_retries_same_id_operation_revision(self):
        b=self.managed_fixture()
        self.at.button(key='manage_start_edit').click().run()
        self.widget('text_input','federation_name').input('UPDATED FEDERATION').run()
        self.page('Complete')
        calls=[]
        def save(record,edit_context=None):
            import copy
            calls.append((copy.deepcopy(record),copy.deepcopy(edit_context)))
            if len(calls)==1:
                return SaveResult(ok=False,message='No final response',data={'error_code':'CONNECTION'})
            return SaveResult(ok=True,saved=True,data={'invoice_no':'INV-20260830-ABCDEF123456-R2','revision':2,
                'invoice_created':True,'customer_email_sent':True})
        with patch('sheets.backend_is_configured',return_value=True),patch('sheets.save_to_google_sheets',side_effect=save):
            self.at.run()
            next(w for w in self.at.button if w.label=='Save Changes & Send Updated PDF').click().run();self.clean()
            next(w for w in self.at.button if w.label=='Retry saving').click().run();self.clean()
        self.assertEqual(calls[0],calls[1])
        self.assertEqual(calls[0][0]['booking_id'],b['booking_id'])
        self.assertEqual(calls[0][0]['revision'],2)
        self.assertEqual(calls[0][1]['expected_revision'],1)
        self.assertTrue(any('updated successfully' in m.value for m in self.at.success))

    def test_individual_edit_restores_passport_and_dates(self):
        b=self.managed_fixture('Individual')
        self.at.button(key='manage_start_edit').click().run();self.clean()
        self.assertEqual(self.widget('text_input','passport_number').value,b['passport_number'])
        self.assertEqual(self.widget('date_input','date_of_birth').value,date(1996,3,21))
        self.assertTrue(self.widget('text_input','individual_email').disabled)
        self.page('Hotel');self.page('Personal')
        self.assertEqual(self.widget('text_input','guest_name').value,b['guest_name'])

    def test_loading_does_not_drop_two_services_on_same_date(self):
        import copy
        from helpers import calculate_booking_totals
        self.managed_fixture(repeated=True)
        response=copy.deepcopy(self.at.session_state['managed_request'])
        response['booking']['transport_services'].append(copy.deepcopy(response['booking']['transport_services'][0]))
        response['booking'].update(calculate_booking_totals(response['booking']))
        self.at.session_state['managed_request']=response
        self.at.run()
        self.at.button(key='manage_start_edit').click().run();self.clean()
        self.page('Transportation')
        self.assertEqual(len(self.at.session_state['transport_ids']),2)
        self.page('Review')
        self.assertTrue(any('€3,600.00' in m.value for m in self.at.markdown))

    def test_existing_request_requires_code_before_load(self):
        from test_request import example
        from helpers import calculate_booking_totals
        b=example();b.update(calculate_booking_totals(b));b['invoice_no']='INV-TEST'
        self.at.button(key='manage_existing').click().run()
        self.at.text_input(key='manage_id').input(b['booking_id'])
        self.at.text_input(key='manage_email').input(b['email'])
        reply={'ok':True,'booking':b,'revision':1,'editable':True,'status':'Received','invoice_created':True,'customer_email_sent':True}
        with patch('sheets.backend_is_configured',return_value=True),patch('sheets.request_edit_code',return_value={'ok':True,'message':'Code sent'}) as send,patch('sheets.verify_edit_code',return_value={'ok':True,'edit_token':'private'}) as verify,patch('sheets.load_request',return_value=reply) as load:
            self.at.run()
            next(w for w in self.at.button if w.label=='Send verification code').click().run();self.clean()
            send.assert_called_once();load.assert_not_called()
            next(w for w in self.at.text_input if w.label=='Email verification code').input('12345678')
            next(w for w in self.at.button if w.label=='Verify & open request').click().run();self.clean()
            verify.assert_called_once_with(b['booking_id'],b['email'],'12345678')
            load.assert_called_once_with(b['booking_id'],'private')
            self.assertTrue(any(w.key=='manage_start_edit' for w in self.at.button))

if __name__=='__main__': unittest.main()
