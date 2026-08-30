import copy
import io
import json
import subprocess
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from config import APP_SCHEMA_VERSION, HOTELS, TRANSPORTATION, SYSTEM_TITLE
from helpers import calculate_booking_totals, validate_booking, price_transport_service, normalize_guest_name, normalize_passport_number, vehicle_suggestions, transport_schedule_dates, stay_dates, transport_end_time_options, time_minutes
from countries import validate_phone
from pdf_generator import generate_pdf

ROOT = Path(__file__).resolve().parents[1]

def example(kind="Federation"):
    return {
        "schema_version": APP_SCHEMA_VERSION, "registration_type": kind,
        "booking_id": "ITKF-20260830-ABCDEF123456", "booking_date": "2026-08-30T15:00:00+00:00",
        "guest_name": "TEST GUEST" if kind == "Individual" else "",
        "federation_name": "TEST FEDERATION" if kind == "Federation" else "",
        "federation_country": "Egypt" if kind == "Federation" else "",
        "federation_country_code": "EG" if kind == "Federation" else "",
        "passport_number": "TEST12345" if kind == "Individual" else "",
        "date_of_birth": "1996-03-21" if kind == "Individual" else "",
        "nationality": "Egypt" if kind == "Individual" else "",
        "nationality_code": "EG" if kind == "Individual" else "",
        "email": "example@example.com", "phone": "+201012345678", "phone_valid": True,
        "hotel": "Tiba Rose El Golf", "meal_plan": "Breakfast",
        "check_in": "2026-10-24", "check_out": "2026-10-26",
        "rooms": [{"room_type": "Double", "quantity": 1}], "transport_services": []}

def service():
    return {"date": "2026-10-24", "service": "Airport Transfer", "direction": "Airport to Hotel",
            "start_time": "09:00", "end_time": "10:00", "ends_next_day": False, "persons": 60,
            "vehicles": {"Bus (50 Seats)": 1, "Toyota Hiace (10 Seats)": 1}}

class RequestTests(unittest.TestCase):
    def test_end_time_choices_enforce_package_limits(self):
        for hours, last, too_late in [(8,'04:00','05:00'),(12,'08:00','09:00')]:
            options=transport_end_time_options('20:00',hours)
            self.assertEqual(options[-1],last)
            self.assertNotIn(too_late,options)
            self.assertTrue(all(0 < (time_minutes(value)-time_minutes('20:00'))%1440 <= hours*60 for value in options))
        self.assertIn('10:07',transport_end_time_options('09:00',8,'10:07'))
        self.assertNotIn('18:01',transport_end_time_options('09:00',8,'18:01'))
    def test_federation_country_required_only_for_federations(self):
        b=example()
        b.pop('federation_country'); b.pop('federation_country_code')
        self.assertIn('Please select the federation country.',validate_booking(b))
        self.assertEqual(validate_booking(example('Individual')),[])
        b.update(federation_country='Germany',federation_country_code='DE')
        self.assertEqual(validate_booking(b),[])

    def test_checkout_message_and_maximum_stay_are_distinct(self):
        for end in ('2026-10-23','2026-10-24'):
            with self.assertRaisesRegex(ValueError,'^Check out date must be after check in date\\.$'):
                stay_dates('2026-10-24',end)
        with self.assertRaisesRegex(ValueError,'^Stay cannot exceed 60 nights\\.$'):
            stay_dates('2026-10-01','2026-12-01')
        self.assertEqual(stay_dates('2026-10-24','2026-10-25'),['2026-10-24'])
    def test_repeating_schedule_inclusive_range_and_exclusions(self):
        dates=transport_schedule_dates('Date range',start_date='2026-10-01',end_date='2026-10-12')
        self.assertEqual(len(dates),12)
        self.assertEqual((dates[0],dates[-1]),('2026-10-01','2026-10-12'))
        trimmed=transport_schedule_dates('Date range',start_date='2026-10-01',end_date='2026-10-12',excluded_dates=['2026-10-05'])
        self.assertEqual(len(trimmed),11); self.assertNotIn('2026-10-05',trimmed)
        b=example(); b['transport_services']=[dict(service(),date=day) for day in dates]
        self.assertEqual(calculate_booking_totals(b)['transport_total_eur'],3000)

    def test_repeating_dates_unique_sorted_and_validated(self):
        self.assertEqual(transport_schedule_dates('Specific dates',selected_dates=['2026-10-08','2026-10-03','2026-10-08']),['2026-10-03','2026-10-08'])
        for args in [dict(mode='Specific dates',selected_dates=[]),dict(mode='Date range',start_date='2026-10-12',end_date='2026-10-01'),dict(mode='Date range',start_date='2026-10-01',end_date='2026-12-31'),dict(mode='Date range',start_date='2026-10-01',end_date='2026-10-01',excluded_dates=['2026-10-01'])]:
            with self.assertRaises(ValueError): transport_schedule_dates(**args)

    def test_schedule_error_blocks_booking(self):
        b=example(); b['transport_schedule_error']='Choose service dates'
        self.assertIn('Choose service dates',validate_booking(b))

    def test_names(self):
        self.assertEqual(normalize_guest_name("  Alaa  Bahaa "), "ALAA BAHAA")
        self.assertEqual(normalize_passport_number("ab- 001234"), "AB001234")
    def test_exact_new_catalog(self):
        self.assertEqual([v["capacity"] for v in TRANSPORTATION.values()], [3,7,10,26,50])
        self.assertEqual([v["prices_eur"]["Daily 12 Hours"] for v in TRANSPORTATION.values()], [145,170,200,240,400])
    def test_no_photo_required_and_individual_single_room(self):
        b=example("Individual")
        self.assertEqual(validate_booking(b), [])
        b["rooms"][0]["quantity"]=2
        self.assertTrue(validate_booking(b))
    def test_federation_multi_room(self):
        b=example(); b["rooms"]=[{"room_type":"Double","quantity":3},{"room_type":"Single","quantity":2}]
        out=calculate_booking_totals(b)
        self.assertEqual(out["room_count"], 5)
        self.assertEqual(out["guests"], 8)
        self.assertEqual(out["grand_total_eur"], 620)
        self.assertEqual(validate_booking(b), [])
    def test_sixty_passengers(self):
        out=price_transport_service(service())
        self.assertEqual((out["seats"],out["remaining"],out["total_eur"]), (60,0,250))
        self.assertEqual(vehicle_suggestions(10)[0],"Toyota Hiace (10 Seats)")
    def test_capacity_shortage(self):
        b=example(); s=service(); s["vehicles"]={"Bus (50 Seats)":1}; b["transport_services"]=[s]
        self.assertIn("10 remaining", " ".join(validate_booking(b)))
    def test_multiple_days(self):
        b=example(); one=service(); two=copy.deepcopy(one); two["date"]="2026-10-25"
        b["transport_services"]=[one,two]
        self.assertEqual(calculate_booking_totals(b)["transport_total_eur"],500)
    def test_daily_packages_and_overnight(self):
        s=service(); s.update(service="Daily 8 Hours",direction="",start_time="20:00",end_time="04:00",ends_next_day=True)
        self.assertEqual(price_transport_service(s)["total_eur"],460)
        s["end_time"]="05:00"
        with self.assertRaises(ValueError): price_transport_service(s)
        s["service"]="Daily 12 Hours"
        self.assertEqual(price_transport_service(s)["total_eur"],600)
    def test_invalid_dates_and_counts(self):
        for key,value in [("check_in","2026-02-30"),("check_out","2026-10-24")]:
            b=example(); b[key]=value; self.assertTrue(validate_booking(b))
        b=example(); b["rooms"][0]["quantity"]=True
        self.assertTrue(validate_booking(b))
    def test_international_phone(self):
        self.assertTrue(validate_phone("EG", "+201012345678")[0])
        self.assertTrue(validate_phone("EG", "+447911123456")[0])
        self.assertFalse(validate_phone("EG", "+20")[0])
    def test_pdf_eur_and_protection(self):
        from pypdf import PdfReader
        b=example(); b["transport_services"]=[service()]; b.update(calculate_booking_totals(b))
        b.update(invoice_no="INV-20260830-ABCDEF123456",invoice_verification_code="TEST-TEST-TEST-TEST")
        data=generate_pdf(b)
        reader=PdfReader(io.BytesIO(data)); self.assertTrue(reader.is_encrypted); reader.decrypt("")
        text="\n".join(p.extract_text() for p in reader.pages)
        self.assertIn("EUR 350.00", text)
        self.assertNotIn("USD", text); self.assertNotIn("EGP",text)
        self.assertIn("TEST FEDERATION",text)
        self.assertIn("Federation Country",text)
        self.assertIn("Egypt",text)
        self.assertIn(SYSTEM_TITLE,text)
    def test_node_backend(self):
        b=example(); b["transport_services"]=[service()]; b.update(calculate_booking_totals(b))
        run=subprocess.run(["node",str(ROOT/"tests/test_backend.cjs")],input=json.dumps(b),text=True,capture_output=True)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        self.assertIn("PASS",run.stdout)

    def test_repeated_schedule_accepted_by_unchanged_backend(self):
        b=example()
        dates=transport_schedule_dates('Date range',start_date='2026-10-01',end_date='2026-10-12')
        b['transport_services']=[dict(service(),date=day) for day in dates]
        b.update(calculate_booking_totals(b))
        run=subprocess.run(['node',str(ROOT/'tests/test_backend.cjs')],input=json.dumps(b),text=True,capture_output=True)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        self.assertIn('PASS',run.stdout)

if __name__ == "__main__": unittest.main()
