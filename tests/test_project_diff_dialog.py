"""feat/project-diff — ui/project_diff_dialog.py's ProjectDiffDialog.
Qt-thin: never touches core/project_diff.py's own comparison logic
beyond rendering whatever compare_projects() already produced — see
test_project_diff.py for that logic in isolation."""
import pytest
from PySide6.QtWidgets import QApplication

from logic_studio.core.project_diff import compare_projects
from logic_studio.ui.project_diff_dialog import ProjectDiffDialog


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _state(blocks, settings=None):
    return {"format": "EPW_LOGIC", "schema_version": 8, "settings": settings or {"name": "P"}, "blocks": blocks}


def _block(uuid, **extra):
    d = {
        "uuid": uuid, "short_id": f"g{uuid}", "type_id": "logic.and", "display_name": "AND",
        "enabled": True, "color": "#00557f", "execution_priority": 1,
        "position": {"x": 0.0, "y": 0.0}, "size": {"width": 60.0, "height": 60.0},
        "properties": {"Address": "", "Tag": "", "Comment": ""}, "inputs": [], "outputs": [],
    }
    d.update(extra)
    return d


def _empty_comparison():
    return {"blocks_added": [], "blocks_removed": [], "blocks_changed": [], "settings_changes": []}


def test_header_shows_labels_and_summary():
    _app()
    dialog = ProjectDiffDialog(_empty_comparison(), "old.epwlogic", "new.epwlogic")
    header_text = dialog.layout().itemAt(0).widget().text()
    assert "old.epwlogic" in header_text
    assert "new.epwlogic" in header_text

def test_no_differences_shows_a_single_placeholder_row():
    _app()
    dialog = ProjectDiffDialog(_empty_comparison(), "A", "B")
    assert dialog.tree.topLevelItemCount() == 1
    assert dialog.tree.topLevelItem(0).text(0) == "Brak różnic"

def test_added_and_removed_blocks_get_their_own_sections():
    _app()
    base = _state([_block("a")])
    target = _state([_block("a"), _block("b")])
    comparison = compare_projects(base, target)
    dialog = ProjectDiffDialog(comparison, "A", "B")

    labels = [dialog.tree.topLevelItem(i).text(0) for i in range(dialog.tree.topLevelItemCount())]
    assert any(l.startswith("Dodane bloki") for l in labels)
    added_root = next(dialog.tree.topLevelItem(i) for i in range(dialog.tree.topLevelItemCount()) if labels[i].startswith("Dodane"))
    assert added_root.childCount() == 1
    assert "logic.and" in added_root.child(0).text(0)

def test_changed_block_shows_field_changes_as_children():
    _app()
    base = _state([_block("a", display_name="AND")])
    target = _state([_block("a", display_name="MyGate")])
    comparison = compare_projects(base, target)
    dialog = ProjectDiffDialog(comparison, "A", "B")

    root = dialog.tree.topLevelItem(0)
    assert root.text(0).startswith("Zmienione bloki")
    block_item = root.child(0)
    assert "ga" in block_item.text(0) or "MyGate" in block_item.text(0)
    field_texts = [block_item.child(i).text(0) for i in range(block_item.childCount())]
    assert any("display_name" in t and "AND" in t and "MyGate" in t for t in field_texts)

def test_moved_block_shows_a_moved_row():
    _app()
    base = _state([_block("a", position={"x": 0.0, "y": 0.0})])
    target = _state([_block("a", position={"x": 50.0, "y": 50.0})])
    comparison = compare_projects(base, target)
    dialog = ProjectDiffDialog(comparison, "A", "B")

    block_item = dialog.tree.topLevelItem(0).child(0)
    field_texts = [block_item.child(i).text(0) for i in range(block_item.childCount())]
    assert "Przesunięty na kanwie" in field_texts

def test_connection_change_shown_under_its_block():
    _app()
    base = _block("a", inputs=[{"uuid": "p1", "name": "In1", "direction": "input", "data_type": "BOOL", "connections": []}])
    target = _block("a", inputs=[{"uuid": "p1", "name": "In1", "direction": "input", "data_type": "BOOL", "connections": ["x"]}])
    comparison = compare_projects(_state([base]), _state([target]))
    dialog = ProjectDiffDialog(comparison, "A", "B")

    block_item = dialog.tree.topLevelItem(0).child(0)
    field_texts = [block_item.child(i).text(0) for i in range(block_item.childCount())]
    assert any("In1" in t and "nowe połączenie" in t for t in field_texts)

def test_settings_changes_section():
    _app()
    base = _state([], settings={"name": "Old"})
    target = _state([], settings={"name": "New"})
    comparison = compare_projects(base, target)
    dialog = ProjectDiffDialog(comparison, "A", "B")

    root = dialog.tree.topLevelItem(0)
    assert root.text(0).startswith("Zmiany ustawień")
    assert "name" in root.child(0).text(0)

def test_all_sections_together_when_everything_changed():
    _app()
    base = _state([_block("a"), _block("b", display_name="X")], settings={"name": "Old"})
    target = _state([_block("a"), _block("b", display_name="Y"), _block("c")], settings={"name": "New"})
    comparison = compare_projects(base, target)
    dialog = ProjectDiffDialog(comparison, "A", "B")
    labels = [dialog.tree.topLevelItem(i).text(0) for i in range(dialog.tree.topLevelItemCount())]
    assert any(l.startswith("Dodane") for l in labels)
    assert any(l.startswith("Zmienione") for l in labels)
    assert any(l.startswith("Zmiany ustawień") for l in labels)
