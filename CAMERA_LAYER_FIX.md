# Camera Layer Fix - Napari Live Layer Access

## Problem

The plugin showed "Using dummy camera" even when ImSwitch's live camera view ("Live: Widefield") was active in Napari.

## Root Cause

**Plugin initialization timing issue:**

1. Plugin loads when Napari starts (before live view is activated)
2. `NapariViewerCameraAdapter` searches for camera layers during `__init__()`
3. No layers exist yet → returns None
4. `is_available()` returned False → recording controller rejected the camera
5. Fell back to dummy camera

**The camera layer only appears AFTER** the user starts live view in ImSwitch, but the adapter wasn't designed to handle this delayed appearance.

## Solution

Modified `NapariViewerCameraAdapter` to be **resilient to delayed layer appearance**:

### 1. Layer Caching
- Cache the layer once found to avoid repeated searches
- Verify cached layer still exists before using it
- Automatically re-search if cached layer disappears

### 2. Deferred Layer Search
- `is_available()` now returns `True` if viewer exists (even without layer)
- Layer search happens during `capture_frame()` instead of just during init
- Adapter keeps trying to find the layer on each capture until successful

### 3. Smart Logging
- Log all available layers during first 5 search attempts (for debugging)
- Reduce log spam after that (only every 10th attempt)
- Clear success/warning messages when layer is found/not found

### 4. Manual Refresh Method
- Added `refresh_camera_layer()` public method
- Can be called from UI to force immediate layer re-detection
- Useful when user starts live view after plugin initialization

## Key Changes

**File:** `camera_adapters.py` ([NapariViewerCameraAdapter](src/timeseries_capture/camera_adapters.py))

### Added Instance Variables
```python
self._cached_layer = None       # Cache layer once found
self._layer_search_count = 0    # Track search attempts
```

### Modified `__init__()`
```python
# Try to find layer immediately, but don't fail if not found
layer = self._get_camera_layer()
if layer:
    logger.info(f"✅ Camera layer found during init: {layer.name}")
else:
    logger.warning("⚠️ No camera layer found yet - will retry when capturing")
```

### Modified `is_available()`
```python
def is_available(self) -> bool:
    if not self.viewer:
        return False

    # If we have a viewer, we're "available" even if no layer yet
    # The layer will be searched for during capture_frame()
    return True
```

### Enhanced `capture_frame()`
```python
def capture_frame(self) -> Optional[np.ndarray]:
    # Get layer (will search and cache if needed)
    layer = self._get_camera_layer()

    if layer is None:
        # No layer found yet - might be waiting for live view to start
        if self._last_frame is not None:
            return self._last_frame
        else:
            if self._layer_search_count % 10 == 1:
                logger.error("No camera layer found (ensure live view is started)")
            return None

    # Get data from layer (with copy to avoid live update issues)
    frame = layer.data.copy()

    # Store and return
    self._last_frame = frame
    return frame
```

### Enhanced `_get_camera_layer()`
```python
def _get_camera_layer(self):
    # Return cached layer if still valid
    if self._cached_layer is not None:
        if self._cached_layer in self.viewer.layers:
            return self._cached_layer
        else:
            self._cached_layer = None

    # Search for layer
    self._layer_search_count += 1

    # Log available layers (first 5 times only)
    if self._layer_search_count <= 5:
        layer_names = [layer.name for layer in self.viewer.layers]
        logger.info(f"Available Napari layers (search #{self._layer_search_count}): {layer_names}")

    # Auto-detect ImSwitch live layer
    for layer in self.viewer.layers:
        if any(indicator in layer.name for indicator in ['Live:', 'Widefield', 'Camera', 'Detector']):
            logger.info(f"✅ Auto-detected ImSwitch layer: {layer.name}")
            self._cached_layer = layer
            self.layer_name = layer.name
            return layer

    # Fallback to any layer with data
    for layer in self.viewer.layers:
        if hasattr(layer, 'data') and layer.data is not None:
            self._cached_layer = layer
            return layer

    return None
```

### New Public Method
```python
def refresh_camera_layer(self) -> bool:
    """
    Force refresh of camera layer detection.
    Useful when live view is started after plugin initialization.
    """
    logger.info("Forcing camera layer refresh...")
    self._cached_layer = None
    self._layer_search_count = 0
    layer = self._get_camera_layer()

    if layer:
        logger.info(f"✅ Camera layer refreshed: {layer.name}")
        return True
    else:
        logger.warning("❌ No camera layer found after refresh")
        return False
```

## How It Works Now

### Scenario 1: Live View Already Running
1. User starts ImSwitch → starts live view → "Live: Widefield" layer created
2. User loads plugin
3. Plugin's `__init__()` searches for layers
4. ✅ Finds "Live: Widefield" immediately
5. Caches it → all captures use real camera frames

### Scenario 2: Plugin Loaded First (Your Case)
1. User loads plugin
2. Plugin's `__init__()` searches for layers
3. ⚠️ No layers found yet → logs warning but doesn't fail
4. User starts live view → "Live: Widefield" layer appears
5. User clicks "Start Recording"
6. First `capture_frame()` call searches again
7. ✅ Finds "Live: Widefield" → caches it
8. All subsequent captures use cached layer → real camera frames!

## Testing

### Expected Logs

**When plugin loads (no live view yet):**
```
INFO: Napari Viewer Camera Adapter initialized (layer=None)
INFO: Available Napari layers (search #1): []
WARNING: ⚠️ No camera layer found yet - will retry when capturing
```

**When recording starts (after live view activated):**
```
INFO: Available Napari layers (search #2): ['Live: Widefield']
INFO: ✅ Auto-detected ImSwitch layer: Live: Widefield
INFO: ✅ Camera layer refreshed: Live: Widefield
```

**During recording:**
```
DEBUG: Capturing frame from layer: Live: Widefield
(Real camera frames captured! 🎉)
```

## Benefits

✅ **No dummy camera anymore** - plugin will find the live layer when it appears
✅ **No ImSwitch modifications needed** - pure Napari layer access
✅ **Works regardless of load order** - plugin can load before or after live view starts
✅ **Automatic recovery** - if layer disappears and reappears, adapter will re-find it
✅ **Performance optimized** - caching avoids repeated layer searches
✅ **Better logging** - clear diagnostic info without spam

## Usage

### Standard Workflow (No Action Needed)
1. Start ImSwitch
2. Load plugin (will show warning if no layer yet - this is OK!)
3. Start live view in ImSwitch
4. Click "Start Recording"
5. ✅ Plugin automatically detects and uses live camera layer

### If Issues Occur
- Restart live view in ImSwitch
- Plugin will automatically detect the layer on next capture
- No need to restart plugin

## Comparison to Backup Implementation

This is the **same approach** used in your backup code ([Backup/capture_controller.py](src/timeseries_capture/Backup/capture_controller.py:151-154)):

```python
# Your backup approach
if self.mode == CaptureMode.IMSWITCH:
    # For ImSwitch, camera_source is the live layer
    if hasattr(self.camera_source, 'data') and self.camera_source.data is not None:
        return self.camera_source.data.copy()
```

Now integrated into the refactored architecture with added resilience and caching!

## Related Documentation

- [NAPARI_LAYER_SOLUTION.md](NAPARI_LAYER_SOLUTION.md) - Original layer access documentation
- [src/timeseries_capture/camera_adapters.py](src/timeseries_capture/camera_adapters.py) - Implementation
- [src/timeseries_capture/Backup/capture_controller.py](src/timeseries_capture/Backup/capture_controller.py) - Original backup code
