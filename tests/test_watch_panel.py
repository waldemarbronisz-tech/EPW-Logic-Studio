"""feat/signal-watch — ui/panels/watch.py's WatchPanel, built on
core/watch.py. Table + SignalPickerDialog-driven add + sparkline trend.
"""
from PySide6.QtWidgets import QApplication, QDialog

from logic_studio.core.project import Project
from logic_studio.core.device_model import DeviceModel
from logic_studio.core import watch
from logic_studio.core.crossref import (
    KIND_PHYSICAL_DI, KIND_PHYSICAL_DO, KIND_ANALOG_IN, KIND_SYSTEM,
)
from logic_studio.engine.io_provider import SimulationIOProvider
from logic_studio.ui.panels.watch import WatchPanel, _COL_KIND, _COL_ID, _COL_DESC, _COL_VALUE, _COL_TREND


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
