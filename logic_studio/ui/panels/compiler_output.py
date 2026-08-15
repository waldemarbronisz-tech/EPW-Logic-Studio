from PySide6.QtWidgets import QWidget, QVBoxLayout, QTabWidget, QTextEdit
from PySide6.QtGui import QTextCursor

class CompilerOutputPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()

        # Tabs for different output types
        self.compiler_log = self._create_text_area()
        self.warnings_log = self._create_text_area()
        self.errors_log = self._create_text_area()
        self.messages_log = self._create_text_area()

        self.tabs.addTab(self.compiler_log, "Compiler")
        self.tabs.addTab(self.warnings_log, "Warnings")
        self.tabs.addTab(self.errors_log, "Errors")
        self.tabs.addTab(self.messages_log, "Messages")

        layout.addWidget(self.tabs)

    def _create_text_area(self) -> QTextEdit:
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        # Monospace font for industrial/log output
        font = text_edit.font()
        font.setFamily("Courier New")
        text_edit.setFont(font)
        return text_edit

    def log_compiler(self, message: str):
        self.compiler_log.append(message)

    def log_warning(self, message: str):
        self.warnings_log.append(f"WARNING: {message}")

    def log_error(self, message: str):
        self.errors_log.append(f"ERROR: {message}")

    def log_message(self, message: str):
        self.messages_log.append(message)
