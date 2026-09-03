"""feat/signal-crossref §2 — the "Sygnały" side panel (read-only)."""
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.core.project import Project
from logic_studio.core.device_model import DeviceModel
from logic_studio.ui.panels.signals import SignalsPanel, COL_SIGNAL, COL_STATE, COL_WRITES, COL_READS, COL_LABEL, SIGNAL_ID_ROLE


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


register_builtin_blocks()


def _di(address):
    b = BlockRegistry.create_block("input.di")
    b.properties["Address"] = address
    return b

def _do(address):
    b = BlockRegistry.create_block("output.do")
    b.properties["Address"] = address
    return b

def _row_of(panel, signal_id):
    for row in range(panel.table.rowCount()):
        if panel.table.item(row, COL_SIGNAL).data(SIGNAL_ID_ROLE) == signal_id:
            return row
    return None


# ---- population / empty state -----------------------------------------

def test_empty_project_shows_placeholder_not_a_table(qsettings):
    # isHidden() (not isVisible()) — a never-shown top-level widget's
    # descendants all report isVisible()==False regardless of their own
    # explicit setVisible() call; isHidden() tracks that explicit flag
    # directly, independent of ancestor visibility.
    _app()
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(Project())
    assert panel.table.isHidden() is True
    assert panel.empty_label.isHidden() is False
    assert "Brak sygnałów" in panel.empty_label.text()

def test_project_with_signals_shows_the_table(qsettings):
    _app()
    p = Project()
    p.add_block(_di("ELA01.DI01"))
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)
    assert panel.table.isHidden() is False
    assert panel.empty_label.isHidden() is True
    assert panel.table.rowCount() == 1

def test_columns_are_in_spec_order(qsettings):
    _app()
    panel = SignalsPanel(settings=qsettings)
    headers = [panel.table.horizontalHeaderItem(i).text() for i in range(panel.table.columnCount())]
    assert headers == ["Stan", "Sygnał", "Typ", "Etykieta", "Zapisuje", "Czyta"]

def test_row_shows_label_from_io_labels(qsettings):
    _app()
    p = Project()
    p.add_block(_di("ELA01.DI01"))
    DeviceModel.set_io_label(p, "ELA01.DI01", "Wyłącznik Q1 zamknięty")
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)

    row = _row_of(panel, "ELA01.DI01")
    assert panel.table.item(row, COL_LABEL).text() == "Wyłącznik Q1 zamknięty"

def test_physical_input_shows_urzadzenie_as_writer(qsettings):
    _app()
    p = Project()
    di = _di("ELA01.DI01")
    p.add_block(di)
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)

    row = _row_of(panel, "ELA01.DI01")
    assert panel.table.item(row, COL_WRITES).text() == "urządzenie"

def test_do_block_shows_its_short_id_as_writer(qsettings):
    _app()
    p = Project()
    do = _do("ADA01.DO01")
    p.add_block(do)
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)

    row = _row_of(panel, "ADA01.DO01")
    assert panel.table.item(row, COL_WRITES).text() == do.short_id

def test_multiple_writers_shown_as_comma_list(qsettings):
    p = Project()
    p.settings["internal_bits"] = [{"name": "X", "type": "BOOL", "retentive": False}]
    vo1 = BlockRegistry.create_block("virtual.output"); vo1.properties["Bit"] = "X"
    vo2 = BlockRegistry.create_block("virtual.output"); vo2.properties["Bit"] = "X"
    p.add_block(vo1)
    p.add_block(vo2)
    _app()
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)

    row = _row_of(panel, "M.X")
    text = panel.table.item(row, COL_WRITES).text()
    assert vo1.short_id in text and vo2.short_id in text

def test_status_icon_present_for_issue_rows_and_absent_for_clean_rows(qsettings):
    _app()
    p = Project()
    p.add_block(_di("ELA01.DI01"))  # clean
    ghost = BlockRegistry.create_block("virtual.input")
    ghost.properties["Bit"] = "GHOST"
    p.add_block(ghost)  # undefined -> error
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)

    clean_row = _row_of(panel, "ELA01.DI01")
    error_row = _row_of(panel, "GHOST")
    assert panel.table.item(clean_row, COL_STATE).icon().isNull()
    assert not panel.table.item(error_row, COL_STATE).icon().isNull()
    assert panel.table.item(error_row, COL_STATE).toolTip() != ""


# ---- filtering (§2.3) ---------------------------------------------------

def test_search_matches_signal_id(qsettings):
    _app()
    p = Project()
    p.add_block(_di("ELA01.DI01"))
    p.add_block(_di("ELA01.DI02"))
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)
    panel.search_edit.setText("DI01")

    assert panel.table.isRowHidden(_row_of(panel, "ELA01.DI01")) is False
    assert panel.table.isRowHidden(_row_of(panel, "ELA01.DI02")) is True

def test_search_matches_label(qsettings):
    _app()
    p = Project()
    p.add_block(_di("ELA01.DI01"))
    DeviceModel.set_io_label(p, "ELA01.DI01", "Blokada bramy")
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)
    panel.search_edit.setText("Blokada")
    assert panel.table.isRowHidden(_row_of(panel, "ELA01.DI01")) is False

def test_search_matches_reader_short_id(qsettings):
    _app()
    p = Project()
    di = _di("ELA01.DI01")
    p.add_block(di)
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)
    panel.search_edit.setText(di.short_id)
    assert panel.table.isRowHidden(_row_of(panel, "ELA01.DI01")) is False

def test_kind_filter_physical_hides_internal_signals(qsettings):
    _app()
    p = Project()
    p.add_block(_di("ELA01.DI01"))
    p.settings["internal_bits"] = [{"name": "X", "type": "BOOL", "retentive": False}]
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)
    panel.kind_filter_checks["Fizyczne"].setChecked(True)

    assert panel.table.isRowHidden(_row_of(panel, "ELA01.DI01")) is False
    assert panel.table.isRowHidden(_row_of(panel, "M.X")) is True

def test_only_issues_toggle_hides_clean_rows(qsettings):
    _app()
    p = Project()
    p.add_block(_di("ELA01.DI01"))  # clean
    ghost = BlockRegistry.create_block("virtual.input")
    ghost.properties["Bit"] = "GHOST"
    p.add_block(ghost)
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)
    panel.only_issues_check.setChecked(True)

    assert panel.table.isRowHidden(_row_of(panel, "ELA01.DI01")) is True
    assert panel.table.isRowHidden(_row_of(panel, "GHOST")) is False

def test_filter_state_persists_via_settings(qsettings):
    _app()
    panel = SignalsPanel(settings=qsettings)
    panel.kind_filter_checks["Systemowe"].setChecked(True)
    panel.only_issues_check.setChecked(True)

    panel2 = SignalsPanel(settings=qsettings)
    assert panel2._selected_kinds == {"Systemowe"}
    assert panel2.kind_filter_checks["Systemowe"].isChecked() is True
    assert panel2.only_issues_check.isChecked() is True

def test_multiple_kind_filters_can_be_selected_at_once(qsettings):
    """feat/signals-panel-narrow-filter: the old exclusive buttons could
    only ever show ONE category; the checklist menu is a real multi-
    select — Fizyczne + Systemowe together, Analogowe/Wewnętrzne still
    hidden."""
    _app()
    p = Project()
    p.add_block(_di("ELA01.DI01"))
    p.settings["internal_bits"] = [{"name": "X", "type": "BOOL", "retentive": False}]
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)

    panel.kind_filter_checks["Fizyczne"].setChecked(True)
    panel.kind_filter_checks["Systemowe"].setChecked(True)

    assert panel.table.isRowHidden(_row_of(panel, "ELA01.DI01")) is False
    assert panel.table.isRowHidden(_row_of(panel, "M.X")) is True

def test_kind_filter_button_label_reflects_selection(qsettings):
    """The button's own caption stays a near-constant width (never grows
    to embed a category name) — that's the whole point of this control —
    so state is checked via the tooltip and the "(n)" count, not a
    category name in the label itself."""
    _app()
    panel = SignalsPanel(settings=qsettings)
    assert panel.kind_filter_button.text() == "Filtruj"

    panel.kind_filter_checks["Fizyczne"].setChecked(True)
    assert panel.kind_filter_button.text() == "Filtruj (1)"
    assert "Fizyczne" in panel.kind_filter_button.toolTip()

    panel.kind_filter_checks["Systemowe"].setChecked(True)
    assert panel.kind_filter_button.text() == "Filtruj (2)"
    assert "Fizyczne" in panel.kind_filter_button.toolTip()
    assert "Systemowe" in panel.kind_filter_button.toolTip()

    panel.kind_filter_checks["Fizyczne"].setChecked(False)
    panel.kind_filter_checks["Systemowe"].setChecked(False)
    assert panel.kind_filter_button.text() == "Filtruj"

def test_checking_every_kind_is_equivalent_to_wszystkie(qsettings):
    """Selecting all 4 categories shows exactly what no selection shows —
    both mean "no restriction", so the caption collapses back to the
    unrestricted "Filtruj" and no filter is reported as applied (§5 CSV
    export's "Filtr zastosowany" comment line)."""
    _app()
    panel = SignalsPanel(settings=qsettings)
    for checkbox in panel.kind_filter_checks.values():
        checkbox.setChecked(True)

    assert panel.kind_filter_button.text() == "Filtruj"
    assert panel._is_filter_applied() is False


# ---- refresh debounce (§2.4) ---------------------------------------------

def test_set_project_rebuilds_immediately(qsettings):
    _app()
    p = Project()
    p.add_block(_di("ELA01.DI01"))
    panel = SignalsPanel(settings=qsettings)
    panel.set_project(p)
    assert panel.table.rowCount() == 1

def test_request_refresh_schedules_a_debounced_rebuild(qsettings):
    _app()
    panel = SignalsPanel(settings=qsettings)
    panel.project = Project()
    panel.project.add_block(_di("ELA01.DI01"))

    assert panel.table.rowCount() == 0  # not rebuilt yet
    panel.request_refresh()
    assert panel._refresh_timer.isActive() is True
    assert panel.table.rowCount() == 0  # still not rebuilt synchronously

def test_request_refresh_actually_rebuilds_after_the_debounce_window(qsettings):
    _app()
    panel = SignalsPanel(settings=qsettings)
    panel.project = Project()
    panel.project.add_block(_di("ELA01.DI01"))

    panel.request_refresh()
    QTest.qWait(350)  # > REFRESH_DEBOUNCE_MS
    assert panel.table.rowCount() == 1

def test_repeated_requests_coalesce_into_one_rebuild(qsettings):
    """A burst of edits must not cause a burst of rebuilds — only the
    LAST request_refresh() within the debounce window should fire."""
    _app()
    panel = SignalsPanel(settings=qsettings)
    panel.project = Project()

    rebuild_count = {"n": 0}
    original = panel._rebuild
    def counting_rebuild():
        rebuild_count["n"] += 1
        original()
    panel._rebuild = counting_rebuild

    for _ in range(5):
        panel.request_refresh()
        QTest.qWait(20)  # well under the 200ms window each time

    QTest.qWait(350)
    assert rebuild_count["n"] == 1
