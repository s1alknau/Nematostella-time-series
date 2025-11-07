"""
Log Panel - System-Log mit Timestamps
"""

import datetime

from qtpy.QtGui import QTextCursor
from qtpy.QtWidgets import QCheckBox, QHBoxLayout, QPushButton, QTextEdit, QVBoxLayout, QWidget


class LogPanel(QWidget):
    """Panel für System-Logs"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._auto_scroll = True
        self._setup_ui()

    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Controls
        controls_layout = QHBoxLayout()

        self.auto_scroll_check = QCheckBox("Auto-scroll")
        self.auto_scroll_check.setChecked(True)
        self.auto_scroll_check.toggled.connect(self._on_auto_scroll_toggled)
        controls_layout.addWidget(self.auto_scroll_check)

        controls_layout.addStretch()

        self.clear_button = QPushButton("Clear Log")
        self.clear_button.clicked.connect(self._on_clear_clicked)
        controls_layout.addWidget(self.clear_button)

        self.save_button = QPushButton("Save Log...")
        self.save_button.clicked.connect(self._on_save_clicked)
        controls_layout.addWidget(self.save_button)

        layout.addLayout(controls_layout)

        # Log Text Area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet(
            """
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 11px;
                border: 1px solid #3e3e3e;
                border-radius: 3px;
            }
        """
        )
        self.log_text.setPlaceholderText("System logs will appear here...")

        layout.addWidget(self.log_text)

        # Initial message
        self.add_log("System initialized. Ready for recording.", level="INFO")

    def _on_auto_scroll_toggled(self, checked: bool):
        """Auto-scroll wurde geändert"""
        self._auto_scroll = checked

    def _on_clear_clicked(self):
        """Clear Button geklickt"""
        self.log_text.clear()
        self.add_log("Log cleared.", level="INFO")

    def _on_save_clicked(self):
        """Save Button geklickt"""
        from qtpy.QtWidgets import QFileDialog

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save Log File",
            f"recording_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "Text Files (*.txt);;All Files (*)",
        )

        if filename:
            try:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(self.log_text.toPlainText())
                self.add_log(f"Log saved to: {filename}", level="SUCCESS")
            except Exception as e:
                self.add_log(f"Failed to save log: {e}", level="ERROR")

    # ========================================================================
    # PUBLIC METHODS
    # ========================================================================

    def add_log(self, message: str, level: str = "INFO"):
        """
        Fügt Log-Eintrag mit Timestamp hinzu.

        Args:
            message: Log-Nachricht
            level: Log-Level (INFO, SUCCESS, WARNING, ERROR)
        """
        timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]

        # Farbe nach Level
        color_map = {
            "INFO": "#d4d4d4",
            "SUCCESS": "#4ec9b0",
            "WARNING": "#dcdcaa",
            "ERROR": "#f48771",
            "DEBUG": "#9cdcfe",
        }

        # Icon nach Level
        icon_map = {"INFO": "ℹ️", "SUCCESS": "✅", "WARNING": "⚠️", "ERROR": "❌", "DEBUG": "🔍"}

        color = color_map.get(level, "#d4d4d4")
        icon = icon_map.get(level, "•")

        # Format: [HH:MM:SS.mmm] ICON Message
        log_entry = (
            f"<span style='color: #808080;'>[{timestamp}]</span> "
            f"<span style='color: {color};'>{icon} {message}</span>"
        )

        self.log_text.append(log_entry)

        # Auto-scroll zum Ende
        if self._auto_scroll:
            cursor = self.log_text.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.log_text.setTextCursor(cursor)

    def clear(self):
        """Löscht Log"""
        self.log_text.clear()

    def get_log_text(self) -> str:
        """Gibt kompletten Log-Text zurück"""
        return self.log_text.toPlainText()
