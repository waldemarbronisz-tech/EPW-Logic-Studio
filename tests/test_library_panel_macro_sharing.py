"""feat/macro-library-import-export — the export/import actions in
ui/panels/library.py. See test_macro_library.py for the underlying
core/macro_library.py logic in isolation."""
import json
import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from logic_studio.blocks import register_builtin_blocks
from logic_studio.core.macros import get_definitions, get_definition, macro_def_id
from logic_studio.core import macro_library
from logic_studio.ui.panels.library import TYPE_ID_ROLE

register_builtin_blocks()


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _close(window):
    window.is_dirty = False
    window.close()


def _block_items(window):
    from logic_studio.ui.canvas.block_item import BlockItem
    return [i for i in window.scene.items() if isinstance(i, BlockItem)]


def _make_window_with_macro(qsettings):
    from logic_studio.ui.main_window import MainWindow

    window = MainWindow(settings=qsettings)
    window.scene.clear()
    window.scene.add_block_from_library("logic.and", 0, 0)
    for item in _block_items(window):
        item.setSelected(True)
    window.scene.create_macro_from_selection("MojMakro")
    def_id = next(iter(get_definitions(window.project).keys()))
    return window, def_id


def _macro_tree_item(panel, def_id):
    type_id = f"macro.{def_id}"
    for i in range(panel._macro_root.childCount()):
        item = panel._macro_root.child(i)
        if item.data(0, TYPE_ID_ROLE) == type_id:
            return item
    return None


# ---- export --------------------------------------------------------------

def test_export_macro_writes_a_valid_bundle(qsettings, tmp_path, monkeypatch):
    _app()
    window, def_id = _make_window_with_macro(qsettings)
    path = str(tmp_path / "MojMakro.epwmacro")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (path, "")))

    window.library_panel._export_macro(def_id)

    with open(path, encoding="utf-8") as f:
        bundle = json.load(f)
    assert bundle["format"] == macro_library.FORMAT
    assert bundle["root_def_id"] == def_id
    assert bundle["definitions"][def_id]["name"] == "MojMakro"
    _close(window)

def test_export_macro_appends_extension_if_missing(qsettings, tmp_path, monkeypatch):
    _app()
    window, def_id = _make_window_with_macro(qsettings)
    path = str(tmp_path / "MojMakro")  # no extension
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (path, "")))

    window.library_panel._export_macro(def_id)

    assert (tmp_path / "MojMakro.epwmacro").exists()
    _close(window)

def test_export_macro_cancelled_dialog_writes_nothing(qsettings, tmp_path, monkeypatch):
    _app()
    window, def_id = _make_window_with_macro(qsettings)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))

    window.library_panel._export_macro(def_id)

    assert list(tmp_path.iterdir()) == []
    _close(window)


# ---- import ----------------------------------------------------------------

def test_import_macro_adds_a_new_definition_and_marks_dirty(qsettings, tmp_path, monkeypatch):
    _app()
    from logic_studio.ui.main_window import MainWindow
    window = MainWindow(settings=qsettings)
    window.scene.clear()
    window.is_dirty = False

    source_window, def_id = _make_window_with_macro(qsettings)
    path = str(tmp_path / "shared.epwmacro")
    macro_library.save_to_file(source_window.project, def_id, path)
    _close(source_window)

    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (path, "")))
    depth_before = len(window.project.undo_stack)

    window.library_panel._import_macro()

    assert len(get_definitions(window.project)) == 1
    assert window.is_dirty is True
    assert len(window.project.undo_stack) == depth_before + 1
    _close(window)

def test_import_macro_refreshes_the_library_tree(qsettings, tmp_path, monkeypatch):
    _app()
    from logic_studio.ui.main_window import MainWindow
    window = MainWindow(settings=qsettings)
    window.scene.clear()

    source_window, def_id = _make_window_with_macro(qsettings)
    path = str(tmp_path / "shared.epwmacro")
    macro_library.save_to_file(source_window.project, def_id, path)
    _close(source_window)

    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (path, "")))
    window.library_panel._import_macro()

    assert not window.library_panel._macro_root.isHidden()
    assert window.library_panel._macro_root.childCount() == 1
    assert window.library_panel._macro_root.child(0).text(0) == "MojMakro"
    _close(window)

def test_import_macro_cancelled_dialog_is_a_no_op(qsettings, monkeypatch):
    _app()
    from logic_studio.ui.main_window import MainWindow
    window = MainWindow(settings=qsettings)
    window.scene.clear()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("", "")))

    window.library_panel._import_macro()

    assert get_definitions(window.project) == {}
    _close(window)

def test_import_macro_invalid_file_shows_an_error_and_imports_nothing(qsettings, tmp_path, monkeypatch):
    _app()
    from logic_studio.ui.main_window import MainWindow
    window = MainWindow(settings=qsettings)
    window.scene.clear()

    bad_path = tmp_path / "not_a_macro.epwmacro"
    bad_path.write_text(json.dumps({"format": "SOMETHING_ELSE"}), encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(bad_path), "")))
    shown = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: shown.append(True)))
    depth_before = len(window.project.undo_stack)

    window.library_panel._import_macro()

    assert shown == [True]
    assert get_definitions(window.project) == {}
    assert len(window.project.undo_stack) == depth_before  # no wasted undo entry
    _close(window)

def test_import_macro_garbage_json_shows_an_error(qsettings, tmp_path, monkeypatch):
    _app()
    from logic_studio.ui.main_window import MainWindow
    window = MainWindow(settings=qsettings)
    window.scene.clear()

    bad_path = tmp_path / "garbage.epwmacro"
    bad_path.write_text("not even json{{{", encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(bad_path), "")))
    shown = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: shown.append(True)))

    window.library_panel._import_macro()

    assert shown == [True]
    _close(window)

def test_round_trip_import_into_a_different_project_places_a_second_instance(qsettings, tmp_path, monkeypatch):
    """End-to-end: export from one window, import into another, then
    place an instance of the imported macro from the library exactly
    like any other block."""
    _app()
    source_window, def_id = _make_window_with_macro(qsettings)
    path = str(tmp_path / "shared.epwmacro")
    macro_library.save_to_file(source_window.project, def_id, path)
    _close(source_window)

    from logic_studio.ui.main_window import MainWindow
    target_window = MainWindow(settings=qsettings)
    target_window.scene.clear()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (path, "")))
    target_window.library_panel._import_macro()

    new_def_id = next(iter(get_definitions(target_window.project).keys()))
    target_window.scene.add_block_from_library(f"macro.{new_def_id}", 0, 0)

    from logic_studio.blocks.macro_instance import MacroInstanceBlock
    instances = [b for b in target_window.project.blocks if isinstance(b, MacroInstanceBlock)]
    assert len(instances) == 1
    assert instances[0].display_name == "MojMakro"
    _close(target_window)


# ---- context menu ----------------------------------------------------------

def test_context_menu_export_action_present_for_a_macro_item(qsettings, monkeypatch):
    _app()
    window, def_id = _make_window_with_macro(qsettings)
    panel = window.library_panel
    item = _macro_tree_item(panel, def_id)
    assert item is not None
    pos = panel.tree.visualItemRect(item).center()

    captured = {}
    def fake_exec_context_menu(self, menu, global_pos):
        captured["actions"] = [a.text() for a in menu.actions()]
        return None
    monkeypatch.setattr(type(panel), "_exec_context_menu", fake_exec_context_menu)

    panel._on_tree_context_menu(pos)

    assert captured["actions"] == ["Eksportuj makroblok..."]
    _close(window)

def test_context_menu_triggers_export_when_its_action_is_chosen(qsettings, monkeypatch):
    _app()
    window, def_id = _make_window_with_macro(qsettings)
    panel = window.library_panel
    item = _macro_tree_item(panel, def_id)
    pos = panel.tree.visualItemRect(item).center()

    # simulate the user picking the (only) action in the menu
    monkeypatch.setattr(type(panel), "_exec_context_menu", lambda self, menu, global_pos: menu.actions()[0])
    exported = []
    monkeypatch.setattr(panel, "_export_macro", lambda d: exported.append(d))

    panel._on_tree_context_menu(pos)

    assert exported == [def_id]
    _close(window)

def test_context_menu_does_nothing_for_a_non_macro_item(qsettings, monkeypatch):
    _app()
    window, def_id = _make_window_with_macro(qsettings)
    panel = window.library_panel
    # any ordinary category item, e.g. the first child of a built-in category root
    cat_root = next(iter(panel._category_roots.values()))
    item = cat_root.child(0)
    pos = panel.tree.visualItemRect(item).center()

    called = []
    monkeypatch.setattr(type(panel), "_exec_context_menu", lambda self, menu, global_pos: called.append(True))

    panel._on_tree_context_menu(pos)

    assert called == []
    _close(window)
