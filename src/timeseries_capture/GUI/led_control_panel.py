"""
LED Control Panel - UI für LED-Steuerung und Kalibrierung
"""

from qtpy.QtCore import Qt
from qtpy.QtCore import Signal as pyqtSignal
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
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
        ir_layout = QHBoxLayout()
        self.ir_power_slider = QSlider(Qt.Horizontal)
        self.ir_power_slider.setRange(0, 100)
        self.ir_power_slider.setValue(100)
        self.ir_power_slider.valueChanged.connect(lambda v: self._on_power_changed("ir", v))
        ir_layout.addWidget(self.ir_power_slider)

        self.ir_power_label = QLabel("100%")
        self.ir_power_label.setMinimumWidth(50)
        self.ir_power_label.setStyleSheet("font-weight: bold;")
        ir_layout.addWidget(self.ir_power_label)

        self.ir_power_slider.valueChanged.connect(lambda v: self.ir_power_label.setText(f"{v}%"))

        power_layout.addRow("IR LED Power:", ir_layout)

        # White LED Power
        white_layout = QHBoxLayout()
        self.white_power_slider = QSlider(Qt.Horizontal)
        self.white_power_slider.setRange(0, 100)
        self.white_power_slider.setValue(50)
        self.white_power_slider.valueChanged.connect(lambda v: self._on_power_changed("white", v))
        white_layout.addWidget(self.white_power_slider)

        self.white_power_label = QLabel("50%")
        self.white_power_label.setMinimumWidth(50)
        self.white_power_label.setStyleSheet("font-weight: bold;")
        white_layout.addWidget(self.white_power_label)

        self.white_power_slider.valueChanged.connect(
            lambda v: self.white_power_label.setText(f"{v}%")
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

        # Calibration Options
        calib_options_layout = QHBoxLayout()

        self.use_full_frame_checkbox = QCheckBox("Use full frame for calibration")
        self.use_full_frame_checkbox.setToolTip(
            "If checked, measures intensity over entire frame.\n"
            "If unchecked, uses center 75% x 75% ROI (avoids edge artifacts)."
        )
        self.use_full_frame_checkbox.setStyleSheet("font-size: 11px;")
        calib_options_layout.addWidget(self.use_full_frame_checkbox)
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
