import sys
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtCore import Qt

class LogicStudioApp(QApplication):
    def __init__(self, argv):
        super().__init__(argv)
        # Force a classic Windows 98 / NT style
        self.setStyle("windows")

        # Set classic Win98 color palette
        from PySide6.QtGui import QPalette, QColor
        from PySide6.QtCore import Qt

        palette = QPalette()
        win_grey = QColor(192, 192, 192)
        win_dark_grey = QColor(128, 128, 128)
        win_black = QColor(0, 0, 0)
        win_white = QColor(255, 255, 255)
        win_highlight = QColor(0, 0, 128) # Classic Win98 blue

        palette.setColor(QPalette.Window, win_grey)
        palette.setColor(QPalette.WindowText, win_black)
        palette.setColor(QPalette.Base, win_white)
        palette.setColor(QPalette.AlternateBase, win_grey)
        palette.setColor(QPalette.ToolTipBase, win_white)
        palette.setColor(QPalette.ToolTipText, win_black)
        palette.setColor(QPalette.Text, win_black)
        palette.setColor(QPalette.Button, win_grey)
        palette.setColor(QPalette.ButtonText, win_black)
        palette.setColor(QPalette.BrightText, Qt.red)
        palette.setColor(QPalette.Link, win_highlight)
        palette.setColor(QPalette.Highlight, win_highlight)
        palette.setColor(QPalette.HighlightedText, win_white)

        self.setPalette(palette)

from logic_studio.ui.main_window import MainWindow

def main():
    app = LogicStudioApp(sys.argv)

    window = MainWindow()
    window.show()

    return app.exec()
