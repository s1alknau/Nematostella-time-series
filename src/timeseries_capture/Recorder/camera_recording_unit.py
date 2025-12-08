"""
Camera Recording Unit

Encapsulates a single camera-ESP32 recording system.
Each unit operates independently and can be controlled individually.
"""

import logging
import threading
from typing import Optional

from ..Config.camera_system_config import CameraConfig
from .frame_capture import FrameCaptureService
from .recording_manager import RecordingManager
from .recording_state import RecordingConfig, RecordingState, RecordingStatus

logger = logging.getLogger(__name__)


class CameraRecordingUnit:
    """
    Single Camera-ESP32 Recording Unit

    Manages one complete recording system:
    - 1 Camera
    - 1 ESP32 Controller
    - 1 Recording Manager
    - 1 HDF5 Data Manager

    Each unit operates independently in its own thread.
    """

    def __init__(
        self,
        camera_config: CameraConfig,
        camera_adapter,
        esp32_controller,
        output_prefix: str = "",
    ):
        """
        Args:
            camera_config: Configuration for this camera
            camera_adapter: Camera adapter instance
            esp32_controller: ESP32 controller instance
            output_prefix: Prefix for output filenames (e.g., "camera1_")
        """
        self.camera_config = camera_config
        self.camera_adapter = camera_adapter
        self.esp32_controller = esp32_controller
        self.output_prefix = output_prefix

        # Create frame capture service
        self.frame_capture = FrameCaptureService(
            esp32_adapter=esp32_controller,
            camera_adapter=camera_adapter,
            stabilization_ms=1000,
            exposure_ms=10,
        )

        # Create recording manager
        self.recording_manager = RecordingManager(self.frame_capture)

        # Recording thread
        self.recording_thread: Optional[threading.Thread] = None

        logger.info(
            f"CameraRecordingUnit initialized: {camera_config.name} (ID: {camera_config.id})"
        )

    @property
    def camera_id(self) -> str:
        """Get camera ID"""
        return self.camera_config.id

    @property
    def camera_name(self) -> str:
        """Get camera name"""
        return self.camera_config.name

    @property
    def is_connected(self) -> bool:
        """Check if camera and ESP32 are connected"""
        return self.camera_adapter.is_available() and self.esp32_controller.is_connected

    @property
    def is_recording(self) -> bool:
        """Check if currently recording"""
        return self.recording_manager.state.status == RecordingStatus.RECORDING

    @property
    def status(self) -> RecordingStatus:
        """Get current recording status"""
        return self.recording_manager.state.status

    @property
    def state(self) -> RecordingState:
        """Get recording state"""
        return self.recording_manager.state

    def connect(self) -> bool:
        """
        Connect camera and ESP32

        Returns:
            True if successful
        """
        try:
            # Check camera
            if not self.camera_adapter.is_available():
                logger.error(f"[{self.camera_id}] Camera not available")
                return False

            # Check ESP32
            if not self.esp32_controller.is_connected:
                logger.error(f"[{self.camera_id}] ESP32 not connected")
                return False

            logger.info(f"[{self.camera_id}] Successfully connected")
            return True

        except Exception as e:
            logger.error(f"[{self.camera_id}] Connection failed: {e}", exc_info=True)
            return False

    def start_recording(self, config: RecordingConfig) -> bool:
        """
        Start recording

        Args:
            config: Recording configuration

        Returns:
            True if started successfully
        """
        if self.is_recording:
            logger.warning(f"[{self.camera_id}] Already recording")
            return False

        # Modify config to add camera-specific prefix
        modified_config = self._add_camera_prefix_to_config(config)

        try:
            # Start recording in separate thread
            self.recording_thread = threading.Thread(
                target=self._recording_worker,
                args=(modified_config,),
                name=f"Recording-{self.camera_id}",
                daemon=True,
            )
            self.recording_thread.start()

            logger.info(f"[{self.camera_id}] Recording started")
            return True

        except Exception as e:
            logger.error(f"[{self.camera_id}] Failed to start recording: {e}", exc_info=True)
            return False

    def _recording_worker(self, config: RecordingConfig):
        """
        Recording worker thread

        Args:
            config: Recording configuration
        """
        try:
            self.recording_manager.start_recording(config)
        except Exception as e:
            logger.error(f"[{self.camera_id}] Recording error: {e}", exc_info=True)

    def stop_recording(self) -> bool:
        """
        Stop recording

        Returns:
            True if stopped successfully
        """
        if not self.is_recording:
            logger.warning(f"[{self.camera_id}] Not recording")
            return False

        try:
            self.recording_manager.stop_recording()

            # Wait for thread to finish (with timeout)
            if self.recording_thread and self.recording_thread.is_alive():
                self.recording_thread.join(timeout=5.0)

                if self.recording_thread.is_alive():
                    logger.warning(f"[{self.camera_id}] Recording thread did not stop cleanly")

            logger.info(f"[{self.camera_id}] Recording stopped")
            return True

        except Exception as e:
            logger.error(f"[{self.camera_id}] Failed to stop recording: {e}", exc_info=True)
            return False

    def _add_camera_prefix_to_config(self, config: RecordingConfig) -> RecordingConfig:
        """
        Add camera-specific prefix to experiment name

        Args:
            config: Original config

        Returns:
            Modified config with camera prefix
        """
        # Create new config with modified experiment name
        prefixed_name = f"{self.output_prefix}{config.experiment_name}"

        # Create modified config (dataclass replace)
        from dataclasses import replace

        return replace(config, experiment_name=prefixed_name)

    def get_statistics(self) -> dict:
        """
        Get recording statistics

        Returns:
            Dict with statistics
        """
        state = self.recording_manager.state

        return {
            "camera_id": self.camera_id,
            "camera_name": self.camera_name,
            "status": state.status.value,
            "total_frames": state.total_frames,
            "captured_frames": state.captured_frames,
            "progress_percent": state.progress_percent,
            "elapsed_time": state.elapsed_time,
            "remaining_time": state.remaining_time,
        }

    def disconnect(self):
        """Disconnect camera and ESP32"""
        try:
            if self.is_recording:
                self.stop_recording()

            # Note: Actual disconnect handled by adapters themselves
            logger.info(f"[{self.camera_id}] Disconnected")

        except Exception as e:
            logger.error(f"[{self.camera_id}] Error during disconnect: {e}", exc_info=True)


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    print("CameraRecordingUnit test")
    print("This module requires camera and ESP32 adapters to test")
    print("See multi_camera_controller.py for integration testing")
