from PySide6.QtWidgets import QMainWindow, QSplitter, QWidget, QVBoxLayout, QTabWidget, QStatusBar, QToolBar, QMenuBar
from PySide6.QtCore import Qt

from logic_studio.ui.canvas.scene import LogicScene
from logic_studio.ui.canvas.view import LogicView
from logic_studio.ui.panels.library import LibraryPanel
from logic_studio.ui.panels.device_explorer import DeviceExplorerPanel
from logic_studio.ui.panels.property_grid import PropertyGridPanel
from logic_studio.ui.panels.compiler_output import CompilerOutputPanel
from logic_studio.ui.panels.simulation import SimulationPanel


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
        file_menu.addAction("New")
        file_menu.addAction("Open...")
        file_menu.addAction("Save")
        file_menu.addAction("Save As...")
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        edit_menu = menubar.addMenu("Edit")
        edit_menu.addAction("Undo")
        edit_menu.addAction("Redo")
        edit_menu.addSeparator()
        edit_menu.addAction("Cut")
        edit_menu.addAction("Copy")
        edit_menu.addAction("Paste")
        edit_menu.addAction("Delete")

        view_menu = menubar.addMenu("View")
        view_menu.addAction("Zoom In")
        view_menu.addAction("Zoom Out")
        view_menu.addAction("Reset Zoom")
        view_menu.addSeparator()
        view_menu.addAction("Grid")
        view_menu.addAction("Snap")

        project_menu = menubar.addMenu("Project")
        project_menu.addAction("Project Settings")
        project_menu.addAction("Recent Projects")

        logic_menu = menubar.addMenu("Logic")
        logic_menu.addAction("Compile")

        sim_menu = menubar.addMenu("Simulation")
        sim_menu.addAction("Start")
        sim_menu.addAction("Pause")
        sim_menu.addAction("Stop")

        window_menu = menubar.addMenu("Window")
        tools_menu = menubar.addMenu("Tools")
        help_menu = menubar.addMenu("Help")

    def _setup_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(True)
        # Using placeholder text actions since we don't have physical 16x16 icon files,
        # but configured exactly like a classic Windows 98 toolbar
        self.addToolBar(toolbar)

        toolbar.addAction("New")
        toolbar.addAction("Open")
        toolbar.addAction("Save")
        toolbar.addSeparator()
        toolbar.addAction("Undo")
        toolbar.addAction("Redo")
        toolbar.addSeparator()
        toolbar.addAction("Compile")
        toolbar.addSeparator()
        toolbar.addAction("Sim Start")
        toolbar.addAction("Pause")
        toolbar.addAction("Stop")
        toolbar.addSeparator()
        toolbar.addAction("Zoom In")
        toolbar.addAction("Zoom Out")
        toolbar.addAction("Grid")
        toolbar.addAction("Snap")

    def _setup_status_bar(self):
        status = QStatusBar()
        self.setStatusBar(status)

        # Win98 style status bar labels
        from PySide6.QtWidgets import QLabel
        self.lbl_ready = QLabel("Ready")
        self.lbl_grid = QLabel("Grid ON")
        self.lbl_snap = QLabel("Snap ON")
        self.lbl_cursor = QLabel("X: 0, Y: 0")
        self.lbl_zoom = QLabel("100%")
        self.lbl_sim = QLabel("Simulation: Stopped")

        status.addWidget(self.lbl_ready, 1)
        status.addPermanentWidget(self.lbl_grid)
        status.addPermanentWidget(self.lbl_snap)
        status.addPermanentWidget(self.lbl_cursor)
        status.addPermanentWidget(self.lbl_zoom)
        status.addPermanentWidget(self.lbl_sim)

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

        # 3. Right Panel (Properties & Simulation)
        right_splitter = QSplitter(Qt.Vertical)
        self.property_panel = PropertyGridPanel()
        self.simulation_panel = SimulationPanel()
        right_splitter.addWidget(self.property_panel)
        right_splitter.addWidget(self.simulation_panel)

        # Add to horizontal splitter
        horizontal_splitter.addWidget(left_tabs)
        horizontal_splitter.addWidget(center_splitter)
        horizontal_splitter.addWidget(right_splitter)

        # Set relative sizes for panels: Left(15%), Center(70%), Right(15%)
        horizontal_splitter.setSizes([300, 1320, 300])

        # Init Application State
        from logic_studio.core.project import Project
        from logic_studio.engine.execution import ExecutionEngine
        self.project = Project()
        self.engine = ExecutionEngine(self.project, self.simulation_panel, [])
        self.engine.cycle_completed.connect(self.scene.refresh_live_states)
        self.engine.cycle_completed.connect(self._update_simulation_panel)

        # Connect Actions
        self._connect_actions()

        # Connect Selection
        self.scene.selectionChanged.connect(self._on_selection_changed)

    def _connect_actions(self):
        from PySide6.QtGui import QAction
        # We find the actions from the toolbars and menus that were added as text
        for action in self.findChildren(QAction):
            t = action.text()
            if t in ["Sim Start", "Start"]:
                action.triggered.connect(self.start_simulation)
            elif t == "Pause":
                action.triggered.connect(self.engine.pause)
            elif t == "Stop":
                action.triggered.connect(self.stop_simulation)
            elif t == "Compile":
                action.triggered.connect(self.compile_project)

    def compile_project(self):
        from logic_studio.compiler.core import Compiler
        comp = Compiler(self.project)
        res = comp.compile()

        self.output_panel.compiler_log.clear()
        self.output_panel.errors_log.clear()
        self.output_panel.warnings_log.clear()

        for w in comp.warnings:
            self.output_panel.log_warning(w)

        if not res:
            for e in comp.errors:
                self.output_panel.log_error(e)
            self.output_panel.log_message("Compilation failed.")
        else:
            self.output_panel.log_message("Compilation successful.")
            self.engine.execution_order = res["execution_order"]

    def start_simulation(self):
        if not self.engine.execution_order:
            self.compile_project()
        self.engine.start()
        self.lbl_sim.setText("Simulation: Running")

    def stop_simulation(self):
        self.engine.stop()
        self.lbl_sim.setText("Simulation: Stopped")
        # Reset block values
        for block in self.project.blocks:
            for p in block.inputs + block.outputs:
                p.value = None
        self.scene.refresh_live_states()

    def _update_simulation_panel(self):
        # Sync ELA/ADA block states to the UI
        # 1. Read Inputs from Panel -> ELA Blocks
        # 2. Write ADA Blocks -> Panel LEDs
        # (This is a simplified binding for milestone 3)
        for block in self.project.blocks:
            if block.__class__.__name__ == "DigitalInputBlock":
                addr = block.properties.get("Address", "")
                if addr.startswith("ELA"):
                    try:
                        idx = int(addr[3:]) - 1
                        val = self.simulation_panel.get_ela_state(idx)
                        block.simulation_state["sim_value"] = val
                    except ValueError:
                        pass
            elif block.__class__.__name__ == "DigitalOutputBlock":
                addr = block.properties.get("Address", "")
                if addr.startswith("ADA"):
                    try:
                        idx = int(addr[3:]) - 1
                        val = block.simulation_state.get("sim_value", False)
                        self.simulation_panel.set_ada_state(idx, val)
                    except ValueError:
                        pass

    def _on_selection_changed(self):
        selected = self.scene.selectedItems()
        from logic_studio.ui.canvas.block_item import BlockItem
        if selected and isinstance(selected[0], BlockItem):
            self.property_panel.load_block_properties(selected[0].logic_block)
        else:
            self.property_panel._set_empty_state()
