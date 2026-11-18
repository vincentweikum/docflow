"""Normalizers for the values people write in a hundred different ways."""
from __future__ import annotations

import re
from datetime import date, datetime

MONEY = r"(?:\$\s?[\d,]+\.\d{2}|USD\s?[\d,]+\.\d{2}|[\d,]+\.\d{2}\s?USD|[\d,]+\.\d{2})"
DATE_FORMATS = ["%m/%d/%Y", "%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%d-%b-%Y", "%m-%d-%Y", "%d %B %Y"]


def parse_money(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(MONEY, text)
    if not m:
        return None
    return float(re.sub(r"[^\d.]", "", m.group(0)))


def parse_date(text: str | None) -> date | None:
    if not text:
        return None
    t = re.sub(r"\s+", " ", text.strip().rstrip(".,"))
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(t, f).date()
        except ValueError:
            continue
    return None
