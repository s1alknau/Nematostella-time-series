"""
ESP32 State Management - Zustandsverwaltung für ESP32

Verantwortlich für:
- LED States (IR, White, Current)
- Power Settings
- Timing Configuration
- Sync State
"""

import logging
import threading
import time
from typing import Optional

from .esp32_commands import LEDTypes, TimingConfig

logger = logging.getLogger(__name__)


class ESP32State:
    """Zustandsverwaltung für ESP32"""

    def __init__(self):
        # Thread safety
        self._lock = threading.RLock()

        # LED Selection
        self.current_led_type = "ir"  # 'ir' | 'white'

        # LED Power Settings
        self.ir_led_power = 100  # 0-100
        self.white_led_power = 50  # 0-100

        # LED States
        self.led_ir_state = False
        self.led_white_state = False

        # Timing Configuration
        self.led_stabilization_ms = 1000
        self.exposure_ms = 10

        # Sync/Pulse State
        self._awaiting_sync = False
        self._pulse_started_at = 0.0
        self._last_sync_response = None

        # Camera Type
        self.camera_type = 1  # HIK_GIGE

    # ========================================================================
    # LED TYPE SELECTION
    # ========================================================================

    def get_current_led_type(self) -> str:
        """Gibt aktuell gewählten LED-Typ zurück"""
        with self._lock:
            return self.current_led_type

    def set_current_led_type(self, led_type: str):
        """
        Setzt aktuellen LED-Typ.

        Args:
            led_type: 'ir' oder 'white'
        """
        with self._lock:
            if led_type not in ["ir", "white"]:
                raise ValueError(f"Invalid LED type: {led_type}")
            self.current_led_type = led_type
            logger.debug(f"LED type set to: {led_type}")

    def get_led_type_byte(self, led_type: Optional[str] = None) -> int:
        """
        Gibt LED-Type als Byte zurück.

        Args:
            led_type: Optional LED type, sonst current

        Returns:
            0 für IR, 1 für White
        """
        with self._lock:
            type_to_use = led_type or self.current_led_type
            return LEDTypes.IR if type_to_use == "ir" else LEDTypes.WHITE

    # ========================================================================
    # LED POWER
    # ========================================================================

    def get_led_power(self, led_type: Optional[str] = None) -> int:
        """
        Gibt LED Power zurück.

        Args:
            led_type: 'ir', 'white' oder None für current

        Returns:
            Power 0-100
        """
        with self._lock:
            if led_type == "ir":
                return self.ir_led_power
            elif led_type == "white":
                return self.white_led_power
            elif led_type is None:
                # Current LED
                if self.current_led_type == "ir":
                    return self.ir_led_power
                else:
                    return self.white_led_power
            else:
                raise ValueError(f"Invalid LED type: {led_type}")

    def set_led_power(self, power: int, led_type: Optional[str] = None):
        """
        Setzt LED Power.

        Args:
            power: Power 0-100
            led_type: 'ir', 'white' oder None für current
        """
        with self._lock:
            power = max(0, min(100, power))

            if led_type == "ir":
                self.ir_led_power = power
                logger.debug(f"IR LED power set to {power}%")
            elif led_type == "white":
                self.white_led_power = power
                logger.debug(f"White LED power set to {power}%")
            elif led_type is None:
                # Set for current LED
                if self.current_led_type == "ir":
                    self.ir_led_power = power
                else:
                    self.white_led_power = power
                logger.debug(f"{self.current_led_type.upper()} LED power set to {power}%")
            else:
                raise ValueError(f"Invalid LED type: {led_type}")

    def get_both_led_powers(self) -> dict:
        """
        Gibt beide LED Powers zurück.

        Returns:
            Dict mit 'ir' und 'white' keys
        """
        with self._lock:
            return {"ir": self.ir_led_power, "white": self.white_led_power}

    # ========================================================================
    # LED STATES
    # ========================================================================

    def get_led_state(self, led_type: str) -> bool:
        """
        Gibt LED State zurück.

        Args:
            led_type: 'ir' oder 'white'

        Returns:
            True wenn LED an
        """
        with self._lock:
            if led_type == "ir":
                return self.led_ir_state
            elif led_type == "white":
                return self.led_white_state
            else:
                raise ValueError(f"Invalid LED type: {led_type}")

    def set_led_state(self, led_type: str, state: bool):
        """
        Setzt LED State.

        Args:
            led_type: 'ir' oder 'white'
            state: True für an, False für aus
        """
        with self._lock:
            if led_type == "ir":
                self.led_ir_state = state
            elif led_type == "white":
                self.led_white_state = state
            else:
                raise ValueError(f"Invalid LED type: {led_type}")

            logger.debug(f"{led_type.upper()} LED state: {'ON' if state else 'OFF'}")

    def get_current_led_state(self) -> bool:
        """Gibt State der aktuell gewählten LED zurück"""
        with self._lock:
            if self.current_led_type == "ir":
                return self.led_ir_state
            else:
                return self.led_white_state

    def get_all_led_states(self) -> dict:
        """
        Gibt alle LED States zurück.

        Returns:
            Dict mit 'ir', 'white', 'current_type', 'current_state'
        """
        with self._lock:
            return {
                "ir": self.led_ir_state,
                "white": self.led_white_state,
                "current_type": self.current_led_type,
                "current_state": self.get_current_led_state(),
            }

    def turn_off_all_leds(self):
        """Schaltet alle LEDs aus"""
        with self._lock:
            self.led_ir_state = False
            self.led_white_state = False
            logger.debug("All LEDs turned off")

    # ========================================================================
    # TIMING
    # ========================================================================

    def get_timing(self) -> TimingConfig:
        """
        Gibt Timing-Konfiguration zurück.

        Returns:
            TimingConfig mit stabilization_ms und exposure_ms
        """
        with self._lock:
            return TimingConfig(
                stabilization_ms=self.led_stabilization_ms, exposure_ms=self.exposure_ms
            )

    def set_timing(self, stabilization_ms: int, exposure_ms: int):
        """
        Setzt Timing-Konfiguration.

        Args:
            stabilization_ms: LED Stabilization Zeit in ms
            exposure_ms: Exposure Zeit in ms
        """
        with self._lock:
            self.led_stabilization_ms = max(10, min(10000, stabilization_ms))
            self.exposure_ms = max(0, min(30000, exposure_ms))
            logger.debug(f"Timing set: {self.led_stabilization_ms}ms + {self.exposure_ms}ms")

    def get_capture_window_timing(self) -> dict:
        """
        Gibt Capture-Window Timing zurück.
        Berechnet wann der Capture stattfinden sollte.

        Returns:
            Dict mit timing info
        """
        with self._lock:
            # Berechne totale Dauer
            total_duration = self.led_stabilization_ms + self.exposure_ms

            # Capture sollte nach Stabilization + halber Exposure stattfinden
            capture_delay_sec = (self.led_stabilization_ms + self.exposure_ms / 2) / 1000.0

            return {
                "led_stabilization_ms": self.led_stabilization_ms,
                "exposure_ms": self.exposure_ms,
                "total_duration_ms": total_duration,
                "capture_delay_sec": capture_delay_sec,
            }

    # ========================================================================
    # SYNC STATE
    # ========================================================================

    def begin_sync_pulse(self) -> float:
        """
        Markiert Start eines Sync-Pulse.

        Returns:
            Timestamp des Pulse-Starts
        """
        with self._lock:
            self._awaiting_sync = True
            self._pulse_started_at = time.time()
            self._last_sync_response = None
            logger.debug("Sync pulse started")
            return self._pulse_started_at

    def is_awaiting_sync(self) -> bool:
        """Gibt zurück ob auf Sync-Complete gewartet wird"""
        with self._lock:
            return self._awaiting_sync

    def get_pulse_start_time(self) -> float:
        """Gibt Pulse-Start-Zeit zurück"""
        with self._lock:
            return self._pulse_started_at

    def complete_sync(self, response_data: dict):
        """
        Markiert Sync als abgeschlossen.

        Args:
            response_data: Response-Daten vom ESP32
        """
        with self._lock:
            self._awaiting_sync = False
            self._last_sync_response = response_data
            logger.debug("Sync completed")

    def get_last_sync_response(self) -> Optional[dict]:
        """Gibt letzte Sync-Response zurück"""
        with self._lock:
            return self._last_sync_response

    def abort_sync(self):
        """Bricht aktuellen Sync ab"""
        with self._lock:
            self._awaiting_sync = False
            logger.debug("Sync aborted")

    # ========================================================================
    # CAMERA TYPE
    # ========================================================================

    def get_camera_type(self) -> int:
        """Gibt Kamera-Typ zurück"""
        with self._lock:
            return self.camera_type

    def set_camera_type(self, camera_type: int):
        """
        Setzt Kamera-Typ.

        Args:
            camera_type: 1=HIK_GIGE, 2=USB_GENERIC
        """
        with self._lock:
            if camera_type not in [1, 2]:
                raise ValueError(f"Invalid camera type: {camera_type}")
            self.camera_type = camera_type
            logger.debug(f"Camera type set to {camera_type}")

    # ========================================================================
    # SNAPSHOT
    # ========================================================================

    def get_snapshot(self) -> dict:
        """
        Gibt kompletten State-Snapshot zurück.

        Returns:
            Dict mit allen State-Informationen
        """
        with self._lock:
            return {
                "current_led_type": self.current_led_type,
                "ir_led_power": self.ir_led_power,
                "white_led_power": self.white_led_power,
                "led_ir_state": self.led_ir_state,
                "led_white_state": self.led_white_state,
                "led_stabilization_ms": self.led_stabilization_ms,
                "exposure_ms": self.exposure_ms,
                "awaiting_sync": self._awaiting_sync,
                "pulse_started_at": self._pulse_started_at,
                "camera_type": self.camera_type,
            }
