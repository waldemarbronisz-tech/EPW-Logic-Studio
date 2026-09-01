class CompiledProgram:
    """
    Immutable, self-contained payload that can be serialized,
    sent to the runtime, and executed independently of the UI model.
    """
    def __init__(self, blocks, execution_order, cycle_time_ms, cycle_delayed_reads=None):
        # We store copies/clones of the blocks to avoid UI mutation
        self.blocks = blocks
        self.execution_order = execution_order
        self.cycle_time_ms = cycle_time_ms
        self.block_map = {b.uuid: b for b in self.blocks}

        # feat/internal-bits §5.2: uuids of blocks reading an internal
        # signal that lags a scan behind its writer — computed once at
        # compile time (Compiler._compute_cycle_delayed_reads()), carried
        # here so the canvas can mark them (§5.3) without recomputing.
        self.cycle_delayed_reads = list(cycle_delayed_reads) if cycle_delayed_reads else []

        # pin_uuid -> Pin, built once so the engine can resolve a connection in
        # O(1) per pin instead of scanning every pin of every block on every scan.
        self.pin_map = {}
        for b in self.blocks:
            for p in b.inputs:
                self.pin_map[p.uuid] = p
            for p in b.outputs:
                self.pin_map[p.uuid] = p

    def get_block(self, uuid):
        return self.block_map.get(uuid)
