"""
ESP32 Controller - High-Level API

Integriert alle ESP32-Komponenten:
- ESP32Communication (Low-level Serial)
- ESP32Commands (Protocol)
- ESP32State (State Management)

Bietet einfache High-Level API für:
- LED Control (IR, White, Dual)
- Sync Pulse Management
- Timing Configuration
- Status Queries
"""

import logging
import time
from typing import Optional

from .esp32_commands import (
    CameraTypes,
    CommandBuilder,
    LEDStatus,
    LEDTypes,
    ResponseParser,
    Responses,
    TimingConfig,
)
from .esp32_communication import ESP32Communication
from .esp32_state import ESP32State

logger = logging.getLogger(__name__)


class ESP32Controller:
    """
    High-Level ESP32 Controller.

    Vereinfacht die Verwendung des ESP32 durch eine saubere API.
    """

    def __init__(
        self, port: Optional[str] = None, baudrate: int = 115200, auto_connect: bool = False
    ):
        """
        Args:
            port: Serial port (None = auto-detect)
            baudrate: Serial baudrate
            auto_connect: Automatically connect on init
        """
        # Components
        self.comm = ESP32Communication(port=port, baudrate=baudrate)
        self.state = ESP32State()

        # Auto-connect
        if auto_connect:
            self.connect()

        logger.info("ESP32Controller initialized")

    # ========================================================================
    # CONNECTION MANAGEMENT
    # ========================================================================

    def connect(self, port: Optional[str] = None) -> bool:
        """
        Connect to ESP32.

        Args:
            port: Optional port override

        Returns:
            True if connected successfully
        """
        success = self.comm.connect(port)

        if success:
            # Initialize with default timing
            self.set_timing(1000, 10)

            # Set camera type to HIK GigE
            self.set_camera_type(CameraTypes.HIK_GIGE)

            # Query initial LED status
            try:
                self.get_led_status()
            except:
                pass

            logger.info("ESP32 connected and initialized")

        return success

    def disconnect(self):
        """Disconnect from ESP32"""
        # Turn off all LEDs before disconnect
        try:
            self.led_off()
        except:
            pass

        self.comm.disconnect()
        logger.info("ESP32 disconnected")

    def is_connected(self, force_check: bool = False) -> bool:
        """
        Check if connected.

        Args:
            force_check: Force actual connection check

        Returns:
            True if connected
        """
        return self.comm.is_connected(force_check)

    # ========================================================================
    # LED TYPE SELECTION
    # ========================================================================

    def select_led_type(self, led_type: str) -> bool:
        """
        Select LED type (IR or White).

        Args:
            led_type: 'ir' or 'white'

        Returns:
            True if successful
        """
        if not self.is_connected():
            logger.error("Not connected")
            return False

        # Clear buffers
        self.comm.clear_buffers()

        # Build and send command
        if led_type.lower() == "ir":
            cmd = CommandBuilder.build_select_led_ir()
            expected_response = Responses.LED_IR_SELECTED
        elif led_type.lower() == "white":
            cmd = CommandBuilder.build_select_led_white()
            expected_response = Responses.LED_WHITE_SELECTED
        else:
            logger.error(f"Invalid LED type: {led_type}")
            return False

        # Send command
        if not self.comm.send_bytes(cmd):
            return False

        # Wait for response
        if not self.comm.read_until_response(expected_response, timeout=2.0):
            logger.error(f"Failed to select LED type: {led_type}")
            return False

        # Update state
        self.state.set_current_led_type(led_type)

        logger.info(f"LED type selected: {led_type.upper()}")
        return True

    # ========================================================================
    # LED CONTROL (Simple On/Off)
    # ========================================================================

    def led_on(self) -> bool:
        """
        Turn on currently selected LED.

        Returns:
            True if successful
        """
        if not self.is_connected():
            logger.error("Not connected")
            return False

        self.comm.clear_buffers()

        cmd = CommandBuilder.build_led_on()
        if not self.comm.send_bytes(cmd):
            return False

        # Wait for ACK
        if not self.comm.read_until_response(Responses.LED_ON_ACK, timeout=2.0):
            logger.error("LED ON failed - no ACK")
            return False

        # Update state
        current_type = self.state.get_current_led_type()
        self.state.set_led_state(current_type, True)

        logger.info(f"{current_type.upper()} LED turned ON")
        return True

    def led_off(self, led_type: Optional[str] = None) -> bool:
        """
        Turn off LED.

        Args:
            led_type: 'ir', 'white', or None for currently selected LED

        Returns:
            True if successful
        """
        if not self.is_connected():
            logger.error("Not connected")
            return False

        # If specific LED type given, select it first
        if led_type is not None:
            if not self.select_led_type(led_type):
                return False

        self.comm.clear_buffers()

        cmd = CommandBuilder.build_led_off()
        if not self.comm.send_bytes(cmd):
            return False

        # Wait for ACK (may be ACK_OFF or just success)
        time.sleep(0.1)  # Small delay for LED to turn off

        # Update state
        current_type = self.state.get_current_led_type()
        self.state.set_led_state(current_type, False)

        logger.info(f"{current_type.upper()} LED turned OFF")
        return True

    def led_dual_off(self) -> bool:
        """
        Turn off both LEDs.

        Returns:
            True if successful
        """
        if not self.is_connected():
            return False

        self.comm.clear_buffers()

        cmd = CommandBuilder.build_led_dual_off()
        if not self.comm.send_bytes(cmd):
            return False

        time.sleep(0.1)

        # Update state
        self.state.turn_off_all_leds()

        logger.info("Both LEDs turned OFF")
        return True

    # ========================================================================
    # LED POWER CONTROL
    # ========================================================================

    def set_led_power(self, power: int, led_type: Optional[str] = None) -> bool:
        """
        Set LED power for specific LED type.

        Args:
            power: Power 0-100
            led_type: 'ir', 'white', or None for current

        Returns:
            True if successful
        """
        if not self.is_connected():
            return False

        power = max(0, min(100, power))

        # Determine which LED
        if led_type == "ir":
            cmd = CommandBuilder.build_set_ir_power(power)
        elif led_type == "white":
            cmd = CommandBuilder.build_set_white_power(power)
        elif led_type is None:
            # Use current LED
            cmd = CommandBuilder.build_set_led_power(power)
        else:
            logger.error(f"Invalid LED type: {led_type}")
            return False

        # AGGRESSIVE buffer clearing before LED power commands
        # This is critical during dual LED setup
        self.comm.clear_buffers(aggressive=True)

        # Send command
        if not self.comm.send_bytes(cmd):
            return False

        # Wait for ACK (0xAA = RESPONSE_LED_ON_ACK)
        response = self.comm.read_bytes(1, timeout=1.0)
        if not response or response[0] != 0xAA:
            logger.warning("LED power command may have failed (no ACK)")
            # Don't return False - command was sent, might still work

        time.sleep(0.05)  # Small delay for ESP32 to process

        # Update state
        self.state.set_led_power(power, led_type)

        led_name = led_type.upper() if led_type else self.state.get_current_led_type().upper()
        logger.info(f"{led_name} LED power set to {power}%")
        return True

    # ========================================================================
    # SYNC PULSE (For Recording)
    # ========================================================================

    def begin_sync_pulse(self, dual: bool = False) -> float:
        """
        Begin sync pulse (LED ON with timing).
        This is used for synchronized frame capture.

        Args:
            dual: If True, use dual LED mode (both IR + White)

        Returns:
            Timestamp when pulse started
        """
        if not self.is_connected():
            raise RuntimeError("Not connected")

        # AGGRESSIVE buffer clearing before sync operations
        # This prevents buffer corruption errors from stale data
        self.comm.clear_buffers(aggressive=True)

        # Build command
        if dual:
            cmd = CommandBuilder.build_sync_capture_dual()
        else:
            cmd = CommandBuilder.build_sync_capture()

        # Send command
        if not self.comm.send_bytes(cmd):
            raise RuntimeError("Failed to send sync pulse command")

        # Wait for ACK
        if not self.comm.read_until_response(Responses.LED_ON_ACK, timeout=2.0):
            raise RuntimeError("No ACK received for sync pulse")

        # Mark in state
        pulse_start = self.state.begin_sync_pulse()

        logger.debug(f"Sync pulse started (dual={dual})")

        return pulse_start

    def wait_sync_complete(self, timeout: float = 5.0) -> dict:
        """
        Wait for sync pulse to complete and get response.

        Args:
            timeout: Timeout in seconds

        Returns:
            Dictionary with sync response data
        """
        if not self.is_connected():
            raise RuntimeError("Not connected")

        # Read sync complete response (15 bytes)
        response_data = self.comm.read_bytes(15, timeout=timeout)

        if not response_data:
            logger.error("No sync complete response received")
            self.state.abort_sync()
            return {
                "success": False,
                "error": "No response",
                "timing_ms": 0,
                "temperature": 0.0,
                "humidity": 0.0,
                "led_type_used": "unknown",
                "led_duration_ms": 0,
                "led_power_actual": 0,
            }

        # Parse response
        sync_response = ResponseParser.parse_sync_response(response_data)

        if not sync_response:
            logger.error("Failed to parse sync response")
            self.state.abort_sync()
            return {
                "success": False,
                "error": "Parse failed",
                "timing_ms": 0,
                "temperature": 0.0,
                "humidity": 0.0,
                "led_type_used": "unknown",
                "led_duration_ms": 0,
                "led_power_actual": 0,
            }

        # Convert to dict
        result = {
            "success": sync_response.success,
            "timing_ms": sync_response.timing_ms,
            "temperature": sync_response.temperature,
            "humidity": sync_response.humidity,
            "led_type_used": sync_response.led_type_used,
            "led_duration_ms": sync_response.led_duration_ms,
            "led_power_actual": sync_response.led_power_actual,
        }

        # Update state
        self.state.complete_sync(result)

        logger.debug(f"Sync complete: {result['timing_ms']}ms, T={result['temperature']:.1f}°C")

        return result

    # ========================================================================
    # TIMING CONFIGURATION
    # ========================================================================

    def set_timing(self, stabilization_ms: int, exposure_ms: int) -> bool:
        """
        Set LED timing parameters.

        Args:
            stabilization_ms: LED stabilization time in ms
            exposure_ms: Exposure time in ms

        Returns:
            True if successful
        """
        if not self.is_connected():
            return False

        # Build command
        cmd = CommandBuilder.build_set_timing(stabilization_ms, exposure_ms)

        # Send command
        if not self.comm.send_bytes(cmd):
            return False

        # Wait for response
        if not self.comm.read_until_response(Responses.TIMING_SET, timeout=2.0):
            logger.error("Failed to set timing")
            return False

        # Update state
        self.state.set_timing(stabilization_ms, exposure_ms)

        logger.info(f"Timing set: {stabilization_ms}ms stabilization + {exposure_ms}ms exposure")
        return True

    def get_timing(self) -> TimingConfig:
        """Get current timing configuration"""
        return self.state.get_timing()

    # ========================================================================
    # STATUS QUERIES
    # ========================================================================

    def get_sensor_data(self) -> Optional[dict]:
        """
        Query sensor data (temperature and humidity) from ESP32.

        Sends CMD_STATUS and reads 5-byte response:
        [status_code][temp_high][temp_low][hum_high][hum_low]

        Note: Applies -2.0°C calibration offset to compensate for:
        - ESP32 self-heating (~+1°C)
        - LED proximity heating (~+1°C)
        To adjust offset, modify TEMPERATURE_CALIBRATION_OFFSET constant.

        Returns:
            dict with 'temperature' and 'humidity', or None if failed
        """
        if not self.is_connected():
            return None

        self.comm.clear_buffers()

        # Send STATUS command
        cmd = CommandBuilder.build_status()
        if not self.comm.send_bytes(cmd):
            return None

        # Read 5-byte response
        response_data = self.comm.read_bytes(5, timeout=2.0)

        if not response_data or len(response_data) < 5:
            logger.error("No sensor data response")
            return None

        try:
            # Parse response: [status][temp_high][temp_low][hum_high][hum_low]
            status_code = response_data[0]

            # Debug: Log raw bytes
            logger.debug(f"Raw sensor response: {' '.join(f'0x{b:02X}' for b in response_data)}")

            # Temperature: int16 big-endian, scaled by 10
            temp_raw = (response_data[1] << 8) | response_data[2]
            # Handle signed int16 (two's complement)
            if temp_raw > 32767:
                temp_raw = temp_raw - 65536
            temperature = temp_raw / 10.0

            # Apply calibration offset to compensate for ESP32 self-heating and LED proximity heating
            # Typical offset: -2.0°C (ESP32 ~+1°C, LED proximity ~+1°C)
            TEMPERATURE_CALIBRATION_OFFSET = -2.0
            temperature = temperature + TEMPERATURE_CALIBRATION_OFFSET

            # Humidity: uint16 big-endian, scaled by 10
            hum_raw = (response_data[3] << 8) | response_data[4]
            humidity = hum_raw / 10.0

            # Validate ranges
            if temperature < -40.0 or temperature > 85.0:
                logger.warning(
                    f"Temperature out of range: {temperature}°C (raw: {temp_raw}, before offset: {temp_raw/10.0}°C)"
                )
                # Use filtered value or default
                temperature = 25.0  # Default room temperature

            if humidity < 0.0 or humidity > 100.0:
                logger.warning(f"Humidity out of range: {humidity}% (raw: {hum_raw})")
                humidity = max(0.0, min(100.0, humidity))  # Clamp to valid range

            logger.debug(
                f"Sensor data: T={temperature:.1f}°C (calibrated, offset={TEMPERATURE_CALIBRATION_OFFSET}°C), H={humidity:.1f}%"
            )

            return {"temperature": temperature, "humidity": humidity, "status_code": status_code}

        except Exception as e:
            logger.error(f"Error parsing sensor data: {e}")
            return None

    def get_led_status(self) -> Optional[LEDStatus]:
        """
        Query current LED status from ESP32.

        Returns:
            LEDStatus or None if failed
        """
        if not self.is_connected():
            return None

        # AGGRESSIVE buffer clearing before status queries
        self.comm.clear_buffers(aggressive=True)

        # Send command
        cmd = CommandBuilder.build_get_led_status()
        if not self.comm.send_bytes(cmd):
            return None

        # Read response (6 bytes)
        response_data = self.comm.read_bytes(6, timeout=2.0)

        if not response_data:
            logger.error("No LED status response")
            return None

        # Parse response
        led_status = ResponseParser.parse_led_status(response_data)

        if led_status:
            # Update internal state
            self.state.set_led_state("ir", led_status.ir_state)
            self.state.set_led_state("white", led_status.white_state)
            self.state.set_led_power(led_status.ir_power, "ir")
            self.state.set_led_power(led_status.white_power, "white")

            # Update current type
            if led_status.current_led_type == LEDTypes.IR:
                self.state.set_current_led_type("ir")
            else:
                self.state.set_current_led_type("white")

        return led_status

    def get_state_snapshot(self) -> dict:
        """Get complete state snapshot"""
        return self.state.get_snapshot()

    # ========================================================================
    # CAMERA TYPE
    # ========================================================================

    def set_camera_type(self, camera_type: int) -> bool:
        """
        Set camera type.

        Args:
            camera_type: CameraTypes.HIK_GIGE or CameraTypes.USB_GENERIC

        Returns:
            True if successful
        """
        if not self.is_connected():
            return False

        cmd = CommandBuilder.build_set_camera_type(camera_type)

        if not self.comm.send_bytes(cmd):
            return False

        time.sleep(0.1)

        self.state.set_camera_type(camera_type)

        cam_name = "HIK_GIGE" if camera_type == CameraTypes.HIK_GIGE else "USB_GENERIC"
        logger.info(f"Camera type set to {cam_name}")
        return True

    # ========================================================================
    # STATISTICS
    # ========================================================================

    def get_connection_stats(self) -> dict:
        """Get connection statistics"""
        comm_stats = self.comm.get_connection_stats()
        state_snapshot = self.state.get_snapshot()

        return {
            **comm_stats,
            "led_states": {
                "ir": state_snapshot["led_ir_state"],
                "white": state_snapshot["led_white_state"],
                "current_type": state_snapshot["current_led_type"],
            },
            "led_powers": {
                "ir": state_snapshot["ir_led_power"],
                "white": state_snapshot["white_led_power"],
            },
        }

    # ========================================================================
    # CLEANUP
    # ========================================================================

    def cleanup(self):
        """Cleanup and disconnect"""
        logger.info("ESP32Controller cleanup...")
        self.disconnect()
        logger.info("ESP32Controller cleanup complete")

    def __del__(self):
        """Ensure cleanup on deletion"""
        try:
            self.cleanup()
        except:
            pass


# ============================================================================
# QUICK TEST
# ============================================================================

if __name__ == "__main__":
    import sys

    print("Testing ESP32Controller...")

    # Create controller
    controller = ESP32Controller(auto_connect=True)

    if not controller.is_connected():
        print("❌ Failed to connect")
        sys.exit(1)

    print("✅ Connected!")

    # Test LED control
    print("\nTesting IR LED...")
    controller.select_led_type("ir")
    controller.set_led_power(50, "ir")
    controller.led_on()
    time.sleep(1)
    controller.led_off()

    print("\nTesting White LED...")
    controller.select_led_type("white")
    controller.set_led_power(30, "white")
    controller.led_on()
    time.sleep(1)
    controller.led_off()

    # Test sync pulse
    print("\nTesting sync pulse...")
    controller.select_led_type("ir")
    controller.set_timing(1000, 10)

    start = controller.begin_sync_pulse(dual=False)
    print(f"Pulse started at {start:.3f}")

    time.sleep(1.0)  # Wait for stabilization

    result = controller.wait_sync_complete()
    print(f"Sync complete: {result}")

    # Get status
    print("\nGetting LED status...")
    status = controller.get_led_status()
    if status:
        print(f"Current LED: {status.current_led_type}")
        print(f"IR: {'ON' if status.ir_state else 'OFF'} ({status.ir_power}%)")
        print(f"White: {'ON' if status.white_state else 'OFF'} ({status.white_power}%)")

    # Cleanup
    controller.cleanup()

    print("\n✅ All tests passed!")
