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
    if not col_anchors or len(col_anchors) < 3:
        return {"header": {}, "columns": [], "rows": []}

    # Step 2: Extract form metadata from cells above the table header
    header_y = min(a["y"] for a in col_anchors.values())
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
    # Calculate row spacing from first-column cells
    first_col_ys = [c["bbox"][0][1] for c in first_col_cells]
    if len(first_col_ys) >= 2:
        spacings = [first_col_ys[i+1] - first_col_ys[i] for i in range(len(first_col_ys)-1)]
        row_spacing = min(spacings)  # minimum distance between rows
        row_tolerance = row_spacing * 0.45  # less than half the row spacing
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
