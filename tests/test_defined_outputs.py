"""fix/safety-block-semantics §8: no block may leave an output as None
after evaluate() -- checked whether this test already existed in the
repository before writing it (per §8.3's own instruction): it did not.
The closest existing coverage, tests/test_block_disable.py's "outputs get
a defined value after a scan, never None" section, is a narrower, later
check specific to a DISABLED block being forced to a safe value
(ExecutionEngine.step()'s own step 0) -- not a general audit of every
registered block type's own evaluate(), which is what this file adds.

Found and fixed by the audit this test locks in (see the branch's other
commits' analog_processing.py/timers.py diffs for the actual fixes):
analog.deadband (§8.1, both outputs), analog.scale, analog.limit,
analog.hysteresis, analog.mov_avg (all four: Out), and timer.tof (ET, in
its idle/never-triggered state) all left an output at None for a fresh
block evaluated with nothing wired to its input(s).
"""
import pytest

from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry

register_builtin_blocks()


def _every_executable_type_id():
    """Every registered block type EXCEPT "Dokumentacja" -- those are
    non-executable (GraphBuilder excludes them from execution_order
    entirely, see compiler/graph.py) and have no evaluate() contract to
    check in the first place."""
    ids = []
    for category in BlockRegistry.get_categories():
        if category == "Dokumentacja":
            continue
        ids.extend(BlockRegistry.get_blocks_in_category(category))
    return ids


@pytest.mark.parametrize("type_id", _every_executable_type_id())
def test_block_never_leaves_an_output_as_none(type_id):
    """A freshly-constructed instance of every registered, executable
    block type, reset to cold state and evaluated with NOTHING wired to
    any of its inputs (every input pin's .value is None, its own
    __init__ default) -- no output may come out of that None. This is
    the worst case every block will see the moment it's placed on the
    canvas, before a single wire is drawn."""
    block = BlockRegistry.create_block(type_id)
    block.reset_runtime_state()
    block.evaluate(engine=None)

    for pin in block.outputs:
        assert pin.value is not None, (
            f"{type_id}: output '{pin.name}' is None after evaluate() "
            "with no inputs connected"
        )
