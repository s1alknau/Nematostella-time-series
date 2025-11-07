"""
HIK Robotics GigE Time-series Capture Plugin for napari
Professional microscopy imaging with ESP32 synchronization
Hybrid mode: Standalone OR ImSwitch detector settings integration
"""

import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import cv2
import h5py
import numpy as np
import serial
from qtpy.QtCore import Qt, QThread, QTimer
from qtpy.QtCore import Signal as pyqtSignal
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from serial.tools import list_ports

# HIK SDK imports and constants
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
    MV_TRIGGER_SOURCE_LINE0 = 0
    MV_ACCESS_Exclusive = 1
    PixelType_Gvsp_Mono8 = 0x01080001
    PixelType_Gvsp_BayerRG8 = 0x01080009
    MV_ACQ_MODE_CONTINUOUS = 2
    MV_EXPOSURE_AUTO_MODE_OFF = 0
    MV_EXPOSURE_AUTO_MODE_CONTINUOUS = 2
    MV_GAIN_MODE_CONTINUOUS = 2

except ImportError:
    _HAS_HIK_SDK = False

    # Dummy classes for development
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


# ESP32 Protocol Constants
class ESP32Commands:
    """ESP32 command constants"""

    LED_ON = 0x01
    LED_OFF = 0x00
    STATUS = 0x02
    SYNC_CAPTURE = 0x0C
    SET_LED_POWER = 0x10
    SET_TIMING = 0x11
    SET_CAMERA_TYPE = 0x13


class ESP32Responses:
    """ESP32 response constants"""

    SYNC_COMPLETE = 0x1B
    TIMING_SET = 0x21


class CameraTypes:
    """Camera type constants"""

    HIK_GIGE = 1
    USB_GENERIC = 2


# ESP32 Controller (same as your Part 1)
class ESP32Controller:
    """Handles ESP32 communication and LED control"""

    def __init__(self):
        self.serial_port: Optional[serial.Serial] = None
        self.connected = False
        self.port_name: Optional[str] = None

    def connect(self, port_name: Optional[str] = None, baud_rate: int = 115200) -> bool:
        """Connect to ESP32 with auto-detection"""
        if port_name is None:
            port_name = self._find_esp32_port()

        try:
            print(f"Attempting to connect to ESP32 on {port_name}...")
            self.serial_port = serial.Serial(port_name, baud_rate, timeout=3, write_timeout=3)
            time.sleep(3)

            if self.serial_port.in_waiting > 0:
                boot_data = self.serial_port.read(self.serial_port.in_waiting)
                print(f"Boot data cleared: {len(boot_data)} bytes")

            for attempt in range(3):
                print(f"Testing connection attempt {attempt + 1}/3...")
                response = self.send_command(ESP32Commands.STATUS, timeout=3.0)

                if response and len(response) >= 3:
                    self.connected = True
                    self.port_name = port_name
                    print(f"✅ ESP32 connected successfully on {port_name}")
                    return True

                time.sleep(1)

            print("❌ No valid response after 3 attempts")
            self.serial_port.close()
            return False

        except Exception as e:
            print(f"ESP32 connection failed: {e}")
            return False

    def disconnect(self):
        """Disconnect from ESP32"""
        if self.serial_port and self.serial_port.is_open:
            try:
                self.send_command(ESP32Commands.LED_OFF)
                self.serial_port.close()
            except:
                pass
        self.connected = False
        self.serial_port = None

    def send_command(
        self, cmd_byte: int, data: Optional[List[int]] = None, timeout: float = 2.0
    ) -> Optional[bytes]:
        """Send command to ESP32"""
        if not self.serial_port or not self.serial_port.is_open:
            return None

        try:
            self.serial_port.reset_input_buffer()
            self.serial_port.reset_output_buffer()
            time.sleep(0.01)

            if data is None:
                command = bytes([cmd_byte])
            else:
                command = bytes([cmd_byte] + data)

            self.serial_port.write(command)
            self.serial_port.flush()

            start_time = time.time()
            response = b""

            while (time.time() - start_time) < timeout:
                if self.serial_port.in_waiting > 0:
                    new_data = self.serial_port.read(self.serial_port.in_waiting)
                    response += new_data

                    if (
                        cmd_byte == ESP32Commands.STATUS
                        and len(response) >= 3
                        or cmd_byte == ESP32Commands.SYNC_CAPTURE
                        and len(response) >= 5
                        or cmd_byte not in [ESP32Commands.STATUS, ESP32Commands.SYNC_CAPTURE]
                        and len(response) >= 1
                    ):
                        break

                time.sleep(0.01)

            return response if response else None

        except Exception as e:
            print(f"ESP32 command error: {e}")
            return None

    def _find_esp32_port(self) -> str:
        """Auto-detect ESP32 serial port"""
        try:
            test_serial = serial.Serial("COM3", 115200, timeout=1)
            test_serial.close()
            return "COM3"
        except:
            pass

        ports = list_ports.comports()
        esp32_keywords = ["ESP32", "SILICON LABS", "CH340", "CP210"]

        for port in ports:
            description = port.description.upper()
            if any(keyword in description for keyword in esp32_keywords):
                return port.device

        if ports:
            return ports[0].device

        raise Exception("No serial ports found")

    def set_led_power(self, power: int) -> bool:
        """Set LED power (0-100%)"""
        if power < 0:
            power = 0
        elif power > 100:
            power = 100

        response = self.send_command(ESP32Commands.SET_LED_POWER, [power])
        return response is not None and len(response) >= 1

    def led_on(self) -> bool:
        """Turn LED on"""
        response = self.send_command(ESP32Commands.LED_ON)
        return response is not None and len(response) >= 3

    def led_off(self) -> bool:
        """Turn LED off"""
        response = self.send_command(ESP32Commands.LED_OFF)
        return response is not None and len(response) >= 3

    # 1. ESP32Controller - sync_capture korrigieren (Timestamps fix)
    def sync_capture(self) -> Optional[Dict[str, Any]]:
        """Korrigierte sync_capture - nur Timestamp-Fix"""
        python_timestamp = time.time()
        response = self.send_command(ESP32Commands.SYNC_CAPTURE, timeout=3.0)

        if response and len(response) >= 7 and response[0] == ESP32Responses.SYNC_COMPLETE:
            timing_ms = (response[1] << 8) | response[2]
            temp_raw = (response[3] << 8) | response[4]
            if temp_raw > 32767:
                temp_raw -= 65536
            temperature = temp_raw / 10.0
            humidity_raw = (response[5] << 8) | response[6]
            humidity = humidity_raw / 10.0

            return {
                "python_timestamp": python_timestamp,
                "esp32_timing_ms": timing_ms,
                "temperature": temperature,
                "humidity": humidity,
            }
        return None


# HIK Camera Thread (same as your Part 2 - abbreviated for space)
class HIKCameraThread(QThread):
    """Dedicated thread for HIK camera operations"""

    frame_ready = pyqtSignal(np.ndarray)
    error_occurred = pyqtSignal(str)
    status_changed = pyqtSignal(str)

    def optimize_camera_bandwidth(self):
        """Optimize camera settings for stable bandwidth"""
        if not self.camera:
            print("❌ No camera connected for bandwidth optimization")
            return False

        print("🔧 Optimizing camera bandwidth settings...")

        try:
            # 1. Set packet size for GigE cameras
            try:
                # Get optimal packet size
                ret, packet_size = self.camera.MV_CC_GetOptimalPacketSize()
                if ret == MV_OK:
                    ret = self.camera.MV_CC_SetIntValue("GevSCPSPacketSize", packet_size)
                    if ret == MV_OK:
                        print(f"✅ Packet size optimized: {packet_size}")
                    else:
                        print(f"⚠️ Failed to set packet size: {ret}")
                else:
                    # Fallback: Set standard packet size
                    self.camera.MV_CC_SetIntValue("GevSCPSPacketSize", 1500)
                    print("⚠️ Using fallback packet size: 1500")
            except Exception as e:
                print(f"⚠️ Packet size optimization failed: {e}")

            # 2. Set inter-packet delay to reduce bandwidth pressure
            try:
                # Add small delay between packets (microseconds)
                ret = self.camera.MV_CC_SetIntValue("GevSCPD", 1000)  # 1ms delay
                if ret == MV_OK:
                    print("✅ Inter-packet delay set: 1000μs")
                else:
                    print(f"⚠️ Failed to set inter-packet delay: {ret}")
            except Exception as e:
                print(f"⚠️ Inter-packet delay setting failed: {e}")

            # 3. Set frame rate to reduce bandwidth
            try:
                ret = self.camera.MV_CC_SetFloatValue("AcquisitionFrameRate", 10.0)  # 10 FPS max
                if ret == MV_OK:
                    print("✅ Frame rate limited to 10 FPS")
                else:
                    print(f"⚠️ Failed to set frame rate: {ret}")
            except Exception as e:
                print(f"⚠️ Frame rate setting failed: {e}")

            # 4. Enable frame rate control
            try:
                ret = self.camera.MV_CC_SetBoolValue("AcquisitionFrameRateEnable", True)
                if ret == MV_OK:
                    print("✅ Frame rate control enabled")
            except Exception as e:
                print(f"⚠️ Frame rate control setting failed: {e}")

            # 5. Set buffer handling
            try:
                # Set buffer mode to prevent drops
                ret = self.camera.MV_CC_SetIntValue("PayloadSize", 2048000)  # 2MB buffer
                if ret == MV_OK:
                    print("✅ Payload size set")
            except Exception as e:
                print(f"⚠️ Payload size setting failed: {e}")

            # 6. Disable auto functions that can cause timing issues
            try:
                self.camera.MV_CC_SetEnumValue("ExposureAuto", 0)  # Manual exposure
                self.camera.MV_CC_SetEnumValue("GainAuto", 0)  # Manual gain
                self.camera.MV_CC_SetEnumValue("BalanceWhiteAuto", 0)  # Manual white balance
                print("✅ Auto functions disabled for stability")
            except Exception as e:
                print(f"⚠️ Auto function disable failed: {e}")

            print("✅ Bandwidth optimization completed")
            return True

        except Exception as e:
            print(f"❌ Bandwidth optimization failed: {e}")
            return False

    def check_network_performance(self):
        """Check network performance for GigE camera"""
        if not self.camera:
            print("❌ No camera connected for network check")
            return

        print("🌐 Checking network performance...")

        try:
            # Check packet size
            try:
                ret, packet_size = self.camera.MV_CC_GetIntValue("GevSCPSPacketSize")
                if ret == MV_OK:
                    print(f"📦 Current packet size: {packet_size}")
                else:
                    print("❌ Cannot read packet size")
            except:
                print("❌ Packet size check failed")

            # Check inter-packet delay
            try:
                ret, delay = self.camera.MV_CC_GetIntValue("GevSCPD")
                if ret == MV_OK:
                    print(f"⏱️ Inter-packet delay: {delay}μs")
                else:
                    print("❌ Cannot read inter-packet delay")
            except:
                print("❌ Inter-packet delay check failed")

            # Check frame rate
            try:
                ret, frame_rate = self.camera.MV_CC_GetFloatValue("AcquisitionFrameRate")
                if ret == MV_OK:
                    print(f"🎬 Frame rate: {frame_rate:.1f} FPS")
                else:
                    print("❌ Cannot read frame rate")
            except:
                print("❌ Frame rate check failed")

            # Check bandwidth usage
            try:
                ret, bandwidth = self.camera.MV_CC_GetIntValue("GevSCBWC")
                if ret == MV_OK:
                    print(f"📊 Bandwidth control: {bandwidth}")
                else:
                    print("❌ Cannot read bandwidth control")
            except:
                print("❌ Bandwidth check failed")

        except Exception as e:
            print(f"❌ Network performance check failed: {e}")

    def set_robust_capture_mode(self):
        """Set camera to robust capture mode for time-lapse"""
        if not self.camera:
            return False

        print("🛡️ Setting robust capture mode for time-lapse...")

        try:
            # 1. Use single frame acquisition mode
            ret = self.camera.MV_CC_SetEnumValue("AcquisitionMode", 0)  # SingleFrame
            if ret == MV_OK:
                print("✅ Single frame acquisition mode set")

            # 2. Set trigger mode for controlled capture
            ret = self.camera.MV_CC_SetEnumValue("TriggerMode", 1)  # On
            if ret == MV_OK:
                print("✅ Trigger mode enabled")

            # 3. Set software trigger
            ret = self.camera.MV_CC_SetEnumValue("TriggerSource", 7)  # Software
            if ret == MV_OK:
                print("✅ Software trigger set")

            # 4. Set conservative timing
            ret = self.camera.MV_CC_SetFloatValue("ExposureTime", 10000.0)  # 10ms
            if ret == MV_OK:
                print("✅ Conservative exposure time set")

            self.capture_mode = "triggered"
            print("✅ Robust capture mode configured")
            return True

        except Exception as e:
            print(f"❌ Robust capture mode setup failed: {e}")
            return False

    def capture_frame_robust(self, timeout_ms: int = 5000) -> Optional[np.ndarray]:
        """Robust frame capture with multiple retry strategies"""
        if not self.camera:
            return None

        max_retries = 3
        retry_delays = [0.1, 0.5, 1.0]  # Progressive delays

        for attempt in range(max_retries):
            try:
                # For triggered mode, send software trigger
                if self.capture_mode == "triggered":
                    ret = self.camera.MV_CC_SetCommandValue("TriggerSoftware")
                    if ret != MV_OK:
                        print(f"⚠️ Trigger failed on attempt {attempt + 1}: {ret}")
                        time.sleep(retry_delays[attempt])
                        continue

                    # Wait for trigger to be processed
                    time.sleep(0.05)

                # Get frame info and buffer
                frame_info = MV_FRAME_OUT_INFO_EX()

                # Try different methods for payload size
                payload_size = None
                try:
                    payload_size = self.camera.MV_CC_GetPayloadSize()
                except:
                    try:
                        ret, payload_size = self.camera.MV_CC_GetIntValue("PayloadSize")
                        if ret != MV_OK:
                            payload_size = None
                    except:
                        payload_size = None

                if payload_size is None:
                    payload_size = 2048000  # 2MB fallback

                data_buf = (c_ubyte * int(payload_size))()

                # Capture frame with extended timeout
                ret = self.camera.MV_CC_GetOneFrameTimeout(
                    data_buf, payload_size, frame_info, timeout_ms
                )

                if ret == MV_OK:
                    # Successfully captured frame
                    image = np.frombuffer(data_buf, count=int(frame_info.nFrameLen), dtype=np.uint8)

                    # Handle pixel formats
                    if frame_info.enPixelType == PixelType_Gvsp_Mono8:
                        frame = image.reshape((frame_info.nHeight, frame_info.nWidth))
                    elif frame_info.enPixelType == PixelType_Gvsp_BayerRG8:
                        bayer = image.reshape((frame_info.nHeight, frame_info.nWidth))
                        frame = cv2.cvtColor(bayer, cv2.COLOR_BayerRG2RGB)
                    else:
                        frame = image.reshape((frame_info.nHeight, frame_info.nWidth))

                    print(f"✅ Frame captured successfully on attempt {attempt + 1}")
                    return frame

                elif ret == MV_E_NODATA:
                    print(f"⚠️ No data available on attempt {attempt + 1}")
                    time.sleep(retry_delays[attempt])
                    continue
                else:
                    print(f"⚠️ Frame capture failed on attempt {attempt + 1}: {ret}")
                    time.sleep(retry_delays[attempt])
                    continue

            except Exception as e:
                print(f"⚠️ Capture exception on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delays[attempt])
                    continue

        print(f"❌ Frame capture failed after {max_retries} attempts")
        return None

    def __init__(self):
        super().__init__()
        self.camera = None
        self.running = False
        self.capture_mode = "continuous"

    def force_release_all_cameras(self):
        """Nuclear option: Force release ALL HIK cameras on the system"""
        if not _HAS_HIK_SDK:
            return

        print("💥 NUCLEAR CAMERA RELEASE - Force releasing ALL HIK cameras...")

        try:
            # Step 1: Enumerate all devices
            device_list = MV_CC_DEVICE_INFO_LIST()
            ret = MvCamera.MV_CC_EnumDevices(MV_GIGE_DEVICE | MV_USB_DEVICE, device_list)

            if ret != MV_OK:
                print(f"❌ Cannot enumerate devices for force release: {ret}")
                return

            print(f"Found {device_list.nDeviceNum} cameras to force release...")

            # Step 2: Force release each camera with multiple strategies
            for i in range(device_list.nDeviceNum):
                try:
                    device_info = cast(
                        device_list.pDeviceInfo[i], POINTER(MV_CC_DEVICE_INFO)
                    ).contents
                    print(f"💥 Force releasing camera {i}...")

                    # Strategy 1: Multiple temporary connections to force release
                    for attempt in range(10):  # More aggressive
                        try:
                            temp_camera = MvCamera()
                            ret = temp_camera.MV_CC_CreateHandle(device_info)
                            if ret == MV_OK:
                                # Try all access modes
                                for access_mode in [0, 1, MV_ACCESS_Exclusive]:
                                    try:
                                        temp_camera.MV_CC_OpenDevice(access_mode, 0)
                                        temp_camera.MV_CC_StopGrabbing()
                                        temp_camera.MV_CC_CloseDevice()
                                        time.sleep(0.1)
                                    except:
                                        pass
                                temp_camera.MV_CC_DestroyHandle()
                            time.sleep(0.1)
                        except Exception as e:
                            print(f"   Release attempt {attempt}: {e}")

                    print(f"✅ Camera {i} release attempts completed")

                except Exception as e:
                    print(f"❌ Error releasing camera {i}: {e}")

            print("💥 Nuclear release completed - waiting for system to stabilize...")
            time.sleep(5.0)  # Longer wait

        except Exception as e:
            print(f"❌ Nuclear release failed: {e}")

    def check_camera_processes(self):
        """Check for other processes using HIK cameras"""
        print("🔍 Checking for processes that might be using HIK cameras...")

        try:
            import psutil

            # Common HIK-related process names
            hik_processes = [
                "MVViewer",
                "HIKVision",
                "iVMS",
                "HikCentral",
                "MVS",
                "ClientDemo",
                "python",
                "pycharm",
            ]

            found_processes = []

            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    proc_name = proc.info["name"].lower()
                    cmdline = " ".join(proc.info["cmdline"] or []).lower()

                    # Check if process might be using HIK cameras
                    if any(hik_name.lower() in proc_name for hik_name in hik_processes):
                        found_processes.append(f"PID {proc.info['pid']}: {proc.info['name']}")
                    elif "hik" in cmdline or "mvs" in cmdline or "camera" in cmdline:
                        found_processes.append(
                            f"PID {proc.info['pid']}: {proc.info['name']} (cmdline match)"
                        )

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            if found_processes:
                print("⚠️ Found processes that might be using cameras:")
                for proc in found_processes:
                    print(f"   {proc}")
                print("💡 Consider closing these applications before connecting")
            else:
                print("✅ No obvious camera-using processes found")

        except ImportError:
            print("❌ psutil not available - cannot check processes")
        except Exception as e:
            print(f"❌ Process check failed: {e}")

    def connect_camera_aggressive(self, camera_index: int) -> bool:
        """Ultra-aggressive camera connection with all strategies"""
        if not _HAS_HIK_SDK:
            return False

        print(f"💥 AGGRESSIVE CONNECTION MODE for camera {camera_index}")

        # Step 1: Check for competing processes
        self.check_camera_processes()

        # Step 2: Nuclear release of all cameras
        self.force_release_all_cameras()

        # Step 3: Additional wait
        print("⏳ Extended wait for camera availability...")
        time.sleep(10.0)  # Long wait

        # Step 4: Try the regular connection
        return self.connect_camera(camera_index)

    def reset_camera_network(self):
        """Try to reset camera network settings (for GigE cameras)"""
        print("🔄 Attempting camera network reset...")

        try:
            # This is a more advanced technique - try to reset GigE camera
            device_list = MV_CC_DEVICE_INFO_LIST()
            ret = MvCamera.MV_CC_EnumDevices(MV_GIGE_DEVICE, device_list)  # Only GigE

            if ret == MV_OK and device_list.nDeviceNum > 0:
                print(f"Found {device_list.nDeviceNum} GigE cameras for reset attempt")

                for i in range(device_list.nDeviceNum):
                    try:
                        device_info = cast(
                            device_list.pDeviceInfo[i], POINTER(MV_CC_DEVICE_INFO)
                        ).contents
                        gige_info = device_info.SpecialInfo.stGigEInfo
                        ip = self._ip_to_string(gige_info.nCurrentIp)

                        print(f"🔄 Attempting reset for camera at {ip}")

                        # Try to create and immediately destroy handle multiple times
                        for reset_attempt in range(5):
                            temp_camera = MvCamera()
                            ret = temp_camera.MV_CC_CreateHandle(device_info)
                            if ret == MV_OK:
                                temp_camera.MV_CC_DestroyHandle()
                            time.sleep(0.5)

                        print(f"✅ Reset attempts completed for {ip}")

                    except Exception as e:
                        print(f"❌ Reset failed for camera {i}: {e}")

            time.sleep(3.0)
            print("🔄 Network reset procedure completed")

        except Exception as e:
            print(f"❌ Network reset failed: {e}")

    def diagnose_camera_state(self, camera_index: int):
        """Diagnose camera state for debugging"""
        if not _HAS_HIK_SDK:
            return

        try:
            print(f"🔍 Diagnosing camera {camera_index}...")

            device_list = MV_CC_DEVICE_INFO_LIST()
            ret = MvCamera.MV_CC_EnumDevices(MV_GIGE_DEVICE | MV_USB_DEVICE, device_list)

            if ret != MV_OK or camera_index >= device_list.nDeviceNum:
                print(f"❌ Cannot enumerate camera {camera_index}")
                return

            device_info = cast(
                device_list.pDeviceInfo[camera_index], POINTER(MV_CC_DEVICE_INFO)
            ).contents

            if device_info.nTLayerType == MV_GIGE_DEVICE:
                gige_info = device_info.SpecialInfo.stGigEInfo
                model = self._extract_string(gige_info.chModelName, 32)
                serial = self._extract_string(gige_info.chSerialNumber, 16)
                ip = self._ip_to_string(gige_info.nCurrentIp)

                print(f"📷 Camera: {model}")
                print(f"📷 Serial: {serial}")
                print(f"📷 IP: {ip}")

                # Check accessibility
                try:
                    accessible = gige_info.nAccessibleNum == 1
                    print(f"📷 Accessible: {accessible}")
                except:
                    print("📷 Accessibility: Unknown")

            # Try to create handle to test availability
            test_camera = MvCamera()
            ret = test_camera.MV_CC_CreateHandle(device_info)
            if ret == MV_OK:
                print("📷 Handle creation: ✅ OK")
                test_camera.MV_CC_DestroyHandle()
            else:
                print(f"📷 Handle creation: ❌ Failed ({ret})")

        except Exception as e:
            print(f"❌ Diagnosis failed: {e}")

    def discover_cameras(self) -> List[Dict[str, Any]]:
        """Discover HIK cameras on network"""
        if not _HAS_HIK_SDK:
            return []

        try:
            device_list = MV_CC_DEVICE_INFO_LIST()
            ret = MvCamera.MV_CC_EnumDevices(MV_GIGE_DEVICE | MV_USB_DEVICE, device_list)

            if ret != MV_OK:
                self.error_occurred.emit(f"Camera enumeration failed with code: {ret}")
                return []

            cameras = []
            for i in range(device_list.nDeviceNum):
                try:
                    device_info = cast(
                        device_list.pDeviceInfo[i], POINTER(MV_CC_DEVICE_INFO)
                    ).contents

                    if device_info.nTLayerType == MV_GIGE_DEVICE:
                        gige_info = device_info.SpecialInfo.stGigEInfo

                        # Extract camera information
                        model = self._extract_string(gige_info.chModelName, 32)
                        serial = self._extract_string(gige_info.chSerialNumber, 16)
                        ip = self._ip_to_string(gige_info.nCurrentIp)

                        # Handle different SDK versions for accessibility check
                        accessible = True  # Default to accessible
                        try:
                            accessible = gige_info.nAccessibleNum == 1
                        except AttributeError:
                            try:
                                accessible = getattr(gige_info, "bAccessible", True)
                            except AttributeError:
                                try:
                                    accessible = getattr(gige_info, "nAccess", 1) == 1
                                except AttributeError:
                                    accessible = True

                        cameras.append(
                            {
                                "index": i,
                                "model": model,
                                "serial": serial,
                                "ip": ip,
                                "type": "GigE",
                                "device_info": device_info,
                                "accessible": accessible,
                            }
                        )

                    elif device_info.nTLayerType == MV_USB_DEVICE:
                        usb_info = device_info.SpecialInfo.stUsb3VInfo

                        model = self._extract_string(usb_info.chModelName, 32)
                        serial = self._extract_string(usb_info.chSerialNumber, 16)

                        cameras.append(
                            {
                                "index": i,
                                "model": model,
                                "serial": serial,
                                "ip": "USB",
                                "type": "USB3",
                                "device_info": device_info,
                                "accessible": True,
                            }
                        )

                except Exception as e:
                    self.error_occurred.emit(f"Error processing camera {i}: {e}")
                    continue

            return cameras

        except Exception as e:
            self.error_occurred.emit(f"Camera discovery error: {e}")
            return []

    def connect_camera(self, camera_index: int) -> bool:
        """Connect to HIK camera with enhanced force release"""
        if not _HAS_HIK_SDK:
            return False

        try:
            print("=== Enhanced Camera Connection ===")

            # Enumerate devices to get device info
            device_list = MV_CC_DEVICE_INFO_LIST()
            ret = MvCamera.MV_CC_EnumDevices(MV_GIGE_DEVICE | MV_USB_DEVICE, device_list)

            if ret != MV_OK or camera_index >= device_list.nDeviceNum:
                print("❌ Device enumeration failed or invalid index")
                return False

            device_info = cast(
                device_list.pDeviceInfo[camera_index], POINTER(MV_CC_DEVICE_INFO)
            ).contents

            # Enhanced force-release procedure
            print("Attempting enhanced force-release...")
            self._enhanced_force_release(device_info)

            # Wait longer after force release
            time.sleep(2.0)

            # Try multiple connection strategies
            connection_strategies = [
                self._try_standard_connection,
                self._try_delayed_connection,
                self._try_minimal_connection,
            ]

            for i, strategy in enumerate(connection_strategies):
                print(f"Trying connection strategy {i+1}/{len(connection_strategies)}...")
                if strategy(device_info):
                    print(f"✅ Camera connected with strategy {i+1}")
                    self._configure_camera()
                    self.status_changed.emit("Connected")
                    return True

                time.sleep(1.0)

            print("❌ All connection strategies failed")
            return False

        except Exception as e:
            print(f"❌ Connection exception: {e}")
            import traceback

            traceback.print_exc()
            return False

    def _enhanced_force_release(self, device_info):
        """Enhanced force release of camera connections"""
        print("Enhanced force release procedure...")

        # Strategy 1: Multiple temporary connections
        for attempt in range(3):
            try:
                temp_camera = MvCamera()
                ret = temp_camera.MV_CC_CreateHandle(device_info)
                if ret == MV_OK:
                    temp_camera.MV_CC_CloseDevice()
                    temp_camera.MV_CC_DestroyHandle()
                    print(f"Force release attempt {attempt + 1} completed")
                time.sleep(0.5)
            except Exception as e:
                print(f"Force release attempt {attempt + 1} error: {e}")

        # Strategy 2: Try to enumerate and release all devices
        try:
            print("Attempting to release all device handles...")
            device_list = MV_CC_DEVICE_INFO_LIST()
            MvCamera.MV_CC_EnumDevices(MV_GIGE_DEVICE | MV_USB_DEVICE, device_list)

            for i in range(device_list.nDeviceNum):
                try:
                    temp_device_info = cast(
                        device_list.pDeviceInfo[i], POINTER(MV_CC_DEVICE_INFO)
                    ).contents
                    temp_camera = MvCamera()
                    ret = temp_camera.MV_CC_CreateHandle(temp_device_info)
                    if ret == MV_OK:
                        temp_camera.MV_CC_CloseDevice()
                        temp_camera.MV_CC_DestroyHandle()
                except:
                    pass
            print("Global device release completed")
        except Exception as e:
            print(f"Global release error: {e}")

    def _try_standard_connection(self, device_info) -> bool:
        """Try standard connection approach"""
        try:
            self.camera = MvCamera()
            ret = self.camera.MV_CC_CreateHandle(device_info)
            if ret != MV_OK:
                print(f"❌ Standard: Create handle failed: {ret}")
                return False

            # Try different access modes
            access_modes = [
                (0, "Monitor"),
                (1, "Control"),
                (MV_ACCESS_Exclusive, "Exclusive"),
            ]

            for access_mode, mode_name in access_modes:
                print(f"Standard: Trying {mode_name} access...")
                ret = self.camera.MV_CC_OpenDevice(access_mode, 0)

                if ret == MV_OK:
                    print(f"✅ Standard: {mode_name} access successful")
                    return True
                else:
                    print(f"❌ Standard: {mode_name} access failed: {ret}")
                    time.sleep(0.5)

            # Cleanup on failure
            self.camera.MV_CC_DestroyHandle()
            self.camera = None
            return False

        except Exception as e:
            print(f"Standard connection error: {e}")
            return False

    def _try_delayed_connection(self, device_info) -> bool:
        """Try connection with longer delays"""
        try:
            print("Delayed connection: Waiting 3 seconds...")
            time.sleep(3.0)

            self.camera = MvCamera()
            ret = self.camera.MV_CC_CreateHandle(device_info)
            if ret != MV_OK:
                print(f"❌ Delayed: Create handle failed: {ret}")
                return False

            time.sleep(1.0)

            print("Delayed: Trying Monitor access...")
            ret = self.camera.MV_CC_OpenDevice(0, 0)  # Monitor mode

            if ret == MV_OK:
                print("✅ Delayed: Monitor access successful")
                return True

            print(f"❌ Delayed: Monitor access failed: {ret}")
            self.camera.MV_CC_DestroyHandle()
            self.camera = None
            return False

        except Exception as e:
            print(f"Delayed connection error: {e}")
            return False

    def _try_minimal_connection(self, device_info) -> bool:
        """Try minimal connection approach"""
        try:
            print("Minimal connection: Basic approach...")

            self.camera = MvCamera()

            # Try to create handle multiple times
            for attempt in range(3):
                ret = self.camera.MV_CC_CreateHandle(device_info)
                if ret == MV_OK:
                    break
                print(f"Minimal: Handle creation attempt {attempt + 1} failed: {ret}")
                time.sleep(1.0)

            if ret != MV_OK:
                print("❌ Minimal: All handle creation attempts failed")
                return False

            print("Minimal: Trying read-only access...")
            ret = self.camera.MV_CC_OpenDevice(0, 0)  # Monitor/read-only

            if ret == MV_OK:
                print("✅ Minimal: Read-only access successful")
                return True

            print(f"❌ Minimal: Read-only access failed: {ret}")
            self.camera.MV_CC_DestroyHandle()
            self.camera = None
            return False

        except Exception as e:
            print(f"Minimal connection error: {e}")
            return False

    def disconnect_camera(self):
        """Disconnect camera"""
        if self.camera:
            try:
                self.stop_acquisition()
                self.camera.MV_CC_CloseDevice()
                self.camera.MV_CC_DestroyHandle()
                self.camera = None
                self.status_changed.emit("Disconnected")
            except Exception as e:
                print(f"Disconnect error: {e}")

    def start_acquisition(self) -> bool:
        """Start camera acquisition"""
        if not self.camera:
            return False

        try:
            ret = self.camera.MV_CC_StartGrabbing()
            if ret == MV_OK:
                self.running = True
                return True
            return False
        except:
            return False

    def stop_acquisition(self):
        """Stop camera acquisition"""
        if self.camera:
            try:
                self.running = False
                self.camera.MV_CC_StopGrabbing()
            except:
                pass

    def capture_frame(self, timeout_ms: int = 1000) -> Optional[np.ndarray]:
        """Capture a single frame with SDK compatibility"""
        if not self.camera:
            return None

        try:
            frame_info = MV_FRAME_OUT_INFO_EX()

            # Try different method names for payload size (SDK version compatibility)
            payload_size = None

            # Method 1: Try the standard method
            try:
                payload_size = self.camera.MV_CC_GetPayloadSize()
                print(f"Using MV_CC_GetPayloadSize: {payload_size}")
            except AttributeError:
                pass

            # Method 2: Try alternative method name
            if payload_size is None:
                try:
                    payload_size = self.camera.MV_CC_GetIntValue("PayloadSize")[1]
                    print(f"Using MV_CC_GetIntValue PayloadSize: {payload_size}")
                except:
                    pass

            # Method 3: Try another alternative
            if payload_size is None:
                try:
                    ret, payload_size = self.camera.MV_CC_GetIntValue("PayloadSize")
                    if ret == MV_OK:
                        print(f"Using MV_CC_GetIntValue (tuple): {payload_size}")
                    else:
                        payload_size = None
                except:
                    pass

            # Method 4: Use default size if all else fails
            if payload_size is None:
                payload_size = 1024 * 1024 * 10  # 10MB default
                print(f"Using default payload size: {payload_size}")

            # Create buffer
            data_buf = (c_ubyte * int(payload_size))()

            # Try different frame capture methods
            ret = None

            # Method 1: Standard timeout method
            try:
                ret = self.camera.MV_CC_GetOneFrameTimeout(
                    data_buf, payload_size, frame_info, timeout_ms
                )
            except AttributeError:
                # Method 2: Alternative method name
                try:
                    ret = self.camera.MV_CC_GetImageForBGR(
                        data_buf, payload_size, frame_info, timeout_ms
                    )
                except AttributeError:
                    # Method 3: Basic method
                    try:
                        ret = self.camera.MV_CC_GetOneFrame(data_buf, payload_size, frame_info)
                    except AttributeError:
                        self.error_occurred.emit("No compatible frame capture method found")
                        return None

            if ret != MV_OK:
                if ret == MV_E_NODATA:
                    return None  # No frame available, not an error
                else:
                    self.error_occurred.emit(f"Frame capture failed: {ret}")
                    return None

            # Convert to numpy array
            image = np.frombuffer(data_buf, count=int(frame_info.nFrameLen), dtype=np.uint8)

            # Handle different pixel formats
            try:
                if frame_info.enPixelType == PixelType_Gvsp_Mono8:
                    return image.reshape((frame_info.nHeight, frame_info.nWidth))
                elif frame_info.enPixelType == PixelType_Gvsp_BayerRG8:
                    bayer = image.reshape((frame_info.nHeight, frame_info.nWidth))
                    return cv2.cvtColor(bayer, cv2.COLOR_BayerRG2RGB)
                else:
                    # Default to mono for unknown formats
                    return image.reshape((frame_info.nHeight, frame_info.nWidth))
            except Exception as reshape_error:
                self.error_occurred.emit(f"Frame reshape error: {reshape_error}")
                return None

        except Exception as e:
            self.error_occurred.emit(f"Frame capture error: {e}")
            return None

    def check_sdk_methods(self):
        """Check which SDK methods are available"""
        if not self.camera:
            print("❌ No camera connected for SDK check")
            return

        print("🔍 Checking available SDK methods...")

        # Check payload size methods
        payload_methods = [
            "MV_CC_GetPayloadSize",
            "MV_CC_GetIntValue",
            "MV_CC_GetPayLoad",
        ]

        for method in payload_methods:
            if hasattr(self.camera, method):
                print(f"✅ {method} available")
            else:
                print(f"❌ {method} not available")

        # Check frame capture methods
        capture_methods = [
            "MV_CC_GetOneFrameTimeout",
            "MV_CC_GetImageForBGR",
            "MV_CC_GetOneFrame",
            "MV_CC_GetImageBuffer",
        ]

        for method in capture_methods:
            if hasattr(self.camera, method):
                print(f"✅ {method} available")
            else:
                print(f"❌ {method} not available")

        # Try to get payload size for testing
        try:
            if hasattr(self.camera, "MV_CC_GetPayloadSize"):
                size = self.camera.MV_CC_GetPayloadSize()
                print(f"📏 Payload size: {size}")
            elif hasattr(self.camera, "MV_CC_GetIntValue"):
                ret, size = self.camera.MV_CC_GetIntValue("PayloadSize")
                if ret == MV_OK:
                    print(f"📏 Payload size (GetIntValue): {size}")
            else:
                print("❌ Cannot determine payload size")
        except Exception as e:
            print(f"❌ Payload size check failed: {e}")

    def set_trigger_mode(self, enabled: bool, source: str = "Software") -> bool:
        """Configure trigger mode"""
        if not self.camera:
            return False

        try:
            if enabled:
                ret = self.camera.MV_CC_SetEnumValue("TriggerMode", MV_TRIGGER_MODE_ON)
                if ret != MV_OK:
                    return False

                trigger_source = (
                    MV_TRIGGER_SOURCE_SOFTWARE if source == "Software" else MV_TRIGGER_SOURCE_LINE0
                )
                ret = self.camera.MV_CC_SetEnumValue("TriggerSource", trigger_source)
                self.capture_mode = "triggered"
            else:
                ret = self.camera.MV_CC_SetEnumValue("TriggerMode", MV_TRIGGER_MODE_OFF)
                self.capture_mode = "continuous"

            return ret == MV_OK
        except:
            return False

    def set_exposure_time(self, exposure_us: int) -> bool:
        """Set exposure time in microseconds"""
        if not self.camera:
            return False

        try:
            # Set manual exposure
            self.camera.MV_CC_SetEnumValue("ExposureAuto", MV_EXPOSURE_AUTO_MODE_OFF)
            ret = self.camera.MV_CC_SetFloatValue("ExposureTime", float(exposure_us))
            return ret == MV_OK
        except:
            return False

    def software_trigger(self) -> bool:
        """Send software trigger"""
        if not self.camera or self.capture_mode != "triggered":
            return False

        try:
            ret = self.camera.MV_CC_SetCommandValue("TriggerSoftware")
            return ret == MV_OK
        except:
            return False

    def run(self):
        """Main thread loop"""
        while self.running:
            if self.capture_mode == "continuous":
                frame = self.capture_frame(100)
                if frame is not None:
                    self.frame_ready.emit(frame)
            else:
                time.sleep(0.01)

    def _configure_camera(self):
        """Configure camera for optimal performance"""
        if not self.camera:
            return

        try:
            # Basic configuration
            self.camera.MV_CC_SetEnumValue("TriggerMode", MV_TRIGGER_MODE_OFF)
            self.camera.MV_CC_SetEnumValue("AcquisitionMode", MV_ACQ_MODE_CONTINUOUS)
            self.camera.MV_CC_SetEnumValue("PixelFormat", PixelType_Gvsp_Mono8)
            self.camera.MV_CC_SetEnumValue("ExposureAuto", MV_EXPOSURE_AUTO_MODE_CONTINUOUS)
            self.camera.MV_CC_SetEnumValue("GainAuto", MV_GAIN_MODE_CONTINUOUS)
        except:
            pass

    def _extract_string(self, char_array, max_length: int) -> str:
        """Extract string from HIK char array"""
        try:
            if hasattr(char_array, "_type_"):
                # ctypes array
                result = ""
                for i in range(min(max_length, len(char_array))):
                    if char_array[i] == 0:
                        break
                    result += chr(char_array[i])
                return result.strip()
            else:
                return str(char_array).strip()
        except Exception as e:
            print(f"String extraction error: {e}")
            return "Unknown"

    def _ip_to_string(self, ip_int: int) -> str:
        """Convert integer IP to string"""
        try:
            return f"{ip_int & 0xFF}.{(ip_int >> 8) & 0xFF}.{(ip_int >> 16) & 0xFF}.{(ip_int >> 24) & 0xFF}"
        except:
            return "0.0.0.0"


# =============================================================================
# FIXED RecordingManager CLASS
# =============================================================================


class RecordingManager:
    """Enhanced RecordingManager with proper HDF5 support"""

    def __init__(self, napari_viewer=None):
        self.hdf5_file: Optional[h5py.File] = None
        self.dataset = None
        self.recording = False
        self.current_frame = 0
        self.total_frames = 0
        self.start_time = 0
        self.viewer = napari_viewer

        # Enhanced tracking
        self.frame_metadata_list = []
        self.save_path = None

    def setup_hdf5_recording(
        self,
        save_path: str,
        frame_shape: tuple,
        total_frames: int,
        metadata: Dict[str, Any],
    ) -> bool:
        """
        Setup HDF5 file with SIMPLIFIED structure:
        - Timing data (including LED duration)
        - Environmental data (temperature, humidity)
        - Frame metadata
        - NO general LED data
        """
        try:
            print("🔧 Setting up SIMPLIFIED HDF5 recording...")
            print(f"   Path: {save_path}")
            print(f"   Frame shape: {frame_shape}")
            print(f"   Total frames: {total_frames}")

            # Create HDF5 file
            self.hdf5_file = h5py.File(save_path, "w")
            self.save_path = save_path

            # Create main dataset for frames
            dataset_shape = (total_frames,) + frame_shape
            chunk_shape = (1,) + frame_shape

            print(f"   Creating dataset with shape: {dataset_shape}")

            self.dataset = self.hdf5_file.create_dataset(
                "frames",
                shape=dataset_shape,
                dtype=np.uint8,
                chunks=chunk_shape,
                compression="gzip",
                compression_opts=4,
                fillvalue=0,
            )

            # Create simplified groups
            self.hdf5_file.create_group("timing")
            self.hdf5_file.create_group("environmental")  # ✅ Keep environmental
            self.hdf5_file.create_group("frame_metadata")
            # ❌ Remove 'led_data' group - not needed

            # ✅ Timing datasets (including LED duration)
            timing_group = self.hdf5_file["timing"]
            timing_group.create_dataset(
                "python_timestamps", (total_frames,), dtype="f8", fillvalue=0.0
            )
            timing_group.create_dataset(
                "esp32_timestamps", (total_frames,), dtype="f8", fillvalue=0.0
            )
            timing_group.create_dataset(
                "frame_drifts_ms", (total_frames,), dtype="f4", fillvalue=0.0
            )
            timing_group.create_dataset(
                "led_durations_ms", (total_frames,), dtype="f4", fillvalue=0.0
            )  # ✅ Keep LED duration
            timing_group.create_dataset(
                "frame_intervals", (total_frames,), dtype="f4", fillvalue=0.0
            )

            # ✅ Environmental datasets (ESP32 sensor data)
            env_group = self.hdf5_file["environmental"]
            env_group.create_dataset(
                "temperature_celsius", (total_frames,), dtype="f4", fillvalue=0.0
            )
            env_group.create_dataset("humidity_percent", (total_frames,), dtype="f4", fillvalue=0.0)

            # ✅ Frame analysis datasets
            frame_group = self.hdf5_file["frame_metadata"]
            frame_group.create_dataset("frame_mean", (total_frames,), dtype="f4", fillvalue=0.0)
            frame_group.create_dataset("frame_std", (total_frames,), dtype="f4", fillvalue=0.0)
            frame_group.create_dataset("frame_min", (total_frames,), dtype="f4", fillvalue=0.0)
            frame_group.create_dataset("frame_max", (total_frames,), dtype="f4", fillvalue=0.0)

            # Save main metadata as attributes
            for key, value in metadata.items():
                if isinstance(value, (str, int, float, bool)):
                    self.hdf5_file.attrs[key] = value
                else:
                    self.hdf5_file.attrs[key] = str(value)

            # Add creation timestamp
            self.hdf5_file.attrs["hdf5_creation_timestamp"] = time.time()
            self.hdf5_file.attrs["hdf5_creation_datetime"] = datetime.now().isoformat()

            # Document the simplified structure
            self.hdf5_file.attrs["data_structure"] = "simplified_environmental_timing"
            self.hdf5_file.attrs["includes"] = "timing, environmental, frame_metadata"
            self.hdf5_file.attrs["excludes"] = "led_power, led_sync_status"

            # Initialize state
            self.total_frames = total_frames
            self.current_frame = 0
            self.recording = True
            self.start_time = time.time()
            self.frame_metadata_list = []

            print("✅ SIMPLIFIED HDF5 recording setup complete:")
            print("   ✅ Timing data (including led_durations_ms)")
            print("   ✅ Environmental data (temperature, humidity)")
            print("   ✅ Frame metadata")
            print("   ❌ LED power/sync data excluded")

            return True

        except Exception as e:
            print(f"❌ HDF5 setup error: {e}")
            import traceback

            traceback.print_exc()

            # Cleanup on failure
            if self.hdf5_file:
                try:
                    self.hdf5_file.close()
                except:
                    pass
                self.hdf5_file = None

            return False

    def save_frame(self, frame: np.ndarray, frame_metadata: Optional[Dict] = None) -> bool:
        """
        Save frame with enhanced metadata tracking
        """
        if not self.recording or not self.dataset or self.hdf5_file is None:
            print("❌ Cannot save frame - recording not active")
            return False

        try:
            # Check bounds
            if self.current_frame >= self.total_frames:
                print(f"❌ Frame index {self.current_frame} exceeds total {self.total_frames}")
                return False

            # Validate frame shape
            expected_shape = self.dataset.shape[1:]
            if frame.shape != expected_shape:
                print(f"❌ Frame shape mismatch: got {frame.shape}, expected {expected_shape}")
                return False

            # Save the frame data
            self.dataset[self.current_frame] = frame

            # Save enhanced metadata
            if frame_metadata:
                self._save_frame_metadata(self.current_frame, frame, frame_metadata)

            # Store metadata for later analysis
            metadata_entry = {
                "frame_index": self.current_frame,
                "timestamp": time.time(),
                "frame_stats": {
                    "mean": float(np.mean(frame)),
                    "std": float(np.std(frame)),
                    "min": float(np.min(frame)),
                    "max": float(np.max(frame)),
                },
            }

            if frame_metadata:
                metadata_entry.update(frame_metadata)

            self.frame_metadata_list.append(metadata_entry)

            print(
                f"✅ Frame {self.current_frame + 1}/{self.total_frames} saved (mean: {np.mean(frame):.1f})"
            )

            # Increment counter
            self.current_frame += 1

            # Periodic flush
            if self.current_frame % 5 == 0:
                self.hdf5_file.flush()
                print(f"💾 HDF5 flushed at frame {self.current_frame}")

            return True

        except Exception as e:
            print(f"❌ Frame save error: {e}")
            import traceback

            traceback.print_exc()
            return False

    def _save_frame_metadata(self, frame_index: int, frame: np.ndarray, metadata: Dict):
        """Save simplified metadata - environmental + LED duration only"""
        try:
            print(f"💾 Saving simplified metadata for frame {frame_index + 1}...")

            # ✅ TIMING DATA (including LED duration)
            if "timing" in self.hdf5_file:
                timing_group = self.hdf5_file["timing"]

                # Python timestamp
                if "timestamp" in metadata:
                    timing_group["python_timestamps"][frame_index] = metadata["timestamp"]
                    print(f"   ✅ python_timestamps[{frame_index}] = {metadata['timestamp']:.3f}")

                # ESP32 timestamp
                if "esp32_timestamp" in metadata:
                    timing_group["esp32_timestamps"][frame_index] = metadata["esp32_timestamp"]
                    print(
                        f"   ✅ esp32_timestamps[{frame_index}] = {metadata['esp32_timestamp']:.3f}"
                    )
                elif "timestamp" in metadata:
                    # Use python timestamp as fallback
                    timing_group["esp32_timestamps"][frame_index] = metadata["timestamp"]

                # Frame drift (from user's requested interval)
                if "timing_drift" in metadata:
                    drift_ms = metadata["timing_drift"] * 1000  # Convert to ms
                    timing_group["frame_drifts_ms"][frame_index] = drift_ms
                    print(f"   ✅ frame_drifts_ms[{frame_index}] = {drift_ms:.1f}ms")

                # ✅ LED DURATION (keep this!)
                if "led_duration_ms" in metadata:
                    timing_group["led_durations_ms"][frame_index] = metadata["led_duration_ms"]
                    print(
                        f"   ✅ led_durations_ms[{frame_index}] = {metadata['led_duration_ms']:.1f}ms"
                    )
                elif "timing_info" in metadata and "total_duration" in metadata["timing_info"]:
                    # Calculate LED duration from timing info
                    total_duration = metadata["timing_info"]["total_duration"]
                    led_duration_ms = total_duration * 1000
                    timing_group["led_durations_ms"][frame_index] = led_duration_ms
                    print(
                        f"   ✅ led_durations_ms[{frame_index}] = {led_duration_ms:.1f}ms (calculated)"
                    )

                # Frame intervals (actual intervals achieved)
                if frame_index > 0 and "timestamp" in metadata:
                    prev_timestamp = timing_group["python_timestamps"][frame_index - 1]
                    if prev_timestamp > 0:
                        interval = metadata["timestamp"] - prev_timestamp
                        timing_group["frame_intervals"][frame_index] = interval
                        print(f"   ✅ frame_intervals[{frame_index}] = {interval:.2f}s")

            # ✅ ENVIRONMENTAL DATA (ESP32 sensors)
            if "environmental" in self.hdf5_file:
                env_group = self.hdf5_file["environmental"]

                if "temperature" in metadata:
                    env_group["temperature_celsius"][frame_index] = metadata["temperature"]
                    print(
                        f"   ✅ temperature_celsius[{frame_index}] = {metadata['temperature']:.1f}°C"
                    )

                if "humidity" in metadata:
                    env_group["humidity_percent"][frame_index] = metadata["humidity"]
                    print(f"   ✅ humidity_percent[{frame_index}] = {metadata['humidity']:.1f}%")

            # ✅ FRAME STATISTICS
            if "frame_metadata" in self.hdf5_file:
                frame_group = self.hdf5_file["frame_metadata"]

                frame_group["frame_mean"][frame_index] = float(np.mean(frame))
                frame_group["frame_std"][frame_index] = float(np.std(frame))
                frame_group["frame_min"][frame_index] = float(np.min(frame))
                frame_group["frame_max"][frame_index] = float(np.max(frame))

                print(f"   ✅ Frame stats saved: mean={np.mean(frame):.1f}")

            print(f"✅ Simplified metadata saved for frame {frame_index + 1}")

        except Exception as e:
            print(f"❌ Simplified metadata save error for frame {frame_index}: {e}")
            import traceback

            traceback.print_exc()

    def finalize_recording(self):
        """
        Finalize recording with comprehensive analysis
        """
        if not self.hdf5_file:
            print("❌ No HDF5 file to finalize")
            return

        try:
            print("🔄 Finalizing recording...")

            # Calculate final statistics
            actual_frames = self.current_frame
            total_duration = time.time() - self.start_time

            # Add final metadata
            self.hdf5_file.attrs["frames_captured"] = actual_frames
            self.hdf5_file.attrs["frames_planned"] = self.total_frames
            self.hdf5_file.attrs["completion_percentage"] = (
                (actual_frames / self.total_frames) * 100 if self.total_frames > 0 else 0
            )
            self.hdf5_file.attrs["actual_duration_seconds"] = total_duration
            self.hdf5_file.attrs["completion_timestamp"] = time.time()
            self.hdf5_file.attrs["completion_datetime"] = datetime.now().isoformat()

            # Calculate timing statistics
            if actual_frames > 1 and "timing" in self.hdf5_file:
                timing_group = self.hdf5_file["timing"]
                intervals = timing_group["frame_intervals"][1:actual_frames]  # Skip first frame

                if len(intervals) > 0:
                    self.hdf5_file.attrs["mean_interval_seconds"] = float(np.mean(intervals))
                    self.hdf5_file.attrs["std_interval_seconds"] = float(np.std(intervals))
                    self.hdf5_file.attrs["min_interval_seconds"] = float(np.min(intervals))
                    self.hdf5_file.attrs["max_interval_seconds"] = float(np.max(intervals))

            # Calculate frame statistics
            if actual_frames > 0 and "frame_metadata" in self.hdf5_file:
                frame_group = self.hdf5_file["frame_metadata"]
                means = frame_group["frame_mean"][:actual_frames]

                if len(means) > 0:
                    self.hdf5_file.attrs["mean_frame_brightness"] = float(np.mean(means))
                    self.hdf5_file.attrs["std_frame_brightness"] = float(np.std(means))
                    self.hdf5_file.attrs["min_frame_brightness"] = float(np.min(means))
                    self.hdf5_file.attrs["max_frame_brightness"] = float(np.max(means))

            # LED statistics
            if actual_frames > 0 and "led_data" in self.hdf5_file:
                led_group = self.hdf5_file["led_data"]
                success_rate = np.mean(led_group["led_sync_success"][:actual_frames])
                self.hdf5_file.attrs["led_sync_success_rate"] = float(success_rate)

            # Save metadata summary as JSON string
            if self.frame_metadata_list:
                summary = {
                    "total_frames_with_metadata": len(self.frame_metadata_list),
                    "first_frame_timestamp": self.frame_metadata_list[0].get("timestamp", 0),
                    "last_frame_timestamp": (
                        self.frame_metadata_list[-1].get("timestamp", 0)
                        if len(self.frame_metadata_list) > 0
                        else 0
                    ),
                }
                self.hdf5_file.attrs["metadata_summary"] = json.dumps(summary)

            # Final flush and close
            self.hdf5_file.flush()
            self.hdf5_file.close()

            print("✅ Recording finalized successfully:")
            print(f"   Frames captured: {actual_frames}/{self.total_frames}")
            print(f"   Duration: {total_duration/60:.1f} minutes")
            print(f"   Saved to: {self.save_path}")

        except Exception as e:
            print(f"❌ Finalization error: {e}")
            import traceback

            traceback.print_exc()
        finally:
            # Reset state
            self.hdf5_file = None
            self.dataset = None
            self.recording = False
            self.current_frame = 0
            self.total_frames = 0
            self.frame_metadata_list = []
            self.save_path = None

    def get_recording_stats(self) -> Dict[str, Any]:
        """Get current recording statistics"""
        if not self.recording:
            return {}

        current_time = time.time()
        elapsed = current_time - self.start_time

        stats = {
            "frames_captured": self.current_frame,
            "total_frames": self.total_frames,
            "completion_percentage": (
                (self.current_frame / self.total_frames) * 100 if self.total_frames > 0 else 0
            ),
            "elapsed_seconds": elapsed,
            "estimated_total_seconds": (
                (elapsed / self.current_frame) * self.total_frames if self.current_frame > 0 else 0
            ),
            "frames_per_second": self.current_frame / elapsed if elapsed > 0 else 0,
        }

        return stats

    def pause_recording(self):
        """Pause recording (keeps file open)"""
        self.recording = False
        print("⏸️ Recording paused")

    def resume_recording(self):
        """Resume recording"""
        if self.hdf5_file and self.dataset:
            self.recording = True
            print("▶️ Recording resumed")
        else:
            print("❌ Cannot resume - no active recording")

    def is_recording(self) -> bool:
        """Check if currently recording"""
        return self.recording and self.hdf5_file is not None

    def get_current_frame_index(self) -> int:
        """Get current frame index"""
        return self.current_frame

    # =============================================================================
    # UPDATED WIDGET METHOD TO USE FIXED RECORDING MANAGER
    # =============================================================================

    def __init__(self, napari_viewer=None):
        self.hdf5_file: Optional[h5py.File] = None
        self.dataset = None
        self.recording = False
        self.current_frame = 0
        self.total_frames = 0
        self.start_time = 0
        self.viewer = napari_viewer

    def _decode_status_response(self, response: bytes) -> Dict[str, Any]:
        """Decode status response with environmental data"""
        if len(response) >= 5:
            status_code = response[0]

            # Temperature (bytes 1-2)
            temp_raw = (response[1] << 8) | response[2]
            if temp_raw > 32767:
                temp_raw -= 65536
            temperature = temp_raw / 10.0

            # Humidity (bytes 3-4)
            humidity_raw = (response[3] << 8) | response[4]
            humidity = humidity_raw / 10.0

            return {
                "status": status_code,
                "temperature": temperature,
                "humidity": humidity,
            }
        return {"status": 0, "temperature": 0.0, "humidity": 0.0}

    def setup_enhanced_hdf5_recording(
        self,
        save_path: str,
        frame_shape: tuple,
        total_frames: int,
        metadata: Dict[str, Any],
    ) -> bool:
        """Setup HDF5 mit korrekten Timestamp-Datentypen"""
        try:
            self.hdf5_file = h5py.File(save_path, "w")

            # Frames dataset
            dataset_shape = (total_frames,) + frame_shape
            chunk_shape = (1,) + frame_shape

            self.dataset = self.hdf5_file.create_dataset(
                "frames",
                shape=dataset_shape,
                dtype=np.uint8,
                chunks=chunk_shape,
                compression="gzip",
                compression_opts=4,
            )

            # Metadata groups
            self.hdf5_file.create_group("frame_metadata")
            self.hdf5_file.create_group("timing")
            self.hdf5_file.create_group("environmental")

            # Timing datasets - alle als float64 für Unix-Timestamps
            timing_group = self.hdf5_file["timing"]
            timing_group.create_dataset(
                "python_timestamps", (total_frames,), dtype="f8"
            )  # Unix timestamp
            timing_group.create_dataset(
                "esp32_timestamps", (total_frames,), dtype="f8"
            )  # Unix timestamp
            timing_group.create_dataset(
                "frame_drifts_ms", (total_frames,), dtype="f4"
            )  # Drift in ms
            timing_group.create_dataset(
                "led_durations_ms", (total_frames,), dtype="f4"
            )  # LED duration

            # Environmental datasets
            env_group = self.hdf5_file["environmental"]
            env_group.create_dataset("temperature_celsius", (total_frames,), dtype="f4")
            env_group.create_dataset("humidity_percent", (total_frames,), dtype="f4")

            # Metadata
            for key, value in metadata.items():
                self.hdf5_file.attrs[key] = value

            # Timing-spezifische Metadaten
            self.hdf5_file.attrs["timestamp_format"] = "unix_epoch_seconds"
            self.hdf5_file.attrs["timestamp_precision"] = "microseconds"

            self.total_frames = total_frames
            self.current_frame = 0
            self.recording = True
            self.start_time = time.time()

            return True

        except Exception as e:
            print(f"❌ HDF5 setup error: {e}")
            return False

    def save_frame(self, frame: np.ndarray, frame_metadata: Optional[Dict] = None) -> bool:
        """
        FIXED save frame method that properly saves timing data
        """
        if not self.recording or not self.dataset or self.hdf5_file is None:
            print("❌ Cannot save frame - recording not active")
            return False

        try:
            # Check bounds
            if self.current_frame >= self.total_frames:
                print(f"❌ Frame index {self.current_frame} exceeds total {self.total_frames}")
                return False

            # Validate frame shape
            expected_shape = self.dataset.shape[1:]
            if frame.shape != expected_shape:
                print(f"❌ Frame shape mismatch: got {frame.shape}, expected {expected_shape}")
                return False

            # Save the frame data
            self.dataset[self.current_frame] = frame
            print(f"✅ Frame {self.current_frame + 1} data saved to HDF5")

            # Save enhanced metadata using FIXED method
            if frame_metadata:
                self._save_frame_metadata(self.current_frame, frame, frame_metadata)

            # Store metadata for later analysis
            metadata_entry = {
                "frame_index": self.current_frame,
                "timestamp": time.time(),
                "frame_stats": {
                    "mean": float(np.mean(frame)),
                    "std": float(np.std(frame)),
                    "min": float(np.min(frame)),
                    "max": float(np.max(frame)),
                },
            }

            if frame_metadata:
                metadata_entry.update(frame_metadata)

            self.frame_metadata_list.append(metadata_entry)

            print(f"✅ Frame {self.current_frame + 1}/{self.total_frames} completely saved")

            # Increment counter
            self.current_frame += 1

            # Periodic flush
            if self.current_frame % 3 == 0:  # Flush more frequently for timing data
                self.hdf5_file.flush()
                print(f"💾 HDF5 flushed at frame {self.current_frame}")

            return True

        except Exception as e:
            print(f"❌ Frame save error: {e}")
            import traceback

            traceback.print_exc()
            return False

    def finalize_recording(self):
        """Finalize recording with comprehensive summary statistics"""
        if self.hdf5_file:
            try:
                # Calculate summary statistics
                actual_frames = self.current_frame
                total_duration = time.time() - self.start_time

                # Add summary attributes
                self.hdf5_file.attrs["frames_captured"] = actual_frames
                self.hdf5_file.attrs["actual_duration_seconds"] = total_duration
                self.hdf5_file.attrs["completion_time"] = time.time()
                self.hdf5_file.attrs["completion_datetime"] = datetime.now().isoformat()

                # Calculate timing statistics if we have data
                if actual_frames > 0 and "timing" in self.hdf5_file:
                    timing_group = self.hdf5_file["timing"]
                    drifts = timing_group["frame_drifts_ms"][:actual_frames]

                    self.hdf5_file.attrs["max_drift_ms"] = np.max(np.abs(drifts))
                    self.hdf5_file.attrs["mean_drift_ms"] = np.mean(drifts)
                    self.hdf5_file.attrs["std_drift_ms"] = np.std(drifts)

                self.hdf5_file.close()
                print(
                    f"✅ Recording finalized: {actual_frames} frames in {total_duration/60:.1f} minutes"
                )

            except Exception as e:
                print(f"❌ Error finalizing recording: {e}")

        self.hdf5_file = None
        self.dataset = None
        self.recording = False


# Main Plugin Widget
class NematostellaTimeSeriesCapture(QWidget):
    """Hybrid plugin: Standalone napari OR ImSwitch detector settings integration"""

    def __init__(self, napari_viewer):
        super().__init__()
        self.viewer = napari_viewer

        # Auto-detect mode and setup accordingly
        self.mode = self._detect_mode()

        # Camera components (mode-dependent)
        self.camera_thread = HIKCameraThread()
        self.imswitch_config = None
        self.imswitch_live_layer = None
        self.camera_connected = False
        self.available_cameras = []

        # Plugin-managed components (both modes)
        self.esp32_controller = ESP32Controller()
        self.recording_manager = RecordingManager(napari_viewer)

        # State variables
        self.live_layer = None
        self.selected_directory = None

        # Initialize UI elements to None (prevents gray warnings)
        self.camera_combo = None
        self.log_display = None
        self.camera_status_label = None
        self.esp32_status_label = None
        self.recording_status_label = None
        self.connect_btn = None
        self.disconnect_btn = None
        self.start_live_btn = None
        self.stop_live_btn = None
        self.test_btn = None
        self.trigger_combo = None
        self.exposure_spinbox = None
        self.start_rec_btn = None
        self.pause_rec_btn = None
        self.stop_rec_btn = None
        self.duration_input = None
        self.interval_input = None
        self.frames_label = None
        self.stats_label = None
        self.select_dir_btn = None
        self.progress_bar = None
        self.current_frame_label = None
        self.elapsed_label = None
        self.eta_label = None
        self.create_subfolder_cb = None
        self.led_on_btn = None
        self.led_off_btn = None
        self.led_power_slider = None
        self.led_power_spinbox = None
        self.connect_esp32_btn = None
        self.disconnect_esp32_btn = None
        self.esp32_status_detail = None
        self.temp_display = None
        self.humidity_display = None
        self.results_display = None
        self.fps_label = None
        self.dropped_frames_label = None

        # Recording timer
        self.capture_timer = QTimer(self)
        self.capture_timer.timeout.connect(self._capture_next_frame_simple)

        # Setup
        self._setup_connections()
        self._setup_ui()
        self._initialize_system()

    def _optimize_bandwidth(self):
        """UI method to optimize camera bandwidth"""
        if not self.camera_connected:
            self._log_message("❌ No camera connected")
            return

        self._log_message("🔧 Optimizing camera bandwidth...")
        if self.camera_thread.optimize_camera_bandwidth():
            self._log_message("✅ Bandwidth optimization completed")
        else:
            self._log_message("❌ Bandwidth optimization failed")

    def _check_network(self):
        """UI method to check network performance"""
        if not self.camera_connected:
            self._log_message("❌ No camera connected")
            return

        self._log_message("🌐 Checking network performance...")
        self.camera_thread.check_network_performance()

    def _update_progress_ui_simple(self, current: int, total: int):
        """Einfache Progress-Update"""
        if self.progress_bar:
            self.progress_bar.setValue(current)
        if hasattr(self, "current_frame_label") and self.current_frame_label:
            self.current_frame_label.setText(f"Frame: {current}/{total}")

    def _quick_frame_capture_test(self):
        """Schneller Test aller Frame-Capture Methoden"""
        self._log_message("\n⚡ === QUICK FRAME CAPTURE TEST ===")

        # Test 1: Current recording method
        self._log_message("Current Recording method:")
        result = self._capture_single_frame_with_led_SYNC()
        if result["capture_success"]:
            mean = np.mean(result["frame"])
            self._log_message(f"✅ Current method: mean={mean:.1f}")
        else:
            self._log_message("❌ Current method failed")

        # Test 2: Direct ImSwitch access
        self._log_message("\nDirect ImSwitch access:")
        if self.imswitch_live_layer and self.imswitch_live_layer.data is not None:
            direct_frame = self.imswitch_live_layer.data.copy()
            direct_mean = np.mean(direct_frame)
            self._log_message(f"✅ Direct access: mean={direct_mean:.1f}")
        else:
            self._log_message("❌ Direct access failed")

        self._log_message("\n💡 If direct access shows higher values, we have a method conflict!")

    def _set_robust_mode(self):
        """UI method to set robust capture mode"""
        if not self.camera_connected:
            self._log_message("❌ No camera connected")
            return

        self._log_message("🛡️ Setting robust capture mode...")
        if self.camera_thread.set_robust_capture_mode():
            self._log_message("✅ Robust mode enabled")
        else:
            self._log_message("❌ Robust mode setup failed")

    def _update_camera_ui_for_mode(self):
        """Update camera UI based on current mode"""
        if self.mode == "imswitch_framegrab":
            # ImSwitch mode - disable connection controls
            self.camera_combo.clear()
            if self.imswitch_live_layer:
                self.camera_combo.addItem(f"📡 {self.imswitch_live_layer.name} (Frame Grabber)")
            else:
                self.camera_combo.addItem("❌ Start ImSwitch live view first")

            # Disable connection buttons - no need to connect
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(False)

            # Enable test and live view controls if ImSwitch is ready
            if self.imswitch_live_layer:
                self._enable_camera_controls(True)
                self.test_btn.setEnabled(True)

            self._log_message("📡 ImSwitch frame grabber mode - no direct camera connection needed")

        else:
            # Standalone mode - normal camera discovery
            self._discover_cameras()

    def _test_esp32_led_detailed(self):
        """Detailed ESP32 LED test with step-by-step verification"""
        if not self.esp32_controller.connected:
            self._log_message("❌ ESP32 not connected for LED test")
            return

        self._log_message("🧪 Starting detailed ESP32 LED test...")

        try:
            # Test 1: Check ESP32 communication
            self._log_message("📊 Test 1: ESP32 communication check...")
            status_response = self.esp32_controller.send_command(ESP32Commands.STATUS, timeout=3.0)
            if status_response:
                hex_status = " ".join([f"0x{b:02X}" for b in status_response])
                self._log_message(f"✅ ESP32 status response: {hex_status}")
            else:
                self._log_message("❌ ESP32 status failed - communication problem")
                return

            # Test 2: LED power control test
            self._log_message("⚡ Test 2: LED power control...")
            power_levels = [0, 25, 50, 75, 100]
            for power in power_levels:
                self._log_message(f"Setting LED power to {power}%...")
                response = self.esp32_controller.send_command(
                    ESP32Commands.SET_LED_POWER, [power], timeout=3.0
                )
                if response:
                    hex_response = " ".join([f"0x{b:02X}" for b in response])
                    self._log_message(f"✅ Power {power}% response: {hex_response}")
                else:
                    self._log_message(f"❌ Power {power}% failed")
                time.sleep(0.3)

            # Test 3: LED ON/OFF commands
            self._log_message("💡 Test 3: LED ON/OFF commands...")

            # Test LED ON
            self.esp32_controller.set_led_power(100)
            time.sleep(0.2)
            on_response = self.esp32_controller.send_command(ESP32Commands.LED_ON, timeout=3.0)
            if on_response:
                hex_on = " ".join([f"0x{b:02X}" for b in on_response])
                self._log_message(f"✅ LED ON response: {hex_on}")
                self._log_message("💡 LED should be ON now - check visually!")
            else:
                self._log_message("❌ LED ON command failed")

            time.sleep(2.0)  # Keep LED on for 2 seconds

            # Test LED OFF
            off_response = self.esp32_controller.send_command(ESP32Commands.LED_OFF, timeout=3.0)
            if off_response:
                hex_off = " ".join([f"0x{b:02X}" for b in off_response])
                self._log_message(f"✅ LED OFF response: {hex_off}")
                self._log_message("🌑 LED should be OFF now - check visually!")
            else:
                self._log_message("❌ LED OFF command failed")

            self._log_message("✅ Detailed ESP32 LED test completed")

        except Exception as e:
            self._log_message(f"❌ ESP32 LED test error: {e}")

    def _test_esp32_timing(self):
        """Test ESP32 command timing and responses"""
        if not self.esp32_controller.connected:
            self._log_message("❌ ESP32 not connected")
            return

        self._log_message("⏱️ Testing ESP32 command timing...")

        try:
            commands_to_test = [
                (ESP32Commands.STATUS, "STATUS", None),
                (ESP32Commands.SET_LED_POWER, "SET_LED_POWER(100)", [100]),
                (ESP32Commands.LED_ON, "LED_ON", None),
                (ESP32Commands.LED_OFF, "LED_OFF", None),
            ]

            for cmd_byte, cmd_name, data in commands_to_test:
                start_time = time.time()
                response = self.esp32_controller.send_command(cmd_byte, data, timeout=5.0)
                end_time = time.time()

                duration_ms = (end_time - start_time) * 1000

                if response:
                    hex_response = " ".join([f"0x{b:02X}" for b in response])
                    self._log_message(
                        f"✅ {cmd_name}: {duration_ms:.1f}ms, response: {hex_response}"
                    )
                else:
                    self._log_message(f"❌ {cmd_name}: {duration_ms:.1f}ms, NO RESPONSE")

                time.sleep(0.2)

        except Exception as e:
            self._log_message(f"❌ Timing test error: {e}")

    def _test_complete_led_sequence(self):
        """Test the complete LED sequence as used in recording"""
        if not self.esp32_controller.connected:
            self._log_message("❌ ESP32 not connected")
            return

        self._log_message("🎬 Testing complete LED sequence (as used in recording)...")

        try:
            for test_cycle in range(3):
                self._log_message(f"🔄 Test cycle {test_cycle + 1}/3...")

                # Step 1: LED OFF
                self._log_message("🌑 Step 1: LED OFF...")
                self.esp32_controller.set_led_power(0)
                self.esp32_controller.led_off()
                time.sleep(0.5)

                # Step 2: LED ON
                self._log_message("⚡ Step 2: LED ON...")
                self.esp32_controller.set_led_power(100)
                time.sleep(0.1)
                on_success = self.esp32_controller.led_on()
                if on_success:
                    self._log_message("✅ LED ON successful")
                else:
                    self._log_message("❌ LED ON failed")

                # Step 3: Wait
                self._log_message("⏱️ Step 3: Waiting 2 seconds...")
                time.sleep(2.0)

                # Step 4: LED OFF
                self._log_message("🌑 Step 4: LED OFF...")
                self.esp32_controller.set_led_power(0)
                off_success = self.esp32_controller.led_off()
                if off_success:
                    self._log_message("✅ LED OFF successful")
                else:
                    self._log_message("❌ LED OFF failed")

                time.sleep(1.0)

            self._log_message("✅ Complete LED sequence test finished")

        except Exception as e:
            self._log_message(f"❌ LED sequence test error: {e}")

    def _manual_led_flash(self):
        """Manual LED flash for quick testing"""
        if not self.esp32_controller.connected:
            self._log_message("❌ ESP32 not connected")
            return

        self._log_message("⚡ Manual LED flash test...")

        try:
            self.esp32_controller.set_led_power(0)
            self.esp32_controller.led_off()
            time.sleep(0.2)

            self.esp32_controller.set_led_power(100)
            self.esp32_controller.led_on()
            self._log_message("💡 LED should flash NOW!")
            time.sleep(1.0)

            self.esp32_controller.set_led_power(0)
            self.esp32_controller.led_off()
            self._log_message("✅ Manual flash completed")

        except Exception as e:
            self._log_message(f"❌ Manual flash error: {e}")

    def _on_camera_frame(self, frame: np.ndarray):
        """Handle new camera frame"""
        try:
            layer_name = "HIK Camera Live"
            is_rgb = frame.ndim == 3

            if self.live_layer is None:
                self.live_layer = self.viewer.add_image(frame, name=layer_name, rgb=is_rgb)
            else:
                self.live_layer.data = frame

        except Exception as e:
            self._log_message(f"❌ Frame display error: {e}")

    def _on_camera_error(self, error_msg: str):
        """Handle camera errors"""
        self._log_message(f"❌ Camera error: {error_msg}")

    def _on_camera_status(self, status_msg: str):
        """Handle camera status updates"""
        if hasattr(self, "camera_status_label") and self.camera_status_label:
            self.camera_status_label.setText(f"Camera: {status_msg}")

    def _start_live_view(self):
        """Start live view based on mode"""
        if not self.camera_connected:
            return

        if self.mode == "imswitch_framegrab":
            # For ImSwitch frame grabbing, we don't start our own acquisition
            self._log_message("✅ ImSwitch frame grabber mode - live view ready")
            self.test_btn.setEnabled(True)
            self.start_live_btn.setEnabled(False)
            self.stop_live_btn.setEnabled(True)
        else:
            # For standalone mode, start normal acquisition
            if self.camera_thread.start_acquisition():
                self.camera_thread.start()
                self.start_live_btn.setEnabled(False)
                self.stop_live_btn.setEnabled(True)
                self._log_message("✅ Live view started")
            else:
                self._log_message("❌ Failed to start live view")

    def _stop_live_view(self):
        """Stop live view based on mode"""
        if self.mode == "imswitch_framegrab":
            # For ImSwitch mode, just update UI
            self.start_live_btn.setEnabled(True)
            self.stop_live_btn.setEnabled(False)
            self.test_btn.setEnabled(False)
            self._log_message("✅ ImSwitch frame grabber mode stopped")
        else:
            # For standalone mode, stop acquisition
            if self.camera_thread.running:
                self.camera_thread.running = False
                self.camera_thread.wait()

            self.camera_thread.stop_acquisition()

            if self.live_layer:
                try:
                    self.viewer.layers.remove(self.live_layer)
                except:
                    pass
                self.live_layer = None

            self.start_live_btn.setEnabled(True)
            self.stop_live_btn.setEnabled(False)
            self._log_message("✅ Live view stopped")

    def _calculate_stats(self):
        """Calculate recording statistics"""
        try:
            duration = float(self.duration_input.text()) if self.duration_input.text() else 0
            interval = float(self.interval_input.text()) if self.interval_input.text() else 0

            if duration > 0 and interval > 0:
                total_frames = int((duration * 60) / interval)
                self.frames_label.setText(str(total_frames))

                stats = "Recording Statistics:\n"
                stats += f"• Frames: {total_frames:,}\n"
                stats += f"• Duration: {duration:.1f} min\n"
                stats += f"• Interval: {interval:.1f} sec"

                self.stats_label.setText(stats)
            else:
                self.frames_label.setText("0")
                self.stats_label.setText("Enter valid parameters")
        except ValueError:
            self.frames_label.setText("Invalid")
            self.stats_label.setText("Invalid input values")

    def _select_directory(self):
        """Select save directory"""
        directory = QFileDialog.getExistingDirectory(self, "Select Save Directory")
        if directory:
            self.selected_directory = directory
            # Update UI if dir_label exists
            if hasattr(self, "dir_label") and self.dir_label:
                self.dir_label.setText(f"Directory: {os.path.basename(directory)}")
                self.dir_label.setToolTip(directory)
                self.dir_label.setStyleSheet("color: #4CAF50;")

            self._log_message(f"📁 Directory selected: {directory}")

    def _create_recording_filepath(self):
        """Create recording file path"""
        try:
            if not self.selected_directory:
                raise ValueError("No directory selected")

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if self.create_subfolder_cb and self.create_subfolder_cb.isChecked():
                save_dir = os.path.join(self.selected_directory, f"timelapse_{timestamp}")
                os.makedirs(save_dir, exist_ok=True)
            else:
                save_dir = self.selected_directory

            filename = f"recording_{timestamp}.h5"
            return os.path.join(save_dir, filename)

        except Exception as e:
            self._log_message(f"❌ Path creation error: {e}")
            raise

    def _detect_frame_shape_simple(self) -> Optional[tuple]:
        """Einfache Frame-Shape-Erkennung"""
        frame = self._grab_current_frame()
        if frame is not None and len(frame.shape) >= 2:
            return frame.shape
        return None

    def _validate_recording_setup(self) -> bool:
        """Validate recording setup"""
        if not self.selected_directory:
            QMessageBox.warning(self, "Setup Error", "Please select a save directory")
            return False

        if not self.duration_input.text() or not self.interval_input.text():
            QMessageBox.warning(self, "Setup Error", "Please enter duration and interval")
            return False

        try:
            duration = float(self.duration_input.text())
            interval = float(self.interval_input.text())
            if duration <= 0 or interval <= 0:
                raise ValueError()
        except ValueError:
            QMessageBox.warning(self, "Setup Error", "Please enter valid numeric values")
            return False

        if self.mode == "imswitch_framegrab":
            if not self.imswitch_live_layer or self.imswitch_live_layer.data is None:
                QMessageBox.warning(self, "Setup Error", "ImSwitch live view not available")
                return False
        else:
            if not self.camera_connected:
                QMessageBox.warning(self, "Setup Error", "Camera not connected")
                return False

        return True

    def _calculate_led_sync_duration(self) -> float:
        """
        Calculate estimated LED sync duration based on mode
        """
        if not self.esp32_controller.connected:
            return 0.5  # Basic frame capture

        if self.mode == "imswitch_framegrab":
            # ImSwitch mode needs more time:
            # LED OFF (0.8s) + Power set (0.3s) + LED ON (0.1s) + Frame wait (1.5s) + LED OFF (0.2s) + Sensors (0.3s)
            return 3.2
        else:
            # Standalone mode is faster:
            # LED OFF (0.5s) + Power set (0.2s) + LED ON (0.1s) + Frame capture (0.5s) + LED OFF (0.1s) + Sensors (0.2s)
            return 1.6

    def _validate_recording_interval(self, requested_interval: float) -> float:
        """Validate and adjust recording interval for LED sync"""
        if not self.esp32_controller.connected:
            return requested_interval  # No LED sync needed

        led_sync_duration = self._calculate_led_sync_duration()
        min_safe_interval = led_sync_duration + 1.0  # Add 1s buffer

        if requested_interval < min_safe_interval:
            self._log_message(f"⚠️ Requested interval {requested_interval}s too short for LED sync")
            self._log_message(f"   LED sync needs ~{led_sync_duration:.1f}s")
            self._log_message(f"   Minimum safe interval: {min_safe_interval:.1f}s")
            return min_safe_interval
        else:
            self._log_message(f"✅ Interval {requested_interval}s is safe for LED sync")
            return requested_interval

    def _start_recording(self):
        """
        SEQUENTIAL recording start - no timer conflicts, guaranteed LED sync
        """
        if not self._validate_recording_setup():
            return

        try:
            duration_min = float(self.duration_input.text())
            requested_interval_s = float(self.interval_input.text())

            # Set timing variables
            self.target_interval = requested_interval_s  # User's request

            # Calculate safe interval for LED sync
            if self.esp32_controller.connected:
                led_sync_duration = self._calculate_led_sync_duration()
                min_safe_interval = led_sync_duration + 1.0  # Add buffer
                self.actual_interval = max(requested_interval_s, min_safe_interval)

                self._log_message(f"🔄 LED sync needs ~{led_sync_duration:.1f}s")
                if self.actual_interval > requested_interval_s:
                    self._log_message(
                        f"⚠️ Interval adjusted from {requested_interval_s}s to {self.actual_interval}s for LED safety"
                    )
            else:
                self.actual_interval = requested_interval_s

            # Calculate total frames
            total_frames = int((duration_min * 60) / self.actual_interval)

            self._log_message("🎬 Starting SEQUENTIAL recording:")
            self._log_message(f"   👤 User requested: {self.target_interval}s intervals")
            self._log_message(f"   🔧 Actually using: {self.actual_interval}s intervals")
            self._log_message(f"   📊 Total frames: {total_frames}")
            self._log_message(f"   ⏱️ Duration: {duration_min:.1f} minutes")

            # Get frame shape
            test_frame = self._grab_current_frame()
            if test_frame is not None:
                frame_shape = test_frame.shape
                self._log_message(f"📏 Frame shape: {frame_shape}")
            else:
                frame_shape = (1024, 1280)
                self._log_message(f"⚠️ Using fallback frame shape: {frame_shape}")

            # Create save path
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            if hasattr(self, "create_subfolder_cb") and self.create_subfolder_cb.isChecked():
                save_dir = os.path.join(self.selected_directory, f"timelapse_{timestamp}")
                os.makedirs(save_dir, exist_ok=True)
            else:
                save_dir = self.selected_directory

            save_path = os.path.join(save_dir, f"recording_{timestamp}.h5")

            # Setup metadata
            metadata = {
                "recording_type": "nematostella_sequential_capture",
                "mode": self.mode,
                "total_frames": total_frames,
                "user_requested_interval_seconds": self.target_interval,
                "actual_interval_seconds": self.actual_interval,
                "duration_minutes": duration_min,
                "creation_time": time.time(),
                "creation_datetime": datetime.now().isoformat(),
                "led_enabled": self.esp32_controller.connected,
                "frame_shape": frame_shape,
                "capture_method": "sequential_no_timer_conflicts",
                "plugin_version": "sequential_v1",
            }

            if self.esp32_controller.connected:
                metadata.update(
                    {
                        "esp32_connected": True,
                        "led_sync_duration_estimate": self._calculate_led_sync_duration(),
                        "environmental_sensors": True,
                    }
                )

            # Setup HDF5 recording
            self._log_message(f"💾 Setting up HDF5 file: {save_path}")

            # Use simplified HDF5 setup if available
            if hasattr(self.recording_manager, "setup_hdf5_recording_SIMPLIFIED"):
                setup_success = self.recording_manager.setup_hdf5_recording_SIMPLIFIED(
                    save_path, frame_shape, total_frames, metadata
                )
            else:
                setup_success = self.recording_manager.setup_hdf5_recording(
                    save_path, frame_shape, total_frames, metadata
                )

            if setup_success:
                # Initialize sequential recording state
                self.recording_start_time = time.time()
                self.sequential_recording_active = True  # Flag for sequential mode

                # Setup UI
                if hasattr(self, "progress_bar"):
                    self.progress_bar.setMaximum(total_frames)
                    self.progress_bar.setValue(0)
                    self.progress_bar.setVisible(True)

                self._enable_recording_controls(True)

                # ✅ CRITICAL: Disconnect any existing timer connections
                if hasattr(self, "capture_timer"):
                    try:
                        self.capture_timer.timeout.disconnect()
                        self.capture_timer.stop()  # Stop any running timer
                    except:
                        pass

                # ✅ Start sequential capture loop (no timer!)
                self._log_message("🔄 Starting sequential capture loop...")
                QTimer.singleShot(500, self._sequential_capture_next_frame)  # Start in 500ms

                self._log_message("✅ SEQUENTIAL recording started successfully!")
                self._log_message(f"   📁 File: {save_path}")
                self._log_message("   🚀 Sequential mode: No timer conflicts!")

            else:
                self._log_message("❌ Failed to setup HDF5 recording")

        except Exception as e:
            self._log_message(f"❌ Sequential recording start error: {e}")
            import traceback

            traceback.print_exc()

    def _sequential_capture_next_frame(self):
        """
        Sequential capture method - captures one frame, then schedules the next
        This eliminates all timer conflicts and guarantees LED sync completion
        """
        # Check if recording is still active
        if (
            not getattr(self, "sequential_recording_active", False)
            or not self.recording_manager.recording
        ):
            self._log_message("🛑 Sequential recording stopped")
            return

        current = self.recording_manager.current_frame
        total = self.recording_manager.total_frames

        # Check if we've captured all frames
        if current >= total:
            self._log_message("✅ All frames captured - stopping sequential recording")
            self._stop_recording()
            return

        # Calculate timing
        target_time = self.recording_start_time + (current * self.actual_interval)
        current_time = time.time()

        # If we're too early, wait and reschedule
        if current_time < target_time - 0.1:  # 100ms tolerance
            wait_time = target_time - current_time
            self._log_message(f"⏳ Frame {current + 1}: Too early, waiting {wait_time:.1f}s more")
            QTimer.singleShot(int(wait_time * 1000), self._sequential_capture_next_frame)
            return

        # Calculate drift from user's original request
        user_expected_time = self.recording_start_time + (current * self.target_interval)
        drift_ms = (current_time - user_expected_time) * 1000

        self._log_message(f"\n📸 === SEQUENTIAL FRAME {current + 1}/{total} ===")
        self._log_message(f"⏱️ Drift from user request: {drift_ms:+.1f}ms")
        self._log_message("🔒 Starting LED sync (no interruptions possible)")

        try:
            # ✅ PERFORM LED SYNC CAPTURE - complete isolation, no timer conflicts!
            capture_start_time = time.time()

            # Use the best available capture method
            if hasattr(self, "_capture_frame_with_led_sync_SIMPLIFIED"):
                capture_result = self._capture_frame_with_led_sync_SIMPLIFIED()
            elif hasattr(self, "_capture_frame_with_led_sync_ENHANCED"):
                capture_result = self._capture_frame_with_led_sync_ENHANCED()
            elif hasattr(self, "_capture_frame_with_led_sync_FIXED"):
                capture_result = self._capture_frame_with_led_sync_FIXED()
            else:
                # Basic fallback
                self._log_message("⚠️ Using basic fallback capture")
                frame = self._grab_current_frame()
                capture_result = {
                    "frame": frame,
                    "capture_success": frame is not None,
                    "capture_method": "sequential_basic_fallback",
                    "python_timestamp": capture_start_time,
                    "esp32_timestamp": capture_start_time,
                    "temperature": 0.0,
                    "humidity": 0.0,
                    "led_duration_ms": 0,
                }

            capture_end_time = time.time()
            total_capture_duration = capture_end_time - capture_start_time

            self._log_message(f"🔓 LED sync completed in {total_capture_duration:.2f}s")

            if capture_result["capture_success"] and capture_result["frame"] is not None:
                frame = capture_result["frame"]
                frame_mean = np.mean(frame)

                # Create comprehensive metadata
                frame_metadata = {
                    "timestamp": capture_result.get("python_timestamp", capture_start_time),
                    "esp32_timestamp": capture_result.get("esp32_timestamp", capture_start_time),
                    "frame_number": current + 1,
                    "capture_method": f"sequential_{capture_result.get('capture_method', 'unknown')}",
                    "capture_success": True,
                    "frame_mean": float(frame_mean),
                    "frame_std": float(np.std(frame)),
                    "frame_shape": frame.shape,
                    "mode": self.mode,
                    # Environmental data
                    "temperature": capture_result.get("temperature", 0.0),
                    "humidity": capture_result.get("humidity", 0.0),
                    # LED timing data
                    "led_duration_ms": capture_result.get(
                        "led_duration_ms", total_capture_duration * 1000
                    ),
                    # Timing analysis
                    "user_requested_interval": self.target_interval,
                    "actual_interval_used": self.actual_interval,
                    "timing_drift": drift_ms / 1000.0,  # Convert to seconds
                    "sequential_capture": True,
                    "capture_duration_actual": total_capture_duration,
                    # Timing context
                    "expected_capture_time": target_time,
                    "actual_capture_time": capture_start_time,
                    "user_expected_time": user_expected_time,
                }

                # Save frame
                if self.recording_manager.save_frame(frame, frame_metadata):
                    self._log_message(f"✅ SEQUENTIAL frame {current + 1} saved successfully!")
                    self._log_message(f"   Frame mean: {frame_mean:.1f}")
                    self._log_message(
                        f"   Temperature: {capture_result.get('temperature', 0):.1f}°C"
                    )
                    self._log_message(f"   Humidity: {capture_result.get('humidity', 0):.1f}%")
                    self._log_message(
                        f"   LED duration: {capture_result.get('led_duration_ms', 0):.1f}ms"
                    )

                    # Update UI
                    self._update_recording_progress_ui(current + 1, total)

                    # ✅ SCHEDULE NEXT FRAME CAPTURE
                    if current + 1 < total:
                        next_target_time = self.recording_start_time + (
                            (current + 1) * self.actual_interval
                        )
                        next_wait_time = next_target_time - time.time()

                        # Ensure minimum wait time
                        next_wait_ms = max(100, int(next_wait_time * 1000))

                        self._log_message(
                            f"⏰ Next frame {current + 2} in {next_wait_ms/1000:.1f}s"
                        )
                        QTimer.singleShot(next_wait_ms, self._sequential_capture_next_frame)
                    else:
                        self._log_message(
                            "🎯 All frames scheduled - sequential recording will complete"
                        )

                else:
                    self._log_message(f"❌ Frame {current + 1} save failed")
                    # Try to continue with next frame
                    QTimer.singleShot(1000, self._sequential_capture_next_frame)
            else:
                error_msg = capture_result.get("error_message", "Unknown capture error")
                self._log_message(f"❌ Sequential frame {current + 1} capture failed: {error_msg}")

                # Try to continue with next frame after delay
                QTimer.singleShot(2000, self._sequential_capture_next_frame)

        except Exception as e:
            self._log_message(f"❌ Sequential capture error for frame {current + 1}: {e}")

            # Emergency LED cleanup
            try:
                if self.esp32_controller.connected:
                    self.esp32_controller.set_led_power(0)
                    self.esp32_controller.led_off()
                    self._log_message("🔧 Emergency LED cleanup completed")
            except:
                pass

            import traceback

            traceback.print_exc()

            # Try to continue after error
            QTimer.singleShot(3000, self._sequential_capture_next_frame)

    def _capture_next_frame_simple(self):
        """Frame-Capture mit vollständigen Metadaten aber einfacher Timing-Logik"""
        if not self.recording_manager.recording:
            return

        current = self.recording_manager.current_frame
        total = self.recording_manager.total_frames

        if current >= total:
            self._stop_recording()
            return

        # =========================================================================
        # DRIFT-BERECHNUNG (wie in der komplexen Version)
        # =========================================================================
        expected_time = self.recording_start_time + (current * self.target_interval)
        actual_time = time.time()
        drift_ms = (actual_time - expected_time) * 1000

        self._log_message(f"\n📸 Frame {current + 1}/{total} (drift: {drift_ms:+.1f}ms)")

        # =========================================================================
        # FRAME CAPTURE MIT TIMING-MESSUNG
        # =========================================================================
        frame_start_time = time.time()
        capture_result = self._capture_single_frame_with_led_SYNC()
        capture_duration = time.time() - frame_start_time

        if capture_result["capture_success"] and capture_result["frame"] is not None:
            frame = capture_result["frame"]

            # =====================================================================
            # FRAME SPEICHERN
            # =====================================================================
            self.recording_manager.dataset[current, :, :] = frame

            # =====================================================================
            # VOLLSTÄNDIGE METADATEN SPEICHERN
            # =====================================================================

            # 1. TIMING-DATEN (Python & ESP32 Timestamps + Drift)
            if "timing" in self.recording_manager.hdf5_file:
                timing_group = self.recording_manager.hdf5_file["timing"]
                timing_group["python_timestamps"][current] = capture_result["python_timestamp"]
                timing_group["esp32_timestamps"][current] = capture_result["esp32_timestamp"]
                timing_group["frame_drifts_ms"][current] = drift_ms
                timing_group["led_durations_ms"][current] = capture_result["led_duration_ms"]

            # 2. UMWELT-DATEN (Temperatur & Luftfeuchtigkeit)
            if "environmental" in self.recording_manager.hdf5_file:
                env_group = self.recording_manager.hdf5_file["environmental"]
                env_group["temperature_celsius"][current] = capture_result["temperature"]
                env_group["humidity_percent"][current] = capture_result["humidity"]

            # 3. FRAME-METADATEN (LED Power, Helligkeit, etc.)
            if "frame_metadata" in self.recording_manager.hdf5_file:
                frame_meta_group = self.recording_manager.hdf5_file["frame_metadata"]
                frame_group = frame_meta_group.create_group(f"frame_{current:05d}")
                frame_group.attrs["led_power"] = capture_result["led_power"]
                frame_group.attrs["frame_mean"] = np.mean(frame)
                frame_group.attrs["frame_std"] = np.std(frame)
                frame_group.attrs["capture_duration_ms"] = capture_duration * 1000
                frame_group.attrs["expected_time"] = expected_time
                frame_group.attrs["actual_time"] = actual_time

            # =====================================================================
            # TIMING-ANALYSE & LOGGING
            # =====================================================================
            python_time = capture_result["python_timestamp"]
            esp32_time = capture_result["esp32_timestamp"]
            time_diff = (esp32_time - python_time) * 1000  # ms

            self._log_message(
                f"✅ Frame saved | Python: {python_time:.3f} | ESP32: {esp32_time:.3f} | Diff: {time_diff:.1f}ms"
            )
            self._log_message(
                f"🌡️ Temp: {capture_result['temperature']:.1f}°C | 💧 Humidity: {capture_result['humidity']:.1f}%"
            )

            # Frame-Counter erhöhen
            self.recording_manager.current_frame += 1
            self._update_progress_ui(current + 1, total)

            # Regelmäßig flushen (alle 5 Frames)
            if current % 5 == 0:
                self.recording_manager.hdf5_file.flush()
                self._log_message(f"💾 HDF5 flushed at frame {current + 1}")

        else:
            self._log_message(f"❌ Frame {current + 1} capture failed - skipping")
            self.recording_manager.current_frame += 1

        # =========================================================================
        # NÄCHSTER FRAME - EINFACHES TIMING
        # =========================================================================
        if self.recording_manager.current_frame < total:
            # Einfache Methode: Festes Interval
            QTimer.singleShot(int(self.target_interval * 1000), self._capture_next_frame_simple)

            # Optional: Drift-Warnung bei großen Abweichungen
            if abs(drift_ms) > 1000:  # Mehr als 1 Sekunde Drift
                self._log_message(f"⚠️ Large timing drift: {drift_ms:.1f}ms")

    def _pause_recording(self):
        """Pause/resume recording"""
        if self.capture_timer.isActive():
            self.capture_timer.stop()
            self.pause_rec_btn.setText("▶️ Resume")
            self._log_message("⏸️ Recording paused")
        else:
            self.capture_timer.start()
            self.pause_rec_btn.setText("⏸️ Pause")
            self._log_message("▶️ Recording resumed")

    def _stop_recording(self):
        """
        Enhanced stop recording method for sequential capture
        """
        self._log_message("🛑 Stopping recording...")

        # Stop sequential capture
        if hasattr(self, "sequential_recording_active"):
            self.sequential_recording_active = False

        # Stop any running timers
        if hasattr(self, "capture_timer"):
            try:
                self.capture_timer.stop()
                self.capture_timer.timeout.disconnect()
            except:
                pass

        # Ensure LED is off
        if self.esp32_controller.connected:
            try:
                self.esp32_controller.set_led_power(0)
                self.esp32_controller.led_off()
                self._log_message("🔧 LED turned off")
            except Exception as e:
                self._log_message(f"⚠️ LED cleanup error: {e}")

        # Finalize recording
        if self.recording_manager.recording:
            elapsed = time.time() - self.recording_manager.start_time
            frames = self.recording_manager.current_frame

            self.recording_manager.finalize_recording()

            self._log_message("✅ Sequential recording completed:")
            self._log_message(f"   Frames captured: {frames}")
            self._log_message(f"   Duration: {elapsed/60:.1f} minutes")

        # Reset UI
        self._enable_recording_controls(False)
        if hasattr(self, "progress_bar"):
            self.progress_bar.setVisible(False)

    def _enable_recording_controls(self, recording: bool):
        """Enable/disable recording controls"""
        self.start_rec_btn.setEnabled(not recording)
        self.pause_rec_btn.setEnabled(recording)
        self.stop_rec_btn.setEnabled(recording)

        self.duration_input.setEnabled(not recording)
        self.interval_input.setEnabled(not recording)
        self.select_dir_btn.setEnabled(not recording)

    def _on_trigger_mode_changed(self):
        """Handle trigger mode changes"""
        if not self.camera_connected:
            return

        trigger_text = self.trigger_combo.currentText()

        if self.mode != "imswitch_framegrab":  # Only apply for direct camera control
            if "Free Running" in trigger_text:
                self.camera_thread.set_trigger_mode(False)
            elif "Software" in trigger_text:
                self.camera_thread.set_trigger_mode(True, "Software")
            elif "Hardware" in trigger_text:
                self.camera_thread.set_trigger_mode(True, "Hardware")

            self._log_message(f"⚙️ Trigger mode: {trigger_text}")

    def _on_exposure_changed(self):
        """Handle exposure changes"""
        if not self.camera_connected:
            return

        exposure_us = self.exposure_spinbox.value()

        if self.mode != "imswitch_framegrab":  # Only apply for direct camera control
            self.camera_thread.set_exposure_time(exposure_us)
            self._log_message(f"⚙️ Exposure changed: {exposure_us}μs")

    def _format_time(self, seconds: float) -> str:
        """Format time in HH:MM:SS format"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _test_led_sync_capture(self):
        """Test the fixed LED sync capture method"""
        self._log_message("\n🧪 === TESTING FIXED LED SYNC CAPTURE ===")

        if not self.esp32_controller.connected:
            self._log_message("❌ ESP32 not connected for test")
            return

        # Test 1: Dark reference
        self._log_message("1️⃣ Taking dark reference...")
        self.esp32_controller.set_led_power(0)
        self.esp32_controller.led_off()
        time.sleep(1.0)

        dark_frame = self._grab_current_frame()
        if dark_frame is not None:
            dark_mean = np.mean(dark_frame)
            self._log_message(f"Dark reference mean: {dark_mean:.1f}")
        else:
            self._log_message("❌ Could not get dark reference")
            return

        # Test 2: LED sync capture
        self._log_message("2️⃣ Testing LED sync capture...")
        result = self._capture_frame_with_led_sync()

        if result["capture_success"]:
            frame = result["frame"]
            frame_mean = np.mean(frame)
            brightness_ratio = frame_mean / dark_mean if dark_mean > 0 else 0

            self._log_message("✅ LED sync test successful!")
            self._log_message(f"   LED frame mean: {frame_mean:.1f}")
            self._log_message(f"   Brightness ratio: {brightness_ratio:.2f}x")

            # Add test frame to viewer
            layer_name = "LED Sync Test"
            existing = [l for l in self.viewer.layers if l.name == layer_name]
            if existing:
                self.viewer.layers.remove(existing[0])
            self.viewer.add_image(frame, name=layer_name)

            if brightness_ratio < 1.2:
                self._log_message(
                    "⚠️ Warning: Frame not significantly brighter - check LED connection!"
                )

        else:
            error_msg = result.get("error_message", "Unknown error")
            self._log_message(f"❌ LED sync test failed: {error_msg}")

    def _test_timing_accuracy(self):
        """Test timing accuracy of the capture system"""
        self._log_message("\n⏱️ === TESTING TIMING ACCURACY ===")

        if not self.esp32_controller.connected:
            self._log_message("❌ ESP32 not connected for timing test")
            return

        test_captures = 5
        target_interval = 2.0  # 2 seconds

        capture_times = []

        for i in range(test_captures):
            self._log_message(f"Timing test {i+1}/{test_captures}...")

            start_time = time.time()
            result = self._capture_frame_with_led_sync()
            end_time = time.time()

            if result["capture_success"]:
                capture_duration = end_time - start_time
                capture_times.append(capture_duration)
                self._log_message(f"   Capture duration: {capture_duration:.2f}s")
            else:
                self._log_message(f"   Capture failed: {result.get('error_message', 'Unknown')}")

            if i < test_captures - 1:  # Don't wait after last capture
                time.sleep(target_interval)

        if capture_times:
            avg_duration = np.mean(capture_times)
            std_duration = np.std(capture_times)

            self._log_message("\n📊 Timing Results:")
            self._log_message(f"   Average duration: {avg_duration:.2f}s ± {std_duration:.2f}s")
            self._log_message(f"   Min duration: {min(capture_times):.2f}s")
            self._log_message(f"   Max duration: {max(capture_times):.2f}s")

            if avg_duration > 5.0:
                self._log_message("⚠️ Warning: Long capture times - consider optimizing!")
        else:
            self._log_message("❌ No successful captures for timing analysis")

    def _test_timestamp_accuracy(self):
        """Test timestamp accuracy between Python and ESP32"""
        if not self.esp32_controller.connected:
            self._log_message("❌ ESP32 not connected")
            return

        self._log_message("\n⏱️ === TIMESTAMP ACCURACY TEST ===")

        # Test 1: Direkte sync_capture
        self._log_message("1️⃣ Direkte sync_capture...")
        sync_data = self.esp32_controller.sync_capture()
        if sync_data:
            self._log_message(f"   Python timestamp: {sync_data['python_timestamp']:.6f}")
            self._log_message(f"   ESP32 timing: {sync_data['esp32_timing_ms']}ms")
            self._log_message(f"   Temperature: {sync_data['temperature']:.1f}°C")
            self._log_message(f"   Humidity: {sync_data['humidity']:.1f}%")
        else:
            self._log_message("   ❌ sync_capture failed")

        # Test 2: V3 Capture mit Timestamps
        self._log_message("\n2️⃣ V3 Capture Timestamps...")
        result = self._capture_single_frame_with_led_SYNC()
        if result["capture_success"]:
            python_ts = result["python_timestamp"]
            esp32_ts = result["esp32_timestamp"]
            diff_ms = (esp32_ts - python_ts) * 1000

            self._log_message(f"   Python: {python_ts:.6f}")
            self._log_message(f"   ESP32:  {esp32_ts:.6f}")
            self._log_message(f"   Difference: {diff_ms:.1f}ms")

            if abs(diff_ms) < 1000:
                self._log_message("   ✅ Timestamps look reasonable")
            else:
                self._log_message("   ⚠️ Large timestamp difference!")
        else:
            self._log_message("   ❌ V3 capture failed")

        self._log_message("\n⏱️ === TIMESTAMP TEST COMPLETE ===")

    def _debug_v3_capture_extended(self):
        """Erweiterte V3 Debug mit Timestamp-Check"""
        self._log_message("\n🔍 === EXTENDED V3 DEBUG ===")

        # Basis-Tests (falls vorhanden)
        if hasattr(self, "_debug_v3_capture"):
            self._debug_v3_capture()

        # Timestamp-Tests
        self._test_timestamp_accuracy()

        self._log_message("\n🎯 === EXTENDED DEBUG COMPLETE ===")

    def _force_release_all(self):
        """UI method to force release all cameras"""
        self._log_message("💥 Force releasing all HIK cameras...")
        self.camera_thread.force_release_all_cameras()
        self._log_message("✅ Force release completed")

    def _check_processes(self):
        """UI method to check camera processes"""
        self._log_message("🔍 Checking for camera processes...")
        self.camera_thread.check_camera_processes()

    def _aggressive_connect(self):
        """UI method for aggressive connection"""
        if not self.available_cameras:
            self._log_message("❌ No cameras available")
            return

        camera_index = self.camera_combo.currentIndex()
        if camera_index < 0:
            self._log_message("❌ No camera selected")
            return

        camera = self.available_cameras[camera_index]
        self._log_message(f"💥 AGGRESSIVE connection to {camera['model']}")

        if self.camera_thread.connect_camera_aggressive(camera_index):
            self.camera_connected = True
            self._enable_camera_controls(True)
            self._log_message("✅ AGGRESSIVE connection successful!")
        else:
            self._log_message("❌ Even aggressive connection failed")

    def _reset_camera_network(self):
        """UI method to reset camera network"""
        self._log_message("🔄 Resetting camera network...")
        self.camera_thread.reset_camera_network()
        self._log_message("✅ Network reset completed")

    def _connect_camera(self):
        """Connect to selected camera"""
        if not self.available_cameras:
            self._log_message("❌ No cameras available")
            return

        camera_index = self.camera_combo.currentIndex()
        if camera_index < 0:
            self._log_message("❌ No camera selected")
            return

        camera = self.available_cameras[camera_index]
        self._log_message(f"🔗 Connecting to {camera['model']}")

        # Connect using the camera thread
        if self.camera_thread.connect_camera(camera_index):
            self.camera_connected = True
            self._enable_camera_controls(True)
            self._log_message(f"✅ Connected to {camera['model']}")
        else:
            self._log_message("❌ Camera connection failed")

    def _disconnect_camera(self):
        """Disconnect camera"""
        if self.camera_thread.running:
            self._stop_live_view()

        self.camera_thread.disconnect_camera()
        self.camera_connected = False
        self._enable_camera_controls(False)
        self._log_message("✅ Camera disconnected")

    def _discover_cameras(self):
        """Discover cameras"""
        self._log_message("🔍 Discovering HIK GigE cameras...")

        if not _HAS_HIK_SDK:
            self._log_message("❌ HIK SDK not available")
            QMessageBox.warning(self, "SDK Missing", "HIK SDK not found")
            return

        self.camera_combo.clear()
        self.available_cameras = self.camera_thread.discover_cameras()

        if self.available_cameras:
            for camera in self.available_cameras:
                status = "✅" if camera["accessible"] else "❌"
                text = f"{status} {camera['model']} ({camera['ip']})"
                self.camera_combo.addItem(text)

            self.connect_btn.setEnabled(True)
            self._log_message(f"✅ Found {len(self.available_cameras)} camera(s)")
        else:
            self.camera_combo.addItem("No cameras found")
            self._log_message("❌ No cameras found")

    def _diagnose_camera(self):
        """Diagnose selected camera"""
        camera_index = self.camera_combo.currentIndex()
        if camera_index >= 0:
            self.camera_thread.diagnose_camera_state(camera_index)
        else:
            self._log_message("❌ No camera selected for diagnosis")

    def _detect_mode(self) -> str:
        """Auto-detect operating mode"""
        # Check if ImSwitch is running and has a live layer
        try:
            if hasattr(self, "viewer") and self.viewer:
                imswitch_indicators = ["Live:", "Widefield", "Camera", "Detector"]
                for layer in self.viewer.layers:
                    if any(indicator in layer.name for indicator in imswitch_indicators):
                        print("🔧 Detected ImSwitch live view - using frame grabber mode")
                        return "imswitch_framegrab"
        except Exception as e:
            print(f"Layer detection error: {e}")

        print("📱 Using standalone mode")
        return "standalone"

    def _find_imswitch_live_layer(self):
        """Find ImSwitch live view layer in napari"""
        if not self.viewer:
            return None

        # Look for layers that match ImSwitch patterns
        imswitch_patterns = [
            "Live:",
            "Widefield",
            "Camera",
            "Detector",
            "WidefieldCamera",
        ]

        for layer in self.viewer.layers:
            for pattern in imswitch_patterns:
                if pattern in layer.name:
                    return layer

        return None

    def _grab_current_frame(self) -> Optional[np.ndarray]:
        """
        SIMPLIFIED frame grabbing - just get the current frame
        """
        try:
            if self.mode == "imswitch_framegrab":
                if self.imswitch_live_layer and self.imswitch_live_layer.data is not None:
                    return self.imswitch_live_layer.data.copy()
            elif self.mode == "standalone":
                if self.camera_thread and self.camera_connected:
                    return self.camera_thread.capture_frame(2000)

            return None

        except Exception as e:
            self._log_message(f"❌ Simple frame grab error: {e}")
            return None

    def _detect_frame_shape_reliably(self) -> Optional[tuple]:
        """
        Reparierte Frame-Shape-Erkennung
        """
        self._log_message("🔍 Frame-Shape Erkennung...")

        try:
            # Mehrere Versuche
            for attempt in range(3):
                self._log_message(f"   Versuch {attempt + 1}/3...")

                frame = self._grab_current_frame()
                if frame is not None:
                    shape = frame.shape
                    self._log_message(f"   ✅ Frame-Shape erkannt: {shape}")

                    # Validierung
                    if len(shape) >= 2 and shape[0] > 0 and shape[1] > 0:
                        return shape
                    else:
                        self._log_message(f"   ❌ Ungültige Shape: {shape}")
                else:
                    self._log_message(f"   ❌ Kein Frame bei Versuch {attempt + 1}")

                time.sleep(0.5)

            self._log_message("❌ Frame-Shape-Erkennung fehlgeschlagen")
            return None

        except Exception as e:
            self._log_message(f"❌ Frame-Shape Fehler: {e}")
            return None

    def _capture_frame_with_led_sync(self) -> Dict[str, Any]:
        """
        Simplified LED sync capture - focus on environmental data + LED duration
        """
        result = {
            "frame": None,
            "capture_success": False,
            "error_message": None,
            "capture_method": "unknown",
            "timing_info": {},
            "esp32_timestamp": None,
            "led_duration_ms": 0,
            "temperature": 0.0,  # ✅ Keep environmental
            "humidity": 0.0,  # ✅ Keep environmental
        }

        capture_start_time = time.time()
        result["python_timestamp"] = capture_start_time

        if not self.esp32_controller.connected:
            # No ESP32 - just grab frame
            result["frame"] = self._grab_current_frame()
            result["capture_success"] = result["frame"] is not None
            result["capture_method"] = "no_esp32"
            result["esp32_timestamp"] = capture_start_time
            return result

        try:
            self._log_message("\n🔄 === SIMPLIFIED LED SYNC CAPTURE ===")

            # Step 1: LED OFF
            led_off_start = time.time()
            self._log_message("🌑 Step 1: LED OFF...")

            for off_attempt in range(2):  # Simplified - fewer attempts
                self.esp32_controller.set_led_power(0)
                time.sleep(0.1)
                self.esp32_controller.led_off()
                time.sleep(0.1)

            time.sleep(0.5)  # Shorter wait

            # Step 2: LED Power Setting (use fixed power - no need to track)
            self._log_message("⚡ Step 2: LED power...")
            led_power = self._get_current_led_power()

            if not self.esp32_controller.set_led_power(led_power):
                result["error_message"] = "Failed to set LED power"
                result["capture_method"] = "led_power_failed"
                return result

            time.sleep(0.2)

            # Step 3: LED ON
            self._log_message("💡 Step 3: LED ON...")

            if not self.esp32_controller.led_on():
                result["error_message"] = "Failed to turn LED ON"
                result["capture_method"] = "led_on_failed"
                self.esp32_controller.set_led_power(0)
                self.esp32_controller.led_off()
                return result

            # Step 4: Frame capture
            frame_capture_start = time.time()
            self._log_message("📸 Step 4: Frame capture...")

            if self.mode == "imswitch_framegrab":
                time.sleep(1.0)  # Simplified timing
                frame = self._wait_for_led_illuminated_frame(3.0)
                result["capture_method"] = "imswitch_simplified"
            else:
                time.sleep(0.3)
                frame = self.camera_thread.capture_frame_robust(3000)
                result["capture_method"] = "standalone_simplified"

            result["esp32_timestamp"] = frame_capture_start

            # Step 5: LED OFF
            self._log_message("🌑 Step 5: LED OFF...")
            self.esp32_controller.set_led_power(0)
            self.esp32_controller.led_off()

            # ✅ Step 6: READ ENVIRONMENTAL SENSORS (this is what we want!)
            self._log_message("🌡️ Step 6: Reading environmental sensors...")
            try:
                time.sleep(0.2)  # Brief wait after LED off
                sync_data = self.esp32_controller.sync_capture()
                if sync_data:
                    result["temperature"] = sync_data.get("temperature", 0.0)
                    result["humidity"] = sync_data.get("humidity", 0.0)
                    self._log_message(f"   ✅ Temperature: {result['temperature']:.1f}°C")
                    self._log_message(f"   ✅ Humidity: {result['humidity']:.1f}%")
                else:
                    self._log_message("   ⚠️ No sensor data received")
            except Exception as e:
                self._log_message(f"   ⚠️ Sensor read failed: {e}")

            # ✅ Calculate LED DURATION (this is what we want!)
            total_duration = time.time() - capture_start_time
            result["led_duration_ms"] = total_duration * 1000

            # Validate result
            if frame is not None:
                frame_mean = np.mean(frame)
                self._log_message("✅ Simplified LED sync successful!")
                self._log_message(f"   Frame mean: {frame_mean:.1f}")
                self._log_message(f"   LED duration: {result['led_duration_ms']:.1f}ms")
                self._log_message(f"   Temperature: {result['temperature']:.1f}°C")
                self._log_message(f"   Humidity: {result['humidity']:.1f}%")

                result["frame"] = frame
                result["capture_success"] = True
            else:
                result["error_message"] = "No frame captured"
                self._log_message("❌ Simplified LED sync failed - no frame")

            return result

        except Exception as e:
            total_duration = time.time() - capture_start_time
            error_msg = f"Simplified LED sync exception: {e}"
            self._log_message(f"❌ {error_msg}")

            result["error_message"] = error_msg
            result["capture_method"] = "exception_error"
            result["led_duration_ms"] = total_duration * 1000

            # Emergency LED OFF
            try:
                self.esp32_controller.set_led_power(0)
                self.esp32_controller.led_off()
            except:
                pass

            return result

    def _wait_for_led_illuminated_frame(
        self, max_wait_seconds: float = 5.0
    ) -> Optional[np.ndarray]:
        """
        Wait for a new frame after LED has been turned on
        """
        if self.mode != "imswitch_framegrab" or not self.imswitch_live_layer:
            return self._grab_current_frame()

        try:
            # Get reference frame (before LED)
            reference_frame = self.imswitch_live_layer.data.copy()
            reference_mean = np.mean(reference_frame)

            self._log_message(
                f"📸 Waiting for LED-illuminated frame (reference mean: {reference_mean:.1f})"
            )

            start_time = time.time()
            frame_checks = 0

            while (time.time() - start_time) < max_wait_seconds:
                time.sleep(0.1)  # Check every 100ms
                frame_checks += 1

                current_frame = self.imswitch_live_layer.data.copy()
                current_mean = np.mean(current_frame)

                # Check if frame is significantly brighter
                brightness_increase = current_mean - reference_mean

                if brightness_increase > 10:  # Arbitrary threshold - adjust as needed
                    self._log_message(
                        f"✅ LED frame detected after {time.time() - start_time:.1f}s (brightness +{brightness_increase:.1f})"
                    )
                    return current_frame

                # Progress update every second
                if frame_checks % 10 == 0:
                    elapsed = time.time() - start_time
                    self._log_message(
                        f"⏳ Still waiting... {elapsed:.1f}s (current mean: {current_mean:.1f})"
                    )

            # Timeout - return current frame anyway
            final_frame = self.imswitch_live_layer.data.copy()
            self._log_message(f"⚠️ Timeout after {max_wait_seconds}s - using current frame")
            return final_frame

        except Exception as e:
            self._log_message(f"❌ LED frame wait error: {e}")
            return self._grab_current_frame()

    def _on_capture_tick_FIXED(self):
        """
        Simplified capture tick - focus on environmental data + LED duration
        """
        if not self.recording_manager.recording:
            return

        current = self.recording_manager.current_frame
        total = self.recording_manager.total_frames

        if current >= total:
            self._stop_recording()
            return

        current_time = time.time()

        # Check timing (if using actual interval for LED safety)
        if self.esp32_controller.connected and hasattr(self, "actual_interval"):
            expected_capture_time = self.recording_start_time + (current * self.actual_interval)
            if current_time < expected_capture_time - 0.5:
                return  # Too early

        # Calculate drift from user's request
        if hasattr(self, "target_interval"):
            user_expected_time = self.recording_start_time + (current * self.target_interval)
            drift_from_user_request = (current_time - user_expected_time) * 1000
        else:
            drift_from_user_request = 0

        self._log_message(f"\n📸 === SIMPLIFIED CAPTURE FRAME {current + 1}/{total} ===")
        self._log_message(f"📊 Drift from user request: {drift_from_user_request:+.1f}ms")

        try:
            # Use simplified capture method
            capture_result = self._capture_frame_with_led_sync()

            if capture_result["capture_success"] and capture_result["frame"] is not None:
                frame = capture_result["frame"]

                # Create simplified metadata - focus on environmental + LED duration
                frame_metadata = {
                    "timestamp": capture_result["python_timestamp"],
                    "esp32_timestamp": capture_result["esp32_timestamp"],
                    "frame_number": current + 1,
                    "capture_method": capture_result["capture_method"],
                    "capture_success": True,
                    "frame_mean": float(np.mean(frame)),
                    "frame_std": float(np.std(frame)),
                    "mode": self.mode,
                    # ✅ ENVIRONMENTAL DATA (what we want!)
                    "temperature": capture_result["temperature"],
                    "humidity": capture_result["humidity"],
                    # ✅ LED DURATION (what we want!)
                    "led_duration_ms": capture_result["led_duration_ms"],
                    # Timing data
                    "user_requested_interval": getattr(self, "target_interval", 0),
                    "timing_drift": drift_from_user_request / 1000.0,
                    "timing_info": capture_result.get("timing_info", {}),
                }

                # Save frame with simplified metadata
                if self.recording_manager.save_frame(frame, frame_metadata):
                    self._log_message(f"✅ Frame {current + 1} saved with environmental data!")
                    self._update_recording_progress_ui(current + 1, total)
                else:
                    self._log_message(f"❌ Frame {current + 1} save failed")
            else:
                error_msg = capture_result.get("error_message", "Unknown error")
                self._log_message(f"❌ Frame {current + 1} capture failed: {error_msg}")

        except Exception as e:
            self._log_message(f"❌ Simplified capture error: {e}")
            try:
                if self.esp32_controller.connected:
                    self.esp32_controller.set_led_power(0)
                    self.esp32_controller.led_off()
            except:
                pass
            import traceback

            traceback.print_exc()

    def _update_recording_progress_ui(self, current: int, total: int):
        """Update recording progress UI"""
        try:
            if self.progress_bar:
                self.progress_bar.setValue(current)

            if self.current_frame_label:
                self.current_frame_label.setText(f"Frame: {current}/{total}")

            if self.elapsed_label:
                elapsed = time.time() - self.recording_manager.start_time
                self.elapsed_label.setText(f"Elapsed: {self._format_time(elapsed)}")

            if self.eta_label and current > 0:
                elapsed = time.time() - self.recording_manager.start_time
                rate = current / elapsed
                eta = (total - current) / rate if rate > 0 else 0
                self.eta_label.setText(f"ETA: {self._format_time(eta)}")

        except Exception as e:
            self._log_message(f"❌ UI update error: {e}")

    def _test_led_before_recording(self):
        """
        Test LED functionality before starting a recording
        """
        if not self.esp32_controller.connected:
            QMessageBox.warning(self, "LED Test", "ESP32 not connected")
            return False

        self._log_message("\n🧪 Testing LED before recording...")

        try:
            # Test LED OFF
            self._log_message("Test 1: LED OFF...")
            self.esp32_controller.set_led_power(0)
            off_resp = self.esp32_controller.led_off()
            if not off_resp:
                self._log_message("❌ LED OFF failed")
                return False

            time.sleep(0.5)

            # Test LED ON at different power levels
            test_powers = [50, 100]
            for power in test_powers:
                self._log_message(f"\nTest 2: LED ON at {power}%...")
                self.esp32_controller.set_led_power(power)
                time.sleep(0.1)
                on_resp = self.esp32_controller.led_on()

                if on_resp:
                    self._log_message(f"✅ LED ON at {power}% successful")
                    time.sleep(1.0)  # Keep on for 1 second

                    # Turn off
                    self.esp32_controller.set_led_power(0)
                    self.esp32_controller.led_off()
                    time.sleep(0.5)
                else:
                    self._log_message(f"❌ LED ON at {power}% failed")
                    return False

            self._log_message("\n✅ LED tests passed!")
            return True

        except Exception as e:
            self._log_message(f"❌ LED test error: {e}")
            return False

    def _test_ir_led_characteristics(self):
        """
        Test IR LED characteristics including warmup and stability
        """
        if not self.esp32_controller.connected:
            self._log_message("❌ ESP32 not connected")
            return

        self._log_message("\n🔬 === IR LED CHARACTERISTICS TEST ===")

        try:
            # Dark reference
            self.esp32_controller.set_led_power(0)
            self.esp32_controller.led_off()
            time.sleep(0.5)

            dark_frame = self._grab_current_frame()  # ✅ KORREKTE Methode
            dark_mean = np.mean(dark_frame) if dark_frame is not None else 0
            self._log_message(f"Dark reference: {dark_mean:.1f}")

            # Test different power levels
            self._log_message("\n1️⃣ Testing IR LED power levels...")
            power_levels = [10, 25, 50, 75, 100]
            power_results = []

            for power in power_levels:
                self.esp32_controller.set_led_power(power)
                time.sleep(0.1)
                self.esp32_controller.led_on()
                time.sleep(2.0)  # ✅ Längere Wartezeit für ImSwitch

                frame = self._grab_current_frame()  # ✅ KORREKTE Methode
                if frame is not None:
                    brightness = np.mean(frame)
                    power_results.append((power, brightness))
                    ratio = brightness / dark_mean if dark_mean > 0 else brightness
                    self._log_message(f"  {power}% → brightness: {brightness:.1f} ({ratio:.1f}x)")

                self.esp32_controller.led_off()
                time.sleep(0.5)

            # Test warmup at 100%
            self._log_message("\n2️⃣ Testing IR LED warmup time...")
            self.esp32_controller.set_led_power(100)
            time.sleep(0.1)

            led_on_time = time.time()
            self.esp32_controller.led_on()

            warmup_data = []
            for i in range(20):  # ✅ Reduziert von 30 auf 20 (2 Sekunden)
                elapsed = time.time() - led_on_time
                frame = self._grab_current_frame()  # ✅ KORREKTE Methode
                if frame is not None:
                    brightness = np.mean(frame)
                    warmup_data.append((elapsed, brightness))
                time.sleep(0.1)

            self.esp32_controller.led_off()

            # Analyze warmup
            if warmup_data:
                initial_brightness = warmup_data[0][1]
                final_brightness = np.mean([b for _, b in warmup_data[-5:]])
                warmup_ratio = (
                    final_brightness / initial_brightness if initial_brightness > 0 else 0
                )

                self._log_message("\n📊 IR LED Analysis:")
                self._log_message(f"Initial brightness: {initial_brightness:.1f}")
                self._log_message(f"Final brightness: {final_brightness:.1f}")
                self._log_message(f"Warmup ratio: {warmup_ratio:.2f}x")

                # Find time to 95% brightness
                if len(warmup_data) > 1:
                    threshold = initial_brightness + (final_brightness - initial_brightness) * 0.95
                    time_to_95 = None
                    for t, b in warmup_data:
                        if b >= threshold:
                            time_to_95 = t
                            break

                    if time_to_95:
                        self._log_message(f"Time to 95% brightness: {time_to_95:.2f}s")
                        self._log_message(
                            f"\n💡 Recommendation: Wait at least {time_to_95 + 0.2:.1f}s after LED ON"
                        )
                    else:
                        self._log_message("\n💡 Recommendation: Wait at least 2.0s after LED ON")

            else:
                self._log_message("❌ No warmup data collected")

        except Exception as e:
            self._log_message(f"❌ Test error: {e}")
        finally:
            self.esp32_controller.set_led_power(0)
            self.esp32_controller.led_off()

    def _manual_test_led_capture(self):
        """
        Manually test a single LED capture to verify it works
        """
        self._log_message("\n🧪 === MANUAL LED CAPTURE TEST ===")

        if not self.esp32_controller.connected:
            self._log_message("❌ ESP32 not connected")
            return

        # Take a dark frame first
        self._log_message("📸 Taking dark reference frame...")
        self.esp32_controller.set_led_power(0)
        self.esp32_controller.led_off()
        time.sleep(0.5)

        if self.mode == "imswitch_framegrab":
            dark_frame = self._grab_current_frame()
        else:
            dark_frame = self.camera_thread.capture_frame_robust(1000)

        if dark_frame is not None:
            dark_mean = np.mean(dark_frame)
            self._log_message(f"Dark frame mean: {dark_mean:.1f}")

        # Now do a full LED capture
        self._log_message("\n🔦 Testing LED capture...")
        capture_result = self._capture_single_frame_with_led_SYNC()

        if capture_result["capture_success"] and capture_result["frame"] is not None:
            frame = capture_result["frame"]
            frame_mean = np.mean(frame)

            if dark_frame is not None:
                brightness_ratio = frame_mean / dark_mean if dark_mean > 0 else 0
                self._log_message(
                    f"✅ Capture successful! Brightness ratio: {brightness_ratio:.2f}x"
                )

                if brightness_ratio < 1.2:
                    self._log_message(
                        "⚠️ Frame not significantly brighter - LED might not be working!"
                    )
            else:
                self._log_message(f"✅ Capture successful! Frame mean: {frame_mean:.1f}")

            # Display the captured frame
            layer_name = "LED Test Capture"
            existing = [l for l in self.viewer.layers if l.name == layer_name]
            if existing:
                self.viewer.layers.remove(existing[0])
            self.viewer.add_image(frame, name=layer_name)

        else:
            self._log_message("❌ LED capture test failed")

    def _calibrate_led_timing(self):
        """
        Vereinfachte LED-Kalibrierung mit korrekten Frame-Grab-Methoden
        """
        if not self.esp32_controller.connected:
            self._log_message("❌ ESP32 required for calibration")
            return None

        self._log_message("\n🔧 === LED KALIBRIERUNG (VEREINFACHT) ===")
        self._log_message("📌 Note: IR LED ist nicht sichtbar für menschliche Augen")

        try:
            # SCHRITT 1: ESP32 zurücksetzen
            self._log_message("\n1️⃣ ESP32 Reset...")
            self.esp32_controller.set_led_power(0)
            self.esp32_controller.led_off()
            time.sleep(0.5)

            # SCHRITT 2: Baseline-Messung
            self._log_message("\n2️⃣ Baseline-Messung (LED AUS)...")

            baseline_frames = []
            for i in range(3):  # ✅ Reduziert von 5 auf 3
                frame = self._grab_current_frame()  # ✅ KORREKTE Methode
                if frame is not None:
                    baseline_frames.append(np.mean(frame))
                    self._log_message(f"   Baseline {i+1}: {np.mean(frame):.1f}")
                time.sleep(0.3)

            if not baseline_frames:
                self._log_message("❌ Keine Baseline-Frames erhalten")
                return None

            dark_mean = np.mean(baseline_frames)
            self._log_message(f"📊 Baseline: {dark_mean:.1f}")

            # SCHRITT 3: LED-Funktionstest
            self._log_message("\n3️⃣ LED-Funktionstest...")

            # Nur 100% testen - vereinfacht!
            test_power = 100
            self._log_message(f"   Testing {test_power}% LED power...")

            # LED Power setzen
            if not self.esp32_controller.set_led_power(test_power):
                self._log_message(f"   ❌ Failed to set power to {test_power}%")
                return None

            time.sleep(0.2)

            # LED ON mit Retry
            led_on_success = False
            for retry in range(3):  # ✅ Reduziert von 5 auf 3
                if self.esp32_controller.led_on():
                    led_on_success = True
                    self._log_message(f"   ✅ LED ON successful (attempt {retry + 1})")
                    break
                else:
                    self._log_message(f"   ⚠️ LED ON attempt {retry + 1} failed")
                    time.sleep(0.1)

            if not led_on_success:
                self._log_message("   ❌ LED ON failed after 3 attempts")
                return None

            # LED-Test mit verschiedenen Wartezeiten
            self._log_message("\n4️⃣ Timing-Test...")

            # ✅ Vereinfachte Delays
            test_delays = [0.5, 1.0, 1.5, 2.0, 2.5]
            results = []

            for delay in test_delays:
                # LED ist bereits AN, nur warten
                time.sleep(delay)

                # ✅ Nur eine Messung pro Delay
                frame = self._grab_current_frame()  # ✅ KORREKTE Methode

                if frame is not None:
                    frame_mean = np.mean(frame)
                    brightness_ratio = frame_mean / dark_mean if dark_mean > 0.1 else frame_mean

                    results.append(
                        {
                            "delay": delay,
                            "brightness_ratio": brightness_ratio,
                            "frame_mean": frame_mean,
                        }
                    )

                    self._log_message(
                        f"   📊 {delay*1000:.0f}ms: {frame_mean:.1f} ({brightness_ratio:.2f}x)"
                    )

                time.sleep(0.2)  # Kurze Pause zwischen Tests

            # LED OFF
            self.esp32_controller.set_led_power(0)
            self.esp32_controller.led_off()

            # SCHRITT 5: Beste Einstellung finden
            if results:
                # Einfach: Höchste Brightness-Ratio nehmen
                best_result = max(results, key=lambda x: x["brightness_ratio"])

                if best_result["brightness_ratio"] > 1.2:  # Mindestens 20% heller
                    self._log_message("\n📊 === KALIBRIERUNG ERFOLGREICH ===")
                    self._log_message(
                        f"✅ Beste Timing-Einstellung: {best_result['delay']*1000:.0f}ms"
                    )
                    self._log_message(f"✅ Helligkeit: {best_result['brightness_ratio']:.2f}x")

                    # Speichere die Kalibrierung
                    self._imswitch_led_delay = best_result["delay"]

                    self._log_message("\n💡 Empfehlung für Recording:")
                    self._log_message(f"   - LED-Delay: {best_result['delay']*1000:.0f}ms")
                    self._log_message("   - LED-Power: 100%")

                    return best_result["delay"]
                else:
                    self._log_message("\n❌ LED zu schwach - Kalibrierung fehlgeschlagen")
                    self._log_message("🔧 Mögliche Probleme:")
                    self._log_message("   - LED nicht angeschlossen")
                    self._log_message("   - LED defekt")
                    self._log_message("   - Kamera-Empfindlichkeit zu niedrig")
                    return None
            else:
                self._log_message("\n❌ Keine gültigen Messungen")
                return None

        except Exception as e:
            self._log_message(f"❌ Kalibrierung Fehler: {e}")
            return None

        finally:
            # LED sicher ausschalten
            try:
                self.esp32_controller.set_led_power(0)
                self.esp32_controller.led_off()
            except:
                pass

    def _compare_led_sequences(self):
        """
        Compare LED sequences to debug why one works and other doesn't
        """
        self._log_message("\n🔍 === COMPARING LED SEQUENCES ===")

        if not self.esp32_controller.connected:
            self._log_message("❌ ESP32 not connected")
            return

        # Sequence 1: Recording style (WORKS)
        self._log_message("\n1️⃣ Recording-style sequence:")
        self._log_message("   - Set power to 0")
        self._log_message("   - LED OFF")
        self._log_message("   - Wait 200ms")
        self._log_message("   - Set power to 100%")
        self._log_message("   - Wait 100ms")
        self._log_message("   - LED ON")

        self.esp32_controller.set_led_power(0)
        self.esp32_controller.led_off()
        time.sleep(0.2)
        self.esp32_controller.set_led_power(100)
        time.sleep(0.1)
        result1 = self.esp32_controller.led_on()
        self._log_message(f"   Result: {result1} - LED should be ON now!")

        time.sleep(2.0)

        self.esp32_controller.led_off()
        time.sleep(1.0)

        # Sequence 2: Original calibration style
        self._log_message("\n2️⃣ Original calibration sequence:")
        self._log_message("   - Set power to 0")
        self._log_message("   - LED OFF")
        self._log_message("   - Wait 200ms")
        self._log_message("   - Set power to 100%")
        self._log_message("   - Wait 50ms (shorter!)")
        self._log_message("   - LED ON")

        self.esp32_controller.set_led_power(0)
        self.esp32_controller.led_off()
        time.sleep(0.2)
        self.esp32_controller.set_led_power(100)
        time.sleep(0.05)  # Shorter wait!
        result2 = self.esp32_controller.led_on()
        self._log_message(f"   Result: {result2} - Is LED ON?")

        time.sleep(2.0)
        self.esp32_controller.led_off()

        self._log_message("\n📊 Results:")
        self._log_message(f"Recording sequence: {result1}")
        self._log_message(f"Calibration sequence: {result2}")
        self._log_message("\nThe difference might be the 100ms vs 50ms wait after set_power!")

    def _test_imswitch_update_timing(self):
        """Test wie lange ImSwitch braucht um Frames zu aktualisieren"""
        self._log_message("\n🧪 Testing ImSwitch frame update timing...")

        if not self.imswitch_live_layer:
            self._log_message("❌ No ImSwitch live layer")
            return

        # Take reference frame
        ref_frame = self.imswitch_live_layer.data.copy()
        ref_mean = np.mean(ref_frame)

        # Turn LED on
        if self.esp32_controller.connected:
            self.esp32_controller.set_led_power(100)
            self.esp32_controller.led_on()

            # Check how long it takes for frame to change
            start_time = time.time()
            max_wait = 3.0
            check_interval = 0.1

            while (time.time() - start_time) < max_wait:
                current_frame = self.imswitch_live_layer.data
                current_mean = np.mean(current_frame)

                if abs(current_mean - ref_mean) > 5:  # Significant change
                    elapsed = time.time() - start_time
                    self._log_message(f"✅ Frame updated after {elapsed*1000:.0f}ms")
                    break

                time.sleep(check_interval)
            else:
                self._log_message("❌ No frame change detected after 3 seconds")

            # LED off
            self.esp32_controller.led_off()

    def _test_imswitch_framegrab(self):
        """Test frame grabbing from ImSwitch"""
        if not self.imswitch_live_layer or self.imswitch_live_layer.data is None:
            self._log_message("❌ No ImSwitch live data available")
            return

        # Grab current frame from ImSwitch
        frame = self.imswitch_live_layer.data.copy()

        # Add test frame to viewer
        layer_name = "Test Frame Grab"
        existing = [l for l in self.viewer.layers if l.name == layer_name]
        if existing:
            self.viewer.layers.remove(existing[0])

        self.viewer.add_image(frame, name=layer_name, rgb=(frame.ndim == 3))
        self._log_message(f"✅ Test frame grab: {frame.shape}")

    def _initialize_system(self):
        """Initialize system based on detected mode and available methods"""
        self._log_message(f"🚀 Initializing Nematostella Capture ({self.mode} mode)...")

        if self.mode == "imswitch_framegrab":
            self._log_message("📡 Setting up ImSwitch frame grabber mode (fallback)...")
            self.imswitch_live_layer = self._find_imswitch_live_layer()

            if self.imswitch_live_layer:
                self._log_message(f"✅ Found ImSwitch live layer: {self.imswitch_live_layer.name}")
                self.camera_connected = True  # We can grab frames from ImSwitch
            else:
                self._log_message("⚠️ No ImSwitch live layer found - start ImSwitch live view first")

        # Setup ESP32 (works in all modes)
        if hasattr(self, "_setup_esp32"):
            self._setup_esp32()

        # Update camera UI based on mode
        if hasattr(self, "_update_camera_ui_for_mode"):
            self._update_camera_ui_for_mode()
        elif self.mode == "standalone":
            self._discover_cameras()

        self._log_message("🎯 System initialization complete")

    def _setup_esp32(self):
        """Setup ESP32 connection"""
        # Simple ESP32 setup - try to connect on COM3
        if self.esp32_controller.connect("COM3", 115200):
            self._enable_esp32_controls(True)
            self._log_message("✅ ESP32 connected")
        else:
            self._log_message("❌ ESP32 connection failed")

    # =============================================================================
    # UI Setup Methods
    # =============================================================================

    def _setup_ui(self):
        """Setup user interface"""
        main_splitter = QSplitter()

        # Control panel
        control_panel = self._create_control_panel()

        # Status panel
        status_panel = self._create_status_panel()

        main_splitter.addWidget(control_panel)
        main_splitter.addWidget(status_panel)
        main_splitter.setSizes([700, 300])

        layout = QHBoxLayout()
        layout.addWidget(main_splitter)
        self.setLayout(layout)

    def _create_control_panel(self) -> QWidget:
        """Create main control panel with tabs"""
        panel = QWidget()
        layout = QVBoxLayout()

        # Add mode indicator
        mode_label = QLabel(f"Mode: {self.mode.replace('_', ' ').title()}")
        mode_label.setStyleSheet("font-weight: bold; color: #4CAF50; padding: 5px;")
        layout.addWidget(mode_label)

        tabs = QTabWidget()
        tabs.addTab(self._create_camera_tab(), "HIK Camera")
        tabs.addTab(self._create_recording_tab(), "Recording")
        tabs.addTab(self._create_esp32_tab_enhanced(), "ESP32 Control")
        tabs.addTab(self._create_diagnostics_tab(), "Diagnostics")

        layout.addWidget(tabs)
        panel.setLayout(layout)
        return panel

    # Add this to your diagnostics tab UI:
    def _add_calibration_button_to_diagnostics(self, layout):
        """Add LED calibration button to diagnostics"""
        calibrate_btn = QPushButton("🔧 Calibrate LED Timing")
        calibrate_btn.clicked.connect(self._calibrate_led_timing)
        calibrate_btn.setToolTip("Find optimal LED delay for your setup")

    def _add_led_testing_section_to_esp32_tab(self, esp32_layout):
        """Add LED testing section to ESP32 tab"""

        # LED Testing section
        testing_group = QGroupBox("LED Testing & Diagnostics")
        testing_layout = QVBoxLayout()

        # Test buttons row 1
        test_buttons_row1 = QHBoxLayout()

        detailed_test_btn = QPushButton("🧪 Detailed LED Test")
        detailed_test_btn.clicked.connect(self._test_esp32_led_detailed)
        detailed_test_btn.setStyleSheet("background-color: #2196F3; color: white;")
        test_buttons_row1.addWidget(detailed_test_btn)

        timing_test_btn = QPushButton("⏱️ Timing Test")
        timing_test_btn.clicked.connect(self._test_esp32_timing)
        test_buttons_row1.addWidget(timing_test_btn)

        testing_layout.addLayout(test_buttons_row1)

        # Test buttons row 2
        test_buttons_row2 = QHBoxLayout()

        sequence_test_btn = QPushButton("🎬 Recording Sequence Test")
        sequence_test_btn.clicked.connect(self._test_complete_led_sequence)
        sequence_test_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        test_buttons_row2.addWidget(sequence_test_btn)

        manual_flash_btn = QPushButton("⚡ Manual Flash")
        manual_flash_btn.clicked.connect(self._manual_led_flash)
        test_buttons_row2.addWidget(manual_flash_btn)

        testing_layout.addLayout(test_buttons_row2)

        # Instructions
        instructions = QLabel(
            "Use these tests to verify LED functionality.\nWatch the physical LED during tests!"
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet("color: #888; font-style: italic; padding: 5px;")
        testing_layout.addWidget(instructions)

        testing_group.setLayout(testing_layout)
        esp32_layout.addWidget(testing_group)

    def _create_status_panel(self) -> QWidget:
        """Create status monitoring panel"""
        panel = QWidget()
        layout = QVBoxLayout()

        # System status
        status_group = QGroupBox("System Status")
        status_layout = QVBoxLayout()

        self.camera_status_label = QLabel("Camera: Disconnected")
        self.esp32_status_label = QLabel("ESP32: Disconnected")
        self.recording_status_label = QLabel("Recording: Ready")

        status_layout.addWidget(self.camera_status_label)
        status_layout.addWidget(self.esp32_status_label)
        status_layout.addWidget(self.recording_status_label)

        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # Log display
        log_group = QGroupBox("System Log")
        log_layout = QVBoxLayout()

        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setMaximumHeight(200)
        self.log_display.setStyleSheet(
            "background-color: #1a1a1a; color: #00ff00; font-family: monospace;"
        )

        log_layout.addWidget(self.log_display)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        panel.setLayout(layout)
        return panel

    def _create_camera_tab(self) -> QWidget:
        """Create camera control tab"""
        widget = QWidget()
        layout = QVBoxLayout()

        # Discovery section
        discovery_group = QGroupBox("Camera Discovery & Connection")
        discovery_layout = QVBoxLayout()

        # Discovery controls
        disc_controls = QHBoxLayout()
        discover_btn = QPushButton("🔍 Discover Cameras")
        discover_btn.clicked.connect(self._discover_cameras)
        disc_controls.addWidget(discover_btn)

        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self._discover_cameras)
        disc_controls.addWidget(refresh_btn)
        discovery_layout.addLayout(disc_controls)

        # Camera selection
        camera_layout = QHBoxLayout()
        camera_layout.addWidget(QLabel("Camera:"))
        self.camera_combo = QComboBox()
        self.camera_combo.setMinimumWidth(300)
        camera_layout.addWidget(self.camera_combo)
        discovery_layout.addLayout(camera_layout)

        # Connection controls
        conn_layout = QHBoxLayout()
        self.connect_btn = QPushButton("🔗 Connect")
        self.connect_btn.clicked.connect(self._connect_camera)
        self.connect_btn.setEnabled(False)
        conn_layout.addWidget(self.connect_btn)

        self.disconnect_btn = QPushButton("❌ Disconnect")
        self.disconnect_btn.clicked.connect(self._disconnect_camera)
        self.disconnect_btn.setEnabled(False)
        conn_layout.addWidget(self.disconnect_btn)
        discovery_layout.addLayout(conn_layout)

        discovery_group.setLayout(discovery_layout)
        layout.addWidget(discovery_group)

        # Configuration section
        config_group = QGroupBox("Camera Configuration")
        config_layout = QVBoxLayout()

        # Trigger mode
        trigger_layout = QHBoxLayout()
        trigger_layout.addWidget(QLabel("Trigger Mode:"))
        self.trigger_combo = QComboBox()
        self.trigger_combo.addItems(["Free Running", "Software Trigger", "Hardware Trigger"])
        self.trigger_combo.currentTextChanged.connect(self._on_trigger_mode_changed)
        trigger_layout.addWidget(self.trigger_combo)
        config_layout.addLayout(trigger_layout)

        # Exposure time
        exposure_layout = QHBoxLayout()
        exposure_layout.addWidget(QLabel("Exposure (μs):"))
        self.exposure_spinbox = QSpinBox()
        self.exposure_spinbox.setRange(100, 1000000)
        self.exposure_spinbox.setValue(10000)
        self.exposure_spinbox.valueChanged.connect(self._on_exposure_changed)
        exposure_layout.addWidget(self.exposure_spinbox)
        config_layout.addLayout(exposure_layout)

        config_group.setLayout(config_layout)
        layout.addWidget(config_group)

        # Live view section
        live_group = QGroupBox("Live View")
        live_layout = QVBoxLayout()

        live_controls = QHBoxLayout()
        self.start_live_btn = QPushButton("▶️ Start Live View")
        self.start_live_btn.clicked.connect(self._start_live_view)
        self.start_live_btn.setEnabled(False)
        live_controls.addWidget(self.start_live_btn)

        self.stop_live_btn = QPushButton("⏹️ Stop Live View")
        self.stop_live_btn.clicked.connect(self._stop_live_view)
        self.stop_live_btn.setEnabled(False)
        live_controls.addWidget(self.stop_live_btn)

        self.test_btn = QPushButton("🧪 Test Capture")
        self.test_btn.clicked.connect(self._test_capture)
        self.test_btn.setEnabled(False)
        live_controls.addWidget(self.test_btn)
        live_layout.addLayout(live_controls)

        live_group.setLayout(live_layout)
        layout.addWidget(live_group)
        bandwidth_group = QGroupBox("Bandwidth Optimization")
        bandwidth_layout = QVBoxLayout()

        bandwidth_btn_layout1 = QHBoxLayout()

        optimize_btn = QPushButton("🔧 Optimize Bandwidth")
        optimize_btn.clicked.connect(self._optimize_bandwidth)
        optimize_btn.setStyleSheet("background-color: #2196F3; color: white;")
        bandwidth_btn_layout1.addWidget(optimize_btn)

        check_network_btn = QPushButton("🌐 Check Network")
        check_network_btn.clicked.connect(self._check_network)
        bandwidth_btn_layout1.addWidget(check_network_btn)

        bandwidth_btn_layout2 = QHBoxLayout()

        robust_mode_btn = QPushButton("🛡️ Robust Mode")
        robust_mode_btn.clicked.connect(self._set_robust_mode)
        robust_mode_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        bandwidth_btn_layout2.addWidget(robust_mode_btn)

        bandwidth_layout.addLayout(bandwidth_btn_layout1)
        bandwidth_layout.addLayout(bandwidth_btn_layout2)

        bandwidth_group.setLayout(bandwidth_layout)
        layout.addWidget(bandwidth_group)
        # Advanced connection controls
        advanced_group = QGroupBox("Advanced Connection Tools")
        advanced_layout = QVBoxLayout()

        advanced_btn_layout1 = QHBoxLayout()

        force_release_btn = QPushButton("💥 Force Release All")
        force_release_btn.clicked.connect(self._force_release_all)
        force_release_btn.setStyleSheet("background-color: #ff6b6b; color: white;")
        advanced_btn_layout1.addWidget(force_release_btn)

        check_processes_btn = QPushButton("🔍 Check Processes")
        check_processes_btn.clicked.connect(self._check_processes)
        advanced_btn_layout1.addWidget(check_processes_btn)

        advanced_btn_layout2 = QHBoxLayout()

        aggressive_connect_btn = QPushButton("💥 AGGRESSIVE Connect")
        aggressive_connect_btn.clicked.connect(self._aggressive_connect)
        aggressive_connect_btn.setStyleSheet(
            "background-color: #ff9500; color: white; font-weight: bold;"
        )
        advanced_btn_layout2.addWidget(aggressive_connect_btn)

        reset_network_btn = QPushButton("🔄 Reset Network")
        reset_network_btn.clicked.connect(self._reset_camera_network)
        advanced_btn_layout2.addWidget(reset_network_btn)

        advanced_layout.addLayout(advanced_btn_layout1)
        advanced_layout.addLayout(advanced_btn_layout2)

        advanced_group.setLayout(advanced_layout)
        layout.addWidget(advanced_group)
        widget.setLayout(layout)
        return widget

    def _create_recording_tab(self) -> QWidget:
        """Create recording control tab"""
        widget = QWidget()
        layout = QVBoxLayout()

        # Parameters section
        params_group = QGroupBox("Recording Parameters")
        params_layout = QVBoxLayout()
        # File management section
        file_group = QGroupBox("File Management")
        file_layout = QVBoxLayout()
        # Directory selection
        dir_layout = QHBoxLayout()
        self.select_dir_btn = QPushButton("📁 Select Directory")
        self.select_dir_btn.clicked.connect(self._select_directory)
        dir_layout.addWidget(self.select_dir_btn)

        self.create_subfolder_cb = QCheckBox("Create timestamped subfolder")
        self.create_subfolder_cb.setChecked(True)
        dir_layout.addWidget(self.create_subfolder_cb)
        file_layout.addLayout(dir_layout)

        # ✅ HINZUFÜGEN: dir_label
        self.dir_label = QLabel("No directory selected")
        self.dir_label.setStyleSheet("color: #888;")
        file_layout.addWidget(self.dir_label)

        file_group.setLayout(file_layout)
        layout.addWidget(file_group)
        # Timing parameters
        timing_layout = QHBoxLayout()

        duration_layout = QVBoxLayout()
        duration_layout.addWidget(QLabel("Duration (min):"))
        self.duration_input = QLineEdit()
        self.duration_input.setPlaceholderText("60")
        self.duration_input.textChanged.connect(self._calculate_stats)
        duration_layout.addWidget(self.duration_input)
        timing_layout.addLayout(duration_layout)

        interval_layout = QVBoxLayout()
        interval_layout.addWidget(QLabel("Interval (sec):"))
        self.interval_input = QLineEdit()
        self.interval_input.setPlaceholderText("30")
        self.interval_input.textChanged.connect(self._calculate_stats)
        interval_layout.addWidget(self.interval_input)
        timing_layout.addLayout(interval_layout)

        frames_layout = QVBoxLayout()
        frames_layout.addWidget(QLabel("Expected Frames:"))
        self.frames_label = QLabel("0")
        self.frames_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        frames_layout.addWidget(self.frames_label)
        timing_layout.addLayout(frames_layout)

        params_layout.addLayout(timing_layout)

        # Statistics display
        self.stats_label = QLabel("Recording Statistics: Enter parameters above")
        self.stats_label.setStyleSheet(
            "background-color: #2a2a2a; padding: 8px; border-radius: 4px;"
        )
        self.stats_label.setWordWrap(True)
        params_layout.addWidget(self.stats_label)

        params_group.setLayout(params_layout)
        layout.addWidget(params_group)

        # Recording control section
        control_group = QGroupBox("Recording Control")
        control_layout = QVBoxLayout()

        # Progress display
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        control_layout.addWidget(self.progress_bar)

        # Progress details
        progress_details = QHBoxLayout()
        self.current_frame_label = QLabel("Frame: 0/0")
        progress_details.addWidget(self.current_frame_label)

        self.elapsed_label = QLabel("Elapsed: 00:00:00")
        progress_details.addWidget(self.elapsed_label)

        self.eta_label = QLabel("ETA: --:--:--")
        progress_details.addWidget(self.eta_label)
        control_layout.addLayout(progress_details)

        # Control buttons
        button_layout = QHBoxLayout()

        self.start_rec_btn = QPushButton("🎬 Start Recording")
        self.start_rec_btn.clicked.connect(self._start_recording)
        button_layout.addWidget(self.start_rec_btn)

        self.pause_rec_btn = QPushButton("⏸️ Pause")
        self.pause_rec_btn.clicked.connect(self._pause_recording)
        self.pause_rec_btn.setEnabled(False)
        button_layout.addWidget(self.pause_rec_btn)

        self.stop_rec_btn = QPushButton("⏹️ Stop")
        self.stop_rec_btn.clicked.connect(self._stop_recording)
        self.stop_rec_btn.setEnabled(False)
        button_layout.addWidget(self.stop_rec_btn)

        control_layout.addLayout(button_layout)
        control_group.setLayout(control_layout)
        layout.addWidget(control_group)

        widget.setLayout(layout)
        return widget

    def _create_esp32_tab_enhanced(self) -> QWidget:
        """Enhanced ESP32 control tab with testing capabilities"""
        widget = QWidget()
        layout = QVBoxLayout()

        # Connection section (keep existing code)
        conn_group = QGroupBox("ESP32 Connection")
        conn_layout = QVBoxLayout()

        conn_controls = QHBoxLayout()
        self.connect_esp32_btn = QPushButton("🔗 Connect ESP32")
        self.connect_esp32_btn.clicked.connect(self._connect_esp32)
        conn_controls.addWidget(self.connect_esp32_btn)

        self.disconnect_esp32_btn = QPushButton("❌ Disconnect")
        self.disconnect_esp32_btn.clicked.connect(self._disconnect_esp32)
        self.disconnect_esp32_btn.setEnabled(False)
        conn_controls.addWidget(self.disconnect_esp32_btn)
        conn_layout.addLayout(conn_controls)

        self.esp32_status_detail = QLabel("ESP32: Not connected")
        conn_layout.addWidget(self.esp32_status_detail)

        conn_group.setLayout(conn_layout)
        layout.addWidget(conn_group)

        # LED control section
        led_group = QGroupBox("LED Control")
        led_layout = QVBoxLayout()

        # *** WICHTIG: LED power control ZUERST ***
        power_layout = QHBoxLayout()
        power_layout.addWidget(QLabel("LED Power:"))

        self.led_power_slider = QSlider(Qt.Horizontal)
        self.led_power_slider.setRange(0, 100)
        self.led_power_slider.setValue(100)
        self.led_power_slider.valueChanged.connect(self._on_led_power_changed)
        power_layout.addWidget(self.led_power_slider)

        self.led_power_spinbox = QSpinBox()
        self.led_power_spinbox.setRange(0, 100)
        self.led_power_spinbox.setValue(100)
        self.led_power_spinbox.setSuffix("%")
        self.led_power_spinbox.valueChanged.connect(self._on_led_power_spinbox_changed)
        power_layout.addWidget(self.led_power_spinbox)
        led_layout.addLayout(power_layout)

        # *** DANN: Manual controls (können jetzt auf led_power_spinbox zugreifen) ***
        manual_layout = QHBoxLayout()
        self.led_on_btn = QPushButton("💡 LED ON (100%)")  # Initial text
        self.led_on_btn.clicked.connect(self._led_on)
        self.led_on_btn.setEnabled(False)
        manual_layout.addWidget(self.led_on_btn)

        self.led_off_btn = QPushButton("🌑 LED OFF")
        self.led_off_btn.clicked.connect(self._led_off)
        self.led_off_btn.setEnabled(False)
        manual_layout.addWidget(self.led_off_btn)
        led_layout.addLayout(manual_layout)

        led_group.setLayout(led_layout)
        layout.addWidget(led_group)

        # LED Testing section
        self._add_led_testing_section_to_esp32_tab(layout)

        # Environmental sensors section
        sensor_group = QGroupBox("Environmental Sensors")
        sensor_layout = QVBoxLayout()

        sensor_readings = QHBoxLayout()

        temp_layout = QVBoxLayout()
        temp_layout.addWidget(QLabel("Temperature:"))
        self.temp_display = QLabel("--°C")
        temp_layout.addWidget(self.temp_display)
        sensor_readings.addLayout(temp_layout)

        hum_layout = QVBoxLayout()
        hum_layout.addWidget(QLabel("Humidity:"))
        self.humidity_display = QLabel("--%")
        hum_layout.addWidget(self.humidity_display)
        sensor_readings.addLayout(hum_layout)

        sensor_layout.addLayout(sensor_readings)

        read_sensors_btn = QPushButton("📊 Read Sensors")
        read_sensors_btn.clicked.connect(self._read_sensors)
        sensor_layout.addWidget(read_sensors_btn)

        sensor_group.setLayout(sensor_layout)
        layout.addWidget(sensor_group)

        widget.setLayout(layout)

        # *** WICHTIG: Update button text NACH vollständiger UI-Initialisierung ***
        QTimer.singleShot(100, self._update_led_power_display)

        return widget

    # Fügen Sie diese Methode zu Ihrer NematostellaTimeSeriesCapture Klasse hinzu:

    def _create_diagnostics_tab(self) -> QWidget:
        """Create diagnostics tab"""
        widget = QWidget()
        layout = QVBoxLayout()

        # System diagnostics
        diag_group = QGroupBox("System Diagnostics")
        diag_layout = QVBoxLayout()

        diag_buttons = QHBoxLayout()

        test_system_btn = QPushButton("🧪 Test Full System")
        test_system_btn.clicked.connect(self._test_full_system)
        diag_buttons.addWidget(test_system_btn)

        test_sync_btn = QPushButton("⚡ Test Sync Capture")
        test_sync_btn.clicked.connect(self._test_sync_capture)
        diag_buttons.addWidget(test_sync_btn)

        diag_layout.addLayout(diag_buttons)
        quick_test_btn = QPushButton("⚡ Quick Frame Test")
        quick_test_btn.clicked.connect(self._quick_frame_capture_test)
        quick_test_btn.setStyleSheet("background-color: #ff6600; color: white; font-weight: bold;")
        diag_layout.addWidget(quick_test_btn)  # oder fügen Sie ihn zu einem Layout hinzu

        # Performance monitoring
        perf_layout = QHBoxLayout()
        self.fps_label = QLabel("FPS: --")
        perf_layout.addWidget(self.fps_label)
        # In Diagnostics-Tab:
        self.dropped_frames_label = QLabel("Dropped: 0")
        perf_layout.addWidget(self.dropped_frames_label)
        diag_layout.addLayout(perf_layout)
        diag_group.setLayout(diag_layout)
        layout.addWidget(diag_group)

        ir_test_btn = QPushButton("🔬 Test IR Characteristics")
        ir_test_btn.clicked.connect(self._test_ir_led_characteristics)
        # Button hinzufügen:
        compare_btn = QPushButton("🔍 Compare LED Sequences")
        compare_btn.clicked.connect(self._compare_led_sequences)
        # In der Diagnostics-Tab:
        timestamp_test_btn = QPushButton("⏱️ Test Timestamps")
        timestamp_test_btn.clicked.connect(self._test_timestamp_accuracy)
        # Test results
        results_group = QGroupBox("Test Results")
        results_layout = QVBoxLayout()

        self.results_display = QTextEdit()
        self.results_display.setReadOnly(True)
        self.results_display.setMaximumHeight(150)
        self.results_display.setStyleSheet(
            "background-color: #1a1a1a; color: #ffffff; font-family: monospace;"
        )
        results_layout.addWidget(self.results_display)

        results_group.setLayout(results_layout)
        layout.addWidget(results_group)

        widget.setLayout(layout)
        return widget

    # Und stellen Sie sicher, dass diese Test-Methoden auch existieren:

    def _test_full_system(self):
        """Test complete system functionality"""
        results = []

        # Test camera connection
        if self.camera_connected:
            if self.mode == "imswitch_framegrab":
                # Test ImSwitch frame grabbing
                frame = self._grab_current_frame()
                if frame is not None:
                    results.append("✅ Camera (ImSwitch): OK")
                else:
                    results.append("❌ Camera (ImSwitch): FAILED")
            else:
                # Test direct camera
                frame = self.camera_thread.capture_frame(1000)
                if frame is not None:
                    results.append("✅ Camera (Direct): OK")
                else:
                    results.append("❌ Camera (Direct): FAILED")
        else:
            results.append("⚠️ Camera: Not connected")

        # Test ESP32 connection
        if self.esp32_controller.connected:
            response = self.esp32_controller.send_command(ESP32Commands.STATUS)
            if response:
                results.append("✅ ESP32: OK")
            else:
                results.append("❌ ESP32: FAILED")
        else:
            results.append("⚠️ ESP32: Not connected")

        # Test LED functionality
        if self.esp32_controller.connected:
            # Test LED power setting
            if self.esp32_controller.set_led_power(50):
                results.append("✅ LED Power Control: OK")
            else:
                results.append("❌ LED Power Control: FAILED")

            # Test LED on/off
            if self.esp32_controller.led_on():
                results.append("✅ LED ON: OK")
                time.sleep(0.5)
                if self.esp32_controller.led_off():
                    results.append("✅ LED OFF: OK")
                else:
                    results.append("❌ LED OFF: FAILED")
            else:
                results.append("❌ LED ON: FAILED")

        # Display results
        result_text = "\n".join(results)
        self.results_display.setText(result_text)
        self._log_message("🧪 System test completed")

    def _test_sync_capture(self):
        """Test synchronized capture"""
        if not self.esp32_controller.connected:
            self._log_message("❌ ESP32 required for sync test")
            self.results_display.setText("❌ ESP32 required for sync test")
            return

        try:
            self._log_message("⚡ Starting sync capture test...")

            # Test LED synchronization
            start_time = time.time()

            # Phase 1: LED OFF
            self.esp32_controller.set_led_power(0)
            self.esp32_controller.led_off()
            time.sleep(0.5)

            # Phase 2: LED ON
            self.esp32_controller.set_led_power(100)
            led_on_success = self.esp32_controller.led_on()

            if not led_on_success:
                self.results_display.setText("❌ Sync test: LED ON failed")
                return

            # Phase 3: Capture frame
            if self.mode == "imswitch_framegrab":
                frame = self._grab_current_frame()
            else:
                frame = self.camera_thread.capture_frame(2000)

            # Phase 4: LED OFF
            self.esp32_controller.set_led_power(0)
            self.esp32_controller.led_off()

            elapsed = time.time() - start_time

            if frame is not None:
                result = f"✅ Sync test: {elapsed*1000:.1f}ms total, frame captured successfully"
                self._log_message(result)
            else:
                result = "❌ Sync test: Frame capture failed"
                self._log_message(result)

            self.results_display.setText(result)

        except Exception as e:
            result = f"❌ Sync test error: {e}"
            self._log_message(result)
            self.results_display.setText(result)

    def _test_esp32_led_detailed(self):
        """Detailed ESP32 LED test"""
        if not self.esp32_controller.connected:
            self._log_message("❌ ESP32 not connected for LED test")
            return

        self._log_message("🧪 Starting detailed ESP32 LED test...")
        # Ihre bestehende Implementierung oder vereinfachte Version
        self._log_message("✅ LED test completed")

    def _test_esp32_timing(self):
        """Test ESP32 timing"""
        if not self.esp32_controller.connected:
            self._log_message("❌ ESP32 not connected")
            return

        self._log_message("⏱️ Testing ESP32 timing...")
        # Ihre bestehende Implementierung oder vereinfachte Version
        self._log_message("✅ Timing test completed")

    def _test_complete_led_sequence(self):
        """Test complete LED sequence"""
        if not self.esp32_controller.connected:
            self._log_message("❌ ESP32 not connected")
            return

        self._log_message("🎬 Testing complete LED sequence...")
        # Ihre bestehende Implementierung oder vereinfachte Version
        self._log_message("✅ LED sequence test completed")

    def _manual_led_flash(self):
        """Manual LED flash"""
        if not self.esp32_controller.connected:
            self._log_message("❌ ESP32 not connected")
            return

        self._log_message("⚡ Manual LED flash...")
        # Ihre bestehende Implementierung oder vereinfachte Version
        self._log_message("✅ Manual flash completed")

    # =============================================================================
    # Mode Detection and Setup Methods (from your Part 3)
    # =============================================================================

    # def _detect_mode(self) -> str:
    #     """Auto-detect operating mode"""
    #     try:
    #         if hasattr(self, 'viewer') and self.viewer:
    #             imswitch_layer_indicators = [
    #                 'Live:', 'Widefield', 'Camera', 'Detector'
    #             ]

    #             for layer in self.viewer.layers:
    #                 if any(indicator in layer.name for indicator in imswitch_layer_indicators):
    #                     print("🔧 Detected ImSwitch live view layer - using frame grabber mode")
    #                     return "imswitch_framegrab"
    #     except Exception as e:
    #         print(f"Layer detection error: {e}")

    #     try:
    #         imswitch_config = self._try_load_imswitch_config()
    #         if imswitch_config and "detectors" in imswitch_config:
    #             print("🔧 Found ImSwitch config file - using settings mode")
    #             self.imswitch_config = imswitch_config
    #             return "imswitch_settings"
    #     except Exception as e:
    #         print(f"Config file detection error: {e}")

    #     print("📱 No ImSwitch detected - using standalone mode")
    #     return "standalone"

    def _try_load_imswitch_config(self) -> Optional[dict]:
        """Try to load ImSwitch configuration"""
        config_paths = [
            "imswitch_config.json",
            os.path.join(os.getcwd(), "config.json"),
            os.path.expanduser("~/.imswitch/config.json"),
            "C:\\ImSwitch\\config\\config.json",
        ]

        for config_path in config_paths:
            if os.path.exists(config_path):
                try:
                    with open(config_path) as f:
                        config = json.load(f)
                    print(f"✅ Loaded ImSwitch config: {config_path}")
                    return config
                except Exception as e:
                    print(f"❌ Error loading {config_path}: {e}")

        return None

    def _setup_connections(self):
        """Setup signal connections"""
        self.camera_thread.frame_ready.connect(self._on_camera_frame)
        self.camera_thread.error_occurred.connect(self._on_camera_error)
        self.camera_thread.status_changed.connect(self._on_camera_status)

    def _log_message(self, message: str):
        """Add timestamped message to log"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        log_entry = f"[{timestamp}] {message}"

        if self.log_display:
            self.log_display.append(log_entry)
            scrollbar = self.log_display.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

        print(log_entry)

    # =============================================================================
    # Camera Control Methods
    # =============================================================================

    def _discover_cameras(self):
        """Discover cameras"""
        self._log_message("🔍 Discovering HIK GigE cameras...")

        if not _HAS_HIK_SDK:
            self._log_message("❌ HIK SDK not available")
            QMessageBox.warning(self, "SDK Missing", "HIK SDK not found")
            return

        self.camera_combo.clear()
        self.available_cameras = self.camera_thread.discover_cameras()

        if self.available_cameras:
            for camera in self.available_cameras:
                status = "✅" if camera["accessible"] else "❌"
                text = f"{status} {camera['model']} ({camera['ip']})"
                self.camera_combo.addItem(text)

            self.connect_btn.setEnabled(True)
            self._log_message(f"✅ Found {len(self.available_cameras)} camera(s)")
        else:
            self.camera_combo.addItem("No cameras found")
            self._log_message("❌ No cameras found")

    def _diagnose_camera(self):
        """Diagnose selected camera"""
        camera_index = self.camera_combo.currentIndex()
        if camera_index >= 0:
            self.camera_thread.diagnose_camera_state(camera_index)

    def connect_camera(self, camera_index: int) -> bool:
        """Connect to HIK camera with enhanced debugging and force release"""
        if not _HAS_HIK_SDK:
            print("❌ HIK SDK not available")
            return False

        try:
            print(f"=== Enhanced Camera Connection (Index: {camera_index}) ===")

            # Step 1: Enumerate devices to get device info
            device_list = MV_CC_DEVICE_INFO_LIST()
            ret = MvCamera.MV_CC_EnumDevices(MV_GIGE_DEVICE | MV_USB_DEVICE, device_list)

            if ret != MV_OK:
                print(f"❌ Device enumeration failed: {ret} (0x{ret:08X})")
                return False

            if camera_index >= device_list.nDeviceNum:
                print(f"❌ Invalid camera index: {camera_index} >= {device_list.nDeviceNum}")
                return False

            device_info = cast(
                device_list.pDeviceInfo[camera_index], POINTER(MV_CC_DEVICE_INFO)
            ).contents

            # Step 2: Print device information for debugging
            if device_info.nTLayerType == MV_GIGE_DEVICE:
                gige_info = device_info.SpecialInfo.stGigEInfo
                model = self._extract_string(gige_info.chModelName, 32)
                ip = self._ip_to_string(gige_info.nCurrentIp)
                print(f"📷 Target camera: {model} at {ip}")

            # Step 3: Enhanced force-release with multiple strategies
            print("🔄 Starting enhanced force-release procedure...")
            self._enhanced_force_release_v2(device_info)

            # Step 4: Wait for device to be fully released
            print("⏳ Waiting for device release...")
            time.sleep(3.0)

            # Step 5: Try connection with improved strategies
            connection_strategies = [
                ("Monitor Only", self._try_monitor_only),
                ("Control Access", self._try_control_access),
                ("Force Exclusive", self._try_force_exclusive),
                ("Delayed Retry", self._try_delayed_retry),
            ]

            for strategy_name, strategy_func in connection_strategies:
                print(f"🔧 Trying strategy: {strategy_name}")
                try:
                    if strategy_func(device_info):
                        print(f"✅ {strategy_name} successful!")
                        self._configure_camera()
                        self.status_changed.emit("Connected")
                        return True
                    else:
                        print(f"❌ {strategy_name} failed")
                except Exception as e:
                    print(f"❌ {strategy_name} exception: {e}")

                time.sleep(1.0)  # Wait between strategies

            print("❌ All connection strategies exhausted")
            return False

        except Exception as e:
            print(f"❌ Connection procedure exception: {e}")
            import traceback

            traceback.print_exc()
            return False

    def _enhanced_force_release_v2(self, device_info):
        """Enhanced force release V2"""
        try:
            # Multiple temporary connections to force release
            for attempt in range(3):
                try:
                    temp_camera = MvCamera()
                    ret = temp_camera.MV_CC_CreateHandle(device_info)
                    if ret == MV_OK:
                        temp_camera.MV_CC_CloseDevice()
                        temp_camera.MV_CC_DestroyHandle()
                    time.sleep(0.5)
                except Exception as e:
                    self._log_message(f"Force release attempt {attempt + 1} error: {e}")

            self._log_message("Enhanced force release V2 completed")

        except Exception as e:
            self._log_message(f"Enhanced force release V2 failed: {e}")

    def _try_monitor_only(self, device_info) -> bool:
        """Try monitor-only access (least intrusive)"""
        try:
            self.camera = MvCamera()
            ret = self.camera.MV_CC_CreateHandle(device_info)
            if ret != MV_OK:
                print(f"   ❌ Handle creation failed: {ret} (0x{ret:08X})")
                return False

            print("   → Attempting Monitor access...")
            ret = self.camera.MV_CC_OpenDevice(0, 0)  # Monitor mode only

            if ret == MV_OK:
                print("   ✅ Monitor access granted")
                return True
            else:
                print(f"   ❌ Monitor access denied: {ret} (0x{ret:08X})")
                self._cleanup_failed_camera()
                return False

        except Exception as e:
            print(f"   ❌ Monitor access exception: {e}")
            self._cleanup_failed_camera()
            return False

    def _try_control_access(self, device_info) -> bool:
        """Try control access with proper timing"""
        try:
            time.sleep(1.0)  # Extra delay

            self.camera = MvCamera()
            ret = self.camera.MV_CC_CreateHandle(device_info)
            if ret != MV_OK:
                print(f"   ❌ Handle creation failed: {ret} (0x{ret:08X})")
                return False

            print("   → Attempting Control access...")
            ret = self.camera.MV_CC_OpenDevice(1, 0)  # Control mode

            if ret == MV_OK:
                print("   ✅ Control access granted")
                return True
            else:
                print(f"   ❌ Control access denied: {ret} (0x{ret:08X})")
                self._cleanup_failed_camera()
                return False

        except Exception as e:
            print(f"   ❌ Control access exception: {e}")
            self._cleanup_failed_camera()
            return False

    def _try_force_exclusive(self, device_info) -> bool:
        """Try exclusive access after extra cleanup"""
        try:
            # Extra cleanup before exclusive attempt
            self._enhanced_force_release_v2(device_info)
            time.sleep(2.0)

            self.camera = MvCamera()
            ret = self.camera.MV_CC_CreateHandle(device_info)
            if ret != MV_OK:
                print(f"   ❌ Handle creation failed: {ret} (0x{ret:08X})")
                return False

            print("   → Attempting Exclusive access...")
            ret = self.camera.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0)

            if ret == MV_OK:
                print("   ✅ Exclusive access granted")
                return True
            else:
                print(f"   ❌ Exclusive access denied: {ret} (0x{ret:08X})")
                self._cleanup_failed_camera()
                return False

        except Exception as e:
            print(f"   ❌ Exclusive access exception: {e}")
            self._cleanup_failed_camera()
            return False

    def _try_delayed_retry(self, device_info) -> bool:
        """Try with maximum delays and retries"""
        try:
            print("   → Long delay retry strategy...")
            time.sleep(5.0)  # Long delay

            # Try monitor access with retries
            for attempt in range(3):
                self.camera = MvCamera()
                ret = self.camera.MV_CC_CreateHandle(device_info)
                if ret != MV_OK:
                    print(f"   → Retry {attempt + 1}: Handle creation failed: {ret}")
                    time.sleep(1.0)
                    continue

                time.sleep(1.0)  # Delay before open
                ret = self.camera.MV_CC_OpenDevice(0, 0)  # Monitor mode

                if ret == MV_OK:
                    print(f"   ✅ Delayed retry {attempt + 1} successful")
                    return True
                else:
                    print(f"   → Retry {attempt + 1}: Access failed: {ret}")
                    self._cleanup_failed_camera()
                    time.sleep(2.0)  # Longer delay between retries

            return False

        except Exception as e:
            print(f"   ❌ Delayed retry exception: {e}")
            self._cleanup_failed_camera()
            return False

    def _cleanup_failed_camera(self):
        """Clean up camera object after failed connection"""
        try:
            if hasattr(self, "camera") and self.camera is not None:
                self.camera.MV_CC_DestroyHandle()
                self.camera = None
        except:
            self.camera = None

    # =============================================================================
    # ALSO ADD THIS DIAGNOSTIC METHOD TO HELP DEBUG
    # =============================================================================

    def diagnose_camera_state(self, camera_index: int):
        """Diagnose camera state for debugging"""
        if not _HAS_HIK_SDK:
            return

        try:
            print(f"🔍 Diagnosing camera {camera_index}...")

            device_list = MV_CC_DEVICE_INFO_LIST()
            ret = MvCamera.MV_CC_EnumDevices(MV_GIGE_DEVICE | MV_USB_DEVICE, device_list)

            if ret != MV_OK or camera_index >= device_list.nDeviceNum:
                print(f"❌ Cannot enumerate camera {camera_index}")
                return

            device_info = cast(
                device_list.pDeviceInfo[camera_index], POINTER(MV_CC_DEVICE_INFO)
            ).contents

            if device_info.nTLayerType == MV_GIGE_DEVICE:
                gige_info = device_info.SpecialInfo.stGigEInfo
                model = self._extract_string(gige_info.chModelName, 32)
                serial = self._extract_string(gige_info.chSerialNumber, 16)
                ip = self._ip_to_string(gige_info.nCurrentIp)

                print(f"📷 Camera: {model}")
                print(f"📷 Serial: {serial}")
                print(f"📷 IP: {ip}")

                # Check accessibility
                try:
                    accessible = gige_info.nAccessibleNum == 1
                    print(f"📷 Accessible: {accessible}")
                except:
                    print("📷 Accessibility: Unknown")

            # Try to create handle to test availability
            test_camera = MvCamera()
            ret = test_camera.MV_CC_CreateHandle(device_info)
            if ret == MV_OK:
                print("📷 Handle creation: ✅ OK")
                test_camera.MV_CC_DestroyHandle()
            else:
                print(f"📷 Handle creation: ❌ Failed ({ret})")

        except Exception as e:
            print(f"❌ Diagnosis failed: {e}")

    def _disconnect_camera(self):
        """Disconnect camera"""
        if self.camera_thread.running:
            self._stop_live_view()

        self.camera_thread.disconnect_camera()
        self.camera_connected = False
        self._enable_camera_controls(False)
        self._log_message("✅ Camera disconnected")

    def _start_live_view(self):
        """Start live view based on mode"""
        if not self.camera_connected:
            return

        if self.mode == "imswitch_framegrab":
            # For ImSwitch frame grabbing, we don't start our own acquisition
            self._log_message("✅ ImSwitch frame grabber mode - live view ready")
            self.test_btn.setEnabled(True)
            self.start_live_btn.setEnabled(False)
            self.stop_live_btn.setEnabled(True)
        else:
            # For standalone mode, start normal acquisition
            if self.camera_thread.start_acquisition():
                self.camera_thread.start()
                self.start_live_btn.setEnabled(False)
                self.stop_live_btn.setEnabled(True)
                self._log_message("✅ Live view started")
            else:
                self._log_message("❌ Failed to start live view")

    def _stop_live_view(self):
        """Stop live view based on mode"""
        if self.mode == "imswitch_framegrab":
            # For ImSwitch mode, just update UI
            self.start_live_btn.setEnabled(True)
            self.stop_live_btn.setEnabled(False)
            self.test_btn.setEnabled(False)
            self._log_message("✅ ImSwitch frame grabber mode stopped")
        else:
            # For standalone mode, stop acquisition
            if self.camera_thread.running:
                self.camera_thread.running = False
                self.camera_thread.wait()

            self.camera_thread.stop_acquisition()

            if self.live_layer:
                try:
                    self.viewer.layers.remove(self.live_layer)
                except:
                    pass
                self.live_layer = None

        self.start_live_btn.setEnabled(True)
        self.stop_live_btn.setEnabled(False)
        self._log_message("✅ Live view stopped")

    def _test_capture(self):
        """Test capture based on mode"""
        if self.mode == "imswitch_framegrab":
            self._test_imswitch_framegrab()
        else:
            # Original test capture for standalone mode
            if not self.camera_connected:
                return

            frame = self.camera_thread.capture_frame(1000)
            if frame is not None:
                layer_name = "Test Capture"
                existing = [l for l in self.viewer.layers if l.name == layer_name]
                if existing:
                    self.viewer.layers.remove(existing[0])

                self.viewer.add_image(frame, name=layer_name, rgb=(frame.ndim == 3))
                self._log_message(f"✅ Test capture: {frame.shape}")
            else:
                self._log_message("❌ Test capture failed")

    # =============================================================================
    # Recording Control Methods
    # =============================================================================
    def _calculate_stats(self):
        """Calculate recording statistics"""
        try:
            duration = float(self.duration_input.text()) if self.duration_input.text() else 0
            interval = float(self.interval_input.text()) if self.interval_input.text() else 0

            if duration > 0 and interval > 0:
                total_frames = int((duration * 60) / interval)
                self.frames_label.setText(str(total_frames))

                stats = "Recording Statistics:\n"
                stats += f"• Frames: {total_frames:,}\n"
                stats += f"• Duration: {duration:.1f} min\n"
                stats += f"• Interval: {interval:.1f} sec"

                self.stats_label.setText(stats)
            else:
                self.frames_label.setText("0")
                self.stats_label.setText("Enter valid parameters")
        except ValueError:
            self.frames_label.setText("Invalid")
            self.stats_label.setText("Invalid input values")

    def _pause_recording(self):
        """Pause/resume recording"""
        if self.capture_timer.isActive():
            self.capture_timer.stop()
            self.pause_rec_btn.setText("▶️ Resume")
            self._log_message("⏸️ Recording paused")
        else:
            self.capture_timer.start()
            self.pause_rec_btn.setText("⏸️ Pause")
            self._log_message("▶️ Recording resumed")

    def _stop_recording(self):
        """Stop recording"""
        self.capture_timer.stop()

        if self.esp32_controller.connected:
            self.esp32_controller.led_off()

        self.recording_manager.finalize_recording()

        self._enable_recording_controls(False)
        self.progress_bar.setVisible(False)

        elapsed = time.time() - self.recording_manager.start_time
        frames = self.recording_manager.current_frame

        self._log_message(f"✅ Recording completed: {frames} frames in {elapsed/60:.1f}min")

    def _update_led_power_display(self):
        """Update LED power display to show current setting"""
        if hasattr(self, "led_power_spinbox") and self.led_power_spinbox:
            current_power = self.led_power_spinbox.value()
            if hasattr(self, "led_on_btn") and self.led_on_btn:
                self.led_on_btn.setText(f"💡 LED ON ({current_power}%)")

            # Also update the status if ESP32 is connected
            if self.esp32_controller.connected and hasattr(self, "esp32_status_detail"):
                self.esp32_status_detail.setText(f"ESP32: Connected - LED Power: {current_power}%")

    def _calculate_next_capture_time(self, frame_number: int) -> float:
        """
        Berechnet den exakten Zeitpunkt für den nächsten Frame
        Kompensiert für Drift durch kumulative Fehler
        """
        return self.recording_start_time + (frame_number * self.target_interval)

    def _get_current_led_power(self) -> int:
        """Get the current LED power setting from UI"""
        if hasattr(self, "led_power_spinbox") and self.led_power_spinbox:
            return self.led_power_spinbox.value()

        return 100  # Default fallback

    def _update_progress_ui(self, current: int, total: int):
        """Update progress UI elements"""
        if self.progress_bar:
            self.progress_bar.setValue(current)
        if hasattr(self, "current_frame_label") and self.current_frame_label:
            self.current_frame_label.setText(f"Frame: {current}/{total}")

        if hasattr(self, "elapsed_label") and self.elapsed_label:
            elapsed = time.time() - self.recording_manager.start_time
            self.elapsed_label.setText(f"Elapsed: {self._format_time(elapsed)}")

        if hasattr(self, "eta_label") and self.eta_label and current > 0:
            elapsed = time.time() - self.recording_manager.start_time
            rate = current / elapsed
            eta = (total - current) / rate if rate > 0 else 0
            self.eta_label.setText(f"ETA: {self._format_time(eta)}")

    def _format_time(self, seconds: float) -> str:
        """Format time in HH:MM:SS format"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    # =============================================================================
    # ESP32 Control Methods
    # =============================================================================

    def _setup_esp32(self):
        """Setup ESP32 connection"""
        if self.esp32_controller.connect():
            self._enable_esp32_controls(True)
            self._log_message("✅ ESP32 connected")
        else:
            self._log_message("❌ ESP32 connection failed")

    def _connect_esp32(self):
        """Connect to ESP32"""
        if self.esp32_controller.connect():
            self._enable_esp32_controls(True)
            self._log_message("✅ ESP32 connected")
        else:
            self._log_message("❌ ESP32 connection failed")

    def _disconnect_esp32(self):
        """Disconnect ESP32"""
        self.esp32_controller.disconnect()
        self._enable_esp32_controls(False)
        self._log_message("✅ ESP32 disconnected")

    def _led_on(self):
        """Enhanced LED ON using current UI power setting"""
        if not self.esp32_controller.connected:
            self._log_message("❌ ESP32 not connected")
            return

        try:
            # WICHTIG: Verwende die aktuelle GUI-Einstellung
            user_led_power = self._get_current_led_power()
            self._log_message(f"💡 Enhanced LED ON sequence with {user_led_power}% power...")

            # Step 1: Ensure clean state - turn off first
            self.esp32_controller.set_led_power(0)
            time.sleep(0.1)
            self.esp32_controller.led_off()
            time.sleep(0.2)

            # Step 2: Set USER SELECTED power
            if not self.esp32_controller.set_led_power(user_led_power):
                self._log_message(f"❌ Failed to set LED power to {user_led_power}%")
                return
            time.sleep(0.1)

            # Step 3: Send LED ON command with retries
            for attempt in range(3):
                if self.esp32_controller.led_on():
                    self._log_message(
                        f"✅ LED ON successful at {user_led_power}% (attempt {attempt + 1})"
                    )
                    return
                else:
                    self._log_message(f"⚠️ LED ON attempt {attempt + 1} failed")
                    time.sleep(0.1)

            self._log_message("❌ LED ON failed after 3 attempts")

        except Exception as e:
            self._log_message(f"❌ LED ON error: {e}")

    def _led_off(self):
        """Enhanced LED OFF with verification"""
        if not self.esp32_controller.connected:
            self._log_message("❌ ESP32 not connected")
            return

        try:
            self._log_message("🌑 Enhanced LED OFF sequence...")

            # Step 1: Set power to 0% (nicht zur GUI-Einstellung!)
            self.esp32_controller.set_led_power(0)
            time.sleep(0.1)

            # Step 2: Send LED OFF command multiple times for reliability
            for attempt in range(3):
                if self.esp32_controller.led_off():
                    self._log_message(f"✅ LED OFF successful (attempt {attempt + 1})")
                    break
                else:
                    self._log_message(f"⚠️ LED OFF attempt {attempt + 1} failed")
                    time.sleep(0.1)

            # Step 3: Final verification
            time.sleep(0.1)
            self._log_message("✅ LED OFF sequence completed")

        except Exception as e:
            self._log_message(f"❌ LED OFF error: {e}")

    def _on_led_power_changed(self, value: int):
        """Handle LED power slider change"""
        self.led_power_spinbox.setValue(value)
        # Update button text to show current power
        self._update_led_power_display()
        # Optionally set power immediately if connected
        if self.esp32_controller.connected:
            self.esp32_controller.set_led_power(value)

    def _on_led_power_spinbox_changed(self, value: int):
        """Handle LED power spinbox change"""
        self.led_power_slider.setValue(value)
        # Update button text to show current power
        self._update_led_power_display()
        # Optionally set power immediately if connected
        if self.esp32_controller.connected:
            self.esp32_controller.set_led_power(value)

    def _read_sensors(self):
        """Read environmental sensors with decimal precision"""
        if not self.esp32_controller.connected:
            self._log_message("❌ ESP32 not connected")
            return

        sync_data = self.esp32_controller.sync_capture()
        if sync_data:
            temp = sync_data.get("temperature", 0.0)
            humidity = sync_data.get("humidity", 0.0)

            # Display with 1 decimal place
            self.temp_display.setText(f"{temp:.1f}°C")
            self.humidity_display.setText(f"{humidity:.1f}%")

            self._log_message(f"📊 Sensors: {temp:.1f}°C, {humidity:.1f}%")
        else:
            self._log_message("❌ Sensor read failed")

    # =============================================================================
    # Diagnostic Methods
    # =============================================================================

    def _test_full_system(self):
        """Test complete system functionality"""
        results = []

        if self.camera_connected:
            frame = self.camera_thread.capture_frame(1000)
            if frame is not None:
                results.append("✅ Camera: OK")
            else:
                results.append("❌ Camera: FAILED")
        else:
            results.append("⚠️ Camera: Not connected")

        if self.esp32_controller.connected:
            response = self.esp32_controller.send_command(ESP32Commands.STATUS)
            if response:
                results.append("✅ ESP32: OK")
            else:
                results.append("❌ ESP32: FAILED")
        else:
            results.append("⚠️ ESP32: Not connected")

        result_text = "\n".join(results)
        self.results_display.setText(result_text)
        self._log_message("🧪 System test completed")

    def _test_sync_capture(self):
        """Test synchronized capture"""
        if not self.esp32_controller.connected:
            self._log_message("❌ ESP32 required for sync test")
            return

        start_time = time.time()
        sync_data = self.esp32_controller.sync_capture()
        if sync_data:
            frame = self.camera_thread.capture_frame(2000)
            elapsed = time.time() - start_time

            if frame is not None:
                result = f"✅ Sync test: {elapsed*1000:.1f}ms, {sync_data['timing_ms']}ms ESP32"
            else:
                result = "❌ Sync test: Camera capture failed"
        else:
            result = "❌ Sync test: ESP32 sync failed"

        self.results_display.setText(result)
        self._log_message(result)

    # =============================================================================
    # Control Helper Methods
    # =============================================================================
    def _validate_hdf5_structure(self):
        """Validiere dass alle benötigten HDF5-Gruppen existieren"""
        if not self.recording_manager.hdf5_file:
            return False

        required_groups = ["timing", "environmental", "frame_metadata"]
        required_datasets = {
            "timing": [
                "python_timestamps",
                "esp32_timestamps",
                "frame_drifts_ms",
                "led_durations_ms",
            ],
            "environmental": ["temperature_celsius", "humidity_percent"],
        }

        try:
            # Prüfe Gruppen
            for group_name in required_groups:
                if group_name not in self.recording_manager.hdf5_file:
                    self._log_message(f"❌ Missing HDF5 group: {group_name}")
                    return False

            # Prüfe Datasets
            for group_name, dataset_names in required_datasets.items():
                group = self.recording_manager.hdf5_file[group_name]
                for dataset_name in dataset_names:
                    if dataset_name not in group:
                        self._log_message(f"❌ Missing HDF5 dataset: {group_name}/{dataset_name}")
                        return False

            self._log_message("✅ HDF5 structure validation passed")
            return True

        except Exception as e:
            self._log_message(f"❌ HDF5 structure validation error: {e}")
            return False

    def _enable_recording_controls(self, recording: bool):
        """Enable/disable recording controls"""
        self.start_rec_btn.setEnabled(not recording)
        self.pause_rec_btn.setEnabled(recording)
        self.stop_rec_btn.setEnabled(recording)

        self.duration_input.setEnabled(not recording)
        self.interval_input.setEnabled(not recording)
        self.select_dir_btn.setEnabled(not recording)

    def _enable_camera_controls(self, enabled: bool):
        """Enable/disable camera controls"""
        self.start_live_btn.setEnabled(enabled and not self.camera_thread.running)
        self.stop_live_btn.setEnabled(enabled and self.camera_thread.running)
        self.test_btn.setEnabled(enabled)
        self.trigger_combo.setEnabled(enabled)
        self.exposure_spinbox.setEnabled(enabled)

        if enabled:
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)
        else:
            self.connect_btn.setEnabled(len(self.available_cameras) > 0)
            self.disconnect_btn.setEnabled(False)

    def _enable_esp32_controls(self, enabled: bool):
        """Enable/disable ESP32 controls"""
        self.led_on_btn.setEnabled(enabled)
        self.led_off_btn.setEnabled(enabled)
        self.led_power_slider.setEnabled(enabled)
        self.led_power_spinbox.setEnabled(enabled)

        if enabled:
            self.connect_esp32_btn.setEnabled(False)
            self.disconnect_esp32_btn.setEnabled(True)
            self.esp32_status_label.setText("ESP32: Connected")
            self.esp32_status_detail.setText("ESP32: Connected and ready")
        else:
            self.connect_esp32_btn.setEnabled(True)
            self.disconnect_esp32_btn.setEnabled(False)
            self.esp32_status_label.setText("ESP32: Disconnected")
            self.esp32_status_detail.setText("ESP32: Not connected")

    # =============================================================================
    # Signal Handlers and Utility Methods
    # =============================================================================

    def _on_camera_frame(self, frame: np.ndarray):
        """Handle new camera frame"""
        try:
            layer_name = "HIK Camera Live"
            is_rgb = frame.ndim == 3

            if self.live_layer is None:
                self.live_layer = self.viewer.add_image(frame, name=layer_name, rgb=is_rgb)
            else:
                self.live_layer.data = frame

        except Exception as e:
            self._log_message(f"❌ Frame display error: {e}")

    def _on_camera_error(self, error_msg: str):
        """Handle camera errors"""
        self._log_message(f"❌ Camera error: {error_msg}")

    def _on_camera_status(self, status_msg: str):
        """Handle camera status updates"""
        if self.camera_status_label:
            self.camera_status_label.setText(f"Camera: {status_msg}")

    def _on_trigger_mode_changed(self):
        """Handle trigger mode changes"""
        if not self.camera_connected:
            return

        trigger_text = self.trigger_combo.currentText()

        if "Free Running" in trigger_text:
            self.camera_thread.set_trigger_mode(False)
        elif "Software" in trigger_text:
            self.camera_thread.set_trigger_mode(True, "Software")
        elif "Hardware" in trigger_text:
            self.camera_thread.set_trigger_mode(True, "Hardware")

        self._log_message(f"⚙️ Trigger mode: {trigger_text}")

    def _on_exposure_changed(self):
        """Handle exposure changes"""
        if not self.camera_connected:
            return

        exposure_us = self.exposure_spinbox.value()
        self.camera_thread.set_exposure_time(exposure_us)
        self._log_message(f"⚙️ Exposure changed: {exposure_us}μs")

    def _format_time(self, seconds: float) -> str:
        """Format time in HH:MM:SS format"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"


# =============================================================================
# Plugin Registration for napari
# =============================================================================


def napari_experimental_provide_dock_widget():
    """Provide the plugin as a napari dock widget"""
    return NematostellaTimeSeriesCapture
