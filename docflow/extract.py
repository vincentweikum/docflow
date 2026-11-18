"""Pull fields and line items out of invoice text, whatever the vendor's layout."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from docflow.parse import MONEY, parse_date, parse_money

# Every way a vendor in the test set labels a field. Order matters: longer and more
# specific labels first, so "Total Due" is never read as a due date and "Bill To" is
# never read as a bill number.
LABELS: dict[str, list[str]] = {
    "invoice_number": [r"invoice\s*(?:#|no\.?|number:?)", r"inv\s*number:?", r"bill\s*no\.?"],
    "po_number": [r"p\.?o\.?\s*(?:#|number)", r"purchase\s*order", r"customer\s*po"],
    "invoice_date": [r"invoice\s*date", r"date\s*issued", r"billing\s*date", r"(?<![a-z] )\bdate"],
    "due_date": [r"due\s*date", r"payment\s*due", r"pay\s*by", r"(?<!total )(?<!amount )(?<!balance )\bdue"],
}
TOTAL_LABEL = r"(?:total\s*due|amount\s*due|balance\s*due|total)"
ITEM_HEADER = re.compile(r"^(description|item)\b.*\b(qty|quantity)\b", re.I)
# qty is any short token: OCR often turns a 7 into "L", "i", "re" or "rg". parse_item repairs it.
ITEM_LINE = re.compile(
    rf"^(?P<desc>.+?)\s+(?P<qty>\S{{1,3}})\s+(?P<unit>{MONEY})\s+(?P<amt>{MONEY})\s*$")
SKIP_LINES = re.compile(r"^(bill to|subtotal|sales tax|thank|remit|net terms)", re.I)


@dataclass
class Extracted:
    file: str
    vendor: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    po_number: str | None = None
    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None
    items: list[dict] = field(default_factory=list)
    raw_text: str = ""
    method: str = "text"


def _all_labels() -> re.Pattern:
    alts = [f"(?P<{k}_{i}>{p})" for k, ps in LABELS.items() for i, p in enumerate(ps)]
    return re.compile(r"(?:^|(?<=\s))(?:" + "|".join(alts) + r")\s*:?\s*", re.I)


LABEL_RE = _all_labels()


def header_fields(lines: list[str]) -> dict[str, str]:
    """Find 'label value' pairs anywhere in the header, including two per line."""
    found: dict[str, str] = {}
    for line in lines:
        if SKIP_LINES.match(line) or re.match(TOTAL_LABEL, line, re.I):
            continue
        matches = list(LABEL_RE.finditer(line))
        for j, m in enumerate(matches):
            key = next(k.rsplit("_", 1)[0] for k, v in m.groupdict().items() if v)
            end = matches[j + 1].start() if j + 1 < len(matches) else len(line)
            value = line[m.end():end].strip(" :")
            if value and key not in found:
                found[key] = value
    return found


def parse_item(m: re.Match) -> dict:
    """Build a line item. If OCR garbled the quantity, recover it from amount / unit price."""
    unit, amount = parse_money(m["unit"]), parse_money(m["amt"])
    item = {"description": m["desc"].strip(), "quantity": None, "unit_price": unit,
            "amount": amount, "repaired": False}
    if m["qty"].isdigit():
        item["quantity"] = int(m["qty"])
    if unit and amount and (item["quantity"] is None or abs(item["quantity"] * unit - amount) > 0.02):
        implied = amount / unit
        if abs(implied - round(implied)) * unit <= 0.02 and round(implied) >= 1:
            item["quantity"], item["repaired"] = round(implied), True
    return item


def extract_text(text: str, file: str = "") -> Extracted:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    out = Extracted(file=file, raw_text=text, vendor=lines[0] if lines else None)

    # The column header row ends the header block. If OCR mangled it, fall back to the
    # first line that looks like a line item.
    header_row = next((i for i, ln in enumerate(lines) if ITEM_HEADER.match(ln)), None)
    if header_row is not None:
        head_end, body_start = header_row, header_row + 1
    else:
        head_end = next((i for i, ln in enumerate(lines) if ITEM_LINE.match(ln)
                         or re.match(r"^subtotal", ln, re.I)), len(lines))
        body_start = head_end
    h = header_fields(lines[1:head_end])
    out.invoice_number = h.get("invoice_number")
    out.po_number = h.get("po_number")
    for k in ("invoice_date", "due_date"):
        d = parse_date(h.get(k))
        setattr(out, k, d.isoformat() if d else None)

    for ln in lines[body_start:]:
        if m := ITEM_LINE.match(ln):
            if not SKIP_LINES.match(m["desc"]):
                out.items.append(parse_item(m))
        elif re.match(r"^subtotal", ln, re.I):
            out.subtotal = parse_money(ln)
        elif re.match(r"^(sales\s*)?tax", ln, re.I):
            out.tax = parse_money(ln)
        elif re.match(TOTAL_LABEL + r"\s*:", ln, re.I):
            out.total = parse_money(ln)
    return out


def ocr_pdf(path: Path, dpi: int = 300) -> str:
    """OCR fallback for image-only PDFs (scans, phone photos saved as PDF)."""
    import pypdfium2 as pdfium
    import pytesseract

    doc = pdfium.PdfDocument(str(path))
    pages = [doc[i].render(scale=dpi / 72).to_pil() for i in range(len(doc))]
    return "\n".join(pytesseract.image_to_string(img, config="--psm 6") for img in pages)


def extract_pdf(path: Path) -> Extracted:
    """Use the PDF's text layer when it has one, otherwise OCR it."""
    with pdfplumber.open(path) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    method = "text"
    if len(text.strip()) < 40:
        text, method = ocr_pdf(path), "ocr"
    out = extract_text(text, file=path.name)
    out.method = method
    return out
