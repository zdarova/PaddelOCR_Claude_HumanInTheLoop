# main.py

CLI entry point orchestrating the full OCR pipeline.

## Usage

```bash
python main.py <pdf_path> [--pages N N N] [--skip-validation] [--rebuild]
```

| Argument | Description |
|----------|-------------|
| `pdf_path` | Path to PDF (absolute or relative to `input/`) |
| `--pages` | Optional list of page numbers to process (default: ALL) |
| `--skip-validation` | Skip Claude API call (still runs number format check) |
| `--rebuild` | Rebuild Excel from existing OCR results (no re-processing) |

## Pipeline Stages

1. **Classify** — `pdf_classifier.classify_pages()` → text vs scanned
2. **Extract text pages** — `text_extractor.extract_text_table()` (pdfplumber)
3. **Render scanned pages** — `page_renderer.render_pages()` → PNG at 300 DPI
4. **Correct rotation** — `rotation_corrector.correct_rotation()` → 3-stage fix
5. **OCR** — `table_ocr.extract_table()` → JSON + CSV per page
6. **Number validation** — Always runs: Italian format regex + sum check
7. **Claude validation** — Optional: semantic consistency check
8. **Build Excel** — `excel_builder.build_excel()` → one tab per page

## Validation Flow

```
Number format check (always)
    │
    ├── All numbers valid + sums match → ✅ Page OK
    │
    ├── Invalid numbers or sum mismatch → ⚠️ Queue for human review
    │
    └── (if --skip-validation NOT set)
        │
        └── Claude validation → additional semantic checks
```

## Environment Variables

- `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True` — skip model download checks
- `ANTHROPIC_API_KEY` — Claude API key (alternative to .env_config/AWS)
