/* Offline Apps Script simulation. No Google access and no real submissions. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const path=require('node:path');
const fixture=JSON.parse(fs.readFileSync(0,'utf8'));
class Range {
  constructor(sheet,r,c,n=1,m=1){Object.assign(this,{sheet,r,c,n,m});if(c+m-1>sheet.cols||r+n-1>sheet.rows)throw Error('Range exceeds grid');}
  getValues(){return Array.from({length:this.n},(_,i)=>Array.from({length:this.m},(_,j)=>this.sheet.data[this.r+i-1]?.[this.c+j-1]??''));}
  setValues(values){assert.equal(values.length,this.n);values.forEach((row,i)=>{assert.equal(row.length,this.m);this.sheet.data[this.r+i-1]??=[];row.forEach((v,j)=>{this.sheet.data[this.r+i-1][this.c+j-1]=typeof v==='string'&&v.startsWith("'")?v.slice(1):v;});});return this;}
  setNumberFormat(){return this;} setFontWeight(){return this;} setBackground(){return this;} setFontColor(){return this;}
}
class Sheet {
  constructor(){this.data=[];this.cols=26;this.rows=1000;}
  getLastColumn(){return this.data.reduce((n,r)=>Math.max(n,r.length),0);}
  getLastRow(){return this.data.length;}
  getMaxColumns(){return this.cols;} getMaxRows(){return this.rows;}
  insertColumnsAfter(_,n){this.cols+=n;} insertRowsAfter(_,n){this.rows+=n;}
  setFrozenRows(){} getRange(...args){return new Range(this,...args);}
}
const sheets={},files=new Map();let locked=false,busy=false,quota=100,emailCount=0,seq=0;
const blob=(bytes,mime,name)=>({getBytes:()=>Array.from(bytes),setName:()=>blob(bytes,mime,name)});
const ss={getSheetByName:n=>sheets[n],insertSheet:n=>(sheets[n]=new Sheet()),getSpreadsheetTimeZone:()=> 'Etc/UTC'};
const folder={getFilesByName:name=>{const found=[...files.values()].filter(f=>f.name===name);return{hasNext:()=>!!found.length,next:()=>found.shift()};},createFile:b=>{
  const id='file'+(++seq), name=b.name;const f={name,getId:()=>id,getUrl:()=>`private:${id}`,getBlob:()=>b};files.set(id,f);return f;
}};
const ctx={console,Date,Math,JSON,Object,Array,Number,String,Boolean,Error,Infinity,isFinite,
  PropertiesService:{getScriptProperties:()=>({getProperty:n=>({SPREADSHEET_ID:'test-sheet',BOOKING_API_TOKEN:'test-token',INVOICE_FOLDER_ID:'test-folder'}[n]??null)})},
  LockService:{getScriptLock:()=>({tryLock:()=>{if(busy||locked)return false;locked=true;return true;},releaseLock:()=>{locked=false;}})},
  SpreadsheetApp:{openById:()=>ss,flush:()=>{}},
  DriveApp:{getFolderById:()=>folder,getFileById:id=>{if(!files.has(id))throw Error('File missing');return files.get(id);}},
  MailApp:{getRemainingDailyQuota:()=>quota,sendEmail:()=>{emailCount++;quota--; }},
  Utilities:{DigestAlgorithm:{SHA_256:'sha256'},Charset:{UTF_8:'utf8'},
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
const invoice=b=>{const normalized=call('normalizeBooking_',b),bytes=Buffer.from('%PDF-1.4 offline-test');return{
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
const otherCountry=clone(fixture);otherCountry.federation_country='Germany';otherCountry.federation_country_code='DE';
failure('ID_CONFLICT',()=>call('createBooking_',otherCountry,{}));
const noCountry=changed(fixture,'10');delete noCountry.federation_country;delete noCountry.federation_country_code;
failure('VALIDATION_ERROR',()=>call('createBooking_',noCountry,{}));
result=call('createBooking_',fixture,invoice(fixture));assert.equal(all('Bookings').length,1);assert.equal(emailCount,1);assert.equal(files.size,1);
const ac=call('accommodation_',fixture);
assert.equal(call('availability_',ac,all('Bookings'))[0].remaining,9);
const next=clone(fixture);next.check_in='2026-10-26';next.check_out='2026-10-27';
assert.equal(call('availability_',call('accommodation_',next),all('Bookings'))[0].remaining,10,'checkout night released');
// An already accepted request retains its price if rates change later.
vm.runInContext('HOTEL_RATES_EUR["Tiba Rose El Golf"].Breakfast.Double=999',ctx);
result=call('createBooking_',fixture,{});assert(result.saved);assert.equal(all('Bookings')[0]['Grand Total EUR'],fixture.grand_total_eur);
vm.runInContext('HOTEL_RATES_EUR["Tiba Rose El Golf"].Breakfast.Double=50',ctx);
// A legacy row without new JSON columns still reserves one room.
const legacy={'Booking ID':'LEGACY-TEST',Hotel:fixture.hotel,'Room Type':'Double','Check-in':'2026-10-24','Check-out':'2026-10-26',Status:'Confirmed'};
assert.equal(call('availability_',ac,[legacy])[0].remaining,9);
legacy.Status='Cancelled';assert.equal(call('availability_',ac,[legacy])[0].remaining,10);
legacy.Status='Confirmed';legacy['Check-in']='bad-date';failure('INVENTORY_REVIEW',()=>call('availability_',ac,[legacy]));
const conflict=clone(fixture);conflict.email='different@example.com';failure('ID_CONFLICT',()=>call('createBooking_',conflict,{}));
const invctx=call('ensureSheet_','Room Inventory',['Hotel','Room Type','Date','Capacity']);
let stock=all('Room Inventory').find(r=>r.Hotel===fixture.hotel&&r['Room Type']==='Double');
call('writeRow_',invctx,stock._row,{Capacity:1},stock);call('setupSheetsNow');
stock=all('Room Inventory').find(r=>r.Hotel===fixture.hotel&&r['Room Type']==='Double');assert.equal(stock.Capacity,1,'setup preserves edits');
failure('SOLD_OUT',()=>call('createBooking_',changed(fixture,'2'),{}));assert.equal(all('Bookings').length,1);
call('writeRow_',invctx,stock._row,{Capacity:10},stock);
busy=true;failure('BUSY',()=>call('createBooking_',changed(fixture,'3'),{}));busy=false;assert.equal(all('Bookings').length,1);
const short=changed(fixture,'4');delete short.transport_services[0].vehicles['Toyota Hiace (10 Seats)'];
failure('VALIDATION_ERROR',()=>call('createBooking_',short,{}));
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
assert.equal(call('availability_',call('accommodation_',next),all('Bookings'))[0].remaining,10);
for (const end of ['2026-10-24','2026-10-23']) {
  assert.throws(()=>call('nights_','2026-10-24',end),e=>e.message==='Check out date must be after check in date.');
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
console.log('PASS backend: schemas, parity, quotas, retries, duplicate passport, dates, capacities, documents, concurrency lock');
