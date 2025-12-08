# Multi-Camera Setup Design Document

## Overview

Support for parallel recording from multiple HIK Robotics GigE cameras, each controlled by its own ESP32 microcontroller.

**Target Configuration:**
- 6 HIK Robotics GigE cameras (connected via network switch)
- 6 ESP32 microcontrollers (connected via USB hub)
- Each camera-ESP32 pair operates independently
- Parallel recording with individual configurations (future)

## Architecture

### Current (Single Camera)
```
GUI
 └─ RecordingController
     └─ RecordingManager
         ├─ FrameCaptureService (1 Camera + 1 ESP32)
         └─ DataManager (1 HDF5 file)
```

### New (Multi-Camera)
```
GUI
 └─ MultiCameraController
     ├─ CameraSystemConfig (defines N cameras)
     ├─ CameraRecordingUnit #1
     │   ├─ RecordingManager
     │   ├─ FrameCaptureService (Camera #1 + ESP32 #1)
     │   └─ DataManager (camera1_recording.h5)
     ├─ CameraRecordingUnit #2
     │   └─ ...
     └─ CameraRecordingUnit #N
         └─ ...
```

## Key Components

### 1. CameraSystemConfig
Defines all connected cameras and ESP32s:
```python
{
    "cameras": [
        {
            "id": "cam1",
            "name": "Camera 1 - Position A",
            "ip": "192.168.1.101",
            "esp32_port": "COM3"
        },
        {
            "id": "cam2",
            "name": "Camera 2 - Position B",
            "ip": "192.168.1.102",
            "esp32_port": "COM4"
        },
        # ... up to 6 cameras
    ]
}
```

### 2. CameraRecordingUnit
Encapsulates one complete recording system:
- 1 Camera Adapter
- 1 ESP32 Controller
- 1 Recording Manager
- 1 Data Manager
- Independent state and configuration

### 3. MultiCameraController
Manages all CameraRecordingUnits:
- Start/stop all recordings (broadcast)
- Monitor status of all units
- Handle errors per unit
- Collect statistics from all units

### 4. MultiCameraGUI
Enhanced GUI with:
- Camera selection dropdown
- "Apply to All" option for settings
- Individual status displays
- Grid view for live preview (future)

## Implementation Strategy

### Phase 1: Core Multi-Camera Support (Current PR)

**Files to Create:**
- `src/timeseries_capture/Recorder/camera_recording_unit.py` - Single camera-ESP32 recording unit
- `src/timeseries_capture/Recorder/multi_camera_controller.py` - Controller for multiple units
- `src/timeseries_capture/Config/camera_system_config.py` - Camera system configuration

**Files to Modify:**
- `src/timeseries_capture/main_widget.py` - Add multi-camera GUI elements
- `src/timeseries_capture/recording_controller.py` - Integrate MultiCameraController

**Features:**
- ✅ Define N camera-ESP32 pairs
- ✅ Start/stop all recordings in parallel
- ✅ Separate HDF5 files per camera
- ✅ Basic status monitoring
- ✅ Simple GUI: dropdown to select camera

### Phase 2: Individual Configuration (Future)

**Features:**
- 🔄 Per-camera LED power settings
- 🔄 Per-camera phase configuration
- 🔄 Per-camera interval settings
- 🔄 "Apply to All" or "Individual" mode

### Phase 3: Advanced GUI (Future)

**Features:**
- 🔄 Grid view: 2×3 or 3×2 layout
- 🔄 Live preview for all cameras
- 🔄 Individual calibration per camera
- 🔄 Batch operations

### Phase 4: Synchronization (Future)

**Features:**
- 🔄 Hardware trigger between ESP32s
- 🔄 Frame timestamp alignment
- 🔄 Combined HDF5 output option

## Hardware Requirements

### Network Setup
- **Switch**: Gigabit Ethernet (1000 Mbps) minimum
- **Recommended**: 10 Gigabit Ethernet for 6+ cameras
- **Camera IPs**: Static IPs in same subnet (e.g., 192.168.1.101-106)
- **PC Network Card**: Gigabit minimum, preferably 10G or multiple NICs

### USB Setup
- **USB Hub**: Powered hub with 6+ ports
- **Power**: Minimum 3A (6 × 500mA per ESP32)
- **ESP32 Ports**: COM3-COM8 (or as configured)

### Bandwidth Calculation

**Per Camera:**
- Resolution: 1024×1224 pixels
- Bit depth: 16-bit
- Frame size: 2.5 MB
- Interval: 5 seconds
- Average: 0.5 MB/s per camera

**Total (6 Cameras):**
- Peak: 15 MB/frame (during simultaneous capture)
- Average: 3 MB/s
- Gigabit Ethernet: 125 MB/s → ✅ Sufficient

**Bottlenecks:**
- Disk write: 6 × 0.5 MB/s = 3 MB/s → ✅ OK for SSD
- RAM: 6 × 10 MB buffering = 60 MB → ✅ Minimal
- CPU: 12 threads (6 recording + 6 HDF5) → ✅ OK for 8+ core CPU

## Configuration File Format

### camera_system.json
```json
{
    "system_name": "Nematostella Multi-Well Setup",
    "cameras": [
        {
            "id": "cam1",
            "name": "Well Plate A1-A4",
            "type": "hik_gige",
            "ip": "192.168.1.101",
            "esp32_port": "COM3",
            "enabled": true
        },
        {
            "id": "cam2",
            "name": "Well Plate B1-B4",
            "type": "hik_gige",
            "ip": "192.168.1.102",
            "esp32_port": "COM4",
            "enabled": true
        }
    ],
    "default_recording_config": {
        "duration_min": 60,
        "interval_sec": 5,
        "phase_enabled": true,
        "light_duration_min": 30,
        "dark_duration_min": 30
    }
}
```

## Error Handling

### Per-Camera Errors
If one camera fails:
- ❌ Camera 3 fails → Only Camera 3 stops recording
- ✅ Cameras 1,2,4,5,6 continue recording
- 📊 Error logged to Camera 3's HDF5 metadata
- 🔔 GUI shows red status for Camera 3

### System-Level Errors
- Network failure → All cameras affected
- Disk full → All recordings stop
- USB hub disconnected → All ESP32s affected

## Output Structure

### Separate Files (Phase 1)
```
output_dir/
├── 20241204_160000/
│   ├── camera1_nematostella_timelapse_20241204_160000.h5
│   ├── camera2_nematostella_timelapse_20241204_160000.h5
│   ├── camera3_nematostella_timelapse_20241204_160000.h5
│   ├── camera4_nematostella_timelapse_20241204_160000.h5
│   ├── camera5_nematostella_timelapse_20241204_160000.h5
│   └── camera6_nematostella_timelapse_20241204_160000.h5
```

### Combined File (Future)
```
output_dir/
├── 20241204_160000/
│   └── multicamera_recording_20241204_160000.h5
│       ├── camera1/
│       │   ├── images/
│       │   └── timeseries/
│       ├── camera2/
│       │   ├── images/
│       │   └── timeseries/
│       └── ...
```

## API Design

### MultiCameraController

```python
class MultiCameraController:
    def __init__(self, system_config: CameraSystemConfig):
        """Initialize with system configuration"""

    def connect_all(self) -> Dict[str, bool]:
        """Connect all cameras and ESP32s"""

    def start_all_recordings(self, config: RecordingConfig) -> bool:
        """Start recording on all enabled cameras"""

    def stop_all_recordings(self) -> bool:
        """Stop all recordings"""

    def get_status(self) -> Dict[str, RecordingStatus]:
        """Get status of all recording units"""

    def get_camera_unit(self, camera_id: str) -> CameraRecordingUnit:
        """Get specific camera unit for individual control"""
```

### CameraRecordingUnit

```python
class CameraRecordingUnit:
    def __init__(self, config: CameraConfig):
        """Initialize single camera-ESP32 unit"""

    def connect(self) -> bool:
        """Connect camera and ESP32"""

    def start_recording(self, config: RecordingConfig) -> bool:
        """Start recording"""

    def stop_recording(self) -> bool:
        """Stop recording"""

    def get_status(self) -> RecordingStatus:
        """Get current status"""

    @property
    def is_recording(self) -> bool:
        """Check if currently recording"""
```

## Testing Strategy

### Unit Tests
- Test CameraRecordingUnit with dummy camera
- Test MultiCameraController with 2 dummy units
- Test configuration loading/validation

### Integration Tests
- Test with 2 real cameras + 2 ESP32s
- Test error handling (disconnect camera mid-recording)
- Test parallel recording performance

### Performance Tests
- Test with 6 cameras at different intervals
- Measure CPU/RAM/Disk usage
- Verify no frame drops

## Migration Path

### Backward Compatibility
- ✅ Single-camera mode still works (default)
- ✅ Existing recordings readable
- ✅ GUI switches between single/multi mode

### Migration Steps
1. User updates to multi-camera branch
2. Create `camera_system.json` config file
3. GUI detects config → switches to multi-camera mode
4. If no config → single-camera mode (legacy)

## Future Enhancements

### Hardware Sync
- Master ESP32 sends trigger to 5 slave ESP32s
- All cameras capture within <1ms
- Requires hardware modification (GPIO connections)

### Network Optimization
- Jumbo frames for GigE cameras
- Separate VLANs for camera groups
- Multiple network interfaces

### Advanced Features
- Real-time image processing pipeline
- Automated well detection and cropping
- Machine learning for quality control

## Known Limitations

### Phase 1
- No hardware synchronization between cameras
- Frame timestamps may differ by ~10-50ms
- No combined HDF5 output
- No per-camera individual configurations

### Future Phases
These limitations will be addressed in subsequent releases.

---

**Document Version:** 1.0
**Created:** 2024-12-04
**Branch:** multicam-setup
