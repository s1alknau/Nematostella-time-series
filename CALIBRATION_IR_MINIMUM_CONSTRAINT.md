# IR LED Minimum Power Constraint (20%)

## Summary

Added a 20% minimum power constraint for IR LED in dual calibration mode to ensure adequate darkfield illumination quality for transparent specimens.

## Problem

In the previous dual calibration implementation, the IR LED power could be reduced to as low as 1% during binary search. This resulted in:
- IR LED power: 25% in light phase (dual mode)
- While technically functional, low IR power reduces darkfield illumination quality
- Transparent specimens (like Nematostella) require sufficient IR illumination for contrast

## Solution

**File**: [src/timeseries_capture/Recorder/calibration_service.py](src/timeseries_capture/Recorder/calibration_service.py)

**Changes**:
- Modified dual calibration binary search to enforce IR LED minimum of 20%
- Changed `min_ir = 1` to `min_ir = 20` (line 149)
- Updated docstring to document this constraint (lines 128-130)

**Code Change** (lines 146-152):
```python
# Binary search boundaries for both LEDs
# IMPORTANT: IR LED minimum set to 20% to maintain adequate darkfield illumination
# quality for transparent specimens (darkfield microscopy requirement)
min_ir = 20
max_ir = 100
min_white = 1
max_white = 100
```

## Expected Impact

### Before (No Constraint):
- Dual calibration could reduce IR LED to very low values (e.g., 25%)
- White LED compensated by increasing power
- Darkfield illumination potentially compromised

### After (20% Minimum):
- IR LED power constrained to ≥20% in dual mode
- White LED calibrated to reach target intensity with this constraint
- Ensures adequate darkfield illumination while matching intensity
- May slightly increase total LED power usage in light phase

## Example Calibration Results

### Before Constraint:
```
Dark Phase:  IR 50%  = 199.8 grayscale
Light Phase: IR 25% + White 15% = 209.8 grayscale
```

### After Constraint (Expected):
```
Dark Phase:  IR 50%  = 199.8 grayscale (unchanged)
Light Phase: IR ≥20% + White adjusted = ~200 grayscale
```

The calibration algorithm will automatically adjust the white LED power to compensate for the IR minimum constraint and still reach the target intensity of 200 grayscale.

## Testing Recommendations

1. **Run Dual Calibration Again**:
   ```bash
   # In GUI: Click "Calibrate Dual"
   # Observe calibration results in log panel
   ```

2. **Verify IR Minimum**:
   - Check that light phase IR power is ≥20%
   - Check that intensity still matches target (~200 grayscale)

3. **Test Recording**:
   ```bash
   # Start a short test recording (5-10 min)
   # Analyze intensity matching
   python analyze_intensity_match.py recording.h5
   ```

4. **Verify Image Quality**:
   - Visually inspect frames from light phase
   - Ensure darkfield contrast is adequate
   - Compare image quality to previous recordings

## Backward Compatibility

- Existing calibrations are NOT affected (stored values remain unchanged)
- Only new dual calibrations will apply the 20% minimum constraint
- If you want to apply this constraint, re-run dual calibration after updating the code

## Related Files

- [calibration_service.py](src/timeseries_capture/Recorder/calibration_service.py) - Binary search algorithm with IR minimum constraint
- [analyze_intensity_match.py](analyze_intensity_match.py) - Tool to verify intensity matching after calibration
- [TIMING_OPTIMIZATION_CHANGES.md](TIMING_OPTIMIZATION_CHANGES.md) - Previous optimization documentation

## Usage Notes

### When to Re-calibrate

You should re-run dual calibration if:
1. Updating from code without this constraint
2. Image quality in light phase appears poor (low contrast)
3. Current IR LED power in dual mode is below 20%

### Manual Override (Advanced)

If you need a different minimum (e.g., 15% or 25%), modify line 149 in calibration_service.py:
```python
min_ir = 20  # Change this value to desired minimum (1-100)
```

**Note**: Values below 15% may result in poor darkfield illumination. Values above 30% may make it difficult for calibration to reach target intensity if specimen is very bright.

## Trade-offs

### Advantages:
- Better darkfield illumination quality
- More consistent image contrast across recordings
- Prevents over-reliance on white LED in dual mode

### Disadvantages:
- Slightly less flexibility in LED power optimization
- May increase total LED power in light phase
- Calibration may fail if specimen is extremely bright (rare)

## Future Improvements

Potential enhancements (if needed):
1. Make minimum IR power configurable via GUI parameter
2. Add per-specimen calibration profiles with different constraints
3. Implement adaptive minimum based on measured image quality metrics
