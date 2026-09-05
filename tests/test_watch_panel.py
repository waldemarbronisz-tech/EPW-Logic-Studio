"""feat/signal-watch — ui/panels/watch.py's WatchPanel, built on
core/watch.py. Table + SignalPickerDialog-driven add + sparkline trend.
"""
from PySide6.QtWidgets import QApplication, QDialog, QHeaderView

from logic_studio.core.project import Project
from logic_studio.core.device_model import DeviceModel
from logic_studio.core import watch
from logic_studio.core.crossref import (
    KIND_PHYSICAL_DI, KIND_PHYSICAL_DO, KIND_ANALOG_IN, KIND_SYSTEM,
)
from logic_studio.engine.io_provider import SimulationIOProvider
from logic_studio.ui.panels.watch import (
    WatchPanel, _TrendDialog, _TrendChart, _TIME_WINDOWS_MS, _DEFAULT_WINDOW_INDEX,
    _COL_KIND, _COL_ID, _COL_DESC, _COL_VALUE, _COL_TREND,
)
from logic_studio.blocks import register_builtin_blocks

register_builtin_blocks()


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---- empty / populated state ------------------------------------------------

def test_empty_project_shows_placeholder(qsettings):
    # isHidden() (not isVisible()) — a never-shown top-level widget's
    # descendants all report isVisible()==False regardless of their own
    # explicit setVisible() call; isHidden() tracks that explicit flag
    # directly (see test_signals_panel.py for the same reasoning).
    _app()
    p = Project()
    panel = WatchPanel(settings=qsettings)
    panel.set_project(p)
    assert panel.table.isHidden() is True
    assert panel.empty_label.isHidden() is False

def test_set_project_builds_a_row_per_watch(qsettings):
    _app()
    p = Project()
    DeviceModel.set_io_label(p, "ELA01.DI01", "Wyłącznik Q1")
    watch.add_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01")

    panel = WatchPanel(settings=qsettings)
    panel.set_project(p)

    assert panel.table.rowCount() == 1
    assert panel.table.item(0, _COL_KIND).text() == "DI"
    assert panel.table.item(0, _COL_ID).text() == "ELA01.DI01"
    assert panel.table.item(0, _COL_DESC).text() == "Wyłącznik Q1"
    assert panel.table.isHidden() is False
    assert panel.empty_label.isHidden() is True

def test_boolean_kind_gets_a_boolean_sparkline(qsettings):
    _app()
    p = Project()
    watch.add_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01")
    panel = WatchPanel(settings=qsettings)
    panel.set_project(p)
    sparkline = panel.table.cellWidget(0, _COL_TREND)
    assert sparkline.is_boolean is True

def test_analog_kind_gets_a_non_boolean_sparkline(qsettings):
    _app()
    p = Project()
    p.settings["analog_points"] = [
        {"address": "AI01", "name": "Temp", "unit": "°C", "min": 0.0, "max": 100.0, "direction": "input"},
    ]
    watch.add_watch(p, KIND_ANALOG_IN, "AI01")
    panel = WatchPanel(settings=qsettings)
    panel.set_project(p)
    sparkline = panel.table.cellWidget(0, _COL_TREND)
    assert sparkline.is_boolean is False


# ---- refresh_values ---------------------------------------------------------

def test_refresh_values_updates_value_cell_and_sparkline(qsettings):
    _app()
    p = Project()
    watch.add_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01")
    panel = WatchPanel(settings=qsettings)
    panel.set_project(p)

    io = SimulationIOProvider()
    io.set_digital_input("ELA01.DI01", True)
    panel.refresh_values(io)

    assert panel.table.item(0, _COL_VALUE).text() == "1"
    sparkline = panel.table.cellWidget(0, _COL_TREND)
    assert sparkline._samples == [True]

def test_refresh_values_shows_dash_for_unresolved_value(qsettings):
    """An internal signal removed from the registry after being watched
    resolves to None (core/watch.py::read_value) — never a crash."""
    _app()
    p = Project()
    p.settings["watched_signals"] = [{"kind": "internal_bit", "signal_id": "GONE"}]
    panel = WatchPanel(settings=qsettings)
    panel.set_project(p)

    io = SimulationIOProvider()
    panel.refresh_values(io)
    assert panel.table.item(0, _COL_VALUE).text() == "-"

def test_refresh_values_is_a_no_op_with_no_project(qsettings):
    _app()
    panel = WatchPanel(settings=qsettings)
    io = SimulationIOProvider()
    panel.refresh_values(io)  # must not raise


# ---- add via SignalPickerDialog ---------------------------------------------

def test_add_via_dialog_creates_a_watch_and_pushes_undo(qsettings, monkeypatch):
    _app()
    from logic_studio.ui.signal_picker import SignalPickerDialog

    p = Project()
    panel = WatchPanel(settings=qsettings)
    panel.set_project(p)

    def fake_exec(self):
        phys_root = self.tree.topLevelItem(0)  # "Wejścia i wyjścia fizyczne"
        leaf = phys_root.child(0)               # "ELA01.DI01"
        self.tree.setCurrentItem(leaf)
        self._on_accept()
        return QDialog.Accepted
    monkeypatch.setattr(SignalPickerDialog, "exec", fake_exec)

    changed_count = {"n": 0}
    panel.changed.connect(lambda: changed_count.__setitem__("n", changed_count["n"] + 1))

    undo_depth_before = len(p.undo_stack)
    panel._on_add_clicked()

    assert panel.table.rowCount() == 1
    assert panel.table.item(0, _COL_ID).text() == "ELA01.DI01"
    assert watch.is_watched(p, KIND_PHYSICAL_DI, "ELA01.DI01")
    assert len(p.undo_stack) == undo_depth_before + 1
    assert changed_count["n"] == 1

def test_add_via_dialog_cancelled_changes_nothing(qsettings, monkeypatch):
    _app()
    from logic_studio.ui.signal_picker import SignalPickerDialog

    p = Project()
    panel = WatchPanel(settings=qsettings)
    panel.set_project(p)
    monkeypatch.setattr(SignalPickerDialog, "exec", lambda self: QDialog.Rejected)

    panel._on_add_clicked()
    assert panel.table.rowCount() == 0
    assert watch.get_watches(p) == []


# ---- remove -----------------------------------------------------------------

def test_remove_selected_deletes_the_watch_and_pushes_one_undo_entry(qsettings):
    _app()
    p = Project()
    watch.add_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01")
    watch.add_watch(p, KIND_SYSTEM, "SYS.READY")
    panel = WatchPanel(settings=qsettings)
    panel.set_project(p)

    panel.table.selectRow(0)
    undo_depth_before = len(p.undo_stack)
    panel._on_remove_clicked()

    assert panel.table.rowCount() == 1
    assert watch.get_watches(p) == [{"kind": KIND_SYSTEM, "signal_id": "SYS.READY"}]
    assert len(p.undo_stack) == undo_depth_before + 1

def test_remove_button_disabled_without_selection(qsettings):
    _app()
    p = Project()
    watch.add_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01")
    panel = WatchPanel(settings=qsettings)
    panel.set_project(p)
    assert panel.remove_btn.isEnabled() is False

    panel.table.selectRow(0)
    assert panel.remove_btn.isEnabled() is True


# ---- placement: bottom output_panel strip, not the 300px left sidebar -----
# The panel briefly lived as a fifth tab in the narrow left sidebar (Library/
# Device Explorer/Sygnały) — unreadable at that width for a table with a
# live-value column and a trend sparkline. Moved to the bottom output_panel
# (Compiler/Warnings/Errors/Messages/Runtime), which spans the canvas width.

def test_watch_panel_lives_in_the_bottom_output_panel_not_the_sidebar(qsettings):
    _app()
    from logic_studio.ui.main_window import MainWindow

    m = MainWindow(settings=qsettings)
    assert m.output_panel.tabs.indexOf(m.watch_panel) >= 0
    assert m.left_tabs.indexOf(m.watch_panel) == -1

def test_run_scan_refreshes_the_watch_panel(qsettings):
    _app()
    from logic_studio.ui.main_window import MainWindow
    from logic_studio.blocks.registry import BlockRegistry

    m = MainWindow(settings=qsettings)
    di = BlockRegistry.create_block("input.di")
    di.properties["Address"] = "ELA01.DI01"
    m.project.add_block(di)
    watch.add_watch(m.project, KIND_PHYSICAL_DI, "ELA01.DI01")
    m.watch_panel.set_project(m.project)

    # Drive the input through SimulationPanel, exactly like a real engineer
    # clicking the DI row — _run_scan()'s _push_inputs_to_io() overwrites
    # io_provider from THIS state every scan, so setting io_provider
    # directly would just be clobbered before the watch panel ever reads it.
    m.simulation_panel._toggle_di("ELA01.DI01")
    m._run_scan()

    assert m.watch_panel.table.item(0, _COL_VALUE).text() == "1"


# ---- column resizing (§ user feedback) --------------------------------------
# The first version force-stretched Opis, leaving Trend pinned to a small
# fixed width the user had no way to enlarge. Every column must now be
# individually draggable — none Stretch.

def test_every_column_is_individually_resizable(qsettings):
    _app()
    panel = WatchPanel(settings=qsettings)
    header = panel.table.horizontalHeader()
    for col in (_COL_KIND, _COL_ID, _COL_DESC, _COL_VALUE, _COL_TREND):
        assert header.sectionResizeMode(col) == QHeaderView.Interactive
    assert header.stretchLastSection() is False

def test_resizing_the_trend_column_resizes_the_sparkline_widget(qsettings):
    """The sparkline must fill its cell, not sit as a fixed-size island
    inside a wider column — otherwise widening the column just adds blank
    padding, defeating the point of making it resizable at all."""
    _app()
    p = Project()
    watch.add_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01")
    panel = WatchPanel(settings=qsettings)
    panel.set_project(p)

    panel.table.setColumnWidth(_COL_TREND, 500)
    sparkline = panel.table.cellWidget(0, _COL_TREND)
    sparkline.resize(500, sparkline.height())
    assert sparkline.width() == 500


# ---- trend popup (§ user feedback) ------------------------------------------

def test_double_click_trend_cell_opens_a_popup(qsettings):
    _app()
    p = Project()
    watch.add_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01")
    panel = WatchPanel(settings=qsettings)
    panel.set_project(p)

    io = SimulationIOProvider()
    io.set_digital_input("ELA01.DI01", True)
    panel.refresh_values(io)

    panel._on_cell_double_clicked(0, _COL_TREND)
    key = (KIND_PHYSICAL_DI, "ELA01.DI01")
    assert key in panel._trend_dialogs
    dialog = panel._trend_dialogs[key]
    assert isinstance(dialog, _TrendDialog)
    assert [v for _, v in dialog.chart._samples] == [True]  # seeded from WatchPanel's timestamped history

def test_double_click_non_trend_column_does_nothing(qsettings):
    _app()
    p = Project()
    watch.add_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01")
    panel = WatchPanel(settings=qsettings)
    panel.set_project(p)

    panel._on_cell_double_clicked(0, _COL_ID)
    assert panel._trend_dialogs == {}

def test_double_click_again_reuses_the_open_dialog(qsettings):
    _app()
    p = Project()
    watch.add_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01")
    panel = WatchPanel(settings=qsettings)
    panel.set_project(p)

    panel._on_cell_double_clicked(0, _COL_TREND)
    first = panel._trend_dialogs[(KIND_PHYSICAL_DI, "ELA01.DI01")]
    panel._on_cell_double_clicked(0, _COL_TREND)
    assert panel._trend_dialogs[(KIND_PHYSICAL_DI, "ELA01.DI01")] is first

def test_refresh_values_feeds_an_open_trend_dialog(qsettings):
    _app()
    p = Project()
    watch.add_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01")
    panel = WatchPanel(settings=qsettings)
    panel.set_project(p)
    panel._on_cell_double_clicked(0, _COL_TREND)
    dialog = panel._trend_dialogs[(KIND_PHYSICAL_DI, "ELA01.DI01")]

    io = SimulationIOProvider()
    io.set_digital_input("ELA01.DI01", True)
    panel.refresh_values(io)

    assert [v for _, v in dialog.chart._samples] == [True]

def test_removing_a_watched_row_closes_its_open_trend_dialog(qsettings):
    _app()
    p = Project()
    watch.add_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01")
    panel = WatchPanel(settings=qsettings)
    panel.set_project(p)
    panel._on_cell_double_clicked(0, _COL_TREND)
    assert len(panel._trend_dialogs) == 1

    panel.table.selectRow(0)
    panel._on_remove_clicked()
    assert panel._trend_dialogs == {}

def test_set_project_closes_all_open_trend_dialogs(qsettings):
    _app()
    p = Project()
    watch.add_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01")
    panel = WatchPanel(settings=qsettings)
    panel.set_project(p)
    panel._on_cell_double_clicked(0, _COL_TREND)
    assert len(panel._trend_dialogs) == 1

    panel.set_project(p)  # e.g. an undo/redo swap
    assert panel._trend_dialogs == {}

def test_boolean_trend_dialog_has_no_manual_scale_controls(qsettings):
    _app()
    p = Project()
    watch.add_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01")
    panel = WatchPanel(settings=qsettings)
    panel.set_project(p)
    panel._on_cell_double_clicked(0, _COL_TREND)
    dialog = panel._trend_dialogs[(KIND_PHYSICAL_DI, "ELA01.DI01")]
    assert not hasattr(dialog, "auto_check")

def test_analog_trend_dialog_manual_scale_overrides_the_chart_range(qsettings):
    _app()
    p = Project()
    p.settings["analog_points"] = [
        {"address": "AI01", "name": "Temp", "unit": "°C", "min": 0.0, "max": 100.0, "direction": "input"},
    ]
    watch.add_watch(p, KIND_ANALOG_IN, "AI01")
    panel = WatchPanel(settings=qsettings)
    panel.set_project(p)
    panel._on_cell_double_clicked(0, _COL_TREND)
    dialog = panel._trend_dialogs[(KIND_ANALOG_IN, "AI01")]

    assert dialog.chart.manual_range is None  # auto by default
    dialog.auto_check.setChecked(False)
    dialog.min_spin.setValue(10.0)
    dialog.max_spin.setValue(20.0)
    assert dialog.chart.manual_range == (10.0, 20.0)

    dialog.auto_check.setChecked(True)
    assert dialog.chart.manual_range is None

def test_trend_dialog_clear_button_empties_the_chart_buffer(qsettings):
    _app()
    p = Project()
    watch.add_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01")
    panel = WatchPanel(settings=qsettings)
    panel.set_project(p)

    io = SimulationIOProvider()
    io.set_digital_input("ELA01.DI01", True)
    panel.refresh_values(io)
    panel._on_cell_double_clicked(0, _COL_TREND)
    dialog = panel._trend_dialogs[(KIND_PHYSICAL_DI, "ELA01.DI01")]
    assert [v for _, v in dialog.chart._samples] == [True]

    dialog.chart.clear_samples()
    assert dialog.chart._samples == []


# ---- time window (§ user feedback: "edit scale, time(s), etc.") -----------
# _TrendChart shows a SELECTABLE TIME WINDOW (real engine-time timestamps),
# not just "last N samples" — the inline table _Sparkline's simpler model.

def test_trend_dialog_has_a_time_window_selector_defaulting_to_one_minute(qsettings):
    _app()
    p = Project()
    watch.add_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01")
    panel = WatchPanel(settings=qsettings)
    panel.set_project(p)
    panel._on_cell_double_clicked(0, _COL_TREND)
    dialog = panel._trend_dialogs[(KIND_PHYSICAL_DI, "ELA01.DI01")]

    assert dialog.window_combo.count() == len(_TIME_WINDOWS_MS)
    assert dialog.window_combo.currentIndex() == _DEFAULT_WINDOW_INDEX
    assert dialog.chart.window_ms == _TIME_WINDOWS_MS[_DEFAULT_WINDOW_INDEX][1]

def test_changing_the_time_window_updates_the_chart(qsettings):
    _app()
    p = Project()
    watch.add_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01")
    panel = WatchPanel(settings=qsettings)
    panel.set_project(p)
    panel._on_cell_double_clicked(0, _COL_TREND)
    dialog = panel._trend_dialogs[(KIND_PHYSICAL_DI, "ELA01.DI01")]

    dialog.window_combo.setCurrentIndex(0)  # "10 s"
    assert dialog.chart.window_ms == _TIME_WINDOWS_MS[0][1]

def test_trend_chart_visible_samples_filters_by_window():
    _app()
    chart = _TrendChart(is_boolean=True)
    chart.set_window_ms(30_000)
    chart.set_samples([(0, False), (60_000, True), (75_000, False)])

    visible = chart._visible_samples(now_ms=90_000)  # window: [60_000, 90_000]
    assert visible == [(60_000, True), (75_000, False)]

def test_seeded_dialog_receives_watchpanels_timestamped_history(qsettings):
    _app()
    p = Project()
    watch.add_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01")
    panel = WatchPanel(settings=qsettings)
    panel.set_project(p)

    io = SimulationIOProvider()
    io.set_digital_input("ELA01.DI01", False)
    panel.refresh_values(io, now_ms=1000)
    io.set_digital_input("ELA01.DI01", True)
    panel.refresh_values(io, now_ms=2000)

    panel._on_cell_double_clicked(0, _COL_TREND)
    dialog = panel._trend_dialogs[(KIND_PHYSICAL_DI, "ELA01.DI01")]
    assert dialog.chart._samples == [(1000, False), (2000, True)]


# ---- history lifecycle -------------------------------------------------------

def test_engine_clock_rollback_resets_history(qsettings):
    """A stopped-then-restarted engine's TimeProvider resets to 0 — every
    pre-restart timestamp would otherwise read as "in the future" relative
    to the new clock. Detected by the clock going backwards; history
    starts over rather than trying to reconcile two incomparable clocks."""
    _app()
    p = Project()
    watch.add_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01")
    panel = WatchPanel(settings=qsettings)
    panel.set_project(p)

    io = SimulationIOProvider()
    panel.refresh_values(io, now_ms=5000)
    panel.refresh_values(io, now_ms=6000)
    key = (KIND_PHYSICAL_DI, "ELA01.DI01")
    assert len(panel._history[key]) == 2

    panel.refresh_values(io, now_ms=0)  # engine restarted
    assert panel._history[key] == [(0, False)]

def test_removing_a_watched_row_also_clears_its_history(qsettings):
    _app()
    p = Project()
    watch.add_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01")
    panel = WatchPanel(settings=qsettings)
    panel.set_project(p)
    io = SimulationIOProvider()
    panel.refresh_values(io)

    panel.table.selectRow(0)
    panel._on_remove_clicked()
    assert panel._history == {}

def test_set_project_clears_history(qsettings):
    _app()
    p = Project()
    watch.add_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01")
    panel = WatchPanel(settings=qsettings)
    panel.set_project(p)
    io = SimulationIOProvider()
    panel.refresh_values(io)
    assert panel._history

    panel.set_project(p)  # e.g. an undo/redo swap
    assert panel._history == {}
