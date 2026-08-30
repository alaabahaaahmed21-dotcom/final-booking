"""Country dropdown and international phone-number validation."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import phonenumbers
import pycountry


@dataclass(frozen=True)
class Country:
    name: str
    iso2: str
    calling_code: str


@lru_cache(maxsize=1)
def countries() -> tuple[Country, ...]:
    values: list[Country] = []
    for iso2 in sorted(phonenumbers.SUPPORTED_REGIONS):
        item = pycountry.countries.get(alpha_2=iso2)
        if item is None:
            continue
        calling_code = phonenumbers.country_code_for_region(iso2)
        if not calling_code:
            continue
        values.append(Country(item.name, iso2, f"+{calling_code}"))
    return tuple(sorted(values, key=lambda item: item.name.casefold()))


@lru_cache(maxsize=1)
def countries_by_name() -> dict[str, Country]:
    return {country.name: country for country in countries()}


@lru_cache(maxsize=1)
def countries_by_code() -> dict[str, Country]:
    return {country.iso2: country for country in countries()}


def country_for_code(iso2: str) -> Country:
    mapping = countries_by_code()
    return mapping.get(iso2.upper()) or mapping["EG"]


def validate_phone(country_iso2: str, raw_number: str) -> tuple[bool, str, str]:
    """Return (is_valid, E.164 value, user-facing validation message)."""

    raw = str(raw_number or "").strip()
    if not raw:
        return False, "", "Phone number is required."
    try:
        parsed = phonenumbers.parse(raw, None if raw.startswith("+") else country_iso2.upper())
    except phonenumbers.NumberParseException:
        return False, "", "Enter a valid phone number for the selected country."

    if not phonenumbers.is_valid_number(parsed):
        return False, "", "Enter a valid phone number for the selected country."

    number_region = phonenumbers.region_code_for_number(parsed)
    # Some territories share a calling code.  The library's resolved region is
    # used to prevent an unrelated country's number from being silently saved.
    if not raw.startswith("+") and number_region and number_region != country_iso2.upper():
        return False, "", "The phone number does not match the selected country."

    formatted = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    return True, formatted, "Valid phone number."
