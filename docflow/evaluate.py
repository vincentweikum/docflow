"""Score the pipeline against the answer key, on clean PDFs and on scanned copies.

    python -m docflow.evaluate          # generates data if needed, writes reports/evaluation.json
"""
from __future__ import annotations

import json
from pathlib import Path

from docflow.extract import extract_pdf
from docflow.generate import generate
from docflow.scan import make_scans
from docflow.validate import Validator

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
FIELDS = ["vendor", "invoice_number", "invoice_date", "due_date", "po_number", "subtotal", "tax", "total"]
# what each injected problem should be flagged as
EXPECTED_FLAG = {"bad_total": "bad_total", "missing_po": "missing_po",
                 "due_before_invoice": "due_before_invoice", "duplicate": "duplicate_of",
                 "line_sum_mismatch": "line_sum_mismatch"}


def score(folder: Path, key: dict[str, dict]) -> dict:
    v = Validator()
    n = field_hits = item_docs_ok = 0
    per_field = dict.fromkeys(FIELDS, 0)
    caught = {e: [0, 0, 0] for e in EXPECTED_FLAG}    # [sent to review, exact reason, total]
    in_batch = {p.name for p in folder.glob("*.pdf")}
    clean_docs = clean_flagged = silent_errors = docs_with_extraction_errors = 0
    review_reasons_on_misreads: dict[str, int] = {}
    for pdf in sorted(folder.glob("*.pdf")):
        t = key[pdf.name]
        x = extract_pdf(pdf)
        r = v.check(x)
        n += 1
        wrong = [f for f in FIELDS if getattr(x, f) != t[f]]
        for f in FIELDS:
            per_field[f] += f not in wrong
        field_hits += len(FIELDS) - len(wrong)
        items_ok = [(i["quantity"], i["amount"]) for i in x.items] == \
                   [(i["quantity"], i["amount"]) for i in t["items"]]
        item_docs_ok += items_ok
        misread = bool(wrong) or not items_ok
        docs_with_extraction_errors += misread
        if misread and r.status == "approved":
            silent_errors += 1
        if misread and r.status == "review":
            for i in r.issues:
                k = i.split(":")[0]
                review_reasons_on_misreads[k] = review_reasons_on_misreads.get(k, 0) + 1
        for e in t["injected_errors"]:
            if e == "duplicate" and t["duplicate_of"] not in in_batch:
                continue        # the original isn't in this batch, so there's nothing to match
            caught[e][2] += 1
            caught[e][0] += r.status == "review"
            caught[e][1] += any(i.startswith(EXPECTED_FLAG[e]) for i in r.issues)
        if not t["injected_errors"]:
            clean_docs += 1
            clean_flagged += r.status == "review"
    return {
        "documents": n,
        "field_accuracy": field_hits / (n * len(FIELDS)),
        "per_field_accuracy": {f: c / n for f, c in per_field.items()},
        "line_items_exact_match": item_docs_ok / n,
        "docs_with_any_extraction_error": docs_with_extraction_errors,
        "silent_errors": silent_errors,
        "injected_problems": {e: {"sent_to_review": c, "exact_reason": x, "total": t}
                              for e, (c, x, t) in caught.items() if t},
        "clean_docs": clean_docs,
        "clean_docs_sent_to_review": clean_flagged,
        "review_reasons_on_misread_docs": review_reasons_on_misreads,
    }


def main() -> None:
    inv, scans = DATA / "invoices", DATA / "scanned"
    if not (inv / "answer_key.json").exists():
        generate(inv)
    if not scans.exists() or not any(scans.glob("*.pdf")):
        make_scans(inv, scans)
    key = {d["file"]: d for d in json.loads((inv / "answer_key.json").read_text())}
    report = {"clean_pdfs": score(inv, key), "scanned_pdfs_ocr": score(scans, key)}
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    (out / "evaluation.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
