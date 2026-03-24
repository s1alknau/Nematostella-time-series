"""
LiveAnalysisWorker - Background QThread that reads accumulated Zarr frames every 20s
and computes per-ROI activity (frame differences), identical to napari-hdf5-activity.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from qtpy.QtCore import QThread
from qtpy.QtCore import Signal as pyqtSignal

logger = logging.getLogger(__name__)


def _apply_illumination_correction(
    activity: np.ndarray,
    led_power: np.ndarray,
) -> np.ndarray:
    """
    Correct for baseline shifts between illumination phases.

    Identical to equalize_signal_per_illumination_period() in napari-hdf5-activity:
      1. Group contiguous frames with the same phase (light: power > 0, dark: power == 0)
      2. Compute 15th-percentile floor per period
      3. Global reference = median of all floors
      4. Shift each period by (global_floor - period_floor), clamp to >= 0

    Args:
        activity: Per-ROI activity array of shape (N-1,) — one value per frame transition
        led_power: white_led_power recorded for each frame, shape (N,)

    Returns:
        Corrected activity array of shape (N-1,), dtype float32
    """
    if len(activity) == 0:
        return activity

    # For diff[i] = |frame[i+1] - frame[i]|, assign to the phase of frame[i+1]
    # so that the transition is attributed to the phase it "lands" in.
    phase_per_diff = (led_power[1:] > 0).astype(np.int8)  # (N-1,) 1=light, 0=dark

    # Find contiguous period boundaries
    periods: list[tuple[int, int]] = []  # (start_idx, end_idx) inclusive, into activity
    start = 0
    for j in range(1, len(phase_per_diff)):
        if phase_per_diff[j] != phase_per_diff[j - 1]:
            periods.append((start, j - 1))
            start = j
    periods.append((start, len(phase_per_diff) - 1))

    if len(periods) < 2:
        # Only one phase present — no correction needed
        return activity

    # Compute 15th-percentile floor per period
    floors = np.empty(len(periods), dtype=np.float32)
    for k, (s, e) in enumerate(periods):
        segment = activity[s : e + 1]
        floors[k] = float(np.percentile(segment, 15)) if len(segment) > 0 else 0.0

    global_floor = float(np.median(floors))

    # Apply shift per period and clamp
    corrected = activity.copy()
    for k, (s, e) in enumerate(periods):
        shift = global_floor - floors[k]
        corrected[s : e + 1] = np.clip(corrected[s : e + 1] + shift, 0.0, None)

    return corrected.astype(np.float32)


class LiveAnalysisWorker(QThread):
    """
    Background thread for live activity analysis during Zarr recording.

    Every `interval_sec` seconds it:
      1. Opens the active Zarr store (read-only)
      2. Reads all frames written so far
      3. Computes per-ROI activity = mean |frame[t] - frame[t-1]| within each mask
      4. Emits `results_ready` with activity arrays + timestamps

    Signals:
        results_ready(dict): Keys: roi_0..N, timestamps, n_frames
        error_occurred(str): Emitted on unexpected exceptions
    """

    results_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        zarr_path: str | Path,
        masks: list[np.ndarray],
        interval_sec: int = 20,
        parent=None,
    ):
        """
        Args:
            zarr_path: Path to the active .zarr store
            masks: List of binary uint8 masks (H, W), one per ROI
            interval_sec: Seconds between analysis updates (default 20)
        """
        super().__init__(parent)
        self.zarr_path = str(zarr_path)
        self.masks = masks
        self.interval_sec = interval_sec
        self._running = False

    # ------------------------------------------------------------------
    # QThread interface
    # ------------------------------------------------------------------

    def run(self):
        self._running = True
        logger.info(
            f"LiveAnalysisWorker started (interval={self.interval_sec}s, ROIs={len(self.masks)})"
        )

        while self._running:
            self._compute_and_emit()
            # Sleep in 500ms chunks so we can react to stop() quickly
            elapsed = 0
            while self._running and elapsed < self.interval_sec * 1000:
                self.msleep(500)
                elapsed += 500

        logger.info("LiveAnalysisWorker stopped")

    def stop(self):
        """Request graceful stop."""
        self._running = False

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def _compute_and_emit(self):
        """Read current Zarr frames and compute activity per ROI."""
        try:
            import zarr  # lazy import — zarr may not be installed

            root = zarr.open_group(self.zarr_path, mode="r")

            # Safety: frames array must exist
            if "images" not in root or "frames" not in root["images"]:
                return
            frames_arr = root["images"]["frames"]

            # Determine how many frames have actually been written.
            # The images array is pre-allocated to its max capacity (e.g. 100 000),
            # so frames_arr.shape[0] is NOT the written count.
            # The timeseries datasets are appended incrementally and are therefore
            # always exactly as long as the number of written frames.
            ts_group = root.get("timeseries", None)
            if ts_group is not None and "frame_index" in ts_group:
                n_frames = int(ts_group["frame_index"].shape[0])
            elif ts_group is not None and "recording_elapsed_sec" in ts_group:
                n_frames = int(ts_group["recording_elapsed_sec"].shape[0])
            else:
                # Fallback: check .zattrs written_frames attribute
                n_frames = int(root.attrs.get("written_frames", 0))

            if n_frames < 2:
                return

            # Read only the actually written frames (avoids loading the full
            # pre-allocated array which can be hundreds of GiB).
            # Normalize to [0, 1] — identical to napari-hdf5-activity (_reader.py:
            # normalize_image_to_float32 divides uint16 by 65535.0).
            dtype_max = float(np.iinfo(frames_arr.dtype).max)  # 255 for uint8, 65535 for uint16
            frame_data = frames_arr[:n_frames].astype(np.float32) / dtype_max  # (N, H, W)

            # Compute frame-to-frame absolute differences
            diffs = np.abs(np.diff(frame_data, axis=0))  # (N-1, H, W)

            # Read LED power for illumination phase correction (N,)
            led_power: np.ndarray | None = None
            if ts_group is not None and "white_led_power" in ts_group:
                led_power = ts_group["white_led_power"][:n_frames].astype(np.float32)

            results: dict = {}
            for i, mask in enumerate(self.masks):
                mask_bool = mask > 0
                if not mask_bool.any():
                    results[f"roi_{i}"] = np.zeros(n_frames - 1, dtype=np.float32)
                    continue
                n_pixels = int(mask_bool.sum())
                # Mean per-pixel activity per frame transition
                roi_diffs = diffs[:, mask_bool]  # (N-1, n_pixels)
                activity = roi_diffs.sum(axis=1) / n_pixels  # (N-1,)

                # Illumination phase baseline correction (identical to analysis plugin)
                if led_power is not None and len(led_power) == n_frames:
                    activity = _apply_illumination_correction(activity, led_power)

                results[f"roi_{i}"] = activity

            # Timestamps (seconds from start)
            if "timeseries" in root and "timestamps" in root["timeseries"]:
                ts = root["timeseries"]["timestamps"][:n_frames].astype(np.float64)
                # Convert to elapsed seconds from first timestamp
                if len(ts) > 1:
                    t0 = ts[0]
                    elapsed_sec = ts[1:n_frames] - t0  # align with diffs (N-1,)
                else:
                    elapsed_sec = np.arange(n_frames - 1, dtype=np.float64)
            else:
                elapsed_sec = np.arange(n_frames - 1, dtype=np.float64)

            results["timestamps"] = elapsed_sec
            results["n_frames"] = n_frames

            self.results_ready.emit(results)
            logger.debug(f"LiveAnalysis update: {n_frames} frames, {len(self.masks)} ROIs")

        except Exception as exc:
            logger.warning(f"LiveAnalysisWorker error (will retry): {exc}")
            # Don't emit error for transient issues (zarr not flushed yet, etc.)
