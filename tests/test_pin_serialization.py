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

def test_every_serializable_block_attribute_is_accounted_for():
    """feat/signal-crossref §0: this class of bug (a field silently never
    restored on load) has now bitten three times — Pin.connections,
    Pin.disabled, and BaseLogicBlock.visibility/execution_state — but the
    field-audit test only ever covered Pin. This is that same audit,
    extended to BaseLogicBlock: every plain attribute a fresh block
    carries must be classified into exactly one of SERIALIZED_FIELDS
    (round-tripped generically), _STRUCTURED_FIELDS (also persisted, via
    its own explicit code — nested structures, or class-determined values
    never overwritten from a file), or _TRANSIENT_FIELDS (never
    serialized, deliberately). An attribute added to __init__ without
    being classified into one of the three fails HERE now, instead of
    silently losing its persistence the way visibility/execution_state
    did."""
    from logic_studio.blocks.base import BaseLogicBlock
    block = AndGate()
    actual = set(vars(block).keys())
    accounted_for = (
        set(BaseLogicBlock.SERIALIZED_FIELDS)
        | set(BaseLogicBlock._STRUCTURED_FIELDS)
        | set(BaseLogicBlock._TRANSIENT_FIELDS)
    )
    assert actual == accounted_for

def test_block_enabled_survives_roundtrip():
    """§0.1 found this exact same bug, latent, on BaseLogicBlock:
    serialize() wrote `visibility`/`enabled`, deserialize() never read them
    back. Nothing in the UI sets either False yet, but the save format has
    claimed to persist both since day one — fixed as part of the same
    refactor (BaseLogicBlock.SERIALIZED_FIELDS).

    feat/io-labels-and-ids §5.6's dead-property audit later REMOVED
    `visibility` entirely (never read by anything but this round-trip and
    the property grid's own display) — only `enabled` remains, since
    validate() genuinely branches on it."""
    p = Project()
    gate = AndGate()
    gate.enabled = False
    p.add_block(gate)

    data = p.serialize()
    p2 = Project.deserialize(data)

    assert p2.blocks[0].enabled is False
    assert not hasattr(p2.blocks[0], 'visibility')

# ---- Level 3: BaseLogicBlock.clone() — the THIRD copy path -----------------
# test/clone-field-coverage: this class of bug has now bitten FOUR times —
# Pin.connections aliased not copied, Pin.disabled dropped on load,
# BaseLogicBlock.visibility/execution_state serialized-but-never-restored
# (all three above), and Pin.safety_relevant never copied by clone() at all
# (fix/safety-block-semantics §6, the ad-hoc regression tests right below
# this section). clone() is not a hypothetical path: core/macros.py's
# expand_project() clones EVERY top-level block on EVERY single compile to
# isolate Validator/GraphBuilder/Exporter from the live project — a field
# clone() drops is a field the COMPILER can never see, no matter how
# faithfully serialize()/deserialize() treat it (the round-trip tests
# above would stay green regardless). This is that same audit, extended to
# the clone() path — Level 1/2 above cover save+load, this covers cloning;
# ARCHITECTURE.md's own "Serializacja" section names a THIRD path on top of
# these two: copying to the clipboard (test_clipboard.py's own
# test_pin_field_survives_copy_paste below).
#
# clone() builds inputs/outputs as two SEPARATE loops (base.py) — exactly
# the shape that already let disabled/safety_relevant drift from each
# other once; parametrizing over BOTH `inputs` and `outputs` here is what
# actually catches that, not just "some pin, somewhere".

# uuid/connections are INTENTIONALLY reset unless preserve_uuid=True
# (base.py's own §4.2 comment: a pasted/duplicated block must get a fresh
# identity) — only meaningfully "preserved" under that flag.
CLONE_IDENTITY_RESET_FIELDS = ("uuid", "connections")
# Every other non-identity Pin field is configuration of the pin ITSELF,
# not tied to a specific wire — must survive clone() regardless of
# preserve_uuid, on both inputs and outputs.
CLONE_ALWAYS_FIELDS = tuple(
    f for f in PROJECT_LEVEL_FIELDS if f not in CLONE_IDENTITY_RESET_FIELDS
)

def test_clone_field_partition_covers_every_project_level_field():
    """Guards the guard: a field falling through the cracks of this
    partition (neither CLONE_ALWAYS_FIELDS nor CLONE_IDENTITY_RESET_FIELDS)
    would silently never be checked at all by either parametrized test
    below."""
    assert set(CLONE_ALWAYS_FIELDS) | set(CLONE_IDENTITY_RESET_FIELDS) == set(PROJECT_LEVEL_FIELDS)

@pytest.mark.parametrize("side", ["inputs", "outputs"])
@pytest.mark.parametrize("preserve_uuid", [False, True])
@pytest.mark.parametrize("field", CLONE_ALWAYS_FIELDS)
def test_pin_field_survives_clone_on_both_sides_regardless_of_preserve_uuid(field, preserve_uuid, side):
    gate = AndGate()
    pin = getattr(gate, side)[0]
    setattr(pin, field, NON_DEFAULT_VALUES[field])

    clone = gate.clone(preserve_uuid=preserve_uuid)
    cloned_pin = getattr(clone, side)[0]

    assert getattr(cloned_pin, field) == NON_DEFAULT_VALUES[field]

@pytest.mark.parametrize("side", ["inputs", "outputs"])
@pytest.mark.parametrize("field", CLONE_IDENTITY_RESET_FIELDS)
def test_pin_identity_field_survives_clone_only_with_preserve_uuid(field, side):
    gate = AndGate()
    pin = getattr(gate, side)[0]
    setattr(pin, field, NON_DEFAULT_VALUES[field])

    preserved = gate.clone(preserve_uuid=True)
    assert getattr(getattr(preserved, side)[0], field) == NON_DEFAULT_VALUES[field]

    fresh = gate.clone(preserve_uuid=False)
    assert getattr(getattr(fresh, side)[0], field) != NON_DEFAULT_VALUES[field]  # deliberately reset


# ---- BaseLogicBlock's OWN fields through clone() ---------------------------

BLOCK_NON_DEFAULT_VALUES = {
    "uuid": "22222222-2222-2222-2222-222222222222",
    "short_id": "g99",
    "display_name": "CustomBlockName",
    "execution_priority": 42,
    "color": "#ABCDEF",
    "enabled": False,
}

def test_every_block_field_has_a_non_default_clone_test_value():
    from logic_studio.blocks.base import BaseLogicBlock
    assert set(BaseLogicBlock.SERIALIZED_FIELDS) == set(BLOCK_NON_DEFAULT_VALUES.keys())

# short_id is deliberately ALWAYS blanked by clone() (base.py's own §4.2
# comment) — a pasted/duplicated/compiled-clone block must never collide
# with the id its source already has, regardless of preserve_uuid.
BLOCK_CLONE_ALWAYS_FIELDS = ("display_name", "execution_priority", "color", "enabled")

def test_block_clone_field_partition_covers_every_serialized_field():
    from logic_studio.blocks.base import BaseLogicBlock
    assert set(BLOCK_CLONE_ALWAYS_FIELDS) | {"uuid", "short_id"} == set(BaseLogicBlock.SERIALIZED_FIELDS)

@pytest.mark.parametrize("preserve_uuid", [False, True])
@pytest.mark.parametrize("field", BLOCK_CLONE_ALWAYS_FIELDS)
def test_block_field_survives_clone_regardless_of_preserve_uuid(field, preserve_uuid):
    gate = AndGate()
    setattr(gate, field, BLOCK_NON_DEFAULT_VALUES[field])
    clone = gate.clone(preserve_uuid=preserve_uuid)
    assert getattr(clone, field) == BLOCK_NON_DEFAULT_VALUES[field]

def test_block_uuid_survives_clone_only_with_preserve_uuid():
    gate = AndGate()
    gate.uuid = BLOCK_NON_DEFAULT_VALUES["uuid"]

    preserved = gate.clone(preserve_uuid=True)
    assert preserved.uuid == BLOCK_NON_DEFAULT_VALUES["uuid"]

    fresh = gate.clone(preserve_uuid=False)
    assert fresh.uuid != BLOCK_NON_DEFAULT_VALUES["uuid"]

def test_block_short_id_is_always_blanked_by_clone_regardless_of_preserve_uuid():
    """Regression-shaped, not just parametrized: short_id is the one
    SERIALIZED_FIELDS entry clone() must NEVER copy, under either flag —
    worth its own explicit assertion, not just "not in ALWAYS_FIELDS"."""
    gate = AndGate()
    gate.short_id = BLOCK_NON_DEFAULT_VALUES["short_id"]

    assert gate.clone(preserve_uuid=True).short_id == ""
    assert gate.clone(preserve_uuid=False).short_id == ""


# ---- fix/safety-block-semantics §6: safety_relevant must survive clone() -
# Kept as explicit, named regressions alongside the parametrized coverage
# above — this is the bug that started this whole audit; a reader tracing
# "why does this test exist" shouldn't have to reverse-engineer it purely
# from a parametrize table.

def test_clone_preserves_safety_relevant_on_output_pins():
    from logic_studio.blocks.analog_io import AnalogInputBlock

    ai = AnalogInputBlock()
    assert ai.outputs[1].safety_relevant is True  # Quality, sanity check
    clone = ai.clone(preserve_uuid=True)
    assert clone.outputs[1].safety_relevant is True

    clone_no_uuid = ai.clone(preserve_uuid=False)
    assert clone_no_uuid.outputs[1].safety_relevant is True

def test_clone_preserves_safety_relevant_on_input_pins():
    """Inputs can carry safety_relevant too (Pin.__init__ makes no
    direction distinction) even though no shipped block sets one today —
    clone() must not special-case outputs only."""
    from logic_studio.blocks.logic_gates import AndGate

    gate = AndGate()
    gate.inputs[0].safety_relevant = True
    clone = gate.clone()
    assert clone.inputs[0].safety_relevant is True
    assert clone.inputs[1].safety_relevant is False

def test_clone_preserves_false_safety_relevant_too():
    """Not just "copies True" -- a pin that ISN'T safety_relevant on the
    original must not become True on the clone either."""
    from logic_studio.blocks.logic_gates import AndGate

    gate = AndGate()
    clone = gate.clone()
    assert clone.outputs[0].safety_relevant is False


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
