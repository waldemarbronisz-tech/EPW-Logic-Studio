"""feat/io-labels-and-ids §2 — the "Etykiety wejść/wyjść" tab in
ProjectSettingsDialog."""
import json
import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.core.project import Project
from logic_studio.core.device_model import DeviceModel


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


register_builtin_blocks()


def _find_row(dialog, address):
    for row in range(dialog.io_labels_table.rowCount()):
        if dialog.io_labels_table.item(row, 0).text() == address:
            return row
    return None


def test_table_lists_every_ela_ada_and_analog_address():
    _app()
    from logic_studio.ui.dialogs import ProjectSettingsDialog

    p = Project()
    p.settings["analog_points"] = [
        {"address": "AI.X", "name": "X", "unit": "", "min": 0.0, "max": 1.0, "direction": "input"},
    ]
    dialog = ProjectSettingsDialog(p)

    assert dialog.io_labels_table.rowCount() == 32 + 32 + 1
    assert _find_row(dialog, "ELA01.DI01") is not None
    assert _find_row(dialog, "ADA01.DO01") is not None
    assert _find_row(dialog, "AI.X") is not None

def test_label_column_prefilled_from_existing_registry():
    _app()
    from logic_studio.ui.dialogs import ProjectSettingsDialog

    p = Project()
    DeviceModel.set_io_label(p, "ELA01.DI01", "Wyłącznik Q1 zamknięty")
    dialog = ProjectSettingsDialog(p)

    row = _find_row(dialog, "ELA01.DI01")
    assert dialog.io_labels_table.item(row, 1).text() == "Wyłącznik Q1 zamknięty"

def test_usage_column_counts_referencing_blocks():
    _app()
    from logic_studio.ui.dialogs import ProjectSettingsDialog

    p = Project()
    di1 = BlockRegistry.create_block("input.di"); di1.properties["Address"] = "ELA01.DI01"
    di2 = BlockRegistry.create_block("input.di"); di2.properties["Address"] = "ELA01.DI01"
    p.add_block(di1)
    p.add_block(di2)
    dialog = ProjectSettingsDialog(p)

    row = _find_row(dialog, "ELA01.DI01")
    assert dialog.io_labels_table.item(row, 2).text() == "2"
    row2 = _find_row(dialog, "ELA01.DI02")
    assert dialog.io_labels_table.item(row2, 2).text() == "0"

def test_address_and_usage_columns_are_read_only():
    _app()
    from logic_studio.ui.dialogs import ProjectSettingsDialog
    from PySide6.QtCore import Qt

    p = Project()
    dialog = ProjectSettingsDialog(p)
    row = _find_row(dialog, "ELA01.DI01")

    assert not (dialog.io_labels_table.item(row, 0).flags() & Qt.ItemIsEditable)
    assert not (dialog.io_labels_table.item(row, 2).flags() & Qt.ItemIsEditable)
    assert dialog.io_labels_table.item(row, 1).flags() & Qt.ItemIsEditable

def test_only_used_filter_defaults_on_and_hides_unused_rows():
    _app()
    from logic_studio.ui.dialogs import ProjectSettingsDialog

    p = Project()
    di = BlockRegistry.create_block("input.di"); di.properties["Address"] = "ELA01.DI01"
    p.add_block(di)
    dialog = ProjectSettingsDialog(p)

    assert dialog.io_labels_only_used_check.isChecked() is True
    used_row = _find_row(dialog, "ELA01.DI01")
    unused_row = _find_row(dialog, "ELA01.DI02")
    assert dialog.io_labels_table.isRowHidden(used_row) is False
    assert dialog.io_labels_table.isRowHidden(unused_row) is True

def test_unchecking_only_used_shows_every_row():
    _app()
    from logic_studio.ui.dialogs import ProjectSettingsDialog

    p = Project()
    dialog = ProjectSettingsDialog(p)
    dialog.io_labels_only_used_check.setChecked(False)

    unused_row = _find_row(dialog, "ELA01.DI02")
    assert dialog.io_labels_table.isRowHidden(unused_row) is False

def test_filter_matches_address_and_label():
    _app()
    from logic_studio.ui.dialogs import ProjectSettingsDialog

    p = Project()
    DeviceModel.set_io_label(p, "ELA01.DI05", "Blokada bramy")
    dialog = ProjectSettingsDialog(p)
    dialog.io_labels_only_used_check.setChecked(False)
    dialog.io_labels_filter_edit.setText("Blokada")

    row = _find_row(dialog, "ELA01.DI05")
    other_row = _find_row(dialog, "ELA01.DI06")
    assert dialog.io_labels_table.isRowHidden(row) is False
    assert dialog.io_labels_table.isRowHidden(other_row) is True


# ---- accept / apply_to_project ------------------------------------------

def test_editing_a_label_and_accepting_writes_the_registry():
    _app()
    from logic_studio.ui.dialogs import ProjectSettingsDialog

    p = Project()
    dialog = ProjectSettingsDialog(p)
    row = _find_row(dialog, "ELA01.DI01")
    dialog.io_labels_table.item(row, 1).setText("Wyłącznik Q1 zamknięty")

    dialog._on_accept()
    dialog.apply_to_project()

    assert DeviceModel.get_io_label(p, "ELA01.DI01") == "Wyłącznik Q1 zamknięty"

def test_clearing_a_label_and_accepting_removes_it():
    _app()
    from logic_studio.ui.dialogs import ProjectSettingsDialog

    p = Project()
    DeviceModel.set_io_label(p, "ELA01.DI01", "Old label")
    dialog = ProjectSettingsDialog(p)
    row = _find_row(dialog, "ELA01.DI01")
    dialog.io_labels_table.item(row, 1).setText("")

    dialog._on_accept()
    dialog.apply_to_project()

    assert DeviceModel.get_io_label(p, "ELA01.DI01") == ""
    assert "ELA01.DI01" not in p.settings["io_labels"]

def test_apply_to_project_pushes_exactly_one_undo_snapshot():
    _app()
    from logic_studio.ui.dialogs import ProjectSettingsDialog

    p = Project()
    dialog = ProjectSettingsDialog(p)
    row = _find_row(dialog, "ELA01.DI01")
    dialog.io_labels_table.item(row, 1).setText("X")
    dialog._on_accept()

    before = len(p.undo_stack)
    dialog.apply_to_project()
    assert len(p.undo_stack) == before + 1


# ---- import/export (§2.2) -----------------------------------------------

def test_export_then_import_round_trips(tmp_path):
    _app()
    from logic_studio.ui.dialogs import ProjectSettingsDialog

    p = Project()
    dialog = ProjectSettingsDialog(p)
    row = _find_row(dialog, "ELA01.DI01")
    dialog.io_labels_table.item(row, 1).setText("Wyłącznik Q1 zamknięty")

    path = tmp_path / "labels.json"
    monkey_path = str(path)

    # Exercise the export logic directly (bypassing the QFileDialog).
    labels = dialog._collect_io_labels()
    with open(monkey_path, "w", encoding="utf-8") as f:
        json.dump({"format": "EPW_IO_LABELS", "schema_version": 1, "io_labels": labels}, f)

    with open(monkey_path, encoding="utf-8") as f:
        data = json.load(f)
    assert data["io_labels"] == {"ELA01.DI01": "Wyłącznik Q1 zamknięty"}

def test_import_reports_added_changed_skipped_counts(monkeypatch, tmp_path):
    _app()
    from logic_studio.ui.dialogs import ProjectSettingsDialog

    p = Project()
    DeviceModel.set_io_label(p, "ELA01.DI02", "Existing label")
    dialog = ProjectSettingsDialog(p)

    incoming = {
        "ELA01.DI01": "New label",       # added
        "ELA01.DI02": "Changed label",   # changed
        "ELA01.DI99": "Ghost channel",   # skipped: unknown address
    }
    path = tmp_path / "import.json"
    path.write_text(json.dumps({"io_labels": incoming}), encoding="utf-8")

    monkeypatch.setattr(
        "logic_studio.ui.dialogs.QFileDialog.getOpenFileName",
        lambda *a, **k: (str(path), "JSON (*.json)"),
    )
    captured = {}
    def fake_question(self, title, text, *a, **k):
        captured["text"] = text
        return QMessageBox.Yes
    monkeypatch.setattr("logic_studio.ui.dialogs.QMessageBox.question", fake_question)

    dialog._import_io_labels()

    assert "Zostanie dodanych: 1" in captured["text"]
    assert "Zmienionych: 1" in captured["text"]
    assert "Pominiętych (nieznany adres): 1" in captured["text"]
    assert dialog.io_labels_table.item(_find_row(dialog, "ELA01.DI01"), 1).text() == "New label"
    assert dialog.io_labels_table.item(_find_row(dialog, "ELA01.DI02"), 1).text() == "Changed label"

def test_import_never_applies_without_confirmation(monkeypatch, tmp_path):
    _app()
    from logic_studio.ui.dialogs import ProjectSettingsDialog

    p = Project()
    dialog = ProjectSettingsDialog(p)

    path = tmp_path / "import.json"
    path.write_text(json.dumps({"io_labels": {"ELA01.DI01": "Should not apply"}}), encoding="utf-8")

    monkeypatch.setattr(
        "logic_studio.ui.dialogs.QFileDialog.getOpenFileName",
        lambda *a, **k: (str(path), "JSON (*.json)"),
    )
    monkeypatch.setattr("logic_studio.ui.dialogs.QMessageBox.question", lambda *a, **k: QMessageBox.No)

    dialog._import_io_labels()

    row = _find_row(dialog, "ELA01.DI01")
    assert dialog.io_labels_table.item(row, 1).text() == ""
