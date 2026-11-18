from docflow.extract import extract_text
from docflow.validate import Validator

TWO_COLUMN = """Delta Crane Services
100 Industrial Way, Oakland, CA 94607
Invoice #: DEL-12345 Due Date: 05/01/2026
Billing Date: 04/01/2026 Customer PO: PO412345
Bill To: Liftech Consultants Inc., Oakland, CA
Item Quantity Rate Line Total
Shackle 25T 2 $100.00 $200.00
Field service hour L $95.00 $665.00
Subtotal: $865.00
Sales Tax: $0.00
Total Due: $865.00
"""


def test_two_fields_per_line_and_tricky_labels():
    x = extract_text(TWO_COLUMN, "t.pdf")
    assert x.vendor == "Delta Crane Services"
    assert x.invoice_number == "DEL-12345"
    assert x.invoice_date == "2026-04-01"
    assert x.due_date == "2026-05-01"          # "Total Due" must not be read as the due date
    assert x.po_number == "PO412345"
    assert x.total == 865.00


def test_ocr_quantity_repair():
    x = extract_text(TWO_COLUMN, "t.pdf")
    hour = x.items[1]
    assert hour["quantity"] == 7 and hour["repaired"]       # "L" recovered from 665 / 95
    assert not x.items[0]["repaired"]


def test_clean_invoice_is_approved():
    assert Validator().check(extract_text(TWO_COLUMN, "t.pdf")).status == "approved"


def test_validator_catches_problems():
    bad = TWO_COLUMN.replace("Total Due: $865.00", "Total Due: $965.00").replace("PO412345", "PQ412345")
    r = Validator().check(extract_text(bad, "b.pdf"))
    assert r.status == "review"
    assert "bad_total" in r.issues and "po_format" in r.issues


def test_duplicate_detection():
    v = Validator()
    v.check(extract_text(TWO_COLUMN, "a.pdf"))
    r = v.check(extract_text(TWO_COLUMN, "b.pdf"))
    assert "duplicate_of:a.pdf" in r.issues


def test_due_before_invoice():
    bad = TWO_COLUMN.replace("Due Date: 05/01/2026", "Due Date: 03/01/2026")
    assert "due_before_invoice" in Validator().check(extract_text(bad, "c.pdf")).issues
