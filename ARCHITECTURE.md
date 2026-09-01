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
3. Push outputs: output blocks (`output.do`) do not write to the IOProvider
   directly — they buffer their value into the engine's output image via
   `ExecutionEngine.queue_digital_output()`. After the whole graph has been
   evaluated, the engine writes that buffered image to the IOProvider in one
   pass, so every output changes atomically at the end of the scan rather than
   one-by-one as `execution_order` happens to visit them.
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
  is expected to call it before trusting an exported runtime file.
- `Project.deserialize()` refuses to load a project that references an unrecognized
  block `type_id` — it raises `ValueError` naming the missing type(s) rather than
  silently dropping that logic (see AUDIT_REPORT.md §3.3).

## 4. Stateful Feedback Execution
Pure combinational logic feedback (e.g. `AND` looped back into itself) is prohibited. However, the compiler explicitly permits feedback if a node along the cycle is flagged with `is_stateful = True` (e.g., `TON`, `RS`, `SR`). This satisfies industrial loop criteria where latency exists through memory buffers.

## 5. Lifecycle and Restarts
The engine uses strict PLC-like stop/restart semantics. Upon encountering an `EngineState.STOPPED` state, a transition into `EngineState.RUNNING` triggers all instantiated Logic Blocks to execute `reset_runtime_state()`. The method zeroes all dynamic outputs, timer values, and edge triggers ensuring clean deterministic behavior irrespective of the memory states when the system halted.

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
