"""Diff/patch for full `Project.serialize()`-shaped dicts.

`Project`'s undo/redo history used to store a complete, independent
snapshot of `{"format", "schema_version", "settings", "blocks": [...]}`
per entry, on a 50-entry cap — measured (AUDIT_REPORT.md §9.1) at ~9.2KB
for an 11-block example, growing roughly linearly with block count, for
up to ~459KiB in the worst case. The overwhelming majority of that per-
entry cost is blocks that DIDN'T change between two consecutive undo
steps (a drag/property-edit/wire-connect typically touches one block, or
a handful) — this module lets `core/project.py` store only WHAT CHANGED
between two states instead of a full duplicate of everything, while still
being able to reconstruct either state exactly on demand.

Two functions, one direction each:
- `diff_project_state(base, target)` -> a diff such that
  `apply_project_diff(base, diff) == target`.
- `apply_project_diff(base, diff)` -> reconstructs `target`.

Both operate purely on plain dicts/lists (no Project/BaseLogicBlock
objects involved) — testable in complete isolation from Qt/the block
registry. See core/project.py's `_stack_push`/`_stack_pop` for how this
is actually used to keep each undo/redo stack's memory proportional to
the SIZE OF EACH EDIT rather than the size of the whole project.

feat/wire-labels: table-driven over three registries below, one per
TREATMENT a top-level key in Project.serialize()'s output can get —
rather than each function hand-listing "format", "schema_version",
"blocks", "wires", "settings" by name, which is exactly the kind of
hand-duplicated enumeration free to silently drift (a key added to
Project.serialize() without a matching entry in exactly one registry
here) that Pin/BaseLogicBlock's own SERIALIZED_FIELDS convention exists
to prevent elsewhere in this codebase. KNOWN_TOP_LEVEL_KEYS is the
single source of truth tests/test_state_diff.py's own meta-level
guardian test checks Project().serialize().keys() against — the
SEVENTH occurrence of "a field/key added without updating every path
that needs to know about it" this project has now found and guarded
against (see test_pin_serialization.py's own docstring for the first
few; this module's own wires-diffing, added alongside core/wire.py, was
the sixth).
"""

# A key present in Project.serialize()'s output but absent from every
# one of these three tuples is UNHANDLED by this module — silently
# dropped by apply_project_diff() (or passed through some fallback that
# happens to be wrong) rather than genuinely diffed. Exactly one
# registry per key; a key appearing in more than one, or in none, means
# this module and Project.serialize() have drifted apart.
SCALAR_KEYS = ("format", "schema_version")
UUID_LIST_KEYS = ("blocks", "wires")
DICT_KEYS = ("settings",)
KNOWN_TOP_LEVEL_KEYS = frozenset(SCALAR_KEYS) | frozenset(UUID_LIST_KEYS) | frozenset(DICT_KEYS)


def _diff_uuid_list(base_list: list, target_list: list) -> dict:
    """Shared by every key in UUID_LIST_KEYS (`blocks`, `wires` — Wire
    records are schematic content, a sibling of blocks, so they get the
    identical treatment): matched by `uuid` rather than list position,
    so an insertion/removal in the middle never makes everything after
    it look "changed"; `order` is stored explicitly only when it
    actually differs from base, since editing/moving an EXISTING entry
    (the overwhelming common case) never reorders the list at all."""
    base_by_uuid = {item["uuid"]: item for item in base_list}
    target_by_uuid = {item["uuid"]: item for item in target_list}

    changed_or_added = {
        uid: item
        for uid, item in target_by_uuid.items()
        if base_by_uuid.get(uid) != item
    }
    removed = [uid for uid in base_by_uuid if uid not in target_by_uuid]

    target_order = [item["uuid"] for item in target_list]
    base_order = [item["uuid"] for item in base_list]
    order = None if target_order == base_order else target_order

    return {"order": order, "set": changed_or_added, "remove": removed}


def _apply_uuid_list_diff(base_list: list, diff: dict) -> list:
    by_uuid = {item["uuid"]: item for item in base_list}
    order = diff["order"]
    if order is None:
        # Unchanged from base -- see _diff_uuid_list()'s comment on why
        # this is the common case and worth not paying list-sized storage
        # for on every single-entry edit.
        order = [item["uuid"] for item in base_list]
    for uid in diff["remove"]:
        by_uuid.pop(uid, None)
    by_uuid.update(diff["set"])
    return [by_uuid[uid] for uid in order]


def _diff_dict(base_dict: dict, target_dict: dict) -> dict:
    """Shared by every key in DICT_KEYS (`settings` today) — diffed per
    top-level key of the dict itself (`analog_points`, `internal_bits`,
    `io_labels`, `ela_devices`, `ada_devices`, `short_id_counters`, ...
    for `settings`) — whichever of those actually differ, whole-value,
    not deeper than that; they don't scale with block count the way
    UUID_LIST_KEYS entries do, so there's no matching payoff in diffing
    inside them."""
    changed = {
        key: value
        for key, value in target_dict.items()
        if key not in base_dict or base_dict[key] != value
    }
    unset = [key for key in base_dict if key not in target_dict]
    return {"set": changed, "unset": unset}


def _apply_dict_diff(base_dict: dict, diff: dict) -> dict:
    result = dict(base_dict)
    for key in diff["unset"]:
        result.pop(key, None)
    result.update(diff["set"])
    return result


def diff_project_state(base: dict, target: dict) -> dict:
    """`base` and `target` are both full Project.serialize()-shaped
    dicts. Every key in KNOWN_TOP_LEVEL_KEYS gets diffed according to
    its own registry above; a key present in `target` but not in any
    registry is silently ignored by this loop (caught instead by
    tests/test_state_diff.py's meta-level test comparing
    KNOWN_TOP_LEVEL_KEYS against a real Project().serialize().keys())."""
    diff = {}
    for key in SCALAR_KEYS:
        diff[key] = target.get(key)
    for key in UUID_LIST_KEYS:
        diff[key] = _diff_uuid_list(base.get(key, []), target.get(key, []))
    for key in DICT_KEYS:
        diff[key] = _diff_dict(base.get(key, {}), target.get(key, {}))
    return diff


def apply_project_diff(base: dict, diff: dict) -> dict:
    """Reconstructs the `target` dict that `diff_project_state(base, ...)`
    was computed against. `base` must be the same dict that was passed as
    `base` when the diff was produced -- this function has no way to
    detect a mismatched base, it will simply produce the wrong result.

    A key from UUID_LIST_KEYS/DICT_KEYS absent from `diff` itself (a
    diff computed by an OLDER in-memory version of this code, before
    that key existed — never a SAVED FILE, which always goes through
    Project.deserialize()'s own migration chain instead) falls back to
    base's own value for that key, i.e. "unchanged" — the same
    degrade-gracefully reasoning `order`'s own None case already uses."""
    result = {}
    for key in SCALAR_KEYS:
        result[key] = diff.get(key, base.get(key))
    for key in UUID_LIST_KEYS:
        key_diff = diff.get(key)
        result[key] = base.get(key, []) if key_diff is None else _apply_uuid_list_diff(base.get(key, []), key_diff)
    for key in DICT_KEYS:
        key_diff = diff.get(key)
        result[key] = base.get(key, {}) if key_diff is None else _apply_dict_diff(base.get(key, {}), key_diff)
    return result
