# Changelog - Per-Phase LED Calibration System

## Version 2.1.0 - 2024-12-04

### Major Features

#### 1. Per-Phase LED Calibration System
- **Dual-mode LED calibration** for intensity-matched phase recordings
- **Automatic per-phase power management** - different LED powers for dark vs light phases
- **GUI integration** - calibration results automatically applied to recordings
- **Target intensity**: 200 grayscale with ≤5% difference between phases

**Files Modified:**
- `src/timeseries_capture/main_widget.py` - Calibration storage and GUI integration
- `src/timeseries_capture/Recorder/recording_manager.py` - Per-phase LED power logic
- `src/timeseries_capture/recording_controller.py` - RecordingConfig with per-phase fields
- `src/timeseries_capture/Recorder/recording_state.py` - Added per-phase power fields
- `src/timeseries_capture/Recorder/calibration_service.py` - Calibration tolerance and iterations

#### 2. IR LED Minimum Constraint (20%)
- **Enforced 20% minimum IR LED power** in dual calibration mode
- Ensures adequate darkfield illumination quality for transparent specimens
- Prevents over-reliance on white LED in dual mode

**Files Modified:**
- `src/timeseries_capture/Recorder/calibration_service.py` (lines 147-152)

#### 3. Camera Exposure Tracking
- **Automatic exposure time logging** during calibration
- **Exposure verification** before starting recording
- **User warnings** if exposure changes between calibration and recording
- **Optional blocking** of recordings with mismatched exposure (>0.5ms difference)

**Files Modified:**
- `src/timeseries_capture/main_widget.py` (lines 74, 532-545, 311-354, 596-601)

#### 4. Timing Optimizations
- **Periodic HDF5 buffer flushing** (every 10 frames instead of every frame)
- **Reduced logging overhead** (debug level for per-frame logs)
- **Results**:
  - Standard deviation reduced from σ=1.11s to σ=0.67s
  - Peak timing spikes reduced from 9s to ~5.8s
  - Cumulative drift reduced from ~4s to ±0.2s

**Files Modified:**
- `src/timeseries_capture/Datamanager/data_manager_hdf5.py` - Periodic flush mechanism
- `src/timeseries_capture/Recorder/recording_manager.py` - Logging optimization

#### 5. Per-LED Power Fields in HDF5
- **Added `ir_led_power` and `white_led_power`** fields to timeseries data
- Enables verification of per-phase LED calibration in recorded data
- Supports diagnostics and analysis tools

**Files Modified:**
- `src/timeseries_capture/Datamanager/data_manager_hdf5.py` (lines 87-88, 306-311)

### Bug Fixes

#### Critical Bug: Phase Recording Not Enabled
- **Fixed**: Recordings showed `phase_enabled: False` despite GUI checkbox being checked
- **Root Cause**: Two missing links in config chain
  1. `recording_controller.py` - Missing per-phase LED power parameters in RecordingConfig
  2. `recording_manager.py` - Incomplete config storage in HDF5 metadata
- **Solution**: Expanded config passing to include all phase and LED power fields

**Files Modified:**
- `src/timeseries_capture/recording_controller.py` (lines 165-168)
- `src/timeseries_capture/Recorder/recording_manager.py` (lines 151-169)

#### String Field Plotting Error
- **Fixed**: TypeError when plotting string fields (phase_str, led_type_str)
- **Solution**: Added categorical conversion and special handling for string data

**Files Modified:**
- `hdf5_timeseries_plotter_v2.py` (lines 162-172, 181-192)

#### Windows Console Encoding
- **Fixed**: UnicodeEncodeError with emoji characters in console output
- **Solution**: Replaced emojis with text labels in diagnostic scripts

**Files Modified:**
- `diagnose_recording_config.py`

### Calibration Parameter Updates

- **Tolerance**: Reduced from 5.0% to 2.5% for tighter intensity matching
- **Max Iterations**: Increased from 10 to 15 for better convergence
- **IR Minimum**: Set to 20% in dual calibration mode

### New Diagnostic Tools

1. **`diagnose_recording_config.py`**
   - Analyzes HDF5 files to verify config values
   - Checks if calibrated LED powers were applied
   - Diagnoses config passing issues

2. **`analyze_intensity_match.py`**
   - Calculates intensity differences between phases
   - Provides calibration recommendations
   - Checks against ≤5% target difference

3. **`check_exposure_settings.py`**
   - Verifies camera exposure settings from HDF5
   - Helps diagnose calibration vs recording mismatches

4. **`hdf5_timeseries_plotter_v2.py`**
   - Enhanced with string field support
   - Added ir_led_power and white_led_power plotting
   - Improved error handling

### Documentation

New documentation files:
- `PER_PHASE_CALIBRATION_GUIDE.md` - Complete calibration system guide
- `TIMING_OPTIMIZATION_CHANGES.md` - HDF5 and logging optimizations
- `CALIBRATION_IR_MINIMUM_CONSTRAINT.md` - 20% IR minimum constraint
- `EXPOSURE_TRACKING_IMPLEMENTATION.md` - Camera exposure tracking system
- `CHANGELOG.md` - This file

### Performance Results

**Timing Improvements:**
- Actual interval std: 1.11s → 0.67s (40% improvement)
- Peak spikes: 9s → 5.8s (36% improvement)
- Cumulative drift: ~4s → ±0.2s (95% improvement)

**Intensity Matching:**
- Previous: Dark 165, Light 178 (7.3% difference)
- Current: Both ~174 with σ=0.35 (consistent)
- Target: ≤5% difference between phases ✅

### Migration Guide

#### For Existing Users

1. **Re-run Calibrations** after updating:
   ```
   - Run IR Calibration (for dark phase)
   - Run Dual Calibration (for light phase with both LEDs)
   - Check log for "💾 Saved for..." messages
   ```

2. **Verify Exposure Consistency**:
   ```
   - Note camera exposure shown during calibration
   - Do NOT change camera exposure before recording
   - GUI will verify and warn if exposure changes
   ```

3. **Enable Phase Recording**:
   ```
   - Check "Enable Day/Night Phase Recording" checkbox
   - Set phase durations (default: 30 min each)
   - Enable "Dual Light Phase" for both LEDs in light phase
   ```

#### Breaking Changes

None - all changes are backward compatible:
- Legacy single LED power values still supported
- Continuous mode (no phases) works as before
- Old HDF5 files can still be read and analyzed

### Known Issues

1. **Old HDF5 files** created before these updates don't have:
   - `exposure_ms` field in timeseries
   - `ir_led_power` and `white_led_power` fields
   - Per-phase power values in metadata

2. **Manual exposure control**: User can still change camera exposure in ImSwitch GUI
   - System warns but doesn't prevent changes
   - Consider "locking" exposure after calibration (future enhancement)

### Contributors

- Implementation and testing: Claude Code & User
- Hardware setup: Nematostella time-series imaging system
- Documentation: Comprehensive guides and diagnostic tools

### Related Issues

- Cumulative drift and timing spikes (RESOLVED)
- LED power calibration not applied (RESOLVED)
- Intensity mismatch between phases (RESOLVED)
- Phase recording not enabled bug (RESOLVED)

---

## Previous Versions

### Version 2.0.0
- Initial release with phase recording support
- Basic LED control and calibration
- HDF5 data storage with timeseries support
