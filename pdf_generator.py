"""Generate a compact booking confirmation PDF in memory."""

from __future__ import annotations

import html
import io
import re
import secrets
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from config import EVENT_TITLE, SYSTEM_TITLE


ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
FONT_REGULAR = "Helvetica"
FONT_BOLD = "Helvetica-Bold"

for regular_path, bold_path in [
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


def generate_pdf(booking: dict[str, Any], protect: bool = True) -> bytes:
    buffer = io.BytesIO()
    encryption = None
    if protect:
        encryption = StandardEncryption(
            userPassword="",
            ownerPassword=secrets.token_urlsafe(32),
            canPrint=1,
            canModify=0,
            canCopy=0,
            canAnnotate=0,
            strength=128,
        )
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Invoice {_safe(booking.get('invoice_no') or booking.get('booking_id'))}",
        encrypt=encryption,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ITKFTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#C8102E"),
        fontName=FONT_BOLD,
        fontSize=18,
        leading=22,
    )
    subtitle_style = ParagraphStyle(
        "ITKFSubtitle",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontName=FONT_REGULAR,
        fontSize=10,
    )
    heading_style = ParagraphStyle(
        "ITKFHeading", parent=styles["Heading2"], fontName=FONT_BOLD, fontSize=14
    )
    cell_style = ParagraphStyle(
        "ITKFCell", parent=styles["Normal"], fontName=FONT_REGULAR, fontSize=8.5, leading=11
    )
    label_style = ParagraphStyle(
        "ITKFLabel", parent=cell_style, fontName=FONT_BOLD, textColor=colors.HexColor("#374151")
    )

    story = [
        Paragraph(_safe(EVENT_TITLE), title_style),
        Paragraph(_safe(SYSTEM_TITLE), subtitle_style),
        Spacer(1, 8 * mm),
        Paragraph("Booking Invoice", heading_style),
    ]

    rows = [
        ["Invoice No", _safe(booking.get("invoice_no") or booking.get("booking_id"))],
        ["Verification Code", _safe(booking.get("invoice_verification_code"))],
        ["Booking ID", _safe(booking.get("booking_id"))],
        ["Booking Date", _safe(booking.get("booking_date"))],
        ["Guest Name", _safe(booking.get("guest_name"))],
        ["Nationality", _safe(booking.get("nationality"))],
        ["Phone", _safe(booking.get("phone"))],
        ["Email", _safe(booking.get("email"))],
        ["Hotel", _safe(booking.get("hotel"))],
        ["Meal Plan", _safe(booking.get("meal_plan"))],
        ["Room Type", _safe(booking.get("room_type"))],
        ["Guests", _safe(booking.get("guests"))],
        ["Check-in", _safe(booking.get("check_in"))],
        ["Check-out", _safe(booking.get("check_out"))],
        ["Nights", _safe(booking.get("nights"))],
        ["Vehicle", _safe(booking.get("vehicle_type"))],
        ["Transportation Persons", _safe(booking.get("transport_persons"))],
        [
            "Transportation Price / Person",
            _money(booking.get("transport_price_per_person_eur"), "EUR"),
        ],
        ["Room Total", _money(booking.get("room_total_eur"), "EUR")],
        ["Transportation Total", _money(booking.get("transport_total_eur"), "EUR")],
        ["Grand Total", _money(booking.get("grand_total_eur"), "EUR")],
        ["USD Equivalent", _money(booking.get("grand_total_usd"), "USD")],
        ["EGP Equivalent", _money(booking.get("grand_total_egp"), "EGP")],
        ["Status", _safe(booking.get("status"))],
    ]

    formatted_rows = [
        [Paragraph(str(label), label_style), Paragraph(str(value), cell_style)]
        for label, value in rows
    ]
    table = Table(formatted_rows, colWidths=[50 * mm, 105 * mm], repeatRows=0)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F3F4F6")),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#374151")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend([table, Spacer(1, 8 * mm)])
    story.append(
        Paragraph(
            "This is a protected, non-editable invoice. Keep it and quote the Booking ID "
            "and Verification Code in any communication.",
            ParagraphStyle("ITKFFooter", parent=cell_style, fontSize=9),
        )
    )

    document.build(story)
    return buffer.getvalue()
