"""
Camera System Configuration

Handles configuration for single and multi-camera setups.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CameraConfig:
    """Configuration for a single camera-ESP32 unit"""

    id: str
    name: str
    type: str  # "hik_gige", "hik_usb", etc.
    ip: Optional[str] = None  # For GigE cameras
    usb_index: Optional[int] = None  # For USB cameras
    esp32_port: str = "COM3"
    enabled: bool = True

    # Optional per-camera settings (future)
    led_ir_power: Optional[int] = None
    led_white_power: Optional[int] = None
    calibration_dark_ir: Optional[int] = None
    calibration_light_ir: Optional[int] = None
    calibration_light_white: Optional[int] = None

    def __post_init__(self):
        """Validate configuration"""
        if self.type == "hik_gige" and not self.ip:
            raise ValueError(f"Camera {self.id}: GigE camera requires IP address")
        if self.type == "hik_usb" and self.usb_index is None:
            raise ValueError(f"Camera {self.id}: USB camera requires usb_index")


@dataclass
class CameraSystemConfig:
    """Configuration for entire multi-camera system"""

    system_name: str
    cameras: List[CameraConfig] = field(default_factory=list)
    default_recording_config: Dict = field(default_factory=dict)

    # System-wide settings
    output_base_dir: Optional[str] = None
    enable_multi_camera: bool = True

    @property
    def enabled_cameras(self) -> List[CameraConfig]:
        """Get list of enabled cameras"""
        return [cam for cam in self.cameras if cam.enabled]

    @property
    def num_cameras(self) -> int:
        """Total number of cameras (enabled + disabled)"""
        return len(self.cameras)

    @property
    def num_enabled_cameras(self) -> int:
        """Number of enabled cameras"""
        return len(self.enabled_cameras)

    def get_camera(self, camera_id: str) -> Optional[CameraConfig]:
        """Get camera config by ID"""
        for cam in self.cameras:
            if cam.id == camera_id:
                return cam
        return None

    def validate(self) -> List[str]:
        """
        Validate configuration

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check camera IDs are unique
        ids = [cam.id for cam in self.cameras]
        if len(ids) != len(set(ids)):
            errors.append("Duplicate camera IDs found")

        # Check ESP32 ports are unique
        ports = [cam.esp32_port for cam in self.enabled_cameras]
        if len(ports) != len(set(ports)):
            errors.append("Duplicate ESP32 ports found")

        # Check IPs are unique (for GigE cameras)
        ips = [cam.ip for cam in self.enabled_cameras if cam.ip]
        if len(ips) != len(set(ips)):
            errors.append("Duplicate camera IP addresses found")

        # Validate each camera
        for cam in self.cameras:
            try:
                cam.__post_init__()
            except ValueError as e:
                errors.append(str(e))

        return errors


def load_camera_system_config(config_path: Path) -> CameraSystemConfig:
    """
    Load camera system configuration from JSON file

    Args:
        config_path: Path to camera_system.json

    Returns:
        CameraSystemConfig instance

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config is invalid
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        data = json.load(f)

    # Parse cameras
    cameras = []
    for cam_data in data.get("cameras", []):
        camera = CameraConfig(
            id=cam_data["id"],
            name=cam_data["name"],
            type=cam_data["type"],
            ip=cam_data.get("ip"),
            usb_index=cam_data.get("usb_index"),
            esp32_port=cam_data["esp32_port"],
            enabled=cam_data.get("enabled", True),
            led_ir_power=cam_data.get("led_ir_power"),
            led_white_power=cam_data.get("led_white_power"),
            calibration_dark_ir=cam_data.get("calibration_dark_ir"),
            calibration_light_ir=cam_data.get("calibration_light_ir"),
            calibration_light_white=cam_data.get("calibration_light_white"),
        )
        cameras.append(camera)

    # Create system config
    system_config = CameraSystemConfig(
        system_name=data.get("system_name", "Multi-Camera System"),
        cameras=cameras,
        default_recording_config=data.get("default_recording_config", {}),
        output_base_dir=data.get("output_base_dir"),
        enable_multi_camera=data.get("enable_multi_camera", True),
    )

    # Validate
    errors = system_config.validate()
    if errors:
        error_msg = "Invalid camera system configuration:\n" + "\n".join(
            f"  - {err}" for err in errors
        )
        raise ValueError(error_msg)

    logger.info(
        f"Loaded camera system config: {system_config.num_enabled_cameras}/{system_config.num_cameras} cameras enabled"
    )

    return system_config


def create_default_config(output_path: Path, num_cameras: int = 6):
    """
    Create a default camera system configuration file

    Args:
        output_path: Where to save the config file
        num_cameras: Number of cameras to configure
    """
    cameras = []
    for i in range(num_cameras):
        camera = {
            "id": f"cam{i+1}",
            "name": f"Camera {i+1} - Position {chr(65+i)}",
            "type": "hik_gige",
            "ip": f"192.168.1.{101+i}",
            "esp32_port": f"COM{3+i}",
            "enabled": True,
        }
        cameras.append(camera)

    config = {
        "system_name": "Nematostella Multi-Camera Setup",
        "cameras": cameras,
        "default_recording_config": {
            "duration_min": 60,
            "interval_sec": 5,
            "phase_enabled": True,
            "light_duration_min": 30,
            "dark_duration_min": 30,
            "start_with_light": True,
            "dual_light_phase": True,
        },
        "output_base_dir": None,  # Use default
        "enable_multi_camera": True,
    }

    with open(output_path, "w") as f:
        json.dump(config, f, indent=2)

    logger.info(f"Created default config at {output_path}")


# ============================================================================
# CLI for creating/validating configs
# ============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python camera_system_config.py create <output_path> [num_cameras]")
        print("  python camera_system_config.py validate <config_path>")
        sys.exit(1)

    command = sys.argv[1]

    if command == "create":
        if len(sys.argv) < 3:
            print("Error: output_path required")
            sys.exit(1)

        output_path = Path(sys.argv[2])
        num_cameras = int(sys.argv[3]) if len(sys.argv) > 3 else 6

        create_default_config(output_path, num_cameras)
        print(f"[OK] Created default config for {num_cameras} cameras at {output_path}")

    elif command == "validate":
        if len(sys.argv) < 3:
            print("Error: config_path required")
            sys.exit(1)

        config_path = Path(sys.argv[2])

        try:
            config = load_camera_system_config(config_path)
            print(f"[OK] Valid configuration: {config.system_name}")
            print(f"   Cameras: {config.num_enabled_cameras}/{config.num_cameras} enabled")
            for cam in config.enabled_cameras:
                if cam.type == "hik_gige":
                    print(f"   - {cam.name}: {cam.ip} (ESP32: {cam.esp32_port})")
                else:
                    print(f"   - {cam.name}: USB{cam.usb_index} (ESP32: {cam.esp32_port})")
        except Exception as e:
            print(f"[ERROR] Invalid configuration: {e}")
            sys.exit(1)

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
