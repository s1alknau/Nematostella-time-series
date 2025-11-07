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
    QComboBox,
    QFrame,
    QFormLayout,
)
from qtpy.QtCore import QTimer, QObject

try:
    from qtpy.QtCore import pyqtSignal
except ImportError:
    from qtpy.QtCore import Signal as pyqtSignal
from qtpy.QtCore import Qt
from qtpy.QtWidgets import QApplication
import time
import os
import numpy as np
from pathlib import Path
from typing import Tuple, Optional
import logging
from PyQt5.QtWidgets import QMessageBox

"""Nematostella timelapse recording widget with Day/Night phase support and HYBRID timing mode."""

logger = logging.getLogger(__name__)


def get_imswitch_main():
    """Get ImSwitch main controller - SAFE from Qt deletions."""
    import sys
    import gc

    # Method 1: sys.modules (safe)
    for module_name in sys.modules.keys():
        if "imswitch" in module_name.lower():
            try:
                module = sys.modules[module_name]
                if hasattr(module, "main_controller"):
                    return module.main_controller
            except:
                continue

    # Method 2: Garbage collector with Qt safety
    try:
        for obj in gc.get_objects():
            try:
                # Skip Qt widgets that might be deleted
                obj_type_str = str(type(obj))
                if "PyQt" in obj_type_str or "QWidget" in obj_type_str or "QLabel" in obj_type_str:
                    continue

                if hasattr(obj, "detectorsManager") and hasattr(obj, "liveViewWidget"):
                    return obj
            except (RuntimeError, ReferenceError):
                continue
    except:
        pass

    return None


class NematostallTimelapseCaptureWidget(QWidget):
    """Main widget for Nematostella timelapse capture with Day/Night phase support and HYBRID timing."""

    def __init__(self, napari_viewer=None, imswitch_main_controller=None):
        super().__init__()

        # Configure logging
        logging.getLogger("_esp32_controller").setLevel(logging.INFO)
        logging.getLogger("_data_manager").setLevel(logging.INFO)

        # Auto-detect napari viewer if not provided
        if napari_viewer is None:
            print("⚠ WARNING: No viewer passed to widget, attempting auto-detection...")
            try:
                import napari

                napari_viewer = napari.current_viewer()
                if napari_viewer is not None:
                    print(
                        f"✓ SUCCESS: Auto-detected napari viewer with {len(napari_viewer.layers)} layers"
                    )
                else:
                    print("✗ FAILED: napari.current_viewer() returned None")
            except Exception as e:
                print(f"✗ FAILED: Could not auto-detect napari viewer: {e}")
        else:
            print(
                f"✓ Viewer was provided: {type(napari_viewer)} with {len(napari_viewer.layers)} layers"
            )

        self.viewer = napari_viewer

        # Auto-detect ImSwitch if not provided
        if imswitch_main_controller is None:
            imswitch_main_controller = get_imswitch_main()
            if imswitch_main_controller:
                print("SUCCESS: ImSwitch auto-detected!")

        self.imswitch_main = imswitch_main_controller
        self.setWindowTitle("Nematostella Time-Series Capture")
        self.setMinimumWidth(800)
        self.setMinimumHeight(600)

        # Camera info
        self.camera_name = "HikCamera"
        self.camera_connected = False

        # Initialize core components
        print(">>> WIDGET: Initializing core components...")

        # DataManager
        self.data_manager = None
        try:
            from ._data_manager import DataManager

            self.data_manager = DataManager()
            print(">>> WIDGET: DataManager created successfully")
        except Exception as e:
            print(f">>> WIDGET: ERROR creating DataManager: {e}")
            print(">>> WIDGET: DataManager will be created on-demand during recording")

        # Recorder
        self.recorder = None
        print(">>> WIDGET: Recorder initialized as None (will be created on start)")

        # Setup UI first
        self._setup_ui()

        # Per-LED desired power
        self.desired_ir_power = (
            self.led_power_slider.value() if hasattr(self, "led_power_slider") else 100
        )
        self.desired_white_power = (
            self.white_led_power_slider.value() if hasattr(self, "white_led_power_slider") else 50
        )

        # Initialize controllers
        self._initialize_controllers()

        # State variables
        self.recording = False

        # Setup connections and timers
        self._setup_connections()
        self._setup_timers()

        print(">>> WIDGET: Initialization complete (HYBRID MODE)")

    def _initialize_controllers(self):
        """Initialize real controllers."""
        try:
            from ._esp32_controller import ESP32Controller
            from ._data_manager import DataManager

            self.esp32_controller = ESP32Controller(self.imswitch_main)
            self.data_manager = DataManager()
            self.recorder = None

            self.camera_connected = self._check_camera_connection()

            self._add_log_entry("Real controllers initialized successfully (HYBRID MODE)")

            if self.esp32_controller.esp32_port:
                self._add_log_entry(f"ESP32 port detected: {self.esp32_controller.esp32_port}")
            else:
                self._add_log_entry("Warning: No ESP32 port detected")

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
        """Camera check with FIXED throttling."""
        import time

        if not hasattr(self.__class__, "_camera_check_time"):
            self.__class__._camera_check_time = 0
            self.__class__._camera_check_interval = 30
            self.__class__._camera_cached_status = False
            self.__class__._camera_cached_source = "Unknown"

        current_time = time.time()
        time_since_check = current_time - self.__class__._camera_check_time

        if time_since_check < self.__class__._camera_check_interval:
            return self.__class__._camera_cached_status

        self.__class__._camera_check_time = current_time

        camera_ready = False
        camera_source = "Unknown"

        try:
            if self.viewer is not None:
                from napari.layers import Image

                for layer in self.viewer.layers:
                    if isinstance(layer, Image):
                        data = getattr(layer, "data", None)
                        if data is not None and data.size > 0:
                            camera_ready = True
                            camera_source = f"napari:{layer.name}"
                            break

            if not camera_ready and self.imswitch_main is not None:
                if hasattr(self.imswitch_main, "liveViewWidget"):
                    live_view = self.imswitch_main.liveViewWidget
                    if hasattr(live_view, "img") and live_view.img is not None:
                        camera_ready = True
                        camera_source = "ImSwitch LiveView"

        except Exception as e:
            camera_ready = False

        self.__class__._camera_cached_status = camera_ready
        self.__class__._camera_cached_source = camera_source

        if hasattr(self, "camera_status_label") and self.camera_status_label is not None:
            try:
                if camera_ready:
                    self.camera_status_label.setText(f"Camera: Ready ({camera_source})")
                    self.camera_status_label.setStyleSheet("color: #00ff00;")
                else:
                    self.camera_status_label.setText("Camera: Not Ready")
                    self.camera_status_label.setStyleSheet("color: #ff0000;")
            except RuntimeError:
                pass

        return camera_ready

    def connect_to_napari(self, viewer):
        """Connect the plugin to a napari viewer."""
        self.viewer = viewer
        self._add_log_entry(f"Connected to napari viewer with {len(viewer.layers)} layers")

        if hasattr(self.__class__, "_camera_check_time"):
            self.__class__._camera_check_time = 0

        self._check_camera_connection()

    def _setup_ui(self):
        """Setup the user interface."""
        layout = QHBoxLayout()

        left_panel = self._create_left_panel()
        layout.addWidget(left_panel, stretch=2)

        right_panel = self._create_right_panel()
        layout.addWidget(right_panel, stretch=1)

        self.setLayout(layout)

    def _create_left_panel(self):
        """Create the left control panel."""
        widget = QWidget()
        layout = QVBoxLayout()

        tabs = QTabWidget()

        camera_tab = self._create_camera_tab()
        tabs.addTab(camera_tab, "File Management")

        recording_tab = self._create_recording_tab()
        tabs.addTab(recording_tab, "Recording")

        esp32_tab = self._create_esp32_tab()
        tabs.addTab(esp32_tab, "ESP32 Control")

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
        """Create recording control tab with exposure/timing controls."""
        widget = QWidget()
        layout = QVBoxLayout()

        # ══════════════════════════════════════════════════════════════════
        # ✅ EXPOSURE & TIMING CONTROL (HYBRID MODE)
        # ══════════════════════════════════════════════════════════════════
        exposure_group = QGroupBox("Camera Exposure & LED Timing (HYBRID MODE)")
        exposure_layout = QFormLayout()

        # Exposure time spinbox
        self.exposure_spinbox = QSpinBox()
        self.exposure_spinbox.setRange(1, 5000)
        self.exposure_spinbox.setValue(10)
        self.exposure_spinbox.setSuffix(" ms")
        self.exposure_spinbox.setToolTip(
            "Camera exposure time in milliseconds.\n"
            "LED timing will automatically adjust to match.\n"
            "Typical values: 5-50ms for fast imaging, 100-500ms for dim samples.\n"
            "Range: 1-5000ms\n\n"
            "HYBRID MODE: Set as Python attribute (no ESP32 command)"
        )
        self.exposure_spinbox.valueChanged.connect(self._on_exposure_changed)
        exposure_layout.addRow("Exposure Time:", self.exposure_spinbox)

        # Separator
        separator1 = QFrame()
        separator1.setFrameShape(QFrame.Shape.HLine)
        separator1.setFrameShadow(QFrame.Shadow.Sunken)
        exposure_layout.addRow(separator1)

        # Auto-calculate checkbox
        self.auto_timing_checkbox = QCheckBox("Auto-calculate LED timing")
        self.auto_timing_checkbox.setChecked(True)
        self.auto_timing_checkbox.setToolTip(
            "Automatically calculate optimal LED stabilization\n"
            "and timing parameters based on exposure time.\n\n"
            "RECOMMENDED: Keep this enabled for best results.\n"
            "Uncheck only if you need manual fine-tuning."
        )
        self.auto_timing_checkbox.stateChanged.connect(self._on_auto_timing_changed)
        exposure_layout.addRow("", self.auto_timing_checkbox)

        # LED Stabilization (manual override)
        self.stabilization_spinbox = QSpinBox()
        self.stabilization_spinbox.setRange(10, 10000)
        self.stabilization_spinbox.setValue(1000)
        self.stabilization_spinbox.setSuffix(" ms")
        self.stabilization_spinbox.setEnabled(False)
        self.stabilization_spinbox.setToolTip(
            "LED stabilization time (warm-up before capture).\n"
            "Time for LED to reach full, stable brightness.\n\n"
            "Only editable when auto-calculate is disabled.\n"
            "Typical: 10-20x the exposure time."
        )
        self.stabilization_spinbox.valueChanged.connect(self._on_manual_timing_changed)
        exposure_layout.addRow("LED Stabilization:", self.stabilization_spinbox)

        # Camera trigger latency (manual override)
        self.latency_spinbox = QSpinBox()
        self.latency_spinbox.setRange(0, 200)
        self.latency_spinbox.setValue(20)
        self.latency_spinbox.setSuffix(" ms")
        self.latency_spinbox.setEnabled(False)
        self.latency_spinbox.setToolTip(
            "Camera trigger latency compensation.\n"
            "Time between trigger command and actual capture.\n\n"
            "Only editable when auto-calculate is disabled.\n"
            "Typical HIK camera: 10-50ms"
        )
        self.latency_spinbox.valueChanged.connect(self._on_manual_timing_changed)
        exposure_layout.addRow("Trigger Latency:", self.latency_spinbox)

        # Separator
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.HLine)
        separator2.setFrameShadow(QFrame.Shadow.Sunken)
        exposure_layout.addRow(separator2)

        # Display calculated total LED duration
        self.led_duration_label = QLabel("210 ms")
        self.led_duration_label.setStyleSheet(
            "color: blue; "
            "font-weight: bold; "
            "font-size: 11pt; "
            "background-color: #E3F2FD; "
            "padding: 4px; "
            "border-radius: 3px;"
        )
        self.led_duration_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.led_duration_label.setToolTip(
            "Total LED-ON duration per frame.\n"
            "= Stabilization + Exposure\n\n"
            "This is how long the LED will be on for each capture."
        )
        exposure_layout.addRow("Total LED Duration:", self.led_duration_label)

        exposure_group.setLayout(exposure_layout)

        # ══════════════════════════════════════════════════════════════════
        # Recording Parameters
        # ══════════════════════════════════════════════════════════════════
        params_group = QGroupBox("Recording Parameters")
        params_layout = QVBoxLayout()

        # Duration + Interval
        duration_layout = QHBoxLayout()
        duration_layout.addWidget(QLabel("Total Duration (min):"))
        self.duration_spinbox = QSpinBox()
        self.duration_spinbox.setRange(1, 10000)
        self.duration_spinbox.setValue(60)
        duration_layout.addWidget(self.duration_spinbox)

        duration_layout.addWidget(QLabel("Interval (sec):"))
        self.interval_spinbox = QSpinBox()
        self.interval_spinbox.setRange(1, 3600)
        self.interval_spinbox.setValue(5)
        duration_layout.addWidget(self.interval_spinbox)

        # Day/Night Phase Controls
        phase_group = QGroupBox("Day/Night Cycle Configuration")
        phase_layout = QVBoxLayout()

        self.enable_day_night_checkbox = QCheckBox("Enable Day/Night Cycling")
        self.enable_day_night_checkbox.setChecked(False)
        phase_layout.addWidget(self.enable_day_night_checkbox)

        phase_controls_layout = QHBoxLayout()

        # Light phase
        light_layout = QVBoxLayout()
        light_layout.addWidget(QLabel("☀️ Light Phase (White LED)"))
        light_duration_layout = QHBoxLayout()
        light_duration_layout.addWidget(QLabel("Duration (min):"))
        self.light_phase_spinbox = QSpinBox()
        self.light_phase_spinbox.setRange(1, 1440)
        self.light_phase_spinbox.setValue(30)
        light_duration_layout.addWidget(self.light_phase_spinbox)
        light_layout.addLayout(light_duration_layout)

        # Dark phase
        dark_layout = QVBoxLayout()
        dark_layout.addWidget(QLabel("🌙 Dark Phase (IR LED)"))
        dark_duration_layout = QHBoxLayout()
        dark_duration_layout.addWidget(QLabel("Duration (min):"))
        self.dark_phase_spinbox = QSpinBox()
        self.dark_phase_spinbox.setRange(1, 1440)
        self.dark_phase_spinbox.setValue(30)
        dark_duration_layout.addWidget(self.dark_phase_spinbox)
        dark_layout.addLayout(dark_duration_layout)

        phase_controls_layout.addLayout(light_layout)
        phase_controls_layout.addLayout(dark_layout)

        # Start phase selector
        start_phase_layout = QHBoxLayout()
        start_phase_layout.addWidget(QLabel("Start with:"))
        self.start_phase_combo = QComboBox()
        self.start_phase_combo.addItems(["Light Phase (☀️ White LED)", "Dark Phase (🌙 IR LED)"])
        start_phase_layout.addWidget(self.start_phase_combo)
        start_phase_layout.addStretch()

        # Dual illumination checkbox
        self.dual_light_phase_checkbox = QCheckBox(
            "Use IR + White simultaneously during LIGHT phase"
        )
        self.dual_light_phase_checkbox.setToolTip(
            "If enabled, both IR and White LEDs are pulsed together during the LIGHT phase."
        )

        # Assemble phase group
        phase_layout.addLayout(phase_controls_layout)
        phase_layout.addLayout(start_phase_layout)
        phase_layout.addWidget(self.dual_light_phase_checkbox)

        # Phase info display
        phase_info_layout = QHBoxLayout()
        self.current_phase_label = QLabel("Current Phase: Light")
        self.current_phase_label.setStyleSheet("color: #ff8800; font-weight: bold;")
        self.phase_cycles_label = QLabel("Total Cycles: 1")
        self.phase_time_remaining_label = QLabel("Phase Time Remaining: --:--")
        phase_info_layout.addWidget(self.current_phase_label)
        phase_info_layout.addWidget(self.phase_cycles_label)
        phase_info_layout.addWidget(self.phase_time_remaining_label)
        phase_layout.addLayout(phase_info_layout)

        phase_group.setLayout(phase_layout)

        # Initialize phase config
        self.phase_config = getattr(self, "phase_config", {})
        self.phase_config.setdefault("enabled", False)
        self.phase_config.setdefault("dual_light_phase", False)
        self.enable_day_night_checkbox.setChecked(bool(self.phase_config["enabled"]))
        self.dual_light_phase_checkbox.setChecked(bool(self.phase_config["dual_light_phase"]))

        # Register widgets for toggle
        self.phase_control_widgets = [
            self.light_phase_spinbox,
            self.dark_phase_spinbox,
            self.start_phase_combo,
            self.dual_light_phase_checkbox,
        ]

        # Expected frames + stats
        expected_layout = QHBoxLayout()
        expected_layout.addWidget(QLabel("Expected Frames:"))
        self.expected_frames_label = QLabel("720")
        expected_layout.addWidget(self.expected_frames_label)
        expected_layout.addStretch()

        self.frames_label = QLabel("● Frames: 720")
        self.duration_label = QLabel("● Duration: 60.0 min")
        self.intervals_label = QLabel("● Intervals: 5.0 sec")
        self.phase_stats_label = QLabel("● Phase Pattern: Continuous")

        # Add to params group
        params_layout.addLayout(duration_layout)
        params_layout.addWidget(phase_group)
        params_layout.addLayout(expected_layout)
        params_layout.addWidget(self.frames_label)
        params_layout.addWidget(self.duration_label)
        params_layout.addWidget(self.intervals_label)
        params_layout.addWidget(self.phase_stats_label)
        params_group.setLayout(params_layout)

        # Recording Control
        control_group = QGroupBox("Recording Control")
        control_layout = QVBoxLayout()

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)

        frame_layout = QHBoxLayout()
        self.frame_info_label = QLabel("Frame: 0/720")
        self.elapsed_label = QLabel("Elapsed: 00:00:00")
        self.eta_label = QLabel("ETA: 00:00:00")
        frame_layout.addWidget(self.frame_info_label)
        frame_layout.addWidget(self.elapsed_label)
        frame_layout.addWidget(self.eta_label)

        button_layout = QHBoxLayout()
        self.start_button = QPushButton("🎬 Start Recording")
        self.pause_button = QPushButton("⏸ Pause")
        self.stop_button = QPushButton("⏹ Stop")
        self.start_button.clicked.connect(self._start_recording)
        self.pause_button.clicked.connect(self._pause_recording)
        self.stop_button.clicked.connect(self._stop_recording)
        self.reset_button = QPushButton("🔄 Reset")
        self.reset_button.clicked.connect(self._reset_recording)
        self.reset_button.setEnabled(False)
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.pause_button)
        button_layout.addWidget(self.stop_button)
        button_layout.addWidget(self.reset_button)

        control_layout.addWidget(self.progress_bar)
        control_layout.addLayout(frame_layout)
        control_layout.addLayout(button_layout)
        control_group.setLayout(control_layout)

        # Add all groups
        layout.addWidget(exposure_group)  # NEW: Exposure controls at top
        layout.addWidget(params_group)
        layout.addWidget(control_group)
        layout.addStretch()
        widget.setLayout(layout)

        # Initialize
        self._toggle_phase_controls()
        self._update_expected_frames()
        self._update_timing_values()  # NEW: Initialize timing display

        return widget

    def _create_esp32_tab(self):
        """Create ESP32 control tab."""
        widget = QWidget()
        layout = QVBoxLayout()

        # ESP32 Connection
        connection_group = QGroupBox("ESP32 Connection")
        conn_layout = QVBoxLayout()

        conn_button_layout = QHBoxLayout()
        self.connect_esp32_button = QPushButton("🔗 Connect ESP32")
        self.disconnect_esp32_button = QPushButton("❌ Disconnect")

        self.connect_esp32_button.clicked.connect(self.widget_connect_esp32_via_imswitch)
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

        # Main LED power
        power_layout = QHBoxLayout()
        power_layout.addWidget(QLabel("LED Power:"))
        self.led_power_slider = QSlider()
        self.led_power_slider.setOrientation(Qt.Horizontal)
        self.led_power_slider.setRange(0, 100)
        self.led_power_slider.setValue(100)
        self.led_power_value_label = QLabel("100%")
        power_layout.addWidget(self.led_power_slider)
        power_layout.addWidget(self.led_power_value_label)

        # Main LED on/off
        led_button_layout = QHBoxLayout()
        self.led_on_button = QPushButton("💡 LED ON (100%)")
        self.led_off_button = QPushButton("🌑 LED OFF")
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

        # White LED sub-group
        white_box = QGroupBox("White LED")
        white_layout = QVBoxLayout()

        w_power_layout = QHBoxLayout()
        w_power_layout.addWidget(QLabel("White LED Power:"))
        self.white_led_power_slider = QSlider()
        self.white_led_power_slider.setOrientation(Qt.Horizontal)
        self.white_led_power_slider.setRange(1, 100)
        self.white_led_power_slider.setValue(50)
        self.white_led_power_value_label = QLabel("50%")
        w_power_layout.addWidget(self.white_led_power_slider)
        w_power_layout.addWidget(self.white_led_power_value_label)

        w_btn_layout = QHBoxLayout()
        self.white_on_button = QPushButton("💡 White ON")
        self.white_off_button = QPushButton("🌫 White OFF")
        w_btn_layout.addWidget(self.white_on_button)
        w_btn_layout.addWidget(self.white_off_button)

        white_layout.addLayout(w_power_layout)
        white_layout.addLayout(w_btn_layout)
        white_box.setLayout(white_layout)

        led_layout.addWidget(white_box)
        led_group.setLayout(led_layout)

        # LED Calibration
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

        # Add all groups
        layout.addWidget(connection_group)
        layout.addWidget(led_group)
        layout.addWidget(calibration_group)
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
    # ✅ TIMING CALCULATION METHODS (HYBRID MODE)
    # ========================================================================

    def _calculate_optimal_timing(self, exposure_ms: int) -> dict:
        """Calculate optimal LED timing based on camera exposure."""
        if exposure_ms < 10:
            stabilization_ms = max(100, exposure_ms * 50)
        elif exposure_ms < 50:
            stabilization_ms = max(200, exposure_ms * 20)
        elif exposure_ms < 500:
            stabilization_ms = max(500, exposure_ms * 10)
        else:
            stabilization_ms = max(1000, exposure_ms * 5)

        stabilization_ms = min(stabilization_ms, 5000)

        if exposure_ms < 20:
            latency_ms = 10
        elif exposure_ms < 100:
            latency_ms = 20
        else:
            latency_ms = min(50, exposure_ms // 4)

        latency_ms = max(5, min(latency_ms, 100))

        total_duration_ms = stabilization_ms + exposure_ms
        capture_offset_ms = stabilization_ms + (exposure_ms // 2) - latency_ms
        capture_offset_ms = max(0, capture_offset_ms)

        return {
            "exposure_ms": int(exposure_ms),
            "stabilization_ms": int(stabilization_ms),
            "latency_ms": int(latency_ms),
            "total_duration_ms": int(total_duration_ms),
            "capture_offset_ms": int(capture_offset_ms),
        }

    def _update_timing_values(self):
        """Update timing values and GUI based on current settings."""
        exposure_ms = self.exposure_spinbox.value()

        if self.auto_timing_checkbox.isChecked():
            # Auto-calculate
            timing = self._calculate_optimal_timing(exposure_ms)

            self.stabilization_spinbox.blockSignals(True)
            self.latency_spinbox.blockSignals(True)

            self.stabilization_spinbox.setValue(timing["stabilization_ms"])
            self.latency_spinbox.setValue(timing["latency_ms"])

            self.stabilization_spinbox.blockSignals(False)
            self.latency_spinbox.blockSignals(False)

            self.led_duration_label.setText(f"{timing['total_duration_ms']} ms")
            self.led_duration_label.setStyleSheet(
                "color: blue; font-weight: bold; font-size: 11pt; "
                "background-color: #E3F2FD; padding: 4px; border-radius: 3px;"
            )
        else:
            # Manual override
            stabilization_ms = self.stabilization_spinbox.value()
            latency_ms = self.latency_spinbox.value()
            total_ms = stabilization_ms + exposure_ms

            self.led_duration_label.setText(f"{total_ms} ms")
            self.led_duration_label.setStyleSheet(
                "color: #FF6F00; font-weight: bold; font-size: 11pt; "
                "background-color: #FFF3E0; padding: 4px; border-radius: 3px;"
            )

    def _on_exposure_changed(self, value: int):
        """Called when exposure spinbox changes."""
        self._update_timing_values()

    def _on_auto_timing_changed(self, state: int):
        """Called when auto-timing checkbox is toggled."""
        auto_enabled = bool(state)

        self.stabilization_spinbox.setEnabled(not auto_enabled)
        self.latency_spinbox.setEnabled(not auto_enabled)

        disabled_style = "QSpinBox:disabled { background-color: #F5F5F5; color: #999; }"
        if auto_enabled:
            self.stabilization_spinbox.setStyleSheet(disabled_style)
            self.latency_spinbox.setStyleSheet(disabled_style)
        else:
            self.stabilization_spinbox.setStyleSheet("")
            self.latency_spinbox.setStyleSheet("")

        self._update_timing_values()

    def _on_manual_timing_changed(self, value: int):
        """Called when manual timing spinboxes change."""
        if not self.auto_timing_checkbox.isChecked():
            self._update_timing_values()

    def _validate_timing_values(self) -> bool:
        """Validate timing values before starting recording."""
        exposure_ms = self.exposure_spinbox.value()
        stabilization_ms = self.stabilization_spinbox.value()
        latency_ms = self.latency_spinbox.value()

        # Check 1: Stabilization vs Exposure
        if stabilization_ms < exposure_ms:
            QMessageBox.warning(
                self,
                "Invalid Timing",
                f"LED stabilization ({stabilization_ms}ms) should be >= exposure ({exposure_ms}ms)\n"
                f"Enable 'Auto-calculate' for optimal values.",
            )
            return False

        # Check 2: Latency vs Exposure
        if latency_ms >= exposure_ms:
            QMessageBox.warning(
                self,
                "Invalid Timing",
                f"Camera latency ({latency_ms}ms) must be < exposure ({exposure_ms}ms)",
            )
            return False

        # Check 3: Long LED duration warning
        total_ms = stabilization_ms + exposure_ms
        if total_ms > 10000:
            reply = QMessageBox.question(
                self,
                "Long LED Duration",
                f"LED will be ON for {total_ms/1000:.1f}s per frame.\n"
                f"This may cause heating/phototoxicity.\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return False

        # Check 4: Very short exposure warning
        if exposure_ms < 5:
            reply = QMessageBox.question(
                self,
                "Very Short Exposure",
                f"Exposure is very short ({exposure_ms}ms).\n"
                f"Images may be very dark.\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return False

        return True

    # ========================================================================
    # ✅ HYBRID MODE: START RECORDING (NO CMD_SET_TIMING)
    # ========================================================================

    def _start_recording(self):
        """Start recording with phase-aware setup and HYBRID timing (no CMD_SET_TIMING)."""
        print("\n" + "=" * 60)
        print("WIDGET: _start_recording() CALLED (HYBRID MODE)")
        print("=" * 60)

        if not self.recording:
            # ================================================================
            # STEP 1: BASIC VALIDATION
            # ================================================================
            print("WIDGET: Checking directory...")
            if not self.directory_edit.text():
                self._add_log_entry("Error: No recording directory selected")
                print("WIDGET: No directory - aborting")
                QMessageBox.warning(
                    self, "No Directory", "Please select a recording directory first."
                )
                return

            print(f"WIDGET: Directory OK: {self.directory_edit.text()}")
            print(f"WIDGET: imswitch_main = {self.imswitch_main}")
            print(f"WIDGET: viewer = {self.viewer}")

            # Check capture sources
            if self.imswitch_main is None and not self._has_live_layer():
                self._add_log_entry(
                    "Error: No ImSwitch controller and no live Napari layer available"
                )
                print("WIDGET: No capture source - aborting")
                QMessageBox.warning(
                    self,
                    "No Camera",
                    "No camera source available.\n\n"
                    "Either start ImSwitch Live View or ensure a live Napari layer exists.",
                )
                return

            print("WIDGET: Capture sources OK")

            # ================================================================
            # STEP 2: VALIDATE TIMING CONFIGURATION
            # ================================================================
            print("WIDGET: Validating timing configuration...")
            if not self._validate_timing_values():
                print("WIDGET: Timing validation failed - aborting")
                return
            print("WIDGET: Timing validation passed")

            # ================================================================
            # STEP 3: GET TIMING FROM GUI
            # ================================================================
            exposure_ms = self.exposure_spinbox.value()

            if self.auto_timing_checkbox.isChecked():
                timing = self._calculate_optimal_timing(exposure_ms)
                stabilization_ms = timing["stabilization_ms"]
                latency_ms = timing["latency_ms"]
            else:
                stabilization_ms = self.stabilization_spinbox.value()
                latency_ms = self.latency_spinbox.value()

            print(f"\n>>> TIMING CONFIG (HYBRID MODE):")
            print(f"    Exposure:       {exposure_ms}ms")
            print(f"    Stabilization:  {stabilization_ms}ms")
            print(f"    Latency:        {latency_ms}ms")
            print(f"    Total LED:      {stabilization_ms + exposure_ms}ms")

            # ================================================================
            # STEP 4: ESP32 CONNECTION CHECK (NO SET_TIMING COMMAND!)
            # ================================================================
            try:
                print(f"\n>>> Step 4: ESP32 Connection Check (HYBRID Mode)")

                # Check if ESP32 controller exists
                if not hasattr(self, "esp32_controller") or self.esp32_controller is None:
                    error_msg = (
                        "ESP32 controller not initialized!\n\n"
                        "This is a critical error. Please restart the plugin."
                    )
                    print(">>> ERROR: No ESP32 controller")
                    QMessageBox.critical(self, "ESP32 Error", error_msg)
                    return

                # Check if ESP32 is connected
                print(">>> Checking ESP32 connection...")
                if not self.esp32_controller.is_connected():
                    print(">>> ESP32 not connected - attempting to connect...")
                    self._add_log_entry("⚠️ ESP32 not connected - connecting...")

                    # Show connecting message
                    connecting_msg = QMessageBox(self)
                    connecting_msg.setWindowTitle("Connecting ESP32")
                    connecting_msg.setText("Connecting to ESP32...")
                    connecting_msg.setStandardButtons(QMessageBox.StandardButton.NoButton)
                    connecting_msg.show()
                    QApplication.processEvents()

                    try:
                        success = self.esp32_controller.connect_with_imswitch_protection()
                        connecting_msg.close()

                        if not success:
                            error_msg = (
                                "ESP32 is not connected!\n\n"
                                "Please:\n"
                                "1. Connect ESP32 using the 'ESP32 Control' tab\n"
                                "2. Check USB cable connection\n"
                                "3. Verify COM port in Device Manager"
                            )
                            print(">>> ESP32 connection failed")
                            QMessageBox.warning(self, "ESP32 Not Connected", error_msg)
                            return

                        print(">>> ESP32 connected successfully")
                        self._add_log_entry("✓ ESP32 connected")

                    except Exception as conn_e:
                        connecting_msg.close()
                        error_msg = f"ESP32 connection failed:\n\n{str(conn_e)}"
                        print(f">>> ESP32 connection error: {conn_e}")
                        QMessageBox.critical(self, "Connection Error", error_msg)
                        return

                print(">>> ESP32 is connected")

                # ================================================================
                # ✅ HYBRID APPROACH: Set timing as Python attributes only!
                # No CMD_SET_TIMING command - just like old version!
                # ================================================================
                print(f"\n>>> Setting timing attributes (HYBRID Mode):")
                print(f"    Exposure:       {exposure_ms}ms")
                print(f"    Stabilization:  {stabilization_ms}ms")
                print(f"    Latency:        {latency_ms}ms")

                # Set timing as Python object attributes (no ESP32 command!)
                self.esp32_controller.led_stabilization_ms = stabilization_ms
                self.esp32_controller.exposure_ms = exposure_ms

                print(">>> Timing attributes set in Python (no ESP32 command sent)")
                self._add_log_entry(
                    f"✓ Timing set: {stabilization_ms}ms stab + {exposure_ms}ms exp"
                )

                # ================================================================
                # ✅ OPTIONAL: Test with a single sync pulse (VERIFICATION)
                # ================================================================
                print(f"\n>>> Performing verification test pulse...")

                try:
                    # Reset any stuck state
                    if hasattr(self.esp32_controller, "_awaiting_sync"):
                        self.esp32_controller._awaiting_sync = False

                    # Do test pulse (this uses the Python attributes we just set)
                    test_start = self.esp32_controller.begin_sync_pulse(dual=False)
                    print(f">>> Test pulse started at {test_start}")

                    # Wait for completion
                    test_resp = self.esp32_controller.wait_sync_complete(timeout=10.0)

                    actual_duration = test_resp.get("led_duration_ms", 0)
                    expected_duration = stabilization_ms + exposure_ms
                    temp = test_resp.get("temperature", "N/A")
                    humidity = test_resp.get("humidity", "N/A")

                    print(f"\n>>> VERIFICATION RESULTS:")
                    print(f"    Expected duration: {expected_duration}ms")
                    print(f"    Actual duration:   {actual_duration}ms")
                    print(f"    Temperature:       {temp}°C")
                    print(f"    Humidity:          {humidity}%")

                    # More lenient tolerance for hybrid mode
                    diff = abs(actual_duration - expected_duration)
                    if diff > 100:  # 100ms tolerance (was 50ms)
                        print(f">>> ⚠️ WARNING: Timing difference is {diff}ms")
                        print(f">>> This may indicate ESP32 is using default/firmware values")
                        print(f">>> Recording will continue but timing may be off")

                        self._add_log_entry(
                            f"⚠️ Timing diff: {diff}ms (expected {expected_duration}ms, got {actual_duration}ms)"
                        )

                        # Show warning but allow to continue
                        reply = QMessageBox.question(
                            self,
                            "Timing Warning",
                            f"ESP32 timing verification shows difference of {diff}ms.\n\n"
                            f"Expected: {expected_duration}ms\n"
                            f"Actual: {actual_duration}ms\n\n"
                            f"This may be normal for Hybrid Mode if ESP32 uses firmware defaults.\n\n"
                            f"Continue recording?",
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                            QMessageBox.StandardButton.Yes,
                        )

                        if reply == QMessageBox.StandardButton.No:
                            print(">>> User cancelled recording")
                            return
                    else:
                        print(f">>> ✅ Timing verified successfully (diff={diff}ms)")
                        self._add_log_entry(
                            f"✓ Timing verified: {actual_duration}ms (diff={diff}ms)"
                        )

                except Exception as verify_e:
                    # In hybrid mode, verification failure is not critical
                    print(f">>> ⚠️ Verification test failed: {verify_e}")
                    print(f">>> This is OK in HYBRID Mode - continuing anyway")
                    self._add_log_entry(f"⚠️ Verification test failed (non-critical in Hybrid Mode)")

                    import traceback

                    traceback.print_exc()

                    # Ask user if they want to continue
                    reply = QMessageBox.question(
                        self,
                        "Verification Failed",
                        f"ESP32 test pulse failed:\n\n{str(verify_e)}\n\n"
                        f"In Hybrid Mode, this may be normal if ESP32 uses firmware defaults.\n\n"
                        f"Continue recording anyway?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.Yes,
                    )

                    if reply == QMessageBox.StandardButton.No:
                        print(">>> User cancelled recording")
                        return

            except Exception as e:
                error_msg = (
                    f"ESP32 setup failed!\n\n" f"Error: {str(e)}\n\n" f"Recording cannot start."
                )
                print(f">>> ❌ ESP32 setup failed: {e}")
                import traceback

                traceback.print_exc()
                QMessageBox.critical(self, "ESP32 Setup Failed", error_msg)
                return

            # ================================================================
            # STEP 5: CREATE RECORDER
            # ================================================================
            try:
                print("WIDGET: Cleaning up layers...")
                self._cleanup_timelapse_layers()

                print("WIDGET: Importing TimelapseRecorder...")
                from ._recorder import TimelapseRecorder

                print("WIDGET: Building phase config...")
                dual_chk = getattr(self, "dual_light_phase_checkbox", None)
                phase_config = {
                    "enabled": self.enable_day_night_checkbox.isChecked(),
                    "light_duration_min": self.light_phase_spinbox.value(),
                    "dark_duration_min": self.dark_phase_spinbox.value(),
                    "start_with_light": (self.start_phase_combo.currentIndex() == 0),
                    "dual_light_phase": bool(dual_chk and dual_chk.isChecked()),
                    "camera_trigger_latency_ms": latency_ms,  # ✅ Pass latency
                    "exposure_ms": exposure_ms,  # ✅ NEW: Pass exposure
                    "stabilization_ms": stabilization_ms,  # ✅ NEW: Pass stabilization
                }
                print(f"WIDGET: phase_config = {phase_config}")

                # Ensure DataManager exists
                if self.data_manager is None:
                    print("WIDGET: DataManager is None - creating new instance...")
                    try:
                        from ._data_manager import DataManager

                        self.data_manager = DataManager()
                        print("WIDGET: DataManager created successfully")
                    except Exception as dm_e:
                        error_msg = f"Failed to create DataManager: {dm_e}"
                        print(f"WIDGET: ERROR: {error_msg}")
                        self._add_log_entry(error_msg)
                        QMessageBox.critical(self, "DataManager Error", error_msg)
                        return

                # Close any existing file
                if self.data_manager.is_file_open():
                    print("WIDGET: Closing existing HDF5 file...")
                    try:
                        self.data_manager.close_file()
                        print("WIDGET: Existing file closed")
                    except Exception as close_e:
                        print(f"WIDGET: Warning: {close_e}")

                # Create recorder
                print("WIDGET: Creating TimelapseRecorder...")
                self.recorder = TimelapseRecorder(
                    duration_min=self.duration_spinbox.value(),
                    interval_sec=self.interval_spinbox.value(),
                    output_dir=self.directory_edit.text(),
                    esp32_controller=self.esp32_controller,
                    data_manager=self.data_manager,
                    imswitch_main=self.imswitch_main,
                    camera_name=self.camera_name,
                    phase_config=phase_config,
                )
                print(f"WIDGET: Recorder created: {self.recorder}")

                # Connect signals
                print("WIDGET: Connecting signals...")
                self.recorder.frame_captured.connect(self._on_frame_captured)
                self.recorder.recording_finished.connect(self._on_recording_finished)
                self.recorder.recording_paused.connect(self._on_recording_paused)
                self.recorder.recording_resumed.connect(self._on_recording_resumed)
                self.recorder.error_occurred.connect(self._on_recording_error)
                self.recorder.progress_updated.connect(self._on_progress_updated)
                self.recorder.status_updated.connect(self._on_status_updated)

                if hasattr(self.recorder, "phase_changed"):
                    self.recorder.phase_changed.connect(self._on_phase_changed)

                print("WIDGET: Signals connected")

                # Assign viewer
                if self.viewer is None:
                    self._add_log_entry("Warning: Napari viewer not connected")
                    print("WIDGET: Warning - no viewer")
                else:
                    self.recorder.viewer = self.viewer
                    print(f"WIDGET: Viewer assigned")

                # Stop status timer during recording
                if hasattr(self, "status_timer"):
                    self.status_timer.stop()
                    print("WIDGET: Status timer stopped")

                # ================================================================
                # STEP 6: START RECORDING
                # ================================================================
                print("WIDGET: Starting recorder...")
                self.recorder.start()

                # Initialize time displays
                self.elapsed_label.setText("Elapsed: 00:00:00")
                self.eta_label.setText("ETA: Calculating...")

                # Start live time update timer
                if not hasattr(self, "recording_timer"):
                    self.recording_timer = QTimer()
                    self.recording_timer.timeout.connect(self._update_recording_times)
                self.recording_timer.start(1000)

                print(f"WIDGET: recorder.start() returned")

                # Small delay to let thread start
                time.sleep(0.5)

                # Check if thread started
                if self.recorder.recording_thread:
                    print(f"WIDGET: Thread alive: {self.recorder.recording_thread.is_alive()}")
                else:
                    print("WIDGET: WARNING - No recording thread!")

                # Update UI
                self.recording = True
                self.start_button.setText("Recording...")
                self.start_button.setEnabled(False)
                self.pause_button.setEnabled(True)
                self.stop_button.setEnabled(True)
                self.reset_button.setEnabled(False)

                # Log start
                if phase_config["enabled"]:
                    start_phase = "Light" if phase_config["start_with_light"] else "Dark"
                    self._add_log_entry(
                        f"✓ Started day/night recording ({start_phase} phase) - HYBRID MODE"
                    )
                    print(f"WIDGET: Started with {start_phase} phase")
                else:
                    self._add_log_entry("✓ Started continuous recording - HYBRID MODE")
                    print("WIDGET: Started continuous recording")

                print("=" * 60)
                print("WIDGET: Recording started successfully (HYBRID MODE)!")
                print("=" * 60 + "\n")

            except Exception as e:
                print(f"WIDGET: EXCEPTION: {type(e).__name__}: {e}")
                import traceback

                traceback.print_exc()
                self._add_log_entry(f"Failed to start recording: {str(e)}")

                error_msg = f"Failed to start recording:\n\n{str(e)}"
                QMessageBox.critical(self, "Recording Start Failed", error_msg)

                # Restart timer if recording failed
                if hasattr(self, "status_timer"):
                    self.status_timer.start(10000)

                # Reset buttons
                self.start_button.setEnabled(True)
                self.start_button.setText("🎬 Start Recording")
                self.pause_button.setEnabled(False)
                self.stop_button.setEnabled(False)

        else:
            print("WIDGET: Already recording - ignoring start request")

    # ========================================================================
    # RECORDING CONTROL METHODS
    # ========================================================================

    def _update_recording_times(self):
        """Update elapsed and remaining time displays during recording (called every second)."""
        if not self.recording or not hasattr(self, "recorder") or self.recorder is None:
            return

        try:
            # Update elapsed time
            if hasattr(self.recorder, "start_time") and self.recorder.start_time is not None:
                elapsed_seconds = time.time() - self.recorder.start_time
                hours = int(elapsed_seconds // 3600)
                minutes = int((elapsed_seconds % 3600) // 60)
                seconds = int(elapsed_seconds % 60)
                self.elapsed_label.setText(f"Elapsed: {hours:02d}:{minutes:02d}:{seconds:02d}")

                # Calculate ETA based on current progress
                if hasattr(self.recorder, "current_frame") and hasattr(
                    self.recorder, "total_frames"
                ):
                    current = self.recorder.current_frame
                    total = self.recorder.total_frames

                    if current > 0 and total > 0:
                        avg_time_per_frame = elapsed_seconds / current
                        remaining_frames = total - current
                        remaining_seconds = avg_time_per_frame * remaining_frames

                        hours = int(remaining_seconds // 3600)
                        minutes = int((remaining_seconds % 3600) // 60)
                        seconds = int(remaining_seconds % 60)
                        self.eta_label.setText(f"ETA: {hours:02d}:{minutes:02d}:{seconds:02d}")
                    else:
                        self.eta_label.setText("ETA: Calculating...")
        except Exception as e:
            # Fail silently to avoid disrupting recording
            pass

    def _pause_recording(self):
        """Pause/resume recording."""
        if self.recorder:
            if hasattr(self.recorder, "is_paused") and self.recorder.is_paused():
                self.recorder.resume()
            else:
                self.recorder.pause()

    def _stop_recording(self):
        """Stop recording safely."""
        print("\n" + "=" * 80)
        print(">>> WIDGET: _stop_recording() CALLED")
        print("=" * 80)

        try:
            # Disable stop button to prevent double-clicks
            self.stop_button.setEnabled(False)

            # Check if recorder exists
            if not hasattr(self, "recorder") or self.recorder is None:
                print(">>> No active recorder")
                self._add_log_entry("⚠️ No recording to stop")
                self.stop_button.setEnabled(True)
                return

            # Check if actually recording
            if not self.recorder.is_recording():
                print(">>> Recorder not recording")
                self._add_log_entry("⚠️ Recording already stopped")
                self.stop_button.setEnabled(True)
                return

            # Send stop signal
            print(">>> Sending stop signal to recorder...")
            self._add_log_entry("⏹ Stopping recording...")
            self.recorder.stop()

            # Update UI immediately (non-blocking)
            self.recording = False
            self.start_button.setText("🎬 Start Recording")
            self.start_button.setEnabled(False)  # Will be enabled after reset
            self.pause_button.setEnabled(False)
            self.stop_button.setEnabled(False)

            # Show stopping message
            if hasattr(self, "status_label"):
                self.status_label.setText("Stopping recording...")

            print(">>> Stop signal sent - waiting for recording_finished signal")
            self._add_log_entry("⏳ Waiting for recorder to finish...")

        except Exception as e:
            print(f">>> ERROR in _stop_recording(): {e}")
            import traceback

            traceback.print_exc()
            self._add_log_entry(f"❌ Error stopping: {str(e)}")

            # Try to re-enable buttons
            self.stop_button.setEnabled(True)
            self.start_button.setEnabled(True)

            QMessageBox.critical(self, "Stop Error", f"Error stopping recording:\n{str(e)}")

        finally:
            print("=" * 80)
            print(">>> WIDGET: _stop_recording() COMPLETE")
            print("=" * 80 + "\n")

    def _reset_recording(self):
        """Reset everything and prepare for a new recording."""
        print("\n" + "=" * 80)
        print(">>> WIDGET: _reset_recording() CALLED")
        print("=" * 80)

        try:
            # Confirm with user
            reply = QMessageBox.question(
                self,
                "Reset Recording",
                "This will reset all recording state.\n\n"
                "Any in-progress data will be lost.\n\n"
                "Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )

            if reply != QMessageBox.Yes:
                print(">>> Reset cancelled by user")
                self._add_log_entry("⚠️ Reset cancelled")
                return

            self._add_log_entry("🔄 Resetting recording state...")

            # Stop any active recording
            print(">>> Step 1: Checking for active recording...")
            if hasattr(self, "recorder") and self.recorder is not None:
                try:
                    if self.recorder.is_recording():
                        print(">>> Recording is active - stopping...")
                        self._add_log_entry("⏹ Stopping active recording...")
                        self.recorder.stop()
                        time.sleep(0.5)
                except Exception as e:
                    print(f">>> Warning: Stop failed: {e}")

            # Clean up recorder
            print(">>> Step 2: Cleaning up recorder...")
            if hasattr(self, "recorder") and self.recorder is not None:
                try:
                    # Disconnect signals safely
                    try:
                        self.recorder.frame_captured.disconnect()
                    except Exception:
                        pass
                    try:
                        self.recorder.progress_updated.disconnect()
                    except Exception:
                        pass
                    try:
                        self.recorder.status_updated.disconnect()
                    except Exception:
                        pass
                    try:
                        self.recorder.error_occurred.disconnect()
                    except Exception:
                        pass
                    try:
                        self.recorder.recording_finished.disconnect()
                    except Exception:
                        pass
                    try:
                        if hasattr(self.recorder, "phase_changed"):
                            self.recorder.phase_changed.disconnect()
                    except Exception:
                        pass

                    print(">>> Signals disconnected")
                except Exception as e:
                    print(f">>> Warning: Signal disconnect failed: {e}")

                # Delete recorder
                try:
                    self.recorder = None
                    print(">>> Recorder deleted")
                    self._add_log_entry("✓ Recorder cleaned up")
                except Exception as e:
                    print(f">>> Warning: Recorder deletion failed: {e}")

            # Clean up data manager
            print(">>> Step 3: Cleaning up data manager...")
            if hasattr(self, "data_manager") and self.data_manager is not None:
                try:
                    if self.data_manager.is_file_open():
                        print(">>> Closing HDF5 file...")
                        self._add_log_entry("💾 Closing HDF5 file...")
                        self.data_manager.close_file()
                        print(">>> HDF5 file closed")
                        self._add_log_entry("✓ HDF5 file closed")
                except Exception as e:
                    print(f">>> Warning: File close failed: {e}")
                    self._add_log_entry(f"⚠️ File close warning: {str(e)}")

                try:
                    self.data_manager = None
                    print(">>> Data manager deleted")
                    self._add_log_entry("✓ Data manager cleaned up")
                except Exception as e:
                    print(f">>> Warning: Data manager deletion failed: {e}")

            # Reset ESP32
            print(">>> Step 4: Resetting ESP32...")
            if hasattr(self, "esp32_controller") and self.esp32_controller is not None:
                try:
                    print(">>> Turning off all LEDs...")
                    self._add_log_entry("💡 Turning off LEDs...")
                    self.esp32_controller.turn_off_all_leds()
                    print(">>> LEDs off")
                    self._add_log_entry("✓ LEDs off")
                except Exception as e:
                    print(f">>> Warning: LED off failed: {e}")
                    self._add_log_entry(f"⚠️ LED control warning: {str(e)}")

            # Clean up Napari layers
            print(">>> Step 5: Cleaning up Napari layers...")
            if self.viewer is not None:
                try:
                    layers_to_remove = []
                    for layer in self.viewer.layers:
                        layer_name = getattr(layer, "name", "").lower()
                        if any(kw in layer_name for kw in ["temp", "capture", "recording"]):
                            layers_to_remove.append(layer)

                    if layers_to_remove:
                        for layer in layers_to_remove:
                            try:
                                self.viewer.layers.remove(layer)
                                print(f">>> Removed layer: {layer.name}")
                            except Exception:
                                pass
                        self._add_log_entry(f"✓ Removed {len(layers_to_remove)} temporary layers")
                except Exception as e:
                    print(f">>> Warning: Layer cleanup failed: {e}")

            # Reset UI
            print(">>> Step 6: Resetting UI...")
            self._reset_ui()
            self._add_log_entry("✓ UI reset")

            # Garbage collection
            print(">>> Step 7: Running garbage collection...")
            import gc

            collected = gc.collect()
            print(f">>> Collected {collected} objects")
            self._add_log_entry(f"✓ Memory cleanup ({collected} objects)")

            print(">>> Reset complete!")
            self._add_log_entry("✅ Reset complete - Ready for new recording")

            QMessageBox.information(
                self,
                "Reset Complete",
                "Recording state has been reset.\n\n"
                "You can now configure and start a new recording.",
            )

            print("=" * 80)
            print(">>> WIDGET: _reset_recording() COMPLETE")
            print("=" * 80 + "\n")

        except Exception as e:
            print(f">>> ERROR in _reset_recording(): {e}")
            import traceback

            traceback.print_exc()
            self._add_log_entry(f"❌ Reset error: {str(e)}")
            QMessageBox.critical(self, "Reset Error", f"Error during reset:\n{str(e)}")

    # ========================================================================
    # SIGNAL HANDLERS
    # ========================================================================

    def _on_frame_captured(self, current_frame: int, total_frames: int):
        """Handle frame captured signal - minimal logging for 72h recordings."""
        # Update frame counter display
        self.frame_info_label.setText(f"Frame: {current_frame}/{total_frames}")

        # Only log every 100 frames
        if current_frame % 100 == 0 or current_frame == total_frames:
            self._add_log_entry(f"Progress: {current_frame}/{total_frames} frames captured")

        # Update progress bar
        progress = int((current_frame / total_frames) * 100) if total_frames > 0 else 0
        self.progress_bar.setValue(progress)

        # Periodic memory cleanup
        if current_frame % 50 == 0 and self.viewer is not None:
            try:
                self._cleanup_timelapse_layers()
            except Exception:
                pass

    def _cleanup_timelapse_layers(self):
        """Aggressively remove temporary layers from napari."""
        if self.viewer is None:
            return

        try:
            layers_to_remove = []

            # Pattern 1: Known temporary/interfering layers
            temp_patterns = [
                "timelapse live",
                "timelapse_live",
                "captured frames",
                "temp",
                "test",
                "quick test",
                "warmup",
                "preview",
            ]

            for layer in self.viewer.layers:
                layer_name = getattr(layer, "name", "").lower()

                # Remove known temp layers
                if any(pattern in layer_name for pattern in temp_patterns):
                    layers_to_remove.append(layer)
                    continue

                # Remove numbered frame layers
                if layer_name.startswith("frame_") or layer_name.startswith("image_"):
                    layers_to_remove.append(layer)

            # Remove identified layers with explicit data deletion
            if layers_to_remove:
                removed_count = 0
                for layer in layers_to_remove:
                    try:
                        # Delete layer data before removing
                        if hasattr(layer, "data"):
                            try:
                                layer.data = None
                                del layer.data
                            except Exception:
                                pass

                        self.viewer.layers.remove(layer)
                        removed_count += 1
                    except Exception:
                        pass

                if removed_count > 0:
                    print(f">>> Removed {removed_count} temporary layers")

            # Enforce maximum layer count
            max_layers = 3
            if len(self.viewer.layers) > max_layers:
                excess = len(self.viewer.layers) - max_layers
                print(
                    f">>> Viewer has {len(self.viewer.layers)} layers, removing {excess} oldest..."
                )

                for _ in range(excess):
                    try:
                        if len(self.viewer.layers) == 0:
                            break

                        oldest_layer = self.viewer.layers[0]
                        if hasattr(oldest_layer, "data"):
                            try:
                                oldest_layer.data = None
                                del oldest_layer.data
                            except Exception:
                                pass

                        self.viewer.layers.remove(oldest_layer)
                    except Exception:
                        break

            # Force GC after cleanup
            try:
                import gc

                collected = gc.collect(generation=0)
                if collected > 5:
                    print(f">>> GC after layer cleanup: {collected} objects collected")
            except Exception:
                pass

        except Exception as e:
            print(f">>> Layer cleanup error (non-fatal): {e}")

    def _on_recording_finished(self):
        """Handle recording finished signal."""
        print("\n" + "=" * 80)
        print(">>> WIDGET: _on_recording_finished() CALLED")
        print("=" * 80)

        try:
            # Stop recording timer
            if hasattr(self, "recording_timer") and self.recording_timer:
                try:
                    self.recording_timer.stop()
                    print(">>> Recording timer stopped")
                except Exception as e:
                    print(f">>> Warning: Timer stop failed: {e}")

            # Get final frame count
            frame_count = 0
            if hasattr(self, "recorder") and self.recorder:
                frame_count = self.recorder.current_frame

            # Update status
            status_msg = f"Recording complete - {frame_count} frames captured"
            if hasattr(self, "status_label"):
                self.status_label.setText(status_msg)

            self._add_log_entry(f"✅ {status_msg}")
            print(f">>> {status_msg}")

            # Update button states
            self.start_button.setEnabled(False)
            self.pause_button.setEnabled(False)
            self.stop_button.setEnabled(False)

            # Enable reset button
            if hasattr(self, "reset_button"):
                self.reset_button.setEnabled(True)
                print(">>> Reset button enabled")

            self._add_log_entry("🔄 Use Reset button to prepare for new recording")

            # Show completion dialog
            QMessageBox.information(
                self,
                "Recording Complete",
                f"Recording finished successfully!\n\n"
                f"Frames captured: {frame_count}\n\n"
                f"Use the Reset button to start a new recording.",
            )

        except Exception as e:
            print(f">>> ERROR in _on_recording_finished(): {e}")
            import traceback

            traceback.print_exc()
            self._add_log_entry(f"❌ Error in finish handler: {str(e)}")

        finally:
            print("=" * 80)
            print(">>> WIDGET: _on_recording_finished() COMPLETE")
            print("=" * 80 + "\n")

    def _reset_ui(self):
        """Reset all UI elements to initial state."""
        try:
            print(">>> Resetting UI elements...")

            # Reset recording flag
            self.recording = False

            # Reset buttons
            self.start_button.setEnabled(True)
            self.start_button.setText("🎬 Start Recording")

            self.pause_button.setEnabled(False)
            self.pause_button.setText("⏸ Pause")

            self.stop_button.setEnabled(False)

            if hasattr(self, "reset_button"):
                self.reset_button.setEnabled(False)

            # Reset progress
            if hasattr(self, "progress_bar"):
                self.progress_bar.setValue(0)
                self.progress_bar.setFormat("0%")

            # Reset time displays
            if hasattr(self, "elapsed_label"):
                self.elapsed_label.setText("Elapsed: 00:00:00")

            if hasattr(self, "eta_label"):
                self.eta_label.setText("ETA: --:--:--")

            # Reset frame counter
            if hasattr(self, "frame_info_label"):
                self.frame_info_label.setText("Frame: 0/0")

            # Reset phase displays
            if hasattr(self, "current_phase_label"):
                self.current_phase_label.setText("Phase: --")

            # Stop timers
            if hasattr(self, "recording_timer") and self.recording_timer:
                try:
                    self.recording_timer.stop()
                except Exception:
                    pass

            print(">>> UI reset complete")

        except Exception as e:
            print(f">>> Warning: UI reset partially failed: {e}")

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
        # Stop the recording timer
        if hasattr(self, "recording_timer"):
            self.recording_timer.stop()
            print("WIDGET: Recording timer stopped due to error")

        self._add_log_entry(f"Recording error: {error_message}")
        self.recording = False
        self.start_button.setText("🎬 Start Recording")
        self.start_button.setEnabled(True)

        # Restart status timer
        if hasattr(self, "status_timer"):
            self.status_timer.start(10000)
            self._add_log_entry("Status timer resumed")

        # Handle specific error types
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
        """Handle status update signal with proper time tracking."""
        # Parse status message to update UI elements
        if "Frame" in status_message and "/" in status_message:
            # Extract frame info from message
            parts = status_message.split("-")
            if len(parts) > 0:
                frame_part = parts[0].strip()
                self.frame_info_label.setText(frame_part)

            # Calculate elapsed time ourselves
            if hasattr(self, "recorder") and self.recorder and hasattr(self.recorder, "start_time"):
                if self.recorder.start_time is not None:
                    elapsed_seconds = time.time() - self.recorder.start_time
                    hours = int(elapsed_seconds // 3600)
                    minutes = int((elapsed_seconds % 3600) // 60)
                    seconds = int(elapsed_seconds % 60)
                    self.elapsed_label.setText(f"Elapsed: {hours:02d}:{minutes:02d}:{seconds:02d}")

            # Extract remaining time from message
            if "Remaining:" in status_message:
                try:
                    for part in parts:
                        if "Remaining:" in part:
                            remaining_text = part.strip()
                            remaining_seconds = float(
                                remaining_text.split("Remaining:")[1].strip().rstrip("s")
                            )

                            hours = int(remaining_seconds // 3600)
                            minutes = int((remaining_seconds % 3600) // 60)
                            seconds = int(remaining_seconds % 60)
                            self.eta_label.setText(f"ETA: {hours:02d}:{minutes:02d}:{seconds:02d}")
                            break
                except Exception:
                    self.eta_label.setText("ETA: Calculating...")

    # ========================================================================
    # PHASE CONTROL METHODS
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
                "led_type": "ir",
                "phase_elapsed_min": elapsed_minutes,
                "phase_remaining_min": 0,
                "cycle_number": 1,
                "total_cycles": 1,
            }

        light_duration = self.light_phase_spinbox.value()
        dark_duration = self.dark_phase_spinbox.value()
        cycle_duration = light_duration + dark_duration

        starts_with_light = self.start_phase_combo.currentIndex() == 0

        cycle_position = elapsed_minutes % cycle_duration
        current_cycle = int(elapsed_minutes / cycle_duration) + 1
        total_duration = self.duration_spinbox.value()
        total_cycles = max(1, int(total_duration / cycle_duration))

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
        else:
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
        """Handle phase change signal from recorder (UI updates only)."""
        self._update_phase_display(phase_info)

        led_type = phase_info.get("led_type", "ir")
        phase_name = phase_info.get("phase", "unknown")
        cycle_num = phase_info.get("cycle_number", 1)

        self._add_log_entry(
            f"Phase changed: {phase_name.upper()} phase (cycle {cycle_num}) - "
            f"LED: {led_type.upper()}"
        )

        if hasattr(self, "recording_status_label"):
            phase_emoji = "☀️" if phase_name == "light" else "🌙"
            self.recording_status_label.setText(
                f"Recording: {phase_emoji} {phase_name.upper()} Phase (Cycle {cycle_num})"
            )

    # ========================================================================
    # CONNECTION SETUP
    # ========================================================================

    def _setup_connections(self):
        """Setup signal connections."""
        # Recording params
        if hasattr(self, "duration_spinbox"):
            self.duration_spinbox.valueChanged.connect(self._update_expected_frames)
        if hasattr(self, "interval_spinbox"):
            self.interval_spinbox.valueChanged.connect(self._update_expected_frames)

        # Phase controls
        if hasattr(self, "enable_day_night_checkbox"):
            self.enable_day_night_checkbox.stateChanged.connect(self._toggle_phase_controls)
            self.enable_day_night_checkbox.stateChanged.connect(self._update_expected_frames)

        if hasattr(self, "light_phase_spinbox"):
            self.light_phase_spinbox.valueChanged.connect(self._update_expected_frames)
        if hasattr(self, "dark_phase_spinbox"):
            self.dark_phase_spinbox.valueChanged.connect(self._update_expected_frames)
        if hasattr(self, "start_phase_combo"):
            self.start_phase_combo.currentIndexChanged.connect(self._update_expected_frames)
        if hasattr(self, "dual_light_phase_checkbox"):
            self.dual_light_phase_checkbox.stateChanged.connect(self._on_dual_light_phase_toggled)

        # IR section
        ir_power_handler = getattr(self, "_on_ir_power_changed", None) or getattr(
            self, "_update_ir_led_power", None
        )
        if hasattr(self, "led_power_slider") and callable(ir_power_handler):
            self.led_power_slider.valueChanged.connect(ir_power_handler)

        ir_on_handler = getattr(self, "_ir_led_on", None) or getattr(self, "_led_on", None)
        ir_off_handler = getattr(self, "_ir_led_off", None) or getattr(self, "_led_off", None)
        if hasattr(self, "led_on_button") and callable(ir_on_handler):
            self.led_on_button.clicked.connect(ir_on_handler)
        if hasattr(self, "led_off_button") and callable(ir_off_handler):
            self.led_off_button.clicked.connect(ir_off_handler)

        # White section
        white_power_handler = getattr(self, "_on_white_power_changed", None) or getattr(
            self, "_update_white_led_power", None
        )
        if hasattr(self, "white_led_power_slider") and callable(white_power_handler):
            self.white_led_power_slider.valueChanged.connect(white_power_handler)

        if hasattr(self, "white_on_button") and hasattr(self, "_white_led_on"):
            self.white_on_button.clicked.connect(self._white_led_on)
        if hasattr(self, "white_off_button") and hasattr(self, "_white_led_off"):
            self.white_off_button.clicked.connect(self._white_led_off)

        # DataManager signals
        if hasattr(self, "data_manager"):
            if hasattr(self.data_manager, "file_created"):
                self.data_manager.file_created.connect(self._on_file_created)
            if hasattr(self.data_manager, "frame_saved"):
                self.data_manager.frame_saved.connect(self._on_frame_saved)
            if hasattr(self.data_manager, "metadata_updated"):
                self.data_manager.metadata_updated.connect(self._on_metadata_updated)

        # ESP32 controller signals
        if hasattr(self, "esp32_controller"):
            try:
                if hasattr(self.esp32_controller, "connection_status_changed"):
                    self.esp32_controller.connection_status_changed.connect(
                        self._on_esp32_conn_changed
                    )
                if hasattr(self.esp32_controller, "led_status_changed"):
                    self.esp32_controller.led_status_changed.connect(self._on_led_status_changed)
            except Exception as e:
                self._add_log_entry(f"ESP32 signal hookup warning: {e}")

        # Initialize labels/button captions
        if hasattr(self, "led_power_slider") and callable(ir_power_handler):
            try:
                ir_power_handler(self.led_power_slider.value())
            except TypeError:
                ir_power_handler()
        if hasattr(self, "white_led_power_slider") and callable(white_power_handler):
            try:
                white_power_handler(self.white_led_power_slider.value())
            except TypeError:
                white_power_handler()

        # Sync phase_config with UI
        self.phase_config = getattr(self, "phase_config", {})
        self.phase_config["enabled"] = (
            bool(self.enable_day_night_checkbox.isChecked())
            if hasattr(self, "enable_day_night_checkbox")
            else self.phase_config.get("enabled", False)
        )
        self.phase_config["dual_light_phase"] = (
            bool(self.dual_light_phase_checkbox.isChecked())
            if hasattr(self, "dual_light_phase_checkbox")
            else self.phase_config.get("dual_light_phase", False)
        )

    def _on_dual_light_phase_toggled(self, state: int):
        """Handle dual light phase checkbox toggle."""
        enabled = bool(state)
        self.phase_config["dual_light_phase"] = enabled

        if hasattr(self, "phase_stats_label"):
            if (
                getattr(self, "enable_day_night_checkbox", None)
                and self.enable_day_night_checkbox.isChecked()
            ):
                txt = (
                    "● Phase Pattern: Day/Night (dual in Light)"
                    if enabled
                    else "● Phase Pattern: Day/Night"
                )
            else:
                txt = "● Phase Pattern: Continuous"
            self.phase_stats_label.setText(txt)

        self._update_expected_frames()

    def _setup_timers(self):
        """Setup periodic timers."""
        # Initial camera check only
        self._check_camera_connection()

        # Add initial log entries
        self._add_log_entry("Plugin initialized successfully (HYBRID MODE)...")

    # ========================================================================
    # UI HELPER METHODS
    # ========================================================================

    def _update_expected_frames(self):
        """Update expected frames calculation with phase support."""
        duration_min = self.duration_spinbox.value()
        interval_sec = self.interval_spinbox.value()

        total_seconds = duration_min * 60
        expected_frames = int(total_seconds / interval_sec) + 1

        self.expected_frames_label.setText(str(expected_frames))
        self.frames_label.setText(f"● Frames: {expected_frames}")
        self.duration_label.setText(f"● Duration: {duration_min}.0 min")
        self.intervals_label.setText(f"● Intervals: {interval_sec}.0 sec")

        if (
            hasattr(self, "enable_day_night_checkbox")
            and self.enable_day_night_checkbox.isChecked()
        ):
            light_min = self.light_phase_spinbox.value()
            dark_min = self.dark_phase_spinbox.value()
            cycle_duration = light_min + dark_min

            if cycle_duration > 0:
                total_cycles = duration_min / cycle_duration
                light_frames = int((light_min * 60) / interval_sec) + 1
                dark_frames = int((dark_min * 60) / interval_sec) + 1

                self.phase_stats_label.setText(
                    f"● Phase Pattern: {total_cycles:.1f} cycles | "
                    f"Light: {light_frames} frames | Dark: {dark_frames} frames"
                )

                complete_cycles = int(total_cycles)
                partial_cycle_min = (total_cycles - complete_cycles) * cycle_duration

                self.phase_cycles_label.setText(
                    f"Total Cycles: {complete_cycles} complete + {partial_cycle_min:.1f}min partial"
                )
            else:
                self.phase_stats_label.setText("● Phase Pattern: Invalid (zero duration)")
        else:
            self.phase_stats_label.setText("● Phase Pattern: Continuous recording")

    def _select_directory(self):
        """Select recording directory."""
        directory = QFileDialog.getExistingDirectory(self, "Select Recording Directory")
        if directory:
            self.directory_edit.setText(directory)
            self._add_log_entry(f"Recording directory set: {directory}")

    def _update_status(self):
        """Minimal status update - no camera checks."""
        try:
            # ESP32 status only
            if self.esp32_controller.is_connected():
                self.esp32_status_label_right.setText("ESP32: Connected")
                self.esp32_status_label_right.setStyleSheet("color: #00ff00;")
            else:
                self.esp32_status_label_right.setText("ESP32: Disconnected")
                self.esp32_status_label_right.setStyleSheet("color: #ff0000;")

            # Recording status
            if self.recording:
                self.recording_status_label.setText("Recording: Active")
                self.recording_status_label.setStyleSheet("color: #ffff00;")
            else:
                self.recording_status_label.setText("Recording: Ready")
                self.recording_status_label.setStyleSheet("color: #00ff00;")

        except Exception as e:
            print(f"Status update error: {e}")

    # ========================================================================
    # ESP32 LED CONTROL METHODS
    # ========================================================================

    def _on_ir_power_changed(self, val: int):
        """IR slider changed - updates IR LED power live."""
        try:
            val = int(val)
            self.desired_ir_power = val

            # Update UI labels
            if hasattr(self, "led_power_value_label"):
                self.led_power_value_label.setText(f"{val}%")
            if hasattr(self, "led_on_button"):
                self.led_on_button.setText(f"💡 IR ON ({val}%)")

            # ✅ FIXED: Always set IR power (auch wenn White selected ist!)
            if hasattr(self, "esp32_controller") and self.esp32_controller.is_connected():
                self.esp32_controller.set_ir_power(val)  # ← DIREKT zu IR!

        except Exception as e:
            self._add_log_entry(f"IR power change failed: {e}")

    def _ir_led_on(self):
        """Turn IR LED on - simplified."""
        try:
            if not self.esp32_controller.is_connected():
                self._add_log_entry("ESP32 not connected")
                return

            power = getattr(self, "desired_ir_power", self.led_power_slider.value())

            # ✅ ONE HIGH-LEVEL CALL (Hardware-Details im Controller!)
            self.esp32_controller.turn_on_ir_led(power)

            # UI updates only
            self._add_log_entry(f"IR LED ON at {power}%")
            if hasattr(self, "esp32_status_label"):
                self.esp32_status_label.setText(f"ESP32: IR ON – {power}%")

        except Exception as e:
            self._add_log_entry(f"IR LED ON failed: {e}")

    def _ir_led_off(self):
        """Turn IR LED off - simplified."""
        try:
            if not self.esp32_controller.is_connected():
                self._add_log_entry("ESP32 not connected")
                return

            # ✅ ONE HIGH-LEVEL CALL
            self.esp32_controller.turn_off_ir_led()

            # UI updates only
            self._add_log_entry("IR LED OFF")
            if hasattr(self, "esp32_status_label"):
                self.esp32_status_label.setText("ESP32: IR OFF")

        except Exception as e:
            self._add_log_entry(f"IR LED OFF failed: {e}")

    def _on_white_power_changed(self, val: int):
        """White slider changed - updates White LED power live."""
        try:
            val = int(val)
            self.desired_white_power = val

            # Update UI labels
            if hasattr(self, "white_led_power_value_label"):
                self.white_led_power_value_label.setText(f"{val}%")
            if hasattr(self, "white_on_button"):
                self.white_on_button.setText(f"💡 White ON ({val}%)")

            # ✅ FIXED: Always set White power (auch wenn IR selected ist!)
            if hasattr(self, "esp32_controller") and self.esp32_controller.is_connected():
                self.esp32_controller.set_white_power(val)  # ← DIREKT zu White!

        except Exception as e:
            self._add_log_entry(f"White power change failed: {e}")

    def _white_led_on(self):
        """Turn White LED on - simplified."""
        try:
            if not self.esp32_controller.is_connected():
                self._add_log_entry("ESP32 not connected")
                return

            power = getattr(self, "desired_white_power", self.white_led_power_slider.value())

            # ✅ ONE HIGH-LEVEL CALL
            self.esp32_controller.turn_on_white_led(power)

            # UI updates only
            self._add_log_entry(f"White LED ON at {power}%")
            if hasattr(self, "esp32_status_label"):
                self.esp32_status_label.setText(f"ESP32: WHITE ON – {power}%")

        except Exception as e:
            self._add_log_entry(f"White LED ON failed: {e}")

    def _white_led_off(self):
        """Turn White LED off - simplified."""
        try:
            if not self.esp32_controller.is_connected():
                self._add_log_entry("ESP32 not connected")
                return

            # ✅ ONE HIGH-LEVEL CALL
            self.esp32_controller.turn_off_white_led()

            # UI updates only
            self._add_log_entry("White LED OFF")
            if hasattr(self, "esp32_status_label"):
                self.esp32_status_label.setText("ESP32: WHITE OFF")

        except Exception as e:
            self._add_log_entry(f"White LED OFF failed: {e}")

    def _manual_flash(self):
        """Manual LED flash."""
        try:
            self.esp32_controller.begin_sync_pulse()
            info = self.esp32_controller.wait_sync_complete(timeout=5.0)
            duration_ms = float(info.get("led_duration_ms", info.get("timing_ms", 0)))
            temp = float(info.get("temperature", 0))
            humidity = float(info.get("humidity", 0))
            self._add_log_entry(
                f"Manual flash: {duration_ms:.0f}ms, T={temp:.1f}°C, H={humidity:.1f}%"
            )
        except Exception as e:
            self._add_log_entry(f"Manual flash failed: {e}")

    def _read_sensors(self):
        """Read environmental sensors."""
        try:
            temp, humidity = self.esp32_controller.read_sensors()
            self.temperature_label.setText(f"{temp:.1f}°C")
            self.humidity_label.setText(f"{humidity:.1f}%")
            self._add_log_entry(f"Temperature: {temp:.1f}°C, Humidity: {humidity:.1f}%")
        except Exception as e:
            self._add_log_entry(f"Sensor reading failed: {str(e)}")

    def widget_connect_esp32_via_imswitch(self):
        """Connect using ImSwitch's ESP32."""
        try:
            self._add_log_entry("Connecting via ImSwitch ESP32Manager...")

            self.connect_esp32_button.setEnabled(False)
            self.connect_esp32_button.setText("Connecting...")

            success = self.esp32_controller.connect_via_imswitch()

            if success:
                self._add_log_entry("✓ ESP32 connected via ImSwitch")
                self.esp32_status_label.setText("ESP32: Connected (ImSwitch)")
                self.esp32_status_label.setStyleSheet("color: #00ff00;")
                self.connect_esp32_button.setText("Connected")
            else:
                self._add_log_entry("ImSwitch method failed, trying direct...")
                success = self.esp32_controller.connect_with_imswitch_protection()

                if success:
                    self._add_log_entry("✓ ESP32 connected (direct)")
                    self.esp32_status_label.setText("ESP32: Connected (Direct)")

            self.connect_esp32_button.setEnabled(True)

        except Exception as e:
            self._add_log_entry(f"Connection failed: {e}")
            self.connect_esp32_button.setEnabled(True)

    def _disconnect_esp32(self):
        """Disconnect from ESP32."""
        try:
            self._add_log_entry("Disconnecting from ESP32...")

            self.disconnect_esp32_button.setEnabled(False)
            self.disconnect_esp32_button.setText("Disconnecting...")

            self.esp32_status_label.setText("ESP32: Disconnecting...")
            self.esp32_status_label.setStyleSheet("color: #ffaa00;")

            self.esp32_controller.disconnect()

            self._add_log_entry("ESP32 disconnected")
            self.esp32_status_label.setText("ESP32: Disconnected")
            self.esp32_status_label.setStyleSheet("color: #888888;")
            self.esp32_status_label_right.setText("ESP32: Disconnected")
            self.esp32_status_label_right.setStyleSheet("color: #888888;")

            self.connect_esp32_button.setText("Connect ESP32")
            self.connect_esp32_button.setEnabled(True)
            self.disconnect_esp32_button.setText("Disconnect")
            self.disconnect_esp32_button.setEnabled(False)

        except Exception as e:
            self._add_log_entry(f"Disconnection failed: {e}")

            self.connect_esp32_button.setText("Connect ESP32")
            self.connect_esp32_button.setEnabled(True)
            self.disconnect_esp32_button.setText("Disconnect")
            self.disconnect_esp32_button.setEnabled(False)

    # ========================================================================
    # LED CALIBRATION METHODS
    # ========================================================================

    def _measure_frame_intensity(self, frame, roi_fraction=0.5, percentile=75):
        """Measure representative intensity from center ROI."""
        if frame is None or frame.size == 0:
            return 0

        h, w = frame.shape[:2]
        roi_h, roi_w = int(h * roi_fraction), int(w * roi_fraction)
        y1, x1 = (h - roi_h) // 2, (w - roi_w) // 2
        y2, x2 = y1 + roi_h, x1 + roi_w

        roi = frame[y1:y2, x1:x2]
        intensity = np.percentile(roi.flatten(), percentile)

        return float(intensity)

    def _auto_calibrate_leds(self):
        """Run LED auto-calibration."""
        try:
            if not self.viewer:
                self.calibration_status_label.setText("✗ No viewer available")
                self.calibration_status_label.setStyleSheet("color: red; font-weight: bold;")
                self._add_log_entry("ERROR: No Napari viewer available for calibration")
                return

            # Try to ensure Live View is active
            if self.imswitch_main and hasattr(self.imswitch_main, "liveViewWidget"):
                try:
                    live_view = self.imswitch_main.liveViewWidget
                    if hasattr(live_view, "liveViewActive"):
                        if not live_view.liveViewActive:
                            self._add_log_entry("Starting Live View for calibration...")
                            if hasattr(live_view, "resumeStream"):
                                live_view.resumeStream()
                            elif hasattr(live_view, "liveViewButton"):
                                live_view.liveViewButton.click()
                            time.sleep(1.5)
                            self._add_log_entry("Live View started")
                except Exception as e:
                    self._add_log_entry(f"Could not auto-start Live View: {e}")

            # Verify live camera feed
            from napari.layers import Image

            has_live_layer = False
            test_frame = None
            test_intensity = 0

            for layer in self.viewer.layers:
                if isinstance(layer, Image):
                    data = getattr(layer, "data", None)
                    if data is not None and data.size > 0:
                        test_frame = np.array(data, copy=True)
                        test_intensity = float(np.mean(test_frame))
                        if test_intensity > 0:
                            has_live_layer = True
                            break

            if not has_live_layer or test_frame is None or test_intensity == 0:
                error_msg = "✗ No live camera feed!\n" "Start Live View in ImSwitch first"
                self.calibration_status_label.setText(error_msg)
                self.calibration_status_label.setStyleSheet("color: red; font-weight: bold;")
                self._add_log_entry("ERROR: Calibration requires live camera feed")
                return

            self._add_log_entry(f"Live feed detected - current intensity: {test_intensity:.1f}")

            # Start calibration
            self.calibration_status_label.setText("⏳ Calibrating... please wait")
            self.calibration_status_label.setStyleSheet("color: orange; font-weight: bold;")
            QApplication.processEvents()

            target_intensity = 200.0
            dual_mode = self.dual_light_phase_checkbox.isChecked()

            print(f"\n{'='*80}")
            print(f">>> AUTO-CALIBRATION START")
            print(f">>> Target intensity: {target_intensity}")
            print(f">>> Dual light mode: {dual_mode}")
            print(f"{'='*80}")

            # Define capture callback
            def capture_and_measure():
                """Capture frame and measure intensity."""
                # Try direct ImSwitch camera access
                if self.imswitch_main:
                    try:
                        if hasattr(self.imswitch_main, "detectorsManager"):
                            detectors = self.imswitch_main.detectorsManager
                            detector_names = detectors.getAllDeviceNames()
                            camera_name = None

                            for name in detector_names:
                                if "camera" in name.lower() or "hik" in name.lower():
                                    camera_name = name
                                    break

                            if not camera_name and detector_names:
                                camera_name = detector_names[0]

                            if camera_name:
                                detector = detectors[camera_name]
                                best_frame = None
                                best_mean = 0

                                for attempt in range(5):
                                    try:
                                        frame = detector.getLatestFrame()

                                        if frame is not None and frame.size > 0:
                                            frame = np.array(frame, copy=True)
                                            frame_mean = float(np.mean(frame))

                                            if frame_mean > best_mean:
                                                best_mean = frame_mean
                                                best_frame = frame

                                            if frame_mean > 10:
                                                break

                                        if attempt < 4:
                                            time.sleep(0.1)

                                    except Exception as e:
                                        if attempt < 4:
                                            time.sleep(0.1)
                                        continue

                                if best_frame is not None and best_mean > 1.0:
                                    intensity = self._measure_frame_intensity(
                                        best_frame, roi_fraction=0.5, percentile=75
                                    )

                                    if intensity < 1.0:
                                        raise RuntimeError(
                                            f"Measured intensity too low: {intensity:.1f}"
                                        )

                                    return best_frame, intensity

                    except Exception as e:
                        print(f"Direct ImSwitch capture failed: {e}")

                # Fallback to Napari
                if not self.viewer:
                    raise RuntimeError("No capture method available")

                from napari.layers import Image

                live_layer = None
                for layer in self.viewer.layers:
                    if isinstance(layer, Image):
                        data = getattr(layer, "data", None)
                        if data is not None and data.size > 0:
                            live_layer = layer
                            break

                if live_layer is None:
                    raise RuntimeError("No live layer found")

                QApplication.processEvents()
                time.sleep(0.5)
                QApplication.processEvents()

                samples = []
                for i in range(10):
                    QApplication.processEvents()
                    time.sleep(0.1)

                    frame = np.array(live_layer.data, copy=True)
                    frame_mean = float(np.mean(frame))
                    samples.append((frame, frame_mean))

                samples.sort(key=lambda x: x[1], reverse=True)
                best_frame, best_mean = samples[0]

                if best_mean < 1.0:
                    raise RuntimeError(f"All capture methods failed - best mean: {best_mean:.1f}")

                intensity = self._measure_frame_intensity(best_frame, 0.5, 75)
                return best_frame, intensity

            # Run calibration
            results = self.esp32_controller.auto_calibrate_led_intensity(
                target_intensity=target_intensity,
                capture_callback=capture_and_measure,
                dual_light_mode=dual_mode,
            )

            # Apply calibrated powers
            self.esp32_controller.apply_calibrated_powers(results)

            # Update UI
            if dual_mode:
                ir_p, white_p = results.get("dual", (100, 100))
                result_text = (
                    f"✓ Calibrated (Dual Mode)\n"
                    f"IR (Dark): {results['ir']}%\n"
                    f"Dual (Light): IR={ir_p}% + White={white_p}%"
                )
            else:
                result_text = (
                    f"✓ Calibrated (Single Mode)\n"
                    f"IR (Dark): {results['ir']}%\n"
                    f"White (Light): {results['white']}%"
                )

            self.calibration_status_label.setText(result_text)
            self.calibration_status_label.setStyleSheet("color: green; font-weight: bold;")

            # Save calibration
            self._save_calibration(results)

            # Update sliders
            if hasattr(self, "led_power_slider"):
                self.led_power_slider.setValue(results["ir"])

            if dual_mode and "dual" in results:
                _, white_p = results["dual"]
                if hasattr(self, "white_led_power_slider"):
                    self.white_led_power_slider.setValue(white_p)
            elif "white" in results:
                if hasattr(self, "white_led_power_slider"):
                    self.white_led_power_slider.setValue(results["white"])

            self._add_log_entry("Calibration completed successfully")

        except Exception as e:
            error_msg = f"✗ Calibration failed:\n{str(e)}"
            self.calibration_status_label.setText(error_msg)
            self.calibration_status_label.setStyleSheet("color: red; font-weight: bold;")
            self._add_log_entry(f"Calibration failed: {e}")
            import traceback

            traceback.print_exc()

    def _save_calibration(self, results: dict):
        """Save calibration to JSON file."""
        import json
        from pathlib import Path

        config_file = Path.home() / ".nematostella_led_calibration.json"

        try:
            data = {
                "timestamp": time.time(),
                "date": time.strftime("%Y-%m-%d %H:%M:%S"),
                "calibrated_powers": results,
                "camera": getattr(self, "camera_name", "widefield"),
            }

            with open(config_file, "w") as f:
                json.dump(data, f, indent=2)

            print(f">>> Calibration saved to: {config_file}")
            self._add_log_entry(f"Calibration saved to: {config_file}")

        except Exception as e:
            print(f">>> WARNING: Could not save calibration: {e}")
            self._add_log_entry(f"Could not save calibration: {e}")

    def _load_calibration(self) -> Optional[dict]:
        """Load saved calibration from file."""
        import json
        from pathlib import Path

        config_file = Path.home() / ".nematostella_led_calibration.json"

        if not config_file.exists():
            return None

        try:
            with open(config_file, "r") as f:
                data = json.load(f)

            age_days = (time.time() - data["timestamp"]) / 86400
            if age_days > 30:
                print(f">>> WARNING: Calibration is {age_days:.0f} days old")
                self._add_log_entry(f"WARNING: Calibration is {age_days:.0f} days old")
            else:
                print(f">>> Loaded calibration from {age_days:.1f} days ago")
                self._add_log_entry(f"Loaded calibration from {age_days:.1f} days ago")

            return data.get("calibrated_powers")

        except Exception as e:
            print(f">>> WARNING: Could not load calibration: {e}")
            self._add_log_entry(f"Could not load calibration: {e}")
            return None

    # ========================================================================
    # DIAGNOSTIC METHODS
    # ========================================================================

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
        """Quick frame capture test."""
        try:
            self._add_log_entry("Quick frame test...")

            start_time = time.time()
            frame, metadata = self._get_live_napari_frame()
            end_time = time.time()

            capture_time = (end_time - start_time) * 1000
            fps = 1.0 / (end_time - start_time) if (end_time - start_time) > 0 else 0

            self.fps_label.setText(f"FPS: {fps:.1f}")
            self.test_results_text.clear()
            self.test_results_text.append(f"Frame captured in {capture_time:.1f}ms")
            self.test_results_text.append(f"Frame shape: {frame.shape}")
            self.test_results_text.append(f"Frame dtype: {frame.dtype}")
            self.test_results_text.append(f"Source: {metadata.get('source', 'unknown')}")
            self.test_results_text.append("✓ Widget frame capture working")

            if self.viewer is not None:
                layer_name = "Quick Test Frame"
                if layer_name in [layer.name for layer in self.viewer.layers]:
                    layer = next(layer for layer in self.viewer.layers if layer.name == layer_name)
                    layer.data = frame
                else:
                    self.viewer.add_image(frame, name=layer_name, colormap="gray")
                self.test_results_text.append("✓ Frame displayed in napari")

            self._add_log_entry(f"Quick test: {capture_time:.1f}ms, {fps:.1f} FPS")

        except Exception as e:
            self._add_log_entry(f"Quick frame test failed: {str(e)}")
            self.test_results_text.clear()
            self.test_results_text.append(f"✗ Frame test failed: {str(e)}")

    def _get_live_napari_frame(self) -> tuple[np.ndarray, dict]:
        """Get a frame from any non-empty Napari image layer."""
        if self.viewer is None:
            raise RuntimeError("No Napari viewer available")
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
        raise RuntimeError("No suitable Napari image layer found")

    def _has_live_layer(self) -> bool:
        """Check if there's a live layer available."""
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
            return True
        return False

    def _debug_esp32_communication(self):
        """Debug ESP32 communication."""
        self._add_log_entry("=== ESP32 COMMUNICATION DEBUG ===")
        self.test_results_text.clear()

        try:
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
        """Debug ImSwitch structure."""
        if self.imswitch_main is None:
            self.test_results_text.append("ImSwitch not available")
            return

        self.test_results_text.clear()
        self.test_results_text.append("=== ImSwitch Structure Debug ===")

        attrs = [attr for attr in dir(self.imswitch_main) if not attr.startswith("_")]
        self.test_results_text.append(f"ImSwitch attributes: {', '.join(attrs[:10])}...")

        live_attrs = ["liveViewWidget", "viewWidget", "imageWidget", "detectorsManager"]
        for attr in live_attrs:
            if hasattr(self.imswitch_main, attr):
                obj = getattr(self.imswitch_main, attr)
                self.test_results_text.append(f"✓ Found {attr}: {type(obj)}")

                if hasattr(obj, "img"):
                    img_obj = getattr(obj, "img", None)
                    if img_obj is not None:
                        shape_info = img_obj.shape if hasattr(img_obj, "shape") else type(img_obj)
                        self.test_results_text.append(f"  - Has image data: {shape_info}")
                if hasattr(obj, "getCurrentImage"):
                    self.test_results_text.append(f"  - Has getCurrentImage method")
            else:
                self.test_results_text.append(f"✗ No {attr} found")

        if self.viewer is not None:
            layer_names = [layer.name for layer in self.viewer.layers]
            self.test_results_text.append(f"Napari layers: {layer_names}")
        else:
            self.test_results_text.append("No napari viewer available")

    # ========================================================================
    # DATAMANAGER SIGNAL HANDLERS
    # ========================================================================

    def _on_file_created(self, filepath: str):
        """Handle file created signal."""
        self._add_log_entry(f"Recording file created: {filepath}")
        filename = Path(filepath).name
        self.recording_status_label.setText(f"Recording: File Created ({filename})")

    def _on_frame_saved(self, frame_number: int):
        """Handle frame saved signal."""
        pass  # Too verbose for log

    def _on_metadata_updated(self, metadata: dict):
        """Handle metadata updated signal."""
        if "actual_frames" in metadata:
            actual_frames = metadata["actual_frames"]
            expected_frames = metadata.get("expected_frames", 0)
            if expected_frames > 0:
                progress = int((actual_frames / expected_frames) * 100)
                self.progress_bar.setValue(progress)

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


# ========================================================================
# NPE2 PLUGIN HOOKS
# ========================================================================


def create_timelapse_widget(napari_viewer=None):
    """Create and return the timelapse widget."""
    return NematostallTimelapseCaptureWidget(napari_viewer, None)


from napari_plugin_engine import napari_hook_implementation


@napari_hook_implementation
def napari_experimental_provide_dock_widget():
    """Provide the timelapse capture dock widget."""

    def create_widget():
        print("=== PLUGIN HOOK CALLED (HYBRID MODE) ===")
        viewer = None
        try:
            import napari

            viewer = napari.current_viewer()
            print(f"Plugin hook: viewer = {viewer}")
            if viewer:
                print(f"Plugin hook: viewer has {len(viewer.layers)} layers")
        except Exception as e:
            print(f"Plugin hook: Failed to get viewer: {e}")

        widget = NematostallTimelapseCaptureWidget(viewer, None)
        print("=== PLUGIN WIDGET CREATED (HYBRID MODE) ===")
        return widget

    return create_widget
