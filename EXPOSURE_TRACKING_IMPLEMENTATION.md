# Camera Exposure Tracking for Calibration-Recording Consistency

## Problem

Calibration and recording were using **different camera exposure times**, causing intensity mismatch:

**Example:**
- Calibration at **5ms exposure** → finds IR 50% gives 200 grayscale
- Recording at **3ms exposure** → IR 50% only gives 165 grayscale (17.5% less)
- Result: 7.3% phase difference instead of target ≤5%

## Root Cause

1. **Calibration** uses `camera_adapter.capture_frame()` directly
   - Uses whatever exposure time camera is currently set to
   - No explicit exposure configuration or verification
   - Located in [main_widget.py:511-513](src/timeseries_capture/main_widget.py#L511-L513)

2. **Recording** reads exposure via `camera.get_exposure_ms()`
   - Configures ESP32 timing based on camera exposure
   - Located in [recording_manager.py:174-192](src/timeseries_capture/Recorder/recording_manager.py#L174-L192)

3. **No verification** that exposure remains consistent between calibration and recording

## Solution Implemented

### 1. Calibration Exposure Logging

**File**: [main_widget.py](src/timeseries_capture/main_widget.py)

**Added** (lines 532-545):
- Read camera exposure time before calibration
- Log exposure time to GUI
- Display warning to user not to change exposure

```python
# Read and log camera exposure time for calibration
try:
    camera_exposure_ms = self.camera_adapter.get_exposure_ms()
    self.log_panel.add_log(
        f"📷 Camera exposure time: {camera_exposure_ms:.1f} ms", "INFO"
    )
    self.log_panel.add_log(
        f"⚠️ IMPORTANT: Do NOT change camera exposure between calibration and recording!", "WARNING"
    )
except Exception as e:
    self.log_panel.add_log(
        f"⚠️ Could not read camera exposure: {e}", "WARNING"
    )
    camera_exposure_ms = None
```

### 2. Calibration Exposure Storage

**File**: [main_widget.py](src/timeseries_capture/main_widget.py)

**Added**:
- Variable to store calibration exposure time (line 74)
- Storage after successful calibration (lines 596-601)

```python
# In __init__:
self._calibration_exposure_ms: Optional[float] = None  # Camera exposure during calibration

# After successful calibration:
if camera_exposure_ms is not None:
    self._calibration_exposure_ms = camera_exposure_ms
    self.log_panel.add_log(
        f"💾 Calibration exposure time: {camera_exposure_ms:.1f} ms", "INFO"
    )
```

### 3. Recording Exposure Verification

**File**: [main_widget.py](src/timeseries_capture/main_widget.py)

**Added** (lines 311-354):
- Check camera exposure before starting recording
- Compare with calibration exposure
- Warn user if exposure changed
- Block recording if difference > 0.5ms (optional)

```python
# Verify camera exposure matches calibration exposure
if self._calibration_exposure_ms is not None:
    try:
        current_exposure_ms = self.camera_adapter.get_exposure_ms()
        exposure_diff = abs(current_exposure_ms - self._calibration_exposure_ms)

        self.log_panel.add_log(
            f"📷 Camera exposure: {current_exposure_ms:.1f} ms", "INFO"
        )
        self.log_panel.add_log(
            f"📷 Calibration exposure: {self._calibration_exposure_ms:.1f} ms", "INFO"
        )

        if exposure_diff > 0.5:  # More than 0.5ms difference
            self.log_panel.add_log(
                f"⚠️ WARNING: Camera exposure changed by {exposure_diff:.1f} ms since calibration!",
                "WARNING"
            )
            # Show dialog asking user to confirm
            # Can cancel recording if exposure mismatch detected
```

### 4. Updated Calibration Parameters

**File**: [main_widget.py](src/timeseries_capture/main_widget.py)

**Updated** calibration service initialization (lines 554-555):
```python
max_iterations=15,  # Increased from 10 to 15 for better convergence
tolerance_percent=2.5,  # Reduced from 5.0% to 2.5% for tighter intensity matching
```

## How It Works

### Workflow

1. **User Runs Calibration**:
   - GUI reads current camera exposure time
   - Logs exposure time to console: `"📷 Camera exposure time: 5.0 ms"`
   - Warns user: `"⚠️ IMPORTANT: Do NOT change camera exposure between calibration and recording!"`
   - Runs calibration at this exposure
   - Stores exposure time in `_calibration_exposure_ms`
   - Shows: `"💾 Calibration exposure time: 5.0 ms"`

2. **User Starts Recording**:
   - GUI reads current camera exposure time
   - Compares with stored calibration exposure
   - If difference > 0.5ms:
     - Shows warning in log panel
     - Displays popup dialog asking user to confirm
     - User can cancel to fix exposure first
   - If match:
     - Shows: `"✅ Camera exposure matches calibration (5.0 ms)"`
     - Proceeds with recording

### User Experience

**Successful Case** (exposure matches):
```
[Calibration]
📷 Camera exposure time: 5.0 ms
⚠️ IMPORTANT: Do NOT change camera exposure between calibration and recording!
✅ IR calibration successful!
💾 Calibration exposure time: 5.0 ms
💾 Saved for DARK phase: IR = 50%

[Recording Start]
📷 Camera exposure: 5.0 ms
📷 Calibration exposure: 5.0 ms
✅ Camera exposure matches calibration (5.0 ms)
🎬 Starting recording...
```

**Mismatch Case** (exposure changed):
```
[Calibration]
📷 Camera exposure time: 5.0 ms
💾 Calibration exposure time: 5.0 ms

[Recording Start]
📷 Camera exposure: 3.0 ms
📷 Calibration exposure: 5.0 ms
⚠️ WARNING: Camera exposure changed by 2.0 ms since calibration!
⚠️ This will cause intensity mismatch! Calibration was done at 5.0 ms.

[Dialog Popup]
Camera exposure (3.0 ms) differs from calibration exposure (5.0 ms).
This will cause intensity mismatch between calibration and recording.
Do you want to continue anyway?
[No] [Yes]
```

## Benefits

1. **Prevents Intensity Mismatch**: User is immediately warned if exposure changes
2. **Clear Traceability**: Calibration exposure is logged and can be verified
3. **User Control**: User can choose to cancel and fix exposure, or proceed anyway
4. **Diagnostic Information**: Logs clearly show what exposure was used

## Testing Instructions

1. **Test Normal Workflow** (exposure stays consistent):
   ```
   1. Set camera exposure to 5ms in ImSwitch
   2. Run IR calibration
   3. Check log shows: "📷 Camera exposure time: 5.0 ms"
   4. Run Dual calibration (without changing exposure)
   5. Start recording
   6. Check log shows: "✅ Camera exposure matches calibration (5.0 ms)"
   7. Verify intensities match (dark ~200, light ~200)
   ```

2. **Test Mismatch Detection**:
   ```
   1. Run calibrations at 5ms exposure
   2. Change camera exposure to 3ms in ImSwitch
   3. Try to start recording
   4. Verify warning appears
   5. Verify popup dialog appears
   6. Choose "No" to cancel
   7. Fix exposure back to 5ms
   8. Start recording successfully
   ```

## Related Changes

This change is part of the complete per-phase calibration system:

1. [PER_PHASE_CALIBRATION_GUIDE.md](PER_PHASE_CALIBRATION_GUIDE.md) - Overall calibration system
2. [CALIBRATION_IR_MINIMUM_CONSTRAINT.md](CALIBRATION_IR_MINIMUM_CONSTRAINT.md) - 20% IR minimum for darkfield
3. [TIMING_OPTIMIZATION_CHANGES.md](TIMING_OPTIMIZATION_CHANGES.md) - HDF5 flush and logging optimization

## Known Limitations

1. **Old Recordings**: Recordings made before this update don't have exposure_ms field in HDF5
2. **Manual Camera Control**: User can still change exposure in ImSwitch GUI - we only warn, not prevent
3. **First Calibration**: If no calibration has been run yet, no verification occurs

## Future Improvements

Potential enhancements:
1. **Auto-set exposure**: Automatically set camera exposure to calibration value when starting recording
2. **Exposure in HDF5**: Store calibration exposure in recording metadata for post-recording verification
3. **Exposure history**: Track all calibration exposures to warn if multiple calibrations used different exposures
4. **GUI exposure lock**: Option to "lock" camera exposure after calibration to prevent accidental changes
