import time
from logic_studio.engine.io_provider import IOProvider, SimulationIOProvider
from logic_studio.engine.time_provider import TimeProvider, SystemTimeProvider

class ExecutionState:
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    FAULT = "FAULT"

class ExecutionEngine:
    """
    Simulates the PLC execution cycle:
    1. Read inputs (ELA)
    2. Evaluate topological graph
    3. Write outputs (ADA)
    """

    def __init__(self, project, execution_order, io_provider: IOProvider, time_provider: TimeProvider):
        self.project = project
        self.execution_order = execution_order # List of block UUIDs

        self.io = io_provider
        self.time = time_provider

        self.interval_ms = project.settings.get("cycle_time_ms", 100)
        self.state = ExecutionState.STOPPED

        # Diagnostics
        self.last_scan_duration_ms = 0.0
        self.max_scan_duration_ms = 0.0
        self.cycle_counter = 0

    def start(self):
        if not self.execution_order:
            self.state = ExecutionState.FAULT
            print("Cannot start simulation without a valid compiled execution order.")
            return

        # If starting from stopped, we need to reset blocks
        if self.state == ExecutionState.STOPPED:
            for b in self.project.blocks:
                if hasattr(b, 'reset_runtime_state'):
                    b.reset_runtime_state()

        self.state = ExecutionState.RUNNING

    def pause(self):
        if self.state == ExecutionState.RUNNING:
            self.state = ExecutionState.PAUSED

    def resume(self):
        if self.state == ExecutionState.PAUSED:
            self.state = ExecutionState.RUNNING

    def stop(self):
        self.state = ExecutionState.STOPPED
        for b in self.project.blocks:
            if hasattr(b, 'reset_runtime_state'):
                b.reset_runtime_state()
            b.simulation_state.clear()
            for p in b.inputs + b.outputs:
                p.value = None

    def step(self):
        """Execute exactly one scan cycle if not FAULT."""
        if self.state == ExecutionState.FAULT:
            return

        start_time = time.monotonic_ns()

        # 0. Build lookup
        block_map = {b.uuid: b for b in self.project.blocks}

        # 1. Acquire input image
        for uuid in self.execution_order:
            b = block_map.get(uuid)
            if b and b.type_id.startswith("input."):
                b.evaluate(engine=self)

        # 2. Execute graph
        for uuid in self.execution_order:
            if uuid in block_map:
                block = block_map[uuid]

                # Signal propagation
                for pin in block.inputs:
                    for conn_uuid in pin.connections:
                        source_pin = self._find_pin_by_uuid(conn_uuid, block_map)
                        if source_pin:
                            pin.value = source_pin.value

                # Execute logic
                if not block.type_id.startswith("input."):
                    block.evaluate(engine=self)

        # 3. Diagnostics
        end_time = time.monotonic_ns()
        duration_ms = (end_time - start_time) / 1_000_000.0
        self.last_scan_duration_ms = duration_ms
        if duration_ms > self.max_scan_duration_ms:
            self.max_scan_duration_ms = duration_ms
        self.cycle_counter += 1

    def _find_pin_by_uuid(self, pin_uuid, block_map):
        for block in block_map.values():
            for p in block.outputs:
                if p.uuid == pin_uuid:
                    return p
        return None
