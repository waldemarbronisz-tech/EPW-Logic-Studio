"""feat/macro-blocks — breadcrumb navigation "into" a macro's own internal
blocks (MainWindow.enter_macro_instance()/_navigate_to_breadcrumb_index()).
See ARCHITECTURE.md §24.9 for the full design writeup, and
core/macros.py's own module-level note on the underlying mechanism."""
import pytest
import json
from PySide6.QtWidgets import QApplication

from logic_studio.blocks import register_builtin_blocks
from logic_studio.core.macros import get_definition, get_definitions
from logic_studio.blocks.macro_instance import MacroInstanceBlock
from logic_studio.ui.canvas.block_item import BlockItem

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
    return [i for i in window.scene.items() if isinstance(i, BlockItem)]


def _make_window_with_macro(qsettings):
    """A window with one AndGate collapsed into a macro named "MojMakro",
    wired between a DI and a DO — the standard fixture for every test
    below."""
    from logic_studio.ui.main_window import MainWindow

    window = MainWindow(settings=qsettings)
    window.scene.clear()
    window.scene.add_block_from_library("input.di", 0, 0)
    window.scene.add_block_from_library("logic.and", 200, 0)
    window.scene.add_block_from_library("output.do", 400, 0)
    di, gate, do = window.project.blocks
    di.outputs[0].connect(gate.inputs[0])
    gate.outputs[0].connect(do.inputs[0])

    for item in _block_items(window):
        if item.logic_block is gate:
            item.setSelected(True)
    window.scene.create_macro_from_selection("MojMakro")

    instance = next(b for b in window.project.blocks if isinstance(b, MacroInstanceBlock))
    return window, di, do, instance


def _instance_item(window, instance):
    return next(i for i in _block_items(window) if i.logic_block is instance)


# ---- entering ----------------------------------------------------------

def test_entering_a_macro_swaps_the_canvas_to_its_internals(qsettings):
    _app()
    window, di, do, instance = _make_window_with_macro(qsettings)

    window.enter_macro_instance(instance)

    assert window.current_macro_def_id == instance.def_id
    type_ids = {b.type_id for b in window.project.blocks}
    assert type_ids == {"logic.and"}
    _close(window)

def test_entering_a_macro_shows_the_breadcrumb(qsettings):
    _app()
    window, di, do, instance = _make_window_with_macro(qsettings)

    window.enter_macro_instance(instance)

    assert not window.breadcrumb_bar.isHidden()
    _close(window)

def test_double_click_on_a_macro_block_enters_it(qsettings):
    _app()
    window, di, do, instance = _make_window_with_macro(qsettings)
    item = _instance_item(window, instance)

    item.mouseDoubleClickEvent(_FakeDoubleClickEvent())

    assert window.current_macro_def_id == instance.def_id
    _close(window)

def test_entering_a_macro_with_a_deleted_definition_is_a_no_op(qsettings):
    from logic_studio.core.macros import delete_definition
    _app()
    window, di, do, instance = _make_window_with_macro(qsettings)
    before = list(window.project.blocks)
    delete_definition(window.project, instance.def_id)

    window.enter_macro_instance(instance)

    assert window.current_macro_def_id is None
    assert window.project.blocks == before
    _close(window)

def test_entering_a_macro_stops_the_simulation(qsettings):
    _app()
    window, di, do, instance = _make_window_with_macro(qsettings)
    window.sim_timer.start(50)

    window.enter_macro_instance(instance)

    assert not window.sim_timer.isActive()
    _close(window)


class _FakeDoubleClickEvent:
    def accept(self):
        pass


# ---- editing + exiting commits back into the definition --------------------

def test_adding_a_block_inside_a_macro_and_exiting_commits_it(qsettings):
    _app()
    window, di, do, instance = _make_window_with_macro(qsettings)
    def_id = instance.def_id

    window.enter_macro_instance(instance)
    window.scene.add_block_from_library("logic.not", 0, 200)
    assert len(window.project.blocks) == 2  # original AND + new NOT

    window._navigate_to_breadcrumb_index(0)

    assert window.current_macro_def_id is None
    assert set(window.project.blocks) == {di, instance, do}
    definition = get_definition(window.project, def_id)
    type_ids = {b["type_id"] for b in definition["blocks"]}
    assert type_ids == {"logic.and", "logic.not"}
    _close(window)

def test_exiting_restores_the_exact_parent_blocks(qsettings):
    _app()
    window, di, do, instance = _make_window_with_macro(qsettings)
    root_blocks = list(window.project.blocks)

    window.enter_macro_instance(instance)
    window._navigate_to_breadcrumb_index(0)

    assert window.project.blocks == root_blocks
    assert window.breadcrumb_bar.isHidden()
    _close(window)

def test_boundary_pins_are_frozen_across_an_edit_session(qsettings):
    """v1 scope: input_pins/output_pins never change while editing a
    macro's internals directly, even if a block is added."""
    _app()
    window, di, do, instance = _make_window_with_macro(qsettings)
    def_id = instance.def_id
    original = get_definition(window.project, def_id)

    window.enter_macro_instance(instance)
    window.scene.add_block_from_library("logic.not", 0, 200)
    window._navigate_to_breadcrumb_index(0)

    updated = get_definition(window.project, def_id)
    assert updated["input_pins"] == original["input_pins"]
    assert updated["output_pins"] == original["output_pins"]
    assert len(instance.inputs) == 1
    assert len(instance.outputs) == 1
    _close(window)

def test_deleting_the_only_block_and_exiting_commits_an_empty_definition(qsettings):
    _app()
    window, di, do, instance = _make_window_with_macro(qsettings)
    def_id = instance.def_id

    window.enter_macro_instance(instance)
    for item in _block_items(window):
        item.setSelected(True)
    window.scene.delete_selected_items()
    assert window.project.blocks == []

    window._navigate_to_breadcrumb_index(0)

    definition = get_definition(window.project, def_id)
    assert definition["blocks"] == []
    _close(window)


# ---- nested navigation -------------------------------------------------

def test_nested_macro_breadcrumb_and_exit_commits_both_levels(qsettings):
    _app()
    window, di, do, outer_instance = _make_window_with_macro(qsettings)
    outer_def_id = outer_instance.def_id

    window.enter_macro_instance(outer_instance)
    # Build a second, INNER macro from the AND gate now visible inside the
    # outer one's own edit view.
    for item in _block_items(window):
        item.setSelected(True)
    window.scene.create_macro_from_selection("Wewnetrzny")
    inner_instance = next(b for b in window.project.blocks if isinstance(b, MacroInstanceBlock))
    inner_def_id = inner_instance.def_id

    window.enter_macro_instance(inner_instance)
    assert window.current_macro_def_id == inner_def_id
    from PySide6.QtWidgets import QPushButton, QLabel
    button_texts = [w.text() for w in window.breadcrumb_bar.findChildren(QPushButton)]
    assert button_texts == ["Główny", "MojMakro"]
    current_labels = [w.text() for w in window.breadcrumb_bar.findChildren(QLabel) if "bold" in w.styleSheet()]
    assert current_labels == ["Wewnetrzny"]

    window._navigate_to_breadcrumb_index(0)

    assert window.current_macro_def_id is None
    assert set(window.project.blocks) == {di, outer_instance, do}
    outer_def = get_definition(window.project, outer_def_id)
    assert len(outer_def["blocks"]) == 1
    assert outer_def["blocks"][0]["type_id"] == f"macro.{inner_def_id}"
    _close(window)


# ---- cross-cutting operations normalize to the top level first -----------

def test_save_auto_exits_and_saves_the_true_top_level(qsettings, tmp_path):
    _app()
    window, di, do, instance = _make_window_with_macro(qsettings)
    def_id = instance.def_id
    window.current_file = str(tmp_path / "test.epwlogic")

    window.enter_macro_instance(instance)
    window.scene.add_block_from_library("logic.not", 0, 200)

    window._save_project()

    assert window.current_macro_def_id is None
    with open(window.current_file, encoding="utf-8") as f:
        saved = json.load(f)
    top_type_ids = {b["type_id"] for b in saved["blocks"]}
    assert top_type_ids == {"input.di", "output.do", f"macro.{def_id}"}
    saved_definition = saved["settings"]["macro_definitions"][def_id]
    assert {b["type_id"] for b in saved_definition["blocks"]} == {"logic.and", "logic.not"}
    _close(window)

def test_compile_auto_exits_the_macro_editing_view(qsettings):
    _app()
    window, di, do, instance = _make_window_with_macro(qsettings)

    window.enter_macro_instance(instance)
    window.compile_project()

    assert window.current_macro_def_id is None
    assert window.breadcrumb_bar.isHidden()
    _close(window)

def test_undo_auto_exits_the_macro_editing_view(qsettings):
    _app()
    window, di, do, instance = _make_window_with_macro(qsettings)

    window.enter_macro_instance(instance)
    window._undo()

    assert window.current_macro_def_id is None
    _close(window)

def test_redo_auto_exits_the_macro_editing_view(qsettings):
    _app()
    window, di, do, instance = _make_window_with_macro(qsettings)

    window.enter_macro_instance(instance)
    window._redo()

    assert window.current_macro_def_id is None
    _close(window)

def test_new_project_resets_macro_nav_without_committing(qsettings):
    _app()
    window, di, do, instance = _make_window_with_macro(qsettings)

    window.enter_macro_instance(instance)
    window.scene.add_block_from_library("logic.not", 0, 200)

    window.is_dirty = False  # skip the unsaved-changes modal prompt
    window._new_project()

    assert window.current_macro_def_id is None
    assert window.breadcrumb_bar.isHidden()
    assert window.project.blocks == []
    _close(window)
