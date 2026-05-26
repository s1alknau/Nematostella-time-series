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

        # Incremental state — avoids reloading all frames on every update.
        # Only the new frames since last call are read; the full frame stack is
        # never held in RAM simultaneously.
        self._last_n: int = 0  # total frames processed so far
        self._boundary_frame: np.ndarray | None = (
            None  # last frame of previous batch (normalised float32)
        )
        # Accumulated 1-D arrays (tiny — one value per frame transition)
        self._roi_activity_raw: list[np.ndarray] = [np.empty(0, dtype=np.float32) for _ in masks]
        self._led_power_acc: np.ndarray = np.empty(0, dtype=np.float32)  # N led-power values
        self._elapsed_acc: np.ndarray = np.empty(0, dtype=np.float32)  # N-1 elapsed-sec values

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
        """Read only NEW Zarr frames since last call and compute activity per ROI.

        Incremental design: the full frame stack is never held in RAM.
        At most (new_frames_since_last_update + 1 boundary frame) are loaded
        per call, so memory usage stays constant regardless of recording length.
        """
        try:
            import zarr  # lazy import — zarr may not be installed

            root = zarr.open_group(self.zarr_path, mode="r")

            # Safety: frames array must exist
            if "images" not in root or "frames" not in root["images"]:
                return
            frames_arr = root["images"]["frames"]

            # Determine how many frames have actually been written.
            # DataManagerZarr writes root.attrs["written_frames"] every flush_interval
            # frames — use this as the authoritative count.  The timeseries arrays are
            # pre-allocated to 100k rows so their .shape[0] is NOT the written count.
            ts_group = root.get("timeseries", None)
            n_frames = int(root.attrs.get("written_frames", 0))

            # Nothing new to process
            if n_frames <= self._last_n or n_frames < 2:
                return

            start_idx = self._last_n  # index of first new frame

            # ----------------------------------------------------------------
            # Load only new frames (small batch, e.g. ~4 frames per 20s update)
            # ----------------------------------------------------------------
            dtype_max = float(np.iinfo(frames_arr.dtype).max)
            new_frames = frames_arr[start_idx:n_frames].astype(np.float32) / dtype_max

            # Prepend boundary frame so we get a diff at the batch seam
            if self._boundary_frame is not None:
                batch = np.concatenate([self._boundary_frame[np.newaxis], new_frames], axis=0)
            else:
                batch = new_frames  # first call — no boundary yet

            # ----------------------------------------------------------------
            # Always accumulate elapsed + LED for new frames — even if we
            # return early below (ensures _elapsed_acc[k] == elapsed of frame k
            # for correct timestamp alignment on subsequent calls).
            # ----------------------------------------------------------------
            if ts_group is not None and "recording_elapsed_sec" in ts_group:
                new_elapsed = ts_group["recording_elapsed_sec"][start_idx:n_frames].astype(
                    np.float32
                )
                self._elapsed_acc = np.concatenate([self._elapsed_acc, new_elapsed])

            if ts_group is not None and "white_led_power" in ts_group:
                new_led = ts_group["white_led_power"][start_idx:n_frames].astype(np.float32)
                self._led_power_acc = np.concatenate([self._led_power_acc, new_led])

            # Update boundary cache and frame counter
            self._boundary_frame = new_frames[-1].copy()
            self._last_n = n_frames

            if batch.shape[0] < 2:
                # Only one frame so far — no diff possible yet
                return

            # Frame differences for this batch only — tiny, O(new_frames)
            diffs = np.abs(np.diff(batch, axis=0))  # (batch-1, H, W)

            # ----------------------------------------------------------------
            # Per-ROI activity for new diffs only, append to accumulators
            # ----------------------------------------------------------------
            for i, mask in enumerate(self.masks):
                mask_bool = mask > 0
                if not mask_bool.any():
                    self._roi_activity_raw[i] = np.concatenate(
                        [self._roi_activity_raw[i], np.zeros(diffs.shape[0], dtype=np.float32)]
                    )
                    continue
                n_pixels = int(mask_bool.sum())
                roi_diffs = diffs[:, mask_bool]  # (batch-1, n_pixels)
                activity = roi_diffs.sum(axis=1) / n_pixels  # mean |ΔPixel| per frame per ROI
                self._roi_activity_raw[i] = np.concatenate(
                    [self._roi_activity_raw[i], activity.astype(np.float32)]
                )

            # ----------------------------------------------------------------
            # Build and emit results using full accumulated 1-D arrays (tiny)
            # ----------------------------------------------------------------
            n_diffs = len(self._roi_activity_raw[0]) if self.masks else 0
            if n_diffs == 0:
                return

            # ----------------------------------------------------------------
            # Apply per-illumination-period baseline equalization — identical
            # to equalize_signal_per_illumination_period() in
            # napari-hdf5-activity.  Without this the raw |dPixel| signal
            # shows a large baseline step at every light/dark transition
            # (brighter frames have more pixel noise -> higher diff floor),
            # making the LD structure of schedule-designed recordings look
            # like illumination artifacts instead of biological activity.
            # Correction is a no-op when only a single phase is present
            # (e.g. continuous IR-only recordings).
            # ----------------------------------------------------------------
            apply_correction = len(self._led_power_acc) == n_diffs + 1
            if not apply_correction:
                logger.debug(
                    f"Skipping illumination correction: led_power_acc has "
                    f"{len(self._led_power_acc)} entries, expected {n_diffs + 1}"
                )

            results: dict = {}
            for i in range(len(self.masks)):
                raw = self._roi_activity_raw[i]
                if apply_correction:
                    results[f"roi_{i}"] = _apply_illumination_correction(raw, self._led_power_acc)
                else:
                    results[f"roi_{i}"] = raw

            # Timestamps aligned with diffs (N-1 values).
            # Attribute diff[i] = |frame[i+1]-frame[i]| to frame[i]'s timestamp so
            # the first diff is at elapsed=0 and all lines start at x=0 in the plot.
            if len(self._elapsed_acc) >= n_diffs:
                elapsed_sec = self._elapsed_acc[0:n_diffs]
            else:
                elapsed_sec = np.arange(n_diffs, dtype=np.float32)

            results["timestamps"] = elapsed_sec
            results["n_frames"] = self._last_n

            self.results_ready.emit(results)
            logger.debug(
                f"LiveAnalysis update: +{n_frames - start_idx} new frames "
                f"({self._last_n} total), {len(self.masks)} ROIs"
            )

        except Exception as exc:
            logger.warning(f"LiveAnalysisWorker error (will retry): {exc}")
            # Don't emit error for transient issues (zarr not flushed yet, etc.)
