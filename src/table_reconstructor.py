"""Template-aware table reconstruction for Italian JV accounting forms.

Strategy: 
1. Find header row by matching known column names
2. Use header X-positions as column anchors
3. Assign all cells below the header to columns based on X-proximity to anchors
4. Group into rows by Y-proximity

Expected columns: CODICE NATURA | DESCRIZIONE NATURA | TOTALE PERIODO | TOTALE PROGRESSIVO
"""

import csv
import re
from pathlib import Path

# Known header patterns for column detection
COLUMN_HEADERS = [
    "CODICE NATURA",
    "DESCRIZIONE NATURA", 
    "TOTALE PERIODO",
    "TOTALE PROGRESSIVO",
]

# Italian number format: optional sign + thousands dots + comma + 2 decimals
# Valid: 0,00 | 45,50 | 4.152,96 | 610.923,82 | 7.296.050,00 | 1.800.100,00- (trailing minus)
ITALIAN_NUMBER_RE = re.compile(r'^-?\d{1,3}(\.\d{3})*,\d{2}-?$')


# --- NUMBER AUTO-FIX HEURISTICS ---

def fix_italian_number(s: str) -> tuple[str, bool]:
    """
    Attempt to auto-fix OCR errors in Italian numbers.
    Returns (fixed_value, was_modified).
    If already valid, returns unchanged.
    """
    s = s.strip().replace(" ", "")
    if not s or not any(ch.isdigit() for ch in s):
        return s, False
    if ITALIAN_NUMBER_RE.match(s):
        return s, False  # already valid

    original = s
    # Preserve trailing minus (Italian negative notation)
    trailing_minus = s.endswith("-")
    if trailing_minus:
        s = s[:-1]

    # H3: Last dot-separated segment is exactly 2 digits → comma misread as dot
    # e.g. '1.150.66' → '1.150,66' or '12.50' → '12,50'
    m = re.match(r'^(\d[\d.]*)\.([\d]{2})$', s)
    if m:
        s = m.group(1) + "," + m.group(2)

    # H1: Last dot-group has >3 digits → last 2 are decimals (comma missed)
    # e.g. '1.15066' → '1.150,66' or '98.65378' → '98.653,78'
    if "," not in s:
        m = re.match(r'^(\d{1,3}(?:\.\d{3})*\.)(\d{4,})$', s)
        if m:
            prefix, tail = m.group(1), m.group(2)
            # Rebuild: tail minus last 2 = thousands part, last 2 = decimals
            int_tail = tail[:-2]
            dec = tail[-2:]
            # Re-apply thousands dots to int_tail
            int_tail_dotted = _add_thousands_dots(int_tail)
            s = prefix + int_tail_dotted + "," + dec
            # Clean double dots
            s = re.sub(r'\.+', '.', s)
            s = s.lstrip('.')

    # H2: Pure digits, no separators → insert comma before last 2
    # e.g. '115066' → '1.150,66' or '9900' → '99,00'
    if "," not in s and "." not in s and re.match(r'^\d+$', s) and len(s) >= 3:
        int_part = s[:-2]
        dec_part = s[-2:]
        int_part = _add_thousands_dots(int_part) if int_part else "0"
        s = f"{int_part},{dec_part}"

    # H4: Number like '5.792.47244' → '5.792.472,44' (last group > 3 digits)
    if "," not in s and "." in s:
        parts = s.split(".")
        if len(parts[-1]) > 3:
            last = parts[-1]
            parts[-1] = last[:-2]
            s = ".".join(parts) + "," + last[-2:]

    # Re-add trailing minus
    if trailing_minus:
        s = s + "-"

    was_modified = s != original
    return s, was_modified


def _add_thousands_dots(s: str) -> str:
    """Add thousands dots to an integer string: '1150' → '1.150'"""
    if len(s) <= 3:
        return s
    result = []
    for i, ch in enumerate(reversed(s)):
        if i > 0 and i % 3 == 0:
            result.append(".")
        result.append(ch)
    return "".join(reversed(result))


def reconstruct_table(cells: list[dict]) -> dict:
    """
    Template-aware reconstruction: detect columns from headers, then assign data cells.
    Returns dict with:
      - 'header': dict of form metadata (ALLEGATO, JV, CONTRATTO, ATTIVITA, FASE, SUBFASE, COMMESSA)
      - 'columns': list of column names
      - 'rows': list of data rows (4 columns each)
    """
    if not cells:
        return {"header": {}, "columns": [], "rows": []}

    # Step 1: Find header cells and their X positions
    col_anchors = _find_column_anchors(cells)

    # FALLBACK: if no header anchors found, infer columns from data X-positions
    # Only if page looks like a detail table (has numeric codes in left column)
    if not col_anchors or len(col_anchors) < 3:
        # Check if this looks like a detail table (has line-item codes at left edge)
        left_codes = [c for c in cells if c["bbox"][0][0] < 300 and c["bbox"][0][1] > 450
                      and (c["text"].strip().isdigit() or c["text"].strip().startswith("P"))]
        if len(left_codes) >= 2:
            col_anchors = _infer_columns_from_data(cells)

    if not col_anchors or len(col_anchors) < 3:
        return {"header": {}, "columns": [], "rows": []}

    # Step 2: Extract form metadata from cells above the table header
    header_y = min(a["y"] for a in col_anchors.values())
    # If columns were inferred (no header row), use Y=450 as metadata cutoff
    if header_y > 450 and not _find_column_anchors(cells):
        header_y = 450.0
    metadata = _extract_metadata(cells, header_y)

    # Step 3: Get only cells at/below the header (the table body)
    table_cells = [c for c in cells if c["bbox"][0][1] >= header_y]

    # Step 4: Assign each table cell to a column
    col_positions = {name: anchor["x"] for name, anchor in col_anchors.items()}

    # Step 5: Group cells into rows and assign columns
    rows = _build_rows(table_cells, col_positions)

    return {
        "header": metadata,
        "columns": sorted(col_anchors.keys(), key=lambda n: col_anchors[n]["x"]),
        "rows": rows,
    }


def _extract_metadata(cells: list[dict], header_y: float) -> dict:
    """Extract form header metadata from cells above the table."""
    meta = {}
    for c in cells:
        if c["bbox"][0][1] >= header_y:
            continue
        text = c["text"].strip()
        text_upper = text.upper()

        if "ALLEGATO" in text_upper and "RENDICONTO" in text_upper:
            meta["allegato"] = text
        elif text_upper.startswith("JOINT VENTURE:") or (text_upper.startswith("JOINT VENTURE") and ":" not in text_upper and "O" in text_upper):
            meta["joint_venture"] = text
        elif "JOINT VENTURE" in text_upper and "TIPO" not in text_upper and "ALLEGATO" not in text_upper:
            meta.setdefault("joint_venture", text)
        elif text_upper.startswith("TIPO CONTRATTO"):
            meta["tipo_contratto"] = text
        elif text_upper.startswith("ATTIVITA"):
            meta["attivita"] = text
        elif text_upper.startswith("FASE:"):
            meta["fase"] = text
        elif text_upper.startswith("SUBFASE"):
            meta["subfase"] = text
        elif text_upper.startswith("COMMESSA:"):
            meta["commessa"] = text
        elif "commessa" in meta and c["bbox"][0][0] > 800 and c["bbox"][0][1] > meta.get("_commessa_y", 0):
            # Commessa description (to the right of COMMESSA: label)
            meta["commessa_desc"] = text

        # Track commessa Y for description detection
        if text_upper.startswith("COMMESSA:"):
            meta["_commessa_y"] = c["bbox"][0][1]

    meta.pop("_commessa_y", None)
    return meta


def _find_column_anchors(cells: list[dict]) -> dict[str, dict]:
    """
    Find column header cells by matching text patterns.
    Returns {column_name: {"x": x_left, "y": y_top}} for each found header.
    """
    anchors = {}

    for c in cells:
        text = c["text"].strip().upper()
        x_left = c["bbox"][0][0]
        y_top = c["bbox"][0][1]

        if text == "CODICE NATURA" or (text == "CODICE" and "CODICE NATURA" not in anchors):
            anchors["CODICE NATURA"] = {"x": x_left, "y": y_top}
        elif text == "DESCRIZIONE NATURA":
            anchors["DESCRIZIONE NATURA"] = {"x": x_left, "y": y_top}
        elif text == "TOTALE PERIODO":
            anchors["TOTALE PERIODO"] = {"x": x_left, "y": y_top}
        elif text == "TOTALE PROGRESSIVO":
            anchors["TOTALE PROGRESSIVO"] = {"x": x_left, "y": y_top}
        elif text == "TOTALE" or text == "TOTALE ":
            # Split header: "TOTALE" alone — only use as PROGRESSIVO if
            # TOTALE PERIODO already found at a different X
            if "TOTALE PERIODO" in anchors and x_left > anchors["TOTALE PERIODO"]["x"] + 200:
                anchors["TOTALE PROGRESSIVO"] = {"x": x_left, "y": y_top}
        elif text == "PROGRESSIVO":
            anchors["TOTALE PROGRESSIVO"] = {"x": x_left, "y": y_top}

    return anchors


def _infer_columns_from_data(cells: list[dict]) -> dict[str, dict]:
    """
    Fallback: infer 4-column layout from X-position clustering of data cells.
    Used when standard header row is missing (continuation pages).
    
    Expected X-zones for this document family:
      Col 1 (Code):        X ~  40-400
      Col 2 (Description): X ~ 500-1500
      Col 3 (Period):      X ~ 2100-2500
      Col 4 (Progressive): X ~ 2600-3100
    """
    if not cells:
        return {}

    # Collect left-edge X positions of cells below the metadata area (Y > 450)
    data_cells = [c for c in cells if c["bbox"][0][1] > 450]
    if len(data_cells) < 6:
        return {}

    x_lefts = sorted(c["bbox"][0][0] for c in data_cells)
    page_width = max(c["bbox"][1][0] for c in cells)

    # Find large X-gaps to identify column boundaries
    unique_xs = sorted(set(int(x) for x in x_lefts))
    if len(unique_xs) < 4:
        return {}

    gaps = []
    for i in range(1, len(unique_xs)):
        gap = unique_xs[i] - unique_xs[i-1]
        if gap > page_width * 0.05:  # significant gap (>5% of page width)
            gaps.append((gap, unique_xs[i-1], unique_xs[i]))

    gaps.sort(key=lambda g: g[0], reverse=True)

    # We need at least 3 gaps to separate 4 columns
    if len(gaps) < 3:
        # Try with lower threshold
        gaps = [(unique_xs[i] - unique_xs[i-1], unique_xs[i-1], unique_xs[i])
                for i in range(1, len(unique_xs))
                if unique_xs[i] - unique_xs[i-1] > page_width * 0.03]
        gaps.sort(key=lambda g: g[0], reverse=True)

    if len(gaps) < 3:
        return {}

    # Take top 3 gaps as column separators
    separators = sorted([g[2] for g in gaps[:3]])  # X positions where new columns start

    # Map to known column names based on X-position ranges
    # First column center < 500, second < 2000, third < 2600, fourth > 2600
    anchors = {}
    col_starts = [unique_xs[0]] + separators

    for i, x_start in enumerate(col_starts):
        if i == 0:
            anchors["CODICE NATURA"] = {"x": float(x_start), "y": 500.0}
        elif i == 1 and x_start < 1500:
            anchors["DESCRIZIONE NATURA"] = {"x": float(x_start), "y": 500.0}
        elif i == 2 or (i == 1 and x_start > 1500):
            anchors["TOTALE PERIODO"] = {"x": float(x_start), "y": 500.0}
        elif i == 3 or (i == 2 and x_start > 2500):
            anchors["TOTALE PROGRESSIVO"] = {"x": float(x_start), "y": 500.0}

    # Ensure we have at least 3 columns
    if len(anchors) < 3:
        return {}

    return anchors


def _build_rows(cells: list[dict], col_positions: dict[str, float]) -> list[list[str]]:
    """
    Assign cells to a 4-column grid.
    Uses FIRST COLUMN cells as row anchors (they have clean Y-spacing).
    """
    col_names = list(col_positions.keys())
    sorted_cols = sorted(col_names, key=lambda n: col_positions[n])

    # Build boundary ranges
    boundaries = []
    for i, name in enumerate(sorted_cols):
        x_start = col_positions[name]
        if i + 1 < len(sorted_cols):
            x_end = (col_positions[name] + col_positions[sorted_cols[i + 1]]) / 2
        else:
            x_end = 99999
        boundaries.append((name, x_start, x_end))

    # Assign column to each cell
    for c in cells:
        c["_col"] = _closest_column(c["bbox"][0][0], boundaries)

    # Find row anchor Y-positions from first-column cells (col 0)
    first_col_cells = sorted(
        [c for c in cells if c["_col"] == 0],
        key=lambda c: c["bbox"][0][1]
    )
    # STATISTICAL ROW PITCH: learn from gap distribution across ALL body cells
    all_y_tops = sorted(set(int(c["bbox"][0][1]) for c in cells))
    if len(all_y_tops) >= 3:
        gaps = [all_y_tops[i+1] - all_y_tops[i] for i in range(len(all_y_tops)-1)]
        # Filter out intra-row jitter (< 10px) to find inter-row gaps
        inter_row_gaps = [g for g in gaps if g > 10]
        if inter_row_gaps:
            # Dominant row pitch = median of inter-row gaps (robust to outliers)
            sorted_gaps = sorted(inter_row_gaps)
            pitch = sorted_gaps[len(sorted_gaps) // 2]  # median
            row_tolerance = pitch * 0.4  # auto-scales with actual spacing
        else:
            row_tolerance = 20
    else:
        row_tolerance = 20

    # Detect ALL row anchors using the computed tolerance
    all_y_tops = sorted(set(int(c["bbox"][0][1]) for c in cells))
    row_anchors = [all_y_tops[0]]
    for y in all_y_tops[1:]:
        if y - row_anchors[-1] > row_tolerance:
            row_anchors.append(y)
        else:
            # Update to average of cluster
            pass

    # Assign each cell to the nearest row anchor
    n_cols = len(sorted_cols)
    rows = [[""] * n_cols for _ in range(len(row_anchors))]

    for c in cells:
        y = c["bbox"][0][1]
        # Find closest row anchor (within 25px tolerance)
        best_row = None
        best_dist = 999
        for ri, anchor_y in enumerate(row_anchors):
            dist = abs(y - anchor_y)
            if dist < best_dist:
                best_dist = dist
                best_row = ri
        if best_row is not None and best_dist <= 25:
            col = c["_col"]
            if col < n_cols:
                if rows[best_row][col]:
                    rows[best_row][col] += " " + c["text"]
                else:
                    rows[best_row][col] = c["text"]

    # Clean up temp key
    for c in cells:
        c.pop("_col", None)

    # Remove empty rows
    rows = [r for r in rows if any(cell.strip() for cell in r)]

    # Auto-fix Italian numbers in financial columns (cols 2, 3 = TOTALE PERIODO, TOTALE PROGRESSIVO)
    for row in rows:
        for col_idx in range(2, min(4, len(row))):
            cell = row[col_idx].strip()
            if cell and any(ch.isdigit() for ch in cell) and not any(k in cell.upper() for k in ["TOTALE", "PERIODO", "PROGRESSIVO", "FASE", "ATTIVITA", "SUBFASE"]):
                fixed, was_modified = fix_italian_number(cell)
                if was_modified:
                    row[col_idx] = fixed

    return rows


def _simple_row_detect(cells: list[dict]) -> list[float]:
    """Fallback: detect rows from all cell Y-tops."""
    y_tops = sorted(set(int(c["bbox"][0][1]) for c in cells))
    rows = [y_tops[0]]
    for y in y_tops[1:]:
        if y - rows[-1] > 25:
            rows.append(y)
    return rows


def _closest_column(x: float, boundaries: list[tuple[str, float, float]]) -> int:
    """Find which column index a given X position belongs to."""
    for i, (name, x_start, x_end) in enumerate(boundaries):
        if x_start - 50 <= x < x_end:  # 50px left tolerance
            return i
    # Fallback: nearest
    dists = [abs(x - (b[1] + b[2]) / 2) for b in boundaries]
    return dists.index(min(dists))


def _row_to_list(items: list[dict], n_cols: int) -> list[str]:
    """Convert a group of assigned cells into a fixed-width row list."""
    row = [""] * n_cols
    for item in items:
        col = item["col"]
        if col < n_cols:
            if row[col]:
                row[col] += " " + item["text"]
            else:
                row[col] = item["text"]
    return row


def write_table_csv(grid: list[list[str]], csv_path: Path):
    """Write reconstructed grid to CSV."""
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        for row in grid:
            writer.writerow(row)


def validate_italian_numbers(result: dict) -> dict:
    """
    Validate that all financial numbers in TOTALE PERIODO and TOTALE PROGRESSIVO
    columns are in valid Italian format (dot=thousands, comma=decimal, 2 decimal places).
    
    Returns:
        {
            "valid": bool,
            "accuracy_score": float (0-1),
            "invalid_cells": [{"row": int, "col": str, "value": str, "reason": str}],
            "sum_check": {"periodo": {"computed": str, "expected": str, "match": bool},
                          "progressivo": {"computed": str, "expected": str, "match": bool}}
        }
    """
    rows = result.get("rows", [])
    columns = result.get("columns", [])
    if not rows or not columns:
        return {"valid": False, "accuracy_score": 0.0, "invalid_cells": [], "sum_check": {}}

    # Find column indices for TOTALE PERIODO and TOTALE PROGRESSIVO
    periodo_idx = None
    progressivo_idx = None
    for i, col in enumerate(columns):
        if "PERIODO" in col.upper():
            periodo_idx = i
        elif "PROGRESSIVO" in col.upper():
            progressivo_idx = i

    invalid_cells = []
    total_numbers = 0
    valid_numbers = 0

    # Check each data row (skip header row and totals row)
    data_rows = []
    totale_row = None
    for row_idx, row in enumerate(rows):
        # Skip header row
        if any("CODICE" in cell.upper() or "DESCRIZIONE" in cell.upper() for cell in row if cell):
            continue
        # Detect totals row
        if any("TOTALE COMMESSA" in cell.upper() for cell in row if cell):
            totale_row = (row_idx, row)
            continue
        data_rows.append((row_idx, row))

    # Validate numbers in financial columns
    for row_idx, row in data_rows:
        for col_idx in [periodo_idx, progressivo_idx]:
            if col_idx is None or col_idx >= len(row):
                continue
            value = row[col_idx].strip()
            if not value:
                continue
            total_numbers += 1
            if ITALIAN_NUMBER_RE.match(value):
                valid_numbers += 1
            else:
                col_name = columns[col_idx] if col_idx < len(columns) else f"col_{col_idx}"
                invalid_cells.append({
                    "row": row_idx,
                    "col": col_name,
                    "value": value,
                    "reason": _diagnose_number_error(value),
                })

    # Sum validation: check TOTALE COMMESSA matches sum of data rows
    sum_check = {}
    if totale_row:
        _, trow = totale_row
        for label, col_idx in [("periodo", periodo_idx), ("progressivo", progressivo_idx)]:
            if col_idx is None or col_idx >= len(trow):
                continue
            expected_str = trow[col_idx].strip()
            if not ITALIAN_NUMBER_RE.match(expected_str):
                sum_check[label] = {"computed": "N/A", "expected": expected_str, "match": False}
                continue
            expected = _parse_italian_number(expected_str)
            computed = 0.0
            for _, row in data_rows:
                if col_idx < len(row):
                    val = row[col_idx].strip()
                    if ITALIAN_NUMBER_RE.match(val):
                        computed += _parse_italian_number(val)
            match = abs(computed - expected) < 0.01
            sum_check[label] = {
                "computed": _format_italian_number(computed),
                "expected": expected_str,
                "match": match,
            }
            if not match:
                invalid_cells.append({
                    "row": totale_row[0],
                    "col": f"TOTALE COMMESSA ({label})",
                    "value": expected_str,
                    "reason": f"Sum mismatch: computed {_format_italian_number(computed)} != declared {expected_str}",
                })

    # Calculate accuracy score
    if total_numbers == 0:
        accuracy = 0.0
    else:
        accuracy = valid_numbers / total_numbers
        # Penalize sum mismatches
        if sum_check:
            sum_matches = sum(1 for s in sum_check.values() if s.get("match"))
            sum_total = len(sum_check)
            accuracy = accuracy * 0.7 + (sum_matches / sum_total) * 0.3

    return {
        "valid": len(invalid_cells) == 0,
        "accuracy_score": accuracy,
        "invalid_cells": invalid_cells,
        "sum_check": sum_check,
    }


def _parse_italian_number(s: str) -> float:
    """Parse Italian format number to float: 610.923,82 → 610923.82, 860,00- → -860.00"""
    s = s.strip()
    negative = s.startswith("-") or s.endswith("-")
    s = s.strip("-")
    result = float(s.replace(".", "").replace(",", "."))
    return -result if negative else result


def _format_italian_number(n: float) -> str:
    """Format float to Italian number: 610923.82 → 610.923,82"""
    int_part = int(abs(n))
    dec_part = round((abs(n) - int_part) * 100)
    # Add thousands dots
    int_str = f"{int_part:,}".replace(",", ".")
    result = f"{int_str},{dec_part:02d}"
    return f"-{result}" if n < 0 else result


def _diagnose_number_error(value: str) -> str:
    """Diagnose why a number doesn't match Italian format."""
    if "," not in value:
        return "Missing comma decimal separator"
    parts = value.rsplit(",", 1)
    if len(parts) == 2 and len(parts[1]) != 2:
        return f"Decimal part has {len(parts[1])} digits instead of 2"
    if "." in parts[0]:
        # Check thousands grouping
        groups = parts[0].split(".")
        for g in groups[1:]:
            if len(g) != 3:
                return f"Invalid thousands grouping: '{parts[0]}'"
    # Check for non-digit characters
    clean = value.replace(".", "").replace(",", "")
    if not clean.replace("-", "").isdigit():
        non_digits = [ch for ch in clean if not ch.isdigit() and ch != "-"]
        return f"Non-digit characters: {non_digits}"
    return "Unknown format issue"
