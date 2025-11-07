"""
Phase Configuration Panel - UI für Day/Night Phasen
"""

from qtpy.QtCore import Signal as pyqtSignal
from qtpy.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class PhaseConfigPanel(QWidget):
    """Panel für Phase-Konfiguration"""

    # Signal wenn sich Config ändert
    config_changed = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Info Text
        info_label = QLabel(
            "Configure day/night cycle phases for your recording. "
            "The system will automatically switch between light and dark phases."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(
            "color: #7f8c8d; padding: 10px; background-color: #ecf0f1; border-radius: 5px;"
        )
        layout.addWidget(info_label)

        # Phase Enable Group
        enable_group = QGroupBox("Phase Recording")
        enable_layout = QVBoxLayout()

        self.phase_enabled_check = QCheckBox("Enable Day/Night Phase Recording")
        self.phase_enabled_check.setStyleSheet("font-weight: bold;")
        self.phase_enabled_check.setChecked(False)
        self.phase_enabled_check.toggled.connect(self._on_phase_enabled_changed)
        self.phase_enabled_check.toggled.connect(self._emit_config_changed)
        enable_layout.addWidget(self.phase_enabled_check)

        enable_group.setLayout(enable_layout)
        layout.addWidget(enable_group)

        # Phase Duration Group
        self.duration_group = QGroupBox("Phase Durations")
        duration_layout = QFormLayout()

        # Light Duration
        self.light_duration_spin = QSpinBox()
        self.light_duration_spin.setRange(1, 1000)
        self.light_duration_spin.setValue(30)
        self.light_duration_spin.setSuffix(" min")
        self.light_duration_spin.valueChanged.connect(self._emit_config_changed)
        duration_layout.addRow("Light Phase Duration:", self.light_duration_spin)

        # Dark Duration
        self.dark_duration_spin = QSpinBox()
        self.dark_duration_spin.setRange(1, 1000)
        self.dark_duration_spin.setValue(30)
        self.dark_duration_spin.setSuffix(" min")
        self.dark_duration_spin.valueChanged.connect(self._emit_config_changed)
        duration_layout.addRow("Dark Phase Duration:", self.dark_duration_spin)

        # Calculated Cycle Info
        self.cycle_info_label = QLabel()
        self.cycle_info_label.setStyleSheet("color: #7f8c8d;")
        self._update_cycle_info()
        self.light_duration_spin.valueChanged.connect(self._update_cycle_info)
        self.dark_duration_spin.valueChanged.connect(self._update_cycle_info)
        duration_layout.addRow("Full Cycle:", self.cycle_info_label)

        self.duration_group.setLayout(duration_layout)
        self.duration_group.setEnabled(False)
        layout.addWidget(self.duration_group)

        # Starting Phase Group
        self.starting_group = QGroupBox("Starting Phase")
        starting_layout = QVBoxLayout()

        self.phase_button_group = QButtonGroup(self)

        self.start_light_radio = QRadioButton("Start with Light Phase (White LED)")
        self.start_light_radio.setChecked(True)
        self.start_light_radio.toggled.connect(self._emit_config_changed)
        self.phase_button_group.addButton(self.start_light_radio)
        starting_layout.addWidget(self.start_light_radio)

        self.start_dark_radio = QRadioButton("Start with Dark Phase (IR LED)")
        self.start_dark_radio.toggled.connect(self._emit_config_changed)
        self.phase_button_group.addButton(self.start_dark_radio)
        starting_layout.addWidget(self.start_dark_radio)

        self.starting_group.setLayout(starting_layout)
        self.starting_group.setEnabled(False)
        layout.addWidget(self.starting_group)

        # LED Configuration Group
        self.led_config_group = QGroupBox("LED Configuration")
        led_layout = QVBoxLayout()

        self.dual_light_check = QCheckBox("Use Dual LED mode in Light Phase (IR + White)")
        self.dual_light_check.setChecked(False)
        self.dual_light_check.setToolTip(
            "When enabled, both IR and White LEDs will be active during light phase"
        )
        self.dual_light_check.toggled.connect(self._emit_config_changed)
        led_layout.addWidget(self.dual_light_check)

        # Camera Trigger Latency
        latency_layout = QHBoxLayout()
        latency_layout.addWidget(QLabel("Camera Trigger Latency:"))

        self.latency_spin = QSpinBox()
        self.latency_spin.setRange(0, 200)
        self.latency_spin.setValue(20)
        self.latency_spin.setSuffix(" ms")
        self.latency_spin.setToolTip(
            "Compensates for camera trigger delay. "
            "Increase if frames appear dark (captured before LED stabilizes)"
        )
        self.latency_spin.valueChanged.connect(self._emit_config_changed)
        latency_layout.addWidget(self.latency_spin)
        latency_layout.addStretch()

        led_layout.addLayout(latency_layout)

        self.led_config_group.setLayout(led_layout)
        self.led_config_group.setEnabled(False)
        layout.addWidget(self.led_config_group)

        # Phase Preview Group
        self.preview_group = QGroupBox("Phase Preview")
        preview_layout = QVBoxLayout()

        self.preview_label = QLabel()
        self.preview_label.setWordWrap(True)
        self._update_preview()
        preview_layout.addWidget(self.preview_label)

        self.preview_group.setLayout(preview_layout)
        self.preview_group.setEnabled(False)
        layout.addWidget(self.preview_group)

        # Connect preview updates
        self.phase_enabled_check.toggled.connect(self._update_preview)
        self.light_duration_spin.valueChanged.connect(self._update_preview)
        self.dark_duration_spin.valueChanged.connect(self._update_preview)
        self.start_light_radio.toggled.connect(self._update_preview)
        self.dual_light_check.toggled.connect(self._update_preview)

        layout.addStretch()

    def _on_phase_enabled_changed(self, enabled: bool):
        """Phase Enable wurde geändert"""
        self.duration_group.setEnabled(enabled)
        self.starting_group.setEnabled(enabled)
        self.led_config_group.setEnabled(enabled)
        self.preview_group.setEnabled(enabled)

    def _update_cycle_info(self):
        """Update Cycle Info Label"""
        light = self.light_duration_spin.value()
        dark = self.dark_duration_spin.value()
        total = light + dark
        self.cycle_info_label.setText(f"{total} minutes ({light} light + {dark} dark)")

    def _update_preview(self):
        """Update Phase Preview"""
        if not self.phase_enabled_check.isChecked():
            self.preview_label.setText("Phase recording is disabled.")
            return

        light_dur = self.light_duration_spin.value()
        dark_dur = self.dark_duration_spin.value()
        starts_light = self.start_light_radio.isChecked()
        dual_mode = self.dual_light_check.isChecked()

        # Build preview text
        preview_parts = []

        if starts_light:
            preview_parts.append(f"1️⃣ LIGHT PHASE ({light_dur} min)")
            if dual_mode:
                preview_parts.append("   💡 White LED + IR LED (Dual Mode)")
            else:
                preview_parts.append("   💡 White LED only")
            preview_parts.append("")
            preview_parts.append(f"2️⃣ DARK PHASE ({dark_dur} min)")
            preview_parts.append("   🌙 IR LED only")
        else:
            preview_parts.append(f"1️⃣ DARK PHASE ({dark_dur} min)")
            preview_parts.append("   🌙 IR LED only")
            preview_parts.append("")
            preview_parts.append(f"2️⃣ LIGHT PHASE ({light_dur} min)")
            if dual_mode:
                preview_parts.append("   💡 White LED + IR LED (Dual Mode)")
            else:
                preview_parts.append("   💡 White LED only")

        preview_parts.append("")
        total = light_dur + dark_dur
        preview_parts.append(f"🔄 Cycle repeats every {total} minutes")

        self.preview_label.setText("\n".join(preview_parts))

    def _emit_config_changed(self):
        """Emit config changed signal"""
        config = self.get_config()
        self.config_changed.emit(config)

    # ========================================================================
    # PUBLIC METHODS
    # ========================================================================

    def get_config(self) -> dict:
        """Gibt aktuelle Phase-Konfiguration zurück"""
        return {
            "enabled": self.phase_enabled_check.isChecked(),
            "light_duration_min": self.light_duration_spin.value(),
            "dark_duration_min": self.dark_duration_spin.value(),
            "start_with_light": self.start_light_radio.isChecked(),
            "dual_light_phase": self.dual_light_check.isChecked(),
            "camera_trigger_latency_ms": self.latency_spin.value(),
        }

    def set_config(self, config: dict):
        """Setzt Phase-Konfiguration"""
        self.phase_enabled_check.setChecked(config.get("enabled", False))
        self.light_duration_spin.setValue(config.get("light_duration_min", 30))
        self.dark_duration_spin.setValue(config.get("dark_duration_min", 30))

        if config.get("start_with_light", True):
            self.start_light_radio.setChecked(True)
        else:
            self.start_dark_radio.setChecked(True)

        self.dual_light_check.setChecked(config.get("dual_light_phase", False))
        self.latency_spin.setValue(config.get("camera_trigger_latency_ms", 20))
