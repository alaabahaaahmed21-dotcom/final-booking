"""Preview and apply the one-time correction to historical accommodation totals.

This is an operator-only command. It has no Streamlit page and does not change
the customer OTP workflow. Run without arguments first; applying requires the
explicit confirmation phrase documented in UPDATE_INSTRUCTIONS.md.
"""
from __future__ import annotations

import argparse
import sys

from sheets import preview_repricing, process_saved_documents, reprice_booking


def all_candidates() -> tuple[list[dict], list[dict]]:
    items: list[dict] = []
    errors: list[dict] = []
    after_row = 1
    while True:
        result = preview_repricing(after_row=after_row, limit=100)
        if not result.get("ok"):
            raise RuntimeError(result.get("error") or "Repricing preview failed.")
        items.extend(result.get("items") or [])
        errors.extend(result.get("errors") or [])
        if not result.get("has_more"):
            return items, errors
        next_row = int(result.get("next_after_row", after_row))
        if next_row <= after_row:
            raise RuntimeError("Repricing preview did not advance safely.")
        after_row = next_row


def show_preview(items: list[dict], errors: list[dict]) -> None:
    print("Bookings requiring corrected accommodation pricing:", len(items))
    for item in items:
        action = "documents/email pending" if not item.get("needs_repricing") else "reprice"
        print(
            f"{item['booking_id']} | {action} | revision {item['revision']} | "
            f"room EUR {item['room_total_old']:.2f} -> {item['room_total_new']:.2f} | "
            f"grand EUR {item['grand_total_old']:.2f} -> {item['grand_total_new']:.2f}"
        )
    if errors:
        print("Rows requiring manual review:", len(errors))
        for error in errors:
            print(f"{error.get('booking_id') or '(missing ID)'} | {error.get('error')}")


def apply(items: list[dict]) -> int:
    completed = queued = failed = 0
    for item in items:
        try:
            result = reprice_booking(item)
            if not result.get("ok") or not result.get("saved"):
                raise RuntimeError(result.get("error") or "The corrected price was not saved.")
            booking = result.get("booking")
            if not isinstance(booking, dict):
                raise RuntimeError("The saved booking snapshot was not returned.")
            documents = process_saved_documents(booking, defer_email=True)
            if not documents.saved or not documents.data.get("invoice_created"):
                raise RuntimeError(documents.message or "The revised PDF was not stored.")
            completed += 1
            if not documents.data.get("customer_email_sent"):
                queued += 1
            email_status = "email sent" if documents.data.get("customer_email_sent") else "email queued"
            print(f"OK {booking['booking_id']} | {booking['invoice_no']} | {email_status}")
        except Exception as exc:
            failed += 1
            print(f"FAILED {item.get('booking_id', '(missing ID)')} | {exc}", file=sys.stderr)
    print(f"Finished: {completed} prepared, {queued} queued for email, {failed} failed.")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview or apply corrected per-person hotel pricing.")
    parser.add_argument("--apply", action="store_true", help="Apply the previewed corrections and create revised PDFs.")
    parser.add_argument("--confirm", default="", help="Required with --apply; enter REPRICE-AND-EMAIL.")
    args = parser.parse_args()
    if args.apply and args.confirm != "REPRICE-AND-EMAIL":
        parser.error("--apply requires --confirm REPRICE-AND-EMAIL")
    try:
        items, errors = all_candidates()
        show_preview(items, errors)
        if not args.apply:
            print("Preview only: no booking, PDF, or email was changed.")
            return 0 if not errors else 2
        if errors:
            print("Apply stopped because some rows need manual review.", file=sys.stderr)
            return 2
        if not items:
            print("Nothing to update.")
            return 0
        return apply(items)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
