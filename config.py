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
SYSTEM_TITLE = "Hotel Booking Request & Registration System"

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

# All new requests and invoices use EUR only.
CURRENCY = "EUR"


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
    "Royal Marshal Hotel": {
        "stars": 3,
        "distance_to_arena": "To be confirmed",
        "location": "4 A El Khalifa El Maamoun Street, Roxy, Heliopolis, Cairo",
        "website": "https://www.royalmarshalhotel.com/",
        "notes": "",
        "rates": {
            "Breakfast": {"Single": 47.5, "Double": 65.0},
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

# Official room allotment supplied by the organizer.  These are capacity
# ceilings per night; the backend derives remaining rooms by subtracting
# active overlapping requests. A dash in the source table is represented as 0
# only when that room type is still present in the current rate catalogue.
ROOM_INVENTORY = {
    "Tiba Rose El Golf": {"Single": 4, "Double": 4, "Triple": 4},
    "Baron Hotel Cairo": {"Single": 10, "Double": 10, "Triple": 10, "Quadruple": 10},
    "Armor House Hotel, Cairo": {"Single": 7, "Double": 8, "Suite (2 rooms / 4 persons)": 25},
    "Hotel El Forsan": {"Single": 10, "Double": 50, "Triple": 0},
    "Hotel Jewel Elnasr": {"Single": 19, "Double": 47, "Triple": 5, "Quadruple": 4},
    "Hotel Infantry House": {"Single": 25, "Double": 25, "Quadruple": 20},
    "Hotel Engineering Authority House": {"Single": 6, "Double": 60, "Quadruple": 40},
    "Royal Marshal Hotel": {"Single": 10, "Double": 30},
}


# ---------------------------------------------------------------------------
# Transportation - final approved quotation. EUR per complete vehicle.
# Source: Transportation_Rates_Official(1).xlsx and nakal_prices.xlsx.
# ---------------------------------------------------------------------------
APP_SCHEMA_VERSION = "2026-08-31-v5.4"
TRANSPORT_RATE_VERSION = "2026-08-30-final-full-vehicle"
TRANSPORT_SERVICES = {
    "Airport Transfer": {"label": "Airport / Hotel - One-way Transfer", "max_hours": None,
                         "directions": ("Airport to Hotel", "Hotel to Airport")},
    "Stadium Transfer": {"label": "Hotel / Stadium - One-way Transfer", "max_hours": None,
                         "directions": ("Hotel to Stadium", "Stadium to Hotel")},
    "Daily 8 Hours": {"label": "Daily Hire - Up to 8 Hours", "max_hours": 8, "directions": ()},
    "Daily 12 Hours": {"label": "Daily Hire - Up to 12 Hours", "max_hours": 12, "directions": ()},
}
TRANSPORTATION = {
    "Limousine (3 Seats)": {"capacity": 3, "prices_eur": {
        "Airport Transfer": 30, "Stadium Transfer": 30, "Daily 8 Hours": 110, "Daily 12 Hours": 145}},
    "H1 / Van (7 Seats)": {"capacity": 7, "prices_eur": {
        "Airport Transfer": 50, "Stadium Transfer": 50, "Daily 8 Hours": 150, "Daily 12 Hours": 170}},
    "Toyota Hiace (10 Seats)": {"capacity": 10, "prices_eur": {
        "Airport Transfer": 60, "Stadium Transfer": 60, "Daily 8 Hours": 160, "Daily 12 Hours": 200}},
    "Coaster (26 Seats)": {"capacity": 26, "prices_eur": {
        "Airport Transfer": 100, "Stadium Transfer": 100, "Daily 8 Hours": 200, "Daily 12 Hours": 240}},
    "Bus (50 Seats)": {"capacity": 50, "prices_eur": {
        "Airport Transfer": 190, "Stadium Transfer": 190, "Daily 8 Hours": 300, "Daily 12 Hours": 400}},
}
MAX_BOOKING_NIGHTS = 60
MAX_TRANSPORT_SERVICES = 60
DEFAULT_COUNTRY_CODE = "EG"
