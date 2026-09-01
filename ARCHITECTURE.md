# EPW Logic Studio Architecture

## 1. Engine & Runtime Separation
The visual IDE canvas and the Runtime are explicitly decoupled.
The `ExecutionEngine` holds absolutely zero UI references. All time logic resolves through an injected `TimeProvider` interface and external signals resolve through an `IOProvider`.

## 2. Cycle Scan Semantics
Each block declares `is_source = True` in its constructor if it has no logic
inputs (DI, constants, system signals, the button/generator blocks, ...). This
is an explicit attribute, not inferred from `type_id` string prefixes.

1. Acquire inputs: evaluate every `is_source` block once, in `execution_order`.
   Their output is then available to the rest of the graph for this scan.
2. Execute the topological graph: for every remaining block, propagate values
   from connected pins, then evaluate it — exactly once per scan. Source
   blocks are skipped here since step 1 already ran them; evaluating a
   stateful source (e.g. the signal generator) twice per scan would make it
   run at twice its configured rate.
3. Push outputs: output blocks (`output.do`, `output.ao`) do not write to the
   IOProvider directly — they buffer their value into the engine's output
   image via `ExecutionEngine.queue_digital_output()` /
   `queue_analog_output()`. After the whole graph has been evaluated, the
   engine writes that buffered image to the IOProvider in one pass (digital
   then analog), so every output changes atomically at the end of the scan
   rather than one-by-one as `execution_order` happens to visit them.
4. Wait for next interval.

## 3. Schema Versioning
- Development format: `format: "EPW_LOGIC"`, `schema_version: 1`
- Compiled format: `format: "EPW_RUNTIME_LOGIC"`, `schema_version: 1`, carrying export
  provenance and integrity metadata: `generated_at` (UTC ISO 8601), `generated_by`
  (`EPW Logic Studio <version>`), `project_name`, `block_count` (executable blocks,
  i.e. `len(execution_order)`), `contains_forced_io`, and a `checksum` — SHA-256 of
  the canonical JSON (`sort_keys=True, separators=(',', ':')`) of every other field,
  computed before `checksum` itself is added. `Exporter.verify_checksum()` /
  `verify_checksum()` in `compiler/exporter.py` recomputes and compares it; EPW-OS
  is expected to call it before trusting an exported runtime file. Both the
  computation and the verification operate on a single closed `CHECKSUM_FIELDS`
  set — everything else in the dict is ignored, so passing `verify_checksum()`
  a `Compiler.compile()` result (which carries a non-serializable
  `CompiledProgram` under `"program"`) still returns the correct bool instead
  of raising `TypeError` (see AUDIT_REPORT.md §0.2).
- `Project.deserialize()` refuses to load a project that references an unrecognized
  block `type_id` — it raises `ValueError` naming the missing type(s) rather than
  silently dropping that logic (see AUDIT_REPORT.md §3.3).

## 4. Stateful Feedback Execution
Pure combinational logic feedback (e.g. `AND` looped back into itself) is prohibited. However, the compiler explicitly permits feedback if a node along the cycle is flagged with `is_stateful = True` (e.g., `TON`, `RS`, `SR`). This satisfies industrial loop criteria where latency exists through memory buffers.

## 5. Lifecycle and Restarts
The engine uses strict PLC-like stop/restart semantics. Upon encountering an `EngineState.STOPPED` state, a transition into `EngineState.RUNNING` triggers all instantiated Logic Blocks to execute `reset_runtime_state()`. The method zeroes all dynamic outputs, timer values, and edge triggers ensuring clean deterministic behavior irrespective of the memory states when the system halted.

**Fail-safe on stop:** `ExecutionEngine.stop()` — and a transition to
`ExecutionState.FAULT` (e.g. `start()` called without a valid compiled
program) — drive every output address ever queued during that engine's
lifetime to its safe state (digital `False`, analog `0.0`) via the
IOProvider, using `self._touched_outputs`. Outputs are never left latched at
their last value just because the scan loop stopped running; the physical
(or simulated) process is actively driven to a known-safe state. `pause()`
is the deliberate exception: it freezes the scan without touching any
output, since a pause is meant to hold the process, not shut it down.

## 6. Time and Testing Boundaries
All logical timings are evaluated deterministically using an injected `TimeProvider`.
- `SystemTimeProvider` implements standard Python monotonic checks for local production testing.
- `SimulationTimeProvider` allows testing logic graphs across hundreds of artificial ticks instantaneously by explicitly iterating `engine.time.advance()`, explicitly ensuring CI headless environments aren't reliant on wall-clock `time.sleep()`.

## 7. Runtime-Only Overrides (Force)
`DigitalInputBlock` and `VirtualInputBlock` support forcing their output to a
fixed value for commissioning/testing. That override lives in
`simulation_state["force_state"]`, never in `properties` — `properties` is
serialized into both the `.epwlogic` project file and the exported
`EPW_RUNTIME_LOGIC` runtime, so a force left in `properties` would ride along
into a saved project and potentially into the object it drives. Loading a
pre-audit project that still has `"Force State"` under `properties` migrates
it into `simulation_state` and strips it from `properties` on load (see
`_migrate_legacy_force_state` in `core/project.py`). If any block still has an
active force at export time, `Exporter.export()` sets
`contains_forced_io: true` and raises a compiler warning listing the forced
blocks, so it is visible before the runtime goes to a controller.

## 8. Fixed vs. Dynamic IO: DI/DO vs. AI/AO
This is a platform-wide rule, not just a Logic Studio one. Digital points
(`input.di`, `output.do`) map to physical terminals on the ELA01/ADA01
modules — a fixed channel count, so `DeviceModel.get_ela_addresses()` /
`get_ada_addresses()` are class-level constants (`ELA_CHANNELS = 32`, etc.)
with no project involved. Analog points have no such fixed hardware list:
what analog points exist, their address/name/unit/range and whether each is
an input or output are entirely defined per-project, in
`project.settings["analog_points"]` — edited via the Project Settings
dialog. `DeviceModel.get_analog_input_addresses(project)` /
`get_analog_output_addresses(project)` / `get_analog_point(project, address)`
therefore take a `project` argument, unlike their DI/DO counterparts.

Because the runtime engine deliberately never holds a live `Project`
reference (see §1), an `input.ai` block's `[min, max]` range (used for its
Quality out-of-range check) is resolved once, at compile time, in
`Compiler.compile()` — via `block.set_range(min, max)` on the isolated
runtime copy — rather than looked up live during `evaluate()`.
