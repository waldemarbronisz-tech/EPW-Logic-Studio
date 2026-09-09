"""feat/macro-library-import-export — logic_studio/core/macro_library.py.
Pure logic, no Qt, headless — see test_library_panel_macros.py for the
export/import UI actions built on this."""
import pytest

from logic_studio.core.project import Project
from logic_studio.core.macros import (
    new_def_id, get_definition, set_definition, build_definition,
    expand_project, macro_def_id, MACRO_TYPE_PREFIX,
)
from logic_studio.core.macro_library import (
    collect_dependencies, export_definition, save_to_file, load_from_file,
    validate_bundle, import_bundle, FORMAT, SCHEMA_VERSION,
)
from logic_studio.blocks.pin import Pin
from logic_studio.blocks.logic_gates import AndGate
from logic_studio.blocks.io_blocks import DigitalInputBlock, DigitalOutputBlock
from logic_studio.blocks.macro_instance import MacroInstanceBlock
from logic_studio.blocks import register_builtin_blocks

register_builtin_blocks()


def _and_macro_definition(name="AndMacro"):
    """One AND gate, exposed as In1/In2/Out — same helper shape as
    test_macros.py's own (build_definition() only exposes a pin that had
    an external connection at build time)."""
    gate = AndGate()
    d1, d2, d3 = DigitalInputBlock(), DigitalInputBlock(), DigitalOutputBlock()
    d1.outputs[0].connect(gate.inputs[0])
    d2.outputs[0].connect(gate.inputs[1])
    gate.outputs[0].connect(d3.inputs[0])
    definition, _ = build_definition(name, [gate])
    return definition


# ---- collect_dependencies() -------------------------------------------

def test_collect_dependencies_of_a_standalone_definition():
    p = Project()
    def_id = new_def_id()
    set_definition(p, def_id, _and_macro_definition())

    collected = collect_dependencies(p, def_id)

    assert set(collected.keys()) == {def_id}

def test_collect_dependencies_includes_a_nested_macro():
    p = Project()
    def_id_a = new_def_id()
    set_definition(p, def_id_a, _and_macro_definition())

    nested = MacroInstanceBlock(def_id=def_id_a)
    nested.configure(get_definition(p, def_id_a))
    definition_b, _ = build_definition("WrapsA", [nested])
    def_id_b = new_def_id()
    set_definition(p, def_id_b, definition_b)

    collected = collect_dependencies(p, def_id_b)

    assert set(collected.keys()) == {def_id_a, def_id_b}

def test_collect_dependencies_multiple_levels_deep():
    p = Project()
    def_id_a = new_def_id()
    set_definition(p, def_id_a, _and_macro_definition())

    nested_a = MacroInstanceBlock(def_id=def_id_a)
    nested_a.configure(get_definition(p, def_id_a))
    definition_b, _ = build_definition("WrapsA", [nested_a])
    def_id_b = new_def_id()
    set_definition(p, def_id_b, definition_b)

    nested_b = MacroInstanceBlock(def_id=def_id_b)
    nested_b.configure(get_definition(p, def_id_b))
    definition_c, _ = build_definition("WrapsB", [nested_b])
    def_id_c = new_def_id()
    set_definition(p, def_id_c, definition_c)

    collected = collect_dependencies(p, def_id_c)

    assert set(collected.keys()) == {def_id_a, def_id_b, def_id_c}

def test_collect_dependencies_skips_a_dangling_reference():
    p = Project()
    def_id_b = new_def_id()
    nested = MacroInstanceBlock(def_id="does-not-exist")
    definition_b = {"name": "B", "blocks": [nested.serialize()], "input_pins": [], "output_pins": []}
    set_definition(p, def_id_b, definition_b)

    collected = collect_dependencies(p, def_id_b)

    assert set(collected.keys()) == {def_id_b}  # the dangling one just isn't there


# ---- export_definition() / save_to_file() / load_from_file() ------------

def test_export_definition_shape():
    p = Project()
    def_id = new_def_id()
    set_definition(p, def_id, _and_macro_definition())

    bundle = export_definition(p, def_id)

    assert bundle["format"] == FORMAT
    assert bundle["schema_version"] == SCHEMA_VERSION
    assert bundle["root_def_id"] == def_id
    assert set(bundle["definitions"].keys()) == {def_id}

def test_export_definition_raises_for_unknown_def_id():
    p = Project()
    with pytest.raises(ValueError, match="Nieznana"):
        export_definition(p, "does-not-exist")

def test_save_and_load_round_trip(tmp_path):
    p = Project()
    def_id = new_def_id()
    set_definition(p, def_id, _and_macro_definition())
    path = str(tmp_path / "test.epwmacro")

    save_to_file(p, def_id, path)
    bundle = load_from_file(path)

    assert bundle["root_def_id"] == def_id
    assert bundle["definitions"][def_id]["name"] == "AndMacro"


# ---- validate_bundle() ----------------------------------------------------

def test_validate_bundle_accepts_a_well_formed_bundle():
    p = Project()
    def_id = new_def_id()
    set_definition(p, def_id, _and_macro_definition())
    validate_bundle(export_definition(p, def_id))  # must not raise

def test_validate_bundle_rejects_wrong_format():
    with pytest.raises(ValueError):
        validate_bundle({"format": "SOMETHING_ELSE", "schema_version": 1, "definitions": {}})

def test_validate_bundle_rejects_a_newer_schema_version():
    with pytest.raises(ValueError):
        validate_bundle({"format": FORMAT, "schema_version": SCHEMA_VERSION + 1, "definitions": {}})

def test_validate_bundle_rejects_garbage():
    with pytest.raises(ValueError):
        validate_bundle("not even a dict")
    with pytest.raises(ValueError):
        validate_bundle({})


# ---- import_bundle() -----------------------------------------------------

def test_import_bundle_creates_a_fresh_def_id():
    source = Project()
    def_id = new_def_id()
    set_definition(source, def_id, _and_macro_definition())
    bundle = export_definition(source, def_id)

    target = Project()
    new_id = import_bundle(target, bundle)

    assert new_id != def_id
    imported = get_definition(target, new_id)
    assert imported["name"] == "AndMacro"
    assert imported["blocks"][0]["type_id"] == "logic.and"

def test_import_bundle_twice_creates_independent_copies():
    source = Project()
    def_id = new_def_id()
    set_definition(source, def_id, _and_macro_definition())
    bundle = export_definition(source, def_id)

    target = Project()
    first_id = import_bundle(target, bundle)
    second_id = import_bundle(target, bundle)

    assert first_id != second_id
    assert get_definition(target, first_id) is not None
    assert get_definition(target, second_id) is not None

def test_import_bundle_rewrites_nested_references():
    source = Project()
    def_id_a = new_def_id()
    set_definition(source, def_id_a, _and_macro_definition())
    nested = MacroInstanceBlock(def_id=def_id_a)
    nested.configure(get_definition(source, def_id_a))
    definition_b, _ = build_definition("WrapsA", [nested])
    def_id_b = new_def_id()
    set_definition(source, def_id_b, definition_b)
    bundle = export_definition(source, def_id_b)

    target = Project()
    new_root_id = import_bundle(target, bundle)

    root_definition = get_definition(target, new_root_id)
    nested_block_data = root_definition["blocks"][0]
    referenced_def_id = macro_def_id(nested_block_data["type_id"])
    assert referenced_def_id is not None
    assert referenced_def_id != def_id_a  # rewritten to a fresh id
    assert get_definition(target, referenced_def_id) is not None  # and that id actually exists in the target

def test_import_bundle_result_expands_and_compiles_in_the_target_project():
    """End-to-end: export from one project, import into another, place an
    instance, and confirm it actually compiles (expand_project() resolves
    the imported definition correctly, no dangling references)."""
    source = Project()
    def_id = new_def_id()
    set_definition(source, def_id, _and_macro_definition())
    bundle = export_definition(source, def_id)

    target = Project()
    new_id = import_bundle(target, bundle)

    instance = MacroInstanceBlock(def_id=new_id)
    instance.configure(get_definition(target, new_id))
    di1, di2, do = DigitalInputBlock(), DigitalInputBlock(), DigitalOutputBlock()
    di1.outputs[0].connect(instance.inputs[0])
    di2.outputs[0].connect(instance.inputs[1])
    instance.outputs[0].connect(do.inputs[0])
    for b in (di1, di2, do, instance):
        target.add_block(b)

    expanded, _wire_scopes, errors = expand_project(target)
    assert errors == []
    assert "logic.and" in {b.type_id for b in expanded}

def test_import_bundle_raises_for_an_invalid_bundle():
    target = Project()
    with pytest.raises(ValueError):
        import_bundle(target, {"format": "NOPE"})
    assert get_definition(target, "anything") is None  # nothing partially imported

def test_import_bundle_leaves_a_dangling_reference_dangling():
    """A definition that ALREADY referenced a missing macro in the source
    project keeps referencing a (still missing, differently-named) one in
    the target — the same "missing definition" compile error either way,
    never silently masked."""
    source = Project()
    def_id_b = new_def_id()
    nested = MacroInstanceBlock(def_id="does-not-exist-anywhere")
    definition_b = {"name": "B", "blocks": [nested.serialize()], "input_pins": [], "output_pins": []}
    set_definition(source, def_id_b, definition_b)
    bundle = export_definition(source, def_id_b)

    target = Project()
    new_id = import_bundle(target, bundle)

    imported = get_definition(target, new_id)
    dangling_type_id = imported["blocks"][0]["type_id"]
    assert dangling_type_id == "macro.does-not-exist-anywhere"
    assert get_definition(target, macro_def_id(dangling_type_id)) is None


# ---- audit/systematic-sweep §1: field survival through export/import ------
# This path (a macro definition's own block/pin data through
# export_definition()/save_to_file()/load_from_file()/import_bundle()) had
# never been checked field-by-field before this audit -- every other
# state-transfer path in this project (serialize/clone/clipboard/state_diff)
# already has one. Verified safe BY CONSTRUCTION (export/import operate on
# the whole already-serialized block/pin dicts via copy.deepcopy(), never
# hand-picking individual fields the way the six known historical bugs all
# involved), but "safe by construction" is exactly the kind of claim this
# audit's own rule is to verify by EXECUTION, not trust by reading -- this
# is that verification, kept as a permanent regression test.

def test_non_default_block_and_pin_fields_survive_export_import_round_trip(tmp_path):
    gate = AndGate()
    gate.enabled = False
    gate.color = "#ABCDEF"
    gate.execution_priority = 7
    gate.properties["Tag"] = "MacroInnerTag"
    gate.outputs[0].safety_relevant = True
    gate.inputs[0].disabled = False  # AND allows disabling inputs; left False deliberately, see below
    gate.inputs[1].disabled = True

    source = Project()
    definition = {"name": "Flags", "blocks": [gate.serialize()], "input_pins": [], "output_pins": []}
    def_id = new_def_id()
    set_definition(source, def_id, definition)

    path = str(tmp_path / "flags.epwmacro")
    save_to_file(source, def_id, path)
    bundle = load_from_file(path)

    target = Project()
    new_id = import_bundle(target, bundle)
    imported_block = get_definition(target, new_id)["blocks"][0]

    assert imported_block["enabled"] is False
    assert imported_block["color"] == "#ABCDEF"
    assert imported_block["execution_priority"] == 7
    assert imported_block["properties"]["Tag"] == "MacroInnerTag"
    assert imported_block["outputs"][0]["safety_relevant"] is True
    assert imported_block["inputs"][0]["disabled"] is False
    assert imported_block["inputs"][1]["disabled"] is True
    # uuid is preserved verbatim -- macro definitions are keyed by pin uuid
    # for GraphBuilder purposes (see core/macros.py's own note on this).
    assert imported_block["uuid"] == gate.serialize()["uuid"]
