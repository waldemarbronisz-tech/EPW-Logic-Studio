"""feat/project-diff — a human-readable summary of what changed between
two `Project.serialize()`-shaped dicts, for the "Porównaj wersje
projektu" view (comparing the live project against its last saved file,
or two arbitrary `.epwlogic` files against each other — e.g. two exports
from git history, or two engineers' own copies).

Deliberately a SEPARATE module from `core/state_diff.py`, not a reuse of
it: that one exists purely for undo/redo's own storage efficiency (whole-
block granularity — "this block's dict differs somehow" — chosen because
that's cheap to compute and cheap to store on every single edit). This
module trades that efficiency for READABILITY: which specific property,
pin connection, or setting changed, with its old and new value, meant to
be read by an engineer reviewing what changed, not reconstructed byte-
for-byte the way undo/redo needs to.

Pure logic, no Qt — see ui/project_diff_dialog.py for the view built on
this.
"""


def compare_projects(base: dict, target: dict) -> dict:
    """`base`/`target` are both full `Project.serialize()`-shaped dicts —
    typically an OLDER version (`base`) and a NEWER one (`target`) of the
    same project, though nothing here requires that; comparing two
    unrelated projects just reports everything as added/removed, which is
    degenerate but not wrong. Blocks are matched by `uuid` (present on
    every block dict), never by list position, so an insertion/removal in
    the middle of the list never makes everything after it look changed.

    Returns:
        {"blocks_added": [block_dict, ...],     # in target, not base
         "blocks_removed": [block_dict, ...],   # in base, not target
         "blocks_changed": [
             {"uuid", "short_id", "display_name", "type_id",
              "field_changes": [{"field", "old", "new"}, ...],
              "moved": bool,
              "connection_changes": [
                  {"pin_uuid", "pin_name", "added": [...], "removed": [...]}
              ]},
             ...],
         "settings_changes": [{"key", "old", "new"}, ...]}   # None old/new = added/removed key

    `field_changes` covers `display_name`/`enabled`/`color`/
    `execution_priority` and every key of `properties` (Address/Tag/
    Comment/...) — `type_id`/`category`/`description` are never diffed,
    same reasoning BaseLogicBlock.SERIALIZED_FIELDS excludes them from
    round-tripping generically: they're determined by the block's own
    class, never data that legitimately "changes" on an existing block.
    Position (`x`/`y`) is reported separately as `moved` rather than as a
    field change — a pure drag on the canvas is a much lower-priority
    signal for a schematic review than an actual logic/wiring change,
    worth keeping visually distinct rather than buried in the same list.
    `settings_changes` is whole-key, same granularity as
    core/state_diff.py's own settings handling — a project's settings
    (analog_points, internal_bits, macro_definitions, ...) don't scale
    with block count the way blocks do, so there's no real payoff in
    diffing inside them for display purposes either."""
    base_blocks = {b["uuid"]: b for b in base.get("blocks", [])}
    target_blocks = {b["uuid"]: b for b in target.get("blocks", [])}

    added = [target_blocks[u] for u in target_blocks if u not in base_blocks]
    removed = [base_blocks[u] for u in base_blocks if u not in target_blocks]

    changed = []
    for uuid, t in target_blocks.items():
        b = base_blocks.get(uuid)
        if b is None or b == t:
            continue
        field_changes, moved, connection_changes = _diff_block(b, t)
        if field_changes or moved or connection_changes:
            changed.append({
                "uuid": uuid,
                "short_id": t.get("short_id") or b.get("short_id"),
                "display_name": t.get("display_name"),
                "type_id": t.get("type_id"),
                "field_changes": field_changes,
                "moved": moved,
                "connection_changes": connection_changes,
            })

    return {
        "blocks_added": added,
        "blocks_removed": removed,
        "blocks_changed": changed,
        "settings_changes": _diff_settings(base.get("settings", {}), target.get("settings", {})),
    }


_SCALAR_FIELDS = ("display_name", "enabled", "color", "execution_priority")


def _diff_block(b: dict, t: dict):
    field_changes = []
    for field in _SCALAR_FIELDS:
        if b.get(field) != t.get(field):
            field_changes.append({"field": field, "old": b.get(field), "new": t.get(field)})

    b_props = b.get("properties", {})
    t_props = t.get("properties", {})
    for key in sorted(set(b_props) | set(t_props)):
        if b_props.get(key) != t_props.get(key):
            field_changes.append({"field": f"properties.{key}", "old": b_props.get(key), "new": t_props.get(key)})

    moved = b.get("position") != t.get("position")

    connection_changes = []
    b_pins = {p["uuid"]: p for key in ("inputs", "outputs") for p in b.get(key, [])}
    t_pins = {p["uuid"]: p for key in ("inputs", "outputs") for p in t.get(key, [])}
    for pin_uuid in sorted(set(b_pins) & set(t_pins)):
        b_conn = set(b_pins[pin_uuid].get("connections", []))
        t_conn = set(t_pins[pin_uuid].get("connections", []))
        if b_conn != t_conn:
            connection_changes.append({
                "pin_uuid": pin_uuid,
                "pin_name": t_pins[pin_uuid].get("name", ""),
                "added": sorted(t_conn - b_conn),
                "removed": sorted(b_conn - t_conn),
            })

    return field_changes, moved, connection_changes


def _diff_settings(base_settings: dict, target_settings: dict):
    changes = []
    for key in sorted(set(base_settings) | set(target_settings)):
        if key not in base_settings:
            changes.append({"key": key, "old": None, "new": target_settings[key]})
        elif key not in target_settings:
            changes.append({"key": key, "old": base_settings[key], "new": None})
        elif base_settings[key] != target_settings[key]:
            changes.append({"key": key, "old": base_settings[key], "new": target_settings[key]})
    return changes


def has_changes(comparison: dict) -> bool:
    return bool(
        comparison["blocks_added"] or comparison["blocks_removed"]
        or comparison["blocks_changed"] or comparison["settings_changes"]
    )


def summarize(comparison: dict) -> str:
    """One-line summary (e.g. "+2 bloki, -1 blok, 3 zmienione, 2 zmiany
    ustawień") — a quick headline for the dialog's title bar/status line
    before the engineer digs into the full detail tree."""
    parts = []
    if comparison["blocks_added"]:
        parts.append(f"+{len(comparison['blocks_added'])} blok(i)")
    if comparison["blocks_removed"]:
        parts.append(f"-{len(comparison['blocks_removed'])} blok(i)")
    if comparison["blocks_changed"]:
        parts.append(f"{len(comparison['blocks_changed'])} zmienione")
    if comparison["settings_changes"]:
        parts.append(f"{len(comparison['settings_changes'])} zmian ustawień")
    return ", ".join(parts) if parts else "Brak różnic"


def block_label(block_dict: dict) -> str:
    """"g7 — MyTag" if the block has a Tag/Comment property, else just its
    short_id/display_name — the same "short_id — extra" shape
    BlockItem._duplicate_reference_label()/SignalsPanel's own reader-menu
    labels already use elsewhere in this app, so a block referenced in a
    diff view reads exactly like it would anywhere else in the UI."""
    ident = block_dict.get("short_id") or block_dict.get("display_name", "?")
    extra = block_dict.get("properties", {}).get("Tag", "") or block_dict.get("properties", {}).get("Comment", "")
    return f"{ident} — {extra}" if extra else ident
