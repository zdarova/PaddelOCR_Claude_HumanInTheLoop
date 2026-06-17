# PaddleOCR + Claude Human-in-the-Loop Table OCR

PDF table extraction pipeline for scanned Italian accounting forms using PaddleOCR 3.6, Claude Opus validation, and human-in-the-loop correction UI.

## Architecture

```
PDF (input/)
    │
    ├── Page Classification (text-selectable vs scanned)
    │
    ├── Image Processing
    │   ├── 90°/180°/270° orientation fix (dominant line analysis)
    │   ├── Baseline tilt correction (morphological text-line detection)
    │   └── Fine deskew (residual angle)
    │
    ├── PaddleOCR 3.6 (PP-OCRv5 + TableRecognitionPipelineV2)
    │   └── Raw OCR with 4-point polygon bounding boxes
    │
    ├── Template-Aware Table Reconstruction
    │   ├── Column detection from header anchors
    │   ├── Row anchoring from first-column cells
    │   └── Form metadata extraction (header fields above table)
    │
    ├── Italian Number Format Validation
    │   ├── Regex check on all financial cells (dot=thousands, comma=decimal)
    │   ├── Sum verification: data rows must match totals row
    │   └── Auto-queue low-accuracy pages for human review
    │
    ├── Claude Opus 4.8 Validation (optional)
    │   ├── Semantic number consistency check
    │   └── OCR error detection (0/O, 1/l, 5/S)
    │
    ├── Low Accuracy → Human Queue (working/queue/)
    │   └── Flask UI with bounding box overlay + inline cell editing
    │
    └── Final Output (output/)
        └── Excel: metadata header + table data, one tab per page
```

## Italian Number Format

The pipeline is designed for Italian accounting documents where:
- Dot (`.`) = thousands separator: `610.923` = 610,923
- Comma (`,`) = decimal separator: `610.923,82` = 610,923.82
- All financial values must have exactly 2 decimal places

**Any number not matching this format triggers low accuracy and human review.**

## Supported Template Structure

The default template has a header section followed by a data table:

```
[Header metadata: document type, entity info, contract type, activity, phase, subphase, reference code]

┌─────────────────┬────────────────────────────┬────────────────┬─────────────────────┐
│ Column 1        │ Column 2                   │ Column 3       │ Column 4            │
│ (Code/ID)       │ (Description)              │ (Period Total) │ (Cumulative Total)  │
├─────────────────┼────────────────────────────┼────────────────┼─────────────────────┤
│ 7110034         │ Description text            │ 0,00           │ 45,50               │
│ 7215006         │ Another description         │ 0,00           │ 290,00              │
│ ...             │ ...                        │ ...            │ ...                 │
├─────────────────┼────────────────────────────┼────────────────┼─────────────────────┤
│                 │ TOTALS ROW:                │ 610.923,82     │ 752.087,28          │
└─────────────────┴────────────────────────────┴────────────────┴─────────────────────┘
```

**Validation rule**: Sum of column 3 data values must equal the totals row value. Same for column 4.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

pip install -r requirements.txt

# Process all pages
PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True python main.py input/document.pdf

# Process specific pages
python main.py input/document.pdf --pages 7 10 15

# Skip Claude validation (faster, still does number format check)
python main.py input/document.pdf --skip-validation

# Rebuild Excel after human corrections
python main.py input/document.pdf --rebuild

# Launch correction UI
python ui_server.py
```

## Configuration

### Claude API Credentials

Priority order:
1. `.env_config` file (local development):
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ANTHROPIC_BASE_URL=https://api.anthropic.com
   ```
2. Environment variable `ANTHROPIC_API_KEY`
3. AWS Secrets Manager: `devops-agent/anthropic-api-key` (eu-west-1)

### `config.yaml`

```yaml
ocr:
  lang: "it"              # Primary language
  use_angle_cls: true
number_format:
  thousands_sep: "."
  decimal_sep: ","
validation:
  accuracy_threshold: 0.85
  claude_model: "claude-opus-4-8"
rendering:
  dpi: 300
rotation:
  max_angle: 15.0
```

## Project Structure

```
├── input/              Source PDFs
├── working/
│   ├── images/         Rendered page PNGs (300 DPI)
│   ├── rotated/        Orientation + tilt corrected images
│   ├── ocr_results/    JSON (bboxes + metadata) + CSV per page
│   └── queue/          Pages flagged for human review
├── output/             Final Excel (one tab per page)
├── src/
│   ├── pdf_classifier.py       Text-selectable vs scanned detection
│   ├── page_renderer.py        PDF → PNG at 300 DPI
│   ├── rotation_corrector.py   3-stage: 90° fix + baseline tilt + fine deskew
│   ├── table_ocr.py            PaddleOCR 3.6 engine wrapper
│   ├── table_reconstructor.py  Template-aware column/row reconstruction + validation
│   ├── text_extractor.py       pdfplumber for text-selectable pages
│   ├── claude_validator.py     LLM semantic validation
│   ├── excel_builder.py        Metadata header + table → Excel
│   └── ui_server.py            Flask UI for human correction
├── tests/
│   └── test_pipeline.py        Unit tests
├── docs/                       Module documentation (for AI agents)
├── config.yaml
├── requirements.txt
├── main.py                     CLI entry point
└── ui_server.py                UI launcher
```

## Requirements

- Python 3.10+
- PaddlePaddle 3.2.2 (CPU)
- PaddleOCR 3.6.0 + PaddleX[ocr] 3.6.1
- poppler-utils (for pdf2image: `apt install poppler-utils` / `brew install poppler`)
- 32GB RAM recommended for large PDFs

## Known Limitations

- PaddlePaddle 3.3.0 has a known OneDNN/PIR bug on CPU — use 3.2.2
- Set `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True` to skip model connectivity checks
- Template-aware reconstruction assumes 4-column layout with known header patterns
- Pages without detectable column headers fall back to adaptive Y-grouping (less accurate)
