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

        # Enforce strict classic Win98/Win2K styled QSS
        # Using exact hexadecimal colors #C0C0C0 (bg), #FFFFFF (highlight), #808080 (shadow), #000000 (text)
        self.setStyleSheet("""
            QWidget {
                background-color: #C0C0C0;
                color: #000000;
                font-family: "MS Sans Serif", "Tahoma", "Arial";
                font-size: 9pt;
            }

            QMainWindow::separator {
                background: #C0C0C0;
                width: 4px;
                height: 4px;
                border-left: 1px solid #FFFFFF;
                border-top: 1px solid #FFFFFF;
                border-right: 1px solid #808080;
                border-bottom: 1px solid #808080;
            }
            QMainWindow::separator:hover {
                background: #D0D0D0;
            }

            QSplitter::handle {
                background: #C0C0C0;
                border-left: 1px solid #FFFFFF;
                border-top: 1px solid #FFFFFF;
                border-right: 1px solid #808080;
                border-bottom: 1px solid #808080;
                margin: 1px;
            }

            QMenuBar {
                background-color: #C0C0C0;
                border-bottom: 1px solid #808080;
            }
            QMenuBar::item {
                background: transparent;
                padding: 2px 6px;
            }
            QMenuBar::item:selected {
                background-color: #000080;
                color: #FFFFFF;
            }

            QMenu {
                background-color: #C0C0C0;
                border-left: 1px solid #FFFFFF;
                border-top: 1px solid #FFFFFF;
                border-right: 2px solid #000000;
                border-bottom: 2px solid #000000;
            }
            QMenu::item {
                padding: 3px 20px;
            }
            QMenu::item:selected {
                background-color: #000080;
                color: #FFFFFF;
            }

            QToolBar {
                background: #C0C0C0;
                border-bottom: 1px solid #808080;
                spacing: 2px;
            }
            QToolButton {
                background: #C0C0C0;
                border: 1px solid transparent;
                padding: 2px;
            }
            QToolButton:hover, QToolButton:pressed {
                border-left: 1px solid #FFFFFF;
                border-top: 1px solid #FFFFFF;
                border-right: 1px solid #808080;
                border-bottom: 1px solid #808080;
            }
            QToolButton:pressed {
                border-left: 1px solid #808080;
                border-top: 1px solid #808080;
                border-right: 1px solid #FFFFFF;
                border-bottom: 1px solid #FFFFFF;
                background: #B0B0B0;
            }

            QStatusBar {
                background: #C0C0C0;
                border-top: 1px solid #FFFFFF;
            }
            QStatusBar::item {
                border-left: 1px solid #808080;
                border-top: 1px solid #808080;
                border-right: 1px solid #FFFFFF;
                border-bottom: 1px solid #FFFFFF;
            }

            QTabWidget::pane {
                border-left: 1px solid #FFFFFF;
                border-top: 1px solid #FFFFFF;
                border-right: 1px solid #808080;
                border-bottom: 1px solid #808080;
                background: #C0C0C0;
            }
            QTabBar::tab {
                background: #C0C0C0;
                border-left: 1px solid #FFFFFF;
                border-top: 1px solid #FFFFFF;
                border-right: 1px solid #808080;
                border-bottom: 1px solid #C0C0C0; /* Connects with pane */
                padding: 4px 8px;
                margin-right: 2px;
            }
            QTabBar::tab:!selected {
                margin-top: 2px;
                border-bottom: 1px solid #808080;
            }

            QGroupBox {
                border-left: 1px solid #808080;
                border-top: 1px solid #808080;
                border-right: 1px solid #FFFFFF;
                border-bottom: 1px solid #FFFFFF;
                margin-top: 2ex;
                font-weight: normal;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 3px;
                left: 5px;
            }

            QTableWidget, QTreeWidget, QTextEdit, QScrollArea {
                background-color: #FFFFFF;
                border-left: 2px solid #808080;
                border-top: 2px solid #808080;
                border-right: 2px solid #FFFFFF;
                border-bottom: 2px solid #FFFFFF;
            }

            QHeaderView::section {
                background-color: #C0C0C0;
                border-left: 1px solid #FFFFFF;
                border-top: 1px solid #FFFFFF;
                border-right: 1px solid #808080;
                border-bottom: 1px solid #808080;
                padding: 2px 4px;
            }

            QScrollBar {
                background: #C0C0C0;
            }
            QScrollBar::handle {
                background: #C0C0C0;
                border-left: 1px solid #FFFFFF;
                border-top: 1px solid #FFFFFF;
                border-right: 1px solid #808080;
                border-bottom: 1px solid #808080;
            }
            QScrollBar::add-line, QScrollBar::sub-line {
                background: #C0C0C0;
                border-left: 1px solid #FFFFFF;
                border-top: 1px solid #FFFFFF;
                border-right: 1px solid #808080;
                border-bottom: 1px solid #808080;
            }
        """)

from logic_studio.ui.main_window import MainWindow

def main():
    app = LogicStudioApp(sys.argv)

    window = MainWindow()
    window.show()

    return app.exec()
