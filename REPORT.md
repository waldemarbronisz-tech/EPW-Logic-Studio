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

## PHASE 4 — EDITOR MODES & GEOMETRY

Branch `feat/editor-modes-and-geometry`, merged (PR #8). §1-§4 shipped; §5
onward (editor work modes, wire drawing/branching, probes, labels) carried
into Phase 5 below under a fresh branch/PR rather than resumed here.

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
- **Correction (Phase 5 / feat/wire-modes-and-labels §0A):** manual GUI
  verification after this shipped found the fix was still wrong — the
  column count was computed from the PANEL's own requested width
  (`self.width()`), not the scroll area's actual viewport width, and
  `ELA_ADA_COLUMN_WIDTH` assumed a short "DI01"-style label when the real
  checkbox text was the full "ELA01.DI01". Both errors pushed the computed
  column count too high, so a third of all channels still rendered outside
  the visible area (now 3 columns computed where 2 truly fit, instead of
  the original bug's 4-computed-where-2-fit). Phase 5 §0A replaces this
  entire panel with a corrected, viewport-width-driven layout — see below.

## PHASE 5 — WIRE MODES & LABELS

Branch `feat/wire-modes-and-labels`, merged with §0/§0A only (§1 onward —
editor work modes, multi-segment wire drawing, wire labels/net semantics —
was not picked up again after this PR's report/confirmation checkpoint;
Phase 6 below is an independent PR, not a continuation of it).

### PIN/BLOCK SERIALIZATION — STRUCTURAL FIX (§0)
- [X] A field added to `Pin` has now silently failed to round-trip through
  save/load TWICE (`connections` aliased instead of copied; `disabled`
  dropped entirely) — both times because serialize() and deserialize() were
  two independently hand-written enumerations free to drift apart.
  `Pin.SERIALIZED_FIELDS` is now the single declared list both methods walk;
  `Pin.restore_fields()` is the one shared implementation of "which fields
  get restored onto an existing pin," used by both `Pin.deserialize()` and
  the project loader (which no longer hand-copies fields itself).
- [X] The same fix applied to `BaseLogicBlock` turned up a real, if latent,
  instance of the identical bug: `visibility`/`enabled` were serialized but
  never restored. Fixed via `BaseLogicBlock.SERIALIZED_FIELDS`.
- [X] Guardian tests (`tests/test_pin_serialization.py`): parametrized over
  every `SERIALIZED_FIELDS` entry, plus a field-audit test that fails if a
  new `Pin.__init__` attribute is added without being classified as
  persisted or transient.

### SIMULATION PANEL — FULL REBUILD (§0A)
- [X] Root cause of the still-broken panel (see Phase 4's correction note
  above): column count now derives from `QScrollArea.viewport().width()`
  (the actually-available space, minus the scrollbar itself) and a tile
  width computed from `QFontMetrics` on the real longest label, not a
  guessed constant.
- [X] New "tylko użyte" ("only used") filter, ON by default — a channel is
  "used" when some block's `Address` property references it. The single
  biggest usability improvement here: a real project uses a handful of the
  32 available DI/DO channels, and scrolling past the other 28 every time
  was pure friction.
- [X] Row redesigned (§0A.3): a colored state dot (not a checkbox — a
  checkbox means "setting," this means "state"), short address ("DI01," not
  "ELA01.DI01" — the module prefix is already in the section header and
  repeats 32 times for nothing), a description column ready for
  `project.settings["io_labels"]` once that registry exists (§0A.5 —
  forward-compatible, not implemented this PR), and a right-aligned value.
  The whole row is the click target for an input; output rows are visually
  inert and non-interactive (§0A.0: DI/AI is what the engineer sets, DO/AO
  is what the logic answers back).
- [X] "Wszystkie" (all-channels) view groups channels into fixed banks of 8
  (§0A.4), mirroring how physical IO modules/terminal strips are organized
  — resizing the panel only ever changes which COLUMN a whole group of 8
  lands in, never the channel order inside a group, so "DI17" is always the
  first row under "DI17-24" no matter the window width.

## PHASE 6 — I/O LABELS & SHORT IDS

Branch `feat/io-labels-and-ids`, all sections closed, no stop-and-report
checkpoint required by the task (data-model/presentation work only — no
editor-interaction or simulation-behavior changes).

### DESCRIPTIVE I/O ADDRESS LABELS (§1/§2/§3)
- [X] `project.settings["io_labels"]` (address -> label), read/written
  exclusively through `DeviceModel.get_io_label()`/`set_io_label()`/
  `get_labelled_addresses()`/`all_addresses()` — never the dict directly.
  Empty (post-strip) label removes the entry rather than storing "".
  `EPWLOGIC_SCHEMA_VERSION` 3 -> 4 (an intentionally empty migration —
  nothing to migrate FROM, but the version number should still reflect
  what the format supports).
- [X] New "Etykiety wejść/wyjść" tab in Project Settings: one row per
  fixed ELA/ADA channel plus every project analog point, a read-only
  Użycia (usage count) column, "pokaż tylko używane" default ON, a filter
  matching address or label text, import/export to JSON with an added/
  changed/skipped-count confirmation before ever overwriting anything.
- [X] Surfaced everywhere an address appears: the canvas block's own
  second line (Comment wins when set — it describes THIS USE, the label
  describes the ADDRESS; also fixed a resulting double-display of Comment
  found while wiring this up), the signal picker's Opis column (and its
  search, for free, since search already scans every column), and every
  compiler/validator message for an addressed I/O block
  ("i3 (ELA01.DI01 — Wyłącznik Q1 zamknięty)").
- [X] Exported in `EPW_RUNTIME_LOGIC` and covered by `CHECKSUM_FIELDS` —
  the canonical source for EPW-OS's own event-register/Historian text.
  `RUNTIME_SCHEMA_VERSION` 3 -> 4.
- [ ] `simulation.py` was explicitly out of scope for this PR (a parallel
  branch owned the panel at the time) — the panel doesn't read
  `io_labels` yet even though the registry is now populated and ready;
  wiring it in is a small follow-up once that branch's work is settled.

### SHORT BLOCK IDENTIFIERS (§4)
- [X] `BaseLogicBlock.short_id` ("g12", "i3", ...) — category letter +
  a project-persistent, monotonically increasing per-prefix counter
  (`project.settings["short_id_counters"]`, `core/short_id.py`) that never
  reissues a deleted block's number. Assigned exactly once, in
  `Project.add_block()` — the one choke point every block passes through,
  which is also what makes an older project without `short_id` get one
  per block, deterministically, in file order, with no dedicated
  migration step. `clone()` deliberately never copies it.
- [X] Replaces `display_name`/UUID in every compiler/validator message
  (`Validator._block_ref()`, `GraphBuilder`'s cycle-detection message,
  the cycle-delayed-read info message) — a bare `display_name` could be
  shared identically by several untitled blocks of the same type.
  Exported as each block's own `short_id` field in `EPW_RUNTIME_LOGIC`;
  already checksum-covered via the existing `"blocks"` entry.

### PROPERTY PANEL REBUILT (§5)
- [X] Four collapsible sections (Identyfikacja/Adresacja/Parametry/
  Zaawansowane) replacing the old flat table — an empty section for a
  given block type is hidden, not shown empty; expand state persisted
  per-section.
- [X] Typed, range-checked editors (QSpinBox/QDoubleSpinBox/QCombobox/
  QLineEdit) instead of free-text table cells a numeric property used to
  silently swallow bad input into. Domain floors by property name
  (non-negative time/count properties, sample counts >= 1) and cross-
  field min<max validation for the known Min/Max-shaped property pairs —
  a rejected edit reverts the field and shows a 4-second status-bar
  message instead of silently keeping (or silently discarding) the edit.
- [X] A numeric property's unit now lives on the editor as a suffix
  ("Preset" + " ms") instead of baked into the displayed name ("Preset
  (ms)") — the underlying `properties` dict KEY is untouched, this is
  presentation-only.
- [X] Undo-stack flooding fixed: commits happen on `editingFinished` (with
  spinbox keyboard-tracking off), and only when the value actually
  changed — not on every keystroke.
- [X] Widget leak fixed: every per-block editor widget set is explicitly
  torn down (`QFormLayout.removeRow()`, which deletes the underlying
  widgets outright) before the next block's is built.
- [X] §5.6 dead-property audit (mandatory per the task) — see ARCHITECTURE.md
  and the answers below; `Visible`/`Execution State` removed outright,
  `Enabled` kept (a real, if currently unreachable pending a UI toggle,
  `validate()` consumer).

### §5.6 — DEAD PROPERTY AUDIT ANSWERS
- **`Enabled`**: read by `BaseLogicBlock.validate()`
  (`if not self.enabled: return errors`) — KEPT. Honest caveat: nothing in
  the application currently ever writes it `False` (no UI toggle exists
  yet), so that branch is presently unreachable in practice. Its property-
  panel row was also dropped in this PR's rebuild — §5.1's own explicit
  section list never mentions one either.
- **`Visible`**: read nowhere except this class's own `serialize()`/
  `deserialize()` round-trip and the old property grid's display of it —
  REMOVED (attribute, serialization, property-grid row).
- **`Execution State`**: set once to `"Idle"` in `__init__`, never updated
  anywhere during simulation — permanently displayed a constant, misleading
  value. REMOVED entirely.

## PHASE 7 — SIGNAL CROSS-REFERENCE PANEL

Branch `feat/signal-crossref`, all sections closed, no stop-and-report
checkpoint required (read-only panel + one new data-model file — no
compiler/engine/editor-interaction changes).

### §0 — FIELD-AUDIT TEST COVERAGE CHECK (mandatory per the task)
- [X] Confirmed: the field-round-trip audit test
  (`test_every_serializable_pin_attribute_is_listed_in_serialized_fields`,
  tests/test_pin_serialization.py) covered ONLY `Pin`, despite
  `BaseLogicBlock` getting the identical `SERIALIZED_FIELDS` treatment
  earlier — and despite that class having ALREADY shown the exact bug the
  audit exists to catch (`visibility`/`execution_state`, found and removed
  in Phase 6 §5.6). Extended: `BaseLogicBlock._STRUCTURED_FIELDS` /
  `_TRANSIENT_FIELDS` (new class-level tuples, base.py) plus
  `test_every_serializable_block_attribute_is_accounted_for()`, the same
  audit shape as Pin's. A future block attribute added without being
  classified into SERIALIZED_FIELDS/_STRUCTURED_FIELDS/_TRANSIENT_FIELDS
  now fails immediately instead of silently losing its persistence a
  fourth time.

### §1 — CROSS-REFERENCE DATA MODEL (`core/crossref.py`)
- [X] `build_crossref(project)`/`find_issues(crossref)` — pure logic, no
  Qt, across all four signal namespaces (ARCHITECTURE.md §14). Reader/
  writer role from pin shape, not `type_id` — a future block type with an
  Address/Bit/Sygnał property is picked up automatically.
- [X] Deliberately duplicates a subset of `compiler/validator.py`'s rules
  — documented at length in both the module's own docstring and
  ARCHITECTURE.md §14, since it's easy to mistake for an oversight rather
  than the deliberate "this has to work without compiling" design it is.

### §2 — READ-ONLY "SYGNAŁY" PANEL (`ui/panels/signals.py`)
- [X] New tab, table (Stan/Sygnał/Typ/Etykieta/Zapisuje/Czyta), search +
  kind filters + "tylko problemy" (persisted), debounced (200ms) rebuild
  wired through `MainWindow.set_dirty()` — the one choke point every
  project mutation already passes through, so no other file needed
  touching to know when to refresh. Empty-state placeholder.

### §3 — NAVIGATION
- [X] Double-click jumps to the writer (or first reader) and pulses an
  outline around the block for ~1s — built entirely from signals.py via a
  temporary scene overlay, without touching block_item.py. Right-click
  lists every reader when there's more than one. Canvas selection
  highlights (never scrolls) the matching row(s).
- [ ] No existing navigation-history mechanism was found in the repo — none
  added, per the task's explicit instruction not to.

### §4 — BLOCK CONTEXT MENU
- [X] "Pokaż użycia sygnału" — enabled only for a block with an assigned
  Address/Bit/Sygnał, switches to the Sygnały tab and focuses that
  signal's row (resetting any stale filter that would otherwise hide it).
  The one change to block_item.py this PR permits.

### §5 — CSV EXPORT
- [X] "Project → Eksportuj listę sygnałów..." — stdlib `csv` module,
  UTF-8 BOM, `;` delimiter, exports exactly the currently-visible
  (filtered) rows read straight off the table's own rendered text, plus a
  "Problemy" column and a leading "#" comment line (project/date/filter
  flag).

### BUGS FOUND AND FIXED DURING THIS PR (not hypothetical — all caught by
tests actually failing)
- `_SEVERITY_RANK` (§2) had no "info" entry — KeyError the first time any
  signal got an info-level issue populated into the table. Fixed, and
  aligned the Stan-column icon / "tylko problemy" filter to the task's own
  literal wording (both explicitly error/warning only — info still gets a
  tooltip, just no color/icon and doesn't count as "a problem").
- `_pulse_highlight()`'s `QTimer` kept firing after its overlay/scene had
  already been destroyed (closing the window mid-animation) — wrapped in
  try/except RuntimeError, a real defensive fix (a user closing a project
  mid-pulse hits the same path a test does).
- `tests/test_signals_csv_export.py` originally constructed every
  `SignalsPanel()` with no injected `settings`, silently falling back to
  the REAL `QSettings("BroniszLabs", "EPW Logic Studio")` (Windows
  registry-backed) — the exact class of mistake the project's own standing
  rule warns about, and the direct cause of real, observed test-order
  flakiness (a stale filter value the buggy run itself wrote into the real
  registry broke unrelated later tests depending on run order). Fixed
  every construction site, and removed the leaked key from the real
  registry before re-verifying the suite was stable across repeated runs.

### Świadomie pominięte / poza zakresem tego PR
- Żadna zmiana w `compiler/validator.py`, `engine/`, ani sposobie pracy
  edytora — panel jest wyłącznie do odczytu, zgodnie z poleceniem.
- Poza nowymi plikami, testami i dokumentacją, jedyne dotknięte pliki to
  `main_window.py` (rejestracja zakładki/menu/hooków odświeżania) i
  `block_item.py` (wyłącznie §4's nowa pozycja menu kontekstowego +
  dwie małe metody pomocnicze) — potwierdzone `git diff --stat`.

## PHASE 8 — CLIPBOARD, ALIGNMENT & TEMPORARY BLOCK DISABLE

Branch `feat/clipboard-and-align`, all six sections closed. See
ARCHITECTURE.md §15 for the full design/rationale write-up; this section
covers the checklist, what was found/measured, and what's explicitly out
of scope.

### §1 — CLIPBOARD (COPY / CUT / PASTE)
- [X] In-app clipboard (`LogicScene.clipboard_data`), not `QClipboard` —
  cross-instance exchange explicitly out of scope per the task.
- [X] Ctrl+C copies selected blocks + connections BETWEEN them; a
  connection leaving the selection is silently dropped.
- [X] Ctrl+X = copy + delete (all connections, including ones leaving the
  selection), one undo entry.
- [X] Ctrl+V: fresh UUIDs/`short_id`s, connections remapped, properties
  copied unchanged. Duplicate-address output block: pasted as-is (never
  silently cleared, never blocked) with an indefinite status-bar warning.
  Cursor-anchored (grid-snapped) or offset+cascade placement — repeated
  Ctrl+V without moving the mouse never stacks copies.
- [X] Cut/Copy enabled only with a selection, Paste only with a non-empty
  clipboard, tracked live.
- [X] Ctrl+D (`duplicate_selected_items`) now reuses copy+paste — one
  implementation, not two.
- [X] Tests: `tests/test_clipboard.py`, 14 — every §1.7-required scenario
  plus action-state and one-undo-entry coverage.

### §2 — ALIGN & DISTRIBUTE
- [X] 8 operations (left/right/top/bottom edges, center horizontal/
  vertical, distribute horizontal/vertical), relative to the FIRST-
  selected block — selection order wasn't tracked anywhere, added via
  `BlockItem.itemChange()`'s `ItemSelectedHasChanged` → `LogicScene.
  selection_order`.
- [X] Distribute keeps the extreme blocks fixed, spaces the rest with
  EQUAL GAPS between edges (not equal spacing between reference points) —
  correct once blocks have different widths/heights, which is the norm
  here (an IO block is wider than a gate).
- [X] Snap-to-grid reused from the existing drag mechanism
  (`BlockItem.itemChange()`'s `ItemPositionChange`) — no second
  implementation.
- [X] Exactly one undo entry per operation regardless of block count.
- [X] Edit menu "Wyrównaj" submenu + canvas/block context menu (2+
  selected) — one shared `ALIGN_OPERATIONS`/`populate_align_menu()`.
- [X] Tests: `tests/test_align.py`, 20 — pixel-exact positions for all 8
  operations (widths fetched from the actual `BlockItem` at test time,
  since an IO block's width depends on rendered identifier text/font
  metrics — not safe to hardcode across environments), one-undo-entry
  checks, minimum-selection no-op guards, menu enablement.

### §3 — UNDO STACK FLOODING
- [X] `mouseReleaseEvent` pushed state unconditionally on every release
  over a selected block, even with no movement — fixed by comparing
  positions snapshotted in `mousePressEvent`.
- [X] Audited every `push_state()` call site in the repository (full list
  and per-site assessment below) — all but two already gated on a real
  change. The audit surfaced a second, more fundamental bug in those two
  (block drag, wire connect): both mutate state LIVE during the mouse
  gesture, and `push_state()` was being called AFTER that mutation,
  pushing the POST-change state instead of the pre-change one — undo was
  verified (empirically, before the fix) to be a no-op for both. Fixed by
  snapshotting `project.serialize()` in `mousePressEvent`, BEFORE the
  gesture, and pushing that stored snapshot instead of a fresh one
  (`Project.push_state()` now takes an optional pre-captured `state`).
  This goes slightly beyond the section's literal "fix the flooding"
  wording, but leaving it unfixed would have meant "drag a block, hit
  undo" silently did nothing — judged not acceptable to ship knowingly.
- [X] 50-entry cap, dropping the oldest — already present in
  `Project.push_state()` before this PR; a test now locks it in.
- [X] Measured the serialized-state size for the largest example,
  `examples/EPW_LOGIC_PRIORITY_A_TEST.epwlogic` (11 blocks): **9398
  bytes** (~9.2 KiB) per snapshot. A full 50-entry stack is therefore
  ~459 KiB worst case for today's largest example — not disproportionate.
  This scales roughly linearly with block count (~854 bytes/block here),
  so a hypothetical several-hundred-block project would sit in the
  low tens of MiB for a full stack — **noted here as a candidate for a
  future diff-based undo storage redesign if/when real projects grow
  that large, but no redesign was done in this PR** (out of scope per
  the task).
- [X] Tests: `tests/test_undo_stack.py`, 5 — no-growth on a no-move click
  (including a 10x repeated-click burst), exactly +1 on a real one-grid-
  cell move, undo-after-drag restores the exact pre-drag position (the
  §3.2 finding), the 50-entry cap.

**`push_state()` call sites found (§3.2 audit), all 11:**

| Site | Gated on a real change? |
|------|--------------------------|
| `property_grid.py:401` (`_commit_property`) | Yes — `if str(old_value) == str(new_value): return` before it |
| `property_grid.py:434` (`_commit_priority`) | Yes — `if ... == new_value: return` before it |
| `property_grid.py:481` (signal picker) | Yes — only after dialog Accept + a signal was chosen |
| `dialogs.py:547` (`apply_to_project`) | Yes in effect — once per dialog OK click, not per field edit |
| `port_item.py:129` (`_toggle_disabled`) | Yes — every call is an explicit, real toggle |
| `block_item.py:715` (`apply_doc_text`) | Yes — `if new_text == old: return` before it |
| `scene.py` `delete_selected_items` | Yes — gated on a non-empty selection |
| `scene.py` `paste_clipboard` | Yes — one paste = one real change |
| `scene.py` `add_block_from_library` | Yes — one add = one real change |
| `scene.py` `mouseReleaseEvent` (block drag) | **Fixed this PR** — was unconditional (flooding) AND pushed the post-move state (no-op undo); now gated on an actual position change and pushes the pre-drag snapshot |
| `scene.py` `mouseReleaseEvent` (wire connect) | **Fixed this PR** (state-order only, no flooding existed here) — was pushing the post-connect state; now pushes the pre-connect snapshot |
| `scene.py` `_apply_block_positions` (align/distribute, this PR) | Yes — pushed BEFORE `setPos()`, correct order from the start |

### §4 — TEMPORARY BLOCK DISABLE
- [X] `BaseLogicBlock.enabled` already existed, already read by
  `validate()` — only the UI toggle was missing.
- [X] Context menu ("Wyłącz blok"/"Włącz blok", label reflects that
  block's state) + Edit menu ("Wyłącz/Włącz zaznaczone bloki" for the
  whole selection, force-direction) — one undo entry regardless of count.
- [X] Excluded from `execution_order` (`GraphBuilder`); outputs forced to
  a safe, type-appropriate, never-`None` value every scan
  (`ExecutionEngine.step()`, `Pin.safe_default_value()`); excluded from
  `validate()` (pre-existing); excluded from runtime export entirely
  (`Exporter.export()` skips it in `"blocks"`).
- [X] Visibility: dimmed body + dashed red outline + diagonal
  strikethrough (`BlockItem.paint()`); dimmed outgoing wires
  (`WireItem.update_path()`); compiler WARNING naming every disabled
  block by `short_id` (see below); status-bar "Wyłączone bloki: N"
  counter; `"contains_disabled_blocks"` in the export, added to
  `CHECKSUM_FIELDS`, modeled on `contains_forced_io`.
- [X] Tests: `tests/test_block_disable.py`, 16.

**Compiler warning format** (a project with two disabled blocks,
`short_id`s `g1`/`g2`):
```
Projekt zawiera wyłączone bloki (pominięte w eksporcie): g1, g2
```

### Świadomie pominięte / poza zakresem tego PR
- §3.3's diff-based undo storage redesign — measured and flagged as a
  future candidate, not implemented, exactly as the task specified.
- No change to `compiler/validator.py` beyond what already existed —
  `validate()`'s disabled-block skip predates this PR.
- The Edit-menu enable/disable actions force a direction for the whole
  selection rather than flipping each block's own prior state
  independently — a deliberate reading of "the same action ... for the
  whole selection" (ARCHITECTURE.md §15.5); ambiguous in the task text,
  documented rather than silently assumed.
