/**
 * Reliable Google Apps Script backend for the 23rd ITKF booking app.
 * Required properties: SPREADSHEET_ID, DRIVE_FOLDER_ID, BOOKING_API_TOKEN.
 * Optional: INVOICE_FOLDER_ID, COMPANY_NAME, EUR_TO_USD, EUR_TO_EGP.
 */

const BOOKINGS_SHEET = "Bookings";
const INVOICES_SHEET = "Invoices";

const BOOKING_HEADERS = [
  "Booking ID", "Booking Date", "Guest Name", "Nationality", "Nationality Code",
  "Phone Country Code", "Phone", "Email", "Personal Photo File ID", "Personal Photo URL",
  "Passport Photo File ID", "Passport Photo URL", "Hotel", "Meal Plan", "Room Type",
  "Guests", "Check-in", "Check-out", "Nights", "Nightly Rate EUR", "Vehicle Type",
  "Transportation Persons", "Transportation Price Per Person EUR", "Room Total EUR",
  "Transportation Total EUR", "Grand Total EUR", "Grand Total USD", "Grand Total EGP",
  "Invoice No", "Invoice File ID", "Invoice URL", "Invoice Verification Code", "Invoice SHA-256",
  "Customer Email Sent", "Email Sent At",
  "Processing Started", "Status", "Last Error"
];

const TRANSPORT_VEHICLES = [
  "Limousine", "Hiace Bus", "Coaster Bus", "33-Seat Bus", "50-Seat Bus"
];

const INVOICE_HEADERS = [
  "Invoice No", "Booking ID", "Created At", "Customer Name", "Customer Email",
  "Grand Total EUR", "Invoice File ID", "Invoice URL", "Invoice Verification Code",
  "Invoice SHA-256", "Email Status", "Email Sent At", "Last Error"
];

const HOTEL_RATES_EUR = {
  "Tiba Rose El Golf": {
    "Breakfast": {"Single": 80, "Double": 50, "Triple": 45},
    "Half Board": {"Single": 95, "Double": 60, "Triple": 50}
  },
  "Hilton Cairo Heliopolis": {"Breakfast": {"Single": 190, "Double": 110}},
  "Sonesta Hotel Tower & Casino Cairo": {
    "Half Board": {"Single": 185, "Double": 110, "Triple": 93}
  },
  "Baron Hotel Cairo": {"Breakfast": {"Single": 130, "Double": 75, "Triple": 60}},
  "Armor House Hotel, Cairo": {
    "Half Board": {"Single": 75, "Double": 55, "Suite (2 rooms / 4 persons)": 45}
  },
  "Hotel El Forsan": {"Half Board": {"Single": 85, "Double": 60, "Triple": 50}},
  "Hotel Jewel Elnasr": {
    "Breakfast": {"Single": 65, "Double": 47, "Triple": 42},
    "Half Board": {"Single": 75, "Double": 57, "Triple": 52},
    "Full Board": {"Single": 85, "Double": 67, "Triple": 62}
  },
  "Hotel Infantry House": {
    "Breakfast": {"Single": 65, "Double": 40, "Quadruple": 30}
  },
  "Hotel Engineering Authority House": {"Breakfast": {"Single": 70, "Double": 45}}
};


function doGet() {
  return json_({ok: true, service: "itkf-booking-backend", version: "2026-08-27-protected-invoices"});
}


function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return json_({ok: false, saved: false, error_code: "EMPTY_REQUEST"});
    }
    const request = JSON.parse(e.postData.contents);
    authorize_(request.token);
    if (request.action === "check_duplicate") {
      return json_(checkDuplicate_(request.booking_id));
    }
    if (request.action === "create_booking") {
      return json_(createBooking_(
        request.booking || {}, request.images || {},
        request.quote_signature || "", request.invoice || {}
      ));
    }
    return json_({ok: false, saved: false, error_code: "UNKNOWN_ACTION"});
  } catch (error) {
    const code = error && error.code ? String(error.code) : "SERVER_ERROR";
    return json_({
      ok: false, saved: false,
      retryable: code === "BUSY" || code === "TEMPORARY_ERROR",
      error_code: code, error: safeError_(error)
    });
  }
}


function createBooking_(booking, images, quoteSignature, invoicePayload) {
  validateBooking_(booking);
  const invoiceNo = "INV-" + String(booking.booking_id).replace(/^ITKF-/, "");
  let existing = {};
  let rowNumber = 0;

  const startLock = LockService.getScriptLock();
  if (!startLock.tryLock(30000)) throw codedError_("BUSY", "The booking service is busy.");
  try {
    const context = ensureSheet_(BOOKINGS_SHEET, BOOKING_HEADERS);
    rowNumber = findRow_(context.sheet, context.headers, "Booking ID", booking.booking_id);
    if (rowNumber) {
      existing = rowObject_(
        context.headers,
        context.sheet.getRange(rowNumber, 1, 1, context.headers.length).getValues()[0]
      );
      if (String(existing["Status"] || "") === "Confirmed") {
        return resultFromObject_(existing, true, true, "Booking already saved.");
      }
      if (String(existing["Status"] || "") === "Processing" &&
          !processingIsStale_(existing["Processing Started"])) {
        return {
          ok: false, saved: false, row_saved: true, retryable: true,
          error_code: "BUSY", error: "This booking is still being processed."
        };
      }
    }

    recalculateBooking_(booking, quoteSignature);
    booking.invoice_no = invoiceNo;
    verifyInvoiceVerification_(booking, invoiceNo);
    const initial = bookingColumns_(booking);
    initial["Invoice No"] = existing["Invoice No"] || invoiceNo;
    initial["Processing Started"] = new Date().toISOString();
    initial["Status"] = "Processing";
    initial["Last Error"] = "";
    rowNumber = writeRow_(context.sheet, context.headers, rowNumber, initial, existing);
    SpreadsheetApp.flush();
  } finally {
    startLock.releaseLock();
  }

  let personal = existingFile_(existing, "Personal Photo File ID", "Personal Photo URL");
  let passport = existingFile_(existing, "Passport Photo File ID", "Passport Photo URL");
  const fileErrors = [];
  if (!personal.fileId && images.personal_photo) {
    try {
      personal = saveImage_(images.personal_photo, booking.booking_id, "personal-photo");
    } catch (error) {
      fileErrors.push("Personal photo: " + safeError_(error));
    }
  }
  if (!passport.fileId && images.passport_photo) {
    try {
      passport = saveImage_(images.passport_photo, booking.booking_id, "passport");
    } catch (error) {
      fileErrors.push("Passport photo: " + safeError_(error));
    }
  }
  if (!passport.fileId) fileErrors.push("Passport photo was not stored.");

  let invoice = existingFile_(existing, "Invoice File ID", "Invoice URL");
  invoice.sha256 = String(existing["Invoice SHA-256"] || "");
  invoice.verificationCode = String(existing["Invoice Verification Code"] || "");
  let invoiceError = "";
  if (!invoice.fileId) {
    try {
      invoice = saveInvoicePdf_(invoicePayload, booking, invoiceNo);
    } catch (error) {
      invoiceError = safeError_(error);
    }
  }

  let emailSent = truthy_(existing["Customer Email Sent"]);
  let emailSentAt = String(existing["Email Sent At"] || "");
  let emailError = "";
  if (!emailSent && invoice.fileId) {
    try {
      sendInvoiceEmail_(booking, invoiceNo, invoice.fileId, invoice.verificationCode);
      emailSent = true;
      emailSentAt = new Date().toISOString();
    } catch (error) {
      emailError = safeError_(error);
    }
  }

  let status = "Confirmed";
  const errors = [];
  if (fileErrors.length) {
    status = "Saved - file upload failed";
    errors.push(fileErrors.join(" | "));
  }
  if (invoiceError) {
    status = "Saved - invoice failed";
    errors.push("Invoice: " + invoiceError);
  } else if (!emailSent) {
    status = "Saved - email failed";
    errors.push("Email: " + (emailError || "Email was not sent."));
  }

  const finalData = bookingColumns_(booking);
  finalData["Personal Photo File ID"] = personal.fileId || "";
  finalData["Personal Photo URL"] = personal.url || "";
  finalData["Passport Photo File ID"] = passport.fileId || "";
  finalData["Passport Photo URL"] = passport.url || "";
  finalData["Invoice No"] = invoiceNo;
  finalData["Invoice File ID"] = invoice.fileId || "";
  finalData["Invoice URL"] = invoice.url || "";
  finalData["Invoice Verification Code"] = invoice.verificationCode ||
    String(booking.invoice_verification_code || "");
  finalData["Invoice SHA-256"] = invoice.sha256 || "";
  finalData["Customer Email Sent"] = emailSent;
  finalData["Email Sent At"] = emailSentAt;
  finalData["Processing Started"] = "";
  finalData["Status"] = status;
  finalData["Last Error"] = errors.join(" | ");

  const finishLock = LockService.getScriptLock();
  if (!finishLock.tryLock(30000)) {
    throw codedError_("BUSY", "The booking was captured but final status is pending.");
  }
  try {
    const context = ensureSheet_(BOOKINGS_SHEET, BOOKING_HEADERS);
    rowNumber = findRow_(context.sheet, context.headers, "Booking ID", booking.booking_id);
    if (!rowNumber) {
      throw codedError_("TEMPORARY_ERROR", "The captured booking row could not be found.");
    }
    writeRow_(context.sheet, context.headers, rowNumber, finalData, {});
    upsertInvoiceLog_(booking, finalData);
    SpreadsheetApp.flush();
  } finally {
    finishLock.releaseLock();
  }

  return resultFromObject_(finalData, true, fileErrors.length === 0, "Booking saved.");
}


function recalculateBooking_(booking, quoteSignature) {
  verifyQuoteSignature_(booking, quoteSignature);
  booking.nights = nightsBetween_(booking.check_in, booking.check_out);
  if (booking.nights < 1 || booking.nights > 60) {
    throw codedError_("VALIDATION_ERROR", "Invalid number of nights.");
  }
  const hotel = HOTEL_RATES_EUR[booking.hotel];
  const plan = hotel && hotel[booking.meal_plan];
  const rate = plan && plan[booking.room_type];
  if (rate === undefined || rate === null) {
    throw codedError_("VALIDATION_ERROR", "Invalid hotel, meal plan or room type.");
  }

  let transportUnit = 0;
  let transportTotal = 0;
  if (truthy_(booking.wants_transportation)) {
    if (TRANSPORT_VEHICLES.indexOf(String(booking.vehicle_type)) < 0) {
      throw codedError_("VALIDATION_ERROR", "Invalid vehicle type.");
    }
    const persons = Number(booking.transport_persons || 0);
    if (!Number.isInteger(persons) || persons < 1) {
      throw codedError_("VALIDATION_ERROR", "Invalid transportation person count.");
    }
    const suppliedPrice = booking.transport_price_per_person_eur;
    if (suppliedPrice === null || suppliedPrice === undefined || suppliedPrice === "") {
      throw codedError_("TRANSPORT_PRICE_PENDING", "Transportation price is not set yet.");
    }
    if (!isFinite(Number(suppliedPrice)) || Number(suppliedPrice) < 0) {
      throw codedError_("VALIDATION_ERROR", "Invalid transportation price.");
    }
    transportUnit = money_(suppliedPrice);
    transportTotal = money_(transportUnit * persons);
  }

  const roomTotal = money_(Number(rate) * booking.nights);
  const grandEur = money_(roomTotal + transportTotal);
  booking.nightly_rate_eur = money_(rate);
  booking.room_total_eur = roomTotal;
  booking.transport_price_per_person_eur = transportUnit;
  booking.transport_total_eur = transportTotal;
  booking.grand_total_eur = grandEur;
  booking.grand_total_usd = money_(grandEur * optionalNumberProp_("EUR_TO_USD", 1 / 0.92));
  booking.grand_total_egp = money_(grandEur * optionalNumberProp_("EUR_TO_EGP", 49 / 0.92));
}


function bookingColumns_(booking) {
  return {
    "Booking ID": booking.booking_id, "Booking Date": booking.booking_date,
    "Guest Name": booking.guest_name, "Nationality": booking.nationality,
    "Nationality Code": booking.nationality_code, "Phone Country Code": booking.phone_country_code,
    "Phone": booking.phone, "Email": booking.email, "Hotel": booking.hotel,
    "Meal Plan": booking.meal_plan, "Room Type": booking.room_type,
    "Guests": Number(booking.guests || 0), "Check-in": booking.check_in,
    "Check-out": booking.check_out, "Nights": booking.nights,
    "Nightly Rate EUR": money_(booking.nightly_rate_eur),
    "Vehicle Type": truthy_(booking.wants_transportation) ? booking.vehicle_type : "-",
    "Transportation Persons": truthy_(booking.wants_transportation) ? Number(booking.transport_persons || 0) : 0,
    "Transportation Price Per Person EUR": money_(booking.transport_price_per_person_eur),
    "Room Total EUR": money_(booking.room_total_eur),
    "Transportation Total EUR": money_(booking.transport_total_eur),
    "Grand Total EUR": money_(booking.grand_total_eur),
    "Grand Total USD": money_(booking.grand_total_usd),
    "Grand Total EGP": money_(booking.grand_total_egp)
  };
}


function saveInvoicePdf_(payload, booking, invoiceNo) {
  if (!payload || String(payload.mime_type || "").toLowerCase() !== "application/pdf" ||
      !payload.base64) {
    throw codedError_("INVALID_INVOICE", "A PDF invoice payload is required.");
  }
  if (String(payload.filename || "") !== invoiceNo + ".pdf") {
    throw codedError_("INVALID_INVOICE", "Invoice filename does not match its number.");
  }
  if (String(payload.verification_code || "") !== String(booking.invoice_verification_code || "")) {
    throw codedError_("INVALID_INVOICE", "Invoice verification code does not match.");
  }
  const bytes = Utilities.base64Decode(String(payload.base64));
  if (!bytes.length || bytes.length > 5 * 1024 * 1024) {
    throw codedError_("INVALID_INVOICE", "Invoice PDF is empty or exceeds 5 MB.");
  }
  const magic = bytes.slice(0, 5).map(function(value) {
    return String.fromCharCode((Number(value) + 256) % 256);
  }).join("");
  if (magic !== "%PDF-") {
    throw codedError_("INVALID_INVOICE", "Invoice content is not a PDF.");
  }
  const sha256 = digestHex_(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, bytes));
  if (!constantTimeEqual_(sha256, String(payload.sha256 || "").toLowerCase())) {
    throw codedError_("INVALID_INVOICE", "Invoice integrity check failed.");
  }
  const pdfBlob = Utilities.newBlob(bytes, "application/pdf", invoiceNo + ".pdf");
  const folderId = optionalProp_("INVOICE_FOLDER_ID") || prop_("DRIVE_FOLDER_ID");
  const pdfFile = DriveApp.getFolderById(folderId).createFile(pdfBlob);
  return {
    fileId: pdfFile.getId(), url: pdfFile.getUrl(), sha256: sha256,
    verificationCode: String(payload.verification_code)
  };
}


function sendInvoiceEmail_(booking, invoiceNo, invoiceFileId, verificationCode) {
  if (MailApp.getRemainingDailyQuota() < 1) {
    throw codedError_("EMAIL_QUOTA_EXHAUSTED", "Daily email quota is exhausted.");
  }
  const companyName = optionalProp_("COMPANY_NAME") ||
    "Egyptian Traditional Karate Federation";
  const subject = invoiceNo + " - 23rd ITKF Championship Booking Invoice";
  const body = "Dear " + booking.guest_name + ",\n\nYour booking has been confirmed. " +
    "Booking ID: " + booking.booking_id + "\nInvoice: " + invoiceNo +
    "\nVerification Code: " + verificationCode +
    "\nGrand Total: EUR " + money_(booking.grand_total_eur).toFixed(2) +
    "\n\nYour invoice is attached.";
  const htmlBody = "<p>Dear " + escapeHtml_(booking.guest_name) + ",</p>" +
    "<p>Your booking has been confirmed.</p>" +
    "<p><b>Booking ID:</b> " + escapeHtml_(booking.booking_id) + "<br>" +
    "<b>Invoice:</b> " + escapeHtml_(invoiceNo) + "<br>" +
    "<b>Verification Code:</b> " + escapeHtml_(verificationCode) + "<br>" +
    "<b>Grand Total:</b> EUR " + money_(booking.grand_total_eur).toFixed(2) + "</p>" +
    "<p>Your invoice is attached.</p>";
  MailApp.sendEmail({
    to: booking.email, subject: subject, body: body, htmlBody: htmlBody, name: companyName,
    attachments: [DriveApp.getFileById(invoiceFileId).getBlob().setName(invoiceNo + ".pdf")]
  });
}


function retryPendingEmails() {
  const quota = Math.min(MailApp.getRemainingDailyQuota(), 50);
  if (quota < 1) return;
  const context = ensureSheet_(BOOKINGS_SHEET, BOOKING_HEADERS);
  if (context.sheet.getLastRow() < 2) return;
  const rows = context.sheet.getRange(
    2, 1, context.sheet.getLastRow() - 1, context.headers.length
  ).getValues();
  let sent = 0;
  rows.forEach(function(row, index) {
    if (sent >= quota) return;
    const item = rowObject_(context.headers, row);
    if (String(item["Status"] || "") !== "Saved - email failed") return;
    if (!item["Invoice File ID"] || truthy_(item["Customer Email Sent"])) return;
    try {
      sendInvoiceEmail_({
        guest_name: item["Guest Name"], booking_id: item["Booking ID"],
        email: item["Email"], grand_total_eur: item["Grand Total EUR"]
      }, item["Invoice No"], item["Invoice File ID"], item["Invoice Verification Code"]);
      item["Customer Email Sent"] = true;
      item["Email Sent At"] = new Date().toISOString();
      item["Status"] = "Confirmed";
      item["Last Error"] = "";
      writeRow_(context.sheet, context.headers, index + 2, item, {});
      upsertInvoiceLog_({
        booking_id: item["Booking ID"], booking_date: item["Booking Date"],
        guest_name: item["Guest Name"], email: item["Email"],
        grand_total_eur: item["Grand Total EUR"]
      }, item);
      sent += 1;
    } catch (error) {
      item["Last Error"] = "Email: " + safeError_(error);
      writeRow_(context.sheet, context.headers, index + 2, item, {});
    }
  });
  SpreadsheetApp.flush();
}


function installHourlyEmailRetryTrigger() {
  const exists = ScriptApp.getProjectTriggers().some(function(trigger) {
    return trigger.getHandlerFunction() === "retryPendingEmails";
  });
  if (!exists) {
    ScriptApp.newTrigger("retryPendingEmails").timeBased().everyHours(1).create();
  }
}


function upsertInvoiceLog_(booking, data) {
  if (!data["Invoice No"]) return;
  const context = ensureSheet_(INVOICES_SHEET, INVOICE_HEADERS);
  const row = findRow_(context.sheet, context.headers, "Invoice No", data["Invoice No"]);
  const log = {
    "Invoice No": data["Invoice No"], "Booking ID": booking.booking_id,
    "Created At": booking.booking_date, "Customer Name": booking.guest_name,
    "Customer Email": booking.email, "Grand Total EUR": money_(booking.grand_total_eur),
    "Invoice File ID": data["Invoice File ID"] || "",
    "Invoice URL": data["Invoice URL"] || "",
    "Invoice Verification Code": data["Invoice Verification Code"] || "",
    "Invoice SHA-256": data["Invoice SHA-256"] || "",
    "Email Status": truthy_(data["Customer Email Sent"]) ? "Sent" : "Failed",
    "Email Sent At": data["Email Sent At"] || "", "Last Error": data["Last Error"] || ""
  };
  writeRow_(context.sheet, context.headers, row, log, {});
}


function checkDuplicate_(bookingId) {
  const context = ensureSheet_(BOOKINGS_SHEET, BOOKING_HEADERS);
  return {
    ok: true,
    exists: Boolean(findRow_(context.sheet, context.headers, "Booking ID", bookingId))
  };
}


function ensureSheet_(name, requiredHeaders) {
  const spreadsheet = SpreadsheetApp.openById(prop_("SPREADSHEET_ID"));
  let sheet = spreadsheet.getSheetByName(name);
  if (!sheet) sheet = spreadsheet.insertSheet(name);
  let headers = [];
  if (sheet.getLastColumn() > 0) {
    headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0].map(String);
  }
  requiredHeaders.forEach(function(header) {
    if (headers.indexOf(header) < 0) headers.push(header);
  });
  if (!headers.length) headers = requiredHeaders.slice();
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.setFrozenRows(1);
  sheet.getRange(1, 1, 1, headers.length)
    .setFontWeight("bold").setBackground("#C8102E").setFontColor("#FFFFFF");
  return {sheet: sheet, headers: headers};
}


function findRow_(sheet, headers, headerName, value) {
  if (!value || sheet.getLastRow() < 2) return 0;
  const column = headers.indexOf(headerName) + 1;
  if (column < 1) return 0;
  const match = sheet.getRange(2, column, sheet.getLastRow() - 1, 1)
    .createTextFinder(String(value)).matchEntireCell(true).findNext();
  return match ? match.getRow() : 0;
}


function writeRow_(sheet, headers, rowNumber, data, existing) {
  const values = headers.map(function(header) {
    if (Object.prototype.hasOwnProperty.call(data, header)) return data[header];
    if (existing && Object.prototype.hasOwnProperty.call(existing, header)) return existing[header];
    return "";
  });
  if (!rowNumber) rowNumber = sheet.getLastRow() + 1;
  sheet.getRange(rowNumber, 1, 1, headers.length).setValues([values]);
  const bookingIdColumn = headers.indexOf("Booking ID") + 1;
  const phoneColumn = headers.indexOf("Phone") + 1;
  if (bookingIdColumn > 0) sheet.getRange(rowNumber, bookingIdColumn).setNumberFormat("@");
  if (phoneColumn > 0) sheet.getRange(rowNumber, phoneColumn).setNumberFormat("@");
  return rowNumber;
}


function rowObject_(headers, values) {
  const object = {};
  headers.forEach(function(header, index) { object[header] = values[index]; });
  return object;
}


function saveImage_(image, bookingId, kind) {
  if (!image || !image.base64 || !image.mime_type || !image.extension) {
    throw new Error("Incomplete image payload.");
  }
  const allowed = {"image/jpeg": "jpg", "image/png": "png"};
  const extension = allowed[String(image.mime_type).toLowerCase()];
  if (!extension || extension !== String(image.extension).toLowerCase()) {
    throw new Error("Unsupported image type.");
  }
  const bytes = Utilities.base64Decode(image.base64);
  if (!bytes.length || bytes.length > 8 * 1024 * 1024) {
    throw new Error("Image is empty or exceeds 8 MB.");
  }
  const safeId = String(bookingId).replace(/[^A-Za-z0-9_-]/g, "");
  const filename = safeId + "_" + kind + "_" + Utilities.getUuid() + "." + extension;
  const file = DriveApp.getFolderById(prop_("DRIVE_FOLDER_ID"))
    .createFile(Utilities.newBlob(bytes, image.mime_type, filename));
  return {fileId: file.getId(), url: file.getUrl()};
}


function existingFile_(object, idHeader, urlHeader) {
  return {fileId: String(object[idHeader] || ""), url: String(object[urlHeader] || "")};
}


function resultFromObject_(data, saved, filesOk, message) {
  return {
    ok: Boolean(saved), saved: Boolean(saved), files_ok: Boolean(filesOk),
    booking_id: String(data["Booking ID"] || ""), status: String(data["Status"] || ""),
    personal_photo_url: String(data["Personal Photo URL"] || ""),
    passport_photo_url: String(data["Passport Photo URL"] || ""),
    invoice_no: String(data["Invoice No"] || ""), invoice_url: String(data["Invoice URL"] || ""),
    invoice_verification_code: String(data["Invoice Verification Code"] || ""),
    invoice_sha256: String(data["Invoice SHA-256"] || ""),
    invoice_created: Boolean(data["Invoice File ID"]),
    customer_email_sent: truthy_(data["Customer Email Sent"]),
    email_error: truthy_(data["Customer Email Sent"]) ? "" : String(data["Last Error"] || ""),
    nightly_rate_eur: number_(data["Nightly Rate EUR"]),
    room_total_eur: number_(data["Room Total EUR"]),
    transport_price_per_person_eur: number_(data["Transportation Price Per Person EUR"]),
    transport_total_eur: number_(data["Transportation Total EUR"]),
    grand_total_eur: number_(data["Grand Total EUR"]),
    grand_total_usd: number_(data["Grand Total USD"]),
    grand_total_egp: number_(data["Grand Total EGP"]), message: message || ""
  };
}


function validateBooking_(booking) {
  const required = [
    "booking_id", "booking_date", "guest_name", "nationality", "nationality_code",
    "phone_country_code", "phone", "email", "hotel", "meal_plan", "room_type",
    "check_in", "check_out"
  ];
  required.forEach(function(field) {
    if (booking[field] === undefined || booking[field] === null ||
        String(booking[field]).trim() === "") {
      throw codedError_("VALIDATION_ERROR", "Missing booking field: " + field);
    }
  });
  if (!/^\+[1-9]\d{6,14}$/.test(String(booking.phone))) {
    throw codedError_("VALIDATION_ERROR", "Phone must be stored in international E.164 format.");
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(booking.email))) {
    throw codedError_("VALIDATION_ERROR", "Invalid email address.");
  }
}


function nightsBetween_(checkIn, checkOut) {
  const start = isoDate_(checkIn);
  const end = isoDate_(checkOut);
  return Math.round((end.getTime() - start.getTime()) / 86400000);
}


function isoDate_(value) {
  const parts = String(value).split("-");
  if (parts.length !== 3) throw codedError_("VALIDATION_ERROR", "Invalid ISO date.");
  const parsed = new Date(Date.UTC(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2])));
  if (isNaN(parsed.getTime())) throw codedError_("VALIDATION_ERROR", "Invalid ISO date.");
  return parsed;
}


function processingIsStale_(value) {
  const timestamp = new Date(String(value || "")).getTime();
  return !timestamp || Date.now() - timestamp > 5 * 60 * 1000;
}


function truthy_(value) {
  return value === true || String(value).toLowerCase() === "true" || String(value) === "1";
}


function money_(value) {
  return Math.round((Number(value) || 0) * 100) / 100;
}


function canonicalQuote_(booking) {
  const wantsTransport = truthy_(booking.wants_transportation);
  return [
    String(booking.booking_id || ""), String(booking.hotel || ""),
    String(booking.meal_plan || ""), String(booking.room_type || ""),
    String(Number(booking.nights || 0)), wantsTransport ? "1" : "0",
    wantsTransport ? String(booking.vehicle_type || "-") : "-",
    wantsTransport ? String(Number(booking.transport_persons || 0)) : "0",
    money_(booking.transport_price_per_person_eur).toFixed(2)
  ].join("\n");
}


function invoiceVerificationMessage_(booking, invoiceNo) {
  return [
    String(invoiceNo || ""), String(booking.booking_id || ""),
    String(booking.email || ""), money_(booking.grand_total_eur).toFixed(2)
  ].join("\n");
}


function hmacHex_(message) {
  return digestHex_(Utilities.computeHmacSha256Signature(
    String(message), prop_("BOOKING_API_TOKEN"), Utilities.Charset.UTF_8
  ));
}


function digestHex_(bytes) {
  return bytes.map(function(value) {
    const normalized = (Number(value) + 256) % 256;
    return normalized.toString(16).padStart(2, "0");
  }).join("");
}


function constantTimeEqual_(left, right) {
  const first = String(left || "");
  const second = String(right || "");
  let different = first.length ^ second.length;
  const length = Math.max(first.length, second.length);
  for (let index = 0; index < length; index += 1) {
    different |= (first.charCodeAt(index) || 0) ^ (second.charCodeAt(index) || 0);
  }
  return different === 0;
}


function verifyQuoteSignature_(booking, providedSignature) {
  const expected = hmacHex_(canonicalQuote_(booking));
  if (!constantTimeEqual_(expected, String(providedSignature || "").toLowerCase())) {
    throw codedError_("INVALID_QUOTE", "Booking price verification failed.");
  }
}


function verifyInvoiceVerification_(booking, invoiceNo) {
  const digest = hmacHex_(invoiceVerificationMessage_(booking, invoiceNo)).toUpperCase().slice(0, 16);
  const expected = digest.match(/.{1,4}/g).join("-");
  if (!constantTimeEqual_(expected, String(booking.invoice_verification_code || "").toUpperCase())) {
    throw codedError_("INVALID_INVOICE", "Invoice verification code is invalid.");
  }
}


function number_(value) {
  const parsed = Number(value);
  return isFinite(parsed) ? parsed : 0;
}


function optionalNumberProp_(name, fallback) {
  const raw = PropertiesService.getScriptProperties().getProperty(name);
  return raw !== null && raw !== "" && isFinite(Number(raw)) ? Number(raw) : fallback;
}


function optionalProp_(name) {
  return PropertiesService.getScriptProperties().getProperty(name) || "";
}


function prop_(name) {
  const value = optionalProp_(name);
  if (!value) throw codedError_("MISSING_PROPERTY", "Missing Script Property: " + name);
  return value;
}


function authorize_(providedToken) {
  if (!providedToken || String(providedToken) !== prop_("BOOKING_API_TOKEN")) {
    throw codedError_("UNAUTHORIZED", "Unauthorized request.");
  }
}


function codedError_(code, message) {
  const error = new Error(message);
  error.code = code;
  return error;
}


function safeError_(error) {
  return error && error.message ? String(error.message).slice(0, 500) : "Unknown error";
}


function escapeHtml_(value) {
  return String(value || "").replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/\"/g, "&quot;").replace(/'/g, "&#039;");
}


function json_(object) {
  return ContentService.createTextOutput(JSON.stringify(object))
    .setMimeType(ContentService.MimeType.JSON);
}
