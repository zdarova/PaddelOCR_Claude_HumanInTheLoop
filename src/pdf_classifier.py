"""Classify PDF pages as text-selectable or scanned (image-based)."""

import pdfplumber
from pathlib import Path

# Minimum characters to consider a page text-selectable
TEXT_THRESHOLD = 50


def classify_pages(pdf_path: Path) -> dict[int, str]:
    """Return {page_num: 'text' | 'scanned'} for each page (1-indexed)."""
    results = {}
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            results[i] = "text" if len(text.strip()) >= TEXT_THRESHOLD else "scanned"
    return results
