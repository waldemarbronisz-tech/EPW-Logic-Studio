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

        # Output image written by blocks during a scan, pushed to the IOProvider
        # atomically at the end of that scan (see step()). Split by kind since
        # IOProvider has separate digital/analog write methods. "internal"
        # (feat/internal-bits §2.3) joins them here — same atomic-flush
        # mechanism, its own key since IOProvider.write_internal() is its
        # own method too.
        self._output_buffer = {"digital": {}, "analog": {}, "internal": {}}

        # Every output address ever queued during this engine's lifetime, so
        # stop()/FAULT can drive all of them to a safe state even ones that
        # were not touched during the final scan (see stop()). Internal
        # signals are deliberately NOT included — unlike physical outputs,
        # an internal signal has no "safe state" the engine can decide on
        # its own (BOOL's False isn't obviously safer than True for an
        # arbitrary M-bit), so stopping the engine leaves them as they were.
        self._touched_outputs = {"digital": set(), "analog": set()}

    def queue_digital_output(self, address: str, value: bool):
        """Called by output blocks during evaluate(). Buffers the write instead of
        touching the IOProvider immediately, so every output block in a scan sees
        the same consistent image and the physical/simulated outputs all change
        together at the end of the scan, not one-by-one as execution_order happens
        to visit them (see ARCHITECTURE.md §2, step 5 "push outputs")."""
        self._output_buffer["digital"][address] = value
        self._touched_outputs["digital"].add(address)

    def queue_analog_output(self, address: str, value: float):
        """Analog counterpart of queue_digital_output() — same atomic-flush
        buffering, written out via IOProvider.write_analog_output()."""
        self._output_buffer["analog"][address] = value
        self._touched_outputs["analog"].add(address)

    def queue_internal_write(self, name: str, value):
        """Internal-signal counterpart of queue_digital_output() (feat/
        internal-bits §2.3) — same atomic-flush buffering (flushed via
        IOProvider.write_internal() at the end of step(), see step())."""
        self._output_buffer["internal"][name] = value

    def _fail_safe_outputs(self):
        """Drive every output address ever queued during this engine's
        lifetime to its safe state (digital False, analog 0.0) and drop
        anything buffered for a scan that never got to flush. Called from
        stop() and from the FAULT transition in start() — see 'fail-safe on
        stop' in ARCHITECTURE.md. Outputs are never left latched on their
        last value when the process is not actively being scanned."""
        self._output_buffer = {"digital": {}, "analog": {}, "internal": {}}
        if self.io is None:
            return
        for address in self._touched_outputs["digital"]:
            self.io.write_digital_output(address, False)
        for address in self._touched_outputs["analog"]:
            self.io.write_analog_output(address, 0.0)

    def load_program(self, program: CompiledProgram):
        """Hot-swap the compiled program."""
        self.program = program
        self.interval_ms = program.cycle_time_ms
        self.stop()

    def start(self):
        if not self.program or not self.program.execution_order:
            self.state = ExecutionState.FAULT
            self._fail_safe_outputs()
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
        """Stop the engine.

        Fail-safe on stop: outputs are NOT latched at their last value. Every
        output address ever queued during this engine's lifetime is driven to
        its safe state (digital False, analog 0.0) via the IOProvider before
        block runtime state (timers, latches, counters, edge memories, ...) is
        reset. The same fail-safe zeroing happens on a transition to FAULT
        (see start()). pause() deliberately does NOT do this — a pause
        freezes the scan, it does not shut the process down.
        """
        self.state = ExecutionState.STOPPED
        self._fail_safe_outputs()
        if self.program:
            for b in self.program.blocks:
                b.simulation_state.clear()
                if hasattr(b, 'reset_runtime_state'):
                    b.reset_runtime_state()
                for p in b.inputs + b.outputs:
                    p.value = None

    def step(self):
        """Execute exactly one scan cycle if not FAULT.

        Follows the 6-step PLC scan from ARCHITECTURE.md §2: acquire inputs,
        execute the topological graph, push outputs — each block evaluated
        exactly once per scan, and the output image written atomically at the
        end so a downstream data recorder never sees a scan half-applied.
        """
        if self.state == ExecutionState.FAULT or not self.program:
            return

        start_time = time.monotonic_ns()
        self._output_buffer = {"digital": {}, "analog": {}, "internal": {}}

        block_map = self.program.block_map
        pin_map = self.program.pin_map

        # 0. Disabled blocks (feat/clipboard-and-align §4.2): excluded from
        # execution_order by GraphBuilder, so they're never evaluate()'d —
        # but anything still wired to one of their outputs (a connection
        # left over from before it was disabled) must still see a defined,
        # type-appropriate value, never None. Forced every scan, not just
        # once, since ExecutionEngine.stop() wipes every pin's .value to
        # None (see stop() above) and start() never re-establishes it.
        for b in self.program.blocks:
            if not getattr(b, 'enabled', True):
                for p in b.outputs:
                    p.value = p.safe_default_value()

        # 1. Acquire: evaluate source blocks (no logic inputs) once, up front,
        # so their output is available to the rest of the graph this scan.
        acquired = set()
        for uuid in self.program.execution_order:
            b = block_map.get(uuid)
            if b and getattr(b, 'is_source', False):
                b.evaluate(engine=self)
                acquired.add(uuid)

        # 2. Execute graph: propagate connected values, then evaluate. Source
        # blocks are skipped here — they already ran in step 1 and must not be
        # evaluated a second time (e.g. a generator must not advance twice as fast).
        for uuid in self.program.execution_order:
            if uuid in acquired or uuid not in block_map:
                continue

            block = block_map[uuid]

            for pin in block.inputs:
                for conn_uuid in pin.connections:
                    source_pin = pin_map.get(conn_uuid)
                    if source_pin is not None and getattr(source_pin, 'direction', -1) == 1:
                        pin.value = source_pin.value
                        break  # Single-driver inputs: first (only) output connection wins.

            block.evaluate(engine=self)

        # 3. Push outputs: apply the buffered output image to the IOProvider in
        # one pass, after every block has finished evaluating.
        for address, value in self._output_buffer["digital"].items():
            self.io.write_digital_output(address, value)
        for address, value in self._output_buffer["analog"].items():
            self.io.write_analog_output(address, value)
        for name, value in self._output_buffer["internal"].items():
            self.io.write_internal(name, value)

        # 4. Diagnostics
        end_time = time.monotonic_ns()
        duration_ms = (end_time - start_time) / 1_000_000.0
        self.last_scan_duration_ms = duration_ms
        if duration_ms > self.max_scan_duration_ms:
            self.max_scan_duration_ms = duration_ms
        self.cycle_counter += 1

        # SYS.SCAN_TIME/SYS.CYCLE_COUNT (§3.2) — kept current on the
        # IOProvider itself so system.signal blocks reading them next scan
        # see this scan's numbers; only meaningful for SimulationIOProvider
        # (a real IOProvider implementation is free to compute these its
        # own way, or not support them at all).
        if hasattr(self.io, 'scan_time_ms'):
            self.io.scan_time_ms = duration_ms
        if hasattr(self.io, 'cycle_count'):
            self.io.cycle_count = float(self.cycle_counter)

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
