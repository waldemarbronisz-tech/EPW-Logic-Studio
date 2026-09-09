"""fix/wire-labels-and-project-integrity §A5 — logic_studio/ui/panels/labels.py."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from logic_studio.blocks import register_builtin_blocks
from logic_studio.core.wire import Wire
from logic_studio.ui.panels.labels import LabelsPanel, _COL_LABEL, _COL_TYPE, _COL_SOURCE, _COL_RECEIVERS, _COL_STATE

register_builtin_blocks()


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_window(qsettings):
    from logic_studio.ui.main_window import MainWindow
    window = MainWindow(settings=qsettings)
    window.scene.clear()
    return window


def _close(window):
    window.is_dirty = False
    window.close()


def test_empty_project_shows_placeholder(qsettings):
    _app()
    panel = LabelsPanel(settings=qsettings)
    assert panel.table.isHidden() is True
    assert panel.empty_label.isHidden() is False
    panel.deleteLater()

def test_no_labels_shows_placeholder_even_with_a_project(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    panel = LabelsPanel(settings=qsettings)
    panel.set_project(window.project)

    assert panel.table.rowCount() == 0
    assert panel.empty_label.isHidden() is False
    panel.deleteLater()
    _close(window)

def test_one_labeled_network_produces_one_row(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    window.scene.add_block_from_library("output.do", 400, 0)
    di, do = window.project.blocks
    w1 = Wire()
    w1.source_pin = di.outputs[0].uuid
    w1.free_end_dest = {"x": 100.0, "y": 0.0}
    w1.label = "Cmd"
    window.project.add_wire(w1)
    w2 = Wire()
    w2.dest_pin = do.inputs[0].uuid
    w2.free_end_source = {"x": 300.0, "y": 0.0}
    w2.label = "Cmd"
    window.project.add_wire(w2)

    panel = LabelsPanel(settings=qsettings)
    panel.set_project(window.project)

    assert panel.table.rowCount() == 1
    assert panel.table.item(0, _COL_LABEL).text() == "Cmd"
    assert panel.table.item(0, _COL_SOURCE).text() == di.short_id
    assert panel.table.item(0, _COL_RECEIVERS).text() == "1"
    assert panel.table.item(0, _COL_STATE).text() == "OK"
    assert panel.empty_label.isHidden() is True
    panel.deleteLater()
    _close(window)

def test_error_row_is_flagged(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("output.do", 0, 0)
    do = window.project.blocks[0]
    w = Wire()
    w.dest_pin = do.inputs[0].uuid
    w.free_end_source = {"x": 0.0, "y": 0.0}
    w.label = "NoSource"
    window.project.add_wire(w)

    panel = LabelsPanel(settings=qsettings)
    panel.set_project(window.project)

    assert panel.table.item(0, _COL_STATE).text() == "Błąd"
    assert panel.table.item(0, _COL_SOURCE).text() == "-"
    panel.deleteLater()
    _close(window)

def test_double_click_source_column_jumps_to_the_source_block(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    di = window.project.blocks[0]
    w = Wire()
    w.source_pin = di.outputs[0].uuid
    w.free_end_dest = {"x": 100.0, "y": 0.0}
    w.label = "Cmd"
    window.project.add_wire(w)

    panel = LabelsPanel(settings=qsettings)
    panel.setParent(window)  # so panel.window() resolves to `window`
    panel.set_project(window.project)

    panel._on_cell_double_clicked(0, _COL_SOURCE)

    from logic_studio.ui.canvas.block_item import BlockItem
    di_item = next(i for i in window.scene.items() if isinstance(i, BlockItem) and i.logic_block is di)
    assert di_item.isSelected()
    panel.deleteLater()
    _close(window)

def test_double_click_label_column_renames_every_matching_wire(qsettings, monkeypatch):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    window.scene.add_block_from_library("output.do", 400, 0)
    di, do = window.project.blocks
    w1 = Wire()
    w1.source_pin = di.outputs[0].uuid
    w1.free_end_dest = {"x": 100.0, "y": 0.0}
    w1.label = "OldName"
    window.project.add_wire(w1)
    w2 = Wire()
    w2.dest_pin = do.inputs[0].uuid
    w2.free_end_source = {"x": 300.0, "y": 0.0}
    w2.label = "OldName"
    window.project.add_wire(w2)

    panel = LabelsPanel(settings=qsettings)
    panel.setParent(window)
    panel.set_project(window.project)

    import logic_studio.ui.label_dialog as label_dialog_module
    monkeypatch.setattr(label_dialog_module, "prompt_for_label", lambda *a, **k: ("NewName", None))

    panel._on_cell_double_clicked(0, _COL_LABEL)

    assert w1.label == "NewName"
    assert w2.label == "NewName"
    assert panel.table.item(0, _COL_LABEL).text() == "NewName"
    panel.deleteLater()
    _close(window)

def test_renaming_to_the_same_name_is_a_no_op(qsettings, monkeypatch):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    di = window.project.blocks[0]
    w = Wire()
    w.source_pin = di.outputs[0].uuid
    w.free_end_dest = {"x": 100.0, "y": 0.0}
    w.label = "SameName"
    window.project.add_wire(w)

    panel = LabelsPanel(settings=qsettings)
    panel.setParent(window)
    panel.set_project(window.project)

    import logic_studio.ui.label_dialog as label_dialog_module
    monkeypatch.setattr(label_dialog_module, "prompt_for_label", lambda *a, **k: ("SameName", None))
    undo_depth_before = len(window.project.undo_stack)

    panel._on_cell_double_clicked(0, _COL_LABEL)

    assert len(window.project.undo_stack) == undo_depth_before  # no push_state()
    panel.deleteLater()
    _close(window)
