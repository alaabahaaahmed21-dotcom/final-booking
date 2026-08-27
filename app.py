"""23rd ITKF World Championship hotel booking application."""

from __future__ import annotations

import base64
import html
import mimetypes
from datetime import date, timedelta
from typing import Any

import streamlit as st

from config import (
    BORDER_COLOR,
    DEFAULT_COUNTRY_CODE,
    EVENT_TITLE,
    HEADER_BG_COLOR,
    HOTELS,
    LOGO_PATHS,
    MAX_BOOKING_NIGHTS,
    MAX_IMAGE_SIZE_MB,
    REQUIRE_PASSPORT_PHOTO,
    REQUIRE_PERSONAL_PHOTO,
    ROOM_OCCUPANCY,
    SYSTEM_TITLE,
    TRANSPORTATION,
)
from countries import countries, countries_by_name, country_for_code, validate_phone
from helpers import (
    calculate_booking_totals,
    calculate_nights,
    current_timestamp,
    format_currency,
    generate_booking_id,
    validate_booking,
)
from pdf_generator import generate_pdf
from sheets import backend_is_configured, save_to_google_sheets
from uploads import validate_uploaded_image


st.set_page_config(
    page_title=f"{EVENT_TITLE} - {SYSTEM_TITLE}",
    page_icon="🥋",
    layout="centered",
    initial_sidebar_state="collapsed",
)


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


def _first_hotel_defaults() -> tuple[str, str, str]:
    hotel = next(iter(HOTELS))
    meal = next(iter(HOTELS[hotel]["rates"]))
    room = next(iter(HOTELS[hotel]["rates"][meal]))
    return hotel, meal, room


DEFAULT_HOTEL, DEFAULT_MEAL, DEFAULT_ROOM = _first_hotel_defaults()
DEFAULT_COUNTRY = country_for_code(DEFAULT_COUNTRY_CODE)
DEFAULTS = {
    "current_page": "Personal",
    "guest_name": "",
    "nationality": DEFAULT_COUNTRY.name,
    "nationality_code": DEFAULT_COUNTRY.iso2,
    "phone_country_code": DEFAULT_COUNTRY.calling_code,
    "phone_national": "",
    "phone": "",
    "phone_valid": False,
    "email": "",
    "personal_photo": None,
    "passport_photo": None,
    "hotel": DEFAULT_HOTEL,
    "_hotel_context": DEFAULT_HOTEL,
    "meal_plan": DEFAULT_MEAL,
    "room_type": DEFAULT_ROOM,
    "guests": 1,
    "check_in": date.today(),
    "check_out": date.today() + timedelta(days=1),
    "wants_transportation": False,
    "vehicle_type": next(iter(TRANSPORTATION)) if TRANSPORTATION else None,
    "transport_persons": 1,
    "booking_submitted": False,
    "last_booking": None,
    "pending_submission": None,
    "pending_error": "",
}

for state_key, default_value in DEFAULTS.items():
    if state_key not in st.session_state:
        st.session_state[state_key] = default_value


PAGES = ["Personal", "Hotel", "Transportation", "Review", "Complete"]
PAGE_LABELS = {
    "Personal": "Personal",
    "Hotel": "Hotel",
    "Transportation": "Transport",
    "Review": "Review",
    "Complete": "Complete",
}


def go_to(page: str) -> None:
    st.session_state.current_page = page


def render_navigation() -> None:
    columns = st.columns(len(PAGES))
    for column, page_name in zip(columns, PAGES):
        with column:
            st.button(
                PAGE_LABELS[page_name],
                key=f"nav_{page_name}",
                use_container_width=True,
                type="primary" if st.session_state.current_page == page_name else "secondary",
                on_click=go_to,
                args=(page_name,),
            )


def _normalize_hotel_state() -> None:
    hotel = st.session_state.get("hotel")
    if hotel not in HOTELS:
        st.session_state.hotel = DEFAULT_HOTEL
        hotel = DEFAULT_HOTEL

    if st.session_state.get("_hotel_context") != hotel:
        meal = next(iter(HOTELS[hotel]["rates"]))
        room = next(iter(HOTELS[hotel]["rates"][meal]))
        st.session_state.meal_plan = meal
        st.session_state.room_type = room
        st.session_state.guests = 1
        st.session_state._hotel_context = hotel

    plans = HOTELS[hotel]["rates"]
    if st.session_state.get("meal_plan") not in plans:
        st.session_state.meal_plan = next(iter(plans))
    rooms = plans[st.session_state.meal_plan]
    if st.session_state.get("room_type") not in rooms:
        st.session_state.room_type = next(iter(rooms))
    expected_guests = ROOM_OCCUPANCY.get(st.session_state.room_type, 1)
    if int(st.session_state.get("guests", 0)) != expected_guests:
        st.session_state.guests = expected_guests


def _sync_guests_to_room() -> None:
    """Set the exact guest count represented by the selected room type."""

    st.session_state.guests = ROOM_OCCUPANCY.get(
        st.session_state.get("room_type", DEFAULT_ROOM), 1
    )


def _ensure_checkout() -> None:
    if st.session_state.check_out <= st.session_state.check_in:
        st.session_state.check_out = st.session_state.check_in + timedelta(days=1)


def _sync_country() -> None:
    country = countries_by_name().get(st.session_state.get("nationality"))
    if country is None:
        country = DEFAULT_COUNTRY
        st.session_state.nationality = country.name
    st.session_state.nationality_code = country.iso2
    st.session_state.phone_country_code = country.calling_code


def current_nights() -> int:
    try:
        return calculate_nights(st.session_state.check_in, st.session_state.check_out)
    except (AttributeError, TypeError):
        return 0


def current_transport_rates() -> dict[str, float | None]:
    return {
        name: details.get("price_per_person_eur")
        for name, details in TRANSPORTATION.items()
    }


def current_totals() -> dict[str, float | bool | None]:
    _normalize_hotel_state()
    transport_rates = current_transport_rates()
    return calculate_booking_totals(
        st.session_state.hotel,
        st.session_state.meal_plan,
        st.session_state.room_type,
        current_nights(),
        bool(st.session_state.wants_transportation),
        st.session_state.vehicle_type,
        int(st.session_state.transport_persons),
        transport_rates,
    )


def render_price_box(totals: dict[str, float | bool | None]) -> None:
    if totals.get("transport_price_pending"):
        transport_line = "<b>Transportation:</b> Price pending"
    else:
        unit_price = totals.get("transport_price_per_person_eur") or 0.0
        transport_line = (
            f"<b>Transportation:</b> {format_currency(float(totals['transport_total_eur']), 'EUR')} "
            f"({format_currency(float(unit_price), 'EUR')} per person)"
        )
    st.markdown(
        f"""
        <div class="itkf-price-box">
          <b>Room total:</b> {format_currency(float(totals['room_total_eur']), 'EUR')}<br>
          {transport_line}
          <hr style="margin:8px 0;">
          <b>Grand total - EUR:</b> {format_currency(float(totals['grand_total_eur']), 'EUR')}<br>
          <b>USD:</b> {format_currency(float(totals['grand_total_usd']), 'USD')}
          &nbsp; | &nbsp;
          <b>EGP:</b> {format_currency(float(totals['grand_total_egp']), 'EGP')}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _process_upload(uploaded: Any, state_key: str) -> None:
    if uploaded is None:
        return
    token_key = f"_{state_key}_token"
    token = (getattr(uploaded, "name", ""), getattr(uploaded, "size", None))
    if st.session_state.get(token_key) == token and st.session_state.get(state_key):
        return
    try:
        st.session_state[state_key] = validate_uploaded_image(uploaded)
        st.session_state[token_key] = token
    except ValueError as exc:
        st.session_state[state_key] = None
        st.session_state.pop(token_key, None)
        st.error(str(exc))


def _remove_upload(state_key: str, widget_key: str) -> None:
    st.session_state[state_key] = None
    st.session_state.pop(f"_{state_key}_token", None)
    st.session_state.pop(widget_key, None)


def booking_from_state() -> dict[str, Any]:
    nights = current_nights()
    totals = current_totals()
    return {
        "guest_name": str(st.session_state.get("guest_name", "")).strip(),
        "nationality": str(st.session_state.get("nationality", "")).strip(),
        "nationality_code": str(st.session_state.get("nationality_code", "")).strip(),
        "phone_country_code": str(st.session_state.get("phone_country_code", "")).strip(),
        "phone": str(st.session_state.get("phone", "")).strip(),
        "phone_valid": bool(st.session_state.get("phone_valid", False)),
        "email": str(st.session_state.get("email", "")).strip(),
        "personal_photo": st.session_state.get("personal_photo"),
        "passport_photo": st.session_state.get("passport_photo"),
        "hotel": st.session_state.hotel,
        "meal_plan": st.session_state.meal_plan,
        "room_type": st.session_state.room_type,
        "guests": int(st.session_state.guests),
        "check_in": st.session_state.check_in,
        "check_out": st.session_state.check_out,
        "nights": nights,
        "wants_transportation": bool(st.session_state.wants_transportation),
        "vehicle_type": st.session_state.vehicle_type if st.session_state.wants_transportation else None,
        "transport_persons": int(st.session_state.transport_persons) if st.session_state.wants_transportation else 0,
        **totals,
    }


def submission_record(raw: dict[str, Any]) -> dict[str, Any]:
    excluded = {"personal_photo", "passport_photo"}
    record = {key: value for key, value in raw.items() if key not in excluded}
    record["check_in"] = raw["check_in"].isoformat()
    record["check_out"] = raw["check_out"].isoformat()
    record["booking_id"] = generate_booking_id()
    record["booking_date"] = current_timestamp()
    record["status"] = "Pending"
    return record


def attempt_pending_save() -> None:
    pending = st.session_state.get("pending_submission")
    if not pending:
        return
    with st.spinner("Saving the booking securely..."):
        result = save_to_google_sheets(
            pending["record"], pending.get("personal_photo"), pending.get("passport_photo")
        )

    if not result.saved:
        st.session_state.pending_error = result.message
        return

    record = dict(pending["record"])
    record.update(
        {
            "personal_photo_url": result.data.get("personal_photo_url", ""),
            "passport_photo_url": result.data.get("passport_photo_url", ""),
            "invoice_no": result.data.get("invoice_no", ""),
            "invoice_url": result.data.get("invoice_url", ""),
            "invoice_verification_code": result.data.get("invoice_verification_code", ""),
            "invoice_sha256": result.data.get("invoice_sha256", ""),
            "invoice_pdf_bytes": result.data.get("_invoice_pdf_bytes"),
            "invoice_created": bool(result.data.get("invoice_created")),
            "customer_email_sent": bool(result.data.get("customer_email_sent")),
            "email_error": result.data.get("email_error", ""),
            "status": result.data.get("status", "Saved"),
            "files_ok": result.files_ok,
        }
    )
    for total_key in (
        "nightly_rate_eur",
        "room_total_eur",
        "transport_price_per_person_eur",
        "transport_total_eur",
        "grand_total_eur",
        "grand_total_usd",
        "grand_total_egp",
    ):
        if total_key in result.data:
            record[total_key] = result.data[total_key]
    st.session_state.last_booking = record
    st.session_state.booking_submitted = True
    st.session_state.pending_submission = None
    st.session_state.pending_error = ""
    st.rerun()


render_header()
render_navigation()


if st.session_state.current_page == "Personal":
    section_title(
        "📝", "Personal Details", "Enter the information exactly as it appears on the passport."
    )
    st.text_input("Full Name *", key="guest_name")

    country_names = [country.name for country in countries()]
    if st.session_state.nationality not in country_names:
        st.session_state.nationality = DEFAULT_COUNTRY.name
    st.selectbox(
        "Nationality / Country *",
        country_names,
        key="nationality",
        on_change=_sync_country,
    )
    _sync_country()
    selected_country = countries_by_name()[st.session_state.nationality]

    phone_prefix_col, phone_number_col = st.columns([1, 3])
    with phone_prefix_col:
        st.text_input(
            "Country Code",
            value=selected_country.calling_code,
            disabled=True,
            key=f"phone_prefix_display_{selected_country.iso2}",
        )
    with phone_number_col:
        st.text_input(
            "Phone Number *",
            key="phone_national",
            placeholder="Enter the national or international number",
        )

    phone_valid, formatted_phone, phone_message = validate_phone(
        selected_country.iso2, st.session_state.phone_national
    )
    st.session_state.phone_valid = phone_valid
    st.session_state.phone = formatted_phone if phone_valid else ""
    if st.session_state.phone_national:
        if phone_valid:
            st.success(f"Phone: {formatted_phone}")
        else:
            st.error(phone_message)

    st.text_input("Email *", key="email")

    section_title("📷", "Personal Documents")
    st.caption(f"JPG/JPEG/PNG only. Maximum {MAX_IMAGE_SIZE_MB} MB per image.")
    photo_col, passport_col = st.columns(2)
    with photo_col:
        personal_label = "Personal / Profile Photo" + (" *" if REQUIRE_PERSONAL_PHOTO else "")
        personal_upload = st.file_uploader(
            personal_label, type=["jpg", "jpeg", "png"], key="personal_photo_upload"
        )
        _process_upload(personal_upload, "personal_photo")
        if st.session_state.personal_photo:
            st.image(st.session_state.personal_photo["data"], caption="Personal photo preview")
            st.button(
                "Remove personal photo",
                on_click=_remove_upload,
                args=("personal_photo", "personal_photo_upload"),
                use_container_width=True,
            )
    with passport_col:
        passport_label = "Passport Photo" + (" *" if REQUIRE_PASSPORT_PHOTO else "")
        passport_upload = st.file_uploader(
            passport_label, type=["jpg", "jpeg", "png"], key="passport_photo_upload"
        )
        _process_upload(passport_upload, "passport_photo")
        if st.session_state.passport_photo:
            st.image(st.session_state.passport_photo["data"], caption="Passport photo preview")
            st.button(
                "Remove passport photo",
                on_click=_remove_upload,
                args=("passport_photo", "passport_photo_upload"),
                use_container_width=True,
            )


elif st.session_state.current_page == "Hotel":
    section_title(
        "🏨",
        "Hotel & Room Selection",
        "Choose the dates and the application will calculate the number of nights automatically.",
    )
    _normalize_hotel_state()
    st.selectbox("Select Hotel *", list(HOTELS), key="hotel", on_change=_normalize_hotel_state)
    _normalize_hotel_state()
    hotel_info = HOTELS[st.session_state.hotel]

    with st.expander("🏨 Hotel Details", expanded=False):
        st.write(f"⭐ Stars: {hotel_info['stars']}")
        st.write(f"📍 Distance to Arena: {hotel_info['distance_to_arena']}")
        st.write(f"📌 Location: {hotel_info['location']}")
        if hotel_info.get("website"):
            st.markdown(f"🌐 [Hotel website]({hotel_info['website']})")
        if hotel_info.get("notes"):
            st.write(f"📝 {hotel_info['notes']}")

    plans = list(hotel_info["rates"])
    if st.session_state.meal_plan not in plans:
        st.session_state.meal_plan = plans[0]
    st.radio(
        "Meal Plan *",
        plans,
        key="meal_plan",
        horizontal=True,
        on_change=_normalize_hotel_state,
    )

    rooms = list(hotel_info["rates"][st.session_state.meal_plan])
    if st.session_state.room_type not in rooms:
        st.session_state.room_type = rooms[0]
    room_col, guests_col = st.columns(2)
    with room_col:
        st.selectbox(
            "Room Type *",
            rooms,
            key="room_type",
            on_change=_sync_guests_to_room,
        )
    with guests_col:
        _sync_guests_to_room()
        st.number_input(
            "Number of Guests (Automatic) *",
            min_value=1,
            max_value=max(ROOM_OCCUPANCY.values()),
            step=1,
            key="guests",
            disabled=True,
            help="Automatically set from the selected room type.",
        )

    date_col1, date_col2 = st.columns(2)
    with date_col1:
        st.date_input("Check-in Date *", key="check_in", on_change=_ensure_checkout)
    with date_col2:
        st.date_input("Check-out Date *", key="check_out")

    nights = current_nights()
    if nights < 1:
        st.error("Check-out date must be after check-in date.")
    elif nights > MAX_BOOKING_NIGHTS:
        st.error(f"A booking cannot exceed {MAX_BOOKING_NIGHTS} nights.")
    else:
        st.success(f"Number of nights: {nights}")

    totals = current_totals()
    st.caption(
        f"Official nightly rate: {format_currency(totals['nightly_rate_eur'], 'EUR')} - "
        "EUR is the base currency."
    )
    render_price_box(totals)


elif st.session_state.current_page == "Transportation":
    section_title(
        "🚐", "Transportation", "Select the vehicle and enter the number of persons."
    )
    st.checkbox("I need transportation", key="wants_transportation")
    if st.session_state.wants_transportation:
        vehicle_names = list(TRANSPORTATION)
        if st.session_state.vehicle_type not in vehicle_names:
            st.session_state.vehicle_type = vehicle_names[0]
        transport_col1, transport_col2 = st.columns(2)
        with transport_col1:
            st.selectbox("Vehicle Type *", vehicle_names, key="vehicle_type")
        with transport_col2:
            st.number_input(
                "Number of Persons *", min_value=1, max_value=500, step=1, key="transport_persons"
            )
        transport_rates = current_transport_rates()
        unit_price = transport_rates.get(st.session_state.vehicle_type)
        if unit_price is None:
            st.warning(
                "Price pending. Enter the EUR price per person in the "
                "TRANSPORTATION section of config.py before accepting this booking."
            )
        else:
            st.info(
                f"Price per person: {format_currency(unit_price, 'EUR')} - "
                f"Total for {int(st.session_state.transport_persons)} person(s): "
                f"{format_currency(unit_price * int(st.session_state.transport_persons), 'EUR')}"
            )
        render_price_box(current_totals())
    else:
        st.info("No transportation selected. You can return here at any time.")


elif st.session_state.current_page == "Review":
    section_title("🔎", "Review Your Booking", "Review all details before completing the booking.")
    raw = booking_from_state()
    errors = validate_booking(raw)
    if errors:
        st.warning("The preview is available, but the following items must be fixed before submission:")
        for error in errors:
            st.write(f"- {error}")

    st.subheader("Personal Details")
    detail_col1, detail_col2 = st.columns(2)
    with detail_col1:
        st.write(f"Name: {raw['guest_name'] or '-'}")
        st.write(f"Nationality: {raw['nationality'] or '-'}")
    with detail_col2:
        st.write(f"Phone: {raw['phone'] or '-'}")
        st.write(f"Email: {raw['email'] or '-'}")

    image_col1, image_col2 = st.columns(2)
    with image_col1:
        if raw["personal_photo"]:
            st.image(raw["personal_photo"]["data"], caption="Personal photo")
        else:
            st.caption("Personal photo: not uploaded")
    with image_col2:
        if raw["passport_photo"]:
            st.image(raw["passport_photo"]["data"], caption="Passport photo")
        else:
            st.caption("Passport photo: not uploaded")

    st.subheader("Hotel")
    st.write(f"Hotel: {raw['hotel']}")
    st.write(f"Meal plan: {raw['meal_plan']}")
    st.write(f"Room type: {raw['room_type']}")
    st.write(f"Guests: {raw['guests']}")
    st.write(f"Check-in: {raw['check_in'].isoformat()}")
    st.write(f"Check-out: {raw['check_out'].isoformat()}")
    st.write(f"Nights: {raw['nights']}")

    st.subheader("Transportation")
    if raw["wants_transportation"]:
        st.write(f"Vehicle: {raw['vehicle_type']}")
        st.write(f"Persons: {raw['transport_persons']}")
        if raw.get("transport_price_pending"):
            st.write("Price per person: Pending")
        else:
            st.write(
                "Price per person: "
                f"{format_currency(raw['transport_price_per_person_eur'], 'EUR')}"
            )
    else:
        st.write("Not requested")
    render_price_box(raw)


elif st.session_state.current_page == "Complete":
    section_title("✅", "Complete Booking", "The booking is confirmed only after Google Sheets saves it.")

    if st.session_state.booking_submitted and st.session_state.last_booking:
        booking = st.session_state.last_booking
        st.success(f"Booking saved successfully. Booking ID: **{booking['booking_id']}**")
        if booking.get("invoice_no"):
            st.info(f"Invoice No: **{booking['invoice_no']}**")
        if booking.get("invoice_verification_code"):
            st.caption(f"Verification Code: {booking['invoice_verification_code']}")
        if not booking.get("files_ok", True):
            st.warning(
                "The registration row was saved, but one or more images could not be uploaded. "
                "Please contact the organizer and quote the Booking ID."
            )
        if not booking.get("invoice_created", False):
            st.warning(
                "The booking was saved, but the invoice PDF could not be stored. "
                "Please contact the organizer and quote the Booking ID."
            )
        elif booking.get("customer_email_sent", False):
            st.success(f"The invoice was emailed to {booking.get('email', 'the customer')}.")
        else:
            st.warning(
                "The booking and invoice were saved, but email delivery failed. "
                "The failure is recorded in Google Sheets and can be retried."
            )
            if booking.get("email_error"):
                st.caption(str(booking["email_error"]))
        try:
            pdf_data = booking.get("invoice_pdf_bytes") or generate_pdf(booking)
            st.download_button(
                "📄 Download Invoice PDF",
                data=pdf_data,
                file_name=f"{booking.get('invoice_no') or booking['booking_id']}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        except Exception as exc:
            st.warning("The booking is saved, but the invoice PDF could not be generated here.")
            st.caption(str(exc))

        if st.button("Start a New Booking", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    else:
        raw = booking_from_state()
        errors = validate_booking(raw)
        if errors:
            for error in errors:
                st.error(error)

        if not backend_is_configured():
            st.warning(
                "Google Sheets is not configured yet. Complete the Apps Script and Streamlit "
                "secrets steps in README.md before accepting real registrations."
            )

        if st.session_state.pending_submission:
            booking_id = st.session_state.pending_submission["record"]["booking_id"]
            st.warning(
                f"Booking {booking_id} has not been saved yet. It remains ready for a safe retry "
                "with the same ID, so retrying will not create a duplicate."
            )
            if st.session_state.pending_error:
                st.error(st.session_state.pending_error)
            if st.button("Retry Saving", type="primary", use_container_width=True):
                attempt_pending_save()
            if st.button("Cancel This Unsaved Attempt", use_container_width=True):
                st.session_state.pending_submission = None
                st.session_state.pending_error = ""
                st.rerun()
        elif st.button(
            "✅ Complete Booking", type="primary", use_container_width=True, disabled=bool(errors)
        ):
            record = submission_record(raw)
            st.session_state.pending_submission = {
                "record": record,
                "personal_photo": raw.get("personal_photo"),
                "passport_photo": raw.get("passport_photo"),
            }
            st.session_state.pending_error = ""
            attempt_pending_save()
