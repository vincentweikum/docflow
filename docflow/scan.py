"""Make 'scanned' copies of invoices: rasterize, rotate a little, add noise, save as image-only PDFs.

These have no text layer, so the pipeline has to OCR them. The extractor was written
against the clean PDFs only, which makes the scanned set an honest held-out test.
"""
from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageFilter


def scan_like(pdf: Path, out: Path, rng: random.Random, dpi: int = 150) -> None:
    page = pdfium.PdfDocument(str(pdf))[0]
    img = page.render(scale=dpi / 72).to_pil().convert("L")
    img = img.rotate(rng.uniform(-1.5, 1.5), resample=Image.BICUBIC, expand=True, fillcolor=255)
    arr = np.asarray(img, dtype=np.int16)
    noise = np.random.default_rng(rng.randint(0, 10**6)).normal(0, rng.uniform(6, 18), arr.shape)
    arr = np.clip(arr + noise + rng.uniform(-15, 0), 0, 255).astype(np.uint8)
    img = Image.fromarray(arr).filter(ImageFilter.GaussianBlur(rng.uniform(0.2, 0.7)))
    img.save(out, "PDF", resolution=dpi)


def make_scans(src: Path, dst: Path, seed: int = 7, share: float = 0.3) -> list[str]:
    dst.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    picked = sorted(p for p in src.glob("*.pdf") if rng.random() < share)
    for p in picked:
        scan_like(p, dst / p.name, rng)
    return [p.name for p in picked]
