"""feat/project-diff — MainWindow's File menu wiring
(_compare_with_saved_file()/_compare_two_projects()/_load_and_normalize()).
See test_project_diff.py/test_project_diff_dialog.py for the underlying
logic and view in isolation."""
import json
import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from logic_studio.blocks import register_builtin_blocks
from logic_studio.ui.project_diff_dialog import ProjectDiffDialog

register_builtin_blocks()


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _close(window):
    window.is_dirty = False
    window.close()


def _make_window(qsettings):
    from logic_studio.ui.main_window import MainWindow
    window = MainWindow(settings=qsettings)
    window.scene.clear()
    return window


# ---- _load_and_normalize() -------------------------------------------

def test_load_and_normalize_round_trips_a_saved_file(qsettings, tmp_path):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    path = str(tmp_path / "p.epwlogic")
    window.project.save_to_file(path)

    normalized = window._load_and_normalize(path)

    assert normalized["blocks"][0]["type_id"] == "logic.and"
    _close(window)

def test_load_and_normalize_raises_for_unreadable_file(qsettings, tmp_path):
    _app()
    window = _make_window(qsettings)
    bad_path = tmp_path / "garbage.epwlogic"
    bad_path.write_text("not json{{{", encoding="utf-8")

    with pytest.raises(Exception):
        window._load_and_normalize(str(bad_path))
    _close(window)


# ---- _compare_with_saved_file() ---------------------------------------

def test_compare_with_saved_file_shows_no_differences_right_after_saving(qsettings, tmp_path, monkeypatch):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    path = str(tmp_path / "p.epwlogic")
    window.project.save_to_file(path)
    window.current_file = path

    captured = {}
    def fake_init(self, comparison, base_label, target_label, parent=None):
        captured["comparison"] = comparison
        captured["labels"] = (base_label, target_label)
    monkeypatch.setattr(ProjectDiffDialog, "__init__", fake_init)
    monkeypatch.setattr(ProjectDiffDialog, "exec", lambda self: None)

    window._compare_with_saved_file()

    from logic_studio.core.project_diff import has_changes
    assert has_changes(captured["comparison"]) is False
    _close(window)

def test_compare_with_saved_file_detects_an_unsaved_change(qsettings, tmp_path, monkeypatch):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    path = str(tmp_path / "p.epwlogic")
    window.project.save_to_file(path)
    window.current_file = path

    # unsaved change: add another block AFTER saving
    window.scene.add_block_from_library("logic.or", 200, 0)

    captured = {}
    def fake_init(self, comparison, base_label, target_label, parent=None):
        captured["comparison"] = comparison
    monkeypatch.setattr(ProjectDiffDialog, "__init__", fake_init)
    monkeypatch.setattr(ProjectDiffDialog, "exec", lambda self: None)

    window._compare_with_saved_file()

    assert len(captured["comparison"]["blocks_added"]) == 1
    assert captured["comparison"]["blocks_added"][0]["type_id"] == "logic.or"
    _close(window)

def test_compare_with_saved_file_shows_a_message_when_never_saved(qsettings, monkeypatch):
    _app()
    window = _make_window(qsettings)
    assert window.current_file is None
    shown = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: shown.append(True)))

    window._compare_with_saved_file()

    assert shown == [True]
    _close(window)

def test_compare_with_saved_file_normalizes_away_schema_migration_noise(qsettings, tmp_path, monkeypatch):
    """A file saved under an OLDER schema_version must not show every
    migration-introduced settings key as spuriously "added" once loaded
    and re-serialized at the current version."""
    _app()
    window = _make_window(qsettings)
    path = str(tmp_path / "old.epwlogic")
    old_data = {
        "format": "EPW_LOGIC", "schema_version": 1,
        "settings": {"name": "Old project", "cycle_time_ms": 100},
        "blocks": [],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(old_data, f)

    # load it normally (runs the full migration chain) so the in-memory
    # project matches what current_file actually represents.
    window._open_project_headless(path)

    captured = {}
    def fake_init(self, comparison, base_label, target_label, parent=None):
        captured["comparison"] = comparison
    monkeypatch.setattr(ProjectDiffDialog, "__init__", fake_init)
    monkeypatch.setattr(ProjectDiffDialog, "exec", lambda self: None)

    window._compare_with_saved_file()

    from logic_studio.core.project_diff import has_changes
    assert has_changes(captured["comparison"]) is False
    _close(window)

def test_compare_with_saved_file_normalizes_to_top_level_first(qsettings, tmp_path, monkeypatch):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    from logic_studio.ui.canvas.block_item import BlockItem
    for item in window.scene.items():
        if isinstance(item, BlockItem):
            item.setSelected(True)
    window.scene.create_macro_from_selection("M")
    path = str(tmp_path / "p.epwlogic")
    window.project.save_to_file(path)
    window.current_file = path

    from logic_studio.blocks.macro_instance import MacroInstanceBlock
    instance = next(b for b in window.project.blocks if isinstance(b, MacroInstanceBlock))
    window.enter_macro_instance(instance)
    assert window.current_macro_def_id is not None

    monkeypatch.setattr(ProjectDiffDialog, "__init__", lambda self, *a, **k: None)
    monkeypatch.setattr(ProjectDiffDialog, "exec", lambda self: None)

    window._compare_with_saved_file()

    assert window.current_macro_def_id is None
    _close(window)


# ---- _compare_two_projects() -------------------------------------------

def test_compare_two_projects_shows_the_diff_between_two_files(qsettings, tmp_path, monkeypatch):
    """Both files come from the SAME lineage (one project, saved twice) —
    compare_projects() matches blocks by uuid, so two INDEPENDENTLY
    created projects would show everything as added/removed regardless
    of type_id overlap, which is correct behavior, just not what this
    test is exercising."""
    _app()
    source = _make_window(qsettings)
    source.scene.add_block_from_library("logic.and", 0, 0)
    path_a = str(tmp_path / "a.epwlogic")
    source.project.save_to_file(path_a)

    source.scene.add_block_from_library("logic.or", 200, 0)
    path_b = str(tmp_path / "b.epwlogic")
    source.project.save_to_file(path_b)
    _close(source)

    window = _make_window(qsettings)
    calls = iter([(path_a, ""), (path_b, "")])
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: next(calls)))
    captured = {}
    def fake_init(self, comparison, base_label, target_label, parent=None):
        captured["comparison"] = comparison
        captured["labels"] = (base_label, target_label)
    monkeypatch.setattr(ProjectDiffDialog, "__init__", fake_init)
    monkeypatch.setattr(ProjectDiffDialog, "exec", lambda self: None)

    window._compare_two_projects()

    assert len(captured["comparison"]["blocks_added"]) == 1
    assert captured["labels"] == ("a.epwlogic", "b.epwlogic")
    _close(window)

def test_compare_two_projects_cancelled_first_dialog_is_a_no_op(qsettings, monkeypatch):
    _app()
    window = _make_window(qsettings)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("", "")))
    called = []
    monkeypatch.setattr(ProjectDiffDialog, "exec", lambda self: called.append(True))

    window._compare_two_projects()

    assert called == []
    _close(window)

def test_compare_two_projects_cancelled_second_dialog_is_a_no_op(qsettings, tmp_path, monkeypatch):
    _app()
    window = _make_window(qsettings)
    src = _make_window(qsettings)
    path_a = str(tmp_path / "a.epwlogic")
    src.project.save_to_file(path_a)
    _close(src)

    calls = iter([(path_a, ""), ("", "")])
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: next(calls)))
    called = []
    monkeypatch.setattr(ProjectDiffDialog, "exec", lambda self: called.append(True))

    window._compare_two_projects()

    assert called == []
    _close(window)
