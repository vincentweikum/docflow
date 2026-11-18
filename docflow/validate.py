"""Business rules. Anything that fails goes to a human review queue with a reason."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from docflow.extract import Extracted

TOLERANCE = 0.02  # cents of rounding slack
REQUIRED = ["vendor", "invoice_number", "invoice_date", "total"]
# The buyer's own purchase orders always look like this, so anything else is a misread or a typo.
PO_PATTERN = re.compile(r"^PO\d{6}$")


@dataclass
class Result:
    status: str                     # "approved" or "review"
    issues: list[str] = field(default_factory=list)


class Validator:
    """Stateful so it can catch duplicates across a batch."""

    def __init__(self) -> None:
        self.seen: dict[tuple[str, str], str] = {}

    def check(self, x: Extracted) -> Result:
        issues: list[str] = []
        for f in REQUIRED:
            if getattr(x, f) in (None, ""):
                issues.append(f"missing_{f}")
        if not x.po_number:
            issues.append("missing_po")
        elif not PO_PATTERN.match(x.po_number):
            issues.append("po_format")
        if not x.items:
            issues.append("no_line_items")

        for it in x.items:
            if it["quantity"] is None or it["unit_price"] is None or it["amount"] is None:
                issues.append(f"unreadable_line:{it['description'][:30]}")
            elif abs(it["quantity"] * it["unit_price"] - it["amount"]) > TOLERANCE:
                issues.append(f"line_math:{it['description'][:30]}")
        if x.items and x.subtotal is not None:
            if abs(sum(it["amount"] for it in x.items) - x.subtotal) > TOLERANCE:
                issues.append("line_sum_mismatch")
        if None not in (x.subtotal, x.tax, x.total) and abs(x.subtotal + x.tax - x.total) > TOLERANCE:
            issues.append("bad_total")
        if x.invoice_date and x.due_date and date.fromisoformat(x.due_date) < date.fromisoformat(x.invoice_date):
            issues.append("due_before_invoice")

        if x.vendor and x.invoice_number:
            key = (x.vendor.lower(), x.invoice_number.upper())
            if key in self.seen:
                issues.append(f"duplicate_of:{self.seen[key]}")
            else:
                self.seen[key] = x.file
        return Result("review" if issues else "approved", issues)
