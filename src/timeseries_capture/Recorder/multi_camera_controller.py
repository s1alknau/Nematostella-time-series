"""
Multi-Camera Controller

Manages multiple camera-ESP32 recording units for parallel operation.
Provides coordinated control and status monitoring across all cameras.
"""

import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

from ..Config.camera_system_config import CameraConfig, CameraSystemConfig
from .camera_recording_unit import CameraRecordingUnit
from .recording_state import RecordingConfig, RecordingStatus

logger = logging.getLogger(__name__)


class MultiCameraController:
    """
    Multi-Camera Recording Controller

    Manages N camera-ESP32 recording units for parallel operation.
    Each unit records independently to its own HDF5 file.

    Features:
    - Start/stop all recordings simultaneously
    - Monitor status of all units
    - Individual unit access for per-camera control
    - Aggregated statistics across all cameras
    """

    def __init__(
        self,
        system_config: CameraSystemConfig,
        camera_factory,
        esp32_factory,
    ):
        """
        Args:
            system_config: Camera system configuration
            camera_factory: Factory function to create camera adapters
                           Signature: camera_factory(camera_config) -> camera_adapter
            esp32_factory: Factory function to create ESP32 controllers
                          Signature: esp32_factory(port) -> esp32_controller
        """
        self.system_config = system_config
        self.camera_factory = camera_factory
        self.esp32_factory = esp32_factory

        # Recording units (camera_id -> CameraRecordingUnit)
        self.units: Dict[str, CameraRecordingUnit] = {}

        # Connection status
        self._connected = False

        logger.info(
            f"MultiCameraController initialized: {system_config.num_enabled_cameras} cameras"
        )

    @property
    def num_cameras(self) -> int:
        """Total number of camera units"""
        return len(self.units)

    @property
    def camera_ids(self) -> List[str]:
        """List of all camera IDs"""
        return list(self.units.keys())

    @property
    def is_connected(self) -> bool:
        """Check if all units are connected"""
        return self._connected

    @property
    def is_any_recording(self) -> bool:
        """Check if any unit is currently recording"""
        return any(unit.is_recording for unit in self.units.values())

    @property
    def num_recording(self) -> int:
        """Number of units currently recording"""
        return sum(1 for unit in self.units.values() if unit.is_recording)

    def connect_all(self) -> Dict[str, bool]:
        """
        Connect all enabled cameras and ESP32s

        Returns:
            Dict mapping camera_id to connection success status
        """
        results = {}

        logger.info("Connecting all camera units...")

        for camera_config in self.system_config.enabled_cameras:
            try:
                # Create camera adapter
                camera_adapter = self.camera_factory(camera_config)

                # Create ESP32 controller
                esp32_controller = self.esp32_factory(camera_config.esp32_port)

                # Create recording unit
                unit = CameraRecordingUnit(
                    camera_config=camera_config,
                    camera_adapter=camera_adapter,
                    esp32_controller=esp32_controller,
                    output_prefix=f"{camera_config.id}_",
                )

                # Try to connect
                success = unit.connect()
                results[camera_config.id] = success

                if success:
                    self.units[camera_config.id] = unit
                    logger.info(f"[{camera_config.id}] Connected successfully")
                else:
                    logger.error(f"[{camera_config.id}] Connection failed")

            except Exception as e:
                logger.error(
                    f"[{camera_config.id}] Error during connection: {e}",
                    exc_info=True,
                )
                results[camera_config.id] = False

        # Update connected status
        self._connected = all(results.values())

        success_count = sum(1 for success in results.values() if success)
        logger.info(
            f"Connected {success_count}/{len(results)} camera units"
        )

        return results

    def start_all_recordings(self, config: RecordingConfig) -> Dict[str, bool]:
        """
        Start recording on all connected units

        Args:
            config: Recording configuration (applied to all cameras)

        Returns:
            Dict mapping camera_id to start success status
        """
        if not self._connected:
            logger.error("Cannot start recordings: Not all units connected")
            return {cam_id: False for cam_id in self.units.keys()}

        results = {}

        logger.info(f"Starting recordings on {len(self.units)} cameras...")

        for cam_id, unit in self.units.items():
            try:
                success = unit.start_recording(config)
                results[cam_id] = success

                if success:
                    logger.info(f"[{cam_id}] Recording started")
                else:
                    logger.error(f"[{cam_id}] Failed to start recording")

            except Exception as e:
                logger.error(
                    f"[{cam_id}] Error starting recording: {e}",
                    exc_info=True,
                )
                results[cam_id] = False

        success_count = sum(1 for success in results.values() if success)
        logger.info(
            f"Started recordings on {success_count}/{len(results)} cameras"
        )

        return results

    def stop_all_recordings(self) -> Dict[str, bool]:
        """
        Stop recording on all units

        Returns:
            Dict mapping camera_id to stop success status
        """
        results = {}

        logger.info(f"Stopping recordings on {len(self.units)} cameras...")

        for cam_id, unit in self.units.items():
            try:
                success = unit.stop_recording()
                results[cam_id] = success

                if success:
                    logger.info(f"[{cam_id}] Recording stopped")
                else:
                    logger.warning(f"[{cam_id}] Stop recording returned False")

            except Exception as e:
                logger.error(
                    f"[{cam_id}] Error stopping recording: {e}",
                    exc_info=True,
                )
                results[cam_id] = False

        success_count = sum(1 for success in results.values() if success)
        logger.info(
            f"Stopped recordings on {success_count}/{len(results)} cameras"
        )

        return results

    def get_unit(self, camera_id: str) -> Optional[CameraRecordingUnit]:
        """
        Get specific camera recording unit

        Args:
            camera_id: Camera ID

        Returns:
            CameraRecordingUnit or None if not found
        """
        return self.units.get(camera_id)

    def get_all_status(self) -> Dict[str, dict]:
        """
        Get status of all recording units

        Returns:
            Dict mapping camera_id to status dict
        """
        status = {}

        for cam_id, unit in self.units.items():
            try:
                status[cam_id] = {
                    "camera_name": unit.camera_name,
                    "connected": unit.is_connected,
                    "recording": unit.is_recording,
                    "status": unit.status.value,
                    "statistics": unit.get_statistics() if unit.is_recording else None,
                }
            except Exception as e:
                logger.error(
                    f"[{cam_id}] Error getting status: {e}",
                    exc_info=True,
                )
                status[cam_id] = {
                    "camera_name": unit.camera_name,
                    "connected": False,
                    "recording": False,
                    "status": "error",
                    "error": str(e),
                }

        return status

    def get_summary_statistics(self) -> dict:
        """
        Get aggregated statistics across all cameras

        Returns:
            Dict with summary statistics
        """
        all_stats = self.get_all_status()

        recording_units = [
            stats for stats in all_stats.values() if stats.get("recording", False)
        ]

        if not recording_units:
            return {
                "num_cameras": len(self.units),
                "num_recording": 0,
                "num_connected": sum(
                    1 for stats in all_stats.values() if stats.get("connected", False)
                ),
            }

        # Aggregate statistics from recording units
        total_frames = sum(
            stats.get("statistics", {}).get("captured_frames", 0)
            for stats in recording_units
        )

        avg_progress = sum(
            stats.get("statistics", {}).get("progress_percent", 0)
            for stats in recording_units
        ) / len(recording_units)

        return {
            "num_cameras": len(self.units),
            "num_recording": len(recording_units),
            "num_connected": sum(
                1 for stats in all_stats.values() if stats.get("connected", False)
            ),
            "total_frames_captured": total_frames,
            "average_progress_percent": avg_progress,
        }

    def disconnect_all(self):
        """Disconnect all camera units"""
        logger.info("Disconnecting all camera units...")

        for cam_id, unit in self.units.items():
            try:
                unit.disconnect()
                logger.info(f"[{cam_id}] Disconnected")
            except Exception as e:
                logger.error(
                    f"[{cam_id}] Error during disconnect: {e}",
                    exc_info=True,
                )

        self.units.clear()
        self._connected = False

        logger.info("All camera units disconnected")

    def wait_for_completion(self, check_interval: float = 1.0):
        """
        Wait for all recordings to complete

        Args:
            check_interval: How often to check status (seconds)
        """
        logger.info("Waiting for all recordings to complete...")

        while self.is_any_recording:
            time.sleep(check_interval)

            # Log progress
            summary = self.get_summary_statistics()
            logger.info(
                f"Recording progress: {summary['num_recording']}/{summary['num_cameras']} cameras, "
                f"{summary['average_progress_percent']:.1f}% average progress"
            )

        logger.info("All recordings completed")


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    print("MultiCameraController test")
    print("")
    print("This requires:")
    print("  1. Valid camera_system.json configuration")
    print("  2. Connected cameras and ESP32s")
    print("  3. Camera and ESP32 factory functions")
    print("")
    print("See main_widget.py for integration example")
