"""Pure EUR request validation and pricing. No images and no currency conversion."""
from __future__ import annotations
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from config import HOTELS, ROOM_OCCUPANCY, MAX_BOOKING_NIGHTS, MAX_TRANSPORT_SERVICES, TRANSPORTATION, TRANSPORT_SERVICES, TRANSPORT_RATE_VERSION

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PASSPORT_NUMBER_RE = re.compile(r"^[A-Z0-9]{5,20}$")

def normalize_guest_name(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).upper()

def normalize_passport_number(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())

def money(value: Any) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

def positive_int(value: Any, label: str, maximum: int = 5000, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or not re.fullmatch(r"\d+", str(value)):
        raise ValueError(f"{label} must be a whole number.")
    result = int(value)
    if result < (0 if allow_zero else 1) or result > maximum:
        raise ValueError(f"Invalid {label.lower()}.")
    return result

def iso_date(value: Any) -> date:
    if isinstance(value, datetime):
        raise ValueError("Use a date without a time.")
    if isinstance(value, date):
        return value
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value)):
        raise ValueError("Use a valid date.")
    return date.fromisoformat(value)

def calculate_nights(check_in: Any, check_out: Any) -> int:
    return max((iso_date(check_out) - iso_date(check_in)).days, 0)

def stay_dates(check_in: Any, check_out: Any) -> list[str]:
    first = iso_date(check_in)
    nights = calculate_nights(check_in, check_out)
    if not 1 <= nights <= MAX_BOOKING_NIGHTS:
        raise ValueError(f"Stay must be between 1 and {MAX_BOOKING_NIGHTS} nights.")
    return [(first + timedelta(days=i)).isoformat() for i in range(nights)]

def time_minutes(value: Any) -> int:
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", str(value)):
        raise ValueError("Choose a valid start and end time.")
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute

def service_duration(item: dict) -> int:
    minutes = time_minutes(item.get("end_time")) - time_minutes(item.get("start_time"))
    if item.get("ends_next_day") is True:
        minutes += 1440
    if not 0 < minutes <= 1440:
        raise ValueError("End time must follow start time; select next day if needed.")
    return minutes

def vehicle_suggestions(remaining: int) -> list[str]:
    """Suggest single vehicles that fit the remaining passengers; never add one."""
    return [name for name, v in sorted(TRANSPORTATION.items(), key=lambda pair: pair[1]["capacity"])
            if v["capacity"] >= remaining]

def price_transport_service(item: dict) -> dict:
    service = str(item.get("service", ""))
    if service not in TRANSPORT_SERVICES:
        raise ValueError("Choose a valid transportation service.")
    iso_date(item.get("date"))
    duration = service_duration(item)
    limit = TRANSPORT_SERVICES[service]["max_hours"]
    if limit and duration > limit * 60:
        raise ValueError(f"{service} allows up to {limit} hours. Choose the appropriate service.")
    directions = TRANSPORT_SERVICES[service]["directions"]
    if directions and item.get("direction") not in directions:
        raise ValueError("Choose the transfer direction.")
    persons = positive_int(item.get("persons"), "Number of passengers")
    selected = item.get("vehicles")
    if not isinstance(selected, dict) or any(name not in TRANSPORTATION for name in selected):
        raise ValueError("Choose valid vehicles.")
    lines = []
    seats = total = 0
    for name, raw in selected.items():
        qty = positive_int(raw, "Vehicle quantity", maximum=100, allow_zero=True)
        if not qty:
            continue
        v = TRANSPORTATION[name]
        unit = v["prices_eur"][service]
        lines.append({"vehicle": name, "quantity": qty, "unit_price_eur": unit, "total_eur": money(qty * unit)})
        seats += qty * v["capacity"]
        total += qty * unit
    return {**item, "duration_minutes": duration, "persons": persons, "seats": seats,
            "remaining": max(persons - seats, 0), "vehicle_lines": lines, "total_eur": money(total)}

def calculate_booking_totals(booking: dict) -> dict:
    hotel = HOTELS.get(booking.get("hotel"), {})
    rates = hotel.get("rates", {}).get(booking.get("meal_plan"), {})
    if not rates:
        raise ValueError("Choose a valid hotel and meal plan.")
    nights = len(stay_dates(booking.get("check_in"), booking.get("check_out")))
    rooms = booking.get("rooms")
    if not isinstance(rooms, list) or not rooms or len(rooms) > len(rates):
        raise ValueError("Select at least one room.")
    room_lines, seen = [], set()
    guests = count = subtotal = 0
    for item in rooms:
        room = item.get("room_type")
        if room not in rates or room in seen:
            raise ValueError("Choose valid, distinct room types.")
        seen.add(room)
        qty = positive_int(item.get("quantity"), "Number of rooms")
        unit = rates[room]
        # Preserve the existing hotel's rate basis; add quantity as a multiplier.
        line_total = money(unit * qty * nights)
        room_lines.append({"room_type": room, "quantity": qty, "unit_rate_eur": unit, "total_eur": line_total})
        guests += ROOM_OCCUPANCY[room] * qty
        count += qty
        subtotal += line_total
    if booking.get("registration_type") == "Individual" and count != 1:
        raise ValueError("Individual registration allows one room. Use Federation for multiple rooms.")
    services = booking.get("transport_services", [])
    if not isinstance(services, list) or len(services) > MAX_TRANSPORT_SERVICES:
        raise ValueError("Too many transportation services.")
    priced_services = [price_transport_service(item) for item in services]
    total_transport = money(sum(item["total_eur"] for item in priced_services))
    return {"nights": nights, "rooms": room_lines, "room_count": count, "guests": guests,
            "room_total_eur": money(subtotal), "transport_services": priced_services,
            "transport_total_eur": total_transport, "grand_total_eur": money(subtotal + total_transport),
            "transport_rate_version": TRANSPORT_RATE_VERSION}

def validate_booking(booking: dict[str, Any]) -> list[str]:
    errors = []
    kind = booking.get("registration_type")
    if kind not in ("Individual", "Federation"):
        errors.append("Choose Individual or Federation registration.")
    field = "federation_name" if kind == "Federation" else "guest_name"
    if not str(booking.get(field, "")).strip() or len(str(booking.get(field, ""))) > 150:
        errors.append("Enter a name of up to 150 characters.")
    if kind == "Individual":
        if not booking.get("nationality"):
            errors.append("Nationality is required.")
        if not PASSPORT_NUMBER_RE.fullmatch(normalize_passport_number(booking.get("passport_number"))):
            errors.append("Passport number must contain 5 to 20 letters or numbers.")
        try:
            dob = iso_date(booking.get("date_of_birth"))
            if not date(1900, 1, 1) <= dob <= date.today():
                raise ValueError()
        except (ValueError, TypeError):
            errors.append("Please enter a valid date of birth.")
    if not booking.get("phone_valid") or not re.fullmatch(r"\+[1-9]\d{6,14}", str(booking.get("phone", ""))):
        errors.append("Enter a valid international phone number, including the country code.")
    if not EMAIL_RE.fullmatch(str(booking.get("email", "")).strip()):
        errors.append("Enter a valid email address.")
    try:
        totals = calculate_booking_totals(booking)
        for index, service in enumerate(totals["transport_services"], 1):
            if service["remaining"]:
                errors.append(f"Transportation {index}: add seats for {service['remaining']} remaining passengers.")
    except (ValueError, TypeError, KeyError) as exc:
        errors.append(str(exc))
    return errors

def format_currency(amount: Any, currency: str = "EUR") -> str:
    if currency != "EUR":
        raise ValueError("Only EUR is supported.")
    return f"€{float(amount):,.2f}"

def generate_booking_id() -> str:
    return f"ITKF-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:12].upper()}"

def current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
