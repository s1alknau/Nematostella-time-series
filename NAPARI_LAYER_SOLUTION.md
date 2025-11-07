# ImSwitch Camera Integration via Napari Layer (NO ImSwitch Changes Needed!)

## Solution

Instead of modifying ImSwitch to pass `camera_manager`, we **access the camera frames directly from the Napari layer** that ImSwitch automatically updates.

## How It Works

### ImSwitch Behavior
When ImSwitch displays live camera feed, it creates a Napari image layer (usually named "Live: Camera" or similar) and continuously updates its `.data` property with new frames.

### Plugin Solution
The plugin's `NapariViewerCameraAdapter` now:

1. **Auto-detects ImSwitch live layers** by looking for layers with names containing:
   - `'Live:'`
   - `'Widefield'`
   - `'Camera'`
   - `'Detector'`

2. **Reads frames directly** from `layer.data` - no camera_manager needed!

3. **Falls back** to the first available image layer if no ImSwitch layer is found

## Code Changes Made

### 1. Enhanced Layer Detection (`camera_adapters.py`)

```python
def _get_camera_layer(self):
    """Get camera layer from viewer"""
    if not self.viewer:
        return None

    try:
        # Auto-detect ImSwitch live layer
        for layer in self.viewer.layers:
            # Look for ImSwitch camera layers
            if hasattr(layer, 'name') and any(indicator in layer.name for indicator in
                ['Live:', 'Widefield', 'Camera', 'Detector']):
                logger.info(f"Auto-detected ImSwitch layer: {layer.name}")
                # Cache layer name
                if not self.layer_name:
                    self.layer_name = layer.name
                return layer

        # Fallback: Get first Image layer with data
        for layer in self.viewer.layers:
            if hasattr(layer, 'data') and layer.data is not None:
                logger.info(f"Using fallback layer: {layer.name}")
                if not self.layer_name and hasattr(layer, 'name'):
                    self.layer_name = layer.name
                return layer
    except Exception as e:
        logger.error(f"Error getting camera layer: {e}")

    return None
```

### 2. Better Logging (`main_widget.py`)

```python
elif self.viewer:
    # Use Napari viewer (will auto-detect ImSwitch live layer)
    self.camera_adapter = create_camera_adapter(
        camera_type='napari',
        napari_viewer=self.viewer
    )
    # Check if ImSwitch layer was found
    info = self.camera_adapter.get_camera_info()
    layer_name = info.get('layer_name', 'unknown')
    if any(indicator in str(layer_name) for indicator in ['Live:', 'Widefield', 'Camera', 'Detector']):
        self.log_panel.add_log(f"✅ ImSwitch camera via layer: {layer_name}", "SUCCESS")
    else:
        self.log_panel.add_log(f"✅ Napari camera initialized: {layer_name}", "SUCCESS")
```

## Benefits

✅ **No ImSwitch modifications needed**
✅ **Works with any Napari viewer** that has image layers
✅ **Auto-detects ImSwitch** live camera layers
✅ **Falls back gracefully** to other layers if needed
✅ **Backwards compatible** with standalone Napari usage

## How to Use

### Option 1: Auto-detect (Recommended)
Just open the plugin in ImSwitch - it will automatically find and use the live camera layer:

```python
# Plugin is loaded via napari plugin system
# No camera_manager needed!
```

### Option 2: Manual Layer Selection
If you want to specify a particular layer:

```python
camera_adapter = create_camera_adapter(
    camera_type='napari',
    napari_viewer=viewer,
    layer_name='Live: My Camera'  # Specific layer
)
```

## Verification

After loading the plugin in ImSwitch, check the log panel:

### ✅ Success (ImSwitch detected):
```
✅ ImSwitch camera via layer: Live: Camera
```

### ✅ Success (Other layer):
```
✅ Napari camera initialized: my_layer
```

### ❌ Problem (No layers found):
```
⚠️ Using dummy camera (no real camera found)
```

## Technical Details

### Frame Capture Flow

```
ImSwitch Camera Thread
        ↓
    Updates Napari Layer.data
        ↓
Plugin reads layer.data
        ↓
    Real camera frames! ✓
```

### Comparison with Old Approach

**Old (requires ImSwitch changes):**
```
Plugin → camera_manager → detector.getLatestFrame()
```

**New (no changes needed):**
```
Plugin → napari_layer.data (already updated by ImSwitch)
```

### Performance

- **No extra overhead** - ImSwitch already updates the layer
- **Thread-safe** - Napari layers handle concurrent access
- **Always latest frame** - ImSwitch continuously updates layer.data

## Example: ImSwitch Setup

When you start ImSwitch with a camera:

1. **ImSwitch creates layer:** `viewer.add_image(name='Live: Camera')`
2. **ImSwitch updates continuously:** `layer.data = new_frame`
3. **Plugin reads automatically:** `frame = layer.data.copy()`

No configuration needed!

## Troubleshooting

### Problem: "Using dummy camera" message

**Possible causes:**
1. No Napari layers exist (start ImSwitch camera first)
2. Layer names don't match detection patterns
3. Layers have no data yet

**Solution:**
1. Start ImSwitch live camera view **before** loading the plugin
2. Ensure camera layer is visible in Napari
3. Try manually specifying layer name if auto-detect fails

### Problem: Old/stale frames

**Cause:** ImSwitch camera not running in live mode

**Solution:** Enable live camera mode in ImSwitch before recording

## Comparison with Backup Implementation

This solution is based on your backup code in `Backup/capture_controller.py`:

```python
# From your backup - same concept!
if self.mode == CaptureMode.IMSWITCH:
    # For ImSwitch, camera_source is the live layer
    if hasattr(self.camera_source, 'data') and self.camera_source.data is not None:
        return self.camera_source.data.copy()
```

We've integrated this approach into the refactored architecture using the adapter pattern.

## Files Modified

- **`camera_adapters.py`** - Enhanced `_get_camera_layer()` with ImSwitch layer detection
- **`main_widget.py`** - Improved logging to show which layer is being used

## No Changes Needed

- ❌ ImSwitch source code
- ❌ ImSwitch configuration
- ❌ Firmware
- ❌ ESP32 code

## Testing

1. ✅ Start ImSwitch with HIK GigE camera
2. ✅ Start live camera view (creates "Live: Camera" layer)
3. ✅ Load Nematostella Timelapse plugin
4. ✅ Check log shows: "✅ ImSwitch camera via layer: Live: Camera"
5. ✅ Start test recording (1 min, 5 sec interval)
6. ✅ Verify HDF5 contains real camera frames (not gradients)
7. ✅ Verify temperature/humidity data
8. ✅ Verify LED synchronization works

## Credits

Based on the layer-access approach from your `Backup/` implementation, now integrated into the refactored plugin architecture.
