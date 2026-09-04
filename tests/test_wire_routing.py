"""Wire routing (WireItem.update_path()) — a wire must always leave its
source pin and enter its destination pin heading in the direction that
pin actually faces (right-mounted -> exits/enters moving +X, left-mounted
-> exits/enters moving -X/from the left), regardless of where the other
end happens to sit on screen, and regardless of which end was clicked
first while drawing the wire (source_port/dest_port track click order,
not logical output/input role).
"""
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF

from logic_studio.blocks import register_builtin_blocks
from logic_studio.ui.canvas.scene import LogicScene
from logic_studio.ui.canvas.block_item import BlockItem
from logic_studio.ui.canvas.wire_item import WireItem
from logic_studio.ui.canvas.port_item import PortItem

register_builtin_blocks()


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _block_item(scene, type_id):
    return next(i for i in scene.items() if isinstance(i, BlockItem) and i.logic_block.type_id == type_id)


def _port_for(block_item, pin):
    return next(p for p in block_item.childItems() if isinstance(p, PortItem) and p.pin is pin)


def _connected_wire(scene, source_block_item, source_pin, dest_block_item, dest_pin):
    assert source_pin.connect(dest_pin)
    source_port = _port_for(source_block_item, source_pin)
    dest_port = _port_for(dest_block_item, dest_pin)
    wire = WireItem(source_port=source_port, dest_port=dest_port)
    scene.addItem(wire)
    wire.update_path()
    return wire


def _path_points(wire):
    path = wire.path()
    return [QPointF(path.elementAt(i).x, path.elementAt(i).y) for i in range(path.elementCount())]


# ---- exit/entry direction invariant --------------------------------------

def test_wire_exits_right_mounted_source_moving_rightward(qsettings):
    _app()
    scene = LogicScene()
    scene.add_block_from_library("logic.and3", 40, 170)
    scene.add_block_from_library("system.message", 460, 170)
    src = _block_item(scene, "logic.and3")
    dst = _block_item(scene, "system.message")

    wire = _connected_wire(scene, src, src.logic_block.outputs[0], dst, dst.logic_block.inputs[0])
    points = _path_points(wire)

    start = points[0]
    second = points[1]
    assert second.x() > start.x()  # exits moving +X (rightward), from a right-mounted output
    assert second.y() == start.y()  # first segment is horizontal


def test_wire_enters_left_mounted_dest_moving_rightward(qsettings):
    """The segment arriving at the destination pin must be horizontal and
    approach from the left — the exact defect in the reported screenshot
    (a short vertical drop right before the pin read as "enters from
    below")."""
    _app()
    scene = LogicScene()
    scene.add_block_from_library("logic.and3", 40, 170)
    scene.add_block_from_library("system.message", 460, 170)
    src = _block_item(scene, "logic.and3")
    dst = _block_item(scene, "system.message")

    wire = _connected_wire(scene, src, src.logic_block.outputs[0], dst, dst.logic_block.inputs[0])
    points = _path_points(wire)

    end = points[-1]
    second_to_last = points[-2]
    assert second_to_last.x() < end.x()  # approaches moving +X, from the left
    assert second_to_last.y() == end.y()  # final segment is horizontal


def test_small_vertical_offset_no_longer_forces_a_large_detour(qsettings):
    """The exact reported scenario: destination pin only slightly higher
    than the source, moderate horizontal gap. The old router's "loop
    around" branch forced a minimum 40px vertical detour even here; the
    new one should stay close to the direct diagonal span."""
    _app()
    scene = LogicScene()
    scene.add_block_from_library("logic.and3", 40, 170)
    scene.add_block_from_library("system.message", 460, 170)
    src = _block_item(scene, "logic.and3")
    dst = _block_item(scene, "system.message")

    out_pin = src.logic_block.outputs[0]
    in_pin = dst.logic_block.inputs[0]
    wire = _connected_wire(scene, src, out_pin, dst, in_pin)
    points = _path_points(wire)

    ys = [p.y() for p in points]
    out_port = _port_for(src, out_pin)
    in_port = _port_for(dst, in_pin)
    expected_span = abs(out_port.scenePos().y() - in_port.scenePos().y())
    assert max(ys) - min(ys) <= expected_span + 1  # no artificial extra detour


def test_backward_wire_still_exits_right_and_enters_from_left(qsettings):
    """Destination block positioned to the LEFT of the source (a feedback-
    style wire) — the direction invariant must hold exactly the same as
    the forward case, not flip because the geometry is reversed."""
    _app()
    scene = LogicScene()
    scene.add_block_from_library("logic.and3", 400, 170)
    scene.add_block_from_library("memory.sr", 60, 260)
    src = _block_item(scene, "logic.and3")
    dst = _block_item(scene, "memory.sr")

    wire = _connected_wire(scene, src, src.logic_block.outputs[0], dst, dst.logic_block.inputs[0])
    points = _path_points(wire)

    start, second = points[0], points[1]
    assert second.x() > start.x() and second.y() == start.y()  # still exits rightward

    end, second_to_last = points[-1], points[-2]
    assert second_to_last.x() < end.x() and second_to_last.y() == end.y()  # still enters from the left


def test_click_order_does_not_flip_which_end_gets_which_direction(qsettings):
    """source_port/dest_port record which pin was clicked FIRST while
    drawing the wire, not which one is logically the output — dragging
    from the INPUT pin to the OUTPUT pin must route identically to
    dragging the other way (same two connectors, same required exit/entry
    sides, only the click order differs)."""
    _app()
    scene = LogicScene()
    scene.add_block_from_library("logic.and3", 40, 170)
    scene.add_block_from_library("system.message", 460, 170)
    src = _block_item(scene, "logic.and3")
    dst = _block_item(scene, "system.message")
    out_pin = src.logic_block.outputs[0]
    in_pin = dst.logic_block.inputs[0]
    out_pin.connect(in_pin)

    # Reversed: WireItem's "source_port" is the INPUT pin (clicked first).
    out_port = _port_for(src, out_pin)
    in_port = _port_for(dst, in_pin)
    wire = WireItem(source_port=in_port, dest_port=out_port)
    scene.addItem(wire)
    wire.update_path()
    points = _path_points(wire)

    # The wire still starts at the input pin's own position and must
    # still leave it moving -X (leftward — it's left-mounted) ...
    start, second = points[0], points[1]
    assert second.x() < start.x() and second.y() == start.y()
    # ... and still arrive at the output pin moving -X (from the right —
    # it's right-mounted).
    end, second_to_last = points[-1], points[-2]
    assert second_to_last.x() > end.x() and second_to_last.y() == end.y()


# ---- dragging a new wire (no dest_port yet) ------------------------------

def test_dragging_preview_ends_exactly_at_the_cursor(qsettings):
    _app()
    scene = LogicScene()
    scene.add_block_from_library("logic.and3", 40, 170)
    src = _block_item(scene, "logic.and3")
    out_port = _port_for(src, src.logic_block.outputs[0])

    wire = WireItem(source_port=out_port)
    wire.temp_end_point = QPointF(300, 250)
    scene.addItem(wire)
    wire.update_path()

    points = _path_points(wire)
    assert points[-1] == QPointF(300, 250)  # no padding stub with nothing real to enter
