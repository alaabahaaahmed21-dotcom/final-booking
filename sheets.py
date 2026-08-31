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

def _timeout_for(action: str) -> tuple[int, int]:
    """Use short, action-specific timeouts so a slow backend never looks frozen."""
    if action in {"check_availability", "check_all_availability", "booking_status"}:
        return (5, 15)
    if action in {"create_booking", "amend_booking"}:
        return (5, 18)
    if action in {"process_documents", "retry_documents"}:
        return (5, 30)
    return (5, 20)


def _post(action: str, body: dict, attempts: int = 1) -> dict:
    if not backend_is_configured():
        return {"ok": False, "saved": False, "error": "Set GOOGLE_APPS_SCRIPT_URL and BOOKING_API_TOKEN in Streamlit Secrets."}
    url = _url()
    payload = {"schema_version": APP_SCHEMA_VERSION, "action": action,
               "token": _secret("BOOKING_API_TOKEN"), **body}
    timeout = _timeout_for(action)
    for attempt in range(attempts):
        try:
            response = requests.post(url, json=payload, timeout=timeout)
            if response.status_code == 429 or response.status_code >= 500:
                raise requests.RequestException("Temporary backend response.")
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError("Invalid response.")
            if not result.get("retryable") or attempt == attempts - 1:
                return result
        except (requests.RequestException, ValueError):
            if attempt == attempts - 1:
                return {"ok": False, "saved": False, "error_code": "CONNECTION",
                        "error": "No final response was received. Your request may already be saved. The app will check the same Request ID before retrying."}
        time.sleep(min(0.4 * 2**attempt + random.uniform(0, 0.15), 1.5))
    return {"ok": False, "saved": False, "error": "Retry this request."}

def check_availability(booking: dict, edit_token: str = "") -> dict:
    return _post("check_availability", {"booking": booking, "edit_token": edit_token}, attempts=1)

def check_all_availability(check_in: str, check_out: str, booking_id: str = "", edit_token: str = "") -> dict:
    """Fetch remaining inventory for every configured hotel in one backend request."""
    return _post(
        "check_all_availability",
        {
            "check_in": check_in,
            "check_out": check_out,
            "booking_id": booking_id,
            "edit_token": edit_token,
        },
        attempts=1,
    )

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

def _with_local_pdf(result: dict, pdf: bytes | None) -> dict:
    """Use the locally generated exact PDF instead of downloading it back from Drive."""
    if pdf and result.get("invoice_created"):
        expected = str(result.get("invoice_sha256") or "")
        actual = hashlib.sha256(pdf).hexdigest()
        if not expected or hmac.compare_digest(actual, expected):
            result["_invoice_pdf_bytes"] = pdf
        else:
            result["invoice_read_error"] = "The saved PDF verification did not match. Retry PDF / email or contact the organizer."
    return result

def process_saved_documents(booking: dict, edit_token: str = "", force_check: bool = False,
                            defer_email: bool = True) -> SaveResult:
    """Store the protected PDF after save; normal email delivery is queued."""
    pdf, payload = _pdf_payload(booking)
    body = {"booking_id": booking["booking_id"], "invoice": payload,
            "force_check": bool(force_check), "defer_email": bool(defer_email)}
    if edit_token:
        body["edit_token"] = edit_token
    result = _with_local_pdf(_post("process_documents", body, attempts=1), pdf)
    return SaveResult(ok=bool(result.get("ok")), saved=bool(result.get("saved")),
                      message=str(result.get("error") or result.get("message") or ""), data=result)

def retry_request_documents(booking: dict, edit_token: str) -> SaveResult:
    # Existing-request manager keeps its edit-token authorization path.
    pdf, payload = _pdf_payload(booking)
    result = _with_local_pdf(_post("retry_documents", {"booking_id": booking["booking_id"],
                           "edit_token": edit_token, "invoice": payload}), pdf)
    return SaveResult(ok=bool(result.get("ok")), saved=bool(result.get("saved")),
                      message=str(result.get("error") or result.get("message") or ""), data=result)

def save_to_google_sheets(booking: dict, max_attempts: int = 2, edit_context: dict | None = None) -> SaveResult:
    """Fast path: validate, reserve inventory and save the booking row only.

    PDF generation, Drive storage and customer email are deliberately separated
    so they cannot delay the user's reservation confirmation.
    """
    record = dict(booking)
    revision = int(record.get("revision", 1))
    record["invoice_no"] = "INV-" + record["booking_id"].removeprefix("ITKF-") + (f"-R{revision}" if revision > 1 else "")
    record["invoice_verification_code"] = _verification_code(_secret("BOOKING_API_TOKEN"), record)
    record["status"] = "Request received"
    body = {"booking": record}
    if edit_context:
        body.update({key: edit_context[key] for key in ("edit_token", "expected_revision", "edit_operation_id")})
    action = "amend_booking" if edit_context else "create_booking"
    # First attempt is intentionally single-shot. If the network response is
    # lost, query the same durable Request ID before repeating a write. This
    # avoids several long create requests while preserving idempotent retries.
    result = _post(action, body, attempts=1)
    if not result.get("saved") and result.get("error_code") == "CONNECTION":
        status = _post("booking_status", {"booking_id": record["booking_id"],
                                          "expected_revision": revision,
                                          "invoice_no": record["invoice_no"],
                                          "email": record["email"]}, attempts=1)
        if status.get("saved"):
            result = status
        elif max_attempts > 1:
            result = _post(action, body, attempts=1)
    saved = bool(result.get("saved"))
    if saved:
        result.setdefault("invoice_no", record["invoice_no"])
        result.setdefault("invoice_verification_code", record["invoice_verification_code"])
    return SaveResult(ok=bool(result.get("ok")) and saved, saved=saved,
                      message=str(result.get("error") or result.get("message") or ""), data=result)
