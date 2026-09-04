"""feat/wire-routing-obstacle-avoidance — WireItem.update_path()'s actual
integration with ui/canvas/routing.py, using real BlockItems on a real
LogicScene (routing.py's own tests cover the algorithm in isolation).
"""
import pytest
from PySide6.QtWidgets import QApplication

from logic_studio.blocks import register_builtin_blocks
from logic_studio.ui.canvas.scene import LogicScene
from logic_studio.ui.canvas.block_item import BlockItem
from logic_studio.ui.canvas.wire_item import WireItem
from logic_studio.ui.canvas.port_item import PortItem
from logic_studio.ui.canvas import routing

register_builtin_blocks()


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _block(scene, type_id):
    return next(i for i in scene.items() if isinstance(i, BlockItem) and i.logic_block.type_id == type_id)


def _port_for(block_item, pin):
    return next(p for p in block_item.childItems() if isinstance(p, PortItem) and p.pin is pin)


def _path_points(wire):
    path = wire.path()
    return [path.elementAt(i) for i in range(path.elementCount())]


def _path_as_qpointf(wire):
    from PySide6.QtCore import QPointF
    return [QPointF(e.x, e.y) for e in _path_points(wire)]


def test_wire_routes_around_a_block_sitting_in_its_direct_path(qsettings):
    """The exact scenario rendered/eyeballed during development: source on
    the right, destination on the left (a backward connection), with a
    third block sitting squarely in the naive single-bend path between
    them."""
    _app()
    scene = LogicScene()
    scene.add_block_from_library("logic.and3", 500, 100)
    scene.add_block_from_library("memory.sr", 60, 260)
    scene.add_block_from_library("logic.not", 250, 170)  # the obstacle

    and3 = _block(scene, "logic.and3")
    sr = _block(scene, "memory.sr")
    obstacle_item = _block(scene, "logic.not")

    out_pin = and3.logic_block.outputs[0]
    in_pin = sr.logic_block.inputs[0]
    assert out_pin.connect(in_pin)
    out_port = _port_for(and3, out_pin)
    in_port = _port_for(sr, in_pin)

    wire = WireItem(source_port=out_port, dest_port=in_port)
    scene.addItem(wire)
    wire.update_path()

    points = _path_as_qpointf(wire)
    obstacle_rect = obstacle_item.sceneBoundingRect()
    assert routing.path_intersects_obstacles(points, [obstacle_rect]) is False

def test_wire_still_uses_the_plain_path_when_nothing_is_in_the_way(qsettings):
    """Regression guard: a wire with a genuinely clear line between its
    two stubs must render EXACTLY the same simple path as before this
    module existed — obstacle avoidance must never kick in unnecessarily
    just because other blocks exist somewhere else on the canvas."""
    _app()
    scene = LogicScene()
    scene.add_block_from_library("logic.and3", 40, 170)
    scene.add_block_from_library("system.message", 460, 170)
    scene.add_block_from_library("logic.not", 40, 500)  # elsewhere, not in the way

    src = _block(scene, "logic.and3")
    dst = _block(scene, "system.message")
    out_pin = src.logic_block.outputs[0]
    in_pin = dst.logic_block.inputs[0]
    assert out_pin.connect(in_pin)
    out_port = _port_for(src, out_pin)
    in_port = _port_for(dst, in_pin)

    wire = WireItem(source_port=out_port, dest_port=in_port)
    scene.addItem(wire)
    wire.update_path()

    out_port_pos = out_port.scenePos()
    in_port_pos = in_port.scenePos()
    start_stub = routing.QPointF(out_port_pos.x() + 15, out_port_pos.y())
    end_stub = routing.QPointF(in_port_pos.x() - 15, in_port_pos.y())
    expected_middle = routing.candidate_path(start_stub, end_stub)

    points = _path_as_qpointf(wire)
    assert points == [out_port_pos] + expected_middle + [in_port_pos]

def test_a_blocks_own_source_and_dest_are_never_treated_as_obstacles(qsettings):
    """A wire naturally starts/ends flush against its OWN source/dest
    block's edge — those two blocks must never count as something the
    wire needs to route around."""
    _app()
    scene = LogicScene()
    scene.add_block_from_library("logic.and3", 40, 170)
    scene.add_block_from_library("system.message", 460, 170)
    src = _block(scene, "logic.and3")
    dst = _block(scene, "system.message")
    out_pin = src.logic_block.outputs[0]
    in_pin = dst.logic_block.inputs[0]
    assert out_pin.connect(in_pin)
    out_port = _port_for(src, out_pin)
    in_port = _port_for(dst, in_pin)

    wire = WireItem(source_port=out_port, dest_port=in_port)
    obstacles = wire._obstacle_rects()
    assert src.sceneBoundingRect() not in obstacles
    assert dst.sceneBoundingRect() not in obstacles

def test_dragging_a_new_wire_never_attempts_obstacle_avoidance(qsettings):
    """No dest_port yet (mid-drag) -> no obstacle list is even computed —
    matches the pre-existing "just follow the cursor" behavior exactly."""
    _app()
    scene = LogicScene()
    scene.add_block_from_library("logic.and3", 0, 0)
    scene.add_block_from_library("logic.not", 100, 100)  # would "obstruct" if it mattered
    src = _block(scene, "logic.and3")
    out_port = _port_for(src, src.logic_block.outputs[0])

    wire = WireItem(source_port=out_port)
    wire.temp_end_point = routing.QPointF(300, 250)
    scene.addItem(wire)
    wire.update_path()

    points = _path_as_qpointf(wire)
    assert points[-1] == routing.QPointF(300, 250)  # ends exactly at the cursor, no detour
