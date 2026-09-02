"""feat/block-rendering-library §4 — "the most important section of this
PR": every connection point (port), on every registered block type, must
land on a grid intersection in the block's own local coordinates (and
therefore, combined with a grid-aligned block origin, in scene coordinates
too). This is the single most important test in the PR (§4.7/§12.5).

feat/editor-modes-and-geometry §1 superseded the previous "denser pin-pitch
grid" design entirely: GRID_SNAP (10) is the block-placement grid AND the
true finest deterministic unit every port position is built from; PORT_PITCH
(20, a GRID_SNAP multiple) is the spacing between a block's own consecutive
ports, symmetric around its vertical center — no longer anchored from the
top edge. Checked here against GRID_SNAP, not PORT_PITCH — a port can land
on an odd multiple of GRID_SNAP that isn't itself a PORT_PITCH multiple
(e.g. input.ai's two outputs, at center ± PORT_PITCH/2)."""
import pytest
from PySide6.QtWidgets import QApplication

from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.ui.canvas.block_item import BlockItem
from logic_studio.ui.canvas.port_item import PortItem
from logic_studio.ui.canvas import style, shapes


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

GATE_TYPE_IDS = [
    type_id
    for category in BlockRegistry.get_categories()
    for type_id in BlockRegistry.get_blocks_in_category(category)
    if BlockRegistry.create_block(type_id).category == "Bramki logiczne"
]


@pytest.mark.parametrize("type_id", ALL_TYPE_IDS)
def test_every_port_lands_on_grid_intersection(type_id):
    _app()
    block = BlockRegistry.create_block(type_id)
    item = BlockItem(block)

    ports = [c for c in item.childItems() if isinstance(c, PortItem)]
    for port in ports:
        pos = port.pos()
        assert pos.x() % style.GRID_SNAP == 0, \
            f"{type_id}: port {port.pin.name!r} x={pos.x()} is not a multiple of GRID_SNAP ({style.GRID_SNAP})"
        assert pos.y() % style.GRID_SNAP == 0, \
            f"{type_id}: port {port.pin.name!r} y={pos.y()} is not a multiple of GRID_SNAP ({style.GRID_SNAP})"

def test_every_registered_type_covered():
    """Guards the parametrization itself: if BlockRegistry ever comes back
    empty (e.g. register_builtin_blocks() not called), the test above would
    silently collect zero cases and "pass" without checking anything."""
    assert len(ALL_TYPE_IDS) >= 60  # 67 at the time this test was written

def test_block_height_is_a_grid_multiple():
    """Every block's height is a GRID_SNAP multiple — built from GATE_BODY/
    PORT_PITCH (both GRID_SNAP multiples themselves) with no further
    rounding needed, unlike the old design's §0.3 workaround."""
    for type_id in ALL_TYPE_IDS:
        block = BlockRegistry.create_block(type_id)
        item = BlockItem(block)
        assert item.height % style.GRID_SNAP == 0, f"{type_id}: height {item.height} not a GRID_SNAP multiple"

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
    assert block.x % style.GRID_SNAP == 0
    assert block.y % style.GRID_SNAP == 0
    # Rounds to the nearest multiple, not just floors/truncates.
    assert block.x == 140
    assert block.y == 50

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
    """Every block's width is a GRID_SNAP multiple on its own — including
    negated gates, which are the same width as their non-negated sibling
    (the bubble is drawn inset near the tip, not by narrowing the body; see
    shapes.draw_gate_shape())."""
    for type_id in ALL_TYPE_IDS:
        block = BlockRegistry.create_block(type_id)
        item = BlockItem(block)
        assert item.width % style.GRID_SNAP == 0, f"{type_id}: width {item.width} not a GRID_SNAP multiple"

# ---- feat/editor-modes-and-geometry §1: fixed body + input rail ----------

GATE_TYPE_IDS_BY_INPUT_COUNT = [
    ("logic.not", 1), ("logic.and", 2), ("logic.and3", 3), ("logic.and4", 4),
    ("logic.nand", 2), ("logic.nand3", 3), ("logic.nand4", 4),
]

@pytest.mark.parametrize("type_id,inputs_count", GATE_TYPE_IDS_BY_INPUT_COUNT)
def test_gate_geometry_matches_the_spec_table(type_id, inputs_count):
    """§1.2's own table, checked exactly (no tolerance): height, every
    input y, and the output y for 1 through 5 inputs (5 has no registered
    gate type, but the height/input-position formula is still exercised
    for it in test_gate_height_formula_matches_spec_for_five_inputs)."""
    _app()
    from logic_studio.blocks.pin import Pin

    block = BlockRegistry.create_block(type_id)
    item = BlockItem(block)
    assert len(block.inputs) == inputs_count

    expected_height = {1: 40, 2: 40, 3: 60, 4: 80}[inputs_count]
    assert item.height == expected_height

    input_ys = sorted(c.pos().y() for c in item.childItems()
                       if isinstance(c, PortItem) and c.pin.direction == Pin.DIR_INPUT)
    expected_input_ys = {
        1: [20],
        2: [10, 30],
        3: [10, 30, 50],
        4: [10, 30, 50, 70],
    }[inputs_count]
    assert input_ys == expected_input_ys

    output_port = next(c for c in item.childItems() if isinstance(c, PortItem) and c.pin.direction == Pin.DIR_OUTPUT)
    expected_output_y = {1: 20, 2: 20, 3: 30, 4: 40}[inputs_count]
    assert output_port.pos().y() == expected_output_y
    assert output_port.pos().y() == item.height / 2

def test_gate_height_formula_matches_spec_for_five_inputs():
    """No 5-input gate is registered, but §1.2's table specifies one —
    check the formula directly rather than only the registered 1-4 cases."""
    assert max(style.GATE_BODY, 5 * style.PORT_PITCH) == 100

def test_four_input_gate_is_shorter_than_before_the_old_grid_density_redesign():
    """Concrete regression pin: a 4-input gate used to be 80px tall under
    the intermediate "denser pitch" design, and 100px under the original
    (pre any redesign) one — both against a fixed 40px width. It's 80 now
    too under the NEW formula (coincidentally the same number, reached a
    completely different way: a fixed 40-tall body plus a 40px rail, not a
    stretched body), and — the actual point of §1 — the body's own drawn
    shape is now always exactly GATE_BODY tall regardless, never stretched."""
    _app()
    block = BlockRegistry.create_block("logic.and4")
    item = BlockItem(block)
    assert item.height == max(style.GATE_BODY, 4 * style.PORT_PITCH)
    assert item.height == 80

# ---- §0.1 audit follow-up: input.ai's Value and Quality outputs used to
# both land at exactly the same position, so a click always hit whichever
# was on top in Z-order and the other was simply unreachable by a wire.
# This is the test that would have caught it two PRs earlier, per the
# audit's own framing. -------------------------------------------------------

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

# ---- output always exactly at body center, no rounding ---------------------

@pytest.mark.parametrize("type_id", GATE_TYPE_IDS)
def test_gate_output_port_is_exactly_at_body_center(type_id):
    """§1: the output port sits at exactly height/2 by construction — no
    gate_output_y()/rounding function exists any more, because nothing
    needs it: height is built from GATE_BODY/PORT_PITCH (both GRID_SNAP
    multiples), which makes height/2 land exactly on a GRID_SNAP multiple
    for every input count, always."""
    from logic_studio.blocks.pin import Pin

    block = BlockRegistry.create_block(type_id)
    item = BlockItem(block)
    output_port = next(c for c in item.childItems() if isinstance(c, PortItem) and c.pin.direction == Pin.DIR_OUTPUT)
    assert output_port.pos().y() == item.height / 2

# ---- §1.3: the rail only appears once an input actually falls outside the
# fixed GATE_BODY square — never for 1-3 inputs, always for 4+. -------------

@pytest.mark.parametrize("type_id,inputs_count", [
    ("logic.not", 1), ("logic.and", 2), ("logic.and3", 3), ("logic.and4", 4),
])
def test_rail_needed_iff_input_falls_outside_fixed_body(type_id, inputs_count):
    _app()
    block = BlockRegistry.create_block(type_id)
    item = BlockItem(block)
    offsets = shapes.centered_port_offsets(inputs_count)
    needs_rail = any(abs(off) > style.GATE_BODY / 2 for off in offsets)
    assert needs_rail == (inputs_count >= 4), \
        f"{type_id}: rail-needed={needs_rail} but inputs_count={inputs_count}"

# ---- COMPLEX/IO: symmetric around center, same rule as gates --------------

def test_io_single_pin_block_port_is_at_center_of_a_40_tall_block():
    _app()
    from logic_studio.blocks.pin import Pin
    block = BlockRegistry.create_block("input.di")
    item = BlockItem(block)
    assert item.height == 40
    port = next(c for c in item.childItems() if isinstance(c, PortItem))
    assert port.pos().y() == 20

def test_io_multi_pin_block_ports_are_symmetric_around_center():
    _app()
    block = BlockRegistry.create_block("input.ai")
    item = BlockItem(block)
    assert item.height == 40  # §1.4: always 40, not the old special-cased 60
    ports = sorted((c.pos().y() for c in item.childItems() if isinstance(c, PortItem)))
    assert ports == [10, 30]

def test_complex_block_ports_symmetric_around_center_both_sides():
    _app()
    from logic_studio.blocks.pin import Pin
    block = BlockRegistry.create_block("counter.ctud")  # 5 inputs, 3 outputs
    item = BlockItem(block)
    center = item.height / 2

    in_ys = sorted(c.pos().y() for c in item.childItems() if isinstance(c, PortItem) and c.pin.direction == Pin.DIR_INPUT)
    out_ys = sorted(c.pos().y() for c in item.childItems() if isinstance(c, PortItem) and c.pin.direction == Pin.DIR_OUTPUT)

    assert in_ys == [center + off for off in shapes.centered_port_offsets(5)]
    assert out_ys == [center + off for off in shapes.centered_port_offsets(3)]
    # Both sides symmetric around the SAME center.
    assert (in_ys[0] + in_ys[-1]) / 2 == center
    assert (out_ys[0] + out_ys[-1]) / 2 == center

# ---- §1.6 migration: dropping GRID_SNAP from 20 to 10 needs no dedicated
# migration step — the existing unconditional realignment pass
# (Project.deserialize(), every load, not gated by schema_version) already
# re-rounds every block position against whatever GRID_SIZE currently is. --

def test_position_aligned_to_the_old_coarser_grid_survives_the_new_finer_one():
    """A position that was already a clean multiple of the OLD GRID_SIZE
    (20) is trivially also a multiple of the NEW one (10, a divisor of 20)
    — so the existing realignment pass leaves it untouched. This is the
    property that makes examples/*.epwlogic need zero position corrections
    under §1's grid change (verified empirically: 0/10 fixtures drifted)."""
    from logic_studio.core.project import Project
    from logic_studio.blocks.logic_gates import AndGate

    p = Project()
    b = AndGate()
    b.set_position(140, 60)  # a clean multiple of the old GRID_SIZE=20
    p.add_block(b)

    reloaded = Project.deserialize(p.serialize())
    assert reloaded.blocks[0].x == 140
    assert reloaded.blocks[0].y == 60
