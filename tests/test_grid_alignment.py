"""feat/block-rendering-library §4 — "the most important section of this
PR": every connection point (port), on every registered block type, must
land on a grid intersection in the block's own local coordinates (and
therefore, combined with a grid-aligned block origin, in scene coordinates
too). This is the single most important test in the PR (§4.7/§12.5).

Two tiers since the grid-density redesign ("bramki są spłaszczone...
zagęścisz siatkę"): GRID_SIZE (20) is the coarse grid block ORIGINS snap to;
PORT_PITCH (10, a GRID_SIZE divisor) is the finer grid individual PORTS and
a block's own HEIGHT land on — checked here against PORT_PITCH, the true
finest deterministic unit every position in the app is now built from.
Block WIDTH and origin position stay GRID_SIZE-based and are checked
against that, unchanged."""
import pytest
from PySide6.QtWidgets import QApplication

from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.ui.canvas.block_item import BlockItem
from logic_studio.ui.canvas.port_item import PortItem
from logic_studio.ui.canvas import style


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


register_builtin_blocks()

ALL_TYPE_IDS = [
    type_id
    for category in BlockRegistry.get_categories()
    for type_id in BlockRegistry.get_blocks_in_category(category)
]


@pytest.mark.parametrize("type_id", ALL_TYPE_IDS)
def test_every_port_lands_on_grid_intersection(type_id):
    _app()
    block = BlockRegistry.create_block(type_id)
    item = BlockItem(block)

    ports = [c for c in item.childItems() if isinstance(c, PortItem)]
    for port in ports:
        pos = port.pos()
        assert pos.x() % style.PORT_PITCH == 0, \
            f"{type_id}: port {port.pin.name!r} x={pos.x()} is not a multiple of PORT_PITCH ({style.PORT_PITCH})"
        assert pos.y() % style.PORT_PITCH == 0, \
            f"{type_id}: port {port.pin.name!r} y={pos.y()} is not a multiple of PORT_PITCH ({style.PORT_PITCH})"

def test_every_registered_type_covered():
    """Guards the parametrization itself: if BlockRegistry ever comes back
    empty (e.g. register_builtin_blocks() not called), the test above would
    silently collect zero cases and "pass" without checking anything."""
    assert len(ALL_TYPE_IDS) >= 60  # 67 at the time this test was written

def test_block_height_is_a_grid_multiple():
    """Gates' height is now built directly from PORT_MARGIN/PORT_PITCH with
    no rounding-up to GRID_SIZE (that rounding was what reintroduced
    asymmetric top/bottom margin around the ports — see
    BlockItem._determine_shape_style()) — so this checks PORT_PITCH, the
    unit height is actually built from, not GRID_SIZE."""
    for type_id in ALL_TYPE_IDS:
        block = BlockRegistry.create_block(type_id)
        item = BlockItem(block)
        assert item.height % style.PORT_PITCH == 0, f"{type_id}: height {item.height} not a PORT_PITCH multiple"

def test_deserialize_realigns_off_grid_block_positions():
    """§4.6: a project saved with an off-grid block position (e.g. from
    free-form dragging before snap-on-move existed) is realigned to the
    grid on load — a no-op for anything already aligned."""
    from logic_studio.core.project import Project
    from logic_studio.blocks.logic_gates import AndGate

    p = Project()
    b = AndGate()
    b.set_position(137, 54)  # deliberately off-grid
    p.add_block(b)

    data = p.serialize()
    assert data["blocks"][0]["position"] == {"x": 137, "y": 54}

    reloaded = Project.deserialize(data)
    block = reloaded.blocks[0]
    assert block.x % style.GRID_SIZE == 0
    assert block.y % style.GRID_SIZE == 0
    # Rounds to the nearest multiple, not just floors/truncates.
    assert block.x == 140
    assert block.y == 60

def test_deserialize_leaves_on_grid_positions_untouched():
    from logic_studio.core.project import Project
    from logic_studio.blocks.logic_gates import AndGate

    p = Project()
    b = AndGate()
    b.set_position(100, 200)
    p.add_block(b)

    reloaded = Project.deserialize(p.serialize())
    assert reloaded.blocks[0].x == 100
    assert reloaded.blocks[0].y == 200

def test_block_width_is_a_grid_multiple():
    """Every block's width is a GRID_SIZE multiple on its own — including
    negated gates, which are the same width as their non-negated sibling
    (the bubble is drawn inset near the tip, not by narrowing the body; see
    shapes.draw_gate_shape())."""
    for type_id in ALL_TYPE_IDS:
        block = BlockRegistry.create_block(type_id)
        item = BlockItem(block)
        assert item.width % style.GRID_SIZE == 0, f"{type_id}: width {item.width} not a GRID_SIZE multiple"

# ---- Grid-density redesign ("bramki są spłaszczone... zagęścisz siatkę
# żeby rozmieścić przyłącza symetrycznie") ----------------------------------

GATE_TYPE_IDS_BY_INPUT_COUNT = [
    ("logic.not", 1), ("logic.and", 2), ("logic.and3", 3), ("logic.and4", 4),
    ("logic.nand", 2), ("logic.nand3", 3), ("logic.nand4", 4),
]

@pytest.mark.parametrize("type_id,inputs_count", GATE_TYPE_IDS_BY_INPUT_COUNT)
def test_gate_input_pins_are_vertically_symmetric_in_the_body(type_id, inputs_count):
    """The whole point of the redesign: PORT_PITCH (10) is now finer than
    PORT_MARGIN (still GRID_SIZE, 20), so a multi-input gate's height is
    `2*PORT_MARGIN + (n-1)*PORT_PITCH` — not the old `(n+1)*PORT_PITCH`,
    which only produced a symmetric result back when PORT_MARGIN and
    PORT_PITCH happened to be equal.

    §0.3 audit follow-up: height is additionally rounded UP to a multiple
    of 2*PORT_PITCH so height/2 always lands exactly on a PORT_PITCH
    multiple (gate_output_y(h) == h/2 exactly, everywhere — see
    test_gate_output_y_matches_body_center_exactly below) — the output
    port must sit exactly where the D-shape/shield curve's tip actually is,
    not wherever the nearest PORT_PITCH multiple to the true center happens
    to be. For an ODD input count the raw (unrounded) height was already a
    2*PORT_PITCH multiple, so this costs nothing — margins stay exactly
    symmetric. For an EVEN input count it adds one extra PORT_PITCH of
    height, all of it below the last input (top margin is still exactly
    PORT_MARGIN) — a known, deliberate trade-off, not a regression."""
    _app()
    from logic_studio.blocks.pin import Pin

    block = BlockRegistry.create_block(type_id)
    item = BlockItem(block)
    assert len(block.inputs) == inputs_count

    input_ys = sorted(c.pos().y() for c in item.childItems()
                       if isinstance(c, PortItem) and c.pin.direction == Pin.DIR_INPUT)

    top_margin = input_ys[0]
    bottom_margin = item.height - input_ys[-1]
    assert top_margin == style.PORT_MARGIN

    expected_extra = 0 if inputs_count % 2 == 1 else style.PORT_PITCH
    assert bottom_margin == top_margin + expected_extra, \
        f"{type_id}: top margin {top_margin}, bottom margin {bottom_margin} — expected bottom == top + {expected_extra}"

def test_four_input_gate_is_shorter_than_before_the_grid_density_redesign():
    """Concrete regression pin: a 4-input gate used to be
    (4+1)*20 = 100px tall against a fixed 40px width (2.5:1) — tall enough
    that the D-shape curve's vertical extent (h/2) badly outstripped the
    horizontal room actually available for it, reading as "flattened"
    ("bramki są spłaszczone"). It must now be meaningfully shorter."""
    _app()
    block = BlockRegistry.create_block("logic.and4")
    item = BlockItem(block)
    assert item.height < 100
    # 2*PORT_MARGIN + 3*PORT_PITCH = 70, rounded up to the next 2*PORT_PITCH
    # multiple (§0.3) = 80.
    raw_height = 2 * style.PORT_MARGIN + 3 * style.PORT_PITCH
    import math
    assert item.height == math.ceil(raw_height / (2 * style.PORT_PITCH)) * (2 * style.PORT_PITCH)

# ---- §0.1 audit follow-up: input.ai's Value and Quality outputs used to
# both land at exactly (width, PORT_MARGIN) — same position, so a click
# always hit whichever was on top in Z-order and the other was simply
# unreachable by a wire. This is the test that would have caught it two PRs
# earlier, per the audit's own framing. -------------------------------------

@pytest.mark.parametrize("type_id", ALL_TYPE_IDS)
def test_no_two_ports_share_a_position(type_id):
    _app()
    block = BlockRegistry.create_block(type_id)
    item = BlockItem(block)

    ports = [c for c in item.childItems() if isinstance(c, PortItem)]
    positions = [(p.pos().x(), p.pos().y()) for p in ports]
    seen = set()
    for port, pos in zip(ports, positions):
        assert pos not in seen, \
            f"{type_id}: port {port.pin.name!r} at {pos} overlaps another port at the exact same position"
        seen.add(pos)

# ---- §0.3 audit follow-up: the output port must sit exactly on the body's
# vertical center, not the nearest PORT_PITCH multiple to it — for an even
# input count those used to differ by up to PORT_PITCH/2, visibly
# separating the D-shape/shield curve's tip from the output port square. --

GATE_TYPE_IDS = [
    type_id
    for category in BlockRegistry.get_categories()
    for type_id in BlockRegistry.get_blocks_in_category(category)
    if BlockRegistry.create_block(type_id).category == "Bramki logiczne"
]

@pytest.mark.parametrize("type_id", GATE_TYPE_IDS)
def test_gate_output_y_matches_body_center_exactly(type_id):
    from logic_studio.ui.canvas import shapes as canvas_shapes

    block = BlockRegistry.create_block(type_id)
    item = BlockItem(block)
    assert canvas_shapes.gate_output_y(item.height) == item.height / 2, \
        f"{type_id}: gate_output_y({item.height}) != {item.height}/2 — output port not on the body's true center"
