# ImSwitch Camera Integration Fix

## Problem

The Nematostella Timelapse plugin shows **gradient test patterns** instead of real HIK GigE camera frames.

## Root Cause

ImSwitch's WidgetFactory only injects `napariViewer`, but the timelapse widget also needs `camera_manager` to access the real camera. Without it, the plugin falls back to DummyCameraAdapter (generates gradients).

## Solution - Add ONE Line to ImSwitch

**File:** `ImSwitch/imswitch/imcontrol/view/ImConMainView.py`

**Location:** Around line 143, right after setting napariViewer

**Add this line:**

```python
# EXISTING CODE (line ~143):
self.factory.setArgument('napariViewer', self.widgets['Image'].napariViewer)

# ADD THIS LINE:
self.factory.setArgument('camera_manager', self._master.detectorsManager)
```

## Complete Context

```python
if 'Image' in enabledDockKeys:
    self.docks['Image'] = Dock('Image Display', size=(1, 1))
    self.widgets['Image'] = self.factory.createWidget(widgets.ImageWidget)
    self.docks['Image'].addWidget(self.widgets['Image'])
    self.factory.setArgument('napariViewer', self.widgets['Image'].napariViewer)

    # ADD THIS LINE ↓
    self.factory.setArgument('camera_manager', self._master.detectorsManager)

    dockArea.addDock(self.docks['Image'], 'left')
```

## What This Does

1. **`self._master.detectorsManager`** - This is ImSwitch's detector/camera manager (contains all cameras like HIK GigE)
2. **`factory.setArgument()`** - Injects the camera_manager into ALL subsequently created widgets
3. The timelapse plugin widget will receive `camera_manager` in its `__init__()` and use the real camera

## Verification

After making the change:

1. Restart ImSwitch
2. Load the Nematostella Timelapse plugin
3. Check the log panel - should show:
   ```
   ✅ HIK GigE camera initialized
   ```
   **NOT:**
   ```
   ⚠️ Using dummy camera (no real camera found)
   ```
4. Start a 1-minute test recording
5. Open the HDF5 file - frames should be real camera images, not gradients

## Technical Details

### How ImSwitch Widget Factory Works

```python
# basewidgets.py
class WidgetFactory:
    def setArgument(self, name, value):
        self._baseKwargs[name] = value  # Stored for all future widgets

    def createWidget(self, widgetClass, *args, **extraKwargs):
        kwargs = self._baseKwargs.copy()  # Inject stored arguments
        widget = widgetClass(*args, **kwargs)
        return widget
```

### How the Timelapse Widget Receives It

```python
# main_widget.py
class NematostellaTimelapseCaptureWidget(QWidget):
    def __init__(self, napari_viewer=None, camera_manager=None):
        # camera_manager will now be passed from WidgetFactory!
        if camera_manager:
            # Use real HIK GigE camera ✅
            self.camera_adapter = create_camera_adapter(
                camera_type='hik',
                camera_manager=camera_manager
            )
        else:
            # Dummy camera (gradients) ❌
            self.camera_adapter = create_camera_adapter(camera_type='dummy')
```

### HIK Camera Adapter

```python
# camera_adapters.py
class HIKCameraAdapter(CameraAdapter):
    def __init__(self, camera_manager, detector_name='Camera'):
        self.camera_manager = camera_manager
        self.detector = camera_manager._detectorManagers[detector_name]

    def capture_frame(self):
        # Get real camera frame from ImSwitch
        return self.detector.getLatestFrame()
```

## Alternative: If detectorsManager is Not Available

If `self._master.detectorsManager` doesn't exist or causes errors, try:

```python
# Option A: Get from master
self.factory.setArgument('camera_manager', self._master._detectorsManager)

# Option B: Import and get singleton
from imswitch.imcontrol.model import getDetectorsManager
self.factory.setArgument('camera_manager', getDetectorsManager())

# Option C: Pass from controller
# In ImConMainViewController or wherever you have access to managers
self.factory.setArgument('camera_manager', detectorsManager)
```

## Files Modified

### ImSwitch Repository
- **`imswitch/imcontrol/view/ImConMainView.py`** (1 line added)

### No Changes Needed in Timelapse Plugin
The plugin already supports receiving `camera_manager` - it's already implemented and ready!

## Related Code

- **WidgetFactory:** `imswitch/imcontrol/view/widgets/basewidgets.py:14-48`
- **Timelapse Widget Init:** `timeseries_capture/main_widget.py:586-604`
- **Camera Adapter Creation:** `timeseries_capture/main_widget.py:145-162`
- **HIK Adapter Implementation:** `timeseries_capture/camera_adapters.py:80-200`
- **HIK Manager (ImSwitch):** `imswitch/imcontrol/model/managers/detectors/HikCamManager.py`

## Testing Checklist

- [ ] Added line to ImConMainView.py
- [ ] Restarted ImSwitch
- [ ] Loaded timelapse plugin
- [ ] Log shows "✅ HIK GigE camera initialized"
- [ ] Started 1-minute test recording
- [ ] Opened HDF5 file
- [ ] Verified frames are real camera images (not gradients)
- [ ] Checked temperature/humidity sensors work
- [ ] Tested LED synchronization
