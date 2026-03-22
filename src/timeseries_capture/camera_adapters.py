"""
HIK GigE Camera Adapter - Wrapper für ImSwitch/Napari Camera

Implementiert das CameraAdapter Interface für:
- HIK GigE Kameras (in ImSwitch)
- Napari Viewer Integration
- Dummy Kamera (für Testing)

Unterstützt:
- Live Frame Capture
- Camera Info Queries
- Availability Checks
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


# ============================================================================
# ABSTRACT CAMERA ADAPTER INTERFACE
# ============================================================================


class CameraAdapter(ABC):
    """
    Abstract Camera Adapter Interface.
    Muss von konkreten Implementierungen erfüllt werden.
    """

    @abstractmethod
    def capture_frame(self) -> Optional[np.ndarray]:
        """
        Capture a frame from camera.

        Returns:
            numpy array (height, width) or None on failure
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if camera is available.

        Returns:
            True if camera is ready
        """
        pass

    @abstractmethod
    def get_camera_info(self) -> dict:
        """
        Get camera information.

        Returns:
            Dictionary with camera info
        """
        pass

    def get_exposure_ms(self) -> float:
        """
        Get current camera exposure time in milliseconds.

        Returns:
            Exposure time in ms, or 10.0 as default if not available
        """
        try:
            info = self.get_camera_info()
            if "parameters" in info and "exposure" in info["parameters"]:
                # Exposure is typically in milliseconds
                return float(info["parameters"]["exposure"])
        except Exception:
            pass
        return 10.0  # Default fallback


# ============================================================================
# HIK GIGE CAMERA ADAPTER (for ImSwitch)
# ============================================================================


class HikGigECameraAdapter(CameraAdapter):
    """
    Adapter für HIK GigE Kamera in ImSwitch.

    Nutzt die ImSwitch Camera Manager API um Frames zu holen.
    """

    def __init__(self, camera_manager=None, detector_name: str = None):
        """
        Args:
            camera_manager: ImSwitch CameraManager instance
            detector_name: Name of the detector/camera in ImSwitch
        """
        self.camera_manager = camera_manager
        self.detector_name = detector_name
        self._last_frame = None

        # Try to find detector automatically if not specified
        if not self.detector_name and self.camera_manager:
            try:
                # Get first available detector
                detectors = list(self.camera_manager._detectorManagers.keys())
                if detectors:
                    self.detector_name = detectors[0]
                    logger.info(f"Auto-selected detector: {self.detector_name}")
            except Exception:
                pass

        logger.info(f"HIK GigE Camera Adapter initialized (detector={self.detector_name})")

    def capture_frame(self) -> Optional[np.ndarray]:
        """
        Capture frame from HIK camera via ImSwitch.

        Returns:
            numpy array or None
        """
        if not self.is_available():
            logger.error("Camera not available")
            return None

        try:
            # Get current frame from camera manager
            # This assumes the camera is already running in live mode
            detector = self.camera_manager._detectorManagers[self.detector_name]

            # Try to get latest frame
            frame = detector.getLatestFrame()

            if frame is None:
                logger.warning("Got None frame from camera")
                return self._last_frame  # Return last known good frame

            # Store as last frame
            self._last_frame = frame

            # Ensure correct format (uint16 for HIK)
            if frame.dtype != np.uint16:
                frame = frame.astype(np.uint16)

            logger.debug(f"Frame captured: {frame.shape}, dtype={frame.dtype}")

            return frame

        except Exception as e:
            logger.error(f"Failed to capture frame: {e}")
            return None

    def is_available(self) -> bool:
        """
        Check if camera is available.

        Returns:
            True if camera manager and detector are ready
        """
        if not self.camera_manager:
            return False

        if not self.detector_name:
            return False

        try:
            # Check if detector exists
            if self.detector_name not in self.camera_manager._detectorManagers:
                return False

            # Check if detector is ready
            detector = self.camera_manager._detectorManagers[self.detector_name]

            # Simple check - detector should have getLatestFrame method
            return hasattr(detector, "getLatestFrame")

        except Exception as e:
            logger.debug(f"Camera availability check failed: {e}")
            return False

    def get_camera_info(self) -> dict:
        """
        Get camera information.

        Returns:
            Dictionary with camera info
        """
        info = {
            "name": "HIK GigE Camera",
            "type": "gige",
            "detector_name": self.detector_name,
            "available": self.is_available(),
        }

        if self.is_available():
            try:
                detector = self.camera_manager._detectorManagers[self.detector_name]

                # Try to get shape from last frame
                if self._last_frame is not None:
                    info["width"] = self._last_frame.shape[1]
                    info["height"] = self._last_frame.shape[0]
                    info["dtype"] = str(self._last_frame.dtype)

                # Try to get camera parameters
                if hasattr(detector, "getParameter"):
                    try:
                        info["parameters"] = {
                            "exposure": detector.getParameter("exposure"),
                            "gain": detector.getParameter("gain"),
                        }
                    except Exception:
                        pass

            except Exception as e:
                logger.debug(f"Could not get detailed camera info: {e}")

        return info


# ============================================================================
# NAPARI VIEWER CAMERA ADAPTER
# ============================================================================


class NapariViewerCameraAdapter(CameraAdapter):
    """
    Adapter für Napari Viewer Live Camera Layer.

    Holt Frames direkt aus dem aktuellen Napari Viewer Layer.
    """

    def __init__(self, napari_viewer, layer_name: str = None):
        """
        Args:
            napari_viewer: Napari viewer instance
            layer_name: Name of the camera layer (or None for auto-detect)
        """
        self.viewer = napari_viewer
        self.layer_name = layer_name
        self._last_frame = None
        self._cached_layer = None  # Cache the layer once found
        self._layer_search_count = 0  # Track search attempts

        logger.info(f"Napari Viewer Camera Adapter initialized (layer={layer_name})")

        # Try to find layer immediately, but don't fail if not found
        layer = self._get_camera_layer()
        if layer:
            logger.info(
                f"✅ Camera layer found during init: {layer.name if hasattr(layer, 'name') else 'unnamed'}"
            )
        else:
            logger.warning("⚠️ No camera layer found yet - will retry when capturing")

    def capture_frame(self) -> Optional[np.ndarray]:
        """
        Capture frame from Napari viewer layer.
        Automatically searches for camera layers if not found yet.

        Returns:
            numpy array or None
        """
        if not self.viewer:
            logger.error("Viewer not available")
            return None

        try:
            # Get layer (will search and cache if needed)
            layer = self._get_camera_layer()

            if layer is None:
                # No layer found yet - might be waiting for live view to start
                if self._last_frame is not None:
                    logger.debug("No layer yet, returning last frame")
                    return self._last_frame
                else:
                    # Only log error every 10 frames to avoid spam
                    if self._layer_search_count % 10 == 1:
                        logger.error(
                            "No camera layer found (ensure live view is started in ImSwitch)"
                        )
                    return None

            # Get data from layer
            frame = layer.data

            if frame is None or frame.size == 0:
                logger.warning("Empty frame from layer")
                return self._last_frame

            # Make a copy to avoid issues with live updates
            frame = frame.copy()

            # Store as last frame
            self._last_frame = frame

            # Ensure correct format
            if frame.dtype != np.uint16:
                frame = frame.astype(np.uint16)

            return frame

        except Exception as e:
            logger.error(f"Failed to capture frame from Napari: {e}")
            # Return last frame as fallback
            return self._last_frame

    def is_available(self) -> bool:
        """
        Check if viewer is available.
        Returns True if viewer exists, even if no layer found yet
        (layer might appear when live view starts).
        """
        if not self.viewer:
            return False

        # If we have a viewer, we're "available" even if no layer yet
        # The layer will be searched for during capture_frame()
        return True

    def refresh_camera_layer(self) -> bool:
        """
        Force refresh of camera layer detection.
        Useful when live view is started after plugin initialization.

        Returns:
            True if layer found, False otherwise
        """
        logger.info("Forcing camera layer refresh...")
        self._cached_layer = None
        self._layer_search_count = 0
        layer = self._get_camera_layer()

        if layer:
            logger.info(
                f"✅ Camera layer refreshed: {layer.name if hasattr(layer, 'name') else 'unnamed'}"
            )
            return True
        else:
            logger.warning("❌ No camera layer found after refresh")
            return False

    def get_camera_info(self) -> dict:
        """Get camera information from Napari layer"""
        info = {
            "name": "Napari Viewer Camera",
            "type": "napari",
            "layer_name": self.layer_name,
            "available": self.is_available(),
        }

        if self.is_available():
            layer = self._get_camera_layer()
            if layer and hasattr(layer, "data"):
                try:
                    info["shape"] = layer.data.shape
                    info["dtype"] = str(layer.data.dtype)
                except Exception:
                    pass

        return info

    def _get_camera_layer(self):
        """
        Get camera layer from viewer.
        Uses caching to avoid repeated layer searches.
        """
        # Return cached layer if available and still valid
        if self._cached_layer is not None:
            try:
                # Verify cached layer still exists in viewer
                if self._cached_layer in self.viewer.layers:
                    return self._cached_layer
                else:
                    logger.warning("Cached layer no longer in viewer, searching again...")
                    self._cached_layer = None
            except Exception:
                self._cached_layer = None

        if not self.viewer:
            logger.warning("No viewer available")
            return None

        try:
            self._layer_search_count += 1

            # Debug: Log all available layers (only first few times to avoid spam)
            if self._layer_search_count <= 5 and hasattr(self.viewer, "layers"):
                layer_names = [
                    layer.name if hasattr(layer, "name") else "unnamed"
                    for layer in self.viewer.layers
                ]
                logger.info(
                    f"Available Napari layers (search #{self._layer_search_count}): {layer_names}"
                )

            if self.layer_name:
                # Get specific layer by name
                layer = self.viewer.layers[self.layer_name]
                self._cached_layer = layer
                return layer
            else:
                # Auto-detect ImSwitch live layer
                for layer in self.viewer.layers:
                    # Look for ImSwitch camera layers
                    if hasattr(layer, "name") and any(
                        indicator in layer.name
                        for indicator in ["Live:", "Widefield", "Camera", "Detector"]
                    ):
                        logger.info(f"✅ Auto-detected ImSwitch layer: {layer.name}")
                        # Cache both the layer and its name
                        self._cached_layer = layer
                        if not self.layer_name:
                            self.layer_name = layer.name
                        return layer

                # Fallback: Get first Image layer with data
                for layer in self.viewer.layers:
                    if hasattr(layer, "data") and layer.data is not None:
                        logger.info(
                            f"Using fallback layer: {layer.name if hasattr(layer, 'name') else 'unknown'}"
                        )
                        # Cache both the layer and its name
                        self._cached_layer = layer
                        if not self.layer_name and hasattr(layer, "name"):
                            self.layer_name = layer.name
                        return layer

                # Only log warning every 10 searches to avoid spam
                if self._layer_search_count % 10 == 0:
                    logger.warning(
                        f"No layers with data found (search #{self._layer_search_count})"
                    )

        except Exception as e:
            logger.error(f"Error getting camera layer: {e}")

        return None


# ============================================================================
# DUMMY CAMERA ADAPTER (for Testing)
# ============================================================================


class DummyCameraAdapter(CameraAdapter):
    """
    Dummy camera für Testing ohne echte Hardware.
    Generiert synthetische Test-Bilder.
    """

    def __init__(self, width: int = 2048, height: int = 2048):
        """
        Args:
            width: Image width
            height: Image height
        """
        self.width = width
        self.height = height
        self.frame_count = 0

        logger.info(f"Dummy Camera Adapter initialized ({width}x{height})")

    def capture_frame(self) -> Optional[np.ndarray]:
        """
        Generate test frame.

        Returns:
            numpy array (height, width) uint16
        """
        import time

        # Simulate capture time
        time.sleep(0.05)  # 50ms

        # Generate test pattern
        frame = self._generate_test_pattern()

        self.frame_count += 1

        logger.debug(f"Dummy frame captured: #{self.frame_count}")

        return frame

    def _generate_test_pattern(self) -> np.ndarray:
        """Generate gradient test pattern"""
        # Create gradient
        y = np.linspace(0, 65535, self.height, dtype=np.uint16)
        x = np.linspace(0, 65535, self.width, dtype=np.uint16)

        # 2D gradient
        yy, xx = np.meshgrid(y, x, indexing="ij")

        # Combine X and Y gradients
        frame = ((yy // 2 + xx // 2) % 65536).astype(np.uint16)

        # Add frame number indicator in corner
        if self.frame_count > 0:
            box_size = min(50, self.height // 10, self.width // 10)
            intensity = min(self.frame_count * 1000, 65535)
            frame[:box_size, :box_size] = intensity

        return frame

    def is_available(self) -> bool:
        """Dummy is always available"""
        return True

    def get_camera_info(self) -> dict:
        """Get dummy camera info"""
        return {
            "name": "Dummy Test Camera",
            "type": "synthetic",
            "width": self.width,
            "height": self.height,
            "frames_generated": self.frame_count,
            "dtype": "uint16",
        }

    def reset_counter(self):
        """Reset frame counter"""
        self.frame_count = 0
        logger.info("Frame counter reset")


# ============================================================================
# HARVESTERS CAMERA ADAPTER (standalone, no vendor SDK required)
# ============================================================================

try:
    from harvesters.core import Harvester  # type: ignore[import-untyped]

    HARVESTERS_AVAILABLE = True
except ImportError:
    HARVESTERS_AVAILABLE = False
    logger.debug("harvesters not installed. Run: pip install harvesters")

# Known CTI search paths — checked in order during auto-detection
_CTI_SEARCH_PATHS = [
    # Daheng Imaging (free, no registration)
    r"C:\Program Files\Daheng Imaging\GalaxySDK\GenTL\Win64\GxGVTL.cti",
    r"C:\Program Files\Daheng Imaging\GalaxySDK\GenTL\Win64\GxU3VTL.cti",
    # Hikrobotics MVS (if installed)
    r"C:\Program Files (x86)\Common Files\MVS\Runtime\Win64_x64\MvProducerGEV.cti",
    r"C:\Program Files (x86)\Common Files\MVS\Runtime\Win64_x64\MvProducerU3V.cti",
    # Allied Vision Vimba X
    r"C:\Program Files\Allied Vision\Vimba X\cti\VimbaGigETL.cti",
    # Matrix Vision mvIMPACT Acquire (free)
    r"C:\Program Files\MATRIX VISION\mvIMPACT Acquire\bin\x64\mvGenTLProducer.cti",
    # Baumer BGAPI2
    r"C:\Program Files\Baumer\Baumer GAPI SDK\Components\BGAPI2_GENICAM\x64\BaumerGigE.cti",
]


def find_cti_files() -> list[str]:
    """
    Return all CTI files found in known SDK locations and GENICAM_GENTL64_PATH.
    Returns a list of absolute paths that exist on this machine.
    """
    import os

    found = []
    # Standard GenTL env variable (set by most SDKs automatically)
    gentl_path = os.environ.get("GENICAM_GENTL64_PATH", "")
    for directory in gentl_path.split(os.pathsep):
        if directory:
            import glob

            for cti in glob.glob(os.path.join(directory, "*.cti")):
                if cti not in found:
                    found.append(cti)
    # Known fixed paths
    for path in _CTI_SEARCH_PATHS:
        if os.path.exists(path) and path not in found:
            found.append(path)
    return found


class HarvestersCameraAdapter(CameraAdapter):
    """
    GenTL / GenICam camera adapter via the harvesters library.

    Works with any GigE Vision or USB3 Vision camera via a free GenTL
    producer (.cti file) — no vendor SDK installation required.

    Install: pip install harvesters
    CTI:     Daheng GxGVTL.cti, MVS MvProducerGEV.cti, or any GenTL producer

    Usage:
        h = Harvester()
        h.add_file('/path/to/producer.cti')
        h.update()
        adapter = HarvestersCameraAdapter(h, device_index=0)
        adapter.open()
        frame = adapter.capture_frame()
        adapter.close()
    """

    def __init__(self, harvester: "Harvester", device_index: int = 0):
        if not HARVESTERS_AVAILABLE:
            raise RuntimeError("harvesters not installed. Run: pip install harvesters")
        self._harvester = harvester
        self._device_index = device_index
        self._ia = None  # ImageAcquirer
        self._open = False
        self._name = "GenTL Camera"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> bool:
        """Create ImageAcquirer and start grabbing. Returns True on success."""
        if self._open:
            return True
        try:
            self._ia = self._harvester.create(self._device_index)
            # Continuous (free-run) mode
            nm = self._ia.remote_device.node_map
            try:
                nm.TriggerMode.value = "Off"
            except Exception:
                pass
            self._ia.start()
            self._open = True
            try:
                vendor = nm.DeviceVendorName.value
                model = nm.DeviceModelName.value
                self._name = f"{vendor} {model}"
            except Exception:
                pass
            logger.info(f"Camera opened via harvesters: {self._name}")
            return True
        except Exception as exc:
            logger.error(f"Harvesters open error: {exc}")
            if self._ia is not None:
                try:
                    self._ia.destroy()
                except Exception:
                    pass
                self._ia = None
            return False

    def close(self):
        """Stop grabbing and release the ImageAcquirer."""
        if not self._open or self._ia is None:
            return
        try:
            self._ia.stop()
            self._ia.destroy()
        except Exception as exc:
            logger.warning(f"Harvesters close error: {exc}")
        self._ia = None
        self._open = False

    # ------------------------------------------------------------------
    # CameraAdapter interface
    # ------------------------------------------------------------------

    def capture_frame(self) -> Optional[np.ndarray]:
        if not self._open or self._ia is None:
            return None
        try:
            buffer = self._ia.try_fetch(timeout=2.0)
            if buffer is None:
                return None
            try:
                comp = buffer.payload.components[0]
                h, w = comp.height, comp.width
                data = comp.data.copy()
                fmt = getattr(comp, "data_format", "")
                if "Mono8" in fmt:
                    frame = data.reshape(h, w).astype(np.uint16)
                else:
                    # Mono10 / Mono12 / Mono16 — already uint16
                    frame = data.view(np.uint16).reshape(h, w)
                return frame
            finally:
                buffer.queue()
        except Exception as exc:
            logger.error(f"capture_frame error: {exc}")
            return None

    def is_available(self) -> bool:
        return self._open

    def get_camera_info(self) -> dict:
        info: dict = {"name": self._name, "type": "GigE Vision (GenTL)"}
        if self._open and self._ia is not None:
            try:
                info["parameters"] = {"exposure": self.get_exposure_ms()}
            except Exception:
                pass
        return info

    def get_exposure_ms(self) -> float:
        if not self._open or self._ia is None:
            return 10.0
        try:
            return self._ia.remote_device.node_map.ExposureTime.value / 1000.0
        except Exception:
            return 10.0

    def set_exposure_ms(self, exposure_ms: float):
        """Set exposure time in milliseconds."""
        if not self._open or self._ia is None:
            return
        try:
            self._ia.remote_device.node_map.ExposureTime.value = exposure_ms * 1000.0
        except Exception as exc:
            logger.warning(f"set_exposure_ms failed: {exc}")


# ============================================================================
# FACTORY FUNCTION
# ============================================================================


def create_camera_adapter(
    camera_type: str = "hik",
    camera_manager=None,
    napari_viewer=None,
    detector_name: str = None,
    layer_name: str = None,
    **kwargs,
) -> CameraAdapter:
    """
    Factory function to create camera adapter.

    Args:
        camera_type: 'hik', 'napari', 'harvesters', or 'dummy'
        camera_manager: ImSwitch camera manager (for HIK)
        napari_viewer: Napari viewer (for Napari adapter)
        detector_name: Detector name (for HIK)
        layer_name: Layer name (for Napari)
        **kwargs: Additional args; for 'harvesters': harvester=<Harvester>, device_index=<int>

    Returns:
        CameraAdapter instance
    """
    if camera_type.lower() == "harvesters":
        harvester = kwargs.get("harvester")
        device_index = int(kwargs.get("device_index", 0))
        if harvester is None:
            logger.warning("No harvester provided for harvesters adapter, falling back to dummy")
            return DummyCameraAdapter()
        adapter = HarvestersCameraAdapter(harvester, device_index)
        adapter.open()
        return adapter

    elif camera_type.lower() == "hik":
        if not camera_manager:
            logger.warning("No camera manager provided, falling back to dummy")
            return DummyCameraAdapter(**kwargs)
        return HikGigECameraAdapter(camera_manager, detector_name)

    elif camera_type.lower() == "napari":
        if not napari_viewer:
            logger.warning("No Napari viewer provided, falling back to dummy")
            return DummyCameraAdapter(**kwargs)
        return NapariViewerCameraAdapter(napari_viewer, layer_name)

    elif camera_type.lower() == "dummy":
        return DummyCameraAdapter(**kwargs)

    else:
        logger.error(f"Unknown camera type: {camera_type}")
        return DummyCameraAdapter(**kwargs)


# ============================================================================
# QUICK TEST
# ============================================================================

if __name__ == "__main__":
    print("Testing Camera Adapters...")

    # Test Dummy Camera
    print("\n1. Testing Dummy Camera...")
    dummy = DummyCameraAdapter(512, 512)

    print(f"Info: {dummy.get_camera_info()}")
    print(f"Available: {dummy.is_available()}")

    frame = dummy.capture_frame()
    print(f"Frame: shape={frame.shape}, dtype={frame.dtype}, mean={frame.mean():.0f}")

    # Test Factory
    print("\n2. Testing Factory...")
    adapter = create_camera_adapter("dummy", width=256, height=256)
    frame = adapter.capture_frame()
    print(f"Factory frame: shape={frame.shape}")

    print("\n✅ All tests passed!")
