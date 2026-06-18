# Output JSON Schema

Each page produces a structured JSON with both raw OCR tokens and normalized business fields.

## Per-Page Schema (`working/ocr_results/{stem}_page_{NNNN}.json`)

```json
{
  "schema_version": 4,
  "bbox_format": "paddle_polygon_4pt",
  "page_num": 7,
  "pdf_stem": "document_name",
  "page_type": "DETAIL_TABLE",
  "page_type_confidence": 0.95,

  "image_path": "/path/to/rotated/image.png",
  "dpi": 300,
  "extraction_mode": "raw_ocr",

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

  "table_header": {
    "allegato": "ALLEGATO al RENDICONTO di JOINT VENTURE...",
    "joint_venture": "JOINT VENTURE: 000706 LONGANESI",
    "tipo_contratto": "TIPO CONTRATTO: O (O = JOINT VENTURE...)",
    "attivita": "ATTIVITA': 2 Sviluppo",
    "fase": "FASE: 04 COSTRUZIONI IMPIANTI",
    "subfase": "SUBFASE: ...",
    "commessa": "COMMESSA: I706.02.041.ET1",
    "commessa_desc": "Longanesi - Rete di raccolta"
  },

  "table_columns": ["CODICE NATURA", "DESCRIZIONE NATURA", "TOTALE PERIODO", "TOTALE PROGRESSIVO"],

  "table_data": {
    "header_row": ["CODICE NATURA", "DESCRIZIONE NATURA", "TOTALE PERIODO", "TOTALE PROGRESSIVO"],
    "data_rows": [
      {"code": "7110034", "description": "Posa tratto a terra", "periodo": "0,00", "progressivo": "45,50"},
      {"code": "7215006", "description": "Viaggi e trasferte collaboratori", "periodo": "0,00", "progressivo": "290,00"}
    ],
    "subtotals": [
      {"type": "COMMESSA", "periodo": "610.923,82", "progressivo": "752.087,28"},
      {"type": "SUBFASE", "periodo": "610.923,82", "progressivo": "752.087,28"},
      {"type": "FASE", "periodo": "610.923,82", "progressivo": "752.087,28"}
    ]
  },

  "validation": {
    "number_format": {"valid": true, "accuracy_score": 1.0, "invalid_cells": []},
    "subtotal_reconcile": {
      "COMMESSA_periodo": {"computed": 610923.82, "expected": 610923.82, "match": true},
      "COMMESSA_progressivo": {"computed": 752087.28, "expected": 752087.28, "match": true}
    },
    "code_format": {"valid": true, "invalid_codes": []},
    "auto_fixed_numbers": [
      {"row": 3, "col": "TOTALE PERIODO", "original": "1.15066", "fixed": "1.150,66"}
    ]
  },

  "modified": false,
  "table_html": ""
}
```

## Cross-Page Validation (future)

```json
{
  "cross_page_validation": {
    "totale_rendiconto": {
      "summary_page": 3,
      "declared": "2.433.373,33",
      "computed_from_detail": "2.433.373,33",
      "match": true
    },
    "differenza_da_fatturare": {
      "summary_page": 3,
      "invoice_page": 2,
      "summary_value": "76.572,04",
      "invoice_net": "76.572,04",
      "match": true
    },
    "partner_split": {
      "group_total": "27.071.463,92",
      "partner_share": "9.068.940,41",
      "partner_pct": 33.5,
      "expected_pct": 33.5,
      "match": true
    }
  }
}
```
