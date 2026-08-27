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

    def test_hiace_is_billed_per_person_using_15_seats(self):
        totals = calculate_booking_totals(
            "Hilton Cairo Heliopolis",
            "Breakfast",
            "Double",
            3,
            True,
            "Hiace (15 Seats)",
            transport_persons=3,
            transport_service="Full Day Within Cairo",
            transport_pricing_mode="per_person",
        )
        self.assertEqual(totals["transport_unit_price_eur"], 6.666667)
        self.assertEqual(totals["transport_total_egp"], 1120.0)
        self.assertEqual(totals["transport_total_eur"], 20.0)
        self.assertEqual(totals["grand_total_eur"], 350.0)

    def test_limousine_is_billed_by_vehicle(self):
        totals = calculate_booking_totals(
            "Hilton Cairo Heliopolis",
            "Breakfast",
            "Double",
            1,
            True,
            "Limousine",
            transport_persons=2,
            transport_service="One-way Transfer - Airport to Stadium or Hotel",
            transport_pricing_mode="per_vehicle",
            transport_vehicle_count=2,
        )
        self.assertFalse(totals["transport_price_pending"])
        self.assertEqual(totals["transport_unit_price_eur"], 23.214286)
        self.assertEqual(totals["transport_total_eur"], 46.43)

    def test_coaster_is_billed_per_person_using_30_seats(self):
        totals = calculate_booking_totals(
            "Hilton Cairo Heliopolis",
            "Breakfast",
            "Double",
            1,
            True,
            "Coaster (30 Seats)",
            transport_persons=30,
            transport_service="One-way Transfer - Airport to Stadium or Hotel",
            transport_pricing_mode="per_person",
        )
        self.assertEqual(totals["transport_unit_price_eur"], 1.815476)
        self.assertEqual(totals["transport_total_eur"], 54.46)

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
