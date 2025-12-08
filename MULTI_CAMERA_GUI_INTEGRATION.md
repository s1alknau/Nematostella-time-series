# Multi-Camera GUI Integration Guide

Guide for integrating multi-camera support into the main GUI (`main_widget.py`).

## Overview

The multi-camera GUI integration adds:
1. **Camera Selection Panel** - Switch between single/multi mode, select active camera
2. **Multi-Camera Status Panel** - Monitor all cameras simultaneously
3. **MultiCameraController** - Backend for parallel recording control

## Integration Steps

### Step 1: Add Configuration Loading

In `main_widget.py`, add configuration detection:

```python
def __init__(self, napari_viewer=None, camera_manager=None, parent=None):
    super().__init__(parent)

    # ... existing code ...

    # Multi-camera support
    self.multi_camera_controller: Optional[MultiCameraController] = None
    self.camera_system_config: Optional[CameraSystemConfig] = None
    self._multi_camera_mode = False

    # Try to load multi-camera config
    self._load_camera_system_config()
```

### Step 2: Load Configuration

```python
def _load_camera_system_config(self):
    """Load camera system configuration if available"""
    from pathlib import Path
    from .Config import load_camera_system_config

    # Look for camera_system.json in various locations
    config_paths = [
        Path("camera_system.json"),
        Path.home() / ".imswitch" / "camera_system.json",
        Path(__file__).parent / "camera_system.json",
    ]

    for config_path in config_paths:
        if config_path.exists():
            try:
                self.camera_system_config = load_camera_system_config(config_path)
                self.log_panel.add_log(
                    f"Multi-camera config loaded: {self.camera_system_config.num_enabled_cameras} cameras",
                    "INFO"
                )
                return
            except Exception as e:
                self.log_panel.add_log(
                    f"Failed to load multi-camera config: {e}",
                    "WARNING"
                )

    # No config found - use single camera mode
    self.log_panel.add_log("No multi-camera config found, using single camera mode", "INFO")
```

### Step 3: Add GUI Panels

Add the new panels to the UI:

```python
def _setup_ui(self):
    """Setup UI"""
    # ... existing tabs ...

    # Add Camera Selection panel if multi-camera config available
    if self.camera_system_config and self.camera_system_config.num_cameras > 1:
        from .GUI import CameraSelectionPanel, MultiCameraStatusPanel

        # Camera selection panel
        self.camera_selection_panel = CameraSelectionPanel()
        self.camera_selection_panel.set_cameras([
            {
                "id": cam.id,
                "name": cam.name,
                "enabled": cam.enabled
            }
            for cam in self.camera_system_config.cameras
        ])

        # Connect signals
        self.camera_selection_panel.camera_selected.connect(self._on_camera_selected)
        self.camera_selection_panel.apply_to_all_clicked.connect(self._on_apply_to_all)
        self.camera_selection_panel.multi_camera_toggled.connect(self._on_multi_camera_toggled)

        # Add to layout (before other tabs or as separate section)
        layout.addWidget(self.camera_selection_panel)

        # Multi-camera status panel
        self.multi_camera_status_panel = MultiCameraStatusPanel()
        self.multi_camera_status_panel.set_cameras([
            {
                "id": cam.id,
                "name": cam.name,
                "enabled": cam.enabled
            }
            for cam in self.camera_system_config.cameras
        ])

        # Add to layout (e.g., at bottom before log panel)
        layout.addWidget(self.multi_camera_status_panel)
    else:
        self.camera_selection_panel = None
        self.multi_camera_status_panel = None
```

### Step 4: Initialize Multi-Camera Controller

```python
def _initialize_hardware(self):
    """Initialize hardware connections"""
    # ... existing single camera/ESP32 init ...

    # Initialize multi-camera controller if config available
    if self.camera_system_config and self.camera_system_config.num_enabled_cameras > 1:
        self._init_multi_camera_controller()
```

```python
def _init_multi_camera_controller(self):
    """Initialize multi-camera controller"""
    from .Recorder import MultiCameraController

    try:
        # Create factory functions
        def camera_factory(camera_config):
            return self._create_camera_adapter_for_config(camera_config)

        def esp32_factory(port):
            return self._create_esp32_controller_for_port(port)

        # Create controller
        self.multi_camera_controller = MultiCameraController(
            system_config=self.camera_system_config,
            camera_factory=camera_factory,
            esp32_factory=esp32_factory,
        )

        # Connect all cameras
        results = self.multi_camera_controller.connect_all()

        success_count = sum(1 for success in results.values() if success)
        self.log_panel.add_log(
            f"Multi-camera: Connected {success_count}/{len(results)} cameras",
            "INFO" if success_count == len(results) else "WARNING"
        )

    except Exception as e:
        self.log_panel.add_log(
            f"Failed to initialize multi-camera controller: {e}",
            "ERROR"
        )
        self.multi_camera_controller = None
```

### Step 5: Handle Camera Selection

```python
def _on_camera_selected(self, camera_id: str):
    """Handle camera selection change"""
    self.log_panel.add_log(f"Selected camera: {camera_id}", "INFO")

    # Update GUI to show settings for selected camera
    # (e.g., load per-camera LED powers if configured)
    if self.multi_camera_controller:
        unit = self.multi_camera_controller.get_unit(camera_id)
        if unit:
            # Update LED panel, etc. with this camera's settings
            pass
```

### Step 6: Handle Apply to All

```python
def _on_apply_to_all(self):
    """Handle apply settings to all cameras"""
    self.log_panel.add_log("Applying settings to all cameras...", "INFO")

    # Get current settings from GUI
    led_powers = self.led_panel.get_led_powers()

    # Apply to all cameras (future: update camera configs)
    self.log_panel.add_log(
        f"Applied: IR={led_powers['ir']}%, White={led_powers['white']}% to all cameras",
        "INFO"
    )

    # TODO: Store in camera configs for future recordings
```

### Step 7: Handle Recording Start/Stop

Modify recording start to use multi-camera controller when enabled:

```python
def _on_start_recording_requested(self):
    """Start recording"""
    # ... existing validation ...

    # Get config
    recording_config = self._get_recording_config()

    # Use multi-camera controller if in multi-camera mode
    if self._multi_camera_mode and self.multi_camera_controller:
        results = self.multi_camera_controller.start_all_recordings(recording_config)

        success_count = sum(1 for success in results.values() if success)

        if success_count > 0:
            self.log_panel.add_log(
                f"Started {success_count}/{len(results)} cameras",
                "SUCCESS" if success_count == len(results) else "WARNING"
            )

            # Start status update timer
            self._start_multi_camera_status_timer()
        else:
            self.log_panel.add_log("Failed to start any cameras", "ERROR")
    else:
        # Use existing single camera recording
        # ... existing code ...
```

### Step 8: Update Status Display

Add timer for updating multi-camera status:

```python
def _start_multi_camera_status_timer(self):
    """Start timer for updating multi-camera status"""
    if not hasattr(self, '_multi_cam_status_timer'):
        from PyQt5.QtCore import QTimer
        self._multi_cam_status_timer = QTimer()
        self._multi_cam_status_timer.timeout.connect(self._update_multi_camera_status)

    self._multi_cam_status_timer.start(1000)  # Update every second

def _update_multi_camera_status(self):
    """Update multi-camera status display"""
    if not self.multi_camera_controller:
        return

    # Get status of all cameras
    status = self.multi_camera_controller.get_all_status()

    # Update status panel
    if self.multi_camera_status_panel:
        self.multi_camera_status_panel.update_all_status(status)

    # Stop timer if no cameras recording
    if not self.multi_camera_controller.is_any_recording:
        self._multi_cam_status_timer.stop()
```

### Step 9: Handle Mode Switching

```python
def _on_multi_camera_toggled(self, enabled: bool):
    """Handle multi-camera mode toggle"""
    self._multi_camera_mode = enabled

    if enabled:
        self.log_panel.add_log("Switched to multi-camera mode", "INFO")
        # Hide single camera controls, show multi controls
    else:
        self.log_panel.add_log("Switched to single camera mode", "INFO")
        # Show single camera controls, hide multi controls
```

## Helper Functions

### Create Camera Adapter from Config

```python
def _create_camera_adapter_for_config(self, camera_config):
    """Create camera adapter from camera config"""
    if camera_config.type == "hik_gige":
        from .camera_adapters import ImSwitchCameraAdapter
        # Use ImSwitch camera manager to get camera by IP
        # Note: Requires camera to be registered in ImSwitch config
        return ImSwitchCameraAdapter(
            camera_manager=self.camera_manager,
            camera_name=camera_config.name,
        )
    else:
        raise ValueError(f"Unsupported camera type: {camera_config.type}")

def _create_esp32_controller_for_port(self, port: str):
    """Create ESP32 controller for COM port"""
    from .ESP32_Controller import ESP32Controller
    return ESP32Controller(port=port)
```

## UI Layout Example

```
┌─────────────────────────────────────────────────────┐
│  Camera Selection Panel                             │
│  Mode: [Multi-Camera ▼]  Camera: [Camera 1 ▼]      │
│  [Apply Settings to All Cameras]                    │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  Recording Control Panel                            │
│  (Standard recording controls)                      │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  Multi-Camera Status                                │
│  3/6 recording | 6/6 connected                      │
│  ─────────────────────────────────────────────────  │
│  ● Camera 1 - Position A    Recording  45.5% (100/220)│
│  ● Camera 2 - Position B    Recording  43.2% (95/220) │
│  ● Camera 3 - Position C    Connected                │
│  ● Camera 4 - Position D    Recording  47.1% (104/220)│
│  ● Camera 5 - Position E    Connected                │
│  ● Camera 6 - Position F    Disconnected             │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  Log Panel                                          │
│  (System logs)                                      │
└─────────────────────────────────────────────────────┘
```

## Testing

### Test with GUI

```python
# In main_widget.py or test script
if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)

    # Create widget with multi-camera config
    widget = NematostellaTimelapseCaptureWidget()
    widget.show()

    sys.exit(app.exec_())
```

### Test Camera Selection

1. Load GUI with multi-camera config
2. Switch to Multi-Camera mode
3. Select different cameras from dropdown
4. Verify status panel shows all cameras
5. Click "Apply to All" and verify log message

### Test Recording

1. Connect all cameras
2. Switch to Multi-Camera mode
3. Configure recording settings
4. Start recording
5. Verify all cameras start recording
6. Monitor status panel for progress
7. Stop recording
8. Verify separate HDF5 files created

## Backward Compatibility

- **Single camera mode**: Works exactly as before if no `camera_system.json` found
- **Existing recordings**: Can still be played back and analyzed
- **Configuration**: Single camera config still supported

## Troubleshooting

### Camera Selection Panel Not Appearing

- Check `camera_system.json` exists and is valid
- Verify config has multiple cameras enabled
- Check logs for config loading errors

### Status Not Updating

- Verify `_multi_cam_status_timer` is started
- Check `update_all_status()` is being called
- Verify `multi_camera_controller` is not None

### Recording Not Starting

- Check all cameras connected before starting
- Verify multi-camera mode is enabled
- Check individual camera connection status

## Next Steps

Future enhancements:
- Per-camera calibration from GUI
- Live preview grid (2×3 or 3×2 layout)
- Individual camera recording controls
- Batch calibration tool

## See Also

- [MULTI_CAMERA_DESIGN.md](MULTI_CAMERA_DESIGN.md) - Architecture documentation
- [MULTI_CAMERA_USAGE.md](MULTI_CAMERA_USAGE.md) - API usage guide
- [test_multi_camera.py](test_multi_camera.py) - Command-line test example
