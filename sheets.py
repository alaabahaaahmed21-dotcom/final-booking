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

def check_availability(booking: dict) -> dict:
    return _post("check_availability", {"booking": booking}, attempts=1)

def save_to_google_sheets(booking: dict, max_attempts: int = 3) -> SaveResult:
    record = dict(booking)
    record["invoice_no"] = "INV-" + record["booking_id"].removeprefix("ITKF-")
    record["invoice_verification_code"] = _verification_code(_secret("BOOKING_API_TOKEN"), record)
    record["status"] = "Request received"
    pdf, payload = None, {}
    try:
        pdf = generate_pdf(record, protect=True)
        payload = {"base64": base64.b64encode(pdf).decode("ascii"), "mime_type": "application/pdf",
                   "filename": record["invoice_no"]+".pdf", "sha256": hashlib.sha256(pdf).hexdigest(),
                   "verification_code": record["invoice_verification_code"]}
    except Exception:
        # Do not lose a request merely because local PDF generation failed.
        pass
    result = _post("create_booking", {"booking": record, "invoice": payload}, attempts=max_attempts)
    saved = bool(result.get("saved"))
    if saved:
        result.setdefault("invoice_no", record["invoice_no"])
        result.setdefault("invoice_verification_code", record["invoice_verification_code"])
        exact = result.pop("invoice_base64", None)
        if exact:
            try:
                data = base64.b64decode(exact, validate=True)
                if data.startswith(b"%PDF-") and hashlib.sha256(data).hexdigest() == result.get("invoice_sha256"):
                    result["_invoice_pdf_bytes"] = data
            except (ValueError, TypeError):
                pass
        # If Drive is pending, the same numbered local PDF can still be downloaded.
        if not result.get("invoice_created") and pdf:
            result["_invoice_pdf_bytes"] = pdf
    return SaveResult(ok=bool(result.get("ok")) and saved, saved=saved,
                      message=str(result.get("error") or result.get("message") or ""), data=result)
