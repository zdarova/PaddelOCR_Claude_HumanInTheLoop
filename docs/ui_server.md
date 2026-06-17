# ui_server.py

Flask web application for human-in-the-loop correction of low-accuracy OCR pages.

## Endpoints

| Route | Method | Purpose |
|-------|--------|---------|
| `/` | GET | Queue list — shows all pages pending review |
| `/review/<filename>` | GET | Page review UI with bounding box overlay |
| `/api/page/<filename>` | GET | JSON data for a queued page |
| `/api/image/<name>` | GET | Serve page image for overlay |
| `/api/save` | POST | Save corrected cells |
| `/api/rebuild/<pdf_stem>` | POST | Rebuild Excel after corrections |

## UI Features

- **Bounding box overlay**: PaddleOCR polygon bboxes rendered on the page image
- **Inline cell editing**: Click a bounding box → editor panel scrolls to that cell
- **Confidence display**: Shows OCR confidence per cell (low confidence highlighted)
- **Modified flag**: Saved corrections set `modified: true` in JSON
- **Accuracy score**: Color-coded (red < 50%, orange < 85%, green ≥ 85%)

## Security
- Binds to `127.0.0.1` only (localhost)
- `debug=False` (no Werkzeug debugger)
- No Claude API key loaded in the UI process
- No authentication (single-user localhost tool)

## Configuration
- `config.yaml` → `ui.host` (default: `127.0.0.1`)
- `config.yaml` → `ui.port` (default: 5000)

## Launch
```bash
python ui_server.py
# Opens at http://127.0.0.1:5000
```

## Workflow
1. Run pipeline → pages below accuracy threshold go to `working/queue/`
2. Launch UI → review and correct cells
3. Save corrections → JSON updated with `modified: true`, CSV rebuilt
4. Run `python main.py input/doc.pdf --rebuild` → Excel regenerated with corrections
