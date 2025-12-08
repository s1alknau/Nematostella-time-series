"""
Test Multi-Camera Setup

Demonstrates how to use the multi-camera system for parallel recording.

Requirements:
1. camera_system.json configuration file
2. Connected cameras (HIK Robotics GigE)
3. Connected ESP32s via USB

Usage:
    python test_multi_camera.py camera_system.json
"""

import logging
import sys
import time
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)


def create_camera_adapter(camera_config):
    """
    Factory function to create camera adapter

    Args:
        camera_config: CameraConfig instance

    Returns:
        Camera adapter instance
    """
    from src.timeseries_capture.camera_adapters import ImSwitchCameraAdapter

    logger.info(f"Creating camera adapter for {camera_config.name}")

    # For HIK GigE cameras via ImSwitch
    if camera_config.type == "hik_gige":
        # Note: This requires ImSwitch camera manager
        # In real usage, you'd pass the actual camera manager
        adapter = ImSwitchCameraAdapter(
            camera_manager=None,  # Replace with actual camera manager
            camera_name=camera_config.name,
        )
        return adapter

    # For testing without real cameras
    from src.timeseries_capture.camera_adapters import DummyCameraAdapter

    logger.warning(f"Using dummy camera for {camera_config.name}")
    return DummyCameraAdapter(width=1024, height=1224)


def create_esp32_controller(port: str):
    """
    Factory function to create ESP32 controller

    Args:
        port: COM port (e.g., "COM3")

    Returns:
        ESP32 controller instance
    """
    from src.timeseries_capture.ESP32_Controller import ESP32Controller

    logger.info(f"Creating ESP32 controller for {port}")

    try:
        controller = ESP32Controller(port=port)
        return controller
    except Exception as e:
        logger.error(f"Failed to create ESP32 controller: {e}")
        raise


def main():
    """Main test function"""

    if len(sys.argv) < 2:
        print("Usage: python test_multi_camera.py <camera_system.json>")
        print("")
        print("Example:")
        print("  python test_multi_camera.py camera_system_example.json")
        sys.exit(1)

    config_path = Path(sys.argv[1])

    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)

    logger.info("=" * 80)
    logger.info("Multi-Camera System Test")
    logger.info("=" * 80)

    # Load camera system configuration
    from src.timeseries_capture.Config import load_camera_system_config

    logger.info(f"Loading configuration from {config_path}")
    system_config = load_camera_system_config(config_path)

    logger.info(f"System: {system_config.system_name}")
    logger.info(
        f"Cameras: {system_config.num_enabled_cameras}/{system_config.num_cameras} enabled"
    )

    for cam in system_config.enabled_cameras:
        logger.info(
            f"  - {cam.name} ({cam.id}): {cam.ip} / ESP32: {cam.esp32_port}"
        )

    # Create multi-camera controller
    from src.timeseries_capture.Recorder import MultiCameraController

    logger.info("")
    logger.info("Creating MultiCameraController...")

    controller = MultiCameraController(
        system_config=system_config,
        camera_factory=create_camera_adapter,
        esp32_factory=create_esp32_controller,
    )

    # Connect all cameras
    logger.info("")
    logger.info("Connecting all cameras...")

    connect_results = controller.connect_all()

    for cam_id, success in connect_results.items():
        status = "[OK]" if success else "[FAILED]"
        logger.info(f"  {status} {cam_id}")

    if not controller.is_connected:
        logger.error("Not all cameras connected. Aborting test.")
        sys.exit(1)

    # Get status
    logger.info("")
    logger.info("System Status:")
    status = controller.get_all_status()

    for cam_id, cam_status in status.items():
        logger.info(
            f"  {cam_id}: {cam_status['camera_name']} - "
            f"Connected: {cam_status['connected']}, "
            f"Recording: {cam_status['recording']}"
        )

    # Start recordings
    logger.info("")
    logger.info("Starting recordings...")

    from src.timeseries_capture.Recorder import RecordingConfig

    recording_config = RecordingConfig(
        duration_min=1,  # Short test: 1 minute
        interval_sec=5,  # 5 second intervals
        experiment_name="multicam_test",
        output_dir="test_output",
        phase_enabled=False,  # Simple test without phases
        # LED powers (example)
        ir_led_power=50,
        white_led_power=30,
    )

    start_results = controller.start_all_recordings(recording_config)

    for cam_id, success in start_results.items():
        status = "[OK]" if success else "[FAILED]"
        logger.info(f"  {status} {cam_id} started")

    # Monitor progress
    logger.info("")
    logger.info("Monitoring recording progress...")
    logger.info("(Press Ctrl+C to stop early)")

    try:
        while controller.is_any_recording:
            time.sleep(5)

            summary = controller.get_summary_statistics()

            logger.info(
                f"Progress: {summary['num_recording']}/{summary['num_cameras']} recording, "
                f"{summary['average_progress_percent']:.1f}% avg, "
                f"{summary['total_frames_captured']} total frames"
            )

    except KeyboardInterrupt:
        logger.info("")
        logger.info("Interrupted by user. Stopping recordings...")

        stop_results = controller.stop_all_recordings()

        for cam_id, success in stop_results.items():
            status = "[OK]" if success else "[FAILED]"
            logger.info(f"  {status} {cam_id} stopped")

    # Disconnect
    logger.info("")
    logger.info("Disconnecting all cameras...")
    controller.disconnect_all()

    logger.info("")
    logger.info("=" * 80)
    logger.info("Test completed successfully!")
    logger.info("=" * 80)

    # Show output files
    output_dir = Path("test_output")
    if output_dir.exists():
        h5_files = list(output_dir.glob("**/*.h5"))
        logger.info(f"\nRecorded {len(h5_files)} HDF5 files:")
        for f in h5_files:
            size_mb = f.stat().st_size / (1024 * 1024)
            logger.info(f"  - {f.name} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)
