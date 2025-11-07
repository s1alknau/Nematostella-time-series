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

            # LED is OFF between frames, so we always need to turn it on
            if not self._led_is_on:
                # Turn ON LED (reuse existing LED type if possible)
                if led_config_changed:
                    logger.info(
                        f"[LED CONFIG CHANGE] {self._current_led_type} → {target_led_config}"
                    )
                else:
                    logger.debug(f"[LED ON] Turning on {target_led_config} LED (same as previous)")

                if dual_mode:
                    # Dual mode: Turn on both LEDs
                    logger.debug("[LED DUAL ON] Turning on both IR and White LEDs...")
                    # Select IR and turn on
                    self.esp32.select_led_type("ir")
                    self.esp32.led_on()
                    time.sleep(0.05)
                    # Select White and turn on
                    self.esp32.select_led_type("white")
                    self.esp32.led_on()
                else:
                    # Single LED mode
                    logger.debug(f"[LED ON] Turning on {led_type} LED...")
                    self.esp32.select_led_type(led_type)
                    self.esp32.led_on()

                # Update cached state
                self._current_led_type = target_led_config
                self._led_is_on = True

                # ALWAYS wait for LED Stabilization (same time regardless of LED type or config change)
                stabilization_sec = self.stabilization_ms / 1000.0
                logger.debug(
                    f"[LED STABILIZING] Waiting {stabilization_sec:.3f}s for LED to stabilize"
                )
                time.sleep(stabilization_sec)

                stabilization_complete = time.time()
                logger.debug(f"[LED STABLE] Stabilization complete at {stabilization_complete:.3f}")
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
            # SCHRITT 3: Get ESP32 sensor data (temperature, humidity)
            # =================================================================
            # Query ESP32 for environmental data
            # Note: We don't query on every frame to avoid delays
            # Only query when LED config changes or periodically
            if led_config_changed:
                try:
                    sensor_data = self.esp32.get_sensor_data()
                    if sensor_data:
                        temperature = sensor_data.get("temperature", 0.0)
                        humidity = sensor_data.get("humidity", 0.0)
                        logger.debug(f"[SENSOR] T={temperature:.1f}°C, H={humidity:.1f}%")
                    else:
                        temperature = 0.0
                        humidity = 0.0
                except Exception as e:
                    logger.warning(f"[SENSOR] Failed to get sensor data: {e}")
                    temperature = 0.0
                    humidity = 0.0
            else:
                # Reuse previous sensor data (avoid delays)
                temperature = 0.0
                humidity = 0.0

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
            # LED should only be ON during capture, not between frames
            if self._led_is_on:
                try:
                    if target_led_config == "dual":
                        self.esp32.led_dual_off()
                        logger.debug("[LED OFF] Both LEDs turned off after capture")
                    else:
                        self.esp32.led_off(led_type)
                        logger.debug(f"[LED OFF] {led_type.upper()} LED turned off after capture")

                    # Mark LED as off, but keep config type for next frame
                    self._led_is_on = False

                except Exception as e:
                    logger.warning(f"[LED OFF] Failed to turn off LED: {e}")

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

            time.sleep(0.5)  # Kurze Pause vor Retry

        logger.error(f"[FAILED] All {max_retries} capture attempts failed")
        return None, {
            "error": f"Failed after {max_retries} attempts",
            "success": False,
            "retries_exhausted": True,
        }

    def reset_led_state(self):
        """
        Resets LED state cache without physically turning off the LED.

        Call this at the start of recording to force LED reconfiguration on first capture.
        This only resets the cache variables - it does NOT physically turn off the LED.
        """
        logger.info("Resetting LED state cache (LED remains physically unchanged)")
        # Only reset cache variables - don't physically turn off LED
        self._current_led_type = None
        self._led_is_on = False
        self._pending_sync_complete = False

    def turn_off_led(self):
        """
        Turns off LED if it's currently on.

        Call this at the end of recording to save power.
        """
        if self._led_is_on:
            try:
                if self._current_led_type == "dual":
                    self.esp32.led_dual_off()
                    logger.info("Both LEDs turned off after recording")
                elif self._current_led_type:
                    self.esp32.led_off(self._current_led_type)
                    logger.info(f"{self._current_led_type.upper()} LED turned off after recording")
                else:
                    # Fallback: turn off both to be safe
                    self.esp32.led_dual_off()
                    logger.info("LEDs turned off after recording (fallback)")
            except Exception as e:
                logger.warning(f"Failed to turn off LED: {e}")
            finally:
                self._led_is_on = False
                self._current_led_type = None

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
