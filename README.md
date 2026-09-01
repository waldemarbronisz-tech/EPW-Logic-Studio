# EPW Logic Studio

A visual Function Block Diagram (FBD) editor and runtime compiler designed for the EPW OS automation platform.

## Architecture

EPW Logic Studio strictly decouples the UI layout logic from the execution runtime.

1. **Engineering UI (`logic_studio.ui`)**: Visual drag-and-drop FBD canvas. Translates graphical wires and block placements into an internal JSON-based Object Model.
2. **Project Model (`logic_studio.core`)**: Maintains `EPW_LOGIC` project schema versioning and structural integrity.
3. **Compiler (`logic_studio.compiler`)**: Generates topological execution orders. Rejects combinational loops while explicitly allowing cycles passing through `is_stateful` memory/timer blocks.
4. **Execution Engine (`logic_studio.engine`)**: A fully headless Python PLC-style runtime execution loop, decoupled from the wall clock via `TimeProvider` and decoupled from hardware by `IOProvider`.

## Features
- **Headless Runtime:** Capable of running simulation steps completely independently of PySide6/Qt context.
- **Strict Data Typing:** Prevents logic connection bridging between incompatible boolean/float/integer boundaries.
- **Versioned, Verifiable Exports:** Compiles `EPW_RUNTIME_LOGIC` with provenance metadata (`generated_at`, `generated_by`, `project_name`, `block_count`, `contains_forced_io`) and a SHA-256 checksum, ready for ingestion by distributed EPW OS targets.
- **Hardware Agnostic Mappings:** Leverages zero-padded endpoint binding identifiers (`ELA01.DI01`, `ADA01.DO16`).
- **Analog Chain:** Project-defined analog points (`AI`/`AO` blocks, `analog.deadband`, `analog.quality`, and hysteresis/on-off delay on every comparator) — unlike DI/DO, analog points are not fixed hardware channels; they're declared per-project in Project Settings and flow through the whole `Elementy Analogowe` library from acquisition to output.
- **Fail-Safe on Stop:** Stopping the engine (or a transition to FAULT) drives every output ever written that session to its safe state (digital `False`, analog `0.0`) instead of leaving it latched at its last value.
