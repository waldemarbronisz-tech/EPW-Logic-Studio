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


# ---- feat/wire-detour-and-text-size §A5 -----------------------------------

def _make_self_loop_wire(scene, type_id="logic.nand3", x=200, y=200):
    """A block's own output wired back to its own input — §A2's feedback
    case, the exact shape reported as passing straight through the
    block's body before this fix."""
    scene.add_block_from_library(type_id, x, y)
    block = _block(scene, type_id)
    out_pin = block.logic_block.outputs[0]
    in_pin = block.logic_block.inputs[0]
    assert out_pin.connect(in_pin)
    out_port = _port_for(block, out_pin)
    in_port = _port_for(block, in_pin)
    wire = WireItem(source_port=out_port, dest_port=in_port)
    scene.addItem(wire)
    wire.update_path()
    return wire, block, out_port, in_port


def test_self_loop_wire_does_not_cross_its_own_blocks_body():
    """§A1/§A2, the exact reported scenario: NAND-3's output wired back to
    its own input must not cut through its own body. Geometric check on
    plain QRectF/QPointF, per §A5's own wording — the wire's own two
    "final approach" segments (port<->stub, right at the block's own
    edge by this app's convention) are excluded, exactly like §A1's
    stated exception; everything else must clear the body entirely."""
    _app()
    scene = LogicScene()
    wire, block, _out, _in = _make_self_loop_wire(scene)
    own_rect = block.sceneBoundingRect()
    points = _path_as_qpointf(wire)
    detour_core = points[2:-2]  # excludes both port->stub approach segments
    assert routing.path_intersects_obstacles(detour_core, [own_rect], margin=0) is False

def test_self_loop_detour_keeps_at_least_one_grid_cell_from_the_body():
    """§A2: "odstęp od korpusu co najmniej jedno oczko siatki, żeby
    przewód nie stykał się z obrysem" — checked with the routing margin
    that's supposed to guarantee it, not just margin=0 (which only proves
    "doesn't overlap", not "doesn't hug the outline")."""
    from logic_studio.core.grid import GRID_SIZE
    _app()
    scene = LogicScene()
    wire, block, _out, _in = _make_self_loop_wire(scene)
    own_rect = block.sceneBoundingRect()
    points = _path_as_qpointf(wire)
    detour_core = points[2:-2]
    assert routing.path_intersects_obstacles(detour_core, [own_rect], margin=GRID_SIZE - 0.5) is False

def test_self_loop_wire_still_touches_both_of_its_own_ports():
    """§A5: the detour must not have pushed either endpoint away from the
    port it's actually supposed to connect to."""
    _app()
    scene = LogicScene()
    wire, _block, out_port, in_port = _make_self_loop_wire(scene)
    points = _path_as_qpointf(wire)
    assert points[0] == out_port.scenePos()
    assert points[-1] == in_port.scenePos()

def test_self_loop_route_is_fully_orthogonal():
    _app()
    scene = LogicScene()
    wire, _block, _out, _in = _make_self_loop_wire(scene)
    points = _path_as_qpointf(wire)
    for i in range(len(points) - 1):
        p1, p2 = points[i], points[i + 1]
        assert p1.x() == p2.x() or p1.y() == p2.y()

def test_self_loop_prefers_the_side_with_more_free_space():
    """§A2: side choice is "more free space; tie -> top", not arbitrary.
    An obstacle placed just above the looping block forces the detour to
    go the other way (down, i.e. larger Y in scene coordinates)."""
    _app()
    scene = LogicScene()
    scene.add_block_from_library("logic.not", 200, 0)  # crowds the top
    wire, block, _out, _in = _make_self_loop_wire(scene, x=200, y=300)
    points = _path_as_qpointf(wire)
    own_rect = block.sceneBoundingRect()
    # points[2:-2] is [riser_start, detour_top, detour_bottom, riser_end] --
    # the middle two are the actual horizontal crossing, at detour_y; the
    # outer two just retain the stub's own Y and aren't part of the
    # up-or-down choice being checked here.
    detour_y_values = [p.y() for p in points[3:5]]
    assert all(y > own_rect.bottom() for y in detour_y_values), (
        "expected the detour to go DOWN (more free space there) with an "
        f"obstacle crowding the top; detour Y values were {detour_y_values}"
    )

def test_wire_between_two_blocks_still_touches_both_ports_after_a_detour():
    """§A5: same check as the self-loop version, for the general
    (different-blocks) obstacle-avoidance case — a detour must never
    leave either end short of its actual port."""
    _app()
    scene = LogicScene()
    scene.add_block_from_library("logic.and3", 500, 100)
    scene.add_block_from_library("memory.sr", 60, 260)
    scene.add_block_from_library("logic.not", 250, 170)  # forces a detour
    and3 = _block(scene, "logic.and3")
    sr = _block(scene, "memory.sr")
    out_pin = and3.logic_block.outputs[0]
    in_pin = sr.logic_block.inputs[0]
    assert out_pin.connect(in_pin)
    out_port = _port_for(and3, out_pin)
    in_port = _port_for(sr, in_pin)
    wire = WireItem(source_port=out_port, dest_port=in_port)
    scene.addItem(wire)
    wire.update_path()
    points = _path_as_qpointf(wire)
    assert points[0] == out_port.scenePos()
    assert points[-1] == in_port.scenePos()

def test_detoured_route_between_two_blocks_is_fully_orthogonal():
    _app()
    scene = LogicScene()
    scene.add_block_from_library("logic.and3", 500, 100)
    scene.add_block_from_library("memory.sr", 60, 260)
    scene.add_block_from_library("logic.not", 250, 170)
    and3 = _block(scene, "logic.and3")
    sr = _block(scene, "memory.sr")
    out_pin = and3.logic_block.outputs[0]
    in_pin = sr.logic_block.inputs[0]
    assert out_pin.connect(in_pin)
    out_port = _port_for(and3, out_pin)
    in_port = _port_for(sr, in_pin)
    wire = WireItem(source_port=out_port, dest_port=in_port)
    scene.addItem(wire)
    wire.update_path()
    points = _path_as_qpointf(wire)
    for i in range(len(points) - 1):
        p1, p2 = points[i], points[i + 1]
        assert p1.x() == p2.x() or p1.y() == p2.y()


# feat/wire-detour-and-text-size §A5: an obstacle (logic.not, same block
# used by the pre-existing single-layout test above) positioned to
# straddle a different one of the naive candidate path's own 3 segments
# each time — out3's stub is (555,130), sr's stub is (45,290), the naive
# path's own bend sits at mid_x=300 — approaching from above, below, and
# either side of that bend.
_OBSTACLE_POSITIONS = [
    ("above", (400, 95)),    # straddles the y=130 run from above
    ("below", (150, 260)),   # straddles the y=290 run from below
    ("left", (260, 155)),    # straddles the x=300 run, offset left
    ("right", (300, 155)),   # straddles the x=300 run, offset right
]


@pytest.mark.parametrize("label, pos", _OBSTACLE_POSITIONS, ids=[l for l, _p in _OBSTACLE_POSITIONS])
def test_wire_avoids_an_obstacle_regardless_of_which_side_it_approaches_from(qsettings, label, pos):
    """§A5: parametrized across an obstacle sitting above, below, to the
    left of, and to the right of the same wire's naive direct path —
    every one of the 4 must still be avoided, not just the single layout
    the original obstacle-avoidance PR happened to be developed against."""
    _app()
    scene = LogicScene()
    scene.add_block_from_library("logic.and3", 500, 100)
    scene.add_block_from_library("memory.sr", 60, 260)
    scene.add_block_from_library("logic.not", pos[0], pos[1])
    src = _block(scene, "logic.and3")
    dst = _block(scene, "memory.sr")
    obstacle_item = _block(scene, "logic.not")
    out_pin = src.logic_block.outputs[0]
    in_pin = dst.logic_block.inputs[0]
    assert out_pin.connect(in_pin)
    out_port = _port_for(src, out_pin)
    in_port = _port_for(dst, in_pin)

    wire = WireItem(source_port=out_port, dest_port=in_port)
    scene.addItem(wire)
    wire.update_path()

    points = _path_as_qpointf(wire)
    obstacle_rect = obstacle_item.sceneBoundingRect()
    assert routing.path_intersects_obstacles(points, [obstacle_rect]) is False, (
        f"obstacle placed {label} of the direct path was not avoided"
    )
    assert points[0] == out_port.scenePos()
    assert points[-1] == in_port.scenePos()
