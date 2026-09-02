# ITKF Hotel Booking Request & Registration System

Production-ready Streamlit application for collecting ITKF 2026 hotel and whole-vehicle transportation requests from individuals and federations. It reserves room allotments through Google Sheets, supports secure request amendments, and creates numbered EUR-only PDF summaries with email delivery.

## Main features

- Separate Individual and Federation registration flows.
- Date-range accommodation pricing with automatic nights and occupancy.
- Live room availability and locked inventory checks at final submission.
- Whole-vehicle transportation for one date, selected dates, or a date range.
- One stable Request ID with email-code verification and revision history.
- Duplicate passport prevention for individual requests.
- AES-protected PDF summaries with logos, verification code, and SHA-256 integrity checks.
- Google Sheets booking/invoice/history records, Google Drive PDF storage, and queued email delivery.
- Light-mode mobile styling and draft preservation across all wizard pages.

## Runtime

- Python 3.11 or newer
- Streamlit 1.40 or newer
- Google Apps Script Web App from `google_apps_script.gs`

Install and run locally:

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

Create `.streamlit/secrets.toml` from `.streamlit/secrets.toml.example`. Never commit the real token.

## Tests

The test suite is offline: it does not write to the real Google Sheet or send real email.

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

See `UPDATE_INSTRUCTIONS.md` for the required Google and Streamlit deployment steps. The application and Apps Script must always be deployed from the same version; this release is `2026-09-02-v5.7`.
