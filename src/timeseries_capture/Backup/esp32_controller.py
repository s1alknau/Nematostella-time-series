import struct
import time
from typing import Any, Dict, List, Optional

import serial
from serial.tools import list_ports


class ESP32Commands:
    """ESP32 command constants"""

    LED_ON = 0x01
    LED_OFF = 0x00
    STATUS = 0x02
    SYNC_CAPTURE = 0x0C
    SET_LED_POWER = 0x10
    GET_TIMESTAMP = 0x20


class ESP32Responses:
    """ESP32 response constants"""

    SYNC_COMPLETE = 0x1B
    ACK = 0xAA
    ERROR = 0xFF
    TIMESTAMP = 0x21
    STATUS_LED_ON = 0x11
    STATUS_LED_OFF = 0x10


class ESP32Controller:
    """Simplified ESP32 communication controller"""

    def __init__(self):
        self.serial_port: Optional[serial.Serial] = None
        self.connected = False
        self.port_name: Optional[str] = None
        self._last_timestamp = 0
        self._boot_time_offset = None

    def connect(self, port_name: Optional[str] = None, baud_rate: int = 115200) -> bool:
        """Connect to ESP32"""
        if port_name is None:
            port_name = self._find_esp32_port()

        try:
            self.serial_port = serial.Serial(port_name, baud_rate, timeout=2)
            time.sleep(2)  # Allow ESP32 to boot

            # Clear boot messages
            if self.serial_port.in_waiting > 0:
                self.serial_port.read(self.serial_port.in_waiting)

            # Test connection
            if self._test_connection():
                self.connected = True
                self.port_name = port_name
                self._sync_time()
                return True

            self.serial_port.close()
            return False

        except Exception as e:
            print(f"ESP32 connection failed: {e}")
            return False

    def disconnect(self):
        """Disconnect from ESP32"""
        if self.serial_port and self.serial_port.is_open:
            self.led_off()
            self.serial_port.close()
        self.connected = False
        self.serial_port = None

    def led_on(self) -> bool:
        """Turn LED on"""
        return self._send_command(ESP32Commands.LED_ON) == ESP32Responses.ACK

    def led_off(self) -> bool:
        """Turn LED off"""
        return self._send_command(ESP32Commands.LED_OFF) == ESP32Responses.ACK

    def set_led_power(self, power: int) -> bool:
        """Set LED power (0-100%)"""
        power = max(0, min(100, power))
        response = self._send_command(ESP32Commands.SET_LED_POWER, [power])
        return response == ESP32Responses.ACK

    def get_status(self) -> Optional[Dict[str, Any]]:
        """Get ESP32 status with environmental data"""
        self._flush_buffers()

        if not self._write_byte(ESP32Commands.STATUS):
            return None

        response = self._read_bytes(5)
        if not response or len(response) != 5:
            return None

        return {
            "led_on": response[0] == ESP32Responses.STATUS_LED_ON,
            "temperature": struct.unpack(">h", response[1:3])[0] / 10.0,
            "humidity": struct.unpack(">H", response[3:5])[0] / 10.0,
        }

    def sync_capture(self) -> Optional[Dict[str, Any]]:
        """Get synchronized capture data with minimal latency"""
        capture_start = time.perf_counter()

        self._flush_buffers()

        if not self._write_byte(ESP32Commands.SYNC_CAPTURE):
            return None

        response = self._read_bytes(11)
        if not response or len(response) != 11 or response[0] != ESP32Responses.SYNC_COMPLETE:
            return None

        # Parse response
        esp32_timestamp = struct.unpack(">I", response[1:5])[0]
        temperature = struct.unpack(">h", response[5:7])[0] / 10.0
        humidity = struct.unpack(">H", response[7:9])[0] / 10.0
        led_duration_ms = response[9]

        # Calculate synchronized timestamp
        if self._boot_time_offset is not None:
            esp32_time = self._boot_time_offset + (esp32_timestamp / 1000.0)
        else:
            esp32_time = time.time()

        return {
            "python_timestamp": capture_start,
            "esp32_timestamp": esp32_time,
            "esp32_millis": esp32_timestamp,
            "temperature": temperature,
            "humidity": humidity,
            "led_duration_ms": led_duration_ms,
        }

    def _test_connection(self) -> bool:
        """Test ESP32 connection"""
        status = self.get_status()
        return status is not None

    def _sync_time(self):
        """Synchronize time with ESP32"""
        try:
            # Get ESP32 timestamp
            self._flush_buffers()
            if self._write_byte(ESP32Commands.GET_TIMESTAMP):
                response = self._read_bytes(5)
                if response and len(response) == 5 and response[0] == ESP32Responses.TIMESTAMP:
                    esp32_millis = struct.unpack(">I", response[1:5])[0]
                    current_time = time.time()
                    self._boot_time_offset = current_time - (esp32_millis / 1000.0)
        except:
            self._boot_time_offset = None

    def _send_command(self, cmd: int, data: Optional[List[int]] = None) -> Optional[int]:
        """Send command and get response"""
        self._flush_buffers()

        # Send command
        if not self._write_byte(cmd):
            return None

        # Send additional data if provided
        if data:
            for byte in data:
                if not self._write_byte(byte):
                    return None

        # Read response
        response = self._read_bytes(1)
        return response[0] if response else None

    def _write_byte(self, byte: int) -> bool:
        """Write single byte to serial"""
        try:
            self.serial_port.write(bytes([byte]))
            self.serial_port.flush()
            return True
        except:
            return False

    def _read_bytes(self, count: int, timeout: float = 1.0) -> Optional[bytes]:
        """Read exact number of bytes"""
        try:
            start_time = time.time()
            data = b""

            while len(data) < count and (time.time() - start_time) < timeout:
                remaining = count - len(data)
                chunk = self.serial_port.read(remaining)
                if chunk:
                    data += chunk
                else:
                    time.sleep(0.001)

            return data if len(data) == count else None
        except:
            return None

    def _flush_buffers(self):
        """Flush serial buffers"""
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.reset_input_buffer()
            self.serial_port.reset_output_buffer()

    def _find_esp32_port(self) -> str:
        """Auto-detect ESP32 serial port"""
        # Try common ESP32 port first
        try:
            test_serial = serial.Serial("COM3", 115200, timeout=1)
            test_serial.close()
            return "COM3"
        except:
            pass

        # Search all ports
        ports = list_ports.comports()
        esp32_keywords = ["ESP32", "SILICON LABS", "CH340", "CP210"]

        for port in ports:
            description = port.description.upper()
            if any(keyword in description for keyword in esp32_keywords):
                return port.device

        # Default to first available port
        if ports:
            return ports[0].device

        raise Exception("No serial ports found")
