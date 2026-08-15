class Exporter:
    def __init__(self, project, execution_order):
        self.project = project
        self.execution_order = execution_order

    def export(self) -> dict:
        """Generates the final logic.json structure optimized for the Runtime Engine."""

        # We store the runtime graph structure, discarding UI position/color data
        runtime_blocks = {}

        for block in self.project.blocks:
            # We map Pin UUIDs to Runtime memory indices or just use UUIDs for now
            inputs = [{"pin_uuid": pin.uuid, "name": pin.name, "type": pin.data_type, "connections": pin.connections} for pin in block.inputs]
            outputs = [{"pin_uuid": pin.uuid, "name": pin.name, "type": pin.data_type, "connections": pin.connections} for pin in block.outputs]

            runtime_blocks[block.uuid] = {
                "type": block.__class__.__name__,
                "category": block.category,
                "inputs": inputs,
                "outputs": outputs,
                "properties": block.properties
            }

        return {
            "version": "1.0",
            "execution_order": self.execution_order,
            "blocks": runtime_blocks
        }
