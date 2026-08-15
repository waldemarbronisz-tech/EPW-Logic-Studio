from PySide6.QtWidgets import QMainWindow, QSplitter, QWidget, QVBoxLayout, QTabWidget, QStatusBar, QToolBar, QMenuBar
from PySide6.QtCore import Qt

from logic_studio.ui.canvas.scene import LogicScene
from logic_studio.ui.canvas.view import LogicView
from logic_studio.ui.panels.library import LibraryPanel
from logic_studio.ui.panels.device_explorer import DeviceExplorerPanel
from logic_studio.ui.panels.property_grid import PropertyGridPanel
from logic_studio.ui.panels.compiler_output import CompilerOutputPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EPW Logic Studio")
        self.resize(1920, 1080)

        self._setup_menus()
        self._setup_toolbar()
        self._setup_status_bar()
        self._setup_layout()

    def _setup_menus(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        file_menu.addAction("New Project")
        file_menu.addAction("Open Project...")
        file_menu.addAction("Save Project")
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        edit_menu = menubar.addMenu("Edit")
        edit_menu.addAction("Undo")
        edit_menu.addAction("Redo")

        view_menu = menubar.addMenu("View")
        view_menu.addAction("Reset Zoom")

        sim_menu = menubar.addMenu("Simulation")
        sim_menu.addAction("Run")
        sim_menu.addAction("Pause")
        sim_menu.addAction("Stop")

    def _setup_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)

        toolbar.addAction("New")
        toolbar.addAction("Open")
        toolbar.addAction("Save")
        toolbar.addSeparator()
        toolbar.addAction("Compile")
        toolbar.addSeparator()
        toolbar.addAction("Simulate")
        toolbar.addAction("Stop")

    def _setup_status_bar(self):
        status = QStatusBar()
        self.setStatusBar(status)
        status.showMessage("Ready")

    def _setup_layout(self):
        # Main central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # We use nested splitters for the main industrial layout
        horizontal_splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(horizontal_splitter)

        # 1. Left Panel (Library & Device Explorer)
        left_tabs = QTabWidget()
        self.library_panel = LibraryPanel()
        self.device_panel = DeviceExplorerPanel()
        left_tabs.addTab(self.library_panel, "Library")
        left_tabs.addTab(self.device_panel, "Device Explorer")

        # 2. Center Panel (Canvas and Bottom Output)
        center_splitter = QSplitter(Qt.Vertical)

        self.scene = LogicScene()
        self.view = LogicView(self.scene)

        self.output_panel = CompilerOutputPanel()

        center_splitter.addWidget(self.view)
        center_splitter.addWidget(self.output_panel)
        # Give canvas more space than output panel
        center_splitter.setSizes([800, 200])

        # 3. Right Panel (Properties)
        self.property_panel = PropertyGridPanel()

        # Add to horizontal splitter
        horizontal_splitter.addWidget(left_tabs)
        horizontal_splitter.addWidget(center_splitter)
        horizontal_splitter.addWidget(self.property_panel)

        # Set relative sizes for panels: Left(15%), Center(70%), Right(15%)
        horizontal_splitter.setSizes([300, 1320, 300])
