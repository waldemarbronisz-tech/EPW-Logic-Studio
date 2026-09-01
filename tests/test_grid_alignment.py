"""feat/block-rendering-library §4 — "the most important section of this
PR": every connection point (port), on every registered block type, must
land on a grid intersection in the block's own local coordinates (and
therefore, combined with a grid-aligned block origin, in scene coordinates
too). This is the single most important test in the PR (§4.7/§12.5)."""
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
        assert pos.x() % style.GRID_SIZE == 0, \
            f"{type_id}: port {port.pin.name!r} x={pos.x()} is not a multiple of GRID_SIZE ({style.GRID_SIZE})"
        assert pos.y() % style.GRID_SIZE == 0, \
            f"{type_id}: port {port.pin.name!r} y={pos.y()} is not a multiple of GRID_SIZE ({style.GRID_SIZE})"

def test_every_registered_type_covered():
    """Guards the parametrization itself: if BlockRegistry ever comes back
    empty (e.g. register_builtin_blocks() not called), the test above would
    silently collect zero cases and "pass" without checking anything."""
    assert len(ALL_TYPE_IDS) >= 60  # 67 at the time this test was written

def test_block_height_is_a_grid_multiple():
    for type_id in ALL_TYPE_IDS:
        block = BlockRegistry.create_block(type_id)
        item = BlockItem(block)
        assert item.height % style.GRID_SIZE == 0, f"{type_id}: height {item.height} not a GRID_SIZE multiple"

def test_block_width_is_a_grid_multiple_once_the_output_offset_is_added():
    """A negated gate's body (width) is intentionally narrower than a grid
    multiple — see block_item._determine_shape_style(): its output port sits
    past the negation bubble at width + output_offset, and it's THAT sum
    which is guaranteed to land on the grid (identically to the non-negated
    sibling's port position, output_offset=0). Every other shape's width has
    no offset and must be a grid multiple on its own."""
    from logic_studio.ui.canvas import shapes

    for type_id in ALL_TYPE_IDS:
        block = BlockRegistry.create_block(type_id)
        item = BlockItem(block)
        offset = shapes.gate_output_offset(item.shape_style) if item.shape_style in shapes.NEGATED_GATES else 0
        assert (item.width + offset) % style.GRID_SIZE == 0, \
            f"{type_id}: width {item.width} + output_offset {offset} not a GRID_SIZE multiple"
