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
"""


def _diff_uuid_list(base_list: list, target_list: list) -> dict:
    """Shared by `blocks` and `wires` (feat/wire-labels §2 — Wire records
    are schematic content, a sibling of blocks, so they get the identical
    treatment): matched by `uuid` rather than list position, so an
    insertion/removal in the middle never makes everything after it look
    "changed"; `order` is stored explicitly only when it actually
    differs from base, since editing/moving an EXISTING entry (the
    overwhelming common case) never reorders the list at all."""
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


def diff_project_state(base: dict, target: dict) -> dict:
    """`base` and `target` are both full Project.serialize()-shaped
    dicts. Blocks and wires are each matched by `uuid` (present on every
    block dict, see BaseLogicBlock.SERIALIZED_FIELDS; and on every wire
    dict, see core/wire.py's Wire.SERIALIZED_FIELDS) via
    `_diff_uuid_list()`. Settings are diffed per top-level key
    (`analog_points`, `internal_bits`, `io_labels`, `ela_devices`,
    `ada_devices`, `short_id_counters`, ...) — whichever of those
    actually differ, whole-value, not deeper than that; they don't scale
    with block count the way `blocks`/`wires` do, so there's no matching
    payoff in diffing inside them."""
    base_settings = base.get("settings", {})
    target_settings = target.get("settings", {})
    changed_settings = {
        key: value
        for key, value in target_settings.items()
        if key not in base_settings or base_settings[key] != value
    }
    unset_settings = [key for key in base_settings if key not in target_settings]

    return {
        "format": target.get("format"),
        "schema_version": target.get("schema_version"),
        "blocks": _diff_uuid_list(base.get("blocks", []), target.get("blocks", [])),
        "wires": _diff_uuid_list(base.get("wires", []), target.get("wires", [])),
        "settings": {"set": changed_settings, "unset": unset_settings},
    }


def apply_project_diff(base: dict, diff: dict) -> dict:
    """Reconstructs the `target` dict that `diff_project_state(base, ...)`
    was computed against. `base` must be the same dict that was passed as
    `base` when the diff was produced -- this function has no way to
    detect a mismatched base, it will simply produce the wrong result."""
    blocks = _apply_uuid_list_diff(base.get("blocks", []), diff["blocks"])
    # "wires" is absent from a diff computed before feat/wire-labels
    # existed (an undo/redo stack entry pushed by an OLDER version of
    # this running process — never a saved FILE, which always goes
    # through Project.deserialize()'s own migration chain instead) --
    # falls back to base's own wires, i.e. "unchanged", the same
    # degrade-gracefully reasoning as `order`'s None case above.
    wires_diff = diff.get("wires")
    wires = base.get("wires", []) if wires_diff is None else _apply_uuid_list_diff(base.get("wires", []), wires_diff)

    settings = dict(base.get("settings", {}))
    for key in diff["settings"]["unset"]:
        settings.pop(key, None)
    settings.update(diff["settings"]["set"])

    return {
        "format": diff.get("format", base.get("format")),
        "schema_version": diff.get("schema_version", base.get("schema_version")),
        "settings": settings,
        "blocks": blocks,
        "wires": wires,
    }
