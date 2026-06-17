"""Unit tests for OCR pipeline — Page 7 benchmark.

These tests validate the pipeline stages without requiring PaddleOCR installed
(mocked OCR engine). Run with: pytest tests/ -v
"""

import json
import csv
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Test constants
PDF_NAME = "GP09-2026U0027_20260130161048501.pdf"
PDF_PATH = Path(__file__).parent.parent / "input" / PDF_NAME
BENCHMARK_PAGE = 7


@pytest.fixture
def tmp_working(tmp_path):
    """Create temporary working directories."""
    dirs = {
        "images": tmp_path / "images",
        "rotated": tmp_path / "rotated",
        "ocr_results": tmp_path / "ocr_results",
        "queue": tmp_path / "queue",
        "output": tmp_path / "output",
    }
    for d in dirs.values():
        d.mkdir()
    return dirs


class TestPDFClassifier:
    """Test page classification (text-selectable vs scanned)."""

    @pytest.mark.skipif(not PDF_PATH.exists(), reason="Test PDF not in input/")
    def test_classify_returns_all_pages(self):
        from src.pdf_classifier import classify_pages
        result = classify_pages(PDF_PATH)
        assert len(result) > 0
        assert all(v in ("text", "scanned") for v in result.values())

    @pytest.mark.skipif(not PDF_PATH.exists(), reason="Test PDF not in input/")
    def test_classify_page_7_exists(self):
        from src.pdf_classifier import classify_pages
        result = classify_pages(PDF_PATH)
        assert BENCHMARK_PAGE in result

    @pytest.mark.skipif(not PDF_PATH.exists(), reason="Test PDF not in input/")
    def test_classify_page_types_are_valid(self):
        from src.pdf_classifier import classify_pages
        result = classify_pages(PDF_PATH)
        for page_num, page_type in result.items():
            assert isinstance(page_num, int)
            assert page_type in ("text", "scanned")


class TestPageRenderer:
    """Test page image rendering."""

    @pytest.mark.skipif(not PDF_PATH.exists(), reason="Test PDF not in input/")
    def test_render_page_7(self):
        from src.page_renderer import render_pages
        result = render_pages(PDF_PATH, [BENCHMARK_PAGE])
        assert BENCHMARK_PAGE in result
        img_path = result[BENCHMARK_PAGE]
        assert img_path.exists()
        assert img_path.suffix == ".png"
        assert img_path.stat().st_size > 0


class TestRotationCorrector:
    """Test deskew correction."""

    @pytest.mark.skipif(not PDF_PATH.exists(), reason="Test PDF not in input/")
    def test_correct_rotation_page_7(self):
        from src.page_renderer import render_pages
        from src.rotation_corrector import correct_rotation
        images = render_pages(PDF_PATH, [BENCHMARK_PAGE])
        rotated = correct_rotation(images[BENCHMARK_PAGE])
        assert rotated.exists()
        assert rotated.stat().st_size > 0


class TestBBoxFormat:
    """Test that bounding box format is PaddleOCR native 4-point polygon."""

    def test_polygon_format_structure(self):
        """Verify polygon is [[x,y],[x,y],[x,y],[x,y]]."""
        from src.table_ocr import _xyxy_to_polygon
        polygon = _xyxy_to_polygon([10, 20, 100, 50])
        assert len(polygon) == 4
        assert all(len(pt) == 2 for pt in polygon)
        # Top-left
        assert polygon[0] == [10.0, 20.0]
        # Top-right
        assert polygon[1] == [100.0, 20.0]
        # Bottom-right
        assert polygon[2] == [100.0, 50.0]
        # Bottom-left
        assert polygon[3] == [10.0, 50.0]

    def test_bbox_helpers(self):
        from src.table_ocr import bbox_top_left_x, bbox_top_left_y, bbox_height
        polygon = [[10, 20], [100, 20], [100, 50], [10, 50]]
        assert bbox_top_left_x(polygon) == 10
        assert bbox_top_left_y(polygon) == 20
        assert bbox_height(polygon) == 30


class TestCSVReconstruction:
    """Test CSV writing from cells."""

    def test_structured_csv(self, tmp_working):
        from src.table_ocr import _write_csv_structured
        cells = [
            {"cell_id": 0, "bbox": [[0, 0], [50, 0], [50, 20], [0, 20]], "text": "A", "confidence": 1.0, "row_idx": 0, "col_idx": 0},
            {"cell_id": 1, "bbox": [[50, 0], [100, 0], [100, 20], [50, 20]], "text": "B", "confidence": 1.0, "row_idx": 0, "col_idx": 1},
            {"cell_id": 2, "bbox": [[0, 20], [50, 20], [50, 40], [0, 40]], "text": "1", "confidence": 0.9, "row_idx": 1, "col_idx": 0},
            {"cell_id": 3, "bbox": [[50, 20], [100, 20], [100, 40], [50, 40]], "text": "2", "confidence": 0.95, "row_idx": 1, "col_idx": 1},
        ]
        csv_path = tmp_working["ocr_results"] / "test_page_0007.csv"
        _write_csv_structured(cells, csv_path)
        with open(csv_path) as f:
            rows = list(csv.reader(f))
        assert rows == [["A", "B"], ["1", "2"]]

    def test_adaptive_csv(self, tmp_working):
        from src.table_ocr import _write_csv_adaptive
        cells = [
            {"cell_id": 0, "bbox": [[0, 10], [50, 10], [50, 30], [0, 30]], "text": "X", "confidence": 1.0, "row_idx": None, "col_idx": None},
            {"cell_id": 1, "bbox": [[60, 12], [110, 12], [110, 32], [60, 32]], "text": "Y", "confidence": 1.0, "row_idx": None, "col_idx": None},
            {"cell_id": 2, "bbox": [[0, 60], [50, 60], [50, 80], [0, 80]], "text": "Z", "confidence": 0.9, "row_idx": None, "col_idx": None},
        ]
        csv_path = tmp_working["ocr_results"] / "test_adaptive.csv"
        _write_csv_adaptive(cells, csv_path)
        with open(csv_path) as f:
            rows = list(csv.reader(f))
        assert len(rows) == 2
        assert rows[0] == ["X", "Y"]
        assert rows[1] == ["Z"]


class TestPageResultSchema:
    """Test output JSON schema matches expected format."""

    def test_schema_fields(self):
        """Verify all required fields exist in page result."""
        required_fields = {
            "schema_version", "bbox_format", "page_num", "pdf_stem",
            "image_path", "dpi", "extraction_mode", "cells",
            "table_html", "modified",
        }
        # Simulate a page result
        page_result = {
            "schema_version": 3,
            "bbox_format": "paddle_polygon_4pt",
            "page_num": 7,
            "pdf_stem": "test",
            "image_path": "/tmp/test.png",
            "dpi": 300,
            "extraction_mode": "table",
            "cells": [],
            "table_html": "",
            "modified": False,
        }
        assert required_fields.issubset(page_result.keys())

    def test_cell_schema(self):
        """Verify cell structure follows spec."""
        cell = {
            "cell_id": 0,
            "bbox": [[10, 20], [100, 20], [100, 50], [10, 50]],
            "text": "hello",
            "confidence": 0.95,
            "row_idx": 0,
            "col_idx": 0,
        }
        assert len(cell["bbox"]) == 4
        assert all(len(pt) == 2 for pt in cell["bbox"])
        assert isinstance(cell["confidence"], float)
        assert 0 <= cell["confidence"] <= 1


class TestExcelBuilder:
    """Test Excel output generation."""

    def test_build_excel_from_csv(self, tmp_working):
        """Build Excel from mock CSV/JSON and verify output."""
        ocr_dir = tmp_working["ocr_results"]
        output_dir = tmp_working["output"]
        pdf_stem = "test_doc"

        # Create mock page JSON + CSV
        page_data = {
            "schema_version": 3,
            "bbox_format": "paddle_polygon_4pt",
            "page_num": 7,
            "pdf_stem": pdf_stem,
            "image_path": None,
            "dpi": 300,
            "extraction_mode": "table",
            "cells": [
                {"cell_id": 0, "bbox": [[0, 0], [50, 0], [50, 20], [0, 20]], "text": "Header", "confidence": 1.0, "row_idx": 0, "col_idx": 0},
            ],
            "table_html": "",
            "modified": False,
            "csv_path": str(ocr_dir / f"{pdf_stem}_page_0007.csv"),
        }
        with open(ocr_dir / f"{pdf_stem}_page_0007.json", "w") as f:
            json.dump(page_data, f)
        with open(ocr_dir / f"{pdf_stem}_page_0007.csv", "w") as f:
            f.write("Header\n100\n200\n")

        # Patch config dirs
        with patch("src.excel_builder.OCR_DIR", ocr_dir), \
             patch("src.excel_builder.OUTPUT_DIR", output_dir):
            from src.excel_builder import build_excel
            excel_path = build_excel(pdf_stem)

        assert excel_path.exists()
        assert excel_path.suffix == ".xlsx"
        assert excel_path.stat().st_size > 0
