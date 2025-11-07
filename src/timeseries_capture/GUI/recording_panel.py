"""
Recording Control Panel - UI für Recording-Steuerung
"""

from pathlib import Path

from qtpy.QtCore import Signal as pyqtSignal
from qtpy.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class RecordingControlPanel(QWidget):
    """Panel für Recording-Steuerung"""

    # Signals (werden an Main Widget gesendet)
    start_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    pause_requested = pyqtSignal()
    resume_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._recording = False
        self._paused = False
        self._setup_ui()

    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Configuration Group
        config_group = QGroupBox("Recording Configuration")
        config_layout = QFormLayout()

        # Duration
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(1, 10000)
        self.duration_spin.setValue(60)
        self.duration_spin.setSuffix(" min")
        self.duration_spin.setToolTip("Total recording duration in minutes")
        config_layout.addRow("Duration:", self.duration_spin)

        # Interval
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 3600)
        self.interval_spin.setValue(5)
        self.interval_spin.setSuffix(" sec")
        self.interval_spin.setToolTip("Time between frames in seconds")
        config_layout.addRow("Interval:", self.interval_spin)

        # Calculated frames
        self.total_frames_label = QLabel("720 frames")
        self.total_frames_label.setStyleSheet("color: #7f8c8d;")
        config_layout.addRow("Total Frames:", self.total_frames_label)

        # Update frames when duration/interval changes
        self.duration_spin.valueChanged.connect(self._update_frame_count)
        self.interval_spin.valueChanged.connect(self._update_frame_count)
        self._update_frame_count()

        # Experiment Name
        self.experiment_name_edit = QLineEdit()
        self.experiment_name_edit.setText("nematostella_timelapse")
        self.experiment_name_edit.setPlaceholderText("Enter experiment name...")
        config_layout.addRow("Experiment:", self.experiment_name_edit)

        # Output Directory
        dir_layout = QHBoxLayout()
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setText(str(Path.home() / "recordings"))
        self.output_dir_edit.setPlaceholderText("Select output directory...")
        dir_layout.addWidget(self.output_dir_edit)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_output_dir)
        dir_layout.addWidget(browse_btn)

        config_layout.addRow("Output Dir:", dir_layout)

        config_group.setLayout(config_layout)
        layout.addWidget(config_group)

        # Control Buttons Group
        control_group = QGroupBox("Recording Control")
        control_layout = QVBoxLayout()

        # Button Row
        button_layout = QHBoxLayout()

        self.start_button = QPushButton("▶ Start Recording")
        self.start_button.setStyleSheet(
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
        self.start_button.clicked.connect(self._on_start_clicked)
        button_layout.addWidget(self.start_button)

        self.pause_button = QPushButton("⏸ Pause")
        self.pause_button.setEnabled(False)
        self.pause_button.setStyleSheet(
            """
            QPushButton {
                background-color: #f39c12;
                color: white;
                font-weight: bold;
                padding: 10px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #e67e22;
            }
            QPushButton:disabled {
                background-color: #95a5a6;
            }
        """
        )
        self.pause_button.clicked.connect(self._on_pause_clicked)
        button_layout.addWidget(self.pause_button)

        self.stop_button = QPushButton("⏹ Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.setStyleSheet(
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
        self.stop_button.clicked.connect(self._on_stop_clicked)
        button_layout.addWidget(self.stop_button)

        control_layout.addLayout(button_layout)

        # Progress Bar
        progress_layout = QVBoxLayout()
        progress_layout.setSpacing(5)

        self.progress_label = QLabel("Ready to record")
        self.progress_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        progress_layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet(
            """
            QProgressBar {
                border: 2px solid #bdc3c7;
                border-radius: 5px;
                text-align: center;
                height: 25px;
            }
            QProgressBar::chunk {
                background-color: #3498db;
                border-radius: 3px;
            }
        """
        )
        progress_layout.addWidget(self.progress_bar)

        # Stats Row
        stats_layout = QHBoxLayout()

        self.frame_label = QLabel("Frame: 0 / 0")
        self.frame_label.setWordWrap(True)
        stats_layout.addWidget(self.frame_label, 1)

        self.elapsed_label = QLabel("Elapsed: 00:00:00")
        self.elapsed_label.setWordWrap(True)
        stats_layout.addWidget(self.elapsed_label, 1)

        self.remaining_label = QLabel("Remaining: 00:00:00")
        self.remaining_label.setWordWrap(True)
        stats_layout.addWidget(self.remaining_label, 1)

        progress_layout.addLayout(stats_layout)

        control_layout.addLayout(progress_layout)

        control_group.setLayout(control_layout)
        layout.addWidget(control_group)

        # Phase Info Group (wird bei Phasen-Recording angezeigt)
        self.phase_info_group = QGroupBox("Current Phase")
        phase_layout = QFormLayout()

        self.phase_label = QLabel("N/A")
        self.phase_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        self.phase_label.setWordWrap(True)
        phase_layout.addRow("Phase:", self.phase_label)

        self.led_type_label = QLabel("N/A")
        self.led_type_label.setWordWrap(True)
        phase_layout.addRow("LED Type:", self.led_type_label)

        self.cycle_label = QLabel("N/A")
        self.cycle_label.setWordWrap(True)
        phase_layout.addRow("Cycle:", self.cycle_label)

        self.phase_remaining_label = QLabel("N/A")
        self.phase_remaining_label.setWordWrap(True)
        phase_layout.addRow("Phase Remaining:", self.phase_remaining_label)

        self.phase_info_group.setLayout(phase_layout)
        self.phase_info_group.setVisible(False)  # Versteckt bis Recording mit Phasen
        layout.addWidget(self.phase_info_group)

        layout.addStretch()

    def _update_frame_count(self):
        """Update berechnete Frame-Anzahl"""
        duration_min = self.duration_spin.value()
        interval_sec = self.interval_spin.value()
        total_frames = int((duration_min * 60) / interval_sec) + 1
        self.total_frames_label.setText(f"{total_frames} frames")

    def _browse_output_dir(self):
        """Browse für Output-Directory"""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Output Directory", self.output_dir_edit.text()
        )
        if directory:
            self.output_dir_edit.setText(directory)

    def _on_start_clicked(self):
        """Start Button geklickt"""
        self._recording = True
        self._paused = False
        self.start_button.setEnabled(False)
        self.pause_button.setEnabled(True)
        self.stop_button.setEnabled(True)
        self.progress_label.setText("Recording in progress...")
        self.start_requested.emit()

    def _on_pause_clicked(self):
        """Pause/Resume Button geklickt"""
        if self._paused:
            # Resume
            self._paused = False
            self.pause_button.setText("⏸ Pause")
            self.progress_label.setText("Recording in progress...")
            self.resume_requested.emit()
        else:
            # Pause
            self._paused = True
            self.pause_button.setText("▶ Resume")
            self.progress_label.setText("Recording paused")
            self.pause_requested.emit()

    def _on_stop_clicked(self):
        """Stop Button geklickt"""
        self._recording = False
        self._paused = False
        self.start_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.pause_button.setText("⏸ Pause")
        self.progress_label.setText("Recording stopped")
        self.stop_requested.emit()

    # ========================================================================
    # PUBLIC METHODS - Vom Main Widget aufgerufen
    # ========================================================================

    def get_config(self) -> dict:
        """Gibt aktuelle Konfiguration zurück"""
        return {
            "duration_min": self.duration_spin.value(),
            "interval_sec": self.interval_spin.value(),
            "experiment_name": self.experiment_name_edit.text(),
            "output_dir": self.output_dir_edit.text(),
        }

    def update_status(self, status: dict):
        """Update Status-Anzeige"""
        # Progress
        progress = status.get("progress_percent", 0)
        self.progress_bar.setValue(int(progress))

        # Frames
        current = status.get("current_frame", 0)
        total = status.get("total_frames", 0)
        self.frame_label.setText(f"Frame: {current} / {total}")

        # Elapsed Time
        elapsed_sec = status.get("elapsed_time", 0)
        elapsed_str = self._format_time(elapsed_sec)
        self.elapsed_label.setText(f"Elapsed: {elapsed_str}")

        # Remaining Time
        if total > 0 and current > 0:
            avg_time_per_frame = elapsed_sec / current
            remaining_frames = total - current
            remaining_sec = remaining_frames * avg_time_per_frame
            remaining_str = self._format_time(remaining_sec)
            self.remaining_label.setText(f"Remaining: {remaining_str}")

        # Recording State
        recording = status.get("recording", False)
        paused = status.get("paused", False)

        if recording:
            if paused:
                self.progress_label.setText("Recording paused")
                self.pause_button.setText("▶ Resume")
            else:
                self.progress_label.setText("Recording in progress...")
                self.pause_button.setText("⏸ Pause")
        else:
            self.progress_label.setText("Ready to record")
            self._recording = False
            self._paused = False
            self.start_button.setEnabled(True)
            self.pause_button.setEnabled(False)
            self.stop_button.setEnabled(False)

    def update_phase_info(self, phase_info: dict):
        """Update Phase-Information"""
        if not phase_info:
            self.phase_info_group.setVisible(False)
            return

        self.phase_info_group.setVisible(True)

        phase = phase_info.get("phase", "N/A")
        self.phase_label.setText(phase.upper())

        # Färbe nach Phase
        if phase == "light":
            self.phase_label.setStyleSheet("font-weight: bold; color: #f39c12;")
        elif phase == "dark":
            self.phase_label.setStyleSheet("font-weight: bold; color: #34495e;")
        else:
            self.phase_label.setStyleSheet("font-weight: bold; color: #2c3e50;")

        led_type = phase_info.get("led_type", "N/A")
        self.led_type_label.setText(led_type.upper())

        cycle = phase_info.get("cycle_number", 0)
        total_cycles = phase_info.get("total_cycles", 0)
        self.cycle_label.setText(f"{cycle} / {total_cycles}")

        remaining_min = phase_info.get("phase_remaining_min", 0)
        self.phase_remaining_label.setText(f"{remaining_min:.1f} min")

    def is_recording(self) -> bool:
        """Gibt zurück ob gerade aufgenommen wird"""
        return self._recording

    def _format_time(self, seconds: float) -> str:
        """Formatiert Sekunden zu HH:MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
