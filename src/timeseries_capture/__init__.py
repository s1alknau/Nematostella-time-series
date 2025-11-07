"""
Nematostella Timelapse Capture System - Refactored Architecture

Modulares Recording-System für lange Zeitraffer-Aufnahmen mit:
- Day/Night Phase Support
- ESP32-gesteuerte LED-Synchronisation
- HDF5-basiertes Daten-Management
- PyQt5/Qt6-basierte GUI

Package Structure:
==================

timeseries_capture/
├── GUI/                    → View Layer (Pure UI)
│   ├── main_widget.py
│   ├── recording_panel.py
│   ├── phase_panel.py
│   ├── led_control_panel.py
│   ├── status_panel.py
│   └── log_panel.py
│
├── Recorder/               → Business Logic Layer
│   ├── recording_manager.py      (Main Coordinator)
│   ├── recording_state.py        (State Management)
│   ├── phase_manager.py          (Day/Night Cycles)
│   └── frame_capture.py          (Hardware Coordination)
│
├── Datamanager/            → Data Persistence Layer
│   └── data_manager_hdf5.py     (HDF5 Storage)
│
├── ESP32_Controller/       → Hardware Communication Layer
│   ├── esp32_controller.py      (High-level API)
│   ├── esp32_communication.py   (Serial I/O)
│   ├── esp32_commands.py        (Protocol)
│   └── esp32_state.py           (State Management)
│
└── __init__.py            → This file

Architecture Principles:
=======================

1. **Separation of Concerns**
   - GUI: Pure View, keine Business-Logik
   - Recorder: Business-Logik, keine Hardware
   - Hardware: Adapter-basiert, austauschbar

2. **Dependency Injection**
   - Hardware-Adapter werden injiziert
   - Controller wird in GUI injiziert
   - Keine festen Kopplungen

3. **Signal-based Communication**
   - Qt Signals für Events
   - Lose Kopplung zwischen Komponenten
   - Einfache Erweiterbarkeit

4. **Thread-Safety**
   - Locks für shared state
   - Thread-safe Operations
   - Sichere Parallelverarbeitung

Version: 2.0.0-refactored
Author: Nematostella Timelapse Team
"""

# ============================================================================
# PACKAGE METADATA
# ============================================================================

__version__ = "2.0.0-refactored"
__author__ = "Nematostella Timelapse Team"
__description__ = "Modular timelapse recording system for Nematostella experiments"

# ============================================================================
# MAIN EXPORTS (Commonly used components)
# ============================================================================

# GUI - Main Widget
# Datamanager - Main Components
from .Datamanager import DataManager, TelemetryMode
from .GUI import NematostellaTimelapseCaptureWidget, create_timelapse_widget

# Recorder - Main Components
from .Recorder import FrameCaptureService, RecordingConfig, RecordingManager, RecordingStatus

# ESP32 Controller - Main Component
# Note: Only import if ESP32 is available
try:
    from .ESP32_Controller import ESP32Controller

    _ESP32_AVAILABLE = True
except ImportError:
    _ESP32_AVAILABLE = False
    ESP32Controller = None
try:
    from .GUI.esp32_connection_panel import ESP32ConnectionPanel
except ImportError:
    ESP32ConnectionPanel = None
__all__ = [
    # GUI
    "NematostellaTimelapseCaptureWidget",
    "create_timelapse_widget",
    # Recorder
    "RecordingManager",
    "RecordingConfig",
    "RecordingStatus",
    "FrameCaptureService",
    # Datamanager
    "DataManager",
    "TelemetryMode",
    # ESP32 (if available)
    "ESP32Controller",
    "ESP32ConnectionPanel",
    # Metadata
    "__version__",
]


# ============================================================================
# PACKAGE INFO
# ============================================================================

PACKAGE_INFO = {
    "version": __version__,
    "description": __description__,
    "author": __author__,
    "components": {
        "GUI": "User interface components",
        "Recorder": "Recording business logic",
        "Datamanager": "HDF5-based data storage",
        "ESP32_Controller": "Hardware communication",
    },
    "features": [
        "Day/Night phase cycling",
        "ESP32 LED synchronization",
        "HDF5 data storage",
        "Configurable telemetry",
        "Thread-safe operations",
        "Phase transition tracking",
        "Real-time statistics",
    ],
    "dependencies": {
        "required": ["numpy", "h5py", "PyQt5/PyQt6"],
        "optional": ["napari", "pyserial"],
    },
}


def get_package_info() -> dict:
    """Get package information"""
    return PACKAGE_INFO


def print_package_info():
    """Print package information"""
    print("=" * 70)
    print(f"Nematostella Timelapse Capture System v{__version__}")
    print("=" * 70)
    print(f"\n{__description__}\n")
    print("Components:")
    for name, desc in PACKAGE_INFO["components"].items():
        status = "✓" if name != "ESP32_Controller" or _ESP32_AVAILABLE else "✗"
        print(f"  {status} {name:20s} - {desc}")
    print("\nFeatures:")
    for feature in PACKAGE_INFO["features"]:
        print(f"  • {feature}")
    print("\nDependencies:")
    print(f"  Required: {', '.join(PACKAGE_INFO['dependencies']['required'])}")
    print(f"  Optional: {', '.join(PACKAGE_INFO['dependencies']['optional'])}")
    print("\n" + "=" * 70)


# ============================================================================
# QUICK START GUIDE
# ============================================================================

QUICK_START = """
Quick Start Guide
=================

1. GUI-only (for Napari plugin):

   from timeseries_capture import create_timelapse_widget
   widget = create_timelapse_widget(napari_viewer=viewer)

2. Full recording workflow:

   from timeseries_capture import (
       RecordingManager, RecordingConfig,
       FrameCaptureService, DataManager,
       ESP32Controller
   )

   # Setup hardware adapters
   esp32 = ESP32Controller(port="COM3")
   esp32.connect()

   camera_adapter = YourCameraAdapter()  # Implement CameraAdapter

   # Create services
   frame_capture = FrameCaptureService(
       esp32_adapter=esp32,
       camera_adapter=camera_adapter
   )

   # Create recording manager
   recorder = RecordingManager(frame_capture_service=frame_capture)

   # Configure recording
   config = RecordingConfig(
       duration_min=60,
       interval_sec=5,
       experiment_name="test",
       output_dir="/path/to/output",
       phase_enabled=True
   )

   # Start recording
   recorder.start_recording(config)

   # Stop when done
   recorder.stop_recording()

3. Data analysis:

   from timeseries_capture import load_recording_info
   import h5py

   # Load recording
   info = load_recording_info("experiment.h5")

   # Access data
   with h5py.File("experiment.h5", "r") as f:
       frames = f["images"]
       timeseries = f["timeseries"]
       temperatures = timeseries["temperature_celsius"][()]
"""


def print_quick_start():
    """Print quick start guide"""
    print(QUICK_START)


# ============================================================================
# VALIDATION
# ============================================================================


def validate_installation() -> dict:
    """
    Validate package installation and dependencies.

    Returns:
        Dictionary with validation results
    """
    results = {"package_version": __version__, "components": {}, "dependencies": {}, "hardware": {}}

    # Check components
    try:
        from . import GUI

        results["components"]["GUI"] = True
    except ImportError:
        results["components"]["GUI"] = False

    try:
        from . import Recorder

        results["components"]["Recorder"] = True
    except ImportError:
        results["components"]["Recorder"] = False

    try:
        from . import Datamanager

        results["components"]["Datamanager"] = True
    except ImportError:
        results["components"]["Datamanager"] = False

    try:
        from . import ESP32_Controller

        results["components"]["ESP32_Controller"] = True
    except ImportError:
        results["components"]["ESP32_Controller"] = False

    # Check dependencies
    try:
        import numpy

        results["dependencies"]["numpy"] = numpy.__version__
    except ImportError:
        results["dependencies"]["numpy"] = False

    try:
        import h5py

        results["dependencies"]["h5py"] = h5py.__version__
    except ImportError:
        results["dependencies"]["h5py"] = False

    try:
        from qtpy import QtCore

        results["dependencies"]["qtpy"] = True
    except ImportError:
        results["dependencies"]["qtpy"] = False

    # Check hardware
    if _ESP32_AVAILABLE:
        try:
            from .ESP32_Controller import find_esp32_ports

            ports = find_esp32_ports()
            results["hardware"]["esp32_ports_found"] = len(ports)
            results["hardware"]["esp32_ports"] = [p["device"] for p in ports]
        except:
            results["hardware"]["esp32_ports_found"] = 0

    return results


def print_validation_report():
    """Print validation report"""
    results = validate_installation()

    print("\nValidation Report")
    print("=" * 50)
    print(f"Package Version: {results['package_version']}")
    print("\nComponents:")
    for name, status in results["components"].items():
        status_str = "✓ OK" if status else "✗ MISSING"
        print(f"  {name:20s} {status_str}")

    print("\nDependencies:")
    for name, version in results["dependencies"].items():
        if version:
            status_str = f"✓ OK (v{version})" if isinstance(version, str) else "✓ OK"
        else:
            status_str = "✗ MISSING"
        print(f"  {name:20s} {status_str}")

    if "esp32_ports_found" in results["hardware"]:
        print("\nHardware:")
        port_count = results["hardware"]["esp32_ports_found"]
        print(f"  ESP32 Ports Found: {port_count}")
        if port_count > 0:
            for port in results["hardware"]["esp32_ports"]:
                print(f"    - {port}")

    print("=" * 50)


# ============================================================================
# MODULE INITIALIZATION
# ============================================================================

# Print info on import (only in debug mode)
if __debug__:
    import os

    if os.environ.get("TIMELAPSE_DEBUG", "").lower() in ("1", "true", "yes"):
        print_package_info()
