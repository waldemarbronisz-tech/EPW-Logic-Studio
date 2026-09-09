"""feat/wire-detour-and-text-size §A4 — WireItem.update_live_state() (a
per-scan color refresh, see scene.py::refresh_live_states(), called by
ExecutionEngine after EVERY simulation cycle for EVERY wire) used to call
the FULL update_path(), re-running obstacle-avoidance routing.route()
purely to pick up a value-driven color change, regardless of whether any
block had actually moved. At 600 blocks with a scan running several
times a second, that's real, needless repeated work. Verifies the fix
directly: a value-only refresh must not touch routing.route() at all.
"""
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from logic_studio.blocks import register_builtin_blocks
from logic_studio.core.project import Project
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


def _connected_wire(scene):
    scene.add_block_from_library("logic.and3", 0, 0)
    scene.add_block_from_library("logic.not", 400, 200)
    src = _block(scene, "logic.and3")
    dst = _block(scene, "logic.not")
    out_pin = src.logic_block.outputs[0]
    in_pin = dst.logic_block.inputs[0]
    assert out_pin.connect(in_pin)
    wire = WireItem(source_port=_port_for(src, out_pin), dest_port=_port_for(dst, in_pin))
    scene.addItem(wire)
    return wire, out_pin


def test_update_live_state_does_not_recompute_routing():
    _app()
    scene = LogicScene()
    wire, out_pin = _connected_wire(scene)
    wire.update_path()  # establish a real path first, same as normal use

    with patch.object(routing, "route", wraps=routing.route) as spy:
        out_pin.value = True
        wire.update_live_state()
        assert spy.call_count == 0, (
            "update_live_state() called routing.route() -- a value-only "
            "refresh should never re-run obstacle-avoidance routing"
        )

def test_update_live_state_still_updates_the_pen_color():
    """The fix must not turn update_live_state() into a no-op — only the
    GEOMETRY recompute is skipped; color still has to change."""
    from logic_studio.ui.canvas import style
    _app()
    scene = LogicScene()
    wire, out_pin = _connected_wire(scene)
    wire.update_path()

    out_pin.value = True
    wire.update_live_state()
    assert wire.color == style.COLOR_LOGIC_HIGH

    out_pin.value = False
    wire.update_live_state()
    assert wire.color == style.COLOR_LOGIC_LOW

def test_update_path_itself_still_calls_routing_route():
    """Sanity check on the spy technique above: routing.route() IS still
    reachable and used by the normal geometry path — update_live_state()
    specifically skips it, routing itself isn't broken."""
    _app()
    scene = LogicScene()
    wire, _out_pin = _connected_wire(scene)

    with patch.object(routing, "route", wraps=routing.route) as spy:
        wire.update_path()
        assert spy.call_count == 1
