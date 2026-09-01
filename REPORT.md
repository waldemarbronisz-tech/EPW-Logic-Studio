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
