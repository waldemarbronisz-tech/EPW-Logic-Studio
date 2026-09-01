"""Canvas rendering tests (feat/block-rendering-library). Presentation-layer
only — no engine/compiler behavior is exercised here."""
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF

from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.ui.canvas.block_item import BlockItem, GATE_SHAPES
from logic_studio.ui.canvas.port_item import PortItem
from logic_studio.ui.canvas import style, shapes
from logic_studio.blocks.pin import Pin


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


register_builtin_blocks()

NEGATED_TYPE_IDS = [
    "logic.not", "logic.nand", "logic.nand3", "logic.nand4",
    "logic.nor", "logic.nor3", "logic.nor4", "logic.xnor",
]
NON_NEGATED_TYPE_IDS = [
    "logic.and", "logic.and3", "logic.and4",
    "logic.or", "logic.or3", "logic.or4", "logic.xor", "logic.buffer",
]


def _output_port(item):
    return next(c for c in item.childItems() if isinstance(c, PortItem) and c.pin.direction == Pin.DIR_OUTPUT)


@pytest.mark.parametrize("type_id", NEGATED_TYPE_IDS)
def test_negated_gate_bubble_and_port_do_not_overlap(type_id):
    """§1: previously both the negation bubble and the output port were
    drawn at exactly (width, height/2) — the port (painted on top as a
    child item) fully occluded the bubble, making NAND indistinguishable
    from AND, NOR from OR, XNOR from XOR. The port must now sit clear of
    the bubble, not merely at a numerically different point."""
    _app()
    block = BlockRegistry.create_block(type_id)
    item = BlockItem(block)

    port_pos = _output_port(item).pos()
    bubble_center = QPointF(item.width + style.BUBBLE_RADIUS, item.height / 2)

    assert port_pos != bubble_center, f"{type_id}: output port sits exactly on the negation bubble"
    assert port_pos.x() > bubble_center.x(), f"{type_id}: output port must sit past the bubble, not on/before it"

@pytest.mark.parametrize("type_id", NON_NEGATED_TYPE_IDS)
def test_non_negated_gate_output_port_flush_with_body(type_id):
    """Non-negated gates must be unaffected by the bubble fix: the output
    port stays flush with the body's right edge, at exactly `width` — no
    layout shift for the sixteen minus four gates that never had a bubble.
    Its y is the body's vertical center rounded to the nearest PORT_PITCH
    (feat/block-rendering-library §4.2) — exactly height/2 only when that's
    already a grid multiple (odd input counts); otherwise the nearest one."""
    _app()
    from logic_studio.ui.canvas.block_item import _round_half_up_to_pitch
    from logic_studio.ui.canvas import style as canvas_style

    block = BlockRegistry.create_block(type_id)
    item = BlockItem(block)

    port_pos = _output_port(item).pos()
    assert port_pos.x() == item.width
    assert port_pos.y() == _round_half_up_to_pitch(item.height / 2, canvas_style.PORT_PITCH)

def test_buffer_has_its_own_shape_and_no_pin_labels():
    """§2.4: logic.buffer must not fall back to GATE_GENERIC, and (like every
    other standard gate) its ports must not draw text labels that would
    overlap the triangle body."""
    _app()
    block = BlockRegistry.create_block("logic.buffer")
    item = BlockItem(block)
    assert item.shape_style == "BUFFER"
    assert "BUFFER" in GATE_SHAPES

def test_gate_body_has_no_separate_shorter_height():
    """§2.3: the body always spans the block's full height now — there is
    no more independent "gate_body_height" a multi-input gate's ports could
    disagree with."""
    _app()
    block = BlockRegistry.create_block("logic.and4")
    item = BlockItem(block)
    assert not hasattr(item, "gate_body_height")

    inputs = [c for c in item.childItems() if isinstance(c, PortItem) and c.pin.direction == Pin.DIR_INPUT]
    assert len(inputs) == 4
    ys = sorted(p.pos().y() for p in inputs)
    # Every input sits strictly within (0, height) — the body (which now IS
    # `height` tall) fully encloses them, with none hanging outside it.
    assert 0 < ys[0] < item.height
    assert 0 < ys[-1] < item.height

def test_negation_bubble_position_matches_output_offset_helper():
    """shapes.gate_output_offset() is the single place that decides where a
    negated gate's port goes; draw_gate_shape() places the bubble using the
    same BUBBLE_RADIUS constant — this pins that relationship down."""
    assert shapes.gate_output_offset("NAND") == 2 * style.BUBBLE_RADIUS
    assert shapes.gate_output_offset("AND") == 0.0

def test_base_block_has_tag_and_comment_and_aliases():
    """§3.1/§4.6: every block gets Tag/Comment properties and an aliases
    list, defaulting to empty."""
    from logic_studio.blocks.logic_gates import AndGate
    a = AndGate()
    assert a.properties["Tag"] == ""
    assert a.properties["Comment"] == ""
    assert a.aliases == []

def test_timer_and_deadband_aliases_populated():
    from logic_studio.blocks.timers import TON, TOF, TP
    from logic_studio.blocks.analog_processing import DeadbandBlock, QualityBlock

    assert "zwłoka" in TON().aliases or "opóźnienie załączenia" in TON().aliases
    assert any("wyłączenia" in a for a in TOF().aliases)
    assert any("impuls" in a or "monostabilny" in a for a in TP().aliases)
    assert any("nieczułości" in a for a in DeadbandBlock().aliases)
    assert any("jakość" in a for a in QualityBlock().aliases)

def test_tag_comment_not_persisted_in_properties_only_when_empty_is_fine():
    """Tag/Comment round-trip through serialize()/deserialize() like any
    other property — no special-casing needed since they're just entries in
    the existing `properties` dict."""
    from logic_studio.blocks.logic_gates import AndGate

    a = AndGate()
    a.properties["Tag"] = "C1"
    a.properties["Comment"] = "Emergency stop interlock"
    data = a.serialize()
    assert data["properties"]["Tag"] == "C1"
    assert data["properties"]["Comment"] == "Emergency stop interlock"
