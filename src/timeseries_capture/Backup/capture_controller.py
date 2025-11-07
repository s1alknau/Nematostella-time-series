import time
from enum import Enum
from typing import Any, Callable, Dict, Optional

import numpy as np


class CaptureMode(Enum):
    """Capture mode enumeration"""

    STANDALONE = "standalone"
    IMSWITCH = "imswitch"


class CaptureController:
    """Unified capture controller for minimal drift and consistent timing"""

    def __init__(self, mode: CaptureMode):
        self.mode = mode
        self.camera_source: Optional[Callable] = None
        self.esp32_controller = None
        self.led_enabled = False
        self.led_power = 100
        self.led_stabilization_ms = 50  # Reduced for faster capture
        self.frame_count = 0
        self.timing_stats = []

    def set_camera_source(self, source: Callable):
        """Set the camera frame source (camera thread or ImSwitch layer)"""
        self.camera_source = source

    def set_esp32_controller(self, controller):
        """Set ESP32 controller for LED sync"""
        self.esp32_controller = controller
        self.led_enabled = controller is not None and controller.connected

    def set_led_power(self, power: int):
        """Set LED power for captures"""
        self.led_power = max(0, min(100, power))

    def capture_frame_with_sync(self) -> Dict[str, Any]:
        """
        Capture single frame with optional LED synchronization.
        Optimized for minimal timing drift.
        """
        # Record precise timing
        capture_start = time.perf_counter()

        result = {
            "frame": None,
            "capture_timestamp": capture_start,
            "led_used": False,
            "led_power": 0,
            "led_duration_ms": 0,
            "temperature": 0.0,
            "humidity": 0.0,
            "success": False,
            "error": None,
        }

        try:
            if self.led_enabled and self.esp32_controller:
                # LED synchronized capture
                result.update(self._capture_with_led())
            else:
                # Simple capture without LED
                result.update(self._capture_without_led())

            # Calculate capture duration
            capture_end = time.perf_counter()
            result["capture_duration_ms"] = (capture_end - capture_start) * 1000

            # Update statistics
            self.frame_count += 1
            self.timing_stats.append(result["capture_duration_ms"])

            # Keep only recent timing stats
            if len(self.timing_stats) > 100:
                self.timing_stats.pop(0)

        except Exception as e:
            result["error"] = str(e)
            result["success"] = False

        return result

    def _capture_with_led(self) -> Dict[str, Any]:
        """Capture with LED synchronization - optimized sequence"""
        # Pre-capture: Ensure LED is off
        self.esp32_controller.led_off()
        time.sleep(0.01)  # Minimal delay

        # Set LED power
        self.esp32_controller.set_led_power(self.led_power)

        # LED ON
        led_on_time = time.perf_counter()
        if not self.esp32_controller.led_on():
            return self._capture_without_led()  # Fallback

        # Wait for LED stabilization
        time.sleep(self.led_stabilization_ms / 1000.0)

        # Capture frame while LED is on
        frame = self._get_frame()
        capture_time = time.perf_counter()

        # LED OFF immediately after capture
        self.esp32_controller.led_off()
        led_off_time = time.perf_counter()

        # Get environmental data (after LED off to not delay capture)
        sync_data = self.esp32_controller.sync_capture()

        if frame is None:
            return {"success": False, "error": "Frame capture failed"}

        result = {
            "frame": frame,
            "led_used": True,
            "led_power": self.led_power,
            "led_duration_ms": (led_off_time - led_on_time) * 1000,
            "success": True,
        }

        # Add environmental data if available
        if sync_data:
            result["temperature"] = sync_data.get("temperature", 0.0)
            result["humidity"] = sync_data.get("humidity", 0.0)
            result["esp32_timestamp"] = sync_data.get("esp32_timestamp", capture_time)

        return result

    def _capture_without_led(self) -> Dict[str, Any]:
        """Simple capture without LED"""
        frame = self._get_frame()

        if frame is None:
            return {"success": False, "error": "Frame capture failed"}

        return {
            "frame": frame,
            "led_used": False,
            "led_power": 0,
            "led_duration_ms": 0,
            "success": True,
        }

    def _get_frame(self) -> Optional[np.ndarray]:
        """Get frame from camera source"""
        if not self.camera_source:
            return None

        try:
            if self.mode == CaptureMode.IMSWITCH:
                # For ImSwitch, camera_source is the live layer
                if hasattr(self.camera_source, "data") and self.camera_source.data is not None:
                    return self.camera_source.data.copy()
            else:
                # For standalone, camera_source is a capture function
                if callable(self.camera_source):
                    return self.camera_source()

        except Exception as e:
            print(f"Frame capture error: {e}")

        return None

    def get_timing_statistics(self) -> Dict[str, float]:
        """Get capture timing statistics"""
        if not self.timing_stats:
            return {"mean_ms": 0.0, "std_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0}

        stats_array = np.array(self.timing_stats)
        return {
            "mean_ms": float(np.mean(stats_array)),
            "std_ms": float(np.std(stats_array)),
            "min_ms": float(np.min(stats_array)),
            "max_ms": float(np.max(stats_array)),
        }

    def optimize_led_timing(self, test_frames: int = 10) -> float:
        """
        Optimize LED stabilization timing by testing different delays.
        Returns optimal delay in milliseconds.
        """
        if not self.led_enabled:
            return 50.0  # Default

        test_delays = [10, 20, 30, 40, 50, 75, 100]  # ms
        results = []

        print("Optimizing LED timing...")

        for delay in test_delays:
            self.led_stabilization_ms = delay
            brightness_values = []

            # Test multiple captures
            for _ in range(test_frames):
                # Dark frame
                self.esp32_controller.led_off()
                time.sleep(0.1)
                dark_frame = self._get_frame()

                if dark_frame is not None:
                    dark_mean = np.mean(dark_frame)

                    # Bright frame
                    result = self._capture_with_led()

                    if result["success"] and result["frame"] is not None:
                        bright_mean = np.mean(result["frame"])
                        brightness_ratio = bright_mean / dark_mean if dark_mean > 0 else 0
                        brightness_values.append(brightness_ratio)

                time.sleep(0.1)

            if brightness_values:
                mean_brightness = np.mean(brightness_values)
                std_brightness = np.std(brightness_values)

                results.append(
                    {
                        "delay": delay,
                        "brightness": mean_brightness,
                        "stability": 1.0 / (1.0 + std_brightness),  # Higher is more stable
                    }
                )

                print(
                    f"  {delay}ms: brightness={mean_brightness:.2f}, stability={1.0 / (1.0 + std_brightness):.2f}"
                )

        if results:
            # Find optimal delay (balance brightness and stability)
            scores = [r["brightness"] * r["stability"] for r in results]
            best_idx = np.argmax(scores)
            optimal_delay = results[best_idx]["delay"]

            self.led_stabilization_ms = optimal_delay
            print(f"Optimal LED delay: {optimal_delay}ms")

            return float(optimal_delay)

        return 50.0  # Default fallback
