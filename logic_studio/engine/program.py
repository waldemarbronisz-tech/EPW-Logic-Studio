class CompiledProgram:
    """
    Immutable, self-contained payload that can be serialized,
    sent to the runtime, and executed independently of the UI model.
    """
    def __init__(self, blocks, execution_order, cycle_time_ms):
        # We store copies/clones of the blocks to avoid UI mutation
        self.blocks = blocks
        self.execution_order = execution_order
        self.cycle_time_ms = cycle_time_ms
        self.block_map = {b.uuid: b for b in self.blocks}

    def get_block(self, uuid):
        return self.block_map.get(uuid)
