"""Extract tables from text-selectable PDF pages using pdfplumber."""

import csv
import json
from pathlib import Path
import pdfplumber
from src.config import OCR_DIR


def extract_text_table(pdf_path: Path, page_num: int) -> dict:
    """Extract tables from a text-selectable page. Returns page_result dict."""
    OCR_DIR.mkdir(parents=True, exist_ok=True)
    stem = pdf_path.stem

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_num - 1]
        tables = page.extract_tables()

    all_cells = []
    rows_data = []

    for table in tables:
        for row_idx, row in enumerate(table):
            row_cells = []
            for col_idx, cell in enumerate(row):
                text = cell or ""
                # Emit PaddleOCR-compatible 4-point polygon bbox
                x1, y1 = col_idx * 100, row_idx * 30
                x2, y2 = (col_idx + 1) * 100, (row_idx + 1) * 30
                all_cells.append({
                    "cell_id": len(all_cells),
                    "bbox": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
                    "text": text,
                    "confidence": 1.0,
                    "row_idx": row_idx,
                    "col_idx": col_idx,
                })
                row_cells.append(text)
            rows_data.append(row_cells)

    page_result = {
        "schema_version": 3,
        "bbox_format": "paddle_polygon_4pt",
        "page_num": page_num,
        "pdf_stem": stem,
        "image_path": None,
        "dpi": None,
        "extraction_mode": "text_selectable",
        "cells": all_cells,
        "table_html": "",
        "modified": False,
    }

    # Save JSON
    json_path = OCR_DIR / f"{stem}_page_{page_num:04d}.json"
    with open(json_path, "w") as f:
        json.dump(page_result, f, indent=2)
    page_result["json_path"] = str(json_path)

    # Save CSV
    csv_path = OCR_DIR / f"{stem}_page_{page_num:04d}.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        for row in rows_data:
            writer.writerow(row)
    page_result["csv_path"] = str(csv_path)

    return page_result
