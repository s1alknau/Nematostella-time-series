"""
Camera Connection Panel — standalone HIK camera selector.

Shows in the GUI when no ImSwitch camera_manager is provided.
Lets the user enumerate, select, and connect to a HIK GigE/USB camera
directly via the MVS SDK.
"""

from __future__ import annotations

import logging

from qtpy.QtCore import Signal as pyqtSignal
from qtpy.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..camera_adapters import MVS_SDK_AVAILABLE, HikDirectCameraAdapter, enumerate_hik_cameras

logger = logging.getLogger(__name__)


class CameraConnectionPanel(QWidget):
    """
    Standalone camera connection panel using the HIK MVS SDK directly.

    Signals:
        camera_connected(HikDirectCameraAdapter): emitted when a camera is opened
        camera_disconnected(): emitted when the camera is closed
    """

    camera_connected = pyqtSignal(object)  # HikDirectCameraAdapter
    camera_disconnected = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._adapter: HikDirectCameraAdapter | None = None
        self._cameras: list[dict] = []
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        group = QGroupBox("Camera Connection (HIK MVS SDK)")
        inner = QVBoxLayout()

        if not MVS_SDK_AVAILABLE:
            lbl = QLabel("MVS SDK not found.\n" "Install Hikrobotics MVS software and restart.")
            lbl.setStyleSheet("color: #e74c3c;")
            inner.addWidget(lbl)
            group.setLayout(inner)
            layout.addWidget(group)
            return

        # Scan row
        scan_row = QHBoxLayout()
        self._scan_btn = QPushButton("🔍 Scan for cameras")
        self._scan_btn.clicked.connect(self._on_scan)
        scan_row.addWidget(self._scan_btn)
        self._status_label = QLabel("Not connected")
        self._status_label.setStyleSheet("color: #8b949e;")
        scan_row.addWidget(self._status_label, stretch=1)
        inner.addLayout(scan_row)

        # Camera dropdown
        self._camera_combo = QComboBox()
        self._camera_combo.setPlaceholderText("— click Scan —")
        inner.addWidget(self._camera_combo)

        # Exposure
        form = QFormLayout()
        self._exposure_spin = QDoubleSpinBox()
        self._exposure_spin.setRange(0.01, 10000.0)
        self._exposure_spin.setValue(10.0)
        self._exposure_spin.setDecimals(2)
        self._exposure_spin.setSuffix(" ms")
        self._exposure_spin.setToolTip("Applied after connecting")
        form.addRow("Exposure:", self._exposure_spin)
        inner.addLayout(form)

        # Connect / Disconnect buttons
        btn_row = QHBoxLayout()
        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setEnabled(False)
        self._connect_btn.setStyleSheet(
            "background-color: #238636; color: white; font-weight: bold;"
        )
        self._connect_btn.clicked.connect(self._on_connect)
        btn_row.addWidget(self._connect_btn)

        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.setEnabled(False)
        self._disconnect_btn.setStyleSheet("background-color: #b62324; color: white;")
        self._disconnect_btn.clicked.connect(self._on_disconnect)
        btn_row.addWidget(self._disconnect_btn)
        inner.addLayout(btn_row)

        group.setLayout(inner)
        layout.addWidget(group)
        layout.addStretch()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_scan(self):
        self._cameras = enumerate_hik_cameras()
        self._camera_combo.clear()
        if not self._cameras:
            self._status_label.setText("No cameras found")
            self._status_label.setStyleSheet("color: #e74c3c;")
            self._connect_btn.setEnabled(False)
            return
        for cam in self._cameras:
            self._camera_combo.addItem(cam["name"])
        self._camera_combo.setCurrentIndex(0)
        self._connect_btn.setEnabled(True)
        self._status_label.setText(f"{len(self._cameras)} camera(s) found")
        self._status_label.setStyleSheet("color: #2980b9;")

    def _on_connect(self):
        idx = self._camera_combo.currentIndex()
        if idx < 0 or idx >= len(self._cameras):
            return
        if self._adapter is not None:
            self._adapter.close()

        cam_info = self._cameras[idx]
        adapter = HikDirectCameraAdapter(cam_info)
        if not adapter.open():
            self._status_label.setText("Failed to open camera")
            self._status_label.setStyleSheet("color: #e74c3c;")
            return

        adapter.set_exposure_ms(self._exposure_spin.value())
        self._adapter = adapter
        self._connect_btn.setEnabled(False)
        self._disconnect_btn.setEnabled(True)
        self._scan_btn.setEnabled(False)
        self._camera_combo.setEnabled(False)
        self._status_label.setText(f"Connected: {cam_info['name'].split(']')[1].strip()}")
        self._status_label.setStyleSheet("color: #27ae60; font-weight: bold;")
        logger.info(f"Camera connected: {cam_info['name']}")
        self.camera_connected.emit(adapter)

    def _on_disconnect(self):
        if self._adapter is not None:
            self._adapter.close()
            self._adapter = None
        self._connect_btn.setEnabled(True)
        self._disconnect_btn.setEnabled(False)
        self._scan_btn.setEnabled(True)
        self._camera_combo.setEnabled(True)
        self._status_label.setText("Disconnected")
        self._status_label.setStyleSheet("color: #8b949e;")
        self.camera_disconnected.emit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_adapter(self) -> HikDirectCameraAdapter | None:
        """Return the currently connected adapter, or None."""
        return self._adapter

    def is_connected(self) -> bool:
        return self._adapter is not None and self._adapter.is_available()

    def closeEvent(self, event):
        self._on_disconnect()
        super().closeEvent(event)
