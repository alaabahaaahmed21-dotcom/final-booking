# Production update - v5.7

Upload and deploy every file in this release together. Do not combine `app.py`, `config.py`, `sheets.py`, `pdf_generator.py`, or `google_apps_script.gs` with an older release.

## 1. Update GitHub / Streamlit

1. Replace the project files with this release, including `requirements.txt`.
2. Keep the three logos and the bundled fonts inside `assets/`.
3. In Streamlit Cloud, open **App settings > Secrets** and set:

```toml
GOOGLE_APPS_SCRIPT_URL = "https://script.google.com/macros/s/YOUR_DEPLOYMENT_ID/exec"
BOOKING_API_TOKEN = "YOUR_PRIVATE_RANDOM_TOKEN"
```

4. Save the secrets and reboot the Streamlit app after the Google deployment below is complete.

## 2. Update Google Apps Script

1. Open the existing Apps Script project connected to the booking system.
2. Replace the complete contents of `Code.gs` with `google_apps_script.gs` from this release and save.
3. Open **Project Settings > Script Properties** and verify:

   - `SPREADSHEET_ID`
   - `BOOKING_API_TOKEN` - exactly the same private value used by Streamlit
   - `INVOICE_FOLDER_ID` - the Google Drive folder for PDFs
   - `COMPANY_NAME` - optional sender name
   - `PUBLIC_APP_URL` - optional public Streamlit URL included in emails

4. From the function menu, run these functions once in order and approve Google permissions if requested:

   1. `setupSheetsNow`
   2. `syncOfficialRoomInventoryNow`
   3. `installRetryTrigger`
   4. `diagnoseBackend`

   `setupSheetsNow` preserves existing bookings. It does not reset booking data.

5. Open **Deploy > Manage deployments**, edit the current Web App deployment, choose **New version**, then **Deploy**.
6. Confirm **Execute as: Me** and **Who has access: Anyone**.
7. Copy the final `/exec` URL into the Streamlit secret and reboot the app.

## 3. Required acceptance check

Use a controlled test email before handover:

1. Submit one Individual request for a Tiba Rose quadruple room.
2. Submit one Federation request with multiple room types and repeated transportation dates.
3. Confirm each request appears once in `Bookings` and its invoice appears in `Invoices`.
4. Confirm the protected PDF opens from the app, Google Drive, Android email, and desktop email.
5. Confirm the email arrives and the same Request ID can be opened and amended with the email verification code.
6. Confirm an amendment updates the existing booking row and creates a new invoice revision instead of a duplicate request.

If `diagnoseBackend` does not report version `2026-09-02-v5.7`, stop and deploy the matching Apps Script version before accepting real requests.
