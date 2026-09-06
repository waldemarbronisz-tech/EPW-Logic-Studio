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
"""
import uuid as uuid_module

from logic_studio.blocks.pin import Pin

MACRO_TYPE_PREFIX = "macro."

SETTINGS_KEY = "macro_definitions"


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
    }


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
# v1 scope: a definition's OWN input_pins/output_pins (what it exposes to
# the OUTSIDE) are FIXED once created — editing a macro's internals can
# freely add/remove/rewire its INTERNAL blocks, but never changes its own
# boundary pins. This sidesteps a much harder problem (resyncing every
# OTHER placed instance of the same definition, at every nesting depth,
# the moment its exposed shape changes) that a first version doesn't need
# to solve — see ARCHITECTURE.md §24.9.

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
    `"input_pins"`/`"output_pins"`/`"name"` are left untouched (frozen by
    design, see module-level note above). Returns False (no-op) if the
    definition was deleted while it was being edited — nothing left to
    commit back into."""
    definition = get_definition(project, def_id)
    if definition is None:
        return False
    definition["blocks"] = [b.serialize() for b in blocks]
    set_definition(project, def_id, definition)
    return True


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
