"""feat/wire-modes-and-labels §0.1 — structural fix for Pin (and
BaseLogicBlock) serialization: a declarative SERIALIZED_FIELDS list walked
by both serialize() and deserialize()/restore_fields(), instead of two
hand-written enumerations free to silently drift apart. This is the second
time that drift actually happened (feat/internal-bits: `connections`
aliased instead of copied; feat/editor-modes-and-geometry: `disabled`
dropped entirely) — these are the guardian tests meant to make a third
occurrence impossible to ship unnoticed.
"""
import pytest

from logic_studio.blocks.pin import Pin
from logic_studio.core.project import Project
from logic_studio.blocks.logic_gates import AndGate
from logic_studio.blocks import register_builtin_blocks

register_builtin_blocks()

# One non-default value per SERIALIZED_FIELDS entry. Kept as a plain dict
# (not computed) so test_every_field_has_a_non_default_test_value can catch
# a field added to SERIALIZED_FIELDS without a matching entry here, instead
# of the parametrized test below silently KeyError-ing in a way pytest
# might report confusingly.
NON_DEFAULT_VALUES = {
    "uuid": "11111111-1111-1111-1111-111111111111",
    "name": "CustomPinName",
    "direction": Pin.DIR_OUTPUT,
    "data_type": Pin.TYPE_FLOAT,
    "connections": ["aaaaaaaa-0000-0000-0000-000000000001", "bbbbbbbb-0000-0000-0000-000000000002"],
    "disabled": True,
    "safety_relevant": True,
}


def test_every_field_has_a_non_default_test_value():
    """Guards the guard: a field added to Pin.SERIALIZED_FIELDS without a
    matching NON_DEFAULT_VALUES entry must fail HERE, loudly, not be
    silently skipped by the parametrized test below."""
    assert set(Pin.SERIALIZED_FIELDS) == set(NON_DEFAULT_VALUES.keys())


def test_every_serializable_pin_attribute_is_listed_in_serialized_fields():
    """§0.1 field-audit: every plain attribute a fresh Pin carries must be
    accounted for — either persisted (SERIALIZED_FIELDS) or explicitly
    marked transient (_TRANSIENT_FIELDS). An attribute added to __init__
    without being added to either fails this test immediately, instead of
    silently never being saved (or silently never being excluded on
    purpose)."""
    pin = Pin("x", Pin.DIR_INPUT)
    actual = set(vars(pin).keys())
    accounted_for = set(Pin.SERIALIZED_FIELDS) | set(Pin._TRANSIENT_FIELDS)
    assert actual == accounted_for


# ---- Level 1: raw Pin.serialize()/Pin.deserialize() — every field --------

@pytest.mark.parametrize("field", Pin.SERIALIZED_FIELDS)
def test_pin_field_roundtrips_through_serialize_deserialize(field):
    pin = Pin("Original", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN)
    setattr(pin, field, NON_DEFAULT_VALUES[field])

    data = pin.serialize()
    reloaded = Pin.deserialize(data)

    assert getattr(reloaded, field) == NON_DEFAULT_VALUES[field]

def test_connections_field_is_copied_not_aliased_on_deserialize():
    """Regression for the FIRST occurrence of this bug class
    (feat/internal-bits): deserialize() must not hand back a list that's
    the same object as the dict's, or mutating one silently mutates the
    other project's in-memory state too."""
    pin = Pin("Original", Pin.DIR_INPUT)
    data = pin.serialize()
    data["connections"] = ["shared-uuid"]

    reloaded = Pin.deserialize(data)
    reloaded.connections.append("mutated-after-load")

    assert data["connections"] == ["shared-uuid"]


# ---- Level 2: full Project save/load through tmp_path ---------------------
# A block's own pins already have the correct name/direction/data_type from
# construction (the block's CLASS defines its own pin shape) — the project
# loader (Project.deserialize(), via Pin.restore_fields()) deliberately
# never overwrites those three (Pin._IDENTITY_FIELDS) from the file, only
# from a freshly-constructed Pin.deserialize() call. So at the whole-
# project level, only the non-identity fields are meaningfully round-
# trippable per-instance; name/direction/data_type are already covered by
# the raw Pin-level test above.
PROJECT_LEVEL_FIELDS = tuple(f for f in Pin.SERIALIZED_FIELDS if f not in Pin._IDENTITY_FIELDS)

def test_every_project_level_field_is_a_serialized_field_minus_identity():
    assert set(PROJECT_LEVEL_FIELDS) == set(Pin.SERIALIZED_FIELDS) - set(Pin._IDENTITY_FIELDS)
    assert len(PROJECT_LEVEL_FIELDS) > 0

@pytest.mark.parametrize("field", PROJECT_LEVEL_FIELDS)
def test_pin_field_survives_full_project_save_load_roundtrip(field, tmp_path):
    p = Project()
    gate = AndGate()
    setattr(gate.inputs[0], field, NON_DEFAULT_VALUES[field])
    p.add_block(gate)

    path = tmp_path / "roundtrip.epwlogic"
    p.save_to_file(str(path))
    p2 = Project.load_from_file(str(path))

    reloaded_pin = p2.blocks[0].inputs[0]
    assert getattr(reloaded_pin, field) == NON_DEFAULT_VALUES[field]

def test_disabled_field_survives_roundtrip_explicit_regression():
    """Regression for the SECOND (and most recent) occurrence of this bug
    class (feat/editor-modes-and-geometry §2): `disabled` was serialized
    but never restored by the project loader's old hand-written loop."""
    p = Project()
    gate = AndGate()
    gate.inputs[1].disabled = True
    p.add_block(gate)

    data = p.serialize()
    p2 = Project.deserialize(data)

    assert p2.blocks[0].inputs[0].disabled is False
    assert p2.blocks[0].inputs[1].disabled is True


# ---- BaseLogicBlock gets the same treatment (§0.1: "to samo dla bloku") --

def test_block_visibility_and_enabled_survive_roundtrip():
    """§0.1 found this exact same bug, latent, on BaseLogicBlock:
    serialize() wrote `visibility`/`enabled`, deserialize() never read them
    back. Nothing in the UI sets either False yet, but the save format has
    claimed to persist both since day one — fixed as part of the same
    refactor (BaseLogicBlock.SERIALIZED_FIELDS)."""
    p = Project()
    gate = AndGate()
    gate.visibility = False
    gate.enabled = False
    p.add_block(gate)

    data = p.serialize()
    p2 = Project.deserialize(data)

    assert p2.blocks[0].visibility is False
    assert p2.blocks[0].enabled is False

def test_block_serialized_fields_round_trip_via_project_deserialize():
    p = Project()
    gate = AndGate()
    gate.display_name = "MójAND"
    gate.color = "#123456"
    gate.execution_priority = 7
    p.add_block(gate)

    data = p.serialize()
    p2 = Project.deserialize(data)
    reloaded = p2.blocks[0]

    assert reloaded.display_name == "MójAND"
    assert reloaded.color == "#123456"
    assert reloaded.execution_priority == 7
