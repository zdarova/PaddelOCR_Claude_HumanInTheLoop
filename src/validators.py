"""Deterministic validators for Italian accounting documents.

These run BEFORE any LLM validation — they are fast, rule-based, and
catch structural errors that don't need AI.
"""

import re
from src.table_reconstructor import ITALIAN_NUMBER_RE, _parse_italian_number, fix_italian_number

# Code pattern: 7-digit numeric OR P/E/I/M prefix
CODE_PATTERN = re.compile(r'^[0-9]{5,8}$|^[PEIMW]\d{4,7}$|^[A-Z]\d{3}\.\d{2}\.\d{3}\.\w+$')


def validate_detail_page(rows: list[list[str]], columns: list[str]) -> dict:
    """
    Validate a DETAIL_TABLE page with deterministic rules.
    Returns validation result with issues found.
    """
    issues = []
    
    if not rows or not columns:
        return {"valid": False, "issues": ["No data"], "checks": {}}

    # Find column indices
    periodo_idx = _find_col(columns, "PERIODO")
    progressivo_idx = _find_col(columns, "PROGRESSIVO")

    # Classify rows
    header_rows = []
    data_rows = []
    subtotal_rows = []  # TOTALE COMMESSA, TOTALE SUBFASE, TOTALE FASE, TOTALE ATTIVITA

    for i, row in enumerate(rows):
        row_text = " ".join(c.upper() for c in row if c)
        if "CODICE" in row_text and "DESCRIZIONE" in row_text:
            header_rows.append((i, row))
        elif any(k in row_text for k in ["TOTALE COMMESSA", "TOTALE SUBFASE", "TOTALE FASE", "TOTALE ATTIVITA"]):
            subtotal_rows.append((i, row, _get_subtotal_type(row_text)))
        elif row[0].strip() if row else False:
            data_rows.append((i, row))

    checks = {
        "column_count": len(columns) == 4,
        "has_header": len(header_rows) > 0,
        "has_data": len(data_rows) > 0,
        "has_totale_commessa": any(t == "COMMESSA" for _, _, t in subtotal_rows),
        "code_format": True,
        "numbers_valid": True,
        "subtotal_reconcile": {},
    }

    # Check 1: Code format validation
    for i, row in data_rows:
        code = row[0].strip() if row else ""
        if code and not CODE_PATTERN.match(code):
            issues.append(f"Row {i}: invalid code format '{code}'")
            checks["code_format"] = False

    # Check 2: Number format in financial columns
    for item in data_rows + [(i, r) for i, r, _ in subtotal_rows]:
        i, row = item
        for col_idx in [periodo_idx, progressivo_idx]:
            if col_idx is None or col_idx >= len(row):
                continue
            val = row[col_idx].strip()
            if val and not ITALIAN_NUMBER_RE.match(val):
                issues.append(f"Row {i}: invalid number '{val}' in col {col_idx}")
                checks["numbers_valid"] = False

    # Check 3: Subtotal reconciliation
    # Sum data rows and compare with TOTALE COMMESSA
    for sub_idx, sub_row, sub_type in subtotal_rows:
        if sub_type != "COMMESSA":
            continue  # Only validate COMMESSA subtotals (FASE/ATTIVITA span multiple commesse)
        
        # Find data rows ABOVE this subtotal (belonging to this commessa)
        commessa_data = [(i, r) for i, r in data_rows if i < sub_idx]
        # If there's a previous subtotal, only count rows after it
        prev_subtotals = [(si, sr, st) for si, sr, st in subtotal_rows if si < sub_idx]
        if prev_subtotals:
            prev_idx = max(si for si, _, _ in prev_subtotals)
            commessa_data = [(i, r) for i, r in commessa_data if i > prev_idx]

        for label, col_idx in [("periodo", periodo_idx), ("progressivo", progressivo_idx)]:
            if col_idx is None or col_idx >= len(sub_row):
                continue
            expected_str = sub_row[col_idx].strip()
            if not ITALIAN_NUMBER_RE.match(expected_str):
                continue
            expected = _parse_italian_number(expected_str)
            computed = 0.0
            for _, r in commessa_data:
                if col_idx < len(r):
                    v = r[col_idx].strip()
                    if ITALIAN_NUMBER_RE.match(v):
                        computed += _parse_italian_number(v)
            
            match = abs(computed - expected) < 0.015  # tolerance for floating point
            checks["subtotal_reconcile"][f"{sub_type}_{label}"] = {
                "computed": computed,
                "expected": expected,
                "match": match,
            }
            if not match:
                from src.table_reconstructor import _format_italian_number
                issues.append(
                    f"TOTALE {sub_type} {label}: sum={_format_italian_number(computed)} != declared={expected_str}"
                )

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "checks": checks,
        "data_rows": len(data_rows),
        "subtotal_rows": len(subtotal_rows),
    }


def validate_partner_split(rows: list[list[str]]) -> dict:
    """Validate partner split page: equity shares should sum to group total."""
    # TODO: implement when partner split extraction is built
    return {"valid": True, "issues": [], "checks": {}}


def validate_cross_page(all_pages: dict) -> dict:
    """
    Cross-page reconciliation:
    - Summary TOTALE RENDICONTO should match sum of all TOTALE ATTIVITA
    - DIFFERENZA DA FATTURARE should match invoice net amount
    """
    # TODO: implement after all page types are extracted
    return {"valid": True, "issues": [], "checks": {}}


def _find_col(columns: list[str], keyword: str) -> int | None:
    for i, col in enumerate(columns):
        if keyword in col.upper():
            return i
    return None


def _get_subtotal_type(text: str) -> str:
    if "TOTALE COMMESSA" in text:
        return "COMMESSA"
    if "TOTALE SUBFASE" in text:
        return "SUBFASE"
    if "TOTALE FASE" in text:
        return "FASE"
    if "TOTALE ATTIVITA" in text:
        return "ATTIVITA"
    return "UNKNOWN"
