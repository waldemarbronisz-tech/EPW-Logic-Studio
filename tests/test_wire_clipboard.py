"""feat/wire-labels §2.4 — the third of the three field-audit paths:
clipboard copy/paste must carry Wire records (label, free end) exactly
like it already carries Pin.connections, remapped onto the pasted
blocks' fresh pin uuids the same way.
"""
import pytest
from PySide6.QtWidgets import QApplication

from logic_studio.blocks import register_builtin_blocks
from logic_studio.core.project import Project
from logic_studio.core.wire import Wire

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


def test_copy_paste_carries_a_labeled_wire_between_two_selected_blocks(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.add_block_from_library("logic.not", 200, 0)
    and_block, not_block = window.project.blocks
    assert and_block.outputs[0].connect(not_block.inputs[0])

    wire = Wire()
    wire.source_pin = and_block.outputs[0].uuid
    wire.dest_pin = not_block.inputs[0].uuid
    wire.label = "Blokada ZS"
    assert window.project.add_wire(wire)

    for item in _block_items(window):
        item.setSelected(True)
    assert window.scene.copy_selected_items()
    window.scene.paste_clipboard()

    assert len(window.project.wires) == 2  # original + pasted
    pasted = [w for w in window.project.wires if w.uuid != wire.uuid][0]
    assert pasted.label == "Blokada ZS"

    new_and = next(b for b in window.project.blocks if b.type_id == "logic.and" and b is not and_block)
    new_not = next(b for b in window.project.blocks if b.type_id == "logic.not" and b is not not_block)
    assert pasted.source_pin == new_and.outputs[0].uuid
    assert pasted.dest_pin == new_not.inputs[0].uuid

    _close(window)

def test_copy_paste_carries_a_free_end_wire_offset_by_the_paste_delta(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    and_block = window.project.blocks[0]

    wire = Wire()
    wire.source_pin = and_block.outputs[0].uuid
    wire.free_end_dest = {"x": 100.0, "y": 20.0}
    wire.label = "Do dalszej części"
    assert window.project.add_wire(wire)

    _block_items(window)[0].setSelected(True)
    assert window.scene.copy_selected_items()
    window.scene.paste_clipboard()

    assert len(window.project.wires) == 2
    pasted = [w for w in window.project.wires if w.uuid != wire.uuid][0]
    assert pasted.label == "Do dalszej części"
    assert pasted.dest_pin is None
    assert pasted.free_end_dest is not None
    # Offset by whatever delta the paste actually used -- same delta as
    # the pasted block's own new position relative to the original.
    new_and = next(b for b in window.project.blocks if b is not and_block)
    delta_x = new_and.x - and_block.x
    delta_y = new_and.y - and_block.y
    assert pasted.free_end_dest["x"] == pytest.approx(100.0 + delta_x)
    assert pasted.free_end_dest["y"] == pytest.approx(20.0 + delta_y)

    _close(window)

def test_copy_drops_a_wire_whose_other_real_end_is_outside_the_selection(qsettings):
    """Same "silently drop what doesn't fully fit" rule copy_selected_
    items() already applies to plain Pin.connections."""
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.add_block_from_library("logic.not", 200, 0)
    and_block, not_block = window.project.blocks
    assert and_block.outputs[0].connect(not_block.inputs[0])

    wire = Wire()
    wire.source_pin = and_block.outputs[0].uuid
    wire.dest_pin = not_block.inputs[0].uuid
    wire.label = "Blokada ZS"
    assert window.project.add_wire(wire)

    # Select ONLY and_block -- not_block (the OTHER real end) stays outside.
    _block_items(window)[0].setSelected(True)
    assert window.scene.copy_selected_items()
    window.scene.paste_clipboard()

    assert len(window.project.wires) == 1  # only the original -- nothing pasted

    _close(window)

def test_paste_wire_gets_a_fresh_uuid_not_the_original(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.add_block_from_library("logic.not", 200, 0)
    and_block, not_block = window.project.blocks
    assert and_block.outputs[0].connect(not_block.inputs[0])

    wire = Wire()
    wire.source_pin = and_block.outputs[0].uuid
    wire.dest_pin = not_block.inputs[0].uuid
    assert window.project.add_wire(wire)

    for item in _block_items(window):
        item.setSelected(True)
    assert window.scene.copy_selected_items()
    window.scene.paste_clipboard()

    uuids = [w.uuid for w in window.project.wires]
    assert len(uuids) == len(set(uuids))  # no duplicate uuid

    _close(window)
