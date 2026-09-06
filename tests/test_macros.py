"""feat/macro-blocks — logic_studio/core/macros.py. Pure logic, no Qt,
headless — see test_macro_instance.py for MacroInstanceBlock itself, and
this module's own docstring for the definition-dict shape."""
import pytest

from logic_studio.core.project import Project
from logic_studio.core.macros import (
    macro_def_id, new_def_id, get_definitions, get_definition,
    set_definition, delete_definition, is_definition_in_use,
    build_definition, expand_project,
    instantiate_definition_blocks, update_definition_blocks,
)
from logic_studio.blocks.pin import Pin
from logic_studio.blocks.logic_gates import AndGate
from logic_studio.blocks.io_blocks import DigitalInputBlock, DigitalOutputBlock
from logic_studio.blocks.macro_instance import MacroInstanceBlock
from logic_studio.blocks import register_builtin_blocks

register_builtin_blocks()


def _empty_definition(name="X"):
    return {"name": name, "blocks": [], "input_pins": [], "output_pins": []}


def _and_macro_definition():
    """One AND gate, exposed as In1/In2/Out. build_definition() only
    exposes a pin that had an EXTERNAL connection at build time (see
    test_build_definition_unconnected_pins_are_not_exposed below), so the
    gate is briefly wired to throwaway blocks purely to produce those
    crossings — the throwaway blocks themselves are discarded, only the
    resulting definition dict is kept."""
    gate = AndGate()
    dummy_di1 = DigitalInputBlock()
    dummy_di2 = DigitalInputBlock()
    dummy_do = DigitalOutputBlock()
    dummy_di1.outputs[0].connect(gate.inputs[0])
    dummy_di2.outputs[0].connect(gate.inputs[1])
    gate.outputs[0].connect(dummy_do.inputs[0])
    definition, _ = build_definition("AndMacro", [gate])
    return definition


# ---- macro_def_id / new_def_id ----------------------------------------

def test_macro_def_id_extracts_suffix():
    assert macro_def_id("macro.ab12cd34") == "ab12cd34"

def test_macro_def_id_none_for_non_macro_type():
    assert macro_def_id("logic.and") is None

def test_macro_def_id_none_for_empty_none_or_bare_prefix():
    assert macro_def_id("") is None
    assert macro_def_id(None) is None
    assert macro_def_id("macro.") is None

def test_new_def_id_is_short_and_unique():
    a, b = new_def_id(), new_def_id()
    assert a != b
    assert len(a) == 8


# ---- definition registry -----------------------------------------------

def test_new_project_has_no_macro_definitions():
    p = Project()
    assert get_definitions(p) == {}
    assert get_definition(p, "missing") is None

def test_set_and_get_definition_round_trips():
    p = Project()
    set_definition(p, "abc123", _empty_definition("Test"))
    assert get_definition(p, "abc123") == _empty_definition("Test")

def test_get_definition_returns_a_copy_not_the_live_dict():
    p = Project()
    set_definition(p, "abc", _empty_definition("X"))
    got = get_definition(p, "abc")
    got["name"] = "Mutated"
    got["blocks"].append({"fake": True})
    assert get_definition(p, "abc")["name"] == "X"
    assert get_definition(p, "abc")["blocks"] == []

def test_get_definitions_lists_everything():
    p = Project()
    set_definition(p, "a", _empty_definition("A"))
    set_definition(p, "b", _empty_definition("B"))
    assert set(get_definitions(p).keys()) == {"a", "b"}

def test_delete_definition_reports_removed():
    p = Project()
    set_definition(p, "abc", _empty_definition("X"))
    assert delete_definition(p, "abc") is True
    assert get_definition(p, "abc") is None

def test_delete_definition_no_op_when_absent():
    p = Project()
    assert delete_definition(p, "missing") is False

def test_is_definition_in_use():
    p = Project()
    inst = MacroInstanceBlock(def_id="abc")
    p.add_block(inst)
    assert is_definition_in_use(p, "abc") is True
    assert is_definition_in_use(p, "other") is False


# ---- build_definition() -------------------------------------------------

def test_build_definition_records_external_crossings_and_output_fanout():
    di = DigitalInputBlock()
    gate = AndGate()
    do1 = DigitalOutputBlock()
    do2 = DigitalOutputBlock()

    di.outputs[0].connect(gate.inputs[0])
    gate.outputs[0].connect(do1.inputs[0])
    gate.outputs[0].connect(do2.inputs[0])

    definition, crossings = build_definition("MyMacro", [gate])

    assert definition["name"] == "MyMacro"
    assert len(definition["blocks"]) == 1
    assert definition["blocks"][0]["uuid"] == gate.uuid

    assert len(definition["input_pins"]) == 1
    assert definition["input_pins"][0]["pin_name"] == "In1"
    assert len(definition["output_pins"]) == 1
    assert definition["output_pins"][0]["pin_name"] == "Out"

    input_crossings = [c for c in crossings if c["direction"] == "input"]
    output_crossings = [c for c in crossings if c["direction"] == "output"]
    assert len(input_crossings) == 1
    assert input_crossings[0]["external_pin_uuid"] == di.outputs[0].uuid
    assert input_crossings[0]["instance_pin_index"] == 0

    assert len(output_crossings) == 2
    assert {c["external_pin_uuid"] for c in output_crossings} == {do1.inputs[0].uuid, do2.inputs[0].uuid}
    assert all(c["instance_pin_index"] == 0 for c in output_crossings)

    # the gate's own serialized copy has the external connections stripped
    gate_data = definition["blocks"][0]
    assert gate_data["inputs"][0]["connections"] == []
    assert gate_data["outputs"][0]["connections"] == []

def test_build_definition_keeps_connections_between_two_selected_blocks():
    g1 = AndGate()
    g2 = AndGate()
    g1.outputs[0].connect(g2.inputs[0])

    definition, crossings = build_definition("Chain", [g1, g2])

    assert len(definition["blocks"]) == 2
    assert crossings == []
    g1_data = next(b for b in definition["blocks"] if b["uuid"] == g1.uuid)
    assert g2.inputs[0].uuid in g1_data["outputs"][0]["connections"]

def test_build_definition_unconnected_pins_are_not_exposed():
    gate = AndGate()
    definition, crossings = build_definition("Lonely", [gate])
    assert definition["input_pins"] == []
    assert definition["output_pins"] == []
    assert crossings == []


# ---- expand_project() ----------------------------------------------------

def test_expand_project_on_empty_project():
    p = Project()
    expanded, errors = expand_project(p)
    assert expanded == []
    assert errors == []

def test_expand_project_replaces_instance_with_definition_blocks():
    p = Project()
    def_id = new_def_id()
    set_definition(p, def_id, _and_macro_definition())

    di1 = DigitalInputBlock()
    di2 = DigitalInputBlock()
    do = DigitalOutputBlock()
    inst = MacroInstanceBlock(def_id=def_id)
    inst.configure(get_definition(p, def_id))

    di1.outputs[0].connect(inst.inputs[0])
    di2.outputs[0].connect(inst.inputs[1])
    inst.outputs[0].connect(do.inputs[0])

    for b in (di1, di2, do, inst):
        p.add_block(b)

    expanded, errors = expand_project(p)
    assert errors == []

    type_ids = {b.type_id for b in expanded}
    assert not any(macro_def_id(t) for t in type_ids)
    assert "logic.and" in type_ids

    inner_gate = next(b for b in expanded if b.type_id == "logic.and")
    di1_out = next(b for b in expanded if b.uuid == di1.uuid).outputs[0]
    di2_out = next(b for b in expanded if b.uuid == di2.uuid).outputs[0]
    do_in = next(b for b in expanded if b.uuid == do.uuid).inputs[0]

    assert inner_gate.inputs[0].uuid in di1_out.connections
    assert di1_out.uuid in inner_gate.inputs[0].connections
    assert inner_gate.inputs[1].uuid in di2_out.connections
    assert di2_out.uuid in inner_gate.inputs[1].connections
    assert inner_gate.outputs[0].uuid in do_in.connections
    assert do_in.uuid in inner_gate.outputs[0].connections

def test_expand_project_does_not_mutate_the_live_project():
    p = Project()
    def_id = new_def_id()
    set_definition(p, def_id, _and_macro_definition())

    di = DigitalInputBlock()
    inst = MacroInstanceBlock(def_id=def_id)
    inst.configure(get_definition(p, def_id))
    di.outputs[0].connect(inst.inputs[0])
    p.add_block(di)
    p.add_block(inst)

    before = (list(di.outputs[0].connections), list(inst.inputs[0].connections))
    expand_project(p)
    after = (list(di.outputs[0].connections), list(inst.inputs[0].connections))
    assert before == after
    assert p.blocks == [di, inst]  # instance is still the live project's own block

def test_expand_project_gives_independent_uuids_to_multiple_instances():
    p = Project()
    def_id = new_def_id()
    set_definition(p, def_id, _and_macro_definition())

    inst1 = MacroInstanceBlock(def_id=def_id)
    inst1.configure(get_definition(p, def_id))
    inst2 = MacroInstanceBlock(def_id=def_id)
    inst2.configure(get_definition(p, def_id))
    p.add_block(inst1)
    p.add_block(inst2)

    expanded, errors = expand_project(p)
    assert errors == []

    gates = [b for b in expanded if b.type_id == "logic.and"]
    assert len(gates) == 2
    assert gates[0].uuid != gates[1].uuid

    all_pin_uuids = [pin.uuid for b in expanded for pin in b.inputs + b.outputs]
    assert len(all_pin_uuids) == len(set(all_pin_uuids))

def test_expand_project_reports_missing_definition():
    p = Project()
    inst = MacroInstanceBlock(def_id="doesnotexist")
    p.add_block(inst)

    expanded, errors = expand_project(p)
    assert expanded == []
    assert len(errors) == 1
    assert "doesnotexist" in errors[0]

def test_expand_project_reports_unknown_block_type_inside_a_definition():
    p = Project()
    def_id = new_def_id()
    definition = _empty_definition("Broken")
    definition["blocks"] = [{"type_id": "logic.does_not_exist", "uuid": "x", "inputs": [], "outputs": []}]
    set_definition(p, def_id, definition)

    inst = MacroInstanceBlock(def_id=def_id)
    p.add_block(inst)

    expanded, errors = expand_project(p)
    assert expanded == []
    assert len(errors) == 1
    assert "logic.does_not_exist" in errors[0]

def test_expand_project_detects_direct_self_reference_cycle():
    p = Project()
    def_id = new_def_id()
    self_ref_instance = MacroInstanceBlock(def_id=def_id)
    definition = _empty_definition("Cyclic")
    definition["blocks"] = [self_ref_instance.serialize()]
    set_definition(p, def_id, definition)

    inst = MacroInstanceBlock(def_id=def_id)
    p.add_block(inst)

    expanded, errors = expand_project(p)
    assert expanded == []
    assert any("cykl" in e.lower() for e in errors)

def test_expand_project_supports_nesting_a_macro_inside_another_macro():
    """A macro definition ("WrapsA") whose OWN internal blocks include an
    instance of a different, already-defined macro ("AndMacro"), wired
    internally to a plain sink gate — the supported nesting shape (the
    exposed boundary lands on the plain sink block, never directly on the
    nested instance's own pin; see core/macros.py's _expand_instance()
    docstring for the one deliberately-unsupported shape). Two placed
    instances of "WrapsA" must expand independently, each wired only to
    its OWN nested AndMacro copy."""
    p = Project()
    def_id_a = new_def_id()
    set_definition(p, def_id_a, _and_macro_definition())

    nested_a_instance = MacroInstanceBlock(def_id=def_id_a)
    nested_a_instance.configure(get_definition(p, def_id_a))
    sink_gate = AndGate()
    nested_a_instance.outputs[0].connect(sink_gate.inputs[0])

    definition_b, _ = build_definition("WrapsA", [nested_a_instance, sink_gate])
    definition_b["input_pins"] = [
        {"block_uuid": sink_gate.uuid, "pin_name": "In2", "data_type": Pin.TYPE_BOOLEAN, "label": "In2"},
    ]
    definition_b["output_pins"] = [
        {"block_uuid": sink_gate.uuid, "pin_name": "Out", "data_type": Pin.TYPE_BOOLEAN, "label": "Out"},
    ]
    def_id_b = new_def_id()
    set_definition(p, def_id_b, definition_b)

    inst_b_1 = MacroInstanceBlock(def_id=def_id_b)
    inst_b_1.configure(get_definition(p, def_id_b))
    inst_b_2 = MacroInstanceBlock(def_id=def_id_b)
    inst_b_2.configure(get_definition(p, def_id_b))
    p.add_block(inst_b_1)
    p.add_block(inst_b_2)

    expanded, errors = expand_project(p)
    assert errors == []

    gates = [b for b in expanded if b.type_id == "logic.and"]
    assert len(gates) == 4  # 2 sink gates + 2 nested AndMacro gates

    all_pin_uuids = [pin.uuid for b in expanded for pin in b.inputs + b.outputs]
    assert len(all_pin_uuids) == len(set(all_pin_uuids))

    pin_owner = {pin.uuid: b for b in expanded for pin in b.inputs + b.outputs}
    sinks = [g for g in gates if g.inputs[0].connections]
    inner = [g for g in gates if not g.inputs[0].connections]
    assert len(sinks) == 2
    assert len(inner) == 2

    driving_uuids = {pin_owner[s.inputs[0].connections[0]].uuid for s in sinks}
    assert driving_uuids == {g.uuid for g in inner}


# ---- instantiate_definition_blocks() / update_definition_blocks() --------
# feat/macro-blocks breadcrumb navigation — ui/main_window.py's
# enter_macro_instance()/_navigate_to_breadcrumb_index() build on these.

def test_instantiate_definition_blocks_restores_uuids_and_connections():
    definition = _and_macro_definition()
    blocks, unknown = instantiate_definition_blocks(definition)

    assert unknown == []
    assert len(blocks) == 1
    gate = blocks[0]
    assert gate.type_id == "logic.and"
    original_data = definition["blocks"][0]
    assert gate.uuid == original_data["uuid"]
    assert gate.short_id == original_data["short_id"]
    assert [p.uuid for p in gate.inputs] == [p["uuid"] for p in original_data["inputs"]]
    assert [p.uuid for p in gate.outputs] == [p["uuid"] for p in original_data["outputs"]]

def test_instantiate_definition_blocks_preserves_internal_connections():
    g1 = AndGate()
    g2 = AndGate()
    g1.outputs[0].connect(g2.inputs[0])
    definition, _ = build_definition("Chain", [g1, g2])

    blocks, unknown = instantiate_definition_blocks(definition)
    assert unknown == []
    fresh_g1 = next(b for b in blocks if b.uuid == g1.uuid)
    fresh_g2 = next(b for b in blocks if b.uuid == g2.uuid)
    assert fresh_g2.inputs[0].uuid in fresh_g1.outputs[0].connections
    assert fresh_g1.outputs[0].uuid in fresh_g2.inputs[0].connections

def test_instantiate_definition_blocks_reports_unknown_type_ids():
    definition = {"name": "Broken", "blocks": [{"type_id": "logic.does_not_exist", "uuid": "x", "inputs": [], "outputs": []}], "input_pins": [], "output_pins": []}
    blocks, unknown = instantiate_definition_blocks(definition)
    assert blocks == []
    assert unknown == ["logic.does_not_exist"]

def test_update_definition_blocks_commits_new_blocks_list():
    p = Project()
    def_id = new_def_id()
    set_definition(p, def_id, _and_macro_definition())

    blocks, _ = instantiate_definition_blocks(get_definition(p, def_id))
    extra = AndGate()
    blocks.append(extra)

    assert update_definition_blocks(p, def_id, blocks) is True

    updated = get_definition(p, def_id)
    assert len(updated["blocks"]) == 2
    assert any(b["uuid"] == extra.uuid for b in updated["blocks"])

def test_update_definition_blocks_leaves_boundary_pins_untouched():
    """v1 scope: a definition's own input_pins/output_pins are frozen while
    its internals are being edited directly — see this module's own note
    on breadcrumb navigation."""
    p = Project()
    def_id = new_def_id()
    original = _and_macro_definition()
    set_definition(p, def_id, original)

    blocks, _ = instantiate_definition_blocks(get_definition(p, def_id))
    update_definition_blocks(p, def_id, blocks)

    updated = get_definition(p, def_id)
    assert updated["input_pins"] == original["input_pins"]
    assert updated["output_pins"] == original["output_pins"]
    assert updated["name"] == original["name"]

def test_update_definition_blocks_no_op_when_definition_was_deleted():
    p = Project()
    def_id = new_def_id()
    set_definition(p, def_id, _and_macro_definition())
    blocks, _ = instantiate_definition_blocks(get_definition(p, def_id))
    delete_definition(p, def_id)

    assert update_definition_blocks(p, def_id, blocks) is False
    assert get_definition(p, def_id) is None
