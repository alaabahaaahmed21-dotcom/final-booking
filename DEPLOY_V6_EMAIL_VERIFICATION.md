# Deploy v6.0 safely

This release preserves the existing booking, pricing, hotel, transportation, customer-edit OTP, PDF, invoice and repricing features. The Transportation sheet still includes Hotel, Check-in and Check-out.

## 1. Update GitHub / Streamlit

Replace the project files with this release, or upload the supplied ZIP contents to the same GitHub repository. Keep the existing `.streamlit/secrets.toml` values in Streamlit Cloud.

In **Streamlit Cloud → App settings → Secrets**, add one new private value without removing the existing ones:

```toml
INVOICE_ADMIN_PASSWORD = "choose-a-long-private-password"
```

If this value is omitted, the page falls back to the existing `REPRICING_ADMIN_PASSWORD`, but a separate password is safer.

## 2. Update Google Apps Script

1. Open the Apps Script project connected to the current Google Sheet.
2. Replace its code with `google_apps_script.gs` from this release.
3. Save the project.
4. From the function selector, run `setupSheetsNow` once and approve permissions if Google asks.

This creates/updates the required headers and adds `Email Verifications` and `Admin Audit`. It does not delete existing bookings, invoices, or transportation rows.

## 3. Redeploy the existing Apps Script URL

1. Click **Deploy → Manage deployments**.
2. Open the current Web App deployment with the pencil icon.
3. Choose **New version**.
4. Click **Deploy**.
5. Keep the same Web App URL already stored in Streamlit Secrets.

Do not create a different deployment unless you also intentionally replace the URL in Streamlit.

## 4. Restart Streamlit

After GitHub and Apps Script are both updated, reboot/redeploy the Streamlit app so both sides use schema `2026-10-07-v6.0`.

## 5. Test a new booking

1. Enter a real email on the registration details page.
2. Click **Send verification code**.
3. Enter the 4-digit code received by email.
4. Complete the booking.
5. Confirm the booking row, invoice PDF and email delivery.

The code expires after 10 minutes. A verified address is bound to the submitted booking and the verification token can be used only once.

## 6. Recover an old pending invoice

Open:

`https://23rd-itkf-booking.streamlit.app/?maintenance=invoices`

Log in with `INVOICE_ADMIN_PASSWORD`, then enter the Booking ID.

- If the saved address is wrong: enter the corrected address, type `CORRECT EMAIL`, and apply the correction.
- Then type `SEND INVOICE` and generate/send the invoice.
- If the address is already correct, skip the correction and only use `SEND INVOICE`.

For the two known cases:

- `ITKF-20260902-381FEE7ABE5A`: correct the address to `stkf.office@gmail.com`, then send the invoice.
- `ITKF-20261006-CA17D150C1FA`: the address is already valid; generate/send the pending invoice directly.

The correction changes only the booking email and pending invoice-delivery metadata. It does not change hotel choices, room prices, transportation, totals, or other booking details. Every organizer correction is recorded in the `Admin Audit` sheet.

## 7. Final checks

In the `Bookings` sheet, confirm `Invoice Created` and `Customer Email Sent` are `true`, and that `Invoice File ID`, `Invoice URL`, `Invoice SHA-256`, and `Email Sent At` are populated. The `Invoices` sheet receives the newly generated invoice record.

Do not enable or run repricing for this email-recovery task.
