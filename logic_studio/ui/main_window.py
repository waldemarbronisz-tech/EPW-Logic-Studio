from PySide6.QtWidgets import QMainWindow, QSplitter, QWidget, QVBoxLayout, QTabWidget, QStatusBar, QToolBar, QLabel
from PySide6.QtGui import QAction, QKeySequence, QActionGroup
from PySide6.QtCore import Qt, QSettings, QPointF

from logic_studio.ui.canvas.scene import LogicScene
from logic_studio.ui.canvas.view import LogicView
from logic_studio.ui.panels.library import LibraryPanel
from logic_studio.ui.panels.device_explorer import DeviceExplorerPanel
from logic_studio.ui.panels.property_grid import PropertyGridPanel
from logic_studio.ui.panels.compiler_output import CompilerOutputPanel
from logic_studio.ui.panels.simulation import SimulationPanel
from logic_studio.ui.panels.element_preview import ElementPreviewPanel
from logic_studio.ui.panels.signals import SignalsPanel
from logic_studio.ui.panels.watch import WatchPanel
from logic_studio.ui.panels.breadcrumb import BreadcrumbBar
from logic_studio.ui.icons import action_icon
from logic_studio.ui.panel_layout import (
    LEFT_PANEL_DOCK_WIDTH, CENTER_PANEL_DOCK_WIDTH, RIGHT_PANEL_DOCK_WIDTH,
)


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
        # feat/project-diff
        self.act_compare_saved = self._make_action("Porównaj z zapisanym plikiem...", self._compare_with_saved_file)
        self.act_compare_files = self._make_action("Porównaj dwa projekty...", self._compare_two_projects)
        self.act_exit = self._make_action("Exit", self.close)

        file_menu = menubar.addMenu("File")
        file_menu.addAction(self.act_new)
        file_menu.addAction(self.act_open)
        file_menu.addAction(self.act_save)
        file_menu.addAction(self.act_save_as)
        file_menu.addSeparator()
        file_menu.addAction(self.act_compare_saved)
        file_menu.addAction(self.act_compare_files)
        file_menu.addSeparator()
        file_menu.addAction(self.act_exit)

        # --- Edit ---
        self.act_undo = self._make_action("Undo", self._undo, "Ctrl+Z", icon_name="undo")
        self.act_redo = self._make_action("Redo", self._redo, "Ctrl+Y", icon_name="redo")
        self.act_delete = self._make_action("Delete", self._delete_selected, "Del")

        # feat/clipboard-and-align §1: an in-app clipboard (LogicScene.
        # clipboard_data), not QClipboard — see scene.py's own docstring.
        self.act_cut = self._make_action("Cut", lambda: self.scene.cut_selected_items(), "Ctrl+X")
        self.act_copy = self._make_action("Copy", lambda: self.scene.copy_selected_items(), "Ctrl+C")
        self.act_paste = self._make_action("Paste", lambda: self.scene.paste_clipboard(), "Ctrl+V")
        # §1.5: Cut/Copy need a selection, Paste needs a non-empty
        # clipboard — both start disabled and stay in sync via
        # _update_clipboard_actions()/_update_paste_action() below.
        self.act_cut.setEnabled(False)
        self.act_copy.setEnabled(False)
        self.act_paste.setEnabled(False)

        edit_menu = menubar.addMenu("Edit")
        edit_menu.addAction(self.act_undo)
        edit_menu.addAction(self.act_redo)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_cut)
        edit_menu.addAction(self.act_copy)
        edit_menu.addAction(self.act_paste)
        edit_menu.addAction(self.act_delete)
        edit_menu.addSeparator()
        # feat/clipboard-and-align §2.3: rebuilt on every open
        # (aboutToShow) rather than kept as persistent QActions — the
        # enabled state of all 8 operations depends on the CURRENT
        # selection size, and populate_align_menu() (scene.py, shared with
        # the block/canvas context menu) already does exactly that.
        self.align_menu = edit_menu.addMenu("Wyrównaj")
        self.align_menu.aboutToShow.connect(self._rebuild_align_menu)

        # feat/clipboard-and-align §4.1: "the same action" as the block's
        # own context-menu toggle (block_item.py), applied to the whole
        # selection — force-to-a-direction (two items) rather than a
        # per-block flip, since a mixed-state selection has no single
        # obvious "opposite". Both call LogicScene.set_blocks_enabled()
        # as exactly one undo entry regardless of how many blocks.
        edit_menu.addSeparator()
        self.act_disable_selected = self._make_action("Wyłącz zaznaczone bloki", self._disable_selected_blocks)
        self.act_enable_selected = self._make_action("Włącz zaznaczone bloki", self._enable_selected_blocks)
        self.act_disable_selected.setEnabled(False)
        self.act_enable_selected.setEnabled(False)
        edit_menu.addAction(self.act_disable_selected)
        edit_menu.addAction(self.act_enable_selected)

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
        # feat/signal-crossref §5.1: exports exactly what's currently
        # visible in the Sygnały panel's table (filters included) to CSV.
        self.act_export_signals = self._make_action(
            "Eksportuj listę sygnałów...", lambda: self.signals_panel.prompt_export_csv()
        )
        # feat/pdf-export: as-built documentation — the current schematic
        # plus (optionally) the same signal list Eksportuj listę
        # sygnałów... already exports as CSV, laid out on paper instead.
        self.act_export_pdf = self._make_action("Eksportuj do PDF...", self._export_pdf)

        project_menu = menubar.addMenu("Project")
        project_menu.addAction(self.act_project_settings)
        project_menu.addAction(self.act_export_signals)
        project_menu.addAction(self.act_export_pdf)

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
        # feat/help-system §6: every item here has an action wired to it
        # — nothing kept "for later" with no handler.
        self.act_help = self._make_action("Pomoc", self._show_help, "F1")
        self.act_help_catalog = self._make_action("Katalog bloków", self._show_block_catalog)
        self.act_help_shortcuts = self._make_action("Skróty klawiszowe", self._show_shortcuts_help)
        self.act_export_block_catalog = self._make_action("Eksportuj katalog bloków...", self._export_block_catalog)
        self.act_about = self._make_action("O programie", self._show_about)
        help_menu = menubar.addMenu("Help")
        help_menu.addAction(self.act_help)
        help_menu.addAction(self.act_help_catalog)
        help_menu.addAction(self.act_help_shortcuts)
        help_menu.addAction(self.act_export_block_catalog)
        help_menu.addSeparator()
        help_menu.addAction(self.act_about)
        self._help_window = None

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
        # feat/clipboard-and-align §4.3: hidden (empty text, same pattern
        # as lbl_modified above) whenever there are none — kept updated by
        # _update_disabled_blocks_status(), called from set_dirty() (every
        # live edit) and _refresh_project_dependent_panels() (project
        # load/undo/redo).
        self.lbl_disabled_blocks = QLabel("")

        status.addWidget(self.lbl_ready, 1)
        status.addPermanentWidget(self.lbl_selected)
        status.addPermanentWidget(self.lbl_disabled_blocks)
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
        # feat/help-system §5.4
        self.element_preview.more_info_requested.connect(self.show_help_for_block_type)

        library_splitter = QSplitter(Qt.Vertical)
        library_splitter.addWidget(self.library_panel)
        library_splitter.addWidget(self.element_preview)
        library_splitter.setSizes([600, 200])  # ~3:1 (§6)
        # test/panel-width-guard: this is the widget actually placed in the
        # "Library" tab (not self.library_panel alone) — the element-preview
        # table stacked below it is exactly what forced this splitter's own
        # minimum width past the left dock's budget once before (see
        # ui/panel_layout.py's PANEL_DOCK_TARGETS and its docstring).
        self.library_splitter = library_splitter

        self.device_panel = DeviceExplorerPanel()
        # feat/signal-crossref §2.1: new "Sygnały" tab alongside Library/
        # Device Explorer — kept as self.left_tabs (not a local variable)
        # so the block context menu (§4) can switch to it programmatically.
        self.signals_panel = SignalsPanel(settings=self.settings)
        # fix/wire-labels-and-project-integrity §A5: fourth left tab,
        # QTabWidget already supports it with no restructuring —
        # every network node compiler/label_merge.py can resolve, in
        # one table.
        from logic_studio.ui.panels.labels import LabelsPanel
        self.labels_panel = LabelsPanel(settings=self.settings)
        left_tabs.addTab(library_splitter, "Library")
        left_tabs.addTab(self.device_panel, "Device Explorer")
        left_tabs.addTab(self.signals_panel, "Sygnały")
        left_tabs.addTab(self.labels_panel, "Etykiety")
        self.left_tabs = left_tabs

        # feat/signal-watch: pinned signals for continuous monitoring during
        # simulation, independent of canvas/library selection. Lives in the
        # bottom output_panel (Compiler/Warnings/Errors/Messages/Runtime),
        # NOT the 300px-wide left sidebar — a table with a live-value column
        # and a trend sparkline needs the canvas-width room the bottom strip
        # already has, not a sixth of the window (see AUDIT_REPORT.md §30
        # for the "put it in the sidebar first" attempt this replaced).
        self.watch_panel = WatchPanel(settings=self.settings)
        self.watch_panel.changed.connect(self.set_dirty)

        # 2. Center Panel (Canvas and Bottom Output)
        center_splitter = QSplitter(Qt.Vertical)

        self.scene = LogicScene()
        self.scene.block_added.connect(self.library_panel.record_recently_used)
        # feat/wire-modes-and-labels §0A.2: the "only used" filter recomputes
        # on every project change a block-add/delete can cause — see
        # SimulationPanel.refresh().
        self.scene.block_added.connect(lambda _type_id: self.simulation_panel.refresh())
        # feat/signal-crossref §2.4: rebuild the cross-reference index
        # (debounced — see SignalsPanel.request_refresh()) on every block
        # placement, same trigger simulation_panel.refresh() already uses.
        self.scene.block_added.connect(lambda _type_id: self.signals_panel.request_refresh())
        self.view = LogicView(self.scene)
        self.view.cursor_moved.connect(self._on_cursor_moved)
        self.view.zoom_changed.connect(self._on_zoom_changed)

        # feat/macro-blocks: "Główny > MakroA > MakroB" trail, shown only
        # while "inside" a macro instance's own internal blocks
        # (enter_macro_instance()) — hidden at the plain top-level view.
        self.breadcrumb_bar = BreadcrumbBar()
        self.breadcrumb_bar.navigate_to.connect(self._navigate_to_breadcrumb_index)
        # feat/macro-editable-pins
        self.breadcrumb_bar.manage_pins_requested.connect(self._open_macro_pins_dialog)
        canvas_container = QWidget()
        canvas_layout = QVBoxLayout(canvas_container)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(0)
        canvas_layout.addWidget(self.breadcrumb_bar)
        canvas_layout.addWidget(self.view)

        self.output_panel = CompilerOutputPanel()
        self.output_panel.tabs.addTab(self.watch_panel, "Obserwowane")

        center_splitter.addWidget(canvas_container)
        center_splitter.addWidget(self.output_panel)
        # Give canvas more space than output panel
        center_splitter.setSizes([800, 200])

        # 3. Right Panel (Properties & Simulation)
        right_splitter = QSplitter(Qt.Vertical)
        self.property_panel = PropertyGridPanel(settings=self.settings)
        self.simulation_panel = SimulationPanel(settings=self.settings)
        self.simulation_panel.step_requested.connect(self._on_step_requested)
        right_splitter.addWidget(self.property_panel)
        right_splitter.addWidget(self.simulation_panel)

        # Add to horizontal splitter
        horizontal_splitter.addWidget(left_tabs)
        horizontal_splitter.addWidget(center_splitter)
        horizontal_splitter.addWidget(right_splitter)

        # Set relative sizes for panels: Left(15%), Center(70%), Right(15%)
        # test/panel-width-guard: these 3 numbers and the "which widget sits
        # in which pane" mapping now live in ui/panel_layout.py — the ONE
        # place both this window and tests/test_panel_width_guard.py read
        # them from, so they can never silently drift apart.
        horizontal_splitter.setSizes(
            [LEFT_PANEL_DOCK_WIDTH, CENTER_PANEL_DOCK_WIDTH, RIGHT_PANEL_DOCK_WIDTH]
        )

        # Init Application State
        from logic_studio.core.project import Project
        from logic_studio.engine.execution import ExecutionEngine
        from logic_studio.engine.io_provider import SimulationIOProvider
        from logic_studio.engine.time_provider import SystemTimeProvider
        from logic_studio.ui.qt_lifetime import create_owned_timer

        self.project = Project()
        self.io_provider = SimulationIOProvider()
        self.engine = ExecutionEngine(None, self.io_provider, SystemTimeProvider())

        # feat/macro-blocks: nav state for "inside a macro's own internal
        # blocks" (enter_macro_instance()) — self.project.blocks is
        # swapped to whichever level this represents; self.project.settings
        # is NEVER swapped, see core/macros.py's own note on this. Empty
        # stack + None def_id == the plain top-level view.
        self._macro_nav_stack = []
        self.current_macro_def_id = None

        # fix/qtimer-lifetime: was a bare QTimer(self) — already correctly
        # parented, so this migration doesn't change behavior, only brings
        # it under the one sanctioned construction path (see
        # ui/qt_lifetime.py) so the audit test in
        # tests/test_qt_timer_lifetime.py doesn't need an exception for it.
        self.sim_timer = create_owned_timer(self, self._on_sim_tick)

        self.current_file = None
        self.is_dirty = False

        self.update_title()
        self._refresh_project_dependent_panels()
        self._update_step_buttons()

        # Connect Selection
        self.scene.selectionChanged.connect(self._on_selection_changed)
        # feat/signal-crossref §3.3: highlight (never scroll to) whatever
        # row(s) in the signals panel correspond to the current canvas
        # selection.
        self.scene.selectionChanged.connect(
            lambda: self.signals_panel.highlight_blocks(self.scene.selectedItems())
        )
        # feat/clipboard-and-align §1.5: Cut/Copy track selection, Paste
        # tracks the clipboard itself.
        self.scene.selectionChanged.connect(self._update_clipboard_actions)
        self.scene.clipboard_changed.connect(self._update_paste_action)
        # feat/clipboard-and-align §4.1: same gating as Cut/Copy above.
        self.scene.selectionChanged.connect(self._update_block_toggle_actions)

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
        # feat/signal-crossref §2.4: set_dirty() is the one choke point
        # EVERY project mutation already passes through — block add/
        # delete/duplicate, every property edit (property_grid.py),
        # Project Settings (io_labels/analog_points/internal_bits). Kept
        # OUTSIDE the `if not self.is_dirty` guard above on purpose: that
        # guard exists so the title bar's "*" only updates once, but the
        # signals panel must re-request a rebuild on EVERY edit, not just
        # the first one after a clean state — request_refresh() itself is
        # what debounces a burst of these into one actual rebuild.
        self.signals_panel.request_refresh()
        # fix/wire-labels-and-project-integrity §A5: same reasoning as
        # signals_panel above — a label can be added/renamed/removed by
        # any edit, not just the wire-context-menu actions that call
        # window._reconstruct_scene() (and thus already show the CANVAS
        # side immediately) — this keeps the panel's own table current.
        self.labels_panel.request_refresh()
        self._update_disabled_blocks_status()

    def _refresh_project_dependent_panels(self):
        """Rebuild every panel whose content is derived from the current
        project's analog_points (AUDIT_REPORT.md §6/§7) — call whenever the
        project is swapped, or its analog point list changes."""
        self.device_panel.set_project(self.project)
        self.simulation_panel.set_project(self.project)
        # feat/signal-crossref §2.4: covers load/undo/redo/Project Settings
        # — set_dirty() above covers everything else.
        self.signals_panel.set_project(self.project)
        # feat/signal-watch: same coverage as signals_panel above — load/
        # undo/redo swap the whole project, this rebuilds the watch rows
        # from its (possibly different) watched_signals list.
        self.watch_panel.set_project(self.project)
        # feat/macro-blocks: same coverage again — rebuilds the library
        # tree's "Makrobloki" category from THIS project's own
        # macro_definitions (a per-project registry, unlike every other
        # category, which is a fixed BlockRegistry class list).
        self.library_panel.set_project(self.project)
        # fix/wire-labels-and-project-integrity §A5: same coverage as
        # signals_panel above — load/undo/redo swap the whole project,
        # this rebuilds the labels table from its (possibly different)
        # wires list.
        self.labels_panel.set_project(self.project)
        self._update_disabled_blocks_status()

    # ---- feat/macro-blocks: breadcrumb navigation "into" a macro ------------
    # See core/macros.py's own module-level note on the overall mechanism
    # (swap self.project.blocks, never self.project.settings) and
    # ARCHITECTURE.md §24.9 for the full design writeup.

    def enter_macro_instance(self, instance_block):
        """Double-click on a placed MacroInstanceBlock
        (BlockItem.mouseDoubleClickEvent()) — swaps the canvas to show ITS
        OWN internal blocks directly. Every existing scene operation (add/
        remove/wire/select/copy/paste/undo) keeps working completely
        unchanged from here on, since none of them know or care which
        "level" self.project.blocks currently represents — they just
        mutate whatever list is there."""
        from logic_studio.core import macros as macros_module
        from PySide6.QtWidgets import QMessageBox

        def_id = macros_module.macro_def_id(instance_block.type_id)
        if def_id is None:
            return
        definition = macros_module.get_definition(self.project, def_id)
        if definition is None:
            self.statusBar().showMessage("Definicja makrobloku nie istnieje (usunięta?).", 5000)
            return

        blocks, unknown_type_ids = macros_module.instantiate_definition_blocks(definition)
        if unknown_type_ids:
            QMessageBox.critical(
                self, "Błąd",
                f"Definicja odwołuje się do nieznanych typów bloków: {', '.join(unknown_type_ids)}"
            )
            return
        # fix/wire-labels-and-project-integrity §B1.2: project.wires is
        # swapped IN LOCKSTEP with project.blocks now — before this, it
        # stayed pointed at the top-level project's own list for the
        # whole time a macro was being edited, which made
        # check_wire_pin_consistency() false-positive on every top-level
        # Wire (its pins simply weren't in the swapped project.blocks
        # any more) and silently dropped/misplaced any Wire drawn while
        # inside the macro's own view (§9.4 of the audit that found this).
        wires = macros_module.instantiate_definition_wires(definition)

        self.stop_simulation()
        self._macro_nav_stack.append({
            "def_id": self.current_macro_def_id,
            "blocks": self.project.blocks,
            "wires": self.project.wires,
        })
        self.current_macro_def_id = def_id
        self.project.blocks = blocks
        self.project.wires = wires
        self.scene.clear()
        self._reconstruct_scene()
        self._refresh_project_dependent_panels()
        self._refresh_breadcrumb()

    def _navigate_to_breadcrumb_index(self, index: int):
        """Exits levels one at a time (innermost first, each one COMMITTED
        back into its own definition via update_definition_blocks()/
        update_definition_wires() before being popped) until the nav
        stack matches `index` — the position clicked in the breadcrumb
        trail. A no-op if `index` is already the current level
        (BreadcrumbBar never actually emits this for the last/current
        entry, but nothing here should depend on that)."""
        from logic_studio.core import macros as macros_module

        while len(self._macro_nav_stack) > index:
            if self.current_macro_def_id is not None:
                macros_module.update_definition_blocks(self.project, self.current_macro_def_id, self.project.blocks)
                # fix/wire-labels-and-project-integrity §B1.2: committed
                # in the SAME breath as blocks, never left behind.
                macros_module.update_definition_wires(self.project, self.current_macro_def_id, self.project.wires)
            parent = self._macro_nav_stack.pop()
            self.current_macro_def_id = parent["def_id"]
            self.project.blocks = parent["blocks"]
            self.project.wires = parent["wires"]

        self.scene.clear()
        self._reconstruct_scene()
        self._refresh_project_dependent_panels()
        self._refresh_breadcrumb()

    def _exit_all_macro_levels(self):
        """Commits every pending level back into its own definition and
        returns to the plain top-level view — called before any operation
        that must act on the TRUE top-level project regardless of what the
        canvas happens to be showing (Save, Compile/Run, Undo/Redo): each
        of those would otherwise risk acting on a macro's own internal
        blocks instead of the real project, or (Undo/Redo specifically)
        desyncing the breadcrumb from whatever the restored snapshot
        actually contains. A no-op when already at the top level."""
        self._navigate_to_breadcrumb_index(0)

    def _reset_macro_nav(self):
        """Hard reset, no commit — used when the WHOLE project is being
        replaced (New/Open): whatever was being edited inside a macro
        belongs to the project about to be discarded, so there is nothing
        meaningful left to save it back into."""
        self._macro_nav_stack = []
        self.current_macro_def_id = None
        self._refresh_breadcrumb()

    def _refresh_breadcrumb(self):
        from logic_studio.core import macros as macros_module

        def_ids = [entry["def_id"] for entry in self._macro_nav_stack] + [self.current_macro_def_id]
        names = []
        for def_id in def_ids:
            if def_id is None:
                names.append("Główny")
                continue
            definition = macros_module.get_definition(self.project, def_id)
            names.append(definition.get("name", def_id) if definition is not None else def_id)
        self.breadcrumb_bar.set_path(names)

    # ---- feat/macro-editable-pins -------------------------------------------
    # Unlike update_definition_blocks() (deferred until the engineer leaves
    # the macro's breadcrumb view), a boundary-pin add/remove is committed
    # AND resynced onto every placed instance IMMEDIATELY — see
    # core/macros.py's own module note on why.

    def expose_macro_pin(self, block_uuid: str, pin_name: str, direction) -> None:
        """Called by BlockItem.populate_expose_pin_menu() — exposes one of
        an internal block's own pins as a new boundary pin of the macro
        currently being edited (self.current_macro_def_id), then resyncs
        every placed instance of it. A no-op if not actually inside a
        macro's edit view right now (shouldn't happen — the menu entry
        that calls this only exists then — but this is cheap to guard
        regardless of how it's reached)."""
        def_id = self.current_macro_def_id
        if def_id is None:
            return
        from logic_studio.core import macros as macros_module
        # add_boundary_pin() looks `block_uuid` up against the definition's
        # STORED "blocks" — but `block_uuid` might belong to a block
        # placed (or edited) in THIS SAME session, which update_definition_
        # blocks() normally leaves uncommitted until the engineer actually
        # leaves the breadcrumb view (see its own docstring). Committing
        # here first means exposing a pin on a block from the current
        # session always finds it, instead of failing as though the block
        # didn't exist.
        macros_module.update_definition_blocks(self.project, def_id, self.project.blocks)
        if not macros_module.add_boundary_pin(self.project, def_id, direction, block_uuid, pin_name):
            return
        self._resync_macro_instances(def_id)
        self.set_dirty()

    def _remove_macro_pin(self, direction, index: int):
        """MacroPinsDialog's own `on_remove` callback — removes the
        boundary pin at `index` from the macro currently being edited,
        resyncs every instance, and returns the fresh definition for the
        dialog to redraw itself from (None on failure — index went stale,
        or somehow not inside a macro's edit view anymore — the dialog
        leaves its own list untouched in that case)."""
        def_id = self.current_macro_def_id
        if def_id is None:
            return None
        from logic_studio.core import macros as macros_module
        if not macros_module.remove_boundary_pin(self.project, def_id, direction, index):
            return None
        self._resync_macro_instances(def_id)
        self.set_dirty()
        return macros_module.get_definition(self.project, def_id)

    def _resync_macro_instances(self, def_id: str) -> list:
        """Rebuilds the pins AND parameter-backed properties of every
        placed instance of `def_id` — anywhere in the project, live or
        nested inside another macro's own stored definition — to match
        its (just-changed) shape. `live_block_lists` is assembled here
        from what MainWindow alone knows about (the current view plus
        every stashed ancestor level); core/macros.py's
        resync_all_instances() itself has no notion of a "nav stack" at
        all, by design (ARCHITECTURE.md §24.10). Returns whatever
        ready-to-show parameter-type-reset warnings that resync produced
        (fix/safety-and-macro-params §C1.4) — [] for a plain pin resync,
        which never produces any."""
        from logic_studio.core import macros as macros_module
        live_block_lists = [self.project.blocks] + [entry["blocks"] for entry in self._macro_nav_stack]
        return macros_module.resync_all_instances(self.project, def_id, live_block_lists)

    def _open_macro_pins_dialog(self) -> None:
        """"Piny makrobloku..." (BreadcrumbBar) — a no-op if somehow
        clicked while not actually inside a macro's edit view (the button
        is only ever visible then, same guard as expose_macro_pin())."""
        def_id = self.current_macro_def_id
        if def_id is None:
            return
        from logic_studio.core.macros import get_definition
        from logic_studio.ui.macro_pins_dialog import MacroPinsDialog

        definition = get_definition(self.project, def_id)
        if definition is None:
            return
        dialog = MacroPinsDialog(definition, self._remove_macro_pin, parent=self, on_parameter_change=self._on_macro_parameter_change)
        dialog.exec()

    # ---- fix/safety-and-macro-params §C2.4: MacroPinsDialog's "Parametry" tab

    def _on_macro_parameter_change(self, action: str, **kwargs):
        """Single dispatcher for every parameter-tab mutation
        (MacroPinsDialog's own `on_parameter_change`) — mirrors
        _remove_macro_pin()'s shape: push_state()/set_dirty()/resync,
        then return the fresh definition (or None on failure) for the
        dialog to redraw itself from. A parameter type change
        specifically doesn't reach here at all today — §C2.4 offers no
        "edit an existing parameter's type" action, only add/remove/
        reorder (a type mismatch instead arises from re-BINDING a
        property of a different type, handled entirely in
        property_grid.py's own flow) — kept as its own branch anyway so
        adding that action later is a one-line dispatch, not a new
        method."""
        def_id = self.current_macro_def_id
        if def_id is None:
            return None
        from logic_studio.core import macros as macros_module

        self.project.push_state()

        if action == "add":
            ok = macros_module.add_parameter(
                self.project, def_id, kwargs["display_name"], kwargs["type"], kwargs["default"],
                unit=kwargs.get("unit", ""), description=kwargs.get("description", ""),
                enum_values=kwargs.get("enum_values"),
            ) is not None
        elif action == "remove":
            ok = macros_module.remove_parameter(self.project, def_id, kwargs["param_name"])
        elif action == "reorder":
            ok = macros_module.reorder_parameters(self.project, def_id, kwargs["new_order"])
        elif action == "update":
            ok = macros_module.update_parameter(self.project, def_id, kwargs["param_name"], **kwargs.get("fields", {}))
        else:
            ok = False

        if not ok:
            return None

        self.set_dirty()
        notices = self._resync_macro_instances(def_id)
        if notices:
            self.statusBar().showMessage(" | ".join(notices), 8000)
        return macros_module.get_definition(self.project, def_id)

    def _update_disabled_blocks_status(self):
        """feat/clipboard-and-align §4.3: "Wyłączone bloki: N" in the
        status bar, shown only when N > 0 (same empty-string-when-clean
        pattern as lbl_modified) — a disabled block sitting unnoticed in
        safety logic is a real hazard, so this has to be visible without
        having to go looking for it."""
        n = sum(1 for b in self.project.blocks if not b.enabled)
        self.lbl_disabled_blocks.setText(f"Wyłączone bloki: {n}" if n > 0 else "")

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
        self.simulation_panel.refresh()  # §0A.2: a deleted DI/DO block may change the "used" set

    # ---- Project Settings / About --------------------------------------------

    def _open_project_settings(self):
        from PySide6.QtWidgets import QDialog
        from logic_studio.ui.dialogs import ProjectSettingsDialog

        dialog = ProjectSettingsDialog(self.project, self)
        if dialog.exec() == QDialog.Accepted:
            dialog.apply_to_project()
            self.set_dirty()
            self._refresh_project_dependent_panels()

    # ---- Help (feat/help-system) --------------------------------------------

    def _get_help_window(self):
        """Reused across repeated F1 presses/menu clicks — a fresh
        HelpWindow() every time would lose Back/Forward history and pop
        a new window on top of whatever's already open (§4.1: "okno
        nienmodalne... dało się z niego korzystać podczas pracy")."""
        from logic_studio.ui.help_window import HelpWindow
        if self._help_window is None:
            self._help_window = HelpWindow(settings=self.settings)
        return self._help_window

    def _open_help_topic(self, topic_id: str, tab: str = "contents"):
        window = self._get_help_window()
        window.select_tab(tab)
        window.navigate_to(topic_id)
        window.show()
        window.raise_()
        window.activateWindow()

    def _context_help_topic(self) -> str:
        """§5.1/§5.2: F1 with a block selected on the canvas opens straight
        to that block's own catalog page; otherwise F1 opens on whatever
        topic matches the CURRENT context (macro editing / simulation
        running), falling back to the welcome page."""
        from logic_studio.ui.canvas.block_item import BlockItem
        selected_blocks = [i for i in self.scene.selectedItems() if isinstance(i, BlockItem)]
        if len(selected_blocks) == 1:
            return f"block:{selected_blocks[0].logic_block.type_id}"

        if self.current_macro_def_id is not None:
            return "concept_macros"

        from logic_studio.engine.execution import ExecutionState
        if self.engine.state in (ExecutionState.RUNNING, ExecutionState.PAUSED):
            return "guide_simulation"

        return "welcome"

    def _show_help(self):
        """F1 — §5.1/§5.2's context-sensitive entry point."""
        self._open_help_topic(self._context_help_topic())

    def _show_block_catalog(self):
        self._open_help_topic("welcome", tab="contents")
        # Land on Contents with the tree visible rather than a specific
        # block — an explicit "Katalog bloków" menu click has no single
        # block in mind the way F1-on-a-selection does.

    def _show_shortcuts_help(self):
        self._open_help_topic("shortcuts")

    def _export_block_catalog(self):
        """§2.4: the generator also feeds a standalone export, independent
        of the interactive help window — useful for coordination
        meetings/project documentation."""
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        from logic_studio.core import block_catalog

        path, _ = QFileDialog.getSaveFileName(
            self, "Eksportuj katalog bloków", "katalog_blokow.md", "Markdown (*.md)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(block_catalog.export_catalog_markdown())
        except OSError as exc:
            QMessageBox.critical(self, "Eksport nie powiódł się", str(exc))

    def show_help_for_block_type(self, type_id: str):
        """Called from ElementPreviewPanel's "Więcej o tym bloku" link
        (§5.4) and available for any other caller that has a type_id
        on hand but no canvas selection to derive it from."""
        self._open_help_topic(f"block:{type_id}")

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

    def _export_pdf(self):
        # feat/pdf-export: same reasoning as compile_project()/
        # _save_project() below — act on the TRUE top-level project,
        # never on whatever a macro's own edit view happens to be
        # showing right now, so a client-facing PDF never accidentally
        # documents only one macro's internals.
        self._exit_all_macro_levels()

        from PySide6.QtWidgets import QFileDialog, QMessageBox

        path, _ = QFileDialog.getSaveFileName(self, "Eksportuj do PDF", "", "PDF Files (*.pdf)")
        if not path:
            return
        if not path.endswith(".pdf"):
            path += ".pdf"

        from logic_studio.ui.pdf_export import export_schematic_to_pdf
        try:
            export_schematic_to_pdf(self.scene, self.project, path)
        except Exception as e:
            QMessageBox.critical(self, "Błąd eksportu PDF", f"Nie udało się wyeksportować PDF:\n{str(e)}")
            return

        self.statusBar().showMessage(f"Wyeksportowano do {path}", 5000)

    def compile_project(self):
        # feat/macro-blocks: Compile/Run always act on the TRUE top-level
        # project, whatever the canvas happens to be showing right now —
        # commit-and-return first, same reasoning as _save_project() below.
        self._exit_all_macro_levels()

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
        # feat/macro-blocks: an undo snapshot pushed while inside a macro's
        # edit view has THAT level's blocks under its own "blocks" key —
        # restoring it without first returning to the top level would
        # desync the breadcrumb (still claiming "inside macro X") from
        # whatever the restored snapshot's `.blocks` actually turns out to
        # be. Normalizing to the top level first keeps undo/redo scoped to
        # a single, consistent level, same reasoning as compile_project().
        self._exit_all_macro_levels()
        state = self.project.undo()
        if state:
            self._apply_state(state)

    def _redo(self):
        self._exit_all_macro_levels()
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
        from logic_studio.ui.canvas.port_item import PortItem
        from logic_studio.compiler.label_merge import describe_label_groups

        block_items = {}
        for block in self.project.blocks:
            item = BlockItem(block)
            self.scene.addItem(item)
            block_items[block.uuid] = item

        pin_to_port = {}
        for block in self.project.blocks:
            item = block_items.get(block.uuid)
            if not item:
                continue
            for child in item.childItems():
                if isinstance(child, PortItem):
                    pin_to_port[child.pin.uuid] = child

        # fix/wire-labels-and-project-integrity §A4: one pass over every
        # label group up front — never recomputed per-wire or inside
        # paint() (label_merge.py's own docstring on why).
        label_summary = describe_label_groups(self.project.wires, self.project.blocks)

        def _label_info_for(label: str):
            return label_summary.get(label.strip().lower()) if label else None

        # A Wire record naming a FULLY-CONNECTED pin pair (§4.1) attaches
        # its label to the WireItem the physical-connection loop below
        # already builds — indexed by pin pair up front rather than
        # searched per-item.
        wire_by_pin_pair = {}
        for wire in self.project.wires:
            if wire.is_fully_connected():
                wire_by_pin_pair[frozenset((wire.source_pin, wire.dest_pin))] = wire

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
                                source_port = pin_to_port.get(out_pin.uuid)
                                dest_port = pin_to_port.get(in_pin.uuid)
                                if source_port and dest_port:
                                    labeled_wire = wire_by_pin_pair.get(frozenset((out_pin.uuid, in_pin.uuid)))
                                    info = _label_info_for(labeled_wire.label) if labeled_wire else None
                                    wire_item = WireItem(source_port, dest_port, wire=labeled_wire, label_info=info)
                                    self.scene.addItem(wire_item)

        # §A4.2: free-end wires get their OWN WireItem, anchored at
        # whichever end is real, with a FIXED (not cursor-following)
        # far end — see WireItem's own note on fixed_free_end vs.
        # temp_end_point.
        for wire in self.project.wires:
            if not wire.has_free_end():
                continue
            anchor_pin_uuid = wire.source_pin if wire.source_pin is not None else wire.dest_pin
            free_pos = wire.free_end_dest if wire.source_pin is not None else wire.free_end_source
            anchor_port = pin_to_port.get(anchor_pin_uuid)
            if anchor_port is None or free_pos is None:
                continue  # dangling reference — nothing to draw
            info = _label_info_for(wire.label)
            free_item = WireItem(
                anchor_port, dest_port=None, wire=wire,
                fixed_free_end=QPointF(free_pos["x"], free_pos["y"]), label_info=info,
            )
            self.scene.addItem(free_item)

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
        # feat/macro-blocks: the whole project is being replaced — whatever
        # macro was being edited belongs to the discarded one, nothing to
        # commit it back into (contrast _exit_all_macro_levels(), used
        # where the SAME project keeps going).
        self._reset_macro_nav()
        self._refresh_project_dependent_panels()

    def _save_project(self):
        # feat/macro-blocks: always save the TRUE top-level project,
        # regardless of which macro's internals the canvas currently shows.
        self._exit_all_macro_levels()
        if self.current_file:
            self.project.save_to_file(self.current_file)
            self.is_dirty = False
            self.update_title()
        else:
            self._save_as_project()

    def _save_as_project(self):
        self._exit_all_macro_levels()
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
            self._reset_macro_nav()  # feat/macro-blocks: see _new_project()
            self._refresh_project_dependent_panels()
            self._reconstruct_scene()

    def _open_project(self):
        if not self.check_dirty_prompt():
            return

        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "EPW Logic Files (*.epwlogic)")
        self._open_project_headless(path)

    # ---- feat/project-diff --------------------------------------------------

    def _load_and_normalize(self, path: str) -> dict:
        """Reads a `.epwlogic` file and runs it through
        `Project.deserialize().serialize()` before handing it to
        compare_projects() — WITHOUT this, comparing a file saved under an
        OLDER schema against the current (always-latest-schema)
        in-memory project would show every migration-introduced settings
        key (macro_definitions, watch_history, ...) as spuriously
        "added", even when the engineer hasn't touched anything since
        loading. Also means a genuinely unreadable/corrupt file (unknown
        block type_id, wrong `"format"`) fails exactly the same way
        opening it normally would, instead of silently feeding garbage
        into the diff. Raises whatever Project.deserialize()/json.load()
        raise — the caller shows it."""
        import json
        from logic_studio.core.project import Project
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Project.deserialize(data).serialize()

    def _show_project_diff(self, base: dict, target: dict, base_label: str, target_label: str):
        from logic_studio.core.project_diff import compare_projects
        from logic_studio.ui.project_diff_dialog import ProjectDiffDialog
        comparison = compare_projects(base, target)
        dialog = ProjectDiffDialog(comparison, base_label, target_label, parent=self)
        dialog.exec()

    def _compare_with_saved_file(self):
        """"Porównaj z zapisanym plikiem..." — the current in-memory
        project (whatever the canvas shows right now) against the file
        it was last saved to/loaded from. Normalizes to the top level
        first (_exit_all_macro_levels()), same reasoning as Save/Compile:
        this must compare the TRUE top-level project, not whatever a
        macro's own edit view happens to be showing."""
        from PySide6.QtWidgets import QMessageBox
        if not self.current_file:
            QMessageBox.information(self, "Porównanie", "Projekt nie był jeszcze zapisany do pliku.")
            return
        self._exit_all_macro_levels()
        try:
            saved = self._load_and_normalize(self.current_file)
        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nie udało się odczytać zapisanego pliku:\n{e}")
            return
        current = self.project.serialize()
        import os
        self._show_project_diff(saved, current, os.path.basename(self.current_file), "Bieżący stan")

    def _compare_two_projects(self):
        """"Porównaj dwa projekty..." — any two `.epwlogic` files, e.g.
        two exports from git history or two engineers' own copies.
        Doesn't touch self.project/self.current_file at all."""
        from PySide6.QtWidgets import QFileDialog
        path_a, _ = QFileDialog.getOpenFileName(self, "Wybierz starszy plik", "", "EPW Logic Files (*.epwlogic)")
        if not path_a:
            return
        path_b, _ = QFileDialog.getOpenFileName(self, "Wybierz nowszy plik", "", "EPW Logic Files (*.epwlogic)")
        if not path_b:
            return
        from PySide6.QtWidgets import QMessageBox
        try:
            data_a = self._load_and_normalize(path_a)
            data_b = self._load_and_normalize(path_b)
        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nie udało się odczytać pliku:\n{e}")
            return
        import os
        self._show_project_diff(data_a, data_b, os.path.basename(path_a), os.path.basename(path_b))

    def _push_inputs_to_io(self):
        """UI (DI checkboxes + analog input sliders/spinboxes) -> IOProvider."""
        from logic_studio.core.device_model import DeviceModel

        for idx, addr in enumerate(DeviceModel.get_ela_addresses(self.project)):
            self.io_provider.set_digital_input(addr, self.simulation_panel.get_ela_state(idx))

        for point in DeviceModel.get_analog_points(self.project):
            if point.get("direction") == "input":
                addr = point.get("address", "")
                self.io_provider.set_analog_input(addr, self.simulation_panel.get_analog_input_value(addr))

    def _pull_outputs_from_io(self):
        """IOProvider -> UI (DO LEDs + analog output readouts)."""
        from logic_studio.core.device_model import DeviceModel

        for idx, addr in enumerate(DeviceModel.get_ada_addresses(self.project)):
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
        # feat/signal-watch: one fresh sample per watched signal per scan —
        # same cadence as the DI/DO/AI/AO sync above, via the same
        # IOProvider. now_ms mirrors system.signal's own evaluate()
        # (blocks/system_signals.py), never a wall clock (determinism).
        now_ms = self.engine.time.current_time_ms() if self.engine.time else 0
        self.watch_panel.refresh_values(self.io_provider, now_ms)
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
        program loaded (the compile step already establishes that).

        fix/safety-block-semantics §9.4: STOPPED is a DRY RUN —
        ExecutionEngine.step() itself now refuses to write real outputs in
        that state (§9.3) — surfaced here so the engineer sees it too,
        not just infers it. PAUSED steps normally, with real writes."""
        from logic_studio.engine.execution import ExecutionState
        if self.engine.state not in (ExecutionState.PAUSED, ExecutionState.STOPPED):
            return
        if not self.engine.program or not self.engine.program.execution_order:
            return

        is_dry_run = self.engine.state == ExecutionState.STOPPED
        for _ in range(count):
            self._run_scan()

        if is_dry_run:
            self.statusBar().showMessage("Krok (bez zapisu wyjść)", 5000)
            self.output_panel.log_runtime(f"Manual step x{count} executed (dry-run, STOPPED — no outputs written).")
        else:
            self.output_panel.log_runtime(f"Manual step x{count} executed.")

    def _update_simulation_panel(self):
        # Sync ELA/ADA block states to the UI
        from logic_studio.core.device_model import DeviceModel
        ela_addrs = DeviceModel.get_ela_addresses(self.project)
        ada_addrs = DeviceModel.get_ada_addresses(self.project)

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
            # fix/safety-and-macro-params §C2.1: threads through which
            # macro (if any) is currently open in breadcrumb edit view —
            # None at the top level, which is every existing call site's
            # unchanged behavior (a default parameter, not a new one).
            self.property_panel.load_block_properties(selected[0].logic_block, self.project, self.current_macro_def_id)
            self.lbl_selected.setText(f"Selected: {selected[0].logic_block.display_name}")
            self.element_preview.show_block_instance(selected[0].logic_block)
        else:
            self.property_panel._set_empty_state()
            self.lbl_selected.setText("Selected: None")
            self.element_preview.clear_canvas_selection()

    def _update_clipboard_actions(self):
        """feat/clipboard-and-align §1.5."""
        has_selection = len(self.scene.selectedItems()) > 0
        self.act_cut.setEnabled(has_selection)
        self.act_copy.setEnabled(has_selection)

    def _update_paste_action(self):
        self.act_paste.setEnabled(not self.scene.clipboard_is_empty())

    def _rebuild_align_menu(self):
        """feat/clipboard-and-align §2.3: Edit -> Wyrównaj."""
        from logic_studio.ui.canvas.scene import populate_align_menu
        self.align_menu.clear()
        populate_align_menu(self.align_menu, self.scene)

    def _selected_block_items(self):
        from logic_studio.ui.canvas.block_item import BlockItem
        return [i for i in self.scene.selectedItems() if isinstance(i, BlockItem)]

    def _disable_selected_blocks(self):
        """feat/clipboard-and-align §4.1: Edit menu equivalent of the
        block's own context-menu toggle, for the whole selection."""
        self.scene.set_blocks_enabled(self._selected_block_items(), False)

    def _enable_selected_blocks(self):
        self.scene.set_blocks_enabled(self._selected_block_items(), True)

    def _update_block_toggle_actions(self):
        """feat/clipboard-and-align §4.1: same has-a-selection gating as
        Cut/Copy (_update_clipboard_actions above)."""
        has_selection = len(self._selected_block_items()) > 0
        self.act_disable_selected.setEnabled(has_selection)
        self.act_enable_selected.setEnabled(has_selection)
