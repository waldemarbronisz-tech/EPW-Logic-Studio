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


def diff_project_state(base: dict, target: dict) -> dict:
    """`base` and `target` are both full Project.serialize()-shaped
    dicts. Blocks are matched by `uuid` (present on every block dict,
    see BaseLogicBlock.SERIALIZED_FIELDS) rather than by list position,
    so an insertion/removal in the middle of the list never makes
    everything after it look "changed". Settings are diffed per top-
    level key (`analog_points`, `internal_bits`, `io_labels`,
    `ela_devices`, `ada_devices`, `short_id_counters`, ...) — whichever
    of those actually differ, whole-value, not deeper than that; they
    don't scale with block count the way `blocks` does, so there's no
    matching payoff in diffing inside them."""
    base_blocks = {b["uuid"]: b for b in base.get("blocks", [])}
    target_blocks = {b["uuid"]: b for b in target.get("blocks", [])}

    changed_or_added = {
        uuid: block
        for uuid, block in target_blocks.items()
        if base_blocks.get(uuid) != block
    }
    removed = [uuid for uuid in base_blocks if uuid not in target_blocks]

    # The overwhelming common case is editing/moving an EXISTING block --
    # no add/remove/reorder at all -- in which case target's list order is
    # identical to base's and there's no need to store a second full list
    # of every uuid in the project just to say so; apply_project_diff()
    # falls back to base's own order when this is None. Only an actual
    # add/remove/reorder (comparatively rare) pays for an explicit list.
    target_order = [b["uuid"] for b in target.get("blocks", [])]
    base_order = [b["uuid"] for b in base.get("blocks", [])]
    order = None if target_order == base_order else target_order

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
        "blocks": {
            "order": order,
            "set": changed_or_added,
            "remove": removed,
        },
        "settings": {"set": changed_settings, "unset": unset_settings},
    }


def apply_project_diff(base: dict, diff: dict) -> dict:
    """Reconstructs the `target` dict that `diff_project_state(base, ...)`
    was computed against. `base` must be the same dict that was passed as
    `base` when the diff was produced -- this function has no way to
    detect a mismatched base, it will simply produce the wrong result."""
    base_blocks = {b["uuid"]: b for b in base.get("blocks", [])}
    order = diff["blocks"]["order"]
    if order is None:
        # Unchanged from base -- see diff_project_state()'s comment on why
        # this is the common case and worth not paying list-sized storage
        # for on every single-block edit.
        order = [b["uuid"] for b in base.get("blocks", [])]
    for uuid in diff["blocks"]["remove"]:
        base_blocks.pop(uuid, None)
    base_blocks.update(diff["blocks"]["set"])
    blocks = [base_blocks[uuid] for uuid in order]

    settings = dict(base.get("settings", {}))
    for key in diff["settings"]["unset"]:
        settings.pop(key, None)
    settings.update(diff["settings"]["set"])

    return {
        "format": diff.get("format", base.get("format")),
        "schema_version": diff.get("schema_version", base.get("schema_version")),
        "settings": settings,
        "blocks": blocks,
    }
