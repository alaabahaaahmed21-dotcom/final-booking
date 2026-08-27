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

# EUR is the only base currency.  The current working conversion agreed for
# the application is 1 EUR = 56 EGP and 1 USD = 49.50 EGP.  Change these two
# values only when the organizer publishes a new booking exchange rate.
CURRENCY_RATES = {
    "EUR_TO_USD": 56.0 / 49.5,
    "EUR_TO_EGP": 56.0,
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

# EUR is the transportation base currency too.  The Limousine values are for
# one complete vehicle.  Every bus value is a preliminary EUR/person rate
# derived from the supplier quotation and the stated vehicle capacity.
TRANSPORT_RATE_VERSION = "2026-08-27 quotation - EUR preliminary rates"

TRANSPORT_SERVICES = {
    "One-way Transfer - Airport to Stadium or Hotel": (
        "One-way Transfer - Airport to Stadium or Hotel"
    ),
    "Full Day Within Cairo": "Full Day Within Cairo",
    "Evening Service": "Evening Service",
}

TRANSPORT_PRICING_LABELS = {
    "per_vehicle": "Full Vehicle",
    "per_person": "Per Person",
}

TRANSPORTATION = {
    "Limousine": {
        "pricing_modes": ("per_vehicle",),
        "prices_eur": {
            "One-way Transfer - Airport to Stadium or Hotel": 23.214286,
            "Full Day Within Cairo": 80.357143,
            "Evening Service": 32.142857,
        },
    },
    "Hiace (15 Seats)": {
        "capacity": 15,
        "pricing_modes": ("per_person",),
        "prices_eur": {
            "One-way Transfer - Airport to Stadium or Hotel": 2.500000,
            "Full Day Within Cairo": 6.666667,
            "Evening Service": 2.976190,
        },
    },
    "Coaster (30 Seats)": {
        "capacity": 30,
        "pricing_modes": ("per_person",),
        "prices_eur": {
            "One-way Transfer - Airport to Stadium or Hotel": 1.815476,
            "Full Day Within Cairo": 3.690476,
            "Evening Service": 1.785714,
        },
    },
    "33-Seat Bus": {
        "capacity": 33,
        "pricing_modes": ("per_person",),
        "prices_eur": {
            "One-way Transfer - Airport to Stadium or Hotel": 1.948052,
            "Full Day Within Cairo": 4.112554,
            "Evening Service": 1.893939,
        },
    },
    "50-Seat Bus": {
        "capacity": 50,
        "pricing_modes": ("per_person",),
        "prices_eur": {
            "One-way Transfer - Airport to Stadium or Hotel": 2.321429,
            "Full Day Within Cairo": 4.714286,
            "Evening Service": 1.892857,
        },
    },
}


# ---------------------------------------------------------------------------
# Upload and booking rules
# ---------------------------------------------------------------------------

MAX_IMAGE_SIZE_MB = 8
MAX_IMAGE_PIXELS = 30_000_000

PERSONAL_PHOTO_TARGET_MB = 0.4
PERSONAL_PHOTO_MAX_DIMENSION = 1200

PASSPORT_PHOTO_TARGET_MB = 0.8
PASSPORT_PHOTO_MAX_DIMENSION = 1800

REQUIRE_PERSONAL_PHOTO = True
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
    "Transportation Service",
    "Transportation Pricing Mode",
    "Transportation Persons",
    "Transportation Vehicle Count",
    "Transportation Billed Units",
    "Transportation Unit Price EGP",
    "Transportation Unit Price EUR",
    "Transportation Rate Version",
    "Transportation Price Per Person EUR",
    "Room Total EUR",
    "Transportation Total EUR",
    "Transportation Total EGP",
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
