import json

# Bump when the on-disk .epwlogic schema changes in a way that requires migration.
# Every bump needs a matching _migrate_vN_to_v(N+1)(data) function registered in
# _MIGRATIONS below — see AUDIT_REPORT.md §2 "Wersjonowanie schematów".
EPWLOGIC_SCHEMA_VERSION = 2


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


# Keyed by the version a migration upgrades FROM. Project.deserialize() walks
# this sequentially — apply the migration for the file's current version,
# re-check, repeat — so a v1 file is ready for a future v2 -> v3 migration to
# be added the exact same way: one function, one new entry here.
_MIGRATIONS = {
    1: _migrate_v1_to_v2,
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
            "analog_points": []
        }

        self.undo_stack = []
        self.redo_stack = []
        self.is_recording = False

    def push_state(self):
        """Take a snapshot of the current project state for undo."""
        if self.is_recording:
            return
        state = self.serialize()
        self.undo_stack.append(state)
        # Keep stack size manageable
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self):
        if not self.undo_stack:
            return None
        self.redo_stack.append(self.serialize())
        return self.undo_stack.pop()

    def redo(self):
        if not self.redo_stack:
            return None
        self.undo_stack.append(self.serialize())
        return self.redo_stack.pop()

    def add_block(self, block):
        if block not in self.blocks:
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

        block_data_list = data.get("blocks", [])

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

            legacy_force = b_data.pop("_legacy_force_state", None)
            if legacy_force:
                block.simulation_state["force_state"] = legacy_force

            for i, pin_data in enumerate(b_data.get("inputs", [])):
                if i < len(block.inputs):
                    block.inputs[i].uuid = pin_data.get("uuid")
                    block.inputs[i].connections = list(pin_data.get("connections", []))

            for i, pin_data in enumerate(b_data.get("outputs", [])):
                if i < len(block.outputs):
                    block.outputs[i].uuid = pin_data.get("uuid")
                    block.outputs[i].connections = list(pin_data.get("connections", []))

            proj.add_block(block)

        if unknown_type_ids:
            raise ValueError(
                "Project references unrecognized block type(s), refusing to load "
                "and silently drop logic: " + ", ".join(unknown_type_ids)
            )

        return proj
