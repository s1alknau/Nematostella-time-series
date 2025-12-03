# Per-Phase LED Calibration Guide

## Overview

The system now supports **per-phase LED power calibration** to ensure consistent intensity across all recording phases.

## Problem Solved

**Previous System (Single Power Values):**
- Only one IR power value stored
- Only one White power value stored
- ❌ Could not have different IR powers for different phases
- ❌ Intensity mismatch when using IR alone vs IR+White together

**New System (Per-Phase Powers):**
- `dark_phase_ir_power`: IR power for dark phase (IR only)
- `light_phase_ir_power`: IR power for light phase (dual mode)
- `light_phase_white_power`: White power for light phase
- ✅ Each phase can have different LED powers
- ✅ Consistent intensity across all phases

---

## Calibration Workflows

### Scenario 1: Dark (IR only) + Light (White only)

**Calibration Steps:**
1. Run **IR Calibration** → Saves to `dark_phase_ir_power`
2. Run **White Calibration** → Saves to `light_phase_white_power`

**Recording Result:**
- Dark phase: IR @ X% → intensity 200 ✅
- Light phase: White @ Y% → intensity 200 ✅

**Configuration:**
```python
phase_enabled = True
dual_light_phase = False  # White only for light phase
dark_phase_ir_power = X    # From IR calibration
light_phase_white_power = Y # From White calibration
```

---

### Scenario 2: Dark (IR only) + Light (Dual LED) ⚠️ **YOUR CASE**

**Calibration Steps:**
1. Run **IR Calibration** → Saves to `dark_phase_ir_power`
2. Run **Dual LED Calibration** → Saves to `light_phase_ir_power` AND `light_phase_white_power`

**Recording Result:**
- Dark phase: IR @ X% (alone) → intensity 200 ✅
- Light phase: IR @ Y% + White @ Z% (together) → intensity 200 ✅

**Configuration:**
```python
phase_enabled = True
dual_light_phase = True   # Both LEDs for light phase
dark_phase_ir_power = X         # From IR calibration (IR alone = 200)
light_phase_ir_power = Y        # From Dual calibration (IR + White = 200)
light_phase_white_power = Z     # From Dual calibration (IR + White = 200)
```

**Key Point:**
- X > Y (Dark phase IR power is higher because it's alone)
- Y + Z together gives intensity 200

---

### Scenario 3: Continuous Recording (No Phases)

**Calibration Steps:**
1. Run calibration for your LED type (IR, White, or Dual)

**Recording Result:**
- Uses legacy `ir_led_power` and `white_led_power` fields
- Per-phase powers are ignored

**Configuration:**
```python
phase_enabled = False
ir_led_power = X
white_led_power = Y
```

---

## Implementation Status

### ✅ Completed:
1. **RecordingConfig** extended with per-phase power fields
2. **Recording Manager** updated to:
   - Set LED powers dynamically based on current phase
   - Store actual powers used in metadata
3. **Backward compatibility** maintained for continuous mode

### ✅ GUI Integration Completed

The GUI has been updated to automatically save calibration results to the correct per-phase fields:

**Current Behavior (After Update):**
- **IR calibration** → saves to `_calibrated_dark_phase_ir_power` (used for dark phase)
- **White calibration** → saves to `_calibrated_light_phase_white_power` (used for light phase)
- **Dual calibration** → saves to `_calibrated_light_phase_ir_power` AND `_calibrated_light_phase_white_power` (used for light phase dual mode)

**How It Works:**

1. **Run Calibrations** in the LED Control Panel:
   - IR Calibration → Sets dark phase IR power
   - Dual Calibration → Sets light phase IR + White powers

2. **Calibration Results Stored** in memory:
   - GUI shows: "💾 Saved for DARK phase: IR = X%"
   - GUI shows: "💾 Saved for LIGHT phase (dual): IR = Y%, White = Z%"

3. **Start Recording**:
   - GUI automatically includes calibrated per-phase powers in the config
   - Recording uses calibrated values for each phase

4. **Values Saved in HDF5**:
   - Each frame's metadata includes the actual LED power used
   - `led_power`, `ir_led_power`, `white_led_power` fields reflect per-phase values

**No Manual Configuration Needed!**

The calibration workflow is now fully automated. Just:
1. Run calibrations
2. Start recording
3. Per-phase powers are applied automatically

---

## How to Find Calibration Values

After running calibrations, check the log output:

**IR Calibration:**
```
✅ IR calibration successful! Power=60%, Intensity=198.5, Error=0.75%
```
→ Use `dark_phase_ir_power = 60`

**Dual Calibration:**
```
✅ Dual calibration successful! IR=40%, White=30%, Intensity=202.1, Error=1.05%
```
→ Use `light_phase_ir_power = 40` and `light_phase_white_power = 30`

---

## Testing

To verify the per-phase calibration is working:

1. Run calibrations and note the power values
2. Set per-phase powers in config (manually for now)
3. Start recording with phases
4. Check HDF5 metadata for each frame:
   - Dark frames should have `ir_led_power = dark_phase_ir_power`
   - Light frames should have `ir_led_power = light_phase_ir_power`, `white_led_power = light_phase_white_power`
5. Plot frame intensities - should be consistent (~200) across all phases

---

## Next Steps

1. **Update GUI** to save calibration results to per-phase fields
2. **Add calibration workflow helper** to guide users through correct calibration order
3. **Add validation** to warn if per-phase powers are not set but phase recording is enabled
