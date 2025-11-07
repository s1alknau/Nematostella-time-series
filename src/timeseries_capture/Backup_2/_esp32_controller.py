# # File: src/napari_timelapse_capture/_esp32_controller.py
# """ESP32 controller with unified direct serial approach - no hybrid complexity."""

# import serial
# import time
# import struct
# import threading
# from typing import Tuple, Optional
# from qtpy.QtCore import QObject

# # ✅ FIX: pyqtSignal Import mit try/except
# try:
#     from qtpy.QtCore import pyqtSignal
# except ImportError:
#     from qtpy.QtCore import Signal as pyqtSignal


# class ESP32Controller(QObject):
#     """Controller for ESP32 communication using direct serial connection."""

#     # Command bytes (matching ESP32 firmware)
#     CMD_LED_ON = 0x01
#     CMD_LED_OFF = 0x00
#     CMD_STATUS = 0x02
#     CMD_SYNC_CAPTURE = 0x0C
#     CMD_SET_LED_POWER = 0x10
#     CMD_SET_TIMING = 0x11
#     CMD_SET_CAMERA_TYPE = 0x13

#     # Response bytes (matching ESP32 firmware)
#     RESPONSE_SYNC_COMPLETE = 0x1B
#     RESPONSE_TIMING_SET = 0x21
#     RESPONSE_ACK_ON = 0x01
#     RESPONSE_ACK_OFF = 0x02
#     RESPONSE_STATUS_ON = 0x11
#     RESPONSE_STATUS_OFF = 0x10
#     RESPONSE_ERROR = 0xFF

#     # Camera types
#     CAMERA_TYPE_HIK_GIGE = 1
#     CAMERA_TYPE_USB_GENERIC = 2

#     # Signals
#     sensor_data_received = pyqtSignal(float, float)  # temperature, humidity
#     led_status_changed = pyqtSignal(bool, int)  # on/off, power_level
#     connection_status_changed = pyqtSignal(bool)  # connected/disconnected

#     def __init__(self, imswitch_main_controller=None):
#         super().__init__()
#         self.imswitch_main = imswitch_main_controller
#         self.serial_connection = None
#         self.connected = False
#         self.led_power = 100  # Default to 100% as in firmware
#         self.led_on_state = False
#         self.led_stabilization_ms = 500
#         self.trigger_delay_ms = 10

#         # Try to get port from ImSwitch config, then auto-detect
#         self.esp32_port = self._get_esp32_port()

#     def _get_esp32_port(self) -> Optional[str]:
#         """Get ESP32 port from ImSwitch config or auto-detect."""
#         # First try: ImSwitch configuration
#         if self.imswitch_main is not None:
#             try:
#                 config = getattr(self.imswitch_main, '_config', None)
#                 if config and 'rs232devices' in config:
#                     esp32_config = config['rs232devices'].get('ESP32', {})
#                     port = esp32_config.get('managerProperties', {}).get('serialport')
#                     if port:
#                         print(f"Found ESP32 port in ImSwitch config: {port}")
#                         return port
#             except Exception as e:
#                 print(f"Could not read ESP32 port from ImSwitch config: {e}")

#         # Second try: Auto-detect
#         return self._find_esp32_port()

#     def _find_esp32_port(self) -> Optional[str]:
#         """Auto-detect ESP32 port."""
#         import serial.tools.list_ports

#         print("Auto-detecting ESP32 port...")
#         ports = serial.tools.list_ports.comports()

#         for port in ports:
#             print(f"Checking port: {port.device} - {port.description}")
#             if any(identifier in port.description.lower() for identifier in
#                 ['esp32', 'cp210x', 'ch340', 'ftdi', 'silicon labs']):
#                 print(f"Found potential ESP32 port: {port.device}")
#                 return port.device

#         print("No ESP32 port auto-detected")
#         return None

#     def connect(self) -> bool:
#         """Connect to ESP32 via direct serial connection."""
#         if not self.esp32_port:
#             raise RuntimeError("No ESP32 port configured or detected")

#         try:
#             print(f"Connecting to ESP32 on port: {self.esp32_port}")

#             self.serial_connection = serial.Serial(
#                 port=self.esp32_port,
#                 baudrate=115200,
#                 timeout=2.0,
#                 write_timeout=1.0
#             )

#             # Wait for ESP32 to initialize
#             time.sleep(2.0)
#             self.serial_connection.reset_input_buffer()

#             # Test connection with status command
#             if self._test_connection():
#                 self.connected = True
#                 self.connection_status_changed.emit(True)
#                 print("ESP32 connected successfully")
#                 return True
#             else:
#                 self.serial_connection.close()
#                 self.serial_connection = None
#                 raise RuntimeError("ESP32 not responding to status command")

#         except Exception as e:
#             if self.serial_connection:
#                 try:
#                     self.serial_connection.close()
#                 except:
#                     pass
#                 self.serial_connection = None
#             raise RuntimeError(f"Failed to connect to ESP32: {str(e)}")

#     def _test_connection(self) -> bool:
#         """Test ESP32 connection with status command."""
#         try:
#             self._send_byte(self.CMD_STATUS)
#             response = self._read_status_response(timeout=3.0)
#             return response is not None
#         except Exception as e:
#             print(f"Connection test failed: {e}")
#             return False

#     def disconnect(self):
#         """Disconnect from ESP32."""
#         if self.serial_connection:
#             try:
#                 # Try to turn off LED before disconnecting
#                 self.led_off()
#             except:
#                 pass
#             try:
#                 self.serial_connection.close()
#             except:
#                 pass
#             finally:
#                 self.serial_connection = None

#         self.connected = False
#         self.connection_status_changed.emit(False)
#         print("ESP32 disconnected")

#     def is_connected(self, force_check: bool = False) -> bool:
#         if not self.connected or not self.serial_connection:
#             return False
#         if force_check:
#             try:
#                 ok = self._test_connection()
#                 if not ok:
#                     self.connected = False
#                     self.connection_status_changed.emit(False)
#                 return ok
#             except:
#                 self.connected = False
#                 self.connection_status_changed.emit(False)
#                 return False
#         return True


#         # Original code (commented out to stop spam):
#         # try:
#         #     # Quick connection test
#         #     self._send_byte(self.CMD_STATUS)
#         #     response = self._read_status_response(timeout=1.0)
#         #     return response is not None
#         # except:
#         #     return False

#     # =========================================================================
#     # UNIFIED SERIAL COMMUNICATION METHODS
#     # =========================================================================

#     def _send_byte(self, byte_val: int):
#         """Send single byte to ESP32 with debug."""
#         if not self.serial_connection:
#             raise RuntimeError("ESP32 not connected")

#         try:
#             print(f"DEBUG: Sending byte 0x{byte_val:02x} to port {self.esp32_port}")
#             self.serial_connection.write(bytes([byte_val]))
#             self.serial_connection.flush()
#             print(f"DEBUG: Byte sent successfully")
#         except Exception as e:
#             print(f"DEBUG: Send failed: {e}")
#             raise RuntimeError(f"Failed to send byte: {str(e)}")

#     def _send_bytes(self, byte_list: list):
#         """Send multiple bytes to ESP32 with debug."""
#         if not self.serial_connection:
#             raise RuntimeError("ESP32 not connected")

#         try:
#             print(f"DEBUG: Sending bytes {[hex(b) for b in byte_list]} to port {self.esp32_port}")
#             self.serial_connection.write(bytes(byte_list))
#             self.serial_connection.flush()
#             print(f"DEBUG: Bytes sent successfully")
#         except Exception as e:
#             print(f"DEBUG: Send failed: {e}")
#             raise RuntimeError(f"Failed to send bytes: {str(e)}")

#     def _read_bytes(self, expected_length: int, timeout: float = 2.0) -> Optional[bytes]:
#         """Read specified number of bytes from ESP32."""
#         if not self.serial_connection:
#             return None

#         start_time = time.time()
#         data = bytearray()

#         while len(data) < expected_length and time.time() - start_time < timeout:
#             if self.serial_connection.in_waiting > 0:
#                 available = min(expected_length - len(data), self.serial_connection.in_waiting)
#                 chunk = self.serial_connection.read(available)
#                 data.extend(chunk)
#                 print(f"DEBUG: Read {len(chunk)} bytes: {[hex(b) for b in chunk]}")
#             else:
#                 time.sleep(0.01)

#         if len(data) == expected_length:
#             print(f"DEBUG: Successfully read {len(data)} bytes")
#             return bytes(data)
#         else:
#             print(f"DEBUG: Read timeout - got {len(data)}/{expected_length} bytes")
#             return None

#     def _read_status_response(self, timeout: float = 2.0) -> Optional[dict]:
#         """Read 5-byte status response from ESP32."""
#         print(f"DEBUG: Waiting for 5-byte status response...")
#         data = self._read_bytes(5, timeout)
#         if not data or len(data) != 5:
#             print(f"DEBUG: Status response failed - got {len(data) if data else 0}/5 bytes")
#             return None

#         try:
#             status_code = data[0]
#             temp_raw = struct.unpack('>h', data[1:3])[0]
#             temperature = temp_raw / 10.0
#             hum_raw = struct.unpack('>H', data[3:5])[0]
#             humidity = hum_raw / 10.0

#             result = {
#                 'status_code': status_code,
#                 'temperature': temperature,
#                 'humidity': humidity,
#                 'led_on': status_code in [self.RESPONSE_STATUS_ON, self.RESPONSE_ACK_ON]
#             }

#             print(f"DEBUG: Status response - Code: 0x{status_code:02x}, LED: {result['led_on']}, T: {temperature:.1f}°C")
#             return result
#         except Exception as e:
#             print(f"Failed to parse status response: {e}")
#             return None

#     def _read_sync_response(self, timeout: float = 5.0) -> Optional[dict]:
#         """Read 7-byte sync response from ESP32."""
#         print(f"DEBUG: Waiting for 7-byte sync response...")
#         data = self._read_bytes(7, timeout)
#         if not data or len(data) != 7:
#             print(f"DEBUG: Sync response failed - got {len(data) if data else 0}/7 bytes")
#             return None

#         try:
#             if data[0] != self.RESPONSE_SYNC_COMPLETE:
#                 print(f"Invalid sync response header: {data[0]:02x}")
#                 return None

#             timing_ms = struct.unpack('>H', data[1:3])[0]
#             temp_raw = struct.unpack('>h', data[3:5])[0]
#             temperature = temp_raw / 10.0
#             hum_raw = struct.unpack('>H', data[5:7])[0]
#             humidity = hum_raw / 10.0

#             result = {
#                 'timing_ms': timing_ms,
#                 'temperature': temperature,
#                 'humidity': humidity
#             }

#             print(f"DEBUG: Sync response - Timing: {timing_ms}ms, T: {temperature:.1f}°C")
#             return result
#         except Exception as e:
#             print(f"Failed to parse sync response: {e}")
#             return None

#     def _wait_for_ack(self, expected_response: int, timeout: float = 1.0) -> bool:
#         """Wait for specific acknowledgment response."""
#         print(f"DEBUG: Waiting for ACK: 0x{expected_response:02x}")
#         start_time = time.time()

#         while time.time() - start_time < timeout:
#             if self.serial_connection.in_waiting > 0:
#                 response = self.serial_connection.read(1)[0]
#                 print(f"DEBUG: Got ACK response: 0x{response:02x}")
#                 if response == expected_response:
#                     return True
#                 elif response == self.RESPONSE_ERROR:
#                     raise RuntimeError("ESP32 reported error")
#             time.sleep(0.01)

#         print(f"DEBUG: ACK timeout after {timeout}s")
#         return False

#     # =========================================================================
#     # ESP32 CONTROL METHODS - SIMPLIFIED FOR DEBUGGING
#     # =========================================================================

#     def set_led_power(self, power: int) -> bool:
#         """Set LED power level (0-100%)."""
#         if not 0 <= power <= 100:
#             raise ValueError("Power must be between 0 and 100")

#         try:
#             self._send_bytes([self.CMD_SET_LED_POWER, power])

#             if self._wait_for_ack(self.RESPONSE_ACK_ON):
#                 self.led_power = power
#                 print(f"LED power set to {power}%")
#                 return True
#             else:
#                 print(f"DEBUG: No ACK for LED power setting")
#                 # Assume success anyway for debugging
#                 self.led_power = power
#                 return True

#         except Exception as e:
#             print(f"DEBUG: LED power setting failed: {e}")
#             raise RuntimeError(f"Failed to set LED power: {str(e)}")

#     def led_on(self) -> bool:
#         """Turn LED on - SIMPLIFIED for debugging."""
#         try:
#             print("DEBUG: === LED ON COMMAND ===")
#             self._send_byte(self.CMD_LED_ON)
#             print("DEBUG: LED ON command sent, waiting for response...")

#             # Wait longer for response due to ESP32 stabilization delay
#             response = self._read_status_response(timeout=5.0)

#             if response:
#                 led_is_on = response['led_on']
#                 print(f"DEBUG: LED response received - LED state: {led_is_on}")

#                 if led_is_on:
#                     self.led_on_state = True
#                     self.led_status_changed.emit(True, self.led_power)
#                     print("DEBUG: LED turned on successfully!")
#                     return True
#                 else:
#                     print("DEBUG: ESP32 reports LED is still off")
#                     return False
#             else:
#                 print("DEBUG: No response received from ESP32")
#                 # For debugging, assume it worked
#                 self.led_on_state = True
#                 self.led_status_changed.emit(True, self.led_power)
#                 return True

#         except Exception as e:
#             print(f"DEBUG: LED ON failed with exception: {e}")
#             raise RuntimeError(f"Failed to turn LED on: {str(e)}")

#     def led_off(self) -> bool:
#         """Turn LED off - SIMPLIFIED for debugging."""
#         try:
#             print("DEBUG: === LED OFF COMMAND ===")
#             self._send_byte(self.CMD_LED_OFF)
#             print("DEBUG: LED OFF command sent, waiting for response...")

#             response = self._read_status_response(timeout=3.0)

#             if response:
#                 led_is_on = response['led_on']
#                 print(f"DEBUG: LED response received - LED state: {led_is_on}")

#                 if not led_is_on:
#                     self.led_on_state = False
#                     self.led_status_changed.emit(False, 0)
#                     print("DEBUG: LED turned off successfully!")
#                     return True
#                 else:
#                     print("DEBUG: ESP32 reports LED is still on")
#                     return False
#             else:
#                 print("DEBUG: No response received from ESP32")
#                 # For debugging, assume it worked
#                 self.led_on_state = False
#                 self.led_status_changed.emit(False, 0)
#                 return True

#         except Exception as e:
#             print(f"DEBUG: LED OFF failed with exception: {e}")
#             raise RuntimeError(f"Failed to turn LED off: {str(e)}")

#     def read_sensors(self) -> Tuple[float, float]:
#         """Read temperature and humidity from DHT22 sensor."""
#         try:
#             print("DEBUG: === READ SENSORS ===")
#             self._send_byte(self.CMD_STATUS)
#             response = self._read_status_response()

#             if response:
#                 temperature = response['temperature']
#                 humidity = response['humidity']
#                 self.sensor_data_received.emit(temperature, humidity)
#                 print(f"DEBUG: Sensors - T: {temperature:.1f}°C, H: {humidity:.1f}%")
#                 return temperature, humidity
#             else:
#                 raise RuntimeError("No response from ESP32 sensors")

#         except Exception as e:
#             raise RuntimeError(f"Failed to read sensors: {str(e)}")

#     def synchronize_capture(self, led_duration_ms: int = None) -> dict:
#         """Synchronize LED flash with frame capture."""
#         try:
#             print("DEBUG: === SYNC CAPTURE ===")
#             esp32_time_start = time.time()

#             # Send sync capture command
#             self._send_byte(self.CMD_SYNC_CAPTURE)

#             # Read sync response
#             response = self._read_sync_response()
#             esp32_time_end = time.time()

#             if response:
#                 # Build timing info compatible with the data manager
#                 timing_info = {
#                     "python_time_start": esp32_time_start,
#                     "python_time_end": esp32_time_end,
#                     "esp32_time_start": esp32_time_start,  # Approximate
#                     "esp32_time_end": esp32_time_end,      # Approximate
#                     "led_duration_actual": response['timing_ms'],
#                     "led_power_actual": self.led_power,
#                     "temperature": response['temperature'],
#                     "humidity": response['humidity'],
#                     "sync_timing_ms": response['timing_ms']
#                 }

#                 print(f"Sync capture: {response['timing_ms']}ms, T={response['temperature']:.1f}°C")
#                 return timing_info
#             else:
#                 raise RuntimeError("No sync response from ESP32")

#         except Exception as e:
#             raise RuntimeError(f"Sync capture failed: {str(e)}")

#     def set_timing(self, stabilization_ms: int = 300, delay_ms: int = 10) -> bool:
#         """Set LED stabilization and trigger delay timing."""
#         try:
#             # Pack timing values as 16-bit big-endian
#             stab_bytes = struct.pack('>H', stabilization_ms)
#             delay_bytes = struct.pack('>H', delay_ms)

#             command = [self.CMD_SET_TIMING] + list(stab_bytes) + list(delay_bytes)
#             self._send_bytes(command)

#             if self._wait_for_ack(self.RESPONSE_TIMING_SET):
#                 self.led_stabilization_ms = stabilization_ms
#                 self.trigger_delay_ms = delay_ms
#                 print(f"Timing set: stabilization={stabilization_ms}ms, delay={delay_ms}ms")
#                 return True
#             else:
#                 print("DEBUG: No ACK for timing setting, assuming success")
#                 self.led_stabilization_ms = stabilization_ms
#                 self.trigger_delay_ms = delay_ms
#                 return True

#         except Exception as e:
#             raise RuntimeError(f"Failed to set timing: {str(e)}")

#     def set_camera_type(self, camera_type: int = None) -> bool:
#         """Set camera type (1=HIK_GIGE, 2=USB_GENERIC)."""
#         if camera_type is None:
#             camera_type = self.CAMERA_TYPE_HIK_GIGE

#         try:
#             self._send_bytes([self.CMD_SET_CAMERA_TYPE, camera_type])

#             if self._wait_for_ack(self.RESPONSE_ACK_ON):
#                 print(f"Camera type set to {camera_type}")
#                 return True
#             else:
#                 print("DEBUG: No ACK for camera type setting, assuming success")
#                 return True

#         except Exception as e:
#             raise RuntimeError(f"Failed to set camera type: {str(e)}")

#     def get_status(self) -> dict:
#         """Get ESP32 status information."""
#         try:
#             self._send_byte(self.CMD_STATUS)
#             response = self._read_status_response()

#             if response:
#                 return {
#                     "connected": True,
#                     "led_on": response['led_on'],
#                     "led_power": self.led_power,
#                     "temperature": response['temperature'],
#                     "humidity": response['humidity'],
#                     "led_stabilization_ms": self.led_stabilization_ms,
#                     "trigger_delay_ms": self.trigger_delay_ms,
#                     "firmware_version": "v3.1_LED_FIX",
#                     "port": self.esp32_port
#                 }
#             else:
#                 raise RuntimeError("No status response from ESP32")

#         except Exception as e:
#             raise RuntimeError(f"Failed to get status: {str(e)}")

#     # =========================================================================
#     # TEST METHODS
#     # =========================================================================

#     def test_led_sequence(self) -> bool:
#         """Test LED sequence for recording validation."""
#         try:
#             print("Testing LED sequence...")

#             # Test basic LED control
#             self.led_on()
#             time.sleep(0.5)
#             self.led_off()
#             time.sleep(0.2)

#             # Test sync capture
#             self.synchronize_capture()

#             print("LED sequence test passed")
#             return True
#         except Exception as e:
#             print(f"LED sequence test failed: {e}")
#             return False

#     def test_timing(self) -> dict:
#         """Test timing accuracy between Python and ESP32."""
#         try:
#             start_time = time.time()
#             timing_info = self.synchronize_capture()
#             end_time = time.time()

#             result = {
#                 "python_start": start_time,
#                 "python_end": end_time,
#                 "esp32_timing_ms": timing_info.get('sync_timing_ms', 0),
#                 "round_trip_time": end_time - start_time,
#                 "led_stabilization_ms": self.led_stabilization_ms,
#                 "trigger_delay_ms": self.trigger_delay_ms
#             }

#             print(f"Timing test: round-trip={result['round_trip_time']*1000:.1f}ms")
#             return result
#         except Exception as e:
#             raise RuntimeError(f"Timing test failed: {str(e)}")

#     def flash_led(self, duration_ms: int = 100) -> bool:
#         """Flash LED using sync capture (duration ignored - firmware controlled)."""
#         try:
#             self.synchronize_capture()
#             return True
#         except Exception as e:
#             print(f"LED flash failed: {e}")
#             return False
# File: src/napari_timelapse_capture/_esp32_controller.py
# """ESP32 controller with robust serial communication and verified LED state management
# for reliable 72-hour timelapse recordings with Day/Night phase support."""

# import serial
# import time
# import struct
# import threading
# import logging
# from typing import Tuple, Optional
# from qtpy.QtCore import QObject

# # ✅ FIX: pyqtSignal Import with try/except
# try:
#     from qtpy.QtCore import pyqtSignal
# except ImportError:
#     from qtpy.QtCore import Signal as pyqtSignal

# # Setup logging instead of print statements
# logger = logging.getLogger(__name__)


# class ESP32Controller(QObject):
#     """Robust ESP32 controller with verified LED switching and retry logic for long-term recordings."""

#     # Command bytes (matching ESP32 firmware)
#     CMD_LED_ON = 0x01
#     CMD_LED_OFF = 0x00
#     CMD_STATUS = 0x02
#     CMD_SYNC_CAPTURE = 0x0C
#     CMD_SET_LED_POWER = 0x10
#     CMD_SET_TIMING = 0x11
#     CMD_SET_CAMERA_TYPE = 0x13

#     # Dual LED Commands (matching ESP32 firmware v4.0)
#     CMD_SELECT_LED_IR = 0x20
#     CMD_SELECT_LED_WHITE = 0x21
#     CMD_LED_DUAL_OFF = 0x22
#     CMD_GET_LED_STATUS = 0x23

#     # Response bytes (matching ESP32 firmware)
#     RESPONSE_SYNC_COMPLETE = 0x1B
#     RESPONSE_TIMING_SET = 0x21
#     RESPONSE_ACK_ON = 0x01
#     RESPONSE_ACK_OFF = 0x02
#     RESPONSE_STATUS_ON = 0x11
#     RESPONSE_STATUS_OFF = 0x10
#     RESPONSE_ERROR = 0xFF

#     # LED Selection Response bytes
#     RESPONSE_LED_IR_SELECTED = 0x30
#     RESPONSE_LED_WHITE_SELECTED = 0x31
#     RESPONSE_LED_STATUS = 0x32

#     # Camera types
#     CAMERA_TYPE_HIK_GIGE = 1
#     CAMERA_TYPE_USB_GENERIC = 2

#     # LED Types
#     LED_TYPE_IR = 0
#     LED_TYPE_WHITE = 1

#     # Signals
#     sensor_data_received = pyqtSignal(float, float)  # temperature, humidity
#     led_status_changed = pyqtSignal(bool, int)  # on/off, power_level
#     connection_status_changed = pyqtSignal(bool)  # connected/disconnected

#     def __init__(self, imswitch_main_controller=None):
#         super().__init__()
#         self.imswitch_main = imswitch_main_controller
#         self.serial_connection = None
#         self.connected = False
#         self.led_power = 100  # Default to 100% as in firmware
#         self.led_on_state = False
#         self.led_stabilization_ms = 500
#         self.trigger_delay_ms = 10

#         # Dual LED state tracking
#         self.current_led_type = 'ir'  # Default to IR for backward compatibility
#         self.led_ir_state = False
#         self.led_white_state = False

#         # ✅ CRITICAL: Thread safety for serial operations
#         self._comm_lock = threading.Lock()

#         # ✅ CRITICAL: Connection health tracking
#         self._last_successful_command = 0
#         self._consecutive_failures = 0
#         self._max_failures_before_reconnect = 3

#         # Try to get port from ImSwitch config, then auto-detect
#         self.esp32_port = self._get_esp32_port()

#     def _get_esp32_port(self) -> Optional[str]:
#         """Get ESP32 port from ImSwitch config or auto-detect."""
#         # First try: ImSwitch configuration
#         if self.imswitch_main is not None:
#             try:
#                 config = getattr(self.imswitch_main, '_config', None)
#                 if config and 'rs232devices' in config:
#                     esp32_config = config['rs232devices'].get('ESP32', {})
#                     port = esp32_config.get('managerProperties', {}).get('serialport')
#                     if port:
#                         logger.info(f"Found ESP32 port in ImSwitch config: {port}")
#                         return port
#             except Exception as e:
#                 logger.warning(f"Could not read ESP32 port from ImSwitch config: {e}")

#         # Second try: Auto-detect
#         return self._find_esp32_port()

#     def _find_esp32_port(self) -> Optional[str]:
#         """Auto-detect ESP32 port."""
#         import serial.tools.list_ports

#         logger.info("Auto-detecting ESP32 port...")
#         ports = serial.tools.list_ports.comports()

#         for port in ports:
#             logger.debug(f"Checking port: {port.device} - {port.description}")
#             if any(identifier in port.description.lower() for identifier in
#                 ['esp32', 'cp210x', 'ch340', 'ftdi', 'silicon labs']):
#                 logger.info(f"Found potential ESP32 port: {port.device}")
#                 return port.device

#         logger.warning("No ESP32 port auto-detected")
#         return None

#     def connect(self) -> bool:
#         """Connect to ESP32 via direct serial connection with robust error handling."""
#         if not self.esp32_port:
#             raise RuntimeError("No ESP32 port configured or detected")

#         with self._comm_lock:
#             try:
#                 logger.info(f"Connecting to ESP32 on port: {self.esp32_port}")

#                 # Close any existing connection
#                 if self.serial_connection:
#                     try:
#                         self.serial_connection.close()
#                     except:
#                         pass
#                     self.serial_connection = None

#                 self.serial_connection = serial.Serial(
#                     port=self.esp32_port,
#                     baudrate=115200,
#                     timeout=2.0,
#                     write_timeout=1.0
#                 )

#                 # Wait for ESP32 to initialize
#                 time.sleep(2.0)
#                 self.serial_connection.reset_input_buffer()

#                 # ✅ CRITICAL: Robust connection test with retries
#                 for attempt in range(3):
#                     try:
#                         if self._test_connection():
#                             self.connected = True
#                             self._consecutive_failures = 0
#                             self._last_successful_command = time.time()
#                             self.connection_status_changed.emit(True)
#                             logger.info("ESP32 connected successfully")

#                             # Initialize LED state after successful connection
#                             self._initialize_led_state()
#                             return True
#                     except Exception as e:
#                         logger.warning(f"Connection test attempt {attempt + 1} failed: {e}")
#                         if attempt < 2:
#                             time.sleep(1.0)

#                 # All attempts failed
#                 self.serial_connection.close()
#                 self.serial_connection = None
#                 raise RuntimeError("ESP32 not responding after 3 attempts")

#             except Exception as e:
#                 if self.serial_connection:
#                     try:
#                         self.serial_connection.close()
#                     except:
#                         pass
#                     self.serial_connection = None
#                 raise RuntimeError(f"Failed to connect to ESP32: {str(e)}")

#     def _initialize_led_state(self):
#         """Initialize LED state after connection with verification."""
#         try:
#             # Get current LED status from ESP32
#             led_status = self.get_led_status()
#             self.current_led_type = led_status.get('current_led_type', 'ir')
#             self.led_ir_state = led_status.get('ir_led_state', False)
#             self.led_white_state = led_status.get('white_led_state', False)
#             self.led_power = led_status.get('led_power_percent', 100)

#             logger.info(f"LED state initialized: Current={self.current_led_type}, "
#                        f"IR={self.led_ir_state}, White={self.led_white_state}, Power={self.led_power}%")
#         except Exception as e:
#             logger.error(f"Could not initialize LED state: {e}")
#             # Use defaults but don't fail connection
#             self.current_led_type = 'ir'
#             self.led_ir_state = False
#             self.led_white_state = False

#     def _test_connection(self) -> bool:
#         """Test ESP32 connection with status command."""
#         try:
#             self._send_byte(self.CMD_STATUS)
#             response = self._read_status_response(timeout=3.0)
#             return response is not None
#         except Exception as e:
#             logger.debug(f"Connection test failed: {e}")
#             return False

#     def disconnect(self):
#         """Disconnect from ESP32 with cleanup."""
#         with self._comm_lock:
#             if self.serial_connection:
#                 try:
#                     # Try to turn off all LEDs before disconnecting
#                     self.turn_off_all_leds()
#                 except:
#                     pass
#                 try:
#                     self.serial_connection.close()
#                 except:
#                     pass
#                 finally:
#                     self.serial_connection = None

#             self.connected = False
#             self.led_ir_state = False
#             self.led_white_state = False
#             self._consecutive_failures = 0
#             self.connection_status_changed.emit(False)
#             logger.info("ESP32 disconnected")

#     def is_connected(self, force_check: bool = False) -> bool:
#         """Check connection status with optional health verification."""
#         if not self.connected or not self.serial_connection:
#             return False

#         if force_check:
#             try:
#                 with self._comm_lock:
#                     ok = self._test_connection()
#                     if ok:
#                         self._consecutive_failures = 0
#                         self._last_successful_command = time.time()
#                     else:
#                         self._consecutive_failures += 1
#                         if self._consecutive_failures >= self._max_failures_before_reconnect:
#                             logger.warning(f"Connection health check failed {self._consecutive_failures} times")
#                             self.connected = False
#                             self.connection_status_changed.emit(False)
#                     return ok
#             except:
#                 self._consecutive_failures += 1
#                 self.connected = False
#                 self.connection_status_changed.emit(False)
#                 return False
#         return True

#     # =========================================================================
#     # ✅ ROBUST SERIAL COMMUNICATION METHODS
#     # =========================================================================

#     def _send_command_with_retry(self, command_byte: int, expected_response: int = None,
#                                 max_retries: int = 3, verify_response: bool = True) -> bool:
#         """Send command with retry logic and optional response verification."""
#         last_exception = None

#         for attempt in range(max_retries):
#             try:
#                 self._send_byte(command_byte)

#                 if verify_response and expected_response:
#                     if self._wait_for_ack(expected_response, timeout=2.0 * (attempt + 1)):
#                         self._consecutive_failures = 0
#                         self._last_successful_command = time.time()
#                         return True
#                     else:
#                         raise RuntimeError(f"No acknowledgment for command 0x{command_byte:02x}")
#                 else:
#                     # Command sent successfully, no response expected
#                     self._consecutive_failures = 0
#                     self._last_successful_command = time.time()
#                     return True

#             except Exception as e:
#                 last_exception = e
#                 self._consecutive_failures += 1
#                 logger.warning(f"Command 0x{command_byte:02x} attempt {attempt + 1} failed: {e}")

#                 if attempt < max_retries - 1:
#                     time.sleep(0.1 * (2 ** attempt))  # Exponential backoff

#         # All retries failed
#         logger.error(f"Command 0x{command_byte:02x} failed after {max_retries} attempts")
#         if self._consecutive_failures >= self._max_failures_before_reconnect:
#             self.connected = False
#             self.connection_status_changed.emit(False)

#         raise RuntimeError(f"Command failed after {max_retries} attempts: {last_exception}")

#     def _send_byte(self, byte_val: int):
#         """Send single byte to ESP32 with validation."""
#         if not self.serial_connection:
#             raise RuntimeError("ESP32 not connected")

#         try:
#             logger.debug(f"Sending byte 0x{byte_val:02x} to port {self.esp32_port}")
#             self.serial_connection.write(bytes([byte_val]))
#             self.serial_connection.flush()
#             logger.debug(f"Byte sent successfully")
#         except Exception as e:
#             raise RuntimeError(f"Failed to send byte: {str(e)}")

#     def _send_bytes(self, byte_list: list):
#         """Send multiple bytes to ESP32 with validation."""
#         if not self.serial_connection:
#             raise RuntimeError("ESP32 not connected")

#         try:
#             logger.debug(f"Sending bytes {[hex(b) for b in byte_list]} to port {self.esp32_port}")
#             self.serial_connection.write(bytes(byte_list))
#             self.serial_connection.flush()
#             logger.debug(f"Bytes sent successfully")
#         except Exception as e:
#             raise RuntimeError(f"Failed to send bytes: {str(e)}")

#     def _read_bytes(self, expected_length: int, timeout: float = 2.0) -> Optional[bytes]:
#         """Read specified number of bytes from ESP32."""
#         if not self.serial_connection:
#             return None

#         start_time = time.time()
#         data = bytearray()

#         while len(data) < expected_length and time.time() - start_time < timeout:
#             if self.serial_connection.in_waiting > 0:
#                 available = min(expected_length - len(data), self.serial_connection.in_waiting)
#                 chunk = self.serial_connection.read(available)
#                 data.extend(chunk)
#                 logger.debug(f"Read {len(chunk)} bytes: {[hex(b) for b in chunk]}")
#             else:
#                 time.sleep(0.01)

#         if len(data) == expected_length:
#             logger.debug(f"Successfully read {len(data)} bytes")
#             return bytes(data)
#         else:
#             logger.debug(f"Read timeout - got {len(data)}/{expected_length} bytes")
#             return None

#     def _read_status_response(self, timeout: float = 2.0) -> Optional[dict]:
#         """Read 5-byte status response from ESP32."""
#         logger.debug(f"Waiting for 5-byte status response...")
#         data = self._read_bytes(5, timeout)
#         if not data or len(data) != 5:
#             logger.debug(f"Status response failed - got {len(data) if data else 0}/5 bytes")
#             return None

#         try:
#             status_code = data[0]
#             temp_raw = struct.unpack('>h', data[1:3])[0]
#             temperature = temp_raw / 10.0
#             hum_raw = struct.unpack('>H', data[3:5])[0]
#             humidity = hum_raw / 10.0

#             result = {
#                 'status_code': status_code,
#                 'temperature': temperature,
#                 'humidity': humidity,
#                 'led_on': status_code in [self.RESPONSE_STATUS_ON, self.RESPONSE_ACK_ON]
#             }

#             logger.debug(f"Status response - Code: 0x{status_code:02x}, LED: {result['led_on']}, T: {temperature:.1f}°C")
#             return result
#         except Exception as e:
#             logger.error(f"Failed to parse status response: {e}")
#             return None

#     def _read_sync_response(self, timeout: float = 5.0) -> Optional[dict]:
#         """Read 7-byte sync response from ESP32."""
#         logger.debug(f"Waiting for 7-byte sync response...")
#         data = self._read_bytes(7, timeout)
#         if not data or len(data) != 7:
#             logger.debug(f"Sync response failed - got {len(data) if data else 0}/7 bytes")
#             return None

#         try:
#             if data[0] != self.RESPONSE_SYNC_COMPLETE:
#                 logger.error(f"Invalid sync response header: {data[0]:02x}")
#                 return None

#             timing_ms = struct.unpack('>H', data[1:3])[0]
#             temp_raw = struct.unpack('>h', data[3:5])[0]
#             temperature = temp_raw / 10.0
#             hum_raw = struct.unpack('>H', data[5:7])[0]
#             humidity = hum_raw / 10.0

#             result = {
#                 'timing_ms': timing_ms,
#                 'temperature': temperature,
#                 'humidity': humidity
#             }

#             logger.debug(f"Sync response - Timing: {timing_ms}ms, T: {temperature:.1f}°C")
#             return result
#         except Exception as e:
#             logger.error(f"Failed to parse sync response: {e}")
#             return None

#     def _wait_for_ack(self, expected_response: int, timeout: float = 1.0) -> bool:
#         """Wait for specific acknowledgment response."""
#         logger.debug(f"Waiting for ACK: 0x{expected_response:02x}")
#         start_time = time.time()

#         while time.time() - start_time < timeout:
#             if self.serial_connection.in_waiting > 0:
#                 response = self.serial_connection.read(1)[0]
#                 logger.debug(f"Got ACK response: 0x{response:02x}")
#                 if response == expected_response:
#                     return True
#                 elif response == self.RESPONSE_ERROR:
#                     raise RuntimeError("ESP32 reported error")
#             time.sleep(0.01)

#         logger.debug(f"ACK timeout after {timeout}s")
#         return False

#     # =========================================================================
#     # ✅ VERIFIED LED SELECTION AND CONTROL METHODS
#     # =========================================================================

#     def select_led_ir(self) -> bool:
#         """Select IR LED with state verification - CRITICAL for phase accuracy."""
#         with self._comm_lock:
#             try:
#                 logger.info("Selecting IR LED...")

#                 # Send command with retry logic
#                 success = self._send_command_with_retry(
#                     self.CMD_SELECT_LED_IR,
#                     self.RESPONSE_LED_IR_SELECTED,
#                     max_retries=3
#                 )

#                 if success:
#                     # ✅ CRITICAL: Verify the switch actually worked
#                     time.sleep(0.1)  # Small delay for LED switch
#                     status = self.get_led_status()

#                     if status['current_led_type'] == 'ir':
#                         self.current_led_type = 'ir'
#                         logger.info("IR LED selected and verified")
#                         return True
#                     else:
#                         raise RuntimeError(f"LED verification failed: expected IR, got {status['current_led_type']}")
#                 else:
#                     raise RuntimeError("No acknowledgment for IR LED selection")

#             except Exception as e:
#                 logger.error(f"Failed to select IR LED: {e}")
#                 raise RuntimeError(f"Failed to select IR LED: {str(e)}")

#     def select_led_white(self) -> bool:
#         """Select White LED with state verification - CRITICAL for phase accuracy."""
#         with self._comm_lock:
#             try:
#                 logger.info("Selecting White LED...")

#                 # Send command with retry logic
#                 success = self._send_command_with_retry(
#                     self.CMD_SELECT_LED_WHITE,
#                     self.RESPONSE_LED_WHITE_SELECTED,
#                     max_retries=3
#                 )

#                 if success:
#                     # ✅ CRITICAL: Verify the switch actually worked
#                     time.sleep(0.1)  # Small delay for LED switch
#                     status = self.get_led_status()

#                     if status['current_led_type'] == 'white':
#                         self.current_led_type = 'white'
#                         logger.info("White LED selected and verified")
#                         return True
#                     else:
#                         raise RuntimeError(f"LED verification failed: expected white, got {status['current_led_type']}")
#                 else:
#                     raise RuntimeError("No acknowledgment for White LED selection")

#             except Exception as e:
#                 logger.error(f"Failed to select White LED: {e}")
#                 raise RuntimeError(f"Failed to select White LED: {str(e)}")

#     def select_led_type(self, led_type: str) -> bool:
#         """Select LED type by string name with verification."""
#         led_type_lower = led_type.lower()
#         if led_type_lower in ['ir', 'infrared', 'night']:
#             return self.select_led_ir()
#         elif led_type_lower in ['white', 'day', 'cob']:
#             return self.select_led_white()
#         else:
#             raise ValueError(f"Unknown LED type: {led_type}. Use 'ir', 'infrared', 'night', 'white', 'day', or 'cob'")

#     def turn_off_all_leds(self) -> bool:
#         """Turn off both IR and White LEDs with verification."""
#         with self._comm_lock:
#             try:
#                 logger.info("Turning off all LEDs...")

#                 success = self._send_command_with_retry(
#                     self.CMD_LED_DUAL_OFF,
#                     self.RESPONSE_ACK_OFF,
#                     max_retries=3
#                 )

#                 if success:
#                     self.led_ir_state = False
#                     self.led_white_state = False
#                     self.led_on_state = False
#                     logger.info("All LEDs turned off successfully")
#                     self.led_status_changed.emit(False, 0)
#                     return True
#                 else:
#                     raise RuntimeError("No acknowledgment for LED dual off command")

#             except Exception as e:
#                 logger.error(f"Failed to turn off all LEDs: {e}")
#                 raise RuntimeError(f"Failed to turn off all LEDs: {str(e)}")

#     def get_led_status(self) -> dict:
#         """Get detailed LED status from ESP32 with fallback."""
#         with self._comm_lock:
#             try:
#                 logger.debug("Getting LED status...")
#                 self._send_byte(self.CMD_GET_LED_STATUS)

#                 # Read 5-byte LED status response
#                 data = self._read_bytes(5, timeout=3.0)
#                 if not data or len(data) != 5:
#                     logger.warning(f"LED status response failed - got {len(data) if data else 0}/5 bytes")
#                     return self._get_fallback_led_status()

#                 try:
#                     if data[0] != self.RESPONSE_LED_STATUS:
#                         logger.warning(f"Invalid LED status response header: {data[0]:02x}")
#                         return self._get_fallback_led_status()

#                     current_type = 'ir' if data[1] == 0 else 'white'
#                     ir_state = bool(data[2])
#                     white_state = bool(data[3])
#                     power_percent = data[4]

#                     # Update local state
#                     self.current_led_type = current_type
#                     self.led_ir_state = ir_state
#                     self.led_white_state = white_state
#                     self.led_power = power_percent
#                     self.led_on_state = ir_state or white_state

#                     status = {
#                         'current_led_type': current_type,
#                         'ir_led_state': ir_state,
#                         'white_led_state': white_state,
#                         'led_power_percent': power_percent,
#                         'any_led_on': ir_state or white_state
#                     }

#                     logger.debug(f"LED Status - Current: {current_type}, IR: {ir_state}, White: {white_state}, Power: {power_percent}%")
#                     return status

#                 except Exception as e:
#                     logger.error(f"Failed to parse LED status response: {e}")
#                     return self._get_fallback_led_status()

#             except Exception as e:
#                 logger.error(f"Get LED status failed: {e}")
#                 return self._get_fallback_led_status()

#     def _get_fallback_led_status(self) -> dict:
#         """Fallback LED status based on local state."""
#         return {
#             'current_led_type': self.current_led_type,
#             'ir_led_state': self.led_ir_state,
#             'white_led_state': self.led_white_state,
#             'led_power_percent': self.led_power,
#             'any_led_on': self.led_ir_state or self.led_white_state
#         }

#     # =========================================================================
#     # ✅ ROBUST ESP32 CONTROL METHODS
#     # =========================================================================

#     def set_led_power(self, power: int) -> bool:
#         """Set LED power level with verification."""
#         if not 0 <= power <= 100:
#             raise ValueError("Power must be between 0 and 100")

#         with self._comm_lock:
#             try:
#                 success = self._send_command_with_retry(
#                     self.CMD_SET_LED_POWER,
#                     expected_response=None,  # No specific response expected
#                     verify_response=False
#                 )

#                 if success:
#                     # Send power value
#                     self._send_byte(power)

#                     # Wait for acknowledgment
#                     if self._wait_for_ack(self.RESPONSE_ACK_ON, timeout=2.0):
#                         self.led_power = power
#                         logger.info(f"LED power set to {power}%")
#                         return True
#                     else:
#                         raise RuntimeError("No acknowledgment for LED power setting")
#                 else:
#                     raise RuntimeError("Failed to send LED power command")

#             except Exception as e:
#                 logger.error(f"LED power setting failed: {e}")
#                 raise RuntimeError(f"Failed to set LED power: {str(e)}")

#     def led_on(self) -> bool:
#         """Turn current LED on with state verification."""
#         with self._comm_lock:
#             try:
#                 logger.info(f"Turning {self.current_led_type.upper()} LED ON")
#                 self._send_byte(self.CMD_LED_ON)

#                 # Wait for response with stabilization time
#                 response = self._read_status_response(timeout=5.0)

#                 if response and response['led_on']:
#                     # Update state based on current LED type
#                     if self.current_led_type == 'ir':
#                         self.led_ir_state = True
#                     else:
#                         self.led_white_state = True

#                     self.led_on_state = True
#                     self.led_status_changed.emit(True, self.led_power)
#                     logger.info(f"{self.current_led_type.upper()} LED turned on successfully")
#                     return True
#                 else:
#                     raise RuntimeError("LED failed to turn on or no response")

#             except Exception as e:
#                 logger.error(f"LED ON failed: {e}")
#                 raise RuntimeError(f"Failed to turn LED on: {str(e)}")

#     def led_off(self) -> bool:
#         """Turn current LED off with state verification."""
#         with self._comm_lock:
#             try:
#                 logger.info(f"Turning {self.current_led_type.upper()} LED OFF")
#                 self._send_byte(self.CMD_LED_OFF)

#                 response = self._read_status_response(timeout=3.0)

#                 if response and not response['led_on']:
#                     # Update state based on current LED type
#                     if self.current_led_type == 'ir':
#                         self.led_ir_state = False
#                     else:
#                         self.led_white_state = False

#                     self.led_on_state = False
#                     self.led_status_changed.emit(False, 0)
#                     logger.info(f"{self.current_led_type.upper()} LED turned off successfully")
#                     return True
#                 else:
#                     raise RuntimeError("LED failed to turn off or no response")

#             except Exception as e:
#                 logger.error(f"LED OFF failed: {e}")
#                 raise RuntimeError(f"Failed to turn LED off: {str(e)}")

#     def read_sensors(self) -> Tuple[float, float]:
#         """Read temperature and humidity from DHT22 sensor."""
#         with self._comm_lock:
#             try:
#                 logger.debug("Reading sensors...")
#                 self._send_byte(self.CMD_STATUS)
#                 response = self._read_status_response()

#                 if response:
#                     temperature = response['temperature']
#                     humidity = response['humidity']
#                     self.sensor_data_received.emit(temperature, humidity)
#                     logger.debug(f"Sensors - T: {temperature:.1f}°C, H: {humidity:.1f}%")
#                     return temperature, humidity
#                 else:
#                     raise RuntimeError("No response from ESP32 sensors")

#             except Exception as e:
#                 raise RuntimeError(f"Failed to read sensors: {str(e)}")

#     def synchronize_capture_with_led(self, led_type: str = None, led_duration_ms: int = None) -> dict:
#         """Synchronize LED flash with frame capture - phase aware with verification."""
#         with self._comm_lock:
#             try:
#                 logger.info("Starting phase-aware sync capture...")
#                 logger.debug(f"Requested LED type: {led_type}")
#                 logger.debug(f"Current LED type: {self.current_led_type}")

#                 esp32_time_start = time.time()

#                 # Switch LED if requested and different from current
#                 if led_type and led_type.lower() != self.current_led_type:
#                     logger.info(f"Switching LED from {self.current_led_type} to {led_type}")
#                     self.select_led_type(led_type)
#                     time.sleep(0.1)  # Small delay for LED switch

#                 # Send sync capture command (uses currently selected LED)
#                 self._send_byte(self.CMD_SYNC_CAPTURE)

#                 # Read sync response
#                 response = self._read_sync_response()
#                 esp32_time_end = time.time()

#                 if response:
#                     # Build timing info compatible with the data manager
#                     timing_info = {
#                         "python_time_start": esp32_time_start,
#                         "python_time_end": esp32_time_end,
#                         "esp32_time_start": esp32_time_start,  # Approximate
#                         "esp32_time_end": esp32_time_end,      # Approximate
#                         "led_duration_actual": response['timing_ms'],
#                         "led_power_actual": self.led_power,
#                         "temperature": response['temperature'],
#                         "humidity": response['humidity'],
#                         "sync_timing_ms": response['timing_ms'],
#                         "led_type_used": self.current_led_type,
#                         "phase_aware_capture": True
#                     }

#                     logger.info(f"Phase-aware sync capture successful: {response['timing_ms']}ms, "
#                                f"{self.current_led_type.upper()} LED, T={response['temperature']:.1f}°C")
#                     return timing_info
#                 else:
#                     raise RuntimeError("No sync response from ESP32")

#             except Exception as e:
#                 raise RuntimeError(f"Phase-aware sync capture failed: {str(e)}")

#     def synchronize_capture(self, led_duration_ms: int = None) -> dict:
#         """Synchronize LED flash with frame capture - backward compatibility."""
#         return self.synchronize_capture_with_led(led_type=None, led_duration_ms=led_duration_ms)

#     def set_timing(self, stabilization_ms: int = 300, delay_ms: int = 10) -> bool:
#         """Set LED stabilization and trigger delay timing."""
#         with self._comm_lock:
#             try:
#                 # Pack timing values as 16-bit big-endian
#                 stab_bytes = struct.pack('>H', stabilization_ms)
#                 delay_bytes = struct.pack('>H', delay_ms)

#                 command = [self.CMD_SET_TIMING] + list(stab_bytes) + list(delay_bytes)
#                 self._send_bytes(command)

#                 if self._wait_for_ack(self.RESPONSE_TIMING_SET):
#                     self.led_stabilization_ms = stabilization_ms
#                     self.trigger_delay_ms = delay_ms
#                     logger.info(f"Timing set: stabilization={stabilization_ms}ms, delay={delay_ms}ms")
#                     return True
#                 else:
#                     raise RuntimeError("No acknowledgment for timing setting")

#             except Exception as e:
#                 raise RuntimeError(f"Failed to set timing: {str(e)}")

#     def set_camera_type(self, camera_type: int = None) -> bool:
#         """Set camera type (1=HIK_GIGE, 2=USB_GENERIC)."""
#         if camera_type is None:
#             camera_type = self.CAMERA_TYPE_HIK_GIGE

#         with self._comm_lock:
#             try:
#                 self._send_bytes([self.CMD_SET_CAMERA_TYPE, camera_type])

#                 if self._wait_for_ack(self.RESPONSE_ACK_ON):
#                     logger.info(f"Camera type set to {camera_type}")
#                     return True
#                 else:
#                     raise RuntimeError("No acknowledgment for camera type setting")

#             except Exception as e:
#                 raise RuntimeError(f"Failed to set camera type: {str(e)}")

#     def get_status(self) -> dict:
#         """Get ESP32 status information with dual LED support."""
#         with self._comm_lock:
#             try:
#                 self._send_byte(self.CMD_STATUS)
#                 response = self._read_status_response()

#                 if response:
#                     led_status = self.get_led_status()
#                     return {
#                         "connected": True,
#                         "led_on": response['led_on'],
#                         "led_power": self.led_power,
#                         "temperature": response['temperature'],
#                         "humidity": response['humidity'],
#                         "led_stabilization_ms": self.led_stabilization_ms,
#                         "trigger_delay_ms": self.trigger_delay_ms,
#                         "firmware_version": "v4.0_DUAL_LED_ROBUST",
#                         "port": self.esp32_port,
#                         "current_led_type": led_status['current_led_type'],
#                         "ir_led_state": led_status['ir_led_state'],
#                         "white_led_state": led_status['white_led_state'],
#                         "dual_led_capable": True,
#                         "consecutive_failures": self._consecutive_failures,
#                         "last_successful_command": self._last_successful_command
#                     }
#                 else:
#                     raise RuntimeError("No status response from ESP32")

#             except Exception as e:
#                 raise RuntimeError(f"Failed to get status: {str(e)}")

#     # =========================================================================
#     # ✅ ENHANCED TEST METHODS
#     # =========================================================================

#     def test_led_sequence(self) -> bool:
#         """Test LED sequence with verification."""
#         try:
#             logger.info("Testing dual LED sequence with verification...")

#             # Test IR LED
#             logger.info("Testing IR LED...")
#             self.select_led_ir()
#             self.led_on()
#             time.sleep(0.5)
#             self.led_off()
#             time.sleep(0.2)

#             # Test White LED
#             logger.info("Testing White LED...")
#             self.select_led_white()
#             self.led_on()
#             time.sleep(0.5)
#             self.led_off()
#             time.sleep(0.2)

#             # Test sync capture with both LEDs
#             logger.info("Testing sync capture with IR LED...")
#             self.select_led_ir()
#             self.synchronize_capture()

#             logger.info("Testing sync capture with White LED...")
#             self.select_led_white()
#             self.synchronize_capture()

#             # Return to default (IR)
#             self.select_led_ir()

#             logger.info("Dual LED sequence test passed with verification")
#             return True
#         except Exception as e:
#             logger.error(f"LED sequence test failed: {e}")
#             return False

#     def test_dual_led_switching(self) -> bool:
#         """Test dual LED switching with strict verification."""
#         try:
#             logger.info("Testing dual LED switching with verification...")

#             # Test switching between LEDs
#             original_led = self.current_led_type

#             # Test IR selection
#             self.select_led_ir()
#             ir_status = self.get_led_status()

#             # Test White selection
#             self.select_led_white()
#             white_status = self.get_led_status()

#             # Restore original
#             self.select_led_type(original_led)

#             success = (ir_status['current_led_type'] == 'ir' and
#                       white_status['current_led_type'] == 'white')

#             if success:
#                 logger.info("Dual LED switching test passed with verification")
#             else:
#                 logger.error("Dual LED switching test failed verification")
#                 logger.error(f"IR status: {ir_status}")
#                 logger.error(f"White status: {white_status}")

#             return success
#         except Exception as e:
#             logger.error(f"Dual LED switching test failed: {e}")
#             return False

#     def flash_led(self, duration_ms: int = 100) -> bool:
#         """Flash LED using sync capture."""
#         try:
#             self.synchronize_capture()
#             return True
#         except Exception as e:
#             logger.error(f"LED flash failed: {e}")
#             return False


"""ESP32 controller with robust serial communication, verified LED state management,
and LED calibration support for reliable 72-hour timelapse recordings with Day/Night phase support."""

import serial
import time
import struct
import threading
import logging
from typing import Tuple, Optional
from qtpy.QtCore import QObject

# ✅ FIX: pyqtSignal Import with try/except
try:
    from qtpy.QtCore import pyqtSignal
except ImportError:
    from qtpy.QtCore import Signal as pyqtSignal

# Setup logging instead of print statements
logger = logging.getLogger(__name__)


class ESP32Controller(QObject):
    """Robust ESP32 controller with verified LED switching, retry logic, and LED calibration
    support for long-term recordings."""

    # Command bytes (matching ESP32 firmware)
    CMD_LED_ON = 0x01
    CMD_LED_OFF = 0x00
    CMD_STATUS = 0x02
    CMD_SYNC_CAPTURE = 0x0C
    CMD_SET_LED_POWER = 0x10
    CMD_SET_TIMING = 0x11
    CMD_SET_CAMERA_TYPE = 0x13

    # Dual LED Commands (matching ESP32 firmware v4.0)
    CMD_SELECT_LED_IR = 0x20
    CMD_SELECT_LED_WHITE = 0x21
    CMD_LED_DUAL_OFF = 0x22
    CMD_GET_LED_STATUS = 0x23

    # Response bytes (matching ESP32 firmware)
    RESPONSE_SYNC_COMPLETE = 0x1B
    RESPONSE_TIMING_SET = 0x21
    RESPONSE_ACK_ON = 0x01
    RESPONSE_ACK_OFF = 0x02
    RESPONSE_STATUS_ON = 0x11
    RESPONSE_STATUS_OFF = 0x10
    RESPONSE_ERROR = 0xFF

    # LED Selection Response bytes
    RESPONSE_LED_IR_SELECTED = 0x30
    RESPONSE_LED_WHITE_SELECTED = 0x31
    RESPONSE_LED_STATUS = 0x32

    # Camera types
    CAMERA_TYPE_HIK_GIGE = 1
    CAMERA_TYPE_USB_GENERIC = 2

    # LED Types
    LED_TYPE_IR = 0
    LED_TYPE_WHITE = 1

    # Signals
    sensor_data_received = pyqtSignal(float, float)  # temperature, humidity
    led_status_changed = pyqtSignal(bool, int)  # on/off, power_level
    connection_status_changed = pyqtSignal(bool)  # connected/disconnected

    def __init__(self, imswitch_main_controller=None):
        super().__init__()
        self.imswitch_main = imswitch_main_controller
        self.serial_connection = None
        self.connected = False
        self.led_power = 100  # Default to 100% as in firmware
        self.led_on_state = False
        self.led_stabilization_ms = 500
        self.trigger_delay_ms = 10

        # Dual LED state tracking
        self.current_led_type = "ir"  # Default to IR for backward compatibility
        self.led_ir_state = False
        self.led_white_state = False

        # ✅ CRITICAL: Thread safety for serial operations
        self._comm_lock = threading.Lock()

        # ✅ CRITICAL: Connection health tracking
        self._last_successful_command = 0
        self._consecutive_failures = 0
        self._max_failures_before_reconnect = 3

        # ✅ NEW: LED Calibration support
        self.calibrated_powers = {}  # Store calibrated LED powers
        self.auto_apply_calibration = False  # Toggle for automatic application

        # Try to get port from ImSwitch config, then auto-detect
        self.esp32_port = self._get_esp32_port()

    def _get_esp32_port(self) -> Optional[str]:
        """Get ESP32 port from ImSwitch config or auto-detect."""
        # First try: ImSwitch configuration
        if self.imswitch_main is not None:
            try:
                config = getattr(self.imswitch_main, "_config", None)
                if config and "rs232devices" in config:
                    esp32_config = config["rs232devices"].get("ESP32", {})
                    port = esp32_config.get("managerProperties", {}).get("serialport")
                    if port:
                        logger.info(f"Found ESP32 port in ImSwitch config: {port}")
                        return port
            except Exception as e:
                logger.warning(f"Could not read ESP32 port from ImSwitch config: {e}")

        # Second try: Auto-detect
        return self._find_esp32_port()

    def _find_esp32_port(self) -> Optional[str]:
        """Auto-detect ESP32 port."""
        import serial.tools.list_ports

        logger.info("Auto-detecting ESP32 port...")
        ports = serial.tools.list_ports.comports()

        for port in ports:
            logger.debug(f"Checking port: {port.device} - {port.description}")
            if any(
                identifier in port.description.lower()
                for identifier in ["esp32", "cp210x", "ch340", "ftdi", "silicon labs"]
            ):
                logger.info(f"Found potential ESP32 port: {port.device}")
                return port.device

        logger.warning("No ESP32 port auto-detected")
        return None

    # def connect(self) -> bool:
    #     """Connect to ESP32 via direct serial connection with robust error handling."""
    #     if not self.esp32_port:
    #         raise RuntimeError("No ESP32 port configured or detected")

    #     with self._comm_lock:
    #         try:
    #             logger.info(f"Connecting to ESP32 on port: {self.esp32_port}")

    #             # Close any existing connection
    #             if self.serial_connection:
    #                 try:
    #                     self.serial_connection.close()
    #                 except:
    #                     pass
    #                 self.serial_connection = None

    #             self.serial_connection = serial.Serial(
    #                 port=self.esp32_port,
    #                 baudrate=115200,
    #                 timeout=2.0,
    #                 write_timeout=1.0
    #             )

    #             # Wait for ESP32 to initialize
    #             time.sleep(2.0)
    #             self.serial_connection.reset_input_buffer()

    #             # ✅ CRITICAL: Robust connection test with retries
    #             for attempt in range(3):
    #                 try:
    #                     if self._test_connection():
    #                         self.connected = True
    #                         self._consecutive_failures = 0
    #                         self._last_successful_command = time.time()
    #                         self.connection_status_changed.emit(True)
    #                         logger.info("ESP32 connected successfully")

    #                         # Initialize LED state after successful connection
    #                         self._initialize_led_state()
    #                         return True
    #                 except Exception as e:
    #                     logger.warning(f"Connection test attempt {attempt + 1} failed: {e}")
    #                     if attempt < 2:
    #                         time.sleep(1.0)

    #             # All attempts failed
    #             self.serial_connection.close()
    #             self.serial_connection = None
    #             raise RuntimeError("ESP32 not responding after 3 attempts")

    #         except Exception as e:
    #             if self.serial_connection:
    #                 try:
    #                     self.serial_connection.close()
    #                 except:
    #                     pass
    #                 self.serial_connection = None
    #             raise RuntimeError(f"Failed to connect to ESP32: {str(e)}")
    def _initialize_led_state_safe(self):
        """Initialize LED state with enhanced error handling and firmware detection."""
        print("DEBUG: === ENTERING SAFE _initialize_led_state() ===")
        try:
            print("DEBUG: About to call get_led_status with firmware detection...")

            # Use the fixed method that handles 0x72 responses
            led_status = self._get_led_status_unlocked()
            print(f"DEBUG: get_led_status() returned: {led_status}")

            print("DEBUG: Extracting LED status values...")
            self.current_led_type = led_status.get("current_led_type", "ir")
            print(f"DEBUG: current_led_type = {self.current_led_type}")

            self.led_ir_state = led_status.get("ir_led_state", False)
            print(f"DEBUG: led_ir_state = {self.led_ir_state}")

            self.led_white_state = led_status.get("white_led_state", False)
            print(f"DEBUG: led_white_state = {self.led_white_state}")

            self.led_power = led_status.get("led_power_percent", 100)
            print(f"DEBUG: led_power = {self.led_power}")

            # ✅ NEW: Log firmware information
            firmware_variant = led_status.get("firmware_variant", "unknown")
            response_header = led_status.get("response_header", "unknown")
            print(
                f"DEBUG: firmware_variant = {firmware_variant}, response_header = {response_header}"
            )

            print(f"DEBUG: LED state initialized successfully with firmware detection")
            logger.info(
                f"LED state initialized: Current={self.current_led_type}, "
                f"IR={self.led_ir_state}, White={self.led_white_state}, Power={self.led_power}%, "
                f"Firmware={firmware_variant}"
            )
            print("DEBUG: === EXITING SAFE _initialize_led_state() ===")

        except Exception as e:
            print(f"DEBUG: Exception in _initialize_led_state_safe(): {type(e).__name__}: {e}")
            import traceback

            traceback.print_exc()
            logger.error(f"Could not initialize LED state: {e}")

            # Use defaults but don't fail connection
            self.current_led_type = "ir"
            self.led_ir_state = False
            self.led_white_state = False
            self.led_power = 100
            self._firmware_variant = "unknown_fallback"
            print("DEBUG: Using default LED state values with firmware fallback")

    def _test_connection_with_firmware_detection(self) -> bool:
        """Test connection with firmware version detection."""
        try:
            print("DEBUG: Testing connection with firmware detection...")

            # Send status command
            self._send_byte(self.CMD_STATUS)

            # Try to read response and detect firmware version
            response = self._read_status_response(timeout=3.0)
            if response is not None:
                print(f"DEBUG: ESP32 responded to status command: {response}")

                # Try to detect firmware version by testing LED status command
                try:
                    self._send_byte(self.CMD_GET_LED_STATUS)
                    led_data = self._read_bytes(5, timeout=2.0)

                    if led_data and len(led_data) == 5:
                        header = led_data[0]
                        print(f"DEBUG: LED status response header: 0x{header:02x}")

                        # Store detected firmware variant
                        if header == 0x32:
                            print("DEBUG: Standard firmware detected")
                            self._firmware_variant = "standard"
                        elif header == 0x72:
                            print("DEBUG: Custom firmware variant detected (0x72)")
                            self._firmware_variant = "variant_0x72"
                        else:
                            print(f"DEBUG: Unknown firmware variant (0x{header:02x})")
                            self._firmware_variant = f"unknown_0x{header:02x}"
                    else:
                        print("DEBUG: No LED status response, using standard firmware assumption")
                        self._firmware_variant = "standard"

                except Exception as led_e:
                    print(f"DEBUG: LED status test failed: {led_e}")
                    self._firmware_variant = "unknown"

                return True
            else:
                print("DEBUG: No response to status command")
                return False

        except Exception as e:
            print(f"DEBUG: Firmware detection test failed: {e}")
            return False

    def connect(self) -> bool:
        """Connect to ESP32 with ImSwitch protection and firmware detection."""
        print("DEBUG: === ENTERING PROTECTED connect() METHOD ===")

        # ✅ CRITICAL: ImSwitch Protection - Pause ImSwitch operations
        imswitch_paused = False
        if self.imswitch_main:
            try:
                print("DEBUG: Attempting to pause ImSwitch operations...")
                # Try to pause live view or detector operations to avoid conflicts
                if hasattr(self.imswitch_main, "liveViewWidget"):
                    live_view = self.imswitch_main.liveViewWidget
                    if hasattr(live_view, "pauseStream"):
                        live_view.pauseStream()
                        imswitch_paused = True
                        print("DEBUG: ImSwitch live view paused")

                # Small delay to let ImSwitch settle
                time.sleep(0.5)
            except Exception as pause_e:
                print(f"DEBUG: ImSwitch pause failed (continuing anyway): {pause_e}")

        try:
            print(f"DEBUG: Checking esp32_port: {self.esp32_port}")
            if not self.esp32_port:
                print("DEBUG: No port, raising RuntimeError")
                raise RuntimeError("No ESP32 port configured or detected")

            print("DEBUG: About to acquire _comm_lock...")
            with self._comm_lock:
                print("DEBUG: Lock acquired successfully")

                try:
                    print(f"DEBUG: Attempting connection to {self.esp32_port}")

                    # Close existing connection
                    if self.serial_connection:
                        print("DEBUG: Closing existing connection...")
                        try:
                            self.serial_connection.close()
                            print("DEBUG: Existing connection closed")
                        except Exception as close_e:
                            print(f"DEBUG: Close error (ignored): {close_e}")
                        self.serial_connection = None
                        print("DEBUG: Connection reference cleared")

                    print("DEBUG: Creating Serial object...")
                    import serial

                    self.serial_connection = serial.Serial(
                        port=self.esp32_port, baudrate=115200, timeout=2.0, write_timeout=1.0
                    )
                    print("DEBUG: Serial object created")

                    print("DEBUG: Starting 2 second wait for ESP32 initialization...")
                    time.sleep(2.0)
                    print("DEBUG: Wait completed")

                    print("DEBUG: Resetting input buffer...")
                    self.serial_connection.reset_input_buffer()
                    print("DEBUG: Buffer reset completed")

                    print("DEBUG: Starting connection test loop...")
                    connection_success = False
                    for attempt in range(3):
                        print(f"DEBUG: Connection test attempt {attempt + 1}")
                        try:
                            if self._test_connection_with_firmware_detection():
                                print("DEBUG: Connection test PASSED with firmware detection")
                                connection_success = True
                                break
                        except Exception as test_e:
                            print(f"DEBUG: Connection test attempt {attempt + 1} failed: {test_e}")
                            if attempt < 2:
                                time.sleep(1.0)

                    if connection_success:
                        self.connected = True
                        self._consecutive_failures = 0
                        self._last_successful_command = time.time()

                        print("DEBUG: About to emit connection_status_changed signal...")
                        self.connection_status_changed.emit(True)
                        print("DEBUG: Signal emitted")

                        print("DEBUG: About to initialize LED state with firmware detection...")
                        self._initialize_led_state_safe()
                        print("DEBUG: LED state initialized")

                        print("DEBUG: Connection successful, returning True")
                        return True
                    else:
                        print("DEBUG: All connection attempts failed")
                        self.serial_connection.close()
                        self.serial_connection = None
                        raise RuntimeError("ESP32 not responding after 3 attempts")

                except Exception as inner_e:
                    print(f"DEBUG: Inner exception: {type(inner_e).__name__}: {inner_e}")
                    if self.serial_connection:
                        try:
                            self.serial_connection.close()
                        except:
                            pass
                        self.serial_connection = None
                    raise RuntimeError(f"Failed to connect to ESP32: {str(inner_e)}")

        except Exception as lock_e:
            print(f"DEBUG: Lock or outer exception: {type(lock_e).__name__}: {lock_e}")
            raise

        finally:
            # ✅ CRITICAL: Resume ImSwitch operations
            if imswitch_paused and self.imswitch_main:
                try:
                    print("DEBUG: Resuming ImSwitch operations...")
                    if hasattr(self.imswitch_main, "liveViewWidget"):
                        live_view = self.imswitch_main.liveViewWidget
                        if hasattr(live_view, "resumeStream"):
                            live_view.resumeStream()
                            print("DEBUG: ImSwitch live view resumed")
                    time.sleep(0.2)  # Let ImSwitch settle
                except Exception as resume_e:
                    print(f"DEBUG: ImSwitch resume failed: {resume_e}")

    def connect_with_imswitch_protection(self) -> bool:
        """Enhanced connect with ImSwitch resource protection and communication recovery."""
        print("DEBUG: === ENTERING PROTECTED ESP32 CONNECTION ===")

        # ✅ CRITICAL: ImSwitch Protection Phase
        imswitch_paused = False
        original_imswitch_state = {}

        if self.imswitch_main:
            try:
                print("DEBUG: Implementing ImSwitch protection...")

                # Method 1: Pause live view
                if hasattr(self.imswitch_main, "liveViewWidget"):
                    live_view = self.imswitch_main.liveViewWidget
                    if hasattr(live_view, "liveViewWidget") and hasattr(live_view, "pauseStream"):
                        live_view.pauseStream()
                        original_imswitch_state["live_view_paused"] = True
                        imswitch_paused = True
                        print("DEBUG: ImSwitch live view paused")

                # Method 2: Pause detector operations
                if hasattr(self.imswitch_main, "detectorsManager"):
                    detectors = self.imswitch_main.detectorsManager
                    if hasattr(detectors, "stopAcquisition"):
                        try:
                            detectors.stopAcquisition()
                            original_imswitch_state["acquisition_stopped"] = True
                            print("DEBUG: ImSwitch acquisition stopped")
                        except:
                            print("DEBUG: ImSwitch acquisition stop failed (may not be running)")

                # Give ImSwitch time to release resources
                time.sleep(0.8)

            except Exception as protection_e:
                print(f"DEBUG: ImSwitch protection failed: {protection_e}")
                # Continue anyway - this is protection, not a requirement

        try:
            # ✅ ENHANCED: Connection with communication recovery
            success = self._connect_with_recovery()

            if success:
                print("DEBUG: ESP32 connected successfully with protection")

                # ✅ FIRMWARE VERIFICATION: Test LED status communication
                try:
                    print("DEBUG: Verifying LED status communication...")
                    led_status = self.get_led_status()

                    if led_status.get("communication_recovered", False):
                        print("DEBUG: Communication was recovered during LED status check")

                    if led_status.get("firmware_aligned", False):
                        print("DEBUG: Firmware communication is properly aligned")

                    firmware_info = {
                        "response_header": led_status.get("response_header", "unknown"),
                        "firmware_aligned": led_status.get("firmware_aligned", False),
                        "current_led_type": led_status.get("current_led_type", "unknown"),
                    }

                    print(f"DEBUG: Firmware verification: {firmware_info}")

                except Exception as verify_e:
                    print(f"DEBUG: Firmware verification failed: {verify_e}")
                    # Don't fail connection for this

            return success

        except Exception as connect_e:
            print(f"DEBUG: Protected connection failed: {connect_e}")
            return False

        finally:
            # ✅ CRITICAL: Restore ImSwitch operations
            if imswitch_paused and self.imswitch_main:
                try:
                    print("DEBUG: Restoring ImSwitch operations...")
                    time.sleep(0.3)  # Let ESP32 settle first

                    # Restore live view
                    if original_imswitch_state.get("live_view_paused", False):
                        if hasattr(self.imswitch_main, "liveViewWidget"):
                            live_view = self.imswitch_main.liveViewWidget
                            if hasattr(live_view, "resumeStream"):
                                live_view.resumeStream()
                                print("DEBUG: ImSwitch live view resumed")

                    # Restore acquisition
                    if original_imswitch_state.get("acquisition_stopped", False):
                        if hasattr(self.imswitch_main, "detectorsManager"):
                            detectors = self.imswitch_main.detectorsManager
                            if hasattr(detectors, "startAcquisition"):
                                try:
                                    detectors.startAcquisition()
                                    print("DEBUG: ImSwitch acquisition resumed")
                                except:
                                    print(
                                        "DEBUG: ImSwitch acquisition resume failed (may be normal)"
                                    )

                    time.sleep(0.2)  # Final settling time

                except Exception as restore_e:
                    print(f"DEBUG: ImSwitch restoration failed: {restore_e}")

    def _connect_with_recovery(self) -> bool:
        """Core connection with enhanced recovery logic."""
        if not self.esp32_port:
            raise RuntimeError("No ESP32 port configured or detected")

        with self._comm_lock:
            try:
                # Close existing connection
                if self.serial_connection:
                    try:
                        self.serial_connection.close()
                        time.sleep(0.2)
                    except:
                        pass
                    self.serial_connection = None

                # Create new connection
                import serial

                self.serial_connection = serial.Serial(
                    port=self.esp32_port, baudrate=115200, timeout=2.0, write_timeout=1.0
                )

                # ✅ ENHANCED: ESP32 initialization with buffer clearing
                print("DEBUG: Waiting for ESP32 initialization...")
                time.sleep(2.0)

                # Clear any startup messages or stale data
                if self.serial_connection.in_waiting > 0:
                    startup_data = self.serial_connection.read(self.serial_connection.in_waiting)
                    print(f"DEBUG: Cleared {len(startup_data)} startup bytes")

                self.serial_connection.reset_input_buffer()
                self.serial_connection.reset_output_buffer()

                # ✅ ROBUST: Connection test with recovery
                connection_success = False
                for attempt in range(3):
                    try:
                        print(f"DEBUG: Connection test attempt {attempt + 1}")

                        # Clear buffers before each attempt
                        if self.serial_connection.in_waiting > 0:
                            self.serial_connection.read(self.serial_connection.in_waiting)

                        # Test basic communication
                        if self._test_connection():
                            print(f"DEBUG: Connection test PASSED on attempt {attempt + 1}")
                            connection_success = True
                            break
                        else:
                            print(f"DEBUG: Connection test FAILED on attempt {attempt + 1}")

                    except Exception as test_e:
                        print(f"DEBUG: Connection test attempt {attempt + 1} exception: {test_e}")

                    if attempt < 2:
                        time.sleep(0.5 * (attempt + 1))  # Increasing delay

                if connection_success:
                    self.connected = True
                    self._consecutive_failures = 0
                    self._last_successful_command = time.time()
                    self.connection_status_changed.emit(True)

                    # ✅ SAFE: LED state initialization with recovery
                    try:
                        self._initialize_led_state_safe()
                    except Exception as led_init_e:
                        print(f"DEBUG: LED state init failed: {led_init_e}")
                        # Don't fail connection for this

                    return True
                else:
                    raise RuntimeError("ESP32 not responding after 3 connection attempts")

            except Exception as e:
                if self.serial_connection:
                    try:
                        self.serial_connection.close()
                    except:
                        pass
                    self.serial_connection = None
                raise RuntimeError(f"ESP32 connection failed: {str(e)}")

    # def _initialize_led_state(self):
    #     """Initialize LED state after connection with verification."""
    #     try:
    #         # Get current LED status from ESP32
    #         led_status = self.get_led_status()
    #         self.current_led_type = led_status.get('current_led_type', 'ir')
    #         self.led_ir_state = led_status.get('ir_led_state', False)
    #         self.led_white_state = led_status.get('white_led_state', False)
    #         self.led_power = led_status.get('led_power_percent', 100)

    #         logger.info(f"LED state initialized: Current={self.current_led_type}, "
    #                    f"IR={self.led_ir_state}, White={self.led_white_state}, Power={self.led_power}%")
    #     except Exception as e:
    #         logger.error(f"Could not initialize LED state: {e}")
    #         # Use defaults but don't fail connection
    #         self.current_led_type = 'ir'
    #         self.led_ir_state = False
    #         self.led_white_state = False
    def _initialize_led_state(self):
        """Initialize LED state after connection with verification - DEBUG VERSION."""
        print("DEBUG: === ENTERING _initialize_led_state() ===")
        try:
            print("DEBUG: About to call get_led_status()...")
            led_status = self._get_led_status_unlocked()
            print(f"DEBUG: get_led_status() returned: {led_status}")

            print("DEBUG: Extracting LED status values...")
            self.current_led_type = led_status.get("current_led_type", "ir")
            print(f"DEBUG: current_led_type = {self.current_led_type}")

            self.led_ir_state = led_status.get("ir_led_state", False)
            print(f"DEBUG: led_ir_state = {self.led_ir_state}")

            self.led_white_state = led_status.get("white_led_state", False)
            print(f"DEBUG: led_white_state = {self.led_white_state}")

            self.led_power = led_status.get("led_power_percent", 100)
            print(f"DEBUG: led_power = {self.led_power}")

            print(f"DEBUG: LED state initialized successfully")
            logger.info(
                f"LED state initialized: Current={self.current_led_type}, "
                f"IR={self.led_ir_state}, White={self.led_white_state}, Power={self.led_power}%"
            )
            print("DEBUG: === EXITING _initialize_led_state() ===")
        except Exception as e:
            print(f"DEBUG: Exception in _initialize_led_state(): {type(e).__name__}: {e}")
            import traceback

            traceback.print_exc()
            logger.error(f"Could not initialize LED state: {e}")
            # Use defaults but don't fail connection
            self.current_led_type = "ir"
            self.led_ir_state = False
            self.led_white_state = False
            print("DEBUG: Using default LED state values")

    def _test_connection(self) -> bool:
        """Test ESP32 connection with status command."""
        try:
            self._send_byte(self.CMD_STATUS)
            response = self._read_status_response(timeout=3.0)
            return response is not None
        except Exception as e:
            logger.debug(f"Connection test failed: {e}")
            return False

    def clear_communication_buffers(self):
        """Clear communication buffers to prevent corruption."""
        if self.serial_connection and self.serial_connection.is_open:
            try:
                if self.serial_connection.in_waiting > 0:
                    stale_data = self.serial_connection.read(self.serial_connection.in_waiting)
                    logger.info(f"Cleared {len(stale_data)} stale bytes")

                self.serial_connection.reset_input_buffer()
                self.serial_connection.reset_output_buffer()
                return True
            except Exception as e:
                logger.error(f"Buffer clear failed: {e}")
                return False
        return False

    def disconnect(self):
        """Disconnect from ESP32 with cleanup."""
        with self._comm_lock:
            if self.serial_connection:
                try:
                    # Try to turn off all LEDs before disconnecting
                    self.turn_off_all_leds()
                except:
                    pass
                try:
                    self.serial_connection.close()
                except:
                    pass
                finally:
                    self.serial_connection = None

            self.connected = False
            self.led_ir_state = False
            self.led_white_state = False
            self._consecutive_failures = 0
            self.connection_status_changed.emit(False)
            logger.info("ESP32 disconnected")

    def is_connected(self, force_check: bool = False) -> bool:
        """Check connection status with optional health verification."""
        if not self.connected or not self.serial_connection:
            return False

        if force_check:
            try:
                with self._comm_lock:
                    ok = self._test_connection()
                    if ok:
                        self._consecutive_failures = 0
                        self._last_successful_command = time.time()
                    else:
                        self._consecutive_failures += 1
                        if self._consecutive_failures >= self._max_failures_before_reconnect:
                            logger.warning(
                                f"Connection health check failed {self._consecutive_failures} times"
                            )
                            self.connected = False
                            self.connection_status_changed.emit(False)
                    return ok
            except:
                self._consecutive_failures += 1
                self.connected = False
                self.connection_status_changed.emit(False)
                return False
        return True

    # =========================================================================
    # ✅ ROBUST SERIAL COMMUNICATION METHODS
    # =========================================================================

    def _send_command_with_retry(
        self,
        command_byte: int,
        expected_response: int = None,
        max_retries: int = 3,
        verify_response: bool = True,
    ) -> bool:
        """Send command with retry logic and optional response verification."""
        last_exception = None

        for attempt in range(max_retries):
            try:
                self._send_byte(command_byte)

                if verify_response and expected_response:
                    if self._wait_for_ack(expected_response, timeout=2.0 * (attempt + 1)):
                        self._consecutive_failures = 0
                        self._last_successful_command = time.time()
                        return True
                    else:
                        raise RuntimeError(f"No acknowledgment for command 0x{command_byte:02x}")
                else:
                    # Command sent successfully, no response expected
                    self._consecutive_failures = 0
                    self._last_successful_command = time.time()
                    return True

            except Exception as e:
                last_exception = e
                self._consecutive_failures += 1
                logger.warning(f"Command 0x{command_byte:02x} attempt {attempt + 1} failed: {e}")

                if attempt < max_retries - 1:
                    time.sleep(0.1 * (2**attempt))  # Exponential backoff

        # All retries failed
        logger.error(f"Command 0x{command_byte:02x} failed after {max_retries} attempts")
        if self._consecutive_failures >= self._max_failures_before_reconnect:
            self.connected = False
            self.connection_status_changed.emit(False)

        raise RuntimeError(f"Command failed after {max_retries} attempts: {last_exception}")

    def _send_byte(self, byte_val: int):
        """Send single byte to ESP32 with validation."""
        if not self.serial_connection:
            raise RuntimeError("ESP32 not connected")

        try:
            logger.debug(f"Sending byte 0x{byte_val:02x} to port {self.esp32_port}")
            self.serial_connection.write(bytes([byte_val]))
            self.serial_connection.flush()
            logger.debug(f"Byte sent successfully")
        except Exception as e:
            raise RuntimeError(f"Failed to send byte: {str(e)}")

    def _send_bytes(self, byte_list: list):
        """Send multiple bytes to ESP32 with validation."""
        if not self.serial_connection:
            raise RuntimeError("ESP32 not connected")

        try:
            logger.debug(f"Sending bytes {[hex(b) for b in byte_list]} to port {self.esp32_port}")
            self.serial_connection.write(bytes(byte_list))
            self.serial_connection.flush()
            logger.debug(f"Bytes sent successfully")
        except Exception as e:
            raise RuntimeError(f"Failed to send bytes: {str(e)}")

    def _read_bytes(self, expected_length: int, timeout: float = 2.0) -> Optional[bytes]:
        """Read specified number of bytes from ESP32."""
        if not self.serial_connection:
            return None

        start_time = time.time()
        data = bytearray()

        while len(data) < expected_length and time.time() - start_time < timeout:
            if self.serial_connection.in_waiting > 0:
                available = min(expected_length - len(data), self.serial_connection.in_waiting)
                chunk = self.serial_connection.read(available)
                data.extend(chunk)
                logger.debug(f"Read {len(chunk)} bytes: {[hex(b) for b in chunk]}")
            else:
                time.sleep(0.01)

        if len(data) == expected_length:
            logger.debug(f"Successfully read {len(data)} bytes")
            return bytes(data)
        else:
            logger.debug(f"Read timeout - got {len(data)}/{expected_length} bytes")
            return None

    def _read_status_response(self, timeout: float = 2.0) -> Optional[dict]:
        """Read 5-byte status response from ESP32."""
        logger.debug(f"Waiting for 5-byte status response...")
        data = self._read_bytes(5, timeout)
        if not data or len(data) != 5:
            logger.debug(f"Status response failed - got {len(data) if data else 0}/5 bytes")
            return None

        try:
            status_code = data[0]
            temp_raw = struct.unpack(">h", data[1:3])[0]
            temperature = temp_raw / 10.0
            hum_raw = struct.unpack(">H", data[3:5])[0]
            humidity = hum_raw / 10.0

            result = {
                "status_code": status_code,
                "temperature": temperature,
                "humidity": humidity,
                "led_on": status_code in [self.RESPONSE_STATUS_ON, self.RESPONSE_ACK_ON],
            }

            logger.debug(
                f"Status response - Code: 0x{status_code:02x}, LED: {result['led_on']}, T: {temperature:.1f}°C"
            )
            return result
        except Exception as e:
            logger.error(f"Failed to parse status response: {e}")
            return None

    def _read_sync_response(self, timeout: float = 5.0) -> Optional[dict]:
        """Read 7-byte sync response from ESP32."""
        logger.debug(f"Waiting for 7-byte sync response...")
        data = self._read_bytes(7, timeout)
        if not data or len(data) != 7:
            logger.debug(f"Sync response failed - got {len(data) if data else 0}/7 bytes")
            return None

        try:
            if data[0] != self.RESPONSE_SYNC_COMPLETE:
                logger.error(f"Invalid sync response header: {data[0]:02x}")
                return None

            timing_ms = struct.unpack(">H", data[1:3])[0]
            temp_raw = struct.unpack(">h", data[3:5])[0]
            temperature = temp_raw / 10.0
            hum_raw = struct.unpack(">H", data[5:7])[0]
            humidity = hum_raw / 10.0

            result = {"timing_ms": timing_ms, "temperature": temperature, "humidity": humidity}

            logger.debug(f"Sync response - Timing: {timing_ms}ms, T: {temperature:.1f}°C")
            return result
        except Exception as e:
            logger.error(f"Failed to parse sync response: {e}")
            return None

    def _wait_for_ack(self, expected_response: int, timeout: float = 1.0) -> bool:
        """Wait for specific acknowledgment response."""
        logger.debug(f"Waiting for ACK: 0x{expected_response:02x}")
        start_time = time.time()

        while time.time() - start_time < timeout:
            if self.serial_connection.in_waiting > 0:
                response = self.serial_connection.read(1)[0]
                logger.debug(f"Got ACK response: 0x{response:02x}")
                if response == expected_response:
                    return True
                elif response == self.RESPONSE_ERROR:
                    raise RuntimeError("ESP32 reported error")
            time.sleep(0.01)

        logger.debug(f"ACK timeout after {timeout}s")
        return False

    # =========================================================================
    # ✅ VERIFIED LED SELECTION AND CONTROL METHODS
    # =========================================================================

    def select_led_ir(self) -> bool:
        """Select IR LED with state verification - CRITICAL for phase accuracy."""
        with self._comm_lock:
            try:
                logger.info("Selecting IR LED...")

                # Send command with retry logic
                success = self._send_command_with_retry(
                    self.CMD_SELECT_LED_IR, self.RESPONSE_LED_IR_SELECTED, max_retries=3
                )

                if success:
                    # ✅ CRITICAL: Verify the switch actually worked
                    time.sleep(0.1)  # Small delay for LED switch
                    status = self.get_led_status()

                    if status["current_led_type"] == "ir":
                        self.current_led_type = "ir"
                        logger.info("IR LED selected and verified")
                        return True
                    else:
                        raise RuntimeError(
                            f"LED verification failed: expected IR, got {status['current_led_type']}"
                        )
                else:
                    raise RuntimeError("No acknowledgment for IR LED selection")

            except Exception as e:
                logger.error(f"Failed to select IR LED: {e}")
                raise RuntimeError(f"Failed to select IR LED: {str(e)}")

    def select_led_white(self) -> bool:
        """Select White LED with state verification - CRITICAL for phase accuracy."""
        with self._comm_lock:
            try:
                logger.info("Selecting White LED...")

                # Send command with retry logic
                success = self._send_command_with_retry(
                    self.CMD_SELECT_LED_WHITE, self.RESPONSE_LED_WHITE_SELECTED, max_retries=3
                )

                if success:
                    # ✅ CRITICAL: Verify the switch actually worked
                    time.sleep(0.1)  # Small delay for LED switch
                    status = self.get_led_status()

                    if status["current_led_type"] == "white":
                        self.current_led_type = "white"
                        logger.info("White LED selected and verified")
                        return True
                    else:
                        raise RuntimeError(
                            f"LED verification failed: expected white, got {status['current_led_type']}"
                        )
                else:
                    raise RuntimeError("No acknowledgment for White LED selection")

            except Exception as e:
                logger.error(f"Failed to select White LED: {e}")
                raise RuntimeError(f"Failed to select White LED: {str(e)}")

    def select_led_type(self, led_type: str) -> bool:
        """Select LED type with optional automatic calibrated power application."""
        led_type_lower = led_type.lower()

        # Perform standard LED selection
        if led_type_lower in ["ir", "infrared", "night"]:
            success = self.select_led_ir()
            actual_led_type = "ir"
        elif led_type_lower in ["white", "whitelight", "day", "cob"]:
            success = self.select_led_white()
            actual_led_type = "whitelight"  # ✅ Use whitelight internally
        else:
            raise ValueError(f"Unknown LED type: {led_type}. Use 'ir', 'white', 'whitelight', etc.")

        if not success:
            return False

        # ✅ Automatic calibrated power application with whitelight_power
        if self.auto_apply_calibration and self.calibrated_powers:
            calibrated_power = self.calibrated_powers.get(actual_led_type)
            if calibrated_power is not None:
                try:
                    self.set_led_power(calibrated_power)

                    # Verify the power was actually set
                    time.sleep(0.1)
                    current_power = self.led_power

                    if abs(current_power - calibrated_power) <= 1:
                        logger.info(
                            f"✓ Calibrated power applied: {actual_led_type.upper()} LED = {calibrated_power}%"
                        )
                    else:
                        logger.warning(
                            f"⚠ Power mismatch: requested {calibrated_power}%, actual {current_power}%"
                        )

                except Exception as e:
                    logger.warning(f"Failed to auto-apply calibrated power: {e}")
            else:
                logger.warning(f"No calibrated power found for {actual_led_type} LED")

        return True

    def turn_off_all_leds(self) -> bool:
        """Turn off both IR and White LEDs with verification."""
        with self._comm_lock:
            try:
                logger.info("Turning off all LEDs...")

                success = self._send_command_with_retry(
                    self.CMD_LED_DUAL_OFF, self.RESPONSE_ACK_OFF, max_retries=3
                )

                if success:
                    self.led_ir_state = False
                    self.led_white_state = False
                    self.led_on_state = False
                    logger.info("All LEDs turned off successfully")
                    self.led_status_changed.emit(False, 0)
                    return True
                else:
                    raise RuntimeError("No acknowledgment for LED dual off command")

            except Exception as e:
                logger.error(f"Failed to turn off all LEDs: {e}")
                raise RuntimeError(f"Failed to turn off all LEDs: {str(e)}")

    # def get_led_status(self) -> dict:
    #     """Get detailed LED status from ESP32 with fallback."""
    #     with self._comm_lock:
    #         try:
    #             logger.debug("Getting LED status...")
    #             self._send_byte(self.CMD_GET_LED_STATUS)

    #             # Read 5-byte LED status response
    #             data = self._read_bytes(5, timeout=3.0)
    #             if not data or len(data) != 5:
    #                 logger.warning(f"LED status response failed - got {len(data) if data else 0}/5 bytes")
    #                 return self._get_fallback_led_status()

    #             try:
    #                 if data[0] != self.RESPONSE_LED_STATUS:
    #                     logger.warning(f"Invalid LED status response header: {data[0]:02x}")
    #                     return self._get_fallback_led_status()

    #                 current_type = 'ir' if data[1] == 0 else 'whitelight'
    #                 ir_state = bool(data[2])
    #                 white_state = bool(data[3])
    #                 power_percent = data[4]

    #                 # Update local state
    #                 self.current_led_type = current_type
    #                 self.led_ir_state = ir_state
    #                 self.led_white_state = white_state
    #                 self.led_power = power_percent
    #                 self.led_on_state = ir_state or white_state

    #                 status = {
    #                     'current_led_type': current_type,
    #                     'ir_led_state': ir_state,
    #                     'white_led_state': white_state,
    #                     'led_power_percent': power_percent,
    #                     'any_led_on': ir_state or white_state
    #                 }

    #                 logger.debug(f"LED Status - Current: {current_type}, IR: {ir_state}, White: {white_state}, Power: {power_percent}%")
    #                 return status

    #             except Exception as e:
    #                 logger.error(f"Failed to parse LED status response: {e}")
    #                 return self._get_fallback_led_status()

    #         except Exception as e:
    #             logger.error(f"Get LED status failed: {e}")
    #             return self._get_fallback_led_status()
    def _get_led_status_unlocked(self) -> dict:
        """Get LED status with communication recovery and firmware alignment."""
        try:
            logger.debug("Getting LED status with communication recovery...")

            # ✅ CRITICAL: Clear any stale data first
            if self.serial_connection.in_waiting > 0:
                stale_data = self.serial_connection.read(self.serial_connection.in_waiting)
                logger.warning(
                    f"Cleared {len(stale_data)} stale bytes: {[hex(b) for b in stale_data]}"
                )

            # ✅ ROBUST: Try LED status command with recovery
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    logger.debug(f"LED status attempt {attempt + 1}/{max_attempts}")

                    # Send command
                    self._send_byte(self.CMD_GET_LED_STATUS)
                    time.sleep(0.1)  # Give ESP32 time to process

                    # Read response
                    data = self._read_bytes(5, timeout=2.0)
                    if not data or len(data) != 5:
                        logger.warning(
                            f"Attempt {attempt + 1}: got {len(data) if data else 0}/5 bytes"
                        )
                        if attempt < max_attempts - 1:
                            time.sleep(0.2)
                            continue
                        else:
                            logger.warning("All attempts failed, using fallback")
                            return self._get_fallback_led_status()

                    response_header = data[0]
                    logger.info(f"Attempt {attempt + 1}: Response header: 0x{response_header:02x}")

                    # ✅ FIRMWARE ALIGNMENT: Handle your specific firmware responses
                    if response_header == 0x32:  # Expected RESPONSE_LED_STATUS
                        logger.info("Standard firmware response (0x32)")
                        current_type = "ir" if data[1] == 0 else "whitelight"
                        ir_state = bool(data[2])
                        white_state = bool(data[3])
                        power_percent = data[4]
                        break

                    elif response_header == 0x72:  # Corrupted/shifted response
                        logger.warning(
                            "Received 0x72 - likely communication corruption, clearing and retrying..."
                        )
                        # Clear buffer and try again
                        if self.serial_connection.in_waiting > 0:
                            extra_data = self.serial_connection.read(
                                self.serial_connection.in_waiting
                            )
                            logger.debug(f"Cleared additional data: {[hex(b) for b in extra_data]}")
                        time.sleep(0.3)
                        continue

                    elif response_header in [0x10, 0x11, 0x48]:  # Status responses instead
                        logger.warning(
                            f"ESP32 sent status response (0x{response_header:02x}) instead of LED status"
                        )
                        # This means the ESP32 is confused - send a status command to reset
                        logger.info("Sending status command to reset ESP32 state...")
                        self._send_byte(self.CMD_STATUS)
                        status_data = self._read_bytes(5, timeout=2.0)
                        if status_data:
                            logger.info("ESP32 status reset successful")
                        time.sleep(0.2)
                        continue

                    else:
                        logger.warning(f"Unknown response header: 0x{response_header:02x}")
                        logger.debug(f"Full response: {[hex(b) for b in data]}")
                        if attempt < max_attempts - 1:
                            continue
                        else:
                            logger.warning("Unknown response after all attempts, using fallback")
                            return self._get_fallback_led_status()

                except Exception as attempt_e:
                    logger.warning(f"Attempt {attempt + 1} failed: {attempt_e}")
                    if attempt < max_attempts - 1:
                        time.sleep(0.2)
                        continue
                    else:
                        return self._get_fallback_led_status()

            # If we get here, we should have valid data
            logger.debug(
                f"LED Status parsed: type={current_type}, ir={ir_state}, white={white_state}, power={power_percent}"
            )

            # Update local state
            self.current_led_type = current_type
            self.led_ir_state = ir_state
            self.led_white_state = white_state
            self.led_power = power_percent
            self.led_on_state = ir_state or white_state

            status = {
                "current_led_type": current_type,
                "ir_led_state": ir_state,
                "white_led_state": white_state,
                "led_power_percent": power_percent,
                "any_led_on": ir_state or white_state,
                "response_header": hex(response_header),
                "communication_recovered": attempt > 0,
                "firmware_aligned": True,
            }

            logger.info(
                f"LED Status SUCCESS: {current_type.upper()}, IR={ir_state}, White={white_state}, Power={power_percent}% (attempt {attempt + 1})"
            )
            return status

        except Exception as e:
            logger.error(f"Get LED status failed completely: {e}")
            return self._get_fallback_led_status()

    def _get_fallback_led_status(self) -> dict:
        """Fallback LED status based on local state."""
        return {
            "current_led_type": self.current_led_type,
            "ir_led_state": self.led_ir_state,
            "white_led_state": self.led_white_state,
            "led_power_percent": self.led_power,
            "any_led_on": self.led_ir_state or self.led_white_state,
        }

    # =========================================================================
    # ✅ NEW: LED CALIBRATION METHODS
    # =========================================================================

    def set_calibrated_powers(self, ir_power: int, whitelight_power: int, auto_apply: bool = True):
        """Set calibrated LED powers and enable/disable automatic application."""
        self.calibrated_powers = {
            "ir": ir_power,
            "whitelight": whitelight_power,  # ✅ Updated key name
        }
        self.auto_apply_calibration = auto_apply

        logger.info(
            f"Calibrated powers set: IR={ir_power}%, WhiteLight={whitelight_power}%, Auto-apply={auto_apply}"
        )

    def get_calibrated_powers(self) -> dict:
        """Get current calibrated powers."""
        return self.calibrated_powers.copy()

    def enable_auto_calibration(self, enabled: bool = True):
        """Enable or disable automatic application of calibrated powers."""
        self.auto_apply_calibration = enabled
        logger.info(f"Auto-calibration {'enabled' if enabled else 'disabled'}")

    def apply_calibrated_power_manual(self, led_type: str) -> bool:
        """Manually apply calibrated power for specific LED type."""
        led_type_lower = led_type.lower()

        # ✅ Updated to handle both 'white' and 'whitelight' for compatibility
        if led_type_lower not in ["ir", "white", "whitelight"]:
            raise ValueError("LED type must be 'ir', 'white', or 'whitelight'")

        if not self.calibrated_powers:
            raise RuntimeError("No calibrated powers available. Run calibration first.")

        # ✅ Map both 'white' and 'whitelight' to the same calibrated value
        if led_type_lower in ["white", "whitelight"]:
            calibrated_power = self.calibrated_powers.get("whitelight")
            actual_led_type = "whitelight"
        else:
            calibrated_power = self.calibrated_powers.get("ir")
            actual_led_type = "ir"

        if calibrated_power is None:
            raise RuntimeError(f"No calibrated power for {actual_led_type} LED")

        try:
            self.set_led_power(calibrated_power)
            logger.info(
                f"Manually applied calibrated power: {actual_led_type.upper()} LED = {calibrated_power}%"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to apply calibrated power: {e}")
            return False

    # =========================================================================
    # ✅ ROBUST ESP32 CONTROL METHODS
    # =========================================================================

    def set_led_power(self, power: int) -> bool:
        """Set LED power level with verification."""
        if not 0 <= power <= 100:
            raise ValueError("Power must be between 0 and 100")

        with self._comm_lock:
            try:
                success = self._send_command_with_retry(
                    self.CMD_SET_LED_POWER,
                    expected_response=None,  # No specific response expected
                    verify_response=False,
                )

                if success:
                    # Send power value
                    self._send_byte(power)

                    # Wait for acknowledgment
                    if self._wait_for_ack(self.RESPONSE_ACK_ON, timeout=2.0):
                        self.led_power = power
                        logger.info(f"LED power set to {power}%")
                        return True
                    else:
                        raise RuntimeError("No acknowledgment for LED power setting")
                else:
                    raise RuntimeError("Failed to send LED power command")

            except Exception as e:
                logger.error(f"LED power setting failed: {e}")
                raise RuntimeError(f"Failed to set LED power: {str(e)}")

    def led_on(self) -> bool:
        """Turn current LED on with state verification."""
        with self._comm_lock:
            try:
                logger.info(f"Turning {self.current_led_type.upper()} LED ON")
                self._send_byte(self.CMD_LED_ON)

                # Wait for response with stabilization time
                response = self._read_status_response(timeout=5.0)

                if response and response["led_on"]:
                    # Update state based on current LED type
                    if self.current_led_type == "ir":
                        self.led_ir_state = True
                    else:
                        self.led_white_state = True

                    self.led_on_state = True
                    self.led_status_changed.emit(True, self.led_power)
                    logger.info(f"{self.current_led_type.upper()} LED turned on successfully")
                    return True
                else:
                    raise RuntimeError("LED failed to turn on or no response")

            except Exception as e:
                logger.error(f"LED ON failed: {e}")
                raise RuntimeError(f"Failed to turn LED on: {str(e)}")

    def led_off(self) -> bool:
        """Turn current LED off with state verification."""
        with self._comm_lock:
            try:
                logger.info(f"Turning {self.current_led_type.upper()} LED OFF")
                self._send_byte(self.CMD_LED_OFF)

                response = self._read_status_response(timeout=3.0)

                if response and not response["led_on"]:
                    # Update state based on current LED type
                    if self.current_led_type == "ir":
                        self.led_ir_state = False
                    else:
                        self.led_white_state = False

                    self.led_on_state = False
                    self.led_status_changed.emit(False, 0)
                    logger.info(f"{self.current_led_type.upper()} LED turned off successfully")
                    return True
                else:
                    raise RuntimeError("LED failed to turn off or no response")

            except Exception as e:
                logger.error(f"LED OFF failed: {e}")
                raise RuntimeError(f"Failed to turn LED off: {str(e)}")

    def read_sensors(self) -> Tuple[float, float]:
        """Read temperature and humidity from DHT22 sensor."""
        with self._comm_lock:
            try:
                logger.debug("Reading sensors...")
                self._send_byte(self.CMD_STATUS)
                response = self._read_status_response()

                if response:
                    temperature = response["temperature"]
                    humidity = response["humidity"]
                    self.sensor_data_received.emit(temperature, humidity)
                    logger.debug(f"Sensors - T: {temperature:.1f}°C, H: {humidity:.1f}%")
                    return temperature, humidity
                else:
                    raise RuntimeError("No response from ESP32 sensors")

            except Exception as e:
                raise RuntimeError(f"Failed to read sensors: {str(e)}")

    def synchronize_capture_with_led(
        self, led_type: str = None, led_duration_ms: int = None
    ) -> dict:
        """Synchronize LED flash with frame capture - phase aware with verification."""
        with self._comm_lock:
            try:
                logger.info("Starting phase-aware sync capture...")
                logger.debug(f"Requested LED type: {led_type}")
                logger.debug(f"Current LED type: {self.current_led_type}")

                esp32_time_start = time.time()

                # Switch LED if requested and different from current
                if led_type and led_type.lower() != self.current_led_type:
                    logger.info(f"Switching LED from {self.current_led_type} to {led_type}")
                    self.select_led_type(led_type)
                    time.sleep(0.1)  # Small delay for LED switch

                # Send sync capture command (uses currently selected LED)
                self._send_byte(self.CMD_SYNC_CAPTURE)

                # Read sync response
                response = self._read_sync_response()
                esp32_time_end = time.time()

                if response:
                    # Build timing info compatible with the data manager
                    timing_info = {
                        "python_time_start": esp32_time_start,
                        "python_time_end": esp32_time_end,
                        "esp32_time_start": esp32_time_start,  # Approximate
                        "esp32_time_end": esp32_time_end,  # Approximate
                        "led_duration_actual": response["timing_ms"],
                        "led_power_actual": self.led_power,
                        "temperature": response["temperature"],
                        "humidity": response["humidity"],
                        "sync_timing_ms": response["timing_ms"],
                        "led_type_used": self.current_led_type,
                        "phase_aware_capture": True,
                    }

                    logger.info(
                        f"Phase-aware sync capture successful: {response['timing_ms']}ms, "
                        f"{self.current_led_type.upper()} LED, T={response['temperature']:.1f}°C"
                    )
                    return timing_info
                else:
                    raise RuntimeError("No sync response from ESP32")

            except Exception as e:
                raise RuntimeError(f"Phase-aware sync capture failed: {str(e)}")

    def synchronize_capture(self, led_duration_ms: int = None) -> dict:
        """Synchronize LED flash with frame capture - backward compatibility."""
        return self.synchronize_capture_with_led(led_type=None, led_duration_ms=led_duration_ms)

    def set_timing(self, stabilization_ms: int = 300, delay_ms: int = 10) -> bool:
        """Set LED stabilization and trigger delay timing."""
        with self._comm_lock:
            try:
                # Pack timing values as 16-bit big-endian
                stab_bytes = struct.pack(">H", stabilization_ms)
                delay_bytes = struct.pack(">H", delay_ms)

                command = [self.CMD_SET_TIMING] + list(stab_bytes) + list(delay_bytes)
                self._send_bytes(command)

                if self._wait_for_ack(self.RESPONSE_TIMING_SET):
                    self.led_stabilization_ms = stabilization_ms
                    self.trigger_delay_ms = delay_ms
                    logger.info(
                        f"Timing set: stabilization={stabilization_ms}ms, delay={delay_ms}ms"
                    )
                    return True
                else:
                    raise RuntimeError("No acknowledgment for timing setting")

            except Exception as e:
                raise RuntimeError(f"Failed to set timing: {str(e)}")

    def set_camera_type(self, camera_type: int = None) -> bool:
        """Set camera type (1=HIK_GIGE, 2=USB_GENERIC)."""
        if camera_type is None:
            camera_type = self.CAMERA_TYPE_HIK_GIGE

        with self._comm_lock:
            try:
                self._send_bytes([self.CMD_SET_CAMERA_TYPE, camera_type])

                if self._wait_for_ack(self.RESPONSE_ACK_ON):
                    logger.info(f"Camera type set to {camera_type}")
                    return True
                else:
                    raise RuntimeError("No acknowledgment for camera type setting")

            except Exception as e:
                raise RuntimeError(f"Failed to set camera type: {str(e)}")

    def get_led_status(self) -> dict:
        """Get detailed LED status from ESP32 with fallback."""
        with self._comm_lock:
            try:
                logger.debug("Getting LED status...")
                return self._get_led_status_unlocked()
            except Exception as e:
                logger.error(f"Get LED status failed: {e}")
                return self._get_fallback_led_status()

    def get_status(self) -> dict:
        """Get ESP32 status information with dual LED and calibration support."""
        with self._comm_lock:
            try:
                self._send_byte(self.CMD_STATUS)
                response = self._read_status_response()

                if response:
                    led_status = self.get_led_status()
                    status = {
                        "connected": True,
                        "led_on": response["led_on"],
                        "led_power": self.led_power,
                        "temperature": response["temperature"],
                        "humidity": response["humidity"],
                        "led_stabilization_ms": self.led_stabilization_ms,
                        "trigger_delay_ms": self.trigger_delay_ms,
                        "firmware_version": "v4.0_DUAL_LED_CALIBRATION",
                        "port": self.esp32_port,
                        "current_led_type": led_status["current_led_type"],
                        "ir_led_state": led_status["ir_led_state"],
                        "white_led_state": led_status["white_led_state"],
                        "dual_led_capable": True,
                        "consecutive_failures": self._consecutive_failures,
                        "last_successful_command": self._last_successful_command,
                        # ✅ NEW: Calibration information
                        "calibrated_powers": self.calibrated_powers,
                        "auto_apply_calibration": self.auto_apply_calibration,
                        "calibration_available": bool(self.calibrated_powers),
                    }
                    return status
                else:
                    raise RuntimeError("No status response from ESP32")

            except Exception as e:
                raise RuntimeError(f"Failed to get status: {str(e)}")

    def save_calibration(self, filepath: str = None):
        """Save calibrated powers to file with whitelight_power naming."""
        if not self.calibrated_powers:
            raise RuntimeError("No calibrated powers to save")

        if filepath is None:
            import os

            filepath = os.path.join(os.path.expanduser("~"), ".napari_timelapse_calibration.json")

        calibration_data = {
            "timestamp": time.time(),
            "timestamp_human": time.strftime("%Y-%m-%d %H:%M:%S"),
            "calibrated_powers": self.calibrated_powers.copy(),
            "esp32_port": self.esp32_port,
            "firmware_version": "v4.0_DUAL_LED_CALIBRATION",
        }

        import json

        with open(filepath, "w") as f:
            json.dump(calibration_data, f, indent=2)
        logger.info(f"Calibration saved to: {filepath}")
        return filepath

    def load_calibration(self, filepath: str = None):
        """Load previously saved calibrated powers with backward compatibility."""
        if filepath is None:
            import os

            filepath = os.path.join(os.path.expanduser("~"), ".napari_timelapse_calibration.json")

        try:
            import json

            with open(filepath, "r") as f:
                calibration_data = json.load(f)

            powers = calibration_data.get("calibrated_powers", {})
            if powers:
                # ✅ Handle backward compatibility for old 'white' naming
                ir_power = powers.get("ir", 100)
                whitelight_power = powers.get(
                    "whitelight", powers.get("white", 100)
                )  # Fallback to 'white'

                self.set_calibrated_powers(
                    ir_power=ir_power, whitelight_power=whitelight_power, auto_apply=True
                )

                timestamp = calibration_data.get("timestamp_human", "unknown")
                logger.info(f"Calibration loaded: IR={ir_power}%, WhiteLight={whitelight_power}%")
                return True
        except FileNotFoundError:
            logger.info("No saved calibration found")
        except Exception as e:
            logger.error(f"Failed to load calibration: {e}")
        return False

    # =========================================================================
    # ✅ ENHANCED TEST METHODS
    # =========================================================================

    def test_led_sequence(self) -> bool:
        """Test LED sequence with verification and calibration."""
        try:
            logger.info("Testing dual LED sequence with verification...")

            # Test IR LED
            logger.info("Testing IR LED...")
            self.select_led_ir()
            self.led_on()
            time.sleep(0.5)
            self.led_off()
            time.sleep(0.2)

            # Test White LED
            logger.info("Testing White LED...")
            self.select_led_white()
            self.led_on()
            time.sleep(0.5)
            self.led_off()
            time.sleep(0.2)

            # Test sync capture with both LEDs
            logger.info("Testing sync capture with IR LED...")
            self.select_led_ir()
            self.synchronize_capture()

            logger.info("Testing sync capture with White LED...")
            self.select_led_white()
            self.synchronize_capture()

            # Test calibrated powers if available
            if self.calibrated_powers:
                logger.info("Testing calibrated power application...")
                self.apply_calibrated_power_manual("ir")
                time.sleep(0.2)
                self.apply_calibrated_power_manual("white")

            # Return to default (IR)
            self.select_led_ir()

            logger.info("Dual LED sequence test passed with verification and calibration")
            return True
        except Exception as e:
            logger.error(f"LED sequence test failed: {e}")
            return False

    def test_dual_led_switching(self) -> bool:
        """Test dual LED switching with strict verification."""
        try:
            logger.info("Testing dual LED switching with verification...")

            # Test switching between LEDs
            original_led = self.current_led_type

            # Test IR selection
            self.select_led_ir()
            ir_status = self.get_led_status()

            # Test White selection
            self.select_led_white()
            white_status = self.get_led_status()

            # Restore original
            self.select_led_type(original_led)

            success = (
                ir_status["current_led_type"] == "ir"
                and white_status["current_led_type"] == "white"
            )

            if success:
                logger.info("Dual LED switching test passed with verification")
            else:
                logger.error("Dual LED switching test failed verification")
                logger.error(f"IR status: {ir_status}")
                logger.error(f"White status: {white_status}")

            return success
        except Exception as e:
            logger.error(f"Dual LED switching test failed: {e}")
            return False

    def test_calibration_system(self) -> bool:
        """Test the calibration system functionality."""
        try:
            logger.info("Testing LED calibration system...")

            # Test setting calibrated powers
            self.set_calibrated_powers(100, 25, auto_apply=False)

            # Test manual application
            self.apply_calibrated_power_manual("ir")
            time.sleep(0.2)
            self.apply_calibrated_power_manual("white")
            time.sleep(0.2)

            # Test auto-apply
            self.enable_auto_calibration(True)
            self.select_led_type("ir")  # Should auto-apply 100%
            time.sleep(0.2)
            self.select_led_type("white")  # Should auto-apply 25%

            logger.info("LED calibration system test passed")
            return True
        except Exception as e:
            logger.error(f"Calibration system test failed: {e}")
            return False

    def flash_led(self, duration_ms: int = 100) -> bool:
        """Flash LED using sync capture."""
        try:
            self.synchronize_capture()
            return True
        except Exception as e:
            logger.error(f"LED flash failed: {e}")
            return False
