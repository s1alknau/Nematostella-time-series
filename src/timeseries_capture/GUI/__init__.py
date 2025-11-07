"""
GUI Package - Pure View Layer (Refactored)

Modulares GUI-System für Nematostella Timelapse Recording.

Architecture:
- Pure View Layer: KEINE Business-Logik oder Hardware-Zugriffe
- Signal-based Communication: Qt Signals für User-Interaktionen
- Controller-Ready: Vorbereitet für Controller-Injection (Phase 5)
- Testable: Alle Panels einzeln testbar

Components:
- MainWidget: Haupt-Widget mit Tab-Layout
- RecordingPanel: Recording-Konfiguration und Steuerung
- PhasePanel: Day/Night Cycle Konfiguration
- LEDControlPanel: LED-Steuerung und Kalibrierung
- StatusPanel: System-Status Bar (unten)
- LogPanel: System-Log mit Timestamps

Usage:
    from GUI import NematostellaTimelapseCaptureWidget

    # Create widget
    widget = NematostellaTimelapseCaptureWidget(napari_viewer=viewer)

    # Or use plugin entry point
    from GUI import create_timelapse_widget
    widget = create_timelapse_widget(napari_viewer=viewer)

Version: 2.0.0-refactored
"""

from ..main_widget import NematostellaTimelapseCaptureWidget, create_timelapse_widget
from .esp32_connection_panel import ESP32ConnectionPanel
from .led_control_panel import LEDControlPanel
from .log_panel import LogPanel
from .phase_panel import PhaseConfigPanel
from .recording_panel import RecordingControlPanel
from .status_panel import StatusPanel

# Version info
__version__ = "2.0.0-refactored"
__author__ = "s1alknau"

# Public API
__all__ = [
    # Main Widget
    "NematostellaTimelapseCaptureWidget",
    "create_timelapse_widget",
    # Panels
    "RecordingControlPanel",
    "PhaseConfigPanel",
    "LEDControlPanel",
    "ESP32ConnectionPanel",
    "StatusPanel",
    "LogPanel",
    # Version
    "__version__",
]


# ============================================================================
# PANEL DESCRIPTIONS (for documentation)
# ============================================================================

PANEL_INFO = {
    "RecordingControlPanel": {
        "description": "Recording configuration and control (start/stop/pause)",
        "signals": ["start_requested", "stop_requested", "pause_requested", "resume_requested"],
        "methods": ["get_config", "update_status", "update_phase_info"],
    },
    "PhaseConfigPanel": {
        "description": "Day/Night cycle configuration with preview",
        "signals": ["config_changed"],
        "methods": ["get_config", "set_config"],
    },
    "LEDControlPanel": {
        "description": "LED control and calibration interface",
        "signals": [
            "led_on_requested",
            "led_off_requested",
            "led_power_changed",
            "calibration_requested",
        ],
        "methods": ["update_status", "get_led_powers", "set_led_powers"],
    },
    "StatusPanel": {
        "description": "Bottom status bar showing hardware and recording status",
        "signals": [],
        "methods": [
            "update_hardware_status",
            "update_led_status",
            "update_recording_status",
            "update_phase_info",
        ],
    },
    "LogPanel": {
        "description": "System log with timestamps and color coding",
        "signals": [],
        "methods": ["add_log", "clear", "get_log_text"],
    },
}


def get_panel_info(panel_name: str = None) -> dict:
    """
    Get information about GUI panels.

    Args:
        panel_name: Optional panel name. If None, returns all panel info.

    Returns:
        Dictionary with panel information
    """
    if panel_name:
        return PANEL_INFO.get(panel_name, {})
    return PANEL_INFO


# ============================================================================
# VALIDATION
# ============================================================================


def validate_imports():
    """
    Validate that all GUI components are properly imported.
    Useful for testing and debugging.

    Returns:
        bool: True if all imports successful
    """
    required_components = [
        "NematostellaTimelapseCaptureWidget",
        "create_timelapse_widget",
        "RecordingControlPanel",
        "PhaseConfigPanel",
        "LEDControlPanel",
        "ESP32ConnectionPanel",
        "StatusPanel",
        "LogPanel",
    ]

    for component in required_components:
        if component not in globals():
            return False

    return True


# Run validation on import (optional, can be disabled)
if __debug__:
    assert validate_imports(), "GUI package imports failed!"
