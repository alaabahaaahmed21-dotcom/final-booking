/* Offline Apps Script simulation. No Google access and no real submissions. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const path=require('node:path');
const fixture=JSON.parse(fs.readFileSync(0,'utf8'));
class Range {
  constructor(sheet,r,c,n=1,m=1){Object.assign(this,{sheet,r,c,n,m});if(c+m-1>sheet.cols||r+n-1>sheet.rows)throw Error('Range exceeds grid');}
  getValues(){return Array.from({length:this.n},(_,i)=>Array.from({length:this.m},(_,j)=>this.sheet.data[this.r+i-1]?.[this.c+j-1]??''));}
  setValues(values){assert.equal(values.length,this.n);values.forEach((row,i)=>{assert.equal(row.length,this.m);this.sheet.data[this.r+i-1]??=[];row.forEach((v,j)=>{this.sheet.data[this.r+i-1][this.c+j-1]=typeof v==='string'&&v.startsWith("'")?v.slice(1):v;});});return this;}
  setNumberFormat(){return this;} setFontWeight(){return this;} setBackground(){return this;} setFontColor(){return this;}
  createTextFinder(text){
    const range=this;
    return {
      matchEntireCell(){return this;},
      findNext(){
        for(let i=0;i<range.n;i++) for(let j=0;j<range.m;j++) {
          const value=range.sheet.data[range.r+i-1]?.[range.c+j-1]??'';
          if(String(value)===String(text)) return {getRow:()=>range.r+i,getColumn:()=>range.c+j};
        }
        return null;
      }
    };
  }
}
class Sheet {
  constructor(){this.data=[];this.cols=26;this.rows=1000;}
  getLastColumn(){return this.data.reduce((n,r)=>Math.max(n,r.length),0);}
  getLastRow(){return this.data.length;}
  getMaxColumns(){return this.cols;} getMaxRows(){return this.rows;}
  insertColumnsAfter(_,n){this.cols+=n;} insertRowsAfter(_,n){this.rows+=n;}
  setFrozenRows(){} getRange(...args){return new Range(this,...args);}
}
const sheets={},files=new Map(),emails=[],cache=new Map(),triggers=[];let locked=false,busy=false,quota=100,emailCount=0,seq=0;
const blob=(bytes,mime,name)=>({getBytes:()=>Array.from(bytes),setName:()=>blob(bytes,mime,name)});
const ss={getSheetByName:n=>sheets[n],insertSheet:n=>(sheets[n]=new Sheet()),getSpreadsheetTimeZone:()=> 'Etc/UTC'};
const folder={getFilesByName:name=>{const found=[...files.values()].filter(f=>f.name===name);return{hasNext:()=>!!found.length,next:()=>found.shift()};},createFile:b=>{
  const id='file'+(++seq), name=b.name;const f={name,getId:()=>id,getUrl:()=>`private:${id}`,getBlob:()=>b,setTrashed:()=>{files.delete(id);}};files.set(id,f);return f;
}};
const ctx={console,Date,Math,JSON,Object,Array,Number,String,Boolean,Error,Infinity,isFinite,
  PropertiesService:{getScriptProperties:()=>({getProperty:n=>({SPREADSHEET_ID:'test-sheet',BOOKING_API_TOKEN:'test-token',INVOICE_FOLDER_ID:'test-folder'}[n]??null)})},
  LockService:{getScriptLock:()=>({tryLock:()=>{if(busy||locked)return false;locked=true;return true;},releaseLock:()=>{locked=false;}})},
  CacheService:{getScriptCache:()=>({get:key=>cache.get(key)||null,put:(key,value)=>cache.set(key,value),remove:key=>cache.delete(key)})},
  ScriptApp:{getProjectTriggers:()=>triggers,newTrigger:name=>({timeBased(){return this;},everyMinutes(){return this;},create(){const t={getHandlerFunction:()=>name};triggers.push(t);return t;}})},
  SpreadsheetApp:{openById:()=>ss,flush:()=>{}},
  DriveApp:{getFolderById:()=>folder,getFileById:id=>{if(!files.has(id))throw Error('File missing');return files.get(id);}},
  MailApp:{getRemainingDailyQuota:()=>quota,sendEmail:message=>{emails.push(message);emailCount++;quota--; }},
  Utilities:{DigestAlgorithm:{SHA_256:'sha256'},Charset:{UTF_8:'utf8'},
    getUuid:()=>crypto.randomUUID(),
    computeDigest:(_,value)=>Array.from(crypto.createHash('sha256').update(typeof value==='string'?value:Buffer.from(value)).digest()),
    computeHmacSha256Signature:(value,key)=>Array.from(crypto.createHmac('sha256',key).update(value).digest()),
    base64Encode:b=>Buffer.from(b).toString('base64'),base64Decode:s=>Array.from(Buffer.from(s,'base64')),
    newBlob:(bytes,mime,name)=>({...blob(bytes,mime,name),name}),formatDate:d=>d.toISOString().slice(0,10)},
  ContentService:{MimeType:{JSON:'json'},createTextOutput:s=>({setMimeType:()=>JSON.parse(s)})}
};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(__dirname,'../google_apps_script.gs'),'utf8'),ctx);
const call=(name,...args)=>ctx[name](...args);
const all=name=>call('rows_',call('ensureSheet_',name,name==='Room Inventory'?['Hotel','Room Type','Date','Capacity']:[]));
const clone=b=>JSON.parse(JSON.stringify(b));
const invoice=b=>{const normalized=call('normalizeBooking_',b),bytes=Buffer.concat([
  Buffer.from('%PDF-1.7\n'),Buffer.alloc(1200,32),Buffer.from('\n%%EOF\n')]);return{
  base64:bytes.toString('base64'),sha256:crypto.createHash('sha256').update(bytes).digest('hex'),
  filename:normalized.invoice_no+'.pdf',mime_type:'application/pdf',verification_code:normalized.invoice_verification_code};};
function changed(b,id){const copy=clone(b);copy.booking_id='ITKF-20260830-'+id.padStart(12,'0');return copy;}
function failure(code,fn){assert.throws(fn,e=>e.code===code);}
call('setupSheetsNow');assert(sheets.Bookings.cols>26,'schema expansion');
const normalized=call('normalizeBooking_',fixture);
assert.equal(normalized.grand_total_eur,fixture.grand_total_eur,'Python/JS total parity');
assert.equal(normalized.transport_services[0].seats,60);
assert.equal(normalized.transport_services.length,fixture.transport_services.length,'all repeated service dates retained');
let result=call('createBooking_',fixture,invoice(fixture));assert.equal(result.saved,true);assert.equal(result.customer_email_sent,true);
assert.equal(all('Bookings').length,1);assert.equal(all('Invoices').length,1);assert.equal(emailCount,1);
assert.equal(all('Bookings')[0]['Federation Country'],'Egypt');
assert.equal(all('Bookings')[0]['Federation Country Code'],'EG');
assert.equal(JSON.parse(all('Bookings')[0]['Booking JSON']).federation_country,'Egypt');
const confirmed=call('doPost',{postData:{contents:JSON.stringify({schema_version:fixture.schema_version,
  token:'test-token',action:'booking_status',booking_id:fixture.booking_id,
  expected_revision:1,invoice_no:normalized.invoice_no,email:fixture.email})}});
assert(confirmed.saved,'lost create response can confirm the same durable request');
const otherCountry=clone(fixture);otherCountry.federation_country='Germany';otherCountry.federation_country_code='DE';
failure('ID_CONFLICT',()=>call('createBooking_',otherCountry,{}));
const noCountry=changed(fixture,'10');delete noCountry.federation_country;delete noCountry.federation_country_code;
failure('VALIDATION_ERROR',()=>call('createBooking_',noCountry,{}));
result=call('createBooking_',fixture,invoice(fixture));assert.equal(all('Bookings').length,1);assert.equal(emailCount,1);assert.equal(files.size,1);
const ac=call('accommodation_',fixture);
assert.equal(call('availability_',ac,all('Bookings'))[0].remaining,49);
const next=clone(fixture);next.check_in='2026-10-26';next.check_out='2026-10-27';
assert.equal(call('availability_',call('accommodation_',next),all('Bookings'))[0].remaining,50,'checkout night released');
// An already accepted request retains its price if rates change later.
vm.runInContext('HOTEL_RATES_EUR["Tiba Rose El Golf"].Breakfast.Double=999',ctx);
result=call('createBooking_',fixture,{});assert(result.saved);assert.equal(all('Bookings')[0]['Grand Total EUR'],fixture.grand_total_eur);
vm.runInContext('HOTEL_RATES_EUR["Tiba Rose El Golf"].Breakfast.Double=50',ctx);
// A legacy row without new JSON columns still reserves one room.
const legacy={'Booking ID':'LEGACY-TEST',Hotel:fixture.hotel,'Room Type':'Double','Check-in':'2026-10-24','Check-out':'2026-10-26',Status:'Confirmed'};
assert.equal(call('availability_',ac,[legacy])[0].remaining,49);
legacy.Status='Cancelled';assert.equal(call('availability_',ac,[legacy])[0].remaining,50);
legacy.Status='Confirmed';legacy['Check-in']='bad-date';failure('INVENTORY_REVIEW',()=>call('availability_',ac,[legacy]));
const conflict=clone(fixture);conflict.email='different@example.com';failure('ID_CONFLICT',()=>call('createBooking_',conflict,{}));
const invctx=call('ensureSheet_','Room Inventory',['Hotel','Room Type','Date','Capacity']);
let stock=all('Room Inventory').find(r=>r.Hotel===fixture.hotel&&r['Room Type']==='Double');
call('writeRow_',invctx,stock._row,{Capacity:1},stock);call('setupSheetsNow');
stock=all('Room Inventory').find(r=>r.Hotel===fixture.hotel&&r['Room Type']==='Double');assert.equal(stock.Capacity,50,'setup synchronizes official capacity');
call('writeRow_',invctx,stock._row,{Capacity:1},stock);
failure('SOLD_OUT',()=>call('createBooking_',changed(fixture,'2'),{}));assert.equal(all('Bookings').length,1);
call('writeRow_',invctx,stock._row,{Capacity:50},stock);
busy=true;failure('BUSY',()=>call('createBooking_',changed(fixture,'3'),{}));busy=false;assert.equal(all('Bookings').length,1);
const short=changed(fixture,'4');delete short.transport_services[0].vehicles['Toyota Hiace (10 Seats)'];
failure('VALIDATION_ERROR',()=>call('createBooking_',short,{}));
for (const passengers of [1,40,50]) {
  const excess=clone(short.transport_services[0]);excess.persons=passengers;
  const accepted=call('transport_',[excess])[0];
  assert.equal(accepted.seats,50);assert.equal(accepted.remaining,0);assert.equal(accepted.total_eur,190);
}
const person=changed(fixture,'5');person.registration_type='Individual';person.guest_name='test person';person.federation_name='';person.passport_number='ab-12345';person.date_of_birth='1996-03-21';person.nationality='Egypt';person.nationality_code='EG';
result=call('createBooking_',person,invoice(person));assert(result.saved);
const duplicate=changed(person,'6');duplicate.passport_number='AB12345';failure('DUPLICATE_PASSPORT',()=>call('createBooking_',duplicate,{}));
assert.equal(all('Bookings').length,2);
quota=0;const mailPending=changed(fixture,'7');result=call('createBooking_',mailPending,invoice(mailPending));
assert(result.saved);assert(result.invoice_created);assert(!result.customer_email_sent);const before=all('Bookings').length;
quota=10;result=call('createBooking_',mailPending,invoice(mailPending));assert(result.customer_email_sent);assert.equal(all('Bookings').length,before);
const pdfPending=changed(fixture,'8');result=call('createBooking_',pdfPending,{});assert(result.saved);assert(!result.invoice_created);
result=call('createBooking_',pdfPending,invoice(pdfPending));assert(result.invoice_created);assert.equal(all('Bookings').length,before+1);
const badDate=changed(fixture,'9');badDate.check_in='2026-02-30';failure('VALIDATION_ERROR',()=>call('createBooking_',badDate,{}));
const override={Hotel:fixture.hotel,'Room Type':'Double',Date:'2026-10-25',Capacity:0};call('writeRow_',invctx,0,override);
assert.equal(call('availability_',ac,all('Bookings'))[0].remaining,0,'per-date override');
assert.equal(call('availability_',call('accommodation_',next),all('Bookings'))[0].remaining,50);
for (const end of ['2026-10-24','2026-10-23']) {
  assert.throws(()=>call('nights_','2026-10-24',end),e=>e.message==='The check-out date must be after the check-in date.');
}
assert.throws(()=>call('nights_','2026-10-01','2026-12-01'),e=>e.message==='Stay cannot exceed 60 nights.');
for (const [hours,end,late] of [[8,'04:00','05:00'],[12,'08:00','09:00']]) {
  const travel=clone(fixture.transport_services[0]);Object.assign(travel,{service:'Daily '+hours+' Hours',direction:'',start_time:'20:00',end_time:end,ends_next_day:true});
  assert.equal(call('transport_',[travel])[0].duration_minutes,hours*60);
  travel.end_time=late;failure('VALIDATION_ERROR',()=>call('transport_',[travel]));
}
// A pre-v3 request lacking federation country can still be retried unchanged.
const oldRaw=changed(fixture,'11');oldRaw.schema_version='2026-08-30-v2';delete oldRaw.federation_country;delete oldRaw.federation_country_code;
const oldSnapshot=clone(normalized);Object.assign(oldSnapshot,{booking_id:oldRaw.booking_id,schema_version:oldRaw.schema_version,invoice_no:'INV-20260830-000000000011'});
delete oldSnapshot.federation_country;delete oldSnapshot.federation_country_code;
const oldHashData={};['registration_type','guest_name','federation_name','passport_number','date_of_birth','nationality','nationality_code','phone','email','hotel','meal_plan','check_in','check_out'].forEach(k=>oldHashData[k]=oldRaw[k]||'');
oldHashData.rooms=oldRaw.rooms.map(r=>({room_type:r.room_type,quantity:r.quantity}));
oldHashData.transport_services=oldRaw.transport_services.map(r=>({date:r.date,service:r.service,direction:r.direction||'',start_time:r.start_time,end_time:r.end_time,ends_next_day:r.ends_next_day===true,persons:r.persons,vehicles:r.vehicles}));
const oldHash=crypto.createHash('sha256').update(JSON.stringify(call('sorted_',oldHashData))).digest('hex');
assert.equal(call('requestHash_',oldRaw),oldHash,'pre-v3 hash compatibility');
const oldRow=call('bookingColumns_',oldSnapshot);Object.assign(oldRow,{'Request Hash':oldHash,'Booking JSON':JSON.stringify(oldSnapshot),Status:'Received','Document Status':'Pending'});
call('writeRow_',call('ensureSheet_','Bookings',[]),0,oldRow);
const countBeforeRetry=all('Bookings').length;
assert(call('createBooking_',oldRaw,{}).saved);
assert.equal(all('Bookings').length,countBeforeRetry,'old retry does not create another reservation');
// Optional federation phone must work through normalization, storage, documents,
// email and idempotent retries, not just the browser's validation.
const noPhone=changed(fixture,'12');Object.assign(noPhone,{phone:'',phone_valid:false,check_in:'2026-11-01',check_out:'2026-11-03'});
const beforeNoPhone=all('Bookings').length;
const noPhoneResult=call('createBooking_',noPhone,invoice(noPhone));
assert(noPhoneResult.saved);assert(noPhoneResult.invoice_created);assert(noPhoneResult.customer_email_sent);
const noPhoneRow=all('Bookings').find(r=>r['Booking ID']===noPhone.booking_id);
assert.equal(noPhoneRow.Phone,'');assert.equal(JSON.parse(noPhoneRow['Booking JSON']).phone,'');
const mailsAfterNoPhone=emailCount;
assert(call('createBooking_',noPhone,invoice(noPhone)).saved);
assert.equal(all('Bookings').length,beforeNoPhone+1);assert.equal(emailCount,mailsAfterNoPhone);
for (const phone of [undefined,null,'   ']) {
  const omitted=clone(noPhone);omitted.phone=phone;
  assert.equal(call('normalizeBooking_',omitted).phone,'');
}
for (const phone of ['abc','+','+20']) {
  const invalid=clone(noPhone);invalid.phone=phone;
  failure('VALIDATION_ERROR',()=>call('normalizeBooking_',invalid));
}
const individualNoPhone=clone(person);individualNoPhone.phone='';
failure('VALIDATION_ERROR',()=>call('normalizeBooking_',individualNoPhone));
// v4: verify possession of the registered mailbox before exposing a request.
quota=1000;
function authenticate(b) {
  call('updateBooking_',b.booking_id,{'Edit Code Sent At':''});
  const before=emails.length;
  const reply=call('requestEditCode_',b.booking_id,b.email);
  assert(reply.ok);assert.equal(emails.length,before+1);
  const code=emails.at(-1).body.match(/code is: (\d{8})/)[1];
  const token=call('verifyEditCode_',b.booking_id,b.email,code).edit_token;
  assert(token);return token;
}
const emailBefore=emails.length;
const hidden=call('requestEditCode_',noPhone.booking_id,'unknown@example.com');
assert(hidden.ok);assert.equal(emails.length,emailBefore);assert(!hidden.booking);
const token=authenticate(noPhone);
const loaded=call('loadRequest_',noPhone.booking_id,token);
assert.equal(loaded.booking.email,noPhone.email);assert.equal(loaded.revision,1);
assert(loaded.invoice_base64);assert(loaded.editable);
assert(!JSON.stringify(loaded).includes('Edit Grant Hash'));
failure('EDIT_AUTH',()=>call('loadRequest_',noPhone.booking_id,'bad-token'));
failure('EDIT_CODE',()=>call('verifyEditCode_',noPhone.booking_id,noPhone.email,emails.at(-1).body.match(/code is: (\d{8})/)[1]));
const requestCount=all('Bookings').length, invoiceCount=all('Invoices').length;
let edited=clone(loaded.booking);
edited.rooms[0].quantity=2;edited.grand_total_eur+=edited.rooms[0].unit_rate_eur*edited.nights;
edited.schema_version=fixture.schema_version;edited.revision=2;edited.updated_at=new Date().toISOString();
const auth={edit_token:token,expected_revision:1,edit_operation_id:'a'.repeat(32)};
failure('EDIT_AUTH',()=>call('amendBooking_',edited,{}, {...auth,edit_token:'bad-token'}));
const changedEmail=clone(edited);changedEmail.email='other@example.com';
failure('EDIT_IDENTITY',()=>call('amendBooking_',changedEmail,{},auth));
const changedType=clone(edited);changedType.registration_type='Individual';
failure('EDIT_IDENTITY',()=>call('amendBooking_',changedType,{},auth));
result=call('amendBooking_',edited,invoice(edited),auth);
assert(result.saved);assert(result.customer_email_sent);assert(result.invoice_created);
assert.equal(result.revision,2);assert(result.invoice_no.endsWith('-R2'));
assert.equal(all('Bookings').length,requestCount,'amendment replaces the same row');
assert.equal(all('Invoices').length,invoiceCount+1,'prior invoice retained');
assert.equal(all('Request History').filter(r=>r['Booking ID']===edited.booking_id).length,1);
assert.equal(call('availability_',call('accommodation_',edited),all('Bookings'))[0].remaining,48,'only revised room count is held');
const mailAfterEdit=emails.length;
result=call('amendBooking_',edited,invoice(edited),auth);
assert.equal(result.revision,2);assert.equal(all('Bookings').length,requestCount);assert.equal(emails.length,mailAfterEdit,'lost edit response is idempotent');
failure('EDIT_CONFLICT',()=>call('amendBooking_',edited,{}, {...auth,edit_operation_id:'b'.repeat(32)}));
failure('NO_CHANGES',()=>call('amendBooking_',edited,{}, {...auth,expected_revision:2,edit_operation_id:'b'.repeat(32)}));
const reordered=clone(edited);reordered.transport_services.reverse();
failure('NO_CHANGES',()=>call('amendBooking_',reordered,{}, {...auth,expected_revision:2,edit_operation_id:'b'.repeat(32)}));
const oversized=clone(edited);oversized.rooms[0].quantity=51;oversized.revision=3;
oversized.grand_total_eur+=49*oversized.rooms[0].unit_rate_eur*oversized.nights;
failure('SOLD_OUT',()=>call('amendBooking_',oversized,{}, {...auth,expected_revision:2,edit_operation_id:'c'.repeat(32)}));
assert.equal(call('loadRequest_',edited.booking_id,token).revision,2,'failed update leaves previous request intact');
const editableAvailability=call('doPost',{postData:{contents:JSON.stringify({schema_version:fixture.schema_version,token:'test-token',
  action:'check_availability',booking:edited,edit_token:token})}});
assert.equal(editableAvailability.availability[0].remaining,50,'preview excludes own reservation only after authorization');
// Missing Drive copy can be repaired after reopening, without another revision.
let latest=call('loadRequest_',edited.booking_id,token);
const missingFile=all('Bookings').find(r=>r['Booking ID']===edited.booking_id)['Invoice File ID'];files.delete(missingFile);
latest=call('loadRequest_',edited.booking_id,token);assert(latest.invoice_read_error);
const repaired=call('processDocuments_',latest.booking,invoice(latest.booking),true,false,true);
assert(repaired.invoice_created);assert(repaired.customer_email_sent);assert.equal(repaired.revision,2);
// A readable but corrupted Drive file is replaced and the corrected PDF is
// re-sent instead of remaining in an endless pending state.
const corruptId=all('Bookings').find(r=>r['Booking ID']===edited.booking_id)['Invoice File ID'];
const corruptName=files.get(corruptId).name;
files.set(corruptId,{name:corruptName,getId:()=>corruptId,getUrl:()=>`private:${corruptId}`,
  getBlob:()=>blob(Buffer.from('%PDF-1.7 readable but missing eof'),'application/pdf',corruptName),
  setTrashed:()=>files.delete(corruptId)});
const mailsBeforeCorruptRepair=emailCount;
const corruptRepaired=call('processDocuments_',latest.booking,invoice(latest.booking),true,false,true);
assert(corruptRepaired.invoice_created);assert(corruptRepaired.customer_email_sent);
assert.notEqual(corruptRepaired.invoice_sha256,'');assert.equal(emailCount,mailsBeforeCorruptRepair+1);
assert(corruptRepaired.invoice_base64,'recovery returns the authoritative repaired PDF');
failure('EDIT_CONFLICT',()=>call('updateDocument_',latest.booking,'old-lease',{'Customer Email Sent':false}));
// Quota failures preserve the revised request and can be retried after reopening.
const third=clone(edited);third.rooms[0].quantity=3;third.revision=3;third.grand_total_eur+=100;
quota=0;
const auth3={...auth,expected_revision:2,edit_operation_id:'d'.repeat(32)};
const mailFail=call('amendBooking_',third,invoice(third),auth3);
assert(mailFail.saved);assert(mailFail.invoice_created);assert(!mailFail.customer_email_sent);
quota=100;call('retryPendingEmails');
assert(call('loadRequest_',edited.booking_id,token).customer_email_sent);
assert.equal(all('Bookings').length,requestCount);
// Unchanged individual passport is allowed on its own record, never on another.
const personToken=authenticate(person);
const personal=clone(call('loadRequest_',person.booking_id,personToken).booking);
personal.phone='+201112345678';personal.revision=2;personal.schema_version=fixture.schema_version;
personal.check_in='2026-12-01';personal.check_out='2026-12-03';
assert(call('amendBooking_',personal,invoice(personal),{edit_token:personToken,expected_revision:1,edit_operation_id:'e'.repeat(32)}).saved);
const otherPerson=changed(person,'ABC');otherPerson.passport_number='OTHER123';otherPerson.check_in='2026-12-01';otherPerson.check_out='2026-12-03';
call('createBooking_',otherPerson,invoice(otherPerson));
personal.passport_number='OTHER123';personal.revision=3;
failure('DUPLICATE_PASSPORT',()=>call('amendBooking_',personal,{}, {edit_token:personToken,expected_revision:2,edit_operation_id:'f'.repeat(32)}));
// Bad OTP attempts and expiration do not grant access; send cooldown limits abuse.
call('updateBooking_',otherPerson.booking_id,{'Edit Code Sent At':''});
call('requestEditCode_',otherPerson.booking_id,otherPerson.email);
const correct=emails.at(-1).body.match(/code is: (\d{8})/)[1], sends=emails.length;
call('requestEditCode_',otherPerson.booking_id,otherPerson.email);assert.equal(emails.length,sends);
for(let i=0;i<5;i++) failure('EDIT_CODE',()=>call('verifyEditCode_',otherPerson.booking_id,otherPerson.email,'xxxxxxxx'));
failure('EDIT_CODE',()=>call('verifyEditCode_',otherPerson.booking_id,otherPerson.email,correct));
call('updateBooking_',edited.booking_id,{'Edit Grant Expires':'2000-01-01T00:00:00Z'});
failure('EDIT_AUTH',()=>call('loadRequest_',edited.booking_id,token));
call('updateBooking_',person.booking_id,{Status:'Cancelled'});
assert(!call('loadRequest_',person.booking_id,personToken).editable);
failure('EDIT_CLOSED',()=>call('amendBooking_',personal,{}, {edit_token:personToken,expected_revision:2,edit_operation_id:'f'.repeat(32)}));
// v5.7 fast completion: Web App save returns before MailApp; protected PDF is
// stored first and the installed trigger delivers the pending email later.
quota=1000;
const queued=changed(fixture,'13');queued.check_in='2026-12-10';queued.check_out='2026-12-12';
const queuedCreate=call('doPost',{postData:{contents:JSON.stringify({schema_version:fixture.schema_version,token:'test-token',action:'create_booking',booking:queued})}});
assert(queuedCreate.saved);assert(!queuedCreate.invoice_created);
const queuedDocs=call('doPost',{postData:{contents:JSON.stringify({schema_version:fixture.schema_version,token:'test-token',action:'process_documents',booking_id:queued.booking_id,invoice:invoice(queued),defer_email:true})}});
assert(queuedDocs.saved);assert(queuedDocs.invoice_created);assert(!queuedDocs.customer_email_sent);
assert(triggers.some(t=>t.getHandlerFunction()==='retryPendingEmails'));
call('retryPendingEmails');
assert(all('Bookings').find(r=>r['Booking ID']===queued.booking_id)['Customer Email Sent']);
console.log('PASS backend: schemas, parity, quotas, retries, passport uniqueness, room holds, OTP, amendments, revisions, recovery, conflict protection');
