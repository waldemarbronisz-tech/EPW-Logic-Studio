"""feat/macro-blocks — logic_studio/blocks/macro_instance.py. See
core/macros.py's module docstring for the overall design; this file covers
MacroInstanceBlock itself: construction, configure(), the deserialize()
override, and clone()."""
import pytest

from logic_studio.core.project import Project
from logic_studio.blocks.pin import Pin
from logic_studio.blocks.macro_instance import MacroInstanceBlock
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.blocks import register_builtin_blocks

register_builtin_blocks()


def _definition():
    return {
        "name": "MojMakroblok",
        "blocks": [],
        "input_pins": [
            {"block_uuid": "b1", "pin_name": "In1", "data_type": Pin.TYPE_BOOLEAN, "label": "Start"},
        ],
        "output_pins": [
            {"block_uuid": "b1", "pin_name": "Out", "data_type": Pin.TYPE_FLOAT, "label": "Wynik"},
        ],
    }


# ---- construction -----------------------------------------------------------

def test_bare_construction_has_no_pins():
    block = MacroInstanceBlock()
    assert block.type_id == "macro."
    assert block.def_id == ""
    assert block.inputs == []
    assert block.outputs == []

def test_construction_with_def_id_sets_type_id():
    block = MacroInstanceBlock(def_id="abc123")
    assert block.type_id == "macro.abc123"
    assert block.def_id == "abc123"

def test_never_registered_in_block_registry():
    """MacroInstanceBlock is resolved via the "macro." type_id prefix, not
    a BlockRegistry entry (core/macros.py's module docstring) — it must
    never show up in a category listing or collide with a real type_id."""
    assert BlockRegistry.get_block_class("macro.abc123") is MacroInstanceBlock
    assert "macro.abc123" not in BlockRegistry._type_id_map


# ---- configure() --------------------------------------------------------

def test_configure_builds_pins_from_definition():
    block = MacroInstanceBlock(def_id="abc")
    block.configure(_definition())

    assert block.display_name == "MojMakroblok"
    assert len(block.inputs) == 1
    assert block.inputs[0].name == "Start"
    assert block.inputs[0].direction == Pin.DIR_INPUT
    assert block.inputs[0].data_type == Pin.TYPE_BOOLEAN

    assert len(block.outputs) == 1
    assert block.outputs[0].name == "Wynik"
    assert block.outputs[0].direction == Pin.DIR_OUTPUT
    assert block.outputs[0].data_type == Pin.TYPE_FLOAT

def test_configure_falls_back_to_pin_name_when_label_missing():
    definition = {
        "name": "X",
        "blocks": [],
        "input_pins": [{"block_uuid": "b1", "pin_name": "In1", "data_type": Pin.TYPE_BOOLEAN}],
        "output_pins": [],
    }
    block = MacroInstanceBlock(def_id="abc")
    block.configure(definition)
    assert block.inputs[0].name == "In1"

def test_configure_replaces_any_previous_pins():
    block = MacroInstanceBlock(def_id="abc")
    block.configure(_definition())
    block.configure({"name": "Y", "blocks": [], "input_pins": [], "output_pins": []})
    assert block.inputs == []
    assert block.outputs == []


# ---- deserialize() --------------------------------------------------------

def test_deserialize_round_trips_pins_and_def_id():
    original = MacroInstanceBlock(def_id="abc")
    original.configure(_definition())

    data = original.serialize()
    restored = MacroInstanceBlock.deserialize(data)

    assert restored.type_id == "macro.abc"
    assert restored.def_id == "abc"
    assert len(restored.inputs) == 1
    assert restored.inputs[0].name == "Start"
    assert restored.inputs[0].data_type == Pin.TYPE_BOOLEAN
    assert restored.inputs[0].uuid == original.inputs[0].uuid
    assert len(restored.outputs) == 1
    assert restored.outputs[0].name == "Wynik"
    assert restored.outputs[0].data_type == Pin.TYPE_FLOAT

def test_deserialize_of_bare_unconfigured_instance():
    """A "macro." (no def_id) instance is corrupt/unconfigured data, but
    must still deserialize without crashing — def_id ends up empty."""
    original = MacroInstanceBlock()
    data = original.serialize()
    restored = MacroInstanceBlock.deserialize(data)
    assert restored.type_id == "macro."
    assert restored.def_id == ""

def test_full_project_save_load_round_trip_preserves_macro_instance():
    """The realistic path: Project.serialize()/Project.deserialize(), which
    for every OTHER block type generically restores pins via a class-
    agnostic Pin.restore_fields() pass AFTER block_class.deserialize() —
    exercising this confirms that generic pass is harmless on top of
    MacroInstanceBlock's own deserialize() override (which already built
    fully-correct pins itself), per core/project.py's block-loading loop."""
    p = Project()
    instance = MacroInstanceBlock(def_id="abc")
    instance.configure(_definition())
    p.add_block(instance)

    data = p.serialize()
    p2 = Project.deserialize(data)

    loaded = p2.blocks[0]
    assert isinstance(loaded, MacroInstanceBlock)
    assert loaded.def_id == "abc"
    assert loaded.type_id == "macro.abc"
    assert loaded.inputs[0].name == "Start"
    assert loaded.outputs[0].name == "Wynik"
    assert loaded.short_id  # assigned by Project.add_block() during load


# ---- clone() --------------------------------------------------------------

def test_clone_preserves_def_id_and_pins():
    original = MacroInstanceBlock(def_id="abc")
    original.configure(_definition())

    clone = original.clone()

    assert clone.def_id == "abc"
    assert clone.type_id == "macro.abc"
    assert len(clone.inputs) == 1
    assert clone.inputs[0].name == "Start"
    assert clone.inputs[0].uuid != original.inputs[0].uuid  # fresh pin identity

def test_clone_preserve_uuid_keeps_pin_uuids_and_connections():
    original = MacroInstanceBlock(def_id="abc")
    original.configure(_definition())
    original.inputs[0].connections.append("external-pin-uuid")

    clone = original.clone(preserve_uuid=True)

    assert clone.uuid == original.uuid
    assert clone.inputs[0].uuid == original.inputs[0].uuid
    assert clone.inputs[0].connections == ["external-pin-uuid"]
