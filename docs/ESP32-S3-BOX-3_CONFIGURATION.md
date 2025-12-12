# ESP32-S3-BOX-3 Configuration Guide

This document describes the hardware configuration for using the Espressif ESP32-S3-BOX-3 development board with the nematostella time-series imaging system.

## Hardware Overview

The **ESP32-S3-BOX-3** is an AIoT development platform featuring:
- ESP32-S3-WROOM-1 module (Wi-Fi + Bluetooth 5 LE)
- 16 MB Flash, 16 MB PSRAM
- 2.4" 320x240 SPI touchscreen display
- Integrated sensors (microphones, gyroscope, accelerometer)
- USB Type-C connectivity

The **ESP32-S3-BOX-3-DOCK** accessory provides:
- Two Pmod™ compatible headers with 16 programmable GPIOs
- USB Type-A host port
- Additional USB Type-C power input

## GPIO Pinout

### Pmod Header Configuration

The ESP32-S3-BOX-3-DOCK exposes two Pmod headers with the following pinout:

#### Left Pmod Header (PIN 1)
```
Row 1: G10  | G14  | G11  | G43/U0TXD | GND | 3V3
Row 2: G13  | G9   | G12  | G44/U0RXD | GND | 3V3
```

#### Right Pmod Header (PIN 1)
```
Row 1: G21  | G19/USB- | G38  | G41  | GND | 3V3
Row 2: G42  | G20/USB+ | G39  | G40  | GND | 3V3
```

### Available GPIO Pins

Total of **16 programmable GPIOs** available:
- G9, G10, G11, G12, G13, G14
- G19, G20, G21
- G38, G39, G40, G41, G42, G43, G44

**Note:** G19/G20 are shared with USB, and G43/G44 are shared with UART. Avoid using these unless you don't need USB host functionality or serial debugging.

### Internal Peripheral Usage (DO NOT USE)

The following GPIOs are **reserved** by internal peripherals on the ESP32-S3-BOX-3 main unit:

**Display Controller:**
- GPIO4 (DC), GPIO5 (CS), GPIO6 (SDA), GPIO7 (SCK)
- GPIO48 (RST), GPIO47 (CTRL)

**Audio System:**
- GPIO2 (I²S_MCLK), GPIO17 (I²S_SCLK), GPIO45 (I²S_LRCK)
- GPIO15 (codec data), GPIO46 (PA control)

**I²C Bus (Sensors/Codec):**
- GPIO18 (I²C_SCL), GPIO8 (I²C_SDA)

**Other:**
- GPIO1 (mute status)

## Pin Assignment for LED Control & DHT22

### Recommended GPIO Pin Mapping

For compatibility with the nematostella imaging system, we need 3 GPIO pins:

| Function | ESP32 (Original) | ESP32-S3-BOX-3 (New) | Notes |
|----------|------------------|----------------------|-------|
| IR LED Control | GPIO 4 | **GPIO 10** | PWM output for IR MOSFET gate |
| White LED Control | GPIO 15 | **GPIO 11** | PWM output for White MOSFET gate |
| DHT22 Data | GPIO 14 | **GPIO 12** | Digital I/O with pull-up |

**Rationale:**
- **GPIO 10, 11, 12** are sequential, easy to remember, and safe to use
- All support PWM (LEDC peripheral on ESP32-S3)
- GPIO 12 supports digital I/O with pull-up for DHT22
- None conflict with internal peripherals

### Alternative Pin Options

If GPIO 10/11/12 are unavailable, use these alternatives:

**Option 2:**
- IR LED: GPIO 38
- White LED: GPIO 39
- DHT22: GPIO 40

**Option 3:**
- IR LED: GPIO 13
- White LED: GPIO 14
- DHT22: GPIO 9

## Wiring Diagram

### MOSFET Connection (Updated for ESP32-S3-BOX-3)

**IR LED Circuit:**
```
                    ┌─────────────┐
ESP32-S3 GPIO 10 ──►│ Gate        │
(3.3V PWM)          │  IRLZ34N    │
                    │  MOSFET     │
                    │             │
12V PSU (+) ────────┤ Drain       │
                    │             │
                    │ Source      ├─────► IR LED Strip (+)
                    └─────────────┘
                                        IR LED Strip (-) ──► GND
```

**White LED Circuit:**
```
                    ┌─────────────┐
ESP32-S3 GPIO 11 ──►│ Gate        │
(3.3V PWM)          │  IRLZ34N    │
                    │  MOSFET     │
                    │             │
24V PSU (+) ────────┤ Drain       │
                    │             │
                    │ Source      ├─────► White LED Strip (+)
                    └─────────────┘
                                        White LED Strip (-) ──► GND
```

### DHT22 Sensor Connection

```
DHT22 Sensor Board:
Pin 1 (VCC)  → ESP32-S3-BOX-3 DOCK 3V3 (Pmod header)
Pin 2 (Data) → ESP32-S3-BOX-3 GPIO 12
Pin 3 (GND)  → ESP32-S3-BOX-3 GND (Pmod header)
```

**Important Notes:**
- Use 3V3 and GND from the **Pmod headers**, not from internal ESP32-S3-BOX-3 pins
- DHT22 sensor board should have **integrated pull-up resistor**
- Keep wires short (<30cm) for reliable communication

### Complete System Wiring

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   USB-C      │     │   12V PSU    │     │   24V PSU    │
│ (ESP32-S3    │     │  (IR LED)    │     │ (White LED)  │
│   BOX-3)     │     │              │     │              │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       │ USB-C              │ 12V+               │ 24V+
       │                    │                    │
       ▼                    ▼                    ▼
   ┌────────────┐      ┌─────────┐         ┌─────────┐
   │ ESP32-S3-  │      │ WAGO #1 │         │ WAGO #2 │
   │ BOX-3-DOCK │      │(IR 12V+)│         │(W 24V+) │
   │            │      └────┬────┘         └────┬────┘
   │ GPIO 10────┼──────┐    │                   │
   │ GPIO 11────┼────┐ │    │                   │
   │ GPIO 12◄───┼─┐  │ │    │                   │
   │  3.3V──┬───┼─┼──┼─┘    │                   │
   │  GND─┬─┼───┼─┼──┘      │                   │
   │  GND─┼─┼───┼─┘         │                   │
   └──┬───┼─┼───┘           │                   │
      │   │ └──DHT22        │                   │
      │   │     VCC         │                   │
      │   │     Data        │                   │
      │   │     GND         └──►IR LED(+)      └──►White LED(+)
      │   │                      12V                24V
      │   │
      │   │            IR MOSFET         White MOSFET
      │   │            Gate◄─GPIO10      Gate◄─GPIO11
      │   │            Drain◄─12V PSU(+) Drain◄─24V PSU(+)
      │   │            Source─┐          Source─┐
      │   │                   │                 │
      ▼   ▼                   ▼                 ▼
   ┌──────────────────────────────────────────────────────┐
   │           WAGO #3 (Common Ground Hub)                │
   │  [1] 12V PSU GND(-)  [2] 24V PSU GND(-)  [3] ESP32-S3 GND│
   │                                                       │
   │  Additional wires connected:                         │
   │  - IR MOSFET Source                                  │
   │  - White MOSFET Source                               │
   │  - IR LED Cathode (-) 12V                            │
   │  - White LED Cathode (-) 24V                         │
   └──────────────────────────────────────────────────────┘
```

**Key Points:**
- **Power Sources**: USB-C (ESP32-S3-BOX-3), 12V PSU (IR LED), 24V PSU (White LED)
- DHT22 powered from **Pmod header 3V3**, not internal ESP32-S3-BOX-3
- **WAGO #1**: 12V+ distribution - [1]=12V PSU(+), [2]=IR LED(+)
- **WAGO #2**: 24V+ distribution - [1]=24V PSU(+), [2]=White LED(+)
- **WAGO #3**: Common ground hub for all power sources
- GPIO 10 → IR MOSFET Gate (direct wire from Pmod header)
- GPIO 11 → White MOSFET Gate (direct wire from Pmod header)

## Firmware Configuration

### Required Changes in ESP32 Firmware

The ESP32 firmware must be updated to use the new GPIO pin assignments:

**File: `ESP32_firmware/src/config.h` (or equivalent)**

```cpp
// Original ESP32 pin assignments
// #define IR_LED_PIN 4
// #define WHITE_LED_PIN 15
// #define DHT22_PIN 14

// ESP32-S3-BOX-3 pin assignments
#define IR_LED_PIN 10      // GPIO 10 via Pmod header
#define WHITE_LED_PIN 11   // GPIO 11 via Pmod header
#define DHT22_PIN 12       // GPIO 12 via Pmod header
```

**PWM Configuration:**
```cpp
// PWM settings (unchanged from original)
#define PWM_FREQUENCY 15000  // 15 kHz
#define PWM_RESOLUTION 8     // 8-bit (0-255)
#define PWM_CHANNEL_IR 0
#define PWM_CHANNEL_WHITE 1
```

**DHT22 Configuration:**
```cpp
// DHT22 sensor (unchanged from original)
#define DHTTYPE DHT22
DHT dht(DHT22_PIN, DHTTYPE);
```

### Firmware Upload

**Using Arduino IDE or PlatformIO:**

1. **Select Board:** ESP32-S3-Box (or ESP32S3 Dev Module)
2. **Configure Partition Scheme:** Default 4MB with spiffs
3. **USB CDC on Boot:** Enabled (for Serial over USB)
4. **Upload Mode:** UART0 (via USB-C)

**Upload Process:**
1. Connect ESP32-S3-BOX-3 to computer via USB-C cable
2. Hold **BOOT** button while pressing **RESET** button (if needed)
3. Upload firmware from Arduino IDE or PlatformIO
4. Monitor serial output at 115200 baud

## Signal Specifications

**PWM Signals (GPIO 10, 11):**
- **GPIO 10**: IR LED MOSFET Gate
- **GPIO 11**: White LED MOSFET Gate
- Logic Level: 3.3V
- Frequency: 15 kHz (set in firmware)
- Duty Cycle: 0-100% (controlled by plugin)
- Rise/Fall Time: <1µs

**DHT22 Communication (GPIO 12):**
- Protocol: Single-wire digital (proprietary)
- Pull-up: 10kΩ to 3.3V (integrated on DHT22 board)
- Sampling Rate: ~0.5 Hz (one reading per 2 seconds max)
- Data Format: 40-bit (16-bit humidity, 16-bit temp, 8-bit checksum)

**Serial Communication:**
- Protocol: UART over USB-C
- Baud Rate: 115200
- Data Format: 8N1 (8 data bits, no parity, 1 stop bit)

## Display Capabilities (Optional Future Enhancement)

The ESP32-S3-BOX-3 includes a 2.4" touchscreen display that could be used for:

### Potential Features:
1. **Local Status Display**
   - Current LED power levels
   - Temperature and humidity readings
   - Recording status (idle/recording)
   - Connection status (USB/network)

2. **Touch Control Interface**
   - Manual LED power adjustment
   - Test LED on/off
   - View sensor readings
   - Emergency stop button

3. **Data Visualization**
   - Real-time temperature/humidity graphs
   - LED duty cycle indicators
   - Recording progress bar

**Note:** Display functionality is **optional** and not required for basic operation. The system works identically to the standard ESP32 setup without using the display.

## Migration Checklist

- [ ] Obtain ESP32-S3-BOX-3 and ESP32-S3-BOX-3-DOCK
- [ ] Update firmware pin definitions (GPIO 10, 11, 12)
- [ ] Test PWM output on GPIO 10 and 11 with oscilloscope
- [ ] Verify DHT22 communication on GPIO 12
- [ ] Connect MOSFETs to Pmod header GPIOs
- [ ] Wire power distribution (WAGO connectors)
- [ ] Test LED control and sensor readings
- [ ] Validate full system integration
- [ ] (Optional) Implement local display features

## Comparison: ESP32 vs ESP32-S3-BOX-3

| Feature | ESP32 DevKit | ESP32-S3-BOX-3 |
|---------|--------------|----------------|
| Microcontroller | ESP32 | ESP32-S3 |
| Flash | 4 MB | 16 MB |
| PSRAM | 0 MB (usually) | 16 MB |
| Display | None | 2.4" 320x240 touchscreen |
| GPIO Access | Direct pins | Via Pmod headers (DOCK) |
| Pin Mapping | GPIO 4, 15, 14 | GPIO 10, 11, 12 |
| USB | Micro-USB (UART) | USB-C (native USB) |
| Enclosure | Open dev board | Enclosed with stand |
| Additional Features | None | Sensors, speaker, microphones |

## Troubleshooting

**LEDs not responding:**
- Verify GPIO 10/11 are correctly wired to MOSFET gates
- Check PWM signal with oscilloscope (0-3.3V square wave at 15kHz)
- Ensure firmware is compiled for ESP32-S3 target

**DHT22 returns 0.0 values:**
- Verify 3.3V and GND from **Pmod header** (not internal ESP32-S3-BOX-3)
- Check GPIO 12 connection
- Ensure DHT22 board has integrated pull-up resistor

**Cannot upload firmware:**
- Select correct board: ESP32-S3-Box or ESP32S3 Dev Module
- Enable "USB CDC on Boot" in board settings
- Try holding BOOT button while clicking Upload

**Display interferes with operation:**
- Display uses GPIO 4-7, 47-48 internally - do not use these pins
- If display shows garbage, it won't affect LED/sensor operation
- Display can be safely ignored if not using it

## References

- [ESP32-S3-BOX-3 Official Page](https://www.espressif.com/en/dev-board/esp32-s3-box-3-en)
- [ESP32-S3-BOX GitHub Repository](https://github.com/espressif/esp-box)
- [ESP32-S3 Datasheet](https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf)
- [ESP-IDF GPIO Documentation](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/gpio.html)

---

**Last Updated:** 2025-12-12
