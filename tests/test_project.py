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

def test_missing_block_graceful_fail():
    p = Project()
    b = NotGate()
    p.add_block(b)

    data = p.serialize()
    # Mangle the type_id to simulate missing plugin/block
    data["blocks"][0]["type_id"] = "logic.missing_xyz"

    p2 = Project.deserialize(data)
    # Should not crash, block list should be empty
    assert len(p2.blocks) == 0

def test_duplicate_pointers():
    # If we duplicate a block in scene, it must get a new UUID
    # to avoid pointer collisions
    b1 = NotGate()
    b2 = b1.clone()

    assert b1.uuid != b2.uuid
    # Ensure nested objects like pins also cloned properly or handled
    assert len(b1.inputs) == len(b2.inputs)
    assert b1.inputs[0].uuid != b2.inputs[0].uuid
