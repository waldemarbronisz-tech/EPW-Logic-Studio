"""feat/wire-labels §2.4 — the same field-audit discipline
test_pin_serialization.py already established for Pin/BaseLogicBlock,
applied to the new core/wire.py::Wire. Three paths, per the spec's own
instruction: save/load (serialize()/deserialize()), clone(), and
clipboard copy (LogicScene.copy_selected_items()/paste_clipboard(),
covered in tests/test_wire_clipboard.py since it needs a real Project/
Qt scene — this file stays Qt-free, mirroring Wire's own design).
"""
import pytest

from logic_studio.core.wire import Wire

# One non-default value per SERIALIZED_FIELDS entry — same "guards the
# guard" reasoning as test_pin_serialization.py's own NON_DEFAULT_VALUES.
NON_DEFAULT_VALUES = {
    "uuid": "11111111-1111-1111-1111-111111111111",
    "source_pin": "aaaaaaaa-0000-0000-0000-000000000001",
    "dest_pin": "bbbbbbbb-0000-0000-0000-000000000002",
    "free_end_source": {"x": 12.0, "y": 34.0},
    "free_end_dest": {"x": 56.0, "y": 78.0},
    "label": "Blokada ZS",
}


def test_every_field_has_a_non_default_test_value():
    assert set(Wire.SERIALIZED_FIELDS) == set(NON_DEFAULT_VALUES.keys())


def test_every_serializable_wire_attribute_is_accounted_for():
    """Every plain attribute a fresh Wire carries must be in
    SERIALIZED_FIELDS — unlike Pin/BaseLogicBlock, Wire has no transient
    runtime-only attributes at all (it's pure schematic data, never
    touched by the engine), so there is no second tuple to split
    against."""
    wire = Wire()
    assert set(vars(wire).keys()) == set(Wire.SERIALIZED_FIELDS)


# ---- Level 1: raw Wire.serialize()/Wire.deserialize() — every field ------

@pytest.mark.parametrize("field", Wire.SERIALIZED_FIELDS)
def test_wire_field_roundtrips_through_serialize_deserialize(field):
    wire = Wire()
    setattr(wire, field, NON_DEFAULT_VALUES[field])

    data = wire.serialize()
    reloaded = Wire.deserialize(data)

    assert getattr(reloaded, field) == NON_DEFAULT_VALUES[field]

def test_free_end_dicts_are_copied_not_aliased_on_deserialize():
    """Same regression class test_pin_serialization.py's own
    test_connections_field_is_copied_not_aliased_on_deserialize()
    guards against for Pin.connections — a mutable field must never come
    back as the SAME object the input dict holds."""
    wire = Wire()
    wire.free_end_source = {"x": 1.0, "y": 2.0}
    data = wire.serialize()

    reloaded = Wire.deserialize(data)
    reloaded.free_end_source["x"] = 999.0

    assert data["free_end_source"]["x"] == 1.0

def test_serialize_itself_does_not_alias_the_live_free_end_dict():
    wire = Wire()
    wire.free_end_source = {"x": 1.0, "y": 2.0}
    data = wire.serialize()
    data["free_end_source"]["x"] = 999.0
    assert wire.free_end_source["x"] == 1.0

def test_absent_fields_fall_back_to_constructor_defaults():
    """Back-compat: a dict missing a field (e.g. one saved by a version
    of this code that didn't have it yet) leaves __init__'s own default
    standing, same as Pin.restore_fields()'s "field not in data: skip"."""
    wire = Wire.deserialize({"uuid": "x"})
    assert wire.source_pin is None
    assert wire.dest_pin is None
    assert wire.free_end_source is None
    assert wire.free_end_dest is None
    assert wire.label == ""


# ---- Level 2: clone() — every field ---------------------------------------

@pytest.mark.parametrize("field", Wire.SERIALIZED_FIELDS)
def test_wire_field_survives_clone(field):
    wire = Wire()
    setattr(wire, field, NON_DEFAULT_VALUES[field])
    clone = wire.clone()
    assert getattr(clone, field) == NON_DEFAULT_VALUES[field]

def test_clone_free_end_dicts_are_independent_objects():
    wire = Wire()
    wire.free_end_dest = {"x": 5.0, "y": 6.0}
    clone = wire.clone()
    clone.free_end_dest["x"] = -1.0
    assert wire.free_end_dest["x"] == 5.0

def test_clone_preserves_uuid():
    """Unlike a block's clone() (which mints a fresh uuid for an
    ordinary duplicate — base.py's own §4.2), Wire.clone() keeps the SAME
    uuid — it exists to support Project-level copy operations that
    remap source_pin/dest_pin onto fresh pins THEMSELVES afterward
    (LogicScene.paste_clipboard()'s established two-pass pattern), not
    to duplicate a wire as a new, independent entity on its own."""
    wire = Wire()
    clone = wire.clone()
    assert clone.uuid == wire.uuid


# ---- Semantics ------------------------------------------------------------

def test_has_free_end_true_when_either_end_missing():
    wire = Wire()
    wire.source_pin = "p1"
    wire.dest_pin = None
    assert wire.has_free_end() is True
    assert wire.is_fully_connected() is False

def test_has_free_end_false_when_both_ends_connected():
    wire = Wire()
    wire.source_pin = "p1"
    wire.dest_pin = "p2"
    assert wire.has_free_end() is False
    assert wire.is_fully_connected() is True


# ---- has_label() (fix/wire-labels-and-project-integrity §A2) --------------

def test_has_label_true_for_a_real_label():
    wire = Wire()
    wire.label = "Blokada ZS"
    assert wire.has_label() is True

def test_has_label_false_for_empty_string():
    wire = Wire()
    assert wire.label == ""
    assert wire.has_label() is False

def test_has_label_false_for_whitespace_only():
    """User correction: a label made of nothing but spaces counts as no
    label at all, everywhere this is checked."""
    wire = Wire()
    wire.label = "   "
    assert wire.has_label() is False

def test_has_label_true_for_a_label_with_leading_or_trailing_spaces():
    """Only a WHOLLY-whitespace label is "no label" -- "Wyl. Q1 " (a
    stray trailing space) is still a real, meaningful label."""
    wire = Wire()
    wire.label = "  Wyl. Q1  "
    assert wire.has_label() is True
