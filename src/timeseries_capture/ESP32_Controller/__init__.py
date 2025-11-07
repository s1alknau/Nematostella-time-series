"""
ESP32 Controller Package - Refactored

Modulare Struktur für ESP32-Kommunikation mit klarer Trennung:
- Communication Layer (serielle Kommunikation)
- Commands Layer (Protokoll-Definitionen)
- State Management (Zustandsverwaltung)
- Main Controller (High-level API)
"""

from .esp32_commands import (
    CameraTypes,
    CommandBuilder,
    Commands,
    LEDStatus,
    LEDTypes,
    ResponseParser,
    Responses,
    SyncResponse,
    TimingConfig,
)
from .esp32_communication import ESP32Communication
from .esp32_controller import ESP32Controller
from .esp32_state import ESP32State

__version__ = "2.0.0-refactored"

__all__ = [
    # Main Controller
    "ESP32Controller",
    # Layers
    "ESP32Communication",
    "ESP32State",
    # Commands
    "Commands",
    "Responses",
    "CameraTypes",
    "LEDTypes",
    "CommandBuilder",
    "ResponseParser",
    # Data Structures
    "SyncResponse",
    "LEDStatus",
    "TimingConfig",
]
