"""
ESP32 Connection Panel - UI for ESP32 Connection Control
"""

import serial.tools.list_ports
from qtpy.QtCore import Signal as pyqtSignal
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ESP32ConnectionPanel(QWidget):
    """Panel für ESP32 Verbindungs-Steuerung"""

    # Signals
    connect_requested = pyqtSignal(str)  # port (or None for auto)
    disconnect_requested = pyqtSignal()
    refresh_ports_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_connected = False
        self._setup_ui()
        self._refresh_available_ports()

    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Info Text
        info_label = QLabel(
            "Connect to ESP32 microcontroller for LED control and sensor monitoring. "
            "The port will be auto-detected or you can select manually."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(
            "color: #7f8c8d; padding: 10px; background-color: #ecf0f1; border-radius: 5px;"
        )
        layout.addWidget(info_label)

        # Connection Control Group
        control_group = QGroupBox("ESP32 Connection")
        control_layout = QVBoxLayout()

        # Port Selection
        port_layout = QHBoxLayout()
        port_layout.addWidget(QLabel("Port:"))

        self.port_combo = QComboBox()
        self.port_combo.addItem("Auto-detect", None)
        self.port_combo.setMinimumWidth(200)
        port_layout.addWidget(self.port_combo)

        self.refresh_button = QPushButton("🔄 Refresh")
        self.refresh_button.setMaximumWidth(100)
        self.refresh_button.clicked.connect(self._on_refresh_clicked)
        port_layout.addWidget(self.refresh_button)

        port_layout.addStretch()
        control_layout.addLayout(port_layout)

        # Auto-connect checkbox
        self.auto_connect_check = QCheckBox("Auto-connect on startup")
        self.auto_connect_check.setChecked(True)
        self.auto_connect_check.setToolTip(
            "Automatically connect to ESP32 when the application starts"
        )
        control_layout.addWidget(self.auto_connect_check)

        # Connection Buttons
        button_layout = QHBoxLayout()

        self.connect_button = QPushButton("🔌 Connect")
        self.connect_button.setStyleSheet(
            """
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
                padding: 10px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #229954;
            }
            QPushButton:disabled {
                background-color: #95a5a6;
            }
        """
        )
        self.connect_button.clicked.connect(self._on_connect_clicked)
        button_layout.addWidget(self.connect_button)

        self.disconnect_button = QPushButton("⚡ Disconnect")
        self.disconnect_button.setEnabled(False)
        self.disconnect_button.setStyleSheet(
            """
            QPushButton {
                background-color: #e74c3c;
                color: white;
                font-weight: bold;
                padding: 10px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
            QPushButton:disabled {
                background-color: #95a5a6;
            }
        """
        )
        self.disconnect_button.clicked.connect(self._on_disconnect_clicked)
        button_layout.addWidget(self.disconnect_button)

        control_layout.addLayout(button_layout)

        control_group.setLayout(control_layout)
        layout.addWidget(control_group)

        # Connection Status Group
        status_group = QGroupBox("Connection Status")
        status_layout = QFormLayout()

        self.status_label = QLabel("Disconnected")
        self.status_label.setStyleSheet("font-weight: bold; color: #e74c3c; font-size: 14px;")
        status_layout.addRow("Status:", self.status_label)

        self.port_label = QLabel("N/A")
        status_layout.addRow("Active Port:", self.port_label)

        self.baudrate_label = QLabel("115200")
        status_layout.addRow("Baud Rate:", self.baudrate_label)

        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # Hardware Info Group
        hw_group = QGroupBox("Hardware Information")
        hw_layout = QFormLayout()

        self.firmware_label = QLabel("N/A")
        hw_layout.addRow("Firmware:", self.firmware_label)

        self.temp_label = QLabel("N/A")
        hw_layout.addRow("Temperature:", self.temp_label)

        self.humidity_label = QLabel("N/A")
        hw_layout.addRow("Humidity:", self.humidity_label)

        self.uptime_label = QLabel("N/A")
        hw_layout.addRow("Uptime:", self.uptime_label)

        hw_group.setLayout(hw_layout)
        layout.addWidget(hw_group)

        # Connection Tips
        tips_group = QGroupBox("💡 Connection Tips")
        tips_layout = QVBoxLayout()

        tips_text = QLabel(
            "• Make sure ESP32 is plugged in via USB\n"
            "• Use a data cable (not charge-only)\n"
            "• Close Arduino IDE or other serial monitors\n"
            "• On Linux: Add user to 'dialout' group\n"
            "• Try pressing the RESET button on ESP32"
        )
        tips_text.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        tips_layout.addWidget(tips_text)

        tips_group.setLayout(tips_layout)
        layout.addWidget(tips_group)

        layout.addStretch()

    def _refresh_available_ports(self):
        """Refresh list of available serial ports"""
        # Clear existing items (except auto-detect)
        while self.port_combo.count() > 1:
            self.port_combo.removeItem(1)

        # Scan for ports
        try:
            ports = serial.tools.list_ports.comports()

            # ESP32 identifiers for highlighting
            esp32_keywords = ["CP210", "CH340", "CH341", "FTDI", "USB", "UART"]

            for port in ports:
                port_desc = (port.description or "").upper()
                port_hw = (port.hwid or "").upper()

                # Check if likely ESP32
                is_esp32_likely = any(kw in port_desc or kw in port_hw for kw in esp32_keywords)

                # Format display text
                display_text = f"{port.device}"
                if port.description:
                    display_text += f" - {port.description}"

                if is_esp32_likely:
                    display_text = f"⭐ {display_text}"

                self.port_combo.addItem(display_text, port.device)

        except Exception as e:
            print(f"Error scanning ports: {e}")

    def _on_refresh_clicked(self):
        """Refresh button clicked"""
        self._refresh_available_ports()
        self.refresh_ports_requested.emit()

    def _on_connect_clicked(self):
        """Connect button clicked"""
        # Get selected port
        port = self.port_combo.currentData()

        # Disable connect button
        self.connect_button.setEnabled(False)
        self.status_label.setText("Connecting...")
        self.status_label.setStyleSheet("font-weight: bold; color: #f39c12; font-size: 14px;")

        # Emit signal
        self.connect_requested.emit(port)

    def _on_disconnect_clicked(self):
        """Disconnect button clicked"""
        # Disable disconnect button
        self.disconnect_button.setEnabled(False)

        # Emit signal
        self.disconnect_requested.emit()

    # ========================================================================
    # PUBLIC METHODS - Called by controller
    # ========================================================================

    def update_connection_status(self, connected: bool, port: str = None):
        """
        Update connection status display.

        Args:
            connected: True if connected
            port: Active port name (if connected)
        """
        self._is_connected = connected

        if connected:
            self.status_label.setText("✅ Connected")
            self.status_label.setStyleSheet("font-weight: bold; color: #27ae60; font-size: 14px;")
            self.port_label.setText(port or "Unknown")

            self.connect_button.setEnabled(False)
            self.disconnect_button.setEnabled(True)
            self.port_combo.setEnabled(False)

        else:
            self.status_label.setText("❌ Disconnected")
            self.status_label.setStyleSheet("font-weight: bold; color: #e74c3c; font-size: 14px;")
            self.port_label.setText("N/A")

            self.connect_button.setEnabled(True)
            self.disconnect_button.setEnabled(False)
            self.port_combo.setEnabled(True)

            # Reset hardware info
            self.firmware_label.setText("N/A")
            self.temp_label.setText("N/A")
            self.humidity_label.setText("N/A")
            self.uptime_label.setText("N/A")

    def update_hardware_info(self, hw_info: dict):
        """
        Update hardware information display.

        Args:
            hw_info: Dictionary with hardware info
        """
        if "firmware" in hw_info:
            self.firmware_label.setText(hw_info["firmware"])

        if "temperature" in hw_info:
            temp = hw_info["temperature"]
            if temp is not None:
                self.temp_label.setText(f"{temp:.1f} °C")
            else:
                self.temp_label.setText("N/A (sensor error)")

        if "humidity" in hw_info:
            humidity = hw_info["humidity"]
            if humidity is not None:
                self.humidity_label.setText(f"{humidity:.1f} %")
            else:
                self.humidity_label.setText("N/A (sensor error)")

        if "uptime" in hw_info:
            uptime = hw_info["uptime"]
            if uptime is not None and uptime > 0:
                # Format uptime nicely
                hours = int(uptime // 3600)
                minutes = int((uptime % 3600) // 60)
                seconds = int(uptime % 60)
                self.uptime_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
            else:
                self.uptime_label.setText("N/A")

    def set_connection_in_progress(self, in_progress: bool):
        """
        Set connection in progress state (show spinner, disable buttons, etc.)

        Args:
            in_progress: True if connection attempt in progress
        """
        if in_progress:
            self.connect_button.setEnabled(False)
            self.disconnect_button.setEnabled(False)
            self.status_label.setText("⏳ Connecting...")
            self.status_label.setStyleSheet("font-weight: bold; color: #f39c12; font-size: 14px;")
        else:
            # Will be updated by update_connection_status()
            pass

    def get_auto_connect_enabled(self) -> bool:
        """Returns whether auto-connect is enabled"""
        return self.auto_connect_check.isChecked()

    def set_auto_connect_enabled(self, enabled: bool):
        """Sets auto-connect checkbox state"""
        self.auto_connect_check.setChecked(enabled)
