# page_renderer.py

Converts scanned PDF pages to PNG images at configurable DPI for OCR processing.

## Function

### `render_pages(pdf_path: Path, page_numbers: list[int]) -> dict[int, Path]`

Renders specified pages to PNG. Returns `{page_num: output_image_path}`.

**Output**: `working/images/{pdf_stem}_page_{NNNN}.png`

## Configuration
- `config.yaml` → `rendering.dpi` (default: 300)

## Dependencies
- `pdf2image` (requires `poppler-utils` system package)

## Notes
- Higher DPI = better OCR accuracy but larger files and slower processing
- 300 DPI is standard for document OCR
- Each page image is ~1-2MB at 300 DPI for A4
