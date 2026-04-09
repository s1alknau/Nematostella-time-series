"""
Recording State Management - Verbessert mit Drift-Kompensation

WICHTIG: Drift darf sich NICHT aufsummieren!

Lösung: Statt vom letzten Frame zu messen, vom Start-Zeitpunkt messen.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class RecordingStatus(Enum):
    """Recording Status States"""

    IDLE = "idle"
    RECORDING = "recording"
    PAUSED = "paused"
    STOPPING = "stopping"


class PhaseType(Enum):
    """Phase Types"""

    LIGHT = "light"
    DARK = "dark"


@dataclass
class RecordingConfig:
    """Recording Configuration"""

    duration_min: int
    interval_sec: int
    experiment_name: str
    output_dir: str

    # Phase Config (optional)
    phase_enabled: bool = False
    light_duration_min: int = 30
    dark_duration_min: int = 30
    start_with_light: bool = True
    dual_light_phase: bool = False
    camera_trigger_latency_ms: int = 20
    white_led_continuous: bool = False  # White LED bleibt während Tagphase dauerhaft an

    # LED Power Config (0-100%)
    # LEGACY: Single power values (for backward compatibility and continuous mode)
    ir_led_power: int = 100
    white_led_power: int = 50

    # PER-PHASE LED Powers (for phase recordings with intensity matching)
    # These override the legacy values when phase_enabled=True
    dark_phase_ir_power: int = 100  # IR power for dark phase (IR only)
    light_phase_ir_power: int = 100  # IR power for light phase (dual mode)
    light_phase_white_power: int = 50  # White power for light phase (white or dual mode)

    # Brightness Validation (v2.4.1+)
    # Adaptive threshold for detecting black frames (set to 50% of calibrated intensity, or 10 minimum)
    brightness_validation_threshold: float = 10.0  # Minimum mean intensity for valid frames

    # ROI Settings (for consistent intensity measurement with calibration)
    use_full_frame_for_validation: bool = (
        True  # If True, measure full frame; if False, use center ROI
    )
    roi_fraction: float = 0.75  # Fraction of frame for ROI (e.g., 0.75 = 75% x 75% center)

    # Output format: "hdf5" or "zarr"
    output_format: str = "hdf5"

    # Bit depth: convert 12-bit HIK frames to uint8 before saving (halves file size)
    save_as_uint8: bool = False


# ============================================================================
# EXPERIMENT SCHEDULE  (optional, does not change RecordingConfig)
# ============================================================================


@dataclass
class SegmentConfig:
    """
    One segment of an ExperimentSchedule.

    Each segment runs its own independent LD/DD/LL cycle for a fixed duration
    (or open-ended if duration_min is None — only valid for the last segment).
    LED powers mirror the per-phase fields in RecordingConfig.
    """

    label: str = "Segment"

    # --- Phase mode ---
    phase_enabled: bool = True  # True = LD cycle, False = continuous
    light_duration_min: int = 720  # 12 h default
    dark_duration_min: int = 720
    start_with_light: bool = True
    dual_light_phase: bool = False
    white_led_continuous: bool = False
    camera_trigger_latency_ms: int = 20

    # --- LED powers ---
    dark_phase_ir_power: int = 100
    light_phase_ir_power: int = 100
    light_phase_white_power: int = 50
    # Continuous mode (phase_enabled=False)
    ir_led_power: int = 100
    white_led_power: int = 50
    continuous_led_type: str = "ir"  # "ir" | "white" | "dual"

    # --- Duration ---
    # None = open-ended; only allowed on the LAST segment of a schedule
    duration_min: int | None = 1440  # 1 day default

    def is_open_ended(self) -> bool:
        return self.duration_min is None

    def to_recording_config_fields(self) -> dict:
        """Return a dict of fields compatible with RecordingConfig."""
        return {
            "phase_enabled": self.phase_enabled,
            "light_duration_min": self.light_duration_min,
            "dark_duration_min": self.dark_duration_min,
            "start_with_light": self.start_with_light,
            "dual_light_phase": self.dual_light_phase,
            "white_led_continuous": self.white_led_continuous,
            "camera_trigger_latency_ms": self.camera_trigger_latency_ms,
            "dark_phase_ir_power": self.dark_phase_ir_power,
            "light_phase_ir_power": self.light_phase_ir_power,
            "light_phase_white_power": self.light_phase_white_power,
            "ir_led_power": self.ir_led_power,
            "white_led_power": self.white_led_power,
        }


@dataclass
class ExperimentSchedule:
    """
    An ordered list of SegmentConfigs that drives a full multi-segment recording.

    Rules:
    - Only the LAST segment may have duration_min=None (open-ended).
    - All other segments must have a positive duration_min.
    - interval_sec, output settings, and experiment metadata apply globally.
    """

    segments: list[SegmentConfig] = field(default_factory=list)
    interval_sec: int = 5
    experiment_name: str = "nematostella_timelapse"
    output_dir: str = ""
    output_format: str = "hdf5"
    save_as_uint8: bool = False
    brightness_validation_threshold: float = 10.0
    use_full_frame_for_validation: bool = True
    roi_fraction: float = 0.75

    def total_duration_min(self) -> int | None:
        """Sum of all segment durations, or None if any segment is open-ended."""
        total = 0
        for seg in self.segments:
            if seg.duration_min is None:
                return None
            total += seg.duration_min
        return total

    def validate(self) -> str | None:
        """Return an error string, or None if valid."""
        if not self.segments:
            return "Schedule has no segments."
        for i, seg in enumerate(self.segments[:-1]):
            if seg.duration_min is None:
                return f"Segment {i+1} ({seg.label!r}) is open-ended but is not the last segment."
            if seg.duration_min <= 0:
                return f"Segment {i+1} ({seg.label!r}) has duration_min <= 0."
        return None

    def to_recording_config(self) -> RecordingConfig:
        """
        Build a RecordingConfig for RecordingState/file-creation.
        duration_min=0 signals open-ended to RecordingState.
        First segment's LED/phase settings initialise the legacy fields.
        """
        first = self.segments[0]
        total = self.total_duration_min() or 0  # 0 = open-ended sentinel
        fields = first.to_recording_config_fields()
        return RecordingConfig(
            duration_min=total,
            interval_sec=self.interval_sec,
            experiment_name=self.experiment_name,
            output_dir=self.output_dir,
            output_format=self.output_format,
            save_as_uint8=self.save_as_uint8,
            brightness_validation_threshold=self.brightness_validation_threshold,
            use_full_frame_for_validation=self.use_full_frame_for_validation,
            roi_fraction=self.roi_fraction,
            **fields,
        )

    # --- Serialization ---

    def to_dict(self) -> dict:
        return {
            "segments": [asdict(s) for s in self.segments],
            "interval_sec": self.interval_sec,
            "experiment_name": self.experiment_name,
            "output_dir": self.output_dir,
            "output_format": self.output_format,
            "save_as_uint8": self.save_as_uint8,
            "brightness_validation_threshold": self.brightness_validation_threshold,
            "use_full_frame_for_validation": self.use_full_frame_for_validation,
            "roi_fraction": self.roi_fraction,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> ExperimentSchedule:
        segs = [SegmentConfig(**s) for s in d.pop("segments", [])]
        return cls(segments=segs, **d)

    @classmethod
    def from_json(cls, s: str) -> ExperimentSchedule:
        return cls.from_dict(json.loads(s))


@dataclass
class PhaseInfo:
    """Current Phase Information"""

    phase: PhaseType
    cycle_number: int
    total_cycles: int
    phase_remaining_min: float
    led_type: str  # 'ir', 'white', 'dual'


class RecordingState:
    """
    Thread-safe Recording State Management mit DRIFT-KOMPENSATION.

    KRITISCH: Timing darf sich NICHT aufsummieren!
    Lösung: Messe vom ABSOLUTEN Start-Zeitpunkt, nicht vom letzten Frame!
    """

    def __init__(self):
        self._lock = threading.RLock()

        # Recording State
        self.status = RecordingStatus.IDLE

        # Frame Info
        self.current_frame = 0
        self.total_frames = 0

        # Timing - ABSOLUT vom Start gemessen!
        self.start_time = 0.0  # Absoluter Start-Zeitpunkt
        self.pause_time = 0.0
        self.total_pause_duration = 0.0
        self.last_frame_time = 0.0  # Nur für Statistik

        # Phase Info (optional)
        self.current_phase: PhaseInfo | None = None

        # Config
        self.config: RecordingConfig | None = None

    # ========================================================================
    # RECORDING STATUS
    # ========================================================================

    def get_status(self) -> RecordingStatus:
        """Gibt aktuellen Status zurück"""
        with self._lock:
            return self.status

    def set_status(self, status: RecordingStatus):
        """Setzt Status"""
        with self._lock:
            old_status = self.status
            self.status = status
            logger.info(f"Recording status: {old_status.value} -> {status.value}")

    def is_recording(self) -> bool:
        """Gibt zurück ob gerade recording läuft"""
        with self._lock:
            return self.status == RecordingStatus.RECORDING

    def is_paused(self) -> bool:
        """Gibt zurück ob paused"""
        with self._lock:
            return self.status == RecordingStatus.PAUSED

    def is_active(self) -> bool:
        """Gibt zurück ob recording oder paused"""
        with self._lock:
            return self.status in [RecordingStatus.RECORDING, RecordingStatus.PAUSED]

    # ========================================================================
    # CONFIGURATION
    # ========================================================================

    def set_config(self, config: RecordingConfig):
        """Setzt Recording-Konfiguration"""
        with self._lock:
            self.config = config

            # Berechne total frames
            # WICHTIG: Kein +1 für SYMMETRISCHE Phase-Verteilung!
            # Beispiel: 120s / 5s = 24 frames
            # Frames bei: t=0, 5, 10, ..., 115 (NICHT bei t=120!)
            # Bei 1-Min-Phasen:
            #   LIGHT (0-60s):  Frames 0-11  = 12 Frames (t=0, 5, ..., 55)
            #   DARK  (60-120s): Frames 12-23 = 12 Frames (t=60, 65, ..., 115)
            # → Gleiche Anzahl pro Phase!
            if config.duration_min == 0:
                # 0 is the open-ended sentinel used by ExperimentSchedule
                self.total_frames = 0
                logger.info(f"Config set: open-ended @ {config.interval_sec}s (runs until stopped)")
            else:
                total_sec = config.duration_min * 60
                self.total_frames = int(total_sec / config.interval_sec)
                logger.info(
                    f"Config set: {config.duration_min}min @ {config.interval_sec}s = {self.total_frames} frames"
                )

    def get_config(self) -> RecordingConfig | None:
        """Gibt Konfiguration zurück"""
        with self._lock:
            return self.config

    # ========================================================================
    # FRAME TRACKING
    # ========================================================================

    def get_frame_info(self) -> dict:
        """Gibt Frame-Informationen zurück"""
        with self._lock:
            return {
                "current_frame": self.current_frame,
                "total_frames": self.total_frames,
                "progress_percent": self.get_progress_percent(),
            }

    def increment_frame(self) -> int:
        """Inkrementiert Frame-Counter"""
        with self._lock:
            self.current_frame += 1
            self.last_frame_time = time.time()
            logger.debug(f"Frame captured: {self.current_frame}/{self.total_frames}")
            return self.current_frame

    def get_progress_percent(self) -> float:
        """Berechnet Progress in Prozent"""
        with self._lock:
            if self.total_frames == 0:
                return 0.0
            return (self.current_frame / self.total_frames) * 100.0

    def is_complete(self) -> bool:
        """Prüft ob Recording fertig ist"""
        with self._lock:
            if self.total_frames == 0:
                return False  # open-ended: runs until manually stopped
            return self.current_frame >= self.total_frames

    # ========================================================================
    # TIMING - MIT DRIFT-KOMPENSATION!
    # ========================================================================

    def start_recording(self):
        """Markiert Start des Recordings"""
        with self._lock:
            self.status = RecordingStatus.RECORDING
            self.start_time = time.time()  # ABSOLUTER Start-Zeitpunkt!
            self.current_frame = 0
            self.total_pause_duration = 0.0
            self.last_frame_time = self.start_time
            logger.info(f"Recording started at {self.start_time:.3f}")

    def pause_recording(self):
        """Pausiert Recording"""
        with self._lock:
            if self.status != RecordingStatus.RECORDING:
                return

            self.status = RecordingStatus.PAUSED
            self.pause_time = time.time()
            logger.info("Recording paused")

    def resume_recording(self):
        """Setzt Recording fort"""
        with self._lock:
            if self.status != RecordingStatus.PAUSED:
                return

            # Add pause duration
            pause_duration = time.time() - self.pause_time
            self.total_pause_duration += pause_duration

            self.status = RecordingStatus.RECORDING
            logger.info(f"Recording resumed (paused for {pause_duration:.1f}s)")

    def stop_recording(self):
        """Stoppt Recording"""
        with self._lock:
            self.status = RecordingStatus.STOPPING
            logger.info("Recording stopping...")

    def finish_recording(self):
        """Finalisiert Recording"""
        with self._lock:
            self.status = RecordingStatus.IDLE
            logger.info("Recording finished")

    def get_elapsed_time(self) -> float:
        """Gibt verstrichene Zeit zurück (ohne Pausen)"""
        with self._lock:
            if self.start_time == 0:
                return 0.0

            current_time = time.time()

            # If paused, don't count current pause
            if self.status == RecordingStatus.PAUSED:
                current_time = self.pause_time

            elapsed = current_time - self.start_time - self.total_pause_duration
            return max(0.0, elapsed)

    def get_remaining_time(self) -> float:
        """Gibt geschätzte verbleibende Zeit zurück"""
        with self._lock:
            if self.current_frame == 0 or self.total_frames == 0:
                return 0.0

            elapsed = self.get_elapsed_time()
            avg_time_per_frame = elapsed / self.current_frame
            remaining_frames = self.total_frames - self.current_frame

            return remaining_frames * avg_time_per_frame

    def get_time_until_next_frame(self) -> float:
        """
        Gibt Zeit bis zum nächsten Frame zurück.

        KRITISCH: Mit DRIFT-KOMPENSATION!

        Frame 0 sollte bei t=0s aufgenommen werden (sofort nach Recording-Start)
        Frame 1 sollte bei t=interval aufgenommen werden
        Frame N sollte bei t=N*interval aufgenommen werden

        Statt:  next_time = last_frame_time + interval  ❌ (drift summiert sich!)
        Jetzt:  next_time = start_time + (frame_number * interval)  ✅ (kein drift!)
        """
        with self._lock:
            if not self.config or self.start_time == 0:
                return 0.0

            # Berechne wann der AKTUELLE Frame sein sollte (absolut vom Start)
            # Frame 0 → t=0s, Frame 1 → t=5s, Frame 2 → t=10s, etc.
            expected_time_for_current_frame = self.current_frame * self.config.interval_sec

            # Aktuelle verstrichene Zeit (ohne Pausen)
            elapsed = self.get_elapsed_time()

            # Wie lange bis zum aktuellen Frame?
            time_until_next = expected_time_for_current_frame - elapsed

            # Only log when drift exceeds 30 s to avoid log spam during catch-up
            if time_until_next < -30:
                logger.warning(
                    f"Behind schedule! Expected frame {self.current_frame} at {expected_time_for_current_frame:.1f}s, "
                    f"but currently at {elapsed:.1f}s (drift: {-time_until_next:.1f}s)"
                )

            return max(0.0, time_until_next)

    def get_timing_info(self) -> dict:
        """
        Gibt detaillierte Timing-Informationen zurück.
        Wichtig für Drift-Analyse!
        """
        with self._lock:
            if not self.config or self.start_time == 0:
                return {}

            elapsed = self.get_elapsed_time()
            expected_elapsed = self.current_frame * self.config.interval_sec
            drift = elapsed - expected_elapsed

            return {
                "elapsed_time": elapsed,
                "expected_elapsed": expected_elapsed,
                "drift_sec": drift,
                "current_frame": self.current_frame,
                "total_frames": self.total_frames,
                "interval_sec": self.config.interval_sec,
                "avg_interval": elapsed / self.current_frame if self.current_frame > 0 else 0.0,
                "on_schedule": abs(drift) < 1.0,  # Weniger als 1 sec drift = OK
            }

    # ========================================================================
    # PHASE MANAGEMENT
    # ========================================================================

    def set_phase(self, phase_info: PhaseInfo):
        """Setzt aktuelle Phase"""
        with self._lock:
            self.current_phase = phase_info
            logger.info(
                f"Phase: {phase_info.phase.value} (cycle {phase_info.cycle_number}/{phase_info.total_cycles})"
            )

    def get_phase(self) -> PhaseInfo | None:
        """Gibt aktuelle Phase zurück"""
        with self._lock:
            return self.current_phase

    def clear_phase(self):
        """Löscht Phase-Info"""
        with self._lock:
            self.current_phase = None

    # ========================================================================
    # SNAPSHOT
    # ========================================================================

    def get_snapshot(self) -> dict:
        """Gibt kompletten State-Snapshot zurück"""
        with self._lock:
            snapshot = {
                "status": self.status.value,
                "recording": self.is_recording(),
                "paused": self.is_paused(),
                "current_frame": self.current_frame,
                "total_frames": self.total_frames,
                "progress_percent": self.get_progress_percent(),
                "elapsed_time": self.get_elapsed_time(),
                "remaining_time": self.get_remaining_time(),
                "time_until_next_frame": self.get_time_until_next_frame(),
            }

            # Add timing info
            timing_info = self.get_timing_info()
            if timing_info:
                snapshot["timing"] = timing_info

            # Add phase info if available
            if self.current_phase:
                snapshot["phase"] = {
                    "phase": self.current_phase.phase.value,
                    "cycle_number": self.current_phase.cycle_number,
                    "total_cycles": self.current_phase.total_cycles,
                    "phase_remaining_min": self.current_phase.phase_remaining_min,
                    "led_type": self.current_phase.led_type,
                }

            return snapshot
