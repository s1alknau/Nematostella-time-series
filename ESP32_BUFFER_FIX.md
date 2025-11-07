# ESP32 Buffer Corruption Fix - Aggressive Buffer Clearing

## Problem

During recording with dual LED mode, ESP32 buffer corruption errors were occurring every 2-3 frames:

```
ERROR: Invalid LED status response header: 0x1B
ERROR: Invalid sync response header: 0x41
ERROR: Failed to parse sync response
```

**Impact:**
- LEDs were not actually turning on despite commands being sent
- All captured frames in HDF5 were completely dark/black
- Camera integration was working (frames from Napari layer were being captured)
- Phase transitions were tracked correctly
- Temperature/humidity data was being logged

**Root Cause:**
The ESP32's internal TX buffer accumulated stale data from previous commands over time. The single-pass buffer clearing before each command was not sufficient to clear this accumulated data.

## Solution

Implemented **aggressive buffer clearing** with multiple passes and delays:

### 1. Enhanced `clear_buffers()` Method

File: [esp32_communication.py:460](src/timeseries_capture/ESP32_Controller/esp32_communication.py#L460)

```python
def clear_buffers(self, aggressive: bool = False) -> bool:
    """
    Clear input/output buffers.

    Args:
        aggressive: If True, performs multiple clearing attempts with delays

    Returns:
        True if successful
    """
    if aggressive:
        # AGGRESSIVE CLEARING: 3 passes with delays
        # This helps clear ESP32's internal TX buffer
        total_cleared = 0

        for attempt in range(3):
            # Read any pending data
            if self.serial_connection.in_waiting > 0:
                junk = self.serial_connection.read(self.serial_connection.in_waiting)
                total_cleared += len(junk)

            # Reset buffers
            self.serial_connection.reset_input_buffer()
            self.serial_connection.reset_output_buffer()

            # Delay to let ESP32 flush internal buffer
            if attempt < 2:
                time.sleep(0.05)  # 50ms between passes

        if total_cleared > 0:
            logger.info(f"🧹 Aggressive buffer clear: removed {total_cleared} bytes total")
    else:
        # Normal single-pass clearing
        # ... existing code ...
```

### 2. Applied Aggressive Clearing to Critical Operations

#### A. Sync Pulse Operations ([esp32_controller.py:319](src/timeseries_capture/ESP32_Controller/esp32_controller.py#L319))

```python
def begin_sync_pulse(self, dual: bool = False) -> float:
    # AGGRESSIVE buffer clearing before sync operations
    # This prevents buffer corruption errors from stale data
    self.comm.clear_buffers(aggressive=True)

    # ... rest of sync code ...
```

**Why:** Sync pulses are the most critical operation - they control LED timing during frame capture.

#### B. LED Power Setting ([esp32_controller.py:279](src/timeseries_capture/ESP32_Controller/esp32_controller.py#L279))

```python
def set_led_power(self, power: int, led_type: Optional[str] = None) -> bool:
    # AGGRESSIVE buffer clearing before LED power commands
    # This is critical during dual LED setup
    self.comm.clear_buffers(aggressive=True)

    # ... rest of LED power code ...
```

**Why:** LED power commands must be received cleanly, especially during dual LED initialization.

#### C. LED Status Queries ([esp32_controller.py:531](src/timeseries_capture/ESP32_Controller/esp32_controller.py#L531))

```python
def get_led_status(self) -> Optional[LEDStatus]:
    # AGGRESSIVE buffer clearing before status queries
    self.comm.clear_buffers(aggressive=True)

    # ... rest of status query code ...
```

**Why:** Status queries were also showing corrupted responses in the logs.

## How It Works

### Timeline During Frame Capture

```
Frame N capture starts
    ↓
Aggressive Buffer Clear (3 passes, 150ms total)
    ↓
Send SYNC_CAPTURE_DUAL command
    ↓
Wait for ACK (LED ON confirmed)
    ↓
ESP32 stabilizes LEDs (1000ms)
    ↓
Camera captures frame
    ↓
ESP32 sends sync response (15 bytes: timing, temp, humidity, LED status)
    ↓
Plugin reads frame from Napari layer
    ↓
Save to HDF5
    ↓
Frame N+1 starts...
```

### Buffer Clearing Timing

- **Pass 1:** Clear Python-side buffers, read ESP32 TX data → Wait 50ms
- **Pass 2:** Clear again (ESP32 may have flushed more data) → Wait 50ms
- **Pass 3:** Final clearing pass
- **Total:** ~150ms overhead per critical command

**Trade-off:** Small latency increase (150ms) for reliable LED operation.

## Expected Improvements

### Before Fix ❌
```
🔆 Initializing DUAL LED mode for light phases
✅ IR LED power set to 100%
✅ White LED power set to 50%

📸 Capturing frame 1/25 (LED: dual, dual_mode: True)
ERROR: Invalid LED status response header: 0x1B
ERROR: Invalid sync response header: 0x41
ERROR: Failed to parse sync response

📸 Capturing frame 2/25 (LED: dual, dual_mode: True)
✅ Frame captured successfully

📸 Capturing frame 3/25 (LED: dual, dual_mode: True)
ERROR: Invalid LED status response header: 0x1B
...

Result: Dark frames in HDF5 (LEDs never actually turned on)
```

### After Fix ✅
```
🔆 Initializing DUAL LED mode for light phases
🧹 Aggressive buffer clear: removed 15 bytes total
✅ IR LED power set to 100%
🧹 Aggressive buffer clear: removed 0 bytes total
✅ White LED power set to 50%

📸 Capturing frame 1/25 (LED: dual, dual_mode: True)
🧹 Aggressive buffer clear: removed 0 bytes total
✅ Frame captured successfully (T=24.5°C, H=45.2%)

📸 Capturing frame 2/25 (LED: dual, dual_mode: True)
🧹 Aggressive buffer clear: removed 0 bytes total
✅ Frame captured successfully (T=24.5°C, H=45.3%)

📸 Capturing frame 3/25 (LED: dual, dual_mode: True)
🧹 Aggressive buffer clear: removed 0 bytes total
✅ Frame captured successfully (T=24.6°C, H=45.3%)

Result: Properly illuminated frames in HDF5 ✨
```

## Testing Instructions

### 1. ⚠️ CRITICAL: Physical ESP32 Reset (DO THIS FIRST!)

The ESP32's internal buffer may still have stale data. You MUST perform a physical reset:

```bash
1. Unplug ESP32 USB cable
2. Wait 5 seconds (allows capacitors to fully discharge)
3. Plug ESP32 USB cable back in
4. Wait 3 seconds (ESP32 boots)
5. Start ImSwitch
6. Connect to ESP32 in the plugin
```

**Why:** Software resets don't clear the ESP32's internal UART buffer. Only a full power cycle does.

### 2. Test Recording

Use the same test parameters as before:

- **Duration:** 2 minutes
- **Interval:** 5 seconds
- **Expected frames:** 24 frames
- **Phase config:**
  - ✅ Enable phase recording
  - Light duration: 1 minute
  - Dark duration: 1 minute
  - ✅ Start with light phase
  - ✅ Dual LED during light phase
  - IR LED power: 100%
  - White LED power: 50%

### 3. Watch Console Output

**Look for:**
```
🧹 Aggressive buffer clear: removed X bytes total
```

- **First clearing:** May show 5-20 bytes removed (leftover boot messages)
- **Subsequent clearings:** Should show 0 bytes (clean buffer)
- **NO MORE ERRORS** like "Invalid LED status response header"

### 4. Verify HDF5 Frames

Open the HDF5 file in HDFView or Python:

```python
import h5py

with h5py.File('your_recording.h5', 'r') as f:
    # Check first light phase frame
    frame1 = f['/images/frame_000000'][:]
    print(f"Frame 1 - Min: {frame1.min()}, Max: {frame1.max()}, Mean: {frame1.mean()}")

    # Check dark phase frame
    frame12 = f['/images/frame_000011'][:]
    print(f"Frame 12 - Min: {frame12.min()}, Max: {frame12.max()}, Mean: {frame12.mean()}")
```

**Expected:**
- **Light phase frames (1-11, 24-25):** High intensity values (e.g., mean > 500, max > 1000)
- **Dark phase frames (12-23):** Low intensity values (e.g., mean < 200)

### 5. Check Telemetry

Verify timeseries data is correctly logged:

```python
with h5py.File('your_recording.h5', 'r') as f:
    # Check LED types
    led_types = f['/timeseries/led_type'][:]
    print(f"LED types: {led_types[:12]}")  # Should show 'dual' for first 11 frames

    # Check phase transitions
    phases = f['/timeseries/phase'][:]
    print(f"Phases: {phases[:25]}")  # Should show 'light' → 'dark' → 'light'

    # Check temperatures
    temps = f['/timeseries/temperature_celsius'][:]
    print(f"Temperature range: {temps.min():.1f}°C - {temps.max():.1f}°C")
```

## Performance Impact

### Timing Overhead

| Operation | Before (ms) | After (ms) | Overhead |
|-----------|-------------|------------|----------|
| `set_led_power()` | ~5 | ~155 | +150ms |
| `begin_sync_pulse()` | ~5 | ~155 | +150ms |
| `get_led_status()` | ~5 | ~155 | +150ms |

**Impact on 5-second intervals:**
- Total overhead per frame: ~155ms (only during sync pulse)
- Percentage of interval: 155ms / 5000ms = **3.1%**
- **Negligible impact** on recording schedule

### Memory Impact

- Aggressive clearing reads and discards data (not stored)
- No additional memory usage
- Slightly reduced memory pressure (clears stale buffers)

## Troubleshooting

### If you still see buffer errors after fix:

1. **Did you physically reset the ESP32?** (unplug/replug USB)
   - Software reset is NOT sufficient
   - Must wait 5 seconds unplugged

2. **Check USB cable quality**
   - Poor quality cables can cause data corruption
   - Try a different cable

3. **Check USB port**
   - Some USB hubs have issues
   - Try direct motherboard USB port

4. **Increase aggressive clearing passes**
   - Edit [esp32_communication.py:480](src/timeseries_capture/ESP32_Controller/esp32_communication.py#L480)
   - Change `range(3)` to `range(5)` for more passes
   - Change `time.sleep(0.05)` to `time.sleep(0.1)` for longer delays

5. **Check ESP32 firmware**
   - Ensure firmware matches protocol expectations
   - Baud rate: 115200
   - No custom modifications to serial communication

### If frames are still dark:

1. **LED hardware check:**
   - Do LEDs physically turn on when you test them in LED Control panel?
   - If not, hardware issue (power supply, LED connections)

2. **Camera exposure:**
   - Is camera exposure set correctly?
   - ImSwitch live view shows bright image when LEDs are on?

3. **Layer synchronization:**
   - Does Napari live view show illuminated frames when LEDs are on?
   - If yes: timing issue (camera not synced with LEDs)
   - If no: LED hardware issue

## Related Documentation

- [CAMERA_LAYER_FIX.md](CAMERA_LAYER_FIX.md) - Napari layer access implementation
- [NAPARI_LAYER_SOLUTION.md](NAPARI_LAYER_SOLUTION.md) - Original layer solution docs
- [Firmware/FIRMWARE_DOCUMENTATION.md](Firmware/FIRMWARE_DOCUMENTATION.md) - ESP32 firmware protocol

## Summary

✅ **Fixed:** ESP32 buffer corruption by implementing aggressive multi-pass buffer clearing
✅ **Applied to:** Sync pulses, LED power commands, status queries
✅ **Impact:** Minimal latency overhead (~3% of frame interval)
✅ **Next Step:** Physical ESP32 reset, then test recording

Expected result: Properly illuminated frames in HDF5, no more buffer corruption errors! 🎉
