"""Authenticated Apps Script client; one stable request ID across retries."""
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
from config import APP_SCHEMA_VERSION
from pdf_generator import generate_pdf

@dataclass
class SaveResult:
    ok: bool
    saved: bool = False
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)

def _secret(name: str) -> str:
    try:
        return str(st.secrets.get(name, "")).strip()
    except Exception:
        return ""

def _url() -> str:
    return _secret("GOOGLE_APPS_SCRIPT_URL") or _secret("GOOGLE_SHEET_API")

def backend_is_configured() -> bool:
    return bool(_url() and _secret("BOOKING_API_TOKEN"))

def _verification_code(token: str, booking: dict) -> str:
    message = "\n".join([booking["invoice_no"], booking["booking_id"],
                         booking["email"], f"{float(booking['grand_total_eur']):.2f}"])
    digest = hmac.new(token.encode(), message.encode(), hashlib.sha256).hexdigest().upper()[:16]
    return "-".join(digest[i:i+4] for i in range(0,16,4))

@st.cache_data(ttl=60, show_spinner=False)
def _check_version(url: str) -> dict | None:
    try:
        response = requests.get(url, timeout=(10, 25))
        response.raise_for_status()
        value = response.json()
        if not isinstance(value, dict) or value.get("version") != APP_SCHEMA_VERSION:
            return {"error_code": "SCHEMA_VERSION", "error":
                    "The app and Google backend use different versions. Upload the matching config.py and application files. In Apps Script: save the matching code, run setupSheetsNow, then Manage deployments > Edit > New version > Deploy."}
    except (requests.RequestException, ValueError):
        return {"error_code": "CONNECTION", "error": "The booking service is unavailable. Check the Web App /exec URL and access settings, then retry."}
    return None

def _post(action: str, body: dict, attempts: int = 3) -> dict:
    if not backend_is_configured():
        return {"ok": False, "saved": False, "error": "Set GOOGLE_APPS_SCRIPT_URL and BOOKING_API_TOKEN in Streamlit Secrets."}
    url = _url()
    # Availability is a high-frequency read. The POST itself already carries
    # schema_version and Apps Script rejects mismatches before dispatching the
    # action, so an extra GET version probe would only double network latency.
    # Keep the friendly preflight for lower-frequency write/edit operations.
    if action != "check_availability":
        problem = _check_version(url)
        if problem:
            return {"ok": False, "saved": False, **problem}
    payload = {"schema_version": APP_SCHEMA_VERSION, "action": action,
               "token": _secret("BOOKING_API_TOKEN"), **body}
    for attempt in range(attempts):
        try:
            response = requests.post(url, json=payload, timeout=(10, 55))
            if response.status_code == 429 or response.status_code >= 500:
                raise requests.RequestException("Temporary backend response.")
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError("Invalid response.")
            if not result.get("retryable") or attempt == attempts-1:
                return result
        except (requests.RequestException, ValueError):
            if attempt == attempts-1:
                return {"ok": False, "saved": False, "error_code": "CONNECTION",
                        "error": "No final response was received. Your request may already be saved. Retry this same request to check it safely."}
        time.sleep(min(0.6 * 2**attempt + random.uniform(0,0.2), 3))
    return {"ok": False, "saved": False, "error": "Retry this request."}

def check_availability(booking: dict, edit_token: str = "") -> dict:
    return _post("check_availability", {"booking": booking, "edit_token": edit_token}, attempts=1)

def request_edit_code(booking_id: str, email: str) -> dict:
    # Never automatically resend an OTP on a lost network response.
    return _post("request_edit_code", {"booking_id": booking_id.strip().upper(), "email": email.strip()}, attempts=1)

def verify_edit_code(booking_id: str, email: str, code: str) -> dict:
    return _post("verify_edit_code", {"booking_id": booking_id.strip().upper(), "email": email.strip(), "code": code.strip()}, attempts=1)

def _decode_pdf(result: dict) -> dict:
    exact = result.pop("invoice_base64", None)
    if exact:
        try:
            data = base64.b64decode(exact, validate=True)
            if not data.startswith(b"%PDF-") or hashlib.sha256(data).hexdigest() != result.get("invoice_sha256"):
                raise ValueError("PDF mismatch")
            result["_invoice_pdf_bytes"] = data
        except (ValueError, TypeError):
            result["invoice_read_error"] = "The PDF could not be verified. Retry PDF / email or contact the organizer."
    return result

def load_request(booking_id: str, edit_token: str) -> dict:
    return _decode_pdf(_post("load_request", {"booking_id": booking_id, "edit_token": edit_token}, attempts=1))

def _pdf_payload(record: dict) -> tuple[bytes | None, dict]:
    try:
        pdf = generate_pdf(record, protect=True)
        return pdf, {"base64": base64.b64encode(pdf).decode("ascii"), "mime_type": "application/pdf",
                     "filename": record["invoice_no"]+".pdf", "sha256": hashlib.sha256(pdf).hexdigest(),
                     "verification_code": record["invoice_verification_code"]}
    except Exception:
        # A PDF failure must never hide or discard a durably saved request.
        return None, {}

def retry_request_documents(booking: dict, edit_token: str) -> SaveResult:
    _, payload = _pdf_payload(booking)
    result = _decode_pdf(_post("retry_documents", {"booking_id": booking["booking_id"],
                           "edit_token": edit_token, "invoice": payload}))
    return SaveResult(ok=bool(result.get("ok")), saved=bool(result.get("saved")),
                      message=str(result.get("error") or result.get("message") or ""), data=result)

def save_to_google_sheets(booking: dict, max_attempts: int = 3, edit_context: dict | None = None) -> SaveResult:
    record = dict(booking)
    revision = int(record.get("revision", 1))
    record["invoice_no"] = "INV-" + record["booking_id"].removeprefix("ITKF-") + (f"-R{revision}" if revision > 1 else "")
    record["invoice_verification_code"] = _verification_code(_secret("BOOKING_API_TOKEN"), record)
    record["status"] = "Request received"
    pdf, payload = _pdf_payload(record)
    body = {"booking": record, "invoice": payload}
    if edit_context:
        body.update({key: edit_context[key] for key in ("edit_token", "expected_revision", "edit_operation_id")})
    result = _decode_pdf(_post("amend_booking" if edit_context else "create_booking", body, attempts=max_attempts))
    saved = bool(result.get("saved"))
    if saved:
        result.setdefault("invoice_no", record["invoice_no"])
        result.setdefault("invoice_verification_code", record["invoice_verification_code"])
        # If Drive is pending, the same numbered local PDF can still be downloaded.
        if not result.get("invoice_created") and pdf:
            result["_invoice_pdf_bytes"] = pdf
    return SaveResult(ok=bool(result.get("ok")) and saved, saved=saved,
                      message=str(result.get("error") or result.get("message") or ""), data=result)
