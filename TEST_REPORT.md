# Final QA report - v5.9

Date: 8 September 2026

## Automated results

- Python compilation: passed.
- Google Apps Script syntax check: passed.
- Offline automated suite: **76 tests passed, 0 failed**.
- Google backend simulation: passed for inventory locks, duplicate passports, idempotent retries, booking-status recovery, OTP access, amendments, revision history, queued email, missing PDFs, and corrupted PDF replacement.

## PDF results

- Individual summary: one A4 page, logos visible, AES protected, EUR only.
- Normal Federation summary: one A4 page, logos visible, AES protected, EUR only.
- Maximum 60-service stress summary: four A4 pages with readable 7 pt minimum text; no forced micro-text.
- Strict parsing and empty-password opening: passed.
- Poppler rendering of every generated page: passed with no clipping or overlap observed.
- Copying and modification are disabled; printing is allowed.

## Accommodation pricing

- Every hotel rate is treated as a per-person, per-night amount.
- Room totals multiply rate x room occupancy x room quantity x nights.
- Python client and Google Apps Script backend pricing parity: passed.
- Historical repricing preview, revision archive, PDF queue, idempotent recovery,
  email retry, and customer-data-free preview: passed.

## Scope

The automated suite is intentionally offline and makes no production Google Sheet writes and sends no real email. Complete the controlled live acceptance check in `UPDATE_INSTRUCTIONS.md` after deploying the matching Google Apps Script Web App.
