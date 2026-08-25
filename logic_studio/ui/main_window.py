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
        act_cut = edit_menu.addAction("Cut")
        act_copy = edit_menu.addAction("Copy")
        act_paste = edit_menu.addAction("Paste")
        act_cut.setEnabled(False)
        act_copy.setEnabled(False)
        act_paste.setEnabled(False)
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
        logic_menu.addAction("Export Runtime")

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

        # New Milestone 4 Labels
        self.lbl_selected = QLabel("Selected: None")
        self.lbl_modified = QLabel("")
        self.lbl_scan = QLabel("Scan: 0ms")

        status.addWidget(self.lbl_ready, 1)
        status.addPermanentWidget(self.lbl_selected)
        status.addPermanentWidget(self.lbl_modified)
        status.addPermanentWidget(self.lbl_grid)
        status.addPermanentWidget(self.lbl_snap)
        status.addPermanentWidget(self.lbl_cursor)
        status.addPermanentWidget(self.lbl_zoom)
        status.addPermanentWidget(self.lbl_scan)
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
        from logic_studio.engine.io_provider import SimulationIOProvider
        from logic_studio.engine.time_provider import SystemTimeProvider
        from PySide6.QtCore import QTimer

        self.project = Project()
        self.io_provider = SimulationIOProvider()
        self.engine = ExecutionEngine(None, self.io_provider, SystemTimeProvider())

        self.sim_timer = QTimer(self)
        self.sim_timer.timeout.connect(self._on_sim_tick)

        self.current_file = None
        self.is_dirty = False

        # Connect Actions
        self._connect_actions()

        self.update_title()

        # Connect Selection
        self.scene.selectionChanged.connect(self._on_selection_changed)

    def closeEvent(self, event):
        if not self.check_dirty_prompt():
            event.ignore()
            return

        self.stop_simulation()
        # Clean up C++ items to prevent pointer crash on exit
        self.scene.clear()
        event.accept()

    def update_title(self):
        title = "EPW Logic Studio"
        if self.current_file:
            import os
            title += f" — {os.path.basename(self.current_file)}"
        else:
            title += " — New Project"

        if self.is_dirty:
            title += " *"

        self.setWindowTitle(title)

    def set_dirty(self):
        if not self.is_dirty:
            self.is_dirty = True
            self.update_title()

    def _connect_actions(self):
        from PySide6.QtGui import QAction
        # We find the actions from the toolbars and menus that were added as text
        for action in self.findChildren(QAction):
            t = action.text()
            if t in ["Sim Start", "Start"]:
                action.triggered.connect(self.start_simulation)
            elif t == "Pause":
                action.triggered.connect(self.engine.pause)
            elif t == "Undo":
                action.triggered.connect(self._undo)
            elif t == "Redo":
                action.triggered.connect(self._redo)
            elif t == "Stop":
                action.triggered.connect(self.stop_simulation)
            elif t == "Compile":
                action.triggered.connect(self.compile_project)
            elif t == "Export Runtime":
                action.triggered.connect(self._export_runtime)
            elif t == "Save":
                action.triggered.connect(self._save_project)
            elif t in ["Save As", "Save As..."]:
                action.triggered.connect(self._save_as_project)
            elif t in ["Open", "Open..."]:
                action.triggered.connect(self._open_project)
            elif t == "New":
                action.triggered.connect(self._new_project)

    def _export_runtime(self):
        self.compile_project()

        if not self.engine.execution_order:
            return # Compilation failed

        from PySide6.QtWidgets import QFileDialog
        import os
        import json

        path, _ = QFileDialog.getSaveFileName(self, "Export Runtime", "", "EPW Runtime Files (*.epwlogic.runtime.json)")
        if path:
            if not path.endswith(".epwlogic.runtime.json"):
                path += ".epwlogic.runtime.json"

            from logic_studio.compiler.exporter import Exporter
            exporter = Exporter(self.project, self.engine.execution_order)
            runtime_data = exporter.export()

            with open(path, 'w') as f:
                json.dump(runtime_data, f, indent=4)

            self.output_panel.log_message(f"Runtime exported to {path}")

    def compile_project(self):
        if self.engine:
            self.engine.stop()

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
            if "program" in res:
                self.engine.load_program(res["program"])

    def start_simulation(self):
        # Force a fresh compile before every run to ensure safety
        self.compile_project()

        if not self.engine.program or not self.engine.program.execution_order:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Simulation Error", "Cannot start simulation. Project compilation failed.")
            return

        self.engine.start()

        cycle_time_ms = self.project.settings.get("cycle_time_ms", 100)
        self.sim_timer.start(cycle_time_ms)

        self.lbl_sim.setText("Simulation: Running")

    def stop_simulation(self):
        self.engine.stop()
        self.sim_timer.stop()
        self.lbl_sim.setText("Simulation: Stopped")
        # Reset block values
        for block in self.project.blocks:
            for p in block.inputs + block.outputs:
                p.value = None
        self.scene.refresh_live_states()

    def check_dirty_prompt(self):
        """Returns False if user cancels, True to proceed."""
        if not self.is_dirty:
            return True

        from PySide6.QtWidgets import QMessageBox
        msg = QMessageBox(self)
        msg.setWindowTitle("Unsaved Changes")
        msg.setText("Do you want to save your changes?")
        msg.setStandardButtons(QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        ret = msg.exec()

        if ret == QMessageBox.Save:
            self._save_project()
            return not self.is_dirty
        elif ret == QMessageBox.Cancel:
            return False
        return True

    def _undo(self):
        state = self.project.undo()
        if state:
            self._apply_state(state)

    def _redo(self):
        state = self.project.redo()
        if state:
            self._apply_state(state)

    def _apply_state(self, state_dict):
        from logic_studio.core.project import Project
        self.stop_simulation()
        self.scene.clear()

        # Preserve undo/redo stacks
        undo_s = self.project.undo_stack
        redo_s = self.project.redo_stack

        self.project = Project.deserialize(state_dict)
        self.project.undo_stack = undo_s
        self.project.redo_stack = redo_s
        self.engine.project = self.project

        # Reconstruct Scene
        self._reconstruct_scene()

    def _reconstruct_scene(self):
        from logic_studio.ui.canvas.block_item import BlockItem
        from logic_studio.ui.canvas.wire_item import WireItem

        block_items = {}
        for block in self.project.blocks:
            item = BlockItem(block)
            self.scene.addItem(item)
            block_items[block.uuid] = item

        for block in self.project.blocks:
            item = block_items.get(block.uuid)
            if not item: continue
            for out_pin in block.outputs:
                for conn_uuid in out_pin.connections:
                    for dest_block in self.project.blocks:
                        dest_item = block_items.get(dest_block.uuid)
                        if not dest_item: continue
                        for in_pin in dest_block.inputs:
                            if in_pin.uuid == conn_uuid:
                                source_port = None
                                dest_port = None
                                from logic_studio.ui.canvas.port_item import PortItem
                                for child in item.childItems():
                                    if isinstance(child, PortItem) and child.pin.uuid == out_pin.uuid:
                                        source_port = child
                                        break
                                for child in dest_item.childItems():
                                    if isinstance(child, PortItem) and child.pin.uuid == in_pin.uuid:
                                        dest_port = child
                                        break
                                if source_port and dest_port:
                                    wire = WireItem(source_port, dest_port)
                                    self.scene.addItem(wire)

    def _new_project(self):
        if not self.check_dirty_prompt():
            return

        from logic_studio.core.project import Project
        self.stop_simulation()
        self.scene.clear()
        self.project = Project()
        self.engine.project = self.project
        self.current_file = None
        self.is_dirty = False
        self.update_title()

    def _save_project(self):
        if self.current_file:
            self.project.save_to_file(self.current_file)
            self.is_dirty = False
            self.update_title()
        else:
            self._save_as_project()

    def _save_as_project(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "Save Project", "", "EPW Logic Files (*.epwlogic)")
        if path:
            if not path.endswith(".epwlogic"):
                path += ".epwlogic"
            self.current_file = path
            self.project.save_to_file(self.current_file)
            self.is_dirty = False
            self.update_title()

    def _open_project_headless(self, path):
        import os
        from PySide6.QtWidgets import QMessageBox
        from logic_studio.core.project import Project
        if path and os.path.exists(path):
            self.stop_simulation()
            try:
                new_proj = Project.load_from_file(path)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to open project:\n{str(e)}")
                return
            self.scene.clear()
            self.project = new_proj
            self.engine.project = self.project
            self.current_file = path
            self.is_dirty = False
            self.update_title()
            self._reconstruct_scene()

    def _open_project(self):
        if not self.check_dirty_prompt():
            return

        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "EPW Logic Files (*.epwlogic)")
        self._open_project_headless(path)

    def _on_sim_tick(self):
        from logic_studio.engine.execution import ExecutionState
        if self.engine.state == ExecutionState.RUNNING:
            # 1. Sync UI -> IO Provider
            from logic_studio.core.device_model import DeviceModel
            ela_addrs = DeviceModel.get_ela_addresses()
            for idx, addr in enumerate(ela_addrs):
                val = self.simulation_panel.get_ela_state(idx)
                self.io_provider.set_digital_input(addr, val)

            # 2. Step Engine
            self.engine.step()

            # 3. Sync IO Provider -> UI
            ada_addrs = DeviceModel.get_ada_addresses()
            for idx, addr in enumerate(ada_addrs):
                val = self.io_provider.read_digital_output(addr)
                self.simulation_panel.set_ada_state(idx, val)

            # 4. Refresh Canvas
            self.scene.refresh_live_states()

    def _update_simulation_panel(self):
        # Sync ELA/ADA block states to the UI
        from logic_studio.core.device_model import DeviceModel
        ela_addrs = DeviceModel.get_ela_addresses()
        ada_addrs = DeviceModel.get_ada_addresses()

        for block in self.project.blocks:
            if block.__class__.__name__ == "DigitalInputBlock":
                addr = block.properties.get("Address", "")
                if addr in ela_addrs:
                    idx = ela_addrs.index(addr)
                    val = self.simulation_panel.get_ela_state(idx)
                    block.simulation_state["sim_value"] = val
            elif block.__class__.__name__ == "DigitalOutputBlock":
                addr = block.properties.get("Address", "")
                if addr in ada_addrs:
                    idx = ada_addrs.index(addr)
                    val = block.simulation_state.get("sim_value", False)
                    self.simulation_panel.set_ada_state(idx, val)

    def _on_selection_changed(self):
        selected = self.scene.selectedItems()
        from logic_studio.ui.canvas.block_item import BlockItem
        if selected and isinstance(selected[0], BlockItem):
            self.property_panel.load_block_properties(selected[0].logic_block)
            self.lbl_selected.setText(f"Selected: {selected[0].logic_block.display_name}")
        else:
            self.property_panel._set_empty_state()
            self.lbl_selected.setText("Selected: None")
