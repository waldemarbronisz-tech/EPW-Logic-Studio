"""feat/wire-labels — consistency between the two representations of
"these two pins are connected": a fully-connected Wire's (source_pin,
dest_pin) pair, and the pins' own Pin.connections lists. Without this,
a large project's compile would eventually be the first place a drift
between them ever showed up.

Found and fixed while writing these tests: THREE existing code paths
disconnect pins directly (ui/canvas/scene.py's delete_selected_items(),
twice, and create_macro_from_selection()) with no idea Wire records
exist at all — a Wire describing a connection one of these paths just
tore down would have been left orphaned, describing a connection that
no longer exists. Project.remove_wire_by_pins()/remove_wires_touching_
pins() close that at the source, one call added to each site.
"""
import pytest
from PySide6.QtWidgets import QApplication

from logic_studio.blocks import register_builtin_blocks
from logic_studio.core.project import Project
from logic_studio.core.wire import Wire, check_wire_pin_consistency

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


def _wire_items(window):
    from logic_studio.ui.canvas.wire_item import WireItem
    return [i for i in window.scene.items() if isinstance(i, WireItem)]


def _port_item_for(window, pin):
    """Connecting two Pin objects directly (as every test below does, to
    get precise control over which pins a Wire names) updates the DATA
    model only -- it does not conjure a WireItem graphics object, the
    same way drag-to-connect on the canvas would. Tests that need an
    actual WireItem present (so delete_selected_items() has graphics to
    select and remove) build one explicitly via this helper, mirroring
    what LogicScene._create_wire_items() already does for paste."""
    from logic_studio.ui.canvas.port_item import PortItem
    for item in _block_items(window):
        for child in item.childItems():
            if isinstance(child, PortItem) and child.pin is pin:
                return child
    raise AssertionError(f"no PortItem found for pin {pin.uuid}")


def _add_wire_item(window, source_pin, dest_pin):
    from logic_studio.ui.canvas.wire_item import WireItem
    source_port = _port_item_for(window, source_pin)
    dest_port = _port_item_for(window, dest_pin)
    item = WireItem(source_port, dest_port)
    window.scene.addItem(item)
    return item


# ---- The checker itself is meaningful, not vacuously green ----------------

def test_freshly_connected_and_labeled_wire_is_consistent():
    p = Project()
    a = _create(p, "logic.and")
    n = _create(p, "logic.not")
    assert a.outputs[0].connect(n.inputs[0])
    wire = Wire()
    wire.source_pin = a.outputs[0].uuid
    wire.dest_pin = n.inputs[0].uuid
    wire.label = "Blokada ZS"
    p.add_wire(wire)

    assert check_wire_pin_consistency(p) == []

def test_free_end_wire_is_not_flagged_as_inconsistent():
    """A free end has only one real pin -- nothing to cross-reference,
    and it must never be mistaken for a violation."""
    p = Project()
    a = _create(p, "logic.and")
    wire = Wire()
    wire.source_pin = a.outputs[0].uuid
    wire.free_end_dest = {"x": 10.0, "y": 10.0}
    p.add_wire(wire)

    assert check_wire_pin_consistency(p) == []

def test_checker_actually_detects_a_hand_built_inconsistency():
    """Sanity check on the checker itself: a Wire describing a
    connection that was NEVER made via Pin.connect() (so .connections
    never got updated) must be flagged, proving the other "consistent"
    assertions in this file aren't vacuously true."""
    p = Project()
    a = _create(p, "logic.and")
    n = _create(p, "logic.not")
    # Deliberately NOT calling a.outputs[0].connect(n.inputs[0]).
    wire = Wire()
    wire.source_pin = a.outputs[0].uuid
    wire.dest_pin = n.inputs[0].uuid
    p.add_wire(wire)

    violations = check_wire_pin_consistency(p)
    assert len(violations) == 2  # neither pin lists the other

def test_checker_detects_a_one_sided_asymmetric_connection():
    """Half of the same sanity check: if only ONE side's .connections
    was (incorrectly) updated, that must be caught too, not just the
    "neither side" case above."""
    p = Project()
    a = _create(p, "logic.and")
    n = _create(p, "logic.not")
    assert a.outputs[0].connect(n.inputs[0])
    n.inputs[0].connections.remove(a.outputs[0].uuid)  # break just one side
    wire = Wire()
    wire.source_pin = a.outputs[0].uuid
    wire.dest_pin = n.inputs[0].uuid
    p.add_wire(wire)

    violations = check_wire_pin_consistency(p)
    assert len(violations) == 1


def _create(project, type_id):
    from logic_studio.blocks.registry import BlockRegistry
    block = BlockRegistry.create_block(type_id)
    project.add_block(block)
    return block


# ---- Deleting a wire keeps the two representations in sync ---------------

def test_deleting_a_labeled_wire_removes_its_wire_record_too(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.add_block_from_library("logic.not", 200, 0)
    a, n = window.project.blocks
    assert a.outputs[0].connect(n.inputs[0])
    wire = Wire()
    wire.source_pin = a.outputs[0].uuid
    wire.dest_pin = n.inputs[0].uuid
    wire.label = "Blokada ZS"
    window.project.add_wire(wire)
    assert check_wire_pin_consistency(window.project) == []
    _add_wire_item(window, a.outputs[0], n.inputs[0])

    _wire_items(window)[0].setSelected(True)
    window.scene.delete_selected_items()

    assert window.project.wires == []  # no orphaned record left behind
    assert check_wire_pin_consistency(window.project) == []

    _close(window)


# ---- Deleting a block keeps the two representations in sync --------------

def test_deleting_a_block_removes_wire_records_touching_its_pins(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.add_block_from_library("logic.not", 200, 0)
    a, n = window.project.blocks
    assert a.outputs[0].connect(n.inputs[0])
    wire = Wire()
    wire.source_pin = a.outputs[0].uuid
    wire.dest_pin = n.inputs[0].uuid
    wire.label = "Blokada ZS"
    window.project.add_wire(wire)

    and_item = next(i for i in _block_items(window) if i.logic_block is a)
    and_item.setSelected(True)
    window.scene.delete_selected_items()

    assert window.project.wires == []
    assert check_wire_pin_consistency(window.project) == []

    _close(window)

def test_deleting_a_block_removes_its_own_free_end_wire_record(qsettings):
    """The case delete_selected_items()'s pre-existing WireItem-graphics
    search could never have found on its own -- a free-end wire has no
    on-canvas WireItem at all yet (drawing one is a later section)."""
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    a = window.project.blocks[0]
    wire = Wire()
    wire.source_pin = a.outputs[0].uuid
    wire.free_end_dest = {"x": 100.0, "y": 20.0}
    wire.label = "Odnośnik"
    window.project.add_wire(wire)
    assert len(window.project.wires) == 1

    _block_items(window)[0].setSelected(True)
    window.scene.delete_selected_items()

    assert window.project.wires == []

    _close(window)

def test_deleting_one_of_two_blocks_leaves_the_untouched_wire_alone(qsettings):
    """Deleting block A must not remove a labeled wire that belongs
    entirely to block B and C."""
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.add_block_from_library("logic.not", 200, 0)
    window.scene.add_block_from_library("logic.buffer", 400, 0)
    a, n, buf = window.project.blocks
    assert n.outputs[0].connect(buf.inputs[0])
    wire = Wire()
    wire.source_pin = n.outputs[0].uuid
    wire.dest_pin = buf.inputs[0].uuid
    wire.label = "Nietknięty"
    window.project.add_wire(wire)

    and_item = next(i for i in _block_items(window) if i.logic_block is a)
    and_item.setSelected(True)
    window.scene.delete_selected_items()

    assert len(window.project.wires) == 1
    assert window.project.wires[0].label == "Nietknięty"
    assert check_wire_pin_consistency(window.project) == []

    _close(window)


# ---- Undo keeps the two representations in sync ---------------------------

def test_undo_after_deleting_a_wire_restores_full_consistency(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.add_block_from_library("logic.not", 200, 0)
    a, n = window.project.blocks
    assert a.outputs[0].connect(n.inputs[0])
    wire = Wire()
    wire.source_pin = a.outputs[0].uuid
    wire.dest_pin = n.inputs[0].uuid
    wire.label = "Blokada ZS"
    window.project.add_wire(wire)
    _add_wire_item(window, a.outputs[0], n.inputs[0])

    _wire_items(window)[0].setSelected(True)
    window.scene.delete_selected_items()
    assert window.project.wires == []

    window._undo()

    assert len(window.project.wires) == 1
    assert window.project.wires[0].label == "Blokada ZS"
    assert check_wire_pin_consistency(window.project) == []

    _close(window)

def test_undo_after_deleting_a_block_restores_full_consistency(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.add_block_from_library("logic.not", 200, 0)
    a, n = window.project.blocks
    assert a.outputs[0].connect(n.inputs[0])
    wire = Wire()
    wire.source_pin = a.outputs[0].uuid
    wire.dest_pin = n.inputs[0].uuid
    wire.label = "Blokada ZS"
    window.project.add_wire(wire)

    and_item = next(i for i in _block_items(window) if i.logic_block is a)
    and_item.setSelected(True)
    window.scene.delete_selected_items()
    assert window.project.wires == []

    window._undo()

    assert len(window.project.blocks) == 2
    assert len(window.project.wires) == 1
    assert check_wire_pin_consistency(window.project) == []

    _close(window)

def test_redo_after_undo_deletes_again_and_stays_consistent(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.add_block_from_library("logic.not", 200, 0)
    a, n = window.project.blocks
    assert a.outputs[0].connect(n.inputs[0])
    wire = Wire()
    wire.source_pin = a.outputs[0].uuid
    wire.dest_pin = n.inputs[0].uuid
    wire.label = "Blokada ZS"
    window.project.add_wire(wire)

    and_item = next(i for i in _block_items(window) if i.logic_block is a)
    and_item.setSelected(True)
    window.scene.delete_selected_items()
    window._undo()
    window._redo()

    assert len(window.project.blocks) == 1
    assert window.project.wires == []
    assert check_wire_pin_consistency(window.project) == []

    _close(window)


# ---- Macro extraction (found while fixing the above -- same bug class) ---

def test_creating_a_macro_removes_wire_records_touching_extracted_blocks(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.add_block_from_library("logic.not", 200, 0)
    a, n = window.project.blocks
    assert a.outputs[0].connect(n.inputs[0])
    wire = Wire()
    wire.source_pin = a.outputs[0].uuid
    wire.dest_pin = n.inputs[0].uuid
    wire.label = "Wewnętrzny"
    window.project.add_wire(wire)

    for item in _block_items(window):
        item.setSelected(True)
    assert window.scene.create_macro_from_selection("MójMakro")

    assert window.project.wires == []
    assert check_wire_pin_consistency(window.project) == []

    _close(window)
