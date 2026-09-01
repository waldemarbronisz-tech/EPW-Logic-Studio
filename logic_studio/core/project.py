import json

# Bump when the on-disk .epwlogic schema changes in a way that requires migration.
EPWLOGIC_SCHEMA_VERSION = 1


def _migrate_legacy_force_state(block, b_data):
    """Back-compat for pre-audit .epwlogic files that persisted "Force State" as a
    property (see AUDIT_REPORT.md §5.1). Forcing an IO point is a runtime-only
    override now, so move any legacy value into simulation_state (never
    re-serialized) and strip it out of properties, so re-saving the project stops
    writing it back to disk."""
    if "Force State" in block.properties:
        value = block.properties.pop("Force State")
        if value and value != "NO FORCE":
            block.simulation_state["force_state"] = value


class Project:
    """Manages the full state of the Logic Studio engineering project."""

    def __init__(self):
        self.blocks = []
        self.settings = {
            "name": "New Project",
            "version": "1.0",
            "cycle_time_ms": 100
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
            raise ValueError(f"Unsupported schema version: {schema_version}")

        proj = cls()
        proj.settings = data.get("settings", proj.settings)

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
            _migrate_legacy_force_state(block, b_data)

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
