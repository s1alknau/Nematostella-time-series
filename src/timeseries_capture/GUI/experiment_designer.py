"""
Experiment Designer Widget

Allows the user to define an ordered list of recording segments, each with
its own phase configuration and duration.  The resulting ExperimentSchedule
is emitted as a Qt signal and can be passed directly to
RecordingController.start_schedule().

Layout:
    ┌─────────────────────────────────────────┐
    │  Segment table  + Add/Remove/Move buttons│
    ├─────────────────────────────────────────┤
    │  Segment editor form                     │
    ├─────────────────────────────────────────┤
    │  Timeline preview (colour-coded bars)    │
    └─────────────────────────────────────────┘
"""

from __future__ import annotations

import logging

from qtpy.QtCore import Qt
from qtpy.QtCore import Signal as pyqtSignal
from qtpy.QtGui import QColor, QPainter, QPen
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

try:
    from ..Recorder.recording_state import ExperimentSchedule, SegmentConfig

    _IMPORTS_OK = True
except ImportError:
    _IMPORTS_OK = False
    logger.warning("ExperimentDesignerWidget: recording_state imports failed")


# ---------------------------------------------------------------------------
# Timeline preview
# ---------------------------------------------------------------------------


class _TimelineWidget(QWidget):
    """
    Horizontal bar showing all segments proportional to their duration.
    LD segments alternate yellow/dark bands at the correct ratio.
    Continuous dark = dark grey, continuous light = yellow.
    Open-ended segments get a minimum width with a '>>' marker.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._segments: list[SegmentConfig] = []
        self.setMinimumHeight(60)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_segments(self, segments: list[SegmentConfig]):
        self._segments = segments
        self.update()

    def paintEvent(self, event):
        if not self._segments:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)

        w = self.width()
        h = self.height()
        y = 4
        bar_h = h - 8

        # Compute total known duration; open-ended gets 10 % minimum width
        known_min = sum(s.duration_min or 0 for s in self._segments)
        open_ended_count = sum(1 for s in self._segments if s.is_open_ended())
        open_min_each = known_min * 0.10 if known_min > 0 else 60
        total_virtual = known_min + open_ended_count * open_min_each
        if total_virtual == 0:
            return

        seg_colors_light = QColor(255, 220, 50)  # yellow
        seg_colors_dark = QColor(50, 50, 50)  # dark grey
        seg_border = QColor(120, 120, 120)

        x = 0
        for seg in self._segments:
            dur = seg.duration_min if seg.duration_min is not None else open_min_each
            seg_w = max(40, int(w * dur / total_virtual))

            if seg.phase_enabled:
                # Draw alternating LD bands
                cycle_min = seg.light_duration_min + seg.dark_duration_min
                if cycle_min <= 0:
                    cycle_min = 1
                n_cycles = max(1, int(dur / cycle_min))
                band_w = seg_w / (n_cycles * 2)
                bx = x
                is_light = seg.start_with_light
                for _ in range(n_cycles * 2):
                    bw = int(band_w)
                    color = seg_colors_light if is_light else seg_colors_dark
                    p.fillRect(int(bx), y, bw, bar_h, color)
                    is_light = not is_light
                    bx += band_w
            else:
                color = (
                    seg_colors_light
                    if seg.continuous_led_type in ("white", "dual")
                    else seg_colors_dark
                )
                p.fillRect(x, y, seg_w, bar_h, color)

            # Border
            p.setPen(QPen(seg_border, 1))
            p.drawRect(x, y, seg_w - 1, bar_h - 1)

            # Label
            p.setPen(
                Qt.white if not seg.phase_enabled and seg.continuous_led_type == "ir" else Qt.black
            )
            label = seg.label
            if seg.is_open_ended():
                label += " >>"
            elif seg.duration_min:
                d = seg.duration_min
                if d >= 1440:
                    label += f"\n{d // 1440}d"
                elif d >= 60:
                    label += f"\n{d // 60}h"
                else:
                    label += f"\n{d}min"
            p.drawText(
                x + 4,
                y + 2,
                seg_w - 8,
                bar_h - 4,
                Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap,
                label,
            )

            x += seg_w

        p.end()


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------


class ExperimentDesignerWidget(QWidget):
    """
    Full experiment schedule designer.

    Signals:
        schedule_ready(ExperimentSchedule): emitted when user clicks Start Schedule
    """

    schedule_ready = pyqtSignal(object)  # ExperimentSchedule
    stop_requested = pyqtSignal()  # emitted when user clicks Stop Recording

    def __init__(self, parent=None):
        super().__init__(parent)
        self._segments: list[SegmentConfig] = []
        self._selected_row: int = -1
        # Calibrated LED powers — filled by set_calibration_values()
        self._cal_dark_ir: int | None = None
        self._cal_light_ir: int | None = None
        self._cal_light_white: int | None = None
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        # Outer layout holds only the scroll area
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        outer.addWidget(scroll)

        # All actual content goes into this container widget
        container = QWidget()
        scroll.setWidget(container)

        root = QVBoxLayout(container)
        root.setSpacing(8)
        root.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Vertical)

        # ---- Segment table + buttons ----
        top = QWidget()
        top_lay = QVBoxLayout(top)
        top_lay.setContentsMargins(0, 0, 0, 0)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["Label", "Mode", "Light (h)", "Dark (h)", "Duration"]
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.itemSelectionChanged.connect(self._on_table_selection)
        top_lay.addWidget(self._table)

        btn_row = QHBoxLayout()
        self._btn_add = QPushButton("+ Add")
        self._btn_remove = QPushButton("− Remove")
        self._btn_up = QPushButton("↑ Up")
        self._btn_down = QPushButton("↓ Down")
        for b in (self._btn_add, self._btn_remove, self._btn_up, self._btn_down):
            btn_row.addWidget(b)
        btn_row.addStretch()
        self._btn_add.clicked.connect(self._on_add)
        self._btn_remove.clicked.connect(self._on_remove)
        self._btn_up.clicked.connect(self._on_move_up)
        self._btn_down.clicked.connect(self._on_move_down)
        top_lay.addLayout(btn_row)
        splitter.addWidget(top)

        # ---- Segment editor form ----
        editor_box = QGroupBox("Segment Editor")
        form = QFormLayout()

        self._edit_label = QLineEdit()
        form.addRow("Label:", self._edit_label)

        self._combo_mode = QComboBox()
        self._combo_mode.addItems(["LD Cycle", "Continuous Dark (DD)", "Continuous Light (LL)"])
        self._combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        form.addRow("Mode:", self._combo_mode)

        light_row = QHBoxLayout()
        self._spin_light_h = QSpinBox()
        self._spin_light_h.setRange(0, 720)
        self._spin_light_h.setValue(12)
        self._spin_light_h.setSuffix(" h")
        self._spin_light_min = QSpinBox()
        self._spin_light_min.setRange(0, 59)
        self._spin_light_min.setValue(0)
        self._spin_light_min.setSuffix(" min")
        light_row.addWidget(self._spin_light_h)
        light_row.addWidget(self._spin_light_min)
        form.addRow("Light duration:", light_row)

        dark_row = QHBoxLayout()
        self._spin_dark_h = QSpinBox()
        self._spin_dark_h.setRange(0, 720)
        self._spin_dark_h.setValue(12)
        self._spin_dark_h.setSuffix(" h")
        self._spin_dark_min = QSpinBox()
        self._spin_dark_min.setRange(0, 59)
        self._spin_dark_min.setValue(0)
        self._spin_dark_min.setSuffix(" min")
        dark_row.addWidget(self._spin_dark_h)
        dark_row.addWidget(self._spin_dark_min)
        form.addRow("Dark duration:", dark_row)

        self._chk_start_light = QCheckBox("Start with light phase")
        self._chk_start_light.setChecked(True)
        form.addRow("", self._chk_start_light)

        self._chk_dual = QCheckBox("Dual LED (IR + White) during light phase")
        form.addRow("", self._chk_dual)

        # Segment duration
        dur_row = QHBoxLayout()
        self._spin_dur_days = QSpinBox()
        self._spin_dur_days.setRange(0, 365)
        self._spin_dur_days.setValue(3)
        self._spin_dur_days.setSuffix(" d")
        self._spin_dur_hours = QSpinBox()
        self._spin_dur_hours.setRange(0, 23)
        self._spin_dur_hours.setValue(0)
        self._spin_dur_hours.setSuffix(" h")
        self._spin_dur_mins = QSpinBox()
        self._spin_dur_mins.setRange(0, 59)
        self._spin_dur_mins.setValue(0)
        self._spin_dur_mins.setSuffix(" min")
        self._chk_open_ended = QCheckBox("Open-ended (until stopped)")
        self._chk_open_ended.stateChanged.connect(self._on_open_ended_changed)
        dur_row.addWidget(self._spin_dur_days)
        dur_row.addWidget(self._spin_dur_hours)
        dur_row.addWidget(self._spin_dur_mins)
        dur_row.addWidget(self._chk_open_ended)
        form.addRow("Duration:", dur_row)

        # LED powers
        self._spin_ir_dark = QSpinBox()
        self._spin_ir_dark.setRange(0, 100)
        self._spin_ir_dark.setValue(100)
        self._spin_ir_dark.setSuffix("%")
        self._spin_ir_light = QSpinBox()
        self._spin_ir_light.setRange(0, 100)
        self._spin_ir_light.setValue(100)
        self._spin_ir_light.setSuffix("%")
        self._spin_white = QSpinBox()
        self._spin_white.setRange(0, 100)
        self._spin_white.setValue(50)
        self._spin_white.setSuffix("%")
        form.addRow("IR power (dark):", self._spin_ir_dark)
        form.addRow("IR power (light):", self._spin_ir_light)
        form.addRow("White power:", self._spin_white)

        self._cal_status_label = QLabel("⚠ No calibration values loaded")
        self._cal_status_label.setStyleSheet("color: #e67e22; font-size: 10px;")
        form.addRow("", self._cal_status_label)

        self._btn_apply = QPushButton("Apply to Segment")
        self._btn_apply.clicked.connect(self._on_apply)
        form.addRow("", self._btn_apply)

        editor_box.setLayout(form)
        splitter.addWidget(editor_box)

        # ---- Timeline ----
        tl_box = QGroupBox("Timeline Preview")
        tl_lay = QVBoxLayout(tl_box)
        self._timeline = _TimelineWidget()
        tl_lay.addWidget(self._timeline)
        splitter.addWidget(tl_box)

        splitter.setSizes([200, 280, 80])
        root.addWidget(splitter)

        # ---- Global settings ----
        glob_box = QGroupBox("Global Settings")
        gform = QFormLayout()

        self._edit_exp_name = QLineEdit("nematostella_timelapse")
        gform.addRow("Experiment name:", self._edit_exp_name)

        self._edit_output_dir = QLineEdit()
        dir_row = QHBoxLayout()
        dir_row.addWidget(self._edit_output_dir)
        btn_browse = QPushButton("Browse…")
        btn_browse.clicked.connect(self._on_browse)
        dir_row.addWidget(btn_browse)
        gform.addRow("Output directory:", dir_row)

        self._spin_interval = QSpinBox()
        self._spin_interval.setRange(1, 3600)
        self._spin_interval.setValue(5)
        self._spin_interval.setSuffix(" s")
        gform.addRow("Frame interval:", self._spin_interval)

        self._combo_format = QComboBox()
        self._combo_format.addItems(["zarr", "hdf5"])
        gform.addRow("Output format:", self._combo_format)

        self._chk_uint8 = QCheckBox("Save as uint8 (halves file size)")
        gform.addRow("", self._chk_uint8)

        glob_box.setLayout(gform)
        root.addWidget(glob_box)

        # ---- Action buttons ----
        action_row = QHBoxLayout()
        self._btn_save = QPushButton("💾 Save Schedule")
        self._btn_load = QPushButton("📂 Load Schedule")
        self._btn_start = QPushButton("▶ Start Schedule Recording")
        self._btn_start.setStyleSheet(
            "QPushButton { background-color: #27ae60; color: white; font-weight: bold; padding: 6px; }"
        )
        self._btn_stop = QPushButton("⏹ Stop Recording")
        self._btn_stop.setStyleSheet(
            "QPushButton { background-color: #c0392b; color: white; font-weight: bold; padding: 6px; }"
            "QPushButton:disabled { background-color: #7f8c8d; color: #bdc3c7; }"
        )
        self._btn_stop.setEnabled(False)
        self._total_label = QLabel("")
        self._total_label.setStyleSheet("color: #7f8c8d;")
        action_row.addWidget(self._btn_save)
        action_row.addWidget(self._btn_load)
        action_row.addStretch()
        action_row.addWidget(self._total_label)
        action_row.addWidget(self._btn_start)
        action_row.addWidget(self._btn_stop)
        root.addLayout(action_row)

        self._btn_save.clicked.connect(self._on_save)
        self._btn_load.clicked.connect(self._on_load)
        self._btn_start.clicked.connect(self._on_start)
        self._btn_stop.clicked.connect(self._on_stop)

        self._set_editor_enabled(False)

    # ------------------------------------------------------------------
    # Table helpers
    # ------------------------------------------------------------------

    def _refresh_table(self):
        self._table.setRowCount(0)
        for i, seg in enumerate(self._segments):
            self._table.insertRow(i)
            mode = (
                "LD" if seg.phase_enabled else ("LL" if seg.continuous_led_type != "ir" else "DD")
            )
            dur = self._format_duration(seg.duration_min)
            self._table.setItem(i, 0, QTableWidgetItem(seg.label))
            self._table.setItem(i, 1, QTableWidgetItem(mode))

            def _fmt_phase(m: int) -> str:
                if m < 60:
                    return f"{m}min"
                elif m % 60 == 0:
                    return f"{m // 60}h"
                else:
                    return f"{m // 60}h {m % 60}min"

            self._table.setItem(
                i,
                2,
                QTableWidgetItem(_fmt_phase(seg.light_duration_min) if seg.phase_enabled else "—"),
            )
            self._table.setItem(
                i,
                3,
                QTableWidgetItem(_fmt_phase(seg.dark_duration_min) if seg.phase_enabled else "—"),
            )
            self._table.setItem(i, 4, QTableWidgetItem(dur))
        self._timeline.set_segments(self._segments)
        self._update_total_label()

    def _format_duration(self, dur_min: int | None) -> str:
        if dur_min is None:
            return "open-ended"
        days = dur_min // 1440
        hours = (dur_min % 1440) // 60
        mins = dur_min % 60
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if mins:
            parts.append(f"{mins}min")
        return " ".join(parts) or "0min"

    def _update_total_label(self):
        total = sum(s.duration_min or 0 for s in self._segments)
        has_open = any(s.is_open_ended() for s in self._segments)
        days = total // 1440
        hours = (total % 1440) // 60
        txt = f"Total: {days}d {hours}h"
        if has_open:
            txt += " + open-ended"
        self._total_label.setText(txt)

    # ------------------------------------------------------------------
    # Editor form helpers
    # ------------------------------------------------------------------

    def _set_editor_enabled(self, enabled: bool):
        for w in (
            self._edit_label,
            self._combo_mode,
            self._spin_light_h,
            self._spin_light_min,
            self._spin_dark_h,
            self._spin_dark_min,
            self._chk_start_light,
            self._chk_dual,
            self._spin_dur_days,
            self._spin_dur_hours,
            self._spin_dur_mins,
            self._chk_open_ended,
            self._spin_ir_dark,
            self._spin_ir_light,
            self._spin_white,
            self._btn_apply,
        ):
            w.setEnabled(enabled)

    def _populate_editor(self, seg: SegmentConfig):
        self._edit_label.setText(seg.label)
        if seg.phase_enabled:
            self._combo_mode.setCurrentIndex(0)
        elif seg.continuous_led_type in ("white", "dual"):
            self._combo_mode.setCurrentIndex(2)
        else:
            self._combo_mode.setCurrentIndex(1)
        self._spin_light_h.setValue(seg.light_duration_min // 60)
        self._spin_light_min.setValue(seg.light_duration_min % 60)
        self._spin_dark_h.setValue(seg.dark_duration_min // 60)
        self._spin_dark_min.setValue(seg.dark_duration_min % 60)
        self._chk_start_light.setChecked(seg.start_with_light)
        self._chk_dual.setChecked(seg.dual_light_phase)
        self._chk_open_ended.setChecked(seg.is_open_ended())
        if not seg.is_open_ended() and seg.duration_min is not None:
            self._spin_dur_days.setValue(seg.duration_min // 1440)
            self._spin_dur_hours.setValue((seg.duration_min % 1440) // 60)
            self._spin_dur_mins.setValue(seg.duration_min % 60)
        self._spin_ir_dark.setValue(seg.dark_phase_ir_power)
        self._spin_ir_light.setValue(seg.light_phase_ir_power)
        self._spin_white.setValue(seg.light_phase_white_power)
        self._on_mode_changed()

    def _read_editor(self) -> SegmentConfig:
        mode_idx = self._combo_mode.currentIndex()
        phase_enabled = mode_idx == 0
        cont_led = "ir" if mode_idx == 1 else "white"

        dur_min: int | None = None
        if not self._chk_open_ended.isChecked():
            dur_min = (
                self._spin_dur_days.value() * 1440
                + self._spin_dur_hours.value() * 60
                + self._spin_dur_mins.value()
            )
            if dur_min == 0:
                dur_min = 1  # minimum 1 minute

        return SegmentConfig(
            label=self._edit_label.text() or "Segment",
            phase_enabled=phase_enabled,
            light_duration_min=max(
                1, self._spin_light_h.value() * 60 + self._spin_light_min.value()
            ),
            dark_duration_min=max(1, self._spin_dark_h.value() * 60 + self._spin_dark_min.value()),
            start_with_light=self._chk_start_light.isChecked(),
            dual_light_phase=self._chk_dual.isChecked(),
            continuous_led_type=cont_led,
            duration_min=dur_min,
            dark_phase_ir_power=self._spin_ir_dark.value(),
            light_phase_ir_power=self._spin_ir_light.value(),
            light_phase_white_power=self._spin_white.value(),
        )

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_mode_changed(self):
        is_ld = self._combo_mode.currentIndex() == 0
        self._spin_light_h.setEnabled(is_ld)
        self._spin_light_min.setEnabled(is_ld)
        self._spin_dark_h.setEnabled(is_ld)
        self._spin_dark_min.setEnabled(is_ld)
        self._chk_start_light.setEnabled(is_ld)
        self._chk_dual.setEnabled(is_ld)
        self._spin_ir_light.setEnabled(is_ld)

    def _on_open_ended_changed(self, state):
        enabled = not bool(state)
        self._spin_dur_days.setEnabled(enabled)
        self._spin_dur_hours.setEnabled(enabled)
        self._spin_dur_mins.setEnabled(enabled)

    def _on_table_selection(self):
        rows = self._table.selectedItems()
        if not rows:
            self._selected_row = -1
            self._set_editor_enabled(False)
            return
        row = self._table.currentRow()
        if 0 <= row < len(self._segments):
            self._selected_row = row
            self._populate_editor(self._segments[row])
            self._set_editor_enabled(True)

    def _on_add(self):
        label = f"Segment {len(self._segments) + 1}"
        seg = SegmentConfig(
            label=label,
            dark_phase_ir_power=self._cal_dark_ir if self._cal_dark_ir is not None else 100,
            light_phase_ir_power=self._cal_light_ir if self._cal_light_ir is not None else 100,
            light_phase_white_power=(
                self._cal_light_white if self._cal_light_white is not None else 50
            ),
        )
        self._segments.append(seg)
        self._refresh_table()
        self._table.selectRow(len(self._segments) - 1)

    def _on_remove(self):
        row = self._selected_row
        if 0 <= row < len(self._segments):
            self._segments.pop(row)
            self._selected_row = -1
            self._refresh_table()
            self._set_editor_enabled(False)

    def _on_move_up(self):
        row = self._selected_row
        if row > 0:
            self._segments[row], self._segments[row - 1] = (
                self._segments[row - 1],
                self._segments[row],
            )
            self._selected_row = row - 1
            self._refresh_table()
            self._table.selectRow(self._selected_row)

    def _on_move_down(self):
        row = self._selected_row
        if 0 <= row < len(self._segments) - 1:
            self._segments[row], self._segments[row + 1] = (
                self._segments[row + 1],
                self._segments[row],
            )
            self._selected_row = row + 1
            self._refresh_table()
            self._table.selectRow(self._selected_row)

    def _on_apply(self):
        row = self._selected_row
        if 0 <= row < len(self._segments):
            self._segments[row] = self._read_editor()
            self._refresh_table()
            self._table.selectRow(row)

    def _on_browse(self):
        path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if path:
            self._edit_output_dir.setText(path)

    def _on_save(self):
        sched = self._build_schedule()
        if sched is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Schedule", "", "JSON Files (*.json)")
        if path:
            try:
                with open(path, "w") as f:
                    f.write(sched.to_json())
                logger.info(f"Schedule saved to {path}")
            except Exception as exc:
                QMessageBox.warning(self, "Save Error", str(exc))

    def _on_load(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Schedule", "", "JSON Files (*.json)")
        if not path:
            return
        try:
            with open(path) as f:
                sched = ExperimentSchedule.from_json(f.read())
            self.set_schedule(sched)
            logger.info(f"Schedule loaded from {path}")
        except Exception as exc:
            QMessageBox.warning(self, "Load Error", str(exc))

    def _on_start(self):
        sched = self._build_schedule()
        if sched is None:
            return
        error = sched.validate()
        if error:
            QMessageBox.warning(self, "Invalid Schedule", error)
            return
        total = sched.total_duration_min()
        total_str = self._format_duration(total) if total else "open-ended"
        n = len(sched.segments)
        msg = f"{n} segment(s), total duration: {total_str}\n\n" + "\n".join(
            f"  {i+1}. {s.label} — "
            f"{'LD ' + str(s.light_duration_min//60) + 'h/' + str(s.dark_duration_min//60) + 'h' if s.phase_enabled else s.continuous_led_type.upper()} "
            f"— {self._format_duration(s.duration_min)}"
            for i, s in enumerate(sched.segments)
        )
        reply = QMessageBox.question(
            self, "Start Schedule Recording?", msg, QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._btn_start.setEnabled(False)
            self._btn_stop.setEnabled(True)
            self.schedule_ready.emit(sched)

    def _on_stop(self):
        reply = QMessageBox.question(
            self,
            "Stop Recording?",
            "Stop the running schedule recording?\nAlready captured frames will be saved.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._btn_stop.setEnabled(False)
            self._btn_start.setEnabled(True)
            self.stop_requested.emit()

    def set_recording_active(self, active: bool):
        """Called by the host widget to sync button states with actual recording state."""
        self._btn_start.setEnabled(not active)
        self._btn_stop.setEnabled(active)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_schedule(self) -> ExperimentSchedule | None:
        return self._build_schedule()

    def set_schedule(self, schedule: ExperimentSchedule):
        self._segments = list(schedule.segments)
        self._edit_exp_name.setText(schedule.experiment_name)
        self._edit_output_dir.setText(schedule.output_dir)
        self._spin_interval.setValue(schedule.interval_sec)
        idx = self._combo_format.findText(schedule.output_format)
        if idx >= 0:
            self._combo_format.setCurrentIndex(idx)
        self._chk_uint8.setChecked(schedule.save_as_uint8)
        self._refresh_table()

    def set_output_dir(self, path: str):
        """Called by main_widget to pre-fill the output directory."""
        self._edit_output_dir.setText(path)

    def set_interval(self, interval_sec: int):
        """Sync frame interval from the main recording panel."""
        self._spin_interval.setValue(interval_sec)

    def set_calibration_values(
        self,
        dark_ir: int | None = None,
        light_ir: int | None = None,
        light_white: int | None = None,
    ):
        """
        Store calibrated LED powers from the LED calibration panel.
        These are applied automatically when a new segment is added and
        pre-fill the editor spinboxes for the currently selected segment.
        """
        if dark_ir is not None:
            self._cal_dark_ir = dark_ir
        if light_ir is not None:
            self._cal_light_ir = light_ir
        if light_white is not None:
            self._cal_light_white = light_white

        parts = []
        if self._cal_dark_ir is not None:
            parts.append(f"IR dark={self._cal_dark_ir}%")
        if self._cal_light_ir is not None:
            parts.append(f"IR light={self._cal_light_ir}%")
        if self._cal_light_white is not None:
            parts.append(f"White={self._cal_light_white}%")

        if parts:
            self._cal_status_label.setText("✓ Calibration: " + ", ".join(parts))
            self._cal_status_label.setStyleSheet("color: #27ae60; font-size: 10px;")
        else:
            self._cal_status_label.setText("⚠ No calibration values loaded")
            self._cal_status_label.setStyleSheet("color: #e67e22; font-size: 10px;")

        # Update spinboxes immediately if a segment is selected
        self._apply_cal_to_spinboxes()

    def _apply_cal_to_spinboxes(self):
        """Push calibrated values into the LED spinboxes if available."""
        if self._cal_dark_ir is not None:
            self._spin_ir_dark.setValue(self._cal_dark_ir)
        if self._cal_light_ir is not None:
            self._spin_ir_light.setValue(self._cal_light_ir)
        if self._cal_light_white is not None:
            self._spin_white.setValue(self._cal_light_white)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_schedule(self) -> ExperimentSchedule | None:
        if not self._segments:
            QMessageBox.warning(self, "Empty Schedule", "Add at least one segment.")
            return None
        return ExperimentSchedule(
            segments=list(self._segments),
            interval_sec=self._spin_interval.value(),
            experiment_name=self._edit_exp_name.text() or "nematostella_timelapse",
            output_dir=self._edit_output_dir.text(),
            output_format=self._combo_format.currentText(),
            save_as_uint8=self._chk_uint8.isChecked(),
        )
