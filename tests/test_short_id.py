"""feat/io-labels-and-ids §4 — short, human-readable block identifiers
("g12", "i3", ...) replacing the raw UUID in every user-facing message.
"""
import pytest

from logic_studio.core.project import Project
from logic_studio.core import short_id
from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.blocks.logic_gates import AndGate, NotGate
from logic_studio.blocks.io_blocks import DigitalInputBlock, DigitalOutputBlock
from logic_studio.blocks.timers import TON
from logic_studio.blocks.memory import SR
from logic_studio.blocks.edges import RTrigBlock
from logic_studio.blocks.counters import CTU
from logic_studio.blocks.documentation import TextBlock
from logic_studio.blocks.constants import TrueConstant
from logic_studio.blocks.comparators import GreaterBlock

register_builtin_blocks()


# ---- §4.1 prefix table --------------------------------------------------

@pytest.mark.parametrize("cls,expected_prefix", [
    (AndGate, "g"), (NotGate, "g"),
    (DigitalInputBlock, "i"),
    (DigitalOutputBlock, "o"),
    (TON, "t"),
    (SR, "f"),
    (GreaterBlock, "a"),
    (RTrigBlock, "e"),
    (CTU, "c"),
    (TextBlock, "d"),
    (TrueConstant, "x"),
])
def test_prefix_for_block_matches_the_category_table(cls, expected_prefix):
    assert short_id.prefix_for_block(cls()) == expected_prefix

def test_virtual_input_and_reg_in_are_inputs():
    for type_id in ("virtual.input", "internal.reg_in"):
        block = BlockRegistry.create_block(type_id)
        assert short_id.prefix_for_block(block) == "i"

def test_virtual_output_and_reg_out_are_outputs():
    for type_id in ("virtual.output", "internal.reg_out"):
        block = BlockRegistry.create_block(type_id)
        assert short_id.prefix_for_block(block) == "o"


# ---- §4.1/§4.2 assignment ------------------------------------------------

def test_assigns_sequential_numbers_per_prefix():
    p = Project()
    g1 = AndGate(); p.add_block(g1)
    g2 = AndGate(); p.add_block(g2)
    i1 = DigitalInputBlock(); p.add_block(i1)

    assert g1.short_id == "g1"
    assert g2.short_id == "g2"
    assert i1.short_id == "i1"

def test_short_id_is_unique_within_a_project():
    p = Project()
    ids = set()
    for _ in range(5):
        b = AndGate()
        p.add_block(b)
        ids.add(b.short_id)
    assert len(ids) == 5

def test_a_block_already_carrying_a_short_id_keeps_it():
    p = Project()
    b = AndGate()
    b.short_id = "g99"
    p.add_block(b)
    assert b.short_id == "g99"

def test_deleting_a_block_never_reissues_its_number():
    """§4.2: numbering is NOT re-densified after a delete — g3's number
    must never come back."""
    p = Project()
    g1 = AndGate(); p.add_block(g1)
    g2 = AndGate(); p.add_block(g2)
    g3 = AndGate(); p.add_block(g3)
    assert [g1.short_id, g2.short_id, g3.short_id] == ["g1", "g2", "g3"]

    p.remove_block(g3)
    g4 = AndGate(); p.add_block(g4)
    assert g4.short_id == "g4"  # not a reissued "g3"


# ---- §4.2 clone gets a NEW id --------------------------------------------

def test_clone_does_not_copy_short_id():
    b = AndGate()
    b.short_id = "g7"
    clone = b.clone()
    assert clone.short_id != "g7"
    assert clone.short_id == ""  # not yet added to a project

def test_cloned_block_gets_a_fresh_id_once_added_to_a_project():
    p = Project()
    original = AndGate()
    p.add_block(original)
    clone = original.clone()
    p.add_block(clone)
    assert clone.short_id != original.short_id
    assert clone.short_id.startswith("g")


# ---- §4.2 migration: deterministic, in file order -----------------------

def test_blocks_without_short_id_get_one_assigned_in_file_order():
    p = Project()
    old_data = {
        "format": "EPW_LOGIC", "schema_version": 4,
        "settings": {"name": "x", "version": "1.0", "cycle_time_ms": 100,
                     "analog_points": [], "internal_bits": [], "io_labels": {}},
        "blocks": [
            {"type_id": "logic.and", "uuid": "u1"},
            {"type_id": "input.di", "uuid": "u2"},
            {"type_id": "logic.and", "uuid": "u3"},
        ],
    }
    proj = Project.deserialize(old_data)
    assert [b.short_id for b in proj.blocks] == ["g1", "i1", "g2"]

def test_migration_is_deterministic_across_repeated_loads():
    """Loading the same FILE twice (json.load() gives a fresh dict each
    time — simulated here with deepcopy, since Project.deserialize()
    mutates the dict it's handed, same as the migration functions already
    do) must assign identical short_ids both times."""
    import copy
    old_data = {
        "format": "EPW_LOGIC", "schema_version": 4,
        "settings": {"name": "x", "version": "1.0", "cycle_time_ms": 100,
                     "analog_points": [], "internal_bits": [], "io_labels": {}},
        "blocks": [{"type_id": "logic.and", "uuid": "u1"}, {"type_id": "logic.or", "uuid": "u2"}],
    }
    ids_a = [b.short_id for b in Project.deserialize(copy.deepcopy(old_data)).blocks]
    ids_b = [b.short_id for b in Project.deserialize(copy.deepcopy(old_data)).blocks]
    assert ids_a == ids_b == ["g1", "g2"]  # OR shares AND's "g" prefix -> sequential within one load

def test_resave_and_reload_preserves_already_assigned_ids():
    p = Project()
    g1 = AndGate(); p.add_block(g1)
    i1 = DigitalInputBlock(); p.add_block(i1)

    data = p.serialize()
    p2 = Project.deserialize(data)
    assert [b.short_id for b in p2.blocks] == ["g1", "i1"]

    data2 = p2.serialize()
    p3 = Project.deserialize(data2)
    assert [b.short_id for b in p3.blocks] == ["g1", "i1"]

def test_mixed_file_some_with_short_id_some_without_never_collides():
    """A file where SOME blocks already carry a short_id (e.g. hand-edited,
    or merged) and others don't must not let a freshly assigned id collide
    with one about to be restored later in the same file."""
    old_data = {
        "format": "EPW_LOGIC", "schema_version": 4,
        "settings": {"name": "x", "version": "1.0", "cycle_time_ms": 100,
                     "analog_points": [], "internal_bits": [], "io_labels": {}},
        "blocks": [
            {"type_id": "logic.and", "uuid": "u1"},          # no short_id -> gets assigned first
            {"type_id": "logic.and", "uuid": "u2", "short_id": "g1"},  # already g1!
        ],
    }
    proj = Project.deserialize(old_data)
    ids = [b.short_id for b in proj.blocks]
    assert len(ids) == len(set(ids)), f"collision: {ids}"
    assert ids[1] == "g1"  # explicitly-saved id preserved
    assert ids[0] != "g1"  # freshly assigned one avoided the collision


# ---- §4.3 usage in compiler/validator messages ---------------------------

def test_validator_message_uses_short_id_not_uuid_or_display_name():
    from logic_studio.compiler.validator import Validator
    p = Project()
    gate = AndGate()
    gate.inputs[0].disabled = True  # allowed only 2+ input gates -> AND qualifies
    gate.inputs[1].disabled = True
    p.add_block(gate)

    errors, warnings = [], []
    Validator(p).run(errors, warnings)

    assert any(gate.short_id in e for e in errors)
    assert not any(gate.uuid in e for e in errors)

def test_compiler_message_includes_address_and_label_for_io_block():
    """§3.3's exact required format: "i3 (ELA01.DI01 — <label>)". Uses a DO
    block (not DI) because DI has no input pins at all — nothing about it
    can ever be flagged "unconnected"; a DO block's own input, left
    unwired, is the natural way to get a real message referencing it."""
    from logic_studio.core.device_model import DeviceModel
    from logic_studio.compiler.validator import Validator

    p = Project()
    do = DigitalOutputBlock()
    do.properties["Address"] = "ADA01.DO01"
    p.add_block(do)
    DeviceModel.set_io_label(p, "ADA01.DO01", "Załącz Q1")

    errors, warnings = [], []
    Validator(p).run(errors, warnings)

    expected_ref = f"{do.short_id} (ADA01.DO01 — Załącz Q1)"
    assert any(expected_ref in w for w in warnings), warnings


# ---- §4.4 export --------------------------------------------------------

def test_short_id_reaches_runtime_export():
    from logic_studio.compiler.core import Compiler
    from logic_studio.compiler.exporter import Exporter

    p = Project()
    gate = AndGate()
    p.add_block(gate)
    c = Compiler(p)
    res = c.compile()
    assert res is not None
    data = Exporter(p, res["program"].execution_order).export()
    assert data["blocks"][gate.uuid]["short_id"] == gate.short_id

def test_short_id_is_covered_by_checksum_via_the_blocks_field():
    """§4.4: no separate CHECKSUM_FIELDS entry is needed — "blocks" already
    covers it, since it carries this whole per-block dict."""
    from logic_studio.compiler.core import Compiler
    from logic_studio.compiler.exporter import Exporter, verify_checksum

    p = Project()
    gate = AndGate()
    p.add_block(gate)
    c = Compiler(p)
    res = c.compile()
    data = Exporter(p, res["program"].execution_order).export()
    assert verify_checksum(data) is True

    tampered = dict(data)
    tampered["blocks"] = dict(data["blocks"])
    tampered["blocks"][gate.uuid] = dict(data["blocks"][gate.uuid])
    tampered["blocks"][gate.uuid]["short_id"] = "TAMPERED"
    assert verify_checksum(tampered) is False
