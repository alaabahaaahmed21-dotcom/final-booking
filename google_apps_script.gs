/**
 * ITKF request backend v5.5.1. Existing Bookings/Invoices rows are preserved.
 * Properties: SPREADSHEET_ID, BOOKING_API_TOKEN, INVOICE_FOLDER_ID
 * (DRIVE_FOLDER_ID is supported as a fallback invoice folder).
 * Deploy: Execute as Me; Anyone. The token is required for every POST action.
 */
const VERSION = "2026-09-01-v5.5.1";
let SPREADSHEET_CACHE_ = null;
const BOOKINGS_SHEET = "Bookings", INVOICES_SHEET = "Invoices", INVENTORY_SHEET = "Room Inventory";
const BOOKING_HEADERS = [
  "Booking ID","Booking Date","Registration Type","Guest Name","Federation Name","Date of Birth",
  "Passport Number","Nationality","Nationality Code","Phone","Email","Hotel","Meal Plan",
  "Room Type","Number of Rooms","Guests","Check-in","Check-out","Nights","Rooms JSON",
  "Transportation JSON","Transportation Rate Version","Room Total EUR","Transportation Total EUR",
  "Grand Total EUR","Invoice No","Invoice Verification Code","Invoice File ID","Invoice URL",
  "Invoice SHA-256","Customer Email Sent","Email Sent At","Status","Document Status",
  "Processing Started","Last Error","Request Hash","Booking JSON","Schema Version",
  "Federation Country","Federation Country Code","Revision","Updated At","Last Edit ID",
  "Edit Code Hash","Edit Code Expires","Edit Code Attempts","Edit Code Sent At",
  "Edit Code Window","Edit Code Sends","Edit Grant Hash","Edit Grant Expires","Document Lease"
];
const INVOICE_HEADERS = [
  "Invoice No","Booking ID","Created At","Customer Name","Customer Email","Grand Total EUR",
  "Invoice File ID","Invoice URL","Invoice Verification Code","Invoice SHA-256","Email Status","Last Error",
  "Revision","Updated At"
];
const HISTORY_SHEET = "Request History";
const HISTORY_HEADERS = ["Booking ID","Revision","Archived At","Booking JSON","Status"];
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
// Current hotel catalogue and official EUR rate per room/night.
const HOTEL_RATES_EUR = {
  "Tiba Rose El Golf": {
    "Breakfast": {"Single": 80, "Double": 50, "Triple": 45},
    "Half Board": {"Single": 95, "Double": 60, "Triple": 50}
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
  "Hotel Engineering Authority House": {"Breakfast": {"Single": 70, "Double": 45}},
  "Royal Marshal Hotel": {"Breakfast": {"Single": 47.5, "Double": 65}}
};

// Official room allotment supplied by the organizer. Capacity is per night.
// Remaining stock is derived from overlapping active booking rows, so checkout,
// cancellation and amendments automatically release/recalculate rooms.
const ROOM_INVENTORY_CAPACITY = {
  "Tiba Rose El Golf": {"Single":4,"Double":4,"Triple":4},
  "Baron Hotel Cairo": {"Single":10,"Double":10,"Triple":10,"Quadruple":10},
  "Armor House Hotel, Cairo": {"Single":7,"Double":8,"Suite (2 rooms / 4 persons)":25},
  "Hotel El Forsan": {"Single":10,"Double":50,"Triple":0},
  "Hotel Jewel Elnasr": {"Single":19,"Double":47,"Triple":5,"Quadruple":4},
  "Hotel Infantry House": {"Single":25,"Double":25,"Quadruple":20},
  "Hotel Engineering Authority House": {"Single":6,"Double":60,"Quadruple":40},
  "Royal Marshal Hotel": {"Single":10,"Double":30}
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
      // Display-only availability must never compete with final booking writes
      // for the global script lock. The final create/amend call still performs
      // a fresh availability check while holding the lock.
      const b = accommodation_(req.booking || {});
      let rows=rows_(ensureSheet_(BOOKINGS_SHEET,BOOKING_HEADERS));
      if (req.edit_token) {
        const row=authorizedEdit_(req.booking.booking_id,req.edit_token,rows);
        rows=rows.filter(r=>r._row!==row._row);
      }
      return json_({ok:true,availability:availability_(b,rows)});
    }
    if (req.action === "check_all_availability") {
      const checkIn=iso_(req.check_in), checkOut=iso_(req.check_out);
      nights_(checkIn,checkOut);
      const cacheKey="avail-v55|"+checkIn+"|"+checkOut;
      const cache=CacheService.getScriptCache();
      if (!req.edit_token) {
        const cached=cache.get(cacheKey);
        if (cached) return json_(JSON.parse(cached));
      }
      let rows=rows_(ensureSheet_(BOOKINGS_SHEET,BOOKING_HEADERS));
      if (req.edit_token) {
        const row=authorizedEdit_(req.booking_id,req.edit_token,rows);
        rows=rows.filter(r=>r._row!==row._row);
      }
      const inventory=inventory_(), byHotel={};
      Object.keys(ROOM_INVENTORY_CAPACITY).forEach(function(hotel) {
        const rooms=Object.keys(ROOM_INVENTORY_CAPACITY[hotel]);
        const probe={hotel:hotel,check_in:checkIn,check_out:checkOut,
          rooms:rooms.map(room=>({room_type:room,quantity:1}))};
        byHotel[hotel]={};
        availability_(probe,rows,inventory).forEach(function(item) {
          byHotel[hotel][item.room_type]=item.remaining;
        });
      });
      const response={ok:true,availability_by_hotel:byHotel};
      if (!req.edit_token) cache.put(cacheKey,JSON.stringify(response),15);
      return json_(response);
    }
    if (req.action === "create_booking") return json_(createBooking_(req.booking || {}, req.invoice || {}));
    if (req.action === "booking_status") {
      const id=requestId_(req.booking_id);
      const row=find_(ensureSheet_(BOOKINGS_SHEET,BOOKING_HEADERS),"Booking ID",id);
      if (!row) return json_({ok:true,saved:false,exists:false});
      if (req.expected_revision && Number(row.Revision||1)!==Number(req.expected_revision))
        return json_({ok:true,saved:false,exists:true,revision:Number(row.Revision||1)});
      if ((req.invoice_no && String(row["Invoice No"])!==String(req.invoice_no)) ||
          (req.email && String(row.Email).trim().toLowerCase()!==String(req.email).trim().toLowerCase()))
        return json_({ok:true,saved:false,exists:true});
      return json_(Object.assign(result_(row,"",false),{exists:true}));
    }
    if (req.action === "request_edit_code") return json_(requestEditCode_(req.booking_id,req.email));
    if (req.action === "verify_edit_code") return json_(verifyEditCode_(req.booking_id,req.email,req.code));
    if (req.action === "load_request") return json_(loadRequest_(req.booking_id,req.edit_token));
    if (req.action === "amend_booking") return json_(amendBooking_(req.booking || {},req.invoice || {},req));
    if (req.action === "process_documents") {
      const id=requestId_(req.booking_id);
      const row=find_(ensureSheet_(BOOKINGS_SHEET,BOOKING_HEADERS),"Booking ID",id);
      if (!row || !row["Booking JSON"]) throw codedError_("SERVER_ERROR","Saved request could not be located.");
      return json_(processDocuments_(JSON.parse(row["Booking JSON"]),req.invoice || {},
        truthy_(req.force_check),truthy_(req.defer_email)));
    }
    if (req.action === "retry_documents") {
      const saved=loadRequest_(req.booking_id,req.edit_token);
      return json_(processDocuments_(saved.booking,req.invoice || {},true,false));
    }
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
  if (!lock.tryLock(7000)) throw codedError_("BUSY","The service is busy. Retry this same request.");
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
  // Federation phone is optional; an entered number must still be valid.
  // Individual registration continues to require a phone number.
  if ((type==="Individual" || phone!=="") && !/^\+[1-9]\d{6,14}$/.test(phone))
    throw codedError_("VALIDATION_ERROR","Invalid international phone number.");
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
  b.revision=raw.revision===undefined?1:int_(raw.revision,"revision",100000,false);
  b.updated_at=String(raw.updated_at || b.booking_date);
  if (!isFinite(Date.parse(b.updated_at))) throw codedError_("VALIDATION_ERROR","Invalid update date.");
  b.invoice_no=invoiceNumber_(b.booking_id,b.revision);
  b.invoice_verification_code=verificationCode_(b);
  b.status="Request received";
  if (JSON.stringify(b).length>45000) throw codedError_("VALIDATION_ERROR","This request has too many service details. Split it into smaller requests.");
  return b;
}
function requestHash_(b,ignoreOrder) {
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
  if (ignoreOrder) {
    const compare=(a,b)=>JSON.stringify(sorted_(a)).localeCompare(JSON.stringify(sorted_(b)));
    data.rooms.sort(compare); data.transport_services.sort(compare);
  }
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
function availability_(b,bookings,inventoryIndex) {
  const index=inventoryIndex || inventory_(), dates=dates_(b.check_in,b.check_out);
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
    if (b.revision!==1) throw codedError_("VALIDATION_ERROR","A new request must start at revision 1.");
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
  // v5.5 fast completion: the current Streamlit client sends no PDF in this
  // first call, so the durable reservation returns immediately. Legacy callers
  // that still supply a PDF keep the previous all-in-one behavior.
  if (invoice && invoice.base64) {
    try { return processDocuments_(saved.booking,invoice); }
    catch(err) { return result_(saved.row,"Request saved; documents are pending.",false); }
  }
  return result_(saved.row,"Request saved; PDF/email processing is pending.",false);
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
    "Invoice No":b.invoice_no,"Invoice Verification Code":b.invoice_verification_code,"Schema Version":VERSION,
    "Revision":b.revision||1,"Updated At":b.updated_at||b.booking_date};
}
function invoiceNumber_(id,revision) {
  return "INV-"+id.replace(/^ITKF-/,"")+(revision>1?"-R"+revision:"");
}
function editable_(row) {
  if (["Received","Request received","Updated"].indexOf(String(row.Status))<0)
    throw codedError_("EDIT_CLOSED","This request cannot be edited online. Please contact the organizer.");
  if (!row["Booking JSON"]) throw codedError_("EDIT_CLOSED","Please contact the organizer to update this older request.");
}
function requestId_(value) {
  const id=String(value||"").trim().toUpperCase();
  if (!/^ITKF-\d{8}-[A-F0-9]{12}$/.test(id)) throw codedError_("VALIDATION_ERROR","Enter the complete Request ID from your email or PDF.");
  return id;
}
function authorizedEdit_(id,token,rows) {
  const row=rows.find(r=>String(r["Booking ID"])===requestId_(id));
  if (!row || !token || String(token).length>200 ||
      !Number.isFinite(Date.parse(row["Edit Grant Expires"]||"")) || Date.parse(row["Edit Grant Expires"])<=Date.now() ||
      !equal_(sha_(String(token)),row["Edit Grant Hash"]))
    throw codedError_("EDIT_AUTH","Your edit session is invalid or expired. Request a new email code.");
  return row;
}
function requestEditCode_(id,email) {
  id=requestId_(id); email=String(email||"").trim().toLowerCase();
  if (email.length>254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))
    throw codedError_("VALIDATION_ERROR","Enter your registered email address.");
  const generic={ok:true,message:"If the Request ID and registered email match, a verification code will be emailed. Check Spam too. Wait at least 60 seconds before requesting another code."};
  return locked_(function() {
    const ctx=ensureSheet_(BOOKINGS_SHEET,BOOKING_HEADERS),row=find_(ctx,"Booking ID",id),now=Date.now();
    // A request number alone never reveals whether a person is registered.
    if (!row || String(row.Email).trim().toLowerCase()!==email || !row["Booking JSON"]) return generic;
    const last=Date.parse(row["Edit Code Sent At"]||"");
    const window=Date.parse(row["Edit Code Window"]||"");
    const recent=Number.isFinite(window) && now-window<60*60*1000;
    if ((Number.isFinite(last) && now-last<60000) || (recent && Number(row["Edit Code Sends"])>=5)) return generic;
    if (MailApp.getRemainingDailyQuota()<1) throw codedError_("EMAIL_QUOTA","Email is temporarily unavailable. Please try later or contact the organizer.");
    // UUID entropy is HMAC-mixed; never use Math.random for authentication.
    const entropy=digestHex_(Utilities.computeHmacSha256Signature(Utilities.getUuid()+Utilities.getUuid(),prop_("BOOKING_API_TOKEN"),Utilities.Charset.UTF_8));
    const code=String(parseInt(entropy.slice(0,12),16)%100000000).padStart(8,"0");
    writeRow_(ctx,row._row,{"Edit Code Hash":sha_(id+"|"+code),"Edit Code Expires":new Date(now+10*60000).toISOString(),
      "Edit Code Attempts":0,"Edit Code Sent At":new Date(now).toISOString(),
      "Edit Code Window":recent?row["Edit Code Window"]:new Date(now).toISOString(),
      "Edit Code Sends":recent?Number(row["Edit Code Sends"]||0)+1:1},row);
    SpreadsheetApp.flush();
    MailApp.sendEmail({to:row.Email,subject:"ITKF request verification code",
      body:"Your verification code is: "+code+"\nRequest ID: "+id+
        "\nThe code expires in 10 minutes. Do not share it. If you did not request it, ignore this email.",
      name:optionalProp_("COMPANY_NAME")||"Egyptian Traditional Karate Federation"});
    return generic;
  });
}
function verifyEditCode_(id,email,code) {
  id=requestId_(id); email=String(email||"").trim().toLowerCase(); code=String(code||"").trim();
  return locked_(function() {
    const ctx=ensureSheet_(BOOKINGS_SHEET,BOOKING_HEADERS),row=find_(ctx,"Booking ID",id);
    const invalid=()=>codedError_("EDIT_CODE","The code is incorrect or expired. Request a new code if needed.");
    if (!row || String(row.Email).trim().toLowerCase()!==email || !row["Edit Code Hash"] ||
        !Number.isFinite(Date.parse(row["Edit Code Expires"]||"")) || Date.parse(row["Edit Code Expires"])<=Date.now() ||
        Number(row["Edit Code Attempts"]||0)>=5) throw invalid();
    if (!/^\d{8}$/.test(code) || !equal_(sha_(id+"|"+code),row["Edit Code Hash"])) {
      writeRow_(ctx,row._row,{"Edit Code Attempts":Number(row["Edit Code Attempts"]||0)+1},row);
      SpreadsheetApp.flush(); throw invalid();
    }
    const token=Utilities.getUuid().replace(/-/g,"")+Utilities.getUuid().replace(/-/g,"");
    const expiry=new Date(Date.now()+60*60000).toISOString();
    writeRow_(ctx,row._row,{"Edit Grant Hash":sha_(token),"Edit Grant Expires":expiry,
      "Edit Code Hash":"","Edit Code Expires":"","Edit Code Attempts":0},row);
    SpreadsheetApp.flush();
    return {ok:true,edit_token:token,expires_at:expiry};
  });
}
function loadRequest_(id,token) {
  const row=authorizedEdit_(id,token,rows_(ensureSheet_(BOOKINGS_SHEET,BOOKING_HEADERS)));
  const b=JSON.parse(row["Booking JSON"]);
  b.revision=Number(row.Revision||b.revision||1);
  b.updated_at=row["Updated At"]||b.updated_at||b.booking_date;
  const result=result_(row);
  return Object.assign(result,{booking:b,editable:["Received","Request received","Updated"].indexOf(String(row.Status))>=0});
}
function archiveRequest_(row) {
  const ctx=ensureSheet_(HISTORY_SHEET,HISTORY_HEADERS),revision=Number(row.Revision||1);
  if (!rows_(ctx).some(r=>r["Booking ID"]===row["Booking ID"] && Number(r.Revision)===revision))
    writeRow_(ctx,0,{"Booking ID":row["Booking ID"],"Revision":revision,"Archived At":new Date().toISOString(),
      "Booking JSON":row["Booking JSON"],"Status":row.Status});
  invoiceLog_(JSON.parse(row["Booking JSON"]),row);
}
function amendBooking_(raw,invoice,req) {
  const saved=locked_(function() {
    const ctx=ensureSheet_(BOOKINGS_SHEET,BOOKING_HEADERS),rows=rows_(ctx);
    const row=authorizedEdit_(raw.booking_id,req.edit_token,rows);
    editable_(row);
    const operation=String(req.edit_operation_id||"");
    if (!/^[a-f0-9]{32}$/.test(operation)) throw codedError_("VALIDATION_ERROR","Invalid edit operation.");
    // A lost response can be retried without another revision, room hold or email.
    if (row["Last Edit ID"]===operation) {
      if (!equal_(row["Request Hash"],requestHash_(raw))) throw codedError_("ID_CONFLICT","This edit attempt already saved different details. Reload the request.");
      return {booking:JSON.parse(row["Booking JSON"]),row:row};
    }
    const revision=Number(row.Revision||1);
    if (int_(req.expected_revision,"revision",100000,false)!==revision)
      throw codedError_("EDIT_CONFLICT","This request was updated elsewhere. Reload it before making further changes.");
    const started=Date.parse(row["Processing Started"]||"");
    if (row["Document Status"]==="Processing" && started && Date.now()-started<10*60000)
      throw codedError_("BUSY","The current PDF/email is being processed. Retry this same edit shortly.");
    const old=JSON.parse(row["Booking JSON"]);
    if (raw.registration_type!==old.registration_type || String(raw.email||"").trim().toLowerCase()!==String(old.email).trim().toLowerCase())
      throw codedError_("EDIT_IDENTITY","Registration type and registered email cannot be changed online. Contact the organizer.");
    if (requestHash_(raw,true)===requestHash_(old,true))
      throw codedError_("NO_CHANGES","No details changed. Use View / download request to retrieve or retry the existing PDF.");
    const b=normalizeBooking_(Object.assign({},raw,{booking_id:old.booking_id,booking_date:old.booking_date,
      email:old.email,revision:revision+1}));
    const others=rows.filter(r=>r._row!==row._row);
    if (b.registration_type==="Individual" && passportExists_(others,b.passport_number))
      throw codedError_("DUPLICATE_PASSPORT","This passport number is already registered on another request.");
    availability_(b,others).forEach(r=>{
      if(r.requested>r.remaining) throw codedError_("SOLD_OUT",r.room_type+": only "+r.remaining+" room(s) available for these dates. Your existing request was not changed.");
    });
    archiveRequest_(row);
    const changes=Object.assign(bookingColumns_(b),{"Booking JSON":JSON.stringify(b),"Request Hash":requestHash_(b),
      "Last Edit ID":operation,"Status":row.Status,"Document Status":"Pending","Processing Started":"","Document Lease":"",
      "Invoice File ID":"","Invoice URL":"","Invoice SHA-256":"","Customer Email Sent":false,"Email Sent At":"","Last Error":""});
    // Replace the existing row atomically under the inventory lock; never append a new booking.
    writeRow_(ctx,row._row,changes,row); SpreadsheetApp.flush();
    return {booking:b,row:Object.assign(row,changes)};
  });
  if (invoice && invoice.base64) {
    try { return processDocuments_(saved.booking,invoice); }
    catch(e) { return result_(saved.row,"The changes were saved. PDF/email processing is pending.",false); }
  }
  return result_(saved.row,"The changes were saved. PDF/email processing is pending.",false);
}
function processDocuments_(b,payload,forceCheck,deferEmail) {
  const lease=locked_(function() {
    const ctx=ensureSheet_(BOOKINGS_SHEET,BOOKING_HEADERS), row=find_(ctx,"Booking ID",b.booking_id);
    if (!row) throw codedError_("SERVER_ERROR","Saved request could not be located.");
    if (["Cancelled","Rejected"].indexOf(String(row.Status))>=0) throw codedError_("EDIT_CLOSED","This request is no longer active.");
    if (row["Invoice No"]!==b.invoice_no) throw codedError_("EDIT_CONFLICT","A newer request revision exists. Reload the request.");
    const started=Date.parse(String(row["Processing Started"]||""));
    if (row["Document Status"]==="Processing" && started && Date.now()-started<10*60*1000)
      return {done:true,row:row};
    // Normal completion avoids another Drive download. Explicit retry from the
    // request manager can force a storage check so a deleted/corrupt copy is
    // repairable without creating another booking revision.
    if (row["Invoice File ID"] && truthy_(row["Customer Email Sent"])) {
      if (!forceCheck) return {done:true,row:row};
      try {
        const bytes=DriveApp.getFileById(row["Invoice File ID"]).getBlob().getBytes();
        const digest=digestHex_(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256,bytes));
        if (!row["Invoice SHA-256"] || !equal_(digest,row["Invoice SHA-256"])) throw Error("PDF integrity mismatch");
      } catch(e) {
        Object.assign(row,{"Invoice File ID":"","Invoice URL":"","Invoice SHA-256":"",
          "Customer Email Sent":false,"Email Sent At":""});
      }
      if (row["Invoice File ID"] && truthy_(row["Customer Email Sent"])) return {done:true,row:row};
    }
    const token=Utilities.getUuid();
    const processing={"Document Status":"Processing","Processing Started":new Date().toISOString(),"Document Lease":token,
      "Invoice File ID":row["Invoice File ID"]||"","Invoice URL":row["Invoice URL"]||"","Invoice SHA-256":row["Invoice SHA-256"]||"",
      "Customer Email Sent":truthy_(row["Customer Email Sent"]),"Email Sent At":row["Email Sent At"]||""};
    writeRow_(ctx,row._row,processing,row);
    SpreadsheetApp.flush();
    return {done:false,row:Object.assign(row,processing),token:token};
  });
  if (lease.done) {
    if (lease.row["Document Status"]!=="Processing") {
      try { locked_(function() { invoiceLog_(b,lease.row); }); } catch(e) { /* Main row remains saved. */ }
    }
    return result_(lease.row,"",false);
  }

  let row=lease.row, errors=[], changes={}, attachment=null;
  try {
    if (!row["Invoice File ID"]) {
      const file=saveInvoicePdf_(payload,b);
      changes["Invoice File ID"]=file.id;
      changes["Invoice URL"]=file.url;
      changes["Invoice SHA-256"]=file.sha256;
      // New PDFs are emailed from the same verified blob that was written to
      // Drive; do not download that file again immediately after uploading it.
      attachment=file.blob;
      Object.assign(row,changes);
    }
    // Normal completion queues email so the user is not held on the success page.
    // Make the queue self-healing: ensure the retry trigger exists automatically.
    // If trigger creation is unavailable for any reason, fall back to immediate
    // delivery rather than leaving a saved request permanently without email.
    if (!truthy_(row["Customer Email Sent"]) && deferEmail) {
      try { ensureRetryTrigger_(); } catch(e) { deferEmail=false; }
    }
    if (!truthy_(row["Customer Email Sent"]) && !deferEmail) {
      if (MailApp.getRemainingDailyQuota()<1) throw Error("Daily email quota reached; delivery will be retried.");
      const name=b.federation_name || b.guest_name;
      if (!attachment) {
        attachment=DriveApp.getFileById(row["Invoice File ID"]).getBlob();
      }
      // Preserve the PDF exactly as generated, including its encryption/protection.
      // Validate the raw bytes first, then wrap those SAME bytes in a clean
      // application/pdf attachment. No PDF parsing, conversion or re-generation
      // happens here, so password/encryption settings remain untouched.
      const attachmentBytes=attachment.getBytes();
      const attachmentMagic=attachmentBytes.slice(0,5).map(v=>String.fromCharCode((v+256)%256)).join("");
      if (!attachmentBytes.length || attachmentBytes.length>5*1024*1024 || attachmentMagic!=="%PDF-")
        throw Error("Stored PDF is invalid. Retry PDF/email from the application.");
      const attachmentSha=digestHex_(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256,attachmentBytes));
      if (!row["Invoice SHA-256"] || !equal_(attachmentSha,row["Invoice SHA-256"]))
        throw Error("Stored PDF integrity check failed. Retry PDF/email from the application.");
      const mailAttachment=Utilities.newBlob(attachmentBytes,"application/pdf",b.invoice_no+".pdf");
      MailApp.sendEmail({
        to:b.email,subject:b.invoice_no+" - ITKF Booking Request",
        body:"Dear "+name+",\n\nYour booking request "+((b.revision||1)>1?"has been updated.":"has been received successfully.")+"\nRequest ID: "+b.booking_id+
          "\nSummary / invoice: "+b.invoice_no+"\nTotal: EUR "+b.grand_total_eur.toFixed(2)+
          "\nRevision: "+(b.revision||1)+"\n\nYour PDF is attached. This is a request summary, not payment or final hotel confirmation."+
          "\nTo view or amend the same request, open the application, choose View / edit existing request, and enter this Request ID and your registered email."+
          "\nYou will receive a verification code. Do not submit a new request for the same booking."+
          (optionalProp_("PUBLIC_APP_URL")?"\nApplication: "+optionalProp_("PUBLIC_APP_URL"):""),
        name:optionalProp_("COMPANY_NAME") || "Egyptian Traditional Karate Federation",
        attachments:[mailAttachment]
      });
      changes["Customer Email Sent"]=true;
      changes["Email Sent At"]=new Date().toISOString();
    }
  } catch(e) { errors.push(safeError_(e)); }

  Object.assign(changes,{"Document Status":errors.length?"Pending":"Ready","Processing Started":"","Document Lease":"","Last Error":errors.join(" | ")});
  row=updateDocument_(b,lease.token,changes);
  try { locked_(function() { invoiceLog_(b,row); }); } catch(e) { /* Booking row remains the authoritative record. */ }
  // The Streamlit client already has the exact generated PDF bytes. Returning
  // them again from Drive would add a full extra download to the submit path.
  return result_(row,"",false);
}
function saveInvoicePdf_(payload,b) {
  const folder=DriveApp.getFolderById(optionalProp_("INVOICE_FOLDER_ID") || prop_("DRIVE_FOLDER_ID"));

  // Validate the PDF supplied by the application first. These are the exact
  // protected/encrypted PDF bytes generated by ReportLab; Apps Script must not
  // alter them.
  let payloadBytes=null, payloadDigest="";
  if (payload && payload.base64) {
    if (payload.mime_type!=="application/pdf" || payload.filename!==b.invoice_no+".pdf")
      throw Error("Invalid PDF metadata.");
    if (!equal_(payload.verification_code,b.invoice_verification_code))
      throw Error("PDF verification does not match this request.");
    payloadBytes=Utilities.base64Decode(payload.base64);
    const payloadMagic=payloadBytes.slice(0,5).map(v=>String.fromCharCode((v+256)%256)).join("");
    if (!payloadBytes.length || payloadBytes.length>5*1024*1024 || payloadMagic!=="%PDF-")
      throw Error("Invalid PDF.");
    payloadDigest=digestHex_(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256,payloadBytes));
    if (!payload.sha256 || !equal_(payloadDigest,payload.sha256))
      throw Error("PDF integrity check failed.");
  }

  // Recover a file written immediately before a prior execution timed out,
  // BUT only when its bytes are verified. Previously any same-name Drive file
  // could be reused, which could resend a partial/stale PDF from an interrupted
  // attempt.
  const matches=folder.getFilesByName(b.invoice_no+".pdf");
  while (matches.hasNext()) {
    const file=matches.next();
    try {
      const storedBytes=file.getBlob().getBytes();
      const storedMagic=storedBytes.slice(0,5).map(v=>String.fromCharCode((v+256)%256)).join("");
      const storedDigest=digestHex_(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256,storedBytes));
      const structurallyValid=storedBytes.length>0 && storedBytes.length<=5*1024*1024 && storedMagic==="%PDF-";
      const matchesPayload=!payloadDigest || equal_(storedDigest,payloadDigest);
      if (structurallyValid && matchesPayload) {
        const verifiedBlob=Utilities.newBlob(storedBytes,"application/pdf",b.invoice_no+".pdf");
        return {id:file.getId(),url:file.getUrl(),sha256:storedDigest,blob:verifiedBlob};
      }
      // Do not reuse a corrupt/stale same-name file. Keep it out of the active
      // path and recreate the invoice from the verified application bytes.
      file.setTrashed(true);
    } catch(e) {
      try { file.setTrashed(true); } catch(ignore) {}
    }
  }

  if (!payloadBytes)
    throw Error("PDF generation is pending. Retry PDF from the application.");

  // Write the exact original bytes; encryption/protection is preserved.
  const blob=Utilities.newBlob(payloadBytes,"application/pdf",b.invoice_no+".pdf");
  const file=folder.createFile(blob);

  // Read back once after creation and verify byte-for-byte integrity before the
  // file is eligible for email delivery. This is intentionally only on a NEW
  // PDF, not an extra read on every successful submission.
  const storedBytes=file.getBlob().getBytes();
  const storedDigest=digestHex_(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256,storedBytes));
  if (!equal_(storedDigest,payloadDigest)) {
    file.setTrashed(true);
    throw Error("Drive PDF integrity check failed. Retry PDF/email from the application.");
  }
  const verifiedBlob=Utilities.newBlob(storedBytes,"application/pdf",b.invoice_no+".pdf");
  return {id:file.getId(),url:file.getUrl(),sha256:storedDigest,blob:verifiedBlob};
}
function updateBooking_(id,changes) {
  return locked_(function() {
    const ctx=ensureSheet_(BOOKINGS_SHEET,BOOKING_HEADERS), row=find_(ctx,"Booking ID",id);
    if (!row) throw Error("Request row is missing.");
    writeRow_(ctx,row._row,changes,row); SpreadsheetApp.flush();
    return Object.assign(row,changes);
  });
}
function updateDocument_(b,token,changes) {
  return locked_(function() {
    const ctx=ensureSheet_(BOOKINGS_SHEET,BOOKING_HEADERS),row=find_(ctx,"Booking ID",b.booking_id);
    if (!row || row["Invoice No"]!==b.invoice_no || row["Document Lease"]!==token)
      throw codedError_("EDIT_CONFLICT","Document processing was superseded. Reload the request.");
    writeRow_(ctx,row._row,changes,row); SpreadsheetApp.flush(); return Object.assign(row,changes);
  });
}
function invoiceLog_(b,row) {
  const ctx=ensureSheet_(INVOICES_SHEET,INVOICE_HEADERS), old=find_(ctx,"Invoice No",b.invoice_no);
  const data={"Invoice No":b.invoice_no,"Booking ID":b.booking_id,"Created At":b.booking_date,
    "Customer Name":b.federation_name||b.guest_name,"Customer Email":b.email,"Grand Total EUR":b.grand_total_eur,
    "Invoice File ID":row["Invoice File ID"]||"","Invoice URL":row["Invoice URL"]||"",
    "Invoice Verification Code":b.invoice_verification_code,"Invoice SHA-256":row["Invoice SHA-256"]||"",
    "Email Status":truthy_(row["Customer Email Sent"])?"Sent":"Pending","Last Error":row["Last Error"]||"",
    "Revision":b.revision||1,"Updated At":b.updated_at||b.booking_date};
  writeRow_(ctx,old?old._row:0,data,old);
}
function result_(row,message,includePdf) {
  const out={ok:true,saved:true,booking_id:String(row["Booking ID"]),status:row.Status,
    revision:Number(row.Revision||1),updated_at:row["Updated At"]||row["Booking Date"],
    invoice_no:row["Invoice No"],invoice_verification_code:row["Invoice Verification Code"],
    invoice_created:Boolean(row["Invoice File ID"]),invoice_url:row["Invoice URL"]||"",
    invoice_sha256:row["Invoice SHA-256"]||"",customer_email_sent:truthy_(row["Customer Email Sent"]),
    document_status:row["Document Status"],message:message||"Your request has been received successfully."};
  if (includePdf!==false && row["Invoice File ID"]) {
    try { out.invoice_base64=Utilities.base64Encode(DriveApp.getFileById(row["Invoice File ID"]).getBlob().getBytes()); }
    catch(e) { out.invoice_read_error="The PDF copy could not be retrieved."; }
  }
  if (row["Booking JSON"]) out.booking=JSON.parse(row["Booking JSON"]);
  return out;
}
function spreadsheet_() {
  if (!SPREADSHEET_CACHE_) SPREADSHEET_CACHE_=SpreadsheetApp.openById(prop_("SPREADSHEET_ID"));
  return SPREADSHEET_CACHE_;
}
function ensureSheet_(name,required) {
  const ss=spreadsheet_();
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
function find_(ctx,header,value) {
  const column=ctx.headers.indexOf(header)+1;
  if (column<1 || ctx.sheet.getLastRow()<2) return undefined;
  const match=ctx.sheet.getRange(2,column,ctx.sheet.getLastRow()-1,1)
    .createTextFinder(String(value)).matchEntireCell(true).findNext();
  if (!match) return undefined;
  const values=ctx.sheet.getRange(match.getRow(),1,1,ctx.headers.length).getValues()[0];
  const row={_row:match.getRow()}; ctx.headers.forEach((h,i)=>row[h]=values[i]); return row;
}
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
  if (v instanceof Date) return Utilities.formatDate(v,spreadsheet_().getSpreadsheetTimeZone(),"yyyy-MM-dd");
  return iso_(String(v));
}
function syncOfficialInventory_(ctx) {
  const existing=rows_(ctx);
  Object.keys(ROOM_INVENTORY_CAPACITY).forEach(function(hotel) {
    Object.keys(ROOM_INVENTORY_CAPACITY[hotel]).forEach(function(room) {
      const capacity=ROOM_INVENTORY_CAPACITY[hotel][room];
      const row=existing.find(r=>r.Hotel===hotel && r["Room Type"]===room && r.Date==="*");
      if (row) writeRow_(ctx,row._row,{"Hotel":hotel,"Room Type":room,"Date":"*","Capacity":capacity},row);
      else writeRow_(ctx,0,{"Hotel":hotel,"Room Type":room,"Date":"*","Capacity":capacity});
    });
  });
}
function setupSheetsNow() {
  locked_(function() {
    ensureSheet_(BOOKINGS_SHEET,BOOKING_HEADERS);
    ensureSheet_(INVOICES_SHEET,INVOICE_HEADERS);
    ensureSheet_(HISTORY_SHEET,HISTORY_HEADERS);
    const ctx=ensureSheet_(INVENTORY_SHEET,INVENTORY_HEADERS);
    syncOfficialInventory_(ctx);
    SpreadsheetApp.flush();
  });
  installRetryTrigger();
  console.log("Setup complete. Existing bookings were preserved, official room capacities were synchronized, and the pending-email retry trigger is installed.");
}
function syncOfficialRoomInventoryNow() {
  locked_(function() {
    const ctx=ensureSheet_(INVENTORY_SHEET,INVENTORY_HEADERS);
    syncOfficialInventory_(ctx);
    SpreadsheetApp.flush();
  });
  console.log("Official room capacities synchronized. Date-specific overrides were preserved.");
}

function diagnoseBackend() {
  prop_("BOOKING_API_TOKEN");
  const ss=spreadsheet_();
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
    try { processDocuments_(JSON.parse(row["Booking JSON"]),{},false,false); } catch(e) { /* Retry on next trigger. */ }
  }
}
function ensureRetryTrigger_() {
  const existing=ScriptApp.getProjectTriggers().filter(t=>t.getHandlerFunction()==="retryPendingEmails");
  if (!existing.length) ScriptApp.newTrigger("retryPendingEmails").timeBased().everyMinutes(1).create();
  return true;
}
function installRetryTrigger() {
  // Recreate deliberately so an older 5-minute trigger is upgraded to 1 minute.
  ScriptApp.getProjectTriggers().filter(t=>t.getHandlerFunction()==="retryPendingEmails").forEach(t=>ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger("retryPendingEmails").timeBased().everyMinutes(1).create();
  console.log("Pending-email retry trigger installed: every 1 minute.");
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
