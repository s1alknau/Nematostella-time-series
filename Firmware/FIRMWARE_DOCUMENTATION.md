# ESP32 Firmware Documentation - Version 2.2

## Overview

This firmware enables the ESP32 microcontroller to synchronize LED illumination with camera exposure for Nematostella timelapse recording. It provides precise timing control, environmental monitoring, and Python-compatible serial communication.

**Current Version:** 2.2
**Release Date:** 2024-11-03
**Compatibility:** Python plugin version 2.0+

---

## Features

- **Dual LED Control**: Independent PWM control for IR (850nm) and White LEDs
- **Hardware Synchronization**: Precise LED-camera sync with configurable timing
- **Environmental Monitoring**: DHT22 temperature and humidity sensor integration
- **Python-Compatible Protocol**: Binary serial communication optimized for Python
- **Flexible Timing**: Configurable LED stabilization and exposure times
- **Power Management**: Independent power control (0-100%) for each LED
- **Sensor Filtering**: Moving average filter for stable sensor readings
- **Automatic Buffer Management**: Prevents serial buffer overflow

---

## Hardware Configuration

### Pin Assignments

| Function | GPIO Pin | Notes |
|----------|----------|-------|
| IR LED PWM | GPIO 4 | PWM Channel 0, 15kHz |
| White LED PWM | GPIO 15 | PWM Channel 1, 15kHz |
| DHT22 Data | GPIO 14 | Requires 10kΩ pull-up resistor |
| USB Serial | Built-in | 115200 baud |

### PWM Configuration

- **Frequency:** 15 kHz
- **Resolution:** 10-bit (0-1023)
- **Power Range:** 0-100% (mapped to PWM duty cycle)

### DHT22 Sensor

- **Type:** DHT22 (AM2302)
- **Power:** 3.3V from ESP32
- **Pull-up:** 10kΩ resistor required on data line
- **Sampling:** Filtered with 5-sample moving average

---

## Default Settings

### Timing Parameters

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| LED Stabilization | 400 ms | 10-10000 ms | Time for LED to stabilize before exposure |
| Exposure Time | 20 ms | 0-30000 ms | Camera exposure duration |
| **Total LED On Time** | **420 ms** | - | Stabilization + Exposure |

### Power Settings

| LED Type | Default Power | Range |
|----------|---------------|-------|
| IR LED | 100% | 0-100% |
| White LED | 100% | 0-100% |

### Camera Type

- **Default:** HIK GigE (Type 1)
- **Alternative:** USB Generic (Type 2)

---

## Serial Communication Protocol

### Serial Settings

- **Baud Rate:** 115200
- **Data Bits:** 8
- **Parity:** None
- **Stop Bits:** 1
- **Flow Control:** None
- **Timeout:** 100 ms

### Command Format

All commands are single-byte or multi-byte sequences sent via serial.

**General Pattern:**
```
[COMMAND_BYTE] [DATA_BYTES (optional)]
```

---

## Command Reference

### Basic LED Control

#### LED ON (0x01)
Turn on the currently selected LED.

**Request:**
```
0x01
```

**Response:**
```
0xAA  (RESPONSE_LED_ON_ACK)
```

**Example (Python):**
```python
serial.write(b'\x01')
response = serial.read(1)  # Expect b'\xAA'
```

---

#### LED OFF (0x00)
Turn off the currently selected LED.

**Request:**
```
0x00
```

**Response:**
```
0xAA  (RESPONSE_LED_ON_ACK)
```

---

### LED Selection

#### SELECT IR LED (0x20)
Select IR LED as the active LED.

**Request:**
```
0x20
```

**Response:**
```
0x30  (RESPONSE_LED_IR_SELECTED)
```

---

#### SELECT WHITE LED (0x21)
Select White LED as the active LED.

**Request:**
```
0x21
```

**Response:**
```
0x31  (RESPONSE_LED_WHITE_SELECTED)
```

---

#### TURN OFF ALL LEDs (0x22)
Turn off both IR and White LEDs simultaneously.

**Request:**
```
0x22
```

**Response:**
```
0xAA  (RESPONSE_LED_ON_ACK)
```

---

### Power Control

#### SET LED POWER (0x10)
Set power for the currently selected LED.

**Request:**
```
0x10 [POWER]
```
- `POWER`: 1 byte (0-100)

**Response:**
```
0xAA  (RESPONSE_LED_ON_ACK)
```

**Example:**
```python
# Set current LED to 75% power
serial.write(b'\x10\x4B')  # 0x4B = 75
```

---

#### SET IR POWER (0x24)
Set IR LED power specifically.

**Request:**
```
0x24 [POWER]
```
- `POWER`: 1 byte (0-100)

**Response:**
```
0xAA  (RESPONSE_LED_ON_ACK)
```

---

#### SET WHITE POWER (0x25)
Set White LED power specifically.

**Request:**
```
0x25 [POWER]
```
- `POWER`: 1 byte (0-100)

**Response:**
```
0xAA  (RESPONSE_LED_ON_ACK)
```

---

### Synchronized Capture

#### SYNC CAPTURE (0x0C)
Perform synchronized LED-camera capture with currently selected LED.

**Request:**
```
0x0C
```

**Response (15 bytes):**
```
0x1B [TEMP_HIGH] [TEMP_LOW] [HUM_HIGH] [HUM_LOW] [DUR_HIGH] [DUR_LOW] [LED_TYPE] [IR_STATE] [WHITE_STATE] [IR_POWER] [WHITE_POWER] [STAB_HIGH] [STAB_LOW]
```

**Response Fields:**
- Byte 0: `0x1B` (RESPONSE_SYNC_COMPLETE)
- Bytes 1-2: Temperature × 100 (uint16, big-endian, e.g., 2350 = 23.50°C)
- Bytes 3-4: Humidity × 100 (uint16, big-endian, e.g., 5500 = 55.00%)
- Bytes 5-6: Sync duration in ms (uint16, big-endian)
- Byte 7: LED type (0=IR, 1=White)
- Byte 8: IR LED state (0=off, 1=on)
- Byte 9: White LED state (0=off, 1=on)
- Byte 10: IR power (0-100)
- Byte 11: White power (0-100)
- Bytes 12-13: Stabilization time in ms (uint16, big-endian)

**Timing Sequence:**
1. Turn on LED
2. Wait for LED_STABILIZATION_MS (default 400ms)
3. Camera exposure for EXPOSURE_MS (default 20ms)
4. Turn off LED
5. Send response with sensor data

**Total Duration:** Stabilization + Exposure (default 420ms)

---

#### SYNC CAPTURE DUAL (0x2C)
Perform synchronized capture with BOTH IR and White LEDs on simultaneously.

**Request:**
```
0x2C
```

**Response:** Same 15-byte format as SYNC CAPTURE

**Use Case:** Dual-wavelength imaging or calibration with combined illumination.

---

### Timing Configuration

#### SET TIMING (0x11)
Configure LED stabilization and exposure times.

**Request (5 bytes):**
```
0x11 [STAB_HIGH] [STAB_LOW] [EXP_HIGH] [EXP_LOW]
```
- Bytes 1-2: Stabilization time in ms (uint16, big-endian)
- Bytes 3-4: Exposure time in ms (uint16, big-endian)

**Response:**
```
0x21  (RESPONSE_TIMING_SET)
```

**Example:**
```python
# Set 1000ms stabilization + 50ms exposure
stab = 1000
exp = 50
cmd = struct.pack('>BHH', 0x11, stab, exp)
serial.write(cmd)  # b'\x11\x03\xE8\x00\x32'
```

**Validation:**
- Stabilization: 10-10000 ms
- Exposure: 0-30000 ms

---

### Status & Diagnostics

#### GET STATUS (0x02)
Query ESP32 status and sensor readings.

**Request:**
```
0x02
```

**Response (5 bytes):**
```
[STATUS] [TEMP_HIGH] [TEMP_LOW] [HUM_HIGH] [HUM_LOW]
```
- Byte 0: Status code
  - `0x11` (RESPONSE_STATUS_ON): LED is on
  - `0x10` (RESPONSE_STATUS_OFF): LED is off
- Bytes 1-2: Temperature × 100 (uint16, big-endian)
- Bytes 3-4: Humidity × 100 (uint16, big-endian)

---

#### GET LED STATUS (0x23)
Get detailed LED configuration and state.

**Request:**
```
0x23
```

**Response (6 bytes):**
```
0x32 [LED_TYPE] [IR_STATE] [WHITE_STATE] [IR_POWER] [WHITE_POWER]
```
- Byte 0: `0x32` (RESPONSE_LED_STATUS)
- Byte 1: Current LED type (0=IR, 1=White)
- Byte 2: IR LED state (0=off, 1=on)
- Byte 3: White LED state (0=off, 1=on)
- Byte 4: IR power (0-100)
- Byte 5: White power (0-100)

---

### Camera Configuration

#### SET CAMERA TYPE (0x13)
Configure camera type for timing optimization.

**Request:**
```
0x13 [CAMERA_TYPE]
```
- `CAMERA_TYPE`:
  - `0x01`: HIK GigE camera
  - `0x02`: USB Generic camera

**Response:**
```
0xAA  (RESPONSE_LED_ON_ACK)
```

---

## Complete Command Table

| Command | Code | Data Bytes | Response | Description |
|---------|------|------------|----------|-------------|
| LED_ON | 0x01 | 0 | 0xAA | Turn on current LED |
| LED_OFF | 0x00 | 0 | 0xAA | Turn off current LED |
| STATUS | 0x02 | 0 | 5 bytes | Get status + sensors |
| SYNC_CAPTURE | 0x0C | 0 | 15 bytes | Synchronized capture |
| SYNC_CAPTURE_DUAL | 0x2C | 0 | 15 bytes | Dual LED capture |
| SET_LED_POWER | 0x10 | 1 | 0xAA | Set current LED power |
| SET_TIMING | 0x11 | 4 | 0x21 | Set stab + exposure |
| SET_CAMERA_TYPE | 0x13 | 1 | 0xAA | Set camera type |
| SELECT_LED_IR | 0x20 | 0 | 0x30 | Select IR LED |
| SELECT_LED_WHITE | 0x21 | 0 | 0x31 | Select White LED |
| LED_DUAL_OFF | 0x22 | 0 | 0xAA | Turn off both LEDs |
| GET_LED_STATUS | 0x23 | 0 | 6 bytes | Get LED config |
| SET_IR_POWER | 0x24 | 1 | 0xAA | Set IR power |
| SET_WHITE_POWER | 0x25 | 1 | 0xAA | Set White power |

---

## Response Codes

| Code | Name | Meaning |
|------|------|---------|
| 0xAA | RESPONSE_LED_ON_ACK | General acknowledgment |
| 0x1B | RESPONSE_SYNC_COMPLETE | Sync capture completed |
| 0x21 | RESPONSE_TIMING_SET | Timing configured |
| 0x30 | RESPONSE_LED_IR_SELECTED | IR LED selected |
| 0x31 | RESPONSE_LED_WHITE_SELECTED | White LED selected |
| 0x32 | RESPONSE_LED_STATUS | LED status data |
| 0x11 | RESPONSE_STATUS_ON | Status: LED on |
| 0x10 | RESPONSE_STATUS_OFF | Status: LED off |
| 0xFF | RESPONSE_ERROR | Error occurred |

---

## Environmental Sensor Details

### DHT22 Specifications

- **Temperature Range:** -40°C to 80°C
- **Temperature Accuracy:** ±0.5°C
- **Humidity Range:** 0-100% RH
- **Humidity Accuracy:** ±2-5% RH
- **Sampling Rate:** Max 0.5 Hz (one reading per 2 seconds)

### Sensor Filtering

The firmware implements a 5-sample moving average filter to reduce noise:

1. Reads sensor every query
2. Validates reading (checks for NaN, out-of-range values)
3. Adds valid reading to 5-sample history buffer
4. Returns average of valid samples
5. Rejects outliers (>10°C difference from previous reading)

This ensures stable, reliable sensor data even in noisy environments.

---

## Timing Details

### Synchronized Capture Sequence

```
Time →
│
├─ [LED OFF] ───────────────────┐
│                                │
├─ CMD_SYNC_CAPTURE received     │
│                                │
├─ [LED ON] ────────────────────┤  ← LED turns on
│                                │
├─ Stabilization Period ────────┤  ← 400ms (default)
│   (LED warming up)             │
│                                │
├─ Exposure Period ─────────────┤  ← 20ms (default)
│   (Camera capturing)           │
│                                │
├─ [LED OFF] ────────────────────┤  ← LED turns off
│                                │
├─ Read Sensors ─────────────────┤  ← DHT22 query
│                                │
├─ Send Response (15 bytes) ────┤  ← 0x1B + data
│
└─ Total Duration: ~420ms
```

**Key Points:**
- LED stays on for **(Stabilization + Exposure)** ms
- Sensor read happens *after* LED turns off
- Response sent immediately after sensor read
- Camera should trigger exposure after stabilization period

---

## Installation & Flashing

### Requirements

- **PlatformIO** (recommended) or **Arduino IDE**
- **ESP32 Board Support** (ESP32 DevKit compatible)
- **DHT sensor library** (by Adafruit)
- **USB Cable** (data-capable, not charge-only)

### Using PlatformIO (Recommended)

```bash
# Navigate to firmware directory
cd Firmware/LED_Nematostella

# Install dependencies
pio lib install

# Build firmware
pio run

# Upload to ESP32
pio run --target upload

# Monitor serial output
pio device monitor
```

### Using Arduino IDE

1. Install **ESP32 Board Support** via Boards Manager
2. Install **DHT sensor library** by Adafruit via Library Manager
3. Open `Firmware/LED_Nematostella/src/main.cpp`
4. Select board: **ESP32 Dev Module**
5. Select correct COM port
6. Click **Upload**
7. Open **Serial Monitor** (115200 baud) to verify

### Verifying Installation

After flashing, open Serial Monitor (115200 baud). You should see:

```
ESP32 Nematostella Controller - Python Compatible v2.2
Default timing: 400ms stab + 20ms exp = 420ms total
```

**Test Commands:**
```
Send: 0x02 (STATUS)
Expect: 5 bytes (status + temp + humidity)

Send: 0x20 (SELECT_LED_IR)
Expect: 0x30 (IR_SELECTED)

Send: 0x01 (LED_ON)
Expect: 0xAA (ACK)
```

---

## Troubleshooting

### Serial Communication Issues

**Symptom:** No response from ESP32

**Solutions:**
- Verify baud rate is 115200
- Check USB cable is data-capable (not charge-only)
- Install CH340/CP2102 drivers (depending on ESP32 variant)
- Try different USB port
- Check if ESP32 is powered (LED should be on)

---

### LED Not Turning On

**Symptom:** LED commands accepted but LED doesn't illuminate

**Solutions:**
- Verify LED driver power supply is connected
- Check PWM signal with oscilloscope (should see 0-3.3V square wave at GPIO 4 or 15)
- Ensure LED driver PWM input is connected to correct GPIO
- Test LED driver independently
- Check LED polarity
- Verify power settings (try `SET_LED_POWER 0x64` for 100%)

---

### DHT22 Returns 0.0 or NaN

**Symptom:** Temperature/humidity always 0.0 or invalid

**Solutions:**
- Verify 10kΩ pull-up resistor is installed on data line
- Check 3.3V power connection to DHT22
- Ensure data pin connected to GPIO 14 (not GPIO 4!)
- Try different DHT22 sensor (failure rate ~5%)
- Check sensor is DHT22 (not DHT11)
- Allow 2-second warm-up after power-on

---

### Timing Drift

**Symptom:** Captures happen at irregular intervals

**Solutions:**
- This is normal - timing is handled by Python plugin, not firmware
- Firmware executes each command immediately
- Python plugin implements drift-compensated scheduling
- Check Python plugin timing logic if drift is excessive

---

## Version History

### Version 2.2 (2024-11-03) - Current
- Fixed CMD_LED_ON to send 0xAA for Python compatibility
- Fixed CMD_LED_OFF to send 0xAA for Python compatibility
- Standardized all ACK responses to use 0xAA
- Improved serial buffer handling (automatic clearing every 30s)
- Updated default timing: 400ms stabilization + 20ms exposure
- Removed deprecated 7-byte sync response format
- Clarified LED on-time calculation

### Version 2.1
- Added dual LED capture mode (CMD_SYNC_CAPTURE_DUAL)
- Improved sensor filtering with 5-sample moving average
- Added outlier rejection for sensor readings
- Enhanced error handling for invalid commands

### Version 2.0
- Complete rewrite for Python compatibility
- Switched to binary protocol (from ASCII)
- Added independent IR/White LED power control
- Implemented 15-byte sync response format
- Added configurable timing parameters

---

## Python Integration Example

```python
import serial
import struct

class ESP32Controller:
    def __init__(self, port='/dev/ttyUSB0'):
        self.ser = serial.Serial(port, 115200, timeout=2)

    def select_ir_led(self):
        """Select IR LED as active."""
        self.ser.write(b'\x20')
        response = self.ser.read(1)
        return response == b'\x30'

    def set_ir_power(self, power):
        """Set IR LED power (0-100)."""
        self.ser.write(bytes([0x24, power]))
        response = self.ser.read(1)
        return response == b'\xAA'

    def sync_capture(self):
        """Perform synchronized capture."""
        self.ser.write(b'\x0C')
        response = self.ser.read(15)

        if response[0] != 0x1B:
            raise Exception("Invalid sync response")

        # Parse response
        temp = struct.unpack('>H', response[1:3])[0] / 100.0
        humidity = struct.unpack('>H', response[3:5])[0] / 100.0
        duration = struct.unpack('>H', response[5:7])[0]

        return {
            'temperature': temp,
            'humidity': humidity,
            'duration_ms': duration,
            'led_type': response[7],
            'ir_state': response[8],
            'white_state': response[9],
            'ir_power': response[10],
            'white_power': response[11]
        }

# Usage
esp32 = ESP32Controller('/dev/ttyUSB0')
esp32.select_ir_led()
esp32.set_ir_power(75)
data = esp32.sync_capture()
print(f"Temperature: {data['temperature']}°C")
print(f"Humidity: {data['humidity']}%")
```

---

## License

This firmware is part of the Nematostella Timelapse Capture project and is licensed under the MIT License.

---

## Support

For issues or questions:
- GitHub Issues: https://github.com/s1alknau/Nematostella-time-series/issues
- Documentation: See main README.md
- Hardware Setup: See QUICK_START_GUIDE.md
