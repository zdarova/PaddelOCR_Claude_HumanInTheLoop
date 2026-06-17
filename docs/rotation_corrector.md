# rotation_corrector.py

Three-stage image rotation and alignment correction for scanned pages.

## Function

### `correct_rotation(image_path: Path) -> Path`

Applies correction and saves to `working/rotated/`. Returns output path.

## Stages

### Stage 1: Coarse Orientation (90°/180°/270°)
- Detects dominant line orientation via Hough transform
- If >60% of lines are vertical → page is rotated 90° or 270°
- Uses `cv2.rotate()` for lossless 90° multiples

### Stage 2: Fine Deskew
- Uses `deskew.determine_skew()` for small residual angles
- Only corrects if angle is between 0.1° and `max_angle` (default 15°)

### Stage 3: Baseline Tilt Correction
- Detects when text on the right side of the page is shifted vertically (scanner/perspective artifact)
- Uses morphological text-line detection: binary threshold → horizontal kernel close → contour fitLine
- Corrects tilts between 0.1° and 2.0°

## Dependencies
- `opencv-python`, `numpy`, `deskew`

## Configuration
- `config.yaml` → `rotation.max_angle` (default: 15.0)

## Why All 3 Stages?
- `determine_skew()` only handles small angles, misses 90° rotations entirely
- Pure rotation correction misses perspective artifacts (baseline tilt)
- The baseline tilt causes cells in the same row to have 15-20px Y-offset between left and right columns, breaking row reconstruction
