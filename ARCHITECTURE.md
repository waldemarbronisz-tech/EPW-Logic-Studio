# EPW Logic Studio Architecture

## 1. Engine & Runtime Separation
The visual IDE canvas and the Runtime are explicitly decoupled.
The `ExecutionEngine` holds absolutely zero UI references. All time logic resolves through an injected `TimeProvider` interface and external signals resolve through an `IOProvider`.

## 2. Cycle Scan Semantics
1. Acquire inputs (evaluate all blocks starting with `input.*` against the IO provider).
2. Execute Topological Graph.
3. Propagate output connections to downstream inputs.
4. Evaluate logic blocks.
5. Push outputs (evaluate all output blocks, triggering writes back to IO Provider).
6. Wait for next interval.

## 3. Schema Versioning
- Development format: `format: "EPW_LOGIC"`, `schema_version: 1`
- Compiled format: `format: "EPW_RUNTIME_LOGIC"`, `schema_version: 1`

## 4. Stateful Feedback Execution
Pure combinational logic feedback (e.g. `AND` looped back into itself) is prohibited. However, the compiler explicitly permits feedback if a node along the cycle is flagged with `is_stateful = True` (e.g., `TON`, `RS`, `SR`). This satisfies industrial loop criteria where latency exists through memory buffers.
