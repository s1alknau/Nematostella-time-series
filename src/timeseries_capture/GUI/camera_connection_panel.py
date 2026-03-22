"""
Camera Connection Panel — standalone camera selector via harvesters / GenTL.

Shows in the GUI when no ImSwitch camera_manager is provided.
Lets the user pick a .cti producer file, enumerate cameras, and connect.
No vendor-specific SDK installation is required — any GenTL producer works.
"""

from __future__ import annotations

import logging

from qtpy.QtCore import Signal as pyqtSignal
from qtpy.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..camera_adapters import (
    HARVESTERS_AVAILABLE,
    HarvestersCameraAdapter,
    find_cti_files,
)

logger = logging.getLogger(__name__)


class CameraConnectionPanel(QWidget):
    """
    Standalone camera connection panel using harvesters + any GenTL producer.

    Signals:
        camera_connected(HarvestersCameraAdapter): emitted when a camera is opened
        camera_disconnected(): emitted when the camera is closed
    """

    camera_connected = pyqtSignal(object)  # HarvestersCameraAdapter
    camera_disconnected = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._adapter: HarvestersCameraAdapter | None = None
        self._harvester = None  # harvesters.core.Harvester instance
        self._cti_loaded: str | None = None
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        group = QGroupBox("Camera Connection (GenTL / harvesters)")
        inner = QVBoxLayout()

        if not HARVESTERS_AVAILABLE:
            lbl = QLabel(
                "harvesters library not found.\n"
                "Install it with:  pip install harvesters\n\n"
                "You also need a GenTL producer (.cti file).\n"
                "Free options: Daheng Imaging Galaxy SDK, MVS (Hikrobotics),\n"
                "Allied Vision Vimba, Baumer GAPI."
            )
            lbl.setStyleSheet("color: #e74c3c;")
            lbl.setWordWrap(True)
            inner.addWidget(lbl)
            group.setLayout(inner)
            layout.addWidget(group)
            return

        # ---- CTI file row ----
        cti_form = QFormLayout()
        cti_row = QHBoxLayout()
        self._cti_combo = QComboBox()
        self._cti_combo.setMinimumWidth(260)
        self._cti_combo.setToolTip("Select a GenTL producer (.cti file)")
        cti_row.addWidget(self._cti_combo, stretch=1)

        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(72)
        browse_btn.clicked.connect(self._on_browse_cti)
        cti_row.addWidget(browse_btn)
        cti_form.addRow("CTI producer:", cti_row)
        inner.addLayout(cti_form)

        # Auto-populate detected CTI files
        detected = find_cti_files()
        for p in detected:
            self._cti_combo.addItem(str(p))
        if not detected:
            self._cti_combo.setPlaceholderText("— no .cti files found, use Browse —")

        # ---- Scan row ----
        scan_row = QHBoxLayout()
        self._scan_btn = QPushButton("🔍 Scan for cameras")
        self._scan_btn.clicked.connect(self._on_scan)
        scan_row.addWidget(self._scan_btn)
        self._status_label = QLabel("Not connected")
        self._status_label.setStyleSheet("color: #8b949e;")
        scan_row.addWidget(self._status_label, stretch=1)
        inner.addLayout(scan_row)

        # ---- Camera dropdown ----
        self._camera_combo = QComboBox()
        self._camera_combo.setPlaceholderText("— click Scan —")
        inner.addWidget(self._camera_combo)

        # ---- Exposure ----
        form = QFormLayout()
        self._exposure_spin = QDoubleSpinBox()
        self._exposure_spin.setRange(0.01, 10000.0)
        self._exposure_spin.setValue(10.0)
        self._exposure_spin.setDecimals(2)
        self._exposure_spin.setSuffix(" ms")
        self._exposure_spin.setToolTip("Applied after connecting")
        form.addRow("Exposure:", self._exposure_spin)
        inner.addLayout(form)

        # ---- Connect / Disconnect ----
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
    # Helpers
    # ------------------------------------------------------------------

    def _get_harvester(self):
        """Return (or create) a Harvester loaded with the selected CTI file."""
        try:
            from harvesters.core import Harvester  # type: ignore[import-untyped]
        except ImportError:
            return None

        cti_path = self._cti_combo.currentText().strip()
        if not cti_path:
            return None

        # Reuse if same file already loaded
        if self._harvester is not None and self._cti_loaded == cti_path:
            return self._harvester

        # Release previous
        if self._harvester is not None:
            try:
                self._harvester.reset()
            except Exception:
                pass

        h = Harvester()
        try:
            h.add_file(cti_path)
            h.update()
        except Exception as exc:
            logger.error(f"Failed to load CTI '{cti_path}': {exc}")
            self._status_label.setText(f"CTI load error: {exc}")
            self._status_label.setStyleSheet("color: #e74c3c;")
            return None

        self._harvester = h
        self._cti_loaded = cti_path
        return h

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_browse_cti(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select GenTL producer", "", "CTI files (*.cti);;All files (*)"
        )
        if path:
            # Insert at top if not already present
            if self._cti_combo.findText(path) == -1:
                self._cti_combo.insertItem(0, path)
            self._cti_combo.setCurrentText(path)

    def _on_scan(self):
        self._camera_combo.clear()
        self._connect_btn.setEnabled(False)

        h = self._get_harvester()
        if h is None:
            self._status_label.setText("Select a valid .cti file first")
            self._status_label.setStyleSheet("color: #e74c3c;")
            return

        n = len(h.device_info_list)
        if n == 0:
            self._status_label.setText("No cameras found")
            self._status_label.setStyleSheet("color: #e74c3c;")
            return

        for i, info in enumerate(h.device_info_list):
            label = (
                getattr(info, "model", None)
                or getattr(info, "serial_number", None)
                or f"Camera {i}"
            )
            self._camera_combo.addItem(f"[{i}] {label}")

        self._camera_combo.setCurrentIndex(0)
        self._connect_btn.setEnabled(True)
        self._status_label.setText(f"{n} camera(s) found")
        self._status_label.setStyleSheet("color: #2980b9;")

    def _on_connect(self):
        idx = self._camera_combo.currentIndex()
        if idx < 0:
            return

        h = self._get_harvester()
        if h is None:
            return

        if self._adapter is not None:
            self._adapter.close()

        adapter = HarvestersCameraAdapter(h, device_index=idx)
        if not adapter.open():
            self._status_label.setText("Failed to open camera")
            self._status_label.setStyleSheet("color: #e74c3c;")
            return

        adapter.set_exposure_ms(self._exposure_spin.value())
        self._adapter = adapter

        self._connect_btn.setEnabled(False)
        self._disconnect_btn.setEnabled(True)
        self._scan_btn.setEnabled(False)
        self._cti_combo.setEnabled(False)
        self._camera_combo.setEnabled(False)

        label = self._camera_combo.currentText()
        self._status_label.setText(f"Connected: {label}")
        self._status_label.setStyleSheet("color: #27ae60; font-weight: bold;")
        logger.info(f"Camera connected: {label}")
        self.camera_connected.emit(adapter)

    def _on_disconnect(self):
        if self._adapter is not None:
            self._adapter.close()
            self._adapter = None

        self._connect_btn.setEnabled(True)
        self._disconnect_btn.setEnabled(False)
        self._scan_btn.setEnabled(True)
        self._cti_combo.setEnabled(True)
        self._camera_combo.setEnabled(True)
        self._status_label.setText("Disconnected")
        self._status_label.setStyleSheet("color: #8b949e;")
        self.camera_disconnected.emit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_adapter(self) -> HarvestersCameraAdapter | None:
        """Return the currently connected adapter, or None."""
        return self._adapter

    def is_connected(self) -> bool:
        return self._adapter is not None and self._adapter.is_available()

    def closeEvent(self, event):
        self._on_disconnect()
        if self._harvester is not None:
            try:
                self._harvester.reset()
            except Exception:
                pass
        super().closeEvent(event)
