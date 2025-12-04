"""
Data Manager - Refactored HDF5-Based System

Combines the proven HDF5 storage approach with improved architecture:
- Raw numpy arrays in HDF5 (uncompressed, like before)
- Comprehensive chunked timeseries tracking
- Phase-aware recording
- Configurable telemetry modes
- Better error handling and statistics
- Clean modular design
"""

import json
import logging
import threading
import time
from enum import IntEnum
from pathlib import Path
from typing import Any, Optional

import h5py
import numpy as np

logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS AND CONFIGURATION
# ============================================================================


class TelemetryMode(IntEnum):
    """Telemetry detail level for timeseries datasets"""

    MINIMAL = 1  # ~15 essential fields
    STANDARD = 2  # ~40 fields (recommended)
    COMPREHENSIVE = 3  # All ~53 fields


# ============================================================================
# CHUNKED TIMESERIES WRITER
# ============================================================================


class ChunkedTimeseriesWriter:
    """
    Optimized chunked timeseries writer for HDF5.
    Creates extendable 1-D datasets with fixed chunk sizes.
    Supports configurable field filtering via telemetry mode.
    """

    # LED and Phase enums
    LED_TYPE_ENUM = {"ir": 0, "white": 1}
    PHASE_ENUM = {"dark": 0, "light": 1, "continuous": 2}

    def __init__(
        self,
        timeseries_group: h5py.Group,
        chunk_size: int = 512,
        mode: TelemetryMode = TelemetryMode.STANDARD,
    ):
        self.g = timeseries_group
        self.chunk_size = int(chunk_size)
        self.mode = mode
        self._lock = threading.RLock()
        self.ds = {}
        self.current_capacity = 0
        self.written_frames = 0

        # String type for HDF5
        str_vlen = h5py.string_dtype(encoding="utf-8")

        # ====================================================================
        # FIELD DEFINITIONS - Organized by category
        # ====================================================================

        # Essential fields (MINIMAL mode)
        minimal_fields = {
            "frame_index": np.int64,
            "recording_elapsed_sec": np.float64,
            "actual_intervals": np.float64,
            "expected_intervals": np.float64,
            "temperature_celsius": np.float32,
            "humidity_percent": np.float32,
            "led_type_str": str_vlen,
            "led_power": np.int16,
            "ir_led_power": np.int16,  # IR LED power (0-100%)
            "white_led_power": np.int16,  # White LED power (0-100%)
            "phase_str": str_vlen,
            "cycle_number": np.int32,
            "frame_mean_intensity": np.float32,
            "sync_success": np.int8,
        }

        # Standard additional fields (STANDARD mode)
        # Streamlined: Keep only useful fields, remove redundant/debug data
        standard_fields = {
            # Phase tracking
            "phase_transition": np.int8,  # Phase change indicator
            # Quality indicators
            "capture_method": str_vlen,  # How frame was captured
            # Timing drift tracking
            "cumulative_drift_sec": np.float32,  # Accumulated timing drift
        }

        # Removed redundant/debug fields:
        # ❌ "capture_timestamp_absolute" - duplicate of "timestamps"
        # ❌ "expected_elapsed_sec" - can calculate from frame_index * interval
        # ❌ "interval_error_sec" - can calculate: actual - expected
        # ❌ "operation_duration_sec" - debugging only
        # ❌ "led_stabilization_ms" - always 1000ms (constant)
        # ❌ "exposure_ms" - always same (camera setting)
        # ❌ "led_duration_ms" - can calculate if needed
        # ❌ "sync_timing_ms" - debugging only
        # ❌ "led_mode" - can infer from led_type
        # ❌ "phase_enabled" - obvious from data
        # ❌ "total_cycles" - same for all frames
        # ❌ "phase_elapsed_min" - can calculate from timestamps
        # ❌ "phase_remaining_min" - can calculate
        # ❌ "frame_std/min/max" - can calculate later if needed
        # ❌ "timeout_occurred" - sync_success is sufficient

        # Comprehensive additional fields (COMPREHENSIVE mode)
        comprehensive_fields = {
            "operation_start_absolute": np.float64,
            "operation_end_absolute": np.float64,
            "expected_timestamps": np.float64,
            "capture_timestamps": np.float64,
            "capture_elapsed_sec": np.float64,
            "frame_drift": np.float32,
            # Note: cumulative_drift_sec is inherited from standard_fields
            "capture_overhead_sec": np.float32,
            "capture_delay_sec": np.float32,
            "stabilization_ms": np.float32,
            "capture_delay_ms": np.int16,
            "camera_trigger_latency_ms": np.int16,
            "temperature": np.float32,
            "humidity": np.float32,
            "led_sync_success": np.int8,
            "transition_count": np.int32,
            "frame_mean": np.float32,
            "sync_quality": str_vlen,
        }

        # Select fields based on mode
        if mode == TelemetryMode.MINIMAL:
            fields = minimal_fields
        elif mode == TelemetryMode.STANDARD:
            fields = {**minimal_fields, **standard_fields}
        else:  # COMPREHENSIVE
            fields = {**minimal_fields, **standard_fields, **comprehensive_fields}

        # Create all datasets
        with self._lock:
            for name, dtype in fields.items():
                if name in self.g:
                    # Dataset exists (reopening file)
                    self.ds[name] = self.g[name]
                else:
                    # Create new dataset
                    self.ds[name] = self.g.create_dataset(
                        name,
                        shape=(0,),
                        maxshape=(None,),
                        chunks=(self.chunk_size,),
                        dtype=dtype,
                        compression=None,  # Uncompressed for speed
                        shuffle=False,
                        fletcher32=False,
                    )

            logger.info(
                f"Timeseries writer initialized: {len(self.ds)} datasets, mode={mode.name}, chunk_size={chunk_size}"
            )

    def _ensure_capacity(self, need_rows: int):
        """Ensure datasets have enough capacity"""
        if need_rows <= self.current_capacity:
            return
        new_cap = max(need_rows, self.current_capacity + self.chunk_size)
        for ds in self.ds.values():
            ds.resize((new_cap,))
        self.current_capacity = new_cap

    def append(
        self, frame_index: int, frame_metadata: dict, esp32_timing: dict, python_timing: dict
    ):
        """
        Append one row to all timeseries datasets.

        Args:
            frame_index: Frame index (0-based)
            frame_metadata: Frame-level metadata
            esp32_timing: ESP32 timing data
            python_timing: Python-side timing data
        """
        with self._lock:
            i = self.written_frames
            self._ensure_capacity(i + 1)

            # Extract data from dicts
            fm = frame_metadata or {}
            et = esp32_timing or {}
            pt = python_timing or {}

            # Helper to safely set dataset value
            def set_value(key, value):
                if key in self.ds:
                    self.ds[key][i] = value

            # ============================================================
            # INDICES
            # ============================================================
            set_value("frame_index", int(frame_index))

            # ============================================================
            # ABSOLUTE TIMESTAMPS - Removed timestamps field (use recording_elapsed_sec)
            # ============================================================
            # Calculate timestamp for COMPREHENSIVE mode only
            timestamp_abs = float(
                pt.get("capture_timestamp_absolute") or fm.get("timestamp") or time.time()
            )

            if self.mode == TelemetryMode.COMPREHENSIVE:
                set_value(
                    "operation_start_absolute",
                    float(pt.get("operation_start_absolute", timestamp_abs)),
                )
                set_value(
                    "operation_end_absolute", float(pt.get("operation_end_absolute", timestamp_abs))
                )
                set_value("expected_timestamps", float(pt.get("expected_time", timestamp_abs)))
                set_value("capture_timestamps", timestamp_abs)

            # ============================================================
            # RELATIVE TIMESTAMPS
            # ============================================================
            recording_elapsed = float(
                fm.get("recording_elapsed_sec")
                or pt.get("recording_elapsed_sec")
                or pt.get("capture_elapsed_sec")
                or 0.0
            )
            set_value("recording_elapsed_sec", recording_elapsed)

            if self.mode == TelemetryMode.COMPREHENSIVE:
                set_value(
                    "capture_elapsed_sec", float(pt.get("capture_elapsed_sec", recording_elapsed))
                )

            # ============================================================
            # INTERVALS
            # ============================================================
            actual_interval = float(pt.get("actual_interval_sec", np.nan))
            expected_interval = float(pt.get("expected_interval_sec", 5.0))

            set_value("actual_intervals", actual_interval)
            set_value("expected_intervals", expected_interval)

            # ============================================================
            # TIMING DRIFT (STANDARD and COMPREHENSIVE modes)
            # ============================================================
            if self.mode in [TelemetryMode.STANDARD, TelemetryMode.COMPREHENSIVE]:
                cumulative_drift = float(pt.get("cumulative_drift_sec", 0.0))
                set_value("cumulative_drift_sec", cumulative_drift)

            # ============================================================
            # OPERATION METRICS (removed - not needed)
            # ============================================================
            # All operation timing fields removed for streamlined mode

            if self.mode == TelemetryMode.COMPREHENSIVE:
                set_value("capture_overhead_sec", float(pt.get("capture_overhead_sec", np.nan)))
                set_value("capture_delay_sec", float(fm.get("capture_delay_sec", np.nan)))

            # ============================================================
            # ESP32 TIMING
            # ============================================================
            # Extract values for COMPREHENSIVE mode (constants, not saved in MINIMAL/STANDARD)
            if self.mode == TelemetryMode.COMPREHENSIVE:
                led_stab_ms = int(et.get("led_stabilization_ms", -1))
                set_value("stabilization_ms", led_stab_ms)
                set_value("capture_delay_ms", int(et.get("capture_delay_ms", -1)))
                set_value("camera_trigger_latency_ms", int(et.get("camera_trigger_latency_ms", -1)))

            # ============================================================
            # ENVIRONMENTAL DATA
            # ============================================================
            temp = float(et.get("temperature_celsius") or et.get("temperature", np.nan))
            humidity = float(et.get("humidity_percent") or et.get("humidity", np.nan))

            set_value("temperature_celsius", temp)
            set_value("humidity_percent", humidity)

            if self.mode == TelemetryMode.COMPREHENSIVE:
                set_value("temperature", temp)
                set_value("humidity", humidity)

            # ============================================================
            # LED STATE
            # ============================================================
            led_power = int(et.get("led_power_actual") or fm.get("led_power", -1))
            led_type_str = str(et.get("led_type_used") or fm.get("led_type", ""))

            # Per-LED powers (for phase-based recordings with per-phase calibration)
            ir_led_power = int(fm.get("ir_led_power", -1))
            white_led_power = int(fm.get("white_led_power", -1))

            set_value("led_power", led_power)
            set_value("ir_led_power", ir_led_power)
            set_value("white_led_power", white_led_power)
            set_value("led_type_str", led_type_str)  # Keep only string version, removed enum

            # Removed: led_mode (can infer from led_type: dual/ir/white)

            sync_success = bool(et.get("sync_success", True))
            set_value("sync_success", 1 if sync_success else 0)

            if self.mode == TelemetryMode.COMPREHENSIVE:
                set_value("led_sync_success", 1 if sync_success else 0)

            # Removed: timeout_occurred (sync_success is sufficient)

            # ============================================================
            # PHASE INFORMATION
            # ============================================================
            phase_str = str(fm.get("phase") or fm.get("current_phase", "continuous"))

            set_value("phase_str", phase_str)  # Keep only string version, removed enum
            set_value("cycle_number", int(fm.get("cycle_number", 0)))

            if self.mode >= TelemetryMode.STANDARD:
                # Keep only phase_transition (as requested)
                set_value("phase_transition", int(fm.get("phase_transition", False)))

            # Removed: phase_enabled, total_cycles, phase_elapsed_min, phase_remaining_min
            # These are either obvious from data or can be calculated

            if self.mode == TelemetryMode.COMPREHENSIVE:
                set_value("transition_count", int(fm.get("transition_count", 0)))

            # ============================================================
            # FRAME STATISTICS
            # ============================================================
            frame_mean = float(fm.get("frame_mean_intensity") or fm.get("frame_mean", 0.0))
            set_value("frame_mean_intensity", frame_mean)

            if self.mode == TelemetryMode.COMPREHENSIVE:
                set_value("frame_mean", frame_mean)

            # Removed: frame_std, frame_min, frame_max
            # These can be calculated post-hoc if needed

            # ============================================================
            # CAPTURE QUALITY
            # ============================================================
            if self.mode >= TelemetryMode.STANDARD:
                capture_method = str(fm.get("capture_method") or fm.get("source", "unknown"))
                set_value("capture_method", capture_method)

            if self.mode == TelemetryMode.COMPREHENSIVE:
                sync_quality = str(fm.get("sync_quality", "excellent"))
                set_value("sync_quality", sync_quality)

            self.written_frames += 1

    def flush(self):
        """Flush all datasets"""
        try:
            if self.g and self.g.file:
                self.g.file.flush()
        except Exception as e:
            logger.warning(f"Timeseries flush error: {e}")

    def trim_to_actual_size(self):
        """
        Trim all datasets to actual written size.
        Call this when recording is finished to remove excess allocated space.
        """
        try:
            if self.written_frames < self.current_capacity:
                logger.info(
                    f"Trimming datasets from {self.current_capacity} to {self.written_frames} frames"
                )
                for ds in self.ds.values():
                    ds.resize((self.written_frames,))
                self.current_capacity = self.written_frames
                logger.info(f"Timeseries datasets trimmed to {self.written_frames} frames")
        except Exception as e:
            logger.warning(f"Error trimming timeseries datasets: {e}")

    def get_stats(self) -> dict:
        """Get writer statistics"""
        return {
            "written_frames": self.written_frames,
            "current_capacity": self.current_capacity,
            "dataset_count": len(self.ds),
            "mode": self.mode.name,
            "chunk_size": self.chunk_size,
        }


# ============================================================================
# MAIN DATA MANAGER
# ============================================================================


class DataManager:
    """
    Refactored HDF5-based Data Manager.

    HDF5 Structure:
    experiment_name.h5
    ├── /images/
    │   ├── frame_000000 (dataset: raw numpy array, uncompressed)
    │   ├── frame_000001
    │   └── ...
    └── /timeseries/
        ├── frame_index
        ├── timestamps
        ├── recording_elapsed_sec
        ├── temperature_celsius
        ├── led_type
        ├── phase
        └── ... (15-19 datasets depending on mode)

    File-level attributes store recording metadata.
    """

    def __init__(
        self,
        telemetry_mode: TelemetryMode = TelemetryMode.STANDARD,
        chunk_size: int = 10,
        flush_interval: int = 10,
    ):
        """
        Args:
            telemetry_mode: Level of telemetry detail
            chunk_size: Chunk size for timeseries datasets
            flush_interval: Flush HDF5 buffers every N frames (default: 10)
        """
        self.telemetry_mode = telemetry_mode
        self.chunk_size = chunk_size
        self.flush_interval = flush_interval

        # HDF5 file
        self.hdf5_file: Optional[h5py.File] = None
        self.current_filepath: Optional[Path] = None
        self._hdf5_lock = threading.RLock()

        # Timeseries writer
        self._ts_writer: Optional[ChunkedTimeseriesWriter] = None

        # Counters
        self.frame_count = 0
        self._frames_since_flush = 0

        # Phase tracking (for transition detection)
        self._current_phase = None
        self._transition_count = 0

        # Timing
        self.recording_start_time = 0.0
        self.last_frame_time = 0.0
        self.cumulative_drift = 0.0

        # Metadata
        self.recording_metadata: dict[str, Any] = {}

        logger.info(
            f"DataManager initialized (HDF5, mode={telemetry_mode.name}, chunk={chunk_size}, flush_every={flush_interval} frames)"
        )

    def create_recording_file(
        self, output_dir: str, experiment_name: str, timestamped: bool = True
    ) -> str:
        """
        Create new HDF5 recording file.

        Args:
            output_dir: Output directory
            experiment_name: Experiment name
            timestamped: Add timestamp to filename

        Returns:
            Path to created file
        """
        with self._hdf5_lock:
            # Generate filename
            if timestamped:
                ts_tag = time.strftime("%Y%m%d_%H%M%S")
                filename = f"{experiment_name}_{ts_tag}.h5"
                output_path = Path(output_dir) / ts_tag
            else:
                filename = f"{experiment_name}.h5"
                output_path = Path(output_dir)

            output_path.mkdir(parents=True, exist_ok=True)
            self.current_filepath = output_path / filename

            try:
                # Create HDF5 file
                self.hdf5_file = h5py.File(self.current_filepath, "w")

                # Create groups
                self.hdf5_file.create_group("images")
                self.hdf5_file.create_group("timeseries")

                # File attributes
                self.hdf5_file.attrs["created"] = time.time()
                self.hdf5_file.attrs["created_human"] = time.strftime("%Y-%m-%d %H:%M:%S")
                self.hdf5_file.attrs["experiment_name"] = experiment_name
                self.hdf5_file.attrs["file_version"] = "5.0-refactored"
                self.hdf5_file.attrs["software"] = "nematostella-timelapse-refactored"
                self.hdf5_file.attrs["structure"] = "phase_aware_timeseries_chunked"
                self.hdf5_file.attrs["phase_support"] = True
                self.hdf5_file.attrs["memory_optimized"] = True
                self.hdf5_file.attrs["chunked_datasets"] = True
                self.hdf5_file.attrs["telemetry_mode"] = self.telemetry_mode.name
                self.hdf5_file.attrs["chunk_size"] = self.chunk_size

                # Initialize counters
                self.frame_count = 0
                self.recording_start_time = time.time()
                self.last_frame_time = 0.0
                self.cumulative_drift = 0.0

                # Initialize metadata
                self.recording_metadata = {
                    "start_time": self.recording_start_time,
                    "expected_frames": 0,
                    "actual_frames": 0,
                    "duration_minutes": 0,
                    "interval_seconds": 0,
                    "phase_enabled": False,
                    "telemetry_mode": self.telemetry_mode.name,
                }

                logger.info(f"HDF5 file created: {self.current_filepath}")

                return str(self.current_filepath)

            except Exception as e:
                logger.error(f"Failed to create HDF5 file: {e}")
                raise

    def set_recording_config(self, config: dict):
        """Store recording configuration"""
        self.recording_metadata.update(config)
        logger.debug(f"Recording config updated: {config}")

    def save_frame(self, frame: np.ndarray, frame_number: int, metadata: dict) -> bool:
        """
        Save frame with comprehensive metadata.

        Args:
            frame: Frame as numpy array
            frame_number: Frame number (1-based for display, but stored as 0-based index)
            metadata: Metadata dictionary

        Returns:
            True if successful
        """
        if not self.hdf5_file:
            logger.error("No HDF5 file open")
            return False

        frame_index = frame_number - 1  # Convert to 0-based
        current_time = time.time()

        with self._hdf5_lock:
            try:
                # Calculate timing metrics
                timing_metrics = self._calculate_timing_metrics(
                    frame_number, current_time, metadata
                )

                # Calculate frame statistics
                frame_stats = self._calculate_frame_statistics(frame)

                # Detect phase transition
                phase_metadata = self._process_phase_info(frame_number, metadata)

                # ============================================================
                # 1. SAVE IMAGE (uncompressed numpy array)
                # ============================================================
                images_group = self.hdf5_file["images"]
                frame_ds_name = f"frame_{frame_index:06d}"

                # Delete if exists (for idempotency)
                if frame_ds_name in images_group:
                    del images_group[frame_ds_name]

                # Create dataset (uncompressed)
                ds = images_group.create_dataset(frame_ds_name, data=frame, compression=None)

                # Essential attributes on frame dataset
                ds.attrs["timestamp"] = current_time
                ds.attrs["frame_number"] = frame_number
                ds.attrs["frame_index"] = frame_index
                ds.attrs["source"] = metadata.get("capture_method", "normal")

                # ============================================================
                # 2. SAVE TIMESERIES DATA
                # ============================================================
                if self._ts_writer is None:
                    self._create_timeseries_writer()

                # Prepare comprehensive metadata dict
                frame_metadata = {
                    **metadata,
                    **frame_stats,
                    **phase_metadata,
                    "frame_number": frame_number,
                    "frame_index": frame_index,
                    "timestamp": current_time,
                }

                # Split into categories for writer
                esp32_timing = {
                    "exposure_ms": metadata.get("exposure_ms", 10),
                    "led_stabilization_ms": metadata.get("led_stabilization_ms", 1000),
                    "led_duration_ms": metadata.get("led_duration_ms", 0),
                    "sync_timing_ms": metadata.get("led_timing_ms", 0),
                    "temperature_celsius": metadata.get("temperature", 0.0),
                    "humidity_percent": metadata.get("humidity", 0.0),
                    "led_power_actual": metadata.get(
                        "led_power_actual", metadata.get("led_power", -1)
                    ),
                    "led_type_used": metadata.get("led_type", "unknown"),
                    "sync_success": metadata.get("success", True),
                    "camera_trigger_latency_ms": metadata.get("camera_trigger_latency_ms", 20),
                }

                python_timing = timing_metrics

                # Append to timeseries
                self._ts_writer.append(
                    frame_index=frame_index,
                    frame_metadata=frame_metadata,
                    esp32_timing=esp32_timing,
                    python_timing=python_timing,
                )

                # Update counters
                self.frame_count += 1
                self.last_frame_time = current_time
                self._frames_since_flush += 1

                # Periodic flush to reduce timing spikes
                if self._frames_since_flush >= self.flush_interval:
                    self._ts_writer.flush()
                    self.hdf5_file.flush()
                    self._frames_since_flush = 0
                    logger.debug(f"HDF5 buffers flushed at frame {frame_number}")

                logger.debug(f"Frame {frame_number} saved (index={frame_index})")

                return True

            except Exception as e:
                logger.error(f"Failed to save frame {frame_number}: {e}")
                return False

    def _create_timeseries_writer(self):
        """Create timeseries writer"""
        try:
            ts_group = self.hdf5_file["timeseries"]
            self._ts_writer = ChunkedTimeseriesWriter(
                ts_group, chunk_size=self.chunk_size, mode=self.telemetry_mode
            )

            # Set group attributes
            ts_group.attrs["description"] = "Chunked timeseries data"
            ts_group.attrs["x_axis"] = "recording_elapsed_sec"
            ts_group.attrs["phase_support"] = True
            ts_group.attrs["chunk_size"] = self.chunk_size
            ts_group.attrs["telemetry_mode"] = self.telemetry_mode.name

            logger.info("Timeseries writer created")

        except Exception as e:
            logger.error(f"Failed to create timeseries writer: {e}")
            raise

    def _calculate_timing_metrics(
        self, frame_number: int, current_time: float, metadata: dict
    ) -> dict:
        """
        Calculate comprehensive timing metrics.

        Note: timing_error_sec includes frame capture duration (~6.5s constant offset).
        Use cumulative_drift_sec to see actual timing drift between frames.
        """

        # Get expected interval
        expected_interval = self.recording_metadata.get("interval_seconds", 5.0)

        # Calculate elapsed times
        recording_elapsed = current_time - self.recording_start_time
        expected_elapsed = (frame_number - 1) * expected_interval

        # Calculate intervals
        if frame_number == 1 or self.last_frame_time == 0:
            actual_interval = 0.0
            interval_error = 0.0
        else:
            actual_interval = current_time - self.last_frame_time
            interval_error = actual_interval - expected_interval

        # Calculate timing error
        # NOTE: This includes constant frame capture overhead (~6.5s)
        # The first frame starts at t=0 but finishes at t=6.5s
        # This is normal and expected behavior
        timing_error = recording_elapsed - expected_elapsed

        # Update cumulative drift
        if frame_number > 1:
            self.cumulative_drift += interval_error

        # Operation timing
        operation_start = metadata.get("capture_start", current_time)
        operation_duration = current_time - operation_start

        return {
            "capture_timestamp_absolute": current_time,
            "operation_start_absolute": operation_start,
            "operation_end_absolute": current_time,
            "recording_elapsed_sec": recording_elapsed,
            "capture_elapsed_sec": recording_elapsed,
            "expected_elapsed_sec": expected_elapsed,
            "expected_time": self.recording_start_time + expected_elapsed,
            "actual_interval_sec": actual_interval,
            "expected_interval_sec": expected_interval,
            "interval_error_sec": interval_error,
            "timing_error_sec": timing_error,
            "cumulative_drift_sec": self.cumulative_drift,
            "operation_duration_sec": operation_duration,
            "capture_overhead_sec": metadata.get("capture_duration", 0.0),
        }

    def _calculate_frame_statistics(self, frame: np.ndarray) -> dict:
        """Calculate frame statistics"""
        try:
            return {
                "frame_mean": float(np.mean(frame)),
                "frame_mean_intensity": float(np.mean(frame)),
                "frame_std": float(np.std(frame)),
                "frame_min": float(np.min(frame)),
                "frame_max": float(np.max(frame)),
            }
        except Exception as e:
            logger.warning(f"Frame statistics calculation failed: {e}")
            return {
                "frame_mean": 0.0,
                "frame_mean_intensity": 0.0,
                "frame_std": 0.0,
                "frame_min": 0.0,
                "frame_max": 0.0,
            }

    def _process_phase_info(self, frame_number: int, metadata: dict) -> dict:
        """Process phase information and detect transitions"""

        phase_enabled = metadata.get("phase_enabled", False)
        phase = metadata.get("phase", "continuous")
        cycle_number = metadata.get("cycle_number", 0)

        # Detect transition (simple inline tracking)
        is_transition = False
        if phase_enabled:
            if self._current_phase is None:
                self._current_phase = phase
            elif phase != self._current_phase:
                # Phase transition detected
                logger.info(
                    f"Phase transition #{self._transition_count + 1}: {self._current_phase} → {phase} (frame {frame_number}, cycle {cycle_number})"
                )
                self._current_phase = phase
                self._transition_count += 1
                is_transition = True

        return {
            "phase": phase,
            "cycle_number": cycle_number,
            "phase_transition": is_transition,
        }

    def flush_file(self):
        """Flush HDF5 file to disk"""
        try:
            if self._ts_writer:
                self._ts_writer.flush()
            if self.hdf5_file:
                self.hdf5_file.flush()
        except Exception as e:
            logger.warning(f"HDF5 flush error: {e}")

    def finalize_recording(self, final_info: dict) -> bool:
        """
        Finalize recording - save metadata and close file.

        Args:
            final_info: Final recording information

        Returns:
            True if successful
        """
        logger.info("Finalizing HDF5 recording...")

        try:
            with self._hdf5_lock:
                if not self.hdf5_file:
                    logger.warning("No HDF5 file to finalize")
                    return False

                # Update file attributes
                self.hdf5_file.attrs["actual_frames"] = self.frame_count
                self.hdf5_file.attrs["finalized"] = True
                self.hdf5_file.attrs["finalized_time"] = time.time()
                self.hdf5_file.attrs["total_phase_transitions"] = self._transition_count

                # Save recording metadata as file-level attributes
                self.recording_metadata.update(final_info)
                self.recording_metadata["actual_frames"] = self.frame_count

                # Store metadata as JSON in file attributes
                self.hdf5_file.attrs["recording_info"] = json.dumps(
                    self.recording_metadata, indent=2
                )

                # Trim timeseries datasets to actual size
                if self._ts_writer:
                    logger.info("Trimming timeseries datasets to actual frame count...")
                    self._ts_writer.trim_to_actual_size()

                    # Get timeseries stats after trimming
                    ts_stats = self._ts_writer.get_stats()
                    ts_group = self.hdf5_file["timeseries"]
                    ts_group.attrs["written_frames"] = ts_stats["written_frames"]
                    ts_group.attrs["dataset_count"] = ts_stats["dataset_count"]
                    ts_group.attrs["trimmed"] = True

                # Final flush
                self.flush_file()

                logger.info(f"Recording finalized successfully ({self.frame_count} frames)")

                # Close HDF5 file to allow external access
                logger.info("Closing HDF5 file to allow external access...")

                # Flush and close timeseries writer
                if self._ts_writer:
                    self._ts_writer.flush()
                    self._ts_writer = None

                # Close HDF5 file
                if self.hdf5_file:
                    self.hdf5_file.flush()
                    self.hdf5_file.close()
                    self.hdf5_file = None
                    logger.info("HDF5 file closed - ready for external analysis")

                return True

        except Exception as e:
            logger.error(f"Failed to finalize recording: {e}")
            return False

    def close_file(self):
        """Close HDF5 file"""
        try:
            with self._hdf5_lock:
                # Flush timeseries writer
                if self._ts_writer:
                    self._ts_writer.flush()
                    self._ts_writer = None

                # Close HDF5 file
                if self.hdf5_file:
                    self.hdf5_file.flush()
                    self.hdf5_file.close()
                    self.hdf5_file = None

                logger.info("HDF5 file closed")

        except Exception as e:
            logger.error(f"Error closing HDF5 file: {e}")

    def get_recording_directory(self) -> Optional[Path]:
        """Get recording directory path"""
        if self.current_filepath:
            return self.current_filepath.parent
        return None

    def get_recording_info(self) -> dict:
        """Get recording information"""
        return {
            **self.recording_metadata,
            "current_filepath": str(self.current_filepath) if self.current_filepath else None,
            "frames_saved": self.frame_count,
            "file_open": self.hdf5_file is not None,
            "total_phase_transitions": self._transition_count,
            "telemetry_mode": self.telemetry_mode.name,
        }

    def get_stats(self) -> dict:
        """Get current statistics"""
        stats = {
            "frames_saved": self.frame_count,
            "file_open": self.hdf5_file is not None,
            "recording_directory": (
                str(self.current_filepath.parent) if self.current_filepath else None
            ),
        }

        if self._ts_writer:
            stats["timeseries"] = self._ts_writer.get_stats()

        return stats

    def cleanup(self):
        """Cleanup resources"""
        logger.info("DataManager cleanup...")
        self.close_file()
        logger.info("DataManager cleanup complete")

    def __del__(self):
        """Ensure file is closed"""
        try:
            self.close_file()
        except Exception:
            pass


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def load_recording_info(filepath: str) -> Optional[dict]:
    """Load recording info from HDF5 file"""
    try:
        with h5py.File(filepath, "r") as f:
            # Load from file-level attributes
            if "recording_info" in f.attrs:
                return json.loads(f.attrs["recording_info"])
            # Fallback for old format
            elif "metadata" in f and "recording_info" in f["metadata"].attrs:
                return json.loads(f["metadata"].attrs["recording_info"])
            return None
    except Exception as e:
        logger.error(f"Failed to load recording info: {e}")
        return None


def get_recording_summary(filepath: str) -> dict:
    """Get summary of HDF5 recording"""
    try:
        with h5py.File(filepath, "r") as f:
            summary = {
                "filepath": filepath,
                "file_size_mb": Path(filepath).stat().st_size / (1024 * 1024),
                "created": f.attrs.get("created", 0),
                "experiment_name": f.attrs.get("experiment_name", "Unknown"),
                "file_version": f.attrs.get("file_version", "Unknown"),
                "telemetry_mode": f.attrs.get("telemetry_mode", "Unknown"),
                "total_frames": f.attrs.get("actual_frames", 0),
                "phase_support": f.attrs.get("phase_support", False),
                "groups": list(f.keys()),
            }

            if "images" in f:
                summary["image_count"] = len(f["images"].keys())

            if "timeseries" in f:
                ts = f["timeseries"]
                summary["timeseries_datasets"] = list(ts.keys())
                summary["timeseries_count"] = len(ts.keys())
                if "written_frames" in ts.attrs:
                    summary["timeseries_frames"] = ts.attrs["written_frames"]

            if "phase_analysis" in f:
                pa = f["phase_analysis"]
                summary["phase_transitions"] = pa.attrs.get("total_transitions", 0)
                summary["cycles_completed"] = pa.attrs.get("cycles_completed", 0)

            return summary

    except Exception as e:
        logger.error(f"Failed to get recording summary: {e}")
        return {"error": str(e)}
