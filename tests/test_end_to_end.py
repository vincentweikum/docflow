"""Generate a small batch, run the pipeline, and check it against the answer key."""
import json

from docflow.generate import generate
from docflow.pipeline import run


def test_pipeline_on_generated_batch(tmp_path):
    invs = generate(tmp_path / "in", n=40, seed=3)
    summary = run(tmp_path / "in", tmp_path / "out")
    assert summary["documents"] == 40
    expected_review = sum(bool(i.injected_errors) for i in invs)
    assert summary["review"] == expected_review
    key = {d["file"]: d for d in json.loads((tmp_path / "in" / "answer_key.json").read_text())}
    import pandas as pd
    out = pd.read_csv(tmp_path / "out" / "invoices.csv")
    for row in out.itertuples():
        assert row.total == key[row.file]["total"]
