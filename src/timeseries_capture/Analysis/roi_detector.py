"""
ROI Detector - HoughCircles-based well detection, identical algorithm to napari-hdf5-activity.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)

try:
    import cv2

    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logger.warning("opencv-python not installed. ROI detection disabled.")


@dataclass
class RoiDetectionResult:
    """Result of HoughCircles ROI detection."""

    masks: list[np.ndarray]  # List of binary uint8 masks (H, W), 0/255
    labeled_frame: np.ndarray  # RGB visualization with circles drawn
    circles: list[tuple[int, int, int]]  # (cx, cy, radius) per ROI
    n_rois: int = field(init=False)

    def __post_init__(self):
        self.n_rois = len(self.masks)


def detect_rois_hough(
    frame: np.ndarray,
    min_radius: int = 80,
    max_radius: int = 150,
    min_dist: int = 150,
    dp: float = 0.5,
    param1: float = 50.0,
    param2: float = 30.0,
) -> RoiDetectionResult:
    """
    Detect circular ROIs using HoughCircles — same algorithm as napari-hdf5-activity.

    Args:
        frame: Grayscale or RGB numpy array (uint8 or uint16)
        min_radius: Minimum circle radius in pixels
        max_radius: Maximum circle radius in pixels
        min_dist: Minimum distance between circle centers
        dp: Inverse ratio of accumulator resolution to image resolution
        param1: Upper Canny edge detection threshold
        param2: Accumulator threshold for circle detection (lower = more circles)

    Returns:
        RoiDetectionResult with masks, labeled frame, and circle coordinates
    """
    if not CV2_AVAILABLE:
        raise RuntimeError(
            "opencv-python is required for ROI detection. Install with: pip install opencv-python"
        )

    # Convert to grayscale
    if frame.ndim == 3:
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    else:
        gray = frame.copy()

    # Normalize to uint8
    if gray.dtype != np.uint8:
        min_val = gray.min()
        max_val = gray.max()
        if max_val > min_val:
            gray = ((gray.astype(np.float32) - min_val) / (max_val - min_val) * 255).astype(
                np.uint8
            )
        else:
            gray = np.zeros_like(gray, dtype=np.uint8)

    # CLAHE enhancement (identical to napari-hdf5-activity)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # HoughCircles detection
    circles_raw = cv2.HoughCircles(
        enhanced,
        cv2.HOUGH_GRADIENT,
        dp=dp,
        minDist=min_dist,
        param1=param1,
        param2=param2,
        minRadius=min_radius,
        maxRadius=max_radius,
    )

    # Build labeled visualization (RGB)
    labeled_frame = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)

    if circles_raw is None:
        logger.warning("No circles detected. Try adjusting min_radius, max_radius, or param2.")
        return RoiDetectionResult(masks=[], labeled_frame=labeled_frame, circles=[])

    # Sort circles in meandering (snake) order — identical to napari-hdf5-activity
    circles_sorted = _sort_circles_meandering_auto(circles_raw[0])
    circles_int = np.round(circles_sorted).astype(int)
    h, w = gray.shape

    masks: list[np.ndarray] = []
    circles_out: list[tuple[int, int, int]] = []

    for i, (cx, cy, r) in enumerate(circles_int):
        # Create binary mask
        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.circle(mask, (int(cx), int(cy)), int(r), 255, thickness=-1)
        masks.append(mask)
        circles_out.append((int(cx), int(cy), int(r)))

        # Draw on labeled frame
        cv2.circle(labeled_frame, (int(cx), int(cy)), int(r), (0, 255, 0), 2)
        cv2.circle(labeled_frame, (int(cx), int(cy)), 3, (0, 255, 0), -1)
        cv2.putText(
            labeled_frame,
            str(i + 1),
            (int(cx) - 10, int(cy) + 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (255, 80, 0),
            2,
            cv2.LINE_AA,
        )

    logger.info(f"Detected {len(masks)} ROIs via HoughCircles")
    return RoiDetectionResult(masks=masks, labeled_frame=labeled_frame, circles=circles_out)


def _sort_circles_meandering_auto(circles: np.ndarray) -> np.ndarray:
    """
    Sort circles in meandering (snake/boustrophedon) order — identical to napari-hdf5-activity.

    Auto-detects plate layout from circle count:
      4→2×2, 6→2×3, 8→2×4, 12→3×4, 16→4×4, 24→4×6
    Other counts fall back to simple left-to-right order.

    Pattern (example 2×3):
      Row 0:  1 → 2 → 3
      Row 1:  6 ← 5 ← 4
    """
    if circles is None or len(circles) == 0:
        return circles

    n = len(circles)
    layout = {4: (2, 2), 6: (2, 3), 8: (2, 4), 12: (3, 4), 16: (4, 4), 24: (4, 6)}

    if n in layout:
        rows, _ = layout[n]
        row_groups = _group_into_rows(circles, rows)
        ordered = []
        for row_idx, row in enumerate(row_groups):
            row_sorted = sorted(row, key=lambda c: c[0])
            if row_idx % 2 == 1:
                row_sorted = row_sorted[::-1]
            ordered.extend(row_sorted)
        return np.array(ordered, dtype=np.float32)
    else:
        # Fallback: sort by X coordinate
        return circles[np.argsort(circles[:, 0])]


def _group_into_rows(circles: np.ndarray, expected_rows: int) -> list:
    """Group circles into rows based on Y coordinate."""
    y_sorted = circles[np.argsort(circles[:, 1])]
    if expected_rows == 1:
        return [y_sorted.tolist()]
    per_row = len(circles) // expected_rows
    rows = []
    for i in range(expected_rows):
        start = i * per_row
        end = len(y_sorted) if i == expected_rows - 1 else start + per_row
        rows.append(y_sorted[start:end].tolist())
    return rows


def masks_to_array(masks: list[np.ndarray]) -> np.ndarray:
    """
    Stack list of binary masks into a single (N, H, W) uint8 array for Zarr storage.
    """
    if not masks:
        return np.zeros((0,), dtype=np.uint8)
    return np.stack(masks, axis=0)


def array_to_masks(arr: np.ndarray) -> list[np.ndarray]:
    """
    Convert (N, H, W) uint8 array back to list of binary masks.
    """
    return [arr[i] for i in range(arr.shape[0])]
