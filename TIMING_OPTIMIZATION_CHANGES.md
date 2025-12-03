# Timing Optimization Changes

## Problem Addressed

Large timing spikes (~9 seconds, ~7 seconds) in `actual_intervals` were causing significant cumulative drift (~4 seconds) during recordings. The expected interval is 5 seconds, but actual intervals showed:
- Mean: μ=4.94s
- Standard deviation: σ=1.11s
- Large spikes up to 9 seconds

## Root Causes Identified

### 1. **HDF5 File I/O Overhead** (Primary Bottleneck)
- HDF5 was automatically flushing buffers to disk after every frame
- Each `save_frame()` call triggered multiple disk write operations
- Creating individual datasets for each frame
- Writing uncompressed data without buffering

### 2. **Logging Overhead** (Secondary Bottleneck)
- `logger.info()` calls on every frame wrote to log file (file I/O)
- `print()` statements on every frame wrote to console (console I/O)
- Phase information logged for every frame

## Changes Implemented

### 1. Periodic HDF5 Flush Mechanism

**File**: [src/timeseries_capture/Datamanager/data_manager_hdf5.py](src/timeseries_capture/Datamanager/data_manager_hdf5.py)

**Changes**:
- Added `flush_interval` parameter to `DataManager.__init__()` (default: 10 frames)
- Added `_frames_since_flush` counter to track frames between flushes
- Modified `save_frame()` to only flush every N frames instead of automatically
- Preserved flush on finalization and close operations

**Code Changes**:
```python
# Added to __init__ (line 423):
def __init__(
    self, telemetry_mode: TelemetryMode = TelemetryMode.STANDARD,
    chunk_size: int = 10,
    flush_interval: int = 10  # NEW PARAMETER
):
    ...
    self.flush_interval = flush_interval
    self._frames_since_flush = 0  # NEW COUNTER

# Added to save_frame() (lines 639-644):
self._frames_since_flush += 1

# Periodic flush to reduce timing spikes
if self._frames_since_flush >= self.flush_interval:
    self._ts_writer.flush()
    self.hdf5_file.flush()
    self._frames_since_flush = 0
    logger.debug(f"HDF5 buffers flushed at frame {frame_number}")
```

**Expected Impact**:
- Reduces disk I/O by 90% (flush every 10 frames instead of every frame)
- Allows HDF5 to batch writes more efficiently
- Should eliminate or significantly reduce large timing spikes

### 2. Reduced Logging Overhead

**File**: [src/timeseries_capture/Recorder/recording_manager.py](src/timeseries_capture/Recorder/recording_manager.py)

**Changes**:
- Removed `print()` statements during frame capture (lines 407-419)
- Changed per-frame `logger.info()` to `logger.debug()` (lines 407-413, 498-502)
- Added periodic progress logging every 10 frames (lines 499-500)

**Code Changes**:
```python
# Before (removed):
print(f"📸 Capturing frame {frame_number}...")
logger.info(f"Capturing frame {frame_number}...")

# After (lines 407-413):
logger.debug(f"Capturing frame {frame_number}...")  # Only in debug mode

# Added periodic progress logging (lines 498-502):
if frame_number % 10 == 0 or frame_number == 1:
    logger.info(f"Progress: Frame {frame_number}/{total_frames} saved")
else:
    logger.debug(f"Frame {frame_number} saved successfully")
```

**Expected Impact**:
- Eliminates console I/O overhead (no more print statements)
- Reduces log file I/O by 90% (only every 10th frame at info level)
- User still gets progress updates every 10 frames
- Full logging available in debug mode if needed

## Usage Notes

### Default Configuration
The optimizations are enabled by default with sensible values:
- HDF5 flush interval: 10 frames
- Progress logging: Every 10 frames

### Custom Configuration
If you need to adjust the flush interval:

```python
from src.timeseries_capture.Datamanager.data_manager_hdf5 import DataManager

# Create DataManager with custom flush interval
data_manager = DataManager(
    telemetry_mode=TelemetryMode.STANDARD,
    chunk_size=10,
    flush_interval=20  # Flush every 20 frames instead of 10
)
```

### Trade-offs

**Flush Interval Settings**:
- **Lower values (5-10 frames)**: More frequent flushes, less data loss if crash, higher I/O overhead
- **Higher values (20-50 frames)**: Less I/O overhead, better timing, more data loss if crash

**Recommended**: Keep default of 10 frames for balance between performance and data safety.

### Debug Mode
To enable full per-frame logging for debugging:

```python
import logging
logging.getLogger("timeseries_capture").setLevel(logging.DEBUG)
```

## Testing Recommendations

1. **Short Test Recording** (5-10 minutes):
   - Verify no errors or crashes
   - Check timing data shows reduced spikes
   - Confirm HDF5 file is valid and complete

2. **Long Test Recording** (1-2 hours):
   - Verify stable operation over time
   - Check cumulative drift is significantly reduced
   - Compare timing statistics to pre-optimization baseline

3. **Plot Timing Data**:
   ```bash
   python hdf5_timeseries_plotter_v2.py recording.h5 --fields actual_intervals,cumulative_drift_sec
   ```

   **Expected Results**:
   - `actual_intervals`: σ < 0.5s (previously σ=1.11s)
   - Peak spikes: < 6 seconds (previously up to 9 seconds)
   - `cumulative_drift_sec`: < 1 second over full recording (previously ~4 seconds)

## Backward Compatibility

All changes are backward compatible:
- Existing code continues to work with default parameters
- HDF5 file format unchanged
- API unchanged (only new optional parameters added)

## Future Improvements

Potential further optimizations (if needed):
1. **Pre-allocate HDF5 datasets** instead of creating per-frame
2. **Use HDF5 chunking** for frame storage
3. **Implement write buffering** to collect multiple frames in memory
4. **Add compression** for image datasets (trade-off: CPU vs I/O)

## Related Files

- [data_manager_hdf5.py](src/timeseries_capture/Datamanager/data_manager_hdf5.py) - HDF5 flush optimization
- [recording_manager.py](src/timeseries_capture/Recorder/recording_manager.py) - Logging optimization
- [hdf5_timeseries_plotter_v2.py](hdf5_timeseries_plotter_v2.py) - Visualization tool for timing analysis
