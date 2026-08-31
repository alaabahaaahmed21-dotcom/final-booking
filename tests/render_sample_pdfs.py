"""Generate local QA samples (not real bookings, not sent to Google)."""
from pathlib import Path
from test_request import example, service
from helpers import calculate_booking_totals
from pdf_generator import generate_pdf

out = Path(__file__).resolve().parents[1] / 'tmp' / 'pdfs'
out.mkdir(parents=True, exist_ok=True)
for kind in ('Individual', 'Federation'):
    booking = example(kind)
    if kind == 'Federation':
        booking['federation_name'] = 'الاتحاد المصري للكاراتيه التقليدي'
        booking['rooms'] = [{'room_type':'Double','quantity':3}, {'room_type':'Single','quantity':2}]
        booking['transport_services'] = [dict(service(), date=f'2026-10-{day}') for day in (24,25,26)]
    else:
        booking['transport_services'] = [service()]
    booking.update(calculate_booking_totals(booking))
    booking.update(invoice_no='INV-20260830-ABCDEF123456-R2', invoice_verification_code='TEST-ONLY-NOT-REAL',
                   revision=2, updated_at='2026-08-31T15:00:00+00:00')
    (out / f'{kind.lower()}-v4.pdf').write_bytes(generate_pdf(booking))
    print(out / f'{kind.lower()}-v4.pdf')
