"""
Status Panel - Zeigt Hardware- und System-Status
"""

from qtpy.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget


class StatusPanel(QWidget):
    """Status-Bar am unteren Rand des Widgets"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        """Setup UI"""
        # Container mit Rahmen
        self.setStyleSheet(
            """
            QWidget {
                background-color: #34495e;
                color: white;
                border-radius: 5px;
            }
        """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(20)

        # ESP32 Status
        self.esp32_icon = QLabel("📡")
        self.esp32_icon.setStyleSheet("background-color: transparent;")
        layout.addWidget(self.esp32_icon)

        self.esp32_label = QLabel("ESP32: Disconnected")
        self.esp32_label.setStyleSheet("background-color: transparent; font-weight: bold;")
        layout.addWidget(self.esp32_label)

        # Separator
        sep1 = self._create_separator()
        layout.addWidget(sep1)

        # Camera Status
        self.camera_icon = QLabel("📷")
        self.camera_icon.setStyleSheet("background-color: transparent;")
        layout.addWidget(self.camera_icon)

        self.camera_label = QLabel("Camera: N/A")
        self.camera_label.setStyleSheet("background-color: transparent;")
        layout.addWidget(self.camera_label)

        # Separator
        sep2 = self._create_separator()
        layout.addWidget(sep2)

        # LED Status
        self.led_icon = QLabel("💡")
        self.led_icon.setStyleSheet("background-color: transparent;")
        layout.addWidget(self.led_icon)

        self.led_label = QLabel("LED: OFF")
        self.led_label.setStyleSheet("background-color: transparent;")
        layout.addWidget(self.led_label)

        # Separator
        sep3 = self._create_separator()
        layout.addWidget(sep3)

        # Recording Status
        self.rec_icon = QLabel("⚪")
        self.rec_icon.setStyleSheet("background-color: transparent; font-size: 16px;")
        layout.addWidget(self.rec_icon)

        self.rec_label = QLabel("Idle")
        self.rec_label.setStyleSheet("background-color: transparent; font-weight: bold;")
        layout.addWidget(self.rec_label)

        layout.addStretch()

        # Phase Info (wird nur bei Phase-Recording angezeigt)
        self.phase_icon = QLabel("🌓")
        self.phase_icon.setStyleSheet("background-color: transparent;")
        self.phase_icon.setVisible(False)
        layout.addWidget(self.phase_icon)

        self.phase_label = QLabel("")
        self.phase_label.setStyleSheet("background-color: transparent;")
        self.phase_label.setVisible(False)
        layout.addWidget(self.phase_label)

    def _create_separator(self) -> QFrame:
        """Erstellt einen vertikalen Separator"""
        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("background-color: #7f8c8d;")
        return line

    # ========================================================================
    # PUBLIC METHODS - Update-Methoden
    # ========================================================================

    def update_hardware_status(self, hw_status: dict):
        """Update Hardware-Status"""
        # ESP32
        esp32_connected = hw_status.get("esp32_connected", False)
        if esp32_connected:
            self.esp32_label.setText("ESP32: Connected")
            self.esp32_label.setStyleSheet(
                "background-color: transparent; font-weight: bold; color: #2ecc71;"
            )
        else:
            self.esp32_label.setText("ESP32: Disconnected")
            self.esp32_label.setStyleSheet(
                "background-color: transparent; font-weight: bold; color: #e74c3c;"
            )

        # Camera
        camera_available = hw_status.get("camera_available", False)
        if camera_available:
            camera_name = hw_status.get("camera_name", "Unknown")
            self.camera_label.setText(f"Camera: {camera_name}")
            self.camera_label.setStyleSheet("background-color: transparent; color: #2ecc71;")
        else:
            self.camera_label.setText("Camera: Not Available")
            self.camera_label.setStyleSheet("background-color: transparent; color: #e74c3c;")

    def update_led_status(self, led_status: dict):
        """Update LED-Status"""
        led_on = led_status.get("led_on", False)
        led_type = led_status.get("led_type", "N/A")
        power = led_status.get("power", 0)

        if led_on:
            self.led_label.setText(f"LED: {led_type.upper()} ON ({power}%)")
            self.led_label.setStyleSheet(
                "background-color: transparent; color: #f39c12; font-weight: bold;"
            )
        else:
            self.led_label.setText("LED: OFF")
            self.led_label.setStyleSheet("background-color: transparent; color: #95a5a6;")

    def update_recording_status(self, rec_status: dict):
        """Update Recording-Status"""
        recording = rec_status.get("recording", False)
        paused = rec_status.get("paused", False)
        current_frame = rec_status.get("current_frame", 0)
        total_frames = rec_status.get("total_frames", 0)

        if recording:
            if paused:
                self.rec_icon.setText("⏸️")
                self.rec_label.setText("Paused")
                self.rec_label.setStyleSheet(
                    "background-color: transparent; font-weight: bold; color: #f39c12;"
                )
            else:
                self.rec_icon.setText("🔴")
                self.rec_label.setText(f"Recording: {current_frame}/{total_frames}")
                self.rec_label.setStyleSheet(
                    "background-color: transparent; font-weight: bold; color: #e74c3c;"
                )
        else:
            self.rec_icon.setText("⚪")
            self.rec_label.setText("Idle")
            self.rec_label.setStyleSheet(
                "background-color: transparent; font-weight: bold; color: #95a5a6;"
            )

    def update_phase_info(self, phase_info: dict):
        """Update Phase-Information"""
        if not phase_info:
            self.phase_icon.setVisible(False)
            self.phase_label.setVisible(False)
            return

        phase = phase_info.get("phase", "N/A")
        cycle = phase_info.get("cycle_number", 0)
        total_cycles = phase_info.get("total_cycles", 0)
        remaining = phase_info.get("phase_remaining_min", 0)

        self.phase_icon.setVisible(True)
        self.phase_label.setVisible(True)

        phase_text = (
            f"Phase: {phase.upper()} | Cycle {cycle}/{total_cycles} | {remaining:.0f}min left"
        )
        self.phase_label.setText(phase_text)

        # Färbe nach Phase
        if phase == "light":
            self.phase_label.setStyleSheet(
                "background-color: transparent; color: #f39c12; font-weight: bold;"
            )
        elif phase == "dark":
            self.phase_label.setStyleSheet(
                "background-color: transparent; color: #95a5a6; font-weight: bold;"
            )
        else:
            self.phase_label.setStyleSheet(
                "background-color: transparent; color: white; font-weight: bold;"
            )
