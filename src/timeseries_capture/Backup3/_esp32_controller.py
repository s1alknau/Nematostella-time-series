"""
ESP32Controller (Python) – robust, kompatibel zum TimelapseRecorder & DataManager.
- Kommandos / Antworten 1:1 wie im Projekt (siehe Konstanten)
- Methoden, die der Recorder verwendet:
    select_led_type('ir'|'white')
    begin_sync_pulse() -> float(timestamp)
    get_capture_window_timing() -> dict(capture_delay_sec, ..., led_stabilization_ms, exposure_ms)
    wait_sync_complete(timeout=5.0) -> dict(timing_ms, temperature, humidity, led_type_used, led_duration_ms, led_power_actual)
    read_sensors() -> (temp, humidity)
    is_connected(force_check=False)
    connect(), disconnect(), turn_off_all_leds()
    set_led_power(int 0..100), set_timing(stabilization_ms, exposure_ms), get_led_status(), get_status()
- Qt-Signale sind optional: pyqtSignal, fallback auf Dummy.
"""

# Standard libs
import time
import struct
import threading
import logging

import logging, time, struct, threading
from typing import Optional, Tuple


# PySerial (optional beim Import; Fehler wird gespeichert)
try:
    import serial  # type: ignore
    import serial.tools.list_ports  # type: ignore
except Exception as e:
    serial = None  # noqa: F401
    _serial_import_error = e  # noqa: F401

# QtCore + Signals: immer als pyqtSignal verfügbar (qtpy -> PyQt6 -> PyQt5 -> Shim)
try:
    from qtpy.QtCore import QObject, Signal as pyqtSignal  # type: ignore
except Exception:
    try:
        from PyQt5.QtCore import QObject, pyqtSignal  # type: ignore
    except Exception:
        try:
            from PyQt5.QtCore import QObject, pyqtSignal  # type: ignore
        except Exception:
            # Minimaler Signal-Shim, damit .connect/.emit/.disconnect funktionieren
            class QObject:  # type: ignore
                pass

            class _SignalShim:
                def __init__(self, *_a, **_k):
                    self._subs = []

                def connect(self, slot):
                    if callable(slot):
                        self._subs.append(slot)

                def emit(self, *args, **kwargs):
                    for fn in list(self._subs):
                        try:
                            fn(*args, **kwargs)
                        except Exception:
                            pass

                def disconnect(self, slot=None):
                    if slot is None:
                        self._subs.clear()
                    else:
                        self._subs = [f for f in self._subs if f is not slot]

            def pyqtSignal(*_a, **_k):  # type: ignore
                return _SignalShim()


logger = logging.getLogger(__name__)


class ESP32Controller(QObject):
    # ====== Kommandos ======
    CMD_LED_ON = 0x01
    CMD_LED_OFF = 0x00
    CMD_STATUS = 0x02
    CMD_SYNC_CAPTURE = 0x0C
    CMD_SET_LED_POWER = 0x10
    CMD_SET_TIMING = 0x11
    CMD_SET_CAMERA_TYPE = 0x13
    CMD_SELECT_LED_IR = 0x20
    CMD_SELECT_LED_WHITE = 0x21
    CMD_LED_DUAL_OFF = 0x22
    CMD_GET_LED_STATUS = 0x23
    CMD_SYNC_CAPTURE_DUAL = 0x2C
    # ====== Antworten ======
    RESPONSE_LED_ON_ACK = 0xAA
    RESPONSE_SYNC_COMPLETE = 0x1B
    RESPONSE_TIMING_SET = 0x21
    RESPONSE_ACK_ON = 0x01
    RESPONSE_ACK_OFF = 0x02
    RESPONSE_STATUS_ON = 0x11
    RESPONSE_STATUS_OFF = 0x10
    RESPONSE_ERROR = 0xFF
    RESPONSE_LED_IR_SELECTED = 0x30
    RESPONSE_LED_WHITE_SELECTED = 0x31
    RESPONSE_LED_STATUS = 0x32
    RESPONSE_SYNC_COMPLETE = 0x1B  # first byte of 7-byte response
    # ====== Kamera-Typen ======
    CAMERA_TYPE_HIK_GIGE = 1
    CAMERA_TYPE_USB_GENERIC = 2

    # ====== Signale ======
    sensor_data_received = pyqtSignal(float, float)
    led_status_changed = pyqtSignal(bool, int)
    connection_status_changed = pyqtSignal(bool)

    def _initialize_led_state_safe(self):
        """Initialize LED state after connection."""
        try:
            # Ensure both LEDs are off initially
            self.turn_off_all_leds()
            time.sleep(0.1)

            # Set timing parameters
            self.set_timing(
                stabilization_ms=self.led_stabilization_ms, exposure_ms=self.exposure_ms
            )

            # Select default LED
            self.select_led_type(self.current_led_type)

            logger.info(f"LED state initialized: {self.current_led_type}, power={self.led_power}%")
        except Exception as e:
            logger.warning(f"LED initialization failed: {e}")

    def __init__(
        self,
        imswitch_main_controller=None,
        port: Optional[str] = None,
        baudrate: int = 115200,
        read_timeout: float = 2.0,
        write_timeout: float = 1.0,
    ):
        super().__init__()

        if serial is None:
            raise RuntimeError(f"pyserial nicht verfügbar: {_serial_import_error}")

        self.imswitch_main = imswitch_main_controller
        self.esp32_port: Optional[str] = port
        self.baudrate = baudrate
        self.read_timeout = float(read_timeout)
        self.write_timeout = float(write_timeout)

        # Verbindungszustand
        self.serial_connection: Optional[serial.Serial] = None
        self.connected = False
        self._comm_lock = threading.RLock()

        # LED / Timing
        self.current_led_type = "ir"  # 'ir' | 'white'
        self.led_power = 100  # 0..100 (applied to the currently selected LED)
        self.led_stabilization_ms = 1000  # consider 1000 to match firmware default
        self.exposure_ms = 10

        # --- NEW: per-LED stored powers (sliders write here; auto-applied on select_led_type) ---
        self.ir_led_power = 100
        self.white_led_power = 50

        # LED Zustände (nur Info)
        self.led_ir_state = False
        self.led_white_state = False
        self.led_on_state = False

        # --- NEW: sync/pulse bookkeeping for begin_sync_pulse()/wait_sync_complete() ---
        self._awaiting_sync = False
        self._pulse_started_at = 0.0
        self._last_sync_response = None

        # --- NEW: ImSwitch integration flags (used by connect_via_imswitch / protection) ---
        self.imswitch_managed = False
        self.esp32_device = None
        self._connection_method = None  # 'direct' or 'imswitch'

        # Kalibrierung (optional)
        self.calibrated_powers = {}
        self.auto_apply_calibration = False

        # Reconnect-Hilfe
        self._consecutive_failures = 0
        self._max_failures_before_reconnect = 3
        self._last_successful_command = 0.0

        # Port ermitteln, falls nicht gesetzt
        if self.esp32_port is None:
            self.esp32_port = self._get_esp32_port()

    # ======================================================================
    # Port-Ermittlung
    # ======================================================================
    def _get_esp32_port(self) -> Optional[str]:
        # ImSwitch Config probieren
        try:
            if self.imswitch_main and hasattr(self.imswitch_main, "_config"):
                cfg = self.imswitch_main._config
                devs = (cfg or {}).get("rs232devices", {})
                esp_cfg = devs.get("ESP32", {})
                port = esp_cfg.get("managerProperties", {}).get("serialport")
                if port:
                    logger.info(f"ESP32-Port aus ImSwitch-Config: {port}")
                    return port
        except Exception as e:
            logger.debug(f"Port aus ImSwitch-Config nicht lesbar: {e}")

        # Auto-Detect
        try:
            for p in serial.tools.list_ports.comports():
                desc = (p.description or "").lower()
                if any(k in desc for k in ["esp32", "cp210", "ch340", "ftdi", "silicon labs"]):
                    logger.info(f"ESP32-Port auto-detected: {p.device}")
                    return p.device
        except Exception as e:
            logger.debug(f"Auto-Detect fehlgeschlagen: {e}")

        logger.warning("Kein ESP32-Port gefunden (wird beim connect() benötigt)")
        return None

    # ======================================================================
    # Verbindung
    # ======================================================================
    def connect(self) -> bool:
        """Sichere Verbindung inkl. Entschärfung möglicher ImSwitch Zugriffe."""
        return self.connect_with_imswitch_protection()

    def connect_via_imswitch(self) -> bool:
        if self.imswitch_main is None:
            return False
        try:
            mgr = getattr(self.imswitch_main, "rs232sManager", None)
            if not mgr or not hasattr(mgr, "_rs232s"):
                return False
            devices = mgr._rs232s
            dev = devices.get("ESP32") or next(
                (d for n, d in devices.items() if "esp32" in n.lower()), None
            )
            if not dev:
                return False
            serial_obj = getattr(dev, "_serial", None)
            if serial_obj and getattr(serial_obj, "is_open", False):
                self.esp32_device = dev
                self.serial_connection = serial_obj
                self.connected = True
                self.imswitch_managed = True
                self._connection_method = "imswitch"
                self.connection_status_changed.emit(True)
                try:
                    self._initialize_led_state_safe()
                except Exception:
                    pass
                return True
            return False
        except Exception as e:
            logger.error(f"connect_via_imswitch failed: {e}")
            return False

    def connect_with_imswitch_protection(self) -> bool:
        """
        Open a direct serial connection safely (pauses ImSwitch live view if present).
        Your widget already falls back to this when connect_via_imswitch() returns False.
        """
        paused = False
        try:
            if self.imswitch_main and hasattr(self.imswitch_main, "liveViewWidget"):
                lv = self.imswitch_main.liveViewWidget
                if hasattr(lv, "pauseStream"):
                    lv.pauseStream()
                    paused = True
        except Exception:
            pass

        try:
            if serial is None:
                raise RuntimeError(f"pyserial not available: {_serial_import_error}")

            # Ensure we have a port
            if not getattr(self, "esp32_port", None):
                if hasattr(self, "_get_esp32_port"):
                    self.esp32_port = self._get_esp32_port()
            if not getattr(self, "esp32_port", None):
                raise RuntimeError("No ESP32 port configured or auto-detected")

            # Close any previous direct serial
            if self.serial_connection and not self.imswitch_managed:
                try:
                    self.serial_connection.close()
                except Exception:
                    pass
                self.serial_connection = None

            self.serial_connection = serial.Serial(
                port=self.esp32_port,
                baudrate=115200,
                timeout=2.0,
                write_timeout=1.0,
            )

            time.sleep(2.0)  # allow USB reset

            # Clean buffers
            try:

                self._clear_serial_buffers()
                if getattr(self.serial_connection, "in_waiting", 0) > 0:
                    self.serial_connection.read(self.serial_connection.in_waiting)
            except Exception:
                pass

            self.connected = True
            self.imswitch_managed = False
            self._connection_method = "direct"
            self.connection_status_changed.emit(True)

            try:
                self._initialize_led_state_safe()
            except Exception:
                pass

            logger.info("ESP32 connected (direct)")
            return True
        except Exception as e:
            logger.error(f"connect_with_imswitch_protection failed: {e}")
            self.connected = False
            self.connection_status_changed.emit(False)
            return False
        finally:
            if paused:
                try:
                    lv = self.imswitch_main.liveViewWidget
                    if hasattr(lv, "resumeStream"):
                        lv.resumeStream()
                except Exception:
                    pass

    def _clear_serial_buffers(self):
        s = self.serial_connection
        if not s:
            return
        try:
            # input
            if hasattr(s, "reset_input_buffer"):
                s.reset_input_buffer()  # type: ignore[attr-defined]
            elif hasattr(s, "flushInput"):
                s.flushInput()  # type: ignore[attr-defined]
            else:
                # last resort: drain whatever is waiting
                try:
                    if getattr(s, "in_waiting", 0):
                        s.read(s.in_waiting)
                except Exception:
                    pass

            # output
            if hasattr(s, "reset_output_buffer"):
                s.reset_output_buffer()  # type: ignore[attr-defined]
            elif hasattr(s, "flushOutput"):
                s.flushOutput()  # type: ignore[attr-defined]
        except Exception as e:
            logger.debug(f"Buffer clear warning: {e}")

    def disconnect(self):
        with self._comm_lock:
            try:
                if self.serial_connection:
                    try:
                        # sicherheitshalber beide LEDs aus
                        self.turn_off_all_leds()
                    except Exception:
                        pass
                    try:
                        self.serial_connection.close()
                    except Exception:
                        pass
                self.serial_connection = None
            finally:
                self.connected = False
                self.connection_status_changed.emit(False)
                logger.info("ESP32 getrennt")

    def is_connected(self, force_check: bool = False) -> bool:
        if not (self.connected and self.serial_connection):
            return False
        if not force_check:
            return True
        try:
            ok = self._test_connection()
            if ok:
                self._consecutive_failures = 0
                self._last_successful_command = time.time()
            else:
                self._consecutive_failures += 1
                if self._consecutive_failures >= self._max_failures_before_reconnect:
                    self.connected = False
                    self.connection_status_changed.emit(False)
            return ok
        except Exception:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._max_failures_before_reconnect:
                self.connected = False
                self.connection_status_changed.emit(False)
            return False

    # ======================================================================
    # Low-Level I/O
    # ======================================================================
    def _send_byte(self, val: int):
        if not (self.connected and self.serial_connection):
            raise RuntimeError("ESP32 nicht verbunden")
        self.serial_connection.write(bytes([val]))
        self.serial_connection.flush()

    def _send_bytes(self, data: bytes):
        if not (self.connected and self.serial_connection):
            raise RuntimeError("ESP32 nicht verbunden")
        self.serial_connection.write(data)
        self.serial_connection.flush()

    def _read_bytes(self, n: int, timeout: float) -> Optional[bytes]:
        """Liest exakt n Bytes (oder None bei Timeout)."""
        if not (self.connected and self.serial_connection):
            return None
        end_t = time.time() + max(0.01, float(timeout))
        buf = bytearray()
        while len(buf) < n and time.time() < end_t:
            iw = getattr(self.serial_connection, "in_waiting", 0)
            if iw:
                chunk = self.serial_connection.read(min(n - len(buf), iw))
                if chunk:
                    buf.extend(chunk)
                    continue
            # falls nix anliegt, kurz schlafen
            time.sleep(0.005)
        return bytes(buf) if len(buf) == n else None

    def _wait_for_ack(self, expected: int, timeout: float = 1.0) -> bool:
        data = self._read_bytes(1, timeout)
        if not data:
            return False
        if data[0] == expected:
            return True
        if data[0] == self.RESPONSE_ERROR:
            raise RuntimeError("ESP32 meldet Fehler (RESPONSE_ERROR)")
        # evtl. „falsche“ Bytes im Buffer – als Fail behandeln
        return False

    def _test_connection(self) -> bool:
        try:
            with self._comm_lock:
                # Buffer räumen
                if self.serial_connection and self.serial_connection.in_waiting:
                    self.serial_connection.read(self.serial_connection.in_waiting)

                self._send_byte(self.CMD_STATUS)
                resp = self._read_status_response(timeout=2.0)
                return resp is not None
        except Exception:
            return False

    # ========================================================================
    # HIGH-LEVEL LED CONTROL METHODS (ADD TO ESP32CONTROLLER)
    # ========================================================================

    def turn_on_ir_led(self, power: int = None) -> bool:
        """
        Turn on IR LED at specified power.

        Args:
            power: LED power (0-100). If None, uses current ir_power setting.

        Returns:
            True if successful
        """
        if not self.is_connected():
            raise RuntimeError("ESP32 not connected")

        if power is None:
            power = self.led_power_ir

        if power < 0 or power > 100:
            raise ValueError(f"Power must be 0-100, got {power}")

        try:
            print(f"\n>>> turn_on_ir_led(power={power})")

            # Set IR power first
            self.set_ir_power(power)

            # Select IR LED
            self.select_led_type("ir")

            # Turn on
            self.led_on()

            print(f">>> IR LED ON at {power}%")
            return True

        except Exception as e:
            print(f">>> turn_on_ir_led failed: {e}")
            raise RuntimeError(f"Failed to turn on IR LED: {e}")

    def turn_off_ir_led(self) -> bool:
        """Turn off IR LED."""
        if not self.is_connected():
            raise RuntimeError("ESP32 not connected")

        try:
            print("\n>>> turn_off_ir_led()")

            # Select IR LED (if not already)
            if self.current_led_type != "ir":
                self.select_led_type("ir")

            # Turn off
            self.led_off()

            print(">>> IR LED OFF")
            return True

        except Exception as e:
            print(f">>> turn_off_ir_led failed: {e}")
            raise RuntimeError(f"Failed to turn off IR LED: {e}")

    def turn_on_white_led(self, power: int = None) -> bool:
        """
        Turn on White LED at specified power.

        Args:
            power: LED power (0-100). If None, uses current white_power setting.

        Returns:
            True if successful
        """
        if not self.is_connected():
            raise RuntimeError("ESP32 not connected")

        if power is None:
            power = self.led_power_white

        if power < 0 or power > 100:
            raise ValueError(f"Power must be 0-100, got {power}")

        try:
            print(f"\n>>> turn_on_white_led(power={power})")

            # Set White power first
            self.set_white_power(power)

            # Select White LED
            self.select_led_type("white")

            # Turn on
            self.led_on()

            print(f">>> White LED ON at {power}%")
            return True

        except Exception as e:
            print(f">>> turn_on_white_led failed: {e}")
            raise RuntimeError(f"Failed to turn on White LED: {e}")

    def turn_off_white_led(self) -> bool:
        """Turn off White LED."""
        if not self.is_connected():
            raise RuntimeError("ESP32 not connected")

        try:
            print("\n>>> turn_off_white_led()")

            # Select White LED (if not already)
            if self.current_led_type != "white":
                self.select_led_type("white")

            # Turn off
            self.led_off()

            print(">>> White LED OFF")
            return True

        except Exception as e:
            print(f">>> turn_off_white_led failed: {e}")
            raise RuntimeError(f"Failed to turn off White LED: {e}")

    def set_ir_power_and_update(self, power: int) -> bool:
        """
        Set IR LED power and update if currently on.

        Args:
            power: LED power (0-100)

        Returns:
            True if successful
        """
        if not self.is_connected():
            raise RuntimeError("ESP32 not connected")

        try:
            # Set power
            self.set_ir_power(power)

            # If IR LED is currently on, the firmware will update PWM automatically
            print(f">>> IR power set to {power}% (live update if LED is on)")
            return True

        except Exception as e:
            print(f">>> set_ir_power_and_update failed: {e}")
            raise RuntimeError(f"Failed to set IR power: {e}")

    def set_white_power_and_update(self, power: int) -> bool:
        """
        Set White LED power and update if currently on.

        Args:
            power: LED power (0-100)

        Returns:
            True if successful
        """
        if not self.is_connected():
            raise RuntimeError("ESP32 not connected")

        try:
            # Set power
            self.set_white_power(power)

            # If White LED is currently on, the firmware will update PWM automatically
            print(f">>> White power set to {power}% (live update if LED is on)")
            return True

        except Exception as e:
            print(f">>> set_white_power_and_update failed: {e}")
            raise RuntimeError(f"Failed to set White power: {e}")

    def set_ir_power(self, power: int) -> bool:
        """Set IR LED power specifically (independent of selection)."""
        if not self.is_connected():
            raise RuntimeError("ESP32 not connected")

        if power < 0 or power > 100:
            raise ValueError(f"Power must be 0-100, got {power}")

        with self._comm_lock:
            try:
                # Clear buffer
                if self.serial_connection.in_waiting > 0:
                    self.serial_connection.read(self.serial_connection.in_waiting)

                # Send CMD_SET_IR_POWER (0x24)
                self._send_byte(0x24)
                self._send_byte(power)

                time.sleep(0.05)

                # Update internal state
                self.led_power_ir = power

                print(f">>> IR power set to {power}%")
                return True

            except Exception as e:
                print(f">>> set_ir_power failed: {e}")
                raise RuntimeError(f"Failed to set IR power: {e}")

    def set_white_power(self, power: int) -> bool:
        """Set White LED power specifically (independent of selection)."""
        if not self.is_connected():
            raise RuntimeError("ESP32 not connected")

        if power < 0 or power > 100:
            raise ValueError(f"Power must be 0-100, got {power}")

        with self._comm_lock:
            try:
                # Clear buffer
                if self.serial_connection.in_waiting > 0:
                    self.serial_connection.read(self.serial_connection.in_waiting)

                # Send CMD_SET_WHITE_POWER (0x25)
                self._send_byte(0x25)
                self._send_byte(power)

                time.sleep(0.05)

                # Update internal state
                self.led_power_white = power

                print(f">>> White power set to {power}%")
                return True

            except Exception as e:
                print(f">>> set_white_power failed: {e}")
                raise RuntimeError(f"Failed to set White power: {e}")

    def turn_on_ir_led(self, power: int = None) -> bool:
        """Turn on IR LED at specified power (high-level method)."""
        if not self.is_connected():
            raise RuntimeError("ESP32 not connected")

        if power is None:
            power = getattr(self, "led_power_ir", 100)

        if power < 0 or power > 100:
            raise ValueError(f"Power must be 0-100, got {power}")

        try:
            print(f"\n>>> turn_on_ir_led(power={power})")

            # Set IR power
            self.set_ir_power(power)

            # Select IR LED
            self.select_led_type("ir")

            # Turn on (with simplified ACK check)
            with self._comm_lock:
                if self.serial_connection.in_waiting > 0:
                    self.serial_connection.read(self.serial_connection.in_waiting)

                self._send_byte(self.CMD_LED_ON)
                time.sleep(0.05)

            print(f">>> IR LED ON at {power}%")
            return True

        except Exception as e:
            print(f">>> turn_on_ir_led failed: {e}")
            raise RuntimeError(f"Failed to turn on IR LED: {e}")

    def turn_off_ir_led(self) -> bool:
        """Turn off IR LED (high-level method)."""
        if not self.is_connected():
            raise RuntimeError("ESP32 not connected")

        try:
            print("\n>>> turn_off_ir_led()")

            # Select IR LED if not already
            if getattr(self, "current_led_type", None) != "ir":
                self.select_led_type("ir")

            # Turn off (with simplified ACK check)
            with self._comm_lock:
                if self.serial_connection.in_waiting > 0:
                    self.serial_connection.read(self.serial_connection.in_waiting)

                self._send_byte(self.CMD_LED_OFF)
                time.sleep(0.05)

            print(">>> IR LED OFF")
            return True

        except Exception as e:
            print(f">>> turn_off_ir_led failed: {e}")
            raise RuntimeError(f"Failed to turn off IR LED: {e}")

    def turn_on_white_led(self, power: int = None) -> bool:
        """Turn on White LED at specified power (high-level method)."""
        if not self.is_connected():
            raise RuntimeError("ESP32 not connected")

        if power is None:
            power = getattr(self, "led_power_white", 100)

        if power < 0 or power > 100:
            raise ValueError(f"Power must be 0-100, got {power}")

        try:
            print(f"\n>>> turn_on_white_led(power={power})")

            # Set White power
            self.set_white_power(power)

            # Select White LED
            self.select_led_type("white")

            # Turn on (with simplified ACK check)
            with self._comm_lock:
                if self.serial_connection.in_waiting > 0:
                    self.serial_connection.read(self.serial_connection.in_waiting)

                self._send_byte(self.CMD_LED_ON)
                time.sleep(0.05)

            print(f">>> White LED ON at {power}%")
            return True

        except Exception as e:
            print(f">>> turn_on_white_led failed: {e}")
            raise RuntimeError(f"Failed to turn on White LED: {e}")

    def turn_off_white_led(self) -> bool:
        """Turn off White LED (high-level method)."""
        if not self.is_connected():
            raise RuntimeError("ESP32 not connected")

        try:
            print("\n>>> turn_off_white_led()")

            # Select White LED if not already
            if getattr(self, "current_led_type", None) != "white":
                self.select_led_type("white")

            # Turn off (with simplified ACK check)
            with self._comm_lock:
                if self.serial_connection.in_waiting > 0:
                    self.serial_connection.read(self.serial_connection.in_waiting)

                self._send_byte(self.CMD_LED_OFF)
                time.sleep(0.05)

            print(">>> White LED OFF")
            return True

        except Exception as e:
            print(f">>> turn_off_white_led failed: {e}")
            raise RuntimeError(f"Failed to turn off White LED: {e}")

    def led_on(self) -> bool:
        """Turn current LED ON; waits for 5-byte status ACK."""
        with self._comm_lock:
            if not self.serial_connection:
                raise RuntimeError("ESP32 not connected")
            self._send_byte(self.CMD_LED_ON)
            resp = self._read_status_response(timeout=3.0)
            if not resp or not resp["led_on"]:
                raise RuntimeError("LED failed to turn on (no ACK)")
            if self.current_led_type == "ir":
                self.led_ir_state = True
            else:
                self.led_white_state = True
            self.led_on_state = True
            self.led_status_changed.emit(True, self.led_power)
            return True

    def led_off(self) -> bool:
        """Turn current LED OFF; waits for 5-byte status ACK."""
        with self._comm_lock:
            if not self.serial_connection:
                raise RuntimeError("ESP32 not connected")
            self._send_byte(self.CMD_LED_OFF)
            resp = self._read_status_response(timeout=3.0)
            if not resp or resp["led_on"]:
                raise RuntimeError("LED failed to turn off (no ACK)")
            if self.current_led_type == "ir":
                self.led_ir_state = False
            else:
                self.led_white_state = False
            self.led_on_state = False
            self.led_status_changed.emit(False, 0)
            return True

    def synchronize_capture(self, dual: bool = False) -> dict:
        """
        Trigger a synchronized capture on the ESP32.
        dual=False -> single-LED (0x0C, current selection)
        dual=True  -> dual-LED  (0x2C, IR+White together)

        Returns dict with at least: timing_ms, temperature, humidity
        and adds: mode, led_type_used, led_power_actual, timestamp.
        """
        import time

        lock = getattr(self, "_comm_lock", None)
        if lock is None:
            from threading import RLock

            self._comm_lock = RLock()
            lock = self._comm_lock

        with lock:
            if not self.serial_connection:
                raise RuntimeError("ESP32 not connected")

            # Clean any stale bytes before issuing a sync
            try:
                if hasattr(self.serial_connection, "reset_input_buffer"):
                    self.serial_connection.reset_input_buffer()
                else:
                    pending = getattr(self.serial_connection, "in_waiting", 0) or 0
                    if pending:
                        self.serial_connection.read(pending)
                if hasattr(self.serial_connection, "reset_output_buffer"):
                    self.serial_connection.reset_output_buffer()
            except Exception:
                pass

            # Pick command
            cmd_single = getattr(self, "CMD_SYNC_CAPTURE", 0x0C)
            cmd_dual = getattr(self, "CMD_SYNC_CAPTURE_DUAL", 0x2C)
            cmd = cmd_dual if dual else cmd_single

            # Send command
            try:
                self._send_byte(cmd)
            except Exception as e:
                raise RuntimeError(
                    f"Failed to send {'dual' if dual else 'single'} sync command: {e}"
                )

            # Read and augment response (blocks until LED pulse finished)
            resp = self.wait_sync_complete(timeout=5.0)
            if not resp:
                raise RuntimeError("No sync response from ESP32")

            resp["timestamp"] = time.time()
            resp["mode"] = "dual" if dual else "single"

            if dual:
                resp["led_type_used"] = "both"
                resp["leds_used"] = ["ir", "white"]
                ir_p = getattr(self, "led_ir_power", None)
                white_p = getattr(self, "led_white_power", None)
                if ir_p is None:
                    ir_p = getattr(self, "led_power", None)
                if white_p is None:
                    white_p = getattr(self, "led_power", None)
                resp["led_power_actual"] = {"ir": ir_p, "white": white_p}
            else:
                current = getattr(self, "current_led_type", "ir")
                resp["led_type_used"] = current
                power = getattr(self, f"led_{current}_power", None)
                if power is None:
                    power = getattr(self, "led_power", None)
                resp["led_power_actual"] = power

            self._last_successful_command = time.time()
            return resp

    def _read_sync_response(self, timeout: float = 5.0) -> dict:
        """
        Wait for 7 bytes: [0]=0x1B, [1..2]=timing_ms, [3..4]=temp*10 (signed),
        [5..6]=humid*10 (unsigned).
        """
        end = time.time() + timeout
        ser = self.serial_connection
        # find header 0x1B
        while time.time() < end:
            b = ser.read(1)
            if not b:
                continue
            if b[0] == self.RESPONSE_SYNC_COMPLETE:
                break
        else:
            raise TimeoutError("SYNC header 0x1B not received")

        rest = bytearray()
        while len(rest) < 6 and time.time() < end:
            chunk = ser.read(6 - len(rest))
            if chunk:
                rest.extend(chunk)

        if len(rest) != 6:
            raise TimeoutError("Incomplete SYNC payload")

        timing_ms = (rest[0] << 8) | rest[1]
        # temp is signed int16 in deci-°C
        t_raw = (rest[2] << 8) | rest[3]
        if t_raw & 0x8000:
            t_raw = t_raw - 0x10000
        temperature_c = t_raw / 10.0
        humidity = ((rest[4] << 8) | rest[5]) / 10.0

        return {
            "timing_ms": timing_ms,
            "temperature": float(temperature_c),
            "humidity": float(humidity),
        }

    def select_led_ir(self) -> bool:
        with self._comm_lock:
            print(">>> ESP32: Sending CMD_SELECT_LED_IR (0x20)...")
            self._send_byte(self.CMD_SELECT_LED_IR)
            ok = self._wait_for_ack(self.RESPONSE_LED_IR_SELECTED, timeout=2.0)
            if ok:
                time.sleep(0.1)  # Hardware-Stabilisierung
                self.current_led_type = "ir"
                print(">>> ESP32: IR LED verified")
            return ok

    def select_led_white(self) -> bool:
        with self._comm_lock:
            print(">>> ESP32: Sending CMD_SELECT_LED_WHITE (0x21)...")
            self._send_byte(self.CMD_SELECT_LED_WHITE)
            ok = self._wait_for_ack(self.RESPONSE_LED_WHITE_SELECTED, timeout=2.0)
            if ok:
                time.sleep(0.1)
                self.current_led_type = "white"
                print(">>> ESP32: White LED verified")
            return ok

    def select_led_type(self, led_type: str) -> bool:
        """Select LED type. Reset sync flag if needed."""
        lt = (led_type or "").lower()
        print(f"\n>>> ESP32: select_led_type('{led_type}') called")

        # ✅ FIX: Reset flag if it's stuck
        if getattr(self, "_awaiting_sync", False):
            print(">>> ESP32: WARNING - _awaiting_sync was True, resetting it")
            self._awaiting_sync = False
            time.sleep(0.1)  # Brief pause

        print(
            f">>> ESP32: Current state - connected={self.connected}, current_led={self.current_led_type}"
        )

        if not self.is_connected():
            print(">>> ESP32: Not connected -> connecting...")
            self.connect()

        if lt in ("ir", "infrared", "night"):
            print(">>> ESP32: Selecting IR LED...")
            return self.select_led_ir()
        elif lt in ("white", "whitelight", "day", "cob"):
            print(">>> ESP32: Selecting White LED...")
            return self.select_led_white()
        else:
            raise ValueError(f"Unknown led_type: {led_type}")

    def set_led_power(self, power: int) -> bool:
        power = int(max(0, min(100, power)))
        print(f">>> ESP32: Setting LED power to {power}%")  # ← ADD THIS

        with self._comm_lock:
            self._send_byte(self.CMD_SET_LED_POWER)
            self._send_byte(power)
            ok = self._wait_for_ack(self.RESPONSE_ACK_ON, timeout=2.0)
            if ok:
                self.led_power = power
                print(f">>> ESP32: LED power confirmed at {power}%")  # ← ADD THIS
                self.led_status_changed.emit(self.led_on_state, self.led_power)
                logger.info(f"LED power set to {power}%")
            else:
                print(f">>> ESP32: LED power setting FAILED!")  # ← ADD THIS
            return ok

    def set_timing(
        self,
        stabilization_ms: int = 300,
        exposure_ms: Optional[int] = None,
        delay_ms: Optional[int] = None,
    ) -> bool:
        if exposure_ms is None and delay_ms is not None:
            exposure_ms = delay_ms
        if exposure_ms is None:
            exposure_ms = self.exposure_ms
        stab = max(10, min(10000, int(stabilization_ms)))
        expo = max(0, min(30000, int(exposure_ms)))

        with self._comm_lock:
            payload = bytes([self.CMD_SET_TIMING]) + struct.pack(">HH", stab, expo)
            self._send_bytes(payload)
            ok = self._wait_for_ack(self.RESPONSE_TIMING_SET, timeout=2.0)
            if ok:
                self.led_stabilization_ms = stab
                self.exposure_ms = expo
                logger.info(f"Timing set: stabilization={stab}ms, exposure={expo}ms")
            return ok

    def set_camera_type(self, camera_type: int = None) -> bool:
        if camera_type is None:
            camera_type = self.CAMERA_TYPE_HIK_GIGE
        with self._comm_lock:
            self._send_bytes(bytes([self.CMD_SET_CAMERA_TYPE, int(camera_type)]))
            return self._wait_for_ack(self.RESPONSE_ACK_ON, timeout=2.0)

    def turn_off_all_leds(self) -> bool:
        with self._comm_lock:
            self._send_byte(self.CMD_LED_DUAL_OFF)
            ok = self._wait_for_ack(self.RESPONSE_ACK_OFF, timeout=2.0)
            if ok:
                self.led_ir_state = False
                self.led_white_state = False
                self.led_on_state = False
                self.led_status_changed.emit(False, 0)
            return ok

    # ======================================================================
    # Sync-Capture (LED-Puls + Bildaufnahme im Recorder)
    # ======================================================================

    def begin_sync_pulse(self, dual: bool = False) -> float:
        """
        Send sync command and wait for LED_ON_ACK.
        Returns the timestamp when LED actually turned ON.
        """
        with self._comm_lock:
            if not self.serial_connection:
                raise RuntimeError("ESP32 not connected")

            # Clear stale input BEFORE sending command
            try:
                if hasattr(self.serial_connection, "reset_input_buffer"):
                    self.serial_connection.reset_input_buffer()
                waiting = getattr(self.serial_connection, "in_waiting", 0)
                if waiting > 0:
                    print(f">>> ESP32: Clearing {waiting} stale bytes before sync")
                    self.serial_connection.read(waiting)
            except Exception as e:
                logger.debug(f"Buffer clear warning: {e}")

            # Send sync command
            cmd = self.CMD_SYNC_CAPTURE_DUAL if dual else self.CMD_SYNC_CAPTURE
            print(f">>> ESP32: Sending sync command (dual={dual}, cmd=0x{cmd:02X})...")
            self._send_byte(cmd)

            # Wait for LED_ON_ACK (0xAA) - this tells us LED is actually ON
            ack_timeout = 1.0
            start_wait = time.time()

            while time.time() - start_wait < ack_timeout:
                if self.serial_connection.in_waiting > 0:
                    ack_byte = self.serial_connection.read(1)
                    if ack_byte and ack_byte[0] == self.RESPONSE_LED_ON_ACK:
                        pulse_start = time.time()
                        print(f">>> ESP32: LED ON confirmed at T={pulse_start:.6f}")
                        print(
                            f">>> ESP32: ACK received after {(pulse_start - start_wait)*1000:.1f}ms"
                        )

                        self._awaiting_sync = True
                        self._pulse_started_at = pulse_start
                        return pulse_start
                    else:
                        # Got wrong byte - log it but keep waiting
                        print(
                            f">>> ESP32: Warning - expected ACK 0x{self.RESPONSE_LED_ON_ACK:02X}, got 0x{ack_byte[0]:02X}"
                        )

                time.sleep(0.001)  # Small delay to avoid busy-wait

            # Timeout - no ACK received
            elapsed = time.time() - start_wait
            raise RuntimeError(f"No LED_ON_ACK received from ESP32 after {elapsed:.2f}s")

    def verify_timing_sync(self) -> bool:
        """
        Verify that ESP32 firmware has the correct timing parameters.
        Does a test pulse and checks if the reported duration matches expectations.
        Returns True if timing is correct, False otherwise.
        """
        try:
            # Get what Python thinks the timing is
            expected_stab = self.led_stabilization_ms
            expected_exp = self.exposure_ms
            expected_duration = expected_stab + expected_exp

            print(f"\n>>> ESP32 TIMING VERIFICATION:")
            print(f">>> Python expects: stab={expected_stab}ms, exp={expected_exp}ms")
            print(f">>> Expected total duration: {expected_duration}ms")

            # Do a test pulse and check the reported duration
            print(">>> Doing test pulse...")
            pulse_start = self.begin_sync_pulse(dual=False)
            resp = self.wait_sync_complete(timeout=10.0)

            actual_duration = resp.get("led_duration_ms", 0)

            print(f">>> Actual duration from firmware: {actual_duration}ms")

            # Allow 5% tolerance
            tolerance = expected_duration * 0.05
            diff = abs(actual_duration - expected_duration)

            if diff > tolerance:
                logger.warning(
                    f"⚠️ Timing mismatch: got {actual_duration}ms, expected {expected_duration}ms (diff: {diff}ms)"
                )
                print(
                    f">>> ⚠️ TIMING MISMATCH: difference of {diff}ms exceeds tolerance ({tolerance}ms)"
                )
                return False

            logger.info(
                f"✓ Timing verification passed: {actual_duration}ms (expected {expected_duration}ms)"
            )
            print(
                f">>> ✓ TIMING VERIFIED: {actual_duration}ms matches expected {expected_duration}ms"
            )
            return True

        except Exception as e:
            logger.error(f"Timing verification failed: {e}")
            print(f">>> ✗ TIMING VERIFICATION FAILED: {e}")
            return False

    def get_capture_window_timing(self) -> dict:
        """
        Compute when to grab the frame relative to the sync pulse:
        LED ON → stabilize → (exposure) → LED OFF
        We capture at the exposure midpoint for maximum margin.
        """
        stabilization_sec = float(self.led_stabilization_ms) / 1000.0
        exposure_sec = float(self.exposure_ms) / 1000.0
        capture_delay = stabilization_sec + (exposure_sec * 0.5)

        return {
            "stabilization_sec": stabilization_sec,
            "exposure_sec": exposure_sec,
            "capture_delay_sec": capture_delay,  # used by recorder
            "capture_offset_sec": capture_delay,  # alias (nice to have)
            "total_duration_sec": stabilization_sec + exposure_sec,
            "led_stabilization_ms": int(self.led_stabilization_ms),
            "exposure_ms": int(self.exposure_ms),
        }

    def wait_sync_complete(self, timeout: float = 5.0) -> dict:
        """
        Block until the 7-byte sync response arrives (or timeout).
        Uses _read_sync_response() if available; otherwise does a safe inline read.
        Clears _awaiting_sync and stores _last_sync_response.
        """
        print(f">>> ESP32: Waiting for sync response (timeout={timeout}s)...")
        if not self.serial_connection:
            raise RuntimeError("ESP32 not connected")

        with self._comm_lock:
            # Prefer the shared helper if you added it earlier
            if hasattr(self, "_read_sync_response") and callable(self._read_sync_response):
                resp = self._read_sync_response(timeout=timeout)
            else:
                # Inline robust reader: scan for header 0x1B then read remaining bytes
                HEADER = getattr(self, "RESPONSE_SYNC_COMPLETE", 0x1B)
                start = time.time()
                buf = bytearray()

                # Drain any obvious junk only if a lot is queued
                try:
                    if getattr(self.serial_connection, "in_waiting", 0) > 64:
                        self.serial_connection.read(self.serial_connection.in_waiting)
                except Exception:
                    pass

                while time.time() - start < timeout:
                    b = self.serial_connection.read(1)
                    if not b:
                        continue
                    # sync to header
                    if not buf:
                        if b[0] != HEADER:
                            continue
                        buf.append(b[0])
                        # read the remaining 6 bytes
                        tail = self.serial_connection.read(6)
                        if tail:
                            buf.extend(tail)
                        if len(buf) >= 7:
                            break
                    else:
                        buf.append(b[0])
                        if len(buf) >= 7:
                            break

                if len(buf) != 7 or buf[0] != HEADER:
                    got = len(buf)
                    print(
                        f">>> ESP32: ERROR - Got {got} bytes (header={buf[0]:02X} if any), expected 7"
                    )
                    raise RuntimeError("No sync response from ESP32")

                # Parse big-endian payload: timing(2), temp(2, signed), hum(2, unsigned)
                timing_ms = (buf[1] << 8) | buf[2]
                temp_raw = (buf[3] << 8) | buf[4]
                if temp_raw & 0x8000:  # sign
                    temp_raw -= 0x10000
                hum_raw = (buf[5] << 8) | buf[6]

                resp = {
                    "timing_ms": timing_ms,
                    "temperature": temp_raw / 10.0,
                    "humidity": hum_raw / 10.0,
                }

            # Bookkeeping
            self._awaiting_sync = False
            self._last_sync_response = dict(resp)

            print(">>> ESP32: Sync response received!")
            print(f">>>   - Timing: {resp.get('timing_ms', 0)}ms")
            print(f">>>   - Temperature: {resp.get('temperature', 0.0):.1f}°C")
            print(f">>>   - Humidity: {resp.get('humidity', 0.0):.1f}%")
            print(">>> ESP32: LED pulse is now COMPLETE")

            # Convenience fields expected elsewhere
            resp.setdefault("led_type_used", self.current_led_type)
            resp.setdefault("led_power_actual", self.led_power)
            resp.setdefault("led_duration_ms", resp.get("timing_ms"))

            return resp

    # ======================================================================
    # Status / Sensorik
    # ======================================================================
    def _read_status_response(self, timeout: float = 2.0) -> Optional[dict]:
        """5-Byte Status: [0x10/0x11, T_hi, T_lo, H_hi, H_lo]"""
        data = self._read_bytes(5, timeout)
        if not data or len(data) != 5:
            return None
        header = data[0]
        temp_raw = struct.unpack(">h", data[1:3])[0]
        hum_raw = struct.unpack(">H", data[3:5])[0]
        return {
            "status_code": header,
            "temperature": temp_raw / 10.0,
            "humidity": hum_raw / 10.0,
            "led_on": header == self.RESPONSE_STATUS_ON,
        }

    def read_sensors(self) -> Tuple[float, float]:
        with self._comm_lock:
            # Input spülen
            if self.serial_connection and self.serial_connection.in_waiting:
                self.serial_connection.read(self.serial_connection.in_waiting)
            self._send_byte(self.CMD_STATUS)
            resp = self._read_status_response(timeout=2.0)
            if not resp:
                raise RuntimeError("No response for STATUS")
            t, h = resp["temperature"], resp["humidity"]
            self.sensor_data_received.emit(t, h)
            return t, h

    def _get_led_status_unlocked(self) -> dict:
        # Optional: vorab Buffer räumen
        if self.serial_connection and self.serial_connection.in_waiting:
            self.serial_connection.read(self.serial_connection.in_waiting)
        self._send_byte(self.CMD_GET_LED_STATUS)
        data = self._read_bytes(5, timeout=2.0)
        if not data or len(data) != 5 or data[0] != self.RESPONSE_LED_STATUS:
            # Fallback auf lokalen Zustand
            return self._get_fallback_led_status()
        type_num = data[1]  # 0=IR,1=WHITE
        ir_on = bool(data[2])
        white_on = bool(data[3])
        power_pct = int(data[4])
        self.current_led_type = "ir" if type_num == 0 else "white"
        self.led_ir_state = ir_on
        self.led_white_state = white_on
        self.led_on_state = ir_on or white_on
        self.led_power = power_pct
        return {
            "current_led_type": self.current_led_type,
            "ir_led_state": ir_on,
            "white_led_state": white_on,
            "led_power_percent": power_pct,
            "any_led_on": self.led_on_state,
        }

    def _get_fallback_led_status(self) -> dict:
        return {
            "current_led_type": self.current_led_type,
            "ir_led_state": self.led_ir_state,
            "white_led_state": self.led_white_state,
            "led_power_percent": self.led_power,
            "any_led_on": self.led_ir_state or self.led_white_state,
        }

    def get_led_status(self) -> dict:
        with self._comm_lock:
            try:
                return self._get_led_status_unlocked()
            except Exception:
                return self._get_fallback_led_status()

    # Kalibration tools
    def get_status(self) -> dict:
        with self._comm_lock:
            self._send_byte(self.CMD_STATUS)
            s = self._read_status_response(timeout=2.0)
            if not s:
                raise RuntimeError("No status response")
            led = self.get_led_status()
            timing = self.get_capture_window_timing()
            return {
                "connected": True,
                "led_on": s["led_on"],
                "led_power": self.led_power,
                "temperature": s["temperature"],
                "humidity": s["humidity"],
                "led_stabilization_ms": self.led_stabilization_ms,
                "exposure_ms": self.exposure_ms,
                "capture_delay_sec": timing["capture_delay_sec"],
                "port": self.esp32_port,
                **led,
            }

    def auto_calibrate_led_intensity(
        self, target_intensity: float = 200.0, capture_callback=None, dual_light_mode: bool = False
    ) -> dict:
        """
        Auto-calibrate LED powers to achieve matching intensities.

        Args:
            target_intensity: Desired mean intensity (0-255)
            capture_callback: Function that captures and returns (frame, mean_intensity)
            dual_light_mode: If True, calibrate for dual LED in light phase

        Returns:
            dict with calibrated powers: {'ir': int, 'white': int} or {'ir': int, 'dual': (int, int)}
        """
        print("\n" + "=" * 80)
        print(">>> AUTO-CALIBRATION START")
        print("=" * 80)
        print(f">>> Target intensity: {target_intensity}")
        print(f">>> Dual light mode: {dual_light_mode}")

        if capture_callback is None:
            raise ValueError("capture_callback required - must return (frame, mean_intensity)")

        calibrated_powers = {}

        try:
            # ✅ Ensure clean state
            self._awaiting_sync = False
            self.turn_off_all_leds()
            time.sleep(1.0)

            # ================================================================
            # STEP 1: Calibrate IR LED
            # ================================================================
            print("\n>>> STEP 1: Calibrating IR LED...")
            self.select_led_type("ir")
            time.sleep(0.5)

            ir_power = self._binary_search_power(
                led_type="ir", target_intensity=target_intensity, capture_callback=capture_callback
            )

            calibrated_powers["ir"] = ir_power
            print(f">>> IR LED calibrated: {ir_power}%")

            # ✅ Clean state after binary search
            self._awaiting_sync = False
            time.sleep(0.5)

            # ================================================================
            # STEP 2: Calibrate White LED (or Dual)
            # ================================================================
            if dual_light_mode:
                print("\n>>> STEP 2: Calibrating DUAL LED (IR + White together)...")

                # Binary search for white power to match target (IR at calibrated power)
                white_power = self._binary_search_dual_power(
                    ir_power=ir_power,
                    target_intensity=target_intensity,
                    capture_callback=capture_callback,
                )

                calibrated_powers["dual"] = (ir_power, white_power)
                print(f">>> DUAL LED calibrated: IR={ir_power}%, White={white_power}%")

            else:
                print("\n>>> STEP 2: Calibrating White LED (single)...")
                self.select_led_type("white")
                time.sleep(0.5)

                white_power = self._binary_search_power(
                    led_type="white",
                    target_intensity=target_intensity,
                    capture_callback=capture_callback,
                )

                calibrated_powers["white"] = white_power
                print(f">>> White LED calibrated: {white_power}%")

            # ✅ Clean state after calibration
            self._awaiting_sync = False
            time.sleep(0.5)

            # ================================================================
            # STEP 3: Verification (SIMPLIFIED - no additional captures)
            # ================================================================
            print("\n>>> STEP 3: Verification...")
            print(f">>> Calibration complete - skipping verification to avoid timing issues")
            print(f">>> You can verify manually by starting a recording")

            # Turn off LEDs
            self.turn_off_all_leds()

            print("\n" + "=" * 80)
            print(">>> AUTO-CALIBRATION COMPLETE")
            print(f">>> Results: {calibrated_powers}")
            print("=" * 80)

            return calibrated_powers

        except Exception as e:
            logger.error(f"Auto-calibration failed: {e}")
            print(f"\n>>> AUTO-CALIBRATION FAILED: {e}")

            # ✅ Ensure clean state on error
            self._awaiting_sync = False
            try:
                self.turn_off_all_leds()
            except:
                pass

            raise

    def _binary_search_power(
        self,
        led_type: str,
        target_intensity: float,
        capture_callback,
        tolerance: float = 5.0,
        max_iterations: int = 10,
    ) -> int:
        """Binary search to find LED power that achieves target intensity."""
        print(f">>> Binary search for {led_type.upper()} LED power...")

        # Ensure correct LED is selected
        print(f">>> Selecting {led_type} LED...")
        self.select_led_type(led_type)
        time.sleep(0.5)
        print(f">>> Current LED type confirmed: {self.current_led_type}")

        low_power = 0
        high_power = 100
        best_power = 50
        best_diff = float("inf")

        for iteration in range(max_iterations):
            test_power = (low_power + high_power) // 2

            # Clear buffers
            try:
                if self.serial_connection and self.serial_connection.in_waiting > 0:
                    cleared = self.serial_connection.read(self.serial_connection.in_waiting)
                    if len(cleared) > 0:
                        print(f"    Cleared {len(cleared)} stale bytes")
            except Exception:
                pass

            # Set power with retry
            print(f"    Setting power to {test_power}%...")
            try:
                self.set_led_power(test_power)
            except RuntimeError as e:
                if "RESPONSE_ERROR" in str(e):
                    print(f"    Power set failed, retrying...")
                    time.sleep(0.5)
                    try:
                        self.set_led_power(test_power)
                    except Exception:
                        print(f"    Retry failed, skipping iteration {iteration+1}")
                        continue
                else:
                    raise

            time.sleep(0.3)  # Let ESP32 process

            try:
                # Start LED pulse (will be on for ~1.5 seconds with calibration timing)
                print(f"    Starting LED pulse...")
                pulse_start = self.begin_sync_pulse(dual=False)

                # ✅ CRITICAL: Wait LONGER for both LED stabilization AND Napari update
                stab_sec = self.led_stabilization_ms / 1000.0

                # Add extra time for Napari to receive and display the frame
                # At 30 FPS, Napari updates every ~33ms
                # We want multiple updates to be sure, so wait for LED stab + extra margin
                napari_update_time = 0.3  # 300ms for multiple Napari updates
                total_wait = stab_sec + napari_update_time

                print(
                    f"    Waiting {total_wait:.2f}s (LED stab: {stab_sec:.2f}s + Napari: {napari_update_time:.2f}s)..."
                )
                time.sleep(total_wait)

                # ✅ Force Qt to process events (update Napari)
                try:
                    from qtpy.QtWidgets import QApplication

                    QApplication.processEvents()
                    print(f"    Qt events processed")
                except Exception:
                    pass

                # NOW capture (LED is definitely on and Napari should have updated)
                print(f"    Capturing frame NOW...")
                frame, intensity = capture_callback()
                print(
                    f"    Captured: intensity={intensity:.1f}, frame_mean={float(np.mean(frame)):.1f}"
                )

                # Wait for sync complete
                print(f"    Waiting for sync complete...")
                self.wait_sync_complete(timeout=10.0)  # Longer timeout for calibration
                print(f"    Sync complete")

            except Exception as e:
                print(f"    Iteration {iteration+1}: Capture failed: {e}")
                time.sleep(0.5)
                continue

            diff = abs(intensity - target_intensity)
            print(
                f"    Iteration {iteration+1}: Power {test_power}% → Intensity {intensity:.1f} (diff: {diff:.1f})"
            )

            # Update best
            if diff < best_diff:
                best_diff = diff
                best_power = test_power

            # Check if close enough
            if diff <= tolerance:
                print(f">>> Found optimal power: {test_power}% (intensity: {intensity:.1f})")
                return test_power

            # Adjust search range
            if intensity < target_intensity:
                low_power = test_power + 1
            else:
                high_power = test_power - 1

            # Convergence check
            if low_power > high_power:
                print(f">>> Search converged: {best_power}% (best diff: {best_diff:.1f})")
                return best_power

            # Delay between iterations
            time.sleep(0.3)

        print(f">>> Max iterations reached: {best_power}% (best diff: {best_diff:.1f})")
        return best_power

    def _binary_search_dual_power(
        self,
        ir_power: int,
        target_intensity: float,
        capture_callback,
        tolerance: float = 5.0,
        max_iterations: int = 10,
    ) -> int:
        """Binary search for white LED power in dual mode (IR power fixed)."""
        print(f">>> Binary search for White LED power (IR fixed at {ir_power}%)...")

        # Set IR power
        self.ir_led_power = ir_power

        low_power = 0
        high_power = 100
        best_power = 50
        best_diff = float("inf")

        for iteration in range(max_iterations):
            test_white_power = (low_power + high_power) // 2

            # Set white power
            self.white_led_power = test_white_power
            print(f"    IR={ir_power}%, White={test_white_power}%")

            time.sleep(0.3)

            try:
                # Start dual LED pulse
                pulse_start = self.begin_sync_pulse(dual=True)

                # ✅ CRITICAL: Same long wait as single LED
                stab_sec = self.led_stabilization_ms / 1000.0
                napari_update_time = 0.3
                total_wait = stab_sec + napari_update_time

                print(f"    Waiting {total_wait:.2f}s for LED + Napari...")
                time.sleep(total_wait)

                # Force Qt events
                try:
                    from qtpy.QtWidgets import QApplication

                    QApplication.processEvents()
                except Exception:
                    pass

                # Capture
                _, intensity = capture_callback()

                # Wait for complete
                self.wait_sync_complete(timeout=10.0)

            except Exception as e:
                print(f"    Iteration {iteration+1}: Capture failed: {e}")
                time.sleep(0.5)
                continue

            diff = abs(intensity - target_intensity)
            print(
                f"    Iteration {iteration+1}: IR={ir_power}%, White={test_white_power}% → Intensity {intensity:.1f} (diff: {diff:.1f})"
            )

            # Update best
            if diff < best_diff:
                best_diff = diff
                best_power = test_white_power

            # Check if close enough
            if diff <= tolerance:
                print(
                    f">>> Found optimal white power: {test_white_power}% (intensity: {intensity:.1f})"
                )
                return test_white_power

            # Adjust search
            if intensity < target_intensity:
                low_power = test_white_power + 1
            else:
                high_power = test_white_power - 1

            # Convergence
            if low_power > high_power:
                print(f">>> Search converged: {best_power}% (best diff: {best_diff:.1f})")
                return best_power

            time.sleep(0.3)

        print(f">>> Max iterations: {best_power}% (best diff: {best_diff:.1f})")
        return best_power

    def apply_calibrated_powers(self, calibrated_powers: dict):
        """
        Apply calibrated LED powers and store them.

        Args:
            calibrated_powers: Dict with 'ir', 'white', and optionally 'dual' keys
        """
        if "ir" in calibrated_powers:
            self.ir_led_power = calibrated_powers["ir"]
            logger.info(f"Applied calibrated IR power: {self.ir_led_power}%")
            print(f">>> Applied IR power: {self.ir_led_power}%")

        if "white" in calibrated_powers:
            self.white_led_power = calibrated_powers["white"]
            logger.info(f"Applied calibrated White power: {self.white_led_power}%")
            print(f">>> Applied White power: {self.white_led_power}%")

        if "dual" in calibrated_powers:
            ir_p, white_p = calibrated_powers["dual"]
            self.ir_led_power = ir_p
            self.white_led_power = white_p
            logger.info(f"Applied calibrated DUAL powers: IR={ir_p}%, White={white_p}%")
            print(f">>> Applied DUAL powers: IR={ir_p}%, White={white_p}%")

        # Store for later use
        self.calibrated_powers = calibrated_powers

        print(f">>> Calibrated powers stored: {calibrated_powers}")

    # ======================================================================
    # Utils
    # ======================================================================
    def clear_communication_buffers(self) -> bool:
        if self.serial_connection and self.serial_connection.is_open:
            try:
                if self.serial_connection.in_waiting:
                    self.serial_connection.read(self.serial_connection.in_waiting)
                self.serial_connection.reset_input_buffer()
                self.serial_connection.reset_output_buffer()
                return True
            except Exception as e:
                logger.debug(f"Buffer clear failed: {e}")
        return False
