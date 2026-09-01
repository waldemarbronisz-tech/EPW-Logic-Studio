import pytest
from logic_studio.core.project import Project
from logic_studio.blocks.logic_gates import NotGate
from logic_studio.blocks.io_blocks import DigitalInputBlock
from logic_studio.blocks import register_builtin_blocks

register_builtin_blocks()

def test_type_id_persistence():
    p = Project()
    b = NotGate()
    b.display_name = "MY_NOT_GATE"
    p.add_block(b)

    data = p.serialize()

    p2 = Project.deserialize(data)
    loaded_b = p2.blocks[0]

    assert loaded_b.type_id == "logic.not"
    assert loaded_b.display_name == "MY_NOT_GATE"

def test_missing_block_raises_instead_of_silently_dropping():
    """AUDIT_REPORT.md §3.3: an unrecognized type_id must fail loudly, not
    silently vanish from the loaded project — that would be a silent loss of
    safety logic on a corrupted or newer-than-this-build file."""
    p = Project()
    b = NotGate()
    p.add_block(b)

    data = p.serialize()
    # Mangle the type_id to simulate missing plugin/block
    data["blocks"][0]["type_id"] = "logic.missing_xyz"

    with pytest.raises(ValueError, match="logic.missing_xyz"):
        Project.deserialize(data)

def test_duplicate_pointers():
    # If we duplicate a block in scene, it must get a new UUID
    # to avoid pointer collisions
    b1 = NotGate()
    b2 = b1.clone()

    assert b1.uuid != b2.uuid
    # Ensure nested objects like pins also cloned properly or handled
    assert len(b1.inputs) == len(b2.inputs)
    assert b1.inputs[0].uuid != b2.inputs[0].uuid

def test_simulation_state_is_not_persisted():
    p = Project()
    b = DigitalInputBlock()
    b.simulation_state["sim_value"] = True
    b.simulation_state["forced_state"] = True
    p.add_block(b)

    data = p.serialize()

    for block_data in data["blocks"]:
        assert "simulation_state" not in block_data

def test_analog_points_roundtrip():
    p = Project()
    p.settings["analog_points"] = [
        {"address": "AI.TEMP", "name": "Temp", "unit": "°C", "min": -40.0, "max": 150.0, "direction": "input"},
    ]
    b = NotGate()
    p.add_block(b)

    data = p.serialize()
    p2 = Project.deserialize(data)
    assert p2.settings["analog_points"] == [
        {"address": "AI.TEMP", "name": "Temp", "unit": "°C", "min": -40.0, "max": 150.0, "direction": "input"},
    ]

def test_analog_points_default_empty_for_new_project():
    p = Project()
    assert p.settings["analog_points"] == []

def test_analog_points_backward_compat_missing_key():
    """AUDIT_REPORT.md §1.1: a project file saved before analog points
    existed has a settings dict with no "analog_points" key at all."""
    data = {
        "format": "EPW_LOGIC",
        "schema_version": 1,
        "settings": {"name": "Old Project", "version": "1.0", "cycle_time_ms": 100},
        "blocks": [],
    }
    p = Project.deserialize(data)
    assert p.settings["analog_points"] == []
    assert p.settings["name"] == "Old Project"  # rest of settings untouched

def test_format_validation():
    data = {
        "format": "WRONG_FORMAT",
        "schema_version": 1,
        "settings": {},
        "blocks": []
    }

    with pytest.raises(ValueError):
        Project.deserialize(data)
