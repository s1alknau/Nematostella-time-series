# """Fixed napari plugin widget for timelapse recording - NO MOCK MODE."""

# import napari
# from qtpy.QtWidgets import (
#     QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
#     QPushButton, QLabel, QSpinBox, QCheckBox,
#     QLineEdit, QTextEdit, QProgressBar, QGroupBox,
#     QSlider, QFileDialog
# )
# from qtpy.QtCore import QTimer, QObject
# try:
#     from qtpy.QtCore import pyqtSignal
# except ImportError:
#     from qtpy.QtCore import Signal as pyqtSignal

# import time
# import os
# import numpy as np
# from pathlib import Path
# from typing import Tuple

# def get_imswitch_main():
#     """Get ImSwitch main controller from global context - SAFE VERSION."""
#     import sys
#     import gc

#     print("=== ImSwitch Detection Debug ===")

#     # Method 1: Look for ImSwitch in sys.modules
#     print("Method 1: Checking sys.modules...")
#     imswitch_modules = [name for name in sys.modules.keys() if 'imswitch' in name.lower()]
#     print(f"Found ImSwitch modules: {imswitch_modules}")

#     for module_name in imswitch_modules:
#         try:
#             module = sys.modules[module_name]
#             print(f"Checking module: {module_name}")

#             # Check for main_controller attribute
#             if hasattr(module, 'main_controller'):
#                 print(f"Found main_controller in {module_name}")
#                 return module.main_controller

#             # Check for other common controller names
#             controller_names = ['mainController', 'controller', 'main', '_main_controller']
#             for controller_name in controller_names:
#                 if hasattr(module, controller_name):
#                     controller = getattr(module, controller_name)
#                     try:
#                         if (hasattr(controller, 'detectorsManager') and
#                             hasattr(controller, 'liveViewWidget')):
#                             print(f"Found ImSwitch controller in {module_name}.{controller_name}")
#                             return controller
#                     except:
#                         continue
#         except Exception as e:
#             print(f"Error checking module {module_name}: {e}")
#             continue

#     # Method 2: Search through garbage collector (SAFE VERSION)
#     print("Method 2: Searching garbage collector...")
#     try:
#         for obj in gc.get_objects():
#             try:
#                 # Only check objects that look like they could be ImSwitch
#                 obj_type = str(type(obj))
#                 if 'imswitch' in obj_type.lower() or 'main' in obj_type.lower():
#                     if (hasattr(obj, 'detectorsManager') and
#                         hasattr(obj, 'liveViewWidget')):
#                         print(f"Found ImSwitch controller via GC: {type(obj)}")
#                         return obj
#             except Exception:
#                 # Skip problematic objects silently
#                 continue
#     except Exception as e:
#         print(f"GC search failed: {e}")

#     print("ImSwitch controller not found")
#     return None
# class NematostallTimelapseCaptureWidget(QWidget):
#     """Main widget for Nematostella timelapse capture - NO MOCK MODE."""

#     def __init__(self, napari_viewer=None, imswitch_main_controller=None):
#         super().__init__()

#         # ✅ DEBUG: Check napari viewer
#         print(f"Widget init: napari_viewer = {type(napari_viewer) if napari_viewer else None}")
#         print(f"Widget init: viewer layers = {len(napari_viewer.layers) if napari_viewer else 'No viewer'}")

#         self.viewer = napari_viewer

#         # ✅ AUTO-DETECT IMSWITCH if not provided
#         if imswitch_main_controller is None:
#             imswitch_main_controller = get_imswitch_main()
#             if imswitch_main_controller:
#                 print("SUCCESS: ImSwitch auto-detected!")

#         self.imswitch_main = imswitch_main_controller
#         self.setWindowTitle("Nematostella Time-Series Capture")
#         self.setMinimumWidth(800)
#         self.setMinimumHeight(600)

#         # Camera info direkt von ImSwitch
#         self.camera_name = "HikCamera"
#         self.camera_connected = False

#         # ✅ UI ZUERST setuppen
#         self._setup_ui()

#         # Import real controllers - NO FALLBACKS
#         self._initialize_controllers()

#         # State variables
#         self.recording = False

#         # Setup connections and timers
#         self._setup_connections()
#         self._setup_timers()

#     def _find_imswitch_controller(self):
#         """Try to find ImSwitch controller from running system."""
#         try:
#             print("Searching for ImSwitch controller...")
#             import gc

#             # Method 1: Search in garbage collector for ImSwitch objects
#             for obj in gc.get_objects():
#                 if (hasattr(obj, 'detectorsManager') and
#                     hasattr(obj, 'liveViewWidget') and
#                     hasattr(obj, 'getState')):
#                     print(f"Found ImSwitch controller: {type(obj)}")
#                     return obj

#             # Method 2: Try napari viewer connections
#             if self.viewer is not None:
#                 # Check if napari has any ImSwitch-related objects
#                 for widget in getattr(self.viewer.window, '_dock_widgets', []):
#                     if hasattr(widget, 'imswitch_main'):
#                         print("Found ImSwitch through napari dock widget")
#                         return widget.imswitch_main

#             # Method 3: Try module-level search
#             import sys
#             for module_name, module in sys.modules.items():
#                 if 'imswitch' in module_name.lower():
#                     for attr_name in dir(module):
#                         attr = getattr(module, attr_name, None)
#                         if (hasattr(attr, 'detectorsManager') and
#                             hasattr(attr, 'liveViewWidget')):
#                             print(f"Found ImSwitch in module: {module_name}")
#                             return attr

#             print("ImSwitch controller not found - will run without camera")
#             return None

#         except Exception as e:
#             print(f"ImSwitch auto-detection failed: {e}")
#             return None

#     def _initialize_controllers(self):
#         """Initialize real controllers - no mock fallbacks."""
#         try:
#             from ._esp32_controller import ESP32Controller
#             from ._data_manager import DataManager

#             # Initialize real controllers
#             self.esp32_controller = ESP32Controller(self.imswitch_main)
#             self.data_manager = DataManager()
#             self.recorder = None

#             # Check camera connection through ImSwitch
#             self.camera_connected = self._check_camera_connection()

#             self._add_log_entry("Real controllers initialized successfully")

#             # Test ESP32 connection on startup
#             if self.esp32_controller.esp32_port:
#                 self._add_log_entry(f"ESP32 port detected: {self.esp32_controller.esp32_port}")
#             else:
#                 self._add_log_entry("Warning: No ESP32 port detected")

#             # Log ImSwitch status
#             if self.imswitch_main is not None:
#                 self._add_log_entry("ImSwitch controller found and connected!")
#             else:
#                 self._add_log_entry("ImSwitch not found - running without camera")

#         except ImportError as e:
#             error_msg = f"CRITICAL: Cannot import required modules: {str(e)}"
#             self._add_log_entry(error_msg)
#             raise RuntimeError(error_msg)
#         except Exception as e:
#             error_msg = f"CRITICAL: Controller initialization failed: {str(e)}"
#             self._add_log_entry(error_msg)
#             raise RuntimeError(error_msg)

#     def _add_log_entry(self, message):
#         """Add entry to system log."""
#         if not hasattr(self, 'log_text') or self.log_text is None:
#             print(f"LOG: {message}")
#             return

#         import datetime
#         now = datetime.datetime.now()
#         timestamp = now.strftime("[%H:%M:%S.%f")[:-3] + "]"
#         log_entry = f"<span style='color: #00ff00;'>{timestamp}</span> {message}"
#         self.log_text.append(log_entry)

#     # def _check_camera_connection(self) -> bool:
#     #     """Check if camera is available through ImSwitch OR napari live layer."""

#     #     # Method 1: Try ImSwitch detection (existing code)
#     #     if self.imswitch_main is not None:
#     #         try:
#     #             if hasattr(self.imswitch_main, 'detectorsManager'):
#     #                 detectors_manager = self.imswitch_main.detectorsManager

#     #                 available_detectors = []
#     #                 if hasattr(detectors_manager, 'getAllDeviceNames'):
#     #                     available_detectors = detectors_manager.getAllDeviceNames()
#     #                 elif hasattr(detectors_manager, 'getAllDetectorNames'):
#     #                     available_detectors = detectors_manager.getAllDetectorNames()

#     #                 if available_detectors:
#     #                     print(f"Available cameras: {available_detectors}")
#     #                     self.camera_name = available_detectors[0]
#     #                     self._add_log_entry(f"Using camera: {self.camera_name}")
#     #                     return True
#     #         except Exception as e:
#     #             print(f"ImSwitch camera check failed: {e}")

#     #     # Method 2: Try napari live layer detection
#     #     try:
#     #         # Auto-detect napari viewer if not available
#     #         if self.viewer is None:
#     #             import napari
#     #             current_viewer = napari.current_viewer()
#     #             if current_viewer is not None:
#     #                 self.viewer = current_viewer
#     #                 print("Auto-detected napari viewer")

#     #         if self.viewer is not None:
#     #             from napari.layers import Image
#     #             live_layer_found = False

#     #             for layer in self.viewer.layers:
#     #                 if not isinstance(layer, Image):
#     #                     continue

#     #                 # Check if layer has data
#     #                 data = getattr(layer, 'data', None)
#     #                 if data is None or (hasattr(data, 'size') and data.size == 0):
#     #                     continue

#     #                 # Check for live view indicators in layer name
#     #                 layer_name = getattr(layer, 'name', '').lower()
#     #                 live_keywords = ['live', 'widefield', 'imswitch', 'camera', 'detector']

#     #                 if any(keyword in layer_name for keyword in live_keywords):
#     #                     self._add_log_entry(f"Found live layer: {layer.name}")
#     #                     live_layer_found = True
#     #                     break

#     #             # If no specifically named live layer, any image layer counts
#     #             if not live_layer_found:
#     #                 for layer in self.viewer.layers:
#     #                     if isinstance(layer, Image):
#     #                         data = getattr(layer, 'data', None)
#     #                         if data is not None and not (hasattr(data, 'size') and data.size == 0):
#     #                             self._add_log_entry(f"Found image layer: {layer.name}")
#     #                             live_layer_found = True
#     #                             break

#     #             if live_layer_found:
#     #                 self._add_log_entry("Camera available via napari live layer")
#     #                 return True

#     #     except Exception as e:
#     #         print(f"Napari layer detection failed: {e}")

#     #     self._add_log_entry("No camera source available")
#     #     return False
#     def _check_camera_connection(self) -> bool:
#         """Simple check: Is ANY camera source ready for recording?"""

#         camera_ready = False
#         camera_source = "Unknown"

#         print("DEBUG: Checking camera connection...")  # ✅ Debug output

#         # Quick test: Try to capture a frame from any available source
#         try:
#             # Method 1: Try Napari live layer (fastest)
#             if self.viewer is not None:
#                 print(f"DEBUG: Checking {len(self.viewer.layers)} napari layers...")
#                 from napari.layers import Image
#                 for layer in self.viewer.layers:
#                     if isinstance(layer, Image):
#                         data = getattr(layer, 'data', None)
#                         if data is not None and data.size > 0:
#                             camera_ready = True
#                             camera_source = f"napari:{layer.name}"
#                             print(f"DEBUG: Found camera source: {camera_source}")
#                             break
#             else:
#                 print("DEBUG: No napari viewer available")

#             # Method 2: Try ImSwitch if Napari didn't work
#             if not camera_ready and self.imswitch_main is not None:
#                 print("DEBUG: Trying ImSwitch LiveView...")
#                 if hasattr(self.imswitch_main, 'liveViewWidget'):
#                     live_view = self.imswitch_main.liveViewWidget
#                     if hasattr(live_view, 'img') and live_view.img is not None:
#                         camera_ready = True
#                         camera_source = "ImSwitch LiveView"
#                         print(f"DEBUG: Found camera source: {camera_source}")
#             else:
#                 print("DEBUG: No ImSwitch available")

#         except Exception as e:
#             print(f"DEBUG: Camera check failed: {e}")
#             camera_ready = False

#         print(f"DEBUG: Camera ready = {camera_ready}, source = {camera_source}")

#         # Update status labels if they exist
#         if hasattr(self, 'camera_status_label') and self.camera_status_label is not None:
#             if camera_ready:
#                 self.camera_status_label.setText(f"Camera: Ready ({camera_source})")
#                 self.camera_status_label.setStyleSheet("color: #00ff00;")
#                 print(f"DEBUG: Updated camera status to Ready ({camera_source})")
#             else:
#                 self.camera_status_label.setText("Camera: Not Ready")
#                 self.camera_status_label.setStyleSheet("color: #ff0000;")
#                 print("DEBUG: Updated camera status to Not Ready")

#         return camera_ready

#     # def _capture_frame_from_imswitch(self) -> Tuple[np.ndarray, dict]:
#     #     """Simple frame capture for testing (widget only)."""
#     #     if self.imswitch_main is None:
#     #         raise RuntimeError("ImSwitch not available")

#     #     try:
#     #         # Method 1: Try live view widget (most common)
#     #         if hasattr(self.imswitch_main, 'liveViewWidget'):
#     #             live_view = self.imswitch_main.liveViewWidget
#     #             if hasattr(live_view, 'img') and live_view.img is not None:
#     #                 frame = live_view.img.copy()
#     #                 print(f"Widget: Got frame from live view: {frame.shape} {frame.dtype}")
#     #                 metadata = {
#     #                     "timestamp": time.time(),
#     #                     "camera_name": self.camera_name,
#     #                     "frame_shape": frame.shape,
#     #                     "frame_dtype": str(frame.dtype),
#     #                     "source": "widget_quick_test"
#     #                 }
#     #                 return frame, metadata

#     #         # Method 2: Try view widget
#     #         if hasattr(self.imswitch_main, 'viewWidget'):
#     #             view_widget = self.imswitch_main.viewWidget
#     #             if hasattr(view_widget, 'getCurrentImage'):
#     #                 frame = view_widget.getCurrentImage()
#     #                 if frame is not None:
#     #                     print(f"Widget: Got frame from viewWidget: {frame.shape}")
#     #                     metadata = {
#     #                         "timestamp": time.time(),
#     #                         "camera_name": self.camera_name,
#     #                         "frame_shape": frame.shape,
#     #                         "frame_dtype": str(frame.dtype),
#     #                         "source": "widget_view_widget"
#     #                     }
#     #                     return frame, metadata

#     #         # Method 3: Simple detector manager fallback
#     #         if hasattr(self.imswitch_main, 'detectorsManager'):
#     #             detectors_manager = self.imswitch_main.detectorsManager
#     #             if hasattr(detectors_manager, 'getLatestFrame'):
#     #                 try:
#     #                     frame = detectors_manager.getLatestFrame(self.camera_name)
#     #                     if frame is not None:
#     #                         print(f"Widget: Got frame from detector manager: {frame.shape}")
#     #                         metadata = {
#     #                             "timestamp": time.time(),
#     #                             "camera_name": self.camera_name,
#     #                             "frame_shape": frame.shape,
#     #                             "frame_dtype": str(frame.dtype),
#     #                             "source": "widget_detector_manager"
#     #                         }
#     #                         return frame, metadata
#     #                 except Exception as e:
#     #                     print(f"Widget: Detector manager failed: {e}")

#     #         raise RuntimeError("Could not get frame for quick test")

#     #     except Exception as e:
#     #         raise RuntimeError(f"Widget frame capture failed: {str(e)}")
#     # def _capture_frame_from_imswitch(self) -> Tuple[np.ndarray, dict]:
#     #     """TEMP MOCK - Test HDF5 saving with dummy frame."""
#     #     # MOCK VERSION - Create dummy frame for testing HDF5 saving
#     #     dummy_frame = np.random.randint(0, 1000, (1024, 1280), dtype=np.uint16)
#     #     metadata = {
#     #         "timestamp": time.time(),
#     #         "camera_name": self.camera_name,
#     #         "frame_shape": dummy_frame.shape,
#     #         "frame_dtype": str(dummy_frame.dtype),
#     #         "source": "MOCK_TEST_FRAME"
#     #     }
#     #     print(f"MOCK: Created dummy frame {dummy_frame.shape}")
#     #     return dummy_frame, metadata

#     def _setup_ui(self):
#         """Setup the user interface."""
#         layout = QHBoxLayout()

#         # Left panel
#         left_panel = self._create_left_panel()
#         layout.addWidget(left_panel, stretch=2)

#         # Right panel
#         right_panel = self._create_right_panel()
#         layout.addWidget(right_panel, stretch=1)

#         self.setLayout(layout)

#     def _create_left_panel(self):
#         """Create the left control panel."""
#         widget = QWidget()
#         layout = QVBoxLayout()

#         # Tab widget
#         tabs = QTabWidget()

#         # Camera tab
#         camera_tab = self._create_camera_tab()
#         tabs.addTab(camera_tab, "File Management")

#         # Recording tab
#         recording_tab = self._create_recording_tab()
#         tabs.addTab(recording_tab, "Recording")

#         # ESP32 tab
#         esp32_tab = self._create_esp32_tab()
#         tabs.addTab(esp32_tab, "ESP32 Control")

#         # Diagnostics tab
#         diagnostics_tab = self._create_diagnostics_tab()
#         tabs.addTab(diagnostics_tab, "Diagnostics")

#         layout.addWidget(tabs)
#         widget.setLayout(layout)
#         return widget

#     def _create_camera_tab(self):
#         """Create camera control tab."""
#         widget = QWidget()
#         layout = QVBoxLayout()

#         # ImSwitch Info
#         imswitch_group = QGroupBox("ImSwitch Camera Info")
#         imswitch_layout = QVBoxLayout()

#         self.camera_info_label = QLabel(f"Camera: {self.camera_name}")
#         self.imswitch_status_label = QLabel("ImSwitch: Not Connected")

#         imswitch_layout.addWidget(self.camera_info_label)
#         imswitch_layout.addWidget(self.imswitch_status_label)
#         imswitch_group.setLayout(imswitch_layout)

#         # File Management
#         file_group = QGroupBox("File Management")
#         file_layout = QVBoxLayout()

#         dir_layout = QHBoxLayout()
#         self.directory_edit = QLineEdit()
#         self.directory_edit.setPlaceholderText("Select Directory")
#         dir_button = QPushButton("📁 Select Directory")
#         dir_button.clicked.connect(self._select_directory)
#         dir_layout.addWidget(self.directory_edit)
#         dir_layout.addWidget(dir_button)

#         self.timestamp_checkbox = QCheckBox("Create timestamped subfolder")
#         self.timestamp_checkbox.setChecked(True)

#         file_layout.addLayout(dir_layout)
#         file_layout.addWidget(self.timestamp_checkbox)
#         file_group.setLayout(file_layout)

#         # layout.addWidget(imswitch_group)
#         layout.addWidget(file_group)
#         layout.addStretch()
#         widget.setLayout(layout)
#         return widget

#     def _create_recording_tab(self):
#         """Create recording control tab."""
#         widget = QWidget()
#         layout = QVBoxLayout()

#         # Recording Parameters
#         params_group = QGroupBox("Recording Parameters")
#         params_layout = QVBoxLayout()

#         # Duration and Interval
#         duration_layout = QHBoxLayout()
#         duration_layout.addWidget(QLabel("Duration (min):"))
#         self.duration_spinbox = QSpinBox()
#         self.duration_spinbox.setRange(1, 10000)
#         self.duration_spinbox.setValue(1)
#         duration_layout.addWidget(self.duration_spinbox)

#         duration_layout.addWidget(QLabel("Interval (sec):"))
#         self.interval_spinbox = QSpinBox()
#         self.interval_spinbox.setRange(1, 3600)
#         self.interval_spinbox.setValue(5)
#         duration_layout.addWidget(self.interval_spinbox)

#         # Expected frames
#         expected_layout = QHBoxLayout()
#         expected_layout.addWidget(QLabel("Expected Frames:"))
#         self.expected_frames_label = QLabel("12")
#         expected_layout.addWidget(self.expected_frames_label)
#         expected_layout.addStretch()

#         params_layout.addLayout(duration_layout)
#         params_layout.addLayout(expected_layout)

#         # Statistics
#         self.frames_label = QLabel("● Frames: 12")
#         self.duration_label = QLabel("● Duration: 1.0 min")
#         self.intervals_label = QLabel("● Intervals: 5.0 sec")

#         params_layout.addWidget(self.frames_label)
#         params_layout.addWidget(self.duration_label)
#         params_layout.addWidget(self.intervals_label)
#         params_group.setLayout(params_layout)

#         # Recording Control
#         control_group = QGroupBox("Recording Control")
#         control_layout = QVBoxLayout()

#         # Progress bar
#         self.progress_bar = QProgressBar()
#         self.progress_bar.setValue(0)

#         # Frame info
#         frame_layout = QHBoxLayout()
#         self.frame_info_label = QLabel("Frame: 0/12")
#         self.elapsed_label = QLabel("Elapsed: 00:00:00")
#         self.eta_label = QLabel("ETA: 00:00:00")

#         frame_layout.addWidget(self.frame_info_label)
#         frame_layout.addWidget(self.elapsed_label)
#         frame_layout.addWidget(self.eta_label)

#         # Control buttons
#         button_layout = QHBoxLayout()
#         self.start_button = QPushButton("🎬 Start Recording")
#         self.pause_button = QPushButton("⏸ Pause")
#         self.stop_button = QPushButton("⏹ Stop")

#         self.start_button.clicked.connect(self._start_recording)
#         self.pause_button.clicked.connect(self._pause_recording)
#         self.stop_button.clicked.connect(self._stop_recording)

#         button_layout.addWidget(self.start_button)
#         button_layout.addWidget(self.pause_button)
#         button_layout.addWidget(self.stop_button)

#         control_layout.addWidget(self.progress_bar)
#         control_layout.addLayout(frame_layout)
#         control_layout.addLayout(button_layout)
#         control_group.setLayout(control_layout)

#         layout.addWidget(params_group)
#         layout.addWidget(control_group)
#         layout.addStretch()
#         widget.setLayout(layout)
#         return widget

#     def _create_esp32_tab(self):
#         """Create ESP32 control tab."""
#         widget = QWidget()
#         layout = QVBoxLayout()

#         # ESP32 Connection
#         connection_group = QGroupBox("ESP32 Connection")
#         conn_layout = QVBoxLayout()

#         conn_button_layout = QHBoxLayout()
#         self.connect_esp32_button = QPushButton("🔗 Connect ESP32")
#         self.disconnect_esp32_button = QPushButton("❌ Disconnect")

#         self.connect_esp32_button.clicked.connect(self._connect_esp32)
#         self.disconnect_esp32_button.clicked.connect(self._disconnect_esp32)

#         conn_button_layout.addWidget(self.connect_esp32_button)
#         conn_button_layout.addWidget(self.disconnect_esp32_button)

#         self.esp32_status_label = QLabel("ESP32: Disconnected")

#         conn_layout.addLayout(conn_button_layout)
#         conn_layout.addWidget(self.esp32_status_label)
#         connection_group.setLayout(conn_layout)

#         # LED Control
#         led_group = QGroupBox("LED Control")
#         led_layout = QVBoxLayout()

#         # LED Power slider
#         power_layout = QHBoxLayout()
#         power_layout.addWidget(QLabel("LED Power:"))
#         self.led_power_slider = QSlider()
#         self.led_power_slider.setOrientation(1)  # Horizontal
#         self.led_power_slider.setRange(0, 100)
#         self.led_power_slider.setValue(100)
#         self.led_power_value_label = QLabel("100%")

#         power_layout.addWidget(self.led_power_slider)
#         power_layout.addWidget(self.led_power_value_label)

#         # LED buttons
#         led_button_layout = QHBoxLayout()
#         self.led_on_button = QPushButton("💡 LED ON (100%)")
#         self.led_off_button = QPushButton("🌑 LED OFF")

#         self.led_on_button.clicked.connect(self._led_on)
#         self.led_off_button.clicked.connect(self._led_off)

#         led_button_layout.addWidget(self.led_on_button)
#         led_button_layout.addWidget(self.led_off_button)

#         # Test buttons
#         test_layout = QHBoxLayout()
#         self.manual_flash_button = QPushButton("⚡ Manual Flash")
#         self.read_sensors_button = QPushButton("📊 Read Sensors")

#         self.manual_flash_button.clicked.connect(self._manual_flash)
#         self.read_sensors_button.clicked.connect(self._read_sensors)

#         test_layout.addWidget(self.manual_flash_button)
#         test_layout.addWidget(self.read_sensors_button)

#         led_layout.addLayout(power_layout)
#         led_layout.addLayout(led_button_layout)
#         led_layout.addLayout(test_layout)
#         led_group.setLayout(led_layout)

#         # Environmental Sensors
#         sensor_group = QGroupBox("Environmental Sensors")
#         sensor_layout = QVBoxLayout()

#         sensor_readings_layout = QHBoxLayout()
#         sensor_readings_layout.addWidget(QLabel("Temperature:"))
#         self.temperature_label = QLabel("--°C")
#         sensor_readings_layout.addWidget(self.temperature_label)

#         sensor_readings_layout.addWidget(QLabel("Humidity:"))
#         self.humidity_label = QLabel("--%")
#         sensor_readings_layout.addWidget(self.humidity_label)

#         sensor_layout.addLayout(sensor_readings_layout)
#         sensor_group.setLayout(sensor_layout)

#         layout.addWidget(connection_group)
#         layout.addWidget(led_group)
#         layout.addWidget(sensor_group)
#         layout.addStretch()
#         widget.setLayout(layout)
#         return widget

#     def _create_diagnostics_tab(self):
#         """Create diagnostics tab."""
#         widget = QWidget()
#         layout = QVBoxLayout()

#         # System Diagnostics
#         diag_group = QGroupBox("System Diagnostics")
#         diag_layout = QVBoxLayout()

#         test_button_layout = QHBoxLayout()
#         self.test_full_button = QPushButton("🔧 Test Full System")
#         self.quick_test_button = QPushButton("Quick Frame Test")

#         # Debug buttons
#         self.debug_esp32_button = QPushButton("🔍 Debug ESP32")
#         self.debug_imswitch_button = QPushButton("🔍 Debug ImSwitch")

#         self.debug_esp32_button.setStyleSheet("""
#             QPushButton {
#                 background-color: #ff0066;
#                 color: white;
#                 font-weight: bold;
#                 padding: 8px;
#             }
#         """)

#         self.debug_imswitch_button.setStyleSheet("""
#             QPushButton {
#                 background-color: #0066ff;
#                 color: white;
#                 font-weight: bold;
#                 padding: 8px;
#             }
#         """)

#         self.debug_esp32_button.clicked.connect(self._debug_esp32_communication)
#         self.debug_imswitch_button.clicked.connect(self._debug_imswitch_structure)

#         self.test_full_button.clicked.connect(self._test_full_system)
#         self.quick_test_button.clicked.connect(self._quick_frame_test)

#         self.quick_test_button.setStyleSheet("""
#             QPushButton {
#                 background-color: #ff6600;
#                 color: white;
#                 font-weight: bold;
#                 padding: 8px;
#             }
#         """)

#         test_button_layout.addWidget(self.test_full_button)
#         test_button_layout.addWidget(self.quick_test_button)
#         test_button_layout.addWidget(self.debug_esp32_button)
#         test_button_layout.addWidget(self.debug_imswitch_button)

#         # Test metrics
#         metrics_layout = QHBoxLayout()
#         self.fps_label = QLabel("FPS: --")
#         self.dropped_label = QLabel("Dropped: 0")

#         metrics_layout.addWidget(self.fps_label)
#         metrics_layout.addWidget(self.dropped_label)
#         metrics_layout.addStretch()

#         diag_layout.addLayout(test_button_layout)
#         diag_layout.addLayout(metrics_layout)
#         diag_group.setLayout(diag_layout)

#         # Test Results
#         results_group = QGroupBox("Test Results")
#         results_layout = QVBoxLayout()

#         self.test_results_text = QTextEdit()
#         self.test_results_text.setReadOnly(True)
#         self.test_results_text.setMaximumHeight(200)

#         results_layout.addWidget(self.test_results_text)
#         results_group.setLayout(results_layout)

#         layout.addWidget(diag_group)
#         layout.addWidget(results_group)
#         layout.addStretch()
#         widget.setLayout(layout)
#         return widget

#     def _create_right_panel(self):
#         """Create the right status panel."""
#         widget = QWidget()
#         layout = QVBoxLayout()

#         # System Status
#         status_group = QGroupBox("System Status")
#         status_layout = QVBoxLayout()

#         self.camera_status_label = QLabel("Camera: Not Connected")
#         self.esp32_status_label_right = QLabel("ESP32: Disconnected")
#         self.recording_status_label = QLabel("Recording: Ready")

#         status_layout.addWidget(self.camera_status_label)
#         status_layout.addWidget(self.esp32_status_label_right)
#         status_layout.addWidget(self.recording_status_label)
#         status_group.setLayout(status_layout)

#         # System Log
#         log_group = QGroupBox("System Log")
#         log_layout = QVBoxLayout()

#         self.log_text = QTextEdit()
#         self.log_text.setReadOnly(True)
#         self.log_text.setMaximumHeight(300)

#         log_layout.addWidget(self.log_text)
#         log_group.setLayout(log_layout)

#         layout.addWidget(status_group)
#         layout.addWidget(log_group)
#         layout.addStretch()
#         widget.setLayout(layout)
#         return widget

#     def _setup_connections(self):
#         """Setup signal connections."""
#         # UI connections (always available)
#         self.duration_spinbox.valueChanged.connect(self._update_expected_frames)
#         self.interval_spinbox.valueChanged.connect(self._update_expected_frames)
#         self.led_power_slider.valueChanged.connect(self._update_led_power)

#         # DataManager connections (always available)
#         self.data_manager.file_created.connect(self._on_file_created)
#         self.data_manager.frame_saved.connect(self._on_frame_saved)
#         self.data_manager.metadata_updated.connect(self._on_metadata_updated)

#         # ESP32 controller connections (always available)
#         self.esp32_controller.connection_status_changed.connect(self._on_esp32_conn_changed)
#         self.esp32_controller.led_status_changed.connect(self._on_led_status_changed)

#         # NOTE: Recorder connections will be set up when recorder is created

#     def _setup_timers(self):
#         """Setup periodic timers."""
#         self.status_timer = QTimer()
#         self.status_timer.timeout.connect(self._update_status)
#         self.status_timer.start(2000)

#         # Add initial log entries
#         self._add_log_entry("Plugin initialized successfully (NO MOCK MODE)")
#         if self.imswitch_main is None:
#             self._add_log_entry("ImSwitch not available - trying auto-detection...")
#             # Try one more time to find ImSwitch
#             self.imswitch_main = self._find_imswitch_controller()
#             if self.imswitch_main:
#                 self._add_log_entry("SUCCESS: ImSwitch auto-detected on retry!")
#                 # Update camera connection status
#                 self.camera_connected = self._check_camera_connection()
#         else:
#             self._add_log_entry("ImSwitch integration active")

#     # =========================================================================
#     # EVENT HANDLERS
#     # =========================================================================

#     def _select_directory(self):
#         """Select recording directory."""
#         directory = QFileDialog.getExistingDirectory(self, "Select Recording Directory")
#         if directory:
#             self.directory_edit.setText(directory)
#             self._add_log_entry(f"Recording directory set: {directory}")

#     def _update_expected_frames(self):
#         """Update expected frames calculation."""
#         duration_min = self.duration_spinbox.value()
#         interval_sec = self.interval_spinbox.value()

#         total_seconds = duration_min * 60
#         expected_frames = total_seconds // interval_sec

#         self.expected_frames_label.setText(str(expected_frames))
#         self.frames_label.setText(f"● Frames: {expected_frames}")
#         self.duration_label.setText(f"● Duration: {duration_min}.0 min")
#         self.intervals_label.setText(f"● Intervals: {interval_sec}.0 sec")

#     def _update_led_power(self):
#         """Update LED power display."""
#         power = self.led_power_slider.value()
#         self.led_power_value_label.setText(f"{power}%")
#         self.led_on_button.setText(f"💡 LED ON ({power}%)")

#         try:
#             if self.esp32_controller.is_connected():
#                 self.esp32_controller.set_led_power(power)
#                 self.esp32_status_label.setText(f"ESP32: Connected - LED Power: {power}%")
#         except Exception as e:
#             self._add_log_entry(f"LED power update failed: {e}")

#     def _connect_esp32(self):
#         """Connect to ESP32."""
#         try:
#             success = self.esp32_controller.connect()
#             if success:
#                 status = self.esp32_controller.get_status()
#                 self._add_log_entry("ESP32 connected successfully")
#                 self._add_log_entry(f"ESP32 Status: {status}")
#                 self.esp32_status_label.setText("ESP32: Connected - LED Power: 100%")
#                 self.esp32_status_label_right.setText("ESP32: Connected")
#             else:
#                 self._add_log_entry("ESP32 connection failed")
#                 self.esp32_status_label.setText("ESP32: Connection Failed")
#                 self.esp32_status_label_right.setText("ESP32: Disconnected")
#         except Exception as e:
#             self._add_log_entry(f"ESP32 connection error: {str(e)}")
#             self.esp32_status_label.setText("ESP32: Error")
#             self.esp32_status_label_right.setText("ESP32: Error")

#     def _disconnect_esp32(self):
#         """Disconnect from ESP32."""
#         try:
#             self.esp32_controller.disconnect()
#             self._add_log_entry("ESP32 disconnected")
#             self.esp32_status_label.setText("ESP32: Disconnected")
#             self.esp32_status_label_right.setText("ESP32: Disconnected")
#         except Exception as e:
#             self._add_log_entry(f"ESP32 disconnect error: {e}")

#     def _led_on(self):
#         """Turn LED on."""
#         try:
#             self.esp32_controller.led_on()
#             self._add_log_entry(f"LED command sent: ON at {self.led_power_slider.value()}%")
#         except Exception as e:
#             self._add_log_entry(f"LED on failed: {str(e)}")

#     def _led_off(self):
#         """Turn LED off."""
#         try:
#             self.esp32_controller.led_off()
#             self._add_log_entry("LED command sent: OFF")
#         except Exception as e:
#             self._add_log_entry(f"LED off failed: {str(e)}")

#     def _manual_flash(self):
#         """Manual LED flash."""
#         try:
#             timing_info = self.esp32_controller.synchronize_capture()
#             temp = timing_info.get('temperature', 0)
#             humidity = timing_info.get('humidity', 0)
#             duration = timing_info.get('led_duration_actual', 0)

#             self._add_log_entry(f"Manual flash: {duration}ms, T={temp:.1f}°C, H={humidity:.1f}%")

#         except Exception as e:
#             self._add_log_entry(f"Manual flash failed: {str(e)}")

#     def _read_sensors(self):
#         """Read environmental sensors."""
#         try:
#             temp, humidity = self.esp32_controller.read_sensors()
#             self.temperature_label.setText(f"{temp:.1f}°C")
#             self.humidity_label.setText(f"{humidity:.1f}%")
#             self._add_log_entry(f"Temperature: {temp:.1f}°C, Humidity: {humidity:.1f}%")
#         except Exception as e:
#             self._add_log_entry(f"Sensor reading failed: {str(e)}")

#     def _debug_esp32_communication(self):
#         """Debug ESP32 communication step by step."""
#         self._add_log_entry("=== ESP32 COMMUNICATION DEBUG ===")
#         self.test_results_text.clear()

#         try:
#             # Check basic connection info
#             self.test_results_text.append(f"ESP32 Port: {self.esp32_controller.esp32_port}")
#             self.test_results_text.append(f"Connected: {self.esp32_controller.connected}")

#             if hasattr(self.esp32_controller, 'serial_connection') and self.esp32_controller.serial_connection:
#                 self.test_results_text.append(f"Serial Open: {self.esp32_controller.serial_connection.is_open}")
#                 self.test_results_text.append(f"Serial Port: {self.esp32_controller.serial_connection.port}")
#             else:
#                 self.test_results_text.append("No serial connection available")

#             # Test simple command
#             self._add_log_entry("Sending raw LED ON command...")
#             try:
#                 if hasattr(self.esp32_controller, '_send_byte'):
#                     self.esp32_controller._send_byte(0x01)
#                     self.test_results_text.append("✓ LED ON command sent")
#                     time.sleep(0.1)

#                     self.esp32_controller._send_byte(0x00)
#                     self.test_results_text.append("✓ LED OFF command sent")
#                 else:
#                     self.test_results_text.append("✗ _send_byte method not available")
#             except Exception as e:
#                 self.test_results_text.append(f"✗ Command send failed: {e}")

#         except Exception as e:
#             self.test_results_text.append(f"✗ Debug failed: {e}")

#     def _debug_imswitch_structure(self):
#         """Debug ImSwitch structure for widget testing."""
#         if self.imswitch_main is None:
#             self.test_results_text.append("ImSwitch not available")
#             return

#         self.test_results_text.clear()
#         self.test_results_text.append("=== ImSwitch Structure Debug ===")

#         # List main attributes
#         attrs = [attr for attr in dir(self.imswitch_main) if not attr.startswith('_')]
#         self.test_results_text.append(f"ImSwitch attributes: {', '.join(attrs[:10])}...")

#         # Check for live view attributes
#         live_attrs = ['liveViewWidget', 'viewWidget', 'imageWidget', 'detectorsManager']
#         for attr in live_attrs:
#             if hasattr(self.imswitch_main, attr):
#                 obj = getattr(self.imswitch_main, attr)
#                 self.test_results_text.append(f"✓ Found {attr}: {type(obj)}")

#                 # Check for image data attributes
#                 if hasattr(obj, 'img'):
#                     img_obj = getattr(obj, 'img', None)
#                     if img_obj is not None:
#                         shape_info = img_obj.shape if hasattr(img_obj, 'shape') else type(img_obj)
#                         self.test_results_text.append(f"  - Has image data: {shape_info}")
#                 if hasattr(obj, 'getCurrentImage'):
#                     self.test_results_text.append(f"  - Has getCurrentImage method")
#             else:
#                 self.test_results_text.append(f"✗ No {attr} found")

#         # Check napari layers if available
#         if self.viewer is not None:
#             layer_names = [layer.name for layer in self.viewer.layers]
#             self.test_results_text.append(f"Napari layers: {layer_names}")
#         else:
#             self.test_results_text.append("No napari viewer available")

#     # =========================================================================
#     # RECORDING AND TEST METHODS
#     # =========================================================================

#     def _test_full_system(self):
#         """Test full system."""
#         try:
#             self._add_log_entry("Starting system test...")
#             self.test_results_text.clear()

#             # Test ESP32
#             if self.esp32_controller.is_connected():
#                 self.test_results_text.append("✓ ESP32 connected")

#                 try:
#                     self.esp32_controller.led_on()
#                     time.sleep(0.1)
#                     self.esp32_controller.led_off()
#                     self.test_results_text.append("✓ LED control working")
#                 except Exception as e:
#                     self.test_results_text.append(f"✗ LED control failed: {e}")

#                 try:
#                     temp, humidity = self.esp32_controller.read_sensors()
#                     self.test_results_text.append(f"✓ Sensors: T={temp:.1f}°C, H={humidity:.1f}%")
#                 except Exception as e:
#                     self.test_results_text.append(f"✗ Sensor reading failed: {e}")
#             else:
#                 self.test_results_text.append("✗ ESP32 not connected")

#             # Test ImSwitch camera
#             if self.imswitch_main is not None:
#                 self.test_results_text.append("✓ ImSwitch available")
#                 try:
#                     frame, metadata = self._capture_frame_from_imswitch()
#                     self.test_results_text.append(f"✓ Camera capture: {frame.shape} {frame.dtype}")
#                     self.test_results_text.append(f"  Source: {metadata.get('source', 'unknown')}")

#                     # Display test frame in napari if available
#                     if self.viewer is not None:
#                         layer_name = "Test Frame"
#                         if layer_name in [layer.name for layer in self.viewer.layers]:
#                             layer = next(layer for layer in self.viewer.layers if layer.name == layer_name)
#                             layer.data = frame
#                         else:
#                             self.viewer.add_image(frame, name=layer_name, colormap='gray')
#                         self.test_results_text.append("✓ Frame displayed in napari")

#                 except Exception as e:
#                     self.test_results_text.append(f"✗ Camera capture failed: {e}")
#             else:
#                 self.test_results_text.append("✗ ImSwitch not available")

#             # Test data manager
#             try:
#                 info = self.data_manager.get_recording_info()
#                 self.test_results_text.append("✓ Data manager ready")
#             except Exception as e:
#                 self.test_results_text.append(f"✗ Data manager error: {e}")

#             self._add_log_entry("System test completed")

#         except Exception as e:
#             self._add_log_entry(f"System test failed: {str(e)}")
#             self.test_results_text.append(f"✗ Test failed: {str(e)}")

#     def _quick_frame_test(self):
#         """Quick frame capture test using ImSwitch directly."""
#         try:
#             self._add_log_entry("Quick frame test (ImSwitch direct)...")

#             start_time = time.time()
#             frame, metadata = self._get_live_napari_frame()
#             end_time = time.time()

#             capture_time = (end_time - start_time) * 1000  # ms
#             fps = 1.0 / (end_time - start_time) if (end_time - start_time) > 0 else 0

#             self.fps_label.setText(f"FPS: {fps:.1f}")
#             self.test_results_text.clear()
#             self.test_results_text.append(f"Frame captured in {capture_time:.1f}ms")
#             self.test_results_text.append(f"Frame shape: {frame.shape}")
#             self.test_results_text.append(f"Frame dtype: {frame.dtype}")
#             self.test_results_text.append(f"Source: {metadata.get('source', 'unknown')}")
#             self.test_results_text.append("✓ Widget frame capture working")

#             # Display in napari if available
#             if self.viewer is not None:
#                 layer_name = "Quick Test Frame"
#                 if layer_name in [layer.name for layer in self.viewer.layers]:
#                     layer = next(layer for layer in self.viewer.layers if layer.name == layer_name)
#                     layer.data = frame
#                 else:
#                     self.viewer.add_image(frame, name=layer_name, colormap='gray')
#                 self.test_results_text.append("✓ Frame displayed in napari")

#             self._add_log_entry(f"Quick test: {capture_time:.1f}ms, {fps:.1f} FPS from {metadata.get('source')}")

#         except Exception as e:
#             self._add_log_entry(f"Quick frame test failed: {str(e)}")
#             self.test_results_text.clear()
#             self.test_results_text.append(f"✗ Frame test failed: {str(e)}")
#     def _get_live_napari_frame(self) -> tuple[np.ndarray, dict]:
#         """Get a frame directly from any non-empty Napari image layer for quick tests/fallback."""
#         if self.viewer is None:
#             raise RuntimeError("No Napari viewer available for fallback")
#         for layer in self.viewer.layers:
#             try:
#                 data = getattr(layer, 'data', None)
#                 if data is None:
#                     continue
#                 frame = np.array(data, copy=True)
#                 if frame.size == 0:
#                     continue
#                 metadata = {
#                     "timestamp": time.time(),
#                     "camera_name": getattr(self, 'camera_name', 'unknown'),
#                     "frame_shape": frame.shape,
#                     "frame_dtype": str(frame.dtype),
#                     "source": f"napari_layer:{layer.name}",
#                     "fallback": True,
#                 }
#                 return frame, metadata
#             except Exception:
#                 continue
#         raise RuntimeError("No suitable Napari image layer found for fallback frame")

#     def _has_live_layer(self) -> bool:
#         if self.viewer is None:
#             return False
#         from napari.layers import Image
#         for layer in self.viewer.layers:
#             if not isinstance(layer, Image):
#                 continue
#             data = getattr(layer, 'data', None)
#             if data is None:
#                 continue
#             try:
#                 if hasattr(data, 'size') and data.size == 0:
#                     continue
#             except Exception:
#                 pass
#             return True  # any non-empty image layer qualifies
#         return False


#     # def _start_recording(self):
#     #     """Start recording with simplified setup."""
#     #     if not self.recording:
#     #         if not self.directory_edit.text():
#     #             self._add_log_entry("Error: No recording directory selected")
#     #             return
#     #         if self.imswitch_main is None and not self._has_live_layer():
#     #             self._add_log_entry("Error: No ImSwitch controller and no live Napari layer available for capture")
#     #             return

#     #         try:
#     #             from ._recorder import TimelapseRecorder

#     #             self.recorder = TimelapseRecorder(
#     #                 duration_min=self.duration_spinbox.value(),
#     #                 interval_sec=self.interval_spinbox.value(),
#     #                 output_dir=self.directory_edit.text(),
#     #                 esp32_controller=self.esp32_controller,
#     #                 data_manager=self.data_manager,
#     #                 imswitch_main=self.imswitch_main,
#     #                 camera_name=self.camera_name
#     #             )

#     #             # ✅ Connect recorder signals AFTER creating the recorder
#     #             self.recorder.frame_captured.connect(self._on_frame_captured)
#     #             self.recorder.recording_finished.connect(self._on_recording_finished)
#     #             self.recorder.recording_paused.connect(self._on_recording_paused)
#     #             self.recorder.recording_resumed.connect(self._on_recording_resumed)
#     #             self.recorder.error_occurred.connect(self._on_recording_error)
#     #             self.recorder.progress_updated.connect(self._on_progress_updated)
#     #             self.recorder.status_updated.connect(self._on_status_updated)
#     #             if self.viewer is None:
#     #                 self._add_log_entry("Warning: Napari viewer is not connected; fallback capture may fail.")
#     #             else:
#     #                 self.recorder.viewer = self.viewer

#     #             # Start recording
#     #             self.recorder.start()
#     #             self.recording = True
#     #             self.start_button.setText("🎬 Recording...")
#     #             self.start_button.setEnabled(False)
#     #             self._add_log_entry("Started timelapse recording (ImSwitch direct)")

#     #         except Exception as e:
#     #             self._add_log_entry(f"Failed to start recording: {str(e)}")
#     def _start_recording(self):
#         """Start recording with simplified setup and layer cleanup."""
#         if not self.recording:
#             if not self.directory_edit.text():
#                 self._add_log_entry("Error: No recording directory selected")
#                 return
#             if self.imswitch_main is None and not self._has_live_layer():
#                 self._add_log_entry("Error: No ImSwitch controller and no live Napari layer available for capture")
#                 return

#             try:
#                 # ✅ NEW: Clean up any existing interfering layers before starting
#                 self._cleanup_timelapse_layers()

#                 from ._recorder import TimelapseRecorder

#                 self.recorder = TimelapseRecorder(
#                     duration_min=self.duration_spinbox.value(),
#                     interval_sec=self.interval_spinbox.value(),
#                     output_dir=self.directory_edit.text(),
#                     esp32_controller=self.esp32_controller,
#                     data_manager=self.data_manager,
#                     imswitch_main=self.imswitch_main,
#                     camera_name=self.camera_name
#                 )

#                 # ✅ Connect recorder signals AFTER creating the recorder
#                 self.recorder.frame_captured.connect(self._on_frame_captured)
#                 self.recorder.recording_finished.connect(self._on_recording_finished)
#                 self.recorder.recording_paused.connect(self._on_recording_paused)
#                 self.recorder.recording_resumed.connect(self._on_recording_resumed)
#                 self.recorder.error_occurred.connect(self._on_recording_error)
#                 self.recorder.progress_updated.connect(self._on_progress_updated)
#                 self.recorder.status_updated.connect(self._on_status_updated)

#                 if self.viewer is None:
#                     self._add_log_entry("Warning: Napari viewer is not connected; fallback capture may fail.")
#                 else:
#                     self.recorder.viewer = self.viewer

#                 # Start recording
#                 self.recorder.start()
#                 self.recording = True
#                 self.start_button.setText("🎬 Recording...")
#                 self.start_button.setEnabled(False)
#                 self._add_log_entry("Started timelapse recording (clean mode - no layer interference)")

#             except Exception as e:
#                 self._add_log_entry(f"Failed to start recording: {str(e)}")
#     def _pause_recording(self):
#         """Pause/resume recording."""
#         if self.recorder:
#             if hasattr(self.recorder, 'is_paused') and self.recorder.is_paused():
#                 self.recorder.resume()
#             else:
#                 self.recorder.pause()

#     def _stop_recording(self):
#         """Stop recording."""
#         if self.recorder:
#             self.recorder.stop()
#             self.recording = False
#             self.recorder = None
#             self.start_button.setText("🎬 Start Recording")
#             self.start_button.setEnabled(True)
#             self.pause_button.setText("⏸ Pause")
#             self._add_log_entry("Recording stopped")

#     # =========================================================================
#     # SIGNAL HANDLERS
#     # =========================================================================

#     def _on_file_created(self, filepath: str):
#         """Handle file created signal from DataManager."""
#         self._add_log_entry(f"Recording file created: {filepath}")
#         # Update UI to show file path
#         filename = Path(filepath).name
#         self.recording_status_label.setText(f"Recording: File Created ({filename})")

#     def _on_frame_saved(self, frame_number: int):
#         """Handle frame saved signal from DataManager."""
#         self._add_log_entry(f"Frame {frame_number} saved to HDF5 file")

#     def _on_metadata_updated(self, metadata: dict):
#         """Handle metadata updated signal from DataManager."""
#         self._add_log_entry("Recording metadata updated")
#         # Optional: Display key metadata in the UI
#         if 'actual_frames' in metadata:
#             actual_frames = metadata['actual_frames']
#             expected_frames = metadata.get('expected_frames', 0)
#             if expected_frames > 0:
#                 progress = int((actual_frames / expected_frames) * 100)
#                 self.progress_bar.setValue(progress)

#     # def _on_frame_captured(self, current_frame: int, total_frames: int):
#     #     """Handle frame captured signal and display in napari."""
#     #     self.frame_info_label.setText(f"Frame: {current_frame}/{total_frames}")
#     #     self._add_log_entry(f"Frame {current_frame}/{total_frames} captured")

#     #     # Display latest frame in napari viewer if available
#     #     if self.viewer is not None and self.recorder is not None:
#     #         try:
#     #             # Get the latest captured frame from data manager
#     #             recording_info = self.data_manager.get_recording_info()
#     #             if recording_info.get('frames_saved', 0) > 0:
#     #                 latest_frame_num = recording_info['frames_saved'] - 1
#     #                 filepath = recording_info.get('current_filepath')

#     #                 if filepath:
#     #                     # Load and display the latest frame
#     #                     frame, metadata = self.data_manager.load_frame(filepath, latest_frame_num)

#     #                     # Update or create layer in napari
#     #                     layer_name = "Timelapse Live"
#     #                     if layer_name in [layer.name for layer in self.viewer.layers]:
#     #                         # Update existing layer
#     #                         layer = next(layer for layer in self.viewer.layers if layer.name == layer_name)
#     #                         layer.data = frame
#     #                     else:
#     #                         # Create new layer
#     #                         self.viewer.add_image(frame, name=layer_name, colormap='gray')

#     #         except Exception as e:
#     #             print(f"Warning: Could not display frame in napari: {e}")
#     def _on_frame_captured(self, current_frame: int, total_frames: int):
#         """Handle frame captured signal - NO NAPARI LAYER CREATION."""
#         self.frame_info_label.setText(f"Frame: {current_frame}/{total_frames}")
#         self._add_log_entry(f"Frame {current_frame}/{total_frames} captured")

#         # ✅ REMOVED: All napari layer creation/update code
#         # No more "Timelapse Live" layer interference!

#         # Keep only the essential UI updates:
#         progress = int((current_frame / total_frames) * 100) if total_frames > 0 else 0
#         self.progress_bar.setValue(progress)
#     def _cleanup_timelapse_layers(self):
#         """Remove any existing Timelapse Live layers that interfere with live view."""
#         if self.viewer is None:
#             return

#         layers_to_remove = []
#         for layer in self.viewer.layers:
#             layer_name = getattr(layer, 'name', '').lower()

#             # Find layers that might interfere
#             if any(keyword in layer_name for keyword in ['timelapse live', 'timelapse_live', 'captured frames']):
#                 layers_to_remove.append(layer)

#         # Remove interfering layers
#         for layer in layers_to_remove:
#             try:
#                 self.viewer.layers.remove(layer)
#                 self._add_log_entry(f"Removed interfering layer: {layer.name}")
#             except Exception as e:
#                 print(f"Could not remove layer {layer.name}: {e}")
#     def _on_recording_finished(self):
#         """Handle recording finished signal."""
#         self.recording = False
#         self.start_button.setText("🎬 Start Recording")
#         self.start_button.setEnabled(True)
#         self.pause_button.setText("⏸ Pause")
#         self.progress_bar.setValue(100)
#         self._add_log_entry("Recording completed successfully")

#     def _on_recording_paused(self):
#         """Handle recording paused signal."""
#         self.pause_button.setText("▶ Resume")
#         self._add_log_entry("Recording paused")

#     def _on_recording_resumed(self):
#         """Handle recording resumed signal."""
#         self.pause_button.setText("⏸ Pause")
#         self._add_log_entry("Recording resumed")

#     def _on_recording_error(self, error_message: str):
#         """Handle recording error signal."""
#         self._add_log_entry(f"Recording error: {error_message}")
#         self.recording = False
#         self.start_button.setText("🎬 Start Recording")
#         self.start_button.setEnabled(True)

#     def _on_progress_updated(self, progress_percent: int):
#         """Handle progress update signal."""
#         self.progress_bar.setValue(progress_percent)

#     def _on_status_updated(self, status_message: str):
#         """Handle status update signal."""
#         # Parse status message to update UI elements
#         if "Frame" in status_message and "/" in status_message:
#             # Extract frame info
#             parts = status_message.split("-")
#             if len(parts) > 0:
#                 frame_part = parts[0].strip()
#                 self.frame_info_label.setText(frame_part)

#             # Extract timing info
#             if "Elapsed:" in status_message:
#                 elapsed_part = [p for p in parts if "Elapsed:" in p]
#                 if elapsed_part:
#                     self.elapsed_label.setText(elapsed_part[0].strip())

#             if "Remaining:" in status_message:
#                 remaining_part = [p for p in parts if "Remaining:" in p]
#                 if remaining_part:
#                     eta_text = remaining_part[0].strip().replace("Remaining:", "ETA:")
#                     self.eta_label.setText(eta_text)

#     def _update_status(self):
#         """Update system status - FIXED VERSION."""
#         # ✅ SAFETY CHECK: Stop if widget is being deleted
#         try:
#             if not hasattr(self, 'camera_status_label') or self.camera_status_label is None:
#                 return
#             # Test if the widget is still alive
#             self.camera_status_label.text()  # This will fail if widget is deleted
#         except (RuntimeError, AttributeError):
#             # Widget is being deleted, stop timer and return
#             if hasattr(self, 'status_timer'):
#                 self.status_timer.stop()
#             return

#         # Auto-detect napari viewer if not available
#         if self.viewer is None:
#             try:
#                 import napari
#                 current_viewer = napari.current_viewer()
#                 if current_viewer is not None and current_viewer != self.viewer:
#                     self.viewer = current_viewer
#                     # Re-check camera connection when viewer becomes available
#                     self.camera_connected = self._check_camera_connection()
#                     self._add_log_entry("Napari viewer auto-detected - camera status updated")
#             except:
#                 pass

#         # ✅ FIX: Use the simple camera check method
#         try:
#             camera_ready = self._check_camera_connection()
#             # Status is already updated in _check_camera_connection()
#         except Exception as e:
#             self.camera_status_label.setText("Camera: Error")
#             self.camera_status_label.setStyleSheet("color: #ff0000;")
#             print(f"Camera status check failed: {e}")

#         # ImSwitch availability (optional info)
#         if hasattr(self, 'imswitch_status_label'):
#             if self.imswitch_main is not None:
#                 self.imswitch_status_label.setText("ImSwitch: Connected")
#                 self.imswitch_status_label.setStyleSheet("color: #00ff00;")
#             else:
#                 self.imswitch_status_label.setText("ImSwitch: Not Available")
#                 self.imswitch_status_label.setStyleSheet("color: #ff0000;")

#         # ESP32 status
#         try:
#             if self.esp32_controller.is_connected():
#                 self.esp32_status_label_right.setText("ESP32: Connected")
#                 self.esp32_status_label_right.setStyleSheet("color: #00ff00;")
#             else:
#                 self.esp32_status_label_right.setText("ESP32: Disconnected")
#                 self.esp32_status_label_right.setStyleSheet("color: #ff0000;")
#         except:
#             self.esp32_status_label_right.setText("ESP32: Error")
#             self.esp32_status_label_right.setStyleSheet("color: #ff0000;")

#         # Recording status
#         if self.recording:
#             self.recording_status_label.setText("Recording: Active")
#             self.recording_status_label.setStyleSheet("color: #ffff00;")
#         else:
#             self.recording_status_label.setText("Recording: Ready")
#             self.recording_status_label.setStyleSheet("color: #00ff00;")

#     def closeEvent(self, event):
#         """Handle widget close event."""
#         try:
#             # Stop timer
#             if hasattr(self, 'status_timer'):
#                 self.status_timer.stop()

#             # Disconnect ESP32
#             if hasattr(self, 'esp32_controller'):
#                 try:
#                     self.esp32_controller.disconnect()
#                 except:
#                     pass

#             # Stop any recording
#             if hasattr(self, 'recorder') and self.recorder:
#                 try:
#                     self.recorder.stop()
#                 except:
#                     pass

#             print("Widget cleanup completed")
#         except Exception as e:
#             print(f"Cleanup error: {e}")

#         event.accept()

#     def _on_esp32_conn_changed(self, connected: bool):
#         """Handle ESP32 connection status change."""
#         text = "ESP32: Connected" if connected else "ESP32: Disconnected"
#         color = "#00ff00" if connected else "#ff0000"
#         self.esp32_status_label.setText(text)
#         self.esp32_status_label.setStyleSheet(f"color: {color};")
#         self.esp32_status_label_right.setText(text)
#         self.esp32_status_label_right.setStyleSheet(f"color: {color};")

#     def _on_led_status_changed(self, is_on: bool, power: int):
#         """Handle LED status change."""
#         if is_on:
#             self.esp32_status_label.setText(f"ESP32: LED ON – {power}%")
#             self.esp32_status_label.setStyleSheet("color: #00ff00;")
#             self._add_log_entry(f"LED status: ON at {power}% power")
#         else:
#             self.esp32_status_label.setText("ESP32: LED OFF")
#             self.esp32_status_label.setStyleSheet("color: #ff0000;")
#             self._add_log_entry("LED status: OFF")

#     def connect_to_napari(self, viewer):
#         """Connect the plugin to a napari viewer."""
#         self.viewer = viewer
#         self._add_log_entry("Connected to napari viewer")


# # ✅ Create widget function
# def create_timelapse_widget(napari_viewer=None):
#     """Create and return the timelapse widget."""
#     return NematostallTimelapseCaptureWidget(napari_viewer, None)


# # ✅ NPE1 hook for backward compatibility
# from napari_plugin_engine import napari_hook_implementation

# @napari_hook_implementation
# def napari_experimental_provide_dock_widget():
#     """Provide the timelapse capture dock widget."""
#     def create_widget():
#         # Get napari viewer if available
#         try:
#             import napari
#             viewer = napari.current_viewer()
#         except:
#             viewer = None

#         widget = NematostallTimelapseCaptureWidget(viewer, None)
#         return widget

#     return create_widget
"""Fixed napari plugin widget for timelapse recording with Day/Night phase support - NO MOCK MODE."""

import napari
from qtpy.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QPushButton,
    QLabel,
    QSpinBox,
    QCheckBox,
    QLineEdit,
    QTextEdit,
    QProgressBar,
    QGroupBox,
    QSlider,
    QFileDialog,
    QComboBox,  # ✅ NEW: Added QComboBox
)
from qtpy.QtCore import QTimer, QObject

try:
    from qtpy.QtCore import pyqtSignal
except ImportError:
    from qtpy.QtCore import Signal as pyqtSignal

import time
import os
import numpy as np
from pathlib import Path
from typing import Tuple


def get_imswitch_main():
    """Get ImSwitch main controller from global context - SAFE VERSION."""
    import sys
    import gc

    print("=== ImSwitch Detection Debug ===")

    # Method 1: Look for ImSwitch in sys.modules
    print("Method 1: Checking sys.modules...")
    imswitch_modules = [name for name in sys.modules.keys() if "imswitch" in name.lower()]
    print(f"Found ImSwitch modules: {imswitch_modules}")

    for module_name in imswitch_modules:
        try:
            module = sys.modules[module_name]
            print(f"Checking module: {module_name}")

            # Check for main_controller attribute
            if hasattr(module, "main_controller"):
                print(f"Found main_controller in {module_name}")
                return module.main_controller

            # Check for other common controller names
            controller_names = ["mainController", "controller", "main", "_main_controller"]
            for controller_name in controller_names:
                if hasattr(module, controller_name):
                    controller = getattr(module, controller_name)
                    try:
                        if hasattr(controller, "detectorsManager") and hasattr(
                            controller, "liveViewWidget"
                        ):
                            print(f"Found ImSwitch controller in {module_name}.{controller_name}")
                            return controller
                    except:
                        continue
        except Exception as e:
            print(f"Error checking module {module_name}: {e}")
            continue

    # Method 2: Search through garbage collector (SAFE VERSION)
    print("Method 2: Searching garbage collector...")
    try:
        for obj in gc.get_objects():
            try:
                # Only check objects that look like they could be ImSwitch
                obj_type = str(type(obj))
                if "imswitch" in obj_type.lower() or "main" in obj_type.lower():
                    if hasattr(obj, "detectorsManager") and hasattr(obj, "liveViewWidget"):
                        print(f"Found ImSwitch controller via GC: {type(obj)}")
                        return obj
            except Exception:
                # Skip problematic objects silently
                continue
    except Exception as e:
        print(f"GC search failed: {e}")

    print("ImSwitch controller not found")
    return None


class NematostallTimelapseCaptureWidget(QWidget):
    """Main widget for Nematostella timelapse capture with Day/Night phase support - NO MOCK MODE."""

    def __init__(self, napari_viewer=None, imswitch_main_controller=None):
        super().__init__()

        # ✅ NEW: Configure logging for corrected modules
        import logging

        logging.getLogger("_esp32_controller").setLevel(logging.INFO)  # Quieter for production
        logging.getLogger("_data_manager").setLevel(logging.INFO)

        # ✅ DEBUG: Check napari viewer
        print(f"Widget init: napari_viewer = {type(napari_viewer) if napari_viewer else None}")
        print(
            f"Widget init: viewer layers = {len(napari_viewer.layers) if napari_viewer else 'No viewer'}"
        )

        self.viewer = napari_viewer

        # ✅ AUTO-DETECT IMSWITCH if not provided
        if imswitch_main_controller is None:
            imswitch_main_controller = get_imswitch_main()
            if imswitch_main_controller:
                print("SUCCESS: ImSwitch auto-detected!")

        self.imswitch_main = imswitch_main_controller
        self.setWindowTitle("Nematostella Time-Series Capture")
        self.setMinimumWidth(800)
        self.setMinimumHeight(600)

        # Camera info direkt von ImSwitch
        self.camera_name = "HikCamera"
        self.camera_connected = False

        # ✅ UI ZUERST setuppen
        self._setup_ui()

        # Import real controllers - NO FALLBACKS
        self._initialize_controllers()

        # State variables
        self.recording = False

        # Setup connections and timers
        self._setup_connections()
        self._setup_timers()

    def _find_imswitch_controller(self):
        """Try to find ImSwitch controller from running system."""
        try:
            print("Searching for ImSwitch controller...")
            import gc

            # Method 1: Search in garbage collector for ImSwitch objects
            for obj in gc.get_objects():
                if (
                    hasattr(obj, "detectorsManager")
                    and hasattr(obj, "liveViewWidget")
                    and hasattr(obj, "getState")
                ):
                    print(f"Found ImSwitch controller: {type(obj)}")
                    return obj

            # Method 2: Try napari viewer connections
            if self.viewer is not None:
                # Check if napari has any ImSwitch-related objects
                for widget in getattr(self.viewer.window, "_dock_widgets", []):
                    if hasattr(widget, "imswitch_main"):
                        print("Found ImSwitch through napari dock widget")
                        return widget.imswitch_main

            # Method 3: Try module-level search
            import sys

            for module_name, module in sys.modules.items():
                if "imswitch" in module_name.lower():
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name, None)
                        if hasattr(attr, "detectorsManager") and hasattr(attr, "liveViewWidget"):
                            print(f"Found ImSwitch in module: {module_name}")
                            return attr

            print("ImSwitch controller not found - will run without camera")
            return None

        except Exception as e:
            print(f"ImSwitch auto-detection failed: {e}")
            return None

    def _initialize_controllers(self):
        """Initialize real controllers - no mock fallbacks."""
        try:
            from ._esp32_controller import ESP32Controller
            from ._data_manager import DataManager

            # Initialize real controllers
            self.esp32_controller = ESP32Controller(self.imswitch_main)
            self.data_manager = DataManager()
            self.recorder = None

            # Check camera connection through ImSwitch
            self.camera_connected = self._check_camera_connection()

            self._add_log_entry("Real controllers initialized successfully")

            # Test ESP32 connection on startup
            if self.esp32_controller.esp32_port:
                self._add_log_entry(f"ESP32 port detected: {self.esp32_controller.esp32_port}")
            else:
                self._add_log_entry("Warning: No ESP32 port detected")

            # Log ImSwitch status
            if self.imswitch_main is not None:
                self._add_log_entry("ImSwitch controller found and connected!")
            else:
                self._add_log_entry("ImSwitch not found - running without camera")

        except ImportError as e:
            error_msg = f"CRITICAL: Cannot import required modules: {str(e)}"
            self._add_log_entry(error_msg)
            raise RuntimeError(error_msg)
        except Exception as e:
            error_msg = f"CRITICAL: Controller initialization failed: {str(e)}"
            self._add_log_entry(error_msg)
            raise RuntimeError(error_msg)

    def _add_log_entry(self, message):
        """Add entry to system log."""
        if not hasattr(self, "log_text") or self.log_text is None:
            print(f"LOG: {message}")
            return

        import datetime

        now = datetime.datetime.now()
        timestamp = now.strftime("[%H:%M:%S.%f")[:-3] + "]"
        log_entry = f"<span style='color: #00ff00;'>{timestamp}</span> {message}"
        self.log_text.append(log_entry)

    def _check_camera_connection(self) -> bool:
        """Simple check: Is ANY camera source ready for recording?"""

        camera_ready = False
        camera_source = "Unknown"

        print("DEBUG: Checking camera connection...")  # ✅ Debug output

        # Quick test: Try to capture a frame from any available source
        try:
            # Method 1: Try Napari live layer (fastest)
            if self.viewer is not None:
                print(f"DEBUG: Checking {len(self.viewer.layers)} napari layers...")
                from napari.layers import Image

                for layer in self.viewer.layers:
                    if isinstance(layer, Image):
                        data = getattr(layer, "data", None)
                        if data is not None and data.size > 0:
                            camera_ready = True
                            camera_source = f"napari:{layer.name}"
                            print(f"DEBUG: Found camera source: {camera_source}")
                            break
            else:
                print("DEBUG: No napari viewer available")

            # Method 2: Try ImSwitch if Napari didn't work
            if not camera_ready and self.imswitch_main is not None:
                print("DEBUG: Trying ImSwitch LiveView...")
                if hasattr(self.imswitch_main, "liveViewWidget"):
                    live_view = self.imswitch_main.liveViewWidget
                    if hasattr(live_view, "img") and live_view.img is not None:
                        camera_ready = True
                        camera_source = "ImSwitch LiveView"
                        print(f"DEBUG: Found camera source: {camera_source}")
            else:
                print("DEBUG: No ImSwitch available")

        except Exception as e:
            print(f"DEBUG: Camera check failed: {e}")
            camera_ready = False

        print(f"DEBUG: Camera ready = {camera_ready}, source = {camera_source}")

        # Update status labels if they exist
        if hasattr(self, "camera_status_label") and self.camera_status_label is not None:
            if camera_ready:
                self.camera_status_label.setText(f"Camera: Ready ({camera_source})")
                self.camera_status_label.setStyleSheet("color: #00ff00;")
                print(f"DEBUG: Updated camera status to Ready ({camera_source})")
            else:
                self.camera_status_label.setText("Camera: Not Ready")
                self.camera_status_label.setStyleSheet("color: #ff0000;")
                print("DEBUG: Updated camera status to Not Ready")

        return camera_ready

    def _setup_ui(self):
        """Setup the user interface."""
        layout = QHBoxLayout()

        # Left panel
        left_panel = self._create_left_panel()
        layout.addWidget(left_panel, stretch=2)

        # Right panel
        right_panel = self._create_right_panel()
        layout.addWidget(right_panel, stretch=1)

        self.setLayout(layout)

    def _create_left_panel(self):
        """Create the left control panel."""
        widget = QWidget()
        layout = QVBoxLayout()

        # Tab widget
        tabs = QTabWidget()

        # Camera tab
        camera_tab = self._create_camera_tab()
        tabs.addTab(camera_tab, "File Management")

        # Recording tab
        recording_tab = self._create_recording_tab()
        tabs.addTab(recording_tab, "Recording")

        # ESP32 tab
        esp32_tab = self._create_esp32_tab()
        tabs.addTab(esp32_tab, "ESP32 Control")

        # Diagnostics tab
        diagnostics_tab = self._create_diagnostics_tab()
        tabs.addTab(diagnostics_tab, "Diagnostics")

        layout.addWidget(tabs)
        widget.setLayout(layout)
        return widget

    def _create_camera_tab(self):
        """Create camera control tab."""
        widget = QWidget()
        layout = QVBoxLayout()

        # ImSwitch Info
        imswitch_group = QGroupBox("ImSwitch Camera Info")
        imswitch_layout = QVBoxLayout()

        self.camera_info_label = QLabel(f"Camera: {self.camera_name}")
        self.imswitch_status_label = QLabel("ImSwitch: Not Connected")

        imswitch_layout.addWidget(self.camera_info_label)
        imswitch_layout.addWidget(self.imswitch_status_label)
        imswitch_group.setLayout(imswitch_layout)

        # File Management
        file_group = QGroupBox("File Management")
        file_layout = QVBoxLayout()

        dir_layout = QHBoxLayout()
        self.directory_edit = QLineEdit()
        self.directory_edit.setPlaceholderText("Select Directory")
        dir_button = QPushButton("📁 Select Directory")
        dir_button.clicked.connect(self._select_directory)
        dir_layout.addWidget(self.directory_edit)
        dir_layout.addWidget(dir_button)

        self.timestamp_checkbox = QCheckBox("Create timestamped subfolder")
        self.timestamp_checkbox.setChecked(True)

        file_layout.addLayout(dir_layout)
        file_layout.addWidget(self.timestamp_checkbox)
        file_group.setLayout(file_layout)

        layout.addWidget(file_group)
        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def _create_recording_tab(self):
        """Create recording control tab with Day/Night phase controls."""
        widget = QWidget()
        layout = QVBoxLayout()

        # Recording Parameters
        params_group = QGroupBox("Recording Parameters")
        params_layout = QVBoxLayout()

        # Duration and Interval (existing)
        duration_layout = QHBoxLayout()
        duration_layout.addWidget(QLabel("Total Duration (min):"))
        self.duration_spinbox = QSpinBox()
        self.duration_spinbox.setRange(1, 10000)
        self.duration_spinbox.setValue(60)  # Default 1 hour
        duration_layout.addWidget(self.duration_spinbox)

        duration_layout.addWidget(QLabel("Interval (sec):"))
        self.interval_spinbox = QSpinBox()
        self.interval_spinbox.setRange(1, 3600)
        self.interval_spinbox.setValue(5)
        duration_layout.addWidget(self.interval_spinbox)

        # ✅ NEW: Day/Night Phase Controls
        phase_group = QGroupBox("Day/Night Cycle Configuration")
        phase_layout = QVBoxLayout()

        # Phase enable checkbox
        self.enable_day_night_checkbox = QCheckBox("Enable Day/Night Cycling")
        self.enable_day_night_checkbox.setChecked(False)
        self.enable_day_night_checkbox.stateChanged.connect(self._toggle_phase_controls)
        phase_layout.addWidget(self.enable_day_night_checkbox)

        # Phase duration controls
        phase_controls_layout = QHBoxLayout()

        # Light phase (White LED)
        light_layout = QVBoxLayout()
        light_layout.addWidget(QLabel("☀️ Light Phase (White LED)"))
        light_duration_layout = QHBoxLayout()
        light_duration_layout.addWidget(QLabel("Duration (min):"))
        self.light_phase_spinbox = QSpinBox()
        self.light_phase_spinbox.setRange(1, 1440)  # 1 min to 24 hours
        self.light_phase_spinbox.setValue(30)  # Default 30 minutes
        light_duration_layout.addWidget(self.light_phase_spinbox)
        light_layout.addLayout(light_duration_layout)

        # Dark phase (IR LED)
        dark_layout = QVBoxLayout()
        dark_layout.addWidget(QLabel("🌙 Dark Phase (IR LED)"))
        dark_duration_layout = QHBoxLayout()
        dark_duration_layout.addWidget(QLabel("Duration (min):"))
        self.dark_phase_spinbox = QSpinBox()
        self.dark_phase_spinbox.setRange(1, 1440)  # 1 min to 24 hours
        self.dark_phase_spinbox.setValue(30)  # Default 30 minutes
        dark_duration_layout.addWidget(self.dark_phase_spinbox)
        dark_layout.addLayout(dark_duration_layout)

        phase_controls_layout.addLayout(light_layout)
        phase_controls_layout.addLayout(dark_layout)

        # Phase info display
        self.phase_info_layout = QHBoxLayout()
        self.current_phase_label = QLabel("Current Phase: Light")
        self.current_phase_label.setStyleSheet("color: #ff8800; font-weight: bold;")
        self.phase_cycles_label = QLabel("Total Cycles: 1")
        self.phase_time_remaining_label = QLabel("Phase Time Remaining: --:--")

        self.phase_info_layout.addWidget(self.current_phase_label)
        self.phase_info_layout.addWidget(self.phase_cycles_label)
        self.phase_info_layout.addWidget(self.phase_time_remaining_label)

        # Starting phase selection
        start_phase_layout = QHBoxLayout()
        start_phase_layout.addWidget(QLabel("Start with:"))
        self.start_phase_combo = QComboBox()
        self.start_phase_combo.addItems(["Light Phase (☀️ White LED)", "Dark Phase (🌙 IR LED)"])
        start_phase_layout.addWidget(self.start_phase_combo)
        start_phase_layout.addStretch()

        # Add all phase controls to group
        phase_layout.addLayout(phase_controls_layout)
        phase_layout.addLayout(start_phase_layout)
        phase_layout.addLayout(self.phase_info_layout)
        phase_group.setLayout(phase_layout)

        # Store phase control widgets for enable/disable
        self.phase_control_widgets = [
            self.light_phase_spinbox,
            self.dark_phase_spinbox,
            self.start_phase_combo,
        ]

        # Expected frames calculation (updated)
        expected_layout = QHBoxLayout()
        expected_layout.addWidget(QLabel("Expected Frames:"))
        self.expected_frames_label = QLabel("720")
        expected_layout.addWidget(self.expected_frames_label)
        expected_layout.addStretch()

        # Statistics (updated)
        self.frames_label = QLabel("● Frames: 720")
        self.duration_label = QLabel("● Duration: 60.0 min")
        self.intervals_label = QLabel("● Intervals: 5.0 sec")
        self.phase_stats_label = QLabel("● Phase Pattern: Continuous")

        # Add layouts to params group
        params_layout.addLayout(duration_layout)
        params_layout.addWidget(phase_group)  # Add phase controls
        params_layout.addLayout(expected_layout)
        params_layout.addWidget(self.frames_label)
        params_layout.addWidget(self.duration_label)
        params_layout.addWidget(self.intervals_label)
        params_layout.addWidget(self.phase_stats_label)
        params_group.setLayout(params_layout)

        # Recording Control (unchanged)
        control_group = QGroupBox("Recording Control")
        control_layout = QVBoxLayout()

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)

        # Frame info
        frame_layout = QHBoxLayout()
        self.frame_info_label = QLabel("Frame: 0/720")
        self.elapsed_label = QLabel("Elapsed: 00:00:00")
        self.eta_label = QLabel("ETA: 00:00:00")

        frame_layout.addWidget(self.frame_info_label)
        frame_layout.addWidget(self.elapsed_label)
        frame_layout.addWidget(self.eta_label)

        # Control buttons
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("🎬 Start Recording")
        self.pause_button = QPushButton("⏸ Pause")
        self.stop_button = QPushButton("⏹ Stop")

        self.start_button.clicked.connect(self._start_recording)
        self.pause_button.clicked.connect(self._pause_recording)
        self.stop_button.clicked.connect(self._stop_recording)

        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.pause_button)
        button_layout.addWidget(self.stop_button)

        control_layout.addWidget(self.progress_bar)
        control_layout.addLayout(frame_layout)
        control_layout.addLayout(button_layout)
        control_group.setLayout(control_layout)

        layout.addWidget(params_group)
        layout.addWidget(control_group)
        layout.addStretch()
        widget.setLayout(layout)

        # Initialize phase controls as disabled
        self._toggle_phase_controls()

        return widget

    def _create_esp32_tab(self):
        """Create ESP32 control tab with proper calibration layout."""
        widget = QWidget()
        layout = QVBoxLayout()

        # ESP32 Connection
        connection_group = QGroupBox("ESP32 Connection")
        conn_layout = QVBoxLayout()

        conn_button_layout = QHBoxLayout()
        self.connect_esp32_button = QPushButton("🔗 Connect ESP32")
        self.disconnect_esp32_button = QPushButton("❌ Disconnect")

        self.connect_esp32_button.clicked.connect(self.widget_connect_esp32_protected)
        self.disconnect_esp32_button.clicked.connect(self._disconnect_esp32)

        conn_button_layout.addWidget(self.connect_esp32_button)
        conn_button_layout.addWidget(self.disconnect_esp32_button)

        self.esp32_status_label = QLabel("ESP32: Disconnected")

        conn_layout.addLayout(conn_button_layout)
        conn_layout.addWidget(self.esp32_status_label)
        connection_group.setLayout(conn_layout)

        # LED Control
        led_group = QGroupBox("LED Control")
        led_layout = QVBoxLayout()

        # LED Power slider
        power_layout = QHBoxLayout()
        power_layout.addWidget(QLabel("LED Power:"))
        self.led_power_slider = QSlider()
        self.led_power_slider.setOrientation(1)  # Horizontal
        self.led_power_slider.setRange(0, 100)
        self.led_power_slider.setValue(100)
        self.led_power_value_label = QLabel("100%")

        power_layout.addWidget(self.led_power_slider)
        power_layout.addWidget(self.led_power_value_label)

        # LED buttons
        led_button_layout = QHBoxLayout()
        self.led_on_button = QPushButton("💡 LED ON (100%)")
        self.led_off_button = QPushButton("🌑 LED OFF")

        self.led_on_button.clicked.connect(self._led_on)
        self.led_off_button.clicked.connect(self._led_off)

        led_button_layout.addWidget(self.led_on_button)
        led_button_layout.addWidget(self.led_off_button)

        # Test buttons
        test_layout = QHBoxLayout()
        self.manual_flash_button = QPushButton("⚡ Manual Flash")
        self.read_sensors_button = QPushButton("📊 Read Sensors")

        self.manual_flash_button.clicked.connect(self._manual_flash)
        self.read_sensors_button.clicked.connect(self._read_sensors)

        test_layout.addWidget(self.manual_flash_button)
        test_layout.addWidget(self.read_sensors_button)

        led_layout.addLayout(power_layout)
        led_layout.addLayout(led_button_layout)
        led_layout.addLayout(test_layout)
        led_group.setLayout(led_layout)

        # ✅ FIXED: LED Calibration section
        calibration_group = QGroupBox("LED Calibration")
        calibration_layout = QVBoxLayout()

        calibrate_button = QPushButton("🎯 Auto-Calibrate LED Powers")
        calibrate_button.clicked.connect(self._auto_calibrate_leds)
        calibrate_button.setStyleSheet(
            "background-color: #ff6600; color: white; font-weight: bold;"
        )

        self.calibration_status_label = QLabel("Calibration: Not performed")

        calibration_layout.addWidget(calibrate_button)
        calibration_layout.addWidget(self.calibration_status_label)
        calibration_group.setLayout(calibration_layout)

        # Environmental Sensors
        sensor_group = QGroupBox("Environmental Sensors")
        sensor_layout = QVBoxLayout()

        sensor_readings_layout = QHBoxLayout()
        sensor_readings_layout.addWidget(QLabel("Temperature:"))
        self.temperature_label = QLabel("--°C")
        sensor_readings_layout.addWidget(self.temperature_label)

        sensor_readings_layout.addWidget(QLabel("Humidity:"))
        self.humidity_label = QLabel("--%")
        sensor_readings_layout.addWidget(self.humidity_label)

        sensor_layout.addLayout(sensor_readings_layout)
        sensor_group.setLayout(sensor_layout)

        # ✅ FIXED: Add all groups to main layout
        layout.addWidget(connection_group)
        layout.addWidget(led_group)
        layout.addWidget(calibration_group)  # This was missing!
        layout.addWidget(sensor_group)
        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def _create_diagnostics_tab(self):
        """Create diagnostics tab."""
        widget = QWidget()
        layout = QVBoxLayout()

        # System Diagnostics
        diag_group = QGroupBox("System Diagnostics")
        diag_layout = QVBoxLayout()

        test_button_layout = QHBoxLayout()
        self.test_full_button = QPushButton("🔧 Test Full System")
        self.quick_test_button = QPushButton("Quick Frame Test")

        # Debug buttons
        self.debug_esp32_button = QPushButton("🔍 Debug ESP32")
        self.debug_imswitch_button = QPushButton("🔍 Debug ImSwitch")

        self.debug_esp32_button.setStyleSheet(
            """
            QPushButton {
                background-color: #ff0066;
                color: white;
                font-weight: bold;
                padding: 8px;
            }
        """
        )

        self.debug_imswitch_button.setStyleSheet(
            """
            QPushButton {
                background-color: #0066ff;
                color: white;
                font-weight: bold;
                padding: 8px;
            }
        """
        )

        self.debug_esp32_button.clicked.connect(self._debug_esp32_communication)
        self.debug_imswitch_button.clicked.connect(self._debug_imswitch_structure)

        self.test_full_button.clicked.connect(self._test_full_system)
        self.quick_test_button.clicked.connect(self._quick_frame_test)

        self.quick_test_button.setStyleSheet(
            """
            QPushButton {
                background-color: #ff6600;
                color: white;
                font-weight: bold;
                padding: 8px;
            }
        """
        )

        test_button_layout.addWidget(self.test_full_button)
        test_button_layout.addWidget(self.quick_test_button)
        test_button_layout.addWidget(self.debug_esp32_button)
        test_button_layout.addWidget(self.debug_imswitch_button)

        # Test metrics
        metrics_layout = QHBoxLayout()
        self.fps_label = QLabel("FPS: --")
        self.dropped_label = QLabel("Dropped: 0")

        metrics_layout.addWidget(self.fps_label)
        metrics_layout.addWidget(self.dropped_label)
        metrics_layout.addStretch()

        diag_layout.addLayout(test_button_layout)
        diag_layout.addLayout(metrics_layout)
        diag_group.setLayout(diag_layout)

        # Test Results
        results_group = QGroupBox("Test Results")
        results_layout = QVBoxLayout()

        self.test_results_text = QTextEdit()
        self.test_results_text.setReadOnly(True)
        self.test_results_text.setMaximumHeight(200)

        results_layout.addWidget(self.test_results_text)
        results_group.setLayout(results_layout)

        layout.addWidget(diag_group)
        layout.addWidget(results_group)
        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def _create_right_panel(self):
        """Create the right status panel."""
        widget = QWidget()
        layout = QVBoxLayout()

        # System Status
        status_group = QGroupBox("System Status")
        status_layout = QVBoxLayout()

        self.camera_status_label = QLabel("Camera: Not Connected")
        self.esp32_status_label_right = QLabel("ESP32: Disconnected")
        self.recording_status_label = QLabel("Recording: Ready")

        status_layout.addWidget(self.camera_status_label)
        status_layout.addWidget(self.esp32_status_label_right)
        status_layout.addWidget(self.recording_status_label)
        status_group.setLayout(status_layout)

        # System Log
        log_group = QGroupBox("System Log")
        log_layout = QVBoxLayout()

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(300)

        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)

        layout.addWidget(status_group)
        layout.addWidget(log_group)
        layout.addStretch()
        widget.setLayout(layout)
        return widget

    # ========================================================================
    # ✅ NEW: LED CALIBRATION METHODS - Add these to your widget class
    # ========================================================================

    def auto_calibrate_led_power(self, target_intensity_percentile=75, roi_fraction=0.5):
        """Auto-calibrate LED powers for consistent illumination intensity."""

        # 1. Capture reference frame with IR LED
        ir_power_initial = 100
        self.esp32_controller.select_led_type("ir")
        self.esp32_controller.set_led_power(ir_power_initial)

        # Allow LED to stabilize
        time.sleep(1.0)

        # Capture IR reference frame
        ir_frame, _ = self._safe_capture_frame()
        ir_intensity = self._measure_frame_intensity(
            ir_frame, roi_fraction, target_intensity_percentile
        )

        # 2. Find optimal white LED power
        whitelight_power_optimal = self._calibrate_whitelight_led_to_match(
            ir_intensity, target_intensity_percentile, roi_fraction
        )

        # 3. Store calibrated values
        self.calibrated_ir_power = ir_power_initial
        self.calibrated_whitelight_power = whitelight_power_optimal

        return {
            "ir_power": self.calibrated_ir_power,
            "whitelight_power": self.calibrated_whitelight_power,  # ✅ Consistent naming
            "ir_intensity": ir_intensity,
            "target_intensity": ir_intensity,
        }

    def _calibrate_whitelight_led_to_match(
        self, target_intensity, percentile, roi_fraction, max_iterations=10
    ):
        """Binary search to find white LED power that matches target intensity."""

        self.esp32_controller.select_led_type("white")  # Can still use 'white' as input

        power_min, power_max = 1, 100
        best_power = 50
        tolerance = target_intensity * 0.05  # 5% tolerance

        for iteration in range(max_iterations):
            current_power = (power_min + power_max) // 2

            self.esp32_controller.set_led_power(current_power)
            time.sleep(0.5)  # LED stabilization

            whitelight_frame, _ = self._safe_capture_frame()
            whitelight_intensity = self._measure_frame_intensity(
                whitelight_frame, roi_fraction, percentile
            )

            intensity_diff = whitelight_intensity - target_intensity

            if abs(intensity_diff) < tolerance:
                best_power = current_power
                break
            elif whitelight_intensity > target_intensity:
                power_max = current_power - 1
            else:
                power_min = current_power + 1

            best_power = current_power

        return best_power

    def _measure_frame_intensity(self, frame, roi_fraction=0.5, percentile=75):
        """Measure representative intensity from center ROI."""
        if frame is None or frame.size == 0:
            return 0

        # Use center ROI to avoid edge effects
        h, w = frame.shape[:2]
        roi_h, roi_w = int(h * roi_fraction), int(w * roi_fraction)
        y1, x1 = (h - roi_h) // 2, (w - roi_w) // 2
        y2, x2 = y1 + roi_h, x1 + roi_w

        roi = frame[y1:y2, x1:x2]

        # Use percentile instead of mean (more robust to outliers)
        intensity = np.percentile(roi.flatten(), percentile)

        return float(intensity)

    def _calibrate_white_led_to_match(
        self, target_intensity, percentile, roi_fraction, max_iterations=10
    ):
        """Binary search to find white LED power that matches target intensity."""

        self.esp32_controller.select_led_type("white")

        power_min, power_max = 1, 100
        best_power = 50
        tolerance = target_intensity * 0.05  # 5% tolerance

        for iteration in range(max_iterations):
            current_power = (power_min + power_max) // 2

            self.esp32_controller.set_led_power(current_power)
            time.sleep(0.5)  # LED stabilization

            white_frame, _ = self._safe_capture_frame()
            white_intensity = self._measure_frame_intensity(white_frame, roi_fraction, percentile)

            intensity_diff = white_intensity - target_intensity

            if abs(intensity_diff) < tolerance:
                best_power = current_power
                break
            elif white_intensity > target_intensity:
                power_max = current_power - 1
            else:
                power_min = current_power + 1

            best_power = current_power

        return best_power

    def _safe_capture_frame(self):
        """Capture frame using existing capture methods."""
        if self.imswitch_main is not None:
            try:
                return self._capture_frame_from_imswitch_direct()
            except Exception as e:
                self._add_log_entry(f"ImSwitch capture failed: {e}, trying Napari...")

        if self.viewer is not None:
            try:
                return self._get_live_napari_frame()
            except Exception as e:
                self._add_log_entry(f"Napari capture failed: {e}")

        raise RuntimeError("All frame capture methods failed")

    def _capture_frame_from_imswitch_direct(self):
        """Capture frame directly from ImSwitch - simplified for calibration."""
        if self.imswitch_main is None:
            raise RuntimeError("ImSwitch not available")

        # Try liveViewWidget first
        if hasattr(self.imswitch_main, "liveViewWidget"):
            live_view = self.imswitch_main.liveViewWidget
            if hasattr(live_view, "img") and live_view.img is not None:
                frame = live_view.img.copy()
                metadata = {
                    "timestamp": time.time(),
                    "camera_name": self.camera_name,
                    "source": "imswitch_live_view",
                }
                return frame, metadata

        raise RuntimeError("Could not capture frame from ImSwitch")

    def _auto_calibrate_leds(self):
        """Perform LED calibration with proper ESP32Controller integration."""
        try:
            if not self.esp32_controller.is_connected():
                self._add_log_entry("Error: ESP32 not connected")
                return

            if not self._has_live_layer() and self.imswitch_main is None:
                self._add_log_entry("Error: No camera source available")
                return

            self._add_log_entry("Starting LED calibration...")
            self.calibration_status_label.setText("Calibration: In progress...")

            # Perform calibration
            results = self.auto_calibrate_led_power()

            # ✅ CRITICAL FIX: Transfer calibrated values to ESP32Controller with whitelight_power
            ir_power = results["ir_power"]
            whitelight_power = results["whitelight_power"]  # ✅ Consistent naming

            # Store in ESP32Controller with auto-apply enabled
            self.esp32_controller.set_calibrated_powers(
                ir_power=ir_power,
                whitelight_power=whitelight_power,  # ✅ Correct parameter name
                auto_apply=True,
            )

            # Update UI
            self.calibration_status_label.setText(
                f"Calibrated: IR={ir_power}%, WhiteLight={whitelight_power}%"
            )
            self._add_log_entry(
                f"Calibration complete and applied: IR LED={ir_power}%, WhiteLight LED={whitelight_power}%"
            )

            # ✅ Verify calibration works by testing both LEDs
            verification_passed = self._verify_calibration_intensity(results)
            if verification_passed:
                self._add_log_entry(
                    "✓ Calibration verification PASSED - intensities match within tolerance"
                )
                self.calibration_status_label.setText(
                    f"Calibrated & Verified: IR={ir_power}%, WhiteLight={whitelight_power}%"
                )
            else:
                self._add_log_entry("⚠ Calibration verification FAILED - intensities may not match")
                self.calibration_status_label.setText(
                    f"Calibrated (Unverified): IR={ir_power}%, WhiteLight={whitelight_power}%"
                )

            # Show results in test area
            if hasattr(self, "test_results_text"):
                self.test_results_text.clear()
                self.test_results_text.append("=== LED Calibration Results ===")
                self.test_results_text.append(f"IR LED Power: {ir_power}%")
                self.test_results_text.append(f"WhiteLight LED Power: {whitelight_power}%")
                self.test_results_text.append(
                    f"Target Intensity: {results['target_intensity']:.1f}"
                )
                self.test_results_text.append("✓ Calibration applied to ESP32Controller")
                self.test_results_text.append("✓ Auto-apply enabled for phase transitions")

        except Exception as e:
            self._add_log_entry(f"LED calibration failed: {e}")
            self.calibration_status_label.setText("Calibration: Failed")
            # Ensure auto-apply is disabled on failure
            if hasattr(self.esp32_controller, "enable_auto_calibration"):
                self.esp32_controller.enable_auto_calibration(False)

    def _verify_calibration_intensity(self, calibration_results):
        """Verify that calibrated LED powers produce similar intensities."""
        try:
            target_intensity = calibration_results["target_intensity"]
            tolerance = target_intensity * 0.1  # 10% tolerance

            # Test IR LED with calibrated power
            self.esp32_controller.select_led_type("ir")
            time.sleep(1.0)  # Allow stabilization
            ir_frame, _ = self._safe_capture_frame()
            ir_measured = self._measure_frame_intensity(ir_frame, 0.5, 75)

            # Test WhiteLight LED with calibrated power
            self.esp32_controller.select_led_type("white")
            time.sleep(1.0)  # Allow stabilization
            whitelight_frame, _ = self._safe_capture_frame()
            whitelight_measured = self._measure_frame_intensity(whitelight_frame, 0.5, 75)

            # Check if intensities match within tolerance
            intensity_diff = abs(ir_measured - whitelight_measured)
            calibration_accuracy = (
                (1 - intensity_diff / target_intensity) * 100 if target_intensity > 0 else 0
            )

            if intensity_diff < tolerance:
                self._add_log_entry(
                    f"✓ Calibration verified: IR={ir_measured:.1f}, WhiteLight={whitelight_measured:.1f} "
                    f"(diff={intensity_diff:.1f}, accuracy={calibration_accuracy:.1f}%)"
                )
                return True
            else:
                self._add_log_entry(
                    f"⚠ Calibration may be inaccurate: IR={ir_measured:.1f}, WhiteLight={whitelight_measured:.1f} "
                    f"(diff={intensity_diff:.1f}, tolerance={tolerance:.1f})"
                )
                return False

        except Exception as e:
            self._add_log_entry(f"Calibration verification failed: {e}")
            return False

    # ========================================================================
    # ✅ NEW: PHASE CONTROL METHODS
    # ========================================================================

    def _toggle_phase_controls(self):
        """Enable/disable phase controls based on checkbox state."""
        enabled = self.enable_day_night_checkbox.isChecked()

        for widget in self.phase_control_widgets:
            widget.setEnabled(enabled)

        # Update labels visibility
        if hasattr(self, "phase_info_layout"):
            for i in range(self.phase_info_layout.count()):
                item = self.phase_info_layout.itemAt(i)
                if item.widget():
                    item.widget().setVisible(enabled)

        # Update statistics
        self._update_expected_frames()

        if enabled:
            self._add_log_entry("Day/Night cycling enabled")
            self.phase_stats_label.setStyleSheet("color: #00ff00;")
        else:
            self._add_log_entry("Day/Night cycling disabled - continuous recording")
            self.phase_stats_label.setStyleSheet("color: #888888;")

    def _get_current_phase_info(self, elapsed_minutes: float) -> dict:
        """Calculate current phase information based on elapsed time."""
        if (
            not hasattr(self, "enable_day_night_checkbox")
            or not self.enable_day_night_checkbox.isChecked()
        ):
            return {
                "phase": "continuous",
                "led_type": "ir",  # Default to IR for backward compatibility
                "phase_elapsed_min": elapsed_minutes,
                "phase_remaining_min": 0,
                "cycle_number": 1,
                "total_cycles": 1,
            }

        light_duration = self.light_phase_spinbox.value()
        dark_duration = self.dark_phase_spinbox.value()
        cycle_duration = light_duration + dark_duration

        # Determine starting phase
        starts_with_light = self.start_phase_combo.currentIndex() == 0

        # Calculate position in cycles
        cycle_position = elapsed_minutes % cycle_duration
        current_cycle = int(elapsed_minutes / cycle_duration) + 1
        total_duration = self.duration_spinbox.value()
        total_cycles = max(1, int(total_duration / cycle_duration))

        # Determine current phase
        if starts_with_light:
            if cycle_position < light_duration:
                phase = "light"
                led_type = "white"
                phase_elapsed = cycle_position
                phase_remaining = light_duration - cycle_position
            else:
                phase = "dark"
                led_type = "ir"
                phase_elapsed = cycle_position - light_duration
                phase_remaining = cycle_duration - cycle_position
        else:
            if cycle_position < dark_duration:
                phase = "dark"
                led_type = "ir"
                phase_elapsed = cycle_position
                phase_remaining = dark_duration - cycle_position
            else:
                phase = "light"
                led_type = "white"
                phase_elapsed = cycle_position - dark_duration
                phase_remaining = cycle_duration - cycle_position

        return {
            "phase": phase,
            "led_type": led_type,
            "phase_elapsed_min": phase_elapsed,
            "phase_remaining_min": phase_remaining,
            "cycle_number": current_cycle,
            "total_cycles": total_cycles,
        }

    def _update_phase_display(self, phase_info: dict):
        """Update phase display labels."""
        if not hasattr(self, "current_phase_label"):
            return

        if phase_info["phase"] == "continuous":
            self.current_phase_label.setText("Current Phase: Continuous")
            self.current_phase_label.setStyleSheet("color: #888888; font-weight: bold;")
        elif phase_info["phase"] == "light":
            self.current_phase_label.setText("Current Phase: Light (White LED)")
            self.current_phase_label.setStyleSheet("color: #ff8800; font-weight: bold;")
        else:  # dark
            self.current_phase_label.setText("Current Phase: Dark (IR LED)")
            self.current_phase_label.setStyleSheet("color: #4444ff; font-weight: bold;")

        if phase_info["phase"] != "continuous":
            remaining_min = phase_info["phase_remaining_min"]
            remaining_sec = int(remaining_min * 60) % 60
            remaining_min_int = int(remaining_min)

            self.phase_time_remaining_label.setText(
                f"Phase Time Remaining: {remaining_min_int}:{remaining_sec:02d}"
            )
            self.phase_cycles_label.setText(
                f"Cycle: {phase_info['cycle_number']}/{phase_info['total_cycles']}"
            )
        else:
            self.phase_time_remaining_label.setText("Phase Time Remaining: --:--")
            self.phase_cycles_label.setText("Total Cycles: Continuous")

    def _on_phase_changed(self, phase_info: dict):
        """Handle phase change signal from recorder."""
        self._update_phase_display(phase_info)

        led_type = phase_info.get("led_type", "ir")
        phase_name = phase_info.get("phase", "unknown")
        cycle_num = phase_info.get("cycle_number", 1)

        self._add_log_entry(
            f"Phase changed: {phase_name.upper()} phase (cycle {cycle_num}) - using {led_type.upper()} LED"
        )

        # Update ESP32 LED selection if available
        if hasattr(self.esp32_controller, "select_led_type"):
            try:
                self.esp32_controller.select_led_type(led_type)
                self._add_log_entry(f"ESP32 LED switched to {led_type.upper()}")
            except Exception as e:
                self._add_log_entry(f"Failed to switch ESP32 LED: {e}")

    # ========================================================================
    # CONNECTION SETUP
    # ========================================================================

    def _setup_connections(self):
        """Setup signal connections - UPDATED with phase controls."""
        # Existing UI connections
        self.duration_spinbox.valueChanged.connect(self._update_expected_frames)
        self.interval_spinbox.valueChanged.connect(self._update_expected_frames)
        self.led_power_slider.valueChanged.connect(self._update_led_power)

        # ✅ NEW: Phase control connections
        self.light_phase_spinbox.valueChanged.connect(self._update_expected_frames)
        self.dark_phase_spinbox.valueChanged.connect(self._update_expected_frames)
        self.start_phase_combo.currentIndexChanged.connect(self._update_expected_frames)

        # DataManager connections (existing)
        self.data_manager.file_created.connect(self._on_file_created)
        self.data_manager.frame_saved.connect(self._on_frame_saved)
        self.data_manager.metadata_updated.connect(self._on_metadata_updated)

        # ESP32 controller connections (existing)
        self.esp32_controller.connection_status_changed.connect(self._on_esp32_conn_changed)
        self.esp32_controller.led_status_changed.connect(self._on_led_status_changed)

    def _setup_timers(self):
        """Setup periodic timers."""
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self._update_status)
        self.status_timer.start(2000)

        # Add initial log entries
        self._add_log_entry("Plugin initialized successfully with Day/Night phase support")
        if self.imswitch_main is None:
            self._add_log_entry("ImSwitch not available - trying auto-detection...")
            # Try one more time to find ImSwitch
            self.imswitch_main = self._find_imswitch_controller()
            if self.imswitch_main:
                self._add_log_entry("SUCCESS: ImSwitch auto-detected on retry!")
                # Update camera connection status
                self.camera_connected = self._check_camera_connection()
        else:
            self._add_log_entry("ImSwitch integration active")

    # =========================================================================
    # EVENT HANDLERS
    # =========================================================================

    def _select_directory(self):
        """Select recording directory."""
        directory = QFileDialog.getExistingDirectory(self, "Select Recording Directory")
        if directory:
            self.directory_edit.setText(directory)
            self._add_log_entry(f"Recording directory set: {directory}")

    def _update_expected_frames(self):
        """Update expected frames calculation with phase support."""
        duration_min = self.duration_spinbox.value()
        interval_sec = self.interval_spinbox.value()

        total_seconds = duration_min * 60
        expected_frames = total_seconds // interval_sec

        # Update basic stats
        self.expected_frames_label.setText(str(expected_frames))
        self.frames_label.setText(f"● Frames: {expected_frames}")
        self.duration_label.setText(f"● Duration: {duration_min}.0 min")
        self.intervals_label.setText(f"● Intervals: {interval_sec}.0 sec")

        # Update phase statistics
        if (
            hasattr(self, "enable_day_night_checkbox")
            and self.enable_day_night_checkbox.isChecked()
        ):
            light_min = self.light_phase_spinbox.value()
            dark_min = self.dark_phase_spinbox.value()
            cycle_duration = light_min + dark_min

            if cycle_duration > 0:
                total_cycles = duration_min / cycle_duration
                light_frames = (light_min * 60) // interval_sec
                dark_frames = (dark_min * 60) // interval_sec

                self.phase_stats_label.setText(
                    f"● Phase Pattern: {total_cycles:.1f} cycles | "
                    f"Light: {light_frames} frames | Dark: {dark_frames} frames"
                )

                # Calculate cycle information
                complete_cycles = int(total_cycles)
                partial_cycle_min = (total_cycles - complete_cycles) * cycle_duration

                self.phase_cycles_label.setText(
                    f"Total Cycles: {complete_cycles} complete + {partial_cycle_min:.1f}min partial"
                )
            else:
                self.phase_stats_label.setText("● Phase Pattern: Invalid (zero duration)")
        else:
            self.phase_stats_label.setText("● Phase Pattern: Continuous recording")

    def _update_led_power(self):
        """Update LED power display."""
        power = self.led_power_slider.value()
        self.led_power_value_label.setText(f"{power}%")
        self.led_on_button.setText(f"💡 LED ON ({power}%)")

        try:
            if self.esp32_controller.is_connected():
                self.esp32_controller.set_led_power(power)
                self.esp32_status_label.setText(f"ESP32: Connected - LED Power: {power}%")
        except Exception as e:
            self._add_log_entry(f"LED power update failed: {e}")

    def _connect_esp32(self):
        """FIXED: Use protected ESP32 connection."""
        try:
            self._add_log_entry("Starting protected ESP32 connection...")

            # ✅ CRITICAL: Use the protected method
            success = self.esp32_controller.connect_with_imswitch_protection()

            if success:
                status = self.esp32_controller.get_status()
                led_status = self.esp32_controller.get_led_status()

                current_led = led_status.get("current_led_type", "unknown")
                communication_recovered = led_status.get("communication_recovered", False)

                if communication_recovered:
                    self._add_log_entry("✓ Communication was recovered during connection")

                self._add_log_entry(f"ESP32 connected: Active LED = {current_led.upper()}")
                self.esp32_status_label.setText(f"ESP32: Connected ({current_led.upper()})")
                self.esp32_status_label_right.setText("ESP32: Connected")

                # Test LED switching
                try:
                    original_led = self.esp32_controller.current_led_type
                    self.esp32_controller.select_led_type("ir")
                    time.sleep(0.1)
                    self.esp32_controller.select_led_type("white")
                    time.sleep(0.1)
                    self.esp32_controller.select_led_type(original_led)
                    self._add_log_entry("LED switching test passed")
                except Exception as led_test_e:
                    self._add_log_entry(f"LED switching test failed: {led_test_e}")

            else:
                self._add_log_entry("ESP32 connection failed")
                self.esp32_status_label.setText("ESP32: Connection Failed")

        except Exception as e:
            error_msg = f"ESP32 connection error: {e}"
            self._add_log_entry(error_msg)
            self.esp32_status_label.setText("ESP32: Connection Error")

    # ✅ WIDGET INTEGRATION: Update your widget's connect method
    def widget_connect_esp32_protected(self):
        """Widget method - use this in your main widget instead of _connect_esp32."""
        try:
            self._add_log_entry("Starting protected ESP32 connection...")

            # Use the protected connection method
            success = self.esp32_controller.connect_with_imswitch_protection()

            if success:
                # Get detailed status
                try:
                    status = self.esp32_controller.get_status()
                    led_status = self.esp32_controller.get_led_status()

                    firmware_info = led_status.get("response_header", "unknown")
                    current_led = led_status.get("current_led_type", "unknown")

                    self._add_log_entry(f"ESP32 connected successfully!")
                    self._add_log_entry(
                        f"Firmware: {firmware_info}, Active LED: {current_led.upper()}"
                    )

                    # Update UI
                    self.esp32_status_label.setText(f"ESP32: Connected ({current_led.upper()})")
                    self.esp32_status_label_right.setText("ESP32: Connected")

                    # Test LED switching to verify full functionality
                    try:
                        original_led = self.esp32_controller.current_led_type
                        self.esp32_controller.select_led_type("ir")
                        time.sleep(0.1)
                        self.esp32_controller.select_led_type("white")
                        time.sleep(0.1)
                        self.esp32_controller.select_led_type(original_led)
                        self._add_log_entry("LED switching test passed")
                    except Exception as led_test_e:
                        self._add_log_entry(f"LED switching test failed: {led_test_e}")

                except Exception as status_e:
                    self._add_log_entry(f"ESP32 connected but status read failed: {status_e}")
                    self.esp32_status_label.setText("ESP32: Connected (Status Unknown)")
            else:
                self._add_log_entry("ESP32 connection failed")
                self.esp32_status_label.setText("ESP32: Connection Failed")

        except Exception as e:
            error_msg = f"Protected ESP32 connection failed: {str(e)}"
            self._add_log_entry(error_msg)
            self.esp32_status_label.setText("ESP32: Connection Error")

    def _disconnect_esp32(self):
        """Disconnect from ESP32."""
        try:
            self.esp32_controller.disconnect()
            self._add_log_entry("ESP32 disconnected")
            self.esp32_status_label.setText("ESP32: Disconnected")
            self.esp32_status_label_right.setText("ESP32: Disconnected")
        except Exception as e:
            self._add_log_entry(f"ESP32 disconnect error: {e}")

    def _led_on(self):
        """Turn LED on."""
        try:
            self.esp32_controller.led_on()
            self._add_log_entry(f"LED command sent: ON at {self.led_power_slider.value()}%")
        except Exception as e:
            self._add_log_entry(f"LED on failed: {str(e)}")

    def _led_off(self):
        """Turn LED off."""
        try:
            self.esp32_controller.led_off()
            self._add_log_entry("LED command sent: OFF")
        except Exception as e:
            self._add_log_entry(f"LED off failed: {str(e)}")

    def _manual_flash(self):
        """Manual LED flash."""
        try:
            timing_info = self.esp32_controller.synchronize_capture()
            temp = timing_info.get("temperature", 0)
            humidity = timing_info.get("humidity", 0)
            duration = timing_info.get("led_duration_actual", 0)

            self._add_log_entry(f"Manual flash: {duration}ms, T={temp:.1f}°C, H={humidity:.1f}%")

        except Exception as e:
            self._add_log_entry(f"Manual flash failed: {str(e)}")

    def _read_sensors(self):
        """Read environmental sensors."""
        try:
            temp, humidity = self.esp32_controller.read_sensors()
            self.temperature_label.setText(f"{temp:.1f}°C")
            self.humidity_label.setText(f"{humidity:.1f}%")
            self._add_log_entry(f"Temperature: {temp:.1f}°C, Humidity: {humidity:.1f}%")
        except Exception as e:
            self._add_log_entry(f"Sensor reading failed: {str(e)}")

    def _debug_esp32_communication(self):
        """Debug ESP32 communication step by step."""
        self._add_log_entry("=== ESP32 COMMUNICATION DEBUG ===")
        self.test_results_text.clear()

        try:
            # Check basic connection info
            self.test_results_text.append(f"ESP32 Port: {self.esp32_controller.esp32_port}")
            self.test_results_text.append(f"Connected: {self.esp32_controller.connected}")

            if (
                hasattr(self.esp32_controller, "serial_connection")
                and self.esp32_controller.serial_connection
            ):
                self.test_results_text.append(
                    f"Serial Open: {self.esp32_controller.serial_connection.is_open}"
                )
                self.test_results_text.append(
                    f"Serial Port: {self.esp32_controller.serial_connection.port}"
                )
            else:
                self.test_results_text.append("No serial connection available")

            # Test simple command
            self._add_log_entry("Sending raw LED ON command...")
            try:
                if hasattr(self.esp32_controller, "_send_byte"):
                    self.esp32_controller._send_byte(0x01)
                    self.test_results_text.append("✓ LED ON command sent")
                    time.sleep(0.1)

                    self.esp32_controller._send_byte(0x00)
                    self.test_results_text.append("✓ LED OFF command sent")
                else:
                    self.test_results_text.append("✗ _send_byte method not available")
            except Exception as e:
                self.test_results_text.append(f"✗ Command send failed: {e}")

        except Exception as e:
            self.test_results_text.append(f"✗ Debug failed: {e}")

    def _debug_imswitch_structure(self):
        """Debug ImSwitch structure for widget testing."""
        if self.imswitch_main is None:
            self.test_results_text.append("ImSwitch not available")
            return

        self.test_results_text.clear()
        self.test_results_text.append("=== ImSwitch Structure Debug ===")

        # List main attributes
        attrs = [attr for attr in dir(self.imswitch_main) if not attr.startswith("_")]
        self.test_results_text.append(f"ImSwitch attributes: {', '.join(attrs[:10])}...")

        # Check for live view attributes
        live_attrs = ["liveViewWidget", "viewWidget", "imageWidget", "detectorsManager"]
        for attr in live_attrs:
            if hasattr(self.imswitch_main, attr):
                obj = getattr(self.imswitch_main, attr)
                self.test_results_text.append(f"✓ Found {attr}: {type(obj)}")

                # Check for image data attributes
                if hasattr(obj, "img"):
                    img_obj = getattr(obj, "img", None)
                    if img_obj is not None:
                        shape_info = img_obj.shape if hasattr(img_obj, "shape") else type(img_obj)
                        self.test_results_text.append(f"  - Has image data: {shape_info}")
                if hasattr(obj, "getCurrentImage"):
                    self.test_results_text.append(f"  - Has getCurrentImage method")
            else:
                self.test_results_text.append(f"✗ No {attr} found")

        # Check napari layers if available
        if self.viewer is not None:
            layer_names = [layer.name for layer in self.viewer.layers]
            self.test_results_text.append(f"Napari layers: {layer_names}")
        else:
            self.test_results_text.append("No napari viewer available")

    # =========================================================================
    # RECORDING AND TEST METHODS
    # =========================================================================

    def _test_full_system(self):
        """Test full system."""
        try:
            self._add_log_entry("Starting system test...")
            self.test_results_text.clear()

            # Test ESP32
            if self.esp32_controller.is_connected():
                self.test_results_text.append("✓ ESP32 connected")

                try:
                    self.esp32_controller.led_on()
                    time.sleep(0.1)
                    self.esp32_controller.led_off()
                    self.test_results_text.append("✓ LED control working")
                except Exception as e:
                    self.test_results_text.append(f"✗ LED control failed: {e}")

                try:
                    temp, humidity = self.esp32_controller.read_sensors()
                    self.test_results_text.append(f"✓ Sensors: T={temp:.1f}°C, H={humidity:.1f}%")
                except Exception as e:
                    self.test_results_text.append(f"✗ Sensor reading failed: {e}")
            else:
                self.test_results_text.append("✗ ESP32 not connected")

            # Test data manager
            try:
                info = self.data_manager.get_recording_info()
                self.test_results_text.append("✓ Data manager ready")
            except Exception as e:
                self.test_results_text.append(f"✗ Data manager error: {e}")

            self._add_log_entry("System test completed")

        except Exception as e:
            self._add_log_entry(f"System test failed: {str(e)}")
            self.test_results_text.append(f"✗ Test failed: {str(e)}")

    def _quick_frame_test(self):
        """Quick frame capture test using ImSwitch directly."""
        try:
            self._add_log_entry("Quick frame test (ImSwitch direct)...")

            start_time = time.time()
            frame, metadata = self._get_live_napari_frame()
            end_time = time.time()

            capture_time = (end_time - start_time) * 1000  # ms
            fps = 1.0 / (end_time - start_time) if (end_time - start_time) > 0 else 0

            self.fps_label.setText(f"FPS: {fps:.1f}")
            self.test_results_text.clear()
            self.test_results_text.append(f"Frame captured in {capture_time:.1f}ms")
            self.test_results_text.append(f"Frame shape: {frame.shape}")
            self.test_results_text.append(f"Frame dtype: {frame.dtype}")
            self.test_results_text.append(f"Source: {metadata.get('source', 'unknown')}")
            self.test_results_text.append("✓ Widget frame capture working")

            # Display in napari if available
            if self.viewer is not None:
                layer_name = "Quick Test Frame"
                if layer_name in [layer.name for layer in self.viewer.layers]:
                    layer = next(layer for layer in self.viewer.layers if layer.name == layer_name)
                    layer.data = frame
                else:
                    self.viewer.add_image(frame, name=layer_name, colormap="gray")
                self.test_results_text.append("✓ Frame displayed in napari")

            self._add_log_entry(
                f"Quick test: {capture_time:.1f}ms, {fps:.1f} FPS from {metadata.get('source')}"
            )

        except Exception as e:
            self._add_log_entry(f"Quick frame test failed: {str(e)}")
            self.test_results_text.clear()
            self.test_results_text.append(f"✗ Frame test failed: {str(e)}")

    def _get_live_napari_frame(self) -> tuple[np.ndarray, dict]:
        """Get a frame directly from any non-empty Napari image layer for quick tests/fallback."""
        if self.viewer is None:
            raise RuntimeError("No Napari viewer available for fallback")
        for layer in self.viewer.layers:
            try:
                data = getattr(layer, "data", None)
                if data is None:
                    continue
                frame = np.array(data, copy=True)
                if frame.size == 0:
                    continue
                metadata = {
                    "timestamp": time.time(),
                    "camera_name": getattr(self, "camera_name", "unknown"),
                    "frame_shape": frame.shape,
                    "frame_dtype": str(frame.dtype),
                    "source": f"napari_layer:{layer.name}",
                    "fallback": True,
                }
                return frame, metadata
            except Exception:
                continue
        raise RuntimeError("No suitable Napari image layer found for fallback frame")

    def _has_live_layer(self) -> bool:
        if self.viewer is None:
            return False
        from napari.layers import Image

        for layer in self.viewer.layers:
            if not isinstance(layer, Image):
                continue
            data = getattr(layer, "data", None)
            if data is None:
                continue
            try:
                if hasattr(data, "size") and data.size == 0:
                    continue
            except Exception:
                pass
            return True  # any non-empty image layer qualifies
        return False

    def _start_recording(self):
        """Start recording with phase-aware setup."""
        if not self.recording:
            if not self.directory_edit.text():
                self._add_log_entry("Error: No recording directory selected")
                return
            if self.imswitch_main is None and not self._has_live_layer():
                self._add_log_entry(
                    "Error: No ImSwitch controller and no live Napari layer available for capture"
                )
                return

            try:
                # Clean up any existing interfering layers
                self._cleanup_timelapse_layers()

                from ._recorder import TimelapseRecorder

                # ✅ NEW: Pass phase configuration to recorder
                phase_config = {
                    "enabled": self.enable_day_night_checkbox.isChecked(),
                    "light_duration_min": self.light_phase_spinbox.value(),
                    "dark_duration_min": self.dark_phase_spinbox.value(),
                    "start_with_light": self.start_phase_combo.currentIndex() == 0,
                }

                self.recorder = TimelapseRecorder(
                    duration_min=self.duration_spinbox.value(),
                    interval_sec=self.interval_spinbox.value(),
                    output_dir=self.directory_edit.text(),
                    esp32_controller=self.esp32_controller,
                    data_manager=self.data_manager,
                    imswitch_main=self.imswitch_main,
                    camera_name=self.camera_name,
                    phase_config=phase_config,  # ✅ NEW parameter
                )

                # Connect recorder signals
                self.recorder.frame_captured.connect(self._on_frame_captured)
                self.recorder.recording_finished.connect(self._on_recording_finished)
                self.recorder.recording_paused.connect(self._on_recording_paused)
                self.recorder.recording_resumed.connect(self._on_recording_resumed)
                self.recorder.error_occurred.connect(self._on_recording_error)
                self.recorder.progress_updated.connect(self._on_progress_updated)
                self.recorder.status_updated.connect(self._on_status_updated)

                # ✅ NEW: Phase change signal
                if hasattr(self.recorder, "phase_changed"):
                    self.recorder.phase_changed.connect(self._on_phase_changed)

                if self.viewer is None:
                    self._add_log_entry(
                        "Warning: Napari viewer is not connected; fallback capture may fail."
                    )
                else:
                    self.recorder.viewer = self.viewer

                # Start recording
                self.recorder.start()
                self.recording = True
                self.start_button.setText("Recording...")
                self.start_button.setEnabled(False)

                if phase_config["enabled"]:
                    start_phase = "Light" if phase_config["start_with_light"] else "Dark"
                    self._add_log_entry(
                        f"Started day/night timelapse recording (starting with {start_phase} phase)"
                    )
                else:
                    self._add_log_entry("Started continuous timelapse recording")

            except Exception as e:
                self._add_log_entry(f"Failed to start recording: {str(e)}")

    def _pause_recording(self):
        """Pause/resume recording."""
        if self.recorder:
            if hasattr(self.recorder, "is_paused") and self.recorder.is_paused():
                self.recorder.resume()
            else:
                self.recorder.pause()

    def _stop_recording(self):
        """Stop recording."""
        if self.recorder:
            self.recorder.stop()
            self.recording = False
            self.recorder = None
            self.start_button.setText("🎬 Start Recording")
            self.start_button.setEnabled(True)
            self.pause_button.setText("⏸ Pause")
            self._add_log_entry("Recording stopped")

    # =========================================================================
    # SIGNAL HANDLERS
    # =========================================================================

    def _on_file_created(self, filepath: str):
        """Handle file created signal from DataManager."""
        self._add_log_entry(f"Recording file created: {filepath}")
        # Update UI to show file path
        filename = Path(filepath).name
        self.recording_status_label.setText(f"Recording: File Created ({filename})")

    def _on_frame_saved(self, frame_number: int):
        """Handle frame saved signal from DataManager."""
        self._add_log_entry(f"Frame {frame_number} saved to HDF5 file")

    def _on_metadata_updated(self, metadata: dict):
        """Handle metadata updated signal from DataManager."""
        self._add_log_entry("Recording metadata updated")
        # Optional: Display key metadata in the UI
        if "actual_frames" in metadata:
            actual_frames = metadata["actual_frames"]
            expected_frames = metadata.get("expected_frames", 0)
            if expected_frames > 0:
                progress = int((actual_frames / expected_frames) * 100)
                self.progress_bar.setValue(progress)

    def _on_frame_captured(self, current_frame: int, total_frames: int):
        """Handle frame captured signal - NO NAPARI LAYER CREATION."""
        self.frame_info_label.setText(f"Frame: {current_frame}/{total_frames}")
        self._add_log_entry(f"Frame {current_frame}/{total_frames} captured")

        # Keep only the essential UI updates:
        progress = int((current_frame / total_frames) * 100) if total_frames > 0 else 0
        self.progress_bar.setValue(progress)

    def _cleanup_timelapse_layers(self):
        """Remove any existing Timelapse Live layers that interfere with live view."""
        if self.viewer is None:
            return

        layers_to_remove = []
        for layer in self.viewer.layers:
            layer_name = getattr(layer, "name", "").lower()

            # Find layers that might interfere
            if any(
                keyword in layer_name
                for keyword in ["timelapse live", "timelapse_live", "captured frames"]
            ):
                layers_to_remove.append(layer)

        # Remove interfering layers
        for layer in layers_to_remove:
            try:
                self.viewer.layers.remove(layer)
                self._add_log_entry(f"Removed interfering layer: {layer.name}")
            except Exception as e:
                print(f"Could not remove layer {layer.name}: {e}")

    def _on_recording_finished(self):
        """Handle recording finished signal."""
        self.recording = False
        self.start_button.setText("🎬 Start Recording")
        self.start_button.setEnabled(True)
        self.pause_button.setText("⏸ Pause")
        self.progress_bar.setValue(100)
        self._add_log_entry("Recording completed successfully")

    def _on_recording_paused(self):
        """Handle recording paused signal."""
        self.pause_button.setText("▶ Resume")
        self._add_log_entry("Recording paused")

    def _on_recording_resumed(self):
        """Handle recording resumed signal."""
        self.pause_button.setText("⏸ Pause")
        self._add_log_entry("Recording resumed")

    def _on_recording_error(self, error_message: str):
        """Enhanced recording error handling."""
        self._add_log_entry(f"Recording error: {error_message}")
        self.recording = False
        self.start_button.setText("🎬 Start Recording")
        self.start_button.setEnabled(True)

        # ✅ NEW: Handle specific error types
        if "LED" in error_message or "ESP32" in error_message:
            self._add_log_entry("CRITICAL: Hardware error detected - recording stopped for safety")
            self.esp32_status_label.setText("ESP32: Hardware Error")
            self.esp32_status_label.setStyleSheet("color: #ff0000;")
        elif "memory" in error_message.lower():
            self._add_log_entry("CRITICAL: Memory error - system may be overloaded")
        elif "frame capture" in error_message.lower():
            self._add_log_entry("CRITICAL: Frame capture failed - check camera connection")

    def _on_progress_updated(self, progress_percent: int):
        """Handle progress update signal."""
        self.progress_bar.setValue(progress_percent)

    def _on_status_updated(self, status_message: str):
        """Handle status update signal."""
        # Parse status message to update UI elements
        if "Frame" in status_message and "/" in status_message:
            # Extract frame info
            parts = status_message.split("-")
            if len(parts) > 0:
                frame_part = parts[0].strip()
                self.frame_info_label.setText(frame_part)

            # Extract timing info
            if "Elapsed:" in status_message:
                elapsed_part = [p for p in parts if "Elapsed:" in p]
                if elapsed_part:
                    self.elapsed_label.setText(elapsed_part[0].strip())

            if "Remaining:" in status_message:
                remaining_part = [p for p in parts if "Remaining:" in p]
                if remaining_part:
                    eta_text = remaining_part[0].strip().replace("Remaining:", "ETA:")
                    self.eta_label.setText(eta_text)

    def _update_status(self):
        """Update system status - ENHANCED with phase info."""
        # Safety check
        try:
            if not hasattr(self, "camera_status_label") or self.camera_status_label is None:
                return
            self.camera_status_label.text()
        except (RuntimeError, AttributeError):
            if hasattr(self, "status_timer"):
                self.status_timer.stop()
            return

        # Auto-detect napari viewer if not available
        if self.viewer is None:
            try:
                import napari

                current_viewer = napari.current_viewer()
                if current_viewer is not None and current_viewer != self.viewer:
                    self.viewer = current_viewer
                    self.camera_connected = self._check_camera_connection()
                    self._add_log_entry("Napari viewer auto-detected - camera status updated")
            except:
                pass

        # Camera status
        try:
            camera_ready = self._check_camera_connection()
        except Exception as e:
            self.camera_status_label.setText("Camera: Error")
            self.camera_status_label.setStyleSheet("color: #ff0000;")
            print(f"Camera status check failed: {e}")

        # ESP32 status
        try:
            if self.esp32_controller.is_connected():
                self.esp32_status_label_right.setText("ESP32: Connected")
                self.esp32_status_label_right.setStyleSheet("color: #00ff00;")
            else:
                self.esp32_status_label_right.setText("ESP32: Disconnected")
                self.esp32_status_label_right.setStyleSheet("color: #ff0000;")
        except:
            self.esp32_status_label_right.setText("ESP32: Error")
            self.esp32_status_label_right.setStyleSheet("color: #ff0000;")

        # ✅ NEW: Recording status with phase info
        if self.recording:
            if hasattr(self, "recorder") and self.recorder:
                try:
                    # Get current recording time
                    elapsed_min = (time.time() - self.recorder.start_time) / 60.0
                    phase_info = self._get_current_phase_info(elapsed_min)
                    self._update_phase_display(phase_info)

                    self.recording_status_label.setText("Recording: Active (Phase-aware)")
                    self.recording_status_label.setStyleSheet("color: #ffff00;")
                except:
                    self.recording_status_label.setText("Recording: Active")
                    self.recording_status_label.setStyleSheet("color: #ffff00;")
            else:
                self.recording_status_label.setText("Recording: Active")
                self.recording_status_label.setStyleSheet("color: #ffff00;")
        else:
            self.recording_status_label.setText("Recording: Ready")
            self.recording_status_label.setStyleSheet("color: #00ff00;")

    def closeEvent(self, event):
        """Handle widget close event."""
        try:
            # Stop timer
            if hasattr(self, "status_timer"):
                self.status_timer.stop()

            # Disconnect ESP32
            if hasattr(self, "esp32_controller"):
                try:
                    self.esp32_controller.disconnect()
                except:
                    pass

            # Stop any recording
            if hasattr(self, "recorder") and self.recorder:
                try:
                    self.recorder.stop()
                except:
                    pass

            print("Widget cleanup completed")
        except Exception as e:
            print(f"Cleanup error: {e}")

        event.accept()

    def _on_esp32_conn_changed(self, connected: bool):
        """Handle ESP32 connection status change."""
        text = "ESP32: Connected" if connected else "ESP32: Disconnected"
        color = "#00ff00" if connected else "#ff0000"
        self.esp32_status_label.setText(text)
        self.esp32_status_label.setStyleSheet(f"color: {color};")
        self.esp32_status_label_right.setText(text)
        self.esp32_status_label_right.setStyleSheet(f"color: {color};")

    def _on_led_status_changed(self, is_on: bool, power: int):
        """Handle LED status change."""
        if is_on:
            self.esp32_status_label.setText(f"ESP32: LED ON – {power}%")
            self.esp32_status_label.setStyleSheet("color: #00ff00;")
            self._add_log_entry(f"LED status: ON at {power}% power")
        else:
            self.esp32_status_label.setText("ESP32: LED OFF")
            self.esp32_status_label.setStyleSheet("color: #ff0000;")
            self._add_log_entry("LED status: OFF")

    def connect_to_napari(self, viewer):
        """Connect the plugin to a napari viewer."""
        self.viewer = viewer
        self._add_log_entry("Connected to napari viewer")


# ✅ Create widget function
def create_timelapse_widget(napari_viewer=None):
    """Create and return the timelapse widget."""
    return NematostallTimelapseCaptureWidget(napari_viewer, None)


# ✅ NPE1 hook for backward compatibility
from napari_plugin_engine import napari_hook_implementation


@napari_hook_implementation
def napari_experimental_provide_dock_widget():
    """Provide the timelapse capture dock widget."""

    def create_widget():
        # Get napari viewer if available
        try:
            import napari

            viewer = napari.current_viewer()
        except:
            viewer = None

        widget = NematostallTimelapseCaptureWidget(viewer, None)
        return widget

    return create_widget
