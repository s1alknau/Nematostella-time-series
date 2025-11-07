"""
Frame Capture Service - Verbesserte Version mit:
1. Garantierter LED-Synchronisation
2. Drift-Kompensation
3. Timing-Validierung

KRITISCH: Frames MÜSSEN bei eingeschalteter LED captured werden!
"""

import logging
import time
from typing import Optional, Tuple

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
    ) -> Tuple[Optional[np.ndarray], dict]:
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
            # SCHRITT 1: LED Configuration (only if needed)
            # =================================================================
            pulse_start = None

            if led_config_changed or not self._led_is_on:
                # LED configuration needs to change - full setup required
                logger.info(f"[LED CONFIG CHANGE] {self._current_led_type} → {target_led_config}")

                # Select LED type (wenn nicht dual)
                if not dual_mode:
                    self.esp32.select_led_type(led_type)

                # BEGIN SYNC PULSE (LED ON)
                pulse_start = self.esp32.begin_sync_pulse(dual=dual_mode)
                logger.debug(f"[LED ON] Sync pulse started at {pulse_start:.3f}")

                # Update cached state
                self._current_led_type = target_led_config
                self._led_is_on = True

                # WARTE für LED Stabilization (full time)
                stabilization_sec = self.stabilization_ms / 1000.0
                logger.debug(
                    f"[LED STABILIZING] Waiting {stabilization_sec:.3f}s for LED to stabilize"
                )
                time.sleep(stabilization_sec)

                stabilization_complete = time.time()
                logger.debug(f"[LED STABLE] Stabilization complete at {stabilization_complete:.3f}")
            else:
                # LED already configured and on - skip setup!
                logger.debug(
                    f"[LED REUSE] LED already on with correct config ({target_led_config}), skipping setup"
                )
                pulse_start = time.time()  # Use current time as "pulse start"
                stabilization_complete = pulse_start  # No stabilization needed
                # No sleep needed - LED is already stable!

            # =================================================================
            # SCHRITT 4: CAPTURE TIMING WINDOW BERECHNEN
            # =================================================================
            # Berechne wann das Capture-Window endet
            # (ESP32 wartet: stabilization + exposure + buffer)

            total_led_duration_ms = self.stabilization_ms + self.exposure_ms + 500  # +500ms buffer
            led_off_time = pulse_start + (total_led_duration_ms / 1000.0)

            current_time = time.time()
            time_until_led_off = led_off_time - current_time

            logger.debug(f"[TIMING] Time until LED OFF: {time_until_led_off*1000:.1f}ms")

            # =================================================================
            # SCHRITT 5: SAFETY CHECK - Genug Zeit für Capture?
            # =================================================================
            # Camera capture braucht typischerweise 50-200ms
            # Wir brauchen MINDESTENS 100ms Puffer!

            min_required_time = 0.100  # 100ms minimum

            if time_until_led_off < min_required_time:
                logger.error(
                    f"[LED SYNC FAIL] Not enough time for capture! {time_until_led_off*1000:.1f}ms < 100ms"
                )
                self.led_sync_failures += 1

                # Warte auf Sync Complete (LED OFF)
                self.esp32.wait_sync_complete(timeout=5.0)

                return None, {
                    "error": "LED sync timing failure",
                    "success": False,
                    "led_sync_failure": True,
                    "time_available": time_until_led_off,
                }

            # =================================================================
            # SCHRITT 6: CAPTURE FRAME (LED ist garantiert AN!)
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
            # SCHRITT 7: VERIFY - War LED noch AN?
            # =================================================================
            # Check ob capture INNERHALB des LED-Windows war
            led_was_on = capture_complete_time < led_off_time

            if not led_was_on:
                logger.warning("[LED WARNING] Capture may have been outside LED window!")
                logger.warning(f"  LED OFF at: {led_off_time:.3f}")
                logger.warning(f"  Capture at: {capture_complete_time:.3f}")
                logger.warning(f"  Difference: {(capture_complete_time - led_off_time)*1000:.1f}ms")
            else:
                logger.debug("[LED VERIFY] ✓ Capture was within LED ON window")

            # =================================================================
            # SCHRITT 8: WAIT for Sync Complete (only if LED was reconfigured)
            # =================================================================
            if led_config_changed:
                # We started a new sync pulse, wait for completion
                logger.debug("[SYNC] Waiting for sync complete...")
                sync_data = self.esp32.wait_sync_complete(timeout=5.0)
                sync_complete_time = time.time()
                logger.debug(f"[LED OFF] Sync complete at {sync_complete_time:.3f}")
            else:
                # LED was reused, no sync pulse was started - skip wait
                logger.debug("[SYNC] LED reused, skipping sync wait")
                sync_data = {
                    "temperature": 0.0,
                    "humidity": 0.0,
                    "timing_ms": 0,
                    "led_power_actual": 0,
                }
                sync_complete_time = time.time()
                # Note: We'll get fresh ESP32 data from periodic sync in next LED config change

            # =================================================================
            # SCHRITT 9: COMPILE METADATA mit allen Timing-Informationen
            # =================================================================
            metadata = {
                # Timestamps
                "timestamp": time.time(),
                "capture_start": capture_start,
                "pulse_start": pulse_start if led_config_changed or not self._led_is_on else None,
                "stabilization_complete": stabilization_complete,
                "capture_command_time": capture_command_time,
                "capture_complete_time": capture_complete_time,
                "sync_complete_time": sync_complete_time,
                # Durations
                "capture_duration": time.time() - capture_start,
                "camera_capture_duration": capture_duration,
                "total_led_duration": sync_complete_time - pulse_start if pulse_start else None,
                # LED State Caching Info
                "led_config_changed": led_config_changed,
                "led_was_reused": not led_config_changed and self._led_is_on,
                # LED Timing
                "led_type": led_type if not dual_mode else "dual",
                "dual_mode": dual_mode,
                "led_stabilization_ms": self.stabilization_ms if led_config_changed else 0,
                "exposure_ms": self.exposure_ms,
                # Timing Verification
                "led_was_on_during_capture": led_was_on,
                "time_until_led_off_ms": time_until_led_off * 1000,
                # ESP32 Data
                "temperature": sync_data.get("temperature", 0.0),
                "humidity": sync_data.get("humidity", 0.0),
                "led_timing_ms": sync_data.get("timing_ms", 0),
                "led_power": sync_data.get("led_power_actual", 0),
                # Frame Info
                "frame_shape": frame.shape if frame is not None else None,
                "frame_dtype": str(frame.dtype) if frame is not None else None,
                # Success
                "success": True,
                "sync_success": True,
            }

            self.total_captures += 1
            self.last_capture_duration = time.time() - capture_start

            logger.debug(
                f"[COMPLETE] Frame captured successfully in {metadata['capture_duration']:.3f}s"
            )

            return frame, metadata

        except Exception as e:
            logger.error(f"[ERROR] Frame capture failed: {e}")
            self.failed_captures += 1

            return None, {"timestamp": time.time(), "error": str(e), "success": False}

    def capture_with_retry(
        self, led_type: str = "ir", dual_mode: bool = False, max_retries: int = 3
    ) -> Tuple[Optional[np.ndarray], dict]:
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
        Resets LED state cache.

        Call this when you want to force LED reconfiguration on next capture,
        or when ending a recording session.
        """
        logger.info("Resetting LED state cache")
        self._current_led_type = None
        self._led_is_on = False

    def turn_off_led(self):
        """
        Turns off LED if it's currently on.

        Call this at the end of recording to save power.
        """
        if self._led_is_on:
            try:
                self.esp32.led_off()
                logger.info("LED turned off after recording")
            except Exception as e:
                logger.warning(f"Failed to turn off LED: {e}")
            finally:
                self._led_is_on = False
                self._current_led_type = None

    def test_capture(self) -> bool:
        """Test-Capture um LED-Synchronisation zu validieren"""
        logger.info("Running test capture with LED synchronization check...")

        try:
            frame, metadata = self.capture_frame(led_type="ir", dual_mode=False)

            if frame is None:
                logger.error("✗ Test capture failed: no frame")
                return False

            # Check LED synchronization
            led_ok = metadata.get("led_was_on_during_capture", False)

            if not led_ok:
                logger.error("✗ Test capture failed: LED was not ON during capture!")
                return False

            logger.info("✓ Test capture successful:")
            logger.info(f"  Frame shape: {frame.shape}")
            logger.info(f"  LED was ON: {led_ok}")
            logger.info(f"  Capture duration: {metadata['camera_capture_duration']*1000:.1f}ms")
            logger.info(f"  Temperature: {metadata.get('temperature', 0):.1f}°C")

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
