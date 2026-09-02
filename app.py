"""23rd ITKF World Championship hotel booking application."""

from __future__ import annotations

import base64
import copy
import html
import importlib.util
import mimetypes
import json
from datetime import date, timedelta, time as dt_time
from pathlib import Path
import uuid
from typing import Any

import streamlit as st

from config import (BORDER_COLOR, DEFAULT_COUNTRY_CODE, EVENT_TITLE, HEADER_BG_COLOR,
    HOTELS, LOGO_PATHS, ROOM_OCCUPANCY, ROOM_INVENTORY, SYSTEM_TITLE, TRANSPORT_SERVICES, TRANSPORTATION,
    APP_SCHEMA_VERSION, MAX_TRANSPORT_SERVICES)
from countries import countries, countries_by_name, country_for_code, validate_phone


st.set_page_config(
    page_title=f"{EVENT_TITLE} - {SYSTEM_TITLE}",
    page_icon="🏨",
    layout="centered",
    initial_sidebar_state="collapsed",
)

if APP_SCHEMA_VERSION != "2026-09-02-v5.6":
    st.error("This app needs the matching v5.6 config.py and Google backend. Upload all supplied update files together, deploy the matching Google code, then reboot the app.")
    st.stop()

try:
    from sheets import (backend_is_configured, save_to_google_sheets, check_availability, check_all_availability,
                        request_edit_code, verify_edit_code, load_request, retry_request_documents,
                        process_saved_documents)
except ImportError:
    st.error("Upload the matching v5.6 sheets.py, pdf_generator.py and requirements.txt beside app.py, then reboot the app. All supplied update files must be installed together.")
    st.stop()


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
        "transport_schedule_dates", "transport_end_time_options",
        "validate_personal_fields", "validate_hotel_fields",
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
transport_end_time_options = _booking_helpers.transport_end_time_options
validate_personal_fields = _booking_helpers.validate_personal_fields
validate_hotel_fields = _booking_helpers.validate_hotel_fields


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

# A brand-new Streamlit browser session must never inherit another request's
# draft. Normal widget reruns keep this flag, while closing the app/tab and
# returning later creates a new session and starts clean. No personal fields
# are stored in st.cache_data.
if not st.session_state.get("_fresh_browser_session_initialized"):
    st.session_state.clear()
    st.session_state["_fresh_browser_session_initialized"] = True

DEFAULTS = {
    "current_page": "Registration", "registration_type": "",
    "guest_name": "", "date_of_birth": None, "passport_number": "",
    "nationality": DEFAULT_COUNTRY.name,
    "individual_phone": DEFAULT_COUNTRY.calling_code, "individual_email": "",
    "federation_name": "", "federation_phone": "", "federation_email": "",
    "federation_country": None,
    "hotel": DEFAULT_HOTEL, "meal_plan": DEFAULT_MEAL, "room_type": DEFAULT_ROOM,
    "check_in": date.today(), "check_out": date.today() + timedelta(days=1),
    "wants_transportation": False, "transport_ids": [],
    "last_booking": None, "pending_submission": None, "pending_error": "",
    "edit_context": None, "edit_original": None,
}
for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value
# Model keys above (and rq_/tr_ model keys) are NEVER widget keys. Streamlit
# may delete a hidden widget; it must never delete the corresponding draft.
if st.session_state.get("draft_state_version") != "independent-inputs-v1":
    # Detach any in-progress values left over from the older widget-key model.
    for key in list(st.session_state):
        if key in DEFAULTS or (key.startswith(("rq_", "tr_")) and not key.endswith("remove")):
            st.session_state[key] = copy.deepcopy(st.session_state[key])
    st.session_state.draft_state_version = "independent-inputs-v1"
st.session_state.setdefault("validation_attempts", [])
if not st.session_state.get("optional_federation_phone_initialized"):
    # The old '+' placeholder is not an entered phone number.
    if st.session_state.federation_phone == "+":
        st.session_state.federation_phone = ""
    st.session_state.optional_federation_phone_initialized = True


def save_visible_inputs():
    """Capture the current page, including edits submitted with a button click."""
    for key in st.session_state.get("rendered_input_keys", []):
        widget_key = "_ui_" + key
        if widget_key in st.session_state:
            st.session_state[key] = copy.deepcopy(st.session_state[widget_key])


def input_changed(callback=None, callback_args=()):
    save_visible_inputs()
    keys = st.session_state.get("rendered_input_keys", [])
    before = {key: copy.deepcopy(st.session_state.get(key)) for key in keys}
    if callback:
        callback(*callback_args)
    # Normalization and dependent defaults run before widgets render. Mirror
    # only those changes so another pending field edit is not overwritten.
    for key in keys:
        if st.session_state.get(key) != before[key]:
            st.session_state["_ui_" + key] = copy.deepcopy(st.session_state[key])


def field_error(key, container=None):
    message = page_errors.get(key)
    if message:
        (container or st).error(message)


def input_field(kind, label, *values, key, container=None, on_change=None, args=(), **kwargs):
    """Render a temporary widget restored from the independent draft model."""
    widget_key = "_ui_" + key
    st.session_state[widget_key] = copy.deepcopy(st.session_state[key])
    st.session_state.rendered_input_keys.append(key)
    result = getattr(container or st, kind)(label, *values, key=widget_key,
        on_change=input_changed, args=(on_change, args), **kwargs)
    st.session_state[key] = copy.deepcopy(result)
    field_error(key, container)
    return result


# Callbacks run BEFORE the script restarts and therefore see the previous
# page's registry. Start a fresh registry only after those callbacks finish.
st.session_state.rendered_input_keys = []

PAGES = ["Personal", "Hotel", "Transportation", "Review", "Complete"]
def go_to(page):
    """Step tabs and Back are unrestricted previews; keep the draft intact."""
    save_visible_inputs()
    st.session_state.current_page = page


def advance_to(page):
    """Next validates required fields; preview tabs never use this callback."""
    save_visible_inputs()
    current = st.session_state.current_page
    forward = page in PAGES and (current not in PAGES or PAGES.index(page) > PAGES.index(current))
    retry = page == "Complete" and (st.session_state.pending_submission or st.session_state.last_booking)
    if forward and not retry:
        for required_page in PAGES[:PAGES.index(page)]:
            if required_page not in ("Personal", "Hotel", "Transportation"):
                continue
            errors = validate_page(required_page)
            if required_page not in st.session_state.validation_attempts:
                st.session_state.validation_attempts.append(required_page)
            if errors:
                st.session_state.current_page = required_page
                return
    st.session_state.current_page = page

def choose_registration(kind):
    if st.session_state.edit_context:
        go_to("Personal")
        return
    if st.session_state.last_booking:
        st.session_state.last_booking = None
        st.session_state.pending_submission = None
        st.session_state.pending_error = ""
    st.session_state.registration_type = kind
    go_to("Personal")

def render_navigation():
    if st.session_state.edit_context:
        st.info("Editing Request ID: " + st.session_state.edit_original["booking_id"] +
                " · Current revision: " + str(st.session_state.edit_context["expected_revision"]))
        st.button("← Exit edit / view saved request", key="exit_edit", on_click=open_request_manager)
    else:
        st.button("← Registration type", key="nav_Registration", on_click=go_to, args=("Registration",))
    for col, page in zip(st.columns(len(PAGES)), PAGES):
        with col:
            st.button({"Transportation": "Transport", "Personal": "Details"}.get(page, page),
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
                     type="primary", use_container_width=True, on_click=advance_to, args=(next_page,))

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
    first = st.session_state[prefix+"date"] or st.session_state.check_in or date.today()
    defaults = {"date_mode": "One date", "range_start": first,
                "range_end": max(first, (st.session_state.check_out or first) - timedelta(days=1)),
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

def sync_transport_window(ident, full_package=False):
    """Keep each package's end time valid; infer overnight travel automatically."""
    prefix = f"tr_{ident}_"
    start, end = st.session_state[prefix+"start"], st.session_state[prefix+"end"]
    if not isinstance(start, dt_time) or not isinstance(end, dt_time):
        return
    hours = TRANSPORT_SERVICES[st.session_state[prefix+"service"]]["max_hours"]
    start_minutes = start.hour * 60 + start.minute
    duration = (end.hour * 60 + end.minute - start_minutes) % 1440
    if hours and (full_package or not 0 < duration <= hours * 60):
        limit = (start_minutes + hours * 60) % 1440
        end = dt_time(limit // 60, limit % 60)
        st.session_state[prefix+"end"] = end
    st.session_state[prefix+"next_day"] = end < start

def transport_template_from_state(ident):
    key = lambda name: st.session_state[f"tr_{ident}_{name}"]
    clock = lambda value: value.strftime("%H:%M") if isinstance(value, dt_time) else ""
    return {"service": key("service"),
            "direction": key("direction") if TRANSPORT_SERVICES[key("service")]["directions"] else "",
            "start_time": clock(key("start")), "end_time": clock(key("end")),
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
    federation_country = countries_by_name().get(state.federation_country)
    phone_input = str((state.individual_phone if individual else state.federation_phone) or "").strip()
    valid, phone, _ = validate_phone(country.iso2 if individual else "EG", phone_input)
    if not individual and not phone_input.strip().startswith("+"):
        valid = False
    raw = {"schema_version": APP_SCHEMA_VERSION, "registration_type": state.registration_type,
           "guest_name": normalize_guest_name(state.guest_name) if individual else "",
           "federation_name": state.federation_name.strip() if not individual else "",
           "federation_country": federation_country.name if not individual and federation_country else "",
           "federation_country_code": federation_country.iso2 if not individual and federation_country else "",
           "passport_number": normalize_passport_number(state.passport_number) if individual else "",
           "date_of_birth": state.date_of_birth.isoformat() if individual and state.date_of_birth else "",
           "nationality": country.name if individual else "", "nationality_code": country.iso2 if individual else "",
           # Keep an invalid provided value visible to validation. Otherwise
           # an invalid federation number would look like an omitted number.
           "phone": phone if valid else phone_input, "phone_valid": valid,
           "email": (state.individual_email if individual else state.federation_email).strip(),
           "hotel": state.hotel, "meal_plan": state.meal_plan, "rooms": selected_rooms(),
           "check_in": state.check_in.isoformat() if state.check_in else "",
           "check_out": state.check_out.isoformat() if state.check_out else ""}
    if state.edit_original:
        raw["booking_id"] = state.edit_original["booking_id"]
    try:
        raw["transport_services"] = transport_from_state()
    except (ValueError, TypeError) as exc:
        raw["transport_services"] = []
        raw["transport_schedule_error"] = str(exc)
    return raw


@st.cache_data(ttl=60, show_spinner=False)
def _cached_all_hotels_availability(check_in: str, check_out: str,
                                    booking_id: str = "", edit_token: str = "") -> dict:
    """Fetch every hotel's remaining room stock in one cached backend call.

    The cache is keyed only by dates plus edit context, not by selected hotel or
    meal plan. Once a date range is loaded, switching hotels/plans is therefore
    local and immediate for up to 60 seconds. The backend still performs a
    fresh locked check when a booking is actually created or amended.
    """
    return check_all_availability(check_in, check_out, booking_id, edit_token)


def all_hotels_availability() -> tuple[dict[str, dict[str, int]], str]:
    """Return live availability for all hotels, with configured allotment fallback."""
    fallback = {
        hotel: {room: max(0, int(capacity)) for room, capacity in rooms.items()}
        for hotel, rooms in ROOM_INVENTORY.items()
    }

    check_in = st.session_state.check_in
    check_out = st.session_state.check_out
    if not isinstance(check_in, date) or not isinstance(check_out, date) or check_out <= check_in:
        return fallback, "Choose valid check-in and check-out dates to see live availability."
    if not backend_is_configured():
        return fallback, "Live availability is temporarily unavailable; shown counts are the room allotment limits."

    edit_context = st.session_state.edit_context or {}
    edit_token = str(edit_context.get("edit_token", ""))
    booking_id = ""
    if st.session_state.edit_original:
        booking_id = str(st.session_state.edit_original.get("booking_id", ""))

    result = _cached_all_hotels_availability(
        check_in.isoformat(), check_out.isoformat(), booking_id, edit_token
    )
    if not result.get("ok"):
        return fallback, result.get("error", "Unable to load live room availability right now.")

    raw = result.get("availability_by_hotel", {})
    available: dict[str, dict[str, int]] = {}
    for hotel, rooms in fallback.items():
        returned = raw.get(hotel, {}) if isinstance(raw, dict) else {}
        available[hotel] = {
            room: max(0, int(returned.get(room, capacity)))
            for room, capacity in rooms.items()
        }
    return available, ""


def live_room_availability() -> tuple[dict[str, int], str]:
    """Get displayed room availability for the selected hotel's current priced rooms."""
    hotel = st.session_state.hotel
    meal_plan = st.session_state.meal_plan
    rates = HOTELS[hotel]["rates"][meal_plan]
    all_available, note = all_hotels_availability()
    hotel_available = all_available.get(hotel, {})
    return {room: int(hotel_available.get(room, 0)) for room in rates}, note


def validate_page(page):
    if page == "Personal":
        return validate_personal_fields(booking_from_state())
    if page == "Hotel":
        raw = booking_from_state()
        errors = validate_hotel_fields(raw)
        if not errors:
            available, _ = live_room_availability()
            unavailable = []
            for room in raw.get("rooms", []):
                remaining = int(available.get(room["room_type"], 0))
                if int(room.get("quantity", 0)) > remaining:
                    unavailable.append(
                        f"{room['room_type']}: only {remaining} room(s) available for these dates."
                    )
            if unavailable:
                errors["rooms"] = " ".join(unavailable)
        return errors
    errors = {}
    if page != "Transportation" or not st.session_state.wants_transportation:
        return errors
    if not st.session_state.transport_ids:
        return {"wants_transportation": "Add at least one transportation service, or uncheck transportation."}
    date_count = 0
    for order, ident in enumerate(st.session_state.transport_ids, 1):
        prefix = f"tr_{ident}_"
        dates = []
        try:
            dates = transport_dates_from_state(ident)
            date_count += len(dates)
        except (ValueError, TypeError) as exc:
            errors[prefix+"dates"] = f"Service {order}: {exc}"
        for name, label in (("start", "start"), ("end", "end")):
            if not isinstance(st.session_state[prefix+name], dt_time):
                errors[prefix+name] = f"Please choose a {label} time."
        try:
            template = transport_template_from_state(ident)
            priced = price_transport_service({**template, "date": dates[0] if dates else date.today().isoformat()})
            if priced["seats"] == 0:
                errors[prefix+"vehicles"] = "Select at least one vehicle."
            elif priced["remaining"]:
                errors[prefix+"vehicles"] = f"Add seats for {priced['remaining']} remaining passengers. Extra seats are allowed."
        except (ValueError, TypeError, KeyError) as exc:
            if prefix+"start" not in errors and prefix+"end" not in errors:
                errors[prefix+"end"] = str(exc)
    if date_count > MAX_TRANSPORT_SERVICES:
        errors["wants_transportation"] = f"Choose at most {MAX_TRANSPORT_SERVICES} dated services in one request."
    return errors

def render_price_box(totals):
    st.markdown(
        '<div class="itkf-price-box">Accommodation: ' + format_currency(totals["room_total_eur"]) +
        '<br>Transportation: ' + format_currency(totals["transport_total_eur"]) +
        '<hr><b>Total: ' + format_currency(totals["grand_total_eur"]) + '</b></div>',
        unsafe_allow_html=True)

@st.fragment
def render_hotel_room_selection():
    """Fast room controls: quantity changes rerun only this fragment."""
    info = HOTELS[st.session_state.hotel]
    rates = info["rates"][st.session_state.meal_plan]
    available, availability_note = live_room_availability()
    if availability_note:
        st.caption(availability_note)

    can_quote_rooms = True
    if st.session_state.registration_type == "Individual":
        room_options = [room for room in rates if available.get(room, 0) > 0]
        sold_out = [room for room in rates if available.get(room, 0) <= 0]
        if not room_options:
            st.error("No rooms are available for the selected hotel and dates.")
            can_quote_rooms = False
        else:
            if st.session_state.room_type not in room_options:
                st.session_state.room_type = room_options[0]
            input_field(
                "selectbox", "Room Type *", room_options, key="room_type",
                format_func=lambda room: f"{room} — {available.get(room, 0)} room(s) available"
            )
            st.info(
                f"Available now: {available.get(st.session_state.room_type, 0)} room(s) · "
                f"Number of guests: {ROOM_OCCUPANCY[st.session_state.room_type]}"
            )
        if sold_out:
            st.caption("Sold out for these dates: " + ", ".join(sold_out) + ".")
    else:
        for room, rate in rates.items():
            remaining = max(0, int(available.get(room, 0)))
            key = room_key(room)
            st.session_state[key] = min(int(st.session_state.get(key, 0)), remaining)
            input_field(
                "number_input",
                f"{room} — {format_currency(rate)} / room / night — {remaining} available",
                min_value=0, max_value=remaining, step=1, key=key, disabled=remaining == 0
            )
        st.caption(
            "Guests (automatic): " +
            str(sum(r["quantity"] * ROOM_OCCUPANCY[r["room_type"]] for r in selected_rooms()))
        )

    field_error("rooms")
    if can_quote_rooms:
        raw = booking_from_state()
        try:
            totals = calculate_booking_totals({**raw, "transport_services": []})
            st.info(f"Number of nights: {totals['nights']} · Number of rooms: {totals['room_count']}")
            render_price_box(totals)
        except (ValueError, TypeError, KeyError) as exc:
            st.error(str(exc))


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
    else:
        st.write(f"Federation country: {raw.get('federation_country') or '-'}")
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
    """Reserve/save the request first; documents are processed after success is visible."""
    st.session_state.pending_submission = record
    with st.spinner("Confirming and saving your request..."):
        result = save_to_google_sheets(record, edit_context=st.session_state.edit_context) if st.session_state.edit_context else save_to_google_sheets(record)
    if not result.saved:
        st.session_state.pending_error = result.message
        # Only clear a request when the server explicitly rejected it BEFORE reserving rooms.
        if result.data.get("error_code") in ("VALIDATION_ERROR", "DUPLICATE_PASSPORT", "SOLD_OUT", "QUOTE_CHANGED", "SCHEMA_VERSION", "NO_CHANGES", "EDIT_IDENTITY", "EDIT_CLOSED"):
            st.session_state.pending_submission = None
        st.rerun()
    booking = {**record, **result.data.get("booking", {}), **result.data}
    st.session_state.last_booking = booking
    st.session_state.submitted_record = booking
    st.session_state.pending_submission = None
    st.session_state.pending_error = ""
    # Each invoice/revision gets one automatic document attempt on the success page.
    st.session_state.documents_attempted_for_invoice = ""
    st.rerun()


def process_completion_documents(saved):
    """Process PDF/Drive/email after the durable reservation is already shown as saved."""
    invoice_no = str(saved.get("invoice_no", ""))
    if not invoice_no or (saved.get("invoice_created") and saved.get("customer_email_sent")):
        return saved
    if st.session_state.get("documents_attempted_for_invoice") == invoice_no:
        return saved
    st.session_state.documents_attempted_for_invoice = invoice_no
    edit_token = (st.session_state.edit_context or {}).get("edit_token", "")
    with st.status("Preparing your one-page PDF and email...", expanded=False) as status:
        result = process_saved_documents(saved, edit_token=edit_token, force_check=bool(st.session_state.get("document_force_check")))
        if result.saved:
            updated = {**saved, **result.data.get("booking", {}), **result.data}
            st.session_state.last_booking = updated
            st.session_state.submitted_record = updated
            st.session_state.document_force_check = False
            if updated.get("invoice_created") and updated.get("customer_email_sent"):
                status.update(label="PDF saved and email sent.", state="complete", expanded=False)
            else:
                status.update(label="Request saved; PDF/email can be retried safely.", state="complete", expanded=False)
            return updated
        status.update(label="Request saved; PDF/email can be retried safely.", state="error", expanded=False)
    return saved


def open_request_manager():
    save_visible_inputs()
    record = st.session_state.last_booking or st.session_state.edit_original or st.session_state.pending_submission
    if record:
        st.session_state.manage_id = record["booking_id"]
        st.session_state.manage_email = record["email"]
    st.session_state.current_page = "Manage"
    st.session_state.edit_context = None
    # Do not leave a stale result visible after an update.
    st.session_state.pop("managed_request", None)
    st.session_state.pop("manage_token", None)


def start_edit_loaded():
    response = st.session_state.managed_request
    original = copy.deepcopy(response["booking"])
    if not response.get("editable"):
        return
    for key in list(st.session_state):
        if key.startswith(("rq_", "tr_", "_ui_")):
            del st.session_state[key]
    for key, value in DEFAULTS.items():
        st.session_state[key] = copy.deepcopy(value)
    state = st.session_state
    state.validation_attempts = []
    state.rendered_input_keys = []
    state.registration_type = original["registration_type"]
    for key in ("guest_name", "passport_number", "federation_name", "hotel", "meal_plan"):
        state[key] = original.get(key, "")
    state.nationality = country_for_code(original.get("nationality_code") or DEFAULT_COUNTRY_CODE).name
    state.federation_country = original.get("federation_country") or None
    if original.get("date_of_birth"):
        state.date_of_birth = date.fromisoformat(original["date_of_birth"])
    state.check_in = date.fromisoformat(original["check_in"])
    state.check_out = date.fromisoformat(original["check_out"])
    prefix = "individual" if original["registration_type"] == "Individual" else "federation"
    state[prefix+"_email"] = original["email"]
    state[prefix+"_phone"] = original.get("phone", "")
    state.room_type = original["rooms"][0]["room_type"]
    normalize_hotel_state()
    for room in HOTELS[state.hotel]["rates"][state.meal_plan]:
        state[room_key(room)] = 0
    for room in original["rooms"]:
        state[room_key(room["room_type"])] = room["quantity"]
    # Regroup repeated dates without dropping distinct services on the same day.
    grouped = []
    for service in original.get("transport_services", []):
        template = {key: service.get(key) for key in ("service", "direction", "start_time", "end_time", "ends_next_day", "persons", "vehicles")}
        signature = json.dumps(template, sort_keys=True)
        match = next((g for g in grouped if g["signature"] == signature and service["date"] not in g["dates"]), None)
        if match is None:
            match = {"signature": signature, "template": template, "dates": []}
            grouped.append(match)
        match["dates"].append(service["date"])
    state.wants_transportation = bool(grouped)
    for group in grouped:
        add_transport()
        ident = state.transport_ids[-1]
        p = f"tr_{ident}_"
        t = group["template"]
        days = sorted(date.fromisoformat(v) for v in group["dates"])
        state[p+"date"] = days[0]
        state[p+"date_mode"] = "One date" if len(days) == 1 else "Specific dates"
        state[p+"selected_dates"] = days
        state[p+"date_options"] = days
        for key in ("service", "direction", "persons"):
            state[p+key] = t[key]
        state[p+"start"] = dt_time.fromisoformat(t["start_time"])
        state[p+"end"] = dt_time.fromisoformat(t["end_time"])
        state[p+"next_day"] = bool(t["ends_next_day"])
        for i, vehicle in enumerate(TRANSPORTATION):
            state[p+f"v{i}"] = t["vehicles"].get(vehicle, 0)
    state.edit_original = original
    state.edit_context = {"edit_token": state.manage_token, "expected_revision": int(response.get("revision", 1)),
                          "edit_operation_id": uuid.uuid4().hex}
    state.current_page = "Personal"


def render_request_manager():
    section_title("🔐", "View / Edit Existing Request", "Use the Request ID from your email or PDF. Do not create a new request to change existing details.")
    if st.button("← Back to registration", key="manage_back"):
        st.session_state.edit_context = None
        st.session_state.edit_original = None
        st.session_state.current_page = "Registration"
        st.rerun()
    with st.form("request_code_form"):
        ident = st.text_input("Request ID", key="manage_id", placeholder="ITKF-20260831-ABCDEF123456", max_chars=40)
        email = st.text_input("Registered Email", key="manage_email", max_chars=254)
        send = st.form_submit_button("Send verification code", disabled=not backend_is_configured())
    if send:
        st.session_state.pop("managed_request", None)
        st.session_state.pop("manage_token", None)
        reply = request_edit_code(ident, email)
        (st.info if reply.get("ok") else st.error)(reply.get("message") or reply.get("error") or "Please try again.")
    st.caption("Codes expire after 10 minutes. Maximum 5 attempts per code; request a new code if needed. Your edit session lasts one hour.")
    with st.form("verify_code_form"):
        code = st.text_input("Email verification code", type="password", max_chars=8)
        verify = st.form_submit_button("Verify & open request", disabled=not backend_is_configured())
    if verify:
        reply = verify_edit_code(ident, email, code)
        if reply.get("ok"):
            st.session_state.manage_token = reply["edit_token"]
            st.session_state.manage_verified_id = ident.strip().upper()
            st.session_state.pop("managed_request", None)
        else:
            st.error(reply.get("error", "Unable to verify this code."))
    token = st.session_state.get("manage_token")
    if token:
        if "managed_request" not in st.session_state:
            reply = load_request(st.session_state.manage_verified_id, token)
            if reply.get("ok"):
                st.session_state.managed_request = reply
            else:
                st.error(reply.get("error", "Unable to load the request."))
                if st.button("Retry loading request"):
                    st.rerun()
                return
        reply = st.session_state.managed_request
        booking = reply["booking"]
        st.success(f"Request ID: {booking['booking_id']} · Revision: {reply.get('revision', 1)}")
        st.code(booking["booking_id"], language=None)
        st.write("Status: " + str(reply.get("status", "Received")))
        st.write("Invoice / summary: " + booking["invoice_no"])
        st.write("Saved total: " + format_currency(booking["grand_total_eur"]))
        st.write("Name: " + (booking.get("federation_name") or booking.get("guest_name") or "-"))
        st.write(f"{booking['hotel']} · {booking['check_in']} to {booking['check_out']}")
        with st.expander("View saved rooms and transportation"):
            for room in booking.get("rooms", []):
                st.write(f"{room['room_type']} × {room['quantity']} room(s) · {format_currency(room['total_eur'])}")
            for service in booking.get("transport_services", []):
                suffix = " (next day)" if service.get("ends_next_day") else ""
                st.write(f"{service['date']} · {service['service']} · {service.get('direction', '')} · {service['start_time']}–{service['end_time']}{suffix}")
                st.write(f"Passengers: {service['persons']} · Seats: {service['seats']} · {format_currency(service['total_eur'])}")
                for vehicle, quantity in service["vehicles"].items():
                    st.write(f"{vehicle} × {quantity}")
        if reply.get("_invoice_pdf_bytes"):
            st.download_button("Download saved PDF", reply["_invoice_pdf_bytes"], file_name=booking["invoice_no"]+".pdf", mime="application/pdf", use_container_width=True)
        if reply.get("invoice_read_error"):
            st.warning(reply["invoice_read_error"])
        st.info("Email sent." if reply.get("customer_email_sent") else "Email delivery is pending.")
        if (not reply.get("invoice_created") or not reply.get("customer_email_sent") or reply.get("invoice_read_error")) and reply.get("status") not in ("Cancelled", "Rejected"):
            if st.button("Retry PDF / email", key="manage_retry_documents", use_container_width=True):
                with st.spinner("Preparing the saved PDF and email..."):
                    result = retry_request_documents(booking, token)
                if result.saved:
                    st.session_state.pop("managed_request", None)
                    st.rerun()
                else:
                    st.error(result.message)
        if reply.get("editable"):
            st.caption("Changes use current prices and room availability. Review the new total before saving. Registered email and registration type remain unchanged; contact the organizer to change them.")
            rates = HOTELS.get(booking.get("hotel"), {}).get("rates", {}).get(booking.get("meal_plan"), {})
            supported = all(r.get("room_type") in rates for r in booking.get("rooms", [])) and bool(rates)
            supported = supported and all(s.get("service") in TRANSPORT_SERVICES and
                all(v in TRANSPORTATION for v in s.get("vehicles", {})) for s in booking.get("transport_services", []))
            if not supported:
                st.warning("Some choices in this older request are no longer offered online. Contact the organizer to amend it.")
            st.button("Edit this request", key="manage_start_edit", type="primary", use_container_width=True, on_click=start_edit_loaded, disabled=not supported)
        else:
            st.info("Contact the organizer to change this request.")

normalize_hotel_state()
render_header()
if st.session_state.current_page == "Manage":
    render_request_manager()
    st.stop()
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
    st.button("View / edit existing request", key="manage_existing", use_container_width=True, on_click=open_request_manager)
    st.stop()
render_navigation()
page = st.session_state.current_page
page_errors = validate_page(page) if page in st.session_state.validation_attempts else {}
if page_errors:
    st.error("Please complete or correct the highlighted fields on this page before continuing.")
if page == "Personal":
    section_title("📝", "Registration Details")
    st.caption("Registration type: " + st.session_state.registration_type)
    if st.session_state.registration_type == "Individual":
        input_field("text_input", "Full Name (CAPITAL LETTERS) *", key="guest_name", on_change=normalize_name, max_chars=150)
        left, right = st.columns(2)
        input_field("text_input", "Passport Number *", key="passport_number", container=left, on_change=normalize_passport, max_chars=20)
        input_field("date_input", "Date of Birth *", key="date_of_birth", container=right, min_value=date(1900,1,1), max_value=date.today(), format="YYYY-MM-DD")
        input_field("selectbox", "Nationality *", [c.name for c in countries()], key="nationality", on_change=sync_country)
        input_field("text_input", "Phone Number (including country code) *", key="individual_phone", placeholder="+201012345678")
        input_field("text_input", "Email *", key="individual_email", max_chars=254, disabled=bool(st.session_state.edit_context))
    else:
        input_field("text_input", "Federation Name *", key="federation_name", max_chars=150)
        input_field("selectbox", "Federation Country *", [c.name for c in countries()],
                     key="federation_country", index=None, placeholder="Select the federation country")
        input_field("text_input", "Federation Email *", key="federation_email", max_chars=254, disabled=bool(st.session_state.edit_context))
        input_field("text_input", "Federation Phone (optional — including country code)", key="federation_phone", placeholder="+201012345678")
    raw = booking_from_state()
    if raw["phone_valid"]:
        st.caption(f"Phone: {raw['phone']}")
    render_step_navigation(back="Manage" if st.session_state.edit_context else "Registration", next_page="Hotel")

elif page == "Hotel":
    section_title("🏨", "Hotel & Rooms", "Choose your rooms and stay dates.")
    input_field("selectbox", "Select Hotel *", list(HOTELS), key="hotel", on_change=normalize_hotel_state)
    info = HOTELS[st.session_state.hotel]
    with st.expander("🏨 Hotel Details"):
        st.write(f"Stars: {info['stars']} · Distance to Arena: {info['distance_to_arena']}")
        st.write(info["location"])
        if info.get("website"):
            st.markdown(f"[Hotel website]({info['website']})")
        if info.get("notes"):
            st.write(info["notes"])
    input_field("radio", "Meal Plan *", list(info["rates"]), key="meal_plan", horizontal=True, on_change=normalize_hotel_state)

    # Availability depends on the stay dates, so dates come before room selection.
    left, right = st.columns(2)
    input_field("date_input", "Check-in Date *", key="check_in", container=left, format="YYYY-MM-DD")
    input_field("date_input", "Check-out Date *", key="check_out", container=right, format="YYYY-MM-DD")

    render_hotel_room_selection()
    render_step_navigation(back="Personal", next_page="Transportation")

elif page == "Transportation":
    section_title("🚐", "Transportation", "Whole-vehicle prices in EUR. All times are Cairo local time.")
    input_field("checkbox", "I need transportation", key="wants_transportation")
    if st.session_state.wants_transportation:
        if not st.session_state.transport_ids:
            add_transport()
        for order, ident in enumerate(list(st.session_state.transport_ids), 1):
            ensure_transport_schedule_state(ident)
            prefix = f"tr_{ident}_"
            with st.expander(f"Service {order}", expanded=True):
                input_field("selectbox", "Service Type", list(TRANSPORT_SERVICES), key=prefix+"service",
                             format_func=lambda v: TRANSPORT_SERVICES[v]["label"],
                             on_change=sync_transport_window, args=(ident, True))
                service = st.session_state[prefix+"service"]
                directions = TRANSPORT_SERVICES[service]["directions"]
                if directions:
                    if st.session_state[prefix+"direction"] not in directions:
                        st.session_state[prefix+"direction"] = directions[0]
                    input_field("selectbox", "Direction", directions, key=prefix+"direction")
                input_field("selectbox", "When do you need this service?", ["One date", "Date range", "Specific dates"],
                             key=prefix+"date_mode",
                             format_func=lambda v: {"One date":"One date", "Date range":"Repeat daily — from / to", "Specific dates":"Choose specific dates"}[v])
                mode = st.session_state[prefix+"date_mode"]
                if mode == "One date":
                    input_field("date_input", "Service Date", key=prefix+"date", format="YYYY-MM-DD")
                elif mode == "Date range":
                    a, b = st.columns(2)
                    input_field("date_input", "First service date", key=prefix+"range_start", container=a, format="YYYY-MM-DD")
                    input_field("date_input", "Last service date", key=prefix+"range_end", container=b, format="YYYY-MM-DD")
                    st.caption("Both dates are included. The same vehicles and times apply to every selected day.")
                    try:
                        options = [date.fromisoformat(value) for value in transport_schedule_dates("Date range",
                            start_date=st.session_state[prefix+"range_start"], end_date=st.session_state[prefix+"range_end"])]
                        st.session_state[prefix+"excluded_dates"] = [value for value in st.session_state[prefix+"excluded_dates"] if value in options]
                        input_field("multiselect", "Skip dates (optional)", options, key=prefix+"excluded_dates",
                                       format_func=lambda v: v.strftime("%a, %d %b %Y"))
                    except (ValueError, TypeError):
                        pass  # The shared validation below displays the exact problem.
                else:
                    input_field("date_input", "Pick a date", key=prefix+"pick_date", format="YYYY-MM-DD")
                    st.button("＋ Add selected date", key="action_add_date_"+ident,
                              on_click=add_selected_transport_date, args=(ident,),
                              disabled=len(st.session_state[prefix+"selected_dates"]) >= MAX_TRANSPORT_SERVICES)
                    input_field("multiselect", "Selected service dates", st.session_state[prefix+"date_options"],
                                   key=prefix+"selected_dates", format_func=lambda v: v.strftime("%a, %d %b %Y"))
                    st.caption("Add each date once. Remove a date using its ×. The same vehicles and times apply to all selected dates.")
                field_error(prefix+"dates")
                sync_transport_window(ident)
                a, b = st.columns(2)
                input_field("time_input", "From", key=prefix+"start", container=a, on_change=sync_transport_window, args=(ident,))
                hours = TRANSPORT_SERVICES[service]["max_hours"]
                start = st.session_state[prefix+"start"]
                if hours and isinstance(start, dt_time):
                    current_end = st.session_state[prefix+"end"]
                    end_options = [dt_time.fromisoformat(value) for value in transport_end_time_options(
                        start.strftime("%H:%M"), hours, current_end.strftime("%H:%M") if current_end else None)]
                    input_field("selectbox", f"To (up to {hours} hours)", end_options, key=prefix+"end", container=b,
                                on_change=sync_transport_window, args=(ident,), index=None,
                                format_func=lambda value: value.strftime("%H:%M") + (" (next day)" if value < start else ""))
                    st.caption(f"End times are limited to {hours} hours after departure. The selected package price applies even if you choose fewer hours.")
                else:
                    input_field("time_input", "To", key=prefix+"end", container=b, on_change=sync_transport_window, args=(ident,))
                if st.session_state[prefix+"next_day"]:
                    st.caption("Ends on the next day (after midnight). This is detected automatically.")
                input_field("number_input", "Passengers to transport", min_value=1, max_value=5000, key=prefix+"persons")
                st.caption("Select the quantity of each vehicle you need:")
                for i, (name, vehicle) in enumerate(TRANSPORTATION.items()):
                    input_field("number_input", f"{name} — {format_currency(vehicle['prices_eur'][service])} / vehicle",
                                    min_value=0, max_value=100, step=1, key=prefix+f"v{i}")
                field_error(prefix+"vehicles")
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
        st.caption("Each transfer price is for one direction; daily hire is charged at the selected package price.")
    render_step_navigation(back="Hotel", next_page="Review")

elif page == "Review":
    section_title("🔎", "Review Your Request")
    raw = booking_from_state()
    for error in validate_booking(raw):
        st.warning(error)
    show_summary(raw)
    render_step_navigation(back="Transportation", next_page="Complete")

elif page == "Complete":
    section_title("✅", "Save Changes" if st.session_state.edit_context else "Submit Request")
    if st.session_state.pending_error:
        st.error(st.session_state.pending_error)
    if st.session_state.last_booking:
        saved = st.session_state.last_booking
        verb = "updated" if int(saved.get("revision", 1)) > 1 else "received"
        # This appears immediately after the durable reservation/save response.
        st.success(f"Your booking request has been {verb} successfully. Request ID: {saved['booking_id']}")
        st.code(saved["booking_id"], language=None)
        st.info(f"Invoice / summary number: {saved.get('invoice_no', '-')}")
        st.caption(f"Revision: {saved.get('revision', 1)}. Keep your Request ID to view or edit this same request later.")

        # PDF/Drive/email no longer delay the reservation confirmation above.
        saved = process_completion_documents(saved)

        if saved.get("_invoice_pdf_bytes"):
            st.download_button("Download PDF", data=saved["_invoice_pdf_bytes"],
                               file_name=saved["invoice_no"]+".pdf", mime="application/pdf", use_container_width=True)
        if not saved.get("invoice_created"):
            st.warning("Your request is saved. Saving the PDF copy is pending.")
        if saved.get("invoice_read_error"):
            st.warning(saved["invoice_read_error"])
        if saved.get("customer_email_sent"):
            st.success("The PDF was emailed to " + saved["email"])
        else:
            st.info("Your request is saved. Email delivery is pending.")
        if not saved.get("invoice_created") or not saved.get("customer_email_sent") or saved.get("invoice_read_error"):
            if st.button("Retry PDF / email", use_container_width=True):
                st.session_state.documents_attempted_for_invoice = ""
                st.session_state.document_force_check = True
                st.rerun()
        st.button("View / edit this request", key="complete_edit", use_container_width=True, on_click=open_request_manager)
        if st.button("Start a new request", use_container_width=True):
            st.session_state.clear()
            st.rerun()
    else:
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
            editing = st.session_state.edit_context
            if editing:
                st.info("Saving changes updates your existing request, checks room availability, and issues a revised EUR PDF. It does not create another booking.")
            if st.button("Save Changes & Send Updated PDF" if editing else "Submit Booking Request", type="primary", use_container_width=True,
                         disabled=bool(errors) or not backend_is_configured()):
                record = {**raw, **calculate_booking_totals(raw),
                          "booking_id": st.session_state.edit_original["booking_id"] if editing else generate_booking_id(),
                          "booking_date": st.session_state.edit_original["booking_date"] if editing else current_timestamp(),
                          "revision": editing["expected_revision"]+1 if editing else 1,
                          "updated_at": current_timestamp()}
                attempt_save(record)
        render_step_navigation(back="Review")
