"""fix/wire-labels-and-project-integrity §A3 — logic_studio/ui/canvas/wire_ops.py."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.core.project import Project
from logic_studio.core.wire import Wire
from logic_studio.ui.canvas.wire_ops import (
    find_wire_for_pins, get_or_create_wire_for_pins,
    clear_label_and_prune_if_pointless, add_stub_wire_from_port,
    convert_wire_to_stubs,
)

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


def _port_item_for(window, pin):
    from logic_studio.ui.canvas.block_item import BlockItem
    from logic_studio.ui.canvas.port_item import PortItem
    for item in window.scene.items():
        if not isinstance(item, BlockItem):
            continue
        for child in item.childItems():
            if isinstance(child, PortItem) and child.pin is pin:
                return child
    raise AssertionError(f"no PortItem found for pin {pin.uuid}")


# ---- find_wire_for_pins() / get_or_create_wire_for_pins() ------------------

def test_find_wire_for_pins_matches_either_ordering():
    p = Project()
    a = BlockRegistry.create_block("logic.and")
    n = BlockRegistry.create_block("logic.not")
    p.add_block(a)
    p.add_block(n)
    w = Wire()
    w.source_pin = a.outputs[0].uuid
    w.dest_pin = n.inputs[0].uuid
    p.add_wire(w)

    assert find_wire_for_pins(p, a.outputs[0].uuid, n.inputs[0].uuid) is w
    assert find_wire_for_pins(p, n.inputs[0].uuid, a.outputs[0].uuid) is w  # reversed

def test_find_wire_for_pins_returns_none_when_absent():
    p = Project()
    assert find_wire_for_pins(p, "x", "y") is None

def test_get_or_create_reuses_an_existing_wire():
    p = Project()
    a = BlockRegistry.create_block("logic.and")
    n = BlockRegistry.create_block("logic.not")
    p.add_block(a)
    p.add_block(n)
    existing = Wire()
    existing.source_pin = a.outputs[0].uuid
    existing.dest_pin = n.inputs[0].uuid
    existing.label = "AlreadyThere"
    p.add_wire(existing)

    result = get_or_create_wire_for_pins(p, a.outputs[0].uuid, n.inputs[0].uuid)
    assert result is existing
    assert len(p.wires) == 1

def test_get_or_create_makes_a_fresh_wire_for_the_common_unlabeled_case():
    p = Project()
    a = BlockRegistry.create_block("logic.and")
    n = BlockRegistry.create_block("logic.not")
    p.add_block(a)
    p.add_block(n)
    a.outputs[0].connect(n.inputs[0])  # physically wired, no Wire record yet

    assert p.wires == []
    wire = get_or_create_wire_for_pins(p, a.outputs[0].uuid, n.inputs[0].uuid)
    assert wire in p.wires
    assert wire.source_pin == a.outputs[0].uuid
    assert wire.dest_pin == n.inputs[0].uuid


# ---- clear_label_and_prune_if_pointless() ----------------------------------

def test_clearing_a_label_on_a_fully_connected_wire_removes_the_record():
    """core/wire.py's own design principle: a plain, fully-connected,
    unlabeled wire carries NO Wire record at all."""
    p = Project()
    a = BlockRegistry.create_block("logic.and")
    n = BlockRegistry.create_block("logic.not")
    p.add_block(a)
    p.add_block(n)
    wire = Wire()
    wire.source_pin = a.outputs[0].uuid
    wire.dest_pin = n.inputs[0].uuid
    wire.label = "ToRemove"
    p.add_wire(wire)

    clear_label_and_prune_if_pointless(p, wire)

    assert p.wires == []

def test_clearing_a_label_on_a_free_end_wire_keeps_the_record():
    """A free end still needs its Wire record to exist regardless of the
    label -- clearing the label alone must not delete it (it would
    become an ordinary Pin.connections-only wire ONLY if fully connected;
    a free end has nothing else to fall back on)."""
    p = Project()
    a = BlockRegistry.create_block("logic.and")
    p.add_block(a)
    wire = Wire()
    wire.source_pin = a.outputs[0].uuid
    wire.free_end_dest = {"x": 1.0, "y": 1.0}
    wire.label = "ToRemove"
    p.add_wire(wire)

    clear_label_and_prune_if_pointless(p, wire)

    assert wire in p.wires
    assert wire.label == ""


# ---- add_stub_wire_from_port() ---------------------------------------------

def test_add_stub_wire_from_an_output_port(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    a = window.project.blocks[0]
    port = _port_item_for(window, a.outputs[0])

    wire = add_stub_wire_from_port(window.project, port)

    assert wire in window.project.wires
    assert wire.source_pin == a.outputs[0].uuid
    assert wire.dest_pin is None
    assert wire.free_end_dest is not None
    # Offset from the port's own scene position, not left at (0, 0).
    assert wire.free_end_dest["x"] != port.scenePos().x() or wire.free_end_dest["y"] != port.scenePos().y()
    _close(window)

def test_add_stub_wire_from_an_input_port(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.not", 0, 0)
    n = window.project.blocks[0]
    port = _port_item_for(window, n.inputs[0])

    wire = add_stub_wire_from_port(window.project, port)

    assert wire in window.project.wires
    assert wire.dest_pin == n.inputs[0].uuid
    assert wire.source_pin is None
    assert wire.free_end_source is not None
    _close(window)


# ---- convert_wire_to_stubs() -----------------------------------------------

def test_convert_wire_to_stubs_disconnects_and_creates_two_free_ends(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.add_block_from_library("logic.not", 200, 0)
    a, n = window.project.blocks
    a.outputs[0].connect(n.inputs[0])
    source_port = _port_item_for(window, a.outputs[0])
    dest_port = _port_item_for(window, n.inputs[0])

    wire_at_source, wire_at_dest = convert_wire_to_stubs(window.project, source_port, dest_port)

    # No longer physically connected.
    assert n.inputs[0].uuid not in a.outputs[0].connections
    assert a.outputs[0].uuid not in n.inputs[0].connections
    # Two independent free-end records, each anchored at its own original pin.
    assert wire_at_source.source_pin == a.outputs[0].uuid
    assert wire_at_source.dest_pin is None
    assert wire_at_dest.dest_pin == n.inputs[0].uuid
    assert wire_at_dest.source_pin is None
    assert wire_at_source in window.project.wires
    assert wire_at_dest in window.project.wires
    _close(window)

def test_convert_wire_to_stubs_removes_a_pre_existing_wire_record(qsettings):
    """If the original wire already had its own Wire record (e.g. a
    pre-existing documentary label), converting to stubs must not leave
    that stale fully-connected-shaped record behind alongside the two
    new free ends."""
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.add_block_from_library("logic.not", 200, 0)
    a, n = window.project.blocks
    a.outputs[0].connect(n.inputs[0])
    old_wire = Wire()
    old_wire.source_pin = a.outputs[0].uuid
    old_wire.dest_pin = n.inputs[0].uuid
    old_wire.label = "OldDocNote"
    window.project.add_wire(old_wire)

    source_port = _port_item_for(window, a.outputs[0])
    dest_port = _port_item_for(window, n.inputs[0])
    convert_wire_to_stubs(window.project, source_port, dest_port)

    assert old_wire not in window.project.wires
    assert len(window.project.wires) == 2  # exactly the two new stubs
    _close(window)
