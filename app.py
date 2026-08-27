import streamlit as st
import pandas as pd
from datetime import date
from pathlib import Path
import requests
import re
import time
import uuid
import base64
import json
import io
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage

# =========================================================
# BOOKING / REGISTRATION APP
# =========================================================
# IMPORTANT:
# 1) Put secrets in .streamlit/secrets.toml (never in this file).
# 2) The Google Apps Script backend supplied with this project
#    stores the registration, passport and invoice securely.
#    Two backend actions are expected:
#       - "check_duplicate"  -> {"ok": true, "exists": bool}
#       - "create_booking"   -> {"ok": true, ...}
#    (see the integration note above check_duplicate() below)
# 3) Hotel prices below are INITIAL values from the supplied table.
#    Edit only HOTEL_DATA / TRANSPORT_DATA when final prices arrive.
# =========================================================

st.set_page_config(
    page_title="Booking & Registration",
    page_icon="🧾",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ---------------- Secrets ----------------
def secret(name, default=None):
    try:
        return st.secrets[name]
    except Exception:
        return default

GOOGLE_SHEET_API = secret("GOOGLE_SHEET_API", "")
ADMIN_TOKEN = secret("ADMIN_TOKEN", "")
ADMIN_PASSWORD = secret("ADMIN_PASSWORD", "")

MAX_PASSPORT_MB = int(secret("MAX_PASSPORT_MB", 5))
MAX_PASSPORT_BYTES = MAX_PASSPORT_MB * 1024 * 1024

# ---------------- Branding ----------------
# اللوجوهات بتتحط في مجلد assets/ جنب app.py بالظبط (نفس الأسماء دي):
#   logo_main.png       -> لوجو الاتحاد (الأحمر/الأسود) - الأكبر
#   logo_secondary.png  -> اللوجو التاني - الأصغر
APP_DIR = Path(__file__).resolve().parent
ASSETS_DIR = APP_DIR / "assets"

def find_asset(stem):
    """Find logos in assets/ OR next to app.py, regardless of image extension/case."""
    search_dirs = [ASSETS_DIR, APP_DIR]
    for folder in search_dirs:
        for ext in ("png", "jpg", "jpeg", "webp", "PNG", "JPG", "JPEG", "WEBP"):
            candidate = folder / f"{stem}.{ext}"
            if candidate.is_file():
                return candidate
    return None

LOGO_MAIN_PATH = find_asset("logo_main")
LOGO_SECONDARY_PATH = find_asset("logo_secondary")

def _b64_of(path):
    try:
        if path and path.is_file():
            return base64.b64encode(path.read_bytes()).decode("ascii")
    except Exception:
        pass
    return None

LOGO_MAIN_B64 = _b64_of(LOGO_MAIN_PATH)
LOGO_SECONDARY_B64 = _b64_of(LOGO_SECONDARY_PATH)

def _logo_data_uri(path):
    if not path or not path.is_file():
        return None
    mime = {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp"
    }.get(path.suffix.lower(), "application/octet-stream")
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"

LOGO_MAIN_URI = _logo_data_uri(LOGO_MAIN_PATH)
LOGO_SECONDARY_URI = _logo_data_uri(LOGO_SECONDARY_PATH)

LOGO_URL = secret("LOGO_URL", "")  # احتياطي فقط لو ملفات الـ assets مش موجودة
COMPANY_NAME = secret("COMPANY_NAME", "Egyptian Traditional Karate Federation")
COMPANY_EMAIL = secret("COMPANY_EMAIL", "")
CURRENCY = secret("CURRENCY", "EGP")
CURRENCY_LABEL = "EGP" if CURRENCY == "EGP" else CURRENCY

# =========================================================
# EDITABLE PRICES
# =========================================================
# الأسعار افتراضيًا للroom/الnight الواحدة ما لم يُذكر غير ذلك.
# القيمة None تعني أن السعر لسه معتمدش، فيبقى الحجز مقفول على الخيار ده.

HOTEL_DATA = {
    "Infantry House": {
        "Single": 2700,
        "Double": 2900,
        "Triple": None,
        "Quadruple": 4000,
        "Meal Plan": "Breakfast",
        "Lunch Supplement": 500,
        "Dinner Supplement": 500,
    },
    "Engineering Authority House": {
        "Single": 3000,
        "Double": 3750,
        "Triple": None,
        "Quadruple": 6500,
        "Meal Plan": "Breakfast",
        "Lunch Supplement": 500,
        "Dinner Supplement": 500,
    },
    "Air Defense House - Fifth Settlement": {
        "Single": 4150,
        "Double": 5120,
        "Triple": 7800,
        "Quadruple": 10400,
        "Meal Plan": "-",
        "Lunch Supplement": 0,
        "Dinner Supplement": 0,
    },
    "Sonesta": {
        "Single": 9000,
        "Double": 10000,
        "Triple": 12500,
        "Quadruple": None,
        "Meal Plan": "Breakfast + Dinner",
        "Lunch Supplement": 1250,
        "Dinner Supplement": 0,
    },
    "Baron Hotel": {
        "Single": 6500,
        "Double": 7000,
        "Triple": 8100,
        "Quadruple": None,
        "Meal Plan": "Breakfast",
        "Lunch Supplement": 800,
        "Dinner Supplement": 800,
    },
    "Jewel Al Nasr": {
        "Single": 2860,
        "Double": 3900,
        "Triple": 5200,
        "Quadruple": 7250,
        "Meal Plan": "Breakfast",
        "Lunch Supplement": 0,
        "Dinner Supplement": 0,
    },
    "Hilton": {
        "Single": None,
        "Double": None,
        "Triple": None,
        "Quadruple": None,
        "Meal Plan": "Price to be confirmed",
        "Lunch Supplement": 0,
        "Dinner Supplement": 0,
    },
    "Air Defense House - Nozha": {
        "Single": 3640,
        "Double": 4160,
        "Triple": None,
        "Quadruple": 6760,
        "Meal Plan": "Price to be confirmed",
        "Lunch Supplement": 0,
        "Dinner Supplement": 0,
    },
}

# الأسعار None عمدًا لحد ما تعرفة Transportation النهائية توصل.
TRANSPORT_DATA = {
    "Limousine": 1000,
    "Hiace Bus": 1000,
    "Coaster Bus": 1000,
    "33-Seat Bus": 1000,
    "50-Seat Bus": 1000,
}


ROOM_LABELS = {
    "Single": "Single",
    "Double": "Double",
    "Triple": "Triple",
    "Quadruple": "Quadruple",
}

ROOM_CAPACITY = {
    "Single": 1,
    "Double": 2,
    "Triple": 3,
    "Quadruple": 4,
}

# ---------------- Nationalities ----------------
NATIONALITIES = [
    "Afghanistan", "Albania", "Algeria", "Argentina", "Armenia",
    "Australia", "Austria", "Azerbaijan", "Bahrain", "Bangladesh",
    "Belarus", "Belgium", "Bosnia and Herzegovina", "Brazil", "Bulgaria",
    "Cameroon", "Canada", "China", "Croatia", "Cyprus", "Czech Republic",
    "Denmark", "Egypt", "Estonia", "Ethiopia", "Finland", "France",
    "Georgia", "Germany", "Ghana", "Greece", "Hungary", "India",
    "Indonesia", "Iran", "Iraq", "Ireland", "Italy", "Japan", "Jordan",
    "Kazakhstan", "Kenya", "Kuwait", "Kyrgyzstan", "Lebanon", "Libya",
    "Lithuania", "Luxembourg", "Malaysia", "Malta", "Mauritius",
    "Mexico", "Morocco", "Netherlands", "New Zealand", "Nigeria",
    "Norway", "Oman", "Pakistan", "Palestine", "Philippines", "Poland",
    "Portugal", "Qatar", "Romania", "Russia", "Saudi Arabia", "Serbia",
    "Singapore", "Slovakia", "Slovenia", "South Africa", "South Korea",
    "Spain", "Sudan", "Sweden", "Switzerland", "Syria", "Tanzania",
    "Thailand", "Tunisia", "Turkey", "Uganda", "Ukraine",
    "United Arab Emirates", "United Kingdom", "United States",
    "Uzbekistan", "Vietnam", "Yemen", "Zambia", "Zimbabwe", "Other",
]

# ---------------- CSS (RTL + professional look) ----------------
st.markdown("""
<style>
html, body, [class*="css"]  { direction: ltr; }
.block-container {max-width: 880px; padding-top: 1.2rem; direction: ltr;}
* { text-align: left; }
.stButton, .stDownloadButton { direction: ltr; }

/* Top brand bar */
.brand-bar{
    display:flex; align-items:center; justify-content:space-between;
    gap:14px; padding:14px 20px; margin-bottom:18px;
    background:linear-gradient(135deg,#0f172a,#1e293b);
    border-radius:16px; color:#fff;
}
.brand-bar h1{ font-size:1.15rem; margin:0; color:#fff; }
.brand-bar span{ font-size:0.8rem; color:#cbd5e1; }
.logo-wrap{ display:flex; align-items:center; gap:10px; }
.logo-wrap img{ display:block; border-radius:8px; background:#fff; }
.logo-wrap img.logo-main{ height:54px; padding:4px; }
.logo-wrap img.logo-sub{ height:38px; padding:4px; }

/* Free page navigation */
.nav-caption { color:#6b7280; font-size:.82rem; margin:2px 0 8px; }

.booking-card {
    border: 1px solid #e5e7eb;
    border-radius: 16px;
    padding: 20px;
    margin: 12px 0;
    background: #ffffff;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.section-title{ font-weight:700; font-size:1.05rem; margin-bottom:6px; }
.small-muted {color:#6b7280;font-size:0.88rem;}
.total-box {
    border: 2px solid #111827;
    border-radius: 14px;
    padding: 16px 20px;
    font-size: 1.2rem;
    font-weight: 800;
    background:#f8fafc;
    margin-top:10px;
}
.price-pill{
    display:inline-block; padding:4px 12px; border-radius:999px;
    background:#eef2ff; color:#3730a3; font-size:0.85rem; font-weight:600;
}
.warn-pill{
    display:inline-block; padding:4px 12px; border-radius:999px;
    background:#fef3c7; color:#92400e; font-size:0.85rem; font-weight:600;
}
.footer-note{ text-align:center; color:#94a3b8; font-size:0.78rem; margin-top:28px; }
</style>
""", unsafe_allow_html=True)

# ---------------- Session ----------------
if "page" not in st.session_state:
    st.session_state.page = "personal"
if "booking_id" not in st.session_state:
    st.session_state.booking_id = None
if "invoice_pdf" not in st.session_state:
    st.session_state.invoice_pdf = None
if "last_backend_error" not in st.session_state:
    st.session_state.last_backend_error = None

PAGE_ORDER = ["personal", "hotel", "transport", "review", "success"]
STEP_LABELS = ["Personal Details", "Hotel", "Transportation", "Review", "Complete"]

# =========================================================
# HELPERS
# =========================================================
def valid_email(email):
    return bool(re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", email.strip()))

def clean_text(value, max_len=200):
    value = str(value or "").strip()
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", value)
    return value[:max_len]

def clean_passport(value):
    # منع فروق التنسيق (مسافات / حروف صغيرة وكبيرة) اللي ممكن تخلي نفس
    # الجواز يتسجل مرتين وهو ظاهريًا "مختلف".
    value = clean_text(value, 30)
    return re.sub(r"\s+", "", value).upper()

def money(value):
    return f"{value:,.2f} {CURRENCY_LABEL}"

def generate_ids():
    token = uuid.uuid4().hex[:10].upper()
    return f"BK-{token}", f"INV-{token}"

def hotel_price(hotel, room_type):
    return HOTEL_DATA.get(hotel, {}).get(room_type)

def meal_supplement(hotel, meal_name):
    return float(HOTEL_DATA.get(hotel, {}).get(meal_name, 0) or 0)

def image_to_bytes(uploaded_file):
    if uploaded_file is None:
        return None, None
    raw = uploaded_file.getvalue()
    if len(raw) > MAX_PASSPORT_BYTES:
        raise ValueError(f"Passport image must be smaller than {MAX_PASSPORT_MB} MB.")
    try:
        img = Image.open(io.BytesIO(raw))
        img.verify()
        img = Image.open(io.BytesIO(raw))
        if img.width > 5000 or img.height > 5000:
            raise ValueError("Passport image dimensions are too large.")
        img = img.convert("RGB")
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=90, optimize=True)
        return out.getvalue(), "passport.jpg"
    except Exception as exc:
        raise ValueError("The passport file is not a valid image.") from exc

def render_brand_bar():
    """Render logos with st.image instead of HTML data-URI images.
    This is more reliable on Streamlit Cloud/mobile browsers.
    """
    safe_company = html.escape(str(COMPANY_NAME))
    st.markdown(
        f"<div class='brand-bar'><div><h1>{safe_company}</h1>"
        "<span>Online Booking & Registration System</span></div></div>",
        unsafe_allow_html=True,
    )

    logo_paths = [x for x in (LOGO_MAIN_PATH, LOGO_SECONDARY_PATH) if x and x.is_file()]
    if logo_paths:
        cols = st.columns(len(logo_paths))
        for col, path in zip(cols, logo_paths):
            with col:
                st.image(str(path), use_container_width=True)
    elif LOGO_URL:
        st.image(LOGO_URL, use_container_width=True)

def navigate_to(page):
    st.session_state.page = page
    st.rerun()

def render_navigation():
    labels = {
        "personal": "Personal",
        "hotel": "Hotel",
        "transport": "Transportation",
        "review": "Review",
        "success": "Complete",
    }
    st.markdown("<div class='nav-caption'>You can move between pages freely to preview the app.</div>", unsafe_allow_html=True)
    cols = st.columns(len(PAGE_ORDER))
    for col, page in zip(cols, PAGE_ORDER):
        with col:
            if st.button(labels[page], key=f"nav_{page}", use_container_width=True, type="primary" if st.session_state.page == page else "secondary"):
                navigate_to(page)


def _pdf_logo_flowable():
    cells = []
    for path, width in ((LOGO_MAIN_PATH, 28 * mm), (LOGO_SECONDARY_PATH, 20 * mm)):
        if path and path.is_file():
            try:
                cells.append(RLImage(str(path), width=width, height=width))
            except Exception:
                pass

    if cells:
        col_widths = [img.drawWidth + 6 * mm for img in cells]
        table = Table([cells], colWidths=col_widths)
        table.hAlign = "CENTER"
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        return table

    if LOGO_URL:
        try:
            resp = requests.get(LOGO_URL, timeout=8)
            resp.raise_for_status()
            img = RLImage(io.BytesIO(resp.content), width=32 * mm, height=32 * mm)
            img.hAlign = "CENTER"
            return img
        except Exception:
            pass

    return None

def create_invoice_pdf(data):
    out = io.BytesIO()

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="InvoiceTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=18,
        leading=22,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="Small",
        parent=styles["Normal"],
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#6b7280"),
    ))

    doc = SimpleDocTemplate(
        out,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )

    story = []

    logo_flow = _pdf_logo_flowable()
    if logo_flow is not None:
        story.append(logo_flow)
        story.append(Spacer(1, 8))

    story += [
        Paragraph(COMPANY_NAME, styles["InvoiceTitle"]),
        Paragraph("Booking Invoice", styles["Heading2"]),
        Spacer(1, 5),
        Paragraph(f"<b>Booking ID:</b> {data['booking_id']}", styles["Normal"]),
        Paragraph(f"<b>Invoice No:</b> {data['invoice_no']}", styles["Normal"]),
        Paragraph(f"<b>Customer:</b> {data['full_name']}", styles["Normal"]),
        Paragraph(f"<b>Email:</b> {data['email']}", styles["Normal"]),
        Paragraph(f"<b>Nationality:</b> {data['nationality']}", styles["Normal"]),
        Spacer(1, 10),
    ]

    rows = [["Item", "Details", "Qty", "Unit Price", "Total"]]
    for item in data["items"]:
        rows.append([
            item["item"],
            item["details"],
            str(item["qty"]),
            money(item["unit_price"]),
            money(item["total"]),
        ])

    table = Table(rows, colWidths=[34 * mm, 66 * mm, 15 * mm, 30 * mm, 30 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(table)
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"<b>Grand Total: {money(data['total'])}</b>", styles["Heading2"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "This invoice is generated electronically. Prices are based on the booking "
        "options selected by the customer.",
        styles["Small"],
    ))
    if COMPANY_EMAIL:
        story.append(Paragraph(f"Contact: {COMPANY_EMAIL}", styles["Small"]))
    doc.build(story)
    return out.getvalue()

def backend_post(payload, timeout=30, retries=2):
    if not GOOGLE_SHEET_API:
        raise RuntimeError("GOOGLE_SHEET_API is not configured in Streamlit secrets.")

    last_exc = None
    for attempt in range(retries + 1):
        try:
            response = requests.post(
                GOOGLE_SHEET_API,
                json=payload,
                timeout=timeout,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            try:
                result = response.json()
            except Exception:
                result = {"ok": response.text.strip().lower() == "ok", "raw": response.text}
            if isinstance(result, dict) and result.get("ok") is False:
                raise RuntimeError(
                    result.get("message") or result.get("error", "Backend rejected the request.")
                )
            return result
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))  # backoff قبل إعادة المحاولة
                continue
    raise last_exc

def check_duplicate(passport_no):
    """
    يتحقق مع الباك إند إن كان رقم الجواز ده مسجل قبل كده.
    ملحوظة تكامل: الـ Google Apps Script المرفوع لازم يفهم
    action = "check_duplicate" ويرجّع {"ok": true, "exists": true/false}
    بعد ما تبعتيلي كود السيرفر هظبط الشكل بالظبط لو مختلف.
    """
    try:
        result = backend_post({
            "action": "check_duplicate",
            "api_token": secret("BOOKING_API_TOKEN", ""),
            "passport_no": passport_no,
        }, timeout=15, retries=1)
        return bool(result.get("exists", False)), None
    except Exception as exc:
        # ما بنمنعش المستخدم من الاستمرار لو خدمة الفحص نفسها وقعت،
        # لكن بنوضح إن الفحص ما تمش عشان تتابعي الموضوع من لوحة الأدمن.
        return False, str(exc)

# =========================================================
# PREVIEW DATA
# =========================================================
def get_preview_personal():
    return {
        "full_name": "Preview Guest",
        "passport_no": "PREVIEW123",
        "nationality": "Egypt",
        "dob": "1990-01-01",
        "email": "preview@example.com",
        "phone": "+20 100 000 0000",
        "passport_bytes": b"",
        "passport_name": "preview.jpg",
    }

def get_preview_hotel():
    hotel = "Infantry House"
    room = "Double"
    guests = 2
    nights = 2
    lunch_rate = meal_supplement(hotel, "Lunch Supplement")
    dinner_rate = meal_supplement(hotel, "Dinner Supplement")
    return {
        "hotel": hotel, "room_type": room, "guests": guests,
        "check_in": date.today().isoformat(),
        "check_out": (date.today() + timedelta(days=nights)).isoformat(),
        "nights": nights, "unit_price": hotel_price(hotel, room),
        "room_total": hotel_price(hotel, room) * nights,
        "lunch_selected": True, "lunch_unit_price": lunch_rate,
        "lunch_total": lunch_rate * guests * nights,
        "dinner_selected": True, "dinner_unit_price": dinner_rate,
        "dinner_total": dinner_rate * guests * nights,
        "meal_total": (lunch_rate + dinner_rate) * guests * nights,
        "total": (hotel_price(hotel, room) + (lunch_rate + dinner_rate) * guests) * nights,
        "meal_plan": HOTEL_DATA[hotel]["Meal Plan"],
    }

def get_preview_transport():
    transport = "Limousine"
    qty = 1
    unit = TRANSPORT_DATA[transport]
    return {"transport": transport, "qty": qty, "unit_price": unit, "total": unit * qty}

# =========================================================
# HEADER (shown on every page)
# =========================================================
render_brand_bar()
render_navigation()

# =========================================================
# PAGE 1 — PERSONAL DATA
# =========================================================
if st.session_state.page == "personal":
    st.markdown('<div class="booking-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">📝 Personal Details</div>', unsafe_allow_html=True)
    st.caption("Please enter the information exactly as it appears on your passport.")

    full_name = st.text_input("Full Name *")
    passport_no = st.text_input("Passport Number *", max_chars=30)
    nationality = st.selectbox("Nationality *", NATIONALITIES, index=None, placeholder="Select nationality")
    dob = st.date_input(
        "Date of Birth *",
        min_value=date(1900, 1, 1),
        max_value=date.today(),
        value=None,
    )
    email = st.text_input("Email Address *", help="Your booking invoice will be sent to this email.")
    phone = st.text_input("Phone Number", max_chars=30)
    passport_file = st.file_uploader(
        f"Passport Image * (JPG/PNG, maximum {MAX_PASSPORT_MB} MB)",
        type=["jpg", "jpeg", "png"],
    )
    st.markdown('</div>', unsafe_allow_html=True)

    if st.button("Next →", use_container_width=True, type="primary"):
        errors = []
        if not clean_text(full_name):
            errors.append("Full name is required.")
        if not clean_text(passport_no):
            errors.append("Passport number is required.")
        if nationality is None:
            errors.append("Nationality is required.")
        if dob is None:
            errors.append("Date of birth is required.")
        if not valid_email(email):
            errors.append("Please enter a valid email address.")
        if passport_file is None:
            errors.append("Passport image is required.")

        if errors:
            for err in errors:
                st.error(err)
        else:
            try:
                passport_bytes, passport_name = image_to_bytes(passport_file)
                st.session_state.personal = {
                    "full_name": clean_text(full_name),
                    "passport_no": clean_passport(passport_no),
                    "nationality": nationality,
                    "dob": dob.isoformat(),
                    "email": clean_text(email, 254),
                    "phone": clean_text(phone, 30),
                    "passport_bytes": passport_bytes,
                    "passport_name": passport_name,
                }
                st.session_state.page = "hotel"
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

# =========================================================
# PAGE 2 — HOTEL
# =========================================================
elif st.session_state.page == "hotel":
    st.markdown('<div class="booking-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">🏨 Hotel Selection</div>', unsafe_allow_html=True)

    hotel_names = list(HOTEL_DATA.keys())
    hotel = st.selectbox("Select hotel", hotel_names)

    available_rooms = [
        room for room in ["Single", "Double", "Triple", "Quadruple"]
        if hotel_price(hotel, room) is not None
    ]

    if not available_rooms:
        st.markdown(
            '<span class="warn-pill">⏳ The price for this hotel has not been confirmed yet.</span>',
            unsafe_allow_html=True,
        )
        room_type = None
        guests = 1
    else:
        room_type = st.selectbox(
            "Room type",
            available_rooms,
            format_func=lambda r: ROOM_LABELS.get(r, r),
        )

        max_guests = ROOM_CAPACITY[room_type]
        guests = st.number_input(
            "Number of guests",
            min_value=1,
            max_value=max_guests,
            value=max_guests,
            step=1,
            help="Meal supplements are calculated per guest per night.",
        )

        st.markdown(
            f'<span class="price-pill">💰 {money(hotel_price(hotel, room_type))} / room / night</span> '
            f'&nbsp; <span class="small-muted">🍽️ {HOTEL_DATA[hotel]["Meal Plan"]}</span>',
            unsafe_allow_html=True,
        )

        lunch_rate = meal_supplement(hotel, "Lunch Supplement")
        dinner_rate = meal_supplement(hotel, "Dinner Supplement")

        st.markdown("**Optional meal supplements**")
        lunch_selected = st.checkbox(
            f"Add Lunch (+{money(lunch_rate)} per guest / night)",
            value=False,
            disabled=lunch_rate <= 0,
        )
        dinner_selected = st.checkbox(
            f"Add Dinner (+{money(dinner_rate)} per guest / night)",
            value=False,
            disabled=dinner_rate <= 0,
        )

        if lunch_rate <= 0:
            st.caption("Lunch supplement is not currently configured for this hotel.")
        if dinner_rate <= 0:
            st.caption("Dinner supplement is not currently configured for this hotel.")

    st.write("")
    col1, col2 = st.columns(2)
    with col1:
        check_in = st.date_input("Check-in date", value=date.today())
    with col2:
        check_out = st.date_input("Check-out date", value=date.today())

    nights = (check_out - check_in).days

    if nights <= 0:
        st.warning("Check-out date must be after check-in date.")
    elif room_type:
        room_total = hotel_price(hotel, room_type) * nights
        lunch_total = (
            lunch_rate * int(guests) * nights
            if lunch_selected else 0
        )
        dinner_total = (
            dinner_rate * int(guests) * nights
            if dinner_selected else 0
        )
        meal_total = lunch_total + dinner_total
        total_hotel = room_total + meal_total

        st.markdown(
            f'<div class="total-box">Room: {money(room_total)}<br>'
            f'Lunch: {money(lunch_total)}<br>'
            f'Dinner: {money(dinner_total)}<br>'
            f'<b>Hotel total: {money(total_hotel)}</b></div>',
            unsafe_allow_html=True,
        )

    st.markdown('</div>', unsafe_allow_html=True)

    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("← Back", use_container_width=True):
            st.session_state.page = "personal"
            st.rerun()
    with col_next:
        if st.button("Next →", use_container_width=True, type="primary"):
            if room_type is None:
                st.error("Please select a hotel with an approved price.")
            elif nights <= 0:
                st.error("Check-out date must be after check-in date.")
            else:
                st.session_state.hotel = {
                    "hotel": hotel,
                    "room_type": room_type,
                    "guests": int(guests),
                    "check_in": check_in.isoformat(),
                    "check_out": check_out.isoformat(),
                    "nights": nights,
                    "unit_price": hotel_price(hotel, room_type),
                    "room_total": room_total,
                    "lunch_selected": bool(lunch_selected),
                    "lunch_unit_price": lunch_rate,
                    "lunch_total": lunch_total,
                    "dinner_selected": bool(dinner_selected),
                    "dinner_unit_price": dinner_rate,
                    "dinner_total": dinner_total,
                    "meal_total": meal_total,
                    "total": total_hotel,
                    "meal_plan": HOTEL_DATA[hotel]["Meal Plan"],
                }
                st.session_state.page = "transport"
                st.rerun()

# PAGE 3 — TRANSPORT
# =========================================================
elif st.session_state.page == "transport":
    st.markdown('<div class="booking-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">🚌 Transportation</div>', unsafe_allow_html=True)

    transport = st.selectbox("Transportation Method", list(TRANSPORT_DATA.keys()))

    if TRANSPORT_DATA[transport] is None:
        st.markdown('<span class="warn-pill">⏳ The price for this transportation option has not been confirmed yet</span>', unsafe_allow_html=True)
    else:
        st.markdown(
            f'<span class="price-pill">💰 {money(TRANSPORT_DATA[transport])}</span>',
            unsafe_allow_html=True,
        )

    qty = st.number_input("Quantity", min_value=1, max_value=100, value=1, step=1)

    if TRANSPORT_DATA[transport] is not None:
        st.markdown(
            f'<div class="total-box">Transportation Total: {money(TRANSPORT_DATA[transport] * int(qty))}</div>',
            unsafe_allow_html=True,
        )
    st.markdown('</div>', unsafe_allow_html=True)

    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("← Back", use_container_width=True):
            st.session_state.page = "hotel"
            st.rerun()
    with col_next:
        if st.button("Next →", use_container_width=True, type="primary"):
            if TRANSPORT_DATA[transport] is None:
                st.error("The price for this transportation option has not been confirmed yet.")
            else:
                unit = TRANSPORT_DATA[transport]
                st.session_state.transport = {
                    "transport": transport,
                    "qty": int(qty),
                    "unit_price": unit,
                    "total": unit * int(qty),
                }
                st.session_state.page = "review"
                st.rerun()

# =========================================================
# PAGE 4 — REVIEW
# =========================================================
elif st.session_state.page == "review":
    st.markdown('<div class="section-title">✅ Review & Confirmation</div>', unsafe_allow_html=True)

    preview_mode = not (st.session_state.get("personal") and st.session_state.get("hotel") and st.session_state.get("transport"))
    p = st.session_state.personal or get_preview_personal()
    h = st.session_state.hotel or get_preview_hotel()
    t = st.session_state.transport or get_preview_transport()

    if preview_mode:
        st.info("Preview mode: this page is only showing the design. Enter the Personal Details and move through the booking normally before submitting a real booking.")

    hotel_item = {
        "item": "Accommodation",
        "details": f"{h['hotel']} — {ROOM_LABELS.get(h['room_type'], h['room_type'])} — {h['nights']} night",
        "qty": h["nights"],
        "unit_price": h["unit_price"],
        "total": h["total"],
    }
    transport_item = {
        "item": "Transportation",
        "details": t["transport"],
        "qty": t["qty"],
        "unit_price": t["unit_price"],
        "total": t["total"],
    }

    meal_items = []
    if h.get("lunch_selected") and h.get("lunch_total", 0) > 0:
        meal_items.append({
            "item": "Lunch",
            "details": f"{h['hotel']} — {h['guests']} guest(s) — {h['nights']} night(s)",
            "qty": h["guests"] * h["nights"],
            "unit_price": h["lunch_unit_price"],
            "total": h["lunch_total"],
        })
    if h.get("dinner_selected") and h.get("dinner_total", 0) > 0:
        meal_items.append({
            "item": "Dinner",
            "details": f"{h['hotel']} — {h['guests']} guest(s) — {h['nights']} night(s)",
            "qty": h["guests"] * h["nights"],
            "unit_price": h["dinner_unit_price"],
            "total": h["dinner_total"],
        })

    items = [hotel_item] + meal_items + [transport_item]
    total = sum(x["total"] for x in items)

    st.markdown('<div class="booking-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">👤 Personal Details</div>', unsafe_allow_html=True)
    st.write(f"**Name:** {p['full_name']}")
    st.write(f"**Passport Number:** {p['passport_no']}")
    st.write(f"**Nationality:** {p['nationality']}")
    st.write(f"**Date of Birth:** {p['dob']}")
    st.write(f"**Email:** {p['email']}")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="booking-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">🧾 Booking Details</div>', unsafe_allow_html=True)
    st.dataframe(
        pd.DataFrame([
            {
                "Item": x["item"],
                "Details": x["details"],
                "Qty": x["qty"],
                "Unit Price": money(x["unit_price"]),
                "Total": money(x["total"]),
            }
            for x in items
        ]),
        use_container_width=True,
        hide_index=True,
    )
    st.markdown(f'<div class="total-box">Grand Total: {money(total)}</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("← Back", use_container_width=True):
            st.session_state.page = "transport"
            st.rerun()

    submit = False
    if not preview_mode:
        with col_next:
            confirm = st.checkbox("I confirm that the information above is correct.")
            submit = st.button("Confirm Booking & Generate Invoice", type="primary", use_container_width=True)

    if submit:
        if not confirm:
            st.error("Please confirm that the information is correct.")
            st.stop()

        with st.spinner("Checking your information..."):
            is_duplicate, dup_error = check_duplicate(p["passport_no"])
        if dup_error:
            st.warning("Automatic duplicate checking is temporarily unavailable. The booking will continue and may be reviewed manually.")
        if is_duplicate:
            st.error("This passport number is already registered. If this is an error, please contact us.")
            st.stop()

        booking_id, invoice_no = generate_ids()

        payload_data = {
            "booking_id": booking_id,
            "invoice_no": invoice_no,
            "full_name": p["full_name"],
            "passport_no": p["passport_no"],
            "nationality": p["nationality"],
            "dob": p["dob"],
            "email": p["email"],
            "phone": p["phone"],
            "hotel": h["hotel"],
            "room_type": h["room_type"],
            "guests": h["guests"],
            "check_in": h["check_in"],
            "check_out": h["check_out"],
            "nights": h["nights"],
            "meal_plan": h["meal_plan"],
            "lunch_selected": h["lunch_selected"],
            "lunch_unit_price": h["lunch_unit_price"],
            "lunch_total": h["lunch_total"],
            "dinner_selected": h["dinner_selected"],
            "dinner_unit_price": h["dinner_unit_price"],
            "dinner_total": h["dinner_total"],
            "transport": t["transport"],
            "transport_qty": t["qty"],
            "total": total,
            "items": items,
        }

        with st.spinner("Creating your booking and invoice..."):
            try:
                pdf_bytes = create_invoice_pdf(payload_data)

                request_payload = {
                    "action": "create_booking",
                    "api_token": secret("BOOKING_API_TOKEN", ""),
                    "booking": payload_data,
                    "passport_base64": base64.b64encode(p["passport_bytes"]).decode("ascii"),
                    "passport_filename": p["passport_name"],
                    "invoice_base64": base64.b64encode(pdf_bytes).decode("ascii"),
                    "invoice_filename": f"{invoice_no}.pdf",
                }

                backend_result = backend_post(request_payload, timeout=45)

                if backend_result.get("duplicate") is True:
                    st.session_state.booking_id = booking_id
                else:
                    st.session_state.booking_id = booking_id
                st.session_state.invoice_no = invoice_no
                st.session_state.invoice_pdf = pdf_bytes
                st.session_state.last_backend_error = None
                st.session_state.page = "success"
                st.rerun()

            except Exception as exc:
                err_msg = str(exc)
                if "already registered" in err_msg.lower():
                    # رفض حقيقي من السيرفر لأن رقم الجواز مسجل قبل كده —
                    # مش مشكلة إرسال، فمفيش داعي لعرض نسخة احتياطية هنا.
                    st.error("This passport number is already registered. The booking was stopped to prevent duplicate registration.")
                else:
                    # البيانات لسه محفوظة في session_state — المستخدم يقدر يحاول تاني
                    # من غير ما يعيد كتابة أي حاجة، وده اللي بيمنع ضياع التسجيلات.
                    st.session_state.last_backend_error = err_msg
                    st.session_state.pending_payload = payload_data
                    st.session_state.pending_pdf = pdf_bytes if "pdf_bytes" in dir() else None
                    st.error("The booking could not be submitted due to a transmission error. Your entered data is preserved and you can try again.")

    if st.session_state.get("last_backend_error"):
        with st.expander("Technical error details (for support)"):
            st.code(st.session_state.last_backend_error)
            if st.session_state.get("pending_payload"):
                backup_json = json.dumps(st.session_state.pending_payload, ensure_ascii=False, indent=2)
                st.download_button(
                    "⬇️ Download Booking Backup",
                    data=backup_json.encode("utf-8"),
                    file_name=f"{st.session_state.pending_payload.get('booking_id','booking')}_backup.json",
                    mime="application/json",
                    use_container_width=True,
                )

# =========================================================
# PAGE 5 — SUCCESS
# =========================================================
elif st.session_state.page == "success":
    if not st.session_state.booking_id:
        st.info("Preview mode: this is the completion page design. No booking has been submitted.")
        st.markdown('<div class="booking-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">🎉 Booking Completed</div>', unsafe_allow_html=True)
        st.write("**Booking ID:** BK-PREVIEW123")
        st.write("**Invoice Number:** INV-PREVIEW123")
        st.write("The real confirmation and invoice download appear here after a successful booking.")
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.balloons()
        st.success("🎉 Booking completed successfully!")

    st.markdown('<div class="booking-card">', unsafe_allow_html=True)
    st.write(f"**Booking ID:** {st.session_state.booking_id}")
    st.write(f"**Invoice Number:** {st.session_state.invoice_no}")
    st.info("The invoice has been sent to the registered email address.")
    st.markdown('</div>', unsafe_allow_html=True)

    if st.session_state.booking_id and st.session_state.invoice_pdf:
        st.download_button(
            "📄 Download Invoice",
            data=st.session_state.invoice_pdf,
            file_name=f"{st.session_state.invoice_no}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

    if st.session_state.booking_id and st.button("Create New Booking", use_container_width=True):
        for key in [
            "personal", "hotel", "transport", "booking_id",
            "invoice_no", "invoice_pdf", "last_backend_error", "pending_payload", "pending_pdf",
        ]:
            st.session_state.pop(key, None)
        st.session_state.page = "personal"
        st.rerun()

st.markdown(f'<div class="footer-note">{COMPANY_NAME} — {COMPANY_EMAIL}</div>', unsafe_allow_html=True)

# =========================================================
# ADMIN
# =========================================================
st.sidebar.divider()
st.sidebar.subheader("🔐 Admin Panel")

admin_password = st.sidebar.text_input("Admin Password", type="password")

if ADMIN_PASSWORD and admin_password == ADMIN_PASSWORD:
    st.sidebar.success("Successfully logged in")

    if st.sidebar.button("Load Bookings"):
        try:
            result = backend_post({
                "action": "admin_list",
                "admin_token": ADMIN_TOKEN,
            })
            rows = result.get("rows", [])
            if rows:
                st.sidebar.success(f"Loaded {len(rows)} bookings.")
                st.session_state.admin_rows = rows
            else:
                st.sidebar.info("No bookings found.")
        except Exception as exc:
            st.sidebar.error("Could not load bookings.")
            st.sidebar.caption(str(exc))

    if "admin_rows" in st.session_state:
        st.subheader("📋 Booking Dashboard")
        df = pd.DataFrame(st.session_state.admin_rows)

        search = st.text_input("🔍 Search (name, passport number, or email)")
        if search and not df.empty:
            mask = df.apply(lambda row: row.astype(str).str.contains(search, case=False, na=False).any(), axis=1)
            df_view = df[mask]
        else:
            df_view = df

        st.dataframe(df_view, use_container_width=True, hide_index=True)

        if "total" in df.columns:
            try:
                grand_total = pd.to_numeric(df["total"], errors="coerce").sum()
                st.markdown(
                    f'<div class="total-box">Total All Bookings: {money(grand_total)}</div>',
                    unsafe_allow_html=True,
                )
            except Exception:
                pass

        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "⬇️ Download Bookings CSV",
            csv,
            "bookings.csv",
            "text/csv",
            use_container_width=True,
        )
