"""Generate a numbered EUR-only booking request PDF in memory."""

from __future__ import annotations

import html
import io
import re
import secrets
from pathlib import Path
from typing import Any
from datetime import date as date_cls, timedelta

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image as RLImage,
    KeepInFrame,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from config import BASE_DIR, EVENT_TITLE, LOGO_PATHS, SYSTEM_TITLE


ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
FONT_REGULAR = "Helvetica"
FONT_BOLD = "Helvetica-Bold"

for regular_path, bold_path in [
    (
        BASE_DIR / "assets" / "fonts" / "DejaVuSans.ttf",
        BASE_DIR / "assets" / "fonts" / "DejaVuSans-Bold.ttf",
    ),
    (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ),
    (
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
    ),
]:
    if regular_path.exists() and bold_path.exists():
        pdfmetrics.registerFont(TTFont("ITKFRegular", str(regular_path)))
        pdfmetrics.registerFont(TTFont("ITKFBold", str(bold_path)))
        FONT_REGULAR = "ITKFRegular"
        FONT_BOLD = "ITKFBold"
        break


def _display_text(value: Any) -> str:
    text = str(value)
    if ARABIC_RE.search(text):
        try:
            import arabic_reshaper
            from bidi.algorithm import get_display

            text = get_display(arabic_reshaper.reshape(text))
        except ImportError:
            pass
    return text


def _safe(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return html.escape(_display_text(value))


def _money(value: Any, currency: str) -> str:
    try:
        return f"{currency} {float(value):,.2f}"
    except (TypeError, ValueError):
        return f"{currency} 0.00"


def _logo_banner() -> Table | None:
    """Build a centered three-logo row while preserving image proportions."""

    logos: list[RLImage] = []
    max_width = 38 * mm
    max_height = 24 * mm
    for configured_path in LOGO_PATHS.values():
        path = Path(configured_path)
        if not path.is_file():
            continue
        try:
            logo = RLImage(str(path))
            scale = min(max_width / logo.imageWidth, max_height / logo.imageHeight)
            logo.drawWidth = logo.imageWidth * scale
            logo.drawHeight = logo.imageHeight * scale
            logo.hAlign = "CENTER"
            logos.append(logo)
        except (OSError, ValueError):
            # A missing or unreadable logo must not prevent invoice creation.
            continue

    if not logos:
        return None

    total_width = 155 * mm
    banner = Table(
        [logos],
        colWidths=[total_width / len(logos)] * len(logos),
        rowHeights=[27 * mm],
        hAlign="CENTER",
    )
    banner.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]
        )
    )
    return banner


def _compact_dates(values: list[str]) -> str:
    """Compress consecutive ISO dates while preserving every booked service date."""
    parsed = []
    for value in sorted(set(str(v) for v in values)):
        try:
            parsed.append(date_cls.fromisoformat(value))
        except ValueError:
            return ", ".join(sorted(set(str(v) for v in values)))
    if not parsed:
        return "-"
    groups = []
    start = prev = parsed[0]
    for current in parsed[1:]:
        if current == prev + timedelta(days=1):
            prev = current
            continue
        groups.append((start, prev))
        start = prev = current
    groups.append((start, prev))
    return ", ".join(a.isoformat() if a == b else f"{a.isoformat()} to {b.isoformat()}" for a, b in groups)


def _transport_groups(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group repeated dated services with identical transport details for a compact one-page PDF."""
    grouped: dict[tuple, dict[str, Any]] = {}
    order: list[tuple] = []
    for item in items:
        vehicle_key = tuple(
            (str(line.get("vehicle", "")), int(line.get("quantity", 0)), float(line.get("unit_price_eur", 0)), float(line.get("total_eur", 0)))
            for line in item.get("vehicle_lines", [])
        )
        key = (
            str(item.get("service", "")), str(item.get("direction", "")),
            str(item.get("start_time", "")), str(item.get("end_time", "")),
            bool(item.get("ends_next_day")), int(item.get("persons", 0)), int(item.get("seats", 0)), vehicle_key,
        )
        if key not in grouped:
            grouped[key] = {"dates": [], "item": item, "count": 0, "total_eur": 0.0}
            order.append(key)
        grouped[key]["dates"].append(str(item.get("date", "")))
        grouped[key]["count"] += 1
        grouped[key]["total_eur"] += sum(float(line.get("total_eur", 0)) for line in item.get("vehicle_lines", []))
    return [grouped[key] for key in order]


def generate_pdf(booking: dict[str, Any], protect: bool = True) -> bytes:
    """Numbered EUR-only request summary, with modification restrictions."""
    buffer = io.BytesIO()
    encryption = StandardEncryption(
        userPassword="", ownerPassword=secrets.token_urlsafe(32),
        canPrint=1, canModify=0, canCopy=0, canAnnotate=0, strength=128,
    ) if protect else None
    document = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=13*mm, rightMargin=13*mm,
        topMargin=9*mm, bottomMargin=14*mm, encrypt=encryption,
        title="Booking Request " + str(booking.get("invoice_no", "")),
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("ITKFTitle", parent=styles["Title"], fontName=FONT_BOLD,
                           fontSize=15, leading=18, textColor=colors.HexColor("#C8102E"), alignment=TA_CENTER)
    normal = ParagraphStyle("ITKFNormal", parent=styles["Normal"], fontName=FONT_REGULAR, fontSize=7.8, leading=9.8)
    heading = ParagraphStyle("ITKFHeading", parent=normal, fontName=FONT_BOLD, fontSize=9.5, leading=11.5,
                             spaceBefore=5, spaceAfter=3, keepWithNext=True)
    centered = ParagraphStyle("ITKFCentered", parent=normal, alignment=TA_CENTER)
    def paragraph(value):
        return Paragraph(_safe(value), normal)
    def table(rows, widths, header=False):
        obj = Table([[paragraph(v) for v in row] for row in rows], colWidths=widths,
                    repeatRows=1 if header else 0, hAlign="LEFT")
        rules = [("VALIGN",(0,0),(-1,-1),"TOP"),
                 ("LINEBELOW",(0,0),(-1,-1),0.25,colors.HexColor("#DDDDDD")),
                 ("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),
                 ("TOPPADDING",(0,0),(-1,-1),2.5),("BOTTOMPADDING",(0,0),(-1,-1),2.5)]
        if header:
            rules.append(("BACKGROUND",(0,0),(-1,0),colors.HexColor("#F3F4F6")))
        obj.setStyle(TableStyle(rules))
        return obj
    story = []
    banner = _logo_banner()
    if banner:
        story.extend([banner, Spacer(1,1.5*mm)])
    story.extend([Paragraph(_safe(EVENT_TITLE),title),
                  Paragraph(_safe(SYSTEM_TITLE),centered),
                  Paragraph("Booking Request Summary",centered), Spacer(1,2.5*mm)])
    individual = booking.get("registration_type") == "Individual"
    details = [
        ["Invoice / Summary No",booking.get("invoice_no")],
        ["Request ID",booking.get("booking_id")],
        ["Revision",booking.get("revision", 1)],
        ["Verification Code",booking.get("invoice_verification_code")],
        ["Request Date",booking.get("booking_date")],
        ["Last Updated",booking.get("updated_at") or booking.get("booking_date")],
        ["Registration Type",booking.get("registration_type")],
        ["Guest Name" if individual else "Federation Name",
         booking.get("guest_name") if individual else booking.get("federation_name")],
        ["Email",booking.get("email")], ["Phone",booking.get("phone")],
    ]
    if individual:
        details.extend([["Nationality",booking.get("nationality")],["Date of Birth",booking.get("date_of_birth")],
                        ["Passport Number",booking.get("passport_number")]])
    elif booking.get("federation_country"):
        # Older saved requests have no federation-country field; do not invent it.
        details.append(["Federation Country",booking["federation_country"]])
    story.append(table(details,[48*mm,130*mm]))
    story.append(Paragraph("Accommodation",heading))
    story.append(paragraph(booking.get("hotel")))
    story.append(paragraph(str(booking.get("meal_plan",""))+" | "+str(booking.get("check_in",""))+
                           " to "+str(booking.get("check_out",""))+" | "+str(booking.get("nights",""))+" nights"))
    rows = [["Room Type","Rooms","EUR / Night","Total EUR"]]
    for item in booking.get("rooms", []):
        rows.append([item["room_type"],item["quantity"],_money(item["unit_rate_eur"],"EUR"),_money(item["total_eur"],"EUR")])
    story.extend([Spacer(1,1*mm),table(rows,[69*mm,19*mm,44*mm,46*mm],True),
                  paragraph("Guests: "+str(booking.get("guests","")))])
    transport_items = booking.get("transport_services", [])
    if transport_items:
        story.append(Paragraph("Transportation", heading))
        rows = [["Date(s)", "Service", "Time", "Pax", "Vehicles", "Total EUR"]]
        for group in _transport_groups(transport_items):
            item = group["item"]
            suffix = "+1" if item.get("ends_next_day") else ""
            service = str(item.get("service", ""))
            if item.get("direction"):
                service += " | " + str(item.get("direction"))
            vehicles = "; ".join(
                f"{line.get('vehicle', '')} x{line.get('quantity', 0)}"
                for line in item.get("vehicle_lines", [])
            ) or "-"
            if group["count"] > 1:
                vehicles += f" | {group['count']} service days"
            rows.append([
                _compact_dates(group["dates"]), service,
                f"{item.get('start_time', '')}-{item.get('end_time', '')}{suffix}",
                item.get("persons", ""), vehicles, _money(group["total_eur"], "EUR"),
            ])
        story.append(table(rows, [37*mm, 38*mm, 27*mm, 13*mm, 45*mm, 24*mm], True))
    story.append(Paragraph("Total",heading))
    story.append(table([["Accommodation",_money(booking.get("room_total_eur"),"EUR")],
                        ["Transportation",_money(booking.get("transport_total_eur"),"EUR")],
                        ["Grand Total",_money(booking.get("grand_total_eur"),"EUR")]], [116*mm,62*mm]))
    story.extend([Spacer(1,2*mm),paragraph("This is a booking request summary, not payment or final hotel confirmation. Please quote your Request ID in any communication."),
                  paragraph("To change this request, choose View / edit existing request in the application and verify your registered email. Do not submit a duplicate request.")])
    if int(booking.get("revision", 1)) > 1:
        story.append(paragraph("This revision replaces earlier request summaries for the same Request ID."))
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(FONT_REGULAR,7)
        canvas.setFillColor(colors.HexColor("#6B7280"))
        canvas.drawString(16*mm,9*mm,str(booking.get("invoice_no","")))
        canvas.drawRightString(194*mm,9*mm,f"Page {doc.page}")
        canvas.restoreState()
    # One-page invoice: keep the complete summary in one A4 frame and shrink
    # proportionally only when a large federation/transport request needs it.
    available_width = A4[0] - document.leftMargin - document.rightMargin
    available_height = A4[1] - document.topMargin - document.bottomMargin
    one_page = KeepInFrame(available_width, available_height, story, mode="shrink", mergeSpace=True)
    document.build([one_page], onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
