"""User-defined macro blocks (feat/macro-blocks) — group a subgraph of
existing blocks into a single, named, reusable block type. Pure logic, no
Qt dependency — see ui/canvas/scene.py::create_macro_from_selection() for
the canvas-side action built on top of this.

**Definition model**: `project.settings["macro_definitions"]`, a dict
`def_id -> definition`, where `definition` is:
    {"name": str,
     "blocks": [...serialize()'d internal blocks, INTERNAL connections
                only — a connection from one internal block to another
                is kept; a connection that used to leave the original
                selection is stripped here and recorded instead as an
                entry in "input_pins"/"output_pins" below...],
     "input_pins":  [{"block_uuid", "pin_name", "data_type", "label"}, ...],
     "output_pins": [{"block_uuid", "pin_name", "data_type", "label"}, ...]}
`input_pins`/`output_pins` are ordered — index i is the macro INSTANCE's
own i-th input/output pin, and identifies exactly which internal block's
pin it stands in front of. `def_id` is a short, stable, machine-generated
id (never the display `name`, which the engineer is free to rename) —
every INSTANCE's `type_id` is `"macro.<def_id>"` (core/short_id.py-style
"letter+number" ids are for the per-project BLOCK counter, a different,
unrelated id space; see MACRO_TYPE_PREFIX below).

**Why macro instances can't be a normal BlockRegistry entry**: every other
block type is a single Python class with a FIXED pin layout, registered
once at import time (BlockRegistry.register() even instantiates a
throwaway `dummy = block_class()` — a real, enforced no-arg-constructor
requirement). A macro's pin layout is inherently PROJECT DATA (however
many inputs/outputs THIS macro's THIS definition declares) — there is no
single Python class whose fixed constructor could represent every
possible macro a project might define. `MacroInstanceBlock`
(blocks/macro_instance.py) is instead a single class whose pins are built
by a separate `configure(definition)` call, and Project.deserialize()/
ui/canvas/scene.py resolve its class directly via the "macro." type_id
prefix instead of going through BlockRegistry at all.

**Compiler integration**: expand_project() below produces a fully
FLATTENED block list — every macro instance recursively replaced by a
fresh, independently-uuid'd copy of its definition's own internal blocks,
wired directly to whatever the instance's own external connections were.
compiler/core.py's Compiler.compile() runs Validator/GraphBuilder/
Exporter against this expanded form instead of the live project, so NONE
of the existing compiler stages need to know macros exist at all — the
same reasoning that keeps ExecutionEngine/IOProvider hardware-agnostic
(ARCHITECTURE.md §1) applies here: macros are an authoring-time
convenience, never a runtime concept. EPW_RUNTIME_LOGIC accordingly never
contains a macro reference, only the blocks it expanded to.

**Instance parameters (fix/safety-and-macro-params §C)**: a definition
also carries `"parameters"` and `"parameter_bindings"` —

    "parameters": [{"name", "display_name", "type", "default", "unit",
                     "description", "enum_values"}, ...],
    "parameter_bindings": [{"parameter", "block_uuid", "property_name"}, ...]

`"name"` is a STABLE, internally-generated identifier ("PARAM_1", ...),
never shown to the engineer and never renamed — `parameter_bindings`
reference a parameter by this field so a rename never breaks a binding.
`"display_name"` is what the engineer sees and edits, and (§C1.3) is ALSO
the property key `MacroInstanceBlock` exposes for that parameter — so
renaming a parameter's display_name changes an INSTANCE's own property
key too. This is deliberately the SAME "a rename is indistinguishable
from remove-then-add" trade-off `_resync_pin_list()` above already makes
for boundary pins (see its own docstring) — accepted here for the same
reason: a dedicated, persistent identity kept separate from the
user-facing label isn't worth the schema complexity for how rarely a
parameter is renamed after instances already depend on it.

A tuple `(new_definition, new_bundle)` value — a symbol like
`"${T_ZWLOKA}"` substituted textually into a property's raw string — was
considered and REJECTED in favor of the explicit `parameter_bindings`
table above: text substitution needs its own parser, turns a typed
numeric property into a string the moment a placeholder appears in it
(breaking every existing type-inference/range-validation path a property
already has), and a value that happens to legitimately contain `{`/`}`
becomes a landmine. An explicit binding table is unambiguous, keeps every
property's own type, and is trivially listable/editable from a UI
(§C2.4) without ever touching a property's stored text.

Values live on the INSTANCE, not the definition: `MacroInstanceBlock`
gets one property per parameter (§C1.3, `sync_instance_parameters()`
below) — `expand_project()`'s substitution step (§C3) copies each
instance's OWN value onto its expanded internal blocks' properties,
AFTER those blocks are copied and BEFORE the graph is built, so the rest
of the compiler pipeline sees nothing but ordinary, already-resolved
property values — EPW_RUNTIME_LOGIC needs no changes at all (§C3.3):
after expansion there is no way to tell a property's value came from a
macro parameter rather than being typed in directly.
"""
import uuid as uuid_module

from logic_studio.blocks.pin import Pin

MACRO_TYPE_PREFIX = "macro."

SETTINGS_KEY = "macro_definitions"

# fix/safety-and-macro-params §C1.1: the closed set of value types a
# parameter can declare — independent of blocks/pin.py's own Pin.TYPE_*
# (those classify a WIRE's data type; a parameter classifies a PROPERTY
# VALUE's Python type, the same vocabulary blocks/constants.py's own
# const.int/const.real/const.time/const.string blocks already use for
# their own typed "Value" property).
PARAM_TYPES = ("INT", "REAL", "BOOL", "STRING", "ENUM")

# Every key a MacroInstanceBlock's own `properties` dict carries that is
# NOT a parameter — used by sync_instance_parameters() below to tell "a
# stale parameter's leftover property" apart from an ordinary base
# property every block has.
_INSTANCE_BASE_PROPERTY_KEYS = frozenset({"Address", "Tag", "Comment"})


def macro_def_id(type_id: str):
    """None if `type_id` doesn't name a macro instance; else the
    definition id it references (the part after "macro.")."""
    if not type_id or not type_id.startswith(MACRO_TYPE_PREFIX):
        return None
    def_id = type_id[len(MACRO_TYPE_PREFIX):]
    return def_id or None  # bare "macro." (an unconfigured/corrupt instance) has no real def_id


def new_def_id() -> str:
    return uuid_module.uuid4().hex[:8]


def get_definitions(project) -> dict:
    """A copy of the whole registry — callers must go through
    set_definition()/delete_definition() to write, the same discipline as
    every other DeviceModel-style registry in this codebase."""
    return {k: _copy_definition(v) for k, v in project.settings.get(SETTINGS_KEY, {}).items()}


def get_definition(project, def_id: str):
    raw = project.settings.get(SETTINGS_KEY, {}).get(def_id)
    return _copy_definition(raw) if raw is not None else None


def _copy_definition(definition: dict) -> dict:
    return {
        "name": definition.get("name", ""),
        "blocks": [dict(b) for b in definition.get("blocks", [])],
        "input_pins": [dict(p) for p in definition.get("input_pins", [])],
        "output_pins": [dict(p) for p in definition.get("output_pins", [])],
        # fix/safety-and-macro-params §C1: absent entirely on a definition
        # built before this feature existed — defaults to [] rather than
        # raising, which is what makes an old macro with no parameters at
        # all (§C5.6) load/compile/behave identically to before.
        "parameters": [_copy_parameter(p) for p in definition.get("parameters", [])],
        "parameter_bindings": [dict(b) for b in definition.get("parameter_bindings", [])],
    }


def _copy_parameter(param: dict) -> dict:
    copy = dict(param)
    copy["enum_values"] = list(param.get("enum_values", []))
    return copy


def set_definition(project, def_id: str, definition: dict):
    project.settings.setdefault(SETTINGS_KEY, {})[def_id] = _copy_definition(definition)


def delete_definition(project, def_id: str) -> bool:
    return project.settings.get(SETTINGS_KEY, {}).pop(def_id, None) is not None


def is_definition_in_use(project, def_id: str) -> bool:
    type_id = MACRO_TYPE_PREFIX + def_id
    return any(b.type_id == type_id for b in project.blocks)


# ---- Editing a definition's own internals directly (breadcrumb nav) --------
# feat/macro-blocks: "enter the macro like a sub-canvas" (ui/main_window.py's
# enter_macro_instance()/_exit_one_macro_level()) works by literally
# swapping WHICH block list `project.blocks` points at — the macro's own
# stored `definition["blocks"]`, instantiated as live blocks, instead of
# the top-level project's — then letting every existing scene operation
# (add/remove/wire/select/undo) run completely unchanged, since none of
# them know or care which "level" `project.blocks` currently represents.
# `project.settings` (short_id counters, macro_definitions itself, ...) is
# NEVER swapped — it stays the one shared registry throughout, which is
# exactly why a block placed while inside a macro's edit view still gets a
# globally-unique short_id, and why the "Makrobloki" library section stays
# consistent regardless of nav depth.
#
# feat/macro-editable-pins: a definition's OWN input_pins/output_pins
# (what it exposes to the OUTSIDE) CAN be changed from inside its own
# breadcrumb edit view too — add_boundary_pin()/remove_boundary_pin()
# below — with every existing placed instance, anywhere in the project
# (including nested inside OTHER macros' own stored definitions),
# resynced immediately by resync_all_instances(). See that function's
# own docstring for the resync algorithm and ARCHITECTURE.md §24.10 for
# the full design writeup.

def instantiate_definition_blocks(definition: dict) -> tuple:
    """Builds fresh LIVE `BaseLogicBlock` objects from `definition["blocks"]`
    — uuid/short_id/pins restored exactly like Project.deserialize()'s own
    block-loading loop (deliberately NOT reusing that loop directly: it
    also does file-migration bookkeeping, e.g. `short_id` counter resync,
    the one-time off-grid position rounding, `_legacy_force_state` —
    none of which apply to data this app just wrote itself moments
    earlier). Returns `(blocks, unknown_type_ids)` — `unknown_type_ids`
    should never actually be non-empty for data this app produced, but a
    hand-edited/corrupted file could still smuggle one in, so this reports
    it the same way Project.deserialize() would rather than crashing."""
    from logic_studio.blocks.registry import BlockRegistry
    from logic_studio.blocks.pin import Pin

    blocks = []
    unknown_type_ids = []
    for b_data in definition.get("blocks", []):
        type_id = b_data.get("type_id")
        block_class = BlockRegistry.get_block_class(type_id)
        if not block_class:
            unknown_type_ids.append(type_id or "?")
            continue

        block = block_class.deserialize(b_data)
        for i, pin_data in enumerate(b_data.get("inputs", [])):
            if i < len(block.inputs):
                Pin.restore_fields(block.inputs[i], pin_data)
        for i, pin_data in enumerate(b_data.get("outputs", [])):
            if i < len(block.outputs):
                Pin.restore_fields(block.outputs[i], pin_data)
        blocks.append(block)
    return blocks, unknown_type_ids


def update_definition_blocks(project, def_id: str, blocks: list) -> bool:
    """Commits `blocks` (this definition's OWN blocks, just edited directly
    via breadcrumb navigation) back into its stored definition —
    `"input_pins"`/`"output_pins"`/`"name"` are left untouched (those are
    add_boundary_pin()/remove_boundary_pin()'s job instead, committed and
    resynced immediately rather than deferred like this function). Returns
    False (no-op) if the definition was deleted while it was being edited
    — nothing left to commit back into."""
    definition = get_definition(project, def_id)
    if definition is None:
        return False
    definition["blocks"] = [b.serialize() for b in blocks]
    set_definition(project, def_id, definition)
    return True


# ---- Editable boundary pins (feat/macro-editable-pins) ---------------------
# Unlike update_definition_blocks() above (deferred until the engineer
# leaves the macro's breadcrumb view), a boundary-pin change is committed
# AND resynced onto every instance IMMEDIATELY — there's no "in-progress,
# not yet applied" state for a pin add/remove the way there is for
# internal-block edits, since every instance needs to agree on the shape
# right away for the canvas (whichever level happens to be visible next)
# to ever show something consistent.

def add_boundary_pin(project, def_id: str, direction, block_uuid: str, pin_name: str) -> bool:
    """Exposes an additional input/output pin on `def_id`'s own
    definition, anchored at one of its internal blocks' own pins
    (`block_uuid`/`pin_name`, matched against the definition's stored
    `"blocks"` — must exist, with `direction` matching that pin's own:
    an exposed INPUT anchors an internal INPUT pin, so the macro
    instance's own input can drive it from outside; ditto OUTPUT).
    Returns False (no-op) if the definition, block, or pin doesn't exist,
    or this exact (block_uuid, pin_name) is already exposed on this side
    — does NOT resync instances itself, call resync_all_instances() right
    after (kept separate so a caller building several changes at once,
    e.g. exposing many pins together, only resyncs once at the end)."""
    from logic_studio.blocks.pin import Pin

    definition = get_definition(project, def_id)
    if definition is None:
        return False
    boundary_key = "input_pins" if direction == Pin.DIR_INPUT else "output_pins"
    pin_list_key = "inputs" if direction == Pin.DIR_INPUT else "outputs"

    block_data = next((b for b in definition["blocks"] if b.get("uuid") == block_uuid), None)
    if block_data is None:
        return False
    pin_data = next((p for p in block_data.get(pin_list_key, []) if p.get("name") == pin_name), None)
    if pin_data is None:
        return False
    already_exposed = any(
        e.get("block_uuid") == block_uuid and e.get("pin_name") == pin_name
        for e in definition[boundary_key]
    )
    if already_exposed:
        return False

    definition[boundary_key].append({
        "block_uuid": block_uuid,
        "pin_name": pin_name,
        "data_type": Pin._decode_data_type(pin_data.get("data_type")),
        "label": pin_name,
    })
    set_definition(project, def_id, definition)
    return True


def remove_boundary_pin(project, def_id: str, direction, index: int) -> bool:
    """Removes the boundary pin at position `index` from `def_id`'s own
    input_pins/output_pins. Returns False (no-op) for a missing
    definition or an out-of-range index. Does NOT resync instances
    itself — same reasoning as add_boundary_pin()."""
    from logic_studio.blocks.pin import Pin

    definition = get_definition(project, def_id)
    if definition is None:
        return False
    boundary_key = "input_pins" if direction == Pin.DIR_INPUT else "output_pins"
    entries = definition[boundary_key]
    if index < 0 or index >= len(entries):
        return False
    entries.pop(index)
    set_definition(project, def_id, definition)
    return True


def _resync_pin_list(current_pins, new_boundary_entries, direction):
    """The shared matching rule behind resync_all_instances(): given an
    instance's CURRENT pins (one side only — inputs or outputs) and the
    definition's NEW boundary-pin entries for that same side, returns
    `(new_pins, removed_pins)`.

    A current pin is REUSED — same object, same uuid, same connections,
    its wiring survives completely untouched — for whichever new slot
    matches it by `(name, data_type)`; a new slot with no match gets a
    brand new, unconnected Pin. Matching by (name, data_type) rather than
    position is what keeps inserting a pin before an existing one, or
    removing one from the middle, from scrambling every survivor's own
    identity just because its index shifted.

    Every current pin NOT reused this way is a removed boundary pin,
    returned in `removed_pins` — the caller is responsible for tearing
    down whatever else in that same block list still references it by
    uuid (this function only ever sees ONE instance's own pins, never the
    rest of the level it lives in, so it can't do that part itself).

    Renaming a pin's label is indistinguishable from removing the old one
    and adding a new one under this scheme — accepted deliberately:
    add_boundary_pin()/remove_boundary_pin() offer no "rename" operation
    at all, precisely because there's no more precise way to resync a
    rename than this without a dedicated, persistent pin identity kept
    separate from its label (not worth the extra schema/model complexity
    for what a remove-then-add already covers, at the cost of that one
    pin's own wiring at every instance)."""
    remaining = list(current_pins)
    new_pins = []
    for entry in new_boundary_entries:
        label = entry.get("label", entry.get("pin_name", ""))
        data_type = entry.get("data_type", "Boolean")
        match = next((p for p in remaining if p.name == label and p.data_type == data_type), None)
        if match is not None:
            remaining.remove(match)
            new_pins.append(match)
        else:
            from logic_studio.blocks.pin import Pin
            new_pins.append(Pin(label, direction, data_type))
    return new_pins, remaining


def _resync_instance_live(instance, new_definition):
    """Rebuilds a LIVE MacroInstanceBlock's own inputs/outputs AND
    parameter-backed properties in place to match `new_definition`'s
    current shape, preserving every surviving pin's own wiring and every
    still-valid parameter's own value. Returns `(removed_pins,
    param_resets)` — `removed_pins` (both sides) is for the caller to
    scrub any OTHER pin in the same block list that still references one
    of them by uuid; `param_resets` is `sync_instance_parameters()`'s own
    return (see there) for the caller to turn into a compile-warning-
    shaped message naming this instance."""
    from logic_studio.blocks.pin import Pin

    new_inputs, removed_inputs = _resync_pin_list(instance.inputs, new_definition.get("input_pins", []), Pin.DIR_INPUT)
    new_outputs, removed_outputs = _resync_pin_list(instance.outputs, new_definition.get("output_pins", []), Pin.DIR_OUTPUT)
    instance.inputs = new_inputs
    instance.outputs = new_outputs
    instance.display_name = new_definition.get("name", instance.display_name)
    param_resets = sync_instance_parameters(instance.properties, new_definition)
    return removed_inputs + removed_outputs, param_resets


def _disconnect_removed_pins_live(block_list, removed_pins):
    removed_uuids = {p.uuid for p in removed_pins}
    if not removed_uuids:
        return
    for block in block_list:
        for pin in block.inputs + block.outputs:
            pin.connections = [c for c in pin.connections if c not in removed_uuids]


def _resync_instance_dict(b_data, new_definition, sibling_blocks_data):
    """Same rebuild as _resync_instance_live(), but for a macro instance
    that ISN'T currently live Python objects — one embedded in some OTHER
    definition's own stored `"blocks"` list (project.settings, plain
    dicts, not touched by this edit session's live nav stack at all).
    Rewrites `b_data["inputs"]`/`["outputs"]`/`["display_name"]`/
    `["properties"]` in place, and scrubs `sibling_blocks_data` (every
    OTHER block dict in that SAME definition) of any dangling reference
    to a removed pin's uuid — the dict-data equivalent of
    _disconnect_removed_pins_live(). Returns `sync_instance_parameters()`'s
    own `param_resets` — this instance has no `short_id` to report by
    (it's not live anywhere right now), so the caller identifies it some
    other way (e.g. the enclosing definition's own name)."""
    from logic_studio.blocks.pin import Pin

    def resync_side(data_key, boundary_key, direction):
        remaining = list(b_data.get(data_key, []))
        new_list = []
        for entry in new_definition.get(boundary_key, []):
            label = entry.get("label", entry.get("pin_name", ""))
            data_type = entry.get("data_type", "Boolean")
            match = next(
                (p for p in remaining
                 if p.get("name") == label and Pin._decode_data_type(p.get("data_type")) == data_type),
                None,
            )
            if match is not None:
                remaining.remove(match)
                new_list.append(match)
            else:
                new_list.append(Pin(label, direction, data_type).serialize())
        b_data[data_key] = new_list
        return remaining

    removed_inputs = resync_side("inputs", "input_pins", Pin.DIR_INPUT)
    removed_outputs = resync_side("outputs", "output_pins", Pin.DIR_OUTPUT)
    b_data["display_name"] = new_definition.get("name", b_data.get("display_name"))
    properties = b_data.setdefault("properties", {})
    param_resets = sync_instance_parameters(properties, new_definition)

    removed_uuids = {p["uuid"] for p in removed_inputs + removed_outputs}
    if removed_uuids:
        for sibling in sibling_blocks_data:
            for key in ("inputs", "outputs"):
                for pin_data in sibling.get(key, []):
                    pin_data["connections"] = [c for c in pin_data.get("connections", []) if c not in removed_uuids]
    return param_resets


def resync_all_instances(project, def_id: str, live_block_lists: list) -> list:
    """Call immediately after add_boundary_pin()/remove_boundary_pin()/a
    parameter add/remove/type-change changes `def_id`'s own shape — walks
    EVERY instance of this definition reachable anywhere in the project
    and rebuilds its pins AND parameter-backed properties to match,
    preserving each surviving pin's own wiring and each still-valid
    parameter's own value (see _resync_pin_list()'s and
    sync_instance_parameters()'s own docstrings for the matching rules).
    A no-op (returns `[]`) if the definition itself was deleted in the
    meantime.

    Returns a list of ready-to-show warning strings, one per parameter
    value an instance had reset to its default because a parameter's type
    changed underneath it (fix/safety-and-macro-params §C1.4) — shown by
    the caller RIGHT AWAY rather than deferred to the next compile like
    analog.quality's own migration notice (core/project.py): a macro
    instance is never itself a block Validator's compile-time view sees
    (expand_project() replaces it with its definition's own internal
    blocks before Validator ever runs, §C3.3), and a `simulation_state`
    notice living on it would in general be silently dropped the moment
    ANY breadcrumb level involved is next committed by
    update_definition_blocks() (serialize() never persists
    `simulation_state` — by design, see base.py's own field tuples) long
    before a compile ever happens. Surfacing the message here instead —
    at the one moment this function already knows exactly which
    instances were actually affected — is the reliable equivalent, not a
    lesser one.

    Two kinds of instance, handled differently:

    - LIVE ones — real Python objects, found by scanning
      `live_block_lists`: every block list that's CURRENTLY live Python
      objects, not just settings data. That's `project.blocks` itself
      PLUS every ancestor level's own stashed list if the caller is mid
      breadcrumb-navigation (MainWindow's own `_macro_nav_stack` entries
      — this module has no notion of a "nav stack" itself, so the caller
      assembles the list). A sibling level NOT on the current breadcrumb
      path (a different macro's own edit view, never entered this
      session) has no live objects at all — see the next case.
    - Instances embedded in some OTHER definition's own stored `"blocks"`
      (project.settings) are rewritten directly as dicts instead — they
      aren't live objects right now regardless of nav state.

    `def_id`'s OWN "blocks" are deliberately never scanned here — a
    macro can't contain a live instance of itself (compile-time cycle
    detection, core/macros.py::expand_project()) in any project this
    module itself ever produced; a hand-edited file that smuggled one in
    anyway is exactly the "cycle" `expand_project()` already catches and
    refuses to compile, not something this function needs to guard
    against on its own."""
    new_definition = get_definition(project, def_id)
    if new_definition is None:
        return []
    type_id = MACRO_TYPE_PREFIX + def_id
    notices = []

    for block_list in live_block_lists:
        for block in block_list:
            if getattr(block, "type_id", None) != type_id:
                continue
            removed, param_resets = _resync_instance_live(block, new_definition)
            _disconnect_removed_pins_live(block_list, removed)
            ref = block.short_id or block.display_name
            notices.extend(_format_param_reset_notice(ref, name, ptype) for name, ptype in param_resets)

    definitions = project.settings.get(SETTINGS_KEY, {})
    for other_def_id, other_definition in definitions.items():
        if other_def_id == def_id:
            continue
        blocks_data = other_definition.get("blocks", [])
        changed = False
        for b_data in blocks_data:
            if b_data.get("type_id") != type_id:
                continue
            param_resets = _resync_instance_dict(b_data, new_definition, blocks_data)
            changed = True
            ref = f"{b_data.get('short_id') or b_data.get('display_name', '?')} (w '{other_definition.get('name', other_def_id)}')"
            notices.extend(_format_param_reset_notice(ref, name, ptype) for name, ptype in param_resets)
        if changed:
            set_definition(project, other_def_id, other_definition)

    return notices


def _format_param_reset_notice(ref: str, display_name: str, new_type: str) -> str:
    return (
        f"[{ref}] Parametr '{display_name}' zmienił typ na {new_type} — "
        "wartość tej instancji zresetowana do domyślnej."
    )


# ---- Instance parameters (fix/safety-and-macro-params §C) ------------------
# A definition's own "parameters"/"parameter_bindings" (module docstring
# above) — CRUD here mirrors add_boundary_pin()/remove_boundary_pin()'s
# own shape (mutate the STORED definition, return bool/id, never resync
# by itself — the caller resyncs once after a batch of changes, exactly
# the same reasoning). sync_instance_parameters() below is the one
# function BOTH a fresh instance's own configure() AND a resync need, so
# "new parameter/removed parameter/type changed" behave identically
# whichever path reaches an instance.

def new_parameter_name(definition: dict) -> str:
    """A stable, never-shown-to-the-engineer identifier — "PARAM_1",
    "PARAM_2", ... — unique within `definition`. See the module docstring
    for why this is kept separate from `display_name`."""
    existing = {p.get("name") for p in definition.get("parameters", [])}
    n = 1
    while f"PARAM_{n}" in existing:
        n += 1
    return f"PARAM_{n}"


def get_parameters(project, def_id: str) -> list:
    definition = get_definition(project, def_id)
    return definition.get("parameters", []) if definition is not None else []


def get_parameter(project, def_id: str, param_name: str):
    return next((p for p in get_parameters(project, def_id) if p.get("name") == param_name), None)


def add_parameter(project, def_id: str, display_name: str, param_type: str, default, unit: str = "",
                   description: str = "", enum_values=None):
    """Appends a new parameter to `def_id`'s own definition. Returns the
    new parameter's internal `name` (see new_parameter_name()), or None
    if the definition doesn't exist. Does NOT resync instances — every
    existing instance simply picks up the new parameter (at its default)
    the next time resync_all_instances() runs, same as a newly exposed
    boundary pin."""
    definition = get_definition(project, def_id)
    if definition is None:
        return None
    name = new_parameter_name(definition)
    definition.setdefault("parameters", []).append({
        "name": name,
        "display_name": display_name,
        "type": param_type,
        "default": default,
        "unit": unit,
        "description": description,
        "enum_values": list(enum_values) if enum_values else [],
    })
    set_definition(project, def_id, definition)
    return name


def remove_parameter(project, def_id: str, param_name: str) -> bool:
    """Removes `param_name` from `def_id`'s own definition, AND every
    binding that referenced it (§C1.2 — a binding pointing at a deleted
    parameter is meaningless, never left dangling). Returns False (no-op)
    if the definition or parameter doesn't exist."""
    definition = get_definition(project, def_id)
    if definition is None:
        return False
    params = definition.get("parameters", [])
    remaining = [p for p in params if p.get("name") != param_name]
    if len(remaining) == len(params):
        return False
    definition["parameters"] = remaining
    definition["parameter_bindings"] = [
        b for b in definition.get("parameter_bindings", []) if b.get("parameter") != param_name
    ]
    set_definition(project, def_id, definition)
    return True


def update_parameter(project, def_id: str, param_name: str, **fields) -> bool:
    """In-place edit of one parameter's own fields (display_name/type/
    default/unit/description/enum_values) — `fields` are merged onto the
    existing entry, unset keys left untouched. Returns False (no-op) if
    the definition or parameter doesn't exist. A `type` change is
    detected and acted on by sync_instance_parameters() at the next
    resync (§C1.4), not here — this function only ever changes the
    DEFINITION; instances are a separate, explicit resync step."""
    definition = get_definition(project, def_id)
    if definition is None:
        return False
    param = next((p for p in definition.get("parameters", []) if p.get("name") == param_name), None)
    if param is None:
        return False
    param.update(fields)
    if "enum_values" in fields:
        param["enum_values"] = list(fields["enum_values"])
    set_definition(project, def_id, definition)
    return True


def reorder_parameters(project, def_id: str, new_order: list) -> bool:
    """Reorders `def_id`'s own parameters to match `new_order` (a list of
    parameter `name`s — every existing name must appear exactly once).
    Purely a display-order convenience (§C2.4's "zmiana kolejności") —
    parameter identity/bindings are entirely name-based and unaffected."""
    definition = get_definition(project, def_id)
    if definition is None:
        return False
    by_name = {p.get("name"): p for p in definition.get("parameters", [])}
    if set(new_order) != set(by_name):
        return False
    definition["parameters"] = [by_name[name] for name in new_order]
    set_definition(project, def_id, definition)
    return True


def get_parameter_bindings(project, def_id: str, param_name: str = None) -> list:
    """Every binding on `def_id`'s own definition, or (with `param_name`)
    only the ones for that one parameter."""
    definition = get_definition(project, def_id)
    if definition is None:
        return []
    bindings = definition.get("parameter_bindings", [])
    if param_name is None:
        return bindings
    return [b for b in bindings if b.get("parameter") == param_name]


def add_parameter_binding(project, def_id: str, param_name: str, block_uuid: str, property_name: str) -> bool:
    """Binds `param_name` to `block_uuid`'s own `property_name` — looked
    up against the definition's STORED "blocks" data, same convention as
    add_boundary_pin(). Returns False if the definition, parameter, or
    (block, property) doesn't exist, or this exact binding already
    exists. Does NOT reject a property already bound to a DIFFERENT
    parameter — compiler/validator.py's own §C4 rule ("dwa parametry
    powiązane z tą samą właściwością") is a WARNING, not something this
    data layer refuses outright."""
    definition = get_definition(project, def_id)
    if definition is None:
        return False
    if not any(p.get("name") == param_name for p in definition.get("parameters", [])):
        return False
    block_data = next((b for b in definition["blocks"] if b.get("uuid") == block_uuid), None)
    if block_data is None or property_name not in block_data.get("properties", {}):
        return False
    bindings = definition.setdefault("parameter_bindings", [])
    if any(b.get("parameter") == param_name and b.get("block_uuid") == block_uuid and b.get("property_name") == property_name for b in bindings):
        return False
    bindings.append({"parameter": param_name, "block_uuid": block_uuid, "property_name": property_name})
    set_definition(project, def_id, definition)
    return True


def remove_parameter_binding(project, def_id: str, block_uuid: str, property_name: str) -> bool:
    """Un-binds whichever parameter (if any) is currently bound to
    `block_uuid`'s own `property_name` — the "Odłącz od parametru" action
    (§C2.3). Returns False if no such binding exists."""
    definition = get_definition(project, def_id)
    if definition is None:
        return False
    bindings = definition.get("parameter_bindings", [])
    remaining = [b for b in bindings if not (b.get("block_uuid") == block_uuid and b.get("property_name") == property_name)]
    if len(remaining) == len(bindings):
        return False
    definition["parameter_bindings"] = remaining
    set_definition(project, def_id, definition)
    return True


def binding_for_property(definition: dict, block_uuid: str, property_name: str):
    """The parameter `name` currently bound to `block_uuid`'s own
    `property_name` in `definition`, or None — property_grid.py's own
    "is this property bound?" check (§C2.3)."""
    for b in definition.get("parameter_bindings", []):
        if b.get("block_uuid") == block_uuid and b.get("property_name") == property_name:
            return b.get("parameter")
    return None


def value_matches_param_type(value, param_type: str) -> bool:
    """Whether `value`'s own Python type is what `param_type` (one of
    PARAM_TYPES) expects — the same closed set of checks
    update_property()'s (blocks/base.py) own isinstance dispatch already
    uses for a plain property, applied here to an instance's
    parameter-backed one."""
    if param_type == "BOOL":
        return isinstance(value, bool)
    if param_type == "INT":
        return isinstance(value, int) and not isinstance(value, bool)
    if param_type == "REAL":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if param_type in ("STRING", "ENUM"):
        return isinstance(value, str)
    return True  # an unrecognized param_type (corrupted file) never blocks a resync


def sync_instance_parameters(properties: dict, definition: dict) -> list:
    """Mutates `properties` (a MacroInstanceBlock's own `.properties`
    dict, OR a serialized instance's `b_data["properties"]` dict — either
    way, a plain `{key: value}` mapping) IN PLACE so it carries exactly
    one entry per CURRENT parameter of `definition`, keyed by that
    parameter's `display_name` (§C1.3):

    - a parameter with no existing entry (new, or an instance created
      before it existed) gets its `default`;
    - a parameter WITH an existing, type-compatible entry keeps that
      value untouched — this is what makes two instances of the same
      macro independently keep their own nastawy across a resync
      triggered by an UNRELATED definition edit (§C5.1's whole point);
    - a parameter whose existing entry's value no longer matches its
      (possibly just-changed) `type` is reset to `default` (§C1.4);
    - any OTHER key in `properties` that isn't a base property
      (Address/Tag/Comment) and doesn't name a CURRENT parameter is
      removed outright — a deleted parameter's leftover value, or a
      rename's old key (module docstring: renaming is remove-then-add).

    Returns a list of `(display_name, new_type)` pairs for every value
    that got reset due to a type mismatch — resync_all_instances() turns
    these into ready-to-show warning strings."""
    params = definition.get("parameters", [])
    valid_display_names = {p.get("display_name") for p in params}

    for key in list(properties.keys()):
        if key not in _INSTANCE_BASE_PROPERTY_KEYS and key not in valid_display_names:
            del properties[key]

    resets = []
    for param in params:
        display_name = param.get("display_name")
        param_type = param.get("type", "STRING")
        if display_name not in properties:
            properties[display_name] = param.get("default")
        elif not value_matches_param_type(properties[display_name], param_type):
            properties[display_name] = param.get("default")
            resets.append((display_name, param_type))
    return resets


# ---- Building a definition from a live selection ---------------------------

def build_definition(name: str, blocks: list) -> tuple:
    """`blocks` are live BaseLogicBlock instances forming the selection to
    extract — still attached to their project/scene; this function never
    mutates them or the project, it only computes data. Returns
    `(definition, crossings)`:

    - `definition`: the dict shape documented at module level, ready for
      set_definition().
    - `crossings`: one entry per pin that had a connection LEAVING the
      selection — `{"direction", "instance_pin_index", "external_pin_uuid"}`
      — ui/canvas/scene.py uses this to wire a freshly-created instance
      block's own boundary pin at that index to the recorded external pin,
      once the instance actually exists and the extracted blocks have been
      removed.

    A connection between two blocks BOTH inside the selection is an
    internal connection (kept in `definition["blocks"]` verbatim, never a
    crossing). An INPUT pin can have at most one external connection (the
    single-driver rule, Pin.connect()); an OUTPUT pin can fan out to
    several external readers — that becomes ONE exposed output pin with
    several crossings all pointing at the same `instance_pin_index`, never
    several separate output pins for what is, internally, one signal.

    Deliberately re-derives the same "keep only connections landing inside
    the selection" filtering ui/canvas/scene.py's own
    copy_selected_items() already does, rather than importing it — this
    module must stay Qt-free, and copy_selected_items() lives in a
    Qt-owning one.
    """
    selected_pin_uuids = {p.uuid for b in blocks for p in (b.inputs + b.outputs)}

    serialized = []
    input_pins = []
    output_pins = []
    crossings = []

    for block in blocks:
        data = block.serialize()
        for key, pins in (("inputs", block.inputs), ("outputs", block.outputs)):
            for pin_data, pin in zip(data[key], pins):
                internal_conns = [c for c in pin.connections if c in selected_pin_uuids]
                external_conns = [c for c in pin.connections if c not in selected_pin_uuids]
                pin_data["connections"] = internal_conns
                if not external_conns:
                    continue
                exposed = {
                    "block_uuid": block.uuid, "pin_name": pin.name,
                    "data_type": pin.data_type, "label": pin.name,
                }
                if pin.direction == Pin.DIR_INPUT:
                    input_pins.append(exposed)
                    idx = len(input_pins) - 1
                    for external_uuid in external_conns:
                        crossings.append({"direction": "input", "instance_pin_index": idx, "external_pin_uuid": external_uuid})
                else:
                    output_pins.append(exposed)
                    idx = len(output_pins) - 1
                    for external_uuid in external_conns:
                        crossings.append({"direction": "output", "instance_pin_index": idx, "external_pin_uuid": external_uuid})
        serialized.append(data)

    definition = {
        "name": name,
        "blocks": serialized,
        "input_pins": input_pins,
        "output_pins": output_pins,
        "parameters": [],
        "parameter_bindings": [],
    }
    return definition, crossings


# ---- Compile-time expansion --------------------------------------------

def expand_project(project) -> tuple:
    """Returns `(expanded_blocks, errors)`. `expanded_blocks` is
    `project.blocks` with every macro instance recursively replaced by
    fresh, independently-uuid'd copies of its definition's own internal
    blocks, wired directly to whatever the instance's own external
    connections were — the macro instance block itself never appears in
    the result. `errors` is non-empty (and `expanded_blocks` always `[]`
    in that case) on a cycle (a macro directly or indirectly containing an
    instance of itself) or a reference to a missing/deleted definition —
    Compiler.compile() surfaces these exactly like a Validator error,
    aborting compilation before Validator/GraphBuilder/Exporter ever run.
    """
    macro_defs = project.settings.get(SETTINGS_KEY, {})
    errors = []
    rewire_plan = []  # [(external_pin_uuid, old_boundary_pin_uuid, new_internal_pin_uuid), ...]
    expanded = _expand_blocks(project.blocks, macro_defs, frozenset(), errors, rewire_plan)
    if errors:
        return [], errors

    pin_map = {}
    for block in expanded:
        for pin in block.inputs + block.outputs:
            pin_map[pin.uuid] = pin

    for external_uuid, old_uuid, new_uuid in rewire_plan:
        external_pin = pin_map.get(external_uuid)
        new_pin = pin_map.get(new_uuid)
        if external_pin is None or new_pin is None:
            # AUDIT_REPORT.md §32: this is NOT the harmless "block already
            # removed" case the old comment here assumed — external_pin
            # missing would mean the LIVE project referenced a pin that
            # never existed (can't happen; `blocks` came from this same
            # project). new_pin missing means a macro's own exposed
            # boundary pin was anchored directly on a NESTED macro
            # instance's own pin, never on one of ITS internal blocks —
            # the one shape _expand_instance() can't resolve (its own
            # docstring explains why: that instance is itself replaced/
            # discarded during expansion, so its pin never survives into
            # the final flattened graph for this to point at). Silently
            # dropping the connection here used to compile "successfully"
            # while quietly producing a signal that does nothing — on an
            # industrial-automation platform that's a hazard, not a
            # cosmetic gap, so this is now a hard compile error instead.
            errors.append(
                "Nie można rozwiązać połączenia makrobloku: wystawiony pin "
                "wskazuje bezpośrednio na pin zagnieżdżonej instancji innego "
                "makrobloku zamiast na zwykły blok wewnętrzny. Dodaj blok "
                "pośredniczący (np. bufor) między nimi i spróbuj ponownie."
            )
            continue
        if old_uuid in external_pin.connections:
            external_pin.connections.remove(old_uuid)
        if new_uuid not in external_pin.connections:
            external_pin.connections.append(new_uuid)
        if external_uuid not in new_pin.connections:
            new_pin.connections.append(external_uuid)

    if errors:
        return [], errors
    return expanded, []


def _expand_blocks(blocks, macro_defs, expanding, errors, rewire_plan):
    from logic_studio.blocks.registry import BlockRegistry

    result = []
    for block in blocks:
        def_id = macro_def_id(block.type_id)
        if def_id is None:
            # clone() deliberately blanks short_id (base.py: a pasted/
            # duplicated block must never collide with its source's id).
            # That reasoning doesn't apply here — this clone isn't a new
            # block being added to the project, it's this SAME block's
            # isolated stand-in for compilation, and compiler messages
            # (Validator warnings, _compute_cycle_delayed_reads' "Odczyt w
            # bloku <tag>") must still name it by the id the engineer
            # actually sees on the canvas.
            fresh = block.clone(preserve_uuid=True)
            fresh.short_id = block.short_id
            result.append(fresh)
            continue
        if def_id in expanding:
            errors.append(
                f"Makroblok '{def_id}' pośrednio zawiera sam siebie (cykl) — kompilacja przerwana."
            )
            continue
        macro_def = macro_defs.get(def_id)
        if macro_def is None:
            ref = block.short_id or block.display_name
            errors.append(f"[{ref}] Odwołuje się do nieistniejącej definicji makrobloku '{def_id}'.")
            continue
        result.extend(_expand_instance(block, def_id, macro_def, macro_defs, expanding, errors, rewire_plan))
        if errors:
            return []
    return result


def _expand_instance(instance_block, def_id, macro_def, macro_defs, expanding, errors, rewire_plan):
    from logic_studio.blocks.registry import BlockRegistry

    pin_uuid_map = {}       # old internal pin uuid (in the definition) -> new (fresh) internal pin uuid
    block_by_old_uuid = {}  # old internal block uuid (in the definition) -> fresh block object
    fresh_blocks = []
    for b_data in macro_def.get("blocks", []):
        block_class = BlockRegistry.get_block_class(b_data.get("type_id"))
        if block_class is None:
            errors.append(
                f"Definicja makrobloku '{macro_def.get('name', def_id)}' odwołuje się do "
                f"nieznanego typu bloku '{b_data.get('type_id')}'."
            )
            return []
        fresh = block_class.deserialize(b_data)
        fresh.uuid = str(uuid_module.uuid4())
        fresh.short_id = ""
        # Every pin gets an explicitly fresh uuid here, regardless of
        # whatever block_class.deserialize() happened to leave it with.
        # For an ordinary block that's already true incidentally (its
        # deserialize() never restores pin uuids from `b_data`, so the
        # ones from its own constructor are already fresh) — but
        # MacroInstanceBlock's own deserialize() override deliberately
        # DOES restore pin uuids verbatim from `b_data` (correct for a
        # genuine load-from-disk). Left alone, a macro definition that
        # itself contains a nested macro instance would, on its second+
        # placed instance, replay the exact same nested-instance pin
        # uuids every time (b_data is the one shared definition dict),
        # colliding across independent instances of the outer macro.
        # Assigning fresh uuids unconditionally here — not relying on
        # incidental constructor behavior — closes that regardless of
        # which block type's deserialize() is involved.
        for i, pin_data in enumerate(b_data.get("inputs", [])):
            if i < len(fresh.inputs):
                fresh.inputs[i].uuid = str(uuid_module.uuid4())
                pin_uuid_map[pin_data["uuid"]] = fresh.inputs[i].uuid
                fresh.inputs[i].connections = list(pin_data.get("connections", []))
        for i, pin_data in enumerate(b_data.get("outputs", [])):
            if i < len(fresh.outputs):
                fresh.outputs[i].uuid = str(uuid_module.uuid4())
                pin_uuid_map[pin_data["uuid"]] = fresh.outputs[i].uuid
                fresh.outputs[i].connections = list(pin_data.get("connections", []))
        block_by_old_uuid[b_data.get("uuid")] = fresh
        fresh_blocks.append(fresh)

    # Remap internal connections onto the fresh pin uuids — same two-pass
    # pattern as ui/canvas/scene.py's paste_clipboard().
    for block in fresh_blocks:
        for pin in block.inputs + block.outputs:
            pin.connections = [pin_uuid_map.get(c, c) for c in pin.connections]

    # fix/safety-and-macro-params §C3.1: substitute THIS instance's own
    # parameter values onto the fresh internal blocks' properties — AFTER
    # they're copied (so there's something to overwrite) and BEFORE the
    # recursive _expand_blocks() call below (§C3.2: outside-in — if one of
    # these fresh blocks is itself a NESTED macro instance, its own
    # properties (parameter values included) must already carry whatever
    # THIS instance just substituted into them before that nested
    # instance's OWN bindings get their turn, when the recursive call
    # expands it in turn). A binding referencing a deleted parameter or
    # block is silently skipped here — compiler/validator.py's own §C4
    # rule is what reports that as a compile ERROR; this function only
    # ever produces a flattened graph, it never itself decides what's
    # valid.
    param_by_name = {p.get("name"): p for p in macro_def.get("parameters", [])}
    for binding in macro_def.get("parameter_bindings", []):
        param = param_by_name.get(binding.get("parameter"))
        target = block_by_old_uuid.get(binding.get("block_uuid"))
        if param is None or target is None:
            continue
        display_name = param.get("display_name")
        property_name = binding.get("property_name")
        if display_name in instance_block.properties and property_name in target.properties:
            # Direct dict write, not update_property() — that method
            # expects a STRING to parse (property_grid.py's own editors
            # always hand it text), while a parameter's stored value is
            # already correctly typed (sync_instance_parameters() is what
            # enforces that). KNOWN NARROW GAP: a block whose OWN
            # update_property() override reacts to THIS SPECIFIC property
            # with a side effect beyond storing it (e.g. system.signal's
            # "Sygnał" re-deriving its output pin type) does not get that
            # side effect re-run here — not exercised by any binding this
            # feature's own tests create (a numeric timer/counter preset,
            # the flagship use case), and no such block is a sensible
            # macro-parameter target in the first place (its OWN pin type
            # would need to already match before the macro was ever
            # built, since expand_project() runs once per compile with no
            # further chance to react to a pin-type change mid-expansion).
            target.properties[property_name] = instance_block.properties[display_name]

    # Note the boundary pins BEFORE recursively expanding — for a nested
    # macro instance that ALSO happens to sit at this definition's own
    # boundary, its pins wouldn't survive with the same uuid past
    # expansion. UNSUPPORTED (a definition's own exposed pin must
    # reference a plain, non-macro internal block) — AUDIT_REPORT.md §32:
    # this WAS assumed unreachable from the normal "create macro from
    # selection" UI (a nested macro's own internal pins aren't
    # individually selectable from the outer canvas), but selecting an
    # ALREADY-PLACED macro instance alongside other blocks and building a
    # bigger macro from THAT selection reaches it just fine — the nested
    # instance's own boundary pin is a completely ordinary, selectable
    # pin from the outside. expand_project()'s final rewire pass below
    # now reports this as a hard compile error (never silently drops the
    # connection) when it can't resolve one of these.
    boundary_pins = []  # (direction, instance_pin_index, internal_pin)
    for i, boundary in enumerate(macro_def.get("input_pins", [])):
        internal_block = block_by_old_uuid.get(boundary["block_uuid"])
        internal_pin = _find_pin(internal_block, boundary["pin_name"], want_input=True) if internal_block else None
        if internal_pin is not None:
            boundary_pins.append(("input", i, internal_pin))
    for j, boundary in enumerate(macro_def.get("output_pins", [])):
        internal_block = block_by_old_uuid.get(boundary["block_uuid"])
        internal_pin = _find_pin(internal_block, boundary["pin_name"], want_input=False) if internal_block else None
        if internal_pin is not None:
            boundary_pins.append(("output", j, internal_pin))

    fresh_blocks = _expand_blocks(fresh_blocks, macro_defs, expanding | {def_id}, errors, rewire_plan)
    if errors:
        return []

    for direction, index, internal_pin in boundary_pins:
        instance_pin = (instance_block.inputs if direction == "input" else instance_block.outputs)[index] \
            if index < len(instance_block.inputs if direction == "input" else instance_block.outputs) else None
        if instance_pin is None:
            continue
        for external_uuid in instance_pin.connections:
            rewire_plan.append((external_uuid, instance_pin.uuid, internal_pin.uuid))

    return fresh_blocks


def _find_pin(block, pin_name: str, want_input: bool):
    for pin in (block.inputs if want_input else block.outputs):
        if pin.name == pin_name:
            return pin
    return None
