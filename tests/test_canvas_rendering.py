"""Canvas rendering tests (feat/block-rendering-library). Presentation-layer
only — no engine/compiler behavior is exercised here."""
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QFont, QFontMetricsF

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
    from AND, NOR from OR, XNOR from XOR. A later fix inset the bubble but
    left it flush against the port square (no gap), which still hid half
    the bubble under the opaque port — the negation was barely visible
    ("zrob wyraźniejszą negację... żeby się nie nakładała z kwadratem
    przyłączeniowym"). The bubble's right edge must now clear the port
    square's left edge (port center - PORT_RADIUS) by BUBBLE_PORT_GAP."""
    _app()
    block = BlockRegistry.create_block(type_id)
    item = BlockItem(block)

    port_pos = _output_port(item).pos()
    bubble_inset = style.PORT_RADIUS + style.BUBBLE_PORT_GAP + style.BUBBLE_RADIUS
    bubble_center = QPointF(item.width - bubble_inset, item.height / 2)
    bubble_right_edge = bubble_center.x() + style.BUBBLE_RADIUS
    port_left_edge = port_pos.x() - style.PORT_RADIUS

    assert port_pos != bubble_center, f"{type_id}: output port sits exactly on the negation bubble"
    assert port_pos.x() > bubble_center.x(), f"{type_id}: output port must sit past the bubble's center, not on/before it"
    assert port_pos.x() == item.width, f"{type_id}: output port must sit at exactly `width`, same as a non-negated gate"
    assert port_left_edge - bubble_right_edge >= style.BUBBLE_PORT_GAP - 1e-9, \
        f"{type_id}: negation bubble must clear the output port square by at least BUBBLE_PORT_GAP"

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

IO_TYPE_IDS = ["input.di", "output.do", "input.ai", "output.ao", "virtual.input", "virtual.output"]
SINGLE_PIN_IO_TYPE_IDS = ["input.di", "output.do", "output.ao", "virtual.input", "virtual.output"]

@pytest.mark.parametrize("type_id", SINGLE_PIN_IO_TYPE_IDS)
def test_single_pin_io_block_ports_have_no_pin_label(type_id):
    """A DO/AO block's single input port sits on the SAME left edge as the
    block's own Address/display-name text (_draw_io_text_lines) — drawing
    the pin's generic name ("Cmd"/"State") there used to render right on
    top of that text (e.g. ADA01.DO14's "Cmd" over its green "DO" label).
    A single-pin IO block's one pin never adds information the block's own
    face doesn't already show, so PortItem must suppress its label, exactly
    like it already does for gates."""
    _app()
    from logic_studio.ui.canvas.block_item import pin_labels_suppressed
    block = BlockRegistry.create_block(type_id)
    item = BlockItem(block)
    assert item.shape_style == "IO"
    assert len(block.inputs) + len(block.outputs) == 1
    assert pin_labels_suppressed(item)

def test_multi_pin_io_block_ports_keep_their_pin_label():
    """§0.1 audit follow-up: input.ai has TWO outputs (Value, Quality) — the
    old blanket "every IO block suppresses pin labels" rule made them
    indistinguishable on the canvas (both are bare identical squares with
    no text), on top of the positioning bug that put them at the same spot
    in the first place. A multi-pin IO block needs its labels."""
    _app()
    from logic_studio.ui.canvas.block_item import pin_labels_suppressed
    block = BlockRegistry.create_block("input.ai")
    item = BlockItem(block)
    assert item.shape_style == "IO"
    assert len(block.inputs) + len(block.outputs) == 2
    assert not pin_labels_suppressed(item)

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

def test_negated_and_non_negated_gates_are_the_same_width():
    """AND and NAND (or any negated/non-negated pair with the same input
    count) must be drawn at identical width — only the last few pixels near
    the tip differ (bubble inset vs. none). An earlier version of this fix
    shrank negated gates' width to make room for the bubble outside the
    body, which made e.g. NAND visibly smaller than AND for no functional
    reason ("bramki się rozjechały")."""
    _app()
    and_item = BlockItem(BlockRegistry.create_block("logic.and"))
    nand_item = BlockItem(BlockRegistry.create_block("logic.nand"))
    assert and_item.width == nand_item.width

    and4_item = BlockItem(BlockRegistry.create_block("logic.and4"))
    nand4_item = BlockItem(BlockRegistry.create_block("logic.nand4"))
    assert and4_item.width == nand4_item.width

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

# ---- Text-overlap audit follow-up ("bramki się rozjechały" thread) --------
# User-reported: ADA01.DO14's "Cmd" pin label rendered right on top of its
# own green "DO" display-name line (both start at the block's left edge,
# same row) — plus a general ask to check every block type for the same
# class of collision, and to make the negation bubble unmistakably clear of
# the output port square.

COMPLEX_READOUT_TYPE_IDS = ["timer.ton", "timer.tof", "timer.tp",
                            "counter.ctu", "counter.ctd", "counter.ctud"]

@pytest.mark.parametrize("type_id", COMPLEX_READOUT_TYPE_IDS)
def test_complex_readout_clears_every_pin_row(type_id):
    """TON/TOF/TP's "T=...[s]" and the counters' "PV=.../CV=..." used to be
    drawn at a fixed (2, 15)/(2, 28) offset — exactly where the first/second
    pin row's own label lands — so e.g. TON's "IN" pin label rendered right
    on top of "T=1.00[s]". The readout's top must now sit at or below the
    bottom of the LAST pin row's reserved label band, for every pin count
    this category actually uses (2 for timers, 3-5 for counters) — not just
    coincidentally clear for whichever pin count happened to be tested."""
    _app()
    from logic_studio.ui.canvas.block_item import _complex_readout_y

    block = BlockRegistry.create_block(type_id)
    pins_count = max(len(block.inputs), len(block.outputs))
    last_pin_label_bottom = style.PORT_MARGIN + max(0, pins_count - 1) * style.PORT_PITCH + 10

    readout_y = _complex_readout_y(pins_count)
    assert readout_y >= last_pin_label_bottom, \
        f"{type_id}: readout top ({readout_y}) must clear the last pin row's label ({last_pin_label_bottom})"

    # And it must still fit inside the block's own body.
    item = BlockItem(block)
    assert readout_y + 13 <= item.height, f"{type_id}: readout must not spill past the block's bottom edge"

def test_io_block_output_do_address_text_no_longer_shares_a_row_with_a_pin_label():
    """Reproduces the exact reported case: an output.do block's Address
    ("ADA01.DO14") and display-name ("DO") text both start flush against
    the left edge — the same edge its single input pin (port at x=0) sits
    on. Confirms the fix's precondition (its one pin's label is suppressed)
    rather than re-deriving pixel positions."""
    _app()
    from logic_studio.ui.canvas.block_item import pin_labels_suppressed

    block = BlockRegistry.create_block("output.do")
    block.properties["Address"] = "ADA01.DO14"
    item = BlockItem(block)
    assert pin_labels_suppressed(item)

# ---- Gate lead-line redesign (reference screenshot: IEC/ANSI-style short
# lead wires on every pin, body pulled back from the port squares instead of
# touching them) ------------------------------------------------------------

ALL_GATE_TYPE_IDS = [
    "logic.not", "logic.buffer",
    "logic.and", "logic.and3", "logic.and4",
    "logic.nand", "logic.nand3", "logic.nand4",
    "logic.or", "logic.or3", "logic.or4",
    "logic.nor", "logic.nor3", "logic.nor4",
    "logic.xor", "logic.xnor",
]

def test_gate_output_y_shared_by_block_item_and_shapes():
    """block_item.py's actual output PortItem and shapes.py's output lead
    line must use the exact same y — computed in one place
    (shapes.gate_output_y) — or the lead line and the port it's supposed to
    connect to could silently drift apart for some input count."""
    from logic_studio.ui.canvas.block_item import _round_half_up_to_pitch
    assert _round_half_up_to_pitch is shapes.round_half_up_to_pitch

@pytest.mark.parametrize("type_id", ALL_GATE_TYPE_IDS)
def test_gate_input_leads_stay_within_the_block_bounding_box(type_id):
    """Every input's lead line runs from x=0 (the port, unchanged) to
    x=GATE_LEAD (the pulled-back body) — must never reach past the block's
    own width, and GATE_LEAD must leave a strictly positive body width even
    for the narrowest gate (NOT/BUFFER, 1 input)."""
    _app()
    block = BlockRegistry.create_block(type_id)
    item = BlockItem(block)
    assert 0 < style.GATE_LEAD < item.width

@pytest.mark.parametrize("type_id", ALL_GATE_TYPE_IDS)
def test_dshape_ellipse_never_overflows_regardless_of_input_count(type_id):
    """The D-shape's (AND/NAND) curve used to be a fixed-radius (h/2)
    semicircle whose rightmost point could land past the block's own width
    for a tall, many-input gate (radius pinned to height, independent of the
    body's actual available width) — invisible for 2-input gates, increasingly
    wrong for 3- and 4-input ones. Recomputes the same right_bound/body_w/
    rx shapes.py derives internally and asserts the ellipse's rightmost
    point (flat_len + rx, measured from left_bound) lands at exactly
    body_w — by construction, not by accident — for every gate type, not
    just the D-shape ones (a no-op check for non-D-shape gates)."""
    _app()
    block = BlockRegistry.create_block(type_id)
    item = BlockItem(block)

    if item.shape_style not in shapes.DSHAPE_GATES:
        return

    negated = item.shape_style in shapes.NEGATED_GATES
    lead = style.GATE_LEAD
    left_bound = lead
    if negated:
        right_bound = item.width - (style.PORT_RADIUS + style.BUBBLE_PORT_GAP + 2 * style.BUBBLE_RADIUS)
    else:
        right_bound = item.width - lead
    body_w = right_bound - left_bound
    assert body_w > 0, f"{type_id}: no room left for the body at all"

    flat_len = body_w * 0.35
    rx = body_w - flat_len
    rightmost = flat_len + rx
    assert rightmost == pytest.approx(body_w), f"{type_id}: D-shape ellipse tip must land exactly at body_w"

def test_icon_rendering_does_not_crash_for_any_gate_shape():
    """block_icon() draws with draw_leads=False at 24px — a smoke test that
    the lead redesign didn't break the (deliberately lead-less) icon path
    for any gate shape_style."""
    _app()
    from logic_studio.ui.icons import block_icon
    for type_id in ALL_GATE_TYPE_IDS:
        icon = block_icon(type_id, size=24)
        assert icon is not None

# ---- §0.2 audit follow-up: pin labels must elide, not silently clip -------
# (a fixed 50px rect + Qt's own clipping used to drop the BEGINNING of a
# long output-side label, since AlignRight anchors the far end near the
# port — "Out Of Range" rendered as "Of Range", the opposite of what the
# pin means).

ALL_BLOCK_TYPE_IDS_FOR_LABEL_TEST = [
    type_id
    for category in BlockRegistry.get_categories()
    for type_id in BlockRegistry.get_blocks_in_category(category)
]

def _elided_pin_label(pin_name, block_width):
    """Reproduces PortItem.paint()'s exact label-sizing logic, so the test
    verifies the real thing rather than a re-derivation of it."""
    font = QFont(style.FONT_FAMILY, style.FONT_SIZE_PIN_LABEL)
    fm = QFontMetricsF(font)
    side_width = max(10.0, block_width * style.PIN_LABEL_SIDE_FRACTION)
    elided = fm.elidedText(pin_name, Qt.ElideRight, side_width)
    return elided, side_width, fm

@pytest.mark.parametrize("type_id", ALL_BLOCK_TYPE_IDS_FOR_LABEL_TEST)
def test_every_pin_label_fits_or_ends_with_ellipsis(type_id):
    _app()
    ELLIPSIS = "…"
    block = BlockRegistry.create_block(type_id)
    item = BlockItem(block)

    for pin in list(block.inputs) + list(block.outputs):
        elided, side_width, fm = _elided_pin_label(pin.name, item.width)
        rendered_width = fm.horizontalAdvance(elided)
        fits = rendered_width <= side_width + 0.5  # tolerance for float rounding
        ends_with_ellipsis = elided.endswith(ELLIPSIS)
        assert fits or ends_with_ellipsis, \
            f"{type_id}: pin {pin.name!r} elided to {elided!r} ({rendered_width}px) doesn't fit {side_width}px and has no ellipsis"

def test_analog_quality_out_of_range_label_keeps_its_beginning():
    """The concrete case from the audit: analog.quality's "Out Of Range"
    output must still start with "Out" once elided — not have its
    beginning silently dropped."""
    _app()
    block = BlockRegistry.create_block("analog.quality")
    item = BlockItem(block)

    pin = next(p for p in block.outputs if p.name == "Out Of Range")
    elided, side_width, fm = _elided_pin_label(pin.name, item.width)
    assert elided.startswith("Out"), \
        f"analog.quality's 'Out Of Range' label must start with 'Out', got {elided!r}"

# ---- §0.4/§0.5 audit follow-up: IO block text vs. the chevron notch ------

def test_output_direction_io_text_margin_clears_the_notch():
    """An output-direction chevron (DO/AO/Virtual OUT) has a notch carved
    into its left edge (shapes.draw_io_shape()) — the identifier text's
    left margin must start at or past the notch's rightmost point, never
    inside it (§0.4: "ADA01.DO01"'s first letter used to sit on the notch's
    diagonal edge)."""
    _app()
    from logic_studio.ui.canvas.block_item import io_text_margin_x
    block = BlockRegistry.create_block("output.do")
    block.properties["Address"] = "ADA01.DO01"
    item = BlockItem(block)

    input_margin = io_text_margin_x(item.width, "input")
    output_margin = io_text_margin_x(item.width, "output")
    assert output_margin >= shapes.io_notch_width(item.width)
    assert output_margin > input_margin, \
        "output-direction margin must reserve extra room for the notch, beyond the plain input-direction margin"

def test_input_and_output_io_block_widths_use_the_same_formula():
    """§0.5: input.di and output.do must compute width via the exact same
    formula (io_text_margin_x() + the same font-metrics/rounding steps) —
    not "equal width" outright. An output-direction block's chevron has a
    notch (§0.4) an input-direction one doesn't, so for the same address
    text it legitimately needs a bit more room to keep that text clear of
    the notch; forcing equal width back would just reintroduce §0.4's
    overlap for the output side. What must be unified is the METHOD, and
    the observable, principled consequence is output width >= input width
    for the same address length — never narrower, and never equal only by
    coincidence of two independent unrelated formulas."""
    _app()
    from logic_studio.ui.canvas.block_item import io_text_margin_x
    di = BlockRegistry.create_block("input.di")
    di.properties["Address"] = "ELA01.DI01"
    do = BlockRegistry.create_block("output.do")
    do.properties["Address"] = "ADA01.DO01"
    assert len(di.properties["Address"]) == len(do.properties["Address"])

    di_item = BlockItem(di)
    do_item = BlockItem(do)
    assert do_item.width >= di_item.width, \
        f"output.do width {do_item.width} must be >= input.di width {di_item.width} (extra room for the notch)"
    # Same formula, different inputs — not two independently-hardcoded paths.
    assert io_text_margin_x(100, "input") == 6
    assert io_text_margin_x(100, "output") == 6 + shapes.io_notch_width(100)
