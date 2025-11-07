import time
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
from qtpy.QtCore import QThread
from qtpy.QtCore import Signal as pyqtSignal

# HIK SDK imports
try:
    from ctypes import *

    import hikrobotcamlib.hiklibs.MvCameraControl_class as mv
    from hikrobotcamlib.hiklibs.MvCameraControl_class import *

    _HAS_HIK_SDK = True

    # HIK SDK Constants
    MV_OK = 0x00000000
    MV_E_NODATA = 0x80000006
    MV_GIGE_DEVICE = 0x00000001
    MV_USB_DEVICE = 0x00000002
    MV_TRIGGER_MODE_OFF = 0
    MV_TRIGGER_MODE_ON = 1
    MV_TRIGGER_SOURCE_SOFTWARE = 7
    MV_ACCESS_Exclusive = 1
    PixelType_Gvsp_Mono8 = 0x01080001
    PixelType_Gvsp_BayerRG8 = 0x01080009

except ImportError:
    _HAS_HIK_SDK = False

    class MvCamera:
        pass

    class MV_CC_DEVICE_INFO_LIST:
        def __init__(self):
            self.nDeviceNum = 0

    class MV_FRAME_OUT_INFO_EX:
        def __init__(self):
            self.nFrameLen = 0
            self.nWidth = 0
            self.nHeight = 0


class HIKCameraThread(QThread):
    """Streamlined HIK camera control thread"""

    frame_ready = pyqtSignal(np.ndarray)
    error_occurred = pyqtSignal(str)
    status_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.camera = None
        self.running = False
        self.device_info = None
        self.payload_size = 0
        self.triggered_mode = False

    def discover_cameras(self) -> List[Dict[str, Any]]:
        """Discover available HIK cameras"""
        if not _HAS_HIK_SDK:
            return []

        try:
            device_list = MV_CC_DEVICE_INFO_LIST()
            ret = MvCamera.MV_CC_EnumDevices(MV_GIGE_DEVICE | MV_USB_DEVICE, device_list)

            if ret != MV_OK:
                return []

            cameras = []
            for i in range(device_list.nDeviceNum):
                device_info = cast(device_list.pDeviceInfo[i], POINTER(MV_CC_DEVICE_INFO)).contents

                if device_info.nTLayerType == MV_GIGE_DEVICE:
                    gige_info = device_info.SpecialInfo.stGigEInfo
                    cameras.append(
                        {
                            "index": i,
                            "model": self._extract_string(gige_info.chModelName, 32),
                            "serial": self._extract_string(gige_info.chSerialNumber, 16),
                            "ip": self._ip_to_string(gige_info.nCurrentIp),
                            "type": "GigE",
                            "device_info": device_info,
                        }
                    )
                elif device_info.nTLayerType == MV_USB_DEVICE:
                    usb_info = device_info.SpecialInfo.stUsb3VInfo
                    cameras.append(
                        {
                            "index": i,
                            "model": self._extract_string(usb_info.chModelName, 32),
                            "serial": self._extract_string(usb_info.chSerialNumber, 16),
                            "ip": "USB",
                            "type": "USB3",
                            "device_info": device_info,
                        }
                    )

            return cameras

        except Exception as e:
            self.error_occurred.emit(f"Discovery error: {e}")
            return []

    def connect_camera(self, camera_index: int) -> bool:
        """Connect to camera with improved error handling"""
        if not _HAS_HIK_SDK:
            return False

        try:
            # Get device info
            device_list = MV_CC_DEVICE_INFO_LIST()
            ret = MvCamera.MV_CC_EnumDevices(MV_GIGE_DEVICE | MV_USB_DEVICE, device_list)

            if ret != MV_OK or camera_index >= device_list.nDeviceNum:
                return False

            self.device_info = cast(
                device_list.pDeviceInfo[camera_index], POINTER(MV_CC_DEVICE_INFO)
            ).contents

            # Create camera handle
            self.camera = MvCamera()
            ret = self.camera.MV_CC_CreateHandle(self.device_info)
            if ret != MV_OK:
                self.error_occurred.emit(f"Create handle failed: {ret}")
                return False

            # Open device
            ret = self.camera.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0)
            if ret != MV_OK:
                self.camera.MV_CC_DestroyHandle()
                self.camera = None
                self.error_occurred.emit(f"Open device failed: {ret}")
                return False

            # Configure camera
            self._configure_camera()

            # Get payload size
            self.payload_size = self._get_payload_size()

            self.status_changed.emit("Connected")
            return True

        except Exception as e:
            self.error_occurred.emit(f"Connection error: {e}")
            return False

    def disconnect_camera(self):
        """Disconnect camera"""
        if self.camera:
            try:
                self.stop_acquisition()
                self.camera.MV_CC_CloseDevice()
                self.camera.MV_CC_DestroyHandle()
            except:
                pass
            finally:
                self.camera = None
                self.status_changed.emit("Disconnected")

    def start_acquisition(self) -> bool:
        """Start image acquisition"""
        if not self.camera:
            return False

        try:
            ret = self.camera.MV_CC_StartGrabbing()
            if ret == MV_OK:
                self.running = True
                return True
            else:
                self.error_occurred.emit(f"Start acquisition failed: {ret}")
                return False
        except Exception as e:
            self.error_occurred.emit(f"Start acquisition error: {e}")
            return False

    def stop_acquisition(self):
        """Stop image acquisition"""
        self.running = False
        if self.camera:
            try:
                self.camera.MV_CC_StopGrabbing()
            except:
                pass

    def capture_frame(self, timeout_ms: int = 1000) -> Optional[np.ndarray]:
        """Capture single frame"""
        if not self.camera or self.payload_size == 0:
            return None

        try:
            # Trigger if in triggered mode
            if self.triggered_mode:
                ret = self.camera.MV_CC_SetCommandValue("TriggerSoftware")
                if ret != MV_OK:
                    return None
                time.sleep(0.05)  # Allow trigger to process

            # Prepare buffer
            frame_info = MV_FRAME_OUT_INFO_EX()
            data_buf = (c_ubyte * self.payload_size)()

            # Get frame
            ret = self.camera.MV_CC_GetOneFrameTimeout(
                data_buf, self.payload_size, frame_info, timeout_ms
            )

            if ret != MV_OK:
                return None

            # Convert to numpy array
            image = np.frombuffer(data_buf, count=int(frame_info.nFrameLen), dtype=np.uint8)

            # Reshape based on pixel format
            if frame_info.enPixelType == PixelType_Gvsp_Mono8:
                return image.reshape((frame_info.nHeight, frame_info.nWidth))
            elif frame_info.enPixelType == PixelType_Gvsp_BayerRG8:
                bayer = image.reshape((frame_info.nHeight, frame_info.nWidth))
                return cv2.cvtColor(bayer, cv2.COLOR_BayerRG2RGB)
            else:
                return image.reshape((frame_info.nHeight, frame_info.nWidth))

        except Exception as e:
            self.error_occurred.emit(f"Capture error: {e}")
            return None

    def set_trigger_mode(self, enabled: bool) -> bool:
        """Set trigger mode"""
        if not self.camera:
            return False

        try:
            if enabled:
                ret = self.camera.MV_CC_SetEnumValue("TriggerMode", MV_TRIGGER_MODE_ON)
                if ret == MV_OK:
                    ret = self.camera.MV_CC_SetEnumValue(
                        "TriggerSource", MV_TRIGGER_SOURCE_SOFTWARE
                    )
                    self.triggered_mode = True
            else:
                ret = self.camera.MV_CC_SetEnumValue("TriggerMode", MV_TRIGGER_MODE_OFF)
                self.triggered_mode = False

            return ret == MV_OK
        except:
            return False

    def set_exposure_time(self, exposure_us: int) -> bool:
        """Set exposure time in microseconds"""
        if not self.camera:
            return False

        try:
            # Disable auto exposure
            self.camera.MV_CC_SetEnumValue("ExposureAuto", 0)
            # Set exposure time
            ret = self.camera.MV_CC_SetFloatValue("ExposureTime", float(exposure_us))
            return ret == MV_OK
        except:
            return False

    def optimize_for_timelapse(self) -> bool:
        """Optimize camera settings for time-lapse capture"""
        if not self.camera:
            return False

        try:
            # Set packet size for GigE
            ret, packet_size = self.camera.MV_CC_GetOptimalPacketSize()
            if ret == MV_OK:
                self.camera.MV_CC_SetIntValue("GevSCPSPacketSize", packet_size)

            # Set inter-packet delay
            self.camera.MV_CC_SetIntValue("GevSCPD", 1000)

            # Limit frame rate
            self.camera.MV_CC_SetFloatValue("AcquisitionFrameRate", 10.0)
            self.camera.MV_CC_SetBoolValue("AcquisitionFrameRateEnable", True)

            # Disable auto functions
            self.camera.MV_CC_SetEnumValue("ExposureAuto", 0)
            self.camera.MV_CC_SetEnumValue("GainAuto", 0)

            return True
        except:
            return False

    def run(self):
        """Main thread loop for continuous acquisition"""
        while self.running:
            if not self.triggered_mode:
                frame = self.capture_frame(100)
                if frame is not None:
                    self.frame_ready.emit(frame)
            else:
                time.sleep(0.01)

    def _configure_camera(self):
        """Basic camera configuration"""
        if not self.camera:
            return

        try:
            # Set continuous acquisition mode
            self.camera.MV_CC_SetEnumValue("AcquisitionMode", 2)
            # Set pixel format to Mono8
            self.camera.MV_CC_SetEnumValue("PixelFormat", PixelType_Gvsp_Mono8)
            # Disable trigger initially
            self.camera.MV_CC_SetEnumValue("TriggerMode", MV_TRIGGER_MODE_OFF)
        except:
            pass

    def _get_payload_size(self) -> int:
        """Get payload size for frame buffer"""
        if not self.camera:
            return 0

        try:
            # Try method 1
            payload_size = self.camera.MV_CC_GetPayloadSize()
            if payload_size > 0:
                return payload_size
        except:
            pass

        try:
            # Try method 2
            ret, payload_size = self.camera.MV_CC_GetIntValue("PayloadSize")
            if ret == MV_OK and payload_size > 0:
                return payload_size
        except:
            pass

        # Default fallback
        return 2048000

    def _extract_string(self, char_array, max_length: int) -> str:
        """Extract string from ctypes char array"""
        try:
            result = ""
            for i in range(min(max_length, len(char_array))):
                if char_array[i] == 0:
                    break
                result += chr(char_array[i])
            return result.strip()
        except:
            return "Unknown"

    def _ip_to_string(self, ip_int: int) -> str:
        """Convert integer IP to string"""
        return f"{ip_int & 0xFF}.{(ip_int >> 8) & 0xFF}.{(ip_int >> 16) & 0xFF}.{(ip_int >> 24) & 0xFF}"
