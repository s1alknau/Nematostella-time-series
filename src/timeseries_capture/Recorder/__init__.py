"""
Recorder Package - Recording Business Logic

Modulares Recording-System mit klarer Trennung der Verantwortlichkeiten:

Components:
- RecordingManager: Hauptkoordinator für Recording-Loop
- RecordingState: Thread-safe Zustandsverwaltung
- PhaseManager: Day/Night Cycle Management
- FrameCaptureService: Hardware-Koordination (LED + Camera)
- DataManager: Wird aus Datamanager Package importiert

Architecture:
- Keine direkte Hardware-Abhängigkeit (nutzt Adapter!)
- Thread-safe Operations
- Event-basierte Kommunikation (Qt Signals)
- Clean Separation of Concerns

Usage:
    from Recorder import RecordingManager, RecordingConfig
    from FrameCapture import FrameCaptureService

    # Create service
    capture_service = FrameCaptureService(esp32_adapter, camera_adapter)

    # Create manager
    manager = RecordingManager(frame_capture_service=capture_service)

    # Start recording
    config = RecordingConfig(
        duration_min=60,
        interval_sec=5,
        experiment_name="test",
        output_dir="/path/to/output"
    )
    manager.start_recording(config)

Version: 2.0.0-refactored
"""

from .calibration_service import CalibrationResult, CalibrationService
from .camera_recording_unit import CameraRecordingUnit
from .frame_capture import CameraAdapter, ESP32Adapter, FrameCaptureService
from .multi_camera_controller import MultiCameraController
from .phase_manager import PhaseManager
from .recording_manager import RecordingManager
from .recording_state import PhaseInfo, PhaseType, RecordingConfig, RecordingState, RecordingStatus

# DataManager wird aus separatem Package importiert
# from Datamanager import DataManager

__version__ = "2.1.0-multicam"

__all__ = [
    # Main Manager
    "RecordingManager",
    # Multi-Camera Support
    "MultiCameraController",
    "CameraRecordingUnit",
    # State Management
    "RecordingState",
    "RecordingStatus",
    "RecordingConfig",
    "PhaseType",
    "PhaseInfo",
    # Phase Management
    "PhaseManager",
    # Frame Capture
    "FrameCaptureService",
    "ESP32Adapter",
    "CameraAdapter",
    # Calibration
    "CalibrationService",
    "CalibrationResult",
]


# ============================================================================
# COMPONENT INFO
# ============================================================================

COMPONENT_INFO = {
    "RecordingManager": {
        "description": "Main coordinator for recording process",
        "responsibilities": [
            "Recording loop management",
            "Component coordination",
            "Event emission (Qt Signals)",
            "Error handling & recovery",
        ],
        "signals": [
            "recording_started",
            "recording_stopped",
            "recording_paused",
            "recording_resumed",
            "frame_captured",
            "progress_updated",
            "phase_changed",
            "error_occurred",
        ],
    },
    "RecordingState": {
        "description": "Thread-safe state management",
        "responsibilities": [
            "Status tracking (idle/recording/paused)",
            "Frame counting",
            "Timing management",
            "Phase state tracking",
        ],
    },
    "PhaseManager": {
        "description": "Day/Night cycle management",
        "responsibilities": [
            "Phase transitions (Light ↔ Dark)",
            "Cycle counting",
            "LED type determination",
            "Phase timing",
        ],
    },
    "FrameCaptureService": {
        "description": "Hardware coordination service",
        "responsibilities": [
            "ESP32 + Camera coordination",
            "Sync pulse management",
            "Capture timing",
            "Retry logic",
        ],
    },
}


def get_component_info(component_name: str = None) -> dict:
    """Get information about recorder components"""
    if component_name:
        return COMPONENT_INFO.get(component_name, {})
    return COMPONENT_INFO
