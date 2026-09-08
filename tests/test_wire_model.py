"""feat/wire-labels §2 — Project-level integration: add_wire()'s own
validation, save/load round-trip through a real Project (not just raw
Wire.serialize()/deserialize(), see test_wire_serialization.py for
that), the v11->v12 schema migration, the §2.5 validator warning, and
§2.6's "a free end without a label creates no graph edge and never
raises" compiler behavior.
"""
import pytest

from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.core.project import Project
from logic_studio.core.wire import Wire
from logic_studio.compiler.core import Compiler

register_builtin_blocks()


# ---- §2.1: add_wire() refuses a wire with no connected end at all --------

def test_add_wire_refuses_two_free_ends():
    p = Project()
    wire = Wire()
    wire.free_end_source = {"x": 0.0, "y": 0.0}
    wire.free_end_dest = {"x": 10.0, "y": 10.0}
    assert p.add_wire(wire) is False
    assert wire not in p.wires

def test_add_wire_accepts_one_free_end():
    p = Project()
    b = BlockRegistry.create_block("logic.and")
    p.add_block(b)
    wire = Wire()
    wire.source_pin = b.outputs[0].uuid
    wire.free_end_dest = {"x": 10.0, "y": 10.0}
    assert p.add_wire(wire) is True
    assert wire in p.wires

def test_add_wire_accepts_a_fully_connected_labeled_wire():
    p = Project()
    a = BlockRegistry.create_block("logic.and")
    n = BlockRegistry.create_block("logic.not")
    p.add_block(a)
    p.add_block(n)
    assert a.outputs[0].connect(n.inputs[0])
    wire = Wire()
    wire.source_pin = a.outputs[0].uuid
    wire.dest_pin = n.inputs[0].uuid
    wire.label = "opis dokumentacyjny"
    assert p.add_wire(wire) is True


# ---- §2 TEST: save/load preserves the free end's coordinates --------------

def test_project_save_load_preserves_free_end_coordinates():
    p = Project()
    b = BlockRegistry.create_block("logic.and")
    p.add_block(b)
    wire = Wire()
    wire.source_pin = b.outputs[0].uuid
    wire.free_end_dest = {"x": 123.5, "y": -45.0}
    p.add_wire(wire)

    data = p.serialize()
    p2 = Project.deserialize(data)

    assert len(p2.wires) == 1
    reloaded = p2.wires[0]
    assert reloaded.free_end_dest == {"x": 123.5, "y": -45.0}
    assert reloaded.source_pin == b.outputs[0].uuid
    assert reloaded.dest_pin is None

def test_new_project_has_no_wires():
    assert Project().wires == []


# ---- §2.3: schema migration v11 -> v12 ------------------------------------

def test_v11_project_migrates_with_an_empty_wires_list():
    data = {
        "format": "EPW_LOGIC", "schema_version": 11,
        "settings": {"ela_devices": ["ELA01"], "ada_devices": ["ADA01"], "cycle_time_ms": 100},
        "blocks": [],
    }
    p = Project.deserialize(data)
    assert p.wires == []

def test_v1_project_migrates_all_the_way_through_with_no_wires():
    data = {
        "format": "EPW_LOGIC", "schema_version": 1,
        "settings": {"name": "Ancient", "version": "1.0", "cycle_time_ms": 100},
        "blocks": [],
    }
    p = Project.deserialize(data)
    assert p.wires == []


# ---- §2.5: validator warning for an unlabeled free end --------------------

def test_validator_warns_on_unlabeled_free_end():
    p = Project()
    b = BlockRegistry.create_block("logic.and")
    p.add_block(b)
    wire = Wire()
    wire.source_pin = b.outputs[0].uuid
    wire.free_end_dest = {"x": 10.0, "y": 10.0}
    p.add_wire(wire)

    c = Compiler(p)
    res = c.compile()
    assert res is not None  # warning, not an error
    assert any("Niedokończony przewód" in w and (b.short_id in w) for w in c.warnings), c.warnings

def test_validator_does_not_warn_on_a_labeled_free_end():
    p = Project()
    b = BlockRegistry.create_block("logic.and")
    p.add_block(b)
    wire = Wire()
    wire.source_pin = b.outputs[0].uuid
    wire.free_end_dest = {"x": 10.0, "y": 10.0}
    wire.label = "Kontynuacja"
    p.add_wire(wire)

    c = Compiler(p)
    res = c.compile()
    assert res is not None
    assert not any("Niedokończony przewód" in w for w in c.warnings)

def test_validator_does_not_warn_on_a_fully_connected_unlabeled_wire():
    """The overwhelming common case -- a plain wire with no Wire record
    at all -- must never trigger this check."""
    p = Project()
    a = BlockRegistry.create_block("logic.and")
    n = BlockRegistry.create_block("logic.not")
    p.add_block(a)
    p.add_block(n)
    assert a.outputs[0].connect(n.inputs[0])

    c = Compiler(p)
    res = c.compile()
    assert res is not None
    assert not any("Niedokończony przewód" in w for w in c.warnings)


# ---- §2.6: a free end without a label creates no graph edge, no crash ----

def test_compile_never_raises_on_a_free_end_wire():
    p = Project()
    b = BlockRegistry.create_block("logic.and")
    p.add_block(b)
    wire = Wire()
    wire.source_pin = b.outputs[0].uuid
    wire.free_end_dest = {"x": 10.0, "y": 10.0}
    p.add_wire(wire)

    c = Compiler(p)
    res = c.compile()  # must not raise
    assert res is not None

def test_free_end_wire_creates_no_edge_execution_order_unaffected():
    """The free-end wire's presence must not change execution_order's
    STRUCTURE at all compared to the identical project with no such wire
    -- there is nothing on its far side to be an edge TO. Compared by
    type_id sequence, not raw uuids, since the two projects are built
    from independently-uuid'd blocks."""
    p = Project()
    a = BlockRegistry.create_block("logic.and")
    n = BlockRegistry.create_block("logic.not")
    p.add_block(a)
    p.add_block(n)
    assert a.outputs[0].connect(n.inputs[0])

    order_without = Compiler(p).compile()["program"].execution_order
    types_without = [next(b for b in p.blocks if b.uuid == u).type_id for u in order_without]

    wire = Wire()
    wire.source_pin = a.outputs[0].uuid
    wire.free_end_dest = {"x": 999.0, "y": 999.0}
    wire.label = "nieużywana odnoga"
    p.add_wire(wire)

    order_with = Compiler(p).compile()["program"].execution_order
    types_with = [next(b for b in p.blocks if b.uuid == u).type_id for u in order_with]

    assert types_without == types_with
    assert order_without == order_with  # same blocks, same uuids -- identical this time
