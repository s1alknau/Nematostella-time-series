# Nematostella Timelapse Capture Plugin

[![License MIT](https://img.shields.io/pypi/l/nematostella-time-series.svg?color=green)](https://github.com/s1alknau/nematostella-time-series/raw/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/nematostella-time-series.svg?color=green)](https://pypi.org/project/nematostella-time-series)
[![Python Version](https://img.shields.io/pypi/pyversions/nematostella-time-series.svg?color=green)](https://python.org)
[![napari hub](https://img.shields.io/endpoint?url=https://api.napari-hub.org/shields/nematostella-time-series)](https://napari-hub.org/plugins/nematostella-time-series)

A professional napari plugin for synchronized timelapse recording of *Nematostella vectensis* with dual-LED illumination (IR + White) and ESP32-based hardware synchronization.

---

## Recent Updates (v2.1.0 - 2024-12-04)

🎉 **Major improvements to calibration and timing systems!**

- ✅ **Per-Phase LED Calibration**: Automatic intensity matching between dark/light phases (target: ≤5% difference)
- ✅ **IR LED Minimum Constraint**: Enforced 20% minimum in dual mode for optimal darkfield illumination
- ✅ **Camera Exposure Tracking**: Automatic verification that exposure matches between calibration and recording
- ✅ **Timing Optimizations**: 95% reduction in cumulative drift, 40% improvement in interval stability
- ✅ **Bug Fixes**: Fixed phase recording config passing and string field plotting

See [CHANGELOG.md](CHANGELOG.md) for complete details.

---

## Features

- **Hardware-Synchronized LED Control**: Precise synchronization between camera exposure and LED illumination via ESP32 microcontroller
- **Dual-LED Support**: Independent control of IR (850nm) exchangeable LEDs and White (broad-spectrum) LEDs for creating light stimulation and oblique lighting
- **Phase-Based Recording**: Automated light/dark cycles for circadian rhythm studies
- **Drift-Compensated Timing**: Frame timing measured from absolute recording start, preventing cumulative drift
- **Environmental Monitoring**: Real-time temperature and humidity tracking via DHT22 sensor
- **LED Calibration**: Interactive calibration system to normalize LED intensities across channels
- **HDF5 Data Storage**: Efficient chunked storage with comprehensive metadata and timeseries data
- **Real-Time Visualization**: Live frame display with recording statistics

---

## Table of Contents

- [Installation](#installation)
- [Hardware Requirements](#hardware-requirements)
  - [Required Components](#required-components)
  - [Hardware Setup & Assembly](#hardware-setup--assembly)
  - [Device Photos](#device-photos)
  - [Wiring & Connection Details](#wiring--connection-details)
- [Quick Start](#quick-start)
- [Architecture Overview](#architecture-overview)
- [Timing Logic & Drift Compensation](#timing-logic--drift-compensation)
- [LED Synchronization](#led-synchronization)
- [Calibration System](#calibration-system)
- [Data Structure](#data-structure)
- [Usage Examples](#usage-examples)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

---

## Installation

### Standard Installation

```bash
pip install nematostella-time-series
```

### Development Installation

```bash
git clone https://github.com/s1alknau/Nematostella-time-series.git
cd nematostella-time-series
pip install -e .
```

### Dependencies

Core dependencies:
- Python >= 3.9
- napari >= 0.4.18
- numpy
- h5py
- pyserial
- qtpy
- pymmcore-plus (for camera control)

---

## Hardware Requirements

### Required Components

1. **ESP32 Microcontroller**

   **Option A: ESP32-DevKitC (Standard)**
   - Firmware: Custom firmware with LED control and sensor support
   - Firmware version: v2.2 or higher
   - GPIO Pins Used: GPIO 4 (IR LED), GPIO 15 (White LED), GPIO 14 (DHT22)

   **Option B: ESP32-S3-BOX-3 (Advanced)** ⭐ *New!*
   - Development board with integrated 2.4" touchscreen display
   - Requires ESP32-S3-BOX-3-DOCK accessory for GPIO access
   - GPIO Pins Used: GPIO 10 (IR LED), GPIO 11 (White LED), GPIO 12 (DHT22)
   - Optional: Local status display and touch control
   - See [ESP32-S3-BOX-3 Configuration Guide](docs/ESP32-S3-BOX-3_CONFIGURATION.md) for details

2. **LED System**
   - **IR LED**: 850nm wavelength, 12V (e.g., LED Streifen 2538 120 LED/m IR 850nm)
   - **White LED**: Broad-spectrum, 24V (e.g., 24 V COB 320 L/m iNextStation)
   - **MOSFET Drivers**: 2x BOJACK IRLZ34N (30A, 55V, Logic-Level N-Channel MOSFET)
   - **Important**: IR and White LEDs use different voltages (12V vs 24V)

3. **DHT22 Sensor**
   - Temperature range: -40°C to 80°C (±0.5°C accuracy)
   - Humidity range: 0-100% RH (±2-5% accuracy)
   - DHT22 sensor board with integrated pull-up resistor (no external resistor needed)

4. **Power Supplies**
   - **ESP32 Power**: 5V via USB (from computer)
   - **IR LED Power**: 12V DC, 2-5A power supply
   - **White LED Power**: 24V DC, 2-5A power supply
   - **Critical**: Common ground connection required between USB ground and both PSU grounds

5. **Connectors & Wiring**
   - **3x WAGO 221-413** COMPACT Lever Connectors (3-conductor)
   - Wire: 18-22 AWG for signal, 16-18 AWG for power
   - Tool-free connection, reusable

6. **Camera**
   - Hik Robotics MV-CS-013 60GN Near Infrared
   - https://www.hikrobotics.com/en/machinevision/productdetail/?id=7038

---

### Hardware Setup & Assembly

#### Step 1: ESP32 Firmware Installation

1. **Download Firmware**
   - Firmware located in: `Firmware/LED_Nematostella/`
   - Required version: v2.2 or higher
   - See [FIRMWARE_DOCUMENTATION.md](Firmware/FIRMWARE_DOCUMENTATION.md) for details

2. **Flash Firmware to ESP32**
   ```bash
   # Using PlatformIO
   cd Firmware/LED_Nematostella
   pio run --target upload

   # Or using Arduino IDE
   # Open src/main.cpp and upload to ESP32 board
   ```

3. **Verify Firmware** (optional)
   - Open Serial Monitor (115200 baud)
   - You should see: `ESP32 LED Controller v2.2 Ready`
   - Type `STATUS` to verify all systems operational

#### Step 2: LED System Assembly with IRLZ34N MOSFETs

**MOSFET Specifications:**
- Model: BOJACK IRLZ34N (IRLZ34NPBF)
- Type: N-Channel Logic-Level MOSFET
- Maximum Ratings: 30A, 55V
- Gate Threshold: 1-2V (logic-level, works with 3.3V from ESP32)
- Package: TO-220

**IR LED Circuit:**
```
                    ┌─────────────┐
ESP32 GPIO 4 ──────►│ Gate        │
(3.3V PWM)          │  IRLZ34N    │
                    │  MOSFET     │
                    │             │
12V PSU (+) ────────┤ Drain       │
                    │             │
                    │ Source      ├─────► IR LED Strip (+)
                    └─────────────┘
                                        IR LED Strip (-) ──► GND

Note: Add current-limiting resistor if using individual LEDs
```

**White LED Circuit:**
```
                    ┌─────────────┐
ESP32 GPIO 15 ─────►│ Gate        │
(3.3V PWM)          │  IRLZ34N    │
                    │  MOSFET     │
                    │             │
24V PSU (+) ────────┤ Drain       │
                    │             │
                    │ Source      ├─────► White LED Strip (+)
                    └─────────────┘
                                        White LED Strip (-) ──► GND

Note: White LED uses 24V power supply (different from 12V IR LED)
```

**MOSFET Connection Details:**
1. **Gate Pin** → ESP32 GPIO (4 or 15) via 220Ω resistor (optional, for protection)
2. **Drain Pin** → Power Supply (+) [12V for IR, 24V for White]
3. **Source Pin** → Common Ground (WAGO #3)
4. **LED Connections:**
   - IR LED: (+) from 12V PSU via WAGO #1, (-) to Common Ground
   - White LED: (+) from 24V PSU via WAGO #2, (-) to Common Ground

**Important:**
- IRLZ34N is **logic-level** compatible (works with 3.3V gate voltage)
- No additional driver circuit needed between ESP32 and MOSFET
- PWM frequency: 15kHz (set in firmware)
- Can handle high-power LED strips (up to 30A theoretical, typically use 1-3A)

**Safety Notes:**
- ⚠️ IR LEDs are invisible - use IR viewer card to verify operation
- Use heatsink on MOSFET if driving >2A continuous
- Add flyback diode (1N4007) across LED if using inductive loads
- Ensure common ground between ESP32, PSU, and MOSFETs
- Use appropriate gauge wire for current loads

#### Step 3: DHT22 Sensor Connection

```
DHT22 Sensor Board Pinout:
Pin 1 (VCC)  → ESP32 3.3V
Pin 2 (Data) → ESP32 GPIO 14
Pin 3 (GND)  → ESP32 GND
```

**Important Notes:**
- DHT22 sensor board has **integrated pull-up resistor** - no external resistor needed
- Direct 3-wire connection to ESP32
- Use short wires (<30cm) for reliable communication

**Power Supply Note:**
- DHT22 datasheet specifies 3.3-6V operating range (5V optimal)
- **This setup uses 3.3V** which provides excellent logic level compatibility:
  - ✅ ESP32 GPIO operates at 3.3V logic
  - ✅ DHT22 powered at 3.3V
  - ✅ Integrated pull-up at 3.3V
  - ✅ All signal levels perfectly matched
- While 5V can provide slightly more stable readings, 3.3V works reliably and avoids any logic level conversion issues
- Sensor has been tested extensively at 3.3V with stable temperature/humidity readings

#### Step 4: Camera Integration

**Supported Camera Types:**

**HIK Robotics Cameras** (tested and recommended):
- **GigE (Ethernet) cameras**: Network-based cameras with high bandwidth
- **USB cameras**: Direct USB connection for easy setup
- Custom adapter available in `Json+cam_manager/`
- See [example_uc2_ddorf_hik_imager_IR.json](Json+cam_manager/example_uc2_ddorf_hik_imager_IR.json)
- See [camera_adapters.py](src/timeseries_capture/camera_adapters.py) for implementation details

**Camera Positioning:**
- Position camera to view sample chamber
- Ensure LEDs illuminate sample area uniformly
- Use IR-pass filter for IR-only imaging (optional)

#### Step 5: Complete System Wiring with WAGO Connectors

**System Overview:**
```
┌─────────────────────────────────────────────────────────────────────┐
│          COMPLETE SYSTEM WIRING (2 PSUs + USB Power)               │
└─────────────────────────────────────────────────────────────────────┘

Power Sources:
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  USB Cable   │     │   12V PSU    │     │   24V PSU    │
│   (ESP32)    │     │  (IR LED)    │     │ (White LED)  │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       │ USB                │ 12V+               │ 24V+
       │                    │                    │
       ▼                    ▼                    ▼
   ┌────────┐          ┌─────────┐         ┌─────────┐
   │ ESP32  │          │ WAGO #1 │         │ WAGO #2 │
   │        │          │(IR 12V+)│         │(W 24V+) │
   │ GPIO 4 ├──────┐   └────┬────┘         └────┬────┘
   │ GPIO15 ├────┐ │     [1][2][3]           [1][2][3]
   │ GPIO14 ◄─┐  │ │      │  │               │  │
   │  3.3V──┬─┼──┼─┘   12V+│  │           24V+│  │
   │  GND─┬─┼─┼──┘         │  │               │  │
   │  GND─┼─┼─┘            │  │               │  │
   └──┬───┼─┘              │  │               │  │
      │   └──DHT22         │  │               │  │
      │       VCC          │  │               │  │
      │       Data         │  └──►IR LED(+)   │  └──►White LED(+)
      │       GND          │      12V         │      24V
      │                    │                  │
      │           IR MOSFET│         White MOSFET
      │           Gate◄─GPIO4       Gate◄─GPIO15
      │           Drain◄─12V PSU(+) Drain◄─24V PSU(+)
      │           Source─┐          Source─┐
      │                  │                 │
      ▼                  ▼                 ▼
   ┌─────────────────────────────────────────────────────┐
   │           WAGO #3 (Common Ground Hub)               │
   │  [1] 12V PSU GND(-)  [2] 24V PSU GND(-)  [3] ESP32 GND│
   │                                                      │
   │  Additional wires connected:                        │
   │  - IR MOSFET Source                                 │
   │  - White MOSFET Source                              │
   │  - IR LED Cathode (-) 12V                           │
   │  - White LED Cathode (-) 24V                        │
   └─────────────────────────────────────────────────────┘
```

**Key Points:**
- **Power Sources**: USB (ESP32), 12V PSU (IR LED), 24V PSU (White LED)
- DHT22 GND → ESP32 second GND pin (direct, NOT via WAGO #3)
- **WAGO #1**: 12V+ distribution - [1]=12V PSU(+), [2]=IR LED(+)
- **WAGO #2**: 24V+ distribution - [1]=24V PSU(+), [2]=White LED(+)
- **WAGO #3 (Critical)**: Common ground hub connecting all power sources
  - [1] 12V PSU GND (-)
  - [2] 24V PSU GND (-)
  - [3] ESP32 GND pin
  - Plus: Both MOSFET Sources, both LED cathodes (-)
- GPIO 4 → IR MOSFET Gate (direct wire)
- GPIO 15 → White MOSFET Gate (direct wire)

**WAGO Connector Usage:**

**WAGO #1 - 12V IR LED Power Distribution**
```
┌─────────────────────────────────────┐
│   WAGO 221-413 #1                   │
│   (IR LED 12V+ Circuit)             │
├─────────────────────────────────────┤
│ [1] 12V PSU (+)                     │
│ [2] 12V IR LED Strip (+)            │
│ [3] (unused or spare connection)    │
└─────────────────────────────────────┘

12V+ flows: 12V PSU → WAGO #1 [1] → IR LED+ [2]
IR LED Strip (-) → Common Ground (WAGO #3)
```

**WAGO #2 - 24V White LED Power Distribution**
```
┌─────────────────────────────────────┐
│   WAGO 221-413 #2                   │
│   (White LED 24V+ Circuit)          │
├─────────────────────────────────────┤
│ [1] 24V PSU (+)                     │
│ [2] 24V White LED Strip (+)         │
│ [3] (unused or spare connection)    │
└─────────────────────────────────────┘

24V+ flows: 24V PSU → WAGO #2 [1] → White LED+ [2]
White LED Strip (-) → Common Ground (WAGO #3)
```

**WAGO #3 - Common Ground Hub**
```
┌─────────────────────────────────────┐
│   WAGO 221-413 #3                   │
│   (Common Ground)                   │
├─────────────────────────────────────┤
│ [1] 12V PSU GND (-)                 │
│ [2] 24V PSU GND (-)                 │
│ [3] ESP32 GND                       │
│                                     │
│ Connected via additional wires:     │
│ - IR MOSFET Source                  │
│ - White MOSFET Source               │
│ - IR LED Strip (-) 12V              │
│ - White LED Strip (-) 24V           │
└─────────────────────────────────────┘
```
**Critical:** This connector creates the common ground between **all power sources** (12V PSU, 24V PSU, ESP32 USB) and all components. Without this common ground, the MOSFETs cannot switch properly.

**MOSFET Wiring:**

IR IRLZ34N MOSFET:
- Gate  → ESP32 GPIO 4 (direct wire, no WAGO)
- Drain → 12V PSU (+) via WAGO #1
- Source → Common Ground (WAGO #3)

White IRLZ34N MOSFET:
- Gate  → ESP32 GPIO 15 (direct wire, no WAGO)
- Drain → 24V PSU (+) via WAGO #2
- Source → Common Ground (WAGO #3)

**Assembly Steps:**

1. **Mount Components:**
   - ESP32 in accessible location for USB connection
   - 2x IRLZ34N MOSFETs (can use heatsinks if needed)
   - LEDs positioned for optimal sample illumination
   - DHT22 sensor near sample chamber for accurate readings
   - Camera mounted with stable positioning

2. **Connect WAGO #1 (12V IR LED Power):**
   - Port [1]: 12V PSU (+) positive
   - Port [2]: IR LED Strip (+) anode
   - Port [3]: Spare/unused
   - IR MOSFET Drain → 12V PSU (+) directly or via WAGO #1

3. **Connect WAGO #2 (24V White LED Power):**
   - Port [1]: 24V PSU (+) positive
   - Port [2]: White LED Strip (+) anode
   - Port [3]: Spare/unused
   - White MOSFET Drain → 24V PSU (+) directly or via WAGO #2

4. **Connect WAGO #3 (Common Ground Hub):**
   - Port [1]: 12V PSU GND (-)
   - Port [2]: 24V PSU GND (-)
   - Port [3]: ESP32 GND pin
   - Additional wires to WAGO #3 (all grounds go here):
     - IR MOSFET Source pin
     - White MOSFET Source pin
     - IR LED Strip (-) cathode
     - White LED Strip (-) cathode

5. **Connect MOSFETs:**
   - IR MOSFET: Gate → ESP32 GPIO 4, Drain → 12V+, Source → GND (WAGO #3)
   - White MOSFET: Gate → ESP32 GPIO 15, Drain → 24V+, Source → GND (WAGO #3)

5. **Connect DHT22 Sensor:**
   - DHT22 VCC → ESP32 3.3V (direct connection)
   - DHT22 Data → ESP32 GPIO 14 (direct connection)
   - DHT22 GND → ESP32 second GND pin (direct connection, NOT via WAGO)

6. **Connect Power Sources:**
   - ESP32: USB cable to computer
   - 12V PSU: Connect mains power (ensure correct voltage!)
   - 24V PSU: Connect mains power (ensure correct voltage!)
   - **Critical:** Verify common ground (WAGO #1) is connected before powering on

7. **Cable Management:**
   - Keep signal cables (PWM, DHT22) away from power cables
   - Use shielded cables for long runs
   - Secure all connections to prevent accidental disconnection
   - Use cable ties to organize wiring

8. **Initial Testing:**
   ```bash
   # Test ESP32 connection
   python -m timeseries_capture.ESP32_Controller.esp32_connection_diagnostic

   # Verify LED control
   # In napari plugin: LED Control tab → Test IR/White LEDs

   # Check sensor readings
   # In napari plugin: Status tab → View temperature/humidity
   ```

---

### Device Photos

**Add your setup photos here to help others replicate the hardware configuration.**

#### Complete System

![Complete Nematostella Timelapse System](docs/images/system_complete.jpg)
*Full system showing ESP32, LED array, camera, and sample chamber*

#### ESP32 Controller Assembly

![ESP32 with DHT22 and LED connections](docs/images/esp32_assembly.jpg)
*ESP32 DevKit with DHT22 sensor and LED driver connections*

#### LED Illumination Setup

![IR and White LED positioning](docs/images/led_setup.jpg)
*Dual-LED array showing IR (850nm) and White LED positioning around sample chamber*

#### Sample Chamber Detail

![Sample chamber with Nematostella](docs/images/sample_chamber.jpg)
*Sample chamber showing Nematostella positioning and illumination*

#### Wiring Overview

![Complete wiring diagram](docs/images/wiring_overview.jpg)
*Overview of all connections: ESP32, LEDs, sensor, and camera*

**Note:** *Photo placeholders above - replace with actual images of your setup. Recommended image directory: `docs/images/`*

**Photo Guidelines:**
- Use high-resolution images (1920x1080 or higher)
- Include labels or annotations for key components
- Show multiple angles for complex assemblies
- Include close-ups of critical connections (DHT22, LED drivers)
- Consider adding a scale reference (e.g., ruler) in photos

---

### Wiring & Connection Details

#### Complete Pinout Reference

```
╔══════════════════════════════════════════════════════════════╗
║                    ESP32 DevKit Pinout                       ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  3.3V  ─────────────────────┬─────────────┐                 ║
║                             │             │                 ║
║                         DHT22 VCC    10kΩ Pull-up           ║
║                                            │                 ║
║  GPIO 14 ───────────────────┴──────────────┤                ║
║                                            │                 ║
║                                       DHT22 Data             ║
║                                                              ║
║  GPIO 4  ─────────────────── IRLZ34N Gate (IR MOSFET)       ║
║                                      │                       ║
║                                      └──→ IR LED Strip      ║
║                                                              ║
║  GPIO 15 ─────────────────── IRLZ34N Gate (White MOSFET)    ║
║                                      │                       ║
║                                      └──→ White LED Strip   ║
║                                                              ║
║  GND ────────────────────────┬───────┬─────────┬────────    ║
║                              │       │         │            ║
║                          DHT22    IR LED   White LED        ║
║                           GND      GND       GND            ║
║                                                              ║
║  USB ────────────────────── Computer (Serial 115200 baud)   ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
```

#### Power Requirements

| Component | Voltage | Current | Notes |
|-----------|---------|---------|-------|
| ESP32 | 5V USB | ~500mA | Powered via USB from computer |
| DHT22 | 3.3V | 1-2mA | Powered from ESP32 3.3V pin (datasheet: 3.3-6V range, 5V optimal) |
| IRLZ34N MOSFETs (2x) | 3.3V (gate) | <1mA each | Logic-level, driven by ESP32 GPIO |
| IR LED Strip | 12V | 1-3A | Via IRLZ34N MOSFET, dedicated 12V PSU |
| White LED Strip | 24V | 1-3A | Via IRLZ34N MOSFET, dedicated 24V PSU |

**Recommended Power Supplies:**
- **12V PSU**: 2-5A for IR LED (regulated output)
- **24V PSU**: 2-5A for White LED (regulated output)
- Both PSUs separate from computer/ESP32 power to avoid noise
- **Critical**: Common ground connection between both PSUs and ESP32 via WAGO #3

**Connectors:**
- WAGO 221-413 COMPACT Lever Connectors (3-conductor)
- Used for safe wire connections (ESP32-MOSFET-LED-PSU)
- Tool-free connection, reusable
- Rated for 32A, 4mm² wire

#### Signal Specifications

**PWM Signals (GPIO 4, 15):**
- **GPIO 4**: IR LED MOSFET Gate
- **GPIO 15**: White LED MOSFET Gate
- Logic Level: 3.3V
- Frequency: 15 kHz (set in firmware)
- Duty Cycle: 0-100% (controlled by plugin)
- Rise/Fall Time: <1µs

**DHT22 Communication (GPIO 14):**
- Protocol: Single-wire digital (proprietary)
- Pull-up: 10kΩ to 3.3V (required)
- Sampling Rate: ~0.5 Hz (one reading per 2 seconds max)
- Data Format: 40-bit (16-bit humidity, 16-bit temp, 8-bit checksum)

**Serial Communication:**
- Protocol: UART over USB
- Baud Rate: 115200
- Data Bits: 8
- Parity: None
- Stop Bits: 1
- Flow Control: None

#### Troubleshooting Hardware Issues

**ESP32 Not Detected:**
- Check USB cable (must be data cable, not charge-only)
- Install CH340/CP2102 USB drivers (depending on ESP32 variant)
- Try different USB port
- Run diagnostic: `python -m timeseries_capture.ESP32_Controller.esp32_connection_diagnostic`

**LEDs Not Responding:**
- Verify LED driver power supply connected
- Check PWM signal with oscilloscope (should see 0-3.3V square wave)
- Test LED drivers independently
- Verify GPIO pin assignments match firmware

**DHT22 Returns 0.0 Values:**
- Check 10kΩ pull-up resistor is installed (or use DHT22 board with integrated pull-up)
- Verify 3.3V power to sensor
- Ensure data pin connected to **GPIO 14** (not GPIO 4!)
- Try different DHT22 sensor (failure rate ~5%)

**LED Intensities Don't Match:**
- Run LED calibration (see [Calibration System](#calibration-system))
- Check LED aging (IR LEDs degrade faster)
- Verify LED driver current settings
- Ensure uniform illumination of sample

---

## Quick Start

### 1. Launch napari with Plugin

```bash
napari
```

In napari:
1. Navigate to `Plugins > Nematostella Timelapse Recording`
2. The plugin opens with 5 main panels

### 2. Connect ESP32

1. Click **ESP32 Connection** tab
2. Ensure ESP32 is connected via USB
3. Click **Connect** (auto-detects port)
4. Verify connection status shows green "✅ Connected"

### 3. Configure Recording

**Basic Settings:**
- **Duration**: 120 minutes
- **Interval**: 5 seconds
- **Experiment Name**: "nematostella_test_01"
- **Output Directory**: Select folder

**Phase Settings** (optional):
- Enable **Phase Recording**
- Light Duration: 60 min
- Dark Duration: 60 min
- First Phase: Light

### 4. Calibrate LEDs (Recommended)

1. Click **LED Calibration** tab
2. Select **Dual Calibration** (for dual-LED recordings)
3. Set Target Intensity: 200
4. Click **Start Calibration**
5. Wait for calibration to complete (~30 seconds)

### 5. Start Recording

1. Click **▶ Start Recording** in Recording Control panel
2. Monitor progress in real-time
3. Recording automatically stops when complete
4. HDF5 file is saved and closed for external access

---

## Architecture Overview

### Component Hierarchy

```
┌─────────────────────────────────────────────────────────┐
│                   Main Widget (GUI)                     │
├─────────────────────────────────────────────────────────┤
│  ┌───────────────┐  ┌────────────────┐  ┌────────────┐ │
│  │ Recording     │  │ ESP32 Control  │  │ Calibration│ │
│  │ Panel         │  │ Panel          │  │ Panel      │ │
│  └───────┬───────┘  └───────┬────────┘  └──────┬─────┘ │
│          │                  │                   │       │
└──────────┼──────────────────┼───────────────────┼───────┘
           │                  │                   │
           ▼                  ▼                   ▼
    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
    │ Recording   │    │ ESP32 GUI   │    │ Calibration │
    │ Controller  │◄───┤ Controller  │◄───┤ Service     │
    └──────┬──────┘    └──────┬──────┘    └─────────────┘
           │                  │
           ▼                  ▼
    ┌─────────────┐    ┌─────────────┐
    │ Recording   │    │    ESP32    │
    │ Manager     │◄───┤ Controller  │
    └──────┬──────┘    └──────┬──────┘
           │                  │
           ▼                  ▼
    ┌─────────────┐    ┌─────────────┐
    │   Frame     │    │    ESP32    │
    │  Capture    │◄───┤    Comm     │
    └──────┬──────┘    └─────────────┘
           │
           ▼
    ┌─────────────┐
    │    Data     │
    │  Manager    │
    │   (HDF5)    │
    └─────────────┘
```

### Key Components

**1. Recording Manager** ([recording_manager.py](src/timeseries_capture/Recorder/recording_manager.py))
- Orchestrates entire recording process
- Manages phase transitions
- Coordinates frame capture with LED control

**2. Frame Capture** ([frame_capture.py](src/timeseries_capture/Recorder/frame_capture.py))
- Synchronizes camera with ESP32 LED control
- Implements sync pulse protocol
- Collects environmental sensor data

**3. ESP32 Controller** ([esp32_controller.py](src/timeseries_capture/ESP32_Controller/esp32_controller.py))
- Hardware abstraction layer for ESP32
- LED power control
- Sensor data acquisition

**4. Recording State** ([recording_state.py](src/timeseries_capture/Recorder/recording_state.py))
- Thread-safe state management
- **Drift-compensated timing calculations**
- Phase information tracking

**5. Data Manager** ([data_manager_hdf5.py](src/timeseries_capture/Datamanager/data_manager_hdf5.py))
- HDF5 file creation and management
- Chunked timeseries writing
- Metadata organization

---

## Timing Logic & Drift Compensation

### The Drift Problem

Traditional timelapse systems measure time between frames:
```python
# ❌ BAD: Cumulative drift
next_capture_time = last_frame_time + interval
```

This causes **cumulative drift** where small timing errors accumulate over time.

### Our Solution: Absolute Time Measurement

We measure all frame times from the **absolute recording start**:

```python
# ✅ GOOD: No drift accumulation
next_capture_time = recording_start + (frame_number * interval)
```

### Implementation Details

**Recording State** ([recording_state.py](src/timeseries_capture/Recorder/recording_state.py:264-295))

```python
def get_time_until_next_frame(self) -> float:
    """
    Calculate time until next frame with drift compensation.

    Frame 0: t = 0s (immediately after start)
    Frame 1: t = interval
    Frame N: t = N × interval

    This ensures timing drift never accumulates!
    """
    elapsed = self.get_elapsed_time()

    # Expected time for NEXT frame (measured from START)
    expected_time_for_next_frame = self.current_frame * self.config.interval_sec

    # Time remaining until next frame
    time_until_next = expected_time_for_next_frame - elapsed

    return max(0.0, time_until_next)
```

### Timing Fields in HDF5

Each frame records:
- `recording_elapsed_sec`: Actual elapsed time since recording start
- `actual_intervals`: Time since previous frame
- `expected_intervals`: Target interval (constant)
- `cumulative_drift_sec`: Accumulated timing error (should stay near 0)

**Analysis Example:**

```python
import h5py

with h5py.File('recording.h5', 'r') as f:
    drift = f['timeseries/cumulative_drift_sec'][:]

    print(f"Max drift: {drift.max():.3f}s")
    print(f"Final drift: {drift[-1]:.3f}s")

    # Good recording: |drift| < 1 second after 2 hours
```

### Phase Timing

Phases are calculated to ensure **symmetric frame distribution**:

```python
# Example: 2-minute recording, 5s interval
total_frames = 120 / 5 = 24 frames  # No +1!

# Frames at: t = 0, 5, 10, ..., 115s (NOT at t=120s)

# With 1-minute phases:
# LIGHT (0-60s):  Frames 0-11  = 12 frames
# DARK  (60-120s): Frames 12-23 = 12 frames
# → Perfect symmetry!
```

---

## LED Synchronization

### Overview

The plugin uses **hardware-synchronized LED control** to ensure precise timing between LED illumination and camera exposure. The ESP32 microcontroller manages LED power and timing, while the Python plugin coordinates frame capture.

### Timing Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    COMPLETE FRAME CYCLE                         │
└─────────────────────────────────────────────────────────────────┘

Python Plugin                ESP32 Firmware              Camera
─────────────                ──────────────              ──────

    │                             │                         │
    │ 1. SET_TIMING               │                         │
    ├────────────────────────────>│                         │
    │    (400ms stab, 5ms exp)    │                         │
    │                             │                         │
    │ 2. SYNC_CAPTURE (0x0C)      │                         │
    ├────────────────────────────>│                         │
    │                             │ LED ON                  │
    │                             ├─────────►               │
    │                             │ (GPIO 4 or 15)          │
    │                             │                         │
    │                             │ [400ms stabilization]   │
    │                             │ ░░░░░░░░░░░░░░░░░░░░░  │
    │                             │                         │
    │ 3. Camera Trigger           │                         │
    ├─────────────────────────────┼────────────────────────>│
    │                             │                         │ Exposure
    │                             │                         │ [5ms]
    │                             │                         │ ████
    │                             │                         │
    │                             │ LED OFF                 │
    │                             ├─────────►               │
    │                             │                         │
    │                             │ Read DHT22              │
    │                             │ ──────►                 │
    │                             │                         │
    │ 4. Response (15 bytes)      │                         │
    │<────────────────────────────┤                         │
    │   (temp, humidity, timing)  │                         │
    │                             │                         │
    │ 5. Snap Frame               │                         │
    ├─────────────────────────────┼────────────────────────>│
    │                             │                         │
    │ 6. Frame Data               │                         │
    │<────────────────────────────┼─────────────────────────┤
    │                             │                         │
    │ 7. Save to HDF5             │                         │
    │ (with metadata)             │                         │
    │                             │                         │
    ▼                             ▼                         ▼

Total Duration: ~405ms (400ms stab + 5ms exposure)
```

### Detailed Timing Breakdown

```
Frame Capture Timeline (Single Frame)
═══════════════════════════════════════════════════════════════

Time (ms)    Event                          Component
─────────    ─────────────────────────────  ──────────────────
    0        Python: Send SYNC_CAPTURE      Plugin
    0        ESP32: Receive command         ESP32
    0        ESP32: LED ON (GPIO 4/15)      ESP32 → LED Driver
             ┌────────────────────────────────────────┐
             │   LED STABILIZATION PERIOD             │
             │   (400ms - LED reaches stable output)  │
             │   ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │
             └────────────────────────────────────────┘
  400        ESP32: LED stabilized          ESP32
  400        Camera: Exposure starts        Camera
             ┌────────────────┐
             │   EXPOSURE     │
             │   (5ms)        │
             │   ████████     │
             └────────────────┘
  405        Camera: Exposure complete      Camera
  405        ESP32: LED OFF                 ESP32
  405        ESP32: Read DHT22              ESP32 → DHT22
  410        ESP32: Send response (15B)     ESP32 → Python
  410        Python: Receive response       Plugin
  410        Python: Snap frame             Plugin → Camera
  415        Python: Receive frame data     Camera → Plugin
  415        Python: Save to HDF5           Plugin → Disk
  420        Frame cycle complete           ✓

Total: ~420ms (405ms sync + 10ms capture + 5ms save)
```

### Phase-Based Timing (Light/Dark Cycles)

```
Phase Recording Timeline (60s Light + 60s Dark @ 5s interval)
═══════════════════════════════════════════════════════════════════

Phase    Time Range    Frames    LED State    Mean Intensity
─────    ──────────    ───────   ─────────    ──────────────
LIGHT    0-60s         12        WHITE ON     ~240
                                 ┌──────┐
                                 │██████│ 5s intervals
                                 └──────┘

DARK     60-120s       12        IR ON        ~195
                                 ┌──────┐
                                 │░░░░░░│ 5s intervals
                                 └──────┘

Transition at t=60s:
    59.5s  ─┐ WHITE LED ON
    59.9s   │ Frame capture
    60.0s  ─┴ WHITE LED OFF
           ─┐ Phase transition
    60.0s   │ ESP32: Select IR LED (0x20)
    60.0s  ─┴ IR LED selected
    60.5s  ─┐ IR LED ON
    60.9s   │ Frame capture
    61.0s  ─┴ IR LED OFF
```

### Drift Compensation Mechanism

The plugin uses **absolute time tracking** to prevent cumulative timing drift:

```
Standard Interval Scheduling (WRONG - causes drift):
═══════════════════════════════════════════════════

Iteration 1: sleep(5.0) → actual: 5.42s (overhead: 0.42s)
Iteration 2: sleep(5.0) → actual: 5.41s (overhead: 0.41s)
Iteration 3: sleep(5.0) → actual: 5.43s (overhead: 0.43s)
...
After 100 frames: drift = 42s! ❌


Drift-Compensated Scheduling (CORRECT):
═══════════════════════════════════════════════════

recording_start_time = time.time()
target_interval = 5.0

Frame 1:
  target_time = start + (1 × 5.0) = 5.0s
  actual_time = 5.42s
  drift = +0.42s
  next_sleep = 5.0 - 0.42 = 4.58s ✓

Frame 2:
  target_time = start + (2 × 5.0) = 10.0s
  actual_time = 10.41s (5.42 + 4.99)
  drift = +0.41s  (accumulated from frame 1)
  next_sleep = 5.0 - 0.41 = 4.59s ✓

Frame 100:
  target_time = start + (100 × 5.0) = 500.0s
  actual_time = 500.2s
  drift = +0.2s (NOT 42s!) ✓

Result: Drift stays < 1s over entire recording ✓
```

Implementation in [recording_manager.py](src/timeseries_capture/Recorder/recording_manager.py:366-385):

```python
recording_start_time = time.time()
target_interval_sec = 5.0

for frame_index in range(total_frames):
    # Calculate when this frame SHOULD be captured
    target_capture_time = recording_start_time + (frame_index * target_interval_sec)

    # Calculate how long to sleep
    now = time.time()
    sleep_duration = target_capture_time - now

    if sleep_duration > 0:
        time.sleep(sleep_duration)

    # Capture frame (takes ~420ms)
    frame_data = self.capture_frame()

    # Calculate actual timing metrics
    actual_time = time.time()
    elapsed = actual_time - recording_start_time
    expected = frame_index * target_interval_sec
    cumulative_drift = elapsed - expected  # Saved to HDF5!
```

### Sync Pulse Implementation

**Frame Capture** ([frame_capture.py](src/timeseries_capture/Recorder/frame_capture.py:287-344))

```python
def capture_frame_with_led_sync(self, led_type: str, dual: bool = False):
    """
    1. Send sync pulse BEGIN command to ESP32
    2. ESP32 turns LED on and starts stabilization timer
    3. Wait for stabilization (1000ms)
    4. Capture camera frame
    5. Send sync pulse COMPLETE command
    6. ESP32 turns LED off
    """
    # Step 1: Begin sync pulse
    pulse_start = self.esp32.begin_sync_pulse(dual=dual)

    # Step 2 & 3: ESP32 handles LED ON + stabilization
    sync_result = self.esp32.wait_sync_complete(timeout=5.0)

    if not sync_result['success']:
        raise TimeoutError("LED sync timeout")

    # Step 4: Capture frame (LED is now stable)
    frame = self.camera_adapter.snap_image()

    return frame, sync_result
```

### ESP32 Communication Protocol

Commands sent via serial (115200 baud):

| Command | Description | Response |
|---------|-------------|----------|
| `PULSE_BEGIN\n` | Start sync pulse | `PULSE_BEGIN_OK\n` |
| `PULSE_BEGIN_DUAL\n` | Start dual-LED pulse | `PULSE_BEGIN_OK\n` |
| `PULSE_COMPLETE\n` | End sync pulse | `PULSE_COMPLETE_OK\n` |
| `SENSOR\n` | Read DHT22 sensor | `SENSOR T=22.5 H=45.2\n` |
| `POWER_IR 75\n` | Set IR LED to 75% | `POWER_IR_OK\n` |
| `POWER_WHITE 50\n` | Set White LED to 50% | `POWER_WHITE_OK\n` |

### Dual-LED Mode

For dual-LED recordings, both LEDs turn on simultaneously:

```python
# Both LEDs on during exposure
pulse_start = esp32.begin_sync_pulse(dual=True)
```

---

## Calibration System

### Purpose

LED calibration ensures **consistent intensity** across:
- Different LED types (IR vs White)
- Different recording sessions
- Different hardware setups

### Calibration Types

**1. IR-Only Calibration**
- Adjusts IR LED power to reach target intensity (200)
- Used for: **IR-only recordings** OR **phase recordings with IR-only dark phase**

**2. White-Only Calibration**
- Adjusts White LED power to reach target intensity (200)
- Used for: **White-only recordings** OR **phase recordings with White-only light phase**

**3. Dual LED Calibration** ⚠️
- Calibrates **both LEDs simultaneously** to reach target intensity (200) when both are ON together
- Turns on both IR and White LEDs, then adjusts their powers proportionally
- Used for: **Continuous dual LED recordings** OR **phase recordings with dual LED light phase**

### CRITICAL: Calibration Workflow for Phase Recordings

Choose the correct calibration method based on your recording phases:

| Recording Configuration | Calibration Method | Why |
|------------------------|-------------------|-----|
| **Continuous IR only** | `calibrate_ir()` | Single LED calibration |
| **Continuous White only** | `calibrate_white()` | Single LED calibration |
| **Continuous Dual LED** | `calibrate_dual()` | Both LEDs together |
| **Phases: IR + White (separate)** | `calibrate_ir()` + `calibrate_white()` | Calibrate each LED individually |
| **Phases: IR + Dual LED** | `calibrate_ir()` + `calibrate_dual()` | Calibrate IR alone, then both together |
| **Phases: White + Dual LED** | `calibrate_white()` + `calibrate_dual()` | Calibrate White alone, then both together |

**Common Mistake:**
- ❌ Using `calibrate_dual()` for phase recording with separate IR/White phases
- ✅ Use `calibrate_ir()` and `calibrate_white()` separately instead

### Calibration Algorithm

Binary search algorithm finds optimal LED power:

```python
def calibrate_led(target_intensity: float, led_type: str):
    """
    Binary search to find LED power that achieves target intensity.

    Algorithm:
    1. Set initial power bounds: [0, 100]
    2. While not converged:
       a. Set LED power to midpoint
       b. Capture test frame
       c. Measure mean intensity
       d. Adjust search bounds based on result
    3. Return optimal power

    Convergence: |measured - target| < tolerance (5%)
    Max iterations: 10
    """
    power_min, power_max = 0, 100

    for iteration in range(max_iterations):
        power = (power_min + power_max) / 2

        set_led_power(power, led_type)
        frame = capture_frame()
        intensity = measure_intensity(frame)

        error = (intensity - target_intensity) / target_intensity * 100

        if abs(error) < tolerance_percent:
            return power  # Converged!

        if intensity < target_intensity:
            power_min = power  # Need more power
        else:
            power_max = power  # Need less power

    return power  # Best effort after max iterations
```

### ROI-Based Measurement

Calibration uses center ROI (75% × 75%) to avoid edge artifacts:

```python
# Avoid edge vignetting
h, w = frame.shape
margin_h = int(h * 0.125)  # 12.5% margin
margin_w = int(w * 0.125)

roi = frame[margin_h:-margin_h, margin_w:-margin_w]
intensity = np.mean(roi)
```

### Calibration Workflow

1. **Setup**
   - Set target intensity (e.g., 200)
   - Select calibration type
   - Set measurement region (ROI vs full frame)

2. **Calibration**
   - Algorithm runs automatically
   - Progress shown in GUI
   - Typical duration: 20-30 seconds

3. **Result**
   - Optimal LED powers saved
   - Results displayed: IR=X%, White=Y%
   - Powers automatically applied to recordings

---

## Data Structure

### HDF5 File Organization

```
recording.h5
│
├── [File Attributes]            # Recording metadata (stored as HDF5 attributes)
│   ├── created                  # Unix timestamp
│   ├── created_human            # Human-readable timestamp
│   ├── experiment_name          # Name of experiment
│   ├── file_version             # File format version
│   ├── software                 # Software name
│   ├── telemetry_mode           # MINIMAL/STANDARD/COMPREHENSIVE
│   ├── duration_min             # Total duration
│   ├── interval_sec             # Frame interval
│   ├── phase_enabled            # Boolean
│   ├── ir_led_power             # IR LED power %
│   ├── white_led_power          # White LED power %
│   └── ...                      # Additional recording parameters
│
├── images/                      # Image stack group
│   └── frames                   # (N, H, W) dataset
│       ├── dtype: uint16
│       ├── shape: (frames, height, width)
│       └── chunks: (1, H, W)
│
└── timeseries/                  # Timeseries data group
    ├── frame_index              # Frame numbers [0, 1, 2, ...]
    ├── recording_elapsed_sec    # Time since start
    ├── actual_intervals         # Actual frame intervals
    ├── expected_intervals       # Target interval (constant)
    ├── cumulative_drift_sec     # ⭐ Accumulated timing drift
    ├── temperature_celsius      # °C
    ├── humidity_percent         # % RH
    ├── led_type_str            # "ir", "white", "dual"
    ├── led_power               # LED power %
    ├── phase_str               # "light", "dark", "continuous"
    ├── cycle_number            # Phase cycle number
    ├── frame_mean_intensity    # Mean pixel value
    ├── sync_success            # LED sync successful (bool)
    ├── phase_transition        # Phase change indicator (bool)
    └── capture_method          # "sync", "direct", etc.
```

**Note**: Metadata is stored as HDF5 **file-level attributes**, not as a separate group. This is more efficient and follows HDF5 best practices.

### Telemetry Modes

Three modes balance data granularity vs file size:

**MINIMAL** (default)
- Essential fields only
- Smallest file size
- Suitable for long recordings

**STANDARD**
- Adds quality indicators
- Timing drift tracking
- Recommended for most users

**COMPREHENSIVE**
- Full debugging information
- Operation timing details
- Largest file size

### Reading Data

**Python (h5py):**
```python
import h5py

with h5py.File('recording.h5', 'r') as f:
    # Load frame stack
    frames = f['frames/frames'][:]  # (N, H, W) array

    # Load timeseries
    time = f['timeseries/recording_elapsed_sec'][:]
    intensity = f['timeseries/frame_mean_intensity'][:]
    temperature = f['timeseries/temperature_celsius'][:]
    drift = f['timeseries/cumulative_drift_sec'][:]

    # Plot timing drift
    import matplotlib.pyplot as plt
    plt.plot(time, drift)
    plt.xlabel('Recording Time (s)')
    plt.ylabel('Cumulative Drift (s)')
    plt.show()
```

**Using Included Plotter:**
```bash
python hdf5_timeseries_plotter_v2.py
# Opens file dialog, then interactive field selection
```

---

## Usage Examples

### Example 1: Simple Continuous Recording

```python
# Settings:
# - Duration: 60 min
# - Interval: 10 sec
# - LED: IR only at 100%
# - No phases

# Result: 360 frames captured every 10 seconds
# Total frames = 60 × 60 / 10 = 360
```

### Example 2: Phase Recording (Circadian Rhythm)

```python
# Settings:
# - Duration: 240 min (4 hours)
# - Interval: 5 sec
# - Phase enabled
# - Light: 120 min (IR LED)
# - Dark: 120 min (White LED)

# Timeline:
# 0-120 min:   LIGHT phase (IR LED)   → 1440 frames
# 120-240 min: DARK phase (White LED) → 1440 frames
# Total: 2880 frames with perfect phase symmetry
```

### Example 3: Dual-LED Recording

```python
# Settings:
# - Duration: 30 min
# - Interval: 3 sec
# - LED: Dual (IR + White simultaneously)
# - Calibrated: IR=60%, White=45%

# Both LEDs on for every frame
# Use for multi-modal imaging
```

### Example 4: Temperature Monitoring

```python
# Load recording and check temperature stability
import h5py
import matplotlib.pyplot as plt

with h5py.File('recording.h5', 'r') as f:
    time = f['timeseries/recording_elapsed_sec'][:] / 60  # Convert to minutes
    temp = f['timeseries/temperature_celsius'][:]

    plt.figure(figsize=(10, 4))
    plt.plot(time, temp)
    plt.xlabel('Time (min)')
    plt.ylabel('Temperature (°C)')
    plt.title(f'Temperature: {temp.mean():.1f} ± {temp.std():.1f}°C')
    plt.grid(True, alpha=0.3)
    plt.show()
```

---

## Troubleshooting

### ESP32 Connection Issues

**Problem**: "Failed to connect to ESP32"

**Solutions**:
1. Check USB cable (must be data cable, not charge-only)
2. Close Arduino IDE or other serial monitors
3. Press ESP32 RESET button
4. On Linux: Add user to `dialout` group
   ```bash
   sudo usermod -a -G dialout $USER
   # Log out and back in
   ```
5. Manually select COM port instead of auto-detect

### LED Synchronization Failures

**Problem**: "LED sync timeout" during recording

**Solutions**:
1. Check LED connections to ESP32
2. Verify ESP32 firmware version (v2.2+)
3. Reduce LED power if overheating occurs
4. Check `sync_success` field in HDF5 to identify failed frames

### Timing Drift Issues

**Problem**: Large cumulative drift (>5 seconds)

**Solutions**:
1. Check computer performance (CPU usage)
2. Reduce frame rate (increase interval)
3. Check camera exposure time
4. Monitor `cumulative_drift_sec` field in recordings
5. Good drift: < 1 second over 2 hours

### Calibration Problems

**Problem**: Calibration fails to converge

**Solutions**:
1. Check if camera is receiving light
2. Verify LED connections
3. Adjust target intensity (try 150-250 range)
4. Use full frame instead of ROI for dark samples
5. Check for lens cap / obstruction

### HDF5 File Access

**Problem**: "Cannot open HDF5 file (file is locked)"

**Solutions**:
1. Stop recording first (file closes automatically)
2. Ensure plugin closed properly
3. Check if file is open in another program
4. Restart napari if persistent

---

## Performance Considerations

### Recommended Settings

**For Long Recordings (>6 hours):**
- Use MINIMAL telemetry mode
- Increase interval (≥5 seconds)
- Monitor disk space

**For High-Quality Capture:**
- Use STANDARD or COMPREHENSIVE mode
- Reduce interval (1-3 seconds)
- Ensure good cooling for LEDs

### System Requirements

**Minimum:**
- CPU: Dual-core 2.0 GHz
- RAM: 4 GB
- Disk: SSD recommended (50 MB/min for 2048×2048 frames)

**Recommended:**
- CPU: Quad-core 3.0 GHz+
- RAM: 8 GB+
- Disk: NVMe SSD (for intensive recordings)

---

## Contributing

Contributions are welcome! Areas for improvement:

1. **Hardware Support**
   - Additional LED controllers
   - More camera models
   - Environmental sensors beyond DHT22

2. **Features**
   - Real-time image processing
   - Multi-region calibration
   - Advanced phase patterns

3. **Documentation**
   - Additional usage examples
   - Video tutorials
   - Firmware documentation

### Development Setup

```bash
# Clone repository
git clone https://github.com/s1alknau/Nematostella-time-series.git
cd nematostella-time-series

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Run linting
pre-commit run --all-files
```

---

## License

Distributed under the terms of the [MIT](http://opensource.org/licenses/MIT) license.

---

## Citation

If you use this plugin in your research, please cite:

```bibtex
@software{nematostella_timelapse,
  title = {Nematostella Timelapse Capture Plugin},
  author = {[Your Name]},
  year = {2025},
  url = {https://github.com/s1alknau/Nematostella-time-series}
}
```

---

## Contact

- **Issues**: [GitHub Issues](https://github.com/s1alknau/Nematostella-time-series/issues)
- **Discussions**: [GitHub Discussions](https://github.com/s1alknau/Nematostella-time-series/discussions)
- **Email**: [your.email@domain.com]

---

## Acknowledgments

- napari team for the excellent imaging platform
- HIK Robotics for camera support and SDK
- ESP32 community for microcontroller support
- Open-source hardware and software communities

---

**Built with ❤️ for *Nematostella vectensis* research**
