"""Generate a realistic, messy test set of invoice PDFs with answer keys.

Real invoices aren't shareable, so the test set is synthetic, but it's built to be
annoying in the ways real ones are: five vendor layouts, labels that change from
vendor to vendor, four date formats, three money formats, and a share of documents
with deliberate problems (math that doesn't add up, a missing PO, a duplicate
invoice, a due date before the invoice date). Every PDF gets a JSON answer key so
the extractor can be scored.
"""
from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

VENDORS = [
    ("Bayline Steel Supply", "layout_table"),
    ("Coastal Electric Co.", "layout_keyvalue"),
    ("Redwood Hydraulics LLC", "layout_twocol"),
    ("Pacific Fastener Group", "layout_compact"),
    ("Golden Gate Rigging", "layout_table"),
    ("Mission Industrial Parts", "layout_keyvalue"),
    ("Delta Crane Services", "layout_twocol"),
    ("Harbor Paint & Coatings", "layout_compact"),
    ("Sierra Safety Equipment", "layout_letter"),
]
ITEMS = [
    ("Wire rope 3/4in x 100ft", 210, 640), ("Shackle 25T", 85, 190), ("Hydraulic hose assembly", 60, 260),
    ("Safety harness, full body", 120, 310), ("Anchor bolt M24 (box of 20)", 45, 120),
    ("Epoxy primer, 5 gal", 140, 280), ("Load cell calibration", 350, 900), ("Field service hour", 95, 165),
    ("Limit switch", 70, 210), ("Grease cartridge (case)", 30, 75), ("Welding rod 7018 (50 lb)", 110, 190),
    ("Sheave bearing", 260, 720), ("Hard hat, class E", 18, 40), ("Freight and handling", 40, 160),
]
INV_LABELS = ["Invoice #", "Invoice No.", "Inv Number:", "INVOICE NUMBER", "Bill No."]
DATE_LABELS = ["Invoice Date", "Date", "Date Issued", "Billing Date"]
DUE_LABELS = ["Due Date", "Payment Due", "Due", "Pay By"]
PO_LABELS = ["PO #", "P.O. Number", "Purchase Order", "Customer PO"]
TOTAL_LABELS = ["Total Due", "TOTAL", "Amount Due", "Balance Due"]
ERRORS = ["bad_total", "missing_po", "due_before_invoice", "duplicate", "line_sum_mismatch"]


@dataclass
class LineItem:
    description: str
    quantity: int
    unit_price: float

    @property
    def amount(self) -> float:
        return round(self.quantity * self.unit_price, 2)


@dataclass
class Invoice:
    file: str
    vendor: str
    layout: str
    invoice_number: str
    invoice_date: str
    due_date: str
    po_number: str | None
    items: list[LineItem]
    subtotal: float
    tax: float
    total: float
    injected_errors: list[str] = field(default_factory=list)
    duplicate_of: str | None = None


def fmt_date(d: date, style: int) -> str:
    return [d.strftime("%m/%d/%Y"), d.strftime("%B %d, %Y").replace(" 0", " "),
            d.isoformat(), d.strftime("%d-%b-%Y")][style]


def fmt_money(x: float, style: int) -> str:
    return [f"${x:,.2f}", f"{x:,.2f} USD", f"USD {x:.2f}"][style]


def make_invoice(i: int, rng: random.Random, seen: list[Invoice]) -> Invoice:
    vendor, layout = rng.choice(VENDORS)
    inv_date = date(2026, 1, 1) + timedelta(days=rng.randint(0, 300))
    due = inv_date + timedelta(days=rng.choice([15, 30, 45, 60]))
    items = [LineItem(d, rng.randint(1, 12), round(rng.uniform(lo, hi), 2))
             for d, lo, hi in rng.sample(ITEMS, rng.randint(1, 6))]
    subtotal = round(sum(it.amount for it in items), 2)
    tax = round(subtotal * rng.choice([0, 0.0725, 0.0875, 0.1025]), 2)
    inv = Invoice(
        file=f"inv_{i:04d}.pdf", vendor=vendor, layout=layout,
        invoice_number=f"{vendor[:3].upper()}-{rng.randint(10000, 99999)}",
        invoice_date=inv_date.isoformat(), due_date=due.isoformat(),
        po_number=f"PO{rng.randint(400000, 499999)}", items=items,
        subtotal=subtotal, tax=tax, total=round(subtotal + tax, 2),
    )
    if rng.random() < 0.18:                      # about 1 in 6 documents has a problem
        err = rng.choice(ERRORS if seen else ERRORS[:3] + ERRORS[4:])
        inv.injected_errors.append(err)
        if err == "bad_total":
            inv.total = round(inv.total + rng.choice([-1, 1]) * rng.uniform(5, 250), 2)
        elif err == "missing_po":
            inv.po_number = None
        elif err == "due_before_invoice":
            inv.due_date = (inv_date - timedelta(days=rng.randint(1, 20))).isoformat()
        elif err == "duplicate":
            src = rng.choice(seen)
            inv.vendor, inv.layout, inv.invoice_number = src.vendor, src.layout, src.invoice_number
            inv.duplicate_of = src.file
        elif err == "line_sum_mismatch":
            inv.subtotal = round(inv.subtotal + rng.uniform(10, 120), 2)
            inv.total = round(inv.subtotal + inv.tax, 2)
    return inv


def render(inv: Invoice, path: Path, rng: random.Random) -> None:
    c = canvas.Canvas(str(path), pagesize=letter)
    w, h = letter
    ds, ms = rng.randint(0, 3), rng.randint(0, 2)
    money = lambda x: fmt_money(x, ms)  # noqa: E731
    lbl = {k: rng.choice(v) for k, v in
           {"inv": INV_LABELS, "date": DATE_LABELS, "due": DUE_LABELS, "po": PO_LABELS,
            "total": TOTAL_LABELS}.items()}
    hdr = [("inv", inv.invoice_number), ("date", fmt_date(date.fromisoformat(inv.invoice_date), ds)),
           ("due", fmt_date(date.fromisoformat(inv.due_date), ds))]
    if inv.po_number:
        hdr.append(("po", inv.po_number))
    rng.shuffle(hdr)

    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, h - 60, inv.vendor)
    c.setFont("Helvetica", 9)
    c.drawString(50, h - 74, f"{rng.randint(100, 9999)} Industrial Way, Oakland, CA 946{rng.randint(0, 21):02d}")
    y = h - 110

    if inv.layout in ("layout_table", "layout_compact", "layout_letter"):
        c.setFont("Helvetica-Bold", 12 if inv.layout != "layout_compact" else 10)
        c.drawString(50 if inv.layout != "layout_letter" else 380, y, "INVOICE")
        c.setFont("Helvetica", 10)
        for k, v in hdr:
            y -= 15
            x = 50 if inv.layout != "layout_letter" else 380
            c.drawString(x, y, f"{lbl[k]}: {v}" if not lbl[k].endswith(":") else f"{lbl[k]} {v}")
    elif inv.layout == "layout_keyvalue":
        c.setFont("Helvetica", 10)
        for k, v in hdr:
            y -= 16
            c.drawString(50, y, lbl[k].rstrip(":"))
            c.drawString(180, y, v)
    else:  # two column header block
        c.setFont("Helvetica", 10)
        for j, (k, v) in enumerate(hdr):
            col, row = j % 2, j // 2
            c.drawString(50 + col * 260, y - 16 * (row + 1), f"{lbl[k].rstrip(':')}: {v}")
        y -= 16 * ((len(hdr) + 1) // 2)

    c.drawString(50, y - 22, "Bill To: Liftech Consultants Inc., Oakland, CA")
    y -= 55
    heads = rng.choice([("Description", "Qty", "Unit Price", "Amount"),
                        ("Item", "Quantity", "Rate", "Line Total"),
                        ("Description", "QTY", "Price Each", "Ext. Price")])
    cols = [50, 330, 400, 490]
    c.setFont("Helvetica-Bold", 10)
    for x, t in zip(cols, heads, strict=True):
        c.drawString(x, y, t)
    c.line(50, y - 4, w - 50, y - 4)
    c.setFont("Helvetica", 10)
    for it in inv.items:
        y -= 16
        for x, t in zip(cols, [it.description, str(it.quantity), money(it.unit_price), money(it.amount)],
                        strict=True):
            c.drawString(x, y, t)
    c.line(50, y - 6, w - 50, y - 6)
    y -= 26
    for name, val in [("Subtotal", inv.subtotal), ("Sales Tax", inv.tax), (lbl["total"], inv.total)]:
        c.setFont("Helvetica-Bold" if name == lbl["total"] else "Helvetica", 10)
        c.drawString(380, y, f"{name}:")
        c.drawString(490, y, money(val))
        y -= 15
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(50, 60, rng.choice(["Thank you for your business.", "Net terms per agreement.",
                                     "Remit to the address above. Questions? Call our AR desk."]))
    c.save()


def generate(out: Path, n: int = 250, seed: int = 42) -> list[Invoice]:
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    invoices: list[Invoice] = []
    for i in range(n):
        inv = make_invoice(i, rng, invoices)
        render(inv, out / inv.file, rng)
        invoices.append(inv)
    truth = []
    for inv in invoices:
        d = asdict(inv)
        d["items"] = [{**asdict(it), "amount": it.amount} for it in inv.items]
        truth.append(d)
    (out / "answer_key.json").write_text(json.dumps(truth, indent=1))
    return invoices


if __name__ == "__main__":
    import sys
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "data/invoices")
    invs = generate(target)
    print(f"wrote {len(invs)} invoices to {target}, "
          f"{sum(bool(i.injected_errors) for i in invs)} with injected problems")
