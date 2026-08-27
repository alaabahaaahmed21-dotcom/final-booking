import unittest
from datetime import date

from config import HOTELS
from countries import country_for_code, validate_phone
from helpers import (
    calculate_booking_totals,
    calculate_nights,
    get_hotel_rate,
    validate_booking,
)


class BookingCalculationsTest(unittest.TestCase):
    def test_date_range_calculates_nights(self):
        self.assertEqual(calculate_nights(date(2026, 10, 10), date(2026, 10, 15)), 5)

    def test_official_tiba_rates(self):
        self.assertEqual(get_hotel_rate("Tiba Rose El Golf", "Breakfast", "Triple"), 45.0)
        self.assertEqual(get_hotel_rate("Tiba Rose El Golf", "Half Board", "Single"), 95.0)

    def test_official_jewel_full_board_rate(self):
        self.assertEqual(get_hotel_rate("Hotel Jewel Elnasr", "Full Board", "Triple"), 62.0)

    def test_eur_is_base_currency(self):
        totals = calculate_booking_totals(
            "Hilton Cairo Heliopolis", "Breakfast", "Double", 3, False, None
        )
        self.assertEqual(totals["room_total_eur"], 330.0)
        self.assertEqual(totals["grand_total_eur"], 330.0)
        self.assertGreater(totals["grand_total_usd"], totals["grand_total_eur"])

    def test_transport_is_price_per_person_in_eur(self):
        totals = calculate_booking_totals(
            "Hilton Cairo Heliopolis",
            "Breakfast",
            "Double",
            3,
            True,
            "Hiace Bus",
            4,
            {"Hiace Bus": 12.5},
        )
        self.assertEqual(totals["transport_price_per_person_eur"], 12.5)
        self.assertEqual(totals["transport_total_eur"], 50.0)
        self.assertEqual(totals["grand_total_eur"], 380.0)

    def test_transport_price_can_remain_pending(self):
        totals = calculate_booking_totals(
            "Hilton Cairo Heliopolis",
            "Breakfast",
            "Double",
            1,
            True,
            "Limousine",
            2,
            {"Limousine": None},
        )
        self.assertTrue(totals["transport_price_pending"])

    def test_egyptian_phone_is_normalized(self):
        egypt = country_for_code("EG")
        valid, value, _ = validate_phone(egypt.iso2, "01012345678")
        self.assertTrue(valid)
        self.assertEqual(value, "+201012345678")

    def test_every_official_hotel_has_rates(self):
        self.assertEqual(len(HOTELS), 9)
        self.assertTrue(all(hotel["rates"] for hotel in HOTELS.values()))

    def test_validation_rejects_reverse_dates(self):
        booking = {
            "guest_name": "Test Guest",
            "nationality": "Egyptian",
            "phone": "+201000000000",
            "email": "test@example.com",
            "personal_photo": None,
            "passport_photo": {"data": b"x"},
            "hotel": "Hilton Cairo Heliopolis",
            "meal_plan": "Breakfast",
            "room_type": "Double",
            "guests": 2,
            "check_in": date(2026, 10, 15),
            "check_out": date(2026, 10, 14),
            "wants_transportation": False,
        }
        self.assertTrue(any("Check-out" in error for error in validate_booking(booking)))


if __name__ == "__main__":
    unittest.main()
