"""
Recording Controller - GUI Controller für Recording

Verantwortlich für:
- GUI ↔ RecordingManager Kommunikation
- Signal-Konvertierung (GUI Signals → Manager Calls)
- Status-Updates zurück an GUI
- Error-Handling zwischen Layers
"""

import logging
from typing import Optional

from qtpy.QtCore import QObject
from qtpy.QtCore import Signal as pyqtSignal

from .camera_adapters import CameraAdapter
from .Recorder import FrameCaptureService, RecordingConfig, RecordingManager

logger = logging.getLogger(__name__)


class RecordingController(QObject):
    """
    Controller zwischen GUI und RecordingManager.

    Architecture:
    - Empfängt Signals von GUI Panels
    - Konvertiert zu RecordingManager Calls
    - Sendet Status-Updates zurück an GUI
    """

    # Signals für GUI Updates
    status_updated = pyqtSignal(dict)  # Recording status
    error_occurred = pyqtSignal(str)  # Error message

    def __init__(
        self,
        esp32_gui_controller,  # ESP32GUIController instance
        camera_adapter: CameraAdapter,
    ):
        """
        Args:
            esp32_gui_controller: ESP32GUIController instance
            camera_adapter: Camera adapter instance
        """
        super().__init__()

        self.esp32_gui = esp32_gui_controller
        self.camera_adapter = camera_adapter

        # Recording components (initialized when needed)
        self.frame_capture_service: Optional[FrameCaptureService] = None
        self.recording_manager: Optional[RecordingManager] = None

        logger.info("RecordingController initialized")

    # ========================================================================
    # INITIALIZATION
    # ========================================================================

    def initialize_recording_system(self) -> bool:
        """
        Initialisiert Recording-System.
        Erstellt FrameCaptureService und RecordingManager.

        Returns:
            True wenn erfolgreich
        """
        try:
            logger.info("Initializing recording system...")

            # Check hardware availability
            if not self.esp32_gui.is_connected():
                logger.error("ESP32 not connected")
                self.error_occurred.emit("ESP32 not connected! Connect first.")
                return False

            if not self.camera_adapter.is_available():
                logger.error("Camera not available")
                self.error_occurred.emit("Camera not available!")
                return False

            # Get ESP32 controller (adapter)
            esp32_controller = self.esp32_gui.get_esp32_controller()

            # Create FrameCaptureService
            self.frame_capture_service = FrameCaptureService(
                esp32_adapter=esp32_controller,
                camera_adapter=self.camera_adapter,
                stabilization_ms=1000,
                exposure_ms=10,
            )

            # Create RecordingManager
            self.recording_manager = RecordingManager(
                frame_capture_service=self.frame_capture_service
            )

            # Connect RecordingManager signals
            self._connect_manager_signals()

            logger.info("Recording system initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize recording system: {e}")
            self.error_occurred.emit(f"Initialization failed: {e}")
            return False

    def _connect_manager_signals(self):
        """Verbindet RecordingManager Signals mit GUI Updates"""
        if not self.recording_manager:
            return

        # Connect manager signals to GUI updates
        self.recording_manager.recording_started.connect(self._on_recording_started)
        self.recording_manager.recording_stopped.connect(self._on_recording_stopped)
        self.recording_manager.recording_paused.connect(self._on_recording_paused)
        self.recording_manager.recording_resumed.connect(self._on_recording_resumed)
        self.recording_manager.frame_captured.connect(self._on_frame_captured)
        self.recording_manager.progress_updated.connect(self._on_progress_updated)
        self.recording_manager.phase_changed.connect(self._on_phase_changed)
        self.recording_manager.error_occurred.connect(self._on_manager_error)

    # ========================================================================
    # RECORDING CONTROL (Called by GUI)
    # ========================================================================

    def start_recording(self, config_dict: dict) -> bool:
        """
        Startet Recording mit gegebener Konfiguration.

        Args:
            config_dict: Configuration dictionary from GUI

        Returns:
            True wenn erfolgreich gestartet
        """
        try:
            logger.info(f"Starting recording: {config_dict}")

            # Initialize if not done yet
            if not self.recording_manager:
                if not self.initialize_recording_system():
                    return False

            # Create RecordingConfig from dict
            # Fix: Phase panel returns 'enabled', but we need 'phase_enabled'
            phase_enabled = config_dict.get("phase_enabled", config_dict.get("enabled", False))

            config = RecordingConfig(
                duration_min=config_dict["duration_min"],
                interval_sec=config_dict["interval_sec"],
                experiment_name=config_dict["experiment_name"],
                output_dir=config_dict["output_dir"],
                phase_enabled=phase_enabled,
                light_duration_min=config_dict.get("light_duration_min", 30),
                dark_duration_min=config_dict.get("dark_duration_min", 30),
                start_with_light=config_dict.get("start_with_light", True),
                dual_light_phase=config_dict.get("dual_light_phase", False),
                camera_trigger_latency_ms=config_dict.get("camera_trigger_latency_ms", 20),
                ir_led_power=config_dict.get("ir_led_power", 100),
                white_led_power=config_dict.get("white_led_power", 50),
                # Per-phase LED powers (from calibration)
                dark_phase_ir_power=config_dict.get("dark_phase_ir_power", 100),
                light_phase_ir_power=config_dict.get("light_phase_ir_power", 100),
                light_phase_white_power=config_dict.get("light_phase_white_power", 50),
            )

            # Start recording
            success = self.recording_manager.start_recording(config)

            if success:
                logger.info("Recording started successfully")
            else:
                logger.error("Failed to start recording")
                self.error_occurred.emit("Failed to start recording")

            return success

        except Exception as e:
            logger.error(f"Error starting recording: {e}")
            self.error_occurred.emit(f"Start error: {e}")
            return False

    def stop_recording(self):
        """Stoppt Recording"""
        try:
            if self.recording_manager:
                self.recording_manager.stop_recording()
                logger.info("Recording stopped")
        except Exception as e:
            logger.error(f"Error stopping recording: {e}")
            self.error_occurred.emit(f"Stop error: {e}")

    def pause_recording(self):
        """Pausiert Recording"""
        try:
            if self.recording_manager:
                self.recording_manager.pause_recording()
                logger.info("Recording paused")
        except Exception as e:
            logger.error(f"Error pausing recording: {e}")
            self.error_occurred.emit(f"Pause error: {e}")

    def resume_recording(self):
        """Setzt Recording fort"""
        try:
            if self.recording_manager:
                self.recording_manager.resume_recording()
                logger.info("Recording resumed")
        except Exception as e:
            logger.error(f"Error resuming recording: {e}")
            self.error_occurred.emit(f"Resume error: {e}")

    # ========================================================================
    # MANAGER EVENT HANDLERS (Internal)
    # ========================================================================

    def _on_recording_started(self):
        """Callback: Recording wurde gestartet"""
        logger.info("Recording started event")
        self._emit_status_update()

    def _on_recording_stopped(self):
        """Callback: Recording wurde gestoppt"""
        logger.info("Recording stopped event")
        self._emit_status_update()

    def _on_recording_paused(self):
        """Callback: Recording wurde pausiert"""
        logger.info("Recording paused event")
        self._emit_status_update()

    def _on_recording_resumed(self):
        """Callback: Recording wurde fortgesetzt"""
        logger.info("Recording resumed event")
        self._emit_status_update()

    def _on_frame_captured(self, current_frame: int, total_frames: int):
        """Callback: Frame wurde captured"""
        logger.debug(f"Frame captured: {current_frame}/{total_frames}")
        self._emit_status_update()

    def _on_progress_updated(self, progress: float):
        """Callback: Progress wurde aktualisiert"""
        logger.debug(f"Progress: {progress:.1f}%")
        # Status update wird automatisch durch frame_captured emitted

    def _on_phase_changed(self, phase_name: str, cycle_number: int):
        """Callback: Phase hat gewechselt"""
        logger.info(f"Phase changed: {phase_name} (cycle {cycle_number})")
        self._emit_status_update()

    def _on_manager_error(self, error_message: str):
        """Callback: Error im RecordingManager"""
        logger.error(f"Manager error: {error_message}")
        self.error_occurred.emit(error_message)

    # ========================================================================
    # STATUS UPDATES TO GUI
    # ========================================================================

    def _emit_status_update(self):
        """Emitted Status-Update für GUI"""
        if not self.recording_manager:
            return

        try:
            status = self.recording_manager.get_status()
            self.status_updated.emit(status)
        except Exception as e:
            logger.error(f"Error getting status: {e}")

    def get_status(self) -> dict:
        """
        Gibt aktuellen Status zurück.

        Returns:
            Status dictionary
        """
        if not self.recording_manager:
            return {
                "recording": False,
                "paused": False,
                "current_frame": 0,
                "total_frames": 0,
                "progress_percent": 0.0,
                "initialized": False,
            }

        return self.recording_manager.get_status()

    def get_state(self):
        """
        Gibt RecordingState-Objekt zurück.

        Returns:
            RecordingState object or None
        """
        if not self.recording_manager:
            return None
        return self.recording_manager.state

    def is_recording(self) -> bool:
        """Gibt zurück ob gerade recording läuft"""
        if not self.recording_manager:
            return False
        return self.recording_manager.is_recording()

    def is_paused(self) -> bool:
        """Gibt zurück ob paused"""
        if not self.recording_manager:
            return False
        return self.recording_manager.is_paused()

    # ========================================================================
    # CLEANUP
    # ========================================================================

    def cleanup(self):
        """Cleanup resources"""
        logger.info("RecordingController cleanup...")

        # Stop recording if active
        if self.recording_manager and self.recording_manager.is_recording():
            self.recording_manager.stop_recording()

        # Cleanup manager
        if self.recording_manager:
            self.recording_manager.cleanup()

        logger.info("RecordingController cleanup complete")
