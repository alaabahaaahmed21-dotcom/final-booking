"""Pure calculation, formatting and validation helpers."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from config import (
    CURRENCY_RATES,
    HOTELS,
    MAX_BOOKING_NIGHTS,
    REQUIRE_PASSPORT_PHOTO,
    REQUIRE_PERSONAL_PHOTO,
    ROOM_OCCUPANCY,
    TRANSPORTATION,
)


MONEY = Decimal("0.01")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _money(value: float | int | Decimal) -> float:
    return float(Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP))


def calculate_nights(check_in: date, check_out: date) -> int:
    """Return the number of hotel nights, or zero for an invalid range."""

    return max((check_out - check_in).days, 0)


def get_hotel_rate(hotel: str, meal_plan: str, room_type: str) -> float:
    try:
        return float(HOTELS[hotel]["rates"][meal_plan][room_type])
    except (KeyError, TypeError, ValueError):
        return 0.0


def calculate_room_total(
    hotel: str,
    meal_plan: str,
    room_type: str,
    nights: int,
) -> float:
    return _money(get_hotel_rate(hotel, meal_plan, room_type) * max(int(nights), 0))


def transportation_price_per_person_eur(
    vehicle_type: str | None,
    transport_rates: dict[str, float | None] | None = None,
) -> float | None:
    if not vehicle_type:
        return None
    if transport_rates is not None and vehicle_type in transport_rates:
        value = transport_rates[vehicle_type]
        return None if value is None else float(value)
    try:
        value = TRANSPORTATION[vehicle_type]["price_per_person_eur"]
        return None if value is None else float(value)
    except (KeyError, TypeError, ValueError):
        return None


def calculate_transportation_total(
    wants_transportation: bool,
    vehicle_type: str | None,
    persons: int,
    transport_rates: dict[str, float | None] | None = None,
) -> tuple[float, float | None, bool]:
    """Return (EUR total, EUR/person, price pending)."""

    if not wants_transportation:
        return 0.0, 0.0, False
    unit_price = transportation_price_per_person_eur(vehicle_type, transport_rates)
    if unit_price is None:
        return 0.0, None, True
    return _money(unit_price * max(int(persons), 0)), _money(unit_price), False


def convert_currency(amount_eur: float, target_currency: str) -> float:
    currency = target_currency.upper()
    if currency == "EUR":
        return _money(amount_eur)
    if currency == "USD":
        return _money(amount_eur * float(CURRENCY_RATES["EUR_TO_USD"]))
    if currency == "EGP":
        return _money(amount_eur * float(CURRENCY_RATES["EUR_TO_EGP"]))
    raise ValueError(f"Unsupported currency: {target_currency}")


def calculate_booking_totals(
    hotel: str,
    meal_plan: str,
    room_type: str,
    nights: int,
    wants_transportation: bool,
    vehicle_type: str | None,
    transport_persons: int = 0,
    transport_rates: dict[str, float | None] | None = None,
) -> dict[str, float | bool | None]:
    room_total_eur = calculate_room_total(hotel, meal_plan, room_type, nights)
    transport_total_eur, transport_price_per_person_eur, transport_price_pending = (
        calculate_transportation_total(
            wants_transportation, vehicle_type, transport_persons, transport_rates
        )
    )
    grand_total_eur = _money(room_total_eur + transport_total_eur)
    return {
        "nightly_rate_eur": _money(get_hotel_rate(hotel, meal_plan, room_type)),
        "room_total_eur": room_total_eur,
        "transport_price_per_person_eur": transport_price_per_person_eur,
        "transport_price_pending": transport_price_pending,
        "transport_total_eur": transport_total_eur,
        "transport_total_egp": convert_currency(transport_total_eur, "EGP"),
        "grand_total_eur": grand_total_eur,
        "grand_total_usd": convert_currency(grand_total_eur, "USD"),
        "grand_total_egp": convert_currency(grand_total_eur, "EGP"),
    }


def format_currency(amount: float, currency: str) -> str:
    symbols = {"EUR": "€", "USD": "$", "EGP": "EGP "}
    code = currency.upper()
    symbol = symbols.get(code, f"{code} ")
    return f"{symbol}{float(amount):,.2f}"


def validate_booking(booking: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if not str(booking.get("guest_name", "")).strip():
        errors.append("Full name is required.")
    if not str(booking.get("nationality", "")).strip():
        errors.append("Nationality is required.")
    if not booking.get("phone_valid") or not str(booking.get("phone", "")).startswith("+"):
        errors.append("Please enter a valid phone number for the selected country.")
    if not EMAIL_RE.match(str(booking.get("email", "")).strip()):
        errors.append("Please enter a valid email address.")

    if REQUIRE_PERSONAL_PHOTO and not booking.get("personal_photo"):
        errors.append("Personal photo is required.")
    if REQUIRE_PASSPORT_PHOTO and not booking.get("passport_photo"):
        errors.append("Passport photo is required.")

    hotel = booking.get("hotel")
    meal_plan = booking.get("meal_plan")
    room_type = booking.get("room_type")
    if hotel not in HOTELS:
        errors.append("Please select a valid hotel.")
    elif meal_plan not in HOTELS[hotel]["rates"]:
        errors.append("Please select a valid meal plan for this hotel.")
    elif room_type not in HOTELS[hotel]["rates"][meal_plan]:
        errors.append("Please select a valid room type for this hotel and meal plan.")

    try:
        check_in = booking.get("check_in")
        check_out = booking.get("check_out")
        if isinstance(check_in, str):
            check_in = date.fromisoformat(check_in)
        if isinstance(check_out, str):
            check_out = date.fromisoformat(check_out)
        nights = calculate_nights(check_in, check_out)
        if nights < 1:
            errors.append("Check-out date must be after check-in date.")
        elif nights > MAX_BOOKING_NIGHTS:
            errors.append(f"A booking cannot exceed {MAX_BOOKING_NIGHTS} nights.")
    except (TypeError, ValueError):
        errors.append("Please select valid check-in and check-out dates.")
        nights = 0

    try:
        guests = int(booking.get("guests", 0))
    except (TypeError, ValueError):
        guests = 0
    max_guests = ROOM_OCCUPANCY.get(str(room_type), 1)
    if guests < 1 or guests > max_guests:
        errors.append(f"The selected room accepts between 1 and {max_guests} guest(s).")

    if booking.get("wants_transportation"):
        if booking.get("vehicle_type") not in TRANSPORTATION:
            errors.append("Please select a valid transportation option.")
        try:
            if int(booking.get("transport_persons", 0)) < 1:
                raise ValueError
        except (TypeError, ValueError):
            errors.append("Please enter the number of persons using transportation.")
        if booking.get("transport_price_pending"):
            errors.append(
                "Transportation price is pending. Add the EUR price per person in config.py before confirmation."
            )

    return errors


def generate_booking_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"ITKF-{stamp}-{uuid.uuid4().hex[:8].upper()}"


def current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
