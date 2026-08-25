import time
from logic_studio.engine.io_provider import IOProvider, SimulationIOProvider
from logic_studio.engine.time_provider import TimeProvider, SystemTimeProvider

class ExecutionState:
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    FAULT = "FAULT"

from logic_studio.engine.program import CompiledProgram

class RuntimeSnapshot:
    """Public read-only DTO for external UI/Tests to inspect runtime state without mutating it."""
    def __init__(self, cycle_counter, state, last_scan_duration_ms, blocks):
        self.cycle_counter = cycle_counter
        self.state = state
        self.last_scan_duration_ms = last_scan_duration_ms
        self.blocks = blocks

class RuntimeBlockState:
    def __init__(self, uuid, type_id, properties, inputs, outputs, simulation_state):
        self.uuid = uuid
        self.type_id = type_id
        self.properties = properties
        self.inputs = inputs
        self.outputs = outputs
        self.simulation_state = simulation_state

class RuntimePinState:
    def __init__(self, uuid, name, value):
        self.uuid = uuid
        self.name = name
        self.value = value

class ExecutionEngine:
    """
    Simulates the PLC execution cycle using a CompiledProgram:
    1. Read inputs (ELA)
    2. Evaluate topological graph
    3. Write outputs (ADA)
    """

    def __init__(self, program: CompiledProgram, io_provider: IOProvider, time_provider: TimeProvider):
        self.program = program
        self.io = io_provider
        self.time = time_provider

        self.interval_ms = program.cycle_time_ms if program else 100
        self.state = ExecutionState.STOPPED

        # Diagnostics
        self.last_scan_duration_ms = 0.0
        self.max_scan_duration_ms = 0.0
        self.cycle_counter = 0

    def load_program(self, program: CompiledProgram):
        """Hot-swap the compiled program."""
        self.program = program
        self.interval_ms = program.cycle_time_ms
        self.stop()

    def start(self):
        if not self.program or not self.program.execution_order:
            self.state = ExecutionState.FAULT
            print("Cannot start simulation without a valid compiled execution program.")
            return

        # If starting from stopped, we need to reset blocks
        if self.state == ExecutionState.STOPPED:
            for b in self.program.blocks:
                b.simulation_state.clear()
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
        if self.program:
            for b in self.program.blocks:
                b.simulation_state.clear()
                if hasattr(b, 'reset_runtime_state'):
                    b.reset_runtime_state()
                for p in b.inputs + b.outputs:
                    p.value = None

    def step(self):
        """Execute exactly one scan cycle if not FAULT."""
        if self.state == ExecutionState.FAULT or not self.program:
            return

        start_time = time.monotonic_ns()

        block_map = self.program.block_map

        # 1. Acquire input image and all source blocks that have no inputs
        for uuid in self.program.execution_order:
            b = block_map.get(uuid)
            if b and (b.type_id.startswith("input.") or not b.inputs or b.type_id == "virtual.input" or b.type_id == "const.real" or b.type_id == "system.signal"):
                b.evaluate(engine=self)

        # 2. Execute graph
        for uuid in self.program.execution_order:
            if uuid in block_map:
                block = block_map[uuid]

                # Signal propagation (read from connected pins)
                for pin in block.inputs:
                    # In Kahn graph we might have stale logic if connections array maps output -> input.
                    # Wait, out.connections contains input pin UUIDs. in.connections contains output pin UUIDs.
                    for conn_uuid in pin.connections:
                        source_pin = self._find_pin_by_uuid(conn_uuid, block_map)
                        if source_pin and getattr(source_pin, 'direction', -1) == 1:
                            pin.value = source_pin.value
                            break # Only take first valid output connection

                # Also we must handle forward propagation if order is strict.
                # Actually, connections are mutual in this system:
                # out.connections has in.uuid, and in.connections has out.uuid.

                # Execute logic
                # Even if it's an input block, evaluating again is harmless if it's topological.
                # Let's just evaluate everything in order.
                block.evaluate(engine=self)

        # 3. Diagnostics
        end_time = time.monotonic_ns()
        duration_ms = (end_time - start_time) / 1_000_000.0
        self.last_scan_duration_ms = duration_ms
        if duration_ms > self.max_scan_duration_ms:
            self.max_scan_duration_ms = duration_ms
        self.cycle_counter += 1

    def get_runtime_snapshot(self) -> RuntimeSnapshot:
        """Returns a stable, read-only snapshot of the current runtime execution."""
        blocks = {}
        if self.program:
            for uuid, b in self.program.block_map.items():
                inputs = {p.uuid: RuntimePinState(p.uuid, p.name, p.value) for p in b.inputs}
                outputs = {p.uuid: RuntimePinState(p.uuid, p.name, p.value) for p in b.outputs}
                # Also store by name for easy test access
                for p in b.inputs:
                    inputs[p.name] = RuntimePinState(p.uuid, p.name, p.value)
                for p in b.outputs:
                    outputs[p.name] = RuntimePinState(p.uuid, p.name, p.value)

                blocks[uuid] = RuntimeBlockState(
                    uuid, b.type_id, b.properties.copy(),
                    inputs, outputs, b.simulation_state.copy()
                )
        return RuntimeSnapshot(self.cycle_counter, self.state, self.last_scan_duration_ms, blocks)

    def get_block_state(self, block_uuid: str) -> RuntimeBlockState:
        snapshot = self.get_runtime_snapshot()
        return snapshot.blocks.get(block_uuid)

    def _find_pin_by_uuid(self, pin_uuid, block_map):
        for block in block_map.values():
            for p in block.outputs:
                if p.uuid == pin_uuid:
                    return p
            for p in block.inputs:
                if p.uuid == pin_uuid:
                    return p
        return None
