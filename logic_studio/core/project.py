import json

class Project:
    """Manages the full state of the Logic Studio engineering project."""

    def __init__(self):
        self.blocks = []
        self.wires = [] # Represented conceptually here; UI maintains actual WireItems
        self.settings = {
            "name": "New Project",
            "version": "1.0",
            "cycle_time_ms": 10
        }

    def add_block(self, block):
        self.blocks.append(block)

    def remove_block(self, block):
        if block in self.blocks:
            self.blocks.remove(block)

    def serialize(self) -> dict:
        """Serialize full project for saving to .project file."""
        return {
            "settings": self.settings,
            "blocks": [b.serialize() for b in self.blocks]
        }

    @classmethod
    def deserialize(cls, data: dict):
        """Loads project from JSON."""
        from logic_studio.blocks.registry import BlockRegistry

        proj = cls()
        proj.settings = data.get("settings", proj.settings)

        block_data_list = data.get("blocks", [])

        # 1. Instantiate blocks without connections
        block_map = {}
        for b_data in block_data_list:
            # We need the class to deserialize
            # Simple approach: Search registry by name/cat
            block_class = None
            for cat in BlockRegistry.get_categories():
                if b_data.get("display_name") in BlockRegistry.get_blocks_in_category(cat):
                    block_class = BlockRegistry._blocks[cat][b_data.get("display_name")]
                    break

            if block_class:
                block = block_class.deserialize(b_data)

                # Restore Pins manually here
                # In production, pin deserialization is complex (matching by name or UUID)
                # For Phase 1 we assume the inputs/outputs length matches the class defaults.
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
