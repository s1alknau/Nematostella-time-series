"""
LED Control Panel - UI für LED-Steuerung und Kalibrierung
"""

from qtpy.QtCore import Qt
from qtpy.QtCore import Signal as pyqtSignal
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class LEDControlPanel(QWidget):
    """Panel für LED-Steuerung"""

    # Signals
    led_on_requested = pyqtSignal(str)  # led_type: 'ir', 'white', 'dual'
    led_off_requested = pyqtSignal(str)  # led_type: 'ir', 'white'
    led_power_changed = pyqtSignal(str, int)  # led_type, power
    calibration_requested = pyqtSignal(str)  # mode: 'ir', 'white', 'dual'
    exposure_changed = pyqtSignal(float)  # exposure in ms, entered by the user

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Info Text
        info_label = QLabel(
            "Control LED power and perform intensity calibration. "
            "Use calibration to match target intensities across different LED modes."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(
            "color: #7f8c8d; padding: 10px; background-color: #ecf0f1; border-radius: 5px;"
        )
        layout.addWidget(info_label)

        # LED Control Group
        control_group = QGroupBox("LED Control")
        control_layout = QVBoxLayout()

        # LED Type Selection
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("LED Type:"))

        self.led_type_combo = QComboBox()
        self.led_type_combo.addItems(["IR LED", "White LED"])
        type_layout.addWidget(self.led_type_combo)
        type_layout.addStretch()

        control_layout.addLayout(type_layout)

        # On/Off Buttons
        button_layout = QHBoxLayout()

        self.led_on_button = QPushButton("💡 Turn ON")
        self.led_on_button.setStyleSheet(
            """
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
                padding: 8px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """
        )
        self.led_on_button.clicked.connect(self._on_led_on_clicked)
        button_layout.addWidget(self.led_on_button)

        self.led_off_button = QPushButton("⚫ Turn OFF")
        self.led_off_button.setStyleSheet(
            """
            QPushButton {
                background-color: #e74c3c;
                color: white;
                font-weight: bold;
                padding: 8px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """
        )
        self.led_off_button.clicked.connect(self._on_led_off_clicked)
        button_layout.addWidget(self.led_off_button)

        control_layout.addLayout(button_layout)

        control_group.setLayout(control_layout)
        layout.addWidget(control_group)

        # LED Power Group
        power_group = QGroupBox("LED Power Settings")
        power_layout = QFormLayout()

        # IR LED Power
        # valueChanged fires on every tick of a slider drag → sending an
        # ESP32 command each time saturated the serial queue (each command
        # waits up to 1 s for ACK) and the LED ended up in an inconsistent
        # state. Wire the ESP32 command to sliderReleased only; keep the
        # cheap in-GUI label update on valueChanged so the % follows the
        # thumb live.
        ir_layout = QHBoxLayout()
        self.ir_power_slider = QSlider(Qt.Horizontal)
        self.ir_power_slider.setRange(0, 100)
        self.ir_power_slider.setValue(100)
        ir_layout.addWidget(self.ir_power_slider)

        self.ir_power_label = QLabel("100%")
        self.ir_power_label.setMinimumWidth(50)
        self.ir_power_label.setStyleSheet("font-weight: bold;")
        ir_layout.addWidget(self.ir_power_label)

        self.ir_power_slider.valueChanged.connect(lambda v: self.ir_power_label.setText(f"{v}%"))
        self.ir_power_slider.sliderReleased.connect(
            lambda: self._on_power_changed("ir", self.ir_power_slider.value())
        )

        power_layout.addRow("IR LED Power:", ir_layout)

        # White LED Power (same reasoning as IR: command only on release)
        white_layout = QHBoxLayout()
        self.white_power_slider = QSlider(Qt.Horizontal)
        self.white_power_slider.setRange(0, 100)
        self.white_power_slider.setValue(50)
        white_layout.addWidget(self.white_power_slider)

        self.white_power_label = QLabel("50%")
        self.white_power_label.setMinimumWidth(50)
        self.white_power_label.setStyleSheet("font-weight: bold;")
        white_layout.addWidget(self.white_power_label)

        self.white_power_slider.valueChanged.connect(
            lambda v: self.white_power_label.setText(f"{v}%")
        )
        self.white_power_slider.sliderReleased.connect(
            lambda: self._on_power_changed("white", self.white_power_slider.value())
        )

        power_layout.addRow("White LED Power:", white_layout)

        power_group.setLayout(power_layout)
        layout.addWidget(power_group)

        # Calibration Group
        calib_group = QGroupBox("Intensity Calibration")
        calib_layout = QVBoxLayout()

        calib_info = QLabel(
            "Calibration finds optimal LED power to match target intensities. "
            "Requires active camera feed."
        )
        calib_info.setWordWrap(True)
        calib_info.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        calib_layout.addWidget(calib_info)

        # Target Intensity Input
        target_layout = QHBoxLayout()
        target_layout.addWidget(QLabel("Target Intensity:"))

        self.target_intensity_spinbox = QDoubleSpinBox()
        self.target_intensity_spinbox.setRange(1.0, 1000.0)
        self.target_intensity_spinbox.setValue(200.0)
        self.target_intensity_spinbox.setDecimals(1)
        self.target_intensity_spinbox.setSingleStep(10.0)
        self.target_intensity_spinbox.setToolTip(
            "Target mean intensity for calibration.\n"
            "Adjust based on your optical configuration (objective aperture).\n"
            "Typical values: 30-50 for high aperture, 100-200 for low aperture."
        )
        self.target_intensity_spinbox.setMinimumWidth(100)
        target_layout.addWidget(self.target_intensity_spinbox)
        target_layout.addStretch()

        calib_layout.addLayout(target_layout)

        # Distance the brightest pixels keep from the sensor limit. The
        # search reduces the LED power until they sit that far below it.
        saturation_layout = QHBoxLayout()
        saturation_layout.addWidget(QLabel("Headroom (%):"))

        self.saturation_spinbox = QDoubleSpinBox()
        self.saturation_spinbox.setRange(0.0, 50.0)
        self.saturation_spinbox.setDecimals(1)
        self.saturation_spinbox.setSingleStep(0.5)
        self.saturation_spinbox.setValue(5.0)
        self.saturation_spinbox.setToolTip(
            "Distance the brightest pixels keep from the sensor limit.\n"
            "5 % means they are regulated to about 95 % of full scale, so\n"
            "nothing is clipped and the value range is still used fully.\n"
            "The LED power is lowered for this even if the target is missed."
        )
        self.saturation_spinbox.setMinimumWidth(100)
        saturation_layout.addWidget(self.saturation_spinbox)
        saturation_layout.addStretch()

        calib_layout.addLayout(saturation_layout)

        # Exposure. Filled from the camera after every calibration; editing it
        # applies the value to the camera, so a user can override what the
        # calibration found without leaving the plugin.
        exposure_layout = QHBoxLayout()
        exposure_layout.addWidget(QLabel("Exposure (ms):"))

        self.exposure_spinbox = QDoubleSpinBox()
        self.exposure_spinbox.setRange(0.1, 1000.0)
        self.exposure_spinbox.setDecimals(1)
        self.exposure_spinbox.setSingleStep(1.0)
        self.exposure_spinbox.setValue(5.0)
        self.exposure_spinbox.setToolTip(
            "Camera exposure time.\n"
            "Filled in after a calibration; change it here to override.\n"
            "Applying also writes it to the ImSwitch setup file."
        )
        self.exposure_spinbox.setMinimumWidth(100)
        exposure_layout.addWidget(self.exposure_spinbox)

        self.apply_exposure_button = QPushButton("Apply")
        self.apply_exposure_button.setToolTip("Set this exposure on the camera")
        self.apply_exposure_button.clicked.connect(
            lambda: self.exposure_changed.emit(self.exposure_spinbox.value())
        )
        exposure_layout.addWidget(self.apply_exposure_button)
        exposure_layout.addStretch()

        calib_layout.addLayout(exposure_layout)

        # Tolerance Input
        tolerance_layout = QHBoxLayout()
        tolerance_layout.addWidget(QLabel("Tolerance (%):"))

        self.tolerance_spinbox = QDoubleSpinBox()
        self.tolerance_spinbox.setRange(0.1, 10.0)
        self.tolerance_spinbox.setValue(1.0)
        self.tolerance_spinbox.setDecimals(1)
        self.tolerance_spinbox.setSingleStep(0.5)
        self.tolerance_spinbox.setToolTip(
            "Acceptable error percentage from target.\n"
            "Lower = stricter matching (takes longer).\n"
            "1.0% = excellent matching (ensures <2% phase difference)\n"
            "2.5% = good matching (ensures <5% phase difference)"
        )
        self.tolerance_spinbox.setMinimumWidth(100)
        tolerance_layout.addWidget(self.tolerance_spinbox)
        tolerance_layout.addStretch()

        calib_layout.addLayout(tolerance_layout)

        # Calibration Options
        calib_options_layout = QHBoxLayout()

        self.use_full_frame_checkbox = QCheckBox("Use full frame for calibration")
        self.use_full_frame_checkbox.setChecked(True)  # Default: use full frame
        self.use_full_frame_checkbox.setToolTip(
            "If checked, measures intensity over entire frame.\n"
            "If unchecked, uses center 75% x 75% ROI (avoids edge artifacts)."
        )
        self.use_full_frame_checkbox.setStyleSheet("font-size: 11px;")
        calib_options_layout.addWidget(self.use_full_frame_checkbox)

        self.auto_exposure_checkbox = QCheckBox("Also find exposure time")
        self.auto_exposure_checkbox.setChecked(False)
        self.auto_exposure_checkbox.setToolTip(
            "Calibrates the LED power at several exposure times and keeps the one\n"
            "that uses the sensor range best without saturating pixels.\n"
            "The chosen time is applied and written to the setup file, so it also\n"
            "holds after a restart. Takes noticeably longer than a single run."
        )
        self.auto_exposure_checkbox.setStyleSheet("font-size: 11px;")
        calib_options_layout.addWidget(self.auto_exposure_checkbox)
        calib_options_layout.addStretch()

        calib_layout.addLayout(calib_options_layout)

        # Calibration Buttons
        calib_button_layout = QHBoxLayout()

        self.calib_ir_button = QPushButton("Calibrate IR")
        self.calib_ir_button.clicked.connect(lambda: self._on_calibration_clicked("ir"))
        calib_button_layout.addWidget(self.calib_ir_button)

        self.calib_white_button = QPushButton("Calibrate White")
        self.calib_white_button.clicked.connect(lambda: self._on_calibration_clicked("white"))
        calib_button_layout.addWidget(self.calib_white_button)

        self.calib_dual_button = QPushButton("Calibrate Dual")
        self.calib_dual_button.clicked.connect(lambda: self._on_calibration_clicked("dual"))
        calib_button_layout.addWidget(self.calib_dual_button)

        calib_layout.addLayout(calib_button_layout)

        # Calibration Results
        self.calib_results = QTextEdit()
        self.calib_results.setMaximumHeight(100)
        self.calib_results.setReadOnly(True)
        self.calib_results.setPlaceholderText("Calibration results will appear here...")
        calib_layout.addWidget(self.calib_results)

        calib_group.setLayout(calib_layout)
        layout.addWidget(calib_group)

        # Current Status Group
        status_group = QGroupBox("Current LED Status")
        status_layout = QFormLayout()

        self.status_led_label = QLabel("OFF")
        self.status_led_label.setStyleSheet("font-weight: bold; color: #e74c3c;")
        status_layout.addRow("LED State:", self.status_led_label)

        self.status_type_label = QLabel("N/A")
        status_layout.addRow("Active Type:", self.status_type_label)

        self.status_power_label = QLabel("N/A")
        status_layout.addRow("Current Power:", self.status_power_label)

        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        layout.addStretch()

    def _on_led_on_clicked(self):
        """LED ON Button geklickt"""
        led_type_map = {0: "ir", 1: "white", 2: "dual"}
        led_type = led_type_map.get(self.led_type_combo.currentIndex(), "ir")
        self.led_on_requested.emit(led_type)

    def _on_led_off_clicked(self):
        """LED OFF Button geklickt"""
        # Get currently selected LED type
        led_type_map = {0: "ir", 1: "white"}
        led_type = led_type_map.get(self.led_type_combo.currentIndex(), "ir")
        self.led_off_requested.emit(led_type)

    def _on_power_changed(self, led_type: str, power: int):
        """LED Power wurde geändert"""
        # Signal wird mit Delay emitted (nur bei Release des Sliders)
        # Um Spam zu vermeiden
        self.led_power_changed.emit(led_type, power)

    def _on_calibration_clicked(self, mode: str):
        """Calibration Button geklickt"""
        self.calib_results.append(f"\n🔄 Starting {mode.upper()} calibration...")
        self.calibration_requested.emit(mode)

    # ========================================================================
    # PUBLIC METHODS
    # ========================================================================

    def update_status(self, status: dict):
        """Update LED Status Display"""
        led_on = status.get("led_on", False)
        led_type = status.get("led_type", "N/A")
        power = status.get("power", 0)

        if led_on:
            self.status_led_label.setText("ON")
            self.status_led_label.setStyleSheet("font-weight: bold; color: #27ae60;")
            self.status_type_label.setText(led_type.upper())
            self.status_power_label.setText(f"{power}%")
        else:
            self.status_led_label.setText("OFF")
            self.status_led_label.setStyleSheet("font-weight: bold; color: #e74c3c;")
            self.status_type_label.setText("N/A")
            self.status_power_label.setText("N/A")

    def add_calibration_result(self, message: str):
        """Fügt Kalibrierungs-Ergebnis hinzu"""
        self.calib_results.append(message)

    def clear_calibration_results(self):
        """Löscht Kalibrierungs-Ergebnisse"""
        self.calib_results.clear()

    def get_led_powers(self) -> dict:
        """Gibt aktuelle LED-Power Werte zurück"""
        return {"ir": self.ir_power_slider.value(), "white": self.white_power_slider.value()}

    def set_led_powers(self, powers: dict):
        """Setzt LED-Power Werte"""
        if "ir" in powers:
            self.ir_power_slider.setValue(powers["ir"])
        if "white" in powers:
            self.white_power_slider.setValue(powers["white"])

    def get_use_full_frame(self) -> bool:
        """Gibt zurück ob Full Frame für Kalibrierung verwendet werden soll"""
        return self.use_full_frame_checkbox.isChecked()

    def get_saturation_headroom_percent(self) -> float:
        """How far below the sensor limit the brightest pixels should stay."""
        return self.saturation_spinbox.value()

    def get_exposure_ms(self) -> float:
        """Exposure currently shown in the panel."""
        return self.exposure_spinbox.value()

    def set_exposure_ms(self, exposure_ms: float):
        """
        Show an exposure without triggering the apply signal.

        Used after a calibration to display what the camera ended up with;
        emitting here would set the value the panel just received.
        """
        blocked = self.exposure_spinbox.blockSignals(True)
        self.exposure_spinbox.setValue(float(exposure_ms))
        self.exposure_spinbox.blockSignals(blocked)

    def get_auto_exposure(self) -> bool:
        """Whether calibration should search the exposure time as well."""
        return self.auto_exposure_checkbox.isChecked()

    def get_target_intensity(self) -> float:
        """Returns the target intensity value for calibration"""
        return self.target_intensity_spinbox.value()

    def get_tolerance_percent(self) -> float:
        """Returns the tolerance percentage for calibration"""
        return self.tolerance_spinbox.value()
