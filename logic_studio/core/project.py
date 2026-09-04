import copy
import json
import re

from logic_studio.core.grid import GRID_SIZE
from logic_studio.core import state_diff


class _HistoryEntry:
    """One undo/redo stack slot. Exactly one of `full`/`diff` is set at
    any time — see Project._stack_push()/_stack_pop() for the invariant
    (topmost entry in a stack is always `full`; every entry below it is
    a `diff` relative to its immediate neighbor above)."""
    __slots__ = ("full", "diff")

    def __init__(self, full: dict = None, diff: dict = None):
        self.full = full
        self.diff = diff

# Bump when the on-disk .epwlogic schema changes in a way that requires migration.
# Every bump needs a matching _migrate_vN_to_v(N+1)(data) function registered in
# _MIGRATIONS below — see AUDIT_REPORT.md §2 "Wersjonowanie schematów".
EPWLOGIC_SCHEMA_VERSION = 5


def _migrate_v1_to_v2(data: dict) -> dict:
    """v1 -> v2 (see AUDIT_REPORT.md §2.1):
    - settings.analog_points introduced. Default to [] when absent — v1
      projects simply had none.
    - "Force State" was, for a time, incorrectly persisted as a per-block
      property (a runtime-only override that must never be saved — see the
      previous PR's AUDIT_REPORT.md §5.1). It is stripped out of properties
      here. An ACTIVE force (not "NO FORCE"/empty) is carried forward via a
      transient "_legacy_force_state" key on the block's own dict; that key
      is consumed exactly once, right after Project.deserialize() constructs
      that block, and folded into its simulation_state (never re-serialized).
      This keeps every v1 back-compat decision in this one function instead
      of split across deserialize() and a separate helper.
    """
    settings = data.setdefault("settings", {})
    settings.setdefault("analog_points", [])

    for b_data in data.get("blocks", []):
        properties = b_data.get("properties")
        if isinstance(properties, dict) and "Force State" in properties:
            value = properties.pop("Force State")
            if value and value != "NO FORCE":
                b_data["_legacy_force_state"] = value

    data["schema_version"] = 2
    return data


_VIRTUAL_IO_TYPE_IDS = ("virtual.input", "virtual.output")

# Same forbidden-character set as internal_bits.validate_internal_bit_name()
# — duplicated as a raw pattern (not imported) to keep this migration usable
# even if that module's validation rule ever changes shape; migrating old
# data should stay stable independent of the CURRENT validation rule.
_MIGRATION_FORBIDDEN_CHARS = re.compile(r'[\s/\\\'"ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]')


def _migrate_v2_to_v3(data: dict) -> dict:
    """v2 -> v3 (feat/internal-bits §8.2):
    - settings.internal_bits introduced. Default to [] when absent.
    - virtual.input/virtual.output blocks used a free-text "Tag" property
      as their signal name — no registry, no uniqueness check, a typo
      silently created a new signal instead of erroring (feat/internal-bits
      §PROBLEM). For every such block with a non-empty Tag, this creates
      (or reuses) a BOOL, non-retentive settings.internal_bits entry named
      after that Tag, and rewrites the block's property from "Tag" to
      "Bit" pointing at it. Two blocks with the same Tag (case-
      insensitively) merge into ONE registry entry, exactly as
      §2.1 requires — this never changes which blocks are logically wired
      to which signal, only how that signal is named/validated going
      forward. A Tag containing characters the new registry doesn't allow
      (spaces, quotes, ...) is sanitized (replaced with "_") rather than
      left to fail validation on the very first load.
    """
    settings = data.setdefault("settings", {})
    internal_bits = settings.setdefault("internal_bits", [])
    by_lower_name = {e["name"].lower(): e for e in internal_bits}

    for b_data in data.get("blocks", []):
        if b_data.get("type_id") not in _VIRTUAL_IO_TYPE_IDS:
            continue
        properties = b_data.get("properties")
        if not isinstance(properties, dict):
            continue
        tag = properties.pop("Tag", None)
        if not tag:
            properties.setdefault("Bit", "")
            continue

        name = _MIGRATION_FORBIDDEN_CHARS.sub("_", tag)
        existing = by_lower_name.get(name.lower())
        if existing is None:
            entry = {
                "name": name, "type": "BOOL", "retentive": False,
                "description": "", "label": "", "category": "",
            }
            internal_bits.append(entry)
            by_lower_name[name.lower()] = entry

        properties["Bit"] = name

    # system.signal used "Tag" to name a system signal too (overloading the
    # SAME property key the generic Tag/Comment feature uses for an
    # unrelated purpose — see PROBLEM in the audit) — carry that value
    # forward as "Sygnał" (§3.4) rather than dropping it. Unlike virtual.*
    # above, this does NOT create a registry entry — the system-signal
    # catalog is a fixed platform contract, not project-defined — and the
    # old value is NOT sanitized/validated here: if it doesn't match a
    # current catalog id (e.g. the old default "SYS_READY" vs the
    # catalog's "SYS.READY"), that's exactly the "sygnał spoza katalogu"
    # case §4.4/§3.4's migration note says the validator must flag live,
    # not something this migration should silently paper over.
    for b_data in data.get("blocks", []):
        if b_data.get("type_id") != "system.signal":
            continue
        properties = b_data.get("properties")
        if not isinstance(properties, dict):
            continue
        tag = properties.pop("Tag", None)
        properties["Sygnał"] = tag or properties.get("Sygnał", "")

    data["schema_version"] = 3
    return data


def _migrate_v3_to_v4(data: dict) -> dict:
    """v3 -> v4 (feat/io-labels-and-ids §1.3):
    - settings.io_labels introduced (address -> descriptive label, e.g.
      "ELA01.DI01" -> "Wyłącznik Q1 zamknięty" — see core/device_model.py's
      get_io_label()/set_io_label()). Default to {} when absent — no v3
      project could have had any entries, since the feature didn't exist.
    This step is otherwise a no-op (nothing to migrate FROM), but it still
    needs to exist and bump schema_version, so a v3 file's version number
    accurately reflects what the CURRENT format supports — see §1.3's own
    reasoning: an empty migration is not a skipped one.
    """
    settings = data.setdefault("settings", {})
    settings.setdefault("io_labels", {})
    data["schema_version"] = 4
    return data


def _migrate_v4_to_v5(data: dict) -> dict:
    """v4 -> v5 (feat/multi-device-io):
    - settings.ela_devices/ada_devices introduced — the project-defined
      list of ELA/ADA module names (core/device_model.py's
      ELA_DEVICES/ADA_DEVICES class constants, previously fixed at
      ["ELA01"]/["ADA01"] for every project). Defaults to exactly that
      single-device list when absent, so every pre-v5 file — which could
      only ever have addressed "ELA01.DI01".."ELA01.DI32"/"ADA01.DO01"..
      "ADA01.DO32" in the first place — keeps validating and compiling
      identically after this migration; nothing is actually being
      migrated FROM, same "an empty migration is not a skipped one"
      reasoning as v3->v4.
    """
    settings = data.setdefault("settings", {})
    settings.setdefault("ela_devices", ["ELA01"])
    settings.setdefault("ada_devices", ["ADA01"])
    data["schema_version"] = 5
    return data


# Keyed by the version a migration upgrades FROM. Project.deserialize() walks
# this sequentially — apply the migration for the file's current version,
# re-check, repeat — so a v1 file goes through v1->v2->v3->v4->v5 in one load.
_MIGRATIONS = {
    1: _migrate_v1_to_v2,
    2: _migrate_v2_to_v3,
    3: _migrate_v3_to_v4,
    4: _migrate_v4_to_v5,
}


class Project:
    """Manages the full state of the Logic Studio engineering project."""

    def __init__(self):
        self.blocks = []
        self.settings = {
            "name": "New Project",
            "version": "1.0",
            "cycle_time_ms": 100,
            # Analog points are fully project-defined (unlike DI/DO, which are
            # fixed physical ELA/ADA channels) — see DeviceModel and
            # AUDIT_REPORT.md §1. Each entry:
            # {"address": str, "name": str, "unit": str, "min": float,
            #  "max": float, "direction": "input" | "output"}
            "analog_points": [],
            # Internal signal registry (feat/internal-bits §1) — project-
            # defined BOOL/REAL signals virtual.input/output and
            # internal.reg_in/out reference by name. See
            # core/internal_bits.py for the entry shape and
            # internal_bit_id() (the derived M./MR./MW./MWR.<name> id).
            "internal_bits": [],
            # Descriptive labels for I/O addresses (feat/io-labels-and-ids
            # §1) — address -> label, e.g. "ELA01.DI01" -> "Wyłącznik Q1
            # zamknięty". Always read/written through DeviceModel.
            # get_io_label()/set_io_label() (§1.4), never this dict
            # directly. A short_id_counters entry (core/short_id.py, §4)
            # is added here lazily by the first block ever added to the
            # project — not seeded here, since an empty project needs none.
            "io_labels": {},
            # feat/multi-device-io: the ELA/ADA modules THIS project
            # addresses — a new project starts with the same single-device
            # default every project always had (DeviceModel.ELA_CHANNELS/
            # ADA_CHANNELS fixed channels-per-device stays a platform
            # constant, not project-defined — only the DEVICE COUNT is).
            # Always read/written through DeviceModel.get_ela_devices()/
            # get_ada_devices(), never this list directly.
            "ela_devices": ["ELA01"],
            "ada_devices": ["ADA01"],
        }

        self.undo_stack = []
        self.redo_stack = []
        self.is_recording = False

    # ---- feat/undo-diff-storage: each stack's memory is proportional to
    # the SIZE OF EACH EDIT, not to the size of the whole project — see
    # AUDIT_REPORT.md §25 / §9.1 for the measured problem this replaces
    # (a full JSON snapshot per entry, growing linearly with block count).
    # Invariant maintained by _stack_push()/_stack_pop() on BOTH
    # undo_stack and redo_stack: the topmost (most recently pushed) entry
    # is always a FULL dict; every entry below it is a diff
    # (core/state_diff.py) relative to its immediate neighbor above —
    # i.e. "what to change on the entry one step newer to get this one".
    # Since undo()/redo() only ever push/pop from the TOP of a stack,
    # reconstructing the entry that becomes newly exposed on pop needs
    # exactly one diff-apply against the value just popped — never a walk
    # back through the whole stack.

    def _stack_push(self, stack: list, state: dict):
        """Push `state` (a full serialize()-shaped dict) onto `stack`,
        converting the previous top (if any) from a full dict into a
        diff first. `state` is deep-copied once here — the single
        isolation point that keeps every stored history entry
        independent of the live project's own mutable dicts/lists
        (BaseLogicBlock.serialize()'s "properties" and Project.settings'
        nested values are returned BY REFERENCE, not copied — without
        this, a later in-place edit, e.g. DeviceModel.set_io_label(),
        would silently rewrite already-pushed history through the
        shared reference)."""
        state = copy.deepcopy(state)
        if stack:
            old_top = stack[-1]
            stack[-1] = _HistoryEntry(diff=state_diff.diff_project_state(base=state, target=old_top.full))
        stack.append(_HistoryEntry(full=state))

    def _stack_pop(self, stack: list) -> dict:
        """Pop and return the topmost full state, re-materializing the
        entry now exposed on top (previously stored as a diff relative
        to the entry just popped) back into a full dict so the "top is
        always full" invariant holds for the next push/pop."""
        popped = stack.pop()
        if stack:
            new_top = stack[-1]
            stack[-1] = _HistoryEntry(full=state_diff.apply_project_diff(base=popped.full, diff=new_top.diff))
        return popped.full

    def push_state(self, state: dict = None):
        """Take a snapshot of the current project state for undo. Pass an
        already-serialized `state` (feat/clipboard-and-align §3.1/§3.2) to
        push a state captured BEFORE a since-applied live mutation instead
        of the project's current (already-mutated) one — needed by
        scene.py's block-drag and click-to-wire handling, both of which
        apply their change live (via BlockItem.itemChange() / Pin.connect())
        during the mouse gesture, before mouseReleaseEvent gets a chance to
        call this; pushing self.serialize() at that point would push the
        POST-change state, making undo() a no-op. Every other call site
        keeps calling this with no argument, exactly as before."""
        if self.is_recording:
            return
        if state is None:
            state = self.serialize()
        self._stack_push(self.undo_stack, state)
        # Keep stack size manageable — dropping the oldest entry never
        # needs to materialize it first (see _stack_push's docstring):
        # nothing else in the chain depends on the entry being discarded.
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self):
        if not self.undo_stack:
            return None
        self._stack_push(self.redo_stack, self.serialize())
        return self._stack_pop(self.undo_stack)

    def redo(self):
        if not self.redo_stack:
            return None
        self._stack_push(self.undo_stack, self.serialize())
        return self._stack_pop(self.redo_stack)

    def add_block(self, block):
        if block not in self.blocks:
            # feat/io-labels-and-ids §4.1/§4.2: assign a short_id the FIRST
            # time a block joins a project — the single choke point every
            # block passes through (library placement, paste/duplicate, and
            # the project loader below, which calls this once per block in
            # FILE ORDER — that's what makes loading an older project
            # without short_id assign ids deterministically in file order
            # with no separate migration pass). A block that already has
            # one (restored from a save file via BaseLogicBlock.
            # SERIALIZED_FIELDS) is left untouched.
            if not getattr(block, 'short_id', None):
                from logic_studio.core import short_id as short_id_module
                short_id_module.assign_short_id(self, block)
            self.blocks.append(block)

    def remove_block(self, block):
        if block in self.blocks:
            self.blocks.remove(block)

    def serialize(self) -> dict:
        """Serialize full project for saving to .epwlogic file."""
        return {
            "format": "EPW_LOGIC",
            "schema_version": EPWLOGIC_SCHEMA_VERSION,
            "settings": self.settings,
            "blocks": [b.serialize() for b in self.blocks]
        }

    def save_to_file(self, filepath: str):
        with open(filepath, 'w') as f:
            json.dump(self.serialize(), f, indent=4)

    @classmethod
    def load_from_file(cls, filepath: str):
        with open(filepath, 'r') as f:
            data = json.load(f)
        return cls.deserialize(data)

    @classmethod
    def deserialize(cls, data: dict):
        """Loads project from JSON.

        Raises ValueError if the format/schema is unrecognized, or if the file
        references block type_ids this build does not know how to construct —
        silently dropping blocks from a safety-logic project is not acceptable,
        so a missing block type must fail loudly instead of losing logic quietly.
        """
        from logic_studio.blocks.registry import BlockRegistry

        # Schema validation
        fmt = data.get("format")
        if fmt and fmt != "EPW_LOGIC":
            raise ValueError(f"Unsupported format: {fmt}")

        schema_version = data.get("schema_version", 0)
        if schema_version > EPWLOGIC_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported schema version: {schema_version}. This build of "
                f"EPW Logic Studio understands up to schema_version "
                f"{EPWLOGIC_SCHEMA_VERSION}; open this file with a newer version "
                f"of the application."
            )

        # Migrate forward sequentially: v1 -> v2 -> ... so a file from any
        # older, still-recognized version reaches EPWLOGIC_SCHEMA_VERSION
        # in-place before anything else looks at `data`.
        while schema_version in _MIGRATIONS:
            data = _MIGRATIONS[schema_version](data)
            schema_version = data["schema_version"]

        proj = cls()
        proj.settings = data.get("settings", proj.settings)
        # Defensive default even post-migration (e.g. a schema_version of 0 /
        # missing entirely skips the migration chain above, same leniency as
        # before schema versioning existed).
        proj.settings.setdefault("analog_points", [])
        proj.settings.setdefault("internal_bits", [])
        proj.settings.setdefault("io_labels", {})
        proj.settings.setdefault("ela_devices", ["ELA01"])
        proj.settings.setdefault("ada_devices", ["ADA01"])

        block_data_list = data.get("blocks", [])

        # feat/io-labels-and-ids §4.2: fast-forward the short_id counters
        # (core/short_id.py) past every short_id already present in the
        # FILE ITSELF before any block is constructed/added — so if some
        # blocks in this file already carry one and others don't (e.g. a
        # file hand-edited, or merged from two sources), a freshly assigned
        # id in the loop below can never collide with one about to be
        # restored a few blocks later. A no-op for the common case (a file
        # either fully has short_ids or, pre-migration, fully doesn't).
        from logic_studio.core import short_id as short_id_module
        short_id_module.resync_counters_with_existing_ids(
            proj, (b_data.get("short_id") for b_data in block_data_list)
        )

        # Instantiate blocks and wire up their pin UUIDs/connections. Connections
        # are fully defined by the UUID lists already embedded in each pin, so no
        # separate wiring pass is needed: GraphBuilder and the engine resolve
        # connections by UUID lookup at compile/run time.
        unknown_type_ids = []
        for b_data in block_data_list:
            type_id = b_data.get("type_id")
            block_class = BlockRegistry.get_block_class(type_id)

            if not block_class:
                label = type_id or f"(missing type_id, display_name={b_data.get('display_name')!r})"
                unknown_type_ids.append(label)
                continue

            block = block_class.deserialize(b_data)

            # One-time realignment (feat/block-rendering-library §4.6): a
            # block saved before ports were grid-aligned may sit at an
            # off-grid position. Its own ports are always placed at
            # grid-multiple offsets from ITS origin (block_item.py), so the
            # only thing that can put a port off-grid in scene coordinates
            # is an off-grid block origin — round it here, once, on every
            # load. A no-op for anything already on-grid.
            #
            # feat/editor-modes-and-geometry §1.6: this pass is UNCONDITIONAL
            # (runs on every load, not gated by schema_version) and always
            # rounds against whatever GRID_SIZE currently is — so when §1
            # dropped GRID_SIZE from 20 to 10, every position already
            # aligned to the old, coarser 20-grid stayed exactly where it
            # was (20 is itself a multiple of 10) with no separate migration
            # step needed. Verified empirically against all ten
            # examples/*.epwlogic fixtures: zero position corrections.
            block.set_position(
                round(block.x / GRID_SIZE) * GRID_SIZE,
                round(block.y / GRID_SIZE) * GRID_SIZE,
            )

            legacy_force = b_data.pop("_legacy_force_state", None)
            if legacy_force:
                block.simulation_state["force_state"] = legacy_force

            # feat/wire-modes-and-labels §0.1: restore every SERIALIZED_
            # FIELDS value (uuid, connections, disabled, safety_relevant,
            # ...) via the one shared Pin.restore_fields() implementation,
            # instead of this loop hand-copying a chosen few attributes by
            # name — that hand-copying is exactly what silently dropped
            # `disabled` (and, before that, aliased `connections` instead of
            # copying it) the last two times a field was added to Pin. A
            # field newly added to Pin.SERIALIZED_FIELDS is picked up here
            # automatically, with no separate edit needed in this loop.
            from logic_studio.blocks.pin import Pin
            for i, pin_data in enumerate(b_data.get("inputs", [])):
                if i < len(block.inputs):
                    Pin.restore_fields(block.inputs[i], pin_data)

            for i, pin_data in enumerate(b_data.get("outputs", [])):
                if i < len(block.outputs):
                    Pin.restore_fields(block.outputs[i], pin_data)

            proj.add_block(block)

        if unknown_type_ids:
            raise ValueError(
                "Project references unrecognized block type(s), refusing to load "
                "and silently drop logic: " + ", ".join(unknown_type_ids)
            )

        return proj
