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
    TRANSPORT_PRICING_LABELS,
    TRANSPORT_RATE_VERSION,
    TRANSPORT_SERVICES,
    TRANSPORTATION,
)


MONEY = Decimal("0.01")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PASSPORT_NUMBER_RE = re.compile(r"^[A-Z0-9]{5,20}$")


def normalize_guest_name(value: Any) -> str:
    """Match the passport style: trimmed, single-spaced and uppercase."""

    return re.sub(r"\s+", " ", str(value or "").strip()).upper()


def normalize_passport_number(value: Any) -> str:
    """Return one canonical value for reliable duplicate detection."""

    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


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


def transportation_unit_price_eur(
    vehicle_type: str | None,
    service: str | None,
    pricing_mode: str | None,
) -> float | None:
    """Return the configured EUR unit rate for one vehicle or one person."""

    if not vehicle_type or not service or not pricing_mode:
        return None
    try:
        vehicle = TRANSPORTATION[vehicle_type]
        if pricing_mode not in vehicle["pricing_modes"]:
            return None
        value = vehicle["prices_eur"][service]
        return None if value is None else float(value)
    except (KeyError, TypeError, ValueError):
        return None


def calculate_transportation_total(
    wants_transportation: bool,
    vehicle_type: str | None,
    service: str | None,
    pricing_mode: str | None,
    persons: int,
    vehicle_count: int = 1,
) -> dict[str, float | int | str | bool | None]:
    """Calculate transport from the official EGP table.

    The Limousine is billed by vehicle quantity.  Every bus is billed per
    person using the preliminary seat rate configured in ``config.py``.
    """

    if not wants_transportation:
        return {
            "transport_unit_price_egp": 0.0,
            "transport_unit_price_eur": 0.0,
            "transport_price_per_person_eur": 0.0,
            "transport_billed_units": 0,
            "transport_pricing_label": "Not requested",
            "transport_price_pending": False,
            "transport_total_eur": 0.0,
            "transport_total_egp": 0.0,
            "transport_rate_version": TRANSPORT_RATE_VERSION,
        }

    unit_price_eur = transportation_unit_price_eur(vehicle_type, service, pricing_mode)
    billed_units = max(int(persons), 0) if pricing_mode == "per_person" else max(int(vehicle_count), 0)
    pricing_label = TRANSPORT_PRICING_LABELS.get(str(pricing_mode), "Unknown")
    if unit_price_eur is None:
        return {
            "transport_unit_price_egp": None,
            "transport_unit_price_eur": None,
            "transport_price_per_person_eur": None,
            "transport_billed_units": billed_units,
            "transport_pricing_label": pricing_label,
            "transport_price_pending": True,
            "transport_total_eur": 0.0,
            "transport_total_egp": 0.0,
            "transport_rate_version": TRANSPORT_RATE_VERSION,
        }

    eur_to_egp = float(CURRENCY_RATES["EUR_TO_EGP"])
    total_eur = _money(unit_price_eur * billed_units)
    unit_price_egp = _money(unit_price_eur * eur_to_egp)
    total_egp = _money(total_eur * eur_to_egp)
    return {
        "transport_unit_price_egp": unit_price_egp,
        "transport_unit_price_eur": round(float(unit_price_eur), 6),
        "transport_price_per_person_eur": (
            round(float(unit_price_eur), 6) if pricing_mode == "per_person" else 0.0
        ),
        "transport_billed_units": billed_units,
        "transport_pricing_label": pricing_label,
        "transport_price_pending": False,
        "transport_total_eur": total_eur,
        "transport_total_egp": total_egp,
        "transport_rate_version": TRANSPORT_RATE_VERSION,
    }


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
    transport_service: str | None = None,
    transport_pricing_mode: str | None = None,
    transport_vehicle_count: int = 1,
) -> dict[str, float | int | str | bool | None]:
    room_total_eur = calculate_room_total(hotel, meal_plan, room_type, nights)
    transport = calculate_transportation_total(
        wants_transportation,
        vehicle_type,
        transport_service,
        transport_pricing_mode,
        transport_persons,
        transport_vehicle_count,
    )
    transport_total_eur = float(transport["transport_total_eur"])
    grand_total_eur = _money(room_total_eur + transport_total_eur)
    room_total_egp = convert_currency(room_total_eur, "EGP")
    result = {
        "nightly_rate_eur": _money(get_hotel_rate(hotel, meal_plan, room_type)),
        "room_total_eur": room_total_eur,
        "grand_total_eur": grand_total_eur,
        "grand_total_usd": convert_currency(grand_total_eur, "USD"),
        "grand_total_egp": _money(room_total_egp + float(transport["transport_total_egp"])),
    }
    result.update(transport)
    return result


def format_currency(amount: float, currency: str) -> str:
    symbols = {"EUR": "€", "USD": "$", "EGP": "EGP "}
    code = currency.upper()
    symbol = symbols.get(code, f"{code} ")
    return f"{symbol}{float(amount):,.2f}"


def validate_booking(booking: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if not normalize_guest_name(booking.get("guest_name")):
        errors.append("Full name is required.")
    if not str(booking.get("nationality", "")).strip():
        errors.append("Nationality is required.")
    passport_number = normalize_passport_number(booking.get("passport_number"))
    if not PASSPORT_NUMBER_RE.fullmatch(passport_number):
        errors.append("Passport number must contain 5 to 20 letters or numbers.")
    try:
        date_of_birth = booking.get("date_of_birth")
        if isinstance(date_of_birth, str):
            date_of_birth = date.fromisoformat(date_of_birth)
        if not isinstance(date_of_birth, date):
            raise ValueError
        if date_of_birth < date(1900, 1, 1) or date_of_birth > date.today():
            raise ValueError
    except (TypeError, ValueError):
        errors.append("Please enter a valid date of birth.")
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
        vehicle_type = booking.get("vehicle_type")
        if vehicle_type not in TRANSPORTATION:
            errors.append("Please select a valid transportation option.")
            vehicle = None
        else:
            vehicle = TRANSPORTATION[str(vehicle_type)]
        if booking.get("transport_service") not in TRANSPORT_SERVICES:
            errors.append("Please select a valid transportation service.")
        pricing_mode = booking.get("transport_pricing_mode")
        if vehicle and pricing_mode not in vehicle.get("pricing_modes", ()):
            errors.append("Please select a valid transportation pricing method.")
        try:
            if int(booking.get("transport_persons", 0)) < 1:
                raise ValueError
        except (TypeError, ValueError):
            errors.append("Please enter the number of persons using transportation.")
        if pricing_mode == "per_vehicle":
            try:
                if int(booking.get("transport_vehicle_count", 0)) < 1:
                    raise ValueError
            except (TypeError, ValueError):
                errors.append("Please enter the number of vehicles required.")
        if booking.get("transport_price_pending"):
            errors.append(
                "Transportation price is pending. Add the official rate in config.py before confirmation."
            )

    return errors


def generate_booking_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"ITKF-{stamp}-{uuid.uuid4().hex[:8].upper()}"


def current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
# Force Streamlit deployment refresh
