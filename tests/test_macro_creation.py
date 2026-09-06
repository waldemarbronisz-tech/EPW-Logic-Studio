"""feat/macro-blocks — LogicScene.create_macro_from_selection() and the
add_block_from_library() macro special-case (ui/canvas/scene.py). See
test_macros.py/test_macro_instance.py for the Qt-free logic these build on.
"""
import pytest
from PySide6.QtWidgets import QApplication

from logic_studio.blocks import register_builtin_blocks
from logic_studio.core.macros import get_definition, get_definitions

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


def _block_items(window):
    from logic_studio.ui.canvas.block_item import BlockItem
    return [i for i in window.scene.items() if isinstance(i, BlockItem)]


def _select_all(window):
    for item in _block_items(window):
        item.setSelected(True)


# ---- create_macro_from_selection() -----------------------------------------

def test_create_macro_replaces_selection_with_one_instance(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    window.scene.add_block_from_library("logic.and", 200, 0)
    window.scene.add_block_from_library("output.do", 400, 0)
    di, gate, do = window.project.blocks
    assert di.outputs[0].connect(gate.inputs[0])
    assert gate.outputs[0].connect(do.inputs[0])

    for item in _block_items(window):
        if item.logic_block is gate:
            item.setSelected(True)

    assert window.scene.create_macro_from_selection("MojGate") is True

    from logic_studio.blocks.macro_instance import MacroInstanceBlock
    remaining = window.project.blocks
    assert len(remaining) == 3  # di, do, and the new instance (gate is gone)
    instance = next(b for b in remaining if isinstance(b, MacroInstanceBlock))
    assert instance.display_name == "MojGate"
    assert len(instance.inputs) == 1
    assert len(instance.outputs) == 1

    definitions = get_definitions(window.project)
    assert len(definitions) == 1
    _close(window)

def test_create_macro_rewires_external_connections_onto_the_instance(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    window.scene.add_block_from_library("logic.and", 200, 0)
    window.scene.add_block_from_library("output.do", 400, 0)
    di, gate, do = window.project.blocks
    assert di.outputs[0].connect(gate.inputs[0])
    assert gate.outputs[0].connect(do.inputs[0])

    for item in _block_items(window):
        if item.logic_block is gate:
            item.setSelected(True)
    window.scene.create_macro_from_selection("MojGate")

    from logic_studio.blocks.macro_instance import MacroInstanceBlock
    instance = next(b for b in window.project.blocks if isinstance(b, MacroInstanceBlock))

    assert instance.inputs[0].uuid in di.outputs[0].connections
    assert di.outputs[0].uuid in instance.inputs[0].connections
    assert instance.outputs[0].uuid in do.inputs[0].connections
    assert do.inputs[0].uuid in instance.outputs[0].connections
    _close(window)

def test_create_macro_draws_wires_to_the_instance_on_canvas(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    window.scene.add_block_from_library("logic.and", 200, 0)
    window.scene.add_block_from_library("output.do", 400, 0)
    di, gate, do = window.project.blocks
    di.outputs[0].connect(gate.inputs[0])
    gate.outputs[0].connect(do.inputs[0])

    for item in _block_items(window):
        if item.logic_block is gate:
            item.setSelected(True)
    window.scene.create_macro_from_selection("MojGate")

    from logic_studio.ui.canvas.wire_item import WireItem
    from logic_studio.blocks.macro_instance import MacroInstanceBlock
    instance_item = next(i for i in _block_items(window) if isinstance(i.logic_block, MacroInstanceBlock))

    wires_touching_instance = [
        w for w in window.scene.items() if isinstance(w, WireItem)
        and ((w.source_port and w.source_port.parentItem() == instance_item)
             or (w.dest_port and w.dest_port.parentItem() == instance_item))
    ]
    assert len(wires_touching_instance) == 2
    _close(window)

def test_create_macro_with_no_selection_is_a_no_op(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    assert window.scene.create_macro_from_selection("Empty") is False
    assert len(get_definitions(window.project)) == 0
    _close(window)

def test_create_macro_is_a_single_undo_entry(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    _select_all(window)

    depth_before = len(window.project.undo_stack)
    window.scene.create_macro_from_selection("Solo")
    assert len(window.project.undo_stack) == depth_before + 1
    _close(window)


# ---- add_block_from_library() macro special-case ---------------------------

def test_placing_a_second_instance_from_the_library_configures_its_pins(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    window.scene.add_block_from_library("logic.and", 200, 0)
    window.scene.add_block_from_library("output.do", 400, 0)
    di, gate, do = window.project.blocks
    di.outputs[0].connect(gate.inputs[0])
    gate.outputs[0].connect(do.inputs[0])

    for item in _block_items(window):
        if item.logic_block is gate:
            item.setSelected(True)
    window.scene.create_macro_from_selection("MojGate")

    from logic_studio.blocks.macro_instance import MacroInstanceBlock
    first_instance = next(b for b in window.project.blocks if isinstance(b, MacroInstanceBlock))

    window.scene.add_block_from_library(first_instance.type_id, 600, 600)

    instances = [b for b in window.project.blocks if isinstance(b, MacroInstanceBlock)]
    assert len(instances) == 2
    second_instance = next(b for b in instances if b.uuid != first_instance.uuid)
    assert second_instance.display_name == "MojGate"
    assert len(second_instance.inputs) == 1
    assert len(second_instance.outputs) == 1
    # independent pin identity from the first instance
    assert second_instance.inputs[0].uuid != first_instance.inputs[0].uuid
    _close(window)

def test_placing_an_instance_of_a_deleted_definition_is_a_no_op(qsettings):
    _app()
    window = _make_window(qsettings)
    from logic_studio.core.macros import delete_definition
    window.scene.add_block_from_library("logic.and", 0, 0)
    _select_all(window)
    window.scene.create_macro_from_selection("Gone")

    def_id = next(iter(get_definitions(window.project).keys()))
    delete_definition(window.project, def_id)

    before = len(window.project.blocks)
    window.scene.add_block_from_library(f"macro.{def_id}", 0, 0)
    assert len(window.project.blocks) == before
    _close(window)


# ---- BlockItem context-menu entry point ------------------------------------

def test_context_menu_prompt_creates_a_macro_from_the_selection(qsettings, monkeypatch):
    """BlockItem._prompt_create_macro_from_selection() — the context-menu
    action's actual handler, split out from contextMenuEvent() precisely
    so it's testable without driving a real modal QInputDialog."""
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    _select_all(window)
    item = _block_items(window)[0]

    from PySide6.QtWidgets import QInputDialog
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("MójMakro", True)))

    item._prompt_create_macro_from_selection()

    from logic_studio.blocks.macro_instance import MacroInstanceBlock
    instance = next(b for b in window.project.blocks if isinstance(b, MacroInstanceBlock))
    assert instance.display_name == "MójMakro"
    _close(window)

def test_context_menu_prompt_cancelled_dialog_is_a_no_op(qsettings, monkeypatch):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    _select_all(window)
    item = _block_items(window)[0]

    from PySide6.QtWidgets import QInputDialog
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("", False)))

    item._prompt_create_macro_from_selection()

    assert len(get_definitions(window.project)) == 0
    _close(window)


# ---- copy/paste/duplicate of a placed macro instance ------------------
# AUDIT_REPORT.md §33: a placed MacroInstanceBlock is just another block
# from copy_selected_items()/paste_clipboard()'s own point of view (both
# operate generically over BlockItem.logic_block), and MacroInstanceBlock.
# deserialize() builds fully self-sufficient pins straight from the
# copied data — so no special-casing should be needed here at all. These
# tests exist to confirm that's actually true (found untested during a
# post-implementation audit sweep, not a reported bug).

def test_copy_paste_a_macro_instance_produces_a_second_configured_instance(qsettings):
    _app()
    window = _make_window(qsettings)
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

    from logic_studio.blocks.macro_instance import MacroInstanceBlock
    original = next(b for b in window.project.blocks if isinstance(b, MacroInstanceBlock))

    for item in _block_items(window):
        item.setSelected(item.logic_block is original)
    assert window.scene.copy_selected_items() is True
    window.scene.paste_clipboard()

    instances = [b for b in window.project.blocks if isinstance(b, MacroInstanceBlock)]
    assert len(instances) == 2
    pasted = next(b for b in instances if b.uuid != original.uuid)
    assert pasted.def_id == original.def_id
    assert pasted.display_name == "MojMakro"
    assert [p.name for p in pasted.inputs] == [p.name for p in original.inputs]
    assert [p.name for p in pasted.outputs] == [p.name for p in original.outputs]
    assert pasted.short_id != original.short_id
    assert pasted.inputs[0].uuid != original.inputs[0].uuid
    _close(window)

def test_duplicate_a_macro_instance(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    _select_all(window)
    window.scene.create_macro_from_selection("Solo")

    from logic_studio.blocks.macro_instance import MacroInstanceBlock
    original = next(b for b in window.project.blocks if isinstance(b, MacroInstanceBlock))
    for item in _block_items(window):
        item.setSelected(item.logic_block is original)

    window.scene.duplicate_selected_items()

    instances = [b for b in window.project.blocks if isinstance(b, MacroInstanceBlock)]
    assert len(instances) == 2
    assert len({b.def_id for b in instances}) == 1
    _close(window)
