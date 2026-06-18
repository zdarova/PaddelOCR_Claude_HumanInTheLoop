"""PaddleOCR 3.6 table extraction via PPStructureV3 + PaddleOCR fallback.

Bounding box format: PaddleOCR native 4-point polygon
  [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
  = [top-left, top-right, bottom-right, bottom-left]
"""

import json
import csv
import re
from pathlib import Path
from src.config import OCR_DIR, CONFIG

SCHEMA_VERSION = 3
BBOX_FORMAT = "paddle_polygon_4pt"

_ocr_engine = None
_structure_engine = None


def _get_ocr():
    """PaddleOCR 3.6 — text detection + recognition (Italian + English)."""
    global _ocr_engine
    if _ocr_engine is None:
        from paddleocr import PaddleOCR
        cfg = CONFIG["ocr"]
        _ocr_engine = PaddleOCR(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=cfg["use_angle_cls"],
            lang=cfg["lang"],
        )
    return _ocr_engine


def _get_structure_engine():
    """TableRecognitionPipelineV2 — focused table recognition (no full layout)."""
    global _structure_engine
    if _structure_engine is None:
        from paddleocr import TableRecognitionPipelineV2
        cfg = CONFIG["ocr"]
        _structure_engine = TableRecognitionPipelineV2(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_layout_detection=False,
        )
    return _structure_engine


def _xyxy_to_polygon(bbox: list) -> list[list[float]]:
    """Convert [x1,y1,x2,y2] to 4-point polygon [[tl],[tr],[br],[bl]]."""
    x1, y1, x2, y2 = [float(v) for v in bbox[:4]]
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def bbox_top_left_y(polygon: list[list[float]]) -> float:
    return polygon[0][1]


def bbox_top_left_x(polygon: list[list[float]]) -> float:
    return polygon[0][0]


def bbox_height(polygon: list[list[float]]) -> float:
    return abs(polygon[3][1] - polygon[0][1])


def extract_table(image_path: Path, page_num: int, pdf_stem: str) -> dict:
    """
    Run PPStructureV3 on a page image.
    Falls back to PaddleOCR raw text detection if no table is found.
    Saves JSON (bounding boxes) + CSV per page.
    """
    OCR_DIR.mkdir(parents=True, exist_ok=True)
    dpi = CONFIG["rendering"]["dpi"]

    all_cells = []
    table_html = ""
    extraction_mode = "table"

    # --- PPStructureV3 pipeline ---
    engine = _get_structure_engine()
    results = engine.predict(str(image_path))

    for result in results:
        # PPStructureV3 returns a result object per page with layout_parsing_result
        if hasattr(result, "keys"):
            res_dict = result
        else:
            res_dict = result.to_dict() if hasattr(result, "to_dict") else {}

        # Extract table blocks from layout parsing
        blocks = res_dict.get("layout_parsing_result", [])
        if isinstance(blocks, dict):
            blocks = blocks.get("parsing_result", [])

        for block in blocks:
            if not isinstance(block, dict):
                continue
            block_type = block.get("block_type", block.get("type", ""))
            if "table" in block_type.lower():
                table_html = block.get("html", block.get("table_html", ""))
                # Extract cells from table block
                cells_data = block.get("cell_boxes", block.get("cells", []))
                for i, cell in enumerate(cells_data):
                    if isinstance(cell, dict):
                        bbox = cell.get("bbox", cell.get("box", [0, 0, 0, 0]))
                        text = cell.get("text", cell.get("content", ""))
                        conf = cell.get("confidence", cell.get("score", 1.0))
                        row_idx = cell.get("row_idx", cell.get("row", None))
                        col_idx = cell.get("col_idx", cell.get("col", None))
                    elif isinstance(cell, (list, tuple)) and len(cell) >= 4:
                        bbox = cell[:4]
                        text = ""
                        conf = 1.0
                        row_idx = None
                        col_idx = None
                    else:
                        continue

                    # Normalize bbox to polygon
                    if bbox and isinstance(bbox[0], (list, tuple)):
                        polygon = [[float(p[0]), float(p[1])] for p in bbox]
                    else:
                        polygon = _xyxy_to_polygon(bbox)

                    all_cells.append({
                        "cell_id": len(all_cells),
                        "bbox": polygon,
                        "text": str(text),
                        "confidence": float(conf),
                        "row_idx": row_idx,
                        "col_idx": col_idx,
                    })

        # Also try OCR text blocks if present (non-table text on page)
        if not all_cells:
            ocr_results = res_dict.get("ocr_result", res_dict.get("dt_polys", []))
            if ocr_results:
                for i, item in enumerate(ocr_results):
                    if isinstance(item, dict):
                        bbox = item.get("dt_polys", item.get("box", []))
                        text = item.get("rec_text", item.get("text", ""))
                        conf = item.get("rec_score", item.get("score", 1.0))
                    elif isinstance(item, (list, tuple)) and len(item) == 2:
                        bbox, (text, conf) = item[0], item[1]
                    else:
                        continue
                    if bbox and isinstance(bbox[0], (list, tuple)):
                        polygon = [[float(p[0]), float(p[1])] for p in bbox]
                    else:
                        polygon = _xyxy_to_polygon(bbox) if len(bbox) >= 4 else [[0, 0]] * 4
                    all_cells.append({
                        "cell_id": i,
                        "bbox": polygon,
                        "text": str(text),
                        "confidence": float(conf) if conf else 1.0,
                        "row_idx": None,
                        "col_idx": None,
                    })

    # --- Fallback: raw PaddleOCR if PPStructureV3 found nothing ---
    if not all_cells:
        extraction_mode = "raw_ocr"
        ocr = _get_ocr()
        ocr_results = ocr.predict(str(image_path))
        for result in ocr_results:
            if hasattr(result, "keys"):
                res_dict = result
            else:
                res_dict = result.to_dict() if hasattr(result, "to_dict") else {}

            dt_polys = res_dict.get("dt_polys", [])
            rec_texts = res_dict.get("rec_texts", [])
            rec_scores = res_dict.get("rec_scores", [])

            for i in range(len(dt_polys)):
                polygon = [[float(p[0]), float(p[1])] for p in dt_polys[i]]
                text = rec_texts[i] if i < len(rec_texts) else ""
                conf = rec_scores[i] if i < len(rec_scores) else 1.0
                all_cells.append({
                    "cell_id": i,
                    "bbox": polygon,
                    "text": str(text),
                    "confidence": float(conf),
                    "row_idx": None,
                    "col_idx": None,
                })

    page_result = {
        "schema_version": SCHEMA_VERSION,
        "bbox_format": BBOX_FORMAT,
        "page_num": page_num,
        "pdf_stem": pdf_stem,
        "image_path": str(image_path),
        "dpi": dpi,
        "extraction_mode": extraction_mode,
        "cells": all_cells,
        "table_html": table_html,
        "modified": False,
    }

    # Save JSON (initial, will be updated after reconstruction)
    json_path = OCR_DIR / f"{pdf_stem}_page_{page_num:04d}.json"
    page_result["json_path"] = str(json_path)

    # Save CSV — prefer structural row/col, then spatial clustering, fallback to adaptive Y
    csv_path = OCR_DIR / f"{pdf_stem}_page_{page_num:04d}.csv"
    if extraction_mode == "table" and any(c.get("row_idx") is not None for c in all_cells):
        _write_csv_structured(all_cells, csv_path)
    else:
        from src.table_reconstructor import reconstruct_table, write_table_csv, validate_italian_numbers
        result = reconstruct_table(all_cells)
        if result["rows"] and len(result["rows"][0]) > 1:
            write_table_csv(result["rows"], csv_path)
            page_result["table_header"] = result["header"]
            page_result["table_columns"] = result["columns"]
            # Validate Italian number format + sum check
            num_validation = validate_italian_numbers(result)
            page_result["number_validation"] = num_validation
            if not num_validation["valid"]:
                page_result["accuracy_score"] = num_validation["accuracy_score"]
                page_result["validation_notes"] = (
                    f"Number format issues: {len(num_validation['invalid_cells'])} invalid cells. "
                    + "; ".join(f"{e['col']}: '{e['value']}' ({e['reason']})" for e in num_validation["invalid_cells"][:5])
                )
        else:
            _write_csv_adaptive(all_cells, csv_path)
    page_result["csv_path"] = str(csv_path)

    # Save final JSON with all enrichment (table_header, table_columns, csv_path, validation)
    with open(json_path, "w") as f:
        json.dump(page_result, f, indent=2)

    return page_result


def _write_csv_structured(cells: list[dict], csv_path: Path):
    """Write CSV using native row/col indices from table structure."""
    if not cells:
        csv_path.write_text("")
        return
    max_row = max((c["row_idx"] for c in cells if c.get("row_idx") is not None), default=0)
    max_col = max((c["col_idx"] for c in cells if c.get("col_idx") is not None), default=0)
    grid = [["" for _ in range(max_col + 1)] for _ in range(max_row + 1)]
    for c in cells:
        r, col = c.get("row_idx"), c.get("col_idx")
        if r is not None and col is not None:
            grid[r][col] = c["text"]
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        for row in grid:
            writer.writerow(row)


def _write_csv_adaptive(cells: list[dict], csv_path: Path):
    """Reconstruct rows using adaptive Y-tolerance (fraction of median cell height)."""
    if not cells:
        csv_path.write_text("")
        return
    sorted_cells = sorted(cells, key=lambda c: (bbox_top_left_y(c["bbox"]), bbox_top_left_x(c["bbox"])))

    heights = [bbox_height(c["bbox"]) for c in sorted_cells]
    heights = [h for h in heights if h > 0]
    median_h = sorted(heights)[len(heights) // 2] if heights else 30
    y_tolerance = max(10, median_h * 0.4)

    rows = []
    current_row = [sorted_cells[0]]
    for cell in sorted_cells[1:]:
        if abs(bbox_top_left_y(cell["bbox"]) - bbox_top_left_y(current_row[0]["bbox"])) < y_tolerance:
            current_row.append(cell)
        else:
            rows.append(sorted(current_row, key=lambda c: bbox_top_left_x(c["bbox"])))
            current_row = [cell]
    rows.append(sorted(current_row, key=lambda c: bbox_top_left_x(c["bbox"])))

    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        for row in rows:
            writer.writerow([c["text"] for c in row])
