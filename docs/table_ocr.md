# table_ocr.py

PaddleOCR 3.6 engine wrapper. Runs table recognition and raw OCR on page images.

## Main Function

### `extract_table(image_path: Path, page_num: int, pdf_stem: str) -> dict`

Runs OCR pipeline and returns structured page result.

## Pipeline

1. **TableRecognitionPipelineV2** — attempts structured table detection (wired/wireless table models)
2. **PaddleOCR raw fallback** — if no table structure detected, extracts all text with bounding boxes
3. **Template-aware reconstruction** — uses `table_reconstructor.py` to assign cells to columns/rows
4. **Italian number validation** — checks all financial cells match `\d{1,3}(\.\d{3})*,\d{2}` format

## Output Schema (JSON)

```json
{
  "schema_version": 3,
  "bbox_format": "paddle_polygon_4pt",
  "page_num": 7,
  "pdf_stem": "document_name",
  "image_path": "/path/to/rotated/image.png",
  "dpi": 300,
  "extraction_mode": "table" | "raw_ocr",
  "cells": [
    {
      "cell_id": 0,
      "bbox": [[x1,y1], [x2,y2], [x3,y3], [x4,y4]],
      "text": "610.923,82",
      "confidence": 0.997,
      "row_idx": null,
      "col_idx": null
    }
  ],
  "table_header": {"allegato": "...", "commessa": "..."},
  "table_columns": ["CODICE NATURA", "DESCRIZIONE NATURA", "TOTALE PERIODO", "TOTALE PROGRESSIVO"],
  "number_validation": {"valid": true, "accuracy_score": 1.0, "sum_check": {...}},
  "table_html": "",
  "modified": false
}
```

## Bounding Box Format

PaddleOCR native 4-point polygon: `[[top-left], [top-right], [bottom-right], [bottom-left]]`

Each point is `[x, y]` in pixel coordinates at the rendering DPI.

## Dependencies
- `paddleocr==3.6.0`, `paddlex[ocr]==3.6.1`, `paddlepaddle==3.2.2`

## Configuration
- `config.yaml` → `ocr.lang`, `ocr.use_angle_cls`

## Known Issues
- PaddlePaddle 3.3.0 has OneDNN bug — pinned to 3.2.2
- TableRecognitionPipelineV2 often fails on forms without clear borders → raw OCR fallback is the norm
- Set `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True` to avoid network checks
