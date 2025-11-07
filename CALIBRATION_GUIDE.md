# LED Calibration Guide

## Overview

The LED Calibration System automatically adjusts LED power levels to achieve consistent and optimal illumination intensity across different LED types (IR and White).

## Features

- **Automatic Intensity Matching:** Calibrates IR and White LEDs to produce similar intensities
- **Binary Search Algorithm:** Efficiently finds optimal power levels
- **Camera Feedback Loop:** Uses real-time camera frames to measure intensity
- **Multiple Calibration Modes:** IR only, White only, or Dual (both LEDs)
- **Thread-Safe:** Runs in background without blocking UI

## Calibration Modes

### 1. IR LED Calibration
**Purpose:** Adjust IR LED power to reach target intensity

**Use Case:**
- Initial setup of IR LED
- Optimizing IR illumination for recording
- Ensuring consistent IR brightness

**Process:**
1. Starts at 50% IR LED power
2. Captures frame and measures intensity
3. Adjusts power up/down using binary search
4. Repeats until target intensity is reached (within 5% tolerance)

### 2. White LED Calibration
**Purpose:** Adjust White LED power to reach target intensity

**Use Case:**
- Initial setup of White LED
- Optimizing White illumination for light phase
- Ensuring consistent White brightness

**Process:**
1. Starts at 30% White LED power
2. Captures frame and measures intensity
3. Adjusts power up/down using binary search
4. Repeats until target intensity is reached (within 5% tolerance)

### 3. Dual LED Calibration
**Purpose:** Match IR and White LED intensities for consistent dual-mode illumination

**Use Case:**
- **Most Important for Phase Recording!**
- Ensures smooth transitions between light and dark phases
- Prevents intensity jumps when switching LED modes

**Process:**
1. First calibrates IR LED to target intensity
2. Then calibrates White LED to match IR intensity
3. Returns both calibrated power levels

## How to Use

### Prerequisites

**CRITICAL: You must complete ALL prerequisites before calibration!**

1. **ESP32 Connected:** LED controller must be connected (click "Connect" button)
2. **Camera Available:** Live camera feed must be active
3. **ImSwitch Live View:** **START LIVE VIEW FIRST** in ImSwitch (REQUIRED!)
   - The calibration will fail if Live View is not running
   - You should see live camera feed in Napari viewer before calibration

### Step-by-Step Instructions

#### 1. Start ImSwitch and Plugin
```
1. Open ImSwitch
2. Start Live View (click "Live View" button)
3. Open the Nematostella Timelapse Plugin
4. Connect to ESP32
```

#### 2. Navigate to LED Control Panel
```
The LED Control Panel contains:
- LED type selection (IR / White / Dual)
- Power sliders for IR and White
- LED ON/OFF buttons
- Calibration buttons
- Calibration results display
```

#### 3. Run Calibration

**For IR LED:**
```
1. Click "Calibrate IR" button
2. Wait 10-30 seconds (depends on convergence)
3. Check calibration results in text area
4. IR power slider updates automatically
```

**For White LED:**
```
1. Click "Calibrate White" button
2. Wait 10-30 seconds
3. Check calibration results
4. White power slider updates automatically
```

**For Dual LED (Recommended):**
```
1. Click "Calibrate Dual" button
2. Wait 20-60 seconds (calibrates both LEDs sequentially)
3. Check calibration results
4. Both sliders update automatically
```

### Reading Calibration Results

**Success Example:**
```
✅ SUCCESS: Calibration successful at 65% power
   IR Power: 65%
   White Power: 42%
   Measured Intensity: 198.3
   Target Intensity: 200.0
   Error: 0.9%
   Iterations: 5
```

**Interpretation:**
- **IR Power:** Final IR LED power level
- **White Power:** Final White LED power level
- **Measured Intensity:** Actual measured mean intensity from camera
- **Target Intensity:** Desired intensity (default: 200.0)
- **Error:** Percentage difference from target (should be <5%)
- **Iterations:** Number of adjustments made

**Failure Example:**
```
❌ FAILED: Calibration did not converge (best error: 12.3%)
   Best Power: IR=85%, White=45%
   Measured Intensity: 175.4
   Target Intensity: 200.0
   Error: 12.3%
   Iterations: 10
```

**Common Failure Reasons:**
- Target intensity too high (LEDs at 100% but still too dim)
- Target intensity too low (minimum LED power still too bright)
- Camera settings incorrect (exposure, gain)
- No live camera feed

## Algorithm Details

### Binary Search Calibration

**Pseudocode:**
```python
min_power = 1
max_power = 100
current_power = initial_power

for iteration in range(max_iterations):
    # Set LED power
    set_led_power(current_power)

    # Capture frame
    frame = capture_frame()

    # Measure intensity (center ROI)
    measured_intensity = mean(frame[center_region])

    # Calculate error
    error = abs(measured_intensity - target_intensity) / target_intensity * 100

    # Check convergence
    if error <= tolerance_percent:
        return SUCCESS

    # Adjust power (binary search)
    if measured_intensity < target_intensity:
        # Too dim, increase power
        min_power = current_power
        current_power = (current_power + max_power) // 2
    else:
        # Too bright, decrease power
        max_power = current_power
        current_power = (min_power + current_power) // 2

return FAILED (did not converge)
```

### Intensity Measurement

**ROI Selection:**
- Uses **center 50%** of frame to avoid edge artifacts
- For 1920x1200 image: ROI is 480:720, 300:900 (960x600 pixels)

**Calculation:**
```python
roi = frame[h//4 : 3*h//4, w//4 : 3*w//4]
intensity = np.mean(roi)
```

## Configuration Parameters

### Target Intensity
**Default:** 200.0
**Range:** 1.0 - 4095.0 (for 12-bit camera)
**Description:** Desired mean pixel intensity

**Recommendations:**
- **Dark samples:** 150-250 (prevents overexposure)
- **Bright samples:** 100-200 (allows headroom)
- **High dynamic range:** 50-150 (preserves detail)

### Tolerance Percentage
**Default:** 5.0%
**Range:** 1.0 - 20.0%
**Description:** Acceptable error from target

**Recommendations:**
- **Strict matching:** 2-3% (slower, more iterations)
- **Standard:** 5% (good balance)
- **Fast calibration:** 10% (faster, less precise)

### Max Iterations
**Default:** 10
**Range:** 5 - 20
**Description:** Maximum calibration attempts

**Recommendations:**
- **Quick test:** 5 iterations
- **Standard:** 10 iterations (usually sufficient)
- **High precision:** 15-20 iterations

## Troubleshooting

### Problem: "Camera not available"

**Solution:**
1. Start ImSwitch Live View first
2. Ensure camera is connected
3. Check camera layer exists in Napari viewer
4. Verify camera adapter is initialized

### Problem: Calibration fails to converge

**Causes:**
1. Target intensity unreachable
2. Camera exposure too high/low
3. Ambient light interference
4. LED hardware issue

**Solutions:**
1. Adjust target intensity (try 150 instead of 200)
2. Adjust camera exposure in ImSwitch
3. Ensure dark environment (close curtains, turn off lights)
4. Check LED connections and power supply

### Problem: Calibration successful but images still look wrong

**Causes:**
1. Camera auto-exposure enabled
2. Camera gain changing
3. Different camera settings during recording vs calibration

**Solutions:**
1. Disable camera auto-exposure in ImSwitch
2. Lock camera gain to fixed value
3. Use same camera settings for calibration and recording

### Problem: Large difference between IR and White power levels

**Example:** IR=85%, White=20%

**This is normal!** White LEDs are typically much brighter than IR LEDs. The calibration ensures they produce **similar intensities** despite different power levels.

### Problem: Calibration takes too long

**Solutions:**
1. Reduce max_iterations (in code)
2. Increase tolerance_percent (in code)
3. Start with better initial power guess

## Best Practices

### 1. Calibrate in Recording Environment
- Use same lighting conditions as recording
- Same camera settings (exposure, gain)
- Same sample preparation (if applicable)

### 2. Calibrate Before Each Experiment
- LED intensity can drift over time
- Temperature affects LED output
- Ensures consistent illumination

### 3. Use Dual Calibration for Phase Recording
- **Always use "Calibrate Dual"** for phase-based recordings
- Ensures smooth intensity transitions
- Prevents artifacts at phase boundaries

### 4. Verify Calibration
After calibration:
1. Click LED ON with "Dual" mode
2. Check live view intensity
3. Switch between IR and White modes
4. Verify intensities look similar

### 5. Save Calibration Results
- Note calibrated power levels in experiment log
- Use same values for similar experiments
- Recalibrate if LEDs or camera change

## Technical Implementation

### File Structure
```
src/timeseries_capture/
├── Recorder/
│   ├── calibration_service.py    # Core calibration logic
│   └── __init__.py                # Exports CalibrationService
├── main_widget.py                 # UI integration
└── GUI/
    └── led_control_panel.py       # Calibration buttons & results
```

### Key Classes

#### CalibrationService
**Location:** `Recorder/calibration_service.py`

**Methods:**
- `calibrate_ir(initial_power)` - Calibrate IR LED
- `calibrate_white(initial_power)` - Calibrate White LED
- `calibrate_dual(ir_initial, white_initial)` - Calibrate both LEDs

**Constructor:**
```python
CalibrationService(
    capture_callback,          # Function that returns np.ndarray
    set_led_power_callback,    # Function(power, led_type) that sets power
    target_intensity=200.0,    # Target mean intensity
    max_iterations=10,         # Max calibration attempts
    tolerance_percent=5.0      # Acceptable error percentage
)
```

#### CalibrationResult
**Location:** `Recorder/calibration_service.py`

**Fields:**
```python
@dataclass
class CalibrationResult:
    success: bool                   # Calibration succeeded?
    led_type: str                   # 'ir', 'white', 'dual'
    ir_power: int                   # IR LED power (0-100)
    white_power: int                # White LED power (0-100)
    measured_intensity: float       # Final measured intensity
    target_intensity: float         # Target intensity
    error_percent: float            # Error percentage
    iterations: int                 # Iterations used
    message: str                    # Result message
```

### Integration Points

#### 1. Main Widget (`main_widget.py`)
```python
def _on_calibration_requested(self, mode: str):
    # Creates CalibrationService
    # Runs calibration in background thread
    # Updates UI with results
```

#### 2. LED Control Panel (`GUI/led_control_panel.py`)
```python
# Emits signal when calibration button clicked
calibration_requested.emit(mode)  # mode: 'ir', 'white', 'dual'

# Displays results
add_calibration_result(message)
```

## Example Usage (Python API)

```python
from Recorder import CalibrationService, CalibrationResult
import numpy as np

# Define callbacks
def capture_frame() -> np.ndarray:
    # Your frame capture logic
    return camera.get_frame()

def set_led_power(power: int, led_type: str) -> bool:
    # Your LED control logic
    return esp32.set_led_power(power, led_type)

# Create calibrator
calibrator = CalibrationService(
    capture_callback=capture_frame,
    set_led_power_callback=set_led_power,
    target_intensity=200.0,
    max_iterations=10,
    tolerance_percent=5.0
)

# Run calibration
result = calibrator.calibrate_dual(
    ir_initial_power=50,
    white_initial_power=30
)

# Check results
if result.success:
    print(f"✅ Calibration successful!")
    print(f"   IR Power: {result.ir_power}%")
    print(f"   White Power: {result.white_power}%")
    print(f"   Error: {result.error_percent:.1f}%")
else:
    print(f"❌ Calibration failed: {result.message}")
```

## Related Documentation

- [ESP32_BUFFER_FIX.md](ESP32_BUFFER_FIX.md) - ESP32 communication fixes
- [PHASE_TIMING_FIX.md](PHASE_TIMING_FIX.md) - Phase recording timing
- [CAMERA_LAYER_FIX.md](CAMERA_LAYER_FIX.md) - Camera integration

## Summary

✅ **Implemented:** Full LED calibration system with binary search algorithm
✅ **UI Integration:** Calibration buttons in LED Control Panel
✅ **Background Processing:** Non-blocking calibration in separate thread
✅ **Real-time Feedback:** Results displayed in GUI
✅ **Auto-Update:** GUI sliders update with calibrated values

**Next Step:** Test calibration with live camera feed and verify intensity matching! 🎉
