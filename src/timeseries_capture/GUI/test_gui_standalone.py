"""
Standalone Test für das refactored GUI Widget

Führt das Widget aus OHNE Controller/Hardware.
Zeigt wie die UI aussieht und funktioniert.
"""

import sys
from pathlib import Path

from qtpy.QtCore import QTimer

# Qt imports
from qtpy.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget

# GUI imports (anpassen wenn im echten Package)
try:
    # Versuche relativen Import
    from gui_refactored import NematostellaTimelapseCaptureWidget
except ImportError:
    # Fallback: füge Verzeichnis zum Path hinzu
    gui_path = Path(__file__).parent
    sys.path.insert(0, str(gui_path))


class DemoController:
    """
    Minimaler Mock-Controller um zu zeigen wie Integration aussieht.
    Simuliert Events ohne echte Hardware.
    """

    def __init__(self, widget):
        self.widget = widget
        self.recording = False
        self.current_frame = 0
        self.total_frames = 100
        self.timer = None

    def start_demo_recording(self):
        """Startet Demo-Recording mit simulierten Updates"""
        self.recording = True
        self.current_frame = 0
        self.total_frames = 100

        # Simuliere Recording-Start
        self.widget.add_log_message("🎬 Demo recording started!")
        self.widget.update_hardware_status(
            {"esp32_connected": True, "camera_available": True, "camera_name": "Demo Camera"}
        )

        # Simuliere LED ON
        self.widget.update_led_status({"led_on": True, "led_type": "ir", "power": 100})

        # Start Timer für Progress-Updates
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_progress)
        self.timer.start(100)  # Alle 100ms

    def _update_progress(self):
        """Simuliert Recording-Progress"""
        if self.current_frame >= self.total_frames:
            self._finish_recording()
            return

        self.current_frame += 1

        # Update Status
        status = {
            "recording": True,
            "paused": False,
            "current_frame": self.current_frame,
            "total_frames": self.total_frames,
            "progress_percent": (self.current_frame / self.total_frames) * 100,
            "elapsed_time": self.current_frame * 0.5,  # Simuliere Zeit
        }

        self.widget.update_recording_status(status)

        # Simuliere Phase-Wechsel bei Frame 50
        if self.current_frame == 50:
            self.widget.add_log_message("🌓 Phase transition: DARK -> LIGHT")
            self.widget.update_phase_info(
                {
                    "phase": "light",
                    "cycle_number": 1,
                    "total_cycles": 2,
                    "phase_remaining_min": 15.5,
                }
            )
            self.widget.update_led_status({"led_on": True, "led_type": "white", "power": 50})

    def _finish_recording(self):
        """Beendet Demo-Recording"""
        if self.timer:
            self.timer.stop()

        self.recording = False

        self.widget.add_log_message("✅ Demo recording finished!")
        self.widget.update_recording_status(
            {
                "recording": False,
                "paused": False,
                "current_frame": self.total_frames,
                "total_frames": self.total_frames,
                "progress_percent": 100,
                "elapsed_time": self.total_frames * 0.5,
            }
        )

        self.widget.update_led_status({"led_on": False, "led_type": "N/A", "power": 0})


def main():
    """Main Test-Funktion"""
    app = QApplication(sys.argv)

    # Erstelle Widget
    widget = NematostallTimelapseCaptureWidget()

    # Erstelle Demo-Controller
    demo_controller = DemoController(widget)

    # Erstelle Demo-Control-Window
    demo_window = QWidget()
    demo_layout = QVBoxLayout(demo_window)

    demo_layout.addWidget(QLabel("<b>Demo Controls</b> (simuliert Controller-Funktionalität)"))

    # Demo Buttons
    start_demo_btn = QPushButton("🎬 Start Demo Recording")
    start_demo_btn.clicked.connect(demo_controller.start_demo_recording)
    demo_layout.addWidget(start_demo_btn)

    connect_hw_btn = QPushButton("🔌 Simulate Hardware Connected")
    connect_hw_btn.clicked.connect(
        lambda: widget.update_hardware_status(
            {"esp32_connected": True, "camera_available": True, "camera_name": "HikCamera"}
        )
    )
    demo_layout.addWidget(connect_hw_btn)

    disconnect_hw_btn = QPushButton("❌ Simulate Hardware Disconnected")
    disconnect_hw_btn.clicked.connect(
        lambda: widget.update_hardware_status({"esp32_connected": False, "camera_available": False})
    )
    demo_layout.addWidget(disconnect_hw_btn)

    led_on_btn = QPushButton("💡 Simulate LED ON")
    led_on_btn.clicked.connect(
        lambda: widget.update_led_status({"led_on": True, "led_type": "ir", "power": 100})
    )
    demo_layout.addWidget(led_on_btn)

    led_off_btn = QPushButton("⚫ Simulate LED OFF")
    led_off_btn.clicked.connect(
        lambda: widget.update_led_status({"led_on": False, "led_type": "N/A", "power": 0})
    )
    demo_layout.addWidget(led_off_btn)

    add_log_btn = QPushButton("📝 Add Test Log")
    add_log_btn.clicked.connect(lambda: widget.add_log_message("This is a test log message"))
    demo_layout.addWidget(add_log_btn)

    demo_layout.addStretch()

    # Zeige Windows
    demo_window.setWindowTitle("Demo Controls")
    demo_window.resize(300, 400)
    demo_window.show()
    demo_window.move(50, 50)

    widget.show()
    widget.move(400, 50)

    # Initial Status setzen
    widget.add_log_message("🚀 GUI Test started - use Demo Controls to simulate events")
    widget.update_hardware_status({"esp32_connected": False, "camera_available": False})

    sys.exit(app.exec_())


if __name__ == "__main__":
    print("=" * 80)
    print("GUI STANDALONE TEST")
    print("=" * 80)
    print()
    print("Dieses Script startet das refactored GUI Widget OHNE echte Hardware.")
    print("Nutze das 'Demo Controls' Fenster um Events zu simulieren.")
    print()
    print("Was du testen kannst:")
    print("  ✓ UI Layout und Design")
    print("  ✓ Button-Funktionalität (werden geloggt)")
    print("  ✓ Progress-Updates (via Demo Recording)")
    print("  ✓ Status-Updates (via Demo Controls)")
    print("  ✓ Phase-Wechsel (automatisch bei Frame 50)")
    print()
    print("Hinweis: Buttons im Haupt-Widget emittieren Signals, aber haben")
    print("         noch keine echte Funktionalität (kein Controller verbunden).")
    print()
    print("=" * 80)
    print()

    main()
