from PySide6.QtWidgets import QMainWindow, QSplitter, QWidget, QVBoxLayout, QTabWidget, QStatusBar, QToolBar, QMenuBar, QLabel
from PySide6.QtGui import QAction, QKeySequence, QActionGroup
from PySide6.QtCore import Qt, QSettings

from logic_studio.ui.canvas.scene import LogicScene
from logic_studio.ui.canvas.view import LogicView
from logic_studio.ui.panels.library import LibraryPanel
from logic_studio.ui.panels.device_explorer import DeviceExplorerPanel
from logic_studio.ui.panels.property_grid import PropertyGridPanel
from logic_studio.ui.panels.compiler_output import CompilerOutputPanel
from logic_studio.ui.panels.simulation import SimulationPanel
from logic_studio.ui.panels.element_preview import ElementPreviewPanel
from logic_studio.ui.icons import action_icon


class MainWindow(QMainWindow):
    def __init__(self, settings=None):
        super().__init__()
        self.setWindowTitle("EPW Logic Studio")
        self.resize(1920, 1080)

        # Injectable so tests (and any headless/CI construction) don't write
        # tree-expand-state/toolbar-style/recently-used into the real user
        # registry — QSettings("BroniszLabs", "EPW Logic Studio") is
        # NativeFormat on Windows, i.e. the actual HKCU registry.
        self.settings = settings if settings is not None else QSettings("BroniszLabs", "EPW Logic Studio")

        self._setup_status_bar()
        self._setup_menus()
        self._setup_toolbar()
        self._setup_layout()

    def _make_action(self, text, slot=None, shortcut=None, checkable=False, checked=False, icon_name=None):
        """Create one QAction and wire it up — the same instance is added to both
        the menu and the toolbar (AUDIT_REPORT.md §2.2/§2.3), so there is exactly
        one place that knows what each command does. icon_name, if given, is
        rendered procedurally via icons.action_icon() (feat/block-rendering-
        library §5.4) — no image files."""
        action = QAction(text, self)
        if icon_name:
            action.setIcon(action_icon(icon_name))
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        if checkable:
            action.setCheckable(True)
            action.setChecked(checked)
        if slot:
            action.triggered.connect(slot)
        return action

    def _setup_menus(self):
        menubar = self.menuBar()

        # --- File ---
        self.act_new = self._make_action("New", self._new_project, "Ctrl+N", icon_name="new")
        self.act_open = self._make_action("Open...", self._open_project, "Ctrl+O", icon_name="open")
        self.act_save = self._make_action("Save", self._save_project, "Ctrl+S", icon_name="save")
        self.act_save_as = self._make_action("Save As...", self._save_as_project, "Ctrl+Shift+S")
        self.act_exit = self._make_action("Exit", self.close)

        file_menu = menubar.addMenu("File")
        file_menu.addAction(self.act_new)
        file_menu.addAction(self.act_open)
        file_menu.addAction(self.act_save)
        file_menu.addAction(self.act_save_as)
        file_menu.addSeparator()
        file_menu.addAction(self.act_exit)

        # --- Edit ---
        self.act_undo = self._make_action("Undo", self._undo, "Ctrl+Z", icon_name="undo")
        self.act_redo = self._make_action("Redo", self._redo, "Ctrl+Y", icon_name="redo")
        self.act_delete = self._make_action("Delete", self._delete_selected, "Del")

        edit_menu = menubar.addMenu("Edit")
        edit_menu.addAction(self.act_undo)
        edit_menu.addAction(self.act_redo)
        edit_menu.addSeparator()
        # Cut/Copy/Paste have no implementation behind them yet — left disabled
        # rather than wired to a fake action, and not on the toolbar.
        act_cut = edit_menu.addAction("Cut")
        act_copy = edit_menu.addAction("Copy")
        act_paste = edit_menu.addAction("Paste")
        act_cut.setEnabled(False)
        act_copy.setEnabled(False)
        act_paste.setEnabled(False)
        edit_menu.addAction(self.act_delete)

        # --- View ---
        self.act_zoom_in = self._make_action("Zoom In", self._zoom_in, icon_name="zoom_in")
        self.act_zoom_out = self._make_action("Zoom Out", self._zoom_out, icon_name="zoom_out")
        self.act_reset_zoom = self._make_action("Reset Zoom", self._reset_zoom)
        self.act_grid = self._make_action("Grid", self._toggle_grid, checkable=True, checked=True, icon_name="grid")
        self.act_snap = self._make_action("Snap", self._toggle_snap, checkable=True, checked=True, icon_name="snap")

        view_menu = menubar.addMenu("View")
        view_menu.addAction(self.act_zoom_in)
        view_menu.addAction(self.act_zoom_out)
        view_menu.addAction(self.act_reset_zoom)
        view_menu.addSeparator()
        view_menu.addAction(self.act_grid)
        view_menu.addAction(self.act_snap)
        view_menu.addSeparator()

        # Toolbar display mode (§5.4): icons / icons+text / text, persisted.
        toolbar_menu = view_menu.addMenu("Toolbar")
        toolbar_style_group = QActionGroup(self)
        toolbar_style_group.setExclusive(True)

        self.act_toolbar_icons = self._make_action("Ikony", lambda: self._set_toolbar_style("icons"), checkable=True)
        self.act_toolbar_icons_text = self._make_action("Ikony i tekst", lambda: self._set_toolbar_style("icons_text"), checkable=True)
        self.act_toolbar_text = self._make_action("Tekst", lambda: self._set_toolbar_style("text"), checkable=True)

        for act in (self.act_toolbar_icons, self.act_toolbar_icons_text, self.act_toolbar_text):
            toolbar_style_group.addAction(act)
            toolbar_menu.addAction(act)

        # --- Project ---
        # "Recent Projects" had no backing mechanism and was removed rather than
        # left as a dead menu item (AUDIT_REPORT.md §2.3) — a real MRU list is a
        # separate feature, not part of this fix pass.
        self.act_project_settings = self._make_action("Project Settings", self._open_project_settings)

        project_menu = menubar.addMenu("Project")
        project_menu.addAction(self.act_project_settings)

        # --- Logic ---
        self.act_compile = self._make_action("Compile", self.compile_project, "F5", icon_name="compile")
        self.act_export_runtime = self._make_action("Export Runtime", self._export_runtime)

        logic_menu = menubar.addMenu("Logic")
        logic_menu.addAction(self.act_compile)
        logic_menu.addAction(self.act_export_runtime)

        # --- Simulation ---
        self.act_sim_start = self._make_action("Start", self.start_simulation, "F6", icon_name="start")
        self.act_sim_pause = self._make_action("Pause", self._pause_simulation, icon_name="pause")
        self.act_sim_stop = self._make_action("Stop", self.stop_simulation, "F7", icon_name="stop")

        sim_menu = menubar.addMenu("Simulation")
        sim_menu.addAction(self.act_sim_start)
        sim_menu.addAction(self.act_sim_pause)
        sim_menu.addAction(self.act_sim_stop)

        # "Window" and "Tools" had no content at all and were removed
        # (AUDIT_REPORT.md §2.3) rather than kept as empty menus.
        self.act_about = self._make_action("O programie", self._show_about)
        help_menu = menubar.addMenu("Help")
        help_menu.addAction(self.act_about)

    def _setup_toolbar(self):
        self.toolbar = QToolBar("Main Toolbar")
        self.toolbar.setMovable(True)
        self.addToolBar(self.toolbar)

        self.toolbar.addAction(self.act_new)
        self.toolbar.addAction(self.act_open)
        self.toolbar.addAction(self.act_save)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.act_undo)
        self.toolbar.addAction(self.act_redo)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.act_compile)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.act_sim_start)
        self.toolbar.addAction(self.act_sim_pause)
        self.toolbar.addAction(self.act_sim_stop)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.act_zoom_in)
        self.toolbar.addAction(self.act_zoom_out)
        self.toolbar.addAction(self.act_grid)
        self.toolbar.addAction(self.act_snap)

        self._restore_toolbar_style()

    def _set_toolbar_style(self, mode: str):
        """icons / icons_text / text — persisted (§5.4)."""
        style_map = {
            "icons": Qt.ToolButtonIconOnly,
            "icons_text": Qt.ToolButtonTextUnderIcon,
            "text": Qt.ToolButtonTextOnly,
        }
        self.toolbar.setToolButtonStyle(style_map.get(mode, Qt.ToolButtonIconOnly))
        self.settings.setValue("toolbar/style", mode)

        action_map = {
            "icons": self.act_toolbar_icons,
            "icons_text": self.act_toolbar_icons_text,
            "text": self.act_toolbar_text,
        }
        action = action_map.get(mode)
        if action and not action.isChecked():
            action.setChecked(True)

    def _restore_toolbar_style(self):
        mode = self.settings.value("toolbar/style", "icons")
        self._set_toolbar_style(mode)

    def _setup_status_bar(self):
        status = QStatusBar()
        self.setStatusBar(status)

        # Win98 style status bar labels. Every one of these is driven from a real
        # source (AUDIT_REPORT.md §2.1) — see _setup_layout() for the signal wiring
        # and compile_project()/start_simulation()/stop_simulation()/_on_sim_tick()
        # for where each value actually gets pushed in.
        self.lbl_ready = QLabel("Gotowy")
        self.lbl_grid = QLabel("Grid: ON")
        self.lbl_snap = QLabel("Snap: ON")
        self.lbl_cursor = QLabel("X: 0, Y: 0")
        self.lbl_zoom = QLabel("Zoom: 100%")
        self.lbl_sim = QLabel("Simulation: Stopped")

        self.lbl_selected = QLabel("Selected: None")
        self.lbl_modified = QLabel("")
        self.lbl_scan = QLabel("Scan: -")

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
        self.library_panel = LibraryPanel(settings=self.settings)
        self.element_preview = ElementPreviewPanel(settings=self.settings)
        self.library_panel.selection_changed.connect(lambda tid: self.element_preview.show_type_id(tid))

        library_splitter = QSplitter(Qt.Vertical)
        library_splitter.addWidget(self.library_panel)
        library_splitter.addWidget(self.element_preview)
        library_splitter.setSizes([600, 200])  # ~3:1 (§6)

        self.device_panel = DeviceExplorerPanel()
        left_tabs.addTab(library_splitter, "Library")
        left_tabs.addTab(self.device_panel, "Device Explorer")

        # 2. Center Panel (Canvas and Bottom Output)
        center_splitter = QSplitter(Qt.Vertical)

        self.scene = LogicScene()
        self.scene.block_added.connect(self.library_panel.record_recently_used)
        self.view = LogicView(self.scene)
        self.view.cursor_moved.connect(self._on_cursor_moved)
        self.view.zoom_changed.connect(self._on_zoom_changed)

        self.output_panel = CompilerOutputPanel()

        center_splitter.addWidget(self.view)
        center_splitter.addWidget(self.output_panel)
        # Give canvas more space than output panel
        center_splitter.setSizes([800, 200])

        # 3. Right Panel (Properties & Simulation)
        right_splitter = QSplitter(Qt.Vertical)
        self.property_panel = PropertyGridPanel()
        self.simulation_panel = SimulationPanel()
        self.simulation_panel.step_requested.connect(self._on_step_requested)
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

        self.update_title()
        self._refresh_project_dependent_panels()
        self._update_step_buttons()

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
        self.lbl_modified.setText("*" if self.is_dirty else "")

    def set_dirty(self):
        if not self.is_dirty:
            self.is_dirty = True
            self.update_title()

    def _refresh_project_dependent_panels(self):
        """Rebuild every panel whose content is derived from the current
        project's analog_points (AUDIT_REPORT.md §6/§7) — call whenever the
        project is swapped, or its analog point list changes."""
        self.device_panel.set_project(self.project)
        self.simulation_panel.set_project(self.project)

    def _update_step_buttons(self):
        """Manual step (§6.3) is only meaningful when the engine is not
        actively free-running: PAUSED, or STOPPED with a program loaded."""
        from logic_studio.engine.execution import ExecutionState
        can_step = (
            self.engine.state in (ExecutionState.PAUSED, ExecutionState.STOPPED)
            and self.engine.program is not None
            and bool(self.engine.program.execution_order)
        )
        self.simulation_panel.set_step_buttons_enabled(can_step)

    # ---- View: zoom / cursor / grid / snap ----------------------------------

    def _on_cursor_moved(self, x, y):
        self.lbl_cursor.setText(f"X: {int(x)}, Y: {int(y)}")

    def _on_zoom_changed(self, factor):
        self.lbl_zoom.setText(f"Zoom: {round(factor * 100)}%")

    def _zoom_in(self):
        self.view.zoom_in()

    def _zoom_out(self):
        self.view.zoom_out()

    def _reset_zoom(self):
        self.view.reset_zoom()

    def _toggle_grid(self):
        self.scene.grid_visible = self.act_grid.isChecked()
        self.lbl_grid.setText(f"Grid: {'ON' if self.scene.grid_visible else 'OFF'}")
        self.scene.update()

    def _toggle_snap(self):
        self.scene.snap_enabled = self.act_snap.isChecked()
        self.lbl_snap.setText(f"Snap: {'ON' if self.scene.snap_enabled else 'OFF'}")

    def _delete_selected(self):
        self.scene.delete_selected_items()

    # ---- Project Settings / About --------------------------------------------

    def _open_project_settings(self):
        from PySide6.QtWidgets import QDialog
        from logic_studio.ui.dialogs import ProjectSettingsDialog

        dialog = ProjectSettingsDialog(self.project, self)
        if dialog.exec() == QDialog.Accepted:
            dialog.apply_to_project()
            self.set_dirty()
            self._refresh_project_dependent_panels()

    def _show_about(self):
        from PySide6.QtWidgets import QMessageBox
        from logic_studio import __version__
        from logic_studio.core.project import EPWLOGIC_SCHEMA_VERSION

        QMessageBox.about(
            self,
            "O programie",
            f"EPW Logic Studio {__version__}\n"
            f"Format projektu: EPW_LOGIC, schema_version {EPWLOGIC_SCHEMA_VERSION}"
        )

    # ---- Logic / Simulation ---------------------------------------------------

    def _export_runtime(self):
        self.compile_project()

        if not self.engine.program or not self.engine.program.execution_order:
            return # Compilation failed

        from PySide6.QtWidgets import QFileDialog
        import json

        path, _ = QFileDialog.getSaveFileName(self, "Export Runtime", "", "EPW Runtime Files (*.epwlogic.runtime.json)")
        if path:
            if not path.endswith(".epwlogic.runtime.json"):
                path += ".epwlogic.runtime.json"

            from logic_studio.compiler.exporter import Exporter
            exporter = Exporter(self.project, self.engine.program.execution_order)
            runtime_data = exporter.export()

            for w in exporter.warnings:
                self.output_panel.log_warning(w)

            with open(path, 'w') as f:
                json.dump(runtime_data, f, indent=4)

            self.output_panel.log_message(f"Runtime exported to {path}")

    def compile_project(self):
        if self.engine:
            self.engine.stop()

        self.lbl_ready.setText("Kompilacja...")

        from logic_studio.compiler.core import Compiler
        comp = Compiler(self.project)
        res = comp.compile()

        self.output_panel.compiler_log.clear()
        self.output_panel.errors_log.clear()
        self.output_panel.warnings_log.clear()

        for w in comp.warnings:
            self.output_panel.log_warning(w)

        for i in comp.infos:
            self.output_panel.log_message(i)

        if not res:
            for e in comp.errors:
                self.output_panel.log_error(e)
            self.output_panel.log_message("Compilation failed.")
            self.lbl_ready.setText("Kompilacja zakończona błędem")
        else:
            block_count = len(self.project.blocks)
            order_len = len(comp.last_execution_order)
            self.output_panel.log_compiler(
                f"Skompilowano {block_count} blok(ów). Długość execution_order: {order_len}."
            )
            self.output_panel.log_message("Compilation successful.")
            self.lbl_ready.setText("Gotowy")
            if "program" in res:
                self.engine.load_program(res["program"])
                self.output_panel.log_runtime(
                    f"Program załadowany: {len(res['program'].blocks)} blok(ów), "
                    f"execution_order={len(res['program'].execution_order)}."
                )

        # Repaint every block so cycle-delay markers (§5.3) reflect this
        # compile's cycle_delayed_reads immediately, not just on the next
        # unrelated redraw.
        self.scene.update()

        self._update_step_buttons()

    def start_simulation(self):
        # Force a fresh compile before every run to ensure safety
        self.compile_project()

        if not self.engine.program or not self.engine.program.execution_order:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Simulation Error", "Cannot start simulation. Project compilation failed.")
            return

        self.engine.start()

        from logic_studio.engine.execution import ExecutionState
        if self.engine.state == ExecutionState.FAULT:
            self.output_panel.log_runtime("Engine transitioned to FAULT on start.")
            self.lbl_ready.setText("Symulacja: błąd silnika")
            self._update_step_buttons()
            return

        cycle_time_ms = self.project.settings.get("cycle_time_ms", 100)
        self.sim_timer.start(cycle_time_ms)

        self.lbl_sim.setText("Simulation: Running")
        self.lbl_ready.setText("Symulacja uruchomiona")
        self.output_panel.log_runtime("Simulation started.")
        self._update_step_buttons()

    def _pause_simulation(self):
        self.engine.pause()
        self.lbl_sim.setText("Simulation: Paused")
        self.output_panel.log_runtime("Simulation paused.")
        self._update_step_buttons()

    def stop_simulation(self):
        self.engine.stop()
        self.sim_timer.stop()
        self.lbl_sim.setText("Simulation: Stopped")
        self.lbl_ready.setText("Gotowy")
        self.output_panel.log_runtime("Simulation stopped.")
        # Reset block values
        for block in self.project.blocks:
            for p in block.inputs + block.outputs:
                p.value = None
        self.scene.refresh_live_states()
        self._update_step_buttons()

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
        self._refresh_project_dependent_panels()

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
        self._refresh_project_dependent_panels()

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
            self._refresh_project_dependent_panels()
            self._reconstruct_scene()

    def _open_project(self):
        if not self.check_dirty_prompt():
            return

        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "EPW Logic Files (*.epwlogic)")
        self._open_project_headless(path)

    def _push_inputs_to_io(self):
        """UI (DI checkboxes + analog input sliders/spinboxes) -> IOProvider."""
        from logic_studio.core.device_model import DeviceModel

        for idx, addr in enumerate(DeviceModel.get_ela_addresses()):
            self.io_provider.set_digital_input(addr, self.simulation_panel.get_ela_state(idx))

        for point in DeviceModel.get_analog_points(self.project):
            if point.get("direction") == "input":
                addr = point.get("address", "")
                self.io_provider.set_analog_input(addr, self.simulation_panel.get_analog_input_value(addr))

    def _pull_outputs_from_io(self):
        """IOProvider -> UI (DO LEDs + analog output readouts)."""
        from logic_studio.core.device_model import DeviceModel

        for idx, addr in enumerate(DeviceModel.get_ada_addresses()):
            self.simulation_panel.set_ada_state(idx, self.io_provider.read_digital_output(addr))

        for point in DeviceModel.get_analog_points(self.project):
            if point.get("direction") == "output":
                addr = point.get("address", "")
                self.simulation_panel.set_analog_output_value(addr, self.io_provider.read_analog_output(addr))

    def _run_scan(self):
        """One full scan: push inputs, step the engine, pull outputs, refresh
        canvas/status bar. Shared by the automatic sim timer (§2.1) and the
        manual step buttons (§6.3), so both behave identically."""
        self._push_inputs_to_io()
        self.engine.step()
        self._pull_outputs_from_io()
        self.scene.refresh_live_states()
        self.lbl_scan.setText(
            f"Scan: {self.engine.last_scan_duration_ms:.2f} ms "
            f"(max {self.engine.max_scan_duration_ms:.2f})"
        )

    def _on_sim_tick(self):
        from logic_studio.engine.execution import ExecutionState
        if self.engine.state == ExecutionState.RUNNING:
            self._run_scan()

    def _on_step_requested(self, count: int):
        """Manual "Krok"/"Krok ×10" from SimulationPanel (§6.3). Only legal
        while the engine is not free-running: PAUSED, or STOPPED with a
        program loaded (the compile step already establishes that)."""
        from logic_studio.engine.execution import ExecutionState
        if self.engine.state not in (ExecutionState.PAUSED, ExecutionState.STOPPED):
            return
        if not self.engine.program or not self.engine.program.execution_order:
            return

        for _ in range(count):
            self._run_scan()

        self.output_panel.log_runtime(f"Manual step x{count} executed.")

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
            self.property_panel.load_block_properties(selected[0].logic_block, self.project)
            self.lbl_selected.setText(f"Selected: {selected[0].logic_block.display_name}")
            self.element_preview.show_block_instance(selected[0].logic_block)
        else:
            self.property_panel._set_empty_state()
            self.lbl_selected.setText("Selected: None")
            self.element_preview.clear_canvas_selection()
