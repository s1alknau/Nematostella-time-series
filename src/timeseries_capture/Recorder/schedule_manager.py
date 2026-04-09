"""
Schedule Manager - Multi-Segment Experiment Scheduling

Drives an ExperimentSchedule at runtime.  Exposes the same interface as
PhaseManager so RecordingManager needs only a single extra attribute check.

Contract:
    - get_current_phase_info(prevent_transition) → PhaseInfo | None
    - is_enabled() → bool
    - start_phase_recording()
    - get_phase_summary() → dict
    - current_segment_index  (int, read-only)
    - current_segment_label  (str, read-only)
    - on_segment_changed     callback set by RecordingManager
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from .phase_manager import PhaseManager
from .recording_state import (
    ExperimentSchedule,
    PhaseInfo,
    PhaseType,
    RecordingConfig,
    SegmentConfig,
)

logger = logging.getLogger(__name__)


class ScheduleManager:
    """
    Drives an ExperimentSchedule segment by segment.

    One PhaseManager is created per LD segment; continuous segments (DD/LL)
    return synthesised PhaseInfo objects without a PhaseManager.

    Segment transitions are detected on every call to get_current_phase_info()
    by comparing wall-clock elapsed time against segment.duration_min.
    """

    def __init__(
        self,
        schedule: ExperimentSchedule,
        on_segment_changed: Callable[[int], None] | None = None,
    ):
        self._schedule = schedule
        self.on_segment_changed = on_segment_changed

        self._current_seg_idx: int = 0
        self._seg_start_times: list[float] = [0.0] * len(schedule.segments)
        self._started = False

        # Build one PhaseManager per segment that uses phases
        self._seg_phase_managers: list[PhaseManager | None] = []
        for seg in schedule.segments:
            if seg.phase_enabled:
                cfg = self._seg_to_recording_config(seg)
                self._seg_phase_managers.append(PhaseManager(cfg))
            else:
                self._seg_phase_managers.append(None)

        logger.info(
            f"ScheduleManager: {len(schedule.segments)} segment(s), "
            f"total={schedule.total_duration_min()} min"
        )

    # ------------------------------------------------------------------
    # PhaseManager-compatible interface
    # ------------------------------------------------------------------

    def is_enabled(self) -> bool:
        return True  # ScheduleManager is always active

    def start_phase_recording(self):
        """Start the first segment."""
        self._started = True
        self._current_seg_idx = 0
        self._seg_start_times[0] = time.time()
        pm = self._seg_phase_managers[0]
        if pm:
            pm.start_phase_recording()
        seg = self._schedule.segments[0]
        logger.info(
            f"ScheduleManager started: segment 0 — {seg.label!r} "
            f"({'LD' if seg.phase_enabled else 'continuous'}, "
            f"{seg.duration_min} min)"
        )

    def get_current_phase_info(self, prevent_transition: bool = False) -> PhaseInfo | None:
        if not self._started:
            return None

        if not prevent_transition:
            self._check_segment_transition()

        seg = self._schedule.segments[self._current_seg_idx]
        pm = self._seg_phase_managers[self._current_seg_idx]

        if pm is not None:
            # Delegate to inner PhaseManager for LD cycle
            return pm.get_current_phase_info(prevent_transition=prevent_transition)
        else:
            # Continuous segment — synthesise a PhaseInfo
            return self._continuous_phase_info(seg)

    def get_phase_summary(self) -> dict:
        seg = self._schedule.segments[self._current_seg_idx]
        pm = self._seg_phase_managers[self._current_seg_idx]
        inner = pm.get_phase_summary() if pm else {"enabled": False}
        return {
            "schedule_mode": True,
            "n_segments": len(self._schedule.segments),
            "current_segment_index": self._current_seg_idx,
            "current_segment_label": seg.label,
            "segment_elapsed_min": self._segment_elapsed_min(),
            "segment_duration_min": seg.duration_min,
            "inner_phase": inner,
        }

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def current_segment_index(self) -> int:
        return self._current_seg_idx

    @property
    def current_segment_label(self) -> str:
        return self._schedule.segments[self._current_seg_idx].label

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _check_segment_transition(self):
        seg = self._schedule.segments[self._current_seg_idx]
        if seg.is_open_ended():
            return  # last open-ended segment never auto-advances
        elapsed_min = self._segment_elapsed_min()
        if elapsed_min >= seg.duration_min:
            self._advance_segment()

    def _advance_segment(self):
        next_idx = self._current_seg_idx + 1
        if next_idx >= len(self._schedule.segments):
            return  # already at last segment
        self._current_seg_idx = next_idx
        self._seg_start_times[next_idx] = time.time()
        pm = self._seg_phase_managers[next_idx]
        if pm:
            pm.start_phase_recording()
        seg = self._schedule.segments[next_idx]
        logger.info(
            f"ScheduleManager: segment transition → {next_idx} — {seg.label!r} "
            f"({'LD' if seg.phase_enabled else 'continuous'}, "
            f"{seg.duration_min} min)"
        )
        if self.on_segment_changed:
            try:
                self.on_segment_changed(next_idx)
            except Exception as exc:
                logger.warning(f"on_segment_changed callback error: {exc}")

    def _segment_elapsed_min(self) -> float:
        t = self._seg_start_times[self._current_seg_idx]
        if t == 0:
            return 0.0
        return (time.time() - t) / 60.0

    def _continuous_phase_info(self, seg: SegmentConfig) -> PhaseInfo:
        """Synthesise a PhaseInfo for a continuous (non-LD) segment."""
        led_map = {
            "ir": PhaseType.DARK,
            "white": PhaseType.LIGHT,
            "dual": PhaseType.LIGHT,
        }
        phase = led_map.get(seg.continuous_led_type, PhaseType.DARK)
        elapsed_min = self._segment_elapsed_min()
        remaining = (
            max(0.0, seg.duration_min - elapsed_min)
            if seg.duration_min is not None
            else float("inf")
        )
        return PhaseInfo(
            phase=phase,
            cycle_number=1,
            total_cycles=1,
            phase_remaining_min=remaining,
            led_type=seg.continuous_led_type,
        )

    @staticmethod
    def _seg_to_recording_config(seg: SegmentConfig) -> RecordingConfig:
        """Build a minimal RecordingConfig so PhaseManager can be constructed."""
        duration = seg.duration_min if seg.duration_min is not None else 0
        return RecordingConfig(
            duration_min=duration,
            interval_sec=5,  # PhaseManager only uses duration + phase durations
            experiment_name=seg.label,
            output_dir="",
            **seg.to_recording_config_fields(),
        )
