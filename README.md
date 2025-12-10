# Nematostella Timelapse Capture Plugin

[![License MIT](https://img.shields.io/pypi/l/nematostella-time-series.svg?color=green)](https://github.com/s1alknau/nematostella-time-series/raw/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/nematostella-time-series.svg?color=green)](https://pypi.org/project/nematostella-time-series)
[![Python Version](https://img.shields.io/pypi/pyversions/nematostella-time-series.svg?color=green)](https://python.org)
[![napari hub](https://img.shields.io/endpoint?url=https://api.napari-hub.org/shields/nematostella-time-series)](https://napari-hub.org/plugins/nematostella-time-series)

A professional napari plugin for synchronized timelapse recording of *Nematostella vectensis* with dual-LED illumination (IR + White) and ESP32-based hardware synchronization.

---

## Features

- **Hardware-Synchronized LED Control**: Precise synchronization between camera exposure and LED illumination via ESP32 microcontroller
- **Dual-LED Support**: Independent control of IR (850nm) and White (broad-spectrum) LEDs for multi-modal imaging
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

1. **ESP32 Microcontroller** (e.g., ESP32-DevKitC)
   - Firmware: Custom firmware with LED control and sensor support
   - Firmware version: v2.2 or higher

2. **LED System**
   - **IR LED**: 850nm wavelength (e.g., TSAL6400)
   - **White LED**: Broad-spectrum (e.g., high-CRI 5000K)
   - LED drivers with PWM control (0-100%)

3. **DHT22 Sensor**
   - Temperature range: -40°C to 80°C (±0.5°C accuracy)
   - Humidity range: 0-100% RH (±2-5% accuracy)

4. **Camera**
   - Compatible with Micro-Manager device adapters
   - Recommended: Cameras with hardware triggering support

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

3. **Verify Firmware**
   - Open Serial Monitor (115200 baud)
   - You should see: `ESP32 LED Controller v2.2 Ready`
   - Type `STATUS` to verify all systems operational

#### Step 2: LED System Assembly

**IR LED Circuit:**
```
ESP32 GPIO 4 → LED Driver (PWM Input) → IR LED (850nm) → GND
                     ↑
                  Power Supply (12V recommended)
```

**White LED Circuit:**
```
ESP32 GPIO 15 → LED Driver (PWM Input) → White LED → GND
                      ↑
                   Power Supply (12V recommended)
```

**Recommended LED Drivers:**
- PWM-compatible constant current drivers
- Input: 5V PWM signal from ESP32
- Output: Adjustable current (typically 350-700mA for high-power LEDs)

**Safety Notes:**
- ⚠️ IR LEDs are invisible - use IR viewer card to verify operation
- Use appropriate current limiting to prevent LED damage
- Ensure proper heat sinking for high-power LEDs

#### Step 3: DHT22 Sensor Connection

```
DHT22 Sensor Pinout:
Pin 1 (VCC)  → ESP32 3.3V
Pin 2 (Data) → ESP32 GPIO 14 (+ 10kΩ pull-up resistor to 3.3V)
Pin 3 (NC)   → Not connected
Pin 4 (GND)  → ESP32 GND
```

**Pull-up Resistor:**
- Required: 10kΩ resistor between Data pin and VCC
- Ensures reliable sensor communication

#### Step 4: Camera Integration

**Supported Camera Types:**
1. **Micro-Manager Compatible Cameras** (recommended)
   - See [camera_adapters.py](src/timeseries_capture/camera_adapters.py)
   - Examples: Hamamatsu, Andor, FLIR, Basler

2. **HIK Vision Cameras**
   - Custom adapter available in `Json+cam_manager/`
   - See [example_uc2_ddorf_hik_imager_IR.json](Json+cam_manager/example_uc2_ddorf_hik_imager_IR.json)

**Camera Positioning:**
- Position camera to view sample chamber
- Ensure LEDs illuminate sample area uniformly
- Use IR-pass filter for IR-only imaging (optional)

#### Step 5: Complete System Assembly

1. **Mount Components:**
   - ESP32 in accessible location for USB connection
   - LEDs positioned for optimal sample illumination
   - DHT22 sensor near sample chamber for accurate readings
   - Camera mounted with stable positioning

2. **Connect Power:**
   - ESP32: USB power (5V, typically from computer)
   - LED drivers: External 12V power supply
   - Camera: Per manufacturer specifications

3. **Cable Management:**
   - Keep signal cables (PWM, DHT22) away from power cables
   - Use shielded cables for long runs
   - Secure all connections to prevent accidental disconnection

4. **Initial Testing:**
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

#### Power Requirements

| Component | Voltage | Current | Notes |
|-----------|---------|---------|-------|
| ESP32 | 5V USB | ~500mA | Powered via USB from computer |
| DHT22 | 3.3V | 1-2mA | Powered from ESP32 3.3V pin |
| IR LED | 12V | 350-700mA | Requires external power supply |
| White LED | 12V | 350-700mA | Requires external power supply |
| **Total** | - | **~1.5A** | External 12V PSU for LEDs |

**Recommended Power Supply:**
- 12V DC, 2A minimum
- Regulated output
- Separate from computer/ESP32 power to avoid noise

#### Signal Specifications

**PWM Signals (GPIO 25, 26):**
- Logic Level: 3.3V
- Frequency: 1 kHz (configurable in firmware)
- Duty Cycle: 0-100% (controlled by plugin)
- Rise/Fall Time: <1µs

**DHT22 Communication:**
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
- Check 10kΩ pull-up resistor is installed
- Verify 3.3V power to sensor
- Ensure data pin connected to GPIO 4
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
- Adjusts IR LED power to reach target intensity
- Used for IR-only recordings

**2. White-Only Calibration**
- Adjusts White LED power to reach target intensity
- Used for White-only recordings

**3. Dual Calibration** ⚠️
- Calibrates IR and White LEDs separately
- **Note**: When both LEDs are used together, intensities add up
- **Recommendation**: Use separate IR/White calibrations for phase recordings

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
- Micro-Manager project for device control
- ESP32 community for microcontroller support

---

**Built with ❤️ for *Nematostella vectensis* research**
