## Multi-Camera Setup Usage Guide

Quick start guide for using the multi-camera parallel recording system.

## Quick Start

### 1. Create Configuration File

```bash
python src/timeseries_capture/Config/camera_system_config.py create camera_system.json 6
```

This creates a template for 6 cameras with default settings:
- IPs: 192.168.1.101-106
- COM ports: COM3-COM8

### 2. Edit Configuration

Edit `camera_system.json` to match your hardware setup:

```json
{
  "system_name": "My Multi-Camera Setup",
  "cameras": [
    {
      "id": "cam1",
      "name": "Camera 1 - Well Plate A",
      "type": "hik_gige",
      "ip": "192.168.1.101",
      "esp32_port": "COM3",
      "enabled": true
    },
    {
      "id": "cam2",
      "name": "Camera 2 - Well Plate B",
      "type": "hik_gige",
      "ip": "192.168.1.102",
      "esp32_port": "COM4",
      "enabled": true
    }
    // ... more cameras
  ],
  "default_recording_config": {
    "duration_min": 120,
    "interval_sec": 5,
    "phase_enabled": true,
    "light_duration_min": 30,
    "dark_duration_min": 30
  }
}
```

### 3. Validate Configuration

```bash
python src/timeseries_capture/Config/camera_system_config.py validate camera_system.json
```

Expected output:
```
[OK] Valid configuration: My Multi-Camera Setup
   Cameras: 6/6 enabled
   - Camera 1 - Well Plate A: 192.168.1.101 (ESP32: COM3)
   - Camera 2 - Well Plate B: 192.168.1.102 (ESP32: COM4)
   ...
```

### 4. Test Multi-Camera System

```bash
python test_multi_camera.py camera_system.json
```

This will:
1. Load configuration
2. Connect all cameras and ESP32s
3. Start short test recording (1 minute)
4. Monitor progress
5. Disconnect and show results

## Hardware Setup

### Network Configuration

**Cameras:**
- Connect all HIK GigE cameras to a network switch
- Assign static IPs: 192.168.1.101, 192.168.1.102, ..., 192.168.1.106
- Use Gigabit Ethernet switch (minimum)
- 10 Gigabit recommended for 6+ cameras

**PC Network:**
- Configure PC network adapter to same subnet (e.g., 192.168.1.100)
- Ensure no firewall blocking

### USB Configuration

**ESP32s:**
- Connect all 6 ESP32s to powered USB hub
- Hub must provide at least 3A total (6 × 500mA)
- Note COM ports assigned to each ESP32

**Find COM Ports (Windows):**
```
Device Manager → Ports (COM & LPT)
```

**Find COM Ports (Linux):**
```bash
ls /dev/ttyUSB*
```

## Programming Interface

### Basic Usage

```python
from pathlib import Path
from src.timeseries_capture.Config import load_camera_system_config
from src.timeseries_capture.Recorder import MultiCameraController, RecordingConfig

# Load configuration
config = load_camera_system_config(Path("camera_system.json"))

# Create controller
controller = MultiCameraController(
    system_config=config,
    camera_factory=create_camera_adapter,  # Your factory function
    esp32_factory=create_esp32_controller,  # Your factory function
)

# Connect all cameras
results = controller.connect_all()

# Start recordings
recording_config = RecordingConfig(
    duration_min=60,
    interval_sec=5,
    experiment_name="my_experiment",
    output_dir="recordings",
)

controller.start_all_recordings(recording_config)

# Wait for completion
controller.wait_for_completion()

# Disconnect
controller.disconnect_all()
```

### Individual Camera Control

```python
# Get specific camera unit
unit = controller.get_unit("cam1")

# Check status
print(f"Camera 1 recording: {unit.is_recording}")

# Stop only this camera
unit.stop_recording()

# Get statistics
stats = unit.get_statistics()
print(f"Frames captured: {stats['captured_frames']}")
```

### Monitor All Cameras

```python
# Get status of all cameras
status = controller.get_all_status()

for cam_id, cam_status in status.items():
    print(f"{cam_id}: {cam_status['status']}")
    if cam_status['recording']:
        stats = cam_status['statistics']
        print(f"  Progress: {stats['progress_percent']:.1f}%")
        print(f"  Frames: {stats['captured_frames']}/{stats['total_frames']}")

# Get summary statistics
summary = controller.get_summary_statistics()
print(f"Recording: {summary['num_recording']}/{summary['num_cameras']} cameras")
print(f"Average progress: {summary['average_progress_percent']:.1f}%")
print(f"Total frames: {summary['total_frames_captured']}")
```

## Output Files

Each camera creates its own HDF5 file:

```
recordings/
└── 20241204_160000/
    ├── cam1_nematostella_timelapse_20241204_160000.h5
    ├── cam2_nematostella_timelapse_20241204_160000.h5
    ├── cam3_nematostella_timelapse_20241204_160000.h5
    ├── cam4_nematostella_timelapse_20241204_160000.h5
    ├── cam5_nematostella_timelapse_20241204_160000.h5
    └── cam6_nematostella_timelapse_20241204_160000.h5
```

## GUI Integration (Coming in Phase 3)

Future GUI will include:
- Camera selection dropdown
- "Apply to All" option for settings
- Grid view showing all camera live feeds
- Individual status indicators per camera
- Batch calibration

## Troubleshooting

### Camera Not Found

```
[ERROR] [cam1] Camera not available
```

**Solutions:**
- Check camera IP address
- Verify network connection
- Ping camera: `ping 192.168.1.101`
- Check HIK SDK installation

### ESP32 Not Connected

```
[ERROR] [cam1] ESP32 not connected
```

**Solutions:**
- Check COM port number
- Verify USB connection
- Check ESP32 firmware loaded
- Try different USB port

### Insufficient Bandwidth

```
[WARNING] Frame capture timeout
```

**Solutions:**
- Reduce number of active cameras
- Increase frame interval
- Upgrade to 10 Gigabit Ethernet
- Use multiple network interfaces

### Recording Not Starting

```
[ERROR] Cannot start recordings: Not all units connected
```

**Solutions:**
- Run `controller.connect_all()` first
- Check connection results
- Fix any failed connections before starting

## Performance Tips

### Optimal Settings for 6 Cameras

**Frame Interval:**
- Minimum: 5 seconds (safe for Gigabit Ethernet)
- Recommended: 10 seconds (more headroom)
- For faster: Use 10 Gigabit Ethernet or reduce camera count

**Resolution:**
- Default: 1024×1224 works well
- Higher resolution: Reduce frame rate or camera count

**Storage:**
- Use SSD for recordings (not HDD)
- Ensure 100+ GB free space for long recordings
- Monitor disk usage during recording

### Network Optimization

**Gigabit Ethernet:**
- Max cameras at 5s interval: 6-8 cameras
- Max cameras at 10s interval: 10-12 cameras

**10 Gigabit Ethernet:**
- Max cameras at 1s interval: 10+ cameras
- Max cameras at 5s interval: 20+ cameras

## Advanced Configuration

### Per-Camera LED Powers (Future)

```json
{
  "cameras": [
    {
      "id": "cam1",
      "name": "Camera 1",
      "ip": "192.168.1.101",
      "esp32_port": "COM3",
      "led_ir_power": 50,
      "led_white_power": 30,
      "calibration_dark_ir": 45,
      "calibration_light_ir": 25,
      "calibration_light_white": 15
    }
  ]
}
```

### Disable Specific Cameras

Set `"enabled": false` to skip a camera:

```json
{
  "id": "cam3",
  "name": "Camera 3 (Maintenance)",
  "enabled": false
}
```

## See Also

- [MULTI_CAMERA_DESIGN.md](MULTI_CAMERA_DESIGN.md) - Complete architecture documentation
- [README.md](README.md) - Main project documentation
- [test_multi_camera.py](test_multi_camera.py) - Example test script
