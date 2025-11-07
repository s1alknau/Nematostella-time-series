# Camera Integration Fix

## Problem

The Nematostella Timelapse plugin is using **dummy camera data** (gradient test patterns) instead of real camera frames from ImSwitch.

## Root Cause

When the plugin is loaded via Napari's standard plugin system, only the `napari_viewer` parameter is passed. The `camera_manager` parameter is **not** passed, so the plugin falls back to using `DummyCameraAdapter` which generates synthetic gradient images.

**Code location:** [main_widget.py:145-162](src/timeseries_capture/main_widget.py#L145-L162)

```python
if self.camera_manager:
    # Use HIK GigE via ImSwitch
    self.camera_adapter = create_camera_adapter(
        camera_type='hik',
        camera_manager=self.camera_manager
    )
elif self.viewer:
    # Use Napari viewer
    self.camera_adapter = create_camera_adapter(
        camera_type='napari',
        napari_viewer=self.viewer
    )
else:
    # FALLBACK: Use dummy for testing ← Currently happening!
    self.camera_adapter = create_camera_adapter(camera_type='dummy')
    self.log_panel.add_log("⚠️ Using dummy camera (no real camera found)", "WARNING")
```

## Solution

ImSwitch needs to **manually instantiate** the timelapse widget and pass the `camera_manager` instead of relying on Napari's automatic plugin discovery.

### Option 1: Manual Widget Creation in ImSwitch (RECOMMENDED)

Modify ImSwitch's plugin/widget loading code to manually create the timelapse widget:

```python
# In ImSwitch's widget/plugin loader
from timeseries_capture import create_timelapse_widget

# Create widget with camera_manager
timelapse_widget = create_timelapse_widget(
    napari_viewer=self.viewer,  # Napari viewer from ImSwitch
    camera_manager=self._master.detectorsManager  # ImSwitch camera manager
)

# Add to ImSwitch interface
self.addDockWidget(Qt.RightDockWidgetArea, timelapse_widget)
```

### Option 2: Magicgui Plugin Hook (Alternative)

If using `magicgui` for plugin discovery, you can use a hook to inject the camera_manager:

```python
# In ImSwitch's plugin system
@magicgui_hook
def inject_camera_manager(widget, viewer):
    """Hook to inject camera_manager into plugins"""
    if hasattr(widget, '__init__') and 'camera_manager' in widget.__init__.__code__.co_varnames:
        # Re-initialize with camera_manager
        widget.__init__(
            napari_viewer=viewer,
            camera_manager=get_camera_manager()
        )
    return widget
```

### Option 3: Environment/Context Injection

Create a context that makes the camera_manager globally accessible:

```python
# In ImSwitch startup
from timeseries_capture import set_camera_context

set_camera_context(camera_manager=self._master.detectorsManager)

# Then in main_widget.py, add fallback:
from .context import get_camera_context

def __init__(self, napari_viewer=None, camera_manager=None):
    # Try context if not provided
    if camera_manager is None:
        camera_manager = get_camera_context()
```

## Verification

After implementing the fix, check the plugin's log panel. You should see:

✅ **Correct:**
```
✅ HIK GigE camera initialized
```

❌ **Wrong (current state):**
```
⚠️ Using dummy camera (no real camera found)
```

## Testing

1. Open ImSwitch with HIK GigE camera
2. Load the Nematostella Timelapse plugin
3. Check the log panel for camera initialization message
4. Start a test recording (1 minute, 5 second interval)
5. Open the HDF5 file and verify frames are real camera data, not gradients

## Files to Modify

### In ImSwitch repository:

- **Location:** Find where napari plugins/widgets are loaded
  - Likely in `imswitch/view` or `imswitch/controller`
  - Look for `dock_widget` or `add_plugin` calls

- **Change:** Replace automatic plugin loading with manual widget creation:
  ```python
  from timeseries_capture import create_timelapse_widget

  widget = create_timelapse_widget(
      napari_viewer=self.viewer,
      camera_manager=self._master.detectorsManager
  )
  ```

### In timelapse plugin (optional enhancement):

- **File:** `src/timeseries_capture/main_widget.py`
- **Enhancement:** Add better error message if dummy camera is used:
  ```python
  else:
      # FALLBACK: Use dummy for testing
      self.camera_adapter = create_camera_adapter(camera_type='dummy')
      self.log_panel.add_log(
          "⚠️ Using DUMMY camera - generating test patterns only!",
          "WARNING"
      )
      self.log_panel.add_log(
          "To use real camera: Pass camera_manager to create_timelapse_widget()",
          "INFO"
      )
  ```

## Additional Notes

- The plugin **already supports** receiving `camera_manager` - the parameter is defined in `create_timelapse_widget()`
- The `HIKCameraAdapter` is properly implemented and ready to use
- No changes needed to the firmware or ESP32 code
- The camera adapter will call `detector.getLatestFrame()` to get real camera frames

## References

- Widget creation: [main_widget.py:586-604](src/timeseries_capture/main_widget.py#L586-L604)
- Camera adapter creation: [main_widget.py:145-162](src/timeseries_capture/main_widget.py#L145-L162)
- HIK camera adapter: [camera_adapters.py:80-200](src/timeseries_capture/camera_adapters.py#L80-L200)
