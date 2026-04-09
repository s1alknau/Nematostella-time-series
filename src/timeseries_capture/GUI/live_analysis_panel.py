"""
Live Analysis Panel - ROI detection + live activity plot during Zarr recording.

Workflow:
  1. User clicks "Capture Preview Frame" → live frame from camera shown
  2. User adjusts HoughCircles parameters → clicks "Detect ROIs"
  3. Labeled frame with detected circles displayed
  4. User starts recording → activity plot updates every 20s automatically
"""

from __future__ import annotations

import logging

import numpy as np
from qtpy.QtCore import QSettings
from qtpy.QtCore import Signal as pyqtSignal
from qtpy.QtGui import QImage, QPixmap
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

# Optional dependencies
try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure

    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    logger.warning("matplotlib not available. Activity plot disabled.")

try:
    from ..Analysis.roi_detector import CV2_AVAILABLE, RoiDetectionResult, detect_rois_hough

    ROI_DETECTION_AVAILABLE = CV2_AVAILABLE
except ImportError:
    ROI_DETECTION_AVAILABLE = False
    logger.warning("roi_detector not importable.")


class LiveAnalysisPanel(QWidget):
    """
    Tab panel for live ROI detection and activity plotting.

    Signals:
        rois_detected(list): Emitted when ROIs are confirmed; carries list of np.ndarray masks
        capture_frame_requested(): Request a live preview frame from the camera
    """

    rois_detected = pyqtSignal(list)  # list[np.ndarray]
    capture_frame_requested = pyqtSignal()

    _SETTINGS_KEY = "LiveAnalysisPanel/roi_detection"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._masks: list[np.ndarray] = []
        self._result: RoiDetectionResult | None = None
        self._last_results: dict = {}
        self._total_duration_min: float | None = None
        # Phase overlay config
        self._phase_enabled: bool = False
        self._light_duration_min: int = 720
        self._dark_duration_min: int = 720
        self._start_with_light: bool = True
        # Schedule-driven phase overlay (takes priority over manual config)
        self._schedule_segments: list | None = None
        self._setup_ui()
        self._load_settings()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setSpacing(12)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        # ---- ROI Detection Group ----
        roi_group = QGroupBox("ROI Detection (HoughCircles)")
        roi_layout = QVBoxLayout()

        # Parameters
        params_layout = QFormLayout()

        self.min_radius_spin = QSpinBox()
        self.min_radius_spin.setRange(5, 1000)
        self.min_radius_spin.setValue(80)
        self.min_radius_spin.setSuffix(" px")
        params_layout.addRow("Min Radius:", self.min_radius_spin)

        self.max_radius_spin = QSpinBox()
        self.max_radius_spin.setRange(10, 2000)
        self.max_radius_spin.setValue(150)
        self.max_radius_spin.setSuffix(" px")
        params_layout.addRow("Max Radius:", self.max_radius_spin)

        self.min_dist_spin = QSpinBox()
        self.min_dist_spin.setRange(10, 2000)
        self.min_dist_spin.setValue(150)
        self.min_dist_spin.setSuffix(" px")
        params_layout.addRow("Min Distance:", self.min_dist_spin)

        self.dp_spin = QDoubleSpinBox()
        self.dp_spin.setRange(0.1, 5.0)
        self.dp_spin.setValue(0.5)
        self.dp_spin.setSingleStep(0.1)
        self.dp_spin.setDecimals(1)
        self.dp_spin.setToolTip(
            "Inverse ratio of accumulator resolution to image resolution.\n"
            "dp=1 → same resolution; dp=2 → half resolution (faster, less precise)."
        )
        params_layout.addRow("dp Ratio:", self.dp_spin)

        self.param1_spin = QDoubleSpinBox()
        self.param1_spin.setRange(1.0, 500.0)
        self.param1_spin.setValue(50.0)
        self.param1_spin.setDecimals(1)
        self.param1_spin.setToolTip(
            "Upper threshold for the Canny edge detector (param1).\n"
            "Higher = fewer, stronger edges detected before circle fitting."
        )
        params_layout.addRow("param1 (Canny):", self.param1_spin)

        self.param2_spin = QDoubleSpinBox()
        self.param2_spin.setRange(1.0, 200.0)
        self.param2_spin.setValue(30.0)
        self.param2_spin.setDecimals(1)
        self.param2_spin.setToolTip(
            "Accumulator threshold for circle detection (param2).\n"
            "Lower = more circles detected (higher sensitivity)."
        )
        params_layout.addRow("param2 (Threshold):", self.param2_spin)

        roi_layout.addLayout(params_layout)

        # Persist values whenever a spinbox changes
        for w in (
            self.min_radius_spin,
            self.max_radius_spin,
            self.min_dist_spin,
            self.dp_spin,
            self.param1_spin,
            self.param2_spin,
        ):
            w.valueChanged.connect(self._save_settings)

        # Buttons
        btn_row = QHBoxLayout()

        self.capture_btn = QPushButton("📷 Capture Preview Frame")
        self.capture_btn.setToolTip("Grab a live frame from the camera for ROI detection")
        self.capture_btn.clicked.connect(self._on_capture_clicked)
        btn_row.addWidget(self.capture_btn)

        self.detect_btn = QPushButton("🔍 Detect ROIs")
        self.detect_btn.setEnabled(False)
        self.detect_btn.clicked.connect(self._on_detect_clicked)
        btn_row.addWidget(self.detect_btn)

        roi_layout.addLayout(btn_row)

        # Format warning banner (shown when HDF5 is selected)
        self.format_warning_label = QLabel(
            "⚠️  Live analysis requires Zarr format. Switch to 'Zarr (.zarr)' in the Recording tab."
        )
        self.format_warning_label.setStyleSheet(
            "background: #7f3f00; color: #ffcc80; padding: 6px; border-radius: 4px; font-weight: bold;"
        )
        self.format_warning_label.setWordWrap(True)
        self.format_warning_label.setVisible(False)
        roi_layout.addWidget(self.format_warning_label)

        # Status label
        self.roi_status_label = QLabel("No preview frame captured yet.")
        self.roi_status_label.setStyleSheet("color: #7f8c8d;")
        roi_layout.addWidget(self.roi_status_label)

        if not ROI_DETECTION_AVAILABLE:
            self.detect_btn.setEnabled(False)
            self.roi_status_label.setText("opencv-python not installed. ROI detection unavailable.")
            self.roi_status_label.setStyleSheet("color: #e74c3c;")

        # Preview image label
        self.preview_label = QLabel("No image")
        self.preview_label.setMinimumHeight(200)
        self.preview_label.setAlignment(self.preview_label.alignment() | 0x0004)  # Qt.AlignHCenter
        self.preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview_label.setStyleSheet("border: 1px solid #bdc3c7; background: #2c3e50;")
        roi_layout.addWidget(self.preview_label)

        roi_group.setLayout(roi_layout)
        layout.addWidget(roi_group)

        # ---- Activity Plot Group ----
        plot_group = QGroupBox("Live Activity Plot (updates every 20s during recording)")
        plot_layout = QVBoxLayout()

        # ROI selector + ZT toggle row
        selector_row = QHBoxLayout()
        selector_row.addWidget(QLabel("Show:"))
        self.roi_selector = QComboBox()
        self.roi_selector.addItem("All ROIs")
        self.roi_selector.setToolTip("Select which ROI(s) to display in the activity plot")
        self.roi_selector.currentIndexChanged.connect(self._on_roi_selector_changed)
        selector_row.addWidget(self.roi_selector)
        selector_row.addStretch()
        self._zt_checkbox = QCheckBox("ZT axis (hours)")
        self._zt_checkbox.setToolTip(
            "Show Zeitgeber Time on x-axis: ZT 0 = recording start, unit = hours"
        )
        self._zt_checkbox.stateChanged.connect(self._on_plot_option_changed)
        selector_row.addWidget(self._zt_checkbox)
        plot_layout.addLayout(selector_row)

        # Phase overlay controls — config is always automatic (from schedule or phase panel)
        phase_box = QGroupBox("Light/Dark Phase Overlay")
        phase_vlay = QVBoxLayout()
        phase_vlay.setContentsMargins(6, 4, 6, 4)

        phase_top = QHBoxLayout()
        self._phase_chk = QCheckBox("Show phase overlay")
        self._phase_chk.stateChanged.connect(self._on_plot_option_changed)
        phase_top.addWidget(self._phase_chk)
        phase_top.addStretch()
        self._schedule_info_label = QLabel("No recording active")
        self._schedule_info_label.setStyleSheet("color: #7f8c8d; font-size: 10px;")
        phase_top.addWidget(self._schedule_info_label)
        phase_vlay.addLayout(phase_top)

        # Internal storage only — no spinboxes shown to user
        self._light_duration_min: int = 720
        self._dark_duration_min: int = 720
        self._start_with_light: bool = True

        phase_box.setLayout(phase_vlay)
        plot_layout.addWidget(phase_box)

        if MATPLOTLIB_AVAILABLE:
            self._figure = Figure(figsize=(6, 3), tight_layout=True)
            self._canvas = FigureCanvas(self._figure)
            self._canvas.setMinimumHeight(220)
            self._ax = self._figure.add_subplot(111)
            self._ax.set_xlabel("Time (min)")
            self._ax.set_ylabel("Σ|ΔPixel| (norm.)")
            self._ax.set_title("Activity per ROI")
            self._ax.grid(True, alpha=0.3)
            plot_layout.addWidget(self._canvas)
        else:
            no_plot_label = QLabel("matplotlib not installed. Activity plot unavailable.")
            no_plot_label.setStyleSheet("color: #e74c3c;")
            plot_layout.addWidget(no_plot_label)

        self.plot_status_label = QLabel("Waiting for recording to start...")
        self.plot_status_label.setStyleSheet("color: #7f8c8d;")
        plot_layout.addWidget(self.plot_status_label)

        plot_group.setLayout(plot_layout)
        layout.addWidget(plot_group)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _save_settings(self):
        s = QSettings()
        s.beginGroup(self._SETTINGS_KEY)
        s.setValue("min_radius", self.min_radius_spin.value())
        s.setValue("max_radius", self.max_radius_spin.value())
        s.setValue("min_dist", self.min_dist_spin.value())
        s.setValue("dp", self.dp_spin.value())
        s.setValue("param1", self.param1_spin.value())
        s.setValue("param2", self.param2_spin.value())
        s.endGroup()

    def _load_settings(self):
        s = QSettings()
        s.beginGroup(self._SETTINGS_KEY)
        if s.contains("min_radius"):
            self.min_radius_spin.setValue(int(s.value("min_radius")))
            self.max_radius_spin.setValue(int(s.value("max_radius")))
            self.min_dist_spin.setValue(int(s.value("min_dist")))
            self.dp_spin.setValue(float(s.value("dp")))
            self.param1_spin.setValue(float(s.value("param1")))
            self.param2_spin.setValue(float(s.value("param2")))
        s.endGroup()

    def _on_capture_clicked(self):
        """Request a live frame from the camera via the main widget."""
        self.capture_frame_requested.emit()

    def _on_detect_clicked(self):
        """Run HoughCircles on the stored preview frame."""
        if not ROI_DETECTION_AVAILABLE:
            self.roi_status_label.setText("opencv-python not available.")
            return
        if self._preview_frame is None:
            self.roi_status_label.setText("No preview frame. Click 'Capture Preview Frame' first.")
            return

        try:
            result = detect_rois_hough(
                frame=self._preview_frame,
                min_radius=self.min_radius_spin.value(),
                max_radius=self.max_radius_spin.value(),
                min_dist=self.min_dist_spin.value(),
                dp=self.dp_spin.value(),
                param1=self.param1_spin.value(),
                param2=self.param2_spin.value(),
            )
            self._result = result
            self._masks = result.masks
            self._show_labeled_frame(result.labeled_frame)
            self.roi_status_label.setText(
                f"✓ {result.n_rois} ROI(s) detected. Start recording to enable live analysis."
            )
            self.roi_status_label.setStyleSheet("color: #27ae60; font-weight: bold;")
            # Emit to main widget so masks can be forwarded to RecordingController
            self.rois_detected.emit(self._masks)
            logger.info(f"ROI detection complete: {result.n_rois} ROIs")
        except Exception as exc:
            self.roi_status_label.setText(f"Detection error: {exc}")
            self.roi_status_label.setStyleSheet("color: #e74c3c;")
            logger.error(f"ROI detection failed: {exc}")

    # ------------------------------------------------------------------
    # Public API (called by main_widget)
    # ------------------------------------------------------------------

    def set_recording_duration(self, total_min: float):
        """Called by main_widget when recording starts so x-axis can be fixed to full duration."""
        self._total_duration_min = float(total_min)

    def set_phase_config(
        self,
        phase_enabled: bool,
        light_duration_min: int,
        dark_duration_min: int,
        start_with_light: bool = True,
    ):
        """
        Store phase config from the phase recording panel.
        Called by main_widget when a plain (non-schedule) recording starts.
        Ignored when a schedule is active.
        """
        if self._schedule_segments is not None:
            return  # schedule takes priority
        self._light_duration_min = light_duration_min
        self._dark_duration_min = dark_duration_min
        self._start_with_light = start_with_light
        self._phase_chk.setChecked(phase_enabled)
        if phase_enabled:
            self._schedule_info_label.setText(
                f"From phase config: {light_duration_min}min light / {dark_duration_min}min dark"
            )
            self._schedule_info_label.setStyleSheet("color: #2980b9; font-size: 10px;")
        else:
            self._schedule_info_label.setText("Continuous recording (no phases)")
            self._schedule_info_label.setStyleSheet("color: #7f8c8d; font-size: 10px;")
        if self._last_results:
            self._render_plot()

    def set_schedule(self, schedule) -> None:
        """
        Load phase overlay directly from an ExperimentSchedule.
        Called by main_widget when a schedule recording starts.
        """
        self._schedule_segments = list(schedule.segments)
        self._phase_chk.setChecked(True)
        n = len(self._schedule_segments)
        segs_desc = ", ".join(s.label for s in self._schedule_segments[:3])
        if n > 3:
            segs_desc += f" +{n - 3} more"
        self._schedule_info_label.setText(f"From schedule: {segs_desc}")
        self._schedule_info_label.setStyleSheet("color: #27ae60; font-size: 10px;")
        if self._last_results:
            self._render_plot()

    def clear_schedule(self) -> None:
        """Revert to phase-panel config (called when a plain recording starts)."""
        self._schedule_segments = None
        self._schedule_info_label.setText("No recording active")
        self._schedule_info_label.setStyleSheet("color: #7f8c8d; font-size: 10px;")

    def set_output_format(self, fmt: str):
        """
        Called by main_widget when the user changes the output format selector.
        Shows/hides the HDF5 warning banner and updates the plot status accordingly.
        """
        is_hdf5 = fmt != "zarr"
        self.format_warning_label.setVisible(is_hdf5)
        if is_hdf5:
            self.plot_status_label.setText(
                "Live analysis not available — switch to Zarr format to enable."
            )
            self.plot_status_label.setStyleSheet("color: #e67e22;")
        else:
            self.plot_status_label.setText("Waiting for recording to start...")
            self.plot_status_label.setStyleSheet("color: #7f8c8d;")

    def set_preview_frame(self, frame: np.ndarray):
        """
        Receive a live preview frame from the camera.
        Frame can be uint8 or uint16, grayscale or RGB.
        """
        self._preview_frame = frame
        self._show_raw_frame(frame)
        self.detect_btn.setEnabled(ROI_DETECTION_AVAILABLE)
        self.roi_status_label.setText("Preview frame captured. Click 'Detect ROIs'.")
        self.roi_status_label.setStyleSheet("color: #2980b9;")

    def update_activity_plot(self, results: dict):
        """
        Called by LiveAnalysisWorker (via signal) with per-ROI activity data.

        results keys: roi_0, roi_1, ..., timestamps, n_frames
        """
        if not MATPLOTLIB_AVAILABLE:
            return
        if not results:
            return

        self._last_results = results

        # Sync dropdown with available ROIs (only when count changes)
        roi_keys = sorted(k for k in results if k.startswith("roi_"))
        n_rois = len(roi_keys)
        # +1 because index 0 is "All ROIs"
        if self.roi_selector.count() != n_rois + 1:
            current_text = self.roi_selector.currentText()
            self.roi_selector.blockSignals(True)
            self.roi_selector.clear()
            self.roi_selector.addItem("All ROIs")
            for i in range(n_rois):
                self.roi_selector.addItem(f"ROI {i + 1}")
            # Restore previous selection if still valid
            idx = self.roi_selector.findText(current_text)
            self.roi_selector.setCurrentIndex(idx if idx >= 0 else 0)
            self.roi_selector.blockSignals(False)

        self._render_plot()

    def _on_roi_selector_changed(self):
        """Re-render the plot when the user changes the dropdown selection."""
        if self._last_results:
            self._render_plot()

    def _on_plot_option_changed(self):
        """Re-render when ZT toggle or phase overlay settings change."""
        if self._last_results:
            self._render_plot()

    def _compute_phase_bands(self, x_max_min: float, use_zt: bool) -> list:
        """
        Return a list of (x_start, x_end, is_light) in plot units.

        When a schedule is active, each segment contributes its own LD pattern.
        Otherwise uses the manual spinbox values.
        x units: hours when use_zt=True, minutes otherwise.
        """
        scale = 1.0 / 60.0 if use_zt else 1.0  # minutes → plot units

        bands = []
        if self._schedule_segments is not None:
            t_min = 0.0
            for seg in self._schedule_segments:
                seg_dur = (
                    float(seg.duration_min)
                    if seg.duration_min is not None
                    else max(0.0, x_max_min - t_min)
                )
                seg_end = t_min + seg_dur

                if not seg.phase_enabled:
                    is_light = getattr(seg, "continuous_led_type", "ir") in ("white", "dual")
                    bands.append((t_min * scale, seg_end * scale, is_light))
                else:
                    light_d = float(seg.light_duration_min)
                    dark_d = float(seg.dark_duration_min)
                    if light_d <= 0 or dark_d <= 0:
                        t_min = seg_end
                        continue
                    is_light = seg.start_with_light
                    bt = t_min
                    while bt < seg_end:
                        dur = light_d if is_light else dark_d
                        end = min(bt + dur, seg_end)
                        bands.append((bt * scale, end * scale, is_light))
                        bt += dur
                        is_light = not is_light

                t_min = seg_end
                if seg.duration_min is None:
                    break
        else:
            light_d = float(self._light_duration_min)
            dark_d = float(self._dark_duration_min)
            if light_d > 0 and dark_d > 0:
                is_light = self._start_with_light
                t = 0.0
                while t < x_max_min:
                    dur = light_d if is_light else dark_d
                    end = min(t + dur, x_max_min)
                    bands.append((t * scale, end * scale, is_light))
                    t += dur
                    is_light = not is_light

        return bands

    def _render_plot(self):
        """Draw the activity plot for the currently selected ROI(s)."""
        if not MATPLOTLIB_AVAILABLE or not self._last_results:
            return

        results = self._last_results
        timestamps = results.get("timestamps", None)
        n_frames = results.get("n_frames", 0)
        roi_keys = sorted(k for k in results if k.startswith("roi_"))
        all_colors = _roi_colors(len(roi_keys))

        use_zt = self._zt_checkbox.isChecked()
        show_phases = self._phase_chk.isChecked()

        selection = self.roi_selector.currentText()
        if selection == "All ROIs":
            keys_to_plot = roi_keys
            colors_to_plot = all_colors
        else:
            roi_idx = int(selection.split()[1]) - 1
            key = f"roi_{roi_idx}"
            keys_to_plot = [key] if key in results else []
            colors_to_plot = [all_colors[roi_idx]] if keys_to_plot else []

        self._ax.clear()

        # X-axis: ZT in hours or elapsed in minutes
        if use_zt:
            xlabel = "ZT (h)"
            x_scale = 1.0 / 3600.0  # seconds → hours
            x_max = self._total_duration_min / 60.0 if self._total_duration_min else None
        else:
            xlabel = "Time (min)"
            x_scale = 1.0 / 60.0  # seconds → minutes
            x_max = self._total_duration_min

        self._ax.set_xlabel(xlabel)
        self._ax.set_ylabel("Σ|ΔPixel| (norm.)")
        self._ax.set_title(f"Live Activity — {n_frames} frames recorded")
        if x_max is not None:
            self._ax.set_xlim(0, x_max)

        # Phase overlay bands (drawn first, behind signal lines)
        if show_phases:
            x_max_min = (
                self._total_duration_min
                if self._total_duration_min
                else (
                    float(np.max(timestamps) / 60.0)
                    if timestamps is not None and len(timestamps)
                    else 1440.0
                )
            )
            for x0, x1, is_light in self._compute_phase_bands(x_max_min, use_zt):
                color = "#ffe680" if is_light else "#2c2c2c"
                alpha = 0.25 if is_light else 0.18
                self._ax.axvspan(x0, x1, color=color, alpha=alpha, linewidth=0)

        self._ax.grid(True, alpha=0.3, zorder=2)

        # Signal lines
        for key, color in zip(keys_to_plot, colors_to_plot):
            activity = results[key]
            if timestamps is not None and len(timestamps) == len(activity):
                x = timestamps * x_scale
            else:
                x = np.arange(len(activity))
            roi_num = int(key.split("_")[1]) + 1
            self._ax.plot(x, activity, color=color, label=f"ROI {roi_num}", linewidth=1.2, zorder=3)

        if keys_to_plot:
            self._ax.legend(loc="upper right", fontsize=8)

        self._canvas.draw()
        n_shown = len(keys_to_plot)
        self.plot_status_label.setText(
            f"Last update: {n_frames} frames | showing {n_shown}/{len(roi_keys)} ROI(s) | updating every 20s"
        )
        self.plot_status_label.setStyleSheet("color: #27ae60;")

    def get_masks(self) -> list[np.ndarray]:
        """Return currently detected ROI masks."""
        return self._masks

    def has_rois(self) -> bool:
        """True if at least one ROI has been detected."""
        return len(self._masks) > 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    _preview_frame: np.ndarray | None = None

    def _show_raw_frame(self, frame: np.ndarray):
        """Display raw (unmodified) frame in the preview label."""
        self._show_frame_array(frame)

    def _show_labeled_frame(self, frame: np.ndarray):
        """Display HoughCircles-labeled RGB frame."""
        self._show_frame_array(frame)

    def _show_frame_array(self, frame: np.ndarray):
        """Convert numpy array to QPixmap and show in preview_label."""
        try:
            # Normalize to uint8 for display
            if frame.dtype != np.uint8:
                lo, hi = frame.min(), frame.max()
                if hi > lo:
                    frame = ((frame.astype(np.float32) - lo) / (hi - lo) * 255).astype(np.uint8)
                else:
                    frame = np.zeros_like(frame, dtype=np.uint8)

            if frame.ndim == 2:
                # Grayscale → RGB for QImage
                frame_rgb = np.stack([frame, frame, frame], axis=2)
            else:
                frame_rgb = frame[:, :, :3]  # drop alpha if present

            h, w, ch = frame_rgb.shape
            bytes_per_line = ch * w
            qimg = QImage(
                frame_rgb.tobytes(),
                w,
                h,
                bytes_per_line,
                QImage.Format_RGB888,
            )
            pixmap = QPixmap.fromImage(qimg)
            # Scale to fit label while keeping aspect ratio
            label_w = self.preview_label.width() or 400
            label_h = self.preview_label.height() or 300
            pixmap = pixmap.scaled(label_w, label_h, 1, 1)  # KeepAspectRatio, SmoothTransformation
            self.preview_label.setPixmap(pixmap)
        except Exception as exc:
            logger.error(f"Failed to display frame: {exc}")
            self.preview_label.setText("Display error")


def _roi_colors(n: int) -> list[str]:
    """Generate n distinct matplotlib colors using tab10/tab20 colormaps."""
    import matplotlib.cm as cm
    import matplotlib.colors as mcolors

    if n <= 10:
        cmap = cm.get_cmap("tab10")
        return [mcolors.to_hex(cmap(i)) for i in range(n)]
    elif n <= 20:
        cmap = cm.get_cmap("tab20")
        return [mcolors.to_hex(cmap(i)) for i in range(n)]
    else:
        # More than 20: cycle through tab20
        cmap = cm.get_cmap("tab20")
        return [mcolors.to_hex(cmap(i % 20)) for i in range(n)]
