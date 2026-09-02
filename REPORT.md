# EPW Logic Studio - Milestone Report

## PHASE 1 - REFERENCE-DRIVEN REBUILD

### VISUAL REWORK
- [X] Removed generic `QGraphicsRectItem` for logic gates.
- [X] Implemented `QPainterPath` for standard engineering shapes (AND=D-shape, OR=Shield, NOT=Triangle).
- [X] Implemented chevron/arrow shapes for Inputs/Outputs to match "tag" style.
- [X] Removed text labels from standard logic gates.
- [X] Adapted multi-input gates to use a vertical "bus bar" on the input side to scale pins vertically while keeping the gate shape size constant.
- [X] Implemented standard green (logic 1) and black (logic 0) coloring for live simulation wires and pins.
- [X] Port item geometry changed from circles to industrial tiny squares (3px radius equivalent).

### LIBRARY REWORK
- [X] Restructured block categories to match requested Polish industrial categories: `Bramki logiczne`, `Detekcja zboczy`, `Wejścia / Wyjścia`, `Elementy Analogowe`, `Timery`, `Przerzutniki`, `Przyciski`, `LED`, `Liczniki`, `Telemechanika`, `Inne`.
- [ ] `Zabezpieczenia Analogowe`, `Zabezpieczenia Dwustanowe`, `Zabezpieczenia Technologiczne`, `Łączniki`, `Banki Nastaw`, `Zabezpieczenia silnikowe` — struktura kategorii zadeklarowana w `LibraryPanel` (grupy istnieją i są ukrywane przy braku bloków), ale bloki do implementacji. Skorygowano z audytu (AUDIT_REPORT.md §7.1): wcześniej oznaczone jako ukończone, mimo że w `logic_studio/blocks/` nie było w nich ani jednego zarejestrowanego bloku.
- [X] Registered new blocks: `AND-3`, `AND-4`, `OR-3`, `OR-4`, `NAND-3`, `NAND-4`, `NOR-3`, `NOR-4`, `Przycisk`, `LED`, `Komunikat użytkownika`, `Generator sygnału`.

### TEST FILES
- [X] Updated test files will be generated upon running the UI or script, verifying the logic operations and UI structure.

### PASS/FAIL CHECKLIST
| Item | Status | Notes |
|------|--------|-------|
| FBD Shapes (AND, OR, NOT) | PASS | Accurate QPainterPaths |
| Tag IO Shapes (Chevron) | PASS | Precise vector paths |
| Simulation Wiring (Green/Black) | PASS | |
| Library Categories (Polish) | PASS | Exact matches |
| Specific Gate Variations (e.g. AND-4) | PASS | Tested 3 and 4 input variations |
| Square Pins | PASS | Radius 3px |

## CONCLUSION
The visual overhaul has been successfully implemented, pivoting the software from a generic node editor to a dedicated industrial Function Block Diagram (FBD) environment. The backend remains structurally intact, passing all pre-existing and new assertions.

## PHASE 2 - ARCHITECTURE HARDENING (RUNTIME READINESS)

### RUNTIME DECOUPLING
- [X] Abstracted `ExecutionEngine` to run headless, fully decoupled from `QTimer`, `QObject`, and `SimulationPanel`.
- [X] Introduced `IOProvider` interface to separate UI states from physical/simulated device IO polling.
- [X] Introduced `TimeProvider` interface to guarantee deterministic timer execution across scans.

### PROJECT & EXPORT SCHEMAS
- [X] Hardened `.epwlogic` persistence format with explicit `format="EPW_LOGIC"` and `schema_version`.
- [X] Hardened `.epwlogic.runtime.json` compiler export with `format="EPW_RUNTIME_LOGIC"`.
- [X] Eradicated `__class__.__name__` logic throughout validation and exporter; system strictly relies on stable `type_id` strings (e.g. `timer.ton`).

### COMPILER VALIDATION & STATEFUL TOPOLOGY
- [X] Compilation explicitly fails on pure combinational loops (e.g., `AND -> OR -> AND`).
- [X] Modified Kahn's algorithm to safely break backward cycles on Explicitly Stateful Blocks (`is_stateful = True` on Timers/Latches), permitting legal PLC feedback paths.
- [X] Compilation failures forcefully wipe the engine's `execution_order` array, preventing stale binaries from launching or exporting.

### CONNECTION & IO ADDRESSING RULES
- [X] Disallowed multiple driver connection sources to standard input pins.
- [X] Prevented implicit connection between incompatible data types without proper coercion blocks.
- [X] Refactored standard IO blocks (`DI`, `DO`) to expect fully qualified Device binding structures (`ELA01.DI01`).

### CONTINUOUS INTEGRATION
- [X] Converted test coverage to verify end-to-end evaluation using deterministic virtual clocks, `SimulationIOProvider`, and Pytest headless Qt environments (`QT_QPA_PLATFORM=offscreen`).

### STUB BLOCKS & DETERMINISTIC FATs
- [X] Removed hardcoded stubs. `SystemSignal`, `SignalGenerator`, `Button`, `LED`, and `UserMessage` map correctly to either dynamic engine execution loops or deterministic logic bindings.
- [X] Added specific integration tests validating strict single-scan ELA->LOGIC->ADA latency pipelines without GUI injection side effects.
- [X] Verified complete headless runtime evaluation using explicit `engine.step()` calls rather than relying on automated `QTimer` propagation.

## PHASE 3 — RENDERING LIBRARY & INTERNAL SIGNALS

Branches `fix/audit-stage-a-b` → `feat/analog-chain` → `fix/export-contract`
→ `feat/block-rendering-library` → `feat/internal-bits`. Full detail in
`AUDIT_REPORT.md` §11-§15; this entry is the milestone-log summary this file
has kept since Phase 1/2.

### AUDIT-DRIVEN HARDENING (`fix/audit-stage-a-b`, `feat/analog-chain`, `fix/export-contract`)
- [X] Functional bug fixes (TP timer state, TOF reading its own output, ButtonBlock never driving its output), fake UI elements removed (status bar, dead menu items, Device Explorer placeholder branches).
- [X] Full analog chain: project-defined analog points, `input.ai`/`output.ao` with quality/holdover, `analog.deadband`/`analog.quality`, hysteresis/on-off delay on every comparator.
- [X] `EPW_RUNTIME_LOGIC` made self-sufficient (`analog_points`, `_resolved_*` block properties) — `EPWLOGIC_SCHEMA_VERSION`/`RUNTIME_SCHEMA_VERSION` bumped to 2 with an explicit migration chain.

### BLOCK RENDERING LIBRARY (`feat/block-rendering-library`)
- [X] Procedural gate/IO/DOC shapes (`ui/canvas/shapes.py`), centralized visual constants (`ui/canvas/style.py`), procedural icons (`ui/icons.py`) — zero image files.
- [X] Grid-alignment invariant: every port on every of the 67 registered block types lands on a deterministic grid intersection (`tests/test_grid_alignment.py`).
- [X] Library panel rebuilt as a searchable tree with recently-used and procedural icons; new `ElementPreviewPanel`.
- [X] Documentation blocks (`doc.text`/`doc.note`/`doc.section`) actually render their `Text` property instead of an empty placeholder rectangle.
- [X] Device Explorer: every address leaf (ELA/ADA/analog) draggable straight onto the canvas as an already-configured block.

### INTERNAL SIGNALS (`feat/internal-bits`)
- [X] Closed six rendering-layer bugs found auditing the block library above (§0 of the PR — most notably `input.ai`'s Value/Quality outputs sharing one port position, and clipped pin labels on `analog.quality`).
- [X] Internal signal registry (`project.settings["internal_bits"]`) replacing free-text tags on `virtual.input`/`virtual.output`, plus new `internal.reg_in`/`internal.reg_out` (REAL registers) — a typo is now a compile error (§4 validator rules), not a silently-created new signal.
- [X] Fixed system-signal catalog (`core/system_signals_catalog.json`) — `system.signal` no longer reads through `read_digital_input()`, so a system signal can no longer collide with a physical DI address.
- [X] Cycle-delay detection: the compiler flags an internal-signal read scheduled ahead of its writer in `execution_order` — a diagnostic no reference tool offers, surfaced as a canvas marker and a compiler "info" message.
- [X] `SignalPickerDialog` ("Wybór sygnału", modeled on eTango Studio's "Wybór bitu dla logiki") and a registry-editor tab in Project Settings.
- [X] `EPWLOGIC_SCHEMA_VERSION`/`RUNTIME_SCHEMA_VERSION` bumped to 3; `internal_bits`/`system_catalog_version` added to the runtime export and its checksum.

### PASS/FAIL CHECKLIST (Phase 3)
| Item | Status | Notes |
|------|--------|-------|
| Every port grid-aligned (67 block types) | PASS | `test_grid_alignment.py`, "the most important test in the PR" |
| No two ports share a position | PASS | `test_no_two_ports_share_a_position` — added after `input.ai` shipped with exactly this bug |
| All `examples/*.epwlogic` load, migrate, compile, export | PASS | `test_every_example_loads_compiles_and_exports`, one fixture fixed (two `virtual.output` blocks sharing a default tag — a real pre-existing ambiguity the new validator correctly caught) |
| Internal-signal registry validation (5 rules) | PASS | `compiler/validator.py` §4 |
| Cycle-delay detection (positive + negative case) | PASS | `compiler/core.py::_compute_cycle_delayed_reads` |
| Export contract (internal_bits/system_catalog_version reconstructable without a live Project) | PASS | `tests/test_export_contract.py` |

## CONCLUSION (Phase 3)
276 → 500 tests. The rendering library closed the visual gap between the
canvas and reference industrial FBD tools; internal signals closed a real
correctness gap (silent signal-name collisions, both internal-to-internal
via free text and system-to-physical via a shared read path) with a
validated registry and a first-of-its-kind stale-read diagnostic. Two real
bugs were caught and fixed during this work rather than shipped: a
pre-existing fixture ambiguity the new "one writer" rule correctly exposed,
and a rename-vs-delete confusion in the registry editor that hung the test
suite in isolation before being diagnosed and fixed.

## PHASE 4 — EDITOR MODES & GEOMETRY (in progress)

Branch `feat/editor-modes-and-geometry`, §1-§4 committed so far (§5 onward
paused for a scheduled report/confirmation checkpoint per the task).

### GATE GEOMETRY (§1)
- [X] Gate body is now a fixed `GATE_BODY` (40x40) square regardless of
  input count — the D-shape/shield curve no longer flattens as inputs are
  added. Inputs beyond what the fixed body holds (4+) spread symmetrically
  above/below it and merge into a vertical rail at the body's own left edge.
- [X] `centered_port_offsets()` (`ui/canvas/shapes.py`) is the one shared
  formula for "N ports symmetric around a block's own center," used
  identically for the real `PortItem` placement and the lead/rail drawing.

### DISABLED ("ZAŚLEPIONE") INPUTS (§2)
- [X] A multi-input logic gate's unconnected input can be explicitly
  disabled — excluded from the block's own logic entirely (not fed an
  implicit default value), toggled by double-click or a right-click context
  menu action on the port, rendered as a short capped gray stub. Compile-time
  rules: no "unconnected" warning for a disabled input; a warning once a
  multi-input gate is down to one active input; an error if every input is
  disabled or if a block type that never opted in ends up with one anyway.

### LIBRARY — ROADMAP CATEGORIES REMOVED FROM THE UI (§3)
- [X] Six categories that had structure but zero registered blocks behind
  them — previously shown grayed out as "(w przygotowaniu)" — are removed
  from the tree entirely. Declaring a feature that doesn't exist yet is the
  same class of problem as a UI element showing a fabricated value; the
  roadmap now lives here instead of in the running application. They return
  as real, populated categories once blocks are registered under them:
  - Zabezpieczenia Analogowe
  - Zabezpieczenia Dwustanowe
  - Zabezpieczenia Technologiczne
  - Łączniki
  - Banki Nastaw
  - Zabezpieczenia silnikowe

### SIMULATION PANEL — UNREACHABLE DI/DO CHANNELS FIXED (§4)
- [X] Bug: the ELA (DI) and ADA (DO) channel grids were laid out in a
  hardcoded 4 columns, but the panel's typical docked width was really only
  wide enough for ~2 — DI03/DI04/DI07/DI08/... and the equivalent ADA
  channels were squeezed out of the visible area with no horizontal
  scrollbar available to reach them (`QScrollArea(widgetResizable=True)`
  never offers one). Half of all 32+32 channels were silently unreachable.
- [X] Column count is now computed from the panel's actual current width
  (`ELA_ADA_COLUMN_WIDTH`) and recalculated on every `resizeEvent`, so both
  docking wider/narrower and the initial docked width itself keep every
  channel reachable. A vertical scrollbar remains available whenever the
  now-taller (fewer-columns) content overflows.
- [X] Added a filter/search field above both grids (`io_filter`) — 32 inputs
  + 32 outputs is faster to search than to scroll for.
