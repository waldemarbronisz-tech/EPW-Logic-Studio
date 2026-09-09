"""feat/wire-labels §2 — the schematic-level "wire" entity this project
never had. Before this module, a connection between two pins had NO
object representation at all: `Pin.connections` (blocks/pin.py) is
purely a list of the OTHER pin's uuid on each end, symmetric, with no
room for a label or a missing end. Every WireItem on the canvas
(ui/canvas/wire_item.py) is a disposable VISUAL reconstruction, rebuilt
from scratch off Pin.connections every time a project loads
(MainWindow._reconstruct_scene()) — nothing to attach metadata to
survives a save/load round trip.

`Wire` fills that gap, but DELIBERATELY only for wires that need to
carry something Pin.connections can't: a label (§3) and/or a free
(unconnected) end (§2). An ordinary, fully-connected, unlabeled wire —
the overwhelming common case, and every wire in every project that
predates this feature — gets NO Wire record at all; it stays exactly
as it's always been, discovered purely from Pin.connections. This is
deliberate, not an oversight: duplicating the topology of every
connection in the project into a second, parallel list would be a far
larger, riskier change (two sources of truth that can drift, touching
GraphBuilder/Exporter/clipboard/undo for every wire that exists today)
than this feature actually needs. A free end has no second pin to be
discovered FROM at all, so it structurally REQUIRES its own record;
a label is attached to a specific wire, so it needs somewhere to live
too — but a plain, fully-wired, unlabeled connection needs neither.

Project.wires is a live-object list (see core/project.py), a sibling of
Project.blocks, not a plain-dict entry under Project.settings — a Wire
is schematic CONTENT (it names live pins by uuid, exactly like a block's
own pins do), not project CONFIGURATION the way analog_points/
internal_bits/io_labels are. core/state_diff.py's undo/redo diffing
treats it exactly like `blocks` for the same reason.
"""
import uuid as _uuid


class Wire:
    """One schematic wire record. Exactly one of (`source_pin`,
    `free_end_source`) is meaningful at a time, and likewise for
    (`dest_pin`, `free_end_dest`) — enforced by callers (Project/the
    canvas), not by this class, matching Pin's own "constructor sets
    identity, callers set state" split. A Wire with NEITHER `source_pin`
    NOR `dest_pin` set (two free ends) must never exist — §2.1's "przewód
    bez żadnego podłączonego końca jest niedozwolony" — see
    Project.add_wire()."""

    # §2.2: the single source of truth for serialize()/deserialize()/
    # clone()/clipboard-copy, exactly the SERIALIZED_FIELDS convention
    # Pin/BaseLogicBlock already established — a field added here is
    # picked up by every one of those call sites automatically, and by
    # the field-audit tests (tests/test_wire_serialization.py) that
    # enforce nothing is ever added to __init__ without also being added
    # here.
    SERIALIZED_FIELDS = (
        "uuid", "source_pin", "dest_pin",
        "free_end_source", "free_end_dest", "label",
    )

    def __init__(self):
        self.uuid: str = str(_uuid.uuid4())
        # Pin.uuid of the driving end, or None if that end is free (§2.1).
        self.source_pin: str | None = None
        # Pin.uuid of the receiving end, or None if that end is free.
        self.dest_pin: str | None = None
        # {"x": float, "y": float} scene position of the free source end,
        # or None while source_pin is set instead.
        self.free_end_source: dict | None = None
        # {"x": float, "y": float} scene position of the free dest end,
        # or None while dest_pin is set instead.
        self.free_end_dest: dict | None = None
        # §3.1: empty by default, never auto-suggested (§3.2) — a
        # network-merging identifier when this wire has a free end, or a
        # purely documentary annotation when both ends are real pins.
        self.label: str = ""

    def has_free_end(self) -> bool:
        """True if either end is unconnected. A Wire with BOTH ends free
        should never exist (Project.add_wire() rejects it) — this is
        simply "at least one real pin is missing", not "exactly one"."""
        return self.source_pin is None or self.dest_pin is None

    def is_fully_connected(self) -> bool:
        return self.source_pin is not None and self.dest_pin is not None

    def has_label(self) -> bool:
        """fix/wire-labels-and-project-integrity §A2 (user correction):
        a label made of nothing but whitespace counts as no label at
        all — the single place that rule lives, so every caller (label-
        merge grouping, the free-end-without-label warning, rendering,
        context-menu enablement) agrees on it instead of re-deriving
        `.strip()` truthiness independently and risking one of them
        drifting."""
        return bool((self.label or "").strip())

    def serialize(self) -> dict:
        data = {}
        for field in self.SERIALIZED_FIELDS:
            value = getattr(self, field)
            # free_end_source/free_end_dest are the only nested mutable
            # values here (plain dicts) — copied, never aliased, same
            # reasoning as Pin.serialize()'s "connections" list copy
            # (test_pin_serialization.py's own regression for exactly
            # this bug class).
            if isinstance(value, dict):
                value = dict(value)
            data[field] = value
        return data

    @classmethod
    def deserialize(cls, data: dict) -> "Wire":
        wire = cls()
        for field in cls.SERIALIZED_FIELDS:
            if field not in data:
                continue  # back-compat: absent -> whatever __init__ already set
            value = data[field]
            if isinstance(value, dict):
                value = dict(value)
            setattr(wire, field, value)
        return wire

    def clone(self) -> "Wire":
        """A fresh Wire with the SAME uuid and pin references — used by
        Project-level copy operations (clipboard) that then remap
        source_pin/dest_pin onto freshly-pasted pins themselves, the same
        two-pass pattern LogicScene.paste_clipboard() already uses for
        Pin.connections (blocks/pin.py has no clone() of its own for the
        identical reason — a bare pin is never copied on its own,
        only ever as part of its owning block)."""
        new_wire = Wire()
        new_wire.uuid = self.uuid
        new_wire.source_pin = self.source_pin
        new_wire.dest_pin = self.dest_pin
        new_wire.free_end_source = dict(self.free_end_source) if self.free_end_source else None
        new_wire.free_end_dest = dict(self.free_end_dest) if self.free_end_dest else None
        new_wire.label = self.label
        return new_wire


def check_wire_pin_consistency(project) -> list:
    """feat/wire-labels: the two representations of "these two pins are
    connected" — a fully-connected Wire's (source_pin, dest_pin) pair,
    and the pins' own Pin.connections lists — must always agree, or a
    large project's compile will eventually see a Wire describing a
    connection that doesn't actually exist (or vice versa: a real
    connection a stale Wire record no longer matches). Checked in BOTH
    directions per wire, since Pin.connect() is supposed to keep
    .connections symmetric, but nothing stops a Wire object from being
    hand-built (a test, or a future UI bug) without actually calling it.

    Returns a list of human-readable violation strings — empty means
    fully consistent. A free-end Wire (has_free_end() True) is skipped
    entirely: it names only one real pin, nothing on the other side to
    cross-reference against.

    This does NOT check the reverse direction wholesale (i.e. "every
    Pin.connections entry has a matching Wire record") — by design,
    core/wire.py's own docstring above, the overwhelming majority of
    connections have NO Wire record at all, and that is correct, not a
    violation."""
    pin_by_uuid = {}
    for block in project.blocks:
        for pin in block.inputs + block.outputs:
            pin_by_uuid[pin.uuid] = pin

    violations = []
    for wire in project.wires:
        if wire.has_free_end():
            continue

        source_pin = pin_by_uuid.get(wire.source_pin)
        dest_pin = pin_by_uuid.get(wire.dest_pin)
        if source_pin is None:
            violations.append(f"Wire {wire.uuid}: source_pin {wire.source_pin} names no pin in this project")
            continue
        if dest_pin is None:
            violations.append(f"Wire {wire.uuid}: dest_pin {wire.dest_pin} names no pin in this project")
            continue

        if wire.dest_pin not in source_pin.connections:
            violations.append(
                f"Wire {wire.uuid}: source pin {wire.source_pin} does not list "
                f"dest pin {wire.dest_pin} in its own connections"
            )
        if wire.source_pin not in dest_pin.connections:
            violations.append(
                f"Wire {wire.uuid}: dest pin {wire.dest_pin} does not list "
                f"source pin {wire.source_pin} in its own connections"
            )
    return violations
