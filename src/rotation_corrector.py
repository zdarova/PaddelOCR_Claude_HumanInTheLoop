"""Correct rotation/skew of page images.

Two-stage correction:
1. Coarse rotation: detect 90°/180°/270° page orientation via dominant edge angles
2. Fine deskew: small angle correction via deskew library
"""

import cv2
import numpy as np
from pathlib import Path
from deskew import determine_skew
from src.config import ROTATED_DIR, CONFIG


def _detect_page_orientation(gray: np.ndarray) -> int:
    """
    Detect if page needs 90/180/270° rotation by analyzing dominant line angles.
    Returns rotation needed: 0, 90, 180, or 270 degrees clockwise.
    """
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100, minLineLength=100, maxLineGap=10)

    if lines is None or len(lines) < 10:
        return 0

    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        angles.append(angle)

    angles = np.array(angles)

    # Count lines in each orientation bucket
    near_0 = np.sum(np.abs(angles) < 15)                           # horizontal text
    near_90 = np.sum((np.abs(angles) > 75) & (np.abs(angles) < 105))  # vertical text
    near_180 = np.sum(np.abs(np.abs(angles) - 180) < 15)           # upside-down

    total = len(angles)
    if total == 0:
        return 0

    # If dominant lines are vertical (>60%), page is rotated 90° or 270°
    if near_90 / total > 0.6:
        # Determine direction: check if most vertical lines go top-to-bottom (-90°) or bottom-to-top (+90°)
        neg_90 = np.sum((angles > -100) & (angles < -80))
        pos_90 = np.sum((angles > 80) & (angles < 100))
        if neg_90 > pos_90:
            return 90   # rotate 90° clockwise to fix
        else:
            return 270  # rotate 270° clockwise to fix

    # If dominant lines suggest upside-down
    if near_180 / total > 0.5:
        return 180

    return 0


def _rotate_90_multiple(img: np.ndarray, degrees: int) -> np.ndarray:
    """Rotate image by exact 90° multiple without quality loss."""
    if degrees == 90:
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    elif degrees == 180:
        return cv2.rotate(img, cv2.ROTATE_180)
    elif degrees == 270:
        return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return img


def correct_rotation(image_path: Path) -> Path:
    """
    Two-stage rotation correction:
    1. Fix 90/180/270° orientation
    2. Fine deskew for small angles
    Returns output path.
    """
    ROTATED_DIR.mkdir(parents=True, exist_ok=True)
    img = cv2.imread(str(image_path))
    grayscale = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Stage 1: coarse orientation fix
    orientation = _detect_page_orientation(grayscale)
    if orientation != 0:
        img = _rotate_90_multiple(img, orientation)
        grayscale = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Stage 2: fine deskew + perspective baseline correction
    max_angle = CONFIG["rotation"]["max_angle"]
    angle = determine_skew(grayscale)

    if angle is not None and 0.1 < abs(angle) <= max_angle:
        h, w = img.shape[:2]
        center = (w // 2, h // 2)
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        img = cv2.warpAffine(
            img, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
        )
        grayscale = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Stage 3: correct baseline tilt (text on right side lower than left)
    img = _correct_baseline_tilt(img, grayscale)

    out_path = ROTATED_DIR / image_path.name
    cv2.imwrite(str(out_path), img)
    return out_path


def _correct_baseline_tilt(img: np.ndarray, gray: np.ndarray) -> np.ndarray:
    """
    Detect and correct baseline tilt where text on right side is shifted
    vertically relative to left side (perspective/scanner artifact).
    Uses morphological text-line detection to measure tilt.
    """
    h, w = img.shape[:2]

    # Threshold to get text regions
    _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
    # Connect text on same line with a wide horizontal kernel
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (w // 3, 1))
    connected = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    # Find contours of connected text lines
    contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    tilts = []
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        if cw > w // 3:  # only wide contours spanning significant page width
            [vx, vy, x0, y0] = cv2.fitLine(cnt, cv2.DIST_L2, 0, 0.01, 0.01)
            angle = np.degrees(np.arctan2(vy[0], vx[0]))
            if abs(angle) < 3:  # sanity check
                tilts.append(angle)

    if len(tilts) < 3:
        return img

    median_tilt = float(np.median(tilts))

    # Only correct if tilt is meaningful (> 0.1°) but small (< 2°)
    if abs(median_tilt) < 0.1 or abs(median_tilt) > 2.0:
        return img

    # Apply rotation to correct the baseline tilt
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, median_tilt, 1.0)
    corrected = cv2.warpAffine(
        img, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )
    return corrected
