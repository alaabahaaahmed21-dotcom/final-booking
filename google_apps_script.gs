/**
 * ITKF request backend v3. Existing Bookings/Invoices rows are preserved.
 * Properties: SPREADSHEET_ID, BOOKING_API_TOKEN, INVOICE_FOLDER_ID
 * (DRIVE_FOLDER_ID is supported as a fallback invoice folder).
 * Deploy: Execute as Me; Anyone. The token is required for every POST action.
 */
const VERSION = "2026-08-30-v3";
const BOOKINGS_SHEET = "Bookings", INVOICES_SHEET = "Invoices", INVENTORY_SHEET = "Room Inventory";
const BOOKING_HEADERS = [
  "Booking ID","Booking Date","Registration Type","Guest Name","Federation Name","Date of Birth",
  "Passport Number","Nationality","Nationality Code","Phone","Email","Hotel","Meal Plan",
  "Room Type","Number of Rooms","Guests","Check-in","Check-out","Nights","Rooms JSON",
  "Transportation JSON","Transportation Rate Version","Room Total EUR","Transportation Total EUR",
  "Grand Total EUR","Invoice No","Invoice Verification Code","Invoice File ID","Invoice URL",
  "Invoice SHA-256","Customer Email Sent","Email Sent At","Status","Document Status",
  "Processing Started","Last Error","Request Hash","Booking JSON","Schema Version",
  "Federation Country","Federation Country Code"
];
const INVOICE_HEADERS = [
  "Invoice No","Booking ID","Created At","Customer Name","Customer Email","Grand Total EUR",
  "Invoice File ID","Invoice URL","Invoice Verification Code","Invoice SHA-256","Email Status","Last Error"
];
const INVENTORY_HEADERS = ["Hotel","Room Type","Date","Capacity"];
const ROOM_OCCUPANCY = {"Single":1,"Double":2,"Triple":3,"Quadruple":4,"Suite (2 rooms / 4 persons)":4};
const TRANSPORT_RATE_VERSION = "2026-08-30-final-full-vehicle";
const TRANSPORT = {
  "Limousine (3 Seats)": {capacity:3, prices:[30,30,110,145]},
  "H1 / Van (7 Seats)": {capacity:7, prices:[50,50,150,170]},
  "Toyota Hiace (10 Seats)": {capacity:10, prices:[60,60,160,200]},
  "Coaster (26 Seats)": {capacity:26, prices:[100,100,200,240]},
  "Bus (50 Seats)": {capacity:50, prices:[190,190,300,400]}
};
const SERVICES = {
  "Airport Transfer": {index:0, hours:0, directions:["Airport to Hotel","Hotel to Airport"]},
  "Stadium Transfer": {index:1, hours:0, directions:["Hotel to Stadium","Stadium to Hotel"]},
  "Daily 8 Hours": {index:2, hours:8, directions:[]},
  "Daily 12 Hours": {index:3, hours:12, directions:[]}
};
// Original hotel names and rates retained, using the existing rate per room/night.
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

function doGet() { return json_({ok:true,service:"itkf-booking-backend",version:VERSION}); }
function doPost(e) {
  try {
    const contents = e && e.postData && e.postData.contents;
    if (!contents || contents.length > 8*1024*1024) throw codedError_("INVALID_REQUEST","Invalid request body.");
    const req = JSON.parse(contents);
    if (!req.token || !equal_(String(req.token), prop_("BOOKING_API_TOKEN")))
      throw codedError_("UNAUTHORIZED","The booking service credentials do not match.");
    if (req.schema_version !== VERSION) throw codedError_("SCHEMA_VERSION","Update the Apps Script deployment and the application together.");
    if (req.action === "check_availability") {
      return json_(locked_(function() {
        const b = accommodation_(req.booking || {});
        return {ok:true,availability:availability_(b, rows_(ensureSheet_(BOOKINGS_SHEET,BOOKING_HEADERS)))};
      }));
    }
    if (req.action === "create_booking") return json_(createBooking_(req.booking || {}, req.invoice || {}));
    if (req.action === "check_duplicate") {
      return json_({ok:true,exists:passportExists_(rows_(ensureSheet_(BOOKINGS_SHEET,BOOKING_HEADERS)),req.passport_number)});
    }
    throw codedError_("UNKNOWN_ACTION","Unsupported action.");
  } catch (err) {
    return json_({ok:false,saved:false,error_code:err.code || "SERVER_ERROR",
      retryable:err.code === "BUSY",error:safeError_(err)});
  }
}
function locked_(callback) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30000)) throw codedError_("BUSY","The service is busy. Retry this same request.");
  try { return callback(); } finally { lock.releaseLock(); }
}
function normalizeGuestName_(v) { return String(v || "").trim().replace(/\s+/g," ").toUpperCase(); }
function normalizePassportNumber_(v) { return String(v || "").toUpperCase().replace(/[^A-Z0-9]/g,""); }
function int_(v,label,maximum,zero) {
  if (typeof v === "boolean" || !/^\d+$/.test(String(v))) throw codedError_("VALIDATION_ERROR",label+" must be a whole number.");
  const n=Number(v);
  if (!Number.isSafeInteger(n) || n<(zero ? 0:1) || n>maximum) throw codedError_("VALIDATION_ERROR","Invalid "+label+".");
  return n;
}
function iso_(v) {
  const value = String(v);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) throw codedError_("VALIDATION_ERROR","Invalid date.");
  const d = new Date(value+"T00:00:00Z");
  if (!isFinite(d.getTime()) || d.toISOString().slice(0,10)!==value) throw codedError_("VALIDATION_ERROR","Invalid date.");
  return value;
}
function nights_(start,end) {
  const count=(Date.parse(iso_(end))-Date.parse(iso_(start)))/86400000;
  if (!Number.isInteger(count) || count<1) throw codedError_("VALIDATION_ERROR","The check-out date must be after the check-in date.");
  if (count>60) throw codedError_("VALIDATION_ERROR","Stay cannot exceed 60 nights.");
  return count;
}
function dates_(start,end) {
  const count=nights_(start,end), time=Date.parse(start);
  return Array.from({length:count},(_,i)=>new Date(time+i*86400000).toISOString().slice(0,10));
}
function minutes_(v) {
  if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(String(v))) throw codedError_("VALIDATION_ERROR","Invalid service time.");
  const p=v.split(":").map(Number); return p[0]*60+p[1];
}
function accommodation_(raw) {
  const plans=HOTEL_RATES_EUR[raw.hotel], rates=plans && plans[raw.meal_plan];
  if (!rates) throw codedError_("VALIDATION_ERROR","Invalid hotel or meal plan.");
  const b={hotel:raw.hotel,meal_plan:raw.meal_plan,check_in:iso_(raw.check_in),check_out:iso_(raw.check_out)};
  b.nights=nights_(b.check_in,b.check_out);
  if (!Array.isArray(raw.rooms) || !raw.rooms.length || raw.rooms.length>Object.keys(rates).length)
    throw codedError_("VALIDATION_ERROR","Choose at least one valid room type.");
  const seen={}; b.guests=0; b.room_count=0; b.room_total_eur=0;
  b.rooms=raw.rooms.map(function(r) {
    if (!r || !Object.prototype.hasOwnProperty.call(rates,r.room_type) || seen[r.room_type])
      throw codedError_("VALIDATION_ERROR","Invalid or duplicate room type.");
    seen[r.room_type]=true;
    const quantity=int_(r.quantity,"room quantity",5000,false), unit=rates[r.room_type];
    b.guests+=quantity*ROOM_OCCUPANCY[r.room_type]; b.room_count+=quantity;
    const total=money_(quantity*unit*b.nights); b.room_total_eur+=total;
    return {room_type:r.room_type,quantity:quantity,unit_rate_eur:unit,total_eur:total};
  });
  b.room_total_eur=money_(b.room_total_eur);
  return b;
}
function transport_(raw) {
  if (!Array.isArray(raw) || raw.length>60) throw codedError_("VALIDATION_ERROR","Invalid transportation list.");
  return raw.map(function(r) {
    if (!r || !Object.prototype.hasOwnProperty.call(SERVICES,r.service)) throw codedError_("VALIDATION_ERROR","Invalid transportation service.");
    const s=SERVICES[r.service], date=iso_(r.date);
    if (s.directions.length && s.directions.indexOf(r.direction)<0) throw codedError_("VALIDATION_ERROR","Choose a transfer direction.");
    const duration=minutes_(r.end_time)-minutes_(r.start_time)+(r.ends_next_day===true ? 1440:0);
    if (duration<=0 || duration>1440 || (s.hours && duration>s.hours*60))
      throw codedError_("VALIDATION_ERROR","The time range exceeds the selected daily package.");
    const persons=int_(r.persons,"passengers",5000,false);
    if (!r.vehicles || Array.isArray(r.vehicles) || typeof r.vehicles!=="object") throw codedError_("VALIDATION_ERROR","Select vehicles.");
    let seats=0,total=0; const vehicles={},lines=[];
    Object.keys(r.vehicles).forEach(function(name) {
      if (!Object.prototype.hasOwnProperty.call(TRANSPORT,name)) throw codedError_("VALIDATION_ERROR","Unknown vehicle.");
      const qty=int_(r.vehicles[name],"vehicle quantity",100,true);
      if (!qty) return;
      const vehicle=TRANSPORT[name], unit=vehicle.prices[s.index];
      vehicles[name]=qty; seats+=qty*vehicle.capacity; total+=qty*unit;
      lines.push({vehicle:name,quantity:qty,unit_price_eur:unit,total_eur:money_(qty*unit)});
    });
    if (seats<persons) throw codedError_("VALIDATION_ERROR","Add seats for "+(persons-seats)+" remaining passengers.");
    return {date:date,service:r.service,direction:s.directions.length?r.direction:"",
      start_time:r.start_time,end_time:r.end_time,ends_next_day:r.ends_next_day===true,
      duration_minutes:duration,persons:persons,vehicles:vehicles,seats:seats,remaining:0,
      vehicle_lines:lines,total_eur:money_(total)};
  });
}
function normalizeBooking_(raw) {
  if (raw.schema_version!==VERSION) throw codedError_("SCHEMA_VERSION","The app and backend must use the same version.");
  if (!/^ITKF-\d{8}-[A-F0-9]{12}$/.test(String(raw.booking_id))) throw codedError_("VALIDATION_ERROR","Invalid request ID.");
  const type=raw.registration_type;
  if (["Individual","Federation"].indexOf(type)<0) throw codedError_("VALIDATION_ERROR","Invalid registration type.");
  const name=type==="Individual"?normalizeGuestName_(raw.guest_name):String(raw.federation_name||"").trim();
  if (!name || name.length>150) throw codedError_("VALIDATION_ERROR","Enter a name of up to 150 characters.");
  const email=String(raw.email||"").trim(), phone=String(raw.phone||"").trim();
  if (email.length>254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw codedError_("VALIDATION_ERROR","Invalid email address.");
  if (!/^\+[1-9]\d{6,14}$/.test(phone)) throw codedError_("VALIDATION_ERROR","Invalid international phone number.");
  const b=Object.assign(accommodation_(raw),{schema_version:VERSION,registration_type:type,
    booking_id:raw.booking_id,booking_date:String(raw.booking_date||""),
    guest_name:type==="Individual"?name:"",federation_name:type==="Federation"?name:"",
    email:email,phone:phone,passport_number:"",date_of_birth:"",nationality:"",nationality_code:"",
    federation_country:"",federation_country_code:""});
  if (!isFinite(Date.parse(b.booking_date))) throw codedError_("VALIDATION_ERROR","Invalid request date.");
  if (type==="Individual") {
    b.passport_number=normalizePassportNumber_(raw.passport_number);
    if (!/^[A-Z0-9]{5,20}$/.test(b.passport_number)) throw codedError_("VALIDATION_ERROR","Invalid passport number.");
    b.date_of_birth=iso_(raw.date_of_birth);
    if (b.date_of_birth<"1900-01-01" || Date.parse(b.date_of_birth)>Date.now()) throw codedError_("VALIDATION_ERROR","Invalid date of birth.");
    b.nationality=String(raw.nationality||"").trim(); b.nationality_code=String(raw.nationality_code||"");
    if (!b.nationality || !/^[A-Z]{2}$/.test(b.nationality_code)) throw codedError_("VALIDATION_ERROR","Nationality is required.");
    if (b.room_count!==1) throw codedError_("VALIDATION_ERROR","Use Federation registration for multiple rooms.");
  } else {
    b.federation_country=String(raw.federation_country||"").trim();
    b.federation_country_code=String(raw.federation_country_code||"");
    if (!b.federation_country || b.federation_country.length>150 || !/^[A-Z]{2}$/.test(b.federation_country_code))
      throw codedError_("VALIDATION_ERROR","Please select the federation country.");
  }
  b.transport_services=transport_(raw.transport_services || []);
  b.transport_total_eur=money_(b.transport_services.reduce((sum,r)=>sum+r.total_eur,0));
  b.grand_total_eur=money_(b.room_total_eur+b.transport_total_eur);
  b.transport_rate_version=TRANSPORT_RATE_VERSION;
  if (!isFinite(Number(raw.grand_total_eur)) || Math.abs(Number(raw.grand_total_eur)-b.grand_total_eur)>0.001)
    throw codedError_("QUOTE_CHANGED","The quote changed. Please review the current prices.");
  b.invoice_no="INV-"+b.booking_id.replace(/^ITKF-/,"");
  b.invoice_verification_code=verificationCode_(b);
  b.status="Request received";
  if (JSON.stringify(b).length>45000) throw codedError_("VALIDATION_ERROR","This request has too many service details. Split it into smaller requests.");
  return b;
}
function requestHash_(b) {
  // Only user choices; computed totals and generated PDF bytes are deliberately excluded.
  const data={};
  ["registration_type","guest_name","federation_name","passport_number","date_of_birth",
   "nationality","nationality_code","phone","email","hotel","meal_plan","check_in","check_out"].forEach(k=>data[k]=b[k]||"");
  // Only add new keys when supplied, retaining the hash of pre-v3 requests.
  if (b.registration_type==="Federation" && (b.federation_country || b.federation_country_code)) {
    data.federation_country=b.federation_country||"";
    data.federation_country_code=b.federation_country_code||"";
  }
  data.rooms=(b.rooms||[]).map(r=>({room_type:r.room_type,quantity:r.quantity}));
  data.transport_services=(b.transport_services||[]).map(r=>({
    date:r.date,service:r.service,direction:r.direction||"",start_time:r.start_time,end_time:r.end_time,
    ends_next_day:r.ends_next_day===true,persons:r.persons,vehicles:r.vehicles
  }));
  return sha_(JSON.stringify(sorted_(data)));
}
function sorted_(value) {
  if (Array.isArray(value)) return value.map(sorted_);
  if (value && typeof value==="object") {
    const out={}; Object.keys(value).sort().forEach(k=>out[k]=sorted_(value[k])); return out;
  }
  return value;
}
function passportExists_(rows,passport) {
  const value=normalizePassportNumber_(passport);
  return Boolean(value) && rows.some(r=>normalizePassportNumber_(r["Passport Number"])===value);
}
function inventory_() {
  const ctx=ensureSheet_(INVENTORY_SHEET,INVENTORY_HEADERS), index={};
  rows_(ctx).forEach(function(r) {
    if (!r.Hotel && !r["Room Type"]) return;
    const date=r.Date==="*"?"*":cellDate_(r.Date);
    const key=String(r.Hotel)+"|"+String(r["Room Type"])+"|"+date;
    if (Object.prototype.hasOwnProperty.call(index,key)) throw codedError_("INVENTORY_CONFIG","Duplicate inventory setting. Contact the organizer.");
    index[key]=int_(r.Capacity,"inventory capacity",100000,true);
  });
  return index;
}
function availability_(b,bookings) {
  const index=inventory_(), dates=dates_(b.check_in,b.check_out);
  const used={};
  b.rooms.forEach(r=>used[r.room_type]=Object.fromEntries(dates.map(d=>[d,0])));
  bookings.forEach(function(row) {
    if (!row["Booking ID"] || row.Hotel!==b.hotel || ["Cancelled","Rejected"].indexOf(String(row.Status))>=0) return;
    let rooms, start, end;
    try {
      start=cellDate_(row["Check-in"]); end=cellDate_(row["Check-out"]); nights_(start,end);
      if (row["Rooms JSON"]) rooms=JSON.parse(row["Rooms JSON"]);
      else rooms=[{room_type:row["Room Type"],quantity:row["Number of Rooms"]||1}];
      if (!Array.isArray(rooms) || !rooms.length) throw Error("rooms");
      rooms.forEach(function(room) {
        if (!ROOM_OCCUPANCY[room.room_type]) throw Error("room type");
        const qty=int_(room.quantity,"reserved rooms",100000,false);
        if (used[room.room_type]) dates.forEach(d=>{if(d>=start && d<end) used[room.room_type][d]+=qty;});
      });
    } catch(e) {
      throw codedError_("INVENTORY_REVIEW","An existing request needs inventory review. Please contact the organizer.");
    }
  });
  return b.rooms.map(function(room) {
    let remaining=Infinity;
    dates.forEach(function(d) {
      const base=b.hotel+"|"+room.room_type+"|", specific=base+d, fallback=base+"*";
      const capacity=Object.prototype.hasOwnProperty.call(index,specific)?index[specific]:index[fallback];
      if (capacity===undefined) throw codedError_("INVENTORY_CONFIG","Room availability is not configured.");
      remaining=Math.min(remaining,Math.max(0,capacity-used[room.room_type][d]));
    });
    return {room_type:room.room_type,requested:room.quantity,remaining:remaining};
  });
}
function createBooking_(raw,invoice) {
  const saved=locked_(function() {
    const ctx=ensureSheet_(BOOKINGS_SHEET,BOOKING_HEADERS), rows=rows_(ctx);
    const existing=rows.find(r=>String(r["Booking ID"])===String(raw.booking_id));
    if (existing) {
      if (!existing["Request Hash"] || requestHash_(raw)!==existing["Request Hash"])
        throw codedError_("ID_CONFLICT","This request ID is already in use. Contact the organizer.");
      if (["Cancelled","Rejected"].indexOf(String(existing.Status))>=0) throw codedError_("CANCELLED","This request is no longer active.");
      return {booking:JSON.parse(existing["Booking JSON"]),row:existing};
    }
    const b=normalizeBooking_(raw);
    if (b.registration_type==="Individual" && passportExists_(rows,b.passport_number))
      throw codedError_("DUPLICATE_PASSPORT","This passport number is already registered.");
    availability_(b,rows).forEach(r=>{
      if (r.requested>r.remaining) throw codedError_("SOLD_OUT",r.room_type+": only "+r.remaining+" room(s) available for these dates.");
    });
    const data=bookingColumns_(b);
    data["Request Hash"]=requestHash_(raw);
    data["Booking JSON"]=JSON.stringify(b);
    data["Status"]="Received"; data["Document Status"]="Pending";
    data["Customer Email Sent"]=false;
    // This single durable row is also the inventory reservation. No separate decrement.
    writeRow_(ctx,0,data);
    SpreadsheetApp.flush();
    return {booking:b,row:data};
  });
  try { return processDocuments_(saved.booking,invoice); }
  catch(err) {
    // A document failure must never report a durable reservation as unsaved.
    return result_(saved.row,"Request saved; documents are pending.");
  }
}
function bookingColumns_(b) {
  return {"Booking ID":b.booking_id,"Booking Date":b.booking_date,"Registration Type":b.registration_type,
    "Guest Name":b.guest_name,"Federation Name":b.federation_name,"Date of Birth":b.date_of_birth,
    "Federation Country":b.federation_country||"","Federation Country Code":b.federation_country_code||"",
    "Passport Number":b.passport_number,"Nationality":b.nationality,"Nationality Code":b.nationality_code,
    "Phone":b.phone,"Email":b.email,"Hotel":b.hotel,"Meal Plan":b.meal_plan,
    "Room Type":b.rooms.map(r=>r.room_type).join(" + "),"Number of Rooms":b.room_count,"Guests":b.guests,
    "Check-in":b.check_in,"Check-out":b.check_out,"Nights":b.nights,"Rooms JSON":JSON.stringify(b.rooms),
    "Transportation JSON":JSON.stringify(b.transport_services),"Transportation Rate Version":b.transport_rate_version,
    "Room Total EUR":b.room_total_eur,"Transportation Total EUR":b.transport_total_eur,"Grand Total EUR":b.grand_total_eur,
    "Invoice No":b.invoice_no,"Invoice Verification Code":b.invoice_verification_code,"Schema Version":VERSION};
}
function processDocuments_(b,payload) {
  const lease=locked_(function() {
    const ctx=ensureSheet_(BOOKINGS_SHEET,BOOKING_HEADERS), row=find_(ctx,"Booking ID",b.booking_id);
    if (!row) throw codedError_("SERVER_ERROR","Saved request could not be located.");
    if (row["Invoice File ID"] && truthy_(row["Customer Email Sent"])) return {done:true,row:row};
    const started=Date.parse(String(row["Processing Started"]||""));
    if (row["Document Status"]==="Processing" && started && Date.now()-started<10*60*1000)
      return {done:true,row:row};
    writeRow_(ctx,row._row,{"Document Status":"Processing","Processing Started":new Date().toISOString()},row);
    SpreadsheetApp.flush(); return {done:false,row:row};
  });
  if (lease.done) {
    // Repair the secondary invoice log if a prior execution stopped after email.
    if (lease.row["Document Status"]!=="Processing") {
      try { locked_(function() { invoiceLog_(b,lease.row); }); } catch(e) { /* Main row remains saved. */ }
    }
    return result_(lease.row);
  }
  let row=lease.row, errors=[];
  try {
    if (!row["Invoice File ID"]) {
      const file=saveInvoicePdf_(payload,b);
      row=updateBooking_(b.booking_id,{"Invoice File ID":file.id,"Invoice URL":file.url,"Invoice SHA-256":file.sha256});
    }
    if (!truthy_(row["Customer Email Sent"])) {
      if (MailApp.getRemainingDailyQuota()<1) throw Error("Daily email quota reached; delivery will be retried.");
      const name=b.federation_name || b.guest_name;
      MailApp.sendEmail({
        to:b.email,subject:b.invoice_no+" - ITKF Booking Request",
        body:"Dear "+name+",\n\nYour booking request has been received successfully.\nRequest ID: "+b.booking_id+
          "\nSummary / invoice: "+b.invoice_no+"\nTotal: EUR "+b.grand_total_eur.toFixed(2)+
          "\n\nYour PDF is attached.",
        name:optionalProp_("COMPANY_NAME") || "Egyptian Traditional Karate Federation",
        attachments:[DriveApp.getFileById(row["Invoice File ID"]).getBlob().setName(b.invoice_no+".pdf")]
      });
      row=updateBooking_(b.booking_id,{"Customer Email Sent":true,"Email Sent At":new Date().toISOString()});
    }
  } catch(e) { errors.push(safeError_(e)); }
  row=updateBooking_(b.booking_id,{"Document Status":errors.length?"Pending":"Ready","Processing Started":"","Last Error":errors.join(" | ")});
  try { locked_(function() { invoiceLog_(b,row); }); } catch(e) { /* Booking row remains the authoritative record. */ }
  return result_(row);
}
function saveInvoicePdf_(payload,b) {
  const folder=DriveApp.getFolderById(optionalProp_("INVOICE_FOLDER_ID") || prop_("DRIVE_FOLDER_ID"));
  // Recover a file written immediately before a prior execution timed out.
  const matches=folder.getFilesByName(b.invoice_no+".pdf");
  if (matches.hasNext()) {
    const file=matches.next();
    return {id:file.getId(),url:file.getUrl(),sha256:digestHex_(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256,file.getBlob().getBytes()))};
  }
  if (!payload.base64 || payload.mime_type!=="application/pdf" || payload.filename!==b.invoice_no+".pdf")
    throw Error("PDF generation is pending. Retry PDF from the application.");
  if (!equal_(payload.verification_code,b.invoice_verification_code)) throw Error("PDF verification does not match this request.");
  const bytes=Utilities.base64Decode(payload.base64);
  const magic=bytes.slice(0,5).map(v=>String.fromCharCode((v+256)%256)).join("");
  if (!bytes.length || bytes.length>5*1024*1024 || magic!=="%PDF-") throw Error("Invalid PDF.");
  const digest=digestHex_(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256,bytes));
  if (!equal_(digest,payload.sha256)) throw Error("PDF integrity check failed.");
  const file=folder.createFile(Utilities.newBlob(bytes,"application/pdf",b.invoice_no+".pdf"));
  return {id:file.getId(),url:file.getUrl(),sha256:digest};
}
function updateBooking_(id,changes) {
  return locked_(function() {
    const ctx=ensureSheet_(BOOKINGS_SHEET,BOOKING_HEADERS), row=find_(ctx,"Booking ID",id);
    if (!row) throw Error("Request row is missing.");
    writeRow_(ctx,row._row,changes,row); SpreadsheetApp.flush();
    return Object.assign(row,changes);
  });
}
function invoiceLog_(b,row) {
  const ctx=ensureSheet_(INVOICES_SHEET,INVOICE_HEADERS), old=find_(ctx,"Invoice No",b.invoice_no);
  const data={"Invoice No":b.invoice_no,"Booking ID":b.booking_id,"Created At":b.booking_date,
    "Customer Name":b.federation_name||b.guest_name,"Customer Email":b.email,"Grand Total EUR":b.grand_total_eur,
    "Invoice File ID":row["Invoice File ID"]||"","Invoice URL":row["Invoice URL"]||"",
    "Invoice Verification Code":b.invoice_verification_code,"Invoice SHA-256":row["Invoice SHA-256"]||"",
    "Email Status":truthy_(row["Customer Email Sent"])?"Sent":"Pending","Last Error":row["Last Error"]||""};
  writeRow_(ctx,old?old._row:0,data,old);
}
function result_(row,message) {
  const out={ok:true,saved:true,booking_id:String(row["Booking ID"]),status:"Request received",
    invoice_no:row["Invoice No"],invoice_verification_code:row["Invoice Verification Code"],
    invoice_created:Boolean(row["Invoice File ID"]),invoice_url:row["Invoice URL"]||"",
    invoice_sha256:row["Invoice SHA-256"]||"",customer_email_sent:truthy_(row["Customer Email Sent"]),
    document_status:row["Document Status"],message:message||"Your request has been received successfully."};
  if (row["Invoice File ID"]) {
    try { out.invoice_base64=Utilities.base64Encode(DriveApp.getFileById(row["Invoice File ID"]).getBlob().getBytes()); }
    catch(e) { out.invoice_read_error="The PDF copy could not be retrieved."; }
  }
  return out;
}
function ensureSheet_(name,required) {
  const ss=SpreadsheetApp.openById(prop_("SPREADSHEET_ID"));
  const sheet=ss.getSheetByName(name)||ss.insertSheet(name);
  let headers=sheet.getLastColumn()?sheet.getRange(1,1,1,sheet.getLastColumn()).getValues()[0].map(String):[];
  const originalLength=headers.length;
  required.forEach(h=>{if(headers.indexOf(h)<0) headers.push(h);});
  if (sheet.getMaxColumns()<headers.length) sheet.insertColumnsAfter(sheet.getMaxColumns(),headers.length-sheet.getMaxColumns());
  if (headers.length!==originalLength) {
    sheet.getRange(1,1,1,headers.length).setValues([headers]);
    sheet.getRange(1,1,1,headers.length).setFontWeight("bold").setBackground("#C8102E").setFontColor("#FFFFFF");
    sheet.setFrozenRows(1);
  }
  return {sheet:sheet,headers:headers};
}
function rows_(ctx) {
  if (ctx.sheet.getLastRow()<2) return [];
  return ctx.sheet.getRange(2,1,ctx.sheet.getLastRow()-1,ctx.headers.length).getValues().map(function(values,index) {
    const row={_row:index+2}; ctx.headers.forEach((h,i)=>row[h]=values[i]); return row;
  });
}
function find_(ctx,header,value) { return rows_(ctx).find(r=>String(r[header])===String(value)); }
function writeRow_(ctx,row,data,old) {
  row=row||ctx.sheet.getLastRow()+1;
  if (row>ctx.sheet.getMaxRows()) ctx.sheet.insertRowsAfter(ctx.sheet.getMaxRows(),row-ctx.sheet.getMaxRows());
  const values=ctx.headers.map(h=>Object.prototype.hasOwnProperty.call(data,h)?data[h]:(old && old[h]!==undefined?old[h]:""));
  const range=ctx.sheet.getRange(row,1,1,ctx.headers.length);
  // Prevent formula injection and preserve passport/phone leading zeros BEFORE writing.
  range.setNumberFormat("@");
  range.setValues([values.map(v=>typeof v==="string" && /^[=+@\-]/.test(v)?"'"+v:v)]);
  return row;
}
function cellDate_(v) {
  if (v instanceof Date) return Utilities.formatDate(v,SpreadsheetApp.openById(prop_("SPREADSHEET_ID")).getSpreadsheetTimeZone(),"yyyy-MM-dd");
  return iso_(String(v));
}
function setupSheetsNow() {
  locked_(function() {
    ensureSheet_(BOOKINGS_SHEET,BOOKING_HEADERS);
    ensureSheet_(INVOICES_SHEET,INVOICE_HEADERS);
    const ctx=ensureSheet_(INVENTORY_SHEET,INVENTORY_HEADERS), rows=rows_(ctx);
    Object.keys(HOTEL_RATES_EUR).forEach(function(hotel) {
      const rooms={}; Object.values(HOTEL_RATES_EUR[hotel]).forEach(plan=>Object.keys(plan).forEach(room=>rooms[room]=true));
      Object.keys(rooms).forEach(function(room) {
        if (!rows.some(r=>r.Hotel===hotel && r["Room Type"]===room && r.Date==="*"))
          writeRow_(ctx,0,{"Hotel":hotel,"Room Type":room,"Date":"*","Capacity":10});
      });
    });
    SpreadsheetApp.flush();
  });
  console.log("Setup complete. Existing data and existing capacities were preserved.");
}
function diagnoseBackend() {
  prop_("BOOKING_API_TOKEN");
  const ss=SpreadsheetApp.openById(prop_("SPREADSHEET_ID"));
  DriveApp.getFolderById(optionalProp_("INVOICE_FOLDER_ID") || prop_("DRIVE_FOLDER_ID")).getName();
  console.log(JSON.stringify({version:VERSION,bookings_sheet_exists:Boolean(ss.getSheetByName(BOOKINGS_SHEET)),
    inventory_sheet_exists:Boolean(ss.getSheetByName(INVENTORY_SHEET)),email_quota_remaining:MailApp.getRemainingDailyQuota()}));
}
function retryPendingEmails() {
  const pending=rows_(ensureSheet_(BOOKINGS_SHEET,BOOKING_HEADERS)).filter(r=>r["Booking JSON"] &&
    r["Invoice File ID"] && ["Cancelled","Rejected"].indexOf(String(r.Status))<0 &&
    !truthy_(r["Customer Email Sent"])).slice(0,20);
  for (const row of pending) {
    if (MailApp.getRemainingDailyQuota()<1) break;
    try { processDocuments_(JSON.parse(row["Booking JSON"]),{}); } catch(e) { /* Retry on next trigger. */ }
  }
}
function installRetryTrigger() {
  if (!ScriptApp.getProjectTriggers().some(t=>t.getHandlerFunction()==="retryPendingEmails"))
    ScriptApp.newTrigger("retryPendingEmails").timeBased().everyMinutes(5).create();
}
function verificationCode_(b) {
  const message=[b.invoice_no,b.booking_id,b.email,Number(b.grand_total_eur).toFixed(2)].join("\n");
  return digestHex_(Utilities.computeHmacSha256Signature(message,prop_("BOOKING_API_TOKEN"),Utilities.Charset.UTF_8))
    .toUpperCase().slice(0,16).match(/.{4}/g).join("-");
}
function sha_(value) { return digestHex_(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256,value,Utilities.Charset.UTF_8)); }
function digestHex_(bytes) { return bytes.map(v=>((Number(v)+256)%256).toString(16).padStart(2,"0")).join(""); }
function equal_(a,b) {
  a=String(a||""); b=String(b||""); let diff=a.length^b.length;
  for(let i=0;i<Math.max(a.length,b.length);i++) diff|=(a.charCodeAt(i)||0)^(b.charCodeAt(i)||0);
  return diff===0;
}
function money_(v) { return Math.round((Number(v)+Number.EPSILON)*100)/100; }
function truthy_(v) { return v===true || String(v).toLowerCase()==="true"; }
function optionalProp_(name) { return PropertiesService.getScriptProperties().getProperty(name)||""; }
function prop_(name) { const v=optionalProp_(name); if(!v) throw codedError_("MISSING_PROPERTY","Missing Script Property: "+name); return v; }
function codedError_(code,msg) { const err=Error(msg); err.code=code; return err; }
function safeError_(err) { return String(err && err.message || "Service error.").slice(0,300); }
function json_(obj) { return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON); }
