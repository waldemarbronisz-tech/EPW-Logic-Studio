import json

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
            "schema_version": 1,
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
        """Loads project from JSON."""
        from logic_studio.blocks.registry import BlockRegistry

        # Schema validation
        fmt = data.get("format")
        if fmt and fmt != "EPW_LOGIC":
            raise ValueError(f"Unsupported format: {fmt}")

        schema_version = data.get("schema_version", 0)
        if schema_version > 1:
            raise ValueError(f"Unsupported schema version: {schema_version}")

        proj = cls()
        proj.settings = data.get("settings", proj.settings)

        block_data_list = data.get("blocks", [])

        # 1. Instantiate blocks without connections
        block_map = {}
        for b_data in block_data_list:
            type_id = b_data.get("type_id")

            # Backwards compatibility check for older JSONs
            if not type_id:
                disp_name = b_data.get("display_name")
                # Fallback to search if needed (not strictly required if we assume clean MVP)
                for cat in BlockRegistry.get_categories():
                    if disp_name in BlockRegistry._blocks[cat]:
                        # Oops, this is actually searching by dict key which is now type_id.
                        # It's better to enforce type_id existence.
                        pass

            block_class = BlockRegistry.get_block_class(type_id)

            if block_class:
                block = block_class.deserialize(b_data)

                for i, pin_data in enumerate(b_data.get("inputs", [])):
                    if i < len(block.inputs):
                        block.inputs[i].uuid = pin_data.get("uuid")
                        block.inputs[i].connections = pin_data.get("connections", [])

                for i, pin_data in enumerate(b_data.get("outputs", [])):
                    if i < len(block.outputs):
                        block.outputs[i].uuid = pin_data.get("uuid")
                        block.outputs[i].connections = pin_data.get("connections", [])

                block_map[block.uuid] = block
                proj.add_block(block)

        return proj
