"""
Camera Selection Panel

GUI panel for selecting active camera in multi-camera setup.
"""

import logging

try:
    from qtpy.QtCore import Signal
    from qtpy.QtWidgets import (
        QComboBox,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
except Exception:
    from PyQt5.QtCore import pyqtSignal as Signal
    from PyQt5.QtWidgets import (
        QComboBox,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

logger = logging.getLogger(__name__)


class CameraSelectionPanel(QWidget):
    """
    Camera Selection Panel

    Allows user to:
    - Select active camera from dropdown
    - Enable/disable multi-camera mode
    - Apply settings to all cameras
    """

    # Signals
    camera_selected = Signal(str)  # camera_id
    apply_to_all_clicked = Signal()
    multi_camera_toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._setup_ui()

    def _setup_ui(self):
        """Setup UI components"""
        layout = QVBoxLayout()

        # Camera Selection Group
        camera_group = QGroupBox("Camera Selection")
        camera_layout = QVBoxLayout()

        # Mode selection
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Mode:"))

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Single Camera", "single")
        self.mode_combo.addItem("Multi-Camera", "multi")
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addStretch()

        camera_layout.addLayout(mode_layout)

        # Camera selection (for multi-camera mode)
        selection_layout = QHBoxLayout()
        selection_layout.addWidget(QLabel("Active Camera:"))

        self.camera_combo = QComboBox()
        self.camera_combo.currentTextChanged.connect(self._on_camera_selected)
        selection_layout.addWidget(self.camera_combo)

        camera_layout.addLayout(selection_layout)

        # Apply to all button
        button_layout = QHBoxLayout()
        self.apply_all_btn = QPushButton("Apply Settings to All Cameras")
        self.apply_all_btn.setEnabled(False)
        self.apply_all_btn.clicked.connect(self._on_apply_all)
        button_layout.addWidget(self.apply_all_btn)

        camera_layout.addLayout(button_layout)

        # Status info
        self.status_label = QLabel("Mode: Single Camera")
        self.status_label.setStyleSheet("color: gray; font-size: 10px;")
        camera_layout.addWidget(self.status_label)

        camera_group.setLayout(camera_layout)
        layout.addWidget(camera_group)

        self.setLayout(layout)

        # Initially disable multi-camera controls
        self.camera_combo.setEnabled(False)

    def set_cameras(self, cameras: list):
        """
        Set available cameras

        Args:
            cameras: List of camera dicts with 'id', 'name', 'enabled'
        """
        self.camera_combo.clear()

        for cam in cameras:
            if cam.get("enabled", True):
                self.camera_combo.addItem(
                    f"{cam['name']} ({cam['id']})",
                    userData=cam["id"],
                )

        # Update status
        num_cameras = len(cameras)
        self.status_label.setText(
            f"Loaded {num_cameras} camera{'s' if num_cameras != 1 else ''}"
        )

        # Enable controls if multiple cameras
        if num_cameras > 1:
            self.camera_combo.setEnabled(True)
            self.apply_all_btn.setEnabled(True)

    def get_selected_camera_id(self) -> str:
        """
        Get currently selected camera ID

        Returns:
            Camera ID string
        """
        return self.camera_combo.currentData()

    def is_multi_camera_mode(self) -> bool:
        """
        Check if multi-camera mode is enabled

        Returns:
            True if multi-camera mode
        """
        return self.mode_combo.currentData() == "multi"

    def set_multi_camera_mode(self, enabled: bool):
        """
        Set multi-camera mode

        Args:
            enabled: True for multi-camera, False for single
        """
        index = 1 if enabled else 0
        self.mode_combo.setCurrentIndex(index)

    def _on_mode_changed(self, index):
        """Handle mode selection change"""
        is_multi = self.mode_combo.currentData() == "multi"

        # Enable/disable camera selection
        self.camera_combo.setEnabled(is_multi)
        self.apply_all_btn.setEnabled(is_multi)

        # Update status
        mode_text = "Multi-Camera" if is_multi else "Single Camera"
        self.status_label.setText(f"Mode: {mode_text}")

        # Emit signal
        self.multi_camera_toggled.emit(is_multi)

        logger.info(f"Camera mode changed: {mode_text}")

    def _on_camera_selected(self, camera_name: str):
        """Handle camera selection change"""
        camera_id = self.get_selected_camera_id()

        if camera_id:
            logger.info(f"Camera selected: {camera_name} ({camera_id})")
            self.camera_selected.emit(camera_id)

    def _on_apply_all(self):
        """Handle apply to all button click"""
        logger.info("Apply to all cameras requested")
        self.apply_to_all_clicked.emit()


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    import sys

    try:
        from PyQt5.QtWidgets import QApplication
    except Exception:
        from qtpy.QtWidgets import QApplication

    app = QApplication(sys.argv)

    # Create panel
    panel = CameraSelectionPanel()

    # Add test cameras
    test_cameras = [
        {"id": "cam1", "name": "Camera 1 - Position A", "enabled": True},
        {"id": "cam2", "name": "Camera 2 - Position B", "enabled": True},
        {"id": "cam3", "name": "Camera 3 - Position C", "enabled": True},
    ]

    panel.set_cameras(test_cameras)

    # Connect signals for testing
    panel.camera_selected.connect(lambda cam_id: print(f"Selected: {cam_id}"))
    panel.apply_to_all_clicked.connect(lambda: print("Apply to all clicked"))
    panel.multi_camera_toggled.connect(lambda enabled: print(f"Multi-camera: {enabled}"))

    panel.show()
    sys.exit(app.exec_())
