"""
Nematostella Time-Series Capture Plugin for napari
Optimized for minimal frame drift and synchronized LED control
Version 4.0
"""

import os
import time
from datetime import datetime

import numpy as np
from qtpy.QtCore import Qt, QTimer
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

from .capture_controller import CaptureController, CaptureMode

# Import our optimized components
# from .esp32_controller import ESP32Controller
# from .hik_camera_thread import HIKCameraThread, _HAS_HIK_SDK
# from .recording_manager import RecordingManager
# from .capture_controller import CaptureController, CaptureMode
# In main_plugin.py, esp32_controller.py, etc.
# Relative imports verwenden:
from .esp32_controller import ESP32Controller
from .hik_camera_thread import HIKCameraThread
from .recording_manager import RecordingManager


class NematostellaTimeSeriesCapture(QWidget):
    """Main plugin widget - streamlined version"""

    def __init__(self, napari_viewer):
        super().__init__()
        self.viewer = napari_viewer

        # Detect mode
        self.mode = self._detect_mode()
        self.capture_mode = (
            CaptureMode.IMSWITCH if self.mode == "imswitch" else CaptureMode.STANDALONE
        )

        # Core components
        self.esp32_controller = ESP32Controller()
        self.camera_thread = (
            HIKCameraThread() if self.capture_mode == CaptureMode.STANDALONE else None
        )
        self.recording_manager = RecordingManager(napari_viewer)
        self.capture_controller = CaptureController(self.capture_mode)

        # State
        self.camera_connected = False
        self.available_cameras = []
        self.save_directory = None
        self.recording_state = {
            "start_time": 0,
            "interval": 0,
            "total_frames": 0,
            "next_frame_time": 0,
        }

        # UI references
        self.ui_elements = {}

        # Recording timer
        self.capture_timer = QTimer(self)
        self.capture_timer.timeout.connect(self._on_capture_timeout)
        self.capture_timer.setTimerType(Qt.PreciseTimer)  # High precision

        # Setup
        self._setup_ui()
        self._initialize_system()

    def _detect_mode(self) -> str:
        """Detect if ImSwitch is available"""
        if hasattr(self.viewer, "layers"):
            for layer in self.viewer.layers:
                if any(indicator in layer.name for indicator in ["Live:", "Widefield", "Camera"]):
                    return "imswitch"
        return "standalone"

    def _setup_ui(self):
        """Create streamlined UI"""
        # Main layout with splitter
        main_layout = QHBoxLayout()
        splitter = QSplitter()

        # Left panel - Controls
        control_widget = QWidget()
        control_layout = QVBoxLayout()

        # Mode indicator
        mode_label = QLabel(f"Mode: {self.mode.upper()}")
        mode_label.setStyleSheet("font-weight: bold; color: #4CAF50; padding: 5px;")
        control_layout.addWidget(mode_label)

        # Tab widget
        tabs = QTabWidget()

        # Camera tab (only for standalone mode)
        if self.capture_mode == CaptureMode.STANDALONE:
            tabs.addTab(self._create_camera_tab(), "Camera")
        else:
            tabs.addTab(self._create_imswitch_tab(), "ImSwitch")

        tabs.addTab(self._create_recording_tab(), "Recording")
        tabs.addTab(self._create_esp32_tab(), "LED Control")
        tabs.addTab(self._create_diagnostics_tab(), "Diagnostics")

        control_layout.addWidget(tabs)
        control_widget.setLayout(control_layout)

        # Right panel - Status
        status_widget = self._create_status_panel()

        # Add to splitter
        splitter.addWidget(control_widget)
        splitter.addWidget(status_widget)
        splitter.setSizes([600, 300])

        main_layout.addWidget(splitter)
        self.setLayout(main_layout)

    def _create_camera_tab(self) -> QWidget:
        """Camera control tab for standalone mode"""
        widget = QWidget()
        layout = QVBoxLayout()

        # Camera selection
        camera_group = QGroupBox("Camera Selection")
        camera_layout = QVBoxLayout()

        # Discovery
        discover_btn = QPushButton("🔍 Discover Cameras")
        discover_btn.clicked.connect(self._discover_cameras)
        camera_layout.addWidget(discover_btn)

        self.ui_elements["camera_combo"] = QComboBox()
        self.ui_elements["camera_combo"].setMinimumWidth(300)
        camera_layout.addWidget(self.ui_elements["camera_combo"])

        # Connection
        conn_layout = QHBoxLayout()
        self.ui_elements["connect_btn"] = QPushButton("🔗 Connect")
        self.ui_elements["connect_btn"].clicked.connect(self._connect_camera)
        self.ui_elements["connect_btn"].setEnabled(False)
        conn_layout.addWidget(self.ui_elements["connect_btn"])

        self.ui_elements["disconnect_btn"] = QPushButton("❌ Disconnect")
        self.ui_elements["disconnect_btn"].clicked.connect(self._disconnect_camera)
        self.ui_elements["disconnect_btn"].setEnabled(False)
        conn_layout.addWidget(self.ui_elements["disconnect_btn"])

        camera_layout.addLayout(conn_layout)
        camera_group.setLayout(camera_layout)
        layout.addWidget(camera_group)

        # Settings
        settings_group = QGroupBox("Camera Settings")
        settings_layout = QVBoxLayout()

        # Exposure
        exp_layout = QHBoxLayout()
        exp_layout.addWidget(QLabel("Exposure (μs):"))
        self.ui_elements["exposure_spin"] = QSpinBox()
        self.ui_elements["exposure_spin"].setRange(100, 1000000)
        self.ui_elements["exposure_spin"].setValue(10000)
        self.ui_elements["exposure_spin"].valueChanged.connect(self._on_exposure_changed)
        exp_layout.addWidget(self.ui_elements["exposure_spin"])
        settings_layout.addLayout(exp_layout)

        # Trigger mode
        trigger_layout = QHBoxLayout()
        trigger_layout.addWidget(QLabel("Trigger Mode:"))
        self.ui_elements["trigger_combo"] = QComboBox()
        self.ui_elements["trigger_combo"].addItems(["Free Running", "Software Trigger"])
        self.ui_elements["trigger_combo"].currentTextChanged.connect(self._on_trigger_changed)
        trigger_layout.addWidget(self.ui_elements["trigger_combo"])
        settings_layout.addLayout(trigger_layout)

        # Optimize button
        optimize_btn = QPushButton("⚡ Optimize for Time-lapse")
        optimize_btn.clicked.connect(self._optimize_camera)
        settings_layout.addWidget(optimize_btn)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # Live view
        live_group = QGroupBox("Live View")
        live_layout = QHBoxLayout()

        self.ui_elements["start_live_btn"] = QPushButton("▶️ Start Live")
        self.ui_elements["start_live_btn"].clicked.connect(self._start_live_view)
        self.ui_elements["start_live_btn"].setEnabled(False)
        live_layout.addWidget(self.ui_elements["start_live_btn"])

        self.ui_elements["stop_live_btn"] = QPushButton("⏹️ Stop Live")
        self.ui_elements["stop_live_btn"].clicked.connect(self._stop_live_view)
        self.ui_elements["stop_live_btn"].setEnabled(False)
        live_layout.addWidget(self.ui_elements["stop_live_btn"])

        live_group.setLayout(live_layout)
        layout.addWidget(live_group)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def _create_imswitch_tab(self) -> QWidget:
        """ImSwitch info tab"""
        widget = QWidget()
        layout = QVBoxLayout()

        info_group = QGroupBox("ImSwitch Frame Grabber")
        info_layout = QVBoxLayout()

        info_text = QLabel(
            "This plugin is using ImSwitch frame grabber mode.\n\n"
            "The plugin will capture frames from the active ImSwitch live view layer.\n"
            "Make sure ImSwitch is running with live view enabled."
        )
        info_text.setWordWrap(True)
        info_layout.addWidget(info_text)

        # Layer info
        layer_layout = QHBoxLayout()
        layer_layout.addWidget(QLabel("Active Layer:"))
        self.ui_elements["layer_label"] = QLabel("Not detected")
        self.ui_elements["layer_label"].setStyleSheet("font-weight: bold;")
        layer_layout.addWidget(self.ui_elements["layer_label"])
        layer_layout.addStretch()
        info_layout.addLayout(layer_layout)

        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh Layer Detection")
        refresh_btn.clicked.connect(self._refresh_imswitch_layer)
        info_layout.addWidget(refresh_btn)

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def _create_recording_tab(self) -> QWidget:
        """Recording control tab"""
        widget = QWidget()
        layout = QVBoxLayout()

        # Parameters
        params_group = QGroupBox("Recording Parameters")
        params_layout = QVBoxLayout()

        # Duration and interval
        timing_layout = QHBoxLayout()

        duration_widget = QWidget()
        duration_layout = QVBoxLayout()
        duration_layout.addWidget(QLabel("Duration (min):"))
        self.ui_elements["duration_input"] = QLineEdit("60")
        self.ui_elements["duration_input"].textChanged.connect(self._calculate_frames)
        duration_layout.addWidget(self.ui_elements["duration_input"])
        duration_widget.setLayout(duration_layout)
        timing_layout.addWidget(duration_widget)

        interval_widget = QWidget()
        interval_layout = QVBoxLayout()
        interval_layout.addWidget(QLabel("Interval (sec):"))
        self.ui_elements["interval_input"] = QLineEdit("30")
        self.ui_elements["interval_input"].textChanged.connect(self._calculate_frames)
        interval_layout.addWidget(self.ui_elements["interval_input"])
        interval_widget.setLayout(interval_layout)
        timing_layout.addWidget(interval_widget)

        frames_widget = QWidget()
        frames_layout = QVBoxLayout()
        frames_layout.addWidget(QLabel("Total Frames:"))
        self.ui_elements["frames_label"] = QLabel("--")
        self.ui_elements["frames_label"].setStyleSheet("font-weight: bold; font-size: 14px;")
        frames_layout.addWidget(self.ui_elements["frames_label"])
        frames_widget.setLayout(frames_layout)
        timing_layout.addWidget(frames_widget)

        params_layout.addLayout(timing_layout)

        # Statistics
        self.ui_elements["stats_label"] = QLabel("Enter parameters to see statistics")
        self.ui_elements["stats_label"].setStyleSheet(
            "background-color: #2a2a2a; padding: 8px; border-radius: 4px;"
        )
        self.ui_elements["stats_label"].setWordWrap(True)
        params_layout.addWidget(self.ui_elements["stats_label"])

        params_group.setLayout(params_layout)
        layout.addWidget(params_group)

        # File settings
        file_group = QGroupBox("File Settings")
        file_layout = QVBoxLayout()

        # Directory selection
        dir_layout = QHBoxLayout()
        self.ui_elements["dir_btn"] = QPushButton("📁 Select Directory")
        self.ui_elements["dir_btn"].clicked.connect(self._select_directory)
        dir_layout.addWidget(self.ui_elements["dir_btn"])

        self.ui_elements["dir_label"] = QLabel("No directory selected")
        self.ui_elements["dir_label"].setStyleSheet("color: #888;")
        dir_layout.addWidget(self.ui_elements["dir_label"])
        dir_layout.addStretch()

        file_layout.addLayout(dir_layout)

        self.ui_elements["subfolder_check"] = QCheckBox("Create timestamped subfolder")
        self.ui_elements["subfolder_check"].setChecked(True)
        file_layout.addWidget(self.ui_elements["subfolder_check"])

        file_group.setLayout(file_layout)
        layout.addWidget(file_group)

        # Recording control
        control_group = QGroupBox("Recording Control")
        control_layout = QVBoxLayout()

        # Progress bar
        self.ui_elements["progress_bar"] = QProgressBar()
        self.ui_elements["progress_bar"].setVisible(False)
        control_layout.addWidget(self.ui_elements["progress_bar"])

        # Progress details
        progress_layout = QHBoxLayout()
        self.ui_elements["frame_label"] = QLabel("Frame: 0/0")
        progress_layout.addWidget(self.ui_elements["frame_label"])

        self.ui_elements["elapsed_label"] = QLabel("Elapsed: 00:00:00")
        progress_layout.addWidget(self.ui_elements["elapsed_label"])

        self.ui_elements["eta_label"] = QLabel("ETA: --:--:--")
        progress_layout.addWidget(self.ui_elements["eta_label"])
        progress_layout.addStretch()
        control_layout.addLayout(progress_layout)

        # Control buttons
        btn_layout = QHBoxLayout()

        self.ui_elements["start_btn"] = QPushButton("🎬 Start Recording")
        self.ui_elements["start_btn"].clicked.connect(self._start_recording)
        self.ui_elements["start_btn"].setStyleSheet(
            "background-color: #4CAF50; color: white; font-weight: bold;"
        )
        btn_layout.addWidget(self.ui_elements["start_btn"])

        self.ui_elements["pause_btn"] = QPushButton("⏸️ Pause")
        self.ui_elements["pause_btn"].clicked.connect(self._pause_recording)
        self.ui_elements["pause_btn"].setEnabled(False)
        btn_layout.addWidget(self.ui_elements["pause_btn"])

        self.ui_elements["stop_btn"] = QPushButton("⏹️ Stop")
        self.ui_elements["stop_btn"].clicked.connect(self._stop_recording)
        self.ui_elements["stop_btn"].setEnabled(False)
        self.ui_elements["stop_btn"].setStyleSheet("background-color: #f44336; color: white;")
        btn_layout.addWidget(self.ui_elements["stop_btn"])

        control_layout.addLayout(btn_layout)

        control_group.setLayout(control_layout)
        layout.addWidget(control_group)

        widget.setLayout(layout)
        return widget

    def _create_esp32_tab(self) -> QWidget:
        """ESP32/LED control tab"""
        widget = QWidget()
        layout = QVBoxLayout()

        # Connection
        conn_group = QGroupBox("ESP32 Connection")
        conn_layout = QVBoxLayout()

        conn_btn_layout = QHBoxLayout()
        self.ui_elements["esp32_connect_btn"] = QPushButton("🔗 Connect ESP32")
        self.ui_elements["esp32_connect_btn"].clicked.connect(self._connect_esp32)
        conn_btn_layout.addWidget(self.ui_elements["esp32_connect_btn"])

        self.ui_elements["esp32_disconnect_btn"] = QPushButton("❌ Disconnect")
        self.ui_elements["esp32_disconnect_btn"].clicked.connect(self._disconnect_esp32)
        self.ui_elements["esp32_disconnect_btn"].setEnabled(False)
        conn_btn_layout.addWidget(self.ui_elements["esp32_disconnect_btn"])
        conn_layout.addLayout(conn_btn_layout)

        self.ui_elements["esp32_status"] = QLabel("Status: Not connected")
        self.ui_elements["esp32_status"].setStyleSheet("padding: 5px;")
        conn_layout.addWidget(self.ui_elements["esp32_status"])

        conn_group.setLayout(conn_layout)
        layout.addWidget(conn_group)

        # LED Control
        led_group = QGroupBox("LED Control")
        led_layout = QVBoxLayout()

        # Power control
        power_layout = QHBoxLayout()
        power_layout.addWidget(QLabel("LED Power:"))

        self.ui_elements["led_slider"] = QSlider(Qt.Horizontal)
        self.ui_elements["led_slider"].setRange(0, 100)
        self.ui_elements["led_slider"].setValue(100)
        self.ui_elements["led_slider"].valueChanged.connect(self._on_led_power_changed)
        power_layout.addWidget(self.ui_elements["led_slider"])

        self.ui_elements["led_power_label"] = QLabel("100%")
        self.ui_elements["led_power_label"].setMinimumWidth(40)
        power_layout.addWidget(self.ui_elements["led_power_label"])

        led_layout.addLayout(power_layout)

        # Manual control
        manual_layout = QHBoxLayout()
        self.ui_elements["led_on_btn"] = QPushButton("💡 LED ON")
        self.ui_elements["led_on_btn"].clicked.connect(self._led_on)
        self.ui_elements["led_on_btn"].setEnabled(False)
        manual_layout.addWidget(self.ui_elements["led_on_btn"])

        self.ui_elements["led_off_btn"] = QPushButton("🌑 LED OFF")
        self.ui_elements["led_off_btn"].clicked.connect(self._led_off)
        self.ui_elements["led_off_btn"].setEnabled(False)
        manual_layout.addWidget(self.ui_elements["led_off_btn"])

        led_layout.addLayout(manual_layout)

        # Test button
        test_led_btn = QPushButton("🧪 Test LED Flash")
        test_led_btn.clicked.connect(self._test_led_flash)
        led_layout.addWidget(test_led_btn)

        led_group.setLayout(led_layout)
        layout.addWidget(led_group)

        # Environmental sensors
        sensor_group = QGroupBox("Environmental Sensors")
        sensor_layout = QVBoxLayout()

        sensor_display = QHBoxLayout()

        temp_widget = QWidget()
        temp_layout = QVBoxLayout()
        temp_layout.addWidget(QLabel("Temperature:"))
        self.ui_elements["temp_label"] = QLabel("--°C")
        self.ui_elements["temp_label"].setStyleSheet("font-size: 18px; font-weight: bold;")
        temp_layout.addWidget(self.ui_elements["temp_label"])
        temp_widget.setLayout(temp_layout)
        sensor_display.addWidget(temp_widget)

        humidity_widget = QWidget()
        humidity_layout = QVBoxLayout()
        humidity_layout.addWidget(QLabel("Humidity:"))
        self.ui_elements["humidity_label"] = QLabel("--%")
        self.ui_elements["humidity_label"].setStyleSheet("font-size: 18px; font-weight: bold;")
        humidity_layout.addWidget(self.ui_elements["humidity_label"])
        humidity_widget.setLayout(humidity_layout)
        sensor_display.addWidget(humidity_widget)

        sensor_layout.addLayout(sensor_display)

        read_btn = QPushButton("📊 Read Sensors")
        read_btn.clicked.connect(self._read_sensors)
        sensor_layout.addWidget(read_btn)

        sensor_group.setLayout(sensor_layout)
        layout.addWidget(sensor_group)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def _create_diagnostics_tab(self) -> QWidget:
        """Diagnostics tab"""
        widget = QWidget()
        layout = QVBoxLayout()

        # Test controls
        test_group = QGroupBox("System Tests")
        test_layout = QVBoxLayout()

        # Test buttons grid
        test_grid = QHBoxLayout()

        test_col1 = QVBoxLayout()
        test_capture_btn = QPushButton("🧪 Test Capture")
        test_capture_btn.clicked.connect(self._test_capture)
        test_col1.addWidget(test_capture_btn)

        test_led_btn = QPushButton("💡 Test LED Sync")
        test_led_btn.clicked.connect(self._test_led_sync)
        test_col1.addWidget(test_led_btn)
        test_grid.addLayout(test_col1)

        test_col2 = QVBoxLayout()
        optimize_timing_btn = QPushButton("⚡ Optimize LED Timing")
        optimize_timing_btn.clicked.connect(self._optimize_led_timing)
        test_col2.addWidget(optimize_timing_btn)

        timing_stats_btn = QPushButton("📊 Timing Statistics")
        timing_stats_btn.clicked.connect(self._show_timing_stats)
        test_col2.addWidget(timing_stats_btn)
        test_grid.addLayout(test_col2)

        test_layout.addLayout(test_grid)
        test_group.setLayout(test_layout)
        layout.addWidget(test_group)

        # Performance
        perf_group = QGroupBox("Performance")
        perf_layout = QHBoxLayout()

        self.ui_elements["fps_label"] = QLabel("FPS: --")
        perf_layout.addWidget(self.ui_elements["fps_label"])

        self.ui_elements["drift_label"] = QLabel("Max Drift: --ms")
        perf_layout.addWidget(self.ui_elements["drift_label"])

        self.ui_elements["cpu_label"] = QLabel("CPU: --%")
        perf_layout.addWidget(self.ui_elements["cpu_label"])

        perf_layout.addStretch()
        perf_group.setLayout(perf_layout)
        layout.addWidget(perf_group)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def _create_status_panel(self) -> QWidget:
        """Create status panel"""
        widget = QWidget()
        layout = QVBoxLayout()

        # System status
        status_group = QGroupBox("System Status")
        status_layout = QVBoxLayout()

        self.ui_elements["camera_status"] = QLabel("Camera: Not connected")
        status_layout.addWidget(self.ui_elements["camera_status"])

        self.ui_elements["esp32_status_2"] = QLabel("ESP32: Not connected")
        status_layout.addWidget(self.ui_elements["esp32_status_2"])

        self.ui_elements["recording_status"] = QLabel("Recording: Ready")
        status_layout.addWidget(self.ui_elements["recording_status"])

        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # Log display
        log_group = QGroupBox("System Log")
        log_layout = QVBoxLayout()

        self.ui_elements["log_display"] = QTextEdit()
        self.ui_elements["log_display"].setReadOnly(True)
        self.ui_elements["log_display"].setStyleSheet(
            "background-color: #1a1a1a; color: #00ff00; font-family: monospace; font-size: 10px;"
        )
        log_layout.addWidget(self.ui_elements["log_display"])

        # Clear button
        clear_btn = QPushButton("Clear Log")
        clear_btn.clicked.connect(lambda: self.ui_elements["log_display"].clear())
        log_layout.addWidget(clear_btn)

        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        widget.setLayout(layout)
        return widget

    def _initialize_system(self):
        """Initialize system components"""
        self._log("🚀 Initializing Nematostella Time-Series Capture v4.0")

        # Setup capture controller
        self.capture_controller.set_esp32_controller(self.esp32_controller)

        # Mode-specific initialization
        if self.capture_mode == CaptureMode.IMSWITCH:
            self._setup_imswitch_mode()
        else:
            self._setup_standalone_mode()

        # Try to connect ESP32
        if self.esp32_controller.connect():
            self._enable_esp32_controls(True)
            self._log("✅ ESP32 connected automatically")
        else:
            self._log("ℹ️ ESP32 not found - manual connection required")

        # Calculate initial frames
        self._calculate_frames()

    def _setup_imswitch_mode(self):
        """Setup for ImSwitch frame grabbing"""
        self._refresh_imswitch_layer()

    def _refresh_imswitch_layer(self):
        """Refresh ImSwitch layer detection"""
        # Find ImSwitch live layer
        live_layer = None
        for layer in self.viewer.layers:
            if any(indicator in layer.name for indicator in ["Live:", "Widefield", "Camera"]):
                live_layer = layer
                break

        if live_layer:
            self.capture_controller.set_camera_source(live_layer)
            self.camera_connected = True
            self.ui_elements["layer_label"].setText(live_layer.name)
            self.ui_elements["layer_label"].setStyleSheet("color: green;")
            self.ui_elements["camera_status"].setText("Camera: ImSwitch Connected")
            self._log(f"✅ ImSwitch mode: using layer '{live_layer.name}'")
        else:
            self.camera_connected = False
            self.ui_elements["layer_label"].setText("No live layer found")
            self.ui_elements["layer_label"].setStyleSheet("color: red;")
            self.ui_elements["camera_status"].setText("Camera: No ImSwitch layer")
            self._log("⚠️ No ImSwitch live layer found")

    def _setup_standalone_mode(self):
        """Setup for standalone camera operation"""
        if self.camera_thread:
            # Connect signals
            self.camera_thread.error_occurred.connect(lambda msg: self._log(f"❌ {msg}"))
            self.camera_thread.status_changed.connect(self._on_camera_status_changed)
            self.camera_thread.frame_ready.connect(self._on_camera_frame)

    def _on_camera_status_changed(self, status: str):
        """Handle camera status change"""
        self.ui_elements["camera_status"].setText(f"Camera: {status}")

    def _on_camera_frame(self, frame: np.ndarray):
        """Handle new camera frame"""
        # Display in napari
        if hasattr(self, "live_layer"):
            self.live_layer.data = frame
        else:
            self.live_layer = self.viewer.add_image(frame, name="Camera Live View")

    # Camera control methods (standalone mode only)
    def _discover_cameras(self):
        """Discover available cameras"""
        if not _HAS_HIK_SDK:
            self._log("❌ HIK SDK not available")
            QMessageBox.warning(
                self, "SDK Missing", "HIK SDK not found. Please install hikrobotcamlib."
            )
            return

        self._log("🔍 Discovering cameras...")
        self.available_cameras = self.camera_thread.discover_cameras()

        self.ui_elements["camera_combo"].clear()
        if self.available_cameras:
            for cam in self.available_cameras:
                text = f"{cam['model']} ({cam['ip']})"
                self.ui_elements["camera_combo"].addItem(text)

            self._log(f"✅ Found {len(self.available_cameras)} camera(s)")
            self.ui_elements["connect_btn"].setEnabled(True)
        else:
            self.ui_elements["camera_combo"].addItem("No cameras found")
            self._log("❌ No cameras found")
            self.ui_elements["connect_btn"].setEnabled(False)

    def _connect_camera(self):
        """Connect to selected camera"""
        index = self.ui_elements["camera_combo"].currentIndex()
        if index < 0 or index >= len(self.available_cameras):
            return

        self._log(f"🔗 Connecting to {self.available_cameras[index]['model']}...")

        if self.camera_thread.connect_camera(index):
            self.camera_connected = True
            self.capture_controller.set_camera_source(
                lambda: self.camera_thread.capture_frame(1000)
            )

            # Update UI
            self.ui_elements["connect_btn"].setEnabled(False)
            self.ui_elements["disconnect_btn"].setEnabled(True)
            self.ui_elements["start_live_btn"].setEnabled(True)
            self.ui_elements["exposure_spin"].setEnabled(True)
            self.ui_elements["trigger_combo"].setEnabled(True)

            self._log("✅ Camera connected successfully")
        else:
            self._log("❌ Camera connection failed")

    def _disconnect_camera(self):
        """Disconnect camera"""
        if hasattr(self, "live_layer"):
            try:
                self.viewer.layers.remove(self.live_layer)
            except:
                pass
            delattr(self, "live_layer")

        self.camera_thread.disconnect_camera()
        self.camera_connected = False

        # Update UI
        self.ui_elements["connect_btn"].setEnabled(True)
        self.ui_elements["disconnect_btn"].setEnabled(False)
        self.ui_elements["start_live_btn"].setEnabled(False)
        self.ui_elements["stop_live_btn"].setEnabled(False)
        self.ui_elements["exposure_spin"].setEnabled(False)
        self.ui_elements["trigger_combo"].setEnabled(False)

        self._log("✅ Camera disconnected")

    def _start_live_view(self):
        """Start camera live view"""
        if self.camera_thread.start_acquisition():
            self.camera_thread.start()
            self.ui_elements["start_live_btn"].setEnabled(False)
            self.ui_elements["stop_live_btn"].setEnabled(True)
            self._log("▶️ Live view started")
        else:
            self._log("❌ Failed to start live view")

    def _stop_live_view(self):
        """Stop camera live view"""
        self.camera_thread.stop_acquisition()
        self.ui_elements["start_live_btn"].setEnabled(True)
        self.ui_elements["stop_live_btn"].setEnabled(False)

        if hasattr(self, "live_layer"):
            try:
                self.viewer.layers.remove(self.live_layer)
            except:
                pass
            delattr(self, "live_layer")

        self._log("⏹️ Live view stopped")

    def _on_exposure_changed(self):
        """Handle exposure change"""
        if self.camera_connected and self.camera_thread:
            exposure = self.ui_elements["exposure_spin"].value()
            if self.camera_thread.set_exposure_time(exposure):
                self._log(f"📷 Exposure set to {exposure}μs")

    def _on_trigger_changed(self):
        """Handle trigger mode change"""
        if self.camera_connected and self.camera_thread:
            mode = self.ui_elements["trigger_combo"].currentText()
            if "Software" in mode:
                self.camera_thread.set_trigger_mode(True)
                self._log("📷 Software trigger enabled")
            else:
                self.camera_thread.set_trigger_mode(False)
                self._log("📷 Free running mode")

    def _optimize_camera(self):
        """Optimize camera for time-lapse"""
        if self.camera_connected and self.camera_thread:
            if self.camera_thread.optimize_for_timelapse():
                self._log("✅ Camera optimized for time-lapse")
            else:
                self._log("❌ Optimization failed")

    # Recording control methods
    def _calculate_frames(self):
        """Calculate total frames and update statistics"""
        try:
            duration = float(self.ui_elements["duration_input"].text())
            interval = float(self.ui_elements["interval_input"].text())

            if duration > 0 and interval > 0:
                total_frames = int((duration * 60) / interval)
                self.ui_elements["frames_label"].setText(str(total_frames))

                # Update statistics
                total_size_mb = (total_frames * 2) / 1024  # Rough estimate
                capture_time = total_frames * 0.1  # Estimate 100ms per capture

                stats = "Recording Statistics:\n"
                stats += f"• Total frames: {total_frames:,}\n"
                stats += f"• Recording time: {duration:.1f} minutes\n"
                stats += f"• Interval: {interval:.1f} seconds\n"
                stats += f"• Estimated size: ~{total_size_mb:.1f} GB\n"
                stats += f"• Capture overhead: ~{capture_time:.1f} seconds"

                self.ui_elements["stats_label"].setText(stats)
            else:
                self.ui_elements["frames_label"].setText("--")
                self.ui_elements["stats_label"].setText("Enter valid parameters")

        except ValueError:
            self.ui_elements["frames_label"].setText("--")
            self.ui_elements["stats_label"].setText("Invalid input values")

    def _select_directory(self):
        """Select save directory"""
        directory = QFileDialog.getExistingDirectory(self, "Select Save Directory")
        if directory:
            self.save_directory = directory
            self.ui_elements["dir_label"].setText(os.path.basename(directory))
            self.ui_elements["dir_label"].setStyleSheet("color: green; font-weight: bold;")
            self._log(f"📁 Save directory: {directory}")

    def _start_recording(self):
        """Start time-lapse recording"""
        # Validate setup
        if not self.camera_connected:
            QMessageBox.warning(self, "Error", "No camera connected or ImSwitch layer detected")
            return

        if not self.save_directory:
            QMessageBox.warning(self, "Error", "Please select save directory")
            return

        try:
            # Get parameters
            duration_min = float(self.ui_elements["duration_input"].text())
            interval_sec = float(self.ui_elements["interval_input"].text())
            total_frames = int((duration_min * 60) / interval_sec)

            if total_frames == 0:
                QMessageBox.warning(self, "Error", "Invalid recording parameters")
                return

            # Test capture to get frame shape
            self._log("📸 Testing capture...")
            test_result = self.capture_controller.capture_frame_with_sync()

            if not test_result["success"] or test_result["frame"] is None:
                QMessageBox.warning(
                    self,
                    "Error",
                    f"Test capture failed: {test_result.get('error', 'Unknown error')}",
                )
                return

            frame_shape = test_result["frame"].shape
            self._log(f"✅ Frame shape: {frame_shape}")

            # Setup save path
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if self.ui_elements["subfolder_check"].isChecked():
                save_dir = os.path.join(self.save_directory, f"timelapse_{timestamp}")
                os.makedirs(save_dir, exist_ok=True)
            else:
                save_dir = self.save_directory

            save_path = os.path.join(save_dir, f"recording_{timestamp}.h5")

            # Create metadata
            metadata = {
                "recording_type": "synchronized_timelapse_v4",
                "interval_seconds": interval_sec,
                "duration_minutes": duration_min,
                "led_enabled": self.esp32_controller.connected,
                "led_power": self.ui_elements["led_slider"].value(),
                "camera_mode": self.capture_mode.value,
                "frame_shape": frame_shape,
                "software_version": "4.0",
                "creation_time": datetime.now().isoformat(),
            }

            # Setup recording
            if not self.recording_manager.setup_recording(
                save_path, frame_shape, total_frames, metadata
            ):
                QMessageBox.warning(self, "Error", "Failed to setup recording file")
                return

            # Initialize recording state
            self.recording_state["start_time"] = time.time()
            self.recording_state["interval"] = interval_sec
            self.recording_state["total_frames"] = total_frames
            self.recording_state["next_frame_time"] = self.recording_state["start_time"]
            self.recording_paused = False

            # Update UI
            self.ui_elements["progress_bar"].setMaximum(total_frames)
            self.ui_elements["progress_bar"].setValue(0)
            self.ui_elements["progress_bar"].setVisible(True)
            self.ui_elements["start_btn"].setEnabled(False)
            self.ui_elements["pause_btn"].setEnabled(True)
            self.ui_elements["stop_btn"].setEnabled(True)
            self.ui_elements["recording_status"].setText("Recording: Active")

            # Start timer
            self.capture_timer.start(10)  # Check every 10ms for precise timing

            self._log(f"🎬 Recording started: {total_frames} frames @ {interval_sec}s intervals")
            self._log(f"💾 Saving to: {save_path}")

        except Exception as e:
            self._log(f"❌ Recording start error: {e}")
            QMessageBox.critical(self, "Error", f"Failed to start recording: {str(e)}")

    def _pause_recording(self):
        """Pause/resume recording"""
        if hasattr(self, "recording_paused"):
            if self.recording_paused:
                # Resume
                self.recording_paused = False
                self.ui_elements["pause_btn"].setText("⏸️ Pause")
                self.capture_timer.start(10)
                self._log("▶️ Recording resumed")
            else:
                # Pause
                self.recording_paused = True
                self.ui_elements["pause_btn"].setText("▶️ Resume")
                self.capture_timer.stop()
                self._log("⏸️ Recording paused")

    def _stop_recording(self):
        """Stop recording"""
        self.capture_timer.stop()

        # Turn off LED
        if self.esp32_controller.connected:
            self.esp32_controller.led_off()

        # Finalize recording
        summary = self.recording_manager.finalize_recording()

        # Update UI
        self.ui_elements["progress_bar"].setVisible(False)
        self.ui_elements["start_btn"].setEnabled(True)
        self.ui_elements["pause_btn"].setEnabled(False)
        self.ui_elements["stop_btn"].setEnabled(False)
        self.ui_elements["recording_status"].setText("Recording: Stopped")

        # Show summary
        if summary["success"]:
            self._log("✅ Recording completed successfully!")
            self._log(f"📊 Frames saved: {summary['frames_saved']}/{summary['frames_expected']}")
            self._log(f"⏱️ Duration: {summary['duration_seconds']:.1f} seconds")

            if "max_drift_ms" in summary:
                self._log(f"📏 Max drift: {summary['max_drift_ms']:.1f}ms")
                self._log(
                    f"📏 Mean drift: {summary['mean_drift_ms']:.1f}ms ± {summary['std_drift_ms']:.1f}ms"
                )

            if "mean_temperature" in summary:
                self._log(f"🌡️ Mean temperature: {summary['mean_temperature']:.1f}°C")

            # Success message
            QMessageBox.information(
                self,
                "Recording Complete",
                f"Recording saved successfully!\n\n"
                f"Frames: {summary['frames_saved']}\n"
                f"Duration: {summary['duration_seconds']:.1f}s\n"
                f"Max drift: {summary.get('max_drift_ms', 0):.1f}ms",
            )
        else:
            self._log("❌ Recording finalization failed")
            QMessageBox.warning(self, "Recording Error", "Failed to finalize recording")

    def _on_capture_timeout(self):
        """High-precision capture timer callback"""
        current_time = time.time()

        # Check if it's time for next frame
        if current_time >= self.recording_state["next_frame_time"]:
            # Calculate drift
            target_time = self.recording_state["start_time"] + (
                self.recording_manager.current_frame * self.recording_state["interval"]
            )
            drift_ms = (current_time - target_time) * 1000

            # Update drift display
            self.ui_elements["drift_label"].setText(f"Drift: {drift_ms:+.1f}ms")

            # Capture frame
            capture_result = self.capture_controller.capture_frame_with_sync()

            if capture_result["success"] and capture_result["frame"] is not None:
                # Prepare frame data
                frame_data = {
                    "frame": capture_result["frame"],
                    "capture_timestamp": capture_result["capture_timestamp"],
                    "target_timestamp": target_time,
                    "drift_ms": drift_ms,
                    "temperature": capture_result.get("temperature", 0.0),
                    "humidity": capture_result.get("humidity", 0.0),
                    "led_power": capture_result.get("led_power", 0),
                    "led_duration_ms": capture_result.get("led_duration_ms", 0),
                    "led_used": capture_result.get("led_used", False),
                }

                # Save frame
                if self.recording_manager.save_frame(frame_data):
                    # Update progress
                    current_frame = self.recording_manager.current_frame
                    self.ui_elements["progress_bar"].setValue(current_frame)
                    self.ui_elements["frame_label"].setText(
                        f"Frame: {current_frame}/{self.recording_state['total_frames']}"
                    )

                    # Update time displays
                    elapsed = current_time - self.recording_state["start_time"]
                    self.ui_elements["elapsed_label"].setText(
                        f"Elapsed: {self._format_time(elapsed)}"
                    )

                    if current_frame > 0:
                        fps = current_frame / elapsed
                        eta = (self.recording_state["total_frames"] - current_frame) / fps
                        self.ui_elements["eta_label"].setText(f"ETA: {self._format_time(eta)}")
                        self.ui_elements["fps_label"].setText(f"FPS: {fps:.2f}")

                    # Schedule next frame
                    self.recording_state["next_frame_time"] = (
                        target_time + self.recording_state["interval"]
                    )

                    # Check if complete
                    if current_frame >= self.recording_state["total_frames"]:
                        self._stop_recording()
                else:
                    self._log("❌ Failed to save frame")
            else:
                self._log(
                    f"❌ Frame capture failed: {capture_result.get('error', 'Unknown error')}"
                )
                # Still advance to next frame time
                self.recording_state["next_frame_time"] += self.recording_state["interval"]

    def _format_time(self, seconds: float) -> str:
        """Format seconds to HH:MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    # ESP32 control methods
    def _connect_esp32(self):
        """Connect to ESP32"""
        self._log("🔗 Connecting to ESP32...")

        if self.esp32_controller.connect():
            self._enable_esp32_controls(True)
            self.capture_controller.set_esp32_controller(self.esp32_controller)
            self._log("✅ ESP32 connected successfully")

            # Read initial sensor values
            self._read_sensors()
        else:
            self._log("❌ ESP32 connection failed")
            QMessageBox.warning(
                self,
                "Connection Failed",
                "Could not connect to ESP32.\n\n"
                "Please check:\n"
                "• ESP32 is connected via USB\n"
                "• Correct drivers are installed\n"
                "• No other program is using the port",
            )

    def _disconnect_esp32(self):
        """Disconnect ESP32"""
        self.esp32_controller.disconnect()
        self._enable_esp32_controls(False)
        self._log("✅ ESP32 disconnected")

    def _enable_esp32_controls(self, enabled: bool):
        """Enable/disable ESP32 controls"""
        self.ui_elements["led_on_btn"].setEnabled(enabled)
        self.ui_elements["led_off_btn"].setEnabled(enabled)
        self.ui_elements["led_slider"].setEnabled(enabled)
        self.ui_elements["esp32_connect_btn"].setEnabled(not enabled)
        self.ui_elements["esp32_disconnect_btn"].setEnabled(enabled)

        # Update status displays
        if enabled:
            self.ui_elements["esp32_status"].setText("Status: Connected ✅")
            self.ui_elements["esp32_status"].setStyleSheet("color: green;")
            self.ui_elements["esp32_status_2"].setText("ESP32: Connected")
        else:
            self.ui_elements["esp32_status"].setText("Status: Not connected")
            self.ui_elements["esp32_status"].setStyleSheet("color: red;")
            self.ui_elements["esp32_status_2"].setText("ESP32: Not connected")
            self.ui_elements["temp_label"].setText("--°C")
            self.ui_elements["humidity_label"].setText("--%")

    def _on_led_power_changed(self, value: int):
        """Handle LED power change"""
        self.ui_elements["led_power_label"].setText(f"{value}%")
        self.capture_controller.set_led_power(value)

        if self.esp32_controller.connected:
            self.esp32_controller.set_led_power(value)

    def _led_on(self):
        """Turn LED on"""
        if self.esp32_controller.led_on():
            self._log(f"💡 LED ON ({self.ui_elements['led_slider'].value()}%)")
        else:
            self._log("❌ LED ON failed")

    def _led_off(self):
        """Turn LED off"""
        if self.esp32_controller.led_off():
            self._log("🌑 LED OFF")
        else:
            self._log("❌ LED OFF failed")

    def _test_led_flash(self):
        """Test LED flash sequence"""
        if not self.esp32_controller.connected:
            self._log("❌ ESP32 not connected")
            return

        self._log("⚡ Testing LED flash...")

        # Flash sequence
        for i in range(3):
            self.esp32_controller.led_on()
            time.sleep(0.5)
            self.esp32_controller.led_off()
            time.sleep(0.5)

        self._log("✅ LED flash test completed")

    def _read_sensors(self):
        """Read environmental sensors"""
        if not self.esp32_controller.connected:
            return

        status = self.esp32_controller.get_status()
        if status:
            self.ui_elements["temp_label"].setText(f"{status['temperature']:.1f}°C")
            self.ui_elements["humidity_label"].setText(f"{status['humidity']:.1f}%")
            self._log(f"📊 Sensors: {status['temperature']:.1f}°C, {status['humidity']:.1f}% RH")
        else:
            self._log("❌ Failed to read sensors")

    # Test and diagnostic methods
    def _test_capture(self):
        """Test single capture"""
        self._log("🧪 Testing capture...")

        start_time = time.time()
        result = self.capture_controller.capture_frame_with_sync()
        capture_time = (time.time() - start_time) * 1000

        if result["success"] and result["frame"] is not None:
            # Display frame
            frame_name = f"Test Capture {datetime.now().strftime('%H:%M:%S')}"
            self.viewer.add_image(result["frame"], name=frame_name)

            # Log details
            self._log(f"✅ Capture successful in {capture_time:.1f}ms")
            self._log(f"   Frame: {result['frame'].shape}, Mean: {np.mean(result['frame']):.1f}")
            self._log(f"   LED: {'Yes' if result['led_used'] else 'No'}")

            if result["led_used"]:
                self._log(f"   LED Power: {result.get('led_power', 0)}%")
                self._log(f"   LED Duration: {result.get('led_duration_ms', 0):.1f}ms")

            if result.get("temperature", 0) > 0:
                self._log(
                    f"   Environment: {result.get('temperature', 0):.1f}°C, {result.get('humidity', 0):.1f}%"
                )
        else:
            self._log(f"❌ Capture failed: {result.get('error', 'Unknown error')}")

    def _test_led_sync(self):
        """Test LED synchronization"""
        if not self.esp32_controller.connected:
            self._log("❌ ESP32 not connected for LED sync test")
            return

        self._log("🧪 Testing LED synchronization...")

        # Capture dark frame
        self.esp32_controller.led_off()
        time.sleep(0.5)
        dark_result = self.capture_controller._capture_without_led()

        if not dark_result["success"]:
            self._log("❌ Failed to capture dark frame")
            return

        dark_mean = np.mean(dark_result["frame"])
        self._log(f"🌑 Dark frame mean: {dark_mean:.1f}")

        # Capture bright frames with different delays
        test_delays = [10, 30, 50, 100]  # ms

        for delay in test_delays:
            self.capture_controller.led_stabilization_ms = delay
            bright_result = self.capture_controller._capture_with_led()

            if bright_result["success"]:
                bright_mean = np.mean(bright_result["frame"])
                ratio = bright_mean / dark_mean if dark_mean > 0 else 0

                self._log(f"💡 {delay}ms delay: mean={bright_mean:.1f}, ratio={ratio:.2f}x")

            time.sleep(0.5)

        # Reset to default
        self.capture_controller.led_stabilization_ms = 50
        self._log("✅ LED sync test completed")

    def _optimize_led_timing(self):
        """Optimize LED timing"""
        if not self.esp32_controller.connected:
            self._log("❌ ESP32 not connected")
            return

        self._log("⚡ Optimizing LED timing...")
        optimal_delay = self.capture_controller.optimize_led_timing(test_frames=5)
        self._log(f"✅ Optimal LED delay: {optimal_delay}ms")

    def _show_timing_stats(self):
        """Show timing statistics"""
        stats = self.capture_controller.get_timing_statistics()

        self._log("📊 Capture Timing Statistics:")
        self._log(f"   Mean: {stats['mean_ms']:.1f}ms")
        self._log(f"   Std Dev: {stats['std_ms']:.1f}ms")
        self._log(f"   Min: {stats['min_ms']:.1f}ms")
        self._log(f"   Max: {stats['max_ms']:.1f}ms")

    def _log(self, message: str):
        """Add message to log with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        log_entry = f"[{timestamp}] {message}"

        if "log_display" in self.ui_elements:
            self.ui_elements["log_display"].append(log_entry)
            # Auto-scroll to bottom
            scrollbar = self.ui_elements["log_display"].verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

        print(log_entry)


# Plugin registration for napari
def napari_experimental_provide_dock_widget():
    """Provide widget for napari"""
    return NematostellaTimeSeriesCapture
