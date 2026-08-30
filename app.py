"""23rd ITKF World Championship hotel booking application."""

from __future__ import annotations

import base64
import copy
import html
import importlib.util
import mimetypes
from datetime import date, timedelta, time as dt_time
from pathlib import Path
import uuid
from typing import Any

import streamlit as st

from config import (BORDER_COLOR, DEFAULT_COUNTRY_CODE, EVENT_TITLE, HEADER_BG_COLOR,
    HOTELS, LOGO_PATHS, ROOM_OCCUPANCY, SYSTEM_TITLE, TRANSPORT_SERVICES, TRANSPORTATION,
    APP_SCHEMA_VERSION, MAX_TRANSPORT_SERVICES)
from countries import countries, countries_by_name, country_for_code, validate_phone
from sheets import backend_is_configured, save_to_google_sheets, check_availability


st.set_page_config(
    page_title=f"{EVENT_TITLE} - {SYSTEM_TITLE}",
    page_icon="🏨",
    layout="centered",
    initial_sidebar_state="collapsed",
)


def _load_booking_helpers():
    """Load this app's helper file independently of a cached `helpers` module."""
    helper_path = Path(__file__).resolve().with_name("helpers.py")
    spec = importlib.util.spec_from_file_location("_itkf_booking_helpers", helper_path)
    if spec is None or spec.loader is None:
        st.error("Cannot load helpers.py. Upload it beside app.py, then reboot the app.")
        st.stop()
    module = importlib.util.module_from_spec(spec)
    # Do not mutate/reload sys.modules['helpers']: another session or dependency
    # may be using that object. Each run gets the adjacent project's source.
    spec.loader.exec_module(module)
    required = (
        "calculate_booking_totals", "generate_booking_id", "current_timestamp",
        "normalize_guest_name", "normalize_passport_number", "validate_booking",
        "format_currency", "price_transport_service", "vehicle_suggestions",
        "transport_schedule_dates",
    )
    missing = [name for name in required if not callable(getattr(module, name, None))]
    if missing:
        st.error("The application files are different versions. Replace helpers.py beside app.py with the latest supplied file, then reboot the app.")
        st.code("Missing functions: " + ", ".join(missing), language=None)
        st.stop()
    return module


_booking_helpers = _load_booking_helpers()
calculate_booking_totals = _booking_helpers.calculate_booking_totals
generate_booking_id = _booking_helpers.generate_booking_id
current_timestamp = _booking_helpers.current_timestamp
normalize_guest_name = _booking_helpers.normalize_guest_name
normalize_passport_number = _booking_helpers.normalize_passport_number
validate_booking = _booking_helpers.validate_booking
format_currency = _booking_helpers.format_currency
price_transport_service = _booking_helpers.price_transport_service
vehicle_suggestions = _booking_helpers.vehicle_suggestions
transport_schedule_dates = _booking_helpers.transport_schedule_dates


st.markdown(
    f"""
<style>
:root {{color-scheme: only light !important;}}
html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {{
    color-scheme: light !important;
    background-color:#FFFFFF !important; color:#1F2937 !important;
}}
.block-container {{padding-top: 1rem; max-width: 940px; padding-bottom: 2rem;}}
#MainMenu, footer {{visibility: hidden;}}
.itkf-header {{
    background: {HEADER_BG_COLOR}; border: 2px solid {BORDER_COLOR};
    border-radius: 0 0 18px 18px; padding: 18px; margin-bottom: 14px;
    box-shadow: 0 1px 7px rgba(0,0,0,.10);
}}
.itkf-logos-row {{
    display:flex; justify-content:center; align-items:center; gap:24px;
    flex-wrap:wrap; margin:2px 0 12px;
}}
.itkf-logo {{width:88px; height:88px; object-fit:contain; display:block;}}
.itkf-logo:first-child {{width:106px; height:106px;}}
.itkf-event-title {{text-align:center; font-size:26px; font-weight:800; color:#222;}}
.itkf-system-title {{text-align:center; font-size:15px; color:#666; margin-top:5px;}}
.itkf-section-title {{font-size:25px; font-weight:750; color:#374151; margin:26px 0 6px;}}
.itkf-section-help {{color:#6b7280; font-size:16px; margin-bottom:18px;}}
.itkf-price-box {{
    background:#fafafa; border:1px solid #e5e7eb; border-left:4px solid {BORDER_COLOR};
    border-radius:10px; padding:14px 16px; margin-top:12px;
}}
.itkf-card {{border:1px solid #e5e7eb; border-radius:12px; padding:14px; margin:8px 0;}}
/* Keep every app button readable even when the phone/browser forces Dark Mode. */
[data-testid="stAppViewContainer"] button {{
    color-scheme: only light !important;
}}
[data-testid="stAppViewContainer"] button:not([kind="primary"]):not([data-testid="baseButton-primary"]) {{
    background:#FFFFFF !important;
    background-image:none !important;
    color:#1F2937 !important;
    -webkit-text-fill-color:#1F2937 !important;
    border:1.5px solid #D1D5DB !important;
    box-shadow:none !important;
    opacity:1 !important;
}}
.stButton > button[kind="primary"],
button[data-testid="baseButton-primary"],
.stFormSubmitButton > button[kind="primary"] {{
    background:{BORDER_COLOR} !important;
    background-image:none !important;
    color:#FFFFFF !important;
    -webkit-text-fill-color:#FFFFFF !important;
    border:1.5px solid {BORDER_COLOR} !important;
    opacity:1 !important;
}}
[data-testid="stAppViewContainer"] button p,
[data-testid="stAppViewContainer"] button span,
[data-testid="stAppViewContainer"] button svg {{
    color:inherit !important;
    -webkit-text-fill-color:inherit !important;
}}
[data-testid="stAppViewContainer"] button:not(:disabled):hover {{
    border-color:{BORDER_COLOR} !important;
}}
[data-testid="stAppViewContainer"] button:disabled {{
    background:#F3F4F6 !important;
    background-image:none !important;
    color:#6B7280 !important;
    -webkit-text-fill-color:#6B7280 !important;
    border-color:#D1D5DB !important;
    opacity:1 !important;
}}

/* Force every form label, hint and field to stay light and readable. */
[data-testid="stAppViewContainer"] label,
[data-testid="stAppViewContainer"] label *,
[data-testid="stWidgetLabel"],
[data-testid="stWidgetLabel"] *,
[data-testid="stInputInstructions"],
[data-testid="stInputInstructions"] * {{
    color:#1F2937 !important;
    -webkit-text-fill-color:#1F2937 !important;
    opacity:1 !important;
}}

[data-testid="stAppViewContainer"] input:not([type="checkbox"]):not([type="radio"]),
[data-testid="stAppViewContainer"] textarea,
[data-testid="stAppViewContainer"] [role="combobox"],
[data-baseweb="input"],
[data-baseweb="base-input"],
[data-baseweb="textarea"],
[data-baseweb="select"] > div {{
    color-scheme: only light !important;
    background-color:#FFFFFF !important;
    background-image:none !important;
    color:#1F2937 !important;
    -webkit-text-fill-color:#1F2937 !important;
    opacity:1 !important;
}}

/* One thin border on the outer field only; inner input stays borderless. */
[data-baseweb="input"],
[data-baseweb="textarea"],
[data-baseweb="select"] > div {{
    border:1px solid #D1D5DB !important;
    box-shadow:none !important;
}}
[data-baseweb="base-input"],
[data-testid="stAppViewContainer"] input:not([type="checkbox"]):not([type="radio"]),
[data-testid="stAppViewContainer"] textarea {{
    border:0 !important;
    outline:0 !important;
    box-shadow:none !important;
}}
[data-baseweb="input"]:focus-within,
[data-baseweb="textarea"]:focus-within,
[data-baseweb="select"] > div:focus-within {{
    border-color:{BORDER_COLOR} !important;
    box-shadow:0 0 0 1px rgba(200,16,46,.12) !important;
}}

[data-baseweb="select"] > div *,
[data-baseweb="input"] svg,
[data-baseweb="textarea"] svg {{
    color:#1F2937 !important;
    fill:#1F2937 !important;
    -webkit-text-fill-color:#1F2937 !important;
}}

[data-testid="stAppViewContainer"] input::placeholder,
[data-testid="stAppViewContainer"] textarea::placeholder {{
    color:#6B7280 !important;
    -webkit-text-fill-color:#6B7280 !important;
    opacity:1 !important;
}}

[data-baseweb="input"]:has(input:disabled),
[data-baseweb="base-input"]:has(input:disabled),
[data-testid="stAppViewContainer"] input:disabled {{
    background-color:#F3F4F6 !important;
    color:#4B5563 !important;
    -webkit-text-fill-color:#4B5563 !important;
    opacity:1 !important;
}}

/* Light unchecked box and federation-red checked box. */
[data-testid="stCheckbox"] input[type="checkbox"] {{
    color-scheme: only light !important;
    accent-color:{BORDER_COLOR} !important;
}}
[data-testid="stCheckbox"] input[type="checkbox"] + div {{
    background-color:#FFFFFF !important;
    background-image:none !important;
    border:1px solid #9CA3AF !important;
    box-shadow:none !important;
}}
[data-testid="stCheckbox"] input[type="checkbox"]:checked + div {{
    background-color:{BORDER_COLOR} !important;
    border-color:{BORDER_COLOR} !important;
}}
[data-testid="stCheckbox"] input[type="checkbox"]:checked + div svg {{
    color:#FFFFFF !important;
    fill:#FFFFFF !important;
}}

[data-testid="stFileUploader"] section,
[data-testid="stFileUploaderDropzone"] {{
    color-scheme: only light !important;
    background-color:#F8FAFC !important;
    background-image:none !important;
    color:#1F2937 !important;
    border-color:#D1D5DB !important;
}}
[data-testid="stFileUploader"] section *,
[data-testid="stFileUploaderDropzone"] * {{
    color:#1F2937 !important;
    -webkit-text-fill-color:#1F2937 !important;
}}

/* Alert text must stay visible inside warning/info/success/error boxes. */
[data-testid="stAlert"],
[data-testid="stAlert"] *,
[data-testid="stAlert"] p,
[data-testid="stAlert"] span {{
    color-scheme: only light !important;
    color:#1F2937 !important;
    -webkit-text-fill-color:#1F2937 !important;
    opacity:1 !important;
}}
[data-testid="stAlert"] svg {{
    color:#1F2937 !important;
    fill:#1F2937 !important;
}}

[data-baseweb="popover"],
[data-baseweb="menu"],
[data-baseweb="calendar"],
[role="listbox"],
[role="option"] {{
    color-scheme: only light !important;
    background-color:#FFFFFF !important;
    color:#1F2937 !important;
    -webkit-text-fill-color:#1F2937 !important;
}}
[role="option"]:hover,
[role="option"][aria-selected="true"] {{
    background-color:#F3F4F6 !important;
}}

input[type="date"]::-webkit-calendar-picker-indicator {{
    color-scheme: only light !important;
    opacity:1 !important;
}}

div[data-testid="stHorizontalBlock"] .stButton > button {{min-height:44px; font-size:14px;}}
@media (prefers-color-scheme: dark) {{
    [data-testid="stAppViewContainer"] button:not([kind="primary"]):not([data-testid="baseButton-primary"]) {{
        background:#FFFFFF !important;
        background-image:none !important;
        color:#1F2937 !important;
        -webkit-text-fill-color:#1F2937 !important;
    }}
    [data-baseweb="input"],
    [data-baseweb="base-input"],
    [data-baseweb="textarea"],
    [data-baseweb="select"] > div,
    [data-testid="stAppViewContainer"] input,
    [data-testid="stAppViewContainer"] textarea {{
        background-color:#FFFFFF !important;
        background-image:none !important;
        color:#1F2937 !important;
        -webkit-text-fill-color:#1F2937 !important;
    }}
}}

/* Final mobile override: keep the latest fixes authoritative over browser auto-darkening. */
div[data-testid="stTextInput"] div[data-baseweb="input"],
div[data-testid="stNumberInput"] div[data-baseweb="input"],
div[data-testid="stDateInput"] div[data-baseweb="input"],
div[data-testid="stTextArea"] div[data-baseweb="textarea"],
div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {{
    color-scheme: only light !important;
    background:#FFFFFF !important;
    background-image:none !important;
    color:#1F2937 !important;
    -webkit-text-fill-color:#1F2937 !important;
    border-width:1px !important;
    border-style:solid !important;
    border-color:#D1D5DB !important;
    box-shadow:none !important;
}}
div[data-testid="stTextInput"] div[data-baseweb="base-input"],
div[data-testid="stNumberInput"] div[data-baseweb="base-input"],
div[data-testid="stDateInput"] div[data-baseweb="base-input"],
div[data-testid="stTextArea"] div[data-baseweb="base-input"] {{
    border:0 !important;
    box-shadow:none !important;
}}
div[data-testid="stCheckbox"] label[data-baseweb="checkbox"] > span:first-child,
div[data-testid="stCheckbox"] label[data-baseweb="checkbox"] > span:first-child > div,
div[data-testid="stCheckbox"] input[type="checkbox"] + div {{
    color-scheme: only light !important;
    background:#FFFFFF !important;
    background-image:none !important;
    border:1px solid #9CA3AF !important;
    box-shadow:none !important;
}}
div[data-testid="stCheckbox"] label[data-baseweb="checkbox"] > span:first-child:has(input:checked),
div[data-testid="stCheckbox"] label[data-baseweb="checkbox"] > span:first-child:has(input:checked) > div,
div[data-testid="stCheckbox"] input[type="checkbox"]:checked + div {{
    background:{BORDER_COLOR} !important;
    border-color:{BORDER_COLOR} !important;
}}
div[data-testid="stAlert"] [data-testid="stMarkdownContainer"],
div[data-testid="stAlert"] [data-testid="stMarkdownContainer"] *,
div[data-testid="stAlert"] p,
div[data-testid="stAlert"] span {{
    color:#1F2937 !important;
    -webkit-text-fill-color:#1F2937 !important;
    opacity:1 !important;
    visibility:visible !important;
}}

/* Streamlit widgets that use their own dark-mode surfaces. */
div[data-testid="stExpander"] details,
div[data-testid="stExpander"] summary {{
    color-scheme: only light !important;
    background:#FFFFFF !important;
    background-image:none !important;
    color:#1F2937 !important;
    -webkit-text-fill-color:#1F2937 !important;
}}
div[data-testid="stExpander"] summary *,
div[data-testid="stExpander"] details p {{
    color:#1F2937 !important;
    -webkit-text-fill-color:#1F2937 !important;
}}
div[data-testid="stExpander"] details a {{
    color:#0284C7 !important;
    -webkit-text-fill-color:#0284C7 !important;
}}

div[data-testid="stRadio"] input[type="radio"] {{
    color-scheme: only light !important;
    accent-color:{BORDER_COLOR} !important;
}}
div[data-testid="stRadio"] input[type="radio"] + div,
div[data-testid="stRadio"] label[data-baseweb="radio"] > div:first-of-type {{
    background:#FFFFFF !important;
    background-image:none !important;
    border-color:#9CA3AF !important;
    box-shadow:inset 0 0 0 20px #FFFFFF !important;
}}
div[data-testid="stRadio"] input[type="radio"]:checked + div,
div[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) > div:first-of-type {{
    background:{BORDER_COLOR} !important;
    border-color:{BORDER_COLOR} !important;
    box-shadow:inset 0 0 0 20px {BORDER_COLOR} !important;
}}
div[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) > div:first-of-type > div {{
    background:#FFFFFF !important;
}}

div[data-testid="stDateInput"] div[data-baseweb="input"],
div[data-testid="stDateInput"] div[data-baseweb="base-input"],
div[data-testid="stDateInput"] input,
div[data-testid*="DateInput"] div[data-baseweb="input"],
div[data-testid*="DateInput"] input {{
    color-scheme: only light !important;
    forced-color-adjust:none !important;
    background-color:#FFFFFF !important;
    background-image:none !important;
    color:#1F2937 !important;
    -webkit-text-fill-color:#1F2937 !important;
    box-shadow:inset 0 0 0 1000px #FFFFFF !important;
    -webkit-box-shadow:inset 0 0 0 1000px #FFFFFF !important;
}}

div[data-testid="stWidgetLabel"] button,
div[data-testid="stTooltipIcon"] button,
button[data-testid="stTooltipIcon"] {{
    color-scheme: only light !important;
    background:transparent !important;
    background-image:none !important;
    color:#6B7280 !important;
    -webkit-text-fill-color:#6B7280 !important;
    border:0 !important;
    box-shadow:none !important;
    opacity:1 !important;
}}
@media (max-width: 600px) {{
    .itkf-logo {{width:58px; height:58px;}}
    .itkf-logo:first-child {{width:72px; height:72px;}}
    .itkf-logos-row {{gap:10px;}}
    .itkf-event-title {{font-size:20px;}}
    div[data-testid="stHorizontalBlock"] .stButton > button {{font-size:11px; padding:.35rem .2rem;}}
}}
</style>
""",
    unsafe_allow_html=True,
)


def _logo_data_uri(path: Any) -> str | None:
    try:
        if not path or not path.exists():
            return None
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"
    except OSError:
        return None


def render_header() -> None:
    logos: list[str] = []
    for key in ("logo1", "logo2", "logo3"):
        uri = _logo_data_uri(LOGO_PATHS.get(key))
        if uri:
            logos.append(
                f'<img class="itkf-logo" src="{uri}" alt="{html.escape(key)}">'
            )
    st.markdown(
        f"""
        <div class="itkf-header">
          <div class="itkf-logos-row">{''.join(logos)}</div>
          <div class="itkf-event-title">{html.escape(EVENT_TITLE)}</div>
          <div class="itkf-system-title">{html.escape(SYSTEM_TITLE)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_title(icon: str, title: str, help_text: str = "") -> None:
    st.markdown(
        f'<div class="itkf-section-title">{icon} {html.escape(title)}</div>',
        unsafe_allow_html=True,
    )
    if help_text:
        st.markdown(
            f'<div class="itkf-section-help">{html.escape(help_text)}</div>',
            unsafe_allow_html=True,
        )


def first_choices():
    hotel = next(iter(HOTELS))
    plan = next(iter(HOTELS[hotel]["rates"]))
    return hotel, plan, next(iter(HOTELS[hotel]["rates"][plan]))

DEFAULT_HOTEL, DEFAULT_MEAL, DEFAULT_ROOM = first_choices()
DEFAULT_COUNTRY = country_for_code(DEFAULT_COUNTRY_CODE)
DEFAULTS = {
    "current_page": "Registration", "registration_type": "",
    "guest_name": "", "date_of_birth": None, "passport_number": "",
    "nationality": DEFAULT_COUNTRY.name,
    "individual_phone": DEFAULT_COUNTRY.calling_code, "individual_email": "",
    "federation_name": "", "federation_phone": "+", "federation_email": "",
    "hotel": DEFAULT_HOTEL, "meal_plan": DEFAULT_MEAL, "room_type": DEFAULT_ROOM,
    "check_in": date.today(), "check_out": date.today() + timedelta(days=1),
    "wants_transportation": False, "transport_ids": [],
    "last_booking": None, "pending_submission": None, "pending_error": "",
}
for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value
# Keep widget values across wizard pages and dynamic sections.
for key in list(st.session_state):
    if key in DEFAULTS or (key.startswith(("rq_", "tr_")) and not key.endswith("_remove")):
        st.session_state[key] = st.session_state[key]

PAGES = ["Personal", "Hotel", "Transportation", "Review", "Complete"]
def go_to(page):
    st.session_state.current_page = page

def choose_registration(kind):
    st.session_state.registration_type = kind
    go_to("Personal")

def render_navigation():
    st.button("← Registration type", key="nav_Registration", on_click=go_to, args=("Registration",))
    for col, page in zip(st.columns(len(PAGES)), PAGES):
        with col:
            st.button("Transport" if page == "Transportation" else page,
                      key="nav_" + page, use_container_width=True,
                      type="primary" if page == st.session_state.current_page else "secondary",
                      on_click=go_to, args=(page,))

def render_step_navigation(back=None, next_page=None):
    st.write("")
    left, right = st.columns(2)
    if back:
        left.button("← Back", key="back_" + st.session_state.current_page,
                    use_container_width=True, on_click=go_to, args=(back,))
    if next_page:
        right.button("Next →", key="next_" + st.session_state.current_page,
                     type="primary", use_container_width=True, on_click=go_to, args=(next_page,))

def normalize_hotel_state():
    state = st.session_state
    if state.hotel not in HOTELS:
        state.hotel = DEFAULT_HOTEL
    plans = HOTELS[state.hotel]["rates"]
    if state.meal_plan not in plans:
        state.meal_plan = next(iter(plans))
    if state.room_type not in plans[state.meal_plan]:
        state.room_type = next(iter(plans[state.meal_plan]))
    for room in plans[state.meal_plan]:
        key = room_key(room)
        if key not in state:
            state[key] = 1 if room == next(iter(plans[state.meal_plan])) else 0

def room_key(room):
    return "rq_" + st.session_state.hotel + "_" + room

def ensure_checkout():
    if st.session_state.check_out <= st.session_state.check_in:
        st.session_state.check_out = st.session_state.check_in + timedelta(days=1)

def sync_country():
    country = countries_by_name()[st.session_state.nationality]
    old_prefix = st.session_state.get("last_phone_prefix", DEFAULT_COUNTRY.calling_code)
    if st.session_state.individual_phone.strip() in ("", "+", old_prefix):
        st.session_state.individual_phone = country.calling_code
    st.session_state.last_phone_prefix = country.calling_code

def normalize_name():
    st.session_state.guest_name = normalize_guest_name(st.session_state.guest_name)

def normalize_passport():
    st.session_state.passport_number = normalize_passport_number(st.session_state.passport_number)

def selected_rooms():
    normalize_hotel_state()
    if st.session_state.registration_type == "Individual":
        return [{"room_type": st.session_state.room_type, "quantity": 1}]
    return [{"room_type": room, "quantity": int(st.session_state[room_key(room)])}
            for room in HOTELS[st.session_state.hotel]["rates"][st.session_state.meal_plan]
            if st.session_state[room_key(room)] > 0]

def add_transport():
    if len(st.session_state.transport_ids) >= MAX_TRANSPORT_SERVICES:
        return
    ident = uuid.uuid4().hex[:10]
    st.session_state.transport_ids = st.session_state.transport_ids + [ident]
    defaults = {"date": st.session_state.check_in, "service": next(iter(TRANSPORT_SERVICES)),
                "direction": "Airport to Hotel", "start": dt_time(9, 0), "end": dt_time(10, 0),
                "next_day": False,
                "persons": max(1, sum(r["quantity"] * ROOM_OCCUPANCY[r["room_type"]] for r in selected_rooms()))}
    for name, value in defaults.items():
        st.session_state[f"tr_{ident}_{name}"] = value
    for index in range(len(TRANSPORTATION)):
        st.session_state[f"tr_{ident}_v{index}"] = 0
    ensure_transport_schedule_state(ident)

def ensure_transport_schedule_state(ident):
    """Also migrate an in-progress single-date service without losing its inputs."""
    prefix = f"tr_{ident}_"
    first = st.session_state[prefix+"date"]
    defaults = {"date_mode": "One date", "range_start": first,
                "range_end": max(first, st.session_state.check_out - timedelta(days=1)),
                "excluded_dates": [], "selected_dates": [], "date_options": [], "pick_date": first}
    for name, value in defaults.items():
        if prefix+name not in st.session_state:
            st.session_state[prefix+name] = value

def add_selected_transport_date(ident):
    prefix = f"tr_{ident}_"
    picked = st.session_state[prefix+"pick_date"]
    selected = st.session_state[prefix+"selected_dates"]
    if isinstance(picked, date) and (picked in selected or len(selected) < MAX_TRANSPORT_SERVICES):
        st.session_state[prefix+"date_options"] = sorted(set(st.session_state[prefix+"date_options"] + [picked]))
        st.session_state[prefix+"selected_dates"] = sorted(set(selected + [picked]))

def duplicate_transport(ident):
    if len(st.session_state.transport_ids) >= MAX_TRANSPORT_SERVICES:
        return
    new_id = uuid.uuid4().hex[:10]
    prefix = f"tr_{ident}_"
    for key in list(st.session_state):
        if key.startswith(prefix) and not key.endswith("_remove"):
            st.session_state[f"tr_{new_id}_"+key[len(prefix):]] = copy.deepcopy(st.session_state[key])
    st.session_state.transport_ids = st.session_state.transport_ids + [new_id]

def remove_transport(ident):
    st.session_state.transport_ids = [item for item in st.session_state.transport_ids if item != ident]

def transport_dates_from_state(ident):
    ensure_transport_schedule_state(ident)
    key = lambda name: st.session_state[f"tr_{ident}_{name}"]
    return transport_schedule_dates(key("date_mode"), single_date=key("date"),
        start_date=key("range_start"), end_date=key("range_end"),
        selected_dates=key("selected_dates"), excluded_dates=key("excluded_dates"))

def transport_template_from_state(ident):
    key = lambda name: st.session_state[f"tr_{ident}_{name}"]
    return {"service": key("service"),
            "direction": key("direction") if TRANSPORT_SERVICES[key("service")]["directions"] else "",
            "start_time": key("start").strftime("%H:%M"), "end_time": key("end").strftime("%H:%M"),
            "ends_next_day": key("next_day"), "persons": key("persons"),
            "vehicles": {name: key(f"v{i}") for i, name in enumerate(TRANSPORTATION) if key(f"v{i}") > 0}}

def transport_from_state():
    if not st.session_state.wants_transportation:
        return []
    items = []
    for order, ident in enumerate(st.session_state.transport_ids, 1):
        try:
            dates = transport_dates_from_state(ident)
            template = transport_template_from_state(ident)
            items.extend({**copy.deepcopy(template), "date": value} for value in dates)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Service {order}: {exc}") from exc
    if len(items) > MAX_TRANSPORT_SERVICES:
        raise ValueError(f"Choose at most {MAX_TRANSPORT_SERVICES} dated services in one request. Each repeated date counts as one service.")
    return items

def booking_from_state():
    state = st.session_state
    normalize_hotel_state()
    individual = state.registration_type == "Individual"
    country = countries_by_name()[state.nationality]
    phone_input = state.individual_phone if individual else state.federation_phone
    valid, phone, _ = validate_phone(country.iso2 if individual else "EG", phone_input)
    if not individual and not phone_input.strip().startswith("+"):
        valid = False
    raw = {"schema_version": APP_SCHEMA_VERSION, "registration_type": state.registration_type,
           "guest_name": normalize_guest_name(state.guest_name) if individual else "",
           "federation_name": state.federation_name.strip() if not individual else "",
           "passport_number": normalize_passport_number(state.passport_number) if individual else "",
           "date_of_birth": state.date_of_birth.isoformat() if individual and state.date_of_birth else "",
           "nationality": country.name if individual else "", "nationality_code": country.iso2 if individual else "",
           "phone": phone if valid else "", "phone_valid": valid,
           "email": (state.individual_email if individual else state.federation_email).strip(),
           "hotel": state.hotel, "meal_plan": state.meal_plan, "rooms": selected_rooms(),
           "check_in": state.check_in.isoformat(), "check_out": state.check_out.isoformat()}
    try:
        raw["transport_services"] = transport_from_state()
    except (ValueError, TypeError) as exc:
        raw["transport_services"] = []
        raw["transport_schedule_error"] = str(exc)
    return raw

def render_price_box(totals):
    st.markdown(
        '<div class="itkf-price-box">Accommodation: ' + format_currency(totals["room_total_eur"]) +
        '<br>Transportation: ' + format_currency(totals["transport_total_eur"]) +
        '<hr><b>Total: ' + format_currency(totals["grand_total_eur"]) + '</b></div>',
        unsafe_allow_html=True)

def show_summary(raw):
    name = raw.get("federation_name") if raw.get("registration_type") == "Federation" else raw.get("guest_name")
    st.write(f"Registration: {raw.get('registration_type', '-')}")
    st.write(f"Name: {name or '-'}")
    st.write(f"Email: {raw.get('email') or '-'}")
    st.write(f"Phone: {raw.get('phone') or '-'}")
    if raw.get("registration_type") == "Individual":
        st.write(f"Passport number: {raw.get('passport_number') or '-'}")
        st.write(f"Date of birth: {raw.get('date_of_birth') or '-'}")
        st.write(f"Nationality: {raw.get('nationality') or '-'}")
    st.subheader("Hotel")
    st.write(f"{raw['hotel']} · {raw['meal_plan']}")
    st.write(f"Check-in: {raw['check_in']} · Check-out: {raw['check_out']}")
    if raw.get("transport_schedule_error"):
        st.info("Complete the transportation dates before reviewing the final total.")
        return
    try:
        totals = calculate_booking_totals(raw)
        for room in totals["rooms"]:
            st.write(f"{room['room_type']} × {room['quantity']} rooms · {format_currency(room['total_eur'])}")
        st.write(f"Nights: {totals['nights']} · Guests: {totals['guests']}")
        if totals["transport_services"]:
            st.subheader("Transportation")
        for i, service in enumerate(totals["transport_services"], 1):
            next_day = " (+1 day)" if service["ends_next_day"] else ""
            st.write(f"{i}. {service['date']} · {service['service']} · {service.get('direction', '')}")
            st.write(f"{service['start_time']}–{service['end_time']}{next_day} (Cairo time)")
            st.write(f"Passengers: {service['persons']} · Seats: {service['seats']}")
            for line in service["vehicle_lines"]:
                st.write(f"{line['vehicle']} × {line['quantity']} · {format_currency(line['total_eur'])}")
        render_price_box(totals)
    except (ValueError, TypeError, KeyError) as exc:
        st.info(str(exc))

def attempt_save(record):
    st.session_state.pending_submission = record
    with st.spinner("Saving your request..."):
        result = save_to_google_sheets(record)
    if not result.saved:
        st.session_state.pending_error = result.message
        # Only clear a request when the server explicitly rejected it BEFORE reserving rooms.
        if result.data.get("error_code") in ("VALIDATION_ERROR", "DUPLICATE_PASSPORT", "SOLD_OUT", "QUOTE_CHANGED", "SCHEMA_VERSION"):
            st.session_state.pending_submission = None
        st.rerun()
    booking = {**record, **result.data}
    st.session_state.last_booking = booking
    st.session_state.submitted_record = record
    st.session_state.pending_submission = None
    st.session_state.pending_error = ""
    st.rerun()

normalize_hotel_state()
render_header()
if not st.session_state.registration_type:
    st.session_state.current_page = "Registration"
if st.session_state.current_page == "Registration":
    section_title("🥋", "Choose Your Registration Type", "Select one option to begin your booking request.")
    with st.container(border=True):
        st.subheader("Federation Registration")
        st.write("Book for your federation or delegation, with multiple rooms and group transportation.")
        st.button("Continue as a Federation →", key="choose_Federation", type="primary",
                  use_container_width=True, on_click=choose_registration, args=("Federation",))
    with st.container(border=True):
        st.subheader("Individual Registration")
        st.write("Book one room using your personal and passport details, with optional transportation.")
        st.button("Continue as an Individual →", key="choose_Individual", type="primary",
                  use_container_width=True, on_click=choose_registration, args=("Individual",))
    st.stop()
render_navigation()
page = st.session_state.current_page
if page == "Personal":
    section_title("📝", "Registration Details")
    st.caption("Registration type: " + st.session_state.registration_type)
    if st.session_state.registration_type == "Individual":
        st.text_input("Full Name (CAPITAL LETTERS) *", key="guest_name", on_change=normalize_name, max_chars=150)
        left, right = st.columns(2)
        left.text_input("Passport Number *", key="passport_number", on_change=normalize_passport, max_chars=20)
        right.date_input("Date of Birth *", key="date_of_birth", min_value=date(1900,1,1), max_value=date.today(), format="YYYY-MM-DD")
        st.selectbox("Nationality *", [c.name for c in countries()], key="nationality", on_change=sync_country)
        st.text_input("Phone Number (including country code) *", key="individual_phone", placeholder="+201012345678")
        st.text_input("Email *", key="individual_email")
        phone_value = st.session_state.individual_phone
    else:
        st.text_input("Federation Name *", key="federation_name", max_chars=150)
        st.text_input("Federation Email *", key="federation_email")
        st.text_input("Federation Phone (including country code) *", key="federation_phone", placeholder="+201012345678")
        phone_value = st.session_state.federation_phone
    raw = booking_from_state()
    if len(phone_value.strip()) > 5:
        if raw["phone_valid"]:
            st.caption(f"Phone: {raw['phone']}")
        else:
            st.error("Please enter a valid phone number including the country code.")
    render_step_navigation(back="Registration", next_page="Hotel")

elif page == "Hotel":
    section_title("🏨", "Hotel & Rooms", "Choose your rooms and stay dates.")
    st.selectbox("Select Hotel *", list(HOTELS), key="hotel", on_change=normalize_hotel_state)
    info = HOTELS[st.session_state.hotel]
    with st.expander("🏨 Hotel Details"):
        st.write(f"Stars: {info['stars']} · Distance to Arena: {info['distance_to_arena']}")
        st.write(info["location"])
        if info.get("website"):
            st.markdown(f"[Hotel website]({info['website']})")
        if info.get("notes"):
            st.write(info["notes"])
    st.radio("Meal Plan *", list(info["rates"]), key="meal_plan", horizontal=True, on_change=normalize_hotel_state)
    rates = info["rates"][st.session_state.meal_plan]
    if st.session_state.registration_type == "Individual":
        st.selectbox("Room Type *", list(rates), key="room_type")
        st.info(f"Number of guests: {ROOM_OCCUPANCY[st.session_state.room_type]}")
    else:
        for room, rate in rates.items():
            st.number_input(f"{room} — {format_currency(rate)} / room / night", min_value=0,
                            max_value=5000, step=1, key=room_key(room))
        st.caption("Guests (automatic): " + str(sum(r["quantity"] * ROOM_OCCUPANCY[r["room_type"]] for r in selected_rooms())))
    left, right = st.columns(2)
    left.date_input("Check-in Date *", key="check_in", on_change=ensure_checkout, format="YYYY-MM-DD")
    right.date_input("Check-out Date *", key="check_out", format="YYYY-MM-DD")
    raw = booking_from_state()
    try:
        totals = calculate_booking_totals({**raw, "transport_services": []})
        st.info(f"Number of nights: {totals['nights']} · Number of rooms: {totals['room_count']}")
        render_price_box(totals)
        if st.button("Check room availability", disabled=not backend_is_configured(), use_container_width=True):
            result = check_availability(raw)
            if result.get("ok"):
                for room in result["availability"]:
                    st.write(f"{room['room_type']}: {room['remaining']} room(s) available throughout this stay.")
            else:
                st.error(result.get("error", "Unable to check availability."))
    except (ValueError, TypeError, KeyError) as exc:
        st.error(str(exc))
    render_step_navigation(back="Personal", next_page="Transportation")

elif page == "Transportation":
    section_title("🚐", "Transportation", "Whole-vehicle prices in EUR. All times are Cairo local time.")
    st.checkbox("I need transportation", key="wants_transportation")
    if st.session_state.wants_transportation:
        if not st.session_state.transport_ids:
            add_transport()
        for order, ident in enumerate(list(st.session_state.transport_ids), 1):
            ensure_transport_schedule_state(ident)
            prefix = f"tr_{ident}_"
            with st.expander(f"Service {order}", expanded=True):
                st.selectbox("Service Type", list(TRANSPORT_SERVICES), key=prefix+"service",
                             format_func=lambda v: TRANSPORT_SERVICES[v]["label"])
                service = st.session_state[prefix+"service"]
                directions = TRANSPORT_SERVICES[service]["directions"]
                if directions:
                    if st.session_state[prefix+"direction"] not in directions:
                        st.session_state[prefix+"direction"] = directions[0]
                    st.selectbox("Direction", directions, key=prefix+"direction")
                st.selectbox("When do you need this service?", ["One date", "Date range", "Specific dates"],
                             key=prefix+"date_mode",
                             format_func=lambda v: {"One date":"One date", "Date range":"Repeat daily — from / to", "Specific dates":"Choose specific dates"}[v])
                mode = st.session_state[prefix+"date_mode"]
                if mode == "One date":
                    st.date_input("Service Date", key=prefix+"date", format="YYYY-MM-DD")
                elif mode == "Date range":
                    a, b = st.columns(2)
                    a.date_input("First service date", key=prefix+"range_start", format="YYYY-MM-DD")
                    b.date_input("Last service date", key=prefix+"range_end", format="YYYY-MM-DD")
                    st.caption("Both dates are included. The same vehicles and times apply to every selected day.")
                    try:
                        options = [date.fromisoformat(value) for value in transport_schedule_dates("Date range",
                            start_date=st.session_state[prefix+"range_start"], end_date=st.session_state[prefix+"range_end"])]
                        st.session_state[prefix+"excluded_dates"] = [value for value in st.session_state[prefix+"excluded_dates"] if value in options]
                        st.multiselect("Skip dates (optional)", options, key=prefix+"excluded_dates",
                                       format_func=lambda v: v.strftime("%a, %d %b %Y"))
                    except (ValueError, TypeError):
                        pass  # The shared validation below displays the exact problem.
                else:
                    st.date_input("Pick a date", key=prefix+"pick_date", format="YYYY-MM-DD")
                    st.button("＋ Add selected date", key="action_add_date_"+ident,
                              on_click=add_selected_transport_date, args=(ident,),
                              disabled=len(st.session_state[prefix+"selected_dates"]) >= MAX_TRANSPORT_SERVICES)
                    st.multiselect("Selected service dates", st.session_state[prefix+"date_options"],
                                   key=prefix+"selected_dates", format_func=lambda v: v.strftime("%a, %d %b %Y"))
                    st.caption("Add each date once. Remove a date using its ×. The same vehicles and times apply to all selected dates.")
                a, b = st.columns(2)
                a.time_input("From", key=prefix+"start")
                b.time_input("To", key=prefix+"end")
                st.checkbox("End time is on the next day", key=prefix+"next_day")
                st.number_input("Passengers to transport", min_value=1, max_value=5000, key=prefix+"persons")
                st.caption("Select the quantity of each vehicle you need:")
                for i, (name, vehicle) in enumerate(TRANSPORTATION.items()):
                    st.number_input(f"{name} — {format_currency(vehicle['prices_eur'][service])} / vehicle",
                                    min_value=0, max_value=100, step=1, key=prefix+f"v{i}")
                try:
                    dates = transport_dates_from_state(ident)
                    priced = price_transport_service({**transport_template_from_state(ident), "date": dates[0]})
                    st.write(f"Seats selected: {priced['seats']} · Passengers: {priced['persons']}")
                    if priced["remaining"]:
                        st.warning(f"{priced['remaining']} passengers still need seats. Select an additional vehicle.")
                        fits = vehicle_suggestions(priced["remaining"])
                        st.caption("Suitable additional vehicles: " + (", ".join(fits) if fits else "Select multiple vehicles."))
                    else:
                        st.success(f"All passengers have seats. Unused seats: {priced['seats'] - priced['persons']}")
                    st.info(f"{len(dates)} date(s) × {format_currency(priced['total_eur'])} per date = {format_currency(priced['total_eur'] * len(dates))}")
                    with st.expander("View selected dates"):
                        st.write(", ".join(dates))
                except (ValueError, TypeError, KeyError) as exc:
                    st.error(str(exc))
                st.button("Remove this service", key=prefix+"remove", on_click=remove_transport, args=(ident,))
                st.button("Duplicate service", key="action_duplicate_"+ident, on_click=duplicate_transport, args=(ident,),
                          disabled=len(st.session_state.transport_ids) >= MAX_TRANSPORT_SERVICES)
        st.button("＋ Add another service", on_click=add_transport,
                  disabled=len(st.session_state.transport_ids) >= MAX_TRANSPORT_SERVICES)
        try:
            services = transport_from_state()
            total = sum(price_transport_service(item)["total_eur"] for item in services)
            st.write(f"All transportation: {len(services)} dated service(s) · {format_currency(total)}")
        except (ValueError, TypeError, KeyError) as exc:
            st.warning(str(exc))
        st.caption("Prices include 14% VAT. Each transfer price is for one direction; daily hire is charged at the selected package price.")
    render_step_navigation(back="Hotel", next_page="Review")

elif page == "Review":
    section_title("🔎", "Review Your Request")
    raw = booking_from_state()
    for error in validate_booking(raw):
        st.warning(error)
    show_summary(raw)
    render_step_navigation(back="Transportation", next_page="Complete")

elif page == "Complete":
    section_title("✅", "Submit Request")
    if st.session_state.last_booking:
        saved = st.session_state.last_booking
        st.success(f"Your booking request has been received successfully. Request ID: {saved['booking_id']}")
        st.info(f"Invoice / summary number: {saved.get('invoice_no', '-')}")
        if saved.get("_invoice_pdf_bytes"):
            st.download_button("Download PDF", data=saved["_invoice_pdf_bytes"],
                               file_name=saved["invoice_no"]+".pdf", mime="application/pdf", use_container_width=True)
        if not saved.get("invoice_created"):
            st.warning("Your request is saved. Saving the PDF copy is pending.")
        if saved.get("customer_email_sent"):
            st.success("The PDF was emailed to " + saved["email"])
        else:
            st.info("Your request is saved. Email delivery is pending.")
        if not saved.get("invoice_created") or not saved.get("customer_email_sent"):
            if st.button("Retry PDF / email", use_container_width=True):
                attempt_save(st.session_state.submitted_record)
        if st.button("Start a new request", use_container_width=True):
            st.session_state.clear()
            st.rerun()
    else:
        if st.session_state.pending_error:
            st.error(st.session_state.pending_error)
        if st.session_state.pending_submission:
            st.info("We have not yet received a final response. Retry the same request safely; do not create another request.")
            st.caption("Request ID: " + st.session_state.pending_submission["booking_id"])
            if st.button("Retry saving", type="primary"):
                attempt_save(st.session_state.pending_submission)
        else:
            raw = booking_from_state()
            errors = validate_booking(raw)
            for error in errors:
                st.error(error)
            if not backend_is_configured():
                st.warning("The booking service is not configured.")
            if st.button("Submit Booking Request", type="primary", use_container_width=True,
                         disabled=bool(errors) or not backend_is_configured()):
                record = {**raw, **calculate_booking_totals(raw),
                          "booking_id": generate_booking_id(), "booking_date": current_timestamp()}
                attempt_save(record)
        render_step_navigation(back="Review")
