# """Phase-aware data manager for HDF5 file storage and metadata management with day/night cycle support
# and memory optimization for 72-hour recordings – UNCOMPRESSED frames + full telemetry time-series."""

# import h5py
# import numpy as np
# import time
# import json
# import threading
# import logging
# from pathlib import Path
# from typing import Iterator
# from qtpy.QtCore import QObject
# import os, time
# from pathlib import Path
# try:
#     from qtpy.QtCore import pyqtSignal
# except ImportError:
#     from qtpy.QtCore import Signal as pyqtSignal

# logger = logging.getLogger(__name__)


# # =============================
# # Chunked time-series writer
# # =============================
# class ChunkedTimeseriesWriter:
#     """
#     Uncompressed, append-only time-series writer.
#     Creates extendable 1-D datasets (maxshape=None) with fixed chunks.
#     Stores both numeric enums *and* readable strings where useful.
#     """
#     ENUMS = {
#         "led_type": {"ir": 0, "white": 1},
#         "phase": {"dark": 0, "light": 1, "continuous": 2}
#     }

#     def __init__(self, timeseries_group: h5py.Group, chunk_size: int = 512):
#         self.g = timeseries_group
#         self.chunk_size = int(chunk_size)
#         self._lock = threading.RLock()
#         self.ds = {}
#         self.current_capacity = 0
#         self.written_frames = 0

#         str_vlen = h5py.string_dtype(encoding="utf-8")

#         # ============================================================================
#         # COMPREHENSIVE FIELD DEFINITIONS - matches recorder output
#         # ============================================================================
#         fields = {
#             # ============ INDICES ============
#             "frame_index": np.int64,

#             # ============ ABSOLUTE TIMESTAMPS (seconds since epoch) ============
#             "timestamps": np.float64,                    # Main absolute timestamp
#             "capture_timestamp_absolute": np.float64,    # Explicit name for clarity
#             "operation_start_absolute": np.float64,      # When capture operation started
#             "operation_end_absolute": np.float64,        # When operation finished
#             "expected_timestamps": np.float64,           # Legacy - expected absolute time
#             "capture_timestamps": np.float64,            # Legacy - actual absolute time

#             # ============ RELATIVE TIMESTAMPS (seconds since recording start) ============
#             "recording_elapsed_sec": np.float64,         # Time since recording began
#             "capture_elapsed_sec": np.float64,           # When frame was captured (relative)
#             "expected_elapsed_sec": np.float64,          # When it should have been (relative)

#             # ============ INTERVALS (seconds) ============
#             "actual_intervals": np.float64,              # Time since last frame
#             "expected_intervals": np.float64,            # Target interval (constant)
#             "interval_error_sec": np.float64,            # Deviation from target interval

#             # ============ TIMING ERRORS (seconds) ============
#             "timing_error_sec": np.float64,              # Early/late vs schedule
#             "frame_drift": np.float32,                   # Legacy name for timing_error
#             "cumulative_drift": np.float32,              # Total accumulated drift
#             "cumulative_drift_sec": np.float64,          # Higher precision version

#             # ============ OPERATION METRICS (seconds) ============
#             "operation_duration_sec": np.float32,        # How long capture took
#             "capture_overhead_sec": np.float32,          # Time beyond LED pulse
#             "capture_delay_sec": np.float32,             # When within pulse we captured

#             # ============ ESP32 TIMING (milliseconds) ============
#             "exposure_ms": np.float32,                   # Camera exposure time
#             "stabilization_ms": np.float32,              # LED stabilization time (legacy)
#             "led_stabilization_ms": np.float32,          # LED stabilization (preferred)
#             "sync_timing_ms": np.float32,                # Total sync duration
#             "led_duration_ms": np.float32,               # Actual LED on duration
#             "capture_delay_ms": np.int16,                # Delay within LED pulse (ms)
#             "camera_trigger_latency_ms": np.int16,       # Camera latency compensation

#             # ============ ENVIRONMENTAL DATA ============
#             "temperature": np.float32,                   # Temperature (legacy)
#             "temperature_celsius": np.float32,           # Temperature with explicit unit
#             "humidity": np.float32,                      # Humidity (legacy)
#             "humidity_percent": np.float32,              # Humidity with explicit unit

#             # ============ LED STATE ============
#             "led_power": np.int16,                       # LED power percent (-1 if unknown)
#             "led_type": np.int8,                         # Enum: ir=0, white=1
#             "led_type_str": str_vlen,                    # Human readable LED type
#             "led_mode": str_vlen,                        # 'single' or 'dual'
#             "led_sync_success": np.int8,                 # Sync successful? (legacy)
#             "sync_success": np.int8,                     # Sync successful? (preferred)
#             "timeout_occurred": np.int8,                 # Did timeout occur? 0/1

#             # ============ PHASE INFORMATION ============
#             "phase_enabled": np.int8,                    # Phase cycling enabled? 0/1
#             "phase": np.int8,                            # Enum: dark=0, light=1, continuous=2
#             "phase_str": str_vlen,                       # Human readable phase
#             "cycle_number": np.int32,                    # Current cycle number
#             "total_cycles": np.int32,                    # Total number of cycles
#             "phase_elapsed_min": np.float32,             # Minutes elapsed in current phase
#             "phase_remaining_min": np.float32,           # Minutes remaining in current phase
#             "phase_transition": np.int8,                 # Is this a transition frame? 0/1
#             "transition_count": np.int32,                # Total number of transitions so far

#             # ============ FRAME STATISTICS ============
#             "frame_mean": np.float32,                    # Mean pixel intensity (legacy)
#             "frame_mean_intensity": np.float32,          # Mean pixel intensity (preferred)
#             "frame_max": np.float32,                     # Maximum pixel value
#             "frame_min": np.float32,                     # Minimum pixel value
#             "frame_std": np.float32,                     # Standard deviation

#             # ============ CAPTURE QUALITY ============
#             "capture_method": str_vlen,                  # Capture source/method
#             "sync_quality": str_vlen,                    # 'excellent' or 'degraded'
#         }

#         # ============================================================================
#         # CREATE ALL DATASETS
#         # ============================================================================
#         with self._lock:
#             for name, dtype in fields.items():
#                 if name in self.g:
#                     # Dataset already exists (e.g., reopening file)
#                     ds = self.g[name]
#                     self.ds[name] = ds
#                 else:
#                     # Create new dataset
#                     self.ds[name] = self.g.create_dataset(
#                         name,
#                         shape=(0,),
#                         maxshape=(None,),
#                         chunks=(self.chunk_size,),
#                         dtype=dtype,
#                         compression=None,
#                         shuffle=False,
#                         fletcher32=False,
#                     )

#             # ========================================================================
#             # METADATA & ATTRIBUTES
#             # ========================================================================
#             self.g.attrs["schema_version"] = "4.0"  # Bumped version for new fields
#             self.g.attrs["enums_json"] = json.dumps(self.ENUMS)

#             # Annotate primary time axes for plotting
#             self.g.attrs["x_axis_primary"] = "recording_elapsed_sec"     # Main axis (relative time)
#             self.g.attrs["x_axis_secondary"] = "frame_index"             # Index axis
#             self.g.attrs["x_axis_absolute"] = "timestamps"               # Absolute time (epoch)

#             # Annotate units for key fields
#             units_map = {
#                 "recording_elapsed_sec": "seconds",
#                 "capture_elapsed_sec": "seconds",
#                 "expected_elapsed_sec": "seconds",
#                 "actual_intervals": "seconds",
#                 "expected_intervals": "seconds",
#                 "interval_error_sec": "seconds",
#                 "timing_error_sec": "seconds",
#                 "cumulative_drift_sec": "seconds",
#                 "operation_duration_sec": "seconds",
#                 "capture_overhead_sec": "seconds",
#                 "capture_delay_sec": "seconds",
#                 "exposure_ms": "milliseconds",
#                 "led_stabilization_ms": "milliseconds",
#                 "sync_timing_ms": "milliseconds",
#                 "led_duration_ms": "milliseconds",
#                 "capture_delay_ms": "milliseconds",
#                 "camera_trigger_latency_ms": "milliseconds",
#                 "temperature_celsius": "celsius",
#                 "humidity_percent": "percent",
#                 "led_power": "percent",
#                 "phase_elapsed_min": "minutes",
#                 "phase_remaining_min": "minutes",
#             }

#             for field, unit in units_map.items():
#                 self.g.attrs[f"units_{field}"] = unit

#             # Set capacity based on existing data
#             self.current_capacity = self.ds["frame_index"].shape[0]
#             self.written_frames = self.current_capacity

#             # Log initialization
#             if self.written_frames > 0:
#                 logger.info(f"Timeseries writer initialized with {self.written_frames} existing frames")
#             else:
#                 logger.info(f"Timeseries writer initialized (empty, chunk_size={self.chunk_size})")
#     # ---- helpers ----
#     @staticmethod
#     def _map_led_type(s: str) -> int:
#         if not s:
#             return -1
#         s = s.lower()
#         if s in ("ir", "infrared", "night"):
#             return 0
#         if s in ("white", "whitelight", "day", "cob"):
#             return 1
#         return -1

#     @staticmethod
#     def _map_phase(s: str, enabled: bool) -> int:
#         if not enabled:
#             return 2  # continuous
#         s = (s or "").lower()
#         if s == "dark":
#             return 0
#         if s == "light":
#             return 1
#         return -1

#     def _ensure_capacity(self, need_rows: int):
#         if need_rows <= self.current_capacity:
#             return
#         new_cap = max(need_rows, self.current_capacity + self.chunk_size)
#         for ds in self.ds.values():
#             ds.resize((new_cap,))
#         self.current_capacity = new_cap

#     # ---- append one row ----
#     def append(self, frame_index: int, frame_metadata: dict, esp32_timing: dict, python_timing: dict):
#         """
#         Append one row to all time-series datasets.
#         Maps comprehensive timing data from recorder to HDF5 fields.
#         """
#         with self._lock:
#             i = self.written_frames
#             self._ensure_capacity(i + 1)

#             # ================================================================
#             # EXTRACT DATA FROM INPUT DICTS
#             # ================================================================
#             fm = frame_metadata or {}
#             et = esp32_timing or {}
#             pt = python_timing or {}

#             # ================================================================
#             # ABSOLUTE TIMESTAMPS (seconds since epoch)
#             # ================================================================
#             timestamp_abs = float(
#                 pt.get("capture_timestamp_absolute") or
#                 fm.get("timestamp") or
#                 pt.get("start_time") or
#                 time.time()
#             )

#             operation_start_abs = float(
#                 pt.get("operation_start_absolute") or
#                 timestamp_abs
#             )

#             operation_end_abs = float(
#                 pt.get("operation_end_absolute") or
#                 timestamp_abs
#             )

#             expected_ts_abs = float(
#                 pt.get("expected_time") or
#                 timestamp_abs
#             )

#             # ================================================================
#             # RELATIVE TIMESTAMPS (seconds since recording start)
#             # ================================================================
#             recording_elapsed = float(
#                 fm.get("recording_elapsed_sec") or
#                 pt.get("capture_elapsed_sec") or
#                 0.0
#             )

#             capture_elapsed = float(
#                 pt.get("capture_elapsed_sec") or
#                 recording_elapsed
#             )

#             expected_elapsed = float(
#                 pt.get("expected_elapsed_sec") or
#                 0.0
#             )

#             # ================================================================
#             # INTERVALS (seconds)
#             # ================================================================
#             actual_interval = float(
#                 pt.get("actual_interval_sec") or
#                 pt.get("actual_interval") or
#                 np.nan
#             )

#             expected_interval = float(
#                 pt.get("expected_interval_sec") or
#                 pt.get("expected_interval") or
#                 5.0
#             )

#             interval_error = float(
#                 pt.get("interval_error_sec") or
#                 np.nan
#             )

#             # ================================================================
#             # TIMING ERRORS (seconds)
#             # ================================================================
#             timing_error = float(
#                 pt.get("timing_error_sec") or
#                 np.nan
#             )

#             frame_drift = float(
#                 pt.get("frame_drift") or
#                 timing_error  # Use timing_error as fallback
#             )

#             cumulative_drift = float(
#                 pt.get("cumulative_drift_sec") or
#                 pt.get("cumulative_drift") or
#                 0.0
#             )

#             # ================================================================
#             # OPERATION METRICS (seconds)
#             # ================================================================
#             operation_duration = float(
#                 pt.get("operation_duration_sec") or
#                 np.nan
#             )

#             capture_overhead = float(
#                 pt.get("capture_overhead_sec") or
#                 np.nan
#             )

#             capture_delay_sec = float(
#                 fm.get("capture_delay_sec") or
#                 et.get("capture_delay_sec") or
#                 np.nan
#             )

#             # ================================================================
#             # ESP32 TIMING (milliseconds)
#             # ================================================================
#             exposure_ms = float(
#                 et.get("exposure_ms") or
#                 np.nan
#             )

#             # LED stabilization - multiple possible names
#             led_stab_ms = float(
#                 et.get("led_stabilization_ms") or
#                 et.get("stabilization_ms") or
#                 np.nan
#             )

#             sync_timing_ms = float(
#                 et.get("sync_timing_ms") or
#                 et.get("timing_ms") or
#                 np.nan
#             )

#             led_duration_ms = float(
#                 et.get("led_duration_ms") or
#                 et.get("led_duration_actual") or
#                 sync_timing_ms
#             )

#             capture_delay_ms = int(
#                 et.get("capture_delay_ms") or
#                 -1
#             )

#             camera_latency_ms = int(
#                 et.get("camera_trigger_latency_ms") or
#                 -1
#             )

#             # ================================================================
#             # ENVIRONMENTAL DATA
#             # ================================================================
#             temp = float(
#                 et.get("temperature_celsius") or
#                 et.get("temperature") or
#                 fm.get("temperature_celsius") or
#                 fm.get("temperature") or
#                 np.nan
#             )

#             humidity = float(
#                 et.get("humidity_percent") or
#                 et.get("humidity") or
#                 fm.get("humidity_percent") or
#                 fm.get("humidity") or
#                 np.nan
#             )

#             # ================================================================
#             # LED STATE
#             # ================================================================
#             led_power = int(
#                 et.get("led_power_actual") or
#                 fm.get("led_power") or
#                 -1
#             )

#             led_type_str = str(
#                 et.get("led_type_used") or
#                 fm.get("led_type_used") or
#                 ""
#             )

#             led_mode = str(
#                 et.get("led_mode") or
#                 et.get("mode") or
#                 "single"
#             )

#             led_type_enum = self._map_led_type(led_type_str)

#             # Sync success flags
#             sync_success = int(
#                 et.get("sync_success", 1)  # Default to success
#             )

#             timeout_occurred = int(
#                 et.get("timeout_occurred", 0)  # Default to no timeout
#             )

#             # Legacy flag
#             led_sync_success = sync_success

#             # ================================================================
#             # PHASE INFORMATION
#             # ================================================================
#             phase_enabled = int(
#                 fm.get("phase_enabled", False)
#             )

#             phase_str = str(
#                 fm.get("current_phase") or
#                 "continuous"
#             )

#             phase_enum = self._map_phase(phase_str, bool(phase_enabled))

#             cycle_number = int(
#                 fm.get("cycle_number") or
#                 -1
#             )

#             total_cycles = int(
#                 fm.get("total_cycles") or
#                 -1
#             )

#             phase_elapsed = float(
#                 fm.get("phase_elapsed_min") or
#                 np.nan
#             )

#             phase_remaining = float(
#                 fm.get("phase_remaining_min") or
#                 np.nan
#             )

#             phase_transition = int(
#                 fm.get("phase_transition", False)
#             )

#             transition_count = int(
#                 fm.get("transition_count") or
#                 0
#             )

#             # ================================================================
#             # FRAME STATISTICS
#             # ================================================================
#             frame_mean = float(
#                 fm.get("frame_mean_intensity") or
#                 fm.get("frame_mean") or
#                 np.nan
#             )

#             frame_max = float(
#                 fm.get("frame_max") or
#                 np.nan
#             )

#             frame_min = float(
#                 fm.get("frame_min") or
#                 np.nan
#             )

#             frame_std = float(
#                 fm.get("frame_std") or
#                 np.nan
#             )

#             # ================================================================
#             # CAPTURE QUALITY
#             # ================================================================
#             capture_method = str(
#                 fm.get("source") or
#                 "unknown"
#             )

#             sync_quality = str(
#                 fm.get("sync_quality") or
#                 ("excellent" if sync_success else "degraded")
#             )

#             # ================================================================
#             # WRITE ALL FIELDS TO DATASETS
#             # ================================================================

#             # --- Indices ---
#             self.ds["frame_index"][i] = int(frame_index)

#             # --- Absolute timestamps ---
#             self.ds["timestamps"][i] = timestamp_abs
#             self.ds["capture_timestamp_absolute"][i] = timestamp_abs
#             self.ds["operation_start_absolute"][i] = operation_start_abs
#             self.ds["operation_end_absolute"][i] = operation_end_abs
#             self.ds["expected_timestamps"][i] = expected_ts_abs
#             self.ds["capture_timestamps"][i] = timestamp_abs  # Legacy

#             # --- Relative timestamps ---
#             self.ds["recording_elapsed_sec"][i] = recording_elapsed
#             self.ds["capture_elapsed_sec"][i] = capture_elapsed
#             self.ds["expected_elapsed_sec"][i] = expected_elapsed

#             # --- Intervals ---
#             self.ds["actual_intervals"][i] = actual_interval
#             self.ds["expected_intervals"][i] = expected_interval
#             self.ds["interval_error_sec"][i] = interval_error

#             # --- Timing errors ---
#             self.ds["timing_error_sec"][i] = timing_error
#             self.ds["frame_drift"][i] = frame_drift  # Legacy
#             self.ds["cumulative_drift"][i] = cumulative_drift  # Legacy
#             self.ds["cumulative_drift_sec"][i] = cumulative_drift

#             # --- Operation metrics ---
#             self.ds["operation_duration_sec"][i] = operation_duration
#             self.ds["capture_overhead_sec"][i] = capture_overhead
#             self.ds["capture_delay_sec"][i] = capture_delay_sec

#             # --- ESP32 timing ---
#             self.ds["exposure_ms"][i] = exposure_ms
#             self.ds["stabilization_ms"][i] = led_stab_ms  # Legacy
#             self.ds["led_stabilization_ms"][i] = led_stab_ms
#             self.ds["sync_timing_ms"][i] = sync_timing_ms
#             self.ds["led_duration_ms"][i] = led_duration_ms
#             self.ds["capture_delay_ms"][i] = capture_delay_ms
#             self.ds["camera_trigger_latency_ms"][i] = camera_latency_ms

#             # --- Environmental data ---
#             self.ds["temperature"][i] = temp  # Legacy
#             self.ds["temperature_celsius"][i] = temp
#             self.ds["humidity"][i] = humidity  # Legacy
#             self.ds["humidity_percent"][i] = humidity

#             # --- LED state ---
#             self.ds["led_power"][i] = led_power
#             self.ds["led_type"][i] = led_type_enum
#             self.ds["led_type_str"][i] = led_type_str
#             self.ds["led_mode"][i] = led_mode
#             self.ds["led_sync_success"][i] = led_sync_success  # Legacy
#             self.ds["sync_success"][i] = sync_success
#             self.ds["timeout_occurred"][i] = timeout_occurred

#             # --- Phase information ---
#             self.ds["phase_enabled"][i] = phase_enabled
#             self.ds["phase"][i] = phase_enum
#             self.ds["phase_str"][i] = phase_str
#             self.ds["cycle_number"][i] = cycle_number
#             self.ds["total_cycles"][i] = total_cycles
#             self.ds["phase_elapsed_min"][i] = phase_elapsed
#             self.ds["phase_remaining_min"][i] = phase_remaining
#             self.ds["phase_transition"][i] = phase_transition
#             self.ds["transition_count"][i] = transition_count

#             # --- Frame statistics ---
#             self.ds["frame_mean"][i] = frame_mean  # Legacy
#             self.ds["frame_mean_intensity"][i] = frame_mean
#             self.ds["frame_max"][i] = frame_max
#             self.ds["frame_min"][i] = frame_min
#             self.ds["frame_std"][i] = frame_std

#             # --- Capture quality ---
#             self.ds["capture_method"][i] = capture_method
#             self.ds["sync_quality"][i] = sync_quality

#             self.written_frames += 1


# # =============================
# # DataManager
# # =============================
# class DataManager(QObject):
#     """Phase-aware data manager: uncompressed frame storage + chunked telemetry time-series."""

#     UNITS = {
#         'time': 'seconds',
#         'temperature': 'celsius',
#         'humidity': 'percent',
#         'led_power': 'percent',
#         'led_duration': 'milliseconds',
#         'frame_drift': 'seconds',
#         'intervals': 'seconds',
#         'phase_duration': 'minutes',
#         'cycle_number': 'dimensionless'
#     }

#     # Signals
#     file_created = pyqtSignal(str)
#     frame_saved = pyqtSignal(int)
#     metadata_updated = pyqtSignal(dict)
#     error_occurred = pyqtSignal(str)
#     phase_transition_detected = pyqtSignal(dict)

#     def __init__(self):
#         super().__init__()
#         self.hdf5_file = None
#         self.current_filepath = None
#         self.frame_count = 0
#         self.recording_metadata = {}
#         self.expected_frame_interval = 5.0

#         self.last_phase = None
#         self.phase_transition_count = 0
#         self.cycle_count = 0

#         self._hdf5_lock = threading.Lock()
#         self._ts_writer: ChunkedTimeseriesWriter | None = None
#         self.datasets_created = False

#         self.last_timestamp = None
#         self.recording_start_time = None

#     # ----------------------------
#     # File lifecycle
#     # ----------------------------
#     def create_recording_file(self, output_dir: str, experiment_name: str = None,
#                               timestamped: bool = True) -> str:
#         print("=" * 60)
#         print(">>> DATAMANAGER: create_recording_file() CALLED")
#         print(f">>> Output dir: {output_dir}")
#         print(f">>> Experiment: {experiment_name}")
#         print(f">>> Timestamped: {timestamped}")
#         print("=" * 60)

#         with self._hdf5_lock:
#             if experiment_name is None:
#                 experiment_name = "nematostella_timelapse"

#             ts_tag = time.strftime("%Y%m%d_%H%M%S") if timestamped else ""
#             filename = f"{experiment_name}_{ts_tag}.h5" if ts_tag else f"{experiment_name}.h5"

#             output_path = Path(output_dir)
#             if timestamped:
#                 output_path = output_path / ts_tag
#             output_path.mkdir(parents=True, exist_ok=True)

#             self.current_filepath = output_path / filename

#             try:
#                 self.hdf5_file = h5py.File(self.current_filepath, "w")

#                 # groups
#                 self.hdf5_file.create_group("images")
#                 self.hdf5_file.create_group("metadata")
#                 self.hdf5_file.create_group("phase_analysis")
#                 self.hdf5_file.create_group("timeseries")

#                 # file attrs
#                 self.hdf5_file.attrs["created"] = time.time()
#                 self.hdf5_file.attrs["created_human"] = time.strftime("%Y-%m-%d %H:%M:%S")
#                 self.hdf5_file.attrs["experiment_name"] = experiment_name
#                 self.hdf5_file.attrs["file_version"] = "4.1"
#                 self.hdf5_file.attrs["software"] = "napari-timelapse-capture-phase-aware"
#                 self.hdf5_file.attrs["structure"] = "phase_aware_timeseries_chunked"
#                 self.hdf5_file.attrs["phase_support"] = True
#                 self.hdf5_file.attrs["memory_optimized"] = True
#                 self.hdf5_file.attrs["chunked_datasets"] = True

#                 # counters
#                 self.frame_count = 0
#                 self.phase_transition_count = 0
#                 self.cycle_count = 0
#                 self.last_phase = None
#                 self.datasets_created = False
#                 self._ts_writer = None

#                 # recording meta
#                 self.recording_metadata = {
#                     "start_time": time.time(),
#                     "expected_frames": 0,
#                     "actual_frames": 0,
#                     "duration_minutes": 0,
#                     "interval_seconds": 0,
#                     "led_power": 0,
#                     "camera_settings": {},
#                     "esp32_settings": {},
#                     "phase_enabled": False,
#                     "phase_config": {},
#                     "phase_transitions": 0,
#                     "cycles_completed": 0,
#                 }

#                 self.file_created.emit(str(self.current_filepath))
#                 logger.info(f"HDF5 created: {self.current_filepath}")
#                 return str(self.current_filepath)

#             except Exception as e:
#                 msg = f"Failed to create HDF5: {e}"
#                 self.error_occurred.emit(msg)
#                 raise RuntimeError(msg)

#     def is_file_open(self) -> bool:
#         return self.hdf5_file is not None

#     def flush_file(self):
#         """Sicheres Flushen – kann auch während der Aufnahme aufgerufen werden."""
#         try:
#             if getattr(self, "_ts_writer", None) and hasattr(self._ts_writer, "flush"):
#                 self._ts_writer.flush()
#             if self.hdf5_file is not None:
#                 self.hdf5_file.flush()
#         except Exception as e:
#             logger.warning(f"HDF5 flush warn: {e}")

#     def close_file(self):
#         """Beende alle Writer/Threads und schließe HDF5 wirklich."""
#         if getattr(self, "_closing", False):
#             return
#         self._closing = True
#         try:
#             # 1) ggf. eigenen Writer-Thread stoppen
#             if hasattr(self, "_writer_quit") and self._writer_quit:
#                 try:
#                     self._writer_quit.set()
#                 except Exception:
#                     pass
#             if hasattr(self, "_writer_thread") and self._writer_thread:
#                 try:
#                     self._writer_thread.join(timeout=5)
#                 except Exception:
#                     pass
#                 self._writer_thread = None

#             # 2) Timeseries-Writer schließen
#             if getattr(self, "_ts_writer", None):
#                 try:
#                     if hasattr(self._ts_writer, "close"):
#                         self._ts_writer.close()
#                     elif hasattr(self._ts_writer, "flush"):
#                         self._ts_writer.flush()
#                 except Exception as e:
#                     logger.warning(f"_ts_writer close warn: {e}")
#                 finally:
#                     self._ts_writer = None

#             # 3) HDF5 flush + close
#             if self.hdf5_file is not None:
#                 try:
#                     self.hdf5_file.flush()
#                 finally:
#                     try:
#                         self.hdf5_file.close()
#                     finally:
#                         self.hdf5_file = None
#             logger.info("HDF5 file closed cleanly")
#         finally:
#             self._closing = False

#     def __del__(self):
#         # Fallback falls der Nutzer nie close_file() ruft
#         try:
#             self.close_file()
#         except Exception:
#             pass

#     # ----------------------------
#     # Saving
#     # ----------------------------
#     def save_frame(self, frame: np.ndarray, frame_metadata: dict,
#                 esp32_timing: dict, python_timing: dict,
#                 memory_optimized: bool = True) -> bool:
#         """Save one frame + append telemetry. Images are UNCOMPRESSED.
#         Optimized for 72h recordings with aggressive memory management."""
#         if not self.hdf5_file:
#             raise RuntimeError("No HDF5 file open")

#         frame_num = self.frame_count
#         frame_ds_name = f"frame_{frame_num:06d}"

#         with self._hdf5_lock:
#             try:
#                 if frame is None or frame.size == 0:
#                     raise ValueError("Invalid frame: None or empty")

#                 images = self.hdf5_file["images"]

#                 # delete stale dataset (if any) for idempotency
#                 if frame_ds_name in images:
#                     try:
#                         del images[frame_ds_name]
#                     except Exception as e:
#                         logger.warning(f"Could not delete existing dataset {frame_ds_name}: {e}")

#                 # 1) write image UNCOMPRESSED (contiguous)
#                 ds = images.create_dataset(frame_ds_name, data=frame, compression=None)

#                 # essential attributes
#                 ts = float(frame_metadata.get("timestamp", time.time()))
#                 ds.attrs["timestamp"] = ts
#                 ds.attrs["frame_number"] = int(frame_num)
#                 ds.attrs["source"] = str(frame_metadata.get("source", "unknown"))

#                 if frame_metadata.get("phase_enabled", False):
#                     ds.attrs["current_phase"] = str(frame_metadata.get("current_phase", "continuous"))
#                     ds.attrs["led_type_used"] = str(frame_metadata.get("led_type_used", "ir"))
#                     ds.attrs["cycle_number"] = int(frame_metadata.get("cycle_number", 1))

#                 # 2) ensure time-series writer
#                 if frame_num == 0 and not self.datasets_created:
#                     self._create_chunked_timeseries_datasets()

#                 # 3) append telemetry (includes exposure/stabilization/sync/capture_delay)
#                 self._append_timeseries_data_chunked(frame_num, frame, frame_metadata, esp32_timing, python_timing)

#                 # 4) compact metadata JSON as attribute on the image dataset
#                 essential_metadata = self._create_essential_metadata(frame_num, frame_metadata, esp32_timing, python_timing)
#                 ds.attrs["metadata_json"] = json.dumps(essential_metadata, separators=(",", ":"))

#                 # 5) phase bookkeeping
#                 self._process_phase_transition_efficient(frame_num, frame_metadata)

#                 # 6) update counters
#                 self.frame_count += 1
#                 self.recording_metadata["actual_frames"] = self.frame_count

#                 # ================================================================
#                 # ✅ NEW: AGGRESSIVE FLUSHING for 72h recordings
#                 # ================================================================
#                 # Flush HDF5 buffer every frame (HDF5 batches internally)
#                 self.hdf5_file.flush()

#                 # ✅ NEW: Deep OS-level flush every 50 frames
#                 if frame_num % 50 == 0:
#                     try:
#                         # Force data to disk at OS level
#                         import os
#                         self.hdf5_file.flush()

#                         # OS-level sync (prevents data loss on crash)
#                         if hasattr(self.hdf5_file.id, 'get_vfd_handle'):
#                             try:
#                                 file_handle = self.hdf5_file.id.get_vfd_handle()
#                                 os.fsync(file_handle)
#                             except Exception:
#                                 pass

#                         logger.info(f"Frame {frame_num}: Deep flush to disk completed")
#                         print(f">>> Frame {frame_num}: Deep HDF5 flush to disk")
#                     except Exception as e:
#                         logger.debug(f"Deep flush skipped: {e}")

#                 # ================================================================
#                 # ✅ NEW: MEMORY MONITORING every 100 frames
#                 # ================================================================
#                 if frame_num % 100 == 0:
#                     self._log_memory_usage(frame_num)

#                     # ✅ NEW: Force garbage collection on memory milestones
#                     try:
#                         import gc
#                         collected = gc.collect()
#                         if collected > 0:
#                             logger.debug(f"Frame {frame_num}: GC collected {collected} objects")
#                     except Exception:
#                         pass

#                 self.frame_saved.emit(frame_num)
#                 return True

#             except Exception as e:
#                 msg = f"Save failed for frame {frame_num}: {e}"
#                 logger.error(msg)
#                 self.error_occurred.emit(msg)

#                 # cleanup half-created image dataset
#                 try:
#                     images = self.hdf5_file["images"]
#                     if frame_ds_name in images:
#                         del images[frame_ds_name]
#                 except Exception:
#                     pass

#                 return False

#             finally:
#                 # ================================================================
#                 # ✅ CRITICAL: Explicit cleanup for long recordings
#                 # ================================================================
#                 # Python's GC might not catch all references immediately
#                 # Explicitly delete local variables to free memory faster
#                 try:
#                     if 'ds' in locals():
#                         del ds
#                     if 'essential_metadata' in locals():
#                         del essential_metadata
#                 except Exception:
#                     pass

#     def save_frame_streaming(self, frame: np.ndarray, frame_metadata: dict,
#                             esp32_timing: dict, python_timing: dict) -> bool:
#         """Streaming save - always memory optimized."""
#         return self.save_frame(frame, frame_metadata, esp32_timing, python_timing, memory_optimized=True)

#     # ----------------------------
#     # Time-series creation/append
#     # ----------------------------
#     def _create_chunked_timeseries_datasets(self):
#         """Create/prepare the chunked, uncompressed time-series group + writer."""
#         if self.datasets_created:
#             return
#         try:
#             # be defensive: ensure the group exists
#             ts_group = self.hdf5_file.require_group("timeseries")

#             # attach writer (expects that ChunkedTimeseriesWriter already defines all datasets)
#             self._ts_writer = ChunkedTimeseriesWriter(ts_group, chunk_size=512)

#             # ✅ FIXED: Use CORRECT field names from the start!
#             ts_group.attrs["description"] = "Phase-aware time-series data (uncompressed, chunked)"
#             ts_group.attrs["x_axis"] = "recording_elapsed_sec"  # ✅ CORRECT!
#             ts_group.attrs["x_axis_alt"] = "frame_index"
#             ts_group.attrs["phase_support"] = True
#             ts_group.attrs["chunk_size"] = 512

#             # write known units from UNITS dict (if present)
#             if hasattr(self, "UNITS") and isinstance(self.UNITS, dict):
#                 for k, v in self.UNITS.items():
#                     ts_group.attrs[f"units_{k}"] = v

#             # ✅ FIXED: Correct unit name
#             ts_group.attrs.setdefault("units_recording_elapsed_sec", "seconds")

#             # ✅ NEW: Add other important units
#             ts_group.attrs.setdefault("units_capture_elapsed_sec", "seconds")
#             ts_group.attrs.setdefault("units_expected_elapsed_sec", "seconds")
#             ts_group.attrs.setdefault("units_actual_intervals", "seconds")
#             ts_group.attrs.setdefault("units_expected_intervals", "seconds")
#             ts_group.attrs.setdefault("units_interval_error_sec", "seconds")

#             self.datasets_created = True
#             logger.info("Time-series datasets created with correct schema")
#         except Exception as e:
#             msg = f"Error creating time-series datasets: {e}"
#             logger.error(msg)
#             self.error_occurred.emit(msg)


#     def _append_timeseries_data_chunked(
#         self,
#         frame_num: int,
#         frame: np.ndarray,
#         frame_metadata: dict,
#         esp32_timing: dict,
#         python_timing: dict,
#     ):
#         """
#         Append one row into chunked time-series.
#         Enriches metadata before passing to writer.
#         """
#         try:
#             # Ensure writer exists
#             if self._ts_writer is None:
#                 self._create_chunked_timeseries_datasets()
#             if self._ts_writer is None:
#                 raise RuntimeError("Timeseries writer not initialized")

#             # Calculate lightweight frame stats
#             stats = self._calculate_frame_stats_single_pass(frame)

#             # Copy and enrich frame_metadata
#             frame_metadata = dict(frame_metadata or {})

#             # ✅ ADD: Frame statistics
#             frame_metadata.setdefault("frame_mean", stats["mean"])
#             frame_metadata.setdefault("frame_mean_intensity", stats["mean"])
#             frame_metadata.setdefault("frame_max", stats["max"])
#             frame_metadata.setdefault("frame_min", stats["min"])
#             frame_metadata.setdefault("frame_std", stats["std"])

#             # ✅ ADD: Transition count
#             frame_metadata.setdefault("transition_count",
#                                     int(getattr(self, "phase_transition_count", 0)))

#             # ✅ NEW: Add recording_elapsed_sec (calculated from python_timing)
#             # This ensures the field is available even if recorder didn't set it
#             pt = python_timing or {}
#             if "recording_elapsed_sec" not in frame_metadata:
#                 # Try multiple sources
#                 recording_elapsed = (
#                     pt.get("capture_elapsed_sec") or
#                     pt.get("recording_elapsed_sec") or
#                     0.0
#                 )
#                 frame_metadata["recording_elapsed_sec"] = float(recording_elapsed)

#             # ✅ Simply pass all dicts to writer - it handles the rest
#             self._ts_writer.append(
#                 frame_index=frame_num,
#                 frame_metadata=frame_metadata,
#                 esp32_timing=esp32_timing,
#                 python_timing=python_timing,
#             )

#         except Exception as e:
#             logger.error(f"Timeseries append error: {e}")
#             raise  # Re-raise so save_frame knows it failed

#     # ----------------------------
#     # Helpers / metadata / finalize
#     # ----------------------------
#     def _create_essential_metadata(
#         self,
#         frame_num: int,
#         frame_metadata: dict,
#         esp32_timing: dict,
#         python_timing: dict,
#     ) -> dict:
#         """
#         Compact JSON attached to each /images/frame_XXXXXX dataset.
#         Includes all key timing and quality metrics.
#         """
#         fm = dict(frame_metadata or {})
#         et = dict(esp32_timing or {})
#         pt = dict(python_timing or {})

#         # Timestamps
#         now_ts = float(
#             fm.get("timestamp") or
#             pt.get("capture_timestamp_absolute") or
#             time.time()
#         )

#         # ✅ FIXED: Relative time calculation
#         # Try multiple sources in priority order
#         recording_elapsed = float(
#             pt.get("capture_elapsed_sec") or           # Primary source from recorder
#             fm.get("recording_elapsed_sec") or         # Backup from enriched metadata
#             pt.get("recording_elapsed_sec") or         # Legacy field
#             (now_ts - self.recording_start_time if self.recording_start_time else 0.0)  # Fallback calculation
#         )

#         essential = {
#             # ============ IDENTITY & TIMING ============
#             "frame_number": int(frame_num),
#             "timestamp": now_ts,
#             "recording_elapsed_sec": recording_elapsed,

#             # ============ INTERVALS ============
#             "actual_interval_sec": float(pt.get("actual_interval_sec", np.nan)),
#             "expected_interval_sec": float(pt.get("expected_interval_sec", 5.0)),
#             "interval_error_sec": float(pt.get("interval_error_sec", np.nan)),

#             # ============ TIMING QUALITY ============
#             "timing_error_sec": float(pt.get("timing_error_sec", np.nan)),
#             "cumulative_drift_sec": float(pt.get("cumulative_drift_sec", 0.0)),
#             "operation_duration_sec": float(pt.get("operation_duration_sec", np.nan)),

#             # ============ ESP32 TIMING ============
#             "exposure_ms": float(et.get("exposure_ms", np.nan)),
#             "led_stabilization_ms": float(et.get("led_stabilization_ms", np.nan)),
#             "led_duration_ms": float(et.get("led_duration_ms", np.nan)),
#             "capture_delay_sec": float(fm.get("capture_delay_sec", np.nan)),

#             # ============ LED STATE ============
#             "led_power": int(et.get("led_power_actual", fm.get("led_power", -1))),
#             "led_type_used": str(et.get("led_type_used") or fm.get("led_type_used") or ""),
#             "led_mode": str(et.get("led_mode", "single")),

#             # ============ ENVIRONMENT ============
#             "temperature_celsius": float(et.get("temperature_celsius") or et.get("temperature", np.nan)),
#             "humidity_percent": float(et.get("humidity_percent") or et.get("humidity", np.nan)),

#             # ============ QUALITY ============
#             "sync_success": bool(et.get("sync_success", True)),
#             "sync_quality": str(fm.get("sync_quality", "excellent")),
#             "capture_method": str(fm.get("source", "unknown")),

#             # ============ PHASE ============
#             "phase_enabled": bool(fm.get("phase_enabled", False)),
#         }

#         # Add phase details if enabled
#         if essential["phase_enabled"]:
#             essential.update({
#                 "current_phase": str(fm.get("current_phase", "continuous")),
#                 "cycle_number": int(fm.get("cycle_number", 1)),
#                 "phase_transition": bool(fm.get("phase_transition", False)),
#             })

#         return essential


#     def _calculate_frame_stats_single_pass(self, frame: np.ndarray) -> dict:
#         if frame is None or frame.size == 0:
#             return {"mean": 0.0, "max": 0.0, "min": 0.0, "std": 0.0}
#         try:
#             flat = frame.ravel()
#             return {
#                 "mean": float(np.mean(flat)),
#                 "min":  float(np.min(flat)),
#                 "max":  float(np.max(flat)),
#                 "std":  float(np.std(flat)),
#             }
#         except Exception as e:
#             logger.warning(f"Frame statistics calculation failed: {e}")
#             return {"mean": 0.0, "max": 0.0, "min": 0.0, "std": 0.0}


#     def _log_memory_usage(self, frame_num: int):
#         try:
#             import psutil
#             process = psutil.Process()
#             memory_mb = process.memory_info().rss / (1024 * 1024)
#             system_memory = psutil.virtual_memory()
#             logger.info(
#                 f"Frame {frame_num}: Process memory: {memory_mb:.1f}MB, "
#                 f"System available: {system_memory.available/(1024**3):.1f}GB"
#             )
#         except Exception:
#             pass


#     def _process_phase_transition_efficient(self, frame_num: int, frame_metadata: dict):
#         current_phase = frame_metadata.get("current_phase", "continuous")
#         is_transition = frame_metadata.get("phase_transition", False)

#         if is_transition and current_phase != self.last_phase:
#             self.phase_transition_count += 1
#             if self.last_phase == "light" and current_phase == "dark":
#                 self.cycle_count += 1

#             info = {
#                 "frame_number": frame_num,
#                 "timestamp": frame_metadata.get("timestamp", time.time()),
#                 "from_phase": self.last_phase or "initial",
#                 "to_phase": current_phase,
#                 "cycle_number": frame_metadata.get("cycle_number", 1),
#                 "transition_count": self.phase_transition_count,
#             }

#             try:
#                 g = self.hdf5_file["phase_analysis"].create_group(
#                     f"transition_{self.phase_transition_count:03d}"
#                 )
#                 for k, v in info.items():
#                     try:
#                         g.attrs[k] = v
#                     except (TypeError, ValueError):
#                         g.attrs[k] = str(v)

#                 self.phase_transition_detected.emit(info.copy())
#                 logger.info(f"Phase transition {self.phase_transition_count}: {self.last_phase} → {current_phase}")
#             except Exception as e:
#                 logger.error(f"Transition save error: {e}")

#         self.last_phase = current_phase


#     def update_recording_metadata(self, metadata: dict):
#         self.recording_metadata.update(metadata)

#         if "interval_seconds" in metadata:
#             old = self.expected_frame_interval
#             self.expected_frame_interval = metadata["interval_seconds"]
#             if isinstance(old, (int, float)):
#                 logger.info(f"Expected frame interval: {old:.1f}s → {self.expected_frame_interval:.1f}s")
#             else:
#                 logger.info(f"Expected frame interval set to: {self.expected_frame_interval:.1f}s")

#         if "phase_config" in metadata:
#             pc = metadata["phase_config"]
#             self.recording_metadata["phase_enabled"] = pc.get("enabled", False)
#             self.recording_metadata["light_duration_min"] = pc.get("light_duration_min", 0)
#             self.recording_metadata["dark_duration_min"] = pc.get("dark_duration_min", 0)
#             self.recording_metadata["starts_with_light"] = pc.get("start_with_light", True)

#         self.metadata_updated.emit(self.recording_metadata.copy())

#         if self.hdf5_file:
#             with self._hdf5_lock:
#                 for k, v in metadata.items():
#                     try:
#                         self.hdf5_file.attrs[k] = v
#                     except (TypeError, ValueError):
#                         self.hdf5_file.attrs[k] = json.dumps(v)


#     def finalize_recording(self):
#         print("\n" + "=" * 80)
#         print(">>> DATAMANAGER: finalize_recording() START")
#         print("=" * 80)
#         if not self.hdf5_file:
#             print(">>> No HDF5 file open, skipping")
#             return

#         with self._hdf5_lock:
#             try:
#                 # ---- update recording metadata ----
#                 self.recording_metadata["end_time"] = time.time()
#                 self.recording_metadata["total_duration"] = (
#                     self.recording_metadata["end_time"] - self.recording_metadata["start_time"]
#                 )
#                 self.recording_metadata["actual_frames"] = self.frame_count
#                 self.recording_metadata["phase_transitions"] = self.phase_transition_count
#                 self.recording_metadata["cycles_completed"] = self.cycle_count

#                 self.update_recording_metadata(self.recording_metadata)

#                 # ---- write timeseries-level attrs (if present) ----
#                 if "timeseries" in self.hdf5_file and self.frame_count > 0:
#                     ts = self.hdf5_file["timeseries"]
#                     ts.attrs["total_frames"] = self.frame_count
#                     ts.attrs["recording_duration"] = self.recording_metadata["total_duration"]
#                     ts.attrs["phase_transitions"] = self.phase_transition_count
#                     ts.attrs["cycles_completed"] = self.cycle_count
#                     ts.attrs["phase_enabled"] = self.recording_metadata.get("phase_enabled", False)

#                     # ✅ NEW: Set x-axis information
#                     ts.attrs["x_axis"] = "recording_elapsed_sec"
#                     ts.attrs["x_axis_alt"] = "frame_index"

#                     # ✅ NEW: Calculate and store actual time range from recorded data
#                     if "recording_elapsed_sec" in ts:
#                         try:
#                             elapsed_data = ts["recording_elapsed_sec"][:]
#                             if len(elapsed_data) > 0:
#                                 x_min = float(np.min(elapsed_data))
#                                 x_max = float(np.max(elapsed_data))
#                                 ts.attrs["x_axis_min"] = x_min
#                                 ts.attrs["x_axis_max"] = x_max
#                                 ts.attrs["actual_duration_sec"] = x_max - x_min
#                                 print(f">>> Timeseries range: {x_min:.3f}s to {x_max:.3f}s (duration: {x_max - x_min:.3f}s)")
#                                 logger.info(f"Timeseries x-axis range: {x_min:.1f}s to {x_max:.1f}s")
#                         except Exception as x_axis_e:
#                             logger.warning(f"Could not compute x-axis range: {x_axis_e}")
#                             print(f">>> Warning: X-axis range computation failed: {x_axis_e}")

#                     # ✅ NEW: Store frame index range
#                     if "frame_index" in ts:
#                         try:
#                             frame_idx = ts["frame_index"][:]
#                             if len(frame_idx) > 0:
#                                 ts.attrs["frame_index_min"] = int(np.min(frame_idx))
#                                 ts.attrs["frame_index_max"] = int(np.max(frame_idx))
#                                 print(f">>> Frame index range: {ts.attrs['frame_index_min']} to {ts.attrs['frame_index_max']}")
#                         except Exception as frame_e:
#                             logger.warning(f"Could not compute frame index range: {frame_e}")

#                     # Writer stats
#                     if self._ts_writer:
#                         ts.attrs["frames_written"] = self._ts_writer.written_frames
#                         ts.attrs["dataset_capacity"] = self._ts_writer.current_capacity

#                 self._finalize_phase_analysis()

#                 duration_hours = self.recording_metadata["total_duration"] / 3600
#                 phase_text = (
#                     f"({self.phase_transition_count} transitions, {self.cycle_count} cycles)"
#                     if self.recording_metadata.get("phase_enabled", False)
#                     else "(continuous mode)"
#                 )

#                 logger.info("=== PHASE-AWARE RECORDING FINALIZING ===")
#                 logger.info(f"Frames: {self.frame_count}")
#                 logger.info(f"Duration: {duration_hours:.1f} hours {phase_text}")
#                 logger.info(f"File: {self.current_filepath}")

#                 # ---- flush any writer, then flush & close HDF5 ----
#                 try:
#                     if self._ts_writer and hasattr(self._ts_writer, "flush"):
#                         self._ts_writer.flush()
#                 except Exception as e:
#                     logger.debug(f"Timeseries writer flush skipped: {e}")

#                 try:
#                     self.hdf5_file.flush()
#                 finally:
#                     self.hdf5_file.close()
#                     self.hdf5_file = None
#                     self._ts_writer = None

#             except Exception as e:
#                 msg = f"Error finalizing recording: {e}"
#                 logger.error(msg)
#                 self.error_occurred.emit(msg)
#             finally:
#                 # ---- durable OS flush + nudge Explorer, then log final size ----
#                 try:
#                     if self.current_filepath:
#                         import os
#                         from pathlib import Path

#                         # Force data to disk (works on Windows/Linux/Mac).
#                         with open(self.current_filepath, "ab") as fh:
#                             fh.flush()
#                             os.fsync(fh.fileno())

#                         # Nudge folder mtime so Explorer refreshes sooner.
#                         parent_dir = str(Path(self.current_filepath).parent)
#                         try:
#                             os.utime(parent_dir, None)
#                         except Exception:
#                             pass

#                         size_mb = Path(self.current_filepath).stat().st_size / (1024 * 1024)
#                         logger.info(f"Final file size on disk: {size_mb:.2f} MB")
#                         print(f">>> Final file size on disk: {size_mb:.2f} MB")
#                 except Exception as e:
#                     logger.debug(f"Post-close fsync/re-stat skipped: {e}")

#         print("=" * 80)
#         print(">>> DATAMANAGER: finalize_recording() COMPLETE")
#         print("=" * 80 + "\n")


#     def _finalize_phase_analysis(self):
#         try:
#             if "phase_analysis" in self.hdf5_file:
#                 g = self.hdf5_file["phase_analysis"]
#                 g.attrs["total_transitions"] = self.phase_transition_count
#                 g.attrs["total_cycles"] = self.cycle_count
#                 g.attrs["phase_enabled"] = self.recording_metadata.get("phase_enabled", False)
#                 if self.recording_metadata.get("phase_enabled", False):
#                     g.attrs["light_duration_min"] = self.recording_metadata.get("light_duration_min", 0)
#                     g.attrs["dark_duration_min"] = self.recording_metadata.get("dark_duration_min", 0)
#                     g.attrs["starts_with_light"] = self.recording_metadata.get("starts_with_light", True)
#         except Exception as e:
#             logger.error(f"Error finalizing phase analysis: {e}")


#     def get_recording_info(self) -> dict:
#         info = self.recording_metadata.copy()
#         info["current_filepath"]  = str(self.current_filepath) if self.current_filepath else None
#         info["frames_saved"]      = self.frame_count
#         info["file_open"]         = self.hdf5_file is not None
#         info["phase_transitions"] = getattr(self, "phase_transition_count", 0)
#         info["cycles_completed"]  = getattr(self, "cycle_count", 0)
#         info["memory_optimized"]  = True
#         info["chunked_operations"]= self._ts_writer is not None
#         return info

#     # ----------------------------
#     # Iterators / utilities
#     # ----------------------------
#     @staticmethod
#     def iter_frames(filepath: str, start_frame: int = 0, end_frame: int = None) -> Iterator[tuple]:
#         try:
#             with h5py.File(filepath, "r") as f:
#                 if "images" not in f:
#                     raise ValueError("No images group found in file")
#                 images = f["images"]
#                 frame_keys = sorted(k for k in images.keys() if k.startswith("frame_"))
#                 if end_frame is None:
#                     end_frame = len(frame_keys)
#                 for i in range(start_frame, min(end_frame, len(frame_keys))):
#                     k = frame_keys[i]
#                     arr = images[k][()]
#                     attrs = dict(images[k].attrs)
#                     yield i, arr, attrs
#         except Exception as e:
#             raise RuntimeError(f"Failed to iterate frames: {e}")

#     @staticmethod
#     def iter_phase_transitions(filepath: str) -> Iterator[dict]:
#         try:
#             with h5py.File(filepath, "r") as f:
#                 if "timeseries" not in f:
#                     return
#                 ts = f["timeseries"]
#                 if "phase_str" not in ts or "frame_index" not in ts:
#                     return
#                 phase_data = ts["phase_str"]
#                 frame_idx = ts["frame_index"]
#                 last = None
#                 for i in range(len(phase_data)):
#                     cur = phase_data[i]
#                     if isinstance(cur, bytes):
#                         cur = cur.decode("utf-8")
#                     if last is not None and cur != last:
#                         yield {
#                             "frame": int(frame_idx[i]),
#                             "from_phase": last,
#                             "to_phase": cur,
#                             "transition_index": i,
#                         }
#                     last = cur
#         except Exception as e:
#             raise RuntimeError(f"Failed to iterate phase transitions: {e}")

#     @staticmethod
#     def get_file_summary(filepath: str) -> dict:
#         try:
#             with h5py.File(filepath, "r") as f:
#                 summary = {
#                     "filepath": filepath,
#                     "created": f.attrs.get("created", 0),
#                     "created_human": f.attrs.get("created_human", "Unknown"),
#                     "experiment_name": f.attrs.get("experiment_name", "Unknown"),
#                     "file_version": f.attrs.get("file_version", "1.0"),
#                     "total_frames": f.attrs.get("actual_frames", 0),
#                     "duration_minutes": f.attrs.get("duration_minutes", 0),
#                     "interval_seconds": f.attrs.get("interval_seconds", 0),
#                     "groups": list(f.keys()),
#                     "file_size_mb": Path(filepath).stat().st_size / (1024 * 1024),
#                     "phase_support": f.attrs.get("phase_support", False),
#                     "phase_enabled": f.attrs.get("phase_enabled", False),
#                     "memory_optimized": f.attrs.get("memory_optimized", False),
#                     "chunked_datasets": f.attrs.get("chunked_datasets", False),
#                 }
#                 for gname in ["images", "metadata", "timeseries", "phase_analysis"]:
#                     if gname in f:
#                         summary[f"{gname}_count"] = len(f[gname].keys())
#                 if "timeseries" in f:
#                     ts = f["timeseries"]
#                     summary["timeseries_datasets"] = list(ts.keys())
#                     if "chunk_size" in ts.attrs:
#                         summary["chunk_size"] = ts.attrs["chunk_size"]
#                 return summary
#         except Exception as e:
#             raise RuntimeError(f"Failed to get file summary: {e}")

#     # ----------------------------
#     def force_memory_cleanup(self):
#         try:
#             import gc
#             if self.hdf5_file:
#                 with self._hdf5_lock:
#                     self.hdf5_file.flush()
#             collected = gc.collect()
#             logger.info(f"Forced memory cleanup: {collected} objects collected")
#             return collected > 0
#         except Exception as e:
#             logger.error(f"Memory cleanup error: {e}")
#             return False

#     @staticmethod
#     def fix_expected_intervals_in_file(filepath: str, expected_interval: float):
#         try:
#             with h5py.File(filepath, "r+") as f:
#                 if "timeseries" in f and "expected_intervals" in f["timeseries"]:
#                     ds = f["timeseries"]["expected_intervals"]
#                     old_vals = ds[:5] if len(ds) > 0 else []
#                     logger.info(f"Fixing {len(ds)} expected_intervals: first5={old_vals}, new={expected_interval}")
#                     ds[:] = expected_interval
#                     ds.attrs["fixed"] = True
#                     ds.attrs["fix_timestamp"] = time.time()
#                     ds.attrs["fix_description"] = f"Fixed to constant {expected_interval} seconds"
#                     return True
#                 else:
#                     logger.warning("No timeseries/expected_intervals found")
#                     return False
#         except Exception as e:
#             logger.error(f"Error fixing file: {e}")
#             return False
"""Phase-aware data manager for HDF5 file storage and metadata management with day/night cycle support
and memory optimization for 72-hour recordings – UNCOMPRESSED frames + full telemetry time-series.

Stufe 3 Filter: 40 Keys (entfernt 13 Redundanzen, behält alle wichtigen Daten)
"""

import h5py
import numpy as np
import time
import json
import threading
import logging
from pathlib import Path
from typing import Iterator
from qtpy.QtCore import QObject
import os, time
from pathlib import Path

try:
    from qtpy.QtCore import pyqtSignal
except ImportError:
    from qtpy.QtCore import Signal as pyqtSignal

logger = logging.getLogger(__name__)


# ================================================================
# TIMESERIES FILTER - Stufe 3: VOLLSTÄNDIG (40 Keys)
# Entfernt nur echte Redundanzen, behält alle wichtigen Daten
# ================================================================

REDUNDANT_TIMESERIES_KEYS = {
    # Timestamp duplicates (use capture_timestamp_absolute as primary)
    "capture_timestamps",  # → duplicate of capture_timestamp_absolute
    "timestamps",  # → duplicate of capture_timestamp_absolute
    # Unit duplicates (same value, different name)
    "cumulative_drift",  # → use cumulative_drift_sec (higher precision)
    "temperature",  # → use temperature_celsius (explicit unit)
    "humidity",  # → use humidity_percent (explicit unit)
    "stabilization_ms",  # → use led_stabilization_ms (consistent naming)
    "frame_mean",  # → use frame_mean_intensity (more descriptive)
    # Type duplicates (keep string version, remove int enum)
    "led_type",  # → use led_type_str (human readable)
    "phase",  # → use phase_str (human readable)
    # Unit conversion duplicates
    "capture_delay_ms",  # → use capture_delay_sec (consistent units)
    # Semantic duplicates
    "capture_elapsed_sec",  # → use recording_elapsed_sec (same meaning)
    "sync_success",  # → use led_sync_success (more specific)
    "led_mode",  # → use led_type_str (contains same info for dual)
}


def should_save_timeseries_key(key: str) -> bool:
    """
    Filter timeseries keys according to Stufe 3 (VOLLSTÄNDIG).

    Returns:
        True if key should be saved (40 keys)
        False if key is redundant (13 keys filtered)
    """
    return key not in REDUNDANT_TIMESERIES_KEYS


# =============================
# Chunked time-series writer
# =============================
class ChunkedTimeseriesWriter:
    """
    Uncompressed, append-only time-series writer with Stufe 3 filtering.
    Creates extendable 1-D datasets (maxshape=None) with fixed chunks.
    Stores both numeric enums *and* readable strings where useful.

    Stufe 3: Saves 40 keys, filters 13 redundant keys.
    """

    ENUMS = {"led_type": {"ir": 0, "white": 1}, "phase": {"dark": 0, "light": 1, "continuous": 2}}

    def __init__(self, timeseries_group: h5py.Group, chunk_size: int = 512):
        self.g = timeseries_group
        self.chunk_size = int(chunk_size)
        self._lock = threading.RLock()
        self.ds = {}
        self.current_capacity = 0
        self.written_frames = 0

        str_vlen = h5py.string_dtype(encoding="utf-8")

        # ============================================================================
        # COMPREHENSIVE FIELD DEFINITIONS - matches recorder output
        # ============================================================================
        fields = {
            # ============ INDICES ============
            "frame_index": np.int64,
            # ============ ABSOLUTE TIMESTAMPS (seconds since epoch) ============
            "timestamps": np.float64,  # Will be filtered (redundant)
            "capture_timestamp_absolute": np.float64,  # Primary timestamp
            "operation_start_absolute": np.float64,  # When capture operation started
            "operation_end_absolute": np.float64,  # When operation finished
            "expected_timestamps": np.float64,  # Expected absolute time
            "capture_timestamps": np.float64,  # Will be filtered (redundant)
            # ============ RELATIVE TIMESTAMPS (seconds since recording start) ============
            "recording_elapsed_sec": np.float64,  # Time since recording began (primary)
            "capture_elapsed_sec": np.float64,  # Will be filtered (redundant)
            "expected_elapsed_sec": np.float64,  # When it should have been (relative)
            # ============ INTERVALS (seconds) ============
            "actual_intervals": np.float64,  # Time since last frame
            "expected_intervals": np.float64,  # Target interval (constant)
            "interval_error_sec": np.float64,  # Deviation from target interval
            # ============ TIMING ERRORS (seconds) ============
            "timing_error_sec": np.float64,  # Early/late vs schedule
            "frame_drift": np.float32,  # Legacy name for timing_error
            "cumulative_drift": np.float32,  # Will be filtered (redundant)
            "cumulative_drift_sec": np.float64,  # Higher precision version
            # ============ OPERATION METRICS (seconds) ============
            "operation_duration_sec": np.float32,  # How long capture took
            "capture_overhead_sec": np.float32,  # Time beyond LED pulse
            "capture_delay_sec": np.float32,  # When within pulse we captured
            # ============ ESP32 TIMING (milliseconds) ============
            "exposure_ms": np.float32,  # Camera exposure time
            "stabilization_ms": np.float32,  # Will be filtered (redundant)
            "led_stabilization_ms": np.float32,  # LED stabilization (preferred)
            "sync_timing_ms": np.float32,  # Total sync duration
            "led_duration_ms": np.float32,  # Actual LED on duration
            "capture_delay_ms": np.int16,  # Will be filtered (redundant)
            "camera_trigger_latency_ms": np.int16,  # Camera latency compensation
            # ============ ENVIRONMENTAL DATA ============
            "temperature": np.float32,  # Will be filtered (redundant)
            "temperature_celsius": np.float32,  # Temperature with explicit unit
            "humidity": np.float32,  # Will be filtered (redundant)
            "humidity_percent": np.float32,  # Humidity with explicit unit
            # ============ LED STATE ============
            "led_power": np.int16,  # LED power percent (-1 if unknown)
            "led_type": np.int8,  # Will be filtered (redundant)
            "led_type_str": str_vlen,  # Human readable LED type
            "led_mode": str_vlen,  # Will be filtered (redundant)
            "led_sync_success": np.int8,  # Sync successful?
            "sync_success": np.int8,  # Will be filtered (redundant)
            "timeout_occurred": np.int8,  # Did timeout occur? 0/1
            # ============ PHASE INFORMATION ============
            "phase_enabled": np.int8,  # Phase cycling enabled? 0/1
            "phase": np.int8,  # Will be filtered (redundant)
            "phase_str": str_vlen,  # Human readable phase
            "cycle_number": np.int32,  # Current cycle number
            "total_cycles": np.int32,  # Total number of cycles
            "phase_elapsed_min": np.float32,  # Minutes elapsed in current phase
            "phase_remaining_min": np.float32,  # Minutes remaining in current phase
            "phase_transition": np.int8,  # Is this a transition frame? 0/1
            "transition_count": np.int32,  # Total number of transitions so far
            # ============ FRAME STATISTICS ============
            "frame_mean": np.float32,  # Will be filtered (redundant)
            "frame_mean_intensity": np.float32,  # Mean pixel intensity (preferred)
            "frame_max": np.float32,  # Maximum pixel value
            "frame_min": np.float32,  # Minimum pixel value
            "frame_std": np.float32,  # Standard deviation
            # ============ CAPTURE QUALITY ============
            "capture_method": str_vlen,  # Capture source/method
            "sync_quality": str_vlen,  # 'excellent' or 'degraded'
        }

        # ============================================================================
        # CREATE ALL DATASETS (with Stufe 3 filter)
        # ============================================================================
        with self._lock:
            created_count = 0
            filtered_count = 0

            for name, dtype in fields.items():
                # ✅ Apply Stufe 3 filter
                if not should_save_timeseries_key(name):
                    filtered_count += 1
                    logger.debug(f"Filtered redundant timeseries key: {name}")
                    continue

                if name in self.g:
                    # Dataset already exists (e.g., reopening file)
                    ds = self.g[name]
                    self.ds[name] = ds
                    created_count += 1
                else:
                    # Create new dataset
                    self.ds[name] = self.g.create_dataset(
                        name,
                        shape=(0,),
                        maxshape=(None,),
                        chunks=(self.chunk_size,),
                        dtype=dtype,
                        compression=None,
                        shuffle=False,
                        fletcher32=False,
                    )
                    created_count += 1

            # ✅ Log filter statistics
            total_fields = len(fields)
            reduction_percent = (filtered_count / total_fields * 100) if total_fields > 0 else 0

            logger.info(
                f"Timeseries datasets: {created_count} created, {filtered_count} filtered (Stufe 3)"
            )
            print(
                f">>> Timeseries datasets: {created_count} created, {filtered_count} redundant keys filtered"
            )
            print(f">>> Storage efficiency: {reduction_percent:.1f}% reduction")
            print(f">>> Keys saved: {list(self.ds.keys())[:10]}... ({len(self.ds)} total)")

            # ========================================================================
            # METADATA & ATTRIBUTES
            # ========================================================================
            self.g.attrs["schema_version"] = "4.1"  # Bumped for Stufe 3 filter
            self.g.attrs["filter_mode"] = "stufe_3_vollstaendig"
            self.g.attrs["keys_saved"] = created_count
            self.g.attrs["keys_filtered"] = filtered_count
            self.g.attrs["enums_json"] = json.dumps(self.ENUMS)

            # Annotate primary time axes for plotting
            self.g.attrs["x_axis_primary"] = "recording_elapsed_sec"  # Main axis (relative time)
            self.g.attrs["x_axis_secondary"] = "frame_index"  # Index axis
            self.g.attrs["x_axis_absolute"] = "capture_timestamp_absolute"  # Absolute time (epoch)

            # Annotate units for key fields
            units_map = {
                "recording_elapsed_sec": "seconds",
                "expected_elapsed_sec": "seconds",
                "actual_intervals": "seconds",
                "expected_intervals": "seconds",
                "interval_error_sec": "seconds",
                "timing_error_sec": "seconds",
                "cumulative_drift_sec": "seconds",
                "operation_duration_sec": "seconds",
                "capture_overhead_sec": "seconds",
                "capture_delay_sec": "seconds",
                "exposure_ms": "milliseconds",
                "led_stabilization_ms": "milliseconds",
                "sync_timing_ms": "milliseconds",
                "led_duration_ms": "milliseconds",
                "camera_trigger_latency_ms": "milliseconds",
                "temperature_celsius": "celsius",
                "humidity_percent": "percent",
                "led_power": "percent",
                "phase_elapsed_min": "minutes",
                "phase_remaining_min": "minutes",
            }

            for field, unit in units_map.items():
                if should_save_timeseries_key(field):
                    self.g.attrs[f"units_{field}"] = unit

            # Set capacity based on existing data
            if "frame_index" in self.ds:
                self.current_capacity = self.ds["frame_index"].shape[0]
                self.written_frames = self.current_capacity
            else:
                self.current_capacity = 0
                self.written_frames = 0

            # Log initialization
            if self.written_frames > 0:
                logger.info(
                    f"Timeseries writer initialized with {self.written_frames} existing frames"
                )
            else:
                logger.info(f"Timeseries writer initialized (empty, chunk_size={self.chunk_size})")

    # ---- helpers ----
    @staticmethod
    def _map_led_type(s: str) -> int:
        if not s:
            return -1
        s = s.lower()
        if s in ("ir", "infrared", "night"):
            return 0
        if s in ("white", "whitelight", "day", "cob"):
            return 1
        return -1

    @staticmethod
    def _map_phase(s: str, enabled: bool) -> int:
        if not enabled:
            return 2  # continuous
        s = (s or "").lower()
        if s == "dark":
            return 0
        if s == "light":
            return 1
        return -1

    def _ensure_capacity(self, need_rows: int):
        if need_rows <= self.current_capacity:
            return
        new_cap = max(need_rows, self.current_capacity + self.chunk_size)
        for ds in self.ds.values():
            ds.resize((new_cap,))
        self.current_capacity = new_cap

    # ---- append one row ----
    def append(
        self, frame_index: int, frame_metadata: dict, esp32_timing: dict, python_timing: dict
    ):
        """
        Append one row to all time-series datasets (with Stufe 3 filter).
        Maps comprehensive timing data from recorder to HDF5 fields.
        Only writes to datasets that passed the filter.
        """
        with self._lock:
            i = self.written_frames
            self._ensure_capacity(i + 1)

            # ================================================================
            # EXTRACT DATA FROM INPUT DICTS
            # ================================================================
            fm = frame_metadata or {}
            et = esp32_timing or {}
            pt = python_timing or {}

            # ================================================================
            # ABSOLUTE TIMESTAMPS (seconds since epoch)
            # ================================================================
            timestamp_abs = float(
                pt.get("capture_timestamp_absolute")
                or fm.get("timestamp")
                or pt.get("start_time")
                or time.time()
            )

            operation_start_abs = float(pt.get("operation_start_absolute") or timestamp_abs)

            operation_end_abs = float(pt.get("operation_end_absolute") or timestamp_abs)

            expected_ts_abs = float(pt.get("expected_time") or timestamp_abs)

            # ================================================================
            # RELATIVE TIMESTAMPS (seconds since recording start)
            # ================================================================
            recording_elapsed = float(
                fm.get("recording_elapsed_sec") or pt.get("capture_elapsed_sec") or 0.0
            )

            capture_elapsed = float(pt.get("capture_elapsed_sec") or recording_elapsed)

            expected_elapsed = float(pt.get("expected_elapsed_sec") or 0.0)

            # ================================================================
            # INTERVALS (seconds)
            # ================================================================
            actual_interval = float(
                pt.get("actual_interval_sec") or pt.get("actual_interval") or np.nan
            )

            expected_interval = float(
                pt.get("expected_interval_sec") or pt.get("expected_interval") or 5.0
            )

            interval_error = float(pt.get("interval_error_sec") or np.nan)

            # ================================================================
            # TIMING ERRORS (seconds)
            # ================================================================
            timing_error = float(pt.get("timing_error_sec") or np.nan)

            frame_drift = float(
                pt.get("frame_drift") or timing_error  # Use timing_error as fallback
            )

            cumulative_drift = float(
                pt.get("cumulative_drift_sec") or pt.get("cumulative_drift") or 0.0
            )

            # ================================================================
            # OPERATION METRICS (seconds)
            # ================================================================
            operation_duration = float(pt.get("operation_duration_sec") or np.nan)

            capture_overhead = float(pt.get("capture_overhead_sec") or np.nan)

            capture_delay_sec = float(
                fm.get("capture_delay_sec") or et.get("capture_delay_sec") or np.nan
            )

            # ================================================================
            # ESP32 TIMING (milliseconds)
            # ================================================================
            exposure_ms = float(et.get("exposure_ms") or np.nan)

            # LED stabilization - multiple possible names
            led_stab_ms = float(
                et.get("led_stabilization_ms") or et.get("stabilization_ms") or np.nan
            )

            sync_timing_ms = float(et.get("sync_timing_ms") or et.get("timing_ms") or np.nan)

            led_duration_ms = float(
                et.get("led_duration_ms") or et.get("led_duration_actual") or sync_timing_ms
            )

            capture_delay_ms = int(et.get("capture_delay_ms") or -1)

            camera_latency_ms = int(et.get("camera_trigger_latency_ms") or -1)

            # ================================================================
            # ENVIRONMENTAL DATA
            # ================================================================
            temp = float(
                et.get("temperature_celsius")
                or et.get("temperature")
                or fm.get("temperature_celsius")
                or fm.get("temperature")
                or np.nan
            )

            humidity = float(
                et.get("humidity_percent")
                or et.get("humidity")
                or fm.get("humidity_percent")
                or fm.get("humidity")
                or np.nan
            )

            # ================================================================
            # LED STATE
            # ================================================================
            led_power = int(et.get("led_power_actual") or fm.get("led_power") or -1)

            led_type_str = str(et.get("led_type_used") or fm.get("led_type_used") or "")

            led_mode = str(et.get("led_mode") or et.get("mode") or "single")

            led_type_enum = self._map_led_type(led_type_str)

            # Sync success flags
            sync_success = int(et.get("sync_success", 1))  # Default to success

            timeout_occurred = int(et.get("timeout_occurred", 0))  # Default to no timeout

            # Legacy flag
            led_sync_success = sync_success

            # ================================================================
            # PHASE INFORMATION
            # ================================================================
            phase_enabled = int(fm.get("phase_enabled", False))

            phase_str = str(fm.get("current_phase") or "continuous")

            phase_enum = self._map_phase(phase_str, bool(phase_enabled))

            cycle_number = int(fm.get("cycle_number") or -1)

            total_cycles = int(fm.get("total_cycles") or -1)

            phase_elapsed = float(fm.get("phase_elapsed_min") or np.nan)

            phase_remaining = float(fm.get("phase_remaining_min") or np.nan)

            phase_transition = int(fm.get("phase_transition", False))

            transition_count = int(fm.get("transition_count") or 0)

            # ================================================================
            # FRAME STATISTICS
            # ================================================================
            frame_mean = float(fm.get("frame_mean_intensity") or fm.get("frame_mean") or np.nan)

            frame_max = float(fm.get("frame_max") or np.nan)

            frame_min = float(fm.get("frame_min") or np.nan)

            frame_std = float(fm.get("frame_std") or np.nan)

            # ================================================================
            # CAPTURE QUALITY
            # ================================================================
            capture_method = str(fm.get("source") or "unknown")

            sync_quality = str(
                fm.get("sync_quality") or ("excellent" if sync_success else "degraded")
            )

            # ================================================================
            # WRITE ALL FIELDS TO DATASETS (with Stufe 3 filter)
            # ================================================================

            # Helper function for conditional write
            def write_if_allowed(key, value):
                """Only write if key passed Stufe 3 filter"""
                if key in self.ds:  # Dataset exists (wasn't filtered)
                    self.ds[key][i] = value

            # --- Indices ---
            write_if_allowed("frame_index", int(frame_index))

            # --- Absolute timestamps ---
            write_if_allowed("timestamps", timestamp_abs)  # Redundant - will be filtered
            write_if_allowed("capture_timestamp_absolute", timestamp_abs)
            write_if_allowed("operation_start_absolute", operation_start_abs)
            write_if_allowed("operation_end_absolute", operation_end_abs)
            write_if_allowed("expected_timestamps", expected_ts_abs)
            write_if_allowed("capture_timestamps", timestamp_abs)  # Redundant - will be filtered

            # --- Relative timestamps ---
            write_if_allowed("recording_elapsed_sec", recording_elapsed)
            write_if_allowed("capture_elapsed_sec", capture_elapsed)  # Redundant - will be filtered
            write_if_allowed("expected_elapsed_sec", expected_elapsed)

            # --- Intervals ---
            write_if_allowed("actual_intervals", actual_interval)
            write_if_allowed("expected_intervals", expected_interval)
            write_if_allowed("interval_error_sec", interval_error)

            # --- Timing errors ---
            write_if_allowed("timing_error_sec", timing_error)
            write_if_allowed("frame_drift", frame_drift)
            write_if_allowed("cumulative_drift", cumulative_drift)  # Redundant - will be filtered
            write_if_allowed("cumulative_drift_sec", cumulative_drift)

            # --- Operation metrics ---
            write_if_allowed("operation_duration_sec", operation_duration)
            write_if_allowed("capture_overhead_sec", capture_overhead)
            write_if_allowed("capture_delay_sec", capture_delay_sec)

            # --- ESP32 timing ---
            write_if_allowed("exposure_ms", exposure_ms)
            write_if_allowed("stabilization_ms", led_stab_ms)  # Redundant - will be filtered
            write_if_allowed("led_stabilization_ms", led_stab_ms)
            write_if_allowed("sync_timing_ms", sync_timing_ms)
            write_if_allowed("led_duration_ms", led_duration_ms)
            write_if_allowed("capture_delay_ms", capture_delay_ms)  # Redundant - will be filtered
            write_if_allowed("camera_trigger_latency_ms", camera_latency_ms)

            # --- Environmental data ---
            write_if_allowed("temperature", temp)  # Redundant - will be filtered
            write_if_allowed("temperature_celsius", temp)
            write_if_allowed("humidity", humidity)  # Redundant - will be filtered
            write_if_allowed("humidity_percent", humidity)

            # --- LED state ---
            write_if_allowed("led_power", led_power)
            write_if_allowed("led_type", led_type_enum)  # Redundant - will be filtered
            write_if_allowed("led_type_str", led_type_str)
            write_if_allowed("led_mode", led_mode)  # Redundant - will be filtered
            write_if_allowed("led_sync_success", led_sync_success)
            write_if_allowed("sync_success", sync_success)  # Redundant - will be filtered
            write_if_allowed("timeout_occurred", timeout_occurred)

            # --- Phase information ---
            write_if_allowed("phase_enabled", phase_enabled)
            write_if_allowed("phase", phase_enum)  # Redundant - will be filtered
            write_if_allowed("phase_str", phase_str)
            write_if_allowed("cycle_number", cycle_number)
            write_if_allowed("total_cycles", total_cycles)
            write_if_allowed("phase_elapsed_min", phase_elapsed)
            write_if_allowed("phase_remaining_min", phase_remaining)
            write_if_allowed("phase_transition", phase_transition)
            write_if_allowed("transition_count", transition_count)

            # --- Frame statistics ---
            write_if_allowed("frame_mean", frame_mean)  # Redundant - will be filtered
            write_if_allowed("frame_mean_intensity", frame_mean)
            write_if_allowed("frame_max", frame_max)
            write_if_allowed("frame_min", frame_min)
            write_if_allowed("frame_std", frame_std)

            # --- Capture quality ---
            write_if_allowed("capture_method", capture_method)
            write_if_allowed("sync_quality", sync_quality)

            self.written_frames += 1


# =============================
# DataManager
# =============================
class DataManager(QObject):
    """Phase-aware data manager: uncompressed frame storage + chunked telemetry time-series.

    Stufe 3 Filter: Saves 40 timeseries keys, filters 13 redundant keys.
    """

    UNITS = {
        "time": "seconds",
        "temperature": "celsius",
        "humidity": "percent",
        "led_power": "percent",
        "led_duration": "milliseconds",
        "frame_drift": "seconds",
        "intervals": "seconds",
        "phase_duration": "minutes",
        "cycle_number": "dimensionless",
    }

    # Signals
    file_created = pyqtSignal(str)
    frame_saved = pyqtSignal(int)
    metadata_updated = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    phase_transition_detected = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.hdf5_file = None
        self.current_filepath = None
        self.frame_count = 0
        self.recording_metadata = {}
        self.expected_frame_interval = 5.0

        self.last_phase = None
        self.phase_transition_count = 0
        self.cycle_count = 0

        self._hdf5_lock = threading.Lock()
        self._ts_writer: ChunkedTimeseriesWriter | None = None
        self.datasets_created = False

        self.last_timestamp = None
        self.recording_start_time = None

    # ----------------------------
    # File lifecycle
    # ----------------------------
    def create_recording_file(
        self, output_dir: str, experiment_name: str = None, timestamped: bool = True
    ) -> str:
        print("=" * 60)
        print(">>> DATAMANAGER: create_recording_file() CALLED")
        print(f">>> Output dir: {output_dir}")
        print(f">>> Experiment: {experiment_name}")
        print(f">>> Timestamped: {timestamped}")
        print(f">>> Filter mode: Stufe 3 (40 keys)")
        print("=" * 60)

        with self._hdf5_lock:
            if experiment_name is None:
                experiment_name = "nematostella_timelapse"

            ts_tag = time.strftime("%Y%m%d_%H%M%S") if timestamped else ""
            filename = f"{experiment_name}_{ts_tag}.h5" if ts_tag else f"{experiment_name}.h5"

            output_path = Path(output_dir)
            if timestamped:
                output_path = output_path / ts_tag
            output_path.mkdir(parents=True, exist_ok=True)

            self.current_filepath = output_path / filename

            try:
                self.hdf5_file = h5py.File(self.current_filepath, "w")

                # groups
                self.hdf5_file.create_group("images")
                self.hdf5_file.create_group("metadata")
                self.hdf5_file.create_group("phase_analysis")
                self.hdf5_file.create_group("timeseries")

                # file attrs
                self.hdf5_file.attrs["created"] = time.time()
                self.hdf5_file.attrs["created_human"] = time.strftime("%Y-%m-%d %H:%M:%S")
                self.hdf5_file.attrs["experiment_name"] = experiment_name
                self.hdf5_file.attrs["file_version"] = "4.1"
                self.hdf5_file.attrs["software"] = "napari-timelapse-capture-phase-aware"
                self.hdf5_file.attrs["structure"] = "phase_aware_timeseries_chunked"
                self.hdf5_file.attrs["phase_support"] = True
                self.hdf5_file.attrs["memory_optimized"] = True
                self.hdf5_file.attrs["chunked_datasets"] = True
                self.hdf5_file.attrs["filter_mode"] = "stufe_3_vollstaendig"
                self.hdf5_file.attrs["timeseries_keys_saved"] = 40
                self.hdf5_file.attrs["timeseries_keys_filtered"] = 13

                # counters
                self.frame_count = 0
                self.phase_transition_count = 0
                self.cycle_count = 0
                self.last_phase = None
                self.datasets_created = False
                self._ts_writer = None

                # recording meta
                self.recording_metadata = {
                    "start_time": time.time(),
                    "expected_frames": 0,
                    "actual_frames": 0,
                    "duration_minutes": 0,
                    "interval_seconds": 0,
                    "led_power": 0,
                    "camera_settings": {},
                    "esp32_settings": {},
                    "phase_enabled": False,
                    "phase_config": {},
                    "phase_transitions": 0,
                    "cycles_completed": 0,
                }

                self.file_created.emit(str(self.current_filepath))
                logger.info(f"HDF5 created: {self.current_filepath} (Stufe 3 filter)")
                return str(self.current_filepath)

            except Exception as e:
                msg = f"Failed to create HDF5: {e}"
                self.error_occurred.emit(msg)
                raise RuntimeError(msg)

    def is_file_open(self) -> bool:
        return self.hdf5_file is not None

    def flush_file(self):
        """Sicheres Flushen – kann auch während der Aufnahme aufgerufen werden."""
        try:
            if getattr(self, "_ts_writer", None) and hasattr(self._ts_writer, "flush"):
                self._ts_writer.flush()
            if self.hdf5_file is not None:
                self.hdf5_file.flush()
        except Exception as e:
            logger.warning(f"HDF5 flush warn: {e}")

    def close_file(self):
        """Beende alle Writer/Threads und schließe HDF5 wirklich."""
        if getattr(self, "_closing", False):
            return
        self._closing = True
        try:
            # 1) ggf. eigenen Writer-Thread stoppen
            if hasattr(self, "_writer_quit") and self._writer_quit:
                try:
                    self._writer_quit.set()
                except Exception:
                    pass
            if hasattr(self, "_writer_thread") and self._writer_thread:
                try:
                    self._writer_thread.join(timeout=5)
                except Exception:
                    pass
                self._writer_thread = None

            # 2) Timeseries-Writer schließen
            if getattr(self, "_ts_writer", None):
                try:
                    if hasattr(self._ts_writer, "close"):
                        self._ts_writer.close()
                    elif hasattr(self._ts_writer, "flush"):
                        self._ts_writer.flush()
                except Exception as e:
                    logger.warning(f"_ts_writer close warn: {e}")
                finally:
                    self._ts_writer = None

            # 3) HDF5 flush + close
            if self.hdf5_file is not None:
                try:
                    self.hdf5_file.flush()
                finally:
                    try:
                        self.hdf5_file.close()
                    finally:
                        self.hdf5_file = None
            logger.info("HDF5 file closed cleanly")
        finally:
            self._closing = False

    def __del__(self):
        # Fallback falls der Nutzer nie close_file() ruft
        try:
            self.close_file()
        except Exception:
            pass

    # ----------------------------
    # Saving
    # ----------------------------
    def save_frame(
        self,
        frame: np.ndarray,
        frame_metadata: dict,
        esp32_timing: dict,
        python_timing: dict,
        memory_optimized: bool = True,
    ) -> bool:
        """Save one frame + append telemetry. Images are UNCOMPRESSED.
        Optimized for 72h recordings with aggressive memory management."""
        if not self.hdf5_file:
            raise RuntimeError("No HDF5 file open")

        frame_num = self.frame_count
        frame_ds_name = f"frame_{frame_num:06d}"

        with self._hdf5_lock:
            try:
                if frame is None or frame.size == 0:
                    raise ValueError("Invalid frame: None or empty")

                images = self.hdf5_file["images"]

                # delete stale dataset (if any) for idempotency
                if frame_ds_name in images:
                    try:
                        del images[frame_ds_name]
                    except Exception as e:
                        logger.warning(f"Could not delete existing dataset {frame_ds_name}: {e}")

                # 1) write image UNCOMPRESSED (contiguous)
                ds = images.create_dataset(frame_ds_name, data=frame, compression=None)

                # essential attributes
                ts = float(frame_metadata.get("timestamp", time.time()))
                ds.attrs["timestamp"] = ts
                ds.attrs["frame_number"] = int(frame_num)
                ds.attrs["source"] = str(frame_metadata.get("source", "unknown"))

                if frame_metadata.get("phase_enabled", False):
                    ds.attrs["current_phase"] = str(
                        frame_metadata.get("current_phase", "continuous")
                    )
                    ds.attrs["led_type_used"] = str(frame_metadata.get("led_type_used", "ir"))
                    ds.attrs["cycle_number"] = int(frame_metadata.get("cycle_number", 1))

                # 2) ensure time-series writer
                if frame_num == 0 and not self.datasets_created:
                    self._create_chunked_timeseries_datasets()

                # 3) append telemetry (includes exposure/stabilization/sync/capture_delay)
                self._append_timeseries_data_chunked(
                    frame_num, frame, frame_metadata, esp32_timing, python_timing
                )

                # 4) compact metadata JSON as attribute on the image dataset
                essential_metadata = self._create_essential_metadata(
                    frame_num, frame_metadata, esp32_timing, python_timing
                )
                ds.attrs["metadata_json"] = json.dumps(essential_metadata, separators=(",", ":"))

                # 5) phase bookkeeping
                self._process_phase_transition_efficient(frame_num, frame_metadata)

                # 6) update counters
                self.frame_count += 1
                self.recording_metadata["actual_frames"] = self.frame_count

                # ================================================================
                # ✅ AGGRESSIVE FLUSHING for 72h recordings
                # ================================================================
                # Flush HDF5 buffer every frame (HDF5 batches internally)
                self.hdf5_file.flush()

                # ✅ Deep OS-level flush every 50 frames
                if frame_num % 50 == 0:
                    try:
                        # Force data to disk at OS level
                        import os

                        self.hdf5_file.flush()

                        # OS-level sync (prevents data loss on crash)
                        if hasattr(self.hdf5_file.id, "get_vfd_handle"):
                            try:
                                file_handle = self.hdf5_file.id.get_vfd_handle()
                                os.fsync(file_handle)
                            except Exception:
                                pass

                        logger.info(f"Frame {frame_num}: Deep flush to disk completed")
                        print(f">>> Frame {frame_num}: Deep HDF5 flush to disk")
                    except Exception as e:
                        logger.debug(f"Deep flush skipped: {e}")

                # ================================================================
                # ✅ MEMORY MONITORING every 100 frames
                # ================================================================
                if frame_num % 100 == 0:
                    self._log_memory_usage(frame_num)

                    # ✅ Force garbage collection on memory milestones
                    try:
                        import gc

                        collected = gc.collect()
                        if collected > 0:
                            logger.debug(f"Frame {frame_num}: GC collected {collected} objects")
                    except Exception:
                        pass

                self.frame_saved.emit(frame_num)
                return True

            except Exception as e:
                msg = f"Save failed for frame {frame_num}: {e}"
                logger.error(msg)
                self.error_occurred.emit(msg)

                # cleanup half-created image dataset
                try:
                    images = self.hdf5_file["images"]
                    if frame_ds_name in images:
                        del images[frame_ds_name]
                except Exception:
                    pass

                return False

            finally:
                # ================================================================
                # ✅ CRITICAL: Explicit cleanup for long recordings
                # ================================================================
                try:
                    if "ds" in locals():
                        del ds
                    if "essential_metadata" in locals():
                        del essential_metadata
                except Exception:
                    pass

    def save_frame_streaming(
        self, frame: np.ndarray, frame_metadata: dict, esp32_timing: dict, python_timing: dict
    ) -> bool:
        """Streaming save - always memory optimized."""
        return self.save_frame(
            frame, frame_metadata, esp32_timing, python_timing, memory_optimized=True
        )

    # ----------------------------
    # Time-series creation/append
    # ----------------------------
    def _create_chunked_timeseries_datasets(self):
        """Create/prepare the chunked, uncompressed time-series group + writer."""
        if self.datasets_created:
            return
        try:
            # be defensive: ensure the group exists
            ts_group = self.hdf5_file.require_group("timeseries")

            # attach writer (expects that ChunkedTimeseriesWriter already defines all datasets)
            self._ts_writer = ChunkedTimeseriesWriter(ts_group, chunk_size=512)

            # ✅ Use CORRECT field names from the start!
            ts_group.attrs["description"] = (
                "Phase-aware time-series data (uncompressed, chunked, Stufe 3 filtered)"
            )
            ts_group.attrs["x_axis"] = "recording_elapsed_sec"  # ✅ CORRECT!
            ts_group.attrs["x_axis_alt"] = "frame_index"
            ts_group.attrs["phase_support"] = True
            ts_group.attrs["chunk_size"] = 512
            ts_group.attrs["filter_mode"] = "stufe_3_vollstaendig"

            # write known units from UNITS dict (if present)
            if hasattr(self, "UNITS") and isinstance(self.UNITS, dict):
                for k, v in self.UNITS.items():
                    ts_group.attrs[f"units_{k}"] = v

            # ✅ Correct unit names
            ts_group.attrs.setdefault("units_recording_elapsed_sec", "seconds")
            ts_group.attrs.setdefault("units_expected_elapsed_sec", "seconds")
            ts_group.attrs.setdefault("units_actual_intervals", "seconds")
            ts_group.attrs.setdefault("units_expected_intervals", "seconds")
            ts_group.attrs.setdefault("units_interval_error_sec", "seconds")

            self.datasets_created = True
            logger.info("Time-series datasets created with Stufe 3 filter")
        except Exception as e:
            msg = f"Error creating time-series datasets: {e}"
            logger.error(msg)
            self.error_occurred.emit(msg)

    def _append_timeseries_data_chunked(
        self,
        frame_num: int,
        frame: np.ndarray,
        frame_metadata: dict,
        esp32_timing: dict,
        python_timing: dict,
    ):
        """
        Append one row into chunked time-series (with Stufe 3 filter).
        Enriches metadata before passing to writer.
        """
        try:
            # Ensure writer exists
            if self._ts_writer is None:
                self._create_chunked_timeseries_datasets()
            if self._ts_writer is None:
                raise RuntimeError("Timeseries writer not initialized")

            # Calculate lightweight frame stats
            stats = self._calculate_frame_stats_single_pass(frame)

            # Copy and enrich frame_metadata
            frame_metadata = dict(frame_metadata or {})

            # ✅ ADD: Frame statistics
            frame_metadata.setdefault("frame_mean", stats["mean"])
            frame_metadata.setdefault("frame_mean_intensity", stats["mean"])
            frame_metadata.setdefault("frame_max", stats["max"])
            frame_metadata.setdefault("frame_min", stats["min"])
            frame_metadata.setdefault("frame_std", stats["std"])

            # ✅ ADD: Transition count
            frame_metadata.setdefault(
                "transition_count", int(getattr(self, "phase_transition_count", 0))
            )

            # ✅ Add recording_elapsed_sec
            pt = python_timing or {}
            if "recording_elapsed_sec" not in frame_metadata:
                recording_elapsed = (
                    pt.get("capture_elapsed_sec") or pt.get("recording_elapsed_sec") or 0.0
                )
                frame_metadata["recording_elapsed_sec"] = float(recording_elapsed)

            # ✅ Simply pass all dicts to writer - it handles filtering
            self._ts_writer.append(
                frame_index=frame_num,
                frame_metadata=frame_metadata,
                esp32_timing=esp32_timing,
                python_timing=python_timing,
            )

        except Exception as e:
            logger.error(f"Timeseries append error: {e}")
            raise

    # ----------------------------
    # Helpers / metadata / finalize
    # ----------------------------
    def _create_essential_metadata(
        self,
        frame_num: int,
        frame_metadata: dict,
        esp32_timing: dict,
        python_timing: dict,
    ) -> dict:
        """
        Compact JSON attached to each /images/frame_XXXXXX dataset.
        Includes all key timing and quality metrics.
        """
        fm = dict(frame_metadata or {})
        et = dict(esp32_timing or {})
        pt = dict(python_timing or {})

        # Timestamps
        now_ts = float(fm.get("timestamp") or pt.get("capture_timestamp_absolute") or time.time())

        # ✅ FIXED: Relative time calculation
        recording_elapsed = float(
            pt.get("capture_elapsed_sec")
            or fm.get("recording_elapsed_sec")
            or pt.get("recording_elapsed_sec")
            or (now_ts - self.recording_start_time if self.recording_start_time else 0.0)
        )

        essential = {
            # ============ IDENTITY & TIMING ============
            "frame_number": int(frame_num),
            "timestamp": now_ts,
            "recording_elapsed_sec": recording_elapsed,
            # ============ INTERVALS ============
            "actual_interval_sec": float(pt.get("actual_interval_sec", np.nan)),
            "expected_interval_sec": float(pt.get("expected_interval_sec", 5.0)),
            "interval_error_sec": float(pt.get("interval_error_sec", np.nan)),
            # ============ TIMING QUALITY ============
            "timing_error_sec": float(pt.get("timing_error_sec", np.nan)),
            "cumulative_drift_sec": float(pt.get("cumulative_drift_sec", 0.0)),
            "operation_duration_sec": float(pt.get("operation_duration_sec", np.nan)),
            # ============ ESP32 TIMING ============
            "exposure_ms": float(et.get("exposure_ms", np.nan)),
            "led_stabilization_ms": float(et.get("led_stabilization_ms", np.nan)),
            "led_duration_ms": float(et.get("led_duration_ms", np.nan)),
            "capture_delay_sec": float(fm.get("capture_delay_sec", np.nan)),
            # ============ LED STATE ============
            "led_power": int(et.get("led_power_actual", fm.get("led_power", -1))),
            "led_type_used": str(et.get("led_type_used") or fm.get("led_type_used") or ""),
            "led_mode": str(et.get("led_mode", "single")),
            # ============ ENVIRONMENT ============
            "temperature_celsius": float(
                et.get("temperature_celsius") or et.get("temperature", np.nan)
            ),
            "humidity_percent": float(et.get("humidity_percent") or et.get("humidity", np.nan)),
            # ============ QUALITY ============
            "sync_success": bool(et.get("sync_success", True)),
            "sync_quality": str(fm.get("sync_quality", "excellent")),
            "capture_method": str(fm.get("source", "unknown")),
            # ============ PHASE ============
            "phase_enabled": bool(fm.get("phase_enabled", False)),
        }

        # Add phase details if enabled
        if essential["phase_enabled"]:
            essential.update(
                {
                    "current_phase": str(fm.get("current_phase", "continuous")),
                    "cycle_number": int(fm.get("cycle_number", 1)),
                    "phase_transition": bool(fm.get("phase_transition", False)),
                }
            )

        return essential

    def _calculate_frame_stats_single_pass(self, frame: np.ndarray) -> dict:
        if frame is None or frame.size == 0:
            return {"mean": 0.0, "max": 0.0, "min": 0.0, "std": 0.0}
        try:
            flat = frame.ravel()
            return {
                "mean": float(np.mean(flat)),
                "min": float(np.min(flat)),
                "max": float(np.max(flat)),
                "std": float(np.std(flat)),
            }
        except Exception as e:
            logger.warning(f"Frame statistics calculation failed: {e}")
            return {"mean": 0.0, "max": 0.0, "min": 0.0, "std": 0.0}

    def _log_memory_usage(self, frame_num: int):
        try:
            import psutil

            process = psutil.Process()
            memory_mb = process.memory_info().rss / (1024 * 1024)
            system_memory = psutil.virtual_memory()
            logger.info(
                f"Frame {frame_num}: Process memory: {memory_mb:.1f}MB, "
                f"System available: {system_memory.available/(1024**3):.1f}GB"
            )
        except Exception:
            pass

    def _process_phase_transition_efficient(self, frame_num: int, frame_metadata: dict):
        current_phase = frame_metadata.get("current_phase", "continuous")
        is_transition = frame_metadata.get("phase_transition", False)

        if is_transition and current_phase != self.last_phase:
            self.phase_transition_count += 1
            if self.last_phase == "light" and current_phase == "dark":
                self.cycle_count += 1

            info = {
                "frame_number": frame_num,
                "timestamp": frame_metadata.get("timestamp", time.time()),
                "from_phase": self.last_phase or "initial",
                "to_phase": current_phase,
                "cycle_number": frame_metadata.get("cycle_number", 1),
                "transition_count": self.phase_transition_count,
            }

            try:
                g = self.hdf5_file["phase_analysis"].create_group(
                    f"transition_{self.phase_transition_count:03d}"
                )
                for k, v in info.items():
                    try:
                        g.attrs[k] = v
                    except (TypeError, ValueError):
                        g.attrs[k] = str(v)

                self.phase_transition_detected.emit(info.copy())
                logger.info(
                    f"Phase transition {self.phase_transition_count}: {self.last_phase} → {current_phase}"
                )
            except Exception as e:
                logger.error(f"Transition save error: {e}")

        self.last_phase = current_phase

    def update_recording_metadata(self, metadata: dict):
        self.recording_metadata.update(metadata)

        if "interval_seconds" in metadata:
            old = self.expected_frame_interval
            self.expected_frame_interval = metadata["interval_seconds"]
            if isinstance(old, (int, float)):
                logger.info(
                    f"Expected frame interval: {old:.1f}s → {self.expected_frame_interval:.1f}s"
                )
            else:
                logger.info(f"Expected frame interval set to: {self.expected_frame_interval:.1f}s")

        if "phase_config" in metadata:
            pc = metadata["phase_config"]
            self.recording_metadata["phase_enabled"] = pc.get("enabled", False)
            self.recording_metadata["light_duration_min"] = pc.get("light_duration_min", 0)
            self.recording_metadata["dark_duration_min"] = pc.get("dark_duration_min", 0)
            self.recording_metadata["starts_with_light"] = pc.get("start_with_light", True)

        self.metadata_updated.emit(self.recording_metadata.copy())

        if self.hdf5_file:
            with self._hdf5_lock:
                for k, v in metadata.items():
                    try:
                        self.hdf5_file.attrs[k] = v
                    except (TypeError, ValueError):
                        self.hdf5_file.attrs[k] = json.dumps(v)

    def finalize_recording(self):
        print("\n" + "=" * 80)
        print(">>> DATAMANAGER: finalize_recording() START (Stufe 3)")
        print("=" * 80)
        if not self.hdf5_file:
            print(">>> No HDF5 file open, skipping")
            return

        with self._hdf5_lock:
            try:
                # ---- update recording metadata ----
                self.recording_metadata["end_time"] = time.time()
                self.recording_metadata["total_duration"] = (
                    self.recording_metadata["end_time"] - self.recording_metadata["start_time"]
                )
                self.recording_metadata["actual_frames"] = self.frame_count
                self.recording_metadata["phase_transitions"] = self.phase_transition_count
                self.recording_metadata["cycles_completed"] = self.cycle_count

                self.update_recording_metadata(self.recording_metadata)

                # ---- write timeseries-level attrs (if present) ----
                if "timeseries" in self.hdf5_file and self.frame_count > 0:
                    ts = self.hdf5_file["timeseries"]
                    ts.attrs["total_frames"] = self.frame_count
                    ts.attrs["recording_duration"] = self.recording_metadata["total_duration"]
                    ts.attrs["phase_transitions"] = self.phase_transition_count
                    ts.attrs["cycles_completed"] = self.cycle_count
                    ts.attrs["phase_enabled"] = self.recording_metadata.get("phase_enabled", False)

                    # ✅ Set x-axis information
                    ts.attrs["x_axis"] = "recording_elapsed_sec"
                    ts.attrs["x_axis_alt"] = "frame_index"

                    # ✅ Calculate actual time range from recorded data
                    if "recording_elapsed_sec" in ts:
                        try:
                            elapsed_data = ts["recording_elapsed_sec"][:]
                            if len(elapsed_data) > 0:
                                x_min = float(np.min(elapsed_data))
                                x_max = float(np.max(elapsed_data))
                                ts.attrs["x_axis_min"] = x_min
                                ts.attrs["x_axis_max"] = x_max
                                ts.attrs["actual_duration_sec"] = x_max - x_min
                                print(
                                    f">>> Timeseries range: {x_min:.3f}s to {x_max:.3f}s (duration: {x_max - x_min:.3f}s)"
                                )
                                logger.info(
                                    f"Timeseries x-axis range: {x_min:.1f}s to {x_max:.1f}s"
                                )
                        except Exception as x_axis_e:
                            logger.warning(f"Could not compute x-axis range: {x_axis_e}")

                    # ✅ Store frame index range
                    if "frame_index" in ts:
                        try:
                            frame_idx = ts["frame_index"][:]
                            if len(frame_idx) > 0:
                                ts.attrs["frame_index_min"] = int(np.min(frame_idx))
                                ts.attrs["frame_index_max"] = int(np.max(frame_idx))
                                print(
                                    f">>> Frame index range: {ts.attrs['frame_index_min']} to {ts.attrs['frame_index_max']}"
                                )
                        except Exception as frame_e:
                            logger.warning(f"Could not compute frame index range: {frame_e}")

                    # Writer stats
                    if self._ts_writer:
                        ts.attrs["frames_written"] = self._ts_writer.written_frames
                        ts.attrs["dataset_capacity"] = self._ts_writer.current_capacity

                        # ✅ NEW: Log filter stats
                        keys_saved = len(self._ts_writer.ds)
                        keys_filtered = len(REDUNDANT_TIMESERIES_KEYS)
                        ts.attrs["keys_saved"] = keys_saved
                        ts.attrs["keys_filtered"] = keys_filtered
                        print(f">>> Timeseries: {keys_saved} keys saved, {keys_filtered} filtered")

                self._finalize_phase_analysis()

                duration_hours = self.recording_metadata["total_duration"] / 3600
                phase_text = (
                    f"({self.phase_transition_count} transitions, {self.cycle_count} cycles)"
                    if self.recording_metadata.get("phase_enabled", False)
                    else "(continuous mode)"
                )

                logger.info("=== PHASE-AWARE RECORDING FINALIZING ===")
                logger.info(f"Frames: {self.frame_count}")
                logger.info(f"Duration: {duration_hours:.1f} hours {phase_text}")
                logger.info(f"File: {self.current_filepath}")
                logger.info(f"Filter: Stufe 3 (40 keys saved, 13 filtered)")

                # ---- flush any writer, then flush & close HDF5 ----
                try:
                    if self._ts_writer and hasattr(self._ts_writer, "flush"):
                        self._ts_writer.flush()
                except Exception as e:
                    logger.debug(f"Timeseries writer flush skipped: {e}")

                try:
                    self.hdf5_file.flush()
                finally:
                    self.hdf5_file.close()
                    self.hdf5_file = None
                    self._ts_writer = None

            except Exception as e:
                msg = f"Error finalizing recording: {e}"
                logger.error(msg)
                self.error_occurred.emit(msg)
            finally:
                # ---- durable OS flush + nudge Explorer, then log final size ----
                try:
                    if self.current_filepath:
                        import os
                        from pathlib import Path

                        # Force data to disk
                        with open(self.current_filepath, "ab") as fh:
                            fh.flush()
                            os.fsync(fh.fileno())

                        # Nudge folder mtime
                        parent_dir = str(Path(self.current_filepath).parent)
                        try:
                            os.utime(parent_dir, None)
                        except Exception:
                            pass

                        size_mb = Path(self.current_filepath).stat().st_size / (1024 * 1024)
                        logger.info(f"Final file size: {size_mb:.2f} MB (Stufe 3 optimized)")
                        print(f">>> Final file size: {size_mb:.2f} MB (Stufe 3: ~25% smaller)")
                except Exception as e:
                    logger.debug(f"Post-close fsync skipped: {e}")

        print("=" * 80)
        print(">>> DATAMANAGER: finalize_recording() COMPLETE")
        print("=" * 80 + "\n")

    def _finalize_phase_analysis(self):
        try:
            if "phase_analysis" in self.hdf5_file:
                g = self.hdf5_file["phase_analysis"]
                g.attrs["total_transitions"] = self.phase_transition_count
                g.attrs["total_cycles"] = self.cycle_count
                g.attrs["phase_enabled"] = self.recording_metadata.get("phase_enabled", False)
                if self.recording_metadata.get("phase_enabled", False):
                    g.attrs["light_duration_min"] = self.recording_metadata.get(
                        "light_duration_min", 0
                    )
                    g.attrs["dark_duration_min"] = self.recording_metadata.get(
                        "dark_duration_min", 0
                    )
                    g.attrs["starts_with_light"] = self.recording_metadata.get(
                        "starts_with_light", True
                    )
        except Exception as e:
            logger.error(f"Error finalizing phase analysis: {e}")

    def get_recording_info(self) -> dict:
        info = self.recording_metadata.copy()
        info["current_filepath"] = str(self.current_filepath) if self.current_filepath else None
        info["frames_saved"] = self.frame_count
        info["file_open"] = self.hdf5_file is not None
        info["phase_transitions"] = getattr(self, "phase_transition_count", 0)
        info["cycles_completed"] = getattr(self, "cycle_count", 0)
        info["memory_optimized"] = True
        info["chunked_operations"] = self._ts_writer is not None
        info["filter_mode"] = "stufe_3_vollstaendig"
        info["timeseries_keys"] = len(self._ts_writer.ds) if self._ts_writer else 0
        return info

    # ----------------------------
    # Iterators / utilities
    # ----------------------------
    @staticmethod
    def iter_frames(filepath: str, start_frame: int = 0, end_frame: int = None) -> Iterator[tuple]:
        try:
            with h5py.File(filepath, "r") as f:
                if "images" not in f:
                    raise ValueError("No images group found in file")
                images = f["images"]
                frame_keys = sorted(k for k in images.keys() if k.startswith("frame_"))
                if end_frame is None:
                    end_frame = len(frame_keys)
                for i in range(start_frame, min(end_frame, len(frame_keys))):
                    k = frame_keys[i]
                    arr = images[k][()]
                    attrs = dict(images[k].attrs)
                    yield i, arr, attrs
        except Exception as e:
            raise RuntimeError(f"Failed to iterate frames: {e}")

    @staticmethod
    def iter_phase_transitions(filepath: str) -> Iterator[dict]:
        try:
            with h5py.File(filepath, "r") as f:
                if "timeseries" not in f:
                    return
                ts = f["timeseries"]
                if "phase_str" not in ts or "frame_index" not in ts:
                    return
                phase_data = ts["phase_str"]
                frame_idx = ts["frame_index"]
                last = None
                for i in range(len(phase_data)):
                    cur = phase_data[i]
                    if isinstance(cur, bytes):
                        cur = cur.decode("utf-8")
                    if last is not None and cur != last:
                        yield {
                            "frame": int(frame_idx[i]),
                            "from_phase": last,
                            "to_phase": cur,
                            "transition_index": i,
                        }
                    last = cur
        except Exception as e:
            raise RuntimeError(f"Failed to iterate phase transitions: {e}")

    @staticmethod
    def get_file_summary(filepath: str) -> dict:
        try:
            with h5py.File(filepath, "r") as f:
                summary = {
                    "filepath": filepath,
                    "created": f.attrs.get("created", 0),
                    "created_human": f.attrs.get("created_human", "Unknown"),
                    "experiment_name": f.attrs.get("experiment_name", "Unknown"),
                    "file_version": f.attrs.get("file_version", "1.0"),
                    "total_frames": f.attrs.get("actual_frames", 0),
                    "duration_minutes": f.attrs.get("duration_minutes", 0),
                    "interval_seconds": f.attrs.get("interval_seconds", 0),
                    "groups": list(f.keys()),
                    "file_size_mb": Path(filepath).stat().st_size / (1024 * 1024),
                    "phase_support": f.attrs.get("phase_support", False),
                    "phase_enabled": f.attrs.get("phase_enabled", False),
                    "memory_optimized": f.attrs.get("memory_optimized", False),
                    "chunked_datasets": f.attrs.get("chunked_datasets", False),
                    "filter_mode": f.attrs.get("filter_mode", "none"),
                    "timeseries_keys_saved": f.attrs.get("timeseries_keys_saved", 0),
                    "timeseries_keys_filtered": f.attrs.get("timeseries_keys_filtered", 0),
                }
                for gname in ["images", "metadata", "timeseries", "phase_analysis"]:
                    if gname in f:
                        summary[f"{gname}_count"] = len(f[gname].keys())
                if "timeseries" in f:
                    ts = f["timeseries"]
                    summary["timeseries_datasets"] = list(ts.keys())
                    if "chunk_size" in ts.attrs:
                        summary["chunk_size"] = ts.attrs["chunk_size"]
                return summary
        except Exception as e:
            raise RuntimeError(f"Failed to get file summary: {e}")

    # ----------------------------
    def force_memory_cleanup(self):
        try:
            import gc

            if self.hdf5_file:
                with self._hdf5_lock:
                    self.hdf5_file.flush()
            collected = gc.collect()
            logger.info(f"Forced memory cleanup: {collected} objects collected")
            return collected > 0
        except Exception as e:
            logger.error(f"Memory cleanup error: {e}")
            return False

    @staticmethod
    def fix_expected_intervals_in_file(filepath: str, expected_interval: float):
        try:
            with h5py.File(filepath, "r+") as f:
                if "timeseries" in f and "expected_intervals" in f["timeseries"]:
                    ds = f["timeseries"]["expected_intervals"]
                    old_vals = ds[:5] if len(ds) > 0 else []
                    logger.info(
                        f"Fixing {len(ds)} expected_intervals: first5={old_vals}, new={expected_interval}"
                    )
                    ds[:] = expected_interval
                    ds.attrs["fixed"] = True
                    ds.attrs["fix_timestamp"] = time.time()
                    ds.attrs["fix_description"] = f"Fixed to constant {expected_interval} seconds"
                    return True
                else:
                    logger.warning("No timeseries/expected_intervals found")
                    return False
        except Exception as e:
            logger.error(f"Error fixing file: {e}")
            return False
