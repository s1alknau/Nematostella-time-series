"""
Data Manager - Zarr-Based Storage

Zarr equivalent of data_manager_hdf5.py.
Produces files readable by napari-hdf5-activity (zarr branch).

Zarr store structure:
    experiment_name_YYYYMMDD_HHMMSS.zarr/
    ├── images/
    │   └── frames        (N, H, W) uint16, chunks=(1, H, W)
    ├── timeseries/
    │   ├── frame_index
    │   ├── recording_elapsed_sec
    │   ├── actual_intervals
    │   ├── temperature_celsius
    │   ├── ...
    └── .zattrs           root attributes (frame_interval, experiment_name, ...)
"""

from __future__ import annotations

import logging
import threading
import time
from enum import IntEnum
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


# ============================================================================
# TELEMETRY MODE (same as HDF5)
# ============================================================================


class TelemetryMode(IntEnum):
    MINIMAL = 1
    STANDARD = 2
    COMPREHENSIVE = 3


# ============================================================================
# ZARR TIMESERIES WRITER
# ============================================================================


class ZarrTimeseriesWriter:
    """Writes per-frame telemetry into a Zarr group as 1-D arrays."""

    LED_TYPE_ENUM = {"ir": 0, "white": 1}
    PHASE_ENUM = {"dark": 0, "light": 1, "continuous": 2}

    def __init__(self, group, chunk_size: int = 512, mode: TelemetryMode = TelemetryMode.STANDARD):
        self.g = group
        self.chunk_size = int(chunk_size)
        self.mode = mode
        self._lock = threading.RLock()
        self.arrays = {}
        self.written_frames = 0

        minimal_fields = {
            "frame_index": np.int64,
            "recording_elapsed_sec": np.float64,
            "actual_intervals": np.float64,
            "expected_intervals": np.float64,
            "temperature_celsius": np.float32,
            "humidity_percent": np.float32,
            "led_type_str": str,
            "led_power": np.int16,
            "ir_led_power": np.int16,
            "white_led_power": np.int16,
            "phase_str": str,
            "cycle_number": np.int32,
            "frame_mean_intensity": np.float32,
            "sync_success": np.int8,
        }
        standard_fields = {
            "phase_transition": np.int8,
            "capture_method": str,
            "cumulative_drift_sec": np.float32,
        }
        comprehensive_fields = {
            "operation_start_absolute": np.float64,
            "operation_end_absolute": np.float64,
            "expected_timestamps": np.float64,
            "capture_timestamps": np.float64,
            "capture_elapsed_sec": np.float64,
            "frame_drift": np.float32,
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
            "sync_quality": str,
        }

        if mode == TelemetryMode.MINIMAL:
            fields = minimal_fields
        elif mode == TelemetryMode.STANDARD:
            fields = {**minimal_fields, **standard_fields}
        else:
            fields = {**minimal_fields, **standard_fields, **comprehensive_fields}

        with self._lock:
            for name, dtype in fields.items():
                if name in self.g:
                    self.arrays[name] = self.g[name]
                else:
                    if dtype is str:
                        self.arrays[name] = self.g.create_dataset(
                            name,
                            shape=(0,),
                            chunks=(self.chunk_size,),
                            dtype="str",
                        )
                    else:
                        self.arrays[name] = self.g.create_dataset(
                            name,
                            shape=(0,),
                            chunks=(self.chunk_size,),
                            dtype=dtype,
                        )

        logger.info(f"Zarr timeseries writer: {len(self.arrays)} arrays, mode={mode.name}")

    def _set(self, name, index, value):
        if name not in self.arrays:
            return
        arr = self.arrays[name]
        if index >= arr.shape[0]:
            arr.resize((index + self.chunk_size,))
        arr[index] = value

    def append(
        self, frame_index: int, frame_metadata: dict, esp32_timing: dict, python_timing: dict
    ):
        with self._lock:
            i = self.written_frames
            # Grow all arrays if needed
            for arr in self.arrays.values():
                if i >= arr.shape[0]:
                    arr.resize((i + self.chunk_size,))

            fm = frame_metadata or {}
            et = esp32_timing or {}
            pt = python_timing or {}

            def s(key, value):
                if key in self.arrays:
                    self.arrays[key][i] = value

            s("frame_index", int(frame_index))

            timestamp_abs = float(
                pt.get("capture_timestamp_absolute") or fm.get("timestamp") or time.time()
            )
            recording_elapsed = float(
                fm.get("recording_elapsed_sec") or pt.get("recording_elapsed_sec") or 0.0
            )
            s("recording_elapsed_sec", recording_elapsed)

            s("actual_intervals", float(pt.get("actual_interval_sec", np.nan)))
            s("expected_intervals", float(pt.get("expected_interval_sec", 5.0)))

            temp = float(et.get("temperature_celsius") or et.get("temperature", np.nan))
            humidity = float(et.get("humidity_percent") or et.get("humidity", np.nan))
            s("temperature_celsius", temp)
            s("humidity_percent", humidity)

            led_power = int(et.get("led_power_actual") or fm.get("led_power", -1))
            led_type_str = str(et.get("led_type_used") or fm.get("led_type", ""))
            ir_led_power = int(fm.get("ir_led_power", -1))
            white_led_power = int(fm.get("white_led_power", -1))
            s("led_power", led_power)
            s("ir_led_power", ir_led_power)
            s("white_led_power", white_led_power)
            s("led_type_str", led_type_str)

            sync_success = bool(et.get("sync_success", True))
            s("sync_success", 1 if sync_success else 0)

            phase_str = str(fm.get("phase") or fm.get("current_phase", "continuous"))
            s("phase_str", phase_str)
            s("cycle_number", int(fm.get("cycle_number", 0)))

            frame_mean = float(fm.get("frame_mean_intensity") or fm.get("frame_mean", 0.0))
            s("frame_mean_intensity", frame_mean)

            if self.mode >= TelemetryMode.STANDARD:
                s("phase_transition", int(fm.get("phase_transition", False)))
                s("capture_method", str(fm.get("capture_method", "unknown")))
                s("cumulative_drift_sec", float(pt.get("cumulative_drift_sec", 0.0)))

            if self.mode == TelemetryMode.COMPREHENSIVE:
                s(
                    "operation_start_absolute",
                    float(pt.get("operation_start_absolute", timestamp_abs)),
                )
                s("operation_end_absolute", float(pt.get("operation_end_absolute", timestamp_abs)))
                s("expected_timestamps", float(pt.get("expected_time", timestamp_abs)))
                s("capture_timestamps", timestamp_abs)
                s("capture_elapsed_sec", float(pt.get("capture_elapsed_sec", recording_elapsed)))
                s("capture_overhead_sec", float(pt.get("capture_overhead_sec", np.nan)))
                s("capture_delay_sec", float(fm.get("capture_delay_sec", np.nan)))
                s("temperature", temp)
                s("humidity", humidity)
                s("led_sync_success", 1 if sync_success else 0)
                s("transition_count", int(fm.get("transition_count", 0)))
                s("frame_mean", frame_mean)
                s("sync_quality", str(fm.get("sync_quality", "excellent")))
                s("stabilization_ms", float(et.get("led_stabilization_ms", -1)))
                s("capture_delay_ms", int(et.get("capture_delay_ms", -1)))
                s("camera_trigger_latency_ms", int(et.get("camera_trigger_latency_ms", -1)))

            self.written_frames += 1

    def trim_to_actual_size(self):
        """Trim all arrays to actually written frames."""
        with self._lock:
            for arr in self.arrays.values():
                if arr.shape[0] > self.written_frames:
                    arr.resize((self.written_frames,))
        logger.info(f"Zarr timeseries trimmed to {self.written_frames} frames")

    def get_stats(self) -> dict:
        return {
            "written_frames": self.written_frames,
            "dataset_count": len(self.arrays),
            "mode": self.mode.name,
        }


# ============================================================================
# MAIN ZARR DATA MANAGER
# ============================================================================


class DataManagerZarr:
    """
    Zarr-based Data Manager — same interface as DataManager (HDF5).

    Store structure:
        experiment.zarr/
        ├── images/frames   (N, H, W) uint16
        ├── timeseries/     1-D telemetry arrays
        └── .zattrs         recording metadata
    """

    def __init__(
        self,
        telemetry_mode: TelemetryMode = TelemetryMode.STANDARD,
        chunk_size: int = 10,
        flush_interval: int = 10,
    ):
        self.telemetry_mode = telemetry_mode
        self.chunk_size = chunk_size
        self.flush_interval = flush_interval

        self._store: Any = None
        self._root: Any = None
        self.current_filepath: Path | None = None
        self._lock = threading.RLock()

        self._ts_writer: ZarrTimeseriesWriter | None = None
        self._frames_array: Any = None
        self._image_shape: tuple[int, int] | None = None
        self._images_max_frames: int = 100_000

        self.frame_count = 0
        self._frames_since_flush = 0
        self._current_phase = None
        self._transition_count = 0

        self.recording_start_time = 0.0
        self.last_frame_time = 0.0
        self.cumulative_drift = 0.0
        self.recording_metadata: dict[str, Any] = {}

        logger.info(f"DataManagerZarr initialized (mode={telemetry_mode.name})")

    def create_recording_file(
        self, output_dir: str, experiment_name: str, timestamped: bool = True
    ) -> str:
        import zarr

        with self._lock:
            if timestamped:
                ts_tag = time.strftime("%Y%m%d_%H%M%S")
                store_name = f"{experiment_name}_{ts_tag}.zarr"
                output_path = Path(output_dir) / ts_tag
            else:
                store_name = f"{experiment_name}.zarr"
                output_path = Path(output_dir)

            output_path.mkdir(parents=True, exist_ok=True)
            self.current_filepath = output_path / store_name

            try:
                # zarr v2: zarr.DirectoryStore / zarr v3: zarr.storage.LocalStore
                _StoreClass = getattr(zarr.storage, "LocalStore", None) or getattr(
                    zarr, "DirectoryStore", None
                )
                assert _StoreClass is not None, "zarr store class not found"
                self._store = _StoreClass(str(self.current_filepath))
                self._root = zarr.open_group(store=self._store, mode="w")

                # Create groups
                self._root.require_group("images")
                self._root.require_group("timeseries")

                # Root attributes
                self._root.attrs["created"] = time.time()
                self._root.attrs["created_human"] = time.strftime("%Y-%m-%d %H:%M:%S")
                self._root.attrs["experiment_name"] = experiment_name
                self._root.attrs["file_version"] = "1.0-zarr"
                self._root.attrs["software"] = "nematostella-timelapse-zarr"
                self._root.attrs["telemetry_mode"] = self.telemetry_mode.name

                self.frame_count = 0
                self.recording_start_time = time.time()
                self.last_frame_time = 0.0
                self.cumulative_drift = 0.0

                self.recording_metadata = {
                    "start_time": self.recording_start_time,
                    "expected_frames": 0,
                    "actual_frames": 0,
                    "duration_minutes": 0,
                    "interval_seconds": 0,
                    "phase_enabled": False,
                    "telemetry_mode": self.telemetry_mode.name,
                }

                logger.info(f"Zarr store created: {self.current_filepath}")
                return str(self.current_filepath)

            except Exception as e:
                logger.error(f"Failed to create Zarr store: {e}")
                raise

    def set_recording_config(self, config: dict):
        self.recording_metadata.update(config)
        # Update frame_interval attribute for analysis plugin compatibility
        interval = config.get("interval_seconds", 5.0)
        if self._root is not None:
            self._root.attrs["frame_interval"] = float(interval)
        logger.debug(f"Zarr recording config updated: {config}")

    def save_frame(self, frame: np.ndarray, frame_number: int, metadata: dict) -> bool:
        if self._root is None:
            logger.error("No Zarr store open")
            return False

        frame_index = frame_number - 1
        current_time = time.time()

        with self._lock:
            try:
                timing_metrics = self._calculate_timing_metrics(
                    frame_number, current_time, metadata
                )
                frame_stats = self._calculate_frame_statistics(frame)
                phase_metadata = self._process_phase_info(frame_number, metadata)

                # ---- Images ----
                if self._frames_array is None:
                    if "frames" in self._root["images"]:
                        self._frames_array = self._root["images"]["frames"]
                        self._image_shape = self._frames_array.shape[1:]
                    else:
                        self._initialize_images_array(frame)

                # Grow if needed
                assert self._image_shape is not None
                if frame_index >= self._frames_array.shape[0]:
                    new_size = frame_index + self._images_max_frames
                    self._frames_array.resize((new_size,) + self._image_shape)
                    logger.warning(f"Zarr frames array extended to {new_size}")

                self._frames_array[frame_index] = frame

                # ---- Timeseries ----
                if self._ts_writer is None:
                    self._create_timeseries_writer()
                assert self._ts_writer is not None

                frame_metadata = {
                    **metadata,
                    **frame_stats,
                    **phase_metadata,
                    "frame_number": frame_number,
                    "frame_index": frame_index,
                    "timestamp": current_time,
                }

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

                self._ts_writer.append(
                    frame_index=frame_index,
                    frame_metadata=frame_metadata,
                    esp32_timing=esp32_timing,
                    python_timing=timing_metrics,
                )

                # Also write absolute timestamp for analysis plugin
                ts_group = self._root["timeseries"]
                if "timestamps" not in ts_group:
                    ts_arr = ts_group.create_dataset(
                        "timestamps",
                        shape=(self._images_max_frames,),
                        chunks=(512,),
                        dtype=np.float64,
                    )
                else:
                    ts_arr = ts_group["timestamps"]
                if frame_index >= ts_arr.shape[0]:
                    ts_arr.resize((frame_index + self.chunk_size,))
                ts_arr[frame_index] = current_time

                self.frame_count += 1
                self.last_frame_time = current_time
                self._frames_since_flush += 1

                logger.debug(f"Zarr frame {frame_number} saved (index={frame_index})")
                return True

            except Exception as e:
                logger.error(f"Failed to save Zarr frame {frame_number}: {e}")
                return False

    def _initialize_images_array(self, frame: np.ndarray) -> None:
        h, w = frame.shape[0], frame.shape[1]
        self._image_shape = (h, w)
        dtype = frame.dtype

        self._frames_array = self._root["images"].create_dataset(
            "frames",
            shape=(self._images_max_frames, h, w),
            chunks=(1, h, w),
            dtype=dtype,
        )
        self._frames_array.attrs["frame_height"] = h
        self._frames_array.attrs["frame_width"] = w
        self._frames_array.attrs["frame_dtype"] = str(dtype)

        self._root["images"].attrs["frame_shape"] = [h, w]
        self._root["images"].attrs["frame_dtype"] = str(dtype)

        # Also set root-level frame_shape for analysis plugin
        self._root.attrs["frame_height"] = h
        self._root.attrs["frame_width"] = w

        logger.info(
            f"Zarr images array pre-allocated: ({self._images_max_frames}, {h}, {w}) dtype={dtype}"
        )

    def _create_timeseries_writer(self):
        ts_group = self._root["timeseries"]
        self._ts_writer = ZarrTimeseriesWriter(
            ts_group, chunk_size=self.chunk_size, mode=self.telemetry_mode
        )
        ts_group.attrs["description"] = "Zarr timeseries telemetry"
        ts_group.attrs["telemetry_mode"] = self.telemetry_mode.name
        logger.info("Zarr timeseries writer created")

    def _calculate_timing_metrics(
        self, frame_number: int, current_time: float, metadata: dict
    ) -> dict:
        expected_interval = self.recording_metadata.get("interval_seconds", 5.0)
        recording_elapsed = current_time - self.recording_start_time
        expected_elapsed = (frame_number - 1) * expected_interval

        if frame_number == 1 or self.last_frame_time == 0:
            actual_interval = 0.0
            interval_error = 0.0
        else:
            actual_interval = current_time - self.last_frame_time
            interval_error = actual_interval - expected_interval

        timing_error = recording_elapsed - expected_elapsed

        if frame_number > 1:
            self.cumulative_drift += interval_error

        operation_start = metadata.get("capture_start", current_time)

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
            "operation_duration_sec": current_time - operation_start,
            "capture_overhead_sec": metadata.get("capture_duration", 0.0),
        }

    def _calculate_frame_statistics(self, frame: np.ndarray) -> dict:
        try:
            frame_mean = float(np.mean(frame))
            if self.telemetry_mode == TelemetryMode.COMPREHENSIVE:
                return {
                    "frame_mean": frame_mean,
                    "frame_mean_intensity": frame_mean,
                    "frame_std": float(np.std(frame)),
                    "frame_min": float(np.min(frame)),
                    "frame_max": float(np.max(frame)),
                }
            return {
                "frame_mean": frame_mean,
                "frame_mean_intensity": frame_mean,
                "frame_std": 0.0,
                "frame_min": 0.0,
                "frame_max": 0.0,
            }
        except Exception:
            return {
                "frame_mean": 0.0,
                "frame_mean_intensity": 0.0,
                "frame_std": 0.0,
                "frame_min": 0.0,
                "frame_max": 0.0,
            }

    def _process_phase_info(self, frame_number: int, metadata: dict) -> dict:
        phase_enabled = metadata.get("phase_enabled", False)
        phase = metadata.get("phase", "continuous")
        cycle_number = metadata.get("cycle_number", 0)

        is_transition = False
        if phase_enabled:
            if self._current_phase is None:
                self._current_phase = phase
            elif phase != self._current_phase:
                self._current_phase = phase
                self._transition_count += 1
                is_transition = True

        return {"phase": phase, "cycle_number": cycle_number, "phase_transition": is_transition}

    def flush_file(self):
        """Zarr stores sync automatically; this is a no-op kept for interface compatibility."""
        pass

    def finalize_recording(self, final_info: dict) -> bool:
        logger.info("Finalizing Zarr recording...")
        try:
            with self._lock:
                if self._root is None:
                    return False

                self._root.attrs["actual_frames"] = self.frame_count
                self._root.attrs["finalized"] = True
                self._root.attrs["finalized_time"] = time.time()
                self._root.attrs["total_phase_transitions"] = self._transition_count

                self.recording_metadata.update(final_info)
                self.recording_metadata["actual_frames"] = self.frame_count

                for k, v in self.recording_metadata.items():
                    try:
                        if isinstance(v, (str, int, float, bool)):
                            self._root.attrs[k] = v
                    except Exception:
                        pass

                # Trim images array
                if (
                    self._frames_array is not None
                    and self._image_shape is not None
                    and self.frame_count > 0
                ):
                    self._frames_array.resize((self.frame_count,) + self._image_shape)
                    logger.info(f"Zarr images array trimmed to {self.frame_count} frames")

                # Trim timeseries
                if self._ts_writer:
                    self._ts_writer.trim_to_actual_size()

                # Trim timestamps
                if "timestamps" in self._root["timeseries"]:
                    self._root["timeseries"]["timestamps"].resize((self.frame_count,))

                logger.info(f"Zarr recording finalized: {self.frame_count} frames")
                return True

        except Exception as e:
            logger.error(f"Zarr finalize error: {e}")
            return False

    def close_file(self):
        """Close/sync the Zarr store."""
        try:
            if self._store is not None:
                if hasattr(self._store, "close"):
                    self._store.close()
                self._store = None
                self._root = None
                self._frames_array = None
                self._ts_writer = None
            logger.info("Zarr store closed")
        except Exception as e:
            logger.error(f"Zarr close error: {e}")

    def cleanup(self):
        self.close_file()

    def get_stats(self) -> dict:
        stats = {
            "format": "zarr",
            "frame_count": self.frame_count,
            "filepath": str(self.current_filepath) if self.current_filepath else None,
        }
        if self._ts_writer:
            stats["timeseries"] = self._ts_writer.get_stats()
        return stats

    def get_recording_directory(self) -> str | None:
        if self.current_filepath:
            return str(self.current_filepath.parent)
        return None

    def save_roi_masks(self, masks: list[np.ndarray]) -> bool:
        """
        Save ROI masks to the Zarr store under rois/masks (N, H, W) uint8.

        Called once after ROI detection, before or during recording.
        Compatible with napari-hdf5-activity: masks are binary (0/255) uint8 arrays.

        Args:
            masks: List of binary uint8 masks, each shape (H, W)

        Returns:
            True on success
        """
        if self._root is None:
            logger.error("save_roi_masks: no Zarr store open")
            return False
        if not masks:
            logger.warning("save_roi_masks: empty masks list, skipping")
            return True
        try:
            mask_array = np.stack(masks, axis=0)  # (N, H, W) uint8
            rois_group = self._root.require_group("rois")
            if "masks" in rois_group:
                del rois_group["masks"]
            rois_group.create_array(
                "masks",
                data=mask_array,
                dtype=np.uint8,
                chunks=(1, mask_array.shape[1], mask_array.shape[2]),
            )
            rois_group.attrs["n_rois"] = len(masks)
            rois_group.attrs["mask_shape"] = list(mask_array.shape[1:])
            logger.info(f"Saved {len(masks)} ROI masks to Zarr store")
            return True
        except Exception as exc:
            logger.error(f"save_roi_masks failed: {exc}")
            return False

    def get_zarr_path(self) -> str | None:
        """Return the path to the current Zarr store, or None if not open."""
        if self.current_filepath:
            return str(self.current_filepath)
        return None
