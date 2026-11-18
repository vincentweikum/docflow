"""Run a folder of invoices through extraction and validation and write clean tables.

    python -m docflow.pipeline data/invoices out/

Writes invoices.csv, line_items.csv, review_queue.csv and run_summary.json.
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

import pandas as pd

from docflow.extract import extract_pdf
from docflow.validate import Validator


def run(src: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    v = Validator()
    heads, lines, queue = [], [], []
    t0 = time.perf_counter()
    for pdf in sorted(src.glob("*.pdf")):
        x = extract_pdf(pdf)
        r = v.check(x)
        heads.append({"file": x.file, "vendor": x.vendor, "invoice_number": x.invoice_number,
                      "invoice_date": x.invoice_date, "due_date": x.due_date, "po_number": x.po_number,
                      "subtotal": x.subtotal, "tax": x.tax, "total": x.total, "n_items": len(x.items),
                      "method": x.method, "status": r.status, "issues": ";".join(r.issues)})
        lines += [{"file": x.file, "line": i + 1, **it} for i, it in enumerate(x.items)]
        if r.status == "review":
            queue.append({"file": x.file, "vendor": x.vendor, "invoice_number": x.invoice_number,
                          "total": x.total, "issues": ";".join(r.issues)})
    secs = time.perf_counter() - t0
    pd.DataFrame(heads).to_csv(out / "invoices.csv", index=False)
    pd.DataFrame(lines).to_csv(out / "line_items.csv", index=False)
    pd.DataFrame(queue, columns=["file", "vendor", "invoice_number", "total", "issues"]).to_csv(
        out / "review_queue.csv", index=False)
    reasons = Counter(i.split(":")[0] for q in queue for i in q["issues"].split(";"))
    summary = {"documents": len(heads), "approved": len(heads) - len(queue), "review": len(queue),
               "ocr_documents": sum(h["method"] == "ocr" for h in heads),
               "line_items": len(lines), "seconds": round(secs, 1), "review_reasons": dict(reasons)}
    (out / "run_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    src, out = Path(sys.argv[1]), Path(sys.argv[2] if len(sys.argv) > 2 else "out")
    print(json.dumps(run(src, out), indent=2))
