"""
Multi-Camera Status Panel

Displays status of all cameras in multi-camera setup.
"""

import logging

try:
    from qtpy.QtCore import Qt
    from qtpy.QtWidgets import (
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QScrollArea,
        QVBoxLayout,
        QWidget,
    )
except Exception:
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import (
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QScrollArea,
        QVBoxLayout,
        QWidget,
    )

logger = logging.getLogger(__name__)


class CameraStatusWidget(QWidget):
    """Single camera status widget"""

    def __init__(self, camera_id: str, camera_name: str, parent=None):
        super().__init__(parent)

        self.camera_id = camera_id
        self.camera_name = camera_name

        self._setup_ui()

    def _setup_ui(self):
        """Setup UI"""
        layout = QHBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)

        # Camera name
        name_label = QLabel(f"<b>{self.camera_name}</b>")
        name_label.setMinimumWidth(150)
        layout.addWidget(name_label)

        # Status indicator
        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet("color: gray; font-size: 16px;")
        layout.addWidget(self.status_indicator)

        # Status text
        self.status_label = QLabel("Idle")
        self.status_label.setMinimumWidth(80)
        layout.addWidget(self.status_label)

        # Progress info
        self.progress_label = QLabel("")
        self.progress_label.setMinimumWidth(150)
        layout.addWidget(self.progress_label)

        layout.addStretch()

        self.setLayout(layout)

    def update_status(self, status: dict):
        """
        Update camera status

        Args:
            status: Status dict with keys:
                - connected: bool
                - recording: bool
                - status: str
                - statistics: dict (optional)
        """
        # Update connection indicator
        if not status.get("connected", False):
            self.status_indicator.setStyleSheet("color: red; font-size: 16px;")
            self.status_label.setText("Disconnected")
            self.progress_label.setText("")
            return

        # Update recording status
        if status.get("recording", False):
            self.status_indicator.setStyleSheet("color: green; font-size: 16px;")
            self.status_label.setText("Recording")

            # Show progress
            stats = status.get("statistics", {})
            if stats:
                progress = stats.get("progress_percent", 0)
                frames = stats.get("captured_frames", 0)
                total = stats.get("total_frames", 0)

                self.progress_label.setText(
                    f"{progress:.1f}% ({frames}/{total} frames)"
                )
        else:
            self.status_indicator.setStyleSheet("color: yellow; font-size: 16px;")
            self.status_label.setText("Connected")
            self.progress_label.setText("")


class MultiCameraStatusPanel(QWidget):
    """
    Multi-Camera Status Panel

    Shows status of all cameras in a scrollable list.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # Camera status widgets
        self.camera_widgets = {}

        self._setup_ui()

    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout()

        # Status group
        status_group = QGroupBox("Camera Status")
        status_layout = QVBoxLayout()

        # Summary
        self.summary_label = QLabel("No cameras configured")
        self.summary_label.setStyleSheet("font-weight: bold; color: gray;")
        status_layout.addWidget(self.summary_label)

        # Scroll area for camera list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(150)
        scroll.setMaximumHeight(300)

        # Container for camera widgets
        self.camera_container = QWidget()
        self.camera_layout = QVBoxLayout()
        self.camera_layout.setSpacing(2)
        self.camera_container.setLayout(self.camera_layout)

        scroll.setWidget(self.camera_container)
        status_layout.addWidget(scroll)

        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        self.setLayout(layout)

    def set_cameras(self, camera_configs: list):
        """
        Initialize camera status widgets

        Args:
            camera_configs: List of camera config dicts
        """
        # Clear existing widgets
        for widget in self.camera_widgets.values():
            widget.deleteLater()
        self.camera_widgets.clear()

        # Create widgets for each camera
        for cam in camera_configs:
            if cam.get("enabled", True):
                widget = CameraStatusWidget(cam["id"], cam["name"])
                self.camera_widgets[cam["id"]] = widget
                self.camera_layout.addWidget(widget)

        # Add stretch at bottom
        self.camera_layout.addStretch()

        # Update summary
        num_cameras = len(self.camera_widgets)
        self.summary_label.setText(
            f"{num_cameras} camera{'s' if num_cameras != 1 else ''} configured"
        )

        logger.info(f"MultiCameraStatusPanel: {num_cameras} cameras configured")

    def update_all_status(self, status_dict: dict):
        """
        Update status for all cameras

        Args:
            status_dict: Dict mapping camera_id to status dict
        """
        recording_count = 0
        connected_count = 0

        for cam_id, status in status_dict.items():
            if cam_id in self.camera_widgets:
                self.camera_widgets[cam_id].update_status(status)

                if status.get("connected", False):
                    connected_count += 1
                if status.get("recording", False):
                    recording_count += 1

        # Update summary
        total = len(self.camera_widgets)
        summary_parts = []

        if recording_count > 0:
            summary_parts.append(f"{recording_count}/{total} recording")

        summary_parts.append(f"{connected_count}/{total} connected")

        self.summary_label.setText(" | ".join(summary_parts))

    def clear(self):
        """Clear all status widgets"""
        for widget in self.camera_widgets.values():
            widget.deleteLater()
        self.camera_widgets.clear()

        self.summary_label.setText("No cameras configured")


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    import sys
    import time

    try:
        from PyQt5.QtCore import QTimer
        from PyQt5.QtWidgets import QApplication
    except Exception:
        from qtpy.QtCore import QTimer
        from qtpy.QtWidgets import QApplication

    app = QApplication(sys.argv)

    # Create panel
    panel = MultiCameraStatusPanel()

    # Add test cameras
    test_cameras = [
        {"id": "cam1", "name": "Camera 1 - Position A", "enabled": True},
        {"id": "cam2", "name": "Camera 2 - Position B", "enabled": True},
        {"id": "cam3", "name": "Camera 3 - Position C", "enabled": True},
        {"id": "cam4", "name": "Camera 4 - Position D", "enabled": True},
    ]

    panel.set_cameras(test_cameras)

    # Simulate status updates
    def update_test_status():
        test_status = {
            "cam1": {
                "connected": True,
                "recording": True,
                "status": "RECORDING",
                "statistics": {
                    "progress_percent": 45.5,
                    "captured_frames": 100,
                    "total_frames": 220,
                },
            },
            "cam2": {
                "connected": True,
                "recording": True,
                "status": "RECORDING",
                "statistics": {
                    "progress_percent": 43.2,
                    "captured_frames": 95,
                    "total_frames": 220,
                },
            },
            "cam3": {
                "connected": True,
                "recording": False,
                "status": "IDLE",
            },
            "cam4": {
                "connected": False,
                "recording": False,
                "status": "DISCONNECTED",
            },
        }

        panel.update_all_status(test_status)

    # Update every second
    timer = QTimer()
    timer.timeout.connect(update_test_status)
    timer.start(1000)

    panel.show()
    sys.exit(app.exec_())
