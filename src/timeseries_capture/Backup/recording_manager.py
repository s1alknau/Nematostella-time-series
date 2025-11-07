import time
from datetime import datetime
from typing import Any, Dict, Optional

import h5py
import numpy as np


class RecordingManager:
    """Optimized HDF5 recording manager with minimal overhead"""

    def __init__(self, napari_viewer=None):
        self.viewer = napari_viewer
        self.hdf5_file: Optional[h5py.File] = None
        self.dataset = None
        self.recording = False
        self.current_frame = 0
        self.total_frames = 0
        self.start_time = 0
        self.frame_buffer_size = 10  # Buffer frames before flushing

    def setup_recording(
        self,
        save_path: str,
        frame_shape: tuple,
        total_frames: int,
        metadata: Dict[str, Any],
    ) -> bool:
        """Setup HDF5 file with optimized structure"""
        try:
            # Create HDF5 file with compression
            self.hdf5_file = h5py.File(save_path, "w")

            # Create main dataset with chunking for efficient I/O
            dataset_shape = (total_frames,) + frame_shape
            chunk_shape = (1,) + frame_shape

            self.dataset = self.hdf5_file.create_dataset(
                "frames",
                shape=dataset_shape,
                dtype=np.uint8,
                chunks=chunk_shape,
                compression="gzip",
                compression_opts=4,
                shuffle=True,
            )

            # Create timing datasets
            timing_group = self.hdf5_file.create_group("timing")
            timing_group.create_dataset("capture_timestamps", (total_frames,), dtype="f8")
            timing_group.create_dataset("frame_numbers", (total_frames,), dtype="i4")
            timing_group.create_dataset("target_timestamps", (total_frames,), dtype="f8")
            timing_group.create_dataset("drift_ms", (total_frames,), dtype="f4")

            # Create environmental datasets
            env_group = self.hdf5_file.create_group("environmental")
            env_group.create_dataset("temperature", (total_frames,), dtype="f4")
            env_group.create_dataset("humidity", (total_frames,), dtype="f4")

            # Create LED datasets
            led_group = self.hdf5_file.create_group("led")
            led_group.create_dataset("power_percent", (total_frames,), dtype="u1")
            led_group.create_dataset("duration_ms", (total_frames,), dtype="u2")
            led_group.create_dataset("illuminated", (total_frames,), dtype="bool")

            # Store metadata
            for key, value in metadata.items():
                if isinstance(value, str) or isinstance(value, (int, float, bool)):
                    self.hdf5_file.attrs[key] = value
                elif isinstance(value, (list, tuple)):
                    self.hdf5_file.attrs[key] = np.array(value)

            # Additional attributes
            self.hdf5_file.attrs["created"] = datetime.now().isoformat()
            self.hdf5_file.attrs["hdf5_version"] = h5py.version.hdf5_version
            self.hdf5_file.attrs["plugin_version"] = "4.0"

            self.total_frames = total_frames
            self.current_frame = 0
            self.recording = True
            self.start_time = time.time()

            return True

        except Exception as e:
            print(f"HDF5 setup error: {e}")
            if self.hdf5_file:
                self.hdf5_file.close()
                self.hdf5_file = None
            return False

    def save_frame(self, frame_data: Dict[str, Any]) -> bool:
        """Save frame with all associated data"""
        if not self.recording or not self.hdf5_file or self.current_frame >= self.total_frames:
            return False

        try:
            idx = self.current_frame

            # Save frame
            self.dataset[idx] = frame_data["frame"]

            # Save timing data
            self.hdf5_file["timing/capture_timestamps"][idx] = frame_data["capture_timestamp"]
            self.hdf5_file["timing/frame_numbers"][idx] = idx
            self.hdf5_file["timing/target_timestamps"][idx] = frame_data["target_timestamp"]
            self.hdf5_file["timing/drift_ms"][idx] = frame_data["drift_ms"]

            # Save environmental data
            self.hdf5_file["environmental/temperature"][idx] = frame_data.get("temperature", 0.0)
            self.hdf5_file["environmental/humidity"][idx] = frame_data.get("humidity", 0.0)

            # Save LED data
            self.hdf5_file["led/power_percent"][idx] = frame_data.get("led_power", 0)
            self.hdf5_file["led/duration_ms"][idx] = frame_data.get("led_duration_ms", 0)
            self.hdf5_file["led/illuminated"][idx] = frame_data.get("led_used", False)

            self.current_frame += 1

            # Flush periodically for data safety
            if self.current_frame % self.frame_buffer_size == 0:
                self.hdf5_file.flush()

            return True

        except Exception as e:
            print(f"Frame save error: {e}")
            return False

    def save_frame_metadata(self, frame_index: int, metadata: Dict[str, Any]):
        """Save additional frame-specific metadata"""
        if not self.hdf5_file or frame_index >= self.total_frames:
            return

        try:
            # Create frame metadata group if needed
            if "frame_metadata" not in self.hdf5_file:
                self.hdf5_file.create_group("frame_metadata")

            frame_group = self.hdf5_file["frame_metadata"].create_group(f"frame_{frame_index:06d}")

            for key, value in metadata.items():
                if isinstance(value, (str, int, float, bool)):
                    frame_group.attrs[key] = value
                elif isinstance(value, np.ndarray):
                    frame_group.create_dataset(key, data=value, compression="gzip")

        except Exception as e:
            print(f"Metadata save error: {e}")

    def finalize_recording(self) -> Dict[str, Any]:
        """Finalize recording and return summary statistics"""
        summary = {
            "frames_saved": self.current_frame,
            "frames_expected": self.total_frames,
            "duration_seconds": time.time() - self.start_time if self.start_time else 0,
            "success": False,
        }

        if self.hdf5_file:
            try:
                # Calculate statistics
                actual_frames = self.current_frame

                if actual_frames > 0:
                    # Get timing statistics
                    drifts = self.hdf5_file["timing/drift_ms"][:actual_frames]
                    summary["max_drift_ms"] = float(np.max(np.abs(drifts)))
                    summary["mean_drift_ms"] = float(np.mean(drifts))
                    summary["std_drift_ms"] = float(np.std(drifts))

                    # Get environmental statistics
                    temps = self.hdf5_file["environmental/temperature"][:actual_frames]
                    summary["mean_temperature"] = float(np.mean(temps))
                    summary["temperature_range"] = (
                        float(np.min(temps)),
                        float(np.max(temps)),
                    )

                # Update file attributes
                self.hdf5_file.attrs["frames_captured"] = actual_frames
                self.hdf5_file.attrs["recording_duration"] = summary["duration_seconds"]
                self.hdf5_file.attrs["completed"] = datetime.now().isoformat()
                self.hdf5_file.attrs["completion_percentage"] = (
                    (actual_frames / self.total_frames * 100) if self.total_frames > 0 else 0
                )

                # Final flush and close
                self.hdf5_file.flush()
                self.hdf5_file.close()

                summary["success"] = True

            except Exception as e:
                print(f"Finalization error: {e}")
                try:
                    self.hdf5_file.close()
                except:
                    pass

        # Reset state
        self.hdf5_file = None
        self.dataset = None
        self.recording = False
        self.current_frame = 0
        self.total_frames = 0

        return summary

    def get_recording_status(self) -> Dict[str, Any]:
        """Get current recording status"""
        if not self.recording:
            return {"recording": False}

        elapsed = time.time() - self.start_time
        fps = self.current_frame / elapsed if elapsed > 0 else 0

        return {
            "recording": True,
            "current_frame": self.current_frame,
            "total_frames": self.total_frames,
            "elapsed_seconds": elapsed,
            "fps": fps,
            "completion_percentage": (
                (self.current_frame / self.total_frames * 100) if self.total_frames > 0 else 0
            ),
        }
