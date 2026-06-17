# PaddleOCR + Claude Human-in-the-Loop Table OCR

PDF table extraction pipeline for Italian Joint Venture accounting forms using PaddleOCR 3.6, Claude Opus validation, and human-in-the-loop correction.

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
    │   ├── Column detection from header anchors (CODICE NATURA, DESCRIZIONE, TOTALE PERIODO, TOTALE PROGRESSIVO)
    │   ├── Row anchoring from first-column cells
    │   └── Form metadata extraction (ALLEGATO, JV, CONTRATTO, ATTIVITA', FASE, SUBFASE, COMMESSA)
    │
    ├── Claude Opus 4.8 Validation (Italian number format aware)
    │   ├── Row sum → TOTALE COMMESSA check
    │   ├── Column sum consistency
    │   └── OCR error detection (0/O, 1/l, 5/S)
    │
    ├── Low Accuracy → Human Queue (working/queue/)
    │   └── Flask UI with bounding box overlay + inline cell editing
    │
    └── Final Output (output/)
        └── Excel: metadata header + table data, one tab per page
```

## Italian Number Format

- Dot (`.`) = thousands separator: `610.923` = 610,923
- Comma (`,`) = decimal separator: `610.923,82` = 610,923.82

## Template Structure

Each page follows the standard JV accounting form:

```
ALLEGATO al RENDICONTO di JOINT VENTURE per TITOLO MINERARIO del periodo XX / YYYY
JOINT VENTURE: XXXXXX NAME
TIPO CONTRATTO: O (O = JOINT VENTURE; A = ASSOCIAZIONE IN PARTECIPAZIONE)
ATTIVITA': X  Descrizione
FASE: XX  DESCRIZIONE FASE
SUBFASE: ...
COMMESSA: CODE  Descrizione commessa

┌─────────────────┬────────────────────────────┬────────────────┬─────────────────────┐
│ CODICE NATURA   │ DESCRIZIONE NATURA         │ TOTALE PERIODO │ TOTALE PROGRESSIVO  │
├─────────────────┼────────────────────────────┼────────────────┼─────────────────────┤
│ 7110034         │ Posa tratto a terra        │ 0,00           │ 45,50               │
│ 7215006         │ Viaggi e trasferte         │ 0,00           │ 290,00              │
│ ...             │ ...                        │ ...            │ ...                 │
├─────────────────┼────────────────────────────┼────────────────┼─────────────────────┤
│                 │ TOTALE COMMESSA:           │ 610.923,82     │ 752.087,28          │
└─────────────────┴────────────────────────────┴────────────────┴─────────────────────┘
```

**Validation rule**: Sum of all TOTALE PERIODO values must equal TOTALE COMMESSA PERIODO, same for PROGRESSIVO.

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

# Skip Claude validation (faster)
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
  lang: "it"              # Italian + English
  use_angle_cls: true
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
│   ├── table_ocr.py            PaddleOCR 3.6 (TableRecognitionPipelineV2 + fallback)
│   ├── table_reconstructor.py  Template-aware column/row detection
│   ├── text_extractor.py       pdfplumber for text-selectable pages
│   ├── claude_validator.py     Opus 4.8 numeric validation
│   ├── excel_builder.py        Metadata header + table → Excel
│   └── ui_server.py            Flask UI for human correction
├── tests/
│   └── test_pipeline.py        12 unit tests (page 7 benchmark)
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

## Dependencies Note

PaddlePaddle 3.3.0 has a known OneDNN/PIR bug on CPU. Use 3.2.2 until fixed.
Set `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True` to skip model connectivity checks.
