"""
ESP32 Communication Layer - FIXED VERSION
Low-level serielle Kommunikation mit verbesserter Verbindungsstabilität

FIXES:
- ✅ Längerer Boot-Delay (2s statt 0.5s)
- ✅ DTR/RTS explizit gesetzt
- ✅ Bessere Port-Erkennung
- ✅ Verbesserte Auto-Reconnect-Logik
- ✅ Mehr Debug-Logging
"""

import logging
import threading
import time
from typing import Optional

import serial
import serial.tools.list_ports

logger = logging.getLogger(__name__)


class ESP32Communication:
    """Low-level serielle Kommunikation mit ESP32 - FIXED"""

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 115200,
        read_timeout: float = 2.0,
        write_timeout: float = 1.0,
    ):
        self.port = port
        self.baudrate = baudrate
        self.read_timeout = read_timeout
        self.write_timeout = write_timeout

        # Connection state
        self.serial_connection: Optional[serial.Serial] = None
        self.connected = False

        # Thread safety
        self._comm_lock = threading.RLock()

        # Stats
        self._consecutive_failures = 0
        self._max_failures_before_reconnect = 3
        self._last_successful_command = 0.0
        self._connection_start_time = 0.0  # Track connection uptime

    def find_esp32_port(self) -> Optional[str]:
        """
        Findet ESP32 Port automatisch - VERBESSERT

        Returns:
            Port string oder None wenn nicht gefunden
        """
        logger.info("Scanning for ESP32 ports...")

        try:
            ports = serial.tools.list_ports.comports()

            # ERWEITERTE ESP32 identifiers
            esp32_identifiers = [
                "CP210",  # Silicon Labs CP210x (sehr häufig)
                "CH340",  # CH340 USB-Serial (billige Boards)
                "CH341",  # CH341 USB-Serial
                "FTDI",  # FTDI chips
                "USB-SERIAL",  # Generic USB-Serial
                "USB SERIAL",  # Variant
                "UART",  # Generic UART
                "SLAB",  # Silicon Labs (alternate)
            ]

            # VID/PID für bekannte ESP32 boards
            esp32_vid_pid = [
                (0x10C4, 0xEA60),  # CP210x
                (0x1A86, 0x7523),  # CH340
                (0x0403, 0x6001),  # FTDI
            ]

            candidates = []

            for port in ports:
                port_desc = (port.description or "").upper()
                port_hw = (port.hwid or "").upper()
                score = 0

                # Check text identifiers
                for identifier in esp32_identifiers:
                    if identifier in port_desc or identifier in port_hw:
                        score += 10
                        logger.debug(f"Port {port.device} matched identifier '{identifier}'")

                # Check VID/PID
                if port.vid and port.pid:
                    if (port.vid, port.pid) in esp32_vid_pid:
                        score += 20
                        logger.debug(
                            f"Port {port.device} matched VID:PID {port.vid:04X}:{port.pid:04X}"
                        )

                # USB in name is weak match
                if "USB" in port_desc or "USB" in port_hw:
                    score += 1

                if score > 0:
                    candidates.append((score, port))
                    logger.info(f"Found potential ESP32 port: {port.device} (score: {score})")
                    logger.info(f"  Description: {port.description}")
                    logger.info(f"  HWID: {port.hwid}")

            if not candidates:
                logger.warning("No ESP32 port found automatically")
                logger.info("Available ports:")
                for port in ports:
                    logger.info(f"  - {port.device}: {port.description}")
                return None

            # Return highest score
            candidates.sort(key=lambda x: x[0], reverse=True)
            best_port = candidates[0][1].device
            logger.info(f"Selected best match: {best_port}")
            return best_port

        except Exception as e:
            logger.error(f"Error scanning ports: {e}")
            return None

    def connect(self, port: Optional[str] = None) -> bool:
        """
        Verbindet mit ESP32 - VERBESSERT

        Args:
            port: Optional port override

        Returns:
            True wenn erfolgreich verbunden
        """
        with self._comm_lock:
            # Close existing connection
            if self.serial_connection and self.serial_connection.is_open:
                try:
                    self.serial_connection.close()
                    logger.debug("Closed existing connection")
                except:
                    pass

            # Determine port
            target_port = port or self.port
            if not target_port:
                target_port = self.find_esp32_port()

            if not target_port:
                logger.error("No port specified and auto-detection failed")
                self.connected = False
                return False

            # Try to connect with different DTR/RTS configurations
            configs = [
                # Most common: DTR and RTS low (prevents auto-reset)
                {"dtr": False, "rts": False},
                # Some boards need DTR high
                {"dtr": True, "rts": False},
                # Default behavior
                {"dtr": None, "rts": None},
            ]

            for config in configs:
                try:
                    logger.info(f"Connecting to ESP32 on {target_port}...")
                    logger.debug(f"Config: DTR={config['dtr']}, RTS={config['rts']}")

                    # Create serial connection with explicit settings
                    serial_kwargs = {
                        "port": target_port,
                        "baudrate": self.baudrate,
                        "timeout": self.read_timeout,
                        "write_timeout": self.write_timeout,
                        "bytesize": serial.EIGHTBITS,
                        "parity": serial.PARITY_NONE,
                        "stopbits": serial.STOPBITS_ONE,
                    }

                    # Add DTR/RTS if specified
                    if config["dtr"] is not None:
                        serial_kwargs["dtr"] = config["dtr"]
                    if config["rts"] is not None:
                        serial_kwargs["rts"] = config["rts"]

                    self.serial_connection = serial.Serial(**serial_kwargs)

                    # WICHTIG: Längerer Delay für ESP32 Boot
                    logger.debug("Waiting for ESP32 to boot...")
                    time.sleep(2.0)  # ERHÖHT von 0.5 auf 2.0 Sekunden

                    # Clear any boot messages in buffer
                    self.clear_buffers()

                    # Test if ESP32 responds
                    logger.debug("Testing ESP32 response...")
                    test_success = self._test_connection()

                    if test_success:
                        self.port = target_port
                        self.connected = True
                        self._consecutive_failures = 0
                        self._connection_start_time = time.time()  # Track connection start time

                        logger.info(f"✅ Successfully connected to ESP32 on {target_port}")
                        logger.info(f"   Config: DTR={config['dtr']}, RTS={config['rts']}")
                        return True
                    else:
                        logger.warning(f"Port opened but ESP32 not responding with config {config}")
                        self.serial_connection.close()

                except serial.SerialException as e:
                    logger.debug(f"Config {config} failed: {e}")
                    continue
                except Exception as e:
                    logger.debug(f"Unexpected error with config {config}: {e}")
                    continue

            # All configs failed
            logger.error(f"Failed to connect to {target_port} with all configurations")
            self.connected = False
            return False

    def _test_connection(self) -> bool:
        """
        Testet ob ESP32 antwortet (NEU)

        Returns:
            True wenn ESP32 antwortet
        """
        try:
            # Send STATUS command (0x02)
            self.serial_connection.write(bytes([0x02]))
            self.serial_connection.flush()

            # Wait for response
            time.sleep(0.2)

            if self.serial_connection.in_waiting > 0:
                response = self.serial_connection.read(self.serial_connection.in_waiting)
                logger.debug(f"Test response: {response.hex()}")
                # Valid responses are 0x10 (OFF) or 0x11 (ON)
                if response and (response[0] == 0x10 or response[0] == 0x11):
                    logger.debug("ESP32 responded correctly to STATUS")
                    return True

            logger.debug("No valid response from ESP32")
            return False

        except Exception as e:
            logger.debug(f"Connection test failed: {e}")
            return False

    def disconnect(self):
        """Trennt Verbindung zum ESP32"""
        with self._comm_lock:
            if self.serial_connection and self.serial_connection.is_open:
                try:
                    self.clear_buffers()
                    self.serial_connection.close()
                    logger.info("ESP32 disconnected")
                except Exception as e:
                    logger.error(f"Error during disconnect: {e}")

            self.connected = False
            self.serial_connection = None

    def is_connected(self, force_check: bool = False) -> bool:
        """
        Prüft ob verbunden.

        Args:
            force_check: Wenn True, prüft tatsächliche Verbindung

        Returns:
            True wenn verbunden
        """
        if not force_check:
            return self.connected

        # Check actual connection
        with self._comm_lock:
            if not self.serial_connection or not self.serial_connection.is_open:
                self.connected = False
                return False

            try:
                # Try to access port (will fail if disconnected)
                _ = self.serial_connection.in_waiting
                self.connected = True
                return True
            except:
                self.connected = False
                return False

    def send_byte(self, byte: int) -> bool:
        """
        Sendet einzelnes Byte.

        Args:
            byte: Byte zu senden (0-255)

        Returns:
            True wenn erfolgreich
        """
        with self._comm_lock:
            if not self.is_connected():
                logger.error("Cannot send byte: not connected")
                return False

            try:
                self.serial_connection.write(bytes([byte]))
                self.serial_connection.flush()
                self._last_successful_command = time.time()
                self._consecutive_failures = 0
                logger.debug(f"Sent byte: 0x{byte:02X}")
                return True

            except Exception as e:
                logger.error(f"Error sending byte 0x{byte:02X}: {e}")
                self._consecutive_failures += 1
                self._check_reconnect()
                return False

    def send_bytes(self, data: bytes) -> bool:
        """
        Sendet mehrere Bytes.

        Args:
            data: Bytes zu senden

        Returns:
            True wenn erfolgreich
        """
        with self._comm_lock:
            if not self.is_connected():
                logger.error("Cannot send bytes: not connected")
                return False

            try:
                self.serial_connection.write(data)
                self.serial_connection.flush()
                self._last_successful_command = time.time()
                self._consecutive_failures = 0
                logger.debug(f"Sent {len(data)} bytes: {data.hex()}")
                return True

            except Exception as e:
                logger.error(f"Error sending bytes: {e}")
                self._consecutive_failures += 1
                self._check_reconnect()
                return False

    def read_byte(self, timeout: Optional[float] = None) -> Optional[int]:
        """
        Liest einzelnes Byte.

        Args:
            timeout: Optional timeout override

        Returns:
            Byte (0-255) oder None bei Fehler
        """
        with self._comm_lock:
            if not self.is_connected():
                return None

            try:
                old_timeout = self.serial_connection.timeout
                if timeout is not None:
                    self.serial_connection.timeout = timeout

                data = self.serial_connection.read(1)

                if timeout is not None:
                    self.serial_connection.timeout = old_timeout

                if len(data) == 1:
                    logger.debug(f"Read byte: 0x{data[0]:02X}")
                    return data[0]
                return None

            except Exception as e:
                logger.error(f"Error reading byte: {e}")
                return None

    def read_bytes(self, count: int, timeout: Optional[float] = None) -> Optional[bytes]:
        """
        Liest mehrere Bytes.

        Args:
            count: Anzahl zu lesender Bytes
            timeout: Optional timeout override

        Returns:
            Bytes oder None bei Fehler
        """
        with self._comm_lock:
            if not self.is_connected():
                return None

            try:
                old_timeout = self.serial_connection.timeout
                if timeout is not None:
                    self.serial_connection.timeout = timeout

                data = self.serial_connection.read(count)

                if timeout is not None:
                    self.serial_connection.timeout = old_timeout

                if len(data) == count:
                    logger.debug(f"Read {count} bytes: {data.hex()}")
                    return data

                logger.warning(f"Expected {count} bytes, got {len(data)}")
                return None

            except Exception as e:
                logger.error(f"Error reading bytes: {e}")
                return None

    def read_until_response(
        self, expected_byte: int, timeout: float = 2.0, max_bytes: int = 100
    ) -> bool:
        """
        Liest bis erwartetes Byte gefunden wird.

        Args:
            expected_byte: Erwartetes Response-Byte
            timeout: Timeout in Sekunden
            max_bytes: Maximale Anzahl zu lesender Bytes

        Returns:
            True wenn Response gefunden
        """
        start_time = time.time()
        bytes_read = 0

        logger.debug(f"Waiting for response 0x{expected_byte:02X}...")

        while (time.time() - start_time) < timeout and bytes_read < max_bytes:
            byte = self.read_byte(timeout=0.1)
            if byte is None:
                continue

            bytes_read += 1

            if byte == expected_byte:
                logger.debug(f"Found expected response 0x{expected_byte:02X}")
                return True

        logger.warning(f"Response 0x{expected_byte:02X} not found within timeout")
        return False

    def clear_buffers(self, aggressive: bool = False) -> bool:
        """
        Löscht Input/Output Buffer.

        Args:
            aggressive: If True, performs multiple clearing attempts with delays

        Returns:
            True wenn erfolgreich
        """
        with self._comm_lock:
            if not self.serial_connection or not self.serial_connection.is_open:
                return False

            try:
                if aggressive:
                    # AGGRESSIVE CLEARING: Multiple passes with delays
                    # This helps clear ESP32's internal TX buffer that may have accumulated data
                    total_cleared = 0

                    for attempt in range(3):
                        # Read any pending data
                        if self.serial_connection.in_waiting > 0:
                            junk = self.serial_connection.read(self.serial_connection.in_waiting)
                            total_cleared += len(junk)
                            logger.debug(
                                f"Aggressive clear pass {attempt+1}: cleared {len(junk)} bytes"
                            )

                        # Reset buffers
                        self.serial_connection.reset_input_buffer()
                        self.serial_connection.reset_output_buffer()

                        # Small delay to let ESP32 flush its internal buffer
                        if attempt < 2:
                            time.sleep(0.05)

                    if total_cleared > 0:
                        logger.info(
                            f"🧹 Aggressive buffer clear: removed {total_cleared} bytes total"
                        )

                else:
                    # NORMAL CLEARING: Single pass
                    # Read and discard any pending data
                    if self.serial_connection.in_waiting > 0:
                        junk = self.serial_connection.read(self.serial_connection.in_waiting)
                        logger.debug(f"Cleared {len(junk)} bytes from input buffer")

                    # Reset buffers
                    self.serial_connection.reset_input_buffer()
                    self.serial_connection.reset_output_buffer()

                return True

            except Exception as e:
                logger.debug(f"Buffer clear failed: {e}")
                return False

    def _check_reconnect(self):
        """Prüft ob Reconnect nötig ist - VERBESSERT"""
        if self._consecutive_failures >= self._max_failures_before_reconnect:
            logger.warning(
                f"⚠️ {self._consecutive_failures} consecutive failures, attempting reconnect..."
            )
            old_port = self.port
            self.disconnect()
            time.sleep(1.0)  # Längerer Delay vor Reconnect
            if self.connect(port=old_port):
                logger.info("✅ Reconnect successful")
            else:
                logger.error("❌ Reconnect failed")

    def get_connection_stats(self) -> dict:
        """
        Gibt Connection-Statistiken zurück.

        Returns:
            Dict mit Stats
        """
        return {
            "connected": self.connected,
            "port": self.port,
            "baudrate": self.baudrate,
            "consecutive_failures": self._consecutive_failures,
            "last_successful_command": self._last_successful_command,
            "time_since_last_command": (
                time.time() - self._last_successful_command
                if self._last_successful_command > 0
                else -1
            ),
            "uptime_seconds": (
                time.time() - self._connection_start_time
                if self._connection_start_time > 0
                else 0
            ),
        }
