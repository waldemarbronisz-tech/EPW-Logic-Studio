"""feat/macro-blocks — canvas rendering of a placed MacroInstanceBlock.
Presentation-layer only, no engine/compiler behavior exercised here (see
test_macros.py / test_macro_instance.py / test_compiler.py for those)."""
import pytest
from PySide6.QtWidgets import QApplication

from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.macro_instance import MacroInstanceBlock
from logic_studio.blocks.pin import Pin
from logic_studio.ui.canvas.block_item import BlockItem, GATE_SHAPES
from logic_studio.ui.canvas.port_item import PortItem


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


register_builtin_blocks()


def _configured_instance(n_in=2, n_out=1):
    block = MacroInstanceBlock(def_id="abc12345")
    block.configure({
        "name": "MojMakroblok",
        "blocks": [],
        "input_pins": [
            {"block_uuid": "b", "pin_name": f"In{i+1}", "data_type": Pin.TYPE_BOOLEAN, "label": f"In{i+1}"}
            for i in range(n_in)
        ],
        "output_pins": [
            {"block_uuid": "b", "pin_name": f"Out{i+1}", "data_type": Pin.TYPE_BOOLEAN, "label": f"Out{i+1}"}
            for i in range(n_out)
        ],
    })
    return block


def test_macro_instance_gets_its_own_distinct_shape_style():
    _app()
    item = BlockItem(_configured_instance())
    assert item.shape_style == "MACRO"
    assert item.shape_style not in GATE_SHAPES
    assert item.shape_style != "COMPLEX"

def test_macro_instance_creates_a_port_per_declared_pin():
    _app()
    item = BlockItem(_configured_instance(n_in=2, n_out=1))
    ports = [c for c in item.childItems() if isinstance(c, PortItem)]
    in_ports = [p for p in ports if p.pin.direction == Pin.DIR_INPUT]
    out_ports = [p for p in ports if p.pin.direction == Pin.DIR_OUTPUT]
    assert len(in_ports) == 2
    assert len(out_ports) == 1

def test_macro_instance_size_grows_with_pin_count():
    _app()
    small = BlockItem(_configured_instance(n_in=1, n_out=1))
    big = BlockItem(_configured_instance(n_in=6, n_out=1))
    assert big.height > small.height

def test_bare_macro_instance_renders_without_crashing():
    """An unconfigured "macro." instance (corrupt/edge-case data) must
    still construct and paint without raising — zero pins is a valid,
    if degenerate, shape."""
    _app()
    item = BlockItem(MacroInstanceBlock())
    assert item.shape_style == "MACRO"
    assert item.childItems() == []

def test_block_icon_renders_for_a_macro_type_id():
    """ui/icons.py's block_icon() must resolve "macro.<def_id>" through
    BlockRegistry (core/macros.py::macro_def_id()) instead of failing to
    find a registered class for it."""
    from logic_studio.ui.icons import block_icon
    icon = block_icon("macro.abc12345")
    assert not icon.isNull()
