# ESP32 Firmware Quick Start Guide

Fast-track guide to flashing the Nematostella timelapse firmware to your ESP32.

**Firmware Version:** 2.2
**Estimated Time:** 10-15 minutes

---

## What You Need

- ✅ ESP32 Dev Board (ESP32-DevKitC or compatible)
- ✅ USB cable (data-capable, not charge-only)
- ✅ Computer with Windows/Mac/Linux
- ✅ **PlatformIO** (recommended) or **Arduino IDE**

---

## Method 1: PlatformIO (Recommended)

### Why PlatformIO?
- Automated dependency management
- Faster builds
- Better error messages
- Works from command line or VS Code

### Step 1: Install PlatformIO

**Option A: VS Code Extension**
1. Install [Visual Studio Code](https://code.visualstudio.com/)
2. Open VS Code
3. Extensions → Search "PlatformIO IDE"
4. Click Install
5. Restart VS Code

**Option B: Command Line**
```bash
pip install platformio
```

### Step 2: Navigate to Firmware Directory

```bash
cd Firmware/LED_Nematostella
```

### Step 3: Build and Upload

```bash
# Build the firmware
pio run

# Upload to ESP32 (auto-detects port)
pio run --target upload

# Monitor serial output to verify
pio device monitor
```

**Expected Output:**
```
ESP32 Nematostella Controller - Python Compatible v2.2
Default timing: 400ms stab + 20ms exp = 420ms total
```

**Note:** The plugin will override exposure time with your camera settings (typically 5ms).

Press `Ctrl+C` to exit monitor.

**Done!** Your ESP32 is now ready.

---

## Method 2: Arduino IDE

### Step 1: Install Arduino IDE

Download from [arduino.cc/en/software](https://www.arduino.cc/en/software)

### Step 2: Add ESP32 Board Support

1. Open Arduino IDE
2. **File → Preferences**
3. In "Additional Board Manager URLs" add:
   ```
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```
4. Click OK
5. **Tools → Board → Boards Manager**
6. Search: "esp32"
7. Install: "esp32 by Espressif Systems" (version 2.0.0+)

### Step 3: Install DHT Library

1. **Tools → Manage Libraries** (or Sketch → Include Library → Manage Libraries)
2. Search: "DHT sensor library"
3. Install: "DHT sensor library by Adafruit" (v1.4.4+)
4. When prompted, also install: "Adafruit Unified Sensor"

### Step 4: Open Firmware

1. **File → Open**
2. Navigate to: `Firmware/LED_Nematostella/src/main.cpp`
3. Click Open

### Step 5: Configure Board Settings

1. **Tools → Board → ESP32 Arduino → ESP32 Dev Module**
2. **Tools → Port → [Select your ESP32 port]**
   - Windows: COM3, COM4, etc.
   - Mac: /dev/cu.usbserial-*
   - Linux: /dev/ttyUSB0, /dev/ttyACM0

3. **Additional Settings:**
   - Upload Speed: 921600
   - Flash Frequency: 80MHz
   - Flash Mode: QIO
   - Flash Size: 4MB (32Mb)
   - Partition Scheme: Default 4MB with spiffs

### Step 6: Upload Firmware

1. Click **Upload** button (→ arrow icon)
2. Wait for "Done uploading" message
3. Press **Reset button** on ESP32 board

### Step 7: Verify Installation

1. **Tools → Serial Monitor**
2. Set baud rate to: **115200**
3. Press Reset button on ESP32

**You should see:**
```
ESP32 Nematostella Controller - Python Compatible v2.2
Default timing: 400ms stab + 20ms exp = 420ms total
```

**Note:** This default timing is overridden by the Python plugin at recording start (typically uses 5ms exposure based on camera settings).

**If you see this, the firmware is working correctly!**

---

## Hardware Connections

After flashing firmware, connect your hardware:

### Pin Assignments

| Component | ESP32 Pin | Notes |
|-----------|-----------|-------|
| IR LED (PWM) | GPIO 4 | Connect to MOSFET gate (IRLZ34N) |
| White LED (PWM) | GPIO 15 | Connect to MOSFET gate (IRLZ34N) |
| DHT22 Data | GPIO 14 | Direct connection (sensor board has integrated pull-up) |
| DHT22 VCC | 3.3V | ESP32 3.3V pin |
| DHT22 GND | GND | ESP32 GND pin |

### Important Notes

- ⚠️ **GPIO 4 = IR LED, GPIO 15 = White LED, GPIO 14 = DHT22**
- ⚠️ DHT22 sensor board has **integrated pull-up resistor** - no external resistor needed
- ⚠️ IR LEDs are invisible - use IR viewer card to verify operation
- ⚠️ MOSFETs (IRLZ34N) control LED strips via 12V power supply
- ⚠️ **Common ground required** between ESP32 (USB power) and 12V PSU

### Wiring Diagram

```
Power Supplies:          ESP32 Controller         MOSFETs & LEDs
┌──────────┐            ┌─────────┐
│ USB PSU  │  USB       │         │  GPIO 4      IRLZ34N    ┌─────────┐
│  (5V)    ├───────────►│ ESP32   ├─────────────► Gate     │ IR LED  │
└────┬─────┘            │         │              Drain◄────┤ Strip   │
     │                  │ GPIO 15 ├────────┐     Source────► (+)     │
     │                  │         │        │                └────┬────┘
┌────┴─────┐            │ GPIO 14 ◄──┐    │     IRLZ34N         │
│ 12V PSU  │            │         │  │    └────► Gate     ┌─────▼────┐
│  (5A)    │  12V+      │  3.3V   ├──┼──►DHT22  Drain◄────┤ White LED│
└────┬─────┘      │     │         │  │    VCC   Source────► Strip (+)│
     │            │     │  GND    │  │                     └────┬─────┘
     │            │     └────┬────┘  └──►DHT22 Data            │
     │            │          │           DHT22 GND             │
     │            │          │                                 │
     └────────────┴──────────┴─────────────────────────────────┘
                        COMMON GROUND (via WAGO connector)

Note: DHT22 sensor board includes integrated pull-up resistor
```

---

## Testing the Firmware

### Method 1: Using Serial Monitor

1. Open Serial Monitor (115200 baud)
2. Type commands as hex values:

   ```
   Send: 02          (STATUS command)
   Expect: 10 + 4 bytes (temp/humidity data)

   Send: 20          (SELECT IR LED)
   Expect: 30        (IR selected)

   Send: 01          (LED ON)
   Expect: AA        (ACK)

   Send: 00          (LED OFF)
   Expect: AA        (ACK)
   ```

**Note:** Most serial monitors can't send raw hex easily. Use Python method instead.

### Method 2: Using Python

Create a test script `test_esp32.py`:

```python
import serial
import time

# Adjust port to your system
PORT = 'COM3'  # Windows
# PORT = '/dev/ttyUSB0'  # Linux
# PORT = '/dev/cu.usbserial-XXXX'  # Mac

ser = serial.Serial(PORT, 115200, timeout=2)
time.sleep(2)  # Wait for ESP32 to initialize

print("Testing ESP32 Firmware v2.2")
print("-" * 40)

# Test 1: Status
print("Test 1: Get Status")
ser.write(b'\x02')
response = ser.read(5)
if len(response) == 5:
    status = response[0]
    temp = int.from_bytes(response[1:3], 'big') / 100.0
    humidity = int.from_bytes(response[3:5], 'big') / 100.0
    print(f"✅ Status: 0x{status:02X}")
    print(f"   Temperature: {temp:.2f}°C")
    print(f"   Humidity: {humidity:.2f}%")
else:
    print(f"❌ Expected 5 bytes, got {len(response)}")

# Test 2: Select IR LED
print("\nTest 2: Select IR LED")
ser.write(b'\x20')
response = ser.read(1)
if response == b'\x30':
    print("✅ IR LED selected (response: 0x30)")
else:
    print(f"❌ Expected 0x30, got {response.hex()}")

# Test 3: LED ON
print("\nTest 3: Turn LED ON")
ser.write(b'\x01')
response = ser.read(1)
if response == b'\xAA':
    print("✅ LED ON (response: 0xAA)")
    print("   Check if IR LED is illuminated (use IR viewer!)")
else:
    print(f"❌ Expected 0xAA, got {response.hex()}")

time.sleep(1)

# Test 4: LED OFF
print("\nTest 4: Turn LED OFF")
ser.write(b'\x00')
response = ser.read(1)
if response == b'\xAA':
    print("✅ LED OFF (response: 0xAA)")
else:
    print(f"❌ Expected 0xAA, got {response.hex()}")

print("\n" + "=" * 40)
print("Firmware test complete!")
ser.close()
```

Run the test:
```bash
python test_esp32.py
```

**Expected Output:**
```
Testing ESP32 Firmware v2.2
----------------------------------------
Test 1: Get Status
✅ Status: 0x10
   Temperature: 23.50°C
   Humidity: 45.20%

Test 2: Select IR LED
✅ IR LED selected (response: 0x30)

Test 3: Turn LED ON
✅ LED ON (response: 0xAA)
   Check if IR LED is illuminated (use IR viewer!)

Test 4: Turn LED OFF
✅ LED OFF (response: 0xAA)

========================================
Firmware test complete!
```

---

## Troubleshooting

### Problem: Port Not Found

**Windows:**
- Install CH340 or CP2102 USB driver (depending on your ESP32 variant)
- Check Device Manager → Ports (COM & LPT)
- Try different USB port
- Try different USB cable (must be data cable!)

**Mac:**
- Install CH340 driver: [github.com/adrianmihalko/ch340g-ch34g-ch34x-mac-os-x-driver](https://github.com/adrianmihalko/ch340g-ch34g-ch34x-mac-os-x-driver)
- Check: `ls /dev/cu.*`

**Linux:**
- Add user to dialout group: `sudo usermod -a -G dialout $USER`
- Logout and login again
- Check: `ls /dev/ttyUSB*`

### Problem: Upload Failed

**Solutions:**
- Hold **BOOT button** on ESP32 while uploading
- Press **RESET button** after upload
- Lower upload speed to 115200 (Tools → Upload Speed)
- Check USB cable is data-capable
- Try different USB port

### Problem: Compilation Errors

**Missing DHT library:**
```
fatal error: DHT.h: No such file or directory
```
**Solution:** Install "DHT sensor library by Adafruit" via Library Manager

**ESP32 board not found:**
```
Error: Board ... not available
```
**Solution:** Install ESP32 board support (see Step 2)

### Problem: No Serial Output

**Solutions:**
- Check baud rate is 115200
- Press RESET button on ESP32
- Check Serial Monitor is connected to correct port
- Check USB cable supports data (not charge-only)

### Problem: DHT22 Shows 0.0 / NaN

**Solutions:**
- Verify 10kΩ pull-up resistor installed on GPIO 14
- Check DHT22 power (3.3V) connection
- Ensure DHT22 data pin connected to GPIO 14 (**not GPIO 4!**)
- Wait 2 seconds after power-on for sensor warm-up
- Try different DHT22 sensor

---

## Next Steps

After successfully flashing and testing:

1. **Connect Python Plugin:**
   ```python
   from timeseries_capture.ESP32_Controller import ESP32Controller

   esp32 = ESP32Controller()
   if esp32.connect():
       print("✅ ESP32 connected!")
   ```

2. **Use with napari Plugin:**
   - Launch napari
   - Plugins → Nematostella Timelapse Recording
   - ESP32 Connection tab → Connect
   - Should auto-detect and connect

3. **Calibrate LEDs:**
   - See main [README.md](../README.md#calibration-system)
   - LED Calibration tab in napari plugin

4. **Start Recording:**
   - Configure recording parameters
   - Set phase settings (optional)
   - Click Start Recording

---

## Additional Resources

- **Full Firmware Documentation:** [FIRMWARE_DOCUMENTATION.md](FIRMWARE_DOCUMENTATION.md)
- **Main Plugin Documentation:** [../README.md](../README.md)
- **Hardware Setup Guide:** [../README.md#hardware-setup--assembly](../README.md#hardware-setup--assembly)
- **Troubleshooting:** [../README.md#troubleshooting](../README.md#troubleshooting)

---

## Support

If you encounter issues:
- Check [FIRMWARE_DOCUMENTATION.md](FIRMWARE_DOCUMENTATION.md) troubleshooting section
- Open an issue on GitHub: https://github.com/s1alknau/Nematostella-time-series/issues
- Include:
  - Error messages (full text)
  - ESP32 board model
  - Operating system
  - Arduino IDE / PlatformIO version
