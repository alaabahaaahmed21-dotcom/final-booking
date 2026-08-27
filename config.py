"""Central configuration for the 23rd ITKF hotel booking application.

Official hotel rates were transcribed from
``ITKF_2026_Official_Hotel FINAL.pdf``.  All hotel rates are EUR for one
night.  The application deliberately treats EUR as the base currency.
"""

from __future__ import annotations

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Event and branding
# ---------------------------------------------------------------------------

EVENT_ORG_NAME = "Egyptian Traditional Karate Federation"
EVENT_TITLE = "23rd ITKF Championship"
SYSTEM_TITLE = "Online Hotel Booking System"

LOGO_PATHS = {
    "logo1": BASE_DIR / "assets" / "logo1.png",
    "logo2": BASE_DIR / "assets" / "logo2.png",
    "logo3": BASE_DIR / "assets" / "logo3.png",
}

HEADER_BG_COLOR = "#FFFFFF"
BORDER_COLOR = "#C8102E"


# ---------------------------------------------------------------------------
# Currency
# ---------------------------------------------------------------------------

# EUR is the only base currency.  Change these two values whenever the
# organizer updates the exchange rate.  The starting values preserve the
# relationship used by the original USD-based configuration:
# 1 USD = 0.92 EUR and 1 USD = 49.00 EGP.
CURRENCY_RATES = {
    "EUR_TO_USD": 1.0 / 0.92,
    "EUR_TO_EGP": 49.0 / 0.92,
}


# ---------------------------------------------------------------------------
# Hotel catalogue - official October 2026 brochure
# ---------------------------------------------------------------------------

# Each value in ``rates`` is an official EUR nightly rate.  A hotel can offer
# one or more meal plans.  Room options that are absent from a plan are not
# selectable in the application.
HOTELS = {
    "Tiba Rose El Golf": {
        "stars": 5,
        "distance_to_arena": "6 min by car",
        "location": "El Golf, Heliopolis, Cairo",
        "website": "http://www.milhouses.com.eg/dar/DefaultAr.aspx?id=1",
        "notes": "",
        "rates": {
            "Breakfast": {"Single": 80.0, "Double": 50.0, "Triple": 45.0},
            "Half Board": {"Single": 95.0, "Double": 60.0, "Triple": 50.0},
        },
    },
    "Hilton Cairo Heliopolis": {
        "stars": 5,
        "distance_to_arena": "15 min by car",
        "location": "Heliopolis, Cairo - El-Orouba / Qism El-Nozha",
        "website": "https://www.hilton.com/en/hotels/caihehi-hilton-cairo-heliopolis/",
        "notes": "",
        "rates": {
            "Breakfast": {"Single": 190.0, "Double": 110.0},
        },
    },
    "Sonesta Hotel Tower & Casino Cairo": {
        "stars": 5,
        "distance_to_arena": "6 min by car / 15 min walk",
        "location": "Nasr City, Cairo - 3 El Tayran Street",
        "website": "https://www.sonesta.com/sonesta-hotels-resorts/cairo-governorate/nasr-city-cairo/sonesta-hotel-tower-casino-cairo",
        "notes": "",
        "rates": {
            "Half Board": {"Single": 185.0, "Double": 110.0, "Triple": 93.0},
        },
    },
    "Baron Hotel Cairo": {
        "stars": 4,
        "distance_to_arena": "10 min by car / 30 min walk",
        "location": "Heliopolis, Cairo - Off Uruba Road",
        "website": "https://baronhotels.com/baron-hotel-cairo/",
        "notes": "",
        "rates": {
            "Breakfast": {"Single": 130.0, "Double": 75.0, "Triple": 60.0},
        },
    },
    "Armor House Hotel, Cairo": {
        "stars": 4,
        "distance_to_arena": "2 min walk",
        "location": "Cairo, Egypt - Salah Salem Street area",
        "website": "http://www.milhouses.com.eg/dar/Default.aspx?id=13",
        "notes": "",
        "rates": {
            "Half Board": {
                "Single": 75.0,
                "Double": 55.0,
                "Suite (2 rooms / 4 persons)": 45.0,
            },
        },
    },
    "Hotel El Forsan": {
        "stars": 4,
        "distance_to_arena": "2 min walk",
        "location": "Cairo, Egypt - immediate arena vicinity",
        "website": "http://www.milhouses.com.eg/dar/Default.aspx?id=13",
        "notes": "",
        "rates": {
            "Half Board": {"Single": 85.0, "Double": 60.0, "Triple": 50.0},
        },
    },
    "Hotel Jewel Elnasr": {
        "stars": 3,
        "distance_to_arena": "8 min by car",
        "location": "Nasr City, Cairo - 18 El Tayaran Street",
        "website": "",
        "notes": "Website not verified in supplied brochure.",
        "rates": {
            "Breakfast": {"Single": 65.0, "Double": 47.0, "Triple": 42.0},
            "Half Board": {"Single": 75.0, "Double": 57.0, "Triple": 52.0},
            "Full Board": {"Single": 85.0, "Double": 67.0, "Triple": 62.0},
        },
    },
    "Hotel Infantry House": {
        "stars": 3,
        "distance_to_arena": "6 min by car / 25 min walk",
        "location": "Cairo, Egypt - Infantry House (Dar El-Moshah)",
        "website": "http://www.milhouses.com.eg/dar/Default.aspx?id=20",
        "notes": "",
        "rates": {
            "Breakfast": {"Single": 65.0, "Double": 40.0, "Quadruple": 30.0},
        },
    },
    "Hotel Engineering Authority House": {
        "stars": 3,
        "distance_to_arena": "6 min by car / 25 min walk",
        "location": "Mansheya El-Bakry, Heliopolis, Cairo",
        "website": "http://www.milhouses.com.eg/dar/Default.aspx?id=19",
        "notes": "",
        "rates": {
            "Breakfast": {"Single": 70.0, "Double": 45.0},
        },
    },
}

ROOM_OCCUPANCY = {
    "Single": 1,
    "Double": 2,
    "Triple": 3,
    "Quadruple": 4,
    "Suite (2 rooms / 4 persons)": 4,
}


# ---------------------------------------------------------------------------
# Transportation
# ---------------------------------------------------------------------------

# Vehicle names remain in English.  Enter each final EUR/person price here once
# the official transportation plan arrives.  ``None`` means "price pending"
# and prevents an invoice from being issued with an incorrect amount.
TRANSPORTATION = {
    "Limousine": {"price_per_person_eur": None},
    "Hiace Bus": {"price_per_person_eur": None},
    "Coaster Bus": {"price_per_person_eur": None},
    "33-Seat Bus": {"price_per_person_eur": None},
    "50-Seat Bus": {"price_per_person_eur": None},
}


# ---------------------------------------------------------------------------
# Upload and booking rules
# ---------------------------------------------------------------------------

MAX_IMAGE_SIZE_MB = 8
MAX_IMAGE_PIXELS = 30_000_000
REQUIRE_PERSONAL_PHOTO = False
REQUIRE_PASSPORT_PHOTO = True
MAX_BOOKING_NIGHTS = 60
DEFAULT_COUNTRY_CODE = "EG"


# ---------------------------------------------------------------------------
# Google Sheet columns used by the Apps Script backend
# ---------------------------------------------------------------------------

SHEET_COLUMNS = [
    "Booking ID",
    "Booking Date",
    "Guest Name",
    "Nationality",
    "Nationality Code",
    "Phone Country Code",
    "Phone",
    "Email",
    "Personal Photo File ID",
    "Personal Photo URL",
    "Passport Photo File ID",
    "Passport Photo URL",
    "Hotel",
    "Meal Plan",
    "Room Type",
    "Guests",
    "Check-in",
    "Check-out",
    "Nights",
    "Nightly Rate EUR",
    "Vehicle Type",
    "Transportation Persons",
    "Transportation Price Per Person EUR",
    "Room Total EUR",
    "Transportation Total EUR",
    "Grand Total EUR",
    "Grand Total USD",
    "Grand Total EGP",
    "Invoice No",
    "Invoice File ID",
    "Invoice URL",
    "Invoice Verification Code",
    "Invoice SHA-256",
    "Customer Email Sent",
    "Email Sent At",
    "Processing Started",
    "Status",
    "Last Error",
]
