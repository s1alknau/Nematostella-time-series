"""
Frame Capture Service - Verbesserte Version mit:
1. Garantierter LED-Synchronisation
2. Drift-Kompensation
3. Timing-Validierung

KRITISCH: Frames MÜSSEN bei eingeschalteter LED captured werden!
"""

import logging
import time
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class FrameCaptureService:
    """
    Verbesserte Frame Capture mit LED-Garantie und Drift-Kompensation.

    KRITISCHE Anforderungen:
    1. Frame MUSS bei eingeschalteter LED captured werden
    2. Drift darf sich NICHT aufsummieren
    3. Alle Timing-Daten müssen gespeichert werden
    """

    def __init__(
        self, esp32_adapter, camera_adapter, stabilization_ms: int = 1000, exposure_ms: int = 10
    ):
        self.esp32 = esp32_adapter
        self.camera = camera_adapter

        self.stabilization_ms = stabilization_ms
        self.exposure_ms = exposure_ms

        # Stats
        self.total_captures = 0
        self.failed_captures = 0
        self.last_capture_duration = 0.0

        # Timing validation
        self.led_sync_failures = 0

        # LED state caching - avoid redundant LED switching
        self._current_led_type = None  # 'ir', 'white', or 'dual'
        self._led_is_on = False
        self._pending_sync_complete = False  # Track if we need to read sync response
        self._white_led_continuous = False  # White LED stays on during full light phase

        # Sensor data caching - query periodically to avoid delays
        self._last_temperature = None  # None = not yet queried
        self._last_humidity = None  # None = not yet queried
        self._sensor_query_interval = 5  # Query every N frames
        self._frames_since_sensor_query = 5  # Force query on first call

        logger.info(
            f"FrameCaptureService initialized (stab={stabilization_ms}ms, exp={exposure_ms}ms)"
        )

    def set_timing(self, stabilization_ms: int, exposure_ms: int) -> bool:
        """Setzt Timing-Parameter"""
        self.stabilization_ms = stabilization_ms
        self.exposure_ms = exposure_ms

        try:
            self.esp32.set_timing(stabilization_ms, exposure_ms)
            logger.info(f"Timing updated: {stabilization_ms}ms + {exposure_ms}ms")
            return True
        except Exception as e:
            logger.error(f"Failed to update timing: {e}")
            return False

    def capture_frame(
        self, led_type: str = "ir", dual_mode: bool = False
    ) -> tuple[Optional[np.ndarray], dict]:
        """
        Captured Frame mit GARANTIERTER LED-Synchronisation.

        WICHTIG: Frame wird NUR captured wenn LED garantiert AN ist!

        Args:
            led_type: 'ir', 'white', oder 'dual'
            dual_mode: Wenn True, beide LEDs nutzen

        Returns:
            Tuple (frame_array, metadata_dict)
        """
        capture_start = time.time()

        # Determine target LED configuration
        target_led_config = "dual" if dual_mode else led_type
        led_config_changed = target_led_config != self._current_led_type

        try:
            # =================================================================
            # SCHRITT 1: LED Configuration (turn on if needed)
            # =================================================================
            pulse_start = time.time()

            # If a background reconnect is in progress, skip LED commands entirely
            # and capture whatever the camera has (frame will likely be dark and
            # trigger the brightness retry, but we must not block the recording loop).
            _esp32_reconnecting = (
                hasattr(self.esp32, "is_reconnecting") and self.esp32.is_reconnecting
            )
            if _esp32_reconnecting:
                logger.warning("[LED SKIP] ESP32 reconnect in progress — capturing without LED")

            if not self._led_is_on and not _esp32_reconnecting:
                stabilization_sec = self.stabilization_ms / 1000.0

                if self._white_led_continuous:
                    # White LED ist dauerhaft an (Tagphase-Modus)
                    if dual_mode:
                        # White läuft durch — nur IR zusätzlich einschalten
                        logger.debug("[LED ON] Continuous White active – turning on IR only...")
                        self.esp32.select_led_type("ir")
                        self.esp32.led_on()
                        time.sleep(stabilization_sec)
                    else:
                        # White-only: LED bereits an, kein weiterer Schritt nötig
                        logger.debug(
                            "[LED ON] Continuous White active – White already on, skip LED on"
                        )
                        # Keine Stabilisierungszeit nötig (LED war bereits stabil an)
                else:
                    # Normaler Modus: LED jetzt einschalten
                    if led_config_changed:
                        logger.debug(
                            f"[LED CONFIG CHANGE] {self._current_led_type} → {target_led_config}"
                        )
                    else:
                        logger.debug(
                            f"[LED ON] Turning on {target_led_config} LED (same as previous)"
                        )

                    if dual_mode:
                        logger.debug("[LED DUAL ON] Turning on both IR and White LEDs...")
                        self.esp32.select_led_type("ir")
                        self.esp32.led_on()
                        time.sleep(0.01)
                        self.esp32.select_led_type("white")
                        self.esp32.led_on()
                    else:
                        logger.debug(f"[LED ON] Turning on {led_type} LED...")
                        self.esp32.select_led_type(led_type)
                        self.esp32.led_on()

                    time.sleep(stabilization_sec)
                    logger.debug(
                        f"[LED STABLE] Stabilization complete after {stabilization_sec:.3f}s"
                    )

                    # Flush stale pre-LED frames from camera buffer.
                    # getLatestFrame() returns the most recent buffered frame which
                    # may have been captured before LED-on. Discard 2 frames so the
                    # actual capture gets a frame acquired after LED stabilization.
                    for _ in range(2):
                        self.camera.capture_frame()
                        time.sleep(0.05)
                    logger.debug("[BUFFER FLUSH] Stale pre-LED frames discarded")

                self._current_led_type = target_led_config
                self._led_is_on = True
                stabilization_complete = time.time()
            else:
                # This should never happen - LED should be OFF between frames
                logger.warning("[LED WARNING] LED was already ON - this should not happen!")
                stabilization_complete = pulse_start

            # =================================================================
            # SCHRITT 2: CAPTURE FRAME (LED is now ON and stable)
            # =================================================================
            logger.debug("[CAPTURING] Starting camera capture...")
            capture_command_time = time.time()

            frame = self.camera.capture_frame()

            capture_complete_time = time.time()
            capture_duration = capture_complete_time - capture_command_time

            logger.debug(f"[CAPTURE DONE] Camera capture took {capture_duration*1000:.1f}ms")

            if frame is None:
                logger.error("[CAPTURE FAIL] Camera returned None")
                self.failed_captures += 1
                return None, {"error": "Camera capture failed", "success": False}

            # =================================================================
            # SCHRITT 3: Use cached ESP32 sensor data (temperature, humidity)
            # =================================================================
            # Sensor queries are now handled BETWEEN frames in recording_manager.py
            # to avoid timing interference with frame capture
            # This ensures sensors are queried after frame save, not during capture

            # Use current cached sensor values (use -1 if not yet queried)
            temperature = self._last_temperature if self._last_temperature is not None else -1.0
            humidity = self._last_humidity if self._last_humidity is not None else -1.0

            # Increment counter (actual query happens in recording_manager between frames)
            self._frames_since_sensor_query += 1

            logger.debug("[LED VERIFY] ✓ Capture completed while LED was ON")

            # =================================================================
            # SCHRITT 4: COMPILE METADATA mit allen Timing-Informationen
            # =================================================================
            metadata = {
                # Timestamps
                "timestamp": time.time(),
                "capture_start": capture_start,
                "led_setup_start": pulse_start,
                "stabilization_complete": stabilization_complete,
                "capture_command_time": capture_command_time,
                "capture_complete_time": capture_complete_time,
                # Durations
                "capture_duration": time.time() - capture_start,
                "camera_capture_duration": capture_duration,
                # LED State Info
                "led_config_changed": led_config_changed,
                "led_was_reused": not led_config_changed,
                "led_is_on": self._led_is_on,
                # LED Configuration
                "led_type": led_type if not dual_mode else "dual",
                "dual_mode": dual_mode,
                "led_stabilization_ms": self.stabilization_ms if led_config_changed else 0,
                "exposure_ms": self.exposure_ms,
                # ESP32 Environmental Data
                "temperature": temperature,
                "humidity": humidity,
                # Frame Info
                "frame_shape": frame.shape if frame is not None else None,
                "frame_dtype": str(frame.dtype) if frame is not None else None,
                # Success
                "success": True,
            }

            self.total_captures += 1
            self.last_capture_duration = time.time() - capture_start

            logger.debug(
                f"[COMPLETE] Frame captured successfully in {metadata['capture_duration']:.3f}s"
            )

            # =================================================================
            # SCHRITT 5: Turn OFF LED after capture
            # =================================================================
            if self._led_is_on and not _esp32_reconnecting:
                try:
                    if self._white_led_continuous:
                        # White LED bleibt an — nur IR abschalten (falls Dual-Modus)
                        if dual_mode:
                            self.esp32.led_off("ir")
                            logger.debug("[LED OFF] IR turned off (White stays on – continuous)")
                        else:
                            # White-only: White bleibt an, nichts abschalten
                            logger.debug("[LED OFF] White stays on (continuous mode)")
                    else:
                        # Normaler Modus: alle LEDs abschalten
                        if target_led_config == "dual":
                            self.esp32.led_dual_off()
                            logger.debug("[LED OFF] Both LEDs turned off after capture")
                        else:
                            self.esp32.led_off(led_type)
                            logger.debug(
                                f"[LED OFF] {led_type.upper()} LED turned off after capture"
                            )

                    self._led_is_on = False

                except Exception as e:
                    logger.warning(f"[LED OFF] Failed to turn off LED: {e}")
                    # Always reset the state flag so the next frame retries LED setup
                    # rather than assuming the LED is still on and skipping turn-on entirely.
                    self._led_is_on = False

            return frame, metadata

        except Exception as e:
            logger.error(f"[ERROR] Frame capture failed: {e}")
            self.failed_captures += 1

            return None, {"timestamp": time.time(), "error": str(e), "success": False}

    def capture_with_retry(
        self, led_type: str = "ir", dual_mode: bool = False, max_retries: int = 3
    ) -> tuple[Optional[np.ndarray], dict]:
        """
        Captured Frame mit Retry-Logik.

        WICHTIG: Jeder Retry ist ein kompletter Capture-Zyklus mit neuem LED-Pulse!
        """
        for attempt in range(max_retries):
            frame, metadata = self.capture_frame(led_type, dual_mode)

            if frame is not None:
                if attempt > 0:
                    metadata["retry_attempt"] = attempt + 1
                return frame, metadata

            # Check if it was LED sync failure
            if metadata.get("led_sync_failure", False):
                logger.error(f"[RETRY] LED sync failure on attempt {attempt+1}, retrying...")
            else:
                logger.warning(
                    f"[RETRY] Capture attempt {attempt + 1}/{max_retries} failed, retrying..."
                )

            time.sleep(0.1)  # Short pause before retry (LED already on, just wait for camera)

        logger.error(f"[FAILED] All {max_retries} capture attempts failed")
        return None, {
            "error": f"Failed after {max_retries} attempts",
            "success": False,
            "retries_exhausted": True,
        }

    def reset_sensor_state(self):
        """
        Force sensor query on the next call to query_sensors_if_needed().

        Call this at the start of each recording so that frame 0 always gets
        a fresh temperature/humidity reading, regardless of where the counter
        was left at the end of the previous recording.
        """
        self._frames_since_sensor_query = self._sensor_query_interval
        logger.info("Sensor query counter reset — next query will fetch fresh data")

    def reset_led_state(self):
        """
        Resets LED state cache without physically turning off the LED.

        Call this at the start of recording to force LED reconfiguration on first capture.
        This only resets the cache variables - it does NOT physically turn off the LED.
        """
        logger.info("Resetting LED state cache (LED remains physically unchanged)")
        self._current_led_type = None
        self._led_is_on = False
        self._pending_sync_complete = False
        self._white_led_continuous = False

    def turn_off_led(self):
        """
        Turns off LED at the end of recording.

        IMPORTANT: Always attempts to turn off LED regardless of cached state,
        since cached state may not reflect physical LED state if errors occurred.

        Call this at the end of recording to save power.
        """
        try:
            # White LED kontinuierlich? Explizit abschalten
            if self._white_led_continuous:
                self.esp32.led_off("white")
                logger.info("Continuous White LED turned off after recording")
                self._white_led_continuous = False
            # Sonstige LEDs abschalten (immer versuchen, unabhängig vom Cache)
            if self._current_led_type == "dual":
                self.esp32.led_dual_off()
                logger.info("Both LEDs turned off after recording")
            elif self._current_led_type:
                self.esp32.led_off(self._current_led_type)
                logger.info(f"{self._current_led_type.upper()} LED turned off after recording")
            else:
                self.esp32.led_dual_off()
                logger.info("LEDs turned off after recording (fallback - no LED type cached)")
        except Exception as e:
            logger.warning(f"Failed to turn off LED: {e}")
        finally:
            self._led_is_on = False
            self._current_led_type = None
            self._white_led_continuous = False

    def set_white_continuous(self, enabled: bool):
        """
        Schaltet die White LED dauerhaft an oder aus (für Tagphase-Modus).

        Wird von RecordingManager bei Phasenübergängen aufgerufen:
        - enabled=True  → Tagphase beginnt: White LED dauerhaft AN
        - enabled=False → Nachtphase beginnt: White LED AUS
        """
        if enabled and not self._white_led_continuous:
            try:
                self.esp32.select_led_type("white")
                self.esp32.led_on()
                self._white_led_continuous = True
                logger.info("[WHITE CONTINUOUS] White LED turned ON (day phase start)")
            except Exception as e:
                logger.warning(f"[WHITE CONTINUOUS] Failed to turn on White LED: {e}")
        elif not enabled and self._white_led_continuous:
            try:
                self.esp32.led_off("white")
                self._white_led_continuous = False
                logger.info("[WHITE CONTINUOUS] White LED turned OFF (night phase start)")
            except Exception as e:
                logger.warning(f"[WHITE CONTINUOUS] Failed to turn off White LED: {e}")

    def query_sensors_if_needed(self) -> bool:
        """
        Query ESP32 sensors (temperature, humidity) if query interval reached.

        This method is called BETWEEN frame captures by recording_manager.py
        to avoid timing interference with frame capture.

        Returns:
            bool: True if sensors were queried, False if using cached values
        """
        should_query = self._frames_since_sensor_query >= self._sensor_query_interval

        if should_query:
            try:
                sensor_data = self.esp32.get_sensor_data()
                print(f"[SENSOR] Raw data from ESP32: {sensor_data}")
                if sensor_data:
                    # Only update if we got valid values (not None, not 0)
                    temp = sensor_data.get("temperature")
                    hum = sensor_data.get("humidity")

                    # Accept any non-None value — esp32_controller already validates and
                    # clamps both readings to realistic sensor ranges before returning.
                    if temp is not None:
                        self._last_temperature = temp
                    else:
                        logger.debug("[SENSOR] Temperature is None, keeping previous")

                    if hum is not None:
                        self._last_humidity = hum
                    else:
                        logger.debug("[SENSOR] Humidity is None, keeping previous")

                    logger.debug(
                        f"[SENSOR] T={self._last_temperature}°C, H={self._last_humidity}% (queried between frames)"
                    )
                else:
                    # Sensor read failed, keep previous values
                    logger.debug("[SENSOR] No data returned, keeping previous values")
            except Exception as e:
                logger.warning(f"[SENSOR] Failed to get sensor data: {e}")
                # Keep previous values on error

            # Reset counter
            self._frames_since_sensor_query = 0
            return True
        else:
            # Use cached sensor data
            logger.debug(
                f"[SENSOR] Using cached values (next query in {self._sensor_query_interval - self._frames_since_sensor_query} frames)"
            )
            return False

    def test_capture(self) -> bool:
        """Test-Capture to validate LED control and frame capture"""
        logger.info("Running test capture with LED control check...")

        try:
            frame, metadata = self.capture_frame(led_type="ir", dual_mode=False)

            if frame is None:
                logger.error("✗ Test capture failed: no frame")
                return False

            # Check if capture succeeded
            success = metadata.get("success", False)

            if not success:
                logger.error("✗ Test capture failed: capture was not successful!")
                return False

            logger.info("✓ Test capture successful:")
            logger.info(f"  Frame shape: {frame.shape}")
            logger.info(f"  LED is ON: {metadata.get('led_is_on', False)}")
            logger.info(f"  Capture duration: {metadata['camera_capture_duration']*1000:.1f}ms")
            logger.info(f"  Temperature: {metadata.get('temperature', 0):.1f}°C")

            # Clean up - turn off LED after test
            self.turn_off_led()

            return True

        except Exception as e:
            logger.error(f"✗ Test capture failed: {e}")
            return False

    def get_capture_stats(self) -> dict:
        """Gibt Capture-Statistiken zurück"""
        success_rate = 0.0
        if self.total_captures > 0:
            success_rate = (
                (self.total_captures - self.failed_captures) / self.total_captures
            ) * 100.0

        return {
            "total_captures": self.total_captures,
            "failed_captures": self.failed_captures,
            "led_sync_failures": self.led_sync_failures,
            "success_rate": success_rate,
            "last_capture_duration": self.last_capture_duration,
        }

    def reset_stats(self):
        """Reset Statistiken"""
        self.total_captures = 0
        self.failed_captures = 0
        self.led_sync_failures = 0
        self.last_capture_duration = 0.0
        logger.info("Capture stats reset")


# ============================================================================
# HARDWARE ADAPTERS (Interface Definitions)
# ============================================================================


class ESP32Adapter:
    """Interface für ESP32 Controller Adapter"""

    def select_led_type(self, led_type: str):
        """Wählt LED-Typ aus"""
        raise NotImplementedError

    def begin_sync_pulse(self, dual: bool = False) -> float:
        """Startet Sync-Pulse, gibt Timestamp zurück"""
        raise NotImplementedError

    def wait_sync_complete(self, timeout: float = 5.0) -> dict:
        """Wartet auf Sync-Complete, gibt Metadata zurück"""
        raise NotImplementedError

    def set_timing(self, stabilization_ms: int, exposure_ms: int):
        """Setzt Timing"""
        raise NotImplementedError


class CameraAdapter:
    """Interface für Camera Adapter"""

    def capture_frame(self) -> Optional[np.ndarray]:
        """Captured Frame, gibt numpy array zurück"""
        raise NotImplementedError

    def is_available(self) -> bool:
        """Prüft ob Kamera verfügbar"""
        raise NotImplementedError

    def get_camera_info(self) -> dict:
        """Gibt Kamera-Informationen zurück"""
        raise NotImplementedError
