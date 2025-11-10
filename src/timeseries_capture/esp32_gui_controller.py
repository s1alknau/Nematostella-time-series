"""
ESP32 GUI Controller - Integration Layer

Bridges the GUI (ESP32ConnectionPanel) with the ESP32Controller hardware.

Responsibilities:
- Handle GUI signals (connect/disconnect requests)
- Manage ESP32Controller lifecycle
- Update GUI with hardware status
- Background hardware monitoring
- Thread-safe operation
"""

import logging
import threading
from typing import Optional

from qtpy.QtCore import QObject, QTimer
from qtpy.QtCore import Signal as pyqtSignal

from .ESP32_Controller.esp32_controller import ESP32Controller  # ✅ Correct!

logger = logging.getLogger(__name__)


class ESP32GUIController(QObject):
    """
    Integration layer between ESP32ConnectionPanel and ESP32Controller.

    This controller:
    1. Listens to GUI signals
    2. Manages ESP32Controller
    3. Updates GUI with status
    4. Monitors hardware in background
    """

    # Signals to emit back to GUI
    connection_status_changed = pyqtSignal(bool, str)  # connected, port
    hardware_info_updated = pyqtSignal(dict)
    connection_error = pyqtSignal(str)  # error message
    log_message = pyqtSignal(str, str)  # message, level

    def __init__(self, connection_panel, log_panel=None):
        """
        Args:
            connection_panel: ESP32ConnectionPanel instance
            log_panel: Optional LogPanel instance for logging
        """
        super().__init__()

        # GUI components
        self.connection_panel = connection_panel
        self.log_panel = log_panel

        # ESP32 Controller
        self.esp32: Optional[ESP32Controller] = None

        # State
        self._is_connected = False
        self._connection_in_progress = False

        # Background monitoring
        self._monitor_timer: Optional[QTimer] = None
        self._monitor_interval_ms = 5000  # 5 seconds

        # Connect GUI signals
        self._connect_gui_signals()

        logger.info("ESP32GuiController initialized")

    def _connect_gui_signals(self):
        """Connect to GUI panel signals"""
        self.connection_panel.connect_requested.connect(self._on_connect_requested)
        self.connection_panel.disconnect_requested.connect(self._on_disconnect_requested)
        self.connection_panel.refresh_ports_requested.connect(self._on_refresh_ports)

        # Connect our signals to GUI update methods
        self.connection_status_changed.connect(self.connection_panel.update_connection_status)
        self.hardware_info_updated.connect(self.connection_panel.update_hardware_info)

        # Log messages
        if self.log_panel:
            self.log_message.connect(self.log_panel.add_log)

    # ========================================================================
    # GUI SIGNAL HANDLERS
    # ========================================================================

    def _on_connect_requested(self, port: Optional[str]):
        """
        Handle connect request from GUI.

        Args:
            port: Port to connect to (None = auto-detect)
        """
        if self._connection_in_progress:
            self._log("Connection already in progress", "WARNING")
            return

        if self._is_connected:
            self._log("Already connected", "WARNING")
            return

        # Show connection in progress
        self._connection_in_progress = True
        self.connection_panel.set_connection_in_progress(True)

        # Connect in background thread
        thread = threading.Thread(target=self._connect_background, args=(port,), daemon=True)
        thread.start()

    def _on_disconnect_requested(self):
        """Handle disconnect request from GUI"""
        if not self._is_connected:
            self._log("Not connected", "WARNING")
            return

        self._log("Disconnecting from ESP32...", "INFO")

        try:
            # Stop monitoring
            self._stop_monitoring()

            # Disconnect ESP32
            if self.esp32:
                self.esp32.disconnect()
                self.esp32 = None

            # Update state
            self._is_connected = False

            # Update GUI
            self.connection_status_changed.emit(False, None)

            self._log("✅ Disconnected successfully", "SUCCESS")

        except Exception as e:
            logger.error(f"Error during disconnect: {e}", exc_info=True)
            self._log(f"❌ Disconnect error: {e}", "ERROR")

    def _on_refresh_ports(self):
        """Handle refresh ports request from GUI"""
        self._log("Refreshing port list...", "INFO")
        # GUI panel handles the actual port refresh

    # ========================================================================
    # CONNECTION LOGIC (Background Thread)
    # ========================================================================

    def _connect_background(self, port: Optional[str]):
        """
        Connect to ESP32 in background thread.

        Args:
            port: Port to connect to (None = auto-detect)
        """
        try:
            port_str = port if port else "auto-detect"
            self._log(f"🔌 Connecting to ESP32 (port: {port_str})...", "INFO")

            # Create controller
            self.esp32 = ESP32Controller(port=port, auto_connect=False)

            # Attempt connection
            success = self.esp32.connect(port=port)

            if success:
                # Connection successful
                self._is_connected = True
                connected_port = self.esp32.comm.port

                self._log(f"✅ Connected to ESP32 on {connected_port}", "SUCCESS")

                # Update GUI (must be done in main thread)
                self.connection_status_changed.emit(True, connected_port)

                # Query hardware info
                self._query_hardware_info()

                # Start background monitoring
                self._start_monitoring()

            else:
                # Connection failed
                self._log("❌ Failed to connect to ESP32", "ERROR")
                self.connection_error.emit(
                    "Failed to connect to ESP32. Check connection and try again."
                )
                self.connection_status_changed.emit(False, None)
                self.esp32 = None

        except Exception as e:
            logger.error(f"Connection error: {e}", exc_info=True)
            self._log(f"❌ Connection error: {e}", "ERROR")
            self.connection_error.emit(f"Connection error: {e}")
            self.connection_status_changed.emit(False, None)
            self.esp32 = None

        finally:
            # Clear connection in progress state
            self._connection_in_progress = False
            self.connection_panel.set_connection_in_progress(False)

    # ========================================================================
    # HARDWARE INFO QUERIES
    # ========================================================================

    def _query_hardware_info(self):
        """Query hardware information from ESP32"""
        if not self._is_connected or not self.esp32:
            return

        try:
            # Get sensor data (temperature and humidity)
            sensor_data = self.esp32.get_sensor_data()

            # Get connection stats
            stats = self.esp32.get_connection_stats()

            # Build hardware info dict
            hw_info = {
                "firmware": "ESP32 v2.2",  # Updated version
                "temperature": sensor_data["temperature"] if sensor_data else None,
                "humidity": sensor_data["humidity"] if sensor_data else None,
                "uptime": stats.get("uptime_seconds", 0),  # Fixed: use actual uptime
            }

            # Emit to GUI
            self.hardware_info_updated.emit(hw_info)

        except Exception as e:
            logger.warning(f"Error querying hardware info: {e}")

    # ========================================================================
    # BACKGROUND MONITORING
    # ========================================================================

    def _start_monitoring(self):
        """Start background hardware monitoring"""
        if self._monitor_timer is not None:
            return

        self._monitor_timer = QTimer()
        self._monitor_timer.timeout.connect(self._monitor_tick)
        self._monitor_timer.start(self._monitor_interval_ms)

        logger.debug("Background monitoring started")

    def _stop_monitoring(self):
        """Stop background monitoring"""
        if self._monitor_timer:
            self._monitor_timer.stop()
            self._monitor_timer = None
            logger.debug("Background monitoring stopped")

    def _monitor_tick(self):
        """Periodic monitoring tick"""
        if not self._is_connected or not self.esp32:
            return

        try:
            # Check if still connected
            if not self.esp32.is_connected(force_check=True):
                logger.warning("ESP32 connection lost")
                self._handle_connection_lost()
                return

            # Update hardware info
            self._query_hardware_info()

        except Exception as e:
            logger.warning(f"Monitor tick error: {e}")

    def _handle_connection_lost(self):
        """Handle lost connection"""
        self._is_connected = False
        self._stop_monitoring()

        self._log("⚠️ Connection to ESP32 lost", "WARNING")
        self.connection_status_changed.emit(False, None)

        # Optionally: Attempt auto-reconnect
        # self._on_connect_requested(self.esp32.comm.port)

    # ========================================================================
    # PUBLIC API - For other GUI components
    # ========================================================================

    def is_connected(self) -> bool:
        """Check if ESP32 is connected"""
        return self._is_connected and self.esp32 is not None

    def get_esp32_controller(self) -> Optional[ESP32Controller]:
        """
        Get ESP32Controller instance.

        Returns:
            ESP32Controller or None if not connected
        """
        return self.esp32 if self._is_connected else None

    def select_led_type(self, led_type: str) -> bool:
        """
        Select LED type.

        Args:
            led_type: 'ir' or 'white'

        Returns:
            True if successful
        """
        if not self.is_connected():
            self._log("Cannot select LED: Not connected", "ERROR")
            return False

        try:
            success = self.esp32.select_led_type(led_type)
            if success:
                self._log(f"LED type selected: {led_type.upper()}", "INFO")
            else:
                self._log(f"Failed to select LED type: {led_type}", "ERROR")
            return success
        except Exception as e:
            logger.error(f"Error selecting LED type: {e}")
            self._log(f"LED selection error: {e}", "ERROR")
            return False

    def set_led_power(self, power: int, led_type: str) -> bool:
        """
        Set LED power.

        Args:
            power: Power 0-100
            led_type: 'ir' or 'white'

        Returns:
            True if successful
        """
        if not self.is_connected():
            return False

        try:
            success = self.esp32.set_led_power(power, led_type)
            if success:
                self._log(f"{led_type.upper()} LED power set to {power}%", "INFO")
            return success
        except Exception as e:
            logger.error(f"Error setting LED power: {e}")
            return False

    def led_on(self, led_type: str) -> bool:
        """
        Turn on LED.

        Args:
            led_type: 'ir', 'white', or 'dual'

        Returns:
            True if successful
        """
        if not self.is_connected():
            self._log("Cannot turn on LED: Not connected", "ERROR")
            return False

        try:
            if led_type == "dual":
                # For dual mode, use sync pulse with dual flag
                self._log("Dual LED mode not yet implemented for manual control", "WARNING")
                return False
            else:
                # Select LED type first
                if not self.esp32.select_led_type(led_type):
                    return False

                # Turn on LED
                success = self.esp32.led_on()
                if success:
                    self._log(f"{led_type.upper()} LED turned ON", "SUCCESS")
                else:
                    self._log(f"Failed to turn on {led_type.upper()} LED", "ERROR")
                return success

        except Exception as e:
            logger.error(f"Error turning on LED: {e}")
            self._log(f"LED ON error: {e}", "ERROR")
            return False

    def led_off(self, led_type: Optional[str] = None) -> bool:
        """
        Turn off LED.

        Args:
            led_type: Optional - 'ir' or 'white'. If specified, selects that LED before turning off.
                     If None, turns off currently selected LED.

        Returns:
            True if successful
        """
        if not self.is_connected():
            return False

        try:
            success = self.esp32.led_off(led_type)
            if success:
                led_desc = f"{led_type.upper()} LED" if led_type else "LED"
                self._log(f"{led_desc} turned OFF", "INFO")
            return success
        except Exception as e:
            logger.error(f"Error turning off LED: {e}")
            return False

    def begin_sync_pulse(self, dual: bool = False) -> float:
        """
        Begin synchronized LED pulse.

        Args:
            dual: Use both LEDs (dual mode)

        Returns:
            Pulse start timestamp
        """
        if not self.is_connected():
            return 0.0

        try:
            return self.esp32.begin_sync_pulse(dual=dual)
        except Exception as e:
            logger.error(f"Error starting sync pulse: {e}")
            return 0.0

    def wait_sync_complete(self, timeout: float = 5.0) -> dict:
        """
        Wait for sync pulse to complete.

        Args:
            timeout: Timeout in seconds

        Returns:
            Dict with sync results
        """
        if not self.is_connected():
            return {"success": False, "error": "Not connected"}

        try:
            return self.esp32.wait_sync_complete(timeout=timeout)
        except Exception as e:
            logger.error(f"Error waiting for sync: {e}")
            return {"success": False, "error": str(e)}

    def set_timing(self, stabilization_ms: int, exposure_ms: int) -> bool:
        """
        Set LED timing.

        Args:
            stabilization_ms: LED stabilization time
            exposure_ms: Exposure time

        Returns:
            True if successful
        """
        if not self.is_connected():
            return False

        try:
            success = self.esp32.set_timing(stabilization_ms, exposure_ms)
            if success:
                self._log(f"Timing set: {stabilization_ms}ms + {exposure_ms}ms", "INFO")
            return success
        except Exception as e:
            logger.error(f"Error setting timing: {e}")
            return False

    # ========================================================================
    # AUTO-CONNECT SUPPORT
    # ========================================================================

    def auto_connect_if_enabled(self):
        """
        Automatically connect if auto-connect is enabled in GUI.
        Should be called on startup.
        """
        if self.connection_panel.get_auto_connect_enabled():
            self._log("Auto-connect enabled, connecting...", "INFO")
            self._on_connect_requested(None)  # Auto-detect port

    # ========================================================================
    # CLEANUP
    # ========================================================================

    def cleanup(self):
        """Cleanup and disconnect"""
        logger.info("ESP32GuiController cleanup...")

        self._stop_monitoring()

        if self.esp32:
            try:
                self.esp32.cleanup()
            except:
                pass
            self.esp32 = None

        self._is_connected = False

        logger.info("ESP32GuiController cleanup complete")

    # ========================================================================
    # HELPERS
    # ========================================================================

    def _log(self, message: str, level: str = "INFO"):
        """
        Log message to both logger and GUI log panel.

        Args:
            message: Log message
            level: Log level (INFO, SUCCESS, WARNING, ERROR)
        """
        # Python logger
        if level == "ERROR":
            logger.error(message)
        elif level == "WARNING":
            logger.warning(message)
        elif level == "SUCCESS":
            logger.info(message)
        else:
            logger.info(message)

        # GUI log panel
        self.log_message.emit(message, level)
