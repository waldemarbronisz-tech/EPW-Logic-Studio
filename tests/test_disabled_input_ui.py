"""feat/editor-modes-and-geometry §2.2/§2.3 — the canvas interaction and
rendering side of disabled ("zaślepione") inputs: eligibility rules for the
double-click/context-menu toggle, and the extra geometry the disabled stub
needs. Compile/validate-level behavior is covered by test_disabled_inputs.py;
this file is presentation-layer only, same split as test_canvas_rendering.py.
"""
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF

from logic_studio.blocks import register_builtin_blocks
from logic_studio.ui.canvas.block_item import BlockItem
from logic_studio.ui.canvas.port_item import PortItem
from logic_studio.ui.canvas import style
from logic_studio.blocks.pin import Pin
from logic_studio.blocks.logic_gates import And3Gate, NotGate


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


register_builtin_blocks()


def _input_ports(item):
    return [c for c in item.childItems() if isinstance(c, PortItem) and c.pin.direction == Pin.DIR_INPUT]

def _output_port(item):
    return next(c for c in item.childItems() if isinstance(c, PortItem) and c.pin.direction == Pin.DIR_OUTPUT)


def test_unconnected_input_on_and3_is_eligible_and_unblocked():
    _app()
    item = BlockItem(And3Gate())
    port = _input_ports(item)[0]
    eligible, blocked_reason = port._disable_eligibility()
    assert eligible is True
    assert blocked_reason is None

def test_input_with_a_wire_is_eligible_but_blocked():
    _app()
    item = BlockItem(And3Gate())
    port = _input_ports(item)[0]
    port.pin.connections.append("some-other-pin-uuid")  # simulate an attached wire
    eligible, blocked_reason = port._disable_eligibility()
    assert eligible is True
    assert blocked_reason is not None

def test_output_port_is_never_eligible():
    _app()
    item = BlockItem(And3Gate())
    port = _output_port(item)
    eligible, _ = port._disable_eligibility()
    assert eligible is False

def test_input_on_block_that_does_not_allow_it_is_not_eligible():
    _app()
    item = BlockItem(NotGate())
    port = _input_ports(item)[0]
    eligible, _ = port._disable_eligibility()
    assert eligible is False

def test_toggle_flips_the_flag_and_is_reversible():
    _app()
    item = BlockItem(And3Gate())
    port = _input_ports(item)[0]
    assert port.pin.disabled is False
    port._toggle_disabled()
    assert port.pin.disabled is True
    port._toggle_disabled()
    assert port.pin.disabled is False

def test_bounding_rect_widens_to_cover_the_stub_when_disabled():
    """§2.3: the stub extends PORT_PITCH further out than the ordinary port
    click box — boundingRect() must grow to cover it once disabled, or Qt
    may fail to repaint/clip it correctly."""
    _app()
    item = BlockItem(And3Gate())
    port = _input_ports(item)[0]

    normal_rect = port.boundingRect()
    port.pin.disabled = True
    disabled_rect = port.boundingRect()

    assert disabled_rect.left() <= -style.PORT_PITCH
    assert disabled_rect.left() < normal_rect.left()

def test_disabled_input_boundingRect_still_covers_the_original_port_click_area():
    """Re-enabling must stay reachable by clicking where the port always
    was, not just somewhere out on the stub."""
    _app()
    item = BlockItem(And3Gate())
    port = _input_ports(item)[0]
    port.pin.disabled = True
    rect = port.boundingRect()
    assert rect.contains(QPointF(0, 0))
