# Temperature Calibration Guide

## Overview

The ESP32 temperature readings are calibrated with a **-2.0°C offset** to compensate for:
- **ESP32 self-heating:** ~+1°C from the microcontroller's operation
- **LED proximity heating:** ~+1°C from nearby LED components

## Current Configuration

**Location:** [esp32_controller.py:497](src/timeseries_capture/ESP32_Controller/esp32_controller.py#L497)

```python
TEMPERATURE_CALIBRATION_OFFSET = -2.0  # Applied offset in °C
temperature = temperature + TEMPERATURE_CALIBRATION_OFFSET
```

## How It Works

### Sensor Hardware
- **Sensor:** DHT22 temperature/humidity sensor
- **Accuracy:** ±0.5°C (typical)
- **Location:** GPIO Pin 14 on ESP32

### Measurement Process
1. ESP32 turns off all LEDs (both IR and White)
2. Waits 50ms for sensor stabilization
3. Reads DHT22 sensor (with 3 retry attempts)
4. Applies 5-value moving average filter (firmware-side)
5. Applies **-2.0°C calibration offset** (Python-side)
6. Restores LED states

### Why Offset is Needed

**Without offset:**
- Room temperature: 23°C
- ESP32 reads: 25°C (too high due to self-heating)

**With -2.0°C offset:**
- Room temperature: 23°C
- ESP32 reads raw: 25°C
- After calibration: 23°C ✅

## Adjusting the Offset

### Step 1: Verify Current Readings

Place a calibrated reference thermometer next to the ESP32 and compare readings:

```python
# In ImSwitch plugin
sensor_data = esp32_controller.get_sensor_data()
print(f"ESP32 Temperature: {sensor_data['temperature']}°C")
print(f"Reference Thermometer: ___ °C")
```

### Step 2: Calculate Required Offset

```
Required Offset = Reference Temperature - Raw ESP32 Temperature
```

**Example:**
- Reference thermometer: 22.5°C
- ESP32 reads (after current -2.0°C offset): 23.5°C
- Difference: 22.5 - 23.5 = -1.0°C
- New offset should be: -2.0 + (-1.0) = **-3.0°C**

### Step 3: Update Offset

Edit [esp32_controller.py:497](src/timeseries_capture/ESP32_Controller/esp32_controller.py#L497):

```python
# Change from:
TEMPERATURE_CALIBRATION_OFFSET = -2.0

# To your calculated value:
TEMPERATURE_CALIBRATION_OFFSET = -3.0  # Adjusted for your environment
```

### Step 4: Test

1. Restart ImSwitch
2. Reconnect to ESP32
3. Check sensor readings
4. Verify against reference thermometer
5. Repeat if necessary

## Expected Temperature Ranges

### Typical Indoor Lab Environment
- **Room Temperature:** 20-24°C
- **With ESP32/LED heating:** +1-3°C
- **Expected readings (uncalibrated):** 22-27°C
- **After -2.0°C offset:** 20-25°C ✅

### Warning Conditions
- **< 15°C:** Unusually cold (check heating)
- **> 30°C:** Too hot (check ventilation, LED power)
- **> 35°C:** Critical (risk of hardware damage)

## Humidity Readings

Humidity measurements are **not** calibrated (offset not needed).

**Typical range:** 30-70% RH
**DHT22 accuracy:** ±2-5% RH

If humidity readings seem incorrect:
- Check for condensation on sensor
- Ensure sensor is not directly exposed to airflow
- Verify sensor is not in enclosed space with poor ventilation

## Troubleshooting

### Temperature Too High (Even After Offset)

**Possible causes:**
1. **Insufficient ventilation:** Add air circulation
2. **LED power too high:** Reduce IR/White power percentage
3. **Offset too small:** Increase offset magnitude (e.g., -2.0 → -3.0)

**Solutions:**
```python
# Reduce LED power
esp32_controller.set_led_power(70, 'ir')    # Instead of 100%
esp32_controller.set_led_power(40, 'white') # Instead of 50%

# Or adjust offset
TEMPERATURE_CALIBRATION_OFFSET = -3.0  # More aggressive correction
```

### Temperature Too Low (Below Reference)

**Possible causes:**
1. **Offset too large:** Temperature over-corrected
2. **Reference thermometer inaccurate:** Verify with second thermometer
3. **Sensor location difference:** ESP32 in different microclimate

**Solutions:**
```python
# Reduce offset magnitude
TEMPERATURE_CALIBRATION_OFFSET = -1.5  # Less aggressive correction
```

### Unstable Readings (Fluctuating)

**Possible causes:**
1. **Airflow near sensor:** Cover sensor or move away from vents
2. **LED cycling:** Heating/cooling cycles from recording
3. **Sensor defect:** Replace DHT22

**Solutions:**
- Firmware already applies 5-value moving average filter
- Increase stabilization time (firmware modification needed)
- Use longer intervals between measurements

## Technical Details

### Calibration Location

The offset is applied in **Python** (not firmware) for easy adjustment:

**File:** `src/timeseries_capture/ESP32_Controller/esp32_controller.py`
**Method:** `get_sensor_data()`
**Line:** 497

### Data Flow

```
DHT22 Sensor
    ↓
ESP32 Firmware (5-value moving average)
    ↓
Serial Communication (int16, scaled by 10)
    ↓
Python Parsing (divide by 10)
    ↓
[CALIBRATION OFFSET APPLIED HERE] ← -2.0°C
    ↓
GUI Display / HDF5 Storage
```

### Alternative: Firmware-Side Calibration

You could also add the offset in firmware (main.cpp:446):

```cpp
// In sendStatusWithSensorData()
int16_t temp_scaled = (int16_t)(temp * 10.0);

// ADD FIRMWARE OFFSET
const int16_t TEMP_OFFSET = -20;  // -2.0°C (scaled by 10)
temp_scaled = temp_scaled + TEMP_OFFSET;
```

**Pros:**
- Offset applied before transmission
- Consistent across all software

**Cons:**
- Requires firmware recompilation and upload
- Harder to adjust/test

## Recording and Storage

Temperature and humidity are recorded in HDF5 files:

**Dataset:** `/timeseries/temperature` and `/timeseries/humidity`
**Units:** °C and % (respectively)
**Frequency:** Once per frame capture

The calibrated values are stored, so all historical data uses the offset that was active during recording.

## Best Practices

### 1. Calibrate Before Long Recordings
- Perform calibration with reference thermometer
- Document offset value in lab notebook
- Note environmental conditions

### 2. Monitor During Recording
- Check temperature display in GUI
- Ensure temperature stays within expected range
- Alert if temperature exceeds 30°C

### 3. Consistent Environment
- Same room temperature as calibration
- Similar LED power settings
- Same ventilation conditions

### 4. Periodic Verification
- Re-check calibration monthly
- After firmware updates
- After hardware modifications

## Related Documentation

- [CALIBRATION_GUIDE.md](CALIBRATION_GUIDE.md) - LED intensity calibration
- [ESP32_BUFFER_FIX.md](ESP32_BUFFER_FIX.md) - Communication improvements
- [Firmware/FIRMWARE_DOCUMENTATION.md](Firmware/FIRMWARE_DOCUMENTATION.md) - Firmware details

## Summary

✅ **Default offset:** -2.0°C compensates for ESP32 + LED heating
✅ **Easy to adjust:** Single constant in esp32_controller.py
✅ **Well-documented:** Clear comments and this guide
✅ **Validated:** Typical indoor lab conditions

**Current configuration should provide accurate readings for most environments.** Adjust only if reference measurements show consistent discrepancy.
