import unittest
from datetime import date

from config import HOTELS, ROOM_INVENTORY, TRANSPORTATION
from countries import country_for_code, validate_phone
from helpers import (
    calculate_booking_totals,
    calculate_nights,
    format_currency,
    normalize_guest_name,
    normalize_passport_number,
    price_transport_service,
    stay_dates,
    transport_schedule_dates,
)


def booking():
    return {
        "registration_type": "Federation",
        "federation_name": "TEST FEDERATION",
        "federation_country": "Egypt",
        "federation_country_code": "EG",
        "email": "test@example.com",
        "phone": "",
        "phone_valid": False,
        "hotel": "Tiba Rose El Golf",
        "meal_plan": "Breakfast",
        "check_in": "2026-10-24",
        "check_out": "2026-10-26",
        "rooms": [{"room_type": "Quadruple", "quantity": 2}],
        "transport_services": [],
    }


class BookingCalculationsTest(unittest.TestCase):
    def test_date_range_calculates_nights(self):
        self.assertEqual(calculate_nights(date(2026, 10, 10), date(2026, 10, 15)), 5)
        self.assertEqual(len(stay_dates("2026-10-10", "2026-10-15")), 5)

    def test_current_tiba_rates_and_inventory(self):
        self.assertEqual(HOTELS["Tiba Rose El Golf"]["rates"]["Breakfast"]["Quadruple"], 112.0)
        self.assertEqual(
            ROOM_INVENTORY["Tiba Rose El Golf"],
            {"Single": 30, "Double": 50, "Triple": 100, "Quadruple": 20},
        )

    def test_removed_and_added_hotels(self):
        self.assertNotIn("Hilton Cairo Heliopolis", HOTELS)
        self.assertNotIn("Sonesta Hotel Tower & Casino Cairo", HOTELS)
        self.assertEqual(
            HOTELS["Royal Marshal Hotel"]["rates"]["Breakfast"],
            {"Single": 47.5, "Double": 65.0},
        )

    def test_eur_only_room_totals(self):
        totals = calculate_booking_totals(booking())
        self.assertEqual(totals["nights"], 2)
        self.assertEqual(totals["room_count"], 2)
        self.assertEqual(totals["guests"], 8)
        self.assertEqual(totals["room_total_eur"], 448.0)
        self.assertEqual(totals["grand_total_eur"], 448.0)
        self.assertEqual(format_currency(448), "€448.00")
        with self.assertRaises(ValueError):
            format_currency(448, "USD")

    def test_transport_is_full_vehicle_pricing(self):
        item = {
            "date": "2026-10-24",
            "service": "Airport Transfer",
            "direction": "Airport to Hotel",
            "start_time": "09:00",
            "end_time": "10:00",
            "ends_next_day": False,
            "persons": 60,
            "vehicles": {"Bus (50 Seats)": 1, "Toyota Hiace (10 Seats)": 1},
        }
        priced = price_transport_service(item)
        self.assertEqual((priced["seats"], priced["remaining"], priced["total_eur"]), (60, 0, 250.0))

    def test_every_vehicle_has_all_current_services(self):
        self.assertEqual([v["capacity"] for v in TRANSPORTATION.values()], [3, 7, 10, 26, 50])
        self.assertTrue(all(len(v["prices_eur"]) == 4 for v in TRANSPORTATION.values()))

    def test_repeating_transport_dates_are_unique(self):
        self.assertEqual(
            transport_schedule_dates(
                "Specific dates",
                selected_dates=["2026-10-25", "2026-10-24", "2026-10-25"],
            ),
            ["2026-10-24", "2026-10-25"],
        )

    def test_names_and_passports_are_normalized(self):
        self.assertEqual(normalize_guest_name("  Alaa  Bahaa "), "ALAA BAHAA")
        self.assertEqual(normalize_passport_number("ab- 001234"), "AB001234")

    def test_egyptian_phone_is_normalized(self):
        egypt = country_for_code("EG")
        valid, value, _ = validate_phone(egypt.iso2, "01012345678")
        self.assertTrue(valid)
        self.assertEqual(value, "+201012345678")

    def test_reverse_stay_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "check-out date must be after"):
            stay_dates("2026-10-15", "2026-10-14")


if __name__ == "__main__":
    unittest.main()
