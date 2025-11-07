"""
Dummy Camera Adapter - Für Testing ohne echte Kamera

Generiert Test-Bilder mit verschiedenen Patterns:
- Gradient
- Frame-Nummer
- LED-Type Indikator
"""

import logging
import time

import numpy as np

logger = logging.getLogger(__name__)


class DummyCameraAdapter:
    """
    Dummy Kamera für Testing.
    Generiert synthetische Bilder ohne echte Hardware.
    """

    def __init__(self, width: int = 512, height: int = 512):
        """
        Args:
            width: Bild-Breite
            height: Bild-Höhe
        """
        self.width = width
        self.height = height
        self.frame_count = 0

        logger.info(f"DummyCameraAdapter initialized ({width}x{height})")

    def capture_frame(self) -> np.ndarray:
        """
        Captured einen Test-Frame.

        Returns:
            numpy array (height, width) uint16
        """
        # Simuliere Capture-Zeit
        time.sleep(0.05)  # 50ms

        # Erstelle Gradient-Bild
        frame = self._generate_test_pattern()

        self.frame_count += 1

        logger.debug(f"Dummy frame captured: #{self.frame_count}")

        return frame

    def _generate_test_pattern(self) -> np.ndarray:
        """Generiert Test-Pattern"""
        # Erstelle Gradient
        y = np.linspace(0, 65535, self.height, dtype=np.uint16)
        x = np.linspace(0, 65535, self.width, dtype=np.uint16)

        # 2D Gradient
        yy, xx = np.meshgrid(y, x, indexing="ij")

        # Kombiniere X und Y Gradienten
        frame = ((yy // 2 + xx // 2) % 65536).astype(np.uint16)

        # Füge Frame-Nummer als Pattern hinzu (in Ecke)
        if self.frame_count > 0:
            # Kleine Box in oberer linker Ecke mit Frame-Nummer
            box_size = min(50, self.height // 10, self.width // 10)
            intensity = min(self.frame_count * 1000, 65535)
            frame[:box_size, :box_size] = intensity

        return frame

    def is_available(self) -> bool:
        """
        Prüft ob Kamera verfügbar.

        Returns:
            Immer True für Dummy
        """
        return True

    def get_camera_info(self) -> dict:
        """
        Gibt Kamera-Informationen zurück.

        Returns:
            Dict mit Info
        """
        return {
            "name": "Dummy Camera",
            "type": "synthetic",
            "width": self.width,
            "height": self.height,
            "frames_captured": self.frame_count,
            "pixel_format": "uint16",
        }

    def reset_counter(self):
        """Reset Frame Counter"""
        self.frame_count = 0
        logger.info("Frame counter reset")


class ESP32AdapterWrapper:
    """
    Wrapper um ESP32Controller um das Adapter-Interface zu erfüllen.
    """

    def __init__(self, esp32_controller):
        """
        Args:
            esp32_controller: ESP32Controller instance
        """
        self.esp32 = esp32_controller
        logger.info("ESP32AdapterWrapper initialized")

    def select_led_type(self, led_type: str):
        """Wählt LED-Typ aus"""
        self.esp32.select_led_type(led_type)

    def begin_sync_pulse(self, dual: bool = False) -> float:
        """Startet Sync-Pulse"""
        return self.esp32.begin_sync_pulse(dual=dual)

    def wait_sync_complete(self, timeout: float = 5.0) -> dict:
        """Wartet auf Sync-Complete"""
        return self.esp32.wait_sync_complete(timeout=timeout)

    def set_timing(self, stabilization_ms: int, exposure_ms: int):
        """Setzt Timing"""
        self.esp32.set_timing(stabilization_ms, exposure_ms)

    def set_led_power(self, power: int, led_type: str = None):
        """Setzt LED Power"""
        self.esp32.set_led_power(power, led_type)


# ============================================================================
# QUICK TEST
# ============================================================================

if __name__ == "__main__":
    print("Testing Dummy Camera Adapter...")

    camera = DummyCameraAdapter(512, 512)

    print(f"Info: {camera.get_camera_info()}")
    print(f"Available: {camera.is_available()}")

    print("\nCapturing test frames...")
    for i in range(3):
        frame = camera.capture_frame()
        print(f"Frame {i+1}: shape={frame.shape}, dtype={frame.dtype}, mean={frame.mean():.0f}")

    print("\n✅ Test successful!")
