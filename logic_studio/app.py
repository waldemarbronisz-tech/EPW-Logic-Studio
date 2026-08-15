import sys
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtCore import Qt

class LogicStudioApp(QApplication):
    def __init__(self, argv):
        super().__init__(argv)
        # Apply standard native styling or custom EPW OS styling
        self.setStyle("Fusion") # Fusion is cross-platform, somewhat native look.
        # Ensure native Windows style would be used in future if available on OS,
        # but Fusion gives a good neutral industrial look across platforms.

from logic_studio.ui.main_window import MainWindow

def main():
    app = LogicStudioApp(sys.argv)

    window = MainWindow()
    window.show()

    return app.exec()
