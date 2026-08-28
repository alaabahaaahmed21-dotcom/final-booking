"""Reliable, idempotent Google Apps Script client."""

from __future__ import annotations

import base64
import hashlib
import hmac
import random
import time
from dataclasses import dataclass, field
from typing import Any

import requests
import streamlit as st

from pdf_generator import generate_pdf
from uploads import to_backend_image


@dataclass
class SaveResult:
    ok: bool
    saved: bool = False
    files_ok: bool = False
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)


def _secret(name: str) -> str:
    try:
        return str(st.secrets.get(name, "")).strip()
    except Exception:
        return ""


def backend_is_configured() -> bool:
    return bool(_secret("GOOGLE_APPS_SCRIPT_URL") and _secret("BOOKING_API_TOKEN"))


def _money(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _quote_message(booking: dict[str, Any]) -> str:
    wants_transport = bool(booking.get("wants_transportation"))
    return "\n".join(
        [
            str(booking.get("booking_id", "")),
            str(booking.get("hotel", "")),
            str(booking.get("meal_plan", "")),
            str(booking.get("room_type", "")),
            str(int(booking.get("nights") or 0)),
            "1" if wants_transport else "0",
            str(booking.get("vehicle_type") or "-") if wants_transport else "-",
            str(booking.get("transport_service") or "-") if wants_transport else "-",
            str(booking.get("transport_pricing_mode") or "-") if wants_transport else "-",
            str(int(booking.get("transport_persons") or 0)) if wants_transport else "0",
            str(int(booking.get("transport_vehicle_count") or 0)) if wants_transport else "0",
            _money(booking.get("transport_unit_price_egp")),
            _money(booking.get("transport_unit_price_eur")),
            str(booking.get("transport_rate_version") or "-") if wants_transport else "-",
        ]
    )


def _invoice_message(booking: dict[str, Any]) -> str:
    return "\n".join(
        [
            str(booking.get("invoice_no", "")),
            str(booking.get("booking_id", "")),
            str(booking.get("email", "")),
            _money(booking.get("grand_total_eur")),
        ]
    )


def _signature(token: str, message: str) -> str:
    return hmac.new(token.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def _verification_code(token: str, booking: dict[str, Any]) -> str:
    digest = _signature(token, _invoice_message(booking)).upper()[:16]
    return "-".join(digest[index : index + 4] for index in range(0, 16, 4))


def save_to_google_sheets(
    booking: dict[str, Any],
    personal_photo: dict[str, Any] | None,
    passport_photo: dict[str, Any] | None,
    max_attempts: int = 4,
) -> SaveResult:
    """Save one booking, retrying the same Booking ID safely.

    The Apps Script endpoint is idempotent, so retrying a timed-out request
    cannot create duplicate rows.
    """

    url = _secret("GOOGLE_APPS_SCRIPT_URL")
    token = _secret("BOOKING_API_TOKEN")
    if not url or not token:
        return SaveResult(
            ok=False,
            message=(
                "Google Sheets is not configured yet. Add "
                "GOOGLE_APPS_SCRIPT_URL and BOOKING_API_TOKEN to Streamlit secrets."
            ),
        )

    try:
        secured_booking = dict(booking)
        booking_id = str(secured_booking.get("booking_id", ""))
        secured_booking["invoice_no"] = "INV-" + booking_id.removeprefix("ITKF-")
        secured_booking["invoice_verification_code"] = _verification_code(token, secured_booking)
        secured_booking["status"] = "Confirmed"
        pdf_bytes = generate_pdf(secured_booking, protect=True)
        pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    except Exception as exc:
        return SaveResult(ok=False, message=f"The protected invoice could not be generated: {exc}")

    payload = {
        "action": "create_booking",
        "token": token,
        "booking": secured_booking,
        "quote_signature": _signature(token, _quote_message(secured_booking)),
        "invoice": {
            "base64": base64.b64encode(pdf_bytes).decode("ascii"),
            "mime_type": "application/pdf",
            "filename": secured_booking["invoice_no"] + ".pdf",
            "sha256": pdf_sha256,
            "verification_code": secured_booking["invoice_verification_code"],
        },
        "images": {
            "personal_photo": to_backend_image(personal_photo),
            "passport_photo": to_backend_image(passport_photo),
        },
    }

    last_error = "Unknown connection error."
    for attempt in range(max_attempts):
        try:
            response = requests.post(url, json=payload, timeout=(10, 50))
            retryable = response.status_code == 429 or response.status_code >= 500
            if retryable:
                last_error = f"Backend returned HTTP {response.status_code}."
            else:
                response.raise_for_status()
                try:
                    result = response.json()
                except ValueError:
                    return SaveResult(
                        ok=False,
                        message="The Google Sheets backend returned an invalid response.",
                    )

                if result.get("retryable") and attempt < max_attempts - 1:
                    last_error = str(result.get("error") or "Temporary backend error.")
                    time.sleep(min(0.8 * (2**attempt) + random.uniform(0.0, 0.35), 5.0))
                    continue

                saved = bool(result.get("saved"))
                ok = bool(result.get("ok")) and saved
                if str(result.get("invoice_sha256", "")).lower() == pdf_sha256:
                    result["_invoice_pdf_bytes"] = pdf_bytes
                message = str(result.get("message") or result.get("error") or "")
                if result.get("error_code") == "DUPLICATE_PASSPORT":
                    message = (
                        "This passport number is already registered. "
                        "Please check the number or contact the organizer."
                    )
                return SaveResult(
                    ok=ok,
                    saved=saved,
                    files_ok=bool(result.get("files_ok", saved)),
                    message=message,
                    data=result,
                )
        except requests.RequestException as exc:
            last_error = str(exc)

        if attempt < max_attempts - 1:
            time.sleep(min(0.8 * (2**attempt) + random.uniform(0.0, 0.35), 5.0))

    return SaveResult(
        ok=False,
        saved=False,
        message=(
            "The booking could not reach Google Sheets after several attempts. "
            f"Nothing was marked as confirmed. Technical detail: {last_error}"
        ),
    )
